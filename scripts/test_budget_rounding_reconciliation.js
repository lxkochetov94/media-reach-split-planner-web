const fs=require('fs'),vm=require('vm');
const app=fs.readFileSync(process.argv[2]||'budget-checker/src/app.js','utf8');
function extract(name){const start=app.indexOf('function '+name+'(');if(start<0)throw new Error('missing '+name);let i=app.indexOf('{',start),d=0;for(;i<app.length;i++){if(app[i]==='{')d++;else if(app[i]==='}'&&--d===0){i++;break;}}return app.slice(start,i)}
const names=['mpNorm','mpBuyingModel','mpCanonicalChannelKey','mpChannelFamily','mpTokenScore','mpDeterministicChannelTarget','mpMatchChannel','mpPlacementTarget','mpAuxChannel','mpPeriodMonths','mpAllocateCentsByControl','mpTechnicalBreakdown','mpAggregateExternal','mpExclusionReasonLabel','mpExclusionKey','mpProjectExclusions','mpFindExclusion','mpIsAuxName','mpTechnicalCostGroups','mpRoundedRubles','mpSameAfterRubleRounding','mpRoundingMessage','mpCompare'];
const state={project:{mediaPlanExclusions:[]}},C={MONTHS:['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек']};
const money=k=>(Number(k||0)/100).toLocaleString('ru-RU',{minimumFractionDigits:0,maximumFractionDigits:2})+' ₽';
const sb={state,C,money,console};vm.createContext(sb);vm.runInContext(names.map(extract).join('\n')+';this.api={mpRoundedRubles,mpSameAfterRubleRounding,mpCompare};',sb);
if(!sb.api.mpSameAfterRubleRounding(2151174336,2151174337))throw new Error('1 kopeck in same rounded ruble must match');
if(sb.api.mpSameAfterRubleRounding(10049,10051))throw new Error('values crossing a ruble rounding boundary must not match');

const ctx={brand:'МОМЕНТ',division:'LAB КЛЕЕВЫЕ',channels:[{channel:'ОЛВ',typeMedia:'Интернет',months:[2151174336,0,0,0,0,0,0,0,0,0,0,0]}]};
const extracted={placements:[{section:'OLV',channelKey:'olv',month:0,amount:21511743.37,sheet:'MP',sourceCell:'U18'}],auxCosts:[],technicalCosts:[],detectedSheets:['MP'],issues:[]};
const r=sb.api.mpCompare(ctx,null,'moment.xlsx',extracted);
if(r.difference!==0||r.rawDifference!==1||!r.overallRoundingOnly)throw new Error('overall rounding classification failed '+JSON.stringify({difference:r.difference,raw:r.rawDifference,flag:r.overallRoundingOnly}));
if(r.criticalMismatchCount!==0||r.roundingNoteCount<1)throw new Error('rounding note must not be critical mismatch');
const note=r.rows.find(x=>x.roundingOnly);
if(!note||note.difference!==0||note.rawDifference!==1||!/0,01/.test(note.message))throw new Error('rounding note content failed '+JSON.stringify(note));

const ctx2={brand:'МОМЕНТ',division:'LAB КЛЕЕВЫЕ',channels:[{channel:'ОЛВ',typeMedia:'Интернет',months:[10049,0,0,0,0,0,0,0,0,0,0,0]}]};
const ext2={placements:[{section:'OLV',channelKey:'olv',month:0,amount:100.51,sheet:'MP',sourceCell:'U19'}],auxCosts:[],technicalCosts:[],detectedSheets:['MP'],issues:[]};
const r2=sb.api.mpCompare(ctx2,null,'x.xlsx',ext2);
if(r2.criticalMismatchCount===0||r2.difference===0)throw new Error('real rounded-ruble mismatch was incorrectly suppressed');
console.log('rounding-aware reconciliation regression: OK');
