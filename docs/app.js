'use strict';
const STORES={'0364':'Bossier City #0364','0356':'Bert Kouns #0356','0381':'Pines Road #0381'};
const $=s=>document.querySelector(s);
const safe=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[c]));
const money=v=>v===null||v===undefined||v===''?'—':new Intl.NumberFormat('en-US',{style:'currency',currency:'USD'}).format(+v);
const ts=v=>{if(!v)return '—';const d=new Date(v);return Number.isNaN(+d)?'—':new Intl.DateTimeFormat('en-US',{timeZone:'America/Chicago',dateStyle:'medium',timeStyle:'short'}).format(d)};
const url=(v,label='Source')=>{try{const a=new URL(v);return /^https?:$/.test(a.protocol)?'<a target="_blank" rel="noopener noreferrer" href="'+safe(a.href)+'">'+safe(label)+' ↗</a>':'—'}catch{return '—'}};
const table=(heads,rows)=>rows.length?'<div class="table-wrap"><table class="table"><thead><tr>'+heads.map(x=>'<th>'+safe(x)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(row=>'<tr>'+row.map(c=>'<td>'+c+'</td>').join('')+'</tr>').join('')+'</tbody></table></div>':'<div class="empty">No verified records available for this view. This does not imply products are unavailable.</div>';
let state={},filter='',tab='overview';
const filtered=xs=>(xs||[]).filter(x=>!filter||x.store_id===filter);
function alertText(message,warning=false){let el=$('#notice');el.hidden=!message;el.innerHTML=message?(warning?'Warning: ':'Note: ')+safe(message):'';}
function switchTab(target){if(!document.getElementById(target))return;tab=target;document.querySelectorAll('.tab-page').forEach(e=>e.hidden=e.id!==target);document.querySelectorAll('.nav').forEach(b=>b.classList.toggle('active',b.dataset.tab===target));$('#pageTitle').textContent=({overview:'Overview',clearance:'Clearance',leads:'Penny Leads',community:'Free Source Reports',monday:'Monday Checklist',history:'Scan History',sources:'Sources & Health'})[target]||target;window.scrollTo(0,0)}
const rowLink=r=>'<button class="text-btn show-history" data-sku="'+safe(r.sku)+'" data-store="'+safe(r.store_id)+'">History</button>';
const priceRows=r=>['<b>'+safe(STORES[r.store_id]||r.store_id)+'</b><small> · '+safe(r.sku)+'</small>',safe(r.name),money(r.price),r.drop_pct==null?'—':safe(r.drop_pct)+'%',safe(r.score??0)+'/100',safe(r.confidence||'Unknown'),url(r.source_url),rowLink(r)];
function readChecks(){try{return JSON.parse(localStorage.getItem('penny_watch_checks')||'[]')}catch{return []}}
function renderChecks(){let e=$('#checksTable');if(e)e.innerHTML=table(['Store','SKU','Outcome','Notes','Time'],readChecks().slice(-80).reverse().map(x=>[safe(STORES[x.store_id]||x.store_id),safe(x.sku),safe(x.result),safe(x.notes),ts(x.checked_at)]));}
function render(){
 let leads=filtered(state.leads||[]),clearance=filtered(state.clearance||[]),monday=filtered(state.monday||[]),runs=state.runs||[],last=runs[0];
 $('#metricCatalog').textContent=Number(state.tracked_count||0).toLocaleString();
 $('#metricObservations').textContent=Number(state.observation_count||0).toLocaleString();
 $('#metricLeads').textContent=new Set([...leads.map(x=>x.sku),...(state.community_leads||[]).map(x=>x.sku)]).size;
 $('#metricClearance').textContent=clearance.filter(x=>+x.drop_pct>=60).length;
 $('#metricLastScan').textContent=last?ts(last.started_at):'Never';
 $('#metricLastStatus').textContent=last?safe(last.status||'unknown').replaceAll('_',' '):'No scan recorded';
 $('#syncLabel').textContent=last?'Last run: '+(last.status||'unknown').replaceAll('_',' ')+' · '+ts(last.started_at):'Waiting for first scan';
 $('#coverage').innerHTML=Object.entries(STORES).map(([id,name])=>{let obs=Number(last?.observed_by_store?.[id]||0),expected=last?.expected_by_store?.[id];let pct=expected?Math.min(100,100*obs/expected):0;return '<div class="coverage-row"><div class="coverage-label"><b>'+safe(name)+'</b><small>'+obs+' in last run · '+(expected==null?'coverage unknown':'expected '+expected)+'</small></div><div class="bar"><div style="width:'+pct+'%"></div></div></div>'}).join('');
 const localPreview=leads.slice().sort((a,b)=>(b.score||0)-(a.score||0)).slice(0,12).map(priceRows);
 const communityPreview=(state.community_leads||[]).slice().sort((a,b)=>(b.la_reports||0)-(a.la_reports||0)||(b.priority_score||0)-(a.priority_score||0)).slice(0,12).map(r=>[
  'Store unverified / '+safe(r.sku),safe(r.name),
  'No local price','—',safe(r.priority_score)+'/100',
  'LA: '+safe(r.la_reports||0)+' · nearby: '+safe(r.neighbor_reports||0),
  url(r.source_url,r.source),''
 ]);
 $('#overviewLeads').innerHTML=table(
  ['Store / SKU','Product','Observed','Drop','Priority','Evidence','Source',''],
  localPreview.length?localPreview:communityPreview
 );
 $('#clearanceTable').innerHTML=table(['Store / SKU','Product','Price','Markdown','Priority','Evidence','Source',''],clearance.map(priceRows));
 $('#leadsTable').innerHTML=table(['Store / SKU','Product','Price','Reports','Priority','Confidence','Sources',''],leads.filter(r=>r.report_count>0).map(r=>[safe(STORES[r.store_id])+' / '+safe(r.sku),safe(r.name),money(r.price),safe(r.report_count||0),safe(r.score||0)+'/100',safe(r.confidence||'Unverified'),(r.source_reports||[]).map(o=>url(o.source_url,o.source)).join(' · ')||'—',rowLink(r)]));
 $('#mondayTable').innerHTML=table(['','Store / SKU','Product','Price','Markdown','Priority','Evidence',''],monday.map(r=>['<input type="checkbox" aria-label="Check '+safe(r.sku)+'">',safe(STORES[r.store_id]+' / '+r.sku),safe(r.name),money(r.price),r.drop_pct==null?'—':safe(r.drop_pct)+'%',safe(r.score||0)+'/100',(r.source_reports||[]).map(o=>url(o.source_url,o.source)).join(' · ')||url(r.source_url),'<button class="text-btn check-now" data-store="'+safe(r.store_id)+'" data-sku="'+safe(r.sku)+'">Log</button>']));
 $('#runsTable').innerHTML=table(['Run','Time CT','Store observations','Total','Archive','Status'],runs.map(r=>[safe(r.id),ts(r.started_at),Object.entries(r.observed_by_store||{}).map(([k,v])=>safe(k)+': '+safe(v)).join(' · ')||'None',Object.values(r.observed_by_store||{}).reduce((a,b)=>a+(+b||0),0),r.archive?'<a href="./'+safe(r.archive)+'" download>Download ZIP ↓</a>':'—',safe(r.status)]));
 let sources=Object.entries(state.sources||{});
 $('#feedHealth').innerHTML='<p><b>'+sources.filter(x=>x[1]).length+'</b> feeds configured. A configured feed does not guarantee valid observations.</p>'+table(['Source','Status'],sources.map(([k,v])=>[safe(k),v?'Configured':'Not configured']));
 const scanHealth=$('#homeDepotHealth');
 if(scanHealth){
  const latest={};
  (state.hd_scan_checks||[]).forEach(r=>{if(!latest[r.store])latest[r.store]=r});
  scanHealth.innerHTML=table(['Store','Last attempt CT','Online prices recorded','Scan status','Reason'],Object.keys(STORES).map(st=>{
   const h=latest[st];
   return [safe(STORES[st]),h?ts(h.checked_at):'Never',safe(h?.price_rows??0),
    safe(h?.status||'Not checked'),safe(h?.reason||'No store-scoped response recorded')];
  }));
 }
 $('#comparisonsTable').innerHTML=table(['SKU','Product','Retailer','Total','Home Depot','Link'],leads.flatMap(r=>(r.offers||[]).map(o=>[safe(r.sku),safe(r.name),safe(o.retailer),money(o.total),money(r.price),url(o.source_url,'Compare')])));
 renderChecks();
 renderCommunity();
 if(last?.errors)alertText('Collection errors: '+String(last.errors),true);
 else if(!last)alertText('No real collection recorded. This page does not contain confirmed Home Depot inventory.');
 else if(last.status!=='complete_tracked_scope')alertText('Last run status: '+last.status+'. Full inventory coverage is NOT established.',true);
 else alertText('Tracked-source scan completed. This is not a verified scan of every Home Depot product.');
}
function downloadCSV(filename,rows){const data=rows.map(x=>x.map(v=>'"'+String(v??'').replaceAll('"','""')+'"').join(',')).join('\r\n');const blob=new Blob(['\ufeff'+data],{type:'text/csv;charset=utf-8'});const a=document.createElement('a');let u=URL.createObjectURL(blob);a.href=u;a.download=filename;a.click();setTimeout(()=>URL.revokeObjectURL(u),1000)}
async function history(sku,store){
 sku=String(sku||'').replace(/[\s-]/g,'');
 if(!/^\d{3,18}$/.test(sku))throw new Error('Use an exact numeric SKU.');
 let bucket=String([...sku].reduce((n,c)=>n+c.charCodeAt(0),0)%128).padStart(3,'0');
 let response=await fetch('./history/bucket-'+bucket+'.json',{cache:'no-store'});
 if(response.status===404){$('#historyChart').innerHTML='<div class="empty">No history for this SKU.</div>';$('#historyTable').innerHTML='';return}
 if(!response.ok)throw new Error('History unavailable.');
 let rows=(await response.json()).filter(x=>x.sku===sku&&x.store_id===store).sort((a,b)=>a.observed_at.localeCompare(b.observed_at));
 if(!rows.length){$('#historyChart').innerHTML='<div class="empty">No matching recorded prices.</div>';$('#historyTable').innerHTML='';return}
 let lo=Math.min(...rows.map(x=>x.price)),hi=Math.max(...rows.map(x=>x.price)),w=700,h=190,p=30;
 let x=i=>p+i*(w-2*p)/Math.max(1,rows.length-1),y=v=>h-p-(v-lo)*(h-2*p)/(hi-lo||1);
 $('#historyChart').innerHTML='<svg viewBox="0 0 '+w+' '+h+'" style="width:100%;max-height:230px"><polyline fill="none" stroke="#d4af37" stroke-width="3" points="'+rows.map((r,i)=>x(i)+','+y(r.price)).join(' ')+'"></polyline></svg><p class="footnote">'+rows.length+' recorded observations; may not reflect in-store checkout prices.</p>';
 $('#historyTable').innerHTML=table(['Observed','Price','Regular','Type','Source'],rows.reverse().map(r=>[ts(r.observed_at),money(r.price),money(r.regular_price),safe(r.price_type),url(r.source_url)]))
}
document.querySelectorAll('[data-tab]').forEach(el=>el.onclick=()=>switchTab(el.dataset.tab));
document.querySelectorAll('[data-jump]').forEach(el=>el.onclick=()=>switchTab(el.dataset.jump));
$('#storeFilter').onchange=e=>{filter=e.target.value;render()};
$('#reload').onclick=()=>load();
$('#mondayLink').onclick=()=>switchTab('monday');
$('#printMonday').onclick=()=>{switchTab('monday');print()};
$('#exportMonday').onclick=()=>location.href='./data/monday-checklist.csv';
$('#exportLeads').onclick=()=>location.href='./data/penny-leads.csv';
$('#checkForm').onsubmit=e=>{e.preventDefault();let o={sku:$('#checkSku').value.trim().replace(/[\s-]/g,''),store_id:$('#checkStore').value,result:$('#checkResult').value,notes:$('#checkNotes').value,checked_at:new Date().toISOString()};if(!/^\d{3,18}$/.test(o.sku)){alertText('Enter the exact SKU.',true);return}let checks=readChecks();checks.push(o);localStorage.setItem('penny_watch_checks',JSON.stringify(checks.slice(-250)));renderChecks();e.target.reset();alertText('Saved only in this browser, not synchronized to the public site.')};
$('#historyForm').onsubmit=async e=>{e.preventDefault();try{await history($('#historySku').value,$('#historyStore').value)}catch(err){alertText(err.message,true)}};
document.addEventListener('click',e=>{let h=e.target.closest('.show-history');if(h){$('#historySku').value=h.dataset.sku;$('#historyStore').value=h.dataset.store;switchTab('history');history(h.dataset.sku,h.dataset.store).catch(err=>alertText(err.message,true))}let c=e.target.closest('.check-now');if(c){$('#checkSku').value=c.dataset.sku;$('#checkStore').value=c.dataset.store;switchTab('monday')}});
async function load(){try{const r=await fetch('./data/dashboard.json?x='+Date.now(),{cache:'no-store'});if(!r.ok)throw Error('Data file not published ('+r.status+')');state=await r.json();render()}catch(e){alertText(e.message,true)}}
load();

function renderCommunity(){
 const list=state.community_leads||[];
 const q=($('#communitySearch')?.value||'').trim().toLowerCase();
 const region=$('#communityRegion')?.value||'all';
 const rows=list.filter(r=>{
  const query=(r.sku+' '+r.name+' '+r.brand).toLowerCase();
  const geographically=region==='la'?(r.la_reports||0)>0:region==='near'?(r.la_reports||0)+(r.neighbor_reports||0)>0:true;
  return (!q||query.includes(q))&&geographically;
 });
 const summary=$('#communitySummary');
 if(summary){
  const last=state.sources_detail?.find(s=>s.source==='Penny Recon');
  summary.textContent=last?.status==='ok'
   ?'Source refreshed '+ts(last.last_success_at)+'. '+list.length+' community SKU leads. No Bossier or Shreveport prices verified by this feed.'
   :last?.status==='error'
    ?'Public feed failed on last attempt. Previous leads are retained where available; treat them as potentially stale.'
    :'No successfully imported community feed yet. This view does not establish available inventory.';
 }
 const target=$('#communityTable');
 if(target)target.innerHTML=table(
  ['SKU','Product','State evidence','Reports','Reported score','Last seen','Source'],
  rows.slice(0,500).map(r=>[
   safe(r.sku),'<b>'+safe(r.name)+'</b><small> '+safe(r.brand)+'</small>',
   'LA: '+safe(r.la_reports||0)+' · nearby: '+safe(r.neighbor_reports||0),
   safe(r.report_count||0)+' <small>('+safe(r.source_count||1)+' reported sources)</small>',
   safe(r.priority_score)+'/100',ts(r.reported_at),
   url(r.source_url,r.source)
  ])
 );
 const mondayBox=$('#mondayCommunityTable');
 if(mondayBox){
  const regional=list.filter(r=>(r.la_reports||0)+(r.neighbor_reports||0)>0)
   .sort((a,b)=>(b.la_reports||0)-(a.la_reports||0)||(b.priority_score||0)-(a.priority_score||0))
   .slice(0,35);
  mondayBox.innerHTML=table(
   ['SKU','Product','LA reports','Nearby reports','Reported last','Source'],
   regional.map(r=>[
    safe(r.sku),safe(r.name),
    safe(r.la_reports||0),safe(r.neighbor_reports||0),ts(r.reported_at),
    url(r.source_url,'Report only')
   ])
  );
 }
 const sources=$('#freeSourceTable');
 if(sources){
  const details=state.sources_detail||[];
  const names=['Penny Recon','PennyCentral manual','PennyLoot manual','Spotted manual','hdscanner','2scraper','omkar'];
  sources.innerHTML=table(['Source','Collection','Last status','Last success','Reference'],names.map(name=>{
   const h=details.find(x=>x.source===name);
   const origin={
    'Penny Recon':'https://www.pennyrecon.com/',
    'PennyCentral manual':'https://www.pennycentral.com/penny-list',
    'PennyLoot manual':'https://www.pennyloot.com/',
    'Spotted manual':'https://www.spottedflips.com/penny',
    hdscanner:'https://github.com/KenStager/HDScanner',
    '2scraper':'https://github.com/2scraper/homedepot-scraper',
    omkar:'https://github.com/omkarcloud/homedepot-scraper'
   }[name];
   return [safe(name),safe(name==='Penny Recon'?'Published JSON':'Manual / permitted export'),
    safe(h?.status||'Not imported'),ts(h?.last_success_at),url(origin,'Source')];
  }));
 }
}
$('#communitySearch').oninput=renderCommunity;
$('#communityRegion').onchange=renderCommunity;
$('#exportCommunity').onclick=()=>location.href='./data/community-leads.csv';
