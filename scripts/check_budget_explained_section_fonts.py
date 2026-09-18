from pathlib import Path
import sys
app=Path(sys.argv[1]).read_text(encoding='utf-8')
css=Path(sys.argv[2]).read_text(encoding='utf-8')
for marker in ['Explained reconciliation section + uniform weights v1','explainedRows=[...explained,...rounding]','Объяснённые различия ·','Расхождений, требующих проверки, нет','${critical.map']:
    if marker not in app: raise SystemExit('missing app marker: '+marker)
for marker in ['.mp-explained-section','.mp-explained-table tbody td','font-weight:400!important','.mp-channel-total td','.mp-rounding-value']:
    if marker not in css: raise SystemExit('missing css marker: '+marker)
print('explained reconciliation section + font contract: OK')
