"""手机投屏(NectarLink)支持: 用真机投屏代替 MuMu 模拟器驱动鸣潮。

背景:
  NectarLink 桌面端把手机画面开成一个独立窗口(标题 "<设备名> · NectarLink"),
  并把鼠标点击按**屏幕比例**转发到手机(desktop/app/qml/MirrorWindow.qml 的
  video.at() -> Mirror.touch)。因此把这个窗口当普通 Windows 窗口抓屏 + 真实
  键鼠点击, 就等于在操作手机, 而且坐标由投屏软件自动换算, 不再有横竖屏/缩放/
  黑边导致的偏移 —— 这正是模拟器上反复出问题的那个坑。

覆盖:
1. src.phone_mirror: 窗口标题识别 + 手机端下载地址;
2. config.py: 「手机投屏(NectarLink)」配置项注册、下载按钮、远控预设新增选项;
3. src.stream_window: NectarLink 预设 -> 标题正则; 手机投屏模式能识别出来;
4. DeviceManager.set_stream_window(phone=True): 打上 phone_mirror 标记;
5. DeviceManager.update_pc_device: 投屏窗口的设备条目带 phone_mirror 标记;
6. BaseWWTask.is_adb(): 手机投屏设备按安卓端处理(编队识别/切人走安卓分支);
7. 手机投屏不做 16:9 裁剪、不做 16:9 比例告警、不尝试启动本机游戏。
"""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

WORK = os.environ.get('OKWW_WORK', r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working")
os.chdir(WORK)
sys.path.insert(0, WORK)

import config  # noqa: E402
from ok.device.DeviceManager import DeviceManager  # noqa: E402
from src import phone_mirror, stream_window  # noqa: E402


def bare_device_manager():
    """不走 __init__, 只装手机投屏相关逻辑需要的属性。"""
    manager = object.__new__(DeviceManager)
    manager.stream_window_mode = False
    manager.phone_mirror_mode = False
    manager.win_interaction_class = None
    manager.hwnd_window = None
    manager.config = {}
    manager.device_dict = {}
    manager.windows_capture_config = {
        'exe': ['Client-Win64-Shipping.exe'],
        'title': None,
        'hwnd_class': 'UnrealWindow',
        'top_hwnd_class': ['CAgreementDlg'],
    }
    return manager


class PhoneMirrorModuleTest(unittest.TestCase):

    def test_apk_url_is_the_netdisk_share(self):
        self.assertEqual(phone_mirror.ANDROID_MIRROR_APK_URL,
                         'https://pan.baidu.com/s/13Y-rkKtfp7EQHd4SJwdzDA?pwd=Jn66')

    def test_nectarlink_window_is_recognized(self):
        self.assertTrue(phone_mirror.is_nectarlink_window('我的手机 · NectarLink'))
        self.assertTrue(phone_mirror.is_nectarlink_window('Pixel 9 Pro · NectarLink'))
        # 桌面主界面不是投屏窗口
        self.assertFalse(phone_mirror.is_nectarlink_window('NectarLink'))
        self.assertFalse(phone_mirror.is_nectarlink_window('鸣潮'))
        self.assertFalse(phone_mirror.is_nectarlink_window(''))
        self.assertFalse(phone_mirror.is_nectarlink_window(None))

    def test_open_apk_uses_browser(self):
        with patch('webbrowser.open') as opener:
            self.assertTrue(phone_mirror.open_android_mirror_apk())
        opener.assert_called_once_with(phone_mirror.ANDROID_MIRROR_APK_URL)


class ConfigTest(unittest.TestCase):

    def test_phone_mirror_option_registered(self):
        names = [option.name for option in config.config['global_configs']]
        self.assertIn('手机投屏', names)

    def test_only_one_phone_mirror_menu(self):
        """两个投屏菜单已经合成一个, 不能再出现第二个。"""
        names = [option.name for option in config.config['global_configs']]
        phone_menus = [n for n in names if '手机投屏' in n]
        self.assertEqual(phone_menus, ['手机投屏'],
                         f'手机投屏只能有一个菜单, 实际有: {phone_menus}')

    def test_phone_mirror_option_has_download_button(self):
        option = next(o for o in config.config['global_configs']
                      if o.name == '手机投屏')
        button = option.config_type['下载手机端']
        self.assertEqual(button['type'], 'button')
        self.assertTrue(callable(button['callback']))
        self.assertIn('网盘', button['text'])

    def test_phone_mirror_option_has_apk_url(self):
        option = next(o for o in config.config['global_configs']
                      if o.name == '手机投屏')
        self.assertEqual(option.default_config['手机端下载地址'],
                         phone_mirror.ANDROID_MIRROR_APK_URL)

    def test_phone_mirror_option_has_mode_switch(self):
        """模式下拉要有内置引擎和桌面端两个选项。"""
        option = next(o for o in config.config['global_configs']
                      if o.name == '手机投屏')
        mode = option.config_type['模式']
        self.assertEqual(mode['type'], 'drop_down')
        self.assertEqual(mode['options'], ['内置引擎', '桌面端'])
        self.assertEqual(option.default_config['模式'], '内置引擎')

    def test_phone_mirror_option_keeps_engine_settings(self):
        """合并后内置引擎的设置项都还在(不能因为合并丢了功能)。"""
        option = next(o for o in config.config['global_configs']
                      if o.name == '手机投屏')
        for key in ('Enable', '手机', '画面宽度', '帧率', '码率',
                    '配对手机', '启动投屏内核', '下载手机端', '手机端下载地址'):
            self.assertIn(key, option.default_config, f'缺少设置项 {key}')
        self.assertTrue(callable(option.config_type['配对手机']['callback']))
        self.assertTrue(callable(option.config_type['启动投屏内核']['callback']))

    def test_stream_preset_lists_nectarlink(self):
        option = next(o for o in config.config['global_configs']
                      if o.name == stream_window.STREAM_CONFIG_NAME)
        options = option.config_type['Preset']['options']
        self.assertIn('NectarLink 手机投屏', options)


class StreamWindowTest(unittest.TestCase):

    def test_preset_title_matches_nectarlink_window(self):
        pattern = stream_window.preset_title('NectarLink 手机投屏')
        self.assertTrue(pattern)
        import re
        self.assertTrue(re.search(pattern, '我的手机 · NectarLink'))

    def test_phone_mirror_preset_detected(self):
        self.assertTrue(stream_window.is_phone_mirror('NectarLink 手机投屏'))
        self.assertFalse(stream_window.is_phone_mirror('Moonlight'))
        self.assertFalse(stream_window.is_phone_mirror(''))

    def test_settings_report_phone_mode(self):
        option = SimpleNamespace(get_config=lambda _name: {
            'Enable': True, 'Preset': 'NectarLink 手机投屏',
            'Window Title': '', 'Force Pynput': True,
        })
        enabled, title, force_pynput = stream_window.stream_window_settings(option)
        self.assertTrue(enabled)
        self.assertTrue(title)
        self.assertTrue(force_pynput)
        self.assertTrue(stream_window.stream_window_phone_mode(option),
                        'NectarLink 预设必须被识别为手机投屏')

    def test_settings_not_phone_for_other_presets(self):
        option = SimpleNamespace(get_config=lambda _name: {
            'Enable': True, 'Preset': 'Moonlight',
            'Window Title': '', 'Force Pynput': True,
        })
        self.assertFalse(stream_window.stream_window_phone_mode(option))

    def test_apply_passes_phone_flag(self):
        manager = Mock()
        manager.set_stream_window.return_value = True
        option = SimpleNamespace(get_config=lambda _name: {
            'Enable': True, 'Preset': 'NectarLink 手机投屏',
            'Window Title': '', 'Force Pynput': True,
        })
        self.assertTrue(stream_window.apply_stream_window(option, manager))
        self.assertTrue(manager.set_stream_window.call_args.kwargs['phone'])


class DeviceManagerTest(unittest.TestCase):

    def test_set_stream_window_marks_phone_mirror(self):
        manager = bare_device_manager()
        self.assertTrue(manager.set_stream_window(r'·\s+NectarLink$', phone=True))
        self.assertTrue(manager.phone_mirror_mode)
        self.assertTrue(manager.stream_window_mode)
        # exe/class 过滤要清掉, 否则只会抓到鸣潮客户端
        self.assertIsNone(manager.windows_capture_config['exe'])
        self.assertIsNone(manager.windows_capture_config['hwnd_class'])

    def test_set_stream_window_without_phone(self):
        manager = bare_device_manager()
        manager.set_stream_window(r'UU远程', phone=False)
        self.assertFalse(manager.phone_mirror_mode)

    def test_pc_device_entry_marked_as_phone_mirror(self):
        manager = bare_device_manager()
        manager.phone_mirror_mode = True
        manager.windows_capture_config['title'] = 'x'
        with patch('ok.device.DeviceManager.find_hwnd',
                   return_value=('手机', 12345, '', 0, 0, 1080, 1920, [])), \
             patch('ok.device.DeviceManager.logger'):
            manager.update_pc_device()
        entry = manager.device_dict['pc_12345']
        self.assertTrue(entry['phone_mirror'], '手机投屏窗口的设备条目必须带标记')
        self.assertEqual(entry['device'], 'windows', '抓屏与输入仍走 windows 链路')

    def test_no_phone_marker_for_normal_stream_window(self):
        manager = bare_device_manager()
        manager.phone_mirror_mode = False
        manager.windows_capture_config['title'] = 'x'
        with patch('ok.device.DeviceManager.find_hwnd',
                   return_value=('远控', 999, '', 0, 0, 1920, 1080, [])), \
             patch('ok.device.DeviceManager.logger'):
            manager.update_pc_device()
        entry = manager.device_dict['pc_999']
        self.assertNotIn('phone_mirror', entry)

    def test_get_exe_path_returns_none_for_phone_mirror(self):
        manager = bare_device_manager()
        manager.phone_mirror_mode = True
        device = {'device': 'windows', 'full_path': r'C:\some\wuthering waves.exe'}
        self.assertIsNone(manager.get_exe_path(device),
                          '手机投屏时游戏在手机上, 不能去启动本机 exe')

    def test_no_16_9_warning_for_phone_mirror(self):
        manager = bare_device_manager()
        manager.stream_window_mode = True
        manager.phone_mirror_mode = True
        manager.hwnd_window = SimpleNamespace(width=1080, height=2400,
                                              client_width=1080, client_height=2400)
        with patch('ok.device.DeviceManager.communicate') as comm:
            manager.check_stream_window_resolution()
        self.assertFalse(comm.notification.emit.called,
                         '手机画面不是 16:9, 不该弹 16:9 告警')


class IsAdbTest(unittest.TestCase):
    """BaseWWTask.is_adb 覆盖: 手机投屏设备按安卓端处理。"""

    def _task(self, device):
        from src.task.BaseWWTask import BaseWWTask
        task = object.__new__(BaseWWTask)
        task._executor = SimpleNamespace(
            device_manager=SimpleNamespace(get_preferred_device=lambda: device))
        return task

    def test_phone_mirror_is_adb(self):
        task = self._task({'device': 'windows', 'phone_mirror': True})
        self.assertTrue(task.is_adb(), '手机投屏必须按安卓端处理(编队识别/切人)')

    def test_normal_windows_is_not_adb(self):
        task = self._task({'device': 'windows'})
        self.assertFalse(task.is_adb())

    def test_real_adb_is_adb(self):
        task = self._task({'device': 'adb'})
        self.assertTrue(task.is_adb())

    def test_no_device_returns_none(self):
        task = self._task(None)
        self.assertIsNone(task.is_adb())


if __name__ == '__main__':
    unittest.main()
