import os
import json
import time
import logging
from typing import List, Dict, Any, Optional, Callable
import httpx
from openai import OpenAI
from schemas import LedgerEntrySchema, MultiItemSaleSchema

logger = logging.getLogger(__name__)

# --- System Prompts and Templates ---

SYSTEM_PROMPT_TEMPLATE = """You are a precise JSON extractor for a Bangladeshi shopkeeper's voice ledger app.
Your task is to parse spoken Bangla utterances into structured ledger operations.

Rules:
1. Output MUST be valid JSON only. Do not add markdown explanation or extra text outside JSON.
2. Field rules:
   - transaction_type: MUST be either "new_sale" or "update_existing".
     * "new_sale": Creating a new transaction line for a customer.
     * "update_existing": Adjusting/paying off/adding to an existing matched customer entry.
   - customer_name: String in Bangla script. (Required)
   - item: Item name in Bangla script or null.
   - quantity: Quantity string in Bangla script or null (e.g. "১ কেজী", "২ টা").
   - total_amount_taka: Numeric total bill (float/int) or null.
   - paid_now_taka: Amount paid in this specific utterance (float/int) or null.
   - paid_amount_taka: Absolute cumulative paid amount confirmed by user, or null.
   - due_amount_taka: Absolute due amount confirmed by user, or null.
   - stated_due_taka: Stated due amount overriding computed due, or null.
   - full_settlement: Boolean true if utterance indicates complete settlement/payoff, else false.
   - matched_entry_id: Integer ID of an existing entry from OPEN_ENTRIES if matched, else null.

Matching Rules:
- Compare spoken customer name with OPEN_ENTRIES. Match phonetically or exact Bangla.
- If an open entry exists for that customer and the speaker is paying or updating due, set transaction_type = "update_existing" and matched_entry_id = <id>.

OPEN_ENTRIES:
{open_entries_json}
"""

FEW_SHOT_EXAMPLES = """
Examples:

Utterance: "রহিমকে ২ কেজী চাল দিলাম ১২০ টাকা, দিল ৫০ টাকা"
Output:
{"transaction_type": "new_sale", "customer_name": "রহিম", "item": "চাল", "quantity": "২ কেজী", "total_amount_taka": 120, "paid_now_taka": 50, "paid_amount_taka": 50, "due_amount_taka": 70, "stated_due_taka": null, "full_settlement": false, "matched_entry_id": null}

Utterance: "রহিম আরো ৫০ টাকা দিল"
Output:
{"transaction_type": "update_existing", "customer_name": "রহিম", "item": null, "quantity": null, "total_amount_taka": null, "paid_now_taka": 50, "paid_amount_taka": null, "due_amount_taka": null, "stated_due_taka": null, "full_settlement": false, "matched_entry_id": 1}

Utterance: "রহিম সব টাকা শোধ করে দিল"
Output:
{"transaction_type": "update_existing", "customer_name": "রহিম", "item": null, "quantity": null, "total_amount_taka": null, "paid_now_taka": null, "paid_amount_taka": null, "due_amount_taka": 0, "stated_due_taka": null, "full_settlement": true, "matched_entry_id": 1}
"""

DAILY_SALES_SYSTEM_PROMPT = """You are a precise JSON extractor for a Bangladeshi shopkeeper's daily sales log app.
Your task is to parse spoken Bangla utterances of cash sales into structured multi-item sale objects.

Rules:
1. Output MUST be valid JSON matching MultiItemSaleSchema:
   - customer_name: String in Bangla script or null if not mentioned.
   - items: List of items purchased. Each item object has:
     * item: Item name in Bangla script (Required)
     * quantity: Quantity string in Bangla script or null
     * unit_price_taka: Unit price in Taka (number) or null
   - total_amount_taka: Overall transaction total in Taka (number, Required)
2. Return ONLY the JSON object. No commentary or markdown wrapper.
"""

DAILY_SALES_FEW_SHOT = """
Transcript: "একজন কাস্টমার ২ ডজন ডিম, ১ কেজি ডিটারজেন্ট, আর ২ কেজি আটা কিনলো, সব মিলিয়ে ৩০০ টাকা।"
Output:
{"customer_name": null,
 "items": [
   {"item": "ডিম", "quantity": "২ ডজন", "unit_price_taka": null},
   {"item": "ডিটারজেন্ট", "quantity": "১ কেজি", "unit_price_taka": null},
   {"item": "আটা", "quantity": "২ কেজি", "unit_price_taka": null}
 ],
 "total_amount_taka": 300}
"""

LEDGER_ASK_SYSTEM_PROMPT = """You are a helpful assistant answering a small vendor's questions about who owes them money, in
natural spoken Bangla. You will be given DATA_CONTEXT (every customer's total, paid, and due
amounts) and a question, possibly containing ASR transcription errors. Answer using ONLY the
data provided — never invent or estimate numbers not in DATA_CONTEXT.

This assistant answers ONLY questions about customer dues/credit — who owes money, how much,
whether someone has settled up, who owes the most, or who has no outstanding balance. If the
question is about cash sales, items sold, or anything outside customer dues, politely say in
Bangla that this page only answers questions about বাকি/পাওনা (dues), and suggest asking on the
বিক্রয় (sales) page instead — do not attempt to answer it.

Keep answers short, natural, spoken-friendly — one or two sentences, in Bangla script.

DATA_CONTEXT:
{data_context_json}

Question: {transcript}"""

SALES_ASK_SYSTEM_PROMPT = """You are a helpful assistant answering a small vendor's questions about their daily cash sales,
in natural spoken Bangla. You will be given DATA_CONTEXT (today's items sold, today's total,
and daily sales totals for the last 30 days) and a question, possibly containing ASR
transcription errors. Answer using ONLY the data provided — never invent or estimate numbers
not in DATA_CONTEXT. To answer a question about a period like "last 7 days," sum the relevant
entries from daily_totals_last_30_days yourself.

This assistant answers ONLY questions about cash sales — what was sold, sales totals for a
period, or item-level details. If the question is about customer dues/credit or anything
outside sales, politely say in Bangla that this page only answers questions about নগদ বিক্রয়
(cash sales), and suggest asking on the হিসাব/বাকি (ledger) page instead — do not attempt to
answer it.

Keep answers short, natural, spoken-friendly — one or two sentences, in Bangla script.

DATA_CONTEXT:
{data_context_json}

Question: {transcript}"""

BUSINESS_SUMMARY_SYSTEM_PROMPT = """You are writing a short, professional business-activity summary in Bangla for a small vendor in Bangladesh, intended to be shown to a bank officer or microfinance representative as evidence of active, ongoing business. Use ONLY the numbers provided in DATA_CONTEXT — never invent, round misleadingly, or add figures not given. Write in a plain, respectful, factual register — no marketing language, no exaggeration, no exclamation marks. Three to five sentences. State the period covered, total sales activity (cash and credit combined), how many customers were served, how many days the business was active, and the current amount owed to the vendor by customers (as a receivable, not a problem). End with a plain factual closing statement, not a sales pitch. Do NOT include English words like 'factual' or formulaic sentences like 'এটি ব্যবসার বর্তমান আর্থিক অবস্থার একটি factual বিবরণ।'

DATA_CONTEXT:
{data_context_json}"""


class GemmaCallError(Exception):
    """Custom exception raised when Gemma LLM call fails unrecoverably."""
    pass


from dotenv import load_dotenv

def _get_llm_config() -> Dict[str, Any]:
    load_dotenv(override=True)

    # 1. Direct Google Gemini API (Dedicated free tier from Google AI Studio)
    gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
    if gemini_key and gemini_key != "your_gemini_api_key_here":
        clean_key = gemini_key.strip('"').strip("'")
        model_name = os.getenv("GEMINI_MODEL_NAME", "").strip() or "gemini-1.5-flash"
        return {
            "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
            "api_key": clean_key,
            "model": model_name,
            "provider": "Google Gemini (Official)",
            "fallback_models": [model_name, "gemini-1.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
        }

    # 2. OpenRouter API (supports user-configured model and automatic free fallback chain on 429)
    openrouter_key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if openrouter_key and openrouter_key != "sk-or-v1-xxxxxxxxxxxxxxxxxxxx":
        clean_key = openrouter_key.strip('"').strip("'")
        env_model = os.getenv("GEMMA_MODEL_NAME", "").strip()
        preferred_model = env_model or "google/gemma-4-26b-a4b-it:free"

        # Ordered free models to try on OpenRouter if the upstream pool is rate-limited (429)
        free_fallbacks = [
            preferred_model,
            "google/gemma-2-9b-it:free",
            "meta-llama/llama-3.3-70b-instruct:free",
            "meta-llama/llama-3.1-8b-instruct:free",
            "qwen/qwen-2.5-72b-instruct:free",
            "mistralai/mistral-7b-instruct:free"
        ]
        unique_fallbacks = list(dict.fromkeys([m for m in free_fallbacks if m]))

        return {
            "base_url": "https://openrouter.ai/api/v1",
            "api_key": clean_key,
            "model": preferred_model,
            "provider": "OpenRouter",
            "fallback_models": unique_fallbacks
        }

    # 3. Groq API
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    if groq_key and groq_key != "gsk_your_groq_api_key_here":
        clean_key = groq_key.strip('"').strip("'")
        model_name = os.getenv("GROQ_MODEL_NAME", "").strip() or "llama-3.3-70b-versatile"
        return {
            "base_url": "https://api.groq.com/openai/v1",
            "api_key": clean_key,
            "model": model_name,
            "provider": "Groq",
            "fallback_models": [model_name, "llama-3.3-70b-versatile", "llama-3.1-8b-instant"]
        }

    raise ValueError("Missing API key! Please set OPENROUTER_API_KEY, GEMINI_API_KEY, or GROQ_API_KEY in your environment.")


def _call_gemma_api(messages: List[Dict[str, str]], retries: int = 1) -> str:
    cfg = _get_llm_config()
    client = OpenAI(
        base_url=cfg["base_url"],
        api_key=cfg["api_key"],
        http_client=httpx.Client(timeout=30.0)
    )

    models_to_try = cfg.get("fallback_models", [cfg["model"]])
    last_error = None

    for model_name in models_to_try:
        for attempt in range(retries + 1):
            try:
                logger.info(f"Calling LLM via {cfg['provider']} ({model_name}), attempt {attempt + 1}/{retries + 1}")
                response = client.chat.completions.create(
                    model=model_name,
                    messages=messages,
                    temperature=0.1,
                    top_p=0.9,
                    max_tokens=512,
                    timeout=30.0
                )
                raw_text = response.choices[0].message.content
                if raw_text and raw_text.strip():
                    return raw_text.strip()
            except Exception as e:
                last_error = e
                err_msg = str(e)
                logger.warning(f"LLM call to {model_name} failed: {err_msg}")
                # If 429 rate limit on shared pool, break attempt loop and switch to next fallback model immediately!
                if "429" in err_msg or "rate-limited" in err_msg.lower() or "quota" in err_msg.lower():
                    logger.info(f"Model {model_name} is rate-limited upstream (429). Switching to next fallback model...")
                    break
                if attempt < retries:
                    time.sleep(1.0)

    raise RuntimeError(f"LLM API request failed ({cfg['provider']}): {str(last_error)}")


def _clean_json_text(text: str) -> str:
    """Clean markdown code block wrappers if present and isolate JSON object."""
    text = text.strip()
    if text.startswith("```json"):
        text = text[7:]
    elif text.startswith("```"):
        text = text[3:]
    if text.endswith("```"):
        text = text[:-3]
    text = text.strip()

    # If still has outer text, extract substring from first { to last }
    if not (text.startswith("{") and text.endswith("}")):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            text = text[start:end + 1]
    return text.strip()


def call_gemma(
    system_prompt: str,
    user_content: str,
    response_validator: Optional[Callable[[Any], Any]] = None,
    max_retries: int = 1
) -> Any:
    """
    Consolidated shared function to call Gemma 4.
    If response_validator is provided, validates JSON response against it and retries
    once with a repair instruction on failure. Returns raw text if no validator given.
    Raises GemmaCallError on unrecoverable failure.
    """
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content}
    ]

    try:
        raw_text = _call_gemma_api(messages, retries=max_retries)
    except Exception as e:
        logger.error(f"Gemma API call failed: {e}")
        raise GemmaCallError(f"Gemma API request failed: {str(e)}") from e

    if response_validator is None:
        return raw_text

    cleaned_json = _clean_json_text(raw_text)
    try:
        data = json.loads(cleaned_json)
        return response_validator(data)
    except Exception as parse_err:
        logger.warning(f"Initial JSON parse/validation failed: {parse_err}. Output was: '{cleaned_json}'. Retrying with repair instruction...")
        repair_messages = messages + [
            {"role": "assistant", "content": raw_text},
            {"role": "user", "content": f"Your last response was not valid JSON or failed schema validation ({str(parse_err)}). Return ONLY valid JSON matching the exact schema with no extra text."}
        ]
        try:
            repaired_raw = _call_gemma_api(repair_messages, retries=max_retries)
            repaired_json = _clean_json_text(repaired_raw)
            repaired_data = json.loads(repaired_json)
            return response_validator(repaired_data)
        except Exception as retry_err:
            logger.error(f"Repaired JSON output also failed validation: {retry_err}")
            raise GemmaCallError(f"Failed to extract valid JSON schema from Gemma 4: {str(retry_err)}") from retry_err


def extract_ledger_entry(transcript: str, open_entries: List[Dict[str, Any]]) -> LedgerEntrySchema:
    """Extract structured ledger entry from Bangla transcript using Gemma 4."""
    open_entries_json = json.dumps(open_entries, ensure_ascii=False, indent=2)
    system_prompt = SYSTEM_PROMPT_TEMPLATE.format(open_entries_json=open_entries_json)
    user_content = f"{FEW_SHOT_EXAMPLES}\n\nUser Spoken Transcript: \"{transcript}\"\n\nOutput:"
    return call_gemma(system_prompt, user_content, response_validator=LedgerEntrySchema.model_validate)


def extract_daily_sale(transcript: str) -> MultiItemSaleSchema:
    """Extract multi-item daily sales log transaction from Bangla transcript using Gemma 4."""
    user_content = f"{DAILY_SALES_FEW_SHOT}\n\nTranscript: \"{transcript}\"\n\nOutput:"
    return call_gemma(DAILY_SALES_SYSTEM_PROMPT, user_content, response_validator=MultiItemSaleSchema.model_validate)


def generate_daily_summary(open_entries: List[Dict[str, Any]]) -> str:
    """Generate professional spoken Bangla summary of open dues."""
    if not open_entries:
        return "বর্তমানে কোনো বকেয়া হিসাব নেই।"
    open_entries_json = json.dumps(open_entries, ensure_ascii=False, indent=2)
    sys_prompt = (
        "You are a professional accounting assistant for a shopkeeper in Bangladesh. "
        "Generate a concise, formal, and strictly professional spoken summary in clear Bangla (Bengali script) "
        "listing only the essential open dues. Do NOT include greetings or conversational filler."
    )
    user_content = f"Open entries list:\n{open_entries_json}\n\nGenerate direct professional Bangla summary:"
    try:
        return call_gemma(sys_prompt, user_content)
    except Exception:
        summary_parts = [f"{entry['customer_name']}: {entry.get('due_amount_taka')} টাকা" for entry in open_entries if entry.get('due_amount_taka')]
        total_due = sum(float(entry.get('due_amount_taka') or 0) for entry in open_entries)
        return "বকেয়া হিসাব: " + ", ".join(summary_parts) + f"। মোট বকেয়া: {total_due} টাকা।"


def ask_ledger_dues(transcript: str, data_context: dict) -> str:
    """PART A — Digital Ledger Q&A (/ledger/ask)."""
    data_context_json = json.dumps(data_context, ensure_ascii=False, indent=2)
    prompt_content = LEDGER_ASK_SYSTEM_PROMPT.format(
        data_context_json=data_context_json,
        transcript=transcript
    )
    try:
        return call_gemma("You are a helpful accounting assistant in Bangladesh.", prompt_content)
    except Exception as e:
        logger.error(f"Failed to get ledger dues answer via Gemma 4: {e}")
        return "দুঃখিত, বর্তমানে পাওনা হিসাবের উত্তর তৈরি করা সম্ভব হচ্ছে না।"


def ask_sales_info(transcript: str, data_context: dict) -> str:
    """PART B — Nagad Bikri Log Q&A (/sales/ask)."""
    data_context_json = json.dumps(data_context, ensure_ascii=False, indent=2)
    prompt_content = SALES_ASK_SYSTEM_PROMPT.format(
        data_context_json=data_context_json,
        transcript=transcript
    )
    try:
        return call_gemma("You are a helpful sales assistant in Bangladesh.", prompt_content)
    except Exception as e:
        logger.error(f"Failed to get sales info answer via Gemma 4: {e}")
        return "দুঃখিত, বর্তমানে বিক্রয় হিসাবের উত্তর তৈরি করা সম্ভব হচ্ছে না।"


def generate_business_summary(data_context: dict) -> str:
    """Generates formal 3-5 sentence business-activity summary in Bangla."""
    data_context_json = json.dumps(data_context, ensure_ascii=False, indent=2)
    prompt_content = BUSINESS_SUMMARY_SYSTEM_PROMPT.format(
        data_context_json=data_context_json
    )
    try:
        summary_text = call_gemma("You write professional business activity summaries in Bangla.", prompt_content)
        import re
        summary_text = re.sub(r'এটি ব্যবসার বর্তমান [^\n।]*factual[^\n।]*[।\.]?', '', summary_text).strip()
        summary_text = re.sub(r'এটি ব্যবসার বর্তমান [^\n।]*সংক্ষিপ্ত বিবরণ[।\.]?', '', summary_text).strip()
        return summary_text
    except Exception as e:
        logger.error(f"Failed to generate business summary via Gemma 4: {e}")
        return "দুঃখিত, ব্যবসার সারসংক্ষেপ তৈরি করতে সমস্যা হয়েছে।"
