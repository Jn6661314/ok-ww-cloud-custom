"""Make the cloud game accept Playwright input while the browser is unfocused.

Cloud-game SDKs commonly check ``document.hasFocus()`` / ``visibilityState`` or
listen for ``blur`` before accepting pointer and keyboard input.  A Playwright
window that is not the OS foreground window therefore appears to ignore every
synthetic click, which forces the user to click the browser window first.

This idempotent patch injects a small init script that reports the page as
always focused/visible and neutralises ``blur``.  It is injected both as an
init script (new pages) and into the already loaded page at browser start.

Set ``browser.background_input = False`` in config.py to disable it.

Usage::

    python tools/patch_ok_script_background.py [path/to/ok/device/capture_methods/browser.py]
"""

from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

MARKER = 'OK-WW BACKGROUND INPUT PATCH'

CONSTANT_ANCHOR = "  return true;\n}'''\n\n\nclass BrowserCaptureMethod(BaseCaptureMethod):"
CONSTANT_NEW = """  return true;
}'''

# {MARKER}: cloud game input must work without OS window focus.
OK_BACKGROUND_JS = '''() => {
  if (window.__okBackgroundInput === undefined) {
    window.__okBackgroundInput = true;
    Object.defineProperty(document, 'hasFocus', {configurable: true, value: () => true});
    Object.defineProperty(document, 'hidden', {configurable: true, get: () => false});
    Object.defineProperty(document, 'visibilityState', {configurable: true, get: () => 'visible'});
    window.addEventListener('blur', () => window.dispatchEvent(new Event('focus')));
    window.dispatchEvent(new Event('focus'));
  }
  return true;
}'''


class BrowserCaptureMethod(BaseCaptureMethod):"""

INIT_OLD = """        fake_pointer_lock = self.config.get('fake_pointer_lock', True)
        if fake_pointer_lock:
            await self.browser.add_init_script(script=f'({FAKE_POINTER_LOCK_JS})()')"""
INIT_NEW = """        fake_pointer_lock = self.config.get('fake_pointer_lock', True)
        if fake_pointer_lock:
            await self.browser.add_init_script(script=f'({FAKE_POINTER_LOCK_JS})()')
        background_input = self.config.get('background_input', True)
        if background_input:
            # {MARKER}: keep the cloud game accepting input when unfocused.
            await self.browser.add_init_script(script=f'({OK_BACKGROUND_JS})()')"""

EVAL_OLD = """        if fake_pointer_lock:
            # A reused page loaded before the init script was registered.
            await self.page.evaluate(FAKE_POINTER_LOCK_JS)"""
EVAL_NEW = """        if fake_pointer_lock:
            # A reused page loaded before the init script was registered.
            await self.page.evaluate(FAKE_POINTER_LOCK_JS)
        if background_input:
            await self.page.evaluate(OK_BACKGROUND_JS)"""


def candidates() -> list[Path]:
    here = Path(__file__).resolve().parent.parent
    paths = [
        Path.cwd() / 'ok' / 'device' / 'capture_methods' / 'browser.py',
        here / 'ok' / 'device' / 'capture_methods' / 'browser.py',
        (Path.home() / 'AppData' / 'Local' / 'ok-ww' / 'data' / 'apps'
         / 'ok-ww' / 'working' / 'ok' / 'device' / 'capture_methods' / 'browser.py'),
    ]
    unique = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    return unique


def patch(path: Path) -> int:
    if not path.is_file():
        print(f'skip (not found): {path}')
        return 0
    text = path.read_text(encoding='utf-8')
    if MARKER in text:
        print(f'already patched: {path}')
        return 0

    for old, new in ((CONSTANT_ANCHOR, CONSTANT_NEW), (INIT_OLD, INIT_NEW), (EVAL_OLD, EVAL_NEW)):
        if text.count(old) != 1:
            print(f'FAILED: expected one match for {old[:60]!r} in {path} (found {text.count(old)}); '
                  'file left untouched')
            return 1
        text = text.replace(old, new.replace('{MARKER}', MARKER))

    backup = path.with_suffix(path.suffix + '.pre-background')
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
