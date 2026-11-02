"""Guard the publication boundary independently of the bundle producer."""
import hashlib,importlib.util,json,os,tempfile,unittest,urllib.error,urllib.parse
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('reader_publisher',ROOT/'scripts/publish_reader_release.py')
publisher=importlib.util.module_from_spec(spec);spec.loader.exec_module(publisher)
COMMIT='a'*40

class ReleasePublisher(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.directory=self.root/'bundle';self.directory.mkdir()
        self.notes=self.root/'notes.md';self.notes.write_text('Release notes',encoding='utf-8')
        self.manifest=self.directory/'paper-close-read-v1.6.0.manifest.json'
        self.manifest.write_text(json.dumps({'source_state':'committed','source_commit':COMMIT}),encoding='utf-8')
        (self.directory/'paper-close-read-v1.6.0.zip').write_bytes(b'fixture producer bytes')
        self.sums()
        self.calls=[];self.existing=None;self.bad_digest=False
        self.env=patch.dict(os.environ,{'GITHUB_REPOSITORY':publisher.REPO});self.env.start()
        self.token=patch.object(publisher,'TOKEN','fixture-token');self.token.start()
        self.ci=patch.object(publisher,'status',return_value={'runs':[{'name':'tests','event':'push','status':'completed','conclusion':'success'}]});self.ci.start()
        self.tag=patch.object(publisher,'tag_commit',return_value=COMMIT);self.tag.start()
        self.api=patch.object(publisher,'request',side_effect=self.request);self.api.start()
        self.addCleanup(patch.stopall);self.addCleanup(self.temp.cleanup)

    def sums(self):
        paths=[p for p in self.directory.iterdir() if p.name!='SHA256SUMS.txt']
        (self.directory/'SHA256SUMS.txt').write_text(''.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.name+'\n' for p in paths),encoding='utf-8')

    def request(self,url,method='GET',body=None,**kwargs):
        self.calls.append((url,method))
        if url.endswith('/git/ref/heads/main'):return {'object':{'sha':COMMIT}}
        if '/releases/tags/' in url:
            if self.existing is not None:return self.existing
            raise urllib.error.HTTPError(url,404,'missing',None,None)
        if url.endswith('/releases') and method=='POST':return {'id':1,'assets':[],'draft':True}
        if url.startswith('https://uploads.github.com/'):
            name=urllib.parse.parse_qs(urllib.parse.urlparse(url).query)['name'][0]
            return {'name':name,'digest':'sha256:'+('0'*64 if self.bad_digest else hashlib.sha256(body).hexdigest())}
        if method=='PATCH':return {'id':1,'html_url':'https://github.com/'+publisher.REPO+'/releases/tag/paper-close-read-v1.6.0','draft':False}
        raise AssertionError((url,method))

    def publish(self):return publisher.publish(self.directory,COMMIT,self.notes)

    def test_wrong_repository_context_cannot_publish(self):
        with patch.dict(os.environ,{'GITHUB_REPOSITORY':'other/repo'}),self.assertRaisesRegex(ValueError,'context'):self.publish()
        self.assertEqual(self.calls,[])

    def test_failed_exact_ci_cannot_publish(self):
        with patch.object(publisher,'status',return_value={'runs':[{'name':'tests','event':'push','status':'completed','conclusion':'failure'}]}),self.assertRaisesRegex(ValueError,'CI'):self.publish()
        self.assertEqual(self.calls,[])

    def test_wrong_manifest_commit_cannot_upload(self):
        self.manifest.write_text(json.dumps({'source_state':'committed','source_commit':'b'*40}),encoding='utf-8');self.sums()
        with self.assertRaisesRegex(ValueError,'bound'):self.publish()
        self.assertFalse(any(method!='GET' for _,method in self.calls))

    def test_tampered_asset_cannot_upload(self):
        (self.directory/'paper-close-read-v1.6.0.zip').write_bytes(b'tampered')
        with self.assertRaisesRegex(ValueError,'checksum'):self.publish()
        self.assertFalse(any(method!='GET' for _,method in self.calls))

    def test_existing_tag_is_never_moved(self):
        with patch.object(publisher,'tag_commit',return_value='b'*40),self.assertRaisesRegex(ValueError,'another commit'):self.publish()
        self.assertFalse(any(method!='GET' for _,method in self.calls))

    def test_bad_server_digest_leaves_draft(self):
        self.bad_digest=True
        with self.assertRaisesRegex(ValueError,'digest'):self.publish()
        self.assertFalse(any(method=='PATCH' for _,method in self.calls))

    def test_upload_time_tag_drift_leaves_draft(self):
        with patch.object(publisher,'tag_commit',side_effect=[COMMIT,'b'*40]),self.assertRaisesRegex(ValueError,'changed during'):self.publish()
        self.assertFalse(any(method=='PATCH' for _,method in self.calls))

    def test_existing_public_release_is_not_completed_or_overwritten(self):
        self.existing={'id':1,'assets':[],'draft':False}
        with self.assertRaisesRegex(ValueError,'refusing modification'):self.publish()
        self.assertFalse(any(method!='GET' for _,method in self.calls))

    def test_publish_only_after_all_asset_digests_and_tag_match(self):
        result=self.publish()
        self.assertFalse(result['draft']);self.assertTrue(result['server_digests_match'])
        self.assertEqual(sum(url.startswith('https://uploads.github.com/') for url,_ in self.calls),3)
        self.assertEqual(self.calls[-1][1],'PATCH')

if __name__=='__main__':unittest.main()
