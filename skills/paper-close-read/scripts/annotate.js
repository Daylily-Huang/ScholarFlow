/* Portable annotations: stable content ID + exact quote + context; never silently misattach. */
(() => {
  'use strict';
  const {config,toast,download,reveal}=window.reader;
  const key='close-read:v2:'+config.paperId+':annotations';
  const persistence=window.ReaderPersistence;
  let items=[], pending=null, editing=null, deleted=null;
  const store=persistence.localStore(key,[],persistence.annotations,persistence.mergeAnnotations);
  items=store.value;
  const containers=new Map([...document.querySelectorAll('[data-ann-id]')].map(el=>[el.dataset.annId,el]));
  const findContainer=id=>containers.get(id);
  function nodes(el){const w=document.createTreeWalker(el,NodeFilter.SHOW_TEXT,{acceptNode:n=>n.parentElement.closest('math,button,script,style')?NodeFilter.FILTER_REJECT:NodeFilter.FILTER_ACCEPT});const a=[];while(w.nextNode())a.push(w.currentNode);return a;}
  const textOf=el=>nodes(el).map(n=>n.textContent).join('');
  const uid=persistence.uid;
  if(store.warning)toast('批注记录暂未恢复；仍可阅读，原有数据会保留备份。');
  function save(){const ok=store.save(items);items=store.value;if(!ok)toast('批注暂存本页；请在阅读工具中导出完整备份。');else if(store.conflicts)toast('两个窗口的批注修改都已保留，请在列表中比较。');return ok;}
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
  function selection(){const s=getSelection();if(!s||s.isCollapsed||!s.rangeCount)return null;const r=s.getRangeAt(0);const parent=n=>n.nodeType===3?n.parentElement:n;const a=parent(r.startContainer).closest('[data-ann-id]'),b=parent(r.endContainer).closest('[data-ann-id]');if(!a||a!==b)return null;const start=offset(a,r.startContainer,r.startOffset),end=offset(a,r.endContainer,r.endOffset);if(start<0||end<=start)return null;const full=textOf(a),text=full.slice(start,end);if(text!==s.toString())return null;return {cid:a.dataset.annId,start,end,text,prefix:Array.from(full.slice(0,start)).slice(-24).join(''),suffix:Array.from(full.slice(end)).slice(0,24).join('')};}
  const bar=document.createElement('div');bar.id='annbar';bar.hidden=true;bar.setAttribute('role','group');bar.setAttribute('aria-label','选中文字操作');bar.innerHTML='<button data-h title="高亮（Alt+H）"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m9 14 7-10 5 5-10 7-2-2Zm0 0-4 4m-2 3h12"/></svg>高亮</button><button data-n title="写批注（Alt+M）"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 4 5 5-11 11-6 1 1-6L15 4Zm-9 10 5 5"/></svg>写批注</button><button data-x aria-label="关闭选区工具" title="关闭（Esc）"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="m6 6 12 12M18 6 6 18"/></svg></button>';document.body.append(bar);
  bar.addEventListener('mousedown',e=>e.preventDefault());bar.querySelector('[data-x]').onclick=()=>{bar.hidden=true;pending=null;};
  const editor=document.createElement('dialog');editor.id='annedit';editor.setAttribute('aria-labelledby','annedit-title');editor.innerHTML='<h2 id="annedit-title">我的批注</h2><p class="ann-quote"></p><label>笔记<textarea rows="5"></textarea></label><div class="dialog-tools"><button data-save>保存</button><button data-cancel>取消</button></div>';document.body.append(editor);
  function openEditor(a=null){editing=a?a.id:null;editor.querySelector('.ann-quote').textContent=a?a.text:pending.text;editor.querySelector('textarea').value=a?a.note:'';const target=findContainer(a?a.cid:pending.cid);if(target)target.tabIndex=-1;window.reader.openDialog(editor,target&&target.getBoundingClientRect().height?target:btn);editor.querySelector('textarea').focus();}
  function commit(note){if(note.length>200000||pending?.text.length>100000){toast('选区或笔记过长，请缩短后保存。');return;}if(editing){const a=items.find(x=>x.id===editing);if(a){a.note=note;a.updatedAt=Date.now();}}else if(pending){if(items.length>=persistence.MAX_ITEMS){toast('当前已达10000条批注，请先导出整理。');return;}items.push({...pending,id:uid(),note,ts:Date.now(),revision:config.revision});}else return;
    const ok=save();paint();pending=null;bar.hidden=true;getSelection().removeAllRanges();if(ok&&!store.conflicts)toast('批注已保存');}
  bar.querySelector('[data-h]').onclick=()=>{editing=null;commit('');};bar.querySelector('[data-n]').onclick=()=>{if(pending)openEditor();};
  editor.querySelector('[data-save]').onclick=()=>{commit(editor.querySelector('textarea').value);editor.close();};editor.querySelector('[data-cancel]').onclick=()=>editor.close();
  editor.querySelector('textarea').addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key==='Enter'){e.preventDefault();editor.querySelector('[data-save]').click();}});
  document.addEventListener('mouseup',e=>{if(e.target.closest('#annbar,dialog,#annbtn'))return;setTimeout(()=>{pending=selection();bar.hidden=!pending;},0);});
  document.addEventListener('keyup',e=>{if(e.key==='Shift'){pending=selection();bar.hidden=!pending;}});
  document.addEventListener('keydown',e=>{if(e.key==='Escape'){bar.hidden=true;pending=null;}if(!e.target.closest('input,textarea,select,[contenteditable=true]')&&e.altKey&&['h','m'].includes(e.key.toLowerCase())){e.preventDefault();pending=selection();if(!pending){toast('请在同一段的同一栏选取文字，避开公式。');return;}if(e.key.toLowerCase()==='h'){editing=null;commit('');}else openEditor();}});
  document.addEventListener('click',e=>{const mark=e.target.closest('mark[data-ann]');if(mark){const a=items.find(x=>x.id===mark.dataset.ann);if(a)openEditor(a);}});
  const panel=document.createElement('dialog');panel.id='annpanel';panel.setAttribute('aria-labelledby','annpanel-title');panel.innerHTML='<h2 id="annpanel-title">批注与备份</h2><p>记录保存在当前浏览器。移动文件、换浏览器或清理存储后可能无法自动恢复；请导出 JSON，再在同一论文页面导入。</p><div class="dialog-tools"><button data-json>导出 JSON</button><button data-md>导出 Markdown</button><button data-import>导入 JSON</button><button data-undo disabled>撤销删除</button><button data-close>关闭</button></div><label>查找批注<input type="search" data-ann-search placeholder="搜索引句或笔记"></label><input type="file" accept="application/json,.json" hidden><p class="import-status" role="status"></p><p class="ann-list-count" role="status"></p><div class="ann-list"></div>';document.body.append(panel);
  const btn=document.createElement('button');btn.id='annbtn';btn.innerHTML='<svg viewBox="0 0 24 24" aria-hidden="true"><path d="m15 4 5 5-11 11-6 1 1-6L15 4Zm-9 10 5 5"/></svg>';document.body.append(btn);btn.onclick=()=>{renderList();window.reader.openDialog(panel,btn);};panel.querySelector('[data-close]').onclick=()=>panel.close();
  function jump(a){const c=findContainer(a.cid);if(!c||a.orphan){toast('原文已变化，批注保留在列表中，未强行定位。');return;}panel.close();const card=c.closest('[id]');if(card)reveal(card.id);let p=c.parentElement;while(p){if(p.tagName==='DETAILS')p.open=true;p=p.parentElement;}c.scrollIntoView({block:'center'});}
  function renderList(){const list=panel.querySelector('.ann-list');list.replaceChildren();const query=panel.querySelector('[data-ann-search]').value.trim().toLocaleLowerCase(),filtered=items.filter(a=>!query||(a.text+' '+a.note).toLocaleLowerCase().includes(query));panel.querySelector('.ann-list-count').textContent=filtered.length?'共 '+filtered.length+' 条'+(filtered.length>200?'，显示前200条，可继续搜索':''):'还没有匹配的批注';for(const a of filtered.slice(0,200)){const row=document.createElement('div');row.className='ann-item';const quote=document.createElement('p');quote.className='ann-quote';quote.textContent=a.text;const note=document.createElement('p');note.textContent=a.note||'（仅高亮）';row.append(quote,note);if(a.orphan){const warning=document.createElement('p');warning.className='ann-orphan';warning.textContent='原文变化或定位不唯一，需人工重新定位';row.append(warning);}for(const [label,action]of [['跳转',()=>jump(a)],['编辑',()=>{panel.close();openEditor(a);}],['删除',()=>{deleted=persistence.clone(a);items=items.filter(x=>x.id!==a.id);save();paint();panel.querySelector('[data-undo]').disabled=false;toast('已删除，可撤销');}]]){const b=document.createElement('button');b.textContent=label;b.onclick=action;row.append(b);}list.append(row);}}
  panel.querySelector('[data-json]').onclick=()=>download('批注备份.json',JSON.stringify({schema:2,paperId:config.paperId,revision:config.revision,items},null,2),'application/json');
  panel.querySelector('[data-md]').onclick=()=>download('批注.md',['# '+config.title+' · 我的批注','',config.citation||'','',...items.flatMap(a=>['> '+a.text,a.note,'来源：'+(window.reader.annotationMetadata?window.reader.annotationMetadata(a):a.cid)+(a.orphan?'（待重定位）':''),''])].join('\n'),'text/markdown;charset=utf-8');
  const file=panel.querySelector('input[type=file]');panel.querySelector('[data-import]').onclick=()=>file.click();
  function importItems(incoming){const merged=persistence.importAnnotations(items,incoming);items=merged.value;const ok=save();paint();return {...merged,saved:ok};}
  file.onchange=async()=>{const message=panel.querySelector('.import-status');try{
    if(!file.files[0])return;if(file.files[0].size>persistence.MAX_FILE)throw Error('备份过大；支持32 MB以内的JSON');
    const data=persistence.readBackup(await file.files[0].text(),config.paperId,window.reader.allowed);
    if(data.reading)window.reader.previewImportState(data.reading);const result=importItems(data.annotations);if(data.reading)window.reader.importState(data.reading);
    message.textContent=`导入 ${result.added} 条；`+(result.saved?'已保存。':'暂存本页，请导出备份。')+(result.conflicts?'冲突版本均已保留。':'');
   }catch(e){message.textContent='导入失败：'+e.message;}finally{file.value='';}};
  panel.querySelector('[data-ann-search]').addEventListener('input',renderList);
  panel.querySelector('[data-undo]').onclick=()=>{if(!deleted)return;items=persistence.importAnnotations(items,[deleted]).value;deleted=null;save();paint();panel.querySelector('[data-undo]').disabled=true;toast('已恢复删除的批注');};
  let selectionTimer;document.addEventListener('selectionchange',()=>{clearTimeout(selectionTimer);selectionTimer=setTimeout(()=>{if(editor.open||panel.open)return;pending=selection();bar.hidden=!pending;},120);});
  addEventListener('storage',e=>{if(e.key!==key)return;if(editor.open){toast('另一窗口有新批注；保存时会合并并保留冲突版本。');return;}if(store.refresh()){items=store.value;paint();}});
  window.__ann={paint,importItems,recoveryRaw:()=>store.recoveryRaw,get items(){return items;}};paint();
})();
