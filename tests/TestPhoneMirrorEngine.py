"""内置投屏引擎: socket 收帧 + 画面归一化 + 坐标换算 + 触控回传 + 配对二维码。

覆盖:
  1. ok/device/capture_methods/phone_mirror_socket: 收帧、裁黑边、归一化;
  2. ok/device/interaction_methods/phone_mirror: 点击/滑动变成手机上的触点;
  3. 坐标换算: 帧坐标 -> 手机屏幕比例(0..1);
  4. src/phone_mirror_pairing: 配对二维码能扫出原始链接。
"""

import os
import socket
import struct
import sys
import threading
import time
import unittest

import cv2
import numpy as np

WORK = os.environ.get('OKWW_WORK', r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working")
os.chdir(WORK)
sys.path.insert(0, WORK)

from ok.device.capture_methods.phone_mirror_socket import (  # noqa: E402
    KIND_FRAME, KIND_TOUCH, TOUCH_DOWN, TOUCH_UP, PhoneMirrorSocketCaptureMethod)
from ok.device.interaction_methods.phone_mirror import PhoneMirrorInteraction  # noqa: E402
from src import phone_mirror_engine, phone_mirror_pairing  # noqa: E402

CONTENT_COLOR = (30, 90, 180)


def bgr_to_nv12(image):
    """BGR -> NV12(和 sidecar 送过来的一致: BT.601 限幅)。"""
    blue = image[:, :, 0].astype(np.float32)
    green = image[:, :, 1].astype(np.float32)
    red = image[:, :, 2].astype(np.float32)
    y = 16.0 + (65.481 * red + 128.553 * green + 24.966 * blue) / 255.0
    u = 128.0 + (-37.797 * red - 74.203 * green + 112.0 * blue) / 255.0
    v = 128.0 + (112.0 * red - 93.786 * green - 18.214 * blue) / 255.0
    luma = np.clip(y, 0, 255).astype(np.uint8)
    cb = np.clip(u, 0, 255).astype(np.uint8)[0::2, 0::2]
    cr = np.clip(v, 0, 255).astype(np.uint8)[0::2, 0::2]
    uv = np.empty((luma.shape[0] // 2, luma.shape[1]), dtype=np.uint8)
    uv[:, 0::2] = cb
    uv[:, 1::2] = cr
    return np.vstack([luma, uv]).tobytes()


class FakeSidecar:
    """假装的投屏内核: 送一帧画面, 并记录收到的触控。"""

    def __init__(self, frame):
        self.frame = frame
        self.received = []
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind(('127.0.0.1', 0))
        self.server.listen(1)
        self.port = self.server.getsockname()[1]
        self.thread = threading.Thread(target=self._serve, daemon=True)
        self.thread.start()

    def _serve(self):
        try:
            conn, _ = self.server.accept()
        except OSError:
            return
        try:
            height, width = self.frame.shape[:2]
            pixels = bgr_to_nv12(self.frame)
            payload = struct.pack('<III', width, height, len(pixels)) + pixels
            conn.sendall(struct.pack('<BI', KIND_FRAME, len(payload)) + payload)
            while True:
                head = b''
                while len(head) < 5:
                    chunk = conn.recv(5 - len(head))
                    if not chunk:
                        return
                    head += chunk
                length = struct.unpack('<I', head[1:5])[0]
                body = b''
                while len(body) < length:
                    chunk = conn.recv(length - len(body))
                    if not chunk:
                        return
                    body += chunk
                self.received.append((head[0], body))
        except OSError:
            return
        finally:
            try:
                conn.close()
            except OSError:
                pass

    def close(self):
        try:
            self.server.close()
        except OSError:
            pass

def make_phone_frame(total=(400, 180), content=(320, 180)):
    """造一帧"手机画面": 两侧有黑边, 中间是 16:9 的内容。"""
    width, height = total
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    content_width, content_height = content
    x = (width - content_width) // 2
    frame[0:content_height, x:x + content_width] = CONTENT_COLOR
    return frame


class TestPhoneMirrorSocketCapture(unittest.TestCase):

    def setUp(self):
        self.frame = make_phone_frame()
        self.sidecar = FakeSidecar(self.frame)
        self.capture = PhoneMirrorSocketCaptureMethod(self.sidecar.port)
        self.capture.start()

    def tearDown(self):
        self.capture.close()
        self.sidecar.close()

    def _wait_for_frame(self, timeout=5.0):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            frame = self.capture.do_get_frame()
            if frame is not None:
                return frame
            time.sleep(0.05)
        return None

    def test_a_frame_arrives_and_the_black_border_is_cut(self):
        frame = self._wait_for_frame()
        self.assertIsNotNone(frame, '没有收到画面')
        # 两侧黑边被裁掉, 剩下的画面是 16:9, 高度归一化到 1080。
        self.assertEqual(frame.shape[1] / frame.shape[0], 16 / 9, f'比例不对: {frame.shape}')
        self.assertEqual(frame.shape[0], 1080)
        # 中间是内容色, 说明裁对了位置。
        self.assertGreater(int(frame[540, 960, 0]), 20)

    def test_coordinates_become_a_share_of_the_phone_screen(self):
        self.assertIsNotNone(self._wait_for_frame())
        # 画面区在整幅里的矩形: x=40, 宽 320(整幅 400), 归一化后 1920 宽。
        x, y = self.capture.normalize_point(960, 540)
        self.assertIsNotNone(x)
        self.assertAlmostEqual(x, (40 + 320 / 2) / 400, places=3)
        self.assertAlmostEqual(y, 0.5, places=3)
        # 左上角是画面区的左上, 不是整幅的左上。
        left, _ = self.capture.normalize_point(0, 0)
        self.assertAlmostEqual(left, 40 / 400, places=3)

    def test_a_click_becomes_a_touch_on_the_phone(self):
        self.assertIsNotNone(self._wait_for_frame())
        interaction = PhoneMirrorInteraction(self.capture)
        self.assertTrue(interaction.click(960, 540, down_time=0.01))
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline and len(self.sidecar.received) < 2:
            time.sleep(0.05)
        kinds = [kind for kind, _ in self.sidecar.received]
        self.assertEqual(kinds[:2], [KIND_TOUCH, KIND_TOUCH])
        first = struct.unpack('<Bff', self.sidecar.received[0][1])
        self.assertEqual(first[0], TOUCH_DOWN)
        self.assertAlmostEqual(first[1], (40 + 320 / 2) / 400, places=2)
        second = struct.unpack('<Bff', self.sidecar.received[1][1])
        self.assertEqual(second[0], TOUCH_UP)

    def test_the_picture_size_is_reported(self):
        self.assertIsNotNone(self._wait_for_frame())
        self.assertEqual(self.capture.screen_size(), (400, 180))
        self.assertEqual(self.capture.picture_size(), (320, 180))


class TestPhoneMirrorPairing(unittest.TestCase):

    # sidecar 实际发出的配对链接长这样: 178 个字符, 里面还有 URL 编码的
    # 冒号和逗号。短链接扫得动不代表长链接也扫得动, 所以用真的长度来测。
    REAL_URI = ('nectarlink://pair?v=0&id=u3kn9obp5qxgjkm9iqx4swhmbz878yjh7u4knfdmjf8961zn6dao'
                '&s=jbtJTgiG5oJ6lrKXWldoaQ&n=ok-ww&a=10.42.31.18%3A53312%2C'
                '192.168.61.1%3A53312%2C192.168.93.1%3A53312')

    def test_the_qr_code_carries_the_pairing_link(self):
        matrix = phone_mirror_pairing.qr_matrix(self.REAL_URI)
        self.assertIsNotNone(matrix)
        self.assertGreater(matrix.shape[0], 20)

    def test_the_qr_code_is_readable(self):
        """画出来的码必须能被扫回原文 —— 手机扫的是屏幕上那张图。"""
        image = phone_mirror_pairing.qr_image(self.REAL_URI)
        self.assertIsNotNone(image)
        data, _, _ = cv2.QRCodeDetector().detectAndDecode(image)
        self.assertEqual(data, self.REAL_URI)

    def test_the_qr_code_is_black_on_white(self):
        """手机扫码器认的是白底黑码; 黑底白码那种它扫不出来。

        OpenCV 的编码器输出的已经是标准极性(深色模块=0), 所以这里不能反相。
        """
        image = phone_mirror_pairing.qr_image(self.REAL_URI)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # 静区: 四周一圈必须是白的, 否则定位图案贴边, 手机扫不准。
        self.assertEqual(int(gray[0].min()), 255, '上边不是白的, 静区丢了')
        self.assertEqual(int(gray[-1].min()), 255, '下边不是白的, 静区丢了')
        self.assertEqual(int(gray[:, 0].min()), 255, '左边不是白的, 静区丢了')
        self.assertEqual(int(gray[:, -1].min()), 255, '右边不是白的, 静区丢了')
        # 深色模块要占一部分, 但不能是全部 —— 全黑就成黑底白码了。
        dark = int((gray < 128).sum())
        self.assertGreater(dark, gray.size // 5, '深色模块太少, 极性可能反了')
        self.assertLess(dark, gray.size * 4 // 5, '深色模块太多, 极性可能反了')

    def test_inverting_the_code_breaks_it(self):
        """反相之后扫不出来 —— 这正是不该反相的理由。"""
        image = phone_mirror_pairing.qr_image(self.REAL_URI)
        inverted = 255 - image
        data, _, _ = cv2.QRCodeDetector().detectAndDecode(inverted)
        self.assertNotEqual(data, self.REAL_URI,
                            '反相的码居然也能扫出来, 那极性判断就不可靠了')

    def test_the_qr_code_becomes_a_pixmap(self):
        """转成 Qt 位图这一步以前会把图转成空的, 界面上就成了一块白板。"""
        image = phone_mirror_pairing.qr_image(self.REAL_URI)
        pixmap = phone_mirror_pairing._to_pixmap(image)
        self.assertIsNotNone(pixmap, '二维码没能转成位图')
        self.assertFalse(pixmap.isNull(), '位图是空的')
        self.assertEqual(pixmap.width(), image.shape[1])
        self.assertEqual(pixmap.height(), image.shape[0])

    def test_a_broken_link_gives_no_pixmap(self):
        """出错了要返回 None, 而不是画一张空白图。"""
        self.assertIsNone(phone_mirror_pairing.qr_image(''))
        self.assertIsNone(phone_mirror_pairing._to_pixmap(None))


class TestPhoneMirrorStatus(unittest.TestCase):
    """内核在同一条 socket 上发状态行, ok-ww 要真的用起来。"""

    def _capture(self):
        capture = PhoneMirrorSocketCaptureMethod(59999)
        return capture

    def test_a_config_line_is_read(self):
        capture = self._capture()
        try:
            capture._on_status(b'{"type":"config","codec":"h264","width":1080,"height":2340}')
            self.assertEqual(capture.status.get('type'), 'config')
            self.assertEqual(capture.status.get('codec'), 'h264')
        finally:
            capture.close()

    def test_the_stream_ending_drops_the_cached_frame(self):
        """手机停了投屏之后, 不能继续拿旧画面当实时画面用。"""
        capture = self._capture()
        try:
            capture._on_frame(struct.pack('<III', 320, 180, 320 * 180 * 3 // 2)
                              + b'\x80' * (320 * 180 * 3 // 2))
            self.assertIsNotNone(capture.do_get_frame(), '应该先有画面')
            capture._on_status(b'{"type":"ended"}')
            self.assertIsNone(capture.do_get_frame(), '投屏结束后不该再返回旧画面')
            self.assertIsNotNone(capture.last_error)
        finally:
            capture.close()

    def test_an_error_line_becomes_the_last_error(self):
        capture = self._capture()
        try:
            capture._on_status(b'{"type":"error","message":"decode failed"}')
            self.assertEqual(capture.last_error, 'decode failed')
        finally:
            capture.close()

    def test_a_broken_line_is_ignored(self):
        capture = self._capture()
        try:
            capture._on_status(b'not json at all')
            self.assertEqual(capture.status, {})
            self.assertIsNone(capture.last_error)
        finally:
            capture.close()


class TestSidecarOutput(unittest.TestCase):
    """内核的状态走 stdout, 每一行一条 JSON。"""

    def test_a_normal_line_is_one_message(self):
        messages = phone_mirror_engine._parse_status_lines('{"type":"ready","port":1234}')
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['type'], 'ready')

    def test_a_prompt_glued_to_a_message_does_not_swallow_it(self):
        """内核往 stdout 写了别的东西, 后面的消息不能跟着一起丢。"""
        line = ('Does the other device show 123 456? [y/N] '
                '{"type":"paired","id":"abc","name":"phone"}')
        messages = phone_mirror_engine._parse_status_lines(line)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['type'], 'paired')
        self.assertEqual(messages[0]['id'], 'abc')

    def test_two_messages_on_one_line_are_both_found(self):
        line = '{"type":"ready","port":1}{"type":"sas","code":"123456"}'
        messages = phone_mirror_engine._parse_status_lines(line)
        self.assertEqual([m['type'] for m in messages], ['ready', 'sas'])

    def test_braces_inside_a_string_do_not_confuse_the_scanner(self):
        line = '{"type":"error","message":"bad { thing } here"}'
        messages = phone_mirror_engine._parse_status_lines(line)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['message'], 'bad { thing } here')

    def test_a_line_without_json_gives_nothing(self):
        self.assertEqual(phone_mirror_engine._parse_status_lines('just some text'), [])

    def test_an_escaped_quote_inside_a_string(self):
        line = r'{"type":"error","message":"say \"hi\""}'
        messages = phone_mirror_engine._parse_status_lines(line)
        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0]['message'], 'say "hi"')


if __name__ == '__main__':
    unittest.main()
