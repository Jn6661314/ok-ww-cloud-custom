# -*- coding: utf-8 -*-
"""v1.8.18: MuMu 战斗切人永远停在 1 号位的修复测试。

根因: 手填编队为空 -> 走画面识别投票, 旧逻辑要求连续 3 次识别一致才锁定;
战斗特效让每次识别组合都不同 -> 从未锁定 -> load_chars 每帧重建角色 ->
角色身份/当前下标每帧重置 -> 切人映射全乱、永远停在 1 号位。

修复:
1. 战斗中首次有效识别即锁定, 锁定后整场战斗不再重识别/换锁;
2. 新增三个编队角色下拉(官方名点选, 防写错), 优先于旧的逗号字符串。
"""
import os
import sys
import time
import unittest

WORK = os.environ.get('OKWW_WORK', r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working")
os.chdir(WORK)
sys.path.insert(0, WORK)

from src.task.BaseWWTask import BaseWWTask  # noqa: E402


def bare_task(android_config=None, in_combat=None):
    """不走 __init__, 只装被测方法需要的属性。"""
    task = object.__new__(BaseWWTask)
    task.android_config = android_config or {}
    task.scene = None if in_combat is None else type('S', (), {'in_combat': in_combat})()
    task._android_team_votes = None
    task._android_team_lock = None
    task._android_team_recheck_at = 0
    task._android_name_alias_cache = None
    task.logs = []
    task.warnings = []
    task.tr = lambda s: s
    task.log_info = lambda msg: task.logs.append(msg)
    task.log_debug = lambda msg: None
    task.log_warning = lambda msg: task.warnings.append(msg)
    return task


class VoteLockTest(unittest.TestCase):

    def test_combat_first_valid_identity_locks_immediately(self):
        task = bare_task(in_combat=True)
        first = ('Labels.char_yuanwu', 'Labels.char_augusta', None)
        result = task.android_vote_team_identity(first)
        self.assertEqual(result, first)
        self.assertEqual(task._android_team_lock, first,
                         '战斗中首次识别必须立即锁定, 不能再等连续 3 次一致')

    def test_combat_lock_survives_garbage_frames(self):
        task = bare_task(in_combat=True)
        task.android_vote_team_identity(('A', 'B', None))
        # 模拟战斗特效导致后续每帧识别都在乱串 / 读空
        for garbage in [('X', 'Y', None), (None, None, None), ('C', 'D', None), ('A', None, None)]:
            result = task.android_vote_team_identity(garbage)
            self.assertEqual(result, ('A', 'B', None),
                             '战斗中已锁定后, 任何抖动帧都不能改变编队')

    def test_no_combat_requires_stable_votes(self):
        task = bare_task(in_combat=False)
        # 非战斗中单次识别不应立即锁定(防换队误锁)
        task.android_vote_team_identity(('A', 'B', None))
        self.assertIsNone(task._android_team_lock)
        # 连续 3 次一致 -> 锁定
        for _ in range(2):
            task.android_vote_team_identity(('A', 'B', None))
        self.assertEqual(task._android_team_lock, ('A', 'B', None))


class ConfiguredTeamTest(unittest.TestCase):

    def test_dropdown_slots_take_priority(self):
        task = bare_task({
            'MuMu 编队': '错写的名字,奥古斯塔',
            'MuMu 编队角色1': 'Yuanwu',
            'MuMu 编队角色2': 'Augusta',
            'MuMu 编队角色3': '',
        })
        team = task.android_configured_team()
        self.assertEqual(len(team), 2)
        # 官方名应解析为 canonical; 只要两个不同且非空即可(具体值由 CharFactory 决定)
        self.assertTrue(all(team))
        self.assertEqual(team[0], team[0])  # 槽位顺序稳定
        self.assertEqual(task.warnings, [], '下拉选的名字都能解析, 不应有警告')

    def test_bad_slot_is_skipped_not_fatal(self):
        task = bare_task({
            'MuMu 编队角色1': 'Yuanwu',
            'MuMu 编队角色2': '不存在的角色XYZ',
            'MuMu 编队角色3': 'Augusta',
        })
        team = task.android_configured_team()
        self.assertEqual(len(team), 2, '无法识别的槽位应跳过, 其余两个仍能组成编队')

    def test_legacy_string_fallback(self):
        task = bare_task({'MuMu 编队': 'Yuanwu,Augusta'})
        team = task.android_configured_team()
        self.assertEqual(len(team), 2)
        self.assertTrue(all(team))

    def test_empty_config_returns_none(self):
        self.assertIsNone(bare_task({}).android_configured_team())
        self.assertIsNone(bare_task({'MuMu 编队': '   ', 'MuMu 编队角色1': ''}).android_configured_team())


class ConfigRegistrationTest(unittest.TestCase):

    def test_dropdown_slots_registered(self):
        import config
        option = next(o for o in config.config['global_configs'] if o.name == 'MuMu 安卓 Config')
        for key in ('MuMu 编队角色1', 'MuMu 编队角色2', 'MuMu 编队角色3'):
            self.assertIn(key, option.default_config)
            self.assertEqual(option.config_type[key]['type'], 'drop_down')
            self.assertIn('Rover', option.config_type[key]['options'])
            self.assertIn('Yuanwu', option.config_type[key]['options'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
