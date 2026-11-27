"""手机投屏(NectarLink)支持: 下载入口 + 投屏窗口识别 + 画面自适应。

用户想把手机画面投到 PC 上驱动鸣潮, 取代模拟器。NectarLink 的桌面端会把
手机画面开成一个独立窗口(标题 "<设备名> · NectarLink"), 并把鼠标点击按
**屏幕比例**转发到手机 —— 因此只要把这个窗口当普通 Windows 窗口抓屏 + 点击,
就能操作手机, 且坐标自动适配缩放/黑边/横竖屏。

本模块提供:
  * ANDROID_MIRROR_APK_URL: 手机端(Android APK)下载地址(网盘分享)。
  * open_android_mirror_apk(): 打开下载地址, 给配置界面的下载按钮用。
  * is_nectarlink_window(title): 判断某个窗口标题是不是 NectarLink 投屏窗口。
  * detect_picture_rect(frame): 在一帧投屏画面里认出「手机画面区」(去掉工具条
    和黑边), 返回它在帧里的矩形。
  * normalize_picture_size(size): 把画面区归一化到模板原生的高度。

画面为什么需要单独处理
----------------------
NectarLink 投屏窗口的客户区里并不只有手机画面:

  1. 顶部或底部有一条工具条(源码 MirrorWindow.qml 的 ``strip`` 属性, 高度
     52 或 96, 底色 ``#121212``);
  2. 手机画面按 ``KeepAspectRatio`` 居中摆放(VideoView.pictureRect), 窗口
     比例和手机比例不一致时四周会出现纯黑边;
  3. 用户拖动窗口时, NectarLink 会在 250ms 后把窗口改回手机比例, 但改回
     之前画面是拉伸变形的。

直接抓整个客户区, 拿到的帧比例既不是 16:9 也不是手机比例, 识图和坐标换算
都会偏。这里把手机画面区从窗口里认出来, 单独裁出来用。
"""

import re
import webbrowser

import cv2
import numpy as np

# 手机端 APK 的下载地址(网盘分享, 含提取码)。
ANDROID_MIRROR_APK_URL = 'https://pan.baidu.com/s/13Y-rkKtfp7EQHd4SJwdzDA?pwd=Jn66'

# NectarLink 桌面端投屏窗口标题: "<设备名> · NectarLink"
# (见 nectarlink desktop/app/qml/MirrorWindow.qml 的 title 属性)
NECTARLINK_WINDOW_PATTERN = re.compile(r'\S.*\s+·\s+NectarLink$')

# ---------------------------------------------------------------------------
# 画面区识别与归一化的参数
# ---------------------------------------------------------------------------

# NectarLink 窗口底色是纯黑(灰度 0), 工具条底色是 #121212(灰度 18)。
# 用 12 把"纯黑"(黑边) 和"工具条底色"分开。
DARK_GRAY = 12

# 工具条底色所在的灰度区间(工具条上有图标, 所以看的是整行的中位数)。
STRIP_GRAY_MIN = 10
STRIP_GRAY_MAX = 32

# 工具条高度候选(px)。见 MirrorWindow.qml:
#   readonly property real strip: Preferences.mirrorToolbarOutside && !Preferences.hideMirrorToolbar
#       ? (!info.app && !navPill.besideToolbar ? 96 : 52) : 0
STRIP_SIZES = (52, 96)

# 实际高度允许的偏差(窗口缩放 / DPI 会带来几个像素的出入)。
STRIP_TOLERANCE = 8

# 一行被判为"内容行"所需的最低非黑像素占比。
CONTENT_ROW_RATIO = 0.02

# 画面归一化后的目标高度: 模板资源是 1920x1080 标注的, 帧高正好 1080 时
# 模板按 1:1 使用(最清晰); 而且帧尺寸恒定, 窗口尺寸变化时框架不用反复
# 重载全部模板。
NORMALIZED_HEIGHT = 1080


def open_android_mirror_apk():
    """打开手机端 APK 的下载页面; 返回是否成功打开。

    供配置界面的「下载手机端」按钮调用。放在 src 下是为了让 config.py
    只做声明, 不写业务逻辑。
    """
    try:
        webbrowser.open(ANDROID_MIRROR_APK_URL)
        return True
    except Exception:
        return False


def is_nectarlink_window(title) -> bool:
    """窗口标题是否是 NectarLink 手机投屏窗口。"""
    if not title:
        return False
    return bool(NECTARLINK_WINDOW_PATTERN.search(str(title).strip()))


# ---------------------------------------------------------------------------
# 画面区识别
# ---------------------------------------------------------------------------


def to_gray(frame):
    """把一帧画面转成灰度图(BGR / BGRA / 灰度 都接受)。"""
    if frame is None:
        return None
    array = np.asarray(frame)
    if array.ndim == 2:
        return array
    if array.shape[2] == 4:
        array = array[:, :, :3]
    return cv2.cvtColor(array, cv2.COLOR_BGR2GRAY)


def longest_run(flags, max_gap=0):
    """在一串布尔值里找最长的一段 True。

    ``max_gap`` 允许两段 True 之间隔着少量 False 也算作同一段(画面里偶尔
    有一两行纯黑不该把画面切成两半)。

    Returns:
        (start, end) 半开区间; 全是 False 时返回 None。
    """
    indexes = np.flatnonzero(flags)
    if indexes.size == 0:
        return None
    best = (int(indexes[0]), int(indexes[0]) + 1)
    start = prev = int(indexes[0])
    for value in indexes[1:]:
        value = int(value)
        if value - prev > max_gap + 1:
            if prev + 1 - start > best[1] - best[0]:
                best = (start, prev + 1)
            start = value
        prev = value
    if prev + 1 - start > best[1] - best[0]:
        best = (start, prev + 1)
    return best


def detect_strip_rows(gray, strip_sizes=STRIP_SIZES, tolerance=STRIP_TOLERANCE):
    """认出 NectarLink 工具条占据的行区间。

    工具条是整条纯 ``#121212`` 的矩形(上面可能浮着几个图标), 所以每一行的
    **灰度中位数**都稳定在 18 附近; 而画面里的暗行中位数会波动。

    Returns:
        (top, bottom) 半开行区间; 没找到工具条时返回 None。
    """
    if gray is None or gray.shape[0] < 16:
        return None
    medians = np.median(gray, axis=1)
    is_strip = (medians >= STRIP_GRAY_MIN) & (medians <= STRIP_GRAY_MAX)

    def _match(length):
        for size in strip_sizes:
            if abs(length - size) <= tolerance:
                return size
        return None

    # 顶部: 从第一行开始的连续工具条行
    top_length = 0
    while top_length < is_strip.shape[0] and is_strip[top_length]:
        top_length += 1
    # 底部: 从最后一行往上的连续工具条行
    bottom_length = 0
    while (bottom_length < is_strip.shape[0]
           and is_strip[is_strip.shape[0] - 1 - bottom_length]):
        bottom_length += 1

    candidates = []
    if _match(top_length) is not None:
        candidates.append((0, top_length))
    if _match(bottom_length) is not None:
        candidates.append((is_strip.shape[0] - bottom_length, is_strip.shape[0]))
    if not candidates:
        return None
    # 工具条一定在边缘, 两边都匹配时取更长的那个(更可能是工具条而不是暗画面)。
    candidates.sort(key=lambda item: item[1] - item[0], reverse=True)
    top, bottom = candidates[0]
    # 稳定性检查: 整块的中位数应该几乎不变(纯色底)。
    block = medians[top:bottom]
    if block.size and float(np.std(block)) > 1.5:
        return None
    return top, bottom


def detect_content_bbox(gray, dark=DARK_GRAY, min_ratio=CONTENT_ROW_RATIO, max_gap=3):
    """在灰度图里找"有内容"的区域(去掉纯黑的黑边)。

    Returns:
        (x, y, w, h); 整张图都是黑的时候返回 None。
    """
    if gray is None or gray.size == 0:
        return None
    return bbox_from_mask(gray > dark, min_ratio=min_ratio, max_gap=max_gap)


def bbox_from_mask(content, min_ratio=CONTENT_ROW_RATIO, max_gap=3):
    """在内容掩码里找包围盒。

    Args:
        content: 布尔数组, True 表示"这一像素有内容"。
        min_ratio: 一行/一列被判为"有内容"所需的最低占比。
        max_gap: 允许两段有内容的行之间隔着少量空白仍算作同一段。

    Returns:
        (x, y, w, h); 没有内容时返回 None。
    """
    if content is None or content.size == 0:
        return None
    height, width = content.shape[:2]
    rows = longest_run(content.mean(axis=1) > min_ratio, max_gap=max_gap)
    if rows is None:
        return None
    top, bottom = rows
    band = content[top:bottom]
    cols = longest_run(band.mean(axis=0) > min_ratio, max_gap=max_gap)
    if cols is None:
        left, right = 0, width
    else:
        left, right = cols
    return int(left), int(top), int(right - left), int(bottom - top)


def detect_picture_rect(frame, strip_sizes=STRIP_SIZES):
    """在一帧投屏窗口画面里找出「手机画面区」。

    处理两件事:
      * 去掉顶部/底部的 NectarLink 工具条(纯 #121212 的整条);
      * 去掉画面四周的纯黑边(窗口比例和手机比例不一致时出现)。

    Returns:
        (x, y, w, h) —— 相对 frame 左上角; 认不出来时返回 None。
    """
    gray = to_gray(frame)
    if gray is None or gray.size == 0:
        return None
    height, width = gray.shape[:2]

    strip = detect_strip_rows(gray, strip_sizes=strip_sizes)
    content = gray > DARK_GRAY
    if strip is not None:
        # 工具条本身也是"非黑", 先把它从内容掩码里剔掉, 否则包围盒会把它
        # 当成画面的一部分。
        content[strip[0]:strip[1]] = False

    bbox = bbox_from_mask(content)
    if bbox is None:
        # 整块都是黑的(刚打开投屏还没出画面): 只能退回到去掉工具条后的区域。
        if strip is None:
            return None
        return 0, int(strip[0]), int(width), int(strip[1] - strip[0])
    return bbox


# ---------------------------------------------------------------------------
# 分辨率归一化
# ---------------------------------------------------------------------------


def normalize_picture_size(size, target_height=NORMALIZED_HEIGHT):
    """把画面区的尺寸归一化到 ``target_height`` 高(等比, 不变形)。

    归一化的两个好处:
      * 模板资源是 1920x1080 标注的, 帧高正好 1080 时模板按 1:1 使用,
        匹配最准(不然框架会把模板缩放/放大, 清晰度打折);
      * 帧尺寸恒定, 窗口被拖动时框架不会反复重载全部模板资源。

    Returns:
        (width, height); 输入非法时原样返回。
    """
    width, height = int(size[0]), int(size[1])
    if width <= 0 or height <= 0 or target_height <= 0:
        return width, height
    scale = target_height / height
    return max(1, round(width * scale)), int(target_height)


def normalized_frame_size(frame_size, target_height=NORMALIZED_HEIGHT):
    """``normalize_picture_size`` 的别名, 语义更贴近调用点。"""
    return normalize_picture_size(frame_size, target_height=target_height)
