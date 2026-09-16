const assert = require('assert');
const core = require('../final-rules.js');

function c(v, extra={}) { const o={v,...extra}; if(extra.w===undefined && typeof v==='string') o.w=v; return o; }
function f(v, formula, extra={}) { return {v, f:formula, w:String(v), ...extra}; }

const flight3 = {
  '!ref':'A1:L22',
  F3:c("Вернель Гранулы Октябрь-Ноябрь'26"),
  F5:c('12.12.2026-30.11.2026'),
  F6:c('Ж 25-45 ВС'),
  C17:c('OLV'), C18:c('Digital Alliance'), L18:c('October'),
  C19:c('Digital Alliance'), L19:c('November'),
  C20:c('Banners, CPM'), L20:c('October'),
  C21:c('Banners, CPM'), L21:c('November'),
  K14:c('12.10'),
  A22:c('Текущие объемы выше порогового месячного бюджета')
};

const math = {
  '!ref':'A1:D3',
  A1:c('Budget (net)'), B1:c('Clicks'), C1:c('CPC'), D1:c('Source'),
  A2:f(1000,'=D2'), B2:c(10), C2:c(200), D2:c(1000),
  A3:c(1000), B3:c(10), C3:c(200), D3:c(1000)
};

const wb = {
  SheetNames:['3 флайт','Математика'],
  Sheets:{'3 флайт':flight3,'Математика':math}
};
const rawInfo = {
  definedNamesTotal:5,
  definedNames:[
    {name:'a',ref:'#REF!'},
    {name:'b',ref:'#VALUE!+#N/A'}
  ],
  externalLinks:[]
};
const intro = 'Старт 12 октября. Размещение надо растянуть на 2 месяца: и OLV и баннеры.';
const r = core.runAllChecks(wb,{rawInfo,intro,globalExclusions:['CPC']});

const start = r.introResults.find(x=>x.sentence.includes('Старт 12 октября'));
assert(start && start.status==='Требует проверки' && /шапк/i.test(start.detail),'start date conflict must be surfaced');
assert(r.issues.some(x=>x.type==='Сопроводительные вводные' && /Дата старта в шапке противоречит/.test(x.problem)),'start conflict issue');

const duration = r.introResults.find(x=>x.sentence.includes('растянуть на 2 месяца'));
assert(duration && duration.status==='Найдено' && /2 месяца/.test(duration.detail),'two-month placement must be confirmed');

assert(!r.issues.some(x=>x.type==='Математика медиаплана' && x.sheet==='Математика' && x.cell==='C2'),'generic media math must not override formula-driven row');
assert(r.issues.some(x=>x.type==='Математика медиаплана' && x.sheet==='Математика' && x.cell==='C3'),'plain-value media math warning should remain');

const names = r.issues.find(x=>x.type==='Именованные диапазоны');
assert(names && /2 уникальных/.test(names.problem) && /3 срабатыван/.test(names.problem),'defined names should distinguish unique names and token hits');

assert(r.issues.some(x=>x.type==='Обоснование порога'),'unsupported threshold claim must be review');
assert(!r.issues.some(x=>/universe/i.test(x.problem)),'technical reach must never be compared to people universe');

console.log('final rules tests passed', r.counts, 'issues', r.issues.length);
