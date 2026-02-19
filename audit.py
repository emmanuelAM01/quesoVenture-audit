#!/usr/bin/env python3
"""
Queso Ventures - Smart SEO/GEO Audit Generator
Auto-fetches: PageSpeed score, website existence, basic GBP data
Manual input:  GBP completeness, visibility, GEO, findings, recommendations

Usage:
    source .env && python audit.py

Requirements:
    pip install requests beautifulsoup4 reportlab

Optional (for PageSpeed):
    Get a free API key at https://developers.google.com/speed/docs/insights/v5/get-started
    Set it in the PAGESPEED_API_KEY variable below or as env var PAGESPEED_KEY
"""

import os
import re
import sys
import time
import requests
from bs4 import BeautifulSoup
from datetime import date
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, HRFlowable
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT

# ── Config ────────────────────────────────────────────────────────────────────
# Get free key at: https://developers.google.com/speed/docs/insights/v5/get-started
PAGESPEED_API_KEY = os.environ.get("PAGESPEED_KEY", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120 Safari/537.36"
}

# ── Brand Colors ──────────────────────────────────────────────────────────────
YELLOW     = colors.HexColor("#F5C842")
DARK       = colors.HexColor("#1A1A1A")
LIGHT_GRAY = colors.HexColor("#F5F5F5")
MID_GRAY   = colors.HexColor("#CCCCCC")
TEXT_GRAY  = colors.HexColor("#555555")
WHITE      = colors.white
RED        = colors.HexColor("#E74C3C")
ORANGE     = colors.HexColor("#F39C12")
GREEN      = colors.HexColor("#2ECC71")

# ── Helpers ───────────────────────────────────────────────────────────────────
def score_color(score, max_score=5):
    pct = score / max_score
    if pct < 0.4:   return RED
    elif pct < 0.7: return ORANGE
    else:           return GREEN

def score_label(score, max_score=5):
    pct = score / max_score
    if pct < 0.4:   return "Needs Work"
    elif pct < 0.7: return "Fair"
    else:           return "Good"

def prompt(label, options=None, default=None):
    if options:
        print(f"\n  {label}")
        for i, o in enumerate(options, 1):
            print(f"    {i}. {o}")
        while True:
            try:
                val = int(input("    Enter number: ").strip())
                if 1 <= val <= len(options):
                    return val
            except ValueError:
                pass
            print("    Invalid. Try again.")
    else:
        suffix = f" [{default}]" if default else ""
        val = input(f"  {label}{suffix}: ").strip()
        return val if val else default

def clean_url(url):
    """Normalize URL for requests."""
    if not url:
        return None
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url
    return url

def divider(title=""):
    width = 55
    if title:
        pad = (width - len(title) - 2) // 2
        print(f"\n{'─'*pad} {title} {'─'*pad}")
    else:
        print(f"\n{'─'*width}")

# ── Auto-fetch Functions ──────────────────────────────────────────────────────
def check_website(url):
    """Check if website exists and is reachable."""
    if not url or url.lower() in ("none", "n", ""):
        return False, None, "No website provided"

    clean = clean_url(url)
    try:
        resp = requests.get(clean, headers=HEADERS, timeout=8, allow_redirects=True)
        if resp.status_code < 400:
            print(f"  ✓ Website reachable: {resp.url} (HTTP {resp.status_code})")
            return True, clean, resp.text
        else:
            print(f"  ✗ Website returned HTTP {resp.status_code}")
            return False, clean, None
    except requests.exceptions.SSLError:
        # Try http fallback
        try:
            clean_http = clean.replace("https://", "http://")
            resp = requests.get(clean_http, headers=HEADERS, timeout=8)
            return True, clean_http, resp.text
        except:
            return False, clean, None
    except Exception as e:
        print(f"  ✗ Could not reach website: {e}")
        return False, clean, None

def get_pagespeed_score(url):
    """Fetch mobile PageSpeed score from Google API."""
    if not url:
        return None, "No website"

    print("  Fetching PageSpeed score...", end=" ", flush=True)

    api_url = f"https://www.googleapis.com/pagespeedonline/v5/runPagespeed"
    params = {
        "url": url,
        "strategy": "mobile",
        "category": "performance",
    }
    if PAGESPEED_API_KEY:
        params["key"] = PAGESPEED_API_KEY

    try:
        resp = requests.get(api_url, params=params, timeout=20)
        data = resp.json()
        score = data.get("lighthouseResult", {}).get("categories", {}).get("performance", {}).get("score")
        if score is not None:
            pct = int(score * 100)
            print(f"{pct}/100")
            return pct, None
        else:
            error = data.get("error", {}).get("message", "Unknown error")
            print(f"API error: {error}")
            return None, error
    except Exception as e:
        print(f"Failed ({e})")
        return None, str(e)

def pagespeed_to_score(pct):
    """Convert 0-100 PageSpeed score to 1-5."""
    if pct is None:  return None
    if pct >= 90:    return 5
    elif pct >= 70:  return 4
    elif pct >= 50:  return 3
    elif pct >= 30:  return 2
    else:            return 1

def scrape_gbp_basics(business_name, city):
    """
    Scrape basic GBP info from Google search.
    Returns dict with rating, review_count, has_hours, has_photos (best effort).
    """
    print("  Fetching Google Business Profile data...", end=" ", flush=True)
    query = f"{business_name} {city}"
    search_url = f"https://www.google.com/search?q={requests.utils.quote(query)}"

    try:
        resp = requests.get(search_url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(resp.text, "html.parser")
        text = soup.get_text(" ", strip=True)

        # Extract rating (e.g. "4.9" or "4.9 stars")
        rating_match = re.search(r'\b([1-5]\.[0-9])\b', text[:3000])
        rating = rating_match.group(1) if rating_match else None

        # Extract review count (e.g. "692 reviews" or "(692)")
        review_match = re.search(r'[\(\s](\d{1,5})\s*(?:Google\s+)?reviews?\b', text[:3000], re.IGNORECASE)
        review_count = review_match.group(1) if review_match else None

        # Check for hours presence
        has_hours = bool(re.search(r'\b(open|closed|hours|AM|PM)\b', text[:3000], re.IGNORECASE))

        print(f"rating={rating or '?'}, reviews={review_count or '?'}")
        return {
            "rating": rating or "?",
            "review_count": review_count or "?",
            "has_hours": has_hours,
        }
    except Exception as e:
        print(f"Failed ({e})")
        return {"rating": "?", "review_count": "?", "has_hours": False}

def check_website_seo_basics(html, city, business_type):
    """
    Parse HTML to check basic SEO signals:
    - City name in title/h1/first paragraph
    - Service type mentioned
    - Mobile viewport tag
    - Phone number present
    Returns dict of findings.
    """
    if not html:
        return {}

    soup = BeautifulSoup(html, "html.parser")
    text_lower = soup.get_text(" ").lower()
    city_lower = city.lower().split(",")[0].strip()
    type_lower = business_type.lower().split()[0]

    title_tag   = soup.find("title")
    title_text  = title_tag.get_text().lower() if title_tag else ""
    h1_tags     = [h.get_text().lower() for h in soup.find_all("h1")]
    viewport    = soup.find("meta", attrs={"name": "viewport"})
    phone       = re.search(r'\(?\d{3}\)?[\s\-\.]\d{3}[\s\-\.]\d{4}', soup.get_text())

    city_in_title   = city_lower in title_text
    city_in_h1      = any(city_lower in h for h in h1_tags)
    city_in_content = city_lower in text_lower
    service_mentioned = type_lower in text_lower
    is_mobile_ready = viewport is not None
    has_phone       = phone is not None

    return {
        "city_in_title":    city_in_title,
        "city_in_h1":       city_in_h1,
        "city_in_content":  city_in_content,
        "service_mentioned":service_mentioned,
        "is_mobile_ready":  is_mobile_ready,
        "has_phone":        has_phone,
    }

def auto_website_score(site_exists, seo):
    """
    Derive a 1-5 website score from automated signals.
    Returns score and list of auto-detected issues.
    """
    if not site_exists:
        return 1, ["No website found"]

    issues = []
    score = 5

    if not seo.get("city_in_title"):
        score -= 0.5
        issues.append("City not in page title")
    if not seo.get("city_in_h1"):
        score -= 0.5
        issues.append("City not in main headline")
    if not seo.get("city_in_content"):
        score -= 1
        issues.append("City name not found in page content")
    if not seo.get("service_mentioned"):
        score -= 1
        issues.append("Service type not clearly mentioned on page")
    if not seo.get("is_mobile_ready"):
        score -= 1
        issues.append("No mobile viewport meta tag — may not be mobile friendly")
    if not seo.get("has_phone"):
        score -= 0.5
        issues.append("No phone number detected on page")

    return max(1, round(score)), issues

# ── Data Collection ───────────────────────────────────────────────────────────
def collect_data():
    print("\n" + "="*55)
    print("  QUESO VENTURES — SMART AUDIT GENERATOR")
    print("="*55)

    data = {}
    auto_findings = []  # findings detected automatically

    # ── Business Info ──────────────────────────────────────────────────────────
    divider("BUSINESS INFO")
    data["business_name"] = prompt("Business name")
    data["business_type"] = prompt("Business type (e.g. Auto Repair, Barber Shop)")
    data["business_city"] = prompt("City / Neighborhood (e.g. Humble, TX)")

    website_input = prompt("Website URL (or leave blank if none)", default="")
    data["has_website"] = bool(website_input and website_input.lower() not in ("none","n",""))
    data["website_url"] = website_input if data["has_website"] else "None"

    # ── Auto-fetch Phase ───────────────────────────────────────────────────────
    divider("AUTO-FETCHING DATA")

    # 1. Website check — with manual fallback
    site_exists, site_url, html = check_website(data["website_url"] if data["has_website"] else None)

    if data["has_website"] and not site_exists:
        print(f"  ✗ Could not reach site automatically.")
        manual_confirm = prompt("  Do you know the site exists? (y/n)", default="n").lower()
        if manual_confirm == "y":
            site_exists = True
            site_url    = clean_url(data["website_url"])
            html        = None
            print("  ✓ Marked as existing (manual confirm) — SEO checks skipped")

    data["has_website"] = site_exists

    # 2. SEO basics from HTML (only if we actually got the HTML)
    seo = check_website_seo_basics(html, data["business_city"], data["business_type"]) if html else {}
    auto_site_score, site_issues = auto_website_score(site_exists, seo)
    auto_findings.extend(site_issues)

    # 3. PageSpeed
    pagespeed_pct, ps_error = get_pagespeed_score(site_url) if site_exists else (None, "No website")
    auto_speed_score = pagespeed_to_score(pagespeed_pct)
    if pagespeed_pct is not None:
        if pagespeed_pct < 50:
            auto_findings.append(f"Mobile PageSpeed score is {pagespeed_pct}/100 — very slow, hurts rankings")
        elif pagespeed_pct < 70:
            auto_findings.append(f"Mobile PageSpeed score is {pagespeed_pct}/100 — needs improvement")

    # 4. GBP basics — try scraping, always fall back to manual
    gbp = scrape_gbp_basics(data["business_name"], data["business_city"])

    if gbp["rating"] == "?" or gbp["review_count"] == "?":
        print("  Could not scrape GBP data — enter manually.")
        print("  (Look at their Google listing in your browser)\n")
        data["review_rating"] = prompt("  Google star rating (e.g. 4.2, or 'none')", default="none")
        data["review_count"]  = prompt("  Number of Google reviews (or '0')", default="0")
    else:
        data["review_rating"] = gbp["rating"]
        data["review_count"]  = gbp["review_count"]

    # Print summary of what was auto-detected
    print("\n  Auto-detected:")
    print(f"    Website:      {'✓ Found' if site_exists else '✗ Not found'}")
    if site_exists and html:
        print(f"    PageSpeed:    {pagespeed_pct if pagespeed_pct else 'Could not fetch (quota or no key)'}")
        print(f"    City in title:{'✓' if seo.get('city_in_title') else '✗'}")
        print(f"    Mobile ready: {'✓' if seo.get('is_mobile_ready') else '✗'}")
        print(f"    Phone on site:{'✓' if seo.get('has_phone') else '✗'}")
    elif site_exists:
        print(f"    PageSpeed:    {pagespeed_pct if pagespeed_pct else 'Could not fetch (quota or no key)'}")
        print(f"    SEO checks:   Skipped (site confirmed manually)")
    print(f"    Rating:       {data['review_rating']}")
    print(f"    Reviews:      {data['review_count']}")

    # ── Competitor ─────────────────────────────────────────────────────────────
    divider("COMPETITOR")
    print(f"  Search Google for: \"{data['business_type']} {data['business_city']}\"")
    print("  Find the top map result that isn't this business.")
    print("  Leave blank and hit Enter to skip any field.\n")
    data["comp_name"]     = prompt("Competitor name", default="N/A")
    data["comp_reviews"]  = prompt("Competitor review count", default="N/A")
    data["comp_rating"]   = prompt("Competitor star rating", default="N/A")
    data["comp_has_site"] = prompt("Competitor has website? (y/n)", default="y").lower() == "y"

    # ── Manual Scores ──────────────────────────────────────────────────────────
    divider("SCORING")

    score_opts = ["1 - Very Poor", "2 - Poor", "3 - Fair", "4 - Good", "5 - Excellent"]

    # Website score — use auto if available, let them override
    if auto_site_score and site_exists:
        print(f"\n  Website Quality — auto-detected score: {auto_site_score}/5")
        override = prompt("  Override? (leave blank to accept)", default="")
        data["website_score"] = int(override) if override.isdigit() else auto_site_score
    elif not site_exists:
        data["website_score"] = 1
        print(f"\n  Website Quality — set to 1 (no website found)")
    else:
        data["website_score"] = prompt("Website Quality\n   (Does it exist? Clear content, mentions city+service?)", options=score_opts)

    # Speed score — use auto if available
    if auto_speed_score:
        print(f"\n  Mobile Page Speed — auto-detected score: {auto_speed_score}/5 ({pagespeed_pct}/100)")
        override = prompt("  Override? (leave blank to accept)", default="")
        data["speed_score"] = int(override) if override.isdigit() else auto_speed_score
    elif not site_exists:
        data["speed_score"] = 1
        print(f"\n  Mobile Page Speed — set to 1 (no website found)")
    else:
        print(f"\n  Mobile Page Speed — could not auto-fetch")
        if not PAGESPEED_API_KEY:
            print("  Tip: Add a free PageSpeed API key to enable auto-scoring")
            print("  Get one at: https://developers.google.com/speed/docs/insights/v5/get-started")
        data["speed_score"] = prompt("  Score manually", options=score_opts)

    # GBP — manual, but give them context
    print(f"\n  Google Business Profile")
    print(f"  Check: photos, services listed, description written, posts, correct hours")
    data["gbp_score"] = prompt("  Score", options=score_opts)

    # Visibility — manual
    print(f"\n  Local Search Visibility")
    print(f"  Search: \"{data['business_type']} {data['business_city']}\" — are they in the top 3 map results?")
    data["visibility_score"] = prompt("  Score", options=score_opts)

    # GEO — manual
    print(f"\n  GEO / AI Search Readiness")
    print(f"  Ask ChatGPT: \"best {data['business_type']} in {data['business_city']}\" — do they appear?")
    data["geo_score"] = prompt("  Score", options=score_opts)

    # ── Findings ───────────────────────────────────────────────────────────────
    divider("FINDINGS")

    # Show auto-detected findings
    if auto_findings:
        print("\n  Auto-detected issues (will be included automatically):")
        for f in auto_findings:
            print(f"    → {f}")

    print("\n  Add your own findings (press Enter twice when done):")
    manual_findings = []
    while True:
        line = input("  > ").strip()
        if line == "" and (not manual_findings or manual_findings[-1] == ""):
            break
        if line:
            manual_findings.append(line)

    data["findings"] = auto_findings + manual_findings

    # ── Recommendations ────────────────────────────────────────────────────────
    divider("RECOMMENDATIONS")
    print("  Enter top 3 recommendations:\n")
    data["recommendations"] = []
    for i in range(1, 4):
        r = prompt(f"  Recommendation {i}")
        if r:
            data["recommendations"].append(r)

    data["auditor_name"] = prompt("\nYour name", default="Queso Ventures")
    data["audit_date"]   = date.today().strftime("%B %d, %Y")

    return data

# ── PDF Builder (same as before, clean version) ───────────────────────────────
def build_pdf(data, output_path):
    doc = SimpleDocTemplate(
        output_path,
        pagesize=letter,
        leftMargin=0.6*inch,
        rightMargin=0.6*inch,
        topMargin=0.5*inch,
        bottomMargin=0.6*inch,
    )

    W = letter[0] - 1.2*inch

    def style(name, **kwargs):
        return ParagraphStyle(name, **kwargs)

    s_header_name = style("HN", fontSize=22, textColor=WHITE,     fontName="Helvetica-Bold", leading=26)
    s_header_sub  = style("HS", fontSize=11, textColor=YELLOW,    fontName="Helvetica",      leading=16)
    s_section     = style("SC", fontSize=11, textColor=DARK,      fontName="Helvetica-Bold", leading=16, spaceBefore=14)
    s_body        = style("BD", fontSize=9,  textColor=TEXT_GRAY, fontName="Helvetica",      leading=14)
    s_small       = style("SM", fontSize=8,  textColor=TEXT_GRAY, fontName="Helvetica",      leading=12)
    s_footer      = style("FT", fontSize=8,  textColor=MID_GRAY,  fontName="Helvetica",      alignment=TA_CENTER)
    s_rec_num     = style("RN", fontSize=13, textColor=YELLOW,    fontName="Helvetica-Bold", alignment=TA_CENTER)
    s_rec_text    = style("RT", fontSize=9,  textColor=TEXT_GRAY, fontName="Helvetica",      leading=14)
    s_cat_name    = style("CN", fontSize=9,  textColor=DARK,      fontName="Helvetica-Bold", leading=13)

    story = []

    # Header
    header_data = [[
        Paragraph(data["business_name"], s_header_name),
        Paragraph("QUESO VENTURES", style("QV", fontSize=10, textColor=YELLOW, fontName="Helvetica-Bold", alignment=TA_RIGHT)),
    ],[
        Paragraph(f"{data['business_type']}  ·  {data['business_city']}", s_header_sub),
        Paragraph(f"SEO & GEO Audit\n{data['audit_date']}", style("AD", fontSize=8, textColor=MID_GRAY, fontName="Helvetica", alignment=TA_RIGHT, leading=13)),
    ]]
    header_table = Table(header_data, colWidths=[W*0.65, W*0.35])
    header_table.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (-1,-1), DARK),
        ("TOPPADDING",    (0,0), (-1,-1), 14),
        ("BOTTOMPADDING", (0,0), (-1,-1), 14),
        ("LEFTPADDING",   (0,0), (-1,-1), 16),
        ("RIGHTPADDING",  (0,0), (-1,-1), 16),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("ROUNDEDCORNERS", [6]),
    ]))
    story.append(header_table)
    story.append(Spacer(1, 16))

    # Overview bar
    total_score = sum([data[k] for k in ["website_score","speed_score","gbp_score","visibility_score","geo_score"]])
    total_pct   = int((total_score / 25) * 100)
    overall_col = score_color(total_score, 25)

    overview_data = [[
        Paragraph(f"<b>{total_pct}%</b>",                          style("TP", fontSize=28, textColor=WHITE,     fontName="Helvetica-Bold", alignment=TA_CENTER)),
        Paragraph(f"<b>{data['review_rating']} ★</b>",             style("RR", fontSize=18, textColor=DARK,      fontName="Helvetica-Bold", alignment=TA_CENTER)),
        Paragraph(f"<b>{data['review_count']}</b>",                 style("RC", fontSize=18, textColor=DARK,      fontName="Helvetica-Bold", alignment=TA_CENTER)),
        Paragraph(f"<b>{'✓ Yes' if data['has_website'] else '✗ No'}</b>", style("WS", fontSize=16, textColor=DARK, fontName="Helvetica-Bold", alignment=TA_CENTER)),
    ],[
        Paragraph("Overall Score",  style("L1", fontSize=8, textColor=YELLOW,    fontName="Helvetica-Bold", alignment=TA_CENTER)),
        Paragraph("Google Rating",  style("L2", fontSize=8, textColor=TEXT_GRAY, fontName="Helvetica",      alignment=TA_CENTER)),
        Paragraph("Reviews",        style("L3", fontSize=8, textColor=TEXT_GRAY, fontName="Helvetica",      alignment=TA_CENTER)),
        Paragraph("Has Website",    style("L4", fontSize=8, textColor=TEXT_GRAY, fontName="Helvetica",      alignment=TA_CENTER)),
    ]]
    col_w = W / 4
    overview_table = Table(overview_data, colWidths=[col_w]*4, rowHeights=[36, 20])
    overview_table.setStyle(TableStyle([
        ("BACKGROUND",    (0,0), (0,-1), overall_col),
        ("BACKGROUND",    (1,0), (-1,-1), LIGHT_GRAY),
        ("TOPPADDING",    (0,0), (-1,-1), 8),
        ("BOTTOMPADDING", (0,0), (-1,-1), 6),
        ("LEFTPADDING",   (0,0), (-1,-1), 6),
        ("RIGHTPADDING",  (0,0), (-1,-1), 6),
        ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
        ("LINEAFTER",     (0,0), (2,1),   0.5, MID_GRAY),
        ("ROUNDEDCORNERS", [4]),
    ]))
    story.append(overview_table)
    story.append(Spacer(1, 18))

    # Score breakdown
    story.append(Paragraph("Score Breakdown", s_section))
    story.append(Spacer(1, 6))

    categories = [
        ("website_score",    "Website Quality",         "Existence, clarity, mobile-ready, city+service mentions"),
        ("speed_score",      "Mobile Page Speed",       "Google PageSpeed Insights score on mobile"),
        ("gbp_score",        "Google Business Profile", "Photos, hours, description, services, posts"),
        ("visibility_score", "Local Search Visibility", "Appears in top 3 map pack results"),
        ("geo_score",        "GEO / AI Readiness",      "Appears in ChatGPT / Perplexity results"),
    ]

    for key, name, note in categories:
        sc       = data[key]
        sc_color = score_color(sc)
        sc_text  = score_label(sc)

        bar_cells = []
        for i in range(1, 6):
            bar_cells.append(
                Table([[" "]], colWidths=[W*0.07], rowHeights=[10],
                      style=TableStyle([("BACKGROUND",(0,0),(0,0), sc_color if i <= sc else MID_GRAY)]))
            )

        row = Table([[
            Paragraph(f"<b>{name}</b><br/><font size='7' color='#999999'>{note}</font>", s_cat_name),
            Table([bar_cells], colWidths=[W*0.07]*5, rowHeights=[10]),
            Paragraph(f"<b>{sc}/5</b>", style(f"SC{key}", fontSize=11, textColor=sc_color, fontName="Helvetica-Bold", alignment=TA_CENTER)),
            Paragraph(sc_text, style(f"SL{key}", fontSize=8, textColor=sc_color, fontName="Helvetica-Bold")),
        ]], colWidths=[W*0.38, W*0.38, W*0.12, W*0.12])
        row.setStyle(TableStyle([
            ("BACKGROUND",    (0,0), (-1,-1), WHITE),
            ("TOPPADDING",    (0,0), (-1,-1), 9),
            ("BOTTOMPADDING", (0,0), (-1,-1), 9),
            ("LEFTPADDING",   (0,0), (-1,-1), 10),
            ("RIGHTPADDING",  (0,0), (-1,-1), 10),
            ("VALIGN",        (0,0), (-1,-1), "MIDDLE"),
            ("BOX",           (0,0), (-1,-1), 0.5, MID_GRAY),
            ("ROUNDEDCORNERS", [4]),
        ]))
        story.append(row)
        story.append(Spacer(1, 5))

    story.append(Spacer(1, 10))

    # Competitor table
    story.append(Paragraph("Competitor Comparison", s_section))
    story.append(Spacer(1, 6))

    comp_rows = [
        ["", f"<b>{data['business_name']}</b>",    f"<b>{data['comp_name']}</b>"],
        ["Google Rating",  data["review_rating"],   data["comp_rating"]],
        ["Review Count",   data["review_count"],    data["comp_reviews"]],
        ["Has Website",    "Yes" if data["has_website"] else "No", "Yes" if data["comp_has_site"] else "No"],
    ]

    comp_table_data = []
    for i, row in enumerate(comp_rows):
        comp_table_data.append([
            Paragraph(row[0], s_small if i > 0 else s_small),
            Paragraph(row[1], style(f"CT1{i}", fontSize=9, textColor=DARK, fontName="Helvetica-Bold" if i==0 else "Helvetica", alignment=TA_CENTER)),
            Paragraph(row[2], style(f"CT2{i}", fontSize=9, textColor=DARK, fontName="Helvetica-Bold" if i==0 else "Helvetica", alignment=TA_CENTER)),
        ])

    comp_table = Table(comp_table_data, colWidths=[W*0.35, W*0.325, W*0.325])
    comp_table.setStyle(TableStyle([
        ("BACKGROUND",     (0,0), (-1,0),  DARK),
        ("TEXTCOLOR",      (0,0), (-1,0),  WHITE),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [WHITE, LIGHT_GRAY]),
        ("BACKGROUND",     (1,1), (1,-1),  WHITE),
        ("TOPPADDING",     (0,0), (-1,-1), 8),
        ("BOTTOMPADDING",  (0,0), (-1,-1), 8),
        ("LEFTPADDING",    (0,0), (-1,-1), 10),
        ("RIGHTPADDING",   (0,0), (-1,-1), 10),
        ("VALIGN",         (0,0), (-1,-1), "MIDDLE"),
        ("LINEAFTER",      (0,0), (1,-1),  0.5, MID_GRAY),
        ("BOX",            (0,0), (-1,-1), 0.5, MID_GRAY),
        ("ROUNDEDCORNERS", [4]),
    ]))
    story.append(comp_table)
    story.append(Spacer(1, 18))

    # Findings
    if data["findings"]:
        story.append(Paragraph("Key Findings", s_section))
        story.append(Spacer(1, 6))
        for finding in data["findings"]:
            row = Table([[
                Paragraph("→", style("AR", fontSize=10, textColor=YELLOW, fontName="Helvetica-Bold")),
                Paragraph(finding, s_body),
            ]], colWidths=[0.25*inch, W - 0.25*inch])
            row.setStyle(TableStyle([
                ("VALIGN",        (0,0), (-1,-1), "TOP"),
                ("TOPPADDING",    (0,0), (-1,-1), 3),
                ("BOTTOMPADDING", (0,0), (-1,-1), 3),
            ]))
            story.append(row)
        story.append(Spacer(1, 14))

    # Recommendations
    if data["recommendations"]:
        story.append(Paragraph("Top Recommendations", s_section))
        story.append(Spacer(1, 8))

        rec_cells = []
        n = len(data["recommendations"])
        for i, rec in enumerate(data["recommendations"], 1):
            cell = Table([[Paragraph(str(i), s_rec_num)],[Paragraph(rec, s_rec_text)]],
                         colWidths=[(W/n) - 8])
            cell.setStyle(TableStyle([
                ("BACKGROUND",    (0,0), (0,0), DARK),
                ("BACKGROUND",    (0,1), (0,1), LIGHT_GRAY),
                ("TOPPADDING",    (0,0), (-1,-1), 10),
                ("BOTTOMPADDING", (0,0), (-1,-1), 10),
                ("LEFTPADDING",   (0,0), (-1,-1), 10),
                ("RIGHTPADDING",  (0,0), (-1,-1), 10),
                ("ROUNDEDCORNERS", [4]),
            ]))
            rec_cells.append(cell)

        rec_row = Table([rec_cells], colWidths=[(W/n) - 4]*n)
        rec_row.setStyle(TableStyle([
            ("LEFTPADDING",  (0,0), (-1,-1), 4),
            ("RIGHTPADDING", (0,0), (-1,-1), 4),
        ]))
        story.append(rec_row)
        story.append(Spacer(1, 20))

    # Footer
    story.append(HRFlowable(width=W, thickness=0.5, color=MID_GRAY))
    story.append(Spacer(1, 8))
    story.append(Paragraph(
        f"Prepared by {data['auditor_name']}  ·  quesoventures.com  ·  {data['audit_date']}  ·  Confidential",
        s_footer
    ))

    doc.build(story)

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    data = collect_data()

    safe_name = data["business_name"].replace(" ", "_").replace("/", "-").lower()
    filename  = f"audit_{safe_name}_{date.today().strftime('%Y%m%d')}.pdf"

    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    output  = os.path.join(desktop if os.path.exists(desktop) else os.getcwd(), filename)

    print(f"\n  Generating PDF...", end=" ", flush=True)
    build_pdf(data, output)
    print(f"done.")
    print(f"\n  ✓ Saved to: {output}\n")

if __name__ == "__main__":
    main()