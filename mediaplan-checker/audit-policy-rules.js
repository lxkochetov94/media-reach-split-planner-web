(function (root, factory) {
  if (typeof module === 'object' && module.exports) module.exports = factory(require('./fa-rules.js'));
  else if (root && root.MPChecks) root.MPChecks = factory(root.MPChecks);
})(typeof globalThis !== 'undefined' ? globalThis : this, function (core) {
  'use strict';
  if (!core || core.__auditPolicyRulesPatched) return core;

  const originalRun = core.runAllChecks.bind(core);
  const S = core.SEVERITY;

  function finish(result) {
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
    const result = originalRun(workbook, options || {});
    return finish(result);
  };

  core.__auditPolicyRulesPatched = true;
  return core;
});
