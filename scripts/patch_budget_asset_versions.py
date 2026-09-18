from pathlib import Path
import re
import sys

path=Path(sys.argv[1] if len(sys.argv)>1 else 'budget-checker/index.html')
version=(sys.argv[2] if len(sys.argv)>2 else '').strip()
if not version:
    raise SystemExit('asset version is required')
html=path.read_text(encoding='utf-8')

assets=[
    'styles.css',
    'src/core.js',
    'src/importer.js',
    'src/excel.js',
    'src/workspace.js',
    '../mediaplan-checker/core.js',
    '../mediaplan-checker/production-rules.js',
    'src/app.js',
]
for asset in assets:
    pattern=re.escape(asset)+r'(?:\?v=[^"\']*)?'
    html,n=re.subn(pattern,asset+'?v='+version,html)
    if n!=1:
        raise SystemExit(f'expected exactly one reference for {asset}, found {n}')

path.write_text(html,encoding='utf-8')
print('budget asset cache bust:',version)
