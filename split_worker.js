/* Split worker: keeps heavy XLSX/Python parsing off the browser UI thread. */
let pyodide = null;
let ready = false;
let splitPath = null;
let reachPath = null;
let exportReady = false;
const splitCache = new Map();

function progress(message){ self.postMessage({type:'progress', message}); }
function jsonResult(raw){ return typeof raw === 'string' ? JSON.parse(raw) : raw; }

async function init(payload){
  if(ready) return;
  progress('Запускаю отдельное ядро Сплитов…');
  importScripts(payload.pyodideUrl + 'pyodide.js');
  pyodide = await loadPyodide({indexURL: payload.pyodideUrl});
  try{ pyodide.FS.mkdir('/app'); }catch(e){}
  const assets = payload.assets || {};
  for(const [name, text] of Object.entries(assets)){
    pyodide.FS.writeFile('/app/' + name, text, {encoding:'utf8'});
  }
  pyodide.runPython("import sys; sys.path.insert(0,'/app'); import web_api");
  ready = true;
  progress('Отдельное ядро Сплитов готово');
}

async function openFile(payload){
  if(!ready) throw new Error('Ядро Сплитов не готово');
  progress('Читаю структуру Excel…');
  const ext = payload.ext === 'xlsm' ? 'xlsm' : 'xlsx';
  splitPath = '/tmp/split_media_plan.' + ext;
  try{ pyodide.FS.unlink(splitPath); }catch(e){}
  pyodide.FS.writeFile(splitPath, new Uint8Array(payload.buffer));
  splitCache.clear();
  const raw = (() => {
    pyodide.globals.set('p', splitPath);
    return pyodide.runPython('web_api.discover(p)');
  })();
  progress('Структура медиаплана распознана');
  return jsonResult(raw);
}

async function loadSplits(payload){
  if(!ready || !splitPath) throw new Error('Сначала загрузите файл для Сплитов');
  const sheets = payload.sheets || [];
  const groups = payload.sheetGroups || [];
  const cacheKey = JSON.stringify([sheets, groups]);
  if(splitCache.has(cacheKey)){
    progress('Использую уже рассчитанный Сплит');
    return splitCache.get(cacheKey);
  }
  progress('Распознаю размещения и помесячные бюджеты…');
  pyodide.globals.set('p', splitPath);
  pyodide.globals.set('s', JSON.stringify(sheets));
  pyodide.globals.set('g', JSON.stringify(groups));
  const raw = pyodide.runPython('web_api.load_splits(p,s,g)');
  const data = jsonResult(raw);
  splitCache.set(cacheKey, data);
  progress('Проверяю контрольные суммы…');
  return data;
}

async function openReach(payload){
  if(!ready) throw new Error('Ядро не готово');
  progress('Читаю структуру медиапланов…');
  const ext = payload.ext === 'xlsm' ? 'xlsm' : 'xlsx';
  reachPath = '/tmp/reach_media_plan.' + ext;
  try{ pyodide.FS.unlink(reachPath); }catch(e){}
  pyodide.FS.writeFile(reachPath, new Uint8Array(payload.buffer));
  pyodide.globals.set('p', reachPath);
  const raw = pyodide.runPython('web_api.discover(p)');
  progress('Список медиапланов готов');
  return jsonResult(raw);
}

async function reachLoadPlan(payload){
  if(!ready || !reachPath) throw new Error('Сначала загрузите медиаплан');
  progress('Распознаю выбранный медиаплан…');
  pyodide.globals.set('p', reachPath);
  pyodide.globals.set('s', JSON.stringify(payload.sheets || []));
  return jsonResult(pyodide.runPython('web_api.load_plan(p,s)'));
}

async function reachMetadata(){
  if(!ready || !reachPath) throw new Error('Сначала загрузите медиаплан');
  progress('Подготавливаю выбранные линейки…');
  pyodide.globals.set('p', reachPath);
  return jsonResult(pyodide.runPython('web_api.multi_reach_metadata(p)'));
}

async function reachCalculate(payload){
  if(!ready) throw new Error('Ядро не готово');
  progress('Считаю охват выбранного плана…');
  pyodide.globals.set('q', JSON.stringify(payload.params || {}));
  return jsonResult(pyodide.runPython('web_api.calculate(q)'));
}

async function reachCalculateMulti(payload){
  if(!ready || !reachPath) throw new Error('Сначала загрузите медиаплан');
  progress('Считаю выбранные линейки…');
  pyodide.globals.set('p', reachPath);
  pyodide.globals.set('q', JSON.stringify(payload.params || {}));
  return jsonResult(pyodide.runPython('web_api.calculate_multi_reach(p,q)'));
}

async function exportSplits(){
  if(!ready || !splitPath) throw new Error('Нет рассчитанных Сплитов');
  progress('Готовлю Excel со Сплитами…');
  if(!exportReady){
    await pyodide.loadPackage('micropip');
    await pyodide.runPythonAsync("import micropip; await micropip.install('xlsxwriter')");
    exportReady = true;
  }
  const out = '/tmp/splits_export.xlsx';
  pyodide.globals.set('out', out);
  pyodide.runPython('web_api.export_splits(out)');
  const bytes = pyodide.FS.readFile(out);
  const copy = new Uint8Array(bytes.length);
  copy.set(bytes);
  return copy.buffer;
}

async function handle(msg){
  const id = msg.id;
  try{
    let result = null;
    if(msg.type === 'init') result = await init(msg.payload || {});
    else if(msg.type === 'open') result = await openFile(msg.payload || {});
    else if(msg.type === 'load') result = await loadSplits(msg.payload || {});
    else if(msg.type === 'export') result = await exportSplits();
    else if(msg.type === 'reachOpen') result = await openReach(msg.payload || {});
    else if(msg.type === 'reachLoadPlan') result = await reachLoadPlan(msg.payload || {});
    else if(msg.type === 'reachMetadata') result = await reachMetadata();
    else if(msg.type === 'reachCalculate') result = await reachCalculate(msg.payload || {});
    else if(msg.type === 'reachCalculateMulti') result = await reachCalculateMulti(msg.payload || {});
    else throw new Error('Неизвестная команда worker: ' + msg.type);
    if(result instanceof ArrayBuffer){
      self.postMessage({type:'result', id, result}, [result]);
    }else{
      self.postMessage({type:'result', id, result});
    }
  }catch(err){
    self.postMessage({type:'error', id, message: err && err.message ? err.message : String(err), stack: err && err.stack ? err.stack : ''});
  }
}

let queue = Promise.resolve();
self.onmessage = (event) => {
  const msg = event.data || {};
  queue = queue.then(() => handle(msg), () => handle(msg));
};
