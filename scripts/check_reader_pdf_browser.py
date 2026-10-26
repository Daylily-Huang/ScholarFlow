"""Exercise PDF layout, vocabulary and reading-state restoration in a real browser."""
import argparse,base64,hashlib,json,os
from pathlib import Path
from playwright.sync_api import sync_playwright
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('folders',nargs='+',type=Path)
parser.add_argument('--work-dir',type=Path,required=True)
parser.add_argument('--output',type=Path,required=True)
parser.add_argument('--browser-executable',required=True)
args=parser.parse_args()
args.work_dir.mkdir(parents=True,exist_ok=True)
for variable in ('TMPDIR','TEMP','TMP'):os.environ[variable]=str(args.work_dir.resolve())
out=args.output.resolve();out.mkdir(parents=True,exist_ok=True)
reports=[]
with sync_playwright() as pw:
    browser=pw.chromium.launch(executable_path=args.browser_executable,headless=True)
    for folder in args.folders:
        folder=folder.resolve();name=folder.name
        context=browser.new_context(offline=True,viewport={'width':1500,'height':1050})
        page=context.new_page();errors=[];page.on('pageerror',lambda error:errors.append(str(error)))
        file=folder/'reader.html';page.goto(file.as_uri())
        page.wait_for_function('!!window.readerPDF')
        count=page.locator('.pcard').count()
        assert page.locator('.pcard .paragraph-vocabulary').count()==count
        assert page.evaluate('[...document.querySelectorAll(".bilingual,.logic")].every(x=>x.open)')
        page.locator('.paragraph-vocabulary').first.scroll_into_view_if_needed();page.screenshot(path=str(out/(name+'-vocabulary.png')))
        page.locator('#export-pdf').click();assert page.locator('.pdf-dialog').is_visible()
        page.screenshot(path=str(out/(name+'-pdf-dialog.png')))
        page.locator('.pdf-dialog button[value=cancel]').click();assert not page.locator('.pdf-dialog').is_visible()
        assert page.evaluate('!document.body.classList.contains("reader-pdf-export")')
        page.locator('[data-route=deep]').click()
        source_data=json.loads((folder/'reading-data/fulltext.json').read_text(encoding='utf-8-sig'))
        guide_data=json.loads((folder/'reading-data/guide.json').read_text(encoding='utf-8-sig'))
        for section in source_data['sections']:
            for item in section['items']:
                if item['t']!='figure':continue
                image=page.locator('#'+item['id']+' img')
                encoded=image.get_attribute('src').split(',',1)[1]
                assert hashlib.sha256(base64.b64decode(encoded)).digest()==hashlib.sha256((folder/'reading-data'/item['src']).read_bytes()).digest()
                assert image.evaluate('(x)=>x.complete && x.naturalWidth>0 && x.naturalHeight>0')
        planned=sum(len(c.get('figures',[])) for c in guide_data['story']['walkthrough'])
        figures=page.locator('#mode-guide .guide-source-figure')
        assert figures.count()==planned
        for i in range(figures.count()):
            figure=figures.nth(i);ref=figure.get_attribute('data-source-figure')
            assert figure.locator('img').get_attribute('src')==page.locator('#'+ref+' img').get_attribute('src')
            assert figure.locator('.original-caption').inner_text().strip()
            assert figure.locator('.figure-focus').is_visible()
            figure.locator('.figure-trigger').click();assert page.locator('#figure-viewer').is_visible()
            assert page.locator('#figure-viewer img').get_attribute('src')==figure.locator('img').get_attribute('src')
            page.locator('#figure-viewer [data-close]').click()
        for chapter_index,chapter in enumerate(guide_data['story']['walkthrough'],1):
            for f,reference in enumerate(chapter.get('figures',[])):
                assert page.evaluate('(v)=>{const figure=document.getElementById(v[0]),para=document.getElementById(v[1]);let x=figure.previousElementSibling;while(x?.matches(".guide-source-figure"))x=x.previousElementSibling;return x===para}',[f'guide-figure-{chapter_index}-{f}',f'guide-chapter-{chapter_index}-p-{reference["after"]}'])
        pdf_viewer_checked=False
        if source_data.get('source_pdf'):
            page.locator('[data-route=full]').click()
            exact=page.locator('#mode-full [data-open-pdf-page][data-pdf-located=true]').first
            target_page=exact.get_attribute('data-open-pdf-page');exact.click()
            viewer=page.locator('#source-pdf-viewer');assert viewer.is_visible()
            assert viewer.locator('[data-page-select]').input_value()==target_page
            page.wait_for_function('document.querySelector("#source-pdf-viewer img").complete && document.querySelector("#source-pdf-viewer img").naturalWidth>0')
            expected_page=next(p for p in source_data['source_pdf']['pages'] if p['page']==int(target_page))
            encoded=viewer.locator('img').get_attribute('src').split(',',1)[1]
            assert hashlib.sha256(base64.b64decode(encoded)).hexdigest()==expected_page['sha256']
            assert viewer.locator('img').evaluate('(x)=>x.complete&&x.naturalWidth>0')
            before=viewer.bounding_box();bar=viewer.locator('.viewer-titlebar').bounding_box()
            page.mouse.move(bar['x']+100,bar['y']+18);page.mouse.down();page.mouse.move(bar['x']+165,bar['y']+48,steps=6);page.mouse.up()
            moved=viewer.bounding_box();assert moved['x']>before['x']+40 and moved['y']>before['y']+15
            handle=viewer.locator('.viewer-resize-handle').bounding_box()
            page.mouse.move(handle['x']+10,handle['y']+10);page.mouse.down();page.mouse.move(handle['x']-70,handle['y']-60,steps=6);page.mouse.up()
            resized=viewer.bounding_box();assert resized['width']<moved['width']-40 and resized['height']<moved['height']-35
            viewer.locator('[data-page-zoom]').select_option('150')
            assert viewer.locator('img').evaluate('(x)=>x.style.width')=='150%'
            viewer.locator('[data-page-select]').select_option(str(source_data['source_pdf']['pages'][-1]['page']))
            assert viewer.locator('img').get_attribute('alt').endswith(str(source_data['source_pdf']['pages'][-1]['page'])+' 页')
            viewer.locator('[data-window-max]').click();assert viewer.bounding_box()['width']>resized['width']
            viewer.locator('[data-window-max]').click();assert abs(viewer.bounding_box()['width']-resized['width'])<2
            viewer.locator('[data-page-zoom]').select_option('fit')
            viewer.locator('[data-page-select]').select_option(target_page)
            page.screenshot(path=str(out/(name+'-pdf-page-window.png')))
            page.keyboard.press('Escape');assert not viewer.is_visible()
            unknown=page.locator('#mode-full [data-open-pdf-page][data-pdf-located=false]')
            if unknown.count():unknown.first.click();assert '未核实' in viewer.locator('.pdf-page-location').inner_text();viewer.locator('[data-window-close]').click()
            pdf_viewer_checked=True
            page.locator('[data-route=deep]').click()
        motions=page.locator('#mode-guide [data-mechanism]')
        assert motions.count()>0
        motion=motions.first;motion.scroll_into_view_if_needed();motion.locator('[data-scrub]').fill('700')
        frame=page.evaluate('(id)=>document.getElementById(id).querySelector("canvas").toDataURL()',motion.get_attribute('id'))
        motion.locator('[data-scrub]').fill('200')
        assert frame!=page.evaluate('(id)=>document.getElementById(id).querySelector("canvas").toDataURL()',motion.get_attribute('id'))
        # Export every paragraph even when a query and a different route hide originals.
        page.locator('[data-route=full]').click();page.locator('#search').fill('NO_MATCH_73910')
        before=page.evaluate('JSON.stringify(window.reader.getState())')
        details=page.evaluate('window.readerPDF.prepare({notes:true})')
        assert details['paragraphs']==count
        assert page.locator('#reader-pdf-document .pdf-pair').count()==count
        assert page.locator('#reader-pdf-document .paragraph-vocabulary').count()==count
        assert page.locator('#reader-pdf-document img').count()==page.locator('#mode-full > .fsect > .source-block img').count()
        assert page.locator('#reader-pdf-document .source-block table').count()==page.locator('#mode-full > .fsect > .source-block table').count()
        assert page.evaluate('[...document.querySelectorAll("[id]")].length===new Set([...document.querySelectorAll("[id]")].map(x=>x.id)).size')
        page.emulate_media(media='print');assert page.locator('#reader-pdf-document').is_visible()
        assert not page.locator('#mode-full').is_visible()
        page.evaluate('window.readerPDF.restore()');page.emulate_media(media='screen')
        assert before==page.evaluate('JSON.stringify(window.reader.getState())')
        plain=page.evaluate('window.readerPDF.prepare({notes:false,paper:"portrait"})')
        assert page.locator('#reader-pdf-document .note').count()==0
        assert page.locator('#reader-pdf-document .paragraph-vocabulary').count()==count
        page.evaluate('window.readerPDF.restore()');page.locator('#search').fill('')
        # Exercise real dialog handler while replacing only the OS print dialog.
        page.evaluate('window.print=()=>{window.__printCalled=!!document.querySelector("#reader-pdf-document");dispatchEvent(new Event("beforeprint"));dispatchEvent(new Event("afterprint"));}')
        page.locator('#export-pdf').click();page.locator('#pdf-print').click();page.wait_for_timeout(150)
        assert page.evaluate('window.__printCalled && !document.getElementById("reader-pdf-document")')
        assert page.locator('#mode-full').is_visible()
        assert not errors,errors
        # Mobile is an emulated layout check, not a device test.
        page.set_viewport_size({'width':390,'height':844});page.locator('.paragraph-vocabulary').first.scroll_into_view_if_needed()
        assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
        if pdf_viewer_checked:
            page.locator('.toolbar [data-open-pdf-page]').click()
            mobile_viewer=page.locator('#source-pdf-viewer');bounds=mobile_viewer.bounding_box()
            assert bounds['x']>=0 and bounds['x']+bounds['width']<=391
            assert bounds['y']>=0 and bounds['y']+bounds['height']<=845
            page.screenshot(path=str(out/(name+'-pdf-page-mobile.png')))
            mobile_viewer.locator('[data-window-close]').click()
        if planned:
            page.locator('[data-route=deep]').click();figures.first.scroll_into_view_if_needed()
            assert page.evaluate('document.documentElement.scrollWidth<=innerWidth+1')
            page.screenshot(path=str(out/(name+'-figure-mobile.png')))
            page.set_viewport_size({'width':1500,'height':1050});figures.first.evaluate('(x)=>x.scrollIntoView({block:"start"})');page.evaluate('scrollBy(0,-document.querySelector(".toolbar").getBoundingClientRect().height-12)');page.screenshot(path=str(out/(name+'-figure.png')))
        page.screenshot(path=str(out/(name+'-mobile.png')))
        reports.append({'paper':name,'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'paragraphs':count,'pdf_fulltext_despite_search':True,'print_options_and_restore':True,'motion_changed':True,'guide_original_figures':planned,'original_images_match':True,'figure_zoom_and_placement':True,'source_pdf_drag_resize_zoom':pdf_viewer_checked,'mobile_390px':True,'page_errors':errors})
        context.close()
    browser.close()
(out/'browser-checks.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(reports,ensure_ascii=False,indent=2))
