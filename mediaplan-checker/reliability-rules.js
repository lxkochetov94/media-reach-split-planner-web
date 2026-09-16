(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./hardening-rules.js'));
  else if (root && root.MPChecks) root.MPChecks = factory(root.MPChecks);
})(typeof globalThis !== 'undefined' ? globalThis : this, function (core) {
  'use strict';
  if (!core || core.__reliabilityRulesPatched) return core;

  const originalRun = core.runAllChecks.bind(core);
  const S = core.SEVERITY;

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
    return '';
  }
  function entries(ws) {
    return Object.keys(ws || {})
      .filter(k => /^[A-Z]{1,3}\d+$/i.test(k))
      .map(addr => ({ addr: addr.toUpperCase(), pos: core.decodeCell(addr), cell: ws[addr] }))
      .filter(x => x.pos && x.cell && (x.cell.v != null || x.cell.f || x.cell.c));
  }
  function cellAt(ws, row1, col0) { return ws && ws[core.encodeCell(row1 - 1, col0)]; }
  function colName(col0) { return core.encodeCell(0, col0).replace(/\d+$/, ''); }
  function issue(severity, type, sheet, cell, value, problem, why, recommendation, related) {
    return { severity, type, sheet: sheet || '', cell: cell || '', value: value == null ? '' : String(value), problem: problem || '', why: why || '', recommendation: recommendation || 'Проверьте вручную.', related: related || '', fixStatus: '' };
  }
  function issueKey(x) { return [x.severity, x.type, x.sheet, x.cell, x.problem, x.related].join('|'); }
  function add(list, x) { if (!list.some(y => issueKey(y) === issueKey(x))) list.push(x); }

  function findHeaderRow(ws) {
    const rows = new Map();
    for (const e of entries(ws)) {
      if (e.pos.r > 39) continue;
      const t = norm(rawText(e.cell));
      if (!t) continue;
      if (!rows.has(e.pos.r)) rows.set(e.pos.r, []);
      rows.get(e.pos.r).push({ c: e.pos.c, t, addr: e.addr });
    }
    for (const [r, cells] of rows) {
      const site = cells.find(x => /^(site|площадка)$/iu.test(x.t));
      const month = cells.find(x => /^(month|месяц)$/iu.test(x.t));
      if (site && month) return { row: r + 1, cells, site: site.c, month: month.c };
    }
    return null;
  }
  function headerCol(h, re) {
    const x = h && h.cells.find(v => re.test(v.t));
    return x ? x.c : null;
  }
  function headerText(ws, h, c) {
    const parts = [];
    for (let r = h.row; r <= h.row + 2; r++) {
      const t = rawText(cellAt(ws, r, c));
      if (t) parts.push(t);
    }
    return norm(parts.join(' '));
  }

  // ---------------------------------------------------------------------------
  // 1. Календарь: только доказанная календарная сетка + реальные placement-строки.
  // Числа KPI (например Frequency = 4.5) и строка номера недели никогда не трактуются как даты/дни.
  // ---------------------------------------------------------------------------
  function parseCalendarDate(cell) {
    if (!cell) return null;
    if (cell.v instanceof Date) return { y: cell.v.getUTCFullYear(), m: cell.v.getUTCMonth() + 1, d: cell.v.getUTCDate() };
    if (cell.t === 'd' && cell.v) {
      const d = new Date(cell.v);
      if (!Number.isNaN(d.getTime())) return { y: d.getUTCFullYear(), m: d.getUTCMonth() + 1, d: d.getUTCDate() };
    }
    // Важное ограничение: обычное числовое значение (4.5, 5, 44 и т.п.) датой не является.
    const shown = typeof cell.v === 'string' ? cell.v : (typeof cell.w === 'string' ? cell.w : '');
    const m = String(shown || '').trim().match(/^(\d{1,2})[.\/-](\d{1,2})(?:[.\/-](\d{2}|\d{4}))?$/u);
    if (!m) return null;
    const day = Number(m[1]), month = Number(m[2]);
    let year = m[3] ? Number(m[3]) : null;
    if (year != null && year < 100) year += 2000;
    if (day < 1 || month < 1 || month > 12) return null;
    const probe = new Date(Date.UTC(year || 2000, month - 1, day));
    if (probe.getUTCMonth() + 1 !== month || probe.getUTCDate() !== day) return null;
    return { y: year, m: month, d: day };
  }
  function inclusiveDays(a, b) {
    if (!a || !b) return null;
    let y1 = a.y || 2000, y2 = b.y || y1;
    if (!b.y && (b.m < a.m || (b.m === a.m && b.d < a.d))) y2 = y1 + 1;
    const d1 = Date.UTC(y1, a.m - 1, a.d), d2 = Date.UTC(y2, b.m - 1, b.d);
    const n = Math.round((d2 - d1) / 86400000) + 1;
    return n >= 1 && n <= 7 ? n : null;
  }
  function placementRows(ws, h) {
    const out = [];
    for (let r = h.row + 1; r <= h.row + 180; r++) {
      const site = rawText(cellAt(ws, r, h.site)).trim();
      const month = rawText(cellAt(ws, r, h.month)).trim();
      if (!site || !month) continue;
      if (/^(total|итого|всего)$/iu.test(norm(site))) continue;
      out.push(r);
    }
    return out;
  }
  function calendarColumns(ws, h) {
    const out = [];
    const maxC = Math.min(220, Math.max(h.month + 1, ...entries(ws).map(e => e.pos.c)));
    const startRow = h.row + 1, endRow = h.row + 2;
    for (let c = h.month + 1; c <= maxC; c++) {
      const a = parseCalendarDate(cellAt(ws, startRow, c));
      const b = parseCalendarDate(cellAt(ws, endRow, c));
      const days = inclusiveDays(a, b);
      if (!days) continue;
      out.push({ c, startRow, endRow, a, b, days });
    }
    return out;
  }
  function rebuildCalendarChecks(workbook, issues) {
    issues = (issues || []).filter(x => x.type !== 'Календарь / активные дни');
    for (const sheet of workbook.SheetNames || []) {
      const ws = workbook.Sheets[sheet];
      if (!ws) continue;
      const h = findHeaderRow(ws);
      if (!h) continue;
      const rows = placementRows(ws, h);
      const cols = calendarColumns(ws, h);
      if (!rows.length || !cols.length) continue;
      for (const band of cols) {
        const offenders = [];
        for (const r of rows) {
          const cell = cellAt(ws, r, band.c);
          if (!cell || typeof cell.v !== 'number' || !Number.isFinite(cell.v)) continue;
          const value = Number(cell.v);
          if (!Number.isInteger(value) || value < 0 || value > 7 || value <= band.days) continue;
          offenders.push(`${colName(band.c)}${r}`);
        }
        if (!offenders.length) continue;
        const aCell = cellAt(ws, band.startRow, band.c), bCell = cellAt(ws, band.endRow, band.c);
        const aRaw = String(aCell && (aCell.w != null ? aCell.w : aCell.v) || '');
        const bRaw = String(bCell && (bCell.w != null ? bCell.w : bCell.v) || '');
        add(issues, issue(
          S.CRITICAL, 'Календарь / активные дни', sheet, offenders.join(', '), `${aRaw} — ${bRaw}`,
          `В интервале ${aRaw}–${bRaw} максимум ${band.days} календарных дней, но в строках размещения указано больше.`,
          'Проверка выполнена только по доказанной календарной шапке и строкам размещений. Количество активных дней математически не может превышать длину интервала.',
          `Исправьте активные дни: для этого интервала допустимо не более ${band.days}.`,
          `${colName(band.c)}${band.startRow}:${colName(band.c)}${band.endRow}`
        ));
      }
    }
    return issues;
  }

  // ---------------------------------------------------------------------------
  // 2. Парные месячные строки. Нормализуем только идентичность площадки,
  // а подозрение строим на факте: в одном и том же поле одна строка содержит
  // производную формулу, соседний месяц — ручное число.
  // ---------------------------------------------------------------------------
  function pairPlatform(raw) {
    let s = String(raw || '').split(/\r?\n/)[0].trim();
    s = s.replace(/\b(?:bonus|бонус(?:ом|ный|ная|ное|ные)?|BLS|SL|brand\s*lift(?:\s*study)?)\b/giu, ' ').replace(/\s+/g, ' ').trim();
    return typeof core.canonicalPlatformName === 'function' ? core.canonicalPlatformName(s) : s;
  }
  function pairGroups(ws, h) {
    const fmt = headerCol(h, /^(format|формат|ad size.*format)$/iu);
    const target = headerCol(h, /(target|таргет|audien|аудитор)/iu);
    const unit = headerCol(h, /(unit type|buying unit|единиц)/iu);
    const groups = new Map();
    for (const r of placementRows(ws, h)) {
      const platformRaw = rawText(cellAt(ws, r, h.site)).trim();
      const month = rawText(cellAt(ws, r, h.month)).trim();
      const platform = pairPlatform(platformRaw);
      const key = [
        platform,
        fmt != null ? norm(rawText(cellAt(ws, r, fmt))) : '',
        target != null ? norm(rawText(cellAt(ws, r, target))) : '',
        unit != null ? norm(rawText(cellAt(ws, r, unit))) : ''
      ].join('|');
      if (!groups.has(key)) groups.set(key, []);
      groups.get(key).push({ r, platform, platformRaw, month });
    }
    return [...groups.values()].filter(g => new Set(g.map(x => norm(x.month))).size >= 2);
  }
  function firstCalendarColumn(ws, h) {
    const cols = calendarColumns(ws, h);
    return cols.length ? Math.min(...cols.map(x => x.c)) : null;
  }
  function isManualInputHeader(label) {
    const t = norm(label);
    return /^(units? qty(?: total)?|ratecard(?: \(cost per unit\))?|multipliers?|data cpm|discount(?:,? %)?|frequency|ctr%?|planning vtr.*|vtr%?|adserver)$/iu.test(t);
  }
  function formulaReferencesOwnRow(formula, row) {
    const re = /\$?[A-Z]{1,3}\$?(\d+)/g;
    let m;
    while ((m = re.exec(String(formula || '')))) if (Number(m[1]) === row) return true;
    return false;
  }
  function rebuildPairedFormulaValueChecks(workbook, issues) {
    issues = (issues || []).filter(x => x.type !== 'Парные строки / формулы');
    for (const sheet of workbook.SheetNames || []) {
      const ws = workbook.Sheets[sheet];
      if (!ws) continue;
      const h = findHeaderRow(ws);
      if (!h) continue;
      const groups = pairGroups(ws, h);
      const calStart = firstCalendarColumn(ws, h);
      if (!groups.length || calStart == null) continue;
      for (const g of groups) {
        const mismatches = [];
        for (let c = h.month + 1; c < calStart; c++) {
          const label = headerText(ws, h, c);
          if (isManualInputHeader(label)) continue;
          const rowCells = g.map(x => ({ r: x.r, cell: cellAt(ws, x.r, c) })).filter(x => x.cell && x.cell.v != null);
          if (rowCells.length < 2) continue;
          const formulaRows = rowCells.filter(x => x.cell.f && formulaReferencesOwnRow(x.cell.f, x.r));
          if (!formulaRows.length) continue;
          const constants = rowCells.filter(x => !x.cell.f && typeof x.cell.v === 'number' && Number.isFinite(x.cell.v));
          for (const x of constants) mismatches.push(`${colName(c)}${x.r}`);
        }
        const cells = [...new Set(mismatches)];
        if (!cells.length) continue;
        add(issues, issue(
          S.CHECK, 'Парные строки / формулы', sheet, cells.join(', '), g.map(x => `${x.platformRaw} — ${x.month}`).join(' | '),
          `В парных месячных строках «${g[0].platform}» производные поля рассчитываются неодинаково: часть формулами, часть введена числами вручную.`,
          'Сравниваются только одинаковые площадка/формат/таргетинг/unit type и только поля, для которых соседняя строка доказывает расчётную формульную логику.',
          'Проверьте перечисленные KPI-ячейки. Если ручной override не предусмотрен, восстановите формулы по парной строке.',
          g.map(x => `строка ${x.r}`).join(', ')
        ));
      }
    }
    return issues;
  }

  // ---------------------------------------------------------------------------
  // 3. Если G40:G46 уже признан битым диапазоном, вторичная «аномалия G41» не нужна.
  // ---------------------------------------------------------------------------
  function expandRefs(value) {
    const out = new Set();
    const re = /([A-Z]{1,3}\d+)(?::([A-Z]{1,3}\d+))?/gi;
    let m;
    while ((m = re.exec(String(value || '')))) {
      const a = core.decodeCell(m[1].toUpperCase());
      const b = core.decodeCell((m[2] || m[1]).toUpperCase());
      if (!a || !b) continue;
      const r1 = Math.min(a.r, b.r), r2 = Math.max(a.r, b.r), c1 = Math.min(a.c, b.c), c2 = Math.max(a.c, b.c);
      if ((r2 - r1 + 1) * (c2 - c1 + 1) > 500) continue;
      for (let r = r1; r <= r2; r++) for (let c = c1; c <= c2; c++) out.add(core.encodeCell(r, c));
    }
    return out;
  }
  function suppressNoiseInsideBrokenRanges(issues) {
    const broken = new Map();
    for (const x of issues || []) {
      if (!/(формула excel|ошибка excel)/iu.test(String(x.type || ''))) continue;
      if (!/(#REF!|бит\w* ссыл|ошибк)/iu.test(`${x.problem || ''} ${x.value || ''}`)) continue;
      if (!broken.has(x.sheet)) broken.set(x.sheet, new Set());
      for (const a of expandRefs(`${x.cell || ''} ${x.related || ''}`)) broken.get(x.sheet).add(a);
    }
    return (issues || []).filter(x => {
      if (!/(структура формул|формул\w* паттерн|ручное значение среди формул)/iu.test(`${x.type || ''} ${x.problem || ''}`)) return true;
      const set = broken.get(x.sheet);
      if (!set || !set.size) return true;
      return ![...expandRefs(x.cell)].some(a => set.has(a));
    });
  }

  // ---------------------------------------------------------------------------
  // 4. Комментарии: исправляем типичный UTF-8 mojibake и отделяем внутренние
  // аудиторские заметки от обычных рабочих комментариев шаблона.
  // ---------------------------------------------------------------------------
  function repairMojibake(value) {
    const s = String(value || '');
    if (!/[ÐÑ][\u0080-\u00BF]/u.test(s)) return s;
    try {
      const bytes = Uint8Array.from(Array.from(s, ch => ch.charCodeAt(0) & 255));
      const decoded = new TextDecoder('utf-8', { fatal: true }).decode(bytes);
      if (/[А-Яа-яЁё]/u.test(decoded)) return decoded;
    } catch (_) {}
    return s;
  }
  function commentText(c) {
    let s = repairMojibake(String((c && ((c.t != null && c.t) || (c.text != null && c.text))) || '')).trim();
    const marker = s.lastIndexOf('Комментарий:');
    if (marker >= 0) s = s.slice(marker + 'Комментарий:'.length).trim();
    return s;
  }
  function rebuildWorkbookComments(workbook, issues) {
    issues = (issues || []).filter(x => !/^Комментарии Excel(?:\s*\/|$)/u.test(String(x.type || '')));
    for (const sheet of workbook.SheetNames || []) {
      const ws = workbook.Sheets[sheet];
      if (!ws) continue;
      const seen = new Set(), all = [];
      for (const e of entries(ws)) {
        const comments = Array.isArray(e.cell.c) ? e.cell.c : [];
        for (const c of comments) {
          const text = commentText(c);
          const author = repairMojibake(String(c && c.a || ''));
          const key = `${e.addr}|${text}|${author}`;
          if (seen.has(key)) continue;
          seen.add(key);
          all.push({ cell: e.addr, text, author });
        }
      }
      if (!all.length) continue;
      const service = all.filter(h => /(аудит|audit|провер|risk|риск|todo|исправ|ошиб|внутрен|служеб)/iu.test(h.text));
      const ordinary = all.filter(h => !service.includes(h));
      if (service.length) {
        add(issues, issue(
          S.CHECK, 'Комментарии Excel / служебные', sheet,
          [...new Set(service.map(h => h.cell))].slice(0, 30).join(', '),
          service.slice(0, 6).map(h => `${h.cell}: ${h.text.slice(0, 180)}`).join(' | '),
          `Найдены внутренние/аудиторские комментарии Excel: ${service.length}.`,
          'Служебные заметки с пометками «АУДИТ», «проверить», «ошибка», «risk» и аналогичными формулировками не должны случайно уйти клиенту.',
          'Просмотрите перечисленные комментарии и удалите внутренние заметки перед отправкой клиенту.'
        ));
      }
      if (ordinary.length) {
        add(issues, issue(
          S.CHECK, 'Комментарии Excel / прочие', sheet,
          [...new Set(ordinary.map(h => h.cell))].slice(0, 30).join(', '),
          ordinary.slice(0, 5).map(h => `${h.cell}: ${h.text.slice(0, 140)}`).join(' | '),
          `В книге есть обычные комментарии Excel: ${ordinary.length}.`,
          'Комментарий может быть намеренной документацией шаблона, поэтому это не ошибка, но перед клиентской отправкой наличие комментариев нужно подтвердить.',
          'Просмотрите комментарии и оставьте только те, которые действительно должны присутствовать в клиентской версии.'
        ));
      }
    }
    return issues;
  }

  // ---------------------------------------------------------------------------
  // 5. _xlfn.* пользователь решил не контролировать вообще.
  // 6. Убираем дубли одной и той же текстовой первопричины.
  // ---------------------------------------------------------------------------
  function dropXlfnNoise(issues) {
    return (issues || []).filter(x => !/_xlfn\./i.test(`${x.problem || ''} ${x.value || ''} ${x.why || ''} ${x.recommendation || ''}`));
  }
  function textRoot(x) {
    const s = `${x.problem || ''} ${x.value || ''} ${x.recommendation || ''}`;
    if (/cost\s+per\s+unt/i.test(s)) return 'cost-per-unt';
    if (/видео\s+ролик|видеоролик/iu.test(s)) return 'video-word';
    return '';
  }
  function dedupeKnownTextRoots(issues) {
    const seen = new Set(), out = [];
    for (const x of issues || []) {
      const root = textRoot(x);
      if (!root) { out.push(x); continue; }
      const key = `${x.sheet}|${x.cell}|${root}`;
      if (seen.has(key)) continue;
      seen.add(key);
      out.push(x);
    }
    return out;
  }

  function finish(result) {
    const seen = new Set();
    result.issues = (result.issues || []).filter(x => {
      const k = issueKey(x);
      if (seen.has(k)) return false;
      seen.add(k);
      return true;
    });
    const weight = { [S.CRITICAL]: 0, [S.CHECK]: 1, [S.TEXT]: 2 };
    result.issues.sort((a, b) => (weight[a.severity] - weight[b.severity]) || String(a.sheet).localeCompare(String(b.sheet), 'ru') || String(a.cell).localeCompare(String(b.cell), 'ru'));
    result.counts = {
      critical: result.issues.filter(x => x.severity === S.CRITICAL).length,
      check: result.issues.filter(x => x.severity === S.CHECK).length,
      text: result.issues.filter(x => x.severity === S.TEXT).length
    };
    result.status = result.issues.length ? 'Нужно исправить' : 'Можно отправлять клиенту';
    return result;
  }

  core.runAllChecks = function (workbook, options) {
    const result = originalRun(workbook, options || {});
    result.issues = dropXlfnNoise(result.issues || []);
    result.issues = rebuildCalendarChecks(workbook, result.issues);
    result.issues = rebuildPairedFormulaValueChecks(workbook, result.issues);
    result.issues = suppressNoiseInsideBrokenRanges(result.issues);
    result.issues = rebuildWorkbookComments(workbook, result.issues);
    result.issues = dedupeKnownTextRoots(result.issues);
    return finish(result);
  };

  core.__reliabilityRulesPatched = true;
  return core;
});
