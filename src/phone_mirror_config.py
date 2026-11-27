"""手机投屏配置的迁移: 把两个旧菜单的配置并进合并后的「手机投屏」。

背景
----
ok-ww 里曾经有两个手机投屏相关的配置菜单:

  * 「手机投屏(NectarLink)」—— 走外部安装的 NectarLink 桌面端, 画面来自它开的
    投屏窗口(标题 "<设备名> · NectarLink");
  * 「手机投屏(内置引擎)」—— 走 ok-ww 自带的投屏内核, 不用再装桌面端。

两者功能重叠(旧菜单只有一个下载入口, 新菜单已经把它包了), 所以合并成一个
「手机投屏」菜单, 里面用「模式」下拉切换走哪条路。

为什么要迁移
------------
框架里 ConfigOption 的**名字就是配置文件名** (``configs/<名字>.json``)。
菜单一改名, 框架就会去找新名字对应的文件, 用户在旧文件里设的值(比如
Enable=True、画面宽度、帧率)就"消失"了 —— 表现为改了配置却没生效, 或者
投屏莫名其妙不启动了。

所以这里在应用启动最早期(config 模块被导入时)做一次迁移: 把旧的两个 JSON
文件合并写进新文件, 顺便把旧文件删掉(留着只会让人以为还有效)。旧文件里的
键都是新菜单的键, 只有「模式」是新增的, 按需补默认值。

迁移规则
--------
  * 新文件已存在 —— 以新文件为准, 只清理旧文件(不覆盖用户已经改过的新配置);
  * 新文件不存在 —— 用旧文件的内容合成新文件(引擎那份优先, 桌面端那份补缺);
  * 「模式」缺失时, 若旧配置里引擎是开着的就选「内置引擎」, 否则选「桌面端」。
"""

import json
import os
import shutil
import sys

# 合并后的菜单名(与 config.py 里的 ConfigOption 一致)。
# 注意: 这里刻意不叫 *_CONFIG_NAME —— 那三个旧名字是历史名, 已经不再注册成
# 配置项了, 而框架有个一致性检查会要求所有 *_CONFIG_NAME 常量都已注册。
NEW_MENU_NAME = '手机投屏'

# 迁移前的两个菜单名。
OLD_ENGINE_MENU_NAME = '手机投屏(内置引擎)'
OLD_DESKTOP_MENU_NAME = '手机投屏(NectarLink)'

# 两种模式。
MODE_ENGINE = '内置引擎'
MODE_DESKTOP = '桌面端'


def _config_dir() -> str:
    """配置文件所在目录。

    必须和框架的取法一致: ``Config`` 用 ``get_relative_path(config_folder, name)``,
    而 ``get_relative_path`` 是 **cwd 相对** 的(不是 exe 相对)。两边取法不一样的话,
    迁移会去另一个目录找文件, 用户已有的设置就丢了。
    """
    base = os.environ.get('OKWW_CONFIG_DIR')
    if base:
        return base
    try:
        from ok.util.config import Config
        from ok.util.file import get_relative_path
        return get_relative_path(Config.config_folder)
    except Exception:
        return os.path.join(os.getcwd(), 'configs')


def _path(name: str) -> str:
    return os.path.join(_config_dir(), f'{name}.json')


def _read(name: str):
    """读一个配置文件; 不存在或坏了就返回 None。"""
    path = _path(name)
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        return data if isinstance(data, dict) else None
    except Exception:
        return None


def _write(name: str, data: dict) -> bool:
    path = _path(name)
    try:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=4)
        return True
    except Exception:
        return False


def _pick_mode(engine: dict, desktop: dict) -> str:
    """猜一个合适的模式: 引擎那份开着就用引擎, 否则桌面端。"""
    if engine and engine.get('Enable'):
        return MODE_ENGINE
    if desktop:
        return MODE_DESKTOP
    return MODE_ENGINE


def is_real_startup() -> bool:
    """现在是不是真正的应用启动(而不是测试导入)。

    迁移会动用户真实的配置文件, 所以只在真正启动 ok-ww 时做:
    判据是命令行入口 —— 正式启动是 main.py / ok-ww.exe, 测试跑的是
    unittest / pytest。测试自己会设 OKWW_CONFIG_DIR 指到临时目录, 但
    没必要让它们去碰用户真实的配置。
    """
    if os.environ.get('OKWW_FORCE_MIGRATION') == '1':
        return True
    argv0 = os.path.basename(sys.argv[0] if sys.argv else '').lower()
    if argv0 in ('main.py', 'main_debug.py', 'ok-ww.exe', 'ok-ww', 'ok_ww.exe'):
        return True
    return False


def migrate_phone_mirror_config(verbose: bool = True) -> bool:
    """把旧的两个投屏配置并进「手机投屏」。返回是否发生了迁移。"""
    if not is_real_startup():
        return False
    engine = _read(OLD_ENGINE_MENU_NAME)
    desktop = _read(OLD_DESKTOP_MENU_NAME)
    if engine is None and desktop is None:
        return False

    new = _read(NEW_MENU_NAME)
    if new is None:
        # 新文件还没有: 用旧配置合成一份。
        merged = {}
        if desktop:
            merged.update(desktop)
        if engine:
            merged.update(engine)
        new = merged
        new.setdefault('模式', _pick_mode(engine or {}, desktop or {}))
        if not _write(NEW_MENU_NAME, new):
            return False
        if verbose:
            print('[手机投屏] 已把旧配置合并到「手机投屏」')
    elif verbose:
        print('[手机投屏] 已存在合并后的配置, 保留新配置, 清理旧文件')

    # 旧文件留着只会让人以为还有效(而且下次迁移会被当成"已存在"), 删掉。
    for name in (OLD_ENGINE_MENU_NAME, OLD_DESKTOP_MENU_NAME):
        path = _path(name)
        try:
            if os.path.exists(path):
                os.remove(path)
                if verbose:
                    print(f'[手机投屏] 已删除旧配置文件 {os.path.basename(path)}')
        except Exception:
            pass
    return True


def cleanup_legacy_configs() -> None:
    """只删旧文件, 不做迁移(旧文件已经手工处理过时用)。"""
    for name in (OLD_ENGINE_MENU_NAME, OLD_DESKTOP_MENU_NAME):
        path = _path(name)
        try:
            if os.path.exists(path):
                os.remove(path)
        except Exception:
            pass


def backup_config(name: str) -> str:
    """备份一个配置文件, 返回备份路径(失败返回空串)。"""
    path = _path(name)
    if not os.path.exists(path):
        return ''
    backup = path + '.bak'
    try:
        shutil.copy2(path, backup)
        return backup
    except Exception:
        return ''
