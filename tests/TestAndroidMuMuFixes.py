# -*- coding: utf-8 -*-
"""v1.5.17: MuMu/安卓端三项修复测试。

1. 每日任务活跃行迹: 手游指南书布局与 PC 不同, PC 专属 OCR 区域全部落空,
   AndroidDailyTask 实测日志 "total daily points 未识别" -> 保守跳过体力。
   新增安卓分支: 宽域 OCR 找 x/100 形式的活跃度读数。
2. 拉海洛方块: 无尽模式详情页没有难度选项(实测报"无法识别难度"),
   开局"无尽模式"玩法说明弹窗挡住棋盘识别(实测 FatalTaskError 截图)。
   新增: 教程弹窗点确认 / 无尽模式明确提示 / 宽域难度兜底 / 返回键兜底。
3. 掉线弹窗按钮变体("重新登录")与频繁掉线提醒。
"""
import os
import re
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

WORK = r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working"
os.chdir(WORK)
sys.path.insert(0, WORK)

from src.task.DailyTask import (ANDROID_ACTIVITY_PAGE_RE, ANDROID_ACTIVITY_TRACE_RE,
                                ANDROID_DAILY_POINTS_RE, DailyTask)
from src.task.RahaiBlocksTask import ChallengeFailed, RahaiBlocksTask
from src.task.BaseWWTask import ANDROID_CONFIRM_TEXTS


def box(name, x=100, y=200):
    return SimpleNamespace(name=name, x=x, y=y, width=60, height=30, confidence=90)


# ---------------------------------------------------------------- DailyTask --
def make_daily(is_adb=True):
    task = DailyTask.__new__(DailyTask)
    task.info_values = {}
    task.unknown = False
    task.ocr_calls = []

    def ocr(*args, **kwargs):
        match = kwargs.get('match')
        task.ocr_calls.append((args, getattr(match, 'pattern', None)))
        results = task._ocr_results.pop(0) if task._ocr_results else []
        if match and results:
            results = [b for b in results if match.search(b.name)]
        return results

    task.ocr = ocr
    task._ocr_results = []
    task.info_set = lambda key, value: task.info_values.__setitem__(key, value)
    task.log_warning = lambda msg, **kw: task.calls.append(('warning', msg))
    task.log_info = lambda msg, **kw: task.calls.append(('info', msg))
    task.calls = []
    task.tr = lambda msg: msg
    task.sleep = lambda seconds=0: None
    task.is_adb = lambda: is_adb
    return task


class TestAndroidDailyPoints(unittest.TestCase):
    """手游端活跃度识别: 宽域 x/100 OCR。"""

    def test_android_points_found(self):
        task = make_daily(is_adb=True)
        task._ocr_results = [[box('今日活跃度 40/100')]]
        self.assertEqual(task.get_total_daily_points(), 40)
        self.assertEqual(task.info_values.get('total daily points'), 40)
        self.assertFalse(getattr(task, '_daily_points_unknown', False))

    def test_android_points_prefers_anchor(self):
        """多个候选时优先取与"活跃度"文字垂直距离最近的读数。"""
        task = make_daily(is_adb=True)
        task._ocr_results = [
            [box('任务进度 3/5', y=300), box('40/100', y=600), box('80/100', y=730)],
            [box('活跃度', y=720)],  # 锚点文字
        ]
        self.assertEqual(task.get_total_daily_points(), 80)

    def test_android_points_invalid_denominator_ignored(self):
        """分母不是 100/200 的计数(如任务进度 3/5)不得误认成活跃度。"""
        task = make_daily(is_adb=True)
        task._ocr_results = [[box('任务进度 3/5')]]
        self.assertIsNone(task.get_total_daily_points())
        self.assertTrue(task._daily_points_unknown)

    def test_android_points_fullwidth_slash(self):
        task = make_daily(is_adb=True)
        task._ocr_results = [[box('活跃度 ６０/１００' if False else '活跃度 60／100')]]
        self.assertEqual(task.get_total_daily_points(), 60)

    def test_pc_path_unchanged(self):
        """PC 端: 原有小区域 OCR 行为不变。"""
        task = make_daily(is_adb=False)
        task._ocr_results = [[box('120')]]
        self.assertEqual(task.get_total_daily_points(), 120)


class TestAndroidActivityTrace(unittest.TestCase):
    """手游端活跃行迹子页签定位。"""

    def test_tab_clicked_when_page_missing(self):
        task = make_daily(is_adb=True)
        task._ocr_results = [
            [],                    # 页面检查: 无活跃度文字
            [box('活跃行迹', y=150)],  # 页签文字
            [box('活跃度 40/100')],   # 点击后页面出现
        ]
        clicks = []
        task.click = lambda target, **kw: clicks.append(target)
        self.assertTrue(task._android_open_activity_trace())
        self.assertEqual(len(clicks), 1, '必须点击"活跃行迹"页签')
        self.assertTrue(any('活跃行迹' in c[1] for c in task.calls if c[0] == 'info'))

    def test_no_click_when_page_already_open(self):
        task = make_daily(is_adb=True)
        task._ocr_results = [[box('活跃度 40/100')]]
        clicks = []
        task.click = lambda target, **kw: clicks.append(target)
        self.assertTrue(task._android_open_activity_trace())
        self.assertEqual(clicks, [], '已在活跃页时不得再点击')

    def test_timeout_warns(self):
        task = make_daily(is_adb=True)
        clicks = []
        task.click = lambda target, **kw: clicks.append(target)
        self.assertFalse(task._android_open_activity_trace(time_out=0.1))
        self.assertTrue(any(c[0] == 'warning' for c in task.calls))

    def test_activity_trace_regex(self):
        self.assertTrue(ANDROID_ACTIVITY_TRACE_RE.search('活跃行迹'))
        self.assertTrue(ANDROID_ACTIVITY_TRACE_RE.search('每日活跃'))
        self.assertTrue(ANDROID_ACTIVITY_PAGE_RE.search('当前活跃度'))
        self.assertTrue(ANDROID_DAILY_POINTS_RE.search('40/100'))
        self.assertTrue(ANDROID_DAILY_POINTS_RE.search('60／100'))
        self.assertIsNone(ANDROID_DAILY_POINTS_RE.search('3/5'))
        self.assertIsNone(ANDROID_DAILY_POINTS_RE.search('12/180'))


# ----------------------------------------------------------- RahaiBlocksTask --
def make_rahai(queue=None, is_adb=False, **attrs):
    task = RahaiBlocksTask.__new__(RahaiBlocksTask)
    task._wait_queue = list(queue or [])
    task.name = 'test'
    task.calls = []

    def wait_until(func, time_out=0, *args, **kwargs):
        if task._wait_queue:
            return task._wait_queue.pop(0)
        return func()

    def ocr(*args, **kwargs):
        match = kwargs.get('match')
        task.calls.append(('ocr', args, getattr(match, 'pattern', None)))
        results = task._ocr_results.pop(0) if task._ocr_results else []
        if match and results:
            results = [b for b in results if match.search(b.name)]
        return results

    task.wait_until = wait_until
    task.ocr = ocr
    task._ocr_results = []
    task.is_adb = lambda: is_adb
    task.is_browser = lambda: False
    task.send_key = lambda key, **kw: task.calls.append(('key', key))
    task.click = lambda *args, **kw: task.calls.append(('click', args))
    task.log_info = lambda msg, **kw: task.calls.append(('info', msg))
    task.log_warning = lambda msg, **kw: task.calls.append(('warning', msg))
    task.tr = lambda msg: msg
    task.sleep = lambda seconds=0: None
    for key, value in attrs.items():
        setattr(task, key, value)
    return task


class TestTutorialConfirm(unittest.TestCase):
    """开局"无尽模式"玩法说明弹窗: 点掉居中确认按钮。"""

    def test_clicks_confirm(self):
        task = make_rahai()
        task._ocr_results = [
            [box('无尽模式')],   # 弹窗文字
            [box('确认', y=1000)],  # 确认按钮
        ]
        self.assertTrue(task._tutorial_confirm())
        self.assertEqual(len([c for c in task.calls if c[0] == 'click']), 1)

    def test_no_popup_no_click(self):
        task = make_rahai()
        task._ocr_results = [[], []]
        self.assertFalse(task._tutorial_confirm())
        self.assertEqual([c for c in task.calls if c[0] == 'click'], [])

    def test_popup_without_confirm_button(self):
        task = make_rahai()
        task._ocr_results = [[box('无尽模式')], []]
        self.assertFalse(task._tutorial_confirm())
        self.assertEqual([c for c in task.calls if c[0] == 'click'], [])


class TestEndlessPage(unittest.TestCase):
    """无尽模式详情页: 无难度选项, 明确提示不支持自动挑战。"""

    def test_endless_message(self):
        task = make_rahai()
        task._event_title = lambda: [box('拉海洛方块·逆转')]
        task._ocr_results = [
            [],  # narrow 困难
            [],  # narrow 简单
            [],  # wide 困难
            [],  # wide 简单
            [box('无尽模式')],  # _endless_page
        ]
        with self.assertRaises(ChallengeFailed) as ctx:
            task._challenge_current_details(object())
        self.assertIn('无尽模式', str(ctx.exception))

    def test_generic_message_when_not_endless(self):
        task = make_rahai()
        task._event_title = lambda: []
        task._ocr_results = [[], [], [], [], []]
        with self.assertRaises(ChallengeFailed) as ctx:
            task._challenge_current_details(object())
        self.assertIn('难度', str(ctx.exception))
        self.assertNotIn('无尽', str(ctx.exception))


class TestWideDifficulty(unittest.TestCase):
    """宽域难度识别: 同时读到简单/困难页签时取最靠上的(标题区)。"""

    def test_topmost_box_wins(self):
        task = make_rahai(is_adb=True)
        task._ocr_results = [[box('简单', y=700), box('困难', y=200)]]
        self.assertEqual(task._widest_selected_difficulty(), '困难')

    def test_none_when_absent(self):
        task = make_rahai(is_adb=True)
        task._ocr_results = [[], []]
        self.assertIsNone(task._widest_selected_difficulty())


class TestReturnToListAdb(unittest.TestCase):
    """手游端返回关卡列表: X 坐标失效时用安卓返回键兜底。"""

    def test_esc_fallback(self):
        detail = SimpleNamespace(name='关卡目标')
        task = make_rahai(is_adb=True)
        task._stage_details = lambda: [detail]  # 第一次检查: 在详情页
        task._go_now_button = lambda: []
        task._stage_list = lambda: [(SimpleNamespace(name='关卡一', x=1, y=2),
                                     SimpleNamespace(name='进行中 0/2', x=1, y=3))]
        with patch.object(RahaiBlocksTask, 'frame', new_callable=PropertyMock):
            # X 点击后列表仍不在 -> esc 兜底后列表出现
            task._wait_queue = [None, None]  # X 后的 go_now / stage_list 都失败
            result = task._return_to_list()
        self.assertEqual(len(result), 1)
        self.assertTrue(any(c == ('key', 'esc') for c in task.calls), '必须用安卓返回键兜底')

    def test_pc_no_esc(self):
        detail = SimpleNamespace(name='关卡目标')
        task = make_rahai(is_adb=False)
        task._stage_details = lambda: [detail]
        task._go_now_button = lambda: []
        task._stage_list = lambda: []
        with self.assertRaises(RuntimeError):
            task._return_to_list()
        self.assertNotIn(('key', 'esc'), task.calls, 'PC 端不得使用返回键兜底')


# --------------------------------------------------------------- BaseWWTask --
class TestDisconnectButtonVariants(unittest.TestCase):
    """掉线弹窗按钮变体与频繁掉线提醒。"""

    def test_relogin_button_in_confirm_list(self):
        for text in ('重新登录', '重新连接', '确认'):
            self.assertIn(text, ANDROID_CONFIRM_TEXTS)

    def test_frequency_warning(self):
        task = DailyTask.__new__(DailyTask)
        task._android_disconnect_times = []
        warnings = []
        task.log_warning = lambda msg, **kw: warnings.append(msg)
        task.tr = lambda msg: msg
        task._track_android_disconnect_frequency()
        task._track_android_disconnect_frequency()
        self.assertEqual(warnings, [], '未达阈值不得提醒')
        task._track_android_disconnect_frequency()
        self.assertEqual(len(warnings), 2, '达到阈值后提醒(日志+通知两条)')
        # 30 分钟内不重复提醒
        task._track_android_disconnect_frequency()
        self.assertEqual(len(warnings), 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
