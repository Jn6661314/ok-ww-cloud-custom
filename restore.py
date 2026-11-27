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
import json
import re
import shutil
import subprocess
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
    # 云鸣潮战斗奖励副本出错后的现场续打（无音区等，不再从 F2 重进）
    'src/reward_dungeon_recovery.py',
    # 远控/串流窗口(试验性)：UU远程/ToDesk/向日葵/Parsec 的窗口当 PC 设备，
    # 启动时按「远控/串流窗口」配置切换（globals 里挂载）
    'src/stream_window.py',
    'src/globals.py',
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
    # 残象聚落：锁不到敌人(双极飞出范围)时原地重锁, 仍失败就跳过当前聚落
    'src/task/NightmareNestTask.py',
    # 拉海洛方块：官方 v3.8.15 + 无尽模式/详情页直启 + 云鸣潮/MuMu 输入分流
    'src/task/RahaiBlocksTask.py',
    'src/task/rahai_blocks.py',
    # MuMu 双指触控：手游版旋转靠屏幕按钮, 用 ADB sendevent 多点触控
    # (一指点旋转 + 一指拖方块), MuMu IPC/u2 单指 API 做不到
    'src/task/multi_touch.py',
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


def read_source_version():
    """从仓库 config.py 读取 ``version`` 常量。"""
    try:
        text = (FILES / 'config.py').read_text(encoding='utf-8')
    except OSError:
        return None
    match = re.search(r"""^version\s*=\s*['"]([^'"]+)['"]""", text, re.MULTILINE)
    return match.group(1) if match else None


def sync_app_version(working: Path, stamp: str, do_backup: bool) -> int:
    """让启动器显示的版本号与 config.py 的 version 保持一致。

    ``data/apps/ok-ww/app.json`` 的 ``current_version`` 是 pyappify 记录"已安装版本"
    的地方：启动器（ok-ww.exe）用它显示版本号，也用它判断"有没有新版本可更新"。

    我们的代码基线上移后如果这里不动，启动器会一直显示旧版本号，并且认为还能更新到
    基线的那个版本 —— 用户一点更新，官方代码就会覆盖 working/repo，整套定制全部丢失。
    """
    version = read_source_version()
    if not version:
        print('[app.json] 读不到 config.py 的 version，跳过版本同步')
        return 0
    app_json = working.parent / 'app.json'
    if not app_json.is_file():
        print(f'[app.json] 未找到 {app_json}，跳过版本同步')
        return 0
    try:
        data = json.loads(app_json.read_text(encoding='utf-8'))
    except (OSError, ValueError) as error:
        print(f'[app.json] 读取失败（{error}），跳过版本同步')
        return 0
    if not isinstance(data, dict):
        print('[app.json] 内容不是 JSON 对象，跳过版本同步')
        return 0
    current = data.get('current_version')
    if current == version:
        print(f'[app.json] 启动器版本已是 {version}，无需同步')
        return 0
    if do_backup:
        try:
            shutil.copy2(app_json, app_json.with_name(f'app.json.{stamp}.bak'))
        except OSError as error:
            print(f'[app.json] 备份失败（{error}），跳过版本同步')
            return 0
    data['current_version'] = version
    try:
        app_json.write_text(json.dumps(data, indent=2, ensure_ascii=False) + '\n',
                            encoding='utf-8')
    except OSError as error:
        print(f'[app.json] 写入失败（{error}）')
        return 0
    print(f'[app.json] 启动器版本 {current} -> {version}'
          '（避免启动器误以为还能更新到该版本而覆盖定制）')
    return 0


GIT_AUTHOR = ('ok-ww-custom', 'custom@local')
# 本地基线的保护标签：即使 HEAD 被切走，这个提交也不会变成孤立对象。
GIT_TAG = 'local-custom-baseline'


def _run_git(repo: Path, *args: str):
    """在 ``repo`` 里跑一条 git 命令，返回 (returncode, 合并输出)。"""
    git = shutil.which('git')
    if not git:
        return None, '系统里找不到 git'
    try:
        done = subprocess.run([git, *args], cwd=str(repo), capture_output=True,
                              text=True, encoding='utf-8', errors='replace')
    except OSError as error:  # pragma: no cover - 取决于本机环境
        return None, str(error)
    return done.returncode, ((done.stdout or '') + (done.stderr or '')).strip()


def sync_repo_git(repo: Path) -> int:
    """把刚部署的定制文件提交进 ``repo`` 的 git，让启动器的"完整性修复"还原成定制版。

    pyappify 的 shared-checkout 布局是"git 数据在 repo、应用文件在 working"。
    启动器发现 working 里的被跟踪文件与 git 不一致时，会从 git 把文件还原回去 ——
    如果定制只以**未提交改动**的形式存在，启动一次就会被整套刷回官方版本
    （v1.8.2 就是这样丢了 22 个文件，界面上的 MuMu/远控/多账号定制全部消失）。

    把定制提交成 git 里的一个本地提交后，同一次"修复"恢复出来的就是定制内容，
    启动器再怎么校验也只会校验到我们自己的版本。
    """
    if not (repo / '.git').exists():
        print(f'[git] {repo} 不是 git 仓库，跳过定制提交')
        return 0

    files = [rel for rel in RELATIVE_FILES if (repo / rel).is_file()]
    if not files:
        print('[git] repo 里找不到定制文件，跳过定制提交')
        return 0

    rc, out = _run_git(repo, 'add', '--', *files)
    if rc is None:
        print(f'[git] 跳过定制提交：{out}')
        return 0
    if rc != 0:
        print(f'[git] git add 失败：{out[:200]}')
        return 0

    # 没有暂存内容 = 上次已经提交过，不必产生空提交。
    rc, out = _run_git(repo, 'diff', '--cached', '--quiet')
    if rc == 0:
        print('[git] 定制内容与 git 中的一致，无需提交')
        _ensure_custom_tag(repo, files)
        return 0

    name, email = GIT_AUTHOR
    rc, out = _run_git(repo, '-c', f'user.name={name}', '-c', f'user.email={email}',
                       'commit', '-q', '-m',
                       'local custom baseline: cloud + mumu/android + rahai endless + stream window')
    if rc:
        print(f'[git] git commit 失败：{out[:200]}')
        return 0

    rc, out = _run_git(repo, 'rev-parse', '--short', 'HEAD')
    head = out if rc == 0 else '?'
    print(f'[git] 定制已提交到 repo 的 git（{head}），启动器校验时不会再把它们还原成官方版')
    _ensure_custom_tag(repo, files)
    return 0


def _ensure_custom_tag(repo: Path, files) -> None:
    """给当前 HEAD 打一个本地标签，避免切换版本后定制提交变成孤立对象。"""
    rc, _ = _run_git(repo, 'tag', '-f', GIT_TAG)
    if rc == 0:
        print(f'[git] 已标记 {GIT_TAG}，切版本后仍可用 git checkout {GIT_TAG} 找回定制')


# 官方版本 tag 的备份前缀（例如官方 v3.8.15 被备份成 official-v3.8.15）
OFFICIAL_TAG_PREFIX = 'official-'


def pin_version_tag_to_head(repo: Path) -> int:
    """让"版本号 tag"指向定制提交，挡住启动器的强制 checkout。

    启动器（pyappify）启动/自修复时，会拿 ``app.json`` 的 ``current_version``
    （例如 ``v3.8.15``）去找**同名 git tag**，然后 ``git checkout -f`` 过去。
    ``-f`` 会丢弃工作区里所有"未提交的定制"，所以只把定制提交进 git 仍然不够：
    定制提交只是 HEAD，启动器照样把 HEAD 切到官方 tag，下一次写文件就全成了官方版
    （v1.8.2 之后在 23:30 又原样丢了一次，22 个文件、界面里 MuMu/远控/多账号全没了）。

    把版本 tag 本身指到定制提交后，同一次 checkout 切出来的就是定制内容，
    启动器再怎么校验也只是在校验我们自己的版本。原官方指向会备份成
    ``official-<版本号>``，需要回到官方基线时 ``git checkout official-v3.8.15`` 即可。
    """
    if not (repo / '.git').exists():
        return 0

    version = read_source_version()
    if not version:
        print('[git] 读不到 config.py 的 version，跳过版本 tag 处理')
        return 0

    rc, current = _run_git(repo, 'rev-parse', f'{version}^{{commit}}')
    rc_head, head = _run_git(repo, 'rev-parse', 'HEAD')
    if rc == 0 and rc_head == 0 and current == head:
        print(f'[git] 版本 tag {version} 已指向定制提交，无需改动')
        return 0

    if rc == 0:
        backup = OFFICIAL_TAG_PREFIX + version
        rc_backup, _ = _run_git(repo, 'rev-parse', '--verify', '--quiet',
                                f'refs/tags/{backup}')
        if rc_backup != 0:
            # 只在第一次改 tag 时备份，避免把定制提交又备份成"官方指向"。
            _run_git(repo, 'tag', backup, current)

    name, email = GIT_AUTHOR
    rc, out = _run_git(repo, '-c', f'user.name={name}', '-c', f'user.email={email}',
                       'tag', '-f', '-a', version, '-m',
                       f'ok-ww {version} (local custom baseline)', 'HEAD')
    if rc:
        print(f'[git] 版本 tag {version} 更新失败：{out[:200]}')
        return 0

    print(f'[git] 版本 tag {version} -> 定制提交：启动器按版本号 checkout 时切出的是'
          f'定制版（原官方指向已备份为 {OFFICIAL_TAG_PREFIX}{version}）')
    return 0


def verify_deploy(working: Path, repo: Path) -> int:
    """部署后自检：确认 working / repo 里的定制文件与仓库内容逐字节一致。"""
    problems = []
    for rel in RELATIVE_FILES:
        source = FILES / rel
        if not source.is_file():
            continue
        want = source.read_bytes()
        for label, root in (('working', working), ('repo', repo)):
            target = root / rel
            if not target.is_file():
                problems.append(f'{label}/{rel} 缺失')
                continue
            if target.read_bytes() != want:
                problems.append(f'{label}/{rel} 与仓库内容不一致')
    if not problems:
        print(f'[自检] {len(RELATIVE_FILES)} 个文件在 working / repo 两处均与仓库一致')
        return 0
    print('[自检] 发现以下问题（启动器可能已经还原过官方版本）：')
    for item in problems[:12]:
        print(f'  - {item}')
    if len(problems) > 12:
        print(f'  ... 共 {len(problems)} 项')
    return 1


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
    sync_app_version(args.working, stamp, not args.no_backup)
    if not args.working_only:
        if restore_to(args.repo, stamp, not args.no_backup, 'repo'):
            return 1
        # 必须在 repo 落盘之后再提交，否则提交进去的是旧内容。
        sync_repo_git(args.repo)
        # 提交之后再把版本 tag 指过来，启动器 checkout 版本号时才会切出定制版。
        pin_version_tag_to_head(args.repo)

    verify_deploy(args.working, args.repo)

    print('')
    print('恢复完成。启动 ok-ww 后按设备照常运行同一个「每日任务」即可：')
    print('  - 云游戏：多账号任务设置页会多出「保存登录状态」「切换账号」两个按钮')
    print('  - MuMu/安卓：设备下拉里会出现模拟器，抓屏默认 MuMu IPC，键位由模拟器映射转发')
    print('  - PC 客户端：行为与官方一致')
    print('账号 Cookie（cloud_profiles）、多账号配置和任务配置（configs）未改动，无需重新配置。')
    print('启动器（ok-ww.exe）显示的版本号已同步为 config.py 的 version，'
          '不会再提示更新到同一版本而覆盖定制。')
    if not args.working_only:
        print(f'定制已同时提交进 repo 的 git（标签 {GIT_TAG}），并把版本 tag 指向了这个'
              '提交：启动器按版本号 checkout / 校验时切出来的是定制版，'
              '不会再被刷回官方代码。')
    print('注意：不要在启动器的更新卡片里手动"安装"官方版本，那会把 working 覆盖成官方代码；'
          '真的更新了，重跑一次本脚本即可。')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
