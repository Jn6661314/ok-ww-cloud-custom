import os
import re
from pathlib import Path

from ok import Box, ConfigOption, Icon, Logger
from ok.util.GlobalConfig import create_basic_options
from src.game_launcher import get_game_launch_arguments
from src.phone_mirror import ANDROID_MIRROR_APK_URL, open_android_mirror_apk
from src.phone_mirror_config import (MODE_DESKTOP, MODE_ENGINE,
                                     migrate_phone_mirror_config)
from src.task.process_feature import process_feature
from src.task.task_icons import task_icon

version = "v3.8.18"

logger = Logger.get_logger(__name__)

# 应用启动最早期就把旧的投屏配置并进合并后的菜单。必须在框架读配置之前做完:
# ConfigOption 的名字就是配置文件名, 不迁移的话用户原来的设置会"消失"。
try:
    migrate_phone_mirror_config()
except Exception as e:  # 迁移失败不该挡住启动
    logger.warning(f'迁移手机投屏配置失败: {e}')


def _open_phone_mirror_apk():
    """「下载手机端」按钮的回调: 打开网盘地址。"""
    return open_android_mirror_apk()


def _open_phone_mirror_pairing():
    """「配对手机」按钮: 打开配对窗口, 手机扫码即可。"""
    try:
        from src.phone_mirror_engine import get_engine
        from src.phone_mirror_pairing import open_pairing_dialog
    except Exception as e:
        logger.error(f'手机投屏: 打开配对窗口失败({e})')
        return False
    engine = get_engine()
    # 一定要配对模式: 跑着的是普通内核时, 引擎会自己换成一个配对内核起来,
    # 免得点了「配对手机」却一直等不到二维码。
    engine.pair = True
    if not engine.start():
        logger.error('手机投屏: 投屏内核启动失败')
        return False
    open_pairing_dialog(engine=engine)
    return True


def _start_phone_mirror_engine():
    """「启动投屏内核」按钮: 立刻把内核跑起来(手机上点允许即可出画面)。"""
    try:
        from src.phone_mirror_engine import get_engine
    except Exception as e:
        logger.error(f'手机投屏: 投屏内核启动失败({e})')
        return False
    engine = get_engine()
    engine.pair = False
    if engine.start():
        logger.info('手机投屏: 内核已启动, 等手机上点「允许」。')
        # 顺手把画面窗口开出来: 手机上点「允许」之后就能看到画面。
        try:
            from src.phone_mirror_preview import show_preview
            show_preview(engine)
        except Exception as e:
            logger.debug(f'手机投屏: 打开预览窗口失败({e})')
        return True
    return False


def _open_phone_mirror_keymap():
    """「校准键位」按钮: 在投屏画面上点一下, 把这个位置绑到某个键。

    手游不认按键事件(只认触点), 所以 ok-ww 的 e / 1 / 2 / ` 必须由自己翻译成
    那个位置的触摸 —— 位置因手机而异, 所以让用户点一次。
    """
    try:
        from src.phone_mirror_engine import get_engine
        from src.phone_mirror_keymap_ui import open_calibration_dialog
    except Exception as e:
        logger.error(f'手机投屏: 打开键位校准失败({e})')
        return False
    return open_calibration_dialog(engine=get_engine())


def _open_phone_mirror_preview():
    """「预览画面」按钮: 在电脑上开个小窗口显示手机画面。"""
    try:
        from src.phone_mirror_engine import get_engine
        from src.phone_mirror_preview import show_preview
    except Exception as e:
        logger.error(f'手机投屏: 打开预览窗口失败({e})')
        return False
    return show_preview(get_engine()) is not None


def _find_most_recently_run_pc_exe():
    try:
        import codecs
        import struct
        import winreg
    except ImportError:
        return None

    user_assist_key = r"Software\Microsoft\Windows\CurrentVersion\Explorer\UserAssist"
    candidates = []
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, user_assist_key) as root:
            for index in range(winreg.QueryInfoKey(root)[0]):
                guid = winreg.EnumKey(root, index)
                try:
                    with winreg.OpenKey(root, fr"{guid}\Count") as count_key:
                        for value_index in range(winreg.QueryInfoKey(count_key)[1]):
                            encoded_path, data, _ = winreg.EnumValue(count_key, value_index)
                            path = os.path.expandvars(codecs.decode(encoded_path, "rot_13"))
                            if not path.casefold().endswith(r"\wuthering waves.exe"):
                                continue
                            if not Path(path).is_file():
                                continue
                            last_run = struct.unpack_from("<Q", data, 60)[0] if len(data) >= 68 else 0
                            candidates.append((last_run, path))
                except OSError:
                    continue
    except OSError:
        return None

    return max(candidates, default=(0, None))[1]


def _find_pc_exe_from_registry():
    try:
        import winreg
    except ImportError:
        return None

    uninstall_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    registry_views = (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY)

    for root in (winreg.HKEY_CURRENT_USER, winreg.HKEY_LOCAL_MACHINE):
        for view in registry_views:
            try:
                with winreg.OpenKey(root, uninstall_key, 0, winreg.KEY_READ | view) as key:
                    subkey_count = winreg.QueryInfoKey(key)[0]
                    for index in range(subkey_count):
                        try:
                            subkey_name = winreg.EnumKey(key, index)
                            with winreg.OpenKey(key, subkey_name) as subkey:
                                display_name = _read_registry_value(subkey, "DisplayName", winreg)
                                if not _is_wuthering_waves_registry_entry(subkey_name, display_name):
                                    continue
                                for value_name in (
                                        "InstallPath", "InstallLocation", "LauncherPath",
                                        "DisplayIcon", "UninstallString"):
                                    registered_path = _read_registry_value(subkey, value_name, winreg)
                                    if game_exe := _find_pc_exe_near_registered_path(registered_path):
                                        return game_exe
                        except OSError:
                            continue
            except OSError:
                continue
    return None


def _read_registry_value(key, name, winreg):
    try:
        return str(winreg.QueryValueEx(key, name)[0])
    except OSError:
        return ""


def _is_wuthering_waves_registry_entry(subkey_name, display_name):
    names = f"{subkey_name} {display_name}".casefold()
    return "wuthering waves" in names or "鸣潮" in names or "鳴潮" in names


def _find_pc_exe_near_registered_path(registered_path):
    if not registered_path:
        return None

    path_text = os.path.expandvars(registered_path.strip().strip('"'))
    exe_end = path_text.casefold().find(".exe")
    if exe_end >= 0:
        path_text = path_text[:exe_end + 4]

    registered = Path(path_text)
    install_folder = registered.parent if registered.suffix.casefold() == ".exe" else registered
    candidates = (
        install_folder / "Wuthering Waves.exe",
        install_folder / "Wuthering Waves Game" / "Wuthering Waves.exe",
        install_folder.parent / "Wuthering Waves Game" / "Wuthering Waves.exe",
    )
    for candidate in candidates:
        if candidate.is_file():
            return str(candidate)
    return None


def calculate_pc_exe_path(running_path):
    if running_path is None:
        return _find_most_recently_run_pc_exe() or _find_pc_exe_from_registry()
    game_exe_folder = Path(running_path).parents[3]
    return str(game_exe_folder / "Wuthering Waves.exe")


def blur_area(width, height):
    """Bottom-right region where the game prints the UID (player id).

    Saved screenshots always pass through this box, so a cloud account's UID never
    ends up in a log image.  The Basic Options "Enable Blur" toggle paints the same
    box over the live window (Blur or Inpaint algorithm).  The box reaches the frame
    edges on purpose: on a 16:9 frame the UID occupies roughly 87%..100% x 97.5%..100%,
    and stopping short of the right edge clipped the last digits.
    """
    return Box(width * 0.870, height * 0.975, width * 0.130, height * 0.025)


basic_config_option = create_basic_options(enable_blur=True)

key_config_option = ConfigOption('Game Hotkey', {
    'Echo Key': 'q',
    'Liberation Key': 'r',
    'Resonance Key': 'e',
    'Tool Key': 't',
    'Jump Key': 'space',
    'Dodge Key': 'lshift',
    'Wheel Key': 'tab',
    'Guidebook Key': 'f2',
    'Bag Key': 'b',
}, description='In Game Hotkey for Skills', config_description={
    'Bag Key': 'In-game hotkey used to open the Bag.',
}, show_at_tab=True, icon=Icon.GAME)

char_config_option = ConfigOption('Character Config', {
    'Iuno C6': False,
    'Roccia C6': False,
    'Chisa DPS': False,
    'Suoming DPS': False,
}, description='Character Config', show_at_tab=True, icon=Icon.PEOPLE)

monthly_card_config_option = ConfigOption('Monthly Card Config', {
    'Check Monthly Card': True,
    'Monthly Card Time': 4
}, description='Turn on to avoid interruption by monthly card when executing tasks', config_description={
    'Check Monthly Card': 'Check for monthly card to avoid interruption of tasks',
    'Monthly Card Time': 'Your computer\'s local time when the monthly card will popup, hour in (1-24)'
})

# MuMu/安卓编队配置: 手游右上角是圆形头像(比 PC 头像大约 1.7 倍), PC 头像模板
# 直接固定尺度匹配必然弱匹配(实测 0.62~0.79 抖动), 队伍身份每帧都在漂 ->
# 奶妈/主C/副C 类型乱变, 切人优先级全乱。除了缩放匹配+投票锁定外,
# 允许用户直接手填编队(最高优先级, 完全不做画面识别 —— "编队为准")。
# 手填编队下拉的角色选项(官方英文名, 用下拉选, 不会写错)。与 CharFactory 的
# mismatched_names 官方名一致; 这里用静态列表避免 config.py 顶层 import 角色类
# 造成循环依赖/拖慢启动。要加新角色时同步这里 + CharFactory 即可。
_MUMU_TEAM_CHARACTERS = [
    '', 'Aalto', 'Aemeath', 'Augusta', 'Baizhi', 'Brant', 'Buling', 'Calcharo',
    'Camellya', 'Cantarella', 'Carlotta', 'Cartethyia', 'Changli', 'Chisa', 'Chixia',
    'Ciaccona', 'Danjin', 'Denia', 'Encore', 'Galbrena', 'Hiyuki', 'Hsin', 'Iuno',
    'Jianxin', 'JingRan', 'Jinhsi', 'Jiyan', 'Lily', 'Lingyang', 'Lucilla', 'Lucy',
    'Lumi', 'Lupa', 'Luuk Herssen', 'Lynae', 'Mornye', 'Mortefi', 'Phoebe', 'Phrolova',
    'Qingxiao', 'Qiuyuan', 'Rebecca', 'Roccia', 'Rover', 'Sanhua', 'Shorekeeper',
    'Sigrika', 'Suisui', 'Suoming', 'Taoqi', 'Verina', 'Xiangli Yao', 'Yangyang',
    'Yangyang: Xuanling', 'Yinlin', 'Youhu', 'Yuanwu', 'Zani', 'Zhezhi',
]
android_config_option = ConfigOption('MuMu 安卓 Config', {
    'MuMu 编队': '',
    'MuMu 编队角色1': '',
    'MuMu 编队角色2': '',
    'MuMu 编队角色3': '',
}, description='MuMu 安卓编队(可选, 编队为准): 推荐用下面三个「编队角色」下拉按槽位选, 不会写错名字; 选了就不做画面识别。留空则自动识别并锁定',
    config_type={
        'MuMu 编队角色1': {'type': 'drop_down', 'options': _MUMU_TEAM_CHARACTERS},
        'MuMu 编队角色2': {'type': 'drop_down', 'options': _MUMU_TEAM_CHARACTERS},
        'MuMu 编队角色3': {'type': 'drop_down', 'options': _MUMU_TEAM_CHARACTERS},
    },
    config_description={
        'MuMu 编队角色1': '编队 1 号位(当前出战). 用下拉选角色名, 选「(空)」表示不用此槽位。三个槽位选满 2~3 个即生效, 完全按此编队战斗、不做画面识别',
        'MuMu 编队角色2': '编队 2 号位. 用下拉选, 防止手写角色名出错; 与角色1/3 不要重复',
        'MuMu 编队角色3': '编队 3 号位. 两人队留空即可',
        'MuMu 编队': '兼容旧版: 也可手动填逗号分隔的角色名(中文/英文皆可, 如 渊武,奥古斯塔)。上面的下拉优先于此项; 下拉全空时才用这里',
    }, show_at_tab=True, icon=Icon.PEOPLE)

# 远控/串流窗口(试验性): UU远程 / ToDesk / 向日葵 / Parsec / Moonlight 这类软件把
# 被控电脑的画面显示成本机的一个窗口, 并把本机键鼠转发过去。所以"抓这个窗口 +
# 往里发真实键鼠事件"就等于在操作被控电脑上的游戏。前提是被控电脑上游戏全屏 16:9,
# 且远控窗口客户区也是 16:9 且画面铺满(有黑边就会整体偏移)。
# 注意: 配置名不要带 "/", 框架会把配置存成 configs/<名称>.json, 斜杠会被当成目录
# 分隔符, 于是落到 configs/远控/串流窗口(试验性).json 这种子目录里。
stream_config_option = ConfigOption('远控串流窗口(试验性)', {
    'Enable': False,
    'Preset': 'Manual',
    'Window Title': '',
    'Force Pynput': True,
}, description='把 UU远程 / ToDesk / 向日葵 / Parsec / Moonlight 等远控或串流软件的窗口当作 PC 设备驱动(试验性)。'
              '位置: 左侧导航「游戏」分组最下面(不在「设置」页里)',
   config_type={
       'Preset': {'type': 'drop_down',
                  'options': ['Manual', 'Moonlight', 'UU远程', 'ToDesk', '向日葵', 'Parsec',
                              'NectarLink 手机投屏']},
   },
   config_description={
       'Enable': '开启后设备下拉里只列出标题匹配的远控/串流窗口, 鸣潮 PC 客户端不再出现; 改完需要重启 ok-ww。要求被控电脑上游戏全屏 16:9, 远控窗口客户区也是 16:9 且画面铺满',
       'Preset': '选软件后自动使用内置窗口标题预设, 不用手填正则。Moonlight 匹配的是串流窗口「<主机名> - Moonlight」, 不会误抓主界面; 选「NectarLink 手机投屏」时窗口里是安卓手机画面, 编队识别与切人按安卓端处理(取代 MuMu 模拟器); 选 Manual 时用下面的 Window Title',
       'Window Title': '窗口标题关键字(正则, 忽略大小写), 例如 UU远程 或 ToDesk|SunloginClient|Parsec。与 Preset 同时填写时两者都会匹配; 都留空则不生效',
       'Force Pynput': '远控软件基本不处理窗口消息(PostMessage), 必须用真实键鼠事件, 保持开启',
   }, show_at_tab=True, icon='monitor')

# 手机投屏: 用真机投屏代替 MuMu 模拟器驱动鸣潮。
#
# 有两条路, 用「模式」切换:
#   内置引擎 —— 投屏内核直接编进 ok-ww, 不用装 NectarLink 桌面端。画面由 ok-ww
#               自己决定分辨率/比例, 点击直接变成手机触点(不经过真实鼠标)。
#   桌面端   —— 旧的方案: 画面来自 NectarLink 桌面端开的投屏窗口
#               (标题 "<设备名> · NectarLink"), ok-ww 抓窗口 + 真实键鼠点击,
#               点击由桌面端按屏幕比例转回手机。
#
# 两条路都要把手机画面按安卓端处理(编队识别/切人), 见 src/phone_mirror.py
# 与 BaseWWTask.is_adb。
phone_mirror_option = ConfigOption('手机投屏', {
    'Enable': False,
    '模式': MODE_ENGINE,
    '手机': '',
    '画面宽度': '1920',
    '帧率': '30',
    '码率': '8000000',
    '配对手机': '',
    '启动投屏内核': '',
    '校准键位': '',
    '预览画面': '',
    '下载手机端': '',
    '手机端下载地址': ANDROID_MIRROR_APK_URL,
}, description='用真机投屏代替模拟器驱动鸣潮: 手机画面投到 PC 上, 脚本抓画面并点击, '
              '点击按屏幕比例转回手机, 坐标自动适配缩放/黑边/横竖屏。'
              '模式选「内置引擎」时不需要安装 NectarLink 桌面端(推荐), '
              '画面分辨率/比例完全由 ok-ww 决定; '
              '选「桌面端」则需要先装 NectarLink 桌面端并打开它的投屏窗口。'
              '步骤: 1) 手机装好下面的 NectarLink 客户端; '
              '2) 内置引擎模式点「配对手机」让手机扫码; '
              '3) 开启本选项并重启 ok-ww, 设备下拉里选「手机投屏」。'
              '注意: 每次重新投屏都要在手机上点「允许」, 所以别反复重启 ok-ww。'
              '注意: 配置名不要带 "/", 否则框架会当成目录。',
   config_type={
       '配对手机': {'type': 'button', 'text': '配对手机(扫码)', 'callback': _open_phone_mirror_pairing},
       '启动投屏内核': {'type': 'button', 'text': '启动投屏内核', 'callback': _start_phone_mirror_engine},
       '校准键位': {'type': 'button', 'text': '校准键位(点屏幕)', 'callback': _open_phone_mirror_keymap},
       '预览画面': {'type': 'button', 'text': '投屏状态', 'callback': _open_phone_mirror_preview},
       '下载手机端': {'type': 'button', 'text': '下载手机端(网盘)', 'callback': _open_phone_mirror_apk},
       '模式': {'type': 'drop_down', 'options': [MODE_ENGINE, MODE_DESKTOP]},
       '画面宽度': {'type': 'drop_down', 'options': ['1280', '1600', '1920', '2560']},
       '帧率': {'type': 'drop_down', 'options': ['24', '30', '60']},
   },
   config_description={
       'Enable': '开启后设备下拉里出现「手机投屏」; 改完需要重启 ok-ww',
       '模式': '内置引擎 = ok-ww 自带投屏内核, 不用装 NectarLink 桌面端(推荐); '
              '桌面端 = 抓 NectarLink 桌面端开的投屏窗口(需先装桌面端并打开窗口)',
       '手机': '内置引擎模式: 要投屏的手机(id 前缀或名字); 留空表示只有一台配对手机时自动选',
       '画面宽度': '内置引擎模式: 向手机请求的画面最长边(像素)。1920 对应 1080p, 模板按 1:1 使用最准',
       '帧率': '内置引擎模式: 向手机请求的帧率。30 足够, 60 更跟手但更吃带宽和 CPU',
       '码率': '内置引擎模式: 向手机请求的视频码率(bps)。8000000 = 8 Mbps',
       '配对手机': '打开配对窗口, 手机用 NectarLink 客户端扫码即可配对(只需一次)',
       '启动投屏内核': '立刻把投屏内核跑起来; 手机上点「允许」后就能出画面',
       '校准键位': '打开投屏画面, 逐个点一下「菜单/返回」「切人 1/2/3」「技能 E」等按钮的位置, '
                   'ok-ww 就学会把这些键变成手机触点。手游不认按键事件, 不做这一步'
                   '只有「菜单/返回」能用(位置固定), 技能/切人都会没反应',
       '预览画面': '打开投屏状态窗口(只显示连接状态/窗口置顶, 不显示手机画面); 投屏时不会自动弹窗',
       '下载手机端': '点击打开网盘, 下载 NectarLink 的 Android 客户端(安装到手机上)',
       '手机端下载地址': '手机端客户端的下载地址(网盘分享, 含提取码)。默认已填好, 可自行替换',
   }, show_at_tab=True, icon='monitor')

config = {
    'debug': False,  # Optional, default: False
    'custom_tasks': True,
    "gui": {
        "type": "qt",
    },
    'task_category_icons': {
        'all': task_icon('category-all'),
        'onetime': task_icon('category-onetime'),
        'trigger': task_icon('category-trigger'),
    },
    'task_category_colors': {
        'all': {'light': '#526174', 'dark': '#B5BECF'},
        'onetime': {'light': '#087C70', 'dark': '#72D9CC'},
        'trigger': {'light': '#AC3652', 'dark': '#F09AA8'},
        'group:Daily Activities': {'light': '#2668AA', 'dark': '#8ABCF0'},
        'group:Echo Management': {'light': '#8C651A', 'dark': '#E8C27C'},
        'group:Multi-account': {'light': '#7650A5', 'dark': '#C2A3EA'},
    },
    'config_folder': 'configs',
    'blur_area': blur_area,
    'gui_icon': 'icons/icon.png',
    # 自定义轴（队伍代码/队伍工坊）：ok-ww 历史版本自带，现以自定义页签形式保留。
    'custom_tabs': [
        ["src.gui.CharacterCodeTab", "CharacterCodeTab"],
    ],
    'global_configs': [basic_config_option, key_config_option, char_config_option, monthly_card_config_option,
                       android_config_option, stream_config_option, phone_mirror_option],
    'ocr': {
        'lib': 'onnxocr',
        'auto_simplify': True,
        'params': {
            'use_openvino': True,
            'use_npu': True,
        }
    },
    'plugin': False,
    'my_app': ['src.globals', 'Globals'],
    'start_timeout': 120,  # default 60
    'wait_until_settle_time': 0,
    # required if using feature detection
    'template_matching': {
        'template_folder': os.path.join('assets', 'templates'),
        'default_horizontal_variance': 0.002,
        'default_vertical_variance': 0.002,
        'default_threshold': 0.8,
        'feature_processor': process_feature,
        'vcenter_features': ['monthly_card', 'skip_dialog_check'],
        'hcenter_features': ['monthly_card', 'suisui_forte3', 'message_dialog', 'claim_stamina_sign',
                             'skip_dialog_check', 'skip_quest_confirm', 'skip_quest_confirm_new',
                             'login_close', 'garden_confirm', 'garden_continue_game',
                             'garden_unpause', 'garden_get_gold', 'garden_get_purple', 'garden_get_skip',
                             'garden_not_interested_confirm', 'garden_not_interested', 'a_garden_back',
                             'garden_get_confirm_gray', 'the_garden_max', 'garden_shop_close', 'garden_new_stage',
                             'a_garden_restart', 'suisui_forte2', 'e_forte', 'f_break_full']
    },
    'windows': {  # required  when supporting windows game
        'top_hwnd_class': [re.compile('CAgreementDlg'), re.compile('CLoginDlg_P_'),
                           'CefBrowserWindow', 'Chrome_RenderWidgetHostHWND', '#32770',
                           re.compile('CNativeLoginDlg'), 'Static', 'ComboBox', 'ComboLBox', 'Button'
                           ],
        'calculate_pc_exe_path': calculate_pc_exe_path,
        'launch_arguments': get_game_launch_arguments,
        'exe': 'Client-Win64-Shipping.exe',
        'hwnd_class': 'UnrealWindow',
        'interaction': ['PostMessage', 'Pynput'],
        'capture_method': ['WGC', 'WGC_HDR','BitBlt_RenderFull'],  # Windows版本支持的话, 优先使用WGC, 否则使用BitBlt_Full
        'check_hdr': False,
        'force_no_hdr': False,
        'check_auto_hdr': True,
        'check_night_light': True,
        'force_no_night_light': False,
    },
    # Optional: run the PC game in a Windows child session so tasks never move the
    # user's own mouse or keyboard. Uses the 'windows' settings above to find the game.
    'child_session': {
        'resolution': (1920, 1080),
        'nick': 'Wuthering Waves (Child Session)',
    },
    # 本地安卓模拟器入口（MuMu/雷电等）：ADB 设备会出现在设备选择列表。
    # 抓屏默认走 MuMu IPC（快, 且支持长按重击）；非 MuMu 模拟器没有 ipc 通道时,
    # 框架会自动回退到 adb 抓屏。输入走 ADBInteraction + 真实键盘事件叠加
    # （见 BaseWWTask.send_key）：手游不认 input keyevent, 必须由模拟器键位映射转发。
    'adb': {
        'packages': ['com.kurogame.mingchao', 'com.kurogame.wutheringwaves'],
        'capture_method': 'ipc',
    },
    'browser': {
        'url': 'https://mc.kurogames.com/cloud/#/',
        'resolution': (1920, 1080),
        'channels': ['msedge', 'chrome', 'chromium'],
        'capture': 'webrtc',
        # Keep SDR video in the compositor; direct video overlays clip WGC colors on HDR displays.
        'args': ['--webrtc-ip-handling-policy=default', '--force-color-profile=srgb',
                 '--disable-direct-composition'],
        'nick': '云游戏(需要Win11并安装Chrome或Edge)',
    },
    'window_size': {
        'width': 1200,
        'height': 800,
        'min_width': 1200,
        'min_height': 800,
    },
    'supported_resolution': {
        'ratio': '16:9',
        'resize_to': [(2560, 1440), (1920, 1080), (1600, 900), (1280, 720)],
        'min_size': (1280, 720)
    },
    'links': {
        'default': {
            'github': 'https://github.com/ok-oldking/ok-wuthering-waves',
            'discord': 'https://discord.gg/vVyCatEBgA',
            'faq': 'https://ok-script.com/ok-ww/'
        },
        'zh_CN': {
            'github': 'https://github.com/ok-oldking/ok-wuthering-waves',
            'discord': 'https://discord.gg/vVyCatEBgA',
            'faq': 'https://ok-script.com/ok-ww',
        },
    },
    'about': """
    <p style="color:red;">
    <strong>本软件是免费开源的。</strong> 如果你被收费，请立即退款。
    </p>
    <p style="color:red;">
        <strong>本软件仅供个人使用，用于学习Python编程、计算机视觉、UI自动化等。</strong> 请勿将其用于任何营利性或商业用途。
    </p>
    <p style="color:red;">
        <strong>使用本软件可能会导致账号被封。</strong> 请在了解风险后再使用。
    </p>
""",
    'screenshots_folder': "screenshots",
    'gui_title': 'OK-WW',  # Optional
    'game_name': 'Wuthering Waves',
    # 'coco_feature_folder': get_path(__file__, 'assets/coco_feature'),  # required if using feature detection
    'log_file': 'logs/ok-ww.log',  # Optional, auto rotating every day
    'error_log_file': 'logs/ok-ww_error.log',
    'launcher_log_file': 'logs/launcher.log',
    'launcher_error_log_file': 'logs/launcher_error.log',
    'version': version,
    'onetime_tasks': [  # tasks to execute
        # 日常任务只注册一次: DailyTask 会按所选设备(PC/云鸣潮/MuMu)自动切换操作方式。
        # MuMu 专用入口 src/task/AndroidDailyTask.py 保留给"想显式确认设备"的用户,
        # 默认不注册, 避免任务列表里出现两个每日任务。
        ["src.task.DailyTask", "DailyTask"],
        ["src.task.GalGameTask", "GalGameTask"],
        ["src.task.RahaiBlocksTask", "RahaiBlocksTask"],
        ["src.task.FarmEchoTask", "FarmEchoTask"],
        ["src.task.NightmareNestTask", "NightmareNestTask"],
        ["src.task.TacetTask", "TacetTask"],
        ["src.task.ForgeryTask", "ForgeryTask"],
        ["src.task.SimulationTask", "SimulationTask"],
        ["src.task.CultivationTask", "CultivationTask"],
        ["src.task.MultiAccountDailyTask", "MultiAccountDailyTask"],
        ["src.task.MultiAccountConfigTask", "MultiAccountConfigTask"],
        ["src.task.MergeEchoTask", "MergeEchoTask"],
        ["src.task.EnhanceEchoTask", "EnhanceEchoTask"],
        ["src.task.ChangeEchoTask", "ChangeEchoTask"],
        ["src.task.GardenTask", "GardenTask"],
        # ["src.task.DiagnosisTask", "DiagnosisTask"],
    ], 'trigger_tasks': [
        ["src.task.AutoCombatTask", "AutoCombatTask"],
        ["src.task.AutoPickTask", "AutoPickTask"],
        ["src.task.AutoLoginTask", "AutoLoginTask"],
        ["src.task.SkipDialogTask", "AutoDialogTask"],
        ["src.task.FastTravelTask", "FastTravelTask"],
        ["src.task.MouseResetTask", "MouseResetTask"],
    ], 'scene': ["src.scene.WWScene", "WWScene"],
    'update_pyappify': {
        'to_version': '1.2.3',
        'zip_url': 'https://github.com/ok-oldking/ok-wuthering-waves/releases/download/v3.5.30/ok-ww-win32.zip',
        'sha256': '447207edbfb6944beb994347048e155df99775eb18c87dcae54dda125071c94a',
    }

}
