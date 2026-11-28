#!/usr/bin/env python3
"""Scoped transport tests; local sockets/TLS are real, DNS failure is injected."""
import importlib.util,json,socket,ssl,subprocess,tempfile,threading,time,unittest
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

try:
    import requests
except ImportError:
    requests=None

ROOT=Path(__file__).resolve().parent.parent
if requests:
    spec=importlib.util.spec_from_file_location('content_network',ROOT/'android-build/content-links/content_network.py')
    network=importlib.util.module_from_spec(spec);spec.loader.exec_module(network)

@unittest.skipUnless(requests,'Install tools/content-test-requirements.txt for real transport tests; cloud build requires them')
class Transport(unittest.TestCase):
    def setUp(self):network._CACHE.clear()
    def test_no_process_wide_socket_or_requests_mutation(self):
        original=socket.getaddrinfo;adapter=requests.Session().get_adapter('https://')
        session=network.prepare_session(requests.Session())
        self.assertIs(socket.getaddrinfo,original)
        self.assertNotIsInstance(adapter,network.ContentAdapter)
        self.assertIs(network.prepare_session(session),session)
    def test_preserves_retries_and_session_headers(self):
        session=requests.Session();session.headers['X-Test']='unchanged'
        original=session.get_adapter('https://');retry=original.max_retries
        network.prepare_session(session)
        self.assertIs(session.get_adapter('https://').max_retries,retry)
        self.assertEqual(session.headers['X-Test'],'unchanged')
    def test_native_first_does_not_consult_doh_when_healthy(self):
        addresses=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('192.0.2.1',443))]
        with patch.object(network,'_native_resolver',return_value=lambda *a:addresses),patch.object(network,'_https_dns') as doh:
            self.assertEqual(network._addresses('content.test',443),addresses);doh.assert_not_called()
    def test_unwraps_only_existing_udp_override_without_mutating_it(self):
        native=socket.getaddrinfo
        class DNSOverride:
            original_getaddrinfo=staticmethod(native)
            def _resolver(self,*a):raise AssertionError('legacy UDP resolver must not be used by content session')
        owner=DNSOverride()
        with patch.object(socket,'getaddrinfo',owner._resolver):
            self.assertIs(network._native_resolver(),native)
            self.assertEqual(socket.getaddrinfo,owner._resolver)
    def test_real_http_survives_simulated_native_dns_failure_and_preserves_host_headers(self):
        seen=[]
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                seen.append((self.headers['Host'],self.headers.get('Referer'),self.headers.get('X-Requested-With'),self.path))
                body=b'{"servers_dub":"mixdrop=fixture","servers_leg":""}'
                self.send_response(200);self.end_headers();self.wfile.write(body)
            def log_message(self,*a):pass
        server=ThreadingHTTPServer(('127.0.0.1',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
        try:
            with patch.object(network,'_native_resolver',return_value=lambda *a:(_ for _ in ()).throw(socket.gaierror())),patch.object(network,'_https_dns',return_value=['127.0.0.1']):
                s=network.prepare_session(requests.Session());s.trust_env=False
                result=s.get('http://content.test:'+str(server.server_port)+'/index.php?do=playerData',headers={'Referer':'https://content.test/film','X-Requested-With':'XMLHttpRequest'},timeout=2)
                self.assertIn('servers_dub',result.json())
            self.assertEqual(seen[0],('content.test:'+str(server.server_port),'https://content.test/film','XMLHttpRequest','/index.php?do=playerData'))
        finally:server.shutdown();server.server_close()
    def test_doh_positive_ttl_and_no_negative_cache(self):
        calls=[]
        class Pool:
            def __init__(self,*a,**kw):
                self.kw=kw;calls.append((a,kw))
                self.assert_config=kw['cert_reqs']==ssl.CERT_REQUIRED and kw['assert_hostname']==kw['server_hostname']
            def request(self,*a,**kw):
                self.request_args=(a,kw)
                return type('Response',(),dict(status=200,data=json.dumps(dict(Status=0,Answer=[dict(type=1,data='1.2.3.4',TTL=30)])).encode()))()
            def close(self):pass
        with patch.object(network,'HTTPSConnectionPool',Pool):
            self.assertEqual(network._https_dns('source.example'),['1.2.3.4'])
            self.assertEqual(network._https_dns('source.example'),['1.2.3.4'])
            self.assertEqual(len(calls),1)
            self.assertTrue(calls[0][1]['cert_reqs']==ssl.CERT_REQUIRED)
        class BadPool(Pool):
            def request(self,*a,**kw):return type('Response',(),dict(status=200,data=b'{"Status":3}'))()
        with patch.object(network,'HTTPSConnectionPool',BadPool):
            with self.assertRaises(socket.gaierror):network._https_dns('missing.example')
            self.assertNotIn('missing.example',network._CACHE)
    def test_https_sni_certificate_and_rejection_are_real(self):
        with tempfile.TemporaryDirectory() as folder:
            cert,key=Path(folder)/'cert.pem',Path(folder)/'key.pem'
            subprocess.run(['openssl','req','-x509','-newkey','rsa:2048','-nodes','-keyout',str(key),'-out',str(cert),'-days','1','-subj','/CN=content.test','-addext','subjectAltName=DNS:content.test'],check=True,capture_output=True)
            class Handler(BaseHTTPRequestHandler):
                def do_GET(self):self.send_response(200);self.end_headers();self.wfile.write(b'ok')
                def log_message(self,*a):pass
            server=ThreadingHTTPServer(('127.0.0.1',0),Handler)
            context=ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER);context.load_cert_chain(cert,key);names=[]
            context.set_servername_callback(lambda sock,name,ctx:names.append(name))
            server.socket=context.wrap_socket(server.socket,server_side=True)
            threading.Thread(target=server.serve_forever,daemon=True).start()
            try:
                addresses=[(socket.AF_INET,socket.SOCK_STREAM,6,'',('127.0.0.1',server.server_port))]
                with patch.object(network,'_addresses',return_value=addresses):
                    session=network.prepare_session(requests.Session());session.trust_env=False
                    url='https://content.test:'+str(server.server_port)+'/'
                    self.assertEqual(session.get(url,verify=str(cert),timeout=2).text,'ok')
                    session.close();session=network.prepare_session(requests.Session());session.trust_env=False
                    with self.assertRaises(requests.exceptions.SSLError):session.get(url,verify=True,timeout=2)
                    self.assertTrue(names and all(x=='content.test' for x in names))
            finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
