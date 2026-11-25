"""拉海洛方块走棋搜索的性能回归测试.

官方 v3.8.15 的 choose_move 只在「托盘 3 块」时裁剪中间状态, 而新关卡/无尽模式
是 4 块托盘: 状态数不设上限 -> 单次搜索要评估上千万次盘面, 纯 CPU 卡死数分钟
(2026-11-25 18:57 / 19:02 两次卡死, 关机线程转储定格在 board_value)。
这组测试保证: 4 块托盘也能在秒级返回, 且墙钟预算耗尽时立刻用已找到的最优解。
"""

import os
import sys
import time
import unittest

WORK = r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working"
os.chdir(WORK)
sys.path.insert(0, WORK)

from src.task import rahai_blocks  # noqa: E402
from src.task.rahai_blocks import Board, choose_move  # noqa: E402

TRAY_4 = (
    ((0, 0), (0, 1), (0, 2), (0, 3)),   # I4
    ((0, 0), (1, 0), (2, 0), (2, 1)),   # L
    ((0, 0), (1, 0), (0, 1), (1, 1)),   # O
    ((0, 0), (0, 1), (0, 2)),           # I3
)


def make_pieces(shapes):
    pieces = []
    for slot, cells in enumerate(shapes):
        piece = type('P', (), {'slot': slot, 'cells': cells, 'pickup': (0, 0)})
        pieces.append(piece)
    return tuple(pieces)


class RahaiSearchBudgetTest(unittest.TestCase):

    def test_four_tray_search_finishes_quickly(self):
        board = Board(0, make_pieces(TRAY_4))
        start = time.monotonic()
        move = choose_move(board)
        elapsed = time.monotonic() - start
        self.assertIsNotNone(move, '4 块托盘必须能找到落点')
        self.assertLess(elapsed, 5.0, f'choose_move 耗时 {elapsed:.1f}s, 组合爆炸回归')

    def test_four_tray_on_crowded_board(self):
        # 盘面越满, 合法落点越少但中间状态越多, 是爆炸最容易出现的场景。
        mask = 0
        for row in range(0, 8):
            for col in range(0, 8):
                if (row + col) % 3 == 0:
                    mask |= 1 << (row * 8 + col)
        board = Board(mask, make_pieces(TRAY_4))
        start = time.monotonic()
        choose_move(board)
        self.assertLess(time.monotonic() - start, 5.0)

    def test_time_budget_returns_best_so_far(self):
        saved = rahai_blocks.CHOOSE_MOVE_TIME_BUDGET
        rahai_blocks.CHOOSE_MOVE_TIME_BUDGET = 1e-9
        try:
            board = Board(0, make_pieces(TRAY_4))
            start = time.monotonic()
            move = choose_move(board)
            self.assertLess(time.monotonic() - start, 2.0, '墙钟兜底失效')
            self.assertIsNotNone(move, '预算耗尽也应返回已找到的最优解')
        finally:
            rahai_blocks.CHOOSE_MOVE_TIME_BUDGET = saved

    def test_three_tray_still_works(self):
        board = Board(0, make_pieces(TRAY_4[:3]))
        self.assertIsNotNone(choose_move(board))


if __name__ == '__main__':
    unittest.main(verbosity=2)
