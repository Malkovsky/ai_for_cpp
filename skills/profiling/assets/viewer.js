const model=__MODEL__,byId=new Map(),parent=new Map(),$=id=>document.getElementById(id);
function index(n,p){byId.set(n.id,n);if(p)parent.set(n.id,p);n.children.forEach(c=>index(c,n));}index(model.root,null);index(model.reverse,null);
let overall=model.root,focus=overall,pattern=null,history=[],layout='flame',sourceFunction=null;
const fmt=x=>x.toLocaleString('en-US'),pct=x=>(100*x/model.root.weight).toFixed(2)+'%',esc=s=>String(s).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function hit(n){return pattern&&pattern.test(n.name+' '+n.sources.join(' '));}
function union(n){return hit(n)?n.weight:n.children.reduce((a,c)=>a+union(c),0);}
function color(n){let h=0;for(const c of n.name)h=(h*31+c.charCodeAt(0))|0;return `hsl(${25+(h>>>0)%22},78%,${72+(h>>>4)%9}%)`;}
function depth(n){return 1+Math.max(0,...n.children.map(depth));}
function sourceRanges(n){
 const fn=model.functions[n.name];
 if(fn?.definition){const d=fn.definition,marked=new Set();for(const location of fn.sources){const m=/^(.*):(\d+)(?:\s.*)?$/.exec(location);if(m&&m[1]===d.path)marked.add(+m[2]);}return [{path:d.path,file:model.source_files[d.path],marked,ranges:[{start:d.start,end:d.end}],full:true}];}
 const files=new Map();
 for(const location of n.sources){const match=/^(.*):(\d+)(?:\s.*)?$/.exec(location);if(!match||+match[2]<1)continue;const path=match[1];if(!files.has(path))files.set(path,new Set());files.get(path).add(+match[2]);}
 return [...files].sort(([a],[b])=>a.localeCompare(b)).map(([path,marked])=>{
  const file=model.source_files[path],lines=[...marked].sort((a,b)=>a-b),ranges=[];
  for(const line of lines){const start=Math.max(1,line-3),end=Math.min(file?.line_count||line+3,line+3),last=ranges[ranges.length-1];if(last&&start<=last.end+1)last.end=Math.max(last.end,end);else ranges.push({start,end});}
  return {path,file,marked,ranges,full:false};
 });
}
function callsFor(n,path,line){return (model.functions[n.name]?.calls||[]).filter(c=>c.path===path&&c.line===line);}
function renderSource(n){
 if(sourceFunction!==n.name){$('source').scrollTop=0;sourceFunction=n.name;}
 const groups=sourceRanges(n),fn=model.functions[n.name];
 if(!groups.length){$('source').innerHTML='<p class="empty">Select a frame with source locations to inspect its function.</p>';return;}
 let html=groups.map(({path,file,marked,ranges,full})=>{
  const heading=`<div class="source-path" title="${esc(path)}">${esc(file?.display||path)}${full?'<span class="scope-label">Full function</span>':''}</div>`;
  if(!file?.available)return `<section class="source-file">${heading}<p class="empty">Source file unavailable in this export.</p></section>`;
  let code='';ranges.forEach((range,index)=>{if(index)code+='<div class="code-gap" aria-label="Omitted lines">⋯</div>';
   for(let line=range.start;line<=range.end;line++){
    const text=file.lines[String(line)];if(text===undefined)continue;
    const calls=callsFor(n,path,line),cost=calls.reduce((sum,c)=>sum+c.weight,0);
    const tip=calls.map(c=>`${c.callee}: ${pct(c.weight)} including descendants`).join('\n');
    const badge=calls.length?`<button class="line-cost" data-call-line="${line}" data-call-path="${esc(path)}" data-function="${esc(n.name)}" title="${esc(tip)}">${pct(cost)}</button>`:'<span class="line-cost empty-cost"></span>';
    code+=`<div class="code-line${marked.has(line)?' sampled':''}"><span class="line-number">${line} :</span>${badge}<code class="code-text">${esc(text)}</code></div>`;
   }
  });
  return `<section class="source-file">${heading}<div class="code-block">${code}</div></section>`;
 }).join('');
 const unresolved=fn?.calls.filter(c=>c.path===null)||[];
 if(unresolved.length)html+=`<div class="unmapped-calls">Callee samples without a resolved call line: ${unresolved.map(c=>`${esc(c.label)} ${pct(c.weight)}`).join(' · ')}</div>`;
 $('source').innerHTML=html;
}
function describe(n){
 const fn=model.functions[n.name],total=fn?.total_weight??n.weight,self=fn?.self_weight??n.self_weight;
 $('frame-name').textContent=n.name;
 $('details').innerHTML=`<span class="function-metric"><span>Total</span><strong>${pct(total)}</strong></span><span class="function-metric"><span>Self</span><strong>${pct(self)}</strong></span><span class="metric-note">of all selected sample periods · Self excludes counted callees</span>`;
 $('frame-context').textContent=`This stack occurrence: ${pct(n.weight)} · ${fmt(n.samples)} samples · ${(100*n.weight/focus.weight).toFixed(2)}% of graph focus`;
 renderSource(n);
}
function selectFunction(name){let best=null;function find(n){if(n.name===name&&(!best||n.weight>best.weight))best=n;n.children.forEach(find);}find(overall);if(best)zoom(best);}
$('source').onclick=e=>{const button=e.target.closest('[data-call-line]');if(!button)return;const calls=callsFor({name:button.dataset.function},button.dataset.callPath,+button.dataset.callLine);if(calls.length)selectFunction(calls.reduce((a,b)=>a.weight>b.weight?a:b).callee);};
function zoom(n,push=true){if(push&&n!==focus)history.push(focus.id);focus=n;render();}
function render(){let height=depth(focus)*26+35,html=`<svg viewBox="0 0 1500 ${height}" role="img" aria-label="Native perf flame graph">`;
 function draw(n,x,level,width){let y=layout==='flame'?height-28-level*26:7+level*26,tip=`${n.name}\nFunction total ${pct(model.functions[n.name]?.total_weight??n.weight)}; self ${pct(model.functions[n.name]?.self_weight??n.self_weight)}\nThis stack occurrence ${pct(n.weight)}; ${fmt(n.samples)} samples`;
 html+=`<g data-id="${n.id}" style="cursor:pointer"><title>${esc(tip)}</title><rect x="${x}" y="${y}" width="${Math.max(0,width)}" height="24" fill="${color(n)}" stroke="white" stroke-width="0.5"${hit(n)?' class="search-hit"':''}/>`;
 if(width>25){let chars=Math.max(0,Math.floor(width/7)-2),text=n.label.length>chars?n.label.slice(0,Math.max(0,chars-1))+'…':n.label;html+=`<text x="${x+4}" y="${y+16}">${esc(text)}</text>`;}html+='</g>';
 let left=x;for(const c of n.children){let w=width*c.weight/n.weight;if(w>.05)draw(c,left,level+1,w);left+=w;}}
 draw(focus,10,0,1480);html+='</svg>';$('view').innerHTML=html;
 const crumbs=[];for(let n=focus;n;n=parent.get(n.id))crumbs.push(n);$('crumbs').innerHTML=crumbs.reverse().map(n=>`<button data-id="${n.id}" title="${esc(n.name)}">${esc(n.label)}</button>`).join('<span>›</span>');
 $('match').textContent=pattern?`Matched ${pct(union(overall))} of complete window`:'';$('back').disabled=!history.length;describe(focus);renderTable();}
function renderTable(){const key=$('sort').value||'self_weight';const rows=model.hotspots.filter(n=>!pattern||hit(n)).sort((a,b)=>b[key]-a[key]);$('hotspots').innerHTML=rows.map(n=>`<tr data-name="${esc(n.name)}"><td title="${esc(n.name)}">${esc(n.label)}</td><td>${pct(n.self_weight)}</td><td>${pct(n.weight)}</td><td>${fmt(n.self_samples)}</td><td>${fmt(n.samples)}</td></tr>`).join('');}
function closestFrame(e){return e.target.closest('[data-id]');}
$('view').onclick=e=>{const el=closestFrame(e);if(el)zoom(byId.get(+el.dataset.id));};$('view').onmouseover=e=>{const el=closestFrame(e);if(el)describe(byId.get(+el.dataset.id));};$('crumbs').onclick=e=>{const el=closestFrame(e);if(el)zoom(byId.get(+el.dataset.id));};
$('reset').onclick=()=>{history=[];zoom(overall,false);};$('back').onclick=()=>{if(history.length)zoom(byId.get(history.pop()),false);};
$('direction').onchange=e=>{overall=model[e.target.value];history=[];zoom(overall,false);};$('layout').onchange=e=>{layout=e.target.value;render();};
$('search').oninput=e=>{try{pattern=e.target.value?new RegExp(e.target.value,'i'):null;$('error').textContent='';render();}catch(err){$('error').textContent='Invalid regular expression';}};$('clear').onclick=()=>{$('search').value='';pattern=null;$('error').textContent='';render();};$('sort').onchange=renderTable;
$('hotspots').onclick=e=>{const row=e.target.closest('[data-name]');if(row)selectFunction(row.dataset.name);};
const m=model.meta;
$('subtitle').textContent=m.scope||'Capture scope not specified';
$('capture').textContent=`${fmt(m.samples)} ${m.event} samples · ${fmt(m.period_weight)} period weights · ${m.functions_resolved||0} source definitions`;
$('method').textContent=[`Binary: ${m.binary}`,`SHA256: ${m.binary_sha256}`,`Root filter: ${m.root_filter||'none'}`,`Capture metadata: ${JSON.stringify(m.capture||{})}`,...(m.warnings||[])].join('\n');render();
