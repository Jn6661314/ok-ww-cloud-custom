"""
安卓端(ADB / MuMu 模拟器)专用的大世界判定。

背景(为什么需要这个模块):
  PC 端用右上角队伍栏的 "1/2/3" 数字徽章(char_1_text / char_2_text /
  char_3_text)判断"是否在大世界且在队伍中"。但安卓客户端的队伍栏是
  **圆形角色头像, 没有数字徽章** —— 这三个模板在安卓大世界画面上的
  匹配置信度只有 0.11~0.15(阈值 0.8), 永远匹配不上。

  结果就是 in_team() 恒返回 False -> in_team_and_world() 恒 False ->
  is_main() 恒 False -> ensure_main() 一直等到 600 秒超时, 期间只有
  "wait_login {switch_login}" 一条日志来回刷, 看起来就是"卡住不动、
  不跳过、也没有额外日志"。

判据(全部为安卓端独有的、与角色/场景无关的 UI 元素), 阈值来自真实帧标定:
  1) 左上角小地图雷达里的**黄色玩家箭头**: 大世界 339/347/502 个黄色像素,
     登录页/加载页/活动页 均为 0(活动页 29) —— 区分度最高。
  2) 底部偏左的**协奏金球**: 大世界 534/717 个橙色像素, 其余画面 0。
  3) 兜底组合: 右上队伍栏**白色血条** + 底部**共鸣者血条**同时成立
     (大世界 815/1057 + 2877/3023; 活动页 619 但血条为 0)。

明确排除项:
  * **加载界面**: 底部有一整条贯穿全屏的白色加载进度条(实测 y=1021~1027,
    单行连续白像素 1299)。它和底部血条在同一个 y 区间, 只看"白像素总数"
    会把加载界面误判成大世界(实测 2240 >= 2200), 因此必须单独识别并排除。
  * **全黑帧**: MuMu 的 IPC 截图偶尔会返回一张纯黑图(均值 0), 此时任何
    模板匹配都不会命中, 表现得和"不在大世界"完全一样, 必须区分开来
    单独报错, 否则排查方向会被彻底带偏。
"""

import cv2
import numpy as np

# --- 区域参数(均为 1920x1080 基准坐标, 实际使用时会按帧宽高等比缩放) ---
RADAR_BOX = (40, 0, 200, 200)           # 左上角小地图雷达(黄色玩家箭头)
ULT_ORB_BOX = (700, 950, 790, 1025)     # 底部偏左的协奏/共鸣金球
HP_BAR_BOX = (760, 1000, 1080, 1030)    # 底部中央共鸣者血条
PARTY_BAR_BOX = (1700, 300, 1815, 345)  # 右上角队伍栏头像下的白色血条
BOTTOM_STRIP = (0, 995, 1920, 1045)     # 底部横条(用于识别贯穿全屏的加载进度条)
# 屏幕中央的大弹窗区域(相对坐标), 如"连接已断开"提示框
DIALOG_BOX = (0.185, 0.269, 0.815, 0.690)

# 黄色(雷达玩家箭头): H 18~42, S>=120, V>=140
YELLOW_LO = (18, 120, 140)
YELLOW_HI = (42, 255, 255)
# 橙色(协奏金球): H 5~25, S>=120, V>=120
ORANGE_LO = (5, 120, 120)
ORANGE_HI = (25, 255, 255)
# 白色(血条/进度条): S<=60, V>=190
WHITE_LO = (0, 0, 190)
WHITE_HI = (180, 60, 255)

# 判定阈值(像素数)
RADAR_YELLOW_MIN = 120
ULT_ORANGE_MIN = 300
HP_BAR_WHITE_MIN = 2200
PARTY_WHITE_MIN = 600
# 单行连续白像素 >= 该值 => 贯穿全屏的加载进度条(实测加载页 1299, 大世界最长 85)
LOADING_BAR_MIN = 800
# 中央弹窗区域亮像素占比 >= 该值 => 大概率有模态弹窗(实测断线弹窗 0.78, 其余 <= 0.11)
DIALOG_BRIGHT_MIN = 0.5

# 整帧判定为"黑屏/无效帧"的亮度上限
BLACK_FRAME_MAX = 8


def _scale_box(box, width, height, base_width=1920, base_height=1080):
    """把 1920x1080 基准坐标换算到当前帧尺寸。"""
    x1 = max(0, int(round(box[0] * width / base_width)))
    y1 = max(0, int(round(box[1] * height / base_height)))
    x2 = min(width, int(round(box[2] * width / base_width)))
    y2 = min(height, int(round(box[3] * height / base_height)))
    return x1, y1, x2, y2


def _crop(frame, box):
    x1, y1, x2, y2 = _scale_box(box, frame.shape[1], frame.shape[0])
    if x2 <= x1 or y2 <= y1:
        return None
    return frame[y1:y2, x1:x2]


def _count_hsv(frame, box, lo, hi):
    roi = _crop(frame, box)
    if roi is None or roi.size == 0:
        return 0
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, lo, hi)
    return int(np.count_nonzero(mask))


def _count_white(frame, box):
    """区域内白色像素总数。"""
    roi = _crop(frame, box)
    if roi is None or roi.size == 0:
        return 0
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, WHITE_LO, WHITE_HI)
    return int(np.count_nonzero(mask))


def _longest_run(row_mask):
    """一维掩码里最长连续非零段的长度。"""
    row = (np.asarray(row_mask).ravel() > 0).astype(np.int8)
    if row.size == 0:
        return 0
    diff = np.diff(np.concatenate((np.zeros(1, dtype=np.int8), row, np.zeros(1, dtype=np.int8))))
    starts = np.flatnonzero(diff == 1)
    ends = np.flatnonzero(diff == -1)
    if starts.size == 0:
        return 0
    return int((ends - starts).max())


def _loading_bar_length(frame):
    """底部横条里最长的一行连续白像素长度。

    加载界面的进度条贯穿整个屏幕宽度(实测 1299 px), 而大世界的血条是
    两段 85 px 的短条, 用这个长度可以稳定区分"正在加载"和"已在大世界"。
    """
    roi = _crop(frame, BOTTOM_STRIP)
    if roi is None or roi.size == 0:
        return 0
    hsv = cv2.cvtColor(roi, cv2.COLOR_BGR2HSV)
    mask = cv2.inRange(hsv, WHITE_LO, WHITE_HI)
    best = 0
    for row in mask:
        best = max(best, _longest_run(row))
    return best


def is_black_frame(frame):
    """整帧是否几乎全黑(MuMu IPC 偶发返回空帧)。"""
    if frame is None or frame.size == 0:
        return True
    return int(frame.max()) <= BLACK_FRAME_MAX


def has_center_dialog(frame):
    """屏幕中央是否有大块浅色模态弹窗。

    用来在跑 OCR 之前先做一次廉价筛选: 安卓端"连接已断开"提示框是一块
    居中的浅色面板(实测亮像素占比 0.78), 而大世界/登录页/加载页都 <= 0.11。

    返回 (是否有弹窗, 亮像素占比)。
    """
    if frame is None or frame.size == 0:
        return False, 0.0
    height, width = frame.shape[:2]
    x1, y1 = int(DIALOG_BOX[0] * width), int(DIALOG_BOX[1] * height)
    x2, y2 = int(DIALOG_BOX[2] * width), int(DIALOG_BOX[3] * height)
    roi = frame[y1:y2, x1:x2]
    if roi.size == 0:
        return False, 0.0
    gray = cv2.cvtColor(roi, cv2.COLOR_BGR2GRAY)
    ratio = float(np.count_nonzero(gray > 200)) / gray.size
    return ratio >= DIALOG_BRIGHT_MIN, ratio


def detect_world_signals(frame):
    """返回安卓端各判据的原始像素统计, 便于日志与排查。"""
    if frame is None or frame.size == 0:
        return {
            'radar_yellow': 0,
            'ult_orange': 0,
            'hp_bar_white': 0,
            'party_white': 0,
            'loading_bar': 0,
            'black': True,
        }
    return {
        'radar_yellow': _count_hsv(frame, RADAR_BOX, YELLOW_LO, YELLOW_HI),
        'ult_orange': _count_hsv(frame, ULT_ORB_BOX, ORANGE_LO, ORANGE_HI),
        'hp_bar_white': _count_white(frame, HP_BAR_BOX),
        'party_white': _count_white(frame, PARTY_BAR_BOX),
        'loading_bar': _loading_bar_length(frame),
        'black': is_black_frame(frame),
    }


def in_android_world(frame):
    """安卓端"是否已在大世界"判定。

    返回 (是否在大世界, 判据说明)。判据说明用于日志, 直接给出是哪一项
    命中/未命中, 便于用户自查画面。
    """
    signals = detect_world_signals(frame)
    if signals['black']:
        return False, 'black_frame'

    # 加载界面优先排除: 底部有贯穿全屏的加载进度条
    if signals['loading_bar'] >= LOADING_BAR_MIN:
        return False, f"loading_screen(loading_bar={signals['loading_bar']})"

    if signals['radar_yellow'] >= RADAR_YELLOW_MIN:
        return True, f"radar_yellow={signals['radar_yellow']}"
    if signals['ult_orange'] >= ULT_ORANGE_MIN:
        return True, f"ult_orange={signals['ult_orange']}"
    # 兜底: 队伍栏血条 + 底部血条同时成立(雷达被弹窗遮挡时使用)
    if signals['party_white'] >= PARTY_WHITE_MIN and signals['hp_bar_white'] >= HP_BAR_WHITE_MIN:
        return True, (f"party_white={signals['party_white']}, "
                      f"hp_bar_white={signals['hp_bar_white']}")

    return False, (
        f"radar_yellow={signals['radar_yellow']}, "
        f"ult_orange={signals['ult_orange']}, "
        f"hp_bar_white={signals['hp_bar_white']}, "
        f"party_white={signals['party_white']}, "
        f"loading_bar={signals['loading_bar']}"
    )
