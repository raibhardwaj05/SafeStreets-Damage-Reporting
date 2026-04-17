import os
import sys
import pdfplumber

# Add backend directory to sys.path so we can import 'app'
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from app import create_app, db
from app.tender_agents import run_tender_pipeline

def main():
    app = create_app()
    download_dir = os.path.join(app.config['BASE_DIR'], 'test_downloads')

    with app.app_context():
        print(f"=== Starting Agent Pipeline on PDFs in {download_dir} ===")
        all_saved_works = []
        
        if not os.path.exists(download_dir):
            print(f"Directory not found: {download_dir}")
            return
            
        for filename in os.listdir(download_dir):
            if not filename.endswith('.pdf'):
                continue
            if len(sys.argv) > 1 and sys.argv[1].lower() not in filename.lower():
                continue
                
            filepath = os.path.join(download_dir, filename)
            print(f"\n--- Processing: {filename} ---")
            
            ocr_text = ""
            try:
                with pdfplumber.open(filepath) as pdf:
                    for p_page in pdf.pages:
                        text = p_page.extract_text()
                        if text: 
                            ocr_text += text + "\n"
            except Exception as e:
                print(f"  ✗ PDF read error: {e}")
                continue
                
            if not ocr_text.strip():
                print(f"  ✗ Empty or scanned PDF image (No OCR text found).")
                continue
                
            try:
                # This runs Agent 1 (Extraction) & Agent 2 (Geocoding) and saves to DB
                saved = run_tender_pipeline(ocr_text, db.session)
                print(f"  ✓ SUCCESS: {len(saved)} WorkOrders extracted and saved to database.")
                if saved:
                    all_saved_works.extend(saved)
            except Exception as e:
                print(f"  ✗ Agent Pipeline failed: {e}")

        # Now test Agent 3 (Pothole Match)
        print("\n" + "="*50)
        print("=== Testing Agent 3 (Pothole Match) ===")
        print("="*50)
        
        from app.tender_agents import run_pothole_match
        from datetime import datetime
        import json
        
        # Try to use a recently extracted work order for testing if available
        test_work = next((w for w in all_saved_works if w.lat and w.lng), None)
        
        if test_work:
            p_lat = test_work.lat + 0.001
            p_lng = test_work.lng + 0.001
            print(f"Simulating pothole report near newly extracted {test_work.department} work...")
        else:
            # Fallback to central Mumbai coordinates if no works were extracted
            p_lat = 19.0760
            p_lng = 72.8777
            print("No road works extracted from PDFs. Simulating Agent 3 test on a random Mumbai coordinate...")
            
        print(f"Pothole GPS: {p_lat:.4f}, {p_lng:.4f}\n")
        
        try:
            match_result = run_pothole_match(
                pothole_lat=p_lat,
                pothole_lng=p_lng,
                detection_date=datetime.utcnow().isoformat(),
                db_session=db.session
            )
            print("\nAgent 3 Summary Statement:")
            print(match_result.get("accountability_statement", "No statement generated."))
            print("\nAgent 3 Top Match:")
            print(json.dumps(match_result.get("top_match", {}), indent=2))
        except Exception as e:
            print(f"  ✗ Agent 3 failed: {e}")

if __name__ == '__main__':
    main()
