import json
import os
import time
from docx import Document
import openpyxl
from playwright.sync_api import sync_playwright
import requests
import re

# -----------------------------
# CONFIG
# -----------------------------
OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:14b"
VAULT_DIR = r"C:\JobSearchAgent\CV certificates and CPD"
PROCESSED_FILE = "processed_jobs.json"
APPLICATIONS_DIR = "tailored_applications"

# -----------------------------
# UTILS
# -----------------------------

def load_processed_jobs():
    if os.path.exists(PROCESSED_FILE):
        try:
            with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
                return set(json.load(f))
        except:
            return set()
    return set()

def save_processed_job(url):
    processed = load_processed_jobs()
    processed.add(url)
    with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
        json.dump(list(processed), f, indent=2)

def read_docx(file_path):
    try:
        doc = Document(file_path)
        return "\n".join([p.text for p in doc.paragraphs])
    except Exception as e:
        return f"[Error reading docx: {e}]"

def read_xlsx(file_path):
    try:
        wb = openpyxl.load_workbook(file_path, data_only=True)
        text_data = []
        for sheet in wb.sheetnames:
            ws = wb[sheet]
            for row in ws.iter_rows(values_only=True):
                if any(row):
                    text_data.append(" | ".join([str(c) if c else "" for c in row]))
        return "\n".join(text_data)
    except Exception as e:
        return f"[Error reading xlsx: {e}]"

def load_vault_documents(vault_path):
    documents = {}
    for root, dirs, files in os.walk(vault_path):
        for filename in files:
            file_path = os.path.join(root, filename)
            rel_path = os.path.relpath(file_path, vault_path)

            if filename.endswith(".docx"):
                documents[rel_path] = read_docx(file_path)
            elif filename.endswith(".xlsx"):
                documents[rel_path] = read_xlsx(file_path)
            elif filename.endswith((".txt", ".md")):
                with open(file_path, "r", encoding="utf-8") as f:
                    documents[rel_path] = f.read()

    return documents

# -----------------------------
# RETRIEVAL — reduce hallucinations
# -----------------------------

def retrieve_relevant_vault_chunks(vault_docs, job_description):
    job_words = set(job_description.lower().split())
    chunks = []

    for name, content in vault_docs.items():
        content_lower = content.lower()
        if any(word in content_lower for word in job_words):
            chunks.append(content[:2000])  # limit chunk size

    if not chunks:
        return "No directly relevant vault content found."

    return "\n\n".join(chunks[:5])  # top 5 chunks only

# -----------------------------
# MODEL CALL — deterministic
# -----------------------------

def query_ollama(prompt):
    payload = {
        "model": MODEL_NAME,
        "prompt": prompt,
        "stream": False,
        "temperature": 0,
        "top_p": 0.1,
        "repeat_penalty": 1.2
    }

    response = requests.post(OLLAMA_URL, json=payload)
    if response.status_code == 200:
        return response.json().get("response", "")
    else:
        raise Exception(f"Error: {response.status_code} - {response.text}")

# -----------------------------
# JSON PARSER — safe
# -----------------------------

def safe_json_parse(response):
    try:
        return json.loads(response)
    except:
        match = re.search(r"\{.*\}", response, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except:
                pass
        return {
            "compatibility_score": 0,
            "strengths": [],
            "gaps": ["invalid output"],
            "apply_recommendation": "no"
        }

# -----------------------------
# CLEAN JOB DESCRIPTION
# -----------------------------

def clean_description(text):
    return "\n".join([line.strip() for line in text.split("\n") if len(line.strip()) > 5])

# -----------------------------
# LINKEDIN SCRAPER
# -----------------------------

def save_job_on_linkedin(page):
    try:
        save_btn = page.locator("button.jobs-save-button, button:has-text('Save')").first
        if save_btn.count() > 0:
            aria_label = save_btn.get_attribute("aria-label") or ""
            if "saved" not in aria_label.lower():
                save_btn.click()
                time.sleep(1)
    except:
        pass

def scrape_top_applicant_jobs(max_pages=2):
    profile_dir = r"C:\JobSearchAgent\playwright_profile"
    processed_urls = load_processed_jobs()
    detailed_jobs = []
    seen_urls = set()

    p = sync_playwright().start()
    context = p.chromium.launch_persistent_context(
        user_data_dir=profile_dir, headless=False, slow_mo=50
    )
    page = context.new_page()

    for page_num in range(max_pages):
        base_url = "https://www.linkedin.com/jobs/collections/recommended/?recommendationChannel=TOP_APPLICANT"
        current_url = f"{base_url}&start={page_num * 25}" if page_num > 0 else base_url

        page.goto(current_url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        for _ in range(8):
            try:
                page.locator(".jobs-search-results-list, .scaffold-layout__list").evaluate("node => node.scrollBy(0, 1500)")
            except:
                page.mouse.wheel(0, 2000)
            time.sleep(2)

        cards = page.locator(".job-card-container, li.occludable-update").all()

        for card in cards:
            try:
                link_elem = card.locator("a[href*='/jobs/view/']").first
                if link_elem.count() == 0:
                    continue

                href = link_elem.get_attribute("href")
                clean_url = href.split("?")[0] if href else ""
                full_url = clean_url if clean_url.startswith("http") else f"https://www.linkedin.com{clean_url}"

                if full_url in processed_urls or full_url in seen_urls:
                    continue

                seen_urls.add(full_url)
                card.click()
                time.sleep(2.5)

                title_elem = card.locator(".job-card-list__title, .job-card-container__link").first
                title = title_elem.inner_text().strip() if title_elem.count() > 0 else "Unknown Title"
                title = title.split("\n")[0].strip()

                date_posted = "N/A"
                time_elem = card.locator("time, .job-card-container__listed-time").first
                if time_elem.count() > 0:
                    date_posted = time_elem.inner_text().strip()

                desc_elem = page.locator(".jobs-description__content, .jobs-box__html-content").first
                description = desc_elem.inner_text().strip() if desc_elem.count() > 0 else "Description not loaded."

                detailed_jobs.append({
                    "title": title,
                    "date": date_posted,
                    "url": full_url,
                    "description": clean_description(description),
                    "card": card,
                })

                if len(detailed_jobs) >= 10:
                    break

            except Exception:
                continue

        if len(detailed_jobs) >= 10:
            break

    return detailed_jobs, page, context, p

# -----------------------------
# MAIN PIPELINE
# -----------------------------

if __name__ == "__main__":
    print("Loading vault...")
    vault_docs = load_vault_documents(VAULT_DIR)

    print("Scraping LinkedIn...")
    new_jobs, page, context, p_instance = scrape_top_applicant_jobs()

    os.makedirs(APPLICATIONS_DIR, exist_ok=True)
    summary_records = []

    for i, job in enumerate(new_jobs):
        relevant_vault = retrieve_relevant_vault_chunks(vault_docs, job["description"])

        eval_prompt = f"""
You are a deterministic job evaluation engine.
You MUST respond ONLY in valid JSON. No prose.

Schema:
{{
  "compatibility_score": int,
  "strengths": [str],
  "gaps": [str],
  "apply_recommendation": "yes" | "no"
}}

Rules:
- Base your evaluation ONLY on the job description and vault chunks.
- If information is missing, respond "unknown".
- NEVER invent experience, skills, or certifications not explicitly present.
- NEVER infer or guess.
- Be strict and literal.

Job Title: {job['title']}
Job Description: {job['description']}

Relevant Vault Chunks:
{relevant_vault}

Return ONLY JSON.
"""

        analysis_raw = query_ollama(eval_prompt)
        analysis = safe_json_parse(analysis_raw)

        score = analysis.get("compatibility_score", 0)
        high_match = score >= 8

        summary_records.append({
            "title": job["title"],
            "score": score,
            "match": "🔥 High Match" if high_match else "Skipped / Low",
            "url": job["url"],
        })

        if high_match:
            job["card"].click()
            time.sleep(1.5)
            save_job_on_linkedin(page)

            cv_prompt = f"""
You MUST respond ONLY in JSON.

Schema:
{{
  "cv_bullets": [str],
  "cover_letter": str
}}

Rules:
- Use ONLY information explicitly present in the vault chunks.
- No invention.
- No assumptions.
- No hallucinations.

Job Title: {job['title']}
Job Description: {job['description']}

Relevant Vault Chunks:
{relevant_vault}

Return ONLY JSON.
"""

            tailored_raw = query_ollama(cv_prompt)
            tailored = safe_json_parse(tailored_raw)

            safe_title = "".join(c if c.isalnum() else "_" for c in job["title"]).strip("_")
            file_path = os.path.join(APPLICATIONS_DIR, f"application_{i+1}_{safe_title}.md")

            with open(file_path, "w", encoding="utf-8") as f:
                f.write(f"# Role: {job['title']}\n")
                f.write(f"- **URL:** {job['url']}\n")
                f.write(f"- **Date Posted:** {job['date']}\n\n")
                f.write("## Evaluation JSON\n")
                f.write(json.dumps(analysis, indent=2))
                f.write("\n\n## Tailored Package\n")
                f.write(json.dumps(tailored, indent=2))

        save_processed_job(job["url"])

    summary_path = os.path.join(APPLICATIONS_DIR, "master_summary.md")
    with open(summary_path, "w", encoding="utf-8") as f:
        f.write("# 📊 Job Application Master Dashboard\n\n")
        f.write("| Job Title | Score | Status | Link |\n")
        f.write("| :--- | :--- | :--- | :--- |\n")
        for rec in summary_records:
            f.write(f"| {rec['title']} | {rec['score']} | {rec['match']} | [View Job]({rec['url']}) |\n")

    context.close()
    p_instance.stop()

    print("Done.")
