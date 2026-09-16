(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./production-rules.js'));
  else if (root && root.MPChecks) root.MPChecks = factory(root.MPChecks);
})(typeof globalThis !== 'undefined' ? globalThis : this, function (core) {
  'use strict';
  if (!core || core.__finalCleanupRulesPatched) return core;

  const originalRun = core.runAllChecks.bind(core);
  const S = core.SEVERITY;

  function norm(v) {
    return String(v == null ? '' : v).replace(/\u00a0/g,' ').replace(/\s+/g,' ').trim().toLowerCase().replace(/ё/g,'е');
  }
  function text(cell) {
    if (!cell) return '';
    if (typeof cell.v === 'string') return cell.v;
    if (cell.t === 's' && cell.v != null) return String(cell.v);
    if (typeof cell.w === 'string') return cell.w;
    return '';
  }
  function entries(ws) {
    return Object.keys(ws || {}).filter(k=>/^[A-Z]{1,3}\d+$/i.test(k)).map(addr=>({addr:addr.toUpperCase(),pos:core.decodeCell(addr),cell:ws[addr]})).filter(x=>x.pos&&x.cell);
  }
  function findControlHeader(ws) {
    const byRow = new Map();
    for (const e of entries(ws)) {
      if (e.pos.r > 14) continue;
      const t = norm(text(e.cell));
      if (!t) continue;
      if (!byRow.has(e.pos.r)) byRow.set(e.pos.r, []);
      byRow.get(e.pos.r).push({c:e.pos.c,t});
    }
    for (const [r,cells] of byRow) {
      const found = cells.find(x=>/^(что обнаружено|найденная проблема|detected issue|issue found)$/iu.test(x.t));
      const status = cells.find(x=>/^(статус|status)$/iu.test(x.t));
      if (found && status) return {row:r+1, found:found.c, status:status.c};
    }
    return null;
  }
  function isHistoricalControlQuote(workbook, issue) {
    if (!issue || issue.severity !== S.TEXT || !issue.sheet || !issue.cell) return false;
    if (!/(провер|check|контрол)/iu.test(issue.sheet)) return false;
    const ws = workbook.Sheets && workbook.Sheets[issue.sheet];
    if (!ws) return false;
    const h = findControlHeader(ws); if (!h) return false;
    const m = String(issue.cell).trim().match(/^([A-Z]{1,3}\d+)$/i); if (!m) return false;
    const pos = core.decodeCell(m[1].toUpperCase()); if (!pos || pos.c !== h.found || pos.r + 1 <= h.row) return false;
    const status = norm(text(ws[core.encodeCell(pos.r, h.status)]));
    return /^(исправлено|ок|ok|fixed)$/iu.test(status);
  }

  core.runAllChecks = function (workbook, options) {
    const result = originalRun(workbook, options || {});
    result.issues = (result.issues || []).filter(x => !isHistoricalControlQuote(workbook, x));
    result.counts = {
      critical: result.issues.filter(x=>x.severity===S.CRITICAL).length,
      check: result.issues.filter(x=>x.severity===S.CHECK).length,
      text: result.issues.filter(x=>x.severity===S.TEXT).length
    };
    result.status = result.issues.length ? 'Нужно исправить' : 'Можно отправлять клиенту';
    return result;
  };

  core.__finalCleanupRulesPatched = true;
  return core;
});
