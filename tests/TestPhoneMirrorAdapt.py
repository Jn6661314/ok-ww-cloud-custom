"""手机投屏(NectarLink)画面自适应: 裁工具条/黑边 + 归一化分辨率 + 坐标换算。

背景:
  NectarLink 投屏窗口的客户区里并不只有手机画面:
    * 顶部或底部有一条工具条(源码 MirrorWindow.qml 的 ``strip``, 高度 52/96,
      底色 ``#121212``);
    * 手机画面按 KeepAspectRatio 居中, 窗口比例和手机比例不一致时四周出现纯黑边;
    * 用户拖动窗口时 NectarLink 会在 250ms 后把窗口改回手机比例, 改回之前画面
      是拉伸变形的。
  直接抓整个客户区, 帧比例既不是 16:9 也不是手机比例, 于是框架报
  "resolution error 2560x1494", 识图与点击坐标也整体偏移。

覆盖:
  1. src.phone_mirror.detect_strip_rows: 认出 52/96 像素的工具条;
  2. src.phone_mirror.detect_picture_rect: 裁掉工具条与黑边, 只留手机画面;
  3. src.phone_mirror.normalize_picture_size: 等比归一化到模板原生高度;
  4. ok/device/capture_methods/phone_mirror: 裁剪 + 归一化 + 坐标换算;
  5. DeviceManager.maximize_phone_mirror_window: 自动最大化投屏窗口;
  6. BaseWWTask.find_best_match_in_box_with_frame: 编队识别支持指定画面。
"""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

WORK = os.environ.get('OKWW_WORK', r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working")
os.chdir(WORK)
sys.path.insert(0, WORK)

from src import phone_mirror  # noqa: E402
from ok.device.capture_methods.phone_mirror import PhoneMirrorCaptureMethod  # noqa: E402


STRIP_COLOR = (18, 18, 18)  # #121212
PICTURE_COLOR = (30, 90, 180)


def make_frame(width=1920, height=1080, strip_rows=0, strip_at='top',
               picture_rect=(100, 200, 1720, 700)):
    """造一帧投屏窗口画面: 纯黑客户区 + 一条工具条 + 一块手机画面。"""
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    x, y, w, h = picture_rect
    frame[y:y + h, x:x + w] = PICTURE_COLOR
    if strip_rows:
        if strip_at == 'top':
            frame[0:strip_rows] = STRIP_COLOR
        else:
            frame[height - strip_rows:height] = STRIP_COLOR
    return frame


class StripDetectionTest(unittest.TestCase):

    def test_top_strip_is_found(self):
        gray = phone_mirror.to_gray(make_frame(strip_rows=96, strip_at='top'))
        strip = phone_mirror.detect_strip_rows(gray)
        self.assertIsNotNone(strip, '顶部的 96 像素工具条必须被认出来')
        self.assertEqual(strip, (0, 96))

    def test_bottom_strip_is_found(self):
        gray = phone_mirror.to_gray(make_frame(strip_rows=52, strip_at='bottom'))
        strip = phone_mirror.detect_strip_rows(gray)
        self.assertIsNotNone(strip, '底部的 52 像素工具条必须被认出来')
        self.assertEqual(strip, (1080 - 52, 1080))

    def test_no_strip_when_picture_fills_window(self):
        gray = phone_mirror.to_gray(make_frame(picture_rect=(0, 0, 1920, 1080)))
        self.assertIsNone(phone_mirror.detect_strip_rows(gray),
                          '没有工具条时不能瞎报')

    def test_dark_picture_is_not_mistaken_for_strip(self):
        # 整幅画面都很暗(中位数落在工具条灰度区间)也不该被当成工具条:
        # 工具条是**边缘**的连续块, 且高度要接近 52/96。
        frame = make_frame(picture_rect=(0, 0, 1920, 1080))
        frame[:, :] = (16, 16, 16)
        gray = phone_mirror.to_gray(frame)
        strip = phone_mirror.detect_strip_rows(gray)
        self.assertIsNone(strip)


class PictureRectTest(unittest.TestCase):

    def test_strip_and_black_bars_are_removed(self):
        frame = make_frame(strip_rows=96, strip_at='top', picture_rect=(100, 200, 1720, 700))
        rect = phone_mirror.detect_picture_rect(frame)
        self.assertIsNotNone(rect)
        x, y, w, h = rect
        self.assertEqual((x, w), (100, 1720), '左右黑边要被裁掉')
        self.assertEqual(h, 700, '画面高度要被裁对')
        # 坐标是相对客户区的原始坐标(工具条占掉的上方 96 像素要算进去,
        # 点击坐标换算才不会再偏 96 像素)。
        self.assertEqual(y, 200)

    def test_bottom_strip_is_removed(self):
        frame = make_frame(strip_rows=52, strip_at='bottom', picture_rect=(100, 200, 1720, 700))
        rect = phone_mirror.detect_picture_rect(frame)
        self.assertIsNotNone(rect)
        x, y, w, h = rect
        self.assertEqual((x, y, w, h), (100, 200, 1720, 700))

    def test_full_window_picture(self):
        frame = make_frame(picture_rect=(0, 0, 1920, 1080))
        rect = phone_mirror.detect_picture_rect(frame)
        self.assertEqual(rect, (0, 0, 1920, 1080))

    def test_black_frame_has_no_rect(self):
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        self.assertIsNone(phone_mirror.detect_picture_rect(frame),
                          '整幅全黑时不该硬猜一个画面区')

    def test_bgra_frame_is_accepted(self):
        frame = make_frame(strip_rows=96, picture_rect=(100, 200, 1720, 700))
        bgra = np.dstack([frame, np.full(frame.shape[:2], 255, dtype=np.uint8)])
        rect = phone_mirror.detect_picture_rect(bgra)
        self.assertIsNotNone(rect)


class NormalizeSizeTest(unittest.TestCase):

    def test_native_1080_is_unchanged(self):
        self.assertEqual(phone_mirror.normalize_picture_size((2400, 1080)), (2400, 1080))

    def test_small_picture_is_scaled_up(self):
        width, height = phone_mirror.normalize_picture_size((1720, 700))
        self.assertEqual(height, 1080)
        self.assertEqual(width, round(1720 * 1080 / 700))

    def test_large_picture_is_scaled_down(self):
        width, height = phone_mirror.normalize_picture_size((3840, 2160))
        self.assertEqual(height, 1080)
        self.assertEqual(width, 1920)

    def test_ratio_is_kept(self):
        width, height = phone_mirror.normalize_picture_size((2400, 900))
        self.assertAlmostEqual(width / height, 2400 / 900, places=2)

    def test_invalid_size_passes_through(self):
        self.assertEqual(phone_mirror.normalize_picture_size((0, 0)), (0, 0))


class FakeInnerCapture:

    def __init__(self, frame, origin=(100, 200)):
        self.frame = frame
        self.origin = origin
        self.closed = False

    def do_get_frame(self):
        return self.frame

    def get_abs_cords(self, x, y):
        return self.x_offset(x), self.y_offset(y)

    def x_offset(self, x):
        return self.origin[0] + x

    def y_offset(self, y):
        return self.origin[1] + y

    def connected(self):
        return True

    def clickable(self):
        return True

    def close(self):
        self.closed = True

    def get_name(self):
        return 'Fake'


class PhoneMirrorCaptureMethodTest(unittest.TestCase):

    def _capture(self, **kwargs):
        frame = make_frame(**kwargs)
        inner = FakeInnerCapture(frame)
        return PhoneMirrorCaptureMethod(inner), inner

    def test_frame_is_cropped_and_normalized(self):
        capture, _ = self._capture(strip_rows=96, picture_rect=(100, 200, 1720, 700))
        adapted = capture.adapt_frame(make_frame(strip_rows=96, picture_rect=(100, 200, 1720, 700)))
        self.assertEqual(adapted.shape[0], 1080, '画面必须归一化到 1080 高')
        self.assertEqual(adapted.shape[1], round(1720 * 1080 / 700))
        self.assertEqual(capture.picture_rect, (100, 200, 1720, 700))

    def test_click_coordinates_are_mapped_back(self):
        capture, inner = self._capture(strip_rows=96, picture_rect=(100, 200, 1720, 700))
        capture.adapt_frame(make_frame(strip_rows=96, picture_rect=(100, 200, 1720, 700)))
        scale = 1080 / 700
        abs_x, abs_y = capture.get_abs_cords(0, 0)
        self.assertAlmostEqual(abs_x, inner.origin[0] + 100, places=3)
        self.assertAlmostEqual(abs_y, inner.origin[1] + 200, places=3)
        # 画面右下角 -> 客户区右下角(归一化取整会带来 1 像素内的误差)
        abs_x, abs_y = capture.get_abs_cords(capture.width, capture.height)
        self.assertAlmostEqual(abs_x, inner.origin[0] + 100 + 1720, delta=1)
        self.assertAlmostEqual(abs_y, inner.origin[1] + 200 + 700, delta=1)
        self.assertAlmostEqual(scale, 1080 / 700, places=6)

    def test_no_rect_falls_back_to_whole_window(self):
        black = np.zeros((1080, 1920, 3), dtype=np.uint8)
        inner = FakeInnerCapture(black)
        capture = PhoneMirrorCaptureMethod(inner)
        adapted = capture.adapt_frame(black)
        self.assertEqual(adapted.shape[:2], (1080, 1920))
        self.assertIsNone(capture.picture_rect)
        abs_x, abs_y = capture.get_abs_cords(5, 6)
        self.assertEqual((abs_x, abs_y), (inner.origin[0] + 5, inner.origin[1] + 6))

    def test_proxy_methods(self):
        capture, inner = self._capture()
        self.assertTrue(capture.connected())
        self.assertTrue(capture.clickable())
        self.assertIn('Fake', capture.get_name())
        capture.close()
        self.assertTrue(inner.closed)


class MaximizePhoneMirrorTest(unittest.TestCase):

    def _manager(self):
        from ok.device.DeviceManager import DeviceManager
        manager = object.__new__(DeviceManager)
        manager._phone_mirror_maximized_hwnd = 0
        window = SimpleNamespace(hwnd=1234, width=1920, height=1080,
                                  do_update_window_size=Mock())
        manager.hwnd_window = window
        return manager, window

    def test_window_is_maximized_once(self):
        manager, window = self._manager()
        with patch('win32gui.IsWindow', return_value=True), \
             patch('win32gui.IsIconic', return_value=False), \
             patch('win32gui.ShowWindow') as show:
            self.assertTrue(manager.maximize_phone_mirror_window())
            show.assert_called_once()
        self.assertEqual(manager._phone_mirror_maximized_hwnd, 1234)
        # 同一个窗口不重复抢
        with patch('win32gui.IsWindow', return_value=True), \
             patch('win32gui.ShowWindow') as show:
            self.assertTrue(manager.maximize_phone_mirror_window())
            show.assert_not_called()

    def test_missing_window_is_noop(self):
        from ok.device.DeviceManager import DeviceManager
        manager = object.__new__(DeviceManager)
        manager._phone_mirror_maximized_hwnd = 0
        manager.hwnd_window = None
        self.assertFalse(manager.maximize_phone_mirror_window())
        manager.hwnd_window = SimpleNamespace(hwnd=0, width=0, height=0,
                                             do_update_window_size=Mock())
        self.assertFalse(manager.maximize_phone_mirror_window())


class BestMatchWithFrameTest(unittest.TestCase):
    """编队识别必须在缩小后的队伍栏画布上匹配(find_best_match_in_box 没有 frame 参数)。"""

    def _task(self):
        from src.task.BaseWWTask import BaseWWTask
        task = object.__new__(BaseWWTask)
        task.find_one = Mock(side_effect=lambda name, **kwargs: (
            SimpleNamespace(confidence=0.9, name=name)
            if name == 'char_bright' else None))
        return task

    def test_picks_highest_confidence(self):
        task = self._task()
        canvas = np.zeros((1080, 1920, 3), dtype=np.uint8)
        box = SimpleNamespace(x=0, y=0, width=40, height=40)
        matched = task.find_best_match_in_box_with_frame(
            box, ['char_dark', 'char_bright'], 0.7, canvas)
        self.assertIsNotNone(matched)
        self.assertEqual(matched.name, 'char_bright')
        # 每一都要把画布传下去
        for call in task.find_one.call_args_list:
            self.assertIs(call.kwargs['frame'], canvas)

    def test_upstream_find_best_match_in_box_has_no_frame_parameter(self):
        """守住这个坑: 上游签名没有 frame, 直接传会 TypeError。"""
        import inspect
        from ok.task.task import FindFeature
        signature = inspect.signature(FindFeature.find_best_match_in_box)
        self.assertNotIn('frame', signature.parameters)


if __name__ == '__main__':
    unittest.main()
