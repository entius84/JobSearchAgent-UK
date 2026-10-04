import json
import os
import time
from docx import Document
from playwright.sync_api import sync_playwright
from pypdf import PdfReader
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL_NAME = "qwen2.5:14b"
PROCESSED_FILE = "processed_jobs.json"
APPLICATIONS_DIR = "tailored_applications"

SEARCH_TITLES = [
    "Mechanical Engineer",
    "Quality Engineer",
    "Quality Assurance Engineer",
    "Validation Engineer",
    "Compliance Engineer",
    "Regulatory Compliance Specialist",
    "Process Engineer",
    "Continuous Improvement Engineer",
    "Decontamination Engineer",
    "Medical Device Engineer",
    "Technical Operations Manager",
    "Operations Manager",
    "QMS Coordinator",
    "Project Engineer",
    "Operations Coordinator",
]


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
  system_instruction = (
      "CRITICAL: You are evaluating jobs for Vincenzo Vitiello, a mechanical "
      "engineer holding a BEng (Hons) from The Open University and AMIMechE "
      "status, with extensive NHS operational, quality management, and "
      "decontamination background. Never use placeholder brackets like "
      "[Your Name] or [Your Educational Background]; always use Vincenzo's "
      "actual background provided in the Career Vault context."
  )
  full_prompt = (
      f"{system_instruction}\n\nContext (My Career"
      f" Vault):\n{context}\n\nQuery:\n{prompt}"
  )
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
    print(f"Scanning directory and subfolders: {vault_path}")
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


def scrape_linkedin_search(page, keyword, location="High Wycombe", max_listings=3):
  processed_data = load_processed_jobs()
  detailed_jobs = []
  seen_urls = set()

  search_url = f"https://www.linkedin.com/jobs/search/?keywords={keyword.replace(' ', '%20')}&location={location.replace(' ', '%20')}"
  print(f"Navigating to LinkedIn search: {search_url}")
  page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
  time.sleep(3)

  for _ in range(4):
    try:
      page.locator(
          ".jobs-search-results-list, .scaffold-layout__list"
      ).evaluate("node => node.scrollBy(0, 1500)")
    except Exception:
      page.mouse.wheel(0, 2000)
    time.sleep(2)

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

      title_elem = card.locator(
          ".job-card-list__title, .job-card-container__link"
      ).first
      title = (
          title_elem.inner_text().strip()
          if title_elem.count() > 0
          else "Unknown Title"
      )
      if "\n" in title:
        title = title.split("\n")[0].strip()

      comp_elem = card.locator(
          ".job-card-container__company-name, .job-search-card__subtitle"
      ).first
      employer = (
          comp_elem.inner_text().strip()
          if comp_elem.count() > 0
          else "Unknown Employer"
      )

      signature = get_job_signature(title, employer)
      full_url = (
          clean_url
          if clean_url.startswith("http")
          else f"https://www.linkedin.com{clean_url}"
      )

      if signature in processed_data or full_url in seen_urls:
        continue

      seen_urls.add(full_url)
      desc_elem = page.locator(
          ".jobs-description__content, .jobs-box__html-content"
      ).first
      description = (
          desc_elem.inner_text().strip()
          if desc_elem.count() > 0
          else "Description not loaded."
      )

      detailed_jobs.append({
          "title": title,
          "employer": employer,
          "signature": signature,
          "date": f"LinkedIn Search: {keyword}",
          "url": full_url,
          "description": description,
          "platform": "LinkedIn",
      })

      if len(detailed_jobs) >= max_listings:
        break
    except Exception as e:
      print(f"Error scraping LinkedIn search card {i+1}: {e}")

  return detailed_jobs


def scrape_reed_recommendations(page, max_listings=5):
  processed_data = load_processed_jobs()
  detailed_jobs = []
  seen_urls = set()

  print("Navigating to Reed homepage for personalized recommendations...")
  page.goto("https://www.reed.co.uk/", wait_until="domcontentloaded", timeout=60000)
  time.sleep(3)

  if "signin" in page.url or "login" in page.url or "authentication" in page.url:
    print("Reed sign-in redirect detected.")
    input(
        "Please log in on Reed in the browser window, then press Enter here in"
        " the terminal to continue..."
    )
    page.goto("https://www.reed.co.uk/", wait_until="domcontentloaded", timeout=60000)
    time.sleep(3)

  page.evaluate("window.scrollTo(0, 500)")
  time.sleep(2)

  for _ in range(4):
    try:
      next_btn = page.locator(
          "button:has-text('›'), button[aria-label*='Next'], div.carousel-next"
      ).first
      if next_btn.count() > 0 and next_btn.is_visible():
        next_btn.click()
        time.sleep(1.5)
    except Exception:
      break

  cards = page.locator(
      "section:has-text('Recommended jobs') article,"
      " div:has-text('Recommended jobs') ~ div div.card,"
      " div[class*='job-result']"
  ).all()
  for i, card in enumerate(cards):
    try:
      link_elem = card.locator("a[href*='/jobs/']").first
      if link_elem.count() == 0:
        continue
      href = link_elem.get_attribute("href")
      full_url = f"https://www.reed.co.uk{href}" if href.startswith("/") else href

      title = link_elem.inner_text().strip()
      if not title or len(title) < 3:
        title_elem = card.locator("h2, h3, a").first
        if title_elem.count() > 0:
          title = title_elem.inner_text().strip()

      comp_elem = card.locator(
          "div[class*='posted'], span[class*='company'], p"
      ).first
      employer = (
          comp_elem.inner_text().strip()
          if comp_elem.count() > 0
          else "Unknown Employer"
      )
      if "Posted by" in employer:
        employer = employer.replace("Posted by", "").strip()

      signature = get_job_signature(title, employer)
      if signature in processed_data or full_url in seen_urls:
        continue

      seen_urls.add(full_url)
      link_elem.click()
      time.sleep(2.5)

      desc_elem = page.locator(
          "div.description, div.job-description, section.job-details"
      ).first
      description = (
          desc_elem.inner_text().strip()
          if desc_elem.count() > 0
          else "Description not loaded."
      )

      detailed_jobs.append({
          "title": title,
          "employer": employer,
          "signature": signature,
          "date": "Reed Recommended",
          "url": full_url,
          "description": description,
          "platform": "Reed",
      })

      page.go_back(wait_until="domcontentloaded")
      time.sleep(2)

      if len(detailed_jobs) >= max_listings:
        break
    except Exception as e:
      print(f"Error scraping Reed recommendation card {i+1}: {e}")

  return detailed_jobs


def scrape_reed_search(page, keyword, location="High Wycombe", max_listings=3):
  processed_data = load_processed_jobs()
  detailed_jobs = []
  seen_urls = set()

  kw_slug = keyword.lower().replace(" ", "-")
  loc_slug = location.lower().replace(" ", "-")
  search_url = f"https://www.reed.co.uk/jobs/{kw_slug}-jobs-in-{loc_slug}"

  print(f"Navigating to Reed search: {search_url}")
  page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
  time.sleep(3)

  cards = page.locator(
      "article.job-result, div.job-result-card, div.card-body"
  ).all()
  for i, card in enumerate(cards):
    try:
      link_elem = card.locator(
          "a.job-result-card__title-link, h2.title a, h3 a"
      ).first
      if link_elem.count() == 0:
        continue
      href = link_elem.get_attribute("href")
      full_url = f"https://www.reed.co.uk{href}" if href.startswith("/") else href

      title = link_elem.inner_text().strip()
      comp_elem = card.locator(
          "a.job-result-card__subtitle-link, div.posted-by, li.posted-by"
      ).first
      employer = (
          comp_elem.inner_text().strip()
          if comp_elem.count() > 0
          else "Unknown Employer"
      )

      signature = get_job_signature(title, employer)
      if signature in processed_data or full_url in seen_urls:
        continue

      seen_urls.add(full_url)
      link_elem.click()
      time.sleep(2.5)

      desc_elem = page.locator(
          "div.description, div.job-description, section.job-details"
      ).first
      description = (
          desc_elem.inner_text().strip()
          if desc_elem.count() > 0
          else "Description not loaded."
      )

      detailed_jobs.append({
          "title": title,
          "employer": employer,
          "signature": signature,
          "date": f"Reed Search: {keyword}",
          "url": full_url,
          "description": description,
          "platform": "Reed",
      })

      page.go_back(wait_until="domcontentloaded")
      time.sleep(2)

      if len(detailed_jobs) >= max_listings:
        break
    except Exception as e:
      print(f"Error scraping Reed search card {i+1}: {e}")

  return detailed_jobs


if __name__ == "__main__":
  print("Loading your career vault...")
  vault_dirs = [r"C:\JobSearchAgent\CV certificates and CPD"]
  docs = load_vault_documents(vault_dirs)
  print(
      f"Successfully loaded {len(docs)} documents from your career vault:"
      f" {list(docs.keys())}"
  )
  vault_context = "\n\n".join(
      [f"--- {name} ---\n {content}" for name, content in docs.items()]
  )

  profile_dir = r"C:\JobSearchAgent\playwright_profile"
  os.makedirs(APPLICATIONS_DIR, exist_ok=True)
  summary_records = []
  all_raw_jobs = []

  with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=profile_dir, headless=False, slow_mo=50
    )
    page = context.new_page()

    print("\n--- Fetching Reed Recommendations ---")
    all_raw_jobs.extend(scrape_reed_recommendations(page, max_listings=5))

    for title in SEARCH_TITLES:
      print(f"\n--- Searching LinkedIn for: {title} in High Wycombe ---")
      all_raw_jobs.extend(
          scrape_linkedin_search(
              page, keyword=title, location="High Wycombe", max_listings=2
          )
      )

      print(f"\n--- Searching Reed for: {title} in High Wycombe ---")
      all_raw_jobs.extend(
          scrape_reed_search(
              page, keyword=title, location="High Wycombe", max_listings=2
          )
      )

    unique_jobs = []
    seen_sigs = set()
    for job in all_raw_jobs:
      if job["signature"] not in seen_sigs:
        seen_sigs.add(job["signature"])
        unique_jobs.append(job)

    print(
        f"\nTotal unique new jobs to evaluate across platforms:"
        f" {len(unique_jobs)}"
    )

    for i, job in enumerate(unique_jobs):
      print(
          f"\nEvaluating Job {i+1}/{len(unique_jobs)} ({job['platform']}):"
          f" {job['title']} at {job['employer']}\nURL: {job['url']}"
      )

      eval_prompt = (
          "Review this job description against my career vault. Provide a"
          " compatibility score out of 10, key strengths, potential gaps, and a"
          " recommendation on whether to apply:\n\nTitle:"
          f" {job['title']}\nDescription:\n{job['description']}"
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

      match_label = "🔥 High Match" if is_top_match else "Skipped / Low"
      summary_records.append({
          "title": job["title"],
          "score": score_str,
          "match": match_label,
          "url": job["url"],
      })

      if is_top_match:
        print("Generating tailored CV positioning & cover letter draft...")
        cv_prompt = (
            "Based on my career vault, write tailored CV highlight bullet points"
            " and a brief cover letter pitch customized specifically for this"
            f" role:\n\nJob Title: {job['title']}\nDescription:\n{job['description']}"
        )
        tailored_content = query_ollama(cv_prompt, vault_context)

        safe_title = "".join(
            c if c.isalnum() else "_" for c in job["title"]
        ).strip("_")
        prefix = "reed" if job["platform"] == "Reed" else "linkedin"
        file_path = os.path.join(
            APPLICATIONS_DIR, f"{prefix}_app_{i+1}_{safe_title}.md"
        )
        with open(file_path, "w", encoding="utf-8") as f:
          f.write(
              f"# Role ({job['platform']}): {job['title']} at"
              f" {job['employer']}\n"
          )
          f.write(f"- **URL:** {job['url']}\n")
          f.write(f"- **Date Posted:** {job['date']}\n\n")
          f.write(f"## Evaluation & Fit\n{analysis}\n\n")
          f.write(
              f"## Tailored CV & Cover Letter Package\n{tailored_content}\n"
          )
        print(f"Saved tailored application package to {file_path}")

      print("-" * 60)
      save_processed_job(
          job["signature"],
          job["title"],
          job["employer"],
          job["url"],
          score_str,
      )

    summary_path = os.path.join(APPLICATIONS_DIR, "master_summary.md")
    with open(summary_path, "w", encoding="utf-8") as f:
      f.write("# 📊 Job Application Master Dashboard\n\n")
      f.write("| Job Title | Compatibility & Score | Status | Direct Link |\n")
      f.write("| :--- | :--- | :--- | :--- |\n")
      for rec in summary_records:
        is_high = "High Match" in rec["match"]
        title_col = rec["title"] if is_high else f"~~{rec['title']}~~"
        score_col = rec["score"] if is_high else f"~~{rec['score']}~~"
        status_col = rec["match"] if is_high else f"~~{rec['match']}~~"
        f.write(
            f"| {title_col} | {score_col} | {status_col} | [View"
            f" Job]({rec['url']}) |\n"
        )
    print(f"\nMaster summary dashboard updated: {summary_path}")

    context.close()
  print("Unified pipeline execution complete!")