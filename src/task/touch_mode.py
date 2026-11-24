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
  - book_key()          : 指南书按键(触屏 F2 -> KEYCODE_F2, 其余走 key_config)

以后要调整触屏键位或某个操作的触屏手法, 只改这一处, 不用再翻遍每个 task。
"""

# 触屏语义键位(统一在 ADB_KEY_MAP 里映射成合法 KEYCODE_*)。
# 键位表: [ ` ] = 菜单/跳过; 触屏的返回与打开菜单是同一个按钮, 就是它。
TOUCH_MENU_BACK_KEY = '`'  # -> ADB_KEY_MAP -> KEYCODE_GRAVE (返回 = 打开菜单 = 菜单/跳过键)
TOUCH_BOOK_KEY = 'f2'      # -> ADB_KEY_MAP -> KEYCODE_F2    (索拉指南)


class TouchMode:
    """按设备模式分发语义操作的轻量助手, 由 BaseWWTask 持有(self.touch)。"""

    def __init__(self, task):
        self.task = task

    @property
    def is_touch(self):
        """当前是否为安卓触屏/模拟器(ADB)设备。"""
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

    def book_key(self):
        """指南书按键: 触屏用 F2, 其余返回 None 交给 key_config。"""
        return TOUCH_BOOK_KEY if self.is_touch else None
