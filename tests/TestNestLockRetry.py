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
        # no_enemy_for() 会先分流 is_adb / is_browser, 这里模拟 PC 端。
        check.is_browser = lambda: False
        check.log_warning = Mock()
        check.tr = lambda text: text
        check.sleep = Mock()
        check.target_enemy = Mock(return_value=False)
        return check

    def test_retry_stops_on_success(self):
        check = self.make_check()
        check.target_enemy.side_effect = [False, True]
        self.assertTrue(check._retry_target_before_give_up(has_health=True))
        self.assertEqual(check.target_enemy.call_count, 2)
        self.assertEqual(check.target_enemy.call_args.kwargs['time_out'], 5)
        self.assertFalse(check.target_lost_give_up)
        self.assertEqual(check._no_enemy_since, 0)

    def test_give_up_after_all_retries_fail(self):
        check = self.make_check(retries=3)
        self.assertFalse(check._retry_target_before_give_up(has_health=True))
        self.assertEqual(check.target_enemy.call_count, 3)
        self.assertTrue(check.target_lost_give_up)

    def test_no_retry_without_health_bar(self):
        """正常清场(敌人被击杀)没有残留血条: 不能重锁, 也不能置 target_lost_give_up。"""
        check = self.make_check()
        self.assertFalse(check._retry_target_before_give_up(has_health=False))
        check.target_enemy.assert_not_called()
        self.assertFalse(check.target_lost_give_up)

    def test_no_retry_when_disabled(self):
        check = self.make_check(retries=0)
        self.assertFalse(check._retry_target_before_give_up(has_health=True))
        check.target_enemy.assert_not_called()
        self.assertFalse(check.target_lost_give_up)

    def test_only_one_retry_round_per_lost_target(self):
        check = self.make_check()
        check._retry_target_before_give_up(has_health=True)
        first_count = check.target_enemy.call_count
        check._retry_target_before_give_up(has_health=True)
        self.assertEqual(check.target_enemy.call_count, first_count)

    def test_no_enemy_window_uses_lock_timeout_when_retry_enabled(self):
        check = self.make_check(timeout=5)
        check._no_enemy_since = time.monotonic() - 3
        self.assertFalse(check.no_enemy_for(), '3 秒还没到 5 秒锁敌窗口, 不能判脱战')
        check.target_enemy_retry_count = 0
        self.assertTrue(check.no_enemy_for(), '框架默认 2 秒窗口仍生效')


class NestSkipTest(unittest.TestCase):

    def make_task(self, found):
        task = nest_mod.NightmareNestTask.__new__(nest_mod.NightmareNestTask)
        task._capture_mode = False
        task.target_lost_give_up = False
        task._unreachable_nests = set()
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
        task.find_f_with_text = Mock(return_value=False)
        # found: 目标丢失后还能不能把声骸找回来。
        task.walk_find_echo = Mock(return_value=found)
        task.yolo_find_echo = Mock(return_value=(found, None))
        task.has_echo_notification = Mock(return_value=False)
        task._should_continue_combat_after_pickup = Mock(return_value=False)
        task.ensure_main = Mock()
        task.openF2Book = Mock()
        task._nest_tab_of_current_nest = 'go_nest'
        task.go_nest = Mock()
        task.send_key = Mock()
        task.wait_in_team_and_world = Mock(return_value=True)

        def _lose_target(**_kwargs):
            task.target_lost_give_up = True
            return True

        task.combat_once = _lose_target
        return task

    def test_target_lost_without_echo_skips_and_remembers_nest(self):
        """目标丢失且确实没捡到声骸: 跳过聚落, 并记进 _unreachable_nests 防止原地打转。"""
        task = self.make_task(found=False)
        task.combat_nest(nest_mod.NestTarget(box=object(), cache_key='nest-a'))
        messages = [str(call) for call in task.log_info.call_args_list]
        self.assertTrue(any('跳过当前聚落' in text for text in messages), messages)
        self.assertIn('nest-a', task._unreachable_nests)

    def test_target_lost_but_echo_found_keeps_nest(self):
        """目标丢失但捡到了声骸: 照常拾取, 不跳过聚落。"""
        task = self.make_task(found=True)
        task.combat_nest(nest_mod.NestTarget(box=object(), cache_key='nest-b'))
        messages = [str(call) for call in task.log_info.call_args_list]
        self.assertFalse(any('跳过当前聚落' in text for text in messages), messages)
        self.assertNotIn('nest-b', task._unreachable_nests)
        self.assertFalse(task.target_lost_give_up)


if __name__ == '__main__':
    unittest.main(verbosity=2)
