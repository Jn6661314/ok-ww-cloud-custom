"""Patch ok-ww's BaseWWTask for reliable cloud-game entry.

Two idempotent edits to a local ``src/task/BaseWWTask.py``:

1. Add cooldown constants next to ``CLOUD_RELOGIN_TIMEOUT``.
2. Use a graded cooldown for the "开始游戏"/"进入游戏" click inside ``wait_login``:
   the first click often does not register and needs a quick retry, but rapid
   repeated clicks while the cloud instance is loading restart the queue (which
   caused the multi-account task to hang after 3 fast clicks in the log).
3. Add ``wait_cloud_game_ready()`` which reuses ``ensure_main``'s detection
   chain (in_team_and_world / wait_login / monthly card / cloud disconnect) to
   positively detect that the cloud game finished entering the game world.

Works on any version that has the matching anchor text; leaves the file
untouched and reports an error if an anchor is missing or ambiguous.  Re-running
is safe (reports "already patched").

Usage::

    python tools/patch_baseww_cloud_ready.py [path/to/src/task/BaseWWTask.py]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

MARKER = 'CLOUD ACCOUNT ENTRY PATCH'

CONST_OLD = "CLOUD_RELOGIN_TIMEOUT = 600"
CONST_NEW = """CLOUD_RELOGIN_TIMEOUT = 600
# CLOUD ACCOUNT ENTRY PATCH: cloud game can take minutes to load after clicking
# "进入游戏"; the home-page button stays visible, so clicks must be throttled.
CLOUD_START_COOLDOWN = 60
# Graded cooldown (seconds): the first "开始游戏" click often does not register,
# so retry quickly a couple of times, then back off to avoid restarting the queue.
CLOUD_START_COOLDOWNS = (0, 8, 30, CLOUD_START_COOLDOWN)
CLOUD_ENTER_TIMEOUT = 600"""

CLICK_OLD = """            if start := self.find_boxes(texts, boundary='bottom_right', match=["开始游戏", re.compile("进入游戏")]):
                if not self.find_boxes(texts, boundary='bottom_right', match=LOGIN_TEXTS):
                    self.click(start)
                    self.log_info(self.tr('Click Start Game! {start}').format(start=start))
                    return False"""
CLICK_NEW = """            if start := self.find_boxes(texts, boundary='bottom_right', match=["开始游戏", re.compile("进入游戏")]):
                if not self.find_boxes(texts, boundary='bottom_right', match=LOGIN_TEXTS):
                    # CLOUD ACCOUNT ENTRY PATCH: graded cooldown. The first "开始游戏"
                    # click often does not register, so retry quickly; then back off so
                    # polling does not restart the cloud queue during loading.
                    now = time.time()
                    clicks = getattr(self, '_cloud_start_clicks', 0)
                    cooldown = CLOUD_START_COOLDOWNS[min(clicks, len(CLOUD_START_COOLDOWNS) - 1)]
                    if now - getattr(self, '_cloud_start_click_time', 0) >= cooldown:
                        self._cloud_start_click_time = now
                        self._cloud_start_clicks = clicks + 1
                        self.click(start, after_sleep=2)
                        self.log_info(self.tr('Click Start Game! ({clicks}) {start}')
                                      .format(clicks=clicks + 1, start=start))
                    return False"""

METHOD_ANCHOR = """    def in_team_and_world(self):
        return self.in_team()[
            0]"""
METHOD_NEW = """    def wait_cloud_game_ready(self, time_out=CLOUD_ENTER_TIMEOUT):
        \"\"\"CLOUD ACCOUNT ENTRY PATCH: wait until the cloud game fully entered.

        Reuses the same detection chain as the local daily mode via
        ``ensure_main``: is_main() checks in_team_and_world (reached the game
        world), wait_login (login box / \"进入游戏\" button, now throttled),
        handle_monthly_card and handle_cloud_disconnect (reconnect).  logged_in
        is reset by the caller so ensure_main widens its timeout automatically;
        esc=False avoids backing out to the cloud home during loading.
        \"\"\"
        self.log_info(self.tr('Waiting for cloud game to finish entering...'), notify=True)
        self._cloud_start_click_time = 0
        self._cloud_start_clicks = 0
        self.ensure_main(esc=False, time_out=time_out)
        self.log_info(self.tr('Cloud game entered successfully'), notify=True)
        return True

    def in_team_and_world(self):
        return self.in_team()[
            0]"""


def candidates() -> list[Path]:
    installed = (Path.home() / 'AppData' / 'Local' / 'ok-ww' / 'data' / 'apps'
                 / 'ok-ww' / 'working' / 'src' / 'task' / 'BaseWWTask.py')
    source = Path(__file__).resolve().parent.parent / 'src' / 'task' / 'BaseWWTask.py'
    unique = []
    for path in (Path.cwd() / 'src' / 'task' / 'BaseWWTask.py', source, installed):
        if path not in unique:
            unique.append(path)
    return unique


# v1 -> v2 upgrade: the old patch used a single fixed 60s cooldown. Replace the
# old click block and the old reset line with the graded-cooldown versions.
UPGRADE_CLICK_OLD = """            if start := self.find_boxes(texts, boundary='bottom_right', match=["开始游戏", re.compile("进入游戏")]):
                if not self.find_boxes(texts, boundary='bottom_right', match=LOGIN_TEXTS):
                    # CLOUD ACCOUNT ENTRY PATCH: throttle repeated clicks. wait_until
                    # polls fast and the button remains during cloud loading; clicking
                    # every poll restarts the queue and the task hangs forever.
                    now = time.time()
                    if now - getattr(self, '_cloud_start_click_time', 0) >= CLOUD_START_COOLDOWN:
                        self._cloud_start_click_time = now
                        self.click(start, after_sleep=2)
                        self.log_info(self.tr('Click Start Game! {start}').format(start=start))
                    return False"""
# The source copy may use the Chinese-comment variant of the same v1 block.
UPGRADE_CLICK_OLD_CN = """            if start := self.find_boxes(texts, boundary='bottom_right', match=["开始游戏", re.compile("进入游戏")]):
                if not self.find_boxes(texts, boundary='bottom_right', match=LOGIN_TEXTS):
                    # 云游戏点"进入游戏"后要排队/加载几分钟, 期间按钮仍在。
                    # wait_until 会高频轮询, 不加冷却会连点导致反复重启排队(#云多账号卡死)。
                    now = time.time()
                    if now - getattr(self, '_cloud_start_click_time', 0) >= CLOUD_START_COOLDOWN:
                        self._cloud_start_click_time = now
                        self.click(start, after_sleep=2)
                        self.log_info(self.tr('Click Start Game! {start}').format(start=start))
                    return False"""
UPGRADE_CONST_OLD = """CLOUD_START_COOLDOWN = 60
CLOUD_ENTER_TIMEOUT = 600"""
UPGRADE_CONST_NEW = """CLOUD_START_COOLDOWN = 60
# Graded cooldown (seconds): the first "开始游戏" click often does not register,
# so retry quickly a couple of times, then back off to avoid restarting the queue.
CLOUD_START_COOLDOWNS = (0, 8, 30, CLOUD_START_COOLDOWN)
CLOUD_ENTER_TIMEOUT = 600"""
UPGRADE_RESET_OLD = """        self._cloud_start_click_time = 0
        self.ensure_main(esc=False, time_out=time_out)"""
UPGRADE_RESET_NEW = """        self._cloud_start_click_time = 0
        self._cloud_start_clicks = 0
        self.ensure_main(esc=False, time_out=time_out)"""


def upgrade_v2(text: str) -> str | None:
    """Upgrade an already-v1-patched file to graded cooldown. Return new text or None."""
    if 'CLOUD_START_COOLDOWNS' in text:
        return text  # already v2
    changed = text
    # constant
    if changed.count(UPGRADE_CONST_OLD) == 1:
        changed = changed.replace(UPGRADE_CONST_OLD, UPGRADE_CONST_NEW)
    # click block (English or Chinese v1 comment)
    click = None
    for candidate in (UPGRADE_CLICK_OLD, UPGRADE_CLICK_OLD_CN):
        if changed.count(candidate) == 1:
            click = candidate
            break
    if click is None:
        print('FAILED: v1 click block not found for upgrade')
        return None
    changed = changed.replace(click, CLICK_NEW)
    # reset line in wait_cloud_game_ready
    if changed.count(UPGRADE_RESET_OLD) != 1:
        print('FAILED: v1 reset line not found for upgrade')
        return None
    changed = changed.replace(UPGRADE_RESET_OLD, UPGRADE_RESET_NEW)
    return changed


MONTHLY_GUARD_MARKER = 'MONTHLY CARD FALSE POSITIVE GUARD'

# 月卡误判守卫: 领邮件后 ensure_main -> is_main -> handle_monthly_card 会用全屏
# 低阈值模板把邮箱奖励图标误判成月卡, 点击后 is_main 提前 return 使 back() 不执行,
# 邮箱关不掉 -> 超时抛异常 -> 错误恢复无限重启。月卡只该在登录阶段/每日月卡窗口检测。
MONTHLY_GUARD_OLD = """    def handle_monthly_card(self):
        monthly_card = self.find_monthly_card()"""

MONTHLY_GUARD_NEW = """    def handle_monthly_card(self):
        # MONTHLY CARD FALSE POSITIVE GUARD: 月卡弹窗只会在两个时机出现 —— 登录阶段
        # (logged_in=False) 和每日月卡时间窗口 (should_check_monthly_card()=True)。
        # 任务中途(已登录、非月卡时间)被 is_main 调用时, 全屏低阈值模板会把邮箱奖励
        # 等圆形图标误判成月卡, 点击后 is_main 提前 return 使 back() 不执行、邮箱关不掉,
        # ensure_main 超时抛异常 -> 错误恢复反复重启(死循环)。此时直接跳过检测。
        if getattr(self, 'logged_in', True) and not self.should_check_monthly_card():
            return False
        monthly_card = self.find_monthly_card()"""

MONTHLY_SET_OLD = """            self.wait_until(self.in_team_and_world, time_out=10,
                            post_action=lambda: self.click_relative(0.50, 0.89, after_sleep=1))
            # self.screenshot('monthly_card3')
            self.set_check_monthly_card(next_day=True)"""
MONTHLY_SET_NEW = """            entered = self.wait_until(self.in_team_and_world, time_out=10,
                            post_action=lambda: self.click_relative(0.50, 0.89, after_sleep=1))
            # self.screenshot('monthly_card3')
            # 只有确认领完月卡回到大世界才把检查推到明天; 否则视为误判, 保留检查以便真正领取。
            if entered:
                self.set_check_monthly_card(next_day=True)"""


def patch_monthly_guard(path: Path) -> int:
    """Independent, idempotent patch: suppress false-positive monthly card checks."""
    if not path.is_file():
        return 0
    text = path.read_text(encoding='utf-8')
    if MONTHLY_GUARD_MARKER in text:
        print(f'monthly guard already patched: {path}')
        return 0
    count_guard = text.count(MONTHLY_GUARD_OLD)
    count_set = text.count(MONTHLY_SET_OLD)
    if count_guard != 1 or count_set != 1:
        print(f'FAILED: monthly guard anchors not unique in {path} '
              f'(guard={count_guard}, set={count_set}); file left untouched')
        return 1
    text = text.replace(MONTHLY_GUARD_OLD, MONTHLY_GUARD_NEW)
    text = text.replace(MONTHLY_SET_OLD, MONTHLY_SET_NEW)
    backup = path.with_suffix(path.suffix + '.pre-monthly-guard')
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(text, encoding='utf-8')
    print(f'monthly guard patched: {path}')
    print(f'backup:  {backup}')
    return 0


def patch(path: Path) -> int:
    if not path.is_file():
        print(f'skip (not found): {path}')
        return 0
    text = path.read_text(encoding='utf-8')
    if MARKER in text:
        upgraded = upgrade_v2(text)
        if upgraded is None:
            return 1
        if upgraded != text:
            path.write_text(upgraded, encoding='utf-8')
            print(f'upgraded to graded-cooldown: {path}')
        else:
            print(f'already patched (v2): {path}')
        return 0
    for old, new in ((CONST_OLD, CONST_NEW), (CLICK_OLD, CLICK_NEW), (METHOD_ANCHOR, METHOD_NEW)):
        found = text.count(old)
        if found != 1:
            print(f'FAILED: expected one match for {old[:60]!r} in {path} (found {found}); file left untouched')
            return 1
        text = text.replace(old, new)
    backup = path.with_suffix(path.suffix + '.pre-cloud-entry')
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(text, encoding='utf-8')
    print(f'patched: {path}')
    print(f'backup:  {backup}')
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', nargs='?', type=Path)
    args = parser.parse_args(argv)
    targets = [args.path] if args.path else candidates()
    failed = 0
    for target in targets:
        failed |= patch(target)
    return failed


if __name__ == '__main__':
    raise SystemExit(main())
