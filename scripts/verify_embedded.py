#!/usr/bin/env python3
"""Verify that embedded legacy Python bytes match canonical .debug_sources."""

from __future__ import annotations

import base64
import gzip
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
SOURCE_DIR = ROOT / ".debug_sources"
ASSET_NAMES = ("engine.py", "web_api.py", "xlsx_reader.py", "splits.py")
PATTERN = re.compile(r"window\.MRP_ASSETS=(\{.*?\});</script>", flags=re.S)


def main() -> None:
    html = INDEX.read_text(encoding="utf-8")
    match = PATTERN.search(html)
    if not match:
        raise SystemExit("MRP_ASSETS not found in index.html")

    assets = json.loads(match.group(1))
    missing = [name for name in ASSET_NAMES if name not in assets]
    if missing:
        raise SystemExit(f"Missing embedded assets: {', '.join(missing)}")

    for name in ASSET_NAMES:
        embedded = gzip.decompress(base64.b64decode(assets[name]))
        source = (SOURCE_DIR / name).read_bytes()
        if embedded != source:
            raise SystemExit(
                f"Embedded {name} does not match .debug_sources/{name}. "
                "Run `make rebuild-embedded`."
            )

    print("Embedded planner core matches canonical .debug_sources files.")


if __name__ == "__main__":
    main()
