import os.path

import cv2

from ok import Config, Logger, get_path_relative_to_exe, og

logger = Logger.get_logger(__name__)

# 手机投屏的配置名(与 config.py 里的 ConfigOption 一致)。
PHONE_MIRROR_CONFIG = '手机投屏'
# 两种投屏模式(见 src/phone_mirror_config.py)。
PHONE_MIRROR_MODE_ENGINE = '内置引擎'
PHONE_MIRROR_MODE_DESKTOP = '桌面端'


class Globals:

    def __init__(self, exit_event):
        self._yolo_model = None
        self.mini_map_arrow = None
        self.logged_in = False
        # 远控/串流窗口(UU远程/ToDesk/Moonlight 等)是另一条独立的路, 先处理;
        # 手机投屏在后面, 它的优先级更高(会覆盖成手机设备)。
        self._apply_stream_window()
        self._apply_phone_mirror()

    def _apply_stream_window(self):
        """试验性: 若开了「远控/串流窗口」, 把设备切换成对应窗口。

        框架在构造 my_app 之前已经把 og.device_manager 准备好, 所以这里能直接改
        设备管理器; 必须在 GUI 刷新设备列表之前完成, 否则下拉里还是 PC 客户端。
        """
        try:
            from src.stream_window import apply_stream_window
            device_manager = getattr(og, 'device_manager', None)
            global_config = getattr(og, 'global_config', None)
            if global_config is None and device_manager is not None:
                global_config = getattr(device_manager, 'global_config', None)
            if apply_stream_window(global_config, device_manager):
                self._relax_resolution_for_phone_mirror(device_manager)
        except Exception as e:
            logger.warning(f'apply stream window failed: {e}')

    def _apply_phone_mirror(self):
        """手机投屏: 按「模式」选择走内置内核还是 NectarLink 桌面端。

        两种模式都把设备切换成"手机"(画面里是安卓手机), 任务侧按安卓端处理
        (编队识别/切人/大世界判定)。

          * 内置引擎 —— 画面来自投屏内核推过来的像素, 分辨率/比例完全由手机和
            配置决定, 不再有"分辨率不符合 16:9"的问题;
          * 桌面端   —— 画面来自 NectarLink 桌面端开的投屏窗口, 抓窗口 + 真实
            键鼠点击, 由桌面端按屏幕比例转回手机。
        """
        try:
            from src.phone_mirror_config import MODE_DESKTOP, MODE_ENGINE
        except Exception as e:
            logger.warning(f'phone mirror config unavailable: {e}')
            return False
        device_manager = getattr(og, 'device_manager', None)
        global_config = getattr(og, 'global_config', None)
        if global_config is None and device_manager is not None:
            global_config = getattr(device_manager, 'global_config', None)
        if global_config is None:
            return False
        try:
            option = global_config.get_config(PHONE_MIRROR_CONFIG)
        except Exception as e:
            logger.debug(f'phone mirror config not available: {e}')
            return False
        try:
            if not option.get('Enable', False):
                return False
            mode = str(option.get('模式', MODE_ENGINE) or MODE_ENGINE).strip()
            if mode == MODE_DESKTOP:
                return self._apply_phone_mirror_desktop(option, device_manager)
            return self._apply_phone_mirror_engine(option, device_manager)
        except Exception as e:
            logger.warning(f'apply phone mirror failed: {e}')
            return False

    def _apply_phone_mirror_desktop(self, option, device_manager):
        """桌面端模式: 抓 NectarLink 桌面端开的投屏窗口。

        走的是「远控/串流窗口」那条链路(只按窗口标题匹配), 画面抓自窗口,
        点击用真实键鼠打到窗口上, 由 NectarLink 桌面端转回手机。
        """
        try:
            from src.stream_window import apply_stream_window
            from src.phone_mirror import NECTARLINK_WINDOW_PATTERN
        except Exception as e:
            logger.warning(f'phone mirror desktop mode unavailable: {e}')
            return False
        if device_manager is None:
            return False
        # 直接给窗口标题正则, 不依赖「远控/串流窗口」菜单里的 Preset ——
        # 手机投屏已经是独立的一项设置, 不该再去别的菜单里选一次。
        try:
            ok = apply_stream_window(None, device_manager, title=NECTARLINK_WINDOW_PATTERN, phone=True)
        except TypeError:
            # 旧版 apply_stream_window 没有这些参数, 退回读配置的做法。
            ok = apply_stream_window(None, device_manager)
        if not ok:
            logger.warning('手机投屏(桌面端): 没能切到 NectarLink 投屏窗口。')
            return False
        self._relax_resolution_for_phone_mirror(device_manager)
        logger.info('手机投屏(桌面端): 已启用, 画面来自 NectarLink 桌面端的投屏窗口。')
        return True

    def _apply_phone_mirror_engine(self, option, device_manager):
        """内置引擎模式: 开启时把内核跑起来, 并让设备管理器改用它。

        画面不再来自任何窗口, 而是投屏内核推过来的像素, 所以分辨率/比例完全
        由手机和这里的设置决定, 也就不会再有"分辨率不符合 16:9"的问题。
        """
        try:
            from src.phone_mirror_engine import get_engine
        except Exception as e:
            logger.warning(f'phone mirror engine unavailable: {e}')
            return False
        if device_manager is None:
            return False
        try:
            engine = get_engine()
            engine.configure(device=str(option.get('手机', '')).strip(),
                             max_size=int(option.get('画面宽度', 1920) or 1920),
                             fps=int(option.get('帧率', 30) or 30),
                             bitrate=int(option.get('码率', 8000000) or 8000000))
            if not engine.running:
                engine.start()
            setter = getattr(device_manager, 'set_phone_mirror_engine', None)
            if setter is None:
                logger.warning('phone mirror engine: 当前框架版本不支持, 跳过。')
                return False
            setter(engine)
            self._relax_resolution_for_phone_mirror(device_manager)
            self._schedule_phone_mirror_preview(option)
            logger.info('手机投屏: 已启用(内置引擎), 画面来自内置投屏内核, '
                        '不需要安装 NectarLink 桌面端。')
            return True
        except Exception as e:
            logger.warning(f'apply phone mirror engine failed: {e}')
            return False

    @staticmethod
    def _schedule_phone_mirror_preview(option):
        """给内置引擎开一个画面窗口, 方便看任务跑到哪一步。

        内置引擎的设备是个"伪设备"(没有窗口), 不主动显示的话屏幕上什么都
        看不见, 任务卡住只能猜。窗口单独连一条内核连接, 不影响任务那条。

        延后两秒再开: 这时候 Qt 的事件循环一定起来了。更早创建 QWidget
        会直接崩(不是抛异常, 兜不住)。
        """
        try:
            if not option.get('运行时显示画面', True):
                return
        except Exception:
            return

        def open_it():
            try:
                from src.phone_mirror_engine import get_engine
                from src.phone_mirror_preview import show_preview
                show_preview(get_engine())
            except Exception as e:
                logger.debug(f'手机投屏: 打开预览窗口失败({e})')

        try:
            from PySide6.QtCore import QTimer
            QTimer.singleShot(2000, open_it)
        except Exception as e:
            logger.debug(f'手机投屏: 排不进预览窗口({e})')

    @staticmethod
    def _relax_resolution_for_phone_mirror(device_manager):
        """手机投屏模式下放宽 16:9 分辨率契约。

        投屏画面的比例由手机决定(常见 20:9 横屏), 强行要求 16:9 只会报
        "resolution error 2560x1494" 并弹一个红色错误提示, 而 ok-ww 抓的
        已经是裁掉 NectarLink 工具条和黑边后的手机画面, 识图与坐标都按画面区
        换算, 不需要 16:9。

        把 ratio / min_size 置空即可: 框架的 check_frame_and_resolution 遇到空值
        会直接判定通过, 不再报错也不再尝试 resize 窗口。

        注意 DeviceManager.supported_ratio 在构造时已经算好(16:9), 保持不变 ——
        模板与点击坐标仍按 16:9 锚点换算, 和框架的比例自适应逻辑保持一致。
        """
        if device_manager is None or not getattr(device_manager, 'phone_mirror_mode', False):
            return
        config = getattr(og, 'config', None)
        if not isinstance(config, dict):
            return
        config['supported_resolution'] = {'ratio': None, 'min_size': None, 'resize_to': None}
        logger.info('手机投屏模式: 已放宽 16:9 分辨率契约(画面比例由手机决定)。')

    @property
    def yolo_model(self):
        if self._yolo_model is None:
            weights = get_path_relative_to_exe(os.path.join("assets", "echo_model", "echo.onnx"))
            if og.config.get("ocr").get("params").get("use_openvino"):
                logger.info("yolo_model Using OpenVinoYolo8Detect")
                from src.OpenVinoYolo8Detect import OpenVinoYolo8Detect
                self._yolo_model = OpenVinoYolo8Detect(
                    weights=weights)
            else:
                logger.info("yolo_model Using OnnxYolo8Detect")
                from src.OnnxYolo8Detect import OnnxYolo8Detect
                self._yolo_model = OnnxYolo8Detect(
                    weights=weights)
        return self._yolo_model

    def yolo_detect(self, image, threshold=0.6, label=-1):
        return self.yolo_model.detect(image, threshold=threshold, label=label)


if __name__ == "__main__":
    glbs = Globals(exit_event=None)
