"""MuMu 手游端"角色动都不动 / 手动锁定也不打"根因修复测试 (v1.5.7).

根因(本次真正命中, 前面 v1.5.2~v1.5.6 修的都是下游症状):
  capture='ipc' 让 DeviceManager 的交互层覆盖条件(capture=='windows')失效,
  实际回退到 ADBInteraction(日志实锤: 'ADBInteraction' object has no attribute
  'mouse_down')。而 MuMu 手游靠【键位映射】操作 —— 模拟器把真实 Windows 键盘
  事件转成屏幕触摸。ADBInteraction 的两条输入通道对手游全部无效:
    1) send_key -> `input keyevent KEYCODE_*` : 安卓系统层按键, 手游不认,
       所以手动按 Y 能锁敌, 脚本 send_key('y') 却毫无反应, 技能键 e/q/r
       发出去没有动画(click_liberation 一直 timeout)。
       另外 Pynput 真实键盘只送到前台窗口, 所以发送前必须把 MuMu 切到前台。
    2) click() 无坐标 -> 点屏幕中心(0.5,0.5)=角色/空地: 手游攻击按钮在
       右下角(0.80,0.775), 点中心永远打不出去 -> 角色一动不动。

修复(全部在 BaseWWTask, 部署清单内, 全局生效):
  - 安卓战斗中的无坐标 click()/mouse_down() 改为点右下角攻击按钮坐标。
  - 安卓模拟器(有 hwnd_window 且 interaction 是 ADBInteraction)先把窗口切前台,
    再叠加 Pynput 真实键盘事件, 触发 MuMu 键位映射; 真机(无 hwnd_window)不变。

本测试用桩验证分发逻辑, 不真的向系统发送键盘/鼠标事件。
"""
import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

WORK = r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working"
os.chdir(WORK)
sys.path.insert(0, WORK)

from src.task.BaseWWTask import BaseWWTask
from ok.device.interaction_methods.adb import ADBInteraction


class KeyboardControllerStub:
    """记录 press/release 调用, 不真的发键盘事件。"""

    instances = []

    def __init__(self):
        self.pressed = []
        self.released = []
        KeyboardControllerStub.instances.append(self)

    def press(self, key):
        self.pressed.append(key)

    def release(self, key):
        self.released.append(key)


class NemulmStub:
    def __init__(self):
        self.down_calls = []
        self.up_calls = 0

    def down(self, x, y):
        self.down_calls.append((int(x), int(y)))

    def up(self):
        self.up_calls += 1


class HwndWindowStub:
    def __init__(self, foreground=True, bring_succeeds=True):
        self.foreground = foreground
        self.bring_succeeds = bring_succeeds
        self.bring_calls = 0

    def is_foreground(self):
        return self.foreground

    def bring_to_front(self):
        self.bring_calls += 1
        if self.bring_succeeds:
            self.foreground = True


class DeviceManagerStub:
    def __init__(self, with_hwnd=True, foreground=True, bring_succeeds=True):
        self.hwnd_window = HwndWindowStub(foreground, bring_succeeds) if with_hwnd else None

    def get_preferred_device(self):
        return {'device': 'adb'}


class ExecutorStub:
    def __init__(self, with_hwnd=True, interaction_is_adb=True, foreground=True, bring_succeeds=True,
                 with_nemu=True):
        self.device_manager = DeviceManagerStub(with_hwnd, foreground, bring_succeeds)
        if interaction_is_adb:
            self.interaction = object.__new__(ADBInteraction)
        else:
            self.interaction = SimpleNamespace(send_key=lambda *a, **kw: None)
        capture = SimpleNamespace()
        capture.nemu_impl = NemulmStub() if with_nemu else None
        self.interaction.capture = capture

    def reset_scene(self):
        pass


class TaskDouble(BaseWWTask):
    """不跑 BaseTask 初始化, 只提供输入相关的最小桩。"""

    @property
    def width(self):
        return 1920

    @property
    def height(self):
        return 1080

    def __init__(self, adb=True, in_combat=True, **executor_kwargs):
        self._adb = adb
        self._in_combat = in_combat
        self._executor = ExecutorStub(**executor_kwargs)
        self.touch = SimpleNamespace(is_touch=False)

    def is_adb(self):
        return self._adb

    def width_of_screen(self, p):
        return int(self.width * p)

    def height_of_screen(self, p):
        return int(self.height * p)

    def sleep(self, seconds):
        pass


def patch_super_click():
    """替换 BaseTask.click, 记录最终交给执行器的坐标。"""
    captured = {}

    def fake_click(self, x=-1, y=-1, *args, **kwargs):
        captured['xy'] = (x, y)
        captured['kwargs'] = kwargs
        return True

    return patch('ok.task.task.BaseTask.click', new=fake_click), captured


class TestAttackClickTarget(unittest.TestCase):
    """手游普攻必须点攻击按钮, 不能点屏幕中心。"""

    def test_adb_in_combat_click_uses_attack_button(self):
        fake = TaskDouble(adb=True, in_combat=True)
        patcher, captured = patch_super_click()
        with patcher:
            BaseWWTask.click(fake)
        self.assertEqual(captured['xy'], (1536, 837))
        self.assertFalse(captured['kwargs']['move'], '手游点击不应先移动鼠标')

    def test_non_adb_click_still_uses_center(self):
        fake = TaskDouble(adb=False, in_combat=True)
        patcher, captured = patch_super_click()
        with patcher:
            BaseWWTask.click(fake)
        self.assertEqual(captured['xy'], (960, 540))

    def test_adb_non_combat_click_still_uses_center(self):
        fake = TaskDouble(adb=True, in_combat=False)
        patcher, captured = patch_super_click()
        with patcher:
            BaseWWTask.click(fake)
        self.assertEqual(captured['xy'], (960, 540))

    def test_attack_button_constant_matches_hud(self):
        ax, ay = BaseWWTask.TOUCH_ATTACK_BUTTON
        self.assertGreater(ax, 0.7, '攻击按钮应在屏幕右侧')
        self.assertGreater(ay, 0.7, '攻击按钮应在屏幕下方')

    def test_mouse_down_uses_attack_button_and_nemu_touch(self):
        fake = TaskDouble(adb=True, in_combat=True)
        BaseWWTask.mouse_down(fake)
        nemu = fake.executor.interaction.capture.nemu_impl
        self.assertEqual(nemu.down_calls, [(1536, 837)])


class TestAdbKeymapAvailability(unittest.TestCase):
    """仅"模拟器 + ADBInteraction"叠加真实键盘; 真机/PC/云不变。"""

    def test_emulator_with_adb_interaction_available(self):
        fake = TaskDouble(adb=True)
        self.assertTrue(BaseWWTask._adb_keymap_available(fake))

    def test_real_device_no_hwnd_unavailable(self):
        fake = TaskDouble(adb=True, with_hwnd=False)
        self.assertFalse(BaseWWTask._adb_keymap_available(fake))

    def test_non_adb_unavailable(self):
        fake = TaskDouble(adb=False)
        self.assertFalse(BaseWWTask._adb_keymap_available(fake))

    def test_not_adb_interaction_unavailable(self):
        fake = TaskDouble(adb=True, interaction_is_adb=False)
        self.assertFalse(BaseWWTask._adb_keymap_available(fake))


class TestSendKeyAddsRealKeyboard(unittest.TestCase):
    """send_key 在模拟器上先切前台, 再叠加 Pynput 真实键盘, 保留 super 调用。"""

    def setUp(self):
        KeyboardControllerStub.instances.clear()

    def test_send_key_calls_real_key_and_super(self):
        fake = TaskDouble(adb=True)
        super_calls = []

        def fake_send_key(self, key, **kwargs):
            super_calls.append(key)

        with patch('pynput.keyboard.Controller', KeyboardControllerStub), \
             patch('ok.task.task.BaseTask.send_key', new=fake_send_key):
            BaseWWTask.send_key(fake, 'y', after_sleep=0)

        self.assertEqual(super_calls, ['y'], '必须保留原 ADB keyevent 通道')
        controller = KeyboardControllerStub.instances[0]
        self.assertEqual(controller.pressed, ['y'])
        self.assertEqual(controller.released, ['y'])
        self.assertEqual(fake.executor.device_manager.hwnd_window.bring_calls, 0,
                         '已经是前台时不必重复抢焦点')

    def test_real_key_brings_emulator_to_front(self):
        fake = TaskDouble(adb=True, foreground=False, bring_succeeds=True)
        with patch('pynput.keyboard.Controller', KeyboardControllerStub):
            ok = BaseWWTask._adb_real_key(fake, 'e', down_time=0.02)

        self.assertTrue(ok)
        self.assertEqual(fake.executor.device_manager.hwnd_window.bring_calls, 1)
        controller = KeyboardControllerStub.instances[0]
        self.assertEqual(controller.pressed, ['e'])

    def test_real_key_skipped_when_window_cannot_be_focused(self):
        fake = TaskDouble(adb=True, foreground=False, bring_succeeds=False)
        with patch('pynput.keyboard.Controller', KeyboardControllerStub):
            ok = BaseWWTask._adb_real_key(fake, 'q')

        self.assertFalse(ok, '非前台窗口不能乱发真实键盘事件')
        self.assertEqual(KeyboardControllerStub.instances, [], '不应创建键盘控制器')

    def test_parse_pynput_key(self):
        for k in ('y', 'e', 'q', 'r', '1', '`'):
            self.assertEqual(BaseWWTask._parse_pynput_key(k), k)
        self.assertIsNotNone(BaseWWTask._parse_pynput_key('esc'))
        self.assertIsNotNone(BaseWWTask._parse_pynput_key('f2'))

    def test_send_key_down_up_use_pynput(self):
        fake = TaskDouble(adb=True)
        super_calls = []

        def fake_down(self, key, **kwargs):
            super_calls.append(('down', key))

        def fake_up(self, key, **kwargs):
            super_calls.append(('up', key))

        with patch('pynput.keyboard.Controller', KeyboardControllerStub), \
             patch('ok.task.task.BaseTask.send_key_down', new=fake_down), \
             patch('ok.task.task.BaseTask.send_key_up', new=fake_up):
            BaseWWTask.send_key_down(fake, 'a')
            BaseWWTask.send_key_up(fake, 'a')

        self.assertEqual(KeyboardControllerStub.instances[0].pressed, ['a'])
        self.assertEqual(KeyboardControllerStub.instances[-1].released, ['a'])
        self.assertEqual(super_calls, [], 'ADBInteraction 没有 down/up, 不能回落 super')

    def test_non_adb_key_hold_still_uses_super(self):
        fake = TaskDouble(adb=False)
        super_calls = []

        def fake_down(self, key, **kwargs):
            super_calls.append(('down', key))

        def fake_up(self, key, **kwargs):
            super_calls.append(('up', key))

        with patch('pynput.keyboard.Controller', KeyboardControllerStub), \
             patch('ok.task.task.BaseTask.send_key_down', new=fake_down), \
             patch('ok.task.task.BaseTask.send_key_up', new=fake_up):
            BaseWWTask.send_key_down(fake, 'a')
            BaseWWTask.send_key_up(fake, 'a')

        self.assertEqual(super_calls, [('down', 'a'), ('up', 'a')])
        self.assertEqual(KeyboardControllerStub.instances, [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
