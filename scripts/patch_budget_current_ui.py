from pathlib import Path
import sys

NEW_CURRENT = r'''function renderCurrent(){
 state.currentBudgetMode=state.currentBudgetMode||'current';
 const p=state.project;
 view.innerHTML=`<div class="card budget-calendar-card"><div class="budget-calendar-head"><div><h2>Бюджет по месяцам</h2><div class="muted">Все уровни видны сразу, без раскрытия дерева. Значения рассчитаны из базы и журнала изменений.</div></div><div class="field budget-date-field"><label>Состояние на дату</label><input id="asOf" type="date"><div class="help">Пусто = актуальное состояние</div></div></div><div class="budget-toolbar"><div class="segmented" id="budgetMode"><button data-budget-mode="current" class="${state.currentBudgetMode==='current'?'active':''}">Актуально</button><button data-budget-mode="base" class="${state.currentBudgetMode==='base'?'active':''}">База</button><button data-budget-mode="delta" class="${state.currentBudgetMode==='delta'?'active':''}">Изменения</button></div><div class="field budget-search-field"><label>Поиск по структуре</label><input id="budgetSearch" placeholder="Бренд, продукт, канал..."></div></div><div id="budgetSummary"></div><div class="help budget-calendar-help">Строки агрегируются автоматически: дивизион → бренд → продукт → тип медиа → канал. Нулевые значения показаны прочерком.</div><div id="budgetMatrix"></div></div>`;
 const date=document.getElementById('asOf'),search=document.getElementById('budgetSearch');
 date.onchange=renderBudgetMatrix;search.oninput=renderBudgetMatrix;
 document.querySelectorAll('[data-budget-mode]').forEach(b=>b.onclick=()=>{state.currentBudgetMode=b.dataset.budgetMode;document.querySelectorAll('[data-budget-mode]').forEach(x=>x.classList.toggle('active',x===b));renderBudgetMatrix();});
 renderBudgetMatrix();
}
function budgetCleanName(name){return String(name??'').replace(/\s+flowchart\b.*$/i,'').replace(/\s+флоучарт\b.*$/i,'').trim()||'—';}
function budgetMonthArray(n,key){if(Array.isArray(n?.[key]))return n[key].map(x=>Number(x||0));const out=Array(12).fill(0);for(const child of n?.children?.values?.()||[]){const a=budgetMonthArray(child,key);for(let i=0;i<12;i++)out[i]+=a[i];}return out;}
function budgetAdjustment(n,key){const v=Number(n?.[key]);if(Number.isFinite(v))return v;let sum=0;for(const child of n?.children?.values?.()||[])sum+=budgetAdjustment(child,key);return sum;}
function budgetNodeNumbers(n,mode){const baseMonths=budgetMonthArray(n,'baseMonths'),currentMonths=budgetMonthArray(n,'currentMonths'),baseAdj=budgetAdjustment(n,'baseAdjustment'),currentAdj=budgetAdjustment(n,'currentAdjustment');if(mode==='base')return {months:baseMonths,adjustment:baseAdj,total:Number(n.base??baseMonths.reduce((a,b)=>a+b,0)+baseAdj)};if(mode==='delta')return {months:currentMonths.map((v,i)=>v-baseMonths[i]),adjustment:currentAdj-baseAdj,total:Number(n.delta??((currentMonths.reduce((a,b)=>a+b,0)+currentAdj)-(baseMonths.reduce((a,b)=>a+b,0)+baseAdj)))};return {months:currentMonths,adjustment:currentAdj,total:Number(n.current??currentMonths.reduce((a,b)=>a+b,0)+currentAdj)};}
function budgetPlain(k){const n=Number(k||0),rub=n/100,hasKop=Math.abs(n%100)>0;return new Intl.NumberFormat('ru-RU',{minimumFractionDigits:hasKop?2:0,maximumFractionDigits:2}).format(rub);}
function budgetCell(v,mode){const n=Number(v||0);if(!n)return '<span class="budget-zero">—</span>';const cls=mode==='delta'?(n>0?'diff-pos':'diff-neg'):'';return `<span class="${cls}">${mode==='delta'&&n>0?'+':''}${budgetPlain(n)}</span>`;}
function budgetCollectRows(tree){const rows=[];const walk=(node,depth,path)=>{const raw=String(node?.name??'').trim(),placeholder=!raw||raw==='—'||raw==='-';const label=placeholder?'':budgetCleanName(raw),nextPath=placeholder?path:[...path,label];if(!placeholder)rows.push({node,depth,path:nextPath,label,leaf:!node.children?.size});for(const child of node?.children?.values?.()||[])walk(child,placeholder?depth:depth+1,nextPath);};for(const child of tree.children.values())walk(child,0,[]);return rows;}
function renderBudgetMatrix(){const asOf=document.getElementById('asOf')?.value||null,query=C.normalizeText(document.getElementById('budgetSearch')?.value||''),mode=state.currentBudgetMode||'current',tree=C.aggregateTree(state.project,asOf);const summary=document.getElementById('budgetSummary');if(summary)summary.innerHTML=`<div class="grid cols-3 budget-summary"><div><span class="muted">База</span><div class="metric">${money(tree.base)}</div></div><div><span class="muted">Изменения</span><div class="metric ${tree.delta>=0?'diff-pos':'diff-neg'}">${tree.delta>=0?'+':''}${money(tree.delta)}</div></div><div><span class="muted">Актуально</span><div class="metric">${money(tree.current)}</div></div></div>`;let rows=budgetCollectRows(tree);if(query)rows=rows.filter(r=>C.normalizeText(r.path.join(' → ')).includes(query));const body=rows.map(r=>{const x=budgetNodeNumbers(r.node,mode),level=state.project.hierarchyLabels?.[Number(r.node.level)]||'',depth=Math.min(r.depth,6);return `<tr class="budget-row ${r.leaf?'budget-leaf':'budget-group'} budget-depth-${Math.min(depth,3)}"><td class="budget-structure"><div style="padding-left:${depth*18}px"><span class="budget-row-name">${esc(r.label)}</span>${level?`<span class="budget-level">${esc(level)}</span>`:''}</div></td>${x.months.map(v=>`<td class="money">${budgetCell(v,mode)}</td>`).join('')}<td class="money budget-adjustment">${budgetCell(x.adjustment,mode)}</td><td class="money budget-total"><b>${budgetCell(x.total,mode)}</b></td></tr>`;}).join('');const matrix=document.getElementById('budgetMatrix');if(matrix)matrix.innerHTML=`<div class="budget-matrix-wrap"><table class="budget-matrix"><thead><tr><th class="budget-structure">Структура</th>${C.MONTHS.map(m=>`<th class="money">${esc(m.slice(0,3))}</th>`).join('')}<th class="money budget-adjustment">Корр. вне мес.</th><th class="money budget-total">Итого, ₽</th></tr></thead><tbody>${body||'<tr><td colspan="15" class="empty">По вашему фильтру строк нет.</td></tr>'}</tbody></table></div>`;}
'''

CSS = r'''
.budget-calendar-head{display:flex;align-items:flex-start;justify-content:space-between;gap:18px}.budget-date-field{width:220px;flex:0 0 220px}.budget-toolbar{display:flex;align-items:end;justify-content:space-between;gap:16px;margin:14px 0}.segmented{display:inline-flex;border:1px solid #cfd6df;border-radius:9px;overflow:hidden;background:#fff}.segmented button{border:0;border-right:1px solid #cfd6df;background:#fff;padding:9px 14px;font:inherit;font-weight:650;cursor:pointer}.segmented button:last-child{border-right:0}.segmented button.active{background:var(--accent2);color:#fff}.budget-search-field{width:min(360px,100%);margin:0}.budget-summary{margin:14px 0 10px}.budget-calendar-help{margin:8px 0 12px}.budget-matrix-wrap{overflow:auto;max-height:70vh;border:1px solid var(--line);border-radius:10px;background:#fff}.budget-matrix{min-width:1720px;font-variant-numeric:tabular-nums}.budget-matrix th,.budget-matrix td{padding:8px 9px;white-space:nowrap}.budget-matrix th{z-index:3}.budget-matrix .budget-structure{position:sticky;left:0;min-width:330px;max-width:420px;z-index:2}.budget-matrix th.budget-structure{z-index:5;background:#f8fafc}.budget-matrix .budget-total{position:sticky;right:0;min-width:125px;z-index:2;background:#fff;border-left:1px solid #e4e8ed}.budget-matrix th.budget-total{z-index:5;background:#f8fafc}.budget-row-name{font-weight:650}.budget-level{display:block;margin-top:2px;font-size:10px;font-weight:500;color:var(--muted)}.budget-zero{color:#a8afb8}.budget-group td{font-weight:650;background:#f8fafc}.budget-group td.budget-structure,.budget-group td.budget-total{background:#f8fafc}.budget-depth-0 td{background:#eaf0f7;font-weight:800}.budget-depth-0 td.budget-structure,.budget-depth-0 td.budget-total{background:#eaf0f7}.budget-depth-1 td{background:#f3f6fa}.budget-depth-1 td.budget-structure,.budget-depth-1 td.budget-total{background:#f3f6fa}.budget-leaf td{background:#fff;font-weight:400}.budget-leaf td.budget-structure,.budget-leaf td.budget-total{background:#fff}.budget-leaf .budget-row-name{font-weight:600}.budget-adjustment{border-left:1px solid #eef1f4}@media(max-width:980px){.budget-calendar-head,.budget-toolbar{flex-direction:column;align-items:stretch}.budget-date-field,.budget-search-field{width:100%;flex:auto}.budget-matrix .budget-structure{min-width:240px}}
'''


def replace_function(text: str, start_marker: str, next_marker: str, new_block: str, label: str) -> str:
    start = text.find(start_marker)
    end = text.find(next_marker, start)
    if start < 0 or end < 0:
        raise SystemExit(f'{label} block not found')
    return text[:start] + new_block.rstrip() + '\n' + text[end:]


def patch_app(path: Path):
    text = path.read_text(encoding='utf-8')
    text = text.replace(",['save','Сохранить']", '', 1)
    text = replace_function(text, 'function renderCurrent(){', 'function renderHistory(){', NEW_CURRENT, 'current budget UI')
    old_button = '<div class="actions"><button id="saveSnapshot" class="btn primary">Сохранить версию сейчас</button></div>'
    new_note = '<div class="info-box"><b>Автосохранение включено.</b> После каждой подтверждённой бюджетной операции файл «Актуальный» обновляется автоматически, а в архив добавляется снимок. Отдельная кнопка «Сохранить» для обычной работы не нужна.</div>'
    if old_button in text:
        text = text.replace(old_button, new_note, 1)
    text = text.replace("document.getElementById('backProjects').onclick=closeProject;document.getElementById('saveSnapshot').onclick=saveProject;", "document.getElementById('backProjects').onclick=closeProject;", 1)
    if "['save','Сохранить']" in text or 'saveSnapshot' in text:
        raise SystemExit('save UI removal failed')
    if 'Бюджет по месяцам' not in text or 'budgetMatrix' not in text:
        raise SystemExit('budget matrix patch failed')
    path.write_text(text, encoding='utf-8')


def patch_styles(path: Path):
    text = path.read_text(encoding='utf-8')
    marker = '.budget-calendar-head{'
    if marker not in text:
        text = text.rstrip() + '\n' + CSS.strip() + '\n'
    path.write_text(text, encoding='utf-8')


if __name__ == '__main__':
    app = Path(sys.argv[1] if len(sys.argv) > 1 else 'budget-checker/src/app.js')
    styles = Path(sys.argv[2] if len(sys.argv) > 2 else app.parent.parent / 'styles.css')
    patch_app(app)
    patch_styles(styles)
