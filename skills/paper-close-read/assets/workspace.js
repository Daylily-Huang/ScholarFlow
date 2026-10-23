/* Reader-owned notes and backups. All operations stay on the current device. */
(()=>{'use strict';
 const reader=window.reader,P=window.ReaderPersistence,cfg=reader.config;
 const tools=document.createElement('button');tools.id='reader-tools';tools.type='button';tools.textContent='阅读工具';tools.setAttribute('aria-haspopup','dialog');document.querySelector('.toolbar').append(tools);
 const panel=document.createElement('dialog');panel.id='reader-workspace';panel.setAttribute('aria-labelledby','workspace-title');
 panel.innerHTML='<h2 id="workspace-title">阅读工具</h2><p class="workspace-intro">整篇笔记、备份与快捷键，都在这里。记录仅保存在当前浏览器。</p><label for="document-note">整篇笔记</label><textarea id="document-note" rows="6" maxlength="1000000" placeholder="这篇论文给我的启发、仍没懂的问题、下次要读的内容…"></textarea><p class="workspace-note-status" role="status"></p><h3>带走阅读记录</h3><div class="dialog-tools"><button data-backup>下载完整备份</button><button data-restore>导入备份</button><button data-markdown>导出阅读笔记</button><button data-standard>标准批注 JSON-LD</button></div><p class="workspace-hint">完整备份包含高亮、批注、已读、复述、阅读位置和整篇笔记。兼容原有批注JSON；导入合并，冲突批注保留两份。JSON-LD供标准批注工具使用，定位目标是本带读页。</p><input type="file" accept="application/json,.json" hidden><p class="workspace-import-status" role="status"></p><div class="workspace-recovery"></div><h3>键盘阅读</h3><dl class="shortcut-list"><dt>/</dt><dd>搜索</dd><dt>Alt + R</dt><dd>继续上次</dd><dt>Alt + 1 / 2 / 3</dt><dd>逐段 / 三分钟 / 十分钟</dd><dt>Alt + H / M</dt><dd>选中文字后高亮 / 批注</dd><dt>?</dt><dd>打开阅读工具</dd><dt>Esc</dt><dd>关闭工具或对话框</dd></dl><div class="dialog-tools"><button data-close>完成</button></div>';
 document.body.append(panel);const note=panel.querySelector('textarea'),status=panel.querySelector('.workspace-note-status');let noteTimer,noteDirty=false;
 function flushNote(){clearTimeout(noteTimer);if(!noteDirty)return;noteDirty=false;if(note.value!==reader.getState().documentNote){const typed=note.value,saved=reader.setDocumentNote(typed),current=reader.getState().documentNote;note.value=current;status.textContent=saved?(current===typed?'整篇笔记已保存':'两个窗口的笔记均已保留，请整理合并内容'):'笔记暂存本页，请下载完整备份';}}
 function open(){note.value=reader.getState().documentNote;status.textContent='';noteDirty=false;reader.openDialog(panel,tools);}
 tools.onclick=open;panel.querySelector('[data-close]').onclick=()=>{flushNote();panel.close();};panel.addEventListener('cancel',flushNote);note.addEventListener('input',()=>{noteDirty=true;clearTimeout(noteTimer);noteTimer=setTimeout(flushNote,500);});addEventListener('pagehide',flushNote);
 function metadata(a){const id=a.cid.replace(/-(en|zh|note)$/,''),meta=cfg.blocks[id];return meta?meta.section+(meta.page?' · PDF第'+meta.page+'页'+(meta.verified?'':'（定位待核对）'):'')+' · '+id:'带读页段落 '+a.cid;}
 function markdown(){flushNote();reader.capturePosition();const state=reader.getState(),lines=['# '+cfg.title+' · 阅读笔记','',cfg.citation||'', '论文标识：'+cfg.paperId,'内容版本：'+cfg.revision,''];
  if(state.documentNote)lines.push('## 整篇笔记',state.documentNote,'');
  lines.push('## 已读与阅读位置','已读 '+state.read.length+' 段。',...state.read.map(id=>'- '+(cfg.blocks[id]?.section||'正文')+' · '+id),'');
  for(const [route,pos]of Object.entries(state.positions||{}))lines.push('阅读位置：'+({'full':'逐段精读','quick':'三分钟入门','deep':'十分钟读懂'}[route]||route)+' · '+pos.id);
  const recalls=Object.entries(state.recall||{}).filter(([,v])=>v.trim());if(recalls.length)lines.push('','## 我的复述',...recalls.flatMap(([k,v])=>['### 问题 '+(Number(k)+1),v,'']));
  const items=window.__ann?.items||[];if(items.length)lines.push('','## 高亮与批注',...items.flatMap(a=>['> '+a.text.replace(/\n/g,'\n> '),a.note||'（仅高亮）','来源：'+metadata(a)+(a.orphan?'（原文变化，待重定位）':''),'']));
  reader.download('阅读笔记.md',lines.join('\n'),'text/markdown;charset=utf-8');
 }
 reader.annotationMetadata=metadata;reader.exportMarkdown=markdown;panel.querySelector('[data-markdown]').onclick=markdown;
 panel.querySelector('[data-backup]').onclick=()=>{flushNote();reader.capturePosition();const payload={schema:3,kind:'scholarflow-reading-backup',paperId:cfg.paperId,revision:cfg.revision,exportedAt:new Date().toISOString(),reading:reader.getState(),annotations:P.annotations(window.__ann?.items||[])};const text=JSON.stringify(payload,null,2);reader.download('完整阅读备份.json',text,'application/json');if(new Blob([text]).size>P.MAX_FILE)status.textContent='完整数据已下载。超过32 MB的备份需先拆分批注文件再导入；请同时导出阅读笔记保存可读副本。';};
 panel.querySelector('[data-standard]').onclick=()=>reader.download('标准批注.jsonld',JSON.stringify(P.webAnnotations(window.__ann?.items||[],cfg),null,2),'application/ld+json');
 const file=panel.querySelector('input[type=file]'),message=panel.querySelector('.workspace-import-status');panel.querySelector('[data-restore]').onclick=()=>{flushNote();file.click();};
 file.onchange=async()=>{try{flushNote();if(!file.files[0])return;if(file.files[0].size>P.MAX_FILE)throw Error('备份过大；支持32 MB以内的JSON');const data=P.readBackup(await file.files[0].text(),cfg.paperId,reader.allowed);if(data.reading)reader.previewImportState(data.reading);const result=window.__ann.importItems(data.annotations);if(data.reading)reader.importState(data.reading);note.value=reader.getState().documentNote;message.textContent='已导入 '+result.added+' 条批注'+(data.reading?'及阅读记录':'')+'。'+(result.conflicts?'冲突批注均已保留。':'');}catch(e){message.textContent='导入失败：'+e.message;}finally{file.value='';}};
 const recovery=panel.querySelector('.workspace-recovery');for(const [label,get]of [['阅读记录',reader.recoveryRaw],['批注',()=>window.__ann.recoveryRaw()]]){const raw=get();if(raw!==null&&raw!==undefined){const b=document.createElement('button');b.textContent='导出原始损坏'+label;b.onclick=()=>reader.download('原始'+label+'.txt',raw,'text/plain;charset=utf-8');recovery.append(b);}}
 document.addEventListener('keydown',e=>{if(e.defaultPrevented||e.target.closest('input,textarea,select,[contenteditable=true],dialog')||document.querySelector('dialog[open]'))return;
  if(e.key==='/'&&!e.ctrlKey&&!e.metaKey&&!e.altKey){e.preventDefault();document.getElementById('search').focus();}
  else if(e.key==='?'&&!e.ctrlKey&&!e.metaKey){e.preventDefault();open();}
  else if(e.altKey&&e.key.toLowerCase()==='r'){e.preventDefault();reader.resume();}
  else if(e.altKey&&['1','2','3'].includes(e.key)){e.preventDefault();document.querySelector('[data-route='+({'1':'full','2':'quick','3':'deep'}[e.key])+']').click();}
 });
})();
