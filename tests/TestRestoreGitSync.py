"""把定制提交进 repo 的 git、以及部署后自检的测试。

背景（v1.8.2 的真实事故）：pyappify 的 shared-checkout 布局是"git 数据放在
``repo``、应用文件放在 ``working``"。``restore.py`` 把 22 个定制文件写进
``working`` 之后，用户启动 ok-ww，启动器发现这些**被跟踪文件**与 git 不一致，
判定成"文件被篡改"，直接从 git 把它们还原 —— 整套定制（云鸣潮多账号、MuMu/安卓、
拉海洛、远控窗口）在界面上瞬间全部消失，只剩官方 v3.8.15 的样子。

根因不是 restore 写错了，而是定制只以"未提交改动"的形式存在：git 里没有它，
任何一次校验/还原都会把它抹掉。所以部署后必须把定制提交进 git。
"""

import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

REPO = Path(__file__).resolve().parent.parent
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))

import restore  # noqa: E402

HAS_GIT = shutil.which('git') is not None


def init_git_repo(path: Path) -> None:
    """建一个空的 git 仓库（带一次初始提交，模拟 repo 的官方基线）。"""
    env = {'GIT_AUTHOR_NAME': 'test', 'GIT_AUTHOR_EMAIL': 't@local',
           'GIT_COMMITTER_NAME': 'test', 'GIT_COMMITTER_EMAIL': 't@local'}
    import os
    run_env = dict(os.environ)
    run_env.update(env)
    subprocess.run(['git', 'init', '-q'], cwd=str(path), check=True, env=run_env)
    (path / 'README').write_text('base\n', encoding='utf-8')
    subprocess.run(['git', 'add', '--', 'README'], cwd=str(path), check=True, env=run_env)
    subprocess.run(['git', 'commit', '-q', '-m', 'upstream baseline'],
                   cwd=str(path), check=True, env=run_env)


class GitSyncTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.repo = self.root / 'repo'
        self.repo.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def test_skips_when_not_a_git_repo(self):
        """没有 .git 时安全跳过，不抛异常、不返回失败。"""
        with mock.patch.object(restore, 'RELATIVE_FILES', ['config.py']):
            (self.repo / 'config.py').write_text('custom\n', encoding='utf-8')
            self.assertEqual(restore.sync_repo_git(self.repo), 0)

    def test_skips_when_no_custom_files(self):
        """git 仓库里一个定制文件都没有时跳过。"""
        init_git_repo(self.repo)
        with mock.patch.object(restore, 'RELATIVE_FILES', ['config.py']):
            self.assertEqual(restore.sync_repo_git(self.repo), 0)

    @unittest.skipUnless(HAS_GIT, '需要 git')
    def test_commits_custom_file_changes(self):
        """定制改动会被提交进 git，HEAD 前进。"""
        init_git_repo(self.repo)
        (self.repo / 'config.py').write_text('base\n', encoding='utf-8')
        subprocess.run(['git', 'add', '--', 'config.py'], cwd=str(self.repo), check=True)
        subprocess.run(['git', '-c', 'user.name=t', '-c', 'user.email=t@local',
                        'commit', '-q', '-m', 'official config'],
                       cwd=str(self.repo), check=True)
        before = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=str(self.repo),
                                capture_output=True, text=True).stdout.strip()

        (self.repo / 'config.py').write_text('custom\n', encoding='utf-8')
        with mock.patch.object(restore, 'RELATIVE_FILES', ['config.py']):
            restore.sync_repo_git(self.repo)

        after = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=str(self.repo),
                               capture_output=True, text=True).stdout.strip()
        self.assertNotEqual(before, after)
        # 工作区应当是干净的：定制已经在 git 里
        status = subprocess.run(['git', 'status', '--short', '--untracked-files=no'],
                                cwd=str(self.repo), capture_output=True, text=True).stdout
        self.assertEqual(status.strip(), '')

    @unittest.skipUnless(HAS_GIT, '需要 git')
    def test_does_not_create_empty_commit(self):
        """已经是定制版时重复运行不产生空提交。"""
        init_git_repo(self.repo)
        (self.repo / 'config.py').write_text('custom\n', encoding='utf-8')
        with mock.patch.object(restore, 'RELATIVE_FILES', ['config.py']):
            restore.sync_repo_git(self.repo)
            first = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=str(self.repo),
                                   capture_output=True, text=True).stdout.strip()
            restore.sync_repo_git(self.repo)
            second = subprocess.run(['git', 'rev-parse', 'HEAD'], cwd=str(self.repo),
                                    capture_output=True, text=True).stdout.strip()
        self.assertEqual(first, second)

    @unittest.skipUnless(HAS_GIT, '需要 git')
    def test_creates_protective_tag(self):
        """提交后打上本地标签，避免切版本后定制提交变成孤立对象。"""
        init_git_repo(self.repo)
        (self.repo / 'config.py').write_text('custom\n', encoding='utf-8')
        with mock.patch.object(restore, 'RELATIVE_FILES', ['config.py']):
            restore.sync_repo_git(self.repo)
        tags = subprocess.run(['git', 'tag', '-l'], cwd=str(self.repo),
                              capture_output=True, text=True).stdout
        self.assertIn(restore.GIT_TAG, tags)


class VersionTagTest(unittest.TestCase):
    """版本 tag 必须指向定制提交，否则启动器 checkout -f 会切回官方。"""

    VERSION = 'v9.9.9'

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.repo = Path(self._tmp.name) / 'repo'
        self.repo.mkdir()

    def tearDown(self):
        self._tmp.cleanup()

    def _git(self, *args):
        return subprocess.run(['git', *args], cwd=str(self.repo), capture_output=True,
                              text=True).stdout.strip()

    def _head(self):
        return self._git('rev-parse', 'HEAD')

    def _tag_commit(self, name):
        return self._git('rev-parse', f'{name}^{{commit}}')

    def test_skips_when_not_a_git_repo(self):
        with mock.patch.object(restore, 'read_source_version', return_value=self.VERSION):
            self.assertEqual(restore.pin_version_tag_to_head(self.repo), 0)

    def test_skips_without_version(self):
        init_git_repo(self.repo)
        with mock.patch.object(restore, 'read_source_version', return_value=None):
            self.assertEqual(restore.pin_version_tag_to_head(self.repo), 0)

    @unittest.skipUnless(HAS_GIT, '需要 git')
    def test_moves_official_tag_to_custom_commit(self):
        """官方 tag 存在时必须移到 HEAD，并备份原指向。"""
        init_git_repo(self.repo)
        official = self._head()
        self._git('tag', '-a', self.VERSION, '-m', 'official release', official)
        (self.repo / 'config.py').write_text('custom\n', encoding='utf-8')
        with mock.patch.object(restore, 'RELATIVE_FILES', ['config.py']):
            restore.sync_repo_git(self.repo)
        custom = self._head()
        self.assertNotEqual(official, custom)

        with mock.patch.object(restore, 'read_source_version', return_value=self.VERSION):
            self.assertEqual(restore.pin_version_tag_to_head(self.repo), 0)

        self.assertEqual(self._tag_commit(self.VERSION), custom)
        self.assertEqual(self._tag_commit('official-' + self.VERSION), official)

    @unittest.skipUnless(HAS_GIT, '需要 git')
    def test_creates_tag_when_missing(self):
        init_git_repo(self.repo)
        with mock.patch.object(restore, 'read_source_version', return_value=self.VERSION):
            restore.pin_version_tag_to_head(self.repo)
        self.assertEqual(self._tag_commit(self.VERSION), self._head())

    @unittest.skipUnless(HAS_GIT, '需要 git')
    def test_idempotent_when_already_pointing_to_head(self):
        """已经指向定制提交时重复运行不再改动（不产生新 tag 对象）。"""
        init_git_repo(self.repo)
        official = self._head()
        self._git('tag', '-a', self.VERSION, '-m', 'official release', official)
        (self.repo / 'config.py').write_text('custom\n', encoding='utf-8')
        with mock.patch.object(restore, 'RELATIVE_FILES', ['config.py']):
            restore.sync_repo_git(self.repo)

        with mock.patch.object(restore, 'read_source_version', return_value=self.VERSION):
            restore.pin_version_tag_to_head(self.repo)
            first = self._git('rev-parse', f'refs/tags/{self.VERSION}')
            restore.pin_version_tag_to_head(self.repo)
            second = self._git('rev-parse', f'refs/tags/{self.VERSION}')

        self.assertEqual(first, second)
        # 备份 tag 保留的是官方提交，不会被第二次运行覆盖成定制提交
        self.assertEqual(self._tag_commit('official-' + self.VERSION), official)


class VerifyDeployTest(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.source = self.root / 'source'
        self.working = self.root / 'working'
        self.repo = self.root / 'repo'
        for path in (self.source, self.working, self.repo):
            (path / 'src').mkdir(parents=True)
            (path / 'src' / 'a.py').write_text('content\n', encoding='utf-8')

    def tearDown(self):
        self._tmp.cleanup()

    def test_passes_when_identical(self):
        with mock.patch.object(restore, 'FILES', self.source), \
                mock.patch.object(restore, 'RELATIVE_FILES', ['src/a.py']):
            self.assertEqual(restore.verify_deploy(self.working, self.repo), 0)

    def test_detects_reverted_file(self):
        """working 被还原成官方版（内容不同）时必须报出来。"""
        (self.working / 'src' / 'a.py').write_text('official\n', encoding='utf-8')
        with mock.patch.object(restore, 'FILES', self.source), \
                mock.patch.object(restore, 'RELATIVE_FILES', ['src/a.py']):
            self.assertEqual(restore.verify_deploy(self.working, self.repo), 1)

    def test_detects_missing_file(self):
        (self.repo / 'src' / 'a.py').unlink()
        with mock.patch.object(restore, 'FILES', self.source), \
                mock.patch.object(restore, 'RELATIVE_FILES', ['src/a.py']):
            self.assertEqual(restore.verify_deploy(self.working, self.repo), 1)


class CopyOverTest(unittest.TestCase):
    """目标文件被占用时的退路。

    投屏内核这种 exe 常常还带着上一次运行的进程，管理员权限下还可能杀不掉，
    直接覆盖会报 [WinError 32]。Windows 允许**重命名**正在运行的 exe（改的是
    目录项不是文件内容），所以先把旧文件挪走再复制 —— 整个部署不至于卡住。
    """

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.source = self.root / 'source.exe'
        self.target = self.root / 'target.exe'
        self.source.write_bytes(b'new')
        self.target.write_bytes(b'old')

    def tearDown(self):
        self._tmp.cleanup()

    def test_copies_when_the_target_is_free(self):
        restore.copy_over(self.source, self.target, '20260101')
        self.assertEqual(self.target.read_bytes(), b'new')

    def test_renames_the_busy_target_and_copies(self):
        """目标被占用时（复制报 PermissionError），改名腾位置再复制。"""
        real_copy = shutil.copy2

        def fake_copy(src, dst, *args, **kwargs):
            if Path(dst) == self.target and not getattr(fake_copy, 'failed', False):
                # 第一次复制（直接覆盖）失败，模拟被占用的 exe
                fake_copy.failed = True
                raise PermissionError(32, '另一个程序正在使用此文件')
            return real_copy(src, dst, *args, **kwargs)

        with mock.patch.object(restore.shutil, 'copy2', side_effect=fake_copy):
            restore.copy_over(self.source, self.target, '20260101')

        self.assertEqual(self.target.read_bytes(), b'new')
        # 旧文件被挪走了, 没丢
        moved = list(self.root.glob('target.exe.old*'))
        self.assertEqual(len(moved), 1)
        self.assertEqual(moved[0].read_bytes(), b'old')

    def test_puts_the_old_file_back_when_the_copy_still_fails(self):
        """改名之后还是复制不成功时, 旧文件要放回去, 不能把部署搞得更糟。"""
        calls = {'n': 0}

        def always_fail(src, dst, *args, **kwargs):
            calls['n'] += 1
            raise PermissionError(32, '另一个程序正在使用此文件')

        with mock.patch.object(restore.shutil, 'copy2', side_effect=always_fail):
            with self.assertRaises(PermissionError):
                restore.copy_over(self.source, self.target, '20260101')

        self.assertTrue(self.target.exists(), '旧文件没放回去')
        self.assertEqual(self.target.read_bytes(), b'old')


if __name__ == '__main__':
    unittest.main()
