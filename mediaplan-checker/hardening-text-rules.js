(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./hardening-rules.js'));
  else if (root && root.MPChecks) root.MPChecks = factory(root.MPChecks);
})(typeof globalThis !== 'undefined' ? globalThis : this, function (core) {
  'use strict';
  if (!core || core.__hardeningTextRulesPatched) return core;

  const originalRun = core.runAllChecks.bind(core);
  const S = core.SEVERITY;
  const RU_LEFT = '(^|[^А-Яа-яЁёA-Za-z])';
  const RU_RIGHT = '(?=$|[^А-Яа-яЁёA-Za-z])';

  function entries(ws) {
    return Object.keys(ws || {}).filter(k=>/^[A-Z]{1,3}\d+$/i.test(k)).map(addr=>({addr:addr.toUpperCase(),cell:ws[addr]})).filter(x=>x.cell);
  }
  function text(cell) {
    if (!cell) return '';
    if (typeof cell.v === 'string') return cell.v;
    if (cell.t === 's' && cell.v != null) return String(cell.v);
    return '';
  }
  function issue(type,sheet,cell,value,problem,recommendation) {
    return {severity:S.TEXT,type,sheet,cell,value:String(value||''),problem,why:'Это заметная опечатка или грамматическая проблема в клиентском тексте.',recommendation,related:'',fixStatus:''};
  }
  function same(a,b) { return a.type===b.type&&a.sheet===b.sheet&&a.cell===b.cell&&a.problem===b.problem; }
  function add(list,x) { if(!list.some(y=>same(y,x))) list.push(x); }

  const rules = [
    [new RegExp(RU_LEFT+'стредств'+RU_RIGHT,'iu'),'Опечатка','«стредств» — вероятная опечатка.','Исправьте на «средств».'],
    [new RegExp(RU_LEFT+'видео\\s+ролик(?:а|ов|и|ом|у)?'+RU_RIGHT,'iu'),'Орфография / оформление','Сочетание «видео ролик» написано раздельно.','Исправьте на «видеоролик» в соответствующей форме.'],
    [new RegExp(RU_LEFT+'оффлайн\\s+(?:покуп\\w*|продаж\\w*|канал\\w*|магазин\\w*)','iu'),'Орфография / оформление','Найдено написание «оффлайн …».','Используйте нормативное «офлайн» и проверьте дефис по конструкции.'],
    [new RegExp(RU_LEFT+'с\\s+таргетировани(?:е|ем)'+RU_RIGHT,'iu'),'Грамматика','Конструкция «с таргетирование» грамматически неверна.','Исправьте на «с таргетированием» или «с таргетингом».']
  ];

  core.runAllChecks = function (workbook, options) {
    const result = originalRun(workbook, options || {});
    for (const sheet of workbook.SheetNames || []) {
      const ws = workbook.Sheets[sheet]; if (!ws) continue;
      for (const e of entries(ws)) {
        const raw = text(e.cell); if (!raw) continue;
        for (const [re,type,problem,recommendation] of rules) {
          if (re.test(raw)) add(result.issues, issue(type,sheet,e.addr,raw,problem,recommendation));
        }
      }
    }
    result.counts = {
      critical: result.issues.filter(x=>x.severity===S.CRITICAL).length,
      check: result.issues.filter(x=>x.severity===S.CHECK).length,
      text: result.issues.filter(x=>x.severity===S.TEXT).length
    };
    result.status = result.issues.length ? 'Нужно исправить' : 'Можно отправлять клиенту';
    core.__hardeningTextRulesPatched = true;
    return result;
  };

  core.__hardeningTextRulesPatched = true;
  return core;
});
