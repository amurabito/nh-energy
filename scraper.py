import json
import csv
import os
import re
from datetime import datetime
from bs4 import BeautifulSoup
from curl_cffi import requests

# UTILITY REGIONS & DEFAULT baseline rates (Effective Feb 2026 - July 2026)
UTILITIES = [
    {
        "id": "Unitil",
        "name": "Unitil (UES)",
        "url": "https://www.energy.nh.gov/engyapps/ceps/ResidentialCompare.aspx?choice=Unitil",
        "default_rate": 0.12061,
        "default_rate_note": "Effective Feb 1, 2026 - Jul 31, 2026"
    },
    {
        "id": "Eversource",
        "name": "Eversource (PSNH)",
        "url": "https://www.energy.nh.gov/engyapps/ceps/ResidentialCompare.aspx?choice=Eversource",
        "default_rate": 0.10542,
        "default_rate_note": "Effective Feb 1, 2026 - Jul 31, 2026"
    },
    {
        "id": "Liberty",
        "name": "Liberty Utilities",
        "url": "https://www.energy.nh.gov/engyapps/ceps/ResidentialCompare.aspx?choice=Liberty",
        "default_rate": 0.11790,
        "default_rate_note": "Effective Feb 1, 2026 - Jul 31, 2026"
    },
    {
        "id": "NHEC",
        "name": "NH Electric Co-op",
        "url": "https://www.energy.nh.gov/engyapps/ceps/ResidentialCompare.aspx?choice=NHEC",
        "default_rate": 0.11150,
        "default_rate_note": "Effective Feb 1, 2026 - Jul 31, 2026"
    }
]

def fetch_html_with_system_client(url):
    """Fetches HTML by impersonating a real browser's TLS signature (JA4/JA3)."""
    try:
        response = requests.get(
            url, 
            impersonate="chrome", 
            timeout=15,
            verify=False,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        if response.status_code != 200:
            return f"Status Code: {response.status_code}\n{response.text}"
        return response.text
    except Exception as err:
        raise RuntimeError(f"Failed to execute underlying network execution frame: {err}")

def parse_rate(rate_str):
    """Clean and parse rate value from string to float."""
    # Strip keywords, symbols, and explicit structural colons
    cleaned = rate_str.lower().replace("per kwh", "").replace("/kwh", "").replace("/ kwh", "").replace("$", "").replace(":", "").strip()
    
    if "¢" in cleaned or "cents" in cleaned or "cent" in cleaned:
        val = cleaned.replace("¢", "").replace("cents", "").replace("cent", "").strip()
        return float(val) / 100.0
    
    # Isolate the exact float string to avoid any trailing labels causing parsing exceptions
    match = re.search(r'\d+\.\d+', cleaned)
    if match:
        val = float(match.group(0))
    else:
        val = float(cleaned)
        
    # Global safety scale: If the rate parsed out as a whole number cents format (e.g. 13.02)
    if val > 1.0:
        val = val / 100.0
    return val

def normalize_space(value):
    """Collapse HTML whitespace into a single-space string."""
    return re.sub(r'\s+', ' ', value or '').strip()

def field_text(table, class_name, label=None):
    """Extract a value from one supplier card cell, removing the visible label."""
    el = table.find(class_=class_name)
    if not el:
        return ""

    text = normalize_space(el.get_text(" ", strip=True))
    if label:
        text = re.sub(rf"^{re.escape(label)}\s*:?\s*", "", text, flags=re.I)
    return normalize_space(text)

def rate_text(table):
    """Extract only the per-kWh price span, avoiding unrelated table numbers."""
    rate_span = table.find(id=re.compile(r'lblKWh'))
    if rate_span:
        return normalize_space(rate_span.get_text(" ", strip=True))

    text = normalize_space(table.get_text(" ", strip=True))
    match = re.search(r"per\s*kwh\s*:?\s*(\$?\d+(?:\.\d+)?)", text, flags=re.I)
    return match.group(1) if match else ""

def signup_link(table, fallback_url):
    """Return the supplier sign-up URL when the card exposes one."""
    for link in table.find_all("a", href=True):
        if "sign up" in normalize_space(link.get_text(" ", strip=True)).lower():
            return link["href"]
    return fallback_url

def extract_term_months(rate_end_str, comments_str, full_context_str=""):
    """Identify commitment months out of detail text strings."""
    search_str = f"{rate_end_str} {comments_str} {full_context_str}".lower()
    match = re.search(r"(\d+)\s*(?:month|mo|billing cycle)", search_str)
    if match:
        return f"{match.group(1)} Months"
    
    date_match = re.search(r"(jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*\s*\d{4}", search_str)
    if date_match:
        return f"Fixed until {date_match.group(0).capitalize()}"
        
    return rate_end_str.strip() or "Variable"

def check_intro_rate(plan_name, intro_price, comments):
    """Filter out introductory promos or teaser structures."""
    intro_clean = intro_price.strip().lower()
    if intro_clean and intro_clean not in ["no", "none", "$0", "$0.00", "n/a", "0", "false"]:
        return True

    search_str = f"{plan_name} {comments}".lower()
    intro_patterns = [
        r"\bintro(?:ductory)?\b",
        r"\bteaser\b",
        r"\bpromo(?:tional)?\b",
        r"\bnew\b.{0,40}\bcustomers?\b",
        r"\bonly available\b.{0,80}\bcustomers?\b",
        r"\bgift card\b",
        r"\b\d+\s*%\s*off\b",
    ]
    return any(re.search(pattern, search_str) for pattern in intro_patterns)

def check_cancellation_fee(fee_str):
    """Identify presence of a restrictive structural cancellation fee."""
    fee_clean = fee_str.lower().replace("cancellation fee:", "").strip()
    if not fee_clean or fee_clean in ["no", "none", "$0", "$0.00", "no cancellation fee", "n/a", "0", "false"]:
        return False
    return True

def scrape_utility(util):
    """Scrapes data elements mapping atomic multi-row table contexts."""
    print(f"Scraping live data for {util['name']}...")
    html = fetch_html_with_system_client(util['url'])
    
    if not html or "403 Forbidden" in html or "access denied" in html.lower():
        with open(f"debug_{util['id']}.html", "w", encoding="utf-8") as df:
            df.write(html)
        raise PermissionError(f"Akamai edge network block encountered. Saved dump to debug_{util['id']}.html")
        
    soup = BeautifulSoup(html, 'html.parser')
    suppliers = []

    # Find the specific supplier multi-row table components
    tables = soup.find_all('table', class_='tblCompareList')
    
    # Fallback to general tables containing supplier blocks if specific classes match
    if not tables:
        tables = [t for t in soup.find_all('table') if t.find(class_='CompanyName')]

    if not tables:
        with open(f"debug_{util['id']}.html", "w", encoding="utf-8") as df:
            df.write(html)
        raise ValueError(f"No supplier tables found in layout. Diagnostic saved to debug_{util['id']}.html")

    for table in tables:
        try:
            # Extract Identity Elements
            company_el = table.find(class_='CompanyName')
            if not company_el:
                continue
            name = normalize_space(company_el.get_text(" ", strip=True).replace("Company Name:", ""))
            
            plan_el = table.find(class_='PlanName')
            plan = normalize_space(plan_el.get_text(" ", strip=True)) if plan_el else "Standard Fixed"
            
            price_text = rate_text(table)
            if not price_text:
                continue
                
            rate_found = parse_rate(price_text)
            if rate_found <= 0:
                continue
            
            # Extract Fee Attributes
            fee_str = field_text(table, "CancellationFee", "Cancellation Fee") or "No"
            has_fee = check_cancellation_fee(fee_str)
            intro_price = field_text(table, "IntroPrice", "Intro Price") or "No"
            comments = field_text(table, "Comments", "Comments")
            term_text = field_text(table, "RateGoodFor", "Rate Good for")
            
            # Match existing strict validation rules (No Cancellation Fees & No Teaser Intro Rates)
            if not has_fee and not check_intro_rate(plan, intro_price, comments):
                term = extract_term_months(term_text, comments)
                suppliers.append({
                    "name": name, 
                    "plan": plan, 
                    "rate": rate_found, 
                    "term": term, 
                    "cancellation_fee": "No", 
                    "intro": "No", 
                    "link": signup_link(table, util["url"])
                })
        except Exception:
            continue

    with open(f"layout_{util['id']}.html", "w", encoding="utf-8") as lf:
        lf.write(html)

    if suppliers:
        print(f"Successfully scraped {len(suppliers)} live elements for {util['name']}.")
    else:
        print(f"Parsed {len(tables)} live elements for {util['name']}; none matched the no-fee/non-promo filter.")
    return suppliers

def scrape_all():
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M')
    all_results = []
    row_stats = {"date": current_time}
    
    # Housekeeping: Evict stale debug code outputs from previous broken runs
    for util in UTILITIES:
        for prefix in ["debug_", "layout_"]:
            old_file = f"{prefix}{util['id']}.html"
            if os.path.exists(old_file):
                os.remove(old_file)
    
    for util in UTILITIES:
        try:
            suppliers = scrape_utility(util)
            suppliers = sorted(suppliers, key=lambda x: x["rate"])
            
            for s in suppliers:
                s["utility_id"] = util["id"]
                s["utility_name"] = util["name"]
                all_results.append(s)

            supplier_best = suppliers[0] if suppliers else None
            default_is_best = not supplier_best or util["default_rate"] <= supplier_best["rate"]

            row_stats[f"{util['id']}_default"] = util["default_rate"]
            row_stats[f"{util['id']}_cheapest"] = util["default_rate"] if default_is_best else supplier_best["rate"]
            row_stats[f"{util['id']}_winner"] = "Utility Default Service" if default_is_best else supplier_best["name"]
        except Exception as err:
            print(f"CRITICAL ERROR: Failed to scrape {util['name']}: {err}")
            return

    valid_rates = [s["rate"] for s in all_results]
    row_stats["global_avg"] = round(sum(valid_rates) / len(valid_rates), 5) if valid_rates else ""
    row_stats["full_data"] = json.dumps(all_results)
    
    with open('suppliers.json', 'w') as f:
        json.dump(all_results, f, indent=2)
        
    file_exists = os.path.isfile('data.csv')
    fieldnames = [
        "date", "global_avg",
        "Unitil_default", "Unitil_cheapest", "Unitil_winner",
        "Eversource_default", "Eversource_cheapest", "Eversource_winner",
        "Liberty_default", "Liberty_cheapest", "Liberty_winner",
        "NHEC_default", "NHEC_cheapest", "NHEC_winner",
        "full_data"
    ]
    
    with open('data.csv', 'a', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        if not file_exists:
            writer.writeheader()
        writer.writerow(row_stats)
        
    print(f"Data pipeline complete at {current_time}. Records synchronized successfully.")

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    os.makedirs(script_dir, exist_ok=True)
    os.chdir(script_dir)
    scrape_all()
