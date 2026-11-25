"""MuMu/安卓端无法战斗修复测试 (v1.5.3).

根因: 安卓端是手游 UI, 与 PC/云游戏战斗判定完全不同:
1. 手游没有 PC 的锁定图标(骷髅准星), has_target() 找 has_target 模板
   永远匹配不到 -> 一直 "target lost, retarget" -> 不进攻击循环。
2. 手游敌人是头顶红色血条+抗锯齿渐变, PC 的 threshold=0.95 把血条
   全部漏掉 -> check_health_bar() 也 False。
3. 锁敌键是 Y 键, 不是 PC 的鼠标中键。

修复:
- tap_target(): adb 发 Y 键, PC/云仍中键。
- has_target(): adb 端用 check_health_bar()(有血条=有敌人)代替锁定图标。
- has_health_bar(): adb 端 threshold 0.95 -> 0.8, 并要求横向条形。

本测试验证以上行为, 并确认 PC/云分支不受影响。
"""
import inspect
import os
import sys
import unittest

WORK = r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working"
os.chdir(WORK)
sys.path.insert(0, WORK)

from src.combat.CombatCheck import CombatCheck
from src.task.BaseCombatTask import BaseCombatTask


class TapTargetDouble:
    def __init__(self, adb=True):
        self._adb = adb
        self.calls = []

    def is_adb(self):
        return self._adb

    def send_key(self, key, **kwargs):
        self.calls.append(('send_key', key, kwargs))

    def middle_click(self, **kwargs):
        self.calls.append(('middle_click', None, kwargs))


class TestTapTarget(unittest.TestCase):
    def test_adb_sends_y_key(self):
        fake = TapTargetDouble(adb=True)
        CombatCheck.tap_target(fake)
        self.assertEqual(fake.calls, [('send_key', 'y', {})])

    def test_pc_uses_middle_click(self):
        fake = TapTargetDouble(adb=False)
        CombatCheck.tap_target(fake)
        self.assertEqual(fake.calls, [('middle_click', None, {})])

    def test_kwargs_passed_through(self):
        fake = TapTargetDouble(adb=True)
        CombatCheck.tap_target(fake, interval=0.2, after_sleep=0.1)
        self.assertEqual(fake.calls[0][2], {'interval': 0.2, 'after_sleep': 0.1})


class TestAndroidTargetDetection(unittest.TestCase):
    """真实战斗截图验证 adb 判定 (来自 10:09 的 has_target 失败截图)。"""

    @classmethod
    def setUpClass(cls):
        import cv2
        cls.cv2 = cv2
        shot = os.path.join(WORK, "screenshots/notification/2026-11-25_10-09-41-212_notification_1_original.png")
        cls.frame = cv2.imread(shot)
        if cls.frame is None:
            raise unittest.SkipTest('真实战斗截图不可用, 跳过像素级验证')

    def make_fake(self, adb):
        from ok import Box
        class Fake:
            _in_combat = False
            def __init__(self, adb, frame):
                self.frame = frame
                self.width, self.height = 1920, 1080
                self._adb = adb
            def is_adb(self): return self._adb
            def is_browser(self): return False
            def height_of_screen(self, r): return int(self.height * r)
            def width_of_screen(self, r): return int(self.width * r)
            def box_of_screen(self, x1, y1, x2, y2, **kw):
                return Box(int(self.width*x1), int(self.height*y1),
                           int(self.width*(x2-x1)), int(self.height*(y2-y1)))
            def get_current_char(self, raise_exception=False): return None
            def draw_boxes(self, *a, **kw): pass
            def find_one(self, *a, **kw): return None
            def get_target_names(self): return 'has_target', 'no_target'
            def get_box_by_name(self, name): return self.box_of_screen(0.9, 0.8, 1.0, 1.0)
            def find_best_match_in_box(self, *a, **kw): return None
            def allow_target_box_short_combat_check(self): return False
            def has_target(self, double_check=False): return CombatCheck.has_target(self, double_check)
            def has_health_bar(self): return CombatCheck.has_health_bar(self)
            def check_health_bar(self): return CombatCheck.check_health_bar(self)
            def target_visible(self): return CombatCheck.target_visible(self)
        return Fake(adb, self.frame)

    def test_adb_detects_health_bar(self):
        self.assertTrue(self.make_fake(True).has_health_bar(),
                        'adb 端必须能识别手游头顶红色血条 (threshold=0.8)')

    def test_adb_has_target_via_health_bar(self):
        self.assertTrue(self.make_fake(True).has_target(),
                        'adb 端 has_target 应等价为"有血条", 不能依赖 PC 锁定图标')

    def test_adb_target_visible(self):
        self.assertTrue(self.make_fake(True).target_visible())

    def test_pc_not_affected_by_mobile_screenshot(self):
        fake = self.make_fake(False)
        self.assertFalse(fake.has_health_bar(), 'PC 端 threshold=0.95 不应误判手游截图血条')


class TestCombatUsesTapTarget(unittest.TestCase):
    def test_target_enemy_uses_tap_target_only(self):
        src = inspect.getsource(CombatCheck.target_enemy)
        self.assertIn('tap_target', src)
        self.assertNotIn('middle_click', src)

    def test_wait_combat_uses_tap_target_only(self):
        src = inspect.getsource(BaseCombatTask.wait_combat)
        self.assertIn('tap_target', src)
        self.assertNotIn('middle_click', src)

    def test_no_direct_middle_click_outside_tap_target(self):
        for path in ('src/combat/CombatCheck.py', 'src/task/BaseCombatTask.py'):
            with open(os.path.join(WORK, path), encoding='utf-8') as f:
                for no, line in enumerate(f, 1):
                    if 'middle_click(' in line:
                        self.assertIn('self.middle_click(**kwargs)', line,
                                      f'{path}:{no} 未走 tap_target: {line.strip()}')


if __name__ == '__main__':
    unittest.main(verbosity=2)
