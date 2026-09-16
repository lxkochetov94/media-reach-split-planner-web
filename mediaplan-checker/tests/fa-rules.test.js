const assert = require('assert');
const core = require('../audit-policy-rules.js');
function c(v, extra={}) { return {v, ...extra}; }
function f(v, formula, extra={}) { return {v, f:formula, ...extra}; }

const ws = {
  '!ref':'A1:DI60',
  I3:c('Campain name:'), I6:c('Period'), J6:c('19.08.2026-15.09.2026'),
  W14:c('Budget (net)'), AN14:c('CR % (Convertion Rate)'), AO14:c('Convertions / Actions'), DI13:c('Run period'),
  O20:c('September'), DI20:f(14,'SUM(AX20:DH20)'),
  O21:c('September'), DI21:c(15),
  O22:c('August'), DI22:f(15,'SUM(AX22:DH22)'),
  O24:c('September'), DI24:f(14,'SUM(AX24:DH24)'),
  O25:c('August'), K25:c('Multi-roll\nIn-stream 75%/Out-sream 25%'), DI25:f(15,'SUM(AX25:DH25)'),
  W21:c(557154.29399999999), W31:c(639341.65739999991), W35:c(294738.04499999998), W36:f(5686405.9864,'SUM(W17:W35)'),
  AK36:f(0.3226085,'IFERROR(SUMIF(AG17:AH25,">0",W17:W25)/AG36,"-")'),
  DS17:f('-', 'IFERROR(VLOOKUP($E17,#REF!,2,0),"-")'),
  A38:c(''), B38:c(0), C38:f(0,'1-1'),
  A39:c(''), B39:c(0), C39:f(0,'2-2'),
};
const vk = {'!ref':'A1:K10', J2:c('Пор трет аудитории')};
const wb={SheetNames:['MP_02.09_approved','VK'],Sheets:{'MP_02.09_approved':ws,'VK':vk}};
const r=core.runAllChecks(wb,{rawInfo:{definedNames:[],definedNamesTotal:0,externalLinks:[]},brandCard:null,globalExclusions:[]});

assert(r.issues.some(x=>x.severity===core.SEVERITY.CRITICAL && x.cell==='AK36' && x.type==='Формула / размерность диапазонов'),'AK36 с SUMIF разной размерности должен оставаться критической арифметической ошибкой');
for (const addr of ['DI20','DI22','DI24','DI25']) assert(r.issues.some(x=>x.cell===addr&&x.type==='Календарь размещения'),`${addr} должен проверяться календарём`);
assert(!r.issues.some(x=>x.type==='Возможный дубль' && /38|39/.test(String(x.value||''))),'Строки с разными формулами не должны считаться дублем только по одинаковым значениям');
for (const [cell,bad] of [['I3','Campain'],['AN14','Convertion'],['AO14','Convertions'],['K25','Out-sream']]) assert(r.issues.some(x=>x.cell===cell&&x.type==='Очевидная опечатка'&&String(x.problem).includes(bad)),`${bad} должен находиться как опечатка`);
assert(r.issues.some(x=>x.sheet==='VK'&&x.cell==='J2'&&x.type==='Очевидная опечатка'),'«Пор трет аудитории» должен находиться');
assert(!r.issues.some(x=>x.type==='Точность бюджета'),'Скрытая дробная точность и формат округления не должны попадать в аудит');
const ref=r.issues.find(x=>x.sheet==='MP_02.09_approved'&&x.cell==='DS17'&&x.type==='Формула Excel');
assert(ref && /маскируется IFERROR/.test(ref.problem),'#REF внутри выполняемого VLOOKUP должен описываться как маскируемая IFERROR ошибка');
console.log('FA audit policy tests passed',r.counts);
