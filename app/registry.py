"""Auto-discovers marketplaces: any folder in /marketplaces with a marketplace.py."""
import importlib.util
from pathlib import Path


def discover(base_dir: Path) -> dict:
    found = {}
    for folder in sorted(base_dir.iterdir()):
        mod_file = folder / "marketplace.py"
        if not (folder.is_dir() and mod_file.exists()):
            continue
        spec = importlib.util.spec_from_file_location(f"mp_{folder.name}", mod_file)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        instance = module.MARKETPLACE(folder)
        if instance.enabled:
            found[instance.name] = instance
    return found
