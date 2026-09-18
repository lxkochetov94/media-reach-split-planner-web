const assert=require('assert');
const core=require('../mediaplan-checker/production-rules.js');
function c(v,extra={}){return {v,...extra};}
const periodFlight={
  '!ref':'A1:V40',
  C13:c('№'),E13:c('Site'),F13:c('Ad Placement & targetings'),J13:c('Период РК'),J14:c('с'),K14:c('по'),
  U13:c('Total cost after discount, RUR'),
  C17:c('Banners, CPM'),
  C18:c(1),E18:c('Hybrid'),J18:c('01.05.2026'),K18:c('30.06.2026'),U18:c(570000),
  C19:c(2),E19:c('BetweenX'),J19:c('01.05.2026'),K19:c('31.05.2026'),U19:c(100000),
  A32:c('Счетчик TNS'),B32:c(30000),
  A33:c('Агентская комиссия'),B33:c(15000),
  A34:c('Скидка'),B34:c(5000),
  A35:c('Платное исследование'),B35:c(7000),
  A36:c('Производство креативов'),B36:c(12000)
};
const wb={SheetNames:['Mediaplan 1 флайт'],Sheets:{'Mediaplan 1 флайт':periodFlight}};
const x=core.extractBudgetPlacements(wb);
assert(x.detectedSheets.includes('Mediaplan 1 флайт'),'period sheet must be detected');
const hybrid=x.placements.find(p=>p.site==='Hybrid');
assert(hybrid,'Hybrid placement missing');
assert.strictEqual(hybrid.month,null,'two-month period must not be forced into one month');
assert.deepStrictEqual(Array.from(hybrid.periodMonths),[4,5],'May-June period months expected');
assert.strictEqual(hybrid.periodStart,'2026-05-01');
assert.strictEqual(hybrid.periodEnd,'2026-06-30');
assert.strictEqual(hybrid.amount,570000);
const between=x.placements.find(p=>p.site==='BetweenX');
assert.strictEqual(between.month,4,'single-month period should resolve to May');
assert.deepStrictEqual(Array.from(between.periodMonths),[4]);
const byKind=Object.fromEntries(x.technicalCosts.map(t=>[t.kind,t]));
assert.strictEqual(byKind.tns.signedAmount,30000);
assert.strictEqual(byKind.agency_commission.signedAmount,15000);
assert.strictEqual(byKind.discount.signedAmount,-5000);
assert.strictEqual(byKind.research.signedAmount,7000);
assert.strictEqual(byKind.creative_production.signedAmount,12000);
assert(!x.issues.some(i=>i.code==='MONTH_NOT_RECOGNIZED'),'period layout must not require Month column');
assert.strictEqual(core.__labBudgetExtractorVersion,'2-periods-tech');
console.log('period budget parser + technical adjustments: OK');
