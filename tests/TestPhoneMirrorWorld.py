"""投屏下的"是否在大世界"判定与 back 节流。

背景(实测): android_world 的 ROI 是 1920x1080 基准、按宽高独立缩放的。手机
投屏画面是 2376x1080(2.2:1), 手游 UI 布局不是 PC 的等比缩放 —— 小地图实际在
x 186..383, 换算后 ROI 只到 247, 黄色箭头被框在外面。结果大世界被判成
"不在大世界" -> is_main 恒 False -> ensure_main 每 2 秒点一次返回, 用户看到
的就是"每日任务一直在按返回菜单"。
"""

import os
import sys
import unittest

import numpy as np

WORK = os.environ.get('OKWW_WORK', r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working")
os.chdir(WORK)
sys.path.insert(0, WORK)

from src.task import android_world as aw  # noqa: E402
from src.task.touch_mode import (  # noqa: E402
    BACK_STORM_LIMIT, TouchMode,
)

WIDTH, HEIGHT = 2376, 1080


def dark_frame():
    """大世界的底: 场景偏暗。"""
    return np.full((HEIGHT, WIDTH, 3), 25, dtype=np.uint8)


def paint(frame, rel_box, value=255):
    """在相对区域里涂一块纯色(BGR 同值 -> 低饱和, 高亮度即"白")。"""
    x1, y1 = int(rel_box[0] * WIDTH), int(rel_box[1] * HEIGHT)
    x2, y2 = int(rel_box[2] * WIDTH), int(rel_box[3] * HEIGHT)
    frame[y1:y2, x1:x2] = value


def world_frame():
    """模拟投屏大世界: 暗背景 + 底部血条(细长白条)。"""
    frame = dark_frame()
    x1, y1 = int(aw.PM_HUD_BOX[0] * WIDTH), int(aw.PM_HUD_BOX[1] * HEIGHT)
    x2, y2 = int(aw.PM_HUD_BOX[2] * WIDTH), int(aw.PM_HUD_BOX[3] * HEIGHT)
    frame[y1 + (y2 - y1) // 2:y1 + (y2 - y1) // 2 + 10, x1 + 20:x2 - 20] = 255
    return frame


class PhoneMirrorWorldTest(unittest.TestCase):

    def test_world_with_hud_is_recognised(self):
        ok, reason = aw.in_android_world(world_frame(), phone_mirror=True)
        self.assertTrue(ok, f'投屏大世界被判成不在大世界: {reason}')
        self.assertIn('pm_radar', reason)

    def test_content_panel_is_not_world(self):
        # 指南书这类浅色内容面板: 白色占比高, 但带内容不会命中加载条判据,
        # 必须由投屏判据自己排除。
        panel = np.full((HEIGHT, WIDTH, 3), 235, dtype=np.uint8)
        panel[:, ::40] = 120  # 竖纹打断"贯穿全屏的连续白", 模拟面板内容
        ok, reason = aw.in_android_world(panel, phone_mirror=True)
        self.assertFalse(ok, f'内容面板被当成大世界: {reason}')
        self.assertIn('not_world', reason)

    def test_pure_light_frame_is_not_world(self):
        # 整帧纯浅色(加载页): 由 loading_bar 判据先拦下, 同样不算大世界
        panel = np.full((HEIGHT, WIDTH, 3), 235, dtype=np.uint8)
        ok, reason = aw.in_android_world(panel, phone_mirror=True)
        self.assertFalse(ok, f'纯浅色帧被当成大世界: {reason}')

    def test_dark_screen_without_hud_is_not_world(self):
        # 登录页/过场: 整屏暗、底部没有血条 -> 不能当成大世界
        ok, _ = aw.in_android_world(dark_frame(), phone_mirror=True)
        self.assertFalse(ok)

    def test_pc_judgement_is_untouched(self):
        # 非投屏仍走原来的 1920 基准 ROI, 不能因为加了投屏分支而改变
        signals = aw.detect_world_signals(world_frame())
        self.assertIn('radar_yellow', signals)
        self.assertNotIn('pm_radar', signals)


class FakeTask:

    def __init__(self):
        self.sent = []
        self.warnings = []
        self.backed = 0

    def send_key(self, key, after_sleep=0):
        self.sent.append(key)
        return True

    def back(self, after_sleep=0):
        self.backed += 1

    def log_warning(self, msg):
        self.warnings.append(msg)

    def tr(self, text):
        return text


class MirrorTouch(TouchMode):

    @property
    def is_touch(self):
        return True

    @property
    def is_phone_mirror(self):
        return True


class PcTouch(TouchMode):

    @property
    def is_touch(self):
        return False

    @property
    def is_phone_mirror(self):
        return False


class BackStormTest(unittest.TestCase):

    def test_back_stops_after_limit_and_warns_once(self):
        task = FakeTask()
        touch = MirrorTouch(task)
        results = [touch.back() for _ in range(BACK_STORM_LIMIT + 3)]
        self.assertEqual(results.count(False), 3, '超出上限的 back 必须被拦下')
        self.assertEqual(len(task.sent), BACK_STORM_LIMIT)
        self.assertEqual(len(task.warnings), 1, '只告警一次, 不能刷屏')

    def test_pc_back_is_not_throttled(self):
        task = FakeTask()
        touch = PcTouch(task)
        for _ in range(BACK_STORM_LIMIT + 3):
            touch.back()
        self.assertEqual(task.backed, BACK_STORM_LIMIT + 3)


if __name__ == '__main__':
    unittest.main()
