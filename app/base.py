"""Base class every marketplace plugin extends."""
import json
import re
import threading
from math import ceil
from pathlib import Path


def parse_price(value):
    """'₹45,990' / '45990.00' / 45990 -> 45990.0 (None if unparseable)."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    cleaned = re.sub(r"[^\d.]", "", str(value))
    try:
        return float(cleaned)
    except ValueError:
        return None


def dig(obj, path):
    """Read 'a.b.c' from nested dicts; None if any step is missing."""
    for key in path.split("."):
        if not isinstance(obj, dict) or key not in obj:
            return None
        obj = obj[key]
    return obj


_UNIT = re.compile(r"(\d)\s+(gb|tb|mb|inch|inches|mp|hz|w|mah|k)\b")


def compact(text):
    """Lower-case and glue numbers to units so '16 GB' == '16gb'."""
    return _UNIT.sub(r"\1\2", (text or "").lower())


def pages(total, page_size):
    return max(1, ceil(total / page_size))


class Marketplace:
    # ---- override these in each marketplace's marketplace.py ----
    name = ""                 # URL slug, e.g. "amazon"
    display_name = ""
    enabled = True            # set False to hide without deleting the folder
    latency_ms = (0, 0)       # simulated response delay (min, max)
    error_rate = 0.0          # probability of a simulated 503

    # Searchable/filterable fields: {name: "dotted.path.in.raw.record"}.
    # Required: id, title, price. Everything else is optional; ANY extra name you add
    # here (e.g. "rating": "rating.stars") becomes filterable as ?rating=4.1,
    # ?min_rating=4, ?max_rating=4.5 with no other code changes.
    field_map = {}

    def fields(self, raw: dict) -> dict:
        out = {k: dig(raw, path) for k, path in self.field_map.items()}
        out["price"] = parse_price(out.get("price"))
        return out

    def envelope(self, items: list, total: int, page: int, page_size: int) -> dict:
        """Wrap a page of RAW records in this marketplace's own response shape."""
        raise NotImplementedError

    def detail(self, raw: dict) -> dict:
        """Response for a single listing (default: the raw record)."""
        return raw

    # ---- shared machinery (no need to touch) ----
    def __init__(self, folder: Path):
        self.folder = folder
        self.data_file = folder / "data.json"
        self._lock = threading.Lock()
        self.records = []
        self.load()

    def load(self):
        self.records = (
            json.loads(self.data_file.read_text(encoding="utf-8"))
            if self.data_file.exists() else []
        )

    def save(self):
        self.data_file.write_text(
            json.dumps(self.records, indent=2, ensure_ascii=False), encoding="utf-8")

    def search(self, q=None, extra=None, match="all"):
        """extra: dict of query params. name=value -> match; min_name/max_name -> range.
        match="all": every word must be in the title (strict).
        match="any": at least one word, results ranked by how many words matched (like a real search API)."""
        extra = extra or {}
        tokens = [t.rstrip("s") if len(t) > 3 else t for t in compact(q).split()]
        scored = []
        for raw in self.records:
            f = self.fields(raw)
            hay = compact(f"{f.get('title','')} {f.get('category','')} {f.get('brand','')}")
            hits = [bool(re.search(r"\b" + re.escape(t), hay)) for t in tokens]
            if tokens and not (all(hits) if match == "all" else any(hits)):
                continue
            if all(self._match(f, k, v) for k, v in extra.items()):
                scored.append((sum(hits), raw))
        if tokens and match == "any":
            scored.sort(key=lambda x: -x[0])      # stable: ties keep data order
        return [raw for _, raw in scored]

    @staticmethod
    def _match(f, key, value):
        for prefix, op in (("min_", float.__ge__), ("max_", float.__le__)):
            if key.startswith(prefix) and key[len(prefix):] in f:
                have = parse_price(f[key[len(prefix):]])
                try:
                    return have is not None and op(have, float(value))
                except ValueError:
                    return True
        if key not in f:
            return True            # unknown params are ignored
        have = f[key]
        if have is None:
            return False
        if isinstance(have, bool):
            return str(have).lower() == value.lower()
        if key in ("id", "category"):                      # exact match (plural-insensitive)
            return str(have).lower().rstrip("s") == value.lower().rstrip("s")
        return value.lower() in str(have).lower()

    def get(self, listing_id):
        for raw in self.records:
            if str(self.fields(raw)["id"]) == str(listing_id):
                return raw
        return None

    def add(self, new_records: list):
        """Insert or update (matched by id). Persists to data.json."""
        added = updated = 0
        with self._lock:
            index = {str(self.fields(r)["id"]): i for i, r in enumerate(self.records)}
            for raw in new_records:
                key = str(self.fields(raw)["id"])
                if key in index:
                    self.records[index[key]] = raw
                    updated += 1
                else:
                    self.records.append(raw)
                    index[key] = len(self.records) - 1
                    added += 1
            self.save()
        return added, updated
