def scrape_multiple_pages(page, max_pages=3):
  all_new_jobs = []
  processed_urls = load_processed_jobs()

  for page_num in range(max_pages):
    start_index = page_num * 25
    print(f"Scraping search results page {page_num + 1} (start={start_index})...")
    
    # Navigate to the paginated search URL
    current_url = f"{BASE_SEARCH_URL}&start={start_index}"
    page.goto(current_url)
    time.sleep(3)

    job_cards = page.locator(".job-card-container").all()
    if not job_cards:
      print("No more job cards found on this page.")
      break

    for card in job_cards:
      try:
        title_elem = card.locator(".job-card-list__title")
        link_elem = card.locator("a.job-card-container__link")
        job_url = link_elem.get_attribute("href").split("?")[0]
        job_title = title_elem.inner_text().strip()

        if job_url not in processed_urls:
          all_new_jobs.append({
              "title": job_title,
              "url": job_url,
              "card": card
          })
      except Exception as e:
        continue

  return all_new_jobs