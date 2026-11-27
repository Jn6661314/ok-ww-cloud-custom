"""手机投屏(内置引擎)的配对窗口: 显示二维码和配对码。

二维码用 OpenCV 自带的编码器画(ok-ww 本来就带了 OpenCV, 不需要额外库),
手机用 NectarLink 客户端扫一下即可配对; 之后的投屏不再需要这个窗口。
"""

import cv2
import numpy as np

from ok import Logger

logger = Logger.get_logger(__name__)

# 二维码的边长(像素), 越大手机扫得越稳。
QR_SCALE = 6

# 静区(quiet zone): 标准要求二维码四周留 4 个模块的空白, 否则手机扫不准。
QR_QUIET_ZONE = 4


def qr_matrix(text: str):
    """把一段文字画成二维码矩阵(0/255 的二维数组); 失败时返回 None。

    OpenCV 编码出来的矩阵**已经是标准极性**: 深色模块 = 0, 浅色模块 = 255,
    也就是"白底黑码", 手机扫起来最省事。所以这里原样返回, 不要反相 ——
    反相之后会变成黑底白码, 绝大多数手机扫码器认不出来。
    """
    if not text:
        return None
    try:
        encoder = cv2.QRCodeEncoder_create()
        return encoder.encode(text)
    except Exception as e:
        logger.warning(f'手机投屏: 生成二维码失败({e})')
        return None


def qr_image(text: str, scale: int = QR_SCALE):
    """把一段文字画成二维码图片(BGR); 失败时返回 None。

    编码器只画模块本身, 不画四周的静区。静区是标准的一部分(要求 4 个模块宽),
    少了它手机在屏幕上扫容易失败, 所以这里自己补上。
    """
    matrix = qr_matrix(text)
    if matrix is None:
        return None
    height, width = matrix.shape[:2]
    quiet = QR_QUIET_ZONE
    canvas = np.full((height + 2 * quiet, width + 2 * quiet), 255, dtype=np.uint8)
    canvas[quiet:quiet + height, quiet:quiet + width] = matrix
    canvas = cv2.resize(canvas, (canvas.shape[1] * scale, canvas.shape[0] * scale),
                        interpolation=cv2.INTER_NEAREST)
    return cv2.cvtColor(canvas, cv2.COLOR_GRAY2BGR)


def _to_pixmap(image):
    """把 BGR 的 numpy 图像转成 Qt 的 QPixmap; 失败时返回 None。

    这里有个容易踩的坑: QImage 的 bytesPerLine 是**每行的字节数**, BGR 每像素
    3 字节, 所以必须传 width * 3。传成 width 的话 Qt 会认为每行数据不够,
    直接给出空图 —— 界面上就成了一块白板, 什么也看不见。
    """
    try:
        from PySide6.QtGui import QImage, QPixmap
    except Exception as e:
        logger.warning(f'手机投屏: 没有 Qt, 显示不了二维码({e})')
        return None
    if image is None or image.size == 0:
        return None
    height, width = image.shape[:2]
    # copy() 之前要保证缓冲区是连续的, 否则 Qt 读到的是错位的行。
    data = np.ascontiguousarray(image)
    try:
        qimage = QImage(data.data, width, height, width * 3, QImage.Format_BGR888).copy()
    except Exception as e:
        logger.warning(f'手机投屏: 二维码转 Qt 图像失败({e})')
        return None
    if qimage.isNull():
        logger.warning('手机投屏: 二维码转成了空图像, 界面上会是白板。')
        return None
    return QPixmap.fromImage(qimage)


def _build_dialog_class():
    """把窗口的代码放在函数里, 这样没装 Qt 的环境也能 import 这个模块。"""
    from PySide6.QtCore import Qt, QTimer
    from PySide6.QtWidgets import (QDialog, QHBoxLayout, QLabel, QPushButton, QVBoxLayout)

    class PairingDialog(QDialog):
        """显示配对二维码, 并让用户核对手机上的配对码。"""

        def __init__(self, parent=None, engine=None):
            super().__init__(parent)
            self.engine = engine
            self.setWindowTitle('手机投屏配对')
            self.setMinimumSize(440, 560)

            self.qr_label = QLabel()
            self.qr_label.setAlignment(Qt.AlignCenter)
            self.qr_label.setStyleSheet('background: white; padding: 12px;')
            # 二维码多大取决于配对链接有多长, 让标签跟着图片走。
            self.qr_label.setScaledContents(False)

            self.status_label = QLabel('正在启动投屏内核…')
            self.status_label.setWordWrap(True)

            self.code_label = QLabel('')
            self.code_label.setAlignment(Qt.AlignCenter)
            self.code_label.setStyleSheet('font-size: 22px; font-weight: bold;')

            self.buttons = QHBoxLayout()
            self.confirm_button = QPushButton('我看到的码一致')
            self.confirm_button.clicked.connect(lambda: self._confirm(True))
            self.reject_button = QPushButton('不一致')
            self.reject_button.clicked.connect(lambda: self._confirm(False))
            self.close_button = QPushButton('关闭')
            self.close_button.clicked.connect(self.close)
            self.buttons.addWidget(self.confirm_button)
            self.buttons.addWidget(self.reject_button)
            self.buttons.addWidget(self.close_button)

            layout = QVBoxLayout(self)
            layout.addWidget(QLabel('用手机上的 NectarLink 客户端扫描下面的二维码:'))
            layout.addWidget(self.qr_label)
            layout.addWidget(self.code_label)
            layout.addWidget(self.status_label)
            layout.addLayout(self.buttons)

            self.timer = QTimer(self)
            self.timer.timeout.connect(self.refresh)
            self.timer.start(500)
            self.refresh()

        # ------------------------------------------------------------------

        def _confirm(self, matched):
            if self.engine is not None:
                self.engine.confirm_pairing(matched)
            self.status_label.setText('已回复配对码' if matched else '已拒绝配对')
            self.confirm_button.setEnabled(False)
            self.reject_button.setEnabled(False)

        def refresh(self):
            """按引擎的状态刷新界面。"""
            engine = self.engine
            if engine is None:
                self.status_label.setText('投屏内核没起来')
                return
            if engine.pairing_uri:
                image = qr_image(engine.pairing_uri)
                if image is not None:
                    pixmap = _to_pixmap(image)
                    if pixmap is not None:
                        self.qr_label.setPixmap(pixmap)
                    else:
                        self.status_label.setText('二维码生成失败(见日志)')
            if engine.sas_code:
                self.code_label.setText(f'手机上的配对码: {engine.sas_code}')
                self.confirm_button.setEnabled(True)
                self.reject_button.setEnabled(True)
            if engine.paired:
                self.status_label.setText('配对成功! 可以关闭这个窗口了。')
                self.code_label.setText('')
            elif engine.last_error:
                self.status_label.setText(f'出错了: {engine.last_error}')
            elif engine.pairing_uri:
                self.status_label.setText('等待手机扫码…')

        def closeEvent(self, event):
            self.timer.stop()
            super().closeEvent(event)

    return PairingDialog


def open_pairing_dialog(parent=None, engine=None):
    """打开配对窗口(阻塞式); 返回是否配对成功。"""
    dialog_class = _build_dialog_class()
    dialog = dialog_class(parent, engine)
    dialog.exec()
    return bool(engine is not None and engine.paired)
