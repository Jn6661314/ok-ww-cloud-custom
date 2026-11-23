"""云鸣潮战斗修复测试: 工坊队伍代码保活 + 云模式协奏环颜色容错。

验证:
1. get_char_by_pos 不再因 isinstance 误判把工坊自定义队伍类退回内置类(类名相同即保留)。
2. apply_team_char_classes 在某一槽位识别失败(unknown)时, 用上一轮缓存的身份补全,
   仍把工坊代码应用到三个角色, 而不是整体跳过。
3. widen_color_range / cloud_con_tolerance: 仅云浏览器模式放宽颜色区间, 本地零影响。
"""
import os
import sys
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

WORK = r"C:/Users/Jn/AppData/Local/ok-ww/data/apps/ok-ww/working"
os.chdir(WORK)
sys.path.insert(0, WORK)

from ok.util.config import Config

from src.Labels import Labels
from src.char import CharFactory
from src.char.CharFactory import apply_team_char_classes, get_char_by_pos
from src.char.CustomCharLoader import (clear_custom_char_cache, clear_team_char_cache,
                                        create_custom_team, save_team_char_code)
from src.char.Mortefi import Mortefi
from src.char.Verina import Verina
from src.char.Chixia import Chixia
from src.task.BaseCombatTask import (CLOUD_CON_COLOR_TOLERANCE, cloud_con_tolerance,
                                      con_colors, widen_color_range)

TEAM = (Mortefi, Verina, Chixia)
# char_name 用的是 Labels 模板对象, 不是类名
NAMES = (Labels.char_mortefi, Labels.char_verina, Labels.char_chixia)


def workshop_code(cls):
    return (
        f"from src.char.{cls.__name__} import {cls.__name__} as B\n"
        f"class {cls.__name__}(B):\n"
        f"    workshop_marker = True\n"
    )


class FakeTask:
    """Minimal task double: identity + debug + log + find hooks."""

    def __init__(self, browser=False):
        self.debug = False
        self._browser = browser
        self._executor = SimpleNamespace()
        self._team_char_identity_cache = {}

    def is_browser(self):
        return self._browser

    def log_info(self, *a, **k):
        pass

    def tr(self, text):
        return text

    def screenshot(self, *a, **k):
        pass


class TeamFixtureMixin:
    def setUp(self):
        self.old_folder = Config.config_folder
        self.tmp = tempfile.TemporaryDirectory()
        Config.config_folder = self.tmp.name
        clear_custom_char_cache()
        clear_team_char_cache()
        create_custom_team(TEAM)
        for cls in TEAM:
            save_team_char_code(TEAM, cls, workshop_code(cls))

    def tearDown(self):
        clear_custom_char_cache()
        clear_team_char_cache()
        Config.config_folder = self.old_folder
        self.tmp.cleanup()


class TestGetCharByPosKeepsCustomClass(TeamFixtureMixin, unittest.TestCase):
    """修复1: 工坊自定义队伍类是内置类的兄弟类, isinstance(old, builtin) 恒 False。"""

    def test_custom_team_instance_not_rebuilt_as_builtin(self):
        custom_cls = CharFactory.load_team_char_class(Mortefi, TEAM)
        self.assertIsNot(custom_cls, Mortefi, "fixture should produce a distinct sibling class")

        task = FakeTask()
        info = CharFactory.char_dict.get(NAMES[0])
        self.assertIsNotNone(info)
        old = custom_cls(task, 0, char_name=NAMES[0], confidence=0.99)

        def fake_find(task_, box, info_):
            return SimpleNamespace(confidence=0.99)

        with patch.object(CharFactory, "_find_registered_char", side_effect=fake_find), \
             patch.object(CharFactory, "_apply_char_config", side_effect=lambda t, c, i: c):
            result = get_char_by_pos(task, None, 0, old)

        # 关键: 返回的仍是工坊自定义类实例, 不是内置 Mortefi
        self.assertIs(type(result), custom_cls)


class TestApplyTeamClassesCacheFallback(TeamFixtureMixin, unittest.TestCase):
    """修复2: 单槽位 unknown 时用缓存身份补全, 工坊代码仍应用到全队。"""

    def test_unknown_slot_filled_from_cache(self):
        task = FakeTask()
        # 第一轮: 三个都识别成功 -> 应用工坊类并写入缓存
        chars = [cls(task, i, char_name=NAMES[i]) for i, cls in enumerate(TEAM)]
        apply_team_char_classes(task, chars)
        self.assertTrue(all(getattr(c, "workshop_marker", False) for c in chars),
                        "workshop code should apply to all slots on a good frame")
        self.assertTrue(task._team_char_identity_cache, "cache should be populated")

        # 第二轮: 槽位 1 识别失败(unknown) -> 用缓存的 Verina 身份补全, 工坊类仍全覆盖
        chars2 = [TEAM[0](task, 0, char_name=NAMES[0]),
                  CharFactory.BaseChar(task, 1, char_name="unknown"),
                  TEAM[2](task, 2, char_name=NAMES[2])]
        apply_team_char_classes(task, chars2)
        self.assertEqual(chars2[1].char_name, NAMES[1], "slot 1 identity restored from cache")
        self.assertEqual([type(c).__name__ for c in chars2], [c.__name__ for c in TEAM])
        self.assertTrue(all(getattr(c, "workshop_marker", False) for c in chars2),
                        "workshop code should still apply despite one bad frame")


class TestCloudColorTolerance(unittest.TestCase):
    """修复3: 颜色容错仅云浏览器模式生效, 本地原样。"""

    def test_widen_color_range(self):
        src = con_colors[0]
        w = widen_color_range(src, 10)
        for ch in ("r", "g", "b"):
            self.assertEqual(w[ch][0], max(0, src[ch][0] - 10))
            self.assertEqual(w[ch][1], min(255, src[ch][1] + 10))
        self.assertIs(widen_color_range(src, 0), src, "zero tolerance returns same object")

    def test_tolerance_only_for_browser(self):
        local = FakeTask(browser=False)
        cloud = FakeTask(browser=True)
        self.assertEqual(cloud_con_tolerance(local), 0)
        self.assertEqual(cloud_con_tolerance(cloud), CLOUD_CON_COLOR_TOLERANCE)
        # 没有 executor 时安全返回 0 (单测兼容)
        self.assertEqual(cloud_con_tolerance(SimpleNamespace(is_browser=lambda: True)), 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
