"""手机投屏配置迁移: 两个旧菜单合成一个「手机投屏」。

背景:
  以前 ok-ww 里有两个手机投屏菜单:
    * 「手机投屏(NectarLink)」—— 走外部 NectarLink 桌面端的投屏窗口;
    * 「手机投屏(内置引擎)」—— 走 ok-ww 自带的投屏内核。
  两者功能重叠, 合成一个「手机投屏」, 里面用「模式」下拉切换。

关键点:
  框架里 ConfigOption 的**名字就是配置文件名**(configs/<名字>.json), 所以改名
  等于换了文件, 用户原来设的值(Enable、画面宽度...)会"消失"。src/phone_mirror_config
  在应用启动最早期做一次迁移, 把旧文件的内容并进新文件。

覆盖:
  1. 旧配置(引擎那份)会合成到新文件, Enable 等设置不丢;
  2. 模式按旧配置推断;
  3. 新文件已存在时以新文件为准, 不覆盖;
  4. 旧文件迁移后被清掉;
  5. 桌面端那份旧配置也能单独迁移。
"""

import json
import os
import shutil
import sys
import tempfile
import unittest

WORK = os.environ.get('OKWW_WORK', r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working")
os.chdir(WORK)
sys.path.insert(0, WORK)

from src import phone_mirror_config  # noqa: E402


class MigrationTestBase(unittest.TestCase):
    """每个用例一个独立的配置目录。"""

    def setUp(self):
        self.tmp = tempfile.mkdtemp(prefix='phone-mirror-config-')
        self.addCleanup(shutil.rmtree, self.tmp, True)
        # 模块用的是环境变量决定配置目录, 这里临时改一下。
        old = os.environ.get('OKWW_CONFIG_DIR')
        os.environ['OKWW_CONFIG_DIR'] = self.tmp
        # 迁移只在真正启动时跑(不该动用户真实配置), 测试里强制打开。
        forced = os.environ.get('OKWW_FORCE_MIGRATION')
        os.environ['OKWW_FORCE_MIGRATION'] = '1'

        def restore():
            if old is None:
                os.environ.pop('OKWW_CONFIG_DIR', None)
            else:
                os.environ['OKWW_CONFIG_DIR'] = old
            if forced is None:
                os.environ.pop('OKWW_FORCE_MIGRATION', None)
            else:
                os.environ['OKWW_FORCE_MIGRATION'] = forced

        self.addCleanup(restore)

    def write_old(self, name, data):
        with open(os.path.join(self.tmp, f'{name}.json'), 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)

    def read_new(self):
        path = os.path.join(self.tmp, '手机投屏.json')
        if not os.path.exists(path):
            return None
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)

    def exists(self, name):
        return os.path.exists(os.path.join(self.tmp, f'{name}.json'))


class MergeTest(MigrationTestBase):

    def test_engine_config_carries_over(self):
        """旧引擎配置的设置必须并进新文件, 不能丢。"""
        self.write_old('手机投屏(内置引擎)', {
            'Enable': True,
            '手机': 'Pixel 9',
            '画面宽度': '2560',
            '帧率': '60',
            '码率': '12000000',
        })
        self.assertTrue(phone_mirror_config.migrate_phone_mirror_config(verbose=False))
        new = self.read_new()
        self.assertIsNotNone(new, '新配置文件应该被创建')
        self.assertTrue(new['Enable'], 'Enable 必须保留')
        self.assertEqual(new['手机'], 'Pixel 9')
        self.assertEqual(new['画面宽度'], '2560')
        self.assertEqual(new['帧率'], '60')
        self.assertEqual(new['码率'], '12000000')

    def test_mode_defaults_to_engine_when_enabled(self):
        """引擎开着就选内置引擎模式。"""
        self.write_old('手机投屏(内置引擎)', {'Enable': True})
        phone_mirror_config.migrate_phone_mirror_config(verbose=False)
        self.assertEqual(self.read_new()['模式'], '内置引擎')

    def test_mode_defaults_to_desktop_when_only_desktop_config(self):
        """只有桌面端那份旧配置时选桌面端模式。"""
        self.write_old('手机投屏(NectarLink)', {
            '下载手机端': '',
            '手机端下载地址': 'https://example.com/apk',
        })
        phone_mirror_config.migrate_phone_mirror_config(verbose=False)
        new = self.read_new()
        self.assertEqual(new['模式'], '桌面端')
        self.assertEqual(new['手机端下载地址'], 'https://example.com/apk')

    def test_engine_takes_precedence_over_desktop(self):
        """两份都有时, 引擎那份的设置优先(它的键更多)。"""
        self.write_old('手机投屏(内置引擎)', {'Enable': True, '画面宽度': '1600'})
        self.write_old('手机投屏(NectarLink)', {'画面宽度': '1280',
                                                '手机端下载地址': 'https://example.com/apk'})
        phone_mirror_config.migrate_phone_mirror_config(verbose=False)
        new = self.read_new()
        self.assertEqual(new['画面宽度'], '1600')
        self.assertEqual(new['手机端下载地址'], 'https://example.com/apk')

    def test_existing_new_config_is_not_overwritten(self):
        """新文件已存在时以新文件为准, 不覆盖用户改过的内容。"""
        self.write_old('手机投屏(内置引擎)', {'Enable': True, '画面宽度': '2560'})
        self.write_old('手机投屏', {'Enable': False, '画面宽度': '1280',
                                    '模式': '桌面端'})
        phone_mirror_config.migrate_phone_mirror_config(verbose=False)
        new = self.read_new()
        self.assertFalse(new['Enable'], '用户新配置不能被旧配置覆盖')
        self.assertEqual(new['画面宽度'], '1280')
        self.assertEqual(new['模式'], '桌面端')

    def test_old_files_are_removed(self):
        """旧文件迁移后清掉, 免得让人以为还有效。"""
        self.write_old('手机投屏(内置引擎)', {'Enable': True})
        self.write_old('手机投屏(NectarLink)', {'下载手机端': ''})
        phone_mirror_config.migrate_phone_mirror_config(verbose=False)
        self.assertFalse(self.exists('手机投屏(内置引擎)'))
        self.assertFalse(self.exists('手机投屏(NectarLink)'))

    def test_nothing_to_migrate(self):
        """两个旧文件都没有时, 不该凭空造出配置文件。"""
        self.assertFalse(phone_mirror_config.migrate_phone_mirror_config(verbose=False))
        self.assertIsNone(self.read_new())

    def test_migration_is_idempotent(self):
        """迁移跑两次不会出错, 也不会把设置改回去。"""
        self.write_old('手机投屏(内置引擎)', {'Enable': True, '画面宽度': '2560'})
        phone_mirror_config.migrate_phone_mirror_config(verbose=False)
        phone_mirror_config.migrate_phone_mirror_config(verbose=False)
        new = self.read_new()
        self.assertTrue(new['Enable'])
        self.assertEqual(new['画面宽度'], '2560')


class StartupGuardTest(MigrationTestBase):
    """迁移只在真正启动时跑 —— 测试导入 config 不该动用户真实配置。"""

    def setUp(self):
        super().setUp()
        # 模拟"不是正式启动": 关掉强制开关。
        os.environ.pop('OKWW_FORCE_MIGRATION', None)

    def test_not_migrated_outside_real_startup(self):
        self.write_old('手机投屏(内置引擎)', {'Enable': True})
        self.assertFalse(phone_mirror_config.migrate_phone_mirror_config(verbose=False))
        self.assertIsNone(self.read_new(), '非正式启动时不该迁移')
        self.assertTrue(self.exists('手机投屏(内置引擎)'), '旧文件也不该被删')

    def test_real_startup_is_detected_for_main_entry(self):
        argv0 = os.path.basename(sys.argv[0] if sys.argv else '').lower()
        # 测试环境下 argv0 不是 main.py, 所以这里只验证判断函数本身可用。
        self.assertIn(phone_mirror_config.is_real_startup(), (True, False))
        if argv0 not in ('main.py', 'main_debug.py'):
            self.assertFalse(phone_mirror_config.is_real_startup(),
                             '测试环境下不该判定为正式启动')


class ModeTest(unittest.TestCase):

    def test_mode_constants(self):
        self.assertEqual(phone_mirror_config.MODE_ENGINE, '内置引擎')
        self.assertEqual(phone_mirror_config.MODE_DESKTOP, '桌面端')

    def test_new_config_name(self):
        self.assertEqual(phone_mirror_config.NEW_MENU_NAME, '手机投屏')


if __name__ == '__main__':
    unittest.main()
