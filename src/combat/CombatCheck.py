import re
import time

import cv2
import numpy as np

import win32api

from ok import find_boxes_by_name, Logger, calculate_color_percentage, TaskDisabledException
from ok import find_color_rectangles, get_mask_in_color_range, is_pure_black
from src import text_white_color
from src.Labels import Labels
from src.char.Roccia import Roccia
from src.task.BaseWWTask import BaseWWTask

logger = Logger.get_logger(__name__)
# 云游戏血条消失后仍视为战斗中的秒数, 之后才检查结束条件(声骸识别)
CLOUD_HEALTH_LOST_GRACE = 3
# 没有锁定目标且看不到血条持续超过该秒数时, 认定怪物已经死亡/消失, 结束自动战斗。
# 比 target_enemy 的单次超时更可靠: 即使血条因云游戏压缩闪烁, 也不会无限续命。
NO_ENEMY_EXIT_SECONDS = 2.0
# 云游戏专属的无敌人退出窗口, 必须大于 CLOUD_HEALTH_LOST_GRACE。
# 之前所有端共用 2 秒, 而云游戏血条宽限是 3 秒 —— 宽限还没到期就被 no_enemy_for()
# 判成"没敌人", 战斗中途中断去走奖励; 官方 TacetTask 要等 walk_to_treasure 30 秒
# 超时才发现"战斗仍在进行", 表现就是敌人没打完却莫名其妙停了。
CLOUD_NO_ENEMY_EXIT_SECONDS = 6.0
# 云游戏重锁时血条消失多久才认定目标死亡: 串流延迟 + 技能特效遮挡下 1.2 秒太短。
CLOUD_RETARGET_HEALTH_LOST = CLOUD_HEALTH_LOST_GRACE
# 云游戏锁定图标: 锁定时骷髅外圈为金色, 未锁定为灰色。视频压缩后 has/no_target_cloud 模板分数只差约 0.01,
# 只用模板定位图标(位置随角色技能栏布局变化), 再看图标内金色像素占比判断是否锁定。
CLOUD_LOCK_SEARCH_BOX = (0.62, 0.85, 0.84, 0.95)
CLOUD_LOCK_GOLD_RATIO = 0.02
# 云游戏画面有串流延迟, 中键锁定后要等更久才能看到金圈, 点得太快会把刚锁定的目标又切掉
CLOUD_RETARGET_INTERVAL = 0.8
# 串流血条的渐变/压缩会让同一条血条仅约 60% 像素落在颜色范围内。
CLOUD_HEALTH_BAR_FILL = 0.6
# 安卓(手游)端谐振破坏检测:
# PC 的 f_break 模板是 "F" 键帽图标, 手游端提示是触摸图标+文字, 永远匹配不上,
# 导致 MuMu 从不触发谐振破坏。安卓端改为两层检测:
#   1. f_break_full(谐振条满的美术图标, 跨端一致)模板, 阈值放宽到 0.85;
#   2. OCR 在屏幕中央区域找 "破坏/谐振" 提示文字, 记录文字位置。
# 找到后把 box 存到 _f_break_box, f_break() 直接点击该位置, 不再按 F 键。
ANDROID_BREAK_OCR_RE = re.compile(r'破坏|谐振')
ANDROID_BREAK_FULL_THRESHOLD = 0.85
# OCR 检测区域: 谐振破坏提示出现在屏幕中央偏上, 取中央区域控制 OCR 耗时。
ANDROID_BREAK_OCR_BOX = (0.2, 0.2, 0.75, 0.75)
# 安卓(手游)端战斗坚持参数: MuMu 上 boss 潜地/无敌帧/切波次期间血条会消失一段时间,
# PC 端有 has_health(血条仍在)时的 30 秒耐心路径, 但安卓端 has_target 和血条是同一个
# 判定, 血条一没就走 target_enemy_time_out(默认 3 秒) -> break out of combat,
# 表现为"打着打着莫名其妙不打了"。安卓端改为:
ANDROID_RETARGET_TIMEOUT = 8    # 无血条时重锁定耐心 3 -> 8 秒
ANDROID_RETARGET_RETRY = 6      # 重锁定失败后先重试一次再退出战斗
ANDROID_NO_ENEMY_EXIT = 4.0     # 连续无敌人退出窗口 2 -> 4 秒
ANDROID_FRAME_DEAD_MAX = 20     # 整帧全黑(抓屏故障)最多坚持秒数, 超过走正常判定


class CombatCheck(BaseWWTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._in_combat = False
        self.skip_combat_check = False
        self.boss_lv_template = None
        self.boss_lv_mask = None
        self._in_liberation = False  # return True
        self.has_count_down = False
        self.sleep_check_interval = 0.4
        self.last_out_of_combat_time = 0
        self.boss_lv_box = None
        self.boss_health_box = None
        self.boss_health = None
        self.last_break_check_time = 0
        self.out_of_combat_reason = ""
        self.last_in_realm_not_combat = 0
        self._last_liberation = 0
        self.target_enemy_time_out = 3
        self.switch_char_time_out = 5
        self.combat_end_condition = None
        self.has_lavitator = False
        self.target_enemy_error_notified = False
        self._cloud_health_lost_at = 0
        self._no_enemy_since = 0
        self.cds = {
        }
        self.esc_count = 0
        self.can_break = False
        self._f_break_box = None
        self._android_frame_dead_since = 0
        # 聚落等场景: 敌人(如双极)飞出范围时, 原地多试几次锁敌再放弃, 而不是
        # 一路追出聚落。默认 0 = 保持框架原有行为, 只有任务显式开启才生效。
        self.target_enemy_retry_count = 0
        self.target_enemy_retry_timeout = 5
        self.target_lost_give_up = False
        self._target_retried_this_episode = False

    def tap_target(self, **kwargs):
        """锁敌: PC/云游戏用鼠标中键; 安卓端(MuMu)用 Y 键。

        MuMu 走 is_adb() 分支, 中键点击不会触发游戏内锁敌,
        必须用 Y 键(模拟器键位映射里的锁定目标键)才能锁定并进入战斗。
        """
        if self.is_adb():
            self.send_key('y', **kwargs)
        else:
            self.middle_click(**kwargs)

    @property
    def in_liberation(self):
        return self._in_liberation

    @in_liberation.setter
    def in_liberation(self, value):
        self._in_liberation = value
        if value:
            self._last_liberation = time.time()

    def on_combat_check(self):
        return True

    def reset_to_false(self, reason=""):
        self.out_of_combat_reason = reason
        self.do_reset_to_false()
        return False

    def do_reset_to_false(self):
        self.cds = {}
        self._in_combat = False
        self.skip_combat_check = False
        self.boss_lv_mask = None
        self.esc_count = 0
        self.boss_lv_template = None
        self.in_liberation = False  # return True
        self.has_count_down = False
        self.last_out_of_combat_time = 0
        self.boss_lv_box = None
        self.boss_health = None
        self.boss_health_box = None
        self._cloud_health_lost_at = 0
        self._no_enemy_since = 0
        self.last_in_realm_not_combat = 0
        self.has_lavitator = False
        self.can_break = False
        self._f_break_box = None
        self.scene.set_not_in_combat()
        return False

    def check_f_break(self):
        if self.can_break:
            return True
        if self.is_adb():
            return self._android_check_f_break()
        if self.find_one(Labels.f_break_full, threshold=0.92):
            self.logger.debug('found f_break_full')
            self.can_break = True
            return True
        if not self.can_break and not self._in_liberation and time.time() - self.last_break_check_time > 1:
            self.last_break_check_time = time.time()
            if self.find_one('f_break', box=self.box_of_screen(0.2, 0.2, 0.75,
                                                               0.8, hcenter=True, vcenter=True), target_height=720):
                if not self.is_pick_f():
                    self.can_break = True
                    return True

    def _android_check_f_break(self):
        """安卓(MuMu)端谐振破坏检测: 模板找谐振条图标 + OCR 找"破坏"提示文字。

        PC 的 f_break 模板是 F 键帽, 手游端是触摸图标, 模板匹配不到。
        检测成功时把提示位置存入 _f_break_box, 供 f_break() 点击。
        OCR 有开销, 限制 1 秒一次; f_break_full 模板便宜, 每次调用都查。
        """
        box = self.find_one(Labels.f_break_full, threshold=ANDROID_BREAK_FULL_THRESHOLD)
        if box is not None:
            self.logger.debug('android found f_break_full')
            self._f_break_box = box
            self.can_break = True
            return True
        if self._in_liberation:
            self._f_break_box = None
            return False
        if time.time() - self.last_break_check_time <= 1:
            return False
        self.last_break_check_time = time.time()
        center = self.box_of_screen(*ANDROID_BREAK_OCR_BOX, hcenter=True, vcenter=True,
                                    name='android_break_ocr')
        try:
            matches = self.ocr(box=center, match=ANDROID_BREAK_OCR_RE)
        except Exception as e:
            self.logger.debug(f'android f_break ocr failed: {e}')
            matches = None
        if matches:
            self._f_break_box = max(matches, key=lambda b: b.y + b.height / 2)
            self.logger.debug('android found break prompt by ocr')
            self.can_break = True
            return True
        self._f_break_box = None
        return False

    def f_break(self):
        if self.can_break or self.check_f_break():
            start = time.time()
            while time.time() - start < 0.5 or (time.time() - start < 5 and (self.can_break or self.check_f_break())):
                if self.is_adb():
                    box = getattr(self, '_f_break_box', None)
                    if box is not None:
                        # 手游端必须点击提示图标/文字本身, 按 F 键(或键位映射)没有谐振破坏
                        x, y = box.center()
                        self.click(x, y, after_sleep=0.1)
                    else:
                        # can_break 被其它路径置位但没有坐标: 尽力而为, 普攻 + F
                        self.click(after_sleep=0.1)
                        self.send_key('f', after_sleep=0.1)
                else:
                    self.send_key('f', after_sleep=0.1)
                    self.click(after_sleep=0.1)
                self.can_break = False
            return True

    def check_count_down(self):
        count_down_area = self.box_of_screen_scaled(3840, 2160, 1820, 266, 2100,
                                                    340, name="check_count_down", hcenter=True)
        count_down = self.calculate_color_percentage(text_white_color,
                                                     count_down_area)

        if self.has_count_down:
            if count_down < 0.03:
                numbers = self.ocr(box=count_down_area, match=count_down_re)
                if self.debug:
                    self.screenshot(f'count_down disappeared {count_down:.2f}%')
                logger.info(f'count_down disappeared {numbers} {count_down:.2f}%')
                if not numbers:
                    self.has_count_down = False
                    return False
                else:
                    return True
            else:
                return True
        else:
            if count_down > 0.03:
                numbers = self.ocr(box=count_down_area, match=count_down_re)
                if numbers:
                    self.has_count_down = True
                logger.info(f'set count_down to {self.has_count_down}  {numbers} {count_down:.2f}%')
            return self.has_count_down

    @property
    def target_area_box(self):
        return self.box_of_screen(0.1, 0.10, 0.9, 0.9, hcenter=True, name="target_area_box")

    def is_boss(self):
        return self.find_one('boss_break_shield') or self.find_one('boss_break_lock')

    def no_enemy_for(self, seconds=None):
        """连续没有目标/血条的时间是否超过阈值。

        安卓端默认 4 秒: boss 潜地/无敌帧/切波次期间血条消失是正常的,
        2 秒就把战斗判死会导致"打着打着莫名其妙不打了"。
        """
        if seconds is None:
            if getattr(self, 'target_enemy_retry_count', 0) and not self.is_adb():
                # 开了"原地重锁"的任务: 给足 lock timeout 再判定无敌人,
                # 否则 2 秒就退出战斗, 根本来不及重锁飞走的目标。
                seconds = self.target_enemy_retry_timeout
            elif self.is_adb():
                seconds = ANDROID_NO_ENEMY_EXIT
            elif self.is_browser():
                # 云游戏: 必须比 CLOUD_HEALTH_LOST_GRACE 长, 否则宽限期内就被判脱战。
                seconds = CLOUD_NO_ENEMY_EXIT_SECONDS
            else:
                seconds = NO_ENEMY_EXIT_SECONDS
        now = time.monotonic()
        if not getattr(self, '_no_enemy_since', 0):
            self._no_enemy_since = now
            return False
        return now - self._no_enemy_since >= seconds

    def _retry_target_before_give_up(self, has_health=False):
        """锁不到目标时原地重试 N 次(不移动, 不追击)。

        返回 True 表示重锁成功、战斗应继续；返回 False 表示确实丢了目标，
        调用方结束战斗并置 target_lost_give_up，由任务决定下一步(例如换聚落)。
        """
        retries = int(getattr(self, 'target_enemy_retry_count', 0) or 0)
        if retries <= 0 or self.is_adb():
            return False
        if self._target_retried_this_episode:
            return False
        self._target_retried_this_episode = True
        for attempt in range(1, retries + 1):
            self.log_warning(
                self.tr('目标锁定失败，原地重锁 {current}/{total}（每次最多 {timeout} 秒）')
                .format(current=attempt, total=retries,
                        timeout=self.target_enemy_retry_timeout))
            if self.target_enemy(wait=True, time_out=self.target_enemy_retry_timeout,
                                 check_health=has_health):
                self._no_enemy_since = 0
                self.target_lost_give_up = False
                return True
            self.sleep(0.4)
        self.target_lost_give_up = True
        self.log_warning(self.tr('多次重锁仍失败，放弃当前目标。'))
        return False

    def _android_frame_is_dead(self):
        """MuMu 抓屏偶发整帧黑/空: 把黑帧当"无敌人"会误退出战斗。

        返回 True 表示当前帧不可用, 战斗判定应保持 in_combat 等抓屏恢复,
        最多坚持 ANDROID_FRAME_DEAD_MAX 秒, 超时走正常判定让上层处理。
        """
        frame = getattr(self, 'frame', None)
        if frame is None:
            dead = True
        else:
            try:
                dead = bool(is_pure_black(frame))
            except Exception:
                dead = False
        if not dead:
            self._android_frame_dead_since = 0
            return False
        now = time.time()
        if not getattr(self, '_android_frame_dead_since', 0):
            self._android_frame_dead_since = now
            logger.warning('android combat: black/empty frame, keep in combat')
            return True
        if now - self._android_frame_dead_since > ANDROID_FRAME_DEAD_MAX:
            self._android_frame_dead_since = 0
            return False
        return True

    def do_check_in_combat(self, target):
        # 安卓端(如 MuMu)掉线弹窗必须在战斗判定前处理。触发任务(AutoCombatTask)
        # 和战斗循环都不经过 is_main(), 之前只有 is_main() 检查掉线, 导致弹窗
        # 遮暗画面 -> check_health_bar() 恒 False -> 一直 target lost retarget,
        # 最后 break out of combat, 表现就是"卡住不动、也不重新登录"。
        # 点掉弹窗 + logged_in=False 后, 由 AutoLoginTask 每 5 秒自动重新登录。
        if self.is_adb() and self.handle_android_disconnect():
            return self.reset_to_false(reason='android disconnected')
        if self.is_adb() and self._android_frame_is_dead():
            return self.scene.set_in_combat()
        if self.in_liberation:
            return True
        if self._in_combat:
            if self.scene.in_combat() is not None:
                return self.scene.in_combat()
            self.check_f_break()
            if current_char := self.get_current_char():
                if current_char.skip_combat_check():
                    return self.scene.set_in_combat()
            if not self.on_combat_check():
                self.log_info(self.tr('on_combat_check failed'))
                return self.reset_to_false(reason='on_combat_check failed')
            has_target = self.has_target()
            if has_target:
                self._no_enemy_since = 0
                self._target_retried_this_episode = False
                self.target_lost_give_up = False
                self.last_in_realm_not_combat = 0
                return self.scene.set_in_combat()
            has_health = self.check_health_bar()
            if has_health:
                self._no_enemy_since = 0
                self._target_retried_this_episode = False
                self.target_lost_give_up = False
            if (self.is_browser() or self.is_adb()) and self.cloud_health_bar_grace(has_health):
                # 云游戏: 未锁定但敌人血条仍在(或刚消失不久)即视为战斗中,
                # 且要先于结束条件判断, 避免技能特效/血条闪烁让声骸识别误判战斗结束。
                # 但如果血条是特效误判而反复闪烁, 仍要在连续无目标超时后退出。
                if self.no_enemy_for():
                    if self._retry_target_before_give_up(has_health):
                        return self.scene.set_in_combat()
                    return self.reset_to_false(reason='no enemy alive')
                self.last_in_realm_not_combat = 0
                return self.scene.set_in_combat()
            if self.no_enemy_for():
                if self._retry_target_before_give_up(has_health):
                    return self.scene.set_in_combat()
                return self.reset_to_false(reason='no enemy alive')
            if self.combat_end_condition is not None and self.combat_end_condition():
                return self.reset_to_false(reason='end condition reached')
            if getattr(self, 'target_enemy_retry_count', 0) and not self.is_adb():
                # 聚落场景: 敌人飞走时不要因为残留血条等 30 秒, 5 秒后就走重锁流程。
                retarget_timeout = self.target_enemy_retry_timeout
            elif has_health:
                retarget_timeout = 30
            elif self.is_adb():
                # 安卓端 has_target 和血条是同一个判定, 血条一没就走默认 3 秒,
                # boss 潜地/无敌帧/切波次会被误判战斗结束; 延长耐心并重试一次。
                retarget_timeout = ANDROID_RETARGET_TIMEOUT
            else:
                retarget_timeout = self.target_enemy_time_out
            if self.target_enemy(wait=True, time_out=retarget_timeout, check_health=has_health):
                logger.debug(f'retarget enemy succeeded')
                return self.scene.set_in_combat()
            if self.should_check_monthly_card() and self.handle_monthly_card():
                return self.scene.set_in_combat()
            logger.error('target_enemy failed, try recheck break out of combat')
            if self._retry_target_before_give_up(has_health):
                return self.scene.set_in_combat()
            if self.is_adb():
                # 一次失败不直接退出: 重试一轮, 避免血条短暂消失误判结束战斗。
                self.sleep(1.5)
                if self.target_enemy(wait=True, time_out=ANDROID_RETARGET_RETRY, check_health=has_health):
                    logger.debug('android retarget retry succeeded')
                    return self.scene.set_in_combat()
                logger.error('android retarget retry failed, break out of combat')
            return self.reset_to_false(reason='target enemy failed')
        else:
            from src.task.AutoCombatTask import AutoCombatTask
            chars_loaded = self.load_chars()
            has_target = self.has_target()
            if not has_target and target:
                self.log_debug('try target')
                self.tap_target(after_sleep=0.1)
            in_combat = has_target or ((self.config.get('Auto Target') or not isinstance(self,
                                                                                         AutoCombatTask)) and self.check_health_bar())
            if in_combat:
                if not has_target and not self.target_enemy(wait=True):
                    if not self.target_enemy_error_notified:
                        self.target_enemy_error_notified = True
                        self.log_error(self.tr('Target enemy failed, please disable Nvidia/AMD Filter or Sharpening!'),
                                       notify=True)
                    return False
                self.has_lavitator = self.find_one('edge_levitator', threshold=0.65)
                self.log_info(self.tr('enter combat {has_lavitator}').format(has_lavitator=self.has_lavitator))
                self._in_combat = chars_loaded or self.load_chars()
                return self._in_combat

    def in_combat(self, target=False):
        self.in_sleep_check = True
        try:
            return self.do_check_in_combat(target)
        except TaskDisabledException:
            raise
        except Exception as e:
            logger.error(f'do_check_in_combat:', e)
        finally:
            self.in_sleep_check = False

    def ensure_levitator(self):  # 目前未使用
        if not self.config.get('Check Levitator', True):
            return True
        if levi := self.find_one('edge_levitator', threshold=0.6):
            self.log_debug('edge levitator found {}'.format(levi))
            return True
        if self.has_char(Roccia):
            if self.find_one('levitator_roccia', threshold=0.6):
                return True
        if self.is_open_world_auto_combat():
            return False
        start = time.time()
        self.sleep(0.2)
        if levi := self.find_one('edge_levitator', threshold=0.6):
            self.log_debug('recheck edge levitator found {}'.format(levi))
            return True
        while time.time() - start < 1 and self.in_team()[0]:
            self.send_key_down(self.key_config.get('Wheel Key'))
            self.sleep(0.4)
        if self.in_team()[0]:
            self.log_info(self.tr('can not open wheel'))
            self.send_key_up(self.key_config.get('Wheel Key'))
            self.sleep(0.1)
            return False
        levitator = self.wait_feature('wheel_levitator', threshold=0.65, box=self.box_of_screen(0.27, 0.16, 0.68, 0.76))
        self.sleep(0.1)
        if not levitator:
            self.send_key_up(self.key_config.get('Wheel Key'))
            raise Exception('no levitator tool in the tab wheel!')
        old = win32api.GetCursorPos()
        self.move(levitator.x, levitator.y)
        abs_pos = self.executor.interaction.capture.get_abs_cords(levitator.x, levitator.y)
        win32api.SetCursorPos(abs_pos)
        self.sleep(0.1)
        self.send_key_up(self.key_config.get('Wheel Key'))
        self.sleep(0.2)
        win32api.SetCursorPos(old)
        if not self.wait_feature('edge_levitator', threshold=0.6, time_out=1):
            if self.has_char(Roccia):
                if self.find_one('levitator_roccia', threshold=0.6):
                    return True
        self.log_debug(f'ensuring leviator succees {levitator}')
        return self.target_enemy()

    def log_time(self, start, name):
        logger.debug(f'check cost {name} {time.time() - start}')
        return True

    def ocr_lv_text(self):
        lvs = self.ocr(box=self.target_area_box,
                       match=re.compile(r'lv\.\d{1,3}', re.IGNORECASE),
                       target_height=540, name='lv_text')
        return lvs

    def get_target_names(self):
        has_name = 'has_target'
        no_name = 'no_target'
        if self.is_browser():
            has_name += '_cloud'
            no_name += '_cloud'
        elif self.width == 1600:
            has_name += '_169'
            no_name += '_169'
        return has_name, no_name

    def allow_target_box_short_combat_check(self):
        if hasattr(self, 'get_current_char') and (current_char := self.get_current_char(raise_exception=False)):
            return getattr(current_char, 'target_box_short_combat_check', False)
        return False

    def has_target(self, double_check=False):
        if self.is_browser():
            return self.cloud_has_target()
        if self.is_adb():
            # 安卓端(如 MuMu)是手游 UI, 没有 PC 端的锁定图标(骷髅准星),
            # 找 has_target 模板永远匹配不到 -> 一直 "target lost, retarget",
            # 即使手动锁定了敌人也不会进入攻击循环。
            # 手游里"有敌人头顶红色血条"即等价于"有可战斗目标"。
            return self.check_health_bar()
        threshold = 0.6
        has_name, no_name = self.get_target_names()
        best = self.find_best_match_in_box(self.get_box_by_name(has_name).scale(1.1), [has_name, no_name],
                                           threshold=threshold)
        if not best:
            best = self.find_best_match_in_box(self.get_box_by_name('box_target_enemy_long'),
                                               [has_name, no_name],
                                               threshold=threshold)
        if not best:
            best = self.find_best_match_in_box(self.get_box_by_name('target_box_long2'), [has_name, no_name],
                                               threshold=threshold)
        if not best and self.allow_target_box_short_combat_check() and self.find_best_match_in_box(
                self.get_box_by_name('target_box_short'), [has_name, no_name], threshold=threshold):
            return True

        if not best:
            best = self.find_best_match_in_box(self.get_box_by_name(has_name).scale(1.1, 2.0),
                                               [has_name, no_name],
                                               threshold=threshold)
            if best and self.esc_count == 0:
                if double_check:
                    logger.error(f'try fix bear echo')
                    self.send_key('esc', after_sleep=2)
                    self.send_key('esc', after_sleep=1.5)
                    self.esc_count = 1
                    return False
                else:
                    self.sleep(1)
                    return self.has_target(double_check=True)
        return best and best.name == has_name

    def cloud_health_bar_grace(self, has_health, grace=CLOUD_HEALTH_LOST_GRACE):
        """云游戏: 血条可见, 或消失未超过 grace 秒(低血量/特效/压缩导致的闪烁), 返回 True。"""
        now = time.time()
        if has_health:
            self._cloud_health_lost_at = 0
            return True
        if not self._cloud_health_lost_at:
            self._cloud_health_lost_at = now
        return now - self._cloud_health_lost_at < grace

    def cloud_lock_icon_gold_ratio(self):
        """云游戏: 定位锁定图标, 返回其中金色像素占比; 找不到图标返回 None。"""
        icon = self.find_best_match_in_box(self.box_of_screen(*CLOUD_LOCK_SEARCH_BOX), list(self.get_target_names()),
                                           threshold=0.6)
        if not icon or self.frame is None:
            return None
        crop = self.frame[icon.y:icon.y + icon.height, icon.x:icon.x + icon.width]
        if crop.size == 0:
            return None
        gold = cv2.inRange(cv2.cvtColor(crop, cv2.COLOR_BGR2HSV), (15, 90, 150), (35, 255, 255))
        return np.count_nonzero(gold) / gold.size

    def cloud_has_target(self):
        """云游戏: 锁定图标外圈为金色即已锁定。"""
        ratio = self.cloud_lock_icon_gold_ratio()
        return ratio is not None and ratio >= CLOUD_LOCK_GOLD_RATIO

    def target_visible(self):
        """PC 看锁定图标; 云游戏锁定图标或敌人血条(如 boss 入场后出现)任一可见即可。"""
        if self.is_browser():
            return self.has_target() or self.check_health_bar()
        return self.has_target()

    def target_enemy(self, wait=True, time_out=None, check_health=False):
        if not wait:
            self.tap_target()
        else:
            if self.target_visible():
                return True
            else:
                timeout = self.target_enemy_time_out if time_out is None else time_out
                logger.info(f'target lost try retarget {timeout}')
                start = time.time()
                health_lost_start = None
                # 云游戏画面延迟下血条会闪断数秒, 1.2 秒就提前放弃重锁会把活目标判死。
                health_lost_patience = CLOUD_RETARGET_HEALTH_LOST if self.is_browser() else 1.2
                while time.time() - start < timeout:
                    self.tap_target(interval=CLOUD_RETARGET_INTERVAL if self.is_browser() else 0.2)
                    if self.is_adb():
                        # 等待 Y 键锁敌期间继续普攻(安卓无坐标点击=右下角攻击按钮),
                        # 敌人重新出现/血条恢复时保持输出, 而不是站着干等。
                        self.click(after_sleep=0.1)
                    if self.target_visible():
                        return True
                    self.next_frame()
                    if check_health:
                        if not self.check_health_bar():
                            if health_lost_start is None:
                                health_lost_start = time.time()
                            elif time.time() - health_lost_start > health_lost_patience:
                                logger.info('health bar disappeared during retarget')
                                return False
                        else:
                            health_lost_start = None
                return False

    def has_health_bar(self):
        # 安卓端(手游 UI)血条带抗锯齿/渐变, 红色填充率只有 0.8~0.9;
        # PC 用的 0.95 会把手游血条全部漏掉 -> 一直认为没有敌人。
        adb = self.is_adb()
        if self._in_combat:
            min_height = self.height_of_screen(9 / 2160)
            max_height = min_height * 3
            min_width = self.width_of_screen(12 / 3840)
        else:
            min_height = self.height_of_screen(9 / 2160)
            max_height = min_height * 3
            min_width = self.width_of_screen(100 / 3840)

        browser = self.is_browser()
        # 手游血条允许更低的填充率, 并要求横向条形以排除伤害数字/技能特效
        health_threshold = 0.8 if adb else (CLOUD_HEALTH_BAR_FILL if browser else 0.95)
        boxes = find_color_rectangles(self.frame, enemy_health_color_red, min_width, min_height,
                                       max_height=max_height, threshold=health_threshold)
        if adb:
            boxes = [box for box in boxes if box.width >= box.height * 3 and box.width >= self.width_of_screen(100 / 3840)]
        if browser:
            # 放宽颜色填充后仍要求横向条形, 排除伤害数字和零散红色特效。
            boxes = [box for box in boxes if box.width >= box.height * 3]

        if len(boxes) > 0:
            self.draw_boxes('enemy_health_bar_red', boxes, color='blue')
            return True
        else:
            # 云游戏视频压缩会让少量血条像素偏离颜色范围, 放宽填充比例
            boxes = find_color_rectangles(self.frame, boss_health_color, min_width, min_height * 1.3,
                                          box=self.box_of_screen(1269 / 3840, 58 / 2160, 2533 / 3840, 200 / 2160,
                                                                 hcenter=True, vcenter=True),
                                          threshold=0.85 if self.is_browser() else 0.95)
            if len(boxes) == 1:
                self.boss_health_box = boxes[0]
                self.boss_health_box.width = 10
                self.boss_health_box.x += 6
                self.boss_health = self.boss_health_box.crop_frame(self.frame)
                self.draw_boxes('boss_health', boxes, color='blue')
                return True
        return False

    def check_health_bar(self):
        return self.has_health_bar() or self.is_boss()

    def keep_boss_text_white(self):
        cropped = self.boss_lv_box.crop_frame(self.frame)
        mask, area = get_mask_in_color_range(cropped, boss_white_text_color)
        if area / mask.shape[0] * mask.shape[1] < 0.05:
            mask, area = get_mask_in_color_range(cropped, boss_orange_text_color)
            if area / mask.shape[0] * mask.shape[1] < 0.05:
                mask, area = get_mask_in_color_range(cropped,
                                                     boss_red_text_color)
                if area / mask.shape[0] * mask.shape[1] < 0.05:
                    logger.error(f'keep_boss_text_white cant find text with the correct color')
                    return None, 0
        return cropped, mask


count_down_re = re.compile(r'\d\d')


def keep_only_white(frame):
    frame[frame != 255] = 0
    return frame


target_enemy_color_yellow = {
    'r': (0x84, 0xAD),  # Red range
    'g': (0x84, 0xAF),  # Green range
    'b': (0x20, 0x6F)  # Blue range
}  # 207,75,60

enemy_health_color_red = {
    'r': (174, 225),  # Red range
    'g': (55, 85),  # Green range
    'b': (55, 76)  # Blue range
}  # 207,75,60

enemy_health_color_black = {
    'r': (10, 55),  # Red range
    'g': (28, 50),  # Green range
    'b': (18, 70)  # Blue range
}

boss_white_text_color = {
    'r': (200, 255),  # Red range
    'g': (200, 255),  # Green range
    'b': (200, 255)  # Blue range
}

boss_orange_text_color = {
    'r': (218, 218),  # Red range
    'g': (178, 178),  # Green range
    'b': (68, 68)  # Blue range
}

boss_red_text_color = {
    'r': (200, 230),  # Red range
    'g': (70, 90),  # Green range
    'b': (60, 80)  # Blue range
}

boss_health_color = {
    'r': (245, 255),  # Red range
    'g': (30, 185),  # Green range
    'b': (4, 75)  # Blue range
}

aim_color = {
    'r': (150, 213),  # Red range
    'g': (148, 185),  # Green range
    'b': (22, 62)  # Blue range
}
