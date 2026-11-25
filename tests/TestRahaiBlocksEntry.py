# -*- coding: utf-8 -*-
"""v1.5.16: 拉海洛方块支持在关卡详情页直接开始。

此前任务启动时必须停在"活动关卡列表"页, 否则报 FatalTaskError。
现在: 若玩家已打开某个关卡详情页, 直接开始当前选中的难度,
打完后回列表继续扫描其余关卡。
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

from src.task.RahaiBlocksTask import ChallengeFailed, RahaiBlocksTask  # noqa: E402


def make_task(queue=None, **attrs):
    """构造绕过 BaseTask.__init__ 的 RahaiBlocksTask 实例。"""
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
        boxes = task._ocr_results.pop(0) if task._ocr_results else []
        if match and boxes:
            boxes = [b for b in boxes if getattr(match, 'search', None) and match.search(b.name)]
        return boxes

    task.wait_until = wait_until
    task.ocr = ocr
    task._ocr_results = []
    task.is_browser = lambda: True
    task._make_interaction = lambda: object()
    task._clickable = lambda interaction: True
    task.next_frame = lambda: None
    task.log_info = lambda msg, **kw: task.calls.append(('info', msg))
    task.log_warning = lambda msg, **kw: task.calls.append(('warning', msg))
    for key, value in attrs.items():
        setattr(task, key, value)
    return task


class TestEntryRouting(unittest.TestCase):
    """_run_task 入口路由: 列表页 / 关卡详情页 / 都不在。"""

    def _run(self, task):
        with patch('src.task.RahaiBlocksTask.canonical_frame', return_value=object()), \
                patch.object(RahaiBlocksTask, 'frame', new_callable=PropertyMock) as frame_mock:
            frame_mock.return_value = object()
            return task._run_task()

    def test_starts_directly_on_details_page(self):
        """列表页不在 + 详情页在: 直接开始当前难度, 然后回列表继续扫描。"""
        detail = SimpleNamespace(name='关卡目标')
        stages = [(SimpleNamespace(name='关卡一', x=100, y=200),
                   SimpleNamespace(name='进行中 2/2', x=100, y=280))]
        direct = []
        task = make_task(queue=[None, detail],
                         _challenge_current_details=lambda interaction: direct.append(interaction),
                         _return_to_list=lambda: stages,
                         _first_page=lambda interaction, stages: stages,
                         _scroll_stages=lambda interaction, direction, stages: (stages, False))
        self._run(task)
        self.assertEqual(len(direct), 1, '必须调用关卡详情页直启')
        self.assertTrue(any(c[0] == 'info' and '直接开始' in c[1] for c in task.calls),
                        '必须记录"直接开始"日志')

    def test_fatal_when_neither_list_nor_details(self):
        """列表页和详情页都不在: 保持原有 FatalTaskError, 但提示两种入口。"""
        task = make_task(queue=[None, None])
        with self.assertRaises(Exception) as ctx:
            self._run(task)
        self.assertIn('关卡', str(ctx.exception))

    def test_list_page_entry_unchanged(self):
        """列表页在: 不触发直启, 走原有扫描流程。"""
        stages = [(SimpleNamespace(name='关卡一', x=100, y=200),
                   SimpleNamespace(name='进行中 2/2', x=100, y=280))]
        direct = []
        task = make_task(queue=[stages],
                         _challenge_current_details=lambda interaction: direct.append(interaction),
                         _first_page=lambda interaction, stages: stages,
                         _scroll_stages=lambda interaction, direction, stages: (stages, False))
        self._run(task)
        self.assertEqual(direct, [], '列表页入口不得触发直启')


class TestChallengeCurrentDetails(unittest.TestCase):
    """_challenge_current_details: 识别当前选中难度并开始。"""

    def test_uses_selected_difficulty(self):
        task = make_task()
        started = []
        task._start_and_play = lambda interaction, difficulty, label: started.append(
            (difficulty, label))
        # OCR: 第一步识别难度(困难命中), 第二步由 _start_and_play 内部处理
        task._ocr_results = [[SimpleNamespace(name='困难')]]
        task._challenge_current_details(object())
        self.assertEqual(started[0][0], '困难')
        self.assertIn('关卡页面直接开始', started[0][1])

    def test_falls_back_to_easy(self):
        task = make_task()
        started = []
        task._start_and_play = lambda interaction, difficulty, label: started.append(difficulty)
        easy = SimpleNamespace(name='简单')
        task._ocr_results = [[easy], [easy]]  # 先被"困难"匹配过滤, 再命中"简单"
        task._challenge_current_details(object())
        self.assertEqual(started[0], '简单')

    def test_raises_without_difficulty(self):
        task = make_task()
        task._ocr_results = [[]]
        with self.assertRaises(ChallengeFailed):
            task._challenge_current_details(object())


class TestStartAndPlay(unittest.TestCase):
    """_start_and_play: 从详情页点开始到领奖励的公共流程。"""

    def test_full_flow(self):
        task = make_task(queue=[True, True])  # _ready_board, _stage_details
        clicks = []
        task.click = lambda *args, **kwargs: clicks.append(args)
        button_state = {'count': 0}

        def challenge_button(wide=False):
            button_state['count'] += 1
            if button_state['count'] <= 1:
                return [SimpleNamespace(name='开始挑战', x=1700, y=1010)]
            return []  # 点击后按钮消失 = 成功进入战斗

        task._challenge_button = challenge_button
        task._play_board = lambda interaction: task.calls.append(('played',))
        with patch('src.task.RahaiBlocksTask.canonical_frame', return_value=object()):
            task._ocr_results = [[SimpleNamespace(name='积分挑战')],  # 关卡目标(积分|奖章)
                                 [],                                  # 点击后按钮消失(成功进入)
                                 ]
            task._start_and_play(object(), '困难', '测试关卡 · 困难')
        self.assertTrue(any(c[0] == 'played' for c in task.calls), '必须执行下棋流程')
        self.assertTrue(any(c[0] == 'info' and '开始挑战：测试关卡' in c[1] for c in task.calls))

    def test_raises_when_goal_not_recognized(self):
        task = make_task()
        task._ocr_results = [[]]  # 关卡目标识别失败
        clicks = []
        task.click = lambda *args, **kwargs: clicks.append(args)
        with self.assertRaises(ChallengeFailed):
            task._start_and_play(object(), '简单', '测试 · 简单')
        self.assertEqual(clicks, [], '识别不到关卡目标时不得点击开始')

    def test_raises_when_start_button_missing(self):
        task = make_task()
        task._ocr_results = [[SimpleNamespace(name='关卡目标')]]
        task._challenge_button = lambda wide=False: None
        with self.assertRaises(ChallengeFailed):
            task._start_and_play(object(), '简单', '测试 · 简单')


if __name__ == '__main__':
    unittest.main(verbosity=2)
