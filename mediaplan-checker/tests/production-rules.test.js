const assert = require('assert');
const core = require('../production-rules.js');

function c(v, extra={}) { return {v, ...extra}; }
function f(v, formula, extra={}) { return {v, f:formula, ...extra}; }
function err(code, shown, formula) { return {t:'e', v:code, w:shown, ...(formula ? {f:formula} : {})}; }

const budget = {
  '!ref':'A1:F10',
  C2:c('1 флайт (сен-окт)'), E2:c('2 флайт (ноя-дек)'),
  C3:c('Бюджет'), D3:c('Охват, UU'), E3:c('Бюджет'), F3:c('Охват, UU'),
  B4:c('OLV'), C4:c('-'), D4:c('-'), E4:c('-'), F4:c('-'),
  B5:c('Banners, CPM'), C5:c(100), E5:c(200),
  C10:f(100,'SUM(C4:C9)'), D10:f(81,'SUM(D4:D9)*0.81'), E10:f(200,'SUM(E4:E9)')
};

const flight2 = {
  '!ref':'A1:AG30',
  C13:c('№'), E13:c('Site'), F13:c('Ad Placement & targetings'), G13:c('Ad size (pixels) / Format'), H13:c('Video details'), I13:c('Unit type'), K13:c('Month'),
  Q13:c('CPM incl. discount'), R13:c('Total cost after discount, RUR'), U13:c('Total cost + adserving, RUR'),
  V14:c('Impressions'), X14:c('Reach UU'), Y14:c('Frequency'), Z14:c('CPT'), AA14:c('CTR%'), AB14:c('Clicks'), AC14:c('CPC'), AD14:c('Completed views 100%'), AE14:c('Planning VTR % (100%)'), AF14:c('CPV (100%)'),
  AG13:c('January'), AG14:c('01.01'), AG15:c('04.01'),

  C17:c('OLV'),
  C18:c(1), E18:c('Digital Alliance VideoNet'), F18:c('Ж 18-34'), G18:c('Multi-roll In-stream 90%, Out-stream 10%'), H18:c(20), I18:c('1000 imp.'), K18:c('November'), R18:f(319534.11,'L18*M18'),
  V18:err(29,'#NAME?','IFERROR(IF($I18="views",#REF!/#REF!,L18*1000),"-")'),
  C19:c(2), E19:c('Digital Alliance VideoNet'), F19:c('Ж 18-34'), G19:c('Multi-roll In-stream 90%, Out-stream 10%'), H19:c(20), I19:c('1000 imp.'), K19:c('December'), R19:f(668402.7,'L19*M19'),
  V19:err(29,'#NAME?','IFERROR(IF($I19="views",#REF!/#REF!,L19*1000),"-")'),

  C25:c('Banners, CPM'),
  C26:c(3), E26:c('Hybrid'), F26:c('Ж 18-29'), G26:c('Баннеры'), H26:c('-'), I26:c('1000 imp.'), K26:c('November'),
  Q26:f(60,'M26*(1-P26)'), U26:f(300000,'R26+T26'), AA26:c(0.001), AE26:c(0.7),
  C27:c(4), E27:c('Hybrid'), F27:c('Ж 18-29'), G27:c('Баннеры'), H27:c('-'), I27:c('1000 imp.'), K27:c('December'),
  Q27:c(60), U27:c(462834.49147), AA27:c(0.001), AE27:c(0.7)
};

const summary = {
  '!ref':'A1:H12',
  D5:err(29,'#NAME?','SUM(D9:D10)'),
  D9:err(29,'#NAME?','1+1'), D10:err(29,'#NAME?','2+2'),
  G1:err(23,'#REF!')
};

const math = {
  '!ref':'A1:B3',
  B1:c(10), B2:c(20), B3:f(31,'SUM(B1:B2)')
};

const control = {
  '!ref':'A1:E3',
  A1:c('Тип проверки'), B1:c('Лист / ячейка'), C1:c('Что обнаружено'), D1:c('Что сделано'), E1:c('Статус'),
  A2:c('Формулы'), B2:c('Mediaplan 2 флайт!V18:V19'), C2:c('Битые ссылки #REF!'), D2:c('Восстановлена логика'), E2:c('Исправлено')
};

const byyd = {
  '!ref':'A1:E30',
  E3:c('https://play.google.com/store/apps/details?id=com.mobile.legends'),
  D25:c('Mobile Legends: Bang Bang'),
  A5:c('Привет,мир')
};

const wb = {
  SheetNames:['Budget channels','Свод','Mediaplan 2 флайт','Math','Проверка 11.08','BYYD'],
  Sheets:{'Budget channels':budget,'Свод':summary,'Mediaplan 2 флайт':flight2,'Math':math,'Проверка 11.08':control,'BYYD':byyd}
};

const options={rawInfo:{definedNames:[],definedNamesTotal:0,externalLinks:[]},brandCard:null,globalExclusions:[]};
const r=core.runAllChecks(wb,options);

// Cached formula errors are not proof of a current error; literal errors and broken formula text remain.
assert(!r.issues.some(x=>x.type==='Ошибка Excel' && x.sheet==='Свод' && ['D5','D9','D10'].includes(x.cell)), 'formula error caches must not be emitted as Excel errors');
assert(!r.issues.some(x=>x.type==='Проверка суммы' && x.sheet==='Свод' && x.cell==='D5'), 'numeric Excel error code must never be compared as SUM result');
assert(r.issues.some(x=>x.type==='Ошибка Excel' && x.sheet==='Свод' && x.cell==='G1'), 'literal #REF cell without formula must remain an error');
assert(r.issues.some(x=>x.type==='Формула Excel' && x.sheet==='Mediaplan 2 флайт' && /V18/.test(x.cell)), 'literal #REF inside formula must remain critical');

// Proven arithmetic error still stays critical.
assert(r.issues.some(x=>x.severity===core.SEVERITY.CRITICAL && x.type==='Проверка суммы' && x.sheet==='Math' && x.cell==='B3'), 'real 31 vs 10+20 arithmetic mismatch must remain critical');

// No phantom Defined Names when workbook.xml has no defined names.
assert(!r.issues.some(x=>x.type==='Именованные диапазоны'), 'zero defined names must produce zero Defined Names warnings');

// Same SUM rows with an extra multiplier are not a range mismatch.
assert(!r.issues.some(x=>x.type==='Диапазон SUM' && x.sheet==='Budget channels' && x.cell==='D10'), 'same row boundaries must not be flagged as SUM range anomaly');

// Technical strings are not prose, but real punctuation errors remain.
assert(!r.issues.some(x=>x.type==='Пунктуация' && x.sheet==='BYYD' && x.cell==='E3'), 'URL must not be linted as prose punctuation');
assert(!r.issues.some(x=>x.type==='Пунктуация' && x.sheet==='Проверка 11.08' && x.cell==='B2'), 'Excel range reference must not be linted as prose punctuation');
assert(!r.issues.some(x=>x.type==='Повтор слова' && x.sheet==='BYYD' && x.cell==='D25'), 'intentional title Bang Bang must not be treated as duplicate word');
assert(r.issues.some(x=>x.type==='Пунктуация' && x.sheet==='BYYD' && x.cell==='A5'), 'normal prose punctuation error must still be detected');

// Missing channel budget is a proven cross-sheet inconsistency.
assert(r.issues.some(x=>x.severity===core.SEVERITY.CRITICAL && x.type==='Сверка бюджета по каналам' && x.sheet==='Budget channels' && x.cell==='E4'), 'OLV exists in flight 2, so Budget channels E4 dash must be critical');
assert(!r.issues.some(x=>x.type==='Сверка бюджета по каналам' && x.sheet==='Budget channels' && x.cell==='C4'), 'flight 1 without OLV must be allowed to show dash');

// Formula-to-hardcode risk is restored and points to exact derived cells only.
const pair=r.issues.find(x=>x.type==='Парные строки / формулы' && x.sheet==='Mediaplan 2 флайт' && /Hybrid/.test(x.value));
assert(pair && /Q27/.test(pair.cell) && /U27/.test(pair.cell), 'paired monthly hardcodes must be found at exact cells');
assert(!/AA27|AE27/.test(pair.cell), 'manual CTR/VTR inputs must not be treated as formula hardcodes');

// Control sheet must not say Fixed while referenced formulas still contain #REF.
assert(r.issues.some(x=>x.type==='Контрольный лист / статус' && x.sheet==='Проверка 11.08' && x.cell==='B2'), 'control sheet status contradiction must be shown');

console.log('production Taft reliability tests passed',r.counts,'issues',r.issues.length);
