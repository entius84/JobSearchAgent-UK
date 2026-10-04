import json
import os
import time
from docx import Document
import openpyxl
from playwright.sync_api import sync_playwright
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:14b"
PROCESSED_FILE = "processed_jobs.json"
APPLICATIONS_DIR = "tailored_applications"


def clean_text(text):
  return "".join(c.lower() for c in text if c.isalnum() or c.isspace()).strip()


def get_job_signature(title, employer):
  return f"{clean_text(title)}_{clean_text(employer)}"


def load_processed_jobs():
  if os.path.exists(PROCESSED_FILE):
    try:
      with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, list):  # Backwards compatibility
          return {
              f"legacy_{i}": {
                  "score": "N/A",
                  "title": "Legacy",
                  "employer": "Unknown",
                  "urls": [url],
              }
              for i, url in enumerate(data)
          }
        return data
    except Exception:
      return {}
  return {}


def save_processed_job(signature, title, employer, url, score):
  processed = load_processed_jobs()
  if signature in processed:
    processed[signature]["score"] = score
    if url not in processed[signature]["urls"]:
      processed[signature]["urls"].append(url)
  else:
    processed[signature] = {
        "score": score,
        "title": title,
        "employer": employer,
        "urls": [url],
    }
  with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
    json.dump(processed, f, indent=2)


def query_ollama(prompt, context=""):
  full_prompt = f"Context (My Career Vault):\n{context}\n\nQuery:\n{prompt}"
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


def load_vault_documents(vault_path):
  documents = {}
  if not os.path.exists(vault_path):
    return documents
  for root, dirs, files in os.walk(vault_path):
    for filename in files:
      file_path = os.path.join(root, filename)
      rel_path = os.path.relpath(file_path, vault_path)
      if filename.endswith((".txt", ".md")):
        with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
          documents[rel_path] = f.read()
      elif filename.endswith(".docx") and not filename.startswith("~$"):
        documents[rel_path] = read_docx(file_path)
  return documents


def scrape_reed_jobs(keyword="Mechanical Engineer", location="High Wycombe", max_listings=5):
  profile_dir = r"C:\JobSearchAgent\playwright_profile"
  processed_data = load_processed_jobs()
  detailed_jobs = []

  kw_slug = keyword.lower().replace(" ", "-")
  loc_slug = location.lower().replace(" ", "-")
  search_url = f"https://www.reed.co.uk/jobs/{kw_slug}-jobs-in-{loc_slug}"

  p = sync_playwright().start()
  context = p.chromium.launch_persistent_context(
      user_data_dir=profile_dir, headless=False, slow_mo=50
  )
  page = context.new_page()

  print(f"Navigating to Reed search: {search_url}")
  page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
  time.sleep(3)

  # Only trigger if actively redirected to an auth URL
  if "signin" in page.url or "login" in page.url or "authentication" in page.url:
    print("Reed sign-in redirect detected.")
    input("Please log in on Reed in the browser window, then press Enter here in the terminal to continue...")
    page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
    time.sleep(3)

  cards = page.locator("article.job-result, div.job-result-card, div.card-body").all()
  print(f"Found {len(cards)} listings on Reed. Filtering against history...")

  for i, card in enumerate(cards):
    try:
      link_elem = card.locator("a.job-result-card__title-link, h2.title a, h3 a").first
      if link_elem.count() == 0:
        continue
      href = link_elem.get_attribute("href")
      full_url = f"https://www.reed.co.uk{href}" if href.startswith("/") else href

      title = link_elem.inner_text().strip()
      
      comp_elem = card.locator("a.job-result-card__subtitle-link, div.posted-by, li.posted-by").first
      employer = comp_elem.inner_text().strip() if comp_elem.count() > 0 else "Unknown Employer"

      signature = get_job_signature(title, employer)

      if signature in processed_data:
        print(f"Skipping duplicate Reed role: {title} at {employer}")
        continue

      link_elem.click()
      time.sleep(2.5)

      desc_elem = page.locator("div.description, div.job-description, section.job-details").first
      description = desc_elem.inner_text().strip() if desc_elem.count() > 0 else "Description not loaded."

      detailed_jobs.append({
          "title": title,
          "employer": employer,
          "signature": signature,
          "date": "Reed Listing",
          "url": full_url,
          "description": description,
      })

      page.go_back(wait_until="domcontentloaded")
      time.sleep(2)

      if len(detailed_jobs) >= max_listings:
        break
    except Exception as e:
      print(f"Error scraping Reed card {i+1}: {e}")

  try:
    context.close()
    p.stop()
  except Exception:
    pass

  return detailed_jobs


if __name__ == "__main__":
  print("Loading your career vault...")
  vault_dir = r"G:\Il mio Drive\lavoro"
  docs = load_vault_documents(vault_dir)
  vault_context = "\n\n".join(
      [f"--- {name} ---\n {content}" for name, content in docs.items()]
  )

  print("Fetching new Reed listings...")
  new_jobs = scrape_reed_jobs(keyword="Mechanical Engineer", location="High Wycombe")
  print(f"Found {len(new_jobs)} new unevaluated Reed job listings.")

  os.makedirs(APPLICATIONS_DIR, exist_ok=True)

  for i, job in enumerate(new_jobs):
    print(f"\nEvaluating Reed Job {i+1}/{len(new_jobs)}: {job['title']} at {job['employer']}\nURL: {job['url']}")

    eval_prompt = (
        "Review this job description against my career vault. Provide a compatibility "
        "score out of 10, key strengths, potential gaps, and a recommendation on whether to apply:\n\n"
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

    if is_top_match:
      print("Generating tailored CV positioning & cover letter draft...")
      cv_prompt = (
          "Based on my career vault, write tailored CV highlight bullet points "
          "and a brief cover letter pitch customized specifically for this role:\n\n"
          f"Job Title: {job['title']}\nDescription:\n{job['description']}"
      )
      tailored_content = query_ollama(cv_prompt, vault_context)

      safe_title = "".join(c if c.isalnum() else "_" for c in job["title"]).strip("_")
      file_path = os.path.join(APPLICATIONS_DIR, f"reed_app_{i+1}_{safe_title}.md")
      with open(file_path, "w", encoding="utf-8") as f:
        f.write(f"# Role (Reed): {job['title']}\n")
        f.write(f"- **Employer:** {job['employer']}\n")
        f.write(f"- **URL:** {job['url']}\n")
        f.write(f"- **Date Posted:** {job['date']}\n\n")
        f.write(f"## Evaluation & Fit\n{analysis}\n\n")
        f.write(f"## Tailored CV & Cover Letter Package\n{tailored_content}\n")
      print(f"Saved tailored application package to {file_path}")

    print("-" * 60)
    save_processed_job(job["signature"], job["title"], job["employer"], job["url"], score_str)

  print("Reed pipeline execution complete!")