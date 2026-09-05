from __future__ import annotations
import json, datetime as dt, math, re
from pathlib import Path
from collections import defaultdict

from engine import (
    ReachParams, apply_reach, discover_media_plan_groups, discover_workbook_structure,
    parse_media_plan, build_plan_node, intersection_breakdown, selected_summary,
    selected_channel_summary, flight_channel_kpi_summary, combine_reach_union,
)
from splits import parse_split_workbook, export_split_xlsx, MONTH_NAMES_RU

PLAN = None
SPLIT_RESULT = None
CURRENT_PATH = None
MULTI_REACH_CACHE_PATH = None
MULTI_REACH_CACHE = {}


def _date(v):
    return v.isoformat() if isinstance(v, (dt.date, dt.datetime)) else None

def _intervals(vals):
    return [[_date(a), _date(b)] for a,b in (vals or [])]

def _num(v):
    try:
        return None if v is None else float(v)
    except Exception:
        return None

def _json(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))

def _merge_intervals(intervals):
    clean = sorted((min(a,b), max(a,b)) for a,b in intervals if a and b)
    if not clean:
        return []
    out=[clean[0]]
    for a,b in clean[1:]:
        pa,pb=out[-1]
        if a <= pb + dt.timedelta(days=1):
            out[-1]=(pa,max(pb,b))
        else:
            out.append((a,b))
    return out


def discover(path: str) -> str:
    structure = discover_workbook_structure(path)
    groups = structure.plans
    return _json({
        "groups":[{
            "id":g.id,"label":g.label,"sheet_names":list(g.sheet_names),
            "brand":g.brand,"campaign":g.campaign,"line":g.line
        } for g in groups],
        "book":{
            "name":Path(path).name,
            "plan_count":len(groups),
            "service_sheet_count":sum(1 for s in structure.sheets if s.role in {"service","summary"}),
            "alternative_sheet_count":sum(1 for s in structure.sheets if s.role=="alternative_version"),
            "sheets":[{
                "name":s.name,"role":s.role,"reason":s.reason,
                "has_media_table":bool(s.has_media_table),"brand":s.brand,"campaign":s.campaign,"line":s.line,
                "variant_family":s.variant_family,"preferred_variant":bool(s.preferred_variant),
            } for s in structure.sheets],
            "variant_families":[{
                "id":v.id,"base_name":v.base_name,"sheet_names":list(v.sheet_names),
                "preferred_sheet":v.preferred_sheet,"reason":v.reason,
            } for v in structure.variants],
        },
    })


def _canonical_structure(plan):
    node=build_plan_node(plan)
    return {
        "level":"plan",
        "key":node.key,"label":node.label,"line":node.line,"brand":node.brand,"campaign":node.campaign,
        "flights":[{
            "level":"flight","id":f.id,"label":f.label,"campaign":f.info.campaign,
            "is_always_on":bool(f.info.is_common),
            "period_start":_date(f.info.period_start),"period_end":_date(f.info.period_end),
            "placements":[{
                "level":"placement","id":p.id,"sheet":p.placement.sheet,"source_row":p.placement.source_row+1,
                "channel":p.placement.channel,"placement_class":p.placement.placement_class,
                "placement_class_reason":p.placement.placement_class_reason,
                "platform":p.placement.platform,
                "platform_canonical":p.placement.platform_canonical,
                "platform_match_reason":p.placement.platform_match_reason,
                "platform_match_confidence":p.placement.platform_match_confidence,
                "platform_status":p.placement.platform_status,
                "platform_needs_review":bool(p.placement.platform_needs_review),
                "platform_suggested_canonical":p.placement.platform_suggested_canonical,
                "is_bonus":bool(p.placement.is_bonus),
                "research_marker":p.placement.research_marker,
                "research_status":p.placement.research_status,
                "research_cost":_num(p.placement.research_cost),
                "research_is_dedicated":bool(p.placement.research_is_dedicated),
                "format":p.placement.format,
                "buying_model":p.placement.buying_model,"budget":_num(p.placement.budget),
                "months":[{
                    "level":"month","key":m.key,"year":m.year,"month":m.month,
                    "period_start":_date(m.period_start),"period_end":_date(m.period_end),
                    "budget":_num(m.budget),"volume":_num(m.volume),
                    "source_budget":bool(m.source_budget),"source_volume":bool(m.source_volume),
                } for m in p.months],
            } for p in f.placements],
        } for f in node.flights],
    }


_MULTI_REACH_CACHE = {}

def load_plan(path: str, sheet_names_json: str = "[]") -> str:
    global PLAN, CURRENT_PATH, SPLIT_RESULT
    sheets = json.loads(sheet_names_json or "[]")
    PLAN = parse_media_plan(path, sheet_names=sheets or None)
    CURRENT_PATH = path
    SPLIT_RESULT = None

    channels=[]
    for x in sorted(PLAN.detail_rows(), key=lambda z:(PLAN.flight_ids().index(z.flight), z.source_row)):
        if x.channel not in channels:
            channels.append(x.channel)

    flow = defaultdict(lambda: defaultdict(list))
    for x in PLAN.detail_rows():
        ints=list(x.intervals or [])
        if not ints and x.start and x.end:
            ints=[(x.start,x.end)]
        flow[x.flight][x.channel or "Other"].extend(ints)
    flow_out={}
    for fid, by_ch in flow.items():
        flow_out[fid]={ch:_intervals(_merge_intervals(ints)) for ch,ints in by_ch.items()}

    flights=[]
    for f in PLAN.flights:
        flights.append({
            "id":f.id,"label":f.label,"sheet":f.sheet,"campaign":f.campaign,
            "period_start":_date(f.period_start),"period_end":_date(f.period_end),
            "ta_name":f.ta_name,"universe":_num(f.universe),"universe_source":f.universe_source,
            "intervals":_intervals(f.intervals),
            "source_reach_people_1p":_num(f.source_reach_people_1p),
            "source_reach_pct_1p":_num(f.source_reach_pct_1p),
            "is_common":bool(f.is_common),
        })
    new_platforms={}
    for x in PLAN.detail_rows():
        if x.platform_status=="NEW_PLATFORM" and x.platform:
            key=x.platform_canonical or x.platform
            item=new_platforms.setdefault(key,{"source_names":set(),"suggestions":set()})
            item["source_names"].add(x.platform)
            if x.platform_suggested_canonical:
                item["suggestions"].add(x.platform_suggested_canonical)
    platform_warnings=list(PLAN.warnings)
    for name,item in sorted(new_platforms.items()):
        sources=", ".join(sorted(item["source_names"]))
        suggestion=", ".join(sorted(item["suggestions"]))
        msg=f"Новая площадка: {name}. Исходное написание: {sources}. Требуется однократная проверка перед добавлением в справочник."
        if suggestion:
            msg+=f" Возможный кандидат: {suggestion}."
        platform_warnings.append(msg)

    result={
        "display_name":PLAN.display_name,"brand":PLAN.brand,"campaign":PLAN.campaign,"line":PLAN.line,
        "universe":_num(PLAN.universe),"period_start":_date(PLAN.period_start),"period_end":_date(PLAN.period_end),
        "warnings":platform_warnings,"new_platforms":[{
            "canonical":name,
            "source_names":sorted(item["source_names"]),
            "suggestions":sorted(item["suggestions"]),
        } for name,item in sorted(new_platforms.items())],
        "flights":flights,"channels":channels,
        "placement_count":len(PLAN.detail_rows()),"total_count":len(PLAN.total_rows()),
        "flow_schedule":flow_out,"structure":_canonical_structure(PLAN),
    }
    return _json(result)


def calculate(params_json: str) -> str:
    if PLAN is None:
        raise RuntimeError("Медиаплан не загружен")
    q=json.loads(params_json)
    selected=q.get("selected_flights") or PLAN.flight_ids()
    universe=float(q.get("universe") or PLAN.universe or 15182450)
    reachability={int(k):float(v) for k,v in (q.get("reachability") or {}).items() if v is not None}
    selected_freqs=tuple(int(x) for x in (q.get("selected_frequencies") or [1,2,3,4]))
    eff=int(q.get("effective_frequency") or 3)
    p=ReachParams(
        universe=universe,
        lag_visible_share=float(q.get("lag_visible_share",0.65)),
        cookie_people=float(q.get("cookie_people",2.4)),
        target_affinity=float(q.get("target_affinity",0.65)),
        reachability_coefficients=reachability,
        selected_frequencies=selected_freqs,
        effective_frequency=eff,
    )
    apply_reach(PLAN,p)
    # Intersection has three modes in Web 0.39:
    # total (default fixed coefficient), detailed (factor product), auto (legacy model).
    intersection_mode=str(q.get("intersection_mode") or "total").lower()
    detail=q.get("intersection_detail") or {}
    complexity=detail.get("complexity") or q.get("complexity") or "Простая"
    factor_overrides={}
    manual_final=None
    if intersection_mode == "total":
        raw=q.get("manual_intersection", 0.85)
        manual_final=float(0.85 if raw in (None, "") else raw)
    elif intersection_mode == "detailed":
        raw_factors=detail.get("factors") or {}
        # Flights and duration are represented separately in the UI but the core period
        # factor is their product. Channel factor is neutral in this manual model because
        # the user requested platforms/rows/flights/duration/audience/complexity explicitly.
        audience=float(raw_factors.get("audience",1.0))
        comp=float(raw_factors.get("complexity",1.0))
        platforms=float(raw_factors.get("platforms",1.0))
        rows=float(raw_factors.get("rows",1.0))
        flights=float(raw_factors.get("flights",1.0))
        duration=float(raw_factors.get("duration",1.0))
        factor_overrides={
            "audience":audience,
            "complexity":comp,
            "platforms":platforms,
            "rows":rows,
            "channels":1.0,
            "period":flights*duration,
        }
    # auto -> no overrides / no manual final
    inter=intersection_breakdown(
        PLAN, selected, universe,
        complexity=complexity,
        factor_overrides=factor_overrides,
        manual_final=manual_final,
    )
    summ=selected_summary(PLAN,selected,p,inter)
    channel_summaries=selected_channel_summary(PLAN,selected,p,inter)

    # Per-flight / channel KPIs for the flowchart.
    flight_kpis={}
    for fid in selected:
        flight_kpis[fid]={}
        for ch in {x.channel for x in PLAN.detail_rows([fid])}:
            k=flight_channel_kpi_summary(PLAN,fid,ch,p)
            flight_kpis[fid][ch]={
                "budget":_num(k.get("budget")),"models":list(k.get("models") or []),
                "reach":{a:_num(b) for a,b in (k.get("reach") or {}).items()},
                "frequency":_num(k.get("frequency")),"performance":[[a,_num(b)] for a,b in (k.get("performance") or [])],
            }

    # Detailed rows.
    details=[]
    for x in sorted(PLAN.detail_rows(selected), key=lambda z:(PLAN.flight_ids().index(z.flight), z.source_row)):
        details.append({
            "flight":x.flight,"flight_label":x.flight_label,"channel":x.channel,
            "placement_class":x.placement_class,"placement_class_reason":x.placement_class_reason,
            "platform":x.platform,"platform_canonical":x.platform_canonical,
            "platform_match_reason":x.platform_match_reason,
            "platform_match_confidence":x.platform_match_confidence,
            "platform_status":x.platform_status,
            "platform_needs_review":bool(x.platform_needs_review),
            "platform_suggested_canonical":x.platform_suggested_canonical,
            "is_bonus":bool(x.is_bonus),
            "research_marker":x.research_marker,
            "research_status":x.research_status,
            "research_cost":_num(x.research_cost),
            "research_is_dedicated":bool(x.research_is_dedicated),
            "format":x.format,
            "buying_model":x.buying_model,"budget":_num(x.budget),"impressions":_num(x.impressions),
            "tech_reach":_num(x.tech_reach),"frequency":_num(x.frequency),
            "start":_date(x.start),"end":_date(x.end),"intervals":_intervals(x.intervals),
            "target_kpi_label":x.target_kpi_label,"target_kpi_value":_num(x.target_kpi_value),
            "reach":{a:_num(b) for a,b in (x.reach or {}).items()},"sheet":x.sheet,"source_row":x.source_row+1,
        })

    # Detection data for the editable detailed-intersection UI.
    reach_selected=[fid for fid in selected if not (PLAN.flight_info(fid) and PLAN.flight_info(fid).is_common)] or list(selected)
    selected_rows=PLAN.detail_rows(reach_selected)
    total_rows=len(selected_rows)
    flight_count=max(1,len(reach_selected))

    def _months_for_flight(fid):
        info=PLAN.flight_info(fid)
        intervals=list((info.intervals if info else None) or [])
        if not intervals and info and info.period_start and info.period_end:
            intervals=[(info.period_start,info.period_end)]
        months=set()
        for a,b in intervals:
            cur=dt.date(a.year,a.month,1)
            endm=dt.date(b.year,b.month,1)
            while cur<=endm:
                months.add((cur.year,cur.month))
                cur=dt.date(cur.year + (1 if cur.month==12 else 0), 1 if cur.month==12 else cur.month+1, 1)
        return len(months)
    durations=[_months_for_flight(fid) for fid in reach_selected]
    durations=[x for x in durations if x>0]
    duration_months=(sum(durations)/len(durations)) if durations else 1.0

    if universe < 7_500_000:
        audience_size_category, audience_suggested = "Очень маленькая", 0.70
    elif universe < 12_000_000:
        audience_size_category, audience_suggested = "Маленькая", 0.80
    else:
        audience_size_category, audience_suggested = "Большая", 1.00

    platform_suggested = 1.00 if inter.platform_count<=1 else (0.95 if inter.platform_count==2 else (0.90 if inter.platform_count<=4 else 0.80))
    rows_suggested = 1.00 if total_rows<=1 else (0.95 if total_rows<=3 else 0.90)
    flights_suggested = 1.00 if flight_count<=1 else 0.90
    duration_suggested = 1.00 if duration_months<=1.0 else (0.95 if duration_months<=3.0 else 0.90)
    complexity_clean = "Сложная" if str(complexity).lower().startswith("слож") else "Простая"
    complexity_suggested = 0.90 if complexity_clean=="Сложная" else 1.00
    detailed_suggested={
        "audience":audience_suggested,
        "complexity":complexity_suggested,
        "platforms":platform_suggested,
        "rows":rows_suggested,
        "flights":flights_suggested,
        "duration":duration_suggested,
    }
    detailed_product=1.0
    for v in detailed_suggested.values(): detailed_product*=v

    return _json({
        "summary":{
            "selected_flights":list(summ.selected_flights),"budget":_num(summ.budget),"impressions":_num(summ.impressions),
            "tech_reach":_num(summ.tech_reach),"frequency":_num(summ.frequency),
            "reach":{a:_num(b) for a,b in (summ.reach or {}).items()},
            "performance":[[a,_num(b)] for a,b in (summ.performance or [])],"warning":summ.warning,
        },
        "intersection":{
            "mode":inter.mode,"applied_product":inter.applied_product,"auto_product":inter.auto_product,
            "audience_category":inter.audience_category,"audience_coef_auto":inter.audience_coef_auto,
            "complexity":inter.complexity,"complexity_coef_auto":inter.complexity_coef_auto,
            "platform_count":inter.platform_count,"platform_coef_auto":inter.platform_coef_auto,
            "rows_per_platform":inter.rows_per_platform,"rows_coef_auto":inter.rows_coef_auto,
            "channel_count":inter.channel_count,"channel_coef_auto":inter.channel_coef_auto,
            "period_situation":inter.period_situation,"period_coef_auto":inter.period_coef_auto,
            "platform_detection":inter.platform_detection,"rows_detection":inter.rows_detection,"channel_detection":inter.channel_detection,
            "requested_mode":intersection_mode,
            "detected":{
                "platform_count":inter.platform_count,
                "row_count":total_rows,
                "flight_count":flight_count,
                "duration_months":duration_months,
                "audience_size_category":audience_size_category,
                "complexity":complexity_clean,
            },
            "suggested_factors":detailed_suggested,
            "suggested_product":detailed_product,
            "manual_detail":detail,
        },
        "channels":[{
            "channel":c.get("channel"),"budget":_num(c.get("budget")),"impressions":_num(c.get("impressions")),
            "tech_reach":_num(c.get("tech_reach")),"frequency":_num(c.get("frequency")),
            "reach":{a:_num(b) for a,b in (c.get("reach") or {}).items()},
            "performance":[[a,_num(b)] for a,b in (c.get("performance") or [])],
        } for c in channel_summaries],
        "flight_kpis":flight_kpis,"details":details,
    })



def _multi_norm_ta(value) -> str:
    return " ".join(str(value or "").strip().lower().replace("ё", "е").split())


def _selected_ta_name(plan, selected_flights) -> str:
    names=[]
    for fid in selected_flights:
        info=plan.flight_info(fid)
        if info is not None and not info.is_common and info.ta_name:
            n=" ".join(str(info.ta_name).split())
            if n and n not in names:
                names.append(n)
    return names[0] if len(names)==1 else (" / ".join(names) if names else "")


def _multi_ta(plan, selected_flights):
    values=[]
    originals=[]
    selected=set(selected_flights or [])
    for f in plan.flights:
        if f.id not in selected or f.is_common or not f.ta_name:
            continue
        key=_multi_norm_ta(f.ta_name)
        if key and key not in values:
            values.append(key)
            originals.append(f.ta_name)
    if len(values)==1:
        return originals[0], values[0]
    if len(values)>1:
        return "Разные ЦА внутри линейки", ""
    return "", ""


def multi_reach_metadata(path: str) -> str:
    groups=discover_media_plan_groups(path)
    plans={}
    out=[]
    for g in groups:
        plan=parse_media_plan(path, sheet_names=g.sheet_names)
        plans[g.id]=plan
        selected=plan.flight_ids()
        ta_name, ta_key=_multi_ta(plan, selected)
        out.append({
            "id":g.id,"label":g.label,"sheet_names":list(g.sheet_names),
            "universe":_num(plan.universe),"ta_name":ta_name,"ta_key":ta_key,
            "flights":[{
                "id":f.id,"label":f.label,"is_common":bool(f.is_common),
                "ta_name":f.ta_name,"universe":_num(f.universe),
            } for f in plan.flights],
        })
    _MULTI_REACH_CACHE[str(path)]={"groups":groups,"plans":plans}
    return _json({"plans":out})


def calculate_multi_reach(path: str, params_json: str) -> str:
    global PLAN
    q=json.loads(params_json or "{}")
    cache=_MULTI_REACH_CACHE.get(str(path))
    if not cache:
        multi_reach_metadata(path)
        cache=_MULTI_REACH_CACHE.get(str(path)) or {"plans":{}}
    plan_map=cache.get("plans") or {}
    base=dict(q.get("base_params") or {})
    requested=q.get("plans") or []
    coef=float(q.get("line_intersection_coefficient",0.85))
    if not math.isfinite(coef) or coef < 0.0 or coef > 1.0:
        raise ValueError("Коэффициент пересечения линеек должен быть в диапазоне 0–1.")
    manual_grand=q.get("grand_universe")
    try:
        manual_grand=float(manual_grand) if manual_grand not in (None, "", 0) else None
    except Exception:
        manual_grand=None

    previous_plan=PLAN
    lines=[]
    try:
        for item in requested:
            pid=str(item.get("id") or "")
            plan=plan_map.get(pid)
            if plan is None:
                continue
            selected_raw=item.get("selected_flights", None)
            selected=plan.flight_ids() if selected_raw is None else [x for x in selected_raw if x in plan.flight_ids()]
            if not selected:
                continue
            universe=float(item.get("universe") or plan.universe or 15182450)
            PLAN=plan
            line_q=dict(base)
            line_q["selected_flights"]=selected
            line_q["universe"]=universe
            subtotal_result=json.loads(calculate(json.dumps(line_q,ensure_ascii=False)))
            subtotal=subtotal_result['summary']
            flights=[]
            for fid in selected:
                fq=dict(line_q); fq["selected_flights"]=[fid]
                flight_result=json.loads(calculate(json.dumps(fq,ensure_ascii=False)))
                fs=flight_result['summary']
                info=plan.flight_info(fid)

                # Stage 9 is representation-only: expose the same intervals already used
                # by load_plan()/the stable single-plan flowchart. No new scheduling logic.
                flow=defaultdict(list)
                for row in plan.detail_rows([fid]):
                    ints=list(row.intervals or [])
                    if not ints and row.start and row.end:
                        ints=[(row.start,row.end)]
                    flow[row.channel or "Other"].extend(ints)
                flow_out={
                    ch:_intervals(_merge_intervals(ints))
                    for ch,ints in flow.items()
                }

                flights.append({
                    "id":fid,"label":info.label if info else fid,
                    "ta_name":info.ta_name if info else "",
                    "is_common":bool(info.is_common) if info else False,
                    "summary":fs,
                    "channels":flight_result.get("channels") or [],
                    "flow_schedule":flow_out,
                })
            ta_name,ta_key=_multi_ta(plan,selected)
            ta_override=str(item.get("ta_name_override") or "").strip()
            if ta_override:
                ta_name=ta_override
                ta_key=_multi_norm_ta(ta_override)
            label=next((g.label for g in cache.get("groups",[]) if g.id==pid), plan.display_name or pid)
            lines.append({
                "id":pid,"label":label,"universe":universe,
                "ta_name":ta_name,"ta_key":ta_key,
                "selected_flights":selected,"flights":flights,"subtotal":subtotal,
                "channels":subtotal_result.get("channels") or [],
            })
    finally:
        PLAN=previous_plan

    grand={
        "budget":sum(float(x['subtotal'].get('budget') or 0.0) for x in lines),
        "impressions":sum(float(x['subtotal'].get('impressions') or 0.0) for x in lines),
        "reach":{},"performance":[],"raw_reach_sum":{},
        "line_intersection_coefficient":coef,"same_ta":False,"same_universe":False,
        "universe":None,"universe_mode":"none","warning":"",
    }
    perf={}
    for line in lines:
        for label,value in (line['subtotal'].get('performance') or []):
            perf[label]=perf.get(label,0.0)+float(value or 0.0)
    grand['performance']=[[k,v] for k,v in sorted(perf.items())]

    reach_lines=[x for x in lines if (x['subtotal'].get('reach') or {}).get('target_1p') is not None]
    if not reach_lines:
        grand['warning']='В выбранных линейках нет охватных CPM/CPV-размещений. SEO/CPC/CPA/CPR и другие performance-строки Reach не создают.'
    else:
        ta_keys=[x.get('ta_key') or '' for x in reach_lines]
        same_ta=bool(all(ta_keys) and len(set(ta_keys))==1)
        universes=[float(x['universe']) for x in reach_lines if x.get('universe')]
        same_universe=bool(len(universes)==len(reach_lines) and max(universes)-min(universes)<=1.0) if universes else False
        grand['same_ta']=same_ta
        grand['same_universe']=same_universe

        max_line=max(
            (x for x in reach_lines if x.get('universe')),
            key=lambda x: float(x.get('universe') or 0.0),
            default=None,
        )
        auto_grand=float(max_line.get('universe')) if max_line is not None else None
        if manual_grand and manual_grand>0:
            grand_u=manual_grand
            grand['universe_mode']='manual'
            grand['universe_source_label']='Ручной Grand Universe'
        else:
            grand_u=auto_grand
            grand['universe_mode']='auto_max'
            grand['universe_source_label']=max_line.get('label') if max_line else ''
        grand['universe']=grand_u

        warnings=[]
        if not same_ta and len(reach_lines)>1:
            warnings.append(
                'ЦА выбранных линеек различаются или не определены. TOTAL нормализован на общий Grand Universe. '
                'Проверьте, что выбранная общая база действительно подходит для объединённого охвата.'
            )
        if manual_grand and auto_grand and manual_grand < auto_grand:
            warnings.append(
                'Ручной Grand Universe меньше максимального Universe одной из выбранных линеек. '
                'Проверьте корректность общей базы.'
            )

        freqs=set()
        for line in reach_lines:
            for key in (line['subtotal'].get('reach') or {}):
                mm=re.fullmatch(r'target_(\d+)p',key)
                if mm:
                    freqs.add(int(mm.group(1)))

        for freq in sorted(freqs):
            key=f'target_{freq}p'
            vals=[(x['subtotal'].get('reach') or {}).get(key) for x in reach_lines]
            vals=[float(v) for v in vals if v is not None]
            if vals:
                grand['raw_reach_sum'][key]=sum(vals)

        if len(reach_lines)==1:
            grand['reach']=dict(reach_lines[0]['subtotal'].get('reach') or {})
        elif grand_u is not None and grand_u > 0:
            grand['reach']=combine_reach_union(
                [(x['subtotal'].get('reach') or {}) for x in reach_lines],
                float(grand_u),
                coefficient=coef,
                frequencies=sorted(freqs),
            )
        else:
            # Without a common Grand Universe a percentage union is undefined.
            # Keep Reach empty instead of manufacturing an unnormalised TOTAL.
            grand['reach']={}
            warnings.append(
                'TOTAL Reach не рассчитан: отсутствует корректный Grand Universe для объединения аудиторий.'
            )

        if len(reach_lines)==1:
            grand['line_intersection_coefficient']=1.0
        grand['warning']=' '.join(warnings)
        grand['normalization_note']=(
            'Каждая линейка рассчитана на собственном Universe. Для TOTAL абсолютные Reach в людях '
            'объединяются с коэффициентом пересечения, а процент TOTAL считается от Grand Universe.'
        )

    return _json({"lines":lines,"grand_total":grand})

def load_splits(
    path: str,
    selected_sheets_json: str | None = None,
    selected_groups_json: str | None = None,
) -> str:
    global SPLIT_RESULT
    selected_sheets=None
    selected_groups=None
    if selected_sheets_json is not None:
        selected_sheets=json.loads(selected_sheets_json)
    if selected_groups_json is not None:
        selected_groups=json.loads(selected_groups_json)
    SPLIT_RESULT=parse_split_workbook(
        path,
        selected_sheets=selected_sheets,
        selected_sheet_groups=selected_groups,
    )
    agg=SPLIT_RESULT.aggregate()
    rows=[]
    format_order={"OLV":0,"Баннеры":1,"Social":2,"Спецпроекты":3,"Статьи":4,"Native":5,"Поиск":6,"РСЯ":7,"Perfomance":8,"SEO":9,"ORM":10,"Исследования":11,"Техническая строка":12}
    for platform in sorted(agg,key=lambda x:x.lower()):
        for fmt in sorted(agg[platform],key=lambda x:(format_order.get(x,8),x.lower())):
            months=agg[platform][fmt]
            row={"platform":platform,"format":fmt,"months":{}}
            for m in range(1,13):
                cell=months.get(m)
                if cell:
                    row["months"][str(m)]={k:_num(v) for k,v in cell.items()}
            rows.append(row)
    return _json({
        "rows":rows,"research":[{
            "platform":x.get("platform",""),"type":x.get("type",""),"status":x.get("status",""),
            "dedicated":bool(x.get("dedicated")),"plan":_num(x.get("plan")),
            "plan_ac":_num(x.get("plan_ac")),"plan_total":_num(x.get("plan_total")),
            "rows":int(x.get("rows") or 0),
        } for x in SPLIT_RESULT.research_summary()],
        "totals":{k:_num(v) for k,v in SPLIT_RESULT.totals().items()},
        "warnings":list(SPLIT_RESULT.warnings),"records":len(SPLIT_RESULT.records),
        "physical_rows":SPLIT_RESULT.physical_rows,
        "duplicate_rows_removed":SPLIT_RESULT.duplicate_rows_removed,
        "version_rows_replaced":SPLIT_RESULT.version_rows_replaced,
        "delta_mismatches":SPLIT_RESULT.delta_mismatches,
        "conservation":{
            "ok":bool(SPLIT_RESULT.conservation_ok),
            "source_plan":_num(SPLIT_RESULT.source_plan_total),
            "records_plan":_num(SPLIT_RESULT.records_plan_total),
            "split_plan":_num(SPLIT_RESULT.split_plan_total),
            "source_ac":_num(SPLIT_RESULT.source_ac_total),
            "records_ac":_num(SPLIT_RESULT.records_ac_total),
            "split_ac":_num(SPLIT_RESULT.split_ac_total),
            "source_total":_num(SPLIT_RESULT.source_total_total),
            "records_total":_num(SPLIT_RESULT.records_total_total),
            "split_total":_num(SPLIT_RESULT.split_total_total),
            "diff_plan":_num(SPLIT_RESULT.conservation_diff_plan),
            "diff_ac":_num(SPLIT_RESULT.conservation_diff_ac),
            "diff_total":_num(SPLIT_RESULT.conservation_diff_total),
        },
        "selected_sheets":list(SPLIT_RESULT.selected_sheets),
        "scanned_sheets":SPLIT_RESULT.scanned_sheets,"detected_tables":SPLIT_RESULT.detected_tables,
        "plan_sheets":list(SPLIT_RESULT.plan_sheets),"fact_sheets":list(SPLIT_RESULT.fact_sheets),
        "months":{str(k):v for k,v in MONTH_NAMES_RU.items()},
    })


def export_splits(out_path: str = "/tmp/splits_export.xlsx") -> str:
    if SPLIT_RESULT is None:
        raise RuntimeError("Сплиты не рассчитаны")
    p=export_split_xlsx(SPLIT_RESULT,out_path)
    return str(p)
