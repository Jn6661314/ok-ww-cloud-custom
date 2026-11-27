#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 releases/ 目录下的版本说明发布成 GitHub Release（自动打 tag）。

用法:
    python tools/publish_release.py            # 发布所有尚未发布的版本
    python tools/publish_release.py v1.5.0     # 只发布指定版本
    python tools/publish_release.py --dry-run  # 只打印将要执行的动作

设计要点:
  * 凭据优先从环境变量 GITHUB_TOKEN 读取; 没有时回落到 git credential manager
    (与 git push 同一份凭据), 因此本地已能 push 的机器无需额外配置。
  * 双语正文直接放在 releases/<tag>.md, 中英文同文件, 发布时原样作为 release body。
  * 幂等: 已存在的 release 会被更新 (改标题/正文), 不会重复创建。
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request

REPO = 'Jn6661314/ok-ww-cloud-custom'
API = f'https://api.github.com/repos/{REPO}'
RELEASES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'releases')

# git tag -> (release 标题, 目标 commit)
PLAN = [
    ('v1.8.22', 'v1.8.22 · 修好配对二维码（之前根本没码）/ Fix the pairing QR code', 'HEAD'),
    ('v1.8.21', 'v1.8.21 · 两个手机投屏菜单合成一个（内置引擎/桌面端）/ One phone-mirroring menu, engine or desktop', 'HEAD'),
    ('v1.8.20', 'v1.8.20 · 内置投屏引擎（不再需要 NectarLink 桌面端）/ Built-in mirroring engine, no NectarLink desktop app', 'HEAD'),
    ('v1.8.19', 'v1.8.19 · 手机投屏(NectarLink)驱动真机玩鸣潮（取代 MuMu）/ Drive a real phone via NectarLink mirroring', 'HEAD'),
    ('v1.8.18', 'v1.8.18 · 修复 MuMu 战斗切人永远只切 1 号位（编队识别抖动）/ Fix MuMu switching stuck on slot 1', 'HEAD'),
    ('v1.8.17', 'v1.8.17 · 修复开了远控窗口模式但设备下拉还是 PC 客户端 / Fix stream-window device dropdown', 'HEAD'),
    ('v1.8.16', 'v1.8.16 · MuMu 方块改用落点预览视觉闭环（不再猜触控坐标）/ Blocks drag via visual servo', 'HEAD'),
    ('v1.8.15', 'v1.8.15 · MuMu 方块拖拽改用 IPC 触控（修复 x/y 落点大幅偏移）/ Blocks drag via MuMu IPC touch', 'HEAD'),
    ('v1.8.14', 'v1.8.14 · MuMu 方块拖拽改用 input motionevent（修复落点错位）/ Blocks drag via input motionevent', 'HEAD'),
    ('v1.8.13', 'v1.8.13 · MuMu 方块旋转改走可配置键位映射键 / MuMu Blocks rotation via configurable keymap key', 'HEAD'),
    ('v1.8.12', 'v1.8.12 · MuMu 拉海洛方块真双指触控(一指旋转+一指拖方块) / MuMu Rahai Blocks two-finger touch', 'HEAD'),
    ('v1.8.11', 'v1.8.11 · 修复鸣潮已启动但 MuMu 报"未连接" / Fix MuMu "not connected" while game is running', 'HEAD'),
    ('v1.8.10', 'v1.8.10 · 修复首次进配置页不显示账号按钮 + MuMu 设备列表加载慢 / Fix account buttons on first config open + slow MuMu device list', 'HEAD'),
    ('v1.8.9', 'v1.8.9 · 修复云鸣潮战斗中误判脱战、敌人没打完就停 / Fix cloud combat stopping mid-fight', 'HEAD'),
    ('v1.8.8', 'v1.8.8 · 云鸣潮战斗奖励副本出错后现场续打、不重进 / Resume the reward dungeon in place after a cloud error', 'HEAD'),
    ('v1.8.7', 'v1.8.7 · 聚落锁敌兜底 + Moonlight 远控预设 / Settlement lock-on fallback and Moonlight preset', 'HEAD'),
    ('v1.8.6', 'v1.8.6 · 修复重启任务偶尔丢账号登录态 / Fix cloud login lost after task restart', 'HEAD'),
    ('v1.8.5', 'v1.8.5 · 两套 Agent 安装提示词：云鸣潮定制 / 真双机版 / Two install prompts: cloud-custom and true dual-PC', 'HEAD'),
    ('v1.8.4', 'v1.8.4 · 修复启动即崩(MuMu 配置改名漏改引用) / Fix startup crash from stale MuMu config name', 'HEAD'),
    ('v1.8.3', 'v1.8.3 · 钉住版本 tag，挡住启动器 checkout -f 还原定制 / Pin the version tag so the launcher cannot revert the customizations', 'HEAD'),
    ('v1.8.2', 'v1.8.2 · 修掉启动器版本号不同步(显示 3.8.14) / Sync launcher version to config.py', 'HEAD'),
    ('v1.8.1', 'v1.8.1 · 修正远控/串流窗口入口位置 + 配置名含斜杠 / Fix remote-window page entry & slash in config names', 'HEAD'),
    ('v1.8.0', 'v1.8.0 · 试验性：把远控/串流软件窗口当作 PC 设备 / Experimental: remote-control & streaming windows as a PC device', 'HEAD'),
    ('v1.7.0', 'v1.7.0 · MuMu / 安卓模拟器支持合并回官方 v3.8.15 基线 / Merge MuMu support into official v3.8.15', 'HEAD'),
    ('v1.6.0', 'v1.6.0 · 以官方 v3.8.15 为基线重建 + 无尽模式 / Rebase onto official v3.8.15 with Endless Mode', 'HEAD'),
    ('v1.0.0', 'v1.0.0 · 云鸣潮定制补丁集首次发布 / First release of the Wuthering Waves cloud patch set', '848e78c'),
    ('v1.0.1', 'v1.0.1 · Agent 一键安装提示词 / Agent-Assisted Install Prompt', '1c9ecb1'),
    ('v1.1.0', 'v1.1.0 · 故障方块机制 / 云 UID 遮罩 / 通关后卡住修复 / ADB 设备入口', '4e2cb3b'),
    ('v1.2.0', 'v1.2.0 · 云战斗工坊修复 / 无怪物自动退出 / Win10 云鸣潮 / 触屏键位补全', 'cfdb185'),
    ('v1.3.0', 'v1.3.0 · 同步上游 v3.8.14（WebRTC）/ 安卓触屏模式层 / MCP 端口自适应', '5c91687'),
    ('v1.4.0', 'v1.4.0 · 安卓独立每日任务 / 大世界判定 / 黑帧与断线弹窗处理 / 索拉指南定位', 'ade8d15'),
    ('v1.5.0', 'v1.5.0 · 梦魇聚落传送按钮 OCR / 登录黑屏冗余等待 / 安卓启动拉起鸣潮', '8ccfedf'),
    ('v1.5.1', 'v1.5.1 · 修复全新安装装不全导致的启动失败 / Fix fresh install missing most files', 'HEAD'),
    ('v1.5.2', 'v1.5.2 · 修复 MuMu/安卓端无法自动战斗 / Fix MuMu Android auto-combat crash', '2463fd3'),
    ('v1.5.3', 'v1.5.3 · 修复 MuMu 手动锁定后仍不战斗 / Fix MuMu still not fighting after target lock', 'dd2ba22'),
    ('v1.5.4', 'v1.5.4 · 修复 MuMu 切人卡死导致打着打着停 / Fix MuMu combat stalling on character switch', 'c986d31'),
    ('v1.5.5', 'v1.5.5 · 修复 MuMu 掉线弹窗卡住不动 / Fix MuMu freeze on disconnect dialog', 'a3849be'),
    ('v1.5.6', 'v1.5.6 · 修复 MuMu 重击长按 mouse_down 崩溃 / Fix MuMu crash on heavy attack', '0fafa52'),
    ('v1.5.7', 'v1.5.7 · 修复 MuMu 手游端锁敌也不打 / Fix MuMu mobile combat doing nothing', 'cb44f95'),
    ('v1.5.8', 'v1.5.8 · 修复 MuMu 打着打着停 / 按编队识别队伍 / AutoCombatTask 兼容', 'HEAD'),
    ('v1.5.9', 'v1.5.9 · 修复 MuMu 无法谐振破坏（识别提示图标并点击）/ Fix MuMu Resonance Break (detect and tap the prompt)', 'HEAD'),
    ('v1.5.10', 'v1.5.10 · 修复 MuMu 打着打着不打了（重锁定耐心/重试/黑帧保护）/ Fix MuMu combat stopping unexpectedly (patient retarget, retry, black-frame guard)', 'HEAD'),
    ('v1.5.11', 'v1.5.11 · 修复 MuMu 切人（只用 1/2 键 / 动态映射 / 发键后核实）/ Fix MuMu character switching (keys 1/2 only, dynamic mapping, post-press verification)', 'HEAD'),
    ('v1.5.12', 'v1.5.12 · 修复声骸副本炸每日任务 + 队伍识别以编队为准 / Fix Tacet crash killing daily task + formation-based team identification', 'HEAD'),
    ('v1.5.21', 'v1.5.21 · 云游戏 UID 遮罩兼容 WebRTC 捕获 / Cloud UID cover: WebRTC capture compatibility', 'HEAD'),
    ('v1.5.20', 'v1.5.20 · 拉海洛方块走棋搜索组合爆炸修复(无尽4块托盘卡死) / Rahai Blocks: fix move-search explosion (endless 4-tile tray freeze)', 'v1.5.21^'),
    ('v1.5.19', 'v1.5.19 · 无尽模式直启兜底 + 云游戏卡死修复 / Endless direct-start fallback + cloud game hang fix', 'v1.5.20^'),
    ('v1.5.18', 'v1.5.18 · 拉海洛方块直接支持无尽模式 / Rahai Blocks: full Endless Mode support', 'v1.5.19^'),
    ('v1.5.17', 'v1.5.17 · MuMu 三项修复: 活跃行迹/拉海洛方块/自动战斗与掉线 / MuMu fixes: activity trace, Rahai Blocks, auto combat & disconnect', 'v1.5.18^'),
    ('v1.5.16', 'v1.5.16 · 拉海洛方块支持关卡详情页直接开始 / Rahai Blocks: start directly from stage details page', 'HEAD'),
    ('v1.5.15', 'v1.5.15 · 爱弥斯轮转修复: 变奏入场必出招 / Aemeath rotation fix: always perform on intro', 'HEAD'),
    ('v1.5.14', 'v1.5.14 · 修复 v1.5.13 识别环节 AttributeError 错误风暴 / Fix AttributeError error storm in v1.5.13 team detection', 'HEAD'),
    ('v1.5.13', 'v1.5.13 · 安卓编队锁定 + 协奏环（延奏）识别修复 / Android formation lock + concerto ring (outro) fix', 'HEAD'),
]


def get_token():
    token = os.environ.get('GITHUB_TOKEN') or os.environ.get('GH_TOKEN')
    if token:
        return token.strip()
    # 回落到 git credential manager (与 git push 同一份凭据)
    try:
        out = subprocess.run(
            ['git', 'credential', 'fill'],
            input='protocol=https\nhost=github.com\n\n',
            capture_output=True, text=True, timeout=30,
        ).stdout
        for line in out.splitlines():
            if line.startswith('password='):
                return line.split('=', 1)[1].strip()
    except Exception as e:  # noqa: BLE001
        print(f'[warn] 读取 git 凭据失败: {e}', file=sys.stderr)
    return None


def api(method, path, token, payload=None):
    url = path if path.startswith('http') else API + path
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header('Authorization', f'Bearer {token}')
    req.add_header('Accept', 'application/vnd.github+json')
    req.add_header('X-GitHub-Api-Version', '2022-11-28')
    req.add_header('User-Agent', 'ok-ww-cloud-custom-release-tool')
    if data:
        req.add_header('Content-Type', 'application/json')
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            body = resp.read().decode('utf-8')
            return resp.status, json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        return e.code, body
    except Exception as e:  # noqa: BLE001
        return 0, str(e)


def git(*args):
    return subprocess.run(['git', *args], capture_output=True, text=True, timeout=60)


def main():
    dry_run = '--dry-run' in sys.argv
    wanted = [a for a in sys.argv[1:] if not a.startswith('--')]

    token = get_token()
    if not token:
        print('[error] 找不到 GitHub 凭据。请设置 GITHUB_TOKEN 环境变量，'
              '或先在本地完成一次 git push 以写入凭据管理器。', file=sys.stderr)
        return 1

    status, existing = api('GET', '/releases?per_page=100', token)
    if status != 200:
        print(f'[error] 无法读取现有 Release: {status} {existing}', file=sys.stderr)
        return 1
    by_tag = {r['tag_name']: r for r in existing}

    for tag, title, commit in PLAN:
        if wanted and tag not in wanted:
            continue

        md_path = os.path.join(RELEASES_DIR, f'{tag}.md')
        if not os.path.exists(md_path):
            print(f'[skip] {tag}: 找不到 {md_path}')
            continue
        with open(md_path, encoding='utf-8') as f:
            body = f.read()

        # 1) 确保 tag 存在并指向目标 commit
        tag_sha = git('rev-list', '-n', '1', tag).stdout.strip()
        if tag_sha != commit:
            r = git('tag', '-f', tag, commit)
            if r.returncode != 0:
                print(f'[error] {tag}: 打 tag 失败: {r.stderr.strip()}')
                continue
            print(f'[tag] {tag} -> {commit} (本地)')

        # 2) 推送 tag
        r = git('push', 'origin', tag)
        if r.returncode != 0 and 'already exists' not in r.stderr:
            print(f'[warn] {tag}: push tag 失败: {r.stderr.strip()}')

        if dry_run:
            print(f'[dry-run] 将发布 {tag} ({len(body)} 字符正文)')
            continue

        payload = {
            'tag_name': tag,
            'name': title,
            'body': body,
            'draft': False,
            'prerelease': False,
        }
        if tag in by_tag:
            # 更新已有 release: 不允许再改 tag / target
            status, resp = api('PATCH', f"/releases/{by_tag[tag]['id']}", token, payload)
            action = '更新'
        else:
            # 新建 release: tag 已推上远端, GitHub 会直接复用它;
            # target_commitish 只接受完整 SHA, 用缩写会返回 422。
            full_sha = git('rev-parse', commit).stdout.strip()
            if full_sha:
                payload['target_commitish'] = full_sha
            status, resp = api('POST', '/releases', token, payload)
            action = '创建'

        if status in (200, 201):
            url = resp.get('html_url', '') if isinstance(resp, dict) else ''
            print(f'[ok] {action} Release {tag} -> {url}')
        else:
            print(f'[error] {action} Release {tag} 失败: {status} {resp}')

    return 0


if __name__ == '__main__':
    sys.exit(main())
