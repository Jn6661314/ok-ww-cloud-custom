"""Deprecated: Nightmare-Nest farming is no longer disabled by default.

Earlier builds forced ``Farm Nightmare Nest for Daily Echo`` off because the
cloud game could idle in a "no combat -> trigger combat" loop.  The user later
asked to restore it, so this patch is now a no-op and is kept only so old
install/restore scripts that still import it keep working.

Usage::

    python tools/patch_daily_no_nest.py [path]   # does nothing
"""

from __future__ import annotations

import argparse
from pathlib import Path

MARKER = 'NO NEST PATCH'


def patch(path: Path) -> int:
    """No-op.  Kept for backward compatibility with older install scripts."""
    print(f'no-op (nest farming enabled by default): {path}')
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('path', nargs='?', type=Path, default=Path('src/task/DailyTask.py'))
    args = parser.parse_args(argv)
    return patch(args.path)


if __name__ == '__main__':
    raise SystemExit(main())
