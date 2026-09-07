(() => {
  let v16File=null, v16Path=null, v16Meta=null, v16Data=null, v16ModuleReady=false;

  const ids = {
    dz:'v16Dropzone', fi:'v16FileInput', file:'v16FileName', status:'v16Status',
    plans:'v16PlanWrap', controls:'v16Controls', k:'v16K', brandU:'v16BrandUniverse',
    autoU:'v16BrandUniverseAuto', calc:'v16Calc', metrics:'v16Metrics',
    table:'v16Table', warning:'v16Warning', diag:'v16Diagnostics'
  };

  async function ensureV16Module(){
    await corePromise;
    if(!coreReady) throw new Error('Базовый парсер не готов');
    if(v16ModuleReady) return;
    const resp=await fetch('reach_v16.py?v=1.6');
    if(!resp.ok) throw new Error('Не удалось загрузить Reach Engine v1.6');
    const txt=await resp.text();
    pyodide.FS.writeFile('/app/reach_v16.py',txt,{encoding:'utf8'});
    pyodide.runPython("import importlib, reach_v16; importlib.reload(reach_v16)");
    v16ModuleReady=true;
  }

  async function v16Call(expr, globals={}){
    await ensureV16Module();
    for(const [k,v] of Object.entries(globals)) pyodide.globals.set(k,v);
    const raw=pyodide.runPython(expr);
    return typeof raw==='string'?JSON.parse(raw):raw;
  }

  function selectedPlans(){
    if(!v16Meta?.plans) return [];
    const out=[];
    for(const p of v16Meta.plans){
      const cb=document.querySelector(`.v16-plan-cb[data-plan-id="${CSS.escape(p.id)}"]`);
      if(!cb?.checked) continue;
      const u=document.querySelector(`.v16-universe[data-plan-id="${CSS.escape(p.id)}"]`);
      out.push({id:p.id,universe:Number(u?.value||p.universe||0),meta:p});
    }
    return out;
  }

  function syncBrandUniverse(force=false){
    const input=$(ids.brandU);
    if(!input) return;
    if(!force && input.dataset.manual==='1') return;
    const plans=selectedPlans();
    const vals=plans.map(x=>Number(x.universe)).filter(x=>Number.isFinite(x)&&x>0);
    input.value=vals.length?String(Math.round(Math.max(...vals))):'';
    input.dataset.manual='0';
  }

  function renderPlanControls(){
    const wrap=$(ids.plans); wrap.innerHTML='';
    for(const p of (v16Meta?.plans||[])){
      const box=document.createElement('div'); box.className='v16-plan';
      box.innerHTML=`
        <div class="v16-plan-head">
          <label><input type="checkbox" class="v16-plan-cb" data-plan-id="${esc(p.id)}" checked>
            <strong>${esc(p.label||p.line||p.campaign||p.id)}</strong>
            <div class="hint">${esc((p.sheet_names||[]).join(', '))}</div>
          </label>
          <div class="field"><label>Universe Line</label><input class="v16-universe" data-plan-id="${esc(p.id)}" type="number" min="1" step="1" value="${p.universe?Math.round(p.universe):''}" placeholder="Введите Universe"></div>
          <div class="field"><label>ЦА из медиаплана</label><input type="text" value="${esc(p.ta_name||'')}" disabled><div class="hint">${p.flight_count||0} флайт(а) · ${p.placement_count||0} размещений</div></div>
        </div>`;
      wrap.appendChild(box);
    }
    document.querySelectorAll('.v16-plan-cb,.v16-universe').forEach(el=>el.addEventListener('change',()=>{
      syncBrandUniverse();
      if(v16Data) calculateV16().catch(console.error);
    }));
    syncBrandUniverse(true);
  }

  async function openV16File(file){
    try{
      setStatus(ids.status,'<span class="spinner"></span>Читаю медиаплан…');
      await ensureV16Module();
      const ext=(file.name.split('.').pop()||'xlsx').toLowerCase();
      v16Path='/tmp/reach_v16_media_plan.'+(ext==='xlsm'?'xlsm':'xlsx');
      const bytes=new Uint8Array(await file.arrayBuffer());
      pyodide.FS.writeFile(v16Path,bytes);
      v16File=file;
      $(ids.file).textContent=file.name;
      v16Meta=await v16Call('reach_v16.discover(p)',{p:v16Path});
      if(!v16Meta.plans?.length) throw new Error('В файле не найден рабочий медиаплан');
      renderPlanControls();
      $(ids.controls).classList.remove('hidden');
      $(ids.warning).classList.add('hidden');
      setStatus(ids.status,`✓ Найдено Line: ${v16Meta.plans.length}. Текущий алгоритм 0.52 не изменён.`,'ok');
      await calculateV16();
    }catch(e){
      console.error(e);
      setStatus(ids.status,'Ошибка v1.6: '+esc(e.message),'err');
    }
  }

  function renderMetrics(){
    const b=v16Data?.brand_total;
    const lines=v16Data?.lines||[];
    const top=b || (lines.length===1?lines[0]:null);
    const u=b?.universe || (lines.length===1?lines[0].universe:null);
    const cards=[
      ['Статус',v16Data?.status||'—'],
      ['Режим Level 2',`Quick · K=${Number(v16Data?.K||2.4).toFixed(2)}`],
      ['Universe',u?num(u,0):'—'],
      ['Показы',top?.impressions!=null?num(top.impressions,0):'—'],
      ['Reach @1+',top?.reach_1p!=null?num(top.reach_1p,0):'—'],
      ['Средняя частота',top?.avg_frequency!=null?num(top.avg_frequency,2):'—']
    ];
    $(ids.metrics).innerHTML=cards.map(([a,b])=>`<div class="metric"><div class="label">${esc(a)}</div><div class="value">${esc(b)}</div></div>`).join('');
  }

  function rowClass(level){
    if(level==='Brand')return 'v16-level-brand';
    if(level==='Line')return 'v16-level-line';
    if(level==='Flight')return 'v16-level-flight';
    return 'v16-level-channel';
  }
  function indentLabel(r){
    if(r.level==='Brand') return 'BRAND · '+r.name;
    if(r.level==='Line') return 'LINE · '+r.name;
    if(r.level==='Flight') return '↳ FLIGHT · '+r.name;
    return '↳↳ CHANNEL · '+r.name;
  }

  function renderTable(){
    const rows=v16Data?.hierarchy||[];
    let h='<thead><tr><th>Уровень</th><th>Line</th><th>Flight</th><th class="num">Universe</th><th class="num">Показы</th><th class="num">Reach @1+</th><th class="num">@1+, %</th><th class="num">Reach @2+</th><th class="num">Reach @3+</th><th class="num">Reach @4+</th><th class="num">Reach @5+</th><th class="num">Reach @6+</th><th class="num">Avg F</th></tr></thead><tbody>';
    for(const r of rows){
      const u=Number(r.universe),rp=Number(r.reach_1p);
      h+=`<tr class="${rowClass(r.level)}"><td><strong>${esc(indentLabel(r))}</strong></td><td>${esc(r.line||'')}</td><td>${esc(r.flight||'')}</td><td class="num">${num(r.universe,0)}</td><td class="num">${num(r.impressions,0)}</td><td class="num">${num(r.reach_1p,0)}</td><td class="num">${Number.isFinite(u)&&u>0&&Number.isFinite(rp)?pct(rp/u,2):'—'}</td><td class="num">${num(r.reach_2p,0)}</td><td class="num">${num(r.reach_3p,0)}</td><td class="num">${num(r.reach_4p,0)}</td><td class="num">${num(r.reach_5p,0)}</td><td class="num">${num(r.reach_6p,0)}</td><td class="num">${num(r.avg_frequency,2)}</td></tr>`;
    }
    h+='</tbody>';
    $(ids.table).innerHTML=h;
  }

  function renderDiagnostics(){
    const lines=[];
    lines.push('REACH ENGINE v1.6 — ИЗОЛИРОВАННЫЙ РАСЧЁТ');
    lines.push('Текущий production-алгоритм 0.52 не изменяется и не вызывается.');
    lines.push('');
    for(const d of (v16Data?.diagnostics||[])){
      lines.push('• '+JSON.stringify(d,null,0));
    }
    $(ids.diag).textContent=lines.join('\n');

    const warn=$(ids.warning);
    const msgs=[];
    if(v16Data?.brand_error) msgs.push(v16Data.brand_error);
    const approx=(v16Data?.diagnostics||[]).filter(x=>String(x.code||'').includes('APPROX')||x.code==='AON_STAGED_MERGE');
    if(approx.length) msgs.push('В расчёте есть явно маркированные approximation/fallback. Смотрите диагностику.');
    if(msgs.length){warn.innerHTML=msgs.map(x=>esc(x)).join('<br>');warn.classList.remove('hidden')}
    else warn.classList.add('hidden');
  }

  async function calculateV16(){
    if(!v16Path||!v16Meta) return;
    const plans=selectedPlans();
    if(!plans.length){setStatus(ids.status,'Выберите хотя бы одну Line.','err');return}
    const K=Number($(ids.k).value||2.4);
    const bu=$(ids.brandU).value.trim();
    const q={
      selected_plan_ids:plans.map(x=>x.id),
      universes:Object.fromEntries(plans.map(x=>[x.id,x.universe])),
      K,
      brand_universe:bu===''?null:Number(bu)
    };
    try{
      setStatus(ids.status,'<span class="spinner"></span>Reach Engine v1.6 считает Levels 1–7…');
      v16Data=await v16Call('reach_v16.calculate(p,q)',{p:v16Path,q:JSON.stringify(q)});
      renderMetrics();renderTable();renderDiagnostics();
      setStatus(ids.status,`✓ v1.6 рассчитан · ${v16Data.lines?.length||0} Line · production 0.52 не затронут`,'ok');
    }catch(e){
      console.error(e);
      setStatus(ids.status,'Ошибка v1.6: '+esc(e.message),'err');
      const warn=$(ids.warning);warn.textContent=e.message;warn.classList.remove('hidden');
    }
  }

  function bind(){
    const dz=$(ids.dz), fi=$(ids.fi);
    if(!dz||!fi) return;
    dz.addEventListener('click',()=>fi.click());
    ['dragenter','dragover'].forEach(ev=>dz.addEventListener(ev,e=>{e.preventDefault();dz.classList.add('drag')}));
    ['dragleave','drop'].forEach(ev=>dz.addEventListener(ev,e=>{e.preventDefault();dz.classList.remove('drag')}));
    dz.addEventListener('drop',e=>{if(e.dataTransfer.files[0])openV16File(e.dataTransfer.files[0])});
    fi.addEventListener('change',()=>{if(fi.files[0])openV16File(fi.files[0])});
    $(ids.calc).addEventListener('click',()=>calculateV16());
    $(ids.k).addEventListener('change',()=>v16Data&&calculateV16());
    $(ids.brandU).addEventListener('change',()=>{ $(ids.brandU).dataset.manual=$(ids.brandU).value.trim()?'1':'0'; if(v16Data)calculateV16()});
    $(ids.autoU).addEventListener('click',()=>{syncBrandUniverse(true); if(v16Data)calculateV16()});
  }

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',bind); else bind();
  window.ReachEngineV16={calculate:calculateV16,openFile:openV16File};
})();