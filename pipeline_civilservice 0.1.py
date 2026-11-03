"""
Civil Service Jobs Scraper (pipeline_civilservice.py)
-----------------------------------------------------
Scrapes all Civil Service Jobs within a 20-mile radius of High Wycombe
across all pages, avoids duplicates using civiservice.json, and accumulates results.
"""

import json
import os
import time
from playwright.sync_api import sync_playwright

OUTPUT_FILE = "civiservice.json"
TARGET_LOCATION = "High Wycombe"


def load_existing_jobs():
    """Loads already saved jobs from civiservice.json to avoid duplicates."""
    if os.path.exists(OUTPUT_FILE):
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
        except Exception:
            return []
    return []


def scrape_civil_service():
    profile_dir = r"C:\JobSearchAgent\playwright_profile"
    os.makedirs(profile_dir, exist_ok=True)

    # Load existing jobs to build our duplicate prevention set
    existing_jobs = load_existing_jobs()
    seen_urls = {job["url"] for job in existing_jobs if "url" in job}
    print(f"Loaded {len(existing_jobs)} existing jobs from {OUTPUT_FILE} (will skip duplicates).")

    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            user_data_dir=profile_dir,
            headless=False,
            slow_mo=50,
            args=["--disable-blink-features=AutomationControlled"],
        )
        page = context.new_page()
        page.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', {get: () => undefined})"
        )

        search_url = "https://www.civilservicejobs.service.gov.uk/csr/index.cgi"
        print("Navigating to Civil Service Jobs portal...")
        page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        
        # Pause for manual captcha/robot verification
        input("\n👉 Complete any robot/captcha check in the browser window, then press **Enter** here in the terminal to continue...\n")
        time.sleep(2)

        # 1. Set location search
        try:
            where_input = page.locator("input[name='where'], input#where").first
            if where_input.count() > 0:
                where_input.fill(TARGET_LOCATION)
                
            search_btn = page.locator("button:has-text('Search for jobs'), input[type='submit']").first
            if search_btn.count() > 0:
                search_btn.click()
                time.sleep(5)
        except Exception as e:
            print(f"Note on initial search setup: {e}")

        # 2. Set 20-mile radius filter & Sort by Newest via JavaScript
        try:
            print("Applying 20-mile radius and sorting by Newest...")
            page.evaluate("""() => {
                document.querySelectorAll('details').forEach(el => el.open = true);
                
                let selectDist = document.querySelector('#ID_csr_form_postcodedistance');
                if (selectDist) {
                    selectDist.value = '20';
                    selectDist.dispatchEvent(new Event('change', { bubbles: true }));
                }

                let sortSelect = document.querySelector('select#ID_csr_form_sortby, select[name*="sort"]');
                if (sortSelect) {
                    for (let option of sortSelect.options) {
                        let txt = option.text.toLowerCase();
                        if (txt.includes('new') || txt.includes('date') || txt.includes('closing')) {
                            sortSelect.value = option.value;
                            sortSelect.dispatchEvent(new Event('change', { bubbles: true }));
                            break;
                        }
                    }
                }
            }""")
            time.sleep(6)
            print("Filters and sorting applied successfully.")
        except Exception as e:
            print(f"Note on applying filters/sorting: {e}")

        # 3. Robust Multi-Page Pagination Loop
        all_new_jobs_meta = []
        page_num = 1

        while page_num <= 10:  # Safety cap at 10 pages (~250 jobs max)
            print(f"Scraping search results page {page_num}...")
            time.sleep(3)

            # Re-query links fresh on the current page DOM
            links = page.locator("h2 a, h3 a, .search-result a").all()
            page_jobs_count = 0

            for link in links:
                try:
                    if link.count() == 0:
                        continue
                    title = link.inner_text().strip()
                    if not title or len(title) < 8 or title.lower() in ["next »", "previous", "home", "sign in", "cymraeg", "advanced search"]:
                        continue
                    
                    href = link.get_attribute("href")
                    if not href:
                        continue
                    
                    full_url = href if href.startswith("http") else f"https://www.civilservicejobs.service.gov.uk{href}"
                    
                    # Skip if already in our json file or already collected in this run
                    if full_url in seen_urls:
                        continue
                    seen_urls.add(full_url)

                    department = "Government Department"
                    try:
                        department = link.evaluate("""el => {
                            let container = el.closest('li') || el.closest('div') || el.parentElement;
                            for(let i=0; i<4; i++) {
                                if(!container) break;
                                let dept = container.querySelector('.department, .employer-name, .org-name, span');
                                if(dept && dept.innerText.trim().length > 1 && dept.innerText.trim() !== arguments[0]) {
                                    return dept.innerText.trim();
                                }
                                container = container.parentElement;
                            }
                            return 'Government Department';
                        }""", title)
                    except Exception:
                        pass

                    all_new_jobs_meta.append({
                        "title": title,
                        "employer": department,
                        "url": full_url
                    })
                    page_jobs_count += 1
                except Exception:
                    pass

            print(f"Collected {page_jobs_count} new unique jobs from page {page_num}.")

            # Navigate to next page explicitly
            next_page_num = page_num + 1
            next_page_link = page.locator(f"a:has-text('{next_page_num}'), a:has-text('next »')").first
            
            if next_page_link.count() > 0 and next_page_link.is_visible():
                try:
                    next_page_link.click()
                    page_num = next_page_num
                    time.sleep(4)
                except Exception as ex:
                    print(f"Pagination navigation notice: {ex}")
                    break
            else:
                print("Reached the last page of search results.")
                break

        print(f"\nTotal new unique jobs to fetch descriptions for: {len(all_new_jobs_meta)}")

        # 4. Visit each new job URL to fetch full descriptions
        newly_scraped_jobs = []
        for i, job in enumerate(all_new_jobs_meta):
            print(f"[{i+1}/{len(all_new_jobs_meta)}] Fetching description: {job['title']} at {job['employer']}")
            try:
                page.goto(job['url'], wait_until="domcontentloaded", timeout=30000)
                time.sleep(2)

                desc_elem = page.locator("#job-description, .job-details-content, main, article").first
                description = desc_elem.inner_text().strip() if desc_elem.count() > 0 else "Description not extracted."

                job_info = {
                    "title": job['title'],
                    "employer": job['employer'],
                    "url": job['url'],
                    "description": description
                }
                newly_scraped_jobs.append(job_info)
            except Exception as ex:
                print(f"Error fetching details for {job['url']}: {ex}")

        # 5. Combine existing jobs with newly scraped ones and save back to civiservice.json
        combined_jobs = existing_jobs + newly_scraped_jobs
        output_path = os.path.join(os.getcwd(), OUTPUT_FILE)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(combined_jobs, f, indent=4)
            
        print(f"\nSuccessfully added {len(newly_scraped_jobs)} new jobs. Total jobs in {OUTPUT_FILE}: {len(combined_jobs)}")

        context.close()


if __name__ == "__main__":
    scrape_civil_service()