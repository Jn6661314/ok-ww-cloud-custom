"""One-click launcher: select the 云游戏 device, pick an account, start ok-ww.

Examples::

    python tools/cloud_launch.py --account YOUR_ACCOUNT_ID
    python tools/cloud_launch.py --no-launch     # only change settings

The device file is backed up once as ``devices.json.pre-cloud``.  Switch back
to the PC client at any time from the app's device selector.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

APP_ROOT = Path.home() / 'AppData' / 'Local' / 'ok-ww'
WORKING = APP_ROOT / 'data' / 'apps' / 'ok-ww' / 'working'
DEVICES = WORKING / 'configs' / 'devices.json'


def select_cloud_device() -> None:
    if not DEVICES.exists():
        print(f'Device config not found: {DEVICES}')
        return
    data = json.loads(DEVICES.read_text(encoding='utf-8'))
    if data.get('preferred') == 'browser' and data.get('capture') == 'browser':
        print('Cloud device already selected.')
        return
    backup = DEVICES.with_suffix('.json.pre-cloud')
    if not backup.exists():
        shutil.copy2(DEVICES, backup)
        print(f'backup: {backup}')
    data['preferred'] = 'browser'
    data['capture'] = 'browser'
    DEVICES.write_text(json.dumps(data, ensure_ascii=False, indent=4) + '\n', encoding='utf-8')
    print('Selected cloud (browser) device.')


def set_account(account: str | None) -> None:
    if not account:
        return
    sys.path.insert(0, str(WORKING))
    from src import cloud_browser
    target = cloud_browser.set_active_account(account)
    print(f'Active account: {account} -> {target}')


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--account', help='Account key from MultiAccountConfig.json')
    parser.add_argument('--no-launch', action='store_true', help='Only update settings')
    args = parser.parse_args(argv)

    select_cloud_device()
    set_account(args.account)
    if args.no_launch:
        return 0
    exe = APP_ROOT / 'ok-ww.exe'
    if not exe.exists():
        print(f'Executable not found: {exe}')
        return 1
    subprocess.Popen([str(exe)], cwd=str(APP_ROOT), close_fds=True)
    print(f'Launched {exe}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
