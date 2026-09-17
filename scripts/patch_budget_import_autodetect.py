from pathlib import Path
import sys

NEW_BLOCK = r'''const HEADER_MONTH_ALIASES=[['янв','январь'],['фев','февраль'],['мар','март'],['апр','апрель'],['май'],['июн','июнь'],['июл','июль'],['авг','август'],['сен','сент','сентябрь'],['окт','октябрь'],['ноя','ноябрь'],['дек','декабрь']];
function guessHeaderRow(rows){
 let best={score:-1,row:1};
 const dimTokens=['бренд','продукт','тип медиа','медиа','канал','дивиз','линей','площад'];
 for(let i=0;i<Math.min(25,rows.length);i++){
  const current=(rows[i]||[]).map(v=>C.normalizeText(v)).filter(Boolean),next=(rows[i+1]||[]).map(v=>C.normalizeText(v)).filter(Boolean),vals=[...current,...next];
  if(!vals.length)continue;
  const dimCount=dimTokens.filter(t=>vals.some(v=>v===t||v.includes(t))).length;
  const monthCount=HEADER_MONTH_ALIASES.filter(a=>vals.some(v=>a.includes(v))).length;
  const hasAnnual=vals.some(v=>v==='итого'||v.includes('всего')||v.includes('total')||v.includes('net'));
  if(dimCount<1||(!hasAnnual&&monthCount<3))continue;
  const score=dimCount*6+monthCount*4+(hasAnnual?3:0)+(current.length?1:0);
  if(score>best.score)best={score,row:i+1};
 }
 return best.row;
}
function findHeaderCol(rows,headerRow,names){
 const wanted=names.map(C.normalizeText),start=Math.max(0,Number(headerRow||1)-1),end=Math.min(rows.length,start+3);
 for(const exact of [true,false])for(let rr=start;rr<end;rr++){const row=rows[rr]||[];for(let i=0;i<row.length;i++){const v=C.normalizeText(row[i]);if(!v)continue;if(exact?wanted.includes(v):wanted.some(n=>v.includes(n)))return I.indexToCol(i);}}
 return '';
}
function looksNumeric(v){return typeof v==='number'&&Number.isFinite(v)||(typeof v==='string'&&/^-?[\d\s]+(?:[.,]\d+)?$/.test(v.trim()));}
function guessDataStartRow(rows,headerRow,moneyColumns,hierarchy){
 const money=(moneyColumns||[]).filter(Boolean).map(I.colToIndex),hierCols=(hierarchy||[]).filter(x=>x.source!=='sheet'&&x.column).map(x=>I.colToIndex(x.column));
 for(let i=Math.max(0,Number(headerRow||1));i<rows.length;i++){
  const row=rows[i]||[],hasMoney=money.some(ci=>{const v=row[ci];return v!==null&&v!==undefined&&v!==''&&looksNumeric(v);}),hasPath=!hierCols.length||hierCols.some(ci=>String(row[ci]??'').trim()!=='');
  if(hasMoney&&hasPath)return i+1;
 }
 return Math.min(rows.length||1,Number(headerRow||1)+1);
}
function guessTotalRules(rows,hierarchy,dataStartRow){
 const markers=new Set(['всего','итого','тотал','total','subtotal']),rules=[],seen=new Set();
 for(const map of hierarchy||[]){
  if(map.source==='sheet'||!map.column)continue;
  const ci=I.colToIndex(map.column);
  for(let i=Math.max(0,Number(dataStartRow||1)-1);i<rows.length;i++){
   const raw=String((rows[i]||[])[ci]??'').trim(),n=C.normalizeText(raw);if(!raw||!markers.has(n))continue;
   const key=map.column+'|'+n;if(seen.has(key))continue;seen.add(key);rules.push({column:map.column,operator:'equals',value:raw});
  }
 }
 return rules;
}
function guessSheetLevelValue(name,summaryRows,summaryConfig,level){
 if(!summaryRows||!summaryConfig)return name;
 const map=(summaryConfig.hierarchy||[]).find(x=>Number(x.level)===Number(level));if(!map?.column)return name;
 const ci=I.colToIndex(map.column),nameNorm=C.normalizeText(name),candidates=[];
 for(let i=Math.max(0,Number(summaryConfig.dataStartRow||1)-1);i<summaryRows.length;i++){
  const raw=String((summaryRows[i]||[])[ci]??'').trim(),n=C.normalizeText(raw);if(n.length>=3&&nameNorm.includes(n))candidates.push({raw,n});
 }
 candidates.sort((a,b)=>b.n.length-a.n.length);return candidates[0]?.raw||name;
}
function guessDetailConfig(name,rows,levels,summaryRows=null,summaryConfig=null){
 const hr=guessHeaderRow(rows);const brand=findHeaderCol(rows,hr,['бренды','бренд'])||'B';const prod=findHeaderCol(rows,hr,['продукт'])||'C';const type=findHeaderCol(rows,hr,['тип медиа'])||'D';const media=findHeaderCol(rows,hr,['медиа','канал'])||'E';const monthNames=['янв','фев','мар','апр','май','июн','июл','авг','сен','окт','ноя','дек'];const m=monthNames.map(x=>findHeaderCol(rows,hr,[x]));const annual=findHeaderCol(rows,hr,['итого'])||findHeaderCol(rows,hr,['всего (до ндс)'])||'';const hierarchy=[];levels.forEach((label,idx)=>{const n=C.normalizeText(label);let col='';if(n.includes('дивиз'))hierarchy.push({level:idx,source:'sheet',column:''});else{if(n.includes('бренд'))col=brand;else if(n.includes('продукт')||n.includes('линей'))col=prod;else if(n.includes('тип медиа')||n==='медиа')col=type;else if(n.includes('канал')||n.includes('площад'))col=media;hierarchy.push({level:idx,source:'column',column:col});}});const dataStartRow=guessDataStartRow(rows,hr,[...m,annual],hierarchy);const cfg={sheetName:name,headerRow:hr,dataStartRow,hierarchy,monthColumns:m,annualTotalColumn:annual,sheetLevelValue:name,rowRules:[]};const sheetMap=hierarchy.find(x=>x.source==='sheet');if(sheetMap)cfg.sheetLevelValue=guessSheetLevelValue(name,summaryRows,summaryConfig,sheetMap.level);cfg.rowRules=guessTotalRules(rows,hierarchy,dataStartRow);return cfg;
}
function guessSummaryConfig(name,rows,levels){
 const hr=guessHeaderRow(rows);const hierarchy=[];levels.forEach((label,idx)=>{const c=findHeaderCol(rows,hr,[label]);if(c)hierarchy.push({level:idx,column:c});});const annual=findHeaderCol(rows,hr,['всего net','всего','итого']);const dataStartRow=guessDataStartRow(rows,hr,[annual],hierarchy.map(x=>({source:'column',column:x.column})));const cfg={sheetName:name,headerRow:hr,dataStartRow,hierarchy,annualTotalColumn:annual,rowRules:[],valueAliases:{}};cfg.rowRules=guessTotalRules(rows,hierarchy.map(x=>({source:'column',column:x.column})),dataStartRow);return cfg;
}'''

OLD_INIT = "for(const n of w.detailSheets) if(!w.configs[n]) w.configs[n]=guessDetailConfig(n,state.sourceWorkbook.sheets[n],w.hierarchyLabels);if(w.summarySheet&&!w.summaryConfig)w.summaryConfig=guessSummaryConfig(w.summarySheet,state.sourceWorkbook.sheets[w.summarySheet],w.hierarchyLabels);"
NEW_INIT = "if(w.summarySheet&&!w.summaryConfig)w.summaryConfig=guessSummaryConfig(w.summarySheet,state.sourceWorkbook.sheets[w.summarySheet],w.hierarchyLabels);for(const n of w.detailSheets) if(!w.configs[n]) w.configs[n]=guessDetailConfig(n,state.sourceWorkbook.sheets[n],w.hierarchyLabels,w.summarySheet?state.sourceWorkbook.sheets[w.summarySheet]:null,w.summaryConfig);"

def patch(path: Path):
    text = path.read_text(encoding='utf-8')
    start = text.find('function guessHeaderRow(rows){')
    end = text.find('function mappingWizardHtml', start)
    if start < 0 or end < 0:
        raise SystemExit('Import autodetection block not found')
    text = text[:start] + NEW_BLOCK + '\n' + text[end:]
    if OLD_INIT not in text:
        if NEW_INIT not in text:
            raise SystemExit('Wizard initialization snippet not found')
    else:
        text = text.replace(OLD_INIT, NEW_INIT, 1)
    path.write_text(text, encoding='utf-8')

if __name__ == '__main__':
    target = Path(sys.argv[1] if len(sys.argv) > 1 else 'budget-checker/src/app.js')
    patch(target)
