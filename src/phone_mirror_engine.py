"""内置投屏引擎(NectarLink sidecar)的管理。

ok-ww 不再依赖外部安装的 NectarLink 桌面端, 而是自己拉起一个无界面的投屏
内核(sidecar):

  * sidecar 用自己的设备身份跟手机配对(配对码由 ok-ww 显示, 手机扫码);
  * 手机同意后, sidecar 把 H.264 画面解码成像素, 通过本机回环 socket 推给
    ok-ww; ok-ww 的点击/按键再通过同一个 socket 回传给手机;
  * 画面比例、分辨率、码率都由 ok-ww 自己决定, 不再受桌面端窗口尺寸影响。

sidecar 进程可以跨多次运行保持存活(每次重新投屏都要在手机上点「允许」,
所以尽量别反复重启它)。引擎把端口写在 ``<数据目录>/link.json`` 里, 下次
ok-ww 启动时先试着连上还在跑的引擎。

同一个数据目录**只能有一个**内核: 设备身份存在那个目录里, 两个内核用同一个
身份在局域网里互相广播时, 手机会拿到对不上的地址, 然后报「设备离线」。
所以这里每次启动前都会先把上次留下的内核清掉。
"""

import json
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from collections import deque
from pathlib import Path

from ok import Logger

logger = Logger.get_logger(__name__)

# sidecar 可执行文件的名字。
SIDECAR_EXE = 'nectarlink-sidecar.exe'

# 内核的报错都在 stderr 里, 这里留最后几行, 出错时好说清楚原因。
STDERR_TAIL_LINES = 8


def _app_root() -> Path:
    """ok-ww 的安装目录。"""
    try:
        from ok import get_path_relative_to_exe
        return Path(get_path_relative_to_exe('.'))
    except Exception:
        return Path(__file__).resolve().parent.parent


def default_data_dir() -> Path:
    """sidecar 存放设备身份与配对列表的目录。"""
    base = os.environ.get('LOCALAPPDATA') or os.path.expanduser('~')
    return Path(base) / 'ok-ww' / 'nectarlink'


def find_sidecar() -> Path:
    """找到 sidecar 可执行文件; 找不到时抛 FileNotFoundError。"""
    candidates = [
        _app_root() / 'bin' / SIDECAR_EXE,
        Path(__file__).resolve().parent.parent / 'bin' / SIDECAR_EXE,
        Path(__file__).resolve().parent / SIDECAR_EXE,
    ]
    found = shutil.which('nectarlink-sidecar')
    if found:
        candidates.append(Path(found))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f'找不到投屏内核 {SIDECAR_EXE}; 试过: ' + ', '.join(str(c) for c in candidates))


def pid_alive(pid) -> bool:
    """某个 pid 是不是还活着。

    Windows 上**不能**用 os.kill(pid, 0) 来试探: 那边的 os.kill 会直接
    TerminateProcess, 也就是"试探"本身会把进程杀掉。这里走 Windows API。
    """
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if sys.platform.startswith('win'):
        try:
            import ctypes
            PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
            STILL_ACTIVE = 259
            kernel32 = ctypes.windll.kernel32
            handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid)
            if not handle:
                return False
            try:
                code = ctypes.c_ulong()
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(code)):
                    return False
                return code.value == STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        except Exception as e:
            logger.debug(f'手机投屏: 查进程 {pid} 失败({e})')
            return False
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False
    except Exception:
        return False


def kill_pid(pid) -> bool:
    """结束一个进程; 成功与否都返回是不是还活着。"""
    try:
        pid = int(pid)
    except (TypeError, ValueError):
        return False
    if pid <= 0:
        return False
    if sys.platform.startswith('win'):
        try:
            subprocess.run(['taskkill', '/PID', str(pid), '/F'],
                           capture_output=True, timeout=15,
                           creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except Exception as e:
            logger.debug(f'手机投屏: 结束进程 {pid} 失败({e})')
    else:
        try:
            os.kill(pid, 15)
        except Exception:
            pass
    # 给它一点时间真的走掉
    for _ in range(20):
        if not pid_alive(pid):
            return True
        time.sleep(0.1)
    return not pid_alive(pid)


def _parse_status_lines(line):
    """从一行输出里取出状态消息(每条一个 JSON 对象)。

    内核的状态走 stdout, 正常情况下每行就是一个 JSON。但内核也可能往 stdout
    写别的东西(比如提示语), 那样会把后面的 JSON 粘在同一行, 整行就不合法了。
    所以这里不只试整行: 找不到就从第一个 '{' 开始, 按大括号配平把 JSON 对象
    逐个抠出来, 免得一条消息被别的东西带走了就永远收不到。
    """
    try:
        message = json.loads(line)
        return [message] if isinstance(message, dict) else []
    except Exception:
        pass
    messages = []
    index = 0
    while True:
        start = line.find('{', index)
        if start < 0:
            break
        depth = 0
        end = -1
        in_string = False
        escaped = False
        for position in range(start, len(line)):
            char = line[position]
            if in_string:
                if escaped:
                    escaped = False
                elif char == '\\':
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == '{':
                depth += 1
            elif char == '}':
                depth -= 1
                if depth == 0:
                    end = position + 1
                    break
        if end < 0:
            break
        try:
            message = json.loads(line[start:end])
        except Exception:
            message = None
        if isinstance(message, dict):
            messages.append(message)
        index = end
    if not messages:
        logger.debug(f'手机投屏: 引擎输出里没有 JSON: {line[:200]}')
    return messages


# 内核日志里的颜色转义码(关掉也可以, 内核那边已经关了, 这里再兜一层)。
_ANSI_PATTERN = re.compile(r'\x1b\[[0-9;]*[A-Za-z]')

# tracing 的日志级别: INFO/DEBUG/TRACE 是日常信息, 不用当成"出错的理由"。
_NOISE_LEVELS = (' INFO ', ' DEBUG ', ' TRACE ')


def _strip_ansi(text: str) -> str:
    """去掉日志里的颜色转义码。"""
    return _ANSI_PATTERN.sub('', text)


def _is_noise(line: str) -> bool:
    """这条内核日志是不是可以忽略的日常信息。"""
    for level in _NOISE_LEVELS:
        if level in line:
            return True
    return False


class SidecarEngine:
    """投屏内核的进程包装: 拉起它、读它的状态、把画面端口交出去。

    Args:
        data_dir: 设备身份与配对列表的目录。
        device: 要投屏的手机(id 前缀或名字); 空表示只有一台时自动选。
        max_size: 请求手机画面最长边(像素)。
        fps: 请求的帧率。
        bitrate: 请求的码率(bps)。
        name: 这个设备在手机端显示的名字。
        pair: 启动时先配对。
    """

    def __init__(self, data_dir=None, device='', max_size=1920, fps=30, bitrate=8_000_000,
                 name='ok-ww', pair=False):
        self.data_dir = Path(data_dir) if data_dir else default_data_dir()
        self.device = device or ''
        self.max_size = int(max_size)
        self.fps = int(fps)
        self.bitrate = int(bitrate)
        self.name = name
        self.pair = pair
        self.process = None
        self.port = None
        self.status = {}
        self.status_message = ''
        self.last_error = None
        self.pairing_uri = None
        self.sas_code = None
        self.paired = False
        self._thread = None
        self._error_thread = None
        self._ready = threading.Event()
        self._lock = threading.Lock()
        # 当前跑着的内核是哪种模式: 'plain' 或者 'pair'。
        self._mode = None
        # 内核 stderr 的最后几行, 用来解释"为什么起不来"。
        self._stderr = deque(maxlen=STDERR_TAIL_LINES * 4)

    def configure(self, device=None, max_size=None, fps=None, bitrate=None, name=None, pair=None):
        """改设置(只在下一次启动内核时生效)。"""
        if device is not None:
            self.device = device
        if max_size is not None:
            self.max_size = int(max_size)
        if fps is not None:
            self.fps = int(fps)
        if bitrate is not None:
            self.bitrate = int(bitrate)
        if name is not None:
            self.name = name
        if pair is not None:
            self.pair = bool(pair)

    # ------------------------------------------------------------------
    # 状态
    # ------------------------------------------------------------------

    @property
    def running(self) -> bool:
        return self.process is not None and self.process.poll() is None

    @property
    def link_file(self) -> Path:
        return self.data_dir / 'link.json'

    @property
    def state_file(self) -> Path:
        """内核写的"我在跑"记录(进程号 + 画面端口)。"""
        return self.data_dir / 'sidecar.json'

    def read_link(self):
        """读上次写下的端口信息(引擎可能还在跑)。"""
        try:
            data = json.loads(self.link_file.read_text(encoding='utf-8'))
            return int(data.get('port', 0)) or None
        except Exception:
            return None

    def read_state(self):
        """读内核写的状态文件。"""
        try:
            data = json.loads(self.state_file.read_text(encoding='utf-8'))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def is_port_alive(self, port) -> bool:
        """端口上是否真的有引擎在听。"""
        if not port:
            return False
        import socket
        try:
            with socket.create_connection(('127.0.0.1', int(port)), timeout=1.0):
                return True
        except Exception:
            return False

    @property
    def stderr_tail(self) -> str:
        """内核 stderr 的最后几行(给用户看的原因)。"""
        with self._lock:
            lines = list(self._stderr)[-STDERR_TAIL_LINES:]
        return '\n'.join(lines)

    @property
    def failure_reason(self) -> str:
        """内核起不来的原因; 没有就说没有。"""
        if self.last_error:
            return self.last_error
        return self.stderr_tail

    # ------------------------------------------------------------------
    # 残留内核
    # ------------------------------------------------------------------

    def _own_pids(self):
        """绝对不能动的进程号: 自己, 和自己起的那个内核。"""
        pids = {os.getpid()}
        if self.process is not None and self.process.poll() is None:
            pids.add(self.process.pid)
        return pids

    def find_engine_pids(self):
        """找出用同一个数据目录的内核进程。

        老版本的内核不写状态文件, 只能按命令行找。找不到就算了, 不影响正常流程。
        """
        if not sys.platform.startswith('win'):
            return []
        script = (
            "Get-CimInstance Win32_Process -Filter \"Name='{exe}'\" | "
            "ForEach-Object {{ Write-Output ($_.ProcessId.ToString() + '::' + $_.CommandLine) }}"
        ).format(exe=SIDECAR_EXE)
        try:
            result = subprocess.run(
                ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script],
                capture_output=True, text=True, timeout=20,
                creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except Exception as e:
            logger.debug(f'手机投屏: 找残留内核失败({e})')
            return []
        marker = str(self.data_dir).lower()
        pids = []
        for line in (result.stdout or '').splitlines():
            if '::' not in line:
                continue
            pid_text, _, command = line.partition('::')
            if marker not in command.lower():
                continue
            try:
                pids.append(int(pid_text.strip()))
            except ValueError:
                continue
        return pids

    def kill_stale_engines(self):
        """把上次留下的内核清掉。

        同一个数据目录只能有一个内核: 设备身份存在那里, 两个内核用同一个身份
        在局域网里互相广播时, 手机会拿到对不上的地址, 然后报「设备离线」。
        """
        own = self._own_pids()
        pids = []
        state = self.read_state()
        pid = state.get('pid')
        if isinstance(pid, int) and pid > 0:
            pids.append(pid)
        pids.extend(self.find_engine_pids())
        for pid in dict.fromkeys(pids):
            if pid in own:
                continue
            if not pid_alive(pid):
                continue
            logger.info(f'手机投屏: 清掉上次留下的投屏内核(pid {pid})')
            if kill_pid(pid):
                logger.info(f'手机投屏: 已结束残留内核(pid {pid})')
            else:
                logger.warning(f'手机投屏: 残留内核(pid {pid})没结束掉, '
                               f'可能会干扰这次的投屏')

    # ------------------------------------------------------------------
    # 启停
    # ------------------------------------------------------------------

    def _command(self):
        exe = find_sidecar()
        command = [str(exe),
                   '--data-dir', str(self.data_dir),
                   '--max-size', str(self.max_size),
                   '--fps', str(self.fps),
                   '--bitrate', str(self.bitrate),
                   '--name', self.name]
        if self.device:
            command += ['--device', self.device]
        if self.pair:
            command.append('--pair')
        return command

    def start(self) -> bool:
        """拉起引擎(不等待就绪); 已经在跑就直接复用。"""
        with self._lock:
            if self.running:
                if self.pair and self._mode != 'pair':
                    # 要配对, 但跑着的是普通内核: 换成一个配对内核。
                    logger.info('手机投屏: 换成配对模式的内核')
                    self._stop_locked()
                else:
                    return True
            existing = self.read_link()
            if existing and self.is_port_alive(existing):
                # 上次那个引擎还活着: 直接连上, 免得每次都要在手机上点「允许」。
                self.port = existing
                logger.info(f'手机投屏: 复用已在运行的投屏内核(端口 {existing})')
                self._ready.set()
                return True
            try:
                command = self._command()
            except FileNotFoundError as e:
                self.last_error = str(e)
                logger.error(f'手机投屏: {e}')
                return False
            # 上次留下的内核先清掉: 两个内核用同一个设备身份会互相干扰。
            self.kill_stale_engines()
            self.data_dir.mkdir(parents=True, exist_ok=True)
            flags = 0
            if sys_platform_is_windows():
                flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            try:
                self.process = subprocess.Popen(command,
                                                 stdin=subprocess.PIPE,
                                                 stdout=subprocess.PIPE,
                                                 stderr=subprocess.PIPE,
                                                 creationflags=flags)
            except Exception as e:
                self.last_error = str(e)
                logger.error(f'手机投屏: 投屏内核启动失败({e})')
                return False
            self._mode = 'pair' if self.pair else 'plain'
            self._stderr.clear()
            self.last_error = None
            self._thread = threading.Thread(target=self._read_output, name='phone-mirror-sidecar', daemon=True)
            self._thread.start()
            self._error_thread = threading.Thread(target=self._read_stderr, name='phone-mirror-sidecar-err', daemon=True)
            self._error_thread.start()
            logger.info(f'手机投屏: 投屏内核已启动({" ".join(command)})')
            return True

    def wait_ready(self, timeout=60.0) -> bool:
        """等到引擎把端口交出来。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._ready.is_set() and self.port:
                return True
            if not self.running and self.process is not None:
                # 内核退了: 等一下读输出的线程, 把最后那条错误捞上来。
                time.sleep(0.3)
                return False
            time.sleep(0.1)
        return False

    def stop(self):
        """停掉引擎。"""
        with self._lock:
            self._stop_locked()

    def _stop_locked(self):
        """停掉引擎(调用方要拿着锁)。"""
        process = self.process
        self.process = None
        self.port = None
        self._ready.clear()
        self._mode = None
        if process is None:
            return
        try:
            process.terminate()
            process.wait(timeout=3)
        except Exception:
            try:
                process.kill()
            except Exception:
                pass
        # 把管道关掉, 别一直占着句柄。
        for stream in (process.stdout, process.stderr, process.stdin):
            try:
                if stream is not None:
                    stream.close()
            except Exception:
                pass
        logger.info('手机投屏: 投屏内核已停止')

    # ------------------------------------------------------------------
    # 输出
    # ------------------------------------------------------------------

    def _read_output(self):
        """读引擎的状态行(每行一个 JSON)。"""
        process = self.process
        if process is None or process.stdout is None:
            return
        try:
            for raw in process.stdout:
                line = raw.decode('utf-8', 'ignore').strip()
                if not line:
                    continue
                for message in _parse_status_lines(line):
                    self._on_message(message)
        except Exception as e:
            logger.debug(f'手机投屏: 读引擎输出结束({e})')

    def _read_stderr(self):
        """把内核的报错收进日志。

        内核的失败原因都在 stderr 里(比如「设备离线」「手机没同意投屏」),
        以前直接扔掉了, 结果界面上只剩一句没头没尾的「内核还没就绪」。
        """
        process = self.process
        if process is None or process.stderr is None:
            return
        try:
            for raw in process.stderr:
                line = _strip_ansi(raw.decode('utf-8', 'ignore').strip()).strip()
                if not line:
                    continue
                logger.debug(f'手机投屏内核: {line}')
                # 内核的日志里一大半是 tracing 的 INFO, 那些进日志就够了;
                # 这里只留可能有用的(WARNING/ERROR, 以及内核自己抛的错误),
                # 免得"起不来的原因"里全是局域网广播的碎话。
                if _is_noise(line):
                    continue
                with self._lock:
                    self._stderr.append(line)
        except Exception as e:
            logger.debug(f'手机投屏: 读内核错误输出结束({e})')

    def _on_message(self, message):
        kind = message.get('type')
        self.status = message
        if kind == 'ready':
            self.port = int(message.get('port', 0)) or None
            self._ready.set()
            logger.info(f'手机投屏: 内核就绪, 画面端口 {self.port}')
        elif kind == 'pairing':
            self.pairing_uri = message.get('uri')
            logger.info('手机投屏: 等待手机扫码配对')
        elif kind == 'sas':
            self.sas_code = message.get('code')
            logger.info(f'手机投屏: 请核对手机上的配对码 {self.sas_code}')
        elif kind == 'paired':
            self.paired = True
            logger.info('手机投屏: 配对成功')
        elif kind == 'waiting':
            self.status_message = message.get('message') or '等手机上线…'
            logger.info(f'手机投屏: {self.status_message}')
        elif kind == 'online':
            self.status_message = '手机已上线, 请在手机上点「允许」'
            logger.info(f'手机投屏: {self.status_message}')
        elif kind == 'retry':
            self.status_message = f'重试请求投屏({message.get("message")})'
            logger.warning(f'手机投屏: {self.status_message}')
        elif kind == 'notice':
            logger.info(f'手机投屏: 内核提示 {message.get("code")}')
        elif kind == 'error':
            self.last_error = message.get('message')
            self.status_message = f'出错了: {self.last_error}'
            logger.error(f'手机投屏: 内核报错: {self.last_error}')

    def confirm_pairing(self, matched: bool = True) -> bool:
        """回答内核的配对码核对(手机上显示的码和这里一致吗)。"""
        if self.process is None or self.process.stdin is None:
            return False
        if not self.running:
            self.last_error = '投屏内核已经退出了'
            return False
        try:
            self.process.stdin.write(('y\n' if matched else 'n\n').encode('utf-8'))
            self.process.stdin.flush()
            return True
        except Exception as e:
            # 内核可能已经在等手机上点「允许」了, 不会再读标准输入。
            logger.debug(f'手机投屏: 回答配对码失败({e})')
            return False


def sys_platform_is_windows() -> bool:
    return sys.platform.startswith('win')


# 全局只保留一个内核: 每次重新投屏都要在手机上点「允许」, 所以尽量让引擎
# 一直活着, 配置界面、启动流程、任务运行都用同一个。
_engine = None
_engine_lock = threading.Lock()


def get_engine(**kwargs) -> SidecarEngine:
    """全局的投屏内核(第一次调用时创建)。"""
    global _engine
    with _engine_lock:
        if _engine is None:
            _engine = SidecarEngine(**kwargs)
        return _engine


def stop_engine():
    """停掉全局的投屏内核。"""
    global _engine
    with _engine_lock:
        if _engine is not None:
            _engine.stop()
            _engine = None
