const state = { project: null, assets: [], relationships: [], graph: null };
const $ = (id) => document.getElementById(id);

async function api(url, options) {
  const response = await fetch(url, options);
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.detail || response.statusText);
  return data;
}

function badge(status) { return `<span class="status ${status}">${status.replace('_', ' ')}</span>`; }
function escapeHtml(value) { return String(value ?? '').replace(/[&<>\"]/g, (c) => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\\':'&#39;'}[c])); }

async function refreshProjects(selectedId) {
  const projects = await api('/api/projects');
  $('projectList').innerHTML = projects.length ? projects.map(p => `<button class="projectItem ${p.id === selectedId ? 'active' : ''}" data-id="${p.id}">${escapeHtml(p.organization_name)}<small>${escapeHtml(p.root_domain)} · ${p.mode}</small></button>`).join('') : '<p class="muted">No projects yet.</p>';
  document.querySelectorAll('.projectItem').forEach(btn => btn.onclick = () => loadProject(btn.dataset.id));
}

async function loadProject(projectId) {
  state.project = await api(`/api/projects/${projectId}`);
  state.relationships = await api(`/api/projects/${projectId}/relationships`);
  state.graph = await api(`/api/projects/${projectId}/graph`);
  $('emptyState').hidden = true; $('appView').hidden = false;
  $('projectName').textContent = state.project.project.organization_name;
  $('projectMode').textContent = `${state.project.project.mode} mode`;
  $('projectMeta').textContent = `${state.project.project.official_website} · allowlist: ${state.project.project.allowed_domains.join(', ')}`;
  $('jsonLink').href = `/api/projects/${projectId}/report.json`; $('htmlLink').href = `/api/projects/${projectId}/report.html`;
  $('assetType').innerHTML = '<option value="">All types</option>' + [...new Set(state.project.assets.map(a => a.asset_type))].sort().map(t => `<option>${escapeHtml(t)}</option>`).join('');
  renderStats(); renderAssets(); renderRelationships(); renderGraph();
  await refreshProjects(projectId);
}

function renderStats() {
  const counts = {}; state.project.assets.forEach(a => counts[a.asset_type] = (counts[a.asset_type] || 0) + 1);
  const cards = [['Total assets', state.project.assets.length], ['Confirmed', state.project.assets.filter(a => a.status === 'confirmed').length], ['Related', state.project.assets.filter(a => a.status === 'related').length], ['Needs review', state.project.assets.filter(a => a.status === 'needs_review').length], ['Relationships', state.project.relationships.length]];
  $('stats').innerHTML = cards.map(([label, value]) => `<div class="stat"><b>${value}</b><span>${label}</span></div>`).join('');
}

function renderAssets() {
  const q = $('assetSearch').value.toLowerCase(), type = $('assetType').value, status = $('assetStatus').value;
  const items = state.project.assets.filter(a => (!q || `${a.display_value} ${a.canonical_value}`.toLowerCase().includes(q)) && (!type || a.asset_type === type) && (!status || a.status === status));
  $('assetRows').innerHTML = items.map(a => `<tr><td>${escapeHtml(a.asset_type)}</td><td><strong>${escapeHtml(a.display_value)}</strong></td><td>${badge(a.status)}</td><td>${a.source_url ? `<a href="${escapeHtml(a.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(a.source_name || a.source_url)}</a>` : '<span class="muted">none</span>'}</td></tr>`).join('') || '<tr><td colspan="4" class="muted">No matching assets.</td></tr>';
}

function renderRelationships() {
  $('relationshipRows').innerHTML = state.relationships.map(r => `<tr data-claim="${r.id}" class="claimRow"><td>${escapeHtml(r.subject_label)}</td><td>${escapeHtml(r.predicate)}</td><td>${escapeHtml(r.object_label)}</td><td>${badge(r.status)}</td><td>${(r.confidence * 100).toFixed(0)}%</td><td>${r.source_url ? escapeHtml(r.source_url) : '<span class="muted">No source</span>'}</td></tr>`).join('') || '<tr><td colspan="6" class="muted">No relationships yet.</td></tr>';
  document.querySelectorAll('.claimRow').forEach(row => row.onclick = () => showClaim(row.dataset.claim));
}

async function showClaim(id) {
  const claim = await api(`/api/projects/${state.project.project.id}/claims/${id}`);
  $('claimPanel').hidden = false;
  $('claimContent').innerHTML = `<dl><dt>Status</dt><dd>${badge(claim.status)}</dd><dt>Predicate</dt><dd>${escapeHtml(claim.predicate)}</dd><dt>Confidence</dt><dd>${(claim.confidence * 100).toFixed(0)}%</dd><dt>Source</dt><dd>${claim.source_url ? `<a href="${escapeHtml(claim.source_url)}" target="_blank" rel="noreferrer">${escapeHtml(claim.source_url)}</a>` : 'none'}</dd><dt>Collected</dt><dd>${escapeHtml(claim.source_collected_at || claim.evidence_collected_at || '')}</dd></dl><blockquote>${escapeHtml(claim.quote || 'No valid evidence quote; review required.')}</blockquote><p>${escapeHtml(claim.rationale || '')}</p>`;
  $('claimPanel').scrollIntoView({behavior:'smooth', block:'start'});
}

function renderGraph() {
  const graph = $('graph'); if (!state.graph.nodes.length) { graph.innerHTML = '<p class="muted" style="padding:12px">No relationships to draw.</p>'; return; }
  const width = Math.max(680, state.graph.nodes.length * 150), height = 320, positions = {};
  state.graph.nodes.forEach((node, index) => { const col = index % 4, row = Math.floor(index / 4); positions[node.id] = {x: 90 + col * 170, y: 60 + row * 105}; });
  const line = state.graph.edges.map(e => { const a=positions[e.source], b=positions[e.target]; if(!a||!b)return ''; return `<line x1="${a.x}" y1="${a.y}" x2="${b.x}" y2="${b.y}" stroke="#9aa8bc" stroke-width="1.5"/><text x="${(a.x+b.x)/2}" y="${(a.y+b.y)/2-5}" fill="#66758b" font-size="10" text-anchor="middle">${escapeHtml(e.label)}</text>`; }).join('');
  const circles = state.graph.nodes.map(n => { const p=positions[n.id], color=n.status==='confirmed'?'#20a34a':n.status==='related'?'#3175ed':n.status==='needs_review'?'#e29523':'#8290a4'; return `<g><circle cx="${p.x}" cy="${p.y}" r="27" fill="#fff" stroke="${color}" stroke-width="3"/><text x="${p.x}" y="${p.y+4}" fill="#172033" font-size="10" text-anchor="middle">${escapeHtml(n.label).slice(0,20)}</text><text x="${p.x}" y="${p.y+43}" fill="#64748b" font-size="9" text-anchor="middle">${escapeHtml(n.kind)}</text></g>`; }).join('');
  graph.innerHTML = `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Relationship graph">${line}${circles}</svg>`;
}

async function loadDemo() { const result = await api('/api/demo/load', {method:'POST'}); $('runMessage').hidden=false; $('runMessage').textContent=result.message; await loadProject(result.project_id); }

$('demoBtn').onclick = () => loadDemo().catch(showError);
$('newProjectBtn').onclick = () => $('projectDialog').showModal();
$('projectForm').onsubmit = async (event) => { event.preventDefault(); const form = new FormData(event.target); const payload = Object.fromEntries(form.entries()); payload.allowed_domains = payload.allowed_domains.split(',').map(v => v.trim()).filter(Boolean); try { const created = await api('/api/projects', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(payload)}); $('projectDialog').close(); await loadProject(created.id); } catch (error) { showError(error); } };
$('collectBtn').onclick = async () => { if (!state.project) return; $('collectBtn').disabled=true; try { const result = await api(`/api/projects/${state.project.project.id}/collect`, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({collectors: state.project.project.mode === 'authorized' ? ['passive_web','dns','authorized_http','ai'] : ['passive_web','dns','ai']})}); $('runMessage').hidden=false; $('runMessage').textContent=`${result.status}: ${result.collectors.map(c => `${c.collector} ${c.status}`).join(', ')}`; await loadProject(state.project.project.id); } catch(error){ showError(error); } finally { $('collectBtn').disabled=false; } };
['assetSearch','assetType','assetStatus'].forEach(id => $(id).addEventListener('input', renderAssets));
function showError(error) { $('runMessage').hidden=false; $('runMessage').textContent=`Error: ${error.message}`; $('runMessage').style.background='#fff1f1'; $('runMessage').style.color='#8f2020'; }
refreshProjects().catch(showError);
