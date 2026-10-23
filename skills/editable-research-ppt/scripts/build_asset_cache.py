"""Maintainer utility: compile an offline library from a provenance catalog.

Requires the optional compile_svg_asset dependency, not used for normal PPT work.
"""
from pathlib import Path
import argparse, hashlib, html, json, shutil
from compile_svg_asset import compile_svg

THEMES={
 'camera-monitoring':('相机监测与活动记录','camera,security_camera,emoji_u1f4f7,sd-card,emoji_u1f4be,battery-full,battery-charging,calendar-days,calendar,clock,footprints,paw,binoculars,compass,moon,sun,chart-scatter,chart-no-axes-combined,notebook-pen,clipboard-check,scan-eye,route'),
 'habitat-sampling':('森林生境与采样设计','tree-pine,trees,leaf,sprout,tree_broadleaved,tree_needleleaved,grass,mountain_range,mountain,water,wetland,map-pin,marker,marker-stroked,map-pin-plus,map-pin-check-inside,locate,map,route,backpack,ruler,tent-tree,emoji_u1f333,emoji_u1f332,emoji_u1f331,emoji_u1f33f,emoji_u1f3de,emoji_u1f9ed,emoji_u1f392,emoji_u1f98c'),
 'molecular-workflow':('非损伤采样与分子实验','test-tube,test-tubes,pipette,dna,scan-barcode,tags,thermometer-snowflake,refrigerator,flask-conical,falcon-15ml-empty,qpcr_machine,96well_pcr_plate_sky,384well_pcr_plate_kelly,agarose-gel,thermalcycler-pcr,thermalcycler-pcr-2,PCR_cycle,electrophoresis-gel,Low_speed_centrifuge,micropipette,micropipette-multi,pipette-box,microtube-closed-blue,microtube-open-translucent,centrifuge,spectrophotometer,gel-electrophoresis,DNA_double_helix,dna-1,emoji_u1f9ec,emoji_u1f9ea,emoji_u1f9e4,emoji_u1f9ca,emoji_u1f9fc'),
 'identity-qc':('微卫星分型与个体识别质控','scan-search,list-checks,git-compare-arrows,network,binary,file-check-2,badge-check,waypoints,clipboard-check,shield-check,check,check-check,triangle-alert,search,filter,funnel,table,database,chart-scatter,chart-no-axes-column,users,git-compare,git-branch,chart-line')}

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--library',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
 source=a.library.resolve();dest=a.output.resolve();dest.mkdir(parents=True,exist_ok=True)
 doc=json.loads((source/'catalog.json').read_text(encoding='utf-8'));results=[]
 for item in doc['assets']:
  data=(source/item['path']).read_bytes()
  assert hashlib.sha256(data).hexdigest()==item['sha256'],item['id']
  path=dest/item['path'];path.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/item['path'],path)
  for lic in [item['license_file'],*item.get('additional_license_files',[])]:
   target=dest/lic;target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source/lic,target)
  try:
   xml,meta=compile_svg(data,item['id'])
   rel='native/'+item['id']+'.xml';path=dest/rel;path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(xml)
   item['native']={**meta,'path':rel,'sha256':hashlib.sha256(xml).hexdigest(),'status':'geometry_candidate','edit_probe':'pending'}
  except (ValueError,TypeError,AttributeError,ZeroDivisionError) as exc:
   item['native']={'status':'source_only','reason':str(exc),'edit_probe':'not_applicable'}
  item['ppt_native_editability']='pending' if item['native']['status']=='geometry_candidate' else 'not_supported_by_cache'
  item['changes']='Original SVG retained; native cache is a separate derivative where supported.'
  results.append({'id':item['id'],'native':item['native']})
 themes={'id':'ecology-field-genetics','label_zh':'生态监测与遗传研究主题','scope':'Illustrative assets only; no private project data, coordinates, or research results. Generic deer is not species-identification evidence.','groups':[]}
 for gid,(label,names) in THEMES.items():
  selected=[x['id'] for x in doc['assets'] if x['name'] in names.split(',')]
  themes['groups'].append({'id':gid,'label_zh':label,'assets':selected})
 for item in doc['assets']:
  item['themes']=[g['id'] for g in themes['groups'] if item['id'] in g['assets']]
  if item['themes']:item['keywords']+=['生态监测','ecology','ecology-field-genetics']
  if item['name']=='emoji_u1f98c':item['label_zh']='通用鹿类示意（非物种鉴定依据）'
 doc['purpose']='Offline online-sourced illustrations with individually declared native conversion status.'
 doc['summary']['native_candidates']=sum(x['native']['status']=='geometry_candidate' for x in doc['assets'])
 doc['summary']['source_only']=len(doc['assets'])-doc['summary']['native_candidates']
 doc['summary']['ecology_theme']=len({x for g in themes['groups'] for x in g['assets']})
 for name,value in [('catalog.json',doc),('themes.json',themes),('conversion.json',results)]:
  (dest/name).write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 cards=[]
 for item in doc['assets']:
  text=' '.join([item['label_zh'],item['id'],item['category'],*item['keywords']])
  native=item['native']['status']=='geometry_candidate'
  cards.append('<article data-search="'+html.escape(text.lower(),quote=True)+'" data-theme="'+('yes' if item['themes'] else 'no')+'" data-native="'+str(native).lower()+'"><img loading="lazy" src="'+item['path']+'"><h3>'+html.escape(item['label_zh'])+'</h3><p>'+html.escape(item['id'])+'</p><p>'+html.escape(item['license'])+' · '+('原生形状候选' if native else 'SVG原件 / 图片后备')+'</p><a href="'+item['path']+'" download>SVG</a> · <a href="'+item['source_url']+'">来源</a></article>')
 page='''<!doctype html><html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>科研素材 · 生态监测研究主题</title><style>*{box-sizing:border-box}body{margin:40px auto;max-width:1380px;padding:0 24px;background:#f5f7f6;color:#143b32;font:16px/1.6 "Microsoft YaHei",sans-serif}h1{font-size:32px}input,select{padding:12px;font:inherit;margin:12px 8px 12px 0;border:1px solid #aac0b8;background:white}input{width:45%}.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:16px}article{padding:18px;background:white;border:1px solid #dce5e0}article[hidden]{display:none}img{width:140px;height:140px;object-fit:contain;display:block;margin:auto}h3{font-size:16px}p{color:#52675d}article p{font-size:12px;overflow-wrap:anywhere}a{color:#006a70}</style><h1>科研素材库 · 生态监测与遗传研究主题</h1><p>相机监测 / 森林生境与采样 / 分子实验 / 个体识别质控。原图证据仍优先；鹿类符号不是特定物种鉴定图。</p><input id="query" placeholder="搜索素材或英文ID"><select id="theme"><option value="yes">生态监测研究主题</option><option value="">全部素材</option></select><select id="native"><option value="">全部编辑状态</option><option value="true">原生形状候选</option><option value="false">仅SVG源文件</option></select><p id="count"></p><div class="grid">'''+''.join(cards)+'''</div><script>const cards=[...document.querySelectorAll('article')];function filter(){let n=0;for(const c of cards){c.hidden=!(query.value.toLowerCase().trim().split(/\\s+/).every(t=>c.dataset.search.includes(t))&&(!theme.value||c.dataset.theme===theme.value)&&(!native.value||c.dataset.native===native.value));if(!c.hidden)n++;}count.textContent=`显示 ${n} / ${cards.length} 项`;}[query,theme,native].forEach(e=>e.addEventListener('input',filter));filter();</script></html>'''
 (dest/'gallery.html').write_text(page,encoding='utf-8')
 print(json.dumps(doc['summary'],ensure_ascii=False))

if __name__=='__main__':main()
