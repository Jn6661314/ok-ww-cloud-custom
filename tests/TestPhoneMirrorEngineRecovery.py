"""投屏内核起不来时的自恢复: 真实原因、残留内核清理、模式切换。

覆盖:
  1. 内核报错(stderr + stdout 的 error 行)能被 ok-ww 读到并说给用户;
  2. 残留内核会被清掉 —— 两个内核用同一个设备身份会互相干扰;
  3. 点「配对手机」时, 跑着普通内核要换成配对内核;
  4. 查进程的办法不会误杀(尤其不能拿 os.kill(pid, 0) 试探, 那在 Windows 上
     是直接 TerminateProcess);
  5. 手机端把这台设备的自动重连关掉(v1.8.24)时, 别看错成"手机没上线"。

这些是 v1.8.23 修的东西: 以前内核一起来就因为「设备离线」退出, 而它的
报错被丢进了 DEVNULL, 界面上只剩一句「投屏内核还没就绪」。
"""

import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

WORK = os.environ.get('OKWW_WORK', r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working")
os.chdir(WORK)
sys.path.insert(0, WORK)

from src import phone_mirror_engine  # noqa: E402

# 假内核: 冒充 sidecar, 按参数说不同的话。
FAKE_SIDECAR = r'''
import sys, time
mode = sys.argv[1] if len(sys.argv) > 1 else 'ready'
if mode == 'error':
    print('{"type":"error","message":"the phone did not agree to share its screen: device is offline"}', flush=True)
    print('Error: "the phone did not agree to share its screen: device is offline"', file=sys.stderr, flush=True)
    sys.exit(1)
if mode == 'stderr-only':
    print('Error: "device is offline"', file=sys.stderr, flush=True)
    sys.exit(1)
if mode == 'noise':
    print('2026-01-01T00:00:00Z  INFO nectarlink_core::node: node started device=abc', file=sys.stderr, flush=True)
    print('2026-01-01T00:00:00Z  INFO swarm_discovery::socket: Added interface 10.0.0.1', file=sys.stderr, flush=True)
    print('Error: "the phone did not agree to share its screen: device is offline"', file=sys.stderr, flush=True)
    sys.exit(1)
if mode == 'waiting':
    print('{"type":"device","id":"abc"}', flush=True)
    print('{"type":"waiting","message":"等手机上线…"}', flush=True)
    time.sleep(30)
if mode == 'reconnect-off':
    print('{"type":"notice","code":"reconnect_off","message":"手机端把自动重连关掉了"}', flush=True)
    print('{"type":"error","message":"手机端把「这台设备的自动重连」关掉了, 所以它一直在拒绝这台电脑。"}', flush=True)
    sys.exit(1)
if mode == 'reconnect-off-log':
    print('2026-01-01T00:00:00Z  INFO nectarlink_core::node: peer=abc reason=application closed: '
          'error_code: 0, reason: b"reconnect off" disconnected', file=sys.stderr, flush=True)
    print('Error: "等了 120 秒也没能连上手机"', file=sys.stderr, flush=True)
    sys.exit(1)
if mode == 'online':
    print('{"type":"online","id":"abc"}', flush=True)
    time.sleep(30)
if mode == 'ready':
    print('{"type":"ready","port":54321}', flush=True)
    time.sleep(30)
time.sleep(30)
'''


class FakeEngine(phone_mirror_engine.SidecarEngine):
    """用假的内核脚本代替真的 sidecar 可执行文件。"""

    def __init__(self, script, mode='ready', **kwargs):
        super().__init__(**kwargs)
        self._script = script
        self._mode_arg = mode

    def _command(self):
        return [sys.executable, self._script, self._mode_arg]


class TestSidecarErrorReporting(unittest.TestCase):
    """内核起不来时, ok-ww 得知道到底为什么。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.script = Path(self.tmp.name) / 'fake_sidecar.py'
        self.script.write_text(FAKE_SIDECAR, encoding='utf-8')
        self.addCleanup(self.tmp.cleanup)

    def _engine(self, mode, **kwargs):
        return FakeEngine(str(self.script), mode, data_dir=self.tmp.name, **kwargs)

    def test_the_error_line_becomes_the_reason(self):
        """内核在 stdout 上报错, ok-ww 要能读到并说给用户。"""
        engine = self._engine('error')
        self.assertTrue(engine.start())
        self.addCleanup(engine.stop)
        self.assertFalse(engine.wait_ready(timeout=10))
        self.assertIn('device is offline', engine.failure_reason)

    def test_the_error_output_becomes_the_reason(self):
        """只有 stderr 有话时(内核直接崩了), 也不能什么都不知道。"""
        engine = self._engine('stderr-only')
        self.assertTrue(engine.start())
        self.addCleanup(engine.stop)
        self.assertFalse(engine.wait_ready(timeout=10))
        self.assertIn('device is offline', engine.failure_reason)

    def test_the_waiting_message_is_shown(self):
        """等手机上线这件事要能显示出来, 免得看着像卡住了。"""
        engine = self._engine('waiting')
        self.assertTrue(engine.start())
        self.addCleanup(engine.stop)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not engine.status_message:
            time.sleep(0.05)
        self.assertIn('等手机上线', engine.status_message)

    def test_the_online_message_is_shown(self):
        engine = self._engine('online')
        self.assertTrue(engine.start())
        self.addCleanup(engine.stop)
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline and not engine.status_message:
            time.sleep(0.05)
        self.assertIn('已上线', engine.status_message)

    def test_the_reason_is_not_filled_with_noise(self):
        """内核的日常日志不算"起不来的原因", 得说人话。"""
        engine = self._engine('noise')
        self.assertTrue(engine.start())
        self.addCleanup(engine.stop)
        self.assertFalse(engine.wait_ready(timeout=10))
        reason = engine.failure_reason
        self.assertIn('device is offline', reason)
        self.assertNotIn('swarm_discovery', reason)
        self.assertNotIn('Added interface', reason)

    def test_the_port_is_taken_from_the_ready_line(self):
        engine = self._engine('ready')
        self.assertTrue(engine.start())
        self.addCleanup(engine.stop)
        self.assertTrue(engine.wait_ready(timeout=10))
        self.assertEqual(engine.port, 54321)


class TestPhoneRefusedTheConnection(unittest.TestCase):
    """手机端把「这台设备的自动重连」关掉时, 得说清楚该点哪里。

    这个开关存在手机本地数据库里(按设备存), 协议上没有一条消息能改对端的开关,
    所以 ok-ww 关不掉也打不开 —— 只能认出来, 然后让用户手点一下。认不出来的话,
    用户看到的是"手机没上线", 会跑去查网络、查防火墙, 方向全错。
    """

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.script = Path(self.tmp.name) / 'fake_sidecar.py'
        self.script.write_text(FAKE_SIDECAR, encoding='utf-8')
        self.addCleanup(self.tmp.cleanup)

    def _engine(self, mode, **kwargs):
        return FakeEngine(str(self.script), mode, data_dir=self.tmp.name, **kwargs)

    def test_the_notice_becomes_advice_the_user_can_follow(self):
        engine = self._engine('reconnect-off')
        self.assertTrue(engine.start())
        self.addCleanup(engine.stop)
        self.assertFalse(engine.wait_ready(timeout=10))
        self.assertTrue(engine.reconnect_off)
        # 提示得是"在手机上点重连", 不是内核那句原始英文错误。
        self.assertIn('重连', engine.failure_reason)
        self.assertIn('重连', engine.status_message)

    def test_the_refusal_hidden_in_a_routine_log_line_is_recognised(self):
        """拒绝的理由藏在内核的一条 INFO 日志里 —— 那句不能被当成噪声扔掉。

        内核是用 tracing::info! 打这行的(reason=b"reconnect off"), 而这里默认
        把 INFO 当日常日志过滤。识别必须发生在过滤之前, 否则最关键的一句正好没了。
        """
        engine = self._engine('reconnect-off-log')
        self.assertTrue(engine.start())
        self.addCleanup(engine.stop)
        self.assertFalse(engine.wait_ready(timeout=10))
        self.assertTrue(engine.reconnect_off)
        self.assertIn('重连', engine.failure_reason)

    def test_a_plain_network_error_is_not_mistaken_for_a_refusal(self):
        engine = self._engine('error')
        self.assertTrue(engine.start())
        self.addCleanup(engine.stop)
        self.assertFalse(engine.wait_ready(timeout=10))
        self.assertFalse(engine.reconnect_off)
        self.assertIn('device is offline', engine.failure_reason)

    def test_the_phrase_is_recognised_whatever_it_is_capitalised(self):
        recognise = phone_mirror_engine._looks_like_reconnect_off
        self.assertTrue(recognise('closed by application: reason: b"reconnect off"'))
        self.assertTrue(recognise('Reconnect Off'))
        self.assertFalse(recognise('device is offline'))
        self.assertFalse(recognise(''))
        self.assertFalse(recognise(None))


class TestStaleEngines(unittest.TestCase):
    """同一个数据目录只能有一个内核。"""

    def test_the_colour_codes_are_stripped(self):
        """内核日志里的颜色码要去掉: 不然" INFO "匹配不上, 日常日志会混进报错原因。"""
        line = ('\x1b[2m2026-01-01T00:00:00Z\x1b[0m \x1b[32m INFO\x1b[0m '
                '\x1b[2msome::target\x1b[0m: hello')
        plain = phone_mirror_engine._strip_ansi(line)
        self.assertNotIn('\x1b', plain)
        self.assertIn(' INFO ', plain)
        self.assertTrue(phone_mirror_engine._is_noise(plain))

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.data_dir = Path(self.tmp.name)

    def _spawn_dummy(self):
        """起一个会一直睡着的进程, 当作残留的内核。"""
        process = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(120)'],
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.addCleanup(self._kill, process)
        return process

    @staticmethod
    def _kill(process):
        try:
            process.kill()
            process.wait(timeout=5)
        except Exception:
            pass

    def test_the_state_file_names_the_engine_to_kill(self):
        """上次留下的内核: 状态文件里有它的进程号, 这次要先清掉。"""
        dummy = self._spawn_dummy()
        (self.data_dir / 'sidecar.json').write_text(
            json.dumps({'pid': dummy.pid, 'port': 0}), encoding='utf-8')
        engine = phone_mirror_engine.SidecarEngine(data_dir=self.data_dir)
        # 只测清理那一步, 不用真去起内核。
        engine.find_engine_pids = lambda: []
        engine.kill_stale_engines()
        deadline = time.monotonic() + 5
        while time.monotonic() < deadline and phone_mirror_engine.pid_alive(dummy.pid):
            time.sleep(0.1)
        self.assertFalse(phone_mirror_engine.pid_alive(dummy.pid), '残留内核没被清掉')

    def test_a_dead_pid_counts_as_gone(self):
        self.assertFalse(phone_mirror_engine.pid_alive(999999))
        self.assertFalse(phone_mirror_engine.pid_alive(0))
        self.assertFalse(phone_mirror_engine.pid_alive('abc'))

    def test_checking_a_pid_does_not_kill_it(self):
        """查进程不能把进程杀掉 —— Windows 上 os.kill(pid, 0) 是会 TerminateProcess 的。"""
        dummy = self._spawn_dummy()
        self.assertTrue(phone_mirror_engine.pid_alive(dummy.pid))
        time.sleep(0.3)
        self.assertTrue(phone_mirror_engine.pid_alive(dummy.pid), '查一次就把进程查死了')

    def test_the_current_process_is_never_killed(self):
        """自己不能被当成残留内核清掉。"""
        engine = phone_mirror_engine.SidecarEngine(data_dir=self.data_dir)
        (self.data_dir / 'sidecar.json').write_text(
            json.dumps({'pid': os.getpid(), 'port': 0}), encoding='utf-8')
        engine.find_engine_pids = lambda: []
        engine.kill_stale_engines()
        self.assertTrue(phone_mirror_engine.pid_alive(os.getpid()))

    def test_engines_are_found_by_their_data_dir(self):
        """老版本的内核不写状态文件, 只能按命令行里的数据目录找。"""
        engine = phone_mirror_engine.SidecarEngine(data_dir=self.data_dir)
        marker = str(self.data_dir).lower()
        fake_output = (
            f'111::"C:\\x\\nectarlink-sidecar.exe" --data-dir {marker} --name ok-ww\n'
            '222::"C:\\x\\nectarlink-sidecar.exe" --data-dir c:\\other\\nectarlink --name ok-ww\n'
            '333::not-a-process-line\n'
        )

        class Result:
            stdout = fake_output
            stderr = ''

        original = subprocess.run
        subprocess.run = lambda *args, **kwargs: Result()
        try:
            pids = engine.find_engine_pids()
        finally:
            subprocess.run = original
        self.assertEqual(pids, [111])


class TestModeSwitch(unittest.TestCase):
    """点「配对手机」要能换成一个配对模式的内核。"""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.script = Path(self.tmp.name) / 'fake_sidecar.py'
        self.script.write_text(FAKE_SIDECAR, encoding='utf-8')
        self.addCleanup(self.tmp.cleanup)

    def test_pairing_replaces_a_plain_engine(self):
        engine = FakeEngine(str(self.script), 'quiet', data_dir=self.tmp.name)
        engine.find_engine_pids = lambda: []
        self.assertTrue(engine.start())
        self.addCleanup(engine.stop)
        first = engine.process.pid
        self.assertEqual(engine._mode, 'plain')
        # 要配对: 跑着的却是普通内核, 得换一个。
        engine.pair = True
        self.assertTrue(engine.start())
        self.assertEqual(engine._mode, 'pair')
        self.assertNotEqual(engine.process.pid, first, '还是原来那个内核')

    def test_a_plain_start_keeps_the_running_engine(self):
        """已经有一个内核在跑, 就接着用, 别反复重启(每次重启都要手机上点允许)。"""
        engine = FakeEngine(str(self.script), 'quiet', data_dir=self.tmp.name)
        engine.find_engine_pids = lambda: []
        self.assertTrue(engine.start())
        self.addCleanup(engine.stop)
        first = engine.process.pid
        self.assertTrue(engine.start())
        self.assertEqual(engine.process.pid, first)


class TestRealSidecar(unittest.TestCase):
    """真的 sidecar 也要按约定说话(没部署就跳过)。"""

    def setUp(self):
        try:
            self.exe = phone_mirror_engine.find_sidecar()
        except FileNotFoundError:
            self.skipTest('没部署 sidecar, 跳过')

    def test_it_answers_with_a_pairing_link(self):
        with tempfile.TemporaryDirectory() as tmp:
            process = subprocess.Popen([str(self.exe), '--data-dir', tmp, '--pair'],
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                messages = []
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    line = process.stdout.readline()
                    if not line:
                        break
                    messages.extend(phone_mirror_engine._parse_status_lines(line.strip()))
                    if any(message.get('type') == 'pairing' for message in messages):
                        break
                pairing = [m for m in messages if m.get('type') == 'pairing']
                self.assertTrue(pairing, f'没给出配对链接: {messages}')
                self.assertTrue(str(pairing[0].get('uri', '')).startswith('nectarlink://pair'))
            finally:
                process.kill()
                process.wait(timeout=10)
                process.stdout.close()

    def test_it_leaves_a_state_file_behind(self):
        """内核在跑的时候要留下"我在跑"的记录, 下次才知道该清谁。"""
        with tempfile.TemporaryDirectory() as tmp:
            process = subprocess.Popen([str(self.exe), '--data-dir', tmp, '--pair'],
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                state_file = Path(tmp) / 'sidecar.json'
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline and not state_file.exists():
                    time.sleep(0.1)
                self.assertTrue(state_file.exists(), '内核没写状态文件')
                state = json.loads(state_file.read_text(encoding='utf-8'))
                self.assertEqual(state.get('pid'), process.pid)
            finally:
                process.kill()
                process.wait(timeout=10)
                process.stdout.close()

    def test_it_says_which_phone_is_missing(self):
        """一台手机都没配对时, 报错要说清楚是缺手机, 而不是别的。"""
        with tempfile.TemporaryDirectory() as tmp:
            process = subprocess.Popen([str(self.exe), '--data-dir', tmp],
                                       stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
            try:
                messages = []
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    line = process.stdout.readline()
                    if not line:
                        break
                    messages.extend(phone_mirror_engine._parse_status_lines(line.strip()))
                    if any(message.get('type') == 'error' for message in messages):
                        break
                errors = [m for m in messages if m.get('type') == 'error']
                self.assertTrue(errors, f'没报错: {messages}')
                self.assertIn('paired phone', str(errors[0].get('message', '')))
            finally:
                process.kill()
                process.wait(timeout=10)
                process.stdout.close()

    def test_it_waits_for_the_phone_instead_of_quitting(self):
        """核心修复: 手机还没连上时, 内核不能一上来就 "device is offline" 退出。

        用真的数据目录(里面有配对好的手机)来测: 手机上线之前, 内核应该
        一直等着并报"等手机上线", **不能**报错退出。

        注意观察窗口要比内核自己的等待上限短: 等满之后内核报「手机没上线」
        是**正确**的行为(那是超时, 不是崩溃), 不能算失败。
        """
        data_dir = phone_mirror_engine.default_data_dir()
        db = data_dir / 'nectarlink.db'
        if not db.exists():
            self.skipTest('本机没有配对过的手机, 跳过')
        process = subprocess.Popen([str(self.exe), '--data-dir', str(data_dir),
                                    '--wait-seconds', '120'],
                                   stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        try:
            messages = []
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                line = process.stdout.readline()
                if not line:
                    break
                messages.extend(phone_mirror_engine._parse_status_lines(line.strip()))
                kinds = [message.get('type') for message in messages]
                if 'error' in kinds or 'online' in kinds:
                    break
            kinds = [message.get('type') for message in messages]
            self.assertNotIn('error', kinds, f'内核又直接报错了: {messages}')
            self.assertIsNone(process.poll(), '内核不该这么快就退出')
            # 手机没上线 → 报"等手机上线"; 手机已上线 → 报"online"。两者都行,
            # 关键是**不能**是错误退出。
            self.assertTrue('waiting' in kinds or 'online' in kinds,
                            f'既没说等手机、也没说已上线: {messages}')
        finally:
            process.kill()
            process.wait(timeout=10)
            process.stdout.close()


if __name__ == '__main__':
    unittest.main()
