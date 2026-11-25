"""Install the custom patches into a local ok-ww installation.

The pyappify build keeps its running Python source in
``%LOCALAPPDATA%/ok-ww/data/apps/ok-ww/working`` and a second copy in
``.../repo``.  This script copies **every** custom file into both places and
additionally drops the offline workshop cache into ``configs``.

The file list lives in ``restore.py`` (``RELATIVE_FILES``) so that the first
install and every later "restore after an official update" stay in sync —
previously this script kept its own, much shorter list, so a fresh install
silently missed 17 files (including ``ok/device/DeviceManager.py`` and
``src/task/BaseWWTask.py``) and the app failed to start.

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

sys.path.insert(0, str(SOURCE))
try:
    from restore import RELATIVE_FILES
except ImportError:  # pragma: no cover - restore.py is always shipped with the repo
    raise SystemExit(
        'restore.py not found next to tools/. Please re-download the whole '
        'repository instead of a single file.')

# Upstream deleted the workshop hosts.  The community mirror snapshot lives in
# the backup folder and is copied into configs so the workshop opens offline.
WORKSHOP_CACHE_SOURCE = SOURCE / 'workshop_cache'


def backup(path: Path) -> None:
    target = path.with_suffix(path.suffix + '.pre-cloud')
    if not target.exists():
        shutil.copy2(path, target)
        print(f'backup:  {target}')


def install(working: Path) -> int:
    if not working.is_dir():
        print(f'Not installed: {working} does not exist')
        print('Please pass the real working directory, e.g. '
              'python tools/install_to_local_app.py "D:/path/to/working"')
        return 1
    print(f'Target: {working}')

    base = working.parent
    # "working" is the directory that actually runs; "repo" is the editable
    # source copy.  Both must receive the custom files, otherwise the next
    # official update restores the working copy from the untouched repo.
    targets = [working]
    repo = base / 'repo'
    if repo.is_dir():
        targets.append(repo)
    else:
        print(f'note: {repo} not found, only the working directory is patched')

    missing = [f for f in RELATIVE_FILES if not (SOURCE / f).is_file()]
    if missing:
        print(f'ERROR: the following custom files are missing from {SOURCE}:')
        for f in missing:
            print(f'    {f}')
        print('Please re-download the whole repository.')
        return 1

    copied = 0
    for root in targets:
        for relative in RELATIVE_FILES:
            source = SOURCE / relative
            target = root / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if target.exists():
                backup(target)
            shutil.copy2(source, target)
            copied += 1
        print(f'copied {len(RELATIVE_FILES)} files -> {root}')

    if WORKSHOP_CACHE_SOURCE.is_dir():
        for root in targets:
            cache_target = root / 'configs' / 'workshop_cache'
            cache_target.mkdir(parents=True, exist_ok=True)
            shutil.copytree(WORKSHOP_CACHE_SOURCE, cache_target, dirs_exist_ok=True)
        print(f'copied workshop snapshot -> {targets[0] / "configs" / "workshop_cache"}')

    print(f'\nDone: {copied} file copies across {len(targets)} director'
          f'{"y" if len(targets) == 1 else "ies"}.')
    print('Start ok-ww, select the 云游戏 device, then run CloudMultiAccountTask.')
    print('If a later official update overwrites the patch, close ok-ww and '
          'run python restore.py (or double-click 一键恢复.bat).')
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('working', nargs='?', type=Path, default=DEFAULT_WORKING)
    return install(parser.parse_args(argv).working)


if __name__ == '__main__':
    raise SystemExit(main())
