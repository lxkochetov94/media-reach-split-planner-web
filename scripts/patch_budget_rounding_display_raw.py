from pathlib import Path
import sys

app_path=Path(sys.argv[1] if len(sys.argv)>1 else 'budget-checker/src/app.js')
app=app_path.read_text(encoding='utf-8')

# UI: rounding-only rows keep their factual kopeck difference visible,
# while internal comparison status remains reconciled (difference=0).
old="rounding=result.rows.filter(x=>x.roundingOnly),tech=result.technicalCosts||[];const notes=[];"
new="rounding=result.rows.filter(x=>x.roundingOnly),tech=result.technicalCosts||[],displayDifference=result.overallRoundingOnly?(result.rawDifference??result.difference):result.difference;const notes=[];"
if old not in app:
    raise SystemExit('render declaration anchor missing')
app=app.replace(old,new,1)

old_top='class="metric ${result.difference?\'diff-neg\':\'diff-pos\'}">${result.difference>=0?\'+\':\'\'}${money(result.difference)}'
new_top='class="metric ${result.overallRoundingOnly?\'mp-rounding-value\':(result.difference?\'diff-neg\':\'diff-pos\')}">${displayDifference>=0?\'+\':\'\'}${money(displayDifference)}'
if old_top not in app:
    raise SystemExit('top difference display anchor missing')
app=app.replace(old_top,new_top,1)

old_channel="${x.excluded?'<span class="mp-excluded-pill">Исключено</span>':x.roundingOnly?'0 ₽':`${x.difference>=0?'+':''}${money(x.difference)}`}"
new_channel="${x.excluded?'<span class="mp-excluded-pill">Исключено</span>':x.roundingOnly?`${(x.rawDifference??0)>=0?'+':''}${money(x.rawDifference??0)}`:`${x.difference>=0?'+':''}${money(x.difference)}`}"
if old_channel not in app:
    raise SystemExit('channel rounding display anchor missing')
app=app.replace(old_channel,new_channel,1)

old_footer='class="money ${result.difference?\'diff-neg\':\'diff-pos\'}">${result.difference>=0?\'+\':\'\'}${money(result.difference)}'
new_footer='class="money ${result.overallRoundingOnly?\'mp-rounding-value\':(result.difference?\'diff-neg\':\'diff-pos\')}">${displayDifference>=0?\'+\':\'\'}${money(displayDifference)}'
if old_footer not in app:
    raise SystemExit('footer difference display anchor missing')
app=app.replace(old_footer,new_footer,1)

old_detail="${d.roundingOnly?'0 ₽':`${d.difference>=0?'+':''}${money(d.difference||0)}`}"
new_detail="${d.roundingOnly?`${(d.rawDifference??0)>=0?'+':''}${money(d.rawDifference??0)}`:`${d.difference>=0?'+':''}${money(d.difference||0)}`}"
if old_detail not in app:
    raise SystemExit('detail rounding display anchor missing')
app=app.replace(old_detail,new_detail,1)

# Excel: visible "Расхождение" keeps the factual raw difference for rounding-only rows.
old="(x.roundingOnly?0:x.difference)/100,(x.rawDifference??x.difference)/100"
new="(x.roundingOnly?(x.rawDifference??0):x.difference)/100,(x.rawDifference??x.difference)/100"
if old not in app:
    raise SystemExit('channel export anchor missing')
app=app.replace(old,new,1)

old="(d.roundingOnly?0:(d.difference||0))/100,(d.rawDifference??d.difference??0)/100"
new="(d.roundingOnly?(d.rawDifference??0):(d.difference||0))/100,(d.rawDifference??d.difference??0)/100"
if old not in app:
    raise SystemExit('detail export anchor missing')
app=app.replace(old,new,1)

if '/* Show raw rounding difference v1 */' not in app:
    app=app.replace('/* Export layout reference + tech runtime fix v1 */','/* Export layout reference + tech runtime fix v1 */\n/* Show raw rounding difference v1 */',1)

app_path.write_text(app,encoding='utf-8')
print('patched raw rounding difference display')
