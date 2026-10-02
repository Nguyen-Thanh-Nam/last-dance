// Source-level logic checks; this DOM stub does not validate browser layout.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..'),fixture=JSON.parse(fs.readFileSync(0,'utf8'));
const html=fs.readFileSync(path.join(root,'FE/index.html'),'utf8');
const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(match=>match[1]);
assert.equal(new Set(ids).size,ids.length,'HTML IDs must be unique');
const setupForm=html.match(/<form id="domainSetupForm">([\s\S]*?)<\/form>/)[1];
assert.equal((setupForm.match(/<input\b/g)||[]).length,1,'Setup must require only one domain input');
assert(!/<select|<textarea/.test(setupForm),'Setup must not contain advanced fields');
const elements=new Map(ids.map(id=>[id,{id,value:'',hidden:false,innerHTML:'',textContent:'',style:{},dataset:{},listeners:{},
  addEventListener(name,handler){this.listeners[name]=handler;},setAttribute(name,value){this[name]=value;},
  scrollIntoView(){this.scrolled=true;},querySelectorAll(){return[];},querySelector(){return{value:'',textContent:''};},
  reset(){},showModal(){this.open=true;},close(){this.open=false;},
  classList:{add(){},remove(){},toggle(){return true;}},click(){this.onclick?.();}}]));
elements.get('assetConfidence').value='0';elements.get('graphDepth').value='0';
const document={getElementById(id){assert(elements.has(id),'Unknown static element: '+id);return elements.get(id);},querySelectorAll(){return[];}};
const responses=new Map([
  ['/api/projects',[]],['/api/projects/'+fixture.project.id,fixture],
  ['/api/projects/'+fixture.project.id+'/relationships',fixture.relationships],
  ['/api/projects/'+fixture.project.id+'/graph',{nodes:[],edges:[]}],
  ...fixture.sources.map(source=>['/api/projects/'+fixture.project.id+'/sources/'+source.id,source])
]);
const requests=[],stored=new Map();let rejectSetup=false;
const sandbox={document,window:{SURFACE_MAP_API_BASE_URL:'http://127.0.0.1:3333',confirm:()=>false,
  localStorage:{getItem:key=>stored.get(key),setItem:(key,value)=>stored.set(key,value)}},URL,console,setTimeout:handler=>setTimeout(handler,0),
  fetch:async (url,options={})=>{const parsed=new URL(url);assert.equal(parsed.port,'3333');
    requests.push({path:parsed.pathname,method:options.method||'GET',body:options.body?JSON.parse(options.body):null});
    if(parsed.pathname==='/api/projects/setup'&&rejectSetup)return{ok:false,json:async()=>({detail:'Invalid domain'})};
    assert(responses.has(parsed.pathname),parsed.pathname);
    const result=responses.get(parsed.pathname);
    if(parsed.pathname.includes('/runs/'))responses.get('/api/projects/'+fixture.project.id).runs=[{id:result.id,status:result.status}];
    return{ok:true,json:async()=>result};}};
vm.createContext(sandbox);vm.runInContext(fs.readFileSync(path.join(root,'FE/app.js'),'utf8'),sandbox);
(async()=>{
  await sandbox.loadProject(fixture.project.id);
  assert.equal(elements.get('appView').hidden,false);
  assert(elements.get('stats').innerHTML.includes('Total assets'));
  assert(elements.get('stats').innerHTML.includes('>'+fixture.assets.length+'</div>'));
  for(const id of ['activityChart','historyChart','assetBreakdown']){
    assert(elements.get(id).innerHTML.length>100,id);
    assert(!elements.get(id).innerHTML.includes('NaN'),id);
  }
  for(const id of ['jsonLink','csvLink','htmlLink'])assert(elements.get(id).href.startsWith('http://127.0.0.1:3333/api/projects/'));
  elements.get('globalSearch').value='app.acme';elements.get('globalSearch').listeners.input();
  const rows=elements.get('assetRows').innerHTML;
  assert.equal((rows.match(/data-asset=/g)||[]).length,2,'Global search should match both the app host and its endpoint');
  elements.get('globalSearch').value='no-such-asset';elements.get('globalSearch').listeners.input();
  assert(elements.get('assetRows').innerHTML.includes('No matching assets.'),'Search should report zero matches');
  elements.get('relationshipStatus').value='needs_review';sandbox.renderRelationships();
  assert(elements.get('relationshipRows').innerHTML.includes('No matching relationships.'));
  elements.get('relationshipStatus').value='';sandbox.renderRelationships();
  assert.equal((elements.get('relationshipRows').innerHTML.match(/data-claim=/g)||[]).length,fixture.relationships.length);
  await sandbox.showSource(fixture.sources[0].id);
  assert.equal(elements.get('sourcePanel').hidden,false);
  assert(elements.get('sourceContent').innerHTML.includes('SHA-256'));
  assert(!elements.get('sourceContent').innerHTML.includes('No textual content'));
  assert(elements.get('sourceContent').innerHTML.includes('&lt;'),'Raw HTML snapshot should be escaped');
  assert(elements.get('sourcePanel').scrolled);
  vm.runInContext(`state.project={...state.project,collector_logs:[{collector:'google_dork',status:'skipped',records_count:0,duration_ms:0,message:'API unavailable. GOOGLE_DORK_LINKS:'+JSON.stringify([{query:'site:acme.example filetype:pdf',url:'https://www.google.com/search?q=site%3Aacme.example+filetype%3Apdf'},{query:'unsafe',url:'https://evil.example/search'}])}]};renderCollectorLogs();`,sandbox);
  assert(elements.get('collectorRows').innerHTML.includes('https://www.google.com/search?q=site%3Aacme.example+filetype%3Apdf'),'Google Dork fallback should show a clickable Google query');
  assert(elements.get('collectorRows').innerHTML.includes('href="#" target="_blank" rel="noreferrer">unsafe</a>'),'Dork links must reject non-Google hosts');
  vm.runInContext('state.project={...state.project,assets:[],relationships:[],sources:[],observations:[]};renderStats();renderDashboard();',sandbox);
  assert(elements.get('recentActivity').innerHTML.includes('No observations yet.'));
  assert(elements.get('sourcesRows').innerHTML.includes('No saved sources.'));
  assert(elements.get('assetBreakdown').innerHTML.includes('No assets'));
  for(const id of ['activityChart','historyChart','assetBreakdown'])assert(!elements.get(id).innerHTML.includes('NaN'),id+' should handle an empty project');
  const active={...fixture,runs:[{id:'setup-run',status:'queued'}]};
  responses.set('/api/projects/'+fixture.project.id,active);
  responses.set('/api/projects/setup',{project:fixture.project,collection:{run_id:'setup-run',status:'queued'},created:true});
  responses.set('/api/projects/'+fixture.project.id+'/runs/setup-run',{id:'setup-run',status:'completed',collectors:[{collector:'ai',status:'ok'}]});
  elements.get('newProjectBtn').click();
  assert.equal(elements.get('setupDialog').open,true);
  elements.get('setupDomain').value='acme.example';
  await elements.get('domainSetupForm').onsubmit({preventDefault(){}});
  await new Promise(resolve=>setTimeout(resolve,20));
  const submitted=requests.find(request=>request.path==='/api/projects/setup');
  assert.deepEqual(submitted.body,{domain:'acme.example'});
  assert.equal(submitted.method,'POST');
  assert.equal(elements.get('setupDialog').open,false);
  assert(requests.some(request=>request.path.endsWith('/runs/setup-run')),'Setup should automatically track its run');
  assert(elements.get('runMessage').textContent.includes('Hoàn tất'));
  assert.equal(elements.get('collectBtn').disabled,false);
  assert.equal(stored.get('surface-map-project'),fixture.project.id);
  assert(!requests.some(request=>request.path.endsWith('/collect')),'Setup must not enqueue a second job');
  active.runs=[{id:'resume-run',status:'running'}];
  responses.set('/api/projects/'+fixture.project.id+'/runs/resume-run',{id:'resume-run',status:'completed_with_errors',collectors:[{collector:'ai',status:'error'}]});
  await sandbox.loadProject(fixture.project.id);
  await new Promise(resolve=>setTimeout(resolve,20));
  assert(requests.some(request=>request.path.endsWith('/runs/resume-run')),'Reload should resume tracking an existing job');
  assert(elements.get('runMessage').textContent.includes('completed_with_errors'));
  assert.equal(elements.get('collectBtn').disabled,false);
  rejectSetup=true;elements.get('newProjectBtn').click();elements.get('setupDomain').value='localhost';
  await elements.get('domainSetupForm').onsubmit({preventDefault(){}});
  assert.equal(elements.get('setupDialog').open,true);
  assert.equal(elements.get('setupError').hidden,false);
  assert.equal(elements.get('setupError').textContent,'Invalid domain');
  assert.equal(elements.get('setupSubmit').disabled,false);
  for(const file of [...html.matchAll(/(?:src|href)="\.\/([^"?#]+)(?:\?[^"#]*)?"/g)].map(m=>m[1])){
    const full=path.join(root,'FE',file);assert(fs.statSync(full).size>0,file);
  }
  console.log('PASS: frontend cards/charts, search, claims/sources, Google Dork links, one-domain setup, automatic collection tracking, reload resume, API errors, port 3333 and local assets.');
})().catch(error=>{console.error(error);process.exitCode=1;});
