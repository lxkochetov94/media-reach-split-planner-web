const fs=require('fs'),vm=require('vm');
const app=fs.readFileSync(process.argv[2]||'budget-checker/src/app.js','utf8');
function extract(name){const start=app.indexOf(`function ${name}(`);if(start<0)throw new Error('missing '+name);let i=app.indexOf('{',start),d=0;for(;i<app.length;i++){if(app[i]==='{')d++;else if(app[i]==='}'&&--d===0){i++;break;}}return app.slice(start,i)}
const names=['mpNorm','mpBuyingModel','mpCanonicalChannelKey','mpChannelFamily','mpTokenScore','mpDeterministicChannelTarget','mpMatchChannel','mpPlacementTarget','mpAuxChannel','mpPeriodMonths','mpAllocateCentsByControl','mpTechnicalBreakdown','mpAggregateExternal','mpExclusionReasonLabel','mpExclusionKey','mpProjectExclusions','mpFindExclusion','mpIsAuxName','mpTechnicalCostGroups','mpRoundedRubles','mpSameAfterRubleRounding','mpRoundingMessage','mpCompare'];
const state={project:{mediaPlanExclusions:[]}};const C={MONTHS:['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек']};
const sandbox={state,C,console};vm.createContext(sandbox);vm.runInContext(names.map(extract).join('\n')+'\nthis.api={mpCanonicalChannelKey,mpMatchChannel,mpCompare};',sandbox);
const ctx={brand:'МОМЕНТ',division:'LAB КЛЕЕВЫЕ',channels:[
 {channel:'Социальные сети CPM',typeMedia:'Интернет',months:[291761435,0,0,0,0,0,0,0,0,0,0,0]},
 {channel:'Социальные сети CPC',typeMedia:'Интернет',months:[201275000,0,0,0,0,0,0,0,0,0,0,0]},
 {channel:'Промостатьи',typeMedia:'Интернет',months:[30000000,0,0,0,0,0,0,0,0,0,0,0]},
 {channel:'Еком Awareness',typeMedia:'E-commerce',months:[500000000,0,0,0,0,0,0,0,0,0,0,0]},
 {channel:'Блогеры',typeMedia:'',months:[2500000000,0,0,0,0,0,0,0,0,0,0,0]}
]};
if(sandbox.api.mpCanonicalChannelKey('Social nets, CPC Герметики')!=='social cpc')throw new Error('social cpc canonical failed');
if(sandbox.api.mpMatchChannel('Social nets, CPC Герметики',ctx)?.channel!=='Социальные сети CPC')throw new Error('social cpc match failed');
const ext={placements:[
 {section:'Social nets, CPM Герметики',channelKey:'social cpm',month:0,amount:1447979.94,sheet:'MP',sourceCell:'U1'},
 {section:'Social nets, CPM Монтажные клеи',channelKey:'social cpm',month:0,amount:1447979.94,sheet:'MP',sourceCell:'U2'},
 {section:'Social nets, CPC Герметики',channelKey:'',month:0,amount:1007200,sheet:'MP',sourceCell:'U3'},
 {section:'Social nets, CPC Монтажные клеи',channelKey:'',month:0,amount:1005550,sheet:'MP',sourceCell:'U4'}
],auxCosts:[],detectedSheets:['MP'],issues:[]};
let r=sandbox.api.mpCompare(ctx,null,'x.xlsx',ext);
const cpc=r.channelSummary.find(x=>x.channel==='Социальные сети CPC');
if(cpc.external!==201275000||cpc.difference!==0||cpc.excluded)throw new Error('social cpc aggregate mismatch '+JSON.stringify(cpc));
if(r.channelSummary.some(x=>x.typeMedia==='Не сопоставлено'&&/Social nets, CPC/.test(x.channel)))throw new Error('social cpc remained unmapped');
state.project.mediaPlanExclusions=[
 {brand:'МОМЕНТ',kind:'channel',channel:'Промостатьи',reasonCode:'SEPARATE_PLAN',comment:''},
 {brand:'МОМЕНТ',kind:'channel',channel:'Еком Awareness',reasonCode:'OUTSIDE_PLAN',comment:''},
 {brand:'МОМЕНТ',kind:'channel',channel:'Блогеры',reasonCode:'OUTSIDE_PLAN',comment:''}
];
r=sandbox.api.mpCompare(ctx,null,'x.xlsx',ext);
for(const ch of ['Промостатьи','Еком Awareness','Блогеры']){const x=r.channelSummary.find(y=>y.channel===ch);if(!x?.excluded)throw new Error(ch+' not excluded');if(r.rows.some(d=>(d.path||[]).includes(ch)))throw new Error(ch+' still creates mismatch');}
if(r.excludedCount!==3)throw new Error('excludedCount');
console.log('social CPC + exclusions regression: OK');
