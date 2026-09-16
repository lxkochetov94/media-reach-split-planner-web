(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./audit-polish-rules.js'));
  else if (root && root.MPChecks) root.MPChecks = factory(root.MPChecks);
})(typeof globalThis !== 'undefined' ? globalThis : this, function (core) {
  'use strict';
  if (!core || core.__faRulesPatched) return core;

  const originalRun = core.runAllChecks.bind(core);
  const S = core.SEVERITY;
  const MONTHS = {
    january:1, february:2, march:3, april:4, may:5, june:6, july:7, august:8, september:9, october:10, november:11, december:12,
    январь:1, февраля:2, февраль:2, март:3, марта:3, апрель:4, апреля:4, май:5, мая:5, июнь:6, июня:6, июль:7, июля:7, август:8, августа:8, сентябрь:9, сентября:9, октябрь:10, октября:10, ноябрь:11, ноября:11, декабрь:12, декабря:12
  };

  function entries(ws) {
    return Object.keys(ws || {}).filter(k => /^[A-Z]{1,3}\d+$/i.test(k)).map(addr => ({addr:addr.toUpperCase(), pos:core.decodeCell(addr), cell:ws[addr]})).filter(x=>x.pos&&x.cell);
  }
  function text(cell) {
    if (!cell) return '';
    if (typeof cell.v === 'string') return cell.v;
    if (cell.t === 's' && cell.v != null) return String(cell.v);
    return '';
  }
  function num(cell) { return cell && typeof cell.v === 'number' && Number.isFinite(cell.v) ? cell.v : null; }
  function add(issues, item, same) {
    const exists = issues.some(same || (x => x.type===item.type && x.sheet===item.sheet && x.cell===item.cell && x.problem===item.problem));
    if (!exists) issues.push(item);
  }
  function mk(severity,type,sheet,cell,value,problem,why,recommendation,related='') {
    return {severity,type,sheet,cell,value:String(value==null?'':value),problem,why,recommendation,related,fixStatus:''};
  }
  function colName(n){ let s=''; for(let x=n+1;x>0;x=Math.floor((x-1)/26)) s=String.fromCharCode((x-1)%26+65)+s; return s; }

  function parseA1Rect(token) {
    let s=String(token||'').trim();
    const bang=s.lastIndexOf('!'); if (bang>=0) s=s.slice(bang+1);
    s=s.replace(/\$/g,'');
    const m=/^([A-Z]{1,3})(\d+):([A-Z]{1,3})(\d+)$/i.exec(s); if(!m) return null;
    const a=core.decodeCell(m[1]+m[2]), b=core.decodeCell(m[3]+m[4]); if(!a||!b) return null;
    return {rows:Math.abs(b.r-a.r)+1, cols:Math.abs(b.c-a.c)+1, raw:token};
  }
  function splitArgs(s) {
    const out=[]; let cur='', depth=0, quote=false;
    for(let i=0;i<s.length;i++){
      const ch=s[i];
      if(ch==='"') { quote=!quote; cur+=ch; continue; }
      if(!quote){ if(ch==='(') depth++; else if(ch===')') depth--; else if(ch===',' && depth===0){ out.push(cur.trim()); cur=''; continue; } }
      cur+=ch;
    }
    out.push(cur.trim()); return out;
  }
  function calls(formula, name) {
    const src=String(formula||''); const up=src.toUpperCase(); const needle=name.toUpperCase()+'('; const out=[];
    let from=0;
    while(true){
      const i=up.indexOf(needle,from); if(i<0) break;
      let j=i+needle.length, depth=1, quote=false;
      for(;j<src.length;j++){
        const ch=src[j]; if(ch==='"'){ quote=!quote; continue; }
        if(quote) continue; if(ch==='(') depth++; else if(ch===')'){ depth--; if(depth===0) break; }
      }
      if(depth===0) out.push(src.slice(i+needle.length,j));
      from=i+needle.length;
    }
    return out;
  }
  function addRangeGeometryChecks(workbook, issues) {
    for(const sheet of workbook.SheetNames||[]){
      const ws=workbook.Sheets[sheet]; if(!ws) continue;
      for(const e of entries(ws)){
        const f=e.cell && e.cell.f; if(typeof f!=='string') continue;
        let mismatch=null;
        for(const body of calls(f,'SUMIF')){
          const a=splitArgs(body); if(a.length<3) continue;
          const r1=parseA1Rect(a[0]), r2=parseA1Rect(a[2]);
          if(r1&&r2&&(r1.rows!==r2.rows||r1.cols!==r2.cols)){ mismatch=`SUMIF: ${a[0]} (${r1.rows}×${r1.cols}) и ${a[2]} (${r2.rows}×${r2.cols})`; break; }
        }
        if(!mismatch){
          for(const body of calls(f,'SUMIFS')){
            const a=splitArgs(body); if(a.length<3) continue;
            const sum=parseA1Rect(a[0]); if(!sum) continue;
            for(let i=1;i<a.length;i+=2){ const cr=parseA1Rect(a[i]); if(cr&&(cr.rows!==sum.rows||cr.cols!==sum.cols)){ mismatch=`SUMIFS: ${a[0]} (${sum.rows}×${sum.cols}) и ${a[i]} (${cr.rows}×${cr.cols})`; break; } }
            if(mismatch) break;
          }
        }
        if(mismatch){
          add(issues,mk(S.CRITICAL,'Формула / размерность диапазонов',sheet,e.addr,'='+f,
            'В условной сумме используются диапазоны разного размера.',
            `${mismatch}. Excel может сместить/расширить диапазон суммирования и вернуть математически неверный KPI без явной ошибки ячейки.`,
            'Приведите диапазон условия и диапазон суммирования к одинаковому числу строк и столбцов, затем перепроверьте итоговый KPI.'),
            x=>x.sheet===sheet&&x.cell===e.addr&&x.type==='Формула / размерность диапазонов');
        }
      }
    }
  }

  function parseDateRange(s){
    const m=/(\d{1,2})\.(\d{1,2})\.(\d{4})\s*[-–—]\s*(\d{1,2})\.(\d{1,2})\.(\d{4})/.exec(String(s||''));
    if(!m) return null;
    const a=new Date(Date.UTC(+m[3],+m[2]-1,+m[1])), b=new Date(Date.UTC(+m[6],+m[5]-1,+m[4]));
    return isNaN(a)||isNaN(b)?null:{start:a,end:b};
  }
  function campaignPeriod(ws){
    const es=entries(ws);
    for(const e of es){
      if(!/^(period|период)$/iu.test(text(e.cell).trim())) continue;
      for(let dc=1;dc<=3;dc++){ const c=ws[core.encodeCell(e.pos.r,e.pos.c+dc)]; const p=parseDateRange(text(c)); if(p) return p; }
    }
    for(const e of es){ const p=parseDateRange(text(e.cell)); if(p) return p; }
    return null;
  }
  function monthNumber(s){ const k=String(s||'').trim().toLowerCase().replace(/ё/g,'е'); return MONTHS[k]||null; }
  function expectedDays(period, month){
    if(!period||!month) return null;
    let total=0; const d=new Date(period.start.getTime());
    while(d<=period.end){ if(d.getUTCMonth()+1===month) total++; d.setUTCDate(d.getUTCDate()+1); }
    return total;
  }
  function findRunHeader(ws){
    for(const e of entries(ws)){
      if(e.pos.r>25) continue;
      const t=text(e.cell).trim();
      if(/^(run\s*period|active\s*days|дни\s+размещения|кол(?:-во|ичество)\s+дней)$/iu.test(t)) return e;
    }
    return null;
  }
  function addCompleteCalendarChecks(workbook, issues){
    for(const sheet of workbook.SheetNames||[]){
      const ws=workbook.Sheets[sheet]; if(!ws) continue;
      const period=campaignPeriod(ws), hdr=findRunHeader(ws); if(!period||!hdr) continue;
      const all=entries(ws); const maxRow=all.reduce((m,e)=>Math.max(m,e.pos.r),0);
      for(let r=hdr.pos.r+1;r<=maxRow;r++){
        const rc=ws[core.encodeCell(r,hdr.pos.c)], days=num(rc); if(days==null||days<=0) continue;
        let month=null;
        for(let c=Math.max(0,hdr.pos.c-40);c<hdr.pos.c;c++){
          const m=monthNumber(text(ws[core.encodeCell(r,c)])); if(m){month=m;break;}
        }
        if(!month) continue;
        const expected=expectedDays(period,month); if(expected==null||days===expected) continue;
        const addr=core.encodeCell(r,hdr.pos.c);
        add(issues,mk(S.CHECK,'Календарь размещения',sheet,addr,days,
          `Количество активных дней (${days}) не совпадает с календарным количеством дней этого месяца внутри периода кампании (${expected}).`,
          'Это может быть намеренная неполная активность, но при непрерывном флайте обычно означает пропущенный или лишний день в календарной сетке.',
          'Сверьте дату старта/финиша строки и недельную сетку; если сокращение периода намеренное — оставьте пояснение.'),
          x=>x.sheet===sheet&&x.cell===addr&&x.type==='Календарь размещения');
      }
    }
  }

  function formulaSignature(ws,row){
    return entries(ws).filter(e=>e.pos.r===row&&typeof e.cell.f==='string').map(e=>`${e.pos.c}:${e.cell.f}`).sort().join('|');
  }
  function suppressValueOnlyDuplicates(workbook, issues){
    return (issues||[]).filter(x=>{
      if(x.type!=='Возможный дубль'||!x.sheet) return true;
      const rows=(String(x.value||'').match(/\d+/g)||[]).map(Number); if(rows.length<2) return true;
      const ws=workbook.Sheets&&workbook.Sheets[x.sheet]; if(!ws) return true;
      const sigs=rows.map(r=>formulaSignature(ws,r));
      return sigs.every(s=>s===sigs[0]);
    });
  }

  const typoRules=[
    [/\bCampain\b/giu,'Campain','Campaign'],
    [/\bOut-sream\b/giu,'Out-sream','Out-stream'],
    [/\bConvertion\b/giu,'Convertion','Conversion'],
    [/\bConvertions\b/giu,'Convertions','Conversions'],
    [/Пор\s+трет\s+аудитории/giu,'Пор трет аудитории','Портрет аудитории']
  ];
  function addTypos(workbook,issues){
    for(const sheet of workbook.SheetNames||[]){ const ws=workbook.Sheets[sheet]; if(!ws) continue;
      for(const e of entries(ws)){ const raw=text(e.cell); if(!raw) continue;
        for(const [re,bad,good] of typoRules){ re.lastIndex=0; if(!re.test(raw)) continue;
          add(issues,mk(S.TEXT,'Очевидная опечатка',sheet,e.addr,raw,`Найдена явная опечатка: «${bad}».`,'Это однозначная орфографическая/техническая ошибка в подписи медиаплана.',`Исправьте на «${good}».`),x=>x.sheet===sheet&&x.cell===e.addr&&x.type==='Очевидная опечатка'&&String(x.problem||'').includes(bad));
        }
      }
    }
  }

  function addBudgetPrecision(workbook,issues){
    for(const sheet of workbook.SheetNames||[]){ const ws=workbook.Sheets[sheet]; if(!ws) continue;
      const headers=entries(ws).filter(e=>e.pos.r<=25&&/(budget\s*\(?(?:net|gross)?\)?|бюджет)/iu.test(text(e.cell)));
      const cols=[...new Set(headers.map(h=>h.pos.c))];
      for(const c of cols){
        const bad=[];
        for(const e of entries(ws)){ if(e.pos.c!==c) continue; const v=num(e.cell); if(v==null) continue; if(Math.abs(v-Math.round(v*100)/100)>1e-6) bad.push(e); }
        if(!bad.length) continue;
        const shown=bad.slice(0,10).map(e=>e.addr); const cell=shown.join(', ')+(bad.length>10?` +${bad.length-10}`:'');
        add(issues,mk(S.CHECK,'Точность бюджета',sheet,cell,bad.slice(0,5).map(e=>`${e.addr}=${e.cell.v}`).join('; '),
          `В денежных значениях обнаружена скрытая точность больше двух знаков после запятой (${bad.length} ячеек).`,
          'Визуально Excel может показывать округлённые рубли/копейки, тогда как итоговые суммы и сверки используют полное значение.',
          'Подтвердите требуемую договорную точность; при необходимости округлите денежные расчёты до 2 знаков формулой/исходными ставками.'),x=>x.sheet===sheet&&x.type==='Точность бюджета');
      }
    }
  }

  function refineMaskedRefIssues(issues){
    for(const x of issues||[]){
      if(x.type!=='Формула Excel') continue;
      const f=String(x.value||'');
      if(/IFERROR\s*\(\s*VLOOKUP\s*\([^)]*#REF!/iu.test(f)){
        x.problem='Формула выполняет обращение к битой ссылке; ошибка маскируется IFERROR.';
        x.why='Внутри реально выполняемого VLOOKUP используется #REF!, а IFERROR только скрывает ошибку отображением резервного значения.';
        x.recommendation='Восстановите корректный диапазон VLOOKUP и затем перепроверьте результат; не полагайтесь на IFERROR как на исправление ссылки.';
      }
    }
  }

  function addExtraBrandSafety(workbook,issues){
    const suspicious=/(?:kino|film|serial|dorama|lord|rezka|horrorstory|shadowandbone|emily-in-paris|modernfamily)/iu;
    const domain=/\b(?:[a-z0-9-]+\.)+(?:ru|com|net|org|tv|video|online|buzz|quest|run|ad)\b/giu;
    for(const sheet of workbook.SheetNames||[]){ const ws=workbook.Sheets[sheet]; if(!ws) continue; const found=[];
      for(const e of entries(ws)){ const raw=text(e.cell); if(!raw) continue; const ms=raw.match(domain)||[]; for(const d of ms) if(suspicious.test(d)) found.push({addr:e.addr,domain:d.toLowerCase()}); }
      const uniq=[]; const seen=new Set(); for(const f of found){ if(seen.has(f.domain)) continue; seen.add(f.domain); uniq.push(f); }
      const existing=(issues||[]).filter(x=>x.sheet===sheet&&x.type==='Brand Safety / домены').map(x=>String(x.value||'')+' '+String(x.problem||'')).join(' ').toLowerCase();
      const addl=uniq.filter(f=>!existing.includes(f.domain)); if(!addl.length) continue;
      add(issues,mk(S.CHECK,'Brand Safety / домены',sheet,addl.slice(0,12).map(x=>x.addr).join(', '),addl.slice(0,12).map(x=>x.domain).join(', '),
        `Найдены дополнительные потенциально спорные кино/сериальные домены: ${addl.slice(0,12).map(x=>x.domain).join(', ')}.`,
        'По названию домена нельзя доказать нарушение brand safety, но такой инвентарь требует ручной сверки.',
        'Проверьте домены по актуальному whitelist/blacklist клиента и правилам площадки.'),x=>x.sheet===sheet&&x.type==='Brand Safety / домены'&&String(x.problem||'').includes('дополнительные'));
    }
  }

  function finish(result){
    const seen=new Set(); result.issues=(result.issues||[]).filter(x=>{const k=[x.severity,x.type,x.sheet,x.cell,x.problem].join('|');if(seen.has(k))return false;seen.add(k);return true;});
    const w={[S.CRITICAL]:0,[S.CHECK]:1,[S.TEXT]:2}; result.issues.sort((a,b)=>(w[a.severity]-w[b.severity])||String(a.sheet).localeCompare(String(b.sheet),'ru')||String(a.cell).localeCompare(String(b.cell),'ru'));
    result.counts={critical:result.issues.filter(x=>x.severity===S.CRITICAL).length,check:result.issues.filter(x=>x.severity===S.CHECK).length,text:result.issues.filter(x=>x.severity===S.TEXT).length};
    result.status=result.issues.length?'Нужно исправить':'Можно отправлять клиенту'; return result;
  }

  core.runAllChecks=function(workbook,options){
    const result=originalRun(workbook,options||{});
    result.issues=suppressValueOnlyDuplicates(workbook,result.issues||[]);
    refineMaskedRefIssues(result.issues);
    addRangeGeometryChecks(workbook,result.issues);
    addCompleteCalendarChecks(workbook,result.issues);
    addTypos(workbook,result.issues);
    addBudgetPrecision(workbook,result.issues);
    addExtraBrandSafety(workbook,result.issues);
    return finish(result);
  };
  core.__faRulesPatched=true;
  return core;
});
