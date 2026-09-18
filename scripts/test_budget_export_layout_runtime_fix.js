const fs=require('fs'),vm=require('vm');
const app=fs.readFileSync(process.argv[2]||'budget-checker/src/app.js','utf8');
function extract(name){const start=app.indexOf('function '+name+'(');if(start<0)throw new Error('missing '+name);let i=app.indexOf('{',start),d=0;for(;i<app.length;i++){if(app[i]==='{')d++;else if(app[i]==='}'&&--d===0){i++;break;}}return app.slice(start,i)}
const mpResult={innerHTML:''},exportBtn={},manualBtn={};
const document={
  getElementById(id){if(id==='mpResult')return mpResult;if(id==='mpExportAuto')return exportBtn;if(id==='mpManual')return manualBtn;return null;},
  querySelectorAll(){return[];}
};
const state={reconcile:{data:{}},lastMediaPlanComparison:null};
const C={MONTHS:['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек']};
const esc=x=>String(x??''),money=x=>String(x??0),info=x=>String(x),mpExclusionReasonLabel=x=>String(x||''),mpSourceDetailsHtml=()=>'',mpTypeLabel=x=>x;
const mpExportComparison=()=>{},mpShowManual=()=>{},mpOpenExclusionsList=()=>{},mpOpenExclusionModal=()=>{};
const written={};
const XLSX={utils:{
  book_new:()=>({sheets:[]}),
  aoa_to_sheet:data=>({'!ref':`A1:J${data.length}`,data}),
  decode_range:ref=>({e:{r:Number(ref.match(/\d+$/)[0])-1}})
},writeFile:(wb,name)=>{written.wb=wb;written.name=name;}};
XLSX.utils.book_append_sheet=(wb,ws,name)=>wb.sheets.push({ws,name});
const budgetSafeFilePart=x=>x,budgetToday=()=> '2026-09-18';
const sb={document,state,C,esc,money,info,mpExclusionReasonLabel,mpSourceDetailsHtml,mpTypeLabel,mpExportComparison,mpShowManual,mpOpenExclusionsList,mpOpenExclusionModal,XLSX,budgetSafeFilePart,budgetToday,console};
vm.createContext(sb);
vm.runInContext([extract('mpApplyExportLayout'),extract('mpRenderComparison'),extract('mpExportComparison')].join('\n')+';this.api={mpRenderComparison,mpExportComparison};',sb);
const result={fileName:'x.xlsx',brand:'МОМЕНТ',division:'LAB КЛЕЕВЫЕ',extracted:{detectedSheets:['MP'],issues:[]},channelSummary:[],rows:[],controlTotal:100,mediaTotal:100,difference:0,rawDifference:0,excludedCount:0,technicalCosts:[],technicalTotal:0,criticalMismatchCount:0,explainedMismatchCount:0,roundingNoteCount:0};
sb.api.mpRenderComparison(result);
if(!/Выгрузить сверку в Excel/.test(mpResult.innerHTML))throw new Error('render failed');
sb.api.mpExportComparison(result);
const byName=Object.fromEntries(written.wb.sheets.map(x=>[x.name,x.ws]));
if(byName['Итоги']['!cols'][0].wch!==40.796875||byName['Итоги']['!cols'][1].wch!==49)throw new Error('summary widths');
if(byName['По каналам']['!cols'].length!==10||byName['По каналам']['!cols'][2].wch!==31)throw new Error('channel widths');
if(byName['Расхождения']['!cols'][8].wch!==239.3984375||byName['Расхождения']['!cols'][9].wch!==255)throw new Error('detail widths');
if(!byName['Расхождения']['!rows'].every(x=>x.hpt===15.6))throw new Error('row height');
console.log('tech runtime + export layout regression: OK');