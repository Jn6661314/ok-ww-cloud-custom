"""手机投屏(NectarLink)支持: 下载入口 + 投屏窗口识别。

用户想把手机画面投到 PC 上驱动鸣潮, 取代模拟器。NectarLink 的桌面端会把
手机画面开成一个独立窗口(标题 "<设备名> · NectarLink"), 并把鼠标点击按
**屏幕比例**转发到手机 —— 因此只要把这个窗口当普通 Windows 窗口抓屏 + 点击,
就能操作手机, 且坐标自动适配缩放/黑边/横竖屏。

本模块提供:
  * ANDROID_MIRROR_APK_URL: 手机端(Android APK)下载地址(网盘分享)。
  * open_android_mirror_apk(): 打开下载地址, 给配置界面的下载按钮用。
  * is_nectarlink_window(title): 判断某个窗口标题是不是 NectarLink 投屏窗口。
"""

import re
import webbrowser

# 手机端 APK 的下载地址(网盘分享, 含提取码)。
ANDROID_MIRROR_APK_URL = 'https://pan.baidu.com/s/13Y-rkKtfp7EQHd4SJwdzDA?pwd=Jn66'

# NectarLink 桌面端投屏窗口标题: "<设备名> · NectarLink"
# (见 nectarlink desktop/app/qml/MirrorWindow.qml 的 title 属性)
NECTARLINK_WINDOW_PATTERN = re.compile(r'\S.*\s+·\s+NectarLink$')


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
