(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./precision.js'));
  else if (root && root.MPChecks) root.MPChecks = factory(root.MPChecks);
})(typeof globalThis !== 'undefined' ? globalThis : this, function (core) {
  'use strict';
  if (!core || core.__labRulesPatched) return core;
  const originalRun = core.runAllChecks.bind(core);
  const S = core.SEVERITY;

  function textCell(cell) {
    if (!cell) return '';
    if (typeof cell.v === 'string') return cell.v;
    if (cell.t === 's' && cell.v != null) return String(cell.v);
    return '';
  }
  function issue(severity,type,sheet,cell,value,problem,why,recommendation,related) {
    return {severity,type,sheet:sheet||'',cell:cell||'',value:value||'',problem,why,recommendation,related:related||'',fixStatus:''};
  }
  function hasIssue(list, x) {
    return list.some(y=>y.severity===x.severity&&y.type===x.type&&y.sheet===x.sheet&&y.cell===x.cell&&y.problem===x.problem);
  }
  function add(list,x){ if(!hasIssue(list,x)) list.push(x); }
  function scanExplicitDuplicates(workbook,list) {
    for (const sheet of workbook.SheetNames || []) {
      const ws = workbook.Sheets[sheet];
      if (!ws) continue;
      for (const addr of Object.keys(ws)) {
        if (!/^[A-Z]{1,3}\d+$/i.test(addr)) continue;
        const raw = textCell(ws[addr]);
        if (!raw || !/[;\n]/.test(raw) || !/[A-Za-zА-Яа-яЁё]/u.test(raw)) continue;
        const parts = raw.split(/[;\n]+/).map(core.normalizeText).filter(x=>x.length>=2 && /[A-Za-zА-Яа-яЁё]/u.test(x));
        const seen=new Set(), dup=[];
        for (const p of parts) { if(seen.has(p) && !dup.includes(p)) dup.push(p); else seen.add(p); }
        if (!dup.length) continue;
        add(list, issue(S.TEXT,'Дубли таргетинга/ключевых слов',sheet,addr,raw,`В одной ячейке повторяются элементы: ${dup.slice(0,5).join(', ')}.`,'Повтор может быть случайным дублем списка.','Проверьте список и удалите лишние повторы.'));
      }
    }
  }
  function finish(result) {
    const weight={[S.CRITICAL]:0,[S.CHECK]:1,[S.TEXT]:2};
    result.issues.sort((a,b)=>(weight[a.severity]-weight[b.severity])||String(a.sheet).localeCompare(String(b.sheet),'ru')||String(a.cell).localeCompare(String(b.cell),'ru'));
    result.counts={critical:result.issues.filter(x=>x.severity===S.CRITICAL).length,check:result.issues.filter(x=>x.severity===S.CHECK).length,text:result.issues.filter(x=>x.severity===S.TEXT).length};
    result.status=result.counts.critical||result.counts.check||result.counts.text?'Нужно исправить':'Можно отправлять клиенту';
    return result;
  }
  core.runAllChecks=function(workbook,options){
    const result=originalRun(workbook,options||{});
    scanExplicitDuplicates(workbook,result.issues);
    return finish(result);
  };
  core.__labRulesPatched=true;
  return core;
});
