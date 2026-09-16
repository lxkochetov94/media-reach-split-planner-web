(function () {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const state = { file: null, workbook: null, result: null, rawInfo: null, filter: 'all' };
  const COMMON_EXCLUSIONS = [
    'OLV','CPM','CPC','CTR','VTR','VK','Rutube','RuTube','RUTUBE','Hybrid','Ozon','Yandex','Яндекс',
    'RTB','Programmatic','Promopost','In-stream','Out-stream','InStream','OutStream','CTV','Smart TV',
    'AdRiver','Weborama','First Data','Digital Alliance','Telegram','TG','РСЯ','ecom','ecommerce','AdFox','Adspector'
  ];

  const els = {
    fileInput: $('fileInput'), fileName: $('fileName'), intro: $('introText'), checkBtn: $('checkBtn'), exportBtn: $('exportBtn'),
    statusCard: $('statusCard'), statusText: $('statusText'), counts: $('counts'), meta: $('meta'), tbody: $('resultsBody'), empty: $('emptyState'),
    introResults: $('introResults'), introPanel: $('introPanel'), resultsPanel: $('resultsPanel'), filterBar: $('filterBar'), libraryError: $('libraryError'),
    progress: $('progress'), progressText: $('progressText')
  };

  function init() {
    bind();
    checkLibraries();
  }

  function bind() {
    els.fileInput.addEventListener('change', () => {
      state.file = els.fileInput.files && els.fileInput.files[0] ? els.fileInput.files[0] : null;
      els.fileName.textContent = state.file ? state.file.name : 'Файл не выбран';
      els.checkBtn.disabled = !state.file;
      resetResults();
    });
    els.checkBtn.addEventListener('click', runAudit);
    els.exportBtn.addEventListener('click', exportAudit);
    els.filterBar.addEventListener('click', (e) => {
      const b = e.target.closest('button[data-filter]'); if (!b) return;
      state.filter = b.dataset.filter;
      [...els.filterBar.querySelectorAll('button')].forEach(x=>x.classList.toggle('active', x===b));
      renderTable();
    });
  }

  function checkLibraries() {
    const missing = [];
    if (!window.XLSX) missing.push('SheetJS');
    if (!window.JSZip) missing.push('JSZip');
    if (missing.length) {
      els.libraryError.hidden = false;
      els.libraryError.textContent = `Не удалось загрузить библиотеку: ${missing.join(', ')}. Проверьте доступ к интернету и перезагрузите страницу.`;
      els.checkBtn.disabled = true;
    }
  }

  async function runAudit() {
    if (!state.file) return;
    if (!window.XLSX) return alert('SheetJS не загружен. Перезагрузите страницу.');
    setBusy(true, 'Читаю Excel и проверяю структуру книги…');
    try {
      const buffer = await state.file.arrayBuffer();
      await nextFrame();
      state.workbook = XLSX.read(buffer, {
        type: 'array', cellFormula: true, cellText: true, cellDates: true, cellStyles: true,
        sheetStubs: false, bookVBA: true, WTF: false
      });
      state.rawInfo = window.JSZip ? await inspectPackage(buffer) : { definedNames: [], externalLinks: [] };
      setBusy(true, 'Проверяю формулы, суммы, текст, даты, дубли и вводные…');
      await nextFrame();
      state.result = MPChecks.runAllChecks(state.workbook, {
        rawInfo: state.rawInfo,
        intro: els.intro.value,
        brandCard: null,
        globalExclusions: COMMON_EXCLUSIONS
      });
      renderResult();
    } catch (err) {
      console.error(err);
      alert(`Не удалось проверить файл. ${err && err.message ? err.message : err}`);
    } finally { setBusy(false); }
  }

  async function inspectPackage(buffer) {
    const result = { definedNames: [], definedNamesTotal: 0, externalLinks: [] };
    try {
      const zip = await JSZip.loadAsync(buffer);
      const wbFile = zip.file('xl/workbook.xml');
      if (wbFile) {
        const xml = await wbFile.async('text');
        const re = /<definedName\b([^>]*)>([\s\S]*?)<\/definedName>/g;
        let m;
        while ((m = re.exec(xml))) {
          result.definedNamesTotal++;
          const nm = /\bname="([^"]+)"/.exec(m[1]);
          const ref = decodeXml(m[2].replace(/<[^>]+>/g,''));
          if (/#REF!|#DIV\/0!|#VALUE!|#N\/A|#NAME\?|#NUM!|#NULL!/i.test(ref)) result.definedNames.push({ name: decodeXml(nm ? nm[1] : ''), ref });
        }
      }
      const externalFiles = Object.keys(zip.files).filter(x=>/^xl\/externalLinks\/externalLink\d+\.xml$/i.test(x));
      const targets = [];
      for (const fileName of externalFiles) {
        const relName = fileName.replace('xl/externalLinks/', 'xl/externalLinks/_rels/') + '.rels';
        const rel = zip.file(relName);
        if (rel) {
          const relXml = await rel.async('text');
          const relRe = /Target="([^"]+)"/g; let rm;
          while ((rm = relRe.exec(relXml))) targets.push(decodeXml(rm[1]));
        }
      }
      result.externalLinks = targets.length ? [...new Set(targets)] : externalFiles;
    } catch (e) { console.warn('Raw package inspection skipped', e); }
    return result;
  }

  function decodeXml(s) {
    return String(s||'').replace(/&lt;/g,'<').replace(/&gt;/g,'>').replace(/&quot;/g,'"').replace(/&apos;/g,"'").replace(/&amp;/g,'&');
  }

  function renderResult() {
    const r = state.result; if (!r) return;
    els.statusCard.hidden = false; els.resultsPanel.hidden = false; els.exportBtn.disabled = false;
    els.statusText.textContent = r.status;
    els.statusCard.className = 'status-card ' + (r.status === 'Можно отправлять клиенту' ? 'ok' : 'needs-work');
    els.counts.innerHTML = `
      <div><strong>${r.counts.critical}</strong><span>Критические ошибки</span></div>
      <div><strong>${r.counts.check}</strong><span>Нужно проверить</span></div>
      <div><strong>${r.counts.text}</strong><span>Текстовые замечания</span></div>`;
    els.meta.textContent = `${r.stats.sheets} листов · ${formatNumber(r.stats.cells)} заполненных ячеек · ${formatNumber(r.stats.formulas)} формул`;
    renderIntro(); renderTable();
  }

  function renderIntro() {
    const items = state.result && state.result.introResults || [];
    els.introPanel.hidden = !items.length;
    if (!items.length) { els.introResults.innerHTML=''; return; }
    els.introResults.innerHTML = items.map(x=>`<div class="intro-result"><span class="intro-badge ${introClass(x.status)}">${escapeHtml(x.status)}</span><div><strong>${escapeHtml(x.sentence)}</strong><p>${escapeHtml(x.detail)}</p></div></div>`).join('');
  }
  function introClass(s) { return s==='Найдено'?'found':s==='Не найдено'?'missing':'review'; }

  function filteredIssues() {
    const all = state.result ? state.result.issues : [];
    if (state.filter === 'critical') return all.filter(x=>x.severity===MPChecks.SEVERITY.CRITICAL);
    if (state.filter === 'check') return all.filter(x=>x.severity===MPChecks.SEVERITY.CHECK);
    if (state.filter === 'text') return all.filter(x=>x.severity===MPChecks.SEVERITY.TEXT);
    return all;
  }

  function renderTable() {
    const issues = filteredIssues();
    els.empty.hidden = issues.length > 0;
    els.tbody.innerHTML = issues.map((x)=>`<tr>
      <td><span class="severity ${severityClass(x.severity)}">${escapeHtml(x.severity)}</span></td>
      <td>${escapeHtml(x.sheet)}</td><td class="mono">${escapeHtml(x.cell)}</td>
      <td><strong>${escapeHtml(x.problem)}</strong><div class="muted small">${escapeHtml(x.type)}</div>${x.value ? `<details><summary>Исходное значение</summary><div class="raw-value">${escapeHtml(truncate(x.value,800))}</div></details>`:''}</td>
      <td>${escapeHtml(x.recommendation)}${x.related?`<div class="muted small related">Связано: ${escapeHtml(x.related)}</div>`:''}</td>
    </tr>`).join('');
  }

  function exportAudit() {
    if (!state.result || !window.XLSX) return;
    const now = new Date();
    const summary = [
      ['Проверка медиаплана',''],
      ['Проверяемый медиаплан', state.file ? state.file.name : ''],
      ['Дата проверки', now.toLocaleString('ru-RU')],
      ['Общий статус', state.result.status],
      ['Критические ошибки', state.result.counts.critical],
      ['Нужно проверить', state.result.counts.check],
      ['Текстовые замечания', state.result.counts.text],
      ['Проверено листов', state.result.stats.sheets],
      ['Проверено заполненных ячеек', state.result.stats.cells],
      ['Проверено формул', state.result.stats.formulas]
    ];
    if (!state.result.issues.length) summary.push(['Результат','Критических ошибок и замечаний не обнаружено']);

    const header = ['№','Важность','Тип проверки','Лист медиаплана','Ячейка','Исходное значение','Найденная проблема','Почему это проблема','Рекомендация','Связанная ячейка / лист','Статус исправления'];
    const rows = state.result.issues.map((x,i)=>[i+1,x.severity,x.type,x.sheet,x.cell,truncate(x.value,2000),x.problem,x.why,x.recommendation,x.related,x.fixStatus||'']);
    if (!rows.length) rows.push(['','','','','','','Критических ошибок и замечаний не обнаружено','','','','']);

    const wb = XLSX.utils.book_new();
    const ws1 = XLSX.utils.aoa_to_sheet(summary);
    ws1['!cols'] = [{wch:30},{wch:80}];
    XLSX.utils.book_append_sheet(wb, ws1, 'Итоги');
    const ws2 = XLSX.utils.aoa_to_sheet([header, ...rows]);
    ws2['!cols'] = [{wch:5},{wch:22},{wch:26},{wch:22},{wch:12},{wch:35},{wch:55},{wch:55},{wch:55},{wch:30},{wch:20}];
    ws2['!autofilter'] = { ref: `A1:K${rows.length+1}` };
    XLSX.utils.book_append_sheet(wb, ws2, 'Ошибки и замечания');

    if (state.result.introResults.length) {
      const introRows = [['Вводная','Статус','Комментарий'], ...state.result.introResults.map(x=>[x.sentence,x.status,x.detail])];
      const ws3 = XLSX.utils.aoa_to_sheet(introRows); ws3['!cols']=[{wch:70},{wch:20},{wch:90}];
      XLSX.utils.book_append_sheet(wb, ws3, 'Сверка вводных');
    }
    const date = now.toISOString().slice(0,10);
    XLSX.writeFile(wb, `Аудит_медиаплана_${date}.xlsx`, { compression: true });
  }

  function setBusy(on, text) {
    els.progress.hidden = !on; els.progressText.textContent = text || 'Проверяю…';
    els.checkBtn.disabled = on || !state.file; els.exportBtn.disabled = on || !state.result;
  }
  function resetResults() { state.result=null; state.workbook=null; state.rawInfo=null; els.statusCard.hidden=true; els.resultsPanel.hidden=true; els.introPanel.hidden=true; els.exportBtn.disabled=true; }
  function nextFrame() { return new Promise(resolve=>requestAnimationFrame(()=>setTimeout(resolve,0))); }
  function truncate(s,n){ s=String(s==null?'':s); return s.length>n?s.slice(0,n)+'…':s; }
  function formatNumber(n){ return new Intl.NumberFormat('ru-RU').format(n||0); }
  function severityClass(s){ return s===MPChecks.SEVERITY.CRITICAL?'critical':s===MPChecks.SEVERITY.CHECK?'check':'text'; }
  function escapeHtml(s){ return String(s==null?'':s).replace(/[&<>'"]/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[ch])); }

  document.addEventListener('DOMContentLoaded', init);
})();