"""Public-source portfolio collection. Cache responses locally; publish sanitized records only."""
from __future__ import annotations
import argparse, hashlib, html, json, re, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import urlparse, urlencode, urljoin
from urllib.request import Request, urlopen
from html.parser import HTMLParser

ROOT = Path(__file__).resolve().parents[1]
CACHE = ROOT.parent / 'analysis' / 'portfolio_collection_2026-09-09'
CACHE.mkdir(parents=True, exist_ok=True)
AS_OF = '2026-09-09'
START = '2024-07-01'
BLOCKED = set()
LAST = {}

def dump(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')

def fetch(url):
    key = hashlib.sha256(url.encode()).hexdigest()
    path = CACHE / (key + '.txt')
    if path.exists():
        return path.read_text(encoding='utf-8')
    host = urlparse(url).netloc
    if host in BLOCKED:
        raise RuntimeError('Deferred after source access/rate limit: ' + host)
    time.sleep(max(0, (5 if 'thrivemarket' in host else 1.1) - (time.monotonic() - LAST.get(host, 0))))
    try:
        req = Request(url, headers={'User-Agent':'ChatGPT-User (KNFReviewResearch/3.0)' if 'thrivemarket' in host else 'Mozilla/5.0 (compatible; KNFReviewResearch/3.0)', 'Accept':'text/html,application/json'})
        with urlopen(req, timeout=35) as response:
            raw = response.read().decode('utf-8', errors='replace')
        path.write_text(raw, encoding='utf-8')
        dump(CACHE/(key+'.meta.json'), {'url':url, 'captured_at':datetime.now(timezone.utc).isoformat(), 'bytes':len(raw)})
        return raw
    except HTTPError as e:
        if e.code in (401,403,412,429):
            BLOCKED.add(host)
        raise
    finally:
        LAST[host] = time.monotonic()

class Scripts(HTMLParser):
    def __init__(self):
        super().__init__(); self.items=[]; self.attrs=None; self.parts=[]
    def handle_starttag(self,tag,attrs):
        if tag=='script': self.attrs=dict(attrs); self.parts=[]
    def handle_data(self,data):
        if self.attrs is not None: self.parts.append(data)
    def handle_endtag(self,tag):
        if tag=='script' and self.attrs is not None:
            self.items.append((self.attrs,''.join(self.parts))); self.attrs=None

def clean(value):
    return ' '.join(html.unescape(re.sub('<[^>]+>',' ',str(value or ''))).split())

def scripts(raw):
    p=Scripts(); p.feed(raw); return p.items

def next_data(raw):
    for attrs, txt in scripts(raw):
        if attrs.get('id')=='__NEXT_DATA__': return json.loads(txt)
    raise ValueError('Public page did not expose a structured product payload')

def walk(value):
    if isinstance(value,dict):
        yield value
        for v in value.values(): yield from walk(v)
    elif isinstance(value,list):
        for v in value: yield from walk(v)

def embedded_judge(raw):
    match=re.search(r'jdgm.data.reviewWidget\[\d+\]\s*=\s*',raw)
    return json.JSONDecoder().raw_decode(raw[match.end():])[0] if match else None

def registry():
    frozen=ROOT/'data/portfolio_product_registry.json'
    if frozen.exists():
        return json.loads(frozen.read_text(encoding='utf-8'))
    data=json.loads((ROOT.parent/'analysis/portfolio_discovery_2026-09-09/official_assortment.json').read_text(encoding='utf-8'))
    products=[]
    for p in data['products']:
        if p['scope_class']=='bundle': continue
        upcs=set(p['locator_upcs'])
        for v in p['variants']:
            upcs.update(x.strip() for x in (v.get('barcode') or '').split(',') if x.strip().isdigit())
        category=p['categories'][0]
        products.append({'id':p['handle'],'name':p['title'],'category':category,'shopify_id':p['shopify_product_id'],
          'url':p['official_url'],'upcs':sorted(upcs),'variants':p['variants'],'current_assortment':True,
          'locator_url':p['store_locator_urls'][0] if p['store_locator_urls'] else None,
          'format':'Frozen' if category.startswith('Frozen') else 'Sauce' if category=='Sauces' else 'Refrigerated',
          'metadata_status':'barcode_enriched' if any(v.get('barcode') for v in p['variants']) else 'catalog_identity_only'})
    historical=ROOT/'data/portfolio_historical_products.json'
    if historical.exists():products.extend(json.loads(historical.read_text(encoding='utf-8')))
    return products

def record(pid,source,provider,rid,day,rating,title,text,url,disclosed=False,origin=None):
    try:
        rating=int(rating)
        datetime.strptime(day[:10],'%Y-%m-%d')
    except (ValueError,TypeError): return None
    if not 1<=rating<=5: return None
    title,text=clean(title),clean(text)
    # Store-visitor and verified-purchase badges are not incentive disclosures.
    if isinstance(disclosed,(list,dict)):
        disclosed=any(re.search(r'incentiv|free.product|promotion|sponsored|thrive.cash',str(x),re.I) for x in disclosed)
    else:disclosed=disclosed is True or disclosed==1
    disclosed=bool(disclosed or re.search(r'collected as part of a promotion|received.{0,50}(?:free|complimentary)|sponsored|in exchange for.{0,30}review',title+' '+text,re.I))
    return {'product_id':pid,'source':origin or source,'display_source':source,'provider':provider,'provider_review_id':str(rid),
      'date':day[:10],'rating':rating,'title':title,'text':text,'written':bool(title or text),
      'incentive':'disclosed' if disclosed else 'not_disclosed_or_unknown','source_url':url,'captured_at':AS_OF,
      'date_basis':'provider_submission_date','review_pool_id':provider+':'+pid,'record_origin':'new_collection'}

def collect_brand(refresh=False):
    out={'as_of':AS_OF,'reviews':[],'snapshots':[],'coverage':[]}
    path=CACHE/'brand.json'
    if path.exists() and not refresh: out=json.loads(path.read_text(encoding='utf-8'))
    done={x['product_id'] for x in out['coverage'] if x['status'] not in ['access_limited','error']}
    for p in registry():
        if not p.get('shopify_id'):continue
        if p['id'] in done: continue
        rows=[];cov={'product_id':p['id'],'source':"Kevin's Natural Foods",'url':p['url'],'captured_at':AS_OF,'match':'official_product'}
        try:
            raw=fetch(p['url']);first=embedded_judge(raw)
            cov['bazaarvoice_component']=bool(re.search('data-bv-show',raw))
            if first is None:
                cov.update(status='no_legacy_feed',note='No legacy review payload; current provider assessed separately.')
            else:
                seen=set();reached=False;pages=0
                for page in range(1,int(first.get('pagination',{}).get('total_pages',1))+1):
                    query={'product_id':p['shopify_id'],'page':page,'sort_by':'created_at','sort_dir':'desc','ts':first.get('metafield_updated_at',AS_OF),'shop_domain':'kevins-natural-foods.myshopify.com','platform':'shopify'}
                    batch=first if page==1 else json.loads(fetch('https://cdn.judge.me/reviews/reviews_for_widget?'+urlencode(query)))
                    pages+=1
                    added=0
                    for r in batch.get('reviews',[]):
                        rid=r.get('uuid') or str(r.get('id'))
                        if rid in seen: continue
                        seen.add(rid); added+=1
                        day=r.get('created_at','')[:10]
                        if day and day<START: reached=True
                        row=record(p['id'],"Kevin's Natural Foods",'Judge.me',rid,day,r.get('rating'),r.get('title'),r.get('body_html') or r.get('body'),p['url'],r.get('transparency_badges'))
                        if row and START<=day<=AS_OF: rows.append(row)
                    if reached or not added: break
                cov.update(status='legacy_window_retrieved',note='Legacy dated feed retrieved through requested start or feed end; current Bazaarvoice assessed separately.',pages=pages,records=len(rows),start_reached=reached)
                out['snapshots'].append({'product_id':p['id'],'source':"Kevin's Natural Foods",'provider':'Judge.me (legacy)','url':p['url'],'rating_count':first.get('number_of_reviews'),'average':first.get('average_rating'),'captured_at':AS_OF,'basis':'legacy_cumulative_snapshot'})
            out['reviews'].extend(rows)
        except Exception as e:
            cov.update(status='access_limited' if isinstance(e,HTTPError) or 'Deferred' in str(e) else 'error',note=str(e),records=len(rows))
            out['reviews'].extend(rows)
        out['coverage']=[r for r in out['coverage'] if r['product_id']!=p['id']]+[cov]
        dump(path,out);print(p['id'],cov['status'],len(rows),flush=True)
        if 'www.kevinsnaturalfoods.com' in BLOCKED: break

def inspect():
    d=json.loads((CACHE/'probe.json').read_text())
    raw=fetch(d['bv']['url'])
    print('BV config',re.findall(r'.{0,40}(?:mars-kevins|main_site|convapi|displayCode).{0,220}',raw)[-20:])
    for name in ['thrive','thrive_brand']:
        t=next_data(fetch(d[name]['url']))
        print(name,[(n.get('id'),n.get('sku'),n.get('title'),n.get('url_key')) for n in walk(t) if n.get('sku') and n.get('url_key')][:100])
    raw=fetch(d['hannaford']['url'])
    print('Hannaford',re.findall(r'.{0,80}(?:bazaarvoice|powerreviews|review|rating).{0,130}',raw)[-20:])

def bv_config():
    raw=fetch('https://apps.bazaarvoice.com/deployments/mars-kevins/main_site/production/en_US/swat_reviews-config.js')
    return json.JSONDecoder().raw_decode(raw[raw.index('.configure(')+11:])[0]

def bv_page(pid,offset=0):
    params={'apiversion':'5.4','passkey':bv_config()['apiKey'],'filter':'ProductId:eq:'+str(pid),
      'sort':'SubmissionTime:desc','limit':100,'offset':offset,'include':'Products','stats':'Reviews'}
    return json.loads(fetch('https://api.bazaarvoice.com/data/reviews.json?'+urlencode(params)))

def bv_probe():
    d=bv_page('3690781311029');dump(CACHE/'bv_probe.json',d)
    print('BV keys',list(d),'Total',d.get('TotalResults'),'Errors',d.get('Errors'))
    print('samples',[{k:r.get(k) for k in ['Id','ProductId','SubmissionTime','LastModificationTime','Rating','Title','IsSyndicated','SyndicationSource','Badges','ContentLocale']} for r in d.get('Results',[])[:3]])

def collect_bv():
    out={'reviews':[],'snapshots':[],'coverage':[]};path=CACHE/'bazaarvoice.json'
    if path.exists():out=json.loads(path.read_text(encoding='utf-8'))
    done={r['product_id'] for r in out['coverage'] if r['status']=='window_retrieved'}
    for p in registry():
        if p['id'] in done:continue
        cov={'product_id':p['id'],'source':"Kevin's Natural Foods",'provider':'Bazaarvoice','url':p['url'],'captured_at':AS_OF,'match':'official_product'}
        rows=[];seen=set()
        try:
            first=bv_page(p['shopify_id']); total=int(first.get('TotalResults',0))
            if first.get('HasErrors'):raise ValueError(str(first.get('Errors')))
            pages=0;reached=False
            for offset in range(0,max(1,total),100):
                data=first if offset==0 else bv_page(p['shopify_id'],offset);pages+=1
                batch=data.get('Results',[])
                for r in batch:
                    if str(r['Id']) in seen:continue
                    seen.add(str(r['Id']));day=r.get('SubmissionTime','')[:10]
                    if day and day<START:reached=True
                    origin=(r.get('SyndicationSource') or {}).get('Name') if r.get('IsSyndicated') else None
                    origin="Kevin's Natural Foods" if origin and 'kevin' in origin.lower() else origin
                    row=record(p['id'],"Kevin's Natural Foods",'Bazaarvoice',r['Id'],day,r.get('Rating'),r.get('Title'),r.get('ReviewText'),p['url'],r.get('IsIncentivizedReview') or any('incentiv' in k.lower() for k in (r.get('Badges') or {})),origin)
                    if row and START<=day<=AS_OF:
                        row['syndicated']=bool(r.get('IsSyndicated'));row['last_modified']=r.get('LastModificationTime');rows.append(row)
                if reached or not batch:break
            stats=next(iter((first.get('Includes',{}).get('Products',{})).values()),{}).get('ReviewStatistics',{})
            out['snapshots'].append({'product_id':p['id'],'source':"Kevin's Natural Foods",'provider':'Bazaarvoice','url':p['url'],'rating_count':stats.get('TotalReviewCount',total),'average':stats.get('AverageOverallRating'),'captured_at':AS_OF,'basis':'current_provider_cumulative_snapshot'})
            cov.update(status='window_retrieved',records=len(rows),total_provider_records=total,pages=pages,start_reached=reached,note='Current provider public feed reached requested start or feed end; original submission dates retained.')
        except Exception as e:cov.update(status='access_limited',records=len(rows),note=str(e))
        out['reviews'].extend(rows);out['coverage'].append(cov);dump(path,out);print('BV',p['id'],cov['status'],len(rows),flush=True)
        if 'api.bazaarvoice.com' in BLOCKED:break

def discover():
    out={'listings':[],'audits':[]}
    # Follow the retailer's published sitemap, not guessed product URLs.
    try:
        urls=re.findall(r'<loc>(.*?)</loc>',fetch('https://thrivemarket.com/sitemap.xml'))
        product_urls=[]
        for u in urls:
            if '.xml' in u:
                content=fetch(u)
                product_urls.extend(re.findall(r'<loc>(https://thrivemarket.com/p/[^<]*kevin[^<]*)</loc>',content))
            elif '/p/' in u and 'kevin' in u:product_urls.append(u)
        for u in sorted(set(product_urls)):out['listings'].append({'source':'Thrive Market','url':html.unescape(u)})
        out['audits'].append({'source':'Thrive Market','method':'published sitemap enumeration','listings':len(product_urls),'status':'catalog_searched'})
    except Exception as e:out['audits'].append({'source':'Thrive Market','status':'access_limited','note':str(e)})
    wm='https://www.walmart.com/browse/kevin-s-natural-foods/YnJhbmQ6S2V2aW4ncyBOYXR1cmFsIEZvb2Rz'
    for page in range(1,3):
        try:
            data=next_data(fetch(wm+('' if page==1 else '?page='+str(page))))
            items={str(n['usItemId']):n for n in walk(data) if n.get('usItemId') and re.search('kevin',n.get('name',''),re.I)}
            for item,n in items.items():out['listings'].append({'source':'Walmart','url':urljoin(wm,n.get('canonicalUrl') or '/ip/'+item).split('?')[0],'item_id':item,'title':n['name'],'upc':n.get('upc')})
            out['audits'].append({'source':'Walmart','method':'brand catalog page '+str(page),'status':'catalog_searched','listings':len(items)})
        except Exception as e:out['audits'].append({'source':'Walmart','status':'access_limited','note':str(e)});break
    try:
        url='https://www.target.com/s?searchTerm=kevins+natural+foods'
        data=next_data(fetch(url))
        items={str(n['tcin']):n for n in walk(data) if n.get('tcin') and 'item' in n and 'kevin' in str(n.get('item',{})).lower()}
        for item,n in items.items():out['listings'].append({'source':'Target','url':'https://www.target.com/p/-/A-'+item,'item_id':item,'title':clean(n.get('item',{}).get('product_description',{}).get('title'))})
        out['audits'].append({'source':'Target','status':'catalog_searched','method':'retailer brand search','listings':len(items)})
    except Exception as e:out['audits'].append({'source':'Target','status':'access_limited','note':str(e)})
    # Additional exact pages observed in the discovery audit and existing module records.
    for pid in ['89908091','81838523','94662250','88883892','87790111','94978150','94736217','94177635']:
        out['listings'].append({'source':'Target','url':'https://www.target.com/p/-/A-'+pid,'item_id':pid})
    for pid in ['1662798211','2455684608']:
        out['listings'].append({'source':'Walmart','url':'https://www.walmart.com/ip/'+pid,'item_id':pid})
    seen=set();unique=[]
    for row in out['listings']:
        key=(row['source'],row.get('item_id') or row['url'])
        if key not in seen:seen.add(key);unique.append(row)
    out['listings']=unique;dump(CACHE/'discovery.json',out)
    print('DISCOVERY',len(unique),out['audits'],flush=True)

def norm(s):
    s=s.lower().replace('barbeque','bbq').replace('barbecue','bbq')
    s=re.sub(r'(\d)([a-z])',r'\1 \2',s)
    return ' '.join(re.findall(r'[a-z0-9]+',s))

def match_product(title,upc=None):
    products=registry();code=re.sub(r'\D','',str(upc or '')).lstrip('0')
    if code:
        exact=[p for p in products if any(x.lstrip('0')==code for x in p['upcs'])]
        if len(exact)==1:return exact[0], 'exact_upc'
    t=norm(title)
    if re.search('variety|sampler|bundle|tikka thai|simmer sauces',t):return None,'mixed_bundle_excluded'
    isbowl=bool(re.search(r'9 5|bowl',t));isfamily=bool(re.search(r'family|28 oz',t))
    iskit=bool(re.search(r'stir fry|skillet meal|with green beans|with broccoli',t))
    isclub=bool(re.search(r'32 oz|costco',t))
    scores=[]
    stop={'style','with','and','natural','foods','kevin','kevins','gluten','free','paleo','keto','cauliflower','in','the','frozen','bowl','family','size','kit','stir','fry','entree','meal','skillet'}
    for p in products:
        c=p['category'];name=norm(p['name']);tokens=set(name.split())-stop
        if (c=='Frozen Bowls')!=isbowl:continue
        if (c=='Frozen Family Meals')!=isfamily:continue
        if (c=='Stir-Fry Entrées')!=iskit:continue
        if ('soup' in t)!=(c=='Soups'):continue
        if c=='Sauces' and not ('sauce' in t and not ('chicken' in t or 'beef' in t)):continue
        if 'sauce' in t and not ('chicken' in t or 'beef' in t) and c!='Sauces':continue
        if c=='Stir-Fry Entrées' and ('kit' not in name)==(not isclub):continue
        overlap=len(tokens & set(t.split()))/max(1,len(tokens))
        if overlap==1:scores.append(p)
    return (scores[0],'exact_flavor_and_format') if len(scores)==1 else (None,'identity_unresolved')

def collect_thrive():
    disc=json.loads((CACHE/'discovery.json').read_text(encoding='utf-8'))
    out={'reviews':[],'snapshots':[],'coverage':[]};path=CACHE/'thrive.json'
    if path.exists():out=json.loads(path.read_text(encoding='utf-8'))
    out['coverage']=[r for r in out['coverage'] if not (r.get('title')=='Buffalo Sauce' and r['status']=='identity_excluded')]
    done={r['url'] for r in out['coverage']}
    for item in [x for x in disc['listings'] if x['source']=='Thrive Market']:
        url=item['url']
        if url in done:continue
        cov={'source':'Thrive Market','url':url,'captured_at':AS_OF};rows=[]
        try:
            data=next_data(fetch(url)); candidates=[n for n in walk(data) if n.get('sku') and n.get('url')==url and n.get('id')]
            if not candidates:raise ValueError('No product identity returned')
            info=candidates[0];p,match=match_product(info.get('title',''),info.get('sku'))
            cov.update(title=info.get('title'),upc=info.get('sku'),match=match,product_id=p['id'] if p else None)
            if not p:cov.update(status='identity_excluded',note='No unique verified assortment match; excluded from metrics.')
            else:
                seen=set();pages=0;total=None
                for page in range(1,200):
                    endpoint=f"https://thrivemarket.com/api/v1/product/{info['id']}/reviews/?cur_page={page}&page_size=100&sort=1&ratings_filter=0"
                    payload=json.loads(fetch(endpoint));pages+=1;batch=payload.get('reviews') or [];total=int(payload.get('review_count') or 0)
                    added=0
                    for r in batch:
                        rid=str(r['id'])
                        if rid in seen:continue
                        added+=1;seen.add(rid)
                        row=record(p['id'],'Thrive Market','Thrive Market',rid,r.get('created_at','')[:10],r.get('value'),r.get('title'),r.get('detail'),url,r.get('thrive_cash_earned'))
                        if row and START<=row['date']<=AS_OF:rows.append(row)
                    if page==1:
                        out['snapshots'].append({'product_id':p['id'],'source':'Thrive Market','provider':'Thrive Market','url':url,'rating_count':payload.get('rating_count'),'average':payload.get('average_rating'),'written_count':total,'captured_at':AS_OF,'basis':'cumulative_snapshot'})
                    if len(seen)>=total or not added:break
                cov.update(status='history_retrieved' if len(seen)==total else 'partial_history',records=len(rows),total_written=total,retrieved_all_time=len(seen),pages=pages,note='Full returned written history; cumulative rating count includes additional rating-only events not exposed as dated records.')
        except Exception as e:cov.update(status='access_limited',note=str(e),records=len(rows))
        out['reviews'].extend(rows);out['coverage'].append(cov);dump(path,out);print('THRIVE',cov.get('title',url),cov['status'],len(rows),flush=True)
        if 'thrivemarket.com' in BLOCKED:break

def collect_walmart():
    disc=json.loads((CACHE/'discovery.json').read_text(encoding='utf-8'));path=CACHE/'walmart.json'
    out=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'reviews':[],'snapshots':[],'coverage':[]}
    retry={r['url'] for r in out['coverage'] if 'NoneType' in r.get('note','')}
    out['coverage']=[r for r in out['coverage'] if r['url'] not in retry]
    out['reviews']=[r for r in out['reviews'] if r['source_url'] not in retry]
    out['snapshots']=[r for r in out['snapshots'] if r['url'] not in retry]
    done={r['url'] for r in out['coverage']}
    for item in [x for x in disc['listings'] if x['source']=='Walmart']:
        url=item['url'];iid=item['item_id']
        if url in done:continue
        cov={'source':'Walmart','url':url,'captured_at':AS_OF};rows=[]
        try:
            raw=fetch(url);data=next_data(raw)['props']['pageProps']['initialData']['data'];info=data.get('product',{})
            title=info.get('name') or item.get('title','');p,match=match_product(title,info.get('upc'))
            cov.update(title=title,upc=info.get('upc'),product_id=p['id'] if p else None,match=match)
            if not p:cov.update(status='identity_excluded',note='Ambiguous, mixed bundle or outside current verified assortment; not assigned by guesswork.')
            else:
                seen=set();total=None;pages=0;reached=False
                for page in range(1,1000):
                    reviewurl=f'https://www.walmart.com/reviews/product/{iid}?page={page}&sort=submission-desc'
                    payload=next_data(fetch(reviewurl))['props']['pageProps']['initialData']['data']['reviews'];pages+=1
                    batch=payload.get('customerReviews',[]);total=int(payload.get('reviewsWithTextCount') or 0);added=0
                    for r in batch:
                        rid=str(r.get('reviewId') or r.get('reviewReferenceId'))
                        if rid in seen:continue
                        seen.add(rid);added+=1
                        value=r.get('reviewSubmissionTime','')
                        try:day=datetime.strptime(value,'%m/%d/%Y').date().isoformat()
                        except ValueError:day=value[:10]
                        if day and day<START:reached=True
                        origin=r.get('clientName') if r.get('isSyndicated') else None
                        if origin and 'kevin' in origin.lower():origin="Kevin's Natural Foods"
                        row=record(p['id'],'Walmart','Walmart',rid,day,r.get('rating'),r.get('reviewTitle'),r.get('reviewText'),url,any('incentiv' in str(b).lower() for b in (r.get('badges') or [])),origin)
                        if row and START<=day<=AS_OF:rows.append(row)
                    if page==1:
                        out['snapshots'].append({'product_id':p['id'],'source':'Walmart','provider':'Walmart','url':url,'rating_count':payload.get('totalReviewCount'),'average':payload.get('roundedAverageOverallRating') or payload.get('averageOverallRating'),'written_count':total,'captured_at':AS_OF,'basis':'cumulative_snapshot'})
                    if reached or len(seen)>=total or not added:break
                cov.update(status='window_retrieved' if reached or len(seen)>=total else 'partial_history',records=len(rows),total_written=total,retrieved_all_time=len(seen),pages=pages,start_reached=reached,note='Public review pages paginated until requested start, reported text count, or no new records.')
        except Exception as e:cov.update(status='access_limited',note=str(e),records=len(rows))
        out['reviews'].extend(rows);out['coverage'].append(cov);dump(path,out);print('WM',cov.get('title',url),cov['status'],len(rows),flush=True)
        if 'www.walmart.com' in BLOCKED:break

def collect_target(refresh=False):
    disc=json.loads((CACHE/'discovery.json').read_text(encoding='utf-8'));path=CACHE/'target.json'
    out=json.loads(path.read_text(encoding='utf-8')) if path.exists() and not refresh else {'reviews':[],'snapshots':[],'coverage':[]}
    out['coverage']=[r for r in out['coverage'] if 'NoneType' not in r.get('note','') and not (r['status']=='identity_excluded' and r['url'].split('-')[-1] in ['94686846','94978150'])]
    queue=[x['url'] for x in disc['listings'] if x['source']=='Target'];seen={r['url'] for r in out['coverage']}
    # Canonical links followed from the public Target category page on September 9.
    queue += ['https://www.target.com/p/-/A-'+x for x in ['94978109','95006718','93214452','81841955','94686846','89908085','94686843','94686845','95006702','93214448','94662249','94662247','94662248','89638587','93214454','94978126','94662251']]
    # Search-indexed public category page exposes canonical links, unlike client-only search.
    try:
        raw=fetch('https://www.target.com/s/kevin%2Bpaleo')
        queue+=['https://www.target.com/p/-/A-'+iid for iid in re.findall(r'href="[^"]*kevin[^"<>]*?/A-(\d+)[^"]*"',raw,re.I)]
    except Exception:pass
    while queue:
        url=queue.pop(0)
        if url in seen:continue
        seen.add(url);cov={'source':'Target','url':url,'captured_at':AS_OF};rows=[]
        try:
            raw=fetch(url);data=next_data(raw)
            for iid in re.findall(r'href="[^"]*kevin[^"<>]*?/A-(\d+)[^"]*"',raw,re.I):
                u='https://www.target.com/p/-/A-'+iid
                if u not in seen:queue.append(u)
            title=clean(re.search(r'<title[^>]*>(.*?)</title>',raw,re.S).group(1)).removesuffix(' : Target')
            p,match=match_product(title)
            if url.endswith('94978150') and re.search('fajita',title,re.I):
                # Exact TCIN verified in the existing stir-fry listing registry;
                # Target's shortened title omits the protein name.
                p=next(x for x in registry() if x['id']=='chicken-fajitas-skillet-meal-kit')
                match='existing_verified_tcin'
            # These three flavors share a single Target rating pool. Keep the group
            # explicit; never infer the reviewed flavor from the page selected.
            pooled=any(x in title.lower() for x in ['korean bbq','cilantro lime','roasted garlic']) and '16oz' in title.lower()
            cov.update(title=title,product_id=p['id'] if p else None,match=match)
            node=next((n for n in walk(data) if 'most_recent' in n and 'statistics' in n),None)
            if not p:cov.update(status='identity_excluded',note='No unique flavor/format identity match.')
            elif pooled:cov.update(status='shared_flavor_pool',note='Ratings pooled across Korean BBQ, Cilantro Lime and Roasted Garlic chicken; excluded from SKU-level and portfolio trend pending review-level flavor resolution.')
            elif node:
                for r in node['most_recent']:
                    rating=r.get('rating',{});row=record(p['id'],'Target','Target',r.get('id'),rating.get('submitted_at','')[:10],rating.get('value'),r.get('title'),r.get('text'),url)
                    if row and START<=row['date']<=AS_OF:rows.append(row)
                cov.update(status='recent_public_sample',records=len(rows),note='Public product payload exposes most-recent records, not complete history. Excluded from default historical trend; available in all-collected sensitivity view.')
                for row in rows:row['coverage_tier']='sample'
            else:cov.update(status='listing_no_dated_payload',note='Exact page found; dated review payload not returned.')
            if p and node:
                stats=node['statistics'];rr=stats['rating']
                out['snapshots'].append({'product_id':p['id'],'source':'Target','provider':'Target','url':url,'rating_count':rr.get('count'),'average':rr.get('average'),'written_count':stats.get('review_count'),'captured_at':AS_OF,'basis':'shared_flavor_pool' if pooled else 'cumulative_snapshot'})
        except Exception as e:cov.update(status='access_limited',note=str(e))
        out['reviews'].extend(rows);out['coverage'].append(cov);dump(path,out);print('TARGET',cov.get('title',url),cov['status'],len(rows),flush=True)
        if 'www.target.com' in BLOCKED:break

def target_api_probe():
    raw=fetch('https://www.target.com/p/-/A-89908091')
    txt=next(t for a,t in scripts(raw) if 'ratingsAndReviews' in t)
    start=txt.find('JSON.parse(')
    config=json.JSONDecoder().raw_decode(txt[start+11:])[0]
    if isinstance(config,str):config=json.loads(config)
    configs=[n for n in walk(config) if n.get('baseUrl') and n.get('apiKey')]
    c=next(n for n in configs if 'reviews' in n.get('apis',{}) and 'ratingAndReviewsV1' in n['apis']['reviews']['endpointPaths'])
    endpoint=c['baseUrl'].rstrip('/')+'/'+c['apis']['reviews']['endpointPaths']['ratingAndReviewsV1'].lstrip('/')
    query={'key':c['apiKey'],'product_id':'89908091','page':0,'size':100,'sort_by':'most_recent','has_text_only':'false'}
    data=json.loads(fetch(endpoint+'?'+urlencode(query)))
    dump(CACHE/'target_api_probe.json',data)
    print('Target public API',str(data)[:3500])

def assess_other_sources():
    seeds=[
      ('Kroger','korean-bbq-style-chicken','https://www.kroger.com/p/kevin-s-natural-foods-family-size-korean-bbq-style-chicken/0081026402856'),
      ('Hannaford','korean-bbq-style-chicken-frozen-bowl','https://www.hannaford.com/groceries/product/kevins-natural-foods-gluten-free-korean-bbq-style-chicken-frozen-meal-9-5-oz-pkg/364431'),
      ('Hannaford','teriyaki-style-chicken','https://hannaford.com/groceries/product/kevins-natural-foods-paleo-teriyaki-chicken-refrigerated-16-oz-pkg/286603'),
      ('Costco','korean-bbq-style-steak-tips','https://www.costco.com/p/-/kevins-natural-foods-korean-bbq-style-beef-32-oz/4000060876'),
      ('Whole Foods','korean-bbq-style-chicken','https://www.wholefoodsmarket.com/grocery/product/korean-bbq-style%20chicken-b083vkrv94'),
      ('Albertsons','korean-bbq-style-chicken','https://www.albertsons.com/shop/pd/kevins-natural-foods-korean-style-bbq-chicken-16-oz/960563141'),
      ('Safeway','mongolian-style-beef','https://www.safeway.com/shop/pd/kevins-natural-foods-mongolian-style-beef-16-oz/970300678'),
      ('Publix','hawaiian-style-chicken','https://www.publix.com/pd/kevins-natural-foods-hawaiian-style-chicken/RIO-PCI-634264'),
      ('Wegmans','korean-bbq-style-chicken','https://www.wegmans.com/shop/product/963603'),
      ('H-E-B',None,'https://www.heb.com/product-detail/kevin-s-natural-foods-paleo-chipotle-lime-chicken/3760036'),
      ('ShopRite','butter-chicken-family-size','https://www.shoprite.com/product/kevins-natural-foods-butter-chicken-family-size-28-oz-id-00810264028197'),
      ('Hy-Vee','cilantro-lime-rice','https://www.hy-vee.com/aisles-online/p/3913578/kevins-natural-foods-cilantro-lime-rice'),
      ('FreshDirect','chicken-marsala','https://www.freshdirect.com/deli_prepared/meals/meals_entrees/sc/meals_entrees_two_plus_chix/p/hmr_pid_3778155'),
      ('Instacart / Sprouts / Meijer','thai-style-coconut-chicken-frozen-bowl','https://www.instacart.com/products/41695689-kevin-s-natural-foods-thai-coconut-chicken-11-5-oz'),
      ('Amazon','mongolian-style-beef','https://www.amazon.com/Kevins-Natural-Foods-Mongolian-Style-Beef/dp/B0C2ZZLZV6'),
    ]
    path=CACHE/'other_sources.json';out=json.loads(path.read_text(encoding='utf-8')) if path.exists() else {'coverage':[],'snapshots':[],'reviews':[]}
    seen={r['url'] for r in out['coverage']}
    for source,pid,url in seeds:
        if url in seen:continue
        cov={'product_id':pid,'source':source,'url':url,'captured_at':AS_OF,'match':'discovery_exact_page' if pid else 'historical_candidate'}
        try:
            raw=fetch(url);items=[]
            for a,t in scripts(raw):
                if a.get('type')=='application/ld+json':
                    try:items.extend(walk(json.loads(t)))
                    except ValueError:pass
            products=[n for n in items if n.get('@type')=='Product' and 'kevin' in str(n.get('name','')).lower()]
            if not products:
                cov.update(status='page_unverified',note='Page request completed but exact structured product/review identity was not returned. Prior listing evidence retained; no invented zero.')
            else:
                product=products[0];cov.update(title=clean(product.get('name')),status='listing_only',note='Exact product page found; complete dated review history not exposed in structured page data.')
                rating=product.get('aggregateRating') or {}
                if rating and pid:
                    out['snapshots'].append({'product_id':pid,'source':source,'provider':source,'url':url,'rating_count':rating.get('ratingCount') or rating.get('reviewCount'),'average':rating.get('ratingValue'),'captured_at':AS_OF,'basis':'cumulative_snapshot'})
                    cov.update(status='ratings_snapshot_only')
                # JSON-LD snippets are bounded samples; never present as complete histories.
                for r in product.get('review',[]) if isinstance(product.get('review'),list) else []:
                    row=record(pid,source,source,hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest()[:20],r.get('datePublished',''),(r.get('reviewRating') or {}).get('ratingValue'),r.get('name'),r.get('reviewBody'),url)
                    if pid and row and START<=row['date']<=AS_OF:row['coverage_tier']='sample';out['reviews'].append(row)
        except Exception as e:cov.update(status='access_limited',note=str(e))
        out['coverage'].append(cov);dump(path,out);print('OTHER',source,cov['status'],flush=True)

def probe():
    urls={
        'brand':'https://www.kevinsnaturalfoods.com/products/korean-bbq-style-chicken',
        'target':'https://www.target.com/p/-/A-89908091',
        'thrive':'https://thrivemarket.com/p/kevins-natural-foods-beef-stroganoff',
        'thrive_brand':'https://thrivemarket.com/brand/kevins-natural-foods',
        'walmart':'https://www.walmart.com/browse/kevin-s-natural-foods/YnJhbmQ6S2V2aW4ncyBOYXR1cmFsIEZvb2Rz',
        'bv':'https://apps.bazaarvoice.com/deployments/mars-kevins/main_site/production/en_US/bv.js',
        'hannaford':'https://www.hannaford.com/groceries/product/kevins-natural-foods-gluten-free-korean-bbq-style-chicken-frozen-meal-9-5-oz-pkg/364431',
    }
    result={}
    for label,url in urls.items():
        try:
            raw=fetch(url)
            info={'url':url,'bytes':len(raw)}
            if label=='brand':
                j=embedded_judge(raw)
                info.update({'judge':{k:j.get(k) for k in ['product_external_id','number_of_reviews','pagination','metafield_updated_at']} if j else None,
                  'bv_attributes':re.findall(r'.{0,60}data-bv-.{0,160}',raw),
                  'bv_script_urls':re.findall(r'https[^\s"<>]+(?:bv\.js)',raw)})
            elif label=='bv':
                info['snippets']=re.findall(r'.{0,30}(?:apiKey|passkey|productId|api\.bazaarvoice).{0,80}',raw)[:15]
            else:
                info['scripts']=[{'id':a.get('id'),'type':a.get('type'),'src':a.get('src'),'size':len(t)} for a,t in scripts(raw) if len(t)>1000 or a.get('src')]
                if label.startswith('thrive'):
                    info['product_links']=sorted(set(re.findall(r'(?:https://thrivemarket.com)?/p/kevins[^"<>\s\\]+',raw)))
                    info['id_snips']=re.findall(r'.{0,50}(?:product_id|productId|review_count|rating_count).{0,80}',raw)[:20]
            result[label]=info
            print(label,json.dumps(info)[:4500],flush=True)
        except Exception as e:
            result[label]={'url':url,'error':str(e)};print(label,str(e),flush=True)
    dump(CACHE/'probe.json',result)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('command',nargs='?',default='probe');args=parser.parse_args()
    {'probe':probe,'inspect':inspect,'brand':collect_brand,'brand-refresh':lambda:collect_brand(True),'bv-probe':bv_probe,'bv':collect_bv,'discover':discover,'thrive':collect_thrive,'walmart':collect_walmart,'target':collect_target,'target-refresh':lambda:collect_target(True),'target-api-probe':target_api_probe,'others':assess_other_sources}[args.command]()
