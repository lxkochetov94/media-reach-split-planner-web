(() => {
  let v16File=null, v16Path=null, v16Meta=null, v16Data=null, v16Catalog=null, v16ModuleReady=false;

  const ids={
    dz:'v16Dropzone',fi:'v16FileInput',file:'v16FileName',status:'v16Status',
    controls:'v16Controls',plans:'v16PlanWrap',inputAudit:'v16InputAudit',
    l2Decision:'v16L2Decision',modelMap:'v16ModelMap',mode:'v16L2Mode',k:'v16K',
    L:'v16L',B:'v16B',D:'v16D',brandU:'v16BrandUniverse',autoU:'v16BrandUniverseAuto',
    targetF:'v16TargetFrequency',calc:'v16Calc',results:'v16Results',metrics:'v16Metrics',
    warning:'v16Warning',profile:'v16FrequencyProfile',exact:'v16ExactFrequency',
    contrib:'v16ContributionTable',table:'v16Table',diag:'v16Diagnostics'
  };

  async function ensureV16Module(){
    await corePromise;
    if(!coreReady)throw new Error('Базовый парсер не готов');
    if(v16ModuleReady)return;
    const resp=await fetch('reach_v16.py?v=1.6.3');
    if(!resp.ok)throw new Error('Не удалось загрузить Reach Engine v1.6');
    const txt=await resp.text();
    pyodide.FS.writeFile('/app/reach_v16.py',txt,{encoding:'utf8'});
    pyodide.runPython("import importlib, reach_v16; importlib.reload(reach_v16)");
    v16ModuleReady=true;
  }

  async function v16Call(expr,globals={}){
    await ensureV16Module();
    for(const[k,v]of Object.entries(globals))pyodide.globals.set(k,v);
    const raw=pyodide.runPython(expr);
    return typeof raw==='string'?JSON.parse(raw):raw;
  }

  function errText(error){
    const raw=String(error?.message||error||'Неизвестная ошибка');
    const lines=raw.split(/\r?\n/).map(x=>x.trim()).filter(Boolean);
    const last=lines.at(-1)||raw;
    return last.replace(/^(?:reach_v16\.)?(?:V16Error|ValueError|TypeError|RuntimeError):\s*/,'').slice(0,520);
  }

  function nval(id){
    const raw=$(id)?.value?.trim?.()??'';
    return raw===''?null:Number(raw);
  }

  function selectedPlans(){
    if(!v16Meta?.plans)return[];
    return v16Meta.plans.flatMap(p=>{
      const cb=document.querySelector(`.v16-plan-cb[data-plan-id="${CSS.escape(p.id)}"]`);
      if(!cb?.checked)return[];
      const u=document.querySelector(`.v16-universe[data-plan-id="${CSS.escape(p.id)}"]`);
      const ud=document.querySelector(`.v16-ud[data-plan-id="${CSS.escape(p.id)}"]`);
      return[{
        id:p.id,meta:p,
        universe:Number(u?.value||p.universe||0),
        webDeviceUniverse:ud?.value?.trim()?Number(ud.value):null
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

  function currentOverrides(){
    return{
      mode:$(ids.mode)?.value||'AUTO',
      K:Number($(ids.k)?.value||2.4),
      L:Number($(ids.L)?.value||68),
      B:nval(ids.B),
      D:nval(ids.D)
    };
  }

  function coverageBadge(label,n,total){
    const ok=total>0&&n===total;
    return`<span class="v16-badge ${ok?'ok':n?'partial':'miss'}">${esc(label)} · ${num(n,0)}/${num(total,0)}</span>`;
  }

  function renderPlanControls(){
    const wrap=$(ids.plans);wrap.innerHTML='';
    for(const p of(v16Meta?.plans||[])){
      const pr=p.input_profile||{},rec=p.advanced_recommended||{};
      const box=document.createElement('div');box.className='v16-plan';
      box.innerHTML=`
        <div class="v16-plan-top">
          <label class="v16-plan-title">
            <input type="checkbox" class="v16-plan-cb" data-plan-id="${esc(p.id)}" checked>
            <span><strong>${esc(p.label||p.line||p.campaign||p.id)}</strong><span class="hint">${esc((p.sheet_names||[]).join(', '))}</span></span>
          </label>
          <div class="field"><label>Universe Line</label><input class="v16-universe" data-plan-id="${esc(p.id)}" type="number" min="1" step="1" value="${p.universe?Math.round(p.universe):''}" placeholder="Введите Universe"></div>
          <div class="field"><label>ЦА</label><input type="text" value="${esc(p.ta_name||'Не распознана')}" disabled></div>
        </div>
        <div class="v16-plan-readout">
          <div><span class="label">Авто-параметры по ЦА</span><strong>B=${num(rec.B,2)} · D=${num(rec.D,2)}</strong><span class="v16-note">${esc(rec.B_source||'')} / ${esc(rec.D_source||'')}</span></div>
          <div><span class="label">Структура</span><strong>${num(p.flight_count||0,0)} флайт(а) · ${num(p.placement_count||0,0)} размещений</strong><span class="v16-note">${num(pr.platforms||0,0)} площадок · ${num(pr.channels||0,0)} каналов</span></div>
          <div><span class="label">Периоды</span><strong>${pr.duration_days_median!=null?'медиана '+num(pr.duration_days_median,0)+' дн.':'нет дат'}</strong><span class="v16-note">${pr.duration_days_min!=null?num(pr.duration_days_min,0)+'–'+num(pr.duration_days_max,0)+' дн.':''}</span></div>
        </div>
        <div class="v16-badges">
          ${coverageBadge('Reach',pr.supplied_reach_rows||0,pr.rows||0)}
          ${coverageBadge('Показы',pr.impressions_rows||0,pr.rows||0)}
          ${coverageBadge('Частота',pr.frequency_rows||0,pr.rows||0)}
          ${coverageBadge('Даты',pr.dated_rows||0,pr.rows||0)}
        </div>
        <details class="v16-line-extra">
          <summary>Дополнительный измеряемый input для Advanced Web</summary>
          <div class="field v16-ud-field"><label>Universe web-устройств U<sub>D</sub></label><input class="v16-ud" data-plan-id="${esc(p.id)}" type="number" min="1" step="1" placeholder="Оставьте пустым, если нет измерения"><div class="hint">Не модельный коэффициент. Заполняется только если есть реальный измеряемый web-device universe; иначе AUTO честно использует Quick для web-части.</div></div>
        </details>`;
      wrap.appendChild(box);
    }
    document.querySelectorAll('.v16-plan-cb,.v16-universe,.v16-ud').forEach(el=>el.addEventListener('change',()=>{
      syncBrandUniverse();
      renderInputAudit();renderL2Decision();renderModelMap();
      if(v16Data)calculateV16();
    }));
    syncBrandUniverse(true);
  }

  function renderInputAudit(){
    const wrap=$(ids.inputAudit), plans=selectedPlans();
    if(!plans.length){wrap.innerHTML='<div class="warning">Не выбрана ни одна Line.</div>';return}
    const total=plans.reduce((a,x)=>a+(x.meta.input_profile?.rows||0),0);
    const sum=k=>plans.reduce((a,x)=>a+(x.meta.input_profile?.[k]||0),0);
    const cards=[
      ['Technical Reach',sum('supplied_reach_rows'),total,'supplied Reach имеет приоритет после consistency check'],
      ['Показы',sum('impressions_rows'),total,'используются для частотной модели и проверок'],
      ['Средняя частота',sum('frequency_rows'),total,'F≥1; при I+Reach+F проверяется арифметика'],
      ['Даты',sum('dated_rows'),total,'нужны для churn и temporal logic']
    ];
    wrap.innerHTML='<div class="v16-audit-grid">'+cards.map(([a,b,t,c])=>`<div class="v16-audit-card"><span class="label">${esc(a)}</span><strong>${num(b,0)} / ${num(t,0)}</strong><div class="v16-progress"><span style="width:${t?Math.min(100,b/t*100):0}%"></span></div><div class="v16-note">${esc(c)}</div></div>`).join('')+'</div>';
  }

  function sourceRu(s){
    return({
      AGE_WIDTH_APPROXIMATION:'по возрастной структуре ЦА',
      BASE_FALLBACK:'базовое модельное значение',
      USER_OVERRIDE:'ручной override'
    })[s]||s||'—';
  }

  function renderL2Decision(){
    const wrap=$(ids.l2Decision),plans=selectedPlans(),ov=currentOverrides();
    if(!plans.length){wrap.innerHTML='';return}
    const blocks=[];
    for(const x of plans){
      const rec=x.meta.advanced_recommended||{},pr=x.meta.input_profile||{};
      const autoAdvanced=!!x.webDeviceUniverse;
      const forced=ov.mode;
      let path,reason;
      if(forced==='QUICK'){path='QUICK';reason='пользователь принудительно выбрал быстрый режим';}
      else if(forced==='ADVANCED_WEB'){path=x.webDeviceUniverse?'ADVANCED WEB':'НЕДОСТАТОЧНО INPUT';reason=x.webDeviceUniverse?'U_D задан, запускается 2A → 2B → 2C':'для принудительного Advanced Web нужен измеряемый U_D';}
      else{path=autoAdvanced?'ADVANCED WEB':'QUICK fallback';reason=autoAdvanced?'есть U_D: можно использовать полную web-цепочку':'U_D отсутствует: коэффициенты B/D рассчитаны, но browser saturation нельзя считать без device-universe';}
      const B=ov.B??rec.B,D=ov.D??rec.D;
      const duration=pr.duration_days_median;
      const churn=duration?1-Math.pow(2,-duration/ov.L):null;
      blocks.push(`<div class="v16-decision-card">
        <div class="v16-decision-title"><div><span class="label">${esc(x.meta.label||x.id)}</span><strong>${esc(path)}</strong></div><span class="v16-pill ${path.includes('НЕДО')?'bad':path.includes('ADVANCED')?'good':'neutral'}">${esc(reason)}</span></div>
        <div class="v16-pipeline">
          <div class="v16-pipe-step"><span>1</span><div><b>Technical Reach</b><small>из медиаплана · ${num(pr.supplied_reach_rows||0,0)}/${num(pr.rows||0,0)} строк</small></div></div>
          <div class="v16-pipe-arrow">→</div>
          <div class="v16-pipe-step"><span>2A</span><div><b>ID churn</b><small>L=${num(ov.L,0)} дн.${churn!=null?' · Pchurn≈'+pct(churn,1):''}</small></div></div>
          <div class="v16-pipe-arrow">→</div>
          <div class="v16-pipe-step"><span>2B</span><div><b>Browser saturation</b><small>B=${num(B,2)} · ${esc(ov.B!=null?'ручной override':sourceRu(rec.B_source))}</small></div></div>
          <div class="v16-pipe-arrow">→</div>
          <div class="v16-pipe-step"><span>2C</span><div><b>Device saturation</b><small>D=${num(D,2)} · ${esc(ov.D!=null?'ручной override':sourceRu(rec.D_source))}</small></div></div>
          <div class="v16-pipe-arrow">→</div>
          <div class="v16-pipe-step final"><span>✓</span><div><b>Estimated People</b><small>0 ≤ Rpeople ≤ U</small></div></div>
        </div>
        <div class="v16-decision-foot">
          <span><b>U:</b> ${num(x.universe,0)}</span>
          <span><b>U<sub>D</sub>:</b> ${x.webDeviceUniverse?num(x.webDeviceUniverse,0):'нет измерения'}</span>
          <span><b>Quick K:</b> ${num(ov.K,2)} · только fallback</span>
        </div>
      </div>`);
    }
    wrap.innerHTML=blocks.join('');
  }

  function interpMU(U){
    const pts=v16Catalog?.level6?.universe_multiplier_points||[];
    if(!pts.length||!Number.isFinite(U))return null;
    if(U<=pts[0].universe)return pts[0].multiplier;
    if(U>=pts.at(-1).universe)return pts.at(-1).multiplier;
    for(let i=0;i<pts.length-1;i++){
      const a=pts[i],b=pts[i+1];
      if(U>=a.universe&&U<=b.universe){
        const t=(U-a.universe)/(b.universe-a.universe);
        return a.multiplier+t*(b.multiplier-a.multiplier);
      }
    }
    return null;
  }

  function chips(items,formatter){
    return'<div class="v16-chip-row">'+items.map(x=>`<span class="v16-chip">${formatter(x)}</span>`).join('')+'</div>';
  }

  function renderModelMap(){
    const wrap=$(ids.modelMap);if(!wrap||!v16Catalog)return;
    const plans=selectedPlans(),ov=currentOverrides(),cat=v16Catalog;
    const mainU=Number($(ids.brandU)?.value||plans[0]?.universe||0);
    const Bvals=plans.map(x=>ov.B??x.meta.advanced_recommended?.B).filter(Number.isFinite);
    const Dvals=plans.map(x=>ov.D??x.meta.advanced_recommended?.D).filter(Number.isFinite);
    const bNow=[...new Set(Bvals.map(x=>num(x,2)))].join(' / ')||'—';
    const dNow=[...new Set(Dvals.map(x=>num(x,2)))].join(' / ')||'—';
    const l5Eff=[];
    for(const line of(v16Data?.lines||[]))for(const f of(line.flights||[]))if(f.rho_effective!=null)l5Eff.push(f.rho_effective);
    const l6Lambda=[];
    for(const line of(v16Data?.lines||[]))if(line.flight_relaxation_lambda!=null)l6Lambda.push(line.flight_relaxation_lambda);
    const mu=interpMU(mainU);
    const cards=[
      {
        lvl:'L2',title:'Technical IDs → People',
        value:`B=${bNow} · D=${dNow} · L=${num(ov.L,0)}д`,
        body:
          '<div class="v16-rule-label">B по возрасту</div>'+chips(cat.level2.browser_by_age,x=>`${x.segment}: ${num(x.value,2)}`)+
          '<div class="v16-rule-label">D по возрасту</div>'+chips(cat.level2.device_by_age,x=>`${x.segment}: ${num(x.value,2)}`)+
          '<div class="v16-rule-label">Churn reference при L=68</div>'+chips(cat.level2.churn_reference,x=>`${x.days}д: ${pct(x.probability,1)}`)
      },
      {
        lvl:'L3A',title:'Weeks → Platform Flight',
        value:'ρ BASE 0,65 · LOW 0,50 · HIGH 0,80',
        body:'<div class="v16-note">Для соседних недель используется temporal dependence; при отсутствии weekly Reach применяется aggregate-flight path без искусственного разложения по неделям.</div>'
      },
      {
        lvl:'L3B',title:'Effective Reach',
        value:`Poisson-Lognormal · σ=${num(cat.level3.sigma_default,2)}`,
        body:`<div class="v16-note">Калибровочный центральный диапазон fitted σ: ${num(cat.level3.sigma_calibration_iqr[0],2)}–${num(cat.level3.sigma_calibration_iqr[1],2)}. Exact buckets 1/2/3/4/5/6+.</div>`
      },
      {
        lvl:'L5',title:'Channels → Flight',
        value:`ρ target ${num(cat.level5.rho_channel_target,2)}${l5Eff.length?' · effective '+[...new Set(l5Eff.map(x=>num(x,3)))].join(' / '):''}`,
        body:'<div class="v16-note">Для 3+ каналов общий λ ослабляет только MODEL_DEFAULT к 0 и только настолько, насколько требует глобальная совместимость.</div>'
      },
      {
        lvl:'L6',title:'Flights → Line',
        value:`M_U≈${mu!=null?num(mu,2):'—'} · residual ≤${pct(cat.level6.residual_cap,0)}`,
        body:'<div class="v16-rule-label">q_temporal по gap</div>'+chips(cat.level6.gap_curve,x=>`${x.days}д: ${pct(x.overlap,1)}`)+
          `<div class="v16-note">${l6Lambda.length?'Фактический λ: '+[...new Set(l6Lambda.map(x=>num(x,3)))].join(' / '):'λ применяется только если target pair overlaps глобально несовместимы.'}</div>`
      },
      {
        lvl:'L7',title:'Lines → Brand',
        value:'ρ line = 0 · Brand master TA required',
        body:'<div class="v16-note">Level 6 q(G)/M_U сюда не переносится. При разных TA Lines должны быть пересчитаны upstream на главную широкую Brand TA.</div>'
      }
    ];
    wrap.innerHTML=cards.map(c=>`<div class="v16-model-card"><div class="v16-model-head"><span>${c.lvl}</span><div><strong>${esc(c.title)}</strong><div class="v16-model-value">${esc(c.value)}</div></div></div><div class="v16-model-body">${c.body}</div></div>`).join('');
  }

  function targetFrequency(){return Math.max(1,Math.min(6,Number($(ids.targetF)?.value||3)))}
  function reachAt(obj,k){return obj?.[`reach_${k}p`]}
  function topResult(){
    const b=v16Data?.brand_total,lines=v16Data?.lines||[];
    return b||(lines.length===1?lines[0]:null);
  }
  function topUniverse(){
    const top=topResult();
    return top?.universe||(v16Data?.lines?.length===1?v16Data.lines[0].universe:null);
  }

  function effectiveL2Label(){
    const modes=[...new Set((v16Data?.lines||[]).map(x=>x?.l2?.effective_mode).filter(Boolean))];
    if(!modes.length)return'—';
    return modes.map(m=>m==='ADVANCED_WEB'?'Advanced Web':m==='QUICK'?'Quick fallback':m).join(' + ');
  }

  function renderMetrics(){
    const top=topResult(),u=topUniverse(),tf=targetFrequency(),r1=reachAt(top,1),rt=reachAt(top,tf);
    const cards=[
      ['Статус',v16Data?.status||'—',''],
      ['Level 2',effectiveL2Label(),'фактически применённый path'],
      ['Universe',u?num(u,0):'—',''],
      ['Показы',top?.impressions!=null?num(top.impressions,0):'—',''],
      ['Reach @1+ · люди',r1!=null?num(r1,0):'—',''],
      ['Reach @1+ · %',u&&r1!=null?pct(r1/u,2):'—',''],
      [`Reach @${tf}+ · люди`,rt!=null?num(rt,0):'—','выбранная эффективная частота'],
      [`Reach @${tf}+ · %`,u&&rt!=null?pct(rt/u,2):'—','выбранная эффективная частота'],
      ['Средняя Human Frequency',top?.avg_frequency!=null?num(top.avg_frequency,2):'—',''],
      ['Дедупликация',top?.dedup_rate!=null?pct(top.dedup_rate,2):'—',top?.dedup_people!=null?num(top.dedup_people,0)+' duplicate Reach':'']
    ];
    $(ids.metrics).innerHTML=cards.map(([a,b,c])=>`<div class="metric"><div class="label">${esc(a)}</div><div class="value">${esc(b)}</div>${c?`<div class="v16-note">${esc(c)}</div>`:''}</div>`).join('');
  }

  function renderFrequencyProfile(){
    const top=topResult(),u=topUniverse(),wrap=$(ids.profile);
    if(!top||!u){wrap.innerHTML='<div class="hint">Нет итогового результата.</div>';return}
    const tf=targetFrequency();
    wrap.innerHTML='<div class="v16-profile-grid">'+[1,2,3,4,5,6].map(k=>{
      const val=Number(reachAt(top,k)||0),share=Math.max(0,Math.min(1,val/u));
      return`<div class="v16-profile-row ${k===tf?'selected':''}">
        <div class="v16-profile-label">@${k}+</div>
        <div class="v16-profile-track"><span style="width:${(share*100).toFixed(3)}%"></span></div>
        <div class="v16-profile-value"><strong>${num(val,0)}</strong><span>${pct(share,2)}</span></div>
      </div>`;
    }).join('')+'</div>';
  }

  function renderExactFrequency(){
    const top=topResult(),u=topUniverse(),wrap=$(ids.exact);
    if(!top||!u||!Array.isArray(top.exact_counts)){wrap.innerHTML='<div class="hint">Exact frequency buckets недоступны.</div>';return}
    const r1=Number(top.reach_1p||0);
    let h='<div class="v16-exact-grid">';
    top.exact_counts.forEach((v,i)=>{
      const k=i===5?'6+':String(i+1),count=Number(v||0),pu=u?count/u:0,pr=r1?count/r1:0;
      h+=`<div class="v16-exact-card"><span class="label">Ровно ${k}</span><strong>${num(count,0)}</strong><div class="v16-exact-split"><span>${pct(pu,2)} Universe</span><span>${pct(pr,2)} достигнутых</span></div></div>`;
    });
    h+='</div>';
    wrap.innerHTML=h;
  }

  function renderContributions(){
    const rows=v16Data?.contribution_rows||[],table=$(ids.contrib);
    if(!rows.length){table.innerHTML='<tbody><tr><td class="hint">Нет merge с несколькими сущностями — вклад не рассчитывается.</td></tr></tbody>';return}
    let h='<thead><tr><th>Уровень merge</th><th>Родитель</th><th>Сущность</th><th class="num">Shapley, люди</th><th class="num">% итогового Reach</th><th class="num">Exclusive, люди</th></tr></thead><tbody>';
    for(const r of rows){
      const parent=Number(r.parent_reach||0),sh=Number(r.shapley_people||0),ex=Number(r.exclusive_people||0);
      h+=`<tr><td>${esc(r.scope)}</td><td>${esc(r.parent||'')}</td><td><strong>${esc(r.name||'')}</strong></td><td class="num">${num(sh,0)}</td><td class="num">${parent?pct(sh/parent,2):'—'}</td><td class="num">${num(ex,0)}</td></tr>`;
    }
    h+='</tbody>';table.innerHTML=h;
  }

  function reachCell(r,k){
    const u=Number(r.universe),val=Number(r[`reach_${k}p`]);
    if(!Number.isFinite(val))return'—';
    return`<strong>${num(val,0)}</strong><span class="v16-pct">${u>0?pct(val/u,2):'—'}</span>`;
  }
  function rowClass(level){
    return level==='Brand'?'v16-level-brand':level==='Line'?'v16-level-line':level==='Flight'?'v16-level-flight':'v16-level-channel';
  }
  function label(r){
    return r.level==='Brand'?'BRAND · '+r.name:r.level==='Line'?'LINE · '+r.name:r.level==='Flight'?'↳ FLIGHT · '+r.name:'↳↳ CHANNEL · '+r.name;
  }
  function renderTable(){
    const rows=v16Data?.hierarchy||[];
    let h='<thead><tr><th>Уровень</th><th>Line</th><th>Flight</th><th class="num">Universe</th><th class="num">Показы</th>'+
      [1,2,3,4,5,6].map(k=>`<th class="num">Reach @${k}+<span class="v16-th-sub">люди · % U</span></th>`).join('')+
      '<th class="num">Avg F</th></tr></thead><tbody>';
    for(const r of rows){
      h+=`<tr class="${rowClass(r.level)}"><td><strong>${esc(label(r))}</strong></td><td>${esc(r.line||'')}</td><td>${esc(r.flight||'')}</td><td class="num">${num(r.universe,0)}</td><td class="num">${num(r.impressions,0)}</td>`;
      for(let k=1;k<=6;k++)h+=`<td class="num v16-reach-cell">${reachCell(r,k)}</td>`;
      h+=`<td class="num">${num(r.avg_frequency,2)}</td></tr>`;
    }
    h+='</tbody>';$(ids.table).innerHTML=h;
  }

  function renderDiagnostics(){
    const lines=['REACH ENGINE v1.6 — TECHNICAL DIAGNOSTICS','Production 0.52 не вызывается.',''];
    for(const d of(v16Data?.diagnostics||[]))lines.push('• '+JSON.stringify(d));
    $(ids.diag).textContent=lines.join('\n');
    const warn=$(ids.warning),msgs=[];
    if(v16Data?.brand_error)msgs.push(v16Data.brand_error);
    const approx=(v16Data?.diagnostics||[]).filter(x=>String(x.code||'').includes('APPROX')||x.code==='AON_STAGED_MERGE'||x.code==='L2_AUTO_FALLBACK_QUICK');
    if(approx.length)msgs.push('Есть явно маркированные approximation/fallback — они раскрыты в карте модели и диагностике.');
    if(msgs.length){warn.innerHTML=msgs.map(esc).join('<br>');warn.classList.remove('hidden')}else warn.classList.add('hidden');
  }

  function renderAll(){
    if(!v16Data)return;
    $(ids.results).classList.remove('hidden');
    renderMetrics();renderFrequencyProfile();renderExactFrequency();renderContributions();renderTable();renderDiagnostics();renderL2Decision();renderModelMap();
  }

  function clearResults(){
    v16Data=null;
    $(ids.results)?.classList.add('hidden');
  }

  async function openV16File(file){
    try{
      clearResults();
      setStatus(ids.status,'<span class="spinner"></span>Читаю медиаплан…');
      await ensureV16Module();
      const ext=(file.name.split('.').pop()||'xlsx').toLowerCase();
      v16Path='/tmp/reach_v16_media_plan.'+(ext==='xlsm'?'xlsm':'xlsx');
      pyodide.FS.writeFile(v16Path,new Uint8Array(await file.arrayBuffer()));
      v16File=file;$(ids.file).textContent=file.name;
      v16Meta=await v16Call('reach_v16.discover(p)',{p:v16Path});
      v16Catalog=v16Meta.model_catalog||null;
      if(!v16Meta.plans?.length)throw new Error('В файле не найден медиаплан');
      renderPlanControls();renderInputAudit();renderL2Decision();renderModelMap();
      $(ids.controls).classList.remove('hidden');
      setStatus(ids.status,`✓ Прочитано Line: ${v16Meta.plans.length}. Проверьте KPI и нажмите «Рассчитать».`,'ok');
    }catch(e){
      console.error(e);clearResults();
      setStatus(ids.status,'Ошибка v1.6: '+esc(errText(e)),'err');
    }
  }

  async function calculateV16(){
    if(!v16Path||!v16Meta)return;
    const plans=selectedPlans();
    if(!plans.length){setStatus(ids.status,'Выберите хотя бы одну Line.','err');clearResults();return}
    const ov=currentOverrides(),bu=$(ids.brandU).value.trim();
    const q={
      selected_plan_ids:plans.map(x=>x.id),
      universes:Object.fromEntries(plans.map(x=>[x.id,x.universe])),
      l2_mode:ov.mode,K:ov.K,
      advanced:{
        L:ov.L,B:ov.B,D:ov.D,
        web_device_universes:Object.fromEntries(plans.filter(x=>x.webDeviceUniverse).map(x=>[x.id,x.webDeviceUniverse]))
      },
      brand_universe:bu===''?null:Number(bu)
    };
    try{
      clearResults();
      setStatus(ids.status,'<span class="spinner"></span>Считаю Levels 1–7…');
      v16Data=await v16Call('reach_v16.calculate(p,q)',{p:v16Path,q:JSON.stringify(q)});
      if(v16Data.model_catalog)v16Catalog=v16Data.model_catalog;
      renderAll();
      setStatus(ids.status,`✓ Reach Engine v1.6 рассчитан · ${v16Data.lines?.length||0} Line`,'ok');
    }catch(e){
      console.error(e);clearResults();
      const msg=errText(e);
      setStatus(ids.status,'Ошибка v1.6: '+esc(msg),'err');
      renderL2Decision();renderModelMap();
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
    $(ids.targetF).addEventListener('change',()=>{if(v16Data){renderMetrics();renderFrequencyProfile()}});
    $(ids.brandU).addEventListener('change',()=>{$(ids.brandU).dataset.manual=$(ids.brandU).value.trim()?'1':'0';renderModelMap();if(v16Data)calculateV16()});
    $(ids.autoU).addEventListener('click',()=>{syncBrandUniverse(true);renderModelMap();if(v16Data)calculateV16()});
    [ids.mode,ids.k,ids.L,ids.B,ids.D].forEach(id=>$(id)?.addEventListener('change',()=>{renderL2Decision();renderModelMap();if(v16Data)calculateV16()}));
  }

  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',bind);else bind();
  window.ReachEngineV16={calculate:calculateV16,openFile:openV16File};
})();