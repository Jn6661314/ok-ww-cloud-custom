"""Moonlight 串流窗口预设.

Moonlight 的串流窗口标题来自上游 app/streaming/session.cpp:
  「<计算机名> - Moonlight」
主界面窗口只叫 Moonlight, 预设必须只匹配串流窗口, 否则会抓错窗口。
"""

import ast
import importlib.util
import os
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORK = os.environ.get('OKWW_WORK', r'C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working')
os.chdir(WORK)
sys.path.insert(0, str(WORK))


def load_from_repo(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sw = load_from_repo('src/stream_window.py', '_stream_window_moonlight_test')


class MoonlightPresetTest(unittest.TestCase):

    def test_moonlight_pattern_matches_stream_window_only(self):
        pattern = re.compile(sw.preset_title('Moonlight'), re.IGNORECASE)
        self.assertTrue(pattern.search('DESKTOP-ABC - Moonlight'))
        self.assertTrue(pattern.search('游戏机 - Moonlight'))
        self.assertFalse(pattern.search('Moonlight'), '不能抓到 Moonlight 主界面')
        self.assertFalse(pattern.search('DESKTOP-ABC - Parsec'))

    def test_other_presets_and_unknown(self):
        self.assertIn('UU远程', sw.preset_title('UU远程'))
        self.assertIn('ToDesk', sw.preset_title('ToDesk'))
        self.assertIn('SunloginClient', sw.preset_title('向日葵'))
        self.assertIn('Parsec', sw.preset_title('Parsec'))
        self.assertEqual(sw.preset_title('Manual'), '')
        self.assertEqual(sw.preset_title('NoSuchPreset'), '')

    def test_resolve_title_combines_preset_and_manual(self):
        preset = sw.preset_title('Moonlight')
        self.assertEqual(sw.resolve_title('Moonlight', ''), preset)
        self.assertEqual(sw.resolve_title('Manual', ' UU远程 '), 'UU远程')
        self.assertEqual(sw.resolve_title('Moonlight', 'UU远程'),
                         f'(?:{preset})|(?:UU远程)')

    def test_settings_use_preset_when_title_blank(self):
        class FakeGlobalConfig:
            def get_config(self, name):
                self.name = name
                return {'Enable': True, 'Preset': 'Moonlight',
                        'Window Title': '', 'Force Pynput': True}

        enabled, title, force = sw.stream_window_settings(FakeGlobalConfig())
        self.assertTrue(enabled)
        self.assertEqual(title, sw.preset_title('Moonlight'))
        self.assertTrue(force)

    def test_settings_without_config(self):
        self.assertIsNone(sw.stream_window_settings(None))


class ConfigRegistrationTest(unittest.TestCase):

    @staticmethod
    def _stream_option_node():
        tree = ast.parse((ROOT / 'config.py').read_text(encoding='utf-8'))
        for node in tree.body:
            if not isinstance(node, ast.Assign):
                continue
            if any(isinstance(t, ast.Name) and t.id == 'stream_config_option'
                   for t in node.targets):
                return node.value
        raise AssertionError('config.py 里没有 stream_config_option')

    def test_preset_registered_with_moonlight(self):
        call = self._stream_option_node()
        self.assertIsInstance(call, ast.Call)
        defaults = ast.literal_eval(call.args[1]) if len(call.args) > 1 else {}
        config_type = {}
        for keyword in call.keywords:
            if keyword.arg == 'config_type':
                config_type = ast.literal_eval(keyword.value)
        self.assertEqual(defaults.get('Preset'), 'Manual')
        self.assertIn('Moonlight', config_type['Preset']['options'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
