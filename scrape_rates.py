from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import json
import re
from datetime import datetime

def scrape_term(page, term_years):
    """Scrape > 100% LTV annuity rates for a given fixed term (years)."""
    url = f"https://www.hypotheker.nl/en/mortgage-interest-rates/annuity-mortgage/{term_years}-year/"
    print(f"\n🔗 Fetching {term_years}-year rates: {url}")
    page.goto(url, wait_until="networkidle")
    page.wait_for_timeout(2000)

    # --- COOKIE BANNER DISMISSAL ---
    try:
        cookie_locator = page.get_by_role("button", name=re.compile(r"Accept|Accepteer|Akkoord", re.IGNORECASE)).first
        if cookie_locator.is_visible():
            cookie_locator.click()
            page.wait_for_timeout(1500)
        else:
            page.evaluate("""() => {
                const buttons = Array.from(document.querySelectorAll('button, div, span, a'));
                const btn = buttons.find(b => {
                    const t = b.textContent.trim().toLowerCase();
                    return t === 'accept' || t === 'accepteer' || t === 'akkoord';
                });
                if (btn) btn.click();
            }""")
            page.wait_for_timeout(1500)
    except Exception:
        pass
    # Force-remove cookie bar overlay in case it persists and blocks clicks
    page.evaluate("""() => {
        document.querySelectorAll('[js-hook-cookie-bar], .c-cookie-bar, .c-cookie-bar__overlay').forEach(el => el.remove());
    }""")

    # --- SELECT > 100% LTV ---
    print(f"  Selecting '> 100%' interestTariff...")
    try:
        page.locator('#interestTariff').select_option(value='106')
        print(f"  ✅ Selected '> 100%'. Waiting for refresh...")
        page.wait_for_timeout(5000)
    except Exception as e:
        print(f"  ❌ interestTariff select failed: {e}")

    # --- SCROLL ---
    for _ in range(4):
        page.mouse.wheel(0, 500)
        page.wait_for_timeout(200)

    # --- EXPAND ALL RESULTS ---
    print(f"  Looking for 'Show all results' button...")
    try:
        expand_btn = page.locator(r"text=/Show all \d+ results/i").first
        if not expand_btn.is_visible():
            expand_btn = page.locator(r"text=/Toon alle \d+ resultaten/i").first

        if expand_btn.is_visible():
            print(f"  ⚡ Found: '{expand_btn.inner_text()}'. Clicking...")
            expand_btn.scroll_into_view_if_needed()
            expand_btn.click(force=True)
            print(f"  ✅ Expanded. Waiting for render...")
            page.wait_for_timeout(4000)
            for _ in range(12):
                page.mouse.wheel(0, 600)
                page.wait_for_timeout(150)
        else:
            print(f"  ⚠️ Expand button not visible. Scraping current view...")
    except Exception as e:
        print(f"  ❌ Expand click failed: {e}")

    return page.content()


def parse_rates(html_content, term_years):
    soup = BeautifulSoup(html_content, 'html.parser')
    rates = []
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

            rates.append({
                "bank_name": bank_name,
                "mortgage_name": mortgage_name,
                "mortgage_type": "Annuity",
                "fixed_term": f"{term_years}-year",
                "interest_rate": interest_rate,
                "logo_url": logo
            })

    # Fallback: table rows
    if len(rates) <= 10:
        print(f"  Running table-row fallback for {term_years}-year...")
        for row in soup.find_all('tr'):
            cols = [c.get_text(strip=True) for c in row.find_all(['td', 'th'])]
            if len(cols) >= 2 and any('%' in col for col in cols):
                mortgage_name = cols[0].strip()
                if mortgage_name.lower() in ["rente", "product", ""] or mortgage_name in seen_mortgages:
                    continue
                seen_mortgages.add(mortgage_name)

                bank_name = "ABN AMRO" if mortgage_name.upper().startswith("ABN AMRO") else (mortgage_name.split()[0] if mortgage_name.split() else "Unknown")

                img = row.find('img')
                logo = img['src'] if (img and img.get('src')) else "N/A"
                if logo.startswith('/'):
                    logo = "https://www.hypotheker.nl" + logo

                rates.append({
                    "bank_name": bank_name,
                    "mortgage_name": mortgage_name,
                    "mortgage_type": "Annuity",
                    "fixed_term": f"{term_years}-year",
                    "interest_rate": next((c for c in cols if '%' in c), "N/A"),
                    "logo_url": logo
                })

    print(f"  📊 {term_years}-year: {len(rates)} products found")
    return rates


def scrape_hypotheker_all_products():
    print("🚀 Launching browser (Headless mode enabled for GitHub Actions)...")
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)

        all_rates = {}
        for term in [5, 10]:
            # Fresh context per term — avoids cookie/state pollution across navigations
            context = browser.new_context(viewport={"width": 1280, "height": 1000})
            page = context.new_page()
            page.set_extra_http_headers({
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            })
            html = scrape_term(page, term)
            all_rates[f"{term}-year"] = parse_rates(html, term)
            context.close()

        browser.close()

    output = {
        "source_url": "https://www.hypotheker.nl/en/mortgage-interest-rates/annuity-mortgage/",
        "scraped_at": datetime.now().isoformat(),
        "ltv_filter": "> 100%",
        "mortgage_type": "Annuity",
        "rates_by_term": all_rates
    }

    output_file = "hypotheker_products_complete.json"
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(output, f, indent=4, ensure_ascii=False)

    total = sum(len(v) for v in all_rates.values())
    print(f"\n🎉 Extraction Successful!")
    print(f"📊 Total products: {total} ({', '.join(f'{k}: {len(v)}' for k, v in all_rates.items())})")
    print(f"💾 File updated: '{output_file}'")


if __name__ == "__main__":
    scrape_hypotheker_all_products()
