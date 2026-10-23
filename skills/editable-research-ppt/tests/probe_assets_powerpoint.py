"""Optional Windows acceptance probe; requires PowerPoint, pywin32 and Pillow.

Uses a disposable work folder and never overwrites the source deck. This is not
part of portable unittest discovery. The bank is built from native-bank.json.
"""
from pathlib import Path
import argparse,hashlib,json,math

def compare(original,native):
    from PIL import Image,ImageChops,ImageStat
    def normalize(path):
        im=Image.open(path).convert('RGBA');white=Image.new('RGBA',im.size,'white');white.alpha_composite(im);im=white.convert('RGB')
        box=ImageChops.difference(im,Image.new('RGB',im.size,'white')).getbbox()
        if box is None:raise ValueError('Blank exported asset: '+str(path))
        return im.crop(box).resize((256,256),Image.Resampling.LANCZOS)
    a,b=normalize(original),normalize(native)
    error=sum(ImageStat.Stat(ImageChops.difference(a,b)).mean)/(3*255)
    pa,pb=a.convert('L'),b.convert('L');aa=list(pa.getdata());bb=list(pb.getdata())
    union=sum(x<245 or y<245 for x,y in zip(aa,bb));intersection=sum(x<245 and y<245 for x,y in zip(aa,bb))
    iou=intersection/union if union else 1
    return {'normalized_mean_color_error':round(error,5),'foreground_iou':round(iou,5),
            'fidelity_screen_pass':error<=0.085 and iou>=0.70,
            'note':'Conservative image screen after foreground alignment; not a substitute for visual review.'}


def run(source,library,work,references=None):
    import win32com.client
    source=source.resolve();library=library.resolve();work=work.resolve()
    if work.exists():raise FileExistsError('Use a fresh work directory')
    work.mkdir(parents=True);renders=work/'renders';renders.mkdir();pairs=work/'pairs';pairs.mkdir()
    digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
    initial_hash=digest(source)
    catalog=json.loads((library/'catalog.json').read_text(encoding='utf-8'))
    assets=[a for a in catalog['assets'] if a.get('native',{}).get('path')]
    report={'source_sha256':initial_hash,'scope':'Windows desktop PowerPoint native groups; each cached asset is edited and saved/reopened. SVG vs group image comparison is a screening aid.','assets':[],'checks':{}}
    app=win32com.client.DispatchEx('PowerPoint.Application');initial=app.Presentations.Count;pres=None
    try:
        report['application']='PowerPoint '+app.Version
        pres=app.Presentations.Open(str(source),0,0,0)
        report['slide_count']=pres.Slides.Count
        locations={}
        for sl in pres.Slides:
            sl.Export(str(renders/('slide-%02d.png'%sl.SlideIndex)),'PNG',1920,1080)
            for sh in sl.Shapes:locations[sh.Name]=(sl.SlideIndex,sh)
        for number,item in enumerate(assets,1):
            name='probe-'+item['id'].replace('/','-');slide_index,group=locations[name]
            assert group.Type==6, item['id']+' is not a native group'
            assert group.GroupItems.Count==item['native']['native_parts'],item['id']
            prefix=item['id'].replace('/','--')
            native_file=pairs/(prefix+'-native.png');original_file=pairs/(prefix+'-original.png')
            group.Export(str(native_file),2,3072,1728)
            if references:
                original_file=references.resolve()/(prefix+'-original.png')
                if not original_file.is_file():raise FileNotFoundError(original_file)
            else:
                original=pres.Slides.Item(slide_index).Shapes.AddPicture(str((library/item['path']).resolve()),0,-1,0,0,float(group.Width),float(group.Height))
                try:original.Export(str(original_file),2,3072,1728)
                finally:original.Delete()
            rec={'id':item['id'],'slide':slide_index,'name':name,'source_sha256':item['sha256'],'cache_sha256':item['native']['sha256'],'native_parts':group.GroupItems.Count,**compare(original_file,native_file)}
            part=None;paint=None
            for candidate in group.GroupItems:
                if candidate.Fill.Visible==-1:part=candidate;paint='fill';break
                if candidate.Line.Visible==-1:part=candidate;paint='line';break
            if part is None:raise ValueError('No editable paint '+item['id'])
            expected_color=0xAA22DD
            if paint=='fill':part.Fill.ForeColor.RGB=expected_color
            else:part.Line.ForeColor.RGB=expected_color
            part.Left=float(part.Left)+2.25
            group.Left=float(group.Left)+1.25
            group.LockAspectRatio=0;group.Width=float(group.Width)*1.03
            rec.update(part_name=part.Name,paint=paint,expected_color=expected_color,
                       expected_group_left=float(group.Left),expected_group_width=float(group.Width),expected_part_left=float(part.Left))
            report['assets'].append(rec)
            if number%40==0:print(json.dumps({'processed':number,'total':len(assets)}),flush=True)
        edited=work/'edited-probe.pptx';pres.SaveAs(str(edited),24);pres.Close();pres=None
        pres=app.Presentations.Open(str(edited),-1,0,0)
        for rec in report['assets']:
            group=pres.Slides.Item(rec['slide']).Shapes.Item(rec['name']);part=group.GroupItems.Item(rec['part_name'])
            actual=part.Fill.ForeColor.RGB if rec['paint']=='fill' else part.Line.ForeColor.RGB
            rec['color_persisted']=actual==rec['expected_color']
            rec['child_move_persisted']=abs(float(part.Left)-rec['expected_part_left'])<0.15
            rec['group_move_persisted']=abs(float(group.Left)-rec['expected_group_left'])<0.15
            rec['group_resize_persisted']=abs(float(group.Width)-rec['expected_group_width'])<0.15
            rec['edit_probe_pass']=all(rec[k] for k in ('color_persisted','child_move_persisted','group_move_persisted','group_resize_persisted'))
            rec['group_type_after_reopen']=group.Type
        report['edited_sha256']=digest(edited)
        report['checks']={'all_native_groups':all(r['group_type_after_reopen']==6 for r in report['assets']),
                          'all_edit_probes_pass':all(r['edit_probe_pass'] for r in report['assets']),
                          'source_unchanged':digest(source)==initial_hash}
        report['fidelity_screen_passed']=sum(r['fidelity_screen_pass'] for r in report['assets'])
        report['fidelity_screen_failed']=[r['id'] for r in report['assets'] if not r['fidelity_screen_pass']]
        report['ok']=all(report['checks'].values())
    finally:
        if pres is not None:pres.Close()
        if initial==0 and app.Presentations.Count==0:app.Quit()
    (work/'validation.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'ok':report['ok'],'assets':len(assets),'checks':report['checks'],'fidelity_passed':report['fidelity_screen_passed'],'fidelity_failed':report['fidelity_screen_failed']},ensure_ascii=False),flush=True)
    return report


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--source',type=Path,required=True);p.add_argument('--library',type=Path,required=True);p.add_argument('--work-dir',type=Path,required=True);p.add_argument('--references',type=Path);a=p.parse_args()
    raise SystemExit(0 if run(a.source,a.library,a.work_dir,a.references)['ok'] else 1)
