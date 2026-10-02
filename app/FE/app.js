let editingProjectId = null;
const state = { project: null, assets: [], relationships: [], graph: null };
const $ = (id) => document.getElementById(id);
const API_BASE_URL = window.SURFACE_MAP_API_BASE_URL;
const apiUrl = (path) => new URL(path, API_BASE_URL).href;
const watchingRuns = new Set();

async function api(url, options) {
  const response = await fetch(apiUrl(url), options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(Array.isArray(data.detail) ? data.detail.map(e => `${e.loc.join('.')}: ${e.msg}`).join('; ') : (data.detail || response.statusText));
  return data;
}

function badge(status) { return `<span class="status ${status}">${status.replace('_', ' ')}</span>`; }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
function safeUrl(value) { try { const url = new URL(value); return ['http:', 'https:'].includes(url.protocol) ? escapeHtml(url.href) : '#'; } catch { return '#'; } }

async function refreshProjects(selectedId) {
  const projects = await api('/api/projects');
  $('projectList').innerHTML = projects.length ? projects.map(p => `<button class="projectItem ${p.id === selectedId ? 'active' : ''}" data-id="${p.id}">${escapeHtml(p.organization_name)}<small>${escapeHtml(p.root_domain)} · ${p.mode}</small></button>`).join('') : '<p class="muted">No projects yet.</p>';
  document.querySelectorAll('.projectItem').forEach(btn => btn.onclick = () => loadProject(btn.dataset.id).catch(showError));
  return projects;
}

async function loadProject(projectId) {
  $('claimPanel').hidden = true; $('assetPanel').hidden = true;
  $('sourcePanel').hidden = true;
  state.project = await api(`/api/projects/${projectId}`);
  state.relationships = await api(`/api/projects/${projectId}/relationships`);
  state.graph = await api(`/api/projects/${projectId}/graph`);
  $('emptyState').hidden = true; $('appView').hidden = false;
  $('projectName').textContent = state.project.project.organization_name;
  $('projectMode').textContent = `${state.project.project.mode} mode`;
  $('projectMeta').textContent = `${state.project.project.official_website} · allowlist: ${state.project.project.allowed_domains.join(', ')} · full mode respects ${state.project.project.mode} scope`;
  $('csvLink').href = apiUrl(`/api/projects/${projectId}/report.csv`);
  $('jsonLink').href = apiUrl(`/api/projects/${projectId}/report.json`); $('htmlLink').href = apiUrl(`/api/projects/${projectId}/report.html`);
  $('assetType').innerHTML = '<option value="">All types</option>' + [...new Set(state.project.assets.map(a => a.asset_type))].sort().map(t => `<option>${escapeHtml(t)}</option>`).join('');
  renderStats(); renderAssets(); renderRelationships(); renderGraph(); renderDashboard();
  renderSocial(); renderCollectorLogs();
  await refreshProjects(projectId);
  closeNavigation();
  try { window.localStorage?.setItem('surface-map-project', projectId); } catch {}
  syncCollectionButtons();
  const activeRun = (state.project.runs || []).find(run => ['queued','running'].includes(run.status));
  if (activeRun) watchCollection(projectId, {...activeRun, run_id:activeRun.id}).catch(showError);
}

function renderStats() {
  const p=state.project, confirmed=p.assets.filter(a=>a.status==='confirmed').length;
  const review=p.relationships.filter(r=>r.status==='needs_review').length;
  const card=(featured,label,total,leftLabel,leftValue,rightLabel,rightValue,footer,chip,mark)=>`<article class="inventoryCard ${featured?'featured':''}"><div class="cardBody"><p class="cardEyebrow">${label}</p><div class="cardNumber">${total}</div><img class="cardChip" src="./assets/${chip}.png" alt="" /><div class="cardFacts"><div><p class="cardEyebrow">${leftLabel}</p><strong>${escapeHtml(leftValue)}</strong></div><div><p class="cardEyebrow">${rightLabel}</p><strong>${escapeHtml(rightValue)}</strong></div></div></div><div class="cardFooter"><span>${escapeHtml(footer)}</span><picture><source media="(max-width:480px)" srcset="./assets/${mark}Mobile.svg" /><img src="./assets/${mark}.svg" alt="" /></picture></div></article>`;
  $('stats').innerHTML=card(true,'Total assets',p.assets.length,'ORGANIZATION',p.project.organization_name,'CONFIRMED',confirmed,p.project.root_domain,'imgChipCard','imgGroup17')+card(false,'Evidence-backed links',p.relationships.length,'SAVED SOURCES',p.sources.length,'NEEDS REVIEW',review,'Traceable inventory','imgChipCard1','imgGroup18');
}

function renderSocial() {
  const accounts = state.project.social_accounts || [];
  $('socialRows').innerHTML = accounts.map(a => `<tr><td>${escapeHtml(a.platform)}</td><td><a href="${safeUrl(a.profile_url)}" target="_blank" rel="noreferrer">${escapeHtml(a.profile_url)}</a></td><td>${badge(a.verification_status)}</td><td>${escapeHtml(a.verification_reason)}</td></tr>`).join('') || '<tr><td colspan="4" class="muted">No social records. Add a public URL or manual export when creating a project.</td></tr>';
}

function renderCollectorLogs() {
  const logs = state.project.collector_logs || [];
  $('collectorRows').innerHTML = logs.map(l => `<tr><td>${escapeHtml(l.collector)}</td><td>${badge(l.status === 'ok' ? 'confirmed' : l.status === 'error' ? 'needs_review' : 'discovered')}</td><td>${l.records_count}</td><td>${l.duration_ms} ms</td><td>${escapeHtml(l.message)}</td></tr>`).join('') || '<tr><td colspan="5" class="muted">No collector logs available.</td></tr>';
}

function renderAssets() {
  const q = $('assetSearch').value.toLowerCase(), type = $('assetType').value, status = $('assetStatus').value, source = $('assetSource').value.toLowerCase();
  const classification = $('assetClass').value, minRank = Number($('assetConfidence').value), seenAfter = $('assetSeenAfter').value ? new Date($('assetSeenAfter').value).getTime() : 0;
  const sourceMatches = (a) => !source || (state.project.observations || []).some(o => { const s = state.project.sources.find(s => s.id === o.source_id); return o.asset_id === a.id && s && `${s.source_name} ${s.source_url}`.toLowerCase().includes(source); });
  const items = state.project.assets.filter(a => (!q || `${a.display_value} ${a.canonical_value}`.toLowerCase().includes(q)) && (!type || a.asset_type === type) && (!status || a.status === status) && sourceMatches(a) && (!classification || a.classification === classification) && (!seenAfter || new Date(a.last_seen_at).getTime() >= seenAfter) && (!minRank || state.relationships.some(r => r.confidence >= minRank && ((r.subject_type === 'asset' && r.subject_id === a.id) || (r.object_type === 'asset' && r.object_id === a.id)))));
  $('assetRows').innerHTML = items.map(a => `<tr data-asset="${a.id}" class="assetRow"><td>${escapeHtml(a.asset_type)}</td><td><strong>${escapeHtml(a.display_value)}</strong></td><td>${badge(a.status)}</td><td>${a.source_url ? `<a href="${safeUrl(a.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(a.source_name || a.source_url)}</a>` : '<span class="muted">none</span>'}</td></tr>`).join('') || '<tr><td colspan="4" class="muted">No matching assets.</td></tr>';
  document.querySelectorAll('.assetRow').forEach(row => row.onclick = () => showAsset(row.dataset.asset).catch(showError));
}

async function showAsset(id) {
  const asset = await api(`/api/projects/${state.project.project.id}/assets/${id}`);
  $('assetPanel').hidden = false;
  $('assetContent').innerHTML = `<h3>${escapeHtml(asset.display_value)}</h3>` + asset.observations.map(o => `<p>${escapeHtml(o.observed_at)} · ${escapeHtml(o.source_url)}<br><small>SHA-256: ${escapeHtml(o.content_hash)}</small></p>`).join('');
  $('assetContent').innerHTML += `<p>Classification: ${escapeHtml(asset.classification)}</p><label>Classification <select id="assetClassification"><option>controlled</option><option>third_party</option><option>candidate</option><option>insufficient_evidence</option><option>rejected</option></select></label><label>Reason <input id="assetReason" placeholder="Evidence for this classification" /></label><button id="saveAssetReview" class="primary">Save classification</button>`;
  $('assetContent').innerHTML += '<h3>Classification history</h3>' + asset.reviews.map(r => `<p>${escapeHtml(r.reviewed_at)} · ${escapeHtml(r.classification)} · ${escapeHtml(r.rationale)}</p>`).join('');
  $('assetClassification').value = asset.classification;
  $('saveAssetReview').onclick = async () => {
    try {
      const reviewed = await api(`/api/projects/${state.project.project.id}/assets/${id}`, {method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({classification:$('assetClassification').value,rationale:$('assetReason').value})});
      const item = state.project.assets.find(a => a.id === id);
      if(item) item.classification = reviewed.classification;
      renderAssets();
      await showAsset(id);
    } catch(error) {showError(error);}
  };
  $('assetPanel').scrollIntoView({behavior:'smooth'});
}

function renderRelationships() {
  const selected=$('relationshipStatus').value;
  $('relationshipRows').innerHTML = state.relationships.filter(r=>!selected||r.status===selected).map(r => `<tr data-claim="${r.id}" class="claimRow"><td>${escapeHtml(r.subject_label)}</td><td>${escapeHtml(r.predicate)}</td><td>${escapeHtml(r.object_label)}</td><td>${escapeHtml(r.relation_class || 'unknown')}</td><td>${badge(r.status)}</td><td>${r.confidence.toFixed(2)} rank</td><td>${r.source_url ? escapeHtml(r.source_url) : '<span class="muted">No source</span>'}</td></tr>`).join('') || '<tr><td colspan="7" class="muted">No matching relationships.</td></tr>';
  document.querySelectorAll('.claimRow').forEach(row => row.onclick = () => showClaim(row.dataset.claim).catch(showError));
}

async function showClaim(id) {
  const claim = await api(`/api/projects/${state.project.project.id}/claims/${id}`);
  $('claimPanel').hidden = false;
  $('claimContent').innerHTML = `<dl><dt>Status</dt><dd>${badge(claim.status)}</dd><dt>Class</dt><dd>${escapeHtml(claim.relation_class || 'unknown')}</dd><dt>Predicate</dt><dd>${escapeHtml(claim.predicate)}</dd><dt>Confidence</dt><dd>${claim.confidence.toFixed(2)} rank (heuristic)</dd><dt>Source</dt><dd>${claim.source_url ? `<a href="${safeUrl(claim.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(claim.source_url)}</a>` : 'none'}</dd><dt>Collected</dt><dd>${escapeHtml(claim.source_collected_at || claim.evidence_collected_at || '')}</dd></dl><blockquote>${escapeHtml(claim.quote || 'No valid evidence quote; review required.')}</blockquote><p>${escapeHtml(claim.rationale || '')}</p><div class="actions"><button class="primary" onclick="reviewClaim('${claim.id}','confirmed')">Confirm</button><button class="secondary" onclick="reviewClaim('${claim.id}','needs_review')">Needs review</button><button class="secondary" onclick="reviewClaim('${claim.id}','rejected')">Reject</button></div>`;
  $('claimContent').innerHTML += '<h3>Review history</h3>' + claim.reviews.map(r => `<p>${escapeHtml(r.reviewed_at)} · ${escapeHtml(r.reviewer)} · ${escapeHtml(r.previous_status)} → ${escapeHtml(r.status)} · ${escapeHtml(r.rationale || '')}</p>`).join('');
  $('claimContent').innerHTML += '<h3>Evidence history</h3>' + claim.evidence_history.map(e => `<p>${escapeHtml(e.source_url)} · ${escapeHtml(e.collected_at)} · ${escapeHtml(e.validity)} · ${escapeHtml(e.role)}<br><small>SHA-256: ${escapeHtml(e.content_hash)}</small></p>`).join('');
  $('claimContent').innerHTML += '<h3>Attach supporting or counter-evidence</h3><select id="evidenceSource">' + state.project.sources.map(s => `<option value="${s.id}">${escapeHtml(s.source_name)}</option>`).join('') + '</select><select id="evidenceRole"><option>supports</option><option>refutes</option></select><textarea id="evidenceQuote" placeholder="Exact quote from saved snapshot"></textarea><button id="attachEvidenceBtn" class="secondary">Attach evidence</button>';
  $('attachEvidenceBtn').onclick = async () => { try { await api(`/api/projects/${state.project.project.id}/claims/${id}/evidence`, {method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({source_id:$('evidenceSource').value,quote:$('evidenceQuote').value,role:$('evidenceRole').value})}); await loadProject(state.project.project.id); await showClaim(id); } catch(error) { showError(error); } };
  $('claimPanel').scrollIntoView({behavior:'smooth', block:'start'});
}

async function reviewClaim(id, status) {
  try {
  await api(`/api/projects/${state.project.project.id}/claims/${id}`, {method:'PATCH', headers:{'Content-Type':'application/json'}, body:JSON.stringify({status})});
  await loadProject(state.project.project.id);
  await showClaim(id);
  } catch(error) { showError(error); }
}

function renderGraph() {
  const graph = $('graph'), selectedStatus = $('graphStatus').value, depth = Number($('graphDepth').value);
  let edges = state.graph.edges.filter(e => !selectedStatus || e.status === selectedStatus);
  let nodes = state.graph.nodes;
  if (depth) {
    let seen = new Set(nodes.filter(n => n.kind === 'organization').map(n => n.id)), frontier = new Set(seen);
    for (let i=0; i<depth; i++) {
      const next = new Set();
      edges.forEach(e => { if(frontier.has(e.source)) next.add(e.target); if(frontier.has(e.target)) next.add(e.source); });
      frontier = new Set([...next].filter(id => !seen.has(id))); frontier.forEach(id => seen.add(id));
    }
    nodes = nodes.filter(n => seen.has(n.id)); edges = edges.filter(e => seen.has(e.source) && seen.has(e.target));
  }
  if (!nodes.length) { graph.innerHTML='<p>No nodes in this view.</p>'; return; }
  const width=760, height=Math.max(340, Math.ceil(nodes.length/4)*120+60), positions={};
  nodes.forEach((n,i) => {positions[n.id]={x:95+(i%4)*180,y:60+Math.floor(i/4)*120};});
  const lines=edges.map(e => {const a=positions[e.source],b=positions[e.target]; if(!a||!b)return ''; return `<g data-claim="${e.id}" class="graphEdge" tabindex="0" role="button" aria-label="Inspect ${escapeHtml(e.label)}"><line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#8a9db8" stroke-width="3"/><text x="${(a.x+b.x)/2}" y="${(a.y+b.y)/2-5}" font-size="10" text-anchor="middle">${escapeHtml(e.label)}</text></g>`;}).join('');
  const circles=nodes.map(n => {const p=positions[n.id],color=n.status==='confirmed'?'#20a34a':n.status==='related'?'#3175ed':'#e29523';return `<g><title>${escapeHtml(n.label)}</title><circle cx="${p.x}" cy="${p.y}" r="27" fill="#fff" stroke="${color}" stroke-width="3"/><text x="${p.x}" y="${p.y+4}" font-size="10" text-anchor="middle">${escapeHtml(n.label.slice(0,20))}</text><text x="${p.x}" y="${p.y+43}" font-size="9" text-anchor="middle">${escapeHtml(n.kind)}</text></g>`;}).join('');
  graph.innerHTML=`<svg viewBox="0 0 ${width} ${height}" style="height:${height}px" aria-label="Relationship graph">${lines}${circles}</svg>`;
  graph.querySelectorAll('.graphEdge').forEach(el => {el.onclick=()=>showClaim(el.dataset.claim).catch(showError);el.onkeydown=e=>{if(e.key==='Enter')el.click();};});
}

function dayKey(value) {
  const date=new Date(value);
  return Number.isNaN(date.getTime()) ? '' : date.toISOString().slice(0,10);
}

function renderDashboard() {
  const p=state.project;
  const formatDate=value=>new Date(value).toLocaleDateString('en-GB',{day:'numeric',month:'short',year:'numeric'});
  const iconSets=[['imgEllipse13','img1'],['imgEllipse10','imgPaypalPaymentPay'],['imgEllipse14','imgLayerX00201']];
  const recent=[...(p.observations||[])].sort((a,b)=>b.observed_at.localeCompare(a.observed_at)).slice(0,3);
  $('recentActivity').innerHTML=recent.map((o,i)=>{
    const asset=p.assets.find(a=>a.id===o.asset_id),icons=iconSets[i];
    if(!asset)return '';
    return `<button class="observationItem" data-observation-asset="${asset.id}"><span class="observationIcon"><span class="observationArtwork icon${i+1}"><img src="./assets/${icons[0]}.svg" alt="" /><img src="./assets/${icons[1]}.svg" alt="" /></span></span><span class="observationText"><strong>${escapeHtml(asset.display_value)}</strong><small>${escapeHtml(formatDate(o.observed_at))}</small></span>${badge(asset.status)}</button>`;
  }).join('')||'<p class="muted">No observations yet. Run a scoped collection to get started.</p>';
  document.querySelectorAll('[data-observation-asset]').forEach(button=>button.onclick=()=>showAsset(button.dataset.observationAsset).catch(showError));
  const days=Array.from({length:7},(_,i)=>{const date=new Date();date.setUTCDate(date.getUTCDate()-6+i);return date.toISOString().slice(0,10);});
  const assets=days.map(day=>new Set((p.observations||[]).filter(o=>dayKey(o.observed_at)===day).map(o=>o.asset_id)).size);
  const sources=days.map(day=>p.sources.filter(s=>dayKey(s.collected_at)===day).length);
  const maximum=Math.max(4,...assets,...sources),top=Math.ceil(maximum/4)*4;
  const grid=Array.from({length:5},(_,i)=>{const y=24+i*43;return `<line x1="40" x2="630" y1="${y}" y2="${y}" stroke="#f3f3f5"/><text x="31" y="${y+4}" fill="#718ebf" font-size="11" text-anchor="end">${top-i*top/4}</text>`;}).join('');
  const bars=days.map((day,i)=>{const x=67+i*81,ah=assets[i]/top*172,sh=sources[i]/top*172;return `<g><title>${day}: ${assets[i]} assets, ${sources[i]} sources</title><rect x="${x}" y="${196-ah}" width="15" height="${ah}" rx="7" fill="#16dbcc"/><rect x="${x+25}" y="${196-sh}" width="15" height="${sh}" rx="7" fill="#1814f3"/><text x="${x+20}" y="220" text-anchor="middle" fill="#718ebf" font-size="11">${new Date(day+'T00:00:00Z').toLocaleDateString('en-GB',{weekday:'short',timeZone:'UTC'})}</text></g>`;}).join('');
  $('activityChart').innerHTML=`<svg viewBox="0 0 650 235" role="img" aria-label="Daily distinct assets and saved sources over the last seven UTC days">${grid}${bars}</svg>`;
  const categories=[['confirmed','Confirmed','#343c6a'],['related','Related','#1814f3'],['discovered','Discovered','#16dbcc'],['needs_review','Needs review','#ffbb38'],['rejected','Rejected','#fe5c73']].map(([status,label,color])=>({status,label,color,count:p.assets.filter(a=>a.status===status).length})).filter(item=>item.count);
  const polar=(angle,radius)=>[130+Math.cos(angle)*radius,130+Math.sin(angle)*radius];
  let angle=-Math.PI/2;
  const slices=categories.map((item,index)=>{
    const share=item.count/p.assets.length, end=angle+share*Math.PI*2, radius=108-index*4;
    const startPoint=polar(angle,radius), endPoint=polar(end,radius), label=polar((angle+end)/2,radius*.6);
    const shape=share===1?`<circle cx="130" cy="130" r="${radius}" fill="${item.color}"/>`:
      `<path d="M130 130 L${startPoint.join(' ')} A${radius} ${radius} 0 ${share>.5?1:0} 1 ${endPoint.join(' ')} Z" fill="${item.color}" stroke="white" stroke-width="4" stroke-linejoin="round"/>`;
    angle=end;
    return shape+(share>=.08?`<text x="${label[0]}" y="${label[1]+4}" text-anchor="middle" fill="white" font-size="13" font-weight="600">${Math.round(share*100)}%</text>`:'');
  }).join('');
  const pieLabel=categories.map(c=>c.label+': '+c.count).join(', ')||'No assets';
  $('assetBreakdown').innerHTML=`<svg class="statusPie" viewBox="0 0 260 260" role="img" aria-label="${escapeHtml(pieLabel)}">${slices||'<circle cx="130" cy="130" r="100" fill="#e6eff5"/><text x="130" y="134" text-anchor="middle" fill="#718ebf" font-size="14">No assets</text>'}</svg><div class="pieLegend">${categories.map(c=>`<span><i style="background:${c.color}"></i>${c.label} ${c.count}</span>`).join('')}</div>`;
  const values=days.map(day=>(p.observations||[]).filter(o=>dayKey(o.observed_at)===day).length);
  const high=Math.ceil(Math.max(4,...values)/4)*4;
  const points=values.map((value,i)=>[45+i*80,190-value/high*155]);
  const path=points.map((point,i)=>(i?'L':'M')+point.join(' ')).join(' ');
  const historyGrid=Array.from({length:5},(_,i)=>`<line x1="45" x2="525" y1="${35+i*38.75}" y2="${35+i*38.75}" stroke="#dfe7fa" stroke-dasharray="3 4"/><text x="35" y="${39+i*38.75}" fill="#718ebf" font-size="11" text-anchor="end">${high-i*high/4}</text>`).join('');
  $('historyChart').innerHTML=`<svg viewBox="0 0 550 225" role="img" aria-label="Saved observation count over the last seven UTC days"><defs><linearGradient id="historyFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#2d60ff" stop-opacity=".22"/><stop offset="100%" stop-color="#2d60ff" stop-opacity=".02"/></linearGradient></defs>${historyGrid}<path d="${path} L525 190 L45 190 Z" fill="url(#historyFill)"/><path d="${path}" stroke="#1814f3" stroke-width="2.5" fill="none"/>${points.map(([x,y],i)=>`<circle cx="${x}" cy="${y}" r="3" fill="#1814f3"><title>${days[i]}: ${values[i]} observations</title></circle><text x="${x}" y="215" text-anchor="middle" fill="#718ebf" font-size="11">${days[i].slice(5)}</text>`).join('')}</svg>`;
  $('sourcesRows').innerHTML=p.sources.map(s=>`<tr class="sourceRow" data-source="${s.id}" tabindex="0"><td><strong>${escapeHtml(s.source_name)}</strong><br><small>${escapeHtml(s.source_url)}</small></td><td>${escapeHtml(formatDate(s.collected_at))}</td><td><span class="sourceHash" title="${escapeHtml(s.content_hash)}">${escapeHtml(s.content_hash)}</span></td></tr>`).join('')||'<tr><td colspan="3" class="muted">No saved sources.</td></tr>';
  document.querySelectorAll('.sourceRow').forEach(row=>{row.onclick=()=>showSource(row.dataset.source).catch(showError);row.onkeydown=event=>{if(event.key==='Enter')row.click();};});
}

async function showSource(id) {
  const source=await api(`/api/projects/${state.project.project.id}/sources/${id}`);
  $('sourcePanel').hidden=false;
  $('sourceContent').innerHTML=`<p>${escapeHtml(source.source_name)} · ${escapeHtml(source.source_url)}</p><p class="muted">SHA-256: ${escapeHtml(source.content_hash)}</p><pre class="sourceSnapshot">${escapeHtml(source.raw_content||'No textual content in this snapshot.')}</pre>`;
  $('sourcePanel').scrollIntoView({behavior:'smooth'});
}

function closeNavigation() {
  $('sidebar').classList.remove('open');
  $('menuBtn').setAttribute('aria-expanded','false');
}

document.querySelectorAll('a.navItem').forEach(link=>link.onclick=()=>{
  document.querySelectorAll('.navItem').forEach(item=>item.classList.remove('active'));
  link.classList.add('active');
  $('pageTitle').textContent=link.querySelector('span:last-child').textContent;
  if(link.hash!=='#workspaceSection')closeNavigation();
});
$('menuBtn').onclick=()=>{const open=$('sidebar').classList.toggle('open');$('menuBtn').setAttribute('aria-expanded',String(open));};
$('profileBtn').onclick=()=>{$('sidebar').classList.add('open');$('menuBtn').setAttribute('aria-expanded','true');$('workspaceSection').scrollIntoView({behavior:'smooth'});};
$('headerSettings').onclick=$('navSettings').onclick=()=>state.project?$('editProjectBtn').click():$('newProjectBtn').click();
$('notificationsBtn').onclick=()=>{if(!state.project)return;$('relationshipStatus').value='needs_review';renderRelationships();$('relationshipsSection').scrollIntoView({behavior:'smooth'});};
$('globalSearch').addEventListener('input',()=>{if(!state.project)return;$('assetSearch').value=$('globalSearch').value;renderAssets();});
$('globalSearch').addEventListener('keydown',event=>{if(event.key==='Enter'&&state.project)$('assetsSection').scrollIntoView({behavior:'smooth'});});
$('relationshipStatus').onchange=renderRelationships;
$('emptyDemoBtn').onclick=()=>loadDemo().catch(showError);

async function loadDemo() { const result = await api('/api/demo/load', {method:'POST'}); $('runMessage').hidden=false; $('runMessage').textContent=result.message; await loadProject(result.project_id); }

$('demoBtn').onclick = () => loadDemo().catch(showError);
$('cancelProjectBtn').onclick = () => { editingProjectId=null; $('projectDialog').close(); };
function openDomainSetup() {
  $('domainSetupForm').reset();
  $('setupError').hidden = true;
  $('setupSubmit').disabled = false;
  $('cancelSetupBtn').disabled = false;
  $('setupSubmit').textContent = 'Bắt đầu';
  $('setupDialog').showModal();
}
$('newProjectBtn').onclick = openDomainSetup;
$('startProjectBtn').onclick = openDomainSetup;
$('cancelSetupBtn').onclick = () => $('setupDialog').close();
$('setupDialog').addEventListener('cancel', event => {
  if ($('setupSubmit').disabled) event.preventDefault();
});
$('domainSetupForm').onsubmit = async event => {
  event.preventDefault();
  if ($('setupSubmit').disabled) return;
  const domain = $('setupDomain').value.trim();
  if (!domain) return;
  $('setupSubmit').disabled = true;
  $('cancelSetupBtn').disabled = true;
  $('setupSubmit').textContent = 'Đang khởi tạo…';
  $('setupError').hidden = true;
  try {
    const result = await api('/api/projects/setup', {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({domain})
    });
    $('setupDialog').close();
    await loadProject(result.project.id);
    await watchCollection(result.project.id, result.collection);
  } catch (error) {
    if ($('setupDialog').open) {
      $('setupError').textContent = error.message;
      $('setupError').hidden = false;
    } else showError(error);
  } finally {
    $('setupSubmit').disabled = false;
    $('cancelSetupBtn').disabled = false;
    $('setupSubmit').textContent = 'Bắt đầu';
  }
};
$('editProjectBtn').onclick = () => { if(!state.project)return; const p=state.project.project; editingProjectId=p.id; $('projectForm').querySelector('h2').textContent='Edit project'; $('projectForm').querySelector('button[value="default"]').textContent='Save'; ['organization_name','official_website','root_domain','mode','notes'].forEach(key=>$('projectForm').elements.namedItem(key).value=p[key]||''); ['allowed_domains','aliases','brands','authorized_assets'].forEach(key=>$('projectForm').elements.namedItem(key).value=(p[key]||[]).join(', ')); ['known_social_accounts','authorized_scopes'].forEach(key=>$('projectForm').elements.namedItem(key).value=JSON.stringify(p[key]||[],null,2)); $('projectDialog').showModal(); };
$('projectForm').onsubmit = async (event) => { event.preventDefault(); const form = new FormData(event.target); const payload = Object.fromEntries(form.entries()); payload.allowed_domains = payload.allowed_domains.split(',').map(v => v.trim()).filter(Boolean); payload.aliases = payload.aliases.split(',').map(v => v.trim()).filter(Boolean); payload.brands = payload.brands.split(',').map(v => v.trim()).filter(Boolean); payload.authorized_assets = payload.authorized_assets.split(',').map(v => v.trim()).filter(Boolean); try { payload.authorized_scopes = payload.authorized_scopes.trim() ? JSON.parse(payload.authorized_scopes) : []; payload.known_social_accounts = payload.known_social_accounts.trim() ? JSON.parse(payload.known_social_accounts) : []; } catch (error) { showError(new Error('Known social accounts must be valid JSON')); return; } try { const created = await api(editingProjectId ? `/api/projects/${editingProjectId}` : '/api/projects', {method:editingProjectId ? 'PUT' : 'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)}); $('projectDialog').close(); editingProjectId=null; await loadProject(created.id); } catch (error) { showError(error); } };
function syncCollectionButtons() {
  const busy = (state.project?.runs || []).some(run => ['queued','running'].includes(run.status));
  $('collectBtn').disabled = busy;
  $('fullCollectBtn').disabled = busy;
}

async function watchCollection(projectId, initial) {
  const runId = initial.run_id || initial.id;
  if (watchingRuns.has(runId)) return;
  watchingRuns.add(runId);
  let result = initial;
  try {
    while (['queued','running'].includes(result.status)) {
      if (state.project?.project.id === projectId) {
        $('collectBtn').disabled = true;
        $('fullCollectBtn').disabled = true;
        $('runMessage').hidden = false;
        $('runMessage').style.background = '';
        $('runMessage').style.color = '';
        $('runMessage').textContent = result.status === 'queued'
          ? 'Đã khởi tạo. Đang chờ thu thập tự động…'
          : `Đang thu thập và phân tích AI · ${(result.collectors || []).length} bước đã xong`;
      }
      await new Promise(resolve => setTimeout(resolve,700));
      result = await api(`/api/projects/${projectId}/runs/${runId}`);
    }
    if (state.project?.project.id === projectId) {
      await loadProject(projectId);
      $('runMessage').hidden = false;
      const steps = (result.collectors || []).map(item => `${item.collector}: ${item.status}`).join(', ');
      const completed = result.status === 'completed';
      $('runMessage').textContent = (completed ? 'Hoàn tất thu thập và phân tích.' : `Tác vụ kết thúc: ${result.status}.`) + (steps ? ` ${steps}` : '');
      $('runMessage').style.background = completed ? '' : '#fff2dc';
      $('runMessage').style.color = completed ? '' : '#8f6215';
    }
  } finally {
    watchingRuns.delete(runId);
    syncCollectionButtons();
  }
}

async function runCollection(profile) {
  if (!state.project) return;
  const projectId = state.project.project.id;
  $('collectBtn').disabled = true;
  $('fullCollectBtn').disabled = true;
  try {
    const result = await api(`/api/projects/${projectId}/collect`, {
      method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({profile})
    });
    if (state.project?.project.id === projectId) {
      state.project.runs = [{id:result.run_id,status:result.status}, ...(state.project.runs || [])];
    }
    await watchCollection(projectId, result);
  } catch (error) { showError(error); }
  finally { syncCollectionButtons(); }
}
$('collectBtn').onclick = () => runCollection('standard');
$('fullCollectBtn').onclick = () => runCollection('full');
$('deleteProjectBtn').onclick = async () => { if (!state.project) return; const projectId = state.project.project.id; if (!window.confirm(`Delete project ${state.project.project.organization_name}? This removes its assets, evidence, runs and reports.`)) return; try { await api(`/api/projects/${projectId}`, {method:'DELETE'}); state.project=null; $('appView').hidden=true; $('emptyState').hidden=false; $('claimPanel').hidden=true; $('runMessage').hidden=true; await refreshProjects(); } catch(error) { showError(error); } };
['assetSearch','assetType','assetStatus','assetSource','assetClass','assetConfidence','assetSeenAfter'].forEach(id => $(id).addEventListener('input', renderAssets));
function showError(error) { $('runMessage').hidden=false; $('runMessage').textContent=`Error: ${error.message}`; $('runMessage').style.background='#fff1f1'; $('runMessage').style.color='#8f2020'; }
refreshProjects().then(projects => {
  let selected;
  try { selected = window.localStorage?.getItem('surface-map-project'); } catch {}
  const project = projects.find(item => item.id === selected) || projects[0];
  return project ? loadProject(project.id) : null;
}).catch(showError);

['graphStatus','graphDepth'].forEach(id => $(id).addEventListener('change', renderGraph));
