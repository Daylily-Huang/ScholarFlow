"""Package only referenced source files and a minimal native runtime for relocation.

Local source handoff: includes referenced PDFs, not a licence/publication checker.
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
RUNTIME=['scripts/generate.py','scripts/fill_styles.py','scripts/evidence_layouts.py','scripts/content_audit.py',
         'scripts/compact_layouts.py','assets/templates/compact-library.pptx','assets/templates/compact-bindings.json',
         'assets/icons/lucide/LICENSE.txt',
         'assets/template-system.json','assets/templates/library.pptx','assets/templates/bindings.json',
         'LICENSE','THIRD_PARTY_NOTICES.md']
REBUILD='''"""Rebuild the native deck with this project's pinned runtime. Python 3.10+."""
from pathlib import Path
import argparse,hashlib,importlib.util,json,sys
sys.dont_write_bytecode=True
root=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--allow-input-edits',action='store_true');p.add_argument('--draft',action='store_true');args=p.parse_args()
manifest=json.loads((root/'project-manifest.json').read_text(encoding='utf-8'))
for name,expected in manifest['files'].items():
    if not isinstance(name,str) or ':' in name or '\\\\' in name or Path(name).is_absolute() or '..' in Path(name).parts:raise SystemExit('Unsafe project manifest path')
    if name=='input.json' and args.allow_input_edits:continue
    path=root/name
    if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest()!=expected:raise SystemExit('Project file missing/changed: '+name)
spec=importlib.util.spec_from_file_location('project_generate',root/'runtime/scripts/generate.py');g=importlib.util.module_from_spec(spec);spec.loader.exec_module(g)
document=json.loads((root/'input.json').read_text(encoding='utf-8'))
print(json.dumps(g.generate(document,args.output,font_profile=manifest['font_profile'],base_dir=root,draft=manifest.get('draft',False) or args.draft),ensure_ascii=False))
'''


def export(input_path,output,*,base_dir=None,font_profile='portable',draft=False):
    input_path=Path(input_path).resolve();destination=Path(output).resolve()
    if destination.exists():raise FileExistsError('Project directory exists; choose a new directory')
    if font_profile not in ['portable','office']:raise ValueError('Unknown font profile')
    base=Path(base_dir).resolve() if base_dir else input_path.parent
    document=json.loads(input_path.read_text(encoding='utf-8-sig'))
    if not isinstance(document,dict) or not isinstance(document.get('slides'),list):raise ValueError('Expected document object and slides array')
    document=copy.deepcopy(document);files={};assets=[]
    spec=importlib.util.spec_from_file_location('source_content',ROOT/'scripts/content_audit.py')
    content=importlib.util.module_from_spec(spec);spec.loader.exec_module(content)
    if not draft and (document.get('demo') is False or 'content_plan' in document):
        checked=content.inspect(document,base)
        if not checked['ok']:raise ValueError('Content review failed before source export: '+json.dumps(checked['issues'],ensure_ascii=False))
    materials=document.get('materials',{})
    if not isinstance(materials,dict) or not isinstance(materials.get('papers',[]),list):raise ValueError('materials.papers must be an array')
    if not isinstance(document.get('illustrations',{}),dict):raise ValueError('illustrations must be an object')
    def asset(container,key,role,allowed=('.png','.pdf')):
        value=container[key]
        if not isinstance(value,str) or not value.strip():raise ValueError('Nonempty asset path required')
        p=Path(value);p=(p if p.is_absolute() else base/p).resolve()
        if not p.is_relative_to(base):raise ValueError('Referenced asset leaves base directory; collect selected files under one project root')
        if not p.is_file():raise FileNotFoundError('Referenced '+role+' file unavailable')
        payload=p.read_bytes();digest=hashlib.sha256(payload).hexdigest()
        suffix=p.suffix.lower()
        if allowed is not None and suffix not in allowed:raise ValueError('Unsupported source asset suffix for '+role)
        relative='assets/'+digest+suffix
        files[relative]=payload;container[key]=relative
        assets.append({'role':role,'path':relative,'sha256':digest})
    for paper in document.get('materials',{}).get('papers',[]):
        if not isinstance(paper,dict):raise ValueError('Each paper must be an object')
        if 'path' in paper:asset(paper,'path','paper')
    for role,path in list(document.get('illustrations',{}).items()):asset(document['illustrations'],role,'illustration')
    for page in document['slides']:
        if not isinstance(page,dict):raise ValueError('Each slide must be an object')
        if not isinstance(page.get('images',{}),dict) or not isinstance(page.get('figures',[]),list):raise ValueError('images must be an object; figures must be an array')
        if 'experiment_scene' in page:raise ValueError('Explicitly migrate experiment_scene to composition before packaging')
        if 'image' in page:asset(page,'image','image')
        for slot,path in list(page.get('images',{}).items()):asset(page['images'],slot,'image')
        for figure in page.get('figures',[]):
            if not isinstance(figure,dict) or 'path' not in figure:raise ValueError('Each figure needs a path')
            asset(figure,'path','figure')
    plan=document.get('content_plan')
    if isinstance(plan,dict):
        for source in plan.get('sources',[]):
            # Content validation already checks UTF-8 extracts and source hashes.
            # Selected originals are opaque evidence data, never runtime modules.
            asset(source,'path','content extract',None)
            if 'origin' in source:asset(source['origin'],'path','content original',None)
        # Only referenced asset paths changed; source bytes and visible wording did not.
        if isinstance(plan.get('review'),dict):plan['review']['slides_sha256']=content.slides_digest(document)
    files['input.json']=(json.dumps(document,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    files['rebuild.py']=REBUILD.encode('utf-8')
    for name in RUNTIME:files['runtime/'+name]=(ROOT/name).read_bytes()
    instructions='''# 可搬迁源项目（本地移交）

本目录包括制作输入、仅被引用的PNG/PDF、内容摘录及其原始证据文件和生成所需的最小运行时；没有复制整个素材文件夹、字体或未被引用的私人文件。这些材料可能包含未公开内容，此工具不检查再分发许可，不应自动上传GitHub。

Python 3.10及以上，运行：

    python -B rebuild.py --output ../regenerated.pptx

输出必须为新文件；不会覆盖已有PPT。全部源文件默认先核对哈希。如果明确编辑input.json后重新制作，可使用 --allow-input-edits；模板、程序和素材仍须匹配原快照，原论文图也仍须满足来源哈希。不要把PPT中的手改当成JSON自动更新。

正式内容还须通过content_plan检查；--allow-input-edits不会跳过它。源内容编辑后先实际核对再更新review。未完成时明确使用--draft重建待审稿；以--draft导出的项目默认保持待审状态，不作为正式内容通过。

字体配置记录在清单内；实际渲染需要安装对应字体并使用Office等软件。能重新生成不证明另一台机器字体、显示、编辑或动画一致。原图为独立图片，其内部不可逐项编辑；标题和自制框图为原生对象。

源材料的备注/来源文本原样保留；路径字段已转为相对路径，但任意正文中仍可能存在私有信息。公开前另作隐私、科学内容与素材许可核对。
'''
    files['使用与重建.md']=instructions.encode('utf-8')
    manifest={'version':1,'font_profile':font_profile,'draft':draft,'assets':assets,
              'privacy':'Referenced PDFs/images included; local handoff only unless separately cleared.',
              'files':{n:hashlib.sha256(b).hexdigest() for n,b in files.items()}}
    files['project-manifest.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    destination.parent.mkdir(parents=True,exist_ok=True);destination.mkdir()
    try:
        for name,data in files.items():
            p=destination/name;p.parent.mkdir(parents=True,exist_ok=True)
            with p.open('xb') as f:f.write(data)
    except BaseException:
        shutil.rmtree(destination);raise
    return {'ok':True,'files':len(files),'assets':len({a['path'] for a in assets}),'directory':str(destination),'local_source_handoff':True}


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--input',required=True,type=Path)
    parser.add_argument('--output-directory',required=True,type=Path);parser.add_argument('--base-directory',type=Path)
    parser.add_argument('--font-profile',choices=['portable','office'],default='portable');parser.add_argument('--draft',action='store_true');args=parser.parse_args()
    try:result=export(args.input,args.output_directory,base_dir=args.base_directory,font_profile=args.font_profile,draft=args.draft)
    except (OSError,ValueError,TypeError,KeyError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False));return 1
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
