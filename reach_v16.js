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

  function friendlyV16Error(message){
    const raw=String(message||'');
    const rules=[
      [/L3A_TEMPORAL_INPUT_REQUIRED/, 'Площадка разбита на несколько периодов, но нет общего Reach за весь флайт. Укажите aggregate Technical Reach или weekly Human Reach.'],
      [/TA_NORMALIZATION_REQUIRED|L6_SCOPE_TA_MISMATCH/, 'Во флайтах разные целевые аудитории. Такой Reach нельзя объединять — сначала нужны входы, пересчитанные на одну Line Master TA.'],
      [/L6_SCOPE_UNIVERSE_MISMATCH|LINE_MASTER_UNIVERSE_CONFIRMATION_REQUIRED|LINE_MASTER_UNIVERSE_OVERRIDE_CONFIRMATION_REQUIRED/, 'Во флайтах различается Universe. Проверьте, что TA, география и human-definition одинаковы, затем подтвердите единый Line Master Universe.'],
      [/LINE_IDENTITY_HEADER_CONFLICT/, 'Названия листов и Campaign/Line headers противоречат друг другу. Подтвердите текущую разбивку только если это действительно разные Lines.'],
      [/BRAND_MASTER_UNIVERSE_REQUIRED/, 'Для Brand Total нужен явный подтверждённый Brand Master Universe. Автоматический max Line U используется только как черновик.'],
      [/GLOBAL.*FEASIB|infeasib/i, 'Заданные пересечения математически несовместимы. Движок не подгоняет измеренные/custom входы — проверьте исходные пересечения и Universe.']
    ];
    for(const [re,txt] of rules)if(re.test(raw))return txt+' Техническая причина: '+raw;
    return raw;
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
        <div class="v16-unit-row v16-unit-card" data-unit-id="${esc(u.id)}">
          <div class="v16-unit-main">
            <strong>${esc(u.platform||'Площадка')}</strong>
            <span>${esc(u.channel||'—')} · ${esc(u.format||'—')}</span>
            <small>${esc(u.sheet)} · строка ${u.row}</small>
          </div>
          <div class="field">
            <label>К какой группе пользователей относится?</label>
            <input class="v16-family" value="${esc(u.suggested_family||'')}" aria-label="Группа пользователей" placeholder="Например: VK, Яндекс, Rutube">
            <div class="hint">Размещения одной экосистемы можно объединить в одну группу, чтобы не посчитать одного человека несколько раз.</div>
          </div>
          <div class="field">
            <label>Где показывалась реклама?</label>
            <select class="v16-env">
              <option value="UNKNOWN" selected>Не знаю / не подтверждено</option>
              <option value="WEB">Сайт в браузере (Web)</option>
              <option value="MOBILE_APP">Мобильное приложение</option>
              <option value="CTV">Smart TV / CTV / OTT</option>
            </select>
            <div class="hint">Если не уверены — оставьте «Не знаю». Движок применит базовый безопасный расчёт.</div>
          </div>
          <details class="v16-unit-tech">
            <summary>Есть дополнительные измеренные данные по устройствам?</summary>
            <div class="v16-unit-tech-grid">
              <div class="field">
                <label>Тип браузера</label>
                <select class="v16-browser">
                  <option value="UNKNOWN" selected>Не определён</option>
                  <option value="CHROMIUM">Chromium / Chrome-подобный</option>
                  <option value="SAFARI">Safari / WebKit</option>
                </select>
              </div>
              <div class="field">
                <label>Размер базы web-устройств для этой строки (U_D)</label>
                <input class="v16-unit-ud" type="number" min="1" step="1" placeholder="Только если есть измерение">
              </div>
              <div class="field">
                <label>Измеренный Reach по устройствам</label>
                <input class="v16-device-reach" type="number" min="0" step="1" placeholder="Для App / CTV, если есть">
              </div>
            </div>
            <div class="hint">Не заполняйте эти поля «на глаз». Они нужны только для более детального Advanced-расчёта.</div>
          </details>
        </div>`).join('');

      const sourceFlights=(p.source_flights||[]).map(f=>`
        <div class="v16-scope-flight">
          <strong>${esc(f.label||f.id)}</strong>
          <span>ЦА: ${esc(f.ta_name||'—')}</span>
          <span>Размер ЦА: ${f.source_universe?num(f.source_universe,0):'—'}</span>
          <span>${esc(f.start||'—')} — ${esc(f.end||'—')}</span>
        </div>`).join('');

      const lineScopeReview=`
        <details class="v16-plan-advanced" ${(p.source_universe_mismatch||p.source_ta_mismatch)?'open':''}>
          <summary>Проверка ЦА и её размера по флайтам</summary>
          <div class="v16-scope-flight-list">${sourceFlights||'<div class="v16-note">Параметры флайтов в источнике не распознаны.</div>'}</div>
          ${p.source_ta_mismatch?'<div class="v16-explain-alert err"><strong>Во флайтах разные целевые аудитории.</strong><span>Их охват нельзя корректно объединить. Сначала нужны входы, пересчитанные на одну и ту же ЦА.</span></div>':''}
          ${p.source_universe_mismatch?'<div class="v16-explain-alert warn"><strong>Размер одной и той же ЦА различается между флайтами.</strong><span>Нужно выбрать актуальный единый Universe только после проверки, что ЦА, география и определение человека действительно одинаковы.</span></div>':''}
          <label class="v16-confirm-line">
            <input type="checkbox" class="v16-line-scope-confirm">
            <span><strong>Подтверждаю единый размер ЦА для этой Line</strong><small>Разрешает нормализацию Universe. Не разрешает объединять разные целевые аудитории.</small></span>
          </label>
        </details>`;

      const identityReview=p.line_identity_review_required?`
        <div class="v16-explain-alert warn v16-line-identity-warning">
          <strong>Непонятно, это одна кампания или несколько.</strong>
          <span>Названия листов похожи, но Campaign/Line в шапках расходятся. Движок не будет объединять их автоматически.</span>
          <label class="v16-confirm-line">
            <input type="checkbox" class="v16-line-identity-confirm">
            <span><strong>Подтверждаю, что это разные Lines</strong><small>Если это одна Line — сначала исправьте названия/идентичность в исходном медиаплане.</small></span>
          </label>
        </div>`: '';

      const platformScopeInputs=(p.platform_scopes||[]).length?`
        <details class="v16-plan-advanced" open>
          <summary>Площадки, разбитые на несколько периодов · ${p.platform_scopes.length}</summary>
          <div class="v16-explain-alert warn">
            <strong>Охват разных месяцев нельзя просто сложить.</strong>
            <span>Один и тот же человек мог увидеть рекламу в нескольких периодах. Нужен общий Reach площадки за весь флайт или недельные Human Reach.</span>
          </div>
          <div class="v16-platform-scope-grid">
            ${(p.platform_scopes||[]).map(s=>`
              <div class="v16-platform-scope-card">
                <strong>${esc(s.platform||s.scope_id)}</strong>
                <small>${esc(s.channel||'—')} · ${s.fragment_count||0} строк в исходнике</small>
                <div class="v16-scope-rows">${(s.source_rows||[]).map(x=>`${esc(x.sheet)}:${x.row}`).join(' · ')}</div>
                <div class="field">
                  <label>Общий Technical Reach за весь флайт</label>
                  <input class="v16-aggregate-rtech" data-scope-id="${esc(s.scope_id)}" type="number" min="0" step="1" placeholder="Введите только измеренное значение">
                </div>
                <div class="v16-note">Если есть недельный Human Reach, его можно передать через экспертные измеренные входы.</div>
              </div>`).join('')}
          </div>
        </details>`: '';

      const excludedReach=(p.excluded_reach_rows||[]).length?`
        <details class="v16-plan-advanced">
          <summary>Строки, которые не участвуют в расчёте Reach · ${p.excluded_reach_rows.length}</summary>
          <div class="v16-note" style="margin:8px 0">У этих размещений нет полного охватного входа: Impressions + (Frequency или Technical Reach). Они остаются частью медиаплана, но движок не придумывает для них аудиторию.</div>
          <div class="v16-excluded-list">
            ${p.excluded_reach_rows.map(x=>`<div><strong>${esc(x.platform||x.unit_id)}</strong><span>${esc(x.channel||'—')} · ${esc(x.buying_model||'—')} · ${esc(x.reason||'')}</span><small>${esc(x.sheet)}:${x.row}</small></div>`).join('')}
          </div>
        </details>`: '';

      const sourceQaItems=(p.import_warnings||[]).filter(w=>String(w.code||'').startsWith('SOURCE_'));
      const sourceQaReview=sourceQaItems.length?`
        <details class="v16-plan-advanced v16-source-qa" open>
          <summary>Ошибки и предупреждения исходного файла · ${sourceQaItems.length}</summary>
          <div class="v16-source-qa-list">
            ${sourceQaItems.map(w=>`<div class="${String(w.code||'').includes('INVALID')?'err':'warn'}"><strong>${esc(w.code||'SOURCE_QA')}</strong><span>${esc(w.message||'')}</span></div>`).join('')}
          </div>
        </details>`: '';

      const aon=(p.aon_pairs||[]).length?`
        <details class="v16-plan-advanced">
          <summary>Always-on и короткие burst-флайты</summary>
          <div class="v16-note" style="margin:8px 0">Годовой Always-on Reach нельзя автоматически разложить на короткий период. Если есть измерение, укажите Human Reach Always-on ровно за период соответствующего burst.</div>
          <div class="v16-aon-grid">
            ${(p.aon_pairs||[]).map(x=>`
              <div class="field">
                <label>${esc(x.aon_label)} → ${esc(x.burst_label)} · ${esc(x.burst_start||'')}—${esc(x.burst_end||'')}</label>
                <input class="v16-aon-slice" data-aon-id="${esc(x.aon_flight_id)}" data-burst-id="${esc(x.burst_flight_id)}" type="number" min="0" step="1" placeholder="Human Reach за этот период">
              </div>`).join('')}
          </div>
        </details>`: '';

      box.innerHTML=`
        <div class="v16-plan-head">
          <label class="v16-plan-title">
            <input type="checkbox" class="v16-plan-cb" checked>
            <span><strong>${esc(p.label||p.line||p.campaign||p.id)}</strong><span class="hint">${esc((p.sheet_names||[]).join(', '))}</span></span>
          </label>
          <div class="field"><label>Размер целевой аудитории для этой Line</label><input class="v16-universe" type="number" min="1" step="1" value="${p.universe?Math.round(p.universe):''}" placeholder="Universe, человек"></div>
          <div class="v16-plan-facts">
            <span>ЦА: <strong>${esc(p.ta_name||'не распознана')}</strong></span>
            <span>${p.flight_count||0} флайта · ${reachRows} из ${p.placement_count||0} строк участвуют в Reach</span>
            <span>Данных достаточно для ${readiness}% охватных строк</span>
          </div>
        </div>

        ${lineScopeReview}
        ${identityReview}
        ${platformScopeInputs}
        ${sourceQaReview}
        ${excludedReach}

        <details class="v16-mapping" open>
          <summary>Проверьте группировку площадок для дедупликации</summary>
          <div class="v16-human-intro">
            <strong>Зачем это нужно?</strong>
            <span>Один человек может встретиться в нескольких размещениях одной экосистемы. Группа пользователей помогает движку не посчитать его дважды.</span>
            <small>Пример: несколько размещений VK логично могут относиться к одной группе «VK». Если вы не уверены — не угадывайте, а проверьте данные площадки.</small>
          </div>
          <div class="v16-unit-cards">${units}</div>
          <label class="v16-confirm-line">
            <input type="checkbox" class="v16-family-confirm">
            <span><strong>Я проверил группы пользователей для всех площадок</strong><small>Без этого подтверждения расчёт объединения площадок не запускается.</small></span>
          </label>
        </details>

        <details class="v16-plan-advanced" open>
          <summary>Как движок переводит браузеры и устройства в людей</summary>
          <div class="v16-human-intro">
            <strong>Зачем вообще нужны B, D, L и U_D?</strong>
            <span>Technical Reach площадки — это технические идентификаторы, а не обязательно реальные люди. Один человек может иметь несколько browser ID и несколько устройств, а browser ID может меняться со временем. Эти параметры нужны, чтобы последовательно убрать такие технические дубли.</span>
            <small>Если измеренного U_D нет, ничего придумывать не нужно: движок использует стандартный Quick-путь.</small>
          </div>
          <div class="v16-auto-strip v16-parameter-explain">
            <div>
              <span class="v16-auto-label">B · browser multiplicity</span>
              <strong>B = ${num(rec.B,2)}</strong>
              <small><b>Что это в жизни:</b> модельное среднее число browser ID / браузерных профилей на одно web-устройство.</small>
              <small><b>Зачем:</b> чтобы разные браузеры и browser ID на одном ноутбуке/телефоне не считались разными устройствами.</small>
              <small><b>Почему здесь ${num(rec.B,2)}:</b> движок рассчитывает коэффициент по возрастному составу ЦА «${esc(p.ta_name||'—')}». Для возрастных сегментов этой ЦА модель даёт диапазон ${fmtRange(rec.B_min,rec.B_max)}.</small>
            </div>
            <div>
              <span class="v16-auto-label">D · device multiplicity</span>
              <strong>D = ${num(rec.D,2)}</strong>
              <small><b>Что это в жизни:</b> модельное среднее число устройств на одного человека.</small>
              <small><b>Зачем:</b> чтобы телефон, ноутбук и планшет одного человека не считались несколькими людьми.</small>
              <small><b>Почему здесь ${num(rec.D,2)}:</b> движок рассчитывает коэффициент по возрастному составу ЦА «${esc(p.ta_name||'—')}». Для возрастных сегментов этой ЦА модель даёт диапазон ${fmtRange(rec.D_min,rec.D_max)}.</small>
            </div>
            <div>
              <span class="v16-auto-label">L · browser ID stability</span>
              <strong>L = 68 дней</strong>
              <small><b>Что это в жизни:</b> параметр скорости смены browser ID в Chromium-классе браузеров.</small>
              <small><b>Зачем:</b> в длинной кампании один и тот же браузер может получить новый ID; без этой поправки один пользователь может выглядеть как несколько технических пользователей.</small>
              <small><b>Почему 68:</b> это фиксированный baseline методологии v1.6 для Chromium. Он не рассчитывается по ЦА и не переносится автоматически на Safari, приложения или CTV.</small>
            </div>
          </div>
          <div class="field v16-ud-human" style="margin-top:10px">
            <label><strong>U_D · измеренный Universe web-устройств этой ЦА</strong></label>
            <input class="v16-line-ud" type="number" min="1" step="1" placeholder="Введите число устройств только если оно реально измерено">
            <div class="v16-ud-explain">
              <span><b>Что это в жизни:</b> количество уникальных web-устройств, относящихся к этой же ЦА, географии и периоду. Это устройства, не люди.</span>
              <span><b>Откуда брать:</b> только из реального измерения площадки / adtech / исследования, если такой device universe доступен.</span>
              <span><b>Какой порядок величины:</b> U_D не обязан равняться Human Universe и может быть выше или ниже него. Его нельзя получать простым умножением U × D — U × D является лишь модельной ёмкостью шага device → people, а не значением для ввода.</span>
              <span><b>Если U_D неизвестен:</b> оставьте поле пустым. Это нормальный сценарий: движок перейдёт на Quick-путь и не будет выдумывать device universe.</span>
            </div>
          </div>
          <div class="v16-human-flow v16-l2-order">
            <div><b>1</b><span><strong>Technical Reach</strong><small>технические ID площадки</small></span></div>
            <div><b>2</b><span><strong>L</strong><small>поправка на смену browser ID во времени</small></span></div>
            <div><b>3</b><span><strong>B + U_D</strong><small>browser ID → уникальные web-устройства</small></span></div>
            <div><b>4</b><span><strong>D</strong><small>устройства → уникальные люди</small></span></div>
            <div><b>5</b><span><strong>Human Reach</strong><small>охват реальных людей для дальнейшего расчёта</small></span></div>
          </div>
        </details>
        ${aon}
      `;
      wrap.appendChild(box);
    }
    wrap.querySelectorAll('input,select').forEach(el=>el.addEventListener('change',markDirty));
    renderPrecalc();
  }

  function renderInputAudit(){
    const wrap=$(ids.inputAudit);if(!wrap)return;
    const state=allUserState(),plans=state.plans;
    if(!plans.length){wrap.innerHTML='<div class="v16-human-summary err"><strong>Не выбрана ни одна Line.</strong><span>Отметьте хотя бы одну кампанию ниже.</span></div>';return}
    wrap.innerHTML='<div class="v16-audit-grid">'+plans.map(p=>{
      const x=p.meta.input_profile||{},rows=x.rows||0,reachRows=x.reach_scope_rows??rows,excluded=x.reach_excluded_rows||0,l1=x.l1_ready_rows||0;
      const mapping=collectFamilyMapping(p),mapped=Object.values(mapping.mapping).filter(Boolean).length,totalUnits=(p.meta.inventory_units||[]).length;
      const mappingReady=mapped===totalUnits&&mapping.confirmed,scope=collectLineScope(p);
      const sourceWarnings=(p.meta.import_warnings||[]).filter(w=>String(w.code||'').startsWith('SOURCE_'));
      const hardSourceError=sourceWarnings.some(w=>String(w.code||'').includes('INVALID'));
      const hardTa=!!p.meta.source_ta_mismatch;
      const uIssue=!!p.meta.source_universe_mismatch&&!scope.scopeConfirmed;
      const platformIssues=(p.meta.platform_scopes||[]).length;
      const blockers=(hardTa?1:0)+(mappingReady?0:1)+(hardSourceError?1:0);
      const reviews=(uIssue?1:0)+platformIssues;
      const stateKind=blockers?'err':reviews?'warn':'ok';
      const stateText=blockers?'До расчёта есть обязательные проверки':reviews?'Перед расчётом нужна проверка':'Основные входы готовы';

      const check=(kind,title,value,meaning,action='')=>`
        <div class="v16-human-check ${kind}">
          <div class="v16-human-check-head"><span>${title}</span><strong>${value}</strong></div>
          <p>${meaning}</p>
          ${action?`<small><b>Что делать:</b> ${action}</small>`:''}
        </div>`;

      return `<div class="v16-audit-card ${stateKind}">
        <div class="v16-audit-title">${badge(stateText,stateKind)}<strong>${esc(p.meta.label||p.id)}</strong></div>
        <div class="v16-human-checks">
          ${check(l1===reachRows?'ok':'warn','Данные для расчёта охвата',`${l1} из ${reachRows} строк готовы`,l1===reachRows?'Для каждой охватной строки есть готовый Technical Reach или пара Impressions + Frequency.':'Не для всех охватных строк хватает исходных данных.',l1===reachRows?'':'Проверьте строки ниже; нужны Technical Reach либо Impressions + Frequency.')}
          ${check(hardTa?'err':uIssue?'warn':'ok','Целевая аудитория и её размер',hardTa?'ЦА различаются':uIssue?'Размер ЦА различается':'Совпадают',hardTa?'Флайты относятся к разным целевым аудиториям — их Reach нельзя корректно объединить.':uIssue?'ЦА выглядит одинаковой, но её размер Universe отличается между флайтами.':'Критических противоречий по ЦА и Universe не найдено.',hardTa?'Пересчитайте входы на одну и ту же ЦА.':uIssue?'Проверьте актуальный Universe и подтвердите его ниже.':'')}
          ${check(mappingReady?'ok':'warn','Группировка площадок',mappingReady?'Проверена':`${mapped} из ${totalUnits} заполнено`,mappingReady?'Вы подтвердили, какие размещения могут относиться к одной пользовательской аудитории.':'Группировка нужна, чтобы один человек не считался несколько раз внутри связанных размещений.',mappingReady?'':'Проверьте карточки площадок ниже и подтвердите группировку.')}
          ${check(hardSourceError?'err':sourceWarnings.length?'warn':'ok','Качество исходного файла',sourceWarnings.length?`${sourceWarnings.length} замечаний`:'Ошибок не найдено',sourceWarnings.length?'В исходном медиаплане есть значения, которые требуют проверки. Движок не исправляет их молча.':'Автоматические проверки не нашли критических проблем. ',sourceWarnings.length?'Раскройте блок с ошибками исходного файла ниже.':'')}
          ${check(platformIssues?'warn':'ok','Площадки в нескольких периодах',platformIssues?`${platformIssues} требуют общего Reach`:'Проблем нет',platformIssues?'Одна площадка встречается в нескольких периодах. Их Reach нельзя просто сложить из-за повторных пользователей.':'Нет неоднозначного сложения Reach по периодам.',platformIssues?'Укажите общий Reach площадки за весь флайт или weekly Human Reach.':'')}
          ${check('neutral','Строки вне Reach',String(excluded),excluded?'Эти размещения остаются в медиаплане, но у них нет достаточных охватных данных, поэтому Reach для них не моделируется.':'Все охватные строки участвуют в расчёте.',excluded?'При необходимости раскройте список ниже.':'')}
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
      const total=adv+quick+blocked;
      const kind=blocked?'error':adv?'advanced':'fallback';
      const title=blocked?'Для части размещений не хватает данных':adv&&quick?'Используется смешанный путь расчёта':adv?'Используется детальный расчёт':'Используется базовый расчёт';
      const summary=blocked
        ? `${blocked} из ${total} размещений нельзя посчитать в принудительном Advanced-режиме без измеренных данных по устройствам.`
        : adv&&quick
          ? `${adv} размещений имеют данные для детального перевода в людей, а ${quick} считаются по стандартному Quick-пути.`
          : adv
            ? `Для всех ${adv} размещений хватает измеренных данных для детального перевода Technical Reach в людей.`
            : `Для ${quick} размещений нет измеренного device universe. Это нормально: движок использует стандартный Quick-путь и явно показывает это как модельное допущение.`;

      return `<div class="v16-decision ${kind}">
        <div class="v16-decision-head">
          <strong>${esc(p.meta.label||p.id)}</strong>
          ${badge(blocked?'Нужны данные':adv&&quick?'Смешанный путь':adv?'Детальный путь':'Базовый путь',blocked?'err':adv?'ok':'warn')}
        </div>
        <div class="v16-human-summary ${blocked?'err':adv?'ok':'warn'}"><strong>${title}</strong><span>${summary}</span></div>
        <div class="v16-human-flow">
          <div><b>1</b><span><strong>Берём Technical Reach</strong><small>Это технические уникальные идентификаторы из площадки/медиаплана.</small></span></div>
          <div><b>2</b><span><strong>${adv?'Объединяем browser ID и устройства':'Применяем стандартный коэффициент K'}</strong><small>${adv?'Там, где есть измеренные device inputs, используем B, D, L и U_D.':'При отсутствии измерений Quick-путь переводит технические ID в оценку людей без выдумывания device data.'}</small></span></div>
          <div><b>3</b><span><strong>Получаем Human Reach</strong><small>Именно этот охват в людях дальше используется для частот, каналов, флайтов и итогового Reach.</small></span></div>
        </div>
        <details class="v16-technical-details">
          <summary>Показать технические параметры этого шага</summary>
          <div class="v16-param-row">
            <span><b>B = ${num(rec.B,2)}</b><small>Browser ID на одно web-устройство. Используется на шаге browser → device.</small></span>
            <span><b>D = ${num(rec.D,2)}</b><small>Устройств на одного человека. Используется на шаге device → people.</small></span>
            <span><b>L = 68 дней</b><small>Параметр смены browser ID Chromium во времени.</small></span>
            <span><b>U_D</b><small>Измеренный Universe web-устройств; без него Advanced Web не запускается.</small></span>
            <span><b>Группы площадок</b><small>${map.confirmed?'Проверены пользователем':'Ещё не подтверждены'}</small></span>
          </div>
        </details>
      </div>`;
    }).join('')+'</div>';
  }

  function renderModelMap(){
    const wrap=$(ids.modelMap);if(!wrap)return;
    const c=modelCatalog();
    if(!c.level2){wrap.innerHTML='<div class="hint">Описание методики появится после загрузки медиаплана.</div>';return}
    const l2=c.level2||{},l3=c.level3||{},l5=c.level5||{},l6=c.level6||{},eng=c.engineering||{};
    const rho=l3.temporal_rho_profiles||{};
    const q=(l6.gap_curve||[]).map(x=>`${x.days} дней → ${pct(x.overlap,1)} пересечения`).join(' · ');

    const step=(level,title,real,action,result,tech)=>`
      <div class="v16-real-step">
        <div class="v16-real-step-head">
          <span class="v16-real-level">${esc(level)}</span>
          <strong>${esc(title)}</strong>
        </div>
        <div class="v16-real-step-grid">
          <div><b>Что это в реальности</b><span>${real}</span></div>
          <div><b>Что делает движок</b><span>${action}</span></div>
          <div><b>Что получаем</b><span>${result}</span></div>
        </div>
        <details class="v16-real-tech">
          <summary>Технические детали этого шага</summary>
          <div>${tech}</div>
        </details>
      </div>`;

    wrap.innerHTML=`
      <div class="v16-human-intro">
        <strong>Как читать этот блок</strong>
        <span>Движок идёт от одной строки медиаплана к итоговому охвату бренда. На каждом следующем шаге он объединяет аудитории и убирает повторных людей, чтобы один человек не посчитался несколько раз.</span>
        <small>Буквы ρ, λ, MaxEnt и другие математические параметры не нужны для обычной работы. Они оставлены только внутри «Технических деталей».</small>
      </div>
      <div class="v16-real-steps">
        ${step(
          'LEVEL 1',
          'Одно размещение в медиаплане',
          'Это одна конкретная строка размещения: например, VK Video / OLV / июнь. У строки есть показы, частота и/или Technical Reach.',
          'Проверяет, согласуются ли показы, частота и Reach. Если Technical Reach не указан, получает его как Impressions ÷ Frequency.',
          'Technical Reach этой строки — число технических уникальных идентификаторов, а не обязательно людей.',
          'Если одновременно заданы Impressions, Frequency и Reach, движок проверяет их арифметическую согласованность с учётом точности Frequency.'
        )}
        ${step(
          'LEVEL 2',
          'Технические ID превращаем в реальных людей',
          'Площадка может считать cookie, browser ID или device ID. Один человек может иметь несколько таких ID, поэтому Technical Reach может быть выше реального количества людей.',
          'Если есть измеренные данные по устройствам, движок учитывает смену browser ID во времени, несколько browser ID на устройстве и несколько устройств у человека. Если данных нет — использует стандартную модель K='+num(l2.quick_k,2)+'.',
          'Human Reach площадки — оценка уникальных людей, которых реально достигло размещение.',
          'Quick: R_people = R_tech / K. Advanced Web: L → B + U_D → D. App/CTV не получают браузерную поправку автоматически.'
        )}
        ${step(
          'LEVEL 3A',
          'Объединяем одну площадку во времени внутри одного флайта',
          'Например, VK Video шёл в июне и июле. Это не две независимые аудитории: часть людей могла увидеть рекламу в обоих месяцах.',
          'Объединяет периоды одной площадки и учитывает повторных людей между неделями/периодами. Если есть weekly Human Reach — использует его. Если есть только общий Reach площадки за весь флайт — берёт его один раз.',
          'Один Human Reach площадки за весь флайт, без простого сложения месячных Reach.',
          'Временная зависимость задаётся профилем ρ: LOW '+num(rho.LOW,2)+', BASE '+num(rho.BASE,2)+', HIGH '+num(rho.HIGH,2)+'. Чем больше разрыв между периодами, тем меньше ожидаемое пересечение.'
        )}
        ${step(
          'LEVEL 3B',
          'Понимаем, сколько людей получили 1, 2, 3 и больше контактов',
          'Средняя частота сама по себе не говорит, сколько людей увидели рекламу хотя бы 3 раза. Два плана с одинаковой средней частотой могут иметь разное распределение контактов.',
          'Строит распределение контактов среди охваченных людей и из него получает Reach 1+, 2+, 3+, 4+, 5+, 6+.',
          'Охват каждой частоты одновременно в людях и в % целевой аудитории.',
          'Модель частоты: Poisson-Lognormal, σ='+num(l3.sigma_default,2)+' по умолчанию. Средняя Human Frequency = Impressions / Human Reach 1+.'
        )}
        ${step(
          'LEVEL 4',
          'Объединяем площадки внутри одного канала',
          'Например, внутри OLV могут одновременно использоваться VK Video, Rutube и другие площадки. Один человек может быть охвачен сразу несколькими из них.',
          'Сначала учитывает группы связанных аудиторий, затем дедуплицирует площадки внутри канала. Измеренные пересечения имеют приоритет; если их нет, используется нейтральная модель.',
          'Уникальный Reach канала — без повторного счёта людей между площадками.',
          'Для 2 сущностей расчёт аналитический. Для 3+ связанных сущностей сначала проверяется глобальная математическая совместимость, затем при необходимости используется Maximum Entropy.'
        )}
        ${step(
          'LEVEL 5',
          'Объединяем каналы внутри одного флайта',
          'Например, один и тот же человек мог попасть и в OLV, и в баннеры, и в соцсети в рамках одного флайта.',
          'Оценивает пересечение аудиторий каналов и убирает дубли. Поэтому общий Reach флайта меньше простой суммы Reach каналов.',
          'Уникальный Reach всего флайта и вклад каждого канала в этот Reach.',
          'Model-default зависимость каналов: ρ target='+num(l5.rho_channel_target,2)+'. Если модельные зависимости для 3+ каналов несовместимы, ослабляется только model-default часть; измеренные/custom inputs не меняются.'
        )}
        ${step(
          'LEVEL 6',
          'Объединяем несколько флайтов одной Line',
          'Например, кампания шла весной, летом и осенью. Некоторые люди увидят рекламу повторно в разных флайтах, но доля повторов зависит от временного разрыва.',
          'Учитывает временное пересечение между флайтами и остаточную повторяемость аудитории. Чем дальше флайты друг от друга, тем меньше ожидаемый overlap.',
          'Уникальный Reach всей Line за весь период.',
          q+'. Остаточная модельная дедупликация ограничена '+pct(l6.residual_cap??.10,0)+' от меньшего Reach пары. Always-on ↔ burst требует реального Reach-среза за burst-период.'
        )}
        ${step(
          'LEVEL 7',
          'Объединяем несколько Lines в общий Reach бренда',
          'Например, бренд одновременно продвигает несколько продуктовых линий. Один человек может попасть в охват нескольких Lines.',
          'Объединяет Lines только если они пересчитаны на одну и ту же целевую аудиторию, географию, период и одинаковое определение уникального человека.',
          'Brand Total Reach — сколько уникальных людей охвачено брендом суммарно по всем выбранным Lines.',
          'Нужен подтверждённый Brand Master Universe и единый Brand Master scope. Если Lines доступны разным подгруппам аудитории, BrandAddressabilityMap задаёт реальные ограничения доступности.'
        )}
      </div>
      <details class="v16-solver-tech">
        <summary>Технические ограничения математического решателя</summary>
        <div class="v16-note">До ${eng.max_entities||12} сущностей в joint-state. Feasibility tolerance ${eng.feasibility_tolerance||'1e-9'}, solver tolerance ${eng.solver_constraint_tolerance||'1e-8'}, максимум ${eng.max_iterations||10000} итераций. Этот блок нужен для аудита, а не для ежедневной работы.</div>
      </details>`;
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
    const top=topResult(),u=topUniverse(),tf=targetFrequency(),wrap=$(ids.metrics);
    if(!top){
      wrap.innerHTML=`<div class="v16-result-state warn"><strong>Brand Total пока не рассчитан.</strong><span>${esc(v16Data?.brand_error||'Проверьте входы Level 7. Если выбрана одна Line, её результат доступен в иерархии ниже.')}</span></div>`;
      return;
    }
    const warnings=(v16Data?.business_diagnostics||[]).filter(x=>x.severity==='WARNING').length;
    const errors=(v16Data?.business_diagnostics||[]).filter(x=>x.severity==='ERROR').length;
    const stateKind=errors?'err':warnings?'warn':'ok';
    const stateTitle=errors?'Расчёт выполнен частично':warnings?'Расчёт выполнен, есть предупреждения':'Расчёт пригоден для планирования';
    const reachCards=[1,2,3,4,5,6].map(k=>{
      const val=Number(reachAt(top,k)),share=u&&Number.isFinite(val)?val/u:null;
      return `<div class="v16-reach-kpi ${k===tf?'selected':''}">
        <span>Reach ${k}+</span>
        <strong>${share!=null?pct(share,2):'—'}</strong>
        <b>${Number.isFinite(val)?num(val,0)+' человек':'—'}</b>
        ${k===tf?'<small>выбранная KPI-частота</small>':''}
      </div>`;
    }).join('');
    const avg=top.avg_frequency!=null?num(top.avg_frequency,2):'—';
    wrap.innerHTML=`
      <div class="v16-result-state ${stateKind}">
        <div><strong>${stateTitle}</strong><span>${errors?errors+' ошибок':warnings?warnings+' предупреждений':'Критических ошибок нет'}</span></div>
        <small>Все Reach N+ ниже показываются одновременно в % целевой аудитории и в людях.</small>
      </div>
      <div class="v16-reach-kpi-grid">${reachCards}</div>
      <div class="v16-summary-grid">
        <div><span>Universe результата</span><strong>${u?num(u,0):'—'}</strong></div>
        <div><span>Impressions</span><strong>${top.impressions!=null?num(top.impressions,0):'—'}</strong></div>
        <div><span>Среднее число контактов</span><strong>${avg}</strong><small>на одного охваченного человека · I / Reach 1+</small></div>
        <div><span>Gross Reach Sum</span><strong>${top.gross_reach_sum!=null?num(top.gross_reach_sum,0):'—'}</strong><small>сумма охватов до текущей дедупликации</small></div>
        <div><span>Повторная аудитория</span><strong>${top.dedup_people!=null?num(top.dedup_people,0):'—'}</strong><small>${top.dedup_rate!=null?pct(top.dedup_rate,2):'—'} от gross reach</small></div>
        <div><span>Модель объединения</span><strong class="v16-model-path">${esc(top.model_path||'—')}</strong></div>
      </div>`;
  }

  function renderFrequencyProfile(){
    const top=topResult(),u=topUniverse(),wrap=$(ids.profile);
    if(!top||!u){wrap.innerHTML='<div class="hint">Нет единого Brand/Line total. Частотная кривая остаётся доступна по строкам иерархии.</div>';return}
    const tf=targetFrequency();
    wrap.innerHTML='<div class="v16-profile-grid">'+[1,2,3,4,5,6].map(k=>{
      const val=Number(reachAt(top,k)||0),share=Math.max(0,Math.min(1,val/u));
      return `<div class="v16-profile-row ${k===tf?'selected':''}">
        <div class="v16-profile-label">Reach ${k}+</div>
        <div class="v16-profile-track" aria-label="Reach ${k}+ ${pct(share,2)}"><span style="width:${(share*100).toFixed(3)}%"></span></div>
        <div class="v16-profile-value"><strong>${pct(share,2)}</strong><span>${num(val,0)} человек</span></div>
      </div>`;
    }).join('')+'</div>';
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
        <small>${reached?pct(people/reached,2):'—'} среди людей с Reach 1+</small>
      </div>`;
    }).join('')+'</div>';
  }

  function reachCell(r,k){
    const u=Number(r.universe),val=Number(r[`reach_${k}p`]);
    if(!Number.isFinite(val))return '<span class="na">—</span>';
    return `<strong>${u>0?pct(val/u,2):'—'}</strong><span class="v16-pct">${num(val,0)} человек</span>`;
  }

  function rowClass(level){return level==='Brand'?'v16-level-brand':level==='Line'?'v16-level-line':level==='Flight'?'v16-level-flight':'v16-level-channel'}
  function indentLabel(r){return r.level==='Brand'?'BRAND · '+r.name:r.level==='Line'?'LINE · '+r.name:r.level==='Flight'?'↳ FLIGHT · '+r.name:'↳↳ CHANNEL · '+r.name}
  function renderTable(){
    const rows=v16Data?.hierarchy||[];
    let h='<thead><tr><th>Уровень</th><th>Line</th><th>Flight</th><th class="num">Universe</th><th class="num">Impressions</th>'+
      [1,2,3,4,5,6].map(k=>`<th class="num">Reach ${k}+<span class="v16-th-sub">% U · люди</span></th>`).join('')+
      '<th class="num">Среднее число контактов</th><th class="num">Gross Reach</th><th class="num">Дедупликация</th><th>Путь модели</th></tr></thead><tbody>';
    for(const r of rows){
      h+=`<tr class="${rowClass(r.level)}">
        <td data-label="Уровень"><strong>${esc(indentLabel(r))}</strong></td>
        <td data-label="Line">${esc(r.line||'')}</td>
        <td data-label="Flight">${esc(r.flight||'')}</td>
        <td data-label="Universe" class="num">${num(r.universe,0)}</td>
        <td data-label="Impressions" class="num">${num(r.impressions,0)}</td>`;
      for(let k=1;k<=6;k++)h+=`<td data-label="Reach ${k}+" class="num v16-reach-cell">${reachCell(r,k)}</td>`;
      h+=`<td data-label="Среднее число контактов" class="num">${num(r.avg_frequency,2)}<span class="v16-pct">на Reach 1+ человека</span></td>
        <td data-label="Gross Reach" class="num">${r.gross_reach_sum!=null?num(r.gross_reach_sum,0):'—'}</td>
        <td data-label="Дедупликация" class="num">${r.dedup_people!=null?num(r.dedup_people,0):'—'}${r.dedup_rate!=null?'<span class="v16-pct">'+pct(r.dedup_rate,2)+'</span>':''}</td>
        <td data-label="Путь модели">${esc(r.model_path||'—')}</td></tr>`;
    }
    $(ids.table).innerHTML=h+'</tbody>';
  }

  function renderContributions(){
    const all=v16Data?.contribution_rows||[],table=$(ids.contrib);
    const rows=all.filter(r=>{
      const parent=Number(r.parent_reach||0),sh=Number(r.shapley_people||0),ex=Number(r.exclusive_people||0);
      return parent>0 && !(Math.abs(sh-parent)<1e-6 && Math.abs(ex-parent)<1e-6);
    });
    if(!rows.length){
      table.innerHTML='<tbody><tr><td class="hint">Здесь нечего сравнивать: на рассматриваемом уровне только одна сущность, поэтому её вклад равен всему Reach.</td></tr></tbody>';
      return;
    }
    let h='<thead><tr><th>Канал / сущность</th><th>Родительский уровень</th><th class="num">Вклад в итоговый Reach</th><th class="num">Эксклюзивная аудитория</th><th class="num">Учтённая часть пересечений</th></tr></thead><tbody>';
    for(const r of rows){
      const parent=Number(r.parent_reach||0),sh=Number(r.shapley_people||0),ex=Number(r.exclusive_people||0),shared=Math.max(0,sh-ex);
      h+=`<tr>
        <td data-label="Канал / сущность"><strong>${esc(r.name||'')}</strong><span class="v16-th-sub">${esc(r.scope||'')}</span></td>
        <td data-label="Родитель">${esc(r.parent||'')}</td>
        <td data-label="Вклад в Reach" class="num"><strong>${num(sh,0)} человек</strong><span class="v16-pct">${parent?pct(sh/parent,2):'—'} итогового Reach</span></td>
        <td data-label="Эксклюзивная аудитория" class="num"><strong>${num(ex,0)} человек</strong><span class="v16-pct">${parent?pct(ex/parent,2):'—'} итогового Reach</span></td>
        <td data-label="Учтённые пересечения" class="num"><strong>${num(shared,0)} человек</strong><span class="v16-pct">${parent?pct(shared/parent,2):'—'} итогового Reach</span></td>
      </tr>`;
    }
    table.innerHTML=h+'</tbody>';
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
        <div class="v16-business-message">${esc(d.message||'')}</div>
        <div class="v16-business-help"><div><b>${esc(e[0])}</b><span>${esc(e[1])}</span></div><div><b>${esc(e[2])}</b><span>${esc(e[3])}</span></div></div>
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
      const suffix=v16Data.status==='GO'?'Brand Total рассчитан':'Результаты Lines рассчитаны; Brand Total требует проверки Level 7';
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
      $(ids.controls).classList.remove('hidden');
      setStatus(ids.status,`Файл распознан: ${v16Meta.plans.length} Line. Проверьте отмеченные входы и группировку площадок.`,'ok');
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