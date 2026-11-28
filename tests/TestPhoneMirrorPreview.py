"""投屏预览的低延迟链路：画面通道复用 + 新帧序号。

以前预览窗口自己再开一条 socket 连到内核，内核要给两个客户端各拷一份全尺寸
NV12，两个 socket 各排一队；任一客户端慢一点，画面就越积越滞后。现在预览
优先接手任务正在用的那条通道，并用 frame_seq 只在画面真的换了时重画。
"""

import os
import sys
import struct
import unittest
from unittest.mock import patch

WORK = os.environ.get('OKWW_WORK', r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working")
os.chdir(WORK)
sys.path.insert(0, WORK)

from ok.device.capture_methods.phone_mirror_socket import PhoneMirrorSocketCaptureMethod  # noqa: E402
from src import phone_mirror_preview as preview  # noqa: E402


class PreviewChannelTest(unittest.TestCase):

    def tearDown(self):
        for capture in list(PhoneMirrorSocketCaptureMethod._instances):
            capture.close()

    def test_active_channel_is_found_and_removed_on_close(self):
        capture = PhoneMirrorSocketCaptureMethod(45678)
        capture._running = True
        capture._socket = object()  # 只要 connected() 认它是连着的就够了

        self.assertIs(PhoneMirrorSocketCaptureMethod.active_for_port(45678), capture)
        self.assertIsNone(PhoneMirrorSocketCaptureMethod.active_for_port(45679))

        capture.close()
        self.assertIsNone(PhoneMirrorSocketCaptureMethod.active_for_port(45678))

    def test_preview_reuses_existing_channel_instead_of_opening_a_second_one(self):
        shared = PhoneMirrorSocketCaptureMethod(45678)
        shared._running = True
        shared._socket = object()
        engine = type('Engine', (), {'port': 45678})()

        with patch.object(PhoneMirrorSocketCaptureMethod, 'active_for_port',
                          return_value=shared):
            capture, owned = preview._attach(engine)

        self.assertIs(capture, shared)
        self.assertFalse(owned, '复用任务的通道时，预览不能把自己当 owner')

    def test_preview_owns_a_fresh_channel_only_when_nothing_is_available(self):
        engine = type('Engine', (), {'port': 45678})()
        with patch.object(PhoneMirrorSocketCaptureMethod, 'active_for_port',
                          return_value=None), \
                patch.object(PhoneMirrorSocketCaptureMethod, 'start', return_value=True):
            capture, owned = preview._attach(engine)

        self.assertTrue(owned)
        self.assertTrue(getattr(capture, 'preview_owner', False))
        # start() 被 mock 掉了，手动把它置成"连上了"再查注册表。
        capture._running = True
        capture._socket = object()
        self.assertIs(PhoneMirrorSocketCaptureMethod.active_for_port(45678), capture)

    def test_every_incoming_frame_advances_the_sequence(self):
        capture = PhoneMirrorSocketCaptureMethod(45678)
        w, h = 8, 8
        payload = struct.pack('<III', w, h, w * h * 3 // 2) + bytes(w * h * 3 // 2)
        self.assertEqual(capture.frame_seq, 0)
        capture._on_frame(payload)
        capture._on_frame(payload)
        self.assertEqual(capture.frame_seq, 2)


if __name__ == '__main__':
    unittest.main()
