import os.path

import cv2

from ok import Config, Logger, get_path_relative_to_exe, og

logger = Logger.get_logger(__name__)

# 内置投屏引擎的配置名(与 config.py 里的 ConfigOption 一致)。
PHONE_MIRROR_ENGINE_CONFIG = '手机投屏(内置引擎)'


class Globals:

    def __init__(self, exit_event):
        self._yolo_model = None
        self.mini_map_arrow = None
        self.logged_in = False
        self._apply_stream_window()
        self._apply_phone_mirror_engine()

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

    def _apply_phone_mirror_engine(self):
        """内置投屏引擎: 开启时把内核跑起来, 并让设备管理器改用它。

        画面不再来自任何窗口, 而是投屏内核推过来的像素, 所以分辨率/比例完全
        由手机和这里的设置决定, 也就不会再有"分辨率不符合 16:9"的问题。
        """
        try:
            from src.phone_mirror_engine import get_engine
        except Exception as e:
            logger.warning(f'phone mirror engine unavailable: {e}')
            return False
        device_manager = getattr(og, 'device_manager', None)
        global_config = getattr(og, 'global_config', None)
        if global_config is None and device_manager is not None:
            global_config = getattr(device_manager, 'global_config', None)
        if global_config is None:
            return False
        try:
            option = global_config.get_config(PHONE_MIRROR_ENGINE_CONFIG)
        except Exception as e:
            logger.debug(f'phone mirror engine config not available: {e}')
            return False
        try:
            if not option.get('Enable', False):
                return False
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
            logger.info('手机投屏(内置引擎): 已启用, 画面来自内置投屏内核, '
                        '不需要安装 NectarLink 桌面端。')
            return True
        except Exception as e:
            logger.warning(f'apply phone mirror engine failed: {e}')
            return False

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
