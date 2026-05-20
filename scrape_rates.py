from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime

def scrape_hypotheker_all_products():
    url = "https://www.hypotheker.nl/en/mortgage-interest-rates/annuity-mortgage/10-year/"
    
    print("🚀 Launching browser (Visual mode enabled so you can watch it)...")
    with sync_playwright() as p:
        # Running with headless=False so you can physically watch it clear the wall
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 1000})
        page = context.new_page()
        
        page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        })
        
        print(f"🔗 Connecting to: {url}")
        page.goto(url, wait_until="networkidle")
        page.wait_for_timeout(2000) # Give the cookie banner a moment to slide onto the screen
        
        # --- NATIVE SHADOW-DOM PIERCING COOKIE CLICK ---
        print("Targeting cookie wall button natively...")
        try:
            # Playwright natively pierces Shadow Roots when using text or role locators
            cookie_locator = page.get_by_role("button", name=re.compile(r"Accept|Accepteer|Akkoord", re.IGNORECASE)).first
            
            if cookie_locator.is_visible():
                print(f"🎯 Cookie button detected ('{cookie_locator.inner_text()}'). Clicking...")
                cookie_locator.click()
                print("🍪 Cookie wall dismissed successfully.")
                page.wait_for_timeout(1500)
            else:
                print("⚠️ Cookie button not instantly visible via role. Trying fallback text locator...")
                # Fallback text locator that also pierces shadow DOMs
                page.locator('text=/^(Accept|Accepteer|Akkoord)$/i').first.click(timeout=3000)
                print("🍪 Cookie wall dismissed via fallback locator.")
                page.wait_for_timeout(1500)
        except Exception as e:
            print(f"ℹ️ Cookie banner processing skipped or already cleared: {e}")

        # --- SCROLL DOWN TO THE BUTTON ---
        print("Scrolling down layout view to bring elements into viewport...")
        for _ in range(4):
            page.mouse.wheel(0, 500)
            page.wait_for_timeout(200)

        # --- CLICK THE EXPANSION BUTTON NATIVELY ---
        print("Looking for the 'Show all results' element...")
        try:
            # Raw string regex pattern prevents syntax warnings and pierces layout fragments
            expand_btn = page.locator(r"text=/Show all \d+ results/i").first
            
            # Dutch fallback if browser context alters locale parameters
            if not expand_btn.is_visible():
                expand_btn = page.locator(r"text=/Toon alle \d+ resultaten/i").first

            if expand_btn.is_visible():
                print(f"⚡ Found expand element: '{expand_btn.inner_text()}'. Clicking...")
                expand_btn.scroll_into_view_if_needed()
                expand_btn.click()
                print("✅ Click registered! Waiting 2 seconds for full list rendering...")
                page.wait_for_timeout(2000)
                
                # Scroll all the way down the newly expanded content to load images/lazy rows
                for _ in range(10):
                    page.mouse.wheel(0, 500)
                    page.wait_for_timeout(150)
            else:
                print("❌ Expansion element not visible on page layout. Taking screenshot to debug...")
                page.screenshot(path="failed_to_find_button.png")
        except Exception as e:
            print(f"❌ Failed clicking the expand element: {e}")

        # Capture complete inflated source markup
        html_content = page.content()
        browser.close()
        
    # --- BROAD PARSER RE-BUILT ---
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
            # 1. Extract interest rate
            rate_match = re.search(r'(\d+[\.,]\d+)\s*%', text)
            if not rate_match:
                continue
            interest_rate = f"{rate_match.group(1)}%"
            
            # 2. Extract Full Mortgage Display Name
            parts = text.split("Product")
            mortgage_name = parts[0].replace(".", "").strip()
            mortgage_name = re.sub(r'\s+', ' ', mortgage_name) # clean up double spacing
            
            # Filter out layout phrases caught as false positives
            if mortgage_name.lower() in ["rente", "product", "calculate", "show", "toon", "mortgage", "fixed", "annuity", ""] or len(mortgage_name) > 60:
                continue
                
            # Deduplicate by the unique package product name
            if mortgage_name in seen_mortgages:
                continue
            seen_mortgages.add(mortgage_name)
            
            # 3. Cleanly Extract the Core Bank Name
            if mortgage_name.upper().startswith("ABN AMRO"):
                bank_name = "ABN AMRO"
            elif mortgage_name.upper().startswith("ASR"):
                bank_name = "ASR"
            else:
                # Fallback to the first word if it's a standard single-word bank name
                words = mortgage_name.split()
                bank_name = words[0] if words else "Unknown"
            
            # 4. Grab Logo Link
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

    # --- FALLBACK PROTECTION CLEANUP ---
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

    # Write out data package
    output_file = "hypotheker_products_complete.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(scraped_payload, f, indent=4, ensure_ascii=False)
        
    print(f"\n🎉 Extraction Successful!")
    print(f"📊 Total unique mortgage packages collected: {len(scraped_payload['rates'])}")
    print(f"💾 File updated: '{output_file}'")

if __name__ == "__main__":
    scrape_hypotheker_all_products()
