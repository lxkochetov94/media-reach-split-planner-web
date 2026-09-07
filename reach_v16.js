(() => {
  let v16File=null, v16Path=null, v16Meta=null, v16Data=null, v16ModuleReady=false;

  const ids = {
    dz:'v16Dropzone', fi:'v16FileInput', file:'v16FileName', status:'v16Status',
    plans:'v16PlanWrap', controls:'v16Controls', mode:'v16L2Mode', k:'v16K',
    L:'v16L', B:'v16B', D:'v16D', brandU:'v16BrandUniverse',
    autoU:'v16BrandUniverseAuto', targetF:'v16TargetFrequency', calc:'v16Calc',
    metrics:'v16Metrics', table:'v16Table', warning:'v16Warning', diag:'v16Diagnostics',
    method:'v16MethodSummary', profile:'v16FrequencyProfile'
  };

  async function ensureV16Module(){
    await corePromise;
    if(!coreReady) throw new Error('Базовый парсер не готов');
    if(v16ModuleReady) return;
    const resp=await fetch('reach_v16.py?v=1.6.2');
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

  function v16ErrorMessage(error){
    const raw=String(error?.message||error||'Неизвестная ошибка');
    const lines=raw.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
    if(!lines.length)return 'Неизвестная ошибка';
    const last=lines[lines.length-1].replace(/^(?:V16Error|ValueError|TypeError|RuntimeError):\s*/,'');
    return last.length>420?last.slice(0,417)+'…':last;
  }

  function nval(id){
    const raw=$(id)?.value?.trim?.()??'';
    return raw===''?null:Number(raw);
  }

  function selectedPlans(){
    if(!v16Meta?.plans) return [];
    const out=[];
    for(const p of v16Meta.plans){
      const cb=document.querySelector(`.v16-plan-cb[data-plan-id="${CSS.escape(p.id)}"]`);
      if(!cb?.checked) continue;
      const u=document.querySelector(`.v16-universe[data-plan-id="${CSS.escape(p.id)}"]`);
      const ud=document.querySelector(`.v16-ud[data-plan-id="${CSS.escape(p.id)}"]`);
      out.push({
        id:p.id,
        universe:Number(u?.value||p.universe||0),
        webDeviceUniverse:ud?.value?.trim()?Number(ud.value):null,
        meta:p
      });
    }
    return out;
  }

  function syncBrandUniverse(force=false){
    const input=$(ids.brandU);
    if(!input) return;
    if(!force && input.dataset.manual==='1') return;
    const vals=selectedPlans().map(x=>Number(x.universe)).filter(x=>Number.isFinite(x)&&x>0);
    input.value=vals.length?String(Math.round(Math.max(...vals))):'';
    input.dataset.manual='0';
  }

  function toggleL2Controls(){
    const mode=$(ids.mode)?.value||'AUTO';
    document.querySelectorAll('.v16-quick-setting').forEach(x=>x.classList.toggle('hidden',mode==='ADVANCED_WEB'));
    document.querySelectorAll('.v16-advanced-setting').forEach(x=>x.classList.toggle('hidden',mode==='QUICK'));
    document.querySelectorAll('.v16-ud-field').forEach(x=>x.classList.toggle('hidden',mode==='QUICK'));
  }

  function renderPlanControls(){
    const wrap=$(ids.plans); wrap.innerHTML='';
    for(const p of (v16Meta?.plans||[])){
      const rec=p.advanced_recommended||{};
      const box=document.createElement('div'); box.className='v16-plan';
      box.innerHTML=`
        <div class="v16-plan-head">
          <label class="v16-plan-title"><input type="checkbox" class="v16-plan-cb" data-plan-id="${esc(p.id)}" checked>
            <span><strong>${esc(p.label||p.line||p.campaign||p.id)}</strong>
            <span class="hint">${esc((p.sheet_names||[]).join(', '))}</span></span>
          </label>
          <div class="field"><label>Universe Line</label><input class="v16-universe" data-plan-id="${esc(p.id)}" type="number" min="1" step="1" value="${p.universe?Math.round(p.universe):''}" placeholder="Введите Universe"></div>
          <div class="field"><label>ЦА из медиаплана</label><input type="text" value="${esc(p.ta_name||'')}" disabled><div class="hint">${p.flight_count||0} флайт(а) · ${p.placement_count||0} размещений</div></div>
          <div class="field v16-ud-field"><label>Web-device Universe U<sub>D</sub></label><input class="v16-ud" data-plan-id="${esc(p.id)}" type="number" min="1" step="1" placeholder="Нужен для Advanced Web"><div class="hint">Не подставляется автоматически. Рекомендовано по ЦА: B=${num(rec.B,2)}, D=${num(rec.D,2)}.</div></div>
        </div>`;
      wrap.appendChild(box);
    }
    document.querySelectorAll('.v16-plan-cb,.v16-universe,.v16-ud').forEach(el=>el.addEventListener('change',()=>{
      syncBrandUniverse();
      if(v16Data) calculateV16().catch(console.error);
    }));
    syncBrandUniverse(true);
    toggleL2Controls();
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
      setStatus(ids.status,`✓ Найдено Line: ${v16Meta.plans.length}. Старый алгоритм 0.52 не изменён.`,'ok');
      await calculateV16();
    }catch(e){
      console.error(e);
      setStatus(ids.status,'Ошибка v1.6: '+esc(v16ErrorMessage(e)),'err');
    }
  }

  function targetFrequency(){return Math.max(1,Math.min(6,Number($(ids.targetF)?.value||3)))}
  function reachAt(obj,k){return obj?.[`reach_${k}p`];}
  function topResult(){
    const b=v16Data?.brand_total;
    const lines=v16Data?.lines||[];
    return b || (lines.length===1?lines[0]:null);
  }
  function topUniverse(){
    const t=topResult();
    return t?.universe || (v16Data?.lines?.length===1?v16Data.lines[0].universe:null);
  }
  function effectiveL2Label(){
    const modes=[...new Set((v16Data?.lines||[]).map(x=>x?.l2?.effective_mode).filter(Boolean))];
    if(!modes.length)return '—';
    if(modes.length>1)return modes.join(' + ');
    const m=modes[0];
    if(m==='QUICK'){
      const ks=[...new Set((v16Data?.lines||[]).map(x=>x?.l2?.K).filter(x=>x!=null))];
      return `Quick${ks.length===1?' · K='+num(ks[0],2):''}`;
    }
    if(m==='ADVANCED_WEB')return 'Advanced Web';
    return m;
  }

  function renderMetrics(){
    const top=topResult(), u=topUniverse(), tf=targetFrequency();
    const r1=reachAt(top,1), rt=reachAt(top,tf);
    const cards=[
      ['Статус',v16Data?.status||'—',''],
      ['Level 2',effectiveL2Label(),''],
      ['Universe',u?num(u,0):'—',''],
      ['Показы',top?.impressions!=null?num(top.impressions,0):'—',''],
      ['Reach @1+ · люди',r1!=null?num(r1,0):'—',''],
      ['Reach @1+ · %',u&&r1!=null?pct(r1/u,2):'—',''],
      [`Reach @${tf}+ · люди`,rt!=null?num(rt,0):'—','Выбранная эффективная частота'],
      [`Reach @${tf}+ · %`,u&&rt!=null?pct(rt/u,2):'—','Выбранная эффективная частота'],
      ['Средняя Human Frequency',top?.avg_frequency!=null?num(top.avg_frequency,2):'—','']
    ];
    $(ids.metrics).innerHTML=cards.map(([a,b,c])=>`<div class="metric"><div class="label">${esc(a)}</div><div class="value">${esc(b)}</div>${c?`<div class="v16-note">${esc(c)}</div>`:''}</div>`).join('');
  }

  function reachCell(r,k){
    const u=Number(r.universe), val=Number(r[`reach_${k}p`]);
    if(!Number.isFinite(val))return '<span class="na">—</span>';
    const pp=Number.isFinite(u)&&u>0?val/u:null;
    return `<strong>${num(val,0)}</strong><span class="v16-pct">${pp==null?'—':pct(pp,2)}</span>`;
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
    let h='<thead><tr><th>Уровень</th><th>Line</th><th>Flight</th><th class="num">Universe</th><th class="num">Показы</th>'+
      [1,2,3,4,5,6].map(k=>`<th class="num">Reach @${k}+<span class="v16-th-sub">люди · % U</span></th>`).join('')+
      '<th class="num">Avg F</th></tr></thead><tbody>';
    for(const r of rows){
      h+=`<tr class="${rowClass(r.level)}"><td><strong>${esc(indentLabel(r))}</strong></td><td>${esc(r.line||'')}</td><td>${esc(r.flight||'')}</td><td class="num">${num(r.universe,0)}</td><td class="num">${num(r.impressions,0)}</td>`;
      for(let k=1;k<=6;k++)h+=`<td class="num v16-reach-cell">${reachCell(r,k)}</td>`;
      h+=`<td class="num">${num(r.avg_frequency,2)}</td></tr>`;
    }
    h+='</tbody>';
    $(ids.table).innerHTML=h;
  }

  function renderFrequencyProfile(){
    const top=topResult(), u=topUniverse(), wrap=$(ids.profile);
    if(!top||!u){wrap.innerHTML='<div class="hint">Нет итогового результата для профиля.</div>';return}
    const tf=targetFrequency();
    let h='<div class="v16-profile-grid">';
    for(let k=1;k<=6;k++){
      const val=Number(reachAt(top,k)||0), share=Math.max(0,Math.min(1,val/u));
      h+=`<div class="v16-profile-row ${k===tf?'selected':''}">
        <div class="v16-profile-label">@${k}+</div>
        <div class="v16-profile-track"><span style="width:${(share*100).toFixed(3)}%"></span></div>
        <div class="v16-profile-value"><strong>${num(val,0)}</strong><span>${pct(share,2)}</span></div>
      </div>`;
    }
    h+='</div>';
    wrap.innerHTML=h;
  }

  function renderMethodSummary(){
    const ds=v16Data?.diagnostics||[], lines=v16Data?.lines||[];
    const l2=lines.map(x=>x.l2).filter(Boolean);
    const l5rel=ds.filter(x=>x.code==='DEFAULT_RELAXED_FOR_GLOBAL_FEASIBILITY'&&x.level===5);
    const l6rel=ds.filter(x=>x.code==='DEFAULT_RELAXED_FOR_GLOBAL_FEASIBILITY'&&x.level===6);
    const cap=ds.filter(x=>x.code==='RESIDUAL_CAP_OVERRIDDEN_BY_GLOBAL_FEASIBILITY');
    const aon=ds.filter(x=>x.code==='AON_STAGED_MERGE');
    const quick=l2.filter(x=>x.effective_mode==='QUICK').length;
    const adv=l2.filter(x=>x.effective_mode==='ADVANCED_WEB').length;
    const l2Text=adv&&quick?`Advanced Web: ${adv} Line · Quick: ${quick} Line`:adv?`Advanced Web · ${adv} Line`:`Quick fallback · ${quick||l2.length} Line`;
    const bvals=[...new Set(l2.map(x=>x.B).filter(x=>x!=null).map(x=>num(x,2)))];
    const dvals=[...new Set(l2.map(x=>x.D).filter(x=>x!=null).map(x=>num(x,2)))];
    const cards=[
      ['L2 · Technical → People',l2Text,adv?`B: ${bvals.join(' / ')} · D: ${dvals.join(' / ')} · L=68д`:'K=2,40 используется только как Quick fallback'],
      ['L3B · Effective Reach','Poisson-Lognormal · σ=2,50','Exact buckets 1/2/3/4/5/6+'],
      ['L5 · Channels → Flight','ρ target = −0,35',l5rel.length?`Global feasibility relaxation: ${l5rel.length}`:'Relaxation не потребовался'],
      ['L6 · Flights → Line','Temporal + residual ≤10%',`${l6rel.length?'λ-relaxation: '+l6rel.length:'λ-relaxation не потребовался'}${cap.length?' · residual cap override':''}${aon.length?' · AON staged':''}`],
      ['L7 · Lines → Brand',v16Data?.brand_total?'Brand merge рассчитан':'Brand total не рассчитан',v16Data?.brand_error||'Neutral/structured path по доступным данным']
    ];
    $(ids.method).innerHTML=cards.map(([a,b,c])=>`<div class="v16-method-card"><div class="label">${esc(a)}</div><strong>${esc(b)}</strong><div class="v16-note">${esc(c)}</div></div>`).join('');
  }

  function renderDiagnostics(){
    const lines=[];
    lines.push('REACH ENGINE v1.6 — ИЗОЛИРОВАННЫЙ РАСЧЁТ');
    lines.push('Текущий production-алгоритм 0.52 не изменяется и не вызывается.');
    lines.push('');
    for(const d of (v16Data?.diagnostics||[])) lines.push('• '+JSON.stringify(d,null,0));
    $(ids.diag).textContent=lines.join('\n');

    const warn=$(ids.warning), msgs=[];
    if(v16Data?.brand_error) msgs.push(v16Data.brand_error);
    const approx=(v16Data?.diagnostics||[]).filter(x=>String(x.code||'').includes('APPROX')||x.code==='AON_STAGED_MERGE'||x.code==='L2_AUTO_FALLBACK_QUICK');
    if(approx.length) msgs.push('В расчёте есть явно маркированные approximation/fallback. Смотрите блок «Как посчитано» и диагностику.');
    if(msgs.length){warn.innerHTML=msgs.map(x=>esc(x)).join('<br>');warn.classList.remove('hidden')}
    else warn.classList.add('hidden');
  }

  function rerenderV16(){
    if(!v16Data)return;
    renderMetrics();renderMethodSummary();renderFrequencyProfile();renderTable();renderDiagnostics();
  }

  async function calculateV16(){
    if(!v16Path||!v16Meta) return;
    const plans=selectedPlans();
    if(!plans.length){setStatus(ids.status,'Выберите хотя бы одну Line.','err');return}
    const bu=$(ids.brandU).value.trim();
    const B=nval(ids.B), D=nval(ids.D);
    const q={
      selected_plan_ids:plans.map(x=>x.id),
      universes:Object.fromEntries(plans.map(x=>[x.id,x.universe])),
      l2_mode:$(ids.mode).value,
      K:Number($(ids.k).value||2.4),
      advanced:{
        L:Number($(ids.L).value||68),
        B:B,
        D:D,
        web_device_universes:Object.fromEntries(plans.filter(x=>x.webDeviceUniverse).map(x=>[x.id,x.webDeviceUniverse]))
      },
      brand_universe:bu===''?null:Number(bu)
    };
    try{
      setStatus(ids.status,'<span class="spinner"></span>Reach Engine v1.6 считает Levels 1–7…');
      v16Data=await v16Call('reach_v16.calculate(p,q)',{p:v16Path,q:JSON.stringify(q)});
      rerenderV16();
      setStatus(ids.status,`✓ v1.6 рассчитан · ${v16Data.lines?.length||0} Line · production 0.52 не затронут`,'ok');
    }catch(e){
      console.error(e);
      const message=v16ErrorMessage(e);
      setStatus(ids.status,'Ошибка v1.6: '+esc(message),'err');
      const warn=$(ids.warning);warn.textContent=message;warn.classList.remove('hidden');
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
    $(ids.mode).addEventListener('change',()=>{toggleL2Controls(); if(v16Data)calculateV16()});
    [ids.k,ids.L,ids.B,ids.D].forEach(id=>$(id).addEventListener('change',()=>v16Data&&calculateV16()));
    $(ids.targetF).addEventListener('change',()=>rerenderV16());
    $(ids.brandU).addEventListener('change',()=>{ $(ids.brandU).dataset.manual=$(ids.brandU).value.trim()?'1':'0'; if(v16Data)calculateV16()});
    $(ids.autoU).addEventListener('click',()=>{syncBrandUniverse(true); if(v16Data)calculateV16()});
    toggleL2Controls();
  }

  if(document.readyState==='loading') document.addEventListener('DOMContentLoaded',bind); else bind();
  window.ReachEngineV16={calculate:calculateV16,openFile:openV16File};
})();