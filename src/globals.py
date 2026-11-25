import os.path

import cv2

from ok import Config, Logger, get_path_relative_to_exe, og

logger = Logger.get_logger(__name__)


class Globals:

    def __init__(self, exit_event):
        self._yolo_model = None
        self.mini_map_arrow = None
        self.logged_in = False
        self._apply_stream_window()

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
            apply_stream_window(global_config, device_manager)
        except Exception as e:
            logger.warning(f'apply stream window failed: {e}')

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
