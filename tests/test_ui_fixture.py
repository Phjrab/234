"""Safety boundary for the UI browser harness, using actual auth/CSRF."""
import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest

from auth import AuthStore
from simulator import Simulator
from server import DashboardServer
from tools.ui_fixture_server import FixtureHandler, fixture_snapshot, PASSWORD


class UIFixtureTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        root = Path(self.directory.name)
        self.auth = AuthStore(root / 'auth.sqlite3')
        token, session = self.auth.login('admin', 'admin', '127.0.0.1')
        self.auth.change_password(token, '127.0.0.1', 'admin', PASSWORD, session['csrf_token'])
        self.sim = Simulator(root / 'state.sqlite3')
        self.server = DashboardServer(('127.0.0.1', 0), self.sim, Path('static'), auth=self.auth)
        self.server.RequestHandlerClass = FixtureHandler
        self.server.ui_snapshot = fixture_snapshot('dataset-67fdd2052ff0')
        self.server.denied_actions = []
        self.server.ui_audit = []
        self.server.ui_mode = 'normal'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        status, data, headers = self.request('/api/auth/login', {'username':'admin', 'password':PASSWORD})
        self.assertEqual(status, 200)
        self.cookie = headers['Set-Cookie'].split(';')[0]
        self.csrf = data['csrf_token']

    def tearDown(self):
        self.server.shutdown()
        self.thread.join(timeout=3)
        self.server.server_close()
        self.auth.close()
        self.sim.close()
        self.directory.cleanup()

    def request(self, path, body=None, auth=False, csrf=True):
        port = self.server.server_port
        headers = {'Origin':f'http://127.0.0.1:{port}', 'Content-Type':'application/json'}
        if auth:
            headers['Cookie'] = self.cookie
            if csrf:
                headers['X-CSRF-Token'] = self.csrf
        connection = http.client.HTTPConnection('127.0.0.1', port, timeout=5)
        connection.request('GET' if body is None else 'POST', path, None if body is None else json.dumps(body), headers)
        response = connection.getresponse()
        data = json.loads(response.read())
        result = response.status, data, dict(response.getheaders())
        connection.close()
        return result

    def test_execution_and_downloads_are_denied_after_auth(self):
        for path in ['/api/training/runs','/api/runs','/api/runs/train-000000000001/pause','/api/huggingface/download']:
            status, data, _ = self.request(path, {}, auth=True)
            self.assertEqual(status, 409)
            self.assertEqual(data['error']['code'], 'ui_fixture_denied')
        self.assertIsNone(self.server.training)
        self.assertIsNone(self.server.model_downloads)
        self.assertIsNone(self.server.worker_thread)

    def test_auth_csrf_and_real_preparation_contract(self):
        self.assertEqual(self.request('/api/status')[0], 401)
        self.assertEqual(self.request('/api/config/dry-run', {}, auth=True, csrf=False)[0], 403)
        status, data, _ = self.request('/api/datasets/validate', {'name':'Synthetic UI data','kind':'LLM','text':'{"instruction":"Hello","output":"World"}'}, auth=True)
        self.assertEqual(status, 200)
        self.assertTrue(data['valid'])
        self.assertEqual(self.server.denied_actions, [])

    def test_fixture_export_is_explicitly_synthetic(self):
        status, data, _ = self.request('/api/runs/train-000000000001/export?format=json', auth=True)
        self.assertEqual(status, 200)
        self.assertTrue(data['ui_fixture'])
        self.assertEqual(data['metrics_provenance'], 'synthetic_ui_fixture')
        self.assertEqual(data['mode'], 'real_training')
        self.assertFalse(data['synthetic'])  # Source contract shape, overridden by explicit fixture provenance.


if __name__ == '__main__':
    unittest.main()
