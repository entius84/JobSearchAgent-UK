# 🇬🇧 JobSearchAgent-UK

An automated, local-LLM-driven job search, evaluation, and application packaging pipeline built for the UK market. Designed with a strict privacy-first approach, it runs entirely offline using a local Ollama instance while scraping and evaluating engineering and operational roles around High Wycombe and surrounding corridors.

---

## 🚀 Project Architecture & Workflow

The system is split into a modular two-phase pipeline to separate web discovery from local AI processing:

1. **Phase 1: Lightweight Discovery & Ingestion (`pipeline_scraper_No_Local_AI.py`)**
   * **Focus:** Pure web scraping and API ingestion with **zero LLM overhead**. 
   * **Hardware Requirement:** **CPU-friendly**—anyone can run this without a dedicated graphics card or local AI models.
   * **Output:** Saves raw listings into `tailored_applications/scraped_jobs_raw.json`.

2. **Phase 2: Evaluation & Packaging (`pipeline.py` & `pipeline_admin.py`)**
   * **Focus:** Local LLM intelligence using Ollama (`qwen2.5:14b`) to score compatibility against your Career Vault.
   * **Hardware Requirement:** Requires local GPU compute and an active Ollama instance.

---

## 🛠️ Tech Stack & Core Tools

* **Automation & Scraping:** Playwright (Python) with persistent browser contexts for seamless session management.
* **Local Intelligence (LLM):** Ollama running `qwen2.5:14b` for zero-cloud, completely private job evaluation and document tailoring.
* **Job Data Providers:** 
  * Direct DOM scraping of **LinkedIn** using a resilient, link-first targeting strategy (`a[href*='/jobs/view/']`) immune to dynamic class hashing.
  * Official **Reed API** integration for robust, structured listing ingestion.
* **State & Deduplication Management:** Centralized JSON signature-tracking (`tailored_applications/processed_jobs.json`).

---

## Project Structure


JobSearchAgent-UK/
│
├── pipeline_scraper_No_Local_AI.py      # Phase 1: Zero-LLM multi-source discovery & ingestion scraper
├── pipeline.py                # Phase 2: Engineering & technical management pipeline (35 mi)
├── pipeline_admin.py          # Phase 2: Local admin & temporary roles pipeline (10 mi)
├── requirements.txt           # Python dependencies
├── .env.example               # Template for environment variables
├── .env                       # Environment variables (API keys - git-ignored)
├── .gitignore                 # Security rules protecting session cookies and personal data
│
├── CV certificates and CPD/   # Local Career Vault (CVs, certifications, training logs)
│
└── tailored_applications/     # Centralized output directory
    ├── scraped_jobs_raw.json  # Raw ingested job database from Phase 1
    ├── processed_jobs.json    # Master deduplication registry
    ├── master_summary.md      # Real-time executive markdown dashboard
    └── *_app_*.md             # Individual tailored cover letters and CV highlightsghts


## 🚀 Getting Started & Setup

### 1. Clone the Repository
```bash
git clone [https://github.com/entius84/JobSearchAgent-UK.git](https://github.com/entius84/JobSearchAgent-UK.git)
cd JobSearchAgent-UK

2. Install Dependencies
Bash
pip install -r requirements.txt
python -m playwright install chromium

3. Configure Environment Variables
Create a .env file in the root directory to securely manage your API keys:

Snippet di codice
REED_API_KEY=your_reed_api_key_here

4. Ensure Local LLM is Running
Make sure Ollama is active and the required model is loaded locally:

Bash
ollama run qwen2.5:14b
5. Run the Pipelines
To run the Engineering Pipeline:

Bash
python pipeline.py
To run the Admin & Temp Pipeline:

Bash
python pipeline_admin.py
🔒 Security & Privacy Best Practices
This repository is configured to ensure sensitive personal data and active web sessions never leak to version control:

Playwright Profiles (playwright_profile/): Ignored via .gitignore to keep active browser cookies and authentication sessions local.

Career Vault (CV certificates and CPD/): Ignored to protect personal CVs, certificates, and professional history files.

Generated Outputs (tailored_applications/): Ignored to keep tailored cover letters and master application trackers private.

API Keys (.env): Kept out of source code entirely using python-dotenv.