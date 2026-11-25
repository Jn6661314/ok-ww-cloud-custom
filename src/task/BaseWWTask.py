import math
import re
import time
from datetime import datetime, timedelta
from typing import List

import numpy as np

from ok import BaseTask, Logger, find_boxes_by_name, og, find_color_rectangles, mask_white, Box
from ok import CannotFindException
from ok.core.events import communicate
from ok import safe_get
from ok.task.exceptions import WaitFailedException
import cv2

from src.Labels import Labels
from src.scene.WWScene import WWScene
from src.task.touch_mode import TouchMode, TOUCH_MENU_BACK_KEY, TOUCH_BOOK_CLICK, TOUCH_ACTIVITY_CLICK
from src.task import android_world
from src.task import android_book

logger = Logger.get_logger(__name__)
number_re = re.compile(r'(\d+)')
stamina_re = re.compile(r'(\d+)/(\d+)')
LOGIN_TEXTS = ["登录", re.compile('Log|点击连接|Click to Connect', re.IGNORECASE), '登入']
CONNECT_TEXT = re.compile(r'點擊連線|點擊連接|点击连接|Click\s+to\s+Connect', re.IGNORECASE)
LOGIN_CLICK_SETTLE_TIME = 4  # seconds; keep below AutoLoginTask trigger_interval (5) so triggers don't overlap
RECHALLENGE_TEXT = re.compile(r'^\s*(?:重新挑战|重新挑戰|再次挑战|再次挑戰|Rechallenge)\s*$', re.IGNORECASE)
# 云游戏网页弹窗, 如 【云服务错误：1020】检测到您已长时间未进行操作，已和服务器断开连接。
# 1020 弹窗按钮是"退出游戏", 4012 只有"确定"; 两者都会回到云游戏首页。
CLOUD_DISCONNECT_TEXTS = re.compile(r'云服务错误|服务器断开|断开连接')
CLOUD_EXIT_GAME_TEXTS = re.compile(r'^(退出游戏|确定)$')
CLOUD_RELOGIN_TIMEOUT = 600
# 安卓端(模拟器)"连接已断开"弹窗: 画面后面仍然是大世界, in_team 判定依然为 True,
# 任务会以为一切正常, 但所有点击都被弹窗挡住, 表现同样是"卡住不动"。
# 该弹窗只有"确认"一个按钮, 点掉后游戏会退回登录页, 由 wait_login 重新登录。
ANDROID_DISCONNECT_TEXTS = re.compile(r'连接已断开|連接已斷開|断开连接|斷開連接|重新登录|重新登錄|重新連線')
# 弹窗按钮文案: 常规"确认"外, 部分版本掉线弹窗的按钮就是"重新登录/重新连接",
# 不加进候选会让 OCR 找不到按钮, 弹窗永远点不掉(表现为"卡住不动")。
ANDROID_CONFIRM_TEXTS = ['确认', '確認', '重新登录', '重新登錄', '重新连接', '重新連線', '重新連接']
# 掉线频率统计: 短时间内反复掉线基本是模拟器/网络环境问题(脚本无法根治),
# 攒够次数提示一次用户检查 MuMu 网络设置, 避免每 3 分钟刷一条通知。
ANDROID_DISCONNECT_GUIDE_SHORT = (
    'MuMu 短时间内频繁掉线，脚本已自动重连；建议关闭 MuMu 的后台省电/限帧设置，'
    '详见日志中的完整排查建议。')
ANDROID_DISCONNECT_GUIDE = (
    'MuMu 频繁掉线完整排查建议:\n'
    '1. MuMu 设置中心 → 性能/其他: 关闭"后台挂机时限制帧率/智能省电"类选项;\n'
    '2. MuMu 挂机时不要最小化到托盘, 保持后台网络开启;\n'
    '3. 模拟器安装目录 Nemu\\EmulatorShell\\networkReset.bat 以管理员运行后重启模拟器;\n'
    '4. 仍频繁掉线可尝试更换 DNS(114.114.114.114)或使用游戏加速器。')
ANDROID_DISCONNECT_GUIDE_INTERVAL = 1800  # 同一条设置建议的再次提醒间隔(秒)
ANDROID_DISCONNECT_GUIDE_THRESHOLD = 3    # 10 分钟内掉线多少次后提醒
ANDROID_DISCONNECT_GUIDE_WINDOW = 600
# CLOUD ACCOUNT ENTRY PATCH: cloud game can take minutes to load after clicking
# "进入游戏"; the home-page button stays visible, so clicks must be throttled.
CLOUD_START_COOLDOWN = 60
# Graded cooldown (seconds): the first "开始游戏" click often does not register,
# so retry quickly a couple of times, then back off to avoid restarting the queue.
CLOUD_START_COOLDOWNS = (0, 8, 30, CLOUD_START_COOLDOWN)
# 「传送」按钮的两套判据:
#   1) PC 模板 —— fast_travel_custom(地图上的黑色圆点) / gray_teleport(灰色传送点)
#      / remove_custom。点开"残像聚落"后地图上出现灰色传送点时走这一套。
#   2) OCR  —— 新界面(云游戏/移动端)点开聚落后, 右侧详情页底部是一个黑底白字的
#      「快速旅行」按钮, PC 模板在上面完全匹配不上(实测最高匹配度只有 0.02~0.28,
#      阈值 0.7 永远达不到), 只能靠 OCR 认字定位。
#      OCR 文本可能是"快速旅行", 也可能夹空格, 所以精确串 + 容错正则一起用。
TRAVEL_BUTTON_TEXTS = ('快速旅行', re.compile(r'快\s*速\s*旅\s*行'))
TRAVEL_BUTTON_SEARCH_BOX = (0.4, 0.55, 1.0, 1.0)
# 传送确认弹窗: PC 有 confirm_btn_* 模板, 移动端/新界面模板同样匹配不上, 用 OCR 兜底。
CONFIRM_BUTTON_TEXTS = ('确认', '確定', '确定', re.compile(r'确\s*认|確\s*認'))
CONFIRM_BUTTON_SEARCH_BOX = (0.3, 0.3, 0.7, 0.85)
# 安卓索拉指南左列的类别图标(PC 模板), 用于判断书是否已经打开
ANDROID_BOOK_TAB_FEATURES = ('gray_book_quest', 'gray_book_boss', 'gray_book_weekly', 'gray_book_all_monsters')
# MuMu 手游只有 1/2 两颗切换键, 对应当前编队中不在场的两个队友。
# 队伍识别以配置的编队为准, 不在战斗期间做画面 OCR(技能特效/伤害数字
# 会干扰徽章识别, 造成误判)。
# 绝不能发 3 键 —— 模拟器键位映射里没有绑定, 发了等于没按,
# 切到 3 号位就会永远失败并在 10 秒后中断战斗。
ANDROID_SWITCH_KEYS = ('1', '2')
# ---- 安卓编队锁定 (v1.5.13) --------------------------------------------
# 手游右上角队伍栏是圆形头像, 直径约 110px@1920x1080, 是 PC 端头像(约 64px)
# 的 1.7 倍。PC 头像模板(char_*)固定尺度直接匹配必然弱匹配 —— 实测同一队
# 2 秒内读出 4 种组合(漂泊者/渊武/仇远/绯雪乱串), char_type 随之漂移,
# 切人优先级/奶妈逻辑全废。
# 修复分三层:
#   1) 全局配置 'MuMu 安卓 Config'->'MuMu 编队' 手填角色名(最高优先级, 零识别);
#   2) 自动: 把队伍栏裁剪后缩放 0.58 倍到 PC 头像尺度再模板匹配(命中率高);
#   3) 连续 ANDROID_TEAM_LOCK_MIN_VOTES 次识别一致才锁定; 锁定后 load_chars
#      完全跳过模板匹配(战斗期间零 OCR, 响应"编队为准、战斗期不识别")。
ANDROID_TEAM_BAR_BOX = (0.850, 0.185, 0.970, 0.620)  # 队伍栏整体区域 (x1,y1,x2,y2)
ANDROID_TEAM_BAR_SCALE = 0.58  # 手游头像缩放到 PC 头像尺度的系数
# 每个编队槽位的头像中心 y(相对全屏)。实测 2 人队头像中心 y=0.259/0.403,
# 间距 0.144, 3 号位按同间距外推; 头像中心 x=0.909。
ANDROID_CHAR_SLOT_CENTER_Y = (0.259, 0.403, 0.547)
ANDROID_TEAM_VOTE_WINDOW = 7  # 投票窗口(最近 N 次识别)
ANDROID_TEAM_LOCK_MIN_VOTES = 3  # 连续一致次数达到即锁定
ANDROID_TEAM_RECHECK_INTERVAL = 15  # 已锁定后复检间隔(秒), 用于自动跟随换队
# 自动识别阈值: 手游头像构图与 PC 模板不同, 低阈值必然张冠李戴(实测 0.6 时
# 同一队读出 渊武/仇远/漂泊者 乱串), 提到 0.72 只接受高置信匹配。
ANDROID_DETECT_THRESHOLD = 0.72
f_white_color = {
    'r': (235, 255),  # Red range
    'g': (235, 255),  # Green range
    'b': (235, 255)  # Blue range
}
processed_feature = False
WIDE_MODE_UI_SCALE = 0.75
# 编队界面的判据。team_close 是可交互按钮, 鼠标悬停时会放大变形, 匹配分数掉到 0.62;
# team_start_challenge 在同一帧不随悬停变化, 且下一步本来就要点它。
TEAM_SCREEN_FEATURES = ('team_start_challenge', 'team_close')


class BaseWWTask(BaseTask):
    map_zoomed = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.monthly_card_config = self.get_global_config('Monthly Card Config')
        self.char_config = self.get_global_config('Character Config')
        self.key_config = self.get_global_config('Game Hotkey')  # 游戏热键配置
        # MuMu/安卓编队(可选, 用户手填则"编队为准"完全跳过画面识别)
        self.android_config = self.get_global_config('MuMu 安卓 Config')
        self.next_monthly_card_start = 0
        self.login_screen_visible = False
        self.scene: WWScene | None = None
        # 安卓触屏/PC/云 语义操作统一入口(返回与打开菜单在触屏是同一个按钮)
        self.touch = TouchMode(self)

    def back(self, *args, after_sleep=0, **kwargs):
        """安卓触屏统一返回语义: back == 打开菜单 == 键位表的 ` 键(KEYCODE_GRAVE)。

        基类 back() 会发 esc(ADB 下即 KEYCODE_BACK), 在 MuMu 等模拟器上会弹
        "确定退出游戏"而不是返回/菜单。触屏下所有 back() 一律走 ` 键;
        PC/云游戏行为不变。
        """
        if self.touch.is_touch:
            self.send_key(TOUCH_MENU_BACK_KEY, after_sleep=after_sleep)
        else:
            super().back(*args, after_sleep=after_sleep, **kwargs)

    # ---- 安卓模拟器(Pynput 真实键盘)输入 ------------------------------------
    # MuMu 手游靠"键位映射"操作: 模拟器把【真实 Windows 键盘事件】转成屏幕触摸。
    # ADBInteraction.send_key 走 `input keyevent KEYCODE_xxx`, 是安卓系统层按键,
    # 手游根本不认 —— 表现就是: 手动按 Y 能锁敌, 脚本 send_key('y') 却毫无反应,
    # 技能键 e/q/r 发出去没有动画(click_liberation 一直 timeout)。
    # 这里在 ADB 模拟器(带 hwnd_window, 排除真机)上叠加一次 Pynput 真实键盘事件,
    # 等价于手动按键, 触发模拟器键位映射。手游不响应原生 keyevent, 故叠加不会
    # 造成"按两次"; 真机无 hwnd_window, 仍只走原本的 ADB keyevent, 行为不变。
    def _adb_keymap_available(self):
        if not self.is_adb():
            return False
        try:
            dm = getattr(self.executor, 'device_manager', None)
            if dm is None or getattr(dm, 'hwnd_window', None) is None:
                return False  # 真机 ADB 没有模拟器窗口
            from ok.device.interaction_methods.adb import ADBInteraction
            return isinstance(getattr(self.executor, 'interaction', None), ADBInteraction)
        except Exception:
            return False

    def _adb_focus_window(self):
        """Pynput 真实键盘只会送到前台窗口, 发送前先把 MuMu 窗口切到前台。

        上游 PynputInteraction 也用 is_foreground() 拒绝非前台输入; 这里沿用同一
        判据, 但主动 bring_to_front() 一次, 让后台运行的脚本也能触发键位映射。
        """
        if not self._adb_keymap_available():
            return False
        try:
            hwnd_window = self.executor.device_manager.hwnd_window
            is_foreground = getattr(hwnd_window, 'is_foreground', None)
            bring_to_front = getattr(hwnd_window, 'bring_to_front', None)
            if callable(is_foreground) and is_foreground():
                return True
            if callable(bring_to_front):
                bring_to_front()
                time.sleep(0.05)
                if callable(is_foreground) and not is_foreground():
                    logger.debug('adb keymap: MuMu window still not foreground, skip pynput key')
                    return False
            # 桩对象/无前景判据的实现: 不阻断原有输入通道。
            return True
        except Exception as e:
            logger.debug(f'adb focus window failed: {e}')
            return False

    @staticmethod
    def _parse_pynput_key(key):
        from pynput import keyboard
        k = str(key).lower()
        special = {
            'esc': keyboard.Key.esc, 'escape': keyboard.Key.esc,
            'enter': keyboard.Key.enter, 'return': keyboard.Key.enter,
            'space': keyboard.Key.space, ' ': keyboard.Key.space,
            'tab': keyboard.Key.tab,
            'shift': keyboard.Key.shift, 'lshift': keyboard.Key.shift_l,
            'rshift': keyboard.Key.shift_r,
            'ctrl': keyboard.Key.ctrl, 'control': keyboard.Key.ctrl,
            'lctrl': keyboard.Key.ctrl_l, 'rctrl': keyboard.Key.ctrl_r,
            'alt': keyboard.Key.alt, 'lalt': keyboard.Key.alt_l, 'ralt': keyboard.Key.alt_r,
        }
        if k in special:
            return special[k]
        if k.startswith('f') and k[1:].isdigit() and 1 <= int(k[1:]) <= 12:
            return getattr(keyboard.Key, k)
        if len(k) == 1:
            return k  # 字母/数字/反引号等单字符, pynput 直接接受
        return None

    def _adb_real_key(self, key, down_time=0.02, up=True):
        """用 Pynput 发真实键盘事件(触发模拟器键位映射)。返回是否成功。"""
        if not self._adb_keymap_available() or not self._adb_focus_window():
            return False
        try:
            parsed = self._parse_pynput_key(key)
            if parsed is None:
                return False
            from pynput import keyboard
            ctrl = keyboard.Controller()
            ctrl.press(parsed)
            if up:
                time.sleep(min(max(down_time, 0.01), 0.2))
                ctrl.release(parsed)
            return True
        except Exception as e:
            logger.debug(f'adb real key failed for {key}: {e}')
            return False

    def send_key(self, key, down_time=0.02, interval=-1, after_sleep=0):
        """触屏下把所有 esc 改写为键位表的 ` 键(返回/菜单是同一个按钮)。

        覆盖 BaseCombatTask / DailyTask / CombatCheck 等散落的 send_key('esc'),
        无需逐个修改; ADB 输入通道下 ` 会映射为 KEYCODE_GRAVE。

        安卓模拟器上叠加 Pynput 真实键盘, 触发 MuMu 键位映射(见 _adb_real_key)。
        """
        if self.touch.is_touch and str(key).lower() in ('esc', 'escape'):
            key = TOUCH_MENU_BACK_KEY
        if self._adb_keymap_available():
            self._adb_real_key(key, down_time=down_time)
        return super().send_key(key, down_time=down_time, interval=interval, after_sleep=after_sleep)

    def send_key_down(self, key, after_sleep=0):
        """安卓模拟器长按走位: Pynput 按下真实键, 触发键位映射的方向摇杆。"""
        if self._adb_keymap_available():
            # ADBInteraction 没有 send_key_down/up, 不能回落到 super (会 AttributeError)。
            if self._adb_real_key(key, up=False) and after_sleep > 0:
                self.sleep(after_sleep)
            return
        return super().send_key_down(key, after_sleep=after_sleep)

    def send_key_up(self, key, after_sleep=0):
        """安卓模拟器松开走位键: 对应 send_key_down 的 Pynput 抬起。"""
        if self._adb_keymap_available():
            try:
                parsed = self._parse_pynput_key(key)
                if parsed is not None:
                    from pynput import keyboard
                    keyboard.Controller().release(parsed)
                    if after_sleep > 0:
                        self.sleep(after_sleep)
            except Exception as e:
                logger.debug(f'adb real key up failed for {key}: {e}')
            return  # 同上: 绝不回落到 ADBInteraction 不存在的 send_key_up
        return super().send_key_up(key, after_sleep=after_sleep)

    @property
    def logged_in(self):
        return og.my_app.logged_in

    @logged_in.setter
    def logged_in(self, value):
        og.my_app.logged_in = value

    def is_open_world_auto_combat(self):
        from src.task.AutoCombatTask import AutoCombatTask
        from src.task.TacetTask import TacetTask
        from src.task.DailyTask import DailyTask
        if isinstance(self, AutoCombatTask):
            if not self.in_realm():
                return True
        elif isinstance(self, (TacetTask, DailyTask)):
            return True
        return False

    def zoom_map(self, esc=True):
        if not self.map_zoomed:
            self.log_info(self.tr('zoom map to max'))
            self.map_zoomed = True
            self.send_key('m', after_sleep=1)
            self.click_relative(0.94, 0.33, after_sleep=0.5)
            if esc:
                self.send_key('esc', after_sleep=1)

    def validate(self, key, value):
        message = self.validate_config(key, value)
        if message:
            return False, message
        else:
            return True, None

    def absorb_echo_text(self, ignore_config=False):
        if self.game_lang == 'zh_CN' or self.game_lang == 'en_US' or self.game_lang == 'zh_TW':
            return re.compile(r'(吸收|Absorb)')
        else:
            return None

    @property
    def absorb_echo_feature(self):
        return self.get_feature_by_lang('absorb')

    def get_feature_by_lang(self, feature):
        lang_feature = feature + '_' + self.game_lang
        if self.feature_exists(lang_feature):
            return lang_feature
        else:
            return None

    def set_check_monthly_card(self, next_day=False):
        if self.monthly_card_config.get('Check Monthly Card'):
            now = datetime.now()
            hour = self.monthly_card_config.get('Monthly Card Time')
            # Calculate the next 4 o'clock in the morning
            next_four_am = now.replace(hour=hour, minute=0, second=0, microsecond=0)
            if now >= next_four_am or next_day:
                next_four_am += timedelta(days=1)
            next_monthly_card_start_date_time = next_four_am - timedelta(seconds=30)
            # Subtract 1 minute from the next 4 o'clock in the morning
            self.next_monthly_card_start = next_monthly_card_start_date_time.timestamp()
            logger.info('set next monthly card start time to {}'.format(next_monthly_card_start_date_time))
        else:
            self.next_monthly_card_start = 0

    @property
    def f_search_box(self):
        f_search_box = self.get_box_by_name('pick_up_f_hcenter_vcenter')
        f_search_box = f_search_box.copy(x_offset=-f_search_box.width * 0.3,
                                         width_offset=f_search_box.width * 0.65,
                                         height_offset=f_search_box.height * 6.5,
                                         y_offset=-f_search_box.height * 5,
                                         name='search_dialog')
        return f_search_box

    def find_f_with_claim_text(self):
        return self.find_f_with_text(target_text=[re.compile('领取|領取|Claim', re.IGNORECASE)])

    def find_f_with_text(self, target_text=None):
        f = self.find_one(Labels.pick_up_f_hcenter_vcenter, box=self.f_search_box, threshold=0.8)
        if not f:
            return None
        if not target_text:
            return f

        start = time.time()
        percent = 0.0
        while time.time() - start < 1:
            percent = self.calculate_color_percentage(f_white_color, f)
            if percent > 0.5:
                break
            self.next_frame()
            self.log_debug(f'f white color percent: {percent} wait')
        if percent < 0.5:
            return None

        if target_text:
            search_text_box = f.copy(x_offset=f.width * 5.2, width_offset=f.width * 6, height_offset=4.5 * f.height,
                                     y_offset=-0.8 * f.height, name='search_text_box')
            text = self.ocr(box=search_text_box, match=target_text)
            logger.debug(f'found f with text {text}, target_text {target_text}')
            if text:
                if text[0].y > search_text_box.y + f.height * 1:
                    logger.debug(f'found f with text {text} below, target_text {target_text}')
                    self.scroll_relative(0.5, 0.5, 1)
                return f
        else:
            return f

    def has_target(self):
        return False

    def walk_to_yolo_echo(self, time_out=8, update_function=None, echo_threshold=0.5):
        last_direction = None
        start = time.time()
        no_echo_start = 0
        while time.time() - start < time_out:
            self.next_frame()
            if self.pick_f():
                self.log_debug('pick echo success')
                self._stop_last_direction(last_direction)
                return True
            if self.in_combat():
                self.log_debug('pick echo has_target return fail')
                self._stop_last_direction(last_direction)
                return False
            echos = self.find_echos(threshold=echo_threshold)
            if not echos:
                if no_echo_start == 0:
                    no_echo_start = time.time()
                elif time.time() - no_echo_start > 3:
                    self.log_debug(f'walk front to_echo, no echos found, break')
                    break
                next_direction = 'w'
            else:
                no_echo_start = 0
                echo = echos[0]
                center_distance = echo.center()[0] - self.width_of_screen(0.5)
                threshold = 0.05 if not last_direction else 0.15
                if abs(center_distance) < self.height_of_screen(threshold):
                    if echo.y + echo.height > self.height_of_screen(0.65):
                        next_direction = 's'
                    else:
                        next_direction = 'w'
                elif center_distance > 0:
                    next_direction = 'd'
                else:
                    next_direction = 'a'
            last_direction = self._walk_direction(last_direction, next_direction)
            if update_function is not None:
                update_function()
        self._stop_last_direction(last_direction)

    def _walk_direction(self, last_direction, next_direction):
        if next_direction != last_direction:
            self._stop_last_direction(last_direction)
            if next_direction:
                self.send_key_down(next_direction)
        return next_direction

    def _stop_last_direction(self, last_direction):
        if last_direction:
            self.send_key_up(last_direction)
            self.sleep(0.01)
        return None

    def walk_to_box(self, find_function, time_out=30, end_condition=None, y_offset=0.05, x_threshold=0.07,
                    use_hook=False):
        start = time.time()
        while time.time() - start < time_out:
            if ended := self.do_walk_to_box(find_function, time_out=time_out - (time.time() - start),
                                            end_condition=end_condition, y_offset=y_offset,
                                            x_threshold=x_threshold, use_hook=use_hook):
                return ended

    def do_walk_to_box(self, find_function, time_out=30, end_condition=None, y_offset=0.05, x_threshold=0.07,
                       use_hook=False):
        if find_function:
            self.wait_until(lambda: (not end_condition or end_condition()) or find_function(), raise_if_not_found=True,
                            time_out=time_out)
        last_direction = None
        start = time.time()
        ended = False
        running = False
        last_target = None
        centered = False
        while time.time() - start < time_out:
            self.next_frame()
            if end_condition:
                ended = end_condition()
                if ended:
                    logger.info(f'do_walk_to_box ended {ended}')
                    break
            treasure_icon = find_function()
            if isinstance(treasure_icon, list):
                if len(treasure_icon) > 0:
                    treasure_icon = treasure_icon[0]
                else:
                    treasure_icon = None
            if treasure_icon:
                last_target = treasure_icon
            if last_target is None:
                next_direction = self.opposite_direction(last_direction)
                self.log_info(self.tr('find_function not found, change to opposite direction'))
            else:
                x, y = last_target.center()
                y = max(0, y - self.height_of_screen(y_offset))
                x_abs = abs(x - self.width_of_screen(0.5))
                threshold = 0.04 if not last_direction else x_threshold
                centered = centered or x_abs <= self.width_of_screen(threshold)
                if not centered:
                    if x > self.width_of_screen(0.5):
                        next_direction = 'd'
                    else:
                        next_direction = 'a'
                else:
                    if last_direction == 's':
                        center = 0.45
                    elif last_direction == 'w':
                        center = 0.6
                    else:
                        center = 0.5
                    if y > self.height_of_screen(center):
                        next_direction = 's'
                    else:
                        next_direction = 'w'
            if next_direction != last_direction:
                if last_direction:
                    self.send_key_up(last_direction)
                    self.sleep(0.001)
                last_direction = next_direction
                if next_direction:
                    self.send_key_down(next_direction)
            if running:
                if not self.find_one('on_the_wall', threshold=0.7):
                    self.log_info(self.tr('not on the wall, stop running'))
                    self.mouse_up(key='right')
            else:
                if next_direction == 'w' and self.find_one('on_the_wall', threshold=0.7):
                    self.log_info(self.tr('on the wall, start running'))
                    running = True
                    self.mouse_down(key='right')
                    self.sleep(0.1)
            if use_hook and next_direction == 'w':
                if self.find_one('tool_teleport', 0.75):
                    self.send_key(self.key_config['Tool Key'])
                    self.sleep(3)
                    continue
        if last_direction:
            self.send_key_up(last_direction)
            self.sleep(0.001)
        if running:
            self.send_key_up(self.key_config.get('Dodge Key'))
        if not end_condition:
            return last_direction is not None
        else:
            return ended

    def opposite_direction(self, direction):
        if direction == 'w':
            return 's'
        elif direction == 's':
            return 'w'
        elif direction == 'a':
            return 'd'
        elif direction == 'd':
            return 'a'
        else:
            return 'w'

    def get_direction(self, location_x, location_y, screen_width, screen_height, centered, current_direction):
        """
        Determines the direction ('w', 'a', 's', 'd') closest to the screen center.
        Args:
            location_x: The x-coordinate of the point.
            location_y: The y-coordinate of the point.
            screen_width: The width of the screen.
            screen_height: The height of the screen.
        Returns:
            A string "w", "a", "s", or "d".
        """
        if screen_width <= 0 or screen_height <= 0:
            # Handle invalid dimensions, default based on horizontal position
            return "a" if location_x < screen_width / 2 else "d"
        center_x = screen_width / 2
        center_y = screen_height / 2
        # Calculate vector from point towards the center
        delta_x = center_x - location_x
        delta_y = center_y - location_y
        # Determine dominant direction based on vector magnitude
        direction = None
        if (abs(delta_x) > abs(delta_y) or (not current_direction and abs(delta_x) > 0.05 * screen_height)
                or abs(delta_x) > 0.15 * screen_height):
            # More horizontal movement needed
            return "a" if delta_x > 0 else "d"

            # More vertical movement needed (or equal)
        return "w" if delta_y > 0 else "s"

    def find_treasure_icon(self):
        return self.find_one('treasure_icon', box=self.box_of_screen(0.03, 0.1, 0.97, 0.81, hcenter=True, vcenter=True),
                             threshold=0.8,
                             target_height=720)

    # 手游(安卓/MuMu)HUD 的普攻按钮中心, 相对截图 1920x1080 的比例。
    # 实测 MuMu 1500x845 截图上攻击按钮中心约 (1200, 655) -> (0.80, 0.775)。
    # PC 客户端"左键点屏幕任意处=普攻", 但手游只有点这个圆形按钮才是普攻;
    # 点屏幕中央(0.5,0.5)落在角色/空地上, 表现就是角色一动不动、怪不掉血。
    TOUCH_ATTACK_BUTTON = (0.80, 0.775)

    def _adb_attack_xy(self):
        """手游普攻按钮的执行器坐标(frame 1920x1080 等比换算)。"""
        return (self.width_of_screen(self.TOUCH_ATTACK_BUTTON[0]),
                self.height_of_screen(self.TOUCH_ATTACK_BUTTON[1]))

    def click(self, x=-1, y=-1, move_back=False, name=None, interval=-1, move=False, down_time=0.01, after_sleep=0,
              key="left"):
        if x == -1 and y == -1:
            if self.is_adb() and getattr(self, '_in_combat', False):
                # 手游战斗中: click() 无坐标是"普攻"语义(见 BaseChar.normal_attack /
                # continues_normal_attack / f_break)。必须点右下角攻击按钮, 不能点屏幕中心。
                x, y = self._adb_attack_xy()
            else:
                x = self.width_of_screen(0.5)
                y = self.height_of_screen(0.5)
            move = False
            down_time = 0.01
        else:
            down_time = 0.2
        return super().click(x, y, move_back, name, interval, move=move, down_time=down_time, after_sleep=after_sleep,
                             key=key)

    def mouse_down(self, x=-1, y=-1, name=None, key="left"):
        """安卓端(ADB)长按普攻(重击): 点住手游右下角攻击按钮。

        上游 ADBInteraction 没有 mouse_down, 直接调会抛 AttributeError 中断战斗
        (v1.5.6)。手游普攻靠点攻击按钮(见本类 click()), 长按同一按钮即重击。
        PC/云游戏仍走上游实现, 行为不变。
        """
        if not self.is_adb():
            return super().mouse_down(x, y, name=name, key=key)
        if x == -1 and y == -1:
            # 与 click() 一致: 战斗中长按攻击按钮; 非战斗兜底屏幕中心。
            if getattr(self, '_in_combat', False):
                x, y = self._adb_attack_xy()
            else:
                x = self.width_of_screen(0.5)
                y = self.height_of_screen(0.5)
        interaction = getattr(self.executor, 'interaction', None)
        capture = getattr(interaction, 'capture', None)
        nemu_impl = getattr(capture, 'nemu_impl', None)
        if nemu_impl is not None:
            try:
                nemu_impl.down(int(x), int(y))
                self._adb_mouse_down_xy = (int(x), int(y))
                return
            except Exception as e:
                logger.warning(f'adb mouse_down via nemu failed: {e}')
        # 兜底: 无 nemu 通道时降级为一次普通点击, 至少保证战斗循环不崩溃中断
        try:
            self.click(x, y, name=name, key=key)
        except Exception as e:
            logger.warning(f'adb mouse_down fallback click failed: {e}')

    def mouse_up(self, name=None, key="left"):
        """安卓端(ADB)结束长按, 对应 mouse_down 的 nemu 触摸抬起。"""
        if not self.is_adb():
            return super().mouse_up(name=name, key=key)
        interaction = getattr(self.executor, 'interaction', None)
        capture = getattr(interaction, 'capture', None)
        nemu_impl = getattr(capture, 'nemu_impl', None)
        if nemu_impl is not None and getattr(self, '_adb_mouse_down_xy', None):
            try:
                nemu_impl.up()
            except Exception as e:
                logger.warning(f'adb mouse_up via nemu failed: {e}')
            finally:
                self._adb_mouse_down_xy = None

    def check_for_monthly_card(self):
        if self.should_check_monthly_card():
            start = time.time()
            logger.info(f'check_for_monthly_card start check')
            if self.in_combat():
                logger.info(f'check_for_monthly_card in combat return')
                return time.time() - start
            if self.in_team_and_world():
                logger.info(f'check_for_monthly_card in team send sleep until monthly card popup')
                monthly_card = self.wait_until(self.handle_monthly_card, time_out=120, raise_if_not_found=False)
                logger.info(f'wait monthly card end {monthly_card}')
                cost = time.time() - start
                return cost
        return 0

    def in_realm(self):
        return not bool(getattr(self, 'treat_as_not_in_realm', False)) and self.find_one('illusive_realm_exit',
                                                                                         threshold=0.7,
                                                                                         frame_processor=convert_bw) and self.in_team() and not self.find_one(
            'world_earth_icon', threshold=0.55,
            frame_processor=convert_bw)

    def in_world(self):
        return self.find_one('world_earth_icon', threshold=0.55,
                             frame_processor=convert_bw) and self.in_team() and not self.find_one('illusive_realm_exit',
                                                                                                  threshold=0.7,
                                                                                                  frame_processor=convert_bw)

    def in_illusive_realm(self):
        return self.find_one('new_realm_4') and self.in_realm() and self.find_one('illusive_realm_menu', threshold=0.6)

    def walk_until_f(self, direction='w', time_out=1, raise_if_not_found=True, backward_time=0, target_text=None,
                     check_combat=False, running=False):
        logger.info(f'walk_until_f direction {direction} target_text: {target_text}')
        if not self.find_f_with_text(target_text=target_text):
            # 视角朝前
            self.middle_click(after_sleep=0.2)
            if backward_time > 0:
                if self.send_key_and_wait_f('s', raise_if_not_found, backward_time, target_text=target_text,
                                            running=running, check_combat=check_combat):
                    logger.info('walk backward found f')
                    return True
            if self.send_key_and_wait_f(direction, raise_if_not_found, time_out, target_text=target_text,
                                        running=running, check_combat=check_combat):
                logger.info('walk forward found f')
                return True
            return False
        else:
            return True

    def get_stamina(self):
        boxes = self.wait_ocr(0.49, 0.0, 0.92, 0.10, raise_if_not_found=False,
                              match=[number_re, stamina_re])
        if not boxes:
            self.screenshot('stamina_error')
            return -1, -1, -1
        current = 0
        back_up = 0
        for box in boxes:
            if match := stamina_re.search(box.name):
                current = int(match.group(1))
            elif match := number_re.search(box.name):
                back_up = int(match.group(1))
        self.info_set('current_stamina', current)
        self.info_set('back_up_stamina', back_up)
        return current, back_up, current + back_up

    def use_stamina(self, once=60, must_use=0):
        self.sleep(1)
        current, back_up, total = self.get_stamina()
        if current >= once * 2:
            used = once * 2
            use_double = True
            logger.info(f"当前体力大于等于双倍, {current} >= {once * 2}")
        elif must_use > once and total >= once * 2:
            used = once * 2
            use_double = True
            logger.info(f"当前加备用大于日常剩余所需, 使用双倍, {must_use} >= {once} and {total} >= {once * 2}")
        else:
            used = once
            use_double = False
            logger.info(f"使用单倍体力")
        if use_double:
            btn = self.click_dialog_right_button()
        else:
            btn = self.click_dialog_left_button()
        if self.wait_feature('gem_add_stamina', horizontal_variance=0.4, vertical_variance=0.05,
                             time_out=2, settle_time=0.5):  # 看是否需要使用备用体力
            self.click_relative(0.70, 0.71, hcenter=True, after_sleep=1)  # 点击确认
            self.click_relative(0.70, 0.71, hcenter=True, after_sleep=1)
            self.back(after_sleep=1)
            self.click(btn, after_sleep=1)

        current -= used
        must_use -= used
        total -= used
        if total < once:
            logger.info(f"current stamina: {current} not enough to continue")
            can_continue = False
        elif must_use <= 0 and current < once:
            can_continue = False
            logger.info(f"current stamina: {current} must_use completed, no need to use back_up")
        else:
            can_continue = True
        return can_continue, used

    def send_key_and_wait_f(self, direction, raise_if_not_found, time_out, running=False, target_text=None,
                            check_combat=False):
        if time_out <= 0:
            return
        self.send_key_down(direction)
        if running:
            self.sleep(0.1)
            self.mouse_down(key='right')
        f_found = self.wait_until(
            lambda: self.find_f_with_text(target_text=target_text) or (check_combat and self.in_combat()),
            time_out=time_out,
            raise_if_not_found=False)
        self.send_key_up(direction)
        if running:
            self.sleep(0.1)
            self.mouse_up(key='right')
        if not f_found:
            if raise_if_not_found:
                raise CannotFindException(self.tr('cant find the f to enter'))
            else:
                logger.warning(f"can't find the f to enter")
                return False
        return f_found

    def run_until(self, condiction, direction, time_out, raise_if_not_found=False, running=False, target=False,
                  post_walk=0):
        if time_out <= 0:
            return
        self.send_key_down(direction)
        if running:
            self.sleep(0.1)
            logger.debug(f'run_until condiction {condiction} direction {direction}')
            self.mouse_down(key='right')
        start = time.time()
        result = None
        while time.time() - start < time_out:
            if result := condiction():
                break
            if target:
                self.middle_click(interval=0.5)
            self.sleep(0.02)
        if result and post_walk:
            self.sleep(post_walk)
        self.send_key_up(direction)
        if running:
            self.sleep(0.1)
            self.mouse_up(key='right')

        if raise_if_not_found and not result:
            raise Exception(self.tr('wait condition failed while walking'))
        return result

    def is_moving(self):
        return False

    def handle_claim_button(self):
        while self.wait_until(self.has_claim, raise_if_not_found=False, time_out=1.5):
            self.sleep(0.5)
            self.send_key('esc')
            self.sleep(0.5)
            logger.info(f"handle_claim_button found a claim reward")
            return True

    def has_claim_stamina(self):
        return not self.in_team()[0] and self.find_one('claim_stamina_sign')

    def has_claim(self):
        return not self.in_team()[0] and self.find_one('claim_cancel_button_hcenter_vcenter', horizontal_variance=0.05,
                                                       vertical_variance=0.1, threshold=0.8)

    def test_absorb(self):
        # self.set_image('tests/images/absorb.png')
        image = cv2.imread('tests/images/absorb.png')
        result = self.executor.ocr_lib(image, use_det=True, use_cls=False, use_rec=True)
        self.logger.info(f'ocr_result {result}')

    def find_echos(self, threshold=0.3):
        """
        Main function to load ONNX model, perform inference, draw bounding boxes, and display the output image.

        Args:
            onnx_model (str): Path to the ONNX model.
            input_image (ndarray): Path to the input image.

        Returns:
            list: List of dictionaries containing detection information such as class_id, class_name, confidence, etc.
        """
        # Load the ONNX model
        ret = og.my_app.yolo_detect(self.frame, threshold=threshold, label=0)

        for box in ret:
            box.y += box.height * 1 / 3
            box.height = 1
        self.draw_boxes("echo", ret)
        return ret

    def yolo_find_all(self, threshold=0.3):
        """
        Main function to load ONNX model, perform inference, draw bounding boxes, and display the output image.

        Args:
            onnx_model (str): Path to the ONNX model.
            input_image (ndarray): Path to the input image.

        Returns:
            list: List of dictionaries containing detection information such as class_id, class_name, confidence, etc.
        """
        # Load the ONNX model
        boxes = og.my_app.yolo_detect(self.frame, threshold=threshold, label=-1)
        ret = sorted(boxes, key=lambda detection: detection.confidence, reverse=True)
        return ret

    def pick_echo(self):
        if self.find_f_with_text(target_text=self.absorb_echo_text()):
            self.send_key('f')
            if not self.handle_claim_button():
                self.log_debug('found a echo picked')
                return True

    def pick_f(self, handle_claim=True):
        if self.find_one('pick_up_f_hcenter_vcenter', box=self.f_search_box, threshold=0.8):
            self.send_key('f', after_sleep=1)
            if not handle_claim:
                return True
            if not self.handle_claim_button():
                self.log_debug('found a echo picked')
                return True

    def is_pick_f(self):
        f = self.find_one('pick_up_f_hcenter_vcenter', box=self.f_search_box,
                          threshold=0.8)
        if not f:
            return False
        dialog_search = f.copy(x_offset=f.width * 3, width_offset=f.width * 1.8, height_offset=f.height * 2,
                               y_offset=-f.height,
                               name='search_dialog')
        dialog_3_dots = self.find_feature('dialog_3_dots', box=dialog_search,
                                          threshold=0.6)
        return bool(dialog_3_dots)

    def walk_to_treasure(self, send_f=True, raise_if_not_found=True):
        self.log_info(self.tr('start walk_to_treasure'))
        found = False
        try:
            found = bool(self.walk_to_box(self.find_treasure_icon, end_condition=self.find_f_with_claim_text))
            if not found:
                found = bool(self.walk_to_box(self.find_treasure_icon, end_condition=self.find_f_with_text))
        except WaitFailedException:
            found = False
            if not self.is_adb():
                raise
        if not found and self.is_adb():
            # 手游端: combat_once 可能在残象切波次/清怪间隙误判"战斗结束",
            # 走向奖励时其实还在打(现场截图: "清理残象 2/3" 血条仍在), 宝箱
            # 尚未刷新, 图标永远找不到; 上游恢复路径依赖 in_realm() 的 PC
            # 模板, 手游端识别不到, WaitFailedException 会炸掉整个每日任务。
            # 这里改为: 先回去把残象清完再走一次; 还找不到就交给外层的
            # pick_f / has_claim_stamina 判断(farm 循环自带 rechallenge 恢复)。
            self.log_warning(self.tr('walk_to_treasure: 未找到宝箱(可能残象未清完), 检查是否仍在战斗'))
            if self.wait_combat(target=True, time_out=5, raise_if_not_found=False):
                self.combat_once(target=True, wait_combat_time=5)
                return self.walk_to_treasure(send_f=send_f, raise_if_not_found=False)
            self.log_warning(self.tr('walk_to_treasure: 无战斗也无宝箱, 交回上层处理'))
            return
        if send_f:
            self.walk_until_f(time_out=2, backward_time=0, raise_if_not_found=raise_if_not_found)
        self.sleep(1)

    def yolo_find_echo(self, use_color=False, turn=True, update_function=None, time_out=8, threshold=0.5):
        max_echo_count = 0
        if self.pick_echo():
            self.sleep(0.5)
            return True, True
        front_box = self.box_of_screen(0.35, 0.35, 0.65, 0.53, hcenter=True)
        color_threshold = 0.02
        for i in range(4):
            if turn:
                self.center_camera()
            echos = self.find_echos(threshold=threshold)
            max_echo_count = max(max_echo_count, len(echos))
            self.log_debug(f'max_echo_count {max_echo_count}')
            if echos:
                self.log_info(self.tr('yolo found echo {echos}').format(echos=echos))
                # return self.walk_to_box(self.find_echos, time_out=15, end_condition=self.pick_echo), max_echo_count > 1
                return self.walk_to_yolo_echo(update_function=update_function, time_out=time_out), max_echo_count > 1
            if use_color:
                color_percent = self.calculate_color_percentage(echo_color, front_box)
                self.log_debug(f'pick_echo color_percent:{color_percent}')
                if color_percent > color_threshold:
                    # if self.debug:
                    #     self.screenshot('echo_color_picked')
                    self.log_debug(f'found color_percent {color_percent} > {color_threshold}, walk now')
                    # return self.walk_to_box(self.find_echos, time_out=15, end_condition=self.pick_echo), max_echo_count > 1
                    return self.walk_to_yolo_echo(update_function=update_function), max_echo_count > 1
            if not turn and i == 0:
                return False, max_echo_count > 1
            self.send_key('a', down_time=0.05)
            self.sleep(0.5)

        self.center_camera()
        return False, max_echo_count > 1

    def center_camera(self):
        self.click(0.5, 0.5, down_time=0.2, key='middle')
        self.sleep(1)

    def turn_direction(self, direction):
        if direction != 'w':
            self.send_key(direction, down_time=0.05, after_sleep=0.5)
        self.center_camera()

    def walk_find_echo(self, backward_time=1, time_out=3):
        if self.walk_until_f(time_out=time_out, backward_time=backward_time, target_text=self.absorb_echo_text(),
                             raise_if_not_found=False, check_combat=True):  # find and pick echo
            logger.debug(f'farm echo found echo move forward walk_until_f to find echo')
            return self.pick_f()

    def incr_drop(self, dropped):
        if dropped:
            self.info['Echo Count'] = self.info.get('Echo Count', 0) + 1
            self.info['Echo per Hour'] = round(
                self.info.get('Echo Count', 0) / max(time.time() - self.start_time, 1) * 3600)

    def should_check_monthly_card(self):
        if self.next_monthly_card_start > 0:
            if 0 < time.time() - self.next_monthly_card_start < 120:
                return True
        return False

    def sleep(self, timeout):
        return super().sleep(timeout - self.check_for_monthly_card())

    def wait_in_team_and_world(self, time_out=10, raise_if_not_found=True, esc=False):
        success = self.wait_until(self.in_team_and_world, time_out=time_out, raise_if_not_found=raise_if_not_found,
                                  post_action=lambda: self.back(after_sleep=2) if esc else None)
        if success:
            self.sleep(0.5)
        return success

    def esc_world_confirm(self, send_esc=True):
        if send_esc:
            self.send_key('esc', after_sleep=1)
        self.click_dialog_right_button()
        self.wait_in_team_and_world(time_out=120)

    def click_dialog_right_button(self):
        confirm = self.find_one([
            Labels.confirm_btn_hcenter_vcenter,
            Labels.confirm_btn_highlight_hcenter_vcenter,
        ])
        if not confirm:
            raise CannotFindException(self.tr("can't find dialog right button"))
        self.click(confirm, after_sleep=2)
        return confirm

    def esc_cancel(self, send_esc=True):
        if send_esc:
            self.send_key('esc', after_sleep=1)
        self.click_dialog_left_button()
        self.wait_in_team_and_world(time_out=120)

    def click_dialog_left_button(self) -> Box:
        cancel = self.find_one([
            Labels.cancel_button_hcenter_vcenter,
            Labels.cancel_button_highlight_hcenter_vcenter,
        ])
        if not cancel:
            raise CannotFindException(self.tr("can't find dialog left button"))
        self.click(cancel, after_sleep=2)
        return cancel

    def ensure_main(self, esc=True, time_out=30):
        self.info_set('current task', f'wait main esc={esc}')
        self.login_screen_visible = False
        if not self.logged_in:
            time_out = 600
        if not self.wait_until(lambda: self.is_main(esc=esc), time_out=time_out, raise_if_not_found=False):
            if not self.logged_in:
                # A nested DailyTask shares the outer scheduled task's executor.
                active_task = self.executor.current_task
                if active_task is not None and active_task.exit_after_task:
                    # Let the executor report the failure and save its screenshot first.
                    self.executor.submit(communicate.quit.emit, name='quit after login timeout')
                if self.login_screen_visible:
                    raise CannotFindException(self.tr('Timed out on the game login screen.'))
            raise Exception(self.tr('Please start in game world and in team!'))
        self.sleep(0.5)
        self.info_set('current task', f'in main esc={esc}')

    def is_main(self, esc=True):
        # 安卓端"连接已断开"弹窗必须在大世界判定之前处理:
        # 弹窗背后仍是大世界, in_team 会返回 True, 任务以为一切正常,
        # 但所有点击都被弹窗挡住, 于是表现为"卡住不动也不跳过"。
        if self.handle_android_disconnect():
            return False
        if self.in_team_and_world():
            self.logged_in = True
            if self.in_realm():
                self.esc_world_confirm()
            return True
        if self.wait_login() or self.login_screen_visible:
            return False
        if self.handle_monthly_card():
            return False
        if self.handle_cloud_disconnect():
            return self.in_team_and_world()
        if esc:
            self.log_debug('main esc')
            self.touch.back(after_sleep=2)
            return False

    def find_cloud_disconnect(self):
        """云游戏断线弹窗: 返回 '退出游戏' 按钮, 否则 None。"""
        if not self.is_browser():
            return None
        texts = self.ocr(box=self.box_of_screen(0.2, 0.25, 0.8, 0.75, hcenter=True, vcenter=True),
                         name='cloud_disconnect', log=self.debug)
        if not self.find_boxes(texts, match=CLOUD_DISCONNECT_TEXTS):
            return None
        return self.find_boxes(texts, match=CLOUD_EXIT_GAME_TEXTS) or None

    def handle_cloud_disconnect(self):
        """云游戏断线(如长时间无操作的 1020/4012 错误)后退出到云游戏首页, 再点进入游戏重新登录。"""
        exit_game = self.find_cloud_disconnect()
        if not exit_game:
            return False
        self.log_info(self.tr('Cloud game disconnected, re-entering the game'), notify=True)
        self.click(exit_game[0], after_sleep=3)
        self.logged_in = False
        # wait_login 在云游戏首页点击"进入游戏", 进游戏后处理登录/月卡, 回到大世界后返回 True
        self.wait_until(self.wait_login, time_out=CLOUD_RELOGIN_TIMEOUT, raise_if_not_found=True,
                        settle_time=1)
        return True

    def handle_android_disconnect(self):
        """安卓端(模拟器)"连接已断开"弹窗处理。

        MuMu 长时间挂机或网络抖动时, 游戏会弹出【连接已断开】对话框
        ("已与服务器断开连接, 请尝试重新登录")。此时画面背后仍然是大世界,
        in_team 判定依然为 True, 任务会认为一切正常, 但所有点击都被弹窗
        挡住, 表现和用户反馈的"卡住不动、不跳过、也没日志"一模一样。

        处理方式: 先用廉价的亮度预筛确认中央有大弹窗(否则不做 OCR),
        再 OCR 确认弹窗文案确实是断线提示, 点掉"确认", 把 logged_in 复位,
        让 wait_login 接手重新登录。
        """
        if not self.is_adb():
            return False
        # 战斗判定每帧都会调到这里; 点掉弹窗后有 2s sleep, 期间画面可能还是弹窗,
        # 不节流的话会重复点确认(弹窗消失后那一击可能落到登录页)。15s 内只处理一次,
        # 足够 AutoLoginTask(每 5s 一次)接手重新登录。
        now = time.time()
        if now - getattr(self, '_android_disconnect_handled_at', 0) < 15:
            return False
        frame = self.executor.nullable_frame()
        if frame is None:
            return False
        has_dialog, ratio = android_world.has_center_dialog(frame)
        if not has_dialog:
            return False
        self.log_debug(f'android: center dialog detected (bright ratio={ratio:.2f}), checking text')
        texts = self.ocr(box=self.box_of_screen(0.15, 0.2, 0.85, 0.8, hcenter=True, vcenter=True),
                         name='android_disconnect', log=self.debug)
        if not self.find_boxes(texts, match=ANDROID_DISCONNECT_TEXTS):
            return False
        confirm = self.find_boxes(texts, match=ANDROID_CONFIRM_TEXTS)
        if not confirm:
            return False
        self.log_info(self.tr('Game disconnected, closing the notice and logging in again'), notify=True)
        # OCR 结果按 y 排序, 最后一个"确认"就是弹窗底部的按钮
        self.click(confirm[-1], after_sleep=2)
        self.logged_in = False
        self._android_disconnect_handled_at = time.time()
        self._track_android_disconnect_frequency()
        return True

    def _track_android_disconnect_frequency(self):
        """统计掉线频率: 短时间内反复掉线提示用户检查模拟器/网络环境。

        实测(2026-11-25 日志)MuMu 挂机时每 180 秒整断线一次, 脚本只能自动
        重连, 根治要改 MuMu 设置(后台省电/网络)或网络环境。按窗口计数提醒,
        同一条建议最多每 30 分钟弹一次, 避免刷屏。
        """
        now = time.time()
        stamps = getattr(self, '_android_disconnect_times', [])
        stamps = [t for t in stamps if now - t < ANDROID_DISCONNECT_GUIDE_WINDOW]
        stamps.append(now)
        self._android_disconnect_times = stamps
        if len(stamps) < ANDROID_DISCONNECT_GUIDE_THRESHOLD:
            return
        if now - getattr(self, '_android_disconnect_guide_at', 0) < ANDROID_DISCONNECT_GUIDE_INTERVAL:
            return
        self._android_disconnect_guide_at = now
        self.log_warning(self.tr(ANDROID_DISCONNECT_GUIDE))
        self.log_warning(self.tr(ANDROID_DISCONNECT_GUIDE_SHORT), notify=True)

    def wait_login(self):
        self.login_screen_visible = False
        if not self.logged_in:
            if self.in_team_and_world():
                self.logged_in = True
                return True
            self.handle_monthly_card()
            if login_close := self.find_one('login_close', horizontal_variance=0.15, vertical_variance=0.1):
                self.click(login_close, after_sleep=1)
                self.log_info(self.tr('Close the notice!'))
                return False
            texts = self.ocr(log=self.debug)

            login_box = self.box_of_screen(0.3, 0.3, 0.7, 0.7, hcenter=True, vcenter=True)
            if login := self.find_boxes(texts,
                                        boundary=login_box,
                                        match=LOGIN_TEXTS):
                self.login_screen_visible = True
                if not self.find_boxes(texts, boundary=login_box, match="+86"):
                    # the game may be auto logging in with saved credentials, wait and
                    # confirm the login button is still there before clicking (#1356)
                    self.sleep(LOGIN_CLICK_SETTLE_TIME)
                    texts = self.ocr(log=self.debug)
                    login = self.find_boxes(texts, boundary=login_box,
                                            match=LOGIN_TEXTS)
                    self.login_screen_visible = bool(login)
                    if login and not self.find_boxes(texts, boundary=login_box,
                                                     match="+86"):
                        self.click(login, after_sleep=1)
                        self.log_info(self.tr('Click the Login button!'))
                return False
            if agree := self.find_boxes(texts, boundary=login_box, match="同意"):
                self.log_debug(f'found agree {agree}')
                if self.find_boxes(texts, boundary=login_box, match=re.compile("隐私")):
                    self.click(agree, after_sleep=1)
                    self.log_info(self.tr('Click the Agree button!'))
                return False
            if self.find_boxes(texts, match=[re.compile("游戏即将重启"), re.compile('遊戲即將重啟')]):
                self.sleep(0.2)
                self.log_info(self.tr('Game update completed; the game will restart'))
                self.click(self.find_boxes(texts, match=["确认", "確認"]), after_sleep=60)
                result = self.start_device()
                self.log_info(self.tr('start_device end {result}').format(result=result))
                self.sleep(30)
                return False

            if start := self.find_boxes(texts, boundary='bottom_right', match=["开始游戏", re.compile("进入游戏")]):
                if not self.find_boxes(texts, boundary='bottom_right', match=LOGIN_TEXTS):
                    # CLOUD ACCOUNT ENTRY PATCH: graded cooldown. The first "开始游戏"
                    # click often does not register, so retry quickly; then back off so
                    # polling does not restart the cloud queue during loading.
                    now = time.time()
                    clicks = getattr(self, '_cloud_start_clicks', 0)
                    cooldown = CLOUD_START_COOLDOWNS[min(clicks, len(CLOUD_START_COOLDOWNS) - 1)]
                    if now - getattr(self, '_cloud_start_click_time', 0) >= cooldown:
                        self._cloud_start_click_time = now
                        self._cloud_start_clicks = clicks + 1
                        self.click(start, after_sleep=2)
                        self.log_info(self.tr('Click Start Game! ({clicks}) {start}')
                                      .format(clicks=clicks + 1, start=start))
                    return False
            if switch_login := self.find_one(Labels.switch_account, vertical_variance=0.1, threshold=0.7):
                if boxes := self.find_boxes(texts, boundary=self.box_of_screen(0.37, 0.63, 0.63, 0.99, hcenter=True,
                                                                               vcenter=True)):
                    self.login_screen_visible = bool(self.find_boxes(boxes, match=CONNECT_TEXT))
                    self.log_info(self.tr('wait_login {switch_login} {boxes}').format(switch_login=switch_login, boxes=boxes))
                    self.click_relative(0.503, 0.926, hcenter=True, vcenter=True, after_sleep=3)
                    return False

    def in_team_and_world(self):
        return self.in_team()[
            0]  # and self.find_one(f'gray_book_button', threshold=0.7, canny_lower=50, canny_higher=150)

    def get_angle_between(self, my_angle, angle):
        if my_angle > angle:
            to_turn = angle - my_angle
        else:
            to_turn = -(my_angle - angle)
        if to_turn > 180:
            to_turn -= 360
        elif to_turn < -180:
            to_turn += 360
        return to_turn

    def get_my_angle(self):
        return self.rotate_arrow_and_find()[0]

    def rotate_arrow_and_find(self):
        arrow_template = self.get_feature_by_name('arrow')
        original_mat = arrow_template.mat
        max_conf = 0
        max_angle = 0
        max_target = None
        max_mat = None
        (h, w) = arrow_template.mat.shape[:2]
        # self.log_debug(f'turn_east h:{h} w:{w}')
        center = (w // 2, h // 2)
        target_box = self.get_box_by_name('arrow')
        # if self.debug:
        #     self.screenshot('arrow_original', original_ mat)
        for angle in range(0, 360):
            # Rotate the template image
            rotation_matrix = cv2.getRotationMatrix2D(center, -angle, 1.0)
            template = cv2.warpAffine(original_mat, rotation_matrix, (w, h))
            # mask = np.where(np.all(template == [0, 0, 0], axis=2), 0, 255).astype(np.uint8)

            target = self.find_one(box=target_box,
                                   template=template, threshold=0.01)
            # if self.debug and angle % 90 == 0:
            #     self.screenshot(f'arrow_rotated_{angle}', arrow_template.mat)
            if target and target.confidence > max_conf:
                max_conf = target.confidence
                max_angle = angle
                max_target = target
                # max_mat = template
        # arrow_template.mat = original_mat
        # arrow_template.mask = None
        # if self.debug and max_mat is not None:
        #     self.screenshot('max_mat',frame=max_mat)
        # self.log_debug(f'turn_east max_conf: {max_conf} {max_angle}')
        return max_angle, max_target

    def get_mini_map_turn_angle(self, feature, threshold=0.72, x_offset=0, y_offset=0):
        box = self.get_box_by_name('box_minimap')
        target = self.find_one(feature, box=box, threshold=threshold)
        if not target:
            self.log_info(self.tr('Can not find {feature} on minimap').format(feature=feature))
            return None
        else:
            self.log_debug(f'found {box} on minimap')
        target.x += target.width * x_offset
        target.y += target.height * y_offset
        direction_angle = calculate_angle_clockwise(box, target)
        my_angle = self.get_my_angle()
        to_turn = self.get_angle_between(my_angle, direction_angle)
        self.log_info(self.tr('angle: {my_angle}, to_turn: {to_turn}').format(my_angle=my_angle, to_turn=to_turn))
        return to_turn

    def _stop_movement(self, current_direction):
        """Releases keys and mouse to stop character movement."""
        if current_direction is not None:
            self.mouse_up(key='right')
            self.send_key_up(current_direction)

    def _navigate_based_on_angle(self, angle, current_direction, current_adjust):
        """
        Core navigation logic to adjust movement based on a target angle.
        This contains the shared logic from the original functions.

        Returns a tuple: (new_direction, new_adjust, should_continue)
        - new_direction: The updated movement direction ('w', 'a', 's', 'd').
        - new_adjust: The updated adjustment state.
        - should_continue: A boolean indicating if the calling loop should `continue`.
        """
        # 1. Handle minor adjustments if already moving forward
        if current_direction == 'w':
            if 10 <= angle <= 80:
                minor_adjust = 'd'
            elif -80 <= angle <= -10:
                minor_adjust = 'a'
            else:
                minor_adjust = None

            if minor_adjust:
                self.send_key_down(minor_adjust)
                self.sleep(0.1)
                self.middle_click(down_time=0.1)
                self.send_key_up(minor_adjust)
                self.sleep(0.01)
                # Tell the caller to continue to the next loop iteration
                return current_direction, current_adjust, True

        # 2. Clean up any previous adjustments
        if current_adjust:
            self.send_key_up(current_adjust)
            current_adjust = None

        # 3. Determine the major new direction based on the angle
        if -45 <= angle <= 45:
            new_direction = 'w'
        elif 45 < angle <= 135:
            new_direction = 'd'
        elif -135 < angle <= -45:
            new_direction = 'a'
        else:
            new_direction = 's'

        # 4. Change direction if needed
        if current_direction != new_direction:
            self.log_info(self.tr('changed direction {angle} {current_direction} -> {new_direction}').format(angle=angle, current_direction=current_direction, new_direction=new_direction))
            if current_direction:
                self.mouse_up(key='right')
                self.send_key_up(current_direction)
                self.wait_until(self.in_combat, time_out=0.2)
            self.turn_direction(new_direction)
            self.send_key_down('w')
            self.wait_until(self.in_combat, time_out=0.2)
            self.mouse_down(key='right')
            current_direction = 'w'  # After turning, we always move forward
            self.wait_until(self.in_combat, time_out=1)

        return current_direction, current_adjust, False

    def android_team_size(self):
        """安卓端编队人数: 编队锁定/手填编队优先, 其次按已加载角色数, 默认 3 人队。

        不在战斗期间做画面 OCR 识别(用户要求): 技能特效/伤害数字会干扰
        队伍栏徽章识别, 造成误判。编队页配置几个人就是几人队。
        """
        identity = self.android_locked_team_identity()
        if identity:
            return len(identity)
        chars = getattr(self, 'chars', None) or []
        try:
            loaded = len([c for c in chars if c is not None])
        except Exception:
            loaded = 0
        if loaded >= 2:
            return min(loaded, 3)
        return 3

    # ---- 安卓编队锁定 (v1.5.13) --------------------------------------------

    def android_configured_team(self):
        """读取全局配置里手填的 'MuMu 编队', 返回 canonical 名元组或 None。

        支持中文名/英文名(如 绯雪,漂泊者·衍射,渊武 / Hiyuki,Rover: Spectro,Yuanwu),
        按编队槽位顺序填写, 2-3 人。填了就是唯一事实来源, 完全不做画面识别。
        """
        raw = ''
        try:
            cfg = getattr(self, 'android_config', None) or {}
            raw = str(cfg.get('MuMu 编队') or '')
        except Exception:
            raw = ''
        if not raw.strip():
            return None
        from src.char.CharFactory import resolve_char_alias
        names = []
        for token in raw.replace('，', ',').replace('、', ',').split(','):
            canonical = resolve_char_alias(self, token)
            if canonical is None:
                if token.strip():
                    self.log_warning(f'编队配置里的角色名无法识别: {token!r}, 忽略手填编队')
                return None
            names.append(canonical)
        if len(names) in (2, 3):
            return tuple(names)
        if names:
            self.log_warning(f'编队配置需要 2-3 个角色, 实际 {len(names)} 个, 忽略手填编队')
        return None

    def android_team_bar_snapshot(self):
        """把手游右上角队伍栏缩放到 PC 头像尺度(不做逐帧模板匹配的预处理)。

        手游圆形头像直径约 110px@1920x1080, 是 PC 头像(约 64px)的 1.7 倍,
        PC 头像模板(char_*)固定尺度直接匹配必然弱匹配。把队伍栏区域缩小
        ANDROID_TEAM_BAR_SCALE 倍后贴回同尺寸黑画布 —— 画布尺寸与主帧一致,
        避免触发 FeatureSet.check_size 清空特征缓存; 头像位置按缩小后实际
        坐标计算搜索框。

        返回 (画布, [每个槽位的搜索框 Box(画布坐标)])。识别失败返回 (None, [])。
        """
        frame = self.executor.nullable_frame()
        if frame is None:
            return None, []
        sw, sh = self.screen_width, self.screen_height
        x1, y1, x2, y2 = ANDROID_TEAM_BAR_BOX
        px1, py1 = int(x1 * sw), int(y1 * sh)
        px2, py2 = int(x2 * sw), int(y2 * sh)
        crop = frame[py1:py2, px1:px2]
        if crop.size == 0:
            return None, []
        scale = ANDROID_TEAM_BAR_SCALE
        small = cv2.resize(crop, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        canvas = np.zeros_like(frame)
        ch, cw = small.shape[:2]
        canvas[py1:py1 + ch, px1:px1 + cw] = small
        boxes = []
        half = int(40 * sh / 1080)  # 搜索框半径: 缩放后头像半径约 32px + 余量
        center_x = px1 + (0.909 * sw - px1) * scale
        for slot_y in ANDROID_CHAR_SLOT_CENTER_Y:
            center_y = py1 + (slot_y * sh - py1) * scale
            boxes.append(Box(center_x - half, center_y - half, half * 2, half * 2,
                             name='android_char_slot'))
        return canvas, boxes

    def android_detect_team_identity(self):
        """在缩放后的队伍栏画布上识别各槽位角色并投票。

        手游头像是"整个头部"圆形构图, PC 模板是"脸部特写"裁剪, 模板匹配天然
        不如 PC 端可靠(实测最高 0.7~0.9 且偶有张冠李戴), 因此:
          - 阈值提到 ANDROID_DETECT_THRESHOLD(0.72), 低于阈值的槽位记 None;
          - 投票锁定由 android_vote_team_identity 把关(连续一致才锁)。
        返回锁定/多数票身份元组(可含 None 槽位), 完全失败返回 None。
        """
        canvas, boxes = self.android_team_bar_snapshot()
        if canvas is None or not boxes:
            return None
        from src.char.CharFactory import char_names
        found = []
        for box in boxes:
            matched = self.find_best_match_in_box(box, char_names, ANDROID_DETECT_THRESHOLD,
                                                  frame=canvas)
            found.append(matched.name if matched else None)
        self.log_debug(f'android team bar detect: {found}')
        if not any(found):
            return None
        return self.android_vote_team_identity(tuple(found))

    def android_vote_team_identity(self, identity):
        """对一次识别结果投票; 连续一致达到阈值时锁定编队。

        - 已锁定时: 仅当最近 N 次投票连续一致且与锁定不同才换锁(自动跟随换队);
          战斗特效造成的偶发误读在连续一致门槛下无法撼动锁定。
        - 未锁定时: 连续一致达到阈值即锁定; 否则返回多数票兜底。
        """
        from collections import Counter, deque
        votes = getattr(self, '_android_team_votes', None)
        if votes is None:
            votes = deque(maxlen=ANDROID_TEAM_VOTE_WINDOW)
            self._android_team_votes = votes
        votes.append(identity)
        recent = list(votes)[-ANDROID_TEAM_LOCK_MIN_VOTES:]
        stable = len(recent) >= ANDROID_TEAM_LOCK_MIN_VOTES and all(
            v == recent[0] for v in recent)
        lock = getattr(self, '_android_team_lock', None)
        if stable and recent[0] is not None and any(recent[0]):
            if recent[0] != lock:
                from src.char.CharFactory import canonical_display_name
                shown = ', '.join(canonical_display_name(n) for n in recent[0])
                message = f'安卓编队锁定: {shown}'
                if lock:
                    message += f' (原: {", ".join(canonical_display_name(n) for n in lock)})'
                self.log_info(message)
            self._android_team_lock = recent[0]
            self._android_team_recheck_at = time.time()
            return recent[0]
        if lock is not None:
            return lock
        counts = Counter(v for v in votes if v and any(v))
        if counts:
            return counts.most_common(1)[0][0]
        return None

    def android_locked_team_identity(self):
        """当前生效的编队身份: 手填配置 > 投票锁定。

        锁定已存在且明确不在战斗中(scene.in_combat is False)时, 每
        ANDROID_TEAM_RECHECK_INTERVAL 秒复检一次, 用户换队后自动重锁(自恢复);
        战斗中或战斗状态未知时完全不复检(用户要求战斗期间不识别)。
        """
        configured = self.android_configured_team()
        if configured:
            return configured
        lock = getattr(self, '_android_team_lock', None)
        if lock is None:
            return None
        scene = getattr(self, 'scene', None)
        if scene is None or scene.in_combat is not False:
            return lock  # 战斗中/状态未知: 绝不识别(用户要求)
        now = time.time()
        if now - getattr(self, '_android_team_recheck_at', 0) < ANDROID_TEAM_RECHECK_INTERVAL:
            return lock
        self._android_team_recheck_at = now
        self.log_debug('android team lock recheck')
        self.android_detect_team_identity()
        return getattr(self, '_android_team_lock', None)

    def android_build_chars_from_identity(self, identity, current_index):
        """按编队身份直接构建角色列表(不做画面识别), 返回是否成功。

        身份元组里允许 None 槽位(该槽保留旧角色对象), 但至少要能构建 2 个角色。
        """
        from src.char.CharFactory import build_char_by_canonical
        if not identity:
            return False
        old_chars = list(getattr(self, 'chars', None) or [None, None, None])
        built = []
        for i, canonical in enumerate(identity):
            built.append(build_char_by_canonical(self, canonical, i, safe_get(old_chars, i)))
        if len([c for c in built if c is not None]) < 2:
            return False
        self.chars = built
        return True

    def android_switch_key(self, index, exclude=()):
        """安卓端按编队槽位取实际切换键; PC/云仍用 index+1 的原有约定。

        MuMu 只有 1/2 两颗切换键, 分别绑在编队中两个非出战队友的按钮上。
        以配置的编队为准, 不做战斗中的画面识别(用户要求), 按实测规律推导:
        键 1 -> 编队靠后的非出战队友(实测出战 3 号位时键 1 切 2 号位),
        键 2 -> 编队靠前的。exclude 里的键是本轮切人已按过但没生效的,
        跳过后自动换另一颗键。任何路径都不会返回 3 —— 模拟器上没有这个键。
        """
        if not self.is_adb():
            return str(index + 1)
        team_size = self.android_team_size()
        current = getattr(self, '_android_current_index', 0)
        if not isinstance(current, int) or not 0 <= current < team_size:
            current = 0
        others = [i for i in range(team_size) if i != current]
        if index in others and len(others) <= len(ANDROID_SWITCH_KEYS):
            first = '1' if index == max(others) else '2'
            second = '2' if first == '1' else '1'
            for k in (first, second):
                if k not in exclude:
                    return k
            return first
        return str(index + 1)

    def in_team(self):
        # 安卓端(ADB/模拟器)队伍栏是圆形头像, 没有 PC 端的 1/2/3 数字徽章,
        # char_N_text 模板永远匹配不上(实测置信度仅 0.11~0.15), 会让
        # in_team_and_world() 恒为 False -> is_main() 恒为 False ->
        # ensure_main() 一直等到 600 秒超时, 表现为"卡住不动且没有日志"。
        # 安卓端改用与角色无关的 HUD 元素判定(小地图雷达黄色玩家箭头等)。
        if self.is_adb():
            return self.in_team_android()

        c1 = self.find_one('char_1_text',
                           threshold=0.8)
        c2 = self.find_one('char_2_text',
                           threshold=0.8)
        c3 = self.find_one('char_3_text',
                           threshold=0.8)
        arr = [c1, c2, c3]
        # logger.debug(f'in_team check {arr}')
        current = -1
        exist_count = 0
        for i in range(len(arr)):
            if arr[i] is None:
                if current == -1:
                    current = i
            else:
                exist_count += 1
        if exist_count == 2 or exist_count == 1:
            self.logged_in = True
            return True, current, exist_count + 1
        else:
            # 三个模板全落空时原先完全静默, 排查时看不到任何线索;
            # 这里把每个模板的实际置信度打出来。
            self.log_debug(f'in_team: no char_N_text matched (c1={c1}, c2={c2}, c3={c3})')
            return False, -1, exist_count + 1

    def in_team_android(self):
        """安卓端"在大世界且在队伍中"判定。

        安卓客户端右上角队伍栏是**圆形角色头像, 没有数字徽章**, PC 端的
        char_N_text 模板在这里永远匹配不上, 因此安卓端改用与角色无关的
        HUD 元素判断(详见 src/task/android_world.py):
          - 左上角小地图雷达里的黄色玩家箭头
          - 底部中央的共鸣者血条 / 大招能量球
          - 右侧队伍栏的白色血条

        返回值与 PC 端 in_team() 保持同构: (是否在队伍, 当前角色下标, 队伍人数)。
        """
        frame = self.executor.nullable_frame()
        if frame is None:
            self.log_debug('in_team(android): no frame available')
            return False, -1, 1

        in_world, reason = android_world.in_android_world(frame)
        if not in_world:
            if reason == 'black_frame':
                # MuMu 的 IPC 截图偶尔返回纯黑图, 此时任何模板匹配都不会命中,
                # 表现和"不在大世界"一样。这里必须明确区分, 否则排查方向会被带偏。
                self.log_warning(self.tr(
                    '安卓端截图全黑(MuMu 抓屏失败), 无法判定是否在大世界。'))
            else:
                self.log_debug(f'in_team(android): not in world ({reason})')
            return False, -1, 1

        self.logged_in = True
        # 以配置的编队为准, 不在战斗期间做画面 OCR 识别(用户要求):
        # 战斗中技能特效/伤害数字会干扰队伍栏徽章识别, 造成误判。
        # 队伍人数按编队(android_team_size), 当前角色用脚本维护的逻辑
        # 下标(切人时由 switch_next_char 推进)。
        team_size = self.android_team_size()
        current_index = getattr(self, '_android_current_index', 0)
        if not isinstance(current_index, int) or not 0 <= current_index < team_size:
            current_index = 0
        self._android_current_index = current_index
        self.log_debug(
            f'in_team(android): in world ({reason}), team_size={team_size}, current={current_index}')
        return True, current_index, team_size

        # Function to check if a component forms a ring

    def find_monthly_card(self):
        return self.find_one('monthly_card', threshold=0.65, horizontal_variance=0.05, vertical_variance=0.05)

    def handle_monthly_card(self):
        # MONTHLY CARD FALSE POSITIVE GUARD: 月卡弹窗只会在两个时机出现 —— 登录阶段
        # (logged_in=False) 和每日月卡时间窗口 (should_check_monthly_card()=True)。
        # 任务中途(已登录、非月卡时间)被 is_main 调用时, 全屏低阈值模板会把邮箱奖励
        # 等圆形图标误判成月卡, 点击后 is_main 提前 return 使 back() 不执行、邮箱关不掉,
        # ensure_main 超时抛异常 -> 错误恢复反复重启(死循环)。此时直接跳过检测。
        if getattr(self, 'logged_in', True) and not self.should_check_monthly_card():
            return False
        # 登录阶段的场景误报(角色/场景酷似弹窗模板)会让 is_main 一直 return False
        # 而永远走不到 back()/菜单键, 卡死在 "wait main esc=True"。连续 3 次
        # "检测到月卡却没回到大世界" 就认定误报, 本次运行跳过检测, 让 is_main 继续走 esc。
        if getattr(self, '_monthly_card_claim_failed', 0) >= 3:
            return False
        monthly_card = self.find_monthly_card()
        entered = False
        # self.screenshot('monthly_card1')
        if monthly_card is not None:
            # self.screenshot('monthly_card1')
            self.log_info(self.tr('monthly_card found click'))
            self.click_relative(0.50, 0.89)
            self.sleep(2)
            # self.screenshot('monthly_card2')
            self.click_relative(0.50, 0.89)
            self.sleep(2)
            entered = self.wait_until(self.in_team_and_world, time_out=10,
                            post_action=lambda: self.click_relative(0.50, 0.89, after_sleep=1))
            # self.screenshot('monthly_card3')
            # 只有确认领完月卡回到大世界才把检查推到明天; 否则视为误判, 保留检查以便真正领取。
            if entered:
                self.set_check_monthly_card(next_day=True)
                self._monthly_card_claim_failed = 0
            else:
                self._monthly_card_claim_failed = getattr(self, '_monthly_card_claim_failed', 0) + 1
                if self._monthly_card_claim_failed >= 3:
                    self.log_info(self.tr('monthly_card detected but claim failed repeatedly, skip this run'))
        # 返回值改为"确实领完回到大世界": 仅检测到模板(可能是误报)不再让 is_main 短路,
        # 这样 is_main 会继续走 esc/back, 不会卡在 wait main。
        return monthly_card is not None and entered

    @property
    def game_lang(self):
        if '鸣潮' in self.hwnd_title or self.is_browser():
            return 'zh_CN'
        elif 'Wuthering' in self.hwnd_title:
            return 'en_US'
        elif '鳴潮' in self.hwnd_title:
            return 'zh_TW'
        return 'unknown_lang'

    def open_esc_menu(self):
        if self.touch.is_touch:
            # 安卓端返回/打开菜单是同一个按钮(KEYCODE_BACK); PC 的 Alt+点击在触屏上无效。
            self.touch.open_menu(after_sleep=0.5)
            return
        self.send_key_down('alt')
        self.sleep(0.05)
        self.click_relative(0.95, 0.04)
        self.send_key_up('alt')
        self.sleep(0.5)

    def open_boss_book(self, name, after_sleep=2):
        self.log_info(self.tr('open_boss_book {name}').format(name=name))
        x = 0.24
        self.sleep(0.4)
        if name == 'ningsu':
            y = 0.4
        elif name == 'moni':
            y = 0.3
        elif name == 'qiangdi':
            y = 0.49
        elif name == 'wuyin':
            y = 0.73
        elif name == 'zhange':
            y = 0.61
        elif name == 'canxiang':
            y = 0.83
        elif name == 'mengyan':
            self.click_relative(0.356, 0.882, after_sleep=after_sleep)
            y = 0.86
        else:
            raise Exception(self.tr('unknown_lang {name}').format(name=name))
        self.click_relative(x, y, after_sleep=after_sleep, name=name)

    def openF2Book(self, feature="gray_book_all_monsters"):
        if hasattr(self, 'reset_to_false'):
            self.reset_to_false('opening book')
        self.ensure_main()
        if self.touch.is_touch:
            # 安卓触屏没有 F2 键: 一律点右上角"索拉指南"图标(方框书本)。
            # 这里绝不能回落到 send_key('f2') —— 安卓端发 F2 什么也不会发生,
            # 只会白等 wait_book 超时然后抛"make sure f2 is the hotkey for book"。
            self.log_info(self.tr('click guidebook icon (touch) to open the book'))
            self.open_touch_book()
        else:
            book_key = self.key_config.get('Guidebook Key', self.key_config.get('索拉指南', 'f2'))
            self.log_info(self.tr('click {book_key} to open the book').format(book_key=book_key))
            if self.in_team_and_world():
                self.send_key(book_key, after_sleep=4)
                self.log_info(self.tr('send {book_key} key to open').format(book_key=book_key))
            if self.in_team_and_world():
                self.log_info(self.tr('send f2 key mouse key to open the book'))
                self.send_key_down('alt')
                self.sleep(0.05)
                self.click_relative(0.77, 0.05)
                self.sleep(0.02)
                self.send_key_up('alt')
                self.sleep(4)
        gray_book_boss = self.wait_book(feature)
        if not gray_book_boss:
            self.log_error(self.tr("can't find gray_book_boss, make sure f2 is the hotkey for book"), notify=True)
            raise Exception(self.tr("can't find gray_book_boss, make sure f2 is the hotkey for book"))
        self.sleep(2)
        self.click_box(gray_book_boss, after_sleep=1.5)
        return gray_book_boss

    def open_touch_book(self, time_out=20):
        """安卓端打开索拉指南: 点右上角图标栏里的方框书本图标(取代 PC 的 F2 键)。

        移动端打开指南书要 1~3 秒, 点完立刻判断常常会误判成"没打开", 于是脚本
        会反复点那个图标(点一下关掉、再点一下打开), 书的状态来回翻, 后面所有
        点击都落在错误的位置。所以这里改成: 先看是不是已经开着, 没开才点;
        点完给几秒钟等它开出来。

        点完会确认左列是否出现竖排类别图标; 没出现就再点一次 ——
        书本来就开着时再点图标反而会把它关掉, 所以必须靠确认决定要不要补点。
        """
        deadline = time.time() + time_out
        while True:
            if self.touch_book_opened():
                self.log_debug('touch book opened')
                return True
            self.click_relative(*TOUCH_BOOK_CLICK, after_sleep=1)
            if self.wait_until(self.touch_book_opened, time_out=4, settle_time=0.5,
                               raise_if_not_found=False):
                self.log_debug('touch book opened')
                return True
            if time.time() >= deadline:
                self.log_warning(self.tr('安卓端未能打开索拉指南(右上角图标点击无响应)'))
                return False
            self.sleep(1)

    def touch_book_opened(self):
        """安卓端索拉指南是否已打开(左列是否出现竖排类别图标)。"""
        frame = self.executor.nullable_frame()
        if frame is None:
            return False
        try:
            return android_book.is_book_opened(frame, templates=self.android_book_templates())
        except Exception as e:
            self.log_debug(f'touch_book_opened failed: {e}')
            return False

    def android_book_templates(self):
        """安卓索拉指南左列的类别图标模板(PC 模板, 用于笔画 IoU 配对)。"""
        templates = []
        for feature in ANDROID_BOOK_TAB_FEATURES:
            template = self.get_feature_template(feature)
            if template is not None:
                templates.append(template)
        return templates

    def find_android_book_tab(self, feature='gray_book_quest'):
        """在安卓索拉指南左列里定位指定类别图标。

        安卓端的索拉指南是移动端布局, 类别图标与 PC 模板尺寸/位置都不同,
        直接用 PC 模板做 NCC 会命中背景空白(见 src/task/android_book.py),
        因此改用笔画掩码 + 多尺度 IoU 配对。
        """
        frame = self.executor.nullable_frame()
        if frame is None:
            self.log_debug('find_android_book_tab: no frame available')
            return None
        template = self.get_feature_template(feature)
        if template is None:
            self.log_debug(f'find_android_book_tab: template {feature} not found')
            return None
        hit = android_book.find_book_tab(frame, template)
        if hit is None:
            self.log_debug(f'find_android_book_tab: {feature} not matched in the left column')
            return None
        x, y, width, height, score = hit
        self.log_debug(f'find_android_book_tab: {feature} @ ({x},{y}) iou={score:.3f}')
        return Box(x=x - width // 2, y=y - height // 2, width=width, height=height,
                   confidence=score, name=feature)

    def get_feature_template(self, feature):
        """取某个模板的原始图片(BGR), 拿不到返回 None。"""
        feature_set = getattr(self.executor, 'feature_set', None)
        if feature_set is None or not feature:
            return None
        try:
            feature_set.ensure_feature(feature)
            item = feature_set.feature_dict.get(feature)
        except Exception as e:
            self.log_debug(f'get_feature_template({feature}) failed: {e}')
            return None
        if item is None:
            return None
        return getattr(item, 'mat', None)

    def open_activity(self, after_sleep=4):
        """打开活动面板(PC 端为 F1 键)。

        安卓触屏端没有 F1, 改为点右上角图标栏里索拉指南图标左边的"活动"图标。
        """
        if self.touch.open_activity(after_sleep=after_sleep):
            self.log_info(self.tr('click activity icon (touch) to open the event panel'))
            return True
        activity_key = self.key_config.get('Activity Key', self.key_config.get('活动', 'f1'))
        self.log_info(self.tr('click {activity_key} to open the event panel').format(activity_key=activity_key))
        self.send_key(activity_key, after_sleep=after_sleep)
        return False

    def click_traval_button(self):
        for feature_name in ['fast_travel_custom', 'gray_teleport', 'remove_custom']:
            if self.find_one(feature_name, threshold=0.7):
                self.sleep(0.5)
                feature = self.find_one(feature_name, threshold=0.7)
                if not feature:
                    continue
                self.click(feature, after_sleep=1)
                if feature.name == 'fast_travel_custom':
                    if confirm := self.wait_feature(
                            ['confirm_btn_hcenter_vcenter', 'confirm_btn_highlight_hcenter_vcenter'],
                            raise_if_not_found=False,
                            threshold=0.6,
                            time_out=2):
                        self.click(0.49, 0.55, after_sleep=0.5)  # 点击不再提醒
                        self.click(confirm, after_sleep=0.5)
                        self.click_confirm()
                if feature.name != 'remove_custom':
                    self.wait_click_skip_dialog_confirm()
                return True

    def find_travel_button(self, threshold=0.7):
        """定位「传送」按钮。

        先用 PC 模板(fast_travel_custom / gray_teleport / remove_custom);
        模板匹配不上时(云游戏/移动端的"快速旅行"按钮)退回 OCR 认字。

        :return: Box(名称是模板名或 OCR 文字); 找不到返回 None
        """
        for feature_name in ('fast_travel_custom', 'gray_teleport', 'remove_custom'):
            if box := self.find_one(feature_name, threshold=threshold):
                return box
        return self.find_travel_button_by_ocr()

    def find_travel_button_by_ocr(self):
        """OCR 找「快速旅行」按钮(右侧详情页底部的黑底白字按钮)。"""
        for box in self.ocr(*TRAVEL_BUTTON_SEARCH_BOX, match=list(TRAVEL_BUTTON_TEXTS)):
            self.log_debug(f'travel button by ocr: {box}')
            return box
        return None

    def find_confirm_button(self, threshold=0.6):
        """定位弹窗里的确认按钮: 先用 PC 模板, 再用 OCR 认「确认/确定」。"""
        for feature_name in ('confirm_btn_hcenter_vcenter', 'confirm_btn_highlight_hcenter_vcenter'):
            if box := self.find_one(feature_name, threshold=threshold):
                return box
        return self.find_confirm_button_by_ocr()

    def find_confirm_button_by_ocr(self):
        """OCR 找弹窗里的「确认/确定」按钮。"""
        for box in self.ocr(*CONFIRM_BUTTON_SEARCH_BOX, match=list(CONFIRM_BUTTON_TEXTS)):
            self.log_debug(f'confirm button by ocr: {box}')
            return box
        return None

    def click_confirm(self, timeout=1):
        self.wait_click_feature(
            ['confirm_btn_hcenter_vcenter', 'confirm_btn_highlight_hcenter_vcenter'],
            relative_x=-1, raise_if_not_found=False,
            threshold=0.6,
            time_out=1)

    def click_skip_dialog_confirm(self):
        skip_dialog_confirm = self.find_one(
            ['confirm_btn_hcenter_vcenter', 'confirm_btn_highlight_hcenter_vcenter'],
            horizontal_variance=0.1,
            vertical_variance=0.1,
        )
        if not skip_dialog_confirm:
            return False

        skip_dialog_check = self.find_one(
            'skip_dialog_check',
            horizontal_variance=0.1,
            vertical_variance=0.1,
        )
        if not skip_dialog_check:
            check_feature = self.get_feature_by_name('skip_dialog_check')
            wide_check_template = cv2.resize(
                check_feature.mat,
                (0, 0),
                fx=WIDE_MODE_UI_SCALE,
                fy=WIDE_MODE_UI_SCALE,
                interpolation=cv2.INTER_AREA,
            )
            skip_dialog_check = self.find_one(
                'skip_dialog_check',
                box=self.box_of_screen(0.35, 0.45, 0.55, 0.65),
                template=wide_check_template,
            )
        if not skip_dialog_check:
            return False

        logger.info('confirm dialog exists, click confirm')
        self.sleep(0.5)
        self.click(skip_dialog_check)
        self.sleep(0.5)
        self.click(skip_dialog_confirm)
        self.sleep(0.2)
        return True

    def wait_click_skip_dialog_confirm(self, time_out=3):
        return self.wait_until(
            self.click_skip_dialog_confirm,
            time_out=time_out,
            raise_if_not_found=False,
        )

    def click_team_challenge(self):
        self.wait_click_feature('team_start_challenge', raise_if_not_found=True, click_after_delay=0.5, after_sleep=1)
        self.wait_click_skip_dialog_confirm()

    def wait_click_travel(self):
        self.wait_until(self.click_traval_button, raise_if_not_found=True, time_out=10)

    def wait_book(self, feature="gray_book_all_monsters", time_out=3):
        if self.touch.is_touch:
            # 安卓端索拉指南是移动端布局, PC 的 gray_book_* 模板定位不到
            # (实测 NCC 全部命中背景空白), 改用笔画掩码 + 多尺度 IoU 配对。
            gray_book_boss = self.wait_until(
                lambda: self.find_android_book_tab(feature),
                time_out=time_out, settle_time=1)
            logger.info(f'found {feature} {gray_book_boss}')
            return gray_book_boss
        gray_book_boss = self.wait_until(
            lambda: self.find_one(feature, box='box_gray_book',
                                  threshold=0.3),
            time_out=time_out, settle_time=1)
        logger.info(f'found gray_book_boss {gray_book_boss}')
        # if self.debug:
        #     self.screenshot(feature)
        return gray_book_boss

    def check_main(self):
        if not self.in_team()[0]:
            self.click_relative(0, 0)
            self.send_key('esc')
            self.sleep(1)
            if not self.in_team()[0]:
                raise Exception(self.tr('must be in game world and in teams'))
        return True

    def _find_book_scroll_top(self):
        box = self.box_of_screen(0.969, 0.191, 0.978, 0.271, name="bar")
        self.draw_boxes(boxes=box, color="blue")
        min_width = self.width_of_screen(5 / 2560)
        min_height = self.height_of_screen(10 / 1440)
        boxes = find_color_rectangles(self.frame, book_bar_color, min_width, min_height, threshold=0.8, box=box)
        if not boxes:
            return 424 / 2160
        bar = boxes[0]
        self.draw_boxes(boxes=bar, color="red")
        return bar.y / self.height

    def click_on_book_target(self, serial_number: int, total_number: int, structure: list[int] = None):
        def get_cross_count(structure, sn):
            current_sum = 0
            cross_count = 0
            for s in structure:
                current_sum += s
                if sn > current_sum:
                    cross_count += 1
                else:
                    break
            return cross_count

        self.sleep(0.5)
        bar_bottom = 0.8806
        bar_x = 0.9730
        header_h = 0.028  # calibrated header height (~40px @1440), replaces separator=0.01
        cross_count = 0
        container_max_rows = 4
        target_index = -1

        bar_top = self._find_book_scroll_top()

        if serial_number <= container_max_rows:
            target_index = serial_number - 1
        else:
            calib_cross = get_cross_count(structure, serial_number) if structure else 0
            calib_container_h = (bar_bottom - bar_top - (len(structure) - 1) * header_h) if structure else (
                        bar_bottom - bar_top)
            calib_item_h = calib_container_h / total_number if total_number else 0
            calib_y = min(bar_top + calib_item_h * serial_number + calib_cross * header_h, bar_bottom)
            to_click_y = calib_y
            item_h = calib_item_h
            self.click(bar_x, to_click_y, after_sleep=1)
        btns = self.find_feature('boss_proceed', box=self.box_of_screen(0.9113, 0.229, 0.9613, 0.861), threshold=0.8)
        # adaptive retry: closed-loop correction for residual underscroll (found 3/4 with low max_y)
        if not target_index > -1 and btns and len(btns) in (3, 4) and structure and serial_number > container_max_rows:
            max_y = max(b.y / self.height for b in btns)
            if max_y < 0.73:
                retry_y = min(to_click_y + item_h * 0.55, bar_bottom) if 'item_h' in locals() and item_h else min(
                    to_click_y + 0.018, bar_bottom)
                self.click(bar_x, retry_y, after_sleep=1)
                btns = self.find_feature('boss_proceed', box=self.box_of_screen(0.9113, 0.229, 0.9613, 0.861),
                                         threshold=0.8)
        if not btns:
            raise Exception(self.tr("can't find boss_proceed"))
        if target_index > -1:
            if target_index < len(btns):
                target = btns[target_index]
            else:
                # Fallback: not enough visible rows, scroll with calibrated header
                calib_cross2 = get_cross_count(structure, serial_number) if structure else 0
                calib_h2 = (bar_bottom - bar_top - (len(structure) - 1) * header_h) if structure else (
                            bar_bottom - bar_top)
                calib_y2 = min(bar_top + (calib_h2 / total_number) * serial_number + calib_cross2 * header_h,
                               bar_bottom) if total_number else bar_bottom
                self.click(bar_x, calib_y2, after_sleep=1)
                btns = self.find_feature('boss_proceed', box=self.box_of_screen(0.9113, 0.229, 0.9613, 0.861),
                                         threshold=0.8)
                if not btns:
                    raise Exception(self.tr("can't find boss_proceed after scroll"))
                target = max(btns, key=lambda box: box.y)
        else:
            target = max(btns, key=lambda box: box.y)
        self.draw_boxes(boxes=target, color="red")
        self.click(target, after_sleep=1)
        feature = self.wait_feature(['fast_travel_custom', 'gray_teleport', 'remove_custom', *TEAM_SCREEN_FEATURES],
                                    time_out=10, settle_time=0.5, raise_if_not_found=True)
        return feature.name in TEAM_SCREEN_FEATURES

    def change_time_to_night(self):
        logger.info('change time to night')
        self.send_key("esc")
        self.sleep(1)
        self.click_relative(0.71, 0.96)
        self.sleep(2)
        self.click_relative(0.19, 0.14)
        self.sleep(1)

        # 调整时间到晚上
        for _ in range(3):
            self.click_relative(0.82, 0.53)
            self.sleep(1)

        self.click_relative(0.52, 0.90)
        self.sleep(6)
        self.send_key("esc")
        self.sleep(1)
        self.send_key("esc")
        self.sleep(1)

    def jump(self, after_sleep=0.01):
        self.send_key(self.key_config.get('Jump Key'), after_sleep=after_sleep)


book_bar_color = {
    "r": (190, 255),
    "g": (190, 255),
    "b": (190, 255),
}

echo_color = {
    'r': (200, 255),  # Red range
    'g': (150, 220),  # Green range
    'b': (130, 170)  # Blue range
}


def calculate_angle_clockwise(box1, box2):
    """
    Calculates angle (radians) from horizontal right to line (x1,y1)->(x2,y2).
    Positive clockwise, negative counter-clockwise.
    """
    x1, y1 = box1.center()
    x2, y2 = box2.center()
    dx = x2 - x1
    dy = y2 - y1
    # math.atan2(dy, dx) gives angle from positive x-axis, positive CCW.
    # Negate for positive CW convention.

    degree = math.degrees(math.atan2(dy, dx))
    if degree < 0:
        degree += 360
    return degree


lower_white = np.array([244, 244, 244], dtype=np.uint8)
lower_white_none_inclusive = np.array([240, 240, 240], dtype=np.uint8)
upper_white = np.array([255, 255, 255], dtype=np.uint8)
black = np.array([0, 0, 0], dtype=np.uint8)


def isolate_white_text_to_black(cv_image):
    """
    Converts pixels in the near-white range (244-255) to black,
    and all others to white.
    Args:
        cv_image: Input image (NumPy array, BGR).
    Returns:
        Black and white image (NumPy array), where matches are black.
    """
    match_mask = cv2.inRange(cv_image, black, lower_white_none_inclusive)
    output_image = cv2.cvtColor(match_mask, cv2.COLOR_GRAY2BGR)

    return output_image


def convert_bw(cv_image):
    match_mask = cv2.inRange(cv_image, lower_white, upper_white)
    output_image = cv2.cvtColor(match_mask, cv2.COLOR_GRAY2BGR)
    return output_image


lower_icon_white = np.array([210, 210, 210], dtype=np.uint8)
upper_icon_white = np.array([255, 255, 255], dtype=np.uint8)


def convert_dialog_icon(cv_image):
    match_mask = cv2.inRange(cv_image, lower_icon_white, upper_icon_white)
    output_image = cv2.cvtColor(match_mask, cv2.COLOR_GRAY2BGR)
    return output_image


def isolate_gua_strokes(image):
    """
    Keeps the white strokes of Buling's hexagram glyphs (卦象 艮/震) and drops the colored halo behind them.

    A pixel's minimum channel is only high when the pixel is close to white, and the top-hat keeps thin
    bright strokes while removing the smooth glow, so plain and highlighted glyphs look the same.

    Args:
        image (np.array): The input BGR image from OpenCV.

    Returns:
        np.array: Single channel 8-bit stroke map.
    """
    gray = image.min(axis=2) if image.ndim == 3 else image
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (9, 9))
    return cv2.morphologyEx(gray, cv2.MORPH_TOPHAT, kernel)


def binarize_for_matching(image, threshold=244):
    """
    Converts a colored image to a binary image based on a brightness threshold.

    The rule is: pixels with a value of 240-255 become pure white (255),
    and all other pixels become pure black (0).

    Args:
        image (np.array): The input BGR image from OpenCV.

    Returns:
        np.array: The resulting binary image (single channel, 8-bit).
    """
    # Convert the image to grayscale for a single brightness value per pixel.
    # This is more robust than checking individual R, G, B channels.

    gray_image = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)

    # Apply the binary threshold.
    # Pixels > 239 will be set to 255 (white).
    # Pixels <= 239 will be set to 0 (black).
    # cv2.THRESH_BINARY is the type of thresholding we want.
    _, binary_image = cv2.threshold(gray_image, threshold, 255, cv2.THRESH_BINARY)
    return binary_image
