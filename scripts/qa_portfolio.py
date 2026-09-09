"""Validate normalized snapshots and, when present, raw public source provenance."""
import json, random, re, hashlib
from urllib.parse import urlparse,parse_qs
from datetime import datetime
from collections import Counter, defaultdict
from portfolio_sources import ROOT,CACHE,registry,record,match_product,embedded_judge,next_data,walk,clean,dump

def load(p):return json.loads(p.read_text(encoding='utf-8'))

def main():
    data=ROOT/'data';products={p['id']:p for p in registry()};rows=load(data/'portfolio_reviews.json');evidence=load(data/'portfolio_source_evidence.json')
    # Regression: visit/purchase verification is not sponsorship.
    args=['p','s','p','1','2026-01-01',5,'Good','Good food','https://example.com']
    assert record(*args,disclosed=['review_collected_from_store_visitor'])['incentive']=='not_disclosed_or_unknown'
    assert record(*args,disclosed=['verified_purchase'])['incentive']=='not_disclosed_or_unknown'
    assert record(*args,disclosed=['incentivized_review'])['incentive']=='disclosed'
    assert record(*args,disclosed=True)['incentive']=='disclosed'
    assert match_product("kevin's foods Gluten Free Size Pesto Chicken Pasta - 28oz")[0]['category']=='Frozen Family Meals'
    assert match_product("Kevin's Entrees and Sides Bundle")[0] is None
    assert match_product("Kevin's Korean BBQ Chicken bowl 9.5 oz")[0]['category']=='Frozen Bowls'
    assert match_product("Kevin's Chicken Piccata with Cauliflower Pasta 26 oz")[0]['category']=='Pastas'
    assert match_product('Buffalo Sauce','810264028814')[0]['current_assortment'] is False
    # All exact UPC matches must resolve uniquely to the same registered product.
    identity=[];provider_pids=defaultdict(set)
    for source,d in evidence.items():
        for c in d['coverage']:
            if c.get('product_id'):
                assert c['product_id'] in products
                if c.get('match')=='exact_upc':assert match_product(c['title'],c['upc'])[0]['id']==c['product_id']
                if c.get('match')=='exact_flavor_and_format':assert match_product(c['title'])[0]['id']==c['product_id'],c
                identity.append({k:c.get(k) for k in ['source','title','product_id','match','status','records']})
            if c['status']=='history_retrieved':assert c['retrieved_all_time']==c['total_written']
        for r in d['reviews']:provider_pids[(r['provider'],r['provider_review_id'])].add(r['product_id'])
    conflicts=[{'provider':k[0],'id':k[1],'products':sorted(v)} for k,v in provider_pids.items() if len(v)>1]
    assert not conflicts,f'Unresolved cross-product pools: {conflicts[:5]}'
    # Match a stratified sample back to the raw cached provider record, not merely
    # to the same derived JSON. Raw payloads remain local and are never published.
    lookup={};files=0
    for meta in CACHE.glob('*.meta.json'):
        info=load(meta);url=info['url'];path=meta.with_name(meta.name.replace('.meta.json','.txt'))
        if not path.exists():continue
        raw=path.read_text(encoding='utf-8');batch=[];provider=None
        if 'instacart.com/graphql?' in url:
            variables=json.loads(parse_qs(urlparse(url).query)['variables'][0])
            cs=[c for c in evidence.get('instacart',{}).get('coverage',[]) if re.search(r'products/'+str(variables['id'])+r'(?:-|$)',c['url']) and c.get('product_id')]
            if not cs:continue
            pid=cs[0]['product_id'];provider='Instacart'
            batch=(json.loads(raw).get('data') or {}).get('productReviews',{}).get('reviews',[])
            for r in batch:
                v=r.get('viewSection') or {};m=re.search(r'Reviewed on ([A-Za-z]+ \d{1,2}, \d{4})',v.get('reviewMetadataString',''))
                if not m:continue
                day=datetime.strptime(m.group(1),'%B %d, %Y').date().isoformat();rating=r['reviewRating']['value']
                rid=hashlib.sha256((pid+'|'+day+'|'+str(rating)+'|'+clean(v.get('reviewTitleString'))+'|'+clean(v.get('reviewContentString'))).encode()).hexdigest()
                lookup[(provider,rid)]=({'date':day,'rating':rating/20,'text':v.get('reviewContentString')},url)
            files+=bool(batch)
            continue
        elif 'judge.me/reviews/reviews_for_widget' in url:
            batch=json.loads(raw).get('reviews',[]);provider='Judge.me'
        elif 'kevinsnaturalfoods.com/products/' in url:
            widget=embedded_judge(raw) or {}
            if widget:assert widget.get('sort_key')=='created_at',url
            batch=widget.get('reviews',[]);provider='Judge.me'
        elif 'thrivemarket.com/api/v1/product/' in url:
            batch=json.loads(raw).get('reviews',[]);provider='Thrive Market'
        elif 'target.com/p/' in url:
            try:
                for n in walk(next_data(raw)):
                    if 'most_recent' in n and 'statistics' in n:batch+=n['most_recent']
                provider='Target'
            except ValueError:pass
        elif 'walmart.com/reviews/product/' in url:
            try:batch=next_data(raw)['props']['pageProps']['initialData']['data']['reviews'].get('customerReviews',[]);provider='Walmart'
            except (ValueError,KeyError):pass
        for r in batch:
            rid=str(r.get('uuid') or r.get('reviewId') or r.get('reviewReferenceId') or r.get('id'))
            lookup[(provider,rid)]=(r,url)
        files+=bool(batch)
    sample=[];groups=defaultdict(list)
    for r in rows:
        if r['record_origin']=='new_collection':groups[(r['provider'],products[r['product_id']]['category'])].append(r)
    random.seed(90926)
    for group,rs in sorted(groups.items()):
        for r in random.sample(rs,min(2,len(rs))):
            if not lookup:continue
            original,url=lookup[(r['provider'],r['provider_review_id'])]
            if r['provider']=='Judge.me':day=original['created_at'][:10];rating=original['rating'];text=original.get('body_html') or original.get('body')
            elif r['provider']=='Thrive Market':day=original['created_at'][:10];rating=original['value'];text=original.get('detail')
            elif r['provider']=='Target':day=original['rating']['submitted_at'][:10];rating=original['rating']['value'];text=original.get('text')
            elif r['provider']=='Instacart':day=original['date'];rating=original['rating'];text=original['text']
            else:
                day=datetime.strptime(original['reviewSubmissionTime'],'%m/%d/%Y').date().isoformat();rating=original['rating'];text=original.get('reviewText')
            assert r['date']==day and r['rating']==int(rating) and r['text']==clean(text),(group,r['id'])
            sample.append({'id':r['id'],'product':products[r['product_id']]['name'],'provider':r['provider'],'date':day,'rating':int(rating),'raw_verified':True})
    report={'as_of':'2026-09-09','raw_payloads_available':files,'stratified_records_verified':len(sample),'categories_verified':len({products[r['product_id']]['category'] for r in rows if any(x['id']==r['id'] for x in sample)}),'provider_id_product_conflicts':conflicts,'sample':sample,'identity_checks':identity,'source_statuses':{name:dict(Counter(c['status'] for c in d['coverage'])) for name,d in evidence.items()}}
    dump(CACHE/'validation_report.json',report)
    if sample:dump(data/'portfolio_validation.json',{k:v for k,v in report.items() if k!='identity_checks'})
    print(json.dumps({k:v for k,v in report.items() if k not in ['sample','identity_checks']},indent=2))
    for c in identity:
        if c['source']!="Kevin's Natural Foods":print(c)

if __name__=='__main__':main()
