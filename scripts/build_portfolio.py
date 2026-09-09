"""Build an isolated, reproducible portfolio dataset from sanitized public evidence."""
from collections import Counter, defaultdict
import argparse, hashlib, json, re
from pathlib import Path
from portfolio_sources import ROOT, CACHE, AS_OF, START, registry, record, dump, clean

DATA=ROOT/'data'
def load(path):return json.loads(path.read_text(encoding='utf-8'))
def quarter(day):return day[:4]+'-Q'+str((int(day[5:7])-1)//3+1)
def fingerprint(r):
    text=clean(r.get('text','')).lower()
    text=re.sub(r'^\[this review was collected as part of a promotion\.\]\s*','',text)
    text=re.sub(r'\W+','',text)
    return (r['product_id'],r['date'],r['rating'],text) if len(text)>45 else None

def build(from_cache=False):
    products=registry();ids={p['id'] for p in products}
    stir=load(DATA/'stir_fry_product_registry.json')['products']
    club={p['handle'] for p in stir if p.get('cohort')=='costco_only'}
    for p in products:
        if p['id'] in club:p['format']='Club stir-fry'
        elif p['category']=='Stir-Fry Entrées':p['format']='Grocery stir-fry'
        p['name']=p['name'].replace('General Tso�s','General Tso’s').replace('General Tso�s','General Tso’s')
    raw=[];coverage=[];snapshots=[]
    archive=DATA/'portfolio_source_evidence.json'
    evidence=load(archive) if archive.exists() and not from_cache else {}
    completed={'legacy_window_retrieved','history_retrieved','window_retrieved'}
    for name in ['brand','thrive','walmart','target','other_sources','instacart']:
        path=CACHE/(name+'.json')
        if name not in evidence and not path.exists():continue
        d=evidence.get(name) or load(path);evidence[name]=d;cov=d.get('coverage',[])
        good_urls={r['url'] for r in cov if r['status'] in completed}
        for r in d.get('reviews',[]):
            r['coverage_tier']='history' if r['source_url'] in good_urls else 'sample'
            raw.append(r)
        coverage.extend(cov);snapshots.extend(d.get('snapshots',[]))
    # Preserve existing evidence without touching the original modules or rewriting
    # an old capture date to imply a fresh retailer visit.
    crosswalk={p['id']:p['handle'] for p in load(DATA/'sku_registry.json')['products']}
    crosswalk.update({p['product_id']:p['handle'] for p in stir})
    prior_count=0
    for file,cutoff in [('reviews_normalized.json','2026-07-22'),('stir_fry_reviews_normalized.json','2026-08-27')]:
        for r in load(DATA/file):
            pid=crosswalk.get(r['product_id']);day=r.get('date') or ''
            if pid not in ids or r.get('metric_eligible') is False or not START<=day<=AS_OF:continue
            source=r['source']; rid=r.get('provider_review_id') or 'archive-'+hashlib.sha256(json.dumps(r,sort_keys=True).encode()).hexdigest()[:20]
            row=record(pid,source,r.get('provider') or source,rid,day,r.get('rating'),r.get('title'),r.get('text'),r.get('source_url') or '',r.get('incentivized') or r.get('transparency_badges'))
            if not row:continue
            row['captured_at']=cutoff;row['record_origin']='previous_module'
            row['coverage_tier']='sample' # Existing archives are useful but not a September-complete portfolio audit.
            raw.append(row);prior_count+=1
    # Keep the best retrieval tier when an older observation overlaps a current one.
    raw.sort(key=lambda r:(r['coverage_tier']!='history',r['record_origin']=='previous_module',r['source']!="Kevin's Natural Foods"))
    unique=[];byid={};bytext={};duplicates=[];excluded=[]
    for r in raw:
        if r['product_id'] not in ids or not START<=r['date']<=AS_OF or not 1<=r['rating']<=5:
            excluded.append({'reason':'identity_date_or_rating','record':r.get('provider_review_id')});continue
        key=(r['provider'],r['provider_review_id'])
        textkey=fingerprint(r)
        prior=byid.get(key) or (bytext.get(textkey) if textkey else None)
        if prior is not None:
            duplicates.append({'provider_review_id':r['provider_review_id'],'product_id':r['product_id'],'source':r['display_source'],'reason':'stable_id_or_same_product_date_rating_text'})
            if r['display_source'] not in prior['observed_on']:prior['observed_on'].append(r['display_source'])
            if r['incentive']=='disclosed':prior['incentive']='disclosed'
            continue
        r['id']=hashlib.sha256((r['provider']+'|'+r['provider_review_id']).encode()).hexdigest()[:24]
        r['quarter']=quarter(r['date']);r['observed_on']=[r['display_source']]
        if not r['source_url'].startswith('https://'):r['source_url']=next(p['url'] for p in products if p['id']==r['product_id'])
        unique.append(r);byid[key]=r
        if textkey:bytext[textkey]=r
    # Add older exact matches as dated evidence, never as newly verified coverage.
    for file,field in [('kevin_retailer_match_audit.json','rows'),('stir_fry_retailer_evidence_2026-08-25.json','coverage')]:
        d=load(DATA/file)
        for c in d.get(field,[]):
            pid=crosswalk.get(c['product_id']);url=c.get('page_url');source=c['source']
            if not url or pid not in ids or source=='Brand':continue
            if any(x.get('product_id')==pid and x['source']==source and x['url']==url for x in coverage):continue
            coverage.append({'product_id':pid,'source':source,'url':url,'status':'prior_listing_evidence','match':c.get('match_type'),'captured_at':d.get('as_of','2026-08-25'),'note':c.get('note') or 'Retained previous exact listing evidence; not a newly collected full history.'})
    # Current provider has a separate access contract. Do not call legacy completion
    # equivalent to complete current brand coverage.
    coverage=[c for c in coverage if c['source']!='Instacart / Sprouts / Meijer']
    snapshots=[s for s in snapshots if s['source']!='Instacart / Sprouts / Meijer']
    provider_note='Current brand pages also load Bazaarvoice. Direct current-provider history remains unavailable through the tested public endpoint. Some newer Kevin’s-origin records were retrieved from publicly hosted Instacart feeds; these do not certify complete current brand coverage. Legacy Judge.me histories are identified separately.'
    source_names=sorted(set(c['source'] for c in coverage)|set(r['source'] for r in unique)|{'Food Lion','Giant','Stop & Shop','The Fresh Market','Sprouts','Meijer'})
    tiers=[]
    for source in source_names:
        cs=[c for c in coverage if c['source']==source];rs=[r for r in unique if r['source']==source]
        tiers.append({'source':source,'dated_records':len(rs),'history_records':sum(r['coverage_tier']=='history' for r in rs),'products_with_records':len({r['product_id'] for r in rs}),
          'matched_products':len({c['product_id'] for c in cs if c.get('product_id')}),'earliest':min((r['date'] for r in rs),default=None),'latest':max((r['date'] for r in rs),default=None),
          'statuses':dict(Counter(c['status'] for c in cs)),'status':'dated_evidence' if rs else 'listing_or_access_evidence' if cs else 'discovery_candidate_no_dated_data'})
    public_snapshots=[];seen_snap=set()
    for s in snapshots:
        if s.get('product_id') not in ids:continue
        key=(s['product_id'],s['source'],s['url'],s.get('provider'))
        if key in seen_snap:continue
        seen_snap.add(key)
        try:s['average']=float(s['average']) if s.get('average') is not None else None;s['rating_count']=int(s['rating_count']) if s.get('rating_count') is not None else None
        except (TypeError,ValueError):continue
        public_snapshots.append(s)
    quarters=[f'{y}-Q{q}' for y in [2024,2025,2026] for q in range(1,5) if '2024-Q3'<=f'{y}-Q{q}'<='2026-Q3']
    quality={'raw_in_window_records':len(raw),'unique_records':len(unique),'duplicates_removed':len(duplicates),'excluded_records':len(excluded),
      'history_records':sum(r['coverage_tier']=='history' for r in unique),'sample_records':sum(r['coverage_tier']=='sample' for r in unique),'prior_archive_candidates':prior_count,
      'products_with_records':len({r['product_id'] for r in unique}),'written_records':sum(r['written'] for r in unique),'rating_only_records':sum(not r['written'] for r in unique),'disclosed_incentive_records':sum(r['incentive']=='disclosed' for r in unique)}
    output={'schema_version':1,'as_of':AS_OF,'start_date':START,'default_quarters':quarters[:-1],'current_quarter':quarters[-1],'products':products,'sources':tiers,'coverage':coverage,'snapshots':public_snapshots,'quality':quality,
      'methodology':{'metric':'Arithmetic mean of unique dated 1–5-star records submitted in each calendar quarter; not a sales-weighted or market-representative measure.',
       'default_scope':'Retrieved public histories. Partial pages and previous-module archives remain available in the all-collected view, not the default trend.',
       'dates':'Provider submission dates; no cumulative snapshot is assigned to a historical quarter. Current quarter is incomplete.',
       'duplicates':'Stable provider ID and same-product/date/rating normalized long-text duplicates are suppressed. Short generic comments are not merged by text.',
       'provider_note':provider_note,
       'retailer_scope':'Source discovery and exact matches are recorded explicitly. Unknown product/source cells are unconfirmed, not zero. Public access does not establish exhaustive market coverage.',
       'historical_scope':'105 current individual food products plus one verified historical Buffalo Sauce listing. The mixed Game Day Grill Pack is excluded. Other historical candidates remain outside metrics until their identities and dated evidence are verified; this is not a certified historical product master.',
       'incentives':'Disclosed promotions, free product and provider incentive badges are flagged. Absence of a badge is not proof a review was organic.',
       'shared_pools':'Target refrigerated Korean BBQ / Cilantro Lime / Roasted Garlic chicken shared ratings are excluded pending review-level flavor resolution.'}}
    dump(DATA/'portfolio_summary.json',output)
    dump(DATA/'portfolio_product_registry.json',products)
    # Only normalized, sanitized records and public listing metadata are frozen.
    # Raw HTML/JSON, reviewer names, widget keys and network logs stay outside Git.
    archive.write_text(json.dumps(evidence,ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    # Compact records keep the static page fast; no names/emails/locations are published.
    (DATA/'portfolio_reviews.json').write_text(json.dumps(sorted(unique,key=lambda r:(r['date'],r['id']),reverse=True),ensure_ascii=False,separators=(',',':'))+'\n',encoding='utf-8')
    dump(CACHE/'quality_audit.json',{'quality':quality,'duplicates':duplicates,'excluded':excluded})
    print(json.dumps(quality,indent=2));print('Sources',[(s['source'],s['dated_records']) for s in tiers if s['dated_records']])

if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--from-cache',action='store_true',help='Freeze a new collection from the local raw-cache directory; default rebuilds the committed sanitized snapshot.')
    build(parser.parse_args().from_cache)
