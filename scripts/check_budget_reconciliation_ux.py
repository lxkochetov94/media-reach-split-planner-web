from pathlib import Path
import sys
app=Path(sys.argv[1]).read_text(encoding='utf-8')
css=Path(sys.argv[2]).read_text(encoding='utf-8')
prod=Path(sys.argv[3]).read_text(encoding='utf-8')
for marker in ['Reconciliation UX + technical costs v1','mpTechnicalCostGroups','mpSourceDetailsHtml','Выгрузить сверку в Excel','Итого в сверке','Объяснено техкостом','Технические расходы']:
    if marker not in app: raise SystemExit('missing app marker: '+marker)
for marker in ['.mp-diff-table','.mp-source-details','.mp-channel-total','.mp-technical-row','.mp-tech-note']:
    if marker not in css: raise SystemExit('missing css marker: '+marker)
for marker in ['extractTechnicalSummaryCosts','technicalCosts','Счётчик TNS']:
    if marker not in prod: raise SystemExit('missing production parser marker: '+marker)
print('reconciliation UX + technical costs contract: OK')
