(() => {
  let v16File=null, v16Path=null, v16Meta=null, v16Data=null, v16ModuleReady=false;

  const ids={
    dz:'v16Dropzone',fi:'v16FileInput',file:'v16FileName',status:'v16Status',
    plans:'v16PlanWrap',controls:'v16Controls',mode:'v16L2Mode',k:'v16K',L:'v16L',B:'v16B',D:'v16D',
    brandU:'v16BrandUniverse',brandUConfirm:'v16BrandUniverseConfirm',autoU:'v16BrandUniverseAuto',
    brandTA:'v16BrandMasterTA',brandGeo:'v16BrandMasterGeo',
    brandStart:'v16BrandHorizonStart',brandEnd:'v16BrandHorizonEnd',
    brandScopeConfirm:'v16BrandScopeConfirm',expertJson:'v16ExpertJson',
    targetF:'v16TargetFrequency',calc:'v16Calc',
    metrics:'v16Metrics',table:'v16Table',warning:'v16Warning',diag:'v16Diagnostics',
    profile:'v16FrequencyProfile',exact:'v16ExactFrequency',contrib:'v16ContributionTable',
    inputAudit:'v16InputAudit',l2Decision:'v16L2Decision',modelMap:'v16ModelMap',results:'v16Results',
    businessDiag:'v16BusinessDiagnostics',trace:'v16AppliedTrace'
  };

  async function ensureV16Module(){
    await corePromise;
    if(!coreReady)throw new Error('Базовый парсер не готов');
    if(v16ModuleReady)return;
    const [mathResp,adapterResp]=await Promise.all([
      fetch('reach_v16_math.py?v=1.6.6'),
      fetch('reach_v16.py?v=1.6.6')
    ]);
    if(!mathResp.ok||!adapterResp.ok)throw new Error('Не удалось загрузить канонический Reach Engine v1.6');
    const [mathTxt,adapterTxt]=await Promise.all([mathResp.text(),adapterResp.text()]);
    pyodide.FS.writeFile('/app/reach_v16_math.py',mathTxt,{encoding:'utf8'});
    pyodide.FS.writeFile('/app/reach_v16.py',adapterTxt,{encoding:'utf8'});
    pyodide.runPython("import importlib, reach_v16_math, reach_v16; importlib.reload(reach_v16_math); importlib.reload(reach_v16)");
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
    const last=lines[lines.length-1].replace(/^(?:reach_v16(?:_math)?\.)?(?:V16Error|ReachValidationError|ReachCalculationError|ValueError|RuntimeError):\s*/,'');
    return last.length>700?last.slice(0,697)+'…':last;
  }

  function nval(id){
    const raw=$(id)?.value?.trim?.()??'';
    return raw===''?null:Number(raw);
  }
  function deepMergeV16(base,extra){
    if(Array.isArray(extra))return extra.slice();
    if(!extra||typeof extra!=='object')return extra;
    const out=(base&&typeof base==='object'&&!Array.isArray(base))?{...base}:{};
    for(const [k,v] of Object.entries(extra)){
      if(['__proto__','prototype','constructor'].includes(k))continue;
      out[k]=(v&&typeof v==='object'&&!Array.isArray(v))?deepMergeV16(out[k],v):(Array.isArray(v)?v.slice():v);
    }
    return out;
  }

  function expertCanonicalInputs(){
    const raw=$(ids.expertJson)?.value?.trim()||'';
    if(!raw)return {};
    let parsed;
    try{parsed=JSON.parse(raw)}catch(e){throw new Error('Canonical measured inputs JSON: '+e.message)}
    if(!parsed||typeof parsed!=='object'||Array.isArray(parsed))throw new Error('Canonical measured inputs JSON должен быть object.');
    return parsed;
  }

  function prefillBrandScope(){
    const plans=v16Meta?.plans||[];
    const tas=[...new Set(plans.map(p=>(p.ta_name||'').trim()).filter(Boolean))];
    if(tas.length===1&&$(ids.brandTA))$(ids.brandTA).value=tas[0];
    const starts=plans.map(p=>p.period_start).filter(Boolean).sort();
    const ends=plans.map(p=>p.period_end).filter(Boolean).sort();
    if(starts.length&&$(ids.brandStart))$(ids.brandStart).value=starts[0];
    if(ends.length&&$(ids.brandEnd))$(ids.brandEnd).value=ends[ends.length-1];
    if($(ids.brandScopeConfirm))$(ids.brandScopeConfirm).checked=false;
  }
  function targetFrequency(){return Math.max(1,Math.min(6,Number($(ids.targetF)?.value||3)))}
  function reachAt(obj,k){return obj?.[`reach_${k}p`]}
  function modelCatalog(){return v16Data?.model_catalog||v16Meta?.model_catalog||{}}
  function badge(text,kind='neutral'){return `<span class="v16-badge ${kind}">${esc(text)}</span>`}
  function fmtRange(a,b,d=2){
    if(a==null||b==null)return '—';
    return Math.abs(Number(a)-Number(b))<1e-9?num(a,d):`${num(a,d)}–${num(b,d)}`;
  }
  function sourceLabel(src){
    return ({
      AGE_WIDTH_APPROXIMATION:'приближение по ширине возраста',
      AGE_DISTRIBUTION:'из распределения возраста',
      BASE_FALLBACK:'базовый fallback',
      USER_OVERRIDE:'ручной override',
      MODEL_DEFAULT:'model default',
      USER_INPUT:'input пользователя'
    })[src]||src||'—';
  }

  function planNode(planId){return document.querySelector(`.v16-plan[data-plan-id="${CSS.escape(planId)}"]`)}

  function selectedPlans(){
    if(!v16Meta?.plans)return [];
    return v16Meta.plans.flatMap(p=>{
      const root=planNode(p.id);
      const cb=root?.querySelector('.v16-plan-cb');
      if(!cb?.checked)return [];
      const u=root.querySelector('.v16-universe');
      return [{id:p.id,universe:Number(u?.value||p.universe||0),meta:p,root}];
    });
  }

  function collectFamilyMapping(plan){
    const mapping={},env={},browsers={},unitUD={},deviceReach={};
    plan.root.querySelectorAll('.v16-unit-row').forEach(row=>{
      const uid=row.dataset.unitId;
      mapping[uid]=row.querySelector('.v16-family')?.value?.trim()||'';
      env[uid]=row.querySelector('.v16-env')?.value||'UNKNOWN';
      browsers[uid]=row.querySelector('.v16-browser')?.value||'UNKNOWN';
      const ud=row.querySelector('.v16-unit-ud')?.value?.trim();
      if(ud)unitUD[uid]=Number(ud);
      const dr=row.querySelector('.v16-device-reach')?.value?.trim();
      if(dr)deviceReach[uid]=Number(dr);
    });
    return {
      mapping,env,browsers,unitUD,deviceReach,
      confirmed:!!plan.root.querySelector('.v16-family-confirm')?.checked
    };
  }

  function collectAonSlices(plan){
    const out={};
    plan.root.querySelectorAll('.v16-aon-slice').forEach(input=>{
      const v=input.value.trim();
      if(!v)return;
      const aon=input.dataset.aonId,burst=input.dataset.burstId;
      out[aon]??={};
      out[aon][burst]=Number(v);
    });
    return out;
  }

  function lineUD(plan){
    const raw=plan.root.querySelector('.v16-line-ud')?.value?.trim();
    return raw?Number(raw):null;
  }

  function collectLineScope(plan){
    return {
      scopeConfirmed:!!plan.root.querySelector('.v16-line-scope-confirm')?.checked,
      identityConfirmed:!!plan.root.querySelector('.v16-line-identity-confirm')?.checked
    };
  }

  function collectPlatformScopeInputs(plan){
    const out={};
    plan.root.querySelectorAll('.v16-aggregate-rtech').forEach(el=>{
      const raw=el.value?.trim()||'';
      const scope=el.dataset.scopeId||'';
      if(scope&&raw!=='')out[scope]=Number(raw);
    });
    return out;
  }

  function allUserState(){
    const plans=selectedPlans();
    const family_mapping={},family_mapping_confirmed={},environments={},browser_families={},
      unit_web_device_universes={},device_reaches={},web_device_universes={},aon_slices={},
      line_scope_confirmed={},line_identity_confirmed={},aggregate_flight_technical_reaches={};
    plans.forEach(p=>{
      const x=collectFamilyMapping(p);
      family_mapping[p.id]=x.mapping;
      family_mapping_confirmed[p.id]=x.confirmed;
      environments[p.id]=x.env;
      browser_families[p.id]=x.browsers;
      unit_web_device_universes[p.id]=x.unitUD;
      device_reaches[p.id]=x.deviceReach;
      const lud=lineUD(p); if(lud)web_device_universes[p.id]=lud;
      const aon=collectAonSlices(p); if(Object.keys(aon).length)aon_slices[p.id]=aon;
      const lineScope=collectLineScope(p);
      line_scope_confirmed[p.id]=lineScope.scopeConfirmed;
      line_identity_confirmed[p.id]=lineScope.identityConfirmed;
      const aggregateScopes=collectPlatformScopeInputs(p);
      if(Object.keys(aggregateScopes).length)aggregate_flight_technical_reaches[p.id]=aggregateScopes;
    });
    return {plans,family_mapping,family_mapping_confirmed,environments,browser_families,
      unit_web_device_universes,device_reaches,web_device_universes,aon_slices,
      line_scope_confirmed,line_identity_confirmed,aggregate_flight_technical_reaches};
  }

  function markDirty(){
    clearResults();
    renderPrecalc();
  }

  function renderPlanControls(){
    const wrap=$(ids.plans);wrap.innerHTML='';
    for(const p of v16Meta?.plans||[]){
      const rec=p.advanced_recommended||{},prof=p.input_profile||{};
      const reachRows=prof.reach_scope_rows??prof.rows??0;
      const readiness=reachRows?Math.round(100*(prof.l1_ready_rows||0)/reachRows):0;
      const box=document.createElement('div');
      box.className='v16-plan';
      box.dataset.planId=p.id;
      const units=(p.inventory_units||[]).map(u=>`
        <tr class="v16-unit-row" data-unit-id="${esc(u.id)}">
          <td><strong>${esc(u.platform||'')}</strong><span class="v16-th-sub">${esc(u.sheet)} · строка ${u.row}</span></td>
          <td>${esc(u.format||'—')}</td>
          <td>${esc(u.channel||'—')}</td>
          <td><input class="v16-family" value="${esc(u.suggested_family||'')}" aria-label="Audience Family"></td>
          <td>
            <select class="v16-env">
              <option value="UNKNOWN" selected>Не определено → Quick</option>
              <option value="WEB">Web / browser</option>
              <option value="MOBILE_APP">Mobile app</option>
              <option value="CTV">CTV / OTT</option>
            </select>
          </td>
          <td>
            <select class="v16-browser">
              <option value="UNKNOWN" selected>Не определён</option>
              <option value="CHROMIUM">Chromium-class</option>
              <option value="SAFARI">Safari / WebKit</option>
            </select>
          </td>
          <td><input class="v16-unit-ud" type="number" min="1" step="1" placeholder="U_D, если есть"></td>
          <td><input class="v16-device-reach" type="number" min="0" step="1" placeholder="Device Reach"></td>
        </tr>`).join('');

      const aon=(p.aon_pairs||[]).length?`
        <details class="v16-plan-advanced">
          <summary>Always-on temporal footprint · нужен только для AON ↔ burst</summary>
          <div class="v16-note" style="margin:8px 0">Годовой AON Reach не раскладывается автоматически. Введите deduplicated human Reach AON ровно за период соответствующего burst, если такой замер есть.</div>
          <div class="v16-aon-grid">
            ${(p.aon_pairs||[]).map(x=>`
              <div class="field">
                <label>${esc(x.aon_label)} → ${esc(x.burst_label)} · ${esc(x.burst_start||'')}—${esc(x.burst_end||'')}</label>
                <input class="v16-aon-slice" data-aon-id="${esc(x.aon_flight_id)}" data-burst-id="${esc(x.burst_flight_id)}"
                  type="number" min="0" step="1" placeholder="AON Human Reach slice">
              </div>`).join('')}
          </div>
        </details>`: '';

      const sourceFlights=(p.source_flights||[]).map(f=>`
        <div class="v16-scope-flight">
          <strong>${esc(f.label||f.id)}</strong>
          <span>TA: ${esc(f.ta_name||'—')}</span>
          <span>U: ${f.source_universe?num(f.source_universe,0):'—'}</span>
          <span>${esc(f.start||'—')} — ${esc(f.end||'—')}</span>
        </div>`).join('');

      const lineScopeReview=`
        <details class="v16-plan-advanced" ${(p.source_universe_mismatch||p.source_ta_mismatch)?'open':''}>
          <summary>Line scope · source Flights и нормализация</summary>
          <div class="v16-scope-flight-list">${sourceFlights||'<div class="v16-note">Source flight scope не распознан.</div>'}</div>
          ${p.source_ta_mismatch?'<div class="warning" style="margin-top:8px"><strong>TA mismatch:</strong> Flights имеют разные ЦА. Это нельзя снять галочкой — нужны upstream inputs на одной Line Master TA.</div>':''}
          ${p.source_universe_mismatch?'<div class="warning" style="margin-top:8px"><strong>Universe mismatch:</strong> движок не использует Universe последнего Flight автоматически. Можно пересчитать все Flights на Human Universe Line выше только после явного подтверждения одинакового TA/geo/human scope.</div>':''}
          <label class="v16-confirm-line">
            <input type="checkbox" class="v16-line-scope-confirm">
            <span><strong>Подтверждаю Line Master Universe / scope</strong><small>Нужно, если Human Universe Line отличается от source U или source U различаются. Это не разрешает TA mismatch.</small></span>
          </label>
        </details>`;

      const identityReview=p.line_identity_review_required?`
        <div class="warning v16-line-identity-warning" style="margin-top:10px">
          <strong>LINE IDENTITY HEADER CONFLICT.</strong> Названия листов имеют общий маркер с другой Line, но Campaign/Line headers расходятся. Движок не объединяет такие Lines автоматически.
          <label class="v16-confirm-line" style="margin-top:8px">
            <input type="checkbox" class="v16-line-identity-confirm">
            <span><strong>Подтверждаю текущую разбивку на отдельные Lines</strong><small>Если это одна Line, сначала исправьте/нормализуйте Campaign/Line identity в исходном МП.</small></span>
          </label>
        </div>`: '';

      const platformScopeInputs=(p.platform_scopes||[]).length?`
        <details class="v16-plan-advanced" open>
          <summary>Level 3A · площадка разбита на несколько source rows</summary>
          <div class="warning" style="margin:8px 0">
            Эти строки нельзя дедуплицировать как независимые Inventory Units. Для каждого platform-flight scope нужен weekly Human Reach либо aggregate Technical Reach за весь Flight.
          </div>
          <div class="v16-platform-scope-grid">
            ${(p.platform_scopes||[]).map(s=>`
              <div class="v16-platform-scope-card">
                <strong>${esc(s.platform||s.scope_id)}</strong>
                <small>${esc(s.channel||'—')} · ${s.fragment_count||0} source rows</small>
                <div class="v16-scope-rows">${(s.source_rows||[]).map(x=>`${esc(x.sheet)}:${x.row}`).join(' · ')}</div>
                <div class="field">
                  <label>Aggregate Technical Reach за platform-flight</label>
                  <input class="v16-aggregate-rtech" data-scope-id="${esc(s.scope_id)}" type="number" min="0" step="1" placeholder="Оставьте пустым, если дадите weekly Human Reach">
                </div>
              </div>`).join('')}
          </div>
        </details>`: '';

      const excludedReach=(p.excluded_reach_rows||[]).length?`
        <details class="v16-plan-advanced">
          <summary>Вне Reach scope · ${p.excluded_reach_rows.length} строк</summary>
          <div class="v16-note" style="margin:8px 0">Для этих строк нет Impressions + (Frequency или Technical Reach). Движок не придумывает им Reach и не требует Audience Family.</div>
          <div class="v16-excluded-list">
            ${p.excluded_reach_rows.map(x=>`<div><strong>${esc(x.platform||x.unit_id)}</strong><span>${esc(x.channel||'—')} · ${esc(x.buying_model||'—')} · ${esc(x.reason||'')}</span><small>${esc(x.sheet)}:${x.row}</small></div>`).join('')}
          </div>
        </details>`: '';

      const sourceQaItems=(p.import_warnings||[]).filter(w=>String(w.code||'').startsWith('SOURCE_'));
      const sourceQaReview=sourceQaItems.length?`
        <details class="v16-plan-advanced v16-source-qa" open>
          <summary>Source QA · ${sourceQaItems.length} предупреждений</summary>
          <div class="v16-source-qa-list">
            ${sourceQaItems.map(w=>`<div class="${String(w.code||'').includes('INVALID')?'err':'warn'}"><strong>${esc(w.code||'SOURCE_QA')}</strong><span>${esc(w.message||'')}</span></div>`).join('')}
          </div>
        </details>`: '';

      box.innerHTML=`
        <div class="v16-plan-head">
          <label class="v16-plan-title">
            <input type="checkbox" class="v16-plan-cb" checked>
            <span><strong>${esc(p.label||p.line||p.campaign||p.id)}</strong>
              <span class="hint">${esc((p.sheet_names||[]).join(', '))}</span>
            </span>
          </label>
          <div class="field"><label>Human Universe Line</label><input class="v16-universe" type="number" min="1" step="1" value="${p.universe?Math.round(p.universe):''}" placeholder="Обязательный input"></div>
          <div class="v16-plan-facts">
            <span>ЦА: <strong>${esc(p.ta_name||'не распознана')}</strong></span>
            <span>${p.flight_count||0} flight · Reach scope ${reachRows}/${p.placement_count||0} строк</span>
            <span>Готовность L1 Reach scope: <strong>${readiness}%</strong></span>
          </div>
        </div>

        <div class="v16-auto-strip">
          <div><span class="v16-auto-label">L2 model fallback</span><strong>B = ${num(rec.B,2)}</strong><small>${sourceLabel(rec.B_source)} · ${fmtRange(rec.B_min,rec.B_max)}</small></div>
          <div><span class="v16-auto-label">L2 model fallback</span><strong>D = ${num(rec.D,2)}</strong><small>${sourceLabel(rec.D_source)} · ${fmtRange(rec.D_min,rec.D_max)}</small></div>
          <div class="field"><label>Line-level U_D, если замер одинаков для Web units</label><input class="v16-line-ud" type="number" min="1" step="1" placeholder="Не выдумывать"></div>
        </div>
        ${lineScopeReview}
        ${identityReview}
        ${platformScopeInputs}
        ${excludedReach}
        ${sourceQaReview}

        <details class="v16-mapping" open>
          <summary>Audience Family и technical environment · обязательная проверка перед расчётом</summary>
          <div class="warning" style="margin:10px 0">
            Family в таблице — предложение для проверки, а не автоматический факт. Движок не считает, пока mapping не подтверждён. Environment UNKNOWN честно ведёт в Quick fallback.
          </div>
          <div class="table-wrap">
            <table class="data-table v16-unit-table">
              <thead><tr><th>Inventory Unit</th><th>Формат</th><th>Канал</th><th>Audience Family</th><th>Environment</th><th>Browser family</th><th>U_D</th><th>Device Reach</th></tr></thead>
              <tbody>${units}</tbody>
            </table>
          </div>
          <label class="v16-confirm-line">
            <input type="checkbox" class="v16-family-confirm">
            <span><strong>Подтверждаю Audience Family mapping для этой Line</strong><small>Без подтверждения Level 4 блокируется — это защита от скрытого угадывания.</small></span>
          </label>
        </details>
        ${aon}
      `;
      wrap.appendChild(box);
    }
    wrap.querySelectorAll('input,select').forEach(el=>el.addEventListener('change',markDirty));
    renderPrecalc();
  }

  function renderInputAudit(){
    const wrap=$(ids.inputAudit); if(!wrap)return;
    const state=allUserState(),plans=state.plans;
    if(!plans.length){wrap.innerHTML='<div class="warning">Не выбрано ни одной Line.</div>';return}
    wrap.innerHTML='<div class="v16-audit-grid">'+plans.map(p=>{
      const x=p.meta.input_profile||{},rows=x.rows||0;
      const reachRows=x.reach_scope_rows??rows;
      const excluded=x.reach_excluded_rows||0;
      const l1=x.l1_ready_rows||0;
      const mapping=collectFamilyMapping(p);
      const mapped=Object.values(mapping.mapping).filter(Boolean).length;
      const mappingReady=mapped===(p.meta.inventory_units||[]).length&&mapping.confirmed;
      const allU=Number.isFinite(p.universe)&&p.universe>0;
      const scope=collectLineScope(p);
      const scopeBadge=p.meta.source_ta_mismatch?badge('TA mismatch','err'):(p.meta.source_universe_mismatch?(scope.scopeConfirmed?badge('U normalized','ok'):badge('U mismatch','warn')):'');
      const identityBadge=p.meta.line_identity_review_required?(scope.identityConfirmed?badge('Line split confirmed','ok'):badge('Line identity review','warn')):'';
      const sourceWarnings=(p.meta.import_warnings||[]).filter(w=>String(w.code||'').startsWith('SOURCE_'));
      const sourceBadge=sourceWarnings.length?badge('Source QA '+sourceWarnings.length,'err'):'';
      return `<div class="v16-audit-card">
        <div class="v16-audit-title">${l1===reachRows?badge('L1 Reach scope готов','ok'):badge('L1 Reach scope проверить','warn')} ${mappingReady?badge('Family confirmed','ok'):badge('Family не подтверждена','warn')} ${scopeBadge} ${identityBadge} ${sourceBadge}<strong>${esc(p.meta.label||p.id)}</strong></div>
        <div class="v16-audit-stats">
          <span>Строк: <b>${rows}</b></span><span>Reach scope: <b>${reachRows}</b></span>
          <span>Вне Reach scope: <b>${excluded}</b></span><span>L1 ready: <b>${l1}/${reachRows}</b></span>
          <span>Universe: <b>${allU?num(p.universe,0):'нет'}</b></span><span>Family mapping: <b>${mapped}/${(p.meta.inventory_units||[]).length}</b></span>
          <span>С датами: <b>${x.dated_rows||0}</b></span><span>I+F: <b>${x.impressions_frequency_rows||0}</b></span>
          <span>Source U: <b>${(p.meta.source_flights||[]).map(f=>f.source_universe?num(f.source_universe,0):'—').join(' / ')||'—'}</b></span>
        </div>
      </div>`;
    }).join('')+'</div>';
  }

  function currentMode(){return $(ids.mode)?.value||'AUTO'}

  function renderL2Decision(){
    const wrap=$(ids.l2Decision);if(!wrap)return;
    const state=allUserState(),mode=currentMode();
    if(!state.plans.length){wrap.innerHTML='';return}
    wrap.innerHTML='<div class="v16-decision-list">'+state.plans.map(p=>{
      const map=collectFamilyMapping(p),rec=p.meta.advanced_recommended||{};
      let adv=0,quick=0,blocked=0;
      const rows=[...p.root.querySelectorAll('.v16-unit-row')];
      rows.forEach(r=>{
        const env=r.querySelector('.v16-env')?.value||'UNKNOWN';
        const unitUD=r.querySelector('.v16-unit-ud')?.value?.trim();
        const lineUd=p.root.querySelector('.v16-line-ud')?.value?.trim();
        const device=r.querySelector('.v16-device-reach')?.value?.trim();
        if(mode==='QUICK'){quick++;return}
        if(mode==='ADVANCED'||mode==='ADVANCED_WEB'){
          const ok=env==='WEB'?!!(unitUD||lineUd):(env==='MOBILE_APP'||env==='CTV')?!!device:false;
          if(ok)adv++;else blocked++;
          return;
        }
        if(env==='WEB'&&(unitUD||lineUd))adv++;
        else if((env==='MOBILE_APP'||env==='CTV')&&device)adv++;
        else quick++;
      });
      return `<div class="v16-decision ${blocked?'error':adv?'advanced':'fallback'}">
        <div class="v16-decision-head"><strong>${esc(p.meta.label||p.id)}</strong>
          ${blocked?badge(`${blocked} Advanced не готовы`,'err'):badge(`${adv} Advanced · ${quick} Quick`,adv?'ok':'warn')}
        </div>
        <div class="v16-formula-path">
          <span>R<sub>tech</sub></span><b>→</b><span>Environment</span><b>→</b>
          <span>Web: 2A→2B→2C<br><small>App/CTV: browser correction OFF</small></span><b>→</b><span>R<sub>people</sub></span>
        </div>
        <div class="v16-param-row">
          <span><b>B ${num(rec.B,2)}</b><small>${sourceLabel(rec.B_source)}; averaged fallback only</small></span>
          <span><b>D ${num(rec.D,2)}</b><small>${sourceLabel(rec.D_source)}; averaged fallback only</small></span>
          <span><b>Family mapping</b><small>${map.confirmed?'USER CONFIRMED':'NOT CONFIRMED'}</small></span>
        </div>
      </div>`;
    }).join('')+'</div>';
  }

  function renderModelMap(){
    const wrap=$(ids.modelMap);if(!wrap)return;
    const c=modelCatalog();
    if(!c.level2){wrap.innerHTML='<div class="hint">Каталог модели загрузится после медиаплана.</div>';return}
    const l2=c.level2||{},l3=c.level3||{},l5=c.level5||{},l6=c.level6||{},eng=c.engineering||{};
    const rho=l3.temporal_rho_profiles||{};
    const q=(l6.gap_curve||[]).map(x=>`${x.days}д=${pct(x.overlap,1)}`).join(' · ');
    wrap.innerHTML=`
      <div class="v16-model-card emphasis"><div class="v16-model-level">LEVEL 1</div><strong>Placement → Technical Uniques</strong>
        <p>Supplied Reach либо I÷F. Если I/Reach/F заданы вместе — precision-aware arithmetic validation; fixed 3% tolerance больше не используется.</p>
      </div>
      <div class="v16-model-card emphasis"><div class="v16-model-level">LEVEL 2</div><strong>Technical IDs → люди</strong>
        <p>Quick K=${num(l2.quick_k,2)} — fallback. Advanced сохраняет environment: Web 2A→2B→2C; App/CTV без browser corrections.</p>
      </div>
      <div class="v16-model-card"><div class="v16-model-level">LEVEL 3A</div><strong>Weeks → Platform Flight</strong>
        <p>ρ LOW ${num(rho.LOW,2)} · BASE ${num(rho.BASE,2)} · HIGH ${num(rho.HIGH,2)}; gap decay ρ<sup>1+G</sup>. Без weekly Human Reach — explicit AGGREGATE_FLIGHT_REACH_MODE.</p>
      </div>
      <div class="v16-model-card"><div class="v16-model-level">LEVEL 3B</div><strong>Effective Reach</strong>
        <p>Poisson-Lognormal σ=${num(l3.sigma_default,2)} model default; μ решается под фактическую Human F. F&lt;1 = validation error, не repair.</p>
      </div>
      <div class="v16-model-card"><div class="v16-model-level">LEVEL 4</div><strong>Inventory Unit → Audience Family → Channel</strong>
        <p>Family не угадывается. Neutral unstructured — closed form; structured/dependent — global feasibility → MaxEnt.</p>
      </div>
      <div class="v16-model-card"><div class="v16-model-level">LEVEL 5</div><strong>Channels → Flight</strong>
        <p>ρ target=${num(l5.rho_channel_target,2)}. Для 3+ MODEL_DEFAULT один общий λ к 0 только при необходимости global feasibility.</p>
      </div>
      <div class="v16-model-card"><div class="v16-model-level">LEVEL 6</div><strong>Flights → Line</strong>
        <p>${esc(q)}. Residual ≤${pct(l6.residual_cap??.10,0)} до global feasibility. AON↔burst требует temporal slice.</p>
      </div>
      <div class="v16-model-card"><div class="v16-model-level">LEVEL 7</div><strong>Lines → Brand</strong>
        <p>Brand Master U_B и единая Brand TA обязательны. BrandAddressabilityMap применяется только к реальной geo/CRM/pool structure.</p>
      </div>
      <div class="v16-model-card"><div class="v16-model-level">SOLVER</div><strong>Feasibility отдельно от MaxEnt</strong>
        <p>Guard ≤${eng.max_entities||12} entities. Feasibility tol ${eng.feasibility_tolerance||'1e-9'}; solver tol ${eng.solver_constraint_tolerance||'1e-8'}; max ${eng.max_iterations||10000} iterations.</p>
      </div>`;
  }

  function renderPrecalc(){renderInputAudit();renderL2Decision();renderModelMap()}

  function topResult(){
    const b=v16Data?.brand_total,lines=v16Data?.lines||[];
    return b||(lines.length===1?lines[0]:null);
  }
  function topUniverse(){
    const t=topResult();
    return t?.universe||(v16Data?.lines?.length===1?v16Data.lines[0].universe:null);
  }

  function renderMetrics(){
    const top=topResult(),u=topUniverse(),tf=targetFrequency();
    if(!top){
      $(ids.metrics).innerHTML=`
        <div class="metric"><div class="label">Статус</div><div class="value">${esc(v16Data?.status||'PARTIAL')}</div></div>
        <div class="metric"><div class="label">Brand Total</div><div class="value">заблокирован</div><div class="v16-note">Смотрите Lines и диагностику ниже.</div></div>`;
      return;
    }
    const r1=reachAt(top,1),rt=reachAt(top,tf);
    const cards=[
      ['Статус',v16Data?.status||'—',''],
      ['Universe',u?num(u,0):'—',''],
      ['Impressions',top.impressions!=null?num(top.impressions,0):'—',''],
      ['Reach @1+ · люди',r1!=null?num(r1,0):'—',''],
      ['Reach @1+ · % U',u&&r1!=null?pct(r1/u,2):'—',''],
      [`Reach @${tf}+ · люди`,rt!=null?num(rt,0):'—','выбранный KPI'],
      [`Reach @${tf}+ · % U`,u&&rt!=null?pct(rt/u,2):'—','выбранный KPI'],
      ['Average Human F',top.avg_frequency!=null?num(top.avg_frequency,2):'—','I / deduplicated Reach 1+'],
      ['Gross Reach Sum',top.gross_reach_sum!=null?num(top.gross_reach_sum,0):'—','до текущего merge'],
      ['Dedup people',top.dedup_people!=null?num(top.dedup_people,0):'—',top.dedup_rate!=null?pct(top.dedup_rate,2):''],
      ['Merge path',top.model_path||'—',''],
    ];
    $(ids.metrics).innerHTML=cards.map(([a,b,c])=>`<div class="metric"><div class="label">${esc(a)}</div><div class="value">${esc(b)}</div>${c?`<div class="v16-note">${esc(c)}</div>`:''}</div>`).join('');
  }

  function renderFrequencyProfile(){
    const top=topResult(),u=topUniverse(),wrap=$(ids.profile);
    if(!top||!u){wrap.innerHTML='<div class="hint">Нет единого Brand/Line total. Частотная кривая доступна по строкам иерархии.</div>';return}
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
    if(!top||!u||!Array.isArray(top.exact_counts)){wrap.innerHTML='<div class="hint">Нет единого total для exact buckets.</div>';return}
    const reached=Number(top.reach_1p||0),labels=['ровно 1','ровно 2','ровно 3','ровно 4','ровно 5','6+'];
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
    let h='<thead><tr><th>Уровень</th><th>Line</th><th>Flight</th><th class="num">Universe</th><th class="num">Impressions</th>'+
      [1,2,3,4,5,6].map(k=>`<th class="num">Reach @${k}+<span class="v16-th-sub">люди · % U</span></th>`).join('')+
      '<th class="num">Avg F</th><th class="num">Gross Reach</th><th class="num">Dedup</th><th>Merge path</th></tr></thead><tbody>';
    for(const r of rows){
      h+=`<tr class="${rowClass(r.level)}"><td><strong>${esc(indentLabel(r))}</strong></td><td>${esc(r.line||'')}</td><td>${esc(r.flight||'')}</td><td class="num">${num(r.universe,0)}</td><td class="num">${num(r.impressions,0)}</td>`;
      for(let k=1;k<=6;k++)h+=`<td class="num v16-reach-cell">${reachCell(r,k)}</td>`;
      h+=`<td class="num">${num(r.avg_frequency,2)}</td><td class="num">${r.gross_reach_sum!=null?num(r.gross_reach_sum,0):'—'}</td><td class="num">${r.dedup_people!=null?num(r.dedup_people,0):'—'}${r.dedup_rate!=null?'<span class="v16-pct">'+pct(r.dedup_rate,2)+'</span>':''}</td><td>${esc(r.model_path||'—')}</td></tr>`;
    }
    $(ids.table).innerHTML=h+'</tbody>';
  }

  function renderContributions(){
    const rows=v16Data?.contribution_rows||[],table=$(ids.contrib);
    if(!rows.length){table.innerHTML='<tbody><tr><td class="hint">Для текущих identity/empty merges нет многосущностного вклада.</td></tr></tbody>';return}
    let h='<thead><tr><th>Scope</th><th>Родитель</th><th>Сущность</th><th class="num">Shapley, люди</th><th class="num">% итогового Reach</th><th class="num">Exclusive, люди</th><th class="num">% итогового Reach</th></tr></thead><tbody>';
    for(const r of rows){
      const parent=Number(r.parent_reach||0),sh=Number(r.shapley_people||0),ex=Number(r.exclusive_people||0);
      h+=`<tr><td>${esc(r.scope||'')}</td><td>${esc(r.parent||'')}</td><td><strong>${esc(r.name||'')}</strong></td><td class="num">${num(sh,0)}</td><td class="num">${parent?pct(sh/parent,2):'—'}</td><td class="num">${num(ex,0)}</td><td class="num">${parent?pct(ex/parent,2):'—'}</td></tr>`;
    }
    table.innerHTML=h+'</tbody>';
  }

  function renderBusinessDiagnostics(){
    const wrap=$(ids.businessDiag);if(!wrap)return;
    const rows=v16Data?.business_diagnostics||[];
    if(!rows.length){wrap.innerHTML='<div class="v16-business-ok">Нет business-level предупреждений. Технический лог остаётся доступен ниже.</div>';return}
    wrap.innerHTML='<div class="v16-business-list">'+rows.map(d=>{
      const kind=d.severity==='ERROR'?'err':d.severity==='WARNING'?'warn':'ok';
      return `<div class="v16-business-item ${kind}">
        <div class="v16-business-head">${badge(d.tag||'INFO',kind)}<strong>${esc(d.title||'')}</strong><span>Level ${esc(d.level??'—')}</span></div>
        <div>${esc(d.message||'')}</div>
      </div>`;
    }).join('')+'</div>';
  }

  function formatTrace(d){
    const code=d.code||'';
    if(code==='L1_TECHNICAL_REACH')return `Technical Reach = ${num(d.R_tech,0)} · source ${d.source} · F tolerance ${d.frequency_tolerance}`;
    if(code==='L2_QUICK')return `Quick: Rpeople=Rtech/K · K=${num(d.K,2)} · reason=${d.reason||'selected'}`;
    if(code==='L2_ADVANCED')return `Advanced ${d.environment}: ${(d.path||[]).join(' → ')} · K_time=${num(d.K_time,4)} · Rstable=${num(d.R_stable,0)} · Rdevice=${num(d.R_device,0)} · Rpeople=${num(d.R_people,0)}`;
    if(code==='L3A_PLATFORM_FLIGHT')return `${d.model_path} · U_p=${num(d.U_p,0)}${d.platform_universe_assumed?' (assumed U)':''} · ρ=${d.rho_base??'N/A'}`;
    if(code==='L3B_EFFECTIVE_REACH')return `${d.model} · Fhuman=${num(d.F_human,3)} · σ=${d.sigma??'N/A'} · μ=${d.mu==null?'N/A':num(d.mu,4)} · residual=${d.solver_residual??0}`;
    if(code==='L4_CHANNEL')return `${d.channel}: ${d.model_path} · D overall=${pct(d.D_overall||0,2)} · solver ${d.solver_iterations??0} iter`;
    if(code==='L5_FLIGHT')return `${d.flight}: ρ target=${d.rho_target} → effective=${d.rho_effective} · λ=${d.lambda} · ${d.model_path}`;
    if(code==='L6_LINE')return `Flights → Line · λ=${d.lambda??1} · ${d.model_path} · D=${pct(d.D_L6||0,2)}`;
    if(code==='L7_BRAND')return `Lines → Brand · U_B=${num(d.U_B,0)} · ${d.BrandAddressabilityMap} · ${d.model_path}`;
    return JSON.stringify(d);
  }

  function renderAppliedTrace(){
    const wrap=$(ids.trace);if(!wrap)return;
    const ds=v16Data?.diagnostics||[];
    const keep=new Set(['L1_TECHNICAL_REACH','L2_QUICK','L2_ADVANCED','L3A_PLATFORM_FLIGHT','L3B_EFFECTIVE_REACH','L4_CHANNEL','L5_FLIGHT','L6_LINE','L7_BRAND']);
    const rows=ds.filter(d=>keep.has(d.code));
    if(!rows.length){wrap.innerHTML='<div class="hint">Расчётный trace не сформирован.</div>';return}
    const grouped={};
    rows.forEach(d=>{const l=String(d.level||'?');(grouped[l]??=[]).push(d)});
    wrap.innerHTML=Object.keys(grouped).sort().map(level=>`
      <details class="v16-trace-level" ${['1','2','3'].includes(level)?'open':''}>
        <summary><strong>LEVEL ${esc(level)}</strong><span>${grouped[level].length} операций</span></summary>
        <div class="v16-trace-items">${grouped[level].map(d=>`<div><code>${esc(d.code)}</code><span>${esc(formatTrace(d))}</span></div>`).join('')}</div>
      </details>`).join('');
  }

  function renderDiagnostics(){
    const ds=v16Data?.diagnostics||[],lines=['REACH ENGINE v1.6 — TECHNICAL LOG','Canonical Levels 1–7 · production Web 0.52 isolated.',''];
    for(const d of ds)lines.push('• '+JSON.stringify(d));
    $(ids.diag).textContent=lines.join('\n');
    const warn=$(ids.warning),msgs=[];
    if(v16Data?.brand_error)msgs.push(v16Data.brand_error);
    if((v16Data?.business_diagnostics||[]).some(x=>x.severity==='WARNING'))msgs.push('Есть fallback / approximation / review flags. Они раскрыты в бизнес-диагностике.');
    if(msgs.length){warn.innerHTML=msgs.map(esc).join('<br>');warn.classList.remove('hidden')}else warn.classList.add('hidden');
  }

  function renderResults(){
    if(!v16Data)return;
    $(ids.results).classList.remove('hidden');
    renderMetrics();renderFrequencyProfile();renderExactFrequency();renderContributions();renderTable();
    renderBusinessDiagnostics();renderAppliedTrace();renderDiagnostics();
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
    const state=allUserState(),plans=state.plans;
    if(!plans.length){setStatus(ids.status,'Выберите хотя бы одну Line.','err');clearResults();return}

    const missingMapping=plans.filter(p=>!collectFamilyMapping(p).confirmed);
    if(missingMapping.length){
      clearResults();
      setStatus(ids.status,'Сначала подтвердите Audience Family mapping для каждой выбранной Line.','err');
      return;
    }

    const brandRaw=$(ids.brandU)?.value?.trim()||'';
    let q={
      selected_plan_ids:plans.map(x=>x.id),
      universes:Object.fromEntries(plans.map(x=>[x.id,x.universe])),
      l2_mode:currentMode(),
      K:Number($(ids.k)?.value||2.4),
      advanced:{
        L:Number($(ids.L)?.value||68),
        B:nval(ids.B),D:nval(ids.D),
        web_device_universes:state.web_device_universes,
        unit_web_device_universes:state.unit_web_device_universes,
        environments:state.environments,
        browser_families:state.browser_families,
        device_reaches:state.device_reaches
      },
      family_mapping:state.family_mapping,
      family_mapping_confirmed:state.family_mapping_confirmed,
      line_scope_confirmed:state.line_scope_confirmed,
      line_identity_confirmed:state.line_identity_confirmed,
      aggregate_flight_technical_reaches:state.aggregate_flight_technical_reaches,
      aon_slices:state.aon_slices,
      brand_universe:brandRaw===''?null:Number(brandRaw),
      brand_universe_confirmed:!!$(ids.brandUConfirm)?.checked,
      brand_master_ta:$(ids.brandTA)?.value?.trim()||'',
      brand_master_geo:$(ids.brandGeo)?.value?.trim()||'',
      brand_horizon_start:$(ids.brandStart)?.value||'',
      brand_horizon_end:$(ids.brandEnd)?.value||'',
      brand_scope_confirmed:!!$(ids.brandScopeConfirm)?.checked
    };

    try{
      q=deepMergeV16(q,expertCanonicalInputs());
      clearResults();
      setStatus(ids.status,'<span class="spinner"></span>Считаю канонические Levels 1–7…');
      const data=await v16Call('reach_v16.calculate(p,q)',{p:v16Path,q:JSON.stringify(q)});
      v16Data=data;
      renderResults();
      const suffix=v16Data.status==='GO'?'Brand Total рассчитан':'Lines рассчитаны; Brand Total заблокирован входами Level 7';
      setStatus(ids.status,`✓ ${suffix} · ${v16Data.lines?.length||0} Line · production 0.52 не затронут`,'ok');
    }catch(e){
      console.error(e);
      const message=errorMessage(e);
      clearResults();
      setStatus(ids.status,'Ошибка Reach Engine v1.6: '+esc(message),'err');
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
      prefillBrandScope();
      $(ids.controls).classList.remove('hidden');
      setStatus(ids.status,`✓ Распознано ${v16Meta.plans.length} Line. Проверьте Family mapping, environment и Brand scope.`,'ok');
    }catch(e){
      console.error(e);clearResults();
      setStatus(ids.status,'Ошибка Reach Engine v1.6: '+esc(errorMessage(e)),'err');
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
    $(ids.calc)?.addEventListener('click',calculateV16);
    $(ids.mode)?.addEventListener('change',markDirty);
    [ids.k,ids.L,ids.B,ids.D].forEach(id=>$(id)?.addEventListener('change',markDirty));
    $(ids.targetF)?.addEventListener('change',()=>{if(v16Data){renderMetrics();renderFrequencyProfile()}});
    $(ids.brandU)?.addEventListener('change',()=>{if($(ids.brandUConfirm))$(ids.brandUConfirm).checked=false;markDirty()});
    $(ids.brandUConfirm)?.addEventListener('change',markDirty);
    [ids.brandTA,ids.brandGeo,ids.brandStart,ids.brandEnd,ids.expertJson].forEach(id=>$(id)?.addEventListener('change',markDirty));
    $(ids.brandScopeConfirm)?.addEventListener('change',markDirty);
    $(ids.autoU)?.addEventListener('click',()=>{
      const vals=selectedPlans().map(x=>x.universe).filter(x=>Number.isFinite(x)&&x>0);
      if(vals.length){
        $(ids.brandU).value=String(Math.round(Math.max(...vals)));
        if($(ids.brandUConfirm))$(ids.brandUConfirm).checked=false;
        clearResults();renderPrecalc();
        setStatus(ids.status,'Max Line Universe подставлен только как черновик. Подтвердите, что это реальный Brand Master U_B.','warn');
      }
    });
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind();
  window.ReachEngineV16={calculate:calculateV16,openFile:openV16File};
})();