from pathlib import Path
import sys

app_path=Path(sys.argv[1] if len(sys.argv)>1 else 'budget-checker/src/app.js')
app=app_path.read_text(encoding='utf-8')

old_family="function mpChannelFamily(v){let s=mpNorm(v).replace(/\\b(programmatic|paid|cpm|cpc)\\b/gu,' ').replace(/\\s+/g,' ').trim();if(/\\bolv\\b|online video|онлайн видео/u.test(s))return'olv';if(/banner|баннер/u.test(s))return'banner';if(/social|соц(?:иальн)?/u.test(s))return'social';if(/rich media|mobile/u.test(s))return'rich';if(/ecom|e-commerce|ecommerce|retail|ритейл/u.test(s))return'ecom';if(/blog|блог/u.test(s))return'blogger';if(/native|натив/u.test(s))return'native';if(/search|контекст|директ|рся/u.test(s))return'context';if(/(^|\\s)(tv|тв)(\\s|$)|телевид/u.test(s))return'tv';if(/verification|верификац|brand safety|viewability|support|сопровожд|monitoring|мониторинг/u.test(s))return'verification';return s;}"
new_family="function mpCanonicalChannelKey(v){const s=mpNorm(v),cpm=/(^|\\s)cpm($|\\s)/u.test(s),cpc=/(^|\\s)cpc($|\\s)/u.test(s);if(/(^|\\s)(olv|олв)($|\\s)|online video|онлайн видео/u.test(s))return'olv';if(/banner|баннер/u.test(s))return cpc?'banners cpc':cpm?'banners cpm':'banners';if(/social(?: nets?| media)?|соц(?:иальн(?:ые|ая|ых|ой)?)?/u.test(s))return cpc?'social cpc':cpm?'social cpm':'social';if(/rich media|mobile/u.test(s))return cpc?'rich media cpc':cpm?'rich media cpm':'rich media';if(/ecom|e-commerce|ecommerce|еком|ритейл|retail/u.test(s)){if(/awareness|охват/u.test(s))return'ecom awareness';if(/performance|перформанс/u.test(s))return'ecom performance';return'ecom';}if(/blogger|bloggers|блогер|инфлюенс/u.test(s))return'blogger';if(/promo.?article|промо.?стат|нативн.*стат|native article/u.test(s))return'promoarticles';if(/native|натив/u.test(s))return'native';if(/search|контекст|директ|рся/u.test(s))return'context';if(/(^|\\s)(tv|тв)(\\s|$)|телевид/u.test(s))return'tv';if(/verification|верификац|brand safety|viewability|support|сопровожд|monitoring|мониторинг/u.test(s))return'verification';return'';}\nfunction mpChannelFamily(v){const k=mpCanonicalChannelKey(v);if(!k)return mpNorm(v);return k.replace(/ (cpm|cpc|awareness|performance)$/u,'');}"
if old_family not in app:
    raise SystemExit('old mpChannelFamily not found')
app=app.replace(old_family,new_family,1)

old_match="function mpMatchChannel(raw,ctx){const n=mpNorm(raw),family=mpChannelFamily(raw),scored=ctx.channels.map(c=>{const cn=mpNorm(c.channel),cf=mpChannelFamily(c.channel);let score=0;if(n&&n===cn)score=100;else if(family&&family===cf&&family.length)score=90;else if(n.length>3&&cn.length>3&&(n.includes(cn)||cn.includes(n)))score=80;else score=Math.round(mpTokenScore(raw,c.channel)*60);return{c,score};}).sort((a,b)=>b.score-a.score);if(!scored.length||scored[0].score<45)return null;if(scored[1]&&scored[1].score===scored[0].score)return null;return scored[0].c;}"
new_match="function mpMatchChannel(raw,ctx){const n=mpNorm(raw),key=mpCanonicalChannelKey(raw),family=mpChannelFamily(raw),scored=ctx.channels.map(c=>{const cn=mpNorm(c.channel),ck=mpCanonicalChannelKey(c.channel),cf=mpChannelFamily(c.channel);let score=0;if(key&&ck&&key===ck)score=120;else if(n&&n===cn)score=110;else if(n.length>3&&cn.length>3&&(n.includes(cn)||cn.includes(n)))score=90;else if(family&&family===cf&&family.length)score=70;else score=Math.round(mpTokenScore(raw,c.channel)*60);return{c,score,key:ck};}).sort((a,b)=>b.score-a.score);if(!scored.length||scored[0].score<45)return null;if(scored[1]&&scored[1].score===scored[0].score)return null;return scored[0].c;}"
if old_match not in app:
    raise SystemExit('old mpMatchChannel not found')
app=app.replace(old_match,new_match,1)

old_agg="for(const p of extracted.placements||[]){const raw=p.section||p.channelKey||p.site||'',target=mpMatchChannel(raw,ctx),source=`${p.sheet}!${p.sourceCell||('строка '+p.row)}`;if(target)add(target,p.month,p.amount,source,raw);else{"
new_agg="for(const p of extracted.placements||[]){const raw=p.section||p.site||p.channelKey||'',matchValue=p.channelKey||p.section||p.site||'',target=mpMatchChannel(matchValue,ctx),source=`${p.sheet}!${p.sourceCell||('строка '+p.row)}`;if(target)add(target,p.month,p.amount,source,raw);else{"
if old_agg not in app:
    raise SystemExit('old placement aggregation not found')
app=app.replace(old_agg,new_agg,1)

app=app.replace('/* LAB mediaplan checker reuse v1 */','/* LAB mediaplan checker reuse v1 */\n/* Budget channel canonical matching v2 */',1)
app_path.write_text(app,encoding='utf-8')
print('patched budget mediaplan channel matching')
