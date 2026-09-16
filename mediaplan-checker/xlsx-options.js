(function (root) {
  'use strict';
  if (!root || !root.XLSX || root.XLSX.__mediaplanCommentsPatched) return;
  const originalRead = root.XLSX.read.bind(root.XLSX);
  root.XLSX.read = function (data, options) {
    return originalRead(data, { ...(options || {}), cellComments: true });
  };
  root.XLSX.__mediaplanCommentsPatched = true;
})(typeof globalThis !== 'undefined' ? globalThis : window);
