const fs=require('fs'),vm=require('vm');
const app=fs.readFileSync(process.argv[2]||'budget-checker/src/app.js','utf8');
function extract(name){const start=app.indexOf('function '+name+'(');if(start<0)throw new Error('missing '+name);let i=app.indexOf('{',start),d=0;for(;i<app.length;i++){if(app[i]==='{')d++;else if(app[i]==='}'&&--d===0){i++;break;}}return app.slice(start,i)}
const names=['mpNorm','mpBuyingModel','mpCanonicalChannelKey','mpChannelFamily','mpTokenScore','mpDeterministicChannelTarget','mpMatchChannel','mpPlacementTarget','mpAuxChannel','mpPeriodMonths','mpAllocateCentsByControl','mpTechnicalBreakdown','mpAggregateExternal','mpExclusionReasonLabel','mpExclusionKey','mpProjectExclusions','mpFindExclusion','mpIsAuxName','mpTechnicalCostGroups','mpRoundedRubles','mpSameAfterRubleRounding','mpRoundingMessage','mpCompare'];
const state={project:{mediaPlanExclusions:[]}},C={MONTHS:['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек']};
const money=k=>(Number(k||0)/100).toLocaleString('ru-RU',{minimumFractionDigits:0,maximumFractionDigits:2})+' ₽';
const sb={state,C,money,console};vm.createContext(sb);vm.runInContext(names.map(extract).join('\n')+';this.api={mpCompare,mpAggregateExternal};',sb);
const ctx={brand:'ГЛИСС КУР',division:'LAB КРАСОТА',channels:[{channel:'Баннерное размещение CPM',typeMedia:'Интернет',months:[0,0,0,0,10000000,50000000,0,0,0,0,0,0]}]};
function baseExtract(amount,technicalCosts=[]){return{placements:[{sheet:'MP',row:18,section:'Banners, CPM',channelKey:'banners cpm',site:'Hybrid',amount,month:null,monthRaw:'2026-05-01 — 2026-06-30',periodMonths:[4,5],periodStart:'2026-05-01',periodEnd:'2026-06-30',sourceCell:'U18'}],auxCosts:[],technicalCosts,detectedSheets:['MP'],issues:[]};}
let r=sb.api.mpCompare(ctx,null,'x.xlsx',baseExtract(600000));
if(r.criticalMismatchCount!==0||r.difference!==0)throw new Error('exact period total must reconcile '+JSON.stringify({crit:r.criticalMismatchCount,diff:r.difference,rows:r.rows}));
let ch=r.channelSummary.find(x=>x.channel==='Баннерное размещение CPM');
if(ch.external!==60000000)throw new Error('channel total exact');
if(r.periodAllocationCount!==1)throw new Error('period allocation missing');
const agg=sb.api.mpAggregateExternal(baseExtract(600000),ctx).matched.get('баннерное размещение cpm');
if(agg.months[4]!==10000000||agg.months[5]!==50000000)throw new Error('must split 100k/500k from flowchart: '+agg.months.slice(4,6));

r=sb.api.mpCompare(ctx,null,'x.xlsx',baseExtract(570000,[{kind:'tns',label:'Счётчик TNS',amount:30000,signedAmount:30000,sheet:'MP',row:30,sourceCell:'B30',rawLabel:'Счётчик TNS'}]));
if(r.difference!==0||r.criticalMismatchCount!==0||!r.technicalExplanation)throw new Error('570k + TNS 30k must reconcile '+JSON.stringify({diff:r.difference,crit:r.criticalMismatchCount,tech:r.technicalExplanation,rows:r.rows}));
if(r.technicalTotal!==3000000)throw new Error('TNS signed total');
if(!r.rows.some(x=>x.explainedByTechnical))throw new Error('monthly/channel gaps must be explained by tech');
const agg2=sb.api.mpAggregateExternal(baseExtract(570000),ctx).matched.get('баннерное размещение cpm');
if(agg2.months[4]!==9500000||agg2.months[5]!==47500000)throw new Error('570k must retain total and follow 1:5 flowchart ratio: '+agg2.months.slice(4,6));

r=sb.api.mpCompare(ctx,null,'x.xlsx',baseExtract(630000,[{kind:'discount',label:'Скидка / дисконт',amount:30000,signedAmount:-30000,sheet:'MP',row:30,sourceCell:'B30',rawLabel:'Скидка'}]));
if(r.difference!==0||r.criticalMismatchCount!==0||r.technicalTotal!==-3000000)throw new Error('630k - discount 30k must reconcile '+JSON.stringify({diff:r.difference,crit:r.criticalMismatchCount,tech:r.technicalTotal}));
console.log('period reconciliation + signed technical adjustments: OK');
