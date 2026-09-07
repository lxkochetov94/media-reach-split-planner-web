from __future__ import annotations

"""
Reach Engine v1.6 — canonical parser/orchestration adapter.

The mathematical source of truth lives in reach_v16_math.py and follows the final
07.09.2026 canonical Levels 1–7 specification.  This module only connects that
math to the existing LAB media-plan parser and exposes JSON APIs for the isolated
web tab.

Production Web 0.52 is intentionally not called or modified.
"""

import datetime as dt
import json
import math
import re
from collections import defaultdict
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
            "family_mapping": "USER_CONFIRMED_OR_REFERENCE_MAPPING",
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
            "aon": "requires deduplicated human temporal slice for AON↔burst",
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


def _plan_ta(plan) -> str:
    return next((f.ta_name for f in plan.flights if f.ta_name and not f.is_common), "")


def _plan_input_profile(plan) -> dict:
    rows = list(plan.detail_rows())
    durations = sorted(
        _duration_days(r.start, r.end) for r in rows if r.start and r.end
    )
    med = None
    if durations:
        n = len(durations)
        med = durations[n // 2] if n % 2 else (durations[n // 2 - 1] + durations[n // 2]) / 2
    return {
        "rows": len(rows),
        "supplied_reach_rows": sum(r.tech_reach is not None for r in rows),
        "impressions_rows": sum(r.impressions is not None for r in rows),
        "frequency_rows": sum(r.frequency is not None for r in rows),
        "impressions_frequency_rows": sum(r.impressions is not None and r.frequency is not None for r in rows),
        "l1_ready_rows": sum(
            r.tech_reach is not None or (r.impressions is not None and r.frequency is not None)
            for r in rows
        ),
        "dated_rows": sum(bool(r.start and r.end) for r in rows),
        "duration_days_min": min(durations) if durations else None,
        "duration_days_median": med,
        "duration_days_max": max(durations) if durations else None,
        "platforms": len({norm(_platform_label(r)) for r in rows}),
        "channels": len({norm(r.channel or "Other") for r in rows}),
    }


def _inventory_units(plan) -> List[dict]:
    units = []
    for row in plan.detail_rows():
        units.append({
            "id": _unit_id(row),
            "label": _unit_label(row),
            "sheet": row.sheet,
            "row": row.source_row + 1,
            "channel": row.channel or "Other",
            "platform": _platform_label(row),
            "format": row.format or "",
            "buying_model": row.buying_model or "",
            "start": _date(row.start),
            "end": _date(row.end),
            "suggested_family": _platform_label(row),
            "family_suggestion_source": "UI_SUGGESTION_REQUIRES_CONFIRMATION",
            "environment_suggestion": "UNKNOWN",
            "environment_source": "NOT_INFERRED",
            "has_impressions": row.impressions is not None,
            "has_frequency": row.frequency is not None,
            "has_technical_reach": row.tech_reach is not None,
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


def _l2_for_row(row, U: float, cfg: dict, diagnostics: List[dict]) -> dict:
    l1 = m.level1_technical(row.impressions, row.frequency, row.tech_reach, frequency_precision=None)
    for d in l1["diagnostics"]:
        diagnostics.append({**d, "level": 1, "sheet": row.sheet, "row": row.source_row + 1})
    rtech = l1["R_tech"]
    uid = _unit_id(row)
    requested = cfg["requested_mode"]

    environment = str(_lookup_unit_map(cfg["environments"], cfg["plan_id"], uid, "UNKNOWN") or "UNKNOWN").upper()
    browser_family = str(_lookup_unit_map(cfg["browser_families"], cfg["plan_id"], uid, "UNKNOWN") or "UNKNOWN").upper()
    unit_ud = _lookup_unit_map(cfg["unit_web_device_universes"], cfg["plan_id"], uid, None)
    line_ud = cfg["web_device_universes"].get(cfg["plan_id"])
    U_D = unit_ud if unit_ud not in (None, "", 0, "0") else line_ud
    device_reach = _lookup_unit_map(cfg["device_reaches"], cfg["plan_id"], uid, None)

    reason = None
    use_advanced = requested == "ADVANCED"
    if requested == "AUTO":
        if environment == "WEB":
            use_advanced = bool(U_D not in (None, "", 0, "0") and row.start and row.end and row.frequency is not None)
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
            "sheet": row.sheet, "row": row.source_row + 1,
            "unit_id": uid,
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
        raise V16Error(f"{row.sheet}:{row.source_row+1}: Advanced требует подтверждённую environment.")
    if environment == "WEB" and U_D in (None, "", 0, "0"):
        raise V16Error(f"{row.sheet}:{row.source_row+1}: Web Advanced требует U_D.")
    if environment == "WEB" and (not row.start or not row.end or row.frequency is None):
        raise V16Error(f"{row.sheet}:{row.source_row+1}: Web Advanced требует dates и Frequency.")
    if environment in {"MOBILE_APP", "CTV"} and device_reach in (None, ""):
        raise V16Error(f"{row.sheet}:{row.source_row+1}: {environment} Advanced требует device-level Reach.")

    try:
        adv = m.level2_advanced(
            rtech, U,
            environment=environment,
            duration_days=_duration_days(row.start, row.end) if row.start and row.end else None,
            frequency=row.frequency,
            web_device_universe=U_D,
            device_reach=device_reach,
            B=cfg["B"], D=cfg["D"], L=cfg["L"],
            browser_family=browser_family,
            safari_l=cfg.get("safari_l"),
            B_source=cfg["B_source"], D_source=cfg["D_source"],
        )
    except (m.ReachValidationError, m.ReachCalculationError) as exc:
        raise V16Error(f"{row.sheet}:{row.source_row+1}: {exc}") from exc
    diagnostics.append({
        "code": "L2_ADVANCED",
        "level": 2,
        "sheet": row.sheet, "row": row.source_row + 1,
        "unit_id": uid,
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
            **d,
            "sheet": row.sheet,
            "row": row.source_row + 1,
            "unit_id": uid,
        })
    return {
        "R_people": adv["R_people"],
        "mode": "ADVANCED",
        "environment": environment,
        "l1": l1,
        "details": adv,
        "fallback_reason": None,
    }


def _l3_for_row(row, U: float, l2out: dict, q: dict, plan_id: str, diagnostics: List[dict]) -> dict:
    uid = _unit_id(row)
    weekly_map = q.get("weekly_human_reaches") or {}
    weekly = _lookup_unit_map(weekly_map, plan_id, uid, None)
    up_map = q.get("platform_universes") or {}
    U_p = _lookup_unit_map(up_map, plan_id, uid, None)
    temporal_profiles = q.get("temporal_profiles") or {}
    prof = str(_lookup_unit_map(temporal_profiles, plan_id, uid, "BASE") or "BASE").upper()
    custom_rhos = q.get("temporal_rhos") or {}
    custom_rho = _lookup_unit_map(custom_rhos, plan_id, uid, None)

    if weekly:
        l3a = m.temporal_platform_reach(
            weekly, U, platform_universe=U_p,
            profile=prof, custom_rho=custom_rho,
        )
    else:
        l3a = m.aggregate_flight_reach_mode(
            l2out["R_people"], U, platform_universe=U_p,
        )
    diagnostics.append({
        "code": "L3A_PLATFORM_FLIGHT",
        "level": 3,
        "unit_id": uid,
        "sheet": row.sheet, "row": row.source_row + 1,
        "model_path": l3a["model_path"],
        "U": U, "U_p": l3a["U_p"],
        "platform_universe_assumed": l3a["platform_universe_assumed"],
        "temporal_profile": l3a.get("profile"),
        "rho_base": l3a.get("rho_base"),
        "rho_source": l3a.get("rho_source"),
        "incremental": l3a.get("incremental"),
    })

    measured_freq = _lookup_unit_map(q.get("measured_exact_frequency") or {}, plan_id, uid, None)
    cap = _lookup_unit_map(q.get("human_frequency_caps") or {}, plan_id, uid, None)
    sigma = _lookup_unit_map(q.get("sigmas") or {}, plan_id, uid, m.SIGMA_DEFAULT)
    sigma_source = "CUSTOM" if sigma != m.SIGMA_DEFAULT else "MODEL_DEFAULT"
    if row.impressions is None:
        raise V16Error(
            f"{row.sheet}:{row.source_row+1}: Level 3B требует Impressions того же scope "
            "или direct human frequency buckets."
        )
    l3b = m.level3_effective_reach(
        l3a["R_1p"], float(row.impressions),
        sigma=float(sigma), sigma_source=sigma_source,
        hard_cap=None if cap in (None, "") else int(cap),
        measured_exact=measured_freq,
    )
    diagnostics.append({
        "code": "L3B_EFFECTIVE_REACH",
        "level": 3,
        "unit_id": uid,
        "sheet": row.sheet, "row": row.source_row + 1,
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
    return {"l3a": l3a, "l3b": l3b}


def _mapping_for_plan(q: dict, plan_id: str) -> Mapping[str, str]:
    all_maps = q.get("family_mapping") or {}
    pmap = all_maps.get(plan_id)
    return pmap if isinstance(pmap, Mapping) else {}


def _mapping_confirmed(q: dict, plan_id: str) -> bool:
    flags = q.get("family_mapping_confirmed") or {}
    if isinstance(flags, Mapping):
        return bool(flags.get(plan_id))
    return False


def _inventory_entity(
    row, U: float, cfg: dict, q: dict, plan_id: str, diagnostics: List[dict],
) -> dict:
    uid = _unit_id(row)
    family_map = _mapping_for_plan(q, plan_id)
    if uid not in family_map or not str(family_map.get(uid) or "").strip():
        raise V16Error(
            f"AUDIENCE_FAMILY_MAPPING_REQUIRED: {uid} ({_unit_label(row)}). "
            "Движок не назначает Audience Family по названию площадки автоматически."
        )
    if not _mapping_confirmed(q, plan_id):
        raise V16Error(
            f"AUDIENCE_FAMILY_MAPPING_CONFIRMATION_REQUIRED: Line {plan_id}. "
            "Подтвердите mapping перед расчётом."
        )

    l2out = _l2_for_row(row, U, cfg, diagnostics)
    l3 = _l3_for_row(row, U, l2out, q, plan_id, diagnostics)
    l3b = l3["l3b"]
    return {
        "name": _unit_label(row),
        "unit_id": uid,
        "family": str(family_map[uid]).strip(),
        "platform": _platform_label(row),
        "channel": row.channel or "Other",
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
        "source_row": row.source_row + 1,
        "sheet": row.sheet,
        "start": row.start,
        "end": row.end,
        "l1": l2out["l1"],
        "l2": {
            "mode": l2out["mode"],
            "environment": l2out["environment"],
            "fallback_reason": l2out["fallback_reason"],
            **{k: v for k, v in l2out["details"].items() if k != "diagnostics"},
        },
        "l3a": l3["l3a"],
        "l3b": {
            k: l3b.get(k)
            for k in (
                "frequency_model", "frequency_model_assumed", "sigma", "sigma_source",
                "mu", "solver_iterations_frequency", "solver_residual_frequency", "cap",
            )
        },
    }


def _build_level4_channels(
    rows: Sequence[Any], U: float, cfg: dict, q: dict, plan_id: str, diagnostics: List[dict],
) -> List[dict]:
    units = [
        _inventory_entity(row, U, cfg, q, plan_id, diagnostics)
        for row in rows
    ]
    by_channel: Dict[str, List[dict]] = defaultdict(list)
    for unit in units:
        by_channel[unit["channel"]].append(unit)

    family_universes_all = q.get("family_universes") or {}
    p_family_u = family_universes_all.get(plan_id) if isinstance(family_universes_all, Mapping) else {}
    p_family_u = p_family_u if isinstance(p_family_u, Mapping) else {}

    channels: List[dict] = []
    for channel_name, ch_units in by_channel.items():
        by_family: Dict[str, List[dict]] = defaultdict(list)
        for unit in ch_units:
            by_family[unit["family"]].append(unit)

        families: List[dict] = []
        family_diagnostics: List[dict] = []
        for family_name, fam_units in by_family.items():
            U_F_raw = p_family_u.get(family_name)
            U_F = U if U_F_raw in (None, "", 0, "0") else m.positive(U_F_raw, f"U_F {family_name}")
            if U_F > U + m.NUMERICAL_TOL:
                raise V16Error(f"Audience Family {family_name}: U_F > U.")
            for ent in fam_units:
                if ent["reach_1p"] > U_F + m.NUMERICAL_TOL:
                    raise V16Error(
                        f"Audience Family {family_name}: Inventory Unit Reach превышает U_F."
                    )
                ent["addressable_universe"] = U_F
                ent["addressable_universe_assumed"] = U_F_raw in (None, "", 0, "0")

            fm = m.audience_merge(
                fam_units, U_F,
                neutral_unstructured=True,
                model_path="L4A_FAMILY",
            )
            fm.update({
                "name": family_name,
                "family_id": family_name,
                "universe": U_F,
                "addressable_universe": U_F,
                "U_F_source": "MODEL_DEFAULT_ASSUMED_U" if U_F_raw in (None, "", 0, "0") else "USER_INPUT",
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
            })

        if len(families) == 1:
            cm = m.audience_merge(families, U, model_path="L4B_CHANNEL")
        else:
            # Ordinary media plans do not contain measured M_ij / pair unions.
            # With no structured addressability inputs, canonical neutral path is exact
            # mutual independence relative to the common Human Universe.
            cm = m.audience_merge(
                families, U,
                neutral_unstructured=True,
                model_path="L4B_CHANNEL",
            )
        cm.update({
            "name": channel_name,
            "families": families,
            "addressable_universe": U,
            "addressable_universe_assumed": True,
            "D_cross": 1.0 - cm["reach_1p"] / sum(f["reach_1p"] for f in families)
                if sum(f["reach_1p"] for f in families) > 0 else 0.0,
            "D_overall": 1.0 - cm["reach_1p"] / sum(u["reach_1p"] for u in ch_units)
                if sum(u["reach_1p"] for u in ch_units) > 0 else 0.0,
        })
        diagnostics.append({
            "code": "L4_CHANNEL",
            "level": 4,
            "channel": channel_name,
            "U": U,
            "audience_family_mapping": [
                {"unit_id": u["unit_id"], "family": u["family"], "source": "USER_CONFIRMED"}
                for u in ch_units
            ],
            "families": family_diagnostics,
            "D_cross": cm["D_cross"],
            "D_overall": cm["D_overall"],
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
            "is_common": bool(f.is_common),
            "campaign": f.campaign or "",
        })
    groups.sort(key=lambda x: (x["start"] or dt.date.max, x["end"] or dt.date.max, x["id"]))
    return groups


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
    flights: List[dict] = []
    for g in groups:
        rows = list(plan.detail_rows([g["id"]]))
        channels = _build_level4_channels(rows, U, cfg, q, plan_id, diagnostics)
        flight = m.level5_flight(channels, U)
        flight.update({
            "name": g["label"],
            "flight_id": g["id"],
            "start": g["start"],
            "end": g["end"],
            "is_common": g["is_common"],
            "ta_name": g["ta_name"],
            "channels": channels,
            "addressable_universe": U,
            "addressable_universe_assumed": True,
        })
        atomic = sum(
            u["reach_1p"]
            for c in channels
            for fam in c.get("families", [])
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
            "U": U,
            "channels": [c["name"] for c in channels],
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

    # Do not silently merge contiguous parser flights.  Their boundary can be real.
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
    try:
        line = m.level6_line(flights, U)
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
    line.update({
        "name": plan.line or plan.display_name or plan.campaign or "Line",
        "brand": plan.brand or "",
        "universe": U,
        "ta_name": ta_name,
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
        "addressable_universe": U,
        "addressable_universe_assumed": True,
    })
    return line


def _brand_merge(lines: Sequence[dict], U: float, diagnostics: List[dict], q: Optional[dict] = None) -> dict:
    q = q or {}
    if not lines:
        return m.level7_brand([], U)

    ta_keys = {_norm_ta(x.get("ta_name")) for x in lines if _norm_ta(x.get("ta_name"))}
    if len(ta_keys) > 1:
        raise V16Error(
            "TA_NORMALIZATION_REQUIRED: Lines имеют разные ЦА. "
            "Все Lines должны быть пересчитаны upstream на Brand Master TA."
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

    addressability_map = q.get("brand_addressability_map")
    out = m.level7_brand(lines, U, addressability_map=addressability_map)
    out["name"] = next((x.get("brand") for x in lines if x.get("brand")), "Brand")
    diagnostics.append({
        "code": "L7_BRAND",
        "level": 7,
        "U_B": U,
        "U_B_source": "USER_INPUT",
        "TA": next(iter(ta_keys), ""),
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
    out = []
    for g in groups:
        plan = parse_media_plan(path, sheet_names=g.sheet_names)
        ta = _plan_ta(plan)
        units = _inventory_units(plan)
        aon_pairs = []
        fs = _flight_groups(plan)
        for aon in [x for x in fs if x["is_common"]]:
            for burst in [x for x in fs if not x["is_common"]]:
                aon_pairs.append({
                    "aon_flight_id": aon["id"],
                    "aon_label": aon["label"],
                    "burst_flight_id": burst["id"],
                    "burst_label": burst["label"],
                    "burst_start": _date(burst["start"]),
                    "burst_end": _date(burst["end"]),
                })
        out.append({
            "id": g.id,
            "label": g.label,
            "sheet_names": list(g.sheet_names),
            "brand": g.brand,
            "line": g.line,
            "campaign": g.campaign,
            "universe": float(plan.universe) if plan.universe else None,
            "ta_name": ta,
            "flight_count": len(plan.flights),
            "placement_count": len(plan.detail_rows()),
            "advanced_recommended": recommended_advanced_factors(ta),
            "input_profile": _plan_input_profile(plan),
            "inventory_units": units,
            "aon_pairs": aon_pairs,
            "import_warnings": _duplicate_warnings(plan.detail_rows()),
        })
    return _json({
        "version": VERSION,
        "plans": out,
        "model_catalog": model_catalog(),
        "contract": {
            "brand_universe_required_for_brand_total": True,
            "family_mapping_confirmation_required": True,
            "unknown_environment_auto_path": "QUICK_FALLBACK",
        },
    })


def calculate(path: str, params_json: str = "{}") -> str:
    q = json.loads(params_json or "{}")
    selected_ids = [str(x) for x in (q.get("selected_plan_ids") or [])]
    overrides = q.get("universes") or {}

    groups = discover_media_plan_groups(path)
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
        U = _plan_universe(plan, overrides.get(g.id))
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
