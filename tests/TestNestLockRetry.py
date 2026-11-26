"""残象聚落: 锁不到敌人时原地重锁, 仍失败就跳过当前聚落。

- 双极等敌人飞出聚落范围时, 不能一路追出去(会跑到别处/超时报错);
- 5 秒内锁不到 -> 原地重锁 2 次 -> 仍失败 -> 直接去下一个聚落;
- 敌人真死了有 F 掉落提示时, 必须照常拾取, 不能被误判成"目标丢失"。
"""

import importlib.util
import os
import sys
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

ROOT = Path(__file__).resolve().parents[1]
WORK = os.environ.get('OKWW_WORK', r'C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working')
os.chdir(WORK)
sys.path.insert(0, str(WORK))


def load_from_repo(relative, name):
    """按路径加载定制文件; sys.modules 里的 working 版本不会被误用。"""
    spec = importlib.util.spec_from_file_location(name, ROOT / relative)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


nest_mod = load_from_repo('src/task/NightmareNestTask.py', '_nest_task_lock_test')
combat_mod = load_from_repo('src/combat/CombatCheck.py', '_combat_check_lock_test')


class LockSettingsTest(unittest.TestCase):

    def test_defaults_are_five_seconds_and_two_retries(self):
        task = nest_mod.NightmareNestTask.__new__(nest_mod.NightmareNestTask)
        task.config = {}
        task._apply_lock_settings()
        self.assertEqual(task.target_enemy_time_out, 5)
        self.assertEqual(task.target_enemy_retry_timeout, 5)
        self.assertEqual(task.target_enemy_retry_count, 2)
        self.assertFalse(task.target_lost_give_up)

    def test_config_is_clamped_and_bad_values_fall_back(self):
        task = nest_mod.NightmareNestTask.__new__(nest_mod.NightmareNestTask)
        task.config = {'Lock Retry Timeout (s)': '999', 'Lock Retries': 'not-a-number'}
        task._apply_lock_settings()
        self.assertEqual(task.target_enemy_time_out, 60)
        self.assertEqual(task.target_enemy_retry_count, 2)


class RetryTargetTest(unittest.TestCase):

    def make_check(self, retries=2, timeout=5):
        check = combat_mod.CombatCheck.__new__(combat_mod.CombatCheck)
        check.target_enemy_retry_count = retries
        check.target_enemy_retry_timeout = timeout
        check.target_lost_give_up = False
        check._target_retried_this_episode = False
        check._no_enemy_since = time.monotonic() - 10
        check.is_adb = lambda: False
        check.log_warning = Mock()
        check.tr = lambda text: text
        check.sleep = Mock()
        check.target_enemy = Mock(return_value=False)
        return check

    def test_retry_stops_on_success(self):
        check = self.make_check()
        check.target_enemy.side_effect = [False, True]
        self.assertTrue(check._retry_target_before_give_up())
        self.assertEqual(check.target_enemy.call_count, 2)
        self.assertEqual(check.target_enemy.call_args.kwargs['time_out'], 5)
        self.assertFalse(check.target_lost_give_up)
        self.assertEqual(check._no_enemy_since, 0)

    def test_give_up_after_all_retries_fail(self):
        check = self.make_check(retries=3)
        self.assertFalse(check._retry_target_before_give_up())
        self.assertEqual(check.target_enemy.call_count, 3)
        self.assertTrue(check.target_lost_give_up)

    def test_no_retry_when_disabled(self):
        check = self.make_check(retries=0)
        self.assertFalse(check._retry_target_before_give_up())
        check.target_enemy.assert_not_called()
        self.assertFalse(check.target_lost_give_up)

    def test_only_one_retry_round_per_lost_target(self):
        check = self.make_check()
        check._retry_target_before_give_up()
        first_count = check.target_enemy.call_count
        check._retry_target_before_give_up()
        self.assertEqual(check.target_enemy.call_count, first_count)

    def test_no_enemy_window_uses_lock_timeout_when_retry_enabled(self):
        check = self.make_check(timeout=5)
        check._no_enemy_since = time.monotonic() - 3
        self.assertFalse(check.no_enemy_for(), '3 秒还没到 5 秒锁敌窗口, 不能判脱战')
        check.target_enemy_retry_count = 0
        self.assertTrue(check.no_enemy_for(), '框架默认 2 秒窗口仍生效')


class NestSkipTest(unittest.TestCase):

    def make_task(self, loot=False):
        task = nest_mod.NightmareNestTask.__new__(nest_mod.NightmareNestTask)
        task._capture_mode = False
        task.target_lost_give_up = False
        task.config = {}
        task.log_info = Mock()
        task.tr = lambda text: text
        task.esc_world_confirm = Mock()
        task.click = Mock()
        task.sleep = Mock()
        task.next_frame = Mock()
        task.run_until = Mock()
        task.wait_feature = Mock(return_value=SimpleNamespace(name='gray_teleport'))
        task._travel_to_nest_or_skip = Mock(return_value=True)
        # 有掉落时: while 循环里第一次命中 -> 按 F -> 第二次不再命中;
        # 战斗结束后给 target_lost 判断再返回一次 True, 证明"有掉落不能跳过聚落"。
        task.find_f_with_text = Mock(side_effect=[True, False, True] if loot else [False, False])
        task.send_key = Mock()
        task.wait_in_team_and_world = Mock(return_value=True)
        task.walk_find_echo = Mock(return_value=True)
        task.has_echo_notification = Mock(return_value=False)
        task._should_continue_combat_after_pickup = Mock(return_value=False)

        def _lose_target(**_kwargs):
            task.target_lost_give_up = True
            return True

        task.combat_once = _lose_target
        return task

    def test_target_lost_without_loot_skips_nest(self):
        task = self.make_task(loot=False)
        task.combat_nest(nest_mod.NestTarget(box=object(), cache_key='nest-a'))
        task.next_frame.assert_called()
        task.esc_world_confirm.assert_not_called()
        messages = [str(call) for call in task.log_info.call_args_list]
        self.assertTrue(any('跳过当前聚落' in text for text in messages), messages)

    def test_enemy_died_with_loot_still_picks_up(self):
        task = self.make_task(loot=True)
        task.combat_nest(nest_mod.NestTarget(box=object(), cache_key='nest-b'))
        messages = [str(call) for call in task.log_info.call_args_list]
        self.assertFalse(any('跳过当前聚落' in text for text in messages), messages)
        self.assertFalse(task.target_lost_give_up)


if __name__ == '__main__':
    unittest.main(verbosity=2)
