(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./stability-rules.js'));
  else if (root && root.MPChecks) root.MPChecks = factory(root.MPChecks);
})(typeof globalThis !== 'undefined' ? globalThis : this, function (core) {
  'use strict';
  if (!core || core.__hardeningRulesPatched) return core;

  const originalRun = core.runAllChecks.bind(core);
  const S = core.SEVERITY;

  // Небольшой product-safe registry взят из соседнего Reach Engine. Он нужен только
  // для внутренней нормализации/группировки. Разные продукты одного владельца
  // (например, Яндекс Директ / РСЯ / ПромоСтраницы / Видео) намеренно НЕ объединяются.
  const PLATFORM_ALIASES = {
    'VK':['VK','ВК','VKontakte','ВКонтакте','VK Video','VK Видео','ВК Видео'],
    'Telegram':['Telegram','Телеграм','Telegram Ads','TG','ТГ'],
    'МТС':['MTS','МТС'],
    'Media Today':['Media Today','MediaToday','Mediatoday'],
    'AstraLab':['AstraLab','Astra Lab'],
    'Yabbi':['Yabbi'],
    'Otclick':['Otclick'],
    'Mobidriven':['Mobidriven'],
    'Beeline':['Beeline','Билайн'],
    'Avito':['Avito','Авито'],
    'First Data':['First Data','FirstData'],
    'SlickJump':['SlickJump','Slick Jump'],
    'Яндекс ПромоСтраницы':['ПромоСтраницы','Промо Страницы','Яндекс ПромоСтраницы','Яндекс Промо Страницы','PromoPages','Promo Pages','Yandex PromoPages','Yandex Promo Pages'],
    'Дзен':['Дзен','Яндекс Дзен','Dzen','Yandex Dzen','Zen','Yandex Zen'],
    'Яндекс Директ':['Yandex.Direct','Yandex Direct','Яндекс.Директ','Яндекс Директ','Yandex Search','Яндекс Поиск'],
    'Яндекс РСЯ':['Yandex.RSYA','Yandex RSYA','Яндекс.РСЯ','Яндекс РСЯ','РСЯ','RSYA'],
    'Яндекс Видео':['Яндекс Видео','Yandex Video'],
    'Digital Alliance VideoNet':['Digital Alliance VideoNet','VideoNet','DA VideoNet'],
    'Digital Alliance':['Digital Alliance'],
    'Adspector':['Adspector'],
    'Solta':['Solta'],
    'Soloway':['Soloway'],
    'Hybrid':['Hybrid'],
    'Rutube':['Rutube','RuTube'],
    'Buzzoola':['Buzzoola'],
    'GPM':['GPM'],
    'RedLlama':['RedLlama','Red Llama'],
    'Adspend':['Adspend'],
    'BYYD':['BYYD'],
    'Mom.Life':['Mom.Life','Mom Life'],
    'Baby.ru':['Baby.ru','Baby ru'],
    'Babyblog.ru':['Babyblog.ru','Babyblog ru'],
    'Genius':['Genius'],
    'Between Exchange':['Between Exchange'],
    'Plazkart':['Plazkart'],
    'Adriver':['Adriver','Ad River']
  };

  const CYR_TO_LAT = {
    а:'a',б:'b',в:'v',г:'g',д:'d',е:'e',ё:'e',ж:'zh',з:'z',и:'i',й:'i',к:'k',л:'l',м:'m',н:'n',о:'o',п:'p',р:'r',с:'s',т:'t',у:'u',ф:'f',х:'kh',ц:'ts',ч:'ch',ш:'sh',щ:'shch',ы:'y',э:'e',ю:'yu',я:'ya',ь:'',ъ:''
  };

  function norm(v) {
    return String(v == null ? '' : v).replace(/\u00a0/g,' ').replace(/[–—−]/g,'-').replace(/\s+/g,' ').trim().toLowerCase().replace(/ё/g,'е');
  }
  function rawText(cell) {
    if (!cell) return '';
    if (typeof cell.v === 'string') return cell.v;
    if (cell.t === 's' && cell.v != null) return String(cell.v);
    return '';
  }
  function entries(ws) {
    return Object.keys(ws || {}).filter(k=>/^[A-Z]{1,3}\d+$/i.test(k)).map(addr=>({addr:addr.toUpperCase(),pos:core.decodeCell(addr),cell:ws[addr]})).filter(x=>x.pos&&x.cell&&(x.cell.v!=null||x.cell.f||x.cell.c));
  }
  function issue(severity,type,sheet,cell,value,problem,why,recommendation,related) {
    return {severity,type,sheet:sheet||'',cell:cell||'',value:value==null?'':String(value),problem:problem||'',why:why||'',recommendation:recommendation||'Проверьте вручную.',related:related||'',fixStatus:''};
  }
  function issueKey(x) { return [x.severity,x.type,x.sheet,x.cell,x.problem,x.related].join('|'); }
  function add(list,x) { if (!list.some(y=>issueKey(y)===issueKey(x))) list.push(x); }
  function colName(c) { return core.encodeCell(0,c).replace(/\d+$/,''); }
  function cellAt(ws,r1,c0) { return ws && ws[core.encodeCell(r1-1,c0)]; }
  function textAt(ws,r1,c0) { return rawText(cellAt(ws,r1,c0)); }

  function platformSignature(v) {
    let s=norm(v);
    let out='';
    for (const ch of s) out += CYR_TO_LAT[ch] != null ? CYR_TO_LAT[ch] : ch;
    return out.replace(/[^a-z0-9]+/g,'');
  }
  const PLATFORM_INDEX = (()=>{
    const m=new Map();
    for (const [canonical,aliases] of Object.entries(PLATFORM_ALIASES)) {
      for (const alias of aliases) {
        const sig=platformSignature(alias);
        if (sig && !m.has(sig)) m.set(sig,canonical);
      }
    }
    return m;
  })();
  function canonicalPlatform(v) {
    const sig=platformSignature(v);
    return PLATFORM_INDEX.get(sig) || String(v||'').trim();
  }

  function strictDateCell(cell) {
    if (!cell) return false;
    if (cell.t==='d' || cell.v instanceof Date) return true;
    const shown=String(cell.w != null ? cell.w : (typeof cell.v==='string'?cell.v:''));
    const fmt=String(cell.z||'').toLowerCase();
    const full=/^(?:\d{1,2}[.\/-]\d{1,2}[.\/-](?:\d{2}|\d{4})|\d{4}[.\/-]\d{1,2}[.\/-]\d{1,2})$/.test(shown.trim());
    const dateFmt=/d/.test(fmt) && /m/.test(fmt);
    return full || (typeof cell.v==='number' && dateFmt);
  }
  function dateContext(ws,pos) {
    const parts=[];
    for (let r=Math.max(0,pos.r-1);r<=pos.r+1;r++) {
      for (let c=Math.max(0,pos.c-5);c<=pos.c-1;c++) {
        const t=rawText(ws[core.encodeCell(r,c)]); if(t) parts.push(t);
      }
    }
    return norm(parts.join(' '));
  }
  function filterFalseSummaryDates(workbook, issues) {
    return issues.filter(x=>{
      if (x.type!=='Свод / устойчивость ссылки' || !x.sheet || !x.cell) return true;
      const ws=workbook.Sheets&&workbook.Sheets[x.sheet];
      const c=ws&&ws[x.cell];
      const pos=core.decodeCell(x.cell);
      if (!ws||!c||!pos||!strictDateCell(c)) return false;
      const ctx=dateContext(ws,pos);
      return /(дата\s+(?:начала|окончания)|начал\w*\s+кампан|оконч\w*\s+кампан|период\s+кампан|campaign\s+(?:start|end)|start\s+date|end\s+date)/iu.test(ctx);
    });
  }

  function extractIssueCells(x) {
    return (String(x.cell||'').match(/[A-Z]{1,3}\d+/g)||[]).map(s=>s.toUpperCase());
  }
  function suppressSecondaryBrokenFormulaNoise(issues) {
    const broken=new Map();
    for (const x of issues) {
      if (!/(формула excel|ошибка excel)/iu.test(String(x.type||''))) continue;
      if (!/(#REF!|бит\w* ссыл|ошибк)/iu.test(`${x.problem||''} ${x.value||''}`)) continue;
      if (!broken.has(x.sheet)) broken.set(x.sheet,new Set());
      extractIssueCells(x).forEach(c=>broken.get(x.sheet).add(c));
    }
    return issues.filter(x=>{
      const set=broken.get(x.sheet); if(!set||!set.size) return true;
      const cells=extractIssueCells(x); if(!cells.some(c=>set.has(c))) return true;
      if (/(структур\w* формул|формул\w* паттерн|ручн\w* значен\w* среди формул)/iu.test(`${x.type||''} ${x.problem||''}`)) return false;
      return true;
    });
  }

  function dateParts(cell) {
    if (!cell) return null;
    if (cell.v instanceof Date) return {y:cell.v.getUTCFullYear(),m:cell.v.getUTCMonth()+1,d:cell.v.getUTCDate()};
    if (cell.t==='d' && cell.v) {
      const d=new Date(cell.v); if(!Number.isNaN(d.getTime())) return {y:d.getUTCFullYear(),m:d.getUTCMonth()+1,d:d.getUTCDate()};
    }
    const shown=String(cell.w != null ? cell.w : (typeof cell.v==='string'?cell.v:''));
    const ts=core.extractDateTokensFromText(shown);
    if (!ts.length) return null;
    return {y:ts[0].year||null,m:ts[0].month,d:ts[0].day};
  }
  function inclusiveDays(a,b) {
    if(!a||!b) return null;
    let y1=a.y||2000, y2=b.y||y1;
    if (!b.y && (b.m<a.m || (b.m===a.m&&b.d<a.d))) y2=y1+1;
    const d1=Date.UTC(y1,a.m-1,a.d), d2=Date.UTC(y2,b.m-1,b.d);
    const n=Math.round((d2-d1)/86400000)+1;
    return n>=1&&n<=31?n:null;
  }
  function addWeeklyCalendarChecks(workbook, issues) {
    for (const sheet of workbook.SheetNames||[]) {
      const ws=workbook.Sheets[sheet]; if(!ws) continue;
      const list=entries(ws); if(!list.length) continue;
      const maxC=Math.min(220,Math.max(...list.map(e=>e.pos.c)));
      for (let c=0;c<=maxC;c++) {
        for (let r=5;r<=35;r++) {
          const a=dateParts(cellAt(ws,r,c)), b=dateParts(cellAt(ws,r+1,c));
          const allowed=inclusiveDays(a,b);
          if (!allowed || allowed>7) continue;
          const offenders=[];
          for (let rr=r+2;rr<=Math.min(r+170,260);rr++) {
            const cell=cellAt(ws,rr,c);
            if (!cell || typeof cell.v!=='number' || !Number.isFinite(cell.v)) continue;
            const v=Number(cell.v);
            if (!Number.isInteger(v) || v<0 || v>7 || v<=allowed) continue;
            offenders.push(`${colName(c)}${rr}`);
          }
          if (!offenders.length) continue;
          const aRaw=String((cellAt(ws,r,c)||{}).w || (cellAt(ws,r,c)||{}).v || '');
          const bRaw=String((cellAt(ws,r+1,c)||{}).w || (cellAt(ws,r+1,c)||{}).v || '');
          add(issues,issue(S.CRITICAL,'Календарь / активные дни',sheet,offenders.join(', '),`${aRaw} — ${bRaw}`,
            `В интервале ${aRaw}–${bRaw} максимум ${allowed} календарных дней, но в строках размещения указано больше.`,
            'Количество активных дней математически не может превышать длину недельного/частичного интервала.',
            `Исправьте активные дни: для этого интервала допустимо не более ${allowed}.`,`${colName(c)}${r}:${colName(c)}${r+1}`));
        }
      }
    }
  }

  function findHeaderRow(ws) {
    const rows=new Map();
    for (const e of entries(ws)) {
      if (e.pos.r>39) continue;
      const t=norm(rawText(e.cell)); if(!t) continue;
      if(!rows.has(e.pos.r)) rows.set(e.pos.r,[]);
      rows.get(e.pos.r).push({c:e.pos.c,t,addr:e.addr});
    }
    let best=null;
    for (const [r,cells] of rows) {
      const site=cells.find(x=>/^(site|площадка)$/iu.test(x.t));
      const month=cells.find(x=>/^(month|месяц)$/iu.test(x.t));
      if(site&&month){best={row:r+1,cells,site:site.c,month:month.c};break;}
    }
    return best;
  }
  function headerCol(h,re) { const x=h&&h.cells.find(v=>re.test(v.t)); return x?x.c:null; }
  function pairGroups(ws,h) {
    const fmt=headerCol(h,/^(format|формат)$/iu), target=headerCol(h,/(target|таргет|аудитор)/iu), unit=headerCol(h,/(unit type|buying unit|единиц)/iu);
    const groups=new Map();
    for (let r=h.row+1;r<=h.row+150;r++) {
      const platform=rawText(cellAt(ws,r,h.site)).trim();
      const month=rawText(cellAt(ws,r,h.month)).trim();
      if(!platform||!month) continue;
      const key=[canonicalPlatform(platform),fmt!=null?norm(rawText(cellAt(ws,r,fmt))):'',target!=null?norm(rawText(cellAt(ws,r,target))):'',unit!=null?norm(rawText(cellAt(ws,r,unit))):''].join('|');
      if(!groups.has(key)) groups.set(key,[]);
      groups.get(key).push({r,platform,month});
    }
    return [...groups.values()].filter(g=>new Set(g.map(x=>norm(x.month))).size>=2);
  }
  function columnHeader(ws,h,c) {
    for (let r=h.row;r>=Math.max(1,h.row-2);r--) {
      const t=rawText(cellAt(ws,r,c)); if(t) return norm(t);
    }
    return '';
  }
  function excludedInputHeader(t) {
    return /(site|площадк|target|таргет|audien|аудитор|format|формат|month|месяц|unit type|buying unit|buying model|cpm|ставк|rate|budget|бюджет|media net|reach\s*\(people\)|technical reach|unique users|охват\s*\(people\)|цена|стоимость)/iu.test(t);
  }
  function addPairedFormulaValueChecks(workbook, issues) {
    for (const sheet of workbook.SheetNames||[]) {
      const ws=workbook.Sheets[sheet]; if(!ws) continue;
      const h=findHeaderRow(ws); if(!h) continue;
      const groups=pairGroups(ws,h); if(!groups.length) continue;
      for (const g of groups) {
        const mismatches=[];
        const maxC=Math.min(h.site+40,55);
        for (let c=0;c<=maxC;c++) {
          if (c===h.site||c===h.month) continue;
          const ht=columnHeader(ws,h,c); if(excludedInputHeader(ht)) continue;
          const vals=g.map(x=>({r:x.r,cell:cellAt(ws,x.r,c)})).filter(x=>x.cell&&x.cell.v!=null);
          if(vals.length<2) continue;
          const hasFormula=vals.some(x=>!!x.cell.f);
          const constants=vals.filter(x=>!x.cell.f&&typeof x.cell.v==='number'&&Number.isFinite(x.cell.v));
          if(!hasFormula||!constants.length) continue;
          constants.forEach(x=>mismatches.push(`${colName(c)}${x.r}`));
        }
        if(!mismatches.length) continue;
        const platform=canonicalPlatform(g[0].platform);
        add(issues,issue(S.CHECK,'Парные строки / формулы',sheet,mismatches.slice(0,25).join(', '),g.map(x=>`${x.platform} — ${x.month}`).join(' | '),
          `В парных месячных строках «${platform}» часть расчётных полей считается формулами, а часть введена числами вручную.`,
          'Для одной площадки/формата с одинаковой логикой месяца обычно должны использовать одинаковый способ расчёта. Ручные значения могут не обновиться после изменения бюджета или объёма.',
          'Проверьте перечисленные ячейки. Если ручной override не предусмотрен методологией, восстановите формулы по парной строке.',g.map(x=>`строка ${x.r}`).join(', ')));
      }
    }
  }

  function formulaRefs(formula) {
    const out=[]; const re=/(?:'((?:[^']|'')+)'|([A-Za-zА-Яа-яЁё0-9_ .-]+))!\$?[A-Z]{1,3}\$?(\d+)/g; let m;
    while((m=re.exec(String(formula||'')))) out.push({sheet:(m[1]||m[2]||'').replace(/''/g,"'").trim(),row:Number(m[3])});
    return out;
  }
  function placementMonths(ws,h) {
    const s=new Set();
    for(let r=h.row+1;r<=h.row+150;r++) {
      const p=rawText(cellAt(ws,r,h.site)); const m=rawText(cellAt(ws,r,h.month));
      if(p&&m) s.add(norm(m));
    }
    return s;
  }
  function referencedMonths(ws,h,rows) {
    const s=new Set(); rows.forEach(r=>{const m=rawText(cellAt(ws,r,h.month)); if(m)s.add(norm(m));}); return s;
  }
  function addSummaryDurationCoverage(workbook,issues) {
    for(const sheet of workbook.SheetNames||[]) {
      if(!/(свод|summary)/iu.test(sheet)) continue;
      const ws=workbook.Sheets[sheet]; if(!ws) continue;
      for(const e of entries(ws)) {
        if(!e.cell.f) continue;
        const ctx=dateContext(ws,e.pos);
        if(!/(период\s+кампан.*дн|campaign.*days|длительн\w*\s+кампан)/iu.test(ctx)) continue;
        const refs=formulaRefs(e.cell.f); if(!refs.length) continue;
        const bySheet=new Map(); refs.forEach(r=>{if(!bySheet.has(r.sheet))bySheet.set(r.sheet,[]);bySheet.get(r.sheet).push(r.row);});
        for(const [target,rows] of bySheet) {
          const tws=workbook.Sheets[target]; if(!tws||!/(флайт|flight)/iu.test(target)) continue;
          const h=findHeaderRow(tws); if(!h) continue;
          const all=placementMonths(tws,h); const used=referencedMonths(tws,h,rows);
          const missing=[...all].filter(m=>!used.has(m));
          if(!missing.length) continue;
          add(issues,issue(S.CHECK,'Свод / период кампании',sheet,e.addr,String(e.cell.f),
            `Формула периода кампании не использует месяц(ы) ${missing.join(', ')} листа «${target}».`,
            'Проверка сравнивает уникальные месяцы размещения, а не все строки площадок, поэтому параллельные площадки одного месяца не суммируются повторно.',
            'Проверьте, должен ли отсутствующий месяц входить в общий период кампании. Если да — добавьте в формулу устойчивую итоговую ссылку на этот месяц.',target));
        }
      }
    }
  }

  function commentText(c) { return String((c&&((c.t!=null&&c.t)||(c.text!=null&&c.text)))||'').trim(); }
  function addWorkbookComments(workbook,issues) {
    for(const sheet of workbook.SheetNames||[]) {
      const ws=workbook.Sheets[sheet]; if(!ws) continue;
      const hits=[];
      for(const e of entries(ws)) {
        const comments=Array.isArray(e.cell.c)?e.cell.c:[];
        for(const c of comments) hits.push({cell:e.addr,text:commentText(c),author:String(c&&c.a||'')});
      }
      if(!hits.length) continue;
      const suspicious=hits.filter(h=>/(аудит|audit|провер|risk|риск|todo|исправ|ошиб)/iu.test(h.text));
      const sample=(suspicious.length?suspicious:hits).slice(0,5).map(h=>`${h.cell}${h.text?`: ${h.text.slice(0,120)}`:''}`).join(' | ');
      add(issues,issue(S.CHECK,'Комментарии Excel',sheet,[...new Set(hits.map(h=>h.cell))].slice(0,20).join(', '),sample,
        `В книге остались комментарии Excel: ${hits.length}${suspicious.length?`; служебных/аудиторских по тексту — ${suspicious.length}`:''}.`,
        'Внутренние комментарии и служебные заметки могут случайно уйти клиенту вместе с медиапланом.',
        'Перед отправкой клиенту просмотрите комментарии и удалите внутренние заметки. Клиентские комментарии оставляйте только осознанно.'));
    }
  }

  function addXlfnInfo(workbook,issues) {
    for(const sheet of workbook.SheetNames||[]) {
      const ws=workbook.Sheets[sheet]; if(!ws) continue;
      const hits=entries(ws).filter(e=>e.cell.f&&/_xlfn\./i.test(String(e.cell.f)));
      if(!hits.length) continue;
      add(issues,issue(S.TEXT,'Техническая совместимость',sheet,hits.slice(0,30).map(h=>h.addr).join(', '),`${hits.length} формул`,
        `Найдено ${hits.length} формул с префиксом _xlfn.`,
        'Это не ошибка в современном Excel, но функция может не поддерживаться в старых версиях Excel или сторонних движках.',
        'Информационно: если файл будет открываться не в актуальном Excel, проверьте совместимость функций.'));
    }
  }

  function extractDomains(v) {
    const out=[]; const re=/(?:https?:\/\/)?(?:www\.)?([a-z0-9а-яё-]+(?:\.[a-z0-9а-яё-]+)+)/giu; let m;
    while((m=re.exec(String(v||'')))) { const h=String(m[1]||'').toLowerCase().replace(/[),.;]+$/,''); if(h&&!out.includes(h))out.push(h); }
    return out;
  }
  function suspiciousDomain(h) {
    return /(lordfilms?|lordserial|hdrezka|rezka|kinogo|kinokrad|filmix|dorama|doramy|serial|mnogoserial|pobegserial|doctor-serial|office-serial|rosserial|serialfriends|kinobar|gidonline|film[-.]?online|kino[-.]?online|big-bang-theory|chernaya-lyubov|garri-potter|harry-potter|sherlock-online)/iu.test(h);
  }
  function rebuildBrandSafety(workbook,issues) {
    issues=issues.filter(x=>x.type!=='Brand Safety / домены');
    for(const sheet of workbook.SheetNames||[]) {
      const ws=workbook.Sheets[sheet]; if(!ws) continue;
      const hits=[];
      for(const e of entries(ws)) {
        const raw=rawText(e.cell); if(!raw) continue;
        for(const host of extractDomains(raw)) if(suspiciousDomain(host)) hits.push({cell:e.addr,host});
      }
      if(!hits.length) continue;
      const hosts=[...new Set(hits.map(h=>h.host))], cells=[...new Set(hits.map(h=>h.cell))];
      add(issues,issue(S.CHECK,'Brand Safety / домены',sheet,cells.length<=15?cells.join(', '):`${cells.slice(0,15).join(', ')} +${cells.length-15}`,hosts.slice(0,30).join(', '),
        `В инвентаре найдены потенциально спорные кино/сериальные домены: ${hosts.slice(0,12).join(', ')}${hosts.length>12?' …':''}.`,
        'По одному домену нельзя доказать нарушение brand safety, но такие источники требуют ручной сверки с актуальными правилами клиента/площадки.',
        'Проверьте домены по whitelist/blacklist и условиям площадки. Подтверждённо допустимые домены не нужно исключать автоматически.',canonicalPlatform(sheet)));
    }
    return issues;
  }

  function normalizedListItem(v) {
    return norm(String(v||'').replace(/^\s*[•·]\s*/u,'').replace(/^\s*-\s+(?=[A-Za-zА-Яа-яЁё])/u,''));
  }
  function splitList(raw) {
    const s=String(raw||'');
    let parts=s.split(/[;\n\r]+/);
    if(parts.length<2 && /[A-Za-zА-Яа-яЁё]/u.test(s) && s.includes(',')) parts=s.split(/,(?=\s*[A-Za-zА-Яа-яЁё«"'\[])/u);
    return parts.map(normalizedListItem).filter(x=>x.length>=2);
  }
  function rebuildKeywordDuplicates(workbook,issues) {
    issues=issues.filter(x=>{
      if(x.type!=='Дубли таргетинга/ключевых слов'||!x.sheet||!x.cell)return true;
      const ws=workbook.Sheets&&workbook.Sheets[x.sheet]; const c=ws&&ws[x.cell];
      if(!c||typeof c.v!=='string') return false;
      if(/^[\d\s,.'’+\-/%₽]+$/u.test(c.v)) return false;
      return false; // ниже пересобираем единым более консервативным правилом
    });
    for(const sheet of workbook.SheetNames||[]) {
      const ws=workbook.Sheets[sheet]; if(!ws) continue;
      for(const e of entries(ws)) {
        const raw=rawText(e.cell); if(!raw||raw.length<5) continue;
        const items=splitList(raw); if(items.length<2) continue;
        const seen=new Set(),dupes=[];
        for(const x of items){if(seen.has(x)&&!dupes.includes(x))dupes.push(x);else seen.add(x);}
        if(!dupes.length) continue;
        add(issues,issue(S.TEXT,'Дубли таргетинга/ключевых слов',sheet,e.addr,raw,
          `В списке повторяются элементы после нормализации регистра/пробелов: ${dupes.slice(0,6).join(', ')}.`,
          'Повтор одинакового ключевого слова или таргетинга обычно не добавляет охват и может быть случайным дублем.',
          'Проверьте список. Удаляйте только действительно одинаковые элементы; операторы соответствия и разные формулировки сохраняйте.'));
      }
    }
    return issues;
  }

  const TEXT_RULES=[
    [/\bстредств\b/iu,'Опечатка','«стредств» — вероятная опечатка.','Исправьте на «средств».'],
    [/\bcost\s+per\s+unt\b/iu,'Опечатка','«Cost per unt» — опечатка в английском заголовке.','Исправьте на «Cost per unit».'],
    [/\bвидео\s+ролик(?:а|ов|и|ом|у)?\b/iu,'Орфография / оформление','Сочетание «видео ролик» написано раздельно.','Исправьте на «видеоролик» в соответствующей форме.'],
    [/\bоффлайн\s+(покуп\w*|продаж\w*|канал\w*|магазин\w*)/iu,'Орфография / оформление','Найдено написание «оффлайн …».','В клиентском тексте используйте «офлайн-…» или «офлайн …» по смыслу; проверьте формулировку.'],
    [/\bс\s+таргетировани(?:е|ем)\b/iu,'Грамматика','Конструкция «с таргетирование» грамматически неверна.','Исправьте на «с таргетированием» или «с таргетингом».']
  ];
  const TAUTOLOGY_RULES=[
    [/во\s+вложени(?:и|я)\s+(?:также\s+)?прикладыва/iu,'«во вложении прикладываем»'],
    [/по\s+ключевым\s+словам\s+по\s+тем/iu,'«по ключевым словам по теме»'],
    [/размещен\w*(?:\s+\S+){0,8}\s+размещен\w*/iu,'повтор слова/корня «размещ…» в коротком фрагменте']
  ];
  function addTextHardening(workbook,issues) {
    for(const sheet of workbook.SheetNames||[]) {
      const ws=workbook.Sheets[sheet]; if(!ws) continue;
      for(const e of entries(ws)) {
        const raw=rawText(e.cell); if(!raw) continue;
        for(const [re,type,problem,reco] of TEXT_RULES) if(re.test(raw)) add(issues,issue(S.TEXT,type,sheet,e.addr,raw,problem,'Это заметная опечатка/грамматическая проблема в клиентском тексте.',reco));
        for(const [re,label] of TAUTOLOGY_RULES) if(re.test(raw)) add(issues,issue(S.TEXT,'Возможная тавтология',sheet,e.addr,raw,`В тексте обнаружена тяжёлая или повторяющаяся конструкция: ${label}.`,'Формулировка может выглядеть тавтологично или канцелярски тяжело.','Переформулируйте фразу короче, сохранив исходный смысл.'));
      }
    }
  }

  function groupAudienceIssues(issues) {
    const rest=[],groups=new Map();
    for(const x of issues) {
      if(x.type!=='ЦА / логика'){rest.push(x);continue;}
      const m=String(x.problem||'').match(/«([^»]+)»/u); const platform=canonicalPlatform(m?m[1]:'');
      const key=[x.sheet,platform,x.value,x.related].join('|');
      if(!groups.has(key))groups.set(key,[]); groups.get(key).push(x);
    }
    for(const g of groups.values()) {
      if(g.length===1){rest.push(g[0]);continue;}
      const first=g[0], cells=[...new Set(g.flatMap(extractIssueCells))];
      const m=String(first.problem||'').match(/«([^»]+)»/u); const platform=canonicalPlatform(m?m[1]:'площадки');
      rest.push({...first,cell:cells.join(', '),problem:`ЦА нескольких строк «${platform}» отличается от общей ЦА кампании (${g.length} строк).`,related:first.related});
    }
    return rest;
  }

  function removeLegacyPeriodNoise(issues) {
    return issues.filter(x=>!(x.type==='Формула / период'&&/использует не все месячные итоги активных дней/iu.test(String(x.problem||''))));
  }

  function finish(result) {
    const seen=new Set();
    result.issues=(result.issues||[]).filter(x=>{const k=issueKey(x);if(seen.has(k))return false;seen.add(k);return true;});
    const weight={[S.CRITICAL]:0,[S.CHECK]:1,[S.TEXT]:2};
    result.issues.sort((a,b)=>(weight[a.severity]-weight[b.severity])||String(a.sheet).localeCompare(String(b.sheet),'ru')||String(a.cell).localeCompare(String(b.cell),'ru'));
    result.counts={critical:result.issues.filter(x=>x.severity===S.CRITICAL).length,check:result.issues.filter(x=>x.severity===S.CHECK).length,text:result.issues.filter(x=>x.severity===S.TEXT).length};
    result.status=result.issues.length?'Нужно исправить':'Можно отправлять клиенту';
    return result;
  }

  core.runAllChecks=function(workbook,options){
    const result=originalRun(workbook,options||{});
    result.issues=filterFalseSummaryDates(workbook,result.issues||[]);
    result.issues=suppressSecondaryBrokenFormulaNoise(result.issues);
    result.issues=removeLegacyPeriodNoise(result.issues);
    result.issues=rebuildBrandSafety(workbook,result.issues);
    result.issues=rebuildKeywordDuplicates(workbook,result.issues);
    addWeeklyCalendarChecks(workbook,result.issues);
    addPairedFormulaValueChecks(workbook,result.issues);
    addSummaryDurationCoverage(workbook,result.issues);
    addWorkbookComments(workbook,result.issues);
    addXlfnInfo(workbook,result.issues);
    addTextHardening(workbook,result.issues);
    result.issues=groupAudienceIssues(result.issues);
    return finish(result);
  };

  core.canonicalPlatformName=canonicalPlatform;
  core.__hardeningRulesPatched=true;
  return core;
});
