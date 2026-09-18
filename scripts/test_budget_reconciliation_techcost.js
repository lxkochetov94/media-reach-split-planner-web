const fs=require('fs'),vm=require('vm');
const app=fs.readFileSync(process.argv[2]||'budget-checker/src/app.js','utf8');
function extract(name){const start=app.indexOf('function '+name+'(');if(start<0)throw new Error('missing '+name);let i=app.indexOf('{',start),d=0;for(;i<app.length;i++){if(app[i]==='{')d++;else if(app[i]==='}'&&--d===0){i++;break;}}return app.slice(start,i)}
const names=['mpNorm','mpBuyingModel','mpCanonicalChannelKey','mpChannelFamily','mpTokenScore','mpDeterministicChannelTarget','mpMatchChannel','mpPlacementTarget','mpAuxChannel','mpAggregateExternal','mpExclusionReasonLabel','mpExclusionKey','mpProjectExclusions','mpFindExclusion','mpIsAuxName','mpTechnicalCostGroups','mpCompare'];
const state={project:{mediaPlanExclusions:[]}},C={MONTHS:['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек']};
const money=k=>(Number(k||0)/100).toLocaleString('ru-RU',{minimumFractionDigits:0,maximumFractionDigits:2})+' ₽';
const sb={state,C,money,console};vm.createContext(sb);vm.runInContext(names.map(extract).join('\n')+';this.api={mpCompare};',sb);
const control=100000000,externalRub=906346.01,tnsRub=93653.99;
const ctx={brand:'МОМЕНТ',division:'LAB КЛЕЕВЫЕ',channels:[{channel:'ОЛВ',typeMedia:'Интернет',months:[control,0,0,0,0,0,0,0,0,0,0,0]}]};
const extracted={placements:[{section:'OLV',channelKey:'olv',month:0,amount:externalRub,sheet:'MP',sourceCell:'U18'}],auxCosts:[],technicalCosts:[{kind:'tns',label:'Счётчик TNS',rawLabel:'Пиксель TNS',amount:tnsRub,sheet:'MP',sourceCell:'B30'}],detectedSheets:['MP'],issues:[]};
const r=sb.api.mpCompare(ctx,null,'moment.xlsx',extracted);
if(r.difference!==0)throw new Error('technical cost must reconcile total: '+r.difference);
if(!r.technicalExplanation||r.technicalExplanation.kind!=='tns')throw new Error('TNS explanation missing');
if(r.technicalTotal!==9365399)throw new Error('TNS total '+r.technicalTotal);
if(!r.rows.length||r.rows.some(x=>!x.explainedByTechnical))throw new Error('channel mismatches must be marked as technically explained');
const tech=r.channelSummary.find(x=>x.technical&&x.channel==='Счётчик TNS');
if(!tech||tech.external!==9365399)throw new Error('technical summary row missing');
console.log('reconciliation technical-cost regression: OK');
