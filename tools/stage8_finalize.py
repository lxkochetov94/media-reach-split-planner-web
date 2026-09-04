from __future__ import annotations

import base64
import gzip
import json
import re
from pathlib import Path

PATH = Path('index.html')
src = PATH.read_text(encoding='utf-8')
m = re.search(r'window\.MRP_ASSETS=(\{.*?\});\s*</script>', src, re.S)
if not m:
    raise SystemExit('MRP_ASSETS not found')
assets = json.loads(m.group(1))

def dec(name: str) -> str:
    return gzip.decompress(base64.b64decode(assets[name])).decode('utf-8')

def enc(text: str) -> str:
    return base64.b64encode(gzip.compress(text.encode('utf-8'), mtime=0)).decode('ascii')

engine = dec('engine.py')
web = dec('web_api.py')

# Preserve the stable frequency curve while enforcing the buying-model contract.
start = engine.index('def _reach_allowed_for_row(')
end = engine.index('\n\ndef _audience_intersection_coef', start)
engine = engine[:start] + '''def _reach_model_allowed(x: Placement) -> bool:\n    \"\"\"Buying-model/channel eligibility independent of whether Reach UU is present.\"\"\"\n    if x.buying_model not in {\"CPM\", \"CPV\"}:\n        return False\n    cls = norm(getattr(x, \"placement_class\", \"\") or x.channel)\n    return \"seo\" not in cls\n\n\ndef _reach_allowed_for_row(plan: ParsedPlan, x: Placement) -> bool:\n    \"\"\"A row creates row-level reach only when CPM/CPV, non-SEO and Reach UU exists.\"\"\"\n    return x.tech_reach is not None and _reach_model_allowed(x)\n''' + engine[end:]

old = '''    reach_rows = [\n        x for x in plan.detail_rows(selected)\n        if _reach_allowed_for_row(plan, x)\n        and not (plan.flight_info(x.flight) and plan.flight_info(x.flight).is_common)\n    ]\n'''
new = '''    reach_rows = [\n        x for x in plan.detail_rows(selected)\n        if _reach_model_allowed(x)\n        and not (plan.flight_info(x.flight) and plan.flight_info(x.flight).is_common)\n    ]\n'''
if old not in engine:
    raise SystemExit('reach_rows anchor not found')
engine = engine.replace(old, new, 1)
old = '''            flight_rows = [\n                x for x in plan.detail_rows([f.id])\n                if _reach_allowed_for_row(plan, x)\n            ]\n'''
new = '''            flight_rows = [\n                x for x in plan.detail_rows([f.id])\n                if _reach_model_allowed(x) and x.tech_reach is not None\n            ]\n'''
if old not in engine:
    raise SystemExit('flight_rows anchor not found')
engine = engine.replace(old, new, 1)
assets['engine.py'] = enc(engine)

# Replace Stage-8 multi-plan API with a strict audience-compatible implementation.
cache_decl = "\n_MULTI_REACH_CACHE = {}\n"
if '_MULTI_REACH_CACHE = {}' not in web:
    insert_at = web.index('\ndef load_plan(')
    web = web[:insert_at] + cache_decl + web[insert_at:]

meta_start = web.index('def multi_reach_metadata(')
calc_start = web.index('def calculate_multi_reach(', meta_start)
# calculate_multi_reach is the last Stage-8 function before load_splits/export helpers.
next_candidates = [x for x in [web.find('\ndef load_splits', calc_start), web.find('\ndef export_', calc_start)] if x != -1]
if not next_candidates:
    raise SystemExit('multi reach function end not found')
func_end = min(next_candidates)

replacement = r'''def _multi_ta(plan, selected_flights):
    values=[]
    originals=[]
    selected=set(selected_flights or [])
    for f in plan.flights:
        if f.id not in selected or f.is_common or not f.ta_name:
            continue
        key=norm(f.ta_name)
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
    coef=max(0.0,min(1.0,float(q.get("line_intersection_coefficient",0.85))))
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
            selected=[x for x in (item.get("selected_flights") or plan.flight_ids()) if x in plan.flight_ids()]
            if not selected:
                continue
            universe=float(item.get("universe") or plan.universe or 15182450)
            PLAN=plan
            line_q=dict(base)
            line_q["selected_flights"]=selected
            line_q["universe"]=universe
            subtotal=json.loads(calculate(json.dumps(line_q,ensure_ascii=False)))['summary']
            flights=[]
            for fid in selected:
                fq=dict(line_q); fq["selected_flights"]=[fid]
                fs=json.loads(calculate(json.dumps(fq,ensure_ascii=False)))['summary']
                info=plan.flight_info(fid)
                flights.append({
                    "id":fid,"label":info.label if info else fid,
                    "ta_name":info.ta_name if info else "",
                    "is_common":bool(info.is_common) if info else False,
                    "summary":fs,
                })
            ta_name,ta_key=_multi_ta(plan,selected)
            label=next((g.label for g in cache.get("groups",[]) if g.id==pid), plan.display_name or pid)
            lines.append({
                "id":pid,"label":label,"universe":universe,
                "ta_name":ta_name,"ta_key":ta_key,
                "selected_flights":selected,"flights":flights,"subtotal":subtotal,
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
    elif len(reach_lines)==1:
        only=reach_lines[0]
        grand['same_ta']=True; grand['same_universe']=True
        grand['universe']=only['universe']; grand['universe_mode']='single_line'
        grand['reach']=dict(only['subtotal'].get('reach') or {})
        grand['raw_reach_sum']={k:v for k,v in grand['reach'].items() if k.startswith('target_') and not k.startswith('target_pct_')}
        grand['line_intersection_coefficient']=1.0
    else:
        ta_keys=[x.get('ta_key') or '' for x in reach_lines]
        same_ta=bool(all(ta_keys) and len(set(ta_keys))==1)
        universes=[float(x['universe']) for x in reach_lines if x.get('universe')]
        same_universe=bool(len(universes)==len(reach_lines) and max(universes)-min(universes)<=1.0)
        grand['same_ta']=same_ta; grand['same_universe']=same_universe
        if not same_ta:
            grand['universe_mode']='incompatible_ta'
            grand['warning']='Grand Reach не рассчитывается: у выбранных охватных линеек разные или не определённые ЦА. Один Universe не делает разные ЦА сопоставимыми. Используйте Subtotal каждой линейки отдельно.'
        else:
            if same_universe:
                grand_u=universes[0]; grand['universe_mode']='same_ta_same_universe'
            elif manual_grand and manual_grand>0:
                grand_u=manual_grand; grand['universe_mode']='same_ta_manual_universe'
            else:
                grand_u=None; grand['universe_mode']='same_ta_different_universe'
                grand['warning']='ЦА совпадает, но Universe линеек различается. Grand Reach в людях рассчитан с коэффициентом пересечения; для Grand Reach % задайте единый Grand Universe.'
            grand['universe']=grand_u
            freqs=set()
            for line in reach_lines:
                for key in (line['subtotal'].get('reach') or {}):
                    mm=re.fullmatch(r'target_(\d+)p',key)
                    if mm: freqs.add(int(mm.group(1)))
            for freq in sorted(freqs):
                key=f'target_{freq}p'
                vals=[(x['subtotal'].get('reach') or {}).get(key) for x in reach_lines]
                vals=[float(v) for v in vals if v is not None]
                if not vals: continue
                raw=sum(vals)
                grand['raw_reach_sum'][key]=raw
                people=raw*coef
                if grand_u is not None:
                    people=min(people,grand_u)
                grand['reach'][key]=people
                if grand_u and grand_u>0:
                    grand['reach'][f'target_pct_{freq}p']=people/grand_u

    return _json({"lines":lines,"grand_total":grand})
'''
web = web[:meta_start] + replacement + web[func_end:]
assets['web_api.py'] = enc(web)

# Correct UI semantics: Universe cannot reconcile genuinely different target audiences.
src = src.replace(
    'Для разных/неопределённых ЦА нужен отдельный Universe, чтобы показать Grand Reach %.',
    'Нужен только при одинаковой ЦА, если Universe линеек различается. Разные ЦА не объединяются в Grand Reach.'
)

src = src[:m.start()] + 'window.MRP_ASSETS=' + json.dumps(assets,separators=(',',':'),ensure_ascii=False) + ';</script>' + src[m.end():]
PATH.write_text(src,encoding='utf-8')
print('stage8 finalizer applied')
