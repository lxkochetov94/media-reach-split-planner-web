from __future__ import annotations

"""
Reach Engine v1.6 — canonical parser/orchestration adapter.

The mathematical source of truth lives in reach_v16_math.py and follows the final
07.09.2026 canonical Levels 1–7 specification.  This module only connects that
math to the existing LAB media-plan parser and exposes JSON APIs for the isolated
web tab.

Production Web 0.52 is intentionally not called or modified.
"""

import copy
import datetime as dt
import json
import math
import re
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

from engine import discover_media_plan_groups, parse_media_plan, norm
import reach_v16_math as m

VERSION = "1.6"
K_DEFAULT = m.K_DEFAULT
SIGMA_DEFAULT = m.SIGMA_DEFAULT
CHROMIUM_L_DEFAULT = m.CHROMIUM_L_DEFAULT
RHO_CHANNEL_DEFAULT = m.RHO_CHANNEL_DEFAULT
RESIDUAL_CAP = m.RESIDUAL_CAP
TEMPORAL_RHO_PROFILES = {k: v for k, v in m.RHO_TEMPORAL.items() if k in {"LOW", "BASE", "HIGH"}}
SIGMA_CALIBRATION_IQR = (2.42, 2.90)

# Compatibility alias used by existing browser/error handling and legacy v1.6 tests.
V16Error = m.ReachValidationError


def _json_default(v: Any):
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    raise TypeError(f"Object of type {v.__class__.__name__} is not JSON serializable")


def _json(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"), default=_json_default)


def _date(v: Any) -> Optional[str]:
    return v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else None


def _norm_ta(v: Any) -> str:
    return " ".join(str(v or "").strip().lower().replace("ё", "е").split())


def _duration_days(a: Optional[dt.date], b: Optional[dt.date]) -> int:
    if not a or not b:
        return 1
    return max(1, (b - a).days + 1)


def _age_range(ta_name: str) -> Optional[Tuple[int, int]]:
    mt = re.search(r"(?<!\d)(\d{1,2})\s*[-–—]\s*(\d{1,2})(?!\d)", str(ta_name or ""))
    if not mt:
        return None
    lo, hi = int(mt.group(1)), int(mt.group(2))
    if lo > hi:
        lo, hi = hi, lo
    if lo < 12:
        return None
    return lo, hi


def recommended_advanced_factors(ta_name: str) -> dict:
    rng = _age_range(ta_name)
    if rng is None:
        return {
            "B": m.BASE_BROWSER,
            "D": m.BASE_DEVICE_FACTOR,
            "B_source": "BASE_FALLBACK",
            "D_source": "BASE_FALLBACK",
            "B_min": min(x[2] for x in m.AGE_B),
            "B_max": max(x[2] for x in m.AGE_B),
            "D_min": min(x[2] for x in m.AGE_D),
            "D_max": max(x[2] for x in m.AGE_D),
            "age_range": None,
            "B_approximation": True,
            "D_approximation": True,
        }
    lo, hi = rng
    b = m.age_weighted_factor(lo, hi, m.AGE_B)
    d = m.age_weighted_factor(lo, hi, m.AGE_D)
    return {
        "B": b["value"], "D": d["value"],
        "B_source": b["source"], "D_source": d["source"],
        "B_min": b["min"], "B_max": b["max"],
        "D_min": d["min"], "D_max": d["max"],
        "age_range": [lo, hi],
        "B_approximation": b["approximation"],
        "D_approximation": d["approximation"],
    }


def model_catalog() -> dict:
    return {
        "engineering": {
            "max_entities": m.MAX_ENTITIES,
            "max_iterations": m.MAX_ITERATIONS,
            "feasibility_tolerance": m.FEASIBILITY_TOL,
            "solver_constraint_tolerance": m.SOLVER_TOL,
            "lambda_search_tolerance": m.LAMBDA_TOL,
        },
        "level1": {
            "frequency_precision_default": 2,
            "precision_tolerance": "max(1e-6, 0.5×10^-p)",
        },
        "level2": {
            "quick_k": m.K_DEFAULT,
            "chromium_l_days": m.CHROMIUM_L_DEFAULT,
            "base_browser": m.BASE_BROWSER,
            "base_device_factor": m.BASE_DEVICE_FACTOR,
            "browser_by_age": [
                {"segment": f"{a}–{b}" if b < 120 else f"{a}+", "value": v}
                for a, b, v in m.AGE_B
            ],
            "browser_by_device": [
                {"segment": k, "value": v} for k, v in m.DEVICE_B.items()
            ],
            "device_by_age": [
                {"segment": f"{a}–{b}" if b < 120 else f"{a}+", "value": v}
                for a, b, v in m.AGE_D
            ],
            "environment_rules": {
                "WEB": "2A browser churn → 2B browser saturation → 2C device saturation",
                "MOBILE_APP": "2A/2B OFF; device-level input required for Advanced",
                "CTV": "2A/2B OFF; co-viewing outside Level 2",
                "UNKNOWN": "Quick fallback unless environment/data are confirmed",
            },
        },
        "level3": {
            "temporal_rho_profiles": TEMPORAL_RHO_PROFILES,
            "gap_decay": "rho_base^(1+G)",
            "platform_universe_fallback": "U_p = U with assumed flag",
            "aggregate_fallback": "AGGREGATE_FLIGHT_REACH_MODE",
            "sigma_default": m.SIGMA_DEFAULT,
            "sigma_calibration_iqr": list(SIGMA_CALIBRATION_IQR),
            "frequency_model": "Poisson-Lognormal",
        },
        "level4": {
            "rho_cross_default": 0.0,
            "family_mapping": "AUTO_REFERENCE_MAPPING_WITH_OPTIONAL_OVERRIDE",
            "unstructured_neutral": "closed-form mutual independence",
            "structured_or_dependent": "global feasibility → Maximum Entropy",
        },
        "level5": {
            "rho_channel_target": m.RHO_CHANNEL_DEFAULT,
            "relaxation": "common lambda in [0,1] toward neutral for MODEL_DEFAULT only",
        },
        "level6": {
            "gap_curve": [{"days": d, "overlap": q} for d, q in m.Q_TEMPORAL_POINTS],
            "residual_cap": m.RESIDUAL_CAP,
            "universe_multiplier_points": [
                {"universe": u, "multiplier": mu} for u, mu in m.UNIVERSE_MULTIPLIER_POINTS
            ],
            "relaxation": "common lambda >=1; never pair-specific clipping",
            "aon": "auto-model temporal slice from AON delivery footprint; measured override has priority",
        },
        "level7": {
            "rho_line_target": m.RHO_LINE_DEFAULT,
            "brand_master_universe": "REQUIRED for Brand Total",
            "brand_master_ta": "REQUIRED; all Lines normalized upstream",
            "brand_addressability": "conditional hard support constraints",
        },
    }


# ---------------------------------------------------------------------------
# Compatibility wrappers / low-level public helpers
# ---------------------------------------------------------------------------

def level1_technical(row, diagnostics: List[dict]) -> Optional[float]:
    try:
        out = m.level1_technical(
            row.impressions,
            row.frequency,
            row.tech_reach,
            frequency_precision=None,
        )
    except m.ReachValidationError as exc:
        raise V16Error(f"{row.sheet}:{row.source_row+1}: {exc}") from exc
    for d in out.get("diagnostics", []):
        diagnostics.append({**d, "level": 1, "sheet": row.sheet, "row": row.source_row + 1})
    diagnostics.append({
        "code": "L1_TECHNICAL_REACH",
        "level": 1,
        "sheet": row.sheet,
        "row": row.source_row + 1,
        "source": out["source"],
        "R_tech": out["R_tech"],
        "F_implied": out.get("F_implied"),
        "frequency_tolerance": out.get("frequency_tolerance"),
    })
    return out["R_tech"]


def level2_quick(rtech: float, U: float, K: float) -> float:
    return m.level2_quick(rtech, U, K)["R_people"]


def level2_advanced_web(
    rtech: float, U: float, T: float, F: float, U_D: float, B: float, D: float,
    L: float = CHROMIUM_L_DEFAULT,
) -> dict:
    out = m.level2_advanced(
        rtech, U, environment="WEB", duration_days=T, frequency=F,
        web_device_universe=U_D, B=B, D=D, L=L,
        browser_family="CHROMIUM",
    )
    return {
        "R_people": out["R_people"],
        "K_time": out["K_time"],
        "R_stable": out["R_stable"],
        "R_device": out["R_device"],
        "B": B, "D": D, "L": L, "U_D": U_D,
    }


def poisson_lognormal_exact(mean_frequency: float, sigma: float = SIGMA_DEFAULT) -> List[float]:
    return m.poisson_lognormal_frequency(mean_frequency, sigma)["exact"]


def _convolve(a: Sequence[float], b: Sequence[float]) -> List[float]:
    return m.convolve_frequency(a, b)


def merge_entities(
    entities: Sequence[dict], U: float,
    pair_targets: Optional[Dict[Tuple[int, int], float]] = None,
    neutral_unstructured: bool = False,
    support: Optional[Sequence[bool]] = None,
    model_path: str = "AUDIENCE_MERGE",
) -> dict:
    pd = None
    if pair_targets is not None:
        pd = {
            k: {
                "J": v,
                "source": "CUSTOM",
                "rho": None,
            }
            for k, v in pair_targets.items()
        }
    return m.audience_merge(
        entities, U, pair_details=pd,
        neutral_unstructured=neutral_unstructured,
        support=support, model_path=model_path,
    )


def _is_feasible(reaches: Sequence[float], U: float, pair_targets: Dict[Tuple[int, int], float]) -> bool:
    return bool(m.global_feasibility(reaches, U, pair_targets).get("feasible"))


def level5_flight(channels: Sequence[dict], U: float, diagnostics: List[dict]) -> dict:
    out = m.level5_flight(channels, U)
    for d in out.get("diagnostics") or []:
        diagnostics.append(d)
        if d.get("code") == "GLOBAL_FEASIBILITY_RELAXATION":
            diagnostics.append({
                **d,
                "code": "DEFAULT_RELAXED_FOR_GLOBAL_FEASIBILITY",
            })
    return out


def _l6_pair_basic(a: dict, b: dict, U: float) -> Tuple[float, dict]:
    meta = m._l6_basic_pair(a, b, U)
    return meta["J_effective"], meta


def _l6_pair(a: dict, b: dict, U: float, diagnostics: List[dict]) -> Tuple[float, dict]:
    meta = m.l6_pair(a, b, U)
    if meta.get("aon_staged"):
        diagnostics.append({
            "code": "AON_STAGED_MERGE",
            "level": 6,
            "aon_temporal_source": meta.get("aon_temporal_source"),
            "A_slice": meta.get("A_slice"),
            "J_same_period": meta.get("J_same_period"),
            "J_rest": meta.get("J_rest"),
        })
    return meta["J_effective"], meta


def q_temporal(gap: int) -> float:
    return m.q_temporal(gap)


def universe_multiplier(U: float) -> float:
    return m.universe_multiplier(U)


def level6_line(flights: Sequence[dict], U: float, diagnostics: List[dict]) -> dict:
    out = m.level6_line(flights, U)
    diagnostics.extend(out.get("diagnostics") or [])
    return out


# ---------------------------------------------------------------------------
# Parser adapter
# ---------------------------------------------------------------------------

def _unit_id(row) -> str:
    return f"{row.sheet}#{row.source_row + 1}"


def _unit_label(row) -> str:
    bits = [
        row.platform_canonical or row.platform or "Unknown platform",
        row.format or "",
        row.buying_model or "",
    ]
    return " · ".join(x for x in bits if x)


def _platform_label(row) -> str:
    return row.platform_canonical or row.platform or "Unknown platform"


REACH_BUYING_MODELS = {"CPM", "CPV"}
_NON_REACH_PLATFORMS = {"adriver", "ad river", "orm", "seo"}
_REACH_CHANNEL_MAP = {
    "баннеры": "Banners",
    "banners": "Banners",
    "olv": "OLV",
    "social": "Social Nets",
    "social nets": "Social Nets",
    "native": "Native",
    "нативная реклама": "Native",
    "статьи": "Native",
    "спецпроекты": "Native",
    "блогеры": "Native",
    "посевы": "Native",
}


def _reach_channel(row: Any) -> str:
    """Reach-only channel classifier.

    It deliberately does not mutate the legacy parser channel used by production 0.52.
    Row format/product evidence outranks enclosing section labels.
    """
    platform = norm(_platform_label(row))
    fmt = norm(getattr(row, "format", ""))
    raw = norm(getattr(row, "raw_text", ""))
    model = str(getattr(row, "buying_model", "") or "OTHER").upper()
    text = " | ".join(x for x in (platform, fmt, raw) if x)

    video = bool(re.search(
        r"\bolv\b|video|видео|pre[- ]?roll|mid[- ]?roll|multi[- ]?roll|"
        r"in[- ]?stream|instream|out[- ]?stream|outstream|ролик|досмотр|true view",
        text, re.I,
    ))
    native = bool(re.search(
        r"native|натив|стать|тгб|промостраниц|promo\s*pages?|promopages?|"
        r"\bдзен\b|\bdzen\b|\bzen\b",
        text, re.I,
    ))
    banner = bool(re.search(
        r"banner|баннер|display|fullscreen|interstitial|медийн|attention smart|"
        r"статик|креатив",
        text, re.I,
    ))
    content_product = bool(re.search(
        r"промостраниц|promo\s*pages?|promopages?|\bдзен\b|\bdzen\b|\bzen\b",
        text, re.I,
    ))

    # Buying-model rule for content products is authoritative.
    if content_product:
        if model == "CPV" or video:
            return "OLV"
        if model == "CPM":
            return "OLV" if video else ("Banners" if banner else "Banners")
        return "Native"

    # Avito explicit native inventory must not inherit an OLV section.
    if platform == "avito":
        if video or model == "CPV":
            return "OLV"
        if native:
            return "Native"
        return "Banners"

    if video:
        return "OLV"
    if native:
        return "Native"
    if banner:
        return "Banners"

    cls = norm(getattr(row, "placement_class", ""))
    if cls in _REACH_CHANNEL_MAP:
        return _REACH_CHANNEL_MAP[cls]
    legacy = norm(getattr(row, "channel", ""))
    return _REACH_CHANNEL_MAP.get(legacy, getattr(row, "channel", None) or "Other")


def _auto_family(row: Any) -> str:
    # Same canonical platform = same automatic Audience Family. Different products
    # are not guessed into one ecosystem unless the canonical registry already merged them.
    return _platform_label(row).strip() or "Unknown platform"


def _auto_environment(rows: Sequence[Any]) -> str:
    text = norm(" | ".join(
        " ".join(str(x or "") for x in (
            _platform_label(r), getattr(r, "format", ""), getattr(r, "raw_text", ""),
            getattr(r, "placement_class", ""), getattr(r, "channel", ""),
        ))
        for r in rows
    ))
    if re.search(r"\bctv\b|smart\s*tv|connected\s*tv|\bott\b|смарт\s*тв", text, re.I):
        return "CTV"
    if re.search(r"in[- ]?app|mobile\s*app|мобильн\w* прилож|приложени", text, re.I):
        return "MOBILE_APP"
    if re.search(
        r"\bweb\b|browser|desktop|сайт|страниц|native|натив|banner|баннер|display|"
        r"промостраниц|promopages?|\bдзен\b|\bdzen\b|\bavito\b|\bавито\b|slickjump",
        text, re.I,
    ):
        return "WEB"
    return "UNKNOWN"


def _auto_browser_family(rows: Sequence[Any]) -> str:
    text = norm(" | ".join(
        " ".join(str(x or "") for x in (_platform_label(r), getattr(r, "format", ""), getattr(r, "raw_text", "")))
        for r in rows
    ))
    if "safari" in text or "webkit" in text:
        return "SAFARI"
    if re.search(r"chromium|chrome|yandex browser|яндекс браузер", text, re.I):
        return "CHROMIUM"
    return "UNKNOWN"


def _reach_buying_model_eligible(row: Any) -> bool:
    model = str(getattr(row, "buying_model", "") or "OTHER").upper()
    if model not in REACH_BUYING_MODELS:
        return False
    platform = norm(_platform_label(row))
    if platform in _NON_REACH_PLATFORMS:
        return False
    reason = str(getattr(row, "placement_class_reason", "") or "").lower()
    if reason.startswith("technical/service"):
        return False
    cls = norm(getattr(row, "placement_class", ""))
    if cls in {"orm", "seo", "perfomance", "поиск", "рся"}:
        return False
    return True


def _plan_ta(plan) -> str:
    return next((f.ta_name for f in plan.flights if f.ta_name and not f.is_common), "")


def _plan_input_profile(plan) -> dict:
    rows = list(plan.detail_rows())
    eligible = _reach_rows(rows)
    excluded = _excluded_reach_rows(rows)
    durations = sorted(
        _duration_days(r.start, r.end) for r in eligible if r.start and r.end
    )
    med = None
    if durations:
        n = len(durations)
        med = durations[n // 2] if n % 2 else (durations[n // 2 - 1] + durations[n // 2]) / 2
    return {
        "rows": len(rows),
        "reach_scope_rows": len(eligible),
        "reach_excluded_rows": len(excluded),
        "supplied_reach_rows": sum(r.tech_reach is not None for r in eligible),
        "impressions_rows": sum(r.impressions is not None for r in eligible),
        "frequency_rows": sum(r.frequency is not None for r in eligible),
        "impressions_frequency_rows": sum(r.impressions is not None and r.frequency is not None for r in eligible),
        "l1_ready_rows": len(eligible),
        "dated_rows": sum(bool(r.start and r.end) for r in eligible),
        "duration_days_min": min(durations) if durations else None,
        "duration_days_median": med,
        "duration_days_max": max(durations) if durations else None,
        "platforms": len({norm(_platform_label(r)) for r in eligible}),
        "channels": len({norm(r.channel or "Other") for r in eligible}),
    }



def _platform_scope_id(row) -> str:
    """Stable Level-3 platform-flight scope id.

    Different source rows of the same platform/channel inside one Flight are fragments
    of one Level-3 scope, not independent Level-4 entities.
    """
    flight_id = str(getattr(row, "flight", "") or "F?")
    channel = str(getattr(row, "channel", "") or "Other").strip()
    platform = _platform_label(row).strip()
    return f"{flight_id}::{channel}::{platform}"


def _scope_map_value(
    mapping: Mapping[str, Any],
    plan_id: str,
    scope_id: str,
    row_ids: Sequence[str],
    *,
    default=None,
    allow_zero: bool = False,
):
    """Read group-level input first, then a unique consistent row-level value."""
    if not isinstance(mapping, Mapping):
        return default
    direct = _lookup_unit_map(mapping, plan_id, scope_id, None)
    if direct not in (None, ""):
        if allow_zero or direct not in (0, "0"):
            return direct

    values = []
    for uid in row_ids:
        v = _lookup_unit_map(mapping, plan_id, uid, None)
        if v in (None, "") or (not allow_zero and v in (0, "0")):
            continue
        values.append(v)
    if not values:
        return default

    def key(v):
        if isinstance(v, (dict, list)):
            return json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)
        return str(v).strip().upper()

    unique = {}
    for v in values:
        unique[key(v)] = v
    if len(unique) > 1:
        raise V16Error(
            f"{scope_id}: conflicting row-level inputs inside one Level-3 platform scope."
        )
    return next(iter(unique.values()))


def _reach_row_state(row: Any) -> dict:
    """Classify whether a media row belongs to Reach Engine scope.

    Business rule: only reach-buying models CPM/CPV enter Reach. CPC/CPR/CPA/CPI/
    CPO/CPL/CPCV/CPE/CPS/package/service rows remain outside Reach even if the source
    file happens to contain a Reach-looking column.
    """
    I = getattr(row, "impressions", None)
    F = getattr(row, "frequency", None)
    R = getattr(row, "tech_reach", None)
    has_i = I is not None and isinstance(I, (int, float)) and math.isfinite(float(I)) and float(I) >= 0
    has_f = F is not None and isinstance(F, (int, float)) and math.isfinite(float(F))
    has_r = R is not None and isinstance(R, (int, float)) and math.isfinite(float(R)) and float(R) >= 0
    buying_ok = _reach_buying_model_eligible(row)
    ready = bool(buying_ok and has_i and (has_r or has_f))
    if not buying_ok:
        reason = "BUYING_MODEL_NOT_REACH_ELIGIBLE"
    elif ready:
        reason = "SUPPLIED_TECHNICAL_REACH" if has_r else "IMPRESSIONS_PLUS_FREQUENCY"
    elif not has_i:
        reason = "IMPRESSIONS_NOT_AVAILABLE"
    else:
        reason = "FREQUENCY_AND_TECHNICAL_REACH_NOT_AVAILABLE"
    return {
        "ready": ready,
        "reason": reason,
        "buying_model_reach_eligible": buying_ok,
        "has_impressions": has_i,
        "has_frequency": has_f,
        "has_technical_reach": has_r,
    }

def _reach_rows(rows: Sequence[Any]) -> List[Any]:
    return [row for row in rows if _reach_row_state(row)["ready"]]


def _excluded_reach_rows(rows: Sequence[Any]) -> List[dict]:
    out = []
    for row in rows:
        state = _reach_row_state(row)
        if state["ready"]:
            continue
        out.append({
            "unit_id": _unit_id(row),
            "sheet": row.sheet,
            "row": row.source_row + 1,
            "platform": _platform_label(row),
            "channel": row.channel or "Other",
            "buying_model": row.buying_model or "",
            "reason": state["reason"],
            "has_impressions": state["has_impressions"],
            "has_frequency": state["has_frequency"],
            "has_technical_reach": state["has_technical_reach"],
        })
    return out


def _platform_scope_requirements(units: Sequence[dict]) -> List[dict]:
    grouped: Dict[str, List[dict]] = defaultdict(list)
    for unit in units:
        grouped[str(unit.get("platform_scope_id") or "")].append(unit)
    out = []
    for scope_id, items in grouped.items():
        if len(items) <= 1:
            continue
        out.append({
            "scope_id": scope_id,
            "platform": items[0].get("platform"),
            "channel": items[0].get("channel"),
            "fragment_count": len(items),
            "source_rows": [
                {"unit_id": x.get("id"), "sheet": x.get("sheet"), "row": x.get("row"), "start": x.get("start"), "end": x.get("end")}
                for x in items
            ],
            "required_input": None,
            "auto_path": "AUTO_PERIODIC_PLATFORM_TEMPORAL",
        })
    return out

def _platform_groups(rows: Sequence[Any]) -> List[List[Any]]:
    grouped: Dict[Tuple[str, str], List[Any]] = defaultdict(list)
    for row in rows:
        grouped[(_reach_channel(row), norm(_platform_label(row)))].append(row)
    return list(grouped.values())

def _inventory_units(plan) -> List[dict]:
    rows = _reach_rows(list(plan.detail_rows()))
    counts = Counter(_platform_scope_id(row) for row in rows)
    units = []
    for row in rows:
        sid = _platform_scope_id(row)
        env = _auto_environment([row])
        units.append({
            "id": _unit_id(row),
            "platform_scope_id": sid,
            "platform_scope_fragments": counts[sid],
            "label": _unit_label(row),
            "sheet": row.sheet,
            "row": row.source_row + 1,
            "channel": _reach_channel(row),
            "source_channel": row.channel or "Other",
            "platform": _platform_label(row),
            "format": row.format or "",
            "buying_model": row.buying_model or "",
            "start": _date(row.start),
            "end": _date(row.end),
            "suggested_family": _auto_family(row),
            "family_suggestion_source": "AUTO_REFERENCE_MAPPING",
            "environment_suggestion": env,
            "environment_source": "AUTO_FROM_PLAN",
            "has_impressions": row.impressions is not None,
            "has_frequency": row.frequency is not None,
            "has_technical_reach": row.tech_reach is not None,
            "l3a_temporal_input_required_if_no_aggregate": False,
        })
    return units

def _duplicate_warnings(rows: Sequence[Any]) -> List[dict]:
    signatures: Dict[tuple, List[dict]] = defaultdict(list)
    for row in rows:
        sig = (
            norm(_platform_label(row)),
            norm(row.format),
            norm(row.buying_model),
            round(float(row.budget or 0), 2),
            round(float(row.impressions or 0), 2),
            round(float(row.tech_reach or 0), 2),
            row.start, row.end,
        )
        signatures[sig].append({"sheet": row.sheet, "row": row.source_row + 1})
    return [
        {
            "code": "DUPLICATE_LIKE_ROW_WARNING",
            "level": "IMPORT",
            "severity": "WARNING",
            "rows": locs,
            "message": "Похожие строки не удалены автоматически; требуется только QA.",
        }
        for sig, locs in signatures.items()
        if len(locs) > 1 and any(sig)
    ]


def _plan_universe(plan, override: Any) -> float:
    if override not in (None, ""):
        return m.positive(override, "Universe")
    if plan.universe is not None and float(plan.universe) > 0:
        return float(plan.universe)
    raise V16Error(f"{plan.display_name or plan.line or 'Line'}: Universe не найден. Укажите измеряемый Universe.")


def _resolve_line_l2(plan, U: float, q: dict, plan_id: str) -> dict:
    requested = str(q.get("l2_mode") or "AUTO").upper()
    if requested not in {"AUTO", "QUICK", "ADVANCED"}:
        # Keep legacy value accepted by existing UI.
        if requested == "ADVANCED_WEB":
            requested = "ADVANCED"
        else:
            raise V16Error("Level 2 mode должен быть AUTO, QUICK или ADVANCED.")

    adv_q = q.get("advanced") or {}
    K = m.finite(q.get("K", m.K_DEFAULT), "K")
    if K < 1:
        raise V16Error("K должен быть >= 1.")

    ta = _plan_ta(plan)
    rec = recommended_advanced_factors(ta)
    B_raw = adv_q.get("B")
    D_raw = adv_q.get("D")
    L_raw = adv_q.get("L")
    B = rec["B"] if B_raw in (None, "") else m.finite(B_raw, "B")
    D = rec["D"] if D_raw in (None, "") else m.finite(D_raw, "D")
    L = m.CHROMIUM_L_DEFAULT if L_raw in (None, "") else m.positive(L_raw, "L")
    if B < 1 or D < 1:
        raise V16Error("B и D должны быть >= 1.")

    return {
        "requested_mode": requested,
        "K": K,
        "K_source": "MODEL_DEFAULT" if q.get("K") in (None, "", m.K_DEFAULT, "2.4", "2.40") else "USER_OVERRIDE",
        "B": B, "D": D, "L": L,
        "B_source": "USER_OVERRIDE" if B_raw not in (None, "") else rec["B_source"],
        "D_source": "USER_OVERRIDE" if D_raw not in (None, "") else rec["D_source"],
        "L_source": "USER_OVERRIDE" if L_raw not in (None, "") and float(L_raw) != m.CHROMIUM_L_DEFAULT else "MODEL_DEFAULT",
        "B_min": rec["B_min"], "B_max": rec["B_max"],
        "D_min": rec["D_min"], "D_max": rec["D_max"],
        "age_range": rec["age_range"],
        "ta_name": ta,
        "web_device_universes": adv_q.get("web_device_universes") or {},
        "unit_web_device_universes": adv_q.get("unit_web_device_universes") or {},
        "environments": adv_q.get("environments") or {},
        "browser_families": adv_q.get("browser_families") or {},
        "device_reaches": adv_q.get("device_reaches") or {},
        "browser_segments": adv_q.get("browser_segments") or {},
        "device_segments": adv_q.get("device_segments") or {},
        "safari_l": adv_q.get("safari_l"),
        "plan_id": plan_id,
    }


def _lookup_unit_map(mapping: Mapping[str, Any], plan_id: str, unit_id: str, default=None):
    plan_map = mapping.get(plan_id) if isinstance(mapping, Mapping) else None
    if isinstance(plan_map, Mapping) and unit_id in plan_map:
        return plan_map[unit_id]
    if unit_id in mapping:
        return mapping[unit_id]
    return default





def _mapping_for_plan(q: dict, plan_id: str) -> Mapping[str, str]:
    all_maps = q.get("family_mapping") or {}
    pmap = all_maps.get(plan_id)
    return pmap if isinstance(pmap, Mapping) else {}


def _mapping_confirmed(q: dict, plan_id: str) -> bool:
    flags = q.get("family_mapping_confirmed") or {}
    if isinstance(flags, Mapping):
        return bool(flags.get(plan_id))
    return False
def _scope_value(
    q: Mapping[str, Any],
    key: str,
    plan_id: str,
    *,
    flight_id: Optional[str] = None,
    name: Optional[str] = None,
    default=None,
):
    root = q.get(key) or {}
    if not isinstance(root, Mapping):
        return default
    cur: Any = root
    if plan_id in cur and isinstance(cur[plan_id], Mapping):
        cur = cur[plan_id]
    if flight_id is not None and isinstance(cur, Mapping) and flight_id in cur and isinstance(cur[flight_id], Mapping):
        cur = cur[flight_id]
    if name is not None and isinstance(cur, Mapping) and name in cur:
        return cur[name]
    if name is None and flight_id is not None and isinstance(cur, Mapping) and flight_id in cur and not isinstance(cur[flight_id], Mapping):
        return cur[flight_id]
    if name is None and plan_id in root and not isinstance(root[plan_id], Mapping):
        return root[plan_id]
    return default


_PAIR_SOURCE_RANK = {
    "MEASURED": 100,
    "MEASURED_CAMPAIGN": 100,
    "MEASURED_ADDRESSABLE": 100,
    "BRAND_ADDRESSABILITY_MAP": 100,
    "HISTORICAL": 80,
    "HISTORICAL_CALIBRATED": 80,
    "CUSTOM": 60,
    "CUSTOM_ADDRESSABILITY": 60,
    "MODEL_DEFAULT": 10,
    "BASE_MODEL_DEFAULT": 10,
    "NEUTRAL_MODEL_DEFAULT": 10,
}


def _pair_specs(
    q: Mapping[str, Any],
    level: str,
    *,
    plan_id: Optional[str] = None,
    flight_id: Optional[str] = None,
    parent: Optional[str] = None,
) -> List[dict]:
    raw = q.get("pair_inputs") or []
    if isinstance(raw, Mapping):
        raw = raw.get(level) or raw.get(level.upper()) or []
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        raise V16Error("pair_inputs должен быть list либо mapping level→list.")
    out = []
    for item in raw:
        if not isinstance(item, Mapping):
            raise V16Error("Каждый pair_inputs item должен быть object.")
        item_level = str(item.get("level") or level).upper()
        if item_level != level.upper():
            continue
        for field, actual in (("plan_id", plan_id), ("flight_id", flight_id), ("parent", parent)):
            expected = item.get(field)
            if expected not in (None, "") and actual is not None and str(expected) != str(actual):
                break
        else:
            out.append(dict(item))
    return out


def _entity_alias_map(entities: Sequence[dict]) -> Dict[str, int]:
    aliases: Dict[str, int] = {}
    for idx, ent in enumerate(entities):
        aliases[str(idx)] = idx
        for key in ("name", "label", "unit_id", "family_id", "flight_id", "plan_id", "line_id"):
            value = str(ent.get(key) or "").strip()
            if value:
                aliases[value] = idx
                aliases[value.lower()] = idx
    return aliases


def _pair_raw_by_index(entities: Sequence[dict], specs: Sequence[dict]) -> Dict[Tuple[int, int], dict]:
    aliases = _entity_alias_map(entities)
    chosen: Dict[Tuple[int, int], Tuple[int, dict]] = {}
    for spec in specs:
        a_raw, b_raw = spec.get("a"), spec.get("b")
        if a_raw is None or b_raw is None:
            raise V16Error("pair_inputs требует a и b.")
        def resolve(token):
            if isinstance(token, int) and 0 <= token < len(entities):
                return token
            key = str(token).strip()
            idx = aliases.get(key, aliases.get(key.lower()))
            if idx is None:
                raise V16Error(f"pair_inputs: entity '{token}' не найдена в текущем scope.")
            return idx
        i, j = resolve(a_raw), resolve(b_raw)
        if i == j:
            raise V16Error("pair_inputs: a и b не могут быть одной entity.")
        key = tuple(sorted((i, j)))
        source = str(spec.get("source") or "CUSTOM").upper()
        rank = _PAIR_SOURCE_RANK.get(source, 50)
        payload = {
            k: v for k, v in spec.items()
            if k not in {"level", "plan_id", "flight_id", "parent", "a", "b"}
        }
        payload["source"] = source
        if key in chosen and chosen[key][0] == rank:
            raise V16Error(
                f"pair_inputs: несколько relations одинакового приоритета для pair {a_raw} × {b_raw}."
            )
        if key not in chosen or rank > chosen[key][0]:
            chosen[key] = (rank, payload)
    return {k: v for k, (_rank, v) in chosen.items()}


def _normalized_pair_details(
    entities: Sequence[dict],
    U: float,
    specs: Sequence[dict],
    *,
    default_rho: Optional[float],
) -> Dict[Tuple[int, int], dict]:
    raw = _pair_raw_by_index(entities, specs)
    out: Dict[Tuple[int, int], dict] = {}
    for (i, j), meta in raw.items():
        Ui = meta.get("U_i", entities[i].get("addressable_universe"))
        Uj = meta.get("U_j", entities[j].get("addressable_universe"))
        Mij = meta.get("M")
        try:
            out[(i, j)] = m.normalize_pair_input(
                meta,
                float(entities[i]["reach_1p"]),
                float(entities[j]["reach_1p"]),
                U,
                Ua=Ui, Ub=Uj, M=Mij,
                default_rho=default_rho,
                default_source=str(meta.get("source") or "CUSTOM"),
            )
        except (m.ReachValidationError, m.ReachCalculationError) as exc:
            raise V16Error(str(exc)) from exc
    return out


def _parse_scope_date(value: Any, label: str) -> dt.date:
    if isinstance(value, dt.datetime):
        return value.date()
    if isinstance(value, dt.date):
        return value
    try:
        return dt.date.fromisoformat(str(value))
    except Exception as exc:
        raise V16Error(f"{label} должен быть YYYY-MM-DD.") from exc



def _l2_for_scope(
    *,
    rtech: float,
    impressions: Optional[float],
    frequency: Optional[float],
    start: Optional[dt.date],
    end: Optional[dt.date],
    U: float,
    cfg: dict,
    diagnostics: List[dict],
    scope_id: str,
    source_refs: Sequence[dict],
    l1: Optional[dict] = None,
    row_ids: Optional[Sequence[str]] = None,
    environment_hint: str = "UNKNOWN",
    browser_family_hint: str = "UNKNOWN",
) -> dict:
    if l1 is None:
        l1 = m.level1_technical(impressions, frequency, rtech, frequency_precision=None)
        for d in l1["diagnostics"]:
            diagnostics.append({
                **d, "level": 1, "scope_id": scope_id,
                "source_refs": list(source_refs),
            })
    rtech = l1["R_tech"]
    requested = cfg["requested_mode"]
    row_ids = list(row_ids or [])

    environment = str(_scope_map_value(
        cfg["environments"], cfg["plan_id"], scope_id, row_ids, default=environment_hint
    ) or environment_hint or "UNKNOWN").upper()
    browser_family = str(_scope_map_value(
        cfg["browser_families"], cfg["plan_id"], scope_id, row_ids, default=browser_family_hint
    ) or browser_family_hint or "UNKNOWN").upper()
    unit_ud = _scope_map_value(
        cfg["unit_web_device_universes"], cfg["plan_id"], scope_id, row_ids, default=None
    )
    line_ud = cfg["web_device_universes"].get(cfg["plan_id"])
    U_D = unit_ud if unit_ud not in (None, "", 0, "0") else line_ud
    device_reach = _scope_map_value(
        cfg["device_reaches"], cfg["plan_id"], scope_id, row_ids, default=None
    )
    browser_segments = _scope_map_value(
        cfg.get("browser_segments") or {}, cfg["plan_id"], scope_id, row_ids, default=None
    )
    device_segments = _scope_map_value(
        cfg.get("device_segments") or {}, cfg["plan_id"], scope_id, row_ids, default=None
    )

    reason = None
    use_advanced = requested == "ADVANCED"
    if requested == "AUTO":
        if environment == "WEB":
            use_advanced = bool(
                U_D not in (None, "", 0, "0")
                and start and end and frequency is not None
            )
            if not use_advanced:
                reason = "INSUFFICIENT_WEB_ADVANCED_INPUTS"
        elif environment in {"MOBILE_APP", "CTV"}:
            use_advanced = device_reach not in (None, "")
            if not use_advanced:
                reason = "DEVICE_LEVEL_REACH_NOT_AVAILABLE"
        else:
            use_advanced = False
            reason = "ENVIRONMENT_NOT_CONFIRMED"

    if not use_advanced:
        quick = m.level2_quick(rtech, U, cfg["K"])
        diagnostics.append({
            "code": "L2_QUICK",
            "level": 2,
            "scope_id": scope_id,
            "source_refs": list(source_refs),
            "requested_mode": requested,
            "effective_mode": "QUICK",
            "reason": reason or ("USER_SELECTED_QUICK" if requested == "QUICK" else None),
            "K": quick["K"], "K_source": cfg["K_source"],
            "source": "FALLBACK" if requested == "AUTO" else "USER_OVERRIDE",
        })
        return {
            "R_people": quick["R_people"],
            "mode": "QUICK",
            "environment": environment,
            "l1": l1,
            "details": quick,
            "fallback_reason": reason,
        }

    if environment == "UNKNOWN":
        raise V16Error(f"{scope_id}: Advanced требует подтверждённую environment.")
    if environment == "WEB" and U_D in (None, "", 0, "0"):
        raise V16Error(f"{scope_id}: Web Advanced требует U_D.")
    if environment == "WEB" and (not start or not end or frequency is None):
        raise V16Error(f"{scope_id}: Web Advanced требует dates и Frequency.")
    if environment in {"MOBILE_APP", "CTV"} and device_reach in (None, ""):
        raise V16Error(f"{scope_id}: {environment} Advanced требует device-level Reach.")

    try:
        adv = m.level2_advanced(
            rtech, U,
            environment=environment,
            duration_days=_duration_days(start, end) if start and end else None,
            frequency=frequency,
            web_device_universe=U_D,
            device_reach=device_reach,
            B=cfg["B"], D=cfg["D"], L=cfg["L"],
            browser_family=browser_family,
            safari_l=cfg.get("safari_l"),
            browser_segments=browser_segments,
            device_segments=device_segments,
            B_source=cfg["B_source"], D_source=cfg["D_source"],
        )
    except (m.ReachValidationError, m.ReachCalculationError) as exc:
        raise V16Error(f"{scope_id}: {exc}") from exc
    diagnostics.append({
        "code": "L2_ADVANCED",
        "level": 2,
        "scope_id": scope_id,
        "source_refs": list(source_refs),
        "requested_mode": requested,
        "effective_mode": "ADVANCED",
        "environment": environment,
        "browser_family": browser_family,
        "B": cfg["B"], "B_source": cfg["B_source"],
        "D": cfg["D"], "D_source": cfg["D_source"],
        "L": cfg["L"], "L_source": cfg["L_source"],
        "U_D": U_D,
        "K_time": adv.get("K_time"),
        "R_stable": adv.get("R_stable"),
        "R_device": adv.get("R_device"),
        "R_people": adv.get("R_people"),
        "path": adv.get("path"),
    })
    for d in adv.get("diagnostics", []):
        diagnostics.append({
            **d, "scope_id": scope_id, "source_refs": list(source_refs),
        })
    return {
        "R_people": adv["R_people"],
        "mode": "ADVANCED",
        "environment": environment,
        "l1": l1,
        "details": adv,
        "fallback_reason": None,
    }


def _l2_for_row(row, U: float, cfg: dict, diagnostics: List[dict]) -> dict:
    l1 = m.level1_technical(
        row.impressions, row.frequency, row.tech_reach, frequency_precision=None
    )
    for d in l1["diagnostics"]:
        diagnostics.append({
            **d, "level": 1, "sheet": row.sheet, "row": row.source_row + 1,
        })
    return _l2_for_scope(
        rtech=l1["R_tech"],
        impressions=row.impressions,
        frequency=row.frequency,
        start=row.start,
        end=row.end,
        U=U,
        cfg=cfg,
        diagnostics=diagnostics,
        scope_id=_unit_id(row),
        source_refs=[{"sheet": row.sheet, "row": row.source_row + 1}],
        l1=l1,
        row_ids=[_unit_id(row)],
    )



def _lookup_platform_input(
    q: Mapping[str, Any],
    key: str,
    plan_id: str,
    flight_id: str,
    scope_id: str,
    platform_name: str,
    row_ids: Sequence[str],
    *,
    default=None,
):
    root = q.get(key) or {}
    if not isinstance(root, Mapping):
        return default

    # Preferred direct/group key path.
    value = _scope_map_value(root, plan_id, scope_id, row_ids, default=None, allow_zero=True)
    if value not in (None, ""):
        return value

    # Structured plan -> flight -> scope/platform aliases.
    p = root.get(plan_id)
    if isinstance(p, Mapping):
        f = p.get(flight_id)
        if isinstance(f, Mapping):
            for alias in (scope_id, platform_name):
                if alias in f:
                    return f[alias]
        for alias in (scope_id, platform_name):
            if alias in p:
                return p[alias]
    return default


def _row_l2_entity(
    row: Any, U: float, cfg: dict, diagnostics: List[dict], scope_id: str,
) -> dict:
    uid = _unit_id(row)
    try:
        l1 = m.level1_technical(
            row.impressions, row.frequency, row.tech_reach, frequency_precision=None
        )
    except m.ReachValidationError as exc:
        raise V16Error(f"{row.sheet}:{row.source_row+1}: {exc}") from exc
    out = _l2_for_scope(
        rtech=l1["R_tech"],
        impressions=row.impressions,
        frequency=row.frequency,
        start=row.start,
        end=row.end,
        U=U,
        cfg=cfg,
        diagnostics=diagnostics,
        scope_id=f"{scope_id}::{uid}",
        source_refs=[{"sheet": row.sheet, "row": row.source_row + 1}],
        l1=l1,
        row_ids=[uid],
        environment_hint=_auto_environment([row]),
        browser_family_hint=_auto_browser_family([row]),
    )
    return {
        "name": uid,
        "reach_1p": out["R_people"],
        "impressions": float(row.impressions or 0.0),
        "start": row.start,
        "end": row.end,
        "l2": out,
    }


def _cluster_period_rows(rows: Sequence[Any]) -> List[List[Any]]:
    ordered = sorted(rows, key=lambda r: (
        r.start or dt.date.min, r.end or dt.date.min, r.source_row
    ))
    if not ordered:
        return []
    clusters: List[List[Any]] = []
    for row in ordered:
        if not clusters:
            clusters.append([row])
            continue
        prev = clusters[-1]
        prev_end = max((x.end for x in prev if x.end), default=None)
        cur_start = row.start
        if prev_end and cur_start and cur_start <= prev_end:
            prev.append(row)
        elif not prev_end and not cur_start:
            prev.append(row)
        else:
            clusters.append([row])
    return clusters


def _auto_period_platform_reach(
    rows: Sequence[Any], U: float, cfg: dict, diagnostics: List[dict],
    scope_id: str, platform_universe: Optional[float], profile: str,
    custom_rho: Optional[float],
) -> Tuple[dict, List[dict]]:
    """Automatically close multi-row platform scope using period-level human reaches.

    Each source fragment is first converted Technical→Human at its own scope. Rows
    active at the same time are unioned neutrally inside the platform; sequential
    periods are then merged with the canonical Level-3 temporal recurrence. No manual
    aggregate Reach is required.
    """
    clusters = _cluster_period_rows(rows)
    if not clusters:
        return m.aggregate_flight_reach_mode(0.0, U, platform_universe=platform_universe), []

    period_entities: List[dict] = []
    period_meta: List[dict] = []
    for idx, cluster in enumerate(clusters):
        ents = [_row_l2_entity(r, U, cfg, diagnostics, scope_id) for r in cluster]
        if len(ents) == 1:
            R = ents[0]["reach_1p"]
            model = "SINGLE_FRAGMENT"
        else:
            merged = m.audience_merge(
                ents, U, neutral_unstructured=True,
                model_path="L3_PLATFORM_SAME_PERIOD_NEUTRAL",
            )
            R = merged["reach_1p"]
            model = merged["model_path"]
        start = min((r.start for r in cluster if r.start), default=None)
        end = max((r.end for r in cluster if r.end), default=None)
        period_entities.append({"reach": R, "start": start, "end": end})
        period_meta.append({
            "period_index": idx + 1,
            "reach_1p": R,
            "start": _date(start),
            "end": _date(end),
            "fragment_count": len(cluster),
            "same_period_model": model,
        })

    # temporal_platform_reach consumes a weekly-style index. We use it only to encode
    # inactive full-week gaps; adjacent source periods remain adjacent indices.
    temporal = []
    order = 0
    prev_end = None
    for item in period_entities:
        if prev_end and item["start"]:
            gap_days = max(0, (item["start"] - prev_end).days - 1)
            order += 1 + gap_days // 7
        elif temporal:
            order += 1
        temporal.append({"week_index": order, "reach": item["reach"]})
        prev_end = item["end"] or prev_end

    try:
        out = m.temporal_platform_reach(
            temporal, U, platform_universe=platform_universe,
            profile=profile, custom_rho=custom_rho,
        )
    except (m.ReachValidationError, m.ReachCalculationError) as exc:
        raise V16Error(f"{scope_id}: automatic period temporal merge failed: {exc}") from exc
    out["model_path"] = "AUTO_PERIODIC_PLATFORM_TEMPORAL"
    out["periods"] = period_meta
    diagnostics.append({
        "code": "L3A_AUTO_PERIODIC_PLATFORM",
        "level": 3,
        "scope_id": scope_id,
        "periods": period_meta,
        "profile": out.get("profile"),
        "rho_base": out.get("rho_base"),
        "model_path": out["model_path"],
        "source": "AUTO_FROM_MEDIA_PLAN_PERIODS",
    })
    return out, period_meta


def _clip_row_to_window(row: Any, start: dt.date, end: dt.date) -> Optional[Any]:
    rs = row.start or start
    re_ = row.end or end
    a, b = max(rs, start), min(re_, end)
    if a > b:
        return None
    full_days = max(1, (re_ - rs).days + 1)
    overlap_days = max(1, (b - a).days + 1)
    share = min(1.0, max(0.0, overlap_days / full_days))
    clone = copy.copy(row)
    clone.start, clone.end = a, b
    if row.impressions is not None:
        clone.impressions = float(row.impressions) * share
    if clone.frequency is not None and clone.impressions is not None:
        clone.tech_reach = clone.impressions / float(clone.frequency)
    elif row.tech_reach is not None:
        clone.tech_reach = float(row.tech_reach) * share
    return clone


def _platform_entity(
    rows: Sequence[Any],
    U: float,
    cfg: dict,
    q: dict,
    plan_id: str,
    flight_id: str,
    diagnostics: List[dict],
) -> dict:
    if not rows:
        raise V16Error("Level 3 platform scope is empty.")

    rows = list(rows)
    platform = _platform_label(rows[0])
    channel = _reach_channel(rows[0])
    scope_id = _platform_scope_id(rows[0])
    row_ids = [_unit_id(row) for row in rows]
    source_refs = [{"sheet": row.sheet, "row": row.source_row + 1} for row in rows]

    # Same Level-3 entity cannot straddle channels/platforms.
    if any(_reach_channel(row) != channel or norm(_platform_label(row)) != norm(platform) for row in rows):
        raise V16Error(f"{scope_id}: mixed platform/channel inside one Level-3 scope.")

    family_map = _mapping_for_plan(q, plan_id)
    families = []
    for row in rows:
        uid = _unit_id(row)
        fam = str(family_map.get(uid) or _auto_family(row)).strip()
        families.append(fam)
    if len({_norm_ta(x) for x in families}) != 1:
        raise V16Error(
            f"AUDIENCE_FAMILY_MAPPING_CONFLICT: {scope_id} имеет разные Family "
            "внутри одной platform-flight entity."
        )
    family = families[0]
    diagnostics.append({
        "code": "AUDIENCE_FAMILY_AUTO",
        "level": 4,
        "scope_id": scope_id,
        "family": family,
        "source": "USER_OVERRIDE" if any(_unit_id(r) in family_map for r in rows) else "AUTO_REFERENCE_MAPPING",
    })

    # Validate every source row independently at Level 1. This is source QA only;
    # Reach is not merged row-by-row after this point.
    row_l1: Dict[str, dict] = {}
    for row in rows:
        try:
            l1 = m.level1_technical(
                row.impressions, row.frequency, row.tech_reach, frequency_precision=None
            )
        except m.ReachValidationError as exc:
            raise V16Error(f"{row.sheet}:{row.source_row+1}: {exc}") from exc
        row_l1[_unit_id(row)] = l1
        for d in l1.get("diagnostics", []):
            diagnostics.append({
                **d, "level": 1, "sheet": row.sheet, "row": row.source_row + 1,
                "scope_id": scope_id,
            })

    if any(row.impressions is None for row in rows):
        raise V16Error(
            f"{scope_id}: Level 3B требует Impressions для всех fragments "
            "или direct human frequency buckets того же platform-flight scope."
        )
    source_impressions = sum(float(row.impressions or 0.0) for row in rows)
    explicit_I = _lookup_platform_input(
        q, "aggregate_flight_impressions", plan_id, flight_id,
        scope_id, platform, row_ids, default=None,
    )
    I_scope = source_impressions if explicit_I in (None, "") else m.finite(
        explicit_I, f"{scope_id} aggregate Flight Impressions"
    )
    if explicit_I not in (None, ""):
        tol = max(1e-6, m.SOLVER_TOL * max(1.0, I_scope))
        if abs(I_scope - source_impressions) > tol:
            diagnostics.append({
                "code": "AGGREGATE_IMPRESSIONS_OVERRIDE",
                "level": 3,
                "scope_id": scope_id,
                "source_rows_sum": source_impressions,
                "aggregate_impressions": I_scope,
                "source": "USER_INPUT",
            })

    weekly = _lookup_platform_input(
        q, "weekly_human_reaches", plan_id, flight_id,
        scope_id, platform, row_ids, default=None,
    )
    U_p = _lookup_platform_input(
        q, "platform_universes", plan_id, flight_id,
        scope_id, platform, row_ids, default=None,
    )
    prof = str(_lookup_platform_input(
        q, "temporal_profiles", plan_id, flight_id,
        scope_id, platform, row_ids, default="BASE",
    ) or "BASE").upper()
    custom_rho = _lookup_platform_input(
        q, "temporal_rhos", plan_id, flight_id,
        scope_id, platform, row_ids, default=None,
    )

    l2out = None
    if weekly:
        try:
            l3a = m.temporal_platform_reach(
                weekly, U, platform_universe=U_p,
                profile=prof, custom_rho=custom_rho,
            )
        except (m.ReachValidationError, m.ReachCalculationError) as exc:
            raise V16Error(f"{scope_id}: {exc}") from exc
        l2_summary = {
            "mode": "UPSTREAM_WEEKLY_HUMAN",
            "environment": "UPSTREAM_HUMAN",
            "fallback_reason": None,
            "source": "USER_INPUT_WEEKLY_HUMAN_REACH",
        }
    else:
        explicit_Rtech = _lookup_platform_input(
            q, "aggregate_flight_technical_reaches", plan_id, flight_id,
            scope_id, platform, row_ids, default=None,
        )
        if len(rows) > 1 and explicit_Rtech in (None, ""):
            l3a, _periods = _auto_period_platform_reach(
                rows, U, cfg, diagnostics, scope_id, U_p, prof, custom_rho,
            )
            l2_summary = {
                "mode": "AUTO_PERIODIC",
                "environment": _auto_environment(rows),
                "fallback_reason": None,
                "aggregate_scope_source": "AUTO_FROM_MEDIA_PLAN_PERIODS",
            }
        elif explicit_Rtech in (None, ""):
            only = rows[0]
            l1 = row_l1[_unit_id(only)]
            Rtech_scope = l1["R_tech"]
            F_scope = only.frequency
            l2out = _l2_for_scope(
                rtech=Rtech_scope,
                impressions=only.impressions,
                frequency=F_scope,
                start=only.start,
                end=only.end,
                U=U,
                cfg=cfg,
                diagnostics=diagnostics,
                scope_id=scope_id,
                source_refs=source_refs,
                l1=l1,
                row_ids=row_ids,
                environment_hint=_auto_environment(rows),
                browser_family_hint=_auto_browser_family(rows),
            )
            aggregate_source = "SINGLE_SOURCE_ROW_COMPLETE_PLATFORM_SCOPE"
        else:
            Rtech_scope = m.finite(
                explicit_Rtech, f"{scope_id} aggregate Flight Technical Reach"
            )
            if Rtech_scope < 0:
                raise V16Error(f"{scope_id}: aggregate technical Reach < 0.")
            if Rtech_scope == 0 and I_scope > 0:
                raise V16Error(f"{scope_id}: aggregate technical Reach=0 при Impressions>0.")
            F_scope = (I_scope / Rtech_scope) if Rtech_scope > 0 else 1.0
            if F_scope < 1 - m.NUMERICAL_TOL:
                raise V16Error(
                    f"{scope_id}: aggregate Impressions/Technical Reach даёт Frequency<1."
                )
            try:
                l1 = m.level1_technical(
                    I_scope, F_scope, Rtech_scope, frequency_precision=12
                )
            except m.ReachValidationError as exc:
                raise V16Error(f"{scope_id}: {exc}") from exc
            l2out = _l2_for_scope(
                rtech=Rtech_scope,
                impressions=I_scope,
                frequency=F_scope,
                start=min((r.start for r in rows if r.start), default=None),
                end=max((r.end for r in rows if r.end), default=None),
                U=U,
                cfg=cfg,
                diagnostics=diagnostics,
                scope_id=scope_id,
                source_refs=source_refs,
                l1=l1,
                row_ids=row_ids,
                environment_hint=_auto_environment(rows),
                browser_family_hint=_auto_browser_family(rows),
            )
            aggregate_source = "USER_INPUT_AGGREGATE_FLIGHT_TECHNICAL_REACH"

        if l2out is not None:
            try:
                l3a = m.aggregate_flight_reach_mode(
                    l2out["R_people"], U, platform_universe=U_p,
                )
            except (m.ReachValidationError, m.ReachCalculationError) as exc:
                raise V16Error(f"{scope_id}: {exc}") from exc
            l2_summary = {
                "mode": l2out["mode"],
                "environment": l2out["environment"],
                "fallback_reason": l2out["fallback_reason"],
                "aggregate_scope_source": aggregate_source,
                **{k: v for k, v in l2out["details"].items() if k != "diagnostics"},
            }

    diagnostics.append({
        "code": "L3A_PLATFORM_FLIGHT",
        "level": 3,
        "scope_id": scope_id,
        "platform": platform,
        "channel": channel,
        "flight_id": flight_id,
        "source_refs": source_refs,
        "fragment_count": len(rows),
        "model_path": l3a["model_path"],
        "U": U, "U_p": l3a["U_p"],
        "platform_universe_assumed": l3a["platform_universe_assumed"],
        "temporal_profile": l3a.get("profile"),
        "rho_base": l3a.get("rho_base"),
        "rho_source": l3a.get("rho_source"),
        "incremental": l3a.get("incremental"),
    })

    measured_freq = _lookup_platform_input(
        q, "measured_exact_frequency", plan_id, flight_id,
        scope_id, platform, row_ids, default=None,
    )
    cap = _lookup_platform_input(
        q, "human_frequency_caps", plan_id, flight_id,
        scope_id, platform, row_ids, default=None,
    )
    sigma = _lookup_platform_input(
        q, "sigmas", plan_id, flight_id,
        scope_id, platform, row_ids, default=m.SIGMA_DEFAULT,
    )
    sigma_source = "CUSTOM" if float(sigma) != m.SIGMA_DEFAULT else "MODEL_DEFAULT"
    try:
        l3b = m.level3_effective_reach(
            l3a["R_1p"], I_scope,
            sigma=float(sigma), sigma_source=sigma_source,
            hard_cap=None if cap in (None, "") else int(cap),
            measured_exact=measured_freq,
        )
    except (m.ReachValidationError, m.ReachCalculationError) as exc:
        raise V16Error(f"{scope_id}: {exc}") from exc
    diagnostics.append({
        "code": "L3B_EFFECTIVE_REACH",
        "level": 3,
        "scope_id": scope_id,
        "platform": platform,
        "flight_id": flight_id,
        "source_refs": source_refs,
        "I_scope": l3b["impressions"],
        "R_1p": l3b["reach_1p"],
        "F_human": l3b["avg_frequency"],
        "model": l3b["frequency_model"],
        "sigma": l3b["sigma"],
        "sigma_source": l3b["sigma_source"],
        "mu": l3b["mu"],
        "solver_iterations": l3b["solver_iterations_frequency"],
        "solver_residual": l3b["solver_residual_frequency"],
        "frequency_model_assumed": l3b["frequency_model_assumed"],
        "cap": l3b["cap"],
    })

    U_i_raw = _lookup_platform_input(
        q, "inventory_universes", plan_id, flight_id,
        scope_id, platform, row_ids, default=None,
    )
    U_i = U if U_i_raw in (None, "", 0, "0") else m.positive(
        U_i_raw, f"U_i {scope_id}"
    )
    if U_i > U + m.NUMERICAL_TOL or l3b["reach_1p"] > U_i + m.NUMERICAL_TOL:
        raise V16Error(f"{scope_id}: требуется Reach ≤ U_i ≤ U.")

    start = min((r.start for r in rows if r.start), default=None)
    end = max((r.end for r in rows if r.end), default=None)
    return {
        "name": platform,
        "unit_id": scope_id,
        "platform_scope_id": scope_id,
        "source_row_ids": row_ids,
        "source_refs": source_refs,
        "fragment_count": len(rows),
        "family": family,
        "platform": platform,
        "channel": channel,
        "reach_1p": l3b["reach_1p"],
        "reach_2p": l3b["reach_2p"],
        "reach_3p": l3b["reach_3p"],
        "reach_4p": l3b["reach_4p"],
        "reach_5p": l3b["reach_5p"],
        "reach_6p": l3b["reach_6p"],
        "impressions": l3b["impressions"],
        "freq_dist": l3b["freq_dist"],
        "exact_counts": l3b["exact_counts"],
        "avg_frequency": l3b["avg_frequency"],
        "start": start,
        "end": end,
        "l2": l2_summary,
        "l3a": l3a,
        "l3b": {
            k: l3b.get(k)
            for k in (
                "frequency_model", "frequency_model_assumed", "sigma", "sigma_source",
                "mu", "solver_iterations_frequency", "solver_residual_frequency", "cap",
            )
        },
        "addressable_universe": U_i,
        "addressable_universe_assumed": U_i_raw in (None, "", 0, "0"),
        "inventory_universe_source": (
            "MODEL_DEFAULT_ASSUMED_FAMILY_OR_U"
            if U_i_raw in (None, "", 0, "0") else "USER_INPUT"
        ),
    }





def _build_level4_channels(
    rows: Sequence[Any], U: float, cfg: dict, q: dict, plan_id: str,
    flight_id: str, diagnostics: List[dict],
) -> List[dict]:
    units = [
        _platform_entity(group, U, cfg, q, plan_id, flight_id, diagnostics)
        for group in _platform_groups(rows)
    ]
    by_channel: Dict[str, List[dict]] = defaultdict(list)
    for unit in units:
        by_channel[unit["channel"]].append(unit)

    channels: List[dict] = []
    for channel_name, ch_units in by_channel.items():
        by_family: Dict[str, List[dict]] = defaultdict(list)
        for unit in ch_units:
            by_family[unit["family"]].append(unit)

        families: List[dict] = []
        family_diagnostics: List[dict] = []
        for family_name, fam_units in by_family.items():
            U_F_raw = _scope_value(
                q, "family_universes", plan_id,
                flight_id=flight_id, name=family_name, default=None,
            )
            U_F = U if U_F_raw in (None, "", 0, "0") else m.positive(
                U_F_raw, f"U_F {family_name}"
            )
            if U_F > U + m.NUMERICAL_TOL:
                raise V16Error(f"Audience Family {family_name}: U_F > U.")
            for ent in fam_units:
                explicit_ui = not bool(ent.get("addressable_universe_assumed"))
                if explicit_ui and float(ent["addressable_universe"]) > U_F + m.NUMERICAL_TOL:
                    raise V16Error(
                        f"Audience Family {family_name}: Inventory Unit U_i превышает U_F."
                    )
                if ent["reach_1p"] > min(U_F, float(ent["addressable_universe"])) + m.NUMERICAL_TOL:
                    raise V16Error(
                        f"Audience Family {family_name}: Inventory Unit Reach превышает addressable capacity."
                    )
                if not explicit_ui:
                    ent["addressable_universe"] = U_F

            specs = _pair_specs(
                q, "L4A", plan_id=plan_id, flight_id=flight_id, parent=family_name,
            )
            pair_details = _normalized_pair_details(
                fam_units, U_F, specs, default_rho=0.0,
            ) if specs else None
            fm = m.audience_merge(
                fam_units, U_F,
                pair_details=pair_details,
                neutral_unstructured=not bool(pair_details),
                model_path="L4A_FAMILY",
            )
            fm.update({
                "name": family_name,
                "family_id": family_name,
                "universe": U_F,
                "addressable_universe": U_F,
                "U_F_source": (
                    "MODEL_DEFAULT_ASSUMED_U"
                    if U_F_raw in (None, "", 0, "0") else "USER_INPUT"
                ),
                "inventory_units": fam_units,
                "D_family": fm["dedup_rate"],
            })
            families.append(fm)
            family_diagnostics.append({
                "family": family_name,
                "U_F": U_F,
                "U_F_source": fm["U_F_source"],
                "gross_reach_sum": fm["gross_reach_sum"],
                "reach": fm["reach_1p"],
                "D_family": fm["D_family"],
                "model_path": fm["model_path"],
                "pair_details": fm.get("pair_details"),
            })

        specs_b = _pair_specs(
            q, "L4B", plan_id=plan_id, flight_id=flight_id, parent=channel_name,
        )
        pair_b = _normalized_pair_details(
            families, U, specs_b, default_rho=0.0,
        ) if specs_b else None
        cm = m.audience_merge(
            families, U,
            pair_details=pair_b,
            neutral_unstructured=not bool(pair_b),
            model_path="L4B_CHANNEL",
        )
        U_c_raw = _scope_value(
            q, "channel_universes", plan_id,
            flight_id=flight_id, name=channel_name, default=None,
        )
        U_c = U if U_c_raw in (None, "", 0, "0") else m.positive(
            U_c_raw, f"U_c {channel_name}"
        )
        if U_c > U + m.NUMERICAL_TOL or cm["reach_1p"] > U_c + m.NUMERICAL_TOL:
            raise V16Error(f"Channel {channel_name}: требуется Reach ≤ U_c ≤ U.")
        cm.update({
            "name": channel_name,
            "families": families,
            "addressable_universe": U_c,
            "addressable_universe_assumed": U_c_raw in (None, "", 0, "0"),
            "U_c_source": (
                "MODEL_DEFAULT_ASSUMED_U"
                if U_c_raw in (None, "", 0, "0") else "USER_INPUT"
            ),
            "D_cross": 1.0 - cm["reach_1p"] / sum(f["reach_1p"] for f in families)
                if sum(f["reach_1p"] for f in families) > 0 else 0.0,
            "D_overall": 1.0 - cm["reach_1p"] / sum(u["reach_1p"] for u in ch_units)
                if sum(u["reach_1p"] for u in ch_units) > 0 else 0.0,
        })
        diagnostics.append({
            "code": "L4_CHANNEL",
            "level": 4,
            "flight_id": flight_id,
            "channel": channel_name,
            "U": U,
            "U_c": U_c,
            "U_c_source": cm["U_c_source"],
            "audience_family_mapping": [
                {
                    "unit_id": u["unit_id"],
                    "family": u["family"],
                    "source": "USER_CONFIRMED",
                    "fragment_count": u.get("fragment_count", 1),
                }
                for u in ch_units
            ],
            "families": family_diagnostics,
            "D_cross": cm["D_cross"],
            "D_overall": cm["D_overall"],
            "pair_details": cm.get("pair_details"),
            "model_path": cm["model_path"],
            "feasibility": cm.get("feasibility"),
            "solver_iterations": cm.get("solver_iterations"),
            "solver_residual": cm.get("solver_residual"),
        })
        channels.append(cm)
    return channels

def _flight_groups(plan) -> List[dict]:
    groups: List[dict] = []
    for f in plan.flights:
        start = f.period_start or (min((x[0] for x in f.intervals), default=None) if f.intervals else None)
        end = f.period_end or (max((x[1] for x in f.intervals), default=None) if f.intervals else None)
        groups.append({
            "id": f.id,
            "label": f.label,
            "start": start,
            "end": end,
            "ta_name": f.ta_name or "",
            "source_universe": f.universe,
            "source_universe_source": f.universe_source or "",
            "is_common": bool(f.is_common),
            "campaign": f.campaign or "",
        })
    groups.sort(key=lambda x: (x["start"] or dt.date.max, x["end"] or dt.date.max, x["id"]))
    return groups


_LINE_HINT_STOPWORDS = {
    "mediaplan", "media", "plan", "mp", "phd", "digital", "lab", "industries",
    "flight", "flights", "wave", "флайт", "флайты", "флаит", "волна",
    "персил", "persil", "final", "финал", "upd", "update", "версия", "version",
    "свеж", "свежий", "свежесть",
    "январь", "февраль", "март", "апрель", "май", "июнь", "июль", "август",
    "сентябрь", "октябрь", "ноябрь", "декабрь",
    "jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "sept",
    "oct", "nov", "dec",
}


def _sheet_line_hint_tokens(name: Any) -> set[str]:
    """Weak sheet-name identity hints used only to force review, never to auto-merge."""
    raw = norm(name)
    tokens = re.findall(r"[0-9a-zа-яё]+", raw, flags=re.IGNORECASE)
    out = set()
    for token in tokens:
        token = token.strip().lower().replace("ё", "е")
        if not token or token.isdigit() or token in _LINE_HINT_STOPWORDS:
            continue
        if re.fullmatch(r"(?:20)?\d{2}", token):
            continue
        if len(token) < 4:
            continue
        out.add(token)
    return out


def _line_identity_conflicts(groups: Sequence[Any]) -> List[dict]:
    """Find contradictory Campaign-vs-sheet line identity patterns.

    This is a validation/review detector only.  It never silently groups plans.
    """
    out: List[dict] = []
    for i in range(len(groups)):
        a = groups[i]
        a_line = str(getattr(a, "line", "") or getattr(a, "label", "") or "").strip()
        a_tokens = set()
        for sheet in getattr(a, "sheet_names", ()) or ():
            a_tokens |= _sheet_line_hint_tokens(sheet)
        if not a_tokens:
            continue
        for j in range(i + 1, len(groups)):
            b = groups[j]
            b_line = str(getattr(b, "line", "") or getattr(b, "label", "") or "").strip()
            if a_line and b_line and norm(a_line) == norm(b_line):
                continue
            b_tokens = set()
            for sheet in getattr(b, "sheet_names", ()) or ():
                b_tokens |= _sheet_line_hint_tokens(sheet)
            shared = sorted(a_tokens & b_tokens)
            if not shared:
                continue
            out.append({
                "code": "LINE_IDENTITY_HEADER_CONFLICT",
                "severity": "WARNING",
                "group_ids": [str(getattr(a, "id", "")), str(getattr(b, "id", ""))],
                "line_a": a_line,
                "line_b": b_line,
                "shared_sheet_markers": shared,
                "sheets_a": list(getattr(a, "sheet_names", ()) or ()),
                "sheets_b": list(getattr(b, "sheet_names", ()) or ()),
                "message": (
                    "Названия рабочих листов указывают на общий line marker, "
                    "но Campaign/Line headers формируют разные Lines. "
                    "Движок не объединяет их автоматически."
                ),
            })
    return out


def _line_scope_summary(groups: Sequence[dict]) -> dict:
    active = [g for g in groups if not g.get("is_common")]
    ta_map = {}
    for g in active:
        key = _norm_ta(g.get("ta_name"))
        if key:
            ta_map.setdefault(key, g.get("ta_name"))
    universes = []
    for g in active:
        u = g.get("source_universe")
        if u not in (None, "", 0, "0"):
            universes.append(float(u))
    distinct_u = []
    for u in universes:
        if not any(abs(u - x) <= max(1e-6, m.SOLVER_TOL * max(1.0, abs(u), abs(x))) for x in distinct_u):
            distinct_u.append(u)
    return {
        "source_tas": list(ta_map.values()),
        "source_universes": distinct_u,
        "ta_mismatch": len(ta_map) > 1,
        "universe_mismatch": len(distinct_u) > 1,
    }


def _validate_line_source_scope(
    groups: Sequence[dict],
    U: float,
    q: Mapping[str, Any],
    plan_id: str,
    diagnostics: Optional[List[dict]] = None,
) -> dict:
    """Validate Line-master scope before any Level-2/3 recalculation."""
    summary = _line_scope_summary(groups)
    if summary["ta_mismatch"]:
        detail = [
            {"flight": g.get("label"), "ta": g.get("ta_name")}
            for g in groups if not g.get("is_common")
        ]
        raise V16Error(
            "L6_SCOPE_TA_MISMATCH / TA_NORMALIZATION_REQUIRED: "
            "Flights внутри одной Line имеют разные ЦА. "
            "Подтверждение в интерфейсе не может просто переименовать такую ЦА; "
            "нужны upstream inputs, рассчитанные на одну Line Master TA. " + str(detail)
        )

    confirm_map = q.get("line_scope_confirmed") or {}
    confirmed = bool(confirm_map.get(plan_id)) if isinstance(confirm_map, Mapping) else False
    source_us = summary["source_universes"]
    tol = max(1e-6, m.SOLVER_TOL * max(1.0, abs(float(U))))

    source_differs_from_master = any(abs(float(u) - float(U)) > tol for u in source_us)
    if summary["universe_mismatch"] and not confirmed:
        raise V16Error(
            "L6_SCOPE_UNIVERSE_MISMATCH / LINE_MASTER_UNIVERSE_CONFIRMATION_REQUIRED: "
            f"Flights имеют разные source Universe {source_us}. "
            "Нельзя silently использовать Universe последнего Flight. "
            "Укажите Human Universe Line и подтвердите, что это одна и та же TA/geo/human-definition "
            "и все Flights должны быть пересчитаны upstream на этот U."
        )
    if source_differs_from_master and not summary["universe_mismatch"] and not confirmed:
        raise V16Error(
            "LINE_MASTER_UNIVERSE_OVERRIDE_CONFIRMATION_REQUIRED: "
            f"Source Universe={source_us}, заданный Line Universe={U}. "
            "Подтвердите нормализацию scope перед пересчётом."
        )

    if diagnostics is not None:
        diagnostics.append({
            "code": "LINE_SOURCE_SCOPE",
            "level": "SCOPE",
            "plan_id": plan_id,
            "source_tas": summary["source_tas"],
            "source_universes": source_us,
            "line_master_universe": U,
            "source_universe_mismatch": summary["universe_mismatch"],
            "line_scope_confirmed": confirmed,
            "universe_normalized": source_differs_from_master,
        })
        if source_differs_from_master and confirmed:
            diagnostics.append({
                "code": "LINE_UNIVERSE_NORMALIZED_USER_CONFIRMED",
                "level": "SCOPE",
                "plan_id": plan_id,
                "source_universes": source_us,
                "line_master_universe": U,
                "source": "USER_CONFIRMED",
            })
    return summary


def _attach_aon_slices(flights: List[dict], q: dict, plan_id: str, diagnostics: List[dict]) -> None:
    all_slices = q.get("aon_slices") or {}
    p_slices = all_slices.get(plan_id) if isinstance(all_slices, Mapping) else {}
    p_slices = p_slices if isinstance(p_slices, Mapping) else {}
    by_id = {f["flight_id"]: f for f in flights}
    for aon in flights:
        if not aon.get("is_common"):
            continue
        supplied = p_slices.get(aon["flight_id"]) if isinstance(p_slices, Mapping) else None
        if not isinstance(supplied, Mapping):
            continue
        slices = []
        for burst_id, reach in supplied.items():
            burst = by_id.get(str(burst_id))
            if burst is None or burst.get("is_common"):
                continue
            slices.append({
                "start": burst.get("start"),
                "end": burst.get("end"),
                "human_reach_1p_slice": m.finite(reach, "AON human Reach slice"),
                "source": "USER_INPUT",
                "burst_flight_id": burst_id,
            })
        aon["temporal_slices"] = slices
        if slices:
            diagnostics.append({
                "code": "AON_TEMPORAL_FOOTPRINT",
                "level": 6,
                "flight": aon["name"],
                "source": "USER_INPUT",
                "slices": slices,
            })


def calculate_line(plan, U: float, cfg: dict, q: dict, plan_id: str, diagnostics: List[dict]) -> dict:
    groups = _flight_groups(plan)
    _validate_line_source_scope(groups, U, q, plan_id, diagnostics)
    flights: List[dict] = []
    line_excluded_rows: List[dict] = []
    for g in groups:
        source_rows = list(plan.detail_rows([g["id"]]))
        excluded = _excluded_reach_rows(source_rows)
        if excluded:
            line_excluded_rows.extend(excluded)
            diagnostics.append({
                "code": "REACH_SCOPE_ROWS_EXCLUDED",
                "level": "SCOPE",
                "severity": "WARNING",
                "plan_id": plan_id,
                "flight_id": g["id"],
                "flight": g["label"],
                "count": len(excluded),
                "rows": excluded,
                "message": (
                    "Строки без полного Level-1/3 Reach input исключены из Reach scope. "
                    "Technical/Human Reach для них не придумывается."
                ),
            })
        rows = _reach_rows(source_rows)
        if not rows:
            diagnostics.append({
                "code": "NON_REACH_FLIGHT_SKIPPED",
                "level": "SCOPE",
                "severity": "INFO",
                "plan_id": plan_id,
                "flight_id": g["id"],
                "flight": g["label"],
                "message": "Flight не содержит ни одной строки с usable Reach input и не участвует в L4–L6.",
            })
            continue
        channels = _build_level4_channels(rows, U, cfg, q, plan_id, g["id"], diagnostics)

        l5_specs = _pair_specs(q, "L5", plan_id=plan_id, flight_id=g["id"])
        l5_pairs = _normalized_pair_details(
            channels, U, l5_specs, default_rho=m.RHO_CHANNEL_DEFAULT,
        ) if l5_specs else None
        flight = m.level5_flight(channels, U, custom_pairs=l5_pairs)

        U_f_raw = _scope_value(q, "flight_universes", plan_id, flight_id=g["id"], default=None)
        U_f = U if U_f_raw in (None, "", 0, "0") else m.positive(U_f_raw, f"U_f {g['label']}")
        if U_f > U + m.NUMERICAL_TOL or flight["reach_1p"] > U_f + m.NUMERICAL_TOL:
            raise V16Error(f"Flight {g['label']}: требуется Reach ≤ U_f ≤ U.")
        flight.update({
            "name": g["label"],
            "flight_id": g["id"],
            "start": g["start"],
            "end": g["end"],
            "is_common": g["is_common"],
            "ta_name": g["ta_name"],
            "channels": channels,
            "addressable_universe": U_f,
            "addressable_universe_assumed": U_f_raw in (None, "", 0, "0"),
        })
        atomic = sum(
            u["reach_1p"]
            for ch in channels
            for fam in ch.get("families", [])
            for u in fam.get("inventory_units", [])
        )
        flight["D_Campaign"] = 1.0 - flight["reach_1p"] / atomic if atomic > 0 else 0.0
        diagnostics.extend({
            **d,
            "flight": g["label"],
        } for d in flight.get("diagnostics", []))
        diagnostics.append({
            "code": "L5_FLIGHT",
            "level": 5,
            "flight": g["label"],
            "flight_id": g["id"],
            "U": U,
            "U_f": U_f,
            "channels": [ch["name"] for ch in channels],
            "rho_target": flight.get("rho_target"),
            "rho_effective": flight.get("rho_effective"),
            "lambda": flight.get("relaxation_lambda"),
            "pair_details": flight.get("pair_details"),
            "model_path": flight.get("model_path"),
            "feasibility": flight.get("feasibility"),
            "solver_iterations": flight.get("solver_iterations"),
            "solver_residual": flight.get("solver_residual"),
            "D_Flight": flight.get("D_Flight"),
            "D_Campaign": flight.get("D_Campaign"),
        })
        flights.append(flight)

    if not flights:
        raise V16Error(
            f"{plan.display_name or plan.line or plan_id}: NO_REACH_ELIGIBLE_MEDIA — "
            "не найдено ни одной строки с Impressions и (Technical Reach или Frequency)."
        )

    for a, b in zip(flights, flights[1:]):
        if a.get("end") and b.get("start") and m.gap_days(a["end"], b["start"]) == 0:
            diagnostics.append({
                "code": "CONTIGUOUS_FLIGHT_BOUNDARY_REVIEW",
                "level": 6,
                "severity": "WARNING",
                "flight_a": a["name"],
                "flight_b": b["name"],
                "message": "G=0. Если это один continuous delivery без реального burst boundary, его нужно нормализовать upstream.",
            })

    _attach_aon_slices(flights, q, plan_id, diagnostics)
    l6_specs = _pair_specs(q, "L6", plan_id=plan_id)
    l6_pairs = _pair_raw_by_index(flights, l6_specs) if l6_specs else None
    try:
        line = m.level6_line(flights, U, custom_pairs=l6_pairs)
    except (m.ReachValidationError, m.ReachCalculationError) as exc:
        raise V16Error(str(exc)) from exc
    diagnostics.extend(line.get("diagnostics") or [])
    diagnostics.append({
        "code": "L6_LINE",
        "level": 6,
        "U": U,
        "flights": [
            {"name": f["name"], "start": _date(f.get("start")), "end": _date(f.get("end")), "is_common": f.get("is_common")}
            for f in flights
        ],
        "pair_details": line.get("pair_details"),
        "lambda": line.get("flight_relaxation_lambda"),
        "chronological_incremental": line.get("chronological_incremental"),
        "model_path": line.get("model_path"),
        "feasibility": line.get("feasibility"),
        "solver_iterations": line.get("solver_iterations"),
        "solver_residual": line.get("solver_residual"),
        "D_L6": line.get("D_L6"),
    })

    ta_names = sorted({
        " ".join(str(g["ta_name"]).split())
        for g in groups if g.get("ta_name") and not g.get("is_common")
    })
    ta_name = ta_names[0] if len(ta_names) == 1 else (_plan_ta(plan) or plan.line or plan.display_name or "")
    line_start = min((f.get("start") for f in flights if f.get("start")), default=plan.period_start)
    line_end = max((f.get("end") for f in flights if f.get("end")), default=plan.period_end)

    U_l_raw = _scope_value(q, "line_universes", plan_id, default=None)
    U_l = U if U_l_raw in (None, "", 0, "0") else m.positive(U_l_raw, f"U_l {plan_id}")
    if U_l > U + m.NUMERICAL_TOL or line["reach_1p"] > U_l + m.NUMERICAL_TOL:
        raise V16Error(f"Line {plan_id}: требуется Reach ≤ U_l ≤ U.")

    line.update({
        "name": plan.line or plan.display_name or plan.campaign or "Line",
        "brand": plan.brand or "",
        "universe": U,
        "ta_name": ta_name,
        "start": line_start,
        "end": line_end,
        "planning_horizon_start": line_start,
        "planning_horizon_end": line_end,
        "flights": flights,
        "l2": {
            "requested_mode": cfg["requested_mode"],
            "K": cfg["K"], "K_source": cfg["K_source"],
            "B": cfg["B"], "B_source": cfg["B_source"],
            "D": cfg["D"], "D_source": cfg["D_source"],
            "L": cfg["L"], "L_source": cfg["L_source"],
            "B_min": cfg["B_min"], "B_max": cfg["B_max"],
            "D_min": cfg["D_min"], "D_max": cfg["D_max"],
            "age_range": cfg["age_range"],
        },
        "addressable_universe": U_l,
        "addressable_universe_assumed": U_l_raw in (None, "", 0, "0"),
        "line_universe_assumed": U_l_raw in (None, "", 0, "0"),
        "reach_scope_excluded_count": len(line_excluded_rows),
        "reach_scope_excluded_rows": line_excluded_rows,
    })
    return line


def _brand_merge(lines: Sequence[dict], U: float, diagnostics: List[dict], q: Optional[dict] = None) -> dict:
    q = q or {}
    if not lines:
        return m.level7_brand([], U)

    if not bool(q.get("brand_scope_confirmed")):
        raise V16Error(
            "BRAND_MASTER_SCOPE_CONFIRMATION_REQUIRED: подтвердите Brand Master TA / geo / horizon / human scope."
        )
    master_ta = str(q.get("brand_master_ta") or "").strip()
    master_geo = str(q.get("brand_master_geo") or "").strip()
    if not master_ta:
        raise V16Error("BRAND_MASTER_TA_REQUIRED: Brand Master TA должна быть задана явно.")
    if not master_geo:
        raise V16Error("BRAND_MASTER_GEO_REQUIRED: master geography должна быть задана явно.")
    horizon_start = _parse_scope_date(q.get("brand_horizon_start"), "Brand horizon start")
    horizon_end = _parse_scope_date(q.get("brand_horizon_end"), "Brand horizon end")
    if horizon_end < horizon_start:
        raise V16Error("Brand horizon end < start.")

    ta_keys = {_norm_ta(x.get("ta_name")) for x in lines if _norm_ta(x.get("ta_name"))}
    if len(ta_keys) > 1 or any(t != _norm_ta(master_ta) for t in ta_keys):
        raise V16Error(
            "TA_NORMALIZATION_REQUIRED: Lines должны быть upstream рассчитаны на явно заданную Brand Master TA."
        )
    for line in lines:
        ls, le = line.get("start"), line.get("end")
        if ls and ls < horizon_start or le and le > horizon_end:
            raise V16Error(
                f"PLANNING_HORIZON_MISMATCH: Line {line.get('label') or line.get('name')} выходит за Brand horizon."
            )

    mismatched_u = [
        {"line": x.get("label") or x.get("name"), "line_universe": x.get("universe")}
        for x in lines
        if abs(float(x.get("universe") or 0) - U) > max(1e-6, m.SOLVER_TOL * U)
    ]
    if mismatched_u:
        raise V16Error(
            "UNIVERSE_MISMATCH / TA_NORMALIZATION_REQUIRED: Brand Total нельзя строить из Line Reach, "
            "рассчитанных на другом Universe. Задайте единый Brand Master Universe всем Lines upstream. "
            + str(mismatched_u)
        )

    # Optional explicit line geographies are checked when supplied. Otherwise geo is
    # accepted only under the explicit Brand scope confirmation; the base parser does
    # not invent geography from free text.
    line_geos = q.get("line_geographies") or {}
    for line in lines:
        pid = line.get("plan_id")
        if isinstance(line_geos, Mapping) and pid in line_geos:
            geo = str(line_geos[pid] or "").strip()
            if not geo:
                raise V16Error(f"Line {pid}: empty geography input.")
            diagnostics.append({
                "code": "LINE_GEO_SCOPE",
                "level": 7,
                "plan_id": pid,
                "line_geo": geo,
                "brand_geo": master_geo,
                "source": "USER_INPUT",
            })

    l7_specs = _pair_specs(q, "L7")
    l7_pairs = _pair_raw_by_index(lines, l7_specs) if l7_specs else None
    addressability_map = q.get("brand_addressability_map")
    out = m.level7_brand(
        lines, U,
        custom_pairs=l7_pairs,
        addressability_map=addressability_map,
    )
    out["name"] = next((x.get("brand") for x in lines if x.get("brand")), "Brand")
    out["brand_master_ta"] = master_ta
    out["brand_master_geo"] = master_geo
    out["brand_horizon_start"] = horizon_start
    out["brand_horizon_end"] = horizon_end
    diagnostics.append({
        "code": "L7_BRAND",
        "level": 7,
        "U_B": U,
        "U_B_source": "USER_INPUT",
        "TA": master_ta,
        "geo": master_geo,
        "planning_horizon": [_date(horizon_start), _date(horizon_end)],
        "human_definition": "CANONICAL_HUMAN_V1_6",
        "scope_confirmation": "USER_CONFIRMED",
        "BrandAddressabilityMap": out.get("brand_addressability_status"),
        "pair_details": out.get("pair_details"),
        "model_path": out.get("model_path"),
        "feasibility": out.get("feasibility"),
        "solver_iterations": out.get("solver_iterations"),
        "solver_residual": out.get("solver_residual"),
        "D_L7": out.get("D_L7"),
    })
    return out


def _business_diagnostics(ds: Sequence[dict], brand_error: Optional[str]) -> List[dict]:
    out: List[dict] = []
    seen = set()

    def add(tag: str, level: Any, title: str, message: str, severity: str = "INFO"):
        key = (tag, str(level), title, message)
        if key in seen:
            return
        seen.add(key)
        out.append({
            "tag": tag, "level": level, "title": title,
            "message": message, "severity": severity,
        })

    for d in ds:
        code = str(d.get("code") or "")
        level = d.get("level")
        if code == "F_PRECISION_ASSUMED":
            add("MODEL DEFAULT", 1, "Точность Frequency не указана",
                "Для arithmetic validation принята точность 2 знака после запятой.", "INFO")
        elif code == "L2_QUICK" and d.get("reason"):
            add("FALLBACK", 2, "Level 2 рассчитан в Quick",
                f"Причина: {d.get('reason')}. K={d.get('K')}.", "WARNING")
        elif code in {"B_AVERAGED_APPROXIMATION", "D_AVERAGED_APPROXIMATION"}:
            add("APPROXIMATION", 2, code,
                "Сегментного Reach для нелинейного расчёта нет; применён разрешённый averaged fallback.", "WARNING")
        elif code == "SAFARI_CHURN_NOT_MODELLED":
            add("APPROXIMATION", 2, "Safari churn не моделировался Chromium L",
                "Для Safari/WebKit не задан отдельный validated L; browser churn 2A не применён.", "WARNING")
        elif code == "L3A_PLATFORM_FLIGHT" and d.get("model_path") == "AGGREGATE_FLIGHT_REACH_MODE":
            add("FALLBACK", 3, "Нет weekly Human Reach",
                "Использован AGGREGATE_FLIGHT_REACH_MODE; temporal week-by-week merge не запускался.", "WARNING")
        elif code == "L3A_PLATFORM_FLIGHT" and d.get("platform_universe_assumed"):
            add("MODEL DEFAULT", 3, "Platform Universe не измерен",
                "Использовано U_p = Human Universe U с assumed flag.", "INFO")
        elif code == "GLOBAL_FEASIBILITY_RELAXATION":
            add("GLOBAL FEASIBILITY RELAXATION", level, "Model-default overlap скорректирован",
                f"Применён единый λ={d.get('lambda'):.6g} только к MODEL_DEFAULT pairs.", "WARNING")
        elif code == "RESIDUAL_CAP_OVERRIDDEN_BY_GLOBAL_FEASIBILITY":
            add("RESIDUAL CAP OVERRIDE", 6, "Residual 10% превышен ради feasibility",
                f"Общий λ={d.get('lambda'):.6g}; hard feasibility имеет приоритет.", "WARNING")
        elif code == "AON_TEMPORAL_FOOTPRINT":
            add("USER INPUT", 6, "AON temporal footprint",
                "Для AON↔burst использован пользовательский deduplicated human Reach slice.", "INFO")
        elif code == "CONTIGUOUS_FLIGHT_BOUNDARY_REVIEW":
            add("VALIDATION REVIEW", 6, "Смежные Flights с G=0",
                d.get("message") or "Проверьте, не является ли это одним continuous delivery.", "WARNING")
        elif code == "DUPLICATE_LIKE_ROW_WARNING":
            add("DATA QUALITY", "IMPORT", "Похожие строки медиаплана",
                "Строки не удалялись автоматически. Проверьте, являются ли они реальными дублями.", "WARNING")
        elif code == "REACH_SCOPE_ROWS_EXCLUDED":
            add("SCOPE EXCLUSION", "SCOPE", "Часть медиаплана вне Reach scope",
                f"Исключено строк: {d.get('count')}. Для них нет полного Level-1/3 input; Reach не моделировался.", "WARNING")
        elif code == "SOURCE_REACH_CURVE_INVALID":
            add("DATA QUALITY", "IMPORT", "Невалидная source Reach-кривая",
                d.get("message") or "В исходном МП Reach @N+ нарушает монотонность.", "ERROR")
        elif code == "SOURCE_DATE_RANGE_INVALID":
            add("DATA QUALITY", "IMPORT", "Ошибка диапазона дат в исходном МП",
                d.get("message") or "Дата окончания раньше даты начала; silent repair запрещён.", "ERROR")
        elif code == "SOURCE_IMPORT_WARNING":
            add("DATA QUALITY", "IMPORT", "Предупреждение парсера",
                d.get("message") or "Источник требует проверки.", "WARNING")
        elif code in {"L4_CHANNEL", "L5_FLIGHT", "L6_LINE", "L7_BRAND"}:
            path = d.get("model_path")
            if path and ("MAXENT" in path or "ADDRESSABILITY_NEUTRAL" in path):
                add("MAXENT", level, "Joint audience model",
                    f"Использован {path}; global feasibility={d.get('feasibility')}.", "INFO")
    if brand_error:
        tag = "TA MISMATCH" if "TA_NORMALIZATION" in brand_error else (
            "UNIVERSE MISMATCH" if "UNIVERSE_MISMATCH" in brand_error else "VALIDATION ERROR"
        )
        add(tag, 7, "Brand Total заблокирован", brand_error, "ERROR")
    return out


def _hierarchy(lines: Sequence[dict], brand: Optional[dict], brand_u: Optional[float]) -> List[dict]:
    rows: List[dict] = []
    keys = ("impressions", "reach_1p", "reach_2p", "reach_3p", "reach_4p", "reach_5p", "reach_6p", "avg_frequency",
            "gross_reach_sum", "dedup_people", "dedup_rate", "model_path")
    for line in lines:
        for flight in line.get("flights", []):
            for channel in flight.get("channels", []):
                rows.append({
                    "level": "Channel",
                    "line": line.get("label") or line.get("name"),
                    "flight": flight.get("name"),
                    "name": channel.get("name"),
                    "universe": line["universe"],
                    **{k: channel.get(k) for k in keys},
                })
            rows.append({
                "level": "Flight",
                "line": line.get("label") or line.get("name"),
                "flight": flight.get("name"),
                "name": flight.get("name"),
                "universe": line["universe"],
                **{k: flight.get(k) for k in keys},
            })
        rows.append({
            "level": "Line",
            "line": line.get("label") or line.get("name"),
            "flight": "",
            "name": line.get("label") or line.get("name"),
            "universe": line["universe"],
            **{k: line.get(k) for k in keys},
        })
    if brand is not None and brand_u:
        rows.append({
            "level": "Brand",
            "line": "", "flight": "",
            "name": brand.get("name") or "Brand",
            "universe": brand_u,
            **{k: brand.get(k) for k in keys},
        })
    return rows


def _contribution_rows(lines: Sequence[dict], brand: Optional[dict]) -> List[dict]:
    rows: List[dict] = []
    for line in lines:
        for flight in line.get("flights", []):
            for channel in flight.get("channels", []):
                for c in channel.get("contributions", []) or []:
                    rows.append({
                        "scope": "Channel",
                        "parent": channel.get("name"),
                        "line": line.get("label"),
                        **c,
                        "parent_reach": channel.get("reach_1p"),
                    })
            for c in flight.get("contributions", []) or []:
                rows.append({
                    "scope": "Flight",
                    "parent": flight.get("name"),
                    "line": line.get("label"),
                    **c,
                    "parent_reach": flight.get("reach_1p"),
                })
        for c in line.get("contributions", []) or []:
            rows.append({
                "scope": "Line",
                "parent": line.get("label") or line.get("name"),
                "line": line.get("label"),
                **c,
                "parent_reach": line.get("reach_1p"),
            })
    if brand is not None:
        for c in brand.get("contributions", []) or []:
            rows.append({
                "scope": "Brand",
                "parent": brand.get("name") or "Brand",
                "line": "",
                **c,
                "parent_reach": brand.get("reach_1p"),
            })
    return rows


# ---------------------------------------------------------------------------
# JSON APIs used by the web tab
# ---------------------------------------------------------------------------

def discover(path: str) -> str:
    groups = discover_media_plan_groups(path)
    identity_conflicts = _line_identity_conflicts(groups)
    conflict_ids = {
        gid for item in identity_conflicts for gid in item.get("group_ids", [])
    }
    out = []
    for g in groups:
        plan = parse_media_plan(path, sheet_names=g.sheet_names)
        ta = _plan_ta(plan)
        units = _inventory_units(plan)
        excluded_units = _excluded_reach_rows(list(plan.detail_rows()))
        platform_scopes = _platform_scope_requirements(units)
        aon_pairs = []
        fs = _flight_groups(plan)
        reach_by_flight = {
            f["id"]: _reach_rows(list(plan.detail_rows([f["id"]])))
            for f in fs
        }
        for aon in [x for x in fs if x["is_common"] and reach_by_flight.get(x["id"])]:
            for burst in [x for x in fs if not x["is_common"] and reach_by_flight.get(x["id"])]:
                aon_pairs.append({
                    "aon_flight_id": aon["id"],
                    "aon_label": aon["label"],
                    "burst_flight_id": burst["id"],
                    "burst_label": burst["label"],
                    "burst_start": _date(burst["start"]),
                    "burst_end": _date(burst["end"]),
                    "input_required": False,
                    "auto_path": "MODELLED_FROM_SOURCE_DELIVERY",
                })
        scope = _line_scope_summary(fs)
        out.append({
            "id": g.id,
            "label": g.label,
            "sheet_names": list(g.sheet_names),
            "brand": g.brand,
            "line": g.line,
            "campaign": g.campaign,
            "universe": float(plan.universe) if plan.universe else None,
            "ta_name": ta,
            "period_start": _date(plan.period_start),
            "period_end": _date(plan.period_end),
            "flight_count": len(plan.flights),
            "placement_count": len(plan.detail_rows()),
            "advanced_recommended": recommended_advanced_factors(ta),
            "input_profile": _plan_input_profile(plan),
            "inventory_units": units,
            "excluded_reach_rows": excluded_units,
            "platform_scopes": platform_scopes,
            "aon_pairs": aon_pairs,
            "source_flights": [
                {
                    "id": f["id"],
                    "label": f["label"],
                    "ta_name": f["ta_name"],
                    "source_universe": f["source_universe"],
                    "source_universe_source": f["source_universe_source"],
                    "start": _date(f["start"]),
                    "end": _date(f["end"]),
                    "campaign": f["campaign"],
                }
                for f in fs if not f["is_common"]
            ],
            "source_ta_mismatch": scope["ta_mismatch"],
            "source_universe_mismatch": scope["universe_mismatch"],
            "line_identity_review_required": str(g.id) in conflict_ids,
            "import_warnings": (
                _duplicate_warnings(plan.detail_rows())
                + [
                    {
                        "code": (
                            str(w).split(":", 1)[0]
                            if str(w).startswith("SOURCE_")
                            else "SOURCE_IMPORT_WARNING"
                        ),
                        "level": "IMPORT",
                        "severity": "WARNING",
                        "message": str(w),
                    }
                    for w in (getattr(plan, "warnings", None) or [])
                ]
            ),
        })
    return _json({
        "version": VERSION,
        "plans": out,
        "line_identity_conflicts": identity_conflicts,
        "model_catalog": model_catalog(),
        "contract": {
            "brand_universe_required_for_brand_total": True,
            "family_mapping_confirmation_required": False,
            "unknown_environment_auto_path": "AUTO_CLASSIFY_THEN_QUICK_FALLBACK",
        },
    })


def calculate(path: str, params_json: str = "{}") -> str:
    q = json.loads(params_json or "{}")
    selected_ids = [str(x) for x in (q.get("selected_plan_ids") or [])]
    overrides = q.get("universes") or {}

    all_groups = discover_media_plan_groups(path)
    identity_conflicts = _line_identity_conflicts(all_groups)
    selected_set = set(selected_ids) if selected_ids else {str(g.id) for g in all_groups}
    identity_confirmed = q.get("line_identity_confirmed") or {}
    for item in identity_conflicts:
        involved = [gid for gid in item.get("group_ids", []) if gid in selected_set]
        if len(involved) >= 2:
            ok = (
                isinstance(identity_confirmed, Mapping)
                and all(bool(identity_confirmed.get(gid)) for gid in involved)
            )
            if not ok:
                raise V16Error(
                    "LINE_IDENTITY_HEADER_CONFLICT: "
                    f"{item.get('line_a')} ↔ {item.get('line_b')}; "
                    f"shared sheet markers={item.get('shared_sheet_markers')}. "
                    "Движок не имеет права автоматически решить, это одна Line или разные. "
                    "Проверьте исходные Campaign/Line headers и подтвердите текущую разбивку, "
                    "если Lines действительно разные."
                )
    groups = all_groups
    if selected_ids:
        groups = [g for g in groups if g.id in selected_ids]
    if not groups:
        raise V16Error("Не выбрано ни одной Line.")

    diagnostics: List[dict] = [{
        "code": "ENGINE_VERSION",
        "version": VERSION,
        "canonical_spec": "Reach Engine Levels 1–7 FINAL v1.6 · 07.09.2026",
        "production_052_isolated": True,
    }]
    lines: List[dict] = []

    for g in groups:
        plan = parse_media_plan(path, sheet_names=g.sheet_names)
        diagnostics.extend(_duplicate_warnings(plan.detail_rows()))
        for warning in (getattr(plan, "warnings", None) or []):
            message = str(warning)
            code = message.split(":", 1)[0] if message.startswith("SOURCE_") else "SOURCE_IMPORT_WARNING"
            diagnostics.append({
                "code": code,
                "level": "IMPORT",
                "severity": "WARNING",
                "plan_id": g.id,
                "message": message,
            })
        U = _plan_universe(plan, overrides.get(g.id))
        _validate_line_source_scope(_flight_groups(plan), U, q, g.id, None)
        cfg = _resolve_line_l2(plan, U, q, g.id)
        diagnostics.append({
            "code": "LINE_SCOPE",
            "level": "SCOPE",
            "plan_id": g.id,
            "U": U,
            "TA": cfg["ta_name"],
            "family_mapping_confirmed": _mapping_confirmed(q, g.id),
            "l2_requested_mode": cfg["requested_mode"],
        })
        line = calculate_line(plan, U, cfg, q, g.id, diagnostics)
        line["plan_id"] = g.id
        line["label"] = g.label
        lines.append(line)

    brand_raw = q.get("brand_universe")
    brand_confirmed = bool(q.get("brand_universe_confirmed"))
    brand: Optional[dict] = None
    brand_error: Optional[str] = None
    brand_U: Optional[float] = None

    if brand_raw in (None, "") or not brand_confirmed:
        brand_error = (
            "BRAND_MASTER_UNIVERSE_REQUIRED: Brand Total требует явный подтверждённый U_B. "
            "Max/сумма Line Universe не подставляются автоматически."
        )
        diagnostics.append({"code": "BRAND_TOTAL_BLOCKED", "level": 7, "message": brand_error})
    else:
        brand_U = m.positive(brand_raw, "Brand Master Universe U_B")
        try:
            brand = _brand_merge(lines, brand_U, diagnostics, q)
            brand["universe"] = brand_U
        except (V16Error, m.ReachValidationError, m.ReachCalculationError) as exc:
            brand_error = str(exc)
            diagnostics.append({"code": "BRAND_TOTAL_BLOCKED", "level": 7, "message": brand_error})

    status = "GO" if brand is not None else "PARTIAL"
    hierarchy = _hierarchy(lines, brand, brand_U)
    contribution_rows = _contribution_rows(lines, brand)
    business = _business_diagnostics(diagnostics, brand_error)

    return _json({
        "version": VERSION,
        "status": status,
        "lines": lines,
        "brand_total": brand,
        "brand_error": brand_error,
        "brand_universe": brand_U,
        "hierarchy": hierarchy,
        "contribution_rows": contribution_rows,
        "model_catalog": model_catalog(),
        "business_diagnostics": business,
        "diagnostics": diagnostics,
    })
