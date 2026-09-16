const assert = require('assert');
const core = require('../hardening-rules.js');

function c(v, extra={}) { return {v, ...extra}; }
function f(v, formula, extra={}) { return {v, f:formula, ...extra}; }

const flight = {
  '!ref':'A1:CV45',
  D5:c('Period'), E5:c('12.10.2026 - 30.11.2026'),
  D7:c('TA'), E7:c('Ж 25–45'),
  D13:c('Site'), E13:c('Ad Placement & targetings'), F13:c('Format'), J13:c('Month'), K13:c('CTR'), L13:c('Clicks'), M13:c('Tech formula'),
  CI14:c('26.10'), CI15:c('31.10'),
  D18:c('Astra Lab'), E18:c('Ж 25–44',{c:[{a:'Аналитик',t:'АУДИТ: проверить таргетинг'}]}), F18:c('Banner'), J18:c('October'),
  K18:f(0.02,'IFERROR(L18/1000,0)'), L18:f(100,'1000*K18'), M18:f(2.2,'_xlfn.IFS(K18="code",2.2,K18="pixel",2.2,K18="click",0)'),
  CI18:c(7), CS18:f(20,'SUM(CI18:CO18)'), AF18:c(3.5),
  D19:c('AstraLab'), E19:c('Ж 25–44'), F19:c('Banner'), J19:c('November'),
  K19:c(0.02), L19:c(100), M19:f(2.2,'_xlfn.IFS(K19="code",2.2,K19="pixel",2.2,K19="click",0)'),
  CI19:c(6), CS19:f(30,'SUM(CI19:CO19)'),
  CV19:c(new Date(Date.UTC(2026,10,30)),{t:'d',w:'30.11.2026',z:'dd.mm.yyyy'})
};

const summary = {
  '!ref':'A1:G12',
  B2:c('Дата начала кампании'), D2:f(new Date(Date.UTC(2026,9,12)),"'3 флайт'!CI14",{t:'d',w:'12.10.2026',z:'dd.mm.yyyy'}),
  B3:c('Дата окончания кампании'), D3:f(new Date(Date.UTC(2026,10,30)),"'3 флайт'!CV19",{t:'d',w:'30.11.2026',z:'dd.mm.yyyy'}),
  B4:c('Период кампании (дней)'), D4:f(64,"44+'3 флайт'!CS18"),
  B8:c('Campaign KPI'), F8:c('Частота'), G9:f(3.5,"'3 флайт'!AF18",{w:'3.5',z:'0.0'})
};

const inventory = {
  '!ref':'A1:B6', A1:c('Domain'),
  B2:c('big-bang-theory.online'), B3:c('garri-potter-film.ru'), B4:c('sherlock-online.ru'), B5:c('example.ru')
};

const textSheet = {
  '!ref':'A1:A5',
  A1:c('Уход за одеждой; уход  за одеждой'),
  A2:c('Также во вложении прикладываем ТТ'),
  A3:c('Покупатели в месяц стредств для стирки'),
  A4:c('12,000,000'),
  A5:c('видео роликов для размещения')
};

const wb = {SheetNames:['Свод','3 флайт','Inventory','Text'],Sheets:{'Свод':summary,'3 флайт':flight,Inventory:inventory,Text:textSheet}};
const r = core.runAllChecks(wb,{rawInfo:{definedNames:[],definedNamesTotal:0,externalLinks:[]},brandCard:null,globalExclusions:[]});

assert.strictEqual(core.canonicalPlatformName('Astra Lab'),'AstraLab','Astra Lab must normalize to AstraLab');
assert.notStrictEqual(core.canonicalPlatformName('Яндекс Директ'),core.canonicalPlatformName('Яндекс ПромоСтраницы'),'different Yandex products must not be merged');

assert(r.issues.some(x=>x.type==='Свод / устойчивость ссылки'&&x.cell==='D3'),'real campaign-end date direct reference must remain visible');
assert(!r.issues.some(x=>x.type==='Свод / устойчивость ссылки'&&x.cell==='G9'),'frequency 3.5 must never be classified as a campaign date');

const cal=r.issues.find(x=>x.type==='Календарь / активные дни'&&x.sheet==='3 флайт');
assert(cal&&/CI18/.test(cal.cell),'26.10–31.10 with 7 active days must be caught independently of flight header');
assert.strictEqual(cal.severity,core.SEVERITY.CRITICAL,'impossible active-day count is proven math error');

const paired=r.issues.find(x=>x.type==='Парные строки / формулы'&&x.sheet==='3 флайт');
assert(paired&&/K19/.test(paired.cell)&&/L19/.test(paired.cell),'manual derived KPI values in paired month row must be surfaced');

assert(r.issues.some(x=>x.type==='Свод / период кампании'&&x.sheet==='Свод'&&x.cell==='D4'&&/november/i.test(x.problem)),'summary duration must detect a missing active month, not missing parallel placement rows');

assert(r.issues.some(x=>x.type==='Комментарии Excel'&&x.sheet==='3 флайт'&&/E18/.test(x.cell)),'Excel comments must be surfaced before client send');
assert(r.issues.some(x=>x.type==='Техническая совместимость'&&x.sheet==='3 флайт'&&/_xlfn/i.test(x.problem)),'_xlfn formulas must be reported as low-priority technical information');

const bs=r.issues.find(x=>x.type==='Brand Safety / домены'&&x.sheet==='Inventory');
assert(bs&&/big-bang-theory\.online/.test(bs.value)&&/garri-potter-film\.ru/.test(bs.value)&&/sherlock-online\.ru/.test(bs.value),'expanded real-world serial/movie domains must be covered');
assert(!/example\.ru/.test(bs.value),'ordinary domains must not be added to brand-safety warning');

const dup=r.issues.find(x=>x.type==='Дубли таргетинга/ключевых слов'&&x.sheet==='Text'&&x.cell==='A1');
assert(dup,'keyword duplicates must be normalized by case and extra spaces');
assert(!r.issues.some(x=>x.type==='Дубли таргетинга/ключевых слов'&&x.cell==='A4'),'formatted number must never be treated as duplicate keywords');

assert(r.issues.some(x=>x.type==='Возможная тавтология'&&x.cell==='A2'),'safe tautology pattern must catch «во вложении прикладываем»');
assert(r.issues.some(x=>x.type==='Опечатка'&&x.cell==='A3'&&/стредств/.test(x.problem)),'obvious typo «стредств» must be caught');

const audience=r.issues.filter(x=>x.type==='ЦА / логика'&&x.sheet==='3 флайт');
assert.strictEqual(audience.length,1,'same normalized platform audience mismatches must be grouped into one review item');
assert(/AstraLab/.test(audience[0].problem),'grouped audience warning must use canonical platform name');

assert(!r.issues.some(x=>/technical reach.*universe|reach.*universe/i.test(String(x.problem||''))),'technical reach must not be compared with people universe');

console.log('hardening LAB tests passed',r.counts,'issues',r.issues.length);
