import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from persistence import StateStore, database_path


class PersistenceTests(unittest.TestCase):
    def test_restart_and_multiple_store_instances(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'state.sqlite3'
            first, second = {}, {}
            a = StateStore(path, users=first)
            b = StateStore(path, users=second)
            with a.transaction():
                first['alice'] = {'logs': ['one']}
            with b.transaction():
                second['alice']['logs'].append('two')
            with a.transaction():
                self.assertEqual(first['alice']['logs'], ['one', 'two'])
            restored = {}
            StateStore(path, users=restored)
            self.assertEqual(restored, first)

    def test_failed_save_rolls_back(self):
        with tempfile.TemporaryDirectory() as directory:
            state = {}
            store = StateStore(Path(directory) / 'state.sqlite3', users=state)
            with self.assertRaises(TypeError):
                with store.transaction():
                    state['invalid'] = object()
            self.assertEqual(state, {})
            with store.transaction():
                self.assertEqual(state, {})

    def test_railway_requires_volume(self):
        with patch.dict(os.environ, {'RAILWAY_ENVIRONMENT_ID': 'test'}, clear=True):
            with self.assertRaises(RuntimeError):
                database_path()
        with patch.dict(os.environ, {'RAILWAY_VOLUME_MOUNT_PATH': '/data'}, clear=True):
            self.assertEqual(database_path(), Path('/data/monarch.sqlite3'))

    def test_api_survives_separate_process_restart(self):
        prelude = '''
from unittest.mock import patch
with patch('threading.Thread.start'):
    import Monarch_API as api
'''
        phases = [
            '''
assert api.addUser('test-user', 'Test Name') == {'status': 'added'}
api.updateLogs('persisted log', 'test-user')
api.updateCurrentStatus('working', 'test-user')
api.updateSchedule('12:00', 'trade', 'test-user')
api.updatePositions({'ABC': 3}, 'test-user')
api.updatesSettings('test-user', {'enabled': True})
api.Ping('test-user', 'V3', 'demo', '123')
api.openPosition('ABC')
api.closePosition('ABC', 5.0, 'long', 'test-user')
api.openPosition('XYZ')
''',
            '''
assert api.login('test-user') == {'status': 'Hey, Test Name'}
assert api.getLogs('test-user') == ['persisted log']
page = api.getTradePage('test-user')['trade-page']
assert page == {'positions': {'ABC': 3}, 'progress': ['working'], 'schedule': [{'12:00': 'trade'}]}
assert api.users['test-user']['Account_Balance'] == '123'
assert api.users['test-user']['settings'] == {'enabled': True}
assert api.users['test-user']['trades'][0]['ABC']['profit'] == 5.0
assert 'XYZ' in api.allOpenPositions
assert api.addUser('test-user', 'Overwrite')['status'] == 'user already exists'
assert api.getLogs('test-user') == ['persisted log']
api.removeUser('test-user', api.adminKey)
''',
            '''
assert api.login('test-user') == api.UNE
assert 'test-user' not in api.passwordToUser
'''
        ]
        with tempfile.TemporaryDirectory() as directory:
            environment = dict(os.environ, RAILWAY_VOLUME_MOUNT_PATH=directory)
            for phase in phases:
                result = subprocess.run([sys.executable, '-c', prelude + phase],
                                        env=environment, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
