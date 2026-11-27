"""手机投屏(内置引擎)的键位映射: 把 ok-ww 的按键翻译成手机屏幕上的触点。

为什么需要这一层
----------------
MuMu 上脚本发 `send_key('e')` 是能生效的, 靠的不是 ok-ww: 是**模拟器自带的
键位映射** —— 它把真实键盘事件翻译成那个位置的屏幕触摸。

真机没有这一层。NectarLink 手机端收到按键只会当成 Android 按键事件注入
(`Elevated` -> `K <keycode>`), 而手游(鸣潮)不认按键事件, 只认触点。所以投屏下
按 e / 1 / 2 / ` 全是白按 —— 只能人手去点屏幕。

这个模块把 MuMu 里那套映射搬到 ok-ww 自己身上: 一张「键 -> 屏幕比例坐标」的表,
按键时直接发触点过去。坐标用屏幕比例(0..1), 与横竖屏、缩放、黑边都无关
(和投屏触控协议一致)。

表存在 ``configs/phone_mirror_keymap.json``, 由「校准键位」窗口点出来, 也可以
自己改(格式 ``{"e": [0.80, 0.65]}``)。
"""

import json
import os

from ok import Logger

logger = Logger.get_logger(__name__)

# 键位表的文件名(不是配置菜单名, 所以不能叫 *_CONFIG_NAME —— 那个后缀在
# 测试里代表"必须是已注册的 ConfigOption 名字")。
KEYMAP_FILE_NAME = 'phone_mirror_keymap'

# 校准窗口里列出来的键, 顺序就是操作里最常用的顺序。
# 第一项是「菜单/返回」: 手游里返回和打开菜单是同一个按钮, 所以 ` 和 esc 都指它。
CALIBRATION_KEYS = [
    ('`', '菜单 / 返回'),
    ('1', '切人 1'),
    ('2', '切人 2'),
    ('3', '切人 3'),
    ('e', '技能 E'),
    ('r', '共鸣解放 R'),
    ('f', '交互 F'),
    ('space', '跳跃'),
    ('y', '锁敌 Y'),
]

# 没校准过的机器至少要有「返回/菜单」: 这个按钮的位置是固定的(左上角),
# 而且不修它整条任务链都会卡住(打不开菜单、退不出界面)。
# 其它键的位置取决于手机分辨率和自定义布局, 不猜 —— 交给校准窗口点。
DEFAULT_KEYMAP = {
    '`': (0.045, 0.065),
    'esc': (0.045, 0.065),
    'escape': (0.045, 0.065),
}

# 同一个按钮的别名: 校准 `` ` `` 之后, esc 也该跟着能用。
KEY_ALIASES = {
    'esc': '`',
    'escape': '`',
    'menu': '`',
}

# 读盘的节流: 按键很频繁, 不能每次都读文件。
_cache = {'mtime': None, 'map': None}


def _config_dir() -> str:
    """配置文件所在目录(取法和框架的 Config 一致, 是 cwd 相对的)。"""
    base = os.environ.get('OKWW_CONFIG_DIR')
    if base:
        return base
    try:
        from ok.util.config import Config
        from ok.util.file import get_relative_path
        return get_relative_path(Config.config_folder)
    except Exception:
        return os.path.join(os.getcwd(), 'configs')


def keymap_path() -> str:
    return os.path.join(_config_dir(), f'{KEYMAP_FILE_NAME}.json')


def normalize_key(key) -> str:
    """把按键名规整成表里用的写法。"""
    text = str(key).strip().lower()
    return KEY_ALIASES.get(text, text)


def _coerce(point):
    """把各种写法压成 (横, 纵) 的比例; 不合法返回 None。"""
    try:
        x, y = float(point[0]), float(point[1])
    except (TypeError, ValueError, IndexError):
        return None
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
        return None
    return (x, y)


def _read_file():
    path = keymap_path()
    try:
        mtime = os.path.getmtime(path)
    except OSError:
        return None, {}
    if _cache['mtime'] == mtime and _cache['map'] is not None:
        return mtime, _cache['map']
    try:
        with open(path, 'r', encoding='utf-8') as f:
            raw = json.load(f)
    except Exception as e:
        logger.warning(f'手机投屏: 读键位映射失败({e})')
        return mtime, {}
    mapping = {}
    if isinstance(raw, dict):
        for key, point in raw.items():
            coerced = _coerce(point)
            if coerced is not None:
                mapping[normalize_key(key)] = coerced
    _cache['mtime'] = mtime
    _cache['map'] = mapping
    return mtime, mapping


def load() -> dict:
    """当前的键位表 = 内置默认 + 校准结果(后者覆盖同名的键)。"""
    _, user = _read_file()
    mapping = dict(DEFAULT_KEYMAP)
    mapping.update(user)
    return mapping


def load_user() -> dict:
    """只要用户校准过的那部分(不含内置默认)。

    校准窗口必须用它初始化: 拿 ``load()`` 会把默认的 ``esc``/``escape`` 也
    带进来, 保存时这两个别名又会把用户刚点的 `` ` `` 覆盖回去。
    """
    _, user = _read_file()
    return dict(user)


def lookup(key):
    """按键对应的屏幕比例坐标; 没映射过就返回 None。"""
    if key is None:
        return None
    return load().get(normalize_key(key))


def save(mapping: dict) -> bool:
    """把校准结果写盘(只写用户校准的那部分, 默认值不落盘)。"""
    clean = {}
    for key, point in (mapping or {}).items():
        coerced = _coerce(point)
        if coerced is None:
            continue
        value = [round(coerced[0], 4), round(coerced[1], 4)]
        name = normalize_key(key)
        if str(key).strip().lower() in KEY_ALIASES:
            # 别名(esc/escape)统一落成 `, 但**不能盖掉**真正的 ` —— 校准窗口
            # 里两个都在, 后写的别名会把用户点的位置冲掉。
            clean.setdefault(name, value)
        else:
            clean[name] = value
    path = keymap_path()
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(clean, f, ensure_ascii=False, indent=4)
    except Exception as e:
        logger.error(f'手机投屏: 保存键位映射失败({e})')
        return False
    _cache['mtime'] = None
    _cache['map'] = None
    logger.info(f'手机投屏: 键位映射已保存 -> {path} ({len(clean)} 个键)')
    return True


def describe() -> str:
    """一行给人看的状态, 用日志里。"""
    mapping = load()
    keys = [k for k in mapping if k in ('`', '1', '2', '3', 'e', 'r', 'f', 'space', 'y')]
    return f'{len(keys)} 个键已映射: {" ".join(sorted(keys))}'


def is_calibrated() -> bool:
    """用户点过校准没有(只有默认的返回键不算)。"""
    _, user = _read_file()
    return bool(user)
