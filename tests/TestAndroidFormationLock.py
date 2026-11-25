"""MuMu 安卓编队锁定测试 (v1.5.13).

问题背景: 手游右上角是圆形头像(直径约 110px@1920), PC 头像模板(约 64px)
固定尺度直接匹配必然弱匹配 —— 实测同一队 2 秒内读出 4 种组合
(漂泊者/渊武/仇远/绯雪乱串), char_type 随之漂移, 切人优先级/奶妈逻辑全废。

v1.5.13 修复分三层:
  1. 全局配置 'MuMu/安卓 Config'->'MuMu 编队' 手填角色名(最高优先级, 零识别);
  2. 队伍栏缩放 0.58 倍到 PC 头像尺度后再模板匹配;
  3. 连续 3 次识别一致才锁定; 锁定后 load_chars 完全跳过模板匹配。

回归覆盖:
  - android_team_size 跟随锁定编队人数。
  - 战斗期间(scene.in_combat)锁定不被复检动摇(编队为准、战斗期不识别)。
  - load_chars_android 按锁定身份构建角色, 不做画面识别。
  - 安卓协奏环检测框对准手游元素图标(v1.5.13 修复 current_con 恒 0)。
"""
import os
import sys
import time
import unittest
from types import SimpleNamespace
from unittest.mock import patch

WORK = r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working"
os.chdir(WORK)
sys.path.insert(0, WORK)

from src.task.BaseWWTask import BaseWWTask  # noqa: E402
from src.task.BaseCombatTask import BaseCombatTask  # noqa: E402
from src.char.CharFactory import build_char_by_canonical, resolve_char_alias  # noqa: E402
from src.Labels import Labels  # noqa: E402

HIYUKI = Labels.char_hiyuki
YUANWU = Labels.char_yuanwu
ROVER = Labels.char_rover


class StubTask(BaseWWTask):
    """最小桩: 不触发 BaseTask.__init__, 手工补齐用到的属性。"""

    def __init__(self, adb=True, chars=(), scene_in_combat=None, config_team=''):
        self._adb = adb
        self.chars = list(chars)
        self.logs = []
        self.android_config = {'MuMu 编队': config_team}
        self._executor = SimpleNamespace(nullable_frame=lambda: None)
        self.scene = SimpleNamespace(in_combat=scene_in_combat)
        self._screen_width = 1920
        self._screen_height = 1080
        self._debug_flag = False

    @property
    def debug(self):
        return self._debug_flag

    @property
    def screen_width(self):
        return self._screen_width

    @property
    def screen_height(self):
        return self._screen_height

    def is_adb(self):
        return self._adb

    def is_browser(self):
        return False

    def log_debug(self, msg):
        self.logs.append(('debug', msg))

    def log_info(self, msg):
        self.logs.append(('info', msg))

    def log_warning(self, msg):
        self.logs.append(('warning', msg))

    def log_error(self, message, exception=None, **kwargs):
        self.logs.append(('error', f'{message}: {exception}'))

    def tr(self, text):
        return text

    def get_box_by_name(self, name):
        return None

    def find_best_match_in_box(self, box, to_find, threshold, **kwargs):
        return None


class TestResolveCharAlias(unittest.TestCase):
    def test_exact_english_class_name(self):
        stub = StubTask()
        self.assertEqual(resolve_char_alias(stub, 'Hiyuki'), HIYUKI)

    def test_chinese_name_via_tr(self):
        stub = StubTask()

        def fake_tr(text):
            return {'Hiyuki': '绯雪', 'Yuanwu': '渊武', 'Rover': '漂泊者'}.get(text, text)

        stub.tr = fake_tr
        self.assertEqual(resolve_char_alias(stub, '绯雪'), HIYUKI)
        self.assertEqual(resolve_char_alias(stub, '渊武'), YUANWU)
        self.assertEqual(resolve_char_alias(stub, '漂泊者'), ROVER)

    def test_unknown_token_returns_none(self):
        stub = StubTask()
        self.assertIsNone(resolve_char_alias(stub, '不存在的角色'))

    def test_empty_token_returns_none(self):
        stub = StubTask()
        self.assertIsNone(resolve_char_alias(stub, ''))
        self.assertIsNone(resolve_char_alias(stub, None))


class TestConfiguredTeam(unittest.TestCase):
    def test_configured_team_parsed_in_order(self):
        stub = StubTask(config_team='Hiyuki, Yuanwu')
        self.assertEqual(BaseWWTask.android_configured_team(stub), (HIYUKI, YUANWU))

    def test_configured_team_three_members(self):
        stub = StubTask(config_team='Hiyuki,Yuanwu,Rover')
        self.assertEqual(len(BaseWWTask.android_configured_team(stub)), 3)

    def test_empty_config_returns_none(self):
        stub = StubTask(config_team='')
        self.assertIsNone(BaseWWTask.android_configured_team(stub))

    def test_unknown_name_rejects_whole_config(self):
        stub = StubTask(config_team='Hiyuki,不存在角色')
        self.assertIsNone(BaseWWTask.android_configured_team(stub), '部分无法识别时整条放弃, 不能半队乱切')

    def test_wrong_member_count_rejected(self):
        stub = StubTask(config_team='Hiyuki')
        self.assertIsNone(BaseWWTask.android_configured_team(stub))


class TestVoteAndLock(unittest.TestCase):
    def test_three_consistent_votes_lock_team(self):
        stub = StubTask()
        identity = (HIYUKI, YUANWU)
        for _ in range(3):
            result = BaseWWTask.android_vote_team_identity(stub, identity)
        self.assertEqual(result, identity)
        self.assertEqual(getattr(stub, '_android_team_lock', None), identity)

    def test_transient_noise_cannot_break_lock(self):
        stub = StubTask()
        identity = (HIYUKI, YUANWU)
        for _ in range(3):
            BaseWWTask.android_vote_team_identity(stub, identity)
        # 战斗特效造成的单帧误读不能撼动锁定
        result = BaseWWTask.android_vote_team_identity(stub, (YUANWU, YUANWU))
        self.assertEqual(result, identity, '偶发误读必须仍返回锁定编队')
        self.assertEqual(BaseWWTask.android_vote_team_identity(stub, None), identity)

    def test_stable_new_team_relocks(self):
        stub = StubTask()
        for _ in range(3):
            BaseWWTask.android_vote_team_identity(stub, (HIYUKI, YUANWU))
        new_team = (ROVER, YUANWU)
        for _ in range(3):
            result = BaseWWTask.android_vote_team_identity(stub, new_team)
        self.assertEqual(result, new_team, '连续一致的换队信号必须重锁')
        self.assertEqual(getattr(stub, '_android_team_lock', None), new_team)

    def test_majority_fallback_before_lock(self):
        stub = StubTask()
        BaseWWTask.android_vote_team_identity(stub, (HIYUKI, YUANWU))
        BaseWWTask.android_vote_team_identity(stub, (HIYUKI, YUANWU))
        BaseWWTask.android_vote_team_identity(stub, (YUANWU, ROVER))
        BaseWWTask.android_vote_team_identity(stub, (HIYUKI, YUANWU))
        result = BaseWWTask.android_vote_team_identity(stub, (ROVER, ROVER))
        self.assertEqual(result, (HIYUKI, YUANWU), '锁定前用多数票兜底')

    def test_team_size_follows_lock(self):
        stub = StubTask()
        for _ in range(3):
            BaseWWTask.android_vote_team_identity(stub, (HIYUKI, YUANWU))
        self.assertEqual(BaseWWTask.android_team_size(stub), 2, '锁定两人队就是两人队')

    def test_team_size_default_three_without_lock(self):
        stub = StubTask()
        self.assertEqual(BaseWWTask.android_team_size(stub), 3)

    def test_recheck_skipped_during_combat(self):
        stub = StubTask(scene_in_combat=True)
        for _ in range(3):
            BaseWWTask.android_vote_team_identity(stub, (HIYUKI, YUANWU))
        stub._android_team_recheck_at = time.time() - 999  # 复检间隔已过
        calls = []
        with patch.object(BaseWWTask, 'android_detect_team_identity',
                          side_effect=lambda: calls.append(1) or None):
            BaseWWTask.android_locked_team_identity(stub)
        self.assertEqual(calls, [], '战斗期间绝不能做画面识别(用户要求编队为准)')

    def test_recheck_runs_outside_combat(self):
        stub = StubTask(scene_in_combat=False)
        for _ in range(3):
            BaseWWTask.android_vote_team_identity(stub, (HIYUKI, YUANWU))
        stub._android_team_recheck_at = time.time() - 999
        calls = []
        with patch.object(BaseWWTask, 'android_detect_team_identity',
                          side_effect=lambda: calls.append(1) or None):
            BaseWWTask.android_locked_team_identity(stub)
        self.assertEqual(len(calls), 1, '非战斗时按间隔复检, 自动跟随换队')


class TestBuildCharsFromIdentity(unittest.TestCase):
    def test_build_two_char_team(self):
        stub = StubTask(chars=[None, None, None])
        ok = BaseWWTask.android_build_chars_from_identity(stub, (HIYUKI, YUANWU), 0)
        self.assertTrue(ok)
        self.assertEqual(len(stub.chars), 2)
        self.assertEqual(stub.chars[0].name, 'Hiyuki')
        self.assertEqual(stub.chars[1].name, 'Yuanwu')

    def test_build_preserves_old_char_state(self):
        stub = StubTask(chars=[None, None, None])
        BaseWWTask.android_build_chars_from_identity(stub, (HIYUKI, YUANWU), 0)
        old = stub.chars[0]
        old.current_con = 0.66
        BaseWWTask.android_build_chars_from_identity(stub, (HIYUKI, YUANWU), 0)
        self.assertIs(stub.chars[0], old, '同名角色必须复用旧实例(保留战斗状态)')
        self.assertEqual(old.current_con, 0.66)

    def test_unknown_identity_keeps_old_slot(self):
        stub = StubTask(chars=[None, None, None])
        BaseWWTask.android_build_chars_from_identity(stub, (HIYUKI, YUANWU), 0)
        second = list(stub.chars)
        ok = BaseWWTask.android_build_chars_from_identity(stub, (HIYUKI, None), 0)
        self.assertTrue(ok)
        self.assertIs(stub.chars[1], second[1], 'None 槽位保留旧对象')
        self.assertEqual(len([c for c in stub.chars if c is not None]), 2)

    def test_all_unknown_fails(self):
        stub = StubTask(chars=[None, None, None])
        self.assertFalse(BaseWWTask.android_build_chars_from_identity(stub, (None, None), 0))

    def test_build_by_canonical_direct(self):
        stub = StubTask()
        char = build_char_by_canonical(stub, HIYUKI, 0, None)
        self.assertIsNotNone(char)
        self.assertEqual(char.char_name, HIYUKI)

    def test_build_unknown_canonical_returns_old(self):
        stub = StubTask()
        sentinel = object()
        self.assertIs(build_char_by_canonical(stub, '不存在角色', 0, sentinel), sentinel)


class TestAndroidLoadChars(unittest.TestCase):
    def test_load_chars_android_uses_lock_without_ocr(self):
        stub = StubTask(chars=[None, None, None])
        for _ in range(3):
            BaseWWTask.android_vote_team_identity(stub, (HIYUKI, YUANWU))
        with patch.object(BaseWWTask, 'android_detect_team_identity',
                          side_effect=lambda: (_ for _ in ()).throw(AssertionError('锁定后不允许画面识别'))):
            ok = BaseCombatTask.load_chars_android(stub, 0)
        self.assertTrue(ok)
        self.assertEqual(stub.chars[0].name, 'Hiyuki')
        self.assertEqual(stub.chars[1].name, 'Yuanwu')

    def test_load_chars_android_detects_when_unlocked(self):
        stub = StubTask(chars=[None, None, None])
        with patch.object(BaseWWTask, 'android_locked_team_identity', return_value=None), \
                patch.object(BaseWWTask, 'android_detect_team_identity',
                             return_value=(HIYUKI, YUANWU)):
            ok = BaseCombatTask.load_chars_android(stub, 1)
        self.assertTrue(ok)
        self.assertEqual(stub.chars[0].name, 'Hiyuki')

    def test_load_chars_android_fails_without_identity(self):
        stub = StubTask(chars=[None, None, None])
        with patch.object(BaseWWTask, 'android_locked_team_identity', return_value=None), \
                patch.object(BaseWWTask, 'android_detect_team_identity', return_value=None):
            # 全部失败时退回上游 PC 框模板识别(老行为), 保证战斗不中断
            self.assertTrue(BaseCombatTask.load_chars_android(stub, 0))
            self.assertTrue(all(c is not None for c in stub.chars[:2]),
                            '兜底路径必须构建出角色对象')
            self.assertEqual(stub.chars[0].char_name, 'unknown')

    def test_load_chars_android_survives_detect_exception(self):
        """v1.5.14 回归: 识别环节抛异常(如 v1.5.13 的 AttributeError)时,
        load_chars_android 不得炸掉 load_chars, 必须记日志并走上游兜底,
        否则 do_check_in_combat 每 100ms 报错一次形成错误风暴。"""
        stub = StubTask(chars=[None, None, None])
        with patch.object(BaseWWTask, 'android_locked_team_identity', return_value=None), \
                patch.object(BaseWWTask, 'android_detect_team_identity',
                             side_effect=AttributeError('boom')):
            self.assertTrue(BaseCombatTask.load_chars_android(stub, 0))
        self.assertTrue(all(c is not None for c in stub.chars[:2]),
                        '异常后兜底路径必须构建出角色对象')


class TestAndroidConBox(unittest.TestCase):
    """v1.5.13: 手游元素图标(0.388,0.917)@1920x1080 比 PC 大, PC 协奏环检测框
    的环带半径(22~27px@1920)够不到手游协奏弧(约 37~42px), current_con 恒 0,
    延奏永远不触发。安卓端必须用对准手游图标的大框。"""

    def test_get_con_box_android_geometry(self):
        stub = StubTask(adb=True)
        box = BaseCombatTask.get_con_box(stub)
        self.assertEqual(box.name, 'con_full_android')
        # @1920x1080: 框应为 (692, 937) 起、约 105x105, 中心 (745, 990) 对准元素图标
        self.assertAlmostEqual(box.x + box.width / 2, 0.388 * 1920, delta=3)
        self.assertAlmostEqual(box.y + box.height / 2, 0.9167 * 1080, delta=3)
        self.assertAlmostEqual(box.width, 105, delta=4)
        self.assertAlmostEqual(box.height, 105, delta=4)

    def test_get_con_box_pc_unchanged(self):
        stub = StubTask(adb=False)
        box = BaseCombatTask.get_con_box(stub)
        self.assertEqual(box.name, 'con_full')
        # PC 框 @1920x1080: (715, 971) 起 63x63
        self.assertAlmostEqual(box.x, 1431 / 3840 * 1920, delta=2)
        self.assertAlmostEqual(box.y, 1942 / 2160 * 1080, delta=2)
        self.assertAlmostEqual(box.width, 63, delta=2)
        self.assertAlmostEqual(box.height, 63, delta=2)

    def test_android_con_box_covers_mobile_arc(self):
        from src.task.BaseCombatTask import ANDROID_CON_BOX
        x1, y1, x2, y2 = ANDROID_CON_BOX
        # 框中心必须对准手游元素图标 (0.388, 0.9167)
        self.assertAlmostEqual((x1 + x2) / 2 / 3840, 0.388, delta=0.003)
        self.assertAlmostEqual((y1 + y2) / 2 / 2160, 0.9167, delta=0.003)
        # 环带半径 0.35119~0.42261 * 框高(换算到 1920x1080) 必须覆盖弧 37~42px
        box_h_1080 = (y2 - y1) / 2160 * 1080
        r1 = 0.35119 * box_h_1080
        r2 = 0.42261 * box_h_1080
        self.assertLessEqual(r1, 37, f'环带内沿 {r1:.1f}px 必须小于弧内沿 37px')
        self.assertGreaterEqual(r2, 42, f'环带外沿 {r2:.1f}px 必须大于弧外沿 42px')
        # 元素图标本体(半径约 35px)必须整体落在环带内孔里, 否则图标金色会被误判成协奏弧
        self.assertGreaterEqual(r1, 35, f'环带内沿 {r1:.1f}px 必须不小于元素图标半径 35px')


class TestSnapshotGeometry(unittest.TestCase):
    def test_snapshot_boxes_around_scaled_avatar(self):
        stub = StubTask()
        import numpy as np
        import cv2
        frame = np.zeros((1080, 1920, 3), dtype=np.uint8)
        # 画一个"头像": 圆心 (1745, 280)@1920x1080, 直径 110px
        cv2.circle(frame, (1745, 280), 55, (120, 130, 140), -1)
        stub._executor = SimpleNamespace(nullable_frame=lambda: frame)
        canvas, boxes = BaseWWTask.android_team_bar_snapshot(stub)
        self.assertIsNotNone(canvas)
        self.assertEqual(canvas.shape, frame.shape, '画布必须与主帧同尺寸, 避免清空特征缓存')
        self.assertEqual(len(boxes), 3)
        b0 = boxes[0]
        # 缩放后头像中心: px1=int(0.850*1920)=1632, py1=int(0.185*1080)=199
        scale = 0.58
        cx = 1632 + (1745 - 1632) * scale
        cy = 199 + (280 - 199) * scale
        self.assertLess(abs(b0.x + b0.width / 2 - cx), 3)
        self.assertLess(abs(b0.y + b0.height / 2 - cy), 3)
        # 搜索框必须完全容纳缩放后的头像(半径 55*0.58=32px)
        self.assertGreaterEqual(b0.width / 2, 35)
        self.assertGreaterEqual(b0.height / 2, 35)


if __name__ == '__main__':
    unittest.main(verbosity=2)
