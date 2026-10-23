/* Dedicated print document: source DOM and reading/annotation state stay intact. */
(()=>{
  'use strict';
  const reader=window.reader;
  if(!reader)return;
  let documentNode=null,pageStyle=null,previousTitle=null;
  const element=(tag,className,text)=>{const el=document.createElement(tag);if(className)el.className=className;if(text!==undefined)el.textContent=text;return el;};
  function copy(node){
    if(!node)return null;
    const clone=node.cloneNode(true);
    for(const el of [clone,...clone.querySelectorAll('*')]){
      for(const attr of [...el.attributes])if(attr.name==='id'||attr.name==='hidden'||attr.name.startsWith('data-')||attr.name.startsWith('on'))el.removeAttribute(attr.name);
    }
    // The reader wraps source images in zoom buttons; unwrap those before removing controls.
    clone.querySelectorAll('button').forEach(el=>{if(el.querySelector('img'))el.replaceWith(...el.childNodes);else el.remove();});
    clone.querySelectorAll('input,select,textarea,dialog,.ann-marker,.ann-actions').forEach(el=>el.remove());
    clone.querySelectorAll('details').forEach(el=>el.open=true);
    // Original in-page references have no targets in a static export.
    clone.querySelectorAll('a[href^="#"]').forEach(el=>el.removeAttribute('href'));
    return clone;
  }
  function restore(){
    document.body.classList.remove('reader-pdf-export');
    documentNode?.remove();pageStyle?.remove();documentNode=null;pageStyle=null;
    if(previousTitle!==null){document.title=previousTitle;previousTitle=null;}
    delete document.documentElement.dataset.readerPdfReady;
  }
  function prepare(options={}){
    restore();
    const notes=options.notes!==false,aux=options.aux===true;
    const paper=options.paper==='portrait'?'portrait':'landscape';
    const out=element('main','pdf-document');out.id='reader-pdf-document';
    const chineseSource=reader.config.sourceLanguage==='zh';
    out.append(element('p','pdf-kicker',chineseSource?'SCHOLARFLOW · 原文与对照文本':'SCHOLARFLOW · 中英双语对照'),element('h1','',reader.config.title),element('p','pdf-citation',reader.config.citation));
    out.append(element('p','pdf-intro','左栏原文 · 右栏中文译文'+(notes?' · 附白话与逻辑':'')+'。词汇释义按本段语境整理。动图与批注保留在 HTML 阅读页。'));
    const draft=document.querySelector('body > header .warning');if(draft)out.append(copy(draft));
    let count=0;
    for(const section of document.querySelectorAll('#mode-full > .fsect')){
      const cards=[...section.children].filter(el=>el.matches('.pcard,.source-block')&&(aux||!el.matches('.compact-info')));
      if(!cards.length)continue;
      const group=element('section','pdf-section');group.append(element('h2','',section.querySelector('h2')?.textContent||''));
      for(const card of cards){
        const paragraph=element('article','pdf-paragraph');
        const en=card.querySelector('.orig'),zh=card.querySelector('.zh');
        const locator=reader.config.blocks[card.id];
        if(en&&zh){
          count++;
          paragraph.append(element('p','pdf-locator','段落 '+count+(locator?.page?' · PDF 第 '+locator.page+' 页':'')));
          const table=element('table','pdf-pair'),head=element('thead'),hr=element('tr');
          hr.append(element('th','',chineseSource?'中文原文':'ENGLISH · 原文'),element('th','',chineseSource?'对照文本':'中文译文'));head.append(hr);table.append(head);
          const row=element('tr'),left=element('td'),right=element('td');left.append(copy(en));right.append(copy(zh));row.append(left,right);
          const body=element('tbody');body.append(row);table.append(body);paragraph.append(table);
          if(notes){
            const note=card.querySelector('.note'),logic=card.querySelector('.logic ul'),trap=card.querySelector('.trap');
            if(note){paragraph.append(element('h3','','白话解释'),copy(note));}
            if(logic){paragraph.append(element('h3','','逻辑要点'),copy(logic));}
            if(trap)paragraph.append(copy(trap));
          }
          const vocabulary=card.querySelector('.paragraph-vocabulary');if(vocabulary)paragraph.append(copy(vocabulary));
        }else{
          paragraph.append(copy(card));
          // MathML is the print form; the raw LaTeX fallback remains if conversion failed.
          if(paragraph.querySelector('math'))paragraph.querySelectorAll('details').forEach(el=>el.remove());
        }
        group.append(paragraph);
      }
      out.append(group);
    }
    const source=element('section','pdf-attribution');source.append(element('h2','','来源与归属'));
    const notesNode=document.getElementById('source-notes');
    if(notesNode){const scope=notesNode.querySelector(':scope > p');if(scope)source.append(copy(scope));const attribution=notesNode.querySelector('.source-attribution');if(attribution)source.append(copy(attribution));}
    source.append(element('p','','由 ScholarFlow paper-close-read '+reader.config.generatorVersion+' 生成；译文、词汇与讲解为 AI 辅助整理。'));
    out.append(source);document.body.append(out);documentNode=out;
    pageStyle=element('style');pageStyle.textContent='@page { size: A4 '+paper+'; margin: 13mm 13mm 16mm; @bottom-right { content: counter(page); font: 9pt sans-serif; color: #6b6660; } }';document.head.append(pageStyle);
    previousTitle=document.title;document.title=reader.config.title+'_中英双语';document.body.classList.add('reader-pdf-export');
    document.documentElement.dataset.readerPdfReady='true';return {paragraphs:count,paper,notes,aux};
  }
  const dialog=element('dialog','pdf-dialog');dialog.setAttribute('aria-labelledby','pdf-dialog-title');
  dialog.innerHTML='<form method="dialog"><h2 id="pdf-dialog-title">导出中英双语 PDF</h2><p>将全文排成左右对照页。在浏览器打印窗口中选择「另存为 PDF」。无需联网或上传论文。</p><label>纸张方向 <select name="paper"><option value="landscape">A4 横向 · 推荐</option><option value="portrait">A4 纵向</option></select></label><label><input name="notes" type="checkbox" checked> 包含白话解释和逻辑要点</label><label><input name="aux" type="checkbox"> 包含作者信息、原始参考文献等附录</label><p class="muted">词汇随段落保留；动图的交互效果请在 HTML 中查看。</p><div class="pdf-dialog-actions"><button value="cancel">取消</button><button type="button" id="pdf-print">排版并打开打印</button></div></form>';
  document.body.append(dialog);
  document.getElementById('export-pdf')?.addEventListener('click',event=>reader.openDialog(dialog,event.currentTarget));
  dialog.querySelector('#pdf-print').addEventListener('click',async()=>{
    const form=dialog.querySelector('form');prepare({paper:form.elements.paper.value,notes:form.elements.notes.checked,aux:form.elements.aux.checked});dialog.close();
    if(document.fonts)await document.fonts.ready;
    try{window.print();}finally{restore();}
  });
  addEventListener('afterprint',restore);
  window.readerPDF={prepare,restore};
  const query=new URLSearchParams(location.search);
  if(query.get('reader-pdf')==='1')prepare({paper:query.get('paper'),notes:query.get('notes')!=='0',aux:query.get('aux')==='1'});
})();
