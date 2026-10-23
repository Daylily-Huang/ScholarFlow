"""Exercise reader persistence/backup user journeys in an actual offline browser."""
import argparse,hashlib,json,uuid
from pathlib import Path


def run(folder,work,output,executable,headless=False,engine="chromium"):
 from playwright.sync_api import sync_playwright
 folder=Path(folder).resolve();work=Path(work).resolve()/('workspace-'+uuid.uuid4().hex[:10]);work.mkdir(parents=True)
 output=Path(output).resolve();output.mkdir(parents=True,exist_ok=True)
 html=folder/'reader.html';guide=json.loads((folder/'reading-data/fulltext.json').read_text(encoding='utf-8-sig'));paper=guide['paper_id'];checks=[];errors=[];network=[]
 def ok(v,label):
  if not v:raise AssertionError(label)
  checks.append(label)
 with sync_playwright() as pw:
  def launch(name,init=None):
   c=getattr(pw,engine).launch_persistent_context(str(work/name),executable_path=executable,headless=headless,viewport={'width':1440,'height':1000},offline=True,accept_downloads=True)
   if init:c.add_init_script(init)
   pg=c.pages[0];pg.on('pageerror',lambda e:errors.append(str(e)));pg.on('request',lambda req:network.append(req.url) if req.url.startswith(('https:','http:')) else None);pg.goto(html.as_uri());return c,pg
  def select(pg,selector='.pcard .orig'):
   pg.evaluate('''(selector)=>{const c=[...document.querySelectorAll(selector)].find(c=>c.textContent.length>40);c.scrollIntoView({block:'center'});const w=document.createTreeWalker(c,NodeFilter.SHOW_TEXT);let n;while(n=w.nextNode())if(n.length>40){const r=document.createRange();r.setStart(n,0);r.setEnd(n,25);getSelection().removeAllRanges();getSelection().addRange(r);break;}}''',selector);pg.wait_for_timeout(180)
   ok(pg.locator('#annbar').is_visible(),'仅selectionchange也能呈现选区工具')
  def download(pg,selector,name):
   with pg.expect_download() as d:pg.locator(selector).click()
   target=work/name;d.value.save_as(str(target));return target
  c,pg=launch('normal');ok(pg.locator('#mode-full').is_visible(),'默认逐段精读保留')
  target=pg.evaluate('''()=>{const c=[...document.querySelectorAll('.pcard')].sort((a,b)=>b.getBoundingClientRect().height-a.getBoundingClientRect().height)[0];const r=c.getBoundingClientRect(),h=document.querySelector('.toolbar').getBoundingClientRect().height;scrollTo(0,scrollY+r.top+r.height*.43-h-20);return c.id}''');pg.wait_for_timeout(700)
  saved=pg.evaluate('reader.getState().positions.full');ok(saved['id']==target and .35<saved['ratio']<.55,'长段中途真实滚动位置已记录')
  c.close();c,pg=launch('normal');pg.locator('#resume').click();pg.wait_for_timeout(100)
  ratio=pg.evaluate('(id)=>{const r=document.getElementById(id).getBoundingClientRect();return ((document.querySelector(".toolbar").getBoundingClientRect().height+20)-r.top)/r.height}',target)
  ok(abs(ratio-saved['ratio'])<.04,'重开浏览器后恢复同一长段中途')
  pg.locator('#font-size').select_option('20');pg.locator('#resume').click();pg.wait_for_timeout(100)
  ratio=pg.evaluate('(id)=>{const r=document.getElementById(id).getBoundingClientRect();return ((document.querySelector(".toolbar").getBoundingClientRect().height+20)-r.top)/r.height}',target)
  ok(abs(ratio-saved['ratio'])<.04,'改变字号后按段内比例恢复')
  pg.locator('[data-read]').first.click();read_id=pg.locator('[data-read]').first.get_attribute('data-read')
  has_recall=bool(pg.locator('[data-recall]').count())
  if has_recall:
   pg.locator('[data-route=deep]').click();pg.locator('[data-recall]').first.fill('复述：显性表型改变不意味着A频率增多');pg.reload();pg.locator('[data-route=deep]').click();ok(pg.locator('[data-recall]').first.input_value().startswith('复述：'),'叙事导读可选复述能填写并刷新恢复');pg.locator('[data-route=full]').click()
  select(pg);pg.locator('#annbar [data-h]').click();select(pg);pg.locator('#annbar [data-n]').click();pg.locator('#annedit textarea').fill('Evidence note 中文');pg.locator('#annedit [data-save]').click()
  ok(pg.locator('#annbtn').get_attribute('data-count')=='2','高亮与文字批注保留')
  pg.locator('#annbtn').click();pg.locator('.ann-item').first.get_by_role('button',name='删除',exact=True).click();ok(pg.locator('#annbtn').get_attribute('data-count')=='1','批注可删除')
  pg.locator('#annpanel [data-undo]').click();ok(pg.locator('#annbtn').get_attribute('data-count')=='2','误删立即撤销恢复')
  pg.locator('[data-ann-search]').fill('Evidence note');ok(pg.locator('.ann-item').count()==1,'按笔记搜索批注')
  pg.locator('#annpanel [data-close]').click();pg.locator('#reader-tools').click();pg.locator('#document-note').fill('整篇思考：这些证据怎样接起来？');pg.wait_for_timeout(600)
  backup=download(pg,'#reader-workspace [data-backup]','full-backup.json');payload=json.loads(backup.read_text(encoding='utf-8'))
  ok(payload['schema']==3 and payload['reading']['documentNote'].startswith('整篇思考') and read_id in payload['reading']['read'] and len(payload['annotations'])==2 and payload['reading']['positions'].get('full'),'完整备份包含笔记/已读/位置/批注')
  if has_recall:ok(payload['reading']['recall']['0'].startswith('复述：'),'完整备份保留真实填写的复述')
  md=download(pg,'#reader-workspace [data-markdown]','reading.md').read_text(encoding='utf-8');ok('整篇思考' in md and paper in md and '来源：' in md and 'Evidence note' in md,'Markdown带论文、笔记及引句来源')
  standard=json.loads(download(pg,'#reader-workspace [data-standard]','annotations.jsonld').read_text(encoding='utf-8'));ok(standard['type']=='AnnotationPage' and standard['items'][0]['target']['selector']['refinedBy']['exact'] and pg.locator('[id="'+standard['items'][0]['target']['selector']['value']+'"]').count()==1 and standard['items'][0]['target'].get('renderedVia'),'标准导出保留引句和派生阅读页目标')
  pg.locator('#reader-workspace').screenshot(path=str(output/(folder.name+'-workspace.png')))
  pg.keyboard.press('Escape');ok(pg.evaluate('document.activeElement.id')=='reader-tools','原生对话框Esc关闭并返回触发控件')
  pg.keyboard.press('/');ok(pg.evaluate('document.activeElement.id')=='search','搜索快捷键可用');pg.keyboard.type('?');ok(not pg.locator('#reader-workspace').is_visible(),'输入框内不拦截问号快捷键');pg.locator('#search').fill('');pg.locator('#reader-tools').focus();pg.keyboard.press('?');ok(pg.locator('#reader-workspace').is_visible(),'问号可发现阅读工具');pg.keyboard.press('Escape')
  # Separate windows edit the same annotation before either has committed both changes.
  pg.locator('#annbtn').click();pg.locator('[data-ann-search]').fill('');pg.locator('.ann-item').first.get_by_role('button',name='编辑',exact=True).click();pg.locator('#annedit textarea').fill('窗口A的解释')
  other=c.new_page();other.goto(html.as_uri());other.locator('#annbtn').click();other.locator('.ann-item').first.get_by_role('button',name='编辑',exact=True).click();other.locator('#annedit textarea').fill('窗口B的解释')
  pg.locator('#annedit [data-save]').click();other.locator('#annedit [data-save]').click();notes=other.evaluate('__ann.items.map(a=>a.note)');ok('窗口A的解释' in notes and '窗口B的解释' in notes,'并发修改同条批注时保留两个版本');other.close();c.close()
  c,pg=launch('restored');pg.locator('#reader-tools').click();file=pg.locator('#reader-workspace input[type=file]');file.set_input_files(str(backup));pg.wait_for_timeout(200)
  state=pg.evaluate('reader.getState()');ok(state['documentNote']==payload['reading']['documentNote'] and read_id in state['read'] and len(pg.evaluate('__ann.items'))==2,'新浏览器导入完整备份恢复记录')
  file.set_input_files(str(backup));pg.wait_for_timeout(150);ok(len(pg.evaluate('__ann.items'))==2,'重复导入不增加重复批注')
  wrong=dict(payload,paperId='unrelated');wrongfile=work/'wrong.json';wrongfile.write_text(json.dumps(wrong),encoding='utf-8');file.set_input_files(str(wrongfile));pg.wait_for_timeout(150);ok('导入失败' in pg.locator('.workspace-import-status').inner_text() and len(pg.evaluate('__ann.items'))==2,'错论文拒收且不改变当前数据')
  bad=json.loads(json.dumps(payload));bad['annotations'][0]['end']=99999;bad['reading']['documentNote']='must not import';badfile=work/'bad.json';badfile.write_text(json.dumps(bad),encoding='utf-8');file.set_input_files(str(badfile));pg.wait_for_timeout(150);ok(pg.evaluate('reader.getState().documentNote')==payload['reading']['documentNote'],'损坏文件整包验证后拒绝，不产生半次导入')
  pg.set_viewport_size({'width':390,'height':844});ok(pg.evaluate('document.documentElement.scrollWidth<=innerWidth'),'390px阅读工具无整页横溢');pg.screenshot(path=str(output/(folder.name+'-mobile-workspace.png')));c.close()
  c,pg=launch('restored');ok(pg.evaluate('reader.getState().documentNote')==payload['reading']['documentNote'],'重开后不打开阅读工具也保留整篇笔记');c.close();c,pg=launch('restored');ok(pg.evaluate('reader.getState().documentNote')==payload['reading']['documentNote'],'关闭未打开的工具不会清空笔记');c.close()
  key='close-read:v2:'+paper;init='''(key)=>{}'''
  corrupt_script='''if(!localStorage.getItem('fixture-once')){localStorage.setItem('fixture-once','1');localStorage.setItem(KEY+':annotations','{broken annotations');localStorage.setItem(KEY+':reading','{broken reading');}'''.replace('KEY',json.dumps(key))
  c,pg=launch('corrupt',corrupt_script);ok(pg.evaluate('(k)=>localStorage.getItem(k+":annotations")',key)=='{broken annotations','加载损坏批注时未覆盖原始值');select(pg);pg.locator('#annbar [data-h]').click();pg.wait_for_timeout(600)
  recovered=pg.evaluate('(key)=>Object.keys(localStorage).filter(k=>k.startsWith(key+":annotations:recovery:")).map(k=>localStorage.getItem(k))',key);ok(recovered==['{broken annotations'],'首次保存前保留损坏原始副本')
  pg.locator('#reader-tools').click();ok(pg.locator('.workspace-recovery button').count()==2,'用户能导出损坏阅读记录和批注以恢复');c.close()
  c,pg=launch('guide-annotations')
  for route in ['quick','deep']:
   pg.locator('[data-route='+route+']').click();select(pg,'#mode-guide '+('#story-overview' if route=='quick' else '.guide-deep')+' [data-ann-id]');pg.locator('#annbar [data-h]').click()
  ok(len(pg.evaluate('__ann.items'))==2,'三分钟与十分钟的实际讲解均可高亮批注');c.close()
  c,pg=launch('quota-concurrency')
  pg.evaluate('''()=>{Storage.prototype.setItem=function(){throw new DOMException('full','QuotaExceededError')};}''')
  select(pg);pg.locator('#annbar [data-n]').click();pg.locator('#annedit textarea').fill('ONLY IN WINDOW A');pg.locator('#annedit [data-save]').click()
  ok(any(a['note']=='ONLY IN WINDOW A' for a in pg.evaluate('__ann.items')),'quota失败后本页保留未保存批注')
  seed=pg.evaluate('__ann.items[0]');seed.update(id='quota-remote-note',note='WINDOW B')
  second=c.new_page();second.goto(html.as_uri());second.evaluate('(a)=>__ann.importItems([a])',seed)
  pg.wait_for_function('__ann.items.some(a=>a.note==="WINDOW B")')
  ok(all(any(a['note']==note for a in pg.evaluate('__ann.items')) for note in ['ONLY IN WINDOW A','WINDOW B']),'远端刷新与quota组合不丢本页未保存批注')
  pg.locator('#reader-tools').click();quota=json.loads(download(pg,'#reader-workspace [data-backup]','quota-merged.json').read_text(encoding='utf-8'))
  ok({a['note'] for a in quota['annotations']}=={'ONLY IN WINDOW A','WINDOW B'},'quota并发后完整备份仍含两个窗口的内容');c.close()
  unavailable='''Storage.prototype.getItem=function(){throw new DOMException('blocked','SecurityError')};Storage.prototype.setItem=function(){throw new DOMException('blocked','SecurityError')};'''
  c,pg=launch('unavailable',unavailable);ok(pg.locator('#mode-full').is_visible(),'存储禁用仍正常显示论文');select(pg);pg.locator('#annbar [data-h]').click();pg.locator('#reader-tools').click();pg.locator('#document-note').fill('存储失败仍能带走');pg.wait_for_timeout(600)
  memory=json.loads(download(pg,'#reader-workspace [data-backup]','memory-backup.json').read_text(encoding='utf-8'));ok(len(memory['annotations'])==1 and memory['reading']['documentNote']=='存储失败仍能带走','禁用存储后批注和笔记仍可从内存完整导出');c.close()
 ok(not errors,'所有场景无浏览器运行错误');ok(not network,'所有场景离线不发外部请求')
 result={'folder':folder.name,'html_sha256':hashlib.sha256(html.read_bytes()).hexdigest(),'browser':engine+(' headed' if not headless else ' headless'),'passed':len(checks),'checks':checks,'errors':errors,'external_requests':network}
 (output/(folder.name+'-workspace-results.json')).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');print(folder.name,len(checks),'workspace checks passed',flush=True);return result

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('folder',type=Path);p.add_argument('--work-dir',required=True,type=Path);p.add_argument('--output',required=True,type=Path);p.add_argument('--browser-executable');p.add_argument('--browser',choices=['chromium','firefox','webkit'],default='chromium');p.add_argument('--headless',action='store_true');a=p.parse_args();run(a.folder,a.work_dir,a.output,a.browser_executable,a.headless,a.browser)
