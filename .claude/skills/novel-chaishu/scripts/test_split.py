"""切章脚本的命令行测试。只测外部行为：给定源本，检查写出的章节文件和分块 JSON。

运行：python -m unittest discover -s .claude/skills/novel-chaishu/scripts -v
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SPLIT = Path(__file__).with_name("split.py")
METRICS = Path(__file__).with_name("metrics.py")
WORKSPACE = Path(__file__).resolve().parents[4]
NANHONG = WORKSPACE / "对标库" / "难哄" / "原文.txt"


def run(script, *args):
    proc = subprocess.run(
        [sys.executable, str(script), *map(str, args)],
        capture_output=True,
        check=True,
    )
    return proc.stdout


def split(source, dest):
    """切章，返回 (分块 JSON 原始字节, 解析后的分块)。"""
    raw = run(SPLIT, source, dest)
    return raw, json.loads(raw.decode("utf-8"))


def chapter(no, size, prefix=""):
    """一章：标题行加一段 size 个汉字。"""
    return f"{prefix}第{no}章\n{'字' * size}\n"


def split_text(text):
    """在临时目录里切一段文本，返回 (分块, 章节文件名列表)。"""
    with tempfile.TemporaryDirectory() as tmp:
        src = Path(tmp, "原文.txt")
        src.write_text(text, encoding="utf-8")
        dest = Path(tmp, "章节")
        _, plan = split(src, dest)
        return plan, sorted(p.name for p in dest.glob("*.md"))


def ranges(plan, kind=None):
    return [(b["起"], b["止"]) for b in plan["分块"] if kind is None or b["类型"] == kind]


@unittest.skipUnless(NANHONG.exists(), "缺少夹具 对标库/难哄/原文.txt")
class 难哄切章(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.dest = Path(cls.tmp.name, "章节")
        cls.raw, cls.plan = split(NANHONG, cls.dest)

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_每章一个文件且按编号排序(self):
        names = sorted(p.name for p in self.dest.glob("*.md"))
        self.assertEqual(len(names), 89)
        self.assertEqual(names[0], "0001-第1章.md")
        self.assertEqual(names[85], "0086-第86章-番外.md")
        self.assertEqual(names[88], "0089-第89章-番外.md")

    def test_章节目录的指标与原txt逐字节相同(self):
        self.assertEqual(run(METRICS, self.dest), run(METRICS, NANHONG))

    def test_精拆到累计不超过15万字的最后一章(self):
        # 第37章累计 148694 字，第38章累计 153529 字
        self.assertEqual(self.plan["精拆"], {"起": 1, "止": 37, "字数": 148694})
        self.assertEqual(self.plan["黄金三章"], [1, 2, 3])
        self.assertEqual(self.plan["章数"], 89)
        self.assertEqual(self.plan["字数"], 389127)

    def test_分块从第4章起首尾相接覆盖全书(self):
        spans = ranges(self.plan)
        self.assertEqual(spans[0][0], 4)
        self.assertEqual(spans[-1][1], 89)
        for (_, end), (start, _) in zip(spans, spans[1:]):
            self.assertEqual(start, end + 1)
        self.assertEqual(ranges(self.plan, "精拆")[-1][1], 37)
        self.assertEqual(ranges(self.plan, "粗拆")[0][0], 38)

    def test_分块字数不超过上限且文件名对得上(self):
        limits = {"精拆": 50000, "粗拆": 100000}
        for block in self.plan["分块"]:
            with self.subTest(块=block["块"]):
                self.assertLessEqual(block["字数"], limits[block["类型"]])
                self.assertEqual(len(block["文件"]), block["止"] - block["起"] + 1)
                self.assertTrue(block["文件"][0].startswith(f"{block['起']:04d}-"))
                for name in block["文件"]:
                    self.assertTrue((self.dest / name).exists())

    def test_同一输入两次输出逐字节相同(self):
        with tempfile.TemporaryDirectory() as tmp:
            raw, _ = split(NANHONG, Path(tmp, "章节"))
        self.assertEqual(raw, self.raw)


class 精拆范围(unittest.TestCase):
    def test_最多50章(self):
        plan, names = split_text("".join(chapter(i, 100) for i in range(1, 61)))
        self.assertEqual(plan["精拆"], {"起": 1, "止": 50, "字数": 5000})
        self.assertEqual(len(names), 60)

    def test_最多15万字(self):
        plan, _ = split_text("".join(chapter(i, 20000) for i in range(1, 11)))
        self.assertEqual(plan["精拆"]["止"], 7)
        self.assertEqual(ranges(plan, "精拆"), [(4, 5), (6, 7)])

    def test_第1章就超过15万字时仍精拆黄金三章(self):
        plan, _ = split_text(chapter(1, 160000) + chapter(2, 10) + chapter(3, 10) + chapter(4, 10))
        self.assertEqual(plan["精拆"]["止"], 3)
        self.assertEqual(ranges(plan, "粗拆"), [(4, 4)])

    def test_不满三章时全归主代理(self):
        plan, _ = split_text(chapter(1, 10) + chapter(2, 10))
        self.assertEqual(plan["黄金三章"], [1, 2])
        self.assertEqual(plan["精拆"]["止"], 2)
        self.assertEqual(plan["分块"], [])


class 粗拆按卷分块(unittest.TestCase):
    def test_整卷装块_超大的卷按章拆开(self):
        # 精拆吃掉第1–5章（15万字）；之后甲卷 6 万、乙卷 6 万装不进同一块，
        # 丙卷 15 万超过上限，按章拆成 9 万和 6 万。
        text = "".join(chapter(i, 30000) for i in range(1, 6))
        text += "第一卷 甲\n" + "".join(chapter(i, 20000) for i in range(6, 9))
        text += "第二卷 乙\n" + "".join(chapter(i, 20000) for i in range(9, 12))
        text += "第三卷 丙\n" + "".join(chapter(i, 30000) for i in range(12, 17))
        plan, _ = split_text(text)
        coarse = [b for b in plan["分块"] if b["类型"] == "粗拆"]
        self.assertEqual([(b["起"], b["止"]) for b in coarse], [(6, 8), (9, 11), (12, 14), (15, 16)])
        self.assertEqual([b["卷"] for b in coarse], [["第一卷 甲"], ["第二卷 乙"], ["第三卷 丙"], ["第三卷 丙"]])

    def test_小卷合进同一块(self):
        text = "".join(chapter(i, 30000) for i in range(1, 6))
        text += "第一卷 甲\n" + chapter(6, 10000) + "第二卷 乙\n" + chapter(7, 10000)
        plan, _ = split_text(text)
        coarse = [b for b in plan["分块"] if b["类型"] == "粗拆"]
        self.assertEqual([(b["起"], b["止"], b["卷"]) for b in coarse], [(6, 7, ["第一卷 甲", "第二卷 乙"])])


class 章节文件(unittest.TestCase):
    def test_文件名去掉非法字符_标题原样写在首行(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp, "原文.txt")
            src.write_text("第1章 你好?吗:是\n　　她来了。\n　　-\n　　他走了。\n", encoding="utf-8")
            dest = Path(tmp, "章节")
            split(src, dest)
            path = dest / "0001-第1章-你好-吗-是.md"
            self.assertEqual(path.read_text(encoding="utf-8"), "# 第1章 你好?吗:是\n她来了。\n他走了。\n")
            out = json.loads(run(METRICS, dest))
            self.assertEqual(out["章节"][0]["标题"], "第1章 你好?吗:是")

    def test_重跑时清掉旧的章节文件(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp, "原文.txt")
            dest = Path(tmp, "章节")
            src.write_text(chapter(1, 5) + chapter(2, 5) + chapter(3, 5), encoding="utf-8")
            split(src, dest)
            src.write_text(chapter(1, 5) + chapter(2, 5), encoding="utf-8")
            split(src, dest)
            self.assertEqual(sorted(p.name for p in dest.glob("*.md")), ["0001-第1章.md", "0002-第2章.md"])

    def test_o参数写出的文件与标准输出逐字节相同(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp, "原文.txt")
            src.write_text(chapter(1, 5), encoding="utf-8")
            out = Path(tmp, "分块.json")
            self.assertEqual(run(SPLIT, src, Path(tmp, "甲"), "-o", out), b"")
            self.assertEqual(out.read_bytes(), run(SPLIT, src, Path(tmp, "乙")))


if __name__ == "__main__":
    unittest.main()
