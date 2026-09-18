from pathlib import Path
import sys
app=Path(sys.argv[1]).read_text(encoding='utf-8')
for marker in [
    'Export layout reference + tech runtime fix v1',
    'tech=result.technicalCosts||[]',
    'mpApplyExportLayout',
    '40.796875,49',
    '18.5,19.69921875,31',
    '19.8984375,27,63.59765625',
    '239.3984375,255',
    'hpt:15.6'
]:
    if marker not in app:
        raise SystemExit('missing marker: '+marker)
print('tech runtime + export layout contract: OK')
