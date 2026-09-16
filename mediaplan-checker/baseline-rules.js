(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./final-rules.js'));
  else if (root && root.MPChecks) root.MPChecks = factory(root.MPChecks);
})(typeof globalThis !== 'undefined' ? globalThis : this, function (core) {
  'use strict';
  if (!core || core.__baselineRulesPatched) return core;

  const originalRun = core.runAllChecks.bind(core);
  const S = core.SEVERITY;
  const MONTH_WORDS = /^(january|february|march|april|may|june|july|august|september|october|november|december|jan|feb|mar|apr|jun|jul|aug|sep|sept|oct|nov|dec|январь|февраль|март|апрель|май|июнь|июль|август|сентябрь|октябрь|ноябрь|декабрь)$/iu;

  function norm(v) {
    return String(v == null ? '' : v).replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim().toLowerCase();
  }
  function text(cell) {
    if (!cell) return '';
    if (typeof cell.v === 'string') return cell.v;
    if (cell.t === 's' && cell.v != null) return String(cell.v);
    return '';
  }
  function addrParts(addr) {
    const m = String(addr || '').toUpperCase().match(/^([A-Z]{1,3})(\d+)$/);
    return m ? { col: m[1], row: Number(m[2]) } : null;
  }
  function colToNumber(col) {
    let n = 0;
    for (const ch of String(col || '').toUpperCase()) n = n * 26 + ch.charCodeAt(0) - 64;
    return n;
  }
  function numberToCol(n) {
    let s = '';
    while (n > 0) { const r = (n - 1) % 26; s = String.fromCharCode(65 + r) + s; n = Math.floor((n - 1) / 26); }
    return s;
  }
  function cellAt(ws, row, colNum) { return ws && ws[`${numberToCol(colNum)}${row}`]; }
  function allEntries(ws) {
    return Object.keys(ws || {}).filter(k => /^[A-Z]{1,3}\d+$/i.test(k)).map(addr => ({ addr: addr.toUpperCase(), cell: ws[addr], pos: addrParts(addr) })).filter(x => x.cell && x.pos);
  }
  function issue(severity, type, sheet, cell, value, problem, why, recommendation, related) {
    return { severity, type, sheet: sheet || '', cell: cell || '', value: value == null ? '' : String(value), problem, why, recommendation, related: related || '', fixStatus: '' };
  }
  function key(x) { return [x.severity,x.type,x.sheet,x.cell,x.problem,x.related].join('|'); }
  function add(list, x) { if (!list.some(y => key(y) === key(x))) list.push(x); }
  function finish(result) {
    const order = { [S.CRITICAL]:0, [S.CHECK]:1, [S.TEXT]:2 };
    result.issues.sort((a,b)=>(order[a.severity]-order[b.severity]) || String(a.sheet).localeCompare(String(b.sheet),'ru') || String(a.cell).localeCompare(String(b.cell),'ru'));
    result.counts = {
      critical: result.issues.filter(x=>x.severity===S.CRITICAL).length,
      check: result.issues.filter(x=>x.severity===S.CHECK).length,
      text: result.issues.filter(x=>x.severity===S.TEXT).length
    };
    result.status = result.issues.length ? 'Нужно исправить' : 'Можно отправлять клиенту';
    return result;
  }

  function isSimpleDirectReference(formula) {
    const f = String(formula || '').replace(/\s+/g, '');
    return /^=(?:'[^']+'|[^'=+\-*/(),]+)!\$?[A-Z]{1,3}\$?\d+$/u.test(f);
  }

  function filterKnownFalsePositives(workbook, options, issues) {
    const hasCanonicalPlatforms = !!norm(options && options.brandCard && options.brandCard.properPlatforms);
    return issues.filter(x => {
      if (x.type === 'Формула / период' && x.sheet && x.cell) {
        const ws = workbook.Sheets && workbook.Sheets[x.sheet];
        const c = ws && ws[x.cell];
        if (c && c.f && isSimpleDirectReference(c.f)) return false;
      }
      if (x.type === 'Единообразие названий' && !hasCanonicalPlatforms) return false;
      return true;
    });
  }

  function mergeLatentFormulaIssues(issues) {
    const buckets = new Map();
    const keep = [];
    for (const x of issues) {
      if (x.type === 'Формула Excel' && x.problem === 'Формула содержит битую ссылку в неактивной ветке.') {
        const k = [x.severity,x.type,x.sheet,x.problem,x.recommendation].join('|');
        if (!buckets.has(k)) buckets.set(k, []);
        buckets.get(k).push(x);
      } else keep.push(x);
    }
    for (const group of buckets.values()) {
      const first = group[0];
      const cells = [];
      for (const x of group) {
        const refs = String(x.cell || '').split(/\s*,\s*/).filter(Boolean);
        for (const r of refs) if (!cells.includes(r)) cells.push(r);
      }
      keep.push({ ...first, cell: cells.join(', '), related: cells.join(', ') });
    }
    return keep;
  }

  function improveDefinedNames(options, issues) {
    const raw = options && options.rawInfo;
    if (!raw || !Array.isArray(raw.definedNames)) return;
    const existing = issues.find(x => x.type === 'Именованные диапазоны');
    if (!existing) return;
    const brokenEntries = raw.definedNames.length;
    const unique = new Set(raw.definedNames.map(n => `${n && (n.name || n.Name) || ''}|${n && (n.ref || n.Ref) || ''}`)).size;
    const total = Number(raw.definedNamesTotal || 0);
    existing.problem = `Обнаружено ${brokenEntries} битых записей именованных диапазонов${total ? ` из ${total}` : ''}; ${unique} уникальных после дедупликации.`;
    existing.why = 'В Excel одно и то же имя/формула может повторяться в разных областях видимости. Поэтому отдельно показываются все битые записи и уникальные комбинации «имя + ссылка».';
    existing.recommendation = 'Проверьте Диспетчер имён Excel; удаляйте только неиспользуемые имена после резервной копии.';
  }

  function findHeader(ws, re, maxRow) {
    let best = null;
    for (const e of allEntries(ws)) {
      if (e.pos.row > (maxRow || 25)) continue;
      const t = norm(text(e.cell));
      if (!t || !re.test(t)) continue;
      if (!best || e.pos.row < best.row) best = { row:e.pos.row, col:colToNumber(e.pos.col), addr:e.addr, text:t };
    }
    return best;
  }
  function findCampaignAudience(ws) {
    for (const e of allEntries(ws)) {
      if (e.pos.row > 12) continue;
      const t = norm(text(e.cell));
      if (!['ta','ца','target audience'].includes(t)) continue;
      const c0 = colToNumber(e.pos.col);
      for (let c = c0 + 1; c <= c0 + 3; c++) {
        const v = cellAt(ws, e.pos.row, c);
        const raw = text(v);
        if (raw) return { label:e.addr, value:`${numberToCol(c)}${e.pos.row}`, raw };
      }
    }
    return null;
  }
  function parseAudience(raw) {
    const s = String(raw || '').replace(/\u00a0/g,' ').replace(/[–—]/g,'-');
    const m = s.match(/(?:^|[\s,;(])([ЖМFM])\s*(\d{2})\s*-\s*(\d{2})/iu);
    return m ? { gender:m[1].toUpperCase(), from:Number(m[2]), to:Number(m[3]), raw:m[0].trim() } : null;
  }
  function sameAudience(a,b) { return a && b && a.gender===b.gender && a.from===b.from && a.to===b.to; }
  function addAudienceChecks(workbook, issues) {
    for (const sheet of workbook.SheetNames || []) {
      const ws = workbook.Sheets[sheet];
      if (!ws) continue;
      const campaign = findCampaignAudience(ws);
      if (!campaign) continue;
      const campaignParsed = parseAudience(campaign.raw);
      if (!campaignParsed) continue;
      const siteHead = findHeader(ws, /^(site|площадка)$/iu, 25);
      const targetHead = findHeader(ws, /(target|таргет|placement.*target)/iu, 25);
      if (!siteHead || !targetHead || siteHead.row !== targetHead.row) continue;
      const mismatches = [];
      for (let r = siteHead.row + 1; r <= siteHead.row + 120; r++) {
        const site = text(cellAt(ws, r, siteHead.col)).trim();
        const trgCell = cellAt(ws, r, targetHead.col);
        const trgRaw = text(trgCell);
        if (!site || !trgRaw) continue;
        const parsed = parseAudience(trgRaw);
        if (!parsed || sameAudience(parsed,campaignParsed)) continue;
        mismatches.push({ row:r, site, raw:parsed.raw || trgRaw.split(/\n/)[0], cell:`${numberToCol(targetHead.col)}${r}` });
      }
      for (const m of mismatches) {
        add(issues, issue(S.CHECK,'ЦА / логика',sheet,m.cell,m.raw,`ЦА строки размещения «${m.site}» (${m.raw}) отличается от общей ЦА кампании (${campaignParsed.raw}).`,'Разные возрастные диапазоны могут быть осознанным ограничением площадки, но без пояснения это формальное расхождение медиаплана.','Подтвердите доступную ЦА площадки. Если расширение осознанное — добавьте пояснение; иначе приведите к общей ЦА.',campaign.value));
      }
    }
  }

  function looksVideo(raw) {
    return /(\bolv\b|video|видео|instream|in-stream|outstream|out-stream|pre[- ]?roll|mid[- ]?roll|post[- ]?roll|видеорол|плеер|smart\s*tv|ctv)/iu.test(String(raw || ''));
  }
  function mediaPlacements(workbook) {
    const rows = [];
    for (const sheet of workbook.SheetNames || []) {
      const ws = workbook.Sheets[sheet];
      if (!ws) continue;
      const siteHead = findHeader(ws, /^(site|площадка)$/iu, 30);
      const formatHead = findHeader(ws, /(format|формат)/iu, 30);
      if (!siteHead || !formatHead || siteHead.row !== formatHead.row) continue;
      const videoHead = findHeader(ws, /(video details|видео)/iu, 30);
      const unitHead = findHeader(ws, /(unit type|единиц)/iu, 30);
      for (let r = siteHead.row + 1; r <= siteHead.row + 150; r++) {
        const site = text(cellAt(ws,r,siteHead.col)).trim();
        const format = text(cellAt(ws,r,formatHead.col)).trim();
        if (!site || !format) continue;
        rows.push({sheet,row:r,site,format,video:videoHead?text(cellAt(ws,r,videoHead.col)).trim():'',unit:unitHead?text(cellAt(ws,r,unitHead.col)).trim():''});
      }
    }
    return rows;
  }
  function addVideoMismatch(workbook, issues) {
    const placements = mediaPlacements(workbook);
    if (!placements.length) return;
    const hasVideo = placements.some(p => looksVideo(`${p.format} ${p.video && p.video !== '-' ? p.video : ''} ${p.unit}`));
    if (hasVideo) return;
    const hits = [];
    for (const sheet of workbook.SheetNames || []) {
      if (!/(свод|summary)/iu.test(sheet)) continue;
      const ws = workbook.Sheets[sheet];
      for (const e of allEntries(ws)) {
        const raw = text(e.cell);
        if (raw && /(audibility|in-stream|out-stream|instream|outstream|слышимости?\s+(?:видео)?ролик|размер\w*\s+плеер|видео\s*ролик)/iu.test(raw)) hits.push({sheet,cell:e.addr,raw});
      }
    }
    if (!hits.length) return;
    const cells = hits.map(h=>`${h.sheet}!${h.cell}`).join(', ');
    add(issues, issue(S.CHECK,'Логика / контент',hits[0].sheet,hits.map(h=>h.cell).join(', '),hits.map(h=>h.raw).join(' | '),'На своде есть видеоспецифичные показатели или текст, но в активных форматах медиаплана видео не обнаружено.','Audibility, In-stream/Out-stream, слышимость ролика и размер плеера не относятся к баннерным/социальным форматам без видео.','Удалите видеоспецифичный блок либо подтвердите, что в кампании действительно есть видеоформат.',cells));
  }

  function monthHeaderInColumn(ws, colNum, maxRow) {
    for (let r = 1; r <= maxRow; r++) {
      const raw = norm(text(cellAt(ws,r,colNum))).replace(/[.'’]/g,'');
      if (MONTH_WORDS.test(raw)) return true;
    }
    return false;
  }
  function addMonthlySumChecks(workbook, issues) {
    for (const sheet of workbook.SheetNames || []) {
      const ws = workbook.Sheets[sheet];
      if (!ws) continue;
      const siteHead = findHeader(ws, /^(site|площадка)$/iu, 30);
      if (!siteHead) continue;
      const activeRows = [];
      for (let r = siteHead.row + 1; r <= siteHead.row + 120; r++) {
        const site = text(cellAt(ws,r,siteHead.col)).trim();
        if (site && !/^(total|итого|всего)$/iu.test(norm(site))) activeRows.push(r);
      }
      if (activeRows.length < 2) continue;
      const startExpected = Math.min(...activeRows), endExpected = Math.max(...activeRows);
      const byRow = new Map();
      for (const e of allEntries(ws)) {
        if (!e.cell.f) continue;
        const m = String(e.cell.f).replace(/\s+/g,'').match(/^=SUM\(\$?([A-Z]{1,3})\$?(\d+):\$?([A-Z]{1,3})\$?(\d+)\)$/i);
        if (!m || m[1].toUpperCase() !== m[3].toUpperCase()) continue;
        const colNum = colToNumber(e.pos.col);
        if (!monthHeaderInColumn(ws,colNum,siteHead.row)) continue;
        const rec = {cell:e.addr,col:e.pos.col,start:Number(m[2]),end:Number(m[4]),formula:e.cell.f};
        if (!byRow.has(e.pos.row)) byRow.set(e.pos.row, []);
        byRow.get(e.pos.row).push(rec);
      }
      for (const [row, formulas] of byRow) {
        if (formulas.length < 6 || row <= endExpected || row > endExpected + 3) continue;
        const bad = formulas.filter(f => f.start !== startExpected || f.end !== endExpected);
        if (!bad.length) continue;
        add(issues, issue(S.CHECK,'Месячные итоги / SUM',sheet,bad.map(x=>x.cell).join(', '),bad.slice(0,4).map(x=>`${x.cell}: ${x.formula}`).join(' | '),`${bad.length} месячных итогов используют диапазон, который не охватывает все строки активных размещений (${startExpected}:${endExpected}).`,'При копировании или смене месяца часть активных строк может выпасть из buying units / budget total.','Унифицируйте месячные SUM так, чтобы они охватывали все строки активных размещений; отдельно проверьте нестандартные границы диапазона.',`Активные строки размещений: ${startExpected}:${endExpected}`));
      }
    }
  }

  function addXlfnChecks(workbook, issues) {
    for (const sheet of workbook.SheetNames || []) {
      const ws = workbook.Sheets[sheet];
      const hits = allEntries(ws).filter(e => e.cell.f && /_xlfn\./i.test(String(e.cell.f)));
      if (!hits.length) continue;
      if (issues.some(x => x.sheet === sheet && x.type === 'Совместимость Excel' && /_xlfn/i.test(`${x.problem} ${x.value}`))) continue;
      add(issues, issue(S.CHECK,'Совместимость Excel',sheet,hits.map(h=>h.addr).join(', '),hits.slice(0,4).map(h=>h.cell.f).join(' | '),`Найдено ${hits.length} формул с префиксом _xlfn.`,'В современном Excel формулы могут работать нормально, но старые версии Excel и сторонние движки иногда возвращают #NAME?.','Если файл должен открываться в разных средах, проверьте совместимость функций или замените их на более базовые аналоги.'));
    }
  }

  function addReachSourceChecks(workbook, issues) {
    for (const sheet of workbook.SheetNames || []) {
      const ws = workbook.Sheets[sheet];
      const hits = [];
      for (const e of allEntries(ws)) {
        const label = norm(text(e.cell));
        if (!/^reach\s*\(people\)\s*\d+\+$/i.test(label) && !/^охват.*\d+\+$/iu.test(label)) continue;
        const c0 = colToNumber(e.pos.col);
        for (let c=c0+1; c<=c0+3; c++) {
          const v = cellAt(ws,e.pos.row,c);
          if (v && typeof v.v === 'number' && Number.isFinite(v.v)) {
            if (!v.f) hits.push({label:e.addr,value:`${numberToCol(c)}${e.pos.row}`,raw:v.v});
            break;
          }
        }
      }
      if (!hits.length) continue;
      add(issues, issue(S.CHECK,'Расчёт охвата / воспроизводимость',sheet,hits.map(h=>h.value).join(', '),hits.map(h=>`${h.value}=${h.raw}`).join(' | '),'Reach (people) введён вручную без формулы или источника внутри книги.','Проценты охвата можно проверить арифметически, но сам прогноз уникального охвата из файла не воспроизводится.','Добавьте источник прогноза, комментарий или отдельный расчётный лист/ссылку на прогноз площадок.',hits.map(h=>h.label).join(', ')));
    }
  }

  function hasFractionBeyondCents(n) {
    return typeof n === 'number' && Number.isFinite(n) && Math.abs(n * 100 - Math.round(n * 100)) > 1e-6;
  }
  function addBudgetPrecisionChecks(workbook, issues) {
    const hits = [];
    for (const sheet of workbook.SheetNames || []) {
      const ws = workbook.Sheets[sheet];
      for (const e of allEntries(ws)) {
        const label = norm(text(e.cell));
        if (!label || !/(^total media net$|бюджет план|итоговая стоимость)/iu.test(label)) continue;
        const c0 = colToNumber(e.pos.col);
        for (let c=c0+1; c<=c0+4; c++) {
          const v = cellAt(ws,e.pos.row,c);
          if (v && typeof v.v === 'number') {
            if (hasFractionBeyondCents(v.v)) hits.push({sheet,label:e.addr,value:`${numberToCol(c)}${e.pos.row}`,raw:v.v});
            break;
          }
        }
      }
    }
    if (!hits.length) return;
    add(issues, issue(S.CHECK,'Точность бюджета','Книга',hits.map(h=>`${h.sheet}!${h.value}`).join(', '),hits.map(h=>`${h.sheet}!${h.value}=${h.raw}`).join(' | '),'Итоговый бюджет содержит скрытые доли копейки сверх двух знаков после запятой.','На экране сумма может выглядеть круглой, хотя сырое значение отличается от договорного бюджета на доли рубля.','Если бюджет должен быть фиксирован до копеек, округлите итоговую формулу до 2 знаков или скорректируйте одну из исходных строк.'));
  }

  function addGrammarChecks(workbook, issues) {
    for (const sheet of workbook.SheetNames || []) {
      const ws = workbook.Sheets[sheet];
      for (const e of allEntries(ws)) {
        const raw = text(e.cell);
        if (!raw) continue;
        if (/\d+\s*[-–—]\s*\d+\s+разных\s+страниц/iu.test(raw)) add(issues, issue(S.TEXT,'Грамматика',sheet,e.addr,raw,'Фраза вида «2–3 разных страниц» грамматически неверна.','После числительного 2–3 в этой конструкции требуется форма «разные страницы».','Исправьте на «2–3 разные страницы».'));
        if (/за\s+последн(?:юю|ие)\s+1\s+недел/iu.test(raw)) add(issues, issue(S.TEXT,'Грамматика',sheet,e.addr,raw,'Конструкция «за последнюю 1 неделю» избыточна.','Число «1» здесь не требуется и делает клиентский текст тяжёлым.','Исправьте на «за последнюю неделю».'));
        if (/ОФД\s+данн/iu.test(raw)) add(issues, issue(S.TEXT,'Орфография / оформление',sheet,e.addr,raw,'«ОФД данные» написано раздельно.','В деловом тексте сложное сочетание лучше оформить через дефис.','Исправьте на «ОФД-данные».'));
      }
    }
  }

  core.runAllChecks = function(workbook, options) {
    options = options || {};
    const result = originalRun(workbook, options);
    result.issues = filterKnownFalsePositives(workbook, options, result.issues || []);
    result.issues = mergeLatentFormulaIssues(result.issues);
    improveDefinedNames(options, result.issues);
    addAudienceChecks(workbook, result.issues);
    addVideoMismatch(workbook, result.issues);
    addMonthlySumChecks(workbook, result.issues);
    addXlfnChecks(workbook, result.issues);
    addReachSourceChecks(workbook, result.issues);
    addBudgetPrecisionChecks(workbook, result.issues);
    addGrammarChecks(workbook, result.issues);
    return finish(result);
  };

  core.__baselineRulesPatched = true;
  return core;
});
