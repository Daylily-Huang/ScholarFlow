"""Publish the verified reader bundle from Actions after exact main CI."""
import argparse,hashlib,json,os,re,sys,time,urllib.request,urllib.error,urllib.parse,zipfile
from pathlib import Path
REPO='Daylily-Huang/ScholarFlow'
BASE='https://api.github.com/repos/'+REPO
TOKEN=os.environ.get('GITHUB_TOKEN','')
def request(url,method='GET',body=None,anonymous=False,raw=False,ctype='application/json'):
 if not url.startswith((BASE+'/', 'https://uploads.github.com/repos/'+REPO+'/','https://github.com/'+REPO+'/releases/download/')):raise ValueError('Unexpected destination')
 headers={'Accept':'application/vnd.github+json','User-Agent':'ScholarFlow-reader-release'}
 if body is not None:headers['Content-Type']=ctype
 req=urllib.request.Request(url,data=body,headers=headers,method=method)
 if TOKEN and not anonymous:req.add_unredirected_header('Authorization','Bearer '+TOKEN)
 with urllib.request.urlopen(req,timeout=180) as r:
  value=r.read();return value if raw else json.loads(value)
def sha(b):return hashlib.sha256(b).hexdigest()
def tag_commit(tag):
 obj=request(BASE+'/git/ref/tags/'+urllib.parse.quote(tag,safe=''))['object']
 for _ in range(16):
  if not re.fullmatch('[a-f0-9]{40}',obj.get('sha','')):raise ValueError('Bad tag object')
  if obj['type']=='commit':return obj['sha']
  if obj['type']!='tag':raise ValueError('Bad tag type')
  obj=request(BASE+'/git/tags/'+obj['sha'])['object']
 raise ValueError('Tag chain too deep')
def status(commit):
 runs=request(BASE+'/actions/runs?head_sha='+commit+'&per_page=30')['workflow_runs']
 checks=request(BASE+'/commits/'+commit+'/check-runs?per_page=100')['check_runs']
 return {'commit':commit,'runs':[{'id':r['id'],'name':r['name'],'event':r['event'],'status':r['status'],'conclusion':r['conclusion'],'url':r['html_url']} for r in runs],
         'checks':[{'name':c['name'],'status':c['status'],'conclusion':c['conclusion'],'url':c['html_url']} for c in checks]}
def publish(directory,commit,notes_path):
 if not TOKEN or os.environ.get('GITHUB_REPOSITORY')!=REPO:raise ValueError('Authorized repository Actions context required')
 if not re.fullmatch('[a-f0-9]{40}',commit):raise ValueError('Exact commit required')
 deadline=time.monotonic()+600
 while True:
  state=status(commit)
  ci=[r for r in state['runs'] if r['name']=='tests' and r['event']=='push']
  if ci and ci[0]['status']=='completed':
   if ci[0]['conclusion']!='success':raise ValueError('Exact main CI has not passed')
   break
  if time.monotonic()>=deadline:raise ValueError('Timed out waiting for exact main CI; no release published')
  time.sleep(15)
 branch=request(BASE+'/git/ref/heads/main')['object']['sha']
 if branch!=commit:raise ValueError('Main moved; candidate must be rechecked before release')
 directory=Path(directory);tag='paper-close-read-v1.6.0'
 manifest=json.loads((directory/(tag+'.manifest.json')).read_text(encoding='utf-8'))
 if manifest.get('source_state')!='committed' or manifest.get('source_commit')!=commit:raise ValueError('Manifest is not bound to release commit')
 expected={}
 for line in (directory/'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
  digest,name=line.split('  ',1)
  if Path(name).name!=name or any(c in name for c in '/\\:') or name in expected:raise ValueError('Unsafe asset name')
  if sha((directory/name).read_bytes())!=digest:raise ValueError('Local checksum mismatch')
  expected[name]=digest
 expected['SHA256SUMS.txt']=sha((directory/'SHA256SUMS.txt').read_bytes())
 if {p.name for p in directory.iterdir() if p.is_file()}!=set(expected):raise ValueError('Unexpected release files')
 try:actual=tag_commit(tag)
 except urllib.error.HTTPError as exc:
  if exc.code!=404:raise
  request(BASE+'/git/refs','POST',json.dumps({'ref':'refs/tags/'+tag,'sha':commit}).encode());actual=tag_commit(tag)
 if actual!=commit:raise ValueError('Existing tag belongs to another commit; refusing to move it')
 try:release=request(BASE+'/releases/tags/'+tag)
 except urllib.error.HTTPError as exc:
  if exc.code!=404:raise
  release=request(BASE+'/releases','POST',json.dumps({'tag_name':tag,'target_commitish':commit,'name':'文献阅读 skill v1.6.0：来源保真与连贯带读','body':Path(notes_path).read_text(encoding='utf-8'),'draft':True,'prerelease':False},ensure_ascii=False).encode())
 assets={a['name']:a for a in release['assets']}
 if set(assets)-set(expected):raise ValueError('Existing release has unexpected assets')
 for name,digest in expected.items():
  if name not in assets:
   if not release['draft']:raise ValueError('Published release is incomplete; refusing modification')
   assets[name]=request('https://uploads.github.com/repos/'+REPO+'/releases/'+str(release['id'])+'/assets?name='+urllib.parse.quote(name),'POST',(directory/name).read_bytes(),ctype='application/octet-stream')
  if assets[name].get('digest')!='sha256:'+digest:raise ValueError('Server digest mismatch: '+name)
 if tag_commit(tag)!=commit:raise ValueError('Tag changed during upload; draft remains unpublished')
 if release['draft']:release=request(BASE+'/releases/'+str(release['id']),'PATCH',b'{"draft":false,"make_latest":"true"}')
 return {'url':release['html_url'],'id':release['id'],'commit':commit,'tag':tag,'assets':expected,'server_digests_match':True,'draft':release['draft']}
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--directory',required=True);p.add_argument('--expected-ci-sha',required=True);a=p.parse_args()
 notes=Path(__file__).resolve().parents[1]/'docs/releases/paper-close-read-v1.6.0/CHANGELOG.zh-CN.md'
 print(json.dumps(publish(a.directory,a.expected_ci_sha,notes),ensure_ascii=False,indent=2))
