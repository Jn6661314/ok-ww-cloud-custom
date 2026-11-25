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
import time
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
            if isinstance(match, str):
                results = [b for b in results if match in b.name]
            else:
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
    """无尽模式: v1.5.18 起直接支持开始/加入对局, 不再提示不支持。"""

    def _detail_endless_task(self):
        task = make_rahai()
        task._event_title = lambda: [box('拉海洛方块·逆转')]
        task._ocr_results = [
            [],  # narrow 困难
            [],  # narrow 简单
            [],  # wide 困难
            [],  # wide 简单
            [box('无尽模式')],  # _endless_page
        ]
        return task

    def test_endless_details_direct_start(self):
        """无尽模式详情页: _challenge_current_details 直接转 _challenge_endless。"""
        task = self._detail_endless_task()
        played = []
        task._challenge_endless = lambda interaction: played.append(interaction)
        task._challenge_current_details(object())
        self.assertEqual(len(played), 1, '必须直接调用 _challenge_endless 开始无尽')

    def test_endless_still_startable(self):
        task = self._detail_endless_task()
        task._challenge_endless = lambda interaction: None
        # 不得抛 ChallengeFailed
        task._challenge_current_details(object())

    def test_generic_message_when_not_endless(self):
        task = make_rahai()
        task._event_title = lambda: []
        task._ocr_results = [[], [], [], [], []]
        with self.assertRaises(ChallengeFailed) as ctx:
            task._challenge_current_details(object())
        self.assertIn('难度', str(ctx.exception))
        self.assertNotIn('无尽', str(ctx.exception))


class TestEndlessIngame(unittest.TestCase):
    """已在无尽模式对局内: 局内 UI/弹窗/棋盘 任一特征即可识别。"""

    def test_ingame_ui_detected(self):
        task = make_rahai()
        task._event_title = lambda: [box('拉海洛方块·逆转')]
        task._ocr_results = [
            [],                     # ENDLESS_POPUP_RE 区域
            [box('历史最高')],       # ENDLESS_INGAME_RE 区域
        ]
        task._playable_board = lambda: None
        self.assertTrue(task._endless_ingame())

    def test_popup_text_detected(self):
        task = make_rahai()
        task._event_title = lambda: [box('拉海洛方块·逆转')]
        task._ocr_results = [
            [box('玩家可以一直游玩争取获取更高的分数，直到失败')],  # 弹窗文字
        ]
        task._playable_board = lambda: None
        self.assertTrue(task._endless_ingame())

    def test_board_detected(self):
        task = make_rahai()
        task._event_title = lambda: [box('拉海洛方块·逆转')]
        task._ocr_results = [[], []]
        task._playable_board = lambda: object()
        self.assertTrue(task._endless_ingame())

    def test_not_ingame_without_title(self):
        task = make_rahai()
        task._event_title = lambda: []
        self.assertFalse(task._endless_ingame())

    def test_endless_goal_parse(self):
        task = make_rahai()
        task._ocr_results = [[box('达到9999分结算可得首通奖励', y=170)]]
        self.assertEqual(task._endless_goal(), 9999)

    def test_endless_goal_absent(self):
        task = make_rahai()
        task._ocr_results = [[box('进行中 0/2', y=170)]]
        self.assertIsNone(task._endless_goal())

    def test_endless_score_parse(self):
        task = make_rahai()
        task._ocr_results = [[box('拉海洛方块·逆转', y=40), box('3600', y=90)]]
        self.assertEqual(task._endless_score(), 3600)


class TestChallengeButtonWide(unittest.TestCase):
    """开始按钮宽域兜底: 无尽模式/手游端按钮位置可能偏移。"""

    def test_narrow_wins(self):
        task = make_rahai()
        task._ocr_results = [[box('开始挑战', y=1010)]]
        self.assertIsNotNone(task._challenge_button(wide=True))

    def test_wide_fallback_plain_start(self):
        task = make_rahai()
        task._ocr_results = [
            [],                 # narrow "开始挑战"
            [box('开始', y=990)],  # wide "^开始(挑战)?$"
        ]
        self.assertIsNotNone(task._challenge_button(wide=True))

    def test_none_when_absent(self):
        task = make_rahai()
        task._ocr_results = [[], []]
        self.assertIsNone(task._challenge_button(wide=True))


class TestFallbackDirectStart(unittest.TestCase):
    """v1.5.19: 难度+无尽特征 OCR 全失败时, 有开始按钮就直接开始(实测 18:28
    无尽详情页读不到任何特征, 旧逻辑误点 X 退出页面)。"""

    def test_fallback_starts_with_button(self):
        task = make_rahai()
        task._event_title = lambda: [box('拉海洛方块·逆转')]
        task._ocr_results = [
            [],  # narrow 困难
            [],  # narrow 简单
            [],  # wide 困难
            [],  # wide 简单
            [],  # _endless_page 三个区域都读不到
            [], [],
            [box('开始挑战', y=1010)],  # _challenge_button narrow
        ]
        started = []
        task._start_and_play = lambda interaction, difficulty, label, check_objective=True: \
            started.append((difficulty, check_objective))
        task._challenge_current_details(object())
        self.assertEqual(len(started), 1, '有开始按钮必须兜底直启')
        self.assertEqual(started[0][0], '未知')
        self.assertFalse(started[0][1], '兜底直启必须跳过积分/奖章目标检查')

    def test_no_button_still_raises(self):
        task = make_rahai()
        task._event_title = lambda: []
        task._ocr_results = [[], [], [], [], [], [], [], []]
        with self.assertRaises(ChallengeFailed):
            task._challenge_current_details(object())


class TestStartAndPlayEndlessRedirect(unittest.TestCase):
    """v1.5.19: 兜底直启点开始后实际进入无尽模式 -> 自动转无尽流程。"""

    def test_redirect_to_endless(self):
        task = make_rahai()
        task._event_title = lambda: [box('拉海洛方块·逆转')]
        # _start_and_play 内部: 积分检查跳过(check_objective=False)
        buttons = [box('开始挑战', y=1010), None]  # 点击后按钮消失
        task._challenge_button = lambda wide=False: buttons.pop(0)
        task._endless_page = lambda: False
        task._endless_ingame = lambda: True  # 点开始后检测到无尽局内特征
        played = []
        task._play_endless_round = lambda interaction: played.append(True)
        task.next_frame = lambda: None
        task._start_and_play(object(), '未知', '兜底', check_objective=False)
        self.assertEqual(played, [True], '进入无尽特征界面必须转 _play_endless_round')

    def test_normal_board_still_works(self):
        task = make_rahai()
        task._event_title = lambda: []
        buttons = [box('开始挑战', y=1010), None]
        task._challenge_button = lambda wide=False: buttons.pop(0)
        task._endless_page = lambda: False
        task._endless_ingame = lambda: False
        played = []
        task._play_board = lambda interaction, **kw: played.append(('normal', kw))
        task._ready_board = lambda: [box('board')]
        task._stage_details = lambda: [box('关卡目标')]  # 普通尾部: 领奖后回到详情页
        task.next_frame = lambda: None
        task._clickable = lambda interaction: True
        task._start_and_play(object(), '困难', '测试', check_objective=False)
        self.assertEqual(played, [('normal', {})], '普通关卡必须走普通棋盘流程')


class TestRunInLoopTimeout(unittest.TestCase):
    """v1.5.19: run_in_loop 超时保护 —— 云游戏浏览器卡顿时 CDP 调用不再永久阻塞。"""

    def _make_capture(self):
        import asyncio
        import threading
        from ok.device.capture_methods.browser import BrowserCaptureMethod
        cap = BrowserCaptureMethod.__new__(BrowserCaptureMethod)
        cap.loop = asyncio.new_event_loop()
        t = threading.Thread(target=cap.loop.run_forever, daemon=True)
        t.start()
        return cap

    def test_normal_call_returns(self):
        import asyncio
        cap = self._make_capture()

        async def ok_coro():
            await asyncio.sleep(0.01)
            return 42

        self.assertEqual(cap.run_in_loop(ok_coro(), timeout=2), 42)
        cap.loop.call_soon_threadsafe(cap.loop.stop)

    def test_hang_call_times_out(self):
        import asyncio
        cap = self._make_capture()
        started = asyncio.Event()

        async def stuck():
            started.set()
            await asyncio.sleep(60)  # 模拟浏览器假死

        t0 = time.time()
        result = cap.run_in_loop(stuck(), timeout=0.3)
        elapsed = time.time() - t0
        self.assertIsNone(result, '超时必须返回 None 而不是永久阻塞')
        self.assertLess(elapsed, 5, '必须在超时后及时返回')
        cap.loop.call_soon_threadsafe(cap.loop.stop)

    def test_exception_logged_not_raised(self):
        import asyncio
        cap = self._make_capture()

        async def boom():
            raise ValueError('boom')

        self.assertIsNone(cap.run_in_loop(boom(), timeout=2))
        cap.loop.call_soon_threadsafe(cap.loop.stop)


class TestChallengeEndless(unittest.TestCase):
    """无尽模式主流程: 详情页开始 / 加入局内 / 目标分退出结算。"""

    def test_start_from_detail_page(self):
        task = make_rahai()
        task._tutorial_confirm = lambda: False
        task._playable_board = lambda: None
        buttons = [box('开始挑战', y=1010), None]  # 点击后按钮消失
        task._challenge_button = lambda wide=False: buttons.pop(0)
        task.next_frame = lambda: None
        task._ready_board = lambda: True
        task._play_board = lambda interaction, endless=False, max_moves=160: 'reward'
        task._challenge_endless(object())
        self.assertTrue(any('开始挑战：无尽模式' in c[1] for c in task.calls if c[0] == 'info'))

    def test_join_running_game(self):
        task = make_rahai()
        task._tutorial_confirm = lambda: False
        task._playable_board = lambda: object()
        task._play_board = lambda interaction, endless=False, max_moves=160: 'dead'
        task._challenge_endless(object())
        self.assertTrue(any('直接加入' in c[1] for c in task.calls if c[0] == 'info'))

    def test_goal_triggers_settle(self):
        task = make_rahai()
        task._tutorial_confirm = lambda: False
        task._playable_board = lambda: object()
        task._play_board = lambda interaction, endless=False, max_moves=160: 'goal'
        settled = []
        task._endless_exit_and_settle = lambda: settled.append(True)
        task._challenge_endless(object())
        self.assertEqual(settled, [True], '达到目标分后必须退出结算')

    def test_no_start_button_raises(self):
        task = make_rahai()
        task._tutorial_confirm = lambda: False
        task._playable_board = lambda: None
        task._challenge_button = lambda wide=False: None
        with self.assertRaises(ChallengeFailed):
            task._challenge_endless(object())


class TestPlayBoardEndless(unittest.TestCase):
    """_play_board 无尽模式: 无合法落点视为本局结束而不是报错。"""

    def test_dead_returns_not_raises(self):
        import src.task.RahaiBlocksTask as mod
        task = make_rahai()
        task.next_frame = lambda: None
        task._clickable = lambda interaction: True
        task._playable_board = lambda: SimpleNamespace(
            pieces=[], mask=0, fixed=0, fault=0)
        with patch.object(mod, 'choose_move', return_value=None):
            reason = task._play_board(object(), endless=True, max_moves=5)
        self.assertEqual(reason, 'dead')

    def test_normal_mode_still_raises(self):
        import src.task.RahaiBlocksTask as mod
        task = make_rahai()
        task.next_frame = lambda: None
        task._clickable = lambda interaction: True
        task._playable_board = lambda: SimpleNamespace(
            pieces=[], mask=0, fixed=0, fault=0)
        with patch.object(mod, 'choose_move', return_value=None):
            with self.assertRaises(ChallengeFailed):
                task._play_board(object(), endless=False, max_moves=5)


class TestEndlessExitSettle(unittest.TestCase):
    """达到目标分后退出结算: 点 X -> 确认/离开 -> 奖励。"""

    def test_clicks_leave_then_reward(self):
        task = make_rahai()
        task._ocr_results = [
            [],                    # 离开 按钮第一查(wait_until 直接调 func)
            [box('离开', y=700)],   # wait_until 队列返回
        ]
        task._wait_queue = [box('离开', y=700)]  # wait_until 直接给返回值
        task._reward = lambda: [box('获得')]
        task._endless_exit_and_settle()
        clicks = [c for c in task.calls if c[0] == 'click']
        self.assertGreaterEqual(len(clicks), 2, '至少点了退出按钮和奖励')


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
