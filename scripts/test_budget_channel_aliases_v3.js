const fs=require('fs'),vm=require('vm');
const app=fs.readFileSync(process.argv[2]||'budget-checker/src/app.js','utf8');
function extract(name){const start=app.indexOf('function '+name+'(');if(start<0)throw new Error('missing '+name);let i=app.indexOf('{',start),d=0;for(;i<app.length;i++){if(app[i]==='{')d++;else if(app[i]==='}'&&--d===0){i++;break;}}return app.slice(start,i)}
const names=['mpNorm','mpBuyingModel','mpCanonicalChannelKey','mpChannelFamily','mpTokenScore','mpDeterministicChannelTarget','mpMatchChannel','mpPlacementTarget','mpAuxChannel','mpAggregateExternal'];
const sb={};vm.createContext(sb);vm.runInContext(names.map(extract).join('\n')+';this.api={mpCanonicalChannelKey,mpMatchChannel,mpPlacementTarget,mpAggregateExternal};',sb);
const ctx={channels:[
 {channel:'Социальные сети CPM',typeMedia:'Интернет',months:Array(12).fill(0)},
 {channel:'Социальные сети CPC',typeMedia:'Интернет',months:Array(12).fill(0)},
 {channel:'Баннерное размещение CPM',typeMedia:'Интернет',months:Array(12).fill(0)},
 {channel:'Баннерное размещение СPC',typeMedia:'Интернет',months:Array(12).fill(0)}
]};
for(const raw of ['Social nets, CPC Герметики','Social nets, СРС Герметики','social cpc']){
 const got=sb.api.mpMatchChannel(raw,ctx); if(!got||got.channel!=='Социальные сети CPC')throw new Error(raw+' => '+(got&&got.channel));
}
const banner=sb.api.mpMatchChannel('Banners, CPC Герметики',ctx);
if(!banner||banner.channel!=='Баннерное размещение СPC')throw new Error('mixed Cyrillic/Latin banner CPC failed');
for(const p of [
 {section:'Social nets, CPC Герметики',channelKey:'',site:'x'},
 {section:'Social nets, CPC Герметики',channelKey:'garbage',site:'x'},
 {section:'Social nets, СРС Монтажные клеи',channelKey:'',site:'x'}
]){
 const got=sb.api.mpPlacementTarget(p,ctx); if(!got||got.channel!=='Социальные сети CPC')throw new Error('placement fallback failed '+JSON.stringify(p));
}
const ext={placements:[
 {section:'Social nets, CPC Герметики',channelKey:'',month:0,amount:1007200,sheet:'MP',sourceCell:'U1'},
 {section:'Social nets, СРС Монтажные клеи',channelKey:'garbage',month:0,amount:1005550,sheet:'MP',sourceCell:'U2'}
],auxCosts:[]};
const agg=sb.api.mpAggregateExternal(ext,ctx),row=agg.matched.get('социальные сети cpc');
if(!row||Math.abs(row.months[0]/100-2012750)>0.001)throw new Error('aggregate failed');
if(agg.unmapped.size)throw new Error('Social CPC remained unmapped: '+[...agg.unmapped.keys()].join(', '));
console.log('deterministic LAB channel aliases v3: OK');
