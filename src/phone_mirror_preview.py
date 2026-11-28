"""投屏状态窗口（已移除实时画面）。

早期这里会单独连一条投屏内核的视频流、把手机画面实时贴到窗口里。现在按需求
去掉：窗口只显示连接状态与「窗口置顶」开关，不再建立视频连接、不抓帧、
不显示任何手机截图。

保留窗口本身和 show_preview()/close_preview() 接口，配置里的按钮照旧可以
打开/关闭它；启动投屏时不会再自动弹这个窗口。
"""

from ok import Logger

logger = Logger.get_logger(__name__)

# 窗口留着引用, 否则 Python 一回收窗口就闪没了。
_windows = []


def _build_window_class():
    """窗口代码放在函数里, 没装 Qt 的环境也能 import 这个模块。"""
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QCheckBox, QLabel, QVBoxLayout, QWidget

    class PreviewWindow(QWidget):
        """投屏状态小窗口；不显示手机画面。"""

        def __init__(self, engine=None, parent=None):
            super().__init__(parent)
            self.engine = engine
            self.setWindowTitle('手机投屏 · 状态')
            self.resize(320, 120)

            self.info = QLabel('已移除预览画面。请直接看手机屏幕了解任务进度。')
            self.info.setAlignment(Qt.AlignCenter)
            self.info.setWordWrap(True)
            self.info.setStyleSheet('background: #111; color: #bbb; padding: 8px;')

            self.status = QLabel('')
            self.status.setStyleSheet('color: #888;')

            self.on_top = QCheckBox('窗口置顶')
            self.on_top.setChecked(True)
            self.on_top.toggled.connect(self._toggle_on_top)

            layout = QVBoxLayout(self)
            layout.addWidget(self.info, 1)
            layout.addWidget(self.status)
            layout.addWidget(self.on_top)

            self._refresh_status()
            self._toggle_on_top(True)

        # ------------------------------------------------------------------

        def _refresh_status(self):
            """只报连接状态，不拉视频流。"""
            engine = self.engine
            if engine is None:
                self.status.setText('未选择投屏设备')
            elif getattr(engine, 'running', False):
                self.status.setText('投屏内核已启动')
            elif getattr(engine, 'port', None) is not None:
                self.status.setText('投屏内核已连接')
            else:
                self.status.setText('投屏内核未启动')

        def _toggle_on_top(self, checked):
            flags = self.windowFlags()
            if checked:
                flags |= Qt.WindowStaysOnTopHint
            else:
                flags &= ~Qt.WindowStaysOnTopHint
            self.setWindowFlags(flags)
            self.show()

    return PreviewWindow


def show_preview(engine, parent=None):
    """打开(或顶到前面)状态窗口; 返回窗口对象, 失败返回 None。"""
    for window in _windows:
        try:
            if window.isVisible():
                window.raise_()
                window.activateWindow()
                return window
        except Exception:
            continue
    try:
        window_class = _build_window_class()
        window = window_class(engine, parent)
        _windows.append(window)
        window.show()
        return window
    except Exception as e:
        logger.error(f'手机投屏: 打开状态窗口失败({e})')
        return None


def close_preview():
    """关掉所有状态窗口。"""
    for window in list(_windows):
        try:
            window.close()
        except Exception:
            pass
    _windows.clear()
