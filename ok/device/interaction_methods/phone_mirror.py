"""手机投屏(内置引擎)的输入: 点击/滑动/按键直接变成手机上的触点。

投屏模式不再走真实鼠标(Pynput), 而是把坐标换算成手机屏幕比例后直接发给
投屏内核, 由内核转成手机上的触点事件。好处:
  * 不需要投屏窗口在前台, 也不会有鼠标飘到别的窗口上;
  * 坐标按手机画面本身换算, 不受窗口位置/黑边/缩放影响;
  * 长按和滑动都能表达(触点的按下/移动/抬起)。
"""

import time

from ok.device.capture_methods.phone_mirror_socket import TOUCH_DOWN, TOUCH_MOVE, TOUCH_UP
from ok.device.interaction_methods.base import BaseInteraction
from ok.util.logger import Logger

from src import phone_mirror_keymap as keymap

logger = Logger.get_logger(__name__)

# 一次滑动分几步发出去(步数太多会拖慢, 太少手机会当成拖拽而不是滑动)。
SWIPE_STEPS = 12


class PhoneMirrorInteraction(BaseInteraction):
    """把 ok-ww 的点击/滑动/按键变成手机上的触点。

    Args:
        capture: PhoneMirrorSocketCaptureMethod, 负责收画面和发输入。
    """

    def __init__(self, capture):
        super().__init__(capture)

    # ------------------------------------------------------------------
    # 指针
    # ------------------------------------------------------------------

    def _point(self, x, y):
        normalize = getattr(self.capture, 'normalize_point', None)
        if normalize is None:
            return None
        try:
            point = normalize(x, y)
        except Exception as e:
            logger.warning(f'手机投屏: 坐标换算失败({e})')
            return None
        if point is None:
            logger.warning('手机投屏: 还没有画面, 忽略这次点击')
        return point

    def click(self, x=-1, y=-1, move_back=False, name=None, down_time=0.05, move=True, key=None):
        super().click(x, y, name=name)
        point = self._point(x, y)
        if point is None:
            return False
        self.capture.send_touch(TOUCH_DOWN, *point)
        if down_time > 0:
            time.sleep(down_time)
        self.capture.send_touch(TOUCH_UP, *point)
        return True

    def move(self, x, y):
        point = self._point(x, y)
        if point is None:
            return False
        return self.capture.send_touch(TOUCH_MOVE, *point)

    def swipe(self, from_x, from_y, to_x, to_y, duration, settle_time=0):
        start = self._point(from_x, from_y)
        end = self._point(to_x, to_y)
        if start is None or end is None:
            return False
        self.capture.send_touch(TOUCH_DOWN, *start)
        steps = max(1, SWIPE_STEPS)
        # duration 是滑动总时长; 至少给手机留出识别成"滑动"的时间。
        interval = max(0.005, (duration or 0.3) / steps)
        for step in range(1, steps + 1):
            ratio = step / steps
            point = (start[0] + (end[0] - start[0]) * ratio,
                     start[1] + (end[1] - start[1]) * ratio)
            self.capture.send_touch(TOUCH_MOVE, *point)
            time.sleep(interval)
        if settle_time > 0:
            time.sleep(settle_time)
        self.capture.send_touch(TOUCH_UP, *end)
        return True

    # ------------------------------------------------------------------
    # 按键
    # ------------------------------------------------------------------

    def send_key(self, key, down_time=0.02):
        """按键: 有键位映射就发触点, 没有才退回手机按键事件。

        手游只认触点, 按键事件它是收不到的(MuMu 上能生效是因为模拟器自带
        键位映射; 真机没有这一层)。所以 e / 1 / 2 / ` 这些必须查
        ``src/phone_mirror_keymap`` 那张表, 在对应位置按一下。

        命中映射时**不再**走父类的 ADB 按键: 伪设备没有 adb shell, 那一下既是
        白按, 也可能先把异常抛出来挡住后面的触点。语义键(f2 / f_break /
        battle_pass)在 ADB_KEY_MAP 里根本没有对应键码, 更不能交给它。
        """
        point = keymap.lookup(key)
        if point is not None:
            # 用和点击一样的手法: 按下 -> 停一下 -> 抬起, 太短会被游戏吞掉。
            self.capture.send_touch(TOUCH_DOWN, *point)
            time.sleep(max(down_time, 0.02))
            self.capture.send_touch(TOUCH_UP, *point)
            return True
        if not self.capture.send_key(key):
            logger.debug(f'手机投屏: 键 {key} 既没映射也没对应的手机按键, 已忽略')
            return False
        return True

    def back(self):
        self.send_key('esc')

    def input_text(self, text):
        logger.warning('手机投屏: 暂不支持直接输入文字')

    def scroll(self, x, y, scroll_amount):
        logger.warning('手机投屏: 暂不支持滚轮')
