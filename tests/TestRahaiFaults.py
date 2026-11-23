"""Fault-block (故障方块) vision and simulation tests for rahai_blocks."""
import random
import sys

import numpy as np

sys.path.insert(0, r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working")

from src.task.rahai_blocks import (BOARD_X, BOARD_Y, CELL, COLS, ROWS, SIZE,
                                   Board, _fault_mask, clear_lines, choose_move)


def cell_center(row, col):
    return round(BOARD_Y + (row + .5) * CELL), round(BOARD_X + (col + .5) * CELL)


def make_frame():
    return np.zeros((1152, 2048, 3), dtype=np.uint8)


def paint_glitch(frame, row, col, rng):
    cy, cx = cell_center(row, col)
    half = 55
    tile = frame[cy - half:cy + half, cx - half:cx + half]
    # magenta noise: B/R bright with big spread, G much lower
    tile[:, :, 0] = rng.integers(200, 256, tile.shape[:2])
    tile[:, :, 1] = rng.integers(40, 170, tile.shape[:2])
    tile[:, :, 2] = rng.integers(170, 256, tile.shape[:2])


def paint_flat(frame, row, col, bgr):
    cy, cx = cell_center(row, col)
    half = 55
    frame[cy - half:cy + half, cx - half:cx + half] = bgr


def bit(row, col):
    return 1 << (row * SIZE + col)


def test_fault_vision():
    rng = np.random.default_rng(7)
    frame = make_frame()
    paint_glitch(frame, 2, 3, rng)
    paint_glitch(frame, 5, 6, rng)
    # normal blocks: purple / blue / orange / white-icon-ish
    paint_flat(frame, 2, 4, (171, 51, 109))   # purple (BGR)
    paint_flat(frame, 5, 5, (220, 60, 60))    # blue-ish
    paint_flat(frame, 5, 7, (60, 140, 240))   # orange
    mask = bit(2, 3) | bit(2, 4) | bit(5, 5) | bit(5, 6) | bit(5, 7)
    fault = _fault_mask(frame, mask)
    assert fault == bit(2, 3) | bit(5, 6), hex(fault)
    # empty cells must never be flagged
    assert _fault_mask(frame, FULL := (1 << 64) - 1) & ~(bit(2, 3) | bit(5, 6)) == 0
    print("test_fault_vision OK")


def test_clear_lines_fault_stays():
    full_row = ROWS[1]
    normal = full_row & ~bit(1, 4)
    fault = bit(1, 4)
    after, lines = clear_lines(normal, 0, fault)
    # the faulted cell survives the clear; everything else in the row goes
    assert after == fault, hex(after)
    assert lines == 1
    # corrupted (fixed) and faulted both stay, column clear unaffected
    after2, lines2 = clear_lines((normal & ~COLS[0]) | bit(1, 0), bit(1, 0), fault)
    assert after2 == bit(1, 0) | fault, hex(after2)
    assert lines2 == 1
    print("test_clear_lines_fault_stays OK")


def test_clear_lines_fault_decrement_observed_by_reread():
    # after the fault is consumed, the block reads as a normal occupied cell
    fault = bit(3, 3)
    after, lines = clear_lines(ROWS[3] ^ 0, 0, fault)
    assert after & fault and lines == 1
    print("test_clear_lines_fault_decrement OK")


def test_choose_move_with_fault():
    fault = bit(0, 0) | bit(0, 1)
    # row 0 nearly full except two cells; place an I-piece to finish the line
    mask = ROWS[0] ^ fault
    pieces = (type("P", (), {"slot": 0, "cells": ((0, 0), (0, 1), (0, 2), (0, 3)), "pickup": (0, 0)}),)
    board = Board(mask=mask, pieces=pieces, fixed=0, fault=fault)
    move = choose_move(board)
    assert move is not None
    after, lines = clear_lines(board.mask | move.mask, board.fixed, board.fault)
    assert lines >= 1
    # faulted cells must survive the simulated clear
    assert after & fault == fault
    print("test_choose_move_with_fault OK")


if __name__ == "__main__":
    test_fault_vision()
    test_clear_lines_fault_stays()
    test_clear_lines_fault_decrement_observed_by_reread()
    test_choose_move_with_fault()
    print("ALL RAHAI FAULT TESTS PASSED")
