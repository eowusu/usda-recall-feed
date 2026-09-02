#!/usr/bin/env python3
"""
Playwright-based USDA FSIS Recall Scraper
Bypasses Akamai WAF using real headless Chromium browser.
"""

import json
import re
import os
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "usda_recalls.json")

def scrape_fsis():
    recalls = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        try:
            print("Navigating to https://www.fsis.usda.gov/recalls ...")
            page.goto("https://www.fsis.usda.gov/recalls", wait_until="domcontentloaded", timeout=45000)
            page.wait_for_timeout(3000)

            # Find all recall cards/rows
            # FSIS uses Drupal views with rows containing titles, dates, risk levels
            cards = page.query_selector_all(".views-row, .recall-teaser, article")
            print(f"Found {len(cards)} recall blocks.")

            for card in cards:
                try:
                    title_elem = card.query_selector("h3 a, h2 a, .field--name-title a, a[href*='/recalls-alerts/']")
                    if not title_elem:
                        continue

                    title = title_elem.inner_text().strip()
                    href = title_elem.get_attribute("href") or ""
                    if not href.startswith("http"):
                        href = f"https://www.fsis.usda.gov{href}"

                    card_text = card.inner_text()

                    # Recalling firm
                    firm_m = re.search(r"^(.*?)\s+(?:Recalls|Issues|Expands Recall of|Expands Public Health Alert for)\s+(.*)$", title, re.IGNORE_CASE)
                    if firm_m:
                        firm = firm_m.group(1).strip()
                        product_and_reason = firm_m.group(2).strip()
                    else:
                        firm = "USDA Regulated Establishment"
                        product_and_reason = title

                    parts = re.split(r"\s+(?:Due to|Because of|For Possible|For Potential|Over Concerns of|Related to)\s+", product_and_reason, maxsplit=1, flags=re.IGNORE_CASE)
                    product_desc = parts[0].strip()
                    hazard = parts[1].strip() if len(parts) > 1 else "Public Health Alert"

                    # Risk severity
                    combined = f"{card_text} {title}".lower()
                    if "class i" in combined or "high risk" in combined:
                        severity = "CLASS_I"
                    elif "class ii" in combined or "low risk" in combined:
                        severity = "CLASS_II"
                    elif "class iii" in combined or "marginal risk" in combined:
                        severity = "CLASS_III"
                    elif any(k in combined for k in ["listeria", "salmonella", "e. coli", "undeclared"]):
                        severity = "CLASS_I"
                    else:
                        severity = "CLASS_I"

                    # Date parsing
                    date_m = re.search(r"([A-Za-z]{3,9}\s+\d{1,2},\s+\d{4})", card_text)
                    if date_m:
                        try:
                            dt = datetime.strptime(date_m.group(1), "%b %d, %Y")
                            date_str = dt.strftime("%Y-%m-%d")
                        except Exception:
                            try:
                                dt = datetime.strptime(date_m.group(1), "%B %d, %Y")
                                date_str = dt.strftime("%Y-%m-%d")
                            except Exception:
                                date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
                    else:
                        date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

                    # Quantity
                    qty_m = re.search(r"(?:approximately|approx\.?)\s+([0-9,]+(?:\.[0-9]+)?\s+(?:pounds|lbs|cases|units|packages|cartons))", card_text, re.IGNORE_CASE)
                    qty = qty_m.group(0).capitalize() if qty_m else ""

                    # Distribution
                    dist_m = re.search(r"(?:distributed to|shipped to|sent to|sold in|retail locations in|distributors in)\s+([^.;\n]+)", card_text, re.IGNORE_CASE)
                    if dist_m and len(dist_m.group(1).strip()) > 4:
                        distribution = dist_m.group(1).strip()
                    elif "nationwide" in combined:
                        distribution = "Nationwide"
                    else:
                        distribution = "Nationwide / Multiple States"

                    slug = href.rstrip("/").split("/")[-1][:35] if href else f"USDA-{date_str}"
                    recall_num = f"FSIS-{slug}"

                    recalls.append({
                        "recall_number": recall_num,
                        "product_description": product_desc,
                        "reason_for_recall": hazard,
                        "recalling_firm": firm,
                        "classification": severity,
                        "product_quantity": qty,
                        "distribution_pattern": distribution,
                        "status": "Active",
                        "recall_initiation_date": date_str,
                        "report_date": date_str,
                        "city": "",
                        "state": "",
                        "country": "USA",
                        "code_info": "EST establishment number on packaging",
                        "voluntary_mandated": "Voluntary: Firm Initiated",
                        "agency": "USDA",
                        "url": href
                    })
                except Exception as e:
                    print(f"Error parsing card: {e}")

        except Exception as e:
            print(f"Playwright navigation error: {e}")
        finally:
            browser.close()

    return recalls

def main():
    print("Running Playwright USDA Scraper...")
    scraped = scrape_fsis()
    print(f"Scraped {len(scraped)} recalls.")

    if scraped:
        output_data = {
            "last_updated": datetime.now(timezone.utc).isoformat(),
            "total": len(scraped),
            "results": scraped
        }
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(output_data, f, indent=2)
        print(f"Successfully wrote {len(scraped)} recalls to {OUTPUT_FILE}")
    else:
        print("Scraping returned 0 items; preserving existing file.")

if __name__ == "__main__":
    main()
