"""
Civil Service Jobs Scraper (pipeline_civilservice.py)
-----------------------------------------------------
Scrapes Civil Service Jobs within a 20-mile radius of High Wycombe
and saves the output to civiservice.json.
"""

import json
import os
import time
from playwright.sync_api import sync_playwright

OUTPUT_FILE = "civiservice.json"
TARGET_LOCATION = "High Wycombe"


def scrape_civil_service():
    profile_dir = r"C:\JobSearchAgent\playwright_profile"
    os.makedirs(profile_dir, exist_ok=True)

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
        
        # Pause to let you handle any robot/captcha check manually
        input("\n👉 Complete any robot/captcha check in the browser window, then press **Enter** here in the terminal to continue...\n")
        time.sleep(2)

        # 1. Ensure "High Wycombe" is set in the Where box
        try:
            where_input = page.locator("input[name='where'], input#where").first
            if where_input.count() > 0:
                where_input.fill(TARGET_LOCATION)
                
            search_btn = page.locator("button:has-text('Search for jobs'), input[type='submit']").first
            if search_btn.count() > 0:
                search_btn.click()
                time.sleep(4)
        except Exception as e:
            print(f"Note on initial search setup: {e}")

        # 2. Open Advanced "Location filters" and set 20 miles radius
        try:
            print("Opening location filters...")
            loc_filter = page.locator("text=Location filters, summary:has-text('Location filters'), a:has-text('Location filters')").first
            if loc_filter.count() > 0 and loc_filter.is_visible():
                loc_filter.click()
                time.sleep(1.5)

            # Select '20' from the distance dropdown
            distance_select = page.locator("select[name*='distance'], select#search-distance, select").first
            if distance_select.count() > 0:
                distance_select.select_option("20")
                print("Set search distance to 20 miles.")
                time.sleep(3)
        except Exception as e:
            print(f"Note on applying 20-mile filter: {e}")

        # Extract all job listing links containing 'jcode'
        job_links = page.locator("a[href*='jcode']").all()
        print(f"Found {len(job_links)} job listings matching criteria.")

        jobs_data = []
        seen_urls = set()

        for link in job_links:
            try:
                if link.count() == 0:
                    continue
                href = link.get_attribute("href")
                if not href:
                    continue
                full_url = (
                    href
                    if href.startswith("http")
                    else f"https://www.civilservicejobs.service.gov.uk{href}"
                )
                if full_url in seen_urls:
                    continue
                seen_urls.add(full_url)

                title = link.inner_text().strip()
                if not title or len(title) < 3:
                    continue

                # Safely extract department context
                department = "Government Department"
                try:
                    department = link.evaluate(
                        """el => {
                        let container = el.closest('li') || el.closest('div') || el.parentElement;
                        for(let i=0; i<3; i++) {
                            if(!container) break;
                            let dept = container.querySelector('.department, .employer-name, .org-name, span');
                            if(dept && dept.innerText.trim().length > 1 && dept.innerText.trim() !== arguments[0]) {
                                return dept.innerText.trim();
                            }
                            container = container.parentElement;
                        }
                        return 'Government Department';
                    }""",
                        title,
                    )
                except Exception:
                    pass

                # Click into job details to grab description
                link.click()
                time.sleep(3)

                desc_elem = page.locator(
                    "#job-description, .job-details-content, main, article"
                ).first
                description = (
                    desc_elem.inner_text().strip()
                    if desc_elem.count() > 0
                    else "Description not extracted."
                )

                job_info = {
                    "title": title,
                    "employer": department,
                    "url": full_url,
                    "description": description,
                }
                jobs_data.append(job_info)
                print(f"[Extracted] {title} at {department}")

                # Go back to search results
                page.go_back()
                time.sleep(2)

            except Exception as ex:
                print(f"Error parsing listing: {ex}")

        # Save to civiservice.json
        output_path = os.path.join(os.getcwd(), OUTPUT_FILE)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(jobs_data, f, indent=4)
        print(f"\nSuccessfully saved {len(jobs_data)} jobs to {output_path}")

        context.close()


if __name__ == "__main__":
    scrape_civil_service()