"""MuMu / 安卓模拟器支持测试。

覆盖：
1. config.py 里的安卓设备入口（adb packages / capture_method / interaction）与
   「MuMu/安卓 Config」全局配置、AndroidDailyTask 注册；
2. 框架侧：ADB 键位映射、MuMu IPC 全黑帧检测、adb 拉起游戏的节流；
3. 业务侧：安卓触屏的返回语义、大世界判定（雷达/加载条/断线弹窗）。
"""

import os
import re
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, PropertyMock, patch

import numpy as np

WORK = os.environ.get('OKWW_WORK', r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working")
os.chdir(WORK)
sys.path.insert(0, WORK)

import config  # noqa: E402
from ok import BaseTask  # noqa: E402
from ok.device.DeviceManager import DeviceManager  # noqa: E402
from ok.device.capture_methods import nemu_ipc  # noqa: E402
from ok.device.interaction_methods import keys  # noqa: E402
from src.task import android_world  # noqa: E402
from src.task.touch_mode import TOUCH_MENU_BACK_KEY, TouchMode  # noqa: E402


class ConfigTest(unittest.TestCase):

    def test_adb_device_entry_declared(self):
        adb = config.config.get('adb')
        self.assertIsNotNone(adb, 'config.py 缺少 adb 设备入口，MuMu 不会出现在设备列表')
        self.assertIn('com.kurogame.mingchao', adb['packages'])
        # MuMu 默认走 IPC 抓屏（快、支持长按重击）；非 MuMu 模拟器由
        # get_preferred_capture() 自动回退到 adb 抓屏。
        self.assertEqual(adb['capture_method'], 'ipc')

    def test_android_team_config_option_registered(self):
        names = [option.name for option in config.config['global_configs']]
        self.assertIn('MuMu 安卓 Config', names)

    def test_global_config_names_have_no_slash(self):
        # 框架按 ``configs/<名称>.json`` 存配置, 名称里的 "/" 会被当成目录分隔符,
        # 于是落到 configs/远控/串流窗口.json 这种子目录里(踩过)。
        for option in config.config['global_configs']:
            self.assertNotIn('/', option.name, f'全局配置名不能含斜杠: {option.name!r}')

    def test_daily_task_registered_only_once(self):
        # 官方 v3.8.15 的设计：一个 DailyTask 按设备自动区分操作，不能注册两次
        names = [item[1] for item in config.config['onetime_tasks']]
        self.assertEqual(names.count('DailyTask'), 1)

    def test_android_daily_task_still_available_as_entry(self):
        from src.task.AndroidDailyTask import AndroidDailyTask
        from src.task.DailyTask import DailyTask
        self.assertTrue(issubclass(AndroidDailyTask, DailyTask))


class KeyMapTest(unittest.TestCase):

    def test_esc_maps_to_android_back(self):
        # 鸣潮手游不响应 KEYCODE_ESCAPE，所有 send_key('esc') 都是"返回/关闭"语义
        self.assertEqual(keys.ADB_KEY_MAP['esc'], 'KEYCODE_BACK')

    def test_letters_digits_and_function_keys_are_legal_keycodes(self):
        self.assertEqual(keys.ADB_KEY_MAP['y'], 'KEYCODE_Y')
        self.assertEqual(keys.ADB_KEY_MAP['f'], 'KEYCODE_F')
        self.assertEqual(keys.ADB_KEY_MAP['1'], 'KEYCODE_1')
        self.assertEqual(keys.ADB_KEY_MAP['f2'], 'KEYCODE_F2')
        self.assertEqual(keys.ADB_KEY_MAP['`'], 'KEYCODE_GRAVE')

    def test_menu_key_is_not_esc(self):
        # 触屏端"返回 = 打开菜单 = 键位表的 ` 键"，不是 esc
        self.assertNotEqual(keys.ADB_KEY_MAP['`'], keys.ADB_KEY_MAP['esc'])


class BlackFrameTest(unittest.TestCase):

    def test_none_and_all_black_are_black(self):
        self.assertTrue(nemu_ipc.is_black_frame(None))
        self.assertTrue(nemu_ipc.is_black_frame(np.zeros((1080, 1920, 3), dtype=np.uint8)))

    def test_loading_frame_is_not_black(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        frame[:, :, 0] = 200
        self.assertFalse(nemu_ipc.is_black_frame(frame))


class AdbStartGameTest(unittest.TestCase):
    """DeviceManager.adb_start_game 的节流与拉起逻辑。"""

    def make_manager(self, in_front=False, ready=True, installed='com.kurogame.mingchao'):
        manager = object.__new__(DeviceManager)
        manager.packages = ['com.kurogame.mingchao']
        manager.exit_event = SimpleNamespace(is_set=lambda: False)
        manager._adb_game_start_at = 0.0
        manager.adb_check_in_front = Mock(return_value=in_front)
        manager.adb_wait_device_ready = Mock(return_value=ready)
        manager.adb_check_installed = Mock(return_value=installed)
        manager.adb_start_package = Mock()
        manager.logger = Mock()
        return manager

    def test_cooldown_skips_repeated_launch(self):
        manager = self.make_manager()
        self.assertTrue(manager.adb_start_game())
        manager.adb_start_package.assert_called_once()
        # 冷却期内再次调用不再发 intent
        self.assertFalse(manager.adb_start_game())
        manager.adb_start_package.assert_called_once()

    def test_game_already_in_front_does_nothing(self):
        manager = self.make_manager(in_front=True)
        self.assertTrue(manager.adb_start_game())
        manager.adb_start_package.assert_not_called()

    def test_device_not_ready_does_not_launch(self):
        manager = self.make_manager(ready=False)
        self.assertFalse(manager.adb_start_game())
        manager.adb_start_package.assert_not_called()

    def test_missing_package_does_not_launch(self):
        manager = self.make_manager(installed=None)
        self.assertFalse(manager.adb_start_game())
        manager.adb_start_package.assert_not_called()

    def test_force_ignores_cooldown(self):
        manager = self.make_manager()
        manager.adb_start_game()
        manager.adb_start_game(force=True)
        self.assertEqual(manager.adb_start_package.call_count, 2)


class AndroidWorldTest(unittest.TestCase):

    def test_black_frame_detected_separately(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        in_world, reason = android_world.in_android_world(frame)
        self.assertFalse(in_world)
        self.assertEqual(reason, 'black_frame')

    def test_radar_player_arrow_means_in_world(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        # RADAR_BOX 内涂满黄色(BGR)，对应 H≈30/S=255/V=255
        frame[10:150, 60:180] = (0, 255, 255)
        in_world, reason = android_world.in_android_world(frame)
        self.assertTrue(in_world, reason)
        self.assertIn('radar_yellow', reason)

    def test_loading_bar_is_not_world(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        # 底部一整行贯穿全屏的白条 = 加载进度条
        frame[1005:1010, :] = (255, 255, 255)
        in_world, reason = android_world.in_android_world(frame)
        self.assertFalse(in_world)
        self.assertIn('loading_screen', reason)

    def test_center_dialog_detection(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        frame[300:700, 400:1500] = 255
        has_dialog, ratio = android_world.has_center_dialog(frame)
        self.assertTrue(has_dialog)
        self.assertGreater(ratio, 0.5)

        empty = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.assertFalse(android_world.has_center_dialog(empty)[0])


class TouchModeTest(unittest.TestCase):

    def make_task(self, adb=True, interaction=None):
        task = Mock()
        task.is_adb = Mock(return_value=adb)
        task.is_browser = Mock(return_value=False)
        task.executor = SimpleNamespace(interaction=interaction)
        return task

    def test_adb_interaction_is_touch(self):
        class FakeADB:
            pass

        with patch('ok.device.interaction_methods.adb.ADBInteraction', FakeADB):
            task = self.make_task(interaction=FakeADB())
            self.assertTrue(TouchMode(task).is_touch)

    def test_post_message_interaction_is_not_touch(self):
        # 用 PostMessage 给模拟器窗口发真实键盘消息时，esc 仍是 PC 语义
        task = self.make_task(interaction=SimpleNamespace())
        self.assertFalse(TouchMode(task).is_touch)

    def test_touch_back_uses_menu_key(self):
        back = TouchMode(Mock())
        with patch.object(TouchMode, 'is_touch', new_callable=PropertyMock, return_value=True):
            back.back()
        back.task.send_key.assert_called_once_with(TOUCH_MENU_BACK_KEY, after_sleep=0)

    def test_book_and_activity_icons_only_on_touch(self):
        touch = TouchMode(Mock())
        with patch.object(TouchMode, 'is_touch', new_callable=PropertyMock, return_value=True):
            self.assertTrue(touch.open_book())
            self.assertTrue(touch.open_activity())
        with patch.object(TouchMode, 'is_touch', new_callable=PropertyMock, return_value=False):
            self.assertFalse(touch.open_book())
            self.assertFalse(touch.open_activity())


class BaseTaskSendKeyTest(unittest.TestCase):

    def test_esc_becomes_menu_key_on_touch(self):
        from src.task.BaseWWTask import BaseWWTask

        task = object.__new__(BaseWWTask)
        task.touch = Mock(is_touch=True)
        task._adb_keymap_available = Mock(return_value=False)
        with patch.object(BaseTask, 'send_key') as base_send:
            BaseWWTask.send_key(task, 'esc')
        base_send.assert_called_once()
        self.assertEqual(base_send.call_args[0][0], TOUCH_MENU_BACK_KEY)

    def test_esc_kept_on_pc(self):
        from src.task.BaseWWTask import BaseWWTask

        task = object.__new__(BaseWWTask)
        task.touch = Mock(is_touch=False)
        task._adb_keymap_available = Mock(return_value=False)
        with patch.object(BaseTask, 'send_key') as base_send:
            BaseWWTask.send_key(task, 'esc')
        self.assertEqual(base_send.call_args[0][0], 'esc')

    def test_adb_keymap_sends_real_key_in_addition(self):
        from src.task.BaseWWTask import BaseWWTask

        task = object.__new__(BaseWWTask)
        task.touch = Mock(is_touch=False)
        task._adb_keymap_available = Mock(return_value=True)
        task._adb_real_key = Mock(return_value=True)
        with patch.object(BaseTask, 'send_key'):
            BaseWWTask.send_key(task, 'y')
        task._adb_real_key.assert_called_once()


if __name__ == '__main__':
    unittest.main(verbosity=2)
