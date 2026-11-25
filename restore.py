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
# 基线：官方 ok-ww v3.8.15（ok-script 3.0.14）。包含云端（云鸣潮）与
# MuMu/安卓模拟器两套定制；纯云端、可直接向上游提 PR 的版本在 official-cloud 分支。
RELATIVE_FILES = [
    'config.py',
    # 框架最小补丁：CDP 调用超时（防云游戏假死卡住任务）+ 后台输入。
    'ok/device/capture_methods/browser.py',
    # 框架 MuMu/ADB 补丁（本地模拟器支持），官方合入后即可删除：
    # - DeviceManager: adb 拉起游戏 / MuMu 网桥 arp 回退 / 窗口抓屏下的交互覆盖
    # - nemu_ipc: MuMu IPC 抓屏的全黑帧检测与连接自恢复
    # - keys: ADB 键位映射（esc->返回、F1-F12、A-Z、0-9、反引号）
    # - window / windows_graphics: WGC 在 Win10 2004+ 可用、去黄色边框
    'ok/device/DeviceManager.py',
    'ok/device/capture_methods/nemu_ipc.py',
    'ok/device/capture_methods/windows_graphics.py',
    'ok/device/interaction_methods/keys.py',
    'ok/util/window.py',
    # 云鸣潮：每个账号一个浏览器 profile（纯 okww 侧目录切换，不改框架）
    'src/cloud_browser.py',
    'src/cloud_recovery.py',
    # 多账号：云游戏分支 + 「保存登录状态/切换账号」按钮（仅云设备显示）
    'src/task/MultiAccountDailyTask.py',
    'src/task/account/MultiAccountConfigStore.py',
    'src/gui/MultiAccountConfigTab.py',
    'src/gui/MultiAccountConfigDialog.py',
    # 云鸣潮/MuMu 适配：活跃度读不到时不按 0 处理；先约电台在浏览器下不吞 Alt；
    # 安卓端改用"活跃行迹"宽域 OCR 读活跃度
    'src/task/DailyTask.py',
    # MuMu/安卓：触屏键位、大世界判定、索拉指南定位、独立每日任务入口
    'src/task/touch_mode.py',
    'src/task/android_world.py',
    'src/task/android_book.py',
    'src/task/AndroidDailyTask.py',
    # MuMu/安卓：BaseWWTask 的触屏语义层 + BaseCombatTask 的编队锁定/切人键位
    # + CombatCheck 的锁敌/谐振破坏 + 触发任务与鼠标复位的健壮性修复
    'src/task/BaseWWTask.py',
    'src/task/BaseCombatTask.py',
    'src/combat/CombatCheck.py',
    'src/task/AutoCombatTask.py',
    'src/task/MouseResetTask.py',
    # 拉海洛方块：官方 v3.8.15 + 无尽模式/详情页直启 + 云鸣潮/MuMu 输入分流
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
    print('恢复完成。启动 ok-ww 后按设备照常运行同一个「每日任务」即可：')
    print('  - 云游戏：多账号任务设置页会多出「保存登录状态」「切换账号」两个按钮')
    print('  - MuMu/安卓：设备下拉里会出现模拟器，抓屏默认 MuMu IPC，键位由模拟器映射转发')
    print('  - PC 客户端：行为与官方一致')
    print('账号 Cookie（cloud_profiles）、多账号配置和任务配置（configs）未改动，无需重新配置。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
