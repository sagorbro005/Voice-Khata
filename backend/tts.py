import os
import uuid
import logging
from gtts import gTTS

logger = logging.getLogger("voice_ledger.tts")

AUDIO_OUTPUT_DIR = os.path.join(os.path.dirname(__file__), "..", "generated_audio")
os.makedirs(AUDIO_OUTPUT_DIR, exist_ok=True)


def to_bangla_numerals(val) -> str:
    """Convert integer/float or numeric string to Bangla numerals."""
    if val is None or val == "":
        return ""
    bangla_digits = {'0': '০', '1': '১', '2': '২', '3': '৩', '4': '৪', '5': '৫', '6': '৬', '7': '৭', '8': '৮', '9': '৯'}
    val_str = str(int(val) if isinstance(val, (int, float)) and float(val).is_integer() else val)
    return "".join(bangla_digits.get(ch, ch) for ch in val_str)


def build_confirmation_text(entry_data: dict) -> str:
    """
    Construct natural Bangla readback phrase from extracted ledger JSON.
    Example: 'করিম কে ৩ কেজি চাল, ১৫০ টাকা, আগামী কাল দেবে — ঠিক আছে?'
    """
    cust = entry_data.get("customer_name") or "গ্রাহক"
    item = entry_data.get("item")
    qty = entry_data.get("quantity")
    amount = entry_data.get("amount_taka")
    due_bn = entry_data.get("due_status_bn")
    action = entry_data.get("action")

    amount_bn = to_bangla_numerals(amount) if amount is not None else ""

    phrase_parts = []
    
    if action == "payment_received":
        phrase_parts.append(f"{cust} এর থেকে")
        if amount_bn:
            phrase_parts.append(f"{amount_bn} টাকা")
        phrase_parts.append("জমা পাওয়া গেছে।")
        if due_bn:
            phrase_parts.append(f"{due_bn}।")
    elif action == "update_existing":
        phrase_parts.append(f"{cust} এর আগের বাকিতে")
        if qty and item:
            phrase_parts.append(f"আরও {qty} {item}")
        elif qty:
            phrase_parts.append(f"আরও {qty}")
        elif item:
            phrase_parts.append(f"আরও {item}")
        if amount_bn:
            phrase_parts.append(f"{amount_bn} টাকা")
        phrase_parts.append("যোগ করা হয়েছে।")
        if due_bn:
            phrase_parts.append(f"{due_bn}।")
    else:  # new_sale
        phrase_parts.append(f"{cust} কে")
        if qty and item:
            phrase_parts.append(f"{qty} {item}")
        elif qty:
            phrase_parts.append(f"{qty}")
        elif item:
            phrase_parts.append(f"{item}")
        if amount_bn:
            phrase_parts.append(f"{amount_bn} টাকা")
        if due_bn:
            phrase_parts.append(f"{due_bn}।")

    phrase = " ".join(phrase_parts) + " ঠিক আছে?"
    return phrase


def synthesize_speech(text: str, filename_prefix: str = "readback") -> str:
    """
    Synthesize Bangla text to MP3 audio file using gTTS.
    Returns the filename (relative to static audio directory).
    """
    try:
        unique_id = uuid.uuid4().hex[:8]
        filename = f"{filename_prefix}_{unique_id}.mp3"
        filepath = os.path.join(AUDIO_OUTPUT_DIR, filename)

        logger.info(f"Synthesizing TTS audio for text: '{text}' -> {filepath}")
        tts = gTTS(text=text, lang="bn", slow=False)
        tts.save(filepath)

        return filename
    except Exception as e:
        logger.error(f"TTS synthesis failed: {e}", exc_info=True)
        raise RuntimeError(f"Failed to generate speech audio: {str(e)}")
