from pathlib import Path
import sys

app_path=Path(sys.argv[1] if len(sys.argv)>1 else 'budget-checker/src/app.js')
css_path=Path(sys.argv[2] if len(sys.argv)>2 else 'budget-checker/styles.css')
app=app_path.read_text(encoding='utf-8')
css=css_path.read_text(encoding='utf-8')

def function_bounds(src,name):
    token='function '+name+'('
    start=src.find(token)
    if start<0:
        raise SystemExit('missing function '+name)
    brace=src.find('{',start)
    depth=0
    quote=None
    escape=False
    i=brace
    while i<len(src):
        ch=src[i]
        if quote:
            if escape:
                escape=False
            elif ch=='\\':
                escape=True
            elif ch==quote:
                quote=None
        else:
            if ch in ("'",'"','`'):
                quote=ch
            elif ch=='{':
                depth+=1
            elif ch=='}':
                depth-=1
                if depth==0:
                    return start,i+1
        i+=1
    raise SystemExit('unterminated function '+name)

start,end=function_bounds(app,'mpRenderComparison')
render=app[start:end]

old_decl="rounding=result.rows.filter(x=>x.roundingOnly),tech=result.technicalCosts||[],displayDifference=result.overallRoundingOnly?(result.rawDifference??result.difference):result.difference;const notes=[];"
new_decl="""rounding=result.rows.filter(x=>x.roundingOnly),tech=result.technicalCosts||[],displayDifference=result.overallRoundingOnly?(result.rawDifference??result.difference):result.difference,explainedRows=[...explained,...rounding],explainedHtml=explainedRows.length?`<details class="mp-explained-section"><summary>Объяснённые различия · ${explainedRows.length}</summary><div class="table-wrap mp-explained-wrap"><table class="mp-explained-table"><thead><tr><th>Тип</th><th>Путь</th><th>Месяц</th><th>Флоучарт</th><th>Медиаплан</th><th>Расхождение</th><th>Комментарий</th><th>Источник</th></tr></thead><tbody>${explainedRows.map(d=>`<tr class="${d.roundingOnly?'mp-rounding-row':'mp-tech-explained-row'}"><td>${esc(d.roundingOnly?'Совпадает после округления':'Объяснено техкостом')}</td><td class="mp-diff-path">${esc((d.path||[]).join(' → '))}</td><td>${d.month==null?'Итого':esc(C.MONTHS[d.month])}</td><td class="money">${money(d.control||0)}</td><td class="money">${money(d.external||0)}</td><td class="money ${d.roundingOnly?'mp-rounding-value':'mp-tech-value'}">${d.roundingOnly?`${(d.rawDifference??0)>=0?'+':''}${money(d.rawDifference??0)}`:`${d.difference>=0?'+':''}${money(d.difference||0)}`}</td><td><div class="mp-diff-comment" title="${esc(d.message||'')}">${esc(d.message||'')}</div></td><td>${mpSourceDetailsHtml(d.sources)}</td></tr>`).join('')}</tbody></table></div></details>`:'';const notes=[];"""
if old_decl not in render:
    raise SystemExit('render declaration anchor missing')
render=render.replace(old_decl,new_decl,1)

old_map='${result.rows.map(d=>`<tr class="${d.roundingOnly?'
new_map='${critical.map(d=>`<tr class="${d.roundingOnly?'
if old_map not in render:
    raise SystemExit('main mismatch rows anchor missing')
render=render.replace(old_map,new_map,1)

old_empty="||'<tr><td colspan=\"8\">Расхождений нет</td></tr>'"
new_empty="||'<tr><td colspan=\"8\">Расхождений, требующих проверки, нет</td></tr>'"
if old_empty not in render:
    raise SystemExit('empty mismatch state anchor missing')
render=render.replace(old_empty,new_empty,1)

old_tail='</tbody></table></div>${unparsed.length?'
new_tail='</tbody></table></div>${explainedHtml}${unparsed.length?'
if old_tail not in render:
    raise SystemExit('explained block insertion anchor missing')
render=render.replace(old_tail,new_tail,1)

app=app[:start]+render+app[end:]

if '/* Explained reconciliation section + uniform weights v1 */' not in app:
    app=app.replace('/* Show raw rounding difference v1 */','/* Show raw rounding difference v1 */\n/* Explained reconciliation section + uniform weights v1 */',1)

css_add=r"""
/* Explained reconciliation section + uniform weights v1 */
.mp-channel-table tbody td,
.mp-channel-table tfoot td,
.mp-diff-table tbody td,
.mp-explained-table tbody td{font-weight:400!important}
.mp-channel-total td,
.mp-rounding-value{font-weight:400!important}
.mp-explained-section{margin-top:14px;border:1px solid #dfe7f1;border-radius:10px;background:#fbfdff;overflow:hidden}
.mp-explained-section>summary{cursor:pointer;list-style:none;padding:10px 12px;font-size:14px;font-weight:400;color:#315579;background:#f4f8fd}
.mp-explained-section>summary::-webkit-details-marker{display:none}
.mp-explained-section>summary::before{content:'▸';display:inline-block;margin-right:6px;color:#64748b}
.mp-explained-section[open]>summary::before{content:'▾'}
.mp-explained-wrap{border:0;border-top:1px solid #dfe7f1;border-radius:0;max-height:42vh}
.mp-explained-table th,.mp-explained-table td{padding:8px 12px;vertical-align:middle;line-height:1.25}
.mp-explained-table td{white-space:nowrap}
"""
if '/* Explained reconciliation section + uniform weights v1 */' not in css:
    css+='\n'+css_add

app_path.write_text(app,encoding='utf-8')
css_path.write_text(css,encoding='utf-8')
print('patched explained reconciliation section + uniform font weights')
