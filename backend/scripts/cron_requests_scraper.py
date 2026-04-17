"""
cron_requests_scraper.py
Automated web scraper for mahatenders.gov.in using raw HTTP requests (Bypasses headless browser bot-blocks).
Downloads recent tender PDFs and passes them directly to the Pothole Accountability Agent pipeline.
"""

import os
import sys
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import time

# Setup Flask app context so we can use the DB and Agents
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import create_app, db
from app.tender_agents import run_tender_pipeline, run_accountability_sweep
import pdfplumber

def run_scraper():
    print(f"\n[{datetime.utcnow().isoformat()}] Starting Mahatenders Requests Scraper...")
    app = create_app()
    
    with app.app_context():
        download_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'work_notices')
        os.makedirs(download_dir, exist_ok=True)

        session = requests.Session()
        session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/114.0.0.0 Safari/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.9'
        })
        
        base_url = "https://mahatenders.gov.in"
        active_tenders_url = f"{base_url}/nicgep/app?page=FrontEndTendersByLocation&service=page"
        
        print("→ Fetching Active Tenders List...")
        try:
            resp = session.get(active_tenders_url, timeout=30)
            soup = BeautifulSoup(resp.text, "html.parser")
            
            # Find the active tenders table rows
            rows = soup.select("table.list_table tr.even, table.list_table tr.odd")
            print(f"→ Found {len(rows)} tender rows on Mahatenders!")
            
            # We'll process the first 3 for testing
            for i, row in enumerate(rows[:3]):
                link = row.select_one("a[id^='DirectLink_']")
                if not link:
                    continue
                    
                tender_title = row.text.strip().split('\n')[0][:50]
                href = link.get('href')
                detail_url = base_url + href
                
                print(f"\n  → Navigating to details for: {tender_title}...")
                
                # Fetch Tender Details page
                detail_resp = session.get(detail_url, timeout=30)
                detail_soup = BeautifulSoup(detail_resp.text, 'html.parser')
                
                # Find PDF download links (usually Tendernotice_X.pdf)
                pdf_anchors = detail_soup.select("a[href*='.pdf']")
                downloaded = False
                
                for pdf_a in pdf_anchors:
                    pdf_href = pdf_a.get('href')
                    if not pdf_href.startswith('http'):
                        pdf_href = base_url + pdf_href
                        
                    pdf_name = pdf_href.split('/')[-1].split('?')[0] or f"tender_{i}.pdf"
                    
                    print(f"    → Found PDF link: Downloading...")
                    
                    # Fetch PDF Data
                    pdf_resp = session.get(pdf_href, timeout=30)
                    
                    # Check if actually PDF and not intercepted by CAPTCHA page
                    if pdf_resp.headers.get('Content-Type') == 'application/pdf' or pdf_resp.content.startswith(b'%PDF'):
                        save_path = os.path.join(download_dir, pdf_name)
                        with open(save_path, 'wb') as f:
                            f.write(pdf_resp.content)
                        print(f"    ✅ Successfully saved real PDF: {pdf_name}")
                        downloaded = True
                        break # Only need one notice per tender
                    else:
                        print("    ⚠ Link was a CAPTCHA trap, skipping...")
                        
                if not downloaded:
                    print("    ⚠ No valid PDF could be downloaded (CAPTCHA blocked or missing).")
                    
                time.sleep(2) # Be polite to NIC servers
                
        except Exception as e:
            print(f"⚠ Connection error navigating NICGEP: {e}")

        # Process downloaded PDFs through Agent Pipeline
        print("\n\n=== AGENT PIPELINE PROCESSING ===")
        for filename in os.listdir(download_dir):
            if filename.endswith(".pdf"):
                filepath = os.path.join(download_dir, filename)
                print(f"\nProcessing: {filename}")
                
                ocr_text = ""
                try:
                    with pdfplumber.open(filepath) as pdf:
                        for p_page in pdf.pages:
                            text = p_page.extract_text()
                            if text: ocr_text += text + "\n"
                except Exception as e:
                    print(f"  ✗ PDF read error: {e}")
                    continue
                    
                if not ocr_text.strip():
                    print(f"  ✗ Empty or scanned PDF image.")
                    continue
                    
                try:
                    saved = run_tender_pipeline(ocr_text, db.session)
                    print(f"  ✓ SUCCESS: {len(saved)} WorkOrders extracted and geocoded via Gemini.")
                    
                    archive_dir = os.path.join(app.config['UPLOAD_FOLDER'], 'work_notices_processed')
                    os.makedirs(archive_dir, exist_ok=True)
                    os.rename(filepath, os.path.join(archive_dir, filename))
                except Exception as e:
                    print(f"  ✗ Agent Pipeline failed: {e}")

        # -----------------------------------------------
        # AGENT 3 SWEEP
        # After all new WorkOrders are saved, re-run Agent 3
        # against every damage report with GPS coordinates.
        # This refreshes accountability for the whole DB.
        # -----------------------------------------------
        print("\n\n=== RUNNING AGENT 3 ACCOUNTABILITY SWEEP ===")
        try:
            sweep_result = run_accountability_sweep(db.session)
            print(f"  Sweep complete: {sweep_result}")
        except Exception as e:
            print(f"  ✗ Sweep failed: {e}")

    print(f"\n[{datetime.utcnow().isoformat()}] HTTP Scraper Finished.")

if __name__ == "__main__":
    run_scraper()
