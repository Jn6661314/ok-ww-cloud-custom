"""云鸣潮战斗中断回归: 血条/锁定短暂消失不能把活目标判成脱战。

真实日志(2026-11-26 13:20/13:21):
  combat check not in combat -> out of combat break -> TacetTask 开始走向奖励
  -> walk_to_treasure 30s 超时 -> "Tacet reward is unavailable and combat is still active"
  -> 重新 combat_once。表现为敌人没打完却莫名其妙停了。

根因: 定制的 no_enemy_for() 对所有端用 2 秒, 短于官方云游戏血条宽限
CLOUD_HEALTH_LOST_GRACE=3 秒, 宽限还没到期就被 reset_to_false。
修复后云游戏端用独立的 6 秒窗口, 并延长重锁时血条闪断的忍耐时间。
"""

import importlib.util
import os
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

ROOT = Path(__file__).resolve().parents[1]
WORK = os.environ.get('OKWW_WORK', r'C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working')
os.chdir(WORK)
sys.path.insert(0, str(WORK))


def load_from_repo(relative, name):
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


cc = load_from_repo('src/combat/CombatCheck.py', '_combat_check_cloud_grace_test')


class GraceConstantTest(unittest.TestCase):

    def test_cloud_no_enemy_window_is_longer_than_official_grace(self):
        """修复的核心不变量: 无敌人窗口必须长于官方 3 秒血条宽限。"""
        self.assertEqual(cc.CLOUD_HEALTH_LOST_GRACE, 3)
        self.assertGreater(cc.CLOUD_NO_ENEMY_EXIT_SECONDS, cc.CLOUD_HEALTH_LOST_GRACE)
        self.assertGreaterEqual(cc.CLOUD_RETARGET_HEALTH_LOST, cc.CLOUD_HEALTH_LOST_GRACE)


class NoEnemyForTest(unittest.TestCase):

    def make_check(self, *, browser=False, adb=False, retries=0, retry_timeout=5):
        check = cc.CombatCheck.__new__(cc.CombatCheck)
        check.is_browser = lambda: browser
        check.is_adb = lambda: adb
        check.target_enemy_retry_count = retries
        check.target_enemy_retry_timeout = retry_timeout
        check._no_enemy_since = 0
        return check

    def test_browser_survives_three_seconds_without_target(self):
        """旧代码 2 秒就判无敌人; 这里模拟 2.5 秒闪断, 必须还在战斗。"""
        check = self.make_check(browser=True)
        check._no_enemy_since = time.monotonic() - 2.5
        self.assertFalse(check.no_enemy_for())

    def test_browser_still_fights_at_five_seconds(self):
        check = self.make_check(browser=True)
        check._no_enemy_since = time.monotonic() - 5.0
        self.assertFalse(check.no_enemy_for())

    def test_browser_gives_up_after_six_seconds(self):
        """仍要能收尾, 不能因为放宽就无限续命。"""
        check = self.make_check(browser=True)
        check._no_enemy_since = time.monotonic() - 6.5
        self.assertTrue(check.no_enemy_for())

    def test_pc_and_adb_windows_unchanged(self):
        pc = self.make_check()
        pc._no_enemy_since = time.monotonic() - 2.5
        self.assertTrue(pc.no_enemy_for(), 'PC 端仍是 2 秒')
        adb = self.make_check(adb=True)
        adb._no_enemy_since = time.monotonic() - 3.5
        self.assertFalse(adb.no_enemy_for(), '安卓端仍是 4 秒')
        adb._no_enemy_since = time.monotonic() - 4.5
        self.assertTrue(adb.no_enemy_for())

    def test_nest_task_keeps_its_own_timeout(self):
        nest = self.make_check(browser=True, retries=2, retry_timeout=5)
        nest._no_enemy_since = time.monotonic() - 4.0
        self.assertFalse(nest.no_enemy_for(), '聚落任务仍按自己的 5 秒重锁窗口')


class InCombatTest(unittest.TestCase):
    """直接走 do_check_in_combat, 复现日志里的误判路径。"""

    def make_check(self, no_enemy_for_seconds):
        check = cc.CombatCheck.__new__(cc.CombatCheck)
        check.is_browser = lambda: True
        check.is_adb = lambda: False
        check.in_liberation = False
        check._in_combat = True
        check.target_enemy_retry_count = 0
        check.target_enemy_time_out = 3
        check.combat_end_condition = None
        check.last_in_realm_not_combat = 0
        # 锁定图标和血条都短暂消失 2.5 秒(云游戏技能特效/压缩常见)
        check._no_enemy_since = time.monotonic() - no_enemy_for_seconds
        check._cloud_health_lost_at = time.time() - no_enemy_for_seconds
        check.scene = SimpleNamespace(in_combat=lambda: None, set_in_combat=Mock(return_value=True))
        check.check_f_break = Mock()
        check.get_current_char = lambda: None
        check.on_combat_check = Mock(return_value=True)
        check.has_target = Mock(return_value=False)
        check.check_health_bar = Mock(return_value=False)
        check.should_check_monthly_card = Mock(return_value=False)
        check.target_enemy = Mock(return_value=False)
        check.reset_to_false = Mock(return_value=False)
        check.log_warning = Mock()
        check.log_info = Mock()
        check.tr = lambda text: text
        return check

    def test_brief_health_loss_keeps_combat(self):
        check = self.make_check(no_enemy_for_seconds=2.5)
        self.assertTrue(check.do_check_in_combat(False))
        check.reset_to_false.assert_not_called()
        check.scene.set_in_combat.assert_called_once()

    def test_real_no_enemy_still_resets(self):
        check = self.make_check(no_enemy_for_seconds=7.0)
        self.assertFalse(check.do_check_in_combat(False))
        check.reset_to_false.assert_called_once()


class RetargetPatienceTest(unittest.TestCase):
    """重锁时血条闪断不应 1.2 秒就放弃。"""

    def test_cloud_waits_for_target_to_reappear(self):
        check = cc.CombatCheck.__new__(cc.CombatCheck)
        check.is_browser = lambda: True
        check.is_adb = lambda: False
        check.target_enemy_time_out = 20
        check.tap_target = Mock()
        check.next_frame = Mock()
        clock = [1000.0]

        def fake_time():
            clock[0] += 0.1
            return clock[0]

        # 目标 2.5 秒后重新可见: 旧代码 1.2 秒就 return False 错过, 新代码能等到。
        check.target_visible = Mock(side_effect=lambda: clock[0] - 1000.0 >= 2.5)
        check.check_health_bar = Mock(side_effect=[True] + [False] * 200)
        with patch.object(cc.time, 'time', fake_time):
            found = check.target_enemy(wait=True, time_out=20, check_health=True)
        self.assertTrue(found, '云游戏血条闪断 2.5 秒后目标回来, 重锁应成功')

    def test_pc_keeps_short_patience(self):
        check = cc.CombatCheck.__new__(cc.CombatCheck)
        check.is_browser = lambda: False
        check.is_adb = lambda: False
        check.target_enemy_time_out = 20
        check.tap_target = Mock()
        check.next_frame = Mock()
        clock = [1000.0]

        def fake_time():
            clock[0] += 0.1
            return clock[0]

        check.target_visible = Mock(side_effect=lambda: clock[0] - 1000.0 >= 2.5)
        check.check_health_bar = Mock(side_effect=[True] + [False] * 200)
        with patch.object(cc.time, 'time', fake_time):
            found = check.target_enemy(wait=True, time_out=20, check_health=True)
        self.assertFalse(found, 'PC 端仍是 1.2 秒提前放弃')


if __name__ == '__main__':
    unittest.main()
