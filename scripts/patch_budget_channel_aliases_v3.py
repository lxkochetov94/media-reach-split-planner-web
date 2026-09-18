from pathlib import Path
import re
import sys

path=Path(sys.argv[1] if len(sys.argv)>1 else "budget-checker/src/app.js")
app=path.read_text(encoding="utf-8")

canonical="""function mpBuyingModel(v){const s=mpNorm(v);if(/(?:^|\\s)[cс][pр][cс](?:\\s|$)/u.test(s)||/cpc/u.test(s))return'cpc';if(/(?:^|\\s)[cс][pр][mм](?:\\s|$)/u.test(s)||/cpm/u.test(s))return'cpm';return'';}
function mpCanonicalChannelKey(v){const s=mpNorm(v),model=mpBuyingModel(s);if(/(^|\\s)(olv|олв)($|\\s)|online video|онлайн видео/u.test(s))return'olv';if(/banner|баннер/u.test(s))return model?'banners '+model:'banners';if(/social|соц(?:иальн)?/u.test(s))return model?'social '+model:'social';if(/rich media|mobile/u.test(s))return model?'rich media '+model:'rich media';if(/ecom|e-commerce|ecommerce|еком|ритейл|retail/u.test(s)){if(/awareness|охват/u.test(s))return'ecom awareness';if(/performance|перформанс/u.test(s))return'ecom performance';return'ecom';}if(/blogger|bloggers|блогер|инфлюенс/u.test(s))return'blogger';if(/promo.?article|промо.?стат|нативн.*стат|native article/u.test(s))return'promoarticles';if(/native|натив/u.test(s))return'native';if(/search|контекст|директ|рся/u.test(s))return'context';if(/(^|\\s)(tv|тв)(\\s|$)|телевид/u.test(s))return'tv';if(/verification|верификац|brand safety|viewability|support|сопровожд|monitoring|мониторинг/u.test(s))return'verification';return'';}"""
app,n=re.subn(r"function mpCanonicalChannelKey\(v\)\{.*?\}\nfunction mpChannelFamily",lambda m: canonical+"\nfunction mpChannelFamily",app,count=1,flags=re.S)
if n!=1: raise SystemExit("canonical channel function not patched")

matcher="""function mpDeterministicChannelTarget(raw,ctx){const key=mpCanonicalChannelKey(raw);if(!key)return null;const hits=ctx.channels.filter(c=>mpCanonicalChannelKey(c.channel)===key);return hits.length===1?hits[0]:null;}
function mpMatchChannel(raw,ctx){const direct=mpDeterministicChannelTarget(raw,ctx);if(direct)return direct;const n=mpNorm(raw),key=mpCanonicalChannelKey(raw),family=mpChannelFamily(raw),scored=ctx.channels.map(c=>{const cn=mpNorm(c.channel),ck=mpCanonicalChannelKey(c.channel),cf=mpChannelFamily(c.channel);let score=0;if(key&&ck&&key===ck)score=120;else if(n&&n===cn)score=110;else if(n.length>3&&cn.length>3&&(n.includes(cn)||cn.includes(n)))score=90;else if(family&&family===cf&&family.length)score=70;else score=Math.round(mpTokenScore(raw,c.channel)*60);return{c,score,key:ck};}).sort((a,b)=>b.score-a.score);if(!scored.length||scored[0].score<45)return null;if(scored[1]&&scored[1].score===scored[0].score)return null;return scored[0].c;}
function mpPlacementTarget(p,ctx){const values=[p&&p.channelKey,p&&p.section,p&&p.site].filter(Boolean);for(const v of values){const direct=mpDeterministicChannelTarget(v,ctx);if(direct)return direct;}for(const v of values){const fuzzy=mpMatchChannel(v,ctx);if(fuzzy)return fuzzy;}return null;}"""
app,n=re.subn(r"function mpMatchChannel\(raw,ctx\)\{.*?\}\nfunction mpAuxChannel",lambda m: matcher+"\nfunction mpAuxChannel",app,count=1,flags=re.S)
if n!=1: raise SystemExit("channel matcher not patched")

old="matchValue=p.channelKey||p.section||p.site||'',target=mpMatchChannel(matchValue,ctx)"
if old not in app: raise SystemExit("placement target anchor not found")
app=app.replace(old,"target=mpPlacementTarget(p,ctx)",1)

marker="/* Budget comparison exclusions v1 */"
if marker in app and "/* Deterministic LAB channel aliases v3 */" not in app:
    app=app.replace(marker,marker+"\n/* Deterministic LAB channel aliases v3 */",1)

path.write_text(app,encoding="utf-8")
print("patched deterministic LAB channel aliases v3")
