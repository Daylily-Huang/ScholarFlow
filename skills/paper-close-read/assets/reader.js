(() => {
  'use strict';
  const config = JSON.parse(document.getElementById('reader-config').textContent);
  const key = 'close-read:v2:' + config.paperId + ':reading';
  const status = document.getElementById('storage-status');
  let timer;
  function toast(message) { status.textContent = message; clearTimeout(timer); timer = setTimeout(() => status.textContent = '', 6000); }
  let state = {route:'full', read:[], recall:{}, last:'', layoutVersion:2};
  try { const old = JSON.parse(localStorage.getItem(key) || 'null'); if(old && Array.isArray(old.read) && old.recall && typeof old.recall === 'object') state = {...state,...old,layoutVersion:old.layoutVersion||0}; }
  catch (_) { toast('浏览器存储不可用或记录损坏；本次仍可阅读，请导出笔记保存。'); }
  if(state.layoutVersion!==2){state.route='full';state.layoutVersion=2;}
  const fontSelect=document.getElementById('font-size');
  if(fontSelect){const fontKey='paper-reader:font-size:v3';const applyFont=n=>{if(!['16','18','20'].includes(n))n='18';document.documentElement.style.fontSize=n+'px';fontSelect.value=n;};try{applyFont(localStorage.getItem(fontKey)||'18');}catch(_){applyFont('18');}fontSelect.addEventListener('change',()=>{applyFont(fontSelect.value);try{localStorage.setItem(fontKey,fontSelect.value);}catch(_){}});}
  function save() { try { localStorage.setItem(key, JSON.stringify(state)); } catch (_) { toast('无法持久保存；请导出阅读笔记与批注备份。'); } }
  function download(name, text, type) { const url = URL.createObjectURL(new Blob([text],{type})); const a = document.createElement('a'); a.href=url; a.download=name; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000); }
  const animations = [];
  const fullNav=document.querySelector('.layout>aside nav');
  const guideNav=document.createElement('nav');guideNav.id='guide-toc';guideNav.setAttribute('aria-label','导读目录');
  document.querySelectorAll('#mode-guide section[id^="story-"]').forEach((s,i)=>{const a=document.createElement('a');a.href='#'+s.id;a.textContent=(i===0?'00 · 一页入门':String(i).padStart(2,'0')+' · '+s.querySelector('h2').textContent);if(i>0)a.dataset.deepLink='true';guideNav.append(a);});
  if(fullNav && guideNav.children.length)fullNav.after(guideNav);

  function route(name, persist=true) {
    if(!['quick','deep','full'].includes(name)) name='quick';
    document.body.classList.toggle('quick',name==='quick');
    if(guideNav.children.length){fullNav.hidden=name!=='full';guideNav.hidden=name==='full';guideNav.querySelectorAll('[data-deep-link]').forEach(a=>a.hidden=name==='quick');}

    document.getElementById('mode-guide').hidden=name==='full';
    document.getElementById('mode-full').hidden=name!=='full';
    document.querySelectorAll('[data-route]').forEach(b=>b.setAttribute('aria-pressed',String(b.dataset.route===name)));
    animations.forEach(a=>a.pause());
    state.route=name; if(persist) save();
  }
  function reveal(id) {
    const el=document.getElementById(id); if(!el) return false;
    if(el.closest('#mode-full')) route('full');
    else if(el.closest('#mode-guide')) route('deep');
    let parent=el.parentElement; while(parent) { if(parent.tagName==='DETAILS') parent.open=true; parent=parent.parentElement; }
    if(el.classList.contains('pcard')) el.querySelector('.bilingual').open=true;
    el.hidden=false;
    document.querySelectorAll('.fsect').forEach(s=>s.hidden=false);
    el.scrollIntoView({block:'start',behavior:'auto'});
    state.last=id;save();return true;
  }
  function hash() { let id; try{id=decodeURIComponent(location.hash.slice(1));}catch(_){return;} if(id)reveal(id); }
  function progress() {
    const cards=[...document.querySelectorAll('[data-read]')];
    let count=0; cards.forEach(b=>{const read=state.read.includes(b.dataset.read);if(read)count++;b.textContent=read?'已读 · 点击撤销':'标为已读';b.setAttribute('aria-pressed',String(read));});
    document.getElementById('progress').textContent=`已读 ${count}/${cards.length} 段`;
  }
  document.querySelectorAll('[data-route]').forEach(b=>b.addEventListener('click',()=>{
    route(b.dataset.route);
    if(b.dataset.route==='quick'){
      const overview=document.getElementById('story-overview');
      if(overview){const offset=(document.querySelector('.toolbar')?.getBoundingClientRect().height||0)+16;window.scrollTo({top:Math.max(0,scrollY+overview.getBoundingClientRect().top-offset),behavior:'instant'});}
    }
  }));
  document.querySelectorAll('[data-read]').forEach(b=>b.addEventListener('click',()=>{const id=b.dataset.read;state.read=state.read.includes(id)?state.read.filter(x=>x!==id):[...state.read,id];state.last=id;save();progress();}));
  document.querySelectorAll('[data-recall]').forEach(t=>{t.value=state.recall[t.dataset.recall]||'';t.addEventListener('input',()=>{state.recall[t.dataset.recall]=t.value;save();});});
  document.getElementById('resume').addEventListener('click',()=>{if(!state.last||!reveal(state.last))toast('还没有阅读位置；点开证据或标记已读后会记录。');});
  document.getElementById('search').addEventListener('input',e=>{
    const q=e.target.value.trim().toLocaleLowerCase(); if(q)route('full'); let n=0;
    document.querySelectorAll('.pcard,.source-block').forEach(c=>{const hit=!q||c.textContent.toLocaleLowerCase().includes(q);c.hidden=!hit;if(hit)n++;});
    document.querySelectorAll('.fsect').forEach(s=>s.hidden=![...s.querySelectorAll('article')].some(a=>!a.hidden));
    document.getElementById('search-count').textContent=q?`${n} 个匹配内容块`:'';
  });
  document.getElementById('export-reading').addEventListener('click',()=>{
    const lines=['# '+config.title+' · 阅读笔记','','论文标识：'+config.paperId,'内容版本：'+config.revision,'已读段落：'+state.read.join(', '),''];
    document.querySelectorAll('.check').forEach((c,i)=>{lines.push('## '+c.querySelector('h3').textContent,state.recall[String(i)]||'尚未填写','');});
    if(window.__ann)for(const a of window.__ann.items)lines.push('> '+a.text,a.note||'（高亮）','定位：'+a.cid,'');
    download('阅读笔记.md',lines.join('\n'),'text/markdown;charset=utf-8');
  });
  document.querySelectorAll('.anim').forEach(el=>{
    const data=JSON.parse(el.dataset.animation), img=el.querySelector('img'), scrub=el.querySelector('input'), play=el.querySelector('[data-action=play]'), speed=el.querySelector('select');
    let index=0, running=false, timeout;
    function draw(){img.src=data.frames[index];scrub.value=String(index);el.querySelector('.frame-count').textContent=`${index+1}/${data.frames.length}`;}
    function pause(){running=false;clearTimeout(timeout);play.textContent='播放';}
    function tick(){timeout=setTimeout(()=>{if(!running)return;index++;if(index>=data.frames.length){index=data.frames.length-1;pause();return;}draw();tick();},data.durations[index]/Number(speed.value));}
    el.querySelectorAll('[data-action]').forEach(b=>b.addEventListener('click',()=>{const act=b.dataset.action;if(act==='play'){if(running)pause();else{if(index===data.frames.length-1)index=0;running=true;play.textContent='暂停';draw();tick();}}else{pause();index=act==='first'?0:Math.max(0,Math.min(data.frames.length-1,index+(act==='next'?1:-1)));draw();}}));
    scrub.addEventListener('input',()=>{pause();index=Number(scrub.value);draw();});speed.addEventListener('change',()=>{if(running){clearTimeout(timeout);tick();}});
    animations.push({pause});draw();
  });
  document.addEventListener('visibilitychange',()=>{if(document.hidden)animations.forEach(a=>a.pause());});
  document.addEventListener('click',e=>{const a=e.target.closest('a[href^="#"]');if(a){const id=a.getAttribute('href').slice(1);if(document.getElementById(id)){e.preventDefault();history.replaceState(null,'','#'+id);reveal(id);}}});
  window.addEventListener('hashchange',hash);
  window.reader={config,toast,download,reveal,route};route(state.route,false);progress();hash();
})();
