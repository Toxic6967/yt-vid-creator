const queue = document.querySelector('#queue');
const form = document.querySelector('#generate-form');
const health = document.querySelector('#health');
const template = document.querySelector('#job-template');

const esc = (s='') => String(s).replace(/[&<>"]/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));

async function jsonFetch(url, options={}) {
  const r = await fetch(url, {headers:{'Content-Type':'application/json'}, ...options});
  if (!r.ok) throw new Error((await r.text()) || `HTTP ${r.status}`);
  return r.json();
}

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

function renderJob(job){
  const node = template.content.firstElementChild.cloneNode(true);
  const manifest = job.manifest || {};
  const topic = job.selected_topic || job.requested_topic || job.niche;
  node.querySelector('.job-topic').textContent = topic;
  node.querySelector('.job-meta').textContent = `${job.channel_name} • ${new Date(job.created_at).toLocaleString()}`;
  const status = node.querySelector('.status');
  status.textContent = job.approved ? 'approved' : job.status.replaceAll('_',' ');
  status.classList.add(job.approved ? 'approved' : job.status);
  node.querySelector('.progress div').style.width = `${job.progress || 0}%`;
  node.querySelector('.stage').textContent = job.error ? job.error : `${job.stage} • ${job.progress || 0}%`;
  if(job.error) node.querySelector('.stage').classList.add('error');

  const videoWrap = node.querySelector('.video-wrap');
  if(job.output_path){
    videoWrap.innerHTML = `<video controls preload="metadata" src="/api/jobs/${job.id}/video"></video>`;
  }

  const details = node.querySelector('.job-details');
  if(manifest.metadata){
    const q = manifest.quality || {};
    details.innerHTML = `<b>${esc(manifest.metadata.title)}</b><br>${esc(manifest.metadata.description)}<br>` +
      `${(manifest.metadata.hashtags||[]).map(esc).join(' ')}<br>` +
      `<span class="rights">${q.source_count || 0} research sources • ${q.external_visual_count || 0} licensed Commons visual(s) • ${q.duration_seconds || '?'} sec</span>`;
  }

  const actions = node.querySelector('.actions');
  if(job.output_path && !job.approved){
    const approve = document.createElement('button'); approve.className='action approve'; approve.textContent='Approve';
    approve.onclick=async()=>{await jsonFetch(`/api/jobs/${job.id}/approve`,{method:'POST'});loadJobs();}; actions.appendChild(approve);
  }
  if(['ready','review_needed','failed'].includes(job.status)){
    const regen = document.createElement('button'); regen.className='action'; regen.textContent='Regenerate';
    regen.onclick=async()=>{await jsonFetch(`/api/jobs/${job.id}/regenerate`,{method:'POST',body:'{}'});loadJobs();}; actions.appendChild(regen);
  }
  if(job.output_path){
    const dl = document.createElement('a'); dl.className='action'; dl.href=`/api/jobs/${job.id}/video`; dl.textContent='Open MP4'; actions.appendChild(dl);
    const mf = document.createElement('a'); mf.className='action'; mf.href=`/api/jobs/${job.id}/manifest`; mf.target='_blank'; mf.textContent='Manifest'; actions.appendChild(mf);
  }
  return node;
}

async function loadJobs(){
  try{
    const jobs = (await jsonFetch('/api/jobs')).filter(j=>j.status!=='deleted');
    queue.innerHTML='';
    if(!jobs.length){queue.innerHTML='<div class="empty">No Shorts yet. Generate the first one.</div>';return;}
    jobs.forEach(j=>queue.appendChild(renderJob(j)));
  }catch(e){queue.innerHTML=`<div class="empty error">${esc(e.message)}</div>`;}
}

form.addEventListener('submit', async e=>{
  e.preventDefault();
  const fd = new FormData(form);
  const payload = Object.fromEntries(fd.entries());
  payload.target_seconds = Number(payload.target_seconds);
  if(!payload.topic) payload.topic = null;
  const button = form.querySelector('button[type="submit"]');
  button.disabled=true; button.textContent='QUEUING…';
  try{await jsonFetch('/api/jobs',{method:'POST',body:JSON.stringify(payload)}); await loadJobs();}
  catch(err){alert(err.message)}
  finally{button.disabled=false;button.textContent='GENERATE SHORT';}
});

document.querySelector('#refresh').onclick=loadJobs;
loadHealth();loadJobs();
setInterval(loadJobs, 3500);
setInterval(loadHealth, 30000);
