"""Exercise real reader HTML in Chromium; reports bind checks to actual HTML hashes."""
import argparse,hashlib,json,sys,uuid
from pathlib import Path

def run(folders,work,output,executable=None,headless=False):
 from playwright.sync_api import sync_playwright
 work=Path(work).resolve()/('run-'+uuid.uuid4().hex[:10]);work.mkdir(parents=True,exist_ok=True);output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
 reports=[]
 with sync_playwright() as pw:
  for folder in folders:
   folder=Path(folder).resolve();html=folder/'reader.html';checks=[];errors=[];network=[]
   def ok(condition,label):
    if not condition:raise AssertionError(str(folder)+': '+label)
    checks.append(label)
   context=pw.chromium.launch_persistent_context(str(work/(folder.name+'-profile')),executable_path=executable,headless=headless,viewport={'width':1500,'height':1050},offline=True,accept_downloads=True)
   page=context.pages[0];page.on('pageerror',lambda e:errors.append(str(e)));page.on('request',lambda req:network.append(req.url) if req.url.startswith(('http://','https://')) else None)
   page.goto(html.as_uri());page.wait_for_timeout(150)
   ok(page.locator('#mode-full').is_visible(),'初次进入逐段精读')
   ok(page.evaluate("getComputedStyle(document.documentElement).fontSize==='18px'"),'18px默认')
   ok(page.evaluate("[...document.querySelectorAll('.bilingual,.logic')].every(x=>x.open)"),'正文与逻辑默认展开')
   ok(page.evaluate("[...document.querySelectorAll('[id]')].map(x=>x.id).length===new Set([...document.querySelectorAll('[id]')].map(x=>x.id)).size"),'无重复DOM标识')
   ok(page.evaluate("[...document.querySelectorAll('a[href^=\"#\"]')].every(x=>!x.hash||document.getElementById(x.hash.slice(1)))"),'全部内部链接存在目标')
   ok(page.evaluate("[...document.querySelectorAll('img')].every(x=>x.complete&&x.naturalWidth>0)"),'内嵌原图完整加载')
   ok(page.locator('.source-attribution').count()==1,'单文件保留作者、来源与许可')
   button=page.locator('[data-read]').first;button.click();page.reload();ok(page.locator('[data-read]').first.get_attribute('aria-pressed')=='true','已读刷新恢复')
   search=page.locator('#search');guide=json.loads((folder/'reading-data/guide.json').read_text(encoding='utf-8'));records=json.loads((folder/'reading-data/translations.json').read_text(encoding='utf-8'));query=next(r['note'][:4] for r in records if r.get('role','body')=='body');search.fill(query);ok(page.locator('#search-count').inner_text()!='0 个匹配内容块','中文检索');search.fill('');ok(page.locator('.pcard:visible').count()==page.locator('.pcard').count(),'清空检索恢复')
   data=json.loads((folder/'reading-data/fulltext.json').read_text(encoding='utf-8'));source_items=[it for sec in data['sections'] for it in sec['items']]
   rich=[it for it in source_items if it['source'].get('inline_runs') and next((r.get('role','body')=='body' for r in records if r['id']==it['id']),False)]
   if rich:
    ok(all(page.locator('[data-ann-id="'+it['id']+'-en"]').inner_text()==it['raw'].strip() for it in rich),'样式与链接不改变原文字符')
    notes=[it for it in source_items if it['source'].get('footnote_label')]
    note_targets={it['id'] for it in notes};links=[(it,r) for it in source_items for r in it['source'].get('inline_runs',[]) if r.get('target') in note_targets]
    if links:
     it,r=links[0];page.locator('[data-ann-id="'+it['id']+'-en"] a[href="#'+r['target']+'"]').first.click();ok(page.evaluate('(id)=>Math.abs(document.getElementById(id).getBoundingClientRect().top)<250',r['target']),'原文注号实际跳到对应注释')
   page.locator('[data-route=quick]').click();ok(page.locator('#story-overview').is_visible() and not page.locator('.guide-deep').is_visible(),'3分钟完整短叙事路线')
   page.evaluate("document.querySelector('#story-overview').scrollIntoView({block:'start'})");page.screenshot(path=str(folder/'overview.png'))
   page.locator('[data-route=deep]').click();ok(page.locator('.guide-deep').is_visible(),'10分钟展开路线')
   guides=page.locator('#mode-guide [data-mechanism]');ok(guides.count()==sum(len(c.get('motions',[])) for c in guide['story']['walkthrough']) and guides.count()>0,'导读解释下直接有计划内演示')
   for i in range(guides.count()):
    m=guides.nth(i);m.scroll_into_view_if_needed();scrub=m.locator('[data-scrub]')
    pixels=[]
    for value,label in [('0','first'),('500','middle'),('1000','last')]:
     scrub.fill(value);pixels.append(page.evaluate('(id)=>document.getElementById(id).querySelector("canvas").toDataURL()',m.get_attribute('id')))
     m.locator('canvas').screenshot(path=str(output/f'{folder.name}-motion{i+1}-{label}.png'))
    ok(len(set(pixels))==3,f'演示{i+1}首中末画面不同')
    scrub.fill('350');m.locator('[data-next]').click();ok(float(m.get_attribute('data-progress'))>.35,f'演示{i+1}分步前进')
    m.locator('[data-prev]').click();ok(float(m.get_attribute('data-progress'))<.667,f'演示{i+1}分步后退')
    m.locator('[data-speed]').select_option('2');ok(m.locator('[data-speed]').input_value()=='2',f'演示{i+1}倍速')
    m.locator('[data-play]').click();page.wait_for_timeout(170);ok(m.get_attribute('data-playing')=='true',f'演示{i+1}实际播放');m.locator('[data-play]').click();ok(m.get_attribute('data-playing')=='false',f'演示{i+1}暂停')
    m.locator('[data-reset]').click();ok(float(m.get_attribute('data-progress'))==0,f'演示{i+1}重置')
   guides.first.locator('[data-scrub]').fill('600');ok(page.locator('#mode-full [data-mechanism]').first.get_attribute('data-progress')=='0.0000','导读与全文实例状态独立')
   guides.first.scroll_into_view_if_needed();guides.first.locator('[data-play]').click();page.locator('[data-route=full]').click();ok(guides.first.get_attribute('data-playing')=='false','切路线停止隐藏播放器')
   page.locator('[data-route=deep]').click();first=page.locator('#mode-guide .concept-card').first;first.scroll_into_view_if_needed();ok(first.is_visible(),'概念卡在对应讲解原地展开')
   page.locator('#mode-guide .story-refs a').first.click();ok(page.locator('#mode-full').is_visible(),'导读证据跳回原段')
   def select():
    page.evaluate('''()=>{const el=[...document.querySelectorAll('.pcard .orig')].find(e=>e.getBoundingClientRect().height>0);el.scrollIntoView({block:'center'});const w=document.createTreeWalker(el,NodeFilter.SHOW_TEXT);let n;while(n=w.nextNode())if(n.length>30){let r=document.createRange();r.setStart(n,0);r.setEnd(n,25);getSelection().removeAllRanges();getSelection().addRange(r);el.dispatchEvent(new MouseEvent('mouseup',{bubbles:true}));break;}}''');page.wait_for_timeout(80)
   select();ok(page.locator('#annbar').is_visible(),'选中文字出现工具条');page.locator('#annbar [data-h]').click();ok(page.locator('mark[data-ann]').count()>0,'高亮覆盖原文')
   select();page.locator('#annbar [data-n]').click();page.locator('#annedit textarea').fill('浏览器验收：原文与解释对照');page.locator('#annedit [data-save]').click();ok(page.locator('#annbtn').get_attribute('data-count')=='2','保存批注并更新角标')
   page.locator('#annbtn').click()
   with page.expect_download() as download:page.locator('#annpanel [data-json]').click()
   backup=work/(folder.name+'-backup.json');download.value.save_as(str(backup));payload=json.loads(backup.read_text(encoding='utf-8'));ok(len(payload['items'])==2,'导出JSON含完整批注')
   page.locator('#annpanel [data-close]').click()
   key='close-read:v2:'+payload['paperId']+':annotations';page.evaluate('(key)=>localStorage.removeItem(key)',key);page.reload();ok(page.locator('#annbtn').get_attribute('data-count')=='0','清除后无残留高亮')
   page.locator('#annbtn').click();page.locator('#annpanel input[type=file]').set_input_files(str(backup));page.wait_for_timeout(100);ok(page.locator('#annbtn').get_attribute('data-count')=='2','导入恢复高亮与批注')
   wrong=dict(payload,paperId='unrelated-paper');wrongpath=work/(folder.name+'-wrong.json');wrongpath.write_text(json.dumps(wrong),encoding='utf-8');page.locator('#annpanel input[type=file]').set_input_files(str(wrongpath));page.wait_for_timeout(100);ok('失败' in page.locator('.import-status').inner_text(),'拒绝其他论文批注')
   page.locator('#annpanel [data-close]').click()
   for route in ['quick','deep','full']:
    page.locator('[data-route='+route+']').click();page.evaluate('window.scrollTo(0,1000)');page.wait_for_timeout(100);page.locator('#back-to-top').click();page.wait_for_function('scrollY===0');ok(True,route+'路线回到顶部')
   page.set_viewport_size({'width':390,'height':844});page.locator('[data-route=deep]').click();page.locator('#mode-guide [data-mechanism]').first.scroll_into_view_if_needed();ok(page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'390px导读无整页横溢');page.screenshot(path=str(folder/'mobile.png'))
   page.locator('[data-route=full]').click();select();bar=page.locator('#annbar').bounding_box();up=page.locator('#back-to-top').bounding_box();ok(bar['x']+bar['width']<up['x'],'手机选区工具不遮挡回顶')
   page.locator('#annbar [data-x]').click();page.emulate_media(reduced_motion='reduce');page.locator('#back-to-top').click();ok(page.evaluate('scrollY')==0,'减少动态效果直接回顶')
   page.set_viewport_size({'width':1500,'height':1050});page.locator('[data-route=deep]').click();m=page.locator('#mode-guide [data-mechanism]').first;m.scroll_into_view_if_needed();m.locator('[data-scrub]').fill('750');page.screenshot(path=str(folder/'walkthrough.png'))
   page.locator('[data-route=full]').click();card=page.locator('.pcard').nth(2);card.scroll_into_view_if_needed();page.screenshot(path=str(folder/'close-reading.png'))
   ok(not errors,'控制台无运行错误');ok(not network,'离线打开无外部请求');context.close()
   context=pw.chromium.launch_persistent_context(str(work/(folder.name+'-profile')),executable_path=executable,headless=headless,viewport={'width':1500,'height':1050},offline=True)
   page=context.pages[0];page.goto(html.as_uri());ok(page.locator('#annbtn').get_attribute('data-count')=='2','重开浏览器进程后批注恢复');ok(page.locator('mark[data-ann]').count()>0,'重开后高亮覆盖真实文字');context.close()
   reports.append({'browser':'Chromium/Chrome headed' if not headless else 'Chromium headless','folder':folder.name,'html_sha256':hashlib.sha256(html.read_bytes()).hexdigest(),'passed':len(checks),'checks':checks,'errors':errors,'external_requests':network})
   print(folder.name,len(checks),'checks passed',flush=True)
 (output/'browser-results.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8')
 return reports
def check_overviews(folders,work,output,executable=None,headless=False):
 """Check the six-step overview without repeating unrelated annotation scenarios."""
 from playwright.sync_api import sync_playwright
 from render_story import RESEARCH_STEPS
 work=Path(work).resolve()/('overview-'+uuid.uuid4().hex[:10]);work.mkdir(parents=True);output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True);reports=[]
 with sync_playwright() as pw:
  for folder in folders:
   folder=Path(folder).resolve();checks=[];errors=[];network=[];g=json.loads((folder/'reading-data/guide.json').read_text(encoding='utf-8'));q=g['story']['overview']
   def ok(value,label):
    if not value:raise AssertionError(str(folder)+': '+label)
    checks.append(label)
   ctx=pw.chromium.launch_persistent_context(str(work/folder.name),executable_path=executable,headless=headless,viewport={'width':1500,'height':1050},offline=True)
   page=ctx.pages[0];page.on('pageerror',lambda x:errors.append(str(x)));page.on('request',lambda x:network.append(x.url) if x.url.startswith(('http:','https:')) else None);page.goto((folder/'reader.html').as_uri());page.locator('[data-route=quick]').click()
   overview=page.locator('#story-overview');ok(overview.is_visible(),'三分钟六步总览可见')
   ok(overview.locator('.research-step').count()==6,'六个研究环节全部呈现')
   ok(overview.locator('.research-num').all_text_contents()==['01','02','03','04','05','06'],'六步阅读顺序明确')
   ok(overview.locator('.research-route span').all_text_contents()==[x[1] for x in RESEARCH_STEPS],'背景到结论的完整路线')
   ok(overview.locator('details').count()==0,'入门无需展开即可看全')
   ok(overview.locator('.story-chain').count()==0,'不重复旧叙述与旧流程卡')
   text=q['title']+q['lead']+q['takeaway']+''.join(x['text'] for x in q['research_map']);ok(len(text)<=650,'主要内容控制在650字符内')
   ok(page.evaluate("getComputedStyle(document.documentElement).fontSize==='18px'"),'18px默认字号')
   ok(overview.locator('.research-step p').all_text_contents()==[x['text'] for x in q['research_map']],'六步文字与保存资料一致')
   ok(page.evaluate("getComputedStyle(document.querySelector('.research-map')).gridTemplateColumns.split(' ').length===3"),'桌面三列按序阅读')
   overview.screenshot(path=str(folder/'overview-map.png'));page.locator('[data-route=quick]').click();page.screenshot(path=str(folder/'overview.png'))
   for i,step in enumerate(q['research_map']):
    page.locator('#story-overview .research-sources a').nth(i).click();ok(page.locator('#mode-full').is_visible() and page.locator('#'+step['refs'][0]).is_visible(),step['step']+'可实际跳回对应原段');page.locator('[data-route=quick]').click()
   page.locator('[data-route=deep]').click();ok(page.locator('.guide-deep').is_visible(),'十分钟仍能正常展开')
   ok(page.locator('#mode-guide [data-mechanism]').count()==sum(len(x.get('motions',[])) for x in g['story']['walkthrough']),'十分钟原地演示保留')
   page.locator('[data-route=full]').click();ok(page.evaluate("[...document.querySelectorAll('.bilingual,.logic')].every(x=>x.open)"),'全文与逻辑仍默认展开')
   page.set_viewport_size({'width':390,'height':844});page.locator('[data-route=quick]').click();ok(page.evaluate("(()=>{const h=document.querySelector('#story-overview h2').getBoundingClientRect(),t=document.querySelector('.toolbar').getBoundingClientRect();return h.top>=t.bottom&&h.bottom<innerHeight;})()"),'手机切入门后标题完整可见')
   ok(page.evaluate('document.documentElement.scrollWidth<=innerWidth'),'390px入门无整页横溢')
   ok(page.evaluate("getComputedStyle(document.querySelector('.research-map')).gridTemplateColumns.split(' ').length===1"),'手机六步单列顺序阅读')
   ok(overview.locator('.research-step').evaluate_all('(xs)=>xs.every((x,i)=>!i||x.getBoundingClientRect().top>xs[i-1].getBoundingClientRect().top)'),'手机视觉顺序与研究顺序一致')
   page.screenshot(path=str(output/(folder.name+'-mobile.png')));page.evaluate('scrollTo(0,0)');page.screenshot(path=str(folder/'mobile-overview.png'),full_page=True)
   page.evaluate('window.scrollTo(0,800)');page.locator('#back-to-top').click();page.wait_for_function('scrollY===0');ok(True,'三分钟回到顶部')
   ok(not errors,'无运行错误');ok(not network,'离线无外部请求');ctx.close()
   reports.append({'folder':folder.name,'browser':'Chrome headed' if not headless else 'Chromium headless','html_sha256':hashlib.sha256((folder/'reader.html').read_bytes()).hexdigest(),'overview_characters':len(text),'passed':len(checks),'checks':checks,'errors':errors,'external_requests':network});print(folder.name,len(checks),'overview checks passed',flush=True)
 (output/'browser-results.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2),encoding='utf-8');return reports

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('folders',nargs='+',type=Path);p.add_argument('--work-dir',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--browser-executable');p.add_argument('--headless',action='store_true');p.add_argument('--overview-only',action='store_true');a=p.parse_args();
 if a.overview_only:
  sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'skills/paper-close-read/scripts'))
  check_overviews(a.folders,a.work_dir,a.output,a.browser_executable,a.headless)
 else:run(a.folders,a.work_dir,a.output,a.browser_executable,a.headless)
