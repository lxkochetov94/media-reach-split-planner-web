#!/usr/bin/env python3
"""Lightweight repository/documentation freshness checks for agent handoff quality."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

REQUIRED = (
    "AGENTS.md",
    "README.md",
    "ARCHITECTURE.md",
    "docs/CURRENT_STATE.md",
    "docs/DEVELOPMENT.md",
    "docs/REACH_ENGINE_V16.md",
    "Makefile",
)


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def main() -> None:
    for rel in REQUIRED:
        require((ROOT / rel).is_file(), f"Required repository guide is missing: {rel}")

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    agents = (ROOT / "AGENTS.md").read_text(encoding="utf-8")
    state = (ROOT / "docs/CURRENT_STATE.md").read_text(encoding="utf-8")
    state_lower = state.lower()

    require("Web 0.42" not in readme, "README still advertises obsolete Web 0.42")
    require("0.52" in readme, "README must state current legacy core 0.52")
    require("1.6.21" in readme, "README must state current Reach asset version 1.6.21")
    require("github.io/media-reach-split-planner-web" in readme, "README production URL missing")
    require("docs/DEVELOPMENT.md" in agents, "AGENTS.md must point to development guide")
    require("docs/REACH_ENGINE_V16.md" in agents, "AGENTS.md must point to Reach methodology")
    require(len(agents.splitlines()) <= 140, "AGENTS.md should stay a compact map, not a manual")
    require(
        "source reach" in state_lower and "qa" in state_lower,
        "Current-state source Reach QA contract missing",
    )

    print("Repository documentation/Codex handoff contract is current.")


if __name__ == "__main__":
    main()
