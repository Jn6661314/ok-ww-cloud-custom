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
# 基线：官方 ok-ww v3.8.15（ok-script 3.0.14）。只保留云端（云鸣潮）相关的
# 定制 + 少量通用修复；MuMu/安卓相关改动在 legacy-mumu-v1.5.21 分支上，未合并。
RELATIVE_FILES = [
    'config.py',
    # 框架最小补丁：CDP 调用超时（防云游戏假死卡住任务）+ 后台输入。
    # 其余框架改动已全部回退，避免与官方 ok-script 分叉。
    'ok/device/capture_methods/browser.py',
    # 云鸣潮：每个账号一个浏览器 profile（纯 okww 侧目录切换，不改框架）
    'src/cloud_browser.py',
    'src/cloud_recovery.py',
    # 多账号：云游戏分支 + 「保存登录状态/切换账号」按钮（仅云设备显示）
    'src/task/MultiAccountDailyTask.py',
    'src/task/account/MultiAccountConfigStore.py',
    'src/gui/MultiAccountConfigTab.py',
    'src/gui/MultiAccountConfigDialog.py',
    # 云鸣潮适配：活跃度读不到时不按 0 处理；先约电台在浏览器下不吞 Alt
    'src/task/DailyTask.py',
    # 官方 v3.8.15 的拉海洛方块（未含无尽模式）；搜索预算修复在 rahai_blocks.py
    'src/task/RahaiBlocksTask.py',
    'src/task/rahai_blocks.py',
    # 爱弥斯：变奏入场就输出（上游要求双队友满协奏退场, 实战几乎不成立）
    'src/char/Aemeath.py',
    # 自定义轴（队伍代码/工坊）
    'src/gui/CharacterCodeTab.py',
    'src/char/CustomCharLoader.py',
    'src/char/CharFactory.py',
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
    print('恢复完成。请启动 ok-ww，选设备「云游戏」后照常运行日常/多账号任务；')
    print('多账号任务的设置页在云设备下会多出「保存登录状态」「切换账号」两个按钮。')
    print('账号 Cookie（cloud_profiles）和任务配置（configs）未改动，无需重新配置。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
