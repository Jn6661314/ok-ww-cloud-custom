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
  - open_book()         : 指南书(触屏直接点右上角索拉指南图标, 其余走按键)

以后要调整触屏键位或某个操作的触屏手法, 只改这一处, 不用再翻遍每个 task。
"""

# 触屏语义键位(统一在 ADB_KEY_MAP 里映射成合法 KEYCODE_*)。
# 键位表: [ ` ] = 菜单/跳过; 触屏的返回与打开菜单是同一个按钮, 就是它。
TOUCH_MENU_BACK_KEY = '`'  # -> ADB_KEY_MAP -> KEYCODE_GRAVE (返回 = 打开菜单 = 菜单/跳过键)

# 索拉指南(触屏): 触屏 UI 的 F2 未必被模拟器键位映射捕获, 改为直接点击
# 右上角图标栏里的索拉指南按钮。坐标来自用户在 MuMu 1278x719 截图上
# 标注的红框中心 (932, 44) -> (0.7293, 0.0612)。
TOUCH_BOOK_CLICK = (0.7293, 0.0612)


class TouchMode:
    """按设备模式分发语义操作的轻量助手, 由 BaseWWTask 持有(self.touch)。"""

    def __init__(self, task):
        self.task = task

    @property
    def is_touch(self):
        """当前是否走 ADB 触屏键位(安卓模拟器且输入通道为 ADB)。

        注意: 若配置成"像 PC 一样给模拟器窗口发键盘消息"(PostMessage/Pynput 等
        窗口消息交互), esc 本身就是 PC 语义, 不做触屏改写 —— 只有真正走
        ADBInteraction(input keyevent) 时才把 esc 语义换成键位表的 ` 键。
        """
        try:
            if not self.task.is_adb():
                return False
            interaction = getattr(self.task.executor, 'interaction', None)
            if interaction is None:
                return True
            from ok.device.interaction_methods.adb import ADBInteraction
            return isinstance(interaction, ADBInteraction)
        except Exception:
            try:
                return bool(self.task.is_adb())
            except Exception:
                return False

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
            self.task.send_key(TOUCH_MENU_BACK_KEY, after_sleep=after_sleep)
        else:
            self.task.back(after_sleep=after_sleep)

    def open_menu(self, after_sleep=0):
        """打开/切换系统菜单。安卓端与返回是同一个按钮(键位表的 `)。"""
        self.back(after_sleep=after_sleep)

    def open_book(self, after_sleep=4):
        """打开索拉指南。触屏直接点右上角图标栏的指南按钮(用户标注红框位置);
        非触屏返回 False, 由调用方走按键(key_config / F2)。"""
        if self.is_touch:
            self.task.click_relative(*TOUCH_BOOK_CLICK, after_sleep=after_sleep)
            return True
        return False
