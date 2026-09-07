(() => {
  let v16File=null, v16Path=null, v16Meta=null, v16Data=null, v16ModuleReady=false;

  const ids={
    dz:'v16Dropzone',fi:'v16FileInput',file:'v16FileName',status:'v16Status',
    plans:'v16PlanWrap',controls:'v16Controls',mode:'v16L2Mode',k:'v16K',L:'v16L',B:'v16B',D:'v16D',
    brandU:'v16BrandUniverse',autoU:'v16BrandUniverseAuto',targetF:'v16TargetFrequency',calc:'v16Calc',
    metrics:'v16Metrics',table:'v16Table',warning:'v16Warning',diag:'v16Diagnostics',
    profile:'v16FrequencyProfile',exact:'v16ExactFrequency',contrib:'v16ContributionTable',
    inputAudit:'v16InputAudit',l2Decision:'v16L2Decision',modelMap:'v16ModelMap',results:'v16Results'
  };

  async function ensureV16Module(){
    await corePromise;
    if(!coreReady) throw new Error('Базовый парсер не готов');
    if(v16ModuleReady) return;
    const resp=await fetch('reach_v16.py?v=1.6.4');
    if(!resp.ok) throw new Error('Не удалось загрузить Reach Engine v1.6');
    const txt=await resp.text();
    pyodide.FS.writeFile('/app/reach_v16.py',txt,{encoding:'utf8'});
    pyodide.runPython("import importlib, reach_v16; importlib.reload(reach_v16)");
    v16ModuleReady=true;
  }

  async function v16Call(expr,globals={}){
    await ensureV16Module();
    for(const [k,v] of Object.entries(globals))pyodide.globals.set(k,v);
    const raw=pyodide.runPython(expr);
    return typeof raw==='string'?JSON.parse(raw):raw;
  }

  function errorMessage(error){
    const raw=String(error?.message||error||'Неизвестная ошибка');
    const lines=raw.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
    if(!lines.length)return 'Неизвестная ошибка';
    const last=lines[lines.length-1].replace(/^(?:reach_v16\.)?(?:V16Error|ValueError|TypeError|RuntimeError):\s*/,'');
    return last.length>420?last.slice(0,417)+'…':last;
  }

  function nval(id){
    const raw=$(id)?.value?.trim?.()??'';
    return raw===''?null:Number(raw);
  }

  function targetFrequency(){return Math.max(1,Math.min(6,Number($(ids.targetF)?.value||3)))}
  function reachAt(obj,k){return obj?.[`reach_${k}p`]}
  function modelCatalog(){return v16Data?.model_catalog||v16Meta?.model_catalog||{}}

  function selectedPlans(){
    if(!v16Meta?.plans)return [];
    return v16Meta.plans.flatMap(p=>{
      const cb=document.querySelector(`.v16-plan-cb[data-plan-id="${CSS.escape(p.id)}"]`);
      if(!cb?.checked)return [];
      const u=document.querySelector(`.v16-universe[data-plan-id="${CSS.escape(p.id)}"]`);
      const ud=document.querySelector(`.v16-ud[data-plan-id="${CSS.escape(p.id)}"]`);
      return [{
        id:p.id,
        universe:Number(u?.value||p.universe||0),
        webDeviceUniverse:ud?.value?.trim()?Number(ud.value):null,
        meta:p
      }];
    });
  }

  function syncBrandUniverse(force=false){
    const input=$(ids.brandU);
    if(!input)return;
    if(!force&&input.dataset.manual==='1')return;
    const vals=selectedPlans().map(x=>x.universe).filter(x=>Number.isFinite(x)&&x>0);
    input.value=vals.length?String(Math.round(Math.max(...vals))):'';
    input.dataset.manual='0';
  }

  function badge(text,kind='neutral'){return `<span class="v16-badge ${kind}">${esc(text)}</span>`}
  function sourceLabel(src){
    return ({
      AGE_WIDTH_APPROXIMATION:'по возрасту ЦА',
      BASE_FALLBACK:'базовое значение',
      USER_OVERRIDE:'ручное значение'
    })[src]||src||'—';
  }
  function fmtRange(a,b,d=2){
    if(a==null||b==null)return '—';
    return Math.abs(Number(a)-Number(b))<1e-9?num(a,d):`${num(a,d)}–${num(b,d)}`;
  }

  function renderPlanControls(){
    const wrap=$(ids.plans);wrap.innerHTML='';
    for(const p of v16Meta?.plans||[]){
      const rec=p.advanced_recommended||{}, prof=p.input_profile||{};
      const box=document.createElement('div');box.className='v16-plan';
      const readiness=prof.rows?Math.round(100*(prof.l1_ready_rows||0)/prof.rows):0;
      box.innerHTML=`
        <div class="v16-plan-head">
          <label class="v16-plan-title">
            <input type="checkbox" class="v16-plan-cb" data-plan-id="${esc(p.id)}" checked>
            <span><strong>${esc(p.label||p.line||p.campaign||p.id)}</strong>
              <span class="hint">${esc((p.sheet_names||[]).join(', '))}</span>
            </span>
          </label>
          <div class="field"><label>Universe Line</label><input class="v16-universe" data-plan-id="${esc(p.id)}" type="number" min="1" step="1" value="${p.universe?Math.round(p.universe):''}" placeholder="Обязательный вход"></div>
          <div class="v16-plan-facts">
            <span>ЦА: <strong>${esc(p.ta_name||'не распознана')}</strong></span>
            <span>${p.flight_count||0} флайт(а) · ${p.placement_count||0} размещений</span>
            <span>Готовность L1: <strong>${readiness}%</strong></span>
          </div>
        </div>
        <div class="v16-auto-strip">
          <div><span class="v16-auto-label">Авто по ЦА</span><strong>B = ${num(rec.B,2)}</strong><small>диапазон для этой ЦА: ${fmtRange(rec.B_min,rec.B_max)}</small></div>
          <div><span class="v16-auto-label">Авто по ЦА</span><strong>D = ${num(rec.D,2)}</strong><small>диапазон для этой ЦА: ${fmtRange(rec.D_min,rec.D_max)}</small></div>
          <div><span class="v16-auto-label">Методология</span><strong>L = 68 дней</strong><small>Chromium-class baseline</small></div>
        </div>
        <details class="v16-plan-advanced">
          <summary>Есть измеряемый Web-device Universe U<sub>D</sub>?</summary>
          <div class="v16-plan-advanced-body">
            <div class="field v16-ud-field"><label>U<sub>D</sub> для этой Line</label><input class="v16-ud" data-plan-id="${esc(p.id)}" type="number" min="1" step="1" placeholder="Оставьте пустым, если данных нет"></div>
            <div class="v16-note">U<sub>D</sub> не выдумываем. Если его нет, AUTO использует Quick fallback. Если есть — AUTO включает Advanced Web 2A→2B→2C.</div>
          </div>
        </details>`;
      wrap.appendChild(box);
    }
    document.querySelectorAll('.v16-plan-cb,.v16-universe,.v16-ud').forEach(el=>el.addEventListener('change',()=>{
      syncBrandUniverse();
      renderPrecalc();
    }));
    syncBrandUniverse(true);
  }

  function renderInputAudit(){
    const wrap=$(ids.inputAudit);
    if(!wrap)return;
    const plans=selectedPlans();
    if(!plans.length){wrap.innerHTML='<div class="warning">Не выбрано ни одной Line.</div>';return}
    wrap.innerHTML='<div class="v16-audit-grid">'+plans.map(({meta:p})=>{
      const x=p.input_profile||{}, rows=x.rows||0;
      const l1=x.l1_ready_rows||0;
      const reach=x.supplied_reach_rows||0;
      const ifRows=x.impressions_frequency_rows||0;
      const dates=x.dated_rows||0;
      const ready=rows&&l1===rows;
      return `<div class="v16-audit-card">
        <div class="v16-audit-title">${ready?badge('L1 готов','ok'):badge('проверить входы','warn')}<strong>${esc(p.label||p.id)}</strong></div>
        <div class="v16-audit-stats">
          <span>Строк: <b>${rows}</b></span><span>Supplied Reach: <b>${reach}</b></span>
          <span>I + F: <b>${ifRows}</b></span><span>С датами: <b>${dates}</b></span>
          <span>Площадок: <b>${x.platforms||0}</b></span><span>Каналов: <b>${x.channels||0}</b></span>
        </div>
        <div class="v16-note">${ready?'Для каждой строки есть supplied Reach либо пара Impressions + Frequency.':'Часть строк не позволяет получить Technical Reach. При расчёте будет явная ошибка или пропуск строки без достаточных данных.'}</div>
      </div>`;
    }).join('')+'</div>';
  }

  function currentMode(){return $(ids.mode)?.value||'AUTO'}
  function renderL2Decision(){
    const wrap=$(ids.l2Decision);if(!wrap)return;
    const mode=currentMode(), plans=selectedPlans();
    if(!plans.length){wrap.innerHTML='';return}
    wrap.innerHTML='<div class="v16-decision-list">'+plans.map(p=>{
      const rec=p.meta.advanced_recommended||{};
      const hasUD=Number.isFinite(p.webDeviceUniverse)&&p.webDeviceUniverse>0;
      let effective,why,kind;
      if(mode==='QUICK'){effective='QUICK';why='Режим принудительно выбран в экспертных настройках.';kind='fallback'}
      else if(mode==='ADVANCED_WEB'){
        effective=hasUD?'ADVANCED WEB':'НЕ ГОТОВ';
        why=hasUD?'Есть U_D, поэтому доступны browser/device saturation.':'Для принудительного Advanced Web нужен измеряемый U_D.';
        kind=hasUD?'advanced':'error';
      }else{
        effective=hasUD?'ADVANCED WEB':'QUICK FALLBACK';
        why=hasUD?'AUTO видит U_D и включает полную цепочку 2A → 2B → 2C.':'U_D не задан. Движок не придумывает device universe и честно использует Quick fallback.';
        kind=hasUD?'advanced':'fallback';
      }
      const path=hasUD&&mode!=='QUICK'
        ?`<div class="v16-formula-path"><span>R<sub>tech</sub></span><b>→</b><span>2A churn<br><small>L=68</small></span><b>→</b><span>2B browser<br><small>B=${num(rec.B,2)}</small></span><b>→</b><span>2C device<br><small>D=${num(rec.D,2)}</small></span><b>→</b><span>R<sub>people</sub></span></div>`
        :`<div class="v16-formula-path compact"><span>R<sub>tech</sub></span><b>→</b><span>÷ K</span><b>→</b><span>R<sub>people</sub></span></div>`;
      return `<div class="v16-decision ${kind}">
        <div class="v16-decision-head"><strong>${esc(p.meta.label||p.id)}</strong>${badge(effective,kind==='advanced'?'ok':kind==='error'?'err':'warn')}</div>
        ${path}
        <div class="v16-decision-why">${esc(why)}</div>
        <div class="v16-param-row">
          <span><b>B ${num(rec.B,2)}</b><small>${sourceLabel(rec.B_source)} · диапазон ${fmtRange(rec.B_min,rec.B_max)}</small></span>
          <span><b>D ${num(rec.D,2)}</b><small>${sourceLabel(rec.D_source)} · диапазон ${fmtRange(rec.D_min,rec.D_max)}</small></span>
          <span><b>U_D ${hasUD?num(p.webDeviceUniverse,0):'нет'}</b><small>${hasUD?'измеряемый input':'не подставляется'}</small></span>
        </div>
      </div>`;
    }).join('')+'</div>';
  }

  function renderModelMap(){
    const wrap=$(ids.modelMap);if(!wrap)return;
    const c=modelCatalog(), plans=selectedPlans();
    if(!c.level2){wrap.innerHTML='<div class="hint">Каталог модели загрузится вместе с медиапланом.</div>';return}
    const selectedRec=plans[0]?.meta?.advanced_recommended||{};
    const l2=c.level2||{},l3=c.level3||{},l5=c.level5||{},l6=c.level6||{};
    const rho=l3.temporal_rho_profiles||{};
    const q=(l6.gap_curve||[]).map(x=>`${x.days}д=${(100*x.overlap).toFixed(x.overlap*100%1?1:0)}%`).join(' · ');
    const mu=(l6.universe_multiplier_points||[]).map(x=>`${x.universe/1e6}м→${num(x.multiplier,2)}`).join(' · ');
    const bdev=(l2.browser_by_device||[]).map(x=>`${x.segment}: ${x.value==null?'N/A':num(x.value,2)}`).join(' · ');
    const churn=(l2.churn_reference||[]).map(x=>`${x.days}д: ${pct(x.probability,1)}`).join(' · ');
    wrap.innerHTML=`
      <div class="v16-model-card emphasis">
        <div class="v16-model-level">LEVEL 2</div><strong>Technical Reach → люди</strong>
        <div class="v16-model-main">B ${num(selectedRec.B,2)} <small>(${fmtRange(selectedRec.B_min,selectedRec.B_max)})</small> · D ${num(selectedRec.D,2)} <small>(${fmtRange(selectedRec.D_min,selectedRec.D_max)})</small></div>
        <p>Advanced: churn → browser saturation → device saturation. Quick K=${num(c.level2.quick_k,2)} остаётся только fallback.</p>
        <div class="v16-model-scale"><span>L=68д</span><span>Browser age: 1,60–1,90</span><span>Device age: 1,74–2,45</span></div>
        <p class="v16-micro"><b>Browser по устройствам:</b> ${esc(bdev)}</p>
        <p class="v16-micro"><b>Churn reference:</b> ${esc(churn)}</p>
      </div>
      <div class="v16-model-card">
        <div class="v16-model-level">LEVEL 3</div><strong>Время + Effective Reach</strong>
        <div class="v16-model-main">ρ: LOW ${num(rho.LOW,2)} · BASE ${num(rho.BASE,2)} · HIGH ${num(rho.HIGH,2)}</div>
        <p>Частотная форма: ${esc(l3.sigma_default!=null?'Poisson-Lognormal, σ='+num(l3.sigma_default,2):'Poisson-Lognormal')}.</p>
        ${l3.sigma_calibration_iqr?'<div class="v16-model-scale"><span>σ calibration IQR '+fmtRange(l3.sigma_calibration_iqr[0],l3.sigma_calibration_iqr[1])+'</span></div>':''}
      </div>
      <div class="v16-model-card">
        <div class="v16-model-level">LEVEL 4</div><strong>Площадки → канал</strong>
        <div class="v16-model-main">Audience Family normalization</div>
        <p>Сначала объединяем общий audience pool, затем семьи. Для 3+ structured constraints сохраняются; neutral не стирает известные M<sub>ij</sub>.</p>
      </div>
      <div class="v16-model-card">
        <div class="v16-model-level">LEVEL 5</div><strong>Каналы → флайт</strong>
        <div class="v16-model-main">ρ target = ${num(l5.rho_channel_target,2)||'-0,35'}</div>
        <p>Для 3+ каналов один общий λ ослабляет MODEL_DEFAULT к 0 только если этого требует global feasibility.</p>
      </div>
      <div class="v16-model-card">
        <div class="v16-model-level">LEVEL 6</div><strong>Флайты → Line</strong>
        <div class="v16-model-main">Temporal overlap + residual ≤ ${Math.round(100*(l6.residual_cap??0.10))}%</div>
        <p class="v16-micro">${esc(q)}</p>
        <div class="v16-model-scale"><span>M_U: ${esc(mu)}</span></div>
      </div>
      <div class="v16-model-card">
        <div class="v16-model-level">LEVEL 7</div><strong>Lines → Brand</strong>
        <div class="v16-model-main">Единая Brand TA · ρ line = 0</div>
        <p>BrandAddressabilityMap включается только при реальных структурных ограничениях: география, CRM, ретаргетинг и специальные pools.</p>
      </div>`;
  }

  function renderPrecalc(){
    renderInputAudit();renderL2Decision();renderModelMap();
  }

  function topResult(){
    const b=v16Data?.brand_total,lines=v16Data?.lines||[];
    return b||(lines.length===1?lines[0]:null);
  }
  function topUniverse(){
    const t=topResult();
    return t?.universe||(v16Data?.lines?.length===1?v16Data.lines[0].universe:null);
  }
  function effectiveL2Label(){
    const modes=[...new Set((v16Data?.lines||[]).map(x=>x?.l2?.effective_mode).filter(Boolean))];
    if(!modes.length)return '—';
    if(modes.length>1)return 'Смешанный: '+modes.join(' + ');
    if(modes[0]==='ADVANCED_WEB')return 'Advanced Web 2A→2B→2C';
    const ks=[...new Set((v16Data?.lines||[]).map(x=>x?.l2?.K).filter(x=>x!=null))];
    return `Quick fallback${ks.length===1?' · K='+num(ks[0],2):''}`;
  }

  function renderMetrics(){
    const top=topResult(),u=topUniverse(),tf=targetFrequency();
    const r1=reachAt(top,1),rt=reachAt(top,tf);
    const lineForDedup=(v16Data?.lines||[]).length===1?v16Data.lines[0]:top;
    const dedup=lineForDedup?.dedup_people,rate=lineForDedup?.dedup_rate;
    const cards=[
      ['Статус',v16Data?.status||'—',''],
      ['Режим Level 2',effectiveL2Label(),''],
      ['Universe',u?num(u,0):'—',''],
      ['Показы',top?.impressions!=null?num(top.impressions,0):'—',''],
      ['Reach @1+ · люди',r1!=null?num(r1,0):'—',''],
      ['Reach @1+ · %',u&&r1!=null?pct(r1/u,2):'—',''],
      [`Reach @${tf}+ · люди`,rt!=null?num(rt,0):'—','Выбранный KPI'],
      [`Reach @${tf}+ · %`,u&&rt!=null?pct(rt/u,2):'—','Выбранный KPI'],
      ['Средняя human frequency',top?.avg_frequency!=null?num(top.avg_frequency,2):'—',''],
      ['Дедупликация',dedup!=null?num(dedup,0):'—',rate!=null?pct(rate,2)+' от gross reach sum':'']
    ];
    $(ids.metrics).innerHTML=cards.map(([a,b,c])=>`<div class="metric"><div class="label">${esc(a)}</div><div class="value">${esc(b)}</div>${c?`<div class="v16-note">${esc(c)}</div>`:''}</div>`).join('');
  }

  function renderFrequencyProfile(){
    const top=topResult(),u=topUniverse(),wrap=$(ids.profile);
    if(!top||!u){wrap.innerHTML='<div class="hint">Нет итогового результата.</div>';return}
    const tf=targetFrequency();
    wrap.innerHTML='<div class="v16-profile-grid">'+[1,2,3,4,5,6].map(k=>{
      const val=Number(reachAt(top,k)||0),share=Math.max(0,Math.min(1,val/u));
      return `<div class="v16-profile-row ${k===tf?'selected':''}">
        <div class="v16-profile-label">@${k}+</div>
        <div class="v16-profile-track"><span style="width:${(share*100).toFixed(3)}%"></span></div>
        <div class="v16-profile-value"><strong>${num(val,0)}</strong><span>${pct(share,2)}</span></div>
      </div>`;
    }).join('')+'</div>';
  }

  function renderExactFrequency(){
    const top=topResult(),u=topUniverse(),wrap=$(ids.exact);
    if(!top||!u||!Array.isArray(top.exact_counts)){wrap.innerHTML='<div class="hint">Exact buckets недоступны.</div>';return}
    const reached=Number(top.reach_1p||0);
    const labels=['ровно 1','ровно 2','ровно 3','ровно 4','ровно 5','6+'];
    wrap.innerHTML='<div class="v16-exact-grid">'+top.exact_counts.map((v,i)=>{
      const people=Number(v||0);
      return `<div class="v16-exact-card"><div class="v16-exact-k">${labels[i]}</div><strong>${num(people,0)}</strong><span>${pct(people/u,2)} от U</span><small>${reached?pct(people/reached,2):'—'} среди достигнутых</small></div>`;
    }).join('')+'</div>';
  }

  function reachCell(r,k){
    const u=Number(r.universe),val=Number(r[`reach_${k}p`]);
    if(!Number.isFinite(val))return '<span class="na">—</span>';
    return `<strong>${num(val,0)}</strong><span class="v16-pct">${u>0?pct(val/u,2):'—'}</span>`;
  }
  function rowClass(level){return level==='Brand'?'v16-level-brand':level==='Line'?'v16-level-line':level==='Flight'?'v16-level-flight':'v16-level-channel'}
  function indentLabel(r){return r.level==='Brand'?'BRAND · '+r.name:r.level==='Line'?'LINE · '+r.name:r.level==='Flight'?'↳ FLIGHT · '+r.name:'↳↳ CHANNEL · '+r.name}
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
    $(ids.table).innerHTML=h+'</tbody>';
  }

  function renderContributions(){
    const rows=v16Data?.contribution_rows||[],table=$(ids.contrib);
    if(!rows.length){table.innerHTML='<tbody><tr><td class="hint">Для текущего merge нет многосущностного вклада.</td></tr></tbody>';return}
    let h='<thead><tr><th>Scope</th><th>Родитель</th><th>Сущность</th><th class="num">Shapley, люди</th><th class="num">% итогового Reach</th><th class="num">Exclusive, люди</th><th class="num">% итогового Reach</th></tr></thead><tbody>';
    for(const r of rows){
      const parent=Number(r.parent_reach||0),sh=Number(r.shapley_people||0),ex=Number(r.exclusive_people||0);
      h+=`<tr><td>${esc(r.scope||'')}</td><td>${esc(r.parent||'')}</td><td><strong>${esc(r.name||'')}</strong></td><td class="num">${num(sh,0)}</td><td class="num">${parent?pct(sh/parent,2):'—'}</td><td class="num">${num(ex,0)}</td><td class="num">${parent?pct(ex/parent,2):'—'}</td></tr>`;
    }
    table.innerHTML=h+'</tbody>';
  }

  function renderDiagnostics(){
    const ds=v16Data?.diagnostics||[],lines=['REACH ENGINE v1.6 — ТЕХНИЧЕСКИЙ ЛОГ','Production 0.52 не изменяется и не вызывается.',''];
    for(const d of ds)lines.push('• '+JSON.stringify(d));
    $(ids.diag).textContent=lines.join('\n');
    const warn=$(ids.warning),msgs=[];
    if(v16Data?.brand_error)msgs.push(v16Data.brand_error);
    const approx=ds.filter(x=>String(x.code||'').includes('APPROX')||x.code==='AON_STAGED_MERGE'||x.code==='L2_AUTO_FALLBACK_QUICK');
    if(approx.length)msgs.push('В расчёте есть явно маркированные приближения или fallback. Они раскрыты в карте модели и техническом логе.');
    if(msgs.length){warn.innerHTML=msgs.map(esc).join('<br>');warn.classList.remove('hidden')}else warn.classList.add('hidden');
  }

  function renderResults(){
    if(!v16Data)return;
    $(ids.results).classList.remove('hidden');
    renderMetrics();renderFrequencyProfile();renderExactFrequency();renderContributions();renderTable();renderDiagnostics();
    renderL2Decision();renderModelMap();
  }

  function clearResults(){
    v16Data=null;
    $(ids.results)?.classList.add('hidden');
    if($(ids.metrics))$(ids.metrics).innerHTML='';
    if($(ids.warning))$(ids.warning).classList.add('hidden');
  }

  async function calculateV16(){
    if(!v16Path||!v16Meta)return;
    const plans=selectedPlans();
    if(!plans.length){setStatus(ids.status,'Выберите хотя бы одну Line.','err');clearResults();return}
    const bu=$(ids.brandU).value.trim(),B=nval(ids.B),D=nval(ids.D);
    const q={
      selected_plan_ids:plans.map(x=>x.id),
      universes:Object.fromEntries(plans.map(x=>[x.id,x.universe])),
      l2_mode:currentMode(),
      K:Number($(ids.k).value||2.4),
      advanced:{
        L:Number($(ids.L).value||68),B,D,
        web_device_universes:Object.fromEntries(plans.filter(x=>x.webDeviceUniverse).map(x=>[x.id,x.webDeviceUniverse]))
      },
      brand_universe:bu===''?null:Number(bu)
    };
    try{
      setStatus(ids.status,'<span class="spinner"></span>Считаю Levels 1–7…');
      const data=await v16Call('reach_v16.calculate(p,q)',{p:v16Path,q:JSON.stringify(q)});
      v16Data=data;
      renderResults();
      setStatus(ids.status,`✓ Рассчитано · ${v16Data.lines?.length||0} Line · production 0.52 не затронут`,'ok');
    }catch(e){
      console.error(e);
      const message=errorMessage(e);
      clearResults();
      setStatus(ids.status,'Ошибка v1.6: '+esc(message),'err');
      renderPrecalc();
    }
  }

  async function openV16File(file){
    try{
      clearResults();
      setStatus(ids.status,'<span class="spinner"></span>Анализирую медиаплан…');
      await ensureV16Module();
      const ext=(file.name.split('.').pop()||'xlsx').toLowerCase();
      v16Path='/tmp/reach_v16_media_plan.'+(ext==='xlsm'?'xlsm':'xlsx');
      pyodide.FS.writeFile(v16Path,new Uint8Array(await file.arrayBuffer()));
      v16File=file;$(ids.file).textContent=file.name;
      v16Meta=await v16Call('reach_v16.discover(p)',{p:v16Path});
      if(!v16Meta.plans?.length)throw new Error('В файле не найден рабочий медиаплан');
      renderPlanControls();
      $(ids.controls).classList.remove('hidden');
      renderPrecalc();
      setStatus(ids.status,`✓ Входы разобраны · ${v16Meta.plans.length} Line. Проверьте KPI и нажмите «Рассчитать».`,'ok');
    }catch(e){
      console.error(e);clearResults();
      setStatus(ids.status,'Ошибка v1.6: '+esc(errorMessage(e)),'err');
    }
  }

  function bind(){
    const dz=$(ids.dz),fi=$(ids.fi);
    if(!dz||!fi)return;
    $(ids.results)?.classList.add('hidden');
    dz.addEventListener('click',()=>fi.click());
    ['dragenter','dragover'].forEach(ev=>dz.addEventListener(ev,e=>{e.preventDefault();dz.classList.add('drag')}));
    ['dragleave','drop'].forEach(ev=>dz.addEventListener(ev,e=>{e.preventDefault();dz.classList.remove('drag')}));
    dz.addEventListener('drop',e=>{if(e.dataTransfer.files[0])openV16File(e.dataTransfer.files[0])});
    fi.addEventListener('change',()=>{if(fi.files[0])openV16File(fi.files[0])});
    $(ids.calc).addEventListener('click',calculateV16);
    $(ids.mode).addEventListener('change',()=>{renderPrecalc()});
    [ids.k,ids.L,ids.B,ids.D].forEach(id=>$(id)?.addEventListener('change',renderPrecalc));
    $(ids.targetF).addEventListener('change',()=>{if(v16Data){renderMetrics();renderFrequencyProfile()}});
    $(ids.brandU).addEventListener('change',()=>{$(ids.brandU).dataset.manual=$(ids.brandU).value.trim()?'1':'0';clearResults();renderPrecalc()});
    $(ids.autoU).addEventListener('click',()=>{syncBrandUniverse(true);clearResults();renderPrecalc()});
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind();
  window.ReachEngineV16={calculate:calculateV16,openFile:openV16File};
})();