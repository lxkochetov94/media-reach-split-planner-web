const assert = require('assert');
const core = require('../markup-rules.js');

function c(v, extra={}) { return {v, ...extra}; }

const ws = {
  '!ref':'A1:H10',
  A1:c('№'), B1:c('Site'), C1:c('Ad Placement & targetings'), D1:c('Format'), E1:c('Month'), F1:c('Наценка'),
  A2:c(1), B2:c('VK'), C2:c('Ж 18-45'), D2:c('Social'), E2:c('October'), F2:c(1.15),
  A3:c(2), B3:c('ВК'), C3:c('Ж 18-45'), D3:c('Promopost'), E3:c('November'), F3:c(1),
  A4:c(3), B4:c('Яндекс'), C4:c('Аукцион'), D4:c('Яндекс Видео (Multiroll)'), E4:c('October'), F4:c(1.2),
  A5:c(4), B5:c('Yandex'), C5:c('Аукцион'), D5:c('Яндекс Баннеры'), E5:c('November'), F5:c(1),
  A6:c(5), B6:c('Яндекс'), C6:c('Поиск'), D6:c('Search'), E6:c('December'), F6:c(1.1),
};

const wb={SheetNames:['Mediaplan'],Sheets:{Mediaplan:ws}};
const options={rawInfo:{definedNames:[],definedNamesTotal:0,externalLinks:[]},brandCard:null,globalExclusions:[]};
const r=core.runAllChecks(wb,options);

const markupIssues=r.issues.filter(x=>x.type==='Наценка площадки');
assert(markupIssues.some(x=>x.cell==='F2' && /VK/.test(x.problem)), 'VK markup != 1 must be critical');
assert(markupIssues.some(x=>x.cell==='F4' && /Multiroll/.test(x.problem)), 'Yandex Multiroll markup != 1 must be critical');
assert(!markupIssues.some(x=>x.cell==='F3'), 'VK markup 1 must pass');
assert(!markupIssues.some(x=>x.cell==='F5'), 'Yandex Banners markup 1 must pass');
assert(!markupIssues.some(x=>x.cell==='F6'), 'Yandex Search is outside this specific no-markup rule');
assert(markupIssues.every(x=>x.severity===core.SEVERITY.CRITICAL), 'markup violations must be critical');

console.log('markup rules tests passed', markupIssues.map(x=>x.cell));
