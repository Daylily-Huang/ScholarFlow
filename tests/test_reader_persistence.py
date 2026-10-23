"""Execute the actual browser-independent backup/persistence code with Node, when available."""
import shutil,subprocess,unittest
from pathlib import Path

NODE=shutil.which('node')
SCRIPT=Path(__file__).resolve().parents[1]/'skills/paper-close-read/assets/persistence.js'

@unittest.skipUnless(NODE,'Node required for browser data-layer execution; core build does not require it')
class ReaderPersistence(unittest.TestCase):
 def run_js(self,body):
  setup=r"""
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm');
const memory=new Map(),storage={getItem:k=>memory.has(k)?memory.get(k):null,setItem:(k,v)=>memory.set(k,String(v))};
const ctx={window:{localStorage:storage},console};vm.runInNewContext(fs.readFileSync(process.argv[1],'utf8'),ctx);
const P=ctx.window.ReaderPersistence,ann=(id='a',note='original')=>({id,cid:'p-en',start:0,end:5,text:'quote',note,prefix:'',suffix:'',ts:1000});
const plain=x=>JSON.parse(JSON.stringify(x));
"""
  result=subprocess.run([NODE,'-e',setup+body,str(SCRIPT)],capture_output=True,text=True)
  self.assertEqual(result.returncode,0,result.stderr)
 def test_corrupt_data_is_backed_up_before_any_write(self):
  self.run_js("""
memory.set('annotations','{broken');const store=P.localStore('annotations',[],P.annotations,P.mergeAnnotations);
assert.equal(store.warning,'corrupt');assert.equal(memory.get('annotations'),'{broken');
assert.equal(store.save([ann()]),true);assert.equal(store.recoveryRaw,'{broken');
const recoveries=[...memory.entries()].filter(([k])=>k.startsWith('annotations:recovery:'));
assert.equal(recoveries.length,1);assert.equal(recoveries[0][1],'{broken');
store.save([ann('a','next')]);assert.equal([...memory.keys()].filter(k=>k.includes(':recovery:')).length,1);
""")
 def test_unavailable_or_full_storage_retains_unsaved_data_for_export(self):
  self.run_js("""
const store=P.localStore('annotations',[],P.annotations,P.mergeAnnotations);
storage.setItem=()=>{throw Error('quota');};assert.equal(store.save([ann()]),false);
assert.equal(store.value[0].text,'quote');assert.equal(memory.get('annotations'),undefined);
assert.equal(store.warning,'unavailable');
""")
 def test_concurrent_note_edits_keep_both_and_deletion_does_not_resurrect(self):
  self.run_js("""
memory.set('a',JSON.stringify([ann()]));const first=P.localStore('a',[],P.annotations,P.mergeAnnotations),second=P.localStore('a',[],P.annotations,P.mergeAnnotations);
first.save([ann('a','first edit')]);second.save([ann('a','second edit')]);
assert.equal(second.conflicts,1);assert.deepEqual(new Set(second.value.map(a=>a.note)),new Set(['first edit','second edit']));
const remaining=second.value.slice(1);second.save(remaining);assert.equal(JSON.parse(memory.get('a')).length,1);
first.refresh();assert.equal(first.value.length,1);
""")
 def test_import_is_idempotent_and_conflicting_ids_do_not_erase_notes(self):
  self.run_js("""
let result=P.importAnnotations([ann()],[ann('a','different')]);assert.equal(result.added,1);assert.equal(result.conflicts,1);assert.equal(result.value.length,2);
result=P.importAnnotations(result.value,[ann('a','different')]);assert.equal(result.added,0);assert.equal(result.value.length,2);
""")
 def test_full_and_legacy_backups_validate_before_modification(self):
  self.run_js("""
const reading={route:'deep',read:['p','removed'],recall:{'0':'my answer'},last:'p',positions:{deep:{id:'p',ratio:.42}},documentNote:'my note',layoutVersion:2};
const payload={schema:3,kind:'scholarflow-reading-backup',paperId:'paper',reading,annotations:[ann()]};
const parsed=P.readBackup(JSON.stringify(payload),'paper',['p']);assert.equal(parsed.reading.documentNote,'my note');assert.equal(parsed.reading.positions.deep.ratio,.42);assert.deepEqual(plain(parsed.reading.read),['p']);
assert.equal(P.readBackup(JSON.stringify({schema:2,paperId:'paper',items:[ann()]}),'paper').reading,null);
assert.throws(()=>P.readBackup(JSON.stringify(payload),'other'));payload.annotations[0].end=999;assert.throws(()=>P.readBackup(JSON.stringify(payload),'paper'));
assert.throws(()=>P.readBackup('x'.repeat(P.MAX_FILE+1),'paper'));
""")
 def test_reading_state_is_whitelisted_and_does_not_overwrite_a_newer_tab(self):
  self.run_js("""
const initial={read:[],recall:{},last:'',route:'full'};
const one=P.localStore('read',initial,v=>P.normalizeReading(v,['p'])),two=P.localStore('read',initial,v=>P.normalizeReading(v,['p']));
one.save({...initial,documentNote:'first'});assert.equal(two.save({...initial,documentNote:'second'}),false);assert.equal(JSON.parse(memory.get('read')).documentNote,'first');assert.equal(two.value.documentNote,'second');
const polluted=JSON.parse('{"read":["p"],"recall":{"__proto__":"bad","0":"ok"},"route":"unknown","evil":true}');
const clean=P.normalizeReading(polluted,['p']);assert.equal(clean.route,'full');assert.equal(clean.evil,undefined);assert.deepEqual(Object.keys(clean.recall),['0']);
""")
 def test_standard_export_keeps_exact_quote_and_targets_derived_reader(self):
  self.run_js("""
const exported=P.webAnnotations([ann()],{paperId:'10.0000/test',revision:'revision'});
assert.equal(exported.type,'AnnotationPage');const target=exported.items[0].target;
assert.equal(target.selector.refinedBy.exact,'quote');assert.equal(target.selector.value,'p-en');assert.match(target.source,/^urn:scholarflow:reader:/);assert.equal(exported.items[0].body.value,'original');
assert.doesNotThrow(()=>P.webAnnotations([{...ann(),ts:1e100}],{paperId:'p',revision:'r'}));
""")
 def test_reading_three_way_merge_preserves_parallel_notes_and_actual_unread(self):
  self.run_js("""
const empty={route:'full',read:[],recall:{},last:'',positions:{},documentNote:''};
memory.set('r',JSON.stringify(empty));const one=P.localStore('r',empty,P.normalizeReading,P.mergeReading),two=P.localStore('r',empty,P.normalizeReading,P.mergeReading);
one.save({...empty,read:['p'],documentNote:'window A'});assert.equal(two.save({...empty,documentNote:'window B'}),true);
assert.match(two.value.documentNote,/window A/);assert.match(two.value.documentNote,/window B/);assert.deepEqual(plain(two.value.read),['p']);
const b=two.value,local={...b,read:[]},remote={...b,recall:{'0':'other'}};assert.deepEqual(plain(P.mergeReading(b,local,remote).value.read),[]);
assert.equal(P.mergeReading(empty,empty,{...empty,route:'deep'}).value.route,'full');
const large='x'.repeat(1000000);assert.equal(P.normalizeReading({...empty,documentNote:large+large}).documentNote.length,2000000);
assert.throws(()=>P.normalizeReading({...empty,documentNote:123}));
""")
 def test_remote_refresh_does_not_discard_a_failed_local_write(self):
  self.run_js("""
memory.set('a',JSON.stringify([ann()]));const first=P.localStore('a',[],P.annotations,P.mergeAnnotations),second=P.localStore('a',[],P.annotations,P.mergeAnnotations);
const set=storage.setItem;storage.setItem=()=>{throw Error('quota');};assert.equal(first.save([ann(),ann('local','ONLY IN WINDOW A')]),false);
storage.setItem=set;second.save([ann(),ann('remote','WINDOW B')]);assert.equal(first.refresh(),true);
assert.deepEqual(new Set(first.value.map(a=>a.note)),new Set(['original','ONLY IN WINDOW A','WINDOW B']));
first.save(first.value);assert.equal(JSON.parse(memory.get('a')).length,3);
""")

if __name__=='__main__':unittest.main()
