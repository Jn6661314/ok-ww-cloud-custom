"""下载/更新工坊离线快照（来自社区公开镜像）。

上游工坊服务器 cfokwwchar.ok-script.com 与 okwwcharcode.ok-script.com 已下线，
本仓库随附 teams.json 与 teams/*.json 文本索引；代码包 codes/*.zip 体积较大，
不放在仓库里，用这个脚本从公开镜像拉取：

    python tools/download_workshop_cache.py

会把 teams.json、teams/、codes/ 写入仓库根目录的 workshop_cache/。
安装脚本会自动把该目录复制到 ok-ww 的 configs/workshop_cache。
"""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path

MIRROR = 'https://github.com/yamadafz/ok-ww-char-code.git'
SOURCE = Path(__file__).resolve().parent.parent
TARGET = SOURCE / 'workshop_cache'


def main() -> int:
    with tempfile.TemporaryDirectory(prefix='okww-workshop-') as tmp:
        repo = Path(tmp) / 'mirror'
        print(f'cloning {MIRROR} ...')
        subprocess.run(['git', 'clone', '--depth', '1', MIRROR, str(repo)], check=True)
        TARGET.mkdir(parents=True, exist_ok=True)
        src_index = repo / 'teams.json'
        if src_index.is_file():
            shutil.copy2(src_index, TARGET / 'teams.json')
            print('copied teams.json')
        for folder in ('teams', 'codes'):
            src = repo / folder
            if src.is_dir():
                shutil.copytree(src, TARGET / folder, dirs_exist_ok=True)
                print(f'copied {folder}/')
    print(f'done: {TARGET}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
