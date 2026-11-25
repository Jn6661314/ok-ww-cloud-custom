"""MuMu 切人键位测试 (v1.5.12: 以编队为准, 战斗中不做画面识别).

用户要求:
  - 队伍识别以配置的编队为准, 不在战斗期间做画面 OCR 识别
    (战斗特效/伤害数字会干扰队伍栏徽章识别)。
  - MuMu 键位映射只有 1/2 两颗切换键, 任何情况都不能发 3 键。

切人键映射按编队动态推导(实测出战 3 号位时: 键 1 -> 2 号位,
键 2 -> 1 号位): 键 1 -> 编队靠后的非出战队友。
"""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

WORK = r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working"
os.chdir(WORK)
sys.path.insert(0, WORK)

from src.task.BaseWWTask import BaseWWTask, ANDROID_SWITCH_KEYS  # noqa: E402
from src.task import android_world  # noqa: E402


class SwitchTask(BaseWWTask):
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


class TestNeverSendKey3(unittest.TestCase):
    """任何 (当前角色, 目标角色) 组合都不能发 3 键。"""

    def test_all_combats_never_3(self):
        for current in range(3):
            for target in range(3):
                if target == current:
                    continue
                fake = SwitchTask(current_index=current)
                key = BaseWWTask.android_switch_key(fake, target)
                self.assertIn(key, ANDROID_SWITCH_KEYS,
                              f'current={current + 1}, target={target + 1} 发了 {key} 键')

    def test_fallback_matches_measured_rule(self):
        # 实测规律: 出战 3 号位时键 1 切 2 号位(编队靠后的非出战队友)。
        fake = SwitchTask(current_index=2)
        self.assertEqual(BaseWWTask.android_switch_key(fake, 1), '1')
        self.assertEqual(BaseWWTask.android_switch_key(fake, 0), '2')

    def test_exclude_alternates_to_the_other_key(self):
        fake = SwitchTask(current_index=2)
        self.assertEqual(BaseWWTask.android_switch_key(fake, 0, exclude=('2',)), '1')
        self.assertEqual(BaseWWTask.android_switch_key(fake, 0, exclude=('2', '1')), '2',
                         '两颗都试过时仍要有确定返回值, 不能崩')

    def test_two_member_team(self):
        # 2 人编队: 当前 1 号位时切 2 号位, 只有一颗键可按。
        fake = SwitchTask(current_index=0, chars=[object(), object()])
        key = BaseWWTask.android_switch_key(fake, 1)
        self.assertIn(key, ANDROID_SWITCH_KEYS)

    def test_pc_path_unchanged(self):
        fake = SwitchTask(adb=False, current_index=0)
        self.assertEqual(BaseWWTask.android_switch_key(fake, 0), '1')
        self.assertEqual(BaseWWTask.android_switch_key(fake, 2), '3', 'PC/云仍用 index+1 约定')


class TestFormationTeamSize(unittest.TestCase):
    def test_default_three(self):
        fake = SwitchTask(current_index=0)
        self.assertEqual(BaseWWTask.android_team_size(fake), 3, '未加载角色时默认三人编队')

    def test_loaded_chars_decide_size(self):
        fake = SwitchTask(chars=[object(), object(), object()])
        self.assertEqual(BaseWWTask.android_team_size(fake), 3)
        fake2 = SwitchTask(chars=[object(), object()])
        self.assertEqual(BaseWWTask.android_team_size(fake2), 2, '编队配置两人就是两人队')

    def test_in_team_android_uses_formation_not_ocr(self):
        fake = SwitchTask(current_index=2)
        with patch.object(android_world, 'in_android_world', return_value=(True, 'radar')):
            in_team, index, size = BaseWWTask.in_team_android(fake)
        self.assertTrue(in_team)
        self.assertEqual(index, 2, '当前角色 = 脚本维护的逻辑下标')
        self.assertEqual(size, 3, '队伍人数按编队, 不做画面识别')

    def test_in_team_android_clamps_bad_index(self):
        fake = SwitchTask(current_index=99)
        with patch.object(android_world, 'in_android_world', return_value=(True, 'radar')):
            _, index, _ = BaseWWTask.in_team_android(fake)
        self.assertEqual(index, 0, '非法逻辑下标要收敛到 0')


class TestSources(unittest.TestCase):
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def _src(self, rel):
        with open(os.path.join(self.repo, rel), encoding='utf-8') as f:
            return f.read()

    def test_no_in_combat_team_ocr(self):
        src = self._src('src/task/BaseWWTask.py')
        self.assertNotIn('_read_android_party_badges', src, '战斗期间队伍栏 OCR 必须移除')
        self.assertNotIn('android_confirm_switch', src, '战斗中发键核实 OCR 必须移除')
        self.assertNotIn('ANDROID_PARTY_BADGE_RE', src)

    def test_switch_loop_uses_formation_key(self):
        src = self._src('src/task/BaseCombatTask.py')
        self.assertIn('self.android_switch_key(switch_to.index', src)
        self.assertIn('switch_to.index + 1', src, 'PC/云仍保留原约定')

    def test_walk_to_treasure_adb_recovery(self):
        src = self._src('src/task/BaseWWTask.py')
        self.assertIn('from ok.task.exceptions import WaitFailedException', src)
        self.assertIn('self.wait_combat(target=True, time_out=5, raise_if_not_found=False)', src,
                      '手游端找宝箱超时要先检查是否仍在战斗')
        self.assertIn('return self.walk_to_treasure(send_f=send_f, raise_if_not_found=False)', src,
                      '清完残象后重试走向奖励')


if __name__ == '__main__':
    unittest.main(verbosity=2)
