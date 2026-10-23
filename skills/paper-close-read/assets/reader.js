(() => {
  'use strict';
  const config = JSON.parse(document.getElementById('reader-config').textContent);
  const key = 'close-read:v2:' + config.paperId + ':reading';
  const status = document.getElementById('storage-status');
  let timer;
  function toast(message) { status.textContent = message; clearTimeout(timer); timer = setTimeout(() => status.textContent = '', 6000); }
  const persistence=window.ReaderPersistence;
  const allowed=[...document.querySelectorAll('[id]')].map(x=>x.id);
  const initial={route:'full',read:[],recall:{},last:'',positions:{},documentNote:'',layoutVersion:2};
  const store=persistence.localStore(key,initial,v=>persistence.normalizeReading(v,allowed),persistence.mergeReading);
  let state=store.value;
  if(store.warning)toast('阅读记录暂未恢复；仍可阅读，原有损坏数据会保留备份。');
  if(state.layoutVersion!==2){state.route='full';state.layoutVersion=2;}
  const fontSelect=document.getElementById('font-size');
  if(fontSelect){const fontKey='paper-reader:font-size:v3';const applyFont=n=>{if(!['16','18','20'].includes(n))n='18';document.documentElement.style.fontSize=n+'px';fontSelect.value=n;};try{applyFont(localStorage.getItem(fontKey)||'18');}catch(_){applyFont('18');}fontSelect.addEventListener('change',()=>{applyFont(fontSelect.value);try{localStorage.setItem(fontKey,fontSelect.value);}catch(_){}});}
  function save() { const ok=store.save(state);state=store.value;if(!ok)toast('无法持久保存；请导出完整备份。');else if(store.conflicts)toast('两个窗口的笔记均已保留，请在阅读工具中整理。');return ok; }
  function download(name, text, type) { const url = URL.createObjectURL(new Blob([text],{type})); const a = document.createElement('a'); a.href=url; a.download=name; a.click(); setTimeout(()=>URL.revokeObjectURL(url),1000); }
  const animations = [];
  const fullNav=document.querySelector('.layout>aside nav');
  const guideNav=document.createElement('nav');guideNav.id='guide-toc';guideNav.setAttribute('aria-label','导读目录');
  document.querySelectorAll('#mode-guide section[id^="story-"]').forEach((s,i)=>{const a=document.createElement('a');a.href='#'+s.id;a.textContent=(i===0?'00 · 一页入门':String(i).padStart(2,'0')+' · '+s.querySelector('h2').textContent);if(i>0)a.dataset.deepLink='true';guideNav.append(a);});
  if(fullNav && guideNav.children.length)fullNav.after(guideNav);

  function route(name, persist=true) {
    if(!['quick','deep','full'].includes(name)) name='quick';
    if(persist&&name!==state.route)capturePosition();
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
    if(window.reader?.search?.active)window.reader.search.clear(false);
    if(el.closest('#mode-full')) route('full');
    else if(el.closest('#mode-guide')) route(el.closest('.guide-deep')?'deep':state.route==='deep'?'deep':'quick');
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
  let positionTimer;
  function capturePosition(){
    if(scrollY<200)return;
    const root=document.getElementById(state.route==='full'?'mode-full':'mode-guide');
    const selector=state.route==='full'?'.pcard,.source-block':state.route==='quick'?'#story-overview':'.story-overview,.story-chapter';
    const edge=(document.querySelector('.toolbar')?.getBoundingClientRect().height||0)+20;
    const blocks=[...root.querySelectorAll(selector)].filter(x=>x.getBoundingClientRect().height>0);
    const current=blocks.find(x=>{const r=x.getBoundingClientRect();return r.top<=edge&&r.bottom>edge;})||blocks.find(x=>x.getBoundingClientRect().top>=edge);
    if(current){const rect=current.getBoundingClientRect();state.positions[state.route]={id:current.id,ratio:Math.max(0,Math.min(1,(edge-rect.top)/Math.max(1,rect.height)))};state.last=current.id;save();}
  }
  function resume(){const fallback=state.route==='quick'?document.getElementById('story-overview'):state.route==='deep'?document.querySelector('.story-chapter'):null;const pos=state.positions[state.route]||(fallback?{id:fallback.id,ratio:0}:state.last?{id:state.last,ratio:0}:null);
    if(!pos||!reveal(pos.id)){toast('开始阅读后，位置会自动记录；也可以点击目录选择章节。');return;}
    const el=document.getElementById(pos.id),edge=(document.querySelector('.toolbar')?.getBoundingClientRect().height||0)+20;
    window.scrollTo({top:Math.max(0,scrollY+el.getBoundingClientRect().top+el.getBoundingClientRect().height*pos.ratio-edge),behavior:'instant'});
  }
  document.getElementById('resume').addEventListener('click',resume);
  addEventListener('scroll',()=>{clearTimeout(positionTimer);positionTimer=setTimeout(capturePosition,500);},{passive:true});
  addEventListener('pagehide',capturePosition);document.addEventListener('visibilitychange',()=>{if(document.hidden)capturePosition();});
  document.getElementById('export-reading').addEventListener('click',()=>{
    if(window.reader.exportMarkdown){window.reader.exportMarkdown();return;}
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
  let printClosed=[];
  addEventListener('beforeprint',()=>{animations.forEach(a=>a.pause());window.mechanismPlayers?.forEach(a=>a.pause());printClosed=[...document.querySelectorAll('details:not([open])')];printClosed.forEach(d=>d.open=true);});
  addEventListener('afterprint',()=>{printClosed.forEach(d=>d.open=false);printClosed=[];});
  document.addEventListener('click',e=>{const a=e.target.closest('a[href^="#"]');if(a){const id=a.getAttribute('href').slice(1);if(document.getElementById(id)){e.preventDefault();history.replaceState(null,'','#'+id);reveal(id);}}});
  window.addEventListener('hashchange',hash);
  function openDialog(dialog,trigger){
    const opener=trigger||document.activeElement;
    if(opener&&typeof opener.focus==='function')opener.focus({preventScroll:true});
    dialog.addEventListener('close',()=>{const active=document.activeElement;if((active===document.body||dialog.contains(active))&&opener?.isConnected&&!opener.closest('[hidden]'))opener.focus({preventScroll:true});},{once:true});
    dialog.showModal();
  }
  function previewImportState(incoming){
    const next=persistence.normalizeReading(incoming,allowed);
    const merged=persistence.mergeReading(initial,state,next).value;
    merged.read=[...new Set([...state.read,...next.read])];
    return persistence.normalizeReading(merged,allowed);
  }
  function importState(incoming){
    state=previewImportState(incoming);
    save();route(state.route,false);progress();
    document.querySelectorAll('[data-recall]').forEach(t=>t.value=state.recall[t.dataset.recall]||'');
  }
  window.reader={config,toast,download,reveal,route,resume,openDialog,capturePosition,allowed,getState:()=>persistence.clone(state),previewImportState,importState,setDocumentNote:value=>{state.documentNote=value;return save();},recoveryRaw:()=>store.recoveryRaw};route(state.route,false);progress();hash();
})();
