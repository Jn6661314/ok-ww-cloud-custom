"""MuMu / 安卓模拟器的双指触控输入（ADB sendevent 多点触控协议）。

拉海洛方块在手游版里旋转靠屏幕左侧的圆形「旋转」按钮，操作方式是
「一指点住旋转按钮 + 另一指长按拖动方块」——这是真正的双指手势。
MuMu IPC SDK（nemu_input_event_touch_down/up）与 uiautomator2 的
touch.down/up 都是单指（pointer id 固定），做不了双指；只有直接写
Linux input 子系统的 ABS_MT_SLOT 才能同时按两个触点。

实现要点
--------
* 触控设备：/dev/input/event*，名称含 "Touchscreen" 且支持 ABS_MT_SLOT，
  启动时自动探测并缓存，避免每次操作都跑一遍 getevent。
* 事件码（Linux input 固定值）：
  ABS_MT_SLOT=0x2f, ABS_MT_POSITION_X=0x35, ABS_MT_POSITION_Y=0x36,
  ABS_MT_TRACKING_ID=0x39, BTN_TOUCH=0x14a, SYN_REPORT=0。
* 坐标映射：游戏横屏 1920x1080（内部归一到 2048x1152），物理触控屏
  1080x1920 竖屏，横屏内容相对物理屏旋转 90°。实测映射为
  ``物理(x, y) = (游戏y, 游戏x)``（见下方 game_to_touch）。
  这个换算在 MuMu 15 / 1080x1920 上实测通过；别的分辨率按比例缩放。
* 每个 slot 需要独立的 tracking_id（递增整数），抬指时写 -1 释放。
* 所有 sendevent 都通过 adb shell 执行（ok-ww 自带 adbutils，shell 用户
  已在 input 组，有 /dev/input/event* 写权限，无需 root）。

本模块只被拉海洛方块任务（MuMu 设备）使用，其他任务不走这条路径。
"""

import time

# Linux input event 常量（内核ABI，稳定不变）
EV_SYN = 0
EV_KEY = 1
EV_ABS = 3
BTN_TOUCH = 0x14a
ABS_MT_SLOT = 0x2f
ABS_MT_POSITION_X = 0x35
ABS_MT_POSITION_Y = 0x36
ABS_MT_TRACKING_ID = 0x39
SYN_REPORT = 0

# 游戏内部逻辑分辨率（与 rahai_blocks.py 一致）
GAME_W, GAME_H = 2048, 1152


class MultiTouchDevice:
    """一条 ADB 连接上的多点触控写入器。

    用法::

        mt = MultiTouchDevice(adb_device)
        mt.down(0, gx, gy)          # slot 0 按下（游戏坐标）
        mt.move(0, gx2, gy2)        # 同槽移动
        mt.down(1, rx, ry)          # slot 1 按下（第二指）
        mt.up(1)                    # 抬第二指
        mt.up(0)                    # 抬第一指
        mt.close()                  # 释放所有仍按下的触点

    坐标一律传「游戏横屏坐标」（1920x1080 或归一到 2048x1152），
    内部换算成物理触控坐标。
    """

    def __init__(self, adb_device, device_node=None, physical_w=1080, physical_h=1920):
        self.device = adb_device
        self.physical_w = physical_w
        self.physical_h = physical_h
        self._node = device_node
        self._next_tracking_id = 1
        self._active = {}  # slot -> tracking_id

    def _sendevent(self, event_type, code, value):
        return self.device.shell(
            f'sendevent {self._node} {event_type} {code} {value}')

    def _ensure_node(self):
        if self._node:
            return
        # 探测支持 ABS_MT_SLOT 的 Touchscreen 设备节点
        info = self.device.shell(['getevent', '-il'])
        node = None
        current = None
        is_touchscreen = False
        for line in info.splitlines():
            stripped = line.strip()
            if stripped.startswith('add device'):
                current = stripped.split(':', 1)[-1].strip()
                is_touchscreen = False
            elif 'name:' in stripped and current:
                is_touchscreen = 'touchscreen' in stripped.lower()
            elif is_touchscreen and 'ABS_MT_SLOT' in stripped and current:
                node = current
                break
        if not node:
            raise RuntimeError(
                '未找到支持多点触控(ABS_MT_SLOT)的 Touchscreen 设备，无法使用双指输入')
        self._node = node

    def game_to_touch(self, gx, gy):
        """游戏横屏坐标 -> 物理触控坐标。

        实测 MuMu 15（物理 1080x1920 竖屏、游戏横屏）的映射为
        ``touch_x = gy, touch_y = gx``（按比例缩放）。例：游戏左侧旋转
        按钮 (232, 750) 对应物理 (750, 232)，点中后画面确实旋转。
        """
        self._ensure_node()
        # 先把游戏坐标按比例缩放（调用方一般已归一到 2048x1152，
        # 这里再按物理短边/长边映射：游戏宽 -> 物理高，游戏高 -> 物理宽）
        tx = gy / GAME_H * self.physical_w
        ty = gx / GAME_W * self.physical_h
        return round(tx), round(ty)

    def _sync(self):
        self._sendevent(EV_SYN, SYN_REPORT, 0)

    def down(self, slot, gx, gy):
        """在指定槽位按下（游戏坐标）。同一 slot 重复 down 会被视为移动。"""
        self._ensure_node()
        tx, ty = self.game_to_touch(gx, gy)
        if slot not in self._active:
            self._active[slot] = self._next_tracking_id
            self._next_tracking_id += 1
        track = self._active[slot]
        self._sendevent(EV_ABS, ABS_MT_SLOT, slot)
        self._sendevent(EV_ABS, ABS_MT_POSITION_X, tx)
        self._sendevent(EV_ABS, ABS_MT_POSITION_Y, ty)
        self._sendevent(EV_ABS, ABS_MT_TRACKING_ID, track)
        self._sync()

    def move(self, slot, gx, gy):
        """移动指定槽位的触点（手指不抬起）。"""
        self._ensure_node()
        tx, ty = self.game_to_touch(gx, gy)
        self._sendevent(EV_ABS, ABS_MT_SLOT, slot)
        self._sendevent(EV_ABS, ABS_MT_POSITION_X, tx)
        self._sendevent(EV_ABS, ABS_MT_POSITION_Y, ty)
        self._sync()

    def up(self, slot):
        """抬起指定槽位的触点。"""
        self._ensure_node()
        self._sendevent(EV_ABS, ABS_MT_SLOT, slot)
        self._sendevent(EV_ABS, ABS_MT_TRACKING_ID, -1)
        self._sync()
        self._active.pop(slot, None)

    def tap(self, slot, gx, gy, duration=0.08):
        """用指定槽位点一下（游戏坐标），不改变其他槽位的按压状态。"""
        self.down(slot, gx, gy)
        time.sleep(duration)
        self.up(slot)

    def close(self):
        """释放所有仍按下的触点（异常收尾用）。"""
        for slot in list(self._active):
            self.up(slot)


class MuMuMultiTouchInteraction:
    """把拉海洛方块用的交互接口映射到双指触控。

    方块任务用一套接口：move / mouse_down / mouse_up / send_key / click。
    这里：
      * slot 0 = 拖动方块的手指（move / mouse_down / mouse_up）
      * send_key('r') = slot 1 点屏幕左侧旋转按钮（第二指）
    ``_place()`` 无需改动即可在 MuMu 上工作。
    """

    # 旋转按钮在游戏逻辑坐标(2048x1152)中的位置（截图实测，左侧圆形按钮）
    ROTATE_BUTTON = (247, 800)

    def __init__(self, multi_touch, screenshot=None):
        self.mt = multi_touch
        self.screenshot = screenshot  # 可选：每次操作后刷新画面用
        self.capture = None
        self._down_pos = None

    def clickable(self):
        # 触屏输入不要求窗口前台/焦点（sendevent 直接写设备节点）
        return True

    def move(self, x, y):
        # x/y 是游戏的 1920x1080 实际像素；换算到 2048x1152 逻辑坐标
        gx = x / 1920 * GAME_W
        gy = y / 1080 * GAME_H
        self.mt.move(0, gx, gy)

    def mouse_down(self, x=-1, y=-1, name=None, key='left'):
        gx = x / 1920 * GAME_W
        gy = y / 1080 * GAME_H
        self._down_pos = (gx, gy)
        self.mt.down(0, gx, gy)

    def mouse_up(self, key='left'):
        self.mt.up(0)
        self._down_pos = None

    def send_key(self, key, down_time=0.08):
        if str(key).lower() == 'r':
            # 第二指点击屏幕旋转按钮（slot 1，不干扰 slot 0 的拖动）
            self.mt.tap(1, *self.ROTATE_BUTTON, duration=down_time)
        # 其他键手游不认，忽略

    def send_key_down(self, key):
        pass

    def send_key_up(self, key):
        pass

    def click(self, x=-1, y=-1, **kwargs):
        gx = x / 1920 * GAME_W
        gy = y / 1080 * GAME_H
        self.mt.tap(0, gx, gy)

    def swipe(self, x1, y1, x2, y2, duration, settle_time=0):
        self.mouse_down(x1, y1)
        steps = max(2, int(duration / 0.02))
        for i in range(1, steps + 1):
            self.move(x1 + (x2 - x1) * i / steps, y1 + (y2 - y1) * i / steps)
            time.sleep(0.02)
        time.sleep(settle_time)
        self.mouse_up()

    def close(self):
        self.mt.close()
