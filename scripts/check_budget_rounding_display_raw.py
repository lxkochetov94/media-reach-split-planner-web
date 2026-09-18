from pathlib import Path
import sys
app=Path(sys.argv[1]).read_text(encoding='utf-8')
for marker in ['Show raw rounding difference v1','displayDifference=result.overallRoundingOnly','x.rawDifference??0','d.rawDifference??0']:
    if marker not in app: raise SystemExit('missing marker: '+marker)
print('raw rounding difference display contract: OK')
