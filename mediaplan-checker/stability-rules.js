(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./baseline-rules.js'));
  else if (root && root.MPChecks) root.MPChecks = factory(root.MPChecks);
})(typeof globalThis !== 'undefined' ? globalThis : this, function (core) {
  'use strict';
  if (!core || core.__stabilityRulesPatched) return core;

  const originalRun = core.runAllChecks.bind(core);
  const S = core.SEVERITY;
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

  function norm(v) {
    return String(v == null ? '' : v).replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
  }
  function rawText(cell) {
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
  function colNumber(col) {
    let n = 0;
    for (const ch of String(col || '').toUpperCase()) n = n * 26 + ch.charCodeAt(0) - 64;
    return n - 1;
  }
  function formulaDisplay(formula) {
    const f = String(formula || '').trim();
    return f.startsWith('=') ? f : `=${f}`;
  }
  function monthFromText(value) {
    const n = norm(value).replace(/[.'’]/g, '');
    for (const [k,v] of Object.entries(MONTHS)) if (n === k) return v;
    return null;
  }
  function rowMonth(ws, row1) {
    const r = Number(row1) - 1;
    if (!Number.isInteger(r) || r < 0) return null;
    for (let c = 0; c <= 20; c++) {
      const m = monthFromText(rawText(ws[core.encodeCell(r,c)]));
      if (m) return m;
    }
    return null;
  }
  function formulaRefs(formula) {
    const out = [];
    const re = /(?:(?:'((?:[^']|'')+)'|([A-Za-zА-Яа-яЁё0-9_ .-]+))!)?(\$?[A-Z]{1,3}\$?\d+)/g;
    let m;
    while ((m = re.exec(String(formula || '')))) {
      out.push({ sheet:(m[1] || m[2] || '').replace(/''/g, "'").trim(), addr:m[3].replace(/\$/g,'').toUpperCase() });
    }
    return out;
  }
  function distinctMonthsForAddresses(ws, addresses) {
    const s = new Set();
    for (const a of addresses) {
      const m = String(a).match(/^[A-Z]{1,3}(\d+)$/i);
      const month = m ? rowMonth(ws, Number(m[1])) : null;
      if (month) s.add(month);
    }
    return s;
  }
  function targetFromPeriodIssue(x) {
    const related = String(x.related || '');
    const m = related.match(/^(.+?):\s*[A-Z]{1,3}\d+/u);
    if (m) return m[1].trim();
    const p = String(x.problem || '').match(/листа\s+«([^»]+)»/u);
    return p ? p[1].trim() : '';
  }
  function shouldSuppressIncompletePeriodIssue(workbook, x) {
    if (x.type !== 'Формула / период' || !/использует не все месячные итоги активных дней/iu.test(String(x.problem || ''))) return false;
    const target = targetFromPeriodIssue(x);
    const sourceWs = workbook.Sheets && workbook.Sheets[x.sheet];
    const targetWs = workbook.Sheets && workbook.Sheets[target];
    const sourceCell = sourceWs && sourceWs[x.cell];
    if (!target || !targetWs || !sourceCell || !sourceCell.f) return false;

    const candidateAddresses = (String(x.related || '').match(/[A-Z]{1,3}\d+/g) || []).map(a=>a.toUpperCase());
    if (!candidateAddresses.length) return false;
    const allMonths = distinctMonthsForAddresses(targetWs, candidateAddresses);
    if (!allMonths.size) return false;

    const refs = formulaRefs(sourceCell.f)
      .filter(r => norm(r.sheet) === norm(target))
      .map(r => r.addr);
    const refMonths = distinctMonthsForAddresses(targetWs, refs);
    if (!refMonths.size) return false;

    return [...allMonths].every(m => refMonths.has(m));
  }
  function filterFalsePositives(workbook, issues) {
    return (issues || []).filter(x => {
      // Прогноз Reach может быть внешним входным параметром площадки. Само отсутствие формулы не является проблемой.
      if (x.type === 'Расчёт охвата / воспроизводимость') return false;
      if (shouldSuppressIncompletePeriodIssue(workbook, x)) return false;
      return true;
    });
  }

  function parseDirectReference(formula) {
    // SheetJS хранит cell.f без ведущего "=", но синтетические/другие источники иногда его добавляют.
    const m = String(formula || '').trim().match(/^=?\s*(?:'((?:[^']|'')+)'|([^!]+))!\$?([A-Z]{1,3})\$?(\d+)\s*$/u);
    if (!m) return null;
    return { sheet:(m[1] || m[2] || '').replace(/''/g,"'").trim(), col:m[3].toUpperCase(), row:Number(m[4]), addr:`${m[3].toUpperCase()}${Number(m[4])}` };
  }
  function isDateLikeCell(cell) {
    if (!cell) return false;
    if (cell.t === 'd' || cell.v instanceof Date) return true;
    const shown = String(cell.w || cell.v || '');
    const fmt = String(cell.z || '');
    if (/\b\d{1,2}[.\/-]\d{1,2}(?:[.\/-]\d{2,4})?\b/.test(shown)) return true;
    return typeof cell.v === 'number' && /[dmyдмг]/i.test(fmt);
  }
  function nearbyLabel(ws, pos) {
    const parts = [];
    for (let r = Math.max(0,pos.r-1); r <= pos.r+1; r++) {
      for (let c = Math.max(0,pos.c-5); c <= pos.c; c++) {
        const t = rawText(ws[core.encodeCell(r,c)]);
        if (t) parts.push(t);
      }
    }
    return norm(parts.join(' '));
  }
  function addSummaryDateRobustness(workbook, issues) {
    for (const sheet of workbook.SheetNames || []) {
      if (!/(свод|summary)/iu.test(sheet)) continue;
      const ws = workbook.Sheets[sheet];
      if (!ws) continue;
      for (const e of entries(ws)) {
        if (!e.cell.f || !isDateLikeCell(e.cell)) continue;
        const ctx = nearbyLabel(ws, e.pos);
        if (!/(период|кампан|campaign|начал|старт|start|конец|оконч|end|финиш|дата)/iu.test(ctx)) continue;
        const ref = parseDirectReference(e.cell.f);
        if (!ref || ref.row < 15) continue;
        const targetWs = workbook.Sheets[ref.sheet];
        if (!targetWs) continue;
        const targetCol = colNumber(ref.col);
        const dateRows = entries(targetWs).filter(x => x.pos.c === targetCol && x.pos.r >= 14 && x.pos.r <= 119 && isDateLikeCell(x.cell));
        if (dateRows.length < 2) continue;
        add(issues, issue(
          S.CHECK,
          'Свод / устойчивость ссылки',
          sheet,
          e.addr,
          formulaDisplay(e.cell.f),
          `Сводная дата кампании ссылается на одну строку размещения (${ref.sheet}!${ref.addr}).`,
          'Текущее значение может быть правильным, но ссылка зависит от конкретной строки. После перестановки строк, добавления площадки или изменения периода свод может перестать отражать фактическую границу кампании.',
          'Если это дата начала/окончания всей кампании, используйте устойчивую итоговую ячейку или MIN/MAX по релевантным датам; если прямая ссылка осознанна — зафиксируйте это в шаблоне.',
          ref.sheet
        ));
      }
    }
  }

  function extractDomains(value) {
    const out = [];
    const re = /(?:https?:\/\/)?(?:www\.)?([a-z0-9а-яё-]+(?:\.[a-z0-9а-яё-]+)+)/giu;
    let m;
    while ((m = re.exec(String(value || '')))) {
      const host = String(m[1] || '').toLowerCase().replace(/[),.;]+$/,'');
      if (host && !out.includes(host)) out.push(host);
    }
    return out;
  }
  function suspiciousDomain(host) {
    return /(lord[-.]?film|lordfilm|hdrezka|rezka|kinogo|kino[-.]?go|kinokrad|filmix|dorama|doramy|serial|kinobar|gidonline|film[-.]?online|kino[-.]?online)/iu.test(host);
  }
  function addBrandSafetyDomains(workbook, issues) {
    for (const sheet of workbook.SheetNames || []) {
      const ws = workbook.Sheets[sheet];
      if (!ws) continue;
      const hits = [];
      for (const e of entries(ws)) {
        const raw = rawText(e.cell);
        if (!raw) continue;
        for (const host of extractDomains(raw)) {
          if (suspiciousDomain(host)) hits.push({cell:e.addr,host});
        }
      }
      if (!hits.length) continue;
      const uniqueHosts = [...new Set(hits.map(h=>h.host))];
      const cells = [...new Set(hits.map(h=>h.cell))];
      add(issues, issue(
        S.CHECK,
        'Brand Safety / домены',
        sheet,
        cells.length <= 12 ? cells.join(', ') : `${cells.slice(0,12).join(', ')} +${cells.length-12}`,
        uniqueHosts.slice(0,20).join(', '),
        `В инвентаре найдены потенциально спорные домены для brand safety: ${uniqueHosts.slice(0,10).join(', ')}${uniqueHosts.length>10?' …':''}.`,
        'Названия доменов содержат признаки неофициальных кино/сериальных ресурсов. Это не доказывает нарушение само по себе, но такой инвентарь нужно проверить перед клиентской отправкой.',
        'Проверьте домены по актуальному whitelist/blacklist клиента и площадки. Подтверждённо допустимые домены можно добавить в исключения.',
        `${hits.length} совпадений`
      ));
    }
  }

  function finish(result) {
    const seen = new Set();
    result.issues = (result.issues || []).filter(x => { const k=issueKey(x); if(seen.has(k)) return false; seen.add(k); return true; });
    const weight = {[S.CRITICAL]:0,[S.CHECK]:1,[S.TEXT]:2};
    result.issues.sort((a,b)=>(weight[a.severity]-weight[b.severity]) || String(a.sheet).localeCompare(String(b.sheet),'ru') || String(a.cell).localeCompare(String(b.cell),'ru'));
    result.counts = {
      critical:result.issues.filter(x=>x.severity===S.CRITICAL).length,
      check:result.issues.filter(x=>x.severity===S.CHECK).length,
      text:result.issues.filter(x=>x.severity===S.TEXT).length
    };
    result.status = result.issues.length ? 'Нужно исправить' : 'Можно отправлять клиенту';
    return result;
  }

  core.runAllChecks = function (workbook, options) {
    const result = originalRun(workbook, options || {});
    result.issues = filterFalsePositives(workbook, result.issues || []);
    addSummaryDateRobustness(workbook, result.issues);
    addBrandSafetyDomains(workbook, result.issues);
    return finish(result);
  };

  core.__stabilityRulesPatched = true;
  return core;
});