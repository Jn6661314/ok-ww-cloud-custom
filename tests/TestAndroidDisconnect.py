"""MuMu/安卓端掉线弹窗导致"卡住不动"修复测试 (v1.5.5).

现象: 游戏长时间挂机/网络抖动弹出【连接已断开】对话框, 遮暗整个画面。
      AutoCombatTask 是触发任务, 战斗循环不经过 is_main(), 而掉线检测
      之前只在 is_main() 里调用 -> 战斗判定一直在被遮暗的画面上找血条,
      恒 False -> 一直 target lost retarget -> break out of combat,
      且 logged_in 一直是 True, AutoLoginTask 不会重登 -> 永远卡在弹窗。

修复:
- CombatCheck.do_check_in_combat() 开头: adb 且 handle_android_disconnect()
  成功时 reset_to_false(reason='android disconnected'), 退出战斗状态。
- handle_android_disconnect() 加 15s 节流锁, 防止战斗循环每帧重复点确认。

重登链条: 点确认 -> logged_in=False(全局 og.my_app) -> AutoLoginTask 每 5s
检测到 False -> wait_login() 重新登录。10:28 的历史日志已验证此链条有效。
"""
import inspect
import os
import sys
import time
import unittest

WORK = r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working"
os.chdir(WORK)
sys.path.insert(0, WORK)

from src.combat.CombatCheck import CombatCheck
from src.task.BaseWWTask import BaseWWTask
from src.task import android_world


class DisconnectDouble:
    """最小桩: 只提供 do_check_in_combat 掉线分支所需的属性/方法。"""

    def __init__(self, adb=True, disconnected=False):
        self._adb = adb
        self._disconnected = disconnected
        self.handled = 0
        self.reset_reason = None
        self.liberation = False

    def is_adb(self):
        return self._adb

    def handle_android_disconnect(self):
        self.handled += 1
        return self._disconnected

    def _android_frame_is_dead(self):
        # v1.5.10 黑帧保护: 测试桩视为画面正常, 不拦截。
        return False

    def reset_to_false(self, reason=""):
        self.reset_reason = reason
        return False

    @property
    def in_liberation(self):
        return self.liberation


class TestCombatDisconnectGate(unittest.TestCase):
    def test_adb_disconnect_resets_combat(self):
        fake = DisconnectDouble(adb=True, disconnected=True)
        result = CombatCheck.do_check_in_combat(fake, target=False)
        self.assertFalse(result)
        self.assertEqual(fake.handled, 1)
        self.assertEqual(fake.reset_reason, 'android disconnected')

    def test_no_disconnect_continues_normal_check(self):
        # handle_android_disconnect 返回 False 时不应 reset, 应继续走正常战斗判定。
        # 用桩覆盖后续方法, 只断言掉线分支没触发 reset。
        fake = DisconnectDouble(adb=True, disconnected=False)
        fake.liberation = True  # 让后续分支直接返回 True, 避免依赖真实战斗态
        result = CombatCheck.do_check_in_combat(fake, target=False)
        self.assertTrue(result)
        self.assertIsNone(fake.reset_reason)

    def test_pc_not_gated_by_disconnect(self):
        # 非 adb 时短路, 不会调用 handle_android_disconnect
        fake = DisconnectDouble(adb=False, disconnected=True)
        fake.liberation = True
        result = CombatCheck.do_check_in_combat(fake, target=False)
        self.assertTrue(result)
        self.assertEqual(fake.handled, 0)


class ThrottleDouble:
    """最小桩: 只提供 handle_android_disconnect 节流分支所需的属性/方法。"""

    def __init__(self):
        self._android_disconnect_handled_at = 0
        self.clicks = 0
        self.logged_in = True

    def is_adb(self):
        return True


class TestDisconnectThrottle(unittest.TestCase):
    def test_recent_handle_skipped(self):
        fake = ThrottleDouble()
        fake._android_disconnect_handled_at = time.time() - 3  # 3 秒前刚处理过
        self.assertFalse(BaseWWTask.handle_android_disconnect(fake))
        self.assertEqual(fake.clicks, 0)

    def test_throttle_code_sets_timestamp(self):
        # 源码级断言: 点击后写时间戳, 且入口处 15s 节流判断存在
        src = inspect.getsource(BaseWWTask.handle_android_disconnect)
        self.assertIn("_android_disconnect_handled_at", src)
        self.assertIn("< 15", src)
        self.assertIn("self.click(confirm[-1]", src)
        self.assertIn("self.logged_in = False", src)
        self.assertIn("self._android_disconnect_handled_at = time.time()", src)


class TestDialogDetection(unittest.TestCase):
    def test_real_disconnect_screenshot_detected(self):
        """10:37 那张真实的掉线弹窗截图必须能被 has_center_dialog 识别。"""
        import cv2
        shot = os.path.join(WORK, 'screenshots', 'error',
                            '2026-11-25_10-37-24-508_error_AndroidDailyTask_WaitFailedException_original.png')
        if not os.path.exists(shot):
            self.skipTest('历史掉线截图不存在(可能被清理), 跳过像素级验证')
        frame = cv2.imread(shot)
        has_dialog, ratio = android_world.has_center_dialog(frame)
        self.assertTrue(has_dialog, f'掉线弹窗未被识别, 亮像素占比={ratio:.2f}')

    def test_normal_combat_screenshot_not_false_positive(self):
        """正常战斗截图不应被误判为弹窗(避免战斗中误点确认)。"""
        import cv2
        shot = os.path.join(WORK, 'screenshots', 'error',
                            '2026-11-25_10-21-47-688_error_AndroidDailyTask_WaitFailedException_original.png')
        if not os.path.exists(shot):
            self.skipTest('历史战斗截图不存在, 跳过')
        frame = cv2.imread(shot)
        has_dialog, ratio = android_world.has_center_dialog(frame)
        self.assertFalse(has_dialog, f'正常战斗画面被误判为弹窗, 亮像素占比={ratio:.2f}')


if __name__ == '__main__':
    unittest.main(verbosity=2)
