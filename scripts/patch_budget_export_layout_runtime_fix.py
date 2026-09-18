from pathlib import Path
import sys

app_path=Path(sys.argv[1] if len(sys.argv)>1 else 'budget-checker/src/app.js')
app=app_path.read_text(encoding='utf-8')

old="rounding=result.rows.filter(x=>x.roundingOnly);const notes=[];"
new="rounding=result.rows.filter(x=>x.roundingOnly),tech=result.technicalCosts||[];const notes=[];"
if old not in app:
    raise SystemExit('mpRenderComparison tech anchor not found')
app=app.replace(old,new,1)

def replace_function(src,name,new_text):
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
                    return src[:start]+new_text+src[i+1:]
        i+=1
    raise SystemExit('unterminated function '+name)

helper=r"""function mpApplyExportLayout(ws,widths){ws['!cols']=widths.map(w=>({wch:w}));if(ws['!ref']){const rg=XLSX.utils.decode_range(ws['!ref']),rows=[];for(let i=0;i<=rg.e.r;i++)rows.push({hpt:15.6});ws['!rows']=rows;}}"""
if 'function mpApplyExportLayout(' not in app:
    idx=app.find('function mpExportComparison(')
    if idx<0: raise SystemExit('mpExportComparison anchor missing')
    app=app[:idx]+helper+'\n'+app[idx:]

new_export=r"""function mpExportComparison(r){const wb=XLSX.utils.book_new(),excluded=r.channelSummary.filter(x=>x.excluded),summary=[['Сверка медиаплана с актуальным бюджетом',''],['Файл',r.fileName],['Бренд',r.brand],['Дивизион',r.division],['Флоучарт в сверке, ₽',r.controlTotal/100],['Медиаплан в сверке, ₽',r.mediaTotal/100],['Расхождение после округления, ₽',r.difference/100],['Исходная разница, ₽',(r.rawDifference??r.difference)/100],['Технические расходы медиаплана, ₽',(r.technicalTotal||0)/100],['Исключено каналов',excluded.length],['Требуют проверки',r.criticalMismatchCount??r.rows.length],['Объяснено техкостами',r.explainedMismatchCount||0],['Совпадает после округления',r.roundingNoteCount||0]],channels=[['Тип строки','Тип медиа','Канал','Флоучарт, ₽','Медиаплан, ₽','Расхождение, ₽','Исходная разница, ₽','Статус','Причина исключения','Комментарий'],...r.channelSummary.map(x=>[x.technical?'Технический расход':'Канал',x.typeMedia,x.channel,x.control/100,x.external/100,(x.roundingOnly?0:x.difference)/100,(x.rawDifference??x.difference)/100,x.technical?'Техкост медиаплана':(x.excluded?'Исключено':(x.roundingOnly?'Совпадает после округления':'В сверке')),x.excluded?mpExclusionReasonLabel(x.exclusion?.reasonCode):'',x.exclusion?.comment||'']),['Итого','','Итого в сверке',r.controlTotal/100,r.mediaTotal/100,r.difference/100,(r.rawDifference??r.difference)/100,r.overallRoundingOnly?'Совпадает после округления':'','','']],details=[['Статус','Тип','Путь','Месяц','Флоучарт, ₽','Медиаплан, ₽','Расхождение, ₽','Исходная разница, ₽','Комментарий','Источник'],...r.rows.map(d=>[d.roundingOnly?'Совпадает после округления':(d.explainedByTechnical?'Объяснено техкостом':'Требует проверки'),mpTypeLabel(d.type),(d.path||[]).join(' → '),d.month==null?'Итого':C.MONTHS[d.month],(d.control||0)/100,(d.external||0)/100,(d.roundingOnly?0:(d.difference||0))/100,(d.rawDifference??d.difference??0)/100,d.message||'',(d.sources||[]).join('; ')])];
const wsSummary=XLSX.utils.aoa_to_sheet(summary);mpApplyExportLayout(wsSummary,[40.796875,49]);XLSX.utils.book_append_sheet(wb,wsSummary,'Итоги');
const wsChannels=XLSX.utils.aoa_to_sheet(channels);mpApplyExportLayout(wsChannels,[18.5,19.69921875,31,11.8984375,13,14.5,14.5,18.796875,23.5,28.59765625]);XLSX.utils.book_append_sheet(wb,wsChannels,'По каналам');
const wsDetails=XLSX.utils.aoa_to_sheet(details);mpApplyExportLayout(wsDetails,[19.8984375,27,63.59765625,6.3984375,11.8984375,13,14.5,14.5,239.3984375,255]);XLSX.utils.book_append_sheet(wb,wsDetails,'Расхождения');
if((r.technicalCosts||[]).length){const tech=[['Тип','Наименование','Сумма, ₽','Источник'],...r.technicalCosts.map(x=>[x.kind,x.label,x.amount/100,(x.sources||[]).join('; ')])],wsTech=XLSX.utils.aoa_to_sheet(tech);mpApplyExportLayout(wsTech,[4,14.09765625,8.8984375,33.19921875]);XLSX.utils.book_append_sheet(wb,wsTech,'Технические расходы');}
if(excluded.length){const ex=[['Тип медиа','Канал','Флоучарт, ₽','Медиаплан, ₽','Причина','Комментарий'],...excluded.map(x=>[x.typeMedia,x.channel,x.control/100,x.external/100,mpExclusionReasonLabel(x.exclusion?.reasonCode),x.exclusion?.comment||''])],wsEx=XLSX.utils.aoa_to_sheet(ex);mpApplyExportLayout(wsEx,[11.09765625,16.5,11.09765625,13,23.5,28.59765625]);XLSX.utils.book_append_sheet(wb,wsEx,'Исключения');}
XLSX.writeFile(wb,`Сверка_медиаплана_${budgetSafeFilePart(r.brand)}_${budgetToday()}.xlsx`,{compression:true});}"""
app=replace_function(app,'mpExportComparison',new_export)

if '/* Export layout reference + tech runtime fix v1 */' not in app:
    app=app.replace('/* Rounding-aware reconciliation v1 */','/* Rounding-aware reconciliation v1 */\n/* Export layout reference + tech runtime fix v1 */',1)

app_path.write_text(app,encoding='utf-8')
print('patched tech runtime + export layout')
