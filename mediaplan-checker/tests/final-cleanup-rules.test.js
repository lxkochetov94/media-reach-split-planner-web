const assert = require('assert');
const core = require('../final-cleanup-rules.js');
function c(v, extra={}) { return {v, ...extra}; }

const control = {
  '!ref':'A1:E3',
  A1:c('Тип проверки'), B1:c('Лист / ячейка'), C1:c('Что обнаружено'), D1:c('Что сделано'), E1:c('Статус'),
  A2:c('Текст'), B2:c('Mediaplan 1 флайт!C39'), C2:c('ЭнтузиасткиProgrammatic — пропущен пробел'), D2:c('Исправлено'), E2:c('Исправлено'),
  A3:c('Текст'), B3:c('Mediaplan 1 флайт!C40'), C3:c('ЭнтузиасткиProgrammatic — требует проверки'), D3:c('Не менялось'), E3:c('Требует проверки')
};
const media = {'!ref':'A1:A1', A1:c('ЭнтузиасткиProgrammatic')};
const wb={SheetNames:['Проверка 11.08','Mediaplan 1 флайт'],Sheets:{'Проверка 11.08':control,'Mediaplan 1 флайт':media}};
const r=core.runAllChecks(wb,{rawInfo:{definedNames:[],definedNamesTotal:0,externalLinks:[]},brandCard:null,globalExclusions:[]});

assert(!r.issues.some(x=>x.severity===core.SEVERITY.TEXT && x.sheet==='Проверка 11.08' && x.cell==='C2'), 'historical quoted typo in a Fixed control row must not be linted as a current issue');
assert(r.issues.some(x=>x.severity===core.SEVERITY.TEXT && x.sheet==='Проверка 11.08' && x.cell==='C3'), 'unresolved control-row text should still be visible');
assert(r.issues.some(x=>x.severity===core.SEVERITY.TEXT && x.sheet==='Mediaplan 1 флайт' && x.cell==='A1'), 'same typo in actual media-plan content must remain');
console.log('final cleanup tests passed', r.counts, 'issues', r.issues.length);
