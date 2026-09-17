from pathlib import Path
import sys

path = Path(sys.argv[1] if len(sys.argv) > 1 else 'budget-checker/src/app.js')
text = path.read_text(encoding='utf-8')
old = "const signed=direction==='ADD'?kop:-kop,next=current+signed,valid=kop>0&&comment.value.trim().length>0&&date.value&&next>=0;"
new = "const signed=direction==='ADD'?kop:-kop,next=current+signed,resultingBudget=isAdjustment?line.current.reduce((a,b)=>a+b,0)+next:next,valid=kop>0&&comment.value.trim().length>0&&date.value&&resultingBudget>=0;"
if old in text:
    text = text.replace(old, new, 1)
elif new not in text:
    raise SystemExit('inline editor validation marker not found')
path.write_text(text, encoding='utf-8')
