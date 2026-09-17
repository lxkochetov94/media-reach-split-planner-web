from pathlib import Path
import sys


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if old not in text:
        if new in text:
            return text
        raise SystemExit(f'{label} not found')
    return text.replace(old, new, 1)


def replace_function(text: str, start_marker: str, next_marker: str, new_block: str, label: str) -> str:
    start = text.find(start_marker)
    end = text.find(next_marker, start)
    if start < 0 or end < 0:
        raise SystemExit(f'{label} block not found')
    return text[:start] + new_block.rstrip() + '\n' + text[end:]


NEW_TOTAL_RULES = r'''function guessTotalRules(rows,hierarchy,dataStartRow){
 const markers=new Set(['всего','итого','тотал','total','subtotal']),rules=[],covered=new Set(),candidates=[];
 for(const map of hierarchy||[]){
  if(map.source==='sheet'||!map.column)continue;
  const ci=I.colToIndex(map.column),byMarker=new Map();
  for(let i=Math.max(0,Number(dataStartRow||1)-1);i<rows.length;i++){
   const raw=String((rows[i]||[])[ci]??'').trim(),n=C.normalizeText(raw);if(!raw||!markers.has(n))continue;
   if(!byMarker.has(n))byMarker.set(n,{column:map.column,value:raw,rows:new Set()});byMarker.get(n).rows.add(i);
  }
  for(const c of byMarker.values())candidates.push(c);
 }
 for(const c of candidates){
  const adds=[...c.rows].some(i=>!covered.has(i));if(!adds)continue;
  rules.push({column:c.column,operator:'equals',value:c.value});for(const i of c.rows)covered.add(i);
 }
 return rules;
}'''

NEW_SHEET_LEVEL = r'''function guessSheetLevelValue(name,summaryRows,summaryConfig,level){
 const nameNorm=C.normalizeText(name),candidates=[],generic=new Set(['lab','flowchart','флоучарт','сводная','summary','total','итого','всего']);
 if(summaryRows){
  const map=(summaryConfig?.hierarchy||[]).find(x=>Number(x.level)===Number(level));
  const preferred=map?.column?[I.colToIndex(map.column)]:null;
  const from=Math.max(0,Number(summaryConfig?.dataStartRow||1)-1);
  for(let i=from;i<summaryRows.length;i++){
   const row=summaryRows[i]||[],cols=preferred||Array.from({length:Math.min(row.length,12)},(_,idx)=>idx);
   for(const ci of cols){
    const raw=String(row[ci]??'').trim(),n=C.normalizeText(raw);
    if(n.length<3||generic.has(n)||!nameNorm.includes(n))continue;
    candidates.push({raw,n});
   }
  }
 }
 if(candidates.length){candidates.sort((a,b)=>b.n.length-a.n.length);return candidates[0].raw;}
 return String(name).replace(/\bflowchart\b/ig,' ').replace(/\b\d{1,2}[.\/-]\d{1,2}(?:[.\/-]\d{2,4})?\b/g,' ').replace(/\s+/g,' ').trim();
}'''


def patch(path: Path):
    text = path.read_text(encoding='utf-8')

    text = replace_function(
        text,
        'function guessTotalRules(rows,hierarchy,dataStartRow){',
        'function guessSheetLevelValue',
        NEW_TOTAL_RULES,
        'total-rule autodetection',
    )
    text = replace_function(
        text,
        'function guessSheetLevelValue(name,summaryRows,summaryConfig,level){',
        'function guessDetailConfig',
        NEW_SHEET_LEVEL,
        'sheet-level autodetection',
    )

    old_steps = '''let html=`<div class="wizard-steps"><span class="${w.step===1?'on':''}">1. Проект</span><span class="${w.step===2?'on':''}">2. Листы</span><span class="${w.step===3?'on':''}">3. Сопоставление</span><span class="${w.step===4?'on':''}">4. Проверка</span></div>`;'''
    new_steps = '''let html=`<div class="wizard-steps"><span class="${w.step===1?'on':''}">1. Проект</span><span class="${w.step===2?'on':''}">2. Листы</span><span class="${w.step===3||w.step===4?'on':''}">3. Проверка</span></div>`;'''
    text = replace_once(text, old_steps, new_steps, 'wizard steps')

    old_transition = "for(const n of w.detailSheets) if(!w.configs[n]) w.configs[n]=guessDetailConfig(n,state.sourceWorkbook.sheets[n],w.hierarchyLabels,w.summarySheet?state.sourceWorkbook.sheets[w.summarySheet]:null,w.summaryConfig);w.step=3;renderWizard();};}"
    new_transition = "for(const n of w.detailSheets) if(!w.configs[n]) w.configs[n]=guessDetailConfig(n,state.sourceWorkbook.sheets[n],w.hierarchyLabels,w.summarySheet?state.sourceWorkbook.sheets[w.summarySheet]:null,w.summaryConfig);w.step=4;renderWizard();};}"
    text = replace_once(text, old_transition, new_transition, 'automatic review transition')

    old_review = '''return `<div class="card"><h2>Проверка импорта</h2><div class="grid cols-3">'''
    new_review = '''return `<div class="card"><h2>Проверка импорта</h2>${info('Структура файла распознана автоматически. Ручное сопоставление нужно только если вы видите, что приложение неверно поняло структуру файла.')}<div class="grid cols-3">'''
    text = replace_once(text, old_review, new_review, 'review notice')

    old_back = '''<button id="wBack4" class="btn">Назад к сопоставлению</button>'''
    new_back = '''<button id="wBack4" class="btn">Настроить импорт вручную</button>'''
    text = replace_once(text, old_back, new_back, 'manual mapping button')

    if 'Настроить импорт вручную' not in text or 'w.step=4;renderWizard();};}' not in text:
        raise SystemExit('UX patch verification failed')

    path.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    target = Path(sys.argv[1] if len(sys.argv) > 1 else 'budget-checker/src/app.js')
    patch(target)
