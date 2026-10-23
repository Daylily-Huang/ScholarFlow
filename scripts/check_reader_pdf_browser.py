"""Exercise PDF layout, vocabulary and reading-state restoration in a real browser."""
import argparse,hashlib,json,os
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
        page.screenshot(path=str(out/(name+'-mobile.png')))
        reports.append({'paper':name,'sha256':hashlib.sha256(file.read_bytes()).hexdigest(),'paragraphs':count,'pdf_fulltext_despite_search':True,'print_options_and_restore':True,'motion_changed':True,'mobile_390px':True,'page_errors':errors})
        context.close()
    browser.close()
(out/'browser-checks.json').write_text(json.dumps(reports,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
print(json.dumps(reports,ensure_ascii=False,indent=2))
