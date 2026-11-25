# -*- coding: utf-8 -*-
"""v1.5.15: 爱弥斯(Aemeath)轮转定制测试。

上游原版逻辑缺陷(实测): 队里有副C时, 爱弥斯只在"变奏入场 + 两个队友都满协奏
退场且 buff 未超时"(has_all_buff)才出招; 副C(Denia)经常协奏未满就被切走,
last_buff_time 不打点 -> has_all_buff 恒 False -> 爱弥斯每次上场 0.3 秒内被
切走, 全场零输出。

定制修复: 只要变奏入场(has_intro)就正常输出; 未入场且有副C时保持待机。
"""
import os
import sys
import unittest
from unittest.mock import patch
from types import SimpleNamespace

# Aemeath.py 依赖上游 BaseChar(不在定制仓库), 从 working 目录导入部署后的定制版本
WORK = r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working"
os.chdir(WORK)
sys.path.insert(0, WORK)

from src.char.Aemeath import Aemeath  # noqa: E402


class StubTask:
    """最小任务桩, 满足 BaseChar.__init__ 与 Aemeath 依赖。"""

    def __init__(self, chars=None):
        self.chars = chars or []
        self.debug = False

    def tr(self, text):
        return text

    def find_one(self, *args, **kwargs):
        return None

    def log_info(self, msg):
        pass

    def log_debug(self, msg):
        pass


class TestAemeathWaitsForIntro(unittest.TestCase):
    """waits_for_intro 规则: 队里有两个队友且其中有副C时等入场。"""

    def _char_with(self, teammates):
        stub = StubTask(chars=teammates)
        char = Aemeath(stub, 0)
        return char

    def test_waits_when_sub_dps_in_team(self):
        denia = SimpleNamespace(is_sub_dps=True)
        verina = SimpleNamespace(is_sub_dps=False)
        char = self._char_with([denia, verina])
        self.assertTrue(char.waits_for_intro())

    def test_no_wait_when_no_sub_dps(self):
        verina = SimpleNamespace(is_sub_dps=False)
        yuanwu = SimpleNamespace(is_sub_dps=False)
        char = self._char_with([verina, yuanwu])
        self.assertFalse(char.waits_for_intro())

    def test_waits_when_team_not_full(self):
        verina = SimpleNamespace(is_sub_dps=False)
        char = self._char_with([verina])
        self.assertTrue(char.waits_for_intro())


class TestAemeathDoPerform(unittest.TestCase):
    """do_perform 分支: 变奏入场必须出招(v1.5.15 修复点)。"""

    def _char(self):
        stub = StubTask()
        return Aemeath(stub, 0)

    def test_no_intro_with_sub_dps_standby(self):
        """未入场且有副C: 待机切人, 不出招(保持上游行为)。"""
        char = self._char()
        char.has_intro = False
        char.waits_for_intro = lambda: True
        calls = {'switch': 0, 'perform': 0, 'attack': 0}
        with patch.object(Aemeath, 'has_long_action', return_value=False), \
             patch.object(Aemeath, 'switch_next_char',
                          side_effect=lambda *a, **k: calls.__setitem__('switch', calls['switch'] + 1)), \
             patch.object(Aemeath, 'perform_everything',
                          side_effect=lambda: calls.__setitem__('perform', calls['perform'] + 1)), \
             patch.object(Aemeath, 'continues_normal_attack',
                          side_effect=lambda *a, **k: calls.__setitem__('attack', calls['attack'] + 1)):
            char.do_perform()
        self.assertEqual(calls['switch'], 1, '待机分支必须切人')
        self.assertEqual(calls['perform'], 0, '待机分支不得出招')
        self.assertEqual(calls['attack'], 0, '待机分支不得普攻')

    def test_intro_without_all_buff_still_performs(self):
        """v1.5.15 核心修复: 变奏入场即使不满 buff 也必须出招。

        上游缺陷: has_all_buff 恒 False 时爱弥斯上场即切走, 全场零输出。
        """
        char = self._char()
        char.has_intro = True
        with patch.object(Aemeath, 'has_all_buff', return_value=False), \
             patch.object(Aemeath, 'waits_for_intro', return_value=True), \
             patch.object(Aemeath, 'has_long_action', return_value=False), \
             patch.object(Aemeath, 'continues_normal_attack', return_value=None), \
             patch.object(Aemeath, 'perform_everything', return_value=None) as pe, \
             patch.object(Aemeath, 'switch_next_char', return_value=None):
            char.do_perform()
        self.assertEqual(pe.call_count, 1, '变奏入场必须执行 perform_everything')
        self.assertFalse(char.must_cast_lib2_this_turn, '不满 buff 不得强制二段大')

    def test_intro_with_all_buff_must_cast_lib2(self):
        """满 buff + 变奏入场: 保持 must_cast_lib2 强制二段大逻辑。"""
        char = self._char()
        char.has_intro = True
        with patch.object(Aemeath, 'has_all_buff', return_value=True), \
             patch.object(Aemeath, 'waits_for_intro', return_value=True), \
             patch.object(Aemeath, 'has_long_action', return_value=False), \
             patch.object(Aemeath, 'continues_normal_attack', return_value=None), \
             patch.object(Aemeath, 'perform_everything', return_value=None) as pe, \
             patch.object(Aemeath, 'switch_next_char', return_value=None):
            char.do_perform()
        self.assertEqual(pe.call_count, 1)
        self.assertTrue(char.must_cast_lib2_this_turn, '满 buff 入场必须标记强制二段大')

    def test_no_intro_no_sub_dps_performs_on_field(self):
        """无副C队且未入场: 站场输出(上游站场行为)。"""
        char = self._char()
        char.has_intro = False
        char.waits_for_intro = lambda: False
        with patch.object(Aemeath, 'has_long_action', return_value=False), \
             patch.object(Aemeath, 'continues_normal_attack', return_value=None), \
             patch.object(Aemeath, 'perform_everything', return_value=None) as pe, \
             patch.object(Aemeath, 'switch_next_char', return_value=None):
            char.do_perform()
        self.assertEqual(pe.call_count, 1, '无副C队时爱弥斯必须站场输出')

    def test_required_action_pending_after_intro(self):
        """入场后未放强化E前, required_action_pending 必须为 True(保证轮转不被打断)。"""
        char = self._char()
        char.has_intro = True
        char.enhance_e_cast_this_turn = False
        char.must_cast_lib2_this_turn = False
        self.assertTrue(char.required_action_pending())
        char.enhance_e_cast_this_turn = True
        self.assertFalse(char.required_action_pending())


if __name__ == '__main__':
    unittest.main(verbosity=2)
