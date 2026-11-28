"""手机投屏的键位映射: 默认表、读写、以及「按键变成触点」这条链路。

为什么要测这些:

  * 手游(鸣潮)不认按键事件, 只认触点。MuMu 上 send_key('e') 能生效是靠模拟器
    自带的键位映射; 真机没有这一层。所以投屏下必须由 ok-ww 自己把键翻译成
    那个位置的触摸 —— 翻译表错了/读不出来, 表现就是"技能没反应, 只能手点屏幕"。
  * 返回/菜单更严重: 发 esc 过去, 手游收到的是 KEYCODE_BACK, 直接弹"是否退出
    游戏"。所以投屏也必须算"触屏"(TouchMode.is_touch), 走键位表的 ` 键。
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

CONFIG_DIR = tempfile.mkdtemp(prefix='okww-keymap-')
# 键位表写到临时目录, 别动用户真实的 configs; 模块跑完要恢复环境变量,
# 否则同一个进程里后面的测试会跟着写到临时目录去。
_OLD_CONFIG_DIR = os.environ.get('OKWW_CONFIG_DIR')
os.environ['OKWW_CONFIG_DIR'] = CONFIG_DIR

from src import phone_mirror_keymap as keymap  # noqa: E402
from ok.device.interaction_methods.phone_mirror import PhoneMirrorInteraction  # noqa: E402
from ok.device.capture_methods.phone_mirror_socket import TOUCH_DOWN, TOUCH_UP  # noqa: E402
from src.task.touch_mode import TouchMode  # noqa: E402


class FakeCapture:
    """只记录发出去的输入, 不需要真的 socket。"""

    def __init__(self):
        self.touches = []
        self.keys = []

    def normalize_point(self, x, y):
        return (x / 1000.0, y / 1000.0)

    def send_touch(self, action, x, y):
        self.touches.append((action, round(x, 3), round(y, 3)))
        return True

    def send_key(self, key):
        self.keys.append(key)
        # 和真实现一致: 只有特殊键才有对应码。
        return str(key).lower() in ('back', 'home', 'enter')


class FakeTask:
    """TouchMode 只用到 is_adb()、executor.interaction、send_key/click_relative。"""

    def __init__(self, interaction):
        self.executor = type('Executor', (), {'interaction': interaction})()
        self._interaction = interaction
        self.sent_keys = []
        self.clicked = []

    def is_adb(self):
        return True

    def send_key(self, key, after_sleep=0):
        self.sent_keys.append(key)
        return self._interaction.send_key(key)

    def click_relative(self, x, y, **kwargs):
        self.clicked.append((x, y))
        return True


class KeymapTest(unittest.TestCase):

    def setUp(self):
        path = keymap.keymap_path()
        if os.path.exists(path):
            os.remove(path)
        keymap._cache['mtime'] = None
        keymap._cache['map'] = None

    def tearDown(self):
        path = keymap.keymap_path()
        if os.path.exists(path):
            os.remove(path)

    def test_the_menu_back_key_is_mapped_out_of_the_box(self):
        # 没校准过也要能用: 返回/菜单的位置是固定的(左上角), 而且在战斗外
        # 每一步都要用它 —— 这条不通, 整条任务链都卡住。
        point = keymap.lookup('`')
        self.assertIsNotNone(point)
        self.assertLess(point[0], 0.2)
        self.assertLess(point[1], 0.2)

    def test_esc_points_at_the_same_button(self):
        # 手游里返回和打开菜单是同一个按钮, 别名不该指到别处去。
        self.assertEqual(keymap.lookup('esc'), keymap.lookup('`'))
        self.assertEqual(keymap.lookup('escape'), keymap.lookup('`'))

    def test_a_calibrated_point_wins_over_the_default(self):
        self.assertTrue(keymap.save({'`': (0.11, 0.09)}))
        self.assertAlmostEqual(keymap.lookup('`')[0], 0.11, places=4)
        self.assertAlmostEqual(keymap.lookup('`')[1], 0.09, places=4)

    def test_aliases_are_written_once(self):
        self.assertTrue(keymap.save({'esc': (0.2, 0.2), '`': (0.3, 0.3)}))
        with open(keymap.keymap_path(), 'r', encoding='utf-8') as f:
            saved = json.load(f)
        self.assertIn('`', saved)
        self.assertNotIn('esc', saved)

    def test_impossible_points_are_dropped(self):
        # 比例必须在 0..1: 超范围的坐标是笔误, 存进去会让点击飞到屏幕外。
        self.assertTrue(keymap.save({'e': (1.4, 0.5), 'r': (0.5, -0.1)}))
        self.assertIsNone(keymap.lookup('e'))
        self.assertIsNone(keymap.lookup('r'))

    def test_saving_keeps_what_was_already_there(self):
        keymap.save({'e': (0.8, 0.65)})
        mapping = dict(keymap.load())
        mapping['1'] = (0.96, 0.3)
        keymap.save(mapping)
        self.assertIsNotNone(keymap.lookup('e'), '先校准的键被覆盖掉了')
        self.assertIsNotNone(keymap.lookup('1'))

    def test_a_broken_file_does_not_break_lookup(self):
        with open(keymap.keymap_path(), 'w', encoding='utf-8') as f:
            f.write('{ 这不是 JSON')
        keymap._cache['mtime'] = None
        keymap._cache['map'] = None
        self.assertIsNotNone(keymap.lookup('`'), '文件坏了也要退回默认表')

    def test_f2_and_f_break_are_calibrated_independently(self):
        # 三个都是手游里不同的按钮: 交互 F / 斩杀 / 索拉指南。
        self.assertTrue(keymap.save({'f': (0.80, 0.65),
                                     'f_break': (0.51, 0.42),
                                     'f2': (0.73, 0.06)}))
        self.assertEqual(keymap.lookup('f'), (0.80, 0.65))
        self.assertEqual(keymap.lookup('f_break'), (0.51, 0.42))
        self.assertEqual(keymap.lookup('f2'), (0.73, 0.06))
        keys = dict(keymap.CALIBRATION_KEYS)
        self.assertEqual(keys['f'], '交互 F')
        self.assertIn('斩杀', keys['f_break'])
        self.assertIn('F2', keys['f2'])

    def test_break_aliases_never_overwrite_interact_f(self):
        self.assertTrue(keymap.save({'f': (0.8, 0.65), '斩杀': (0.5, 0.4)}))
        with open(keymap.keymap_path(), 'r', encoding='utf-8') as f:
            saved = json.load(f)
        self.assertNotIn('斩杀', saved)
        self.assertEqual(keymap.lookup('f'), (0.8, 0.65))
        self.assertEqual(keymap.lookup('f_break'), (0.5, 0.4))
        self.assertEqual(keymap.lookup('fbreak'), (0.5, 0.4))


class InteractionTest(unittest.TestCase):

    def setUp(self):
        path = keymap.keymap_path()
        if os.path.exists(path):
            os.remove(path)
        keymap._cache['mtime'] = None
        keymap._cache['map'] = None
        keymap.save({'e': (0.8, 0.65), '1': (0.96, 0.3)})
        self.capture = FakeCapture()
        self.interaction = PhoneMirrorInteraction(self.capture)

    def tearDown(self):
        path = keymap.keymap_path()
        if os.path.exists(path):
            os.remove(path)

    def test_a_mapped_key_is_sent_as_a_touch(self):
        # 这是这版的核心: 技能键必须是"那个位置按一下", 不是按键事件。
        self.assertTrue(self.interaction.send_key('e', down_time=0.01))
        self.assertEqual([t[0] for t in self.capture.touches], [TOUCH_DOWN, TOUCH_UP])
        self.assertAlmostEqual(self.capture.touches[0][1], 0.8, places=3)
        self.assertAlmostEqual(self.capture.touches[0][2], 0.65, places=3)
        self.assertEqual(self.capture.keys, [], '映射过的键不该再发按键事件')

    def test_the_menu_back_key_goes_through_the_map(self):
        self.assertTrue(self.interaction.send_key('`', down_time=0.01))
        self.assertEqual(len(self.capture.touches), 2)
        self.assertEqual(self.capture.keys, [])

    def test_an_unmapped_key_falls_back_to_the_phone_key(self):
        # 没有映射的键仍然可以走手机按键(back/home/enter 这类系统键)。
        self.interaction.send_key('back', down_time=0.01)
        self.assertEqual(self.capture.keys, ['back'])
        self.assertEqual(self.capture.touches, [])

    def test_a_key_with_neither_map_nor_code_is_reported_as_unhandled(self):
        self.assertFalse(self.interaction.send_key('f12', down_time=0.01))

    def test_f_break_and_f2_are_separate_touches(self):
        keymap.save({'f': (0.8, 0.65), 'f_break': (0.5, 0.4), 'f2': (0.7, 0.06)})
        capture = FakeCapture()
        interaction = PhoneMirrorInteraction(capture)
        for key in ('f', 'f_break', 'f2'):
            self.assertTrue(interaction.send_key(key, down_time=0.01))
        taps = [t for t in capture.touches if t[0] == TOUCH_DOWN]
        self.assertEqual([(t[1], t[2]) for t in taps],
                         [(0.8, 0.65), (0.5, 0.4), (0.7, 0.06)])


class TouchModeTest(unittest.TestCase):

    def setUp(self):
        path = keymap.keymap_path()
        if os.path.exists(path):
            os.remove(path)
        keymap._cache['mtime'] = None
        keymap._cache['map'] = None

    def tearDown(self):
        path = keymap.keymap_path()
        if os.path.exists(path):
            os.remove(path)

    def test_mirroring_counts_as_touch(self):
        # 投屏下 back() 必须走键位表的 `, 而不是 esc: 手游收到 esc 会弹
        # "是否确定退出游戏", 那就不是"返回"而是"要退游戏"了。
        capture = FakeCapture()
        interaction = PhoneMirrorInteraction(capture)
        touch = TouchMode(FakeTask(interaction))
        self.assertTrue(touch.is_touch, '投屏没被当成触屏')
        touch.back()
        self.assertEqual(len(capture.touches), 2)
        self.assertEqual(capture.keys, [])

    def test_calibrated_f2_point_is_used_for_guidebook(self):
        keymap.save({'f2': (0.31, 0.12)})
        capture = FakeCapture()
        task = FakeTask(PhoneMirrorInteraction(capture))
        touch = TouchMode(task)
        self.assertTrue(touch.is_phone_mirror)
        self.assertTrue(touch.open_book())
        self.assertEqual(task.sent_keys, ['f2'])
        self.assertEqual(task.clicked, [], '校准后不该再点默认图标')
        self.assertEqual([(t[1], t[2]) for t in capture.touches if t[0] == TOUCH_DOWN],
                         [(0.31, 0.12)])

    def test_uncalibrated_f2_keeps_the_default_icon(self):
        capture = FakeCapture()
        task = FakeTask(PhoneMirrorInteraction(capture))
        touch = TouchMode(task)
        self.assertIsNone(touch.mapped_key('f2'))
        self.assertTrue(touch.open_book())
        self.assertEqual(task.sent_keys, [])
        self.assertEqual(len(task.clicked), 1)


class BreakKeyTest(unittest.TestCase):
    """斩杀与交互 F 必须独立: 斩杀点不能抢交互 F 的触点。"""

    def setUp(self):
        path = keymap.keymap_path()
        if os.path.exists(path):
            os.remove(path)
        keymap._cache['mtime'] = None
        keymap._cache['map'] = None

    def tearDown(self):
        path = keymap.keymap_path()
        if os.path.exists(path):
            os.remove(path)

    def _fake_check(self, task):
        fake = type('BreakCheck', (), {})()
        fake.can_break = True
        fake.touch = TouchMode(task)
        fake.sent = []
        fake.clicked = []
        fake.check_f_break = lambda: False
        fake.is_adb = lambda: True

        def send_key(key, after_sleep=0):
            fake.sent.append(key)
            return task.send_key(key)

        fake.send_key = send_key
        fake.click = lambda *args, **kwargs: fake.clicked.append((args, kwargs))
        return fake

    def test_calibrated_break_point_is_used(self):
        from src.combat.CombatCheck import CombatCheck
        keymap.save({'f': (0.8, 0.65), 'f_break': (0.52, 0.44)})
        capture = FakeCapture()
        fake = self._fake_check(FakeTask(PhoneMirrorInteraction(capture)))
        CombatCheck.f_break(fake)
        self.assertTrue(fake.sent, '斩杀没有发出任何触点')
        self.assertTrue(all(key == 'f_break' for key in fake.sent))
        self.assertNotIn('f', fake.sent, '斩杀用了交互 F 的键')
        self.assertEqual(fake.clicked, [])
        self.assertEqual([(t[1], t[2]) for t in capture.touches if t[0] == TOUCH_DOWN][0],
                         (0.52, 0.44))

    def test_without_calibration_the_original_adb_path_stays(self):
        from src.combat.CombatCheck import CombatCheck
        fake = self._fake_check(FakeTask(PhoneMirrorInteraction(FakeCapture())))
        fake._f_break_box = type('Box', (), {'center': lambda self: (0.6, 0.5)})()
        CombatCheck.f_break(fake)
        self.assertEqual(fake.sent, [], '没校准却发了语义键, PC/MuMu 会不认识')
        self.assertTrue(fake.clicked, '没校准时应维持点提示位置的老逻辑')


class BattlePassTouchTest(unittest.TestCase):
    """先约电台: PC 要按住 Alt 才显示入口, 手游没有 Alt, 只能点校准出来的触点。"""

    def setUp(self):
        path = keymap.keymap_path()
        if os.path.exists(path):
            os.remove(path)
        keymap._cache['mtime'] = None
        keymap._cache['map'] = None

    def tearDown(self):
        path = keymap.keymap_path()
        if os.path.exists(path):
            os.remove(path)

    def _task(self):
        from src.task.DailyTask import DailyTask
        task = FakeTask(PhoneMirrorInteraction(FakeCapture()))
        task.touch = TouchMode(task)
        task.is_browser = lambda: False
        task.sleep = lambda *a, **k: None
        task.back = lambda **k: None
        task.ocr = lambda *a, **k: []
        task.log_debug = lambda *a, **k: None
        return DailyTask, task

    def test_battle_pass_aliases_share_one_point(self):
        self.assertEqual(keymap.normalize_key('先约电台'), 'battle_pass')
        self.assertEqual(keymap.normalize_key('battlepass'), 'battle_pass')
        self.assertEqual(keymap.normalize_key('bp'), 'battle_pass')
        self.assertIn('先约电台', dict(keymap.CALIBRATION_KEYS)['battle_pass'])

    def test_calibrated_battle_pass_point_is_clicked_first(self):
        keymap.save({'battle_pass': (0.62, 0.11)})
        DailyTask, task = self._task()
        task._battle_pass_opened = lambda: True

        DailyTask._open_battle_pass(task)

        self.assertEqual(task.sent_keys, ['battle_pass'])
        self.assertEqual(task.clicked, [], '校准后不该再点右上角候选位置')
        taps = [(t[1], t[2]) for t in task._interaction.capture.touches if t[0] == TOUCH_DOWN]
        self.assertEqual(taps, [(0.62, 0.11)])

    def test_phone_mirror_never_sends_alt(self):
        # 投屏手机端没有 Alt 这个键, 发它只会让右上角图标一直不出现。
        DailyTask, task = self._task()
        task._battle_pass_opened = lambda: False
        task.send_key_down = lambda *a, **k: self.fail('投屏不该发 alt')
        task.send_key_up = lambda *a, **k: self.fail('投屏不该发 alt')

        DailyTask._open_battle_pass(task)

        self.assertEqual(task.sent_keys, [])
        self.assertTrue(task.clicked, '没校准时应该退到点右上角候选位置')


def tearDownModule():
    shutil.rmtree(CONFIG_DIR, ignore_errors=True)
    if _OLD_CONFIG_DIR is None:
        os.environ.pop('OKWW_CONFIG_DIR', None)
    else:
        os.environ['OKWW_CONFIG_DIR'] = _OLD_CONFIG_DIR

if __name__ == '__main__':
    unittest.main()
