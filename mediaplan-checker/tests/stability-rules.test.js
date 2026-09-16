const assert = require('assert');
const core = require('../stability-rules.js');

function c(v, extra={}) { return {v, ...extra}; }
function f(v, formula, extra={}) { return {v, f:formula, ...extra}; }

const flight = {
  '!ref':'A1:CV40',
  D5:c('Period'), E5:c('01.11.2026 - 31.12.2026'),
  D13:c('Site'), E13:c('Ad Placement & targetings'), F13:c('Format'), J13:c('Month'),
  CI14:c('01.11'), CJ14:c('08.11'), CK14:c('15.11'), CL14:c('22.11'), CM14:c('29.11'),
  CI15:c('01.12'), CJ15:c('08.12'), CK15:c('15.12'), CL15:c('22.12'), CM15:c('29.12'),
  D18:c('Digital Alliance'), J18:c('November'), CS18:f(30,'=SUM(CI18:CO18)'), CV18:c(new Date(Date.UTC(2026,10,30)),{t:'d',w:'30.11.2026',z:'dd.mm.yyyy'}),
  D19:c('Digital Alliance'), J19:c('December'), CS19:f(31,'=SUM(CI19:CO19)'), CV19:c(new Date(Date.UTC(2026,11,31)),{t:'d',w:'31.12.2026',z:'dd.mm.yyyy'}),
  D20:c('Hybrid'), J20:c('November'), CS20:f(30,'=SUM(CI20:CO20)'), CV20:c(new Date(Date.UTC(2026,10,30)),{t:'d',w:'30.11.2026',z:'dd.mm.yyyy'}),
  D21:c('Hybrid'), J21:c('December'), CS21:f(31,'=SUM(CI21:CO21)'), CV21:c(new Date(Date.UTC(2026,11,31)),{t:'d',w:'31.12.2026',z:'dd.mm.yyyy'}),
  V28:c('Reach (people) 1+'), W28:c(5000000), V29:c('Reach (%) 1+'), W29:f(.4,'=W28/$E$7')
};

const summary = {
  '!ref':'A1:D6',
  B2:c('Период кампании'),
  B3:c('Окончание кампании'), D3:f(new Date(Date.UTC(2026,11,31)),"='2 флайт'!CV19",{t:'d',w:'31.12.2026',z:'dd.mm.yyyy'}),
  B4:c('Период кампании (дней)'), D4:f(105,"=44+'2 флайт'!CS18+'2 флайт'!CS19")
};

const inventory = {
  '!ref':'A1:B4',
  A1:c('Domain'),
  B2:c('lordfilm-example.com'),
  B3:c('office-serial.com'),
  B4:c('example.ru')
};

const wb = {SheetNames:['Свод','2 флайт','Inventory'], Sheets:{'Свод':summary,'2 флайт':flight,Inventory:inventory}};
const r = core.runAllChecks(wb,{rawInfo:{definedNames:[],definedNamesTotal:0,externalLinks:[]},brandCard:null,globalExclusions:[]});

assert(!r.issues.some(x=>x.type==='Расчёт охвата / воспроизводимость'),'manual Reach forecast must not be treated as a problem by default');
assert(!r.issues.some(x=>x.type==='Формула / период' && /использует не все месячные итоги активных дней/i.test(x.problem)),'period formula must not require every placement row when referenced rows already cover all distinct months');
assert(r.issues.some(x=>x.type==='Формула / период' && x.sheet==='Свод' && x.cell==='D4' && /констант/i.test(x.problem)),'hard-coded period constant must remain visible');
assert(r.issues.some(x=>x.type==='Свод / устойчивость ссылки' && x.sheet==='Свод' && x.cell==='D3'),'summary campaign end date linked to one placement row must be flagged as a structural risk');
const bs = r.issues.find(x=>x.type==='Brand Safety / домены' && x.sheet==='Inventory');
assert(bs && /lordfilm-example\.com/.test(bs.value) && /office-serial\.com/.test(bs.value),'suspicious entertainment domains must be surfaced for manual brand-safety review');
assert(!/example\.ru/.test(bs.value),'ordinary domains must not be included in brand-safety warning');
assert(!r.issues.some(x=>/universe/i.test(x.problem)),'technical Reach must never be compared with people universe');

console.log('stability LAB tests passed', r.counts, 'issues', r.issues.length);
