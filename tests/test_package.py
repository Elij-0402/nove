"""发布检查器的正反例；只操作临时技能副本。"""
import importlib.util
import shutil
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_package", ROOT / "scripts" / "check_package.py")
checker = importlib.util.module_from_spec(spec)
spec.loader.exec_module(checker)


class 发布检查(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.skills = Path(self.temp.name) / "安装包"
        shutil.copytree(ROOT / "skills", self.skills,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))

    def errors(self):
        return checker.check_package(self.skills)

    def test_完整包通过(self):
        self.assertEqual(self.errors(), [])

    def test_缺少技能失败(self):
        shutil.rmtree(self.skills / "novel-shengao")
        self.assertTrue(any("技能集合不符" in e for e in self.errors()))

    def test_多余技能失败(self):
        (self.skills / "unrelated").mkdir()
        self.assertTrue(any("多出" in e for e in self.errors()))

    def test_缺少脚本失败(self):
        (self.skills / "novel-chaishu/scripts/metrics.py").unlink()
        self.assertTrue(any("metrics.py" in e for e in self.errors()))

    def test_缺少资产失败(self):
        (self.skills / "novel/assets/规范/套话候选.txt").unlink()
        self.assertTrue(any("套话候选.txt" in e for e in self.errors()))

    def test_错误技能名失败(self):
        path = self.skills / "novel/SKILL.md"
        path.write_text(path.read_text(encoding="utf-8").replace("name: novel", "name: other", 1),
                        encoding="utf-8")
        self.assertTrue(any("name/description" in e for e in self.errors()))

    def test_缺少描述失败(self):
        path = self.skills / "novel/SKILL.md"
        lines = path.read_text(encoding="utf-8").splitlines()
        path.write_text("\n".join(line for line in lines if not line.startswith("description:")),
                        encoding="utf-8")
        self.assertTrue(any("name/description" in e for e in self.errors()))

    def test_静态断链失败(self):
        path = self.skills / "novel/BROKEN.md"
        path.write_text("[缺失文件](missing.md)\n", encoding="utf-8")
        self.assertTrue(any("断链" in e for e in self.errors()))

    def test_外部地址和工作区占位符不当断链(self):
        path = self.skills / "novel/EXAMPLE.md"
        path.write_text("[外部](https://example.com/a.md)\n[产物](作品/<书名>/项目.md)\n[本节](#说明)\n",
                        encoding="utf-8")
        self.assertEqual(self.errors(), [])

    def test_入口缺少初始化指针失败(self):
        path = self.skills / "novel/SKILL.md"
        path.write_text(path.read_text(encoding="utf-8").replace("SETUP.md", "PROJECT.md"),
                        encoding="utf-8")
        self.assertTrue(any("初始化指针" in e for e in self.errors()))

    def test_工作区相对脚本路径失败(self):
        path = self.skills / "novel/EXAMPLE.md"
        path.write_text("python ../novel-chaishu/scripts/metrics.py input.txt\n", encoding="utf-8")
        self.assertTrue(any("工作目录" in e for e in self.errors()))

    def test_私有目录混入失败(self):
        (self.skills / "novel" / "作品").mkdir()
        self.assertTrue(any("本地目录" in e for e in self.errors()))

    def test_用户专属路径失败(self):
        (self.skills / "novel/EXAMPLE.md").write_text("C:/Users/example/private\n", encoding="utf-8")
        self.assertTrue(any("本机用户路径" in e for e in self.errors()))

    def test_发布根文档完整(self):
        self.assertEqual(checker.check_package(ROOT / "skills", ROOT), [])


if __name__ == "__main__":
    unittest.main()
