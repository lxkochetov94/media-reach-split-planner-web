from pathlib import Path
import sys

html=Path(sys.argv[1]).read_text(encoding='utf-8')
version=sys.argv[2]
for asset in [
    'styles.css',
    'src/core.js',
    'src/importer.js',
    'src/excel.js',
    'src/workspace.js',
    '../mediaplan-checker/core.js',
    '../mediaplan-checker/production-rules.js',
    'src/app.js',
]:
    marker=f'{asset}?v={version}'
    if marker not in html:
        raise SystemExit('missing versioned asset: '+marker)
for asset in ['styles.css','src/app.js','src/excel.js','../mediaplan-checker/production-rules.js']:
    if f'{asset}"' in html:
        raise SystemExit('unversioned asset remains: '+asset)
print('budget asset version contract: OK')
