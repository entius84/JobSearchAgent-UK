from dotenv import load_dotenv
load_dotenv()
import datetime
import json
import os
import time
from docx import Document
from playwright.sync_api import sync_playwright
from pypdf import PdfReader
import requests
from requests.auth import HTTPBasicAuth

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:14b"
APPLICATIONS_DIR = "tailored_applications"
PROCESSED_FILE = os.path.join(APPLICATIONS_DIR, "processed_jobs.json")
REED_API_KEY = os.getenv("REED_API_KEY")  # Register free at reed.co.uk/developers

SEARCH_TITLES = [
    "Service Coordinator", "Helpdesk Coordinator", "Maintenance Planner", "Work Order Administrator",
    "Compliance Administrator", "Data Coordinator", "EDMS Administrator", "Document Control Assistant",
    "Project Administrator", "NPI Coordinator", "PMO Administrator", "Operations Support Assistant",
    "Goods-in Administrator", "Stock Controller", "Purchasing Coordinator", "Order Processor"
]

ADMIN_LOCATIONS = ["High Wycombe"]


def clean_text(text):
    return "".join(c.lower() for c in text if c.isalnum() or c.isspace()).strip()


def get_job_signature(title, employer):
    return f"{clean_text(title)}_{clean_text(employer)}"


def load_processed_jobs():
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


def record_processed_job(job_data, match_score):
    os.makedirs(APPLICATIONS_DIR, exist_ok=True)
    json_path = os.path.join(APPLICATIONS_DIR, "processed_jobs.json")
    summary_path = os.path.join(APPLICATIONS_DIR, "master_summary.md")

    records = []
    if os.path.exists(json_path):
        try:
            with open(json_path, "r", encoding="utf-8") as f:
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

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(records, f, indent=4)

    header = "| Date Processed | Job Title | Company | Date Posted | Match Score | Direct Link |\n|---|---|---|---|---|---|\n"
    is_high = any(k in str(match_score) for k in ["High Match", "7/", "8/", "9/", "10/"])
    title_col = entry["title"] if is_high else f"~~{entry['title']}~~"
    score_col = entry["match_score"] if is_high else f"~~{entry['match_score']}~~"
    row = f"| {entry['date_processed']} | {title_col} | {entry['company']} | {entry['date_posted']} | {score_col} | [View Job]({entry['url']}) |\n"

    mode = "a" if os.path.exists(summary_path) else "w"
    with open(summary_path, mode, encoding="utf-8") as f:
        if mode == "w":
            f.write("# 📊 Admin & Temp Job Application Master Dashboard\n\n")
            f.write(header)
        f.write(row)


def query_ollama(prompt, context=""):
    system_instruction = (
        "CRITICAL: Evaluating operational, admin, and coordination roles for Vincenzo Vitiello "
        "(BEng Mech Eng, AMIMechE, ILM Level 5, 5 years zero-major-non-conformance NHS QMS/EDMS, LEAN capacity/backlog reduction). "
        "Do not penalize admin roles for lacking heavy FEA/CAD. Prioritize speed-to-competency, document control rigor, KPI tracking, and local commute fit."
    )
    full_prompt = f"{system_instruction}\n\nContext (My Career Vault):\n{context}\n\nQuery:\n{prompt}"
    payload = {"model": MODEL_NAME, "prompt": full_prompt, "stream": False}
    response = requests.post(OLLAMA_URL, json=payload)
    if response.status_code == 200:
        return response.json().get("response", "")
    else:
        raise Exception(f"Error: {response.status_code} - {response.text}")


def read_docx(file_path):
    try:
        doc = Document(file_path)
        return "\n".join([p.text for p in doc.paragraphs])
    except Exception as e:
        return f"[Error reading docx: {e}]"


def read_pdf(file_path):
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


def load_vault_documents(vault_paths):
    documents = {}
    if isinstance(vault_paths, str):
        vault_paths = [vault_paths]
    for vault_path in vault_paths:
        if not os.path.exists(vault_path):
            print(f"Warning: Directory not found -> {vault_path}")
            continue
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
                        print(f"Skipping {filename}: {e}")
                elif filename.endswith(".docx") and not filename.startswith("~$"):
                    documents[key] = read_docx(file_path)
                elif filename.endswith(".pdf"):
                    documents[key] = read_pdf(file_path)
    return documents


def scrape_linkedin_search(page, keyword, location="High Wycombe", max_listings=1):
    processed_data = load_processed_jobs()
    detailed_jobs = []
    seen_urls = set()
    search_url = f"https://www.linkedin.com/jobs/search/?keywords={keyword.replace(' ', '%20')}&location={location.replace(' ', '%20')}&distance=10"
    print(f"Navigating LinkedIn: {keyword} in {location} (10 mi)")
    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)
        for _ in range(3):
            try:
                page.locator(".jobs-search-results-list, .scaffold-layout__list").evaluate("node => node.scrollBy(0, 1500)")
            except Exception:
                page.mouse.wheel(0, 2000)
            time.sleep(1.5)
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
                time.sleep(2)
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
                    "title": title, "employer": employer, "signature": signature,
                    "date": f"LinkedIn ({location})", "url": full_url, "description": description,
                    "platform": "LinkedIn", "is_top_applicant": is_top_applicant,
                })
                if len(detailed_jobs) >= max_listings:
                    break
            except Exception:
                continue
    except Exception as e:
        print(f"LinkedIn error for {keyword} in {location}: {e}")
    return detailed_jobs


def fetch_reed_jobs_via_api(keyword, location="High Wycombe", max_listings=1):
    processed_data = load_processed_jobs()
    detailed_jobs = []
    seen_urls = set()
    url = "https://www.reed.co.uk/api/1.0/search"
    params = {"keywords": keyword, "locationName": location, "distanceFromLocation": 10}
    try:
        response = requests.get(url, auth=HTTPBasicAuth(REED_API_KEY, ""), params=params, timeout=30)
        if response.status_code == 200:
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
                    "title": title, "employer": employer, "signature": signature,
                    "date": date_posted, "url": job_url,
                    "description": description or "Description not provided.",
                    "platform": "Reed", "is_top_applicant": False,
                })
                if len(detailed_jobs) >= max_listings:
                    break
    except Exception as e:
        print(f"Reed API error for {keyword} in {location}: {e}")
    return detailed_jobs


if __name__ == "__main__":
    print("Loading career vault for Admin/Temp pipeline...")
    vault_dirs = [r"C:\JobSearchAgent\CV certificates and CPD"]
    docs = load_vault_documents(vault_dirs)
    vault_context = "\n\n".join([f"--- {name} ---\n {content}" for name, content in docs.items()])
    profile_dir = r"C:\JobSearchAgent\playwright_profile"
    os.makedirs(APPLICATIONS_DIR, exist_ok=True)
    all_raw_jobs = []

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(user_data_dir=profile_dir, headless=False, slow_mo=50)
        page = context.new_page()

        for title in SEARCH_TITLES:
            for loc in ADMIN_LOCATIONS:
                all_raw_jobs.extend(scrape_linkedin_search(page, keyword=title, location=loc, max_listings=1))
                all_raw_jobs.extend(fetch_reed_jobs_via_api(keyword=title, location=loc, max_listings=1))

        unique_jobs = []
        seen_sigs = set()
        for job in all_raw_jobs:
            sig = job["signature"]
            if sig not in seen_sigs:
                seen_sigs.add(sig)
                unique_jobs.append(job)

        print(f"\nUnique admin jobs to evaluate: {len(unique_jobs)}")
        for i, job in enumerate(unique_jobs):
            print(f"\nEvaluating {i+1}/{len(unique_jobs)} ({job['platform']}): {job['title']} at {job['employer']}")
            eval_prompt = (
                "Review this role against my vault. Provide a compatibility score out of 10, "
                "key strengths, speed-to-competency fit, and recommendation:\n\n"
                f"Title: {job['title']}\nDescription:\n{job['description']}"
            )
            analysis = query_ollama(eval_prompt, vault_context)
            print(analysis)

            is_top_match = False
            score_str = "N/A"
            for line in analysis.split("\n"):
                if "score" in line.lower():
                    score_str = line.strip()
                    if any(str(num) in line for num in ["7/", "8/", "9/", "10/"]):
                        is_top_match = True
                    break

            if job.get("is_top_applicant", False):
                is_top_match = True
                if not any(f"{num}/" in score_str for num in range(7, 11)):
                    score_str = "8/10 (Top Applicant Match)"

            if is_top_match:
                print("Generating tailored admin/coordinator pitch...")
                cv_prompt = (
                    "Write tailored CV highlight bullet points and a brief fast-start cover letter pitch "
                    f"emphasizing EDMS/QMS document control and LEAN scheduling speed for this role:\n\nJob Title: {job['title']}\nDescription:\n{job['description']}"
                )
                tailored_content = query_ollama(cv_prompt, vault_context)
                safe_title = "".join(c if c.isalnum() else "_" for c in job["title"]).strip("_")
                prefix = "reed" if job["platform"] == "Reed" else "linkedin"
                file_path = os.path.join(APPLICATIONS_DIR, f"{prefix}_app_{i+1}_{safe_title}.md")
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(f"# Role ({job['platform']}): {job['title']} at {job['employer']}\n")
                    f.write(f"- **URL:** {job['url']}\n- **Date Posted:** {job['date']}\n\n## Evaluation & Fit\n{analysis}\n\n## Tailored Pitch\n{tailored_content}\n")
                print(f"Saved package to {file_path}")

            match_label = "🔥 High Match" if is_top_match else f"Low / Skipped ({score_str})"
            record_processed_job(
                job_data={"title": job["title"], "company": job["employer"], "date_posted": job["date"], "url": job["url"]},
                match_score=match_label
            )
            print("-" * 50)

        context.close()
    print("Admin/Temp pipeline execution complete!")