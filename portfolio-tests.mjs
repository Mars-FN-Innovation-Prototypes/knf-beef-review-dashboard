import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {stats,selectRows,quarterly,csvCell} from './portfolio-metrics.mjs';

const read=n=>JSON.parse(readFileSync(new URL(`./data/${n}.json`,import.meta.url),'utf8'));
const s=read('portfolio_summary'),rows=read('portfolio_reviews'),products=new Map(s.products.map(p=>[p.id,p]));
const defaults={category:'all',product:'all',source:'all',format:'all',evidence:'history',weighting:'reviews',incentives:false,written:false,currentOnly:false};
assert.equal(s.products.filter(p=>p.current_assortment).length,105);
assert.equal(new Set(s.products.map(p=>p.category)).size,11);
assert.equal(products.size,s.products.length);
assert.equal(s.default_quarters.length,8);
assert.deepEqual([s.default_quarters[0],s.default_quarters.at(-1),s.current_quarter],['2024-Q3','2026-Q2','2026-Q3']);
assert.equal(rows.length,s.quality.unique_records);
assert.equal(new Set(rows.map(r=>r.id)).size,rows.length);
const fields=new Set(['product_id','source','display_source','provider','provider_review_id','date','rating','title','text','written','incentive','source_url','captured_at','date_basis','review_pool_id','record_origin','coverage_tier','id','quarter','observed_on']);
for(const r of rows){
  assert.ok(products.has(r.product_id));
  assert.ok(r.date>=s.start_date&&r.date<=s.as_of);
  assert.ok(Number.isInteger(r.rating)&&r.rating>=1&&r.rating<=5);
  assert.equal(r.quarter,`${r.date.slice(0,4)}-Q${Math.ceil(Number(r.date.slice(5,7))/3)}`);
  assert.ok(r.source_url.startsWith('https://'));
  assert.ok(['disclosed','not_disclosed_or_unknown'].includes(r.incentive));
  assert.ok(Object.keys(r).every(k=>fields.has(k)),`Unexpected public field: ${Object.keys(r).filter(k=>!fields.has(k))}`);
  assert.equal(r.written,Boolean(r.title||r.text));
}
const selected=selectRows(rows,products,defaults,s.default_quarters),series=quarterly(selected,s.default_quarters);
assert.equal(series.reduce((n,q)=>n+q.n,0),selected.length);
for(const q of series){const rs=selected.filter(r=>r.quarter===q.quarter);assert.equal(q.average,rs.length?rs.reduce((a,r)=>a+r.rating,0)/rs.length:null);}
assert.ok(!selected.some(r=>r.coverage_tier==='sample'||r.quarter===s.current_quarter));
assert.ok(selectRows(rows,products,{...defaults,evidence:'all'},s.default_quarters).length>=selected.length);
assert.ok(!selectRows(rows,products,{...defaults,incentives:true},s.default_quarters).some(r=>r.incentive==='disclosed'));
assert.ok(!selectRows(rows,products,{...defaults,currentOnly:true},s.default_quarters).some(r=>!products.get(r.product_id).current_assortment));
assert.ok(!selectRows(rows,products,{...defaults,written:true},s.default_quarters).some(r=>!r.written));
const comp=selectRows(rows,products,{...defaults,weighting:'comparable'},s.default_quarters);
for(const r of comp){assert.equal(new Set(comp.filter(x=>x.product_id===r.product_id&&x.source===r.source).map(x=>x.quarter)).size,8);}
assert.equal(stats([]).average,null);
assert.equal(stats([{product_id:'a',source:'x',rating:1},{product_id:'a',source:'x',rating:1},{product_id:'b',source:'x',rating:5}]).average,7/3);
assert.equal(stats([{product_id:'a',source:'x',rating:1},{product_id:'a',source:'x',rating:1},{product_id:'b',source:'x',rating:5}],'products').average,3);
assert.ok(csvCell('=WEBSERVICE("bad")').startsWith('"\''));
assert.ok(csvCell(' +SUM(1)').startsWith('"\''));
assert.equal(csvCell('line,"two"'),'"line,""two"""');
for(const page of ['index.html','stir-fry.html'])assert.ok(readFileSync(new URL(page,import.meta.url),'utf8').includes('href="portfolio.html"'));
console.log('Portfolio integrity and calculation tests passed.');
console.log(JSON.stringify({default_n:selected.length,comparable_n:comp.length,quarters:series.map(q=>({quarter:q.quarter,n:q.n,average:q.average,products:q.products,sources:q.sources}))},null,2));
