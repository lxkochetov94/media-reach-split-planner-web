const fs=require('fs'),vm=require('vm');
const app=fs.readFileSync(process.argv[2]||'budget-checker/src/app.js','utf8');
function extract(name){
  const start=app.indexOf(`function ${name}`); if(start<0) throw new Error(`missing ${name}`);
  let i=app.indexOf('{',start),depth=0;
  for(;i<app.length;i++){if(app[i]==='{')depth++;else if(app[i]==='}'&&--depth===0){i++;break;}}
  return app.slice(start,i);
}
const names=['mpNorm','mpBuyingModel','mpCanonicalChannelKey','mpChannelFamily','mpTokenScore','mpDeterministicChannelTarget','mpMatchChannel','mpPlacementTarget','mpAuxChannel','mpAggregateExternal'];
const sandbox={};vm.createContext(sandbox);vm.runInContext(names.map(extract).join('\n')+'\nthis.api={mpMatchChannel,mpAggregateExternal};',sandbox);
const api=sandbox.api;
const channels=[
  ['ОЛВ','Интернет'],['Баннерное размещение CPM','Интернет'],['Баннерное размещение CPC','Интернет'],
  ['Социальные сети CPM','Интернет'],['Социальные сети CPC','Интернет'],
  ['Еком Awareness','E-commerce'],['Еком Performance','E-commerce'],['Блогеры',''],['Промостатьи','Интернет']
].map(([channel,typeMedia])=>({channel,typeMedia,months:Array(12).fill(0)}));
const ctx={channels};
for(const [raw,want] of [
  ['olv','ОЛВ'],['OLV (Герметики+Монтажные клеи)','ОЛВ'],
  ['banners cpm','Баннерное размещение CPM'],['Banners, CPM Герметики','Баннерное размещение CPM'],
  ['banners cpc','Баннерное размещение CPC'],['Banners, CPC Монтажные клеи','Баннерное размещение CPC'],
  ['social cpm','Социальные сети CPM'],['Social nets, CPM Герметики','Социальные сети CPM'],
  ['social cpc','Социальные сети CPC'],['Social nets, CPC Монтажные клеи','Социальные сети CPC'],
  ['Ecom Awareness Герметики','Еком Awareness'],['Ecom Performance Монтажные клеи','Еком Performance'],
  ['Bloggers','Блогеры'],['Promo articles','Промостатьи']
]){
  const got=api.mpMatchChannel(raw,ctx);
  if(!got||got.channel!==want)throw new Error(`${raw}: got ${got&&got.channel}, want ${want}`);
}
const extracted={placements:[
  {section:'OLV (Герметики+Монтажные клеи)',channelKey:'olv',month:0,amount:31818697.84,sheet:'MP',sourceCell:'U18'},
  {section:'Banners, CPM Герметики',channelKey:'banners cpm',month:0,amount:3201715.65,sheet:'MP',sourceCell:'U30'},
  {section:'Banners, CPM Монтажные клеи',channelKey:'banners cpm',month:0,amount:3201715.65,sheet:'MP',sourceCell:'U31'},
  {section:'Banners, CPC Герметики',channelKey:'banners cpc',month:0,amount:4827149,sheet:'MP',sourceCell:'U40'},
  {section:'Banners, CPC Монтажные клеи',channelKey:'banners cpc',month:0,amount:4608337,sheet:'MP',sourceCell:'U41'},
  {section:'Social nets, CPM Герметики',channelKey:'social cpm',month:0,amount:1447979.94,sheet:'MP',sourceCell:'U50'},
  {section:'Social nets, CPM Монтажные клеи',channelKey:'social cpm',month:0,amount:1447979.94,sheet:'MP',sourceCell:'U51'},
  {section:'Social nets, CPC Герметики',channelKey:'social cpc',month:0,amount:1007200,sheet:'MP',sourceCell:'U60'},
  {section:'Social nets, CPC Монтажные клеи',channelKey:'social cpc',month:0,amount:1005550,sheet:'MP',sourceCell:'U61'}
],auxCosts:[]};
const agg=api.mpAggregateExternal(extracted,ctx);
const expected=new Map([
  ['олв',31818697.84],['баннерное размещение cpm',6403431.30],['баннерное размещение cpc',9435486],
  ['социальные сети cpm',2895959.88],['социальные сети cpc',2012750]
]);
for(const [name,want] of expected){
  const row=agg.matched.get(name),got=row?row.months[0]/100:null;
  if(got==null||Math.abs(got-want)>0.001)throw new Error(`${name}: got ${got}, want ${want}`);
}
if(agg.unmapped.size)throw new Error(`unexpected unmapped: ${[...agg.unmapped.keys()].join(', ')}`);
console.log('budget channel matching regression: OK');
