(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./final-cleanup-rules.js'));
  else if (root && root.MPChecks) root.MPChecks = factory(root.MPChecks);
})(typeof globalThis !== 'undefined' ? globalThis : this, function (core) {
  'use strict';
  if (!core || core.__markupRulesPatched) return core;

  const originalRun = core.runAllChecks.bind(core);
  const S = core.SEVERITY;

  function norm(v) {
    return String(v == null ? '' : v)
      .replace(/\u00a0/g, ' ')
      .replace(/[–—−]/g, '-')
      .replace(/ё/g, 'е')
      .replace(/\s+/g, ' ')
      .trim()
      .toLowerCase();
  }
  function text(cell) {
    if (!cell) return '';
    if (cell.w != null && cell.w !== '') return String(cell.w);
    if (cell.v == null) return '';
    return String(cell.v);
  }
  function num(cell) {
    if (!cell) return null;
    if (typeof cell.v === 'number' && Number.isFinite(cell.v)) return Number(cell.v);
    const s=String(cell.w!=null?cell.w:(cell.v!=null?cell.v:''))
      .replace(/\u00a0/g,' ').replace(/\s+/g,'').replace(',','.')
      .replace(/[^0-9.+-]/g,'');
    if (!s) return null;
    const n=Number(s);
    return Number.isFinite(n) ? n : null;
  }
  function entries(ws) {
    return Object.keys(ws || {})
      .filter(k=>/^[A-Z]{1,3}\d+$/i.test(k))
      .map(addr=>({addr:addr.toUpperCase(),pos:core.decodeCell(addr),cell:ws[addr]}))
      .filter(x=>x.pos&&x.cell);
  }
  function cellAt(ws,r,c){ return ws && ws[core.encodeCell(r,c)]; }
  function issue(severity,type,sheet,cell,value,problem,why,recommendation,related) {
    return {severity,type,sheet:sheet||'',cell:cell||'',value:value==null?'':String(value),problem,why,recommendation,related:related||'',fixStatus:''};
  }
  function key(x){ return [x.severity,x.type,x.sheet,x.cell,x.problem,x.related].join('|'); }
  function add(list,x){ if(!list.some(y=>key(y)===key(x))) list.push(x); }

  function findPlacementHeader(ws){
    const es=entries(ws);
    if(!es.length) return null;
    const maxC=Math.min(220,Math.max(...es.map(e=>e.pos.c)));
    const maxR=Math.min(45,Math.max(...es.map(e=>e.pos.r)));
    for(let r=0;r<=maxR;r++){
      let site=null,markup=null,format=null,placement=null;
      for(let c=0;c<=maxC;c++){
        const h=norm(text(cellAt(ws,r,c)));
        if(!h) continue;
        if(site==null && /^(?:site|platform|площадка|название сайта|название площадки)$/iu.test(h)) site=c;
        if(markup==null && /^(?:наценк\w*|markup|mark-up|коэффициент наценки)$/iu.test(h)) markup=c;
        if(format==null && /^(?:format|формат|ad size(?: \(pixels\))?|размер(?: объявления)?)$/iu.test(h)) format=c;
        if(placement==null && /^(?:ad placement(?: & targetings)?|размещение|placement)$/iu.test(h)) placement=c;
      }
      if(site!=null && markup!=null) return {row:r,site,markup,format,placement};
    }
    return null;
  }

  function isVk(site){
    const s=norm(site).replace(/[._-]/g,' ');
    return /^(?:vk|вк|vkontakte|вконтакте)(?:\s+(?:com|ads|реклама))*$/iu.test(s);
  }
  function isYandexAuctionNoMarkup(site,format,placement){
    const full=norm([site,format,placement].filter(Boolean).join(' | '));
    if(!/(?:yandex|яндекс)/iu.test(full)) return false;
    const multiroll=/(?:multi\s*-?\s*roll|multiroll|мульти\s*-?\s*ролл|мультиролл)/iu.test(full);
    const banners=/(?:banner|баннер)/iu.test(full);
    return multiroll || banners;
  }
  function expectedNoMarkupReason(site,format,placement){
    if(isVk(site)) return 'VK';
    if(isYandexAuctionNoMarkup(site,format,placement)){
      const full=norm([site,format,placement].join(' | '));
      return /(?:multi\s*-?\s*roll|multiroll|мульти\s*-?\s*ролл|мультиролл)/iu.test(full)
        ? 'Яндекс Видео (Multiroll)'
        : 'Яндекс Баннеры';
    }
    return '';
  }

  function addMarkupChecks(workbook,issues){
    for(const sheet of workbook.SheetNames||[]){
      const ws=workbook.Sheets&&workbook.Sheets[sheet];
      if(!ws) continue;
      const h=findPlacementHeader(ws);
      if(!h) continue;
      const maxR=entries(ws).reduce((m,e)=>Math.max(m,e.pos.r),h.row);
      let blankRun=0;
      for(let r=h.row+1;r<=maxR;r++){
        const site=text(cellAt(ws,r,h.site)).trim();
        if(!site){ if(++blankRun>=20) break; continue; }
        blankRun=0;
        if(/^(?:total|итого|всего)$/iu.test(norm(site))) continue;
        const format=h.format!=null?text(cellAt(ws,r,h.format)).trim():'';
        const placement=h.placement!=null?text(cellAt(ws,r,h.placement)).trim():'';
        const reason=expectedNoMarkupReason(site,format,placement);
        if(!reason) continue;

        const markupCell=cellAt(ws,r,h.markup);
        const markup=num(markupCell);
        if(markup!=null && Math.abs(markup-1)<=1e-9) continue;

        const addr=core.encodeCell(r,h.markup);
        const shown=text(markupCell).trim();
        const actual=shown || (markup==null?'пусто':String(markup));
        add(issues,issue(
          S.CRITICAL,
          'Наценка площадки',
          sheet,
          addr,
          actual,
          `${reason}: наценка должна быть 1,00, сейчас «${actual}».`,
          reason==='VK'
            ? 'Для размещений VK наценка в медиаплане не применяется.'
            : 'Для этого аукционного формата Яндекса наценка в медиаплане не применяется.',
          'Установите наценку 1,00 и перепроверьте зависимые стоимости/CPM/CPC.',
          `${site}${format?' · '+format:''}`
        ));
      }
    }
  }

  function finish(result){
    const order={[S.CRITICAL]:0,[S.CHECK]:1,[S.TEXT]:2};
    result.issues.sort((a,b)=>(order[a.severity]-order[b.severity])||String(a.sheet).localeCompare(String(b.sheet),'ru')||String(a.cell).localeCompare(String(b.cell),'ru'));
    result.counts={
      critical:result.issues.filter(x=>x.severity===S.CRITICAL).length,
      check:result.issues.filter(x=>x.severity===S.CHECK).length,
      text:result.issues.filter(x=>x.severity===S.TEXT).length
    };
    result.status=result.issues.length?'Нужно исправить':'Можно отправлять клиенту';
    return result;
  }

  core.runAllChecks=function(workbook,options){
    const result=originalRun(workbook,options||{});
    addMarkupChecks(workbook,result.issues);
    return finish(result);
  };
  core.__markupRulesPatched=true;
  return core;
});
