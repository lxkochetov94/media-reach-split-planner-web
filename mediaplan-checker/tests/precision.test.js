const assert = require('assert');
const core = require('../precision.js');
function c(v, extra={}) { const o={v,...extra}; if(extra.w===undefined && typeof v==='string') o.w=v; return o; }
function f(v, formula, extra={}) { return {v, f:formula, w:String(v), ...extra}; }

const flight2 = {
  '!ref':'A1:CR20', F3:c("Вернель Гранулы Август-Сентябрь'26"), F5:c('08.08.2026-08.09.2026'), F6:c('Ж 25-35 ВС'), F7:c(7333270),
  A12:c('Площадка'), B12:c('Month'), C12:c('Impressions'), D12:c('Clicks'), E12:c('CTR'), F12:c('Budget (net)'), G12:c('CPM'), H12:c('Reach'), I12:c('Frequency'), J12:c('Views'), K12:c('VTR'),
  A18:c('Digital Alliance'), B18:c('August'), L18:c('OLV'), M18:c('1000 imp.'), N18:c('Ж 25-45'), C18:f(100000,'=M18*1000'), D18:f(1000,'=C18*E18'), E18:f(0.01,'=D18/C18'), F18:f(10000,'=C18/1000*G18'), G18:f(100,'=F18/C18*1000'), H18:c(25000), I18:f(4,'=C18/H18'), J18:f(80000,'=C18*K18'), K18:f(0.8,'=J18/C18'),
  A19:c('Digital Alliance'), B19:c('September'), L19:c('OLV'), M19:c('1000 imp.'), N19:c('Ж 25-45'), C19:c(110000), D19:c(1100), E19:c(0.01), F19:c(11000), G19:c(100), H19:c(27500), I19:c(4), J19:c(88000), K19:c(0.8),
  S15:c('Cost per unt'), CL14:c('23.11'), CM14:c('30.08'), CN14:c('07.12'), CO14:c('14.12'),
  BR14:c('02.08'), BS14:c('09.08'), BT14:c('16.08'), BU14:c('23.08'), BV14:c('30.08'), BW14:c('06.09'), BX14:c('13.09'),
  BR18:c(1), BS18:c(7), BT18:c(7), BU18:c(7), BV18:c(1), BW18:c(0), BX18:c(0), CR18:f(23,'=SUM(BR18:BX18)'),
  BR19:c(0), BS19:c(0), BT19:c(0), BU19:c(0), BV19:c(2), BW19:c(6), BX19:c(0), CR19:f(8,'=SUM(BR19:BX19)'),
  V18:f(100000,'=IF(A18="x",#REF!/#REF!,100000)'), V19:f(110000,'=IF(A19="x",#REF!/#REF!,110000)')
};
const flight3 = {
  '!ref':'A1:CS22', F3:c("Вернель Гранулы Октябрь-Ноябрь'26"), F5:c('12.10.2026-30.11.2026'), F6:c('Ж 25-45 ВС'), F7:c(15182450),
  A12:c('Площадка'), B12:c('Month'), C12:c('Impressions'), D12:c('Clicks'), E12:c('CTR'), F12:c('Budget (net)'), G12:c('CPM'), H12:c('Reach'), I12:c('Frequency'),
  A18:c('VK'), B18:c('October'), C18:f(100000,'=M18*1000'), D18:f(1000,'=C18*E18'), E18:f(0.01,'=D18/C18'), F18:f(10000,'=C18/1000*G18'), G18:f(100,'=F18/C18*1000'), H18:c(25000), I18:f(4,'=C18/H18'),
  A19:c('VK'), B19:c('November'), C19:f(150000,'=M19*1000'), D19:f(1500,'=C19*E19'), E19:f(0.01,'=D19/C19'), F19:f(15000,'=C19/1000*G19'), G19:f(100,'=F19/C19*1000'), H19:c(37500), I19:f(4,'=C19/H19'),
  T18:f(2.2,'=_xlfn.IFS(K18="code",2.2,K18="click",0)'), T19:f(2.2,'=_xlfn.IFS(K19="code",2.2,K19="click",0)'),
  CE14:c('12.10'), CF14:c('19.10'), CG14:c('26.10'), CH14:c('02.11'), CI14:c('09.11'), CJ14:c('16.11'), CK14:c('23.11'), CL14:c('30.11'),
  CE15:c('18.10'), CF15:c('25.10'), CG15:c('31.10'), CH15:c('08.11'), CI15:c('15.11'), CJ15:c('22.11'), CK15:c('29.11'), CL15:c('06.12'),
  CE18:c(7), CF18:c(7), CG18:c(7), CH18:c(0), CI18:c(0), CJ18:c(0), CK18:c(0), CL18:c(0), CS18:f(21,'=SUM(CE18:CL18)'),
  CE19:c(0), CF19:c(0), CG19:c(0), CH19:c(8), CI19:c(7), CJ19:c(7), CK19:c(7), CL19:c(1), CS19:f(30,'=SUM(CE19:CL19)'),
  CM14:c('23.11'), CN14:c('30.08'), CO14:c('07.12'), CP14:c('14.12'),
  CP15:f('21.12','=TEXT(DAY(DATEVALUE(LEFT(CO14,5))+7),"00")&"."&TEXT(MONTH(DATEVALUE(LEFT(CO14,5))+7),"00")'),
  CQ15:f('28.12','=TEXT(DAY(DATEVALUE(LEFT(CP14,5))+7),"00")&"."&TEXT(MONTH(DATEVALUE(LEFT(CP14,5))+7),"00")', {c:[{t:'АУДИТ — риск переносимости'}]})
};
const summary = {'!ref':'A1:D5', A2:c('Начало'), B2:c('01.04.2026'), A3:c('Конец'), B3:c('30.11.2026'), A4:c('Период кампании (дней)'), D4:f(143,"='3 флайт'!CS18+91+'2 флайт'!CR18+'2 флайт'!CR19")};
const text = {'!ref':'A1:D8', A1:c('Cтирка'), A2:c('Показы /\n План'), A3:c('CPC /  \nПлан'), A4:c('12,000,000'), A5:c('стойки кондиционер для белья'), A6:c('Пользователи выбирают размещения. Качество размещений повышается, поэтому стоимость размещения выше. Дополнительные размещения также требуют контроля.'), B1:c(26731,{w:'26,731 '}), B2:c(0,{w:'0 '}), C1:c('VK; VK; Hybrid'), D1:c('Лайм HD TV\u00A0')};
const hidden = {'!ref':'A1:G46', F3:c("Вернель Гранулы Апрель-Июнь'26"), F6:c('Ж 25-45 ВС'), '!rows':Array.from({length:46},(_,i)=> i>=39 ? {hidden:true}:{}), G40:{t:'e',v:23,w:'#REF!',f:'=#REF!'}, G41:{t:'e',v:23,w:'#REF!',f:'=#REF!'}, G42:{t:'e',v:23,w:'#REF!',f:'=#REF!'}, G43:{t:'e',v:23,w:'#REF!',f:'=#REF!'}, G44:{t:'e',v:23,w:'#REF!',f:'=#REF!'}, G45:{t:'e',v:23,w:'#REF!',f:'=#REF!'}, G46:{t:'e',v:23,w:'#REF!',f:'=#REF!'}};
const wb={SheetNames:['Свод','2 флайт','3 флайт','Текст','1 флайт'],Sheets:{'Свод':summary,'2 флайт':flight2,'3 флайт':flight3,'Текст':text,'1 флайт':hidden}};
const rawInfo={definedNamesTotal:30249,definedNames:Array.from({length:10},(_,i)=>({name:'x'+i,ref:i<4?'#REF!':i<8?'#N/A':'#NAME?'})),externalLinks:['file:///LAB/Лоск Детская линейка.xlsx']};
const r=core.runAllChecks(wb,{rawInfo,intro:'Перенести бюджет Core в Гранулы. Размещение растянуть на 2 месяца. Прописать аргументы, почему не стоит растягивать на 3 месяца.',globalExclusions:['CPM','CTR']});

assert(!r.issues.some(x=>x.sheet==='Текст' && ['B1','B2'].includes(x.cell) && x.type==='Пробелы'),'formatted numbers must not be text findings');
assert(!r.issues.some(x=>x.sheet==='Текст' && x.cell==='A2' && x.problem.includes('двойные')),'line break must not create fake double space');
assert(r.issues.some(x=>x.sheet==='Текст' && x.cell==='A3' && x.type==='Пробелы'),'real double spaces must be found');
assert(!r.issues.some(x=>x.sheet==='Текст' && x.cell==='A4' && x.type==='Дубли таргетинга/ключевых слов'),'number must not be parsed as duplicate list');
assert(r.issues.some(x=>x.sheet==='2 флайт' && x.cell==='S15' && (x.problem+x.recommendation).includes('Cost per unit')),'Cost per unt typo');
assert(r.issues.some(x=>x.sheet==='Текст' && x.cell==='A5' && (x.problem+x.recommendation).includes('стойкий кондиционер')),'стойки typo');
assert(r.issues.some(x=>x.sheet==='Текст' && x.cell==='A1' && x.type==='Смешение алфавитов'));
assert(r.issues.some(x=>x.sheet==='Текст' && x.cell==='A6' && x.type==='Возможная тавтология'));
assert(r.issues.some(x=>x.sheet==='Текст' && x.cell==='D1' && x.problem.includes('неразрывный')));
assert(r.issues.some(x=>x.sheet==='Текст' && x.cell==='C1' && x.type==='Дубли таргетинга/ключевых слов'));
const hiddenRef=r.issues.filter(x=>x.sheet==='1 флайт' && x.type==='Формула Excel');
assert(hiddenRef.length===1 && hiddenRef[0].cell==='G40:G46' && hiddenRef[0].severity===core.SEVERITY.CHECK,'hidden ref errors must group and not inflate critical count');
const latent=r.issues.filter(x=>x.sheet==='2 флайт' && x.type==='Формула Excel' && /V18/.test(x.cell));
assert(latent.length===1 && latent[0].severity===core.SEVERITY.CHECK,'latent formula errors should be review, not critical');
assert(r.issues.some(x=>x.type==='Совместимость Excel' && x.sheet==='3 флайт' && x.problem.includes('2 формул')),'xlfn grouped');
assert(r.issues.some(x=>x.type==='Формулы дат' && x.sheet==='3 флайт'),'DATEVALUE without year');
assert(r.issues.some(x=>x.type==='Служебные комментарии' && x.sheet==='3 флайт'),'audit comments');
assert(r.issues.some(x=>x.type==='ЦА / логика' && x.sheet==='2 флайт'),'audience inconsistency');
assert(r.issues.some(x=>x.type==='Связанные ячейки' && x.sheet==='2 флайт'),'paired hardcodes');
assert(r.issues.some(x=>x.type==='Календарь размещения' && x.sheet==='2 флайт' && x.problem.includes('(23)')),'flight2 day mismatch');
assert(r.issues.some(x=>x.type==='Календарь размещения' && x.sheet==='3 флайт' && x.problem.includes('(21)')),'flight3 October day mismatch');
assert(r.issues.some(x=>x.type==='Календарь' && x.sheet==='2 флайт' && x.cell==='CM14'),'30.08 wrong month flight2');
assert(r.issues.some(x=>x.type==='Календарь' && x.sheet==='3 флайт' && x.cell==='CN14'),'30.08 wrong month flight3');
assert(r.issues.some(x=>x.type==='Формула / период' && x.sheet==='Свод' && x.cell==='D4' && x.problem.includes('не все')),'summary period incomplete');
assert(r.issues.some(x=>x.type==='Формула / период' && x.sheet==='Свод' && x.cell==='D4' && x.problem.includes('константа')),'summary hardcoded constant');
assert(r.issues.some(x=>x.type==='Именованные диапазоны' && /10/.test(x.problem)));
assert(r.issues.some(x=>x.type==='Внешние связи книги' && /1/.test(x.problem)));
assert(r.introResults.some(x=>x.sentence.includes('Перенести') && x.status==='Требует проверки'));
assert(r.introResults.some(x=>x.sentence.includes('аргументы') && x.status==='Не найдено'));
assert(!r.issues.some(x=>x.type==='Математика медиаплана' && x.sheet==='3 флайт' && ['E18','G18','I18'].includes(x.cell)));
assert(!r.issues.some(x=>/universe/i.test(x.problem)),'must never compare technical reach with people universe');
console.log('precision tests passed',r.counts,'issues',r.issues.length);
