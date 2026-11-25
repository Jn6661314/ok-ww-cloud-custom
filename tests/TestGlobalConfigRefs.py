"""全局配置名的一致性检查。

事故背景（v1.8.1 引入、v1.8.3 后暴露）：
v1.8.1 把全局配置 ``MuMu/安卓 Config`` 改名为 ``MuMu 安卓 Config``（配置名不能含 ``/``，
框架会按 ``configs/<名称>.json`` 落盘，斜杠会变成子目录），但 ``src/task/BaseWWTask.py``
里的读取处忘了同步：

    self.android_config = self.get_global_config('MuMu/安卓 Config')

于是任何任务实例化时都会抛 ``RuntimeError: Can not find global config MuMu/安卓 Config``，
ok-ww 启动直接失败、连重试三次后退出（23:56 的日志）。

本测试用 AST 静态扫描，不导入 config.py（避免依赖 cv2 / PySide6）：

1. 收集 config.py 里所有 ``ConfigOption('<名字>', ...)`` 的注册名；
2. 收集 src/ 下所有 ``get_global_config('<名字>')`` 的字面量引用，必须都在注册名里；
3. 收集 src/ 下 ``XXX_CONFIG_NAME = '<名字>'`` 这类常量，必须都在注册名里
   （如 ``src/stream_window.py`` 的 ``STREAM_CONFIG_NAME``）；
4. 注册名自身不得含 ``/``（否则配置会被写进子目录）。
"""

import ast
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SCAN_DIRS = ('src',)
SKIP_PARTS = {'.git', '__pycache__', 'tests', 'ok-ww-update', 'cache'}


def _call_name(node: ast.Call):
    func = node.func
    return getattr(func, 'id', None) or getattr(func, 'attr', None)


def _str_arg(node: ast.Call):
    if node.args and isinstance(node.args[0], ast.Constant) \
            and isinstance(node.args[0].value, str):
        return node.args[0].value
    return None


def registered_config_names() -> set:
    """config.py 里所有 ConfigOption 的注册名。"""
    tree = ast.parse((REPO / 'config.py').read_text(encoding='utf-8'))
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and _call_name(node) == 'ConfigOption':
            name = _str_arg(node)
            if name:
                names.add(name)
    return names


def _scan_py_files():
    for folder in SCAN_DIRS:
        root = REPO / folder
        if not root.is_dir():
            continue
        for path in sorted(root.rglob('*.py')):
            if SKIP_PARTS & set(path.parts):
                continue
            yield path


def global_config_references():
    """(文件, 行号, 配置名) 形式的 get_global_config 字面量引用。"""
    refs = []
    for path in _scan_py_files():
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and _call_name(node) == 'get_global_config':
                name = _str_arg(node)
                if name:
                    refs.append((path.relative_to(REPO), node.lineno, name))
    return refs


def config_name_constants():
    """(文件, 行号, 常量名, 值) 形式的配置名常量赋值。"""
    found = []
    for path in _scan_py_files():
        tree = ast.parse(path.read_text(encoding='utf-8'))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Assign) or len(node.targets) != 1:
                continue
            target = node.targets[0]
            # 只认 "<前缀>_CONFIG_NAME"：全局配置名常量都这么命名。
            # 裸 CONFIG_NAME 是账号配置之类的文件名（如 MultiAccountConfig.json），不在此列。
            if not isinstance(target, ast.Name) or not target.id.endswith('_CONFIG_NAME'):
                continue
            value = node.value
            if isinstance(value, ast.Constant) and isinstance(value.value, str):
                if value.value.endswith(('.json', '.yaml', '.yml')):
                    continue
                found.append((path.relative_to(REPO), node.lineno, target.id, value.value))
    return found


class GlobalConfigRefsTest(unittest.TestCase):
    def setUp(self):
        self.names = registered_config_names()

    def test_registered_names_found(self):
        """先确认解析器真的读到了注册名，避免测试因解析失败而空转。"""
        self.assertIn('MuMu 安卓 Config', self.names)
        self.assertIn('远控串流窗口(试验性)', self.names)

    def test_no_slash_in_registered_names(self):
        """配置名不能含 /（否则配置会落到 configs/子目录/xxx.json）。"""
        offenders = [n for n in self.names if '/' in n]
        self.assertEqual(offenders, [], f'全局配置名不能含斜杠: {offenders}')

    def test_get_global_config_names_are_registered(self):
        """代码里读取的每个配置名都必须有对应的 ConfigOption。"""
        missing = [(str(f), line, name) for f, line, name in global_config_references()
                   if name not in self.names]
        self.assertEqual(missing, [],
                         'get_global_config 引用了未注册的配置名（改名时漏改？）: '
                         + ', '.join(f'{f}:{line} -> {name}' for f, line, name in missing))

    def test_config_name_constants_are_registered(self):
        """*_CONFIG_NAME 常量（运行时读取用的名字）也必须在注册名里。"""
        consts = config_name_constants()
        self.assertTrue(consts, '应当至少扫到 stream_window 的 STREAM_CONFIG_NAME')
        missing = [(str(f), line, const, value) for f, line, const, value in consts
                   if value not in self.names]
        self.assertEqual(missing, [],
                         '配置名常量指向了未注册的名字: '
                         + ', '.join(f'{f}:{line} {const}={value}' for f, line, const, value in missing))


if __name__ == '__main__':
    unittest.main()
