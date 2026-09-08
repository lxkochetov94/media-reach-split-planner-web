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
    profile:'v16FrequencyProfile',exact:'v16ExactFrequency',
    inputAudit:'v16InputAudit',l2Decision:'v16L2Decision',modelMap:'v16ModelMap',results:'v16Results',
    businessDiag:'v16BusinessDiagnostics',trace:'v16AppliedTrace'
  };

  async function ensureV16Module(){
    await corePromise;
    if(!coreReady)throw new Error('Базовый парсер не готов');
    if(v16ModuleReady)return;
    const [mathResp,adapterResp]=await Promise.all([
      fetch('reach_v16_math.py?v=1.6.20'),
      fetch('reach_v16.py?v=1.6.20')
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

  function friendlyV16Error(message){
    const raw=String(message||'');
    const rules=[
      [/TA_NORMALIZATION_REQUIRED|L6_SCOPE_TA_MISMATCH/, 'Во флайтах действительно указаны разные целевые аудитории. Их нельзя объединить в один охват, пока входы не приведены к одной ЦА.'],
      [/LINE_IDENTITY_HEADER_CONFLICT/, 'В исходном файле расходятся названия Line/Campaign. Проверьте, это одна кампания или разные Lines.'],
      [/BRAND_MASTER_UNIVERSE_REQUIRED/, 'Для общего результата нескольких Lines нужен единый Universe бренда.'],
      [/BRAND_MASTER_TA_REQUIRED|BRAND_MASTER_SCOPE_CONFIRMATION_REQUIRED/, 'Для объединения нескольких Lines нужна единая целевая аудитория бренда.'],
      [/BRAND_MASTER_GEO_REQUIRED/, 'Для объединения нескольких Lines нужна единая география бренда.'],
      [/PLANNING_HORIZON_MISMATCH/, 'Периоды выбранных Lines не укладываются в общий период Brand Total.'],
      [/GLOBAL.*FEASIB|infeasib/i, 'Заданные пересечения аудиторий математически несовместимы. Проверьте измеренные пересечения и Universe.']
    ];
    for(const [re,txt] of rules)if(re.test(raw))return txt;
    return 'Не удалось завершить расчёт. Откройте техническую диагностику для подробностей.';
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
    const web_device_universes={},line_scope_confirmed={},line_identity_confirmed={};
    plans.forEach(p=>{
      const lud=lineUD(p); if(lud)web_device_universes[p.id]=lud;
      const lineScope=collectLineScope(p);
      line_scope_confirmed[p.id]=lineScope.scopeConfirmed;
      line_identity_confirmed[p.id]=lineScope.identityConfirmed;
    });
    return {plans,web_device_universes,line_scope_confirmed,line_identity_confirmed};
  }

  function markDirty(){
    clearResults();
    renderPrecalc();
  }

  function renderPlanControls(){
    const wrap=$(ids.plans);wrap.innerHTML='';
    for(const p of v16Meta?.plans||[]){
      const rec=p.advanced_recommended||{},prof=p.input_profile||{};
      const reachRows=prof.reach_scope_rows??0;
      const readiness=reachRows?Math.round(100*(prof.l1_ready_rows||0)/reachRows):0;
      const box=document.createElement('div');
      box.className='v16-plan';
      box.dataset.planId=p.id;

      const lineScope=p.source_ta_mismatch?`
        <details class="v16-plan-advanced v16-required-input" open>
          <summary>Проверка целевой аудитории между флайтами</summary>
          <div class="warning">Во флайтах указаны разные целевые аудитории. Это реальное противоречие исходного файла: их нельзя объединить без пересчёта на одну ЦА.</div>
        </details>`:'';

      const identity=p.line_identity_review_required?`
        <details class="v16-plan-advanced v16-required-input" open>
          <summary>Нужно подтвердить разбивку на Lines</summary>
          <div class="v16-note">Названия листов похожи, но Campaign/Line в шапках расходятся. Подтверждение нужно только если это действительно отдельные Lines.</div>
          <label class="v16-confirm-line"><input type="checkbox" class="v16-line-identity-confirm"><span><strong>Это отдельные Lines</strong></span></label>
        </details>`:'';

      box.innerHTML=`
        <div class="v16-plan-head">
          <label class="v16-plan-title">
            <input type="checkbox" class="v16-plan-cb" checked>
            <span><strong>${esc(p.label||p.line||p.campaign||p.id)}</strong><span class="hint">${esc((p.sheet_names||[]).join(', '))}</span></span>
          </label>
          <div class="field"><label>Universe Line</label><input class="v16-universe" type="number" min="1" step="1" value="${p.universe?Math.round(p.universe):''}" placeholder="Universe ЦА"></div>
          <div class="v16-plan-facts">
            <span>ЦА: <strong>${esc(p.ta_name||'не распознана')}</strong></span>
            <span>${p.flight_count||0} флайт(а) · ${reachRows} охватных строк</span>
            <span>Готовность входов: <strong>${readiness}%</strong></span>
          </div>
        </div>

        <div class="v16-auto-strip">
          <div>
            <span class="v16-auto-label">B — browser ID на одно web-устройство</span>
            <strong>B = ${num(rec.B,2)}</strong>
            <small>Диапазон для этой ЦА: ${fmtRange(rec.B_min,rec.B_max)} · рассчитывается автоматически по ЦА.</small>
          </div>
          <div>
            <span class="v16-auto-label">D — устройств на одного человека</span>
            <strong>D = ${num(rec.D,2)}</strong>
            <small>Диапазон для этой ЦА: ${fmtRange(rec.D_min,rec.D_max)} · рассчитывается автоматически по ЦА.</small>
          </div>
          <div>
            <span class="v16-auto-label">L — период стабильности browser ID Chromium</span>
            <strong>L = 68 дней</strong>
            <small>Фиксированное значение методологии v1.6.</small>
          </div>
        </div>

        <details class="v16-plan-advanced">
          <summary>U<sub>D</sub> — если есть реальное измерение web-устройств</summary>
          <div class="v16-plan-advanced-body">
            <div class="field v16-ud-field"><label>U<sub>D</sub> для этой Line</label><input class="v16-line-ud" type="number" min="1" step="1" placeholder="Оставьте пустым, если измерения нет"></div>
            <div class="v16-note"><b>U<sub>D</sub> — измеренное количество уникальных web-устройств этой же ЦА, географии и периода.</b> Это не люди. Если такого измерения нет, поле остаётся пустым.</div>
          </div>
        </details>

        ${lineScope}
        ${identity}
      `;

      wrap.appendChild(box);
    }
    wrap.querySelectorAll('input,select').forEach(el=>el.addEventListener('change',()=>{markDirty();renderPrecalc();}));
    renderPrecalc();
  }

  function renderInputAudit(){
    const wrap=$(ids.inputAudit);if(!wrap)return;
    const state=allUserState(),plans=state.plans;
    if(!plans.length){wrap.innerHTML='<div class="warning">Не выбрано ни одной Line.</div>';return}
    wrap.innerHTML='<div class="v16-audit-grid">'+plans.map(p=>{
      const x=p.meta.input_profile||{},rows=x.reach_scope_rows??0;
      const l1=x.l1_ready_rows||0,reach=x.supplied_reach_rows||0,ifRows=x.impressions_frequency_rows||0;
      const hardTA=!!p.meta.source_ta_mismatch;
      const ready=rows>0&&l1===rows&&!hardTA;
      return `<div class="v16-audit-card">
        <div class="v16-audit-title">${ready?badge('готово к расчёту','ok'):badge('нужна проверка','warn')}<strong>${esc(p.meta.label||p.id)}</strong></div>
        <div class="v16-audit-stats">
          <span>Охватных строк: <b>${rows}</b></span>
          <span>С готовым Technical Reach: <b>${reach}</b></span>
          <span>Impressions + Frequency: <b>${ifRows}</b></span>
        </div>
        <div class="v16-note">${hardTA?'Во флайтах разные ЦА — это блокирует объединение Line.':ready?'Все обязательные охватные входы есть. CPC/CPR/CPA и другие неохватные закупки автоматически исключены из Reach.':'Проверьте только отмеченные выше исключения. Технические сообщения исходного файла доступны в диагностике после расчёта.'}</div>
      </div>`;
    }).join('')+'</div>';
  }

  function currentMode(){return $(ids.mode)?.value||'AUTO'}
  function currentK(){return Number($(ids.k)?.value||2.44)}
  function currentKIsOverride(){return Math.abs(currentK()-2.44)>1e-12}
  function syncL2ModeControls(){
    const detailed=currentMode()==='ADVANCED_WEB';
    document.querySelectorAll('#v16ExpertSettings .v16-advanced-setting').forEach(el=>{
      el.classList.toggle('hidden',!detailed);
    });
    [ids.L,ids.B,ids.D].forEach(id=>{
      const el=$(id); if(el)el.disabled=!detailed;
    });
  }

  function renderL2Decision(){
    const wrap=$(ids.l2Decision);if(!wrap)return;
    const state=allUserState(),mode=currentMode(),K=currentK(),kOverride=currentKIsOverride();
    if(!state.plans.length){wrap.innerHTML='';return}
    const detailed=mode==='ADVANCED_WEB';
    const B=detailed?(nval(ids.B)??null):null;
    const D=detailed?(nval(ids.D)??null):null;
    const L=detailed?(nval(ids.L)??68):null;
    wrap.innerHTML='<div class="v16-decision-list">'+state.plans.map(p=>{
      const rec=p.meta.advanced_recommended||{};
      const measuredUD=lineUD(p);
      const sourceCurve=p.meta.source_reach_pct_curve||null;
      const status=detailed
        ?`Детальный Web · B/D/L активны`
        :kOverride
          ?`Автоматически · задан K = ${num(K,2)}`
          :`Автоматически · K = ${num(K,2)}`;
      const explanation=detailed
        ?`Для Digital/Web-размещений используется детальный путь. Если environment/browser family не размечены, Detailed Web применяет прозрачные Web/Chromium-допущения. U_D при отсутствии измерения строится от автоматического D, поэтому ручной D больше не компенсирует сам себя.`
        :kOverride
          ?`AUTO использует только K как пользовательский параметр. Изменение K пересчитывает Human Reach; B, D и L в этом режиме не участвуют.`
          :`AUTO — самостоятельный быстрый расчёт для массового планирования. Он использует Technical Reach, исходную Frequency и K = ${num(K,2)}. B, D и L в AUTO полностью отключены.`;
      const benchmark=sourceCurve
        ?`В медиаплане найдена итоговая Reach-кривая. Она используется только как QA-сравнение после расчёта и никак не меняет результат AUTO или Detailed.`
        :`Готовой Reach-кривой в медиаплане нет — это нормально: AUTO рассчитывает охват полностью самостоятельно.`;
      return `<details class="v16-decision ${detailed?'advanced':'fallback'}">
        <summary><strong>${esc(p.meta.label||p.id)}</strong><span>${esc(status)}</span></summary>
        <div class="v16-decision-body">
          <div class="v16-formula-path compact">
            <span>Technical Reach</span><b>→</b><span>${detailed?'Detailed Web B / D / L':'AUTO planner model + K'}</span><b>→</b><span>Human Reach</span>
          </div>
          <div class="v16-decision-why">${esc(explanation)}</div>
          <div class="v16-note">${esc(benchmark)}</div>
          <div class="v16-param-row">
            <span><b>K = ${num(K,2)}</b><small>${kOverride?'USER_OVERRIDE':'model default'}</small></span>
            ${detailed?`
              <span><b>B = ${num(B??rec.B,2)}</b><small>${B!=null?'USER_OVERRIDE':'auto по ЦА'}</small></span>
              <span><b>D = ${num(D??rec.D,2)}</b><small>${D!=null?'USER_OVERRIDE':'auto по ЦА'}</small></span>
              <span><b>L = ${num(L,0)} дней</b><small>Detailed Web</small></span>
              <span><b>U_D ${measuredUD?num(measuredUD,0):'AUTO = U × auto-D'}</b><small>${measuredUD?'измеренный':'модельный baseline Universe устройств'}</small></span>`
              :'<span><b>B / D / L</b><small>автоматически, редактирование отключено</small></span>'}
          </div>
        </div>
      </details>`;
    }).join('')+'</div>';
  }

  function renderModelMap(){
    const wrap=$(ids.modelMap);if(!wrap)return;
    const cat=modelCatalog();
    if(!cat.level2){wrap.innerHTML='<div class="hint">Каталог модели загрузится после медиаплана.</div>';return}
    wrap.innerHTML=`
      <div class="v16-model-card emphasis"><div class="v16-model-level">LEVEL 1</div><strong>Строка медиаплана → Technical Reach</strong><p>Проверяем показы, частоту и Reach одной строки.</p></div>
      <div class="v16-model-card emphasis"><div class="v16-model-level">LEVEL 2</div><strong>Technical Reach → люди</strong><p>Переводим технические ID площадки в Human Reach.</p></div>
      <div class="v16-model-card"><div class="v16-model-level">LEVEL 3A</div><strong>Площадка во времени</strong><p>Объединяем периоды одной площадки без двойного счёта людей.</p></div>
      <div class="v16-model-card"><div class="v16-model-level">LEVEL 3B</div><strong>@1+…@6+</strong><p>Считаем, сколько людей получили минимум 1, 2, 3 и больше контактов.</p></div>
      <div class="v16-model-card"><div class="v16-model-level">LEVEL 4</div><strong>Площадки → канал</strong><p>Убираем пересечения пользователей между площадками одного канала.</p></div>
      <div class="v16-model-card"><div class="v16-model-level">LEVEL 5</div><strong>Каналы → флайт</strong><p>Объединяем каналы в уникальный Reach одного флайта.</p></div>
      <div class="v16-model-card"><div class="v16-model-level">LEVEL 6</div><strong>Флайты → Line</strong><p>Объединяем флайты с учётом повторной аудитории между периодами.</p></div>
      <div class="v16-model-card"><div class="v16-model-level">LEVEL 7</div><strong>Lines → Brand</strong><p>Объединяем Lines в общий Brand Reach на одной ЦА и Universe.</p></div>
    `;
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

  function friendlyModelPath(path){
    const p=String(path||'');
    if(!p)return '—';
    if(/L6_LINE.*IDENTITY/.test(p))return 'Один активный флайт — дополнительная дедупликация не требуется';
    if(/L7_BRAND.*IDENTITY/.test(p))return 'Одна Line — Brand Total равен результату Line';
    if(/L4B_CHANNEL.*IDENTITY/.test(p))return 'Одна площадка/аудитория в канале';
    if(/L5_FLIGHT.*IDENTITY/.test(p))return 'Один активный канал во флайте';
    if(/INDEPENDENCE/.test(p))return 'Нейтральное объединение независимых аудиторий';
    if(/ANALYTIC/.test(p))return 'Аналитическое объединение аудиторий';
    if(/MAXENT/.test(p))return 'Многомерная дедупликация аудиторий';
    if(/ADDRESSABILITY_NEUTRAL/.test(p))return 'Объединение с учётом доступной аудитории';
    return 'Канонический путь Reach Engine v1.6';
  }

  function renderMetrics(){
    const top=topResult(),u=topUniverse(),tf=targetFrequency(),wrap=$(ids.metrics);
    if(!top){
      wrap.innerHTML=`<div class="v16-overview-card v16-overview-empty warn"><strong>Итоговый результат пока не рассчитан.</strong><span>${esc(friendlyV16Error(v16Data?.brand_error||''))}</span></div>`;
      return;
    }
    const diagnostics=v16Data?.business_diagnostics||[];
    const rawDiagnostics=v16Data?.diagnostics||[];
    const warnings=diagnostics.filter(x=>x.severity==='WARNING');
    const errors=diagnostics.filter(x=>x.severity==='ERROR');
    const stateKind=errors.length?'err':warnings.length?'warn':'ok';
    const stateTitle=errors.length?'Расчёт требует проверки':warnings.length?'Расчёт выполнен, есть предупреждения':'Расчёт выполнен';
    const issues=errors.length?errors:warnings;
    const issueCount=issues.length;
    const issueLabel=errors.length
      ? issueCount===1?'ошибка':issueCount>=2&&issueCount<=4?'ошибки':'ошибок'
      : warnings.length
        ? issueCount===1?'предупреждение':issueCount>=2&&issueCount<=4?'предупреждения':'предупреждений'
        : 'без предупреждений';
    const stateIcon=errors.length||warnings.length?'!':'✓';
    const firstIssue=issues[0];

    const mode=currentMode(),K=currentK(),kOverride=currentKIsOverride();
    const l2Advanced=rawDiagnostics.filter(d=>d.code==='L2_ADVANCED');
    const l2Auto=rawDiagnostics.filter(d=>d.code==='L2_AUTO');
    const modeledUD=l2Advanced.some(d=>String(d.U_D_source||'').startsWith('MODEL_DERIVED_U_X_D'));
    let modelDetail=kOverride
      ?`AUTO рассчитан с заданным K = ${num(K,2)}`
      :'AUTO рассчитан независимо от готового Reach в медиаплане';
    let modelExplain=kOverride
      ?`K изменён пользователем, поэтому Human Reach и частотная кривая пересчитаны. Source Reach, если он есть в файле, используется только для QA-сравнения.`
      :`Быстрый AUTO использует Technical Reach, исходную Frequency и стандартный K = ${num(K,2)}. Готовый Reach из медиаплана не входит в формулу.`;

    if(mode==='ADVANCED_WEB'){
      modelDetail=l2Advanced.length?'Детальный Web-расчёт применён':'Detailed Web частично использовал AUTO fallback';
      modelExplain=l2Advanced.length
        ?`Для web-размещений Technical Reach переведён в людей через B, D и L. ${modeledUD?'При отсутствии измеренного U_D использован модельный device Universe на auto-D.':'Использован доступный измеренный U_D.'}${l2Auto.length?` Для неприменимых строк использован независимый AUTO fallback с K = ${num(K,2)}.`:''}`
        :`Для строк, где Detailed Web неприменим, использован независимый AUTO fallback с K = ${num(K,2)}. Source Reach не влияет на расчёт.`;
    }

    const stateDetail=errors.length?(firstIssue?.title||'Нужна проверка входных данных'):modelDetail;
    const stateExplain=errors.length
      ?'Результат нельзя считать финальным, пока не исправлена указанная проблема во входных данных.'
      :modelExplain;

    const reachRows=[1,2,3,4,5,6].map(k=>{
      const val=Number(reachAt(top,k)),share=u&&Number.isFinite(val)?val/u:null,selected=k===tf;
      return `<div class="v16-overview-reach-row ${selected?'selected':''}">
        <span class="v16-overview-frequency-key">@${k}+</span>
        <strong>${share!=null?pct(share,2):'—'}</strong>
        <b>${Number.isFinite(val)?num(val,0):'—'}</b>
      </div>`;
    }).join('');

    const avg=top.avg_frequency!=null?num(top.avg_frequency,1):'—';
    const dedupRate=top.dedup_rate!=null?pct(top.dedup_rate,2):'—';

    wrap.innerHTML=`
      <section class="v16-overview-card v16-overview-status ${stateKind}">
        <div class="v16-overview-status-top">
          <div class="v16-overview-status-icon">${stateIcon}</div>
          <div>
            <h3>${stateTitle}</h3>
            ${issueCount
              ?`<div class="v16-overview-status-issue"><strong>${issueCount}</strong><span>${issueLabel}</span></div>`
              :`<div class="v16-overview-status-issue ok"><strong>Готово</strong><span>${issueLabel}</span></div>`}
          </div>
        </div>
        <div class="v16-overview-status-detail">
          <b>${esc(stateDetail)}</b>
          <span>${esc(stateExplain)}</span>
          ${issueCount?'<small>Подробности — в блоке предупреждений и технической диагностике ниже.</small>':''}
        </div>
      </section>

      <section class="v16-overview-card v16-overview-frequency">
        <div class="v16-overview-card-head">
          <h3>Охват по частоте</h3>
          <p>Охват @1+…@6+ одновременно показан в % целевой аудитории и в людях.</p>
        </div>
        <div class="v16-overview-reach-head">
          <span>Частота</span><span>% ЦА</span><span>Люди</span>
        </div>
        <div class="v16-overview-reach-body">${reachRows}</div>
      </section>

      <section class="v16-overview-card v16-overview-summary">
        <div class="v16-overview-card-head"><h3>Ключевые результаты</h3></div>
        <div class="v16-overview-summary-list">
          <div><span>Universe результата</span><strong>${u?num(u,0):'—'}</strong></div>
          <div><span>Impressions</span><strong>${top.impressions!=null?num(top.impressions,0):'—'}</strong></div>
          <div><span>Среднее число контактов</span><strong>${avg}</strong><small>на @1+ человека · I / @1+</small></div>
          <div><span>Gross Reach Sum</span><strong>${top.gross_reach_sum!=null?num(top.gross_reach_sum,0):'—'}</strong><small>сумма охватов до дедупликации</small></div>
          <div><span>Повторная аудитория</span><strong>${top.dedup_people!=null?num(top.dedup_people,0):'—'}</strong><small>${dedupRate} от Gross Reach</small></div>
          <div><span>Модель объединения</span><strong class="v16-model-path">${esc(friendlyModelPath(top.model_path))}</strong></div>
        </div>
      </section>`;
  }

  function renderFrequencyProfile(){
    const top=topResult(),u=topUniverse(),wrap=$(ids.profile);
    if(!top||!u){wrap.innerHTML='<div class="hint">Нет единого результата для построения кривой.</div>';return}
    const tf=targetFrequency();
    const pts=[1,2,3,4,5,6].map(k=>{
      const val=Number(reachAt(top,k)||0),share=Math.max(0,Math.min(1,val/u));
      return {k,val,share,pct:share*100};
    });
    const W=360,H=300,L=42,PLOT_L=62,R=12,T=20,B=38;
    const x=k=>PLOT_L+(k-1)*(W-PLOT_L-R)/5;
    const y=p=>T+(100-p)*(H-T-B)/100;
    const poly=pts.map(p=>`${x(p.k).toFixed(1)},${y(p.pct).toFixed(1)}`).join(' ');
    const grid=[0,25,50,75,100].map(p=>{
      const yy=y(p);
      return `<g><line x1="${L}" y1="${yy}" x2="${W-R}" y2="${yy}" class="v16-chart-grid"/><text x="${L-6}" y="${yy+4}" text-anchor="end" class="v16-chart-axis">${num(p,0)}%</text></g>`;
    }).join('');
    const dots=pts.map(p=>`<g class="${p.k===tf?'selected':''}"><circle cx="${x(p.k)}" cy="${y(p.pct)}" r="${p.k===tf?5:4}" class="v16-chart-dot"/><text x="${x(p.k)}" y="${H-12}" text-anchor="middle" class="v16-chart-axis">@${p.k}+</text></g>`).join('');

    wrap.innerHTML=`
      <div class="v16-er-chart">
        <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Кривая Effective Reach @1+…@6+">
          ${grid}
          <polyline points="${poly}" class="v16-chart-line"/>
          ${dots}
        </svg>
      </div>`;
  }

  function renderExactFrequency(){
    const top=topResult(),u=topUniverse(),wrap=$(ids.exact);
    if(!top||!u||!Array.isArray(top.exact_counts)){wrap.innerHTML='<div class="hint">Нет единого total для exact frequency buckets.</div>';return}
    const reached=Number(top.reach_1p||0),labels=['Ровно 1 контакт','Ровно 2 контакта','Ровно 3 контакта','Ровно 4 контакта','Ровно 5 контактов','6+ контактов'];
    wrap.innerHTML='<div class="v16-exact-grid">'+top.exact_counts.map((v,i)=>{
      const people=Number(v||0);
      return `<div class="v16-exact-card">
        <div class="v16-exact-k">${labels[i]}</div>
        <strong>${num(people,0)} человек</strong>
        <span>${pct(people/u,2)} от целевой аудитории</span>
        <small>${reached?pct(people/reached,2):'—'} среди людей с @1+</small>
      </div>`;
    }).join('')+'</div>';
  }

  function reachCell(r,k){
    const u=Number(r.universe),val=Number(r[`reach_${k}p`]);
    if(!Number.isFinite(val))return '<span class="na">—</span>';
    return `<strong>${u>0?pct(val/u,2):'—'}</strong><span class="v16-pct">${num(val,0)} человек</span>`;
  }

  function hierarchyType(level){
    return level==='Brand'?'Кампания':level==='Line'?'Линейка':level==='Flight'?'Флайт':level==='Platform'?'':'Канал';
  }
  function hierarchyClass(level){
    return level==='Brand'?'v16-level-brand':level==='Line'?'v16-level-line':level==='Flight'?'v16-level-flight':level==='Platform'?'v16-level-platform':'v16-level-channel';
  }
  function renderTable(){
    const rows=v16Data?.hierarchy||[],table=$(ids.table);
    if(!table)return;
    const tf=targetFrequency(),freqs=tf===1?[1]:[1,tf];
    const contextKey=r=>[r.line||'',r.flight||'',r.channel||r.name||''].join('||');
    const channelKeys=new Map();
    let seq=0;
    rows.filter(r=>r.level==='Channel').forEach(r=>channelKeys.set(contextKey(r),'ch'+(++seq)));

    let h='<thead><tr><th>Уровень / объект</th><th>Линейка</th><th>Флайт</th><th class="num">Universe</th><th class="num">Impressions</th>'+
      freqs.map(k=>`<th class="num v16-hierarchy-kpi">@${k}+<span class="v16-th-sub">% ЦА · люди${k===tf?' · выбранная частота':''}</span></th>`).join('')+
      '<th class="num">Среднее число контактов</th><th class="num">Дедупликация<span class="v16-th-sub">чел. · % Gross Reach</span></th><th>Модель объединения</th></tr></thead><tbody>';

    for(const r of rows){
      const level=r.level||'Channel',type=hierarchyType(level),cls=hierarchyClass(level);
      const key=level==='Platform'?channelKeys.get(contextKey(r)):level==='Channel'?channelKeys.get(contextKey(r)):null;
      const hasPlatforms=level==='Channel' && rows.some(x=>x.level==='Platform'&&contextKey(x)===contextKey(r));
      const isPlatform=level==='Platform';
      const toggle=hasPlatforms
        ?`<button type="button" class="v16-hierarchy-toggle" data-channel-key="${esc(key)}" aria-expanded="false" title="Показать площадки">+</button>`
        :'<span class="v16-hierarchy-toggle-spacer"></span>';
      const typeBadge=type?`<span class="v16-hierarchy-type ${level.toLowerCase()}">${esc(type)}</span>`:'';
      const object=`<div class="v16-hierarchy-object">${isPlatform?'<span class="v16-hierarchy-toggle-spacer"></span>':toggle}${typeBadge}<strong>${esc(r.name||'—')}</strong></div>`;
      const gross=Number(r.gross_reach_sum||0),dedup=Number(r.dedup_people||0),unique=Number(r.reach_1p||0);
      const invariantOk=!gross||Math.abs((gross-dedup)-unique)<=Math.max(1,Math.abs(gross)*1e-8) && dedup>=-1e-6 && dedup<=gross+1e-6;
      const rowAttrs=isPlatform?` data-parent-channel="${esc(key||'')}"`:'';
      h+=`<tr class="${cls}${isPlatform?' v16-platform-child hidden':''}"${rowAttrs}>
        <td data-label="Уровень / объект">${object}</td>
        <td data-label="Линейка">${esc(r.line||'')}</td>
        <td data-label="Флайт">${esc(r.flight||'')}</td>
        <td data-label="Universe" class="num">${num(r.universe,0)}</td>
        <td data-label="Impressions" class="num">${r.impressions!=null?num(r.impressions,0):'—'}</td>`;
      for(const k of freqs)h+=`<td data-label="@${k}+" class="num v16-reach-cell ${k===tf?'selected':''}">${reachCell(r,k)}</td>`;
      const isTotalLevel=level==='Flight'||level==='Line'||level==='Brand';
      const hideZeroTotalDedup=isTotalLevel && Math.abs(dedup)<=1e-6;
      const dedupHtml=hideZeroTotalDedup
        ?''
        :`<strong>${r.dedup_people!=null?num(r.dedup_people,0):'—'}</strong><span class="v16-pct">${r.dedup_rate!=null?pct(r.dedup_rate,2):'—'}</span>`;
      h+=`<td data-label="Среднее число контактов" class="num"><strong>${r.avg_frequency!=null?num(r.avg_frequency,1)+' на @1+ человека':'—'}</strong></td>
        <td data-label="Дедупликация" class="num v16-dedup-cell ${invariantOk?'':'invalid'}">${dedupHtml}</td>
        <td data-label="Модель объединения">${r.model_path?esc(friendlyModelPath(r.model_path)):'—'}</td></tr>`;
    }
    table.innerHTML=h+'</tbody>';
    table.querySelectorAll('.v16-hierarchy-toggle').forEach(btn=>btn.addEventListener('click',()=>{
      const key=btn.dataset.channelKey,open=btn.getAttribute('aria-expanded')==='true';
      btn.setAttribute('aria-expanded',String(!open));
      btn.textContent=open?'+':'−';
      btn.title=open?'Показать площадки':'Скрыть площадки';
      table.querySelectorAll(`.v16-platform-child[data-parent-channel="${CSS.escape(key)}"]`).forEach(row=>row.classList.toggle('hidden',open));
    }));
  }

  function renderBusinessDiagnostics(){
    const wrap=$(ids.businessDiag);if(!wrap)return;
    const rows=v16Data?.business_diagnostics||[];
    if(!rows.length){wrap.innerHTML='<div class="v16-business-ok"><strong>Критических предупреждений нет.</strong><span>Технический лог и применённый путь остаются доступны ниже.</span></div>';return}
    const explain=d=>{
      const tag=String(d.tag||'').toUpperCase(),sev=d.severity||'INFO';
      if(tag.includes('TA MISMATCH'))return ['Почему важно','Охваты разных целевых аудиторий нельзя корректно объединить.','Что делать','Нормализуйте входы на одну и ту же целевую аудиторию до объединения.'];
      if(tag.includes('UNIVERSE MISMATCH'))return ['Почему важно','Для объединения нужен один размер одной и той же целевой аудитории.','Что делать','Подтвердите единый Universe только после проверки TA, географии и human-definition.'];
      if(tag.includes('SCOPE EXCLUSION'))return ['Почему важно','Для исключённых строк нет достаточного Reach-входа, поэтому их охват нельзя честно моделировать.','Что делать','Оставьте их вне Reach либо добавьте измеренные Impressions + Frequency/Technical Reach.'];
      if(tag.includes('DATA QUALITY'))return ['Почему важно','Ошибка находится в исходном медиаплане; движок не исправляет её автоматически.','Что делать','Проверьте указанную строку/дату/Reach-кривую в исходном файле.'];
      if(tag.includes('FALLBACK'))return ['Что это значит','Точного входа нет, поэтому применён разрешённый запасной путь модели.','Что делать','Если есть измеренный вход, укажите его; иначе fallback остаётся явно отмеченным.'];
      if(tag.includes('APPROXIMATION'))return ['Что это значит','Часть расчёта основана на разрешённом приближении.','Что делать','Используйте измеренный сегментный вход, если он доступен.'];
      if(tag.includes('MODEL DEFAULT'))return ['Что это значит','Для параметра нет измеренного значения, поэтому использован стандарт модели v1.6.','Что делать','Ничего, если подтверждённого измеренного значения нет.'];
      if(tag.includes('GLOBAL FEASIBILITY'))return ['Почему важно','Исходные model-default пересечения пришлось скорректировать, чтобы вся система вероятностей была математически возможна.','Что делать','Измеренные/custom пересечения не изменяются; проверьте их только если получили отдельную validation error.'];
      if(sev==='ERROR')return ['Почему важно','Эта проблема блокирует корректный итоговый расчёт.','Что делать','Исправьте или подтвердите вход, указанный в сообщении.'];
      return ['Что это значит','Движок показывает применённое допущение или проверку, чтобы результат был аудируемым.','Что делать','Дополнительных действий не требуется, если входы подтверждены.'];
    };
    wrap.innerHTML='<div class="v16-business-list">'+rows.map(d=>{
      const kind=d.severity==='ERROR'?'err':d.severity==='WARNING'?'warn':'ok',e=explain(d);
      return `<div class="v16-business-item ${kind}">
        <div class="v16-business-head">${badge(d.tag||'INFO',kind)}<strong>${esc(d.title||'')}</strong><span>Level ${esc(d.level??'—')}</span></div>
        <div class="v16-business-message">${esc((d.severity==='ERROR'?friendlyV16Error(d.message):d.message)||'')}</div>
        <div class="v16-business-help"><div><b>${esc(e[0])}</b><span>${esc(e[1])}</span></div><div><b>${esc(e[2])}</b><span>${esc(e[3])}</span></div></div>
      </div>`;
    }).join('')+'</div>';
  }

  function formatTrace(d){
    const code=d.code||'';
    if(code==='L1_TECHNICAL_REACH')return `Technical Reach = ${num(d.R_tech,0)} · source ${d.source} · F tolerance ${d.frequency_tolerance}`;
    if(code==='L2_AUTO')return `AUTO: независимый planner path · K=${num(d.K,2)} · people factor=${num(d.people_factor,4)}`;
    if(code==='L2_QUICK')return `Legacy Quick: Rpeople=Rtech/K · K=${num(d.K,2)}`;
    if(code==='L2_ADVANCED')return `Advanced ${d.environment}: ${(d.path||[]).join(' → ')} · K_time=${num(d.K_time,4)} · Rstable=${num(d.R_stable,0)} · Rdevice=${num(d.R_device,0)} · Rpeople=${num(d.R_people,0)}`;
    if(code==='L3A_PLATFORM_FLIGHT')return `${d.model_path} · U_p=${num(d.U_p,0)}${d.platform_universe_assumed?' (assumed U)':''} · ρ=${d.rho_base??'N/A'}`;
    if(code==='L3B_EFFECTIVE_REACH')return `${d.model} · Fhuman=${num(d.F_human,3)} · Ftech=${d.technical_frequency==null?'N/A':num(d.technical_frequency,3)} · σ=${d.sigma??'N/A'} · μ=${d.mu==null?'N/A':num(d.mu,4)}`;
    if(code==='L4_CHANNEL')return `${d.channel}: ${d.model_path} · D overall=${pct(d.D_overall||0,2)} · solver ${d.solver_iterations??0} iter`;
    if(code==='L5_FLIGHT')return `${d.flight}: ρ target=${d.rho_target} → effective=${d.rho_effective} · λ=${d.lambda} · ${d.model_path}`;
    if(code==='L6_LINE')return `Flights → Line · λ=${d.lambda??1} · ${d.model_path} · D=${pct(d.D_L6||0,2)}`;
    if(code==='L7_BRAND')return `Lines → Brand · U_B=${num(d.U_B,0)} · ${d.BrandAddressabilityMap} · ${d.model_path}`;
    return JSON.stringify(d);
  }

  function renderAppliedTrace(){
    const wrap=$(ids.trace);if(!wrap)return;
    const ds=v16Data?.diagnostics||[];
    const keep=new Set(['L1_TECHNICAL_REACH','L2_AUTO','L2_QUICK','L2_ADVANCED','L3A_PLATFORM_FLIGHT','L3B_EFFECTIVE_REACH','L4_CHANNEL','L5_FLIGHT','L6_LINE','L7_BRAND']);
    const rows=ds.filter(d=>keep.has(d.code));
    if(!rows.length){wrap.innerHTML='<div class="hint">Расчётный путь не сформирован.</div>';return}
    const names={
      '1':'Проверили исходный Technical Reach',
      '2':'Перевели технические идентификаторы в людей',
      '3':'Учли время и распределение частоты',
      '4':'Объединили площадки внутри каналов',
      '5':'Объединили каналы внутри флайтов',
      '6':'Объединили флайты в Line',
      '7':'Объединили Lines в Brand'
    };
    const grouped={};rows.forEach(d=>{const l=String(d.level||'?');(grouped[l]??=[]).push(d)});
    wrap.innerHTML='<div class="v16-method-steps">'+Object.keys(grouped).sort().map(level=>`
      <details class="v16-trace-level">
        <summary><span class="v16-method-num">${esc(level)}</span><strong>${esc(names[level]||('Level '+level))}</strong><span>${grouped[level].length} операций</span></summary>
        <div class="v16-trace-items">${grouped[level].map(d=>`<div><code>${esc(d.code)}</code><span>${esc(formatTrace(d))}</span></div>`).join('')}</div>
      </details>`).join('')+'</div>';
  }

  function renderDiagnostics(){
    const ds=v16Data?.diagnostics||[],lines=['REACH ENGINE v1.6 — TECHNICAL LOG','Canonical Levels 1–7 · production Web 0.52 isolated.',''];
    for(const d of ds)lines.push('• '+JSON.stringify(d));
    $(ids.diag).textContent=lines.join('\n');
    const warn=$(ids.warning),msgs=[];
    if(v16Data?.brand_error)msgs.push(friendlyV16Error(v16Data.brand_error));
    if((v16Data?.business_diagnostics||[]).some(x=>x.severity==='WARNING'))msgs.push('Есть модельные допущения. Подробности доступны в технической диагностике.');
    if(msgs.length){warn.innerHTML=msgs.map(esc).join('<br>');warn.classList.remove('hidden')}else warn.classList.add('hidden');
  }

  function renderResults(){
    if(!v16Data)return;
    $(ids.results).classList.remove('hidden');
    renderMetrics();renderFrequencyProfile();renderExactFrequency();renderTable();
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

    const brandRaw=$(ids.brandU)?.value?.trim()||'';
    let q={
      selected_plan_ids:plans.map(x=>x.id),
      universes:Object.fromEntries(plans.map(x=>[x.id,x.universe])),
      l2_mode:currentMode(),
      K:currentK(),
      advanced:{
        L:currentMode()==='ADVANCED_WEB'?Number($(ids.L)?.value||68):null,
        B:currentMode()==='ADVANCED_WEB'?nval(ids.B):null,
        D:currentMode()==='ADVANCED_WEB'?nval(ids.D):null,
        web_device_universes:state.web_device_universes
      },
      line_scope_confirmed:state.line_scope_confirmed,
      line_identity_confirmed:state.line_identity_confirmed,
      brand_universe:brandRaw===''?null:Number(brandRaw),
      brand_universe_confirmed:brandRaw!=='' && (plans.length===1 || !!$(ids.brandUConfirm)?.checked),
      brand_master_ta:$(ids.brandTA)?.value?.trim()||'',
      brand_master_geo:$(ids.brandGeo)?.value?.trim()||'',
      brand_horizon_start:$(ids.brandStart)?.value||'',
      brand_horizon_end:$(ids.brandEnd)?.value||'',
      brand_scope_confirmed:plans.length===1 || !!$(ids.brandScopeConfirm)?.checked
    };

    try{
      q=deepMergeV16(q,expertCanonicalInputs());
      clearResults();
      setStatus(ids.status,'<span class="spinner"></span>Считаю Levels 1–7…');
      const data=await v16Call('reach_v16.calculate(p,q)',{p:v16Path,q:JSON.stringify(q)});
      v16Data=data;
      renderResults();
      const suffix=v16Data.status==='GO'?'Reach рассчитан':'Lines рассчитаны; Brand Total требует проверки Level 7';
      setStatus(ids.status,`✓ ${suffix} · ${v16Data.lines?.length||0} Line`,'ok');
    }catch(e){
      console.error(e);
      const message=errorMessage(e);
      clearResults();
      setStatus(ids.status,'Ошибка расчёта: '+esc(friendlyV16Error(message)),'err');
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
      v16File=file;$(ids.file).innerHTML=`<strong>${esc(file.name)}</strong><span>${num(file.size/1024/1024,2)} МБ · файл загружен локально</span>`;
      v16Meta=await v16Call('reach_v16.discover(p)',{p:v16Path});
      if(!v16Meta.plans?.length)throw new Error('В файле не найден рабочий медиаплан');
      renderPlanControls();
      prefillBrandScope();
      syncL2ModeControls();
      $(ids.controls).classList.remove('hidden');
      setStatus(ids.status,`Файл распознан: ${v16Meta.plans.length} Line. Охватные строки и технические параметры определены автоматически.`,'ok');
    }catch(e){
      console.error(e);clearResults();
      setStatus(ids.status,'Ошибка загрузки: '+esc(friendlyV16Error(errorMessage(e))),'err');
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
    $(ids.mode)?.addEventListener('change',()=>{syncL2ModeControls();markDirty();renderPrecalc()});
    [ids.k,ids.L,ids.B,ids.D].forEach(id=>$(id)?.addEventListener('change',markDirty));
    syncL2ModeControls();
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