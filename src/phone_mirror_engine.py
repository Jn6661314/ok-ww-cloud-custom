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
"""

import json
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path

from ok import Logger

logger = Logger.get_logger(__name__)

# sidecar 可执行文件的名字。
SIDECAR_EXE = 'nectarlink-sidecar.exe'


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
        self.last_error = None
        self.pairing_uri = None
        self.sas_code = None
        self.paired = False
        self._thread = None
        self._ready = threading.Event()
        self._lock = threading.Lock()

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

    def read_link(self):
        """读上次写下的端口信息(引擎可能还在跑)。"""
        try:
            data = json.loads(self.link_file.read_text(encoding='utf-8'))
            return int(data.get('port', 0)) or None
        except Exception:
            return None

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
            self.data_dir.mkdir(parents=True, exist_ok=True)
            flags = 0
            if sys_platform_is_windows():
                flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
            try:
                self.process = subprocess.Popen(command,
                                                 stdin=subprocess.PIPE,
                                                 stdout=subprocess.PIPE,
                                                 stderr=subprocess.DEVNULL,
                                                 creationflags=flags)
            except Exception as e:
                self.last_error = str(e)
                logger.error(f'手机投屏: 投屏内核启动失败({e})')
                return False
            self._thread = threading.Thread(target=self._read_output, name='phone-mirror-sidecar', daemon=True)
            self._thread.start()
            logger.info(f'手机投屏: 投屏内核已启动({" ".join(command)})')
            return True

    def wait_ready(self, timeout=60.0) -> bool:
        """等到引擎把端口交出来。"""
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self._ready.is_set() and self.port:
                return True
            if not self.running and self.process is not None:
                return False
            time.sleep(0.1)
        return False

    def stop(self):
        """停掉引擎。"""
        with self._lock:
            process = self.process
            self.process = None
            self.port = None
            self._ready.clear()
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
        elif kind == 'error':
            self.last_error = message.get('message')
            logger.warning(f'手机投屏: 内核报错: {self.last_error}')

    def confirm_pairing(self, matched: bool = True) -> bool:
        """回答内核的配对码核对(手机上显示的码和这里一致吗)。"""
        if self.process is None or self.process.stdin is None:
            return False
        try:
            self.process.stdin.write(('y\n' if matched else 'n\n').encode('utf-8'))
            self.process.stdin.flush()
            return True
        except Exception as e:
            logger.warning(f'手机投屏: 回答配对码失败({e})')
            return False


def sys_platform_is_windows() -> bool:
    import sys
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
