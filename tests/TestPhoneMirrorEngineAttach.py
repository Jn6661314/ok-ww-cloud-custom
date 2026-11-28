"""设备管理器接回投屏内核: 引擎对象丢了端口时的自愈。

现场(v1.8.29 之后): 日志里「内核就绪, 画面端口 50086」和「投屏内核还没
就绪, 请在手机上点允许」交替刷屏, 界面一直卡在「等待游戏启动」——
内核其实活得好好的, 只是 DeviceManager 手里的那个引擎对象 port 是 None。
以前这里只会干等 2 秒然后报错, 每 2 秒一轮, 永不成功。

现在: 引擎对象从没拉起过内核(process is None)时, 先让它自己 start() ——
start() 会读 link.json, 端口还通就直接复用, 不用重新在手机上点「允许」。
"""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import patch

WORK = os.environ.get('OKWW_WORK', r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working")
os.chdir(WORK)
sys.path.insert(0, WORK)

from ok.device.DeviceManager import DeviceManager  # noqa: E402
from ok.device.capture_methods.phone_mirror_socket import PhoneMirrorSocketCaptureMethod  # noqa: E402

PORT = 50086


def make_engine(port=None, process=None, running=False, on_start=None):
    engine = SimpleNamespace(port=port, process=process, running=running,
                             failure_reason='', start_calls=0)

    def start():
        engine.start_calls += 1
        if on_start is not None:
            on_start(engine)
        return True

    engine.start = start
    engine.wait_ready = lambda timeout=0.0: engine.port is not None
    return engine


def make_manager(engine, capture_method=None):
    return SimpleNamespace(phone_mirror_engine=engine,
                           capture_method=capture_method,
                           interaction=None,
                           exit_event=None)


class EngineAttachTest(unittest.TestCase):

    def tearDown(self):
        for capture in list(PhoneMirrorSocketCaptureMethod._instances):
            capture.close()

    def test_no_port_and_never_started_reattaches_the_running_engine(self):
        engine = make_engine(on_start=lambda e: setattr(e, 'port', PORT))
        manager = make_manager(engine)

        with patch.object(PhoneMirrorSocketCaptureMethod, 'active_for_port', return_value=None), \
                patch.object(PhoneMirrorSocketCaptureMethod, 'start', return_value=True):
            DeviceManager._use_phone_mirror_engine_capture(manager)

        self.assertEqual(engine.start_calls, 1, '引擎没端口时应该尝试接回已在运行的内核')
        self.assertEqual(manager.capture_method.port, PORT)

    def test_engine_that_already_ran_is_not_restarted(self):
        """process 有值说明这个对象起过内核(哪怕刚崩), 别在这里反复重启。"""
        engine = make_engine(process=SimpleNamespace(poll=lambda: 1))
        engine.wait_ready = lambda timeout=0.0: False
        manager = make_manager(engine)

        DeviceManager._use_phone_mirror_engine_capture(manager)

        self.assertEqual(engine.start_calls, 0)
        self.assertIsNone(manager.capture_method)

    def test_ready_engine_keeps_its_existing_channel(self):
        existing = PhoneMirrorSocketCaptureMethod(PORT)
        existing._running = True
        existing._socket = object()
        engine = make_engine(port=PORT)
        manager = make_manager(engine, capture_method=existing)

        DeviceManager._use_phone_mirror_engine_capture(manager)

        self.assertEqual(engine.start_calls, 0)
        self.assertIs(manager.capture_method, existing)
        self.assertTrue(existing.adopted_by_task)


if __name__ == '__main__':
    unittest.main()
