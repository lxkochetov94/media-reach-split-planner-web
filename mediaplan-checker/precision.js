(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./core.js'));
  else if (root && root.MPChecks) root.MPChecks = factory(root.MPChecks);
})(typeof globalThis !== 'undefined' ? globalThis : this, function (core) {
  'use strict';
  if (!core || core.__precisionPatched) return core;

  const originalRun = core.runAllChecks.bind(core);
  const S = core.SEVERITY;
  const ERROR_TOKENS = ['#REF!', '#DIV/0!', '#VALUE!', '#N/A', '#NAME?', '#NUM!', '#NULL!'];
  const MONTHS = {
    january:1,jan:1,'янв':1,'январ':1,'января':1,
    february:2,feb:2,'фев':2,'феврал':2,'февраля':2,
    march:3,mar:3,'мар':3,'март':3,'марта':3,
    april:4,apr:4,'апр':4,'апрел':4,'апреля':4,
    may:5,'май':5,'мая':5,
    june:6,jun:6,'июн':6,'июня':6,
    july:7,jul:7,'июл':7,'июля':7,
    august:8,aug:8,'авг':8,'август':8,'августа':8,
    september:9,sep:9,sept:9,'сен':9,'сент':9,'сентябр':9,'сентября':9,
    october:10,oct:10,'окт':10,'октябр':10,'октября':10,
    november:11,nov:11,'ноя':11,'нояб':11,'ноябр':11,'ноября':11,
    december:12,dec:12,'дек':12,'декабр':12,'декабря':12
  };
  const STOP = new Set(['который','которая','которые','этого','этой','этот','также','более','менее','через','между','после','перед','будет','будут','может','могут','только','нужно','надо','данной','данного','данный','данная','разных','своей','своего','всего','очень','если','почему','например','периода','период','месяца','месяцев','месяц']);

  function rawString(cell) {
    if (!cell) return '';
    if (typeof cell.v === 'string') return cell.v;
    if (cell.t === 's' && cell.v != null) return String(cell.v);
    return '';
  }
  function isNum(cell) { return !!cell && typeof cell.v === 'number' && Number.isFinite(cell.v); }
  function cell(workbook, sheet, addr) { return workbook && workbook.Sheets && workbook.Sheets[sheet] && workbook.Sheets[sheet][addr] || null; }
  function hidden(workbook, sheet, addr) {
    const ws = workbook.Sheets && workbook.Sheets[sheet], p = core.decodeCell(addr);
    if (!ws || !p) return false;
    return !!((ws['!rows'] && ws['!rows'][p.r] && ws['!rows'][p.r].hidden) || (ws['!cols'] && ws['!cols'][p.c] && ws['!cols'][p.c].hidden));
  }
  function entries(ws) {
    return Object.keys(ws || {}).filter(k=>/^[A-Z]{1,3}\d+$/i.test(k)).map(addr=>({addr:addr.toUpperCase(),pos:core.decodeCell(addr),cell:ws[addr]})).filter(x=>x.pos && x.cell && (x.cell.v!=null || x.cell.f));
  }
  function bounds(ws) {
    const e=entries(ws); if(!e.length) return {s:{r:0,c:0},e:{r:0,c:0},entries:e};
    let minR=Infinity,minC=Infinity,maxR=-1,maxC=-1;
    for(const x of e){minR=Math.min(minR,x.pos.r);minC=Math.min(minC,x.pos.c);maxR=Math.max(maxR,x.pos.r);maxC=Math.max(maxC,x.pos.c);}
    return {s:{r:minR,c:minC},e:{r:maxR,c:maxC},entries:e};
  }
  function issue(severity,type,sheet,cellAddr,value,problem,why,recommendation,related) {
    return {severity,type,sheet:sheet||'',cell:cellAddr||'',value:value==null?'':String(value),problem:problem||'',why:why||'',recommendation:recommendation||'Проверьте вручную.',related:related||'',fixStatus:''};
  }
  function keyIssue(x){return [x.severity,x.type,x.sheet,x.cell,x.problem,x.related].join('|');}
  function add(list,x){if(!list.some(y=>keyIssue(y)===keyIssue(x))) list.push(x);}
  function monthFromText(text) {
    const n=core.normalizeText(text).replace(/[.'’]/g,''); if(!n) return null;
    for(const [k,v] of Object.entries(MONTHS)) if(n===k || n.startsWith(k)) return v;
    return null;
  }
  function parseRange(text) {
    const t=core.extractDateTokensFromText(text); if(t.length<2 || !t[0].year || !t[1].year) return null;
    const a=new Date(Date.UTC(t[0].year,t[0].month-1,t[0].day)), b=new Date(Date.UTC(t[1].year,t[1].month-1,t[1].day));
    if(Number.isNaN(+a)||Number.isNaN(+b)) return null; return {start:a,end:b};
  }
  function simpleSum(formula) {
    const f=String(formula||'').replace(/^=/,'').replace(/\s+/g,'');
    const m=/^SUM\((\$?[A-Z]{1,3}\$?\d+):(\$?[A-Z]{1,3}\$?\d+)\)$/i.exec(f);
    return m?{start:m[1].replace(/\$/g,''),end:m[2].replace(/\$/g,'')}:null;
  }
  function summarize(cells) {
    const a=[...new Set((cells||[]).filter(Boolean))]; if(a.length<=1) return a[0]||'';
    const p=a.map(x=>({a:x,p:core.decodeCell(x)}));
    if(p.every(x=>x.p)){
      const cols=new Set(p.map(x=>x.p.c)), rows=p.map(x=>x.p.r).sort((x,y)=>x-y);
      if(cols.size===1 && rows.every((r,i)=>i===0||r===rows[i-1]+1)) return `${core.encodeCell(rows[0],p[0].p.c)}:${core.encodeCell(rows[rows.length-1],p[0].p.c)}`;
    }
    return a.length<=5?a.join(', '):`${a.slice(0,5).join(', ')} +${a.length-5}`;
  }

  function filterNoise(issues, workbook) {
    const out=[];
    for(const x of issues) {
      const c=cell(workbook,x.sheet,x.cell);
      if(x.severity===S.TEXT && x.sheet && x.cell) {
        const raw=rawString(c);
        if(!raw) continue;
        if(x.type==='Пробелы' && /двойн|множествен/i.test(x.problem) && !/[ \t]{2,}/.test(raw)) continue;
        if(x.type==='Дубли таргетинга/ключевых слов') {
          if(!/[;\n]/.test(raw) || !/[A-Za-zА-Яа-яЁё]/u.test(raw)) continue;
          const parts=raw.split(/[;\n]+/).map(core.normalizeText).filter(v=>v.length>=2 && /[A-Za-zА-Яа-яЁё]/u.test(v));
          const s=new Set(),d=new Set(); for(const p of parts){if(s.has(p))d.add(p);else s.add(p);} if(!d.size) continue;
        }
      }
      if(x.type==='Ручное значение среди формул') continue;
      if(x.type==='Математика медиаплана' && c && c.f) continue;
      out.push({...x});
    }
    return out;
  }

  function normalizeFormulaErrors(issues, workbook) {
    const byCell=new Map(), rest=[];
    for(const x of issues) {
      if((x.type==='Ошибка Excel'||x.type==='Формула Excel') && x.sheet && /^[A-Z]+\d+$/i.test(x.cell)) {
        const k=`${x.sheet}|${x.cell}`; if(!byCell.has(k))byCell.set(k,[]); byCell.get(k).push(x);
      } else rest.push(x);
    }
    for(const arr of byCell.values()) {
      const base=arr.find(x=>x.type==='Формула Excel')||arr[0], c=cell(workbook,base.sheet,base.cell);
      const active=!!(c && (c.t==='e'||ERROR_TOKENS.includes(String(c.w||c.v||'').trim().toUpperCase())));
      const isHidden=hidden(workbook,base.sheet,base.cell);
      const y={...base};
      y.severity=active&&!isHidden?S.CRITICAL:S.CHECK;
      if(active&&isHidden){y.problem='В скрытой/служебной ячейке сохранена ошибка Excel.';y.why='Скрытый блок может не влиять на видимые итоги сейчас, но технически содержит ошибку.';}
      else if(!active){y.problem='Формула содержит битую ссылку в неактивной ветке.';y.why='Текущее значение корректно, но при смене условия или копировании строки ошибка может активироваться.';}
      rest.push(y);
    }
    return rest;
  }

  function groupFormulaRanges(issues) {
    const candidates=new Map(), other=[];
    for(const x of issues) {
      const p=core.decodeCell(x.cell);
      if(p && x.type==='Формула Excel') {
        const k=[x.severity,x.type,x.sheet,x.problem,x.why,x.recommendation].join('|'); if(!candidates.has(k))candidates.set(k,[]); candidates.get(k).push(x);
      } else other.push(x);
    }
    for(const arr of candidates.values()) {
      arr.sort((a,b)=>{const p=core.decodeCell(a.cell),q=core.decodeCell(b.cell);return p.c-q.c||p.r-q.r;});
      let run=[]; const flush=()=>{if(!run.length)return;if(run.length===1)other.push(run[0]);else{const cells=run.map(x=>x.cell);other.push({...run[0],cell:summarize(cells),related:cells.join(', ')});}run=[];};
      for(const x of arr){if(!run.length){run=[x];continue;}const p=core.decodeCell(x.cell),q=core.decodeCell(run[run.length-1].cell);if(p.c===q.c&&p.r===q.r+1)run.push(x);else{flush();run=[x];}} flush();
    }
    return other;
  }

  function addTextPrecision(workbook, list) {
    for(const sheet of workbook.SheetNames||[]) {
      const ws=workbook.Sheets[sheet]; if(!ws)continue;
      for(const e of entries(ws)) {
        const raw=rawString(e.cell); if(!raw)continue;
        const common=[sheet,e.addr,raw];
        if(/\u00A0/.test(raw)) add(list,issue(S.TEXT,'Пробелы',...common,'Обнаружен неразрывный пробел.','Он визуально почти не отличается от обычного, но мешает поиску и сравнению.','Замените на обычный пробел, если специальная верстка не нужна.'));
        if(/\bcost\s+per\s+unt\b/i.test(raw)) add(list,issue(S.TEXT,'Очевидная опечатка',...common,'Опечатка: «Cost per unt».','В заголовке пропущена буква i.','Исправьте на «Cost per unit».'));
        if(/(^|[^А-Яа-яЁё])стойки\s+кондиционер(?=$|[^А-Яа-яЁё])/iu.test(raw)) add(list,issue(S.TEXT,'Очевидная опечатка',...common,'Возможная опечатка: «стойки кондиционер».','По смыслу ожидается форма «стойкий кондиционер».','Проверьте и исправьте на «стойкий кондиционер», если это не специальная формулировка.'));
        if(/(^|[^А-Яа-яЁё])видео\s+ролик(ов|а|и|ами|ах)?(?=$|[^А-Яа-яЁё])/iu.test(raw)) add(list,issue(S.TEXT,'Очевидная опечатка',...common,'«Видеоролик» написан раздельно.','В клиентском тексте корректнее слитное написание.','Исправьте «видео ролик(ов)» на «видеоролик(ов)».'));
        const taut=tautology(raw); if(taut) add(list,issue(S.TEXT,'Возможная тавтология',...common,`В длинном тексте многократно повторяется основа «${taut.stem}…» (${taut.count} раз).`,'Это не доказанная ошибка, но формулировка может выглядеть тяжело и шаблонно.','Перечитайте абзац и сократите повторяющиеся слова.'));
      }
    }
  }
  function tautology(text) {
    if(String(text).length<140)return null;
    const words=(core.normalizeText(text).match(/[а-яёa-z]{6,}/giu)||[]).filter(w=>!STOP.has(w)); const m=new Map();
    for(const w of words){const st=w.slice(0,6);m.set(st,(m.get(st)||0)+1);} let best=null; for(const [stem,count] of m)if(count>=3&&(!best||count>best.count))best={stem,count}; return best;
  }

  function addFormulaCompatibility(workbook,list) {
    for(const sheet of workbook.SheetNames||[]) {
      const ws=workbook.Sheets[sheet];if(!ws)continue;const xlfn=[],datev=[];
      for(const e of entries(ws)) {
        const f=String(e.cell.f||''); if(!f)continue;
        if(/_xlfn\./i.test(f))xlfn.push(e.addr);
        if(/DATEVALUE\s*\(/i.test(f)&&(/LEFT\s*\([^,]+,\s*5\s*\)/i.test(f)||/DATEVALUE\s*\(\s*"?\d{1,2}[.\/-]\d{1,2}"?\s*\)/i.test(f)))datev.push(e.addr);
      }
      if(xlfn.length)add(list,issue(S.CHECK,'Совместимость Excel',sheet,summarize(xlfn),'',`Найдено ${xlfn.length} формул с префиксом _xlfn.`,`Современный Excel обычно поддерживает такие функции, но старые версии могут не поддерживать их.`,`Если файл должен открываться в старом Excel — проверьте совместимость; иначе исправление не требуется.`,xlfn.slice(0,30).join(', ')));
      if(datev.length)add(list,issue(S.CHECK,'Формулы дат',sheet,summarize(datev),'',`Найдено ${datev.length} формул DATEVALUE, которые собирают дату без явного года.`,`Результат может зависеть от локали и текущего года на другом компьютере.`,`Надёжнее хранить реальные даты с годом и показывать их форматом dd.mm.`,datev.slice(0,30).join(', ')));
    }
  }

  function rowFeatures(ws,r) {
    const out=[];for(let c=0;c<=18;c++){const s=rawString(ws[core.encodeCell(r,c)]);if(!s)continue;const n=core.normalizeText(s);if(!n||monthFromText(n)||/^\d{1,2}[.\/-]\d{1,2}/.test(n))continue;if(n.length>=2)out.push(n);}return out;
  }
  function paired(ws,r1,r2) {
    const a=new Set(rowFeatures(ws,r1)),b=new Set(rowFeatures(ws,r2));if(a.size<2||b.size<2)return false;let common=0;for(const x of a)if(b.has(x))common++;return common>=2&&common/Math.max(a.size,b.size)>=0.45;
  }
  function addPairedHardcodes(workbook,list) {
    for(const sheet of workbook.SheetNames||[]) {
      const ws=workbook.Sheets[sheet];if(!ws)continue;const b=bounds(ws);
      for(let r=b.s.r;r<b.e.r;r++){
        if(!paired(ws,r,r+1))continue;const bad=[];
        for(let c=Math.max(8,b.s.c);c<=Math.min(50,b.e.c);c++){
          const a=ws[core.encodeCell(r,c)],d=ws[core.encodeCell(r+1,c)];if(!a||!d)continue;
          const af=!!a.f,df=!!d.f,al=isNum(a)&&!af,dl=isNum(d)&&!df;if((af&&dl)||(df&&al))bad.push(core.encodeCell(af?r+1:r,c));
        }
        if(bad.length>=2)add(list,issue(S.CHECK,'Связанные ячейки',sheet,summarize(bad),'',`В парных строках ${r+1}/${r+2} часть расчётных полей задана формулами, а часть — ручными числами (${bad.length} ячеек).`,`При изменении объёма или ставки строки могут перестать пересчитываться синхронно.`,`Проверьте, какие поля входные; производные KPI лучше считать одинаково во всех парных строках.`,bad.join(', ')));
      }
    }
  }

  function primaryPeriod(ws) {
    const c=[];for(const e of entries(ws)){if(e.pos.r>12)continue;const p=parseRange(core.getCellText(e.cell));if(!p)continue;const days=Math.floor((p.end-p.start)/86400000)+1;if(days>0&&days<=370)c.push({...p,item:e});}c.sort((a,b)=>a.item.pos.r-b.item.pos.r||a.item.pos.c-b.item.pos.c);return c[0]||null;
  }
  function rowMonth(ws,r) {for(let c=0;c<=20;c++){const m=monthFromText(rawString(ws[core.encodeCell(r,c)]));if(m)return m;}return null;}
  function expectedDays(p,m){let n=0,d=new Date(p.start);while(d<=p.end){if(d.getUTCMonth()+1===m)n++;d.setUTCDate(d.getUTCDate()+1);}return n||null;}
  function headerDateEvidence(ws,sum,row) {
    const a=core.decodeCell(sum.start),b=core.decodeCell(sum.end);if(!a||!b)return 0;let n=0;for(let rr=Math.max(0,row-8);rr<row;rr++)for(let c=Math.min(a.c,b.c);c<=Math.max(a.c,b.c);c++)if(core.extractDateTokensFromText(core.getCellText(ws[core.encodeCell(rr,c)])).length)n++;return n;
  }
  function dayCandidates(workbook) {
    const all={};for(const sheet of workbook.SheetNames||[]){const ws=workbook.Sheets[sheet],p=primaryPeriod(ws);if(!p)continue;const b=bounds(ws),arr=[];for(const e of b.entries){if(!e.cell.f||!isNum(e.cell)||e.cell.v<1||e.cell.v>31||Math.abs(e.cell.v-Math.round(e.cell.v))>1e-9)continue;const sum=simpleSum(e.cell.f);if(!sum)continue;const a=core.decodeCell(sum.start),z=core.decodeCell(sum.end);if(!a||!z||Math.abs(a.c-z.c)<4||headerDateEvidence(ws,sum,e.pos.r)<3)continue;const m=rowMonth(ws,e.pos.r);if(m)arr.push({addr:e.addr,row:e.pos.r,col:e.pos.c,month:m,value:e.cell.v,period:p});}if(arr.length)all[sheet]=arr;}return all;
  }
  function addCalendar(workbook,list) {
    for(const sheet of workbook.SheetNames||[]){const ws=workbook.Sheets[sheet],rows=new Map();for(const e of entries(ws)){const raw=rawString(e.cell)||core.getCellText(e.cell),t=core.extractDateTokensFromText(raw);if(t.length===1&&!t[0].year&&/^\s*\d{1,2}[.\/-]\d{1,2}\s*$/.test(String(raw))){if(!rows.has(e.pos.r))rows.set(e.pos.r,[]);rows.get(e.pos.r).push({e,t:t[0]});}}for(const arr of rows.values()){if(arr.length<4)continue;arr.sort((a,b)=>a.e.pos.c-b.e.pos.c);for(let i=1;i<arr.length;i++){const p=arr[i-1].t,n=arr[i].t,po=p.month*40+p.day,no=n.month*40+n.day,wrap=p.month>=11&&n.month<=2;if(!wrap&&no<po-20)add(list,issue(S.TEXT,'Календарь',sheet,arr[i].e.addr,core.getCellText(arr[i].e.cell),`Дата «${core.getCellText(arr[i].e.cell)}» выбивается назад из последовательности календаря.`,`Предыдущая подпись: «${core.getCellText(arr[i-1].e.cell)}». Похоже на опечатку месяца.`,`Проверьте подпись даты.`,arr[i-1].e.addr));}}}
    const dc=dayCandidates(workbook);
    for(const [sheet,arr] of Object.entries(dc))for(const x of arr){const exp=expectedDays(x.period,x.month);if(exp!=null&&x.value!==exp)add(list,issue(S.CHECK,'Календарь размещения',sheet,x.addr,x.value,`Количество активных дней (${x.value}) не совпадает с календарным количеством дней этого месяца внутри периода кампании (${exp}).`,`Это может быть намеренная неполная активность, но в непрерывном флайте обычно указывает на пропущенный/лишний день или несостыковку шапки и календаря.`,`Сверьте дату старта/финиша и недельную сетку.`,x.period.item.addr));}
    addSummaryPeriod(workbook,list,dc);
  }
  function formulaRefs(f){const a=[];const re=/(?:(?:'((?:[^']|'')+)'|([A-Za-zА-Яа-яЁё0-9_ .-]+))!)?(\$?[A-Z]{1,3}\$?\d+)/g;let m;while((m=re.exec(f||'')))a.push({sheet:(m[1]||m[2]||'').replace(/''/g,"'").trim(),addr:m[3].replace(/\$/g,'').toUpperCase()});return a;}
  function addSummaryPeriod(workbook,list,dc){for(const sheet of workbook.SheetNames||[]){const ws=workbook.Sheets[sheet];for(const e of entries(ws)){if(!e.cell.f)continue;let label='';for(let d=1;d<=4;d++){const c=e.pos.c-d;if(c<0)break;label+=' '+rawString(ws[core.encodeCell(e.pos.r,c)]);}if(!/период.*(дн|day)|длительност.*(дн|day)/i.test(core.normalizeText(label)))continue;const refs=formulaRefs(e.cell.f);for(const [target,arr] of Object.entries(dc)){const ref=refs.filter(r=>core.normalizeText(r.sheet)===core.normalizeText(target)).map(r=>r.addr),addresses=arr.map(x=>x.addr);if(!ref.some(a=>addresses.includes(a)))continue;const miss=addresses.filter(a=>!ref.includes(a));if(miss.length)add(list,issue(S.CHECK,'Формула / период',sheet,e.addr,`=${e.cell.f}`,`Сводная формула периода использует не все месячные итоги активных дней листа «${target}».`,`Найдены ссылки ${ref.filter(a=>addresses.includes(a)).join(', ')}, но отсутствуют ${miss.join(', ')}. После добавления нового месяца свод мог остаться на старой логике.`,`Зафиксируйте методику показателя и включите все нужные месяцы либо поясните исключение.`,`${target}: ${addresses.join(', ')}`));}if(/(?:^|[+\-*/(])\s*\d{2,3}(?:\s*[+\-*/)]|$)/.test(e.cell.f))add(list,issue(S.CHECK,'Формула / период',sheet,e.addr,`=${e.cell.f}`,'В формуле периода есть крупная константа, введённая вручную.','При изменении флайтов такая константа не обновится автоматически.','Проверьте источник константы и по возможности замените ссылкой на расчётную ячейку.'));}}}

  function addAudienceConsistency(workbook,list){const sheets=[];for(const sheet of workbook.SheetNames||[]){if(!/флайт|flight/i.test(sheet))continue;const ws=workbook.Sheets[sheet];let aud=null;for(const e of entries(ws)){if(e.pos.r>10)continue;const m=core.getCellText(e.cell).match(/(?:м\s*\/\s*ж|ж\s*\/\s*м|ж|м)\s*\d{1,2}\s*[-–—]\s*\d{1,2}/iu);if(m){aud={value:m[0],addr:e.addr};break;}}if(aud)sheets.push({sheet,aud});}if(sheets.length<2)return;const cnt=new Map();for(const s of sheets){const k=core.normalizeText(s.aud.value).replace(/\s/g,'');cnt.set(k,(cnt.get(k)||0)+1);}let dom=null,n=0;for(const [k,v] of cnt)if(v>n){dom=k;n=v;}if(n<2)return;const sample=sheets.find(s=>core.normalizeText(s.aud.value).replace(/\s/g,'')===dom);for(const s of sheets)if(core.normalizeText(s.aud.value).replace(/\s/g,'')!==dom)add(list,issue(S.CHECK,'ЦА / логика',s.sheet,s.aud.addr,s.aud.value,`ЦА в шапке этого флайта отличается от большинства других флайтов: «${s.aud.value}» против «${sample.aud.value}».`,`Это может быть согласованное отличие, но охватные KPI становятся несопоставимы, если оно случайное.`,`Сверьте с последним брифом/карточкой бренда и universe.`,`${sample.sheet}!${sample.aud.addr}`));}

  function addComments(workbook,list){for(const sheet of workbook.SheetNames||[]){const ws=workbook.Sheets[sheet],hits=[];for(const e of entries(ws)){const cs=Array.isArray(e.cell.c)?e.cell.c:[];for(const c of cs){const t=String(c.t||c.text||'');if(/\bаудит\b|\baudit\b|внутренн|риск переносимости/iu.test(t))hits.push(e.addr);}}if(hits.length)add(list,issue(S.CHECK,'Служебные комментарии',sheet,summarize(hits),'',`В файле найдены внутренние audit-комментарии: ${hits.length}.`,`Служебные комментарии не должны попадать в клиентскую версию.`,`Удалите внутренние комментарии после финальной проверки.`,hits.join(', ')));}}

  function addWorkbookHygiene(workbook,options,list){
    for(let i=list.length-1;i>=0;i--)if(['Именованные диапазоны','Внешние связи книги'].includes(list[i].type))list.splice(i,1);
    const raw=options&&options.rawInfo||{}, wbNames=workbook.Workbook&&Array.isArray(workbook.Workbook.Names)?workbook.Workbook.Names:[], merged=[],seen=new Set();
    for(const n of (Array.isArray(raw.definedNames)?raw.definedNames:[]).concat(wbNames)){const name=n&&(n.name||n.Name)||'',ref=n&&(n.ref||n.Ref)||'';if(!ERROR_TOKENS.some(t=>String(ref).toUpperCase().includes(t)))continue;const k=`${name}|${ref}`;if(!seen.has(k)){seen.add(k);merged.push({name,ref});}}
    if(merged.length){const counts={};for(const t of ERROR_TOKENS)counts[t]=0;for(const n of merged)for(const t of ERROR_TOKENS)if(String(n.ref).toUpperCase().includes(t))counts[t]++;const details=Object.entries(counts).filter(([,v])=>v).map(([k,v])=>`${k}: ${v}`).join('; '),total=Math.max(Number(raw.definedNamesTotal||0),wbNames.length||0);add(list,issue(S.CHECK,'Именованные диапазоны','Книга','Defined Names','',`Обнаружено ${merged.length} битых именованных диапазонов${total?` из ${total}`:''}.`,'Большое количество битых имён засоряет шаблон, но само по себе не доказывает ошибку видимых расчётов.','Проверьте Диспетчер имён Excel; удаляйте только неиспользуемые имена после резервной копии.',details));}
    if(Array.isArray(raw.externalLinks)&&raw.externalLinks.length){const map=new Map();for(const v of raw.externalLinks){const s=String(v||'').trim();if(!s)continue;let k=s.replace(/\\/g,'/').replace(/%20/gi,' ').split('#')[0].split('?')[0];const m=k.match(/([^/]+\.(?:xlsx?|xlsm|xlsb))$/i);if(m)k=m[1].toLowerCase();if(!map.has(k))map.set(k,s);}const u=[...map.values()];add(list,issue(S.CHECK,'Внешние связи книги','Книга',u.length===1?'externalLink1.xml':'Внешние связи',u.join('; '),`В структуре .xlsx найдено внешних книг/связей: ${u.length}.`,'Внешняя связь может быть намеренной, но также может тянуть чужой клиентский контекст.','Проверьте, относится ли внешняя книга к текущему медиаплану; удалите случайные связи.'));}
  }

  function enhanceIntro(result,workbook,options,list){const intro=String(options&&options.intro||'').trim();if(!intro)return result.introResults||[];const existing=(result.introResults||[]).slice();const sentences=intro.split(/\n+|(?<=[.!?;])\s+/).map(x=>x.trim()).filter(Boolean);for(const s of sentences){if(!/(почему|аргумент|обоснов|объясн)/iu.test(s))continue;const already=existing.find(x=>x.sentence===s&&x.status!=='Требует проверки');if(already)continue;let cand=null;for(const sheet of workbook.SheetNames||[])for(const e of entries(workbook.Sheets[sheet])){const raw=rawString(e.cell);if(raw&&raw.length>100&&/(интенсив|рекламн.*шум|декабр|растяг|порог)/iu.test(raw)){cand={sheet,addr:e.addr};break;}if(cand)break;}const status=cand?'Требует проверки':'Не найдено',detail=cand?`Найден потенциально связанный текст: ${cand.sheet}!${cand.addr}. Нужна ручная оценка, закрывает ли он запрос на аргументацию.`:'Во вводных запрошено объяснение/аргументация, но похожий развернутый текст в книге не найден.';const idx=existing.findIndex(x=>x.sentence===s);if(idx>=0)existing[idx]={sentence:s,status,detail};else existing.push({sentence:s,status,detail});add(list,issue(S.CHECK,'Сопроводительные вводные',cand?cand.sheet:'Книга',cand?cand.addr:'',s,detail,'Приложение не должно придумывать стратегический аргумент, но должно отметить незакрытый запрос клиента.','Проверьте сопроводительный комментарий клиенту.'));}return existing;}

  function compressTemplateText(issues){const groups=new Map(),consumed=new Set(),out=[];for(const x of issues){if(x.severity!==S.TEXT||!['Пробелы','Пунктуация'].includes(x.type)||!x.sheet||!x.cell)continue;const k=[x.type,x.sheet,x.problem,x.value].join('|');if(!groups.has(k))groups.set(k,[]);groups.get(k).push(x);}for(const arr of groups.values()){if(arr.length<4)continue;const cells=arr.map(x=>x.cell);out.push({...arr[0],cell:summarize(cells),problem:`${arr[0].problem} Повторяется в ${arr.length} однотипных ячейках.`,related:cells.join(', ')});arr.forEach(x=>consumed.add(x));}for(const x of issues)if(!consumed.has(x))out.push(x);return out;}

  function sortAndCounts(issues){const w={[S.CRITICAL]:0,[S.CHECK]:1,[S.TEXT]:2};issues.sort((a,b)=>(w[a.severity]-w[b.severity])||String(a.sheet).localeCompare(String(b.sheet),'ru')||String(a.cell).localeCompare(String(b.cell),'ru'));return{critical:issues.filter(x=>x.severity===S.CRITICAL).length,check:issues.filter(x=>x.severity===S.CHECK).length,text:issues.filter(x=>x.severity===S.TEXT).length};}

  core.runAllChecks=function(workbook,options){
    options=options||{};
    const base=originalRun(workbook,options);
    let list=filterNoise(base.issues||[],workbook);
    list=normalizeFormulaErrors(list,workbook);
    list=groupFormulaRanges(list);
    addTextPrecision(workbook,list);
    addFormulaCompatibility(workbook,list);
    addPairedHardcodes(workbook,list);
    addCalendar(workbook,list);
    addAudienceConsistency(workbook,list);
    addComments(workbook,list);
    addWorkbookHygiene(workbook,options,list);
    const introResults=enhanceIntro(base,workbook,options,list);
    list=compressTemplateText(list);
    const seen=new Set();list=list.filter(x=>{const k=keyIssue(x);if(seen.has(k))return false;seen.add(k);return true;});
    const counts=sortAndCounts(list);
    return {...base,issues:list,introResults,counts,status:counts.critical||counts.check||counts.text?'Нужно исправить':'Можно отправлять клиенту'};
  };
  core.__precisionPatched=true;
  return core;
});
