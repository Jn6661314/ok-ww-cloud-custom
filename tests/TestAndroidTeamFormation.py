"""MuMu 编队识别 / 自动战斗兼容测试 (v1.5.12).

v1.5.8 曾用队伍栏徽章 OCR 识别编队, v1.5.12 按用户要求改为:
  - 队伍识别以配置的编队为准, 战斗期间不做画面 OCR
    (战斗特效/伤害数字会干扰徽章识别, 造成误判)。
  - 当前角色 = 脚本维护的逻辑下标, 队伍人数按编队 (android_team_size)。

同时保留回归:
  - MuMu 键位映射只有 1/2 两颗切换键, 任何情况不能发 3 键。
  - AutoCombatTask None 守卫与异常捕获 (触发任务不能被 disable)。
  - 安卓血条闪烁宽限。
"""
import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

WORK = r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working"
os.chdir(WORK)
sys.path.insert(0, WORK)

from src.task.BaseWWTask import BaseWWTask  # noqa: E402
from src.task import android_world  # noqa: E402


class PartyTask(BaseWWTask):
    @property
    def width(self):
        return 1920

    @property
    def height(self):
        return 1080

    def __init__(self, adb=True, current_index=0, chars=()):
        self._adb = adb
        self._android_current_index = current_index
        self.chars = list(chars)
        self.logged_in = False
        self.logs = []
        self._executor = SimpleNamespace(nullable_frame=lambda: object())

    @property
    def logged_in(self):
        return self._logged_in

    @logged_in.setter
    def logged_in(self, value):
        self._logged_in = value

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


class TestFormationBasedTeam(unittest.TestCase):
    def test_full_team_default_current_kept(self):
        fake = PartyTask(current_index=2)
        with patch.object(android_world, 'in_android_world', return_value=(True, 'radar')):
            in_team, index, size = BaseWWTask.in_team_android(fake)
        self.assertTrue(in_team)
        self.assertEqual(size, 3, '默认按完整三人编队加载')
        self.assertEqual(index, 2, '当前角色 = 脚本维护的逻辑下标')

    def test_team_size_follows_loaded_chars(self):
        fake = PartyTask(current_index=1, chars=[object(), object()])
        with patch.object(android_world, 'in_android_world', return_value=(True, 'radar')):
            _, _, size = BaseWWTask.in_team_android(fake)
        self.assertEqual(size, 2, '编队加载出两人就是两人队')

    def test_bad_logical_index_clamped(self):
        fake = PartyTask(current_index=-5)
        with patch.object(android_world, 'in_android_world', return_value=(True, 'radar')):
            _, index, _ = BaseWWTask.in_team_android(fake)
        self.assertEqual(index, 0)

    def test_not_in_world_returns_not_in_team(self):
        fake = PartyTask(current_index=0)
        with patch.object(android_world, 'in_android_world', return_value=(False, 'menu')):
            in_team, index, _ = BaseWWTask.in_team_android(fake)
        self.assertFalse(in_team)
        self.assertEqual(index, -1)

    def test_black_frame_logged_as_warning(self):
        fake = PartyTask(current_index=0)
        with patch.object(android_world, 'in_android_world', return_value=(False, 'black_frame')):
            in_team, _, _ = BaseWWTask.in_team_android(fake)
        self.assertFalse(in_team)
        self.assertTrue(any(kind == 'warning' for kind, _ in fake.logs),
                        'MuMu 黑帧必须显式告警, 不能静默当成"不在大世界"')


class TestCombatMuMuCompatibility(unittest.TestCase):
    repo = Path(__file__).resolve().parent.parent

    def test_switch_next_char_uses_android_switch_key(self):
        src = (self.repo / 'src/task/BaseCombatTask.py').read_text(encoding='utf-8')
        self.assertIn('self.android_switch_key(switch_to.index', src)
        self.assertIn('switch_to.index + 1', src, 'PC/云仍保留原约定')

    def test_auto_combat_guards_none_and_exceptions(self):
        src = (self.repo / 'src/task/AutoCombatTask.py').read_text(encoding='utf-8')
        self.assertIn('def _current_char_for_perform(self):', src)
        self.assertIn('if current_char is None:', src)
        self.assertIn('except Exception as e:', src, '触发任务不能因单帧异常被 disable')
        self.assertIn("self.reset_auto_combat('auto combat perform failed')", src)

    def test_auto_combat_task_is_deployed(self):
        src = (self.repo / 'restore.py').read_text(encoding='utf-8')
        self.assertIn("'src/task/AutoCombatTask.py'", src)

    def test_health_bar_grace_covers_adb(self):
        src = (self.repo / 'src/combat/CombatCheck.py').read_text(encoding='utf-8')
        self.assertIn('(self.is_browser() or self.is_adb()) and self.cloud_health_bar_grace', src)


if __name__ == '__main__':
    unittest.main(verbosity=2)
