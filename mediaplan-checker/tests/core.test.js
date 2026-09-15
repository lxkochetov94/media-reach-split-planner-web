const assert = require('assert');
const core = require('../core.js');
function c(v, extra={}) { return { v, w:String(v), ...extra }; }
const ws = {
  '!ref':'A1:N9',
  A1:c('Площадка'), B1:c('Impressions'), C1:c('Clicks'), D1:c('CTR'), E1:c('Budget (net)'), F1:c('CPM'), G1:c('Start'), H1:c('End'), I1:c('Days'),
  A2:c('VK'), B2:c(100000), C2:c(1000), D2:c(0.01), E2:c(10000), F2:c(100), G2:c('12.10.2026'), H2:c('18.10.2026'), I2:c(7),
  A3:c('RuTube'), B3:c(100000), C3:c(1000), D3:c(0.2), E3:c(10000), F3:c(100), G3:c('19.10.2026'), H3:c('25.10.2026'), I3:c(7),
  A4:c('Cтирка  порошок '),
  J2:{v:2,f:'=B2/50000',w:'2'}, J3:c(123), J4:{v:4,f:'=B4/50000',w:'4'},
  K2:{v:10000,f:'=SUM(E2:E3)',w:'10000'},
  L2:{v:1,f:"='Missing'!A1",w:'1'},
  M2:{v:1,f:'=IF(A2="x",#REF!,1)',w:'1'},
  N2:c('12.12.2026–30.11.2026')
};
const wb = { SheetNames:['План'], Sheets:{План:ws}, Workbook:{Names:[]} };
const r = core.runAllChecks(wb,{intro:'Убрать Hybrid\nСтарт 12 октября',globalExclusions:['CPM','CTR']});
assert(r.counts.critical >= 3, 'expected critical findings');
assert(r.counts.check >= 2, 'expected check findings');
assert(r.counts.text >= 2, 'expected text findings');
assert(r.issues.some(x=>x.problem.includes('отсутствующий лист')));
assert(r.issues.some(x=>x.problem.includes('Формула содержит #REF!')));
assert(r.issues.some(x=>x.type==='Ручное значение среди формул'));
assert(r.issues.some(x=>x.type==='Смешение алфавитов'));
assert(r.issues.some(x=>x.type==='Период размещения'));
assert(!r.issues.some(x=>/universe/i.test(x.problem)), 'must not compare reach and universe');
console.log('core tests passed', r.counts);
