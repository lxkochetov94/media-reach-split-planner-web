(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./reliability-rules.js'));
  else if (root && root.MPChecks) root.MPChecks = factory(root.MPChecks);
})(typeof globalThis !== 'undefined' ? globalThis : this, function (core) {
  'use strict';
  if (!core || core.__auditPolishRulesPatched) return core;

  const originalRun = core.runAllChecks.bind(core);
  const S = core.SEVERITY;

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
      .filter(x => x.pos && x.cell);
  }
  function issue(type, sheet, cell, value, problem, why, recommendation) {
    return { severity:S.TEXT, type, sheet, cell, value:String(value || ''), problem, why, recommendation, related:'', fixStatus:'' };
  }
  function add(list, item, predicate) {
    if (!(list || []).some(predicate || (x => x.type===item.type && x.sheet===item.sheet && x.cell===item.cell && x.problem===item.problem))) list.push(item);
  }

  function ownRowLeftContext(ws, pos) {
    const parts = [];
    for (let c=Math.max(0,pos.c-8); c<pos.c; c++) {
      const t = rawText(ws[core.encodeCell(pos.r,c)]);
      if (t) parts.push(t);
    }
    return parts.join(' ').toLowerCase().replace(/ё/g,'е').replace(/\s+/g,' ').trim();
  }
  function filterFalsePeriodCoverage(workbook, issues) {
    return (issues || []).filter(x => {
      if (x.type !== 'Свод / период кампании' || !x.sheet || !x.cell) return true;
      const ws = workbook.Sheets && workbook.Sheets[x.sheet];
      const pos = core.decodeCell(String(x.cell).split(',')[0].trim());
      if (!ws || !pos) return false;
      const ctx = ownRowLeftContext(ws,pos);
      return /(период\w*\s+кампан\w*.*дн|длительн\w*\s+кампан|campaign\s+(?:period|duration|days)|duration\s+of\s+campaign)/iu.test(ctx);
    });
  }

  function addSpecificTextRoots(workbook, issues) {
    for (const sheet of workbook.SheetNames || []) {
      const ws = workbook.Sheets[sheet];
      if (!ws) continue;
      for (const e of entries(ws)) {
        const raw = rawText(e.cell);
        if (!raw) continue;

        // JS \b не является Unicode-aware для кириллицы, поэтому используем явные границы.
        if (/(^|[^А-Яа-яЁёA-Za-z])видео\s+ролик(?:а|ов|и|ом|у)?(?=$|[^А-Яа-яЁёA-Za-z])/iu.test(raw)) {
          const item = issue(
            'Орфография / оформление', sheet, e.addr, raw,
            'Сочетание «видео ролик» написано раздельно.',
            'В клиентском тексте это заметная орфографическая/редакторская ошибка.',
            'Исправьте на «видеоролик» в соответствующей форме.'
          );
          add(issues,item,x => x.sheet===sheet && x.cell===e.addr && /видео\s+ролик|видеоролик/iu.test(`${x.problem||''} ${x.recommendation||''}`));
        }

        // Три и более формы одного корня в одном текстовом блоке — достаточно консервативный
        // сигнал тавтологии. Два употребления не трогаем: в медиапланах они часто нормальны.
        const placementRoots = raw.match(/размещ(?:ен|ени|ать|аем|ается|ают|ено|ены)\w*/giu) || [];
        if (placementRoots.length >= 3) {
          const item = issue(
            'Возможная тавтология', sheet, e.addr, raw,
            'В одном текстовом блоке многократно повторяется слово/корень «размещ…».',
            'Три и более близких по смыслу употребления могут утяжелять клиентскую формулировку.',
            'Проверьте формулировку и при необходимости замените часть повторов: «кампания», «активность», «инвентарь» или перестройте предложение.'
          );
          add(issues,item,x => x.sheet===sheet && x.cell===e.addr && x.type==='Возможная тавтология' && /размещ/iu.test(String(x.problem||'')));
        }

        if (/во\s+вложени(?:и|я)\s+(?:также\s+)?прикладыва/iu.test(raw)) {
          const item = issue('Возможная тавтология',sheet,e.addr,raw,'Конструкция «во вложении прикладываем» тавтологична.','В клиентском тексте формулировка выглядит избыточной.','Используйте «во вложении — …» или «прикладываем …».');
          add(issues,item,x => x.sheet===sheet && x.cell===e.addr && x.type==='Возможная тавтология' && /вложени/iu.test(String(x.problem||'')));
        }

        if (/по\s+ключевым\s+словам\s+по\s+тем/iu.test(raw)) {
          const item = issue('Возможная тавтология',sheet,e.addr,raw,'Конструкция «по ключевым словам по теме» содержит повтор предлога.','Фраза выглядит тяжело и может быть упрощена без потери смысла.','Переформулируйте, например: «по тематическим ключевым словам».');
          add(issues,item,x => x.sheet===sheet && x.cell===e.addr && x.type==='Возможная тавтология' && /ключев/iu.test(String(x.problem||'')));
        }
      }
    }
  }

  function finish(result) {
    const seen = new Set();
    result.issues = (result.issues || []).filter(x => {
      const key = [x.severity,x.type,x.sheet,x.cell,x.problem,x.related].join('|');
      if (seen.has(key)) return false;
      seen.add(key); return true;
    });
    const weight = { [S.CRITICAL]:0, [S.CHECK]:1, [S.TEXT]:2 };
    result.issues.sort((a,b)=>(weight[a.severity]-weight[b.severity]) || String(a.sheet).localeCompare(String(b.sheet),'ru') || String(a.cell).localeCompare(String(b.cell),'ru'));
    result.counts = {
      critical: result.issues.filter(x=>x.severity===S.CRITICAL).length,
      check: result.issues.filter(x=>x.severity===S.CHECK).length,
      text: result.issues.filter(x=>x.severity===S.TEXT).length
    };
    result.status = result.issues.length ? 'Нужно исправить' : 'Можно отправлять клиенту';
    return result;
  }

  core.runAllChecks = function (workbook, options) {
    const result = originalRun(workbook, options || {});
    result.issues = filterFalsePeriodCoverage(workbook, result.issues || []);
    addSpecificTextRoots(workbook, result.issues);
    return finish(result);
  };

  core.__auditPolishRulesPatched = true;
  return core;
});
