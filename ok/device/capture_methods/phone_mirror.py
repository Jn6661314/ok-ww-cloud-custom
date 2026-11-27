"""手机投屏(NectarLink)抓屏适配层。

NectarLink 投屏窗口的客户区里混着它自己的工具条和黑边, 直接抓整个客户区
拿到的帧比例既不是 16:9 也不是手机比例, 识图和坐标换算都会整体偏移。

这里用一个包装器把真正的抓屏方法包起来:
  * 认出「手机画面区」(去掉工具条和黑边), 只留手机画面;
  * 把画面等比归一化到模板原生高度(1080), 帧尺寸恒定 -> 窗口被拖动时框架
    不用反复重载全部模板资源;
  * 点击坐标跟着换算: 帧坐标 -> 画面区像素 -> 客户区坐标 -> 屏幕绝对坐标。
"""

import threading

import cv2

from ok.device.capture_methods.base import BaseWindowsCaptureMethod
from ok.util.logger import Logger

from src.phone_mirror import NORMALIZED_HEIGHT, detect_picture_rect, normalize_picture_size

logger = Logger.get_logger(__name__)


class PhoneMirrorCaptureMethod(BaseWindowsCaptureMethod):
    """投屏窗口抓屏: 裁到手机画面区 + 归一化分辨率 + 坐标换算。

    Args:
        inner: 真正的抓屏方法(WGC / BitBlt)。
        target_height: 归一化后的目标高度, 默认模板原生高度 1080。
    """

    def __init__(self, inner, target_height=NORMALIZED_HEIGHT):
        self.inner = inner
        self.target_height = target_height
        self._size = (0, 0)
        # 兜底的退出事件: 底层抓屏方法没带 exit_event 时用它, 否则框架的
        # get_frame() 会在 self.exit_event.is_set() 上炸掉。
        self._own_exit_event = threading.Event()
        # 手机画面区在客户区里的矩形 (x, y, w, h)
        self.picture_rect = None
        # 画面区只跟窗口尺寸有关, 尺寸没变就不用重新认
        self.rect_key = None
        # 归一化缩放系数(目标高 / 原高)
        self.scale = 1.0

    # ------------------------------------------------------------------
    # 代理: 框架会用到抓屏方法的这些接口
    # ------------------------------------------------------------------

    def __getattr__(self, item):
        # 只在常规查找失败时兜底代理到 inner(框架会访问各种实现细节,
        # 比如 WGC 的 get_capture_hwnd / start_or_stop)。
        inner = self.__dict__.get('inner')
        if inner is None:
            raise AttributeError(item)
        try:
            return getattr(inner, item)
        except AttributeError:
            raise AttributeError(item)

    @property
    def hwnd_window(self):
        return self.inner.hwnd_window

    @hwnd_window.setter
    def hwnd_window(self, hwnd_window):
        self.inner.hwnd_window = hwnd_window

    @property
    def exit_event(self):
        event = getattr(self.inner, 'exit_event', None)
        return event if event is not None else self._own_exit_event

    @exit_event.setter
    def exit_event(self, value):
        try:
            self.inner.exit_event = value
        except Exception:
            pass

    def connected(self):
        return self.inner.connected()

    def clickable(self):
        return self.inner.clickable()

    def close(self):
        self.inner.close()

    def get_name(self):
        return f'{self.inner.get_name()}+投屏适配'

    # ------------------------------------------------------------------
    # 抓帧与画面适配
    # ------------------------------------------------------------------

    def do_get_frame(self):
        frame = self.inner.do_get_frame()
        if frame is None:
            return None
        return self.adapt_frame(frame)

    def do_get_frame_wait(self, timeout):
        getter = getattr(self.inner, 'do_get_frame_wait', None)
        frame = getter(timeout) if getter is not None else self.inner.do_get_frame()
        if frame is None:
            return None
        return self.adapt_frame(frame)

    def adapt_frame(self, frame):
        """裁到手机画面区并归一化分辨率。"""
        height, width = frame.shape[:2]
        key = (width, height)
        if key != self.rect_key:
            self.rect_key = key
            self.picture_rect = detect_picture_rect(frame)
            if self.picture_rect is None:
                logger.warning(f'投屏画面: 认不出手机画面区(客户区 {width}x{height}), 先按整幅处理')
            else:
                x, y, w, h = self.picture_rect
                logger.info(f'投屏画面区: x={x} y={y} {w}x{h} (客户区 {width}x{height}, '
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
    # 坐标换算
    # ------------------------------------------------------------------

    def get_abs_cords(self, x, y):
        """帧坐标 -> 屏幕绝对坐标(把裁剪与归一化都还原回去)。"""
        rect = self.picture_rect
        if rect is None:
            return self.inner.get_abs_cords(x, y)
        scale = self.scale or 1.0
        return self.inner.get_abs_cords(x / scale + rect[0], y / scale + rect[1])

    def picture_size(self):
        """当前画面区在客户区里的尺寸, 没认出来时返回 None。"""
        return None if self.picture_rect is None else self.picture_rect[2:]
