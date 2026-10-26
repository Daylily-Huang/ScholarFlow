/* Mouse/keyboard movable and resizable original-source windows. */
(()=>{'use strict';
 const clamp=(v,min,max)=>Math.max(min,Math.min(max,v));
 function attach(dialog){
  if(dialog.dataset.floatingReady)return;
  dialog.dataset.floatingReady='true';dialog.classList.add('floating-viewer');
  const title=dialog.querySelector('h2'),bar=document.createElement('div');bar.className='viewer-titlebar';bar.title='拖动标题栏移动窗口';
  title.before(bar);bar.append(title);
  const actions=document.createElement('div');actions.className='viewer-window-actions';
  actions.innerHTML='<button type="button" data-window-max aria-label="最大化或还原窗口">□</button><button type="button" data-window-close aria-label="关闭原文窗口">×</button>';bar.append(actions);
  const resize=document.createElement('button');resize.className='viewer-resize-handle';resize.type='button';resize.setAttribute('aria-label','调整窗口大小');resize.title='拖拽缩放窗口；方向键也可调整';resize.textContent='◢';dialog.append(resize);
  let last=null;
  function place(left,top,width,height){
   width=clamp(width,Math.min(320,innerWidth-16),innerWidth-16);height=clamp(height,Math.min(240,innerHeight-16),innerHeight-16);
   dialog.style.width=width+'px';dialog.style.height=height+'px';dialog.style.left=clamp(left,8,innerWidth-width-8)+'px';dialog.style.top=clamp(top,8,innerHeight-height-8)+'px';
   dialog.dispatchEvent(new Event('viewerresize'));
  }
  place(Math.max(8,(innerWidth-900)/2),Math.max(8,(innerHeight-700)/2),Math.min(900,innerWidth-24),Math.min(700,innerHeight-24));
  function gesture(target,mode){
   let start=null;
   target.addEventListener('pointerdown',event=>{
    if(event.button!==0||(mode==='move'&&event.target.closest('button')))return;
    const r=dialog.getBoundingClientRect();start={x:event.clientX,y:event.clientY,left:r.left,top:r.top,width:r.width,height:r.height};
    target.setPointerCapture(event.pointerId);event.preventDefault();
   });
   target.addEventListener('pointermove',event=>{
    if(!start)return;const dx=event.clientX-start.x,dy=event.clientY-start.y;
    if(mode==='move')place(start.left+dx,start.top+dy,start.width,start.height);
    else place(start.left,start.top,start.width+dx,start.height+dy);
   });
   for(const name of ['pointerup','pointercancel','lostpointercapture'])target.addEventListener(name,()=>{start=null;});
  }
  gesture(bar,'move');gesture(resize,'resize');
  bar.tabIndex=0;bar.setAttribute('role','group');bar.setAttribute('aria-label','拖动或使用方向键移动原文窗口');
  bar.addEventListener('keydown',event=>{
   if(event.target!==bar||!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;
   const r=dialog.getBoundingClientRect(),step=event.shiftKey?80:20;event.preventDefault();
   place(r.left+(event.key==='ArrowRight'?step:event.key==='ArrowLeft'?-step:0),r.top+(event.key==='ArrowDown'?step:event.key==='ArrowUp'?-step:0),r.width,r.height);
  });
  resize.addEventListener('keydown',event=>{
   if(!['ArrowLeft','ArrowRight','ArrowUp','ArrowDown'].includes(event.key))return;
   const r=dialog.getBoundingClientRect(),step=event.shiftKey?80:20;event.preventDefault();
   place(r.left,r.top,r.width+(event.key==='ArrowRight'?step:event.key==='ArrowLeft'?-step:0),r.height+(event.key==='ArrowDown'?step:event.key==='ArrowUp'?-step:0));
  });
  actions.querySelector('[data-window-close]').onclick=()=>dialog.close();
  actions.querySelector('[data-window-max]').onclick=()=>{
   if(last){place(last.left,last.top,last.width,last.height);last=null;}
   else{const r=dialog.getBoundingClientRect();last={left:r.left,top:r.top,width:r.width,height:r.height};place(8,8,innerWidth-16,innerHeight-16);}
  };
  addEventListener('resize',()=>{if(dialog.open){const r=dialog.getBoundingClientRect();place(r.left,r.top,r.width,r.height);}});
  new MutationObserver(()=>{if(dialog.open){const r=dialog.getBoundingClientRect();place(r.left,r.top,r.width,r.height);}}).observe(dialog,{attributes:true,attributeFilter:['open']});
 }
 window.ReaderFloatingWindow={attach};
 const figure=document.getElementById('figure-viewer');if(figure)attach(figure);
})();
