"""
Administrative & Temp Job Search Pipeline (pipeline_temp_admin.py)
------------------------------------------------------------------
Automates the discovery, filtering, and local LLM evaluation of local 
administrative, coordination, support, and temporary roles strictly within 
a hyper-local 10-mile radius of High Wycombe.

Author: Vincenzo Vitiello
"""

from dotenv import load_dotenv
load_dotenv()
import datetime
import json
import logging
import os
import random
import time
from typing import List, Dict, Any, Optional
from docx import Document
from playwright.sync_api import sync_playwright
from pypdf import PdfReader
import requests
from requests.auth import HTTPBasicAuth

# --- CONFIGURATION & PATHS ---
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:14b"
APPLICATIONS_DIR = "tailored_applications"  # Unified centralized vault folder
PROCESSED_FILE = os.path.join(APPLICATIONS_DIR, "processed_jobs.json")
MASTER_SUMMARY_PATH = os.path.join(APPLICATIONS_DIR, "master_summary.md")
REED_API_KEY = os.getenv("REED_API_KEY")

SEARCH_RADIUS_MILES: int = 10  # Strictly restricted to 10 miles (High Wycombe core)
TARGET_LOCATION: str = "High Wycombe"

SEARCH_TITLES = [
    "Administrator",
    "Admin Assistant",
    "Office Coordinator",
    "Project Coordinator",
    "Helpdesk Support",
    "Operations Administrator",
    "Data Entry Clerk",
    "Temporary Administrator",
    "Secretary",
    "Customer Support Coordinator",
]

# Configure logging for pipeline execution traceability
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s"
)
logger = logging.getLogger(__name__)

# --- TEXT & DEDUP UTILITIES ---
def clean_text(text: str) -> str:
    """Normalizes text by removing non-alphanumeric characters for signature matching."""
    return "".join(c.lower() for c in text if c.isalnum() or c.isspace()).strip()

def get_job_signature(title: str, employer: str) -> str:
    """Generates a unique signature hash for job deduplication."""
    return f"{clean_text(title)}_{clean_text(employer)}"

def load_processed_jobs() -> dict:
    """Loads processed jobs, converting list formats to a signature lookup map."""
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    sig_map = {}
                    for item in data:
                        if isinstance(item, dict) and "title" in item and "company" in item:
                            sig = get_job_signature(item["title"], item["company"])
                            sig_map[sig] = {
                                "score": item.get("match_score", "N/A"),
                                "title": item.get("title"),
                                "employer": item.get("company"),
                                "urls": [item.get("url")] if item.get("url") else [],
                            }
                    return sig_map
                return data
        except Exception:
            return {}
    return {}

def record_processed_job(job_data: dict, match_score: str) -> None:
    """Appends job metadata to the centralized processed_jobs.json and shared master_summary.md dashboard."""
    os.makedirs(APPLICATIONS_DIR, exist_ok=True)

    records = []
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, list):
                    records = loaded
        except Exception:
            records = []

    entry = {
        "title": job_data.get("title"),
        "company": job_data.get("company"),
        "date_posted": job_data.get("date_posted", "Unknown"),
        "date_processed": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "match_score": match_score,
        "url": job_data.get("url"),
    }
    records.append(entry)

    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4)

    header = "| Date Processed | Job Title | Company | Date Posted | Match Score | Direct Link |\n|---|---|---|---|---|---|\n"
    is_high = any(k in str(match_score) for k in ["High Match", "7/", "8/", "9/", "10/"])
    title_col = entry["title"] if is_high else f"~~{entry['title']}~~"
    score_col = entry["match_score"] if is_high else f"~~{entry['match_score']}~~"
    row = f"| {entry['date_processed']} | {title_col} | {entry['company']} | {entry['date_posted']} | {score_col} | [View Job]({entry['url']}) |\n"

    mode = "a" if os.path.exists(MASTER_SUMMARY_PATH) else "w"
    with open(MASTER_SUMMARY_PATH, mode, encoding="utf-8") as f:
        if mode == "w":
            f.write("# 📊 Unified Master Job Search Dashboard (Engineering & Admin)\n\n")
            f.write(header)
        f.write(row)

# --- PLATFORM ACTIONS (BOOKMARK/FAVORITE) ---
def save_job_on_linkedin(page) -> None:
    """Programmatically clicks the native LinkedIn Save button for high matches."""
    try:
        save_btn = page.locator("button.jobs-save-button, button[aria-label*='Save']").first
        if save_btn.count() > 0 and save_btn.is_visible():
            save_btn.click(force=True)
            time.sleep(1)
            logger.info("⭐ Saved job to LinkedIn Favourites/Bookmark.")
    except Exception as e:
        logger.warning(f"Notice: Could not trigger LinkedIn save UI: {e}")

# --- AI & VAULT LOADERS ---
def query_ollama(prompt: str, context: str = "") -> str:
    """Evaluates job details against Career Vault using local Ollama instance (qwen2.5:14b)."""
    system_instruction = (
        "CRITICAL: You are evaluating administrative, coordination, and temporary roles "
        "for Vincenzo Vitiello, focusing on operational organization, document control rigor, "
        "and local High Wycombe commute fit. Never use placeholder brackets like [Your Name]; "
        "always use Vincenzo's actual background from the Career Vault context."
    )
    full_prompt = f"{system_instruction}\n\nContext (My Career Vault):\n{context}\n\nQuery:\n{prompt}"
    payload = {"model": MODEL_NAME, "prompt": full_prompt, "stream": False}
    response = requests.post(OLLAMA_URL, json=payload)
    if response.status_code == 200:
        return response.json().get("response", "")
    else:
        raise Exception(f"Error: {response.status_code} - {response.text}")

def read_docx(file_path: str) -> str:
    """Extracts text content from Word document files (.docx)."""
    try:
        doc = Document(file_path)
        return "\n".join([p.text for p in doc.paragraphs])
    except Exception as e:
        return f"[Error reading docx: {e}]"

def read_pdf(file_path: str) -> str:
    """Extracts text content from PDF files."""
    try:
        reader = PdfReader(file_path)
        text = ""
        for page in reader.pages:
            extracted = page.extract_text()
            if extracted:
                text += extracted + "\n"
        return text
    except Exception as e:
        return f"[Error reading pdf: {e}]"

def load_vault_documents(vault_paths) -> dict:
    """Recursively scans career vault directories for reference files."""
    documents = {}
    if isinstance(vault_paths, str):
        vault_paths = [vault_paths]

    for vault_path in vault_paths:
        if not os.path.exists(vault_path):
            logger.warning(f"Warning: Directory not found -> {vault_path}")
            continue
        logger.info(f"Scanning directory and subfolders: {vault_path}")
        for root, dirs, files in os.walk(vault_path):
            for filename in files:
                file_path = os.path.join(root, filename)
                rel_path = os.path.relpath(file_path, vault_path)
                key = f"{os.path.basename(vault_path)}/{rel_path}"

                if filename.endswith((".txt", ".md")):
                    try:
                        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                            documents[key] = f.read()
                    except Exception as e:
                        logger.warning(f"Skipping {filename}: {e}")
                elif filename.endswith(".docx") and not filename.startswith("~$"):
                    documents[key] = read_docx(file_path)
                elif filename.endswith(".pdf"):
                    documents[key] = read_pdf(file_path)
    return documents

# --- SCRAPERS ---
def scrape_linkedin_search(page, keyword: str, location: str = "High Wycombe", max_listings: int = 2) -> List[Dict[str, Any]]:
    """
    Scrapes LinkedIn admin/temp job listings within a strict 10-mile radius using 
    a bounded scroll loop with randomized anti-bot delays and automatic end-of-list detection.
    """
    processed_data = load_processed_jobs()
    detailed_jobs: List[Dict[str, Any]] = []
    seen_urls = set()

    # Strict 10-mile distance parameter enforcement (&distance=10)
    search_url = (
        f"https://www.linkedin.com/jobs/search/?"
        f"keywords={keyword.replace(' ', '%20')}"
        f"&location={location.replace(' ', '%20')}%2C%20England%2C%20United%20Kingdom"
        f"&distance={SEARCH_RADIUS_MILES}"
    )
    logger.info(f"Navigating to LinkedIn search: {search_url}")
    page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
    time.sleep(3)

    # Bounded scroll loop (up to 8 iterations with safety check)
    previous_count = 0
    max_scrolls = 8
    for i in range(max_scrolls):
        try:
            page.locator(".jobs-search-results-list, .scaffold-layout__list").evaluate("node => node.scrollTop = node.scrollHeight")
        except Exception:
            page.mouse.wheel(0, 2000)
        
        time.sleep(random.uniform(2.0, 3.5))
        
        current_jobs = page.locator("a[href*='/jobs/view/']").count()
        if current_jobs == previous_count:
            logger.info(f"Reached end of LinkedIn results list at scroll iteration {i + 1}.")
            break
        previous_count = current_jobs

    cards = page.locator(".job-card-container, li.occludable-update").all()
    for i, card in enumerate(cards):
        try:
            link_elem = card.locator("a[href*='/jobs/view/']").first
            if link_elem.count() == 0:
                continue
            href = link_elem.get_attribute("href")
            clean_url = href.split("?")[0] if href else ""
            if not clean_url:
                continue

            card.scroll_into_view_if_needed()
            card.click()
            time.sleep(2.5)

            title_elem = card.locator(".job-card-list__title, .job-card-container__link").first
            title = title_elem.inner_text().strip() if title_elem.count() > 0 else "Unknown Title"
            if "\n" in title:
                title = title.split("\n")[0].strip()

            comp_elem = card.locator(".job-card-container__company-name, .job-search-card__subtitle").first
            employer = comp_elem.inner_text().strip() if comp_elem.count() > 0 else "Unknown Employer"

            signature = get_job_signature(title, employer)
            full_url = clean_url if clean_url.startswith("http") else f"https://www.linkedin.com{clean_url}"

            if signature in processed_data or full_url in seen_urls:
                continue

            seen_urls.add(full_url)

            top_applicant_elem = page.locator("text=You'd be a top applicant")
            is_top_applicant = top_applicant_elem.count() > 0 and top_applicant_elem.is_visible()

            desc_elem = page.locator(".jobs-description__content, .jobs-box__html-content").first
            description = desc_elem.inner_text().strip() if desc_elem.count() > 0 else "Description not loaded."

            detailed_jobs.append({
                "title": title,
                "employer": employer,
                "signature": signature,
                "date": f"LinkedIn Search: {keyword}",
                "url": full_url,
                "description": description,
                "platform": "LinkedIn",
                "is_top_applicant": is_top_applicant,
            })

            if len(detailed_jobs) >= max_listings:
                break
        except Exception as e:
            logger.warning(f"Error scraping LinkedIn search card {i+1}: {e}")

    return detailed_jobs


def fetch_reed_jobs_via_api(keyword: str, location: str = "High Wycombe", max_listings: int = 2) -> List[Dict[str, Any]]:
    """Queries Reed API for local administrative roles within the strict 10-mile radius."""
    processed_data = load_processed_jobs()
    detailed_jobs: List[Dict[str, Any]] = []
    seen_urls = set()
    url = "https://www.reed.co.uk/api/1.0/search"

    params = {
        "keywords": keyword,
        "locationName": location,
        "distanceFromLocation": SEARCH_RADIUS_MILES,  # Strictly 10 miles
    }

    logger.info(f"Fetching Reed API for '{keyword}' in {location} ({SEARCH_RADIUS_MILES} mi)...")
    try:
        response = requests.get(url, auth=HTTPBasicAuth(REED_API_KEY, ""), params=params, timeout=30)
        if response.status_code != 200:
            logger.error(f"Reed API Error: {response.status_code} - {response.text}")
            return []

        data = response.json()
        for item in data.get("results", []):
            title = item.get("jobTitle")
            employer = item.get("employerName")
            job_url = item.get("jobUrl")
            description = item.get("jobDescription")
            date_posted = item.get("date", "Unknown")

            if not title or not employer or not job_url:
                continue

            signature = get_job_signature(title, employer)
            if signature in processed_data or job_url in seen_urls:
                continue

            seen_urls.add(job_url)

            detailed_jobs.append({
                "title": title,
                "employer": employer,
                "signature": signature,
                "date": date_posted,
                "url": job_url,
                "description": description or "Description not provided.",
                "platform": "Reed",
                "is_top_applicant": False,
            })

            if len(detailed_jobs) >= max_listings:
                break
    except Exception as e:
        logger.error(f"Error connecting to Reed API: {e}")

    return detailed_jobs


def run_admin_pipeline() -> None:
    """
    Executes the end-to-end administrative pipeline workflow:
    1. Scrapes LinkedIn and Reed API with strict 10-mile filters.
    2. Deduplicates against the unified `tailored_applications/processed_jobs.json`.
    3. Evaluates roles via local Ollama and packages tailored outputs into `tailored_applications/`.
    """
    logger.info("Starting Admin & Temp Pipeline execution...")
    
    vault_dirs = [r"C:\JobSearchAgent\CV certificates and CPD"]
    docs = load_vault_documents(vault_dirs)
    logger.info(f"Successfully loaded {len(docs)} documents from your career vault.")
    vault_context = "\n\n".join([f"--- {name} ---\n {content}" for name, content in docs.items()])

    profile_dir = r"C:\JobSearchAgent\playwright_profile"
    os.makedirs(APPLICATIONS_DIR, exist_ok=True)
    all_raw_jobs = []

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(user_data_dir=profile_dir, headless=False, slow_mo=50)
        page = context.new_page()

        for title in SEARCH_TITLES:
            logger.info(f"\n--- Searching LinkedIn for: {title} in High Wycombe (10mi) ---")
            all_raw_jobs.extend(scrape_linkedin_search(page, keyword=title, location=TARGET_LOCATION, max_listings=2))

            logger.info(f"\n--- Fetching Reed API for: {title} in High Wycombe (10mi) ---")
            all_raw_jobs.extend(fetch_reed_jobs_via_api(keyword=title, location=TARGET_LOCATION, max_listings=2))

        unique_jobs = []
        seen_sigs = set()
        for job in all_raw_jobs:
            if job["signature"] not in seen_sigs:
                seen_sigs.add(job["signature"])
                unique_jobs.append(job)

        logger.info(f"\nTotal unique new admin jobs to evaluate: {len(unique_jobs)}")

        for i, job in enumerate(unique_jobs):
            logger.info(f"\nEvaluating Job {i+1}/{len(unique_jobs)} ({job['platform']}): {job['title']} at {job['employer']}\nURL: {job['url']}")

            eval_prompt = (
                "Review this administrative/coordination job description against my career vault. "
                "Provide a compatibility score out of 10, key strengths, potential gaps, and a recommendation on whether to apply:\n\n"
                f"Title: {job['title']}\nDescription:\n{job['description']}"
            )
            analysis = query_ollama(eval_prompt, vault_context)
            print(analysis)

            is_top_match = False
            score_str = "N/A"
            for line in analysis.split("\n"):
                if "score" in line.lower():
                    score_str = line.strip()
                    if any(str(num) in line for num in ["8/", "9/", "10/"]):
                        is_top_match = True
                        break

            if job.get("is_top_applicant", False):
                logger.info("🌟 LinkedIn Premium Badge Detected: 'You'd be a top applicant'!")
                is_top_match = True
                if not any(f"{num}/" in score_str for num in range(8, 11)):
                    score_str = "9/10 (LinkedIn Top Applicant Match)"

            if is_top_match:
                if job["platform"] == "LinkedIn":
                    save_job_on_linkedin(page)

                logger.info("Generating tailored CV positioning & cover letter draft...")
                cv_prompt = (
                    "Based on my career vault, write tailored CV highlight bullet points and a brief cover letter pitch "
                    f"customized specifically for this admin/coordination role:\n\nJob Title: {job['title']}\nDescription:\n{job['description']}"
                )
                tailored_content = query_ollama(cv_prompt, vault_context)

                safe_title = "".join(c if c.isalnum() else "_" for c in job["title"]).strip("_")
                prefix = "reed_admin" if job["platform"] == "Reed" else "linkedin_admin"
                file_path = os.path.join(APPLICATIONS_DIR, f"{prefix}_app_{i+1}_{safe_title}.md")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f"# Admin Role ({job['platform']}): {job['title']} at {job['employer']}\n")
                    f.write(f"- **URL:** {job['url']}\n")
                    f.write(f"- **Date Posted:** {job['date']}\n")
                    if job.get("is_top_applicant"):
                        f.write("- **Status:** 🌟 Flagged by LinkedIn as 'You'd be a top applicant'\n\n")
                    else:
                        f.write("\n")
                    f.write(f"## Evaluation & Fit\n{analysis}\n\n")
                    f.write(f"## Tailored CV & Cover Letter Package\n{tailored_content}\n")
                logger.info(f"Saved tailored application package to {file_path}")

            print("-" * 60)
            match_label = "🔥 High Match" if is_top_match else f"Low / Skipped ({score_str})"
            record_processed_job(
                job_data={
                    "title": job["title"],
                    "company": job["employer"],
                    "date_posted": job["date"],
                    "url": job["url"],
                },
                match_score=match_label,
            )

        context.close()
    logger.info("Admin & Temp Pipeline execution completed successfully.")


if __name__ == "__main__":
    run_admin_pipeline()