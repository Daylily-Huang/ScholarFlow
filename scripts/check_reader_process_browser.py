"""Exercise topic-independent object/keyframe scenes in a real offline browser."""
import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT/'skills/paper-close-read/scripts'))


def make_reader(work):
    from parse_mineru import parse_document
    from build_html import build, atomic_write
    source = '# Teaching fixture\n\nA particle moves through a recording boundary.\n\nA message travels from a speaker to a listener.\n'
    data = parse_document(source, 'source.md', 'teaching-process-fixture')
    data['front']['title'] = '声明式过程演示回归样例'
    blocks = [i for s in data['sections'] for i in s['items'] if i['t'] == 'p']
    refs = [i['id'] for i in blocks]
    records = [dict(id=i['id'], zh='教学样例，不是论文结果。', note='观察具体对象的变化，再解释记录或信息的区别。', keys=['先保持对象相同，再改变位置。']) for i in blocks]
    scenes = []
    for n, ref in enumerate(refs):
        scenes.append(dict(id='motion-demo-'+str(n), scene='process', title=['对象移动与记录', '信息到达与听者'][n],
            question='变化的是哪一个对象？', anchor=ref, refs=[ref], stages=['起点', '中间', '终点'], note='自编教学样例',
            visual=dict(description='固定条件，观察同一对象从左到右移动。数值只定义教学画面。', elements=[
                dict(id='field', type='rect', meaning='区域', props=dict(x=60,y=90,w=350,h=230,fill='#edf3ed',stroke='#52836b')),
                dict(id='object', type='circle' if n==0 else 'rect', meaning='粒子或信息对象',
                     props=dict(x=100,y=200,r=12,w=20,h=20,fill='#568ba1',stroke='none'),
                     frames=[dict(at=0.5,x=350),dict(at=1,x=650)]),
                dict(id='curve', type='polyline', meaning='随条件变化的示意曲线',
                     props=dict(points=[[100,330],[400,300],[700,250]],stroke='#cf5267'),
                     frames=[dict(at=1,points=[[100,350],[400,220],[700,100]])]),
                dict(id='label',type='text',meaning='状态标签',props=dict(x=480,y=100,text='教学：起点',font_size=22),
                     frames=[dict(at=0.5,text='教学：中间'),dict(at=1,text='教学：终点')])])) )
    overview=dict(title='看得见对象变化，才知道解释跨了哪一步',lead='回归测试用自编材料，检查通用关键帧绘制。',format='research-map',
                  research_map=[dict(step=s,text='此处为教学回归样例。',refs=[refs[0]]) for s in ['background','gap','question','method','findings','conclusion']],
                  takeaway='两种题材使用同一个声明式引擎。',refs=[refs[0]])
    guide=dict(story=dict(overview=overview,walkthrough=[dict(title='同一对象如何改变结果',bridge='先认出对象。',paragraphs=['观察位置改变，检查两种题材都能绘制。'],connection='回到原文对象。',refs=refs,motions=[dict(id=s['id']) for s in scenes])]),
               mechanisms=scenes,visual_plan=[dict(id='vp-'+str(n),question=s['question'],mode='motion',kind='mechanism',mechanism=s['id'],refs=s['refs'],reason='需显示对象位置变化。',observe='起点、中间和终点的对象位置。') for n,s in enumerate(scenes)])
    html, _ = build(data, records, guide, work, source, require_visual_plan=True)
    path = work/'reader.html'; atomic_write(path, html)
    return path


def check_browser(args):
    from playwright.sync_api import sync_playwright
    work = args.work_dir.resolve(); work.mkdir(parents=True, exist_ok=True)
    path = make_reader(work)
    checks, errors, external = [], [], []
    def check(value, label):
        if not value: raise AssertionError(label)
        checks.append(label)
    with sync_playwright() as p:
        options = dict(headless=True, env={**os.environ,'TEMP':str(work),'TMP':str(work)})
        if args.browser_executable: options['executable_path'] = args.browser_executable
        b = p.chromium.launch(**options)
        c = b.new_context(viewport=dict(width=1440,height=1000)); page = c.new_page()
        page.on('pageerror',lambda e:errors.append(str(e)))
        page.on('request',lambda r:external.append(r.url) if r.url.startswith(('https://','http://')) else None)
        page.goto(path.as_uri()); page.wait_for_function('window.reader && window.__ann')
        page.locator('[data-route=deep]').click()
        motions = page.locator('#mode-guide .mechanism')
        check(motions.count()==2,'two topics use the same process renderer')
        for n in range(2):
            m=motions.nth(n);m.scroll_into_view_if_needed();frames=[]
            for v in [0,500,1000]:
                m.locator('[data-scrub]').evaluate('(e,v)=>{e.value=v;e.dispatchEvent(new Event("input",{bubbles:true}))}',v)
                frames.append(m.locator('canvas').evaluate('(c)=>c.toDataURL()'))
            check(len(set(frames))==3,'topic '+str(n)+' changes actual object geometry')
            # Inspect the rendered object at its expected final coordinate, not just a changed label.
            pixel=m.locator('canvas').evaluate('(c)=>{const q=c.width/900;return [...c.getContext("2d").getImageData(Math.round(655*q),Math.round(205*q),1,1).data]}')
            check(pixel[2]>pixel[0] and pixel[3]>200,'topic '+str(n)+' object arrives at final location')
            check(page.locator('#mode-guide').is_visible(),'scrubbing stays in walkthrough')
            m.locator('[data-reset]').click();m.locator('[data-play]').click();page.wait_for_timeout(80)
            check(m.get_attribute('data-playing')=='true','topic '+str(n)+' plays')
            page.locator('[data-route=full]').click()
            check(m.get_attribute('data-playing')!='true','topic '+str(n)+' pauses when route hides')
            original=page.locator('#mode-full .mechanism').nth(n)
            check(original.get_attribute('data-progress')=='0.0000','original and guide player states independent')
            page.locator('[data-route=deep]').click()
        page.set_viewport_size(dict(width=390,height=844))
        check(page.evaluate('document.documentElement.scrollWidth<=innerWidth+1'),'390px viewport has no page overflow')
        check(not external,'no external runtime resources')
        check(not errors,'no JavaScript runtime errors')
        b.close()
    result=dict(passed=len(checks),checks=checks,errors=errors,external_requests=external)
    (work/'browser-checks.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    return result


if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--work-dir',type=Path,required=True);ap.add_argument('--browser-executable')
    print(json.dumps(check_browser(ap.parse_args()),ensure_ascii=False,indent=2))
