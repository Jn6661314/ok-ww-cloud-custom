"""安卓端索拉指南(PC 端 F2 指南书)的类别图标定位。

背景
----
PC 端鸣潮用 F2 打开"索拉指南", 左侧是一列类别图标:

  任务        = 菱形星标 (gray_book_quest)
  首领        = 交叉双剑 (gray_book_boss)
  周常        = 循环徽章 (gray_book_weekly)
  全部怪物    = 骷髅面具 (gray_book_all_monsters)

安卓客户端的索拉指南是另一套**移动端布局**: 最左侧一列竖排类别图标, 内容在右侧。
类别图标的外观与 PC 相同, 但整体缩放和偏移都不同 —— 实测安卓左列图标中心
x≈76, y≈190 / 320 / 462 / 597 / 729 / 845; PC 端模板锚点是 x≈39~48,
y≈156 / 283 / 426 / 695。

直接拿 PC 模板做 NCC 模板匹配会**命中背景空白**: 实测在安卓书界面上,
gray_book_quest 最高分 0.712 @ (48,156)、gray_book_boss 0.741 @ (44,283)、
gray_book_weekly 0.767 @ (42,426)、gray_book_all_monsters 0.822 @ (39,695),
全部落在模板自身锚点处的**空背景**上而不是图标上 —— 定位失败, 而且点下去
也是错的位置。

做法
----
改用"白色笔画二值掩码 + 多尺度 IoU 滑窗"配对:

  1. 把屏幕左侧图标列窄条二值化成笔画掩码(低饱和 + 高亮度), 背景自然变 0;
  2. 把 PC 模板同样二值化(灰度/笔画两种口径各来一份), 裁到笔画外接框;
  3. 在若干缩放比例下, 用积分图算**逐位置精确 IoU**, 取全局最高分。

掩码比对只关心**笔画形状**, 对背景明暗、轻微缩放都不敏感。实测在真实安卓
书界面上, 四个 PC 类别模板全部对号入座:

  gray_book_quest        IoU 0.681 -> 安卓 y≈191 (菱形星标)
  gray_book_boss         IoU 0.803 -> 安卓 y≈323 (交叉双剑)
  gray_book_weekly       IoU 0.778 -> 安卓 y≈461 (循环徽章)
  gray_book_all_monsters IoU 0.879 -> 安卓 y≈729 (骷髅面具)
"""

import cv2
import numpy as np

# 左侧类别图标列的横向范围(相对屏宽)。实测安卓左列图标中心 x≈76/1920≈0.04,
# 取 1.5%~7.5% 既能框住整列, 又不会把右侧列表面板(x≈210 起)的文字框进来。
COLUMN_X_FROM = 0.015
COLUMN_X_TO = 0.075

# 纵向范围(相对屏高):
#   上界 0.12 —— 顶部是标题栏("素材获取"图标), 不是类别图标;
#   下界 0.73 —— 屏幕下方的背景渐变会变亮成一片白, 二值化后整块全 1,
#                 任何模板都能在上面拿到 IoU=1.0 的假匹配, 必须排除。
COLUMN_Y_FROM = 0.12
COLUMN_Y_TO = 0.73

# 笔画掩码阈值(屏幕侧): 低饱和 + 高亮度 = 图标的白色线条。
# 未选中的类别图标是半透明白(比选中态暗), 阈值不能太高, 否则只能检出选中项。
STROKE_SAT_MAX = 110
STROKE_VAL_MIN = 150

# 模板侧灰度掩码阈值
TEMPLATE_GRAY_MIN = 90

# 多尺度搜索的缩放比例(安卓图标与 PC 模板尺寸不完全一致)
SCALES = (0.40, 0.50, 0.60, 0.70, 0.80, 0.90, 1.00, 1.10)

# 判定为同一类别所需的最小 IoU。实测正确匹配 0.68~0.88, 错误匹配 < 0.5。
DEFAULT_IOU = 0.55

# 连通域过滤(用于判断索拉指南是否已打开)
MIN_AREA = 200
MAX_AREA = 4000
MIN_SIDE = 20
MAX_SIDE = 80

# 索拉指南左列至少要有这么多个类别图标, 才认为书已打开
OPENED_MIN_ICONS = 3

# 且这些图标要竖向铺开这么多像素 —— 大世界画面左上角也会碰到若干亮色碎片
# (实测 4 个, 但只分布在 y=223~374 的 151 px 内), 而索拉指南的类别图标
# 从 y≈177 一直排到 y≈730。限定跨度可以避免把大世界误判成"书已打开"。
OPENED_MIN_SPREAD = 350


def stroke_mask(img):
    """白色笔画的二值掩码(0/1 uint8); 入参为 None 或空图时返回 None。"""
    if img is None or getattr(img, 'size', 0) == 0:
        return None
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    mask = (hsv[:, :, 1] < STROKE_SAT_MAX) & (hsv[:, :, 2] > STROKE_VAL_MIN)
    return mask.astype(np.uint8)


def gray_mask(img, threshold=TEMPLATE_GRAY_MIN):
    """亮度高于阈值的二值掩码(0/1 uint8)。"""
    if img is None or getattr(img, 'size', 0) == 0:
        return None
    return (cv2.cvtColor(img, cv2.COLOR_BGR2GRAY) > threshold).astype(np.uint8)


def _crop_to_ink(mask):
    """把掩码裁到笔画实际覆盖的范围, 去掉空白边。"""
    if mask is None or mask.size == 0:
        return None
    ys = np.where(mask.any(axis=1))[0]
    xs = np.where(mask.any(axis=0))[0]
    if len(ys) == 0 or len(xs) == 0:
        return None
    return mask[ys[0]:ys[-1] + 1, xs[0]:xs[-1] + 1]


def _iou_map(screen_bin, tpl_bin):
    """逐位置 IoU 图。

    matchTemplate(TM_CCORR) 在二值图上就是交集像素数; 再用积分图求出每个
    窗口内的笔画像素数, 即可还原精确 IoU = 交集 / (窗口笔画数 + 模板笔画数 - 交集)。
    """
    th, tw = tpl_bin.shape
    if screen_bin.shape[0] < th or screen_bin.shape[1] < tw:
        return None
    inter = cv2.matchTemplate(screen_bin, tpl_bin, cv2.TM_CCORR)
    integ = cv2.integral(screen_bin)
    local = integ[th:, tw:] - integ[:-th, tw:] - integ[th:, :-tw] + integ[:-th, :-tw]
    union = local.astype(np.float64) + float(tpl_bin.sum()) - inter
    return np.where(union > 0, inter / np.maximum(union, 1e-6), 0.0)


def find_icon_candidates(frame):
    """左侧图标列里的类别图标候选框(笔画连通域)。

    用于判断索拉指南是否已经打开 —— 左列会出现 4~6 个竖排的类别图标。
    """
    mask = stroke_mask(frame)
    if mask is None:
        return []
    h, w = mask.shape[:2]
    x0 = max(0, int(w * COLUMN_X_FROM))
    x1 = min(w, int(w * COLUMN_X_TO))
    y0 = max(0, int(h * COLUMN_Y_FROM))
    y1 = min(h, int(h * COLUMN_Y_TO))
    strip = mask[y0:y1, x0:x1]
    if strip.size == 0:
        return []
    count, _labels, stats, _cent = cv2.connectedComponentsWithStats(strip, 8)
    boxes = []
    for i in range(1, count):
        x, y, bw, bh, area = stats[i]
        if not (MIN_AREA <= area <= MAX_AREA):
            continue
        if not (MIN_SIDE <= bw <= MAX_SIDE and MIN_SIDE <= bh <= MAX_SIDE):
            continue
        boxes.append((x + x0, y + y0, x + x0 + bw - 1, y + y0 + bh - 1))
    boxes.sort(key=lambda b: b[1])
    return boxes


def _template_variants(template):
    """模板的两种掩码口径(灰度 / 笔画), 各裁到笔画外接框。"""
    variants = []
    for mask in (gray_mask(template), stroke_mask(template)):
        cropped = _crop_to_ink(mask)
        if cropped is not None and cropped.size:
            variants.append(cropped)
    return variants


def _best_match(screen_bin, tpl):
    """在屏幕掩码里找该模板的最佳落点。

    :return: (score, loc, height, width) —— 最佳 IoU / 位置 / 模板缩放后尺寸; 找不到返回 None
    """
    best = None
    for scale in SCALES:
        th = max(4, int(tpl.shape[0] * scale))
        tw = max(4, int(tpl.shape[1] * scale))
        resized = cv2.resize(tpl, (tw, th), interpolation=cv2.INTER_AREA)
        if resized.sum() == 0:
            continue
        iou = _iou_map(screen_bin, resized)
        if iou is None:
            continue
        _minv, maxv, _minloc, loc = cv2.minMaxLoc(iou)
        if best is None or maxv > best[0]:
            best = (float(maxv), loc, th, tw)
    return best


def find_book_tab(frame, template, iou_threshold=DEFAULT_IOU):
    """在安卓索拉指南左侧图标列里定位与 template 同类别的图标。

    :param frame: 当前帧 (BGR)
    :param template: PC 端类别图标模板 (BGR)
    :param iou_threshold: 判定为同一类别所需的最小 IoU
    :return: (cx, cy, width, height, score) —— 图标中心/尺寸/IoU 分数; 找不到返回 None
    """
    if frame is None or template is None:
        return None
    h, w = frame.shape[:2]
    x0 = max(0, int(w * COLUMN_X_FROM))
    x1 = min(w, int(w * COLUMN_X_TO))
    y0 = max(0, int(h * COLUMN_Y_FROM))
    y1 = min(h, int(h * COLUMN_Y_TO))
    screen_bin = stroke_mask(frame)
    if screen_bin is None:
        return None
    screen_bin = screen_bin[y0:y1, x0:x1]
    if screen_bin.size == 0:
        return None

    variants = _template_variants(template)
    if not variants:
        return None

    best = None
    for tpl in variants:
        found = _best_match(screen_bin, tpl)
        if found is None:
            continue
        score, loc, th, tw = found
        if best is None or score > best[4]:
            best = (x0 + loc[0] + tw // 2, y0 + loc[1] + th // 2, tw, th, score)
    if best is None or best[4] < iou_threshold:
        return None
    return best


def count_book_tabs(frame, templates, iou_threshold=DEFAULT_IOU):
    """找出左列能配上的类别图标(模板法)。

    连通域启发式在真实安卓书界面上偏严(未选中的图标笔画偏淡, 常常凑不满
    min_icons 个), 会把"书已经打开"误判成"没打开" —— 表现为脚本反复点右上角
    图标(点一下关掉、再点一下打开), 书的状态来回翻, 后续点击全落在错误位置。
    模板法(和 find_book_tab 同一套笔画 IoU 配对)在实测中稳定认得出左列图标,
    所以用它做补充判据。

    注意: 大世界画面左上角偶尔也会撞出 1~2 个高分假匹配(实测 re_world 画面
    撞出 gray_book_weekly 0.78 / gray_book_all_monsters 0.91), 所以调用方还要
    配合"数量 + 竖向跨度"一起判断, 不能只看分数。

    :param frame: 当前帧 (BGR)
    :param templates: PC 端类别图标模板列表 (BGR)
    :return: [(cx, cy, width, height, score), ...]
    """
    if frame is None or not templates:
        return []
    matched = []
    for template in templates:
        hit = find_book_tab(frame, template, iou_threshold=iou_threshold)
        if hit is not None:
            matched.append(hit)
    return matched


# 模板法判定"书已打开"所需的最小图标数与竖向跨度(像素)。
# 书界面实测 4 个图标分布在 y≈191/322/461/727(跨度 536);
# 大世界里的假匹配挤在一起(跨度 < 30), 用跨度就能把两者分开。
TEMPLATE_MIN_ICONS = 3
TEMPLATE_MIN_SPREAD = 200


def is_book_opened(frame, templates=None, min_icons=OPENED_MIN_ICONS, min_spread=OPENED_MIN_SPREAD):
    """安卓端索拉指南是否已打开(左列是否出现足够多、且竖向铺开的类别图标)。

    :param templates: 可选的 PC 类别图标模板列表, 给定时作为补充判据
    """
    boxes = find_icon_candidates(frame)
    if len(boxes) >= min_icons:
        ys = [(b[1] + b[3]) // 2 for b in boxes]
        if (max(ys) - min(ys)) >= min_spread:
            return True
    if templates:
        matched = count_book_tabs(frame, templates)
        if len(matched) >= TEMPLATE_MIN_ICONS:
            ys = [m[1] for m in matched]
            if (max(ys) - min(ys)) >= TEMPLATE_MIN_SPREAD:
                return True
    return False
