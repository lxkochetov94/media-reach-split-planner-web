#!/usr/bin/env python3
"""Rebuild canonical legacy Python sources into index.html MRP_ASSETS."""

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
    for name in ASSET_NAMES:
        raw = (SOURCE_DIR / name).read_bytes()
        assets[name] = base64.b64encode(
            gzip.compress(raw, compresslevel=9, mtime=0)
        ).decode("ascii")

    block = (
        "window.MRP_ASSETS="
        + json.dumps(assets, ensure_ascii=False, separators=(",", ":"))
        + ";</script>"
    )
    rebuilt = html[: match.start()] + block + html[match.end() :]
    INDEX.write_text(rebuilt, encoding="utf-8")
    print("Rebuilt window.MRP_ASSETS from canonical .debug_sources files.")


if __name__ == "__main__":
    main()
