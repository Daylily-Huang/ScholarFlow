/* Local-only persistence and portable backup primitives; no DOM or network required. */
((g)=>{'use strict';
 const MAX_FILE=32*1024*1024,MAX_ITEMS=10000;
 const own=(o,k)=>Object.prototype.hasOwnProperty.call(o,k);
 const object=x=>x!==null&&typeof x==='object'&&!Array.isArray(x);
 const str=(x,n)=>typeof x==='string'&&x.length<=n;
 const uid=()=>g.crypto&&typeof g.crypto.randomUUID==='function'?g.crypto.randomUUID():'a-'+Date.now()+'-'+Math.random().toString(36).slice(2);
 const clone=x=>JSON.parse(JSON.stringify(x));
 function validAnnotation(a){return object(a)&&str(a.id,300)&&!!a.id&&str(a.cid,300)&&!!a.cid&&str(a.text,100000)&&!!a.text&&str(a.note,200000)&&Number.isSafeInteger(a.start)&&Number.isSafeInteger(a.end)&&a.start>=0&&a.end>a.start&&a.end-a.start===a.text.length&&str(a.prefix,1000)&&str(a.suffix,1000);}
 function cleanAnnotation(a){if(!validAnnotation(a))throw Error('批注字段无效或超出支持范围');return {id:a.id,cid:a.cid,text:a.text,note:a.note,start:a.start,end:a.end,prefix:a.prefix,suffix:a.suffix,...(Number.isFinite(a.ts)?{ts:a.ts}:{}),...(Number.isFinite(a.updatedAt)?{updatedAt:a.updatedAt}:{}),...(str(a.revision,100)?{revision:a.revision}:{})};}
 function annotations(value){if(!Array.isArray(value)||value.length>MAX_ITEMS||new Set(value.map(a=>a&&a.id)).size!==value.length)throw Error('批注列表无效、标识重复或过大');return value.map(cleanAnnotation);}
 const signature=a=>a?JSON.stringify([a.cid,a.text,a.note,a.prefix,a.suffix]):null;
 function mergeText(base,local,remote){
  if(local===base)return remote;if(remote===base||local===remote)return local;
  if(!local)return remote;if(!remote)return local;
  if(local.includes(remote))return local;if(remote.includes(local))return remote;
  return local+'\n\n—— 另一份记录 ——\n'+remote;
 }
 function mergeReading(base,local,remote){
  const out=clone(local),same=(a,b)=>JSON.stringify(a)===JSON.stringify(b);let conflicts=0;
  out.read=[...new Set([...base.read,...local.read,...remote.read])].filter(id=>local.read.includes(id)===base.read.includes(id)?remote.read.includes(id):local.read.includes(id));
  out.recall={};for(const k of new Set([...Object.keys(local.recall),...Object.keys(remote.recall)]))out.recall[k]=mergeText(base.recall[k]||'',local.recall[k]||'',remote.recall[k]||'');
  out.documentNote=mergeText(base.documentNote||'',local.documentNote||'',remote.documentNote||'');
  if(out.documentNote!==local.documentNote&&local.documentNote!==base.documentNote)conflicts++;
  // A remote note edit must not switch the active window's route behind its DOM.
  out.route=local.route;out.last=local.last;
  out.positions={...remote.positions,...local.positions};for(const route of Object.keys(out.positions))if(same(local.positions?.[route],base.positions?.[route])&&remote.positions?.[route])out.positions[route]=remote.positions[route];
  return {value:out,conflicts};
 }
 function mergeAnnotations(base,local,remote){
  const maps=[base,local,remote].map(xs=>new Map(annotations(xs).map(a=>[a.id,a]))),ids=new Set(maps.flatMap(m=>[...m.keys()])),out=[];let conflicts=0;
  for(const id of ids){const [b,l,r]=maps.map(m=>m.get(id)),bs=signature(b),ls=signature(l),rs=signature(r);let chosen;
   if(ls===bs)chosen=r;else if(rs===bs)chosen=l;else if(ls===rs)chosen=l;
   else if(l&&r){out.push(r);if(!out.some(x=>signature(x)===ls)){out.push({...l,id:uid()});conflicts++;}continue;}
   else {chosen=l||r;conflicts++;}
   if(chosen)out.push(chosen);
  }return {value:out,conflicts};
 }
 function importAnnotations(current,incoming){const out=annotations(current),seen=new Set(out.map(signature)),ids=new Set(out.map(a=>a.id));let added=0,conflicts=0;
  for(const a of annotations(incoming)){const s=signature(a);if(seen.has(s))continue;const collision=ids.has(a.id),item={...a,id:collision?uid():a.id};out.push(item);seen.add(s);ids.add(item.id);added++;if(collision)conflicts++;}
  return {value:annotations(out),added,conflicts};
 }
 function normalizeReading(v,allowed){
  if(!object(v))throw Error('阅读记录必须是对象');const ids=new Set(allowed||[]),okId=x=>str(x,300)&&(!ids.size||ids.has(x));
  if(!Array.isArray(v.read)||!object(v.recall))throw Error('阅读记录字段无效');
  const read=[...new Set(v.read.filter(okId))],recall=Object.create(null),positions=Object.create(null);
  for(const k of Object.keys(v.recall))if(/^\d{1,5}$/.test(k)){if(!str(v.recall[k],MAX_FILE))throw Error('复述文本无效或过长');recall[k]=v.recall[k];}
  if(v.documentNote!==undefined&&!str(v.documentNote,MAX_FILE))throw Error('整篇笔记无效或过长');
  if(object(v.positions))for(const route of ['full','quick','deep']){const a=v.positions[route];if(object(a)&&okId(a.id)&&Number.isFinite(a.ratio))positions[route]={id:a.id,ratio:Math.max(0,Math.min(1,a.ratio))};}
  return {route:['full','quick','deep'].includes(v.route)?v.route:'full',read,recall,last:okId(v.last)?v.last:'',positions,documentNote:v.documentNote||'',layoutVersion:2};
 }
 function localStore(key,initial,validate,merge){
  let value=clone(initial),lastRaw=null,base=clone(initial),recoveryRaw=null,warning='',conflicts=0;
  try{lastRaw=g.localStorage.getItem(key);if(lastRaw!==null){try{value=validate(JSON.parse(lastRaw));base=clone(value);}catch(_){recoveryRaw=lastRaw;warning='corrupt';}}}catch(_){warning='unavailable';}
  const recoveryCopy=recoveryRaw;
  return {get value(){return clone(value);},get recoveryRaw(){return recoveryCopy;},get warning(){return warning;},get conflicts(){return conflicts;},
   save(next){value=validate(next);try{
    const current=g.localStorage.getItem(key);
    if(recoveryRaw!==null){const backup=key+':recovery:'+Date.now()+':'+uid();g.localStorage.setItem(backup,recoveryRaw);recoveryRaw=null;}
    if(current!==lastRaw&&current!==null){let remote;try{remote=validate(JSON.parse(current));}catch(_){g.localStorage.setItem(key+':recovery:'+Date.now()+':'+uid(),current);}
     if(remote){if(!merge){warning='conflict';return false;}const result=merge(base,value,remote);value=validate(result.value);conflicts=result.conflicts;}
    }
    const raw=JSON.stringify(value);g.localStorage.setItem(key,raw);lastRaw=raw;base=clone(value);warning='';return true;
   }catch(_){warning='unavailable';return false;}},
   refresh(){try{
    const raw=g.localStorage.getItem(key);if(raw===null||raw===lastRaw)return false;const next=validate(JSON.parse(raw));
    const dirty=JSON.stringify(value)!==JSON.stringify(base);
    if(dirty){if(!merge){warning='conflict';return false;}const result=merge(base,value,next);value=validate(result.value);conflicts=result.conflicts;}
    else value=next;
    // The remote snapshot is the new base; failed local writes remain in RAM for export/retry.
    base=clone(next);lastRaw=raw;return true;
   }catch(_){return false;}}
  };
 }
 function readBackup(text,paperId,allowed){
  if(typeof text!=='string'||text.length>MAX_FILE)throw Error('备份过大；支持32 MB以内的JSON');
  let bytes=0;for(const c of text){const n=c.codePointAt(0);bytes+=n<128?1:n<2048?2:n<65536?3:4;if(bytes>MAX_FILE)throw Error('备份过大；支持32 MB以内的JSON');}
  const d=JSON.parse(text);if(!object(d)||d.paperId!==paperId)throw Error('文件不属于这篇论文');
  if(d.schema===2)return {annotations:annotations(d.items),reading:null};
  if(d.schema!==3||d.kind!=='scholarflow-reading-backup')throw Error('不支持的备份版本');
  return {annotations:annotations(d.annotations),reading:normalizeReading(d.reading,allowed)};
 }
 function webAnnotations(items,config){
  const source='urn:scholarflow:reader:'+encodeURIComponent(config.paperId);
  return {'@context':'http://www.w3.org/ns/anno.jsonld',id:source+':annotations',type:'AnnotationPage',items:annotations(items).map(a=>({id:source+':annotation:'+encodeURIComponent(a.id),type:'Annotation',motivation:a.note?'commenting':'highlighting',...(a.note?{body:{type:'TextualBody',value:a.note,format:'text/plain',purpose:'commenting'}}:{}),target:{type:'SpecificResource',source,renderedVia:{id:'urn:scholarflow:reader-revision:'+config.revision,type:'Software'},selector:{type:'FragmentSelector',value:a.cid,refinedBy:{type:'TextQuoteSelector',exact:a.text,prefix:a.prefix,suffix:a.suffix}}},...(Number.isFinite(a.ts)&&Math.abs(a.ts)<=8640000000000000?{created:new Date(a.ts).toISOString()}:{}),...(Number.isFinite(a.updatedAt)&&Math.abs(a.updatedAt)<=8640000000000000?{modified:new Date(a.updatedAt).toISOString()}:{})}))};
 }
 g.ReaderPersistence={MAX_FILE,MAX_ITEMS,uid,clone,validAnnotation,annotations,mergeAnnotations,importAnnotations,normalizeReading,mergeReading,localStore,readBackup,webAnnotations};
})(typeof window!=='undefined'?window:globalThis);
