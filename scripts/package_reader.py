"""Create and optionally verify a standalone paper-close-read release (stdlib only)."""
import argparse,ast,hashlib,json,subprocess,sys,tempfile,zipfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(raw):return hashlib.sha256(raw).hexdigest()
def skill_version():
    tree=ast.parse((ROOT/'skills/paper-close-read/scripts/build_html.py').read_text(encoding='utf-8'))
    for node in tree.body:
        if isinstance(node,ast.Assign) and any(isinstance(t,ast.Name) and t.id=='GENERATOR_VERSION' for t in node.targets):
            value=ast.literal_eval(node.value)
            if not isinstance(value,str) or not value:raise ValueError('Invalid generator version')
            return value
    raise ValueError('Generator version missing')
def verify_archive(archive):
    with tempfile.TemporaryDirectory(prefix='reader-release-verify-',dir=str(Path(archive).parent)) as temp:
        temp=Path(temp)
        with zipfile.ZipFile(archive) as z:
            names=z.namelist()
            if len(names)!=len(set(names)):raise ValueError('Duplicate ZIP entries')
            if any(n.startswith(('/', '\\')) or '..' in Path(n).parts or ':' in n for n in names):raise ValueError('Unsafe ZIP paths')
            manifest=json.loads(z.read('manifest.json'))
            if set(names)!=(set(manifest['files'])|{'manifest.json'}):raise ValueError('ZIP file list differs from manifest')
            for name,expected in manifest['files'].items():
                if sha(z.read(name))!=expected:raise ValueError('Hash differs: '+name)
            z.extractall(temp/'unpacked')
        unpacked=temp/'unpacked';target=temp/'skills';sibling=target/'unrelated-skill';sibling.mkdir(parents=True);(sibling/'keep.txt').write_text('keep',encoding='utf-8')
        def run(args):
            result=subprocess.run([sys.executable,*[str(a) for a in args]],cwd=str(temp),capture_output=True,text=True,encoding='utf-8')
            if result.returncode:raise ValueError(result.stdout+result.stderr)
            return result
        for _ in range(2):run([unpacked/'install.py','--target',target])
        for name,expected in manifest['skill_files'].items():
            if sha((target/'paper-close-read'/name).read_bytes())!=expected:raise ValueError('Installed hash differs: '+name)
        if (sibling/'keep.txt').read_text(encoding='utf-8')!='keep':raise ValueError('Sibling skill changed')
        selftest=run([target/'paper-close-read/scripts/selftest.py','--work-dir',temp/'selftest'])
        for paper in ['hardy1908','carroll1895']:
            data=ROOT/'examples/paper-close-read'/paper/'reading-data';html=temp/(paper+'.html')
            run([target/'paper-close-read/scripts/build_html.py',data/'fulltext.json',data/'translations.json',data/'guide.json',html,'--asset-root',data,'--source',data/'source.md'])
            if html.read_bytes()!=(data.parent/'reader.html').read_bytes():raise ValueError('Installed generator differs for '+paper)
        return {'manifest_files':len(manifest['files']),'installed_skill_files':len(manifest['skill_files']),'idempotent_install':True,'sibling_preserved':True,'real_readers_rebuilt':['hardy1908','carroll1895'],'selftest':selftest.stdout.strip()}
def package(output,verify=False):
    version=skill_version();tag='paper-close-read-v'+version;output=Path(output);output.mkdir(parents=True,exist_ok=True)
    skill=ROOT/'skills/paper-close-read';docs=ROOT/'docs/releases'/tag
    payload={}
    for path in sorted(skill.rglob('*')):
        if path.is_file() and '__pycache__' not in path.parts and path.suffix!='.pyc':payload['paper-close-read/'+path.relative_to(skill).as_posix()]=path.read_bytes()
    installer=(ROOT/'scripts/install_reader.py').read_text(encoding='utf-8')
    origin="Path(__file__).resolve().parents[1]/'skills/paper-close-read'"
    if installer.count(origin)!=1:raise ValueError('Installer source layout changed; inspect packaging adapter')
    payload['install.py']=installer.replace(origin,"Path(__file__).resolve().parent/'paper-close-read'").encode('utf-8')
    for name in ['INSTALL.zh-CN.md','CHANGELOG.zh-CN.md']:payload[name]=(docs/name).read_bytes()
    commit=subprocess.check_output(['git','rev-parse','HEAD'],cwd=str(ROOT)).decode().strip()
    skill_files={name.removeprefix('paper-close-read/'):sha(raw) for name,raw in payload.items() if name.startswith('paper-close-read/')}
    manifest={'component':'paper-close-read','version':version,'tag':tag,'source_commit':commit,'license':'MIT (skill code only)','skill_tree_sha256':sha(json.dumps(skill_files,sort_keys=True,separators=(',',':')).encode()),'skill_files':skill_files,'files':{name:sha(raw) for name,raw in payload.items()}}
    manifest_bytes=(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n').encode('utf-8');payload['manifest.json']=manifest_bytes
    archive=output/(tag+'.zip')
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=9) as z:
        for name,raw in sorted(payload.items()):
            info=zipfile.ZipInfo(name,date_time=(1980,1,1,0,0,0));info.compress_type=zipfile.ZIP_DEFLATED;info.external_attr=0o100644<<16;z.writestr(info,raw)
    (output/(tag+'.manifest.json')).write_bytes(manifest_bytes)
    for name in ['INSTALL.zh-CN.md','CHANGELOG.zh-CN.md']:(output/name).write_bytes(payload[name])
    assets=[archive,output/(tag+'.manifest.json'),output/'INSTALL.zh-CN.md',output/'CHANGELOG.zh-CN.md']
    with (output/'SHA256SUMS.txt').open('w',encoding='utf-8',newline='\n') as stream:stream.write(''.join(sha(p.read_bytes())+'  '+p.name+'\n' for p in assets))
    result={'version':version,'source_commit':commit,'zip':str(archive),'zip_sha256':sha(archive.read_bytes()),'skill_tree_sha256':manifest['skill_tree_sha256'],'assets':[p.name for p in assets]+['SHA256SUMS.txt']}
    if verify:result['verification']=verify_archive(archive)
    return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',required=True,type=Path);p.add_argument('--verify',action='store_true');a=p.parse_args()
    try:print(json.dumps(package(a.output,a.verify),ensure_ascii=False,indent=2))
    except (OSError,ValueError,subprocess.SubprocessError,zipfile.BadZipFile) as exc:p.exit(2,'Release packaging failed: '+str(exc)+'\n')