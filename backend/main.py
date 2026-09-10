import os
import sys
import logging
from typing import List, Dict, Any, Optional
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from dotenv import load_dotenv

# Add backend directory to sys.path
sys.path.insert(0, os.path.dirname(__file__))

import ledger_db
import ledger_logic
import asr
import gemma_client
from gemma_client import GemmaCallError
import tts
from schemas import (
    LedgerEntrySchema,
    UpdateEntryRequest,
    TranscribeResponse,
    ExtractRequest,
    ExtractResponse,
    ConfirmRequest,
    SummaryResponse,
    ErrorResponse,
    MultiItemSaleSchema,
    DailySaleExtractRequest,
    DailySaleExtractResponse,
    DailySaleConfirmRequest,
    InsightsAskRequest,
    InsightsAskResponse
)

# Load environment variables from .env file
load_dotenv(override=True)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("voice_khata")

# Fail fast requirement check for OpenRouter API Key
openrouter_key = os.getenv("OPENROUTER_API_KEY", "")
has_openrouter = openrouter_key and "sk-or-v1-xxxxxxxx" not in openrouter_key and openrouter_key.strip() != ""

if not has_openrouter:
    error_msg = (
        "\n" + "=" * 80 + "\n"
        "FATAL ERROR: OpenRouter API Key missing in environment!\n"
        "Please set OPENROUTER_API_KEY in your .env file:\n"
        "  OPENROUTER_API_KEY=sk-or-v1-your-key-here\n" +
        "=" * 80 + "\n"
    )
    logger.critical(error_msg)
    sys.stderr.write(error_msg)
    sys.exit(1)

# Initialize Database on startup
DB_PATH = os.getenv("DB_PATH", os.path.join(os.path.dirname(__file__), "..", "voice_khata.db"))
os.makedirs(os.path.dirname(os.path.abspath(DB_PATH)), exist_ok=True)
ledger_db.init_db(DB_PATH)

# Helper DB wrapper interface expected by ledger_logic
class DBLogicHelper:
    def __init__(self, db_path: str):
        self.db_path = db_path

    def get_entry(self, entry_id: int) -> Optional[Dict[str, Any]]:
        return ledger_db.get_entry(entry_id, self.db_path)

    def get_open_entries_by_name(self, customer_name: str) -> List[Dict[str, Any]]:
        return ledger_db.get_open_entries_by_name(customer_name, self.db_path)

db_logic_helper = DBLogicHelper(DB_PATH)

app = FastAPI(
    title="Voice Khata API",
    description="Voice-first financial ledger app powered by Gemma 4",
    version="1.0.0"
)

# Enable CORS for local frontend communication
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup_event() -> None:
    """Initialize STT model on app startup if available."""
    logger.info("Initializing ASR configuration...")
    try:
        asr.init_asr_model()
        logger.info("ASR initialized successfully.")
    except Exception as e:
        logger.warning(f"ASR initialization notice: {e}")


@app.get("/")
def root_endpoint() -> Dict[str, Any]:
    """Root endpoint verifying API is running."""
    return {
        "status": "online",
        "app": "Voice Khata API",
        "version": "1.0.0",
        "endpoints": {
            "health": "/health",
            "docs": "/docs",
            "entries": "/entries",
            "daily_sales": "/daily-sales/today",
            "business_summary": "/business-summary"
        }
    }


@app.get("/health")
def health_check() -> Dict[str, str]:
    """Returns system health status and active database backend."""
    return {
        "status": "ok",
        "app": "Voice Khata",
        "llm": "google/gemma-4-26b-a4b-it:free",
        "database": "SQLite (voice_khata.db)"
    }


@app.post("/transcribe", response_model=TranscribeResponse)
async def transcribe_endpoint(file: UploadFile = File(...)) -> Any:
    """Accepts audio file upload and transcribes spoken Bangla audio using pre-loaded ASR model."""
    logger.info(f"Received audio upload: {file.filename} (content_type={file.content_type})")
    try:
        content = await file.read()
        if not content or len(content) == 0:
            return JSONResponse(status_code=400, content={"error": "Uploaded audio file is empty."})
        
        transcript = asr.transcribe_audio(content)
        if not transcript:
            return JSONResponse(status_code=400, content={"error": "Could not extract intelligible speech from audio."})
        
        return TranscribeResponse(transcript=transcript)
    except Exception as e:
        logger.error(f"Transcribe endpoint error: {e}", exc_info=True)
        return JSONResponse(status_code=400, content={"error": f"Audio processing failed: {str(e)}"})


@app.post("/extract", response_model=ExtractResponse)
def extract_endpoint(req: ExtractRequest) -> Any:
    """Extracts structured credit entry JSON from spoken Bangla transcript using Gemma 4."""
    logger.info(f"Extract endpoint called with transcript: '{req.transcript}'")
    if not req.transcript or req.transcript.strip() == "":
        return JSONResponse(status_code=400, content={"error": "Transcript cannot be empty."})

    try:
        open_entries = ledger_db.get_open_entries(DB_PATH)
        extracted = gemma_client.extract_ledger_entry(req.transcript, open_entries)
        
        preview_update = None
        try:
            preview_update = ledger_logic.compute_ledger_update(extracted.model_dump(), db_logic_helper)
        except Exception as compute_err:
            logger.warning(f"Preview computation warning: {compute_err}")
            preview_update = None

        return ExtractResponse(
            structured_entry=extracted,
            preview_update=preview_update
        )
    except GemmaCallError as gerr:
        logger.error(f"Gemma extraction call failed: {gerr}")
        return JSONResponse(status_code=500, content={"error": f"LLM extraction failed: {str(gerr)}"})
    except Exception as e:
        logger.error(f"Extraction endpoint error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": f"Extraction failed: {str(e)}"})


@app.post("/confirm")
def confirm_endpoint(req: ConfirmRequest) -> Any:
    """Saves confirmed structured credit ledger entry to SQLite database."""
    logger.info(f"Confirm endpoint called with entry: {req.entry}")
    try:
        entry_dict = req.entry.model_dump()
        saved_entry, open_entries = ledger_db.save_ledger_entry(entry_dict, DB_PATH)
        all_entries = ledger_db.get_all_entries(DB_PATH)

        return {
            "message": "Entry saved successfully",
            "saved_record": saved_entry,
            "all_entries": all_entries,
            "open_entries": open_entries
        }
    except Exception as e:
        logger.error(f"Confirm endpoint error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": f"Failed to save ledger entry: {str(e)}"})


@app.post("/daily-sales/extract", response_model=DailySaleExtractResponse)
def daily_sales_extract_endpoint(req: DailySaleExtractRequest) -> Any:
    """Extracts multi-item cash sale transaction JSON from spoken Bangla transcript using Gemma 4."""
    logger.info(f"Daily sales extract called with transcript: '{req.transcript}'")
    if not req.transcript or req.transcript.strip() == "":
        return JSONResponse(status_code=400, content={"error": "Transcript cannot be empty."})

    try:
        extracted = gemma_client.extract_daily_sale(req.transcript)
        return DailySaleExtractResponse(structured_entry=extracted)
    except GemmaCallError as gerr:
        logger.error(f"Gemma sales extraction call failed: {gerr}")
        return JSONResponse(status_code=500, content={"error": f"Sales extraction failed: {str(gerr)}"})
    except Exception as e:
        logger.error(f"Daily sales extraction failed: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": f"Daily sales extraction failed: {str(e)}"})


@app.post("/daily-sales/confirm")
def daily_sales_confirm_endpoint(req: DailySaleConfirmRequest) -> Any:
    """Saves confirmed multi-item cash sale transaction to sales_transactions and sale_items tables."""
    logger.info(f"Daily sales confirm called with entry: {req.entry}")
    try:
        data = req.entry.model_dump()
        result = ledger_db.save_sales_transaction(data, DB_PATH)
        return result
    except Exception as e:
        logger.error(f"Daily sales confirm failed: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": f"Failed to save daily sales transaction: {str(e)}"})


@app.get("/daily-sales/today")
def daily_sales_today_endpoint() -> Any:
    """Returns today's cash sales transactions list and running total sum."""
    try:
        return ledger_db.get_today_sales(DB_PATH)
    except Exception as e:
        logger.error(f"Failed to fetch today's sales: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": f"Failed to fetch today's sales: {str(e)}"})


@app.get("/daily-sales/history")
def daily_sales_history_endpoint(
    range: str = "30days",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Any:
    """Returns sales transactions in resolved date range with itemized breakdown and aggregate summary."""
    try:
        return ledger_db.get_sales_history(range, start_date, end_date, DB_PATH)
    except ValueError as ve:
        return JSONResponse(status_code=400, content={"error": str(ve)})
    except Exception as e:
        logger.error(f"Failed to fetch sales history: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": f"Failed to fetch sales history: {str(e)}"})


@app.put("/entries/{entry_id}")
def update_entry_endpoint(entry_id: int, req: UpdateEntryRequest) -> Any:
    """Updates specific credit ledger entry fields in SQLite database."""
    logger.info(f"Update endpoint called for entry ID {entry_id}")
    try:
        updated_record = ledger_db.update_entry_fields(entry_id, req.model_dump(), DB_PATH)
        if not updated_record:
            return JSONResponse(status_code=404, content={"error": "এন্ট্রি খুঁজে পাওয়া যায়নি"})
        return {
            "message": "এন্ট্রি সফলভাবে আপডেট করা হয়েছে",
            "updated_record": updated_record,
            "all_entries": ledger_db.get_all_entries(DB_PATH)
        }
    except Exception as e:
        logger.error(f"Update entry endpoint error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": f"আপডেট ব্যর্থ হয়েছে: {str(e)}"})


@app.delete("/entries/{entry_id}")
def delete_entry_endpoint(entry_id: int) -> Any:
    """Deletes specific credit ledger entry from SQLite database."""
    logger.info(f"Delete endpoint called for entry ID {entry_id}")
    try:
        success = ledger_db.delete_entry(entry_id, DB_PATH)
        if not success:
            return JSONResponse(status_code=404, content={"error": "এন্ট্রি খুঁজে পাওয়া যায়নি"})
        return {
            "message": "এন্ট্রি সফলভাবে মুছে ফেলা হয়েছে",
            "all_entries": ledger_db.get_all_entries(DB_PATH)
        }
    except Exception as e:
        logger.error(f"Delete entry endpoint error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": f"ডিলিট ব্যর্থ হয়েছে: {str(e)}"})


@app.get("/summary", response_model=SummaryResponse)
def summary_endpoint() -> Any:
    """Generates professional spoken Bangla summary of open dues and synthesizes audio file."""
    logger.info("Summary endpoint called.")
    try:
        open_entries = ledger_db.get_open_entries(DB_PATH)
        summary_text = gemma_client.generate_daily_summary(open_entries)
        audio_filename = tts.synthesize_speech(summary_text, filename_prefix="summary")
        
        return SummaryResponse(
            summary_text=summary_text,
            audio_url=f"/audio/{audio_filename}"
        )
    except Exception as e:
        logger.error(f"Summary endpoint error: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": f"Failed to generate summary: {str(e)}"})


@app.get("/entries")
def get_entries_endpoint() -> Any:
    """Returns all ledger records and active open records from SQLite."""
    try:
        return {
            "all_entries": ledger_db.get_all_entries(DB_PATH),
            "open_entries": ledger_db.get_open_entries(DB_PATH)
        }
    except Exception as e:
        return JSONResponse(status_code=500, content={"error": f"Failed to fetch entries: {str(e)}"})


@app.post("/ledger/ask", response_model=InsightsAskResponse)
def ledger_ask_endpoint(req: InsightsAskRequest) -> Any:
    """Answers vendor questions about customer dues/credit using Gemma 4 and synthesizes spoken audio."""
    logger.info(f"Received ledger dues question: '{req.transcript}'")
    if not req.transcript or not req.transcript.strip():
        return JSONResponse(status_code=400, content={"error": "Question transcript cannot be empty."})

    try:
        data_context = ledger_db.build_ledger_data_context(DB_PATH)
        answer_text = gemma_client.ask_ledger_dues(req.transcript, data_context)
        audio_filename = tts.synthesize_speech(answer_text, filename_prefix="ledger_dues")

        return InsightsAskResponse(
            answer_text=answer_text,
            audio_url=f"/audio/{audio_filename}"
        )
    except Exception as e:
        logger.error(f"Error answering ledger dues question: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": f"Failed to answer question: {str(e)}"})


@app.post("/sales/ask", response_model=InsightsAskResponse)
def sales_ask_endpoint(req: InsightsAskRequest) -> Any:
    """Answers vendor questions about daily cash sales/items using Gemma 4 and synthesizes spoken audio."""
    logger.info(f"Received sales question: '{req.transcript}'")
    if not req.transcript or not req.transcript.strip():
        return JSONResponse(status_code=400, content={"error": "Question transcript cannot be empty."})

    try:
        data_context = ledger_db.build_sales_data_context(DB_PATH)
        answer_text = gemma_client.ask_sales_info(req.transcript, data_context)
        audio_filename = tts.synthesize_speech(answer_text, filename_prefix="sales_info")

        return InsightsAskResponse(
            answer_text=answer_text,
            audio_url=f"/audio/{audio_filename}"
        )
    except Exception as e:
        logger.error(f"Error answering sales question: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": f"Failed to answer question: {str(e)}"})


@app.get("/business-summary")
def get_business_summary_endpoint(
    range: str = "30days",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Any:
    """Returns Gemma 4 narrated business summary paragraph along with aggregate context metrics and activity logs."""
    logger.info(f"Received business summary request for range: '{range}'")
    try:
        period_map = {
            "30days": "গত ৩০ দিন",
            "90days": "গত ৯০ দিন",
            "all": "সব সময়",
            "today": "আজ",
            "7days": "গত ৭ দিন"
        }
        period_label = period_map.get(range, "নির্বাচিত সময়কাল")
        
        start_d, end_d = ledger_db.resolve_date_range(range, start_date, end_date)
        data_context = ledger_db.build_business_summary_context(start_d, end_d, period_label, db_path=DB_PATH)
        summary_text = gemma_client.generate_business_summary(data_context)

        return {
            "summary_text": summary_text,
            "context": data_context
        }
    except Exception as e:
        logger.error(f"Error generating business summary: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={"error": f"Failed to generate business summary: {str(e)}"})


@app.get("/audio/{filename}")
def serve_audio_file(filename: str) -> FileResponse:
    """Serves synthesized TTS audio files."""
    gen_path = os.path.join(os.path.dirname(__file__), "..", "generated_audio", filename)
    if os.path.exists(gen_path):
        return FileResponse(gen_path, media_type="audio/mpeg")

    raise HTTPException(status_code=404, detail="Audio file not found")
