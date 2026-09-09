import {stats,selectRows,quarterly,csvCell} from './portfolio-metrics.mjs';
const $=id=>document.getElementById(id);
const esc=value=>String(value??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const num=n=>new Intl.NumberFormat('en-US').format(n);
const dec=n=>n==null?'—':n.toFixed(2);
const pct=n=>n==null?'—':`${(n*100).toFixed(1)}%`;
const qlabel=q=>q.replace(/(\d{4})-Q(\d)/,'Q$2 $1');
const OWNED="Kevin's Natural Foods";
const COLORS=['#19738D','#62BB46','#EB6916','#8C3C68','#00634D','#B45378','#7B6C00','#67728D'];
const state={summary:null,reviews:[],products:new Map(),filtered:[],quarters:[],series:[],limit:15,explorer:[]};
const checks=['qtd','incentives','written','zoom','currentOnly'];
const controls=['window','qtd','evidence','category','product','source','format','weighting','incentives','written','overlay','zoom','currentOnly'];
function filters(){return Object.fromEntries(controls.map(id=>[id,checks.includes(id)?$(id).checked:$(id).value]));}
function table(headers,rows,numeric=[]){return `<table><thead><tr>${headers.map((h,i)=>`<th scope="col" class="${numeric.includes(i)?'num':''}">${esc(h)}</th>`).join('')}</tr></thead><tbody>${rows.length?rows.map(row=>`<tr>${row.map((cell,i)=>`<td class="${numeric.includes(i)?'num':''}">${cell}</td>`).join('')}</tr>`).join(''):`<tr><td colspan="${headers.length}">No eligible evidence for this selection.</td></tr>`}</tbody></table>`;}
function option(value,label){return `<option value="${esc(value)}">${esc(label)}</option>`;}
function updateProducts(){const current=$('product').value;const category=$('category').value;const products=state.summary.products.filter(p=>(category==='all'||p.category===category)&&(!$('currentOnly').checked||p.current_assortment));$('product').innerHTML=option('all','All products')+products.map(p=>option(p.id,p.name)).join('');if(products.some(p=>p.id===current))$('product').value=current;}
function render(){
  const f=filters();state.quarters=state.summary.default_quarters.slice(-Number(f.window));if(f.qtd)state.quarters.push(state.summary.current_quarter);
  state.filtered=selectRows(state.reviews,state.products,f,state.quarters);state.series=quarterly(state.filtered,state.quarters,f.weighting);
  $('viewCount').textContent=`${num(state.filtered.length)} dated ratings`;
  const latest=state.series.find(q=>q.quarter===state.summary.default_quarters.at(-1));
  const prev=state.series.find(q=>q.quarter===state.summary.default_quarters.at(-2));
  const yoy=state.series.find(q=>q.quarter===state.summary.default_quarters.at(-5));
  const change=(a,b)=>a?.average!=null&&b?.average!=null?`${a.average-b.average>=0?'+':''}${(a.average-b.average).toFixed(2)}`:'—';
  const kpis=[['Latest completed quarter',dec(latest?.average),`${qlabel(latest.quarter)} · n = ${num(latest.n)}`],['Quarter-on-quarter',change(latest,prev),`Rating-point change · YoY ${change(latest,yoy)}`],['1–2-star share',pct(latest?.lowShare),'Among eligible ratings in latest completed quarter'],['Quarter coverage',`${latest.products} products`,`${latest.sources} sources · ${num(latest.n)} unique ratings`]];
  $('kpis').innerHTML=kpis.map(([label,value,note])=>`<article class="p-kpi"><span class="label">${esc(label)}</span><strong>${esc(value)}</strong><small>${esc(note)}</small></article>`).join('');
  const notes={reviews:'Each unique dated rating gets one vote.',products:'Each product with data gets equal weight within a quarter; the product mix can change.',comparable:'Only product/source pairs with data in every selected quarter are included. Each pair has equal, fixed weight; n is the underlying record count.'};
  $('weightNote').textContent=notes[f.weighting];
  $('trendSubtitle').textContent=`Average of collected dated ratings (out of 5) · ${$('evidence').selectedOptions[0].text} · ${qlabel(state.quarters[0])}–${qlabel(state.quarters.at(-1))}${f.qtd?' (last quarter QTD)':''}`;
  $('chartNote').textContent=`${notes[f.weighting]} Counts below each point are unique dated ratings. n < 10 is a small base. Gaps mean no eligible evidence, not zero. Retailer and product mix may change over time. ${f.evidence==='all'?'This view includes partial samples and earlier archives; treat the trend as directional.':'Current-provider and retailer access gaps remain; this is not a complete market census.'}`;
  drawChart(f);
  $('quarterTable').innerHTML=table(['Quarter','Average / 5','1–2-star share','n','Products','Sources','Disclosed incentives'],state.series.map(q=>[`<button type="button" data-quarter="${q.quarter}">${esc(qlabel(q.quarter))}${q.quarter===state.summary.current_quarter?' · QTD':''}</button>`,dec(q.average),pct(q.lowShare),num(q.n)+(q.n>0&&q.n<10?' · small base':''),num(q.products),num(q.sources),pct(q.incentiveShare)]),[1,2,3,4,5,6]);
  const old=$('detailQuarter').value;$('detailQuarter').innerHTML=state.quarters.map(q=>option(q,qlabel(q)+(q===state.summary.current_quarter?' · QTD':''))).join('');$('detailQuarter').value=state.quarters.includes(old)?old:state.summary.default_quarters.at(-1);
  state.limit=15;renderDetail();renderCoverage();
}
function drawChart(f){
  const width=960,height=390,left=60,right=30,top=32,bottom=240,n=state.quarters.length;
  let overlays=[];
  if(f.overlay!=='none'){
    const groups=new Map();for(const r of state.filtered){const k=f.overlay==='source'?r.source:state.products.get(r.product_id).category;if(!groups.has(k))groups.set(k,[]);groups.get(k).push(r);}
    overlays=[...groups].sort((a,b)=>b[1].length-a[1].length).slice(0,8).map(([name,rows],i)=>({name,color:COLORS[i],series:quarterly(rows,state.quarters,f.weighting)}));
  }
  const values=[...state.series,...overlays.flatMap(o=>o.series)].map(q=>q.average).filter(v=>v!=null);
  const min=f.zoom&&values.length?Math.max(1,Math.floor((Math.min(...values)-.15)*2)/2):1;
  const max=f.zoom&&values.length?Math.min(5,Math.ceil((Math.max(...values)+.15)*2)/2):5;
  const lo=min===max?Math.max(1,min-.5):min,hi=min===max?Math.min(5,max+.5):max;
  const x=i=>left+i*(width-left-right)/Math.max(1,n-1),y=v=>bottom-(v-lo)/(hi-lo)*(bottom-top);
  let content=`<rect width="960" height="390" fill="white"/><text x="60" y="16" font-size="11" fill="#68625e">Rating / 5${f.zoom?' · zoomed axis':''}</text>`;
  for(let v=lo;v<=hi+.001;v+=(hi-lo<=2?.5:1)){content+=`<line x1="${left}" x2="${width-right}" y1="${y(v)}" y2="${y(v)}" stroke="#e6e1dd"/><text x="45" y="${y(v)+4}" text-anchor="end" font-size="11" fill="#68625e">${v.toFixed(1)}</text>`;}
  function line(series,color,primary){let s='';for(let i=1;i<series.length;i++){if(series[i-1].average==null||series[i].average==null)continue;s+=`<line x1="${x(i-1)}" y1="${y(series[i-1].average)}" x2="${x(i)}" y2="${y(series[i].average)}" stroke="${color}" stroke-width="${primary?3:1.8}" ${series[i].quarter===state.summary.current_quarter?'stroke-dasharray="6 5"':''} opacity="${primary?1:.85}"/>`;}return s;}
  for(const o of overlays)content+=line(o.series,o.color,false);
  content+=line(state.series,'#0000A0',true);
  const maxN=Math.max(1,...state.series.map(q=>q.n));
  state.series.forEach((q,i)=>{
    const px=x(i);if(q.average!=null){content+=`<circle cx="${px}" cy="${y(q.average)}" r="6" fill="#0000A0" role="button" tabindex="0" data-quarter="${q.quarter}" aria-label="${qlabel(q.quarter)}: ${dec(q.average)} out of five, ${q.n} ratings"><title>${qlabel(q.quarter)} · ${dec(q.average)} / 5 · n=${q.n} · ${q.products} products · ${q.sources} sources</title></circle><text x="${px}" y="${y(q.average)-13}" font-size="12" font-weight="bold" fill="#0000A0" text-anchor="middle">${dec(q.average)}</text>`;}
    content+=`<text x="${px}" y="264" font-size="11" text-anchor="middle" fill="#3C3C3C">${qlabel(q.quarter)}</text>${q.quarter===state.summary.current_quarter?`<text x="${px}" y="278" font-size="9" text-anchor="middle" fill="#8c4400">QTD</text>`:''}<rect x="${px-19}" y="${335-q.n/maxN*36}" width="38" height="${q.n/maxN*36}" rx="3" fill="#c7e9bb"/><text x="${px}" y="351" font-size="11" text-anchor="middle" fill="#0000A0">n=${num(q.n)}</text>`;
  });
  content+='<text x="60" y="382" font-size="10" fill="#68625e">Unique dated ratings · Public-source evidence · Captured September 9, 2026 · Not complete market coverage</text>';
  $('chart').innerHTML=`<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${width} ${height}" role="img" aria-label="Average consumer rating by quarter with contributing review counts"><title>Average rating of collected dated reviews by quarter</title>${content}</svg>`;
  $('legend').innerHTML=[{name:'Portfolio',color:'#0000A0'},...overlays].map(o=>`<span><i class="p-dot" style="background:${o.color}"></i>${esc(o.name)}</span>`).join('')+(overlays.length===8?'<span>Top 8 by collected volume</span>':'');
}
function grouped(rows,key){const groups=new Map();for(const r of rows){const k=key(r);if(!groups.has(k))groups.set(k,[]);groups.get(k).push(r);}return [...groups].map(([name,rs])=>({name,...stats(rs)})).sort((a,b)=>b.n-a.n);}
function renderDetail(){
  const q=$('detailQuarter').value;const rows=state.filtered.filter(r=>r.quarter===q);$('detailTitle').textContent=`Inside ${qlabel(q)}${q===state.summary.current_quarter?' · quarter to date':''}`;
  $('ratingDistribution').innerHTML=table([1,2,3,4,5].map(n=>`${n} star${n===1?'':'s'}`),[[1,2,3,4,5].map(n=>{const count=rows.filter(r=>r.rating===n).length;return `${num(count)} · ${pct(rows.length?count/rows.length:null)}`;})]);
  const baseHeaders=['Group','Average / 5','1–2 stars','n'];const asRow=g=>[esc(g.name),dec(g.average),pct(g.lowShare),num(g.n)];
  $('categoryTable').innerHTML=table(baseHeaders,grouped(rows,r=>state.products.get(r.product_id).category).map(asRow),[1,2,3]);
  $('sourceTable').innerHTML=table(baseHeaders,grouped(rows,r=>r.source).map(asRow),[1,2,3]);
  $('productTable').innerHTML=table(['Product','Category','Average / 5','1–2 stars','n','Sources'],grouped(rows,r=>r.product_id).map(g=>{const p=state.products.get(g.name);return [`<button type="button" data-product="${esc(p.id)}">${esc(p.name)}</button>`,esc(p.category),dec(g.average),pct(g.lowShare),num(g.n),num(g.sources)];}),[2,3,4,5]);
  renderReviews();
}
function renderReviews(){const text=$('reviewSearch').value.toLowerCase().trim(),star=$('starFilter').value;const rows=state.filtered.filter(r=>r.quarter===$('detailQuarter').value&&(star==='all'||(star==='low'?r.rating<=2:r.rating===Number(star)))&&(!text||`${r.title} ${r.text} ${state.products.get(r.product_id).name}`.toLowerCase().includes(text)));state.explorer=rows;
  $('reviewCount').textContent=`${num(rows.length)} matching records in the selected quarter. Table averages above use individual review weighting.`;
  $('reviewList').innerHTML=rows.slice(0,state.limit).map(r=>`<article class="p-review"><div class="p-review-meta"><strong>${r.rating} / 5</strong><span>${esc(state.products.get(r.product_id).name)}</span><span>${esc(r.source)}</span><span>${r.date}</span>${r.incentive==='disclosed'?'<span class="p-badge">Disclosed incentive</span>':''}${r.coverage_tier==='sample'?'<span class="p-badge">Partial / earlier archive</span>':''}</div><h3>${esc(r.title||'Rating record')}</h3><p>${esc(r.text||'No written text supplied.')}</p><a href="${esc(r.source_url)}" target="_blank" rel="noopener noreferrer">Source listing ↗</a><span class="p-note"> · Captured ${r.captured_at}${r.observed_on.length>1?' · Also observed on '+esc(r.observed_on.join(', ')):''}</span></article>`).join('')||'<p class="p-empty">No reviews match this selection. Try another quarter or broaden the filters.</p>';
  $('moreReviews').hidden=rows.length<=state.limit;
}
function renderCoverage(){
  const f=filters(),summary=state.summary;const products=summary.products.filter(p=>(f.category==='all'||p.category===f.category)&&(f.product==='all'||p.id===f.product)&&(f.format==='all'||p.format===f.format)&&(!f.currentOnly||p.current_assortment));const ids=new Set(products.map(p=>p.id));
  const sourceMatch=s=>f.source==='all'||(f.source==='owned'?s===OWNED:f.source==='retailers'?s!==OWNED:s===f.source);
  const cov=summary.coverage.filter(c=>ids.has(c.product_id)&&sourceMatch(c.source));
  const auditRows=state.reviews.filter(r=>ids.has(r.product_id)&&sourceMatch(r.source));
  $('coverageSummary').innerHTML=`<span><strong>${num(auditRows.length)}</strong> collected dated records</span><span><strong>${new Set(auditRows.map(r=>r.product_id)).size} / ${products.length}</strong> selected products with dated evidence</span><span><strong>${num(summary.quality.duplicates_removed)}</strong> overlaps removed across the full collection</span><span>Audit covers July 2024–September 9, 2026, including samples. Product/source filters apply; quarter and review-characteristic filters do not.</span>`;
  $('sourceCoverage').innerHTML=table(['Originating source','All dated records','Retrieved histories','Products with records','Latest dated record'],summary.sources.filter(s=>sourceMatch(s.source)).map(s=>{const rs=auditRows.filter(r=>r.source===s.source);return [esc(s.source),num(rs.length),num(rs.filter(r=>r.coverage_tier==='history').length),num(new Set(rs.map(r=>r.product_id)).size),esc(rs.map(r=>r.date).sort().at(-1)||'No dated records')];}),[1,2,3]);
  const sources=summary.sources.filter(s=>sourceMatch(s.source)).map(s=>s.source);
  $('matrix').innerHTML=table(['Product',...sources],products.map(p=>[esc(p.name),...sources.map(s=>{const cells=cov.filter(c=>c.product_id===p.id&&c.source===s);if(!cells.length)return '<span title="Exact page not established in this audit">—</span>';const c=cells.find(c=>/retrieved/.test(c.status))||cells.find(c=>c.records)||cells[0];const hist=/retrieved/.test(c.status);const labels={shared_flavor_pool:'Pooled',ratings_snapshot_only:'Snapshot',access_limited:'Access gap',page_unverified:'Unverified',identity_excluded:'Excluded',error:'Unverified'};return `<a class="${hist?'hist':c.records?'sample':''}" href="${esc(c.url)}" target="_blank" rel="noopener noreferrer" title="${esc(c.status+' · '+(c.note||''))}">${hist?'History':c.records?'Sample':labels[c.status]||'Listing'}</a>`;})]));
  $('listingTable').innerHTML=table(['Product','Source','Status','Capture date','Notes'],cov.map(c=>[`<a href="${esc(c.url)}" target="_blank" rel="noopener noreferrer">${esc(state.products.get(c.product_id).name)}</a>`,esc(c.source),esc(c.status.replaceAll('_',' ')),esc(c.captured_at),esc(c.note||'')]));
  $('snapshots').innerHTML=table(['Product','Source / provider','Average / 5','Cumulative ratings','Written total','Basis','As of'],summary.snapshots.filter(s=>ids.has(s.product_id)&&sourceMatch(s.source)).map(s=>[`<a href="${esc(s.url)}" target="_blank" rel="noopener noreferrer">${esc(state.products.get(s.product_id).name)}</a>`,esc(s.source+' / '+s.provider),dec(s.average),s.rating_count==null?'—':num(s.rating_count),s.written_count==null?'—':num(s.written_count),esc(s.basis.replaceAll('_',' ')),esc(s.captured_at)]),[2,3,4]);
}
function download(name,content,type='text/csv;charset=utf-8'){const blob=new Blob([content],{type}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
function csv(headers,rows){return '\uFEFF'+[headers,...rows].map(row=>row.map(csvCell).join(',')).join('\r\n');}
function exportQuarter(){const f=filters();download('KNF_Quarterly_Ratings.csv',csv(['quarter','average_rating','low_star_share','unique_n','products','sources','evidence_scope','weighting','category','product','source','format','current_assortment_only','written_only','exclude_disclosed_incentives','is_qtd','capture_date'],state.series.map(q=>[q.quarter,q.average,q.lowShare,q.n,q.products,q.sources,f.evidence,f.weighting,f.category,f.product,f.source,f.format,f.currentOnly,f.written,f.incentives,q.quarter===state.summary.current_quarter,state.summary.as_of])));}
async function exportChart(){
  const svg=$('chart').querySelector('svg').cloneNode(true),f=filters();
  const captions=['KNF portfolio — '+$('trendSubtitle').textContent,$('weightNote').textContent,
    `Category: ${$('category').selectedOptions[0].text} · Product: ${$('product').selectedOptions[0].text}`,
    `Source: ${$('source').selectedOptions[0].text} · Format: ${$('format').selectedOptions[0].text}`,
    `Current assortment only: ${f.currentOnly} · Written only: ${f.written} · Disclosed incentives excluded: ${f.incentives}`];
  const lines=captions.flatMap(text=>text.match(/.{1,140}(?:\s|$)|\S+/g)||[text]);
  const legendItems=[...$('legend').querySelectorAll('span')].map(el=>({text:el.textContent,color:el.querySelector('i')?.style.background}));
  const height=425+lines.length*16+legendItems.length*17;
  svg.setAttribute('width','960');svg.setAttribute('height',String(height));svg.setAttribute('viewBox',`0 0 960 ${height}`);svg.setAttribute('font-family','Arial, sans-serif');
  svg.querySelector('rect').setAttribute('height',String(height));
  const ns='http://www.w3.org/2000/svg';let y=410;
  for(const text of lines){const el=document.createElementNS(ns,'text');el.setAttribute('x','60');el.setAttribute('y',String(y));el.setAttribute('font-size','10');el.setAttribute('fill','#3C3C3C');el.textContent=text;svg.append(el);y+=16;}
  for(const item of legendItems){const el=document.createElementNS(ns,'text');el.setAttribute('x','60');el.setAttribute('y',String(y));el.setAttribute('font-size','11');el.setAttribute('fill',item.color||'#3C3C3C');el.textContent='● '+item.text;svg.append(el);y+=17;}
  const xml=new XMLSerializer().serializeToString(svg);
  if($('chartFormat').value==='svg'){download('KNF_Quarterly_Rating_Trend.svg',xml,'image/svg+xml');return;}
  const url=URL.createObjectURL(new Blob([xml],{type:'image/svg+xml'}));
  try{const img=new Image();img.src=url;await img.decode();const canvas=document.createElement('canvas');canvas.width=1920;canvas.height=height*2;canvas.getContext('2d').drawImage(img,0,0,canvas.width,canvas.height);const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!blob)throw new Error('Image export failed');download('KNF_Quarterly_Rating_Trend.png',blob,'image/png');}
  catch(error){$('loadStatus').textContent='PNG export could not be created. Please choose SVG and retry.';console.error(error);}finally{URL.revokeObjectURL(url);}
}
async function boot(){try{
  const [summary,reviews]=await Promise.all(['data/portfolio_summary.json','data/portfolio_reviews.json'].map(async url=>{const r=await fetch(url);if(!r.ok)throw new Error(`Data request failed (${r.status})`);return r.json();}));
  state.summary=summary;state.reviews=reviews;state.products=new Map(summary.products.map(p=>[p.id,p]));
  $('assortmentChip').textContent=`${summary.products.filter(p=>p.current_assortment).length} current + ${summary.products.filter(p=>!p.current_assortment).length} historical products`;
  $('category').innerHTML+=Array.from(new Set(summary.products.map(p=>p.category))).map(c=>option(c,c)).join('');
  $('source').innerHTML+=summary.sources.map(s=>option(s.source,s.source+(s.dated_records?'':' · no dated data'))).join('');
  $('format').innerHTML+=Array.from(new Set(summary.products.map(p=>p.format))).map(c=>option(c,c)).join('');updateProducts();
  $('methodText').innerHTML=Object.entries(summary.methodology).map(([k,v])=>`<p><strong>${esc(k.replaceAll('_',' '))}</strong>${esc(v)}</p>`).join('');
  for(const id of controls)$(id).addEventListener('change',()=>{if(['category','currentOnly'].includes(id))updateProducts();render();});
  $('reset').addEventListener('click',()=>{for(const id of controls){if(checks.includes(id))$(id).checked=false;else $(id).selectedIndex=0;}updateProducts();$('reviewSearch').value='';$('starFilter').value='all';render();});
  $('detailQuarter').addEventListener('change',()=>{state.limit=15;renderDetail();});$('reviewSearch').addEventListener('input',()=>{state.limit=15;renderReviews();});$('starFilter').addEventListener('change',()=>{state.limit=15;renderReviews();});$('moreReviews').addEventListener('click',()=>{state.limit+=15;renderReviews();});
  document.addEventListener('click',e=>{const q=e.target.closest('[data-quarter]'),p=e.target.closest('[data-product]');if(q){$('detailQuarter').value=q.dataset.quarter;state.limit=15;renderDetail();$('breakdown').scrollIntoView({behavior:'smooth',block:'start'});}if(p){$('product').value=p.dataset.product;render();}});
  $('chart').addEventListener('keydown',e=>{if(['Enter',' '].includes(e.key)&&e.target.dataset.quarter){e.preventDefault();e.target.dispatchEvent(new MouseEvent('click',{bubbles:true}));}});
  $('exportQuarter').addEventListener('click',exportQuarter);$('exportChart').addEventListener('click',exportChart);
  $('exportReviews').addEventListener('click',()=>download('KNF_Filtered_Quarter_Reviews.csv',csv(['product','category','source','date','rating','title','text','incentive_disclosure','evidence_tier','captured_at','source_url'],state.explorer.map(r=>[state.products.get(r.product_id).name,state.products.get(r.product_id).category,r.source,r.date,r.rating,r.title,r.text,r.incentive,r.coverage_tier,r.captured_at,r.source_url]))));
  $('exportCoverage').addEventListener('click',()=>download('KNF_Portfolio_Coverage.csv',csv(['product','source','status','match','as_of','url','notes'],state.summary.coverage.map(c=>[state.products.get(c.product_id)?.name||c.title||'Unassigned',c.source,c.status,c.match,c.captured_at,c.url,c.note]))));
  $('loadStatus').textContent='';render();
}catch(error){$('loadStatus').classList.add('error');$('loadStatus').textContent='Portfolio data could not be loaded. Please refresh the page. '+error.message;console.error(error);}}
$('toggleFilters').addEventListener('click',()=>{const collapsed=document.body.classList.toggle('filters-collapsed');$('toggleFilters').setAttribute('aria-expanded',String(!collapsed));$('toggleFilters').textContent=collapsed?'Show filters':'Hide filters';});
boot();
