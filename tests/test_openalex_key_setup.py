"""Free-key integration, secret-free diagnostics, and honest OA failures."""
import importlib.util
import io
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
import urllib.error

SCRIPTS=Path(__file__).resolve().parents[1]/'skills/literature-discovery-acquisition/scripts'
sys.path.insert(0,str(SCRIPTS))
import openalex_access as access
import agent_search as search
import download_oa_papers as download


class KeySetupTests(unittest.TestCase):
    def test_key_only_in_auth_header(self):
        with patch.dict(os.environ,{'OPENALEX_API_KEY':'synthetic-test-secret'}):
            req=access.make_request('https://api.openalex.org/works?search=test')
            self.assertNotIn('synthetic-test-secret',req.full_url)
            self.assertEqual(req.get_header('Authorization'),'Bearer synthetic-test-secret')

    def test_refuse_non_api_host(self):
        with patch.dict(os.environ,{'OPENALEX_API_KEY':'synthetic-test-secret'}):
            for url in ('https://publisher.org/pdf','http://api.openalex.org/works','https://api.openalex.org.evil.test/works'):
                with self.assertRaises(ValueError):
                    access.make_request(url)

    def test_redirect_does_not_forward_key(self):
        with patch.dict(os.environ,{'OPENALEX_API_KEY':'synthetic-test-secret'}):
            req=access.make_request('https://api.openalex.org/works/W1')
            redirected=access.urllib.request.HTTPRedirectHandler().redirect_request(
                req,None,302,'moved',{},'https://publisher.example/pdf')
        self.assertIsNone(redirected.get_header('Authorization'))

    def test_missing_key_warns_once_on_stderr(self):
        with patch.dict(os.environ,{'OPENALEX_API_KEY':''}), patch.object(access,'_warned_keyless',False),patch('sys.stderr',new_callable=io.StringIO) as err:
            self.assertIsNone(access.make_request('https://api.openalex.org/works').get_header('Authorization'))
            access.make_request('https://api.openalex.org/works')
            self.assertEqual(err.getvalue().count('No OPENALEX_API_KEY'),1)

    def test_offline_status_does_not_reveal_key(self):
        with patch.dict(os.environ,{'OPENALEX_API_KEY':'synthetic-test-secret'}):
            result,code=access.check()
            self.assertTrue(result['key_configured'])
            self.assertNotIn('synthetic-test-secret',str(result))
            self.assertEqual(result['online_validation'],'NOT_RUN')

    def test_no_key_online_check_does_not_call_network(self):
        with patch.dict(os.environ,{'OPENALEX_API_KEY':''}),patch.object(access.urllib.request,'urlopen') as network:
            self.assertEqual(access.check(True)[1],2)
            network.assert_not_called()

    def test_budget_and_unknown_429_differ(self):
        def error(text):
            return urllib.error.HTTPError('https://api.openalex.org/works',429,'limited',{},io.BytesIO(text))
        self.assertEqual(access.error_code(error(b'Insufficient budget. Keyless requests from this client.')),'OPENALEX_BUDGET_EXHAUSTED')
        self.assertEqual(access.error_code(error(b'Rate limit exceeded')),'OPENALEX_RATE_LIMIT_OR_BUDGET')

    def test_failed_oa_resolution_is_not_closed(self):
        exc=urllib.error.HTTPError('https://api.openalex.org/works',429,'limited',{},io.BytesIO(b'Insufficient budget'))
        with patch.object(download.urllib.request,'urlopen',side_effect=exc):
            url,status=download.query_openalex_oa('10.1234/example')
        self.assertIsNone(url)
        self.assertEqual(status,'OPENALEX_BUDGET_EXHAUSTED')

    def test_resolution_failures_never_print_paywall(self):
        import json
        for code in ('OPENALEX_BUDGET_EXHAUSTED','OPENALEX_AUTH_REQUIRED_OR_INVALID','OPENALEX_REQUEST_FAILED'):
            with self.subTest(code=code),tempfile.TemporaryDirectory() as folder:
                source=Path(folder)/'input.json'
                source.write_text(json.dumps([{'record_id':'REC-KEY','doi':'10.1234/example',
                    'title':'Test','screening_status':'Include'}]),encoding='utf-8')
                with patch.object(download,'query_openalex_oa',return_value=(None,code)),patch.object(download.time,'sleep'),patch('sys.stdout',new_callable=io.StringIO) as out:
                    download.run_pipeline(str(source),str(Path(folder)/'out'),max_downloads=1)
                self.assertIn('OA status UNKNOWN',out.getvalue())
                self.assertNotIn('Paywalled: Requires institutional access',out.getvalue())
                ledger=json.loads((Path(folder)/'out/download_ledger.json').read_text(encoding='utf-8'))
                self.assertEqual(ledger[0]['status'],'DOWNLOAD_FAILED')

    def test_search_and_doi_resolution_attach_key(self):
        captured=[]
        class Response:
            status=200
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self):return b'{"meta":{"count":0},"results":[],"open_access":{"oa_status":"closed"}}'
        def request(req,**kwargs):
            captured.append(req)
            return Response()
        with patch.dict(os.environ,{'OPENALEX_API_KEY':'synthetic-test-secret'}),patch.object(search.urllib.request,'urlopen',side_effect=request):
            search.query_openalex_headless('test',limit=1)
            download.query_openalex_oa('10.1234/example')
        self.assertEqual(len(captured),2)
        self.assertTrue(all(r.get_header('Authorization')=='Bearer synthetic-test-secret' for r in captured))

    def test_activation_error_is_secret_free(self):
        error=urllib.error.HTTPError('https://api.openalex.org/rate-limit',403,'forbidden',{},io.BytesIO(b'{"error":"key_not_activated"}'))
        with patch.dict(os.environ,{'OPENALEX_API_KEY':'synthetic-test-secret'}),patch.object(access.urllib.request,'urlopen',side_effect=error):
            report,code=access.check(True)
        self.assertEqual(code,1)
        self.assertEqual(report['online_validation'],'OPENALEX_KEY_NOT_ACTIVATED')
        self.assertNotIn('synthetic-test-secret',str(report))

    def test_snowball_all_requests_receive_auth(self):
        captured=[]
        class Response:
            status=200
            def __init__(self,data):self.data=data
            def __enter__(self):return self
            def __exit__(self,*args):return False
            def read(self):
                import json
                return json.dumps(self.data).encode()
        def request(req,**kwargs):
            captured.append(req)
            if len(captured)==1:
                return Response({'id':'https://openalex.org/W1','doi':'https://doi.org/10.1234/example',
                    'referenced_works':['https://openalex.org/W2']})
            return Response({'results':[]})
        with patch.dict(os.environ,{'OPENALEX_API_KEY':'synthetic-test-secret'}),patch.object(search.urllib.request,'urlopen',side_effect=request):
            search.run_snowball_search('10.1234/example',limit=2)
        self.assertEqual(len(captured),3)
        self.assertTrue(all(r.get_header('Authorization')=='Bearer synthetic-test-secret' for r in captured))
