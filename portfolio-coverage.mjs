export function coverageReason(source,rows,coverage,snapshots,allRows=[]){
  const history=rows.filter(r=>r.coverage_tier==='history').length;
  const ratings=snapshots.filter(s=>s.rating_count>0);
  const knownTotal=ratings.length?Math.max(...ratings.map(s=>s.rating_count)):null;
  if(source==='Instacart (hosted review pool)' && coverage.some(c=>c.feed_end_reached))return {label:'Hosted reviews counted under their origins',detail:'Public written-review feeds were retrieved. Records are attributed to Kevin’s, Sprouts or Meijer where disclosed, not counted again as Instacart reviews. Displayed pool totals can exceed returned dated text.',knownTotal};
  if(rows.length)return {label:history?'Dated evidence collected':'Partial / archived evidence',detail:history?'Some retrieved histories contribute. This does not certify every product or the entire retailer.':'Records exist, but not a complete current history. Select “All collected evidence + samples” to include them.',knownTotal};
  if(ratings.length)return {label:'Ratings visible; dated history missing',detail:`${ratings.length} matched listing snapshot(s) show ratings. The largest observed listing has ${knownTotal}; this is not a unique retailer total. Dated review records have not been collected for this selection.`,knownTotal};
  if(allRows.some(r=>r.source===source))return {label:'No records for this selection',detail:'This source has collected records elsewhere in the assortment. None match the selected products/formats.',knownTotal};
  if(coverage.some(c=>c.status==='access_limited'))return {label:'Access limited',detail:'A tested page was blocked, timed out, or required an unavailable access path. Review availability is unknown—not zero.',knownTotal};
  if(coverage.some(c=>['listing_only','listing_no_dated_payload','prior_listing_evidence'].includes(c.status)))return {label:'Listing found; history uncollected',detail:'Product-page evidence exists, but a usable dated review feed was not established. Coverage is incomplete.',knownTotal};
  if(coverage.length)return {label:'Page / identity not confirmed',detail:'The available response did not establish a usable exact-product dated review history. Further matching or access work remains.',knownTotal};
  return {label:'Not fully assessed',detail:'This is a discovery candidate or an unmatched product/source combination. A complete listing and pagination audit has not been performed.',knownTotal};
}
