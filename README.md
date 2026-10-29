# Marketplace Sandbox

Mock third-party marketplace APIs (Amazon, Flipkart, ...) for the SecondHand aggregator demo.
Each marketplace has its **own data and its own response format**, like real, separate APIs.
Demo use only. Data is a snapshot (laptops from Amazon.in and Flipkart pages saved on 28 Oct 2026).

## Run
```bash
pip install -r requirements.txt
uvicorn app.main:app --port 9000        # docs at http://localhost:9000/docs
# CHAOS=0 uvicorn ...                   # disable simulated delays/errors
```

## API
| Endpoint | Purpose |
|---|---|
| `GET /` | list marketplaces + listing counts |
| `GET /{market}/listings?q=&match=all\|any&page=&page_size=` + any `field_map` field, e.g. `&brand=hp&min_price=30000&max_rating=4.5&sponsored=false` | search |
| `GET /{market}/listings/{id}` | one listing |
| `POST /{market}/listings` | add/update listings (raw native format, JSON array) |
| `POST /admin/reload` | re-read all data.json files |
| `POST /admin/chaos/{market}` | body `{"latency_ms":[3000,5000],"error_rate":0.3}` for timeout demo |

`match=all` (default) needs every word in the title; `match=any` returns candidates ranked by how many words matched
(what the aggregator uses). Numbers and units are tolerant: `16 gb` finds `16GB`.

## Add data from saved pages
```bash
pip install -r requirements-tools.txt
python tools/extract_html.py amazon   "Amazon.in _ phones.html"  --category phones
python tools/extract_html.py flipkart "Phones - Flipkart.html"   --category phones
```
Save pages with Ctrl+S "Webpage, Complete" after scrolling to the bottom. Records merge into
`data.json` by id, so repeat for more pages/categories. Add `--files-dir "<page>_files"` to copy
product images (served at `/static/<market>/<file>`), `--dry-run` to preview.
Restart the server (or `POST /admin/reload`) afterwards.
Other ways: edit `data.json` directly, `python tools/import_data.py <market> file.json`, or `POST /{market}/listings`.

## Add a new field
- **Just store it:** put any new key in the records (or add it in the extractor). The API returns raw records as-is, so it appears immediately.
- **Make it filterable:** add one line to `field_map` in that marketplace's `marketplace.py`, e.g. `"ram": "specs.ram"`.
  Then `?ram=16`, `?min_rating=4`, `?max_price=50000` etc. work with no other code.

## Add a marketplace (e.g. Myntra)
1. Create `marketplaces/myntra/` with `data.json` (your raw records).
2. Create `marketplaces/myntra/marketplace.py`: copy `flipkart/marketplace.py` and change
   `name`, `field_map` (your raw field paths) and `envelope()` (response shape).
3. For HTML import, add an `extract_myntra` function to `tools/extract_html.py` and register it in `EXTRACTORS`.
4. Restart. It is auto-discovered at `/myntra/listings`.

## Remove / disable a marketplace
Delete its folder, or set `enabled = False` in its `marketplace.py`. Restart.
