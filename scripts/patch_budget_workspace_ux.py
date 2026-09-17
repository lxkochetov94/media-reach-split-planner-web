from pathlib import Path
import re
import sys

app_path = Path(sys.argv[1])
css_path = Path(sys.argv[2])
text = app_path.read_text(encoding='utf-8')
css = css_path.read_text(encoding='utf-8')

MARKER = 'Unified budget workspace UX'
if MARKER in text:
    print('workspace UX already applied')
    raise SystemExit(0)

text, n = re.subn(
    r"const menu=\[.*?\];",
    "const menu=[['project','Проект'],['current','Актуальный бюджет'],['mediaplan','Сверить медиаплан'],['history','История изменений'],['control','Контроль']];",
    text,
    count=1,
    flags=re.S,
)
if n != 1:
    raise SystemExit('menu replacement failed')

new_current = r'''function renderCurrent(){
 state.currentBudgetMode=state.currentBudgetMode||'current';
 state.budgetSelectedPaths=state.budgetSelectedPaths||{};
 view.innerHTML=`<div class="card budget-calendar-card"><div class="budget-calendar-head"><div><h2>Бюджет по месяцам</h2><div class="muted">Рабочий флоучарт: значения до НДС, база неизменна, подтверждённые изменения сохраняются автоматически.</div></div><div class="field budget-date-field"><label>Состояние на дату</label><input id="asOf" type="date"><div class="help">Пусто = актуальное состояние</div></div></div><div class="budget-toolbar budget-toolbar-clean"><div class="budget-toolbar-main"><div class="segmented budget-mode-compact" id="budgetMode"><button data-budget-mode="current" class="${state.currentBudgetMode==='current'?'active':''}">Актуально</button><button data-budget-mode="base" class="${state.currentBudgetMode==='base'?'active':''}">База</button><button data-budget-mode="delta" class="${state.currentBudgetMode==='delta'?'active':''}">Изменения</button></div><div class="field budget-search-field compact-field"><label>Поиск</label><input id="budgetSearch" placeholder="Бренд, продукт, канал..."></div><div class="budget-export-actions compact-actions"><button id="exportCurrentBudget" class="btn btn-sm">Выгрузить весь бюджет</button><button id="exportBudgetHistory" class="btn btn-sm">Выгрузить историю</button></div></div><div class="budget-toolbar-secondary"><div class="budget-selection-status"><span id="budgetSelectionCount" class="muted">Ничего не выбрано</span><button id="exportSelectedBudget" class="btn btn-sm primary" disabled>Выгрузить выделенное</button><button id="clearBudgetSelection" class="btn btn-sm ghost" disabled>Снять выделение</button></div><div class="budget-inline-actions"><button id="openBudgetNewLine" class="btn btn-sm">+ Новая строка</button><button id="openBudgetRedistribute" class="btn btn-sm">Перераспределить</button></div></div></div><div id="budgetSummary"></div><div class="help budget-calendar-help">Нажмите на сумму в конечной строке канала, чтобы добавить или снять бюджет. Комментарий обязателен. Галочками можно выбрать строки для отдельной выгрузки. Синяя точка означает наличие истории.</div><div id="budgetMatrix"></div></div>`;
 const date=document.getElementById('asOf'),search=document.getElementById('budgetSearch');
 date.onchange=renderBudgetMatrix;search.oninput=renderBudgetMatrix;
 document.querySelectorAll('[data-budget-mode]').forEach(b=>b.onclick=()=>{state.currentBudgetMode=b.dataset.budgetMode;document.querySelectorAll('[data-budget-mode]').forEach(x=>x.classList.toggle('active',x===b));renderBudgetMatrix();});
 document.getElementById('exportCurrentBudget').onclick=()=>exportCurrentBudgetMatrix(false);
 document.getElementById('exportSelectedBudget').onclick=()=>exportCurrentBudgetMatrix(true);
 document.getElementById('exportBudgetHistory').onclick=()=>E.exportHistory(state.project);
 document.getElementById('clearBudgetSelection').onclick=()=>{state.budgetSelectedPaths={};renderBudgetMatrix();};
 document.getElementById('openBudgetNewLine').onclick=openBudgetNewLineModal;
 document.getElementById('openBudgetRedistribute').onclick=openBudgetRedistributeModal;
 renderBudgetMatrix();
}
'''
text, n = re.subn(
    r"function renderCurrent\(\)\{.*?\n\}\n(?=function budgetCleanName)",
    lambda m: new_current,
    text,
    count=1,
    flags=re.S,
)
if n != 1:
    raise SystemExit('renderCurrent replacement failed')

helpers_and_export = r'''function budgetSelectionKey(path){return C.pathKey(path);}
function budgetPathStartsWith(path,prefix){if(prefix.length>path.length)return false;for(let i=0;i<prefix.length;i++)if(C.normalizeText(path[i])!==C.normalizeText(prefix[i]))return false;return true;}
function budgetSelectedEntries(){return Object.values(state.budgetSelectedPaths||{});}
function budgetResolveSelectedLeafIds(built){const selected=budgetSelectedEntries(),ids=new Set();if(!selected.length)return ids;for(const line of built.lines.values())if(selected.some(prefix=>budgetPathStartsWith(line.path,prefix)))ids.add(line.leafId);return ids;}
function budgetUpdateSelectionControls(){const count=Object.keys(state.budgetSelectedPaths||{}).length,leafCount=budgetResolveSelectedLeafIds(C.buildState(state.project,document.getElementById('asOf')?.value||null)).size,label=document.getElementById('budgetSelectionCount'),exp=document.getElementById('exportSelectedBudget'),clear=document.getElementById('clearBudgetSelection');if(label)label.textContent=count?`Выбрано: ${count} · бюджетных строк: ${leafCount}`:'Ничего не выбрано';if(exp)exp.disabled=!leafCount;if(clear)clear.disabled=!count;}
function budgetBindSelection(){document.querySelectorAll('[data-budget-select]').forEach(cb=>cb.onchange=()=>{const key=cb.dataset.budgetSelect,path=JSON.parse(decodeURIComponent(cb.dataset.budgetPath));state.budgetSelectedPaths=state.budgetSelectedPaths||{};if(cb.checked)state.budgetSelectedPaths[key]=path;else delete state.budgetSelectedPaths[key];document.querySelectorAll(`[data-budget-select="${CSS.escape(key)}"]`).forEach(x=>x.checked=cb.checked);budgetUpdateSelectionControls();});budgetUpdateSelectionControls();}
function budgetLineOptions(){const built=C.buildState(state.project);return [...built.lines.values()].sort((a,b)=>C.pathKey(a.path).localeCompare(C.pathKey(b.path))).map(line=>`<option value="${esc(line.leafId)}">${esc(line.path.filter(Boolean).join(' → '))}</option>`).join('');}
function openBudgetNewLineModal(){const fields=(state.project.hierarchyLabels||[]).map((label,i)=>`<div class="field"><label>${esc(label)}</label><input data-new-line-level="${i}" placeholder="${esc(label)}"></div>`).join('');showModal(`<h3>Новая бюджетная строка</h3><div class="muted">Строка создаётся через журнал изменений. Базовый бюджет не переписывается.</div><div class="new-line-grid">${fields}</div><div class="field"><label>Дата изменения</label><input id="newLineDate" type="date" value="${budgetToday()}"></div><div class="field"><label>Комментарий <span class="required-mark">обязательно</span></label><textarea id="newLineComment" placeholder="Почему добавляется новая строка"></textarea></div><div class="actions modal-actions"><button data-close class="btn">Отмена</button><button id="newLineConfirm" class="btn primary" disabled>Добавить строку</button></div>`,close=>{const inputs=[...document.querySelectorAll('[data-new-line-level]')],comment=document.getElementById('newLineComment'),date=document.getElementById('newLineDate'),btn=document.getElementById('newLineConfirm');const update=()=>btn.disabled=!comment.value.trim()||!date.value||!inputs.some(x=>x.value.trim());inputs.forEach(x=>x.oninput=update);comment.oninput=update;date.onchange=update;btn.onclick=async()=>{try{btn.disabled=true;await commitBudgetCellMutation(()=>C.addNewLineOperation(state.project,{path:inputs.map(x=>x.value.trim()),eventDate:date.value,comment:comment.value.trim()}));close();render();}catch(e){alert(e.message);update();}};update();});}
function openBudgetRedistributeModal(){const options=budgetLineOptions();showModal(`<h3>Перераспределить бюджет</h3><div class="muted">Операция атомарная: сумма одновременно снимается у источника и добавляется получателю. Общий бюджет не меняется.</div><div class="field"><label>Источник</label><select id="redisSource">${options}</select></div><div class="row"><div class="field"><label>Месяц источника</label><select id="redisSourceMonth">${C.MONTHS.map((m,i)=>`<option value="${i}">${esc(m)}</option>`).join('')}</select></div><div class="field"><label>Получатель</label><select id="redisTarget">${options}</select></div><div class="field"><label>Месяц получателя</label><select id="redisTargetMonth">${C.MONTHS.map((m,i)=>`<option value="${i}">${esc(m)}</option>`).join('')}</select></div></div><div class="row"><div class="field"><label>Сумма, ₽</label><input id="redisAmount" inputmode="decimal" placeholder="0"></div><div class="field"><label>Дата</label><input id="redisDate" type="date" value="${budgetToday()}"></div></div><div class="field"><label>Комментарий <span class="required-mark">обязательно</span></label><textarea id="redisComment" placeholder="Причина перераспределения"></textarea></div><div id="redisPreview" class="budget-edit-preview"></div><div class="actions modal-actions"><button data-close class="btn">Отмена</button><button id="redisConfirm" class="btn primary" disabled>Подтвердить перераспределение</button></div>`,close=>{const source=document.getElementById('redisSource'),target=document.getElementById('redisTarget'),sm=document.getElementById('redisSourceMonth'),tm=document.getElementById('redisTargetMonth'),amount=document.getElementById('redisAmount'),date=document.getElementById('redisDate'),comment=document.getElementById('redisComment'),preview=document.getElementById('redisPreview'),btn=document.getElementById('redisConfirm');const update=()=>{let kop=0;try{kop=C.rubToKopecks(amount.value||0);}catch(_e){}const built=C.buildState(state.project),line=built.lines.get(source.value),available=Number(line?.current?.[Number(sm.value)]||0),same=source.value===target.value&&sm.value===tm.value,valid=kop>0&&kop<=available&&!same&&date.value&&comment.value.trim();preview.innerHTML=kop>0?`Источник после операции: <b>${budgetPlain(available-kop)} ₽</b> · общий бюджет проекта не изменится.`:'<span class="muted">Введите сумму перераспределения.</span>';btn.disabled=!valid;};[source,target,sm,tm,date].forEach(x=>x.onchange=update);amount.oninput=update;comment.oninput=update;btn.onclick=async()=>{try{btn.disabled=true;const kop=C.rubToKopecks(amount.value);await commitBudgetCellMutation(()=>C.addRedistributionOperation(state.project,{sourceLeafId:source.value,sourceMonth:Number(sm.value),targetLeafId:target.value,targetMonth:Number(tm.value),amountKopecks:kop,eventDate:date.value,comment:comment.value.trim()}));close();render();}catch(e){alert(e.message);update();}};update();});}
function exportCurrentBudgetMatrix(selectedOnly=false){if(!globalThis.XLSX)return alert('Библиотека Excel не загрузилась.');const asOf=document.getElementById('asOf')?.value||null,built=C.buildState(state.project,asOf),selectedIds=selectedOnly?budgetResolveSelectedLeafIds(built):null;if(selectedOnly&&!selectedIds.size)return alert('Сначала отметьте нужные строки галочками.');const rows=[[...state.project.hierarchyLabels,...C.MONTHS,'Корректировка вне месяцев, ₽','Итого до НДС, ₽']];for(const line of [...built.lines.values()].sort((a,b)=>C.pathKey(a.path).localeCompare(C.pathKey(b.path)))){if(selectedOnly&&!selectedIds.has(line.leafId))continue;const total=line.current.reduce((a,b)=>a+b,0)+Number(line.currentAdjustment||0);rows.push([...line.path,...line.current.map(v=>v/100),Number(line.currentAdjustment||0)/100,total/100]);}const wb=XLSX.utils.book_new(),ws=XLSX.utils.aoa_to_sheet(rows);XLSX.utils.book_append_sheet(wb,ws,'Актуальный бюджет');const suffix=asOf||budgetToday(),prefix=selectedOnly?'Выделенный_бюджет':'Актуальный_бюджет';XLSX.writeFile(wb,`${prefix}_${budgetSafeFilePart(state.project.projectName)}_${budgetSafeFilePart(state.project.period)}_${suffix}.xlsx`,{compression:true});}
'''
text, n = re.subn(
    r"function exportCurrentBudgetMatrix\(\)\{.*?\n(?=function renderBudgetMatrix)",
    lambda m: helpers_and_export,
    text,
    count=1,
    flags=re.S,
)
if n != 1:
    raise SystemExit('export/helper replacement failed')

new_matrix = r'''function renderBudgetMatrix(){const asOf=document.getElementById('asOf')?.value||null,query=C.normalizeText(document.getElementById('budgetSearch')?.value||''),mode=state.currentBudgetMode||'current',tree=C.aggregateTree(state.project,asOf);const summary=document.getElementById('budgetSummary');if(summary)summary.innerHTML=`<div class="grid cols-3 budget-summary"><div><span class="muted">База до НДС</span><div class="metric">${money(tree.base)}</div></div><div><span class="muted">Изменения</span><div class="metric ${tree.delta>=0?'diff-pos':'diff-neg'}">${tree.delta>=0?'+':''}${money(tree.delta)}</div></div><div><span class="muted">Актуально до НДС</span><div class="metric">${money(tree.current)}</div></div></div>`;let rows=budgetCollectRows(tree);if(query)rows=rows.filter(r=>C.normalizeText(r.path.join(' → ')).includes(query));const body=rows.map(r=>{const x=budgetNodeNumbers(r.node,mode),level=state.project.hierarchyLabels?.[Number(r.node.level)]||'',depth=Math.min(r.depth,6),key=budgetSelectionKey(r.path),checked=!!state.budgetSelectedPaths?.[key],pathData=encodeURIComponent(JSON.stringify(r.path));return `<tr class="budget-row ${r.leaf?'budget-leaf':'budget-group'} budget-depth-${Math.min(depth,3)} ${checked?'budget-row-selected':''}"><td class="budget-select"><input type="checkbox" data-budget-select="${esc(key)}" data-budget-path="${esc(pathData)}" ${checked?'checked':''} aria-label="Выбрать ${esc(r.label)}"></td><td class="budget-structure"><div style="padding-left:${depth*12}px"><span class="budget-row-name">${esc(r.label)}</span>${level?`<span class="budget-level">${esc(level)}</span>`:''}</div></td>${x.months.map((v,i)=>`<td class="money">${budgetDisplayCell(r,v,i,mode,asOf)}</td>`).join('')}<td class="money budget-adjustment">${budgetDisplayCell(r,x.adjustment,'adjustment',mode,asOf)}</td><td class="money budget-total">${budgetCell(x.total,mode)}</td></tr>`;}).join('');const matrix=document.getElementById('budgetMatrix');if(matrix){matrix.innerHTML=`<div class="budget-matrix-wrap"><table class="budget-matrix"><thead><tr><th class="budget-select"><span class="sr-only">Выбор</span></th><th class="budget-structure">Структура</th>${C.MONTHS.map(m=>`<th class="money">${esc(m.slice(0,3))}</th>`).join('')}<th class="money budget-adjustment">Корр. вне мес.</th><th class="money budget-total">Итого до НДС, ₽</th></tr></thead><tbody>${body||'<tr><td colspan="16" class="empty">По вашему фильтру строк нет.</td></tr>'}</tbody></table></div>`;budgetBindEditableCells();budgetBindSelection();}}
'''
text, n = re.subn(
    r"function renderBudgetMatrix\(\)\{.*?\n(?=function renderHistory)",
    lambda m: new_matrix,
    text,
    count=1,
    flags=re.S,
)
if n != 1:
    raise SystemExit('renderBudgetMatrix replacement failed')

# Add a stable marker without changing runtime behavior.
text = text.replace("function budgetCleanName", "/* Unified budget workspace UX */\nfunction budgetCleanName", 1)

css_marker = '/* Unified budget workspace UX */'
if css_marker not in css:
    css += r'''

/* Unified budget workspace UX */
.budget-calendar-card{padding:18px 18px 14px}
.budget-calendar-head{margin-bottom:10px}
.budget-calendar-head h2{font-size:20px;margin:0 0 3px}
.budget-toolbar-clean{display:flex;flex-direction:column;gap:8px;padding:10px 0 11px;margin:0;border-top:1px solid #e6ebf2;border-bottom:1px solid #e6ebf2;background:transparent}
.budget-toolbar-main,.budget-toolbar-secondary{display:flex;align-items:flex-end;gap:10px;justify-content:space-between}
.budget-toolbar-main{flex-wrap:wrap}
.budget-mode-compact button{padding:8px 14px;font-size:13px}
.compact-field{margin:0;min-width:260px;max-width:380px;flex:1}
.compact-field label{font-size:12px;margin-bottom:3px}
.compact-field input{height:36px;padding:7px 10px}
.compact-actions,.budget-inline-actions,.budget-selection-status{display:flex;align-items:center;gap:7px;flex-wrap:wrap}
.btn-sm{min-height:34px;padding:7px 11px;font-size:13px}
.btn.ghost{border-color:transparent;background:transparent;color:#536273}
.btn.ghost:hover{background:#eef3f8}
.budget-selection-status{min-height:34px}
.budget-selection-status .muted{font-size:12px;min-width:150px}
.budget-summary{margin:10px 0 4px}
.budget-summary .metric{font-size:20px;line-height:1.15}
.budget-calendar-help{font-size:12px;margin:4px 0 8px}
.budget-matrix-wrap{max-height:620px;border-radius:8px}
.budget-matrix th,.budget-matrix td{padding:5px 8px;line-height:1.12}
.budget-matrix th{font-size:12px}
.budget-row-name{font-size:13px;font-weight:500}
.budget-level{font-size:10px;margin-top:2px}
.budget-group .budget-row-name{font-weight:600}
.budget-depth-0 .budget-row-name{font-weight:650}
.budget-select{position:sticky;left:0;width:32px;min-width:32px;max-width:32px;text-align:center!important;padding-left:6px!important;padding-right:4px!important;background:inherit;z-index:3}
.budget-structure{left:32px!important}
.budget-select input{width:14px;height:14px;margin:0;accent-color:#0d5bd7;cursor:pointer;opacity:.42;transition:opacity .12s}
.budget-row:hover .budget-select input,.budget-row-selected .budget-select input{opacity:1}
.budget-row-selected td{background:#edf5ff!important}
.budget-value-btn{font-size:12.5px;padding:2px 3px}
.budget-history-dot{width:5px;height:5px}
.new-line-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:10px;margin:14px 0}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}
@media(max-width:980px){.budget-toolbar-main,.budget-toolbar-secondary{align-items:stretch}.compact-field{max-width:none}.new-line-grid{grid-template-columns:1fr}}
'''

app_path.write_text(text, encoding='utf-8')
css_path.write_text(css, encoding='utf-8')
print('workspace UX applied')
