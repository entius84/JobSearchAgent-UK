import json
import os
import re
import time
from playwright.sync_api import sync_playwright

PROCESSED_FILE = "processed_jobs.json"
PROFILE_DIR = r"C:\JobSearchAgent\playwright_profile"


def load_high_match_reed_jobs():
  if not os.path.exists(PROCESSED_FILE):
    print(f"Error: {PROCESSED_FILE} not found.")
    return []

  with open(PROCESSED_FILE, "r", encoding="utf-8") as f:
    data = json.load(f)

  reed_jobs = []
  for sig, info in data.items():
    if not isinstance(info, dict):
      continue

    score_str = str(info.get("score", ""))
    urls = info.get("urls", [])

    is_reed = any("reed.co.uk" in url for url in urls)
    
    # Extract numbers from the score string to find if any is >= 8
    numbers = [int(n) for n in re.findall(r"\d+", score_str)]
    is_high_match = any(8 <= n <= 10 for n in numbers)

    if is_reed and is_high_match:
      for url in urls:
        if "reed.co.uk" in url:
          reed_jobs.append({
              "title": info.get("title", "Unknown"),
              "employer": info.get("employer", "Unknown"),
              "url": url,
              "score": score_str,
          })
          break
  return reed_jobs


def click_reed_save_button(page):
  save_selectors = [
      "button:has-text('Save')",
      "button[aria-label*='Save']",
      "a:has-text('Save')",
      "button.save-job",
      "[data-qa='save-job']",
  ]

  for selector in save_selectors:
    btn = page.locator(selector).first
    if btn.count() > 0 and btn.is_visible():
      text = btn.inner_text().lower()
      if "saved" in text:
        print("-> Job is already saved on Reed.")
        return True
      btn.click()
      print("-> Successfully clicked 'Save' on Reed portal.")
      time.sleep(2)
      return True

  print("-> Warning: Could not locate a visible 'Save' button on this listing.")
  return False


if __name__ == "__main__":
  jobs = load_high_match_reed_jobs()
  if not jobs:
    print("No high-matching Reed jobs (score >= 8) found in processed records.")
    exit()

  print(f"Found {len(jobs)} high-matching Reed jobs to bookmark on the portal.")

  with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(
        user_data_dir=PROFILE_DIR, headless=False, slow_mo=50
    )
    page = context.new_page()

    for i, job in enumerate(jobs):
      print(
          f"\nProcessing {i+1}/{len(jobs)}: {job['title']} at"
          f" {job['employer']}\nScore: {job['score']}\nURL: {job['url']}"
      )
      try:
        page.goto(job["url"], wait_until="domcontentloaded", timeout=60000)
        time.sleep(3)

        if (
            "signin" in page.url
            or "login" in page.url
            or "authentication" in page.url
        ):
          print("Reed sign-in required.")
          input(
              "Please log in to Reed in the browser window, then press Enter"
              " here in the terminal to continue..."
          )
          page.goto(job["url"], wait_until="domcontentloaded", timeout=60000)
          time.sleep(3)

        click_reed_save_button(page)
      except Exception as e:
        print(f"Error processing job page: {e}")

    context.close()
  print("\nFinished saving high-match Reed jobs!")