"""指标脚本的命令行测试。只测外部行为：给定输入文件，检查输出的 JSON。

运行：python -m unittest discover -s .claude/skills/novel-chaishu/scripts -v
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("metrics.py")
WORKSPACE = Path(__file__).resolve().parents[4]
NANHONG = WORKSPACE / "对标库" / "难哄" / "原文.txt"


def run_raw(path, *args):
    """跑一次脚本，返回 stdout 原始字节。"""
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(path), *args],
        capture_output=True,
        check=True,
    )
    return proc.stdout


def run_on(files, target, raw=False):
    """在临时目录里写入 {相对路径: 内容}（UTF-8），对 target 跑脚本；target 为空串表示目录本身。"""
    with tempfile.TemporaryDirectory() as tmp:
        for name, body in files.items():
            path = Path(tmp, name)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(body, encoding="utf-8")
        stdout = run_raw(Path(tmp, target))
    return stdout if raw else json.loads(stdout.decode("utf-8"))


def run_text(text, raw=False):
    return run_on({"in.txt": text}, "in.txt", raw)


@unittest.skipUnless(NANHONG.exists(), "缺少夹具 对标库/难哄/原文.txt")
class 难哄原文(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = run_raw(NANHONG)
        cls.out = json.loads(cls.raw.decode("utf-8"))

    def test_切出89章且标题保留(self):
        chapters = self.out["章节"]
        self.assertEqual(len(chapters), 89)
        self.assertEqual(self.out["全书"]["章数"], 89)
        self.assertEqual([c["序号"] for c in chapters], list(range(1, 90)))
        self.assertEqual(chapters[0]["标题"], "第1章")
        self.assertEqual(chapters[84]["标题"], "第85章")
        self.assertEqual(chapters[85]["标题"], "第86章 番外")
        self.assertEqual(chapters[86]["标题"], "第87章 哥哥")
        self.assertEqual(chapters[88]["标题"], "第89章 番外")

    def test_抽查3章字数和对白占比与人工计数一致(self):
        # 参考值用独立方法得出：PowerShell 按行号截取章节，去掉场景分隔线“-”，
        # 数非空白字符；正则 “([^”]*)” 取每行引号内文字再数。
        expected = {1: (3615, 0.1862), 45: (5184, 0.2921), 89: (5601, 0.0816)}
        for no, (chars, dialogue) in expected.items():
            chapter = self.out["章节"][no - 1]
            with self.subTest(章=no):
                self.assertLessEqual(abs(chapter["字数"] - chars), chars * 0.01)
                self.assertLessEqual(abs(chapter["对白占比"] - dialogue), 0.03)

    def test_输出不含下载站声明和分隔线(self):
        text = self.raw.decode("utf-8")
        for noise in ("声明", "txt02", "八零电子书", "用户上传", "版权", "----", "===="):
            self.assertNotIn(noise, text)

    def test_三种编码输出完全一致(self):
        text = NANHONG.read_bytes().decode("utf-8-sig")
        with tempfile.TemporaryDirectory() as tmp:
            for enc in ("utf-8", "utf-8-sig", "gb18030"):
                path = Path(tmp, f"{enc}.txt")
                path.write_bytes(text.encode(enc))
                with self.subTest(编码=enc):
                    self.assertEqual(run_raw(path), self.raw)

    def test_同一输入两次输出逐字节相同(self):
        self.assertEqual(run_raw(NANHONG), self.raw)


CLEAN = """第1章 初见
　　她推开门，屋里没人。
　　“有人吗？”她问。
　　-
　　没人回答。
第2章 再见
　　第二天，他来了。
　　“早。”
"""

NOISY = """声明：本书为八零电子书(txt02.com)的用户自网络收集整理制作,仅供预览交流学习使用,版权归原作者和出版社所有。
---------------------------用户上传之内容开始--------------------------------
===========
第1章 初见
　　她推开门，屋里没人。
　　天才一秒记住本站地址：www.example.com 最快更新！
　　“有人吗？”她问。
　　-
**********
※※※
　　没人回答。
第2章 再见
　　第二天，他来了。
　　更多精彩，请登录 http://example.net
　　“早。”
（本章完）
---------------------------用户上传之内容结束--------------------------------
声明：本书为八零电子书(txt02.com)的用户自网络收集整理制作,以上作品内容之版权与本站无任何关系。
"""


class 杂质剥离(unittest.TestCase):
    def test_声明广告和分隔线不影响统计(self):
        self.assertEqual(run_text(NOISY, raw=True), run_text(CLEAN, raw=True))

    def test_字母拆散的域名水印也剥掉(self):
        # 《难哄》正文里夹着的真实水印：字母之间插空格、下划线，混用全角和希腊字母
        watermarks = [
            "宝 书 网  w  w w . b  a   o  s h    u  6  .   c  o  m",
            "八_零_电_子_书 _w_w  _w_ .t _x_t_ 0 _2. _ c_o_m",
            "⑧  ○  電   孑  書    w   Ｗ Ｗ . Ｔ  Ｘ   t   ○   2. c o m",
            "㈧_ ○_電_芓 _書_Ｗ_  w_ ω_.Τ_ Χ  _t_零  _  2 .c_o _m",
            "防止失联,请记住本 站备 用域名： t   x    t  0  2 . c  o m",
        ]
        noisy = CLEAN.replace("没人回答。\n", "没人回答。\n" + "\n".join(watermarks) + "\n")
        self.assertEqual(run_text(noisy, raw=True), run_text(CLEAN, raw=True))

    def test_晋江作者有话要说不算正文(self):
        out = run_text(
            "第1章 初见\n　　她推开门。\n作者有话要说：\n　　感谢投雷的小天使们！\n　　明天加更。\n"
            "第2章 再见\n　　他来了。\n"
        )
        self.assertEqual([c["字数"] for c in out["章节"]], [5, 4])

    def test_正文里提到下载站用语的句子不删(self):
        out = run_text("第1章\n　　她刷新了最新章节，还是没更。\n")
        self.assertEqual(out["全书"]["字数"], 14)


class 句长段长和全书汇总(unittest.TestCase):
    # 手算 CLEAN：长度一律按非空白字符数（含标点）。
    # 第1章 段落 [10, 9, 5]，句子 她推开门，屋里没人。/“有人吗？”/她问。/没人回答。 = [10, 6, 3, 5]
    # 第2章 段落 [8, 4]，句子 第二天，他来了。/“早。” = [8, 4]
    # 引号内：有人吗？(4)、早。(2)
    @classmethod
    def setUpClass(cls):
        cls.out = run_text(CLEAN)

    def test_每章字数对白和句长(self):
        first = self.out["章节"][0]
        self.assertEqual(first["字数"], 24)
        self.assertEqual(first["对白占比"], 0.1667)
        self.assertEqual(
            first["句长统计"],
            {
                "数量": 4, "平均": 6.0, "最小": 3, "P25": 3, "中位数": 5, "P75": 6, "P90": 10, "最大": 10,
                "分布": {"1-5": 0.5, "6-10": 0.5, "11-20": 0.0, "21-30": 0.0, "31-50": 0.0, "51+": 0.0},
            },
        )
        self.assertEqual(first["段长统计"]["数量"], 3)
        self.assertEqual(first["段长统计"]["平均"], 8.0)
        self.assertEqual(first["段长统计"]["分布"]["1-10"], 1.0)

    def test_全书汇总(self):
        book = self.out["全书"]
        self.assertEqual(book["章数"], 2)
        self.assertEqual(book["字数"], 36)
        self.assertEqual(book["对白占比"], 0.1667)
        self.assertEqual(book["章字数统计"]["平均"], 18.0)
        self.assertEqual(book["章字数统计"]["最大"], 24)
        self.assertEqual(book["句长统计"]["数量"], 6)
        self.assertEqual(book["句长统计"]["中位数"], 5)
        self.assertEqual(book["句长统计"]["P75"], 8)
        self.assertEqual(book["段长统计"]["平均"], 7.2)
        self.assertEqual(book["段长统计"]["中位数"], 8)

    def test_直引号也算对白(self):
        # "你好。"(5) + 他说。(3) = 8 字，引号内 你好。 = 3 字
        out = run_text('第1章\n"你好。"他说。\n')
        self.assertEqual(out["章节"][0]["对白占比"], 0.375)


class 高频词(unittest.TestCase):
    def test_整词计数且去掉被吸收的片段和功能词(self):
        # 字数 8+13+12+11+6+21 = 71。“以凡”“温以”总跟着凑成“温以凡”，被吸收；
        # “有一个”含功能词“一个”，“有一”被“有一个”吸收；其余片段都只出现 1 次。
        text = (
            "第1章\n温以凡看着桑延。\n温以凡说：“桑延，你好。”\n桑延没说话，温以凡笑了。\n"
            "温以凡走了。桑延跟上。\n温以凡回头。\n她有一个想法，他有一个问题，我有一个办法。\n"
        )
        out = run_text(text)
        self.assertEqual(out["全书"]["字数"], 71)
        self.assertEqual(
            out["全书"]["高频词"],
            [
                {"词": "温以凡", "次数": 5, "每万字": 704.23},
                {"词": "桑延", "次数": 4, "每万字": 563.38},
            ],
        )


class 词表计数(unittest.TestCase):
    def test_按词表顺序统计全书出现次数(self):
        # 字数 9+10 = 19；“仿佛”出现 3 次（第二段 2 次），“微微”0 次；杂质行里的不算
        files = {
            "in.txt": "第1章\n她仿佛听见了什么。\n仿佛是风，仿佛不是。\nwww.example.com 仿佛\n",
            "词表.txt": "# 比喻\n仿佛\n\n微微\n",
        }
        with tempfile.TemporaryDirectory() as tmp:
            for name, body in files.items():
                Path(tmp, name).write_text(body, encoding="utf-8")
            out = json.loads(run_raw(Path(tmp, "in.txt"), "--phrases", str(Path(tmp, "词表.txt"))))
        self.assertEqual(out["全书"]["字数"], 19)
        self.assertEqual(
            out["全书"]["词表计数"],
            [
                {"词": "仿佛", "次数": 3, "每万字": 1578.95},
                {"词": "微微", "次数": 0, "每万字": 0.0},
            ],
        )

    def test_不给词表时没有这一项(self):
        self.assertNotIn("词表计数", run_text(CLEAN)["全书"])


class 章节标题格式(unittest.TestCase):
    def test_中文数字番外楔子和卷标题(self):
        text = (
            "第一卷 相遇\n楔子\n　　雨下了一夜。\n"
            "第一章 初见\n　　她推开门。\n　　第一章写完的时候，天已经亮了。\n"
            "第二章再见\n　　他来了。\n"
            "第二卷 重逢\n第一百零一章：旧人\n　　旧人归来。\n"
            "番外一 婚后\n　　日子很长。\n"
        )
        chapters = run_text(text)["章节"]
        self.assertEqual(
            [c["标题"] for c in chapters],
            ["楔子", "第一章 初见", "第二章再见", "第一百零一章：旧人", "番外一 婚后"],
        )
        self.assertEqual(
            [c["卷"] for c in chapters],
            ["第一卷 相遇", "第一卷 相遇", "第一卷 相遇", "第二卷 重逢", "第二卷 重逢"],
        )
        # 正文里以“第一章”开头的句子不是标题
        self.assertEqual(chapters[1]["字数"], 20)

    def test_下载站常见的标题前缀(self):
        text = (
            "正文 第一章 初来乍到\n　　他来了。\n"
            "【第二章】初见\n　　她笑了。\n"
            "第二卷 第三章 重逢\n　　又见面了。\n"
        )
        chapters = run_text(text)["章节"]
        self.assertEqual(
            [c["标题"] for c in chapters],
            ["正文 第一章 初来乍到", "【第二章】初见", "第二卷 第三章 重逢"],
        )
        self.assertEqual([c["卷"] for c in chapters], [None, None, "第二卷"])

    def test_关键字开头的正文短句不当标题(self):
        text = (
            "第1章 开始\n　　第三回合，他又输了！\n　　第一节课下课后，他去找她\n"
            "　　尾声渐渐消失在走廊尽头……\n"
        )
        self.assertEqual(len(run_text(text)["章节"]), 1)

    def test_没有章节标题时整篇算一章(self):
        out = run_text("她推开门。\n他来了。\n")
        self.assertEqual(len(out["章节"]), 1)
        self.assertEqual(out["章节"][0]["标题"], "全文")
        self.assertEqual(out["章节"][0]["字数"], 9)


class 输出到文件(unittest.TestCase):
    def test_o参数写出的文件与标准输出逐字节相同(self):
        with tempfile.TemporaryDirectory() as tmp:
            src = Path(tmp, "clean.txt")
            src.write_text(CLEAN, encoding="utf-8")
            dest = Path(tmp, "指标.json")
            self.assertEqual(run_raw(src, "-o", str(dest)), b"")
            self.assertEqual(dest.read_bytes(), run_raw(src))


class 章节目录输入(unittest.TestCase):
    def test_章节md目录与等价txt统计一致(self):
        chapters = {
            "0001-初见.md": "# 第1章 初见\n\n她推开门，屋里没人。\n\n“有人吗？”她问。\n\n---\n\n没人回答。\n",
            "0002-再见.md": "# 第2章 再见\n\n第二天，他来了。\n\n“早。”\n",
        }
        self.assertEqual(run_on(chapters, "", raw=True), run_text(CLEAN, raw=True))

    def test_没有标题行时用文件名做章名(self):
        out = run_on({"0001-初见.md": "她推开门。\n", "0002-再见.md": "他来了。\n"}, "")
        self.assertEqual([c["标题"] for c in out["章节"]], ["初见", "再见"])

    def test_单个章节md文件与只含它的目录一致(self):
        files = {"0001-初见.md": "# 第1章 初见\n\n她推开门。\n"}
        single = run_on(files, "0001-初见.md", raw=True)
        self.assertEqual(single, run_on(files, "", raw=True))
        self.assertEqual(json.loads(single)["章节"][0]["字数"], 5)


if __name__ == "__main__":
    unittest.main()
