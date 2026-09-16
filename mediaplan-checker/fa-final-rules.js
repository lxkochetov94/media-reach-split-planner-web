(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./fa-rules.js'));
  else if (root && root.MPChecks) root.MPChecks = factory(root.MPChecks);
})(typeof globalThis !== 'undefined' ? globalThis : this, function (core) {
  'use strict';
  if (!core || core.__faFinalRulesPatched) return core;
  const originalRun = core.runAllChecks.bind(core), S=core.SEVERITY;
  const MONTHS={january:1,february:2,march:3,april:4,may:5,june:6,july:7,august:8,september:9,october:10,november:11,december:12,январь:1,февраль:2,март:3,апрель:4,май:5,июнь:6,июль:7,август:8,сентябрь:9,октябрь:10,ноябрь:11,декабрь:12};
  function entries(ws){return Object.keys(ws||{}).filter(k=>/^[A-Z]{1,3}\d+$/i.test(k)).map(a=>({addr:a.toUpperCase(),pos:core.decodeCell(a),cell:ws[a]})).filter(x=>x.pos&&x.cell);}
  function text(c){return c&&typeof c.v==='string'?c.v:'';} function num(c){return c&&typeof c.v==='number'&&Number.isFinite(c.v)?c.v:null;}
  function parseRange(s){const m=/(\d{1,2})\.(\d{1,2})\.(\d{4})\s*[-–—]\s*(\d{1,2})\.(\d{1,2})\.(\d{4})/.exec(String(s||''));if(!m)return null;return{start:new Date(Date.UTC(+m[3],+m[2]-1,+m[1])),end:new Date(Date.UTC(+m[6],+m[5]-1,+m[4]))};}
  function period(ws){for(const e of entries(ws)){if(/^(period|период)$/iu.test(text(e.cell).trim()))for(let d=1;d<=3;d++){const p=parseRange(text(ws[core.encodeCell(e.pos.r,e.pos.c+d)]));if(p)return p;}}return null;}
  function expected(p,m){let n=0,d=new Date(p.start);while(d<=p.end){if(d.getUTCMonth()+1===m)n++;d.setUTCDate(d.getUTCDate()+1);}return n;}
  function runHeader(ws){return entries(ws).find(e=>e.pos.r<=25&&/^(run\s*period|active\s*days|дни\s+размещения|кол(?:-во|ичество)\s+дней)$/iu.test(text(e.cell).trim()));}
  function addCalendar(wb,issues){for(const sh of wb.SheetNames||[]){const ws=wb.Sheets[sh],p=ws&&period(ws),h=ws&&runHeader(ws);if(!ws||!p||!h)continue;const max=entries(ws).reduce((m,e)=>Math.max(m,e.pos.r),0);for(let r=h.pos.r+1;r<=max;r++){const v=num(ws[core.encodeCell(r,h.pos.c)]);if(v==null||v<=0)continue;let month=null;for(let c=0;c<h.pos.c;c++){const t=text(ws[core.encodeCell(r,c)]).trim().toLowerCase();if(MONTHS[t]){month=MONTHS[t];break;}}if(!month)continue;const exp=expected(p,month);if(v===exp)continue;const addr=core.encodeCell(r,h.pos.c);if(issues.some(x=>x.sheet===sh&&x.cell===addr&&x.type==='Календарь размещения'))continue;issues.push({severity:S.CHECK,type:'Календарь размещения',sheet:sh,cell:addr,value:String(v),problem:`Количество активных дней (${v}) не совпадает с календарным количеством дней этого месяца внутри периода кампании (${exp}).`,why:'Это может быть намеренная неполная активность, но при непрерывном флайте обычно означает пропущенный или лишний день в календарной сетке.',recommendation:'Сверьте дату старта/финиша строки и недельную сетку; если сокращение периода намеренное — оставьте пояснение.',related:'',fixStatus:''});}}}
  function finish(r){const w={[S.CRITICAL]:0,[S.CHECK]:1,[S.TEXT]:2};r.issues.sort((a,b)=>(w[a.severity]-w[b.severity])||String(a.sheet).localeCompare(String(b.sheet),'ru')||String(a.cell).localeCompare(String(b.cell),'ru'));r.counts={critical:r.issues.filter(x=>x.severity===S.CRITICAL).length,check:r.issues.filter(x=>x.severity===S.CHECK).length,text:r.issues.filter(x=>x.severity===S.TEXT).length};r.status=r.issues.length?'Нужно исправить':'Можно отправлять клиенту';return r;}
  core.runAllChecks=function(wb,options){const r=originalRun(wb,options||{});addCalendar(wb,r.issues);return finish(r);};
  core.__faFinalRulesPatched=true;return core;
});
