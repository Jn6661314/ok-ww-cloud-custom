"""手机投屏(内置引擎)抓屏: 从本机回环 socket 收画面, 并把触控回传给手机。

内置投屏内核(sidecar)把手机的 H.264 画面解码成像素, 通过 127.0.0.1 上的
一个 socket 推给 ok-ww; ok-ww 的点击和按键再通过同一个 socket 回传给手机。

这里做三件事:
  * 收帧: 后台线程读 socket, 只保留最新的一帧(慢了就丢旧的, 不排队);
  * 裁剪与归一化: 手机画面(横屏 20:9 等)两侧可能有黑边, 裁掉之后等比缩到
    模板原生高度 1080, 帧尺寸恒定, 模板按 1:1 使用, 匹配最准;
  * 坐标换算: 帧坐标 -> 手机屏幕比例(0..1), sidecar 再转成手机上的触点。

协议(和 sidecar 的 src/link.rs 对应): 每条消息是 1 字节类型 + 4 字节长度
(小端) + 负载。

  类型 1 状态: JSON 文本
  类型 2 画面: u32 宽 + u32 高 + u32 字节数 + NV12 像素
  类型 3 触控: u8 动作(0按下/1移动/2抬起) + f32 x + f32 y
  类型 4 按键: u8 键码
"""

import json
import socket
import struct
import threading
import time

import cv2
import numpy as np

from ok.device.capture_methods.base import BaseCaptureMethod
from ok.util.logger import Logger

from src.phone_mirror import NORMALIZED_HEIGHT, detect_picture_rect, normalize_picture_size

logger = Logger.get_logger(__name__)

KIND_STATUS = 1
KIND_FRAME = 2
KIND_TOUCH = 3
KIND_KEY = 4

TOUCH_DOWN = 0
TOUCH_MOVE = 1
TOUCH_UP = 2

KEY_BACK = 0
KEY_HOME = 1
KEY_RECENTS = 2
KEY_ENTER = 3
KEY_BACKSPACE = 4

# start() 等首次连上 sidecar 的时间。连的是本机回环, 正常几十毫秒就建好。
FIRST_CONNECT_TIMEOUT = 3.0

# socket 断掉之后, 这段时间内仍然算"已连接"。
#
# 内核重启(换配对模式)或者手机短暂掉线时 socket 会断一下, 后台线程每秒重连。
# 框架在启动流程里会问 connected(), 落在这一秒里就会把设备判成"未连接",
# 然后跑去启动游戏 exe —— 内置引擎没有 exe, 用户看到的是"游戏路径不存在"。
RECONNECT_GRACE = 8.0

# 键名 -> sidecar 的键码。ok-ww 的按键名来自 ADB 键位表, 这里只挑手机能懂的。
KEY_CODES = {
    'back': KEY_BACK,
    'esc': KEY_BACK,
    'escape': KEY_BACK,
    'backspace': KEY_BACKSPACE,
    'enter': KEY_ENTER,
    'return': KEY_ENTER,
    'home': KEY_HOME,
    'recents': KEY_RECENTS,
    'menu': KEY_RECENTS,
}


class PhoneMirrorSocketCaptureMethod(BaseCaptureMethod):
    """从 sidecar 收手机画面的抓屏方法。

    Args:
        port: sidecar 的本机端口。
        exit_event: 框架的退出事件, 收到信号后停止收帧。
        target_height: 画面归一化后的高度(默认模板原生高度 1080)。
    """

    name = 'PhoneMirrorSocket'

    def __init__(self, port, exit_event=None, target_height=NORMALIZED_HEIGHT):
        super().__init__()
        self.port = int(port)
        self.target_height = target_height
        self.exit_event = exit_event
        self._own_exit_event = threading.Event()
        self._socket = None
        self._send_lock = threading.Lock()
        self._frame_lock = threading.Lock()
        self._frame_ready = threading.Event()
        # 最新一帧: (宽, 高, NV12 字节)
        self._raw = None
        self._raw_size = (0, 0)
        # 画面区在手机整幅画面里的矩形 (x, y, w, h)
        self.picture_rect = None
        self.rect_key = None
        # 归一化缩放系数(目标高 / 原高)
        self.scale = 1.0
        self.status = {}
        self.last_error = None
        self._thread = None
        self._running = False
        # 最近一次连上 sidecar 的时刻(monotonic)。断开重连的间隙里靠它维持
        # "已连接"的判断, 免得框架把设备当成未连接。
        self._last_connected = 0.0

    # ------------------------------------------------------------------
    # 连接与收帧
    # ------------------------------------------------------------------

    def start(self):
        """开始收帧(后台线程), 并等首次连上。

        Returns:
            是否已经连上 sidecar。

        必须**等连上再返回**: 框架紧接着会问 connected(), 拿它判断"这个设备能不能
        启动"。如果这里只是把线程拉起来就返回, 那个瞬间还没连上, connected() 就是
        False —— 框架会把内置引擎(它没有窗口、没有 exe)当成"未连接的 windows
        设备", 跑去启动游戏 exe, 最后报"游戏路径不存在, 请手动打开游戏"。
        """
        if self._running:
            return self.connected()
        self._running = True
        self._thread = threading.Thread(target=self._receive_loop, name='phone-mirror-recv', daemon=True)
        self._thread.start()
        deadline = time.monotonic() + FIRST_CONNECT_TIMEOUT
        while time.monotonic() < deadline:
            if self._socket is not None:
                return True
            if not self._running:
                break
            time.sleep(0.02)
        return self._socket is not None

    def connected(self):
        if not self._running:
            return False
        if self._socket is not None:
            return True
        # 刚断的: 后台线程正在重连, 别让调用方以为设备没了。
        return (self._last_connected > 0
                and time.monotonic() - self._last_connected < RECONNECT_GRACE)

    def clickable(self):
        return self.connected()

    def get_name(self):
        return f'PhoneMirrorSocket_{self.port}'

    def close(self):
        self._running = False
        self._own_exit_event.set()
        sock = self._socket
        self._socket = None
        if sock is not None:
            try:
                sock.close()
            except Exception:
                pass
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            self._thread = None

    def _stopped(self):
        event = self.exit_event if self.exit_event is not None else self._own_exit_event
        try:
            return event.is_set()
        except Exception:
            return False

    def _receive_loop(self):
        """连上 sidecar, 一直收帧; 断了就重连。"""
        while not self._stopped():
            try:
                self._connect_once()
            except Exception as e:
                logger.debug(f'手机投屏: 连接 sidecar 失败({e}), 稍后重试')
                self.last_error = str(e)
            if self._stopped():
                break
            time.sleep(1.0)

    def _connect_once(self):
        sock = socket.create_connection(('127.0.0.1', self.port), timeout=5)
        sock.settimeout(5.0)
        self._socket = sock
        self._last_connected = time.monotonic()
        logger.info(f'手机投屏: 已连接 sidecar 127.0.0.1:{self.port}')
        try:
            while not self._stopped():
                try:
                    kind, payload = self._read_message(sock)
                except socket.timeout:
                    continue
                except OSError:
                    break
                if kind == KIND_FRAME:
                    self._on_frame(payload)
                elif kind == KIND_STATUS:
                    self._on_status(payload)
        finally:
            self._socket = None
            try:
                sock.close()
            except Exception:
                pass

    @staticmethod
    def _read_message(sock):
        head = b''
        while len(head) < 5:
            chunk = sock.recv(5 - len(head))
            if not chunk:
                raise OSError('连接已关闭')
            head += chunk
        length = struct.unpack('<I', head[1:5])[0]
        payload = b''
        while len(payload) < length:
            chunk = sock.recv(min(1 << 20, length - len(payload)))
            if not chunk:
                raise OSError('连接已关闭')
            payload += chunk
        return head[0], payload

    def _on_status(self, payload):
        """处理内核发来的状态行。

        内核在同一条 socket 上发状态(sidecar 的 src/link.rs): 画面格式变了、
        解码出错、手机停止投屏等。这些消息以前没人收, 现在真正用起来——
        特别是 "ended": 手机停了投屏以后必须把缓存的帧丢掉, 否则框架会一直
        对着一张旧截图点, 看起来像"点了没反应"。
        """
        try:
            message = json.loads(payload.decode('utf-8'))
        except Exception:
            return
        if not isinstance(message, dict):
            return
        self.status = message
        kind = message.get('type')
        if kind == 'ended':
            self._drop_frame()
            self.last_error = '手机端停止了投屏'
            logger.warning('手机投屏: 手机端停止了投屏, 已丢弃缓存画面')
        elif kind == 'error':
            text = message.get('message') or '未知错误'
            self.last_error = str(text)
            logger.warning(f'手机投屏: 内核报错: {text}')
        elif kind == 'config':
            logger.info(
                '手机投屏: 画面格式 '
                f"{message.get('codec')} {message.get('width')}x{message.get('height')}"
            )
        elif kind == 'size':
            logger.info(f"手机投屏: 解码分辨率 {message.get('width')}x{message.get('height')}")

    def _drop_frame(self):
        """丢掉缓存的那一帧(投屏断了以后不能再拿旧画面当实时画面用)。"""
        with self._frame_lock:
            self._raw = None
            self._raw_size = (0, 0)
        self._frame_ready.clear()

    def _on_frame(self, payload):
        if len(payload) < 12:
            return
        width, height, size = struct.unpack('<III', payload[:12])
        pixels = payload[12:]
        if len(pixels) < size:
            pixels = pixels + b'\x00' * (size - len(pixels))
        with self._frame_lock:
            self._raw = pixels
            self._raw_size = (width, height)
        self._frame_ready.set()

    # ------------------------------------------------------------------
    # 取帧
    # ------------------------------------------------------------------

    def do_get_frame(self):
        with self._frame_lock:
            raw = self._raw
            size = self._raw_size
        if raw is None or size[0] <= 0 or size[1] <= 0:
            return None
        frame = self._to_bgr(raw, size)
        if frame is None:
            return None
        return self.adapt_frame(frame)

    def do_get_frame_wait(self, timeout):
        deadline = time.monotonic() + max(0.0, timeout)
        while True:
            frame = self.do_get_frame()
            if frame is not None:
                return frame
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            self._frame_ready.wait(min(0.05, remaining))
            self._frame_ready.clear()

    @staticmethod
    def _to_bgr(raw, size):
        """NV12 -> BGR。sidecar 给的是紧凑排列(行宽 == 宽)。"""
        width, height = size
        if width <= 0 or height <= 0:
            return None
        expected = width * height * 3 // 2
        if len(raw) < expected:
            return None
        nv12 = np.frombuffer(raw[:expected], dtype=np.uint8).reshape(height * 3 // 2, width)
        try:
            return cv2.cvtColor(nv12, cv2.COLOR_YUV2BGR_NV12)
        except Exception as e:
            logger.warning(f'手机投屏: NV12 转色失败({e})')
            return None

    def adapt_frame(self, frame):
        """裁到手机画面区(去黑边)并归一化分辨率。"""
        height, width = frame.shape[:2]
        key = (width, height)
        if key != self.rect_key:
            self.rect_key = key
            self.picture_rect = detect_picture_rect(frame)
            if self.picture_rect is None:
                logger.warning(f'手机投屏: 认不出画面区({width}x{height}), 先按整幅处理')
            else:
                x, y, w, h = self.picture_rect
                logger.info(f'手机投屏画面区: x={x} y={y} {w}x{h} (整幅 {width}x{height}, '
                            f'比例 {w / max(1, h):.3f})')
        rect = self.picture_rect
        if rect is None:
            self.scale = 1.0
            return frame
        x, y, w, h = rect
        if w <= 0 or h <= 0 or x + w > width or y + h > height:
            self.scale = 1.0
            return frame
        picture = frame[y:y + h, x:x + w]
        target_width, target_height = normalize_picture_size((w, h), self.target_height)
        if (target_width, target_height) != (w, h):
            interpolation = cv2.INTER_AREA if target_height < h else cv2.INTER_LINEAR
            picture = cv2.resize(picture, (target_width, target_height), interpolation=interpolation)
        self.scale = target_height / h
        return picture

    # ------------------------------------------------------------------
    # 坐标换算与输入
    # ------------------------------------------------------------------

    def screen_size(self):
        """手机整幅画面的尺寸(未经裁剪)。"""
        return self._raw_size

    def picture_size(self):
        """画面区在手机整幅画面里的尺寸。"""
        return None if self.picture_rect is None else self.picture_rect[2:]

    def normalize_point(self, x, y):
        """帧坐标 -> 手机屏幕比例 (0..1, 0..1)。

        帧坐标是裁剪+归一化之后的画面坐标, 这里把裁剪和缩放都还原回手机
        整幅画面, 再换算成比例。
        """
        width, height = self._raw_size
        if width <= 0 or height <= 0:
            return None
        rect = self.picture_rect
        if rect is None:
            px, py = float(x), float(y)
        else:
            rx, ry, _, rh = rect
            scale = self.scale or 1.0
            px = rx + x / scale
            py = ry + y / scale
        nx = min(1.0, max(0.0, px / width))
        ny = min(1.0, max(0.0, py / height))
        return nx, ny

    def send_touch(self, action, x, y):
        """把一次触控发给手机(x, y 是 0..1 的屏幕比例)。"""
        payload = struct.pack('<Bff', action, float(x), float(y))
        return self._send(KIND_TOUCH, payload)

    def send_key(self, key):
        """把一次按键发给手机; 不认识的键返回 False。"""
        code = KEY_CODES.get(str(key).strip().lower())
        if code is None:
            return False
        return self._send(KIND_KEY, struct.pack('<B', code))

    def _send(self, kind, payload):
        sock = self._socket
        if sock is None:
            self.last_error = 'sidecar 未连接'
            return False
        message = struct.pack('<BI', kind, len(payload)) + payload
        try:
            with self._send_lock:
                sock.sendall(message)
            return True
        except Exception as e:
            logger.warning(f'手机投屏: 发送输入失败({e})')
            self.last_error = str(e)
            return False
