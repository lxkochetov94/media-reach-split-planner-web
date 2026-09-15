(function (root, factory) {
  const api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.MPChecks = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  const SEVERITY = {
    CRITICAL: 'Критическая ошибка',
    CHECK: 'Нужно проверить',
    TEXT: 'Текстовое замечание'
  };

  const ERROR_TOKENS = ['#REF!', '#DIV/0!', '#VALUE!', '#N/A', '#NAME?', '#NUM!', '#NULL!'];
  const TYPO_RULES = [
    [/(^|\s)кодиционер(?=$|[\s,.;:!?])/giu, 'кондиционер'],
    [/(^|\s)промостраниц(?=$|[\s,.;:!?])/giu, 'промостраниц'],
    [/(^|\s)оффлайнн(?=$|[\s,.;:!?])/giu, 'офлайн'],
    [/(^|\s)таргеттинг(?=$|[\s,.;:!?])/giu, 'таргетинг']
  ];

  const PLATFORM_ALIASES = {
    rutube: ['rutube', 'rutube.ru'],
    vk: ['vk', 'вк', 'vkontakte', 'вконтакте'],
    hybrid: ['hybrid'],
    ozon: ['ozon'],
    yandex: ['yandex', 'яндекс'],
    telegram: ['telegram', 'телеграм', 'tg'],
    'digital alliance': ['digital alliance'],
    'first data': ['first data'],
    'adfox': ['adfox'],
    'advmusic': ['advmusic'],
    'adspector': ['adspector']
  };

  const MONTHS = {
    'янв': 1, 'январ': 1, 'января': 1,
    'фев': 2, 'феврал': 2, 'февраля': 2,
    'мар': 3, 'март': 3, 'марта': 3,
    'апр': 4, 'апрел': 4, 'апреля': 4,
    'май': 5, 'мая': 5,
    'июн': 6, 'июня': 6,
    'июл': 7, 'июля': 7,
    'авг': 8, 'август': 8, 'августа': 8,
    'сен': 9, 'сент': 9, 'сентябр': 9, 'сентября': 9,
    'окт': 10, 'октябр': 10, 'октября': 10,
    'ноя': 11, 'нояб': 11, 'ноябр': 11, 'ноября': 11,
    'дек': 12, 'декабр': 12, 'декабря': 12
  };

  const HEADER_SYNONYMS = {
    impressions: ['impressions', 'imps', 'показы', 'показов', 'impression'],
    clicks: ['clicks', 'клики', 'кликов', 'click'],
    ctr: ['ctr'],
    budget: ['budget', 'budget net', 'budget (net)', 'бюджет', 'media net', 'total media net', 'cost', 'затраты'],
    cpm: ['cpm'],
    cpc: ['cpc'],
    reach: ['reach', 'охват', 'unique users', 'уникальные пользователи'],
    frequency: ['frequency', 'freq', 'частота'],
    views: ['views', 'просмотры', 'video views', 'view'],
    vtr: ['vtr'],
    platform: ['site', 'platform', 'площадка', 'publisher', 'placement'],
    format: ['format', 'формат'],
    audience: ['target audience', 'audience', 'ца', 'targeting', 'targetings', 'таргетинг', 'аудитория'],
    month: ['month', 'месяц'],
    period: ['period', 'период'],
    start: ['start', 'start date', 'дата начала', 'начало'],
    end: ['end', 'end date', 'дата окончания', 'конец'],
    days: ['days', 'day', 'дни', 'дней', 'кол-во дней', 'количество дней', 'active days']
  };

  function normalizeText(value) {
    return String(value == null ? '' : value)
      .replace(/\u00A0/g, ' ')
      .replace(/[‐‑‒–—―]/g, '-')
      .replace(/\s+/g, ' ')
      .trim()
      .toLowerCase();
  }

  function compactText(value) {
    return normalizeText(value).replace(/[«»"'`]/g, '').replace(/\s*([,;:/+()-])\s*/g, '$1');
  }

  function colToNumber(col) {
    let n = 0;
    for (const ch of col.toUpperCase()) n = n * 26 + ch.charCodeAt(0) - 64;
    return n - 1;
  }

  function numberToCol(n) {
    let s = '';
    n += 1;
    while (n > 0) {
      const r = (n - 1) % 26;
      s = String.fromCharCode(65 + r) + s;
      n = Math.floor((n - 1) / 26);
    }
    return s;
  }

  function decodeCell(addr) {
    const m = /^([A-Z]+)(\d+)$/i.exec(addr || '');
    return m ? { c: colToNumber(m[1]), r: Number(m[2]) - 1 } : null;
  }

  function encodeCell(r, c) {
    return `${numberToCol(c)}${r + 1}`;
  }

  function decodeRange(ref) {
    const parts = String(ref || 'A1:A1').split(':');
    const a = decodeCell(parts[0]);
    const b = decodeCell(parts[1] || parts[0]);
    return a && b ? { s: a, e: b } : { s: { r: 0, c: 0 }, e: { r: 0, c: 0 } };
  }

  function actualCellEntries(ws) {
    return Object.keys(ws || {})
      .filter(k => k && k[0] !== '!' && /^[A-Z]{1,3}\d+$/i.test(k))
      .map(addr => ({ addr: addr.toUpperCase(), pos: decodeCell(addr), cell: ws[addr] }))
      .filter(x => x.pos && x.cell && (x.cell.v != null || x.cell.f));
  }

  function actualBounds(ws) {
    const entries = actualCellEntries(ws);
    if (!entries.length) return { s:{r:0,c:0}, e:{r:0,c:0}, entries };
    let minR=Infinity,minC=Infinity,maxR=-1,maxC=-1;
    for (const e of entries) { minR=Math.min(minR,e.pos.r); minC=Math.min(minC,e.pos.c); maxR=Math.max(maxR,e.pos.r); maxC=Math.max(maxC,e.pos.c); }
    return { s:{r:minR,c:minC}, e:{r:maxR,c:maxC}, entries };
  }

  function getCellText(cell) {
    if (!cell) return '';
    if (cell.w != null && cell.w !== '') return String(cell.w);
    if (cell.v instanceof Date) return cell.v.toISOString().slice(0, 10);
    if (cell.v == null) return '';
    return String(cell.v);
  }

  function isNumberCell(cell) {
    return !!cell && typeof cell.v === 'number' && Number.isFinite(cell.v);
  }

  function createIssue(severity, type, sheet, cell, value, problem, why, recommendation, related) {
    return {
      severity,
      type,
      sheet: sheet || '',
      cell: cell || '',
      value: value == null ? '' : String(value),
      problem: problem || '',
      why: why || '',
      recommendation: recommendation || 'Проверьте вручную.',
      related: related || '',
      fixStatus: ''
    };
  }

  function pushIssue(state, issue) {
    const key = [issue.severity, issue.type, issue.sheet, issue.cell, issue.problem, issue.related].join('|');
    if (state.keys.has(key)) return;
    state.keys.add(key);
    state.issues.push(issue);
  }

  function isExcludedWord(word, exclusions) {
    const n = normalizeText(word);
    return exclusions.some(x => normalizeText(x) === n);
  }

  function extractSheetRefs(formula) {
    const refs = [];
    const re = /(?:'((?:[^']|'')+)'|([A-Za-zА-Яа-яЁё0-9_ .-]+))!\$?[A-Z]{1,3}\$?\d+/g;
    let m;
    while ((m = re.exec(formula || ''))) refs.push((m[1] || m[2] || '').replace(/''/g, "'").trim());
    return refs.filter(Boolean);
  }

  function normalizeFormulaShape(formula, addr) {
    if (!formula) return '';
    const origin = decodeCell(addr) || { r: 0, c: 0 };
    return String(formula)
      .replace(/\s+/g, '')
      .replace(/((?:'((?:[^']|'')+)'|([A-Za-zА-Яа-яЁё0-9_ .-]+))!)?(\$?)([A-Z]{1,3})(\$?)(\d+)/g,
        function (_, fullSheet, quotedSheet, plainSheet, absCol, col, absRow, row) {
          const c = colToNumber(col);
          const r = Number(row) - 1;
          const sheet = (quotedSheet || plainSheet || '').replace(/''/g, "'");
          const colToken = absCol ? `C$${c}` : `C${c - origin.c >= 0 ? '+' : ''}${c - origin.c}`;
          const rowToken = absRow ? `R$${r}` : `R${r - origin.r >= 0 ? '+' : ''}${r - origin.r}`;
          return `${sheet ? `[${normalizeText(sheet)}]!` : ''}${colToken}${rowToken}`;
        })
      .toUpperCase();
  }

  function parseSimpleSum(formula) {
    const f = String(formula || '').replace(/\s+/g, '');
    const m = /^SUM\((?:(?:'((?:[^']|'')+)'|([^!'\[\]]+))!)?(\$?[A-Z]{1,3}\$?\d+):(\$?[A-Z]{1,3}\$?\d+)\)$/i.exec(f);
    if (!m) return null;
    return { sheet: (m[1] || m[2] || '').replace(/''/g, "'"), start: m[3].replace(/\$/g, ''), end: m[4].replace(/\$/g, '') };
  }

  function sumRange(workbook, currentSheet, parsed) {
    const sheetName = parsed.sheet || currentSheet;
    const ws = workbook.Sheets && workbook.Sheets[sheetName];
    if (!ws) return null;
    const a = decodeCell(parsed.start), b = decodeCell(parsed.end);
    if (!a || !b) return null;
    let sum = 0, count = 0;
    for (let r = Math.min(a.r, b.r); r <= Math.max(a.r, b.r); r++) {
      for (let c = Math.min(a.c, b.c); c <= Math.max(a.c, b.c); c++) {
        const cell = ws[encodeCell(r, c)];
        if (isNumberCell(cell)) { sum += cell.v; count++; }
      }
    }
    return { sum, count, sheetName };
  }

  function approxEqual(a, b, relTol, absTol) {
    if (!Number.isFinite(a) || !Number.isFinite(b)) return true;
    const diff = Math.abs(a - b);
    return diff <= Math.max(absTol || 0, Math.max(Math.abs(a), Math.abs(b)) * (relTol || 0));
  }

  function extractDateTokensFromText(text) {
    const tokens = [];
    const s = String(text || '');
    const re = /\b(0?[1-9]|[12]\d|3[01])[.\/-](0?[1-9]|1[0-2])(?:[.\/-](20\d{2}|19\d{2}))?\b/g;
    let m;
    while ((m = re.exec(s))) tokens.push({ day: Number(m[1]), month: Number(m[2]), year: m[3] ? Number(m[3]) : null, raw: m[0] });
    const reRu = /(0?[1-9]|[12]\d|3[01])\s+(янв(?:аря)?|фев(?:раля)?|мар(?:та)?|апр(?:еля)?|ма[йя]|июн(?:я)?|июл(?:я)?|авг(?:уста)?|сент?(?:ября)?|окт(?:ября)?|нояб?(?:ря)?|дек(?:абря)?)/giu;
    while ((m = reRu.exec(s))) {
      const key = normalizeText(m[2]).replace(/ь$/,'');
      const found = Object.keys(MONTHS).find(k => key.startsWith(k));
      if (found) tokens.push({ day: Number(m[1]), month: MONTHS[found], year: null, raw: m[0] });
    }
    return tokens;
  }

  function dateTokenKey(t) {
    return `${t.year || '*'}-${String(t.month).padStart(2,'0')}-${String(t.day).padStart(2,'0')}`;
  }

  function parseDateRange(text) {
    const s = String(text || '');
    const all = extractDateTokensFromText(s);
    if (all.length < 2) return null;
    const a = all[0], b = all[1];
    if (!a.year || !b.year) return null;
    const start = new Date(Date.UTC(a.year, a.month - 1, a.day));
    const end = new Date(Date.UTC(b.year, b.month - 1, b.day));
    if (Number.isNaN(start.getTime()) || Number.isNaN(end.getTime())) return null;
    return { start, end, a, b };
  }

  function collectWorkbookIndex(workbook) {
    const cells = [];
    const bySheet = {};
    const textParts = [];
    const dateTokens = new Set();
    const sheetNames = workbook.SheetNames || Object.keys(workbook.Sheets || {});
    for (const sheetName of sheetNames) {
      const ws = workbook.Sheets[sheetName];
      if (!ws) continue;
      const sheetCells = [];
      for (const entry of actualCellEntries(ws)) {
        const { addr, pos, cell } = entry;
        const r = pos.r, c = pos.c;
        const text = getCellText(cell);
        const item = { sheet: sheetName, addr, r, c, cell, text, formula: cell.f || '' };
        cells.push(item); sheetCells.push(item);
        if (text) {
          textParts.push(text);
          extractDateTokensFromText(text).forEach(t => {
            dateTokens.add(dateTokenKey(t));
            if (t.year) dateTokens.add(`*-${String(t.month).padStart(2,'0')}-${String(t.day).padStart(2,'0')}`);
          });
        }
        if (cell.v instanceof Date) {
          const d = cell.v;
          dateTokens.add(`${d.getUTCFullYear()}-${String(d.getUTCMonth()+1).padStart(2,'0')}-${String(d.getUTCDate()).padStart(2,'0')}`);
          dateTokens.add(`*-${String(d.getUTCMonth()+1).padStart(2,'0')}-${String(d.getUTCDate()).padStart(2,'0')}`);
        }
      }
      bySheet[sheetName] = sheetCells;
    }
    return { cells, bySheet, searchText: normalizeText(textParts.join('\n')), dateTokens, sheetNames };
  }

  function checkTechnical(workbook, index, state, rawInfo) {
    const existingSheets = new Set(index.sheetNames.map(normalizeText));
    for (const item of index.cells) {
      const { cell, formula, sheet, addr, text } = item;
      const errorText = cell && cell.t === 'e' ? (cell.w || cell.v || 'Ошибка Excel') : '';
      if (errorText || ERROR_TOKENS.includes(String(text).trim().toUpperCase())) {
        pushIssue(state, createIssue(SEVERITY.CRITICAL, 'Ошибка Excel', sheet, addr, text, `В ячейке сохранена ошибка Excel: ${errorText || text}.`, 'Это технически некорректное значение книги.', 'Проверьте исходную формулу или ссылку.'));
      }
      if (!formula) continue;

      const upper = formula.toUpperCase();
      const formulaErrors = ERROR_TOKENS.filter(t => upper.includes(t));
      if (formulaErrors.length) {
        pushIssue(state, createIssue(SEVERITY.CRITICAL, 'Формула Excel', sheet, addr, `=${formula}`, `Формула содержит ${[...new Set(formulaErrors)].join(', ')}.`, 'Ошибка находится в тексте формулы и может быть скрыта внутри неактивной ветки IF/IFERROR.', 'Проверьте все ссылки внутри формулы, даже если текущее отображаемое значение выглядит корректно.'));
      }

      for (const refSheet of extractSheetRefs(formula)) {
        if (!existingSheets.has(normalizeText(refSheet)) && !refSheet.includes('[')) {
          pushIssue(state, createIssue(SEVERITY.CRITICAL, 'Связи между листами', sheet, addr, `=${formula}`, `Формула ссылается на отсутствующий лист «${refSheet}».`, 'Такая ссылка не может быть корректно рассчитана внутри текущей книги.', 'Проверьте имя листа и ссылку.', refSheet));
        }
      }

      if (/\[[^\]]+\.(xlsx?|xlsm|xlsb)\]/i.test(formula)) {
        pushIssue(state, createIssue(SEVERITY.CHECK, 'Внешняя ссылка', sheet, addr, `=${formula}`, 'Формула содержит ссылку на внешний Excel-файл.', 'Значение зависит от другой книги и может быть устаревшим или случайно перенесённым из другого медиаплана.', 'Проверьте, нужна ли внешняя связь и относится ли файл к текущему бренду.'));
      }

      const sum = parseSimpleSum(formula);
      if (sum) {
        const target = decodeCell(addr), a = decodeCell(sum.start), b = decodeCell(sum.end);
        if ((!sum.sheet || normalizeText(sum.sheet) === normalizeText(sheet)) && target && a && b && target.r >= Math.min(a.r,b.r) && target.r <= Math.max(a.r,b.r) && target.c >= Math.min(a.c,b.c) && target.c <= Math.max(a.c,b.c)) {
          pushIssue(state, createIssue(SEVERITY.CRITICAL, 'Формула SUM', sheet, addr, `=${formula}`, 'Диапазон SUM включает саму итоговую ячейку.', 'Это создаёт циклическую ссылку или некорректный итог.', 'Исправьте границы диапазона суммирования.'));
        }
        if (typeof cell.v === 'number') {
          const calculated = sumRange(workbook, sheet, sum);
          if (calculated && calculated.count > 0 && !approxEqual(cell.v, calculated.sum, 1e-8, 0.0001)) {
            pushIssue(state, createIssue(SEVERITY.CRITICAL, 'Проверка суммы', sheet, addr, `=${formula} → ${cell.v}`, 'Сохранённый итог SUM не совпадает с суммой числовых ячеек диапазона.', 'Это математически проверяемое расхождение в текущем файле.', 'Проверьте диапазон и значения строк.', `${calculated.sheetName}!${sum.start}:${sum.end}`));
          }
        }
      }
    }

    if (rawInfo && Array.isArray(rawInfo.definedNames) && rawInfo.definedNames.length) {
      const broken = rawInfo.definedNames.filter(x => ERROR_TOKENS.some(t => String(x.ref || '').toUpperCase().includes(t)));
      if (broken.length) {
        const formulaTokens = new Set();
        for (const c of index.cells) if (c.formula) {
          const toks = String(c.formula).match(/[A-Za-zА-Яа-яЁё_\\][A-Za-zА-Яа-яЁё0-9_.\\]*/gu) || [];
          toks.forEach(t => formulaTokens.add(normalizeText(t)));
        }
        const usedBroken = broken.filter(n => n.name && formulaTokens.has(normalizeText(n.name)));
        const sev = usedBroken.length ? SEVERITY.CRITICAL : SEVERITY.CHECK;
        pushIssue(state, createIssue(sev, 'Именованные диапазоны', 'Книга', '', '', `Обнаружено ${broken.length} именованных диапазонов с битыми ссылками${usedBroken.length ? `; ${usedBroken.length} из них используются в формулах` : ''}.`, usedBroken.length ? 'Используемая битая именованная ссылка может влиять на расчёты.' : 'Неиспользуемые битые имена часто являются техническим мусором старых шаблонов, но требуют проверки.', usedBroken.length ? 'Исправьте используемые битые имена; остальные можно очистить отдельно.' : 'Проверьте Диспетчер имён Excel; не исправляйте автоматически без необходимости.'));
      }
    }
    if (rawInfo && rawInfo.externalLinks && rawInfo.externalLinks.length) {
      pushIssue(state, createIssue(SEVERITY.CHECK, 'Внешние связи книги', 'Книга', '', rawInfo.externalLinks.join('; '), `В структуре .xlsx найдено внешних связей: ${rawInfo.externalLinks.length}.`, 'Внешняя связь может быть намеренной, но перед отправкой клиенту её необходимо проверить.', 'Проверьте, относятся ли внешние книги к текущему медиаплану.'));
    }
  }

  function escapeRegExp(s) { return String(s).replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); }

  function checkText(index, state, exclusions) {
    const platformForms = {};
    for (const item of index.cells) {
      if (typeof item.cell.v !== 'string' && item.cell.t !== 's' && typeof item.text !== 'string') continue;
      const raw = item.text;
      if (!raw) continue;
      const visible = raw.replace(/\r/g, '');
      const trimmed = visible.trim();
      const common = [item.sheet, item.addr, raw];

      if (visible !== trimmed) pushIssue(state, createIssue(SEVERITY.TEXT, 'Пробелы', ...common, 'Есть пробел в начале или в конце текста.', 'Лишние пробелы мешают единообразию и могут ломать сравнение строк.', 'Удалите ведущий/концевой пробел.'));
      if (/ {2,}/.test(visible.replace(/\n/g, ' '))) pushIssue(state, createIssue(SEVERITY.TEXT, 'Пробелы', ...common, 'Обнаружены двойные или множественные пробелы.', 'Это типичная техническая опечатка.', 'Оставьте один пробел.'));
      if (/\s+[,.!?;:]/.test(visible)) pushIssue(state, createIssue(SEVERITY.TEXT, 'Пунктуация', ...common, 'Есть пробел перед знаком препинания.', 'Оформление текста выглядит неаккуратно.', 'Удалите пробел перед знаком препинания.'));
      if (/[,:;!?](?=[А-Яа-яЁёA-Za-z])/u.test(visible)) pushIssue(state, createIssue(SEVERITY.TEXT, 'Пунктуация', ...common, 'После знака препинания нет пробела.', 'В обычном тексте после такого знака должен быть пробел.', 'Добавьте пробел, если это не специальная запись или код.'));

      const repeat = /(?:^|[^A-Za-zА-Яа-яЁё])([A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё-]{1,})\s+\1(?=$|[^A-Za-zА-Яа-яЁё])/iu.exec(visible);
      if (repeat && !isExcludedWord(repeat[1], exclusions)) pushIssue(state, createIssue(SEVERITY.TEXT, 'Повтор слова', ...common, `Слово «${repeat[1]}» повторено подряд.`, 'Вероятна случайная тавтология/дублирование.', 'Удалите лишний повтор, если он не намеренный.'));

      const tokens = visible.match(/[A-Za-zА-Яа-яЁё][A-Za-zА-Яа-яЁё0-9-]*/gu) || [];
      for (const token of tokens) {
        if (/[A-Za-z]/.test(token) && /[А-Яа-яЁё]/u.test(token) && !isExcludedWord(token, exclusions)) {
          pushIssue(state, createIssue(SEVERITY.TEXT, 'Смешение алфавитов', ...common, `В слове «${token}» смешаны латинские и кириллические буквы.`, 'Частая причина — случайно введённая латинская буква внутри русского слова.', 'Проверьте написание слова.'));
          break;
        }
      }
      if (/[\u0000-\u0008\u000B\u000C\u000E-\u001F\uFFFD]/.test(visible)) pushIssue(state, createIssue(SEVERITY.TEXT, 'Странные символы', ...common, 'Обнаружен непечатаемый или повреждённый символ.', 'Такой символ может быть следствием копирования из внешнего источника.', 'Удалите или замените символ.'));

      for (const [re, suggestion] of TYPO_RULES) {
        re.lastIndex = 0;
        if (re.test(visible)) pushIssue(state, createIssue(SEVERITY.TEXT, 'Очевидная опечатка', ...common, `Возможная опечатка. Ожидаемый вариант: «${suggestion}».`, 'Слово совпало с локальным словарём частых опечаток.', 'Проверьте и исправьте написание.'));
      }

      const items = visible.split(/[;,\n]+/).map(x => normalizeText(x)).filter(x => x.length >= 3);
      const seen = new Set();
      const dupes = new Set();
      for (const x of items) { if (seen.has(x)) dupes.add(x); else seen.add(x); }
      if (dupes.size) pushIssue(state, createIssue(SEVERITY.TEXT, 'Дубли таргетинга/ключевых слов', ...common, `В одной ячейке повторяются элементы: ${Array.from(dupes).slice(0,5).join(', ')}.`, 'Повтор может быть случайным дублем списка.', 'Проверьте список и удалите лишние повторы.'));

      const nt = normalizeText(visible);
      for (const [canonical, aliases] of Object.entries(PLATFORM_ALIASES)) {
        if (aliases.some(a => nt.includes(normalizeText(a)))) {
          if (!platformForms[canonical]) platformForms[canonical] = new Map();
          const exactMatches = visible.match(new RegExp(aliases.map(escapeRegExp).join('|'), 'giu')) || [];
          exactMatches.forEach(m => {
            const k = m.trim();
            if (!platformForms[canonical].has(k)) platformForms[canonical].set(k, []);
            platformForms[canonical].get(k).push(`${item.sheet}!${item.addr}`);
          });
        }
      }
    }

    for (const [canonical, forms] of Object.entries(platformForms)) {
      const unique = Array.from(forms.keys());
      const caseInsensitive = new Set(unique.map(x => x.toLowerCase()));
      if (unique.length > 1 && (caseInsensitive.size > 1 || unique.length > 1)) {
        const related = unique.map(x => `${x}: ${(forms.get(x) || []).slice(0,3).join(', ')}`).join('; ');
        pushIssue(state, createIssue(SEVERITY.TEXT, 'Единообразие названий', 'Книга', '', unique.join(' / '), `Площадка «${canonical}» встречается в разных вариантах написания.`, 'Разные варианты в одном клиентском файле выглядят непоследовательно.', 'Выберите единый вариант написания по карточке бренда или шаблону LAB.', related));
      }
    }
  }

  function checkFormulaPatterns(workbook, index, state) {
    for (const sheetName of index.sheetNames) {
      const ws = workbook.Sheets[sheetName];
      if (!ws) continue;
      const bounds = actualBounds(ws);
      const entries = bounds.entries;

      for (const entry of entries) {
          const c = entry.pos.c, r = entry.pos.r;
          if (r <= bounds.s.r || r >= bounds.e.r) continue;
          const prevAddr = encodeCell(r - 1, c), addr = encodeCell(r, c), nextAddr = encodeCell(r + 1, c);
          const prev = ws[prevAddr], cur = ws[addr], next = ws[nextAddr];
          if (!cur) continue;
          if (cur.f && prev && prev.f && next && next.f) {
            const p = normalizeFormulaShape(prev.f, prevAddr), n = normalizeFormulaShape(next.f, nextAddr), x = normalizeFormulaShape(cur.f, addr);
            if (p === n && x !== p) pushIssue(state, createIssue(SEVERITY.CHECK, 'Структура формул', sheetName, addr, `=${cur.f}`, 'Формула отличается от одинаковой структуры формул сверху и снизу.', 'Это может быть намеренное исключение, но также типичный признак съехавшей ссылки после копирования строки.', 'Сравните ссылки с соседними строками.', `${prevAddr}, ${nextAddr}`));
          }
          if (!cur.f && isNumberCell(cur) && prev && prev.f && next && next.f) {
            const p = normalizeFormulaShape(prev.f, prevAddr), n = normalizeFormulaShape(next.f, nextAddr);
            if (p === n) pushIssue(state, createIssue(SEVERITY.CHECK, 'Ручное значение среди формул', sheetName, addr, cur.v, 'В колонке между двумя однотипными формулами стоит число, введённое вручную.', 'Это может быть согласованный хардкод, но требует отдельной проверки.', 'Проверьте источник значения и необходимость ручного ввода.', `${prevAddr}, ${nextAddr}`));
          }
      }

      for (const entry of entries) {
          const c = entry.pos.c, r = entry.pos.r;
          if (c <= bounds.s.c || c >= bounds.e.c) continue;
          const leftAddr = encodeCell(r, c - 1), addr = encodeCell(r, c), rightAddr = encodeCell(r, c + 1);
          const left = ws[leftAddr], cur = ws[addr], right = ws[rightAddr];
          if (!cur || !cur.f || !left || !left.f || !right || !right.f) continue;
          const l = normalizeFormulaShape(left.f, leftAddr), x = normalizeFormulaShape(cur.f, addr), rr = normalizeFormulaShape(right.f, rightAddr);
          if (l === rr && x !== l && /^SUM\(/i.test(cur.f) && /^SUM\(/i.test(left.f) && /^SUM\(/i.test(right.f)) {
            pushIssue(state, createIssue(SEVERITY.CHECK, 'Диапазон SUM', sheetName, addr, `=${cur.f}`, 'Диапазон SUM отличается от однотипных итогов слева и справа.', 'В месячных/периодных блоках это может означать пропущенную или лишнюю строку в диапазоне.', 'Сравните границы диапазона с соседними итоговыми колонками.', `${leftAddr}, ${rightAddr}`));
          }
      }
    }
  }

  function headerKey(text) {
    const n = normalizeText(text).replace(/[()]/g,'').replace(/\s+/g,' ');
    for (const [key, names] of Object.entries(HEADER_SYNONYMS)) {
      if (names.some(x => n === normalizeText(x) || n.includes(normalizeText(x)))) return key;
    }
    return null;
  }

  function detectTables(workbook) {
    const tables = [];
    for (const sheetName of workbook.SheetNames || []) {
      const ws = workbook.Sheets[sheetName]; if (!ws) continue;
      const bounds = actualBounds(ws);
      const headerRows = [];
      const rows = new Map();
      for (const e of bounds.entries) { if (!rows.has(e.pos.r)) rows.set(e.pos.r, []); rows.get(e.pos.r).push(e); }
      for (const [r, entries] of rows) {
        const cols = {};
        for (const e of entries) {
          const key = headerKey(getCellText(e.cell)); if (key && cols[key] == null) cols[key] = e.pos.c;
        }
        if (Object.keys(cols).length >= 3 || (cols.start != null && cols.end != null && cols.days != null)) headerRows.push({ r, cols });
      }
      headerRows.sort((a,b)=>a.r-b.r);
      for (let i = 0; i < headerRows.length; i++) {
        const h = headerRows[i];
        const nextR = i + 1 < headerRows.length ? headerRows[i + 1].r - 1 : Math.min(bounds.e.r, h.r + 150);
        tables.push({ sheetName, headerRow: h.r, endRow: nextR, cols: h.cols });
      }
    }
    return tables;
  }

  function numericValue(ws, r, c) {
    if (c == null) return null;
    const cell = ws[encodeCell(r,c)];
    return isNumberCell(cell) ? cell.v : null;
  }

  function compareRatio(stored, ratio) {
    if (!Number.isFinite(stored) || !Number.isFinite(ratio)) return true;
    const candidates = [ratio, ratio * 100];
    return candidates.some(x => approxEqual(stored, x, 0.03, Math.abs(x) < 2 ? 0.0025 : 0.2));
  }

  function checkMediaMath(workbook, state) {
    const tables = detectTables(workbook);
    for (const table of tables) {
      const ws = workbook.Sheets[table.sheetName], c = table.cols;
      for (let r = table.headerRow + 1; r <= table.endRow; r++) {
        const imp = numericValue(ws,r,c.impressions), clicks = numericValue(ws,r,c.clicks), ctr = numericValue(ws,r,c.ctr);
        const budget = numericValue(ws,r,c.budget), cpm = numericValue(ws,r,c.cpm), cpc = numericValue(ws,r,c.cpc);
        const reach = numericValue(ws,r,c.reach), freq = numericValue(ws,r,c.frequency), views = numericValue(ws,r,c.views), vtr = numericValue(ws,r,c.vtr);
        if (imp > 0 && clicks != null && ctr != null) {
          const calc = clicks / imp;
          if (!compareRatio(ctr, calc)) pushIssue(state, createIssue(SEVERITY.CHECK, 'Математика медиаплана', table.sheetName, encodeCell(r,c.ctr), ctr, 'Нужно проверить. CTR отличается от расчёта клики / показы.', 'Допускаются округления и особенности методологии площадки, поэтому это не считается доказанной ошибкой.', 'Сверьте формулу и источник показателей.', `${encodeCell(r,c.clicks)} / ${encodeCell(r,c.impressions)}`));
        }
        if (budget != null && imp > 0 && cpm != null) {
          const calc = budget / imp * 1000;
          if (!approxEqual(cpm, calc, 0.02, 0.5)) pushIssue(state, createIssue(SEVERITY.CHECK, 'Математика медиаплана', table.sheetName, encodeCell(r,c.cpm), cpm, 'Нужно проверить. CPM отличается от расчёта бюджет / показы × 1000.', 'Возможны комиссии, НДС или другая база бюджета, поэтому приложение не определяет «правильное» число.', 'Проверьте методологию бюджета и формулу.', `${encodeCell(r,c.budget)} / ${encodeCell(r,c.impressions)}`));
        }
        if (budget != null && clicks > 0 && cpc != null) {
          const calc = budget / clicks;
          if (!approxEqual(cpc, calc, 0.02, 0.5)) pushIssue(state, createIssue(SEVERITY.CHECK, 'Математика медиаплана', table.sheetName, encodeCell(r,c.cpc), cpc, 'Нужно проверить. CPC отличается от расчёта бюджет / клики.', 'Возможны комиссии или другая база затрат.', 'Проверьте методологию и формулу.', `${encodeCell(r,c.budget)} / ${encodeCell(r,c.clicks)}`));
        }
        if (imp > 0 && reach > 0 && freq != null) {
          const calc = imp / reach;
          if (!approxEqual(freq, calc, 0.03, 0.1)) pushIssue(state, createIssue(SEVERITY.CHECK, 'Математика медиаплана', table.sheetName, encodeCell(r,c.frequency), freq, 'Нужно проверить. Частота отличается от расчёта показы / охват.', 'Расхождение может быть вызвано методологией площадки или округлением.', 'Проверьте формулу и тип охвата.', `${encodeCell(r,c.impressions)} / ${encodeCell(r,c.reach)}`));
        }
        if (imp > 0 && views != null && vtr != null) {
          const calc = views / imp;
          if (!compareRatio(vtr, calc)) pushIssue(state, createIssue(SEVERITY.CHECK, 'Математика медиаплана', table.sheetName, encodeCell(r,c.vtr), vtr, 'Нужно проверить. VTR отличается от расчёта просмотры / показы.', 'Возможна иная база просмотра, поэтому это предупреждение.', 'Проверьте определение просмотра и формулу.', `${encodeCell(r,c.views)} / ${encodeCell(r,c.impressions)}`));
        }

        if (c.start != null && c.end != null && c.days != null) {
          const sCell = ws[encodeCell(r,c.start)], eCell = ws[encodeCell(r,c.end)], dCell = ws[encodeCell(r,c.days)];
          const sd = toDate(sCell), ed = toDate(eCell), days = dCell && typeof dCell.v === 'number' ? dCell.v : null;
          if (sd && ed) {
            if (sd > ed) pushIssue(state, createIssue(SEVERITY.CRITICAL, 'Период размещения', table.sheetName, encodeCell(r,c.start), `${getCellText(sCell)} — ${getCellText(eCell)}`, 'Дата начала позже даты окончания.', 'Это технически невозможный период.', 'Исправьте даты периода.', encodeCell(r,c.end)));
            if (days != null && sd <= ed) {
              const calcDays = Math.floor((ed - sd) / 86400000) + 1;
              if (Math.abs(days - calcDays) >= 1) pushIssue(state, createIssue(SEVERITY.CHECK, 'Календарь размещения', table.sheetName, encodeCell(r,c.days), days, `Количество дней (${days}) не совпадает с календарным количеством дней между указанными датами (${calcDays}).`, 'Возможно, планируются только активные/рабочие дни; поэтому требуется проверка, а не автоматическое исправление.', 'Проверьте календарную сетку и логику активных дней.', `${encodeCell(r,c.start)}:${encodeCell(r,c.end)}`));
            }
          }
        }
      }
    }
  }

  function toDate(cell) {
    if (!cell) return null;
    if (cell.v instanceof Date && !Number.isNaN(cell.v.getTime())) return new Date(Date.UTC(cell.v.getFullYear(), cell.v.getMonth(), cell.v.getDate()));
    const text = getCellText(cell);
    const t = extractDateTokensFromText(text)[0];
    if (t && t.year) {
      const d = new Date(Date.UTC(t.year,t.month-1,t.day));
      return Number.isNaN(d.getTime()) ? null : d;
    }
    return null;
  }

  function checkDateRanges(index, state) {
    for (const item of index.cells) {
      const p = parseDateRange(item.text);
      if (p && p.start > p.end) pushIssue(state, createIssue(SEVERITY.CRITICAL, 'Период размещения', item.sheet, item.addr, item.text, 'В текстовом периоде дата начала позже даты окончания.', 'Это технически невозможный период кампании/размещения.', 'Исправьте даты периода.'));
    }
  }

  function checkDuplicates(workbook, state) {
    for (const sheetName of workbook.SheetNames || []) {
      const ws = workbook.Sheets[sheetName]; if (!ws) continue;
      const rows = new Map();
      for (const e of actualCellEntries(ws)) { if (!rows.has(e.pos.r)) rows.set(e.pos.r, []); rows.get(e.pos.r).push(e); }
      const signatures = new Map();
      for (const [r, entries] of rows) {
        const sorted = entries.slice().sort((a,b)=>a.pos.c-b.pos.c);
        const nonEmpty = sorted.filter(e=>normalizeText(getCellText(e.cell)));
        if (nonEmpty.length < 3) continue;
        const sig = nonEmpty.map(e=>`${e.pos.c}:${normalizeText(getCellText(e.cell))}`).join('\u241f');
        if (!signatures.has(sig)) signatures.set(sig, []);
        signatures.get(sig).push(r);
      }
      for (const rowsSame of signatures.values()) {
        if (rowsSame.length > 1) {
          const first = rowsSame[0], second = rowsSame[1];
          pushIssue(state, createIssue(SEVERITY.CHECK, 'Возможный дубль', sheetName, encodeCell(second, 0), `Строки ${rowsSame.map(r=>r+1).join(', ')}`, 'Обнаружены полностью одинаковые заполненные строки.', 'Это может быть намеренное повторение, поэтому случай помечен как возможный дубль.', 'Проверьте, требуется ли повтор строки.', `строка ${first+1}`));
        }
      }
    }
  }

  function extractAudiences(index) {
    const out = [];
    const re = /(?:м\s*\/\s*ж|ж\s*\/\s*м|ж|м)\s*\d{1,2}\s*[-–—]\s*\d{1,2}/giu;
    for (const item of index.cells) {
      let m; re.lastIndex = 0;
      while ((m = re.exec(item.text || ''))) out.push({ value: m[0].replace(/\s+/g,' '), item });
    }
    return out;
  }

  function splitLines(value) {
    if (Array.isArray(value)) return value.map(String).map(x=>x.trim()).filter(Boolean);
    return String(value || '').split(/\n|;/).map(x=>x.trim()).filter(Boolean);
  }

  function checkBrandCard(index, state, brandCard) {
    if (!brandCard) return;
    const allowedAud = splitLines(brandCard.targetAudiences).map(compactText);
    if (allowedAud.length) {
      for (const a of extractAudiences(index)) {
        if (!allowedAud.includes(compactText(a.value))) pushIssue(state, createIssue(SEVERITY.CHECK, 'Соответствие бренду', a.item.sheet, a.item.addr, a.value, `В медиаплане указана ЦА «${a.value}», которой нет в карточке бренда.`, `В карточке указано: ${splitLines(brandCard.targetAudiences).join('; ')}. Отличие не считается автоматической ошибкой.`, 'Проверьте, согласована ли эта ЦА для текущего размещения.'));
      }
    }

    const required = [];
    const forbidden = [];
    splitLines(brandCard.additionalRules).forEach(line => {
      const m1 = /^обязательно\s*:\s*(.+)$/i.exec(line); if (m1) required.push(m1[1].trim());
      const m2 = /^(?:запрещено|не использовать)\s*:\s*(.+)$/i.exec(line); if (m2) forbidden.push(m2[1].trim());
    });
    required.forEach(term => {
      if (!index.searchText.includes(normalizeText(term))) pushIssue(state, createIssue(SEVERITY.CHECK, 'Соответствие бренду', 'Книга', '', term, `Обязательный элемент из карточки бренда не найден: «${term}».`, 'Правило задано пользователем в карточке бренда.', 'Проверьте, должен ли элемент присутствовать в этой версии медиаплана.'));
    });
    forbidden.forEach(term => {
      const hit = index.cells.find(c => normalizeText(c.text).includes(normalizeText(term)));
      if (hit) pushIssue(state, createIssue(SEVERITY.CHECK, 'Соответствие бренду', hit.sheet, hit.addr, hit.text, `Найден элемент, отмеченный в карточке как нежелательный/запрещённый: «${term}».`, 'Это правило задано пользователем и требует проверки контекста.', 'Проверьте соответствие актуальному неймингу и правилам бренда.'));
    });
  }

  function parseMoney(text) {
    const s = String(text || '').replace(/\u00A0/g,' ');
    const m = /(\d[\d\s.,]*)\s*(млн|миллион(?:а|ов)?|тыс|тысяч(?:а|и)?|руб|р\.?|₽)?/iu.exec(s);
    if (!m) return null;
    let n = m[1].replace(/\s/g,'').replace(',', '.');
    const parts = n.split('.');
    if (parts.length > 2) n = parts.join('');
    let v = Number(n); if (!Number.isFinite(v)) return null;
    const unit = normalizeText(m[2] || '');
    if (unit.startsWith('млн') || unit.startsWith('миллион')) v *= 1e6;
    else if (unit.startsWith('тыс')) v *= 1e3;
    return v;
  }

  function instructionEntities(sentence) {
    const entities = [];
    const s = normalizeText(sentence);
    for (const [canonical, aliases] of Object.entries(PLATFORM_ALIASES)) if (aliases.some(a => s.includes(normalizeText(a)))) entities.push(canonical);
    const tokens = String(sentence).match(/[A-ZА-ЯЁ][A-Za-zА-Яа-яЁё0-9-]{2,}/g) || [];
    for (const t of tokens) if (!/^(Увеличить|Убрать|Добавить|Продлить|Старт|Размещение|Нужно|Проверить)$/i.test(t) && !entities.some(e=>normalizeText(e)===normalizeText(t))) entities.push(t);
    return [...new Set(entities)].slice(0,6);
  }

  function introDateFound(token, index) {
    const key = dateTokenKey(token);
    if (index.dateTokens.has(key)) return true;
    if (token.year && index.dateTokens.has(`*-${String(token.month).padStart(2,'0')}-${String(token.day).padStart(2,'0')}`)) return true;
    if (!token.year && index.dateTokens.has(`*-${String(token.month).padStart(2,'0')}-${String(token.day).padStart(2,'0')}`)) return true;
    return false;
  }

  function checkIntro(intro, index, state) {
    const results = [];
    const text = String(intro || '').trim();
    if (!text) return results;
    const sentences = text.split(/\n+|(?<=[.!?;])\s+/).map(x=>x.trim()).filter(Boolean);
    for (const sentence of sentences) {
      const entities = instructionEntities(sentence);
      const dates = extractDateTokensFromText(sentence);
      const money = parseMoney(sentence);
      let status = 'Требует проверки', detail = 'Не удалось однозначно подтвердить изменение по одному текущему файлу.';
      let createdIssue = false;

      const remove = /(убрать|исключить|удалить|не использовать)/iu.test(sentence);
      const add = /(добавить|включить)/iu.test(sentence);
      const increase = /(увеличить|поднять|добавить\s+к)/iu.test(sentence);
      const decrease = /(снизить|уменьшить|срезать)/iu.test(sentence);
      const transfer = /(перенести|перенос)/iu.test(sentence);
      const startIntent = /(старт|начать|начало)/iu.test(sentence);

      const entityHits = entities.filter(e => index.searchText.includes(normalizeText(e)));
      if (remove && entities.length) {
        if (entityHits.length) {
          status = 'Не найдено'; detail = `Требование «убрать» не подтверждено: ${entityHits.join(', ')} всё ещё встречается в книге.`;
          const hit = index.cells.find(c => entityHits.some(e => normalizeText(c.text).includes(normalizeText(e))));
          pushIssue(state, createIssue(SEVERITY.CHECK, 'Сопроводительные вводные', hit ? hit.sheet : 'Книга', hit ? hit.addr : '', hit ? hit.text : sentence, detail, 'В сопроводительных вводных указано удалить/исключить сущность.', 'Проверьте, должна ли сущность остаться в технических/исторических комментариях.'));
          createdIssue = true;
        } else { status = 'Найдено'; detail = 'Сущность из требования «убрать» в книге не найдена.'; }
      } else if (add && entities.length) {
        if (entityHits.length) { status = 'Найдено'; detail = `Найдены: ${entityHits.join(', ')}.`; }
        else {
          status = 'Не найдено'; detail = `Не найдено подтверждение добавления: ${entities.join(', ')}.`;
          pushIssue(state, createIssue(SEVERITY.CHECK, 'Сопроводительные вводные', 'Книга', '', sentence, detail, 'Во вводных есть явное требование добавить сущность.', 'Проверьте, учтено ли требование.'));
          createdIssue = true;
        }
      } else if ((increase || decrease) && entities.length) {
        if (entityHits.length) {
          status = 'Требует проверки'; detail = `${entityHits.join(', ')} найдено в книге${money ? `; указанное изменение ${formatNumber(money)} ₽ нельзя подтвердить без предыдущей версии/базы сравнения` : ', но направление изменения нельзя подтвердить без предыдущей версии'}.`;
        } else {
          status = 'Не найдено'; detail = `Сущность из требования не найдена: ${entities.join(', ')}.`;
        }
        pushIssue(state, createIssue(SEVERITY.CHECK, 'Недостаточно данных', 'Книга', '', sentence, detail, 'Для проверки увеличения/снижения нужна исходная версия или явно заданное целевое значение.', 'Загрузите/сверьте предыдущий медиаплан либо проверьте изменение вручную.'));
        createdIssue = true;
      } else if (transfer) {
        status = 'Требует проверки';
        detail = entityHits.length ? `В книге найдены связанные сущности: ${entityHits.join(', ')}. Сумму и источник переноса нельзя доказать без исходного файла/версии.` : 'Перенос нельзя доказать по одному текущему файлу.';
        pushIssue(state, createIssue(SEVERITY.CHECK, 'Недостаточно данных', 'Книга', '', sentence, detail, 'Перенос бюджета/строк требует сравнения источника и назначения.', 'Проверьте исходный файл или предыдущую версию медиаплана.'));
        createdIssue = true;
      }

      if (dates.length) {
        const found = dates.filter(d => introDateFound(d,index));
        if (found.length === dates.length && !createdIssue) { status = 'Найдено'; detail = `Даты из вводных найдены в книге: ${dates.map(d=>d.raw).join(', ')}.`; }
        else if (found.length < dates.length) {
          const missing = dates.filter(d => !introDateFound(d,index));
          status = 'Не найдено'; detail = `Не найдены даты из вводных: ${missing.map(d=>d.raw).join(', ')}.`;
          pushIssue(state, createIssue(SEVERITY.CHECK, 'Сопроводительные вводные', 'Книга', '', sentence, detail, 'В клиентском комментарии есть явные даты.', 'Проверьте шапку, календарную сетку и периоды размещений.'));
        } else if (startIntent && found.length) {
          status = 'Найдено'; detail = `Дата старта ${found.map(d=>d.raw).join(', ')} встречается в книге.`;
        }
      }

      if (!dates.length && !remove && !add && !increase && !decrease && !transfer) {
        if (entities.length && entityHits.length === entities.length) { status = 'Найдено'; detail = `Упомянутые сущности найдены: ${entityHits.join(', ')}.`; }
      }
      results.push({ sentence, status, detail });
    }
    return results;
  }

  function formatNumber(n) {
    try { return new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(n); }
    catch (_) { return String(n); }
  }

  function runAllChecks(workbook, options) {
    options = options || {};
    const state = { issues: [], keys: new Set() };
    const index = collectWorkbookIndex(workbook);
    const exclusions = [...(options.globalExclusions || []), ...splitLines(options.brandCard && options.brandCard.exclusions), ...splitLines(options.brandCard && options.brandCard.allowedAbbreviations)];

    checkTechnical(workbook, index, state, options.rawInfo || null);
    checkFormulaPatterns(workbook, index, state);
    checkText(index, state, exclusions);
    checkMediaMath(workbook, state);
    checkDateRanges(index, state);
    checkDuplicates(workbook, state);
    checkBrandCard(index, state, options.brandCard || null);
    const introResults = checkIntro(options.intro || '', index, state);

    const weight = { [SEVERITY.CRITICAL]: 0, [SEVERITY.CHECK]: 1, [SEVERITY.TEXT]: 2 };
    state.issues.sort((a,b) => (weight[a.severity]-weight[b.severity]) || a.sheet.localeCompare(b.sheet,'ru') || a.cell.localeCompare(b.cell,'ru'));
    const counts = {
      critical: state.issues.filter(x=>x.severity===SEVERITY.CRITICAL).length,
      check: state.issues.filter(x=>x.severity===SEVERITY.CHECK).length,
      text: state.issues.filter(x=>x.severity===SEVERITY.TEXT).length
    };
    return {
      issues: state.issues,
      introResults,
      counts,
      status: counts.critical || counts.check || counts.text ? 'Нужно исправить' : 'Можно отправлять клиенту',
      stats: { sheets: index.sheetNames.length, cells: index.cells.length, formulas: index.cells.filter(x=>x.formula).length, textCells: index.cells.filter(x=>typeof x.cell.v==='string' || x.cell.t==='s').length }
    };
  }

  return {
    SEVERITY,
    normalizeText,
    normalizeFormulaShape,
    extractDateTokensFromText,
    collectWorkbookIndex,
    checkIntro,
    runAllChecks,
    decodeCell,
    encodeCell,
    decodeRange,
    getCellText
  };
});
