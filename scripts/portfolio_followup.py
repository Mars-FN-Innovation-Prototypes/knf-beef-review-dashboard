"""Follow-up public review-card audit; preserve access gaps and origin labels."""
import json,re,sys
from portfolio_sources import *

def instacart_query(pid,limit=100,after=None):
    manifest=fetch('https://d2guulkeunn7d8.cloudfront.net/assets/rspack/operation-hashes-87671a68613e90db-v3.webpack_chunk.js')
    queryhash=re.search(r'"GetLandingProductReviews":"([a-f0-9]+)"',manifest).group(1)
    variables={'id':str(pid),'limit':limit}
    if after:variables['after']=after
    params={'operationName':'GetLandingProductReviews','variables':json.dumps(variables,separators=(',',':')),'extensions':json.dumps({'persistedQuery':{'version':1,'sha256Hash':queryhash}},separators=(',',':'))}
    return json.loads(fetch('https://www.instacart.com/graphql?'+urlencode(params)))

def collect_instacart():
    path=CACHE/'instacart.json'
    out=json.loads(path.read_text(encoding='utf-8')) if path.exists() and 'refresh' not in sys.argv else {'reviews':[],'coverage':[],'snapshots':[]}
    queue=['https://www.instacart.com/products/41695689-kevin-s-natural-foods-thai-coconut-chicken-11-5-oz','https://www.instacart.com/products/20742008-kevin-s-natural-foods-cilantro-lime-chicken-16-0-oz','https://www.instacart.com/products/64414811-kevins-natural-foods-honey-garlic-chicken-stirfry']
    queue+=json.loads((ROOT/'data/portfolio_instacart_discovery.json').read_text(encoding='utf-8'))['urls']
    queue+=json.loads((ROOT/'data/portfolio_instacart_discovery_extra.json').read_text(encoding='utf-8'))['urls']
    for p in (ROOT/'data').glob('*retailer*.json'):
        queue+=re.findall(r'https://www\.instacart\.com/(?:store/)?products/[^"\s<>\\]+',p.read_text(encoding='utf-8'))
    seen={re.search(r'products/(\d+)',c['url']).group(1) for c in out['coverage']}
    while queue:
        url=html.unescape(queue.pop(0)).split('?')[0]
        m=re.search(r'products/(\d+)',url)
        if not m or m.group(1) in seen:continue
        iid=m.group(1);seen.add(iid)
        cov={'source':'Instacart (hosted review pool)','url':url,'captured_at':AS_OF};rows=[]
        try:
            raw=fetch(url);nodes=[]
            for attrs,t in scripts(raw):
                if attrs.get('type')=='application/ld+json':
                    try:nodes+=list(walk(json.loads(t)))
                    except ValueError:pass
            info=next((n for n in nodes if n.get('@type')=='Product' and 'kevin' in n.get('name','').lower()),None)
            if not info:raise ValueError('Exact structured product identity not returned')
            page_title=clean(re.search(r'<title[^>]*>(.*?)</title>',raw,re.S).group(1))
            p,match=match_product(page_title,info.get('gtin13') or info.get('gtin12'))
            # Published title explicitly identifies this grocery kit but omits “kit”.
            if iid=='64414811' and 'honey garlic' in info['name'].lower():p=next(x for x in registry() if x['id']=='honey-garlic-chicken-stir-fry-kit');match='prior_verified_instacart_id'
            cov.update(product_id=p['id'] if p else None,title=page_title,match=match)
            queue+=['https://www.instacart.com'+x for x in re.findall(r'href="(/products/\d+[^"<>]*kevin[^"<>]*)"',raw,re.I)]
            if not p:cov.update(status='identity_excluded',note='No unique flavor and format match; not assigned by guesswork.')
            else:
                after=None;unique={};expected=None;complete=False;pages=0
                for _ in range(100):
                    d=instacart_query(iid,100,after)
                    if d.get('errors'):raise ValueError('Public query returned errors: '+str(d['errors'])[:200])
                    result=(d.get('data') or {}).get('productReviews')
                    if not result:raise ValueError('Public query returned no review payload')
                    pages+=1;expected=int(result.get('totalAmount') or 0);batch=result.get('reviews') or []
                    for r in batch:
                        v=r.get('viewSection') or {};meta=v.get('reviewMetadataString','')
                        daymatch=re.search(r'Reviewed on ([A-Za-z]+ \d{1,2}, \d{4})',meta)
                        originmatch=re.search(r' on (.+)$',meta[12:])
                        rating=r.get('reviewRating',{}).get('value')
                        if not daymatch or not originmatch or rating not in [20,40,60,80,100]:continue
                        day=datetime.strptime(daymatch.group(1),'%B %d, %Y').date().isoformat();origin=originmatch.group(1)
                        origin="Kevin's Natural Foods" if 'kevin' in origin.lower() else 'Sprouts' if 'sprouts' in origin.lower() else origin
                        title=v.get('reviewTitleString') or '';body=v.get('reviewContentString') or ''
                        rid=hashlib.sha256((p['id']+'|'+day+'|'+str(rating)+'|'+clean(title)+'|'+clean(body)).encode()).hexdigest()
                        row=record(p['id'],'Instacart (hosted review pool)','Instacart',rid,day,rating//20,title,body,url,origin=origin)
                        if row:unique[rid]=row
                    pageinfo=result.get('pageInfo') or {}
                    if len(batch)>=expected or len(unique)>=expected or pageinfo.get('hasNextPage') is False:complete=True;break
                    cursor=pageinfo.get('endCursor')
                    if not pageinfo.get('hasNextPage') or not cursor or cursor==after:break
                    after=cursor
                rows=[r for r in unique.values() if START<=r['date']<=AS_OF and not re.search(r"isn.t a review of Kevin|is not a review of.{0,30}product",r['text'],re.I)]
                cov.update(status='window_retrieved' if complete else 'partial_history',records=len(rows),displayed_total=expected,retrieved_all_time=len(unique),pages=pages,feed_end_reached=complete,note=f'Public dated feed exhausted: {complete}; {len(unique)} distinct returned dated records versus displayed total {expected}. Displayed totals can include events not returned with dated text; the difference is not imputed. Numeric 0–100 star-fill values divided by 20 and verified against the visible 1–5-star UI. Original source retained; positional IDs replaced with content fingerprints. Non-product website-only complaints excluded.')
                agg=info.get('aggregateRating') or {}
                out['snapshots'].append({'product_id':p['id'],'source':cov['source'],'provider':'Instacart hosted pool','url':url,'rating_count':int(agg.get('reviewCount') or expected),'average':agg.get('ratingValue'),'written_count':None,'captured_at':AS_OF,'basis':'mixed_origin_cumulative_snapshot'})
                for origin in sorted({r['source'] for r in rows}):
                    if origin!=cov['source']:out['coverage'].append({**cov,'source':origin,'records':sum(r['source']==origin for r in rows),'note':cov['note']+' This row is the attributed origin subset, not the full hosted-pool count.'})
            out['reviews'].extend(rows)
        except Exception as e:cov.update(status='access_limited',note=str(e),records=len(rows))
        out['coverage'].append(cov);dump(path,out);print('INSTACART',cov.get('title',url),cov['status'],len(rows),flush=True)
        if 'www.instacart.com' in BLOCKED:break

if __name__=='__main__':collect_instacart()
