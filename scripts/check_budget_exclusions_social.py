from pathlib import Path
import sys
app=Path(sys.argv[1]).read_text(encoding='utf-8')
excel=Path(sys.argv[2]).read_text(encoding='utf-8')
css=Path(sys.argv[3]).read_text(encoding='utf-8')
for marker in ['Budget comparison exclusions v1','mpStoreExclusion','mpOpenExclusionModal','mpOpenExclusionsList','data-mp-exclude-channel','Исключения ·','Флоучарт в сверке','Медиаплан в сверке']:
    if marker not in app: raise SystemExit('missing app marker: '+marker)
for marker in ['mediaPlanExclusionsJson','mediaPlanExclusions:JSON.parse']:
    if marker not in excel: raise SystemExit('missing persistence marker: '+marker)
for marker in ['Budget comparison exclusions v1','.mp-row-menu','.mp-excluded-row','.mp-excluded-pill']:
    if marker not in css: raise SystemExit('missing css marker: '+marker)
print('budget exclusions + social matching contract: OK')
