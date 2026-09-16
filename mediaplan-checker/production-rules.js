(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./audit-policy-rules.js'));
  else if (root && root.MPChecks) root.MPChecks = factory(root.MPChecks);
})(typeof globalThis !== 'undefined' ? globalThis : this, function (core) {
  'use strict';
  if (!core || core.__productionRulesPatched) return core;

  const originalRun = core.runAllChecks.bind(core);
  const S = core.SEVERITY;
  const MONTH_RE = /^(?:january|february|march|april|may|june|july|august|september|october|november|december|январь|февраль|март|апрель|май|июнь|июль|август|сентябрь|октябрь|ноябрь|декабрь)$/iu;

  function norm(v) {
    return String(v == null ? '' : v)
      .replace(/\u00a0/g, ' ')
      .replace(/[–—−]/g, '-')
      .replace(/\s+/g, ' ')
      .trim()
      .toLowerCase()
      .replace(/ё/g, 'е');
  }
  function rawText(cell) {
    if (!cell) return '';
    if (typeof cell.v === 'string') return cell.v;
    if (cell.t === 's' && cell.v != null) return String(cell.v);
    if (typeof cell.w === 'string' && cell.w) return cell.w;
    return '';
  }
  function entries(ws) {
    return Object.keys(ws || {})
      .filter(k => /^[A-Z]{1,3}\d+$/i.test(k))
      .map(addr => ({ addr: addr.toUpperCase(), pos: core.decodeCell(addr), cell: ws[addr] }))
      .filter(x => x.pos && x.cell && (x.cell.v != null || x.cell.f || x.cell.c));
  }
  function cellAt(ws, row1, col0) { return ws && ws[core.encodeCell(row1 - 1, col0)]; }
  function colName(c) { return core.encodeCell(0, c).replace(/\d+$/, ''); }
  function issue(severity, type, sheet, cell, value, problem, why, recommendation, related) {
    return { severity, type, sheet: sheet || '', cell: cell || '', value: value == null ? '' : String(value), problem, why, recommendation, related: related || '', fixStatus: '' };
  }
  function key(x) { return [x.severity,x.type,x.sheet,x.cell,x.problem,x.related].join('|'); }
  function add(list, x) { if (!list.some(y => key(y) === key(x))) list.push(x); }

  function issueCell(workbook, x) {
    if (!x || !x.sheet || !x.cell || !workbook.Sheets || !workbook.Sheets[x.sheet]) return null;
    const m = String(x.cell).trim().match(/^([A-Z]{1,3}\d+)$/i);
    return m ? workbook.Sheets[x.sheet][m[1].toUpperCase()] : null;
  }

  function parseSimpleSumRange(formula) {
    const f = String(formula || '').replace(/\s+/g, '');
    const m = /SUM\((?:(?:'((?:[^']|'')+)'|([^!'\[\]]+))!)?(\$?[A-Z]{1,3}\$?\d+):(\$?[A-Z]{1,3}\$?\d+)\)/i.exec(f);
    if (!m) return null;
    return { sheet:(m[1] || m[2] || '').replace(/''/g,"'"), start:m[3].replace(/\$/g,''), end:m[4].replace(/\$/g,'') };
  }
  function cellsInRange(workbook, currentSheet, parsed) {
    if (!parsed) return [];
    const ws = workbook.Sheets && workbook.Sheets[parsed.sheet || currentSheet];
    const a = core.decodeCell(parsed.start), b = core.decodeCell(parsed.end);
    if (!ws || !a || !b) return [];
    const out=[];
    for (let r=Math.min(a.r,b.r); r<=Math.max(a.r,b.r); r++) for (let c=Math.min(a.c,b.c); c<=Math.max(a.c,b.c); c++) out.push(ws[core.encodeCell(r,c)]);
    return out;
  }
  function hasUnreliableSumInputs(workbook, x, cell) {
    if (!cell || cell.t === 'e' || typeof cell.v !== 'number' || !Number.isFinite(cell.v)) return true;
    const parsed = parseSimpleSumRange(cell.f);
    if (!parsed) return false;
    return cellsInRange(workbook, x.sheet, parsed).some(c => c && c.t === 'e');
  }
  function sumRowBounds(formula) {
    const p = parseSimpleSumRange(formula);
    if (!p) return null;
    const a = core.decodeCell(p.start), b = core.decodeCell(p.end);
    return a && b ? [Math.min(a.r,b.r), Math.max(a.r,b.r)] : null;
  }

  function looksLikeUrl(v) { return /^(?:https?|ftp):\/\/\S+$/iu.test(String(v || '').trim()) || /^www\.[^\s]+$/iu.test(String(v || '').trim()); }
  function looksLikeExcelRefText(v) {
    const s = String(v || '').trim();
    return /^(?:'[^']+'|[^!\n]+)!\$?[A-Z]{1,3}\$?\d+(?::\$?[A-Z]{1,3}\$?\d+)?$/iu.test(s);
  }
  function looksIntentionalRepeatedTitle(v) {
    return /:\s*([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё-]*)\s+\1\s*$/iu.test(String(v || '').trim());
  }

  function filterFalsePositives(workbook, options, issues) {
    const rawInfo = options && options.rawInfo;
    return (issues || []).filter(x => {
      const c = issueCell(workbook, x);

      // SheetJS represents cached Excel errors as t='e' and numeric error codes in v.
      // A cached error on a formula is not proof that the formula is wrong now: the book may simply
      // not have been recalculated by the library. Literal error cells without formulas remain errors.
      if (x.type === 'Ошибка Excel' && c && c.f && c.t === 'e') return false;

      // Do not compare error codes (e.g. 29 for #NAME?) with arithmetic SUM results.
      // A SUM mismatch is kept only when the stored result and its inputs are reliable numeric cells.
      if (x.type === 'Проверка суммы' && c && hasUnreliableSumInputs(workbook, x, c)) return false;

      // If workbook.xml contains no Defined Names, no Defined Names warning should be shown merely
      // because error tokens exist elsewhere in formulas/package XML.
      if (x.type === 'Именованные диапазоны' && rawInfo && Number(rawInfo.definedNamesTotal || 0) === 0 && Array.isArray(rawInfo.definedNames) && rawInfo.definedNames.length === 0) return false;

      // A SUM may be followed by a multiplier and still use exactly the same row boundaries as its
      // neighbouring totals. In that case there is no range anomaly.
      if (x.type === 'Диапазон SUM' && c && c.f) {
        const target = sumRowBounds(c.f);
        const refs = String(x.related || '').split(/\s*,\s*/).filter(Boolean);
        const peerBounds = refs.map(ref => {
          const m = ref.match(/^([A-Z]{1,3}\d+)$/i);
          const pc = m && workbook.Sheets[x.sheet] && workbook.Sheets[x.sheet][m[1].toUpperCase()];
          return pc && pc.f ? sumRowBounds(pc.f) : null;
        }).filter(Boolean);
        if (target && peerBounds.length && peerBounds.every(b => b[0] === target[0] && b[1] === target[1])) return false;
      }

      // URLs and pure Excel references are technical strings, not prose.
      if (x.severity === S.TEXT && x.type === 'Пунктуация' && (looksLikeUrl(x.value) || looksLikeExcelRefText(x.value))) return false;

      // Repetition can be part of an official product/title name: "Mobile Legends: Bang Bang".
      if (x.severity === S.TEXT && x.type === 'Повтор слова' && looksIntentionalRepeatedTitle(x.value)) return false;

      return true;
    });
  }

  function findMediaHeader(ws) {
    const rows = new Map();
    for (const e of entries(ws)) {
      if (e.pos.r > 35) continue;
      const t = norm(rawText(e.cell));
      if (!t) continue;
      if (!rows.has(e.pos.r)) rows.set(e.pos.r, []);
      rows.get(e.pos.r).push({ c:e.pos.c, t, addr:e.addr });
    }
    for (const [r,cells] of rows) {
      const site=cells.find(x=>/^(site|площадка)$/iu.test(x.t));
      const month=cells.find(x=>/^(month|месяц)$/iu.test(x.t));
      if (!site || !month) continue;
      const no=cells.find(x=>/^(№|no\.?|#)$/iu.test(x.t));
      return { row:r+1, cells, site:site.c, month:month.c, no:no ? no.c : null };
    }
    return null;
  }
  function headerCol(h,re) { const x=h&&h.cells.find(v=>re.test(v.t)); return x ? x.c : null; }
  function headerText(ws,h,c) {
    const out=[];
    for (let r=h.row; r<=h.row+2; r++) { const t=rawText(cellAt(ws,r,c)); if (t) out.push(t); }
    return norm(out.join(' '));
  }
  function placementRows(ws,h) {
    const out=[];
    const max=entries(ws).reduce((m,e)=>Math.max(m,e.pos.r+1),h.row);
    for (let r=h.row+1;r<=max;r++) {
      const site=rawText(cellAt(ws,r,h.site)).trim(), month=rawText(cellAt(ws,r,h.month)).trim();
      if (site && month && !/^(total|итого|всего)$/iu.test(norm(site))) out.push(r);
    }
    return out;
  }
  function calendarStart(ws,h) {
    const maxC=Math.max(...entries(ws).map(e=>e.pos.c),h.month+1);
    for (let c=h.month+1;c<=Math.min(maxC,220);c++) {
      const parts=[];
      for (let r=h.row;r<=h.row+2;r++) { const t=rawText(cellAt(ws,r,c)).trim(); if (t) parts.push(t); }
      if (parts.some(x=>MONTH_RE.test(norm(x)))) return c;
      const dates=parts.filter(x=>/^\d{1,2}[.\/-]\d{1,2}(?:[.\/-]\d{2,4})?$/u.test(x));
      if (dates.length>=2) return c;
    }
    return null;
  }
  function sectionAt(ws,h,row) {
    if (h.no == null) return '';
    for (let r=row-1;r>h.row;r--) {
      const c=cellAt(ws,r,h.no), raw=rawText(c).trim();
      if (!raw || /^\d+(?:[.,]\d+)?$/u.test(raw)) continue;
      const site=rawText(cellAt(ws,r,h.site)).trim(), month=rawText(cellAt(ws,r,h.month)).trim();
      if (!site && !month && !/^(№|no\.?|#)$/iu.test(raw)) return raw;
    }
    return '';
  }
  function pairPlatform(raw) {
    let s=String(raw||'').split(/\r?\n/)[0].trim();
    s=s.replace(/\b(?:bonus|бонус(?:ом|ный|ная|ное|ные)?|BLS|SL|brand\s*lift(?:\s*study)?)\b/giu,' ').replace(/\s+/g,' ').trim();
    return typeof core.canonicalPlatformName === 'function' ? core.canonicalPlatformName(s) : s;
  }
  function formulaReferencesOwnRow(formula,row) {
    const re=/\$?[A-Z]{1,3}\$?(\d+)/g; let m;
    while ((m=re.exec(String(formula||'')))) if (Number(m[1])===row) return true;
    return false;
  }
  function manualHeader(label) {
    const t=norm(label);
    return /^(units? qty(?: total)?|ratecard(?: \(cost per unit\))?|multipliers?|data cpm|discount(?:,? %)?|frequency|ctr%?|planning vtr.*|vtr%?|adserver|month|месяц)$/iu.test(t);
  }

  function rebuildPairedFormulaChecks(workbook, issues) {
    issues=(issues||[]).filter(x=>x.type!=='Парные строки / формулы');
    for (const sheet of workbook.SheetNames||[]) {
      const ws=workbook.Sheets[sheet]; if(!ws) continue;
      const h=findMediaHeader(ws), cal=h&&calendarStart(ws,h); if(!h||cal==null) continue;
      const fmt=headerCol(h,/(format|формат|ad size.*format)/iu), target=headerCol(h,/(target|таргет|audien|аудитор)/iu), unit=headerCol(h,/(unit type|buying unit|единиц)/iu), video=headerCol(h,/(video details|видео)/iu);
      const groups=new Map();
      for (const r of placementRows(ws,h)) {
        const platformRaw=rawText(cellAt(ws,r,h.site)).trim(), month=rawText(cellAt(ws,r,h.month)).trim();
        const k=[
          norm(sectionAt(ws,h,r)), pairPlatform(platformRaw),
          fmt!=null?norm(rawText(cellAt(ws,r,fmt))):'',
          target!=null?norm(rawText(cellAt(ws,r,target))):'',
          unit!=null?norm(rawText(cellAt(ws,r,unit))):'',
          video!=null?norm(rawText(cellAt(ws,r,video))):''
        ].join('|');
        if(!groups.has(k)) groups.set(k,[]);
        groups.get(k).push({r,month,platform:pairPlatform(platformRaw),platformRaw,section:sectionAt(ws,h,r)});
      }
      for (const g of groups.values()) {
        if(new Set(g.map(x=>norm(x.month))).size<2) continue;
        const bad=[];
        for(let c=h.month+1;c<cal;c++) {
          if(manualHeader(headerText(ws,h,c))) continue;
          const rc=g.map(x=>({r:x.r,cell:cellAt(ws,x.r,c)})).filter(x=>x.cell&&(x.cell.v!=null||x.cell.f));
          if(rc.length<2) continue;
          const formulaRows=rc.filter(x=>x.cell.f&&formulaReferencesOwnRow(x.cell.f,x.r));
          if(!formulaRows.length) continue;
          for(const x of rc) if(!x.cell.f&&x.cell.t!=='e'&&typeof x.cell.v==='number'&&Number.isFinite(x.cell.v)) bad.push(`${colName(c)}${x.r}`);
        }
        const cells=[...new Set(bad)]; if(!cells.length) continue;
        add(issues,issue(S.CHECK,'Парные строки / формулы',sheet,cells.join(', '),g.map(x=>`${x.platformRaw} — ${x.month}`).join(' | '),
          `В парных месячных строках «${g[0].platform}» часть производных KPI введена числами вместо формул.`,
          'Сравниваются только строки одной секции с одинаковыми площадкой, форматом, таргетингом и unit type. Если один месяц доказывает расчётную формулу, ручное число в соседнем месяце является риском расхождения при следующем обновлении.',
          'Проверьте перечисленные ячейки. Если ручной override не предусмотрен, восстановите формулы по парной строке.',
          `${g[0].section || 'секция не подписана'}; ${g.map(x=>`строка ${x.r}`).join(', ')}`));
      }
    }
    return issues;
  }

  function categoryKey(raw) {
    const s=norm(raw).replace(/\bprogrammatic\b/gu,' ').replace(/\bpaid\b/gu,' ').replace(/\s+/g,' ');
    if(/\bolv\b|online video|онлайн видео/iu.test(s)) return 'olv';
    if(/rich\s*media/iu.test(s)&&/cpc/iu.test(s)) return 'rich media cpc';
    if(/social/iu.test(s)&&/cpm/iu.test(s)) return 'social cpm';
    if(/social/iu.test(s)&&/cpc/iu.test(s)) return 'social cpc';
    if(/banner/iu.test(s)&&/cpm/iu.test(s)) return 'banners cpm';
    if(/banner/iu.test(s)&&/cpc/iu.test(s)) return 'banners cpc';
    return null;
  }
  function activeCategories(ws) {
    const h=findMediaHeader(ws); if(!h||h.no==null) return new Set();
    const budget=headerCol(h,/total cost after discount|total cost \+ adserving|budget|бюджет/iu);
    const out=new Set(); let current=null;
    const max=entries(ws).reduce((m,e)=>Math.max(m,e.pos.r+1),h.row);
    for(let r=h.row+1;r<=max;r++) {
      const no=rawText(cellAt(ws,r,h.no)).trim(), site=rawText(cellAt(ws,r,h.site)).trim(), month=rawText(cellAt(ws,r,h.month)).trim();
      if(no&&!site&&!month&&!/^\d+(?:[.,]\d+)?$/u.test(no)) { const k=categoryKey(no); if(k) current=k; continue; }
      if(!site||!month||!current) continue;
      const bc=budget!=null?cellAt(ws,r,budget):null;
      const active=(bc&&((typeof bc.v==='number'&&Number.isFinite(bc.v)&&bc.v>0)||!!bc.f)) || (!bc && site);
      if(active) out.add(current);
    }
    return out;
  }
  function flightNoFromText(v) { const m=String(v||'').match(/(\d+)\s*флайт/iu); return m?Number(m[1]):null; }
  function flightSheet(workbook,no) { return (workbook.SheetNames||[]).find(s=>new RegExp(`(?:^|\\D)${no}\\s*флайт`,'iu').test(s)); }
  function missingSummaryValue(cell) {
    if(!cell) return true;
    if(cell.f) return false;
    if(typeof cell.v==='number') return !Number.isFinite(cell.v)||cell.v===0;
    const t=norm(rawText(cell)); return !t||t==='-'||t==='—';
  }
  function addBudgetChannelCrossChecks(workbook,issues) {
    const summaries=(workbook.SheetNames||[]).filter(s=>/(budget.*channel|бюджет.*канал)/iu.test(s));
    for(const sheet of summaries) {
      const ws=workbook.Sheets[sheet]; if(!ws) continue;
      for(const e of entries(ws)) {
        if(e.pos.r>12||!/^(бюджет|budget)$/iu.test(norm(rawText(e.cell)))) continue;
        let no=null;
        for(let r=e.pos.r-1;r>=Math.max(0,e.pos.r-4)&&no==null;r--) no=flightNoFromText(rawText(ws[core.encodeCell(r,e.pos.c)]));
        if(no==null) continue;
        const fs=flightSheet(workbook,no), fws=fs&&workbook.Sheets[fs]; if(!fws) continue;
        const active=activeCategories(fws); if(!active.size) continue;
        const max=entries(ws).reduce((m,x)=>Math.max(m,x.pos.r),e.pos.r+20);
        for(let r=e.pos.r+1;r<=max;r++) {
          let label='';
          for(let c=e.pos.c-1;c>=0;c--) { const t=rawText(ws[core.encodeCell(r,c)]).trim(); if(t){label=t;break;} }
          const cat=categoryKey(label); if(!cat||!active.has(cat)) continue;
          const addr=core.encodeCell(r,e.pos.c), cell=ws[addr];
          if(!missingSummaryValue(cell)) continue;
          add(issues,issue(S.CRITICAL,'Сверка бюджета по каналам',sheet,addr,rawText(cell)||String(cell&&cell.v!=null?cell.v:''),
            `В своде по каналам для ${no}-го флайта отсутствует бюджет категории «${label}», хотя в медиаплане есть активные размещения этой категории.`,
            `Лист «${fs}» содержит строки размещения в категории «${label}», поэтому значение «-»/пусто/0 в бюджетной разбивке противоречит составу флайта.`,
            `Заполните бюджет категории «${label}» формулой/ссылкой на итог соответствующей секции и перепроверьте сумму бюджетов ${no}-го флайта.`,fs));
        }
      }
    }
  }

  function parseSheetRange(raw) {
    const s=String(raw||'').trim(), bang=s.lastIndexOf('!'); if(bang<1) return null;
    let sheet=s.slice(0,bang).trim().replace(/^'(.*)'$/,'$1').replace(/''/g,"'");
    const m=s.slice(bang+1).trim().match(/^(\$?[A-Z]{1,3}\$?\d+)(?::(\$?[A-Z]{1,3}\$?\d+))?$/i); if(!m) return null;
    return {sheet,start:m[1].replace(/\$/g,''),end:(m[2]||m[1]).replace(/\$/g,'')};
  }
  function expandRange(workbook,p,limit) {
    const ws=p&&workbook.Sheets&&workbook.Sheets[p.sheet], a=p&&core.decodeCell(p.start), b=p&&core.decodeCell(p.end); if(!ws||!a||!b) return [];
    const out=[];
    for(let r=Math.min(a.r,b.r);r<=Math.max(a.r,b.r);r++) for(let c=Math.min(a.c,b.c);c<=Math.max(a.c,b.c);c++) { out.push({addr:core.encodeCell(r,c),cell:ws[core.encodeCell(r,c)]}); if(out.length>=(limit||300)) return out; }
    return out;
  }
  function addControlSheetChecks(workbook,issues) {
    for(const sheet of workbook.SheetNames||[]) {
      if(!/(провер|check|контрол)/iu.test(sheet)) continue;
      const ws=workbook.Sheets[sheet]; if(!ws) continue;
      let header=null;
      for(let r=1;r<=15&&!header;r++) {
        const row=entries(ws).filter(e=>e.pos.r===r-1);
        const target=row.find(e=>/(лист\s*\/\s*ячейка|sheet\s*\/\s*cell)/iu.test(rawText(e.cell)));
        const status=row.find(e=>/^(статус|status)$/iu.test(norm(rawText(e.cell))));
        if(target&&status) header={row:r,target:target.pos.c,status:status.pos.c};
      }
      if(!header) continue;
      const max=entries(ws).reduce((m,e)=>Math.max(m,e.pos.r+1),header.row);
      for(let r=header.row+1;r<=max;r++) {
        const status=norm(rawText(cellAt(ws,r,header.status))); if(!/^(исправлено|ок|ok|fixed)$/iu.test(status)) continue;
        const raw=rawText(cellAt(ws,r,header.target)).trim(), p=parseSheetRange(raw); if(!p) continue;
        const bad=expandRange(workbook,p,500).filter(x=>x.cell&&typeof x.cell.f==='string'&&/#REF!/iu.test(x.cell.f)).map(x=>x.addr);
        if(!bad.length) continue;
        const shown=bad.slice(0,20).join(', ')+(bad.length>20?` +${bad.length-20}`:'');
        add(issues,issue(S.CHECK,'Контрольный лист / статус',sheet,core.encodeCell(r-1,header.target),raw,
          `Контрольный лист помечает диапазон как «${rawText(cellAt(ws,r,header.status))}», но в фактических формулах по-прежнему есть #REF!.`,
          'Статус контрольного листа противоречит текущему содержимому медиаплана и может создать ложное ощущение, что ошибка уже устранена.',
          'Исправьте формулы в указанном диапазоне либо обновите статус контрольного листа после фактической проверки.',`${p.sheet}!${shown}`));
      }
    }
  }

  function refineFormulaRefText(issues) {
    for(const x of issues||[]) {
      if(x.type!=='Формула Excel'||!/#REF!/iu.test(String(x.value||''))) continue;
      x.why='В тексте формулы присутствует битая ссылка #REF!. Даже если повреждённая ветка IF сейчас не используется или результат маскируется IFERROR, структура формулы остаётся некорректной и может сломаться при смене unit type/условий.';
      x.recommendation='Восстановите корректные ссылки внутри формулы и после этого перепроверьте зависимые KPI.';
    }
  }

  function finish(result) {
    const seen=new Set();
    result.issues=(result.issues||[]).filter(x=>{const k=key(x); if(seen.has(k))return false; seen.add(k); return true;});
    const order={[S.CRITICAL]:0,[S.CHECK]:1,[S.TEXT]:2};
    result.issues.sort((a,b)=>(order[a.severity]-order[b.severity])||String(a.sheet).localeCompare(String(b.sheet),'ru')||String(a.cell).localeCompare(String(b.cell),'ru'));
    result.counts={critical:result.issues.filter(x=>x.severity===S.CRITICAL).length,check:result.issues.filter(x=>x.severity===S.CHECK).length,text:result.issues.filter(x=>x.severity===S.TEXT).length};
    result.status=result.issues.length?'Нужно исправить':'Можно отправлять клиенту';
    return result;
  }

  core.runAllChecks=function(workbook,options){
    const result=originalRun(workbook,options||{});
    result.issues=filterFalsePositives(workbook,options||{},result.issues||[]);
    result.issues=rebuildPairedFormulaChecks(workbook,result.issues);
    addBudgetChannelCrossChecks(workbook,result.issues);
    addControlSheetChecks(workbook,result.issues);
    refineFormulaRefText(result.issues);
    return finish(result);
  };

  core.__productionRulesPatched=true;
  return core;
});
