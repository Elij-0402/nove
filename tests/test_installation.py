"""从独立工作区验证复制及链接安装，不调用模型或触碰作者资料。"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILLS = tuple(sorted(p.name for p in (ROOT / "skills").iterdir() if p.is_dir()))
SOURCE = """第1章 夜信
小岚推开门。
“信到了。”阿舟说。
第2章 空船
河上只有一条空船。
“先别上去。”
第3章 回声
两人沿着岸走。钟声停了。
第4章 天明
门在天亮前打开了。
"""


def snapshot(root):
    return {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in root.rglob("*") if p.is_file() and "__pycache__" not in p.parts}


def run(script, *args, cwd):
    env = {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}
    result = subprocess.run([sys.executable, str(script), *map(str, args)],
                            cwd=cwd, env=env, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr.decode("utf-8", errors="replace"))
    return result.stdout


class 安装链路(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="novel-install-")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.workspace = self.base / "作者 空间"
        self.workspace.mkdir()
        (self.workspace / "作者备注.md").write_text("这是手写资料，测试不能改动。", encoding="utf-8")

    def copy(self, dest):
        shutil.copytree(ROOT / "skills", dest,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        return dest

    def assert_pipeline(self, installed):
        before = snapshot(installed)
        raw_note = (self.workspace / "作者备注.md").read_bytes()
        run(ROOT / "scripts/check_package.py", "--skills-root", installed, cwd=self.workspace)
        setup = installed / "novel/scripts/setup.py"
        run(setup, self.workspace, cwd=self.base)
        source = self.workspace / "对标库/原创测试/原文.txt"
        source.parent.mkdir(parents=True)
        source.write_text(SOURCE, encoding="utf-8")
        chapters = source.parent / "生成章节"
        scripts = installed / "novel-chaishu/scripts"
        plan = json.loads(run(scripts / "split.py", source, chapters, cwd=self.workspace))
        self.assertEqual(plan["章数"], 4)
        raw = run(scripts / "metrics.py", source, cwd=self.workspace)
        self.assertEqual(raw, run(scripts / "metrics.py", chapters, cwd=self.workspace))
        metrics = source.parent / "指标.json"
        metrics.write_bytes(raw)
        annotation = source.parent / "语义标注.json"
        annotation.write_text(json.dumps([
            {"序号": i, "情绪点": ["悬念"] if i == 1 else [],
             "钩子": "悬念" if i < 4 else "平收", "大高潮": i == 4,
             "新角色": ["主角:小岚"] if i == 1 else [], "高光": ["主角"]}
            for i in range(1, 5)
        ], ensure_ascii=False), encoding="utf-8")
        semantic = json.loads(run(scripts / "semantics.py", annotation, "--metrics", metrics,
                                  cwd=self.workspace))
        self.assertEqual(semantic["范围"]["章数"], 4)
        self.assertEqual(semantic["大高潮"]["计数"], 1)
        guidelines = self.workspace / "规范/套话候选.txt"
        guidelines.write_text("# 作者自定义词表\n自定义表达\n", encoding="utf-8")
        run(setup, cwd=self.workspace)
        self.assertEqual(guidelines.read_text(encoding="utf-8"), "# 作者自定义词表\n自定义表达\n")
        self.assertEqual(snapshot(installed), before)
        self.assertEqual((self.workspace / "作者备注.md").read_bytes(), raw_note)

    def test_项目级Claude复制安装(self):
        self.assert_pipeline(self.copy(self.base / "安装项目/.claude/skills"))

    def test_agents复制安装(self):
        self.assert_pipeline(self.copy(self.base / "安装项目/.agents/skills"))

    def test_用户级技能与工作区完全分离(self):
        self.assert_pipeline(self.copy(self.base / "模拟用户/.claude/skills"))

    def test_自定义安装目录含中文空格(self):
        self.assert_pipeline(self.copy(self.base / "自定义 工具库/七件套"))

    def test_每个技能通过符号链接安装(self):
        canonical = self.copy(self.base / "真实安装源")
        linked = self.base / "链接安装/.claude/skills"
        linked.mkdir(parents=True)
        try:
            for name in SKILLS:
                (linked / name).symlink_to(canonical / name, target_is_directory=True)
        except OSError:
            if os.name == "nt":
                self.skipTest("当前 Windows 用户没有符号链接权限；复制安装另有强制测试")
            raise
        original = snapshot(canonical)
        self.assert_pipeline(linked)
        self.assertEqual(snapshot(canonical), original)


if __name__ == "__main__":
    unittest.main()
