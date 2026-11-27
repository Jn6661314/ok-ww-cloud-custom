"""校准手机投屏的键位映射: 在投屏画面上点一下, 把这个位置绑到某个键。

为什么要有这个窗口
------------------
投屏下 ok-ww 的按键要变成手机触点才能生效(手游不认按键事件)。键在屏幕上的
位置取决于手机分辨率、刘海、游戏里的自定义布局 —— 猜不出来, 所以让用户点一次。
一个键点一下, 十秒能点完, 之后就和 MuMu 上的键位映射一样了。

用法: 全局配置 -> 手机投屏 -> 「校准键位」。
"""

import cv2

from ok import Logger

from src import phone_mirror_keymap as keymap
from src.phone_mirror_pairing import _to_pixmap

logger = Logger.get_logger(__name__)

# 校准窗口里画面的显示宽度(像素)。太大占屏幕, 太小点不准。
DISPLAY_WIDTH = 900

# 画面显示的最大高度: 手机竖屏时按宽度缩放会撑到两千像素, 屏幕放不下。
MAX_DISPLAY_HEIGHT = 660


def _attach_capture(engine):
    """连上投屏内核的画面端口, 返回一个能取帧的 capture; 连不上返回 None。"""
    if engine is None:
        return None
    if engine.port is None:
        # 内核还没跑起来: 拉起来并稍等一会儿。只等 3 秒 —— 这个函数是在界面
        # 定时器里调的, 等太久整个窗口就卡住了; 没就绪下次再试。
        if not engine.start():
            return None
        if not engine.wait_ready(timeout=3):
            return None
    try:
        from ok.device.capture_methods.phone_mirror_socket import PhoneMirrorSocketCaptureMethod
        capture = PhoneMirrorSocketCaptureMethod(engine.port)
        if not capture.start():
            capture.close()
            return None
        return capture
    except Exception as e:
        logger.error(f'手机投屏: 校准窗口连不上画面端口({e})')
        return None


def _build_dialog_class():
    """把窗口代码放在函数里, 没装 Qt 的环境也能 import 这个模块。"""
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QListWidget,
                                   QListWidgetItem, QPushButton, QVBoxLayout)

    class ClickLabel(QLabel):
        """点一下就能读到相对坐标的画面标签。"""

        def __init__(self, on_click):
            super().__init__()
            self._on_click = on_click
            self.setAlignment(Qt.AlignCenter)
            self.setStyleSheet('background: #111;')

        def mousePressEvent(self, event):
            width, height = self.width(), self.height()
            if width > 0 and height > 0:
                pos = event.position()
                self._on_click(pos.x() / width, pos.y() / height)
            super().mousePressEvent(event)

    class CalibrationDialog(QDialog):
        """左边选键, 右边在画面上点位置。"""

        def __init__(self, parent=None, engine=None):
            super().__init__(parent)
            self.engine = engine
            self.capture = None
            # 只装用户校准过的键: 拿 keymap.load() 会把默认的 esc/escape 带进来,
            # 存盘时它们会把用户刚点的 ` 覆盖掉(见 keymap.save 里的注释)。
            self.mapping = keymap.load_user()
            self.setWindowTitle('手机投屏 · 校准键位')
            self.setMinimumWidth(DISPLAY_WIDTH + 300)

            self.list = QListWidget()
            self.list.setMinimumWidth(240)

            self.image = ClickLabel(self._on_pick)
            self.image.setFixedSize(DISPLAY_WIDTH, int(DISPLAY_WIDTH * 9 / 16))

            self.hint = QLabel('先选左边的键, 再在右边画面上点它对应的按钮。')
            self.hint.setWordWrap(True)

            # 必须在 hint 建好之后再连: 填充列表会触发 currentRowChanged,
            # 那一下就去读 self.hint 了。
            self.list.currentRowChanged.connect(lambda _: self._update_hint())
            self._fill_list()

            self.save_button = QPushButton('保存')
            self.save_button.clicked.connect(self._save)
            close_button = QPushButton('关闭')
            close_button.clicked.connect(self.close)
            buttons = QHBoxLayout()
            buttons.addWidget(self.save_button)
            buttons.addWidget(close_button)

            right = QVBoxLayout()
            right.addWidget(self.image)
            right.addWidget(self.hint)
            right.addLayout(buttons)
            layout = QHBoxLayout(self)
            layout.addWidget(self.list)
            layout.addLayout(right)

            self.timer = QTimer(self)
            self.timer.timeout.connect(self._refresh_frame)
            self.timer.start(500)
            self._refresh_frame()

        # ------------------------------------------------------------------

        def _fill_list(self, keep_row=0):
            self.list.blockSignals(True)
            self.list.clear()
            for key, label in keymap.CALIBRATION_KEYS:
                name = keymap.normalize_key(key)
                text = f'{label}  ({key})'
                point = self.mapping.get(name)
                if point is not None:
                    text += f'  ✓ {point[0]:.3f}, {point[1]:.3f}'
                else:
                    default = keymap.DEFAULT_KEYMAP.get(name)
                    if default is not None:
                        text += f'  (默认 {default[0]:.3f}, {default[1]:.3f})'
                item = QListWidgetItem(text)
                item.setData(Qt.UserRole, key)
                self.list.addItem(item)
            self.list.setCurrentRow(max(0, min(keep_row, self.list.count() - 1)))
            self.list.blockSignals(False)

        def _current_key(self):
            item = self.list.currentItem()
            return None if item is None else item.data(Qt.UserRole)

        def _update_hint(self):
            key = self._current_key()
            if key is None:
                self.hint.setText('先选一个键。')
                return
            label = dict(keymap.CALIBRATION_KEYS).get(key, key)
            self.hint.setText(f'请点画面上的「{label}」按钮。点完会自动跳到下一个键。')

        def _on_pick(self, x_ratio, y_ratio):
            key = self._current_key()
            if key is None:
                self.hint.setText('先在左边选一个键, 再点画面。')
                return
            self.mapping[keymap.normalize_key(key)] = (x_ratio, y_ratio)
            logger.info(f'手机投屏: 键位 {key} -> {x_ratio:.3f}, {y_ratio:.3f}')
            row = self.list.currentRow()
            self._fill_list(keep_row=row)
            # 自动跳到下一个还没设置的键, 都设置完了就停着。
            for offset in range(1, self.list.count() + 1):
                index = (row + offset) % self.list.count()
                key_at = self.list.item(index).data(Qt.UserRole)
                if self.mapping.get(keymap.normalize_key(key_at)) is None:
                    self.list.setCurrentRow(index)
                    break
            else:
                self.list.setCurrentRow(row)

        def _refresh_frame(self):
            if self.capture is None:
                self.capture = _attach_capture(self.engine)
                if self.capture is None:
                    self.hint.setText('拿不到投屏画面: 先在「手机投屏」里点「启动投屏内核」, '
                                      '并在手机上点「允许」。')
                    return
            frame = self.capture.do_get_frame()
            if frame is None:
                return
            height, width = frame.shape[:2]
            if width <= 0 or height <= 0:
                return
            # 竖屏时只按宽度缩放会把窗口撑到两千像素高(屏幕放不下), 所以宽高
            # 都要卡: 取更小的那个缩放比。
            scale = min(DISPLAY_WIDTH / width, MAX_DISPLAY_HEIGHT / height)
            target = (max(1, int(width * scale)), max(1, int(height * scale)))
            pixmap = _to_pixmap(cv2.resize(frame, target))
            if pixmap is None:
                return
            self.image.setPixmap(pixmap)
            self.image.setFixedSize(target[0], target[1])
            self.setMinimumWidth(target[0] + 300)

        def _save(self):
            if keymap.save(self.mapping):
                self.save_button.setText('已保存')
                self.save_button.setEnabled(False)
                self.hint.setText(f'已保存到 {keymap.keymap_path()}')
            else:
                self.hint.setText('保存失败(见日志)')

        def closeEvent(self, event):
            self.timer.stop()
            if self.capture is not None:
                self.capture.close()
                self.capture = None
            super().closeEvent(event)

    return CalibrationDialog


def open_calibration_dialog(parent=None, engine=None):
    """打开校准窗口(阻塞式); 返回是否保存过。"""
    dialog_class = _build_dialog_class()
    dialog = dialog_class(parent, engine)
    dialog.exec()
    return bool(keymap.is_calibrated())
