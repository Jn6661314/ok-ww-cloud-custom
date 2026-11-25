"""MuMu 按编队识别队伍 / 自动战斗兼容测试 (v1.5.8).

v1.5.7 让 MuMu 能打起来, 但还会"打着打着不打了":
  1) in_team_android() 固定返回 2 人队伍、当前角色默认 1 号位; 实际截图里
     右上角有两个非出战徽章 1/2, 说明是 3 人队且当前是 3 号位。
     load_chars() 因此把 chars 截成 2 个, 第三个角色和工坊编队代码永远不加载。
  2) MuMu 键位映射的"切换角色N"提示可能和编队槽位倒序(实测槽位1按 2 键),
     原代码固定 send_key(index+1) 会切到错误角色。
  3) 上游 AutoCombatTask 直接 get_current_char().perform(), 角色对象短暂为空时
     抛 AttributeError, TaskExecutor 会把触发任务 disable —— 自动战斗自己关掉。
  4) 手游血条闪烁时没有云游戏那样的宽限, 容易误判战斗结束。

本测试用桩验证编队识别、切人键映射、自动战斗 None 守卫和血条宽限。
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

from src.task.BaseWWTask import (  # noqa: E402
    BaseWWTask, ANDROID_PARTY_BADGE_RE, ANDROID_SWITCH_LABEL_RE,
)
from src.task import android_world  # noqa: E402


OcrBox = lambda name, y: SimpleNamespace(name=name, y=y, height=30, x=1700, width=40)


class PartyTask(BaseWWTask):
    @property
    def width(self):
        return 1920

    @property
    def height(self):
        return 1080

    def __init__(self, badges=(), labels=(), adb=True, current_index=0):
        self._adb = adb
        self._badges = badges
        self._labels = labels
        self._android_current_index = current_index
        self._android_party_scan_ready = False
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

    def box_of_screen(self, *args, **kwargs):
        return SimpleNamespace(x=0, y=0, width=1920, height=1080)

    def ocr(self, box=None, match=None, **kwargs):
        if match is ANDROID_PARTY_BADGE_RE or match == ANDROID_PARTY_BADGE_RE:
            return [OcrBox(name, y) for name, y in self._badges]
        if match is ANDROID_SWITCH_LABEL_RE or match == ANDROID_SWITCH_LABEL_RE:
            return [OcrBox(name, y) for name, y in self._labels]
        return []


class TestAndroidPartyBadges(unittest.TestCase):
    def test_two_badges_mean_three_member_team_and_slot3_active(self):
        fake = PartyTask(badges=[('1', 220), ('2', 320)])
        with patch.object(android_world, 'in_android_world', return_value=(True, 'radar')):
            in_team, index, size = BaseWWTask.in_team_android(fake)
        self.assertTrue(in_team)
        self.assertEqual(size, 3, '两个非出战徽章表示完整三人编队')
        self.assertEqual(index, 2, '徽章 1/2 都在时当前是 3 号位')

    def test_missing_badge_decides_current_slot(self):
        fake = PartyTask(badges=[('1', 220), ('3', 420)])
        with patch.object(android_world, 'in_android_world', return_value=(True, 'radar')):
            _, index, size = BaseWWTask.in_team_android(fake)
        self.assertEqual(size, 3)
        self.assertEqual(index, 1, '缺 2 号徽章说明当前是 2 号位')

    def test_no_badge_keeps_full_team_and_logical_index(self):
        fake = PartyTask(current_index=2)
        with patch.object(android_world, 'in_android_world', return_value=(True, 'radar')):
            _, index, size = BaseWWTask.in_team_android(fake)
        self.assertEqual(size, 3, 'OCR 读不到时仍按完整编队加载, 不能退回 2 人')
        self.assertEqual(index, 2, 'OCR 读不到时保留脚本维护的下标')

    def test_switch_keys_follow_keymap_labels(self):
        fake = PartyTask(
            badges=[('1', 220), ('2', 320)],
            labels=[('切换角色2', 255), ('切换角色1', 355)],
        )
        badges, key_map = BaseWWTask._read_android_party_badges(fake)
        self.assertEqual(badges, {0, 1})
        self.assertEqual(key_map[0], '2', '徽章 1 旁边的提示是按 2 键')
        self.assertEqual(key_map[1], '1', '徽章 2 旁边的提示是按 1 键')
        self.assertEqual(BaseWWTask.android_switch_key(fake, 0), '2')
        self.assertEqual(BaseWWTask.android_switch_key(fake, 1), '1')
        # 当前是 1 号位(默认 current_index=0), 切 3 号位: 另一个队友(2 号位)
        # 已确认用 1 键, 剩下那颗 2 键必然归 3 号位 —— 不再发不存在的 3 键。
        self.assertEqual(BaseWWTask.android_switch_key(fake, 2), '2')

    def test_pc_switch_key_unchanged(self):
        fake = PartyTask(adb=False, badges=[('1', 220), ('2', 320)])
        self.assertEqual(BaseWWTask.android_switch_key(fake, 0), '1')
        self.assertEqual(BaseWWTask.android_switch_key(fake, 2), '3')


class TestCombatMuMuCompatibility(unittest.TestCase):
    repo = Path(__file__).resolve().parent.parent

    def test_switch_next_char_uses_android_switch_key(self):
        src = (self.repo / 'src/task/BaseCombatTask.py').read_text(encoding='utf-8')
        self.assertIn('self.android_switch_key(switch_to.index, exclude=tried_keys)', src)
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
