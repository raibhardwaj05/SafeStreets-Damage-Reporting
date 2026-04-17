"""
cron_scraper.py
Automated web scraper for mahatenders.gov.in using Playwright.
Downloads recent tender PDFs and passes them directly to the Pothole Accountability Agent pipeline.
Intended to be run via cron every 12 hours.
"""

import os
import sys
import time
import requests
import tempfile
import pdfplumber
from datetime import datetime
from playwright.sync_api import sync_playwright

# Setup Flask app context so we can use the DB and Agents
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import create_app, db
from app.tender_agents import run_tender_pipeline, run_accountability_sweep

def run_scraper():
    print(f"\n[{datetime.utcnow().isoformat()}] Starting Mahatenders Scraper...")

    app = create_app()
    with app.app_context():
        # Setup temp download dir
        download_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'work_notices')
        os.makedirs(download_dir, exist_ok=True)

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            
            # Use a context that allows automatic downloads
            context = browser.new_context(accept_downloads=True)
            page = context.new_page()

            # The default Mahatenders live active tenders URL
            # Note: Government portals change often. This uses the basic latest active tenders list.
            print("→ Navigating to Mahatenders Active Tenders...")
            
            try:
                # Go directly to active tenders page (bypassing some landing page fluff if possible)
                page.goto("https://www.mcgm.gov.in/irj/portal/anonymous/qletenders_new", timeout=60000)
                
                # Wait for the main tender table to load
                page.wait_for_selector("table.dataTable", timeout=15000)

                # Find tenders in the dataTable
                tenders = page.locator("table.dataTable tbody tr").all()
                print(f"→ Found {len(tenders)} rows on page 1...")

                # For full realism, mahatenders usually has a CAPTCHA on the actual download page.
                # Since we don't have a captcha solver integrated here, we simulate the scraping logic 
                # but fallback to processing existing PDFs if the portal blocks headless bots.
                
                # We will click the first tender's 'View' button if available.
                # In Mahatenders, the view link is usually an anchor tag inside the td with id 'DirectLink_X'
                
                # We will extract basic text from the table
                row = tenders[0] if tenders else None
                if row:
                    try:
                        print(f"  → Attempting to open first tender: {row.inner_text()[:60]}...")
                        # Click the view link in the second column
                        view_link = row.locator("td:nth-child(2) a").first
                        if view_link.count() > 0:
                            href = view_link.get_attribute("href")
                            print(f"  → Found PDF link: {href}")
                            # For MCGM portal, the link might be relative or full. Let's make sure it's full.
                            if href and not href.startswith("http"):
                                href = "https://www.mcgm.gov.in" + href
                            
                            # Let's try downloading it directly by issuing a page.goto or using request
                            # Wait for the download if the browser triggers one
                            try:
                                print("  → ATTEMPTING DOWNLOAD...")
                                with page.expect_download(timeout=15000) as download_info:
                                    view_link.click()
                                
                                download = download_info.value
                                save_path = os.path.join(download_dir, download.suggested_filename)
                                download.save_as(save_path)
                                print(f"  ✅ Successfully downloaded: {download.suggested_filename}")
                            except Exception as down_e:
                                print(f"  ⚠ Did not trigger automatic download. Navigating to PDF instead... {down_e}")
                                # Navigating to PDF means we might just get the PDF in the browser or we can download it manually via python requests
                                response = requests.get(href, verify=False)
                                if response.status_code == 200:
                                    filename = href.split('/')[-1].split('?')[0] or "tender_mcgm.pdf"
                                    if not filename.endswith('.pdf'):
                                        filename += '.pdf'
                                    save_path = os.path.join(download_dir, filename)
                                    with open(save_path, 'wb') as f:
                                        f.write(response.content)
                                    print(f"  ✅ Successfully downloaded via requests: {filename}")
                                else:
                                    print("  ⚠ Failed to download PDF via requests.")
                        else:
                            print("  ⚠ No 'View' link found for this tender row.")
                    except Exception as e:
                        print(f"  ⚠ Error interacting with tender row: {e}")

                print("\n[INFO] Scraper finished looking for links.")

            finally:
                browser.close()

            # Example of how the pipeline is called once a PDF is downloaded
            print("\n→ Scanning Download Directory for unprocessed PDFs...")
            for filename in os.listdir(download_dir):
                if filename.endswith(".pdf"):
                    filepath = os.path.join(download_dir, filename)
                    
                    print(f"\nProcessing: {filename}")
                    
                    # 1. OCR Step
                    ocr_text = ""
                    try:
                        with pdfplumber.open(filepath) as pdf:
                            for p_num, p_page in enumerate(pdf.pages):
                                text = p_page.extract_text()
                                if text:
                                    ocr_text += text + "\n"
                    except Exception as e:
                        print(f"  ✗ PDF Plumber error on {filename}: {e}")
                        continue

                    if not ocr_text.strip():
                        print(f"  ✗ Empty OCR text for {filename} (scanned image?)")
                        continue

                    # 2. Agent 1 + Agent 2 Pipeline
                    try:
                        saved = run_tender_pipeline(ocr_text, db.session)
                        print(f"  ✓ SUCCESS: {len(saved)} WorkOrders extracted and geocoded via Gemini from {filename}.")
                        
                        # Move processed file to an archive folder so we don't process it again
                        archive_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'work_notices_processed')
                        os.makedirs(archive_dir, exist_ok=True)
                        os.rename(filepath, os.path.join(archive_dir, filename))
                    except Exception as e:
                        print(f"  ✗ Pipeline failed for {filename}: {e}")

        # -----------------------------------------------
        # AGENT 3 SWEEP
        # After all new WorkOrders are saved, re-run Agent 3
        # against every damage report with GPS coordinates.
        # -----------------------------------------------
        print("\n\n=== RUNNING AGENT 3 ACCOUNTABILITY SWEEP ===")
        try:
            sweep_result = run_accountability_sweep(db.session)
            print(f"  Sweep complete: {sweep_result}")
        except Exception as e:
            print(f"  ✗ Sweep failed: {e}")

    print(f"\n[{datetime.utcnow().isoformat()}] Scraper Finished.")

if __name__ == "__main__":
    run_scraper()
