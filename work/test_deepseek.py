"""Verify local assistant launch boundaries and the pet menu integration."""
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT/'src'))
from citlali_pet import app
from citlali_pet.ui import deepseek
from citlali_pet.ui.menu_view import COMMANDS, HEIGHT, HITS, hit_test, render_menu


class DeepSeekTests(unittest.TestCase):
    def test_local_url_rejects_remote_hosts_credentials_and_other_ports(self):
        self.assertTrue(deepseek.local_url('http://127.0.0.1:3080/?token=test'))
        for url in (None, '', 'https://example.com', 'http://127.0.0.1:3081/',
                    'http://user:pass@127.0.0.1:3080/', 'http://127.0.0.1:bad/'):
            self.assertFalse(deepseek.local_url(url))

    def test_child_state_and_caches_stay_inside_installation(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            root = Path(folder)
            env = deepseek.launch_environment(root)
            for name in ('DSH_HOME','TEMP','TMP','npm_config_cache','npm_config_store_dir',
                         'PNPM_HOME','COREPACK_HOME','XDG_CACHE_HOME'):
                self.assertTrue(Path(env[name]).relative_to(root).parts)
                self.assertTrue(Path(env[name]).is_dir())
            self.assertEqual(env['DSH_PERMISSION_MODE'], 'workspace-write')

    def test_authenticated_service_accepts_credential_free_401_probe(self):
        with patch.object(deepseek, 'HTTPConnection') as connection:
            connection.return_value.getresponse.return_value.status = 401
            self.assertTrue(deepseek.service_ready('http://127.0.0.1:3080/?token=test'))
            connection.return_value.close.assert_called_once()
        with patch.object(deepseek, 'HTTPConnection') as connection:
            connection.return_value.request.side_effect = OSError
            self.assertFalse(deepseek.service_ready('http://127.0.0.1:3080/'))

    def test_reopen_reuses_live_service_without_spawning(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            root = Path(folder)
            (root/'data').mkdir()
            url = 'http://127.0.0.1:3080/?token=test'
            (root/'data/pet-service.json').write_text(json.dumps({'pid':123,'url':url}))
            with patch.object(deepseek,'process_alive',return_value=True), \
                 patch.object(deepseek,'service_ready',return_value=True), \
                 patch.object(deepseek.subprocess,'Popen') as spawn:
                self.assertEqual(deepseek.ensure_service(root),url)
                spawn.assert_not_called()

    def test_missing_installation_has_actionable_error(self):
        with tempfile.TemporaryDirectory(dir=ROOT/'work') as folder:
            with self.assertRaisesRegex(RuntimeError,'install_deepseek.ps1'):
                deepseek.ensure_service(Path(folder))

    def test_menu_button_dispatches_without_waiting_for_service(self):
        with patch.object(app, 'open_assistant') as launch:
            app.DesktopPet.menu_command(SimpleNamespace(hwnd=42),70)
            launch.assert_called_once()
        self.assertIn(70,COMMANDS)
        for command, (left,top,right,bottom) in HITS.items():
            self.assertEqual(hit_test((left+right)/2,(top+bottom)/2),command)
            self.assertLess(bottom,HEIGHT)
        state={'auto':False,'requested':'standing','pending':None,'paused':False,'scale':1}
        render_menu(state,70).save(ROOT/'work/deepseek-menu-preview.png')


if __name__ == '__main__':
    unittest.main()
