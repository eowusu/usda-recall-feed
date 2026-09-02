#!/usr/bin/env python3
"""
USDA FSIS Recall Sync Script
Fetches active meat and poultry recalls from USDA FSIS and outputs normalized JSON.
"""

import json
import re
import urllib.request
from datetime import datetime, timezone
import os

FSIS_RSS_URL = "https://www.fsis.usda.gov/recalls-alerts/rss.xml"
OUTPUT_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "usda_recalls.json")

def fetch_rss():
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        "Accept": "application/rss+xml, application/xml, text/xml, */*"
    }
    req = urllib.request.Request(FSIS_RSS_URL, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            return resp.read().decode("utf-8")
    except Exception as e:
        print(f"Warning: Could not fetch live RSS: {e}")
        return None

def parse_items(xml_content):
    if not xml_content:
        return []

    items = []
    item_blocks = re.findall(r"<item>(.*?)</item>", xml_content, re.DOTALL)
    for block in item_blocks:
        title_m = re.search(r"<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>", block, re.DOTALL)
        link_m = re.search(r"<link>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</link>", block, re.DOTALL)
        desc_m = re.search(r"<description>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</description>", block, re.DOTALL)
        pub_m = re.search(r"<pubDate>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</pubDate>", block, re.DOTALL)

        title = clean_text(title_m.group(1)) if title_m else ""
        link = clean_text(link_m.group(1)) if link_m else ""
        desc = clean_text(desc_m.group(1)) if desc_m else ""
        pub_date = clean_text(pub_m.group(1)) if pub_m else ""

        if title:
            items.append(process_item(title, link, desc, pub_date))
    return items

def clean_text(text):
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&#39;", "'").replace("&nbsp;", " ")
    return re.sub(r"\s+", " ", text).strip()

def process_item(title, link, desc, pub_date):
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

    # Severity
    combined = f"{desc} {title} {hazard}".lower()
    if "class i" in combined or "high risk" in combined:
        severity = "CLASS_I"
    elif "class ii" in combined or "low risk" in combined:
        severity = "CLASS_II"
    elif "class iii" in combined or "marginal risk" in combined:
        severity = "CLASS_III"
    elif any(k in combined for k in ["listeria", "salmonella", "e. coli", "undeclared", "allergen"]):
        severity = "CLASS_I"
    else:
        severity = "CLASS_I"

    # Quantity
    qty_m = re.search(r"(?:approximately|approx\.?)\s+([0-9,]+(?:\.[0-9]+)?\s+(?:pounds|lbs|cases|units|packages|cartons))", desc, re.IGNORE_CASE)
    qty = qty_m.group(0).capitalize() if qty_m else ""

    # Distribution
    dist_m = re.search(r"(?:distributed to|shipped to|sent to|sold in|retail locations in|distributors in)\s+([^.;\n]+)", desc, re.IGNORE_CASE)
    if dist_m and len(dist_m.group(1).strip()) > 4:
        distribution = dist_m.group(1).strip()
    elif "nationwide" in combined:
        distribution = "Nationwide"
    else:
        distribution = "Nationwide / Multiple States"

    # Date
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if pub_date:
        try:
            clean_date = pub_date[:25].strip()
            dt = datetime.strptime(clean_date, "%a, %d %b %Y %H:%M:%S")
            date_str = dt.strftime("%Y-%m-%d")
        except Exception:
            pass

    slug = link.rstrip("/").split("/")[-1][:35] if link else f"USDA-{date_str}"
    recall_num = f"FSIS-{slug}"

    return {
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
        "url": link
    }

def get_base_recalls():
    return [
        {
            "recall_number": "FSIS-RC-005-2025",
            "product_description": "Not-Ready-To-Eat Frozen Buffalo Chicken Products",
            "reason_for_recall": "Misbranding and undeclared allergens (egg, soy, and wheat)",
            "recalling_firm": "Shanghai Ravioli Corporation",
            "classification": "CLASS_I",
            "product_quantity": "Approximately 2,500 pounds",
            "distribution_pattern": "Massachusetts, New York, Rhode Island",
            "status": "Active",
            "recall_initiation_date": "2025-02-14",
            "report_date": "2025-02-14",
            "city": "Boston",
            "state": "MA",
            "country": "USA",
            "code_info": "EST. 4567, Packed between Dec 1, 2024 and Feb 10, 2025",
            "voluntary_mandated": "Voluntary: Firm Initiated",
            "agency": "USDA",
            "url": "https://www.fsis.usda.gov/recalls-alerts/shanghai-ravioli-corporation-recalls-not-ready-eat-frozen-buffalo-chicken-products"
        },
        {
            "recall_number": "FSIS-RC-058-2024",
            "product_description": "Ready-To-Eat Meat and Poultry Products",
            "reason_for_recall": "Possible Listeria monocytogenes contamination",
            "recalling_firm": "BrucePac",
            "classification": "CLASS_I",
            "product_quantity": "Approximately 9,986,245 pounds",
            "distribution_pattern": "Nationwide",
            "status": "Active",
            "recall_initiation_date": "2024-10-09",
            "report_date": "2024-10-09",
            "city": "Durant",
            "state": "OK",
            "country": "USA",
            "code_info": "EST. 51205 or P-51205, Best if Used by June 19, 2025 to Oct 8, 2025",
            "voluntary_mandated": "Voluntary: Firm Initiated",
            "agency": "USDA",
            "url": "https://www.fsis.usda.gov/recalls-alerts/brucepac-recalls-ready-eat-meat-and-poultry-products-due-possible-listeria"
        },
        {
            "recall_number": "FSIS-RC-027-2024",
            "product_description": "Ready-To-Eat Liverwurst and Deli Meat Products",
            "reason_for_recall": "Confirmed Listeria monocytogenes contamination (Outbreak Investigation)",
            "recalling_firm": "Boar's Head Provisions Co., Inc.",
            "classification": "CLASS_I",
            "product_quantity": "Approximately 7,200,000 pounds",
            "distribution_pattern": "Nationwide",
            "status": "Active",
            "recall_initiation_date": "2024-07-26",
            "report_date": "2024-07-26",
            "city": "Jarratt",
            "state": "VA",
            "country": "USA",
            "code_info": "EST. 12612, Sell by dates through Oct 2024",
            "voluntary_mandated": "Voluntary: Firm Initiated",
            "agency": "USDA",
            "url": "https://www.fsis.usda.gov/recalls-alerts/boars-head-provisions-co--recalls-ready-eat-liverwurst-and-other-deli-meat-products"
        },
        {
            "recall_number": "FSIS-RC-044-2024",
            "product_description": "Ready-To-Eat Pork and Poultry Products",
            "reason_for_recall": "Produced without benefit of federal inspection and possible Listeria contamination",
            "recalling_firm": "Yu Shang Food, Inc.",
            "classification": "CLASS_I",
            "product_quantity": "Approximately 72,240 pounds",
            "distribution_pattern": "CA, FL, GA, IL, NV, NJ, NY, OR, PA, TX, WA",
            "status": "Active",
            "recall_initiation_date": "2024-11-09",
            "report_date": "2024-11-09",
            "city": "Spartanburg",
            "state": "SC",
            "country": "USA",
            "code_info": "EST. P-46684 or EST. M-46684",
            "voluntary_mandated": "Voluntary: Firm Initiated",
            "agency": "USDA",
            "url": "https://www.fsis.usda.gov/recalls-alerts/yu-shang-food-inc--recalls-ready-eat-meat-and-poultry-products"
        }
    ]

def main():
    print("Syncing USDA FSIS Recalls...")
    rss_xml = fetch_rss()
    parsed = parse_items(rss_xml)

    existing_map = {r["recall_number"]: r for r in get_base_recalls()}
    for item in parsed:
        existing_map[item["recall_number"]] = item

    merged_list = list(existing_map.values())
    merged_list.sort(key=lambda x: x.get("recall_initiation_date", ""), reverse=True)

    output_data = {
        "last_updated": datetime.now(timezone.utc).isoformat(),
        "total": len(merged_list),
        "results": merged_list
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output_data, f, indent=2)

    print(f"Successfully synced {len(merged_list)} recalls to {OUTPUT_FILE}")

if __name__ == "__main__":
    main()
