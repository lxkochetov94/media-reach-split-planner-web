const assert = require('assert');
require('../hardening-text-rules.js');
require('../reliability-rules.js');
const core = require('../audit-polish-rules.js');

function c(v, extra={}) { return {v, ...extra}; }
function f(v, formula, extra={}) { return {v, f:formula, ...extra}; }

const summary = {
  '!ref':'A1:H30',
  B2:c('Дата старта кампании'), D2:f(46174,"'Mediaplan 1 флайт'!K17"),
  B3:c('Дата окончания кампании'), D3:f(46371,"'Mediaplan 3 флайт'!CV19"),
  B4:c('Период кампании (дней)'), D4:f(134,"44+'Mediaplan 3 флайт'!CS19"),
  B22:c('Размещения 2026 года нацелены на повышение качества контакта. Это достигается благодаря более высокой видимости  креативов, слышимости видео роликов. Увеличение качества размещений влияет на стоимость, поэтому размещения 2026 года дороже.')
};

const flight1 = {
  '!ref':'A1:L30',
  C13:c('№'), E13:c('Site'), L13:c('Month'),
  E17:c('VK Video'), L17:c('July'), K17:c('01.07.2026')
};

const flight3 = {
  '!ref':'A1:CV30',
  C13:c('№'), E13:c('Site'), L13:c('Month'),
  E18:c('Digital Alliance'), L18:c('November'), CS18:c(30), CV18:c('30.11.2026'),
  E19:c('Digital Alliance'), L19:c('December'), CS19:c(15), CV19:c('15.12.2026')
};

const wb = {
  SheetNames:['Свод','Mediaplan 1 флайт','Mediaplan 3 флайт'],
  Sheets:{'Свод':summary,'Mediaplan 1 флайт':flight1,'Mediaplan 3 флайт':flight3}
};
const r = core.runAllChecks(wb,{rawInfo:{definedNames:[],definedNamesTotal:0,externalLinks:[]},brandCard:null,globalExclusions:[]});

assert(!r.issues.some(x=>x.type==='Свод / период кампании' && x.sheet==='Свод' && x.cell==='D3'),
  'Дата окончания D3 не должна проверяться как длительность кампании из-за соседнего B4');
assert(r.issues.some(x=>x.type==='Свод / период кампании' && x.sheet==='Свод' && x.cell==='D4'),
  'Настоящая ячейка периода D4 должна сохранять проверку покрытия месяцев');

const video = r.issues.filter(x=>x.sheet==='Свод' && x.cell==='B22' && /видео\s+ролик|видеоролик/iu.test(`${x.problem||''} ${x.recommendation||''}`));
assert.strictEqual(video.length,1,'«видео роликов» должно давать ровно одно отдельное замечание, даже если в ячейке есть двойные пробелы');

const tautology = r.issues.filter(x=>x.sheet==='Свод' && x.cell==='B22' && x.type==='Возможная тавтология' && /размещ/iu.test(String(x.problem||'')));
assert.strictEqual(tautology.length,1,'Повтор «размещ…» должен сохраняться как отдельная тавтология и не поглощаться замечанием про пробелы');

assert(r.issues.some(x=>x.sheet==='Свод' && x.cell==='B22' && x.type==='Пробелы'),
  'Техническое замечание про двойные пробелы тоже должно остаться отдельной первопричиной');

console.log('audit polish Laska tests passed', r.counts, 'issues', r.issues.length);
