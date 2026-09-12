#!/usr/bin/env python3
"""Fail if a Reach-only change modifies index.html outside the isolated v1.6 surface."""

from __future__ import annotations

import argparse
import re
import subprocess


def read_ref(ref: str) -> str:
    return subprocess.check_output(["git", "show", f"{ref}:index.html"], text=True)


def normalize(html: str) -> str:
    start = html.find('<section id="tab-reach16"')
    end = html.find('<section id="tab-flow"', start)
    if start < 0 or end < 0:
        raise SystemExit("Reach Engine v1.6 section markers not found in index.html")
    html = html[:start] + "<!-- REACH_V16_ISOLATED_SECTION -->\n" + html[end:]
    html = re.sub(r'reach_v16\.css\?v=[^"\']+', "reach_v16.css?v=V16", html)
    html = re.sub(r'reach_v16\.js\?v=[^"\']+', "reach_v16.js?v=V16", html)
    return html


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    args = parser.parse_args()

    base = normalize(read_ref(args.base))
    head = normalize(read_ref(args.head))
    if base != head:
        raise SystemExit(
            "Reach surface guard failed: index.html changed outside the isolated "
            "Reach Engine v1.6 section/cache references."
        )
    print("Reach-only index.html surface is isolated from the legacy production shell.")


if __name__ == "__main__":
    main()
