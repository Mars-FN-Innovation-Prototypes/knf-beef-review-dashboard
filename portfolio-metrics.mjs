export function stats(rows, weighting = 'reviews') {
  const n = rows.length;
  if (!n) return {n:0,average:null,lowShare:null,products:0,sources:0,incentiveShare:null};
  let groups = [rows];
  if (weighting !== 'reviews') {
    const map = new Map();
    for (const r of rows) {
      const key = weighting === 'products' ? r.product_id : `${r.product_id}|${r.source}`;
      if (!map.has(key)) map.set(key, []);
      map.get(key).push(r);
    }
    groups = [...map.values()];
  }
  return {n, average:groups.reduce((s,g)=>s+g.reduce((a,r)=>a+r.rating,0)/g.length,0)/groups.length,
    lowShare:groups.reduce((s,g)=>s+g.filter(r=>r.rating<=2).length/g.length,0)/groups.length,
    products:new Set(rows.map(r=>r.product_id)).size,sources:new Set(rows.map(r=>r.source)).size,
    incentiveShare:rows.filter(r=>r.incentive==='disclosed').length/n};
}

export function matches(selection, value) {
  return Array.isArray(selection) ? selection.includes(value) : selection==='all'||selection===value;
}
export function sourceMatches(selection,value){
  if(Array.isArray(selection))return selection.includes(value);
  return selection==='all'||(selection==='owned'?value==="Kevin's Natural Foods":selection==='retailers'?value!=="Kevin's Natural Foods":selection===value);
}
export function selectRows(rows, products, filters, quarters) {
  let selected = rows.filter(r => {
    const p=products.get(r.product_id);
    return p && quarters.includes(r.quarter) && (filters.evidence==='all'||r.coverage_tier==='history') &&
      matches(filters.category,p.category) && matches(filters.product,r.product_id) && matches(filters.format,p.format) &&
      (!filters.currentOnly||p.current_assortment) &&
      sourceMatches(filters.source,r.source) &&
      (!filters.incentives||r.incentive!=='disclosed') && (!filters.written||r.written);
  });
  if (filters.weighting==='comparable') {
    const cells=new Map();
    for (const r of selected) {
      const key=`${r.product_id}|${r.source}`;
      if (!cells.has(key)) cells.set(key,new Set());
      cells.get(key).add(r.quarter);
    }
    const eligible=new Set([...cells].filter(([,q])=>quarters.every(x=>q.has(x))).map(([key])=>key));
    selected=selected.filter(r=>eligible.has(`${r.product_id}|${r.source}`));
  }
  return selected;
}

export function quarterly(rows, quarters, weighting='reviews') {
  return quarters.map(q=>({quarter:q,...stats(rows.filter(r=>r.quarter===q),weighting)}));
}
export function csvCell(value) {
  let text=String(value??'');
  if (/^[\s]*[=+@-]/.test(text)) text="'"+text;
  return '"'+text.replaceAll('"','""')+'"';
}
