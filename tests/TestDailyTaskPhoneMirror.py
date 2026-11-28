"""手机投屏下每日任务的识别修复。

实测手游「活跃行迹」页与 PC 完全不同：
  * 当前活跃度是单独一个数字（如 120），不是 PC 的 "120/100"；
  * 里程碑格子里才有 20/40/60/80/100，不能用 ^\\d+$ 随便取第一个；
  * 左侧页签是纯图标，没有文字可 OCR，PC 的 (0.17,0.12) 会把页面切走；
  * 指南书里用户的「返回」键位可能落在指南书图标上，必须点右上角 X。
"""

import os
import sys
import unittest
from types import SimpleNamespace

WORK = os.environ.get('OKWW_WORK', r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working")
os.chdir(WORK)
sys.path.insert(0, WORK)

from src.task.DailyTask import (  # noqa: E402
    ANDROID_ACTIVITY_PAGE_RE, ANDROID_DAILY_POINTS_FREE_RE,
    ANDROID_DAILY_POINTS_RE, DailyTask,
)
from src.task.touch_mode import TOUCH_PANEL_CLOSE_CLICK, TouchMode  # noqa: E402


def box(name, x, y):
    return SimpleNamespace(name=name, x=x, y=y, width=60, height=30)


class DailyPointsTest(unittest.TestCase):

    def test_free_number_pattern_excludes_fractions_and_stamina(self):
        self.assertEqual(ANDROID_DAILY_POINTS_FREE_RE.match('120').group(1), '120')
        self.assertIsNone(ANDROID_DAILY_POINTS_FREE_RE.match('0/1'))
        self.assertIsNone(ANDROID_DAILY_POINTS_FREE_RE.match('80/240'))
        # 480 这类超出活跃度上限的数字靠代码里的 <= 200 过滤。

    def _fake_task(self, anchors, fractions, free):
        seen = []

        def ocr(x, y, to_x, to_y, match=None, name=None, **kwargs):
            seen.append(name)
            if match is ANDROID_ACTIVITY_PAGE_RE:
                return anchors
            if match is ANDROID_DAILY_POINTS_RE:
                return fractions
            if match is ANDROID_DAILY_POINTS_FREE_RE:
                return free
            return []

        return SimpleNamespace(
            ocr=ocr, height=1080, info_set=lambda *a: None,
            sleep=lambda _: None, tr=lambda s: s, seen=seen,
            log_warning=lambda *a: None, log_info=lambda *a: None,
        )

    def test_standalone_points_beat_milestones_near_bottom_label(self):
        task = self._fake_task(
            anchors=[box('活跃度', 356, 118), box('活跃度', 441, 955)],
            fractions=[],
            free=[box('120', 436, 890), box('20', 809, 959), box('40', 1131, 959)],
        )
        self.assertEqual(DailyTask._android_total_daily_points(task), 120)
        self.assertIn('android_daily_points_free', task.seen)

    def test_fraction_layout_still_works(self):
        task = self._fake_task(
            anchors=[box('活跃度', 441, 955)],
            fractions=[box('60/100', 430, 890)],
            free=[box('120', 436, 890)],
        )
        self.assertEqual(DailyTask._android_total_daily_points(task), 60)

    def test_unknown_points_are_not_reported_as_zero(self):
        task = self._fake_task(anchors=[], fractions=[], free=[])
        self.assertIsNone(DailyTask._android_total_daily_points(task))
        self.assertTrue(task._daily_points_unknown)


class ActivityTraceTest(unittest.TestCase):

    def test_clicks_first_left_icon_when_no_text_is_visible(self):
        clicked = []

        def ocr(*args, **kwargs):
            return []

        task = SimpleNamespace(
            ocr=ocr,
            click_relative=lambda x, y, **kwargs: clicked.append((x, y)),
            sleep=lambda _: None,
            log_info=lambda *a: None,
            log_warning=lambda *a: None,
            tr=lambda s: s,
        )
        DailyTask._android_open_activity_trace(task, time_out=0)
        self.assertIn((0.062, 0.17), clicked,
                      '手游左侧页签没有文字，必须点第一个图标进入活跃行迹')


class ClosePanelTest(unittest.TestCase):

    def test_phone_mirror_closes_book_by_fixed_x(self):
        clicked = []

        class MirrorTouch(TouchMode):
            @property
            def is_phone_mirror(self):
                return True

        task = SimpleNamespace(
            click_relative=lambda x, y, **kwargs: clicked.append((x, y)),
        )
        self.assertTrue(MirrorTouch(task).close_panel())
        self.assertIn(TOUCH_PANEL_CLOSE_CLICK, clicked)

    def test_other_devices_do_not_click_fixed_x(self):
        clicked = []

        class OtherTouch(TouchMode):
            @property
            def is_phone_mirror(self):
                return False

        task = SimpleNamespace(
            click_relative=lambda x, y, **kwargs: clicked.append((x, y)),
        )
        self.assertFalse(OtherTouch(task).close_panel())
        self.assertEqual(clicked, [])


if __name__ == '__main__':
    unittest.main()
