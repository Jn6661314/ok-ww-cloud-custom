import os
import re
import socket
import threading
import time
from concurrent.futures import ThreadPoolExecutor

import cv2
import numpy as np

from ok.device.capture import HwndWindow, BrowserCaptureMethod, update_capture_method, NemuIpcCaptureMethod, \
    ADBCaptureMethod
from ok.device.capture_methods.base import BaseWindowsCaptureMethod
from ok.device.interaction import PostMessageInteraction, GenshinInteraction, ForegroundPostMessageInteraction, \
    PynputInteraction, PyDirectInteraction, BrowserInteraction, ADBInteraction
from ok.core.events import communicate
from ok.util.collection import parse_ratio
from ok.util.config import Config
from ok.util.file import delete_if_exists
from ok.util.handler import Handler
from ok.util.logger import Logger
from ok.util.process import kill_exe
from ok.util.window import windows_graphics_available, find_hwnd

logger = Logger.get_logger(__name__)

# 手机投屏抓屏适配层(裁工具条/黑边 + 归一化分辨率 + 坐标换算)。
# 这个模块是我们新增的文件, 旧版本 ok-ww 里没有, 导入失败时退化成普通抓屏。
try:
    from ok.device.capture_methods.phone_mirror import PhoneMirrorCaptureMethod
except Exception:  # pragma: no cover - 只在旧版本目录里才会发生
    PhoneMirrorCaptureMethod = None

# 手机投屏(内置引擎): 画面来自投屏内核的本机 socket, 点击直接变成手机触点。
# 这两个模块是我们新增的, 旧版本 ok-ww 里没有, 导入失败时退化成普通投屏窗口。
try:
    from ok.device.capture_methods.phone_mirror_socket import PhoneMirrorSocketCaptureMethod
except Exception:  # pragma: no cover - 只在旧版本目录里才会发生
    PhoneMirrorSocketCaptureMethod = None

try:
    from ok.device.interaction_methods.phone_mirror import PhoneMirrorInteraction
except Exception:  # pragma: no cover - 只在旧版本目录里才会发生
    PhoneMirrorInteraction = None

# 安卓设备(真机/模拟器)启动流程里用 adb 拉起游戏的节流参数。
# 模拟器开机后游戏不会自动运行, 需要显式发 LAUNCHER intent;
# 而 do_start 在"等待设备就绪"的循环里会被反复调用, 所以两次拉起之间要留冷却。
ADB_GAME_START_COOLDOWN = 20
# 模拟器刚开机时 adb 可能还没连上, 这里最多等这么久再判定"设备没就绪"。
ADB_DEVICE_READY_TIMEOUT = 60


def resolve_emulator_window_exe(exe_path, instance_name=None):
    """Resolve an emulator launcher path to the instance window executable."""
    if not exe_path:
        return exe_path

    normalized_path = os.path.normpath(exe_path)
    if os.path.basename(normalized_path).lower() != 'mumunxmain.exe':
        return exe_path

    match = re.search(r'-(\d+(?:\.\d+)+)-\d+$', instance_name or '')
    version = match.group(1) if match else '12.0'
    install_root = os.path.dirname(os.path.dirname(normalized_path))
    return os.path.join(
        install_root, 'nx_device', version, 'shell', 'MuMuNxDevice.exe')


def method_name(method):
    return method.__name__ if isinstance(method, type) else str(method)


class DeviceManager:

    def __init__(self, app_config, exit_event=None, global_config=None):
        logger.info('__init__ start')
        self._device = None
        self._adb = None
        self.executor = None
        self.capture_method = None
        self.global_config = global_config
        self._adb_lock = threading.Lock()
        self._adb_game_start_at = 0.0
        if app_config.get('adb'):
            self.packages = app_config.get('adb').get('packages')
        else:
            self.packages = None
        supported_resolution = app_config.get(
            'supported_resolution', {})
        self.supported_ratio = parse_ratio(supported_resolution.get('ratio'))
        self.supported_resolution = supported_resolution
        # 试验性: 把远控/串流软件( UU远程 / ToDesk / 向日葵 / Parsec ... )的窗口当 PC 设备。
        # 打开后 windows 设备不再按"鸣潮客户端 exe + UnrealWindow"匹配, 而是按窗口标题匹配。
        self.stream_window_mode = False
        # 手机投屏(NectarLink): 窗口里是安卓手机画面。抓屏与输入仍走 windows 链路
        # (抓窗口 + 真实键鼠点击, 由投屏软件转到手机), 但任务侧按安卓端处理。
        self.phone_mirror_mode = False
        # 内置投屏引擎: 不抓任何窗口, 画面由自带的投屏内核经本机 socket 推来,
        # 点击直接变成手机上的触点(不再需要安装 NectarLink 桌面端)。
        self.phone_mirror_engine_mode = False
        self.phone_mirror_engine = None
        # 已经最大化过的投屏窗口(hwnd), 避免反复抢用户窗口。
        self._phone_mirror_maximized_hwnd = 0
        # MuMu 网桥模式 adb 自动发现的结果缓存 {模拟器名: (serial or None, 时间戳)}。
        # 没有缓存时每次设备刷新都会 arp + 逐 IP 端口探测, 把设备列表拖慢几十秒。
        self._bridge_cache = {}
        self.windows_capture_config = app_config.get('windows')
        self.adb_capture_config = app_config.get('adb')
        self.browser_config = app_config.get('browser')
        self.debug = app_config.get('debug')
        self.interaction = None
        self.device_dict = {}
        self.exit_event = exit_event
        self.resolution_dict = {}
        default_capture = 'windows' if app_config.get('windows') else (
            'browser' if app_config.get('browser') else 'adb')
        self.config = Config("devices",
                             {"preferred": "", "pc_full_path": "", 'capture': default_capture, 'selected_exe': '',
                              'selected_hwnd': 0, 'interaction': ''})
        self.handler = Handler(exit_event, 'RefreshAdb')
        if self.windows_capture_config is not None:
            if isinstance(self.windows_capture_config.get('exe'), str):
                self.windows_capture_config['exe'] = [self.windows_capture_config.get('exe')]

            self.hwnd_window = HwndWindow(exit_event, self.windows_capture_config.get('title'),
                                          self.windows_capture_config.get('exe'),
                                          hwnd_class=self.windows_capture_config.get('hwnd_class'),
                                          global_config=self.global_config, device_manager=self,
                                          top_hwnd_class=self.windows_capture_config.get('top_hwnd_class'))
            interaction = self.windows_capture_config.get('interaction')
            if isinstance(interaction, list):
                if interaction:
                    selected_interaction = interaction[0]
                else:
                    selected_interaction = 'Pynput'
            else:
                selected_interaction = interaction

            saved_interaction = self.config.get('interaction')
            if saved_interaction:
                if isinstance(interaction, list):
                    for item in interaction:
                        item_name = item.__name__ if isinstance(item, type) else item
                        if saved_interaction == item_name:
                            selected_interaction = item
                            break
                else:
                    item_name = interaction.__name__ if isinstance(interaction, type) else interaction
                    if saved_interaction == item_name:
                        selected_interaction = interaction

            if selected_interaction == 'PostMessage':
                self.win_interaction_class = PostMessageInteraction
            elif selected_interaction == 'Genshin':
                self.win_interaction_class = GenshinInteraction
            elif selected_interaction == 'ForegroundPostMessage':
                self.win_interaction_class = ForegroundPostMessageInteraction
            elif selected_interaction == 'Pynput':
                self.win_interaction_class = PynputInteraction
            elif selected_interaction == 'PyDirect':
                self.win_interaction_class = PyDirectInteraction
            elif selected_interaction:
                self.win_interaction_class = selected_interaction
            else:
                self.win_interaction_class = PynputInteraction
        else:
            self.hwnd_window = None

        logger.info('__init__ end')

    def stop_hwnd(self):
        if self.hwnd_window:
            logger.info(f'stop_hwnd {self.hwnd_window.exe_full_path}')
            if self.hwnd_window.exe_full_path:
                kill_exe(abs_path=self.hwnd_window.exe_full_path)

    def close(self):
        """Stop capture resources before Qt/Python teardown begins."""
        hwnd_window = self.hwnd_window
        if hwnd_window is not None:
            hwnd_window.stop()

        capture_method = self.capture_method
        self.capture_method = None
        if capture_method is not None:
            try:
                capture_method.close()
            except Exception as e:
                logger.error(f'capture method close failed: {e}')

    def select_hwnd(self, exe, hwnd):
        self.config['selected_exe'] = exe
        self.config['selected_hwnd'] = hwnd

    # ------------------------------------------------------------------
    # 试验性: 远控 / 串流软件窗口作为设备
    #
    # UU远程、ToDesk、向日葵、Parsec、Moonlight 这类软件, 本质是把被控电脑的画面
    # 显示成本机的一个窗口, 再把本机的键鼠事件转发过去。所以"抓这个窗口 + 往里发
    # 真实键鼠事件"就等于在操作被控电脑上的游戏, 不需要任何远程专用逻辑。
    #
    # 两个必须注意的点:
    #   1. 远控软件不处理窗口消息(PostMessage 打到它窗口上不会转发), 必须用 Pynput;
    #   2. 窗口客户区必须是 16:9 且画面铺满, 否则坐标换算和识图会整体偏移。
    # ------------------------------------------------------------------
    def set_stream_window(self, title, force_pynput=True, phone=False):
        """把窗口标题匹配 ``title`` 的远控/串流窗口当作 windows 设备。

        Args:
            title: 窗口标题关键字, 字符串会被编译成忽略大小写的正则; 也可直接传 re.Pattern。
                   传 None / 空串时进入"列出所有窗口"模式: 清掉所有过滤, 让设备下拉里
                   出现所有可见窗口(含远控窗口), 由用户手动选——不再静默退回默认 PC 客户端。
            force_pynput: 强制用 PynputInteraction(真实键鼠事件), 远控软件基本都要求这样。
            phone: True 表示窗口里是**安卓手机**画面(NectarLink 手机投屏)。抓屏与输入
                   仍走 windows 链路(抓窗口 + 真实键鼠点击, 由投屏软件转到手机), 但设备
                   会打上 ``phone_mirror`` 标记, 让任务侧按安卓端处理(编队识别/切人等)。

        Returns:
            bool: 是否成功切换。
        """
        if self.windows_capture_config is None:
            logger.warning('stream window mode needs a windows device config')
            return False

        pattern = None
        if title:
            pattern = title if hasattr(title, 'search') else re.compile(str(title).strip(), re.IGNORECASE)
            if not getattr(pattern, 'pattern', ''):
                pattern = None

        self.stream_window_mode = True
        # 手机投屏: 窗口里是安卓手机画面, 任务侧要按安卓端处理。
        self.phone_mirror_mode = bool(phone)
        # 清掉鸣潮客户端的 exe / 窗口类限制, 改成只按标题匹配远控窗口;
        # top_hwnd_class 原本用于 PC 登录器, 对远控窗口没有意义。
        # 没填标题时 pattern=None, update_pc_device 会枚举所有可见窗口供用户在下拉里选。
        self.windows_capture_config['exe'] = None
        self.windows_capture_config['title'] = pattern
        self.windows_capture_config['hwnd_class'] = None
        self.windows_capture_config['top_hwnd_class'] = None
        if force_pynput:
            self.win_interaction_class = PynputInteraction
            self.config['interaction'] = 'Pynput'
        if self.hwnd_window is not None:
            # 远控窗口的尺寸由远控软件(画质/缩放)决定, 程序自动 resize 只会把画面
            # 拉变形或引入黑边, 所以直接禁用自动调整; 分辨率不对仍然会告警。
            self.hwnd_window.try_resize_to = lambda *args, **kwargs: False
            # HwndWindow 在 __init__ 里已经按 PC 客户端参数建好了, 这里重新指向远控窗口。
            # 无标题模式传 None, 待用户在设备下拉里选定窗口后再由框架填具体窗口。
            self.hwnd_window.update_window(pattern, None, 0, 0, -1, None, None)
        logger.info(f'stream window mode enabled, title pattern: {getattr(pattern, "pattern", None)}, '
                    f'phone mirror: {self.phone_mirror_mode}')
        return True

    def set_phone_mirror_engine(self, engine):
        """切到内置投屏引擎(画面来自本机 socket, 不再抓窗口)。

        Args:
            engine: SidecarEngine 实例; None 表示关掉内置引擎。
        """
        self.phone_mirror_engine = engine
        self.phone_mirror_engine_mode = engine is not None
        if engine is not None:
            # 投屏设备在任务侧要按安卓端处理(编队识别/切人/大世界判定)。
            self.phone_mirror_mode = True
            self.stream_window_mode = True
        logger.info(f'phone mirror engine mode: {self.phone_mirror_engine_mode}')

    def check_stream_window_resolution(self):
        """远控/串流模式下检查窗口比例, 不匹配时告警(不阻断, 实验性)。"""
        if not self.stream_window_mode:
            return None
        if self.phone_mirror_mode:
            # 手机投屏: 手机画面比例由设备决定(常见 20:9 横屏), 16:9 检查对手机
            # 没有意义 —— 强行按 16:9 裁会把画面切掉。ok-ww 抓的已经是裁掉
            # NectarLink 工具条和黑边后的手机画面, 坐标按画面区换算, 所以这里
            # 只汇报当前画面尺寸, 不报警告。
            getter = getattr(getattr(self, 'capture_method', None), 'picture_size', None)
            if getattr(self, 'phone_mirror_engine_mode', False):
                picture = getter() if callable(getter) else None
                if picture:
                    logger.info(f'手机投屏画面区 {picture[0]}x{picture[1]}; '
                                f'已归一化到模板原生分辨率, 点击坐标按画面区换算。')
                return None
            window = self.hwnd_window
            if window is None:
                return None
            width = getattr(window, 'width', 0) or getattr(window, 'client_width', 0)
            height = getattr(window, 'height', 0) or getattr(window, 'client_height', 0)
            if width <= 0 or height <= 0:
                return None
            picture = None
            getter = getattr(getattr(self, 'capture_method', None), 'picture_size', None)
            if callable(getter):
                picture = getter()
            if picture:
                logger.info(f'手机投屏画面区 {picture[0]}x{picture[1]} (窗口客户区 {width}x{height}); '
                            f'已归一化到模板原生分辨率, 点击坐标按画面区换算。')
            else:
                logger.info(f'手机投屏窗口客户区 {width}x{height}; 画面区识别中, '
                            f'点击坐标会自动换算成手机屏幕比例。')
            return None
        window = self.hwnd_window
        if window is None:
            return None
        width = getattr(window, 'width', 0) or getattr(window, 'client_width', 0)
        height = getattr(window, 'height', 0) or getattr(window, 'client_height', 0)
        if width <= 0 or height <= 0:
            return None
        ratio = width / height
        if self.supported_ratio is None or abs(ratio - self.supported_ratio) <= 0.02:
            return None
        size = f'{width}x{height}'
        message = (f'远控/串流窗口比例是 {size} (宽高比 {ratio:.3f}), 不是 16:9。'
                   f'请把远控窗口拉成 16:9 并让画面铺满客户区, 同时确认被控电脑上的游戏是全屏运行, '
                   f'否则点击坐标和识图会整体偏移。')
        logger.warning(message)
        try:
            communicate.notification.emit(message, None, True, True, None, None, None)
        except Exception as e:
            logger.debug(f'emit stream window warning failed: {e}')
        return message

    def maximize_phone_mirror_window(self):
        """把投屏窗口最大化, 拿到最大的画面分辨率。

        NectarLink 对最大化/全屏窗口不会再自动改尺寸(源码 MirrorWindow.qml 的
        screenResizeTimer 对 Maximized/FullScreen 直接 return), 所以最大化之后
        窗口尺寸是稳定的, ok-ww 才能把画面归一化到模板原生分辨率; 否则用户
        随手拖一下窗口, 画面比例就变一次, 模板资源也要跟着重载一遍。

        代价是投屏窗口会盖住屏幕(自动化运行时无所谓)。失败不影响继续用。
        """
        window = self.hwnd_window
        if window is None:
            return False
        hwnd = getattr(window, 'hwnd', 0)
        if not hwnd:
            return False
        if getattr(self, '_phone_mirror_maximized_hwnd', 0) == hwnd:
            return True
        try:
            import win32con
            import win32gui
            if not win32gui.IsWindow(hwnd):
                return False
            if win32gui.IsIconic(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_RESTORE)
            win32gui.ShowWindow(hwnd, win32con.SW_MAXIMIZE)
            window.do_update_window_size()
            self._phone_mirror_maximized_hwnd = hwnd
            logger.info(f'投屏窗口已最大化: 客户区 {window.width}x{window.height}')
            return True
        except Exception as e:
            logger.warning(f'投屏窗口最大化失败(不影响使用): {e}')
            return False

    def refresh(self):
        logger.debug('calling refresh')
        return self.handler.post(self.do_refresh, remove_existing=True, skip_if_running=True)

    @property
    def adb(self):
        with self._adb_lock:
            if self._adb is None:
                import adbutils
                logger.debug(f'init adb')
                from adbutils._utils import _get_bin_dir
                bin_dir = _get_bin_dir()
                exe = os.path.join(bin_dir, "adb.exe" if os.name == 'nt' else 'adb')
                from adbutils._utils import _is_valid_exe
                if os.path.isfile(exe) and _is_valid_exe(exe):
                    os.environ['ADBUTILS_ADB_PATH'] = exe
                    logger.info(f'set ADBUTILS_ADB_PATH {os.getenv("ADBUTILS_ADB_PATH")}')
                else:
                    logger.error(f'set ADBUTILS_ADB_PATH failed {exe}')
                self._adb = adbutils.AdbClient(host="127.0.0.1", socket_timeout=4)
                from adbutils import AdbError
                try:
                    self._adb.device_list()
                except AdbError as e:
                    self.try_kill_adb(e)
            return self._adb

    def try_kill_adb(self, e=None):
        logger.error('try kill adb server', e)
        import psutil
        for proc in psutil.process_iter():
            if proc.name() == 'adb.exe' or proc.name() == 'adb':
                logger.info(f'kill adb by process name {proc.cmdline()}')
                try:
                    proc.kill()
                except Exception as e:
                    logger.error(f'kill adb server failed', e)
        logger.info('try kill adb end')

    def adb_connect(self, addr, try_connect=True):
        from adbutils import AdbError
        try:
            for device in self.adb.list():
                if self.exit_event.is_set():
                    logger.error(f"adb_connect exit_event is set")
                    return None
                if device.serial == addr:
                    if device.state == 'offline':
                        logger.info(f'adb_connect offline disconnect first {addr}')
                        self.adb.disconnect(addr)
                    else:
                        logger.info(f'adb_connect already connected {addr}')
                        return self.adb.device(serial=addr)
            if try_connect:
                ret = self.adb.connect(addr, timeout=5)
                logger.info(f'adb_connect try_connect {addr} {ret}')
                return self.adb_connect(addr, try_connect=False)
            else:
                logger.info(f'adb_connect {addr} not in device list {self.adb.list()}')
        except AdbError as e:
            logger.error(f"adb connect error {addr}", e)
            self.try_kill_adb(e)
        except Exception as e:
            logger.error(f"adb connect error return none {addr}", e)

    # MuMu 网桥 adb 自动发现的探测结果缓存时长(秒)。缓存期内不再做 arp +
    # 逐 IP 端口探测, 否则设备列表每次刷新都会被拖慢几十秒。
    BRIDGE_FALLBACK_TTL = 120

    def adb_connect_bridge_fallback(self, emulator):
        """MuMu 网桥(bridge)模式回退: 127.0.0.1:adb_port 无人监听时,
        从 ARP 表发现虚拟机的局域网 IP, 尝试其 5555/16384 adb 端口。

        MuMu 15 开启网桥后, 模拟器获得独立局域网 IP 且 NAT 端口转发不生效,
        adb 必须连 `<vm_ip>:5555`。IP 由 DHCP 分配、每次开机可能变化,
        因此动态发现, 但结果缓存 ``BRIDGE_FALLBACK_TTL`` 秒: 缓存期内直接
        复用上次的 serial(或失败结论), 不再全网探测。
        """
        name_and_path = f"{getattr(emulator, 'name', '')} {getattr(emulator, 'path', '')}".lower()
        if 'mumu' not in name_and_path:
            return None
        now = time.time()
        cached = self._bridge_cache.get(getattr(emulator, 'name', ''))
        if cached is not None and now - cached[1] < self.BRIDGE_FALLBACK_TTL:
            serial = cached[0]
            if serial and self.adb_connect(serial) is not None:
                return serial
            return None
        try:
            import subprocess
            # 中文 Windows 的 arp 输出是 GBK 编码, 不能用 text=True 的默认 utf-8 解码
            proc = subprocess.run(['arp', '-a'], capture_output=True, timeout=10,
                                  creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
            out = proc.stdout.decode(errors='replace')
            candidates = []
            for m in re.finditer(r'(\d+\.\d+\.\d+\.\d+)', out):
                ip = m.group(1)
                if (ip.startswith('127.') or ip.startswith('224.') or ip.startswith('239.')
                        or ip.endswith('.255') or ip in candidates):
                    continue
                candidates.append(ip)
            for ip in candidates:
                for port in (5555, 16384):
                    try:
                        with socket.create_connection((ip, port), timeout=0.25):
                            pass
                    except OSError:
                        continue
                    serial = f'{ip}:{port}'
                    device = self.adb_connect(serial)
                    if device is not None:
                        logger.info(f'MuMu bridge adb discovered {serial} for {emulator.name}')
                        self._bridge_cache[emulator.name] = (serial, now)
                        return device
        except Exception as e:
            logger.error(f'MuMu bridge adb fallback error', e)
        self._bridge_cache[emulator.name] = (None, now)
        return None

    def get_devices(self):
        devices = list(self.device_dict.values())
        def sort_key(d):
            device_type = d.get('device')
            if device_type == 'adb':
                return 0
            if device_type == 'windows':
                return 1
            if device_type == 'browser':
                return 2
            return 3
        return sorted(devices, key=sort_key)

    def _replace_pc_devices(self, pc_devices):
        """Replace window records from the previous Windows enumeration."""
        old_pc_keys = [key for key in self.device_dict if key == 'pc' or key.startswith('pc_')]
        for key in old_pc_keys:
            del self.device_dict[key]
        self.device_dict.update(pc_devices)

    def update_pc_device(self):
        if getattr(self, 'phone_mirror_engine_mode', False):
            # 内置投屏引擎没有窗口, 但框架需要一个"设备"来挂抓屏和输入。
            imei = 'pc_phone_mirror'
            pc_device = {"address": "", "imei": imei, "device": "windows",
                         "model": "", "nick": "手机投屏",
                         "width": 1920, "height": 1080,
                         "hwnd": "手机投屏", "capture": "windows",
                         "connected": True, "full_path": "",
                         "real_hwnd": 0, "exe": None,
                         "phone_mirror": True,
                         "resolution": "1920x1080"}
            self._replace_pc_devices({imei: pc_device})
            return imei
        if self.windows_capture_config is not None:
            if not self.windows_capture_config.get('exe') and not self.windows_capture_config.get('hwnd_class') and not self.windows_capture_config.get('title'):
                from ok.util.window import find_all_visible_windows, get_window_bounds
                windows = find_all_visible_windows()
                pc_devices = {}
                for hwnd, title, exe_name, full_path in windows:
                    x, y, _, _, width, height, m_scaling = get_window_bounds(hwnd)
                    if width > 0 and height > 0:
                        imei = f"pc_{hwnd}"
                        pc_device = {
                            "address": "", "imei": imei, "device": "windows",
                            "model": "", "nick": title, "width": width,
                            "height": height, "hwnd": title, "capture": "windows",
                            "connected": True, "full_path": full_path,
                            "real_hwnd": hwnd, "exe": exe_name,
                            "resolution": f"{width}x{height}"
                        }
                        if self.phone_mirror_mode:
                            pc_device["phone_mirror"] = True
                        pc_devices[imei] = pc_device
                self._replace_pc_devices(pc_devices)
                return None

            # 远控/串流模式下只按窗口标题匹配: exe 可能残留上次选中的 PC 客户端路径,
            # 这里必须忽略, 否则会拿鸣潮 exe 去过滤远控窗口。
            exe_filter = None if self.stream_window_mode else (
                    self.windows_capture_config.get('exe') or self.config.get('selected_exe'))
            name, hwnd, full_path, x, y, width, height, hwnds = find_hwnd(self.windows_capture_config.get('title'),
                                                                   exe_filter, 0, 0,
                                                                   player_id=-1,
                                                                   class_name=self.windows_capture_config.get(
                                                                       'hwnd_class'),
                                                                   selected_hwnd=0 if self.stream_window_mode
                                                                   else self.config.get('selected_hwnd'),
                                                                   top_hwnd_class=self.windows_capture_config.get('top_hwnd_class'))
            if self.stream_window_mode and not hwnd:
                # 远控窗口还没打开: 不建"未连接"的占位设备, 让启动流程去等窗口出现,
                # 而不是走进"启动游戏"分支误报"游戏路径不存在"。
                self._replace_pc_devices({})
                return None
            exe_list = exe_filter
            if isinstance(exe_list, str):
                exe_list = [exe_list]
            nick = name or (exe_list[0] if exe_list else "PC")
            imei = f"pc_{hwnd}" if hwnd else "pc"
            pc_device = {"address": "", "imei": imei, "device": "windows",
                         "model": "", "nick": nick, "width": width,
                         "height": height,
                         "hwnd": nick, "capture": "windows",
                         "connected": hwnd > 0,
                         "full_path": full_path or self.config.get('pc_full_path'),
                         "real_hwnd": hwnd,
                         "exe": exe_list
                         }
            if self.phone_mirror_mode:
                # 手机投屏: 窗口里是安卓手机画面, 任务侧按安卓端处理(编队识别/切人等)。
                pc_device["phone_mirror"] = True
            logger.info(f'update_pc_device pc_device: {pc_device}')
            if full_path and full_path != self.config.get('pc_full_path'):
                logger.info(f'start update_pc_device pc_full_path {full_path}')
                self.config['pc_full_path'] = full_path

            if width != 0:
                pc_device["resolution"] = f"{width}x{height}"
            self._replace_pc_devices({imei: pc_device})
            return imei

    def update_browser_device(self):
        if self.browser_config and windows_graphics_available():
            width, height = self.browser_config.get('resolution', (1280, 720))
            nick = self.browser_config.get('nick', 'Browser')
            connected = False
            if isinstance(self.capture_method, BrowserCaptureMethod):
                connected = self.capture_method.connected()
            self.device_dict['browser'] = {
                "address": self.browser_config.get('url'),
                "imei": 'browser',
                "device": "browser",
                "nick": nick,
                "width": width,
                "height": height,
                "connected": connected,
                "resolution": f"{width}x{height}"
            }

    def do_refresh(self, current=False):
        try:
            self.refresh_emulators(current)
            self.refresh_phones(current)
            self.update_pc_device()
            self.update_browser_device()
        except Exception as e:
            logger.error('refresh error', e)

        if self.exit_event.is_set():
            return
        try:
            self.do_start(notify=False)
        finally:
            communicate.adb_devices.emit(True)

        logger.debug(f'refresh {self.device_dict}')

    def refresh_phones(self, current=False):
        if self.adb_capture_config is None:
            return

        def refresh_one(adb_device):
            imei = self.adb_get_imei(adb_device)
            if imei is not None:
                preferred = self.get_preferred_device()
                if current and preferred is not None and preferred['imei'] != imei:
                    logger.debug(f"refresh current only skip others {preferred['imei']} != {imei}")
                    return None
                found = False
                for device in self.device_dict.values():
                    if device.get('adb_imei') == imei:
                        found = True
                        break
                if not found:
                    width, height = self.get_resolution(adb_device)
                    logger.debug(f'refresh_phones found an phone {adb_device}')
                    phone_device = {"address": adb_device.serial, "device": "adb", "connected": True, "imei": imei,
                                    "nick": adb_device.prop.model or imei, "player_id": -1,
                                    "resolution": f'{width}x{height}', "adb_imei": imei}
                    return imei, phone_device
            return None

        devices = list(self.adb.iter_device())
        if self.exit_event.is_set():
            return
            
        try:
            with ThreadPoolExecutor(max_workers=min(len(devices), 8) if devices else 1) as executor:
                results = list(executor.map(refresh_one, devices))

            for result in results:
                if result:
                    imei, device = result
                    self.device_dict[imei] = device
        except RuntimeError as e:
            if 'shutdown' in str(e):
                logger.debug(f'ThreadPoolExecutor failed during shutdown: {e}')
            else:
                raise
        logger.debug(f'refresh_phones done')

    def refresh_emulators(self, current=False):
        if self.adb_capture_config is None:
            return
        from ok.alas.emulator_windows import EmulatorManager
        manager = EmulatorManager()
        installed_emulators = manager.all_emulator_instances
        logger.info(f'installed emulators {installed_emulators}')

        def refresh_one(emulator):
            preferred = self.get_preferred_device()
            if current and preferred is not None and preferred['imei'] != emulator.name:
                logger.debug(f"refresh current only skip others {preferred['imei']} != {emulator.name}")
                return None
            adb_device = self.adb_connect(emulator.serial)
            if adb_device is None:
                # MuMu 网桥(bridge)模式下 NAT 的 127.0.0.1:port 不会被监听,
                # adb 端口挂在虚拟机自己的局域网 IP 上, 需要自动发现。
                adb_device = self.adb_connect_bridge_fallback(emulator)
            if adb_device is not None:
                adb_width, adb_height = self.get_resolution(adb_device)
            else:
                adb_width, adb_height = 0, 0
            window_exe = resolve_emulator_window_exe(emulator.path, emulator.name)
            name, hwnd, full_path, x, y, width, height, _ = find_hwnd(
                None, window_exe, adb_width, adb_height, emulator.player_id)
            logger.info(
                f'adb_connect emulator result {window_exe} {emulator.player_id} {emulator.type} {adb_device} hwnd_size {width, height} adb_size {adb_width, adb_height} {name, hwnd}')
            connected = adb_device is not None
            address = adb_device.serial if adb_device is not None else emulator.serial
            emulator_device = {"address": address, "device": "adb", "full_path": emulator.path,
                               "connected": connected, "imei": emulator.name, "player_id": emulator.player_id,
                               "nick": name or emulator.name, "emulator": emulator}
            if adb_device is not None:
                emulator_device["resolution"] = f"{adb_width}x{adb_height}"
                emulator_device["adb_imei"] = self.adb_get_imei(adb_device)
            return emulator.name, emulator_device

        if self.exit_event.is_set():
            return
            
        try:
            with ThreadPoolExecutor(max_workers=min(len(installed_emulators), 8) if installed_emulators else 1) as executor:
                results = list(executor.map(refresh_one, installed_emulators))

            for result in results:
                if result:
                    name, device = result
                    self.device_dict[name] = device
        except RuntimeError as e:
            if 'shutdown' in str(e):
                logger.debug(f'ThreadPoolExecutor failed during shutdown: {e}')
            else:
                raise
        logger.info(f'refresh emulators {self.device_dict}')
    def get_resolution(self, device=None):
        if device is None:
            device = self.device
        width, height = 0, 0
        if device is not None:
            if resolution := self.resolution_dict.get(device.serial):
                return resolution
            frame = self.do_screencap(device)
            if frame is not None:
                height, width, _ = frame.shape
                logger.info(f'get_resolution capture frame frame.shape {width, height}')
                if self.supported_ratio is None or abs(width / height - self.supported_ratio) < 0.01:
                    self.resolution_dict[device.serial] = (width, height)
                else:
                    logger.warning(f'resolution error {device.serial} {self.supported_ratio} {width, height}')
            else:
                logger.info(f'get_resolution capture frame is None')
        return width, height

    def set_preferred_device(self, imei=None, index=-1):
        logger.debug(f"set_preferred_device {imei} {index}")
        if index != -1:
            imei = self.get_devices()[index]['imei']
        elif imei is None:
            imei = self.config.get("preferred")
        preferred = self.device_dict.get(imei)
        if preferred is None:
            if len(self.device_dict) > 0:
                connected_device = None
                for device in self.device_dict.values():
                    if device.get('connected') or connected_device is None:
                        connected_device = device
                logger.info(f'first start use first or connected device {connected_device}')
                preferred = connected_device
                imei = preferred['imei']
            else:
                logger.warning(f'no devices')
                return
        if self.config.get("preferred") != imei:
            logger.info(f'preferred device did change {imei}')
            self.config["preferred"] = imei
            if preferred.get('device') == 'windows' and preferred.get('real_hwnd'):
                self.select_hwnd(preferred.get('exe'), preferred.get('real_hwnd'))
            self.start()
        logger.debug(f'preferred device: {preferred}')

    def shell_device(self, device, *args, **kwargs):
        logger.debug(f'adb shell {device} {args} {kwargs}')
        if device is not None:
            try:
                return device.shell(*args, **kwargs)
            except Exception as e:
                error_msg = str(e).lower()
                if 'offline' in error_msg or 'closed' in error_msg:
                    logger.warning(f"shell_device: Device {device.serial} offline or closed, disconnecting to force reconnect. ({e})")
                    try:
                        self.adb.disconnect(device.serial)
                    except Exception as disc_e:
                        logger.error(f'shell_device disconnect failed: {disc_e}')
                raise
        else:
            raise Exception('Device is none')

    def adb_get_imei(self, device):
        try:
            return (self.shell_device(device, "settings get secure android_id", timeout=5) or
                    self.shell_device(device, "service call iphonesubinfo 4", timeout=5) or device.prop.model)
        except Exception as e:
            logger.error(f"adb_get_imei exception: {e}")
            return None

    def do_screencap(self, device) -> np.ndarray | None:
        if device is None:
            return None
        try:
            png_bytes = self.shell_device(device, "screencap -p", encoding=None, timeout=10)
            if png_bytes is not None and len(png_bytes) > 0:
                image_data = np.frombuffer(png_bytes, dtype=np.uint8)
                image = cv2.imdecode(image_data, cv2.IMREAD_COLOR)
                if image is not None:
                    return image
                else:
                    logger.error(f"Screencap image decode error, probably disconnected")
        except Exception as e:
            logger.error('screencap', e)

    def adb_ui_dump(self):
        device = self.device
        if device:
            try:
                dump_output = self.shell_device(device, ["uiautomator", "dump"], encoding='utf-8', timeout=60)
                match = re.search(r"/sdcard/.*\.xml", dump_output)
                if match:
                    dump_file_path = match.group(0)
                    logger.debug(f"Dumped UI file at: {dump_file_path}")
                    xml_content = None
                    local_file_path = os.path.join('temp', 'window_dump.xml')

                    if not os.path.exists('temp'):
                        os.makedirs('temp')

                    delete_if_exists(local_file_path)

                    device.sync.pull(dump_file_path, local_file_path)
                    if os.path.isfile(local_file_path):
                        with open(local_file_path, 'r', encoding='utf-8') as f:
                            xml_content = f.read()
                    return xml_content
                else:
                    logger.error(f"Error: Could not extract the file path from the output:  {dump_output}")
                    return None
            except Exception as e:
                logger.error('adb_ui_dump exception', e)

    def get_preferred_device(self):
        imei = self.config.get("preferred")
        preferred = self.device_dict.get(imei)
        return preferred

    def get_preferred_capture(self):
        """Return the capture method in effect for the preferred device.

        devices.json 的 capture 是全局单值：从 PC/云游戏切到 MuMu 后可能残留
        另一个设备类型的值（如 'browser'）。保存值不在当前设备支持的方法里时，
        回退到 app config 为该设备声明的方法（MuMu 默认 ipc），再退到第一个
        可用方法。

        注意 'windows' 对模拟器是**合法**抓屏方式（窗口抓屏 WGC/BitBlt），
        拉海洛方块依赖它的屏幕坐标 get_abs_cords 与 Pynput 真实键盘旋转，
        不能当残留纠偏掉。
        """
        selected = self.config.get("capture")
        available = self.available_capture_methods()
        if not available or selected in available:
            return selected
        preferred = self.get_preferred_device()
        if preferred and preferred.get('device') == 'adb':
            declared = (getattr(self, 'adb_capture_config', None) or {}).get('capture_method')
            if declared in available:
                return method_name(declared)
        return available[0]

    def available_capture_methods(self, device=None):
        """Return valid capture method identifiers for a selected device."""
        device = device or self.get_preferred_device()
        if not device:
            return []
        kind = device.get('device')
        if kind == 'windows':
            configured = (self.windows_capture_config or {}).get('capture_method', [])
            methods = configured if isinstance(configured, list) else [configured]
            return [method_name(item) for item in (methods or ['windows']) if item]
        if kind == 'browser':
            return ['browser']
        # 模拟器/安卓设备: adb + ipc(MuMu) + windows(窗口抓屏)。
        # windows 必须保留 —— 拉海洛方块靠它拿屏幕坐标(get_abs_cords)并用
        # Pynput 真实键盘走 MuMu 键位映射旋转方块, IPC/adb 抓屏做不到。
        methods = ['adb', 'windows']
        emulator = device.get('emulator')
        if emulator is not None:
            try:
                from ok.alas.emulator_windows import Emulator
                if (emulator and emulator.type == Emulator.MuMuPlayer12
                        and 'MuMuPlayerGlobal' not in str(emulator.path)):
                    methods.append('ipc')
            except (AttributeError, ImportError):
                pass
        return methods

    def available_interaction_methods(self, device=None):
        """Return valid interaction method identifiers for a selected device."""
        device = device or self.get_preferred_device()
        if not device:
            return []
        kind = device.get('device')
        if kind == 'windows':
            configured = (self.windows_capture_config or {}).get('interaction', [])
            methods = configured if isinstance(configured, list) else [configured]
            return [method_name(item) for item in (methods or ['Pynput']) if item]
        if kind == 'browser':
            return ['BrowserInteraction']
        if kind == 'adb':
            return ['ADBInteraction']
        return ['Default Interaction']

    def set_hwnd_name(self, hwnd_name):
        preferred = self.get_preferred_device()
        if preferred.get("hwnd") != hwnd_name:
            preferred['hwnd'] = hwnd_name
            if self.hwnd_window:
                self.hwnd_window.title = hwnd_name
            self.config.save_file()

    def set_capture(self, capture):
        if self.config.get("capture") != capture:
            self.config['capture'] = capture
            self.start()

    def set_interaction(self, interaction):
        interaction_name = interaction.__name__ if isinstance(interaction, type) else interaction
        
        config_interaction = self.windows_capture_config.get('interaction') if self.windows_capture_config else None
        if isinstance(interaction, str):
            if isinstance(config_interaction, list):
                for item in config_interaction:
                    if isinstance(item, type) and item.__name__ == interaction:
                        interaction = item
                        break
            elif isinstance(config_interaction, type) and config_interaction.__name__ == interaction:
                interaction = config_interaction

        if self.config.get("interaction") != interaction_name:
            self.config['interaction'] = interaction_name
            if interaction == 'PostMessage':
                self.win_interaction_class = PostMessageInteraction
            elif interaction == 'Genshin':
                self.win_interaction_class = GenshinInteraction
            elif interaction == 'ForegroundPostMessage':
                self.win_interaction_class = ForegroundPostMessageInteraction
            elif interaction == 'Pynput':
                self.win_interaction_class = PynputInteraction
            elif interaction and interaction != 'PyDirect':
                self.win_interaction_class = interaction
            else:
                self.win_interaction_class = PyDirectInteraction
            self.start()

    def get_hwnd_name(self):
        preferred = self.get_preferred_device()
        return preferred.get('hwnd')

    def ensure_hwnd(self, title, exe, frame_width=0, frame_height=0, player_id=-1, hwnd_class=None, top_hwnd_class=None):
        if self.hwnd_window is None:
            self.hwnd_window = HwndWindow(self.exit_event, title, exe, frame_width, frame_height, player_id,
                                          hwnd_class, global_config=self.global_config, device_manager=self, top_hwnd_class=top_hwnd_class)
        else:
            self.hwnd_window.update_window(title, exe, frame_width, frame_height, player_id, hwnd_class, top_hwnd_class)

    def use_windows_capture(self):
        if getattr(self, 'phone_mirror_engine_mode', False):
            self._use_phone_mirror_engine_capture()
            return
        selected_method = self.config.get('capture')
        valid_methods = self.windows_capture_config.get('capture_method', [])
        if not selected_method or selected_method not in valid_methods:
             if valid_methods:
                 selected_method = valid_methods[0]
        # 投屏模式外面裹了一层适配器, 这里先取回真正的抓屏方法: 否则框架按
        # 类型判断("不是 WGC 就重建")会把适配器丢掉, 画面区裁剪就失效了。
        inner = self.capture_method
        if PhoneMirrorCaptureMethod is not None and isinstance(inner, PhoneMirrorCaptureMethod):
            inner = inner.inner
        self.capture_method = update_capture_method(self.windows_capture_config, inner, self.hwnd_window,
                                                    exit_event=self.exit_event, selected_method=selected_method)
        if self.capture_method is None:
            logger.error(f'cant find a usable windows capture')
        else:
            if (self.phone_mirror_mode and PhoneMirrorCaptureMethod is not None
                    and isinstance(self.capture_method, BaseWindowsCaptureMethod)):
                # 投屏: 窗口客户区里混着 NectarLink 的工具条和黑边, 裹一层适配器
                # 只保留手机画面, 并把画面归一化到模板原生分辨率(帧尺寸恒定,
                # 窗口被拖动时框架也不用反复重载模板资源)。
                self.capture_method = PhoneMirrorCaptureMethod(self.capture_method)
                logger.info('投屏抓屏已启用画面适配: 裁掉工具条/黑边 + 归一化到 1080 高的模板分辨率')
            logger.info(f'capture method {type(self.capture_method)}')
            if self.interaction:
                self.interaction.capture = self.capture_method

    def _use_phone_mirror_engine_capture(self):
        """内置投屏引擎: 画面从本机 socket 收, 不抓窗口。"""
        engine = self.phone_mirror_engine
        if engine is None or PhoneMirrorSocketCaptureMethod is None:
            logger.error('手机投屏: 投屏内核没起来, 无法抓屏')
            self.capture_method = None
            return
        if engine.port is None:
            # 内核还活着 = 还在等手机上线 / 等手机上点「允许」, 多等一会儿;
            # 内核已经退了 = 没必要等, 直接把它报的原因说出来。
            timeout = 30.0 if engine.running else 2.0
            if not engine.wait_ready(timeout=timeout):
                reason = engine.failure_reason
                if reason:
                    logger.error(f'手机投屏: 投屏内核还没就绪: {reason}')
                else:
                    logger.error('手机投屏: 投屏内核还没就绪, '
                                 '请在手机上的 NectarLink 里点「允许」投屏')
                self.capture_method = None
                return
        old = self.capture_method
        if isinstance(old, PhoneMirrorSocketCaptureMethod):
            old.close()
        self.capture_method = PhoneMirrorSocketCaptureMethod(engine.port, exit_event=self.exit_event)
        self.capture_method.start()
        logger.info(f'手机投屏: 已连接投屏内核, 画面端口 {engine.port}')
        if self.interaction:
            self.interaction.capture = self.capture_method

    def start(self):
        self.handler.post(self.do_start, remove_existing=True, skip_if_running=True)

    def do_start(self, notify=True):
        logger.debug(f'do_start')
        preferred = self.get_preferred_device()
        if preferred is None:
            if self.device_dict:
                self.set_preferred_device()
            if notify:
                communicate.adb_devices.emit(True)
            return

        if preferred['device'] == 'windows':
            title = self.windows_capture_config.get('title')
            exe = self.windows_capture_config.get('exe')
            if not exe and not title and preferred.get('real_hwnd'):
                exe = preferred.get('exe')

            if self.stream_window_mode:
                if self.phone_mirror_mode:
                    if getattr(self, 'phone_mirror_engine_mode', False):
                        # 内置投屏引擎: 画面来自本机 socket, 根本没有窗口, 也不做
                        # 16:9 裁剪 —— 手机画面比例由手机决定。
                        pass
                    else:
                        # 手机投屏: 窗口客户区里是手机画面(可能带 NectarLink 工具条
                        # 和黑边), 不做 16:9 参考尺寸裁剪 —— 手机画面比例由手机决定,
                        # 强行按 16:9 裁会把画面切掉。抓屏时由投屏适配层裁到画面区。
                        self.ensure_hwnd(title, exe,
                                         hwnd_class=self.windows_capture_config.get('hwnd_class'),
                                         top_hwnd_class=self.windows_capture_config.get('top_hwnd_class'))
                        # 最大化后 NectarLink 不再自动改窗口尺寸, 画面尺寸稳定,
                        # 归一化后的帧尺寸也就恒定(模板不用反复重载)。
                        self.maximize_phone_mirror_window()
                else:
                    # 远控窗口一般带标题栏(甚至可能有黑边), 传一个 16:9 参考尺寸后
                    # find_hwnd 会先在窗口内部找 16:9 的画面区域, HwndWindow 也会按
                    # 比例裁掉多出来的高度, 这样抓屏内容和坐标换算才能对上。
                    ref_width = preferred.get('width') or 1920
                    self.ensure_hwnd(title, exe, ref_width, max(1, int(ref_width * 9 / 16)),
                                     hwnd_class=self.windows_capture_config.get('hwnd_class'),
                                     top_hwnd_class=self.windows_capture_config.get('top_hwnd_class'))
            else:
                self.ensure_hwnd(title, exe,
                                 hwnd_class=self.windows_capture_config.get('hwnd_class'),
                                 top_hwnd_class=self.windows_capture_config.get('top_hwnd_class'))
            self.use_windows_capture()
            if getattr(self, 'phone_mirror_engine_mode', False) and PhoneMirrorInteraction is not None:
                # 内置引擎: 点击直接发给手机, 不用真实鼠标, 也不需要窗口在前台。
                if not isinstance(self.interaction, PhoneMirrorInteraction):
                    self.interaction = PhoneMirrorInteraction(self.capture_method)
                else:
                    self.interaction.capture = self.capture_method
            elif not isinstance(self.interaction, self.win_interaction_class):
                self.interaction = self.win_interaction_class(self.capture_method, self.hwnd_window)
            elif self.interaction:
                self.interaction.capture = self.capture_method
            preferred['connected'] = self.capture_method is not None and self.capture_method.connected()
            self.check_stream_window_resolution()
        elif preferred['device'] == 'browser':
            if not isinstance(self.capture_method, BrowserCaptureMethod):
                if self.capture_method is not None:
                    self.capture_method.close()
                self.capture_method = BrowserCaptureMethod(
                    self.browser_config, self.exit_event, global_config=self.global_config)
            if not isinstance(self.interaction, BrowserInteraction):
                self.interaction = BrowserInteraction(self.capture_method)

            if not self.capture_method.connected():
                self.capture_method.start_browser()

            preferred['connected'] = self.capture_method.connected()
        else:
            width, height = self.get_resolution()
            # 安卓设备下 capture 必须按当前设备纠偏：从 PC/云游戏切过来时
            # devices.json 可能残留 'windows'，照它走会去找启动器 exe 而 hwnd=0，
            # 明明 adb 已连上却报"设备未连接"。
            capture = self.get_preferred_capture()
            if capture == "windows":
                window_exe = resolve_emulator_window_exe(
                    preferred.get('full_path'), getattr(preferred.get('emulator'), 'name', None))
                self.ensure_hwnd(None, window_exe, width, height, preferred['player_id'])
                logger.info(f'do_start use windows capture {self.hwnd_window.title}')
                self.use_windows_capture()
                # 模拟器窗口抓屏 + 窗口消息交互(如 adb 配置里 interaction=PostMessage):
                # 把模拟器当普通 Windows 窗口驱动, 由模拟器自己的键位映射转成触屏操作。
                if (self.config.get('interaction') and self.win_interaction_class is not None
                        and self.win_interaction_class is not ADBInteraction
                        and self.hwnd_window is not None and self.capture_method is not None
                        and hasattr(self.capture_method, 'get_abs_cords')):
                    if not isinstance(self.interaction, self.win_interaction_class):
                        self.interaction = self.win_interaction_class(self.capture_method, self.hwnd_window)
                    else:
                        self.interaction.capture = self.capture_method
            else:
                if capture == 'ipc':
                    if not isinstance(self.capture_method, NemuIpcCaptureMethod):
                        if self.capture_method is not None:
                            self.capture_method.close()
                        self.capture_method = NemuIpcCaptureMethod(self, self.exit_event)
                    self.capture_method.update_emulator(self.get_preferred_device().get('emulator'))
                    logger.info(f'use ipc capture {preferred}')
                else:
                    if not isinstance(self.capture_method, ADBCaptureMethod):
                        logger.debug(f'use adb capture')
                        if self.capture_method is not None:
                            self.capture_method.close()
                        self.capture_method = ADBCaptureMethod(self, self.exit_event, width=width,
                                                               height=height)
                        logger.info(f'use adb capture {preferred}')
                if preferred.get('full_path'):
                    logger.info(f'ensure_hwnd for debugging {preferred} {width, height}')
                    emulator = preferred.get('emulator')
                    window_exe = resolve_emulator_window_exe(
                        preferred.get('full_path'), getattr(emulator, 'name', None))
                    self.ensure_hwnd(None, window_exe,
                                     width, height,
                                     preferred['player_id'])
                elif self.hwnd_window is not None:
                    self.hwnd_window.stop()
                    self.hwnd_window = None
                # 非窗口抓屏(ipc / adb 截图)一律走 ADBInteraction:
                # 输入由 BaseWWTask.send_key 叠一层真实键盘事件交给模拟器键位映射。
                # 窗口消息交互只在上面 capture == 'windows' 的分支里创建。
                if not isinstance(self.interaction, ADBInteraction):
                    self.interaction = ADBInteraction(self, self.capture_method, width, height)
                else:
                    self.interaction.capture = self.capture_method
                    self.interaction.width = width
                    self.interaction.height = height

            # 安卓设备启动: 模拟器/真机开机后游戏不会自动运行,
            # 这里等设备就绪后用 adb 把鸣潮拉起来(已经在前台则跳过)。
            try:
                self.adb_start_game()
            except Exception as e:
                logger.warning(f'do_start adb_start_game failed: {e}')

        if notify:
            communicate.adb_devices.emit(True)

    def update_resolution_for_hwnd(self):
        if self.hwnd_window is not None and self.hwnd_window.frame_aspect_ratio == 0 and self.adb_capture_config:
            width, height = self.get_resolution()
            logger.debug(f'update resolution for {self.hwnd_window} {width}x{height}')
            self.hwnd_window.update_frame_size(width, height)

    @property
    def device(self):
        if preferred := self.get_preferred_device():
            if self._device is None:
                logger.debug(f'get device connect {preferred}')
                self._device = self.adb_connect(preferred.get('address'))
            if self._device is not None and self._device.serial != preferred.get('address'):
                logger.info(f'get device adb device addr changed {preferred}')
                self._device = self.adb_connect(preferred.get('address'))
        else:
            logger.error(f'self.get_preferred_device returned None')
        return self._device

    def adb_kill_server(self):
        if self.adb is not None:
            self.adb.server_kill()
            logger.debug('adb kill_server')

    @property
    def width(self):
        if self.capture_method is not None:
            return self.capture_method.width
        return 0

    @property
    def height(self):
        if self.capture_method is not None:
            return self.capture_method.height
        return 0

    def update_device_list(self):
        pass

    def clear_devices(self):
        logger.info('clear_devices')
        self.device_dict.clear()
        self.config['preferred'] = ''
        self.config['selected_hwnd'] = 0
        self.config['pc_full_path'] = ''
        self._device = None
        self.resolution_dict.clear()

    def shell(self, *args, **kwargs):
        device = self.device
        logger.debug(f'adb shell {device} {args} {kwargs}')
        if device is not None:
            return self.shell_device(device, *args, **kwargs)
        else:
            raise Exception('Device is none')

    def device_connected(self):
        preferred = self.get_preferred_device()
        if preferred['device'] == 'windows' or preferred['device'] == 'browser':
            return True
        elif self.device is not None:
            try:
                state = self.shell('echo 1', timeout=3)
                logger.debug(f'device_connected check device state is {state}')
                return state is not None
            except Exception as e:
                logger.error(f'device_connected error occurred, {e}')

    def get_exe_path(self, device):
        if self.phone_mirror_mode and device.get('device') == 'windows':
            # 手机投屏: 鸣潮跑在手机上, 本机没有可启动的 exe。
            # 投屏窗口没开时只会提示"游戏路径不存在", 这里说明真实原因。
            logger.info('手机投屏模式: 游戏在手机上运行, 本机不启动游戏; '
                        '请确认 NectarLink 的手机投屏窗口已打开。')
            return None
        path = device.get('full_path')
        if device.get(
                'device') == 'windows' and self.windows_capture_config:
            if not path or path == "none":
                path = None
            if calculate := self.windows_capture_config.get(
                    'calculate_pc_exe_path'):
                calculate_path = path
                if isinstance(calculate, str):
                    path = calculate
                else:
                    try:
                        path = calculate(calculate_path)
                    except Exception as e:
                        logger.error(
                            f'calculate_pc_exe_path failed for caller path {calculate_path}: {e}', e)
                        return None
                logger.info(
                    f'calculate_pc_exe_path caller path {calculate_path}, result {path}')
                if isinstance(path, str) and '://' in path:
                    logger.info(f'path is a url skip checking {path}')
                    return path
            if path and os.path.exists(path):
                return path
            return None
        if not path:
            return None
        elif emulator := device.get('emulator'):
            from ok.alas.platform_windows import get_emulator_exe
            return get_emulator_exe(emulator)
        else:
            return None

    def adb_check_installed(self, packages):
        installed = self.shell('pm list packages', timeout=30)
        if isinstance(packages, str):
            packages = [packages]
        for package in packages:
            if package in installed:
                return package

    def adb_check_in_front(self, packages):
        if not packages:
            return True
        front = self.device is not None and self.device.app_current()
        logger.debug(f'adb_check_in_front {front}')
        if front:
            if isinstance(packages, str):
                packages = [packages]
            for package in packages:
                if package == front.package:
                    return True

    def adb_start_package(self, package):
        self.shell(f'monkey -p {package} -c android.intent.category.LAUNCHER 1')

    def adb_ensure_in_front(self):
        front = self.adb_check_in_front(self.packages)
        logger.debug(f'adb_ensure_in_front {front}')
        if front:
            return front
        elif installed := self.adb_check_installed(self.packages):
            self.adb_start_package(installed)
            return True

    def adb_wait_device_ready(self, timeout=None):
        """等待安卓设备(模拟器)开机就绪。

        模拟器刚起来时 adb 可能还没连上, 或者系统还在开机动画中, 此时执行
        命令会失败。这里轮询到设备能正常回命令为止, 返回是否就绪。
        """
        timeout = ADB_DEVICE_READY_TIMEOUT if timeout is None else timeout
        deadline = time.time() + timeout
        while not self.exit_event.is_set():
            try:
                if self.device is None:
                    # adb 还没连上(模拟器仍在开机): 这里不空等,
                    # 交给"等待设备就绪"的循环下一轮再试。
                    logger.debug('adb_wait_device_ready: device not connected yet')
                    return False
                if self.shell('echo ok', timeout=5):
                    return True
            except Exception as e:
                logger.debug(f'adb_wait_device_ready: device not ready yet ({e})')
            if time.time() >= deadline:
                return False
            time.sleep(1)
        return False

    def adb_start_game(self, force=False):
        """安卓设备启动流程里用 adb 拉起鸣潮。

        模拟器/真机开机后游戏并不会自动运行, 这里显式发 LAUNCHER intent 把
        鸣潮拉起来。已经在前台就不做任何事; 有冷却时间, 避免"等待设备就绪"
        的循环里反复拉起。返回是否成功拉起(或本来就在前台)。
        """
        if not self.packages:
            logger.debug('adb_start_game: no packages configured')
            return False
        now = time.time()
        if not force and now - self._adb_game_start_at < ADB_GAME_START_COOLDOWN:
            logger.debug('adb_start_game: cooling down, skip')
            return False
        try:
            if self.adb_check_in_front(self.packages):
                logger.debug('adb_start_game: game already in front')
                self._adb_game_start_at = now
                return True
            if not self.adb_wait_device_ready():
                logger.warning('adb_start_game: 安卓设备未就绪, 稍后重试拉起游戏')
                return False
            installed = self.adb_check_installed(self.packages)
        except Exception as e:
            logger.warning(f'adb_start_game: 查询游戏包名失败: {e}')
            return False
        if not installed:
            logger.warning(f'adb_start_game: 未找到鸣潮包名 {self.packages}')
            return False
        logger.info(f'adb_start_game: 拉起鸣潮 {installed}')
        try:
            self.adb_start_package(installed)
        except Exception as e:
            logger.warning(f'adb_start_game: 拉起鸣潮失败: {e}')
            return False
        self._adb_game_start_at = now
        return True

    def update_capture(self, config: dict):
        import time
        logger.info(f'update_capture {config}')
        if 'windows' in config:
            win_config = config['windows']
            reset_selected_hwnd = any(
                key in win_config for key in ('title', 'exe', 'hwnd_class', 'top_hwnd_class', 'selected_hwnd')
            )
            selected_hwnd = self.config.get('selected_hwnd')
            self.clear_devices()
            if not reset_selected_hwnd:
                self.config['selected_hwnd'] = selected_hwnd
            for key in ('title', 'hwnd_class', 'top_hwnd_class'):
                if key in win_config:
                    self.windows_capture_config[key] = win_config[key]
            if 'exe' in win_config:
                exe_val = win_config['exe']
                self.windows_capture_config['exe'] = [exe_val] if isinstance(exe_val, str) else exe_val
                self.config['selected_exe'] = exe_val if isinstance(exe_val, str) else exe_val[0]
            if 'selected_hwnd' in win_config:
                self.config['selected_hwnd'] = win_config['selected_hwnd']

            imei = self.update_pc_device()
            if not imei:
                raise Exception("Cannot find window")

            pc = self.device_dict.get(imei)
            if not pc or not pc.get('connected'):
                logger.error(f"Cannot find window. PC device data: {pc}, config: {self.windows_capture_config}")
                raise Exception("Cannot find window")

            self.set_preferred_device(imei)

            if 'interaction' in win_config:
                self.set_interaction(win_config['interaction'])
            if 'capture_method' in win_config:
                self.set_capture(win_config['capture_method'])
            elif 'capture' in win_config:
                self.set_capture(win_config['capture'])

            if 'resolution' in win_config:
                resolution = win_config['resolution']
                if getattr(self, 'hwnd_window', None):
                    for _ in range(50):
                        if self.hwnd_window.hwnd:
                            break
                        time.sleep(0.1)
                    if self.hwnd_window.hwnd:
                        logger.info(f'update_capture try_resize_to {resolution}')
                        res = self.hwnd_window.try_resize_to([resolution])
                        if not res:
                            raise Exception(f"Failed to resize window to {resolution}")
            if getattr(self, 'hwnd_window', None):
                self.hwnd_window.do_update_window_size()
                logger.info(f'update_capture window size {self.hwnd_window.width}x{self.hwnd_window.height}')

        elif 'adb' in config:
            adb_config = config['adb']
            self.clear_devices()
            if 'packages' in adb_config:
                self.packages = adb_config['packages']

            self.refresh_phones()
            self.refresh_emulators()

            connected_adb = None
            for device in self.get_devices():
                if device.get('device') == 'adb' and device.get('connected'):
                    connected_adb = device
                    break

            if not connected_adb:
                raise Exception("Cannot find an connected ADB device")

            self.set_preferred_device(connected_adb['imei'])

            if 'interaction' in adb_config:
                self.set_interaction(adb_config['interaction'])
            if 'capture_method' in adb_config:
                self.set_capture(adb_config['capture_method'])
            elif 'capture' in adb_config:
                self.set_capture(adb_config['capture'])

            if self.packages:
                if not self.adb_ensure_in_front():
                    raise Exception("Failed to start app packages")

            if 'resolution' in adb_config:
                resolution = adb_config['resolution']
                current_res = self.get_resolution()
                if current_res[0] != resolution[0] or current_res[1] != resolution[1]:
                    try:
                        self.shell(f"wm size {resolution[0]}x{resolution[1]}")
                        self.resolution_dict.clear() # clear cache
                    except Exception as e:
                        raise Exception(f"Failed to resize ADB to {resolution}: {e}")

        elif 'browser' in config:
            browser_config = config['browser']
            self.clear_devices()
            if not getattr(self, 'browser_config', None):
                self.browser_config = {}
            self.browser_config.update(browser_config)

            self.update_browser_device()
            bd = self.device_dict.get('browser')
            if not bd:
                 raise Exception("Cannot initialize browser device")

            self.set_preferred_device('browser')
            self.set_capture('browser')

            if 'resolution' in browser_config:
                resolution = browser_config['resolution']
                try:
                    if getattr(self, 'capture_method', None) and hasattr(self.capture_method, 'page'):
                         async def _resize():
                             await self.capture_method.page.set_viewport_size({'width': resolution[0], 'height': resolution[1]})
                         self.capture_method.run_in_loop(_resize())
                except Exception as e:
                    raise Exception(f"Failed to resize browser to {resolution}: {e}")

    def ensure_capture(self, config: dict):
        import time
        logger.info(f'ensure_capture {config}')
        self.clear_devices()
        if 'windows' in config:
            win_config = config['windows']
            for key in ('title', 'hwnd_class', 'top_hwnd_class'):
                if key in win_config:
                    self.windows_capture_config[key] = win_config[key]
                else:
                    self.windows_capture_config.pop(key, None)
            if 'exe' in win_config:
                exe_val = win_config['exe']
                self.windows_capture_config['exe'] = [exe_val] if isinstance(exe_val, str) else exe_val
                self.config['selected_exe'] = exe_val if isinstance(exe_val, str) else exe_val[0]
                
            self.config['selected_hwnd'] = 0
                
            imei = self.update_pc_device()
            if not imei:
                raise Exception("Cannot find window")
            
            pc = self.device_dict.get(imei)
            if not pc or not pc.get('connected'):
                logger.error(f"Cannot find window. PC device data: {pc}, config: {self.windows_capture_config}")
                raise Exception("Cannot find window")
            
            self.set_preferred_device(imei)
            
            if 'interaction' in win_config:
                self.set_interaction(win_config['interaction'])
            if 'capture_method' in win_config:
                self.set_capture(win_config['capture_method'])
            else:
                self.set_capture('windows')
                
            if 'resolution' in win_config:
                resolution = win_config['resolution']
                if getattr(self, 'hwnd_window', None):
                    for _ in range(50):
                        if self.hwnd_window.hwnd:
                            break
                        time.sleep(0.1)
                    if self.hwnd_window.hwnd:
                        logger.info(f'ensure_capture try_resize_to {resolution}')
                        res = self.hwnd_window.try_resize_to([resolution])
                        if not res:
                            raise Exception(f"Failed to resize window to {resolution}")
            if getattr(self, 'hwnd_window', None):
                self.hwnd_window.do_update_window_size()
                logger.info(f'ensure_capture window size {self.hwnd_window.width}x{self.hwnd_window.height}')

        elif 'adb' in config:
            adb_config = config['adb']
            if 'packages' in adb_config:
                self.packages = adb_config['packages']
                
            self.refresh_phones()
            self.refresh_emulators()
            
            connected_adb = None
            for device in self.get_devices():
                if device.get('device') == 'adb' and device.get('connected'):
                    connected_adb = device
                    break
                    
            if not connected_adb:
                raise Exception("Cannot find an connected ADB device")
                
            self.set_preferred_device(connected_adb['imei'])
            
            if 'interaction' in adb_config:
                self.set_interaction(adb_config['interaction'])
            if 'capture_method' in adb_config:
                self.set_capture(adb_config['capture_method'])
            elif self.config.get('capture') not in ('adb', 'ipc'):
                self.set_capture('adb')
                
            if self.packages:
                if not self.adb_ensure_in_front():
                    raise Exception("Failed to start app packages")
                    
            if 'resolution' in adb_config:
                resolution = adb_config['resolution']
                current_res = self.get_resolution()
                if current_res[0] != resolution[0] or current_res[1] != resolution[1]:
                    try:
                        self.shell(f"wm size {resolution[0]}x{resolution[1]}")
                        self.resolution_dict.clear() # clear cache
                    except Exception as e:
                        raise Exception(f"Failed to resize ADB to {resolution}: {e}")

        elif 'browser' in config:
            browser_config = config['browser']
            if not getattr(self, 'browser_config', None):
                self.browser_config = {}
            self.browser_config.update(browser_config)
            
            self.update_browser_device()
            bd = self.device_dict.get('browser')
            if not bd:
                 raise Exception("Cannot initialize browser device")
            
            self.set_preferred_device('browser')
            self.set_capture('browser')
            
            if 'resolution' in browser_config:
                resolution = browser_config['resolution']
                try:
                    if getattr(self, 'capture_method', None) and hasattr(self.capture_method, 'page'):
                         async def _resize():
                             await self.capture_method.page.set_viewport_size({'width': resolution[0], 'height': resolution[1]})
                         self.capture_method.run_in_loop(_resize())
                except Exception as e:
                    raise Exception(f"Failed to resize browser to {resolution}: {e}")
