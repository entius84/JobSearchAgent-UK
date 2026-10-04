# 🇬🇧 JobSearchAgent-UK

An automated, local-LLM-driven job search, evaluation, and application packaging pipeline built for the UK market. Designed with a strict privacy-first approach, it runs entirely offline using a local Ollama instance while scraping and evaluating engineering and operational roles around High Wycombe and surrounding corridors.

---

##  Project Architecture & Dual Tracks

The system operates across two specialized pipelines that share a centralized data sink to prevent cross-pipeline duplication:

1. **Engineering & Technical Leadership (`pipeline.py`)**
   * **Focus:** Mechanical Engineering, Quality Assurance, Validation, Compliance, Decontamination, Medical Devices, and Technical Operations.
   * **Search Radius:** 35-mile radius (covering Oxford, Slough, Reading, and West/Central London corridors).
   * **Evaluation Angle:** Evaluates deep technical engineering credentials (BEng Hons, AMIMechE status, QMS compliance, and NHS operational track record).

2. **Administrative, Operations & Temp Support (`pipeline_admin.py`)**
   * **Focus:** Service Coordination, Helpdesk Management, Maintenance Planning, EDMS Administration, and Project/PMO Administration.
   * **Search Radius:** 10-mile hyper-local radius (strictly focused around High Wycombe).
   * **Evaluation Angle:** Prioritizes speed-to-competency, document control rigor, KPI tracking, and local commute fit without penalizing roles for lacking heavy CAD/FEA.

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
├── pipeline.py                # Engineering & technical management pipeline (35 mi)
├── pipeline_admin.py          # Local admin & temporary roles pipeline (10 mi)
├── requirements.txt           # Python dependencies
├── .env                       # Environment variables (API keys - git-ignored)
├── .gitignore                 # Security rules protecting session cookies and personal data
│
├── CV certificates and CPD/   # Local Career Vault (CVs, certifications, training logs)
│
└── tailored_applications/     # Centralized output directory
    ├── processed_jobs.json    # Master deduplication registry
    ├── master_summary.md      # Real-time executive markdown dashboard
    └── *_app_*.md             # Individual tailored cover letters and CV highlights

    🚀 Getting Started & Setup
1. Clone the Repository
Bash
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