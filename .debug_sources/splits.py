from __future__ import annotations

import calendar
import datetime as dt
import math
import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple
from xml.sax.saxutils import escape

from xlsx_reader import XlsxWorkbook
try:
    from engine import canonicalize_platform_name, classify_placement, detect_model, placement_markers, research_details
except ImportError:  # local regression against 0.44 core
    from engine import detect_model
    def canonicalize_platform_name(value):
        raw = _display(value) if '_display' in globals() else str(value or '').strip()
        return raw, 'local fallback', 0.5
    def placement_markers(platform='', fmt='', raw=''):
        t = ' | '.join(str(x or '') for x in (platform, fmt, raw))
        research = '/'.join(x for x in ('BLS','SL') if re.search(rf'(?i)\b{x}\b', t))
        cleaned = re.sub(r'(?i)\b(?:bonus|бонус(?:ом)?)\s*(?:BLS|SL)\b|\b(?:BLS|SL)\s*(?:bonus|бонус(?:ом)?)\b', ' ', t)
        return bool(re.search(r'(?i)\bbonus\b|\bбонус(?:ом|ный|ная|ное|ные)?\b', cleaned)), research

    def research_details(platform='', fmt='', raw='', budget=None):
        marker = placement_markers(platform, fmt, raw)[1]
        dedicated = bool(
            re.fullmatch(r'(?i)\s*(?:BLS|SL|brand[ -]*lift(?:[ -]*study)?|sales[ -]*lift|search[ -]*lift|research|исследовани\w*)\s*', str(platform or ''))
            or re.fullmatch(r'(?i)\s*(?:BLS|SL|brand[ -]*lift(?:[ -]*study)?|sales[ -]*lift|search[ -]*lift|research|исследовани\w*)\s*', str(fmt or ''))
        )
        bonus = bool(re.search(
            r'(?i)(?:bonus|бонус\w*)\s*(?:BLS|SL)|(?:BLS|SL)\s*(?:bonus|бонус\w*)',
            ' | '.join(str(x or '') for x in (platform,fmt,raw))
        ))
        if bonus: return marker, 'BONUS', 0.0, dedicated
        if dedicated and budget not in (None,0): return marker, 'PAID', float(budget), True
        return marker, ('COST_NOT_SEPARATED' if marker else ''), None, dedicated

    def classify_placement(platform='', fmt='', raw='', model='OTHER', legacy_channel=None, section_class=None):
        t = (' '.join(str(x or '') for x in (platform, fmt, raw))).lower()
        if 'slickjump' in t or 'avito' in t or 'baby.ru' in t:
            return ('OLV' if any(x in t for x in ('video','видео','pre-roll','instream')) or model in {'CPV','CPCV'} else 'Баннеры', 'local hard rule')
        if any(x in t for x in ('блогер','инфлюенс','посев','seeding')): return 'Спецпроекты','local social special'
        if 'seo' in t: return 'SEO','local seo'
        if 'рся' in t or 'rsya' in t: return 'РСЯ','local rsya'
        if 'direct' in t or 'директ' in t or 'поиск' in t: return 'Поиск','local search'
        if any(x in t for x in ('video','видео','olv','pre-roll','instream')): return 'OLV','local video'
        if any(x in t for x in ('banner','баннер','display','тгб','slickjump')): return 'Баннеры','local display'
        if 'orm' in t: return 'ORM','local orm'
        if 'native' in t or 'натив' in t: return 'Native','local native'
        return 'Social','local fallback'

MONTH_NAMES_RU = {
    1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель", 5: "Май", 6: "Июнь",
    7: "Июль", 8: "Август", 9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
}
MONTH_ALIASES: Dict[int, Tuple[str, ...]] = {
    1: ("январ", "january", "jan"), 2: ("феврал", "february", "feb"),
    3: ("март", "march", "mar"), 4: ("апрел", "april", "apr"),
    5: ("май", "мая", "may"), 6: ("июн", "june", "jun"),
    7: ("июл", "july", "jul"), 8: ("август", "august", "aug"),
    9: ("сентябр", "september", "sep", "sept"), 10: ("октябр", "october", "oct"),
    11: ("ноябр", "november", "nov"), 12: ("декабр", "december", "dec"),
}


def _norm(v: Any) -> str:
    if v is None:
        return ""
    s = str(v).replace("\n", " ").replace("\r", " ").lower().replace("ё", "е")
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _display(v: Any) -> str:
    if v is None:
        return ""
    return re.sub(r"\s+", " ", str(v).replace("\r", " ").replace("\n", " ")).strip()


def _to_number(v: Any) -> Optional[float]:
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        try:
            f = float(v)
            return f if math.isfinite(f) else None
        except Exception:
            return None
    s = str(v).strip().replace("\xa0", " ")
    if not s or s in {"-", "—", "#N/A", "#NAME?", "#VALUE!", "#REF!"}:
        return None
    # Percent is returned as a human percentage number: 1.65% -> 1.65.
    pct = "%" in s
    s = s.replace("₽", "").replace("руб.", "").replace("руб", "").replace("rur", "")
    s = s.replace(" ", "").replace("%", "")
    # decimal comma, possible thousands commas
    if s.count(",") == 1 and s.count(".") == 0:
        s = s.replace(",", ".")
    elif s.count(",") > 0 and s.count(".") > 0:
        s = s.replace(",", "")
    try:
        f = float(s)
        return f if math.isfinite(f) else None
    except Exception:
        return None


def _month_from_value(v: Any) -> Optional[int]:
    if isinstance(v, (dt.datetime, dt.date)):
        return v.month
    if isinstance(v, (int, float)) and 1 <= float(v) <= 12 and float(v).is_integer():
        return int(v)
    t = _norm(v)
    if not t:
        return None
    for m, aliases in MONTH_ALIASES.items():
        if any(a in t for a in aliases):
            return m
    # formats like 08.2026 / 8/2026
    mm = re.search(r"(?:^|\D)(1[0-2]|0?[1-9])[./-](?:20)?\d{2}(?:\D|$)", t)
    if mm:
        return int(mm.group(1))
    return None


def _parse_date(v: Any) -> Optional[dt.date]:
    if isinstance(v, dt.datetime):
        return v.date()
    if isinstance(v, dt.date):
        return v
    s = _display(v)
    if not s:
        return None
    m = re.search(r"(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})", s)
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    try:
        return dt.date(y, mo, d)
    except Exception:
        return None


def _parse_period(v: Any, default_year: int = 2026) -> Tuple[Optional[dt.date], Optional[dt.date]]:
    if isinstance(v, (dt.date, dt.datetime)):
        d = v.date() if isinstance(v, dt.datetime) else v
        return d, d
    s = _display(v)
    if not s:
        return None, None
    pats = re.findall(r"\d{1,2}[./-]\d{1,2}(?:[./-]\d{2,4})?", s)
    dates: List[dt.date] = []
    for p in pats[:2]:
        bits = re.split(r"[./-]", p)
        try:
            d, mo = int(bits[0]), int(bits[1])
            y = int(bits[2]) if len(bits) > 2 else default_year
            if y < 100:
                y += 2000
            dates.append(dt.date(y, mo, d))
        except Exception:
            pass
    if len(dates) >= 2:
        return min(dates), max(dates)
    if len(dates) == 1:
        return dates[0], dates[0]
    month = _month_from_value(s)
    if month:
        ym = re.search(r"20\d{2}", s)
        y = int(ym.group()) if ym else default_year
        return dt.date(y, month, 1), dt.date(y, month, calendar.monthrange(y, month)[1])
    return None, None



def _is_social_special_project_text(*values: Any) -> bool:
    """High-priority detector for blogger/influencer placements and social seeding.

    Strong business rule:
    - bloggers / influencers / KOL / content creators -> Special projects;
    - seeding / посевы -> Special projects;
    - targeting descriptions such as "интересы: блогеры" must not be mistaken for a format.
    """
    t = " | ".join(_norm(v) for v in values if v not in (None, ""))
    if not t:
        return False

    # "Посевы" are an explicit placement type and always a special project.
    if re.search(r"\bпосев\w*|\bsocial\s+seeding\b|\bseeding\b|\bseeded\s+placement\b", t):
        return True

    creator = bool(re.search(
        r"\bблогер\w*|\bинфлюенс\w*|\bbloggers?\b|\binfluencers?\b|"
        r"\bkol\b|key\s+opinion\s+leaders?|\bлидер\w*\s+мнен\w*|"
        r"content\s+creators?|\bcreators?\b|контент[- ]?креатор\w*",
        t,
    ))
    if not creator:
        return False

    # Explicit collaboration/placement wording is conclusive even in a longer description.
    if re.search(
        r"интеграц|размещ|публикац|натив|обзор|пост|ролик|реклам|"
        r"integration|placement|collab|sponsor|native\s+post|branded\s+content",
        t,
    ):
        return True

    # A short standalone format such as "Блогеры", "Influencers", "VK блогеры" is valid.
    # Do not treat audience/targeting descriptions as the placement type.
    if len(t) <= 90 and not re.search(
        r"таргет|target(?:ing)?|интерес|interests?|аудитор|audience|сегмент",
        t,
    ):
        return True

    return False


def _row_social_special_signal(row: Sequence[Any]) -> str:
    """Return only cells that strongly identify bloggers/influencers or seeding."""
    hits: List[str] = []
    for cell in row[:45]:
        if cell in (None, ""):
            continue
        text = _display(cell)
        if text and _is_social_special_project_text(text):
            hits.append(text)
    return " | ".join(hits)

def _format_group(*values: Any, section: str = "") -> str:
    # First classify only the explicit row values (format / placement / platform).
    # A section name is a fallback and must never override an explicit creative format.
    t = " | ".join(_norm(v) for v in values if v not in (None, ""))
    sec = _norm(section)

    # Bloggers/influencers and social seeding are always special projects, regardless
    # of the social platform (VK, Instagram, Telegram, MAX, YouTube, Rutube, etc.).
    if _is_social_special_project_text(t, sec):
        return "Спецпроекты"

    # Yandex products must stay separate in splits. They have materially different
    # buying logic and must never be collapsed into one generic "Контекст" row.
    # Check RSYA before Direct because some templates mention both Yandex/Direct wording
    # and RSYA in one description.
    if re.search(r"yandex\s*[.\- ]?\s*rsya|яндекс[^|]{0,25}рся|\bрся\b", t):
        return "РСЯ (Yandex.RSYA)"
    if re.search(r"yandex\s*[.\- ]?\s*direct|яндекс[^|]{0,25}(поиск|директ)|\bяндекс\.поиск\b", t):
        return "Поиск (Yandex.Direct)"
    if re.search(r"промостраниц|promo\s*pages?|promopages?|yandex[^|]{0,25}promo", t):
        return "Промостраницы"

    if re.search(r"вериф|verification|adserv|adriver|brand safety|fraud|viewability", t):
        return "Верификация"
    if re.search(r"спецпроект|special project|native|натив|интеграц|стать|дочит|прочтен|брендирован|\borm\b", t):
        return "Спецпроекты"
    if re.search(r"контекст|search|поиск|директ|direct|sem\b|рся|rsa\b|yandex direct|яндекс директ", t):
        return "Контекст"
    if re.search(r"video|видео|olv\b|олв\b|pre.?roll|preroll|mid.?roll|instream|in.?stream|out.?stream|cpcv|cpv", t):
        return "Видео"
    if re.search(r"banner|баннер|display|rich media|static|статика|тизер|медийн|promo post|промопост|\bsocial\b|social nets?|соцсет|мобильн(?:ая|ой) реклам|тематическ(?:ие|их) сайт|fullscreen|full screen|playable|универсальн(?:ые|ое)? объяв|перетяжк|300[хx×]250|attention smart|интерстициал|interstitial", t):
        return "Баннеры"

    # Section-level fallback only when explicit row values did not resolve the format.
    if re.search(r"yandex\s*[.\- ]?\s*rsya|яндекс[^|]{0,25}рся|\bрся\b", sec):
        return "РСЯ (Yandex.RSYA)"
    if re.search(r"yandex\s*[.\- ]?\s*direct|яндекс[^|]{0,25}(поиск|директ)|\bяндекс\.поиск\b", sec):
        return "Поиск (Yandex.Direct)"
    if re.search(r"промостраниц|promo\s*pages?|promopages?|yandex[^|]{0,25}promo", sec):
        return "Промостраницы"
    if re.search(r"вериф|verification|adserv|adriver|brand safety|fraud|viewability", sec):
        return "Верификация"
    if re.search(r"спецпроект|special project|native|натив|интеграц|стать|дочит|прочтен|брендирован|\borm\b", sec):
        return "Спецпроекты"
    if re.search(r"контекст|search|поиск|директ|direct|sem\b|рся|rsa\b|yandex direct|яндекс директ", sec):
        return "Контекст"
    if re.search(r"olv\b|олв\b|video|видео", sec):
        return "Видео"
    if re.search(r"banner|баннер|display|social|соцсет|programmatic|программатик|мобильн(?:ая|ой) реклам|тематическ(?:ие|их) сайт|playable", sec):
        return "Баннеры"
    if re.search(r"native|спец|натив", sec):
        return "Спецпроекты"
    return "Не определено"


def _looks_like_section(row: Sequence[Any]) -> Optional[str]:
    vals = [_display(x) for x in row[:35] if x not in (None, "")]
    if not vals or len(vals) > 4:
        return None
    text = " | ".join(vals)
    group = _format_group(text)
    if group != "Не определено":
        return text
    return None


def _is_total_row(row: Sequence[Any]) -> bool:
    txt = " | ".join(_norm(x) for x in row[:45] if x not in (None, ""))
    if not txt:
        return False
    return bool(re.search(r"\btotal\b|тотал по каналу|итого по каналу|subtotal|подытог|общий итог|grand total", txt))


def _strip_bonus(platform: str) -> str:
    # Research suffixes and bonus markers are attributes, not platform identity.
    s = re.sub(r"(?i)\b(?:bonus|бонус(?:ом)?)\s*(?:bls|sl)\b", "", platform)
    s = re.sub(r"(?i)\b(?:bls|sl)\s*(?:bonus|бонус(?:ом)?)\b", "", s)
    s = re.sub(r"(?i)\b(?:bls|sl)\b", "", s)
    s = re.sub(r"(?i)\bbonus\b|\bбонус(?:ом|ный|ная|ное|ные)?\b", "", s)
    return re.sub(r"\s+", " ", s).strip(" -|,")


def _canonical_platform(platform: str) -> str:
    """Collapse obvious naming variants that are formats/products of the same platform."""
    raw = _strip_bonus(platform)
    t = _norm(raw)
    compact = re.sub(r"[^a-zа-я0-9]+", "", t)
    if re.search(r"(^|\b)(vk|вк|vkontakte)(\b|$)", t):
        return "VK"
    # Yandex Promopages are sometimes written as a standalone platform/product name
    # without the word Yandex. Normalize all such aliases to the Yandex platform so
    # that Promopages / Promo Pages / Промостраницы aggregate into one row:
    # Яндекс | Промостраницы.
    if re.search(r"promopages?", compact) or "промостраниц" in compact:
        return "Яндекс"
    if "яндекс" in t or re.search(r"(^|\b)yandex(\b|$)", t):
        return "Яндекс"
    if compact in {"mediatoday", "медиатудей"}:
        return "Media Today"
    if compact == "telegramads":
        return "Telegram Ads"
    if compact in {"yabbi", "ябби"}:
        return "Yabbi"
    if compact in {"astralab", "астралаб"}:
        return "Astra Lab"
    if re.match(r"^avito\b", t):
        return "Avito"
    if compact in {"babyru", "бэбиру", "бебиру"}:
        return "Baby.ru"
    if compact in {"slickjump", "сликджамп"}:
        return "SlickJump"
    if re.match(r"^genius\b", t):
        return "Genius"
    # Normalize cosmetic differences but preserve unknown seller names.
    return raw


def _platform_format_override(platform: str, format_group: str) -> str:
    """Apply hard business rules for platforms whose split format taxonomy is fixed."""
    p = _norm(platform)
    compact = re.sub(r"[^a-zа-я0-9]+", "", p)

    # Avito and Baby.ru are media inventory in this planner: display or OLV only.
    # If the generic classifier found video, keep it; every other result becomes banners.
    if re.match(r"^avito\b", p) or compact in {"babyru", "бэбиру", "бебиру"}:
        return "Видео" if format_group == "Видео" else "Баннеры"

    # SlickJump follows the same hard rule: only display or OLV.
    if compact in {"slickjump", "сликджамп"}:
        return "Видео" if format_group == "Видео" else "Баннеры"

    return format_group


FIELD_PATTERNS: Dict[str, Tuple[str, ...]] = {
    "platform": ("название сайта", "название площадки", "площадка", "site", "platform", "publisher", "sales house", "seller", "ресурс", "сайт"),
    "format": ("формат", "ad placement", "placement format", "ad size", "format", "размещение", "тип размещения"),
    "buying_model": ("модель закупки", "тип закупки", "buying model", "buy model", "pricing model", "purchase model"),
    "unit_type": ("unit type", "purchase unit", "buying unit", "единица закупки", "тип единицы", "единица"),
    "month": ("month", "месяц"),
    "period": ("период рк", "campaign period", "период размещения", "period", "flight dates"),
    "start": ("start date", "date start", "дата старта", "дата начала", "начало размещения", "start"),
    "end": ("end date", "date end", "finish date", "дата окончания", "окончание размещения", "finish", "end"),
    "verification": (
        "стоимость за услуги верификации", "verification cost", "верификация стоимость", "верификация total",
        "adserving total cost", "adserving cost", "total adserving", "верификатор стоимость",
        "верификация стоимость", "adserving total cost", "ad serving total cost",
    ),
    "budget_plus_verification": (
        "итоговая стоимость, без ндс", "итоговая стоимость без ндс", "total cost + adserving",
        "total cost incl adserving", "total cost with adserving", "media + verification", "media+verification",
        "бюджет до ак", "бюджет до агентской комиссии", "budget before agency", "budget pre agency",
        "cost before agency", "итого без ндс",
        "стоимость после скидки (до ак и до ндс)", "стоимость после скидки до ак и до ндс",
        "стоимость после скидки (до ак, до ндс)", "стоимость после скидки до ак до ндс",
    ),
    "media_budget": (
        "общая стоимость после скидки, без ндс", "общая стоимость размещения после скидки, без ндс",
        "total cost after discount, rur", "total cost after discount", "media net", "net media cost",
        "media budget", "бюджет без ндс", "бюджет до ндс", "бюджет",
        "стоимость после скидки (до ндс)", "стоимость после скидки до ндс",
        "стоимость заказа после скидки до ндс",
    ),
    "ac_amount": (
        "агентская комиссия", "агентская комиссия, руб", "ак, руб", "ак руб", "agency commission",
        "agency fee", "agency commission, rur", "agency fee, rur", "агентское вознаграждение",
        "сумма ак fix заказа (до ндс)", "сумма ак fix заказа до ндс", "сумма ак fix",
    ),
    "ac_rate": ("ак fix, %", "ак fix %", "ак, %", "ак %", "agency commission %", "agency fee %", "ставка ак", "ac %"),
    "budget_plus_ac": (
        "бюджет + ак", "бюджет+ак", "budget + ac", "budget+ac", "итого с ак", "total incl agency",
        "total including agency", "media + agency", "media+agency", "итого после ак",
        "стоимость после скидки (с ак до ндс)", "стоимость после скидки с ак до ндс",
    ),
}


def _header_label_score(label: str, field: str) -> float:
    t = _norm(label)
    if not t:
        return 0.0
    flat = re.sub(r"[^a-zа-я0-9%+]+", " ", t)
    flat = re.sub(r"\s+", " ", flat).strip()
    # A metric mentioning a website (visits/clicks/views) is not the platform column.
    if field == "platform" and "сайт" in t and "название сайта" not in t and "название площадки" not in t:
        if re.search(r"посещ|визит|переход|просмотр|клик|пользоват", t):
            return 0.0
    # VAT columns should never become pre-AC totals.
    if field in {"media_budget", "budget_plus_verification", "budget_plus_ac", "ac_amount"} and ("с ндс" in t or "with vat" in t or "incl vat" in t or "including vat" in t):
        return 0.0
    # Row-level finance fields must never bind to horizontal month subcolumns such as
    # "Бюджет | февраль". Monthly blocks are discovered independently below.
    if field in {"media_budget", "budget_plus_verification", "budget_plus_ac", "ac_amount", "verification"}:
        if _month_from_value(t) is not None and "20" not in t:
            return 0.0
    # Explicit final pre-AC budget should not match generic budget if it mentions agency.
    patterns = FIELD_PATTERNS[field]
    best = 0.0
    for p in patterns:
        pp = _norm(p)
        pp_flat = re.sub(r"[^a-zа-я0-9%+]+", " ", pp)
        pp_flat = re.sub(r"\s+", " ", pp_flat).strip()
        if t == pp or flat == pp_flat:
            best = max(best, 3.0)
        elif pp in t or (pp_flat and pp_flat in flat):
            best = max(best, 2.0 + min(len(pp_flat or pp), 40) / 100.0)
    # Prefer the actual Site/Platform column over a Sales house/Seller column.
    # The latter is useful only as a fallback; in LAB templates H=Sales house and I=Site.
    if field == "platform":
        if t in {"site", "platform", "площадка", "название сайта", "название площадки", "сайт"} and best > 0:
            best += 1.0
        elif "sales house" in t or t == "seller":
            best = min(best, 1.0)

    # Explicit creative format columns must outrank targeting/placement-description columns.
    # New LAB/OMD templates use both "Ad Placement & targetings" and
    # "Ad size (pixels) / Format". The latter is the actual format for splits.
    if field == "format":
        has_explicit_format = (
            "format" in t or "формат" in t or "ad size" in t
        )
        looks_like_targeting = (
            "target" in t or "таргет" in t
        )
        if has_explicit_format and best > 0:
            best += 1.0
        elif looks_like_targeting:
            best = min(best, 0.40)

    # Prevent generic "budget" from hijacking AC/total columns.
    if field == "media_budget" and ("ак" in t or "agency" in t):
        best = 0.0
    if field == "verification":
        if "ставка" in t or "rate" in t or "%" in t or "per unit" in t or "cost per unit" in t:
            best = 0.0
        elif best > 0 and not any(x in flat for x in ("стоимость", "cost", "total", "итого", "сумма")):
            # A bare group header such as "Верификация" is not the money column.
            best = 0.0
    if field == "ac_amount" and "%" in t:
        best = 0.0
    return best


def _combine_header_rows(matrix: List[List[Any]], start: int, height: int, max_cols: int = 160) -> List[str]:
    cols = min(max((len(matrix[r]) for r in range(start, min(len(matrix), start + height))), default=0), max_cols)
    labels: List[str] = []
    for c in range(cols):
        parts: List[str] = []
        for r in range(start, min(len(matrix), start + height)):
            if c < len(matrix[r]):
                v = _display(matrix[r][c])
                if v and v not in parts:
                    parts.append(v)
        labels.append(" | ".join(parts))
    return labels


def _map_header(labels: Sequence[str]) -> Tuple[Dict[str, int], float]:
    mapping: Dict[str, int] = {}
    score = 0.0
    for field in FIELD_PATTERNS:
        candidates: List[Tuple[float, int]] = []
        for i, label in enumerate(labels):
            sc = _header_label_score(label, field)
            if sc > 0:
                candidates.append((sc, i))
        if candidates:
            # Highest semantic score wins; on a tie prefer the left-most source column.
            # Wide LAB templates repeat Site/Platform again in operational/monthly blocks
            # to the right, while the real media table is on the left.
            candidates.sort(key=lambda x: (-x[0], x[1]))
            mapping[field] = candidates[0][1]
    # Hierarchical headers often have a group name in the left subcolumn only:
    # "Верификация" -> [Ставка] [Стоимость] or "Adserving" -> [Cost per unit] [Total cost].
    # Pick the adjacent total/cost subcolumn as the monetary verification field.
    if "verification" not in mapping:
        for i, label in enumerate(labels):
            cur = _norm(label)
            prev = _norm(labels[i - 1]) if i > 0 else ""
            if i > 0 and (cur in {"стоимость", "total cost", "итого", "сумма"} or cur.endswith(" total cost")):
                if any(x in prev for x in ("вериф", "adserv", "verification")):
                    mapping["verification"] = i
                    break

    if "platform" in mapping:
        score += 5
    if any(k in mapping for k in ("media_budget", "budget_plus_verification", "budget_plus_ac")):
        score += 5
    if "budget_plus_verification" in mapping:
        score += 2.0
    if "budget_plus_ac" in mapping:
        score += 2.0
    if "format" in mapping:
        score += 1.5
    if any(k in mapping for k in ("month", "period", "start")):
        score += 1.5
    if any(k in mapping for k in ("ac_amount", "ac_rate")):
        score += 2
    if "verification" in mapping:
        score += 1
    return mapping, score


@dataclass
class SplitRecord:
    sheet: str
    source_row: int
    platform: str
    format_group: str
    month: int
    year: int
    plan_budget: float
    plan_ac: float
    plan_total: float
    fact_budget: float = 0.0
    fact_ac: float = 0.0
    fact_total: float = 0.0
    fact_available: bool = False
    verification: float = 0.0
    source_format: str = ""
    source_class: str = ""
    source_plan: str = ""
    is_bonus: bool = False
    research_marker: str = ""
    research_status: str = ""
    research_cost: Optional[float] = None
    research_is_dedicated: bool = False

    # Backward-compatible aliases: the old split model was plan-only.
    @property
    def budget(self) -> float:
        return self.plan_budget

    @property
    def ac(self) -> float:
        return self.plan_ac

    @property
    def total(self) -> float:
        return self.plan_total

    @property
    def delta_budget(self) -> float:
        return (self.plan_budget - self.fact_budget) if self.fact_available else 0.0

    @property
    def delta_total(self) -> float:
        return (self.plan_total - self.fact_total) if self.fact_available else 0.0


@dataclass
class SplitResult:
    path: Path
    records: List[SplitRecord] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    scanned_sheets: int = 0
    detected_tables: int = 0
    skipped_rows: int = 0
    plan_sheets: List[str] = field(default_factory=list)
    fact_sheets: List[str] = field(default_factory=list)
    selected_sheets: List[str] = field(default_factory=list)
    physical_rows: int = 0
    duplicate_rows_removed: int = 0
    version_rows_replaced: int = 0
    delta_mismatches: int = 0
    source_plan_total: float = 0.0
    source_ac_total: float = 0.0
    source_total_total: float = 0.0
    records_plan_total: float = 0.0
    records_ac_total: float = 0.0
    records_total_total: float = 0.0
    split_plan_total: float = 0.0
    split_ac_total: float = 0.0
    split_total_total: float = 0.0
    conservation_ok: bool = True
    conservation_diff_plan: float = 0.0
    conservation_diff_ac: float = 0.0
    conservation_diff_total: float = 0.0

    def aggregate(self) -> Dict[str, Dict[str, Dict[int, Dict[str, float]]]]:
        out: Dict[str, Dict[str, Dict[int, Dict[str, float]]]] = {}
        for r in self.records:
            cell = out.setdefault(r.platform, {}).setdefault(r.format_group, {}).setdefault(
                r.month,
                {
                    "plan": 0.0, "plan_ac": 0.0, "plan_total": 0.0,
                    "fact": 0.0, "fact_ac": 0.0, "fact_total": 0.0,
                    "delta": 0.0, "delta_total": 0.0,
                    "verification": 0.0,
                    "record_count": 0.0, "fact_available_count": 0.0,
                },
            )
            cell["plan"] += r.plan_budget
            cell["plan_ac"] += r.plan_ac
            cell["plan_total"] += r.plan_total
            cell["verification"] += r.verification
            cell["record_count"] += 1.0
            if r.fact_available:
                cell["fact"] += r.fact_budget
                cell["fact_ac"] += r.fact_ac
                cell["fact_total"] += r.fact_total
                # Delta follows the source template convention: PLAN - FACT.
                cell["delta"] += r.plan_budget - r.fact_budget
                cell["delta_total"] += r.plan_total - r.fact_total
                cell["fact_available_count"] += 1.0
        return out

    def research_summary(self) -> List[Dict[str, Any]]:
        grouped: Dict[Tuple[str, str, str, bool], Dict[str, Any]] = {}
        seen_rows: Dict[Tuple[str, str, str, bool], set] = {}
        for r in self.records:
            if not r.research_marker:
                continue
            key = (r.platform, r.research_marker, r.research_status or "COST_NOT_SEPARATED", bool(r.research_is_dedicated))
            item = grouped.setdefault(key, {
                "platform": r.platform, "type": r.research_marker,
                "status": r.research_status or "COST_NOT_SEPARATED",
                "dedicated": bool(r.research_is_dedicated),
                "plan": 0.0, "plan_ac": 0.0, "plan_total": 0.0, "rows": 0,
            })
            phys = (r.sheet, r.source_row)
            seen = seen_rows.setdefault(key, set())
            if phys not in seen:
                seen.add(phys); item["rows"] += 1
            if r.research_status == "PAID" and r.research_is_dedicated:
                item["plan"] += r.plan_budget
                item["plan_ac"] += r.plan_ac
                item["plan_total"] += r.plan_total
        out = []
        for item in grouped.values():
            if item["status"] == "BONUS":
                item["plan"] = item["plan_ac"] = item["plan_total"] = 0.0
            elif item["status"] != "PAID":
                item["plan"] = item["plan_ac"] = item["plan_total"] = None
            out.append(item)
        return sorted(out, key=lambda x: (str(x["platform"]).lower(), str(x["type"]).lower(), str(x["status"])))

    def totals(self) -> Dict[str, float]:
        comparable = [r for r in self.records if r.fact_available]
        out = {
            "plan": sum(r.plan_budget for r in self.records),
            "plan_ac": sum(r.plan_ac for r in self.records),
            "plan_total": sum(r.plan_total for r in self.records),
            "fact": sum(r.fact_budget for r in comparable),
            "fact_ac": sum(r.fact_ac for r in comparable),
            "fact_total": sum(r.fact_total for r in comparable),
            "delta": sum(r.plan_budget - r.fact_budget for r in comparable),
            "delta_total": sum(r.plan_total - r.fact_total for r in comparable),
            "verification": sum(r.verification for r in self.records),
            "fact_records": float(len(comparable)),
            "records": float(len(self.records)),
        }
        # Backward-compatible aliases for code that still refers to the plan-only names.
        out["budget"] = out["plan"]
        out["ac"] = out["plan_ac"]
        out["total"] = out["plan_total"]
        return out


def _row_get(row: Sequence[Any], mapping: Dict[str, int], key: str) -> Any:
    c = mapping.get(key)
    return row[c] if c is not None and c < len(row) else None


def _authoritative_total_value(
    matrix: Sequence[Sequence[Any]], mapping: Dict[str, int], field: str,
    data_start: int, data_end: int,
) -> Optional[float]:
    """Read an explicit Excel Total cell for one finance field.

    LAB plans sometimes keep row-level finance for historical/fact blocks while the
    final Plan order total intentionally covers only the active order range. When a
    dedicated Total cell exists, it is the source of truth for that Plan finance field.
    """
    col = mapping.get(field)
    if col is None:
        return None
    for r in range(max(0, data_start), min(len(matrix), data_end)):
        row = matrix[r]
        if not _is_total_row(row):
            continue
        value = _to_number(row[col] if col < len(row) else None)
        if value is not None:
            return float(value)
    return None


def _reconcile_sheet_plan_ac_to_total(
    result: "SplitResult",
    source_finance: Dict[Tuple[str, int], Tuple[float, float, float]],
    sheet_name: str,
    target_ac: float,
) -> None:
    """Reconcile Plan AC to an explicit Excel Total without mixing Plan and Fact.

    Exact leading/trailing exclusions mirror formulas such as SUM(AA25:AA51).
    Only when the Total cannot be reproduced by a clean boundary exclusion do we
    proportionally reconcile Plan AC and emit a warning. Fact AC stays untouched.
    """
    keys = sorted((k for k in source_finance if k[0] == sheet_name), key=lambda x: x[1])
    if not keys:
        return
    current = sum(source_finance[k][1] for k in keys)
    if round(current + 1e-9, 2) == round(target_ac + 1e-9, 2):
        return
    if current <= 1e-12:
        return

    row_factor: Dict[int, float] = {row: 1.0 for _, row in keys}
    method = "proportional"
    excess = current - target_ac
    if excess > 0:
        prefix = 0.0
        for _, row in keys:
            prefix += source_finance[(sheet_name, row)][1]
            if round(prefix + 1e-9, 2) == round(excess + 1e-9, 2):
                for _, rr in keys:
                    if rr <= row:
                        row_factor[rr] = 0.0
                method = f"leading rows through {row}"
                break
        if method == "proportional":
            suffix = 0.0
            for _, row in reversed(keys):
                suffix += source_finance[(sheet_name, row)][1]
                if round(suffix + 1e-9, 2) == round(excess + 1e-9, 2):
                    for _, rr in keys:
                        if rr >= row:
                            row_factor[rr] = 0.0
                    method = f"trailing rows from {row}"
                    break

    if method == "proportional":
        factor = target_ac / current
        for _, row in keys:
            row_factor[row] = factor

    for key in keys:
        plan, ac, _total = source_finance[key]
        new_ac = ac * row_factor[key[1]]
        source_finance[key] = (plan, new_ac, plan + new_ac)

    for rec in result.records:
        if rec.sheet != sheet_name or rec.source_row not in row_factor:
            continue
        rec.plan_ac *= row_factor[rec.source_row]
        rec.plan_total = rec.plan_budget + rec.plan_ac

    after = sum(source_finance[k][1] for k in keys)
    residual = target_ac - after
    if abs(residual) >= 0.0000001:
        last_key = next((k for k in reversed(keys) if abs(source_finance[k][1]) > 0 or target_ac == 0), keys[-1])
        plan, ac, _total = source_finance[last_key]
        source_finance[last_key] = (plan, ac + residual, plan + ac + residual)
        candidates = [z for z in result.records if z.sheet == sheet_name and z.source_row == last_key[1]]
        if candidates:
            candidates[-1].plan_ac += residual
            candidates[-1].plan_total = candidates[-1].plan_budget + candidates[-1].plan_ac

    result.warnings.append(
        f"{sheet_name}: План АК приведён к явному Excel Total {target_ac:.2f} руб.; "
        f"строковая сумма была {current:.2f} руб. ({method})."
    )


def _row_month_splits(row: Sequence[Any], mapping: Dict[str, int], sheet_name: str, default_year: int) -> List[Tuple[int, int, float]]:
    """Return (year, month, weight). Explicit Month wins; otherwise allocate period by active days."""
    mv = _row_get(row, mapping, "month")
    m = _month_from_value(mv)
    if m:
        year = default_year
        if isinstance(mv, (dt.date, dt.datetime)):
            year = mv.year
        else:
            ym = re.search(r"20\d{2}", _display(mv))
            if ym:
                year = int(ym.group())
        return [(year, m, 1.0)]

    start = _parse_date(_row_get(row, mapping, "start"))
    end = _parse_date(_row_get(row, mapping, "end"))
    if not start:
        ps, pe = _parse_period(_row_get(row, mapping, "period"), default_year)
        start, end = ps, pe
    if start and not end:
        end = start
    if start and end:
        if end < start:
            start, end = end, start
        total_days = (end - start).days + 1
        parts: List[Tuple[int, int, float]] = []
        cur = dt.date(start.year, start.month, 1)
        while cur <= end:
            mend = dt.date(cur.year, cur.month, calendar.monthrange(cur.year, cur.month)[1])
            seg_start, seg_end = max(start, cur), min(end, mend)
            if seg_start <= seg_end:
                days = (seg_end - seg_start).days + 1
                parts.append((cur.year, cur.month, days / total_days))
            if cur.month == 12:
                cur = dt.date(cur.year + 1, 1, 1)
            else:
                cur = dt.date(cur.year, cur.month + 1, 1)
        return parts

    # Last fallback: sheet name carries month.
    m = _month_from_value(sheet_name)
    if m:
        ym = re.search(r"20\d{2}", sheet_name)
        return [(int(ym.group()) if ym else default_year, m, 1.0)]
    return []


def _table_candidates(matrix: List[List[Any]]) -> List[Tuple[int, int, Dict[str, int], float]]:
    out: List[Tuple[int, int, Dict[str, int], float]] = []
    search_rows = min(320, len(matrix))
    for start in range(search_rows):
        best: Optional[Tuple[int, Dict[str, int], float]] = None
        for h in (1, 2, 3):
            labels = _combine_header_rows(matrix, start, h)
            mapping, score = _map_header(labels)
            score -= (h - 1) * 0.25
            if score >= 9.0 and (best is None or score > best[2]):
                best = (h, mapping, score)
        if best:
            h, mapping, score = best
            if out and start <= out[-1][0] + out[-1][1] + 2:
                if score > out[-1][3]:
                    out[-1] = (start, h, mapping, score)
            else:
                out.append((start, h, mapping, score))
    return out



@dataclass
class _HorizontalMonthBlock:
    header_row: int
    start_col: int
    kind: str
    label: str
    score: float
    month_cols: Dict[int, int] = field(default_factory=dict)


def _month_run(row: Sequence[Any], start_col: int) -> Dict[int, int]:
    """Return a contiguous calendar run (2+ month headers), allowing partial years."""
    first = _month_from_value(row[start_col]) if start_col < len(row) else None
    if first is None:
        return {}
    out: Dict[int, int] = {first: start_col}
    expected = first % 12 + 1
    for cc in range(start_col + 1, len(row)):
        m = _month_from_value(row[cc])
        if m is None or m != expected or m in out:
            break
        out[m] = cc
        expected = m % 12 + 1
        if len(out) >= 12:
            break
    return out if len(out) >= 2 else {}


def _block_context(matrix: List[List[Any]], header_row: int, start_col: int, width: int = 12) -> str:
    """Read the nearest semantic group label above a horizontal month block."""
    parts: List[str] = []
    for rr in range(header_row - 1, max(-1, header_row - 7), -1):
        if rr < 0 or rr >= len(matrix):
            continue
        row = matrix[rr]
        vals: List[str] = []
        for cc in range(max(0, start_col - 1), min(len(row), start_col + width)):
            v = _display(row[cc])
            if v and _month_from_value(v) is None and v not in vals:
                vals.append(v)
        if vals:
            parts.extend(vals)
            break
    return " | ".join(parts)


def _find_budget_month_blocks(
    matrix: List[List[Any]],
    header_start: int,
    data_start: int,
    data_end: int,
    mapping: Dict[str, int],
) -> Dict[str, Optional[_HorizontalMonthBlock]]:
    """Detect PLAN / FACT / DELTA monthly money blocks, including partial-year layouts."""
    candidates: List[_HorizontalMonthBlock] = []
    r0 = max(0, header_start - 8)
    r1 = min(len(matrix), header_start + 7)
    for rr in range(r0, r1):
        row = matrix[rr]
        cc = 0
        while cc < len(row):
            run = _month_run(row, cc)
            if not run:
                cc += 1
                continue
            width = max(run.values()) - min(run.values()) + 1
            label = _block_context(matrix, rr, cc, width)
            t = _norm(label)
            if re.search(r"объем|volume|impression|показ", t) and not re.search(r"бюджет|budget|стоимост|cost", t):
                cc += width
                continue
            if re.search(r"разниц|delta", t):
                kind, base = "delta", 145.0
            elif re.search(r"факт|fact|actual", t) and re.search(r"бюджет|budget|стоимост|cost", t):
                kind, base = "fact", 140.0
            elif re.search(r"план|plan", t) and re.search(r"бюджет|budget|стоимост|cost", t):
                kind, base = "plan", 145.0
            elif re.search(r"бюджет|budget|стоимост|cost", t):
                kind, base = "generic", 115.0
            else:
                cc += width
                continue

            compared = matched = 0
            media_col = mapping.get("media_budget")
            if kind in {"plan", "generic"} and media_col is not None:
                for r in range(data_start, min(data_end, data_start + 500)):
                    rw = matrix[r]
                    if media_col >= len(rw):
                        continue
                    expected = _to_number(rw[media_col])
                    if expected is None or abs(expected) < 1e-9:
                        continue
                    vals = [_to_number(rw[col]) if col < len(rw) else None for col in run.values()]
                    actual = sum(v or 0.0 for v in vals)
                    if abs(actual) < 1e-9:
                        continue
                    compared += 1
                    tol = max(1.0, abs(expected) * 0.001)
                    if abs(actual - expected) <= tol:
                        matched += 1
            validation = (matched / compared * 25.0) if compared else 0.0
            candidates.append(_HorizontalMonthBlock(rr, cc, kind, label, base + validation, dict(run)))
            cc += width

    def pick(kind: str) -> Optional[_HorizontalMonthBlock]:
        items = [b for b in candidates if b.kind == kind]
        if not items:
            return None
        return sorted(items, key=lambda b: (b.score, len(b.month_cols), -b.start_col), reverse=True)[0]

    return {
        "plan": pick("plan") or pick("generic"),
        "fact": pick("fact"),
        "delta": pick("delta"),
    }


def _find_budget_month_block(
    matrix: List[List[Any]], header_start: int, data_start: int, data_end: int, mapping: Dict[str, int]
) -> Optional[_HorizontalMonthBlock]:
    return _find_budget_month_blocks(matrix, header_start, data_start, data_end, mapping).get("plan")


def _horizontal_month_values(row: Sequence[Any], block: Optional[_HorizontalMonthBlock]) -> List[Optional[float]]:
    out: List[Optional[float]] = [None] * 12
    if block is None:
        return out
    for month, col in block.month_cols.items():
        out[month - 1] = _to_number(row[col]) if col < len(row) else None
    return out


def _find_activity_month_columns(matrix: List[List[Any]], header_start: int, default_year: int) -> Dict[int, Tuple[int, int]]:
    """Find dated activity columns: month -> (column, year)."""
    best: Dict[int, Tuple[int, int]] = {}
    for rr in range(max(0, header_start - 6), min(len(matrix), header_start + 6)):
        row = matrix[rr]
        cur: Dict[int, Tuple[int, int]] = {}
        for cc, value in enumerate(row[:220]):
            txt = _display(value)
            if not re.search(r"\d{1,2}[./-]\d{1,2}", txt):
                continue
            a, b = _parse_period(value, default_year)
            if not a or not b or (b - a).days > 45:
                continue
            cur[a.month] = (cc, a.year)
        if len(cur) > len(best):
            best = cur
    return best if len(best) >= 2 else {}


def _activity_month_weights(row: Sequence[Any], columns: Dict[int, Tuple[int, int]]) -> List[Tuple[int, int, float]]:
    vals: List[Tuple[int, int, float]] = []
    for month, (col, year) in columns.items():
        if col >= len(row):
            continue
        raw = row[col]
        num = _to_number(raw)
        if num is not None and abs(num) > 1e-12:
            vals.append((year, month, abs(num)))
        elif num is None and _display(raw):
            vals.append((year, month, 1.0))
    if not vals:
        return []
    # Calendar flags are normally 1/blank. If arbitrary values are present they can
    # represent activity intensity; use them only as relative weights.
    total = sum(v for _, _, v in vals)
    if total <= 0:
        total = float(len(vals))
        vals = [(y, m, 1.0) for y, m, _ in vals]
    return [(y, m, v / total) for y, m, v in vals]


def _sheet_family_key(name: str) -> str:
    t = _norm(name).replace("_", " ")
    t = re.sub(r"\b(доп\w*\s*бюдж\w*|upd\w*|update\w*|copy|копия|final|финал)\b", " ", t)
    t = re.sub(r"\(\d+\)|\b20\d{2}[._-]?\d{0,4}\b", " ", t)
    return re.sub(r"[^a-zа-я0-9]+", "", t)


def _has_explicit_version_marker(name: str) -> bool:
    """Allow cross-sheet dedupe only for explicitly marked sheet versions.

    Flight numbers and calendar years are not version markers: those sheets stay additive.
    """
    t = _norm(name).replace("_", " ")
    return bool(re.search(
        r"\b(final|финал|approved|согласован|upd|update|updated|апдейт|обновлен|new|новая|новый|новое|copy|копия)\b|доп\w*\s*бюдж",
        t, re.I,
    ))


def _sheet_preference_score(name: str, order: int = 0) -> float:
    """Prefer explicit updated/final media-plan versions; workbook order is tie-breaker."""
    t = _norm(name)
    score = float(order) / 10000.0
    if re.search(r"\b(final|финал|approved|согласован)\b", t): score += 40.0
    if re.search(r"\b(upd|update|updated|апдейт|обновлен)\b", t): score += 30.0
    if re.search(r"доп\w*\s*бюдж", t): score += 25.0
    if re.search(r"\b(new|новая|новый|новое)\b", t): score += 15.0
    if re.search(r"\b(copy|копия)\b", t): score -= 10.0
    return score


def _row_text_signature(row: Sequence[Any]) -> Tuple[str, ...]:
    vals: List[str] = []
    for v in row[:32]:
        if v in (None, "") or isinstance(v, (int, float, bool)):
            continue
        t = _norm(v)
        if t and not t.startswith("="):
            vals.append(t)
    return tuple(vals)


def _infer_sheet_year(matrix: List[List[Any]], default_year: int) -> int:
    """Infer financial calendar year from top metadata/date headers."""
    counts: Dict[int, int] = {}
    for row in matrix[:40]:
        for value in row[:120]:
            for y in re.findall(r"\b(20\d{2})\b", _display(value)):
                yi = int(y)
                counts[yi] = counts.get(yi, 0) + 1
    if counts:
        return sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))[0][0]
    return default_year


def parse_split_workbook(
    path: str | Path,
    default_year: int = 2026,
    selected_sheets: Optional[Sequence[str]] = None,
    selected_sheet_groups: Optional[Sequence[Sequence[str]]] = None,
) -> SplitResult:
    path = Path(path)
    result = SplitResult(path=path)
    allowed = set(selected_sheets) if selected_sheets is not None else None
    result.selected_sheets = list(selected_sheets or [])
    # Cross-sheet deduplication is allowed only inside an explicit version family.
    # Different plans, flights and calendar years are additive even when their rows look alike.
    sheet_group_id: Dict[str, int] = {}
    version_group_token: Dict[str, Any] = {}
    if selected_sheet_groups is not None:
        for idx, group in enumerate(selected_sheet_groups):
            names = [str(sheet) for sheet in group]
            for sheet in names:
                sheet_group_id[sheet] = idx
            families: Dict[str, List[str]] = {}
            for sheet in names:
                families.setdefault(_sheet_family_key(sheet), []).append(sheet)
            for family, members in families.items():
                if len(members) > 1 and any(_has_explicit_version_marker(x) for x in members):
                    token = ("plan_version", idx, family)
                    for sheet in members:
                        version_group_token[sheet] = token
    seen_physical: set[Tuple[str, int]] = set()
    cross_sheet_seen: Dict[Tuple[Any, ...], Tuple[str, int, Tuple[Any, ...], float]] = {}
    source_finance: Dict[Tuple[str, int], Tuple[float, float, float]] = {}
    authoritative_sheet_ac: Dict[str, float] = {}

    with XlsxWorkbook(path) as wb:
        all_names = wb.sheet_names()
        scan_names = [n for n in all_names if allowed is None or n in allowed]
        result.scanned_sheets = len(scan_names)
        for sheet_order, sheet_name in enumerate(scan_names):
            ns = _norm(sheet_name)
            if any(x in ns for x in ("справоч", "инструкц", "методолог", "калибров", "readme")):
                continue
            sh = wb.read_sheet(sheet_name, max_rows=12000, max_cols=260)
            matrix = sh.matrix
            sheet_year = _infer_sheet_year(matrix, default_year)
            tables = _table_candidates(matrix)
            if not tables:
                continue
            result.detected_tables += len(tables)

            for t_index, (header_start, header_h, mapping, _score) in enumerate(tables):
                data_start = header_start + header_h
                next_header = tables[t_index + 1][0] if t_index + 1 < len(tables) else len(matrix)
                explicit_ac_total = _authoritative_total_value(matrix, mapping, "ac_amount", data_start, next_header)
                if explicit_ac_total is not None:
                    authoritative_sheet_ac[sheet_name] = authoritative_sheet_ac.get(sheet_name, 0.0) + explicit_ac_total
                month_blocks = _find_budget_month_blocks(matrix, header_start, data_start, next_header, mapping)
                plan_block = month_blocks.get("plan")
                fact_block = month_blocks.get("fact")
                delta_block = month_blocks.get("delta")
                activity_cols = _find_activity_month_columns(matrix, header_start, sheet_year)
                if plan_block and sheet_name not in result.plan_sheets:
                    result.plan_sheets.append(sheet_name)
                if fact_block and sheet_name not in result.fact_sheets:
                    result.fact_sheets.append(sheet_name)

                blank_run = 0
                current_section = ""
                for r in range(data_start, next_header):
                    physical_key = (sheet_name, r)
                    if physical_key in seen_physical:
                        continue
                    row = matrix[r]
                    if all(v in (None, "") for v in row[:max(mapping.values(), default=0) + 1]):
                        blank_run += 1
                        if blank_run >= 18:
                            break
                        continue
                    blank_run = 0

                    sec = _looks_like_section(row)
                    platform_raw = _row_get(row, mapping, "platform")
                    budget_probe = _to_number(_row_get(row, mapping, "budget_plus_verification"))
                    if budget_probe is None:
                        budget_probe = _to_number(_row_get(row, mapping, "media_budget"))
                    if sec and budget_probe is None:
                        current_section = sec
                        continue
                    if _is_total_row(row):
                        continue

                    raw_platform = _display(platform_raw)
                    source_format = _display(_row_get(row, mapping, "format"))
                    raw_text = " | ".join(_display(v) for v in row[:55] if v not in (None, ""))
                    is_bonus, research_marker = placement_markers(raw_platform, source_format, raw_text)
                    research_marker, research_status, research_cost, research_is_dedicated = research_details(
                        raw_platform, source_format, raw_text, None
                    )
                    canonical, _match_reason, _conf = canonicalize_platform_name(raw_platform)
                    platform = canonical or _canonical_platform(raw_platform)
                    if not platform and research_is_dedicated:
                        platform = "Исследование"
                    if not platform or _norm(platform) in {"site", "platform", "площадка", "ресурс", "сайт"}:
                        continue

                    model_text = _display(_row_get(row, mapping, "buying_model")) + " | " + raw_text
                    model = detect_model(model_text, row, mapping)
                    placement_class, class_reason = classify_placement(
                        platform=platform, fmt=source_format, raw=raw_text, model=model,
                        legacy_channel=current_section or None,
                    )
                    if research_is_dedicated:
                        format_group = "Исследования"
                        class_reason = f"dedicated research row: {research_marker}"
                    elif placement_class is None:
                        # Technical rows remain visible only if they actually carry money.
                        format_group = "Техническая строка"
                    else:
                        format_group = placement_class

                    media_budget_raw = _to_number(_row_get(row, mapping, "media_budget"))
                    media_budget = media_budget_raw or 0.0
                    verification = _to_number(_row_get(row, mapping, "verification")) or 0.0
                    pre_ac = _to_number(_row_get(row, mapping, "budget_plus_verification"))
                    if pre_ac is None:
                        pre_ac = media_budget + verification
                    if abs(pre_ac) < 1e-12 and media_budget:
                        pre_ac = media_budget
                    research_marker, research_status, research_cost, research_is_dedicated = research_details(
                        raw_platform, source_format, raw_text, pre_ac
                    )
                    if research_is_dedicated:
                        format_group = "Исследования"

                    ac_amount = _to_number(_row_get(row, mapping, "ac_amount"))
                    ac_rate_raw = _to_number(_row_get(row, mapping, "ac_rate"))
                    explicit_total = _to_number(_row_get(row, mapping, "budget_plus_ac"))
                    if ac_amount is None and explicit_total is not None:
                        ac_amount = explicit_total - pre_ac

                    effective_rate = 0.0
                    if ac_rate_raw is not None:
                        effective_rate = ac_rate_raw if abs(ac_rate_raw) <= 1 else ac_rate_raw / 100.0
                    elif ac_amount is not None and abs(pre_ac) > 1e-9:
                        effective_rate = ac_amount / pre_ac
                    elif explicit_total is not None and abs(pre_ac) > 1e-9:
                        effective_rate = (explicit_total - pre_ac) / pre_ac
                    if ac_amount is None:
                        ac_amount = pre_ac * effective_rate
                    plan_row_total = explicit_total if explicit_total is not None else pre_ac + ac_amount

                    plan_values = _horizontal_month_values(row, plan_block)
                    fact_values = _horizontal_month_values(row, fact_block)
                    delta_values = _horizontal_month_values(row, delta_block)
                    plan_present = [v for v in plan_values if v is not None]
                    fact_present = [v for v in fact_values if v is not None]
                    plan_sum = sum(plan_present) if plan_present else 0.0

                    # A block named only "Бюджет" is an allocation profile, not a second
                    # financial source of truth. Reconcile its monthly proportions to the
                    # exact row-level pre-AC amount. Explicit "План" blocks stay untouched.
                    if plan_block is not None and plan_block.kind == "generic" and plan_present and abs(pre_ac) > 1e-9 and abs(plan_sum) > 1e-9:
                        scale = pre_ac / plan_sum
                        plan_values = [None if v is None else float(v) * scale for v in plan_values]
                        plan_present = [v for v in plan_values if v is not None]
                        plan_sum = sum(plan_present)

                    row_records: List[SplitRecord] = []
                    if plan_present or fact_present:
                        for month in range(1, 13):
                            pv = plan_values[month - 1]
                            fv = fact_values[month - 1]
                            plan_available = pv is not None
                            fact_available = fv is not None
                            if not plan_available and not fact_available:
                                continue
                            plan_budget = float(pv or 0.0)
                            fact_budget = float(fv or 0.0)
                            if abs(plan_sum) > 1e-9:
                                plan_ac = ac_amount * (plan_budget / plan_sum)
                            else:
                                plan_ac = plan_budget * effective_rate
                            plan_total = plan_budget + plan_ac
                            fact_ac = fact_budget * effective_rate if fact_available else 0.0
                            fact_total = fact_budget + fact_ac if fact_available else 0.0
                            if delta_values[month - 1] is not None and fact_available:
                                expected_delta = plan_budget - fact_budget
                                if abs(float(delta_values[month - 1]) - expected_delta) > max(1.0, abs(expected_delta) * 0.001):
                                    result.delta_mismatches += 1
                            if format_group == "Техническая строка" and abs(verification) < 1e-9:
                                month_verification = plan_budget
                            elif abs(plan_sum) > 1e-9:
                                month_verification = verification * (plan_budget / plan_sum)
                            else:
                                month_verification = 0.0
                            row_records.append(SplitRecord(
                                sheet=sheet_name, source_row=r + 1, platform=platform,
                                format_group=format_group, month=month, year=activity_cols.get(month, (0, sheet_year))[1],
                                plan_budget=plan_budget, plan_ac=plan_ac, plan_total=plan_total,
                                fact_budget=fact_budget, fact_ac=fact_ac, fact_total=fact_total,
                                fact_available=fact_available, verification=month_verification,
                                source_format=source_format, source_class=class_reason,
                                is_bonus=is_bonus, research_marker=research_marker,
                                research_status=research_status,
                                research_cost=(plan_budget if research_status == "PAID" and research_is_dedicated else (0.0 if research_status == "BONUS" else None)),
                                research_is_dedicated=research_is_dedicated,
                            ))
                    else:
                        if abs(pre_ac) < 1e-9 and abs(ac_amount or 0.0) < 1e-9 and abs(plan_row_total) < 1e-9:
                            continue
                        month_parts = _row_month_splits(row, mapping, sheet_name, sheet_year)
                        if not month_parts:
                            month_parts = _activity_month_weights(row, activity_cols)
                        if not month_parts:
                            result.skipped_rows += 1
                            result.warnings.append(f"{sheet_name}, строка {r+1}: не удалось определить месяц для «{platform}».")
                            continue
                        for year, month, weight in month_parts:
                            row_records.append(SplitRecord(
                                sheet=sheet_name, source_row=r + 1, platform=platform,
                                format_group=format_group, month=month, year=year,
                                plan_budget=pre_ac * weight,
                                plan_ac=(ac_amount or 0.0) * weight,
                                plan_total=plan_row_total * weight,
                                fact_budget=0.0, fact_ac=0.0, fact_total=0.0,
                                fact_available=False,
                                verification=(pre_ac * weight if format_group == "Техническая строка" and abs(verification) < 1e-9 else verification * weight),
                                source_format=source_format, source_class=class_reason,
                                is_bonus=is_bonus, research_marker=research_marker,
                                research_status=research_status,
                                research_cost=(pre_ac * weight if research_status == "PAID" and research_is_dedicated else (0.0 if research_status == "BONUS" else None)),
                                research_is_dedicated=research_is_dedicated,
                            ))

                    if not row_records:
                        continue
                    seen_physical.add(physical_key)

                    # Independent source-of-truth for the conservation test:
                    # row-level money read from the physical Excel placement before
                    # it is distributed into monthly SplitRecord cells.
                    source_plan_value = float(plan_sum if plan_present else pre_ac)
                    source_ac_value = float(ac_amount or 0.0)
                    source_total_value = source_plan_value + source_ac_value

                    # Same physical placement may appear on a base and an updated/dop-budget
                    # sheet. Identity excludes finance; changed finance is a version, not an
                    # additional placement. Unique rows on either sheet are still additive.
                    fin_sig = tuple((z.year, z.month, round(z.plan_budget, 2), round(z.plan_ac, 2), round(z.fact_budget, 2), z.fact_available) for z in row_records)
                    if sheet_name in sheet_group_id:
                        group_token = version_group_token.get(
                            sheet_name, ("sheet", sheet_group_id[sheet_name], sheet_name)
                        )
                    else:
                        # Without an explicit logical-plan map, never guess that two sheets are versions.
                        group_token = ("sheet", sheet_name)
                    semantic_sig = (
                        group_token, platform, format_group, _norm(source_format),
                        _row_text_signature(row),
                    )
                    current_score = _sheet_preference_score(sheet_name, sheet_order)
                    previous = cross_sheet_seen.get(semantic_sig)
                    if previous is not None and previous[0] != sheet_name:
                        prev_sheet, prev_row, prev_fin, prev_score = previous
                        if prev_fin == fin_sig:
                            result.duplicate_rows_removed += 1
                            continue
                        if current_score >= prev_score:
                            result.records = [z for z in result.records if not (z.sheet == prev_sheet and z.source_row == prev_row + 1)]
                            source_finance.pop((prev_sheet, prev_row + 1), None)
                            result.version_rows_replaced += 1
                        else:
                            result.version_rows_replaced += 1
                            continue
                    cross_sheet_seen[semantic_sig] = (sheet_name, r, fin_sig, current_score)
                    source_finance[(sheet_name, r + 1)] = (
                        source_plan_value, source_ac_value, source_total_value
                    )
                    result.records.extend(row_records)

    for sheet_name, target_ac in authoritative_sheet_ac.items():
        if sheet_name in version_group_token:
            # A per-sheet Total cannot safely override a partially retained version sheet.
            continue
        _reconcile_sheet_plan_ac_to_total(result, source_finance, sheet_name, target_ac)

    result.physical_rows = len({(z.sheet, z.source_row) for z in result.records})

    # Main financial invariant, checked to the kopeck:
    # source physical placements == plan records == aggregated Splits.
    result.source_plan_total = sum(v[0] for v in source_finance.values())
    result.source_ac_total = sum(v[1] for v in source_finance.values())
    result.source_total_total = sum(v[2] for v in source_finance.values())
    result.records_plan_total = sum(z.plan_budget for z in result.records)
    result.records_ac_total = sum(z.plan_ac for z in result.records)
    result.records_total_total = sum(z.plan_total for z in result.records)
    _agg = result.aggregate()
    result.split_plan_total = sum(
        cell["plan"] for formats in _agg.values() for months in formats.values() for cell in months.values()
    )
    result.split_ac_total = sum(
        cell["plan_ac"] for formats in _agg.values() for months in formats.values() for cell in months.values()
    )
    result.split_total_total = sum(
        cell["plan_total"] for formats in _agg.values() for months in formats.values() for cell in months.values()
    )
    def _kopeck_diff(a: float, b: float) -> float:
        return round(round(a + 1e-9, 2) - round(b + 1e-9, 2), 2)
    d1 = _kopeck_diff(result.source_plan_total, result.records_plan_total)
    d2 = _kopeck_diff(result.records_plan_total, result.split_plan_total)
    da1 = _kopeck_diff(result.source_ac_total, result.records_ac_total)
    da2 = _kopeck_diff(result.records_ac_total, result.split_ac_total)
    dt1 = _kopeck_diff(result.source_total_total, result.records_total_total)
    dt2 = _kopeck_diff(result.records_total_total, result.split_total_total)
    result.conservation_diff_plan = round(d1 + d2, 2)
    result.conservation_diff_ac = round(da1 + da2, 2)
    result.conservation_diff_total = round(dt1 + dt2, 2)
    result.conservation_ok = all(abs(x) < 0.005 for x in (d1, d2, da1, da2, dt1, dt2))
    if not result.conservation_ok:
        result.warnings.append(
            "ФИНАНСОВАЯ ОШИБКА: сумма исходных размещений, сумма плана и сумма Сплитов "
            "не совпадают до копейки. "
            f"План: source={result.source_plan_total:.2f}, records={result.records_plan_total:.2f}, split={result.split_plan_total:.2f}; "
            f"АК: source={result.source_ac_total:.2f}, records={result.records_ac_total:.2f}, split={result.split_ac_total:.2f}."
        )

    if not result.records:
        result.warnings.append("Не найдено строк, одновременно содержащих площадку и финансовый план/период.")
    if result.duplicate_rows_removed:
        result.warnings.append(f"Удалено точных межлистовых дублей финансовых строк: {result.duplicate_rows_removed}.")
    if result.version_rows_replaced:
        result.warnings.append(f"Строк финансовых версий заменено более актуальным источником: {result.version_rows_replaced}.")
    if result.delta_mismatches:
        result.warnings.append(f"Контроль План−Факт не совпал с исходным блоком дельты в {result.delta_mismatches} месячных ячейках.")
    missing_fact = [s for s in result.plan_sheets if s not in result.fact_sheets]
    if missing_fact:
        result.warnings.append(
            "Факт отсутствует как отдельный помесячный блок на листах: " + ", ".join(missing_fact) +
            ". Для них Факт и Дельта не рассчитываются и не подменяются нулем."
        )
    return result


# ------------------------ Minimal grouped XLSX export (stdlib only) ------------------------

def _col_letter(n: int) -> str:
    s = ""
    while n:
        n, rem = divmod(n - 1, 26)
        s = chr(65 + rem) + s
    return s


def _xml_cell(ref: str, value: Any, style: int = 0) -> str:
    if isinstance(value, (int, float)) and value is not None:
        return f'<c r="{ref}" s="{style}"><v>{float(value):.10f}</v></c>'
    txt = escape("" if value is None else str(value))
    return f'<c r="{ref}" s="{style}" t="inlineStr"><is><t>{txt}</t></is></c>'


def export_split_xlsx(result: SplitResult, out_path: str | Path) -> Path:
    """Export PLAN / FACT / DELTA split matrices to an Excel-compatible XLSX workbook."""
    import xlsxwriter

    out_path = Path(out_path)
    agg = result.aggregate()
    format_order = {
        "Баннеры": 0, "Видео": 1, "Промостраницы": 2,
        "Поиск (Yandex.Direct)": 3, "РСЯ (Yandex.RSYA)": 4,
        "Контекст": 5, "Спецпроекты": 6, "Верификация": 7, "Не определено": 9,
    }
    metrics = [
        ("plan", "План"),
        ("plan_ac", "АК план"),
        ("plan_total", "План + АК"),
        ("fact", "Факт"),
        ("fact_ac", "АК факт"),
        ("fact_total", "Факт + АК"),
        ("delta", "Дельта без АК"),
        ("delta_total", "Дельта с АК"),
    ]
    fact_metrics = {"fact", "fact_ac", "fact_total", "delta", "delta_total"}

    workbook = xlsxwriter.Workbook(str(out_path))
    workbook.set_properties({
        "title": "Сплиты",
        "subject": "План, факт и дельта по площадкам, форматам и месяцам",
        "author": "Media Reach Planner",
    })

    header_fmt = workbook.add_format({
        "bold": True, "font_color": "#FFFFFF", "bg_color": "#314A60",
        "border": 1, "border_color": "#D9E2E8", "align": "center", "valign": "vcenter",
    })
    text_fmt = workbook.add_format({"border": 1, "border_color": "#D9E2E8", "valign": "vcenter"})
    money_fmt = workbook.add_format({
        "border": 1, "border_color": "#D9E2E8", "num_format": "0.00",
        "align": "right", "valign": "vcenter",
    })
    delta_fmt = workbook.add_format({
        "border": 1, "border_color": "#D9E2E8", "num_format": '0.00;[Red]-0.00',
        "align": "right", "valign": "vcenter",
    })
    total_text_fmt = workbook.add_format({
        "bold": True, "font_color": "#FFFFFF", "bg_color": "#314A60",
        "border": 1, "border_color": "#D9E2E8", "valign": "vcenter",
    })
    total_money_fmt = workbook.add_format({
        "bold": True, "font_color": "#FFFFFF", "bg_color": "#314A60",
        "border": 1, "border_color": "#D9E2E8", "num_format": "0.00",
        "align": "right", "valign": "vcenter",
    })

    for metric, sheet_name in metrics:
        ws = workbook.add_worksheet(sheet_name)
        headers = ["Площадка", "Формат", *[MONTH_NAMES_RU[m] for m in range(1, 13)], "Итого"]
        for col, value in enumerate(headers):
            ws.write(0, col, value, header_fmt)

        row = 1
        totals_by_month = [0.0] * 12
        available_by_month = [False] * 12
        annual_total = 0.0
        annual_available = False
        value_fmt = delta_fmt if metric in {"delta", "delta_total"} else money_fmt

        for platform in sorted(agg, key=lambda x: x.lower()):
            formats = agg[platform]
            for fmt in sorted(formats, key=lambda x: (format_order.get(x, 8), x.lower())):
                months = formats[fmt]
                ws.write(row, 0, platform, text_fmt)
                ws.write(row, 1, fmt, text_fmt)
                row_total = 0.0
                row_available = False
                for month in range(1, 13):
                    cell = months.get(month)
                    available = bool(cell) and (metric not in fact_metrics or cell.get("fact_available_count", 0.0) > 0)
                    if available:
                        value = float(cell.get(metric, 0.0) or 0.0)
                        row_total += value
                        totals_by_month[month - 1] += value
                        available_by_month[month - 1] = True
                        row_available = True
                        ws.write_number(row, month + 1, value, value_fmt)
                    else:
                        ws.write_blank(row, month + 1, None, value_fmt)
                if row_available or metric not in fact_metrics:
                    annual_total += row_total
                    annual_available = True
                    ws.write_number(row, 14, row_total, value_fmt)
                else:
                    ws.write_blank(row, 14, None, value_fmt)
                row += 1

        ws.write(row, 0, "ИТОГО", total_text_fmt)
        ws.write(row, 1, "", total_text_fmt)
        for month_idx, value in enumerate(totals_by_month, start=0):
            col = month_idx + 2
            if available_by_month[month_idx] or metric not in fact_metrics:
                ws.write_number(row, col, value, total_money_fmt)
            else:
                ws.write_blank(row, col, None, total_money_fmt)
        if annual_available or metric not in fact_metrics:
            ws.write_number(row, 14, annual_total, total_money_fmt)
        else:
            ws.write_blank(row, 14, None, total_money_fmt)

        ws.set_column(0, 0, 24)
        ws.set_column(1, 1, 20)
        ws.set_column(2, 13, 16)
        ws.set_column(14, 14, 18)
        ws.set_row(0, 24)
        ws.freeze_panes(1, 2)
        ws.autofilter(0, 0, row, 14)
        ws.hide_gridlines(2)

    research = result.research_summary()
    if research:
        ws = workbook.add_worksheet("Исследования")
        headers = ["Площадка", "Исследование", "Статус", "План", "АК план", "План + АК", "Строк"]
        for col, value in enumerate(headers):
            ws.write(0, col, value, header_fmt)
        status_label = {
            "BONUS": "Бонусное",
            "PAID": "Платное",
            "COST_NOT_SEPARATED": "Стоимость не выделена отдельно",
        }
        for row_idx, item in enumerate(research, start=1):
            ws.write(row_idx, 0, item.get("platform") or "Исследование", text_fmt)
            ws.write(row_idx, 1, item.get("type") or "Исследование", text_fmt)
            ws.write(row_idx, 2, status_label.get(item.get("status"), item.get("status") or ""), text_fmt)
            for col, key in ((3, "plan"), (4, "plan_ac"), (5, "plan_total")):
                value = item.get(key)
                if value is None:
                    ws.write_blank(row_idx, col, None, money_fmt)
                else:
                    ws.write_number(row_idx, col, float(value), money_fmt)
            ws.write_number(row_idx, 6, int(item.get("rows") or 0), text_fmt)
        ws.set_column(0, 1, 24)
        ws.set_column(2, 2, 34)
        ws.set_column(3, 5, 16)
        ws.set_column(6, 6, 10)
        ws.freeze_panes(1, 0)
        ws.autofilter(0, 0, len(research), len(headers) - 1)
        ws.hide_gridlines(2)

    workbook.close()
    return out_path

