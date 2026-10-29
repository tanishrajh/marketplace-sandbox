import asyncio
import os
import random
from pathlib import Path
from typing import List, Optional

from fastapi.staticfiles import StaticFiles
from fastapi import Body, FastAPI, HTTPException, Query, Request

from app.registry import discover

BASE = Path(__file__).resolve().parent.parent
CHAOS_ENABLED = os.getenv("CHAOS", "1") != "0"   # CHAOS=0 turns off delays/errors

app = FastAPI(title="Marketplace Sandbox", description="Mock third-party marketplace APIs for demo use.")
markets = discover(BASE / "marketplaces")
for _m in markets.values():                       # optional product images: marketplaces/<m>/images/
    if (_m.folder / "images").is_dir():
        app.mount(f"/static/{_m.name}", StaticFiles(directory=_m.folder / "images"), name=f"img_{_m.name}")


def get_market(name: str):
    m = markets.get(name)
    if not m:
        raise HTTPException(404, f"Unknown marketplace '{name}'. Available: {list(markets)}")
    return m


async def chaos(m):
    if not CHAOS_ENABLED:
        return
    lo, hi = m.latency_ms
    if hi > 0:
        await asyncio.sleep(random.uniform(lo, hi) / 1000)
    if m.error_rate and random.random() < m.error_rate:
        raise HTTPException(503, f"{m.display_name} temporarily unavailable (simulated)")


@app.get("/")
def index():
    return [{"name": m.name, "display_name": m.display_name, "listings": len(m.records),
             "latency_ms": m.latency_ms, "error_rate": m.error_rate} for m in markets.values()]


@app.get("/health")
def health():
    return {"status": "ok", "marketplaces": list(markets), "chaos": CHAOS_ENABLED}


@app.get("/{market}/listings")
async def search(market: str, request: Request, q: Optional[str] = None,
                 page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
                 match: str = Query("all", pattern="^(all|any)$")):
    """Also accepts any field from the marketplace's field_map as a filter,
    e.g. ?category=laptops&brand=HP&min_price=30000&max_price=60000&min_rating=4
    match=any returns results ranked by how many query words matched (default: all words required)."""
    m = get_market(market)
    await chaos(m)
    extra = {k: v for k, v in request.query_params.items()
             if k not in ("q", "page", "page_size", "match")}
    hits = m.search(q, extra, match)
    start = (page - 1) * page_size
    return m.envelope(hits[start:start + page_size], len(hits), page, page_size)


@app.get("/{market}/listings/{listing_id}")
async def detail(market: str, listing_id: str):
    m = get_market(market)
    await chaos(m)
    raw = m.get(listing_id)
    if raw is None:
        raise HTTPException(404, "Listing not found")
    return m.detail(raw)


# ---------- admin / data management ----------
@app.post("/{market}/listings")
def add_listings(market: str, records: List[dict] = Body(...)):
    """Add or update listings in the marketplace's NATIVE raw format (matched by id)."""
    m = get_market(market)
    try:
        added, updated = m.add(records)
    except KeyError as e:
        raise HTTPException(422, f"Record missing field {e} required by {market}'s format")
    return {"added": added, "updated": updated, "total": len(m.records)}


@app.post("/admin/reload")
def reload_data():
    for m in markets.values():
        m.load()
    return {m.name: len(m.records) for m in markets.values()}


@app.post("/admin/chaos/{market}")
def set_chaos(market: str, latency_ms: List[int] = Body([0, 0]), error_rate: float = Body(0.0)):
    """Change a marketplace's simulated delay/failure at runtime (handy for the timeout demo)."""
    m = get_market(market)
    m.latency_ms = (latency_ms[0], latency_ms[1])
    m.error_rate = error_rate
    return {"market": market, "latency_ms": m.latency_ms, "error_rate": m.error_rate}
