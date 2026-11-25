"""启动器版本号同步（app.json.current_version ↔ config.py::version）的测试。

背景：pyappify 的 ``data/apps/ok-ww/app.json`` 里 ``current_version`` 记录"已安装版本"，
启动器（ok-ww.exe）用它显示版本号，也用它判断"有没有新版本可以更新"。

我们的代码基线上移后如果这里不同步，会出现两个问题：

1. 启动器一直显示旧版本号（例如代码已是 v3.8.15，界面还写着 v3.8.14），
   让人误以为定制没生效；
2. 启动器认为还能"更新"到基线那个版本 —— 用户一点更新，官方代码就会覆盖
   ``working`` / ``repo``，整套定制（云账号、MuMu、拉海洛等）全部丢失。

所以 ``restore.py`` 每次部署都要把 ``current_version`` 对齐到 ``config.py`` 的 ``version``。
"""

import json
import re
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import restore  # noqa: E402


def make_layout(tmp, current_version):
    """建出 ``<tmp>/working`` + ``<tmp>/app.json``，返回 (working, app_json)。"""
    root = Path(tmp)
    working = root / 'working'
    working.mkdir()
    app_json = root / 'app.json'
    app_json.write_text(json.dumps({
        'name': 'ok-ww',
        'current_version': current_version,
        'app_starting_version': 'v3.8.9',
        'available_versions': ['v3.8.15', 'v3.8.14'],
        'update_method': 'MANUAL_UPDATE',
    }, indent=2, ensure_ascii=False), encoding='utf-8')
    return working, app_json


class ReadSourceVersionTest(unittest.TestCase):
    def test_reads_the_repo_config_version(self):
        expected = re.search(r"""^version\s*=\s*['"]([^'"]+)['"]""",
                             (REPO / 'config.py').read_text(encoding='utf-8'),
                             re.MULTILINE).group(1)
        self.assertEqual(restore.read_source_version(), expected)

    def test_version_looks_like_a_release(self):
        # 启动器按数字版本比较，写成 "dev" 之类会让它一直提示有更新
        self.assertRegex(restore.read_source_version(), r'^v\d+\.\d+\.\d+$')


class SyncAppVersionTest(unittest.TestCase):
    def test_rewrites_when_launcher_version_is_older(self):
        with tempfile.TemporaryDirectory() as tmp:
            working, app_json = make_layout(tmp, 'v3.8.14')
            self.assertEqual(restore.sync_app_version(working, 'STAMP', True), 0)
            data = json.loads(app_json.read_text(encoding='utf-8'))
            self.assertEqual(data['current_version'], restore.read_source_version())
            # 其他字段原样保留
            self.assertEqual(data['app_starting_version'], 'v3.8.9')
            self.assertEqual(data['available_versions'], ['v3.8.15', 'v3.8.14'])

    def test_backs_up_before_rewriting(self):
        with tempfile.TemporaryDirectory() as tmp:
            working, app_json = make_layout(tmp, 'v3.8.14')
            restore.sync_app_version(working, 'STAMP', True)
            backup = app_json.with_name('app.json.STAMP.bak')
            self.assertTrue(backup.is_file())
            self.assertEqual(json.loads(backup.read_text(encoding='utf-8'))['current_version'],
                             'v3.8.14')

    def test_leaves_file_alone_when_already_synced(self):
        with tempfile.TemporaryDirectory() as tmp:
            working, app_json = make_layout(tmp, restore.read_source_version())
            before = app_json.read_text(encoding='utf-8')
            restore.sync_app_version(working, 'STAMP', True)
            self.assertEqual(app_json.read_text(encoding='utf-8'), before)
            self.assertFalse(app_json.with_name('app.json.STAMP.bak').exists())

    def test_no_backup_when_disabled(self):
        with tempfile.TemporaryDirectory() as tmp:
            working, app_json = make_layout(tmp, 'v3.8.14')
            restore.sync_app_version(working, 'STAMP', False)
            self.assertFalse(app_json.with_name('app.json.STAMP.bak').exists())
            self.assertEqual(
                json.loads(app_json.read_text(encoding='utf-8'))['current_version'],
                restore.read_source_version())

    def test_missing_app_json_is_not_fatal(self):
        with tempfile.TemporaryDirectory() as tmp:
            working = Path(tmp) / 'working'
            working.mkdir()
            self.assertEqual(restore.sync_app_version(working, 'STAMP', True), 0)

    def test_broken_json_is_left_untouched(self):
        with tempfile.TemporaryDirectory() as tmp:
            working, app_json = make_layout(tmp, 'v3.8.14')
            app_json.write_text('{not json', encoding='utf-8')
            self.assertEqual(restore.sync_app_version(working, 'STAMP', True), 0)
            self.assertEqual(app_json.read_text(encoding='utf-8'), '{not json')

    def test_non_object_json_is_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            working, app_json = make_layout(tmp, 'v3.8.14')
            app_json.write_text('["v3.8.14"]', encoding='utf-8')
            self.assertEqual(restore.sync_app_version(working, 'STAMP', True), 0)
            self.assertEqual(app_json.read_text(encoding='utf-8'), '["v3.8.14"]')


if __name__ == '__main__':
    unittest.main()
