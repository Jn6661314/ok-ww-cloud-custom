"""MuMu 双指触控（ADB sendevent 多点触控）测试。

拉海洛方块手游版旋转靠屏幕左侧的「旋转」按钮，需要一指点按钮 + 一指拖动，
MuMu IPC/u2 都是单指 API，只有直接写 ABS_MT_SLOT 才能双指。
覆盖：坐标映射（实测 (游戏y, 游戏x)）、slot/tracking_id 管理、
交互接口（send_key('r') -> 第二指点旋转按钮）、异常收尾释放触点。
"""

import os
import sys
import unittest
from unittest.mock import Mock, call

WORK = os.environ.get('OKWW_WORK', r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working")
os.chdir(WORK)
sys.path.insert(0, WORK)

from src.task.multi_touch import (  # noqa: E402
    ABS_MT_POSITION_X, ABS_MT_POSITION_Y, ABS_MT_SLOT, ABS_MT_TRACKING_ID,
    EV_ABS, EV_KEY, EV_SYN, BTN_TOUCH, SYN_REPORT,
    GAME_H, GAME_W, MultiTouchDevice, MuMuMultiTouchInteraction,
)


class FakeAdbDevice:
    """记录所有 sendevent 调用，不真的连设备。"""

    def __init__(self, getevent_output=None):
        self.events = []
        self.getevent_output = getevent_output or (
            'add device 4: /dev/input/event4\n'
            '  name:     "Xiaomi Touchscreen"\n'
            '  ABS (0003): ABS_MT_SLOT : value 1\n'
        )

    def shell(self, cmd, *args, **kwargs):
        if isinstance(cmd, list) and cmd[0] == 'getevent':
            return self.getevent_output
        self.events.append(cmd)
        return ''

    def event_tuples(self):
        out = []
        for e in self.events:
            # _sendevent 传的是单个字符串 'sendevent <node> <type> <code> <val>'
            parts = str(e).split()
            if len(parts) == 5 and parts[0] == 'sendevent':
                out.append(tuple(int(p) for p in parts[2:]))
        return out


class CoordinateMappingTest(unittest.TestCase):
    """实测映射: 游戏(232, 750) -> 物理(750, 232)，即物理(x,y)=(游戏y, 游戏x)。"""

    def make_mt(self):
        dev = FakeAdbDevice()
        mt = MultiTouchDevice(dev, device_node='/dev/input/event4')
        return dev, mt

    def test_rotate_button_mapping(self):
        _, mt = self.make_mt()
        tx, ty = mt.game_to_touch(232 / 1920 * GAME_W, 750 / 1080 * GAME_H)
        # 游戏(232,750) in 1920x1080 -> 逻辑(248,800) -> 物理(800/1152*1080=750, 248/2048*1920=232)
        self.assertAlmostEqual(tx, 750, delta=3)
        self.assertAlmostEqual(ty, 232, delta=3)

    def test_node_auto_detect(self):
        dev = FakeAdbDevice()
        mt = MultiTouchDevice(dev)
        self.assertIsNone(mt._node)
        mt.game_to_touch(100, 100)
        self.assertEqual(mt._node, '/dev/input/event4')

    def test_no_multitouch_device_raises(self):
        dev = FakeAdbDevice(getevent_output='add device 1: /dev/input/event7\n  name: "Joystick"\n')
        mt = MultiTouchDevice(dev)
        with self.assertRaises(RuntimeError):
            mt.game_to_touch(100, 100)


class SlotManagementTest(unittest.TestCase):
    def make_mt(self):
        dev = FakeAdbDevice()
        return dev, MultiTouchDevice(dev, device_node='/dev/input/event4')

    def test_two_slots_have_distinct_tracking_ids(self):
        dev, mt = self.make_mt()
        mt.down(0, 100, 200)
        mt.down(1, 300, 400)
        self.assertEqual(mt._active[0], 1)
        self.assertEqual(mt._active[1], 2)

    def test_slot_slot_selectors_emitted(self):
        dev, mt = self.make_mt()
        mt.down(0, 100, 200)
        mt.down(1, 300, 400)
        # 两次 down 分别写 ABS_MT_SLOT 0 / 1
        selectors = [v for (t, c, v) in dev.event_tuples() if t == EV_ABS and c == ABS_MT_SLOT]
        self.assertIn(0, selectors)
        self.assertIn(1, selectors)

    def test_up_releases_tracking_id(self):
        dev, mt = self.make_mt()
        mt.down(0, 100, 200)
        mt.up(0)
        tuples = dev.event_tuples()
        self.assertIn((EV_ABS, ABS_MT_TRACKING_ID, -1), tuples)
        self.assertNotIn(0, mt._active)

    def test_move_keeps_same_tracking_id(self):
        dev, mt = self.make_mt()
        mt.down(0, 100, 200)
        mt.move(0, 150, 250)
        self.assertEqual(mt._active[0], 1)
        # move 不重复写 tracking_id（只在 down 时分配）
        tid_writes = [v for (t, c, v) in dev.event_tuples() if t == EV_ABS and c == ABS_MT_TRACKING_ID]
        self.assertEqual(tid_writes.count(1), 1)

    def test_close_releases_all_slots(self):
        dev, mt = self.make_mt()
        mt.down(0, 100, 200)
        mt.down(1, 300, 400)
        mt.close()
        self.assertEqual(mt._active, {})
        releases = [v for (t, c, v) in dev.event_tuples() if t == EV_ABS and c == ABS_MT_TRACKING_ID and v == -1]
        self.assertEqual(len(releases), 2)

    def test_sendevent_uses_correct_codes(self):
        dev, mt = self.make_mt()
        mt.down(0, 100, 200)
        tuples = dev.event_tuples()
        self.assertIn((EV_ABS, ABS_MT_SLOT, 0), tuples)
        self.assertIn((EV_ABS, ABS_MT_POSITION_X, 188), tuples)  # 200/1152*1080=188
        self.assertIn((EV_ABS, ABS_MT_POSITION_Y, 94), tuples)   # 100/2048*1920=94
        self.assertIn((EV_ABS, ABS_MT_TRACKING_ID, 1), tuples)
        self.assertIn((EV_SYN, SYN_REPORT, 0), tuples)

    def test_btn_touch_pressed_on_first_down_and_released_on_last_up(self):
        """BTN_TOUCH 漏发会让 Android 把触点当悬浮，方块拿不起来（v1.8.12 bug）。"""
        dev, mt = self.make_mt()
        mt.down(0, 100, 200)
        tuples = dev.event_tuples()
        self.assertIn((EV_KEY, BTN_TOUCH, 1), tuples)
        # 第二指按下不应重复发 BTN_TOUCH=1
        n_press = tuples.count((EV_KEY, BTN_TOUCH, 1))
        mt.down(1, 300, 400)
        self.assertEqual(dev.event_tuples().count((EV_KEY, BTN_TOUCH, 1)), n_press)
        # 抬起第一指（还有第二指）不发 BTN_TOUCH=0
        mt.up(0)
        self.assertNotIn((EV_KEY, BTN_TOUCH, 0), dev.event_tuples())
        # 抬起最后一指才清 BTN_TOUCH
        mt.up(1)
        self.assertIn((EV_KEY, BTN_TOUCH, 0), dev.event_tuples())


class InteractionAdapterTest(unittest.TestCase):
    def make_interaction(self):
        dev = FakeAdbDevice()
        mt = MultiTouchDevice(dev, device_node='/dev/input/event4')
        mt.down = Mock()
        mt.move = Mock()
        mt.up = Mock()
        mt.tap = Mock()
        mt.close = Mock()
        return dev, mt, MuMuMultiTouchInteraction(mt)

    def test_clickable_always_true(self):
        _, _, it = self.make_interaction()
        self.assertTrue(it.clickable())

    def test_mouse_down_move_up_use_slot0(self):
        _, mt, it = self.make_interaction()
        it.mouse_down(960, 540)  # 屏幕中心
        mt.down.assert_called_once()
        self.assertEqual(mt.down.call_args[0][0], 0)
        it.move(1000, 600)
        mt.move.assert_called_once()
        self.assertEqual(mt.move.call_args[0][0], 0)
        it.mouse_up()
        mt.up.assert_called_once_with(0)

    def test_send_key_r_taps_rotate_button_on_slot1(self):
        # 未配键位映射键 -> 回退点屏幕旋转按钮
        _, mt, it = self.make_interaction()
        it.send_key('r', down_time=.08)
        mt.tap.assert_called_once()
        slot = mt.tap.call_args[0][0]
        self.assertEqual(slot, 1)
        gx, gy = mt.tap.call_args[0][1:3]
        self.assertAlmostEqual(gx, it.ROTATE_BUTTON[0])
        self.assertAlmostEqual(gy, it.ROTATE_BUTTON[1])

    def test_send_key_r_prefers_keymap_key(self):
        # 配了键位映射键 -> 发真实键盘, 不点屏幕按钮
        mt = MultiTouchDevice(FakeAdbDevice(), device_node='/dev/input/event4')
        mt.tap = Mock()
        sender = Mock(return_value=True)
        it = MuMuMultiTouchInteraction(mt, rotate_key='f1', key_sender=sender)
        self.assertTrue(it.send_key('r', down_time=.09))
        sender.assert_called_once_with('f1', .09)
        mt.tap.assert_not_called()  # 不走屏幕坐标

    def test_send_key_r_falls_back_if_key_sender_fails(self):
        # 键位映射键发送失败(窗口没前置等) -> 回退点屏幕按钮
        mt = MultiTouchDevice(FakeAdbDevice(), device_node='/dev/input/event4')
        mt.tap = Mock()
        sender = Mock(return_value=False)
        it = MuMuMultiTouchInteraction(mt, rotate_key='f1', key_sender=sender)
        it.send_key('r')
        sender.assert_called_once()
        mt.tap.assert_called_once()

    def test_parse_mukey_common_keys(self):
        from src.task.multi_touch import parse_mukey
        self.assertIsNotNone(parse_mukey('f1'))
        self.assertIsNotNone(parse_mukey('f12'))
        self.assertIsNotNone(parse_mukey('space'))
        self.assertIsNotNone(parse_mukey('a'))
        self.assertIsNone(parse_mukey('not-a-key'))

    def test_other_keys_ignored(self):
        _, mt, it = self.make_interaction()
        it.send_key('esc')
        it.send_key('f')
        mt.tap.assert_not_called()

    def test_rotate_does_not_interrupt_slot0_drag(self):
        """旋转用 slot1，不能碰 slot0 的拖动。"""
        _, mt, it = self.make_interaction()
        it.mouse_down(500, 400)
        it.send_key('r')
        it.move(600, 450)
        self.assertEqual(mt.down.call_args[0][0], 0)
        self.assertEqual(mt.tap.call_args[0][0], 1)
        self.assertEqual(mt.move.call_args[0][0], 0)
        mt.up.assert_not_called()  # slot0 仍按住

    def test_close_releases_all(self):
        _, mt, it = self.make_interaction()
        it.close()
        mt.close.assert_called_once()


if __name__ == '__main__':
    unittest.main()
