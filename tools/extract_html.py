"""Turn a saved marketplace search-results page into raw records for the sandbox.

  python tools/extract_html.py amazon   "Amazon.in _ laptop.html" --category laptops
  python tools/extract_html.py flipkart "Laptop - Flipkart.html"  --category laptops
  options: --files-dir "<saved page>_files"  copy product images into marketplaces/<m>/images
           --dry-run                          print a sample instead of saving

Records are MERGED into marketplaces/<m>/data.json (matched by id), so you can run it on
many pages/categories. To support a new marketplace: write one function like extract_amazon
below and register it in EXTRACTORS (it should return a list of dicts in that marketplace's
native format).
"""
import argparse
import unicodedata
import json
import re
import shutil
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from bs4 import BeautifulSoup

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

# Text injected by browser extensions (price-history overlays etc.). Everything after is ignored.
NOISE_MARKERS = ("Deal Mirage",)


def clean_strings(tag):
    out = []
    for s in tag.stripped_strings:
        if any(m in s for m in NOISE_MARKERS):
            break
        out.append(s)
    return out


def num(text, as_int=False):
    m = re.search(r"\d[\d,]*\.?\d*", text or "")
    if not m:
        return None
    v = float(m.group().replace(",", ""))
    return int(v) if as_int else v


def brand_of(title):
    title = unicodedata.normalize("NFKC", title or "")      # fancy unicode lettering -> plain
    title = re.sub(r"(?i)^(\w+?)laptop\b", r"\1 laptop", title)
    first = re.split(r"[\s,]", title.strip())[0] if title else None
    return first.title() if first and first.isupper() and len(first) > 3 else first


def first_url(srcset):
    return srcset.split(",")[0].split()[0] if srcset else None


# ----------------------------------------------------------------- Amazon
def extract_amazon(soup, category):
    records = []
    for card in soup.select('div[data-component-type="s-search-result"]'):
        asin = card.get("data-asin")
        h2 = card.select_one("h2")
        if not asin or not h2:
            continue
        strings = clean_strings(card)
        title = h2.get("aria-label") or h2.get_text(strip=True)
        title = re.sub(r"^Sponsored Ad\s*-\s*", "", title)
        price = card.select_one("span.a-price:not(.a-text-price) span.a-offscreen")
        mrp = card.select_one("span.a-price.a-text-price span.a-offscreen")
        stars = card.select_one("span.a-icon-alt")
        ratings_link = card.select_one('a[aria-label*="ratings"]')
        text = " ".join(strings)
        delivery = card.select_one('[data-cy="delivery-recipe"]')
        img = card.select_one("img.s-image")
        offers = [s for s in strings if re.search(
            r"(?i)(back with|% off on|cashback|coupon|no.cost emi|bank offer)", s)
            and not re.match(r"\(\d+% off\)", s)]
        records.append({
            "asin": asin,
            "title": title,
            "brand": brand_of(title),
            "category": category,
            "price": price.get_text(strip=True) if price else None,
            "list_price": mrp.get_text(strip=True) if mrp else None,
            "discount": (re.search(r"\((\d+% off)\)", text) or [None, None])[1],
            "rating": {
                "stars": num(stars.get_text()) if stars else None,
                "count": num(ratings_link["aria-label"], True) if ratings_link else None,
            },
            "bought_past_month": next((s for s in strings if "bought in past month" in s), None),
            "sponsored": "Sponsored" in strings,
            "prime": bool(card.select_one("i.a-icon-prime")),
            "delivery": re.split(r"Service:", delivery.get_text(" ", strip=True))[0].strip() if delivery else None,
            "offers": [o for o in dict.fromkeys(offers)
                       if not (o.endswith("...") and any(x != o and x.startswith(o[:-3]) for x in offers))],
            "image": first_url(img.get("srcset")) if img else None,
            "image_file": Path(img["src"]).name if img and img.get("src") else None,
            "url": f"https://www.amazon.in/dp/{asin}",
        })
    return records


# ----------------------------------------------------------------- Flipkart
def extract_flipkart(soup, category):
    cards = {}
    for c in soup.select("div[data-id]"):
        cards.setdefault(c["data-id"], c)       # page repeats some ids
    records = []
    for pid, card in cards.items():
        link = card.select_one('a[href*="/p/itm"]')
        imgs = [i for i in card.select("img") if i.get("src", "").startswith(".") or i.get("src", "").startswith("http")
                and "chrome-extension" not in i.get("src", "")]
        img = next((i for i in imgs if i.get("alt")), imgs[0] if imgs else None)
        if not link or not img:
            continue
        strings = clean_strings(card)
        url = urlparse(link["href"])
        rupee = [i for i, s in enumerate(strings) if s.startswith("₹")]
        price = strings[rupee[0]] if rupee else None
        mrp = discount = None
        for i in rupee[1:]:
            if i + 1 < len(strings) and re.match(r"\d+% off", strings[i + 1]):
                mrp, discount = strings[i], strings[i + 1]
                break
        exchange = next((strings[i + 1] for i, s in enumerate(strings)
                         if s == "Upto" and i + 1 < len(strings)), None)
        rating = next((s for s in strings if re.fullmatch(r"\d\.\d", s)), None)
        ratings_txt = next((s for s in strings if s.endswith(" Ratings")), None)
        reviews_txt = next((s for s in strings if s.endswith(" Reviews")), None)
        name = img.get("alt") or next(
            (x for x in strings if x != "Add to Compare" and not x.startswith("₹") and len(x) > 12),
            link["href"].split("/")[3].replace("-", " ").title())
        records.append({
            "productId": parse_qs(url.query).get("pid", [pid])[0],
            "name": name,
            "brand": brand_of(name),
            "vertical": category,
            "pricing": {"sellingPrice": num(price, True) if price else None,
                        "mrp": num(mrp, True) if mrp else None,
                        "discountPct": num(discount, True) if discount else None},
            "ratings": {"average": float(rating) if rating else None,
                        "totalCount": num(ratings_txt, True) if ratings_txt else None,
                        "reviewCount": num(reviews_txt, True) if reviews_txt else None},
            "specs": [li.get_text(strip=True) for li in card.select("li")],
            "exchangeOfferUpto": num(exchange, True) if exchange else None,
            "bankOffer": "Bank Offer" in strings,
            "fAssured": any("/fa_" in (i.get("src") or "") for i in card.select("img")),
            "sponsored": "Ad" in strings or "Sponsored" in strings,
            "image_file": Path(img["src"]).name if img.get("src") else None,
            "productUrl": f"https://www.flipkart.com{url.path}?pid={parse_qs(url.query).get('pid', [pid])[0]}",
        })
    return records


EXTRACTORS = {"amazon": extract_amazon, "flipkart": extract_flipkart}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("marketplace", choices=EXTRACTORS)
    ap.add_argument("html")
    ap.add_argument("--category", required=True)
    ap.add_argument("--files-dir")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    soup = BeautifulSoup(Path(a.html).read_text(encoding="utf-8", errors="ignore"), "lxml")
    records = EXTRACTORS[a.marketplace](soup, a.category)
    skipped = [r for r in records if not (r.get("price") or r.get("pricing", {}).get("sellingPrice"))]
    records = [r for r in records if r not in skipped]
    if skipped:
        print(f"Skipped {len(skipped)} listing(s) with no price (unavailable).")

    if a.files_dir:
        dest = ROOT / "marketplaces" / a.marketplace / "images"
        dest.mkdir(exist_ok=True)
        for r in records:
            src = Path(a.files_dir) / (r.get("image_file") or "")
            if r.get("image_file") and src.exists():
                shutil.copy(src, dest / src.name)
                r["image_local"] = f"/static/{a.marketplace}/{src.name}"

    missing = [r for r in records if not (r.get("price") or r.get("pricing", {}).get("sellingPrice"))]
    print(f"Extracted {len(records)} listings ({len(missing)} without a price).")
    if a.dry_run:
        print(json.dumps(records[:2], indent=2, ensure_ascii=False))
        return
    from app.registry import discover
    market = discover(ROOT / "marketplaces")[a.marketplace]
    added, updated = market.add(records)
    print(f"{a.marketplace}: added {added}, updated {updated}, total {len(market.records)}")


if __name__ == "__main__":
    main()
