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

logger = Logger.get_logger(__name__)

# 与 config.py 中的 ConfigOption 名称保持一致(不要带 "/", 否则配置会落到子目录里)
STREAM_CONFIG_NAME = '远控串流窗口(试验性)'


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
        title = str(option.get('Window Title', '') or '').strip()
        force_pynput = bool(option.get('Force Pynput', True))
    except Exception as e:
        logger.warning(f'read stream window config failed: {e}')
        return None
    return enabled, title, force_pynput


def apply_stream_window(global_config=None, device_manager=None):
    """把远控/串流窗口切换成当前设备; 未启用或配置不全时返回 False。"""
    settings = stream_window_settings(global_config)
    if not settings:
        return False
    enabled, title, force_pynput = settings
    if not enabled:
        return False
    if not title:
        logger.info('远控/串流窗口已开启但没填窗口标题, 继续使用默认 PC 设备。')
        return False
    if device_manager is None:
        logger.warning('远控/串流窗口: 取不到 device_manager, 跳过。')
        return False
    setter = getattr(device_manager, 'set_stream_window', None)
    if setter is None:
        logger.warning('远控/串流窗口: 当前框架版本不支持, 跳过。')
        return False
    if not setter(title, force_pynput=force_pynput):
        return False
    logger.info(f'远控/串流窗口模式已启用: 标题匹配 "{title}", 输入方式 '
                f'{"Pynput(真实键鼠)" if force_pynput else "由框架决定"}。'
                f'请确认被控电脑上游戏全屏 16:9, 且远控窗口客户区也是 16:9 无黑边。')
    return True
