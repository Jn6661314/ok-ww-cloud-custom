"""投屏预览窗口: 在电脑上显示手机画面, 方便看任务跑到哪一步了。

内置引擎模式下 ok-ww 是个"伪设备"(没有窗口), 所以默认什么都看不见 ——
任务卡住时只能猜。这个窗口单独连一条到投屏内核的连接, 实时显示画面,
和任务那条连接互不影响(内核的 serve 是循环 accept, 每个连接独立推流)。
"""

import cv2

from ok import Logger

from src.phone_mirror_pairing import _to_pixmap

logger = Logger.get_logger(__name__)

# 检查新帧的间隔(毫秒)。16ms = 60fps 轮询一次, 但只在画面真的换了的时候才
# 渲染 —— 以前 33ms 定时无脑重画, 最坏凭空多 33ms 延迟, 还白做一遍缩放。
TICK_MS = 16

# 窗口留着引用, 否则 Python 一回收窗口就闪没了。
_windows = []


def _attach(engine):
    """拿到一条画面通道：优先复用任务正在用的那条，没有才自己开。

    Returns:
        (capture, owned)。owned=True 表示这条连接是本窗口开的，关窗时可以关掉；
        任务接手后（adopted_by_task）也视为非本窗口所有。
    """
    if engine is None or engine.port is None:
        return None, False
    try:
        from ok.device.capture_methods.phone_mirror_socket import PhoneMirrorSocketCaptureMethod
        shared = PhoneMirrorSocketCaptureMethod.active_for_port(engine.port)
        if shared is not None:
            return shared, False
        capture = PhoneMirrorSocketCaptureMethod(engine.port)
        if not capture.start():
            capture.close()
            return None, False
        capture.preview_owner = True
        return capture, True
    except Exception as e:
        logger.debug(f'手机投屏: 预览连不上画面端口({e})')
        return None, False


def _build_window_class():
    """窗口代码放在函数里, 没装 Qt 的环境也能 import 这个模块。"""
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget

    class PreviewWindow(QWidget):
        """一个能缩放的小窗口, 实时显示手机画面。"""

        def __init__(self, engine=None, parent=None):
            super().__init__(parent)
            self.engine = engine
            self.capture = None
            self.owns_capture = False
            self.last_seq = -1
            self.setWindowTitle('手机投屏 · 画面')
            self.resize(720, 405)

            self.image = QLabel('正在连接投屏内核…')
            self.image.setAlignment(Qt.AlignCenter)
            self.image.setMinimumSize(320, 180)
            self.image.setStyleSheet('background: #111; color: #bbb;')

            self.status = QLabel('')
            self.status.setStyleSheet('color: #888;')

            self.on_top = QCheckBox('窗口置顶')
            self.on_top.setChecked(True)
            self.on_top.toggled.connect(self._toggle_on_top)

            layout = QVBoxLayout(self)
            layout.addWidget(self.image, 1)
            layout.addWidget(self.status)
            layout.addWidget(self.on_top)

            self.timer = QTimer(self)
            self.timer.timeout.connect(self._tick)
            self.timer.start(TICK_MS)
            self._toggle_on_top(True)

        # ------------------------------------------------------------------

        def _toggle_on_top(self, checked):
            flags = self.windowFlags()
            if checked:
                flags |= Qt.WindowStaysOnTopHint
            else:
                flags &= ~Qt.WindowStaysOnTopHint
            self.setWindowFlags(flags)
            self.show()

        def _tick(self):
            if self.capture is None:
                self.capture, self.owns_capture = _attach(self.engine)
                if self.capture is None:
                    self.status.setText('还没连上投屏内核(先启动内核, 手机上点「允许」)')
                    return
            # 任务接手了这条连接以后，窗口就不拥有它了。
            if getattr(self.capture, 'adopted_by_task', False):
                self.owns_capture = False
            seq = getattr(self.capture, 'frame_seq', -1)
            if seq == self.last_seq:
                return
            frame = self.capture.do_get_frame()
            if frame is None:
                self.status.setText('已连接投屏内核, 等画面…')
                return
            height, width = frame.shape[:2]
            box_w, box_h = self.image.width(), self.image.height()
            if width <= 0 or height <= 0 or box_w <= 0 or box_h <= 0:
                return
            scale = min(box_w / width, box_h / height)
            target = (max(1, int(width * scale)), max(1, int(height * scale)))
            pixmap = _to_pixmap(cv2.resize(frame, target, interpolation=cv2.INTER_AREA))
            if pixmap is None:
                return
            self.last_seq = seq
            self.image.setPixmap(pixmap)
            self.status.setText(f'{width}x{height}')

        def closeEvent(self, event):
            self.timer.stop()
            if self.capture is not None and self.owns_capture:
                self.capture.close()
            self.capture = None
            super().closeEvent(event)

    return PreviewWindow


def show_preview(engine, parent=None):
    """打开(或顶到前面)预览窗口; 返回窗口对象, 失败返回 None。"""
    for window in _windows:
        try:
            if window.isVisible():
                window.raise_()
                window.activateWindow()
                return window
        except Exception:
            continue
    # 内核还没跑就顺手拉起来: 用户点「预览画面」时多半还没启动过它。
    try:
        if engine is not None and engine.port is None and not engine.running:
            engine.start()
    except Exception as e:
        logger.debug(f'手机投屏: 启动内核失败({e})')
    try:
        window_class = _build_window_class()
        window = window_class(engine, parent)
        _windows.append(window)
        window.show()
        return window
    except Exception as e:
        logger.error(f'手机投屏: 打开预览窗口失败({e})')
        return None


def close_preview():
    """关掉所有预览窗口。"""
    for window in list(_windows):
        try:
            window.close()
        except Exception:
            pass
    _windows.clear()
