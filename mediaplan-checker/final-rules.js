(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./lab-rules.js'));
  else if (root && root.MPChecks) root.MPChecks = factory(root.MPChecks);
})(typeof globalThis !== 'undefined' ? globalThis : this, function (core) {
  'use strict';
  if (!core || core.__finalRulesPatched) return core;

  const originalRun = core.runAllChecks.bind(core);
  const S = core.SEVERITY;
  const ERROR_TOKENS = ['#REF!', '#DIV/0!', '#VALUE!', '#N/A', '#NAME?', '#NUM!', '#NULL!'];
  const MONTHS = {
    january:1, jan:1, 'январь':1, 'января':1,
    february:2, feb:2, 'февраль':2, 'февраля':2,
    march:3, mar:3, 'март':3, 'марта':3,
    april:4, apr:4, 'апрель':4, 'апреля':4,
    may:5, 'май':5, 'мая':5,
    june:6, jun:6, 'июнь':6, 'июня':6,
    july:7, jul:7, 'июль':7, 'июля':7,
    august:8, aug:8, 'август':8, 'августа':8,
    september:9, sep:9, sept:9, 'сентябрь':9, 'сентября':9,
    october:10, oct:10, 'октябрь':10, 'октября':10,
    november:11, nov:11, 'ноябрь':11, 'ноября':11,
    december:12, dec:12, 'декабрь':12, 'декабря':12
  };

  function textCell(cell) {
    if (!cell) return '';
    if (typeof cell.v === 'string') return cell.v;
    if (cell.t === 's' && cell.v != null) return String(cell.v);
    return '';
  }
  function entries(ws) {
    return Object.keys(ws || {})
      .filter(k => /^[A-Z]{1,3}\d+$/i.test(k))
      .map(addr => ({ addr: addr.toUpperCase(), pos: core.decodeCell(addr), cell: ws[addr] }))
      .filter(x => x.pos && x.cell && (x.cell.v != null || x.cell.f));
  }
  function issue(severity, type, sheet, cell, value, problem, why, recommendation, related) {
    return { severity, type, sheet: sheet || '', cell: cell || '', value: value == null ? '' : String(value), problem, why, recommendation, related: related || '', fixStatus: '' };
  }
  function issueKey(x) { return [x.severity,x.type,x.sheet,x.cell,x.problem,x.related].join('|'); }
  function add(list, x) { if (!list.some(y => issueKey(y) === issueKey(x))) list.push(x); }
  function sameDayMonth(a, b) { return !!a && !!b && Number(a.day) === Number(b.day) && Number(a.month) === Number(b.month); }
  function flightNumber(name) { const m = String(name || '').match(/(^|\D)(\d+)\s*(?:флайт|flight)/i); return m ? Number(m[2]) : -1; }
  function flightSheets(workbook) {
    return (workbook.SheetNames || []).filter(s => /флайт|flight/i.test(s)).sort((a,b) => flightNumber(a)-flightNumber(b));
  }
  function latestFlightSheet(workbook) {
    const a = flightSheets(workbook); return a.length ? a[a.length-1] : null;
  }
  function parseHeaderPeriod(ws) {
    const candidates = [];
    for (const e of entries(ws)) {
      if (e.pos.r > 11) continue;
      const t = core.extractDateTokensFromText(core.getCellText(e.cell));
      if (t.length < 2 || !t[0].year || !t[1].year) continue;
      candidates.push({ cell:e.addr, start:t[0], end:t[1], raw:core.getCellText(e.cell) });
    }
    candidates.sort((a,b) => {
      const pa = core.decodeCell(a.cell), pb = core.decodeCell(b.cell);
      return pa.r-pb.r || pa.c-pb.c;
    });
    return candidates[0] || null;
  }
  function sheetContainsDate(ws, token) {
    for (const e of entries(ws)) {
      const tokens = core.extractDateTokensFromText(core.getCellText(e.cell));
      if (tokens.some(t => sameDayMonth(t, token))) return e.addr;
    }
    return null;
  }
  function monthFromCellText(value) {
    const n = core.normalizeText(value).replace(/[.'’]/g,'');
    if (!n) return null;
    for (const [k,v] of Object.entries(MONTHS)) if (n === k) return v;
    return null;
  }
  function placementMonths(ws) {
    const found = new Set();
    for (const e of entries(ws)) {
      if (e.pos.r < 15 || e.pos.c > 20) continue;
      const m = monthFromCellText(textCell(e.cell));
      if (m) found.add(m);
    }
    return [...found].sort((a,b)=>a-b);
  }
  function sheetSearchText(ws) {
    return core.normalizeText(entries(ws).map(e => textCell(e.cell)).filter(Boolean).join('\n'));
  }

  function filterMediaMathNoise(workbook, issues) {
    return issues.filter(x => {
      if (x.type !== 'Математика медиаплана' || !x.sheet || !x.cell) return true;
      const ws = workbook.Sheets && workbook.Sheets[x.sheet];
      if (!ws) return true;
      const addrs = [x.cell].concat((String(x.related || '').match(/[A-Z]{1,3}\d+/g) || []));
      const cells = addrs.map(a => ws[a]).filter(Boolean);
      if (!cells.length) return false;
      // Универсальная арифметика допустима только для полностью ручной строки.
      // Если хотя бы один участник расчёта — формула, сначала доверяем структуре книги,
      // а не предполагаемой позиции соседних колонок.
      if (cells.some(c => c.f)) return false;
      return cells.every(c => typeof c.v === 'number' && Number.isFinite(c.v));
    });
  }

  function improveDefinedNames(options, issues) {
    const raw = options && options.rawInfo;
    if (!raw || !Array.isArray(raw.definedNames) || !raw.definedNames.length) return;
    const unique = new Map();
    for (const n of raw.definedNames) {
      const name = n && (n.name || n.Name) || '';
      const ref = n && (n.ref || n.Ref) || '';
      if (!ERROR_TOKENS.some(t => String(ref).toUpperCase().includes(t))) continue;
      unique.set(`${name}|${ref}`, {name,ref});
    }
    const counts = {};
    for (const t of ERROR_TOKENS) counts[t] = 0;
    for (const n of unique.values()) {
      const u = String(n.ref).toUpperCase();
      for (const t of ERROR_TOKENS) if (u.includes(t)) counts[t]++;
    }
    const tokenHits = Object.values(counts).reduce((a,b)=>a+b,0);
    const details = Object.entries(counts).filter(([,v])=>v).map(([k,v])=>`${k}: ${v}`).join('; ');
    const existing = issues.find(x => x.type === 'Именованные диапазоны');
    if (!existing) return;
    const total = Number(raw.definedNamesTotal || 0);
    existing.problem = `Обнаружено ${unique.size} уникальных битых именованных диапазонов${total ? ` из ${total}` : ''}. По типам ошибок — ${tokenHits} срабатываний.`;
    existing.why = tokenHits > unique.size
      ? `Одно имя может содержать несколько разных ошибок одновременно, поэтому сумма по типам (${tokenHits}) может быть больше числа уникальных имён (${unique.size}). ${details}`
      : `Разбивка по типам: ${details}`;
    existing.recommendation = 'Проверьте Диспетчер имён Excel; удаляйте только неиспользуемые имена после резервной копии.';
  }

  function updateIntroResult(results, sentence, status, detail) {
    const i = results.findIndex(x => x.sentence === sentence);
    if (i >= 0) results[i] = { sentence, status, detail };
    else results.push({ sentence, status, detail });
  }

  function enhanceStartIntro(workbook, sentence, results, issues) {
    if (!/(старт|начал|начало|начать)/iu.test(sentence)) return;
    const tokens = core.extractDateTokensFromText(sentence);
    if (!tokens.length) return;
    const wanted = tokens[0];
    const candidates = [];
    for (const sheet of flightSheets(workbook)) {
      const ws = workbook.Sheets[sheet];
      const hit = sheetContainsDate(ws, wanted);
      if (!hit) continue;
      candidates.push({ sheet, hit, period:parseHeaderPeriod(ws) });
    }
    if (!candidates.length) return;
    const exact = candidates.find(x => x.period && sameDayMonth(x.period.start, wanted));
    if (exact) {
      updateIntroResult(results, sentence, 'Найдено', `Дата старта из вводных подтверждена шапкой ${exact.sheet}!${exact.period.cell}.`);
      return;
    }
    const conflict = candidates.find(x => x.period && !sameDayMonth(x.period.start, wanted));
    if (!conflict) return;
    const wantedText = wanted.raw || `${wanted.day}.${wanted.month}`;
    const detail = `Дата ${wantedText} найдена в календаре ${conflict.sheet}!${conflict.hit}, но старт в шапке ${conflict.sheet}!${conflict.period.cell} указан иначе: «${conflict.period.raw}».`;
    updateIntroResult(results, sentence, 'Требует проверки', detail);
    add(issues, issue(S.CHECK,'Сопроводительные вводные',conflict.sheet,conflict.period.cell,conflict.period.raw,'Дата старта в шапке противоречит сопроводительным вводным и календарю.','Одна и та же кампания содержит разные даты старта.','Сверьте шапку флайта с утверждённой датой и календарной сеткой.',conflict.hit));
  }

  function requestedMonthCount(sentence) {
    if (/(почему|не стоит|не нужно|не рекоменду|например)/iu.test(sentence)) return null;
    if (!/(растянут|продл|размещен|сделать)/iu.test(sentence)) return null;
    const m = sentence.match(/(?:на|в течение)\s*(\d+)\s*месяц/iu);
    return m ? Number(m[1]) : null;
  }
  function enhanceDurationIntro(workbook, sentence, results, issues) {
    const requested = requestedMonthCount(sentence);
    if (!requested) return;
    const sheet = latestFlightSheet(workbook);
    if (!sheet) return;
    const ws = workbook.Sheets[sheet];
    const months = placementMonths(ws);
    if (!months.length) {
      updateIntroResult(results, sentence, 'Требует проверки', `Не удалось надёжно определить месяцы размещения на листе «${sheet}».`);
      return;
    }
    const names = months.map(m => String(m).padStart(2,'0')).join(', ');
    const text = sheetSearchText(ws);
    const wantsOlv = /\bOLV\b/i.test(sentence);
    const wantsBanners = /баннер|banner/iu.test(sentence);
    const olvOk = !wantsOlv || /\bolv\b/i.test(text);
    const bannersOk = !wantsBanners || /баннер|banner/iu.test(text);
    if (months.length === requested && olvOk && bannersOk) {
      const channels = [wantsOlv?'OLV':null,wantsBanners?'баннеры':null].filter(Boolean);
      updateIntroResult(results, sentence, 'Найдено', `В последнем флайте «${sheet}» размещение заведено на ${months.length} месяца (месяцы ${names})${channels.length ? `; требуемые каналы найдены: ${channels.join(', ')}` : ''}.`);
      return;
    }
    const detail = `Во вводных запрошено ${requested} месяца, а в строках размещений последнего флайта «${sheet}» обнаружено месяцев: ${months.length} (${names})${!olvOk?' ; OLV не найден':''}${!bannersOk?' ; баннерное размещение не найдено':''}.`;
    updateIntroResult(results, sentence, 'Не найдено', detail);
    add(issues, issue(S.CHECK,'Сопроводительные вводные',sheet,'',sentence,detail,'Явное требование по длительности/каналам не подтверждено строками размещений.','Сверьте месяцы и каналы последнего флайта.'));
  }

  function enhanceIntro(workbook, options, baseResults, issues) {
    const text = String(options && options.intro || '').trim();
    const results = (baseResults || []).slice();
    if (!text) return results;
    const sentences = text.split(/\n+|(?<=[.!?;])\s+/).map(x=>x.trim()).filter(Boolean);
    for (const sentence of sentences) {
      enhanceStartIntro(workbook, sentence, results, issues);
      enhanceDurationIntro(workbook, sentence, results, issues);
    }
    return results;
  }

  function addUnsupportedThresholdClaims(workbook, options, issues) {
    const claims = [];
    for (const sheet of workbook.SheetNames || []) {
      const ws = workbook.Sheets[sheet];
      for (const e of entries(ws)) {
        const raw = textCell(e.cell);
        if (!raw) continue;
        if (/(порогов\w*\s+месячн\w*\s+бюджет|выше\s+порог\w*|минимальн\w*\s+месячн\w*\s+бюджет)/iu.test(raw)) claims.push({sheet,cell:e.addr,text:raw});
      }
    }
    const intro = String(options && options.intro || '');
    if (/(порогов\w*\s+месячн\w*\s+бюджет|выше\s+порог\w*|минимальн\w*\s+месячн\w*\s+бюджет)/iu.test(intro)) claims.push({sheet:'Вводные',cell:'',text:intro});
    if (!claims.length) return;

    let evidence = false;
    for (const sheet of workbook.SheetNames || []) {
      const ws = workbook.Sheets[sheet];
      for (const e of entries(ws)) {
        const raw = textCell(e.cell);
        if (!raw || !/(порог|min(?:imum)?\s+budget|минимальн\w*\s+бюджет)/iu.test(raw)) continue;
        if (/\d[\d\s.,]*\s*(?:₽|руб|р\.?|тыс|млн)/iu.test(raw)) { evidence = true; break; }
      }
      if (evidence) break;
    }
    if (evidence) return;
    const c = claims[0];
    add(issues, issue(S.CHECK,'Обоснование порога',c.sheet,c.cell,c.text,'Тезис о пороговом/минимальном месячном бюджете не подтверждён явным числовым порогом внутри книги.','Без источника или числового поля такой тезис нельзя доказать по текущему медиаплану.','Добавьте источник/примечание с порогом либо формулируйте вывод без недоказанного числового порога.'));
  }

  function finish(result) {
    const seen = new Set();
    result.issues = result.issues.filter(x => { const k=issueKey(x); if(seen.has(k)) return false; seen.add(k); return true; });
    const w = {[S.CRITICAL]:0,[S.CHECK]:1,[S.TEXT]:2};
    result.issues.sort((a,b)=>(w[a.severity]-w[b.severity])||String(a.sheet).localeCompare(String(b.sheet),'ru')||String(a.cell).localeCompare(String(b.cell),'ru'));
    result.counts = {
      critical:result.issues.filter(x=>x.severity===S.CRITICAL).length,
      check:result.issues.filter(x=>x.severity===S.CHECK).length,
      text:result.issues.filter(x=>x.severity===S.TEXT).length
    };
    result.status = result.counts.critical || result.counts.check || result.counts.text ? 'Нужно исправить' : 'Можно отправлять клиенту';
    return result;
  }

  core.runAllChecks = function (workbook, options) {
    options = options || {};
    const result = originalRun(workbook, options);
    result.issues = filterMediaMathNoise(workbook, result.issues || []);
    improveDefinedNames(options, result.issues);
    result.introResults = enhanceIntro(workbook, options, result.introResults || [], result.issues);
    addUnsupportedThresholdClaims(workbook, options, result.issues);
    return finish(result);
  };

  core.__finalRulesPatched = true;
  return core;
});
