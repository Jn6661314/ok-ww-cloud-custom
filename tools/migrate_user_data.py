"""把用户数据从旧 ok-ww 运行目录迁移到新目录（只复制，不删除、不上传）。

为什么需要
----------
发布的绿色包**故意不含**任何登录态（Cookie、账号配置、键位校准）——这是隐私要求。
所以在本机换用新版本目录时，必须把旧目录里的用户数据迁过去，否则点新快捷方式
看到的就是一个“全新安装”，看起来像登录状态被清掉了（实际一分都没丢）。

用法::

    python tools/migrate_user_data.py <旧 working 目录> <新 working 目录>

复制范围（全是用户数据，不含代码）:
    configs/**                  多账号配置、任务配置、投屏键位校准
    data/cloud_profiles/**      浏览器 profile —— Cookie 真正所在的位置
    cloud_profiles/**           旧版本留下的位置
    cache/playwright/storage_state.json

目标里已有的同名文件会先备份到 <新目录父目录>/_userdata_backup_<时间戳>/。
本脚本既不读文件内容，也不往仓库/Release 写任何东西。
"""

from __future__ import annotations

import argparse
import datetime
import shutil
import sys
from pathlib import Path

COPY_DIRS = (
    'configs',
    'data/cloud_profiles',
    'cloud_profiles',
)
COPY_FILES = (
    'cache/playwright/storage_state.json',
)


def backup_target(target: Path, relative: str, backup_root: Path) -> int:
    """把目标上将被覆盖的目录/文件先复制一份，返回备份的文件数。"""
    source = target / relative
    if not source.exists():
        return 0
    keeper = backup_root / relative
    keeper.parent.mkdir(parents=True, exist_ok=True)
    count = 0
    if source.is_dir():
        shutil.copytree(source, keeper, dirs_exist_ok=True)
        count = sum(1 for path in source.rglob('*') if path.is_file())
    else:
        shutil.copy2(source, keeper)
        count = 1
    return count


def copy_user_data(source: Path, target: Path, backup_root: Path) -> int:
    copied = 0
    for relative in COPY_DIRS:
        src = source / relative
        if not src.is_dir():
            continue
        dst = target / relative
        copied += backup_target(target, relative, backup_root)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst, dirs_exist_ok=True)
        count = sum(1 for path in src.rglob('*') if path.is_file())
        print(f'[复制] {relative} -> {dst} ({count} 个文件)')
        copied += count
    for relative in COPY_FILES:
        src = source / relative
        if not src.is_file():
            continue
        dst = target / relative
        copied += backup_target(target, relative, backup_root)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f'[复制] {relative} -> {dst}')
        copied += 1
    return copied


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path, help='旧版本的 working 目录')
    parser.add_argument('target', type=Path, help='新版本的 working 目录')
    args = parser.parse_args(argv)
    if not args.source.is_dir():
        print(f'[错误] 源目录不存在: {args.source}')
        return 1
    if not args.target.is_dir():
        print(f'[错误] 目标目录不存在: {args.target}')
        return 1
    stamp = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
    backup_root = args.target.parent / f'_userdata_backup_{stamp}'
    copied = copy_user_data(args.source, args.target, backup_root)
    print(f'[完成] 共复制 {copied} 项用户数据。')
    if backup_root.exists():
        print(f'[备份] 目标上被覆盖的旧文件在: {backup_root}')
    print('注意：本脚本从不删除源文件，也不把用户数据写进仓库或发布包。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main(sys.argv[1:]))
