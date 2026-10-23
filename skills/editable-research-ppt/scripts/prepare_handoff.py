"""Create a new, self-contained delivery folder; never overwrite existing output.

Original research material is not copied automatically. Rendering evidence is
accepted only when the source and every preview hash match the supplied files.
"""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]
def module(name):
    spec=importlib.util.spec_from_file_location(name,ROOT/'scripts'/(name+'.py'))
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
def sha(data):return hashlib.sha256(data).hexdigest()


def prepare(pptx,output,preview_dir=None,*,public=False):
    source=Path(pptx).resolve();destination=Path(output).resolve()
    if destination.exists():raise FileExistsError('Delivery directory exists; choose a new directory')
    if source.suffix.lower()!='.pptx':raise ValueError('Expected PPTX')
    payload=source.read_bytes();digest=sha(payload)
    inspection=module('inspect_deck').inspect(source)
    if not inspection['ok']:raise ValueError('Package inspection failed: '+str(inspection['errors']))
    if inspection['sha256']!=digest:raise ValueError('Source changed during inspection')
    layout=module('audit').audit(source,strict=True)
    if not layout['ok']:raise ValueError('Strict layout audit failed: '+str(layout['errors']))
    if inspection['offline_dependencies']:raise ValueError('Linked content must be embedded before offline delivery')
    if public and inspection['privacy_indicators']:
        raise ValueError('Review local paths or credential-like content before preparing a public bundle')
    files={'presentation.pptx':payload}
    rendering=None
    if preview_dir is not None:
        preview_dir=Path(preview_dir).resolve()
        rendering=json.loads((preview_dir/'powerpoint-validation.json').read_text(encoding='utf-8-sig'))
        if rendering.get('source_sha256')!=digest or rendering.get('quality_ok') is not True or rendering.get('source_unchanged') is not True:
            raise ValueError('Render evidence must pass and match the exact PPTX SHA256')
        pages=rendering.get('slides')
        if not isinstance(pages,list) or len(pages)!=len(inspection['pages']):raise ValueError('Incomplete preview set')
        if [p.get('slide') for p in pages]!=list(range(1,len(pages)+1)):raise ValueError('Preview page order mismatch')
        for i,page in enumerate(pages,1):
            name=f'slide-{i:02d}.png'
            if page.get('preview_file')!=name:raise ValueError('Unexpected preview filename')
            data=(preview_dir/name).read_bytes()
            if not data.startswith(b'\x89PNG\r\n\x1a\n') or sha(data)!=page.get('preview_sha256'):
                raise ValueError('Preview bytes differ from rendering report')
            files['previews/'+name]=data
        # Do not copy machine-local source paths from the rendering log.
        rendering=dict(rendering);rendering['source']='presentation.pptx'
        files['render-validation.json']=(json.dumps(rendering,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    status='结构检查通过；附与本稿哈希一致的PowerPoint渲染记录，仍需人工核对内容和视觉。' if rendering else '结构检查通过；未附本稿实机渲染记录，视觉未验证。'
    instructions=f'''# 使用与编辑

打开 presentation.pptx。预览如存在，位于previews文件夹。

验证状态：{status}

原生文字、形状、连接线可在PowerPoint修改；原生图表含工作簿时可编辑数据。独立图片可移动、裁剪和替换，内部文字/曲线不可逐项编辑；视频需要修改源文件再导出。对象清单只证明包结构，实际编辑仍以目标软件保存重开验证为准。

请另存后编辑。PPT中的手工修改不会自动写回制作JSON。原论文图表保持原图和来源；需要源码或原始数据时向制作者索取，交付工具不会自动附带私有论文和数据。不要因有交付包而假定素材许可已核实。

本工具没有主动删除备注、敏感资料、外链或修改科学内容。object-report.json中的privacy_indicators仅为模式提示，不是完整隐私审查。公开前核对备注、作者元信息、图像内容、引用和第三方素材许可。

未验证的软件和平台不作像素或播放一致性承诺。
'''
    files['使用与编辑.md']=instructions.encode('utf-8')
    files['object-report.json']=(json.dumps(inspection,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    files['layout-validation.json']=(json.dumps(layout,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    manifest={'version':1,'presentation_sha256':digest,'render_evidence_matched':rendering is not None,
              'manual_content_and_visual_review':'not established by this tool',
              'files':{n:sha(b) for n,b in files.items()}}
    files['delivery-manifest.json']=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8')
    destination.parent.mkdir(parents=True,exist_ok=True)
    destination.mkdir()  # Exclusive reservation; no existing directory may be replaced.
    try:
        for name,data in files.items():
            p=destination/name;p.parent.mkdir(parents=True,exist_ok=True)
            with p.open('xb') as f:f.write(data)
    except BaseException:
        shutil.rmtree(destination)
        raise
    return {'ok':True,'directory':str(destination),'sha256':digest,'files':len(files),'render_evidence_matched':rendering is not None}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--pptx',type=Path,required=True)
    parser.add_argument('--output-directory',type=Path,required=True)
    parser.add_argument('--preview-directory',type=Path)
    parser.add_argument('--public',action='store_true',help='Block pattern-based privacy indicators; does not publish or clear licences')
    args=parser.parse_args()
    try:result=prepare(args.pptx,args.output_directory,args.preview_directory,public=args.public)
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print(json.dumps({'ok':False,'error':str(exc)},ensure_ascii=False));return 1
    print(json.dumps(result,ensure_ascii=False,indent=2));return 0


if __name__=='__main__':raise SystemExit(main())
