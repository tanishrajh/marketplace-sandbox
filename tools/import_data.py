"""Bulk-add raw records to a marketplace:  python tools/import_data.py amazon my_scrape.json
Records must be in that marketplace's native format (see its data.json). Matched by id."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.registry import discover  # noqa: E402

name, file = sys.argv[1], sys.argv[2]
markets = discover(Path(__file__).resolve().parent.parent / "marketplaces")
added, updated = markets[name].add(json.loads(Path(file).read_text(encoding="utf-8")))
print(f"{name}: added {added}, updated {updated}, total {len(markets[name].records)}")
