"""
Lightweight Job Discovery Pipeline (pipeline_discovery.py)
----------------------------------------------------------
Pure scraping and ingestion engine with zero AI/LLM overhead.
Easily configurable keywords, location, and radius.
"""

import json
import os
import random
import time
from dotenv import load_dotenv
import requests
from requests.auth import HTTPBasicAuth
from playwright.sync_api import sync_playwright

load_dotenv()

# ==========================================
# CONFIGURATIONS (Easily modify here)
# ==========================================
SEARCH_LOCATION = "High Wycombe"
SEARCH_RADIUS_MILES = 20

SEARCH_KEYWORDS = [
    "Mechanical Engineer",
    "Quality Engineer",
    "Validation Engineer",
    "Process Engineer",
    "QMS Coordinator",
    "Project Engineer",
]

OUTPUT_DIR = "tailored_applications"
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "scraped_jobs_raw.json")
REED_API_KEY = os.getenv("REED_API_KEY")


def clean_text(text: str) -> str:
    return "".join(c.lower() for c in text if c.isalnum() or c.isspace()).strip()


def get_job_signature(title: str, employer: str) -> str:
    return f"{clean_text(title)}_{clean_text(employer)}"


def load_existing_signatures() -> set:
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {get_job_signature(item["title"], item["employer"]) for item in data if "title" in item and "employer" in item}
        except Exception:
            return set()
    return set()


def scrape_linkedin_search(page, keyword: str, location: str, radius: int, max_listings: int = 10) -> list:
    seen_sigs = load_existing_signatures()
    detailed_jobs = []
    seen_urls = set()

    search_url = f"https://www.linkedin.com/jobs/search/?keywords={keyword.replace(' ', '%20')}&location={location.replace(' ', '%20')}&distance={radius}"
    print(f"Navigating to LinkedIn search: {search_url}")
    
    try:
        page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        time.sleep(4)
    except Exception as e:
        print(f"Navigation error: {e}")
        return []

    for _ in range(4):
        try:
            page.locator(".jobs-search-results-list, .scaffold-layout__list").evaluate("node => node.scrollTop = node.scrollHeight")
        except Exception:
            try:
                page.mouse.wheel(0, 2000)
            except Exception:
                pass
        time.sleep(random.uniform(2.0, 3.0))

    job_links = page.locator("a[href*='/jobs/view/']").all()
    print(f"Found {len(job_links)} raw links for '{keyword}'.")

    for link in job_links:
        try:
            href = link.get_attribute("href")
            clean_url = href.split("?")[0] if href else ""
            if not clean_url:
                continue

            full_url = clean_url if clean_url.startswith("http") else f"https://www.linkedin.com{clean_url}"
            if full_url in seen_urls:
                continue

            link.scroll_into_view_if_needed()
            link.click()
            time.sleep(2.0)

            title = link.inner_text().strip().split("\n")[0]
            if not title or len(title) < 3:
                title = keyword

            employer = "Unknown Employer"
            try:
                employer = link.evaluate("""el => {
                    let card = el.closest('div') || el.parentElement;
                    for(let i=0; i<4; i++) {
                        if(!card) break;
                        let sub = card.querySelector('.job-card-container__company-name, .job-search-card__subtitle, span');
                        if(sub && sub.innerText.trim().length > 1) return sub.innerText.trim();
                        card = card.parentElement;
                    }
                    return 'Unknown Employer';
                }""")
            except Exception:
                pass

            signature = get_job_signature(title, employer)
            if signature in seen_sigs:
                continue

            seen_urls.add(full_url)
            seen_sigs.add(signature)

            desc_elem = page.locator(".jobs-description__content, .jobs-box__html-content, article.jobs-description").first
            description = desc_elem.inner_text().strip() if desc_elem.count() > 0 else "Description not loaded."

            detailed_jobs.append({
                "title": title,
                "employer": employer,
                "signature": signature,
                "url": full_url,
                "description": description,
                "platform": "LinkedIn",
                "keyword_queried": keyword
            })

            if len(detailed_jobs) >= max_listings:
                break
        except Exception as e:
            print(f"Error parsing link: {e}")

    return detailed_jobs


def fetch_reed_jobs(keyword: str, location: str, radius: int, max_listings: int = 10) -> list:
    seen_sigs = load_existing_signatures()
    detailed_jobs = []
    url = "https://www.reed.co.uk/api/1.0/search"

    params = {
        "keywords": keyword,
        "locationName": location,
        "distanceFromLocation": radius,
    }

    print(f"Fetching Reed API for '{keyword}' within {radius} miles of {location}...")
    try:
        response = requests.get(url, auth=HTTPBasicAuth(REED_API_KEY, ""), params=params, timeout=30)
        if response.status_code != 200:
            print(f"Reed API Error: {response.status_code}")
            return []

        for item in response.json().get("results", []):
            title = item.get("jobTitle")
            employer = item.get("employerName")
            job_url = item.get("jobUrl")
            description = item.get("jobDescription")

            if not title or not employer or not job_url:
                continue

            signature = get_job_signature(title, employer)
            if signature in seen_sigs:
                continue
            seen_sigs.add(signature)

            detailed_jobs.append({
                "title": title,
                "employer": employer,
                "signature": signature,
                "url": job_url,
                "description": description or "Description not provided.",
                "platform": "Reed",
                "keyword_queried": keyword
            })

            if len(detailed_jobs) >= max_listings:
                break
    except Exception as e:
        print(f"Error with Reed API: {e}")

    return detailed_jobs


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    all_new_jobs = []

    profile_dir = r"C:\JobSearchAgent\playwright_profile"
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_dir, headless=False, slow_mo=50,
            args=["--disable-blink-features=AutomationControlled"]
        )
        page = context.new_page()
        page.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")

        for kw in SEARCH_KEYWORDS:
            print(f"\n--- Scraping LinkedIn: {kw} ---")
            all_new_jobs.extend(scrape_linkedin_search(page, kw, SEARCH_LOCATION, SEARCH_RADIUS_MILES, max_listings=5))

            print(f"\n--- Querying Reed API: {kw} ---")
            all_new_jobs.extend(fetch_reed_jobs(kw, SEARCH_LOCATION, SEARCH_RADIUS_MILES, max_listings=5))

        context.close()

    # Append to centralized raw store
    existing_data = []
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                existing_data = json.load(f)
        except Exception:
            existing_data = []

    combined = existing_data + all_new_jobs
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(combined, f, indent=4)

    print(f"\nDiscovery complete! Added {len(all_new_jobs)} new jobs. Total raw database size: {len(combined)}")