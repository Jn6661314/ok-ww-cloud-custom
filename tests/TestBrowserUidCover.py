"""云游戏 UID 遮罩: WebRTC 捕获源下的像素级遮罩测试.

背景: 遮罩原实现只是注入 DOM 覆盖层(position:fixed 黑条), 但 WebRTC
捕获模式直接读取页面视频流的解码帧, 不经过页面合成 —— DOM 覆盖层
进不了帧, 截图/日志会泄露右下角 UID(遮罩失效, 2026-11-25 上游合入
WebRTC 捕获 00cb86c 后暴露)。修复为在取帧路径上按相同比例直接涂黑帧像素。
"""
import sys
import unittest

import numpy as np

sys.path.insert(0, r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working")

from ok.device.capture_methods.browser import (BrowserCaptureMethod,
                                               UID_COVER_HEIGHT,
                                               UID_COVER_WIDTH)


def make_method(cover=True):
    method = BrowserCaptureMethod.__new__(BrowserCaptureMethod)
    method._cover_uid = cover
    return method


class TestUidCoverOnFrame(unittest.TestCase):
    def test_masks_bottom_right_region(self):
        frame = np.full((1080, 1920, 3), 200, dtype=np.uint8)
        out = make_method(True)._apply_uid_cover(frame)
        self.assertIs(out, frame, "应原地涂黑并返回同一帧")
        bar_w = round(1920 * UID_COVER_WIDTH)
        bar_h = round(1080 * UID_COVER_HEIGHT)
        self.assertEqual(bar_w, 250)
        self.assertEqual(bar_h, 27)
        # 遮罩区域内全黑
        self.assertEqual(int(out[1080 - bar_h:, 1920 - bar_w:].max()), 0)
        # 遮罩区域外保持原值(上一行 / 左边一列)
        self.assertEqual(int(out[1080 - bar_h - 1, :].min()), 200)
        self.assertEqual(int(out[:, 1920 - bar_w - 1].min()), 200)

    def test_other_resolutions(self):
        for height, width in ((720, 1280), (900, 1600), (1080, 1920)):
            frame = np.full((height, width, 3), 128, dtype=np.uint8)
            make_method(True)._apply_uid_cover(frame)
            bar_w = max(1, round(width * UID_COVER_WIDTH))
            bar_h = max(1, round(height * UID_COVER_HEIGHT))
            self.assertEqual(int(frame[height - bar_h:, width - bar_w:].max()), 0)
            self.assertEqual(int(frame[:height - bar_h, :].min()), 128)

    def test_toggle_off_keeps_frame(self):
        frame = np.full((1080, 1920, 3), 200, dtype=np.uint8)
        out = make_method(False)._apply_uid_cover(frame)
        self.assertEqual(int(out.min()), 200, "关闭遮罩后帧不应被修改")

    def test_none_frame(self):
        self.assertIsNone(make_method(True)._apply_uid_cover(None))

    def test_default_enabled_when_attribute_missing(self):
        method = BrowserCaptureMethod.__new__(BrowserCaptureMethod)
        self.assertFalse(hasattr(method, '_cover_uid'))
        frame = np.full((1080, 1920, 3), 200, dtype=np.uint8)
        method._apply_uid_cover(frame)
        self.assertEqual(int(frame[-1, -1].max()), 0, "配置缺失时默认开启遮罩")


if __name__ == '__main__':
    unittest.main(verbosity=2)
