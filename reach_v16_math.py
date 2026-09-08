from __future__ import annotations

"""
Canonical mathematical core for Reach Engine v1.6.

This module is parser-agnostic.  It implements the mathematics fixed in
"Reach Engine / Methodology v1.6 · Levels 1–7 · 07.09.2026" and is loaded
only by the isolated Reach Engine tab.  Production Web 0.52 does not import it.
"""

import datetime as dt
import math
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

VERSION = "1.6"

# Canonical engineering defaults.
MAX_ENTITIES = 12
MAX_ITERATIONS = 10_000
FEASIBILITY_TOL = 1e-9
SOLVER_TOL = 1e-8
LAMBDA_TOL = 1e-6
NUMERICAL_TOL = SOLVER_TOL

K_DEFAULT = 2.44

# AUTO is intentionally the fast, planner-like path. Its baseline comes from the
# pre-v1.6 production planner defaults that were already used in this project, not
# from any Reach value found in the uploaded workbook.
AUTO_K_REFERENCE = 2.44
AUTO_COOKIE_PEOPLE_BASE = 2.1125083718004576
AUTO_LAG_VISIBLE_SHARE = 0.6566358687813219
AUTO_TARGET_AFFINITY = 0.65
AUTO_BASE_PEOPLE_FACTOR = (
    AUTO_TARGET_AFFINITY / (AUTO_COOKIE_PEOPLE_BASE * AUTO_LAG_VISIBLE_SHARE)
)

# Stable mass-planning reachability profile. These coefficients are fixed model
# defaults validated across the project's LAB/Persil planning fixtures; they are
# never read or fitted from the currently uploaded workbook.
AUTO_REACHABILITY = {
    1: 1.00,
    2: 0.77,
    3: 0.77,
    4: 0.65,
    5: 0.55,
    6: 0.45,
}

CHROMIUM_L_DEFAULT = 68.0
BASE_BROWSER = 1.80
BASE_DEVICE_FACTOR = 2.25
SIGMA_DEFAULT = 2.50
RHO_TEMPORAL = {"LOW": 0.50, "BASE": 0.65, "HIGH": 0.80, "NEUTRAL": 0.0}
RHO_CHANNEL_DEFAULT = -0.35
RHO_LINE_DEFAULT = 0.0
RESIDUAL_CAP = 0.10

AGE_B = ((12, 24, 1.80), (25, 34, 1.90), (35, 44, 1.90), (45, 54, 1.75), (55, 120, 1.60))
AGE_D = ((12, 24, 2.45), (25, 34, 2.35), (35, 44, 2.25), (45, 54, 2.15), (55, 120, 1.74))
DEVICE_B = {
    "SMARTPHONE": 1.85,
    "DESKTOP": 1.80,
    "LAPTOP": 1.80,
    "TABLET": 1.70,
    "CTV": None,
}
Q_TEMPORAL_POINTS = ((0, .20), (14, .15), (28, .125), (42, .10), (56, .05), (68, 0.0))
UNIVERSE_MULTIPLIER_POINTS = (
    (5_000_000.0, 2.50),
    (7_500_000.0, 2.25),
    (10_000_000.0, 2.00),
    (12_500_000.0, 1.50),
    (15_000_000.0, 1.00),
)


class ReachValidationError(ValueError):
    """Hard input/data-quality error. Inputs are never silently repaired."""


class ReachCalculationError(RuntimeError):
    """Numerical/solver failure after the input system passed validation."""


def finite(v: Any, name: str) -> float:
    try:
        x = float(v)
    except Exception as exc:
        raise ReachValidationError(f"{name}: ожидается число.") from exc
    if not math.isfinite(x):
        raise ReachValidationError(f"{name}: ожидается конечное число.")
    return x


def positive(v: Any, name: str) -> float:
    x = finite(v, name)
    if x <= 0:
        raise ReachValidationError(f"{name} должен быть > 0.")
    return x


def _normalize_probability(x: float, diagnostics: Optional[List[dict]] = None, label: str = "probability") -> float:
    if -NUMERICAL_TOL <= x < 0:
        if diagnostics is not None:
            diagnostics.append({"code": "NUMERICAL_NORMALIZATION", "field": label, "from": x, "to": 0.0})
        return 0.0
    if 1 < x <= 1 + NUMERICAL_TOL:
        if diagnostics is not None:
            diagnostics.append({"code": "NUMERICAL_NORMALIZATION", "field": label, "from": x, "to": 1.0})
        return 1.0
    if x < 0 or x > 1:
        raise ReachValidationError(f"{label}: вероятность вне диапазона 0…1 ({x}).")
    return x


# ---------------------------------------------------------------------------
# Level 1
# ---------------------------------------------------------------------------

def level1_technical(
    impressions: Optional[float],
    frequency: Optional[float],
    supplied_reach: Optional[float],
    *,
    frequency_precision: Optional[int] = None,
) -> dict:
    """Canonical Placement -> Technical Uniques contract."""
    I = None if impressions is None else finite(impressions, "Impressions")
    F = None if frequency is None else finite(frequency, "Average Frequency")
    R = None if supplied_reach is None else finite(supplied_reach, "Technical Reach")

    if I is not None and I < 0:
        raise ReachValidationError("Impressions < 0.")
    if F is not None and F < 1:
        raise ReachValidationError("Average Frequency должна быть >= 1.")
    if R is not None and R < 0:
        raise ReachValidationError("Technical Reach < 0.")

    flags: List[dict] = []
    p = frequency_precision
    if p is None:
        p = 2
        flags.append({"code": "F_PRECISION_ASSUMED", "precision": 2, "source": "MODEL_DEFAULT"})
    try:
        p = int(p)
    except Exception as exc:
        raise ReachValidationError("Frequency precision должна быть целым числом.") from exc
    if p < 0 or p > 12:
        raise ReachValidationError("Frequency precision должна быть в диапазоне 0…12.")
    epsilon = max(1e-6, 0.5 * (10.0 ** (-p)))

    if R is not None:
        if I is not None:
            if I == 0 and R > 0:
                raise ReachValidationError("I=0 при supplied Reach>0.")
            if I > 0 and R == 0:
                raise ReachValidationError("supplied Reach=0 при Impressions>0.")
            if R > I + NUMERICAL_TOL:
                raise ReachValidationError("supplied Reach превышает Impressions.")
        f_implied = None
        if I is not None and F is not None and R > 0:
            f_implied = I / R
            if abs(f_implied - F) > epsilon:
                raise ReachValidationError(
                    "ARITHMETIC_INCONSISTENCY: Impressions / supplied Reach "
                    f"= {f_implied:.8g}, но Frequency = {F:.8g}; tolerance={epsilon:.8g}."
                )
        return {
            "R_tech": R,
            "source": "USER_INPUT_SUPPLIED_REACH",
            "F_implied": f_implied,
            "frequency_precision": p,
            "frequency_tolerance": epsilon,
            "diagnostics": flags,
        }

    if I is None:
        raise ReachValidationError("Level 1: нужен supplied Reach либо Impressions + Frequency.")
    if I == 0:
        return {
            "R_tech": 0.0,
            "source": "DERIVED_I_OVER_F",
            "F_implied": F,
            "frequency_precision": p,
            "frequency_tolerance": epsilon,
            "diagnostics": flags,
        }
    if F is None:
        raise ReachValidationError("Level 1: при отсутствии supplied Reach требуется Frequency.")
    return {
        "R_tech": I / F,
        "source": "DERIVED_I_OVER_F",
        "F_implied": F,
        "frequency_precision": p,
        "frequency_tolerance": epsilon,
        "diagnostics": flags,
    }


# ---------------------------------------------------------------------------
# Level 2
# ---------------------------------------------------------------------------

def level2_auto(rtech: float, universe: float, k: float = K_DEFAULT) -> dict:
    """Fast planner-like Technical Reach -> people conversion.

    K is a user sensitivity coefficient around the reference 2.44. The baseline
    people factor is inherited from the project's earlier mass-planning model and
    is independent of any source Reach summary in the workbook.
    """
    rtech = finite(rtech, "R_tech")
    U = positive(universe, "Human Universe")
    K = finite(k, "K")
    if rtech < 0:
        raise ReachValidationError("R_tech < 0.")
    if K < 1:
        raise ReachValidationError("K должен быть >= 1.")
    factor = AUTO_BASE_PEOPLE_FACTOR * (AUTO_K_REFERENCE / K)
    r = rtech * factor
    if r > U + NUMERICAL_TOL:
        raise ReachValidationError(
            f"Level 2 AUTO: Human Reach {r:.0f} превышает Universe {U:.0f}."
        )
    return {
        "R_people": r,
        "mode": "AUTO",
        "K": K,
        "K_reference": AUTO_K_REFERENCE,
        "people_factor": factor,
        "base_people_factor": AUTO_BASE_PEOPLE_FACTOR,
        "K_source": "MODEL_DEFAULT" if abs(K - K_DEFAULT) <= 1e-12 else "USER_OVERRIDE",
        "diagnostics": [],
    }


def _auto_zt_poisson_lambda(mean_frequency: float) -> float:
    """Lambda for a zero-truncated Poisson with the requested exposed-user mean."""
    f = max(1.0000001, finite(mean_frequency, "Technical Frequency"))
    if f <= 1.000001:
        return 1e-6
    lo, hi = 1e-8, max(8.0, f * 2.0 + 2.0)
    for _ in range(90):
        mid = (lo + hi) / 2.0
        denom = 1.0 - math.exp(-mid)
        value = mid / denom if denom > 0 else 1.0
        if value < f:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2.0


def _auto_poisson_tail(lam: float, threshold: int) -> float:
    if threshold <= 0:
        return 1.0
    term = math.exp(-lam)
    cumulative = term
    for k in range(1, threshold):
        term *= lam / k
        cumulative += term
    return max(0.0, min(1.0, 1.0 - cumulative))


def auto_frequency_reach(
    reach_1p: float,
    impressions: float,
    technical_frequency: float,
) -> dict:
    """Fast AUTO @1+…@6+ curve from the plan's technical average frequency.

    Unlike Detailed Web, AUTO deliberately does not fit a Poisson-lognormal model to
    the inferred human frequency. It reproduces the simple planning convention:
    derive a zero-truncated Poisson contact curve from source Technical Frequency,
    then apply it to the independently estimated human @1+.
    """
    R = finite(reach_1p, "AUTO Reach 1+")
    I = finite(impressions, "AUTO Impressions")
    F = finite(technical_frequency, "AUTO Technical Frequency")
    if R < 0 or I < 0:
        raise ReachValidationError("Reach/Impressions не могут быть отрицательными.")
    if F < 1 - NUMERICAL_TOL:
        raise ReachValidationError("AUTO Technical Frequency должна быть >=1.")
    if R == 0:
        exact_counts = [0.0] * 6
        cumulative = [0.0] * 6
        exact = [1.0, 0, 0, 0, 0, 0]
        lam = None
    else:
        lam = _auto_zt_poisson_lambda(max(1.000001, F))
        p1 = _auto_poisson_tail(lam, 1)
        cumulative = []
        previous = R
        for threshold in range(1, 7):
            poisson_ratio = 1.0 if threshold == 1 else (
                _auto_poisson_tail(lam, threshold) / p1 if p1 > 0 else 0.0
            )
            ratio = poisson_ratio * AUTO_REACHABILITY.get(threshold, 1.0)
            value = min(previous, max(0.0, R * ratio))
            cumulative.append(value)
            previous = value
        exact_counts = [
            max(0.0, cumulative[k] - cumulative[k + 1]) for k in range(5)
        ] + [max(0.0, cumulative[5])]
        exact = [x / R for x in exact_counts]
    avg_human = I / R if R > 0 else None
    return {
        **{f"reach_{k+1}p": cumulative[k] for k in range(6)},
        "exact_counts": exact_counts,
        "freq_dist": exact,
        "impressions": I,
        "avg_frequency": avg_human,
        "frequency_model": "AUTO_ZT_POISSON_TECH_FREQUENCY",
        "frequency_model_assumed": True,
        "technical_frequency": F,
        "lambda": lam,
        "reachability_coefficients": dict(AUTO_REACHABILITY),
        "sigma": None,
        "sigma_source": None,
        "mu": None,
        "solver_iterations_frequency": 0,
        "solver_residual_frequency": 0.0,
        "cap": None,
    }


def level2_quick(rtech: float, universe: float, k: float = K_DEFAULT) -> dict:
    rtech = finite(rtech, "R_tech")
    U = positive(universe, "Human Universe")
    K = finite(k, "K")
    if rtech < 0:
        raise ReachValidationError("R_tech < 0.")
    if K < 1:
        raise ReachValidationError("K должен быть >= 1.")
    r = rtech / K
    if r > U + NUMERICAL_TOL:
        raise ReachValidationError(
            f"Level 2 Quick: Human Reach {r:.0f} превышает Universe {U:.0f}."
        )
    return {
        "R_people": r,
        "mode": "QUICK",
        "K": K,
        "K_source": "MODEL_DEFAULT" if abs(K - K_DEFAULT) <= 1e-12 else "USER_OVERRIDE",
        "diagnostics": [],
    }


def _age_value(age: int, bands: Sequence[Tuple[int, int, float]]) -> Optional[float]:
    return next((v for lo, hi, v in bands if lo <= age <= hi), None)


def age_weighted_factor(
    lo: int,
    hi: int,
    bands: Sequence[Tuple[int, int, float]],
    *,
    weights: Optional[Mapping[int, float]] = None,
) -> dict:
    if lo > hi:
        lo, hi = hi, lo
    if lo < 12:
        raise ReachValidationError("Автоматическая экстраполяция B/D для возраста младше 12 лет запрещена.")
    vals: List[Tuple[float, float]] = []
    for age in range(lo, hi + 1):
        val = _age_value(age, bands)
        if val is None:
            raise ReachValidationError(f"Нет модельного B/D для возраста {age}.")
        w = 1.0 if weights is None else float(weights.get(age, 0.0))
        if w < 0:
            raise ReachValidationError("Возрастной вес < 0.")
        vals.append((val, w))
    denom = sum(w for _, w in vals)
    if denom <= 0:
        raise ReachValidationError("Сумма возрастных весов должна быть > 0.")
    return {
        "value": sum(v * w for v, w in vals) / denom,
        "source": "AGE_DISTRIBUTION" if weights is not None else "AGE_WIDTH_APPROXIMATION",
        "approximation": weights is None,
        "min": min(v for v, _ in vals),
        "max": max(v for v, _ in vals),
    }


def _browser_saturation(r_stable: float, u_device: float, B: float) -> float:
    U_D = positive(u_device, "Web-device Universe U_D")
    B = finite(B, "Browser multiplicity B")
    if B < 1:
        raise ReachValidationError("Browser multiplicity B должна быть >= 1.")
    cap = U_D * B
    if r_stable > cap + NUMERICAL_TOL:
        raise ReachValidationError(
            f"Level 2B: R_stable {r_stable:.0f} превышает capacity U_D×B {cap:.0f}."
        )
    base = 1.0 - r_stable / cap
    if base < -NUMERICAL_TOL:
        raise ReachValidationError("Level 2B: отрицательное основание saturation.")
    base = max(0.0, base)
    return U_D * (1.0 - base ** B)


def _device_saturation(r_device: float, universe: float, D: float) -> float:
    U = positive(universe, "Human Universe")
    D = finite(D, "Device multiplicity D")
    if D < 1:
        raise ReachValidationError("Device multiplicity D должна быть >= 1.")
    cap = U * D
    if r_device > cap + NUMERICAL_TOL:
        raise ReachValidationError(
            f"Level 2C: R_device {r_device:.0f} превышает capacity U×D {cap:.0f}."
        )
    base = 1.0 - r_device / cap
    if base < -NUMERICAL_TOL:
        raise ReachValidationError("Level 2C: отрицательное основание saturation.")
    base = max(0.0, base)
    return U * (1.0 - base ** D)


def level2_advanced(
    rtech: float,
    universe: float,
    *,
    environment: str,
    duration_days: Optional[float] = None,
    frequency: Optional[float] = None,
    web_device_universe: Optional[float] = None,
    device_reach: Optional[float] = None,
    B: Optional[float] = None,
    D: Optional[float] = None,
    L: Optional[float] = None,
    browser_family: str = "CHROMIUM",
    safari_l: Optional[float] = None,
    browser_segments: Optional[Sequence[dict]] = None,
    device_segments: Optional[Sequence[dict]] = None,
    B_source: str = "MODEL_DEFAULT",
    D_source: str = "MODEL_DEFAULT",
) -> dict:
    """Advanced Level 2 with explicit environment semantics.

    browser_segments entries: {r_stable, U_D, B, weight?}.  Each segment is transformed
    BEFORE aggregation.  device_segments entries: {r_device, U, D}.  They are also
    transformed before aggregation.
    """
    rtech = finite(rtech, "R_tech")
    U = positive(universe, "Human Universe")
    if rtech < 0:
        raise ReachValidationError("R_tech < 0.")
    env = str(environment or "").strip().upper()
    if env not in {"WEB", "MOBILE_APP", "CTV", "UNKNOWN"}:
        raise ReachValidationError("environment должен быть WEB, MOBILE_APP, CTV или UNKNOWN.")
    if env == "UNKNOWN":
        raise ReachValidationError("Advanced Level 2 требует подтверждённую environment segmentation.")

    diagnostics: List[dict] = []
    path: List[str] = []
    K_time = 1.0
    r_stable = None

    if env == "WEB":
        if duration_days is None or frequency is None:
            raise ReachValidationError("Web Advanced требует duration_days и Frequency.")
        T = positive(duration_days, "T")
        F = finite(frequency, "Average Frequency")
        if F < 1:
            raise ReachValidationError("Average Frequency должна быть >= 1.")

        browser = str(browser_family or "CHROMIUM").upper()
        L_eff: Optional[float]
        if "SAFARI" in browser or "WEBKIT" in browser:
            if safari_l is None:
                L_eff = None
                K_time = 1.0
                diagnostics.append({
                    "code": "SAFARI_CHURN_NOT_MODELLED",
                    "level": 2,
                    "source": "FALLBACK",
                    "message": "Chromium L=68 не применён к Safari/WebKit без валидированного Safari L.",
                })
            else:
                L_eff = positive(safari_l, "Safari L")
        elif browser in {"UNKNOWN", "MIXED", ""}:
            L_eff = None
            K_time = 1.0
            diagnostics.append({
                "code": "BROWSER_CHURN_NOT_MODELLED_UNKNOWN_MIX",
                "level": 2,
                "source": "APPROXIMATION",
                "message": "Browser identity mix не подтверждён; Chromium L=68 не применён автоматически.",
            })
        else:
            L_eff = positive(CHROMIUM_L_DEFAULT if L is None else L, "Chromium L")

        if L_eff is not None and F > 1:
            K_time = 1.0 + (F - 1.0) * (1.0 - 2.0 ** (-T / (L_eff * F)))
        r_stable = rtech / K_time
        path.append("2A_BROWSER_CHURN" if L_eff is not None else "2A_SKIPPED_SAFARI_NO_L")

        if browser_segments:
            r_device_total = 0.0
            for idx, seg in enumerate(browser_segments, 1):
                rs = finite(seg.get("r_stable"), f"browser_segment[{idx}].r_stable")
                ud = positive(seg.get("U_D"), f"browser_segment[{idx}].U_D")
                b = finite(seg.get("B"), f"browser_segment[{idx}].B")
                r_device_total += _browser_saturation(rs, ud, b)
            r_device = r_device_total
            diagnostics.append({"code": "B_SEGMENTED_NONLINEAR", "level": 2, "segments": len(browser_segments)})
        else:
            if web_device_universe is None:
                raise ReachValidationError("Web Advanced 2B требует Web-device Universe U_D.")
            b = BASE_BROWSER if B is None else finite(B, "B")
            r_device = _browser_saturation(r_stable, web_device_universe, b)
            diagnostics.append({
                "code": "B_AVERAGED_APPROXIMATION",
                "level": 2,
                "B": b,
                "source": B_source,
            })
        path.append("2B_BROWSER_SATURATION")

    elif env in {"MOBILE_APP", "CTV"}:
        # Canonical rule: no browser churn/browser multiplicity.  Advanced may continue
        # only when an actual device-level Reach for the same scope is available.
        if device_reach is None:
            raise ReachValidationError(
                f"{env}: Advanced Level 2 требует device-level Reach; "
                "technical app/CTV IDs нельзя автоматически объявить устройствами."
            )
        r_device = finite(device_reach, "Device Reach")
        if r_device < 0:
            raise ReachValidationError("Device Reach < 0.")
        path.extend(["2A_NOT_APPLICABLE", "2B_NOT_APPLICABLE"])
        if env == "CTV":
            diagnostics.append({
                "code": "CTV_COVIEWING_OUTSIDE_LEVEL2",
                "level": 2,
                "source": "METHODOLOGY",
            })

    if device_segments:
        r_people_total = 0.0
        segment_u_total = 0.0
        for idx, seg in enumerate(device_segments, 1):
            rd = finite(seg.get("r_device"), f"device_segment[{idx}].r_device")
            su = positive(seg.get("U"), f"device_segment[{idx}].U")
            sd = finite(seg.get("D"), f"device_segment[{idx}].D")
            r_people_total += _device_saturation(rd, su, sd)
            segment_u_total += su
        if segment_u_total > U + NUMERICAL_TOL:
            raise ReachValidationError("Сумма segment Human Universes превышает общий Human Universe.")
        r_people = r_people_total
        diagnostics.append({"code": "D_SEGMENTED_NONLINEAR", "level": 2, "segments": len(device_segments)})
    else:
        d = BASE_DEVICE_FACTOR if D is None else finite(D, "D")
        r_people = _device_saturation(r_device, U, d)
        diagnostics.append({
            "code": "D_AVERAGED_APPROXIMATION",
            "level": 2,
            "D": d,
            "source": D_source,
        })
    path.append("2C_DEVICE_SATURATION")

    if r_people > U + NUMERICAL_TOL:
        raise ReachValidationError("Level 2 Advanced: Human Reach превышает Universe.")
    return {
        "R_people": r_people,
        "R_stable": r_stable,
        "R_device": r_device,
        "K_time": K_time,
        "mode": "ADVANCED",
        "environment": env,
        "path": path,
        "diagnostics": diagnostics,
    }


# ---------------------------------------------------------------------------
# Level 3A — temporal platform-flight Reach
# ---------------------------------------------------------------------------

def temporal_platform_reach(
    weekly: Sequence[dict],
    universe: float,
    *,
    platform_universe: Optional[float] = None,
    profile: str = "BASE",
    custom_rho: Optional[float] = None,
) -> dict:
    U = positive(universe, "Human Universe")
    U_p = U if platform_universe is None else positive(platform_universe, "Platform Universe U_p")
    if U_p > U + NUMERICAL_TOL:
        raise ReachValidationError("U_p не может превышать Human Universe U.")

    prof = str(profile or "BASE").upper()
    if prof == "CUSTOM":
        if custom_rho is None:
            raise ReachValidationError("CUSTOM temporal profile требует rho.")
        rho = finite(custom_rho, "rho_base")
        source = "CUSTOM"
    else:
        if prof not in RHO_TEMPORAL:
            raise ReachValidationError("Temporal profile должен быть LOW, BASE, HIGH, NEUTRAL или CUSTOM.")
        rho = RHO_TEMPORAL[prof]
        source = "MARKET_BENCHMARK" if prof in {"LOW", "BASE", "HIGH"} else "DIAGNOSTIC"
    if not (0 <= rho <= 1):
        raise ReachValidationError("rho_base должен быть в диапазоне 0…1.")

    items = []
    for idx, raw in enumerate(weekly, 1):
        R = finite(raw.get("reach"), f"week[{idx}].reach")
        if R < 0 or R > U_p + NUMERICAL_TOL:
            raise ReachValidationError(f"week[{idx}] Reach должен быть в диапазоне 0…U_p.")
        order = raw.get("week_index", idx)
        try:
            order = int(order)
        except Exception as exc:
            raise ReachValidationError("week_index должен быть целым.") from exc
        if order < 0:
            raise ReachValidationError("week_index < 0.")
        items.append((order, R, raw))
    items.sort(key=lambda x: x[0])

    if not items:
        return {
            "R_1p": 0.0,
            "incremental": [],
            "U": U,
            "U_p": U_p,
            "platform_universe_assumed": platform_universe is None,
            "profile": prof,
            "rho_base": rho,
            "rho_source": source,
            "model_path": "WEEKLY_TEMPORAL",
        }

    first_order, first_R, _ = items[0]
    p_prev = first_R / U_p if U_p > 0 else 0.0
    Z = 1.0 - p_prev
    C = first_R
    rows = [{
        "week_index": first_order,
        "weekly_reach": first_R,
        "gap_weeks": None,
        "rho_eff": None,
        "j_ind": None,
        "j_max": None,
        "j": None,
        "b": None,
        "incremental_reach": first_R,
        "cumulative_reach": C,
    }]

    prev_order = first_order
    for order, R, _raw in items[1:]:
        p = R / U_p
        gap = max(0, order - prev_order - 1)
        rho_eff = rho ** (1 + gap)
        j_ind = p_prev * p
        j_max = min(p_prev, p)
        j = j_ind + rho_eff * (j_max - j_ind)

        if p_prev >= 1 - NUMERICAL_TOL:
            b = 0.0
            inc = 0.0
            Z = 0.0
            C = U_p
        else:
            b = (p - j) / (1.0 - p_prev)
            if b < -NUMERICAL_TOL or b > 1 + NUMERICAL_TOL:
                raise ReachValidationError(
                    f"Level 3A: derived b_t={b} вне 0…1; проверьте weekly Reach/rho/scope."
                )
            b = min(1.0, max(0.0, b))
            inc = U_p * Z * b
            Z = Z * (1.0 - b)
            C_new = U_p * (1.0 - Z)
            if C_new + NUMERICAL_TOL < C:
                raise ReachCalculationError("Level 3A: cumulative Reach уменьшился.")
            C = C_new

        if inc < -NUMERICAL_TOL or inc > R + NUMERICAL_TOL:
            raise ReachCalculationError("Level 3A: Incremental Reach вышел за 0…weekly Reach.")
        rows.append({
            "week_index": order,
            "weekly_reach": R,
            "gap_weeks": gap,
            "rho_eff": rho_eff,
            "j_ind": j_ind,
            "j_max": j_max,
            "j": j,
            "b": b,
            "incremental_reach": max(0.0, inc),
            "cumulative_reach": C,
        })
        p_prev = p
        prev_order = order

    if C > U_p + NUMERICAL_TOL:
        raise ReachCalculationError("Level 3A: Platform Flight Reach превышает U_p.")
    return {
        "R_1p": C,
        "incremental": rows,
        "U": U,
        "U_p": U_p,
        "platform_universe_assumed": platform_universe is None,
        "profile": prof,
        "rho_base": rho,
        "rho_source": source,
        "model_path": "WEEKLY_TEMPORAL",
    }


def aggregate_flight_reach_mode(r_people_flight: float, universe: float, *, platform_universe: Optional[float] = None) -> dict:
    U = positive(universe, "Human Universe")
    U_p = U if platform_universe is None else positive(platform_universe, "Platform Universe U_p")
    R = finite(r_people_flight, "R_people,flight")
    if U_p > U + NUMERICAL_TOL:
        raise ReachValidationError("U_p > U.")
    if R < 0 or R > U_p + NUMERICAL_TOL:
        raise ReachValidationError("Aggregate Flight Human Reach должен быть в диапазоне 0…U_p.")
    return {
        "R_1p": R,
        "incremental": [],
        "U": U,
        "U_p": U_p,
        "platform_universe_assumed": platform_universe is None,
        "profile": None,
        "rho_base": None,
        "rho_source": None,
        "model_path": "AGGREGATE_FLIGHT_REACH_MODE",
    }


# ---------------------------------------------------------------------------
# Level 3B — Poisson-Lognormal effective frequency
# ---------------------------------------------------------------------------

def _normal_grid(n: int = 481, lo: float = -10.0, hi: float = 10.0) -> Tuple[List[float], List[float]]:
    step = (hi - lo) / (n - 1)
    z = [lo + i * step for i in range(n)]
    w: List[float] = []
    c = 1.0 / math.sqrt(2.0 * math.pi)
    for i, x in enumerate(z):
        simpson = 1 if i in (0, n - 1) else (4 if i % 2 else 2)
        w.append(simpson * c * math.exp(-0.5 * x * x) * step / 3.0)
    s = sum(w)
    return z, [x / s for x in w]


_Z, _ZW = _normal_grid()


def _pl_unconditional(mu: float, sigma: float, max_n: int = 5) -> Tuple[float, float, List[float]]:
    probs = [0.0] * (max_n + 1)
    mean = 0.0
    for z, wz in zip(_Z, _ZW):
        lam = math.exp(mu + sigma * z)
        mean += wz * lam
        term = math.exp(-lam)
        probs[0] += wz * term
        for k in range(1, max_n + 1):
            term *= lam / k
            probs[k] += wz * term
    return mean, probs[0], probs


def _truncated_distribution(mu: float, sigma: float, cap: int) -> Tuple[float, List[float]]:
    if cap < 1:
        raise ReachValidationError("Human frequency cap должен быть >= 1.")
    raw = [0.0] * (cap + 1)
    for z, wz in zip(_Z, _ZW):
        lam = math.exp(mu + sigma * z)
        term = math.exp(-lam)
        for k in range(1, cap + 1):
            term *= lam / k
            raw[k] += wz * term
    mass = sum(raw[1:])
    if mass <= 1e-300:
        return float("inf"), [0.0] * cap
    cond = [raw[k] / mass for k in range(1, cap + 1)]
    mean = sum((k + 1) * p for k, p in enumerate(cond))
    return mean, cond


def poisson_lognormal_frequency(
    mean_frequency: float,
    sigma: float = SIGMA_DEFAULT,
    *,
    cap: Optional[int] = None,
) -> dict:
    f = finite(mean_frequency, "Human Average Frequency")
    s = positive(sigma, "sigma")
    if f < 1 - NUMERICAL_TOL:
        raise ReachValidationError("Human Average Frequency < 1: несовместимые Reach/Impressions.")
    if abs(f - 1.0) <= NUMERICAL_TOL:
        return {
            "exact": [1.0, 0.0, 0.0, 0.0, 0.0, 0.0],
            "mu": None,
            "sigma": s,
            "solver_iterations": 0,
            "solver_residual": 0.0,
            "model": "DEGENERATE_FREQUENCY_1",
            "cap": cap,
        }

    C = None if cap is None else int(cap)
    if C is not None:
        if C < 1:
            raise ReachValidationError("Human frequency cap должен быть >= 1.")
        if f > C + NUMERICAL_TOL:
            raise ReachValidationError("Human Average Frequency превышает подтверждённый hard cap.")

    lo, hi = -24.0, 12.0
    residual = None
    iterations = 0
    final_dist: Optional[List[float]] = None

    def conditional_mean_at(mu_value: float):
        if C is None:
            mean_value, p0_value, probs_value = _pl_unconditional(mu_value, s, 5)
            return mean_value / max(1e-300, 1.0 - p0_value), probs_value
        mean_value, dist_value = _truncated_distribution(mu_value, s, C)
        return mean_value, dist_value

    # Hard-cap conditioning can require a very large μ when σ is heavy-tailed.
    # Bracket the requested mean deterministically instead of assuming hi=12.
    hi_mean, _ = conditional_mean_at(hi)
    while hi_mean < f - 1e-10 and hi < 30.0:
        hi += 2.0
        hi_mean, _ = conditional_mean_at(hi)
    if hi_mean < f - 1e-10:
        raise ReachCalculationError(
            "Poisson-Lognormal cap solver: target mean cannot be bracketed "
            f"for sigma={s}, cap={C}, target={f}."
        )

    for iterations in range(1, 181):
        mid = (lo + hi) / 2.0
        cond_mean, dist = conditional_mean_at(mid)
        residual = cond_mean - f
        if abs(residual) <= 1e-10:
            lo = hi = mid
            if C is not None:
                final_dist = dist
            break
        if cond_mean < f:
            lo = mid
        else:
            hi = mid
    mu = (lo + hi) / 2.0

    if C is None:
        mean, p0, probs = _pl_unconditional(mu, s, 5)
        denom = max(1e-300, 1.0 - p0)
        exact_1_5 = [probs[k] / denom for k in range(1, 6)]
        exact = exact_1_5 + [max(0.0, 1.0 - sum(exact_1_5))]
        cond_mean = mean / denom
    else:
        cond_mean, full = _truncated_distribution(mu, s, C)
        final_dist = full
        exact = [0.0] * 6
        for n, p in enumerate(full, 1):
            exact[min(6, n) - 1] += p

    total = sum(exact)
    if total <= 0:
        raise ReachCalculationError("Poisson-Lognormal: пустое conditional distribution.")
    exact = [max(0.0, p / total) for p in exact]
    residual = cond_mean - f
    if abs(residual) > SOLVER_TOL:
        raise ReachCalculationError(
            f"Poisson-Lognormal mu solver не сошёлся: residual={residual:.3g}."
        )
    return {
        "exact": exact,
        "mu": mu,
        "sigma": s,
        "solver_iterations": iterations,
        "solver_residual": residual,
        "model": "POISSON_LOGNORMAL",
        "cap": C,
    }


def level3_effective_reach(
    reach_1p: float,
    impressions: float,
    *,
    sigma: float = SIGMA_DEFAULT,
    sigma_source: str = "MODEL_DEFAULT",
    hard_cap: Optional[int] = None,
    measured_exact: Optional[Sequence[float]] = None,
) -> dict:
    R = finite(reach_1p, "Platform Flight Reach 1+")
    I = finite(impressions, "I_scope")
    if R < 0 or I < 0:
        raise ReachValidationError("Reach/Impressions не могут быть отрицательными.")
    if R == 0:
        if I > NUMERICAL_TOL:
            raise ReachValidationError("Reach 1+=0 при Impressions>0.")
        exact = [0.0] * 6
        freq_meta = {"model": "EMPTY", "mu": None, "sigma": sigma, "solver_iterations": 0, "solver_residual": 0.0}
        f = None
    else:
        f = I / R
        if f < 1 - NUMERICAL_TOL:
            raise ReachValidationError(
                f"Level 3B: F̄_human=I/R_1+={f:.6g}<1. Входы несовместимы."
            )
        if measured_exact is not None:
            vals = [finite(x, "measured exact frequency") for x in measured_exact]
            if len(vals) != 6:
                raise ReachValidationError("Measured exact frequency должна содержать buckets 1,2,3,4,5,6+.")
            if any(x < -NUMERICAL_TOL for x in vals):
                raise ReachValidationError("Measured exact frequency содержит отрицательную долю.")
            ssum = sum(vals)
            if abs(ssum - 1.0) > SOLVER_TOL:
                raise ReachValidationError("Measured exact frequency должна суммироваться в 1.")
            exact = [max(0.0, x) for x in vals]
            freq_meta = {
                "model": "MEASURED_HUMAN_EXACT",
                "mu": None,
                "sigma": None,
                "solver_iterations": 0,
                "solver_residual": 0.0,
                "cap": hard_cap,
            }
        else:
            freq_meta = poisson_lognormal_frequency(f, sigma, cap=hard_cap)
            exact = freq_meta["exact"]

    exact_counts = [R * p for p in exact]
    cumulative = [sum(exact_counts[k:]) for k in range(6)]
    return {
        **{f"reach_{k+1}p": cumulative[k] for k in range(6)},
        "exact_counts": exact_counts,
        "freq_dist": exact if R > 0 else [1.0, 0, 0, 0, 0, 0],
        "impressions": I,
        "avg_frequency": f,
        "frequency_model": freq_meta.get("model"),
        "frequency_model_assumed": measured_exact is None and freq_meta.get("model") == "POISSON_LOGNORMAL",
        "sigma": freq_meta.get("sigma"),
        "sigma_source": sigma_source if measured_exact is None else "MEASURED",
        "mu": freq_meta.get("mu"),
        "solver_iterations_frequency": freq_meta.get("solver_iterations"),
        "solver_residual_frequency": freq_meta.get("solver_residual"),
        "cap": hard_cap,
    }


# ---------------------------------------------------------------------------
# Generic AudienceMerge used by Levels 4–7
# ---------------------------------------------------------------------------

def pair_bounds(
    Ra: float,
    Rb: float,
    U: float,
    *,
    Ua: Optional[float] = None,
    Ub: Optional[float] = None,
    M: Optional[float] = None,
) -> Tuple[float, float]:
    Ra, Rb, U = finite(Ra, "Ra"), finite(Rb, "Rb"), positive(U, "Universe")
    if M is None or Ua is None or Ub is None:
        return max(0.0, Ra + Rb - U), min(Ra, Rb)
    Ua, Ub, M = positive(Ua, "Ua"), positive(Ub, "Ub"), finite(M, "M")
    if M < 0 or M > min(Ua, Ub) + NUMERICAL_TOL:
        raise ReachValidationError("Addressable intersection M должна быть в 0…min(Ua,Ub).")
    if Ua > U + NUMERICAL_TOL or Ub > U + NUMERICAL_TOL:
        raise ReachValidationError("Addressable Universe entity > merge Universe.")
    mi = max(0.0, Ra - (Ua - M))
    mj = max(0.0, Rb - (Ub - M))
    return max(0.0, mi + mj - M), min(Ra, Rb, M)


def neutral_overlap(
    Ra: float,
    Rb: float,
    U: float,
    *,
    Ua: Optional[float] = None,
    Ub: Optional[float] = None,
    M: Optional[float] = None,
) -> float:
    if M is not None and Ua is not None and Ub is not None:
        Ua, Ub = positive(Ua, "Ua"), positive(Ub, "Ub")
        M = finite(M, "M")
        return M * (Ra / Ua) * (Rb / Ub)
    return Ra * Rb / U


def overlap_from_rho(
    Ra: float,
    Rb: float,
    U: float,
    rho: float,
    *,
    Ua: Optional[float] = None,
    Ub: Optional[float] = None,
    M: Optional[float] = None,
) -> dict:
    r = finite(rho, "rho")
    if r < -1 or r > 1:
        raise ReachValidationError("rho должен быть в диапазоне -1…1.")
    j0 = neutral_overlap(Ra, Rb, U, Ua=Ua, Ub=Ub, M=M)
    jmin, jmax = pair_bounds(Ra, Rb, U, Ua=Ua, Ub=Ub, M=M)
    if j0 < jmin - NUMERICAL_TOL or j0 > jmax + NUMERICAL_TOL:
        raise ReachValidationError("Neutral overlap J0 несовместим с feasible bounds.")
    j = j0 + r * ((jmax - j0) if r >= 0 else (j0 - jmin))
    if j < jmin - NUMERICAL_TOL or j > jmax + NUMERICAL_TOL:
        raise ReachValidationError("Derived overlap J вне feasible bounds.")
    return {"J0": j0, "J_min": jmin, "J_max": jmax, "J": j, "rho": r}


def _event_column(state: int, n: int, pair_keys: Sequence[Tuple[int, int]]) -> List[float]:
    col = [1.0]
    col.extend(1.0 if (state >> i) & 1 else 0.0 for i in range(n))
    col.extend(1.0 if ((state >> i) & 1 and (state >> j) & 1) else 0.0 for i, j in pair_keys)
    return col


def _phase1_feasible(
    reaches: Sequence[float],
    U: float,
    pair_targets: Mapping[Tuple[int, int], float],
    *,
    support: Optional[Sequence[bool]] = None,
    tolerance: float = FEASIBILITY_TOL,
    max_pivots: int = 20_000,
) -> dict:
    """Separate deterministic Phase-I LP feasibility test on the full joint-state set.

    Standard form: A w = b, w>=0.  Artificial variables provide the initial basis.
    The Phase-I objective is the sum of artificial variables; optimum 0 certifies
    global feasibility.  This is deliberately separate from the MaxEnt/IPF solver.
    """
    n = len(reaches)
    if n > MAX_ENTITIES:
        raise ReachValidationError(f"Joint state guard: {n}>{MAX_ENTITIES}. Требуется approved approximation/review.")
    pair_keys = sorted(pair_targets)
    b = [1.0] + [r / U for r in reaches] + [pair_targets[k] / U for k in pair_keys]
    m = len(b)
    state_ids = [
        s for s in range(1 << n)
        if support is None or (s < len(support) and bool(support[s]))
    ]
    if not state_ids:
        return {"feasible": False, "objective": float("inf"), "pivots": 0, "reason": "EMPTY_SUPPORT"}

    columns = [_event_column(s, n, pair_keys) for s in state_ids]
    # Basis starts as artificial identity; B^-1 = I.
    Binv = [[1.0 if i == j else 0.0 for j in range(m)] for i in range(m)]
    basis = [len(columns) + i for i in range(m)]
    xB = list(b)
    cB = [1.0] * m

    def dot(a: Sequence[float], bb: Sequence[float]) -> float:
        return sum(x * y for x, y in zip(a, bb))

    def basis_y() -> List[float]:
        return [sum(cB[r] * Binv[r][c] for r in range(m)) for c in range(m)]

    def is_basic(var: int) -> bool:
        return var in basis

    objective = sum(c * x for c, x in zip(cB, xB))
    pivots = 0
    rc_tol = 1e-12

    while pivots < max_pivots:
        y = basis_y()
        entering = None
        entering_col = None

        # Bland order: original state variables, then artificials.
        for j, col in enumerate(columns):
            if is_basic(j):
                continue
            rc = -dot(y, col)
            if rc < -rc_tol:
                entering = j
                entering_col = col
                break
        if entering is None:
            for aidx in range(m):
                var = len(columns) + aidx
                if is_basic(var):
                    continue
                rc = 1.0 - y[aidx]
                if rc < -rc_tol:
                    col = [1.0 if k == aidx else 0.0 for k in range(m)]
                    entering = var
                    entering_col = col
                    break

        if entering is None:
            objective = sum(c * x for c, x in zip(cB, xB))
            return {
                "feasible": objective <= tolerance,
                "objective": objective,
                "pivots": pivots,
                "state_count": len(state_ids),
                "constraint_count": m,
                "reason": "PHASE1_OPTIMUM",
            }

        d = [dot(row, entering_col) for row in Binv]
        candidates = [(xB[i] / d[i], basis[i], i) for i in range(m) if d[i] > 1e-14]
        if not candidates:
            return {
                "feasible": False,
                "objective": objective,
                "pivots": pivots,
                "state_count": len(state_ids),
                "constraint_count": m,
                "reason": "PHASE1_UNBOUNDED",
            }
        theta, _basis_var, leave = min(candidates, key=lambda x: (x[0], x[1]))
        pivot = d[leave]
        old_pivot_row = list(Binv[leave])

        # Update primal basic values.
        new_xB = [xB[i] - theta * d[i] for i in range(m)]
        new_xB[leave] = theta
        for i, value in enumerate(new_xB):
            if -NUMERICAL_TOL <= value < 0:
                new_xB[i] = 0.0
        xB = new_xB

        # Eta/Gauss-Jordan inverse update.
        Binv[leave] = [v / pivot for v in old_pivot_row]
        for i in range(m):
            if i == leave:
                continue
            factor = d[i] / pivot
            if abs(factor) > 0:
                Binv[i] = [Binv[i][k] - factor * old_pivot_row[k] for k in range(m)]

        basis[leave] = entering
        cB[leave] = 0.0 if entering < len(columns) else 1.0
        pivots += 1
        objective = sum(c * x for c, x in zip(cB, xB))

        if objective <= tolerance:
            # Zero Phase-I objective is already a mathematical feasibility certificate.
            return {
                "feasible": True,
                "objective": objective,
                "pivots": pivots,
                "state_count": len(state_ids),
                "constraint_count": m,
                "reason": "PHASE1_ZERO_OBJECTIVE",
            }

    raise ReachCalculationError("Global feasibility Phase-I solver превысил max pivots.")


def global_feasibility(
    reaches: Sequence[float],
    U: float,
    pair_targets: Mapping[Tuple[int, int], float],
    *,
    support: Optional[Sequence[bool]] = None,
) -> dict:
    U = positive(U, "Universe")
    rs = [finite(r, "Reach") for r in reaches]
    for r in rs:
        if r < 0 or r > U + NUMERICAL_TOL:
            raise ReachValidationError("Entity Reach вне 0…Universe.")
    for (i, j), J in pair_targets.items():
        lo, hi = pair_bounds(rs[i], rs[j], U)
        if J < lo - FEASIBILITY_TOL or J > hi + FEASIBILITY_TOL:
            return {
                "feasible": False,
                "reason": "PAIRWISE_BOUNDS",
                "pair": [i, j],
                "J": J,
                "J_min": lo,
                "J_max": hi,
            }
    if len(rs) <= 2:
        return {"feasible": True, "reason": "PAIRWISE_SUFFICIENT", "objective": 0.0, "pivots": 0}
    return _phase1_feasible(rs, U, pair_targets, support=support)


def _maxent_three(
    reaches: Sequence[float],
    U: float,
    pair_targets: Mapping[Tuple[int, int], float],
    *,
    support: Optional[Sequence[bool]] = None,
) -> dict:
    """Exact one-dimensional Maximum-Entropy closure for three binary entities."""
    p1, p2, p3 = [r / U for r in reaches]
    j12 = pair_targets[(0, 1)] / U
    j13 = pair_targets[(0, 2)] / U
    j23 = pair_targets[(1, 2)] / U
    constant0 = 1.0 - p1 - p2 - p3 + j12 + j13 + j23
    lo = max(0.0, j12 + j13 - p1, j12 + j23 - p2, j13 + j23 - p3)
    hi = min(j12, j13, j23, constant0)
    if lo > hi + FEASIBILITY_TOL:
        raise ReachValidationError("Three-way system is globally infeasible.")

    def weights_at(t: float) -> List[float]:
        w111 = t
        w110 = j12 - t
        w101 = j13 - t
        w011 = j23 - t
        w100 = p1 - j12 - j13 + t
        w010 = p2 - j12 - j23 + t
        w001 = p3 - j13 - j23 + t
        w000 = constant0 - t
        # state order: 000,100,010,110,001,101,011,111
        vals = [w000, w100, w010, w110, w001, w101, w011, w111]
        out = []
        for x in vals:
            if x < -SOLVER_TOL:
                raise ReachValidationError("Three-way MaxEnt state probability < 0.")
            out.append(0.0 if x < 0 else x)
        if support is not None:
            for s, ok in enumerate(support):
                if s < 8 and not ok and out[s] > SOLVER_TOL:
                    raise ReachValidationError("Three-way solution violates hard support.")
                if s < 8 and not ok:
                    out[s] = 0.0
        return out

    def entropy(t: float) -> float:
        try:
            vals = weights_at(t)
        except ReachValidationError:
            return -float("inf")
        return -sum(x * math.log(x) for x in vals if x > 0)

    # If structured support rules remove states, the 1D interval can be reduced by
    # requiring their affine probabilities to equal zero.  Find feasible candidates.
    if support is not None:
        candidates = [lo, hi]
        affine = [
            (constant0, -1.0),                  # 000
            (p1 - j12 - j13, 1.0),             # 100
            (p2 - j12 - j23, 1.0),             # 010
            (j12, -1.0),                       # 110
            (p3 - j13 - j23, 1.0),             # 001
            (j13, -1.0),                       # 101
            (j23, -1.0),                       # 011
            (0.0, 1.0),                        # 111
        ]
        required = []
        for s in range(8):
            if s < len(support) and not support[s]:
                a, b = affine[s]
                if abs(b) <= 1e-15:
                    if abs(a) > SOLVER_TOL:
                        raise ReachValidationError("Hard support is infeasible.")
                else:
                    required.append(-a / b)
        if required:
            t0 = required[0]
            if any(abs(x - t0) > SOLVER_TOL for x in required[1:]):
                raise ReachValidationError("Hard support requires conflicting triple intersections.")
            if t0 < lo - SOLVER_TOL or t0 > hi + SOLVER_TOL:
                raise ReachValidationError("Hard support triple intersection outside feasible interval.")
            vals = weights_at(min(hi, max(lo, t0)))
            return {"weights": vals, "iterations": 0, "residual": 0.0, "status": "CONVERGED_ANALYTIC_3"}

    if hi - lo <= SOLVER_TOL:
        vals = weights_at((lo + hi) / 2.0)
        return {"weights": vals, "iterations": 0, "residual": 0.0, "status": "CONVERGED_ANALYTIC_3_BOUNDARY"}

    # Golden-section maximization of the strictly concave entropy.
    a, b = lo, hi
    gr = (math.sqrt(5.0) - 1.0) / 2.0
    x1 = b - gr * (b - a)
    x2 = a + gr * (b - a)
    f1, f2 = entropy(x1), entropy(x2)
    iterations = 0
    while b - a > 1e-13 and iterations < 300:
        iterations += 1
        if f1 < f2:
            a = x1
            x1, f1 = x2, f2
            x2 = a + gr * (b - a)
            f2 = entropy(x2)
        else:
            b = x2
            x2, f2 = x1, f1
            x1 = b - gr * (b - a)
            f1 = entropy(x1)
    vals = weights_at((a + b) / 2.0)
    # Direct construction satisfies the constraints to floating tolerance.
    return {"weights": vals, "iterations": iterations, "residual": 0.0, "status": "CONVERGED_ANALYTIC_3"}


def _ipf_maxent(
    reaches: Sequence[float],
    U: float,
    pair_targets: Mapping[Tuple[int, int], float],
    *,
    support: Optional[Sequence[bool]] = None,
) -> dict:
    n = len(reaches)
    if n == 3 and set(pair_targets) == {(0, 1), (0, 2), (1, 2)}:
        return _maxent_three(reaches, U, pair_targets, support=support)
    size = 1 << n
    allowed = [s for s in range(size) if support is None or (s < len(support) and support[s])]
    if not allowed:
        raise ReachValidationError("Joint model: empty support.")
    w = [0.0] * size
    for s in allowed:
        w[s] = 1.0 / len(allowed)

    constraints: List[Tuple[List[bool], float, str]] = []
    for i, r in enumerate(reaches):
        constraints.append(([bool((s >> i) & 1) for s in range(size)], r / U, f"R[{i}]"))
    for (i, j), J in sorted(pair_targets.items()):
        constraints.append(
            ([bool(((s >> i) & 1) and ((s >> j) & 1)) for s in range(size)], J / U, f"J[{i},{j}]")
        )

    residual = float("inf")
    for it in range(1, MAX_ITERATIONS + 1):
        for event, target, label in constraints:
            cur = sum(w[s] for s in allowed if event[s])
            if target <= SOLVER_TOL:
                for s in allowed:
                    if event[s]:
                        w[s] = 0.0
            elif target >= 1.0 - SOLVER_TOL:
                for s in allowed:
                    if not event[s]:
                        w[s] = 0.0
            else:
                if cur <= 1e-300 or cur >= 1 - 1e-15:
                    raise ReachCalculationError(
                        f"Maximum Entropy/IPF numerical boundary at {label}; system passed feasibility."
                    )
                a = target / cur
                b = (1.0 - target) / (1.0 - cur)
                for s in allowed:
                    w[s] *= a if event[s] else b
            z = sum(w[s] for s in allowed)
            if not math.isfinite(z) or z <= 0:
                raise ReachCalculationError("Maximum Entropy/IPF normalization failure.")
            inv = 1.0 / z
            for s in allowed:
                w[s] *= inv

        if it % 5 == 0 or it == MAX_ITERATIONS:
            residual = 0.0
            for event, target, _label in constraints:
                cur = sum(w[s] for s in allowed if event[s])
                residual = max(residual, abs(cur - target))
            if residual <= SOLVER_TOL:
                return {"weights": w, "iterations": it, "residual": residual, "status": "CONVERGED"}

    raise ReachCalculationError(
        f"Maximum Entropy не сошёлся за {MAX_ITERATIONS} iterations; residual={residual:.3g}."
    )


def _independence_weights(reaches: Sequence[float], U: float, support: Optional[Sequence[bool]] = None) -> List[float]:
    n = len(reaches)
    probs = [r / U for r in reaches]
    weights = [0.0] * (1 << n)
    total = 0.0
    for state in range(1 << n):
        if support is not None and (state >= len(support) or not support[state]):
            continue
        p = 1.0
        for i, q in enumerate(probs):
            p *= q if (state >> i) & 1 else (1.0 - q)
        weights[state] = p
        total += p
    if total <= 0:
        raise ReachValidationError("Independence support has zero probability.")
    if abs(total - 1.0) > SOLVER_TOL:
        # Conditional normalization is not neutral independence anymore. Structured
        # support must therefore use the explicit ADDRESSABILITY_NEUTRAL/MaxEnt path.
        raise ReachValidationError("Structured support нельзя считать closed-form independence.")
    return weights


def _two_weights(Ra: float, Rb: float, J: float, U: float) -> List[float]:
    vals = [
        1.0 - (Ra + Rb - J) / U,
        (Ra - J) / U,
        (Rb - J) / U,
        J / U,
    ]
    out = []
    for i, x in enumerate(vals):
        if x < -SOLVER_TOL:
            raise ReachValidationError("Pair overlap несовместим с Reach/Universe.")
        out.append(0.0 if x < 0 else x)
    return out


def convolve_frequency(a: Sequence[float], b: Sequence[float]) -> List[float]:
    if len(a) != 6 or len(b) != 6:
        raise ReachValidationError("Frequency distribution должна иметь 6 buckets.")
    out = [0.0] * 6
    for ia, pa in enumerate(a, 1):
        for ib, pb in enumerate(b, 1):
            if pa <= 0 or pb <= 0:
                continue
            out[min(6, ia + ib) - 1] += pa * pb
    return out


def _coverage_contributions(entities: Sequence[dict], U: float, weights: Sequence[float]) -> List[dict]:
    n = len(entities)
    shapley = [0.0] * n
    exclusive = [0.0] * n
    for state, prob in enumerate(weights):
        if state == 0 or prob <= 0:
            continue
        members = [i for i in range(n) if (state >> i) & 1]
        people = U * prob
        share = people / len(members)
        for i in members:
            shapley[i] += share
        if len(members) == 1:
            exclusive[members[0]] += people
    return [
        {
            "name": entities[i].get("name") or f"entity_{i+1}",
            "shapley_people": shapley[i],
            "exclusive_people": exclusive[i],
        }
        for i in range(n)
    ]


def _joint_output(
    entities: Sequence[dict],
    U: float,
    weights: Sequence[float],
    *,
    model_path: str,
    pair_details: Optional[Mapping[Tuple[int, int], dict]] = None,
    feasibility: Optional[dict] = None,
    solver: Optional[dict] = None,
) -> dict:
    n = len(entities)
    h = [0.0] * 6
    for state, ws in enumerate(weights):
        if state == 0 or ws <= 0:
            continue
        g = None
        for i, ent in enumerate(entities):
            if not ((state >> i) & 1):
                continue
            fd = list(ent.get("freq_dist") or [])
            if len(fd) != 6:
                raise ReachValidationError(f"{ent.get('name')}: missing exact frequency distribution.")
            g = fd if g is None else convolve_frequency(g, fd)
        if g is None:
            continue
        for k, p in enumerate(g):
            h[k] += ws * p

    exact_counts = [U * p for p in h]
    reach = [sum(exact_counts[k:]) for k in range(6)]
    impressions = sum(float(e.get("impressions") or 0.0) for e in entities)
    r1 = reach[0]
    out = {
        **{f"reach_{k+1}p": reach[k] for k in range(6)},
        "exact_counts": exact_counts,
        "freq_dist": [x / r1 * U if False else 0 for x in exact_counts],  # overwritten below
        "impressions": impressions,
        "avg_frequency": (impressions / r1) if r1 > 0 else None,
        "model_path": model_path,
        "entity_count": n,
        "state_count": len(weights),
        "weights": list(weights) if n <= 6 else None,
        "feasibility": feasibility,
        "solver_status": None if solver is None else solver.get("status"),
        "solver_iterations": None if solver is None else solver.get("iterations"),
        "solver_residual": None if solver is None else solver.get("residual"),
    }
    if r1 > 0:
        out["freq_dist"] = [c / r1 for c in exact_counts]
    else:
        out["freq_dist"] = [1.0, 0, 0, 0, 0, 0]

    gross = sum(float(e.get("reach_1p") or 0.0) for e in entities)
    dedup = gross - r1
    if dedup < -SOLVER_TOL:
        raise ReachCalculationError("Merged Reach exceeds Gross Reach Sum.")
    out.update({
        "gross_reach_sum": gross,
        "dedup_people": max(0.0, dedup),
        "dedup_rate": max(0.0, dedup) / gross if gross > 0 else 0.0,
        "contributions": _coverage_contributions(entities, U, weights),
        "pair_details": {
            f"{entities[i].get('name','entity')} × {entities[j].get('name','entity')}": dict(meta)
            for (i, j), meta in (pair_details or {}).items()
        },
    })

    # Canonical reach/contact invariants.
    for k in range(5):
        if reach[k] + SOLVER_TOL < reach[k + 1]:
            raise ReachCalculationError("Frequency Reach is not monotonic.")
    if r1 > U + SOLVER_TOL:
        raise ReachCalculationError("Merged Reach > Universe.")
    for k, rk in enumerate(reach, 1):
        if rk > impressions / k + max(1e-6, SOLVER_TOL * max(1.0, impressions)):
            raise ReachValidationError(
                f"CONTACT_INCONSISTENCY: Reach @{k}+={rk:.3f} > Impressions/{k}."
            )
    if abs(sum(exact_counts) - r1) > max(1e-5, SOLVER_TOL * max(1.0, r1)):
        raise ReachCalculationError("Exact buckets do not sum to Reach 1+.")
    return out


def audience_merge(
    entities: Sequence[dict],
    U: float,
    *,
    pair_details: Optional[Mapping[Tuple[int, int], dict]] = None,
    neutral_unstructured: bool = False,
    support: Optional[Sequence[bool]] = None,
    model_path: str = "AUDIENCE_MERGE",
) -> dict:
    U = positive(U, "Merge Universe")
    ents = [dict(e) for e in entities if float(e.get("reach_1p") or 0.0) > 0]
    if not ents:
        return {
            "reach_1p": 0.0, "reach_2p": 0.0, "reach_3p": 0.0, "reach_4p": 0.0,
            "reach_5p": 0.0, "reach_6p": 0.0, "exact_counts": [0.0] * 6,
            "freq_dist": [1.0, 0, 0, 0, 0, 0], "impressions": 0.0,
            "avg_frequency": None, "model_path": model_path + "_EMPTY",
            "entity_count": 0, "gross_reach_sum": 0.0, "dedup_people": 0.0,
            "dedup_rate": 0.0, "contributions": [], "pair_details": {},
            "feasibility": {"feasible": True, "reason": "EMPTY"},
        }
    if len(ents) > MAX_ENTITIES:
        raise ReachValidationError(
            f"Joint state guard: {len(ents)}>{MAX_ENTITIES}. Нельзя silently упрощать модель."
        )
    reaches = [finite(e["reach_1p"], "Entity Reach") for e in ents]
    for r in reaches:
        if r < 0 or r > U + NUMERICAL_TOL:
            raise ReachValidationError("Entity Reach вне 0…Universe.")

    if len(ents) == 1:
        e = ents[0]
        weights = [1.0 - reaches[0] / U, reaches[0] / U]
        return _joint_output(ents, U, weights, model_path=model_path + "_IDENTITY",
                             feasibility={"feasible": True, "reason": "IDENTITY"})

    pd: Dict[Tuple[int, int], dict] = {}
    targets: Dict[Tuple[int, int], float] = {}
    supplied = pair_details or {}
    for i in range(len(ents)):
        for j in range(i + 1, len(ents)):
            meta = dict(supplied.get((i, j), {}))
            if "J" not in meta:
                J = neutral_overlap(reaches[i], reaches[j], U)
                meta.update({
                    "J0": J, "J": J,
                    "J_min": pair_bounds(reaches[i], reaches[j], U)[0],
                    "J_max": pair_bounds(reaches[i], reaches[j], U)[1],
                    "rho": 0.0,
                    "source": "NEUTRAL_MODEL_DEFAULT",
                })
            J = finite(meta["J"], "Pair J")
            jmin, jmax = pair_bounds(
                reaches[i], reaches[j], U,
                Ua=meta.get("U_i"), Ub=meta.get("U_j"), M=meta.get("M"),
            )
            if J < jmin - FEASIBILITY_TOL or J > jmax + FEASIBILITY_TOL:
                raise ReachValidationError(
                    f"Pair {i},{j}: J={J} вне feasible bounds [{jmin},{jmax}]."
                )
            meta.setdefault("J_min", jmin)
            meta.setdefault("J_max", jmax)
            meta.setdefault("J0", neutral_overlap(
                reaches[i], reaches[j], U,
                Ua=meta.get("U_i"), Ub=meta.get("U_j"), M=meta.get("M"),
            ))
            pd[(i, j)] = meta
            targets[(i, j)] = J

    if len(ents) == 2:
        weights = _two_weights(reaches[0], reaches[1], targets[(0, 1)], U)
        return _joint_output(
            ents, U, weights, model_path=model_path + "_ANALYTIC",
            pair_details=pd, feasibility={"feasible": True, "reason": "PAIR_ANALYTIC"},
        )

    if neutral_unstructured and support is None and all(
        abs(float(meta.get("rho", 0.0))) <= 1e-15
        and meta.get("M") is None
        and str(meta.get("source", "")).upper() in {"NEUTRAL_MODEL_DEFAULT", "MODEL_DEFAULT", ""}
        for meta in pd.values()
    ):
        weights = _independence_weights(reaches, U)
        return _joint_output(
            ents, U, weights, model_path=model_path + "_INDEPENDENCE",
            pair_details=pd, feasibility={"feasible": True, "reason": "UNSTRUCTURED_NEUTRAL_CLOSED_FORM"},
        )

    feas = global_feasibility(reaches, U, targets, support=support)
    if not feas.get("feasible"):
        raise ReachValidationError(
            "GLOBAL_FEASIBILITY=FAIL: pairwise constraints несовместимы на полном joint-state space. "
            + str(feas)
        )
    solver = _ipf_maxent(reaches, U, targets, support=support)
    return _joint_output(
        ents, U, solver["weights"],
        model_path=model_path + ("_ADDRESSABILITY_NEUTRAL" if all(x.get("rho") is not None and abs(float(x.get("rho"))) <= 1e-15 for x in pd.values()) else "_MAXENT"),
        pair_details=pd, feasibility=feas, solver=solver,
    )


def normalize_pair_input(
    raw: Mapping[str, Any],
    Ra: float,
    Rb: float,
    U: float,
    *,
    Ua: Optional[float] = None,
    Ub: Optional[float] = None,
    M: Optional[float] = None,
    default_rho: Optional[float] = None,
    default_source: str = "CUSTOM",
) -> dict:
    """Normalize measured/historical/custom pair relation without silent repair.

    Accepted relation forms are direct intersection J, pair union, or rho.
    Addressable universes/intersection may also be supplied.
    """
    meta = dict(raw or {})
    Ua_eff = meta.get("U_i", meta.get("Ua", Ua))
    Ub_eff = meta.get("U_j", meta.get("Ub", Ub))
    M_eff = meta.get("M", M)
    if Ua_eff is not None:
        Ua_eff = positive(Ua_eff, "U_i")
    if Ub_eff is not None:
        Ub_eff = positive(Ub_eff, "U_j")
    if M_eff is not None:
        M_eff = finite(M_eff, "M")

    source = str(meta.get("source") or default_source).strip().upper()
    rho = None
    if "J" in meta or "intersection" in meta:
        J = finite(meta.get("J", meta.get("intersection")), "Pair J")
        if meta.get("rho") is not None:
            rho = finite(meta.get("rho"), "rho")
    elif "union" in meta:
        union = finite(meta.get("union"), "Pair union")
        J = finite(Ra, "Ra") + finite(Rb, "Rb") - union
        if meta.get("rho") is not None:
            rho = finite(meta.get("rho"), "rho")
    elif meta.get("rho") is not None or default_rho is not None:
        rho = finite(meta.get("rho") if meta.get("rho") is not None else default_rho, "rho")
        derived = overlap_from_rho(Ra, Rb, U, rho, Ua=Ua_eff, Ub=Ub_eff, M=M_eff)
        J = derived["J"]
    else:
        raise ReachValidationError(
            "Pair relation требует J / intersection / union / rho либо level-specific default_rho."
        )

    jmin, jmax = pair_bounds(Ra, Rb, U, Ua=Ua_eff, Ub=Ub_eff, M=M_eff)
    if J < jmin - FEASIBILITY_TOL or J > jmax + FEASIBILITY_TOL:
        raise ReachValidationError(
            f"{source} pair J={J} вне feasible bounds [{jmin},{jmax}]."
        )
    j0 = neutral_overlap(Ra, Rb, U, Ua=Ua_eff, Ub=Ub_eff, M=M_eff)
    out = dict(meta)
    out.update({
        "J": J,
        "J0": j0,
        "J_min": jmin,
        "J_max": jmax,
        "source": source,
    })
    if Ua_eff is not None:
        out["U_i"] = Ua_eff
    if Ub_eff is not None:
        out["U_j"] = Ub_eff
    if M_eff is not None:
        out["M"] = M_eff
    if rho is not None:
        if rho < -1 or rho > 1:
            raise ReachValidationError("rho должен быть в диапазоне -1…1.")
        out["rho"] = rho
    return out


# ---------------------------------------------------------------------------
# Level 5
# ---------------------------------------------------------------------------

def level5_channel_pairs(
    channels: Sequence[dict],
    U: float,
    *,
    custom_pairs: Optional[Mapping[Tuple[int, int], dict]] = None,
) -> Tuple[Dict[Tuple[int, int], dict], float, List[dict]]:
    n = len(channels)
    reaches = [float(c["reach_1p"]) for c in channels]
    hard = custom_pairs or {}
    diagnostics: List[dict] = []

    def make(lam: float) -> Dict[Tuple[int, int], dict]:
        out: Dict[Tuple[int, int], dict] = {}
        for i in range(n):
            for j in range(i + 1, n):
                if (i, j) in hard:
                    out[(i, j)] = dict(hard[(i, j)])
                    continue
                Ui = float(channels[i].get("addressable_universe") or U)
                Uj = float(channels[j].get("addressable_universe") or U)
                M = None
                if channels[i].get("addressable_intersections"):
                    M = channels[i]["addressable_intersections"].get(channels[j].get("name"))
                rho = RHO_CHANNEL_DEFAULT * lam
                meta = overlap_from_rho(reaches[i], reaches[j], U, rho, Ua=Ui, Ub=Uj, M=M)
                meta.update({
                    "U_i": Ui, "U_j": Uj, "M": M,
                    "M_source": "MEASURED_ADDRESSABLE" if M is not None else "MODEL_DEFAULT",
                    "source": "MEASURED_ADDRESSABLE" if M is not None else "BASE_MODEL_DEFAULT",
                    "rho_target": RHO_CHANNEL_DEFAULT,
                    "rho_effective": rho,
                })
                out[(i, j)] = meta
        return out

    target = make(1.0)
    if n < 3:
        return target, 1.0, diagnostics
    target_J = {k: v["J"] for k, v in target.items()}
    if global_feasibility(reaches, U, target_J).get("feasible"):
        return target, 1.0, diagnostics

    neutral = make(0.0)
    neutral_J = {k: v["J"] for k, v in neutral.items()}
    if not global_feasibility(reaches, U, neutral_J).get("feasible"):
        raise ReachValidationError(
            "Level 5: система infeasible даже при λ=0; hard measured/historical/custom constraints конфликтуют."
        )

    lo, hi = 0.0, 1.0
    while hi - lo > LAMBDA_TOL:
        mid = (lo + hi) / 2.0
        pairs = make(mid)
        feasible = global_feasibility(reaches, U, {k: v["J"] for k, v in pairs.items()}).get("feasible")
        if feasible:
            lo = mid
        else:
            hi = mid
    lam = lo
    effective = make(lam)
    diagnostics.append({
        "code": "GLOBAL_FEASIBILITY_RELAXATION",
        "level": 5,
        "lambda": lam,
        "rho_target": RHO_CHANNEL_DEFAULT,
        "rho_effective": RHO_CHANNEL_DEFAULT * lam,
        "source": "MODEL_DEFAULT",
    })
    return effective, lam, diagnostics


def level5_flight(
    channels: Sequence[dict],
    U: float,
    *,
    custom_pairs: Optional[Mapping[Tuple[int, int], dict]] = None,
) -> dict:
    if not channels:
        return audience_merge([], U, model_path="L5_FLIGHT")
    pairs, lam, diagnostics = level5_channel_pairs(channels, U, custom_pairs=custom_pairs)
    full_neutral = len(channels) >= 3 and all(
        abs(float(x.get("rho_effective", x.get("rho", 999)))) <= 1e-15
        and x.get("M") is None
        and x.get("source") not in {"MEASURED_CAMPAIGN", "HISTORICAL_CALIBRATED", "CUSTOM", "MEASURED_ADDRESSABLE"}
        for x in pairs.values()
    )
    out = audience_merge(
        channels, U, pair_details=pairs,
        neutral_unstructured=full_neutral,
        model_path="L5_FLIGHT",
    )
    out["relaxation_lambda"] = lam
    out["rho_target"] = RHO_CHANNEL_DEFAULT
    out["rho_effective"] = RHO_CHANNEL_DEFAULT * lam
    out["diagnostics"] = diagnostics
    out["D_Flight"] = out["dedup_rate"]
    return out


# ---------------------------------------------------------------------------
# Level 6
# ---------------------------------------------------------------------------

def gap_days(a_end: Optional[dt.date], b_start: Optional[dt.date]) -> int:
    if not a_end or not b_start:
        raise ReachValidationError("Level 6 требует реальные Flight start/end dates.")
    return max(0, (b_start - a_end).days - 1)


def q_temporal(gap: int) -> float:
    g = max(0, int(gap))
    if g >= 68:
        return 0.0
    for (x1, y1), (x2, y2) in zip(Q_TEMPORAL_POINTS, Q_TEMPORAL_POINTS[1:]):
        if x1 <= g <= x2:
            t = (g - x1) / (x2 - x1)
            return y1 + t * (y2 - y1)
    return 0.0


def universe_multiplier(U: float) -> float:
    U = positive(U, "Universe")
    pts = UNIVERSE_MULTIPLIER_POINTS
    if U <= pts[0][0]:
        return pts[0][1]
    if U >= pts[-1][0]:
        return pts[-1][1]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if x1 <= U <= x2:
            t = (U - x1) / (x2 - x1)
            return y1 + t * (y2 - y1)
    raise ReachCalculationError("Universe multiplier interpolation failure.")


def _l6_basic_pair(a: dict, b: dict, U: float) -> dict:
    Ra, Rb = float(a["reach_1p"]), float(b["reach_1p"])
    a0, a1 = a.get("start"), a.get("end")
    b0, b1 = b.get("start"), b.get("end")
    if not all((a0, a1, b0, b1)):
        raise ReachValidationError("Level 6 pair требует start/end обеих Flights.")
    if a0 <= b0:
        G = gap_days(a1, b0) if a1 < b0 else 0
    else:
        G = gap_days(b1, a0) if b1 < a0 else 0

    qt = q_temporal(G)
    mu = universe_multiplier(U)
    j_temporal = min(Ra, Rb) * qt * mu
    Ui = float(a.get("addressable_universe") or U)
    Uj = float(b.get("addressable_universe") or U)
    M = a.get("addressable_intersections", {}).get(b.get("name")) if a.get("addressable_intersections") else None
    j_neutral = neutral_overlap(Ra, Rb, U, Ua=Ui, Ub=Uj, M=M)
    j_residual = min(j_neutral, RESIDUAL_CAP * min(Ra, Rb))
    target = max(j_temporal, j_residual)
    jmin, jmax = pair_bounds(Ra, Rb, U, Ua=Ui, Ub=Uj, M=M)
    if target < jmin:
        effective = jmin
        bound_status = "RAISED_TO_J_MIN"
    elif target > jmax:
        # For a two-flight MODEL_DEFAULT pair, hard feasibility bound has priority.
        effective = jmax
        bound_status = "LOWERED_TO_J_MAX"
    else:
        effective = target
        bound_status = "WITHIN_BOUNDS"
    return {
        "J": effective,
        "J_target": target,
        "J_effective": effective,
        "J0": j_neutral,
        "J_neutral": j_neutral,
        "J_temporal": j_temporal,
        "J_residual": j_residual,
        "J_min": jmin,
        "J_max": jmax,
        "gap_days": G,
        "q_temporal": qt,
        "M_U": mu,
        "source": "MODEL_DEFAULT",
        "pair_bound_status": bound_status,
        "residual_cap": RESIDUAL_CAP,
    }


def _aon_slice_for_burst(aon: dict, burst: dict) -> Optional[float]:
    slices = aon.get("temporal_slices") or []
    b0, b1 = burst.get("start"), burst.get("end")
    if not b0 or not b1:
        return None
    # Exact comparable subperiod is preferred.  We deliberately do not sum overlapping
    # monthly reaches because monthly Reach values are not necessarily a deduplicated union.
    exact = [
        s for s in slices
        if s.get("start") == b0 and s.get("end") == b1 and s.get("human_reach_1p_slice") is not None
    ]
    if exact:
        return float(exact[0]["human_reach_1p_slice"])
    return None


def l6_pair(a: dict, b: dict, U: float) -> dict:
    aon_xor = bool(a.get("is_common")) ^ bool(b.get("is_common"))
    if not aon_xor:
        return _l6_basic_pair(a, b, U)
    aon = a if a.get("is_common") else b
    burst = b if a.get("is_common") else a
    slice_reach = _aon_slice_for_burst(aon, burst)
    if slice_reach is None:
        raise ReachValidationError(
            "AON_TEMPORAL_APPROXIMATION_REQUIRED: для AON↔burst нет "
            "deduplicated human Reach slice точно сопоставимого subperiod."
        )
    if slice_reach < 0 or slice_reach > float(aon["reach_1p"]) + NUMERICAL_TOL:
        raise ReachValidationError("AON slice Reach вне 0…annual AON Reach.")

    slice_ent = dict(aon)
    slice_ent["reach_1p"] = slice_reach
    slice_ent["start"] = burst.get("start")
    slice_ent["end"] = burst.get("end")
    first = _l6_basic_pair(slice_ent, burst, U)
    J1 = first["J_effective"]
    f_remaining = max(0.0, float(burst["reach_1p"]) - J1)
    a_rest = max(0.0, float(aon["reach_1p"]) - slice_reach)
    Jn2 = f_remaining * a_rest / U if U > 0 else 0.0
    J2 = min(Jn2, RESIDUAL_CAP * min(f_remaining, a_rest))
    target = J1 + J2
    jmin, jmax = pair_bounds(float(a["reach_1p"]), float(b["reach_1p"]), U)
    if target < jmin - NUMERICAL_TOL or target > jmax + NUMERICAL_TOL:
        effective = min(jmax, max(jmin, target))
        bound_status = "PAIR_BOUND_APPLIED"
    else:
        effective = target
        bound_status = "WITHIN_BOUNDS"
    return {
        "J": effective, "J_target": target, "J_effective": effective,
        "J0": neutral_overlap(float(a["reach_1p"]), float(b["reach_1p"]), U),
        "J_neutral": neutral_overlap(float(a["reach_1p"]), float(b["reach_1p"]), U),
        "J_temporal": first["J_temporal"],
        "J_residual": first["J_residual"],
        "J_min": jmin, "J_max": jmax,
        "gap_days": 0, "q_temporal": first["q_temporal"], "M_U": first["M_U"],
        "source": "MODEL_DEFAULT_AON_STAGED",
        "pair_bound_status": bound_status,
        "aon_staged": True,
        "A_slice": slice_reach,
        "A_rest": a_rest,
        "F_remaining": f_remaining,
        "J_same_period": J1,
        "J_rest": J2,
        "aon_temporal_source": "MEASURED_OR_UPSTREAM_DEDUPLICATED_SLICE",
    }


def level6_line(
    flights: Sequence[dict],
    U: float,
    *,
    custom_pairs: Optional[Mapping[Tuple[int, int], dict]] = None,
) -> dict:
    if not flights:
        return audience_merge([], U, model_path="L6_LINE")
    if len(flights) == 1:
        out = audience_merge(flights, U, model_path="L6_LINE")
        out["flight_relaxation_lambda"] = 1.0
        out["D_L6"] = out["dedup_rate"]
        out["chronological_incremental"] = [{
            "name": flights[0].get("name"),
            "incremental_people": out["reach_1p"],
            "cumulative_people": out["reach_1p"],
        }]
        out["diagnostics"] = []
        return out

    n = len(flights)
    reaches = [float(f["reach_1p"]) for f in flights]
    supplied = custom_pairs or {}
    pairs: Dict[Tuple[int, int], dict] = {}
    for i in range(n):
        for j in range(i + 1, n):
            raw = dict(supplied.get((i, j), {}))
            hard_relation = any(k in raw for k in ("J", "intersection", "union", "rho"))
            if hard_relation:
                Ui = raw.get("U_i", flights[i].get("addressable_universe"))
                Uj = raw.get("U_j", flights[j].get("addressable_universe"))
                Mfg = raw.get("M")
                pairs[(i, j)] = normalize_pair_input(
                    raw, reaches[i], reaches[j], U,
                    Ua=Ui, Ub=Uj, M=Mfg,
                    default_source=str(raw.get("source") or "CUSTOM"),
                )
                continue

            ai, bj = dict(flights[i]), dict(flights[j])
            if raw:
                Ui = raw.get("U_i", raw.get("Ua", ai.get("addressable_universe")))
                Uj = raw.get("U_j", raw.get("Ub", bj.get("addressable_universe")))
                if Ui is not None:
                    ai["addressable_universe"] = positive(Ui, "U_f")
                if Uj is not None:
                    bj["addressable_universe"] = positive(Uj, "U_g")
                if raw.get("M") is not None:
                    Mfg = finite(raw.get("M"), "M_fg")
                    ai.setdefault("addressable_intersections", {})[bj.get("name")] = Mfg
            meta = l6_pair(ai, bj, U)
            if raw:
                meta["M_source"] = str(raw.get("source") or "CUSTOM_ADDRESSABILITY").upper()
                if raw.get("M") is not None:
                    meta["M"] = float(raw["M"])
                    meta["U_i"] = ai.get("addressable_universe")
                    meta["U_j"] = bj.get("addressable_universe")
            pairs[(i, j)] = meta

    lam = 1.0
    diagnostics: List[dict] = []
    target_J = {k: v["J_effective"] if "J_effective" in v else v["J"] for k, v in pairs.items()}
    if n >= 3 and not global_feasibility(reaches, U, target_J).get("feasible"):
        model_keys = [
            k for k, v in pairs.items()
            if str(v.get("source", "")).upper().startswith("MODEL_DEFAULT")
        ]
        if not model_keys:
            raise ReachValidationError("Level 6: hard pair constraints globally infeasible.")
        upper = float("inf")
        for key in model_keys:
            v = pairs[key]
            target = float(v.get("J_target", v.get("J", 0.0)))
            if target <= 0:
                continue
            upper = min(upper, v["J_max"] / target)
        if not math.isfinite(upper):
            raise ReachCalculationError("Level 6: common λ cannot be constructed.")
        if upper < 1 - LAMBDA_TOL:
            raise ReachCalculationError("MODEL_DEFAULT_GLOBAL_INFEASIBLE: λ upper bound < 1.")

        def scaled(candidate: float) -> Dict[Tuple[int, int], float]:
            scaled_targets: Dict[Tuple[int, int], float] = {}
            for key, meta in pairs.items():
                if key in model_keys:
                    target = float(meta.get("J_target", meta.get("J", 0.0)))
                    value = candidate * target
                    if value > meta["J_max"] + FEASIBILITY_TOL:
                        raise ReachCalculationError(
                            "MODEL_DEFAULT_GLOBAL_INFEASIBLE: common λ would exceed J_max."
                        )
                    scaled_targets[key] = value
                else:
                    scaled_targets[key] = float(meta.get("J_effective", meta["J"]))
            return scaled_targets

        if upper <= 1 + LAMBDA_TOL:
            raise ReachCalculationError("MODEL_DEFAULT_GLOBAL_INFEASIBLE: no λ>1 available.")
        steps = 80
        prev = 1.0
        bracket = None
        for s in range(1, steps + 1):
            cand = 1.0 + (upper - 1.0) * s / steps
            try:
                feasible = global_feasibility(reaches, U, scaled(cand)).get("feasible")
            except ReachCalculationError:
                feasible = False
            if feasible:
                bracket = (prev, cand)
                break
            prev = cand
        if bracket is None:
            raise ReachCalculationError(
                "MODEL_DEFAULT_GLOBAL_INFEASIBLE: common λ не восстанавливает feasibility до J_max."
            )
        lo, hi = bracket
        while hi - lo > LAMBDA_TOL:
            mid = (lo + hi) / 2.0
            if global_feasibility(reaches, U, scaled(mid)).get("feasible"):
                hi = mid
            else:
                lo = mid
        lam = hi
        final_J = scaled(lam)
        cap_override = False
        for key in model_keys:
            meta = pairs[key]
            meta["J_effective"] = final_J[key]
            meta["J"] = final_J[key]
            meta["lambda"] = lam
            if final_J[key] > RESIDUAL_CAP * min(reaches[key[0]], reaches[key[1]]) + NUMERICAL_TOL:
                raw_target = float(meta.get("J_target", meta.get("J", 0.0)))
                if raw_target <= RESIDUAL_CAP * min(reaches[key[0]], reaches[key[1]]) + NUMERICAL_TOL:
                    cap_override = True
                    meta["residual_cap_overridden"] = True
        diagnostics.append({"code": "GLOBAL_FEASIBILITY_RELAXATION", "level": 6, "lambda": lam})
        if cap_override:
            diagnostics.append({
                "code": "RESIDUAL_CAP_OVERRIDDEN_BY_GLOBAL_FEASIBILITY",
                "level": 6, "lambda": lam,
            })

    overlapping = []
    for i in range(n):
        for j in range(i + 1, n):
            a0, a1 = flights[i].get("start"), flights[i].get("end")
            b0, b1 = flights[j].get("start"), flights[j].get("end")
            if a0 and a1 and b0 and b1 and max(a0, b0) <= min(a1, b1):
                overlapping.append([flights[i].get("name"), flights[j].get("name")])
    if overlapping:
        diagnostics.append({
            "code": "START_ORDER_ATTRIBUTION",
            "level": 6,
            "severity": "WARNING",
            "pairs": overlapping,
            "message": "Flights overlap in time; chronological incremental is start-order attribution, not causal first-touch.",
        })

    out = audience_merge(flights, U, pair_details=pairs, model_path="L6_LINE")
    out["flight_relaxation_lambda"] = lam
    out["diagnostics"] = diagnostics
    out["D_L6"] = out["dedup_rate"]

    chronological: List[dict] = []
    sorted_idx = sorted(
        range(n),
        key=lambda i: (flights[i].get("start") or dt.date.max, flights[i].get("end") or dt.date.max),
    )
    if out.get("weights") is not None:
        weights = out["weights"]
        prior_union = 0.0
        seen_mask = 0
        for idx in sorted_idx:
            seen_mask |= 1 << idx
            union = U * sum(p for state, p in enumerate(weights) if state & seen_mask)
            inc = union - prior_union
            chronological.append({
                "name": flights[idx].get("name"),
                "incremental_people": inc,
                "cumulative_people": union,
            })
            prior_union = union
    out["chronological_incremental"] = chronological
    return out


# ---------------------------------------------------------------------------
# Level 7
# ---------------------------------------------------------------------------

def brand_addressability_support(n: int, map_spec: Optional[dict]) -> Optional[List[bool]]:
    """Backward-compatible global state support for simple forbidden/allowed-state maps."""
    if not map_spec:
        return None
    allowed = [True] * (1 << n)
    forbidden_pairs = map_spec.get("forbidden_pairs") or []
    for pair in forbidden_pairs:
        i, j = int(pair[0]), int(pair[1])
        if not (0 <= i < n and 0 <= j < n and i != j):
            raise ReachValidationError("BrandAddressabilityMap: invalid forbidden pair.")
        for state in range(1 << n):
            if ((state >> i) & 1) and ((state >> j) & 1):
                allowed[state] = False
    allowed_states = map_spec.get("allowed_states")
    if allowed_states is not None:
        explicit = [False] * (1 << n)
        for s in allowed_states:
            si = int(s)
            if si < 0 or si >= (1 << n):
                raise ReachValidationError("BrandAddressabilityMap: state out of range.")
            explicit[si] = True
        allowed = [a and b for a, b in zip(allowed, explicit)]
    if not allowed[0]:
        raise ReachValidationError(
            "BrandAddressabilityMap не может запрещать empty state в base U_B scope."
        )
    return allowed


def _brand_line_mask(raw: Any, lines: Sequence[dict]) -> int:
    n = len(lines)
    if isinstance(raw, bool):
        raise ReachValidationError("eligible_line_mask: boolean не является допустимой маской.")
    if isinstance(raw, int):
        mask = raw
    elif isinstance(raw, str):
        s = raw.strip()
        if not s:
            mask = 0
        elif set(s) <= {"0", "1"}:
            mask = int(s, 2)
        else:
            names = [x.strip() for x in s.split(",") if x.strip()]
            return _brand_line_mask(names, lines)
    elif isinstance(raw, Sequence):
        if len(raw) == n and all(isinstance(x, bool) for x in raw):
            mask = sum((1 << i) for i, ok in enumerate(raw) if ok)
        else:
            aliases: Dict[str, int] = {}
            for i, line in enumerate(lines):
                for key in ("name", "label", "plan_id", "line_id"):
                    value = str(line.get(key) or "").strip()
                    if value:
                        aliases[value] = i
                        aliases[value.lower()] = i
            mask = 0
            for token in raw:
                if isinstance(token, int) and 0 <= token < n:
                    idx = token
                else:
                    key = str(token).strip()
                    idx = aliases.get(key, aliases.get(key.lower()))
                    if idx is None:
                        raise ReachValidationError(
                            f"BrandAddressabilityMap: unknown line in eligible_line_mask: {token}."
                        )
                mask |= 1 << idx
    else:
        raise ReachValidationError(
            "eligible_line_mask должен быть integer bitmask, binary string или list line ids/names."
        )
    if mask < 0 or mask >= (1 << n):
        raise ReachValidationError("BrandAddressabilityMap: eligible_line_mask вне диапазона.")
    return mask


def _brand_cells(
    lines: Sequence[dict],
    U: float,
    map_spec: Optional[dict],
) -> Optional[dict]:
    raw_cells = None if not map_spec else map_spec.get("cells")
    if not raw_cells:
        return None
    n = len(lines)
    if n > MAX_ENTITIES:
        raise ReachValidationError(f"Joint state guard: {n}>{MAX_ENTITIES}.")
    cells = []
    total = 0.0
    for idx, raw in enumerate(raw_cells):
        pop = finite(raw.get("population"), f"BrandAddressabilityMap cell[{idx}].population")
        if pop < 0:
            raise ReachValidationError("BrandAddressabilityMap cell population < 0.")
        if pop == 0:
            continue
        mask = _brand_line_mask(raw.get("eligible_line_mask", 0), lines)
        cells.append({
            "cell_id": str(raw.get("cell_id") or f"cell_{idx+1}"),
            "population": pop,
            "mask": mask,
        })
        total += pop
    if not cells:
        raise ReachValidationError("BrandAddressabilityMap cells are empty.")
    tol = max(1e-6, SOLVER_TOL * max(1.0, U))
    if abs(total - U) > tol:
        raise ReachValidationError(
            f"BrandAddressabilityMap cell populations sum to {total}, expected U_B={U}."
        )

    U_l = [0.0] * n
    M: Dict[Tuple[int, int], float] = {}
    for i in range(n):
        U_l[i] = sum(c["population"] for c in cells if (c["mask"] >> i) & 1)
        if U_l[i] <= 0 and float(lines[i].get("reach_1p") or 0) > NUMERICAL_TOL:
            raise ReachValidationError(
                f"BrandAddressabilityMap: Line {i} has Reach>0 but derived U_l=0."
            )
        if float(lines[i].get("reach_1p") or 0) > U_l[i] + NUMERICAL_TOL:
            raise ReachValidationError(
                f"BrandAddressabilityMap: Line {i} Reach exceeds map-derived U_l."
            )
        explicit = lines[i].get("addressable_universe")
        assumed = bool(
            lines[i].get("addressable_universe_assumed")
            or lines[i].get("line_universe_assumed")
        )
        if explicit not in (None, "") and not assumed:
            if abs(float(explicit) - U_l[i]) > tol:
                raise ReachValidationError(
                    f"BrandAddressabilityMap: explicit U_l for Line {i} conflicts with map-derived U_l."
                )
    for i in range(n):
        for j in range(i + 1, n):
            M[(i, j)] = sum(
                c["population"] for c in cells
                if ((c["mask"] >> i) & 1) and ((c["mask"] >> j) & 1)
            )
    return {"cells": cells, "U_l": U_l, "M": M}


def _phase1_general(
    columns: Sequence[Sequence[float]],
    b: Sequence[float],
    *,
    tolerance: float = FEASIBILITY_TOL,
    max_pivots: int = 20_000,
) -> dict:
    """Phase-I LP for arbitrary non-negative latent-state columns."""
    m = len(b)
    if m == 0:
        return {"feasible": True, "objective": 0.0, "pivots": 0}
    if not columns:
        return {"feasible": False, "objective": float("inf"), "pivots": 0, "reason": "EMPTY_SUPPORT"}
    if any(x < -NUMERICAL_TOL for x in b):
        return {"feasible": False, "objective": float("inf"), "pivots": 0, "reason": "NEGATIVE_TARGET"}

    Binv = [[1.0 if i == j else 0.0 for j in range(m)] for i in range(m)]
    basis = [len(columns) + i for i in range(m)]
    xB = [max(0.0, float(x)) for x in b]
    cB = [1.0] * m

    def dot(a: Sequence[float], bb: Sequence[float]) -> float:
        return sum(x * y for x, y in zip(a, bb))

    def basis_y() -> List[float]:
        return [sum(cB[r] * Binv[r][col] for r in range(m)) for col in range(m)]

    objective = sum(c * x for c, x in zip(cB, xB))
    pivots = 0
    while pivots < max_pivots:
        y = basis_y()
        entering = None
        entering_col = None
        for j, col in enumerate(columns):
            if j in basis:
                continue
            if -dot(y, col) < -1e-12:
                entering = j
                entering_col = col
                break
        if entering is None:
            for aidx in range(m):
                var = len(columns) + aidx
                if var in basis:
                    continue
                if 1.0 - y[aidx] < -1e-12:
                    entering = var
                    entering_col = [1.0 if k == aidx else 0.0 for k in range(m)]
                    break
        if entering is None:
            objective = sum(c * x for c, x in zip(cB, xB))
            return {
                "feasible": objective <= tolerance,
                "objective": objective,
                "pivots": pivots,
                "variable_count": len(columns),
                "constraint_count": m,
                "reason": "PHASE1_OPTIMUM",
            }

        d = [dot(row, entering_col) for row in Binv]
        candidates = [(xB[i] / d[i], basis[i], i) for i in range(m) if d[i] > 1e-14]
        if not candidates:
            return {
                "feasible": False, "objective": objective, "pivots": pivots,
                "variable_count": len(columns), "constraint_count": m,
                "reason": "PHASE1_UNBOUNDED",
            }
        theta, _basis_var, leave = min(candidates, key=lambda x: (x[0], x[1]))
        pivot = d[leave]
        old_pivot_row = list(Binv[leave])
        new_xB = [xB[i] - theta * d[i] for i in range(m)]
        new_xB[leave] = theta
        xB = [0.0 if -NUMERICAL_TOL <= x < 0 else x for x in new_xB]
        Binv[leave] = [v / pivot for v in old_pivot_row]
        for i in range(m):
            if i == leave:
                continue
            factor = d[i] / pivot
            if abs(factor) > 0:
                Binv[i] = [Binv[i][k] - factor * old_pivot_row[k] for k in range(m)]
        basis[leave] = entering
        cB[leave] = 0.0 if entering < len(columns) else 1.0
        pivots += 1
        objective = sum(c * x for c, x in zip(cB, xB))
        if objective <= tolerance:
            return {
                "feasible": True, "objective": objective, "pivots": pivots,
                "variable_count": len(columns), "constraint_count": m,
                "reason": "PHASE1_ZERO_OBJECTIVE",
            }
    raise ReachCalculationError("BrandAddressabilityMap Phase-I solver превысил max pivots.")


def _brand_cell_joint(
    lines: Sequence[dict],
    U: float,
    cell_info: dict,
    pair_details: Mapping[Tuple[int, int], dict],
    map_spec: Mapping[str, Any],
) -> dict:
    n = len(lines)
    support = brand_addressability_support(n, {
        "forbidden_pairs": map_spec.get("forbidden_pairs") or [],
        "allowed_states": map_spec.get("allowed_states"),
    }) if (map_spec.get("forbidden_pairs") or map_spec.get("allowed_states") is not None) else None

    variables: List[Tuple[int, int]] = []
    by_cell: Dict[int, List[int]] = {}
    for ci, cell in enumerate(cell_info["cells"]):
        ids = []
        for state in range(1 << n):
            if state & ~cell["mask"]:
                continue
            if support is not None and not support[state]:
                continue
            ids.append(len(variables))
            variables.append((ci, state))
        if not ids:
            raise ReachValidationError(
                f"BrandAddressabilityMap cell {cell['cell_id']} has no feasible joint state."
            )
        by_cell[ci] = ids

    if len(variables) > 100_000:
        raise ReachCalculationError(
            "BrandAddressabilityMap latent state count >100000; map must be made sparser before exact calculation."
        )

    pair_keys = sorted(pair_details)
    events: List[List[bool]] = []
    targets: List[float] = []
    labels: List[str] = []
    for ci, cell in enumerate(cell_info["cells"]):
        events.append([vci == ci for vci, _ in variables])
        targets.append(cell["population"] / U)
        labels.append(f"CELL[{cell['cell_id']}]")
    for i, line in enumerate(lines):
        events.append([bool((state >> i) & 1) for _ci, state in variables])
        targets.append(float(line["reach_1p"]) / U)
        labels.append(f"R[{i}]")
    for i, j in pair_keys:
        events.append([
            bool(((state >> i) & 1) and ((state >> j) & 1))
            for _ci, state in variables
        ])
        targets.append(float(pair_details[(i, j)]["J"]) / U)
        labels.append(f"J[{i},{j}]")

    columns = [
        [1.0 if events[row][col] else 0.0 for row in range(len(events))]
        for col in range(len(variables))
    ]
    feas = _phase1_general(columns, targets)
    if not feas.get("feasible"):
        raise ReachValidationError(
            "GLOBAL_FEASIBILITY=FAIL: BrandAddressabilityMap hard cells/Reach/pairs are incompatible. "
            + str(feas)
        )

    w = [0.0] * len(variables)
    for ci, cell in enumerate(cell_info["cells"]):
        ids = by_cell[ci]
        share = (cell["population"] / U) / len(ids)
        for vid in ids:
            w[vid] = share

    residual = float("inf")
    for it in range(1, MAX_ITERATIONS + 1):
        for event, target, label in zip(events, targets, labels):
            cur = sum(x for x, ok in zip(w, event) if ok)
            if target <= SOLVER_TOL:
                for k, ok in enumerate(event):
                    if ok:
                        w[k] = 0.0
            elif target >= 1.0 - SOLVER_TOL:
                for k, ok in enumerate(event):
                    if not ok:
                        w[k] = 0.0
            else:
                if cur <= 1e-300 or cur >= 1 - 1e-15:
                    raise ReachCalculationError(
                        f"BrandAddressabilityMap MaxEnt/IPF numerical boundary at {label}."
                    )
                a = target / cur
                b = (1.0 - target) / (1.0 - cur)
                for k, ok in enumerate(event):
                    w[k] *= a if ok else b
            z = sum(w)
            if not math.isfinite(z) or z <= 0:
                raise ReachCalculationError("BrandAddressabilityMap MaxEnt normalization failure.")
            inv = 1.0 / z
            w = [x * inv for x in w]

        if it % 5 == 0 or it == MAX_ITERATIONS:
            residual = 0.0
            for event, target in zip(events, targets):
                cur = sum(x for x, ok in zip(w, event) if ok)
                residual = max(residual, abs(cur - target))
            if residual <= SOLVER_TOL:
                state_weights = [0.0] * (1 << n)
                for prob, (_ci, state) in zip(w, variables):
                    state_weights[state] += prob
                return {
                    "weights": state_weights,
                    "iterations": it,
                    "residual": residual,
                    "status": "CONVERGED_ADDRESSABILITY_CELLS",
                    "feasibility": feas,
                    "latent_variable_count": len(variables),
                }
    raise ReachCalculationError(
        f"BrandAddressabilityMap Maximum Entropy не сошёлся за {MAX_ITERATIONS}; residual={residual:.3g}."
    )


def level7_brand(
    lines: Sequence[dict],
    brand_universe: float,
    *,
    custom_pairs: Optional[Mapping[Tuple[int, int], dict]] = None,
    addressability_map: Optional[dict] = None,
) -> dict:
    U = positive(brand_universe, "Brand Master Universe U_B")
    if not lines:
        out = audience_merge([], U, model_path="L7_BRAND")
        out["brand_addressability_status"] = "NOT_APPLICABLE"
        return out
    if len(lines) > MAX_ENTITIES:
        raise ReachValidationError(f"Joint state guard: {len(lines)}>{MAX_ENTITIES}.")
    reaches = [float(x["reach_1p"]) for x in lines]
    for r in reaches:
        if r > U + NUMERICAL_TOL:
            raise ReachValidationError("Line Reach превышает Brand Master Universe.")

    n = len(lines)
    supplied = custom_pairs or {}
    cell_info = _brand_cells(lines, U, addressability_map)
    pairs: Dict[Tuple[int, int], dict] = {}

    if cell_info is not None:
        for i in range(n):
            for j in range(i + 1, n):
                Ui, Uj = cell_info["U_l"][i], cell_info["U_l"][j]
                Mij = cell_info["M"][(i, j)]
                if (i, j) in supplied:
                    meta = normalize_pair_input(
                        supplied[(i, j)], reaches[i], reaches[j], U,
                        Ua=Ui, Ub=Uj, M=Mij,
                        default_source=str(supplied[(i, j)].get("source") or "CUSTOM"),
                    )
                else:
                    meta = overlap_from_rho(
                        reaches[i], reaches[j], U, RHO_LINE_DEFAULT,
                        Ua=Ui, Ub=Uj, M=Mij,
                    )
                    meta["source"] = "BRAND_ADDRESSABILITY_MAP"
                    meta["rho_source"] = "MODEL_DEFAULT"
                meta.update({
                    "U_i": Ui, "U_j": Uj, "M": Mij,
                    "M_source": "BRAND_ADDRESSABILITY_MAP",
                })
                pairs[(i, j)] = meta

        solver = _brand_cell_joint(lines, U, cell_info, pairs, addressability_map or {})
        out = _joint_output(
            lines, U, solver["weights"],
            model_path="L7_BRAND_ADDRESSABILITY_CELLS_MAXENT",
            pair_details=pairs,
            feasibility=solver["feasibility"],
            solver=solver,
        )
        out["brand_addressability_status"] = "STRUCTURED_CELLS"
        out["brand_addressability_cells"] = [
            {
                "cell_id": cell["cell_id"],
                "population": cell["population"],
                "eligible_line_mask": cell["mask"],
            }
            for cell in cell_info["cells"]
        ]
        out["derived_line_universes"] = {
            str(lines[i].get("name") or lines[i].get("label") or i): cell_info["U_l"][i]
            for i in range(n)
        }
        out["D_L7"] = out["dedup_rate"]
        return out

    forbidden = {
        tuple(sorted((int(p[0]), int(p[1]))))
        for p in ((addressability_map or {}).get("forbidden_pairs") or [])
    }
    for i in range(n):
        for j in range(i + 1, n):
            Ui = float(lines[i].get("addressable_universe") or U)
            Uj = float(lines[j].get("addressable_universe") or U)
            if (i, j) in supplied:
                pairs[(i, j)] = normalize_pair_input(
                    supplied[(i, j)], reaches[i], reaches[j], U,
                    Ua=Ui, Ub=Uj,
                    M=supplied[(i, j)].get("M"),
                    default_source=str(supplied[(i, j)].get("source") or "CUSTOM"),
                )
                continue
            if (i, j) in forbidden:
                pairs[(i, j)] = {
                    "J": 0.0, "J0": 0.0, "J_min": 0.0, "J_max": 0.0,
                    "rho": 0.0, "U_i": Ui, "U_j": Uj, "M": 0.0,
                    "M_source": "BRAND_ADDRESSABILITY_MAP",
                    "source": "BRAND_ADDRESSABILITY_MAP",
                    "rho_source": "NOT_APPLICABLE",
                }
                continue
            Mij = None
            if lines[i].get("addressable_intersections"):
                Mij = lines[i]["addressable_intersections"].get(lines[j].get("name"))
            if Mij is None:
                Mij = Ui * Uj / U
                m_source = "MODEL_DEFAULT"
            else:
                m_source = "MEASURED_ADDRESSABLE"
            meta = overlap_from_rho(
                reaches[i], reaches[j], U, RHO_LINE_DEFAULT,
                Ua=Ui, Ub=Uj, M=Mij,
            )
            meta.update({
                "U_i": Ui, "U_j": Uj, "M": Mij,
                "M_source": m_source,
                "source": "MODEL_DEFAULT" if m_source == "MODEL_DEFAULT" else "MEASURED_ADDRESSABLE",
                "rho_source": "MODEL_DEFAULT",
            })
            pairs[(i, j)] = meta

    support = brand_addressability_support(n, addressability_map)
    structured = support is not None or any(
        v.get("M_source") == "MEASURED_ADDRESSABLE" for v in pairs.values()
    )
    out = audience_merge(
        lines, U, pair_details=pairs,
        neutral_unstructured=(not structured and not supplied),
        support=support,
        model_path="L7_BRAND",
    )
    out["brand_addressability_status"] = "STRUCTURED" if support is not None else (
        "ADDRESSABILITY_NEUTRAL" if structured else "UNSTRUCTURED_NEUTRAL"
    )
    out["D_L7"] = out["dedup_rate"]
    return out

