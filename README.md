# Voice Khata 🎙️

> **Voice-First AI Financial Management & Ledger Assistant for Micro-Vendors in Bangladesh**  
> *Built for the **Build with Gemma 4** Hackathon*

---

## 📌 Executive Summary

**Voice Khata** is a voice-first financial ledger designed specifically for informal-economy vendors in Bangladesh—such as street sellers, rickshaw pullers, grocery vendors, and small shopkeepers. Vendors speak sales or credit updates aloud in natural **Bangla**, and Voice Khata automatically transcribes the audio using **Groq Whisper-large-v3** or `banglaspeech2text`, extracts structured financial transactions in **natural Bangla script** using **Gemma 4** (with multi-model free fallbacks on OpenRouter), and manages a local SQLite database (`voice_khata.db`) with full credit/due tracking, daily cash sales logs, business summary generation, and interactive AI voice Q&A.

---

## 🤖 LLM & ASR Implementation Overview

### 1. Multi-Model Resilient LLM Engine (`backend/gemma_client.py`)
- **Primary Engine**: **Google Gemma 4** (`google/gemma-4-26b-a4b-it:free` via OpenRouter).
- **Automatic Fallback Chain**: If the primary free endpoint is rate-limited (HTTP 429) or unavailable, the system automatically falls back through high-performing free models (`nvidia/nemotron-3-super-120b-a12b:free`, `nex-agi/nex-n2.5-pro:free`, `nvidia/nemotron-3.5-lightning:free`, `google/gemma-4-31b-it:free`) to guarantee 100% request success.
- **ASR Error Repair**: Prompts instruct the LLM to contextually resolve phonetic speech recognition errors.
- **Robust JSON Extraction**: Automatically parses, validates, and cleans markdown code blocks or reasoning wrappers to output pure structured JSON.

### 2. Dual-Engine Speech-to-Text (`backend/asr.py`)
- **Groq Cloud Whisper API**: *(Recommended)* Free `whisper-large-v3` API delivering ultra-fast ~200ms Bangla transcription with zero server RAM footprint.
- **Local ASR Fallback**: Standard `banglaspeech2text` (16kHz mono audio preprocessing via PyAV & Hugging Face pipeline).

### 3. Structured Credit Ledger Extraction (`extract_ledger_entry`)
- Parses spoken Bangla utterances into structured JSON (`customer_name`, `item`, `quantity`, `total_amount_taka`, `paid_amount_taka`, `due_amount_taka`, `matched_entry_id`).

### 4. Multi-Item Daily Sales Extraction (`extract_daily_sale`)
- Extracts itemized product arrays from single spoken utterances (e.g., *"২ কেজি চাল ১২০ টাকা আর ১ লিটার তেল ২০০ টাকা"*).

### 5. Dual Domain-Scoped Q&A Assistants (`ask_ledger_dues`, `ask_sales_info`)
- **Ledger Q&A (`/ledger/ask`)**: Answers questions regarding customer credit balances (*"কার কাছে সবচেয়ে বেশি বাকি?"*, *"সাগরের কত টাকা বাকি?"*) using strictly queried database context.
- **Sales Q&A (`/sales/ask`)**: Answers queries about cash sales (*"আজকে মোট কত টাকার বিক্রি হয়েছে?"*, *"গত ৭ দিনে মোট বিক্রয় কত?"*).
- **Domain Guardrails**: Enforces polite Bangla refusal and redirection if a vendor asks a sales question on the ledger page or vice versa.

### 6. Formal Business Summary Generation (`generate_business_summary`)
- Generates a 3–5 sentence, respectful, factual Bangla financial narrative for bank or microfinance loan officers.

---

## 🌟 Core Modules & Application Flow

### 📖 1. Digital Credit Ledger (ডিজিটাল হালখাতা)
- **Voice / Text Entry**: Speak or type credit transactions in Bangla.
- **Preview & Verification**: Vendors inspect extracted total, paid, and due amounts before confirming write operations to SQLite.
- **Customer Tabs**: Tracks open dues, partial payments, and full settlements automatically.

### 📋 2. Daily Cash Sales Log (আজকের নগদ বিক্রয় লগ)
- **Itemized Cash Sales Log**: Quick recording of cash sales transactions with multiple items.
- **Collapsible History Cards**: Interactive date-grouped list with expandable dropdown rows (`▼` / `▲`) showing itemized breakdowns.

### 📊 3. Business Summary (ব্যবসার সারসংক্ষেপ)
- **Formal Register Layout**: Credible, high-contrast document view designed for showing to financial officers.
- **Period Filtering**: Generate summaries across **30 Days**, **90 Days**, or **All Time**.
- **Combined Activity Log**: Auditable table combining cash transactions and credit records with period totals.

---

## 📂 Project Repository Structure

```text
Voice Ledger 2/
├── .env.example                # Template for environment variable keys
├── README.md                   # Project documentation & guide
├── reset_db.py                 # SQLite database schema reset script
├── voice_khata.db              # Active SQLite database file
├── backend/
│   ├── main.py                 # FastAPI application routes & CORS setup
│   ├── gemma_client.py         # Consolidated LLM client & prompts with fallback chain
│   ├── ledger_db.py            # SQLite database queries & context builders
│   ├── ledger_logic.py         # Ledger update rules & computation logic
│   ├── asr.py                  # Groq Cloud Whisper & BanglaSpeech2Text ASR pipeline
│   ├── tts.py                  # gTTS Bangla speech synthesis engine
│   ├── schemas.py              # Pydantic data schemas & response models
│   ├── utils.py                # Bangla numeral conversion utilities
│   └── requirements.txt        # Backend dependencies
└── frontend/
    ├── index.html              # Digital Credit Ledger page
    ├── app.js                  # Digital Ledger frontend controller
    ├── daily_sales.html        # Daily Cash Sales Log page
    ├── daily_sales.js          # Daily Sales Log frontend controller
    ├── business_summary.html   # Formal Business Summary page
    ├── business_summary.js     # Business Summary frontend controller
    └── shared/
        └── summary-theme.css   # Formal document stylesheet
```

---

## 🛠️ Technology Stack & Dependencies

| Layer | Technology |
| :--- | :--- |
| **Generative LLM** | Google Gemma 4 (`google/gemma-4-26b-a4b-it:free` via OpenRouter with multi-model fallback) |
| **Speech-to-Text (ASR)** | Groq Whisper-large-v3 API / `banglaspeech2text` |
| **Text-to-Speech (TTS)** | `gTTS` (Bangla voice synthesis for Q&A and summary) |
| **Backend Framework** | Python 3.9+, FastAPI 0.111.0, Uvicorn 0.30.1 |
| **Database** | SQLite (`voice_khata.db`) |
| **Frontend** | HTML5, Vanilla CSS3 (Glassmorphism design system), JavaScript (ES6+) |

---

## 📋 Prerequisites & Setup

### 1. Environment Configuration
Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Set your API keys in `.env`:
```ini
OPENROUTER_API_KEY=sk-or-v1-your-key-here
GEMMA_MODEL_NAME=google/gemma-4-26b-a4b-it:free
GROQ_API_KEY=gsk_your_groq_api_key_here  # Optional: for free 200ms cloud ASR
```

### 2. Install Backend Dependencies

```bash
pip install -r backend/requirements.txt
```

---

## 🔌 API Endpoint Reference

| Endpoint | Method | Description |
| :--- | :--- | :--- |
| `/` | `GET` | Root API status & welcome message |
| `/health` | `GET` | Health check endpoint returning backend status & active DB |
| `/transcribe` | `POST` | Transcribes uploaded Bangla audio file using ASR |
| `/extract` | `POST` | Extracts structured credit entry JSON using Gemma 4 |
| `/confirm` | `POST` | Saves confirmed credit ledger transaction to SQLite |
| `/entries` | `GET` | Returns all credit ledger records and open entries |
| `/daily-sales/extract` | `POST` | Extracts multi-item daily sales transaction using Gemma 4 |
| `/daily-sales/confirm` | `POST` | Saves multi-item cash sale transaction to SQLite |
| `/daily-sales/today` | `GET` | Returns today's sales transactions list and running total |
| `/daily-sales/history` | `GET` | Returns sales transactions in date range (30days/90days/all) |
| `/ledger/ask` | `POST` | Answers customer dues questions using Gemma 4 + synthesizes audio |
| `/sales/ask` | `POST` | Answers cash sales questions using Gemma 4 + synthesizes audio |
| `/business-summary` | `GET` | Generates Gemma 4 business summary narrative & context metrics |
| `/audio/{filename}` | `GET` | Serves synthesized TTS audio files |

---

## 🏃 Running the Application

### 1. Start Backend Server

```bash
python -m uvicorn backend.main:app
```

*The server will start on default port 8000 (`http://127.0.0.1:8000`).*

### 2. Launch Frontend

Open `frontend/index.html` directly in your web browser, or serve via Python:

```bash
python -m http.server 3000 --directory frontend
```

Visit: `http://localhost:3000`

---

## 🧪 Database Reset Utility

To reset all database tables to a clean state:

```bash
python reset_db.py
```
