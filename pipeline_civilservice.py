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
        print("Navigazione al portale Civil Service Jobs...")
        page.goto(search_url, wait_until="domcontentloaded", timeout=60000)
        
        # Pausa per permetterti di risolvere manualmente il captcha/robot check
        input("\nRisolvi l'eventuale controllo anti-bot nel browser, quindi premi **Invio** qui nel terminale per continuare...\n")
        time.sleep(2)

        # 1. Imposta la località nel campo Where e invia la ricerca
        try:
            where_input = page.locator("input[name='where'], input#where").first
            if where_input.count() > 0:
                where_input.fill(TARGET_LOCATION)
                
            search_btn = page.locator("button:has-text('Search for jobs'), input[type='submit']").first
            if search_btn.count() > 0:
                search_btn.click()
                time.sleep(5)
        except Exception as e:
            print(f"Nota sulla configurazione della ricerca iniziale: {e}")

        # 2. Imposta il raggio a 20 miglia tramite JavaScript
        try:
            print("Applicazione del filtro raggio a 20 miglia...")
            page.evaluate("""() => {
                document.querySelectorAll('details').forEach(el => el.open = true);
                let select = document.querySelector('#ID_csr_form_postcodedistance');
                if (select) {
                    select.value = '20';
                    select.dispatchEvent(new Event('change', { bubbles: true }));
                }
            }""")
            
            print("Attesa aggiornamento risultati...")
            time.sleep(5)
            print("Filtro applicato.")
        except Exception as e:
            print(f"Nota sull'applicazione del filtro a 20 miglia: {e}")

        # Estrae i link degli annunci puntando alle intestazioni o ai link principali dei risultati
        # Cerchiamo tutti i link all'interno dei risultati di ricerca (es. h2 a, h3 a o classi simili)
        job_links = page.locator("h2 a, h3 a, .search-result a, main a[href*='spec'], main a[href*='job']").all()
        
        # Se i selettori specifici non bastano, prendiamo i link validi che sembrano titoli di lavoro
        if len(job_links) == 0:
            job_links = page.locator("main a").all()

        print(f"Trovati {len(job_links)} elementi candidati.")

        jobs_data = []
        seen_urls = set()

        for link in job_links:
            try:
                if link.count() == 0:
                    continue
                
                title = link.inner_text().strip()
                # Filtriamo solo i link che sembrano titoli di lavoro reali (evitando paginazioni o link generici)
                if not title or len(title) < 8 or title.lower() in ["next »", "previous", "home", "sign in", "cymraeg", "advanced search"]:
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

                department = "Government Department"
                try:
                    department = link.evaluate(
                        """el => {
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
                    }""",
                        title,
                    )
                except Exception:
                    pass

                # Entra nei dettagli dell'annuncio per recuperare la descrizione
                link.click()
                time.sleep(2.5)

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
                print(f"[Estratto] {title} presso {department}")

                # Torna indietro ai risultati di ricerca e ri-applica se necessario
                page.go_back()
                time.sleep(2)

            except Exception as ex:
                print(f"Errore durante l'analisi dell'annuncio: {ex}")

        # Salva tutto su civiservice.json
        output_path = os.path.join(os.getcwd(), OUTPUT_FILE)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(jobs_data, f, indent=4)
        print(f"\nSalvati con successo {len(jobs_data)} lavori in {output_path}")

        context.close()


if __name__ == "__main__":
    scrape_civil_service()