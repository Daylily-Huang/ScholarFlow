/* Portable annotations: stable content ID + exact quote + context; never silently misattach. */
(() => {
  'use strict';
  const {config,toast,download,reveal}=window.reader;
  const key='close-read:v2:'+config.paperId+':annotations';
  let items=[], pending=null, editing=null;
  const findContainer=id=>[...document.querySelectorAll('[data-ann-id]')].find(el=>el.dataset.annId===id);
  function nodes(el){const w=document.createTreeWalker(el,NodeFilter.SHOW_TEXT,{acceptNode:n=>n.parentElement.closest('math,button,script,style')?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT});const a=[];while(w.nextNode())a.push(w.currentNode);return a;}
  const textOf=el=>nodes(el).map(n=>n.textContent).join('');
  const uid=()=>crypto.randomUUID?crypto.randomUUID():'a-'+Date.now()+'-'+Math.random().toString(36).slice(2);
  function valid(a){return a&&typeof a.id==='string'&&typeof a.cid==='string'&&typeof a.text==='string'&&a.text.length>0&&typeof a.note==='string'&&Number.isInteger(a.start)&&Number.isInteger(a.end)&&a.start>=0&&a.end>a.start&&a.end-a.start===a.text.length&&typeof a.prefix==='string'&&typeof a.suffix==='string';}
  try {const raw=JSON.parse(localStorage.getItem(key)||'[]');if(!Array.isArray(raw)||!raw.every(valid)||new Set(raw.map(a=>a.id)).size!==raw.length)throw Error('invalid');items=raw;}
  catch(_){toast('批注存储不可用或格式损坏；未覆盖旧数据，本次请导出备份。');}
  function save(){try{localStorage.setItem(key,JSON.stringify(items));return true;}catch(_){toast('无法持久保存批注；请立即导出 JSON 备份。');return false;}}
  function locate(a,c){
    const text=textOf(c);
    const hits=[];let from=0,pos;
    while((pos=text.indexOf(a.text,from))!==-1){if((!a.prefix||text.slice(Math.max(0,pos-a.prefix.length),pos)===a.prefix)&&(!a.suffix||text.slice(pos+a.text.length,pos+a.text.length+a.suffix.length)===a.suffix))hits.push(pos);from=pos+1;}
    if(hits.length===1){a.start=hits[0];a.end=hits[0]+a.text.length;return true;}
    return false;
  }
  function paint(){
    document.querySelectorAll('mark[data-ann]').forEach(m=>m.replaceWith(...m.childNodes));
    document.querySelectorAll('[data-ann-id]').forEach(c=>c.normalize());
    for(const a of items){const c=findContainer(a.cid);a.orphan=!c||!locate(a,c);if(a.orphan)continue;let offset=0;
      for(const node of nodes(c)){const start=offset;offset+=node.textContent.length;const lo=Math.max(a.start-start,0),hi=Math.min(a.end-start,node.textContent.length);if(hi<=lo)continue;
        const range=document.createRange();range.setStart(node,lo);range.setEnd(node,hi);const mark=document.createElement('mark');mark.dataset.ann=a.id;mark.className='ann-mark';mark.title=a.note;range.surroundContents(mark);
      }
    }
    btn.dataset.count=String(items.length);btn.setAttribute('aria-label','批注（'+items.length+' 条）');btn.title='查看批注（'+items.length+' 条）';renderList();
  }
  function offset(c,node,n){let count=0;for(const t of nodes(c)){if(t===node)return count+n;count+=t.textContent.length;}return -1;}
  function selection(){const s=getSelection();if(!s||s.isCollapsed||!s.rangeCount)return null;const r=s.getRangeAt(0);const parent=n=>n.nodeType===3?n.parentElement:n;const a=parent(r.startContainer).closest('[data-ann-id]'),b=parent(r.endContainer).closest('[data-ann-id]');if(!a||a!==b)return null;const start=offset(a,r.startContainer,r.startOffset),end=offset(a,r.endContainer,r.endOffset);if(start<0||end<=start)return null;const full=textOf(a),text=full.slice(start,end);if(text!==s.toString())return null;return {cid:a.dataset.annId,start,end,text,prefix:full.slice(Math.max(0,start-24),start),suffix:full.slice(end,end+24)};}
  const bar=document.createElement('div');bar.id='annbar';bar.hidden=true;bar.setAttribute('role','group');bar.setAttribute('aria-label','选中文字操作');bar.innerHTML='<button data-h title="高亮（Alt+H）"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 14 7-10 5 5-10 7-2-2Zm0 0-4 4m-2 3h12"/></svg>高亮</button><button data-n title="写批注（Alt+M）"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 4 5 5-11 11-6 1 1-6L15 4Zm-9 10 5 5"/></svg>写批注</button><button data-x aria-label="关闭选区工具" title="关闭（Esc）"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg></button>';document.body.append(bar);
  bar.addEventListener('mousedown',e=>e.preventDefault());bar.querySelector('[data-x]').onclick=()=>{bar.hidden=true;pending=null;};
  const editor=document.createElement('dialog');editor.id='annedit';editor.innerHTML='<h2>我的批注</h2><p class="ann-quote"></p><label>笔记<textarea rows="5"></textarea></label><div class="dialog-tools"><button data-save>保存</button><button data-cancel>取消</button></div>';document.body.append(editor);
  function openEditor(a=null){editing=a?a.id:null;editor.querySelector('.ann-quote').textContent=a?a.text:pending.text;editor.querySelector('textarea').value=a?a.note:'';editor.showModal();editor.querySelector('textarea').focus();}
  function commit(note){if(editing){const a=items.find(x=>x.id===editing);if(a)a.note=note;}else if(pending){items.push({...pending,id:uid(),note,ts:Date.now(),revision:config.revision});}else return;
    const ok=save();paint();pending=null;bar.hidden=true;getSelection().removeAllRanges();if(ok)toast('已保存到此浏览器；换设备前请导出备份。');}
  bar.querySelector('[data-h]').onclick=()=>{editing=null;commit('');};bar.querySelector('[data-n]').onclick=()=>{if(pending)openEditor();};
  editor.querySelector('[data-save]').onclick=()=>{commit(editor.querySelector('textarea').value);editor.close();};editor.querySelector('[data-cancel]').onclick=()=>editor.close();
  editor.querySelector('textarea').addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();editor.querySelector('[data-save]').click();}});
  document.addEventListener('mouseup',e=>{if(e.target.closest('#annbar,dialog,#annbtn'))return;setTimeout(()=>{pending=selection();bar.hidden=!pending;},0);});
  document.addEventListener('keyup',e=>{if(e.key==='Shift'){pending=selection();bar.hidden=!pending;}});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){bar.hidden=true;pending=null;}if(e.altKey&&['h','m'].includes(e.key.toLowerCase())){e.preventDefault();pending=selection();if(!pending){toast('请在同一段的同一栏选取文字，避开公式。');return;}if(e.key.toLowerCase()==='h'){editing=null;commit('');}else openEditor();}});
  document.addEventListener('click',e=>{const mark=e.target.closest('mark[data-ann]');if(mark){const a=items.find(x=>x.id===mark.dataset.ann);if(a)openEditor(a);}});
  const panel=document.createElement('dialog');panel.id='annpanel';panel.innerHTML='<h2>批注与备份</h2><p>记录保存在当前浏览器。移动文件、换浏览器或清理存储后可能无法自动恢复；请导出 JSON，再在同一论文页面导入。</p><div class="dialog-tools"><button data-json>导出 JSON</button><button data-md>导出 Markdown</button><button data-import>导入 JSON</button><button data-close>关闭</button></div><input type="file" accept="application/json,.json" hidden><p class="import-status" role="status"></p><div class="ann-list"></div>';document.body.append(panel);
  const btn=document.createElement('button');btn.id='annbtn';btn.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 4 5 5-11 11-6 1 1-6L15 4Zm-9 10 5 5"/></svg>';document.body.append(btn);btn.onclick=()=>{renderList();panel.showModal();};panel.querySelector('[data-close]').onclick=()=>panel.close();
  function jump(a){const c=findContainer(a.cid);if(!c||a.orphan){toast('原文已变化，批注保留在列表中，未强行定位。');return;}panel.close();const card=c.closest('[id]');if(card)reveal(card.id);let p=c.parentElement;while(p){if(p.tagName==='DETAILS')p.open=true;p=p.parentElement;}c.scrollIntoView({block:'center'});}
  function renderList(){const list=panel.querySelector('.ann-list');list.replaceChildren();for(const a of items){const row=document.createElement('div');row.className='ann-item';const quote=document.createElement('p');quote.className='ann-quote';quote.textContent=a.text;const note=document.createElement('p');note.textContent=a.note||'（仅高亮）';row.append(quote,note);if(a.orphan){const warning=document.createElement('p');warning.className='ann-orphan';warning.textContent='原文变化或定位不唯一，需人工重新定位';row.append(warning);}for(const [label,action]of [['跳转',()=>jump(a)],['编辑',()=>{panel.close();openEditor(a);}],['删除',()=>{items=items.filter(x=>x.id!==a.id);save();paint();}]]){const b=document.createElement('button');b.textContent=label;b.onclick=action;row.append(b);}list.append(row);}}
  panel.querySelector('[data-json]').onclick=()=>download('批注备份.json',JSON.stringify({schema:2,paperId:config.paperId,revision:config.revision,items},null,2),'application/json');
  panel.querySelector('[data-md]').onclick=()=>download('批注.md',['# '+config.title+' · 我的批注','',...items.flatMap(a=>['> '+a.text,a.note,'定位：'+a.cid+(a.orphan?'（待重定位）':''),''])].join('\n'),'text/markdown;charset=utf-8');
  const file=panel.querySelector('input');panel.querySelector('[data-import]').onclick=()=>file.click();
  file.onchange=async()=>{const message=panel.querySelector('.import-status');try{if(!file.files[0])return;const data=JSON.parse(await file.files[0].text());if(data.schema!==2||data.paperId!==config.paperId||!Array.isArray(data.items)||!data.items.every(valid)||new Set(data.items.map(a=>a.id)).size!==data.items.length)throw Error('文件格式或论文标识不匹配');let added=0;for(const a of data.items){const old=items.find(x=>x.id===a.id);if(old&&old.cid===a.cid&&old.text===a.text&&old.note===a.note)continue;items.push({...a,id:old?uid():a.id});added++;}const ok=save();paint();message.textContent=`导入 ${added} 条；`+(ok?'已保存。':'保存失败，请导出备份。');}catch(e){message.textContent='导入失败：'+e.message;}finally{file.value='';}};
  window.__ann={paint,get items(){return items;}};paint();
})();
