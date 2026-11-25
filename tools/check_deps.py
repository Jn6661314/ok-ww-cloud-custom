# -*- coding: utf-8 -*-
"""依赖完整性审计脚本: 扫描 ok-ww 运行目录下全部源码的 import,
在实际运行环境(ok-ww 自带 python)中逐个验证, 并区分"缺失且危险"与"有保护的可选依赖"。

背景: ok-script 把 ADB 能力拆成可选依赖组 (ok-script[adb]), 安装/升级时若跳过
依赖同步, adbutils/uiautomator2 等就缺失, 运行时才炸 ModuleNotFoundError
(2026-11-25 实例: import adbutils 失败 -> 设备列表 None -> 'NoneType' object
is not subscriptable 连锁报错)。

用法: 用 ok-ww 自带 python 在 working 目录运行:
    "$LOCALAPPDATA/ok-ww/data/apps/ok-ww/python/python.exe" tools/check_deps.py [运行目录]

退出码: 0 = 无危险缺失; 1 = 存在顶层裸 import 且未保护的缺失包。
"""
import ast
import importlib.util
import os
import re
import sys

STDLIB = set(sys.stdlib_module_names)
LOCAL = {'ok', 'src', 'config', 'main', 'pyappify', 'ok_tasks', 'task', 'char', 'combat'}

# 已知有 try/except 或平台/配置分支保护的模块 -> 仅提示, 不算失败
KNOWN_GUARDED = {
    # paperclip.py 剪贴板: try/except + 平台判断 (macOS/Linux 才用)
    'AppKit', 'Foundation', 'PyQt5', 'PySide6', 'qtpy',
    # OCR 引擎备选: TaskExecutor 按配置分支懒加载, 默认 onnxocr(内置)
    'dgocr', 'paddleocr', 'rapidocr',
    # YOLO 后端: use_openvino=True(默认)走 OpenVINO, onnxruntime 仅在关闭时需要
    'onnxruntime',
    # 可选功能: opencc=简繁转换(auto_simplify), polib=翻译文件更新
    'opencc', 'polib',
}

# 顶层裸 import 且无保护的高危模块 -> 一律视为必须安装
# (adbutils/uiautomator2/d3dshot 属 ok-script[adb] / 截屏回退组, 缺了就是运行时炸)


def collect_imports(root):
    mods = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames
                       if d not in ('__pycache__', '.git', 'node_modules')]
        for fn in filenames:
            if not fn.endswith('.py'):
                continue
            p = os.path.join(dirpath, fn)
            try:
                tree = ast.parse(open(p, encoding='utf-8', errors='ignore').read())
            except Exception:
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for a in node.names:
                        mods.setdefault(a.name.split('.')[0], set()).add(p)
                elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                    mods.setdefault(node.module.split('.')[0], set()).add(p)
    return {m: v for m, v in mods.items() if m not in STDLIB and m not in LOCAL}


def is_lazy_import(module, files):
    """import 语句是否在函数/property 内(懒加载) -> 用时才炸, 属软风险。"""
    for p in files:
        try:
            src = open(p, encoding='utf-8', errors='ignore').read()
        except OSError:
            continue
        # 粗判: import 前有缩进即懒加载 (顶层 import 无缩进)
        if re.search(r'^\s+(import|%s)\b' % re.escape(module), src, re.M):
            return True
    return False


def main():
    root = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else os.getcwd())
    print(f'审计目录: {root}')
    third = collect_imports(root)
    print(f'第三方模块 {len(third)} 个\n')

    failures, warnings = [], []
    for m in sorted(third):
        try:
            spec = importlib.util.find_spec(m)
            if spec is None:
                raise ModuleNotFoundError(m)
            __import__(m)
        except Exception as e:
            detail = f'{m}: {type(e).__name__} ({e})' if not isinstance(e, ModuleNotFoundError) \
                else f'{m}: 未安装 (ModuleNotFoundError)'
            if m in KNOWN_GUARDED:
                warnings.append(detail + '  [有保护的可选依赖, 可忽略]')
            elif is_lazy_import(m, third[m]):
                warnings.append(detail + '  [懒加载, 仅在用到相关功能时报错]')
            else:
                failures.append(detail + f'  [使用文件: {sorted(third[m])[:2]}]')

    if warnings:
        print('== 可选/软风险 ==')
        for w in warnings:
            print('  -', w)
        print()
    if failures:
        print('== 危险缺失 (会直接炸运行) ==')
        for f in failures:
            print('  -', f)
        print('\n修复: 用 ok-ww 自带 python 安装, 例如')
        print('  "$LOCALAPPDATA/ok-ww/data/apps/ok-ww/python/python.exe" '
              '-m pip install --only-binary=:all: <包名>')
        return 1
    print('结论: 所有必需依赖均已安装, 环境健康。')
    return 0


if __name__ == '__main__':
    sys.exit(main())
