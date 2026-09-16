const assert = require('assert');
const core = require('../reliability-rules.js');

function c(v, extra={}) { return {v, ...extra}; }
function f(v, formula, extra={}) { return {v, f:formula, ...extra}; }

const flight = {
  '!ref':'A1:CU60',
  E5:c('Period'), F5:c('12.10.2026-30.11.2026'),
  C13:c('№'), D13:c('Sales house'), E13:c('Site'), F13:c('Ad Placement & targetings'), G13:c('Ad size (pixels) / Format'), H13:c('Video details'), I13:c('Unit type'), J13:c('AdServer'), K13:c('Month'),
  L13:c('Units Qty total'), M13:c('Ratecard\n(cost per unit)'), N13:c('Multipliers'), O13:c('Data CPM'), P13:c('Discount, %'), Q13:c('CPM incl. discount'), R13:c('Total cost after discount, RUR'), S13:c('Adserving'), U13:c('Total cost + adserving, RUR'), V13:c('Media Results forecast'),
  V14:c('Impressions'), W14:c('Impressions, %'), X14:c('Reach UU'), Y14:c('Frequency'), Z14:c('CPT'), AA14:c('CTR%'), AB14:c('Clicks'), AC14:c('CPC'), AD14:c('Completed views 100%'), AE14:c('Planning VTR % (100%)'), AF14:c('CPV (100%)'),
  S15:c('Cost per unt'), T15:c('Total cost'),

  // Calendar band. AL16 is a week number and must never be interpreted as active days.
  AL14:c('01.02'), AL15:c('01.02'), AL16:c(5), AL17:c(1),
  CG14:c('26.10'), CG15:c('31.10'), CG16:c(44), CG17:c(6),

  // Same placement, two months; first platform contains a bonus decoration.
  E18:c('VK Видео\nБонус BLS',{c:[{a:'Analyst',t:'ÐÐ£ÐÐÐ¢ â Ð¿ÑÐ¾Ð²ÐµÑÐ¸ÑÑ ÑÐ¾ÑÐ¼ÑÐ»Ñ'}]}),
  F18:c('Ж 25-35 ВС\n1) Интересы; 2) Ключевые слова;'), G18:c('Pre-roll\nIn-stream 100%'), I18:c('1000 imp.'), J18:c('pixel'), K18:c('October'),
  L18:c(4968.636), M18:c(170), N18:c(1), O18:c(0), P18:c(0),
  Q18:f(170,'IFERROR(R18/V18*1000,"-")'), R18:f(844668.12,'IFERROR(L18*((M18-M18*P18)+O18)*N18,"-")'), S18:c(2.2), T18:f(12570.649,'V18/1000*S18*1.15'), U18:f(857238.769,'R18+T18'),
  V18:f(4968636,'L18*1000'), X18:f(1656212,'IFERROR(V18/Y18,"-")'), Y18:c(3), Z18:f(510,'IFERROR(R18/X18*1000,"-")'), AA18:c(.009), AB18:f(44717.724,'V18*AA18'), AC18:f(18.8889,'R18/AB18'), AD18:f(3229613.4,'V18*AE18'), AE18:c(.65), AF18:f(.261538,'R18/AD18'),
  CG18:c(7),

  E19:c('VK Видео',{c:[{a:'Planner',t:'Стоимость 2025'}]}),
  F19:c('Ж 25-35 ВС\n1) Интересы; 2) Ключевые слова;'), G19:c('Pre-roll\nIn-stream 100%'), I19:c('1000 imp.'), J19:c('pixel'), K19:c('November'),
  L19:c(1732.499), M19:c(170), N19:c(1), O19:c(0), P19:c(0),
  Q19:c(170), R19:c(294524.83), S19:c(2.2), T19:c(4383.22), U19:c(298908.05),
  V19:f(1732499,'L19*1000'), X19:c(577499.667), Y19:c(3), Z19:c(510), AA19:c(.009), AB19:c(15592.491), AC19:c(18.8889), AD19:f(1126124.35,'V19*AE19'), AE19:c(.65), AF19:c(.261538),

  // _xlfn exists but must be ignored completely in final audit.
  T22:f(2.2,'_xlfn.IFS(J22="code",2.2,J22="pixel",2.2,J22="click",0)'),

  // Numbers in a KPI column: 4.5 is Frequency, not 4 May.
  Z28:c(4.5), Z29:c(4.5), Z30:c(4.5), Z31:c(4.5), Z32:c(5),

  // Broken range with a structurally different middle formula: secondary noise must not survive.
  G40:c('#REF!',{t:'e',f:'#REF!'}),
  G41:c('#REF!',{t:'e',f:'IFERROR(#REF!,0)'}),
  G42:c('#REF!',{t:'e',f:'#REF!'}),
  G43:c('#REF!',{t:'e',f:'#REF!'}),
  G44:c('#REF!',{t:'e',f:'#REF!'}),
  G45:c('#REF!',{t:'e',f:'#REF!'}),
  G46:c('#REF!',{t:'e',f:'#REF!'})
};

const textSheet = {
  '!ref':'A1:A3',
  A1:c('видео роликов для размещения'),
  A2:c('Cost per unt'),
  A3:c('ОФД данные')
};

const wb = {SheetNames:['3 флайт','Text'],Sheets:{'3 флайт':flight,Text:textSheet}};
const r = core.runAllChecks(wb,{rawInfo:{definedNames:[],definedNamesTotal:0,externalLinks:[]},brandCard:null,globalExclusions:[]});

const calendar = r.issues.filter(x=>x.type==='Календарь / активные дни');
assert(calendar.some(x=>/CG18/.test(x.cell)),'real 26.10–31.10 = 7 days must be caught');
assert(!calendar.some(x=>/AL16|AL17/.test(x.cell)),'week number/default row must never be treated as placement active days');
assert(!calendar.some(x=>/Z3[0-2]|Z2[8-9]/.test(x.cell)),'Frequency 4.5/5 must never be parsed as dates or calendar days');

const paired = r.issues.find(x=>x.type==='Парные строки / формулы'&&x.sheet==='3 флайт');
assert(paired,'paired month formula/value mismatch must be detected even when one platform row contains Bonus BLS decoration');
for (const ref of ['Q19','R19','T19','U19','X19','Z19','AB19','AC19','AF19']) assert(paired.cell.includes(ref),`paired check must show concrete cell ${ref}`);

assert(!r.issues.some(x=>/_xlfn\./i.test(`${x.problem||''} ${x.value||''}`)),'_xlfn must be completely ignored');

const service = r.issues.find(x=>x.type==='Комментарии Excel / служебные');
assert(service && /АУДИТ/.test(service.value),'mojibake audit comment must be repaired and classified as internal');
const ordinary = r.issues.find(x=>x.type==='Комментарии Excel / прочие');
assert(ordinary && /Стоимость 2025/.test(ordinary.value),'ordinary workbook comment must be kept separately');

assert(!r.issues.some(x=>x.cell==='G41' && /(структура формул|формул.*паттерн)/iu.test(`${x.type||''} ${x.problem||''}`)),'secondary formula-pattern warning inside broken G40:G46 block must be suppressed');

const costIssues = r.issues.filter(x=>x.sheet==='Text'&&x.cell==='A2'&&/cost\s+per\s+unt/i.test(`${x.problem||''} ${x.value||''}`));
assert.strictEqual(costIssues.length,1,'Cost per unt must produce one text root cause, not duplicates');
const videoIssues = r.issues.filter(x=>x.sheet==='Text'&&x.cell==='A1'&&/видео\s+ролик|видеоролик/iu.test(`${x.problem||''} ${x.value||''}`));
assert.strictEqual(videoIssues.length,1,'video роликов spelling must produce one root cause, not duplicates');

assert(!r.issues.some(x=>/technical reach.*universe|reach.*universe/i.test(String(x.problem||''))),'technical Reach must not be compared with people universe');

console.log('reliability Vernell tests passed',r.counts,'issues',r.issues.length);
