import json
import os
import time
from playwright.sync_api import sync_playwright

PROCESSED_JOBS_FILE = "processed_jobs.json"


def clean_text(text):
  return "".join(c.lower() for c in text if c.isalnum() or c.isspace()).strip()


def get_job_signature(title, employer):
  return f"{clean_text(title)}_{clean_text(employer)}"


def load_processed_jobs():
  if os.path.exists(PROCESSED_JOBS_FILE):
    try:
      with open(PROCESSED_JOBS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
        if isinstance(data, list):  # Backwards compatibility for old list format
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
  with open(PROCESSED_JOBS_FILE, "w", encoding="utf-8") as f:
    json.dump(processed, f, indent=2)


def scrape_top_applicant_jobs_with_descriptions(max_pages=2):
  profile_dir = r"C:\JobSearchAgent\playwright_profile"

  with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=profile_dir, headless=False, slow_mo=50
    )
    page = context.new_page()

    detailed_jobs = []
    seen_urls = set()

    for page_num in range(max_pages):
      base_url = "https://www.linkedin.com/jobs/collections/recommended/?recommendationChannel=TOP_APPLICANT"
      current_url = (
          f"{base_url}&start={page_num * 25}" if page_num > 0 else base_url
      )

      print(f"Navigating to Top Applicant collection (Page {page_num + 1})...")
      page.goto(current_url, wait_until="domcontentloaded", timeout=60000)

      if "login" in page.url or "uas" in page.url or "microsoft" in page.url:
        print("Please complete login in the browser window...")
        input(
            "Press Enter here in the terminal *after* you are fully logged in..."
        )

      time.sleep(3)
      print("Scrolling the inner job list container...")
      for _ in range(8):
        try:
          page.locator(
              ".jobs-search-results-list, .scaffold-layout__list"
          ).evaluate("node => node.scrollBy(0, 1500)")
        except Exception:
          page.mouse.wheel(0, 2000)
        time.sleep(2)

      print("Extracting listings and filtering processed entries...")
      cards = page.locator(".job-card-container, li.occludable-update").all()

      page_new_found = 0
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
          time.sleep(2.5)  # Wait for description panel to render

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
          processed_data = load_processed_jobs()

          if signature in processed_data or clean_url in seen_urls:
            print(f"Skipping duplicate/processed role: {title} at {employer}")
            continue

          seen_urls.add(clean_url)

          date_posted = "N/A"
          time_elem = card.locator(
              "time, .job-card-container__listed-time"
          ).first
          if time_elem.count() > 0:
            date_posted = time_elem.inner_text().strip()

          desc_elem = page.locator(
              ".jobs-description__content, .jobs-box__html-content"
          ).first
          description = (
              desc_elem.inner_text().strip()
              if desc_elem.count() > 0
              else "Description not loaded."
          )

          full_url = (
              clean_url
              if clean_url.startswith("http")
              else f"https://www.linkedin.com{clean_url}"
          )
          detailed_jobs.append({
              "title": title,
              "employer": employer,
              "signature": signature,
              "date": date_posted,
              "url": full_url,
              "description": description,
              "card": card,
          })
          page_new_found += 1
          print(f"[{len(detailed_jobs)}] Extracted full details for: {title}")

          if len(detailed_jobs) >= 10:
            break

        except Exception as e:
          print(f"Skipping card {i+1} due to error: {e}")

        if len(detailed_jobs) >= 10:
          break

      if len(detailed_jobs) >= 10 or page_new_found == 0:
        break

    print(
        f"\nSuccessfully extracted {len(detailed_jobs)} complete new job"
        " profiles."
    )
    context.close()
    return detailed_jobs, page, context


if __name__ == "__main__":
  jobs, page, context = scrape_top_applicant_jobs_with_descriptions()