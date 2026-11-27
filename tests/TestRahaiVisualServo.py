"""拉海洛方块落点预览视觉闭环测试（修复 MuMu 触控坐标偏移）。

MuMu 的触控坐标系不可靠，改为用游戏落点预览做视觉伺服：
1. preview_center 从棋盘帧读出预览占据格子的包围盒中心；
2. _visual_servo 实测「手指像素->预览逻辑位移」雅可比，反推手指该挪多少，
   迭代到 preview_matches，不依赖任何坐标系假设。
"""

import os
import sys
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

import numpy as np

WORK = r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working"
os.chdir(WORK)
sys.path.insert(0, WORK)

from src.task.rahai_blocks import (  # noqa: E402
    BOARD_X, BOARD_Y, CELL, WIDTH, HEIGHT, Board, preview_center,
)
import src.task.RahaiBlocksTask as rahai_task  # noqa: E402


def frame_with_cells(cells):
    """造一张 2048x1152 棋盘帧：只有给定格子中心是亮的。"""
    frame = np.zeros((HEIGHT, WIDTH, 3), dtype=np.uint8)
    for r, c in cells:
        x = round(BOARD_X + (c + .5) * CELL)
        y = round(BOARD_Y + (r + .5) * CELL)
        # _board_masks 采样格子四角偏移 (±24,±25)，要求 chroma>40；
        # 画满整格并填高饱和洋红（B/R 高、G 低），保证四角采样都命中。
        half = round(CELL / 2)
        frame[y-half:y+half, x-half:x+half] = (200, 30, 220)
    return frame


class PreviewCenterTest(unittest.TestCase):
    def test_no_preview_returns_none(self):
        board = Board(mask=0, pieces=())
        self.assertIsNone(preview_center(frame_with_cells([]), board))

    def test_single_cell_center(self):
        board = Board(mask=0, pieces=())
        c = preview_center(frame_with_cells([(2, 3)]), board)
        expected = (BOARD_X + 3.5 * CELL, BOARD_Y + 2.5 * CELL)
        self.assertAlmostEqual(c[0], expected[0], delta=2)
        self.assertAlmostEqual(c[1], expected[1], delta=2)

    def test_l_shape_uses_bounding_box_center(self):
        # L 形三格，包围盒中心 != 格子均值；必须和 Move.drop 一致。
        board = Board(mask=0, pieces=())
        c = preview_center(frame_with_cells([(1, 1), (2, 1), (2, 2)]), board)
        self.assertAlmostEqual(c[0], BOARD_X + 2 * CELL, delta=2)
        self.assertAlmostEqual(c[1], BOARD_Y + 2 * CELL, delta=2)

    def test_excludes_cells_already_on_board(self):
        board = Board(mask=1, pieces=())
        c = preview_center(frame_with_cells([(0, 0), (3, 3)]), board)
        expected = (BOARD_X + 3.5 * CELL, BOARD_Y + 3.5 * CELL)
        self.assertAlmostEqual(c[0], expected[0], delta=2)
        self.assertAlmostEqual(c[1], expected[1], delta=2)


class VisualServoTest(unittest.TestCase):
    """实测雅可比 + 迭代修正，命中即返回 True；不依赖坐标系假设。"""

    def make_task(self):
        task = object.__new__(rahai_task.RahaiBlocksTask)
        task.sleep = Mock()
        task.next_frame = Mock(return_value=object())
        task._clickable = Mock(return_value=True)
        return task

    def simulate(self, target, scale=(2, 3), mirrored=(False, False), max_steps=12):
        """模拟一个任意线性坐标系：预览 = 基准 + 手指位移*比例（可镜像）。

        伺服应实测出这个比例并收敛，证明它不依赖「坐标系=截图坐标」的假设。
        """
        base = (100.0, 100.0)
        state = {'fx': 0, 'fy': 0}

        def preview(_frame, _board):
            sx = -1 if mirrored[0] else 1
            sy = -1 if mirrored[1] else 1
            return (base[0] + state['fx'] * scale[0] * sx,
                    base[1] + state['fy'] * scale[1] * sy)

        def matched(frame, board, move):
            c = preview(frame, board)
            return abs(c[0] - target[0]) < 3 and abs(c[1] - target[1]) < 3

        interaction = Mock()
        interaction.move.side_effect = lambda x, y: state.__setitem__('fx', x) or state.__setitem__('fy', y)
        task = self.make_task()

        with patch.object(rahai_task, 'preview_center', side_effect=preview), \
             patch.object(rahai_task, 'preview_matches', side_effect=matched), \
             patch.object(rahai_task, 'canonical_frame', side_effect=lambda f: f):
            result = task._visual_servo(
                interaction=interaction, board=Board(mask=0, pieces=()), move=None,
                point=lambda xy: (0, 0), target=target, max_steps=max_steps)
        return result, state

    def test_converges_with_anisotropic_scale(self):
        ok, state = self.simulate(target=(180, 220), scale=(2, 3))
        self.assertTrue(ok)
        self.assertAlmostEqual(state['fx'], 40, delta=6)
        self.assertAlmostEqual(state['fy'], 40, delta=6)

    def test_converges_with_mirrored_axes(self):
        # x 镜像 + y 镜像：手指右移预览左移，伺服实测负雅可比照样收敛。
        ok, state = self.simulate(target=(60, 40), scale=(2, 3), mirrored=(True, True))
        self.assertTrue(ok)
        self.assertAlmostEqual(state['fx'], 20, delta=6)
        self.assertAlmostEqual(state['fy'], 20, delta=6)

    def test_no_preview_returns_false(self):
        task = self.make_task()
        interaction = Mock()
        with patch.object(rahai_task, 'preview_center', return_value=None), \
             patch.object(rahai_task, 'preview_matches', return_value=False), \
             patch.object(rahai_task, 'canonical_frame', side_effect=lambda f: f):
            result = task._visual_servo(
                interaction=interaction, board=Board(mask=0, pieces=()), move=None,
                point=lambda xy: (100, 100), target=(200, 200), max_steps=5)
        self.assertFalse(result)


if __name__ == '__main__':
    unittest.main()
