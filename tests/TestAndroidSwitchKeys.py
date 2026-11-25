"""MuMu 切人键位修复测试 (v1.5.11).

用户反馈: MuMu 键位映射里只有 1 和 2 两颗切换键。此前实现有两个缺陷:
  1) OCR 读不到"切换角色N"提示时兜底映射是 {0:'1', 1:'2', 2:'3'},
     android_switch_key 还会回退 str(index+1) —— 都会发 3 键,
     模拟器上没绑定, 发了等于没按, 切 3 号位永远失败。
  2) 发键后盲目把逻辑下标推进到目标值, 不核实画面: 按错键时脚本以为
     切成了, 实际还在原角色上, 战斗逻辑全部失配。

修复后:
  - 键->角色映射随出战角色动态推导, 任何情况都不发 3 键;
  - android_confirm_switch() 用编队徽章核实实际出战角色;
  - switch_next_char 安卓分支按错键时自动换另一颗键重试。
"""
import os
import sys
import unittest
from types import SimpleNamespace

WORK = r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working"
os.chdir(WORK)
sys.path.insert(0, WORK)

from src.task.BaseWWTask import (  # noqa: E402
    BaseWWTask, ANDROID_PARTY_BADGE_RE, ANDROID_SWITCH_LABEL_RE, ANDROID_SWITCH_KEYS,
)
from src.task import android_world  # noqa: E402


OcrBox = lambda name, y: SimpleNamespace(name=name, y=y, height=30, x=1700, width=40)


class SwitchTask(BaseWWTask):
    @property
    def width(self):
        return 1920

    @property
    def height(self):
        return 1080

    def __init__(self, badges=(), labels=(), adb=True, current_index=0):
        self._adb = adb
        self._badges = badges
        self._labels = labels
        self._android_current_index = current_index
        self._android_party_scan_ready = False
        self.logged_in = False
        self.logs = []
        self._executor = SimpleNamespace(nullable_frame=lambda: object())

    @property
    def logged_in(self):
        return self._logged_in

    @logged_in.setter
    def logged_in(self, value):
        self._logged_in = value

    def is_adb(self):
        return self._adb

    def is_browser(self):
        return False

    def log_debug(self, msg):
        self.logs.append(('debug', msg))

    def log_warning(self, msg):
        self.logs.append(('warning', msg))

    def tr(self, text):
        return text

    def box_of_screen(self, *args, **kwargs):
        return SimpleNamespace(x=0, y=0, width=1920, height=1080)

    def ocr(self, box=None, match=None, **kwargs):
        if match is ANDROID_PARTY_BADGE_RE or match == ANDROID_PARTY_BADGE_RE:
            return [OcrBox(name, y) for name, y in self._badges]
        if match is ANDROID_SWITCH_LABEL_RE or match == ANDROID_SWITCH_LABEL_RE:
            return [OcrBox(name, y) for name, y in self._labels]
        return []


class TestNeverSendKey3(unittest.TestCase):
    """MuMu 只有 1/2 两颗切换键, 任何 (当前角色, 目标角色) 组合都不能发 3。"""

    def test_no_labels_fallback_never_3(self):
        for current in range(3):
            for target in range(3):
                if target == current:
                    continue
                fake = SwitchTask(current_index=current)
                key = BaseWWTask.android_switch_key(fake, target)
                self.assertIn(key, ANDROID_SWITCH_KEYS,
                              f'current={current + 1}, target={target + 1} 发了 {key} 键')

    def test_fallback_matches_measured_rule(self):
        # 实测规律: 出战 3 号位时键 1 切 2 号位(编队靠后的队友)。
        fake = SwitchTask(current_index=2)
        self.assertEqual(BaseWWTask.android_switch_key(fake, 1), '1')
        self.assertEqual(BaseWWTask.android_switch_key(fake, 0), '2')

    def test_exclude_alternates_to_the_other_key(self):
        fake = SwitchTask(current_index=2)
        self.assertEqual(BaseWWTask.android_switch_key(fake, 0, exclude=('2',)), '1')
        self.assertEqual(BaseWWTask.android_switch_key(fake, 0, exclude=('2', '1')), '2',
                         '两颗都试过时仍要有确定返回值, 不能崩')

    def test_derive_from_confirmed_teammate_key(self):
        # 当前 1 号位, 键位提示只确认了 2 号位用 1 键 -> 3 号位必然是 2 键。
        fake = SwitchTask(current_index=0, labels=[('切换角色1', 255)])
        fake._badges = [('2', 220), ('3', 320)]
        self.assertEqual(BaseWWTask.android_switch_key(fake, 2), '2')

    def test_pc_path_unchanged(self):
        fake = SwitchTask(adb=False, current_index=0)
        self.assertEqual(BaseWWTask.android_switch_key(fake, 2), '3', 'PC/云仍用 index+1 约定')


class TestConfirmSwitch(unittest.TestCase):
    def test_two_badges_confirm_current_char(self):
        fake = SwitchTask(current_index=0, badges=[('1', 220), ('2', 320)])
        confirmed = BaseWWTask.android_confirm_switch(fake, 2)
        self.assertEqual(confirmed, 2, '缺 3 号徽章说明当前是 3 号位')
        self.assertEqual(fake._android_current_index, 2, '核实结果必须写回逻辑下标')

    def test_ocr_failure_returns_none_and_keeps_index(self):
        fake = SwitchTask(current_index=1, badges=[])
        fake._android_party_scan_ready = True
        confirmed = BaseWWTask.android_confirm_switch(fake, 0)
        self.assertIsNone(confirmed, '徽章读不到时返回 None, 由调用方乐观推进')
        self.assertEqual(fake._android_current_index, 1, '读不到时不能乱改逻辑下标')

    def test_force_bypasses_cache(self):
        fake = SwitchTask(current_index=0, badges=[('1', 220), ('2', 320)])
        # 伪造一份"永不过期"的陈旧缓存(空徽章), force=True 必须跳过它重新 OCR。
        fake._android_party_scan_ready = True
        fake._android_party_scan_at = float('inf')
        fake._android_party_badges = set()
        confirmed = BaseWWTask.android_confirm_switch(fake, 0)
        self.assertEqual(confirmed, 2, 'force=True 必须跳过缓存重新 OCR')
        self.assertEqual(fake._android_current_index, 2)

    def test_pc_returns_none(self):
        fake = SwitchTask(adb=False, current_index=0)
        self.assertIsNone(BaseWWTask.android_confirm_switch(fake, 1))


class TestSwitchLoopSources(unittest.TestCase):
    import inspect
    repo = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

    def test_switch_next_char_verifies_after_press(self):
        src = open(os.path.join(self.repo, 'src/task/BaseCombatTask.py'), encoding='utf-8').read()
        self.assertIn('self.android_confirm_switch(switch_to.index)', src,
                      '发键后必须用编队徽章核实')
        self.assertIn('tried_keys', src, '按错键要换另一颗键重试')

    def test_no_default_key3_map(self):
        src = open(os.path.join(self.repo, 'src/task/BaseWWTask.py'), encoding='utf-8').read()
        self.assertNotIn('ANDROID_DEFAULT_SWITCH_KEYS', src, '含 3 键的默认映射必须移除')
        self.assertIn("ANDROID_SWITCH_KEYS = ('1', '2')", src)

    def test_badge_driven_current_index(self):
        src = open(os.path.join(self.repo, 'src/task/BaseWWTask.py'), encoding='utf-8').read()
        self.assertIn('def android_confirm_switch', src)


if __name__ == '__main__':
    unittest.main(verbosity=2)
