from pathlib import Path
import sys
app=Path(sys.argv[1]).read_text(encoding='utf-8')
css=Path(sys.argv[2]).read_text(encoding='utf-8')
for marker in ['Rounding-aware reconciliation v1','mpRoundedRubles','mpSameAfterRubleRounding','mpRoundingMessage','Совпадает после округления','Исходная разница, ₽']:
    if marker not in app: raise SystemExit('missing app marker: '+marker)
for marker in ['.mp-rounding-row','.mp-rounding-value','.mp-rounding-note']:
    if marker not in css: raise SystemExit('missing css marker: '+marker)
print('rounding-aware reconciliation contract: OK')
