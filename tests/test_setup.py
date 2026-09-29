"""SETUP 的独立安装与失败前置检查；所有破坏性夹具操作只针对临时副本。

运行：python -m unittest discover -s tests -v
"""
import contextlib
import importlib.util
import io
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock


SKILL = Path(__file__).resolve().parents[1] / "skills" / "novel"
# 独立列出发布契约，避免测试跟着实现一起漏掉必需资产。
EXPECTED_ASSETS = (
    "模板/设定/世界观.md",
    "模板/设定/力量体系.md",
    "模板/设定/角色.md",
    "模板/设定/关系体系.md",
    "模板/设定/势力.md",
    "模板/设定/时间线.md",
    "模板/大纲/伏笔表.md",
    "模板/大纲/卷纲.md",
    "模板/大纲/总纲.md",
    "读者画像/晋江.md",
    "读者画像/番茄.md",
    "读者画像/起点.md",
    "AI腔清单.md",
    "套话候选.txt",
)


def snapshot(root):
    """同时比较文件内容、修改时间及目录集合，检测意外覆盖或部分写入。"""
    return {
        path.relative_to(root).as_posix(): (
            None if path.is_dir() else (path.read_bytes(), path.stat().st_mtime_ns)
        )
        for path in root.rglob("*")
    }


class SetupTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.tmp = Path(temporary.name)
        # 刻意不用仓库、skills 或 novel 这些目录名，验证可独立安装。
        self.skill = self.tmp / "自定义 工具目录" / "独立安装"
        shutil.copytree(
            SKILL, self.skill,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "*.pyo", ".pytest_cache"),
        )
        self.script = self.skill / "scripts" / "setup.py"
        self.assets = self.skill / "assets" / "规范"
        self.cwd = self.tmp / "working"
        self.cwd.mkdir()
        self.target = self.tmp / "project"

    def run_setup(self, *args, encoding="utf-8"):
        env = os.environ.copy()
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONIOENCODING"] = encoding
        return subprocess.run(
            [sys.executable, str(self.script), *map(str, args)],
            cwd=self.cwd, env=env, capture_output=True, text=True,
            encoding=encoding, timeout=30,
        )

    def assert_success(self, result, target):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("SETUP 完成", result.stdout)
        self.assertEqual(result.stderr, "")
        for name in ("规范", "作品", "对标库"):
            self.assertTrue((target / name).is_dir(), name)
        for name in EXPECTED_ASSETS:
            self.assertTrue((target / "规范" / name).is_file(), name)

    def assert_preflight_failure(self, *args):
        before = snapshot(self.tmp)
        result = self.run_setup(*args)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(result.stdout, "")
        self.assertTrue(result.stderr.strip())
        self.assertNotIn("SETUP 完成", result.stdout + result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(snapshot(self.tmp), before)
        return result

    def test_empty_project_receives_all_fourteen_assets(self):
        self.assert_success(self.run_setup(self.target), self.target)
        files = {p.relative_to(self.target / "规范").as_posix()
                 for p in (self.target / "规范").rglob("*") if p.is_file()}
        self.assertEqual(files, set(EXPECTED_ASSETS))
        self.assertEqual(len(files), 14)
        for name in EXPECTED_ASSETS:
            self.assertEqual((self.target / "规范" / name).read_bytes(),
                             (self.assets / name).read_bytes())
        self.assertEqual(list((self.target / "作品").iterdir()), [])
        self.assertEqual(list((self.target / "对标库").iterdir()), [])

    def test_existing_empty_project_is_supported(self):
        self.target.mkdir()
        self.assert_success(self.run_setup(self.target), self.target)

    def test_repeated_setup_is_idempotent(self):
        self.assert_success(self.run_setup(self.target), self.target)
        before = snapshot(self.target)
        result = self.run_setup(self.target)
        self.assert_success(result, self.target)
        self.assertIn("铺了 0 个文件", result.stdout)
        self.assertEqual(snapshot(self.target), before)

    def test_user_edits_empty_files_and_unrelated_work_are_preserved(self):
        edits = {
            "规范/模板/设定/角色.md": b"user edits\r\n\x00",
            "规范/AI腔清单.md": b"",
            "作品/原创/正文/0001.md": "我的原创正文。\n".encode("utf-8"),
            "对标库/自备/notes.txt": b"private notes\n",
        }
        for name, body in edits.items():
            path = self.target / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(body)
        before = snapshot(self.target)
        self.assert_success(self.run_setup(self.target), self.target)
        after = snapshot(self.target)
        for name in edits:
            self.assertEqual(after[name], before[name])

    def test_missing_file_is_repaired_inside_existing_directories(self):
        self.assert_success(self.run_setup(self.target), self.target)
        missing = self.target / "规范" / "模板/大纲/卷纲.md"
        missing.unlink()
        before = snapshot(self.target)
        self.assert_success(self.run_setup(self.target), self.target)
        after = snapshot(self.target)
        self.assertEqual(missing.read_bytes(), (self.assets / "模板/大纲/卷纲.md").read_bytes())
        for name, state in before.items():
            self.assertEqual(after[name], state)

    def test_missing_asset_directory_fails_before_writing(self):
        shutil.rmtree(self.assets)
        self.assert_preflight_failure(self.target)
        self.assertFalse(self.target.exists())

    def test_asset_directory_must_be_a_directory(self):
        shutil.rmtree(self.assets)
        self.assets.write_bytes(b"not a directory")
        self.assert_preflight_failure(self.target)

    def test_every_required_asset_is_checked_before_writing(self):
        for name in EXPECTED_ASSETS:
            with self.subTest(asset=name):
                asset = self.assets / name
                body = asset.read_bytes()
                asset.unlink()
                try:
                    self.assert_preflight_failure(self.target)
                    self.assertFalse(self.target.exists())
                finally:
                    asset.write_bytes(body)

    def test_empty_and_whitespace_only_assets_are_rejected(self):
        for name in EXPECTED_ASSETS:
            asset = self.assets / name
            body = asset.read_bytes()
            for empty in (b"", b" \r\n\t"):
                with self.subTest(asset=name, content=empty):
                    asset.write_bytes(empty)
                    try:
                        self.assert_preflight_failure(self.target)
                    finally:
                        asset.write_bytes(body)

    def test_required_asset_cannot_be_a_directory(self):
        asset = self.assets / EXPECTED_ASSETS[-1]
        asset.unlink()
        asset.mkdir()
        self.assert_preflight_failure(self.target)

    def test_source_is_validated_even_when_project_is_already_complete(self):
        self.assert_success(self.run_setup(self.target), self.target)
        (self.assets / EXPECTED_ASSETS[0]).unlink()
        self.assert_preflight_failure(self.target)

    def test_files_blocking_target_directories_fail_before_writing(self):
        locations = (".", "作品", "对标库", "规范", "规范/模板",
                     "规范/模板/设定", "规范/模板/大纲", "规范/读者画像")
        for index, name in enumerate(locations):
            with self.subTest(location=name):
                target = self.tmp / f"conflict-{index}"
                blocker = target / name
                blocker.parent.mkdir(parents=True, exist_ok=True)
                blocker.write_bytes(b"keep this file")
                self.assert_preflight_failure(target)

    def test_directories_blocking_target_files_fail_before_writing(self):
        for index, name in enumerate(EXPECTED_ASSETS):
            with self.subTest(asset=name):
                target = self.tmp / f"file-conflict-{index}"
                blocker = target / "规范" / name
                blocker.mkdir(parents=True)
                (blocker / "keep.txt").write_bytes(b"keep directory contents")
                self.assert_preflight_failure(target)

    def test_file_in_target_ancestors_fails_before_writing(self):
        blocker = self.tmp / "blocked-parent"
        blocker.write_bytes(b"keep ancestor")
        self.assert_preflight_failure(blocker / "nested" / "project")

    def test_explicit_relative_target_is_resolved_instead_of_cwd(self):
        self.assert_success(self.run_setup("../chosen project"), self.tmp / "chosen project")
        self.assertEqual(list(self.cwd.iterdir()), [])

    def test_no_argument_uses_cwd_not_installation_directory(self):
        before = snapshot(self.skill)
        self.assert_success(self.run_setup(), self.cwd)
        self.assertEqual(snapshot(self.skill), before)
        self.assertFalse(self.target.exists())

    def test_unicode_spaces_and_arbitrary_installation_parent(self):
        target = self.tmp / "创作 空间" / "长篇 一"
        before = snapshot(self.skill)
        self.assertNotEqual(self.skill.parent.name, "skills")
        self.assert_success(self.run_setup(target), target)
        self.assertEqual(snapshot(self.skill), before)

    def test_python_api_keeps_optional_project_root(self):
        spec = importlib.util.spec_from_file_location("setup_under_test", self.script)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with contextlib.redirect_stdout(io.StringIO()):
            with mock.patch.object(module.Path, "cwd", return_value=self.cwd):
                self.assertIsNone(module.setup())
            with mock.patch.object(module.Path, "cwd", side_effect=AssertionError("unexpected cwd lookup")):
                self.assertIsNone(module.setup(str(self.target)))
        for target in (self.cwd, self.target):
            self.assertTrue((target / "规范" / "套话候选.txt").is_file())

    def test_bad_cli_arguments_are_friendly_and_do_not_write(self):
        for args in ((self.target, "unexpected"), ("--unknown-option",)):
            with self.subTest(args=args):
                result = self.assert_preflight_failure(*args)
                self.assertEqual(result.returncode, 2)
                self.assertIn("usage:", result.stderr)

    def test_output_is_compatible_with_windows_gbk_console(self):
        self.assert_success(self.run_setup(self.target, encoding="gbk"), self.target)


if __name__ == "__main__":
    unittest.main()
