from __future__ import annotations

"""
Reach Engine v1.6 — isolated experimental calculation core.

This module is intentionally separate from the production 0.52 reach engine.
It reuses only the workbook parser from engine.py and does not call apply_reach(),
combine_reach_union() or any of the legacy reach aggregation functions.

Implemented production path:
L1 placement technical reach -> L2 Quick people -> aggregate L3 fallback ->
L4 platform/family/channel merge -> L5 channel/flight merge ->
L6 flight/line merge -> L7 line/brand merge.

The module keeps every model-default relaxation and approximation visible in diagnostics.
"""

import datetime as dt
import json
import math
from collections import defaultdict
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from engine import discover_media_plan_groups, parse_media_plan, norm

VERSION = "1.6"
MAX_ENTITIES = 12
IPF_TOL = 1e-8
IPF_MAX_ITER = 1800
SIGMA_DEFAULT = 2.50
K_DEFAULT = 2.40
RHO_CHANNEL_DEFAULT = -0.35
RESIDUAL_CAP = 0.10
ARITH_REL_TOL = 0.03


class V16Error(ValueError):
    pass


def _json_default(v: Any):
    if isinstance(v, (dt.datetime, dt.date)):
        return v.isoformat()
    raise TypeError(f"Object of type {v.__class__.__name__} is not JSON serializable")


def _json(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, separators=(",", ":"), default=_json_default)


def _finite(v: Any, name: str) -> float:
    try:
        x = float(v)
    except Exception as e:
        raise V16Error(f"{name}: ожидается число.") from e
    if not math.isfinite(x):
        raise V16Error(f"{name}: ожидается конечное число.")
    return x


def _positive(v: Any, name: str) -> float:
    x = _finite(v, name)
    if x <= 0:
        raise V16Error(f"{name} должен быть больше 0.")
    return x


def _norm_ta(v: Any) -> str:
    return " ".join(str(v or "").strip().lower().replace("ё", "е").split())


def _date(v: Optional[dt.date]) -> Optional[str]:
    return v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else None


def _gap_days(a_end: Optional[dt.date], b_start: Optional[dt.date]) -> int:
    if not a_end or not b_start:
        return 0
    # Inclusive convention: 28.02 -> 01.03 means G=0.
    return max(0, (b_start - a_end).days - 1)


def _duration_days(a: Optional[dt.date], b: Optional[dt.date]) -> int:
    if not a or not b:
        return 1
    return max(1, (b - a).days + 1)


# --------------------------- L1 / L2 ---------------------------

def level1_technical(row, diagnostics: List[dict]) -> Optional[float]:
    I = None if row.impressions is None else _finite(row.impressions, "Impressions")
    F = None if row.frequency is None else _finite(row.frequency, "Average Frequency")
    supplied = None if row.tech_reach is None else _finite(row.tech_reach, "Reach")

    if I is not None and I < 0:
        raise V16Error(f"{row.sheet}:{row.source_row+1}: Impressions < 0.")
    if supplied is not None and supplied < 0:
        raise V16Error(f"{row.sheet}:{row.source_row+1}: Reach < 0.")
    if F is not None and F <= 0:
        raise V16Error(f"{row.sheet}:{row.source_row+1}: Average Frequency должна быть > 0.")

    if supplied is not None:
        if I is not None:
            if I == 0 and supplied > 0:
                raise V16Error(f"{row.sheet}:{row.source_row+1}: I=0 при Reach>0.")
            if supplied > I + 1e-9:
                raise V16Error(f"{row.sheet}:{row.source_row+1}: Reach превышает Impressions.")
        if supplied == 0 and I is not None and I > 0:
            raise V16Error(f"{row.sheet}:{row.source_row+1}: Reach=0 при Impressions>0.")
        if I is not None and F is not None:
            if F < 1:
                raise V16Error(f"{row.sheet}:{row.source_row+1}: Average Frequency < 1.")
            expected = supplied * F
            rel = abs(I - expected) / max(1.0, abs(I))
            if rel > ARITH_REL_TOL:
                raise V16Error(
                    f"{row.sheet}:{row.source_row+1}: арифметическая ошибка — "
                    f"Impressions не согласуются с Reach × Frequency."
                )
            elif rel > 1e-6:
                diagnostics.append({
                    "code": "L1_ROUNDING_DIAGNOSTIC",
                    "row": row.source_row + 1,
                    "sheet": row.sheet,
                    "relative_difference": rel,
                })
        return supplied

    if I is None:
        return None
    if I == 0:
        return 0.0
    if F is None:
        return None
    if F < 1:
        raise V16Error(f"{row.sheet}:{row.source_row+1}: Average Frequency < 1.")
    return I / F


def level2_quick(rtech: float, U: float, K: float) -> float:
    if K < 1:
        raise V16Error("K должен быть >= 1.")
    r = rtech / K
    if r > U + 1e-6:
        raise V16Error(
            f"Level 2: Human Reach {r:.0f} превышает Universe {U:.0f}. "
            "Проверьте Reach, Universe и K."
        )
    return max(0.0, r)


# --------------------------- frequency ---------------------------

_PL_CACHE: Dict[Tuple[float, float], List[float]] = {}


def _normal_grid(n: int = 321, lo: float = -7.0, hi: float = 7.0):
    step = (hi - lo) / (n - 1)
    z = [lo + i * step for i in range(n)]
    w = []
    c = 1.0 / math.sqrt(2.0 * math.pi)
    for i, x in enumerate(z):
        simpson = 1 if i in (0, n - 1) else (4 if i % 2 else 2)
        w.append(simpson * c * math.exp(-0.5 * x * x) * step / 3.0)
    s = sum(w)
    return z, [x / s for x in w]


_Z, _ZW = _normal_grid()


def _pl_moments(mu: float, sigma: float) -> Tuple[float, List[float]]:
    p = [0.0] * 6  # P(N=0..5)
    mean = 0.0
    for z, wz in zip(_Z, _ZW):
        lam = math.exp(mu + sigma * z)
        mean += wz * lam
        term = math.exp(-lam)
        p[0] += wz * term
        for k in range(1, 6):
            term *= lam / k
            p[k] += wz * term
    return mean, p


def poisson_lognormal_exact(mean_frequency: float, sigma: float = SIGMA_DEFAULT) -> List[float]:
    f = _finite(mean_frequency, "Human Average Frequency")
    if f < 1 - 1e-9:
        raise V16Error("Human Average Frequency не может быть меньше 1.")
    if abs(f - 1.0) <= 1e-9:
        return [1.0, 0.0, 0.0, 0.0, 0.0, 0.0]

    key = (round(f, 5), round(sigma, 4))
    if key in _PL_CACHE:
        return list(_PL_CACHE[key])

    lo, hi = -20.0, 8.0
    for _ in range(90):
        mid = (lo + hi) / 2.0
        mean, probs = _pl_moments(mid, sigma)
        p0 = probs[0]
        cond = mean / max(1e-15, 1.0 - p0)
        if cond < f:
            lo = mid
        else:
            hi = mid
    mu = (lo + hi) / 2.0
    _, probs = _pl_moments(mu, sigma)
    p0 = probs[0]
    denom = max(1e-15, 1.0 - p0)
    exact = [probs[k] / denom for k in range(1, 6)]
    exact6 = max(0.0, 1.0 - sum(exact))
    out = exact + [exact6]
    s = sum(out)
    out = [max(0.0, x / s) for x in out]
    _PL_CACHE[key] = list(out)
    return out


def _convolve(a: Sequence[float], b: Sequence[float]) -> List[float]:
    out = [0.0] * 6
    for ia, pa in enumerate(a, 1):
        if pa <= 0:
            continue
        for ib, pb in enumerate(b, 1):
            if pb <= 0:
                continue
            k = min(6, ia + ib)
            out[k - 1] += pa * pb
    return out


def _reach_from_exact(U: float, exact_unconditional: Sequence[float], impressions: float) -> dict:
    ex = list(exact_unconditional)
    cumulative = []
    for k in range(6):
        cumulative.append(U * sum(ex[k:]))
    r1 = cumulative[0]
    return {
        "reach_1p": r1,
        "reach_2p": cumulative[1],
        "reach_3p": cumulative[2],
        "reach_4p": cumulative[3],
        "reach_5p": cumulative[4],
        "reach_6p": cumulative[5],
        "pct_1p": r1 / U if U > 0 else 0.0,
        "avg_frequency": impressions / r1 if r1 > 0 else None,
        "impressions": impressions,
        "exact_counts": [U * x for x in ex],
    }


# --------------------------- audience merge ---------------------------

def _pair_bounds(Ra: float, Rb: float, U: float, Ua: Optional[float] = None,
                 Ub: Optional[float] = None, M: Optional[float] = None) -> Tuple[float, float]:
    if Ua is None or Ub is None or M is None:
        return max(0.0, Ra + Rb - U), min(Ra, Rb)
    ma = max(0.0, Ra - (Ua - M))
    mb = max(0.0, Rb - (Ub - M))
    return max(0.0, ma + mb - M), min(Ra, Rb, M)


def _neutral_overlap(Ra: float, Rb: float, U: float, Ua: Optional[float] = None,
                     Ub: Optional[float] = None, M: Optional[float] = None) -> float:
    if Ua and Ub and M is not None and Ua > 0 and Ub > 0:
        return M * (Ra / Ua) * (Rb / Ub)
    return Ra * Rb / U


def _signed_overlap(Ra: float, Rb: float, U: float, rho: float,
                    Ua: Optional[float] = None, Ub: Optional[float] = None,
                    M: Optional[float] = None) -> float:
    j0 = _neutral_overlap(Ra, Rb, U, Ua, Ub, M)
    jmin, jmax = _pair_bounds(Ra, Rb, U, Ua, Ub, M)
    if rho >= 0:
        j = j0 + rho * (jmax - j0)
    else:
        j = j0 + rho * (j0 - jmin)
    return min(jmax, max(jmin, j))


def _independent_weights(reaches: Sequence[float], U: float, support: Optional[Sequence[bool]] = None) -> List[float]:
    n = len(reaches)
    probs = [r / U for r in reaches]
    out = [0.0] * (1 << n)
    total = 0.0
    for s in range(1 << n):
        if support is not None and not support[s]:
            continue
        p = 1.0
        for i, q in enumerate(probs):
            p *= q if (s >> i) & 1 else (1.0 - q)
        out[s] = p
        total += p
    if total <= 0:
        raise V16Error("Joint model: пустой support.")
    return [x / total for x in out]


def _constraint_events(n: int, pair_targets: Dict[Tuple[int, int], float], U: float):
    events = []
    for i in range(n):
        mask = [bool((s >> i) & 1) for s in range(1 << n)]
        events.append((mask, None))
    for (i, j), target in pair_targets.items():
        mask = [bool(((s >> i) & 1) and ((s >> j) & 1)) for s in range(1 << n)]
        events.append((mask, target / U))
    return events


def _ipf_weights(reaches: Sequence[float], U: float, pair_targets: Dict[Tuple[int, int], float],
                 support: Optional[Sequence[bool]] = None, tol: float = IPF_TOL,
                 max_iter: int = IPF_MAX_ITER) -> Tuple[Optional[List[float]], float, int]:
    n = len(reaches)
    if n > MAX_ENTITIES:
        raise V16Error(f"Слишком много сущностей для exact joint model: {n}>{MAX_ENTITIES}.")
    size = 1 << n
    if support is None:
        support = [True] * size
    allowed = [i for i, ok in enumerate(support) if ok]
    if not allowed:
        return None, float("inf"), 0
    w = [0.0] * size
    init = 1.0 / len(allowed)
    for s in allowed:
        w[s] = init

    constraints: List[Tuple[List[bool], float]] = []
    for i, r in enumerate(reaches):
        constraints.append(([bool((s >> i) & 1) for s in range(size)], r / U))
    for (i, j), target in sorted(pair_targets.items()):
        constraints.append(([bool(((s >> i) & 1) and ((s >> j) & 1)) for s in range(size)], target / U))

    for it in range(1, max_iter + 1):
        for event, target in constraints:
            target = min(1.0, max(0.0, target))
            cur = sum(w[s] for s in allowed if event[s])
            if target <= tol:
                for s in allowed:
                    if event[s]:
                        w[s] = 0.0
            elif target >= 1.0 - tol:
                for s in allowed:
                    if not event[s]:
                        w[s] = 0.0
            else:
                if cur <= 1e-18 or cur >= 1.0 - 1e-18:
                    return None, float("inf"), it
                a = target / cur
                b = (1.0 - target) / (1.0 - cur)
                for s in allowed:
                    w[s] *= a if event[s] else b
            z = sum(w[s] for s in allowed)
            if z <= 0 or not math.isfinite(z):
                return None, float("inf"), it
            inv = 1.0 / z
            for s in allowed:
                w[s] *= inv

        if it % 5 == 0 or it == max_iter:
            residual = 0.0
            for event, target in constraints:
                cur = sum(w[s] for s in allowed if event[s])
                residual = max(residual, abs(cur - target))
            if residual <= tol:
                return w, residual, it
    return None, residual, max_iter


def _two_weights(Ra: float, Rb: float, J: float, U: float) -> List[float]:
    vals = [
        1.0 - (Ra + Rb - J) / U,
        (Ra - J) / U,
        (Rb - J) / U,
        J / U,
    ]
    if min(vals) < -1e-8:
        raise V16Error("Pair overlap несовместим с Reach/Universe.")
    return [max(0.0, x) for x in vals]


def _joint_output(entities: Sequence[dict], U: float, weights: Sequence[float], model_path: str,
                  pair_targets: Optional[Dict[Tuple[int, int], float]] = None, extra: Optional[dict] = None) -> dict:
    n = len(entities)
    exact_uncond = [0.0] * 6
    for state, ws in enumerate(weights):
        if ws <= 0 or state == 0:
            continue
        g = [1.0, 0, 0, 0, 0, 0]
        first = True
        for i, ent in enumerate(entities):
            if (state >> i) & 1:
                if first:
                    g = list(ent["freq_dist"])
                    first = False
                else:
                    g = _convolve(g, ent["freq_dist"])
        for k in range(6):
            exact_uncond[k] += ws * g[k]

    impressions = sum(float(e.get("impressions") or 0.0) for e in entities)
    out = _reach_from_exact(U, exact_uncond, impressions)
    out.update({
        "model_path": model_path,
        "entity_count": n,
        "pair_targets": {
            f"{entities[i]['name']} × {entities[j]['name']}": v
            for (i, j), v in (pair_targets or {}).items()
        },
        "weights": weights if n <= 6 else None,
    })
    if extra:
        out.update(extra)
    return out


def merge_entities(entities: Sequence[dict], U: float, pair_targets: Optional[Dict[Tuple[int, int], float]] = None,
                   neutral_unstructured: bool = False, support: Optional[Sequence[bool]] = None,
                   model_path: str = "AUDIENCE_MERGE") -> dict:
    ents = [e for e in entities if float(e.get("reach_1p") or 0.0) > 0]
    if not ents:
        return {
            "reach_1p": 0.0, "reach_2p": 0.0, "reach_3p": 0.0, "reach_4p": 0.0,
            "reach_5p": 0.0, "reach_6p": 0.0, "pct_1p": 0.0, "avg_frequency": None,
            "impressions": sum(float(e.get("impressions") or 0.0) for e in entities),
            "exact_counts": [0.0] * 6, "model_path": model_path, "entity_count": 0,
            "freq_dist": [1, 0, 0, 0, 0, 0],
        }
    if len(ents) == 1:
        e = dict(ents[0])
        exact_counts = [e["reach_1p"] * x for x in e["freq_dist"]]
        res = _reach_from_exact(U, [x / U for x in exact_counts], float(e.get("impressions") or 0))
        res.update({"model_path": model_path + "_IDENTITY", "entity_count": 1, "freq_dist": list(e["freq_dist"])})
        return res

    reaches = [float(e["reach_1p"]) for e in ents]
    for r in reaches:
        if r < -1e-9 or r > U + 1e-6:
            raise V16Error("Reach сущности выходит за Universe.")

    if neutral_unstructured and pair_targets is None:
        weights = _independent_weights(reaches, U, support=support)
        result = _joint_output(ents, U, weights, model_path + "_INDEPENDENCE")
    else:
        pt = pair_targets or {}
        if len(ents) == 2:
            J = pt.get((0, 1))
            if J is None:
                J = _neutral_overlap(reaches[0], reaches[1], U)
            weights = _two_weights(reaches[0], reaches[1], J, U)
            result = _joint_output(ents, U, weights, model_path + "_ANALYTIC", {(0, 1): J})
        else:
            weights, residual, it = _ipf_weights(reaches, U, pt, support=support)
            if weights is None:
                raise V16Error("CALCULATION ERROR: Maximum Entropy/IPF не сошёлся для допустимой системы.")
            result = _joint_output(
                ents, U, weights, model_path + "_MAXENT", pt,
                {"solver_residual": residual, "solver_iterations": it},
            )

    r1 = result["reach_1p"]
    if r1 > 0:
        result["freq_dist"] = [
            result["exact_counts"][k] / r1 for k in range(6)
        ]
    else:
        result["freq_dist"] = [1, 0, 0, 0, 0, 0]
    return result


def _is_feasible(reaches: Sequence[float], U: float, pair_targets: Dict[Tuple[int, int], float]) -> bool:
    if len(reaches) <= 2:
        if len(reaches) < 2:
            return True
        j = pair_targets.get((0, 1), _neutral_overlap(reaches[0], reaches[1], U))
        lo, hi = _pair_bounds(reaches[0], reaches[1], U)
        return lo - 1e-8 <= j <= hi + 1e-8
    w, residual, _ = _ipf_weights(reaches, U, pair_targets, tol=2e-7, max_iter=900)
    return w is not None and residual <= 2e-7


# --------------------------- Level 4 / 5 ---------------------------

def _entity_from_row(row, U: float, K: float, diagnostics: List[dict]) -> Optional[dict]:
    rtech = level1_technical(row, diagnostics)
    if rtech is None:
        return None
    rpeople = level2_quick(rtech, U, K)
    I = float(row.impressions or 0.0)
    if I < 0:
        raise V16Error("Impressions < 0.")
    fbar = I / rpeople if rpeople > 0 and I > 0 else (float(row.frequency) if row.frequency else 1.0)
    if rpeople > 0 and fbar < 1:
        # Supplied placement Reach may be technical while impressions are rounded.
        fbar = 1.0
        diagnostics.append({
            "code": "DEGENERATE_FREQUENCY_1",
            "sheet": row.sheet, "row": row.source_row + 1,
        })
    freq = poisson_lognormal_exact(fbar if rpeople > 0 else 1.0)
    return {
        "name": row.platform_canonical or row.platform or f"row_{row.source_row+1}",
        "reach_1p": rpeople,
        "impressions": I,
        "freq_dist": freq,
        "platform": row.platform_canonical or row.platform or "Other",
        "channel": row.channel or "Other",
        "source_row": row.source_row + 1,
        "sheet": row.sheet,
    }


def level4_channel(rows: Sequence[Any], U: float, K: float, diagnostics: List[dict]) -> List[dict]:
    units: List[dict] = []
    signatures = defaultdict(list)
    for row in rows:
        e = _entity_from_row(row, U, K, diagnostics)
        if e is not None and e["reach_1p"] > 0:
            units.append(e)
        sig = (
            norm(row.platform_canonical or row.platform), norm(row.format), norm(row.buying_model),
            round(float(row.budget or 0), 2), round(float(row.impressions or 0), 2),
            round(float(row.tech_reach or 0), 2), row.start, row.end,
        )
        signatures[sig].append((row.sheet, row.source_row + 1))
    for sig, locs in signatures.items():
        if len(locs) > 1 and any(sig):
            diagnostics.append({"code": "POSSIBLE_DUPLICATE_ROWS", "rows": locs})

    by_channel: Dict[str, List[dict]] = defaultdict(list)
    for e in units:
        by_channel[e["channel"]].append(e)

    channels = []
    for ch, ch_units in by_channel.items():
        by_family: Dict[str, List[dict]] = defaultdict(list)
        for e in ch_units:
            # One Inventory Unit -> exactly one Audience Family.
            family = e["platform"] or "Other"
            by_family[family].append(e)

        families = []
        for fam, fam_units in by_family.items():
            if len(fam_units) == 1:
                m = merge_entities(fam_units, U, model_path="L4_FAMILY")
            else:
                pt = {}
                for i in range(len(fam_units)):
                    for j in range(i + 1, len(fam_units)):
                        pt[(i, j)] = _neutral_overlap(fam_units[i]["reach_1p"], fam_units[j]["reach_1p"], U)
                m = merge_entities(fam_units, U, pair_targets=pt, model_path="L4_FAMILY")
            m["name"] = fam
            families.append(m)

        if len(families) == 1:
            cm = merge_entities(families, U, model_path="L4_CHANNEL")
        else:
            # No structured M_ij is available from ordinary media-plan rows,
            # therefore neutral unstructured path is the documented fallback.
            cm = merge_entities(families, U, neutral_unstructured=True, model_path="L4_CHANNEL")
        cm["name"] = ch
        cm["families"] = families
        channels.append(cm)
    return channels


def _channel_pair_targets(channels: Sequence[dict], U: float, lam: float) -> Dict[Tuple[int, int], float]:
    rho = RHO_CHANNEL_DEFAULT * lam
    pt = {}
    for i in range(len(channels)):
        for j in range(i + 1, len(channels)):
            pt[(i, j)] = _signed_overlap(channels[i]["reach_1p"], channels[j]["reach_1p"], U, rho)
    return pt


def level5_flight(channels: Sequence[dict], U: float, diagnostics: List[dict]) -> dict:
    if not channels:
        return merge_entities([], U, model_path="L5_FLIGHT")
    if len(channels) <= 2:
        pt = _channel_pair_targets(channels, U, 1.0) if len(channels) == 2 else None
        out = merge_entities(channels, U, pair_targets=pt, model_path="L5_FLIGHT")
        out["rho_target"] = RHO_CHANNEL_DEFAULT
        out["rho_effective"] = RHO_CHANNEL_DEFAULT
        out["relaxation_lambda"] = 1.0
        return out

    reaches = [c["reach_1p"] for c in channels]
    target = _channel_pair_targets(channels, U, 1.0)
    if _is_feasible(reaches, U, target):
        lam = 1.0
    else:
        neutral = _channel_pair_targets(channels, U, 0.0)
        if not _is_feasible(reaches, U, neutral):
            raise V16Error("Level 5: система несовместима даже при neutral overlap.")
        lo, hi = 0.0, 1.0
        for _ in range(45):
            mid = (lo + hi) / 2.0
            if _is_feasible(reaches, U, _channel_pair_targets(channels, U, mid)):
                lo = mid
            else:
                hi = mid
        lam = lo
        diagnostics.append({
            "code": "DEFAULT_RELAXED_FOR_GLOBAL_FEASIBILITY",
            "level": 5, "lambda": lam,
            "rho_target": RHO_CHANNEL_DEFAULT,
            "rho_effective": RHO_CHANNEL_DEFAULT * lam,
        })
    pt = _channel_pair_targets(channels, U, lam)
    out = merge_entities(channels, U, pair_targets=pt, model_path="L5_FLIGHT")
    out["rho_target"] = RHO_CHANNEL_DEFAULT
    out["rho_effective"] = RHO_CHANNEL_DEFAULT * lam
    out["relaxation_lambda"] = lam
    return out


# --------------------------- Level 6 ---------------------------

_Q_POINTS = [(0, .20), (14, .15), (28, .125), (42, .10), (56, .05), (68, 0.0)]


def q_temporal(gap: int) -> float:
    g = max(0, int(gap))
    if g >= 68:
        return 0.0
    for (x1, y1), (x2, y2) in zip(_Q_POINTS, _Q_POINTS[1:]):
        if x1 <= g <= x2:
            t = (g - x1) / (x2 - x1)
            return y1 + t * (y2 - y1)
    return 0.0


def universe_multiplier(U: float) -> float:
    pts = [(5_000_000, 2.50), (7_500_000, 2.25), (10_000_000, 2.00), (12_500_000, 1.50), (15_000_000, 1.00)]
    if U <= pts[0][0]:
        return pts[0][1]
    if U >= pts[-1][0]:
        return pts[-1][1]
    for (x1, y1), (x2, y2) in zip(pts, pts[1:]):
        if x1 <= U <= x2:
            t = (U - x1) / (x2 - x1)
            return y1 + t * (y2 - y1)
    return 1.0


def _l6_pair_basic(a: dict, b: dict, U: float) -> Tuple[float, dict]:
    Ra, Rb = a["reach_1p"], b["reach_1p"]
    if (a["start"] or dt.date.min) <= (b["start"] or dt.date.min):
        G = _gap_days(a.get("end"), b.get("start"))
    else:
        G = _gap_days(b.get("end"), a.get("start"))
    qt = q_temporal(G)
    mu = universe_multiplier(U)
    minr = min(Ra, Rb)
    j_temporal = minr * qt * mu
    j_residual = min(Ra * Rb / U, RESIDUAL_CAP * minr)
    j_target = max(j_temporal, j_residual)
    jmin, jmax = _pair_bounds(Ra, Rb, U)
    j = min(jmax, max(jmin, j_target))
    return j, {
        "gap_days": G,
        "q_temporal": qt,
        "M_U": mu,
        "J_temporal": j_temporal,
        "J_residual": j_residual,
        "J_target": j_target,
        "J_min": jmin,
        "J_max": jmax,
        "bound_adjusted": abs(j - j_target) > 1e-8,
    }


def _aon_slice_reach(aon: dict, burst: dict, U: float) -> float:
    a0, a1 = aon.get("start"), aon.get("end")
    b0, b1 = burst.get("start"), burst.get("end")
    if not a0 or not a1 or not b0 or not b1:
        return min(aon["reach_1p"], burst["reach_1p"])
    overlap_start = max(a0, b0)
    overlap_end = min(a1, b1)
    if overlap_end < overlap_start:
        return 0.0
    share = _duration_days(overlap_start, overlap_end) / _duration_days(a0, a1)
    p = min(0.999999999, max(0.0, aon["reach_1p"] / U))
    # Constant-hazard fallback: U*(1-(1-p)^share).
    return U * (1.0 - (1.0 - p) ** share)


def _l6_pair(a: dict, b: dict, U: float, diagnostics: List[dict]) -> Tuple[float, dict]:
    if bool(a.get("is_common")) ^ bool(b.get("is_common")):
        aon = a if a.get("is_common") else b
        burst = b if a.get("is_common") else a
        slice_r = _aon_slice_reach(aon, burst, U)
        slice_ent = dict(aon)
        slice_ent["reach_1p"] = slice_r
        slice_ent["start"] = burst.get("start")
        slice_ent["end"] = burst.get("end")
        j1, meta1 = _l6_pair_basic(slice_ent, burst, U)
        burst_remaining = max(0.0, burst["reach_1p"] - j1)
        aon_rest = max(0.0, aon["reach_1p"] - slice_r)
        j2 = min(
            burst_remaining * aon_rest / U if U > 0 else 0.0,
            RESIDUAL_CAP * min(burst_remaining, aon_rest),
        )
        j = j1 + j2
        jmin, jmax = _pair_bounds(a["reach_1p"], b["reach_1p"], U)
        j = min(jmax, max(jmin, j))
        diagnostics.append({
            "code": "AON_STAGED_MERGE",
            "aon": aon["name"], "burst": burst["name"],
            "slice_reach": slice_r,
            "slice_source": "APPROXIMATION_CONSTANT_HAZARD",
            "J_same_period": j1, "J_rest": j2,
        })
        return j, {
            "aon_staged": True, "slice_reach": slice_r,
            "J_same_period": j1, "J_rest": j2,
            "J_min": jmin, "J_max": jmax,
            "meta_same_period": meta1,
        }
    return _l6_pair_basic(a, b, U)


def _normalize_flight_groups(plan) -> List[dict]:
    raw = []
    for f in plan.flights:
        start = f.period_start
        end = f.period_end
        if not start and f.intervals:
            start = min(x[0] for x in f.intervals)
        if not end and f.intervals:
            end = max(x[1] for x in f.intervals)
        raw.append({
            "ids": [f.id], "label": f.label, "start": start, "end": end,
            "ta_name": f.ta_name or "", "is_common": bool(f.is_common),
        })
    raw.sort(key=lambda x: (x["start"] or dt.date.max, x["end"] or dt.date.max))
    out: List[dict] = []
    for item in raw:
        if not out:
            out.append(item)
            continue
        prev = out[-1]
        compatible_ta = not prev["ta_name"] or not item["ta_name"] or _norm_ta(prev["ta_name"]) == _norm_ta(item["ta_name"])
        if (not prev["is_common"] and not item["is_common"] and compatible_ta
                and prev["end"] and item["start"] and _gap_days(prev["end"], item["start"]) == 0):
            prev["ids"].extend(item["ids"])
            prev["label"] = prev["label"] + " + " + item["label"]
            prev["end"] = max(prev["end"], item["end"]) if item["end"] else prev["end"]
        else:
            out.append(item)
    return out


def level6_line(flights: Sequence[dict], U: float, diagnostics: List[dict]) -> dict:
    if not flights:
        return merge_entities([], U, model_path="L6_LINE")
    if len(flights) == 1:
        out = merge_entities(flights, U, model_path="L6_LINE")
        out["flight_relaxation_lambda"] = 1.0
        return out

    pt = {}
    meta = {}
    for i in range(len(flights)):
        for j in range(i + 1, len(flights)):
            val, m = _l6_pair(flights[i], flights[j], U, diagnostics)
            pt[(i, j)] = val
            meta[(i, j)] = m

    reaches = [f["reach_1p"] for f in flights]
    lam = 1.0
    if len(flights) >= 3 and not _is_feasible(reaches, U, pt):
        # Common multiplier >=1 for MODEL_DEFAULT overlaps. Keep relative structure.
        max_lam = float("inf")
        for (i, j), v in pt.items():
            if v <= 1e-12:
                continue
            _, jmax = _pair_bounds(reaches[i], reaches[j], U)
            max_lam = min(max_lam, jmax / v)
        if not math.isfinite(max_lam):
            max_lam = 8.0
        max_lam = max(1.0, min(max_lam, 20.0))

        found = None
        steps = 80
        prev = 1.0
        for s in range(1, steps + 1):
            cand = 1.0 + (max_lam - 1.0) * s / steps
            cand_pt = {(i, j): min(_pair_bounds(reaches[i], reaches[j], U)[1], v * cand)
                       for (i, j), v in pt.items()}
            if _is_feasible(reaches, U, cand_pt):
                found = (prev, cand)
                break
            prev = cand
        if found is None:
            raise V16Error("Level 6: MODEL_DEFAULT overlaps нельзя привести к global feasibility единым коэффициентом.")
        lo, hi = found
        for _ in range(40):
            mid = (lo + hi) / 2.0
            cand_pt = {(i, j): min(_pair_bounds(reaches[i], reaches[j], U)[1], v * mid)
                       for (i, j), v in pt.items()}
            if _is_feasible(reaches, U, cand_pt):
                hi = mid
            else:
                lo = mid
        lam = hi
        new_pt = {}
        cap_override = False
        for (i, j), v in pt.items():
            _, jmax = _pair_bounds(reaches[i], reaches[j], U)
            nv = min(jmax, v * lam)
            new_pt[(i, j)] = nv
            minr = min(reaches[i], reaches[j])
            if minr > 0 and nv > RESIDUAL_CAP * minr + 1e-8:
                # 10% is a model residual target cap; hard global feasibility has priority.
                cap_override = True
        pt = new_pt
        diagnostics.append({
            "code": "DEFAULT_RELAXED_FOR_GLOBAL_FEASIBILITY",
            "level": 6, "lambda": lam,
        })
        if cap_override:
            diagnostics.append({
                "code": "RESIDUAL_CAP_OVERRIDDEN_BY_GLOBAL_FEASIBILITY",
                "level": 6, "lambda": lam,
            })

    out = merge_entities(flights, U, pair_targets=pt, model_path="L6_LINE")
    out["flight_relaxation_lambda"] = lam
    out["pair_meta"] = {
        f"{flights[i]['name']} × {flights[j]['name']}": meta[(i, j)]
        for (i, j) in meta
    }
    return out


# --------------------------- Line / Brand orchestration ---------------------------

def _plan_universe(plan, override: Optional[float]) -> float:
    if override not in (None, ""):
        return _positive(override, "Universe")
    if plan.universe is not None and float(plan.universe) > 0:
        return float(plan.universe)
    raise V16Error(f"{plan.display_name or plan.line or 'Line'}: Universe не найден. Укажите его вручную.")


def _line_ta(plan, groups: Sequence[dict]) -> str:
    names = []
    for g in groups:
        if g.get("ta_name"):
            n = " ".join(str(g["ta_name"]).split())
            if n and n not in names:
                names.append(n)
    return names[0] if len(names) == 1 else (plan.line or plan.display_name or "")


def calculate_line(plan, U: float, K: float, diagnostics: List[dict]) -> dict:
    groups = _normalize_flight_groups(plan)
    flights = []
    for g in groups:
        rows = plan.detail_rows(g["ids"])
        channels = level4_channel(rows, U, K, diagnostics)
        flight = level5_flight(channels, U, diagnostics)
        flight.update({
            "name": g["label"],
            "source_flight_ids": list(g["ids"]),
            "start": g["start"],
            "end": g["end"],
            "is_common": g["is_common"],
            "ta_name": g["ta_name"],
            "channels": channels,
        })
        flights.append(flight)

    line = level6_line(flights, U, diagnostics)
    line.update({
        "name": plan.line or plan.display_name or plan.campaign or "Line",
        "brand": plan.brand or "",
        "universe": U,
        "ta_name": _line_ta(plan, groups),
        "flights": flights,
    })
    return line


def _brand_merge(lines: Sequence[dict], U: float, diagnostics: List[dict]) -> dict:
    if not lines:
        return merge_entities([], U, model_path="L7_BRAND")
    if len(lines) == 1:
        out = merge_entities(lines, U, model_path="L7_BRAND")
        out["name"] = lines[0].get("brand") or "Brand"
        return out

    ta_keys = {_norm_ta(x.get("ta_name")) for x in lines if _norm_ta(x.get("ta_name"))}
    if len(ta_keys) > 1:
        raise V16Error(
            "TA_NORMALIZATION_REQUIRED: Lines имеют разные ЦА. "
            "Перед Level 7 пересчитайте все Lines на главную Brand TA."
        )

    # No structured geo / CRM / retargeting map can be reconstructed reliably from
    # ordinary media-plan rows. Therefore use the documented unstructured neutral path.
    out = merge_entities(lines, U, neutral_unstructured=True, model_path="L7_BRAND")
    out["name"] = next((x.get("brand") for x in lines if x.get("brand")), "Brand")
    diagnostics.append({
        "code": "BRAND_ADDRESSABILITY_UNSTRUCTURED",
        "message": "BrandAddressabilityMap не включена: структурные geo/CRM/pool inputs отсутствуют.",
    })
    return out


def discover(path: str) -> str:
    groups = discover_media_plan_groups(path)
    out = []
    for g in groups:
        plan = parse_media_plan(path, sheet_names=g.sheet_names)
        out.append({
            "id": g.id,
            "label": g.label,
            "sheet_names": list(g.sheet_names),
            "brand": g.brand,
            "line": g.line,
            "campaign": g.campaign,
            "universe": float(plan.universe) if plan.universe else None,
            "ta_name": next((f.ta_name for f in plan.flights if f.ta_name and not f.is_common), ""),
            "flight_count": len(plan.flights),
            "placement_count": len(plan.detail_rows()),
        })
    return _json({"version": VERSION, "plans": out})


def calculate(path: str, params_json: str = "{}") -> str:
    q = json.loads(params_json or "{}")
    selected_ids = [str(x) for x in (q.get("selected_plan_ids") or [])]
    overrides = q.get("universes") or {}
    K = _positive(q.get("K", K_DEFAULT), "K")
    if K < 1:
        raise V16Error("K должен быть >= 1.")

    groups = discover_media_plan_groups(path)
    if selected_ids:
        groups = [g for g in groups if g.id in selected_ids]
    if not groups:
        raise V16Error("Не выбрано ни одной Line.")

    diagnostics: List[dict] = [{
        "code": "ENGINE_VERSION",
        "version": VERSION,
        "l2_mode": "QUICK",
        "K": K,
    }]
    lines = []
    for g in groups:
        plan = parse_media_plan(path, sheet_names=g.sheet_names)
        U = _plan_universe(plan, overrides.get(g.id))
        line = calculate_line(plan, U, K, diagnostics)
        line["plan_id"] = g.id
        line["label"] = g.label
        lines.append(line)

    brand_U_raw = q.get("brand_universe")
    brand_U = _positive(brand_U_raw, "Brand Universe") if brand_U_raw not in (None, "") else max(x["universe"] for x in lines)
    for line in lines:
        if line["reach_1p"] > brand_U + 1e-6:
            raise V16Error(
                f"Brand Universe {brand_U:.0f} меньше Line Reach {line['reach_1p']:.0f}."
            )

    brand_error = None
    try:
        brand = _brand_merge(lines, brand_U, diagnostics)
        brand["universe"] = brand_U
    except V16Error as e:
        brand = None
        brand_error = str(e)
        diagnostics.append({"code": "BRAND_TOTAL_BLOCKED", "message": brand_error})

    # Compact hierarchy for the UI.
    hierarchy = []
    for line in lines:
        for f in line.get("flights", []):
            for c in f.get("channels", []):
                hierarchy.append({
                    "level": "Channel", "line": line["label"], "flight": f["name"],
                    "name": c["name"], "universe": line["universe"], **{
                        k: c.get(k) for k in ("impressions","reach_1p","reach_2p","reach_3p","reach_4p","reach_5p","reach_6p","avg_frequency")
                    }
                })
            hierarchy.append({
                "level": "Flight", "line": line["label"], "flight": f["name"],
                "name": f["name"], "universe": line["universe"], **{
                    k: f.get(k) for k in ("impressions","reach_1p","reach_2p","reach_3p","reach_4p","reach_5p","reach_6p","avg_frequency")
                }
            })
        hierarchy.append({
            "level": "Line", "line": line["label"], "flight": "",
            "name": line["label"], "universe": line["universe"], **{
                k: line.get(k) for k in ("impressions","reach_1p","reach_2p","reach_3p","reach_4p","reach_5p","reach_6p","avg_frequency")
            }
        })
    if brand is not None:
        hierarchy.append({
            "level": "Brand", "line": "", "flight": "", "name": brand.get("name") or "Brand",
            "universe": brand_U, **{
                k: brand.get(k) for k in ("impressions","reach_1p","reach_2p","reach_3p","reach_4p","reach_5p","reach_6p","avg_frequency")
            }
        })

    return _json({
        "version": VERSION,
        "status": "GO" if brand_error is None else "PARTIAL",
        "l2_mode": "QUICK",
        "K": K,
        "lines": lines,
        "brand_total": brand,
        "brand_error": brand_error,
        "hierarchy": hierarchy,
        "diagnostics": diagnostics,
    })
