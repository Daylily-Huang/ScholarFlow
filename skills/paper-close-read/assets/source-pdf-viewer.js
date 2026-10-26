/* Actual rendered PDF pages, embedded once per page in the single-file reader. */
(()=>{'use strict';
 const reader=window.reader,config=reader?.config.sourcePdf;if(!config?.pages?.length)return;
 const dialog=document.createElement('dialog');dialog.id='source-pdf-viewer';dialog.setAttribute('aria-labelledby','source-pdf-title');
 dialog.innerHTML='<h2 id="source-pdf-title">PDF 原页</h2><div class="pdf-page-tools"><button type="button" data-page-prev aria-label="上一原页">←</button><label>PDF 文件页 <select data-page-select></select></label><button type="button" data-page-next aria-label="下一原页">→</button><button type="button" data-page-out aria-label="缩小原页">−</button><select data-page-zoom aria-label="原页缩放"><option value="fit">适应宽度</option><option value="50">50%</option><option value="75">75%</option><option value="100">100%</option><option value="125">125%</option><option value="150">150%</option><option value="200">200%</option></select><button type="button" data-page-in aria-label="放大原页">＋</button></div><p class="pdf-page-location" role="status"></p><div class="pdf-page-stage"><img alt=""></div><p class="pdf-page-hint">真实 PDF 原页图像 · 拖标题移动，拖右下角调整窗口；图片清晰度取决于准备原页的分辨率。</p>';
 document.body.append(dialog);window.ReaderFloatingWindow.attach(dialog);
 const select=dialog.querySelector('[data-page-select]'),zoom=dialog.querySelector('[data-page-zoom]'),image=dialog.querySelector('img'),stage=dialog.querySelector('.pdf-page-stage'),status=dialog.querySelector('.pdf-page-location');
 for(const page of config.pages){const option=document.createElement('option');option.value=String(page.page);option.textContent=String(page.page);select.append(option);}
 let index=0,opener=null,located=false,browsing=false;
 function scale(){image.style.width=zoom.value==='fit'?'100%':zoom.value+'%';image.style.maxWidth='none';}
 function draw(){
  const current=config.pages[index];image.src=current.image;image.alt='原PDF文件第 '+current.page+' 页';select.value=String(current.page);scale();stage.scrollTo(0,0);
  status.textContent=(browsing?'原页浏览中，可与正文对照。':located?'已按核对记录定位。':'本段页码未核实，可翻页对照。')+' 当前 PDF 第 '+current.page+' / '+config.pageCount+' 页；已内嵌 '+config.pages.length+' 页。';
  dialog.querySelector('[data-page-prev]').disabled=index===0;dialog.querySelector('[data-page-next]').disabled=index===config.pages.length-1;
 }
 function open(page,trigger){
  opener=trigger||document.activeElement;
  const chosen=config.pages.findIndex(p=>p.page===Number(page));located=chosen>=0&&Number(page)>0;index=located?chosen:0;browsing=false;
  draw();if(!dialog.open)dialog.show();dialog.querySelector('[data-window-close]').focus({preventScroll:true});
 }
 select.onchange=()=>{index=config.pages.findIndex(p=>p.page===Number(select.value));browsing=true;draw();};
 dialog.querySelector('[data-page-prev]').onclick=()=>{if(index>0){index--;browsing=true;draw();}};
 dialog.querySelector('[data-page-next]').onclick=()=>{if(index<config.pages.length-1){index++;browsing=true;draw();}};
 zoom.onchange=scale;
 function changeZoom(amount){const current=zoom.value==='fit'?100:Number(zoom.value),choices=[50,75,100,125,150,200];zoom.value=String(amount>0?(choices.find(v=>v>current)||200):([...choices].reverse().find(v=>v<current)||50));scale();}
 dialog.querySelector('[data-page-out]').onclick=()=>changeZoom(-25);dialog.querySelector('[data-page-in]').onclick=()=>changeZoom(25);
 dialog.addEventListener('close',()=>{if(opener?.isConnected)opener.focus({preventScroll:true});});
 document.addEventListener('keydown',event=>{if(event.key==='Escape'&&dialog.open&&!document.querySelector('dialog:modal')){event.preventDefault();dialog.close();}});
 document.addEventListener('click',event=>{const button=event.target.closest('[data-open-pdf-page]');if(button)open(button.dataset.openPdfPage,button);});
 const toolbar=document.createElement('button');toolbar.type='button';toolbar.textContent='查看 PDF 原文';toolbar.dataset.openPdfPage='';document.querySelector('.toolbar').append(toolbar);
 window.readerPdfPages={open};
})();
