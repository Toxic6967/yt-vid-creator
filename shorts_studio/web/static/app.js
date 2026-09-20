const queue = document.querySelector('#queue');
const health = document.querySelector('#health');
const template = document.querySelector('#job-template');
let profile = null;
let radarPoll = null;
let mediaRenderSignature = '';

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
  if(name==='image'){ loadImages(); loadMediaHealth(); loadMediaJobs(); }
  if(name==='video'){ loadMediaHealth(); loadMediaJobs(); }
  if(name==='review') loadJobs();
}
document.querySelectorAll('.tab').forEach(btn=>btn.onclick=()=>showTab(btn.dataset.tab));
document.querySelectorAll('[data-video-mode]').forEach(btn=>{
  btn.onclick=()=>{
    const mode=btn.dataset.videoMode;
    document.querySelectorAll('[data-video-mode]').forEach(x=>x.classList.toggle('active',x===btn));
    document.querySelectorAll('#tab-video .mode-pane').forEach(x=>x.classList.toggle('active',x.id===`video-mode-${mode}`));
  };
});
document.querySelectorAll('[data-refresh-media]').forEach(btn=>btn.onclick=()=>loadMediaJobs(true));

async function loadHealth(){
  try{
    const h = await jsonFetch('/api/health');
    const voiceReady = Boolean(h.voice && h.voice.ready);
    const ok = h.ollama.ok && h.ollama.model_installed && h.ffmpeg.ok && voiceReady;
    health.className = 'health ' + (ok ? 'ok' : 'bad');
    if(ok) health.textContent = `Story AI ready • ${h.ollama.model} • human voice`;
    else if(!h.ollama.ok) health.textContent = 'Ollama not running';
    else if(!h.ollama.model_installed) health.textContent = `Install model: ollama pull ${h.ollama.model}`;
    else if(!voiceReady) health.textContent = 'Human voice not installed • run install_human_voice.bat';
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
    `<b>${esc(profile.channel_name)}</b><span>${esc(profile.niche)}</span><span>${esc(profile.audience)}</span><span>${esc(profile.tone)} • ~${profile.target_seconds}s</span>`;
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
  finally{btn.disabled=false;btn.textContent='GENERATE ROBLOX STORY'}
};

document.querySelector('#video-form').addEventListener('submit', async e=>{
  e.preventDefault();
  if(!profile) await loadProfile();
  const fd = new FormData(e.currentTarget);
  const payload = {
    channel_name: profile.channel_name,
    niche: profile.niche,
    topic: fd.get('topic'),
    content_type: fd.get('content_type') || 'story',
    story_genre: fd.get('story_genre') || 'auto',
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
       <div class="topic-subject">${esc((evidence.content_type || 'trend').toUpperCase())} • ${esc(t.subject)}</div>
       <h3>${esc(t.title)}</h3>
       <p>${esc(t.reason)}</p>
       <div class="score-row">
         <span>YouTube ${Math.round(t.youtube_score)}</span>
         <span>Recency ${Math.round(t.recency_score)}</span>
         <span>Curiosity ${Math.round(t.curiosity_score)}</span>
         ${evidence.relatability_score ? `<span>Relatable ${Math.round(evidence.relatability_score)}</span>` : ''}
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
  const grid=document.querySelector('#graphic-grid');
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


async function loadMediaHealth(){
  try{
    const state=await jsonFetch('/api/media/health');
    const imageStatus=document.querySelector('#image-engine-status');
    const videoStatus=document.querySelector('#video-engine-status');
    const imageButton=document.querySelector('#ai-image-button');
    const videoButton=document.querySelector('#ai-video-button');

    if(state.ok){
      if(state.story_image_ready){
        imageStatus.textContent='ComfyUI connected • Story keyframes: FLUX.2 Klein 4B FP8 ready';
      }else if(state.image_ready){
        imageStatus.textContent=`ComfyUI connected • general image engine ready • Story FLUX upgrade missing`;
      }else{
        imageStatus.textContent='ComfyUI connected, but no image checkpoint is installed yet.';
      }
      imageStatus.className='notice '+(state.story_image_ready?'ok':'');
      if(state.story_video_ready && state.story_image_ready){
        videoStatus.textContent='Story movie stack ready • FLUX.2 Klein keyframes → LTX 2B motion';
      }else if(state.story_video_ready){
        videoStatus.textContent='LTX motion ready • FLUX.2 Story keyframes not installed yet';
      }else if(state.video_ready){
        videoStatus.textContent='ComfyUI connected • Wan motion fallback ready • cinematic I2V upgrade not installed yet';
      }else if((state.missing_video_models||[]).length){
        videoStatus.textContent='ComfyUI connected • video models not detected: '+state.missing_video_models.join(', ');
      }else{
        videoStatus.textContent='ComfyUI connected, but the local video workflow is not ready yet.';
      }
      videoStatus.className='notice '+((state.story_video_ready||state.video_ready)?'ok':'');
      imageButton.disabled=!state.image_ready;
      videoButton.disabled=!(state.story_video_ready||state.video_ready);
    }else{
      imageStatus.textContent='ComfyUI is not running yet. AI image generation is unavailable until we install/start it.';
      videoStatus.textContent='ComfyUI is not running yet. AI video generation is unavailable until we install/start it.';
      imageStatus.className='notice error';
      videoStatus.className='notice error';
      imageButton.disabled=true;
      videoButton.disabled=true;
    }
  }catch(err){
    for(const id of ['#image-engine-status','#video-engine-status']){
      const node=document.querySelector(id);
      if(node){node.textContent=err.message;node.className='notice error';}
    }
  }
}

document.querySelector('#ai-image-form').addEventListener('submit', async e=>{
  e.preventDefault();
  const fd=new FormData(e.currentTarget);
  const data=Object.fromEntries(fd.entries());
  data.steps=Number(data.steps);
  data.cfg=Number(data.cfg);
  data.variations=Number(data.variations);
  data.seed=data.seed ? Number(data.seed) : null;
  data.enhance_prompt=fd.has('enhance_prompt');
  const btn=document.querySelector('#ai-image-button');
  btn.disabled=true;btn.textContent='QUEUING AI IMAGE…';
  try{
    await jsonFetch('/api/media/image',{method:'POST',body:JSON.stringify(data)});
    mediaRenderSignature='';
    await loadMediaJobs(true);
  }catch(err){alert(err.message)}
  finally{btn.textContent='GENERATE AI IMAGE';await loadMediaHealth();}
});

document.querySelector('#ai-video-form').addEventListener('submit', async e=>{
  e.preventDefault();
  const fd=new FormData(e.currentTarget);
  const data=Object.fromEntries(fd.entries());
  data.seconds=Number(data.seconds);
  data.motion_strength=Number(data.motion_strength);
  data.variations=Number(data.variations);
  data.seed=data.seed ? Number(data.seed) : null;
  data.enhance_prompt=fd.has('enhance_prompt');
  const btn=document.querySelector('#ai-video-button');
  btn.disabled=true;btn.textContent='QUEUING AI VIDEO…';
  try{
    await jsonFetch('/api/media/video',{method:'POST',body:JSON.stringify(data)});
    mediaRenderSignature='';
    await loadMediaJobs(true);
  }catch(err){alert(err.message)}
  finally{btn.textContent='GENERATE AI VIDEO';await loadMediaHealth();}
});

function mediaJobCard(job){
  const el=document.createElement('article');
  el.className='generation-card '+job.kind;
  let preview='';
  if(job.output_path && job.kind==='image'){
    preview=`<img src="/api/media/jobs/${job.id}/file" loading="lazy">`;
  }else if(job.output_path && job.kind==='video'){
    preview=`<video controls preload="metadata" src="/api/media/jobs/${job.id}/file"></video>`;
  }
  el.innerHTML=`
    ${preview}
    <div class="media-job-copy generation-copy">
      <b>${esc(job.prompt)}</b>
      <span>${esc(job.kind)} • ${esc(job.status)} • ${job.progress||0}%</span>
      ${job.error?`<span class="error">${esc(job.error)}</span>`:''}
    </div>
    <div class="actions"></div>`;
  const actions=el.querySelector('.actions');
  if(job.output_path){
    const open=document.createElement('a');
    open.className='action';open.href=`/api/media/jobs/${job.id}/file`;open.textContent='Open';
    actions.appendChild(open);
  }
  const del=document.createElement('button');
  del.className='action danger';del.textContent='Delete';
  del.onclick=async()=>{
    if(!confirm('Delete this generated media file?')) return;
    await jsonFetch(`/api/media/jobs/${job.id}`,{method:'DELETE'});
    mediaRenderSignature='';
    await loadMediaJobs(true);
  };
  actions.appendChild(del);
  return el;
}

async function loadMediaJobs(force=false){
  try{
    const jobs=await jsonFetch('/api/media/jobs');
    const signature=JSON.stringify(jobs.map(j=>[j.id,j.status,j.progress,j.output_path,j.error]));
    if(!force && signature===mediaRenderSignature) return;
    mediaRenderSignature=signature;

    const imageBox=document.querySelector('#ai-image-gallery');
    const videoBox=document.querySelector('#ai-video-gallery');
    if(imageBox) imageBox.innerHTML='';
    if(videoBox) videoBox.innerHTML='';

    for(const job of jobs){
      const box=job.kind==='image'?imageBox:videoBox;
      if(box) box.appendChild(mediaJobCard(job));
    }

    if(imageBox && !imageBox.children.length){
      imageBox.innerHTML='<div class="studio-empty"><b>Your images will appear here</b><span>Describe a scene on the left and generate it locally.</span></div>';
    }
    if(videoBox && !videoBox.children.length){
      videoBox.innerHTML='<div class="studio-empty"><b>Your video clips will appear here</b><span>Create hooks, B-roll, reveals and reusable shots.</span></div>';
    }
  }catch(err){ console.error(err); }
}


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
    const script=manifest.script||{};
    const chars=(script.characters||[]).map(c=>c.name).filter(Boolean).join(' • ');
    const storyBits=[];
    if(script.genre) storyBits.push(esc(script.genre));
    if(chars) storyBits.push(esc(chars));
    if(q.hook_score!=null) storyBits.push(`hook ${q.hook_score}`);
    if(q.relatability_score!=null) storyBits.push(`relatable ${q.relatability_score}`);
    if(q.payoff_score!=null) storyBits.push(`payoff ${q.payoff_score}`);
    if(q.game_specificity_score!=null) storyBits.push(`game-specific ${q.game_specificity_score}`);
    details.innerHTML=`<b>${esc(manifest.metadata.title)}</b><br>${esc(manifest.metadata.description)}<br>`+
      `${(manifest.metadata.hashtags||[]).map(esc).join(' ')}<br>`+
      (storyBits.length ? `<span class="rights">${storyBits.join(' • ')}</span><br>` : '')+
      `<span class="rights">${esc(manifest.content_type||job.content_type||'auto')} • story/retention ${q.retention_score??'?'} • cinematic motion ${q.cinematic_i2v_count||0} • cinematic stills ${q.ai_visual_count||0} • ${q.duration_seconds||'?'} sec</span>`;
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
    regen.className='action';
    if((job.content_type||'auto')==='story'){
      regen.textContent='Regenerate Story';
      regen.onclick=async()=>{await jsonFetch(`/api/jobs/${job.id}/regenerate`,{method:'POST',body:'{}'});loadJobs();};
    }else{
      regen.textContent='Remake as Story';
      regen.onclick=async()=>{await jsonFetch(`/api/jobs/${job.id}/remake-story`,{method:'POST',body:'{}'});loadJobs();};
    }
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

Promise.all([loadHealth(),loadProfile(),loadJobs(),loadMediaHealth(),loadMediaJobs()]).catch(console.error);
setInterval(loadJobs, 3500);
setInterval(loadMediaJobs, 5000);
setInterval(loadHealth, 30000);
setInterval(loadMediaHealth, 30000);
