const assert = require('assert');
const core = require('../baseline-rules.js');

function c(v, extra={}) { return {v, ...extra}; }
function f(v, formula, extra={}) { return {v, f:formula, ...extra}; }

const media = {
  '!ref':'A1:EU35',
  D5:c('Period'), E5:c('01.11.2026 - 30.11.2026'), D6:c('TA'), E6:c('Ж 25-40'),
  D13:c('Site'), E13:c('Ad Placement & targetings'), F13:c('Ad size (pixels) / Format'), G13:c('Video details'), H13:c('Unit type'), J13:c('Month'),
  D18:c('Yandex RTB'), E18:c('Ж 25-44\n1) Интересы'), F18:c('Баннеры'), G18:c('-'), H18:c('1000 imp.'), J18:c('November'), R18:f(2.2,'=_xlfn.IFS(I18="code",2.2,I18="pixel",2.2,I18="click",0)'), U18:f(1,'=IF(A1="x",#REF!/#REF!,1)'),
  D19:c('Hybrid'), E19:c('Ж 25-40'), F19:c('Баннеры'), G19:c('-'), H19:c('1000 imp.'), J19:c('November'), U19:f(1,'=IF(A1="x",#REF!/#REF!,1)'),
  D20:c('First Data'), E20:c('Ж 25-40'), F20:c('Баннеры'), G20:c('-'), H20:c('1000 imp.'), J20:c('November'), U20:f(1,'=IF(A1="x",#REF!/#REF!,1)'),
  D23:c('VK'), E23:c('Ж 25-40'), F23:c('Promopost'), G23:c('-'), H23:c('1000 imp.'), J23:c('November'), U23:f(1,'=IF(A1="x",#REF!/#REF!,1)'),
  DA12:c('January'), DE12:c('February'), DI12:c('March'), DM12:c('April'), DQ12:c('May'), DU12:c('June'), DY12:c('July'), EC12:c('August'), EG12:c('September'), EK12:c('October'), EO12:c('November'), ES12:c('December'),
  DA24:f(0,'=SUM(DA18:DA22)'), DE24:f(0,'=SUM(DE18:DE22)'), DI24:f(0,'=SUM(DI18:DI22)'), DM24:f(0,'=SUM(DM18:DM22)'), DQ24:f(0,'=SUM(DQ18:DQ22)'), DU24:f(0,'=SUM(DU18:DU23)'), DY24:f(0,'=SUM(DY18:DY22)'), EC24:f(0,'=SUM(EC18:EC22)'), EG24:f(0,'=SUM(EG18:EG22)'), EK24:f(0,'=SUM(EK18:EK22)'), EO24:f(0,'=SUM(EO18:EO23)'), ES24:f(0,'=SUM(ES18:ES22)'),
  V28:c('Reach (people) 1+'), W28:c(7696785.7), V29:c('Reach (%) 1+'), W29:f(.49,'=W28/$E$7'), V30:c('Reach (people) 2+'), W30:c(5072206.1), V31:c('Reach (%) 2+'), W31:f(.32,'=W30/$E$7'),
  C30:c('Итоговая стоимость, без НДС'), E30:f(4150000.02676,'=SUM(E27:E29)'), C32:c('Итоговая стоимость, с НДС'), E32:f(5063000.0326472,'=SUM(E30:E31)')
};

const summary = {
  '!ref':'A1:D20',
  B4:c('Период кампании (дней)'), D4:f(30,"='Mediaplan 100в1'!CQ18"),
  B13:c('Viewability'), C13:c('Audibility'), C15:c('In-stream: 65%\nOut-stream: 43%'),
  B20:c('слышимости видео роликов, увеличенному размеру плееров')
};
const hybrid = {'!ref':'A1:D20', B9:c('Пользователи Яндекс Маркета, посещали 2-3 разных страниц за последнюю 1 неделю. Ozon'), D16:c('купить на ozon')};
const first = {'!ref':'A1:B3', B2:c('ОФД данные (1+ покупка)')};
const wb = {SheetNames:['Свод','Mediaplan 100в1','Hybrid','First Data'], Sheets:{'Свод':summary,'Mediaplan 100в1':media,Hybrid:hybrid,'First Data':first}};
const rawInfo = {definedNamesTotal:5, definedNames:[{name:'a',ref:'#REF!'},{name:'a',ref:'#REF!'},{name:'b',ref:'#N/A'}], externalLinks:[]};
const r = core.runAllChecks(wb,{rawInfo,brandCard:null,globalExclusions:['CPM','CTR']});

assert(!r.issues.some(x=>x.type==='Формула / период' && x.sheet==='Свод' && x.cell==='D4'),'simple direct reference on summary must not be treated as incomplete period logic');
assert(!r.issues.some(x=>x.type==='Единообразие названий'),'without a brand card capitalization variants must not create platform false positives');
assert(r.issues.some(x=>x.type==='ЦА / логика' && x.sheet==='Mediaplan 100в1' && x.cell==='E18'),'Yandex audience mismatch must be detected');
assert(r.issues.some(x=>x.type==='Логика / контент' && x.sheet==='Свод'),'video-specific summary content without video placements must be detected');
assert(r.issues.some(x=>x.type==='Месячные итоги / SUM' && /DA24/.test(x.cell)),'monthly SUM ranges that exclude an active row must be detected');
assert(r.issues.some(x=>x.type==='Совместимость Excel' && /_xlfn/i.test(`${x.problem} ${x.value}`)),'_xlfn formulas must be detected');
assert(r.issues.some(x=>x.type==='Расчёт охвата / воспроизводимость' && /W28/.test(x.cell)),'manual reach values must be marked as not reproducible');
assert(r.issues.some(x=>x.type==='Точность бюджета'),'hidden fractions beyond kopecks must be detected');
assert(r.issues.some(x=>x.type==='Грамматика' && x.sheet==='Hybrid' && /2–3/.test(x.recommendation)),'2-3 разных страниц grammar issue must be detected');
assert(r.issues.some(x=>x.type==='Грамматика' && x.sheet==='Hybrid' && /последнюю неделю/.test(x.recommendation)),'за последнюю 1 неделю must be detected');
assert(r.issues.some(x=>x.type==='Орфография / оформление' && x.sheet==='First Data'),'ОФД-данные spelling must be detected');

const latent = r.issues.filter(x=>x.type==='Формула Excel' && x.problem==='Формула содержит битую ссылку в неактивной ветке.');
assert(latent.length===1 && /U23/.test(latent[0].cell),'same latent #REF root cause must be grouped');
const names = r.issues.find(x=>x.type==='Именованные диапазоны');
assert(names && /3 битых записей/.test(names.problem) && /2 уникальных/.test(names.problem),'defined names must show raw broken entries and deduplicated count separately');
assert(!r.issues.some(x=>/universe/i.test(x.problem)),'technical reach must never be compared to people universe');

console.log('baseline LAB tests passed', r.counts, 'issues', r.issues.length);
