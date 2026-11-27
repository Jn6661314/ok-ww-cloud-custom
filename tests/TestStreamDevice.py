"""远控 / 串流软件窗口作为设备（试验性）的测试。

覆盖：
1. config.py 里「远控/串流窗口(试验性)」全局配置的注册与默认值；
2. src.stream_window 读取配置 / 应用配置的分支（未开启、标题为空、无设备管理器）；
3. DeviceManager.set_stream_window 的重写结果（标题正则、去 exe/class、强制 Pynput）；
4. 窗口比例检查（16:9 通过、16:10 告警、未开启不检查）；
5. 远控窗口没打开时不建"未连接"占位设备（否则启动流程会误报游戏路径不存在）；
6. Globals 初始化时的挂载不会抛异常。
"""

import os
import re
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

WORK = os.environ.get('OKWW_WORK', r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working")
os.chdir(WORK)
sys.path.insert(0, WORK)

import config  # noqa: E402
from ok.device.DeviceManager import DeviceManager  # noqa: E402
from ok.device.interaction import PynputInteraction  # noqa: E402
from src import stream_window  # noqa: E402


def bare_device_manager():
    """不走 __init__（会建窗口/起线程），只装 set_stream_window 需要的属性。"""
    manager = object.__new__(DeviceManager)
    manager.stream_window_mode = False
    manager.win_interaction_class = None
    manager.hwnd_window = None
    manager.config = {}
    manager.windows_capture_config = {
        'exe': ['Client-Win64-Shipping.exe'],
        'title': None,
        'hwnd_class': 'UnrealWindow',
        'top_hwnd_class': ['CAgreementDlg'],
    }
    return manager


class ConfigTest(unittest.TestCase):

    def test_stream_option_registered(self):
        names = [option.name for option in config.config['global_configs']]
        self.assertIn(stream_window.STREAM_CONFIG_NAME, names)

    def test_stream_option_defaults(self):
        option = next(o for o in config.config['global_configs']
                      if o.name == stream_window.STREAM_CONFIG_NAME)
        self.assertFalse(option.default_config['Enable'], '默认必须是关闭(试验性)')
        self.assertEqual(option.default_config['Window Title'], '')
        self.assertTrue(option.default_config['Force Pynput'])

    def test_my_app_still_globals(self):
        self.assertEqual(config.config['my_app'], ['src.globals', 'Globals'])


class SettingsTest(unittest.TestCase):

    def test_reads_values(self):
        global_config = Mock()
        global_config.get_config.return_value = {'Enable': True, 'Window Title': ' UU远程 ', 'Force Pynput': False}
        self.assertEqual(stream_window.stream_window_settings(global_config), (True, 'UU远程', False))

    def test_missing_option_returns_none(self):
        global_config = Mock()
        global_config.get_config.side_effect = RuntimeError('not found')
        self.assertIsNone(stream_window.stream_window_settings(global_config))

    def test_no_global_config(self):
        self.assertIsNone(stream_window.stream_window_settings(None))


class ApplyTest(unittest.TestCase):

    def _global_config(self, enable, title, force_pynput=True):
        global_config = Mock()
        global_config.get_config.return_value = {
            'Enable': enable, 'Window Title': title, 'Force Pynput': force_pynput}
        return global_config

    def test_applies_to_device_manager(self):
        manager = Mock()
        manager.set_stream_window.return_value = True
        self.assertTrue(stream_window.apply_stream_window(self._global_config(True, 'UU远程'), manager))
        manager.set_stream_window.assert_called_once_with('UU远程', force_pynput=True)

    def test_disabled_does_nothing(self):
        manager = Mock()
        self.assertFalse(stream_window.apply_stream_window(self._global_config(False, 'UU远程'), manager))
        manager.set_stream_window.assert_not_called()

    def test_empty_title_lists_all_windows(self):
        # 开了远控但没填标题: 仍要进入列出所有窗口模式, 不能静默退回 PC 客户端。
        manager = Mock()
        manager.set_stream_window.return_value = True
        self.assertTrue(stream_window.apply_stream_window(self._global_config(True, '   '), manager))
        manager.set_stream_window.assert_called_once_with(None, force_pynput=True)

    def test_without_device_manager(self):
        self.assertFalse(stream_window.apply_stream_window(self._global_config(True, 'UU远程'), None))


class SetStreamWindowTest(unittest.TestCase):

    def test_rewrites_windows_config(self):
        manager = bare_device_manager()
        self.assertTrue(manager.set_stream_window('UU远程'))

        self.assertTrue(manager.stream_window_mode)
        windows = manager.windows_capture_config
        self.assertIsNone(windows['exe'], '必须清掉鸣潮 exe, 否则匹配不到远控窗口')
        self.assertIsNone(windows['hwnd_class'], 'UnrealWindow 类名会挡掉远控窗口')
        self.assertIsNone(windows['top_hwnd_class'])
        self.assertTrue(windows['title'].search('UU远程-被控电脑'))
        self.assertTrue(windows['title'].search('uu远程'), '应忽略大小写')

    def test_forces_pynput(self):
        manager = bare_device_manager()
        manager.set_stream_window('ToDesk')
        self.assertIs(manager.win_interaction_class, PynputInteraction)
        self.assertEqual(manager.config['interaction'], 'Pynput')

    def test_can_keep_configured_interaction(self):
        manager = bare_device_manager()
        manager.set_stream_window('Parsec', force_pynput=False)
        self.assertIsNone(manager.win_interaction_class)
        self.assertNotIn('interaction', manager.config)

    def test_empty_title_lists_all_windows(self):
        # 空标题 = 清掉所有过滤, 让 update_pc_device 枚举所有可见窗口供用户在下拉里选。
        manager = bare_device_manager()
        self.assertTrue(manager.set_stream_window('  '))
        self.assertTrue(manager.stream_window_mode)
        windows = manager.windows_capture_config
        self.assertIsNone(windows['exe'])
        self.assertIsNone(windows['title'])
        self.assertIsNone(windows['hwnd_class'])
        self.assertIsNone(windows['top_hwnd_class'])
        self.assertIs(manager.win_interaction_class, PynputInteraction)

    def test_none_title_lists_all_windows(self):
        manager = bare_device_manager()
        self.assertTrue(manager.set_stream_window(None))
        self.assertTrue(manager.stream_window_mode)
        self.assertIsNone(manager.windows_capture_config['title'])

    def test_without_windows_config(self):
        manager = bare_device_manager()
        manager.windows_capture_config = None
        self.assertFalse(manager.set_stream_window('UU远程'))
        self.assertFalse(manager.stream_window_mode)

    def test_accepts_compiled_pattern(self):
        manager = bare_device_manager()
        self.assertTrue(manager.set_stream_window(re.compile('SunloginClient', re.I)))
        self.assertTrue(manager.windows_capture_config['title'].search('SunloginClient 15.2'))

    def test_repoints_existing_window_and_disables_resize(self):
        manager = bare_device_manager()
        manager.hwnd_window = Mock()
        manager.set_stream_window('UU远程')
        manager.hwnd_window.update_window.assert_called_once()
        # 窗口标题已经换成远控窗口的正则, 不再带 exe / 窗口类
        title = manager.hwnd_window.update_window.call_args[0][0]
        self.assertTrue(title.search('UU远程'))
        # 远控窗口不能被程序自动 resize, 否则画面会变形/加黑边
        self.assertFalse(manager.hwnd_window.try_resize_to([(1920, 1080)]))


class ResolutionCheckTest(unittest.TestCase):

    def _manager(self, width, height, enabled=True):
        manager = bare_device_manager()
        manager.stream_window_mode = enabled
        manager.supported_ratio = 16 / 9
        manager.hwnd_window = SimpleNamespace(width=width, height=height,
                                              client_width=width, client_height=height)
        return manager

    def test_16_9_passes(self):
        for width, height in ((1920, 1080), (2560, 1440), (1280, 720)):
            self.assertIsNone(self._manager(width, height).check_stream_window_resolution())

    def test_16_10_warns(self):
        message = self._manager(1920, 1200).check_stream_window_resolution()
        self.assertIsNotNone(message)
        self.assertIn('16:9', message)
        self.assertIn('1920x1200', message)

    def test_skipped_when_disabled(self):
        self.assertIsNone(self._manager(1920, 1200, enabled=False).check_stream_window_resolution())

    def test_skipped_without_window(self):
        manager = self._manager(1920, 1080)
        manager.hwnd_window = None
        self.assertIsNone(manager.check_stream_window_resolution())


class UpdatePcDeviceTest(unittest.TestCase):

    def test_no_placeholder_when_window_missing(self):
        manager = bare_device_manager()
        manager.stream_window_mode = True
        manager.windows_capture_config['title'] = re.compile('UU远程', re.I)
        manager.windows_capture_config['hwnd_class'] = None
        manager.device_dict = {'pc_1': {'imei': 'pc_1'}}

        with patch('ok.device.DeviceManager.find_hwnd', return_value=(None, 0, None, 0, 0, 0, 0, [])):
            manager.update_pc_device()

        self.assertEqual(manager.device_dict, {},
                         '远控窗口没开时不应留下未连接设备, 否则会误报游戏路径不存在')

    def test_empty_filters_enumerate_all_windows(self):
        # 修复目标: 开了远控没填标题时, 下拉要列出所有窗口(含远控窗口),
        # 而不是只剩鸣潮 PC 客户端。set_stream_window(None) 把三个过滤都清空后
        # 就应命中这条枚举分支。
        manager = bare_device_manager()
        manager.set_stream_window(None)
        manager.device_dict = {}
        windows = [(10, 'DESKTOP-ABC - Moonlight', 'Moonlight.exe', 'C:\\moonlight.exe'),
                   (20, 'UU远程-被控电脑', 'UURemote.exe', 'C:\\uu.exe')]
        with patch('ok.util.window.find_all_visible_windows', return_value=windows), \
                patch('ok.util.window.get_window_bounds',
                      side_effect=[(0, 0, 0, 0, 1920, 1080, 1), (0, 0, 0, 0, 1600, 900, 1)]):
            manager.update_pc_device()

        self.assertEqual(len(manager.device_dict), 2)
        nicks = {d['nick'] for d in manager.device_dict.values()}
        self.assertIn('DESKTOP-ABC - Moonlight', nicks)
        self.assertIn('UU远程-被控电脑', nicks)


class GlobalsHookTest(unittest.TestCase):

    def test_globals_init_does_not_raise(self):
        from src.globals import Globals
        with patch('src.stream_window.apply_stream_window', return_value=False) as apply:
            Globals(exit_event=None)
        self.assertTrue(apply.called)


if __name__ == '__main__':
    unittest.main()
