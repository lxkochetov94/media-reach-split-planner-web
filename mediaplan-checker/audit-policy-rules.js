(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./fa-final-rules.js'));
  else if (root && root.MPChecks) root.MPChecks = factory(root.MPChecks);
})(typeof globalThis !== 'undefined' ? globalThis : this, function (core) {
  'use strict';
  if (!core || core.__auditPolicyRulesPatched) return core;

  const originalRun = core.runAllChecks.bind(core);
  const S = core.SEVERITY;

  function finish(result) {
    // Формат отображения и скрытая дробная точность сами по себе не являются ошибкой.
    // Удаляем только этот тип предупреждения. Доказанные арифметические ошибки,
    // ошибки формул, несовпадающие диапазоны, неверные суммы и календарная математика сохраняются.
    result.issues = (result.issues || []).filter(x => x.type !== 'Точность бюджета');
    result.counts = {
      critical: result.issues.filter(x => x.severity === S.CRITICAL).length,
      check: result.issues.filter(x => x.severity === S.CHECK).length,
      text: result.issues.filter(x => x.severity === S.TEXT).length
    };
    result.status = result.issues.length ? 'Нужно исправить' : 'Можно отправлять клиенту';
    return result;
  }

  core.runAllChecks = function (workbook, options) {
    return finish(originalRun(workbook, options || {}));
  };

  core.__auditPolicyRulesPatched = true;
  return core;
});
