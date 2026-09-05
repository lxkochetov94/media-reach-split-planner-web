from __future__ import annotations

import calendar
import datetime as dt
import difflib
import math
import json
import re
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from xlsx_reader import XlsxWorkbook, SheetData


# ------------------------ normalization ------------------------

def norm(v: Any) -> str:
    if v is None:
        return ""
    # This function is on the hottest parser path and can be called tens of thousands
    # of times per workbook. Keep it regex-free: the global ``re`` cache is shared with
    # many dynamic media-patterns and cache churn used to make sequential workbook
    # uploads progressively slower.
    s = str(v).strip().lower().replace("ё", "е")
    s = s.replace("_", " ").replace("–", "-").replace("—", "-").replace("−", "-")
    s = s.replace("\n", " ").replace("\r", " ")
    return " ".join(s.split())



# ------------------------ platform canonicalization ------------------------

# Canonical registry is deliberately product-safe: aliases are merged only when they
# describe the same advertising platform/product. Different products of one owner
# (e.g. Yandex Direct, RSYA, PromoPages, Dzen, Video) remain separate canonical names.
PLATFORM_CANONICAL_ALIASES: Dict[str, Tuple[str, ...]] = {
    "VK": ("VK", "ВК", "VKontakte", "ВКонтакте", "VK Video", "VK Видео", "ВК Видео"),
    "Telegram": ("Telegram", "Телеграм", "Telegram Ads", "TG", "ТГ"),
    "МТС": ("MTS", "МТС"),
    "Media Today": ("Media Today", "MediaToday", "Mediatoday"),
    "AstraLab": ("AstraLab", "Astra Lab"),
    "Yabbi": ("Yabbi", "YABBI"),
    "Otclick": ("Otclick",),
    "Mobidriven": ("Mobidriven",),
    "Beeline": ("Beeline", "Билайн"),
    "Avito": ("Avito", "Авито"),
    "First Data": ("First Data", "FirstData"),
    "SlickJump": ("SlickJump", "Slick Jump"),
    "Яндекс ПромоСтраницы": (
        "ПромоСтраницы", "Промо Страницы", "Яндекс ПромоСтраницы", "Яндекс Промо Страницы",
        "PromoPages", "Promo Pages", "Yandex PromoPages", "Yandex Promo Pages",
    ),
    "Дзен": ("Дзен", "Яндекс Дзен", "Dzen", "Yandex Dzen", "Zen", "Yandex Zen"),
    "Яндекс Директ": ("Yandex.Direct", "Yandex Direct", "Яндекс.Директ", "Яндекс Директ", "Yandex Search", "Яндекс Поиск"),
    "Яндекс РСЯ": ("Yandex.RSYA", "Yandex RSYA", "Яндекс.РСЯ", "Яндекс РСЯ", "РСЯ", "RSYA"),
    "Яндекс Видео": ("Яндекс Видео", "Yandex Video"),
    "Digital Alliance VideoNet": ("Digital Alliance VideoNet", "VideoNet", "DA VideoNet"),
    "Adspector": ("Adspector",),
    "Solta": ("Solta",),
    "Soloway": ("Soloway",),
    "Hybrid": ("Hybrid",),
    "Rutube": ("Rutube", "RuTube"),
    "Buzzoola": ("Buzzoola",),
    "GPM": ("GPM",),
    "RedLlama": ("RedLlama", "Red Llama"),
    "Adspend": ("Adspend",),
    "BYYD": ("BYYD",),
    "Mom.Life": ("Mom.Life", "Mom Life"),
    "Baby.ru": ("Baby.ru", "Baby ru"),
    "Babyblog.ru": ("Babyblog.ru", "Babyblog ru"),
    "Genius": ("Genius",),
    "Between Exchange": ("Between Exchange",),
    "ORM": ("ORM",),
    "SEO": ("SEO",),
    "Adriver": ("Adriver", "Ad River"),
}

_CYRILLIC_TO_LATIN = str.maketrans({
    "а":"a","б":"b","в":"v","г":"g","д":"d","е":"e","ё":"e","ж":"zh","з":"z","и":"i","й":"i",
    "к":"k","л":"l","м":"m","н":"n","о":"o","п":"p","р":"r","с":"s","т":"t","у":"u","ф":"f",
    "х":"kh","ц":"ts","ч":"ch","ш":"sh","щ":"shch","ы":"y","э":"e","ю":"yu","я":"ya","ь":"","ъ":"",
})


_RESEARCH_MARKER_RE = re.compile(r"(?i)(?<![a-zа-я0-9])(?:BLS|SL)(?![a-zа-я0-9])")
_BONUS_WORD_RE = re.compile(
    r"(?i)(?<![a-zа-я0-9])(?:bonus(?:\s+(?:volume|inventory))?|"
    r"бонус(?:ом|ный|ная|ное|ные)?(?:\s+(?:объем|объём|показ(?:ы|ов)?|инвентар(?:ь|я)))?)(?![a-zа-я0-9])"
)
_RESEARCH_PHRASE_RE = re.compile(
    r"(?i)(?<![a-zа-я0-9])(?:"
    r"(?:bonus|бонус(?:ом)?)\s*(?:BLS|SL)|"
    r"(?:BLS|SL)\s*(?:bonus|бонус(?:ом)?)"
    r")(?![a-zа-я0-9])"
)


def _strip_platform_decorations(value: Any) -> str:
    """Strip research/bonus decorations without changing the media owner identity."""
    s = "" if value is None else str(value).strip()
    if not s:
        return ""
    s = _RESEARCH_PHRASE_RE.sub(" ", s)
    s = _RESEARCH_BONUS_ANY_RE.sub(" ", s)
    s = _RESEARCH_EXTRA_STRIP_RE.sub(" ", s)
    s = _RESEARCH_MARKER_RE.sub(" ", s)
    s = _BONUS_WORD_RE.sub(" ", s)
    s = re.sub(r"\s*\((?:конструктор аудитории|кастомный сегмент|общая ца|тестовая ца)\)\s*$", "", s, flags=re.I)
    s = re.sub(r"[\s\-–—,:;|/]+", " ", s).strip()
    return s


_RESEARCH_EXTRA_PATTERNS = (
    ("BLS", re.compile(r"(?i)(?<![a-zа-я0-9])brand[\s-]*lift(?:[\s-]*study)?(?![a-zа-я0-9])")),
    ("Sales Lift", re.compile(r"(?i)(?<![a-zа-я0-9])sales[\s-]*lift(?![a-zа-я0-9])")),
    ("Search Lift", re.compile(r"(?i)(?<![a-zа-я0-9])search[\s-]*lift(?![a-zа-я0-9])")),
    ("Ad Recall Lift", re.compile(r"(?i)(?<![a-zа-я0-9])ad[\s-]*recall[\s-]*lift(?![a-zа-я0-9])")),
)
_RESEARCH_GENERIC_EXACT_RE = re.compile(r"(?i)^\s*(?:research|research study|исследовани\w*)\s*$")
_RESEARCH_BONUS_ANY_RE = re.compile(
    r"(?i)(?:bonus|бонус(?:ом|ный|ная|ное|ные)?)\s*(?:research|исследовани\w*)?\s*"
    r"(?:BLS|SL|brand[\s-]*lift(?:[\s-]*study)?|sales[\s-]*lift|search[\s-]*lift|ad[\s-]*recall[\s-]*lift)"
    r"|(?:BLS|SL|brand[\s-]*lift(?:[\s-]*study)?|sales[\s-]*lift|search[\s-]*lift|ad[\s-]*recall[\s-]*lift)"
    r"\s*(?:research|исследовани\w*)?\s*(?:bonus|бонус(?:ом|ный|ная|ное|ные)?)"
)
_RESEARCH_EXTRA_STRIP_RE = re.compile(
    r"(?i)(?<![a-zа-я0-9])(?:brand[\s-]*lift(?:[\s-]*study)?|sales[\s-]*lift|search[\s-]*lift|ad[\s-]*recall[\s-]*lift)(?![a-zа-я0-9])"
)


def _detect_research_types(platform: Any = "", fmt: Any = "", raw: Any = "") -> str:
    values = [str(platform or ""), str(fmt or "")]
    raw_text = str(raw or "")
    found: List[str] = []

    def add(v: str) -> None:
        if v and v not in found:
            found.append(v)

    for text in values + [raw_text]:
        if _RESEARCH_MARKER_RE.search(text):
            for m in _RESEARCH_MARKER_RE.finditer(text):
                add(m.group(0).upper())
        for label, rx in _RESEARCH_EXTRA_PATTERNS:
            if rx.search(text):
                add(label)

    # Generic Research/Исследование is allowed only when it is itself a platform/format
    # field, never from a long targeting/comment row (e.g. Tiburon Research data source).
    if not found and any(_RESEARCH_GENERIC_EXACT_RE.match(x) for x in values):
        add("Исследование")
    return "/".join(found)


def _research_field_is_dedicated(value: Any) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    if _RESEARCH_GENERIC_EXACT_RE.match(text):
        return True
    marker = _detect_research_types(text, "", "")
    if not marker:
        return False
    cleaned = _RESEARCH_EXTRA_STRIP_RE.sub(" ", text)
    cleaned = _RESEARCH_MARKER_RE.sub(" ", cleaned)
    cleaned = _BONUS_WORD_RE.sub(" ", cleaned)
    cleaned = re.sub(r"[\s\-–—,:;|/()]+", " ", cleaned).strip()
    return not cleaned


def research_details(
    platform: Any = "", fmt: Any = "", raw: Any = "", budget: Optional[float] = None,
) -> Tuple[str, str, Optional[float], bool]:
    """Return type, payment status, separately allocated cost, dedicated-row flag."""
    marker = _detect_research_types(platform, fmt, raw)
    if not marker:
        return "", "", None, False
    text = " | ".join(str(x or "") for x in (platform, fmt, raw))
    dedicated = _research_field_is_dedicated(platform) or _research_field_is_dedicated(fmt)
    if _RESEARCH_BONUS_ANY_RE.search(text):
        return marker, "BONUS", 0.0, dedicated
    if dedicated and budget is not None and abs(float(budget)) > 1e-9:
        return marker, "PAID", float(budget), True
    return marker, "COST_NOT_SEPARATED", None, dedicated


def placement_markers(platform: Any = "", fmt: Any = "", raw: Any = "") -> Tuple[bool, str]:
    """Return free-media bonus flag and research type; research bonus is separate."""
    text = " | ".join(str(x or "") for x in (platform, fmt, raw))
    marker = _detect_research_types(platform, fmt, raw)
    without_research_bonus = _RESEARCH_BONUS_ANY_RE.sub(" ", text)
    is_bonus = bool(_BONUS_WORD_RE.search(without_research_bonus))
    return is_bonus, marker


def _clean_platform_display(value: Any) -> str:
    """Remove non-identity decorations while preserving a human-readable source name."""
    raw = "" if value is None else str(value).strip()
    if not raw:
        return ""
    first_line = raw.split("\n", 1)[0].strip()
    return _strip_platform_decorations(first_line)


def _platform_signature(value: Any) -> str:
    """Script-independent compact signature; mixed Cyrillic/Latin becomes comparable."""
    s = _clean_platform_display(value).lower().replace("ё", "е")
    s = s.translate(_CYRILLIC_TO_LATIN)
    return re.sub(r"[^a-z0-9]+", "", s)


def _limited_edit_distance(a: str, b: str, limit: int = 2) -> int:
    if abs(len(a) - len(b)) > limit:
        return limit + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        row_min = i
        for j, cb in enumerate(b, 1):
            v = min(cur[-1] + 1, prev[j] + 1, prev[j - 1] + (ca != cb))
            cur.append(v)
            row_min = min(row_min, v)
        if row_min > limit:
            return limit + 1
        prev = cur
    return prev[-1]


def _platform_alias_index() -> List[Tuple[str, str, str]]:
    out: List[Tuple[str, str, str]] = []
    for canonical, aliases in PLATFORM_CANONICAL_ALIASES.items():
        for alias in aliases:
            signature = _platform_signature(alias)
            if signature:
                out.append((signature, canonical, alias))
    return out


_PLATFORM_ALIAS_INDEX = _platform_alias_index()


def canonicalize_platform_name(value: Any) -> Tuple[str, str, float]:
    """Return canonical name, match reason and confidence.

    Order: exact normalized/transliterated alias -> conservative typo match -> cleaned
    source value. Short brand names (VK/MTS/GPM etc.) are never fuzzy-matched.
    """
    cleaned = _clean_platform_display(value)
    signature = _platform_signature(cleaned)
    if not signature:
        return "", "empty", 0.0

    exact = [(canonical, alias) for sig, canonical, alias in _PLATFORM_ALIAS_INDEX if sig == signature]
    if exact:
        return exact[0][0], f"alias: {exact[0][1]}", 1.0

    # Human typo fallback. Require a reasonably long name, small edit distance and an
    # unambiguous best candidate. This prevents aggressive merges of different platforms.
    if len(signature) >= 5:
        candidates: List[Tuple[float, int, str, str]] = []
        for alias_sig, canonical, alias in _PLATFORM_ALIAS_INDEX:
            if len(alias_sig) < 5:
                continue
            max_dist = 1 if max(len(signature), len(alias_sig)) < 9 else 2
            dist = _limited_edit_distance(signature, alias_sig, max_dist)
            if dist > max_dist:
                continue
            ratio = difflib.SequenceMatcher(None, signature, alias_sig).ratio()
            if ratio >= 0.88:
                candidates.append((ratio, -dist, canonical, alias))
        candidates.sort(reverse=True)
        if candidates:
            best = candidates[0]
            # Multiple aliases of the same canonical platform are not ambiguity.
            competing = [x for x in candidates[1:] if x[2] != best[2]]
            if not competing or best[0] - competing[0][0] >= 0.03:
                return best[2], f"fuzzy alias: {best[3]}", round(best[0], 4)

    return cleaned, "unrecognized; preserved source name", 0.5


def _suggest_known_platform(value: Any) -> str:
    """Suggest, but never auto-merge, a plausible known platform for an unknown name."""
    signature = _platform_signature(value)
    if len(signature) < 5:
        return ""
    candidates: List[Tuple[float, str]] = []
    for alias_sig, canonical, _alias in _PLATFORM_ALIAS_INDEX:
        if len(alias_sig) < 5:
            continue
        ratio = difflib.SequenceMatcher(None, signature, alias_sig).ratio()
        if ratio >= 0.80:
            candidates.append((ratio, canonical))
    if not candidates:
        return ""
    candidates.sort(reverse=True)
    best_ratio, best_name = candidates[0]
    competing = [x for x in candidates[1:] if x[1] != best_name]
    if competing and best_ratio - competing[0][0] < 0.04:
        return ""
    return best_name


def platform_identity_state(
    source: Any,
    canonical: str,
    reason: str,
    confidence: float,
) -> Tuple[str, bool, str]:
    """Return status, review flag and a non-binding canonical suggestion."""
    if not canonical:
        return "EMPTY_PLATFORM", False, ""
    if reason.startswith("alias:"):
        return "KNOWN_PLATFORM", False, canonical
    if reason.startswith("fuzzy alias:"):
        return "KNOWN_PLATFORM_FUZZY", True, canonical
    return "NEW_PLATFORM", True, _suggest_known_platform(source)


def harmonize_unknown_platform_variants(rows: Sequence[Any]) -> None:
    """Safely cluster repeated unknown spellings inside one loaded media plan.

    Known registry aliases are already canonicalized row-by-row. For genuinely new
    platforms, variants are merged only when the workbook itself contains a very close,
    unambiguous spelling. A single unknown name is preserved as-is.
    """
    unknown: Dict[str, List[Any]] = defaultdict(list)
    for row in rows:
        if not getattr(row, "platform", ""):
            continue
        if getattr(row, "platform_match_confidence", 0.0) >= 0.88:
            continue
        sig = _platform_signature(getattr(row, "platform", ""))
        if sig:
            unknown[sig].append(row)
    if len(unknown) < 2:
        return

    reps = sorted(
        unknown.items(),
        key=lambda kv: (-len(kv[1]), -len(kv[0]), kv[0]),
    )
    clusters: List[Tuple[str, str, List[Any]]] = []
    for sig, members in reps:
        display = Counter(_clean_platform_display(x.platform) for x in members).most_common(1)[0][0]
        best_idx: Optional[int] = None
        best_ratio = 0.0
        for idx, (base_sig, _base_display, _base_members) in enumerate(clusters):
            if len(sig) < 5 or len(base_sig) < 5:
                continue
            max_dist = 1 if max(len(sig), len(base_sig)) < 9 else 2
            dist = _limited_edit_distance(sig, base_sig, max_dist)
            if dist > max_dist:
                continue
            ratio = difflib.SequenceMatcher(None, sig, base_sig).ratio()
            if ratio >= 0.93 and ratio > best_ratio:
                best_idx, best_ratio = idx, ratio
        if best_idx is None:
            clusters.append((sig, display, list(members)))
        else:
            base_sig, base_display, base_members = clusters[best_idx]
            base_members.extend(members)
            clusters[best_idx] = (base_sig, base_display, base_members)
            for x in members:
                x.platform_canonical = base_display
                x.platform_match_reason = "workbook fuzzy variant"
                x.platform_match_confidence = round(best_ratio, 4)
                x.platform_status = "NEW_PLATFORM"
                x.platform_needs_review = True
                x.platform_suggested_canonical = base_display


def to_number(v: Any) -> Optional[float]:
    if v is None or v == "":
        return None
    if isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        try:
            f = float(v)
            if math.isnan(f):
                return None
            return f
        except Exception:
            return None
    s = str(v).strip().lower().replace("\xa0", "").replace(" ", "")
    if not s:
        return None
    mult = 1.0
    if "млрд" in s or "billion" in s or re.search(r"\bbn\b", s):
        mult = 1_000_000_000.0
    elif "млн" in s or "million" in s:
        mult = 1_000_000.0
    elif "тыс" in s or "thousand" in s:
        mult = 1_000.0
    s = re.sub(r"[^0-9,\.\-]", "", s)
    if not s:
        return None
    # Russian decimal comma; English thousands comma.
    if "," in s and "." not in s:
        if s.count(",") == 1 and len(s.split(",")[-1]) <= 3:
            s = s.replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s and "." in s:
        s = s.replace(",", "")
    try:
        return float(s) * mult
    except Exception:
        return None


def is_numeric(v: Any) -> bool:
    return to_number(v) is not None


def clean_display(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (dt.date, dt.datetime)):
        return v.strftime("%d.%m.%Y")
    return str(v).strip()


# ------------------------ dates ------------------------

MONTH_WORDS = {
    1: ["янв", "январ", "jan", "january"],
    2: ["фев", "феврал", "feb", "february"],
    3: ["мар", "март", "mar", "march"],
    4: ["апр", "апрел", "apr", "april"],
    5: ["май", "мая", "may"],
    6: ["июн", "июнь", "июня", "jun", "june"],
    7: ["июл", "июль", "июля", "jul", "july"],
    8: ["авг", "август", "aug", "august"],
    9: ["сен", "сент", "сентябр", "sep", "sept", "september"],
    10: ["окт", "октябр", "oct", "october"],
    11: ["ноя", "ноябр", "nov", "november"],
    12: ["дек", "декабр", "dec", "december"],
}


def _parse_single_date(v: Any, default_year: int = 2026) -> Optional[dt.date]:
    if v is None:
        return None
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    # Excel serial date (Windows 1900 date system).
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        try:
            f = float(v)
            if 1000 <= f <= 100000:
                return dt.date(1899, 12, 30) + dt.timedelta(days=int(f))
        except Exception:
            pass
    s = str(v).strip()
    if not s:
        return None
    # dd.mm.yyyy / dd-mm-yyyy / dd/mm/yyyy; year can be omitted
    m = re.fullmatch(r"\s*(\d{1,2})[./-](\d{1,2})(?:[./-](\d{2,4}))?\s*", s)
    if m:
        d, mo = int(m.group(1)), int(m.group(2))
        y = int(m.group(3)) if m.group(3) else default_year
        if y < 100:
            y += 2000
        try:
            return dt.date(y, mo, d)
        except ValueError:
            return None
    return None


def parse_period(v: Any, default_year: int = 2026) -> Tuple[Optional[dt.date], Optional[dt.date]]:
    if v is None:
        return None, None
    if isinstance(v, (dt.date, dt.datetime)):
        d = v.date() if isinstance(v, dt.datetime) else v
        return d, d
    s = str(v).strip().lower().replace("ё", "е")
    if not s:
        return None, None

    # two explicit dates
    pats = re.findall(r"\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?", s)
    ds = [_parse_single_date(x, default_year) for x in pats[:2]]
    ds = [x for x in ds if x is not None]
    if len(ds) == 1:
        return ds[0], ds[0]
    if len(ds) >= 2:
        return min(ds[0], ds[1]), max(ds[0], ds[1])

    # month names and optional year
    months: List[int] = []
    for m, variants in MONTH_WORDS.items():
        if any(vv in s for vv in variants):
            months.append(m)
    months = sorted(set(months))
    ym = re.search(r"(20\d{2})", s)
    y = int(ym.group(1)) if ym else default_year
    if months:
        sm, em = months[0], months[-1]
        return dt.date(y, sm, 1), dt.date(y, em, calendar.monthrange(y, em)[1])
    return None, None


def parse_period_intervals(v: Any, default_year: int = 2026) -> List[Tuple[dt.date, dt.date]]:
    """Parse one or several campaign intervals, preserving gaps such as Mar-May + Jul."""
    if v is None:
        return []
    if isinstance(v, (dt.date, dt.datetime)):
        d = v.date() if isinstance(v, dt.datetime) else v
        return [(d, d)]
    raw = str(v).strip()
    if not raw:
        return []
    text = raw.lower().replace("ё", "е")
    text = re.sub(r"[–—−]", "-", text)
    year_match = re.search(r"(20\d{2})", text)
    default_y = int(year_match.group(1)) if year_match else default_year

    # Explicit date ranges can be separated by +, ; or commas.
    explicit = re.findall(
        r"(\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?)\s*(?:-|по|до)\s*(\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?)",
        text,
    )
    if explicit:
        out: List[Tuple[dt.date, dt.date]] = []
        for a, b in explicit:
            da, db = _parse_single_date(a, default_y), _parse_single_date(b, default_y)
            if da and db:
                out.append((min(da, db), max(da, db)))
        if out:
            return _merge_date_intervals(out)

    # Work segment-by-segment so a gap expressed with '+' is not collapsed.
    cleaned = re.sub(r"\([^)]*\)", " ", text)
    segments = [x.strip() for x in re.split(r"\s*\+\s*|;", cleaned) if x.strip()]
    out: List[Tuple[dt.date, dt.date]] = []
    for seg in segments:
        ym = re.search(r"(20\d{2})", seg)
        y = int(ym.group(1)) if ym else default_y
        month_hits: List[Tuple[int, int]] = []
        for month, variants in MONTH_WORDS.items():
            pos = None
            for vv in variants:
                mm = re.search(rf"(?<![a-zа-я]){re.escape(vv)}[a-zа-я]*", seg)
                if mm and (pos is None or mm.start() < pos):
                    pos = mm.start()
            if pos is not None:
                month_hits.append((pos, month))
        month_hits.sort()
        months = [m for _, m in month_hits]
        if not months:
            continue
        if len(months) >= 2 and re.search(r"-|\bпо\b|\bдо\b", seg):
            sm, em = months[0], months[-1]
            if em < sm:
                # Cross-year ranges are rare in annual media plans; keep explicit chronology.
                out.append((dt.date(y, sm, 1), dt.date(y + 1, em, calendar.monthrange(y + 1, em)[1])))
            else:
                out.append((dt.date(y, sm, 1), dt.date(y, em, calendar.monthrange(y, em)[1])))
        else:
            for m in months:
                out.append((dt.date(y, m, 1), dt.date(y, m, calendar.monthrange(y, m)[1])))
    if out:
        return _merge_date_intervals(out)
    ps, pe = parse_period(v, default_year)
    return [(ps, pe or ps)] if ps else []


def _merge_date_intervals(intervals: Sequence[Tuple[dt.date, dt.date]]) -> List[Tuple[dt.date, dt.date]]:
    clean = sorted((min(a, b), max(a, b)) for a, b in intervals if a and b)
    if not clean:
        return []
    out = [clean[0]]
    for a, b in clean[1:]:
        pa, pb = out[-1]
        if a <= pb + dt.timedelta(days=1):
            out[-1] = (pa, max(pb, b))
        else:
            out.append((a, b))
    return out


def _flight_number_from_text(value: Any) -> Optional[int]:
    t = norm(value)
    if not t:
        return None
    for pat in (
        r"(?:период\s*)?(?:flight|флайт|wave|волна)\s*[-_ ]*(\d+)",
        r"(?:^|\b)f\s*[-_ ]?(\d+)(?:\b|$)",
    ):
        m = re.search(pat, t, re.IGNORECASE)
        if m:
            return int(m.group(1))
    return None


def _is_common_section(value: Any) -> bool:
    t = norm(value).rstrip(":;")
    return t in {"общее", "общий блок", "always on", "always-on", "aon"} or bool(re.search(r"\b(always[- ]?on|aon)\b", t))


# ------------------------ channels ------------------------


def _is_social_special_project_text(*values: Any) -> bool:
    """High-priority detector for blogger/influencer placements and social seeding."""
    t = " | ".join(norm(v) for v in values if v not in (None, ""))
    if not t:
        return False

    if re.search(r"\bпосев\w*|\bsocial\s+seeding\b|\bseeding\b|\bseeded\s+placement\b", t, re.IGNORECASE):
        return True

    creator = bool(re.search(
        r"\bблогер\w*|\bинфлюенс\w*|\bbloggers?\b|\binfluencers?\b|"
        r"\bkol\b|key\s+opinion\s+leaders?|\bлидер\w*\s+мнен\w*|"
        r"content\s+creators?|\bcreators?\b|контент[- ]?креатор\w*",
        t, re.IGNORECASE,
    ))
    if not creator:
        return False

    if re.search(
        r"интеграц|размещ|публикац|натив|обзор|пост|ролик|реклам|"
        r"integration|placement|collab|sponsor|native\s+post|branded\s+content",
        t, re.IGNORECASE,
    ):
        return True

    if len(t) <= 90 and not re.search(
        r"таргет|target(?:ing)?|интерес|interests?|аудитор|audience|сегмент",
        t, re.IGNORECASE,
    ):
        return True

    return False


CHANNEL_PATTERNS: List[Tuple[str, List[str]]] = [
    # Explicit products which must stay as standalone flowchart rows.
    ("Статьи", [
        # Content products are only candidates here. Row-level routing below refines
        # them by buying model: CPR -> Articles, CPM -> Banners/OLV.
        r"промостраниц", r"promo\s*pages?", r"promopages?", r"promo[-_ ]?page",
        r"\bдзен\b", r"\bdzen\b", r"\bzen\b", r"яндекс[^|]{0,20}дзен", r"yandex[^|]{0,20}zen"
    ]),
    ("ORM", [r"\borm\b", r"online reputation", r"репутац.*менедж"]),
    ("OLV", [
        r"\bolv\b", r"\bолв\b", r"online video", r"digital video", r"video ads?", r"\bvideo\b",
        r"онлайн[- ]?видео", r"pre[- ]?roll", r"preroll", r"mid[- ]?roll", r"instream", r"in[- ]?stream"
    ]),
    ("Banners", [
        r"\bbanners?\b", r"\bбаннер", r"\bdisplay\b", r"display ads?", r"rich media",
        r"медийн.*баннер", r"баннерн.*реклам", r"мобильн.*реклам", r"playable ads?",
        r"fullscreen", r"interstitial", r"интерактивн.*формат", r"тематическ.*сайт"
    ]),
    ("Social Nets", [
        r"social nets?", r"social media", r"\bsocial\b", r"соцсет", r"социальн.*сет",
        r"\bvk ads\b", r"\bvk\b", r"\bвк\b", r"vkontakte", r"telegram ads", r"\btg\b", r"\bтг\b"
    ]),
    ("Native", [r"\bnative\b", r"натив", r"спецпроект", r"special project", r"прочтени", r"дочитыв", r"стать"]),
    ("Perfomance", [
        r"\bsearch\b", r"context", r"контекст", r"директ", r"direct", r"\bsem\b", r"поиск",
        r"performance", r"перформанс", r"перфоманс", r"conversion", r"конверсион", r"рся", r"rsya", r"rsya"
    ]),
    ("E-com", [r"e[- ]?com", r"ecommerce", r"marketplace", r"маркетплейс", r"\bozon\b", r"wildberries", r"яндекс.?маркет", r"yandex.?market"]),
    ("Programmatic", [r"programmatic", r"программатик", r"\bdsp\b", r"getintent", r"segmento", r"adspector", r"hybrid", r"response"]),
    ("Services", [r"\bуслуги\b", r"\bverification\b", r"верификац", r"трекинг траф"]),
]


def infer_channel(text: Any) -> Optional[str]:
    t = norm(text)
    if not t:
        return None
    # Blogger/influencer placements and social seeding belong to the native/special-project
    # flowchart row even when the same text also contains VK / TG / other social platforms.
    if _is_social_special_project_text(t):
        return "Native"
    for channel, patterns in CHANNEL_PATTERNS:
        for p in patterns:
            if re.search(p, t, re.IGNORECASE):
                return channel
    return None


def infer_channel_from_values(values: Sequence[Any]) -> Optional[str]:
    return infer_channel(" | ".join(clean_display(v) for v in values if v not in (None, "")))


PLACEMENT_CLASSES: Tuple[str, ...] = (
    "OLV", "Баннеры", "Social", "Спецпроекты", "Блогеры", "Посевы",
    "SEO", "ORM", "Perfomance", "Поиск", "РСЯ", "Статьи", "Native",
)


def classify_placement(
    platform: str = "",
    fmt: str = "",
    raw: str = "",
    model: str = "OTHER",
    legacy_channel: Optional[str] = None,
    section_class: Optional[str] = None,
) -> Tuple[Optional[str], str]:
    """Classify one row into the Stage-3 placement taxonomy.

    Row-level product/format evidence outranks an enclosing section label. The result
    is separate from Placement.channel so current reach/split/flow calculations remain
    unchanged in Stage 3.
    """
    platform_n = norm(platform)
    fmt_n = norm(fmt)
    raw_n = norm(raw)
    text = " | ".join(x for x in (platform_n, fmt_n, raw_n) if x)
    row_text = " | ".join(x for x in (platform_n, fmt_n) if x)
    legacy = norm(legacy_channel)
    section = section_class if section_class in PLACEMENT_CLASSES else None
    model_u = (model or "OTHER").upper()

    # LAB hard rule: Mom.Life is a banner placement. Platform identity
    # outranks generic blogger/integration wording in the row description.
    if platform_n == "mom.life":
        return "Баннеры", "hard platform rule: Mom.Life → Баннеры"

    # Stage 4 hard platform rules. SlickJump, Avito and Baby.ru are never
    # routed to Native/Special Projects. They can only be display or OLV.
    # Buying model still controls KPI independently (e.g. CPC Avito = Banners + clicks).
    if platform_n in {"slickjump", "avito", "baby.ru"}:
        video_hint = bool(re.search(
            r"\bvideo\b|\bolv\b|онлайн[- ]?видео|видеореклам|видео|pre[- ]?roll|preroll|"
            r"mid[- ]?roll|multi[- ]?roll|instream|in[- ]?stream|out[- ]?stream|outstream|"
            r"ролик|досмотр|in-read video|video ad",
            fmt_n, re.I,
        ))
        if model_u in {"CPV", "CPCV"} or video_hint:
            return "OLV", f"hard platform rule: {platform or platform_n} video → OLV"
        return "Баннеры", f"hard platform rule: {platform or platform_n} non-video → Баннеры"

    # PromoPages / Yandex Zen are content products, but their actual ad format and
    # buying model can turn a row into ordinary display or video inventory. Keep the
    # placement class separate from KPI logic: e.g. CPC PromoPages remains Articles
    # with clicks as KPI, while CPCV video remains OLV with completed views as KPI.
    content_product = bool(re.search(
        r"промостраниц|promo\s*pages?|promopages?|promo[-_ ]?page|"
        r"\bдзен\b|\bdzen\b|\bzen\b|яндекс[^|]{0,20}дзен|yandex[^|]{0,20}zen",
        text, re.I,
    ))
    if content_product:
        video_hint = bool(re.search(
            r"\bvideo\b|\bolv\b|онлайн[- ]?видео|видеореклам|видео|pre[- ]?roll|preroll|"
            r"mid[- ]?roll|multi[- ]?roll|instream|in[- ]?stream|outstream|ролик|досмотр",
            fmt_n, re.I,
        ))
        banner_hint = bool(re.search(
            r"\bbanners?\b|баннер|\bdisplay\b|rich[- ]?media|fullscreen|interstitial|"
            r"медийн|статик|креатив",
            fmt_n, re.I,
        ))
        if model_u == "CPR":
            return "Статьи", "PromoPages/Zen CPR article buying model"
        if model_u in {"CPV", "CPCV"}:
            return "OLV", "PromoPages/Zen video buying model"
        if model_u == "CPM":
            if video_hint:
                return "OLV", "PromoPages/Zen CPM video format"
            if banner_hint:
                return "Баннеры", "PromoPages/Zen CPM banner/display format"
            if section in {"OLV", "Баннеры"}:
                return section, "PromoPages/Zen CPM section format"
            return "Баннеры", "PromoPages/Zen CPM without video signal"
        if video_hint:
            return "OLV", "PromoPages/Zen explicit video format"
        if banner_hint:
            return "Баннеры", "PromoPages/Zen explicit banner/display format"
        return "Статьи", "PromoPages/Zen content product"

    # ORM precedes seeding because an ORM estimate can contain seeding as a sub-service.
    if platform_n == "orm" or legacy == "orm" or re.search(
        r"(^|[|\s])orm([|\s]|$)|online reputation|репутац.*менедж|orm[- ]?поддерж", text, re.I
    ):
        return "ORM", "explicit ORM product/section"

    if platform_n == "seo" or legacy == "seo" or re.search(
        r"(^|[|\s])seo([|\s]|$)|seo[- ]?оптимизац|search engine optimization", text, re.I
    ):
        return "SEO", "explicit SEO product/section"

    # Technical/service rows must not inherit a media section.
    if legacy in {"services", "service"} or platform_n in {"adriver", "ad river", "pixel", "пиксель tns", "tns"} or re.search(
        r"verification|верификац|adserving fee|tracking fee|трекинг траф|пиксел\w* tns",
        row_text, re.I,
    ):
        return None, "technical/service row outside placement taxonomy"

    if re.search(
        r"\bблогер\w*|\bинфлюенс\w*|\binfluencers?\b|\bbloggers?\b|"
        r"\bkol\b|key opinion leaders?|лидер\w* мнен\w*|content[- ]?creators?",
        text, re.I,
    ):
        return "Спецпроекты", "hard rule: blogger/influencer → Спецпроекты"

    if re.search(r"\bпосев\w*|social seeding|\bseeding\b|seeded placement", text, re.I):
        return "Спецпроекты", "hard rule: seeding → Спецпроекты"

    if re.search(r"спецпроект|special project|спецразмещ|спонсорств|sponsorship|sponsored project", text, re.I):
        return "Спецпроекты", "explicit special-project/sponsorship placement"

    if re.search(
        r"yandex[. _-]*rsya|яндекс[. _-]*рся|\bрся\b|\brsya\b|рекламн\w* сет\w* яндекс",
        text, re.I,
    ):
        return "РСЯ", "explicit Yandex RSYA placement"

    if re.search(
        r"yandex[. _-]*direct|яндекс[. _-]*директ|яндекс[. _-]*поиск|yandex search|search ads?|поисков\w* реклам",
        row_text, re.I,
    ):
        return "Поиск", "explicit paid-search placement"

    if re.search(
        r"\bolv\b|online[- ]?video|digital[- ]?video|pre[- ]?roll|preroll|mid[- ]?roll|"
        r"multi[- ]?roll|in[- ]?stream|instream|out[- ]?stream|outstream|true view|video placement|"
        r"видеореклам|онлайн[- ]?видео|видеоролик|досмотр|vk video|vk видео|вк видео|яндекс видео|videonet",
        row_text, re.I,
    ):
        return "OLV", "explicit online-video format"

    if platform_n.startswith("slickjump") or re.search(
        r"\bnative\b|нативн\w* (?:реклам|формат|размещ)|нативная реклама|slickjump|"
        r"текстово[- ]?графическ\w* модул\w* slickjump",
        text, re.I,
    ):
        return "Native", "explicit native/content placement"

    if re.search(
        r"\bbanners?\b|баннер|\bdisplay\b|rich[- ]?media|fullscreen|interstitial|"
        r"playable ads?|брендировани\w*|перетяжк|небоскреб|floorad|interscroller|attention smart|whitebanner",
        row_text, re.I,
    ):
        return "Баннеры", "explicit display/banner format"

    if re.search(
        r"telegram ads|vk ads|vkontakte|(^|[|\s])vk([|\s]|$)|(^|[|\s])вк([|\s]|$)|"
        r"универсальн\w* объявлен|promo post|промо[- ]?пост|carousel|карусел",
        row_text, re.I,
    ):
        return "Social", "paid social placement"

    if model_u in {"CPA", "CPL", "CPO", "CPI", "CPS", "CPE"} or re.search(
        r"(^|[|\s])performance([|\s]|$)|перформанс|перфоманс|conversion|конверсион",
        row_text, re.I,
    ):
        return "Perfomance", "generic performance placement"

    if section:
        return section, "section fallback"

    fallback = {
        "olv": "OLV", "banners": "Баннеры", "social nets": "Social", "social": "Social",
        "native": "Native", "статьи": "Статьи", "orm": "ORM",
        "perfomance": "Perfomance", "performance": "Perfomance", "search / context": "Perfomance",
        "e-com": "Perfomance",
    }.get(legacy)
    if fallback:
        return fallback, "legacy channel fallback"
    return None, "unclassified placement"


def infer_placement_section(text: Any, legacy_channel: Optional[str] = None) -> Optional[str]:
    """Resolve a pure section/header label to the Stage-3 taxonomy."""
    t = norm(text).rstrip(":;-")
    exact = {
        "olv": "OLV", "online video": "OLV", "баннеры": "Баннеры", "banners": "Баннеры",
        "social": "Social", "social nets": "Social", "соцсети": "Social", "социальные сети": "Social",
        "спецпроекты": "Спецпроекты", "спецпроект": "Спецпроекты", "special projects": "Спецпроекты",
        "блогеры": "Блогеры", "блогер": "Блогеры", "influencers": "Блогеры",
        "посевы": "Посевы", "посев": "Посевы", "seeding": "Посевы",
        "seo": "SEO", "orm": "ORM", "performance": "Perfomance", "perfomance": "Perfomance",
        "перформанс": "Perfomance", "перфоманс": "Perfomance", "поиск": "Поиск", "search": "Поиск",
        "рся": "РСЯ", "rsya": "РСЯ", "нативная реклама": "Native", "native": "Native",
        "native ads": "Native", "натив": "Native", "статьи": "Статьи", "статья": "Статьи",
    }
    if t in exact:
        return exact[t]
    cls, _ = classify_placement(raw=t, legacy_channel=legacy_channel)
    return cls


def _special_row_channel(
    platform: str,
    fmt: str,
    raw: str,
    model: str = "OTHER",
    current_channel: Optional[str] = None,
    row_channel: Optional[str] = None,
) -> Optional[str]:
    """Resolve products that can belong to different flowchart channels.

    Rules agreed for PromoPages / Yandex Zen:
    - CPR -> ``Статьи``. PromoPages and Zen therefore aggregate in one row.
    - CPM -> ``OLV`` for explicit video formats, otherwise ``Banners``.
    - CPV/CPCV -> ``OLV``.
    ORM always remains a standalone row, including Always-on blocks.
    """
    text = " | ".join(x for x in (platform, fmt, raw) if x)
    t = norm(text)

    if _is_social_special_project_text(text):
        return "Native"

    if re.search(r"\borm\b|online reputation|репутац.*менедж", t, re.IGNORECASE):
        return "ORM"

    content_product = bool(re.search(
        r"промостраниц|promo\s*pages?|promopages?|promo[-_ ]?page|"
        r"\bдзен\b|\bdzen\b|\bzen\b|яндекс[^|]{0,20}дзен|yandex[^|]{0,20}zen",
        t, re.IGNORECASE
    )) or current_channel == "Статьи" or row_channel == "Статьи"

    if not content_product:
        return None

    model = (model or "OTHER").upper()
    if model == "CPR":
        return "Статьи"
    if model in {"CPV", "CPCV"}:
        return "OLV"

    # Creative format is authoritative inside CPM content-product rows.
    # Do not use the platform name itself here because PromoPages/Zen are product
    # names, not evidence that the creative is an article.
    creative = norm(" | ".join(x for x in (fmt, raw) if x))
    video_hint = bool(re.search(
        r"\bvideo\b|\bolv\b|онлайн[- ]?видео|видеореклам|видео|pre[- ]?roll|preroll|"
        r"mid[- ]?roll|instream|in[- ]?stream|ролик|досмотр",
        creative, re.IGNORECASE
    ))
    banner_hint = bool(re.search(
        r"\bbanners?\b|баннер|\bdisplay\b|rich media|fullscreen|interstitial|"
        r"медийн|статик|креатив",
        creative, re.IGNORECASE
    ))

    if model == "CPM":
        if video_hint:
            return "OLV"
        if banner_hint:
            return "Banners"
        # If the enclosing section already tells us it is video/banner, preserve it.
        if current_channel in {"OLV", "Banners"}:
            return current_channel
        if row_channel in {"OLV", "Banners"}:
            return row_channel
        # CPM without a video signal is treated as display/banner inventory.
        return "Banners"

    # For templates where the buying model is absent, retain explicit creative clues.
    if video_hint:
        return "OLV"
    if banner_hint:
        return "Banners"

    # Legacy/fallback behavior: an otherwise unclassified PromoPages/Zen row is content.
    return "Статьи"


# ------------------------ columns / KPI ------------------------

COLUMN_SYNONYMS: Dict[str, List[str]] = {
    "platform": ["site", "platform", "publisher", "seller", "resource", "площадка", "ресурс", "сайт"],
    "format": ["format", "placement", "placement format", "ad format", "формат", "размещение", "хронометраж"],
    "buying_model": ["buying model", "buy type", "buy model", "pricing model", "purchase model", "модель закупки", "тип закупки", "модель оплаты"],
    "unit_type": ["unit type", "unit", "purchase unit", "buying unit", "единица закупки", "единица", "тип единицы"],
    "month": ["month", "месяц"],
    "budget": [
        "total cost after discount, rur", "total cost after discount rur", "total cost after discount",
        "total cost, rur", "total cost", "net budget", "media budget", "budget", "бюджет",
        "стоимость после скидки", "стоимость размещения"
    ],
    "impressions": ["impressions", "impression", "ots", "показы", "показов", "показы / план", "показы план"],
    "units_qty": ["units qty total", "units qty", "кол-во единиц закупки", "количество единиц закупки"],
    "tech_reach": [
        "reach uu", "reach, uu", "technical reach", "reach ads", "охват ads", "технический охват",
        "unique reach", "unique users", "uu reach", "reach unique", "охват, uu / план", "охват uu / план",
        "охват, uu", "охват uu"
    ],
    "frequency": ["frequency", "freq", "average frequency", "avg frequency", "частота / план", "частота план", "частота", "средняя частота"],
    "period": ["period", "flight", "flight dates", "campaign period", "период", "период размещения"],
    "start_date": ["start date", "date start", "start", "дата старта", "дата начала", "начало размещения"],
    "end_date": ["end date", "date end", "finish date", "finish", "end", "дата окончания", "окончание размещения"],
    "cpm": ["cpm", "срм"], "cpc": ["cpc", "срс"], "cpa": ["cpa", "сра"], "cpi": ["cpi"],
    "cpo": ["cpo", "сро"], "cpl": ["cpl"], "cpr": ["cpr", "срr"], "cpv": ["cpv"],
    "cpcv": ["cpcv"], "cpe": ["cpe"], "cps": ["cps"],
    "clicks": ["clicks", "click", "клики", "переходы"],
    "actions": ["actions", "action", "действия", "конверсии", "conversions"],
    "installs": ["installs", "install", "установки", "установка"],
    "orders": ["orders", "order", "заказы", "заказов", "покупки"],
    "leads": ["leads", "lead", "лиды"],
    "reads": ["reads", "read", "прочтения", "прочтений", "дочитывания", "дочитываний", "completed reads"],
    "views": ["views", "view", "просмотры", "просмотров"],
    "completed_views": ["completed views", "completed view", "досмотры", "досмотров", "100% views", "full views"],
    "engagements": ["engagements", "engagement", "вовлечения", "реакции"],
    "sales": ["sales", "sale", "продажи"],
    "ctr": ["ctr", "кликабельность"], "vtr": ["vtr", "досматриваемость"],
}

EXACT_PRIORITY: Dict[str, List[str]] = {
    "platform": ["название сайта", "площадка", "site", "platform"],
    "format": ["формат", "format", "placement format", "ad format"],
    "budget": ["total cost after discount, rur", "total cost after discount rur", "общая стоимость после скидки, без ндс", "стоимость после скидки (до ндс)"],
    "tech_reach": ["reach uu", "reach, uu", "охват, uu / план", "охват uu / план", "технический охват за рк"],
    "frequency": ["frequency", "частота / план", "частота план", "частота"],
    "impressions": ["impressions", "показы / план", "показы план", "показы"],
}

PERF_MODELS = {
    "CPC": ("cpc", "clicks", "Клики"),
    "CPA": ("cpa", "actions", "Действия"),
    "CPI": ("cpi", "installs", "Установки"),
    "CPO": ("cpo", "orders", "Заказы"),
    "CPL": ("cpl", "leads", "Лиды"),
    "CPR": ("cpr", "reads", "Прочтения / дочитывания"),
    "CPCV": ("cpcv", "completed_views", "Досмотры"),
    "CPV": ("cpv", "views", "Просмотры"),
    "CPE": ("cpe", "engagements", "Вовлечения"),
    "CPS": ("cps", "sales", "Продажи"),
}

TOTAL_WORDS = ["grand total", "total digital", "digital total", "all digital", "all media", "итого", "всего", "тотал", "субтотал", "subtotal", "total"]


def column_score(label: str, key: str) -> float:
    l = norm(label)
    if not l:
        return 0.0
    if key == "sales" and "sales house" in l:
        return 0.0
    for x in EXACT_PRIORITY.get(key, []):
        if l == x:
            return 2.0
        if x in l:
            return 1.8
    if key in {"cpm", "cpc", "cpa", "cpi", "cpo", "cpl", "cpr", "cpv", "cpcv", "cpe", "cps", "ctr", "vtr"}:
        if re.search(rf"(^|[^a-z]){re.escape(key)}([^a-z]|$)", l):
            return 1.2
    best = 0.0
    for syn in COLUMN_SYNONYMS.get(key, []):
        s = norm(syn)
        if l == s:
            best = max(best, 1.0)
        elif s and s in l:
            best = max(best, 0.75 + min(len(s), 40) / 200)
    return best


def detect_columns(labels: Sequence[str]) -> Tuple[Dict[str, int], Dict[str, float]]:
    mapping: Dict[str, int] = {}
    conf: Dict[str, float] = {}

    # In some OMD templates a second operational block after "Run period" repeats
    # words such as Impression/Site/Status. Those are NOT the media forecast columns.
    # Core media metrics therefore prefer matches before the first Run period marker.
    run_period_idx: Optional[int] = None
    for i, label in enumerate(labels):
        if norm(label).startswith("run period"):
            run_period_idx = i
            break

    post_run_allowed = {"period", "start_date", "end_date"}
    for i, label in enumerate(labels):
        for key in COLUMN_SYNONYMS:
            if run_period_idx is not None and i >= run_period_idx and key not in post_run_allowed:
                continue
            sc = column_score(label, key)
            if sc < 0.58:
                continue
            # When scores are equal, keep the leftmost match. If a later match is only
            # slightly stronger, keep the earlier forecast column rather than an ops copy.
            if key not in conf or sc > conf[key] + 0.08:
                mapping[key] = i
                conf[key] = sc
    return mapping, conf


def _combine_header_rows(matrix: List[List[Any]], start: int, height: int) -> List[str]:
    end = min(start + height, len(matrix))
    # Media-plan KPI headers sit on the left/center; wide weekly calendars on the right
    # can contain hundreds of columns. Limit header semantic scanning for speed while
    # still covering LAB templates (Run Period is around col 96 in the current template).
    max_c = min(140, max((len(matrix[r]) for r in range(start, end)), default=0))
    labels: List[str] = []
    for c in range(max_c):
        parts: List[str] = []
        for r in range(start, end):
            v = matrix[r][c] if c < len(matrix[r]) else None
            s = norm(v)
            if s and s not in parts:
                parts.append(s)
        labels.append(" | ".join(parts) if parts else f"column_{c+1}")
    return labels


def _header_score(labels: Sequence[str]) -> Tuple[float, Dict[str, int], Dict[str, float]]:
    mapping, conf = detect_columns(labels)
    score = sum(conf.values())

    # Agency plans often have a very wide calendar to the right of the actual media table.
    # Week numbers and dates in that calendar must NOT destroy header detection.
    # Penalize numeric header tokens only inside the meaningful media/KPI block.
    metric_keys = {
        "platform", "format", "buying_model", "unit_type", "month", "budget",
        "impressions", "tech_reach", "frequency", "cpm", "cpc", "cpa", "cpi",
        "cpo", "cpl", "cpr", "cpv", "cpcv", "cpe", "cps", "clicks", "actions",
        "installs", "orders", "leads", "reads", "views", "completed_views",
        "engagements", "sales", "ctr", "vtr"
    }
    relevant_cols = [idx for key, idx in mapping.items() if key in metric_keys]
    last_relevant = max(relevant_cols) if relevant_cols else min(len(labels) - 1, 50)
    numeric_tokens = 0
    for lab in labels[:last_relevant + 1]:
        parts = [p.strip() for p in lab.split("|") if p.strip()]
        numeric_tokens += sum(1 for p in parts if to_number(p) is not None)
    score -= numeric_tokens * 2.5

    if "budget" in mapping:
        score += 6
    if "tech_reach" in mapping:
        score += 7
    if "impressions" in mapping:
        score += 2
    if "platform" in mapping:
        score += 1
    if "buying_model" in mapping or "unit_type" in mapping:
        score += 1
    if any(k in mapping for k in ["cpc", "cpa", "cpi", "cpo", "cpl", "cpr", "cpv", "cpcv", "cpe", "cps"]):
        score += 1

    has_media_metric = (
        "tech_reach" in mapping
        or "impressions" in mapping
        or any(k in mapping for k in ["cpc", "cpa", "cpi", "cpo", "cpr", "cpv", "cpcv", "cpl", "cpe", "cps"])
    )
    if not ("budget" in mapping and has_media_metric):
        score -= 12
    return score, mapping, conf


# ------------------------ metadata ------------------------

@dataclass
class SheetMeta:
    name: str
    period_start: Optional[dt.date] = None
    period_end: Optional[dt.date] = None
    period_raw: str = ""
    brand: str = ""
    campaign: str = ""
    # Stable product/line identity. When the source does not expose it explicitly,
    # discovery derives it conservatively from the campaign name.
    line: str = ""
    ta_name: str = ""
    ta_universe: Optional[float] = None
    ta_universe_source: str = ""
    inferred_channel: Optional[str] = None
    missing_formula_cache: int = 0
    # A single worksheet may contain several flights. Keep their real intervals,
    # source Universe and source Reach @1+ independently.
    flight_intervals: Dict[int, List[Tuple[dt.date, dt.date]]] = field(default_factory=dict)
    flight_universe: Dict[int, float] = field(default_factory=dict)
    flight_reach_people_1p: Dict[int, float] = field(default_factory=dict)
    flight_reach_pct_1p: Dict[int, float] = field(default_factory=dict)
    universe_candidates: List[Tuple[str, float]] = field(default_factory=list)


def _neighbor_values(matrix: List[List[Any]], r: int, c: int, radius: int = 4) -> List[Any]:
    vals: List[Any] = []
    row = matrix[r] if 0 <= r < len(matrix) else []
    # Embedded label+value handled separately; prioritize right cells.
    for cc in range(c + 1, min(c + 1 + radius, len(row))):
        if row[cc] not in (None, ""):
            vals.append(row[cc])
    for rr in range(r + 1, min(r + 3, len(matrix))):
        row2 = matrix[rr]
        for cc in range(c, min(c + radius, len(row2))):
            if row2[cc] not in (None, ""):
                vals.append(row2[cc])
    return vals


def extract_metadata(sheet: SheetData, default_year: int = 2026) -> SheetMeta:
    m = sheet.matrix
    meta = SheetMeta(
        name=sheet.name,
        inferred_channel=infer_channel(sheet.name),
        missing_formula_cache=sheet.formulas_without_cached_values,
    )
    scan_rows = min(160, len(m))
    exact_universe: Optional[float] = None
    reach_rows: List[Tuple[int, Optional[int], Optional[float], Optional[float]]] = []

    for r in range(scan_rows):
        row = m[r]
        for c, v in enumerate(row):
            t = norm(v)
            if not t:
                continue

            # Campaign identity is used to distinguish several independent media plans
            # stored in one workbook from true multi-flight sheets of one campaign.
            label_key = t.rstrip(":;")
            if label_key in {
                "бренд", "brand", "client/brand", "client brand",
                "клиент/бренд", "клиент бренд",
            } and not meta.brand:
                for cc in range(c + 1, min(c + 4, len(row))):
                    txt = clean_display(row[cc])
                    if txt:
                        meta.brand = txt
                        break
            if label_key in {
                "кампания", "campaign", "campain", "campaing", "campaign name", "campain name", "campaing name",
                "название кампании",
            } and not meta.campaign:
                for cc in range(c + 1, min(c + 4, len(row))):
                    txt = clean_display(row[cc])
                    if txt:
                        meta.campaign = txt
                        break

            # Product / line is a level above a flight. Some LAB/OMD templates expose
            # it directly, others only encode it in Campaign name. Keep the explicit
            # source whenever it exists and derive a fallback only during discovery.
            if label_key in {
                "линейка", "линия", "продукт", "продукт/линейка", "линейка/продукт",
                "product", "product line", "range", "subbrand", "sub-brand", "суббренд",
            } and not meta.line:
                for cc in range(c + 1, min(c + 4, len(row))):
                    txt = clean_display(row[cc])
                    if txt and to_number(txt) is None:
                        meta.line = txt
                        break

            # Campaign period in header: same cell or neighboring cells.
            period_label = (
                t == "period" or t.startswith("period:") or t.startswith("period ")
                or t.startswith("campaign period") or t == "период"
                or t.startswith("период:") or t.startswith("период ")
                or t.startswith("период рк")
            )
            if period_label and meta.period_start is None and _flight_number_from_text(t) is None:
                candidates: List[Any] = []
                if ":" in str(v):
                    candidates.append(str(v).split(":", 1)[1])
                else:
                    candidates.append(re.sub(r"(?i)^\s*(campaign\s+)?period\s*", "", str(v)).strip())
                candidates.extend(_neighbor_values(m, r, c, 5))
                for cand in candidates:
                    intervals = parse_period_intervals(cand, default_year)
                    if intervals:
                        meta.period_start = min(a for a, _ in intervals)
                        meta.period_end = max(b for _, b in intervals)
                        meta.period_raw = clean_display(cand)
                        break

            # Flight-specific period, including "Период Флайт 1:" and "Флайт 2:".
            flight_num = _flight_number_from_text(t)
            if flight_num is not None and ("флайт" in t or "flight" in t or "wave" in t or "волна" in t):
                candidates: List[Any] = []
                # Text after ':' may contain a period in compact templates.
                if ":" in str(v):
                    tail = str(v).split(":", 1)[1].strip()
                    if tail:
                        candidates.append(tail)
                # Prefer immediate cells to the right; do not scan below because other flights follow.
                for cc in range(c + 1, min(c + 6, len(row))):
                    if row[cc] not in (None, ""):
                        candidates.append(row[cc])
                for cand in candidates:
                    intervals = parse_period_intervals(cand, default_year)
                    if intervals:
                        meta.flight_intervals[flight_num] = intervals
                        break

            # TA name in header: "TA | Ж 25-45 BC" / "ЦА: | ...".
            if (t == "ta" or t.rstrip(":") in {"цa", "ца", "target audience"}) and not meta.ta_name:
                for cand in _neighbor_values(m, r, c, 3):
                    txt = clean_display(cand)
                    if txt and to_number(txt) is None:
                        meta.ta_name = txt
                        break

            # Universe: support TA Universe, Russian labels and the CrossWeb wording
            # used in the second battle workbook.
            universe_label = (
                t == "ta universe" or t.startswith("ta universe:") or t.startswith("ta universe ")
                or t.startswith("target audience universe") or t.startswith("universe ta")
                or t.startswith("юниверс ца") or t.startswith("crossweb universe")
            )
            russian_audience_label = t.startswith("объем аудитории") or t.startswith("объём аудитории")
            if universe_label or russian_audience_label:
                if russian_audience_label and not meta.ta_name:
                    label_txt = clean_display(v)
                    label_txt = re.sub(r"(?i)^\s*об[ъь]?ем\s+аудитории\s*", "", label_txt).strip()
                    label_txt = re.sub(r"(?i)[,;:]?\s*(чел|человек|people)\s*$", "", label_txt).strip()
                    meta.ta_name = label_txt
                candidates: List[Any] = []
                if ":" in str(v):
                    candidates.append(str(v).split(":", 1)[1])
                candidates.extend(row[c + 1:min(c + 6, len(row))])
                found = None
                for cand in candidates:
                    n = to_number(cand)
                    if n is not None and n >= 1000:
                        found = n
                        break
                if found is not None:
                    label = clean_display(v)
                    meta.universe_candidates.append((label, found))
                    # Only an unqualified CrossWeb/TA Universe is a sheet-level default.
                    if t in {"crossweb universe", "ta universe", "target audience universe", "universe ta", "юниверс ца"} or russian_audience_label:
                        exact_universe = found
                        meta.ta_universe = found
                        meta.ta_universe_source = "mp"

            # Source Reach @1+ rows. Two adjacent numbers are typically people and pct.
            if ("охват в людях" in t or "reach people" in t or "people reach" in t) and "1+" in t:
                nums: List[float] = []
                for cc in range(c + 1, min(c + 7, len(row))):
                    n = to_number(row[cc])
                    if n is not None:
                        nums.append(n)
                people = next((n for n in nums if n >= 1000), None)
                pct = next((n for n in nums if 0 < n <= 1.5), None)
                reach_rows.append((r, _flight_number_from_text(t), people, pct))

    # If there is exactly one qualified CrossWeb Universe, it is still safe as a sheet default.
    if meta.ta_universe is None and len(meta.universe_candidates) == 1:
        meta.ta_universe = meta.universe_candidates[0][1]
        meta.ta_universe_source = "mp"
        exact_universe = meta.ta_universe

    # Map unnumbered Reach rows to flights by order. This covers templates where the
    # rows are named by segment (e.g. legs/hands) while flight periods are listed nearby.
    flight_nums = sorted(meta.flight_intervals)
    numbered_flights = {x[1] for x in reach_rows if x[1] is not None}
    missing_flights = [n for n in flight_nums if n not in numbered_flights]
    unnumbered = [x for x in reach_rows if x[1] is None]
    ordered_map: Dict[int, Tuple[Optional[float], Optional[float]]] = {}
    if missing_flights and unnumbered:
        for n, item in zip(missing_flights, sorted(unnumbered, key=lambda x: x[0])):
            ordered_map[n] = (item[2], item[3])

    for _row, n_hint, people, pct in reach_rows:
        if n_hint is None:
            continue
        if people is not None:
            meta.flight_reach_people_1p[n_hint] = people
        if pct is not None:
            meta.flight_reach_pct_1p[n_hint] = pct
        if people is not None and pct not in (None, 0):
            u = people / pct
            if u >= 1000:
                meta.flight_universe[n_hint] = u

    for n, (people, pct) in ordered_map.items():
        if people is not None:
            meta.flight_reach_people_1p[n] = people
        if pct is not None:
            meta.flight_reach_pct_1p[n] = pct
        if people is not None and pct not in (None, 0):
            u = people / pct
            if u >= 1000:
                meta.flight_universe[n] = u

    # A common exact CrossWeb Universe applies to every flight unless a flight-specific
    # denominator was recovered from source Reach people / Reach %.
    if exact_universe is not None:
        for n in flight_nums:
            meta.flight_universe.setdefault(n, exact_universe)

    # Complete source reach from pct × Universe when the workbook's people formula has no cache.
    for n, pct in list(meta.flight_reach_pct_1p.items()):
        u = meta.flight_universe.get(n) or exact_universe
        if n not in meta.flight_reach_people_1p and u is not None:
            meta.flight_reach_people_1p[n] = u * pct

    # When all flight universes are equal, expose the common value at sheet level.
    if meta.ta_universe is None and meta.flight_universe:
        vals = [round(v, 3) for v in meta.flight_universe.values()]
        if len(set(vals)) == 1:
            meta.ta_universe = vals[0]
            meta.ta_universe_source = "mp"

    # If only flight periods are present, they define the sheet campaign span.
    if meta.flight_intervals:
        all_intervals = [iv for vals in meta.flight_intervals.values() for iv in vals]
        if all_intervals:
            if meta.period_start is None:
                meta.period_start = min(a for a, _ in all_intervals)
            if meta.period_end is None:
                meta.period_end = max(b for _, b in all_intervals)
    return meta


# ------------------------ table extraction ------------------------

@dataclass
class TableDef:
    sheet_name: str
    header_start: int
    header_height: int
    labels: List[str]
    mapping: Dict[str, int]
    confidence: Dict[str, float]
    channel: Optional[str]
    score: float
    data_start: int
    data_end: int


def find_tables(sheet: SheetData, meta: SheetMeta) -> List[TableDef]:
    m = sheet.matrix
    if not m:
        return []
    candidates: List[Tuple[float, int, int, List[str], Dict[str, int], Dict[str, float]]] = []
    search_rows = min(250, len(m))

    # Fast path for multi-flight workbooks: first find rows that look like a media header
    # by a budget token, then score only nearby 1-3 row header windows. This avoids
    # re-scoring hundreds of calendar columns for every row on every flight sheet.
    anchor_rows: List[int] = []
    budget_tokens = (
        "total cost after discount", "net budget", "media budget", "budget",
        "бюджет", "стоимость после скидки",
    )
    for r in range(search_rows):
        txt = " | ".join(norm(v) for v in m[r][:140] if v not in (None, ""))
        if any(tok in txt for tok in budget_tokens):
            anchor_rows.append(r)

    starts_to_check: List[int]
    if anchor_rows:
        starts = set()
        for r in anchor_rows:
            for st in range(max(0, r - 2), min(search_rows, r + 1)):
                starts.add(st)
        starts_to_check = sorted(starts)
    else:
        starts_to_check = list(range(search_rows))

    for start in starts_to_check:
        for h in (1, 2, 3):
            labels = _combine_header_rows(m, start, h)
            score, mapping, conf = _header_score(labels)
            score -= (h - 1) * 0.35
            if score >= 5:
                candidates.append((score, start, h, labels, mapping, conf))

    # choose non-overlapping high-quality headers
    candidates.sort(key=lambda x: (x[1], -x[0], x[2]))
    selected: List[Tuple[float, int, int, List[str], Dict[str, int], Dict[str, float]]] = []
    last_end = -10
    # For same nearby region choose the best.
    by_region: List[List[Tuple]] = []
    for cand in candidates:
        if not by_region or cand[1] - by_region[-1][-1][1] > 3:
            by_region.append([cand])
        else:
            by_region[-1].append(cand)
    for region in by_region:
        best = max(region, key=lambda x: x[0])
        selected.append(best)
    selected.sort(key=lambda x: x[1])

    tables: List[TableDef] = []
    for idx, (score, start, h, labels, mapping, conf) in enumerate(selected):
        data_start = start + h
        next_header = selected[idx + 1][1] if idx + 1 < len(selected) else len(m)
        # cut at 15 consecutive blank rows, otherwise before next header
        end = next_header - 1
        blank = 0
        for r in range(data_start, next_header):
            row = m[r]
            if all(v in (None, "") for v in row[:len(labels)]):
                blank += 1
                if blank >= 15:
                    end = r - blank
                    break
            else:
                blank = 0
        # channel from sheet or 12 rows above header
        chan = meta.inferred_channel
        if chan is None:
            # Search the nearest section label ABOVE the header. Never inspect the header
            # itself because words like "Performance" can be metric group labels, not channels.
            for rr in range(start - 1, max(-1, start - 13), -1):
                c = infer_channel_from_values(m[rr])
                if c:
                    chan = c
                    break
        tables.append(TableDef(sheet.name, start, h, labels, mapping, conf, chan, score, data_start, max(data_start - 1, end)))
    return tables


@dataclass
class Placement:
    sheet: str
    source_row: int
    flight: str = "F1"
    flight_label: str = "Flight 1"
    channel: str = "Other"
    # Stage-3 classifier; separate from legacy channel so calculations are untouched.
    placement_class: Optional[str] = None
    placement_class_reason: str = ""
    platform: str = ""
    platform_canonical: str = ""
    platform_match_reason: str = ""
    platform_match_confidence: float = 0.0
    platform_status: str = "NEW_PLATFORM"
    platform_needs_review: bool = True
    platform_suggested_canonical: str = ""
    is_bonus: bool = False
    research_marker: str = ""
    research_status: str = ""
    research_cost: Optional[float] = None
    research_is_dedicated: bool = False
    format: str = ""
    buying_model: str = "OTHER"
    budget: Optional[float] = None
    impressions: Optional[float] = None
    tech_reach: Optional[float] = None
    frequency: Optional[float] = None
    start: Optional[dt.date] = None
    end: Optional[dt.date] = None
    target_kpi_label: str = ""
    target_kpi_value: Optional[float] = None
    is_total: bool = False
    synthetic_total: bool = False
    raw_text: str = ""
    # Source-structure hints used to split one physical row across several flights.
    flight_hint: Optional[int] = None
    common_scope: bool = False
    intervals: List[Tuple[dt.date, dt.date]] = field(default_factory=list)
    # Structure-only activity periods read from calendar flag columns (e.g. 1/blank
    # under dated month headers). They are used to identify flight periods but are not
    # substituted into the existing flow/reach/split calculations at this stage.
    structure_intervals: List[Tuple[dt.date, dt.date]] = field(default_factory=list)
    month_budget: Dict[int, float] = field(default_factory=dict)
    month_volume: Dict[int, float] = field(default_factory=dict)
    reach: Dict[str, float] = field(default_factory=dict)

    def signature(self) -> Tuple:
        # Ignore sheet/channel for detail rows so the same placement repeated on a summary
        # and a channel sheet is deduplicated. Keep channel for totals because OLV TOTAL
        # and Banners TOTAL are distinct objects.
        return (
            norm(self.flight),
            norm(self.channel) if self.is_total else "",
            norm(self.platform), norm(self.format), norm(self.buying_model),
            round(self.budget or 0, 2), round(self.impressions or 0, 2), round(self.tech_reach or 0, 2),
            self.start, self.end, self.is_total
        )


def _model_from_unit_type(v: Any) -> Optional[str]:
    t = norm(v)
    if not t:
        return None
    if "1000 imp" in t or "1000 impression" in t or "1000 показ" in t or "тыс показ" in t:
        return "CPM"
    if "click" in t or "клик" in t:
        return "CPC"
    if "completed view" in t or "100% view" in t or "досмотр" in t:
        return "CPV"
    if re.search(r"(^|\b)view(s)?(\b|$)", t) or "просмотр" in t:
        return "CPV"
    if "install" in t or "установ" in t:
        return "CPI"
    if "order" in t or "заказ" in t or "purchase" in t or "покуп" in t:
        return "CPO"
    if "lead" in t or "лид" in t:
        return "CPL"
    if "read" in t or "прочт" in t or "дочит" in t:
        return "CPR"
    if "action" in t or "conversion" in t or "действ" in t or "конверс" in t:
        return "CPA"
    if "engagement" in t or "вовлеч" in t:
        return "CPE"
    if "sale" in t or "продаж" in t:
        return "CPS"
    return None


def detect_model(text: str, row: Sequence[Any], mapping: Dict[str, int]) -> str:
    # 1) Explicit buying model column is authoritative.
    explicit = clean_display(_get(row, mapping, "buying_model"))
    if explicit:
        t = norm(explicit).upper()
        for code in ("CPCV", "CPM", "CPC", "CPA", "CPI", "CPO", "CPL", "CPR", "CPV", "CPE", "CPS"):
            if re.search(rf"(^|[^A-Z]){code}([^A-Z]|$)", t):
                return code

    # 2) In LAB agency templates, Unit type is the real buying-model signal.
    #    Example: 1000 imp. = CPM. CPC/CPV columns may be forecast KPIs and MUST
    #    not override the actual buying model.
    unit_model = _model_from_unit_type(_get(row, mapping, "unit_type"))
    if unit_model:
        return unit_model

    # 3) Explicit CPM/CPC/... token in descriptive row text.
    t = norm(text).upper()
    for code in ("CPCV", "CPM", "CPC", "CPA", "CPI", "CPO", "CPL", "CPR", "CPV", "CPE", "CPS"):
        if re.search(rf"(^|[^A-Z]){code}([^A-Z]|$)", t):
            return code

    # 4) Rate-column fallback only if EXACTLY ONE buying-rate column is populated.
    #    Several rate columns can coexist as forecast metrics in media plans.
    populated = []
    for code in ("CPCV", "CPC", "CPA", "CPI", "CPO", "CPL", "CPR", "CPV", "CPE", "CPS", "CPM"):
        key = code.lower()
        idx = mapping.get(key)
        if idx is not None and idx < len(row) and to_number(row[idx]) not in (None, 0):
            populated.append(code)
    if len(populated) == 1:
        return populated[0]
    return "OTHER"


def _get(row: Sequence[Any], mapping: Dict[str, int], key: str) -> Any:
    idx = mapping.get(key)
    if idx is None or idx >= len(row):
        return None
    return row[idx]


def _row_total(text: str) -> bool:
    t = norm(text)
    return any(re.search(rf"(^|\b){re.escape(w)}(\b|$)", t) for w in TOTAL_WORDS)


def _is_unlabeled_subtotal(
    row: Sequence[Any],
    mapping: Dict[str, int],
    platform: str,
    fmt: str,
    model: str,
) -> bool:
    """
    Real media plans often contain a channel subtotal row with no label at all:
    Site/Placement/Buy type are blank, while budget/impressions/reach/frequency/KPI
    cells contain calculated totals.

    We treat such a numeric-only aggregate row as a subtotal when:
    - there is no descriptive placement name;
    - buying model is blank/OTHER;
    - at least two aggregate metrics are populated;
    - at least one of Impressions / Reach UU / a result KPI is present.

    This intentionally avoids requiring words Total/Subtotal.
    """
    if platform or fmt:
        return False

    # Buying model is intentionally NOT used here. In real media plans an unlabeled
    # subtotal may contain derived CPC/CPV metrics even when the channel is bought on CPM.
    # The subtotal model is inferred later from the actual child placements.
    aggregate_keys = [
        "budget", "impressions", "tech_reach", "frequency",
        "clicks", "actions", "installs", "orders", "leads", "reads",
        "views", "completed_views", "engagements", "sales"
    ]
    populated = {
        k: to_number(_get(row, mapping, k))
        for k in aggregate_keys
        if k in mapping
    }
    populated = {k: v for k, v in populated.items() if v is not None}

    if len(populated) < 2:
        return False

    result_keys = {
        "impressions", "tech_reach", "clicks", "actions", "installs",
        "orders", "leads", "reads", "views", "completed_views",
        "engagements", "sales"
    }
    if not any(k in populated for k in result_keys):
        return False

    # If the row contains meaningful free text outside known metric/model cells,
    # it is more likely a placement than an unlabeled subtotal.
    known_cols = set(mapping.values())
    free_text = []
    for idx, v in enumerate(row):
        if idx in known_cols or v in (None, "") or is_numeric(v):
            continue
        txt = clean_display(v)
        if txt:
            free_text.append(txt)
    if free_text:
        return False

    return True


def _descriptive_name(row: Sequence[Any], mapping: Dict[str, int]) -> Tuple[str, str]:
    platform = clean_display(_get(row, mapping, "platform"))
    fmt = clean_display(_get(row, mapping, "format"))
    if platform or fmt:
        return platform, fmt
    # fallback: first text cells that aren't obvious total/channel/model/headers
    texts: List[str] = []
    for v in row[:12]:
        if v in (None, "") or is_numeric(v):
            continue
        s = clean_display(v)
        n = norm(s)
        if not s or infer_channel(s) or re.search(r"\b(CPM|CPC|CPA|CPI|CPO|CPL|CPR|CPV|CPCV|CPE|CPS)\b", s.upper()):
            continue
        if any(w in n for w in TOTAL_WORDS):
            continue
        texts.append(s)
    if texts:
        platform = texts[0]
    if len(texts) > 1:
        fmt = texts[1]
    return platform, fmt


def _month_number(v: Any) -> Optional[int]:
    t = norm(v)
    if not t:
        return None
    for m, variants in MONTH_WORDS.items():
        if any(re.search(rf"(^|[^a-zа-я]){re.escape(x)}", t) for x in variants):
            return m
    return None


def _clamped_month_period(month_num: int, meta: SheetMeta, default_year: int) -> Tuple[Optional[dt.date], Optional[dt.date]]:
    year = meta.period_start.year if meta.period_start else default_year
    s = dt.date(year, month_num, 1)
    e = dt.date(year, month_num, calendar.monthrange(year, month_num)[1])
    if meta.period_start and s < meta.period_start:
        s = meta.period_start
    if meta.period_end and e > meta.period_end:
        e = meta.period_end
    if e < s:
        return None, None
    return s, e



@dataclass
class _PlanMonthBlock:
    kind: str  # "volume" | "budget"
    start_col: int
    header_row: int
    context: str = ""


def _month_sequence_at(row: Sequence[Any], start_col: int) -> bool:
    if start_col < 0 or start_col + 12 > len(row):
        return False
    return all(_month_number(row[start_col + i]) == i + 1 for i in range(12))


def _month_block_context(matrix: List[List[Any]], header_row: int, start_col: int) -> str:
    bits: List[str] = []
    for rr in range(header_row - 1, max(-1, header_row - 7), -1):
        row = matrix[rr]
        local = []
        for cc in range(max(0, start_col - 1), min(len(row), start_col + 12)):
            txt = clean_display(row[cc])
            if txt:
                local.append(txt)
        if local:
            bits.extend(local)
            # Nearest non-empty group label normally owns this month sequence.
            joined = " | ".join(local)
            if re.search(r"об[ъь]?ем|volume|бюдж|budget|факт|actual|plan|план", norm(joined)):
                break
    return " | ".join(bits)


def _find_plan_month_blocks(sheet: SheetData, table: TableDef) -> Dict[str, _PlanMonthBlock]:
    matrix = sheet.matrix
    if not matrix:
        return {}
    r0 = max(0, table.header_start - 8)
    r1 = min(len(matrix), table.header_start + table.header_height + 5)
    max_cols = min(180, max((len(matrix[r]) for r in range(r0, r1)), default=0))
    candidates: List[_PlanMonthBlock] = []
    for rr in range(r0, r1):
        row = matrix[rr]
        for cc in range(0, max(0, min(len(row), max_cols) - 11)):
            if not _month_sequence_at(row, cc):
                continue
            ctx = norm(_month_block_context(matrix, rr, cc))
            if re.search(r"факт|actual|fact", ctx):
                continue
            kind = ""
            if re.search(r"бюдж|budget", ctx):
                kind = "budget"
            elif re.search(r"об[ъь]?ем|volume", ctx):
                kind = "volume"
            if kind:
                candidates.append(_PlanMonthBlock(kind, cc, rr, ctx))
    out: Dict[str, _PlanMonthBlock] = {}
    for kind in ("volume", "budget"):
        vals = [x for x in candidates if x.kind == kind]
        if vals:
            # Prefer the candidate closest to the main header; for ties keep leftmost.
            vals.sort(key=lambda x: (abs(x.header_row - table.header_start), x.start_col))
            out[kind] = vals[0]
    return out


def _horizontal_month_values(row: Sequence[Any], block: Optional[_PlanMonthBlock]) -> Dict[int, float]:
    if block is None:
        return {}
    out: Dict[int, float] = {}
    for month in range(1, 13):
        idx = block.start_col + month - 1
        n = to_number(row[idx]) if idx < len(row) else None
        if n is not None and abs(n) > 1e-12:
            out[month] = float(n)
    return out


def _months_to_intervals(months: Iterable[int], year: int) -> List[Tuple[dt.date, dt.date]]:
    vals = sorted({int(m) for m in months if 1 <= int(m) <= 12})
    if not vals:
        return []
    spans: List[Tuple[int, int]] = []
    a = b = vals[0]
    for m in vals[1:]:
        if m == b + 1:
            b = m
        else:
            spans.append((a, b)); a = b = m
    spans.append((a, b))
    return [
        (dt.date(year, a, 1), dt.date(year, b, calendar.monthrange(year, b)[1]))
        for a, b in spans
    ]


def _find_structure_calendar_columns(sheet: SheetData, table: TableDef, default_year: int) -> Dict[int, Tuple[dt.date, dt.date]]:
    """Find a horizontal calendar of explicit dated periods near a media header.

    Some production LAB sheets mark campaign activity with 1/blank cells under headers
    such as ``01.09.2025 - 30.09.2025`` while volume/budget columns may cover a narrower
    paid period. This calendar is structural evidence for a flight period only.
    """
    matrix = sheet.matrix
    if not matrix:
        return {}
    r0 = max(0, table.header_start - 4)
    r1 = min(len(matrix), table.header_start + table.header_height + 3)
    best: Dict[int, Tuple[dt.date, dt.date]] = {}
    for rr in range(r0, r1):
        row = matrix[rr]
        current: Dict[int, Tuple[dt.date, dt.date]] = {}
        for cc, value in enumerate(row[:180]):
            # Structural calendar headers are explicit dated ranges, not repeated
            # month-name labels used by volume/budget blocks.
            if not re.search(r"\d{1,2}[./-]\d{1,2}", clean_display(value)):
                continue
            ints = parse_period_intervals(value, default_year)
            if len(ints) != 1:
                continue
            a, b = ints[0]
            # Calendar columns in these templates are monthly/short planning windows,
            # not generic campaign periods in the left metadata block.
            if (b - a).days > 45:
                continue
            current[cc] = (a, b)
        if len(current) >= 3 and len(current) > len(best):
            best = current
    return best


def _structure_intervals_from_row(row: Sequence[Any], columns: Dict[int, Tuple[dt.date, dt.date]]) -> List[Tuple[dt.date, dt.date]]:
    active: List[Tuple[dt.date, dt.date]] = []
    for cc, period in columns.items():
        if cc >= len(row):
            continue
        value = row[cc]
        n = to_number(value)
        if (n is not None and abs(n) > 1e-12) or (n is None and clean_display(value)):
            active.append(period)
    return _merge_date_intervals(active)


def parse_table(sheet: SheetData, meta: SheetMeta, table: TableDef, default_year: int = 2026) -> List[Placement]:
    out: List[Placement] = []
    current_channel = table.channel or "Other"
    current_placement_class = infer_placement_section(current_channel, current_channel) if current_channel and current_channel != "Other" else None
    current_flight_hint: Optional[int] = None
    current_common_scope = False
    seen_channels: set[str] = set()
    m = sheet.matrix
    max_c = max(len(table.labels), max((len(row) for row in m[table.data_start:min(table.data_end + 1, len(m))]), default=0))
    month_blocks = _find_plan_month_blocks(sheet, table)
    structure_calendar = _find_structure_calendar_columns(sheet, table, default_year)

    for r in range(table.data_start, min(table.data_end + 1, len(m))):
        row = list(m[r][:max_c]) + [None] * max(0, max_c - len(m[r]))
        row = row[:max_c]
        if all(v in (None, "") for v in row):
            continue

        raw = " | ".join(clean_display(v) for v in row if v not in (None, ""))
        left_label = clean_display(_get(row, table.mapping, "platform"))
        if not left_label:
            # In header-driven templates the first descriptive cell is normally within
            # the first 12 columns. This catches Flight/Common section labels even when
            # the platform mapping is temporarily ambiguous.
            left_label = next((clean_display(v) for v in row[:12] if v not in (None, "") and not is_numeric(v)), "")

        # Internal flight marker rows are structure, never placements. This is checked
        # before numeric tests because such rows may contain subtotal formulas far right.
        marker_flight = _flight_number_from_text(left_label or raw)
        marker_norm = norm(left_label or raw)
        if marker_flight is not None and ("флайт" in marker_norm or "flight" in marker_norm or "wave" in marker_norm or "волна" in marker_norm):
            current_flight_hint = marker_flight
            current_common_scope = False
            continue

        # Explicit common/AON section starts rows which should not be forced into the
        # preceding flight. Examples: "Общее", "Общий блок", "AON".
        if _is_common_section(left_label):
            current_flight_hint = None
            current_common_scope = True
            common_channel = infer_channel(raw)
            if common_channel:
                if common_channel in {"Search / Context", "Performance"}:
                    common_channel = "Perfomance"
                current_channel = common_channel
                current_placement_class = infer_placement_section(raw, common_channel)
                seen_channels.add(common_channel)
            continue

        row_channel = infer_channel(raw)

        # Pure channel section row. Ignore calendar/week cells far to the right: only
        # mapped media metrics and the descriptive left block determine whether this is data.
        numbers_present = any(
            (to_number(_get(row, table.mapping, k)) not in (None, 0))
            for k in ["budget", "impressions", "tech_reach", "cpc", "cpa", "cpi", "cpo", "cpr", "cpv", "cpcv"]
        )
        left_nonempty = sum(v not in (None, "") for v in row[:min(20, len(row))])
        if row_channel and not numbers_present and left_nonempty <= 8:
            if row_channel in {"Search / Context", "Performance"}:
                row_channel = "Perfomance"
            current_channel = row_channel
            current_placement_class = infer_placement_section(raw, row_channel)
            seen_channels.add(row_channel)
            continue

        budget = to_number(_get(row, table.mapping, "budget"))
        impressions = to_number(_get(row, table.mapping, "impressions"))
        reach = to_number(_get(row, table.mapping, "tech_reach"))
        frequency = to_number(_get(row, table.mapping, "frequency"))

        # Some LAB files have broken cached formulas (#NAME?) in Impressions while
        # Units Qty total is intact. For 1000 imp. buying units, rebuild impressions.
        if impressions is None:
            units_qty = to_number(_get(row, table.mapping, "units_qty"))
            unit_txt = norm(_get(row, table.mapping, "unit_type"))
            if units_qty is not None and ("1000 imp" in unit_txt or "1000 impression" in unit_txt or "1000 показ" in unit_txt):
                impressions = units_qty * 1000.0

        platform, fmt = _descriptive_name(row, table.mapping)
        is_bonus, research_marker = placement_markers(platform, fmt, raw)
        platform_canonical, platform_match_reason, platform_match_confidence = canonicalize_platform_name(platform)
        platform_status, platform_needs_review, platform_suggested_canonical = platform_identity_state(
            platform, platform_canonical, platform_match_reason, platform_match_confidence
        )
        model_text = clean_display(_get(row, table.mapping, "buying_model")) + " | " + raw
        model = detect_model(model_text, row, table.mapping)
        research_marker, research_status, research_cost, research_is_dedicated = research_details(
            platform, fmt, raw, budget
        )
        if research_is_dedicated and not platform_canonical:
            platform_canonical = "Исследование"
            platform_status = "RESEARCH_ROW"
            platform_needs_review = False
            platform_suggested_canonical = ""

        performance_amount_present = any(
            to_number(_get(row, table.mapping, x)) is not None
            for x in ["clicks", "orders", "installs", "reads", "actions", "leads", "views", "completed_views", "sales"]
        )

        # Prevent lower calculation/summary blocks from being mistaken for placements.
        meaningful = (
            budget is not None
            or impressions is not None
            or performance_amount_present
            or (reach is not None and bool(platform or fmt))
        )
        if not meaningful:
            continue

        month_budget = _horizontal_month_values(row, month_blocks.get("budget"))
        month_volume = _horizontal_month_values(row, month_blocks.get("volume"))
        active_months = sorted(set(month_budget) | set(month_volume))
        structure_intervals = _structure_intervals_from_row(row, structure_calendar)

        # Dates: authoritative horizontal plan months first, then explicit Month/date fields.
        intervals: List[Tuple[dt.date, dt.date]] = []
        year = default_year
        if current_flight_hint is not None and meta.flight_intervals.get(current_flight_hint):
            year = meta.flight_intervals[current_flight_hint][0][0].year
        elif meta.period_start:
            year = meta.period_start.year
        if active_months:
            intervals = _months_to_intervals(active_months, year)

        s = e = None
        if intervals:
            s = min(a for a, _ in intervals)
            e = max(b for _, b in intervals)
        if (not s or not e) and "month" in table.mapping:
            mn = _month_number(_get(row, table.mapping, "month"))
            if mn:
                s, e = _clamped_month_period(mn, meta, default_year)
                if s and e:
                    intervals = [(s, e)]
        if not s or not e:
            s = _parse_single_date(_get(row, table.mapping, "start_date"), default_year)
            e = _parse_single_date(_get(row, table.mapping, "end_date"), default_year)
            if s and e:
                intervals = [(min(s, e), max(s, e))]
        if (not s or not e) and "period" in table.mapping:
            period_idx = table.mapping.get("period")
            pints = parse_period_intervals(_get(row, table.mapping, "period"), default_year)
            if pints:
                intervals = pints
                s, e = min(a for a, _ in pints), max(b for _, b in pints)
                # In LAB templates "Период РК" is often a merged visual header over
                # two physical columns: start date in the mapped cell and end date
                # immediately to the right. A numeric Excel start date is itself a
                # valid one-day interval, so without this check rows such as
                # 01.05.2026 | 31.05.2026 become 01.05–01.05 in the flowchart.
                if (
                    len(pints) == 1 and s == e
                    and period_idx is not None and period_idx + 1 < len(row)
                ):
                    right_date = _parse_single_date(row[period_idx + 1], default_year)
                    if right_date is not None and right_date >= s:
                        e = right_date
                        intervals = [(s, e)]
            else:
                ps, pe = parse_period(_get(row, table.mapping, "period"), default_year)
                if ps is not None and (pe is None or pe == ps) and period_idx is not None and period_idx + 1 < len(row):
                    right_date = _parse_single_date(row[period_idx + 1], default_year)
                    if right_date is not None and right_date >= ps:
                        pe = right_date
                s = s or ps
                e = e or pe
                if s and e:
                    intervals = [(s, e)]
        s = s or meta.period_start
        e = e or meta.period_end or s
        if not intervals and s and e:
            intervals = [(s, e)]

        # Explicit product rows override an enclosing channel section. This is critical
        # for Always-on blocks: ORM must remain ORM, and Yandex PromoPages must be shown
        # as a separate Articles row instead of being absorbed into Perfomance/Native.
        special_channel = _special_row_channel(
            platform, fmt, raw, model=model,
            current_channel=current_channel, row_channel=row_channel,
        )
        channel = special_channel or (current_channel if current_channel and current_channel != "Other" else (row_channel or meta.inferred_channel or "Other"))
        if channel in {"Search / Context", "Performance"}:
            channel = "Perfomance"

        placement_class, placement_class_reason = classify_placement(
            platform=platform_canonical or platform, fmt=fmt, raw=raw, model=model,
            legacy_channel=channel, section_class=current_placement_class,
        )
        if research_is_dedicated:
            placement_class = "Исследования"
            placement_class_reason = f"dedicated research row: {research_marker}"
            channel = "Исследования"
        if placement_class is None and placement_class_reason.startswith("technical/service"):
            platform_status = "TECHNICAL_ROW"
            platform_needs_review = False
            platform_suggested_canonical = ""

        explicit_total = _row_total(raw)
        total = explicit_total or _is_unlabeled_subtotal(
            row=row, mapping=table.mapping, platform=platform, fmt=fmt, model=model
        )

        # A generic TOTAL after several channel blocks is the all-media campaign total.
        is_campaign_total = False
        if explicit_total:
            descriptive = [clean_display(v) for v in row[:20] if v not in (None, "") and not is_numeric(v)]
            generic_total = any(norm(x).rstrip(":;") in {"total", "итого", "grand total", "total digital", "digital total"} for x in descriptive)
            if generic_total and len(seen_channels) >= 2:
                channel = "TOTAL"
                is_campaign_total = True

        if not total and channel and channel != "Other":
            seen_channels.add(channel)

        if total and channel != "Other":
            child_models = {
                x.buying_model for x in out
                if (not x.is_total) and x.channel == channel and x.buying_model != "OTHER"
            }
            if len(child_models) == 1:
                model = next(iter(child_models))

        kpi_label = ""
        kpi_value: Optional[float] = None
        if model in PERF_MODELS:
            rate_key, count_key, label = PERF_MODELS[model]
            kpi_label = label
            kpi_value = to_number(_get(row, table.mapping, count_key))
            if kpi_value is None:
                rate = to_number(_get(row, table.mapping, rate_key))
                if budget is not None and rate not in (None, 0):
                    kpi_value = budget / rate
        elif model == "CPM":
            kpi_label = "Показы"
            kpi_value = impressions
        else:
            for key, label in [
                ("clicks", "Клики"), ("orders", "Заказы"), ("installs", "Установки"),
                ("reads", "Прочтения / дочитывания"), ("actions", "Действия"),
                ("leads", "Лиды"), ("views", "Просмотры"), ("completed_views", "Досмотры"),
                ("sales", "Продажи")
            ]:
                val = to_number(_get(row, table.mapping, key))
                if val is not None:
                    kpi_label, kpi_value = label, val
                    break

        out.append(Placement(
            sheet=sheet.name, source_row=r + 1, channel=channel,
            placement_class=placement_class, placement_class_reason=placement_class_reason,
            platform=platform, platform_canonical=platform_canonical,
            platform_match_reason=platform_match_reason,
            platform_match_confidence=platform_match_confidence,
            platform_status=platform_status,
            platform_needs_review=platform_needs_review,
            platform_suggested_canonical=platform_suggested_canonical,
            is_bonus=is_bonus, research_marker=research_marker,
            research_status=research_status, research_cost=research_cost,
            research_is_dedicated=research_is_dedicated,
            format=fmt,
            buying_model=model, budget=budget, impressions=impressions, tech_reach=reach,
            frequency=frequency, start=s, end=e, target_kpi_label=kpi_label,
            target_kpi_value=kpi_value, is_total=total, raw_text=raw,
            flight_hint=current_flight_hint, common_scope=current_common_scope,
            intervals=intervals, structure_intervals=structure_intervals,
            month_budget=month_budget, month_volume=month_volume,
        ))

        # In standard templates a generic all-media TOTAL closes the media table.
        if is_campaign_total:
            break
    return out


# ------------------------ reach engine ------------------------

@dataclass
class ReachParams:
    universe: float
    lag_visible_share: float = 0.6566358687813219
    cookie_people: float = 2.1125083718004576
    target_affinity: float = 0.65

    # Reachability coefficients are adjustment factors on top of the frequency curve.
    # Default is 100% for every threshold. A coefficient should only be changed when
    # the media plan / benchmark contains an explicit reachability assumption.
    reachability_coefficients: Dict[int, float] = field(default_factory=lambda: {
        2: 1.0,
        3: 1.0,
        4: 1.0,
        5: 1.0,
        6: 1.0,
    })

    # @1+ is the base reach and is always calculated internally.
    # Additional thresholds can be shown/calculated independently up to @6+.
    selected_frequencies: Tuple[int, ...] = (1, 2, 3, 4)
    effective_frequency: int = 3

    def normalized_frequencies(self) -> Tuple[int, ...]:
        freqs = {1}
        for f in self.selected_frequencies:
            f = int(f)
            if 1 <= f <= 6:
                freqs.add(f)
        return tuple(sorted(freqs))

    def reachability(self, freq: int) -> Optional[float]:
        value = self.reachability_coefficients.get(int(freq))
        if value is None:
            return None
        return float(value)


def _unit_interval(value: float, name: str) -> float:
    """Validate a coefficient that must be within [0, 1] without silently clipping it."""
    v = float(value)
    if not math.isfinite(v) or v < 0.0 or v > 1.0:
        raise ValueError(f"{name} должен быть в диапазоне 0–1, получено {value!r}")
    return v


def _strict_reach_probability(people: float, universe: float, name: str) -> float:
    """Convert Reach people to a strict probability and reject impossible source data."""
    if not math.isfinite(float(people)) or float(people) < 0:
        raise ValueError(f"{name}: Reach должен быть неотрицательным конечным числом.")
    if not math.isfinite(float(universe)) or float(universe) <= 0:
        raise ValueError(f"{name}: Universe должен быть положительным конечным числом.")
    p = float(people) / float(universe)
    if p >= 1.0:
        raise ValueError(
            f"{name}: Reach {float(people):.0f} чел. достиг или превысил Universe {float(universe):.0f}. "
            "Такой результат физически невозможен; проверьте исходные данные/Universe."
        )
    return p


def _zt_poisson_lambda(mean_frequency: float) -> float:
    """
    Solve lambda for a zero-truncated Poisson distribution:
        E[X | X>=1] = lambda / (1 - exp(-lambda)) = mean_frequency

    This gives a coherent frequency-only reach curve when no empirical
    reachability benchmark is available: @2+ < @1+, @3+ < @2+, etc.
    """
    f = max(1.0000001, float(mean_frequency))
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


def _poisson_tail(lam: float, threshold: int) -> float:
    """P(X >= threshold) for Poisson(lambda), threshold >= 1."""
    if threshold <= 0:
        return 1.0
    term = math.exp(-lam)
    cumulative = term  # P(X=0)
    for k in range(1, threshold):
        term *= lam / k
        cumulative += term
    return max(0.0, min(1.0, 1.0 - cumulative))


def _simple_frequency_technical_reach(
    tech_reach: float,
    impressions: Optional[float],
    avg_frequency: Optional[float],
    threshold: int,
) -> float:
    """
    Frequency-only mode used when no reachability benchmark is provided.

    @1+ is the technical unique reach from the media plan.
    For @2+...@6+ we derive a strictly decreasing contact-frequency curve
    from the average frequency using a zero-truncated Poisson distribution.

    This avoids the previous impossible case where @1+ == @2+ == @3+
    whenever average frequency happened to be above the selected threshold.
    """
    if threshold <= 1:
        return float(tech_reach)
    if tech_reach <= 0:
        return 0.0

    f: Optional[float] = None
    if avg_frequency is not None and avg_frequency > 0:
        f = float(avg_frequency)
    elif impressions is not None and impressions >= 0:
        f = float(impressions) / float(tech_reach)

    if f is None or not math.isfinite(f):
        # Conservative fallback if only @1+ is known.
        return float(tech_reach) / float(threshold)

    # An exposed user's average contact count should be >=1. If source data
    # are inconsistent and produce <1, keep the curve valid instead of failing.
    f = max(1.000001, f)
    lam = _zt_poisson_lambda(f)
    p1 = _poisson_tail(lam, 1)
    pn = _poisson_tail(lam, threshold)
    ratio = pn / p1 if p1 > 0 else 0.0

    # Numerical guard: every higher threshold must remain below @1+.
    ratio = max(0.0, min(0.999999, ratio))
    return float(tech_reach) * ratio


def calculate_reach(
    tech_reach: Optional[float],
    p: ReachParams,
    impressions: Optional[float] = None,
    avg_frequency: Optional[float] = None,
) -> Dict[str, float]:
    if tech_reach is None or tech_reach < 0:
        return {}
    if p.universe <= 0 or p.cookie_people <= 0 or p.lag_visible_share <= 0:
        return {}

    frequencies = p.normalized_frequencies()
    ms: Dict[int, float] = {}

    # Base @1+.
    ms1 = float(tech_reach) / p.cookie_people
    ms[1] = ms1

    previous = ms1
    for freq in frequencies:
        if freq == 1:
            continue

        # Higher-frequency reach is ALWAYS derived from the contact-frequency curve.
        # Reachability is an optional adjustment to that curve; 100% means "do not
        # additionally reduce it". This prevents the impossible @1+ == @3+ case when
        # reachability defaults are 100%.
        simple_tech = _simple_frequency_technical_reach(
            float(tech_reach),
            impressions,
            avg_frequency,
            freq,
        )
        coefficient = p.reachability(freq)
        coefficient = 1.0 if coefficient is None else _unit_interval(coefficient, f"Достижимость @{freq}+")
        value = (simple_tech / p.cookie_people) * coefficient
        # Monotonic guard: each higher threshold must be strictly below the previous one.
        value = min(value, previous * 0.999999)
        ms[freq] = max(0.0, value)
        previous = ms[freq]

    corrected = {k: v / p.lag_visible_share for k, v in ms.items()}
    target = {k: v * p.target_affinity for k, v in corrected.items()}
    pct = {k: v / p.universe for k, v in target.items()}

    out: Dict[str, float] = {}
    for k in sorted(ms):
        out[f"ms_{k}p"] = ms[k]
        out[f"corrected_{k}p"] = corrected[k]
        out[f"target_{k}p"] = target[k]
        out[f"target_pct_{k}p"] = pct[k]
    return out


def calculate_reach_from_target_1p(
    target_reach_1p: Optional[float],
    p: ReachParams,
    impressions: Optional[float] = None,
    avg_frequency: Optional[float] = None,
) -> Dict[str, float]:
    """
    Fallback for templates that explicitly contain Reach people @1+ per flight but do not
    expose a reliable campaign-level technical Reach UU. @1+ is source data; higher
    frequencies use the same reachability/frequency curve as the main engine.
    """
    if target_reach_1p is None or target_reach_1p < 0 or p.universe <= 0:
        return {}
    target1 = float(target_reach_1p)
    _strict_reach_probability(target1, p.universe, "Источник Reach @1+")
    freqs = p.normalized_frequencies()
    targets: Dict[int, float] = {1: target1}
    previous = target1
    for freq in freqs:
        if freq == 1:
            continue
        # The source @1+ stays authoritative; @2+...@6+ are derived from a coherent
        # frequency curve and only then adjusted by reachability. A 100% coefficient
        # therefore preserves the curve instead of cloning @1+.
        f = avg_frequency
        if f is None and impressions is not None and target1 > 0:
            # Weak fallback only when no technical-frequency estimate is available.
            f = max(1.0, impressions / max(target1, 1.0))
        f = max(1.000001, float(f or 1.0))
        lam = _zt_poisson_lambda(f)
        p1 = _poisson_tail(lam, 1)
        pn = _poisson_tail(lam, freq)
        ratio = pn / p1 if p1 > 0 else 0.0
        coef = p.reachability(freq)
        coef = 1.0 if coef is None else _unit_interval(coef, f"Достижимость @{freq}+")
        value = target1 * ratio * coef
        value = min(value, previous * 0.999999)
        targets[freq] = max(0.0, value)
        previous = targets[freq]
    out: Dict[str, float] = {}
    for k in sorted(targets):
        out[f"target_{k}p"] = targets[k]
        out[f"target_pct_{k}p"] = targets[k] / p.universe
    return out


def combine_reach_union(
    reach_sets: Iterable[Dict[str, float]],
    universe: float,
    coefficient: float = 1.0,
    frequencies: Optional[Iterable[int]] = None,
) -> Dict[str, float]:
    """
    Combine already-unique Reach sets on one audience universe without arithmetic summing.

    Old logic used SUM(Reach) * coefficient. With several flights this can exceed the
    audience universe (for example 3 x ~60% * 0.85 > 100%). Reach is a union, not an
    additive metric.

    We first calculate the bounded union probability:
        P(union) = 1 - PRODUCT(1 - P_i)
    and only then apply the selected conservative intersection coefficient.
    This preserves the existing meaning of the coefficient as a discount for additional
    overlap while making >100% mathematically impossible by construction.
    """
    items = [r for r in reach_sets if r]
    if not items or universe <= 0:
        return {}
    coef = _unit_interval(coefficient, "Коэффициент пересечения")
    freqs = tuple(int(x) for x in (frequencies or (1, 2, 3, 4, 5, 6)))
    out: Dict[str, float] = {}
    previous: Optional[float] = None

    for freq in sorted(set(freqs)):
        key = f"target_{freq}p"
        vals = [r.get(key) for r in items]
        if any(v is None for v in vals):
            continue

        probs = [
            _strict_reach_probability(float(v), float(universe), f"Reach @{freq}+")
            for v in vals
        ]
        union_prob = 1.0 - math.prod(1.0 - p for p in probs)
        combined_prob = union_prob * coef
        people = combined_prob * float(universe)

        if combined_prob >= 1.0:
            raise ValueError(f"Объединенный Reach @{freq}+ достиг или превысил 100%.")
        if previous is not None:
            if previous > 0 and people >= previous:
                raise ValueError(
                    f"Объединенный Reach @{freq}+ не ниже охвата на меньшей частоте. "
                    "Проверьте входные frequency/reachability данные."
                )
            if previous == 0 and people > 0:
                raise ValueError(
                    f"Объединенный Reach @{freq}+ появился после нулевого охвата на меньшей частоте."
                )
        out[key] = people
        out[f"target_pct_{freq}p"] = combined_prob
        previous = people

    return out


def apply_reach(plan: ParsedPlan, params: ReachParams, prefer_flight_universe: bool = True) -> None:
    for x in plan.placements:
        row_params = params
        if prefer_flight_universe:
            info = plan.flight_info(x.flight)
            if info is not None and info.universe is not None and info.universe > 0:
                row_params = ReachParams(
                    universe=float(info.universe),
                    lag_visible_share=params.lag_visible_share,
                    cookie_people=params.cookie_people,
                    target_affinity=params.target_affinity,
                    reachability_coefficients=dict(params.reachability_coefficients),
                    selected_frequencies=tuple(params.selected_frequencies),
                    effective_frequency=params.effective_frequency,
                )
        if _reach_allowed_for_row(plan, x):
            x.reach = calculate_reach(
                x.tech_reach,
                row_params,
                impressions=x.impressions,
                avg_frequency=x.frequency,
            )
        else:
            x.reach = {}



@dataclass
class FlightInfo:
    id: str
    label: str
    sheet: str
    period_start: Optional[dt.date] = None
    period_end: Optional[dt.date] = None
    ta_name: str = ""
    universe: Optional[float] = None
    universe_source: str = ""
    intervals: List[Tuple[dt.date, dt.date]] = field(default_factory=list)
    source_reach_people_1p: Optional[float] = None
    source_reach_pct_1p: Optional[float] = None
    is_common: bool = False
    # Keep the source campaign identity at flight level when one plan/line is split
    # into campaigns named by different periods (e.g. May, Jul-Aug, Sep-Nov).
    campaign: str = ""


@dataclass
class IntersectionBreakdown:
    selected_flights: Tuple[str, ...]
    audience_size: float
    audience_category: str
    audience_coef_auto: float
    complexity: str
    complexity_coef_auto: float
    platform_count: int
    platform_coef_auto: float
    rows_per_platform: float
    rows_coef_auto: float
    channel_count: int
    channel_coef_auto: float
    period_situation: str
    period_coef_auto: float
    auto_product: float
    applied_product: float
    mode: str = "auto"
    applied_factors: Dict[str, float] = field(default_factory=dict)
    platform_detection: str = ""
    rows_detection: str = ""
    channel_detection: str = ""


@dataclass
class CombinedSummary:
    selected_flights: Tuple[str, ...]
    budget: Optional[float]
    impressions: Optional[float]
    tech_reach: Optional[float]
    frequency: Optional[float]
    reach: Dict[str, float]
    performance: List[Tuple[str, float]] = field(default_factory=list)
    intersection: Optional[IntersectionBreakdown] = None
    warning: str = ""


@dataclass
class ParsedPlan:
    path: Path
    placements: List[Placement]
    sheet_meta: Dict[str, SheetMeta]
    tables: List[TableDef]
    universe: Optional[float]
    period_start: Optional[dt.date]
    period_end: Optional[dt.date]
    warnings: List[str]
    flights: List[FlightInfo] = field(default_factory=list)
    display_name: str = ""
    brand: str = ""
    campaign: str = ""
    line: str = ""

    def flight_ids(self) -> List[str]:
        return [f.id for f in self.flights]

    def flight_info(self, flight_id: str) -> Optional[FlightInfo]:
        return next((f for f in self.flights if f.id == flight_id), None)

    def detail_rows(self, selected_flights: Optional[Iterable[str]] = None) -> List[Placement]:
        selected = set(selected_flights) if selected_flights is not None else None
        return [x for x in self.placements if not x.is_total and (selected is None or x.flight in selected)]

    def total_rows(self, selected_flights: Optional[Iterable[str]] = None) -> List[Placement]:
        selected = set(selected_flights) if selected_flights is not None else None
        return [x for x in self.placements if x.is_total and (selected is None or x.flight in selected)]

    def campaign_total(self, selected_flights: Optional[Iterable[str]] = None) -> Optional[Placement]:
        totals = [x for x in self.total_rows(selected_flights) if x.tech_reach is not None]
        if not totals:
            return None
        # Campaign total must be an explicit all-media/summary total, not just the largest
        # channel subtotal. This prevents OLV TOTAL from being mislabeled as campaign Reach.
        neutral = [x for x in totals if x.channel in {"TOTAL", "Other"} or "summary" in norm(x.sheet) or "total digital" in norm(x.raw_text) or "grand total" in norm(x.raw_text) or "all digital" in norm(x.raw_text)]
        if neutral:
            return max(neutral, key=lambda x: ((x.budget or 0), (x.tech_reach or 0)))
        # If the whole plan contains only one channel, its total is also the campaign total.
        channels = {x.channel for x in self.detail_rows(selected_flights) if x.channel and x.channel != "Other"}
        if len(channels) == 1:
            return max(totals, key=lambda x: ((x.budget or 0), (x.tech_reach or 0)))
        return None

    def budget_total(self, selected_flights: Optional[Iterable[str]] = None) -> Optional[float]:
        selected = list(selected_flights) if selected_flights is not None else None
        if selected is not None and len(selected) > 1:
            total = 0.0
            seen = False
            for fid in selected:
                ct = self.flight_total(fid)
                if ct is not None and ct.budget is not None:
                    total += ct.budget
                    seen = True
                else:
                    vals = [x.budget for x in self.detail_rows([fid]) if x.budget is not None]
                    if vals:
                        total += sum(vals)
                        seen = True
            return total if seen else None
        campaign = self.campaign_total(selected)
        if campaign is not None and campaign.budget is not None:
            return campaign.budget
        details = [x.budget for x in self.detail_rows(selected) if x.budget is not None]
        if details:
            return sum(details)
        totals = [x.budget for x in self.total_rows(selected) if x.budget is not None]
        return max(totals) if totals else None

    def flight_total(self, flight_id: str) -> Optional[Placement]:
        totals = [x for x in self.total_rows([flight_id]) if x.tech_reach is not None]
        if not totals:
            return None
        neutral = [x for x in totals if x.channel in {"TOTAL", "Other"} or "total digital" in norm(x.raw_text) or "grand total" in norm(x.raw_text)]
        if neutral:
            return max(neutral, key=lambda x: ((x.budget or 0), (x.tech_reach or 0)))
        channels = {x.channel for x in self.detail_rows([flight_id]) if x.channel and x.channel != "Other"}
        if len(channels) == 1:
            return max(totals, key=lambda x: ((x.budget or 0), (x.tech_reach or 0)))
        return None

    def channel_total(self, flight_id: str, channel: str) -> Optional[Placement]:
        totals = [x for x in self.total_rows([flight_id]) if x.channel == channel and x.tech_reach is not None]
        if totals:
            return max(totals, key=lambda x: ((x.budget or 0), (x.tech_reach or 0)))
        rows = [x for x in self.detail_rows([flight_id]) if x.channel == channel and x.tech_reach is not None]
        if len(rows) == 1:
            return rows[0]
        return None


@dataclass(frozen=True)
class MonthNode:
    year: int
    month: int
    key: str
    period_start: dt.date
    period_end: dt.date
    budget: Optional[float] = None
    volume: Optional[float] = None
    source_budget: bool = False
    source_volume: bool = False


@dataclass
class PlacementNode:
    id: str
    placement: Placement
    months: List[MonthNode] = field(default_factory=list)


@dataclass
class FlightNode:
    id: str
    label: str
    info: FlightInfo
    placements: List[PlacementNode] = field(default_factory=list)


@dataclass
class PlanNode:
    key: str
    label: str
    line: str
    brand: str
    campaign: str
    flights: List[FlightNode] = field(default_factory=list)


def _month_pairs_for_interval(a: dt.date, b: dt.date) -> List[Tuple[int, int]]:
    a, b = min(a, b), max(a, b)
    out: List[Tuple[int, int]] = []
    y, m = a.year, a.month
    while (y, m) <= (b.year, b.month):
        out.append((y, m))
        if m == 12:
            y, m = y + 1, 1
        else:
            m += 1
    return out


def placement_month_nodes(x: Placement, flight: Optional[FlightInfo] = None, default_year: int = 2026) -> List[MonthNode]:
    """Expose the canonical last level: Placement -> Month.

    The function never invents a monthly budget/volume split. Source monthly values are
    attached only where the workbook actually contains them; intervals still produce
    active month nodes with ``budget=None`` / ``volume=None`` when no monthly source split
    exists. This keeps structure separate from later planning assumptions.
    """
    intervals = list(x.intervals or [])
    if not intervals and x.start and x.end:
        intervals = [(x.start, x.end)]
    if not intervals and flight is not None:
        intervals = list(flight.intervals or [])
        if not intervals and flight.period_start and flight.period_end:
            intervals = [(flight.period_start, flight.period_end)]

    pairs: List[Tuple[int, int]] = []
    for a, b in intervals:
        pairs.extend(_month_pairs_for_interval(a, b))
    pairs = list(dict.fromkeys(pairs))

    source_months = sorted(set(x.month_budget) | set(x.month_volume))
    fallback_year = (
        x.start.year if x.start else
        (flight.period_start.year if flight and flight.period_start else
         (intervals[0][0].year if intervals else default_year))
    )
    present_month_numbers = {m for _y, m in pairs}
    for m in source_months:
        if m not in present_month_numbers:
            pairs.append((fallback_year, m))
    pairs = sorted(set(pairs))

    # Month-number dictionaries originate from annual media-plan templates. If a plan
    # ever spans two years with the same month number, the source split is ambiguous;
    # do not duplicate the same budget into both years.
    month_occurrence = Counter(m for _y, m in pairs)
    out: List[MonthNode] = []
    for year, month in pairs:
        month_start = dt.date(year, month, 1)
        month_end = dt.date(year, month, calendar.monthrange(year, month)[1])
        active_parts = []
        for a, b in intervals:
            lo, hi = min(a, b), max(a, b)
            if month_start <= hi and month_end >= lo:
                active_parts.append((max(month_start, lo), min(month_end, hi)))
        if active_parts:
            period_start = min(a for a, _ in active_parts)
            period_end = max(b for _, b in active_parts)
        else:
            period_start, period_end = month_start, month_end
        unique_source_month = month_occurrence[month] == 1
        has_budget = unique_source_month and month in x.month_budget
        has_volume = unique_source_month and month in x.month_volume
        out.append(MonthNode(
            year=year, month=month, key=f"{year:04d}-{month:02d}",
            period_start=period_start, period_end=period_end,
            budget=x.month_budget.get(month) if has_budget else None,
            volume=x.month_volume.get(month) if has_volume else None,
            source_budget=has_budget, source_volume=has_volume,
        ))
    return out


def build_plan_node(plan: ParsedPlan) -> PlanNode:
    """Build the canonical in-memory hierarchy: Plan -> Flight -> Placement -> Month."""
    flights: List[FlightNode] = []
    for f in plan.flights:
        pnodes: List[PlacementNode] = []
        for x in sorted(plan.detail_rows([f.id]), key=lambda r: (r.sheet, r.source_row)):
            source_id = re.sub(r"[^0-9a-zа-я]+", "-", norm(x.sheet), flags=re.IGNORECASE).strip("-") or "sheet"
            pid = f"{f.id}:{source_id}:{x.source_row + 1}"
            pnodes.append(PlacementNode(pid, x, placement_month_nodes(x, f)))
        flights.append(FlightNode(f.id, f.label, f, pnodes))
    key = _line_key(plan.line or plan.display_name or plan.path.stem)
    return PlanNode(key=key, label=plan.display_name, line=plan.line, brand=plan.brand, campaign=plan.campaign, flights=flights)


def _dedupe_internal(rows: List[Placement]) -> List[Placement]:
    """
    Dedupe parser duplicates without merging two different physical source rows.
    Internal-flight templates can contain two genuinely different placements with
    identical platform/format/budget/month values, so the generic semantic signature
    is too aggressive here.
    """
    seen = set()
    out: List[Placement] = []
    for x in rows:
        key = (norm(x.sheet), int(x.source_row), norm(x.flight), x.is_total)
        if key in seen:
            continue
        seen.add(key)
        out.append(x)
    return out


def _dedupe(rows: List[Placement]) -> List[Placement]:
    seen = set()
    out = []
    for x in rows:
        sig = x.signature()
        if sig in seen:
            continue
        seen.add(sig)
        out.append(x)
    return out


def _extract_flight_number(sheet_name: str) -> Optional[int]:
    t = norm(sheet_name)
    patterns = [
        r"(?:flight|флайт|wave|волна)\s*[-_ ]*(\d+)",
        r"(?:^|\b)(\d+)\s*(?:flight|флайт|wave|волна)(?:\b|$)",
        r"(?:^|\b)f\s*[-_ ]?(\d+)(?:\b|$)",
    ]
    for pat in patterns:
        m = re.search(pat, t)
        if m:
            return int(m.group(1))
    return None


def _looks_like_summary_sheet(name: str) -> bool:
    t = norm(name)
    return bool(re.search(r"(^|\b)(summary|свод|сводная|dashboard|annual total|year total|итоги)(\b|$)", t))


def _explicit_service_sheet_name(name: str) -> bool:
    """Strong sheet-name signals that describe controls/calculations, not placements."""
    t = norm(name)
    patterns = (
        r"^(?:budget|budgets?)\s+(?:channels?|by channels?)$",
        r"^(?:бюджет|бюджеты)\s+(?:каналов|по каналам)$",
        r"^(?:channel|channels)\s+budget$",
        # Strong reference/reporting names stay service tabs even if their cells
        # accidentally resemble a media-plan table.
        r"^(?:.*\s+)?(?:reference|references|ref|справоч\w*|справка|readme|инструкц\w*)$",
        r"^(?:отчет|отчёт|report|reports|результат\w*|results?)$",
        r"^(?:список\s+городов|cities|city\s+list|geo\s+list)$",
    )
    return any(re.search(p, t, flags=re.IGNORECASE) for p in patterns)


def _explicit_discard_sheet_name(name: str) -> bool:
    """Explicit user-facing draft/delete markers are never an active media plan."""
    t = norm(name)
    return bool(re.search(
        r"(?:^|\b)(?:draft|чернов\w*|to\s+delete|delete\s+me|удалить|на\s+удаление)(?:\b|$)",
        t, flags=re.IGNORECASE,
    ))


def _looks_like_reporting_sheet(sheet: SheetData) -> bool:
    """Detect PLAN/FACT reporting tabs that can superficially resemble a media table."""
    parts: List[str] = []
    for row in sheet.matrix[:35]:
        for value in row[:80]:
            if value not in (None, ""):
                parts.append(norm(value))
    text = " | ".join(parts)
    has_fact = bool(re.search(r"(?:^|\W)fact(?:\W|$)|факт", text, flags=re.IGNORECASE))
    has_delta = "delta" in text or "дельта" in text
    has_report = "report period" in text or "reporting period" in text or "actual budget" in text
    return bool(has_fact and has_delta and has_report)


def _sheet_scenario_name(name: str) -> str:
    """Return an explicit scenario marker when a workbook contains parallel plan options."""
    t = norm(name)
    if re.search(r"(?:^|\b)(?:реко|рекоменд\w*|reco|recommend(?:ed|ation)?)(?:\b|$)", t):
        return "Реко"
    mm = re.search(r"(?:^|\b)(\d+(?:[.,]\d+)?)\s*(?:млн|million|mln)(?:\b|$)", t)
    if mm:
        return f"{mm.group(1).replace(',', '.')} млн"
    mm = re.search(r"(?:^|\b)(?:scenario|сценарий|option|вариант)\s*[-_ ]*([0-9a-zа-я]+)(?:\b|$)", t)
    if mm:
        return f"Сценарий {mm.group(1)}"
    return ""


def _normalize_audience_name(value: str) -> str:
    t = norm(value)
    # Treat Cyrillic ВС and Latin BC as the same socio-demographic suffix.
    t = re.sub(r"\bвс\b", "bc", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t


def _load_audience_reference() -> Dict[str, float]:
    path = Path(__file__).with_name("audiences.json")
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return {
            _normalize_audience_name(str(item.get("name", ""))): float(item["universe"])
            for item in data
            if item.get("name") and item.get("universe") is not None
        }
    except Exception:
        return {}


def _resolve_audience_universe(ta_name: str, library: Dict[str, float]) -> Optional[float]:
    key = _normalize_audience_name(ta_name)
    if not key:
        return None
    if key in library:
        return library[key]
    # Conservative fuzzy fallback: exact library name contained in a longer label
    # (e.g. "Ж 25-45 BC LTV"). Prefer the longest matching key.
    candidates = [(k, v) for k, v in library.items() if k and (k in key or key in k)]
    if candidates:
        candidates.sort(key=lambda kv: len(kv[0]), reverse=True)
        return candidates[0][1]
    return None


def _platform_key(value: str) -> str:
    text = clean_display(value).split("\n", 1)[0]
    t = norm(text)
    key = re.sub(r"[^a-zа-я0-9]+", "", t)

    # Agreed alias for intersection/subtotal logic:
    # VK, VK Видео and VK Video are the same platform, only different formats.
    vk_aliases = {
        "vk", "vkvideo", "vkвидео", "вк", "вквидео", "vkontakte",
        "вконтакте", "вконтактеvideo", "вконтактевидео",
    }
    if key in vk_aliases or key.startswith("vkvideo") or key.startswith("вквидео"):
        return "vk"

    # Normalize spelling differences between templates: "Media Today" == "Mediatoday".
    return key


def _fallback_platform_overlap(platform_count: int) -> float:
    """Fallback for missing CHANNEL subtotals only, per agreed rule."""
    if platform_count <= 1:
        return 1.0
    if platform_count == 2:
        return 0.90
    if platform_count >= 3:
        return 0.80
    return 1.0


def _synthesize_missing_channel_totals(rows: List[Placement], flight: FlightInfo) -> List[Placement]:
    """
    If a flight has no subtotal row for a channel, synthesize one.
    Additive metrics are summed; technical reach is sum(Reach UU) × platform overlap:
    1 platform=1.0, 2=0.9, 3+=0.8. Frequency = Impressions / Reach UU.
    Existing explicit/unlabeled subtotals are NEVER overwritten.
    """
    out = list(rows)
    details = [x for x in rows if not x.is_total]
    channels: List[str] = []
    for x in details:
        if x.channel and x.channel not in {"Other", "TOTAL"} and x.channel not in channels:
            channels.append(x.channel)

    for channel in channels:
        existing = [x for x in rows if x.is_total and x.channel == channel]
        if existing:
            continue
        children = [x for x in details if x.channel == channel]
        if not children:
            continue

        budget_vals = [x.budget for x in children if x.budget is not None]
        imp_vals = [x.impressions for x in children if x.impressions is not None]
        reach_vals = [x.tech_reach for x in children if x.tech_reach is not None]
        platforms = {_platform_key(x.platform) for x in children if _platform_key(x.platform)}
        platform_count = max(1, len(platforms))
        overlap = _fallback_platform_overlap(platform_count)

        budget = sum(budget_vals) if budget_vals else None
        impressions = sum(imp_vals) if imp_vals else None
        tech_reach = (sum(reach_vals) * overlap) if reach_vals else None
        frequency = (impressions / tech_reach) if impressions is not None and tech_reach not in (None, 0) else None

        models = {x.buying_model for x in children if x.buying_model != "OTHER"}
        model = next(iter(models)) if len(models) == 1 else "OTHER"
        kpi_label = "Показы" if model == "CPM" else ""
        kpi_value = impressions if model == "CPM" else None

        starts = [x.start for x in children if x.start]
        ends = [x.end for x in children if x.end]
        source_row = max((x.source_row for x in rows), default=0) + len(out) + 1
        out.append(Placement(
            sheet=flight.sheet,
            source_row=source_row,
            flight=flight.id,
            flight_label=flight.label,
            channel=channel,
            platform="",
            format="",
            buying_model=model,
            budget=budget,
            impressions=impressions,
            tech_reach=tech_reach,
            frequency=frequency,
            start=min(starts) if starts else flight.period_start,
            end=max(ends) if ends else flight.period_end,
            target_kpi_label=kpi_label,
            target_kpi_value=kpi_value,
            is_total=True,
            synthetic_total=True,
            raw_text=f"AUTO SUBTOTAL {channel}: {platform_count} platform(s), overlap={overlap:.2f}",
        ))
    return out



def _month_overlaps_intervals(month: int, intervals: Sequence[Tuple[dt.date, dt.date]], year: int) -> bool:
    if not intervals:
        return False
    a = dt.date(year, month, 1)
    b = dt.date(year, month, calendar.monthrange(year, month)[1])
    return any(a <= ie and b >= is_ for is_, ie in intervals)


def _split_weight(values: Dict[int, float], months: Sequence[int], fallback_months: Sequence[int]) -> float:
    if values:
        total = sum(values.values())
        part = sum(values.get(m, 0.0) for m in months)
        if abs(total) > 1e-12:
            return part / total
    if fallback_months:
        return len(set(months)) / max(1, len(set(fallback_months)))
    return 1.0


def _nearest_flight_for_month(month: int, meta: SheetMeta, year: int) -> Optional[int]:
    """Return the nearest declared flight to a month that sits outside all flight periods."""
    best: Optional[Tuple[int, int]] = None
    month_idx = year * 12 + month
    for n, intervals in meta.flight_intervals.items():
        for a, b in intervals:
            a_idx = a.year * 12 + a.month
            b_idx = b.year * 12 + b.month
            if a_idx <= month_idx <= b_idx:
                return n
            dist = min(abs(month_idx - a_idx), abs(month_idx - b_idx))
            cand = (dist, n)
            if best is None or cand < best:
                best = cand
    return best[1] if best else None


def _split_placement_for_internal_flights(
    x: Placement,
    meta: SheetMeta,
    warnings: Optional[List[str]] = None,
) -> Dict[Any, Placement]:
    """Partition one physical row into source flights using monthly plan blocks."""
    flight_nums = sorted(meta.flight_intervals)
    if not flight_nums:
        if x.common_scope:
            return {"AON": x}
        if x.flight_hint is not None:
            return {int(x.flight_hint): x}
        return {1: x}

    active_months = sorted(set(x.month_budget) | set(x.month_volume))
    bucket_months: Dict[Any, List[int]] = defaultdict(list)

    if x.common_scope:
        bucket_months["AON"] = active_months
    elif x.flight_hint in flight_nums:
        bucket_months[int(x.flight_hint)] = active_months
    elif active_months:
        year = meta.period_start.year if meta.period_start else next(iter(meta.flight_intervals.values()))[0][0].year
        for month in active_months:
            matched = [n for n in flight_nums if _month_overlaps_intervals(month, meta.flight_intervals.get(n, []), year)]
            if len(matched) == 1:
                bucket_months[matched[0]].append(month)
            elif len(matched) > 1:
                # Overlapping source flights are ambiguous; assign to the earliest one once.
                bucket_months[matched[0]].append(month)
            else:
                # A normal media row outside the declared flight periods is almost always
                # a stale header/date discrepancy. Do not turn it into fake Always-on:
                # assign it to the nearest flight and surface the conflict explicitly.
                nearest = _nearest_flight_for_month(month, meta, year)
                if nearest is not None:
                    bucket_months[nearest].append(month)
                    if warnings is not None:
                        month_name = {1:'январь',2:'февраль',3:'март',4:'апрель',5:'май',6:'июнь',7:'июль',8:'август',9:'сентябрь',10:'октябрь',11:'ноябрь',12:'декабрь'}.get(month, str(month))
                        warnings.append(
                            f"{x.sheet}, строка {x.source_row + 1}: {month_name} есть в помесячном плане, "
                            f"но не входит в заявленные периоды флайтов; месяц отнесён к ближайшему Flight {nearest}. "
                            "Проверьте период в шапке медиаплана."
                        )
                else:
                    bucket_months["AON"].append(month)
    elif len(flight_nums) == 1:
        bucket_months[flight_nums[0]] = []
    else:
        bucket_months["AON"] = []

    # Remove empty AON when an explicit flight owns the row.
    bucket_months = {k: v for k, v in bucket_months.items() if v or not active_months}
    if not bucket_months:
        bucket_months[x.flight_hint or flight_nums[0]] = active_months

    result: Dict[Any, Placement] = {}
    for key, months in bucket_months.items():
        budget_w = _split_weight(x.month_budget, months, active_months)
        volume_w = _split_weight(x.month_volume, months, active_months)
        metric_w = volume_w if x.month_volume else budget_w
        if len(bucket_months) == 1:
            budget_w = volume_w = metric_w = 1.0

        intervals: List[Tuple[dt.date, dt.date]] = []
        if months:
            year = meta.period_start.year if meta.period_start else default_year_from_intervals(meta.flight_intervals)
            intervals = _months_to_intervals(months, year)
        elif key != "AON" and isinstance(key, int):
            intervals = list(meta.flight_intervals.get(key, []))
        elif x.intervals:
            intervals = list(x.intervals)

        budget = x.budget * budget_w if x.budget is not None else None
        impressions = x.impressions * volume_w if x.impressions is not None else None
        tech_reach = x.tech_reach * metric_w if x.tech_reach is not None else None
        kpi_value = x.target_kpi_value
        if kpi_value is not None:
            if x.buying_model == "CPM":
                kpi_value = impressions
            else:
                kpi_value = kpi_value * metric_w
        frequency = x.frequency
        if impressions is not None and tech_reach not in (None, 0):
            frequency = impressions / tech_reach

        clone = replace(
            x,
            budget=budget,
            impressions=impressions,
            tech_reach=tech_reach,
            frequency=frequency,
            start=min((a for a, _ in intervals), default=x.start),
            end=max((b for _, b in intervals), default=x.end),
            target_kpi_value=kpi_value,
            intervals=intervals,
            month_budget={m: x.month_budget[m] for m in months if m in x.month_budget},
            month_volume={m: x.month_volume[m] for m in months if m in x.month_volume},
            raw_text=x.raw_text + f" | AUTO FLIGHT SPLIT {key}",
        )
        result[key] = clone
    return result


def default_year_from_intervals(mapping: Dict[int, List[Tuple[dt.date, dt.date]]], fallback: int = 2026) -> int:
    for intervals in mapping.values():
        if intervals:
            return intervals[0][0].year
    return fallback


def _split_internal_sheet_rows(
    meta: SheetMeta,
    rows: List[Placement],
    warnings: Optional[List[str]] = None,
) -> Dict[Any, List[Placement]]:
    """Return rows partitioned into Flight N and optional AON for one worksheet."""
    groups: Dict[Any, List[Placement]] = defaultdict(list)
    for x in rows:
        # The generic campaign TOTAL belongs to the whole sheet and cannot be copied into
        # every flight. Per-flight/channel totals are synthesized from split detail rows.
        if x.is_total and x.channel == "TOTAL":
            continue
        parts = _split_placement_for_internal_flights(x, meta, warnings)
        for key, clone in parts.items():
            groups[key].append(clone)
    return groups


@dataclass
class MediaPlanGroup:
    id: str
    label: str
    sheet_names: Tuple[str, ...]
    brand: str = ""
    campaign: str = ""
    line: str = ""


@dataclass
class SheetClassification:
    name: str
    role: str
    reason: str = ""
    has_media_table: bool = False
    brand: str = ""
    campaign: str = ""
    line: str = ""
    variant_family: str = ""
    preferred_variant: bool = True


@dataclass
class VariantFamily:
    id: str
    base_name: str
    sheet_names: Tuple[str, ...]
    preferred_sheet: str
    reason: str = "explicit version markers"


@dataclass
class WorkbookStructure:
    path: Path
    plans: List[MediaPlanGroup]
    sheets: List[SheetClassification]
    variants: List[VariantFamily] = field(default_factory=list)


_MONTH_WORDS = (
    r"январ(?:ь|я)?|янв|феврал(?:ь|я)?|фев|март(?:а)?|мар|апрел(?:ь|я)?|апр|май|мая|"
    r"июн(?:ь|я)?|июл(?:ь|я)?|август(?:а)?|авг|сентябр(?:ь|я)?|сент|сен|"
    r"октябр(?:ь|я)?|окт|ноябр(?:ь|я)?|ноя|дек(?:абр(?:ь|я)?)?|"
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|jul(?:y)?|"
    r"aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)


def _campaign_line_name(value: Any) -> str:
    """Return a stable plan/line name while removing flight-only period suffixes.

    Example: ``Бреф Сила Актив Июль-Август'26`` -> ``Бреф Сила Актив``.
    The function intentionally removes only strong temporal / flight suffixes; other
    campaign wording remains part of the identity so two genuinely different lines
    are not merged merely because they share a brand.
    """
    s = clean_display(value).strip()
    if not s:
        return ""
    s = re.sub(r"(?i)^\s*(?:рк|campaign|кампания)\s*[:\-]?\s*", "", s).strip()
    # Strong trailing period suffix. The year is optional because many live MPs use
    # short labels such as "Тафт Уход Сен-Окт" / "Ноя-Дек".
    month_suffix = rf"\s+(?:{_MONTH_WORDS})(?:\s*[-–—]\s*(?:{_MONTH_WORDS}))?(?:\s*[’']?\s*(?:20)?\d{{2}})?\s*$"
    s = re.sub(month_suffix, "", s, flags=re.IGNORECASE).strip()
    s = re.sub(r"(?i)\s+(?:q[1-4]|[1-4]\s*(?:кв\.?|квартал\w*))\s*[’']?\s*(?:20)?\d{2}\s*$", "", s).strip()
    s = re.sub(r"(?i)\s+(?:flight|флайт|wave|волна)\s*[-_ ]*\d+\s*$", "", s).strip()
    # Date ranges used as a campaign suffix (01.07-16.08.26, 15.09.26–02.11.26).
    s = re.sub(r"\s+\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\s*[-–—]\s*\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?\s*$", "", s).strip()
    return re.sub(r"\s+", " ", s).strip(" -_;,")


def _meta_line_name(meta: SheetMeta) -> str:
    return clean_display(meta.line) or _campaign_line_name(meta.campaign)


def _line_key(value: Any) -> str:
    t = norm(value)
    t = re.sub(r"[^0-9a-zа-я]+", " ", t, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", t).strip()


def _choose_brand(metas: Sequence[SheetMeta], line_name: str = "") -> str:
    brands = [m.brand for m in metas if m.brand]
    if not brands:
        return ""
    lk = _line_key(line_name)
    # In OMD-origin tabs Client/Brand may contain the advertiser (LAB Industries),
    # while another flight contains the actual brand. Prefer a brand that is visibly
    # present in the stable line name before falling back to majority vote.
    if lk:
        contained = [b for b in brands if _line_key(b) and _line_key(b) in lk]
        if contained:
            return Counter(contained).most_common(1)[0][0]
    return Counter(brands).most_common(1)[0][0]


def _variant_signature(name: str) -> Tuple[str, float, Tuple[str, ...]]:
    """Normalize a sheet name for conservative alternative-version detection."""
    raw = norm(name)
    t = raw
    score = 0.0
    markers: List[str] = []

    def drop(pattern: str, label: str, delta: float) -> None:
        nonlocal t, score
        if re.search(pattern, t, flags=re.IGNORECASE):
            markers.append(label)
            score += delta
            t = re.sub(pattern, " ", t, flags=re.IGNORECASE)

    drop(r"\b(?:approved|утвержд\w*|согласован\w*)\b", "approved", 60)
    drop(r"\b(?:final|финал\w*)\b", "final", 50)
    drop(r"\b(?:update|updated|upd|апдейт|обновлен\w*|обновл\w*)\b", "update", 40)
    # Explicit dated snapshots, e.g. "от 22.05".
    md = re.search(r"\bот\s+(\d{1,2})[._/-](\d{1,2})(?:[._/-](\d{2,4}))?\b", t)
    if md:
        day, month = int(md.group(1)), int(md.group(2))
        year = int(md.group(3)) if md.group(3) else 0
        if 0 < year < 100:
            year += 2000
        markers.append("dated")
        score += 20 + (year * 372 + month * 31 + day) / 1_000_000
        t = t[:md.start()] + " " + t[md.end():]
    vm = re.search(r"(?:^|\b)v(?:er(?:sion)?)?\s*[-_ ]?(\d+)\b", t, flags=re.IGNORECASE)
    if vm:
        markers.append("version")
        score += 10 + int(vm.group(1)) / 100
        t = t[:vm.start()] + " " + t[vm.end():]
    drop(r"\b(?:old|стар\w*|archive|архив\w*|backup|бэкап\w*)\b", "old", -30)
    drop(r"\b(?:draft|чернов\w*)\b", "draft", -25)
    drop(r"\b(?:copy|копия)\b", "copy", -15)
    if re.search(r"\(\s*\d+\s*\)\s*$", t):
        markers.append("copy_index")
        score -= 10
        t = re.sub(r"\(\s*\d+\s*\)\s*$", " ", t)

    # Soft/hard-sign spelling differences frequently occur in Yandex sheet names.
    base = t.replace("ъ", "").replace("ь", "")
    base = re.sub(r"[^0-9a-zа-я]+", " ", base, flags=re.IGNORECASE)
    base = re.sub(r"\s+", " ", base).strip()
    return base, score, tuple(markers)


def discover_workbook_structure(path: str | Path, default_year: int = 2026) -> WorkbookStructure:
    """Discover the canonical top levels: Book -> Plan/line.

    Discovery is deliberately shallow: only the first media-plan area of each sheet is
    read. Heavy reference tabs are classified without loading their entire used range.
    Full rows are parsed only after a specific plan/line is selected.
    """
    path = Path(path)
    records: List[Dict[str, Any]] = []
    with XlsxWorkbook(path) as wb:
        names = wb.sheet_names()
        for order, name in enumerate(names):
            sheet = wb.read_sheet_preview(name, max_rows=360, max_cols=180)
            meta = extract_metadata(sheet, default_year)
            tdefs = find_tables(sheet, meta)
            summary = _looks_like_summary_sheet(name) and len(names) > 1
            explicit_service = _explicit_service_sheet_name(name) or _looks_like_reporting_sheet(sheet)
            explicit_discard = _explicit_discard_sheet_name(name)
            raw_has_media = bool(tdefs)
            has_media = raw_has_media and not summary and not explicit_service and not explicit_discard
            line_name = _meta_line_name(meta)
            records.append({
                "order": order, "name": name, "meta": meta, "tdefs": tdefs,
                "summary": summary, "explicit_service": explicit_service,
                "explicit_discard": explicit_discard, "raw_has_media": raw_has_media,
                "has_media": has_media, "line": line_name,
                "line_key": _line_key(line_name), "scenario": _sheet_scenario_name(name),
            })

    # Detect explicit alternative-version families. A media sheet is only compared to
    # another media sheet inside the same line identity; service/reference tabs may be
    # compared globally because they cannot alter plan calculations.
    families: List[VariantFamily] = []
    variant_members: Dict[str, Tuple[str, bool]] = {}
    buckets: Dict[Tuple[str, str, str], List[Tuple[Dict[str, Any], float, Tuple[str, ...]]]] = defaultdict(list)
    for rec in records:
        base, score, markers = _variant_signature(rec["name"])
        if not base:
            continue
        scope = rec["line_key"] if rec["has_media"] else "__service__"
        kind = "media" if rec["has_media"] else "service"
        buckets[(kind, scope, base)].append((rec, score, markers))

    vf_seq = 1
    for (kind, _scope, base), members in buckets.items():
        if len(members) < 2 or not any(m[2] for m in members):
            continue
        # Avoid declaring differently numbered flight tabs as versions even when a user
        # happens to add a version marker to one of them.
        flight_nums = {_extract_flight_number(m[0]["name"]) for m in members}
        if kind == "media" and len({n for n in flight_nums if n is not None}) > 1:
            continue
        preferred = max(members, key=lambda x: (x[1], -x[0]["order"]))
        family_id = f"V{vf_seq}"
        vf_seq += 1
        ordered = sorted(members, key=lambda x: x[0]["order"])
        families.append(VariantFamily(
            family_id, base, tuple(x[0]["name"] for x in ordered), preferred[0]["name"]
        ))
        for rec, _score, _markers in members:
            variant_members[rec["name"]] = (family_id, rec["name"] == preferred[0]["name"])

    # Build active media candidates. Non-preferred explicit media versions are retained
    # in diagnostics but excluded from calculations to prevent double counting.
    active = []
    classifications: List[SheetClassification] = []
    for rec in records:
        name, meta = rec["name"], rec["meta"]
        vf = variant_members.get(name)
        if rec.get("explicit_discard"):
            role, reason = "alternative_version", "explicit draft/delete sheet"
        elif rec.get("explicit_service"):
            role, reason = "service", "explicit reporting/budget-control sheet"
        elif rec["summary"]:
            role, reason = "summary", "summary/aggregate sheet"
        elif rec["has_media"]:
            if vf and not vf[1]:
                role, reason = "alternative_version", "non-preferred explicit media-plan version"
            else:
                role, reason = "media", "usable media table"
                active.append(rec)
        else:
            if vf and not vf[1]:
                role, reason = "alternative_version", "possible older/duplicate service-tab version"
            else:
                role, reason = "service", "no usable media placement table"
        classifications.append(SheetClassification(
            name=name, role=role, reason=reason, has_media_table=bool(rec.get("raw_has_media")),
            brand=meta.brand, campaign=meta.campaign, line=rec["line"],
            variant_family=vf[0] if vf else "", preferred_variant=(vf[1] if vf else True),
        ))

    if not active:
        return WorkbookStructure(path, [], classifications, families)

    # Canonical plan/line grouping. Period-only differences in Campaign name collapse to
    # one line; substantive wording remains distinct. This fixes books where each flight
    # has its own campaign date suffix while preserving genuinely separate products.
    grouped: Dict[Any, List[Dict[str, Any]]] = defaultdict(list)
    unidentified: List[Dict[str, Any]] = []

    # Parallel budget/recommendation scenarios must not be arithmetically summed.
    # If one logical line contains more than one explicit scenario marker, keep a
    # separate top-level plan per scenario while still merging years/flights inside it.
    scenarios_by_line: Dict[str, set[str]] = defaultdict(set)
    for rec in active:
        if rec["line_key"] and rec.get("scenario"):
            scenarios_by_line[rec["line_key"]].add(_line_key(rec["scenario"]))

    for rec in active:
        meta = rec["meta"]
        if rec["line_key"]:
            scenario = rec.get("scenario") or ""
            scenario_key = _line_key(scenario)
            if scenario_key and len(scenarios_by_line.get(rec["line_key"], set())) > 1:
                grouped[("line_scenario", rec["line_key"], scenario_key)].append(rec)
            else:
                grouped[("line", rec["line_key"])].append(rec)
        elif meta.brand or meta.campaign:
            grouped[("identity", norm(meta.brand), norm(meta.campaign))].append(rec)
        else:
            unidentified.append(rec)

    # If there is a single identified line, unidentified media tabs are most likely
    # channel/flight tabs belonging to it (legacy behaviour). With multiple lines we keep
    # them separate because silently attaching them would be unsafe.
    if unidentified and len(grouped) == 1:
        next(iter(grouped.values())).extend(unidentified)
        unidentified = []

    out: List[MediaPlanGroup] = []
    seq = 1
    for _key, members in sorted(grouped.items(), key=lambda kv: min(x["order"] for x in kv[1])):
        members = sorted(members, key=lambda x: x["order"])
        metas = [x["meta"] for x in members]
        lines = [x["line"] for x in members if x["line"]]
        line = Counter(lines).most_common(1)[0][0] if lines else ""
        brand = _choose_brand(metas, line)
        campaigns = [m.campaign for m in metas if m.campaign]
        distinct_campaigns = list(dict.fromkeys(campaigns))
        campaign = distinct_campaigns[0] if len(distinct_campaigns) == 1 else ""
        label = line or " — ".join(x for x in (brand, campaign) if x) or ", ".join(x["name"] for x in members)
        scenarios = [x.get("scenario") for x in members if x.get("scenario")]
        if scenarios and len(scenarios_by_line.get(_line_key(line), set())) > 1:
            scenario_label = Counter(scenarios).most_common(1)[0][0]
            label = f"{label} — {scenario_label}"
        out.append(MediaPlanGroup(f"P{seq}", label, tuple(x["name"] for x in members), brand, campaign, line))
        seq += 1

    if unidentified:
        # Keep one legacy logical plan for unidentified working sheets; explicit flight
        # tabs will still split correctly at the next level.
        members = sorted(unidentified, key=lambda x: x["order"])
        out.append(MediaPlanGroup(
            f"P{seq}", "Другой медиаплан — " + ", ".join(x["name"] for x in members),
            tuple(x["name"] for x in members)
        ))

    return WorkbookStructure(path, out, classifications, families)


def discover_media_plan_groups(path: str | Path, default_year: int = 2026) -> List[MediaPlanGroup]:
    """Backward-compatible plan picker backed by canonical workbook discovery."""
    return discover_workbook_structure(path, default_year).plans


def parse_media_plan(
    path: str | Path,
    default_year: int = 2026,
    sheet_names: Optional[Iterable[str]] = None,
) -> ParsedPlan:
    path = Path(path)
    warnings: List[str] = []
    if path.suffix.lower() == ".xls":
        raise ValueError("Формат .xls слишком старый. Откройте файл в Excel и сохраните как .xlsx — после этого приложение его прочитает.")

    allowed = set(sheet_names) if sheet_names is not None else None
    with XlsxWorkbook(path) as wb:
        if allowed is None:
            sheets = wb.read_all()
        else:
            available = set(wb.sheet_names())
            sheets = {name: wb.read_sheet(name) for name in wb.sheet_names() if name in allowed and name in available}

    metas: Dict[str, SheetMeta] = {}
    tables: List[TableDef] = []
    working: List[Tuple[int, str, SheetMeta, List[TableDef], List[Placement]]] = []

    for order, (name, sheet) in enumerate(sheets.items()):
        if allowed is not None and name not in allowed:
            continue
        meta = extract_metadata(sheet, default_year)
        metas[name] = meta
        tdefs = find_tables(sheet, meta)
        if not tdefs:
            if meta.missing_formula_cache:
                warnings.append(f"{name}: {meta.missing_formula_cache} формул без сохраненного результата.")
            continue

        sheet_rows: List[Placement] = []
        for td in tdefs:
            sheet_rows.extend(parse_table(sheet, meta, td, default_year))
        if not any(not x.is_total for x in sheet_rows):
            continue
        if _looks_like_summary_sheet(name) and len(sheets) > 1:
            continue

        working.append((order, name, meta, tdefs, sheet_rows))
        tables.extend(tdefs)
        if meta.missing_formula_cache:
            warnings.append(
                f"{name}: {meta.missing_formula_cache} формул без сохраненного результата. "
                "Если значения пустые, пересохраните МП в Excel."
            )

    # Canonical platform aliases are metadata only at this stage. Legacy ``platform``
    # remains untouched, so existing reach/split/flowchart calculations do not change.
    harmonize_unknown_platform_variants([
        x for _, _, _, _, source_rows in working for x in source_rows if not x.is_total
    ])

    placements: List[Placement] = []
    flights: List[FlightInfo] = []
    audience_library = _load_audience_reference()

    # Separate-flight sheets (legacy/OMD style) remain the highest-priority structure.
    external_numbers = [_extract_flight_number(name) for _, name, _, _, _ in working]
    external_explicit_exists = any(n is not None for n in external_numbers)
    internal_exists = (
        any(meta.flight_intervals for _, _, meta, _, _ in working)
        or any(
            x.flight_hint is not None or x.common_scope
            for _, _, _, _, rows in working
            for x in rows
            if not x.is_total
        )
    )

    if internal_exists and not external_explicit_exists:
        # ---------------- Internal multi-flight worksheet(s) ----------------
        logical_rows: Dict[Any, List[Placement]] = defaultdict(list)
        logical_metas: Dict[Any, List[Tuple[str, SheetMeta]]] = defaultdict(list)
        source_budget_control = sum(
            float(x.budget)
            for _, _, _, _, source_rows in working
            for x in source_rows
            if not x.is_total and x.budget is not None
        )

        for _, name, meta, _tdefs, rows in working:
            split = _split_internal_sheet_rows(meta, rows, warnings)
            for key, part_rows in split.items():
                logical_rows[key].extend(part_rows)
                logical_metas[key].append((name, meta))

        def logical_sort(k: Any) -> Tuple[int, int]:
            return (1, 9999) if k == "AON" else (0, int(k))

        for idx, key in enumerate(sorted(logical_rows, key=logical_sort), start=1):
            rows = logical_rows[key]
            meta_items = logical_metas.get(key, [])
            fid = f"F{idx}"
            is_common = key == "AON"
            label = "Always-on" if is_common else f"Flight {int(key)}"

            intervals: List[Tuple[dt.date, dt.date]] = []
            if not is_common:
                for _name, meta in meta_items:
                    intervals.extend(meta.flight_intervals.get(int(key), []))
            # For structural flight periods, explicit calendar flags are the strongest
            # source when present. They are kept separate from placement.intervals so this
            # stage does not alter the existing flow/reach/split calculation paths.
            structural = [p for x in rows for p in x.structure_intervals]
            has_declared_flights = any(meta.flight_intervals for _name, meta in meta_items)
            if structural and not has_declared_flights:
                # Marker-only layouts (no declared flight periods) need the source
                # calendar to establish the flight span. In standard LAB templates with
                # declared flight periods, preserve the existing period/month logic.
                intervals.extend(structural)
            else:
                for x in rows:
                    intervals.extend(x.intervals or ([(x.start, x.end)] if x.start and x.end else []))
            intervals = _merge_date_intervals(intervals)

            starts = [a for a, _ in intervals]
            ends = [b for _, b in intervals]
            if not starts:
                starts = [x.start for x in rows if x.start]
            if not ends:
                ends = [x.end for x in rows if x.end]

            ta_names = [meta.ta_name for _, meta in meta_items if meta.ta_name]
            ta_name = Counter(ta_names).most_common(1)[0][0] if ta_names else ""

            univ_vals: List[float] = []
            source_people_vals: List[float] = []
            source_pct_vals: List[float] = []
            for _name, meta in meta_items:
                if not is_common and int(key) in meta.flight_universe:
                    univ_vals.append(float(meta.flight_universe[int(key)]))
                elif meta.ta_universe is not None:
                    univ_vals.append(float(meta.ta_universe))
                if not is_common and int(key) in meta.flight_reach_people_1p:
                    source_people_vals.append(float(meta.flight_reach_people_1p[int(key)]))
                if not is_common and int(key) in meta.flight_reach_pct_1p:
                    source_pct_vals.append(float(meta.flight_reach_pct_1p[int(key)]))

            universe = Counter(round(v, 3) for v in univ_vals).most_common(1)[0][0] if univ_vals else None
            universe_source = "mp" if universe is not None else ""
            if is_common:
                universe = None
                universe_source = ""
            if universe is None and ta_name and not is_common:
                resolved = _resolve_audience_universe(ta_name, audience_library)
                if resolved is not None:
                    universe = resolved
                    universe_source = "library"

            source_people = Counter(round(v, 6) for v in source_people_vals).most_common(1)[0][0] if source_people_vals else None
            source_pct = Counter(round(v, 12) for v in source_pct_vals).most_common(1)[0][0] if source_pct_vals else None
            sheet_label = ", ".join(dict.fromkeys(name for name, _ in meta_items))
            flight_campaigns = [meta.campaign for _name, meta in meta_items if meta.campaign]
            flight_campaign = Counter(flight_campaigns).most_common(1)[0][0] if flight_campaigns else ""

            flight = FlightInfo(
                id=fid,
                label=label,
                sheet=sheet_label,
                period_start=min(starts) if starts else None,
                period_end=max(ends) if ends else None,
                ta_name=ta_name,
                universe=universe,
                universe_source=universe_source,
                intervals=intervals,
                source_reach_people_1p=source_people,
                source_reach_pct_1p=source_pct,
                is_common=is_common,
                campaign=flight_campaign,
            )
            flights.append(flight)

            for x in rows:
                x.flight = fid
                x.flight_label = label
            group_rows = _dedupe_internal(rows)
            group_rows = _synthesize_missing_channel_totals(group_rows, flight)
            synthetic_channels = [x.channel for x in group_rows if x.synthetic_total]
            if synthetic_channels:
                warnings.append(
                    f"{label}: субтоталы рассчитаны автоматически для: {', '.join(dict.fromkeys(synthetic_channels))}. "
                    "Бюджет/показы суммированы, Reach UU = сумма Reach UU × fallback коэффициент площадок."
                )
            placements.extend(group_rows)

        split_budget_control = sum(float(x.budget) for x in placements if not x.is_total and x.budget is not None)
        if abs(split_budget_control - source_budget_control) > 0.01:
            warnings.insert(0,
                "КРИТИЧЕСКАЯ ПРОВЕРКА: после распределения строк по флайтам изменилась контрольная сумма бюджета "
                f"({source_budget_control:.2f} → {split_budget_control:.2f}). Расчёт требует проверки парсера."
            )

    else:
        # ---------------- Existing sheet-based flight grouping ----------------
        channel_named_count = sum(1 for _, name, _, _, _ in working if infer_channel(name) is not None)
        channel_tabs_layout = bool(working) and not external_explicit_exists and len(working) > 1 and channel_named_count >= max(2, math.ceil(len(working) * 0.6))

        grouped: Dict[Any, List[Tuple[int, str, SheetMeta, List[TableDef], List[Placement]]]] = defaultdict(list)
        for item in working:
            order, name, meta, tdefs, rows = item
            explicit = _extract_flight_number(name)
            if explicit is not None:
                key = ("flight", explicit)
            elif channel_tabs_layout:
                key = ("channel_tabs", 1)
            elif meta.period_start or meta.period_end:
                key = ("period", meta.period_start, meta.period_end)
            else:
                key = ("sheet", order)
            grouped[key].append(item)

        def group_sort(item):
            key, members = item
            if key[0] == "flight":
                return (0, key[1], dt.date.min, min(x[0] for x in members))
            starts = [x[2].period_start for x in members if x[2].period_start]
            return (1, 9999, min(starts) if starts else dt.date.max, min(x[0] for x in members))

        groups = sorted(grouped.items(), key=group_sort)
        for idx, (key, members) in enumerate(groups, start=1):
            explicit_num = key[1] if key[0] == "flight" else None
            label = f"Flight {explicit_num}" if explicit_num is not None else f"Flight {idx}"
            fid = f"F{idx}"

            starts = [m[2].period_start for m in members if m[2].period_start]
            ends = [m[2].period_end for m in members if m[2].period_end]
            ta_names = [m[2].ta_name for m in members if m[2].ta_name]
            ta_name = Counter(ta_names).most_common(1)[0][0] if ta_names else ""
            univs = [round(m[2].ta_universe, 3) for m in members if m[2].ta_universe is not None]
            universe = Counter(univs).most_common(1)[0][0] if univs else None
            universe_source = "mp" if universe is not None else ""
            if universe is None and ta_name:
                resolved = _resolve_audience_universe(ta_name, audience_library)
                if resolved is not None:
                    universe = resolved
                    universe_source = "library"

            all_intervals = []
            for mbr in members:
                meta = mbr[2]
                if meta.flight_intervals:
                    for ints in meta.flight_intervals.values():
                        all_intervals.extend(ints)
            if not all_intervals and starts and ends:
                all_intervals = [(min(starts), max(ends))]

            sheet_label = ", ".join(m[1] for m in sorted(members, key=lambda x: x[0]))
            flight_campaigns = [m[2].campaign for m in members if m[2].campaign]
            flight_campaign = Counter(flight_campaigns).most_common(1)[0][0] if flight_campaigns else ""
            flight = FlightInfo(
                fid, label, sheet_label,
                min(starts) if starts else None,
                max(ends) if ends else None,
                ta_name,
                universe,
                universe_source,
                intervals=_merge_date_intervals(all_intervals),
                campaign=flight_campaign,
            )
            flights.append(flight)

            group_rows: List[Placement] = []
            for _, _, _, _, rows in members:
                for x in rows:
                    x.flight = fid
                    x.flight_label = label
                group_rows.extend(rows)
            group_rows = _dedupe(group_rows)
            group_rows = _synthesize_missing_channel_totals(group_rows, flight)
            synthetic_channels = [x.channel for x in group_rows if x.synthetic_total]
            if synthetic_channels:
                warnings.append(
                    f"{label}: субтоталы рассчитаны автоматически для: {', '.join(dict.fromkeys(synthetic_channels))}. "
                    "Бюджет/показы суммированы, Reach UU = сумма Reach UU × fallback коэффициент площадок."
                )
            placements.extend(group_rows)

    # Normalize all-media TOTAL model separately inside each flight.
    for flight in flights:
        flight_rows = [x for x in placements if x.flight == flight.id]
        detail_models = {x.buying_model for x in flight_rows if not x.is_total and x.buying_model != "OTHER"}
        if len(detail_models) == 1:
            only_model = next(iter(detail_models))
            for x in flight_rows:
                if x.is_total and x.channel in {"TOTAL", "Other"}:
                    x.buying_model = only_model
                    if only_model == "CPM":
                        x.target_kpi_label = "Показы"
                        x.target_kpi_value = x.impressions
        else:
            for x in flight_rows:
                if x.is_total and x.channel in {"TOTAL", "Other"}:
                    x.buying_model = "OTHER"
                    x.target_kpi_label = ""
                    x.target_kpi_value = None

    # Combined plan defaults to the latest non-common flight with Universe.
    flights_with_universe = [f for f in flights if f.universe is not None]
    preferred_universe_flights = [f for f in flights_with_universe if not f.is_common] or flights_with_universe
    if preferred_universe_flights:
        latest = max(preferred_universe_flights, key=lambda f: (f.period_end or f.period_start or dt.date.min, f.id))
        universe = latest.universe
    else:
        universe = None
    univs = [round(f.universe, 3) for f in preferred_universe_flights]
    if len(set(univs)) > 1:
        warnings.append(
            "На флайтах разные TA Universe. Для объединенного плана по умолчанию используется Universe самого позднего выбранного флайта; каждый флайт хранит свой Universe."
        )

    starts = [f.period_start for f in flights if f.period_start]
    ends = [f.period_end for f in flights if f.period_end]
    period_start = min(starts) if starts else None
    period_end = max(ends) if ends else None

    if not placements:
        warnings.append("Не найдено ни одной строки размещения.")
    if not flights:
        warnings.append("Не найдено ни одного рабочего листа медиаплана.")
    if universe is None:
        warnings.append("Не найден TA Universe и не удалось подобрать его по справочнику. Его нужно ввести вручную.")
    for f in flights:
        if f.universe is None and not f.is_common:
            warnings.append(f"{f.label}: TA Universe не найден и не сопоставлен со справочником.")
        elif f.universe_source == "library":
            warnings.append(
                f"{f.label}: TA Universe {int(round(f.universe)):,} подставлен из справочника для ЦА '{f.ta_name}'.".replace(",", " ")
            )
    if period_start is None:
        warnings.append("Не найден Period в шапке. Флоучарт может быть пустым.")
    if not any(x.budget is not None for x in placements):
        warnings.append("Не найден бюджет. Ожидаем столбец Total cost after discount, RUR или его вариант.")
    reach_expected = any(
        (not x.is_total) and x.buying_model != "CPC" and (
            x.buying_model in {"CPM", "CPV"}
            or (x.impressions is not None and x.frequency is not None)
            or x.tech_reach is not None
        ) for x in placements
    )
    if reach_expected and not any(x.tech_reach is not None for x in placements):
        warnings.append("Для охватных строк не найден Reach UU. Reach по ним посчитать нельзя.")

    line_names = [_meta_line_name(m) for m in metas.values() if _meta_line_name(m)]
    line = Counter(line_names).most_common(1)[0][0] if line_names else ""
    brand = _choose_brand(list(metas.values()), line)
    campaigns = [m.campaign for m in metas.values() if m.campaign]
    distinct_campaigns = list(dict.fromkeys(campaigns))
    campaign = distinct_campaigns[0] if len(distinct_campaigns) == 1 else ""
    display_name = line or " — ".join(x for x in [brand, campaign] if x) or (next(iter(metas)) if len(metas) == 1 else path.stem)

    return ParsedPlan(
        path, placements, metas, tables, universe, period_start, period_end, warnings, flights,
        display_name=display_name, brand=brand, campaign=campaign, line=line,
    )


def _reach_model_allowed(x: Placement) -> bool:
    """Buying-model/channel eligibility independent of whether Reach UU is present."""
    if x.buying_model not in {"CPM", "CPV"}:
        return False
    cls = norm(getattr(x, "placement_class", "") or x.channel)
    return "seo" not in cls and "исслед" not in cls and "research" not in cls


def _reach_allowed_for_row(plan: ParsedPlan, x: Placement) -> bool:
    """A row creates row-level reach only when CPM/CPV, non-SEO and Reach UU exists."""
    return x.tech_reach is not None and _reach_model_allowed(x)


def _audience_intersection_coef(universe: float) -> Tuple[str, float]:
    """
    Agreed rule:
    medium/wide audience size does not additionally narrow overlap.
    Only narrow / very narrow audiences reduce the coefficient.
    """
    if universe < 7_500_000:
        return "Очень узкая", 0.70
    if universe < 12_000_000:
        return "Узкая", 0.80
    if universe < 20_000_000:
        return "Средняя", 1.00
    if universe <= 30_000_000:
        return "Широкая", 1.00
    return "Очень широкая", 1.00


def _platform_intersection_coef(value: int) -> float:
    """
    Platforms are evaluated within each flight, not across the annual plan:
    1 -> 1.00; 2 -> 0.95; 3-4 -> 0.90; 5+ -> 0.80.
    """
    value = max(1, int(value))
    if value == 1:
        return 1.00
    if value == 2:
        return 0.95
    if value <= 4:
        return 0.90
    return 0.80


def _rows_intersection_coef(rows_per_platform: float) -> float:
    """
    Exactly one row per platform -> 1.00.
    More than one row per platform within a flight -> 0.90.
    """
    return 1.00 if float(rows_per_platform) <= 1.0000001 else 0.90


def _intersection_channel_bucket(channel: str) -> Optional[str]:
    """
    Only three media families influence the channel factor:
    OLV / Banners / Social.
    Context/search is excluded.
    Native/mobile/display-like formats are treated as Banners.
    """
    t = norm(channel)
    if not t:
        return None

    if any(token in t for token in (
        "контекст", "context", "search", "поиск", "директ", "direct", "seo", "sem",
    )):
        return None

    if any(token in t for token in ("olv", "video", "видео")):
        return "OLV"
    if any(token in t for token in ("social", "соц", "smm", "vk ads", "вк ads")):
        return "Social"
    if any(token in t for token in (
        "banner", "баннер", "display", "native", "натив", "mobile", "мобайл",
        "мобиль", "rich media", "richmedia", "programmatic", "программатик",
        "teaser", "тизер",
    )):
        return "Banners"

    if t == "banners":
        return "Banners"
    if t == "social nets":
        return "Social"
    return None


def _channel_intersection_coef(value: int) -> float:
    value = max(1, int(value))
    if value == 1:
        return 1.00
    if value == 2:
        return 0.95
    return 0.90


def intersection_breakdown(
    plan: ParsedPlan,
    selected_flights: Iterable[str],
    universe: float,
    complexity: str = "Простая",
    factor_overrides: Optional[Dict[str, float]] = None,
    manual_final: Optional[float] = None,
) -> IntersectionBreakdown:
    selected = tuple(x for x in selected_flights if x in plan.flight_ids())
    reach_selected = tuple(
        fid for fid in selected
        if not (plan.flight_info(fid) and plan.flight_info(fid).is_common)
    ) or selected
    details = plan.detail_rows(reach_selected)
    factor_overrides = dict(factor_overrides or {})

    audience_category, audience_auto = _audience_intersection_coef(universe)
    complexity_clean = "Сложная" if norm(complexity).startswith("слож") else "Простая"
    complexity_auto = 0.90 if complexity_clean == "Сложная" else 1.0

    # Platforms: evaluate every selected flight separately.
    platform_counts_by_flight: Dict[str, int] = {}
    for fid in reach_selected:
        flight_details = [x for x in details if x.flight == fid]
        platforms = {_platform_key(x.platform) for x in flight_details if _platform_key(x.platform)}
        platform_counts_by_flight[fid] = max(1, len(platforms)) if flight_details else 1

    # Use the most complex individual flight; never sum/union platforms through all flights.
    platform_count = max(platform_counts_by_flight.values(), default=1)
    platform_auto = _platform_intersection_coef(platform_count)

    # Rows/platform: average inside each flight; repeated flights are not pooled.
    rows_avg_by_flight: Dict[str, float] = {}
    for fid in reach_selected:
        flight_details = [x for x in details if x.flight == fid]
        by_platform: Dict[str, int] = defaultdict(int)
        for x in flight_details:
            pkey = _platform_key(x.platform)
            if pkey:
                by_platform[pkey] += 1
        if by_platform:
            rows_avg_by_flight[fid] = sum(by_platform.values()) / len(by_platform)
        elif flight_details:
            rows_avg_by_flight[fid] = 1.0

    rows_per_platform = max(rows_avg_by_flight.values(), default=1.0)
    rows_auto = _rows_intersection_coef(rows_per_platform)

    # Channels: only OLV / Banners / Social count, also within each flight.
    channel_counts_by_flight: Dict[str, int] = {}
    for fid in reach_selected:
        flight_details = [x for x in details if x.flight == fid]
        buckets = {
            bucket
            for x in flight_details
            for bucket in [_intersection_channel_bucket(x.channel)]
            if bucket
        }
        channel_counts_by_flight[fid] = max(1, len(buckets)) if flight_details else 1

    channel_count = max(channel_counts_by_flight.values(), default=1)
    channel_auto = _channel_intersection_coef(channel_count)

    infos = [plan.flight_info(fid) for fid in reach_selected]
    infos = [f for f in infos if f is not None]
    if len(reach_selected) <= 1:
        info = infos[0] if infos else None
        if info and info.period_start and info.period_end:
            month_span = (info.period_end.year - info.period_start.year) * 12 + info.period_end.month - info.period_start.month + 1
        else:
            month_span = 1
        if month_span <= 1:
            period_situation, period_auto = "1 флайт", 1.0
        else:
            period_situation, period_auto = "1 флайт, но 2-3 месяца", 0.95
    else:
        sorted_infos = sorted(
            [f for f in infos if f.period_start and f.period_end],
            key=lambda f: f.period_start or dt.date.min,
        )
        long_gap = False
        for a, b in zip(sorted_infos, sorted_infos[1:]):
            if a.period_end and b.period_start and (b.period_start - a.period_end).days > 31:
                long_gap = True
                break
        if long_gap:
            period_situation, period_auto = "Перерыв больше месяца", 0.90
        else:
            period_situation, period_auto = "Разные флайты", 0.90

    auto_factors = {
        "audience": audience_auto,
        "complexity": complexity_auto,
        "platforms": platform_auto,
        "rows": rows_auto,
        "channels": channel_auto,
        "period": period_auto,
    }
    applied = {
        k: _unit_interval(factor_overrides.get(k, v), f"Коэффициент {k}")
        for k, v in auto_factors.items()
    }
    auto_product = math.prod(auto_factors.values())
    adjusted_product = math.prod(applied.values())

    # The selected intersection mode is a TOTAL DIGITAL aggregation rule and must
    # work even when the plan has only one flight. One flight can still contain
    # many platforms/rows/channels that overlap. Web 0.39 incorrectly forced 1.00
    # for every single-flight plan, ignoring the user's 0.85 total coefficient.
    if manual_final is not None:
        applied_product = _unit_interval(manual_final, "Тотал коэффициент пересечения")
        mode = "manual"
    elif factor_overrides:
        applied_product = adjusted_product
        mode = "adjusted"
    else:
        applied_product = auto_product
        mode = "auto"

    def _label(fid: str) -> str:
        info = plan.flight_info(fid)
        return info.label if info else fid

    platform_detection = " · ".join(
        f"{_label(fid)}: {count}" for fid, count in platform_counts_by_flight.items()
    )
    rows_detection = " · ".join(
        f"{_label(fid)}: {value:.1f}" for fid, value in rows_avg_by_flight.items()
    )
    channel_detection = " · ".join(
        f"{_label(fid)}: {count}" for fid, count in channel_counts_by_flight.items()
    )

    return IntersectionBreakdown(
        selected_flights=selected,
        audience_size=universe,
        audience_category=audience_category,
        audience_coef_auto=audience_auto,
        complexity=complexity_clean,
        complexity_coef_auto=complexity_auto,
        platform_count=platform_count,
        platform_coef_auto=platform_auto,
        rows_per_platform=rows_per_platform,
        rows_coef_auto=rows_auto,
        channel_count=channel_count,
        channel_coef_auto=channel_auto,
        period_situation=period_situation,
        period_coef_auto=period_auto,
        auto_product=auto_product,
        applied_product=applied_product,
        mode=mode,
        applied_factors=applied,
        platform_detection=platform_detection,
        rows_detection=rows_detection,
        channel_detection=channel_detection,
    )

def _aggregate_performance(rows: Iterable[Placement]) -> List[Tuple[str, float]]:
    agg: Dict[str, float] = defaultdict(float)
    seen: set[str] = set()
    for x in rows:
        if x.target_kpi_label and x.target_kpi_value is not None and x.buying_model != "CPM":
            agg[x.target_kpi_label] += float(x.target_kpi_value)
            seen.add(x.target_kpi_label)
    return [(label, agg[label]) for label in sorted(seen)]


def selected_summary(
    plan: ParsedPlan,
    selected_flights: Iterable[str],
    params: ReachParams,
    intersection: IntersectionBreakdown,
) -> CombinedSummary:
    selected = tuple(x for x in selected_flights if x in plan.flight_ids())
    if not selected:
        return CombinedSummary(tuple(), None, None, None, None, {}, [], intersection, "Выберите хотя бы один флайт.")

    budget = 0.0
    impressions = 0.0
    have_budget = have_imps = False

    for fid in selected:
        total = plan.flight_total(fid)
        if total is not None and total.budget is not None:
            budget += total.budget
            have_budget = True
        else:
            vals = [x.budget for x in plan.detail_rows([fid]) if x.budget is not None]
            if vals:
                budget += sum(vals)
                have_budget = True
        # Additive impressions are used only for diagnostics/frequency fallback.
        vals_i = [x.impressions for x in plan.detail_rows([fid]) if x.impressions is not None]
        if vals_i:
            impressions += sum(vals_i)
            have_imps = True

    # Reach rows are strictly reach-buying placements. Performance/services do not
    # create reach and cannot make a flight eligible for a source Reach subtotal.
    reach_rows = [
        x for x in plan.detail_rows(selected)
        if _reach_model_allowed(x)
        and not (plan.flight_info(x.flight) and plan.flight_info(x.flight).is_common)
    ]

    # Source CrossWeb Reach people @1+ per flight has priority, but only for flights
    # that actually contain at least one reach-buying row.
    reach_flights = []
    for fid in selected:
        info = plan.flight_info(fid)
        if info is None or info.is_common:
            continue
        if any(x.flight == fid for x in reach_rows):
            reach_flights.append(info)
    source_ready = bool(reach_flights) and all(f.source_reach_people_1p is not None for f in reach_flights)

    tech_reach: Optional[float] = None
    frequency: Optional[float] = None
    reach: Dict[str, float] = {}
    warning = ""

    # Frequency fallback uses the same strict reach-buying set.
    reach_imps_vals = [x.impressions for x in reach_rows if x.impressions is not None]
    reach_impressions = sum(reach_imps_vals) if reach_imps_vals else None

    if source_ready:
        # Build a frequency curve inside every flight first and only then combine flights.
        # Using total impressions / already-deduplicated annual reach artificially inflates
        # average frequency and can make @3+ almost identical to @1+.
        per_flight_reach: List[Dict[str, float]] = []
        weighted_freq_num = 0.0
        weighted_freq_den = 0.0
        for f in reach_flights:
            source1 = float(f.source_reach_people_1p)
            flight_rows = [
                x for x in plan.detail_rows([f.id])
                if _reach_model_allowed(x) and x.tech_reach is not None
            ]
            fi = sum(float(x.impressions or 0.0) for x in flight_rows if x.impressions is not None)
            fr = sum(float(x.tech_reach or 0.0) for x in flight_rows if x.tech_reach is not None)
            avg_f = (fi / fr) if fr > 0 and fi > 0 else None
            if avg_f is not None:
                weighted_freq_num += avg_f * source1
                weighted_freq_den += source1
            fp = ReachParams(
                universe=params.universe,
                lag_visible_share=params.lag_visible_share,
                cookie_people=params.cookie_people,
                target_affinity=params.target_affinity,
                reachability_coefficients=dict(params.reachability_coefficients),
                selected_frequencies=tuple(params.selected_frequencies),
                effective_frequency=params.effective_frequency,
            )
            per_flight_reach.append(calculate_reach_from_target_1p(
                source1, fp, impressions=(fi if fi > 0 else None), avg_frequency=avg_f
            ))

        reach = combine_reach_union(
            per_flight_reach,
            params.universe,
            coefficient=intersection.applied_product,
            frequencies=params.normalized_frequencies(),
        )
        frequency = (weighted_freq_num / weighted_freq_den) if weighted_freq_den > 0 else None
    else:
        # Legacy fallback: explicit/synthesized all-media technical Reach UU per flight.
        # Without authoritative CrossWeb flight reach, TOTAL DIGITAL reach is rebuilt
        # from the physical reach-buying rows and the user-selected intersection rule.
        # This intentionally replaces embedded source-total formulas such as
        # SUM(Reach UU)*0.90: otherwise a media-plan coefficient would silently override
        # the 0.85/manual/detailed coefficient selected in the web calculator.
        row_reach_sets: List[Dict[str, float]] = []
        raw_reaches: List[float] = []
        for x in reach_rows:
            if x.tech_reach is None:
                continue
            raw_reaches.append(float(x.tech_reach))
            row_reach_sets.append(calculate_reach(
                x.tech_reach,
                params,
                impressions=x.impressions,
                avg_frequency=x.frequency,
            ))
        if row_reach_sets:
            # Keep technical reach/frequency only as diagnostics. The actual Reach is a
            # bounded union of row-level audiences and is never an arithmetic sum.
            raw_tech_total = sum(raw_reaches)
            tech_reach = raw_tech_total
            frequency = (
                reach_impressions / raw_tech_total
                if reach_impressions is not None and raw_tech_total > 0 else None
            )
            reach = combine_reach_union(
                row_reach_sets,
                params.universe,
                coefficient=intersection.applied_product,
                frequencies=params.normalized_frequencies(),
            )
        else:
            warning = (
                "Для выбранных флайтов не найден Reach UU в охватных строках — "
                "объединенный Reach не рассчитывается."
            )

    r1 = reach.get("target_pct_1p")
    if not warning and r1 is not None and r1 >= 1.0:
        warning = "Расчетный Reach @1+ превышает 100%. Проверьте Universe и коэффициент пересечения."
    elif not warning and r1 is not None and r1 >= 0.95:
        warning = "Расчетный Reach @1+ ≥95%. Проверьте Universe и коэффициент пересечения."

    return CombinedSummary(
        selected,
        budget if have_budget else None,
        impressions if have_imps else None,
        tech_reach,
        frequency,
        reach,
        _aggregate_performance(plan.detail_rows(selected)),
        intersection,
        warning,
    )



FLOW_PERFORMANCE_LABELS = {
    "CPC": "Клики",
    "CPA": "Действия",
    "CPI": "Установки",
    "CPO": "Заказы",
    "CPL": "Лиды",
    "CPR": "Дочитывания",
    "CPCV": "Досмотры",
    "CPE": "Вовлечения",
    "CPS": "Продажи",
}


def flight_channel_kpi_summary(
    plan: ParsedPlan,
    flight_id: str,
    channel: str,
    params: ReachParams,
) -> Dict[str, Any]:
    """
    KPI summary for ONE flight inside ONE channel.

    Display policy agreed for the flowchart:
    - CPM / CPV: Budget + Reach @1+ + Reach at the selected effective frequency.
    - CPC: Budget + Clicks.
    - CPR: Budget + Reads/completed reads.
    - Other performance buying models: Budget + their target KPI.
    - If several performance models coexist, aggregate each KPI separately.
    - If reach and performance buying models coexist, show both blocks.
    """
    rows = [
        x for x in plan.detail_rows([flight_id])
        if x.channel == channel
    ]
    if not rows:
        return {
            "flight": flight_id,
            "channel": channel,
            "budget": None,
            "models": tuple(),
            "reach": {},
            "frequency": None,
            "performance": [],
        }

    budget_vals = [x.budget for x in rows if x.budget is not None]
    budget = sum(budget_vals) if budget_vals else None
    models = tuple(sorted({x.buying_model for x in rows if x.buying_model and x.buying_model != "OTHER"}))

    reach_models = {"CPM", "CPV"}
    has_reach_model = any(m in reach_models for m in models)
    perf_models = [m for m in models if m not in reach_models]

    subtotal = plan.channel_total(flight_id, channel)
    reach: Dict[str, float] = {}
    frequency: Optional[float] = None

    # For reach-based buying use the explicit/synthesized channel subtotal.
    # This avoids summing reach across placements.
    if has_reach_model and subtotal is not None and subtotal.tech_reach is not None:
        frequency = subtotal.frequency
        if frequency is None and subtotal.impressions is not None and subtotal.tech_reach not in (None, 0):
            frequency = subtotal.impressions / subtotal.tech_reach
        reach = calculate_reach(
            subtotal.tech_reach,
            params,
            impressions=subtotal.impressions,
            avg_frequency=frequency,
        )

    # Performance KPI is aggregated by actual buying model.
    perf_agg: Dict[str, float] = defaultdict(float)
    for model in perf_models:
        label = FLOW_PERFORMANCE_LABELS.get(model)
        if not label:
            continue
        vals = [
            float(x.target_kpi_value)
            for x in rows
            if x.buying_model == model and x.target_kpi_value is not None
        ]
        if vals:
            perf_agg[label] += sum(vals)

    performance = [(label, perf_agg[label]) for label in FLOW_PERFORMANCE_LABELS.values() if label in perf_agg]

    return {
        "flight": flight_id,
        "channel": channel,
        "budget": budget,
        "models": models,
        "reach": reach,
        "frequency": frequency,
        "performance": performance,
    }


def selected_channel_summary(
    plan: ParsedPlan,
    selected_flights: Iterable[str],
    params: ReachParams,
    intersection: IntersectionBreakdown,
) -> List[Dict[str, Any]]:
    selected = tuple(x for x in selected_flights if x in plan.flight_ids())
    groups: Dict[str, List[Placement]] = defaultdict(list)
    for x in plan.detail_rows(selected):
        groups[x.channel].append(x)

    out: List[Dict[str, Any]] = []
    for channel, rows in groups.items():
        budget_vals = [x.budget for x in rows if x.budget is not None]
        imp_vals = [x.impressions for x in rows if x.impressions is not None]
        budget = sum(budget_vals) if budget_vals else None
        impressions = sum(imp_vals) if imp_vals else None

        channel_flights = [fid for fid in selected if any(x.channel == channel for x in plan.detail_rows([fid]))]
        reach_sources = []
        for fid in channel_flights:
            src = plan.channel_total(fid, channel)
            if src and src.tech_reach is not None:
                reach_sources.append(src.tech_reach)
        tech_reach = None
        reach: Dict[str, float] = {}
        if reach_sources and len(reach_sources) == len(channel_flights):
            if len(reach_sources) == 1:
                tech_reach = reach_sources[0]
                frequency = impressions / tech_reach if impressions is not None and tech_reach not in (None, 0) else None
                reach = calculate_reach(
                    tech_reach, params, impressions=impressions, avg_frequency=frequency
                )
            else:
                source_sets = [
                    calculate_reach(src, params)
                    for src in reach_sources
                ]
                reach = combine_reach_union(
                    source_sets,
                    params.universe,
                    coefficient=intersection.applied_product,
                    frequencies=params.normalized_frequencies(),
                )
                tech_reach = sum(reach_sources)
                frequency = impressions / tech_reach if impressions is not None and tech_reach > 0 else None
        else:
            frequency = None
        out.append({
            "channel": channel,
            "budget": budget,
            "impressions": impressions,
            "tech_reach": tech_reach,
            "frequency": frequency,
            "reach": reach,
            "performance": _aggregate_performance(rows),
        })
    return out


def channel_summary(plan: ParsedPlan) -> List[Dict[str, Any]]:
    groups: Dict[str, List[Placement]] = defaultdict(list)
    for x in plan.detail_rows():
        groups[x.channel].append(x)
    out: List[Dict[str, Any]] = []
    totals_by_channel: Dict[str, List[Placement]] = defaultdict(list)
    for x in plan.total_rows():
        totals_by_channel[x.channel].append(x)

    for channel, rows in sorted(groups.items()):
        budget = sum(x.budget or 0 for x in rows) if any(x.budget is not None for x in rows) else None
        impressions = sum(x.impressions or 0 for x in rows) if any(x.impressions is not None for x in rows) else None
        # Reach: explicit channel total; if only one reach placement, that placement itself is safe.
        reach_source: Optional[Placement] = None
        tr = [x for x in totals_by_channel.get(channel, []) if x.tech_reach is not None and x.reach]
        if tr:
            reach_source = max(tr, key=lambda x: (x.budget or 0, x.tech_reach or 0))
        else:
            reach_rows = [x for x in rows if x.tech_reach is not None and x.reach]
            if len(reach_rows) == 1:
                reach_source = reach_rows[0]
        perf = []
        for x in rows:
            if x.target_kpi_label and x.target_kpi_value is not None and x.buying_model != "CPM":
                perf.append((x.target_kpi_label, x.target_kpi_value))
        out.append({
            "channel": channel,
            "budget": budget,
            "impressions": impressions,
            "reach_source": reach_source,
            "performance": perf,
        })
    return out
