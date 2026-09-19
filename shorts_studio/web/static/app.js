const queue = document.querySelector('#queue');
const health = document.querySelector('#health');
const template = document.querySelector('#job-template');
let profile = null;
let radarPoll = null;

const esc = (s='') => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

async function jsonFetch(url, options={}) {
  const r = await fetch(url, {headers:{'Content-Type':'application/json'}, ...options});
  if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
  return r.json();
}

function showTab(name){
  document.querySelectorAll('.tab').forEach(b=>b.classList.toggle('active', b.dataset.tab===name));
  document.querySelectorAll('.tab-page').forEach(p=>p.classList.toggle('active', p.id===`tab-${name}`));
  if(name==='radar') loadRadar();
  if(name==='image') loadImages();
  if(name==='review') loadJobs();
}
document.querySelectorAll('.tab').forEach(btn=>btn.onclick=()=>showTab(btn.dataset.tab));

async function loadHealth(){
  try{
    const h = await jsonFetch('/api/health');
    const ok = h.ollama.ok && h.ollama.model_installed && h.ffmpeg.ok;
    health.className = 'health ' + (ok ? 'ok' : 'bad');
    if(ok) health.textContent = `Local AI ready • ${h.ollama.model}`;
    else if(!h.ollama.ok) health.textContent = 'Ollama not running';
    else if(!h.ollama.model_installed) health.textContent = `Install model: ollama pull ${h.ollama.model}`;
    else health.textContent = 'FFmpeg unavailable';
  }catch(e){health.className='health bad';health.textContent='Health check failed';}
}

async function loadProfile(){
  profile = await jsonFetch('/api/profile');
  const f = document.querySelector('#profile-form');
  for(const [key,value] of Object.entries(profile)){
    if(f.elements[key]) f.elements[key].value = value;
  }
  const vf = document.querySelector('#video-form');
  vf.elements.voice.value = profile.voice;
  vf.elements.target_seconds.value = profile.target_seconds;
  document.querySelector('#profile-summary').innerHTML =
    `<b>${esc(profile.channel_name)}</b><span>${esc(profile.niche)}</span><span>${esc(profile.tone)} • ~${profile.target_seconds}s</span>`;
}

document.querySelector('#profile-form').addEventListener('submit', async e=>{
  e.preventDefault();
  const data = Object.fromEntries(new FormData(e.currentTarget).entries());
  for(const k of ['target_seconds','trend_weight','evergreen_weight','experiment_weight']) data[k]=Number(data[k]);
  try{ profile = await jsonFetch('/api/profile',{method:'PUT',body:JSON.stringify(data)}); await loadProfile(); }
  catch(err){ alert(err.message); }
});

document.querySelector('#auto-generate').onclick=async e=>{
  const btn=e.currentTarget; btn.disabled=true; btn.textContent='QUEUING FULL AUTO…';
  try{
    await jsonFetch('/api/auto-generate',{method:'POST',body:'{}'});
    showTab('review');
  }catch(err){alert(err.message)}
  finally{btn.disabled=false;btn.textContent='GENERATE FULL SHORT'}
};

document.querySelector('#video-form').addEventListener('submit', async e=>{
  e.preventDefault();
  if(!profile) await loadProfile();
  const fd = new FormData(e.currentTarget);
  const payload = {
    channel_name: profile.channel_name,
    niche: profile.niche,
    topic: fd.get('topic'),
    voice: fd.get('voice'),
    target_seconds: Number(fd.get('target_seconds')),
  };
  const btn=e.currentTarget.querySelector('button[type="submit"]');
  btn.disabled=true; btn.textContent='QUEUING…';
  try{ await jsonFetch('/api/jobs',{method:'POST',body:JSON.stringify(payload)}); showTab('review'); }
  catch(err){ alert(err.message); }
  finally{btn.disabled=false;btn.textContent='CREATE FULL VIDEO';}
});

function topicCard(t){
  const el=document.createElement('article');
  el.className='topic-card';
  const evidence=t.evidence||{};
  const videos=evidence.youtube_samples||[];
  const best=videos.reduce((m,v)=>Math.max(m,Number(v.views||0)),0);
  el.innerHTML =
    `<div class="score-ring">${Math.round(t.score)}</div>
     <div class="topic-copy">
       <div class="topic-subject">${esc(t.subject)}</div>
       <h3>${esc(t.title)}</h3>
       <p>${esc(t.reason)}</p>
       <div class="score-row">
         <span>YouTube ${Math.round(t.youtube_score)}</span>
         <span>Recency ${Math.round(t.recency_score)}</span>
         <span>Curiosity ${Math.round(t.curiosity_score)}</span>
         <span>Duplicate risk ${Math.round(t.duplicate_risk)}%</span>
       </div>
       <div class="sample">Best observed sample: ${best ? best.toLocaleString()+' views' : 'view count unavailable'}</div>
     </div>
     <button class="action make-short">MAKE SHORT</button>`;
  el.querySelector('.make-short').onclick=async()=>{
    const b=el.querySelector('.make-short'); b.disabled=true;b.textContent='QUEUING…';
    try{await jsonFetch(`/api/topics/${t.id}/make-short`,{method:'POST',body:'{}'});showTab('review')}
    catch(err){alert(err.message);b.disabled=false;b.textContent='MAKE SHORT'}
  };
  return el;
}

async function loadRadar(){
  const box=document.querySelector('#topic-grid');
  const status=document.querySelector('#radar-status');
  try{
    const state=await jsonFetch('/api/radar');
    const run=state.run;
    if(run){
      status.textContent = run.status==='running' ? 'Scanning recent Roblox signals… this can take a few minutes.' :
        run.status==='failed' ? `Radar failed: ${run.error||'unknown error'}` :
        `Last scan finished • ${new Date(run.updated_at).toLocaleString()}`;
      status.className='notice '+(run.status==='failed'?'error':'');
    }
    box.innerHTML='';
    if(!state.topics.length) box.innerHTML='<div class="empty">No radar results yet. Press SCAN ROBLOX NOW.</div>';
    state.topics.forEach(t=>box.appendChild(topicCard(t)));
    if(run && run.status==='running' && !radarPoll){
      radarPoll=setInterval(async()=>{
        const s=await jsonFetch('/api/radar');
        if(!s.run || s.run.status!=='running'){clearInterval(radarPoll);radarPoll=null;loadRadar();}
      },4000);
    }
  }catch(err){status.textContent=err.message;status.className='notice error';}
}

document.querySelector('#scan-radar').onclick=async e=>{
  const btn=e.currentTarget;btn.disabled=true;btn.textContent='SCANNING…';
  try{await jsonFetch('/api/radar/scan',{method:'POST',body:'{}'});await loadRadar();}
  catch(err){alert(err.message)}
  finally{btn.disabled=false;btn.textContent='SCAN ROBLOX NOW'}
};

document.querySelector('#image-form').addEventListener('submit', async e=>{
  e.preventDefault();
  const data=Object.fromEntries(new FormData(e.currentTarget).entries());
  const btn=e.currentTarget.querySelector('button[type="submit"]');btn.disabled=true;btn.textContent='CREATING…';
  try{await jsonFetch('/api/images',{method:'POST',body:JSON.stringify(data)});await loadImages();}
  catch(err){alert(err.message)}
  finally{btn.disabled=false;btn.textContent='CREATE QUICK GRAPHIC'}
});

async function loadImages(){
  const grid=document.querySelector('#image-grid');
  try{
    const items=await jsonFetch('/api/images');
    grid.innerHTML='';
    if(!items.length){grid.innerHTML='<div class="empty">No standalone images yet.</div>';return;}
    items.forEach(item=>{
      const el=document.createElement('article');el.className='image-card';
      el.innerHTML=`<img loading="lazy" src="/api/images/${item.id}/file"><div><b>${esc(item.headline||item.prompt)}</b><span>${esc(item.aspect)}</span></div><a class="action" href="/api/images/${item.id}/file">Open image</a>`;
      grid.appendChild(el);
    });
  }catch(err){grid.innerHTML=`<div class="empty error">${esc(err.message)}</div>`;}
}
document.querySelector('#refresh-images').onclick=loadImages;

function createJobCard(job){
  const node=template.content.firstElementChild.cloneNode(true);
  node.dataset.jobId=job.id;
  queue.appendChild(node);
  return node;
}

function updateJobCard(node, job){
  const manifest=job.manifest||{};
  const topic=job.selected_topic||job.requested_topic||job.niche;
  node.querySelector('.job-topic').textContent=topic;
  node.querySelector('.job-meta').textContent=`${job.channel_name} • ${new Date(job.created_at).toLocaleString()}`;
  const status=node.querySelector('.status');
  status.className='status '+(job.approved?'approved':job.status);
  status.textContent=job.approved?'approved':job.status.replaceAll('_',' ');
  node.querySelector('.progress div').style.width=`${job.progress||0}%`;
  const stage=node.querySelector('.stage');
  stage.textContent=job.error?job.error:`${job.stage} • ${job.progress||0}%`;
  stage.classList.toggle('error',Boolean(job.error));

  // Create the player only once. Polling updates the surrounding card, not the video element.
  const videoWrap=node.querySelector('.video-wrap');
  if(job.output_path && !videoWrap.querySelector('video')){
    const video=document.createElement('video');
    video.controls=true;
    video.preload='metadata';
    video.src=`/api/jobs/${job.id}/video`;
    videoWrap.appendChild(video);
  }

  const details=node.querySelector('.job-details');
  if(manifest.metadata){
    const q=manifest.quality||{};
    details.innerHTML=`<b>${esc(manifest.metadata.title)}</b><br>${esc(manifest.metadata.description)}<br>`+
      `${(manifest.metadata.hashtags||[]).map(esc).join(' ')}<br>`+
      `<span class="rights">${q.source_count||0} research sources • ${q.external_visual_count||0} licensed visual(s) • ${q.duration_seconds||'?'} sec</span>`;
  }

  const actions=node.querySelector('.actions');
  actions.innerHTML='';
  if(job.output_path && !job.approved){
    const approve=document.createElement('button');
    approve.className='action approve';approve.textContent='Approve';
    approve.onclick=async()=>{await jsonFetch(`/api/jobs/${job.id}/approve`,{method:'POST'});loadJobs();};
    actions.appendChild(approve);
  }
  if(['ready','review_needed','failed'].includes(job.status)){
    const regen=document.createElement('button');
    regen.className='action';regen.textContent='Regenerate';
    regen.onclick=async()=>{await jsonFetch(`/api/jobs/${job.id}/regenerate`,{method:'POST',body:'{}'});loadJobs();};
    actions.appendChild(regen);
  }
  if(job.output_path){
    const dl=document.createElement('a');dl.className='action';dl.href=`/api/jobs/${job.id}/video`;dl.textContent='Open MP4';actions.appendChild(dl);
    const mf=document.createElement('a');mf.className='action';mf.href=`/api/jobs/${job.id}/manifest`;mf.target='_blank';mf.textContent='Manifest';actions.appendChild(mf);
  }

  const del=document.createElement('button');
  del.className='action danger';
  del.textContent='Delete';
  del.onclick=async()=>{
    if(!confirm(`Delete this Short and its local rendered files?\n\n${topic}`)) return;
    del.disabled=true;del.textContent='Deleting…';
    try{
      await jsonFetch(`/api/jobs/${job.id}`,{method:'DELETE'});
      node.remove();
      if(!queue.querySelector('.job-card')) queue.innerHTML='<div class="empty">No Shorts yet.</div>';
    }catch(err){
      alert(err.message);del.disabled=false;del.textContent='Delete';
    }
  };
  actions.appendChild(del);
}

async function loadJobs(){
  try{
    const jobs=(await jsonFetch('/api/jobs')).filter(j=>j.status!=='deleted');
    queue.querySelectorAll('.empty').forEach(n=>n.remove());
    const existing=new Map([...queue.querySelectorAll('.job-card')].map(n=>[n.dataset.jobId,n]));
    const liveIds=new Set(jobs.map(j=>j.id));

    for(const job of jobs){
      let node=existing.get(job.id);
      if(!node) node=createJobCard(job);
      updateJobCard(node,job);
    }
    for(const [id,node] of existing) if(!liveIds.has(id)) node.remove();
    if(!jobs.length && !queue.querySelector('.empty')) queue.innerHTML='<div class="empty">No Shorts yet. Generate the first one.</div>';
  }catch(err){
    if(!queue.querySelector('.job-card')) queue.innerHTML=`<div class="empty error">${esc(err.message)}</div>`;
  }
}
document.querySelector('#refresh').onclick=loadJobs;

Promise.all([loadHealth(),loadProfile(),loadJobs()]).catch(console.error);
setInterval(loadJobs, 3500);
setInterval(loadHealth, 30000);
