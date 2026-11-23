"""Enable per-account cookie profiles in ok-script's BrowserCaptureMethod.

ok-script hardcodes ``user_data_dir = os.path.join('cache', 'playwright')`` and
never persists ``storage_state`` explicitly.  This script applies small,
idempotent edits to any local copy of
``ok/device/capture_methods/browser.py``:

1. Resolve the profile directory from ``config['user_data_dir']`` (string or
   zero-argument callable), then the ``OK_WW_CLOUD_PROFILE`` environment
   variable, falling back to the original ``cache/playwright``.
2. After launch, restore cookies via ``context.add_cookies()`` and localStorage
   via ``add_init_script()``.  IMPORTANT: ``launch_persistent_context()`` does
   NOT accept a ``storage_state`` keyword (only ``browser.new_context()``
   does); passing it makes every browser channel fail to start.
3. Write ``storage_state.json`` when the browser closes, so logins survive
   restarts and account switches.

The script detects and upgrades the older V1 patch (which passed the illegal
``storage_state`` kwarg) in place.

Usage::

    python tools/patch_ok_script_browser.py [path/to/ok/device/capture_methods/browser.py]

With no path, common installations are detected automatically.  Re-running is
safe: V2 files are reported as already patched.
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

V1_MARKER = 'OK-WW CLOUD ACCOUNT PATCH'
V2_MARKER = 'OK-WW CLOUD ACCOUNT PROFILE V2'

# --- anchors in a pristine (unpatched) ok-script file ---------------------
LAUNCH_OLD = "user_data_dir = os.path.join('cache', 'playwright')"
CONTEXT_OLD = """                    viewport={'width': width, 'height': height},
                    device_scale_factor=1
                )"""
RESTORE_ANCHOR = """        if self.browser is None:
            raise Exception("Failed to launch system browser.")

        fake_pointer_lock = self.config.get('fake_pointer_lock', True)"""
CLOSE_OLD = """        if self.browser:
            try:
                await self.browser.close()"""

# --- exact code produced by the older, broken V1 patch --------------------
V1_LAUNCH = """        # OK-WW CLOUD ACCOUNT PATCH: per-account browser profile (ok-wuthering-waves extension).
        _cloud_dir = self.config.get('user_data_dir')
        if callable(_cloud_dir):
            _cloud_dir = _cloud_dir()
        user_data_dir = str(_cloud_dir) if _cloud_dir else os.environ.get('OK_WW_CLOUD_PROFILE')
        user_data_dir = user_data_dir or os.path.join('cache', 'playwright')
        os.makedirs(user_data_dir, exist_ok=True)
        self.user_data_dir = user_data_dir
        _cloud_state = os.path.join(user_data_dir, 'storage_state.json')
        launch_kwargs = {}
        if os.path.isfile(_cloud_state):
            launch_kwargs['storage_state'] = _cloud_state"""
V1_CONTEXT = """                    viewport={'width': width, 'height': height},
                    device_scale_factor=1,
                    **launch_kwargs
                )"""

# --- V2 replacement: NO storage_state kwarg, restore via context API ------
PROFILE_BLOCK = """        # OK-WW CLOUD ACCOUNT PROFILE V2: per-account browser profile (ok-wuthering-waves extension).
        # launch_persistent_context() has NO storage_state parameter; restoring a
        # saved login is done through the context API just after launch (below).
        _cloud_dir = self.config.get('user_data_dir')
        if callable(_cloud_dir):
            _cloud_dir = _cloud_dir()
        user_data_dir = str(_cloud_dir) if _cloud_dir else os.environ.get('OK_WW_CLOUD_PROFILE')
        user_data_dir = user_data_dir or os.path.join('cache', 'playwright')
        os.makedirs(user_data_dir, exist_ok=True)
        self.user_data_dir = user_data_dir"""

CONTEXT_CLEAN = """                    viewport={'width': width, 'height': height},
                    device_scale_factor=1
                )"""

RESTORE_BLOCK = """        if self.browser is None:
            raise Exception("Failed to launch system browser.")

        # OK-WW CLOUD ACCOUNT PROFILE V2: restore cookies/localStorage for this account.
        _state_path = os.path.join(self.user_data_dir, 'storage_state.json')
        if os.path.isfile(_state_path):
            try:
                import json as _json
                with open(_state_path, encoding='utf-8') as _f:
                    _saved = _json.load(_f)
                _saved_cookies = _saved.get('cookies') or []
                if _saved_cookies:
                    await self.browser.add_cookies(_saved_cookies)
                for _origin in (_saved.get('origins') or []):
                    _url = _origin.get('origin', '')
                    for _entry in (_origin.get('localStorage') or []):
                        _name = _entry.get('name', '')
                        _value = _entry.get('value', '')
                        await self.browser.add_init_script(
                            script="if (location.origin === " + _json.dumps(_url)
                            + ") { try { localStorage.setItem(" + _json.dumps(_name)
                            + ", " + _json.dumps(_value) + "); } catch (e) {} }")
            except Exception as _e:
                logger.warning(f"Failed to restore browser storage state: {_e}")

        fake_pointer_lock = self.config.get('fake_pointer_lock', True)"""

CLOSE_NEW = """        if self.browser:
            try:
                # Persist cookies/localStorage for this account on exit.
                _state_dir = getattr(self, 'user_data_dir', os.path.join('cache', 'playwright'))
                await self.browser.storage_state(path=os.path.join(_state_dir, 'storage_state.json'))
            except Exception as e:
                logger.warning(f"Failed to save browser storage state: {e}")
            try:
                await self.browser.close()"""


def candidates() -> list[Path]:
    paths = []
    here = Path(__file__).resolve().parent.parent
    env = Path(sys.argv[0]).resolve().parent
    for root in (Path.cwd(), here, env):
        paths.append(root / 'ok' / 'device' / 'capture_methods' / 'browser.py')
    installed = Path.home() / 'AppData' / 'Local' / 'ok-ww' / 'data' / 'apps' / 'ok-ww' / 'working'
    paths.append(installed / 'ok' / 'device' / 'capture_methods' / 'browser.py')
    unique = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    return unique


def _replace_once(text: str, old: str, new: str, path: Path) -> str:
    found = text.count(old)
    if found != 1:
        raise ValueError(f'expected one match for {old[:60]!r} in {path}, found {found}')
    return text.replace(old, new)


def patch(path: Path) -> int:
    if not path.is_file():
        print(f'skip (not found): {path}')
        return 0
    original = path.read_text(encoding='utf-8')
    if V2_MARKER in original:
        print(f'already patched (v2): {path}')
        return 0

    text = original
    try:
        if V1_MARKER in text:
            # Upgrade the broken V1 patch in place (illegal storage_state kwarg).
            text = _replace_once(text, V1_LAUNCH, PROFILE_BLOCK, path)
            text = _replace_once(text, V1_CONTEXT, CONTEXT_CLEAN, path)
            text = _replace_once(text, RESTORE_ANCHOR, RESTORE_BLOCK, path)
            action = 'upgraded v1->v2'
        else:
            # Fresh patch on a pristine ok-script file.
            text = _replace_once(text, LAUNCH_OLD, PROFILE_BLOCK, path)
            text = _replace_once(text, CONTEXT_OLD, CONTEXT_CLEAN, path)
            text = _replace_once(text, RESTORE_ANCHOR, RESTORE_BLOCK, path)
            text = _replace_once(text, CLOSE_OLD, CLOSE_NEW, path)
            action = 'patched v2'
    except ValueError as error:
        print(f'FAILED: {error}; file left untouched')
        return 1

    backup = path.with_suffix(path.suffix + '.pre-cloud-patch')
    if not backup.exists():
        shutil.copy2(path, backup)
    path.write_text(text, encoding='utf-8')
    print(f'{action}: {path}')
    print(f'backup:  {backup}')
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', nargs='?', type=Path, help='Path to browser.py')
    args = parser.parse_args(argv)
    targets = [args.path] if args.path else candidates()
    failed = 0
    for target in targets:
        failed |= patch(target)
    return failed


if __name__ == '__main__':
    raise SystemExit(main())
