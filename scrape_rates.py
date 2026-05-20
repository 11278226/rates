from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime

def scrape_hypotheker_all_products():
    url = "https://www.hypotheker.nl/en/mortgage-interest-rates/annuity-mortgage/10-year/"
    
    print("🚀 Launching browser (Headless mode enabled for GitHub Actions)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True) 
        context = browser.new_context(viewport={"width": 1280, "height": 1000})
        page = context.new_page()
        
        page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        })
        
        print(f"🔗 Connecting to: {url}")
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(2000) 
        
        # --- COOKIE BANNER DISMISSAL ---
        print("Bypassing cookie consent wall...")
        try:
            cookie_locator = page.get_by_role("button", name=re.compile(r"Accept|Accepteer|Akkoord", re.IGNORECASE)).first
            if cookie_locator.is_visible():
                cookie_locator.click()
                print("🍪 Cookie wall dismissed via role locator.")
                page.wait_for_timeout(1500)
            else:
                print("⚠️ Role locator missed cookie button. Running JS fallback evaluator...")
                page.evaluate("""() => {
                    const buttons = Array.from(document.querySelectorAll('button, div, span, a'));
                    const btn = buttons.find(b => {
                        const t = b.textContent.trim().toLowerCase();
                        return t === 'accept' || t === 'accepteer' || t === 'akkoord';
                    });
                    if (btn) btn.click();
                }""")
                print("🍪 Cookie wall dismissed via fallback evaluator.")
                page.wait_for_timeout(1500)
        except Exception as e:
            print(f"ℹ️ Cookie step skipped or handled: {e}")

        # --- DROPDOWN SELECTION: CHANGE interestTariff TO > 100% ---
        print("Selecting '> 100%' from interestTariff dropdown...")
        try:
            page.locator('#interestTariff').select_option(value='106')
            print("✅ Selected '> 100%' (val=106). Waiting for page refresh...")
            page.wait_for_timeout(5000)
        except Exception as e:
            print(f"❌ Failed to select interestTariff: {e}")

        # --- SCROLL DOWN ---
        print("Scrolling viewport to bring tables into view...")
        for _ in range(4):
            page.mouse.wheel(0, 500)
            page.wait_for_timeout(200)

        # --- CLICK EXPANSION BUTTON ---
        print("Looking for the 'Show all results' expansion element...")
        try:
            expand_btn = page.locator(r"text=/Show all \d+ results/i").first
            if not expand_btn.is_visible():
                expand_btn = page.locator(r"text=/Toon alle \d+ resultaten/i").first

            if expand_btn.is_visible():
                print(f"⚡ Found expand element: '{expand_btn.inner_text()}'. Clicking...")
                expand_btn.scroll_into_view_if_needed()
                expand_btn.click()
                print("✅ Click registered! Waiting for full list rendering...")
                page.wait_for_timeout(4000)
                
                for _ in range(12):
                    page.mouse.wheel(0, 600)
                    page.wait_for_timeout(150)
            else:
                print("⚠️ Expansion button not visible. Scraping current view...")
        except Exception as e:
            print(f"❌ Failed clicking the expand element: {e}")

        html_content = page.content()
        browser.close()
        
    # --- DATA PARSING LAYER (BeautifulSoup) ---
    soup = BeautifulSoup(html_content, 'html.parser')
    
    scraped_payload = {
        "source_url": url,
        "scraped_at": datetime.now().isoformat(),
        "fixed_term": "10-year",
        "rates": []
    }
    
    seen_mortgages = set()
    
    for element in soup.find_all(['div', 'tr', 'li']):
        text = element.get_text(separator=" ", strip=True)
        
        if "Product" in text and "%" in text:
            rate_match = re.search(r'(\d+[\.,]\d+)\s*%', text)
            if not rate_match:
                continue
            interest_rate = f"{rate_match.group(1)}%"
            
            parts = text.split("Product")
            mortgage_name = parts[0].replace(".", "").strip()
            mortgage_name = re.sub(r'\s+', ' ', mortgage_name)
            
            if mortgage_name.lower() in ["rente", "product", "calculate", "show", "toon", "mortgage", "fixed", "annuity", ""] or len(mortgage_name) > 60:
                continue
                
            if mortgage_name in seen_mortgages:
                continue
            seen_mortgages.add(mortgage_name)
            
            if mortgage_name.upper().startswith("ABN AMRO"):
                bank_name = "ABN AMRO"
            elif mortgage_name.upper().startswith("ASR"):
                bank_name = "ASR"
            else:
                words = mortgage_name.split()
                bank_name = words[0] if words else "Unknown"
            
            img = element.find('img')
            logo = img['src'] if (img and img.get('src')) else "N/A"
            if logo.startswith('/'):
                logo = "https://www.hypotheker.nl" + logo
                
            scraped_payload["rates"].append({
                "bank_name": bank_name,
                "mortgage_name": mortgage_name,
                "mortgage_type": "Annuity",
                "interest_rate": interest_rate,
                "logo_url": logo
            })

    # --- FALLBACK PROTECTION ---
    if len(scraped_payload["rates"]) <= 10:
        print("Running table-row fallback extraction fallback strategy...")
        for row in soup.find_all('tr'):
            cols = [c.get_text(strip=True) for c in row.find_all(['td', 'th'])]
            if len(cols) >= 2 and any('%' in col for col in cols):
                mortgage_name = cols[0].strip()
                
                if mortgage_name.lower() in ["rente", "product", ""] or mortgage_name in seen_mortgages:
                    continue
                seen_mortgages.add(mortgage_name)
                
                if mortgage_name.upper().startswith("ABN AMRO"):
                    bank_name = "ABN AMRO"
                else:
                    bank_name = mortgage_name.split()[0] if mortgage_name.split() else "Unknown"
                
                img = row.find('img')
                logo = img['src'] if (img and img.get('src')) else "N/A"
                if logo.startswith('/'):
                    logo = "https://www.hypotheker.nl" + logo
                
                scraped_payload["rates"].append({
                    "bank_name": bank_name,
                    "mortgage_name": mortgage_name,
                    "mortgage_type": "Annuity",
                    "interest_rate": next((c for c in cols if '%' in c), "N/A"),
                    "logo_url": logo
                })

    output_file = "hypotheker_products_complete.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(scraped_payload, f, indent=4, ensure_ascii=False)
        
    print(f"\n🎉 Extraction Successful!")
    print(f"📊 Total unique mortgage packages collected: {len(scraped_payload['rates'])}")
    print(f"💾 File updated: '{output_file}'")

if __name__ == "__main__":
    scrape_hypotheker_all_products()