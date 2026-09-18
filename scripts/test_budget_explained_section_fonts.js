const fs=require('fs'),vm=require('vm');
const app=fs.readFileSync(process.argv[2]||'budget-checker/src/app.js','utf8');
const css=fs.readFileSync(process.argv[3]||'budget-checker/styles.css','utf8');
function extract(name){const start=app.indexOf('function '+name+'(');if(start<0)throw new Error('missing '+name);let i=app.indexOf('{',start),d=0;for(;i<app.length;i++){if(app[i]==='{')d++;else if(app[i]==='}'&&--d===0){i++;break;}}return app.slice(start,i)}
const mpResult={innerHTML:''},exportBtn={},manualBtn={};
const document={getElementById(id){if(id==='mpResult')return mpResult;if(id==='mpExportAuto')return exportBtn;if(id==='mpManual')return manualBtn;return null;},querySelectorAll(){return[];}};
const state={reconcile:{data:{}},lastMediaPlanComparison:null};
const C={MONTHS:['Янв','Фев','Мар','Апр','Май','Июн','Июл','Авг','Сен','Окт','Ноя','Дек']};
const esc=x=>String(x??''),money=x=>(Number(x||0)/100).toLocaleString('ru-RU',{minimumFractionDigits:0,maximumFractionDigits:2})+' ₽',info=x=>String(x),mpExclusionReasonLabel=x=>String(x||''),mpSourceDetailsHtml=()=>'<details>source</details>',mpTypeLabel=x=>x;
const mpExportComparison=()=>{},mpShowManual=()=>{},mpOpenExclusionsList=()=>{},mpOpenExclusionModal=()=>{};
const sb={document,state,C,esc,money,info,mpExclusionReasonLabel,mpSourceDetailsHtml,mpTypeLabel,mpExportComparison,mpShowManual,mpOpenExclusionsList,mpOpenExclusionModal,console};
vm.createContext(sb);
vm.runInContext(extract('mpRenderComparison')+';this.api={mpRenderComparison};',sb);
const mk=(channel,extra={})=>({type:'MONTH_MISMATCH',path:['LAB','МОМЕНТ','Интернет',channel],month:0,control:10000,external:9000,difference:-1000,rawDifference:-1000,message:channel,sources:[],...extra});
const result={fileName:'x.xlsx',brand:'МОМЕНТ',division:'LAB',extracted:{detectedSheets:['MP'],issues:[]},channelSummary:[],rows:[
 mk('CHANNEL_CRITICAL_X'),
 mk('CHANNEL_TECH_X',{explainedByTechnical:true}),
 mk('CHANNEL_ROUND_X',{type:'ROUNDING_NOTE',roundingOnly:true,difference:0,rawDifference:1})
],controlTotal:100,mediaTotal:100,difference:0,rawDifference:0,excludedCount:0,technicalCosts:[],technicalTotal:0,criticalMismatchCount:1,explainedMismatchCount:1,roundingNoteCount:1};
sb.api.mpRenderComparison(result);
const html=mpResult.innerHTML;
const split=html.split('<details class="mp-explained-section">');
if(split.length!==2)throw new Error('explained section missing or duplicated');
if(!split[0].includes('CHANNEL_CRITICAL_X'))throw new Error('critical mismatch missing from What does not match');
if(split[0].includes('CHANNEL_TECH_X')||split[0].includes('CHANNEL_ROUND_X'))throw new Error('explained rows leaked into What does not match');
if(!split[1].includes('CHANNEL_TECH_X')||!split[1].includes('CHANNEL_ROUND_X'))throw new Error('explained rows missing from explained section');
if(split[1].includes('CHANNEL_CRITICAL_X'))throw new Error('critical row leaked into explained section');
if(/<details class="mp-explained-section"\s+open/.test(html))throw new Error('explained section must be collapsed by default');
for(const marker of ['.mp-channel-table tbody td','.mp-diff-table tbody td','.mp-explained-table tbody td','font-weight:400!important','.mp-rounding-value{font-weight:400!important}']){
 if(!css.includes(marker))throw new Error('missing uniform font marker '+marker);
}
console.log('explained reconciliation section + uniform font weights: OK');
