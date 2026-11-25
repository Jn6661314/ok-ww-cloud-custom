"""MuMu/安卓端"打着打着莫名其妙不打了"修复测试 (v1.5.10).

根因(日志 + 现场截图证据):
1. 安卓端 has_target 与血条是同一个判定, PC 端"血条仍在时 30 秒耐心重锁"的
   路径永远走不到; 血条一消失(潜地/无敌帧/切波次)就走默认 3 秒重锁定失败
   -> break out of combat。日志里 "target lost try retarget 3/10" ->
   "target_enemy failed, try recheck break out of combat" 反复出现, 而现场
   截图(12:13:59 / 12:18:36)里 boss 血条明明可见。
2. 重锁定失败一次就直接退出战斗, 没有二次确认。
3. MuMu 抓屏偶发整帧黑(日志大量"抓屏返回空画面"), 黑帧会被当"无敌人"。

修复 (src/combat/CombatCheck.py):
- 安卓无血条重锁定耐心 3 -> 8 秒 (ANDROID_RETARGET_TIMEOUT)。
- 重锁定失败后先重试一轮(6 秒)再退出。
- 等待 Y 键锁敌期间继续普攻(无坐标点击=攻击按钮), 保持输出。
- 连续无敌人退出窗口 2 -> 4 秒 (ANDROID_NO_ENEMY_EXIT)。
- 整帧黑/空帧保护: 保持 in_combat 最多 20 秒 (ANDROID_FRAME_DEAD_MAX)。
- PC/云游戏路径不变。
"""
import inspect
import os
import sys
import time
import types
import unittest

WORK = r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working"
os.chdir(WORK)
sys.path.insert(0, WORK)

from src.combat import CombatCheck as CombatCheckModule
from src.combat.CombatCheck import (
    ANDROID_FRAME_DEAD_MAX,
    ANDROID_NO_ENEMY_EXIT,
    ANDROID_RETARGET_RETRY,
    ANDROID_RETARGET_TIMEOUT,
    CombatCheck,
)


class QuietLogger(types.SimpleNamespace):
    pass


def make_fake(**attrs):
    fake = types.SimpleNamespace()
    fake._no_enemy_since = 0
    fake._android_frame_dead_since = 0
    fake.frame = None
    fake.is_adb = lambda: True
    for k, v in attrs.items():
        setattr(fake, k, v)
    return fake


class TestNoEnemyFor(unittest.TestCase):
    def test_adb_uses_longer_window(self):
        fake = make_fake(_no_enemy_since=time.monotonic() - 3.0)
        self.assertFalse(CombatCheck.no_enemy_for(fake),
                         '安卓端 3 秒无血条不应判定无敌人(阈值 4 秒)')

    def test_adb_window_value(self):
        fake = make_fake(_no_enemy_since=time.monotonic() - (ANDROID_NO_ENEMY_EXIT + 0.1))
        self.assertTrue(CombatCheck.no_enemy_for(fake))

    def test_pc_keeps_short_window(self):
        fake = make_fake(_no_enemy_since=time.monotonic() - 3.0)
        fake.is_adb = lambda: False
        self.assertTrue(CombatCheck.no_enemy_for(fake),
                        'PC 端仍用 2 秒窗口, 不受安卓参数影响')

    def test_explicit_seconds_overrides(self):
        fake = make_fake(_no_enemy_since=time.monotonic() - 0.5)
        self.assertTrue(CombatCheck.no_enemy_for(fake, seconds=0.3))


class TestAndroidFrameDead(unittest.TestCase):
    def test_none_frame_keeps_combat(self):
        fake = make_fake(frame=None)
        self.assertTrue(CombatCheck._android_frame_is_dead(fake))
        # 持续黑帧在窗口期内保持 True
        fake._android_frame_dead_since = time.time() - 5
        self.assertTrue(CombatCheck._android_frame_is_dead(fake))

    def test_black_frame_timeout_falls_through(self):
        fake = make_fake(frame=None)
        fake._android_frame_dead_since = time.time() - (ANDROID_FRAME_DEAD_MAX + 1)
        self.assertFalse(CombatCheck._android_frame_is_dead(fake),
                         '黑帧超过上限应走正常判定, 不能永远挂起')

    def test_normal_frame_not_dead(self):
        import numpy as np
        fake = make_fake(frame=np.zeros((10, 10, 3), dtype=np.uint8))
        fake.frame = np.full((10, 10, 3), 200, dtype=np.uint8)
        self.assertFalse(CombatCheck._android_frame_is_dead(fake))


class TestSourceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.check_src = inspect.getsource(CombatCheck.do_check_in_combat)
        cls.target_src = inspect.getsource(CombatCheck.target_enemy)
        cls.no_enemy_src = inspect.getsource(CombatCheck.no_enemy_for)

    def test_android_retarget_timeout_extended(self):
        self.assertIn('ANDROID_RETARGET_TIMEOUT', self.check_src)
        self.assertIn('ANDROID_RETARGET_RETRY', self.check_src, '重锁定失败必须先重试再退出')
        self.assertIn('retarget_timeout = 30', self.check_src, 'PC 端血条仍在时的 30 秒路径保留')

    def test_android_retry_before_break(self):
        self.assertIn('android retarget retry', self.check_src)

    def test_retarget_keeps_attacking_on_adb(self):
        self.assertIn('if self.is_adb():', self.target_src)
        self.assertIn('self.click(after_sleep=0.1)', self.target_src,
                      '安卓端等待锁敌期间要继续普攻')

    def test_no_enemy_window_android(self):
        self.assertIn('ANDROID_NO_ENEMY_EXIT', self.no_enemy_src)
        self.assertIn('NO_ENEMY_EXIT_SECONDS', self.no_enemy_src, 'PC 端窗口保留')

    def test_frame_dead_guard_in_check(self):
        self.assertIn('_android_frame_is_dead', self.check_src)

    def test_constants_ordering(self):
        self.assertGreaterEqual(ANDROID_RETARGET_TIMEOUT, 8)
        self.assertGreater(ANDROID_NO_ENEMY_EXIT, 2.0)
        self.assertGreater(ANDROID_FRAME_DEAD_MAX, ANDROID_RETARGET_TIMEOUT)


if __name__ == '__main__':
    unittest.main(verbosity=2)
