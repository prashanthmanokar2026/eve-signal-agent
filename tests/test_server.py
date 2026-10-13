import json
import threading
import unittest
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from echo.server import SessionStore, make_server


class SessionTests(unittest.TestCase):
    def test_reset_isolated_from_inflight_old_session(self):
        store=SessionStore();old=store.create('first-contact');new=store.create('first-contact')
        store.step(old['session'],0)
        self.assertEqual(store.sessions[new['session']].env.actions,0)
        self.assertEqual(store.step(new['session'],0)['revision'],1)

    def test_duplicate_step_rejected(self):
        store=SessionStore();session=store.create('first-contact')['session']
        store.step(session,0)
        with self.assertRaises(ValueError):store.step(session,0)
        self.assertEqual(store.sessions[session].env.actions,1)

    def test_simultaneous_steps_execute_once(self):
        store=SessionStore();session=store.create('first-contact')['session']
        def attempt(_):
            try:return store.step(session,0)['revision']
            except ValueError:return 'rejected'
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertCountEqual(list(pool.map(attempt,range(2))),[1,'rejected'])

    def test_unknown_mission_and_expired_session(self):
        store=SessionStore()
        with self.assertRaises(ValueError):store.create('../secret')
        with self.assertRaises(KeyError):store.step('absent',0)


class HTTPTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server=make_server(0);cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url=f'http://127.0.0.1:{cls.server.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();cls.thread.join()

    def request(self,path,data=None,headers=None):
        req=urllib.request.Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,
            headers=headers if headers is not None else {'X-Echo-Client':'1','Content-Type':'application/json'})
        return urllib.request.urlopen(req)

    def test_static_app_and_mission_catalog(self):
        with self.request('/') as response:
            self.assertIn(b'ECHO',response.read());self.assertIn("frame-ancestors 'none'",response.headers['Content-Security-Policy'])
        with self.request('/api/missions') as response:self.assertEqual(len(json.load(response)),3)

    def test_complete_mission_and_export(self):
        with self.request('/api/sessions',{'mission':'first-contact'}) as response:state=json.load(response)
        while state['outcome']=='searching':
            with self.request('/api/step',{'session':state['session'],'revision':state['revision']}) as response:state=json.load(response)
        self.assertEqual(state['outcome'],'found')
        with self.request('/api/export/'+state['session']) as response:
            data=json.load(response);self.assertEqual(len(data['trace']),state['actions'])

    def test_cross_origin_and_missing_header_rejected(self):
        for headers in [{},{'X-Echo-Client':'1','Origin':'http://evil.example'}]:
            with self.assertRaises(urllib.error.HTTPError) as error:
                self.request('/api/sessions',{'mission':'first-contact'},headers)
            self.assertEqual(error.exception.code,403)

    def test_invalid_host_and_path(self):
        for path,headers,code in [('/',{'Host':'evil.example'},403),('/../echo/config.py',None,404)]:
            with self.assertRaises(urllib.error.HTTPError) as error:self.request(path,headers=headers)
            self.assertEqual(error.exception.code,code)

    def test_invalid_request_handled(self):
        with self.assertRaises(urllib.error.HTTPError) as error:self.request('/api/step',{'session':None,'revision':False})
        self.assertEqual(error.exception.code,400)


if __name__=='__main__':unittest.main()
