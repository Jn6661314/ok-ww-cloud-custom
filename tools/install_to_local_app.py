"""Install the cloud multi-account feature into a local ok-ww installation.

The pyappify build keeps its running Python source in
``%LOCALAPPDATA%/ok-ww/data/apps/ok-ww/working``.  This script copies the new
modules there and applies the same small, idempotent edits to the local copies
of ``config.py``, ``MultiAccountConfigStore.py`` and ok-script's browser
capture.  Every modified file is backed up with a ``.pre-cloud`` suffix.

Usage::

    python tools/install_to_local_app.py [path/to/working]

Run it while ok-ww is closed, then start the app normally.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
SOURCE = HERE.parent
DEFAULT_WORKING = (Path.home() / 'AppData' / 'Local' / 'ok-ww' / 'data'
                   / 'apps' / 'ok-ww' / 'working')

NEW_FILES = [
    ('src/cloud_browser.py', 'src/cloud_browser.py'),
    ('src/cloud_recovery.py', 'src/cloud_recovery.py'),
    ('src/task/CloudDailyTask.py', 'src/task/CloudDailyTask.py'),
    ('src/task/CloudMultiAccountTask.py', 'src/task/CloudMultiAccountTask.py'),
    ('src/task/SaveCloudAccountCookieTask.py', 'src/task/SaveCloudAccountCookieTask.py'),
    ('src/task/SwitchCloudAccountTask.py', 'src/task/SwitchCloudAccountTask.py'),
    ('src/task/RahaiBlocksTask.py', 'src/task/RahaiBlocksTask.py'),
    ('src/task/DailyTask.py', 'src/task/DailyTask.py'),
    ('src/task/account/MultiAccountConfigStore.py', 'src/task/account/MultiAccountConfigStore.py'),
    ('src/gui/MultiAccountConfigTab.py', 'src/gui/MultiAccountConfigTab.py'),
    ('src/gui/MultiAccountConfigDialog.py', 'src/gui/MultiAccountConfigDialog.py'),
    # Restored from upstream history: custom team code (自定义轴) + team workshop.
    ('src/gui/CharacterCodeTab.py', 'src/gui/CharacterCodeTab.py'),
    ('src/char/CustomCharLoader.py', 'src/char/CustomCharLoader.py'),
    ('src/char/CharFactory.py', 'src/char/CharFactory.py'),
    ('src/task/BaseCombatTask.py', 'src/task/BaseCombatTask.py'),
]

# Upstream deleted the workshop hosts.  The community mirror snapshot lives in
# the backup folder and is copied into configs so the workshop opens offline.
WORKSHOP_CACHE_SOURCE = SOURCE / 'workshop_cache'

CONFIG_EDITS = [
    ("    'global_configs': [basic_config_option, key_config_option, char_config_option, monthly_card_config_option],\n",
     "    'global_configs': [basic_config_option, key_config_option, char_config_option, monthly_card_config_option],\n"
     "    # Restored from the historical version: custom team code (自定义轴) + team workshop page.\n"
     "    'custom_tabs': [\n"
     "        [\"src.gui.CharacterCodeTab\", \"CharacterCodeTab\"],\n"
     "    ],\n"),
    ("from src.game_launcher import get_game_launch_arguments",
     "from src import cloud_browser\nfrom src.game_launcher import get_game_launch_arguments"),
    ("        'nick': '云游戏(需要Win11并安装Chrome或Edge)',",
     "        # Evaluated at launch time so per-account cookie profiles are honoured.\n"
     "        'user_data_dir': cloud_browser.current_profile_dir,\n"
     "        'nick': '云游戏(需要Win11并安装Chrome或Edge)',"),
    ('        ["src.task.DailyTask", "DailyTask"],',
     '        ["src.task.DailyTask", "DailyTask"],\n'
     '        ["src.task.CloudDailyTask", "CloudDailyTask"],'),
    ('        ["src.task.MultiAccountConfigTask", "MultiAccountConfigTask"],',
     '        ["src.task.MultiAccountConfigTask", "MultiAccountConfigTask"],\n'
     '        ["src.task.CloudMultiAccountTask", "CloudMultiAccountTask"],'),
    ('        ["src.task.CloudMultiAccountTask", "CloudMultiAccountTask"],',
     '        ["src.task.CloudMultiAccountTask", "CloudMultiAccountTask"],\n'
     '        ["src.task.SaveCloudAccountCookieTask", "SaveCloudAccountCookieTask"],'),
    ('        ["src.task.SaveCloudAccountCookieTask", "SaveCloudAccountCookieTask"],',
     '        ["src.task.SaveCloudAccountCookieTask", "SaveCloudAccountCookieTask"],\n'
     '        ["src.task.SwitchCloudAccountTask", "SwitchCloudAccountTask"],'),
]

STORE_TASKS = [
    ('src.task.MultiAccountDailyTask', 'MultiAccountDailyTask'),
    ('src.task.MultiAccountConfigTask', 'MultiAccountConfigTask'),
    ('src.task.CloudMultiAccountTask', 'CloudMultiAccountTask'),
    ('src.task.SaveCloudAccountCookieTask', 'SaveCloudAccountCookieTask'),
    ('src.task.SwitchCloudAccountTask', 'SwitchCloudAccountTask'),
]
STORE_FINAL = ("MULTI_ACCOUNT_TASKS = {\n"
               + ''.join(f"    ('{module}', '{cls}'),\n" for module, cls in STORE_TASKS)
               + "}")


def backup(path: Path) -> None:
    target = path.with_suffix(path.suffix + '.pre-cloud')
    if not target.exists():
        shutil.copy2(path, target)
        print(f'backup:  {target}')


def edit_once(path: Path, old: str, new: str) -> bool:
    text = path.read_text(encoding='utf-8')
    if new in text:
        return False
    if text.count(old) != 1:
        raise RuntimeError(f'{path}: expected one match for {old[:60]!r}, got {text.count(old)}')
    backup(path)
    path.write_text(text.replace(old, new), encoding='utf-8')
    print(f'edited:  {path}')
    return True


def install(working: Path) -> int:
    if not working.is_dir():
        print(f'Not installed: {working} does not exist')
        return 1
    print(f'Target: {working}')

    for relative, destination in NEW_FILES:
        source = SOURCE / relative
        target = working / destination
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            backup(target)
        shutil.copy2(source, target)
        print(f'copied:  {target}')

    if WORKSHOP_CACHE_SOURCE.is_dir():
        cache_target = working / 'configs' / 'workshop_cache'
        cache_target.mkdir(parents=True, exist_ok=True)
        shutil.copytree(WORKSHOP_CACHE_SOURCE, cache_target, dirs_exist_ok=True)
        print(f'copied workshop snapshot: {cache_target}')

    for old, new in CONFIG_EDITS:
        edit_once(working / 'config.py', old, new)
    store_py = working / 'src/task/account/MultiAccountConfigStore.py'
    store_text = store_py.read_text(encoding='utf-8')
    if STORE_FINAL not in store_text:
        # Replace the whole registry block regardless of how many earlier
        # (partial) edits were applied, so re-running after an update is safe.
        import re
        pattern = re.compile(r"MULTI_ACCOUNT_TASKS = \{.*?\n\}", re.S)
        if not pattern.search(store_text):
            raise RuntimeError(f'{store_py}: cannot locate MULTI_ACCOUNT_TASKS block')
        backup(store_py)
        store_py.write_text(pattern.sub(STORE_FINAL, store_text, count=1), encoding='utf-8')
        print(f'edited:  {store_py}')

    browser_py = working / 'ok/device/capture_methods/browser.py'
    from patch_ok_script_browser import patch as patch_profile
    from patch_ok_script_background import patch as patch_background
    if patch_profile(browser_py) or patch_background(browser_py):
        return 1

    # Cloud entry fix: throttle "进入游戏" clicks + detect entry completion.
    # Patch in place (not copy) so version-specific local code is preserved.
    from patch_baseww_cloud_ready import patch as patch_cloud_ready
    from patch_baseww_cloud_ready import patch_monthly_guard
    if patch_cloud_ready(working / 'src/task/BaseWWTask.py'):
        return 1
    # 月卡误判守卫: 领邮件后 is_main 会把邮箱奖励图标误判为月卡导致卡死。
    if patch_monthly_guard(working / 'src/task/BaseWWTask.py'):
        return 1

    print('\nDone. Start ok-ww, select the 云游戏 device, then run CloudMultiAccountTask.')
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('working', nargs='?', type=Path, default=DEFAULT_WORKING)
    return install(parser.parse_args(argv).working)


if __name__ == '__main__':
    raise SystemExit(main())
