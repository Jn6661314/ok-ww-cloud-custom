"""MuMu/安卓端重击长按崩溃修复测试 (v1.5.6).

现象: 战斗真正跑起来后, 漂泊者连招 heavy_attack() 调用 self.task.mouse_down(),
      但 ADBInteraction 没有 mouse_down 方法 -> AttributeError -> AutoCombatTask
      exception stopped, 自动战斗停止。日志:
        Rover.py:165 spectro_routine_aftertune_combo -> heavy_attack
        BaseChar.py:924 self.task.mouse_down()
        AttributeError: 'ADBInteraction' object has no attribute 'mouse_down'

根因: mouse_down/mouse_up 在 20+ 角色类的重击连招里都用, 而上游 ADBInteraction
      只实现了 click/send_key/swipe, 没有 mouse_down/up。

修复: 在 BaseWWTask 覆盖 mouse_down/mouse_up (部署清单内, 所有任务都继承它):
      - adb: 用 nemu_impl.down/up 在屏幕中心(与 click 的 -1,-1 处理一致)长按;
        无 nemu 通道时降级为普通 click, 保证不崩溃。
      - PC/云: super() 走上游实现, 行为不变。
"""
import inspect
import os
import sys
import unittest

WORK = r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working"
os.chdir(WORK)
sys.path.insert(0, WORK)

from src.task.BaseWWTask import BaseWWTask


class FakeNemu:
    def __init__(self, fail=False):
        self.down_calls = []
        self.up_calls = 0
        self.fail = fail

    def down(self, x, y):
        if self.fail:
            raise RuntimeError('nemu down failed')
        self.down_calls.append((x, y))

    def up(self):
        self.up_calls += 1


class FakeCapture:
    def __init__(self, nemu):
        self.nemu_impl = nemu


class FakeInteraction:
    def __init__(self, nemu):
        self.capture = FakeCapture(nemu)


class FakeExecutor:
    def __init__(self, nemu):
        self.interaction = FakeInteraction(nemu)


class AdbTaskDouble:
    """模拟 adb 任务实例: 提供 BaseWWTask.mouse_down/up 用到的最小属性。"""

    def __init__(self, nemu=None, fallback_clicks=None):
        self._adb = True
        self.executor = FakeExecutor(nemu) if nemu is not None else None
        self.width = 1920
        self.height = 1080
        self.fallback_clicks = fallback_clicks if fallback_clicks is not None else []

    def is_adb(self):
        return self._adb

    def width_of_screen(self, p):
        return int(self.width * p)

    def height_of_screen(self, p):
        return int(self.height * p)

    def click(self, x, y, name=None, key="left"):
        self.fallback_clicks.append((x, y))


class TestAdbMouseHold(unittest.TestCase):
    def test_adb_mouse_down_uses_nemu_center(self):
        nemu = FakeNemu()
        fake = AdbTaskDouble(nemu=nemu)
        BaseWWTask.mouse_down(fake)  # 默认 -1,-1
        self.assertEqual(nemu.down_calls, [(960, 540)], '应在屏幕中心触摸按下')
        self.assertEqual(fake._adb_mouse_down_xy, (960, 540))

    def test_adb_mouse_down_with_explicit_xy(self):
        nemu = FakeNemu()
        fake = AdbTaskDouble(nemu=nemu)
        BaseWWTask.mouse_down(fake, x=100, y=200)
        self.assertEqual(nemu.down_calls, [(100, 200)])

    def test_adb_mouse_up_calls_nemu_up(self):
        nemu = FakeNemu()
        fake = AdbTaskDouble(nemu=nemu)
        BaseWWTask.mouse_down(fake)
        BaseWWTask.mouse_up(fake)
        self.assertEqual(nemu.up_calls, 1)
        self.assertIsNone(fake._adb_mouse_down_xy)

    def test_mouse_up_without_down_is_noop(self):
        nemu = FakeNemu()
        fake = AdbTaskDouble(nemu=nemu)
        BaseWWTask.mouse_up(fake)  # 没有前置 down
        self.assertEqual(nemu.up_calls, 0)

    def test_nemu_fail_falls_back_to_click_no_crash(self):
        nemu = FakeNemu(fail=True)
        fake = AdbTaskDouble(nemu=nemu)
        # 不应抛异常
        BaseWWTask.mouse_down(fake)
        self.assertEqual(fake.fallback_clicks, [(960, 540)], 'nemu 失败应降级为普通点击')

    def test_no_nemu_falls_back_to_click(self):
        fake = AdbTaskDouble(nemu=None)
        fake.executor = FakeExecutor(FakeCapture(None))
        BaseWWTask.mouse_down(fake)
        self.assertEqual(fake.fallback_clicks, [(960, 540)])


class TestPcCloudUnchanged(unittest.TestCase):
    """PC/云游戏: adb=False 时必须走 super(), 不改上游行为。"""

    def test_non_adb_calls_super(self):
        src = inspect.getsource(BaseWWTask.mouse_down)
        self.assertIn('if not self.is_adb():', src)
        self.assertIn('return super().mouse_down(', src)
        src_up = inspect.getsource(BaseWWTask.mouse_up)
        self.assertIn('if not self.is_adb():', src_up)
        self.assertIn('return super().mouse_up(', src_up)


class TestCoverage(unittest.TestCase):
    def test_all_mouse_down_calls_reach_task(self):
        # 所有角色重击都用 self.task.mouse_down(), 覆盖层在 BaseWWTask 上全局生效
        import glob
        count = 0
        for path in glob.glob(os.path.join(WORK, 'src', 'char', '*.py')):
            with open(path, encoding='utf-8') as f:
                count += f.read().count('self.task.mouse_down()')
        self.assertGreater(count, 10, f'应覆盖所有角色重击调用, 实际仅 {count} 处')


if __name__ == '__main__':
    unittest.main(verbosity=2)
