const $ = (selector) => document.querySelector(selector);
const esc = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number = value => Number(value || 0).toLocaleString('en-US');
const date = value => value ? new Intl.DateTimeFormat('en-GB', {day:'2-digit',month:'short',year:'numeric',hour:'2-digit',minute:'2-digit',timeZone:'UTC',hour12:false}).format(new Date(value)) : 'Unknown';
const labels = {status:'State',priority:'Priority',assignment_group:'Assignment group',assigned_to:'Engineer',impact:'Impact',urgency:'Urgency',reassignment_count:'Reassignments',category:'Category',subcategory:'Subcategory',symptom:'Symptom'};
const state = {config:null,asOf:null,mode:'demo',view:'command',selected:null,detail:null,analysis:null,actions:[],activity:[],search:'',priority:'',offset:0,queue:null,loading:false,analysisError:'',drafts:new Map(),version:0,queueRequest:0,activityFilter:''};
const PAGE_SIZE = 10;
const priorityBadge = priority => `<span class="priority ${['Critical','High','Moderate','Low','Planning'].includes(priority) ? priority : ''}">${esc(({Critical:'P1',High:'P2',Moderate:'P3',Low:'P4',Planning:'P5'})[priority] || '—')} · ${esc(priority || 'Unknown')}</span>`;
const snapshotKey = () => `${state.selected}|${state.asOf}`;
const sameTime = (a,b) => a && b && new Date(a).getTime() === new Date(b).getTime();
const currentActions = () => state.actions.filter(a => sameTime(a.replay_as_of,state.asOf));
let toastTimer;
function toast(message,error=false){ const element=$('#toast');element.textContent=message;element.classList.toggle('error',error);element.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>element.hidden=true,5000); }
async function api(path,options={}){
  const response=await fetch(path,{...options,headers:{'Content-Type':'application/json',...options.headers},signal:AbortSignal.timeout(130000)});
  const data=await response.json();
  if(!response.ok) throw new Error(typeof data.detail==='string'?data.detail:'The request could not be completed. Check the inputs and try again.');
  return data;
}
const errorMessage=error=>error.name==='TimeoutError'?'The request timed out. Retry or switch to Demo Mode.':error.message || 'Unable to reach the local server.';
function empty(title,message){return `<div class="empty"><h2>${esc(title)}</h2><p>${esc(message)}</p></div>`;}
function setHeading(title,description,eyebrow,breadcrumb){$('#page-title').textContent=title;$('#page-description').textContent=description;$('#eyebrow').textContent=eyebrow;$('#breadcrumb').textContent=breadcrumb;}
function setModeBadge(){ const badge=$('#mode-badge');badge.className=`pill ${state.mode==='demo'?'demo-pill':'live-pill'}`;badge.textContent=state.mode==='demo'?'DEMO MODE':state.config.gemma_configured?'LIVE INFERENCE':'LIVE · SETUP REQUIRED'; }
function syncReplay(){ $('#replay-time').value=state.asOf.slice(0,19); }
function setReplay(value){state.asOf=value;state.version++;state.queueRequest++;state.queue=null;state.analysis=null;state.analysisError='';state.loading=false;state.detail=null;state.offset=0;syncReplay();route();}
function route(){
  if(!state.config?.dataset_loaded) return;
  window.scrollTo(0,0);
  const [view,id]=location.hash.slice(1).split('/');
  const next=['command','queue','investigation','history'].includes(view)?view:'command';
  state.view=next;
  document.querySelectorAll('[data-nav]').forEach(el=>{el.classList.toggle('active',el.dataset.nav===next);if(el.dataset.nav===next)el.setAttribute('aria-current','page');else el.removeAttribute('aria-current');});
  if(next==='investigation'){
    let selected=id?decodeURIComponent(id):state.selected || state.config.default_incident;
    if(selected!==state.selected){state.version++;state.selected=selected;state.analysis=null;state.detail=null;state.analysisError='';state.loading=false;state.actions=[];}
    loadInvestigation();
  } else if(next==='history'){loadActivity();} else {renderQueueShell();loadQueue();}
}
function renderQueueShell(){
  const command=state.view==='command';
  setHeading(command?'Incident Command Center':'Incident Queue',command?'A clear view of the incident. A considered next step.':'Search real incidents and investigate their state at the selected replay point.','OPERATIONS WORKSPACE',command?'Command Center':'Incident Queue');
  $('#content').innerHTML=`${command?'<section class="metrics" id="metrics" aria-label="Incident summary"></section><div id="spotlight"></div>':''}
    <section class="panel"><div class="panel-heading"><div><h2>Incident queue <span class="count" id="queue-count">…</span></h2><p>Point-in-time records, ordered by priority</p></div><div class="table-controls"><div class="search-wrap"><span aria-hidden="true">⌕</span><label class="sr-only" for="incident-search">Search incident ID</label><input id="incident-search" placeholder="Search incident ID…" value="${esc(state.search)}" maxlength="100"></div><label class="sr-only" for="priority-filter">Filter by priority</label><select id="priority-filter"><option value="">All priorities</option>${['Critical','High','Moderate','Low','Planning'].map(p=>`<option ${p===state.priority?'selected':''}>${p}</option>`).join('')}</select></div></div>
    <div class="table-scroll"><table><caption class="sr-only">Incident snapshots at the selected replay timestamp</caption><thead><tr><th scope="col">Incident ID</th><th scope="col">Priority</th><th scope="col">Incident state</th><th scope="col">Category</th><th scope="col">Assignment group</th><th scope="col">Last updated</th><th scope="col"><span class="sr-only">Investigate</span></th></tr></thead><tbody id="incident-rows"><tr><td colspan="7">Loading real incident records…</td></tr></tbody></table></div><div class="table-footer"><span id="queue-range">Loading snapshot…</span><div class="pager"><button class="button secondary small" id="previous-page" aria-label="Previous page">←</button><span id="page-number">Page 1</span><button class="button secondary small" id="next-page" aria-label="Next page">→</button></div></div></section>`;
  if(command && state.queue)renderMetrics();
  let timer;
  $('#incident-search').addEventListener('input',e=>{state.search=e.target.value;state.offset=0;clearTimeout(timer);timer=setTimeout(loadQueue,220);});
  $('#priority-filter').addEventListener('change',e=>{state.priority=e.target.value;state.offset=0;loadQueue();});
  $('#previous-page').onclick=()=>{state.offset=Math.max(0,state.offset-PAGE_SIZE);loadQueue();};
  $('#next-page').onclick=()=>{state.offset+=PAGE_SIZE;loadQueue();};
}
function renderMetrics(){
  if(!$('#metrics')||!state.queue)return;
  const c=state.queue.counts;
  $('#metrics').innerHTML=[['Unique incidents',c.unique_incidents,'At the selected replay point','▦',''],['Critical incidents',c.critical,'P1 · Immediate attention','!','critical'],['High-priority incidents',c.high,'P2 · Elevated priority','↗','high'],['Require investigation',c.unresolved,'Unresolved in source history','⌕','pending']].map(([label,value,sub,icon,cls])=>`<div class="metric ${cls}"><div class="metric-top">${label}<span class="metric-icon" aria-hidden="true">${icon}</span></div><div class="metric-value">${number(value)}</div><small>${sub}</small></div>`).join('');
  $('#spotlight').innerHTML=`<section class="spotlight"><div class="spotlight-intro"><div class="spotlight-symbol" aria-hidden="true">✧</div><div><div class="eyebrow">FROM SIGNAL TO NEXT STEP</div><h2>Your investigation starts with the evidence.</h2><p>Explore ${esc(state.config.default_incident)}, review triage suggestions, and record your decisions.</p></div></div><button class="button secondary" id="open-demo">Open demo incident <span aria-hidden="true">↗</span></button></section>`;
  $('#open-demo').onclick=()=>{setReplay(state.config.default_as_of);location.hash=`investigation/${state.config.default_incident}`;};
}
async function loadQueue(){
  const request=++state.queueRequest;
  const params=new URLSearchParams({as_of:state.asOf,search:state.search,limit:PAGE_SIZE,offset:state.offset});
  if(state.priority)params.set('priority',state.priority);
  try{
    const data=await api(`/api/incidents?${params}`);
    if(request!==state.queueRequest||!['command','queue'].includes(state.view))return;
    state.queue=data;renderMetrics();$('#queue-count').textContent=number(data.total);
    $('#incident-rows').innerHTML=data.incidents.length?data.incidents.map(i=>`<tr class="${i.priority==='Critical'?'critical-row':''}"><td><a class="incident-link" href="#investigation/${encodeURIComponent(i.incident_id)}">${esc(i.incident_id)}</a></td><td>${priorityBadge(i.priority)}</td><td><span class="state-dot ${['Closed','Resolved'].includes(i.status)?'closed':''}"></span>${esc(i.status||'Unknown')}</td><td>${esc(i.category||'Unknown')}</td><td>${esc(i.assignment_group||'Unassigned')}</td><td>${date(i.observed_at)}</td><td><a class="text-button" aria-label="Investigate ${esc(i.incident_id)}" href="#investigation/${encodeURIComponent(i.incident_id)}">↗</a></td></tr>`).join(''):'<tr><td colspan="7">No incidents match this snapshot and filter. Try another ID, priority, or replay time.</td></tr>';
    $('#queue-range').textContent=data.total?`Showing ${number(state.offset+1)}–${number(Math.min(state.offset+PAGE_SIZE,data.total))} of ${number(data.total)} incidents`:'0 matching incidents';
    $('#page-number').textContent=`Page ${Math.floor(state.offset/PAGE_SIZE)+1} of ${Math.max(1,Math.ceil(data.total/PAGE_SIZE))}`;
    $('#previous-page').disabled=state.offset===0;$('#next-page').disabled=state.offset+PAGE_SIZE>=data.total;
  }catch(error){if(request===state.queueRequest&&$('#incident-rows'))$('#incident-rows').innerHTML=`<tr><td colspan="7">${esc(errorMessage(error))}</td></tr>`;}
}
async function loadInvestigation(){
  setHeading('Incident Investigation','Understand the context. Review the evidence. Decide what comes next.','AI TRIAGE / INVESTIGATION','Investigation');
  const version=state.version,id=state.selected;
  $('#content').innerHTML='<div class="empty"><span class="spinner"></span><h2>Opening investigation…</h2></div>';
  try{
    const [detail,actions]=await Promise.all([api(`/api/incidents/${encodeURIComponent(id)}?as_of=${encodeURIComponent(state.asOf)}`),api(`/api/incidents/${encodeURIComponent(id)}/actions`)]);
    if(version!==state.version||state.view!=='investigation')return;
    state.detail=detail;state.actions=actions;renderInvestigation();
  }catch(error){if(version===state.version&&state.view==='investigation')$('#content').innerHTML=empty('Incident unavailable at this replay point',errorMessage(error)+' Use Reset demo point or return to the queue.');}
}
function renderInvestigation(){
  const i=state.detail.incident;
  const fields=[['Impact',i.impact],['Urgency',i.urgency],['Category',i.category],['Subcategory',i.subcategory],['Assignment group',i.assignment_group],['Assigned engineer',i.assigned_to||'Unassigned'],['Reassignments',i.reassignment_count],['Symptom',i.symptom],['Created / opened',date(i.opened_at)],['Last updated',date(i.observed_at)]];
  const investigated=currentActions().some(a=>a.kind==='investigated');
  $('#content').innerHTML=`<div class="investigation-top"><div class="investigation-id"><a href="#queue" class="text-button" aria-label="Back to incident queue">←</a><h2>${esc(i.incident_id)}</h2>${priorityBadge(i.priority)}<span class="pill muted-pill">${esc(i.status||'Unknown')}</span></div><button class="button secondary small" id="mark-investigated" ${investigated?'disabled':''}>${investigated?'✓ Investigated':'✓ Mark Investigated'}</button></div>
    <div class="investigation-grid"><div class="column"><section class="panel"><div class="panel-heading"><h2>Incident overview</h2><span class="count">SNAPSHOT</span></div><div class="panel-body"><dl class="metadata">${fields.map(([label,value])=>`<div><dt>${label}</dt><dd>${esc(value??'Unknown')}</dd></div>`).join('')}</dl><p class="context-note">Category, group, and engineer identifiers are anonymized. Their real-world meaning is unknown.</p></div></section>
    <section class="panel"><div class="panel-heading"><div><h2>Incident timeline <span class="count">${state.detail.timeline.length} events</span></h2><p>Recorded updates through ${date(state.asOf)}</p></div></div><div class="timeline">${state.detail.timeline.map((event,index)=>{const changes=Object.entries(event.changes);return `<div class="timeline-item"><time>${date(event.observed_at)}</time><h3>${index===0?'First recorded event':changes.length?'Incident updated':'Record updated'}</h3><p>${index===0?`${esc(event.snapshot.status||'Unknown')} · ${esc(event.snapshot.priority||'Unknown')} priority · ${esc(event.snapshot.assignment_group||'Unassigned')}`:changes.length?changes.map(([key,value])=>`${esc(labels[key]||key)} → ${esc(value||'Unknown')}`).join('<br>'):'No change in the displayed incident fields.'}</p></div>`;}).join('')}</div></section>
    <section class="panel"><div class="panel-heading"><h2>Investigation notes</h2><span class="count">SAVED LOCALLY</span></div><div class="panel-body"><label class="sr-only" for="investigation-note">Investigation note</label><textarea class="note-input" id="investigation-note" maxlength="2000" placeholder="Record what you found, what to verify, or why you made a decision…">${esc(state.drafts.get(snapshotKey())||'')}</textarea><div class="note-actions"><small>Visible in Activity History</small><button id="save-note" class="button secondary small">Save Note</button></div><div class="saved-notes" id="saved-notes"></div></div></section></div>
    <div class="column"><section class="panel ai-panel"><div class="panel-heading"><div><h2><span class="ai-mark" aria-hidden="true">✧</span> AI triage copilot</h2><p>Evidence-led recommendations. Human judgment.</p></div><small>GEMMA</small></div><div class="ai-toolbar"><label class="sr-only" for="analysis-mode">Analysis mode</label><select id="analysis-mode"><option value="demo" ${state.mode==='demo'?'selected':''}>Demo Mode · deterministic</option><option value="live" ${state.mode==='live'?'selected':''}>Live Gemma${state.config.gemma_configured?'':' · setup required'}</option></select><button id="analyze" class="button primary">✧ Analyze with Gemma</button></div><div id="analysis-content"></div><div class="review-notice"><span>◇</span> Human review required. Accepting a recommendation records a decision; it does not change infrastructure.</div></section></div></div>`;
  $('#analysis-mode').onchange=e=>{state.mode=e.target.value;state.version++;state.analysis=null;state.analysisError='';state.loading=false;setModeBadge();renderAnalysis();};
  $('#analyze').onclick=analyze;
  $('#investigation-note').oninput=e=>{state.drafts.set(snapshotKey(),e.target.value);};
  $('#save-note').onclick=async()=>{const text=$('#investigation-note').value.trim();if(!text){toast('Write a note before saving.',true);$('#investigation-note').focus();return;}const key=snapshotKey();if(await saveAction('note',text,null,$('#save-note'))){state.drafts.delete(key);if(snapshotKey()===key&&$('#investigation-note'))$('#investigation-note').value='';}};
  $('#mark-investigated').onclick=()=>saveAction('investigated','Engineer marked this replay snapshot investigated.',null,$('#mark-investigated'));
  renderNotes();renderAnalysis();
}
function renderNotes(){
  if(!$('#saved-notes'))return;
  $('#saved-notes').innerHTML=currentActions().filter(a=>a.kind==='note').slice(0,5).map(a=>`<div class="saved-note"><p>${esc(a.description)}</p><small>${date(a.created_at)} UTC · Saved</small></div>`).join('');
  const done=currentActions().some(a=>a.kind==='investigated');
  $('#mark-investigated').disabled=done;$('#mark-investigated').textContent=done?'✓ Investigated':'✓ Mark Investigated';
}
async function analyze(){
  if(state.loading)return;
  const version=state.version,id=state.selected,asOf=state.asOf,mode=state.mode;
  state.loading=true;state.analysisError='';renderAnalysis();
  try{const result=await api(`/api/incidents/${encodeURIComponent(id)}/analyze?${new URLSearchParams({as_of:asOf,mode})}`,{method:'POST'});if(version===state.version)state.analysis=result;}
  catch(error){if(version===state.version)state.analysisError=errorMessage(error);}
  finally{if(version===state.version){state.loading=false;if(state.view==='investigation'&&$('#analysis-content'))renderAnalysis();}}
}
function renderAnalysis(){
  const container=$('#analysis-content');if(!container)return;
  $('#analyze').disabled=state.loading;$('#analyze').innerHTML=state.loading?'<span class="spinner"></span> Analyzing…':'✧ Analyze with Gemma';
  if(state.loading){container.innerHTML=`<div class="ai-empty"><span class="spinner"></span><h3>Reviewing incident context…</h3><p>${state.mode==='demo'?'Preparing deterministic demo guidance from this snapshot.':'Gemma is reviewing the snapshot and timeline. This may take up to 120 seconds.'}</p></div>`;return;}
  if(state.analysisError){container.innerHTML=`<div class="error-box" role="alert">${esc(state.analysisError)}</div><div class="ai-empty"><h3>Analysis was not completed</h3><p>Your notes and decisions are saved. Retry the request, or choose Demo Mode above.</p></div>`;return;}
  if(!state.analysis){container.innerHTML=`<div class="ai-empty"><div class="ai-orb" aria-hidden="true">✧</div><h3>A second perspective on the incident.</h3><p>Review the available evidence, surface investigation hypotheses, and choose your next steps.</p><div class="capabilities"><span>Snapshot + timeline</span><span>Ranked hypotheses</span><span>Investigation steps</span></div></div><div class="panel-body" style="padding-top:0"><div class="analysis-banner ${state.mode==='live'?'live':''}">${state.mode==='demo'?'Demo Mode is active. Analysis is deterministic and uses real incident metadata. No model inference is performed.':state.config.gemma_configured?'Live mode sends this historical snapshot to the configured model provider.':'Live inference needs server credentials, endpoint, and a deployed Gemma model. Select Demo Mode to run the complete workflow now.'}</div></div>`;return;}
  const a=state.analysis;
  container.innerHTML=`<div class="panel-body"><div class="analysis-banner ${a.mode==='live'?'live':''}"><strong>${a.mode==='demo'?'DEMO ANALYSIS':'LIVE MODEL RESPONSE'}</strong> · ${esc(a.provider)}<br>Evidence cutoff: ${date(state.asOf)} · All causes below are unverified hypotheses.</div>
    <section class="analysis-section"><h3 class="section-label">Triage summary</h3><p class="analysis-summary">${esc(a.summary)}</p><div class="severity-note">${esc(a.severity)}</div></section>
    <section class="analysis-section"><h3 class="section-label">Possible root causes <span>HYPOTHESES</span></h3>${a.hypotheses.map((h,index)=>`<div class="hypothesis"><h3><span class="rank">${index+1}</span>${esc(h.cause)}</h3><p><strong>EVIDENCE</strong><br>${esc(h.evidence)}</p><p><strong>VERIFY</strong><br>${esc(h.verification)}</p></div>`).join('')}</section>
    <section class="analysis-section"><h3 class="section-label">Recommended actions <span>${a.recommended_actions.length} STEPS</span></h3><div id="action-cards"></div></section>
    <section class="analysis-section"><h3 class="section-label">Missing information</h3><ul class="info-list">${a.missing_information.map(item=>`<li>${esc(item)}</li>`).join('')}</ul><details class="checklist"><summary>Suggested Investigation Checklist</summary><p>No matching runbook source is connected. This checklist is derived from the recommendations and needs engineer review.</p><ol>${a.recommended_actions.map(item=>`<li>${esc(item.title)}</li>`).join('')}</ol></details></section></div>`;
  renderActions();
}
function renderActions(){
  if(!$('#action-cards')||!state.analysis)return;
  $('#action-cards').innerHTML=state.analysis.recommended_actions.map((action,index)=>{
    const decision=currentActions().find(a=>a.recommendation===action.title&&a.analysis_mode===state.analysis.mode&&['accept','dismiss'].includes(a.kind));
    return `<article class="action-card ${decision?.kind||''}"><h3><span class="rank">${index+1}</span>${esc(action.title)}</h3><p>${esc(action.reason)}</p><div class="action-bottom"><span class="decision-label">${decision?decision.kind==='accept'?'✓ Accepted':'− Dismissed':'Awaiting your review'}</span><div class="action-controls"><button class="button small accept-button" data-decision="accept" data-index="${index}" ${decision?.kind==='accept'?'disabled':''}>Accept</button><button class="button small dismiss-button" data-decision="dismiss" data-index="${index}" ${decision?.kind==='dismiss'?'disabled':''}>Dismiss</button></div></div></article>`;
  }).join('');
  document.querySelectorAll('[data-decision]').forEach(button=>button.onclick=()=>{const a=state.analysis.recommended_actions[Number(button.dataset.index)];saveAction(button.dataset.decision,a.title,a.title,button);});
}
async function saveAction(kind,description,recommendation,button){
  const id=state.selected,asOf=state.asOf,key=snapshotKey();
  if(button.disabled)return false;
  const controls=button.closest('.action-controls');
  if(controls)controls.querySelectorAll('button').forEach(b=>b.disabled=true);else button.disabled=true;
  try{
    const record=await api(`/api/incidents/${encodeURIComponent(id)}/actions`,{method:'POST',body:JSON.stringify({kind,description,recommendation,replay_as_of:asOf,analysis_mode:recommendation?state.analysis.mode:null})});
    if(snapshotKey()===key){state.actions.unshift(record);if(state.view==='investigation'){renderNotes();renderActions();}}
    toast(({accept:'Recommendation accepted. Decision recorded.',dismiss:'Recommendation dismissed. Decision recorded.',note:'Investigation note saved.',investigated:'Snapshot marked investigated. Decision recorded.'})[kind]);return true;
  }catch(error){toast(errorMessage(error),true);if(snapshotKey()===key&&state.view==='investigation')renderActions();return false;}
  finally{if(button.isConnected&&kind!=='investigated')button.disabled=false;if(kind==='investigated'&&button.isConnected)renderNotes();}
}
async function loadActivity(){
  setHeading('Activity History','An accountable record of your investigation, one decision at a time.','ENGINEER DECISIONS','Activity History');
  $('#content').innerHTML='<div class="empty"><span class="spinner"></span><h2>Loading saved decisions…</h2></div>';
  try{const actions=await api('/api/activity');if(state.view!=='history')return;state.activity=actions;
    $('#content').innerHTML=`<section class="panel"><div class="panel-heading"><div><h2>Decision log <span class="count">${actions.length}</span></h2><p>Latest 500 entries · Persistent local audit history · Decision timestamps in UTC</p></div><label class="sr-only" for="history-search">Filter history by incident ID</label><input id="history-search" class="history-filter" placeholder="Filter by incident ID…" value="${esc(state.activityFilter)}"></div><div id="history-list"></div></section>`;
    $('#history-search').oninput=e=>{state.activityFilter=e.target.value;renderActivity();};renderActivity();
  }catch(error){if(state.view==='history')$('#content').innerHTML=empty('Could not load activity',errorMessage(error));}
}
function renderActivity(){
  const actions=state.activity.filter(a=>a.incident_id.toLowerCase().includes(state.activityFilter.toLowerCase()));
  $('#history-list').innerHTML=actions.length?actions.map(a=>`<article class="history-row"><div class="history-icon ${a.kind}">${({accept:'✓',dismiss:'−',note:'≡',investigated:'✓'})[a.kind]}</div><div><h3><button class="incident-link" data-history-id="${a.id}">${esc(a.incident_id)}</button><span class="pill muted-pill">${({accept:'Accepted',dismiss:'Dismissed',note:'Note saved',investigated:'Investigated'})[a.kind]}</span>${a.analysis_mode?`<span class="pill ${a.analysis_mode==='demo'?'demo-pill':'live-pill'}">${a.analysis_mode==='demo'?'DEMO':'LIVE'}</span>`:''}</h3><p>${esc(a.description)}</p><small>${a.replay_as_of?`Replay snapshot: ${date(a.replay_as_of)}`:'Replay timestamp not recorded for this legacy entry'}</small></div><time datetime="${esc(a.created_at)}">${date(a.created_at)} UTC</time></article>`).join(''):empty('No decisions recorded yet','Accept or dismiss a recommendation, save a note, or mark an incident investigated to start your audit trail.');
  document.querySelectorAll('[data-history-id]').forEach(button=>button.onclick=()=>{const record=state.activity.find(a=>a.id===Number(button.dataset.historyId));if(record.replay_as_of){state.asOf=record.replay_as_of;state.version++;state.analysis=null;state.loading=false;state.analysisError='';syncReplay();}location.hash=`investigation/${encodeURIComponent(record.incident_id)}`;});
}
$('#replay-form').onsubmit=e=>{e.preventDefault();const value=$('#replay-time').value;if(!value)return;const timestamp=new Date(`${value}Z`);if(!Number.isFinite(timestamp.getTime()))return toast('Choose a valid replay time.',true);setReplay(timestamp.toISOString());};
$('#demo-point').onclick=()=>{if(state.config?.default_as_of){setReplay(state.config.default_as_of);toast('Demo replay point restored.');}};
window.addEventListener('hashchange',route);
async function boot(){
  try{state.config=await api('/api/config');if(!state.config.dataset_loaded){$('#content').innerHTML=empty('Connect the incident dataset','Place incident_event_log.csv in the data folder or set RANE_INCIDENTS_CSV, then restart the server. No sample incidents or fabricated metrics are shown.');$('#dataset-info').textContent='No incident dataset loaded';return;}
    state.asOf=state.config.default_as_of;state.mode=state.config.default_mode;setModeBadge();syncReplay();
    $('#dataset-info').textContent=`${number(state.config.total_incidents)} real incidents · ${number(state.config.total_events)} events · Source time (timezone unspecified)${state.config.skipped_rows?` · ${number(state.config.skipped_rows)} invalid rows skipped`:''}`;
    route();
  }catch(error){$('#content').innerHTML=empty('Unable to load the workspace',errorMessage(error)+' Refresh to retry.');}
}
boot();
