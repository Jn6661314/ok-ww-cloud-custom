"""
安卓触屏(ADB / MuMu / 雷电等模拟器)专用操作模式层。

设计原则(重要):
  安卓端的「返回」和「打开菜单」是同一个按钮, 就是键位表里的"菜单/跳过"键 —— 反引号 `。
  触屏鸣潮用 ` (KEYCODE_GRAVE) 打开/关闭菜单、退回上一级; 它不响应 PC 的 esc /
  系统 KEYCODE_BACK —— 实测主界面发 KEYCODE_BACK 弹的是"是否确定退出游戏", 并非返回/菜单。
  因此本模式把触屏的 back()/open_menu() 统一绑定到键位表里的 `, 不拆成两个键。

  PC / 云游戏行为完全不变: 它们仍走各自的 back()(PC=esc, 云=浏览器 esc)。

本模块把原先散落在各 task 里的 is_adb()/is_browser() 判断和触屏键位
集中到一处, 对外提供语义化入口:
  - is_touch / is_cloud : 当前设备模式判定
  - back() / open_menu(): 返回=打开菜单(同一个按钮, 触屏为键位表的 ` -> KEYCODE_GRAVE)
  - open_book()         : 指南书(投屏可校准 F2 触点; 其余触屏点右上角图标; PC 走 F2)
  - open_activity()     : 活动面板(触屏直接点右上角活动图标, 其余走按键 F1)
  - mapped_key()        : 投屏下某个语义键有没有自定义触点(f_break / f2)

以后要调整触屏键位或某个操作的触屏手法, 只改这一处, 不用再翻遍每个 task。
"""

import time

# 触屏语义键位(统一在 ADB_KEY_MAP 里映射成合法 KEYCODE_*)。
# 键位表: [ ` ] = 菜单/跳过; 触屏的返回与打开菜单是同一个按钮, 就是它。
TOUCH_MENU_BACK_KEY = '`'  # -> ADB_KEY_MAP -> KEYCODE_GRAVE (返回 = 打开菜单 = 菜单/跳过键)

# 投屏下 back 的"刹车": 手游没有稳定的返回键, back 点的是右上角(面板里是 X,
# 大世界里是设置/头像)。一旦"是否在大世界"判错, ensure_main 会每 2 秒点一次,
# 表现为"一直在按返回菜单", 而且点开的面板会层层叠加。这里限制窗口内的次数,
# 超出就停止发触点并告警, 让上层超时报错, 而不是无限乱点。
BACK_STORM_WINDOW = 10.0
BACK_STORM_LIMIT = 5

# ---------------------------------------------------------------------------
# 右上角图标栏(1920x1080 基准)。实测大世界右上角有 6 个图标, 从左到右:
#   #1 活动(音叉状)  #2 索拉指南(方框书本)  #3 罗盘  #4 相机  #5 头像  #6 设置
# 触屏端没有 F1/F2 键, 改点图标:
#   F1(活动)     -> #1
#   F2(索拉指南) -> #2
# 坐标: 索拉指南取用户在 MuMu 截图上的标注 (932,44)/(1278,719) -> (0.7293,0.0612);
#       活动取同一栏实测的图标中心 (1308,65)/(1920,1080) -> (0.6813,0.0602)。
# ---------------------------------------------------------------------------
TOUCH_ACTIVITY_CLICK = (0.6813, 0.0602)
TOUCH_BOOK_CLICK = (0.7293, 0.0612)
# 手游指南书/面板右上角的关闭 X（实测 (2199,60)/(2376,1080)）。
# 用户把菜单/返回键校准到了指南书图标附近，靠它关面板会关不掉，
# 所以投屏下优先点这个固定的 X。
TOUCH_PANEL_CLOSE_CLICK = (0.925, 0.056)


class TouchMode:
    """按设备模式分发语义操作的轻量助手, 由 BaseWWTask 持有(self.touch)。"""

    def __init__(self, task):
        self.task = task
        self._back_times = []
        self._back_storm_warned = False

    @property
    def is_touch(self):
        """当前是否走触屏键位(安卓模拟器/手机投屏, 且输入通道是触屏式)。

        注意: 若配置成"像 PC 一样给模拟器窗口发键盘消息"(PostMessage/Pynput 等
        窗口消息交互), esc 本身就是 PC 语义, 不做触屏改写 —— 只有真正把输入
        变成触点的通道(ADB `input keyevent` / 投屏内核的触点注入)才把 esc
        语义换成键位表的 ` 键。

        手机投屏(内置引擎)也算触屏: 手游不认 esc / KEYCODE_BACK, 按下去只会弹
        "是否退出游戏"; 它的返回/菜单同样要用键位表的 ` —— 由
        ``src/phone_mirror_keymap`` 翻译成那个位置的触点。
        """
        try:
            if not self.task.is_adb():
                return False
            interaction = getattr(self.task.executor, 'interaction', None)
            if interaction is None:
                return True
            from ok.device.interaction_methods.adb import ADBInteraction
            if isinstance(interaction, ADBInteraction):
                return True
            from ok.device.interaction_methods.phone_mirror import PhoneMirrorInteraction
            return isinstance(interaction, PhoneMirrorInteraction)
        except Exception:
            try:
                return bool(self.task.is_adb())
            except Exception:
                return False

    @property
    def is_phone_mirror(self):
        """当前输入是否来自手机投屏(内置引擎)的触点通道。

        和 is_touch 的区别: MuMu/ADB 也走触屏语义, 但它有自己的键位映射, 不读
        ``configs/phone_mirror_keymap.json``。只有投屏才用那张自定义表。
        """
        try:
            from ok.device.interaction_methods.phone_mirror import PhoneMirrorInteraction
            return isinstance(getattr(self.task.executor, 'interaction', None), PhoneMirrorInteraction)
        except Exception:
            return False

    def mapped_key(self, key):
        """投屏下这个键是否已校准成独立触点; 是则返回键名, 否则 None。

        PC / MuMu 不认识 f_break 这种语义键, 调用方只在拿到非 None 时才改走它,
        没校准就保持原来的按键/点击逻辑, 不破坏已有行为。
        """
        if not self.is_phone_mirror:
            return None
        try:
            from src import phone_mirror_keymap as keymap
            return key if keymap.lookup(key) is not None else None
        except Exception:
            return None

    @property
    def is_cloud(self):
        """当前是否为云游戏浏览器设备。"""
        try:
            return bool(self.task.is_browser())
        except Exception:
            return False

    def back(self, after_sleep=0):
        """返回/关闭一层。触屏用键位表的菜单/跳过键 `; PC/云维持原 back()(esc)。"""
        if self.is_touch:
            if self.is_phone_mirror and not self._back_allowed():
                return False
            self.task.send_key(TOUCH_MENU_BACK_KEY, after_sleep=after_sleep)
        else:
            self.task.back(after_sleep=after_sleep)

    def _back_allowed(self):
        """投屏下 back 的节流: 窗口内超过上限就拦下(见 BACK_STORM_* 注释)。"""
        now = time.time()
        self._back_times = [t for t in self._back_times if now - t < BACK_STORM_WINDOW]
        if len(self._back_times) >= BACK_STORM_LIMIT:
            if not self._back_storm_warned:
                self._back_storm_warned = True
                log = getattr(self.task, 'log_warning', None)
                if log:
                    log(self.task.tr(
                        '投屏下连续返回无效, 已暂停点击; 请确认游戏画面已回到大世界'))
            return False
        self._back_times.append(now)
        return True

    def open_menu(self, after_sleep=0):
        """打开/切换系统菜单。安卓端与返回是同一个按钮(键位表的 `)。"""
        self.back(after_sleep=after_sleep)

    def close_panel(self, after_sleep=1):
        """关掉当前打开的指南书/面板（仅手机投屏）。

        手游面板右上角有固定 X，而「菜单/返回」是用户自己校准的触点，实测可能
        落在指南书图标上导致关不掉。这里直接点 X，并在主界面安全跳过。
        """
        if not self.is_phone_mirror:
            return False
        self.task.click_relative(*TOUCH_PANEL_CLOSE_CLICK, after_sleep=after_sleep)
        return True

    def open_book(self, after_sleep=4):
        """打开索拉指南。投屏优先点用户校准的 F2 触点; 没校准仍点右上角图标栏
        的指南按钮; 非触屏返回 False, 由调用方走按键(key_config / F2)。"""
        if self.is_touch:
            if self.mapped_key('f2'):
                self.task.send_key('f2', after_sleep=after_sleep)
                return True
            self.task.click_relative(*TOUCH_BOOK_CLICK, after_sleep=after_sleep)
            return True
        return False

    def open_activity(self, after_sleep=4):
        """打开活动面板(PC 端为 F1 键)。触屏直接点右上角图标栏的活动图标
        (索拉指南图标左边那个); 非触屏返回 False, 由调用方走按键。"""
        if self.is_touch:
            self.task.click_relative(*TOUCH_ACTIVITY_CLICK, after_sleep=after_sleep)
            return True
        return False
