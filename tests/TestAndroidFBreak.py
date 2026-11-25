"""MuMu/安卓端谐振破坏修复测试 (v1.5.9).

根因: PC 的 f_break 模板是 "F" 键帽图标 (36x43, 取自 3840x2160 PC 截图),
手游端谐振破坏提示是触摸图标+文字, 模板永远匹配不上 -> check_f_break()
恒 False -> f_break() 从不触发, MuMu 无法谐振破坏。

修复 (src/combat/CombatCheck.py):
- check_f_break(): 安卓端走 _android_check_f_break():
    1) f_break_full 谐振条图标模板 (跨端美术一致), 阈值放宽 0.92 -> 0.85;
    2) OCR 在屏幕中央区域找 "破坏/谐振" 提示文字, 记录位置到 _f_break_box。
- f_break(): 安卓端直接点击识别到的提示位置 (图标/文字), 不再按 F 键;
  PC/云游戏仍 send_key('f') + click。
"""
import inspect
import os
import sys
import unittest

WORK = r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working"
os.chdir(WORK)
sys.path.insert(0, WORK)

from ok import Box

from src.combat.CombatCheck import (
    ANDROID_BREAK_OCR_RE,
    CombatCheck,
)


class QuietLogger:
    def debug(self, *a, **kw):
        pass

    def info(self, *a, **kw):
        pass


class BreakDouble:
    """只提供 check_f_break/_android_check_f_break/f_break 需要的最小桩。"""

    def __init__(self, adb=True, found=None, ocr_matches=None, in_liberation=False):
        self._adb = adb
        self.found = found
        self.ocr_matches = ocr_matches
        self._in_liberation = in_liberation
        self.can_break = False
        self.last_break_check_time = 0
        self._f_break_box = None
        self.logger = QuietLogger()
        self.find_calls = []
        self.ocr_calls = []
        self.clicks = []
        self.keys = []

    def is_adb(self):
        return self._adb

    def check_f_break(self):
        return CombatCheck.check_f_break(self)

    def _android_check_f_break(self):
        return CombatCheck._android_check_f_break(self)

    def find_one(self, *a, **kw):
        self.find_calls.append((a, kw))
        return self.found

    def ocr(self, box=None, match=None, **kw):
        self.ocr_calls.append((box, match))
        return self.ocr_matches

    def box_of_screen(self, *a, **kw):
        return Box(300, 200, 900, 600)

    def click(self, *a, **kw):
        self.clicks.append((a, kw))
        return True

    def send_key(self, *a, **kw):
        self.keys.append((a, kw))


class TestAndroidCheckFBreak(unittest.TestCase):
    def test_full_template_hit_sets_box(self):
        box = Box(800, 500, 40, 50)
        fake = BreakDouble(adb=True, found=box)
        self.assertTrue(CombatCheck.check_f_break(fake))
        self.assertTrue(fake.can_break)
        self.assertIs(fake._f_break_box, box)
        self.assertEqual(fake.ocr_calls, [], '模板命中时不应做 OCR')

    def test_full_template_threshold_relaxed_for_android(self):
        fake = BreakDouble(adb=True, found=None)
        CombatCheck.check_f_break(fake)
        # f_break_full 查询用了放宽后的阈值 (0.85 而不是 PC 的 0.92)
        full_calls = [kw for a, kw in fake.find_calls if a and a[0] is not None and 'full' in str(a[0])]
        self.assertTrue(full_calls, '安卓端必须先查 f_break_full')
        self.assertTrue(any(kw.get('threshold', 0) <= 0.9 for kw in full_calls))

    def test_liberation_blocks_ocr_fallback(self):
        fake = BreakDouble(adb=True, found=None, in_liberation=True)
        self.assertFalse(CombatCheck.check_f_break(fake))
        self.assertEqual(fake.ocr_calls, [])

    def test_ocr_throttled_to_one_per_second(self):
        fake = BreakDouble(adb=True, found=None)
        fake.last_break_check_time = __import__('time').time()  # 刚查过
        self.assertFalse(CombatCheck.check_f_break(fake))
        self.assertEqual(fake.ocr_calls, [], '1 秒内不得重复 OCR')

    def test_ocr_fallback_finds_break_text(self):
        text_box = Box(900, 600, 200, 40)
        fake = BreakDouble(adb=True, found=None, ocr_matches=[text_box])
        self.assertTrue(CombatCheck.check_f_break(fake))
        self.assertTrue(fake.can_break)
        self.assertIs(fake._f_break_box, text_box)
        self.assertEqual(len(fake.ocr_calls), 1)
        # OCR 区域在屏幕中央
        area = fake.ocr_calls[0][0]
        self.assertIsInstance(area, Box)

    def test_ocr_miss_clears_box(self):
        fake = BreakDouble(adb=True, found=None, ocr_matches=[])
        self.assertFalse(CombatCheck.check_f_break(fake))
        self.assertIsNone(fake._f_break_box)
        self.assertFalse(fake.can_break)

    def test_ocr_regex_matches_prompt_text(self):
        self.assertTrue(ANDROID_BREAK_OCR_RE.search('谐振破坏'))
        self.assertTrue(ANDROID_BREAK_OCR_RE.search('破坏'))
        self.assertFalse(ANDROID_BREAK_OCR_RE.search('拾取'))
        self.assertFalse(ANDROID_BREAK_OCR_RE.search('普通攻击'))


class TestFBreakAction(unittest.TestCase):
    def test_adb_clicks_detected_position_no_f_key(self):
        box = Box(900, 600, 200, 40)
        fake = BreakDouble(adb=True)
        fake.can_break = True
        fake._f_break_box = box
        CombatCheck.f_break(fake)
        self.assertTrue(fake.clicks, '安卓端必须点击识别到的提示位置')
        first = fake.clicks[0][0]
        self.assertEqual(first[0], 1000, '必须点击 box 中心 x')
        self.assertEqual(first[1], 620, '必须点击 box 中心 y')
        self.assertEqual(fake.keys, [], '识别到位置时不得按 F 键')

    def test_adb_fallback_without_box_still_tries(self):
        fake = BreakDouble(adb=True)
        fake.can_break = True
        fake._f_break_box = None
        CombatCheck.f_break(fake)
        self.assertTrue(fake.clicks, '无坐标时也要普攻尝试')
        self.assertTrue(fake.keys, '无坐标时回退按 F')

    def test_pc_path_unchanged(self):
        fake = BreakDouble(adb=False)
        fake.can_break = True
        CombatCheck.f_break(fake)
        self.assertEqual(fake.keys[0][0], ('f',), 'PC 端仍按 F 键')
        self.assertEqual(fake.clicks[0][0], (), 'PC 端仍无坐标普攻')


class TestSourceContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.check_src = inspect.getsource(CombatCheck.check_f_break)
        cls.android_src = inspect.getsource(CombatCheck._android_check_f_break)
        cls.fbreak_src = inspect.getsource(CombatCheck.f_break)

    def test_check_dispatches_on_adb(self):
        self.assertIn('if self.is_adb():', self.check_src)
        self.assertIn('_android_check_f_break', self.check_src)

    def test_pc_path_preserved(self):
        self.assertIn('f_break_full', self.check_src)
        self.assertIn('0.92', self.check_src, 'PC 端 f_break_full 阈值保持 0.92')
        self.assertIn('is_pick_f', self.check_src, 'PC 端保留拾取 F 消歧')

    def test_android_uses_template_plus_ocr(self):
        self.assertIn('f_break_full', self.android_src)
        self.assertIn('self.ocr(', self.android_src)
        self.assertIn('_f_break_box', self.android_src)

    def test_f_break_clicks_position_on_adb(self):
        self.assertIn('if self.is_adb():', self.fbreak_src)
        self.assertIn('box.center()', self.fbreak_src)
        self.assertIn('self.click(x, y', self.fbreak_src)

    def test_f_break_pc_branch_kept(self):
        self.assertIn("send_key('f'", self.fbreak_src)


if __name__ == '__main__':
    unittest.main(verbosity=2)
