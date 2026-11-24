"""一键恢复 ok-ww 云鸣潮定制修改。

当 ok-ww 自动更新覆盖了我们修改的文件后，运行本脚本即可把所有定制代码
恢复到运行目录（working）和源码目录（repo）两处。

恢复前会自动把当前文件备份到一个带时间戳的目录，可随时回退。

用法::

    python restore.py                      # 恢复默认安装位置的 working + repo
    python restore.py "D:/some/working"    # 恢复自定义 working 目录
    python restore.py --no-backup          # 不备份当前文件（谨慎）
    python restore.py --working-only       # 只恢复 working，不碰 repo
"""

from __future__ import annotations

import argparse
import datetime
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = HERE  # 本仓库根目录即"最终生效文件"目录

DEFAULT_BASE = (Path.home() / 'AppData' / 'Local' / 'ok-ww'
                / 'data' / 'apps' / 'ok-ww')

# 我们改动/新增的全部文件（相对 working / repo 根目录）
RELATIVE_FILES = [
    'config.py',
    'ok/device/capture_methods/browser.py',
    'src/cloud_browser.py',
    'src/cloud_recovery.py',
    'src/task/CloudDailyTask.py',
    'src/task/CloudMultiAccountTask.py',
    'src/task/SaveCloudAccountCookieTask.py',
    'src/task/SwitchCloudAccountTask.py',
    'src/task/RahaiBlocksTask.py',
    'src/task/DailyTask.py',
    'src/task/BaseWWTask.py',
    'src/task/account/MultiAccountConfigStore.py',
    'src/gui/MultiAccountConfigTab.py',
    'src/gui/MultiAccountConfigDialog.py',
    # 从上游历史恢复: 自定义编队代码(自定义轴) + 队伍工坊
    'src/gui/CharacterCodeTab.py',
    'src/char/CustomCharLoader.py',
    'src/char/CharFactory.py',
    'src/task/BaseCombatTask.py',
    # 怪物消失后自动退出战斗
    'src/combat/CombatCheck.py',
    # Win10 云鸣潮兼容 (WGC 可用性门禁 + 去除黄色边框)
    'ok/util/window.py',
    'ok/device/capture_methods/windows_graphics.py',
    # ADB/触屏模式下 esc 映射为安卓返回键
    'ok/device/interaction_methods/keys.py',
    # v3.8.14 官方新增: 合并版 browser.py 依赖的 WebRTC 抓屏模块
    'ok/device/capture_methods/browser_webrtc.py',
]


def restore_to(dest: Path, stamp: str, do_backup: bool, label: str) -> int:
    if not dest.is_dir():
        print(f'[跳过] {label} 目录不存在: {dest}')
        return 0

    restored = 0
    backed_up = 0
    backup_root = dest.parent / f'custom-backup-before-restore-{stamp}' / label

    for rel in RELATIVE_FILES:
        source = FILES / rel
        target = dest / rel
        if not source.is_file():
            print(f'[警告] 备份中缺少文件: {source}')
            continue
        try:
            if do_backup and target.is_file():
                keeper = backup_root / rel
                keeper.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(target, keeper)
                backed_up += 1
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            restored += 1
        except OSError as error:
            print(f'[失败] {target}: {error}')
            print('        请先关闭 ok-ww 再重试。')
            return 1

    print(f'[{label}] 恢复 {restored} 个文件' +
          (f'，当前文件已备份到 {backup_root}' if backed_up else '，无需备份当前文件'))
    return 0


def restore_workshop_cache(working: Path, stamp: str, do_backup: bool) -> int:
    """Restore the offline workshop snapshot into working/configs/workshop_cache."""
    source = HERE / 'workshop_cache'
    if not source.is_dir():
        print('[跳过] 备份中没有工坊离线快照')
        return 0
    target = working / 'configs' / 'workshop_cache'
    try:
        if do_backup and target.is_dir():
            keeper = working.parent / f'custom-backup-before-restore-{stamp}' / 'working' / 'configs' / 'workshop_cache'
            keeper.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(target, keeper, dirs_exist_ok=True)
        target.mkdir(parents=True, exist_ok=True)
        shutil.copytree(source, target, dirs_exist_ok=True)
    except OSError as error:
        print(f'[失败] 工坊离线快照 {target}: {error}')
        return 1
    print(f'[working] 已恢复工坊离线快照 -> {target}')
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('working', nargs='?', type=Path,
                        default=DEFAULT_BASE / 'working',
                        help='working 目录（默认自动检测）')
    parser.add_argument('--repo', type=Path, default=DEFAULT_BASE / 'repo',
                        help='repo 目录（默认自动检测）')
    parser.add_argument('--no-backup', action='store_true',
                        help='恢复前不备份当前文件')
    parser.add_argument('--working-only', action='store_true',
                        help='只恢复 working，不恢复 repo')
    args = parser.parse_args(argv)

    if not FILES.is_dir():
        print(f'[错误] 找不到备份文件目录: {FILES}')
        return 1

    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    print(f'恢复时间戳: {stamp}')
    print(f'备份来源:   {FILES}')
    print('')

    if restore_to(args.working, stamp, not args.no_backup, 'working'):
        return 1
    if restore_workshop_cache(args.working, stamp, not args.no_backup):
        return 1
    if not args.working_only:
        if restore_to(args.repo, stamp, not args.no_backup, 'repo'):
            return 1

    print('')
    print('恢复完成。请启动 ok-ww，选择「云游戏」设备后运行云鸣潮任务。')
    print('账号 Cookie（cloud_profiles）和任务配置（configs）未改动，无需重新配置。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
