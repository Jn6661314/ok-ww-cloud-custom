"""MuMu/安卓端自动战斗修复测试.

修复背景: 安卓队伍栏是圆形头像, PC 的 char_N_text 数字徽章模板匹配不上,
in_team_android() 原先恒返回 current_index=-1, 导致:
  - load_chars() 没有任何角色 index 能匹配 -1 -> is_current_char 全 False
  - get_current_char() 返回 None -> combat_once() 的 .perform() / refresh_cd()
    的 .index 抛 AttributeError -> 战斗刚进入就崩溃 ("MuMu 无法自动战斗")
  - switch_next_char() 靠 current_index == switch_to.index 判定切人成功,
    恒 -1 还会让切人等 10 秒后抛 raise_not_in_combat

本测试验证:
1. in_team_android() 返回 0..2 的逻辑下标, 且可被外部推进, 不再是 -1。
2. get_current_char() 安卓端在 is_current_char 全 False 时按逻辑下标兜底,
   不再返回 None; PC 端行为不变(仍返回 None)。
3. refresh_cd() / get_cd() 在当前角色缺失时安全返回, 不抛 AttributeError。
4. switch_next_char() 安卓端发出切人键后推进逻辑下标(源码断言, 因为完整
   切人循环需要真实帧/按键通道)。
"""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

WORK = r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working"
os.chdir(WORK)
sys.path.insert(0, WORK)

from src.task.BaseWWTask import BaseWWTask
from src.task.BaseCombatTask import BaseCombatTask
from src.task import android_world


class FakeTask:
    """Minimal task double carrying only what the patched methods touch."""

    def __init__(self, adb=True, frame=None):
        self._adb = adb
        self._frame = frame
        self.chars = [None, None, None]
        self.logged_in = False
        self.logs = []
        self._android_current_index = 0
        self.scene = SimpleNamespace(cd_refreshed=False)
        self.cds = {}
        self.executor = SimpleNamespace(nullable_frame=lambda: self._frame)

    def is_adb(self):
        return self._adb

    def is_browser(self):
        return False

    def log_debug(self, msg):
        self.logs.append(('debug', msg))

    def log_warning(self, msg):
        self.logs.append(('warning', msg))

    def tr(self, text):
        return text

    def get_current_char(self, raise_exception=False):
        return BaseCombatTask.get_current_char(self, raise_exception)

    def refresh_cd(self):
        return BaseCombatTask.refresh_cd(self)


class TestInTeamAndroid(unittest.TestCase):
    def test_returns_logical_index_not_minus_one(self):
        fake = FakeTask(frame=object())
        with patch.object(android_world, 'in_android_world', return_value=(True, 'radar_yellow=100')):
            in_team, index, count = BaseWWTask.in_team_android(fake)
        self.assertTrue(in_team)
        self.assertNotEqual(index, -1, 'c0: 当前角色下标不能是 -1')
        self.assertTrue(0 <= index < 3)
        self.assertEqual(count, 2)
        self.assertTrue(fake.logged_in)

    def test_preserves_advanced_logical_index(self):
        fake = FakeTask(frame=object())
        fake._android_current_index = 2
        with patch.object(android_world, 'in_android_world', return_value=(True, 'hp_bar_white=3000')):
            _, index, _ = BaseWWTask.in_team_android(fake)
        self.assertEqual(index, 2, 'c1: 已推进的逻辑下标必须被保留')

    def test_clamps_out_of_range_index(self):
        fake = FakeTask(frame=object())
        fake._android_current_index = 99
        with patch.object(android_world, 'in_android_world', return_value=(True, 'ok')):
            _, index, _ = BaseWWTask.in_team_android(fake)
        self.assertEqual(index, 0, 'c2: 越界下标必须回落到 0')

    def test_black_frame_returns_false(self):
        fake = FakeTask(frame=object())
        with patch.object(android_world, 'in_android_world', return_value=(False, 'black_frame')):
            in_team, index, count = BaseWWTask.in_team_android(fake)
        self.assertFalse(in_team)
        self.assertEqual(index, -1)
        self.assertTrue(any(w == 'warning' for w, _ in fake.logs), 'c3: 黑帧必须打 warning')


class TestGetCurrentChar(unittest.TestCase):
    def test_android_fallback_by_logical_index(self):
        fake = FakeTask(adb=True)
        c0 = SimpleNamespace(is_current_char=False, index=0)
        c1 = SimpleNamespace(is_current_char=False, index=1)
        fake.chars = [c0, c1, None]
        fake._android_current_index = 1
        got = BaseCombatTask.get_current_char(fake)
        self.assertIs(got, c1, 'c4: 安卓端应按逻辑下标兜底')
        self.assertTrue(c1.is_current_char, 'c5: 兜底后应标记为当前角色')

    def test_android_fallback_first_non_none(self):
        fake = FakeTask(adb=True)
        c0 = SimpleNamespace(is_current_char=False, index=0)
        fake.chars = [None, c0, None]
        fake._android_current_index = 2  # 越界, 应回落到第一个非空
        got = BaseCombatTask.get_current_char(fake)
        self.assertIs(got, c0, 'c6: 逻辑下标越界时回落到第一个非空角色')

    def test_pc_behavior_unchanged(self):
        fake = FakeTask(adb=False)
        c0 = SimpleNamespace(is_current_char=False, index=0)
        fake.chars = [c0, None, None]
        got = BaseCombatTask.get_current_char(fake)
        self.assertIsNone(got, 'c7: PC 端无当前角色时仍返回 None (行为不变)')

    def test_existing_current_char_untouched(self):
        fake = FakeTask(adb=True)
        c0 = SimpleNamespace(is_current_char=False, index=0)
        c1 = SimpleNamespace(is_current_char=True, index=1)
        fake.chars = [c0, c1, None]
        fake._android_current_index = 0
        got = BaseCombatTask.get_current_char(fake)
        self.assertIs(got, c1, 'c8: 已有当前角色时优先返回, 不被兜底覆盖')


class TestCdSafety(unittest.TestCase):
    def test_refresh_cd_no_current_char(self):
        fake = FakeTask(adb=True)
        fake.chars = [None, None, None]
        fake._android_current_index = 0
        # refresh_cd 内部 get_current_char 返回 None 时应直接返回, 不读 .index
        ret = BaseCombatTask.refresh_cd(fake)
        self.assertIsNone(ret, 'c9: 无当前角色时 refresh_cd 应安全跳过')
        self.assertFalse(fake.scene.cd_refreshed)

    def test_get_cd_no_current_char(self):
        fake = FakeTask(adb=True)
        fake.chars = [None, None, None]
        # get_cd 调用 self.refresh_cd -> fake 的实现; 再 get_current_char -> None
        ret = BaseCombatTask.get_cd(fake, 'resonance')
        self.assertEqual(ret, 0, 'c10: 无当前角色时 get_cd 应返回 0, 不抛 AttributeError')


class TestSourceGuards(unittest.TestCase):
    """对完整切人循环做源码级断言(运行时需要真实帧与按键通道, 不便在单测中构造)。"""

    @classmethod
    def setUpClass(cls):
        with open(os.path.join(WORK, 'src', 'task', 'BaseCombatTask.py'), encoding='utf-8') as f:
            cls.src = f.read()
        with open(os.path.join(WORK, 'src', 'task', 'BaseWWTask.py'), encoding='utf-8') as f:
            cls.wwsrc = f.read()

    def test_switch_syncs_android_index(self):
        self.assertIn('self._android_current_index = switch_to.index', self.src,
                      'c11: 切人后必须同步安卓逻辑下标')

    def test_combat_once_has_none_guard(self):
        self.assertIn('if current_char is None:', self.src,
                      'c12: combat_once 必须有当前角色缺失保护')

    def test_in_team_android_uses_logical_index(self):
        self.assertIn('return True, current_index, 2', self.wwsrc,
                      'c13: in_team_android 必须返回逻辑下标而非 -1')


if __name__ == '__main__':
    unittest.main(verbosity=2)
