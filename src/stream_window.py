"""试验性: 把远控 / 串流软件窗口当作 ok-ww 的 PC 设备。

UU远程 / ToDesk / 向日葵 / Parsec / Moonlight 这类软件, 本质是把被控电脑的画面
显示成本机的一个窗口, 再把本机的键鼠事件转发过去。因此只要做两件事:

  1. 抓这个窗口的画面(走 windows 抓屏, 与 PC 客户端完全同一条链路);
  2. 往这个窗口发真实键鼠事件(Pynput, 远控软件基本不处理窗口消息);

就等于在操作被控电脑上的游戏, 不需要任何"远程"专用逻辑。

硬性前提(不满足就会坐标偏移 / 识图失败, 启动时会检查并告警):

  * 被控电脑: 游戏必须**全屏**运行, 且分辨率是 16:9
    (1920x1080 / 2560x1440 / 1600x900 / 1280x720 之一);
  * 远控软件: 画质选"原画 / 原始分辨率", 不要用"自适应 / 缩放填充";
  * 本机窗口: 客户区必须是 16:9 且画面铺满, 出现黑边会被裁切或整体偏移;
  * 窗口不要最小化, 也不要在游戏时被其它窗口遮挡(远控软件通常只在前台时转发按键)。

已知限制:
  * 远控软件自身有延迟和压缩, 识图阈值可能要比本地 PC 放宽;
  * 若远控端把鼠标做成"相对移动/锁定", 点击会偏移, 需要改成绝对定位模式;
  * 同一时间只能启用一个窗口(开启后鸣潮 PC 客户端不再出现在设备列表里)。
"""

from ok import Logger

from src.phone_mirror import NECTARLINK_WINDOW_PATTERN

logger = Logger.get_logger(__name__)

# 与 config.py 中的 ConfigOption 名称保持一致(不要带 "/", 否则配置会落到子目录里)
STREAM_CONFIG_NAME = '远控串流窗口(试验性)'

# 常见远控/串流软件的窗口标题预设(正则, 匹配时忽略大小写)。
# Moonlight 客户端的串流窗口标题由源码 app/streaming/session.cpp 拼成
# 「<计算机名> - Moonlight」, 主界面窗口只叫 Moonlight; 这里只匹配串流窗口,
# 避免误抓主界面。其余软件用窗口类/程序名兜底, 也可在 Window Title 里手填覆盖。
TITLE_PRESETS = {
    'Manual': '',
    'Moonlight': r'\S.*\s+-\s+Moonlight$',
    'UU远程': r'UU远程',
    'ToDesk': r'ToDesk',
    '向日葵': r'SunloginClient|向日葵',
    'Parsec': r'Parsec',
    # NectarLink 的手机投屏窗口标题是「<设备名> · NectarLink」
    # (见 desktop/app/qml/MirrorWindow.qml 的 title 属性)。
    'NectarLink 手机投屏': NECTARLINK_WINDOW_PATTERN.pattern,
}

# 手机投屏(NectarLink)预设名。这个模式下窗口代表的是**手机**而不是被控电脑,
# 因此设备要按安卓端处理(编队识别/切人键位/大世界判定都走安卓分支)。
PHONE_MIRROR_PRESET = 'NectarLink 手机投屏'


def is_phone_mirror(preset) -> bool:
    """该预设是否为「手机投屏」(窗口里是安卓手机画面)。"""
    return str(preset or '').strip() == PHONE_MIRROR_PRESET


def preset_title(preset) -> str:
    """取预设对应的标题正则; 未知预设返回空串。"""
    return TITLE_PRESETS.get(str(preset or '').strip(), '')


def resolve_title(preset, manual) -> str:
    """预设 + 手填标题合成最终正则(忽略大小写由 DeviceManager 负责)。"""
    pattern = preset_title(preset)
    custom = str(manual or '').strip()
    if pattern and custom:
        return f'(?:{pattern})|(?:{custom})'
    return pattern or custom


def stream_window_settings(global_config):
    """读取远控/串流窗口设置, 返回 (enabled, title, force_pynput) 或 None。"""
    if global_config is None:
        return None
    try:
        option = global_config.get_config(STREAM_CONFIG_NAME)
    except Exception as e:
        logger.debug(f'stream window config not available: {e}')
        return None
    try:
        enabled = bool(option.get('Enable', False))
        title = resolve_title(option.get('Preset'), option.get('Window Title'))
        force_pynput = bool(option.get('Force Pynput', True))
    except Exception as e:
        logger.warning(f'read stream window config failed: {e}')
        return None
    return enabled, title, force_pynput


def stream_window_phone_mode(global_config):
    """当前预设是否为「手机投屏」(窗口里是安卓手机画面)。

    手机投屏(NectarLink)要按安卓端处理, 才能复用安卓的编队识别/切人逻辑。
    单独一个函数, 保持 stream_window_settings 的返回结构不变。
    """
    if global_config is None:
        return False
    try:
        option = global_config.get_config(STREAM_CONFIG_NAME)
        return is_phone_mirror(option.get('Preset'))
    except Exception as e:
        logger.debug(f'read stream window phone mode failed: {e}')
        return False


def apply_stream_window(global_config=None, device_manager=None, title=None, phone=None):
    """把远控/串流窗口切换成当前设备; 未启用或配置不全时返回 False。

    Args:
        global_config: 全局配置。传 None 表示"不读配置", 直接用下面两个参数。
        device_manager: 设备管理器。
        title: 窗口标题正则。给了就用它, 不读配置里的 Preset/Window Title。
        phone: True 表示窗口里是安卓手机画面。给了就用它, 不读配置里的 Preset。
    """
    if title is not None or phone is not None:
        # 直接指定了窗口和模式(手机投屏的桌面端模式就是这么用的): 不看配置。
        settings = None
    else:
        settings = stream_window_settings(global_config)
    if settings is None and title is None:
        return False
    if settings is not None:
        enabled, config_title, force_pynput = settings
        if not enabled:
            return False
    else:
        config_title, force_pynput = '', True
    if title is None:
        title = config_title
    if phone is None:
        phone = stream_window_phone_mode(global_config)
    if device_manager is None:
        logger.warning('远控/串流窗口: 取不到 device_manager, 跳过。')
        return False
    setter = getattr(device_manager, 'set_stream_window', None)
    if setter is None:
        logger.warning('远控/串流窗口: 当前框架版本不支持, 跳过。')
        return False
    # 未填标题也启用: 进入"列出所有窗口"模式, 让用户在设备下拉里手动选远控窗口,
    # 而不是静默退回默认 PC 客户端(那样下拉里根本看不到远控窗口)。
    try:
        ok = setter(title or None, force_pynput=force_pynput, phone=phone)
    except TypeError:
        # 旧版 DeviceManager 没有 phone 参数(框架未升级时), 退回普通远控模式。
        ok = setter(title or None, force_pynput=force_pynput)
    if not ok:
        return False
    if phone:
        logger.info('远控/串流窗口模式已启用: NectarLink 手机投屏(安卓端)。'
                    '画面抓自投屏窗口, 点击会由 NectarLink 转到手机屏幕; '
                    '编队识别与切人按安卓端处理。请确认投屏窗口里是鸣潮画面。')
        return True
    if title:
        logger.info(f'远控/串流窗口模式已启用: 标题匹配 "{title}", 输入方式 '
                    f'{"Pynput(真实键鼠)" if force_pynput else "由框架决定"}。'
                    f'请确认被控电脑上游戏全屏 16:9, 且远控窗口客户区也是 16:9 无黑边。')
    else:
        logger.info('远控/串流窗口模式已启用(未填标题): 设备下拉会列出所有可见窗口, '
                    '请从中选远控/串流窗口; 建议填 Preset 或 Window Title 以便自动匹配。'
                    '请确认被控电脑上游戏全屏 16:9, 且远控窗口客户区也是 16:9 无黑边。')
    return True
