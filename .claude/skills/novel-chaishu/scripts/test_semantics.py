"""语义指标脚本的命令行测试。只测外部行为：给定语义标注和指标 JSON，检查输出的语义指标 JSON。

运行：python -m unittest discover -s .claude/skills/novel-chaishu/scripts -v
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).with_name("semantics.py")
WORKSPACE = Path(__file__).resolve().parents[4]
NANHONG_ANN = WORKSPACE / "对标库" / "难哄" / "语义标注.json"
NANHONG_METRICS = WORKSPACE / "对标库" / "难哄" / "指标.json"


def ann(no, 情绪点=None, 钩子="平收", 大高潮=False, 新角色=None, 高光=None):
    return {"序号": no, "情绪点": list(情绪点 or []), "钩子": 钩子,
            "大高潮": 大高潮, "新角色": list(新角色 or []), "高光": list(高光 or [])}


def metrics_for(annot, 每章字数):
    """给每一章配一个统一字数，凑出一份最小的 指标.json。"""
    章节 = [{"序号": c["序号"], "字数": 每章字数} for c in annot]
    return {"全书": {"章数": len(annot), "字数": 每章字数 * len(annot)}, "章节": 章节}


def run_raw(annot_path, metrics_path, *args):
    proc = subprocess.run(
        [sys.executable, str(SCRIPT), str(annot_path), "--metrics", str(metrics_path), *args],
        capture_output=True, check=True,
    )
    return proc.stdout


def run_on(annot, metrics, *args, raw=False):
    """把 语义标注 与 指标 两份 JSON 写进临时目录再跑脚本。"""
    with tempfile.TemporaryDirectory() as tmp:
        a = Path(tmp, "语义标注.json")
        a.write_bytes(json.dumps(annot, ensure_ascii=False).encode("utf-8"))
        m = Path(tmp, "指标.json")
        m.write_bytes(json.dumps(metrics, ensure_ascii=False).encode("utf-8"))
        out = run_raw(a, m, *args)
    return out if raw else json.loads(out.decode("utf-8"))


def run_uniform(annot, 每章字数=1000, *args, raw=False):
    return run_on(annot, metrics_for(annot, 每章字数), *args, raw=raw)


# 主链路夹具：6 章，每章 1000 字，覆盖六大块的正常路径（含可算出的间隔）。
FIXTURE = [
    ann(1, ["笑点", "心动"], "悬念", False, ["女主:甲", "男主:乙"], ["男主"]),
    ann(2, ["笑点"], "平收", True, [], ["女主"]),
    ann(3, [], "反转", False, ["闺蜜:丙"], []),
    ann(4, [], "平收", False, [], ["男主", "女主"]),
    ann(5, ["笑点", "虐", "笑点"], "危机", True, [], ["男主"]),
    ann(6, ["甜"], "情感悬停", False, ["反派:丁"], ["主角"]),
]


class 主链路(unittest.TestCase):
    # 手算 FIXTURE（每章 1000 字，共 6000 字）：
    # 情绪点 2+1+0+0+3+1=7；笑点4 心动1 虐1 甜1；空情绪点 ch3,ch4 连续=2
    # 大高潮 ch2,ch5；钩子 非平收 ch1,3,5,6=4；新角色 2+1+1=4
    # 高光章 ch1,2,4,5,6=5；男主 ch1,4,5；女主 ch2,4；主角 ch6
    @classmethod
    def setUpClass(cls):
        cls.out = run_uniform(FIXTURE, 1000)

    def test_范围与情绪点(self):
        self.assertEqual(self.out["范围"], {"起": None, "止": None, "章数": 6, "字数": 6000})
        self.assertEqual(self.out["情绪点"], {
            "总数": 7, "密度每万字": 11.67, "每章均": 1.17, "间隔字数": 857.14,
            "最长空窗章数": 2,
            "类型占比": {"笑点": 0.5714, "心动": 0.1429, "甜": 0.1429, "虐": 0.1429},
        })
        self.assertEqual(list(self.out["情绪点"]["类型占比"]), ["笑点", "心动", "甜", "虐"])

    def test_大高潮(self):
        self.assertEqual(self.out["大高潮"], {
            "计数": 2, "章号": [2, 5], "首个章号": 2, "间隔中位": 3, "间隔最大": 3})

    def test_钩子(self):
        self.assertEqual(self.out["钩子"], {
            "覆盖率": 0.6667,
            "类型分布": {"平收": 2, "反转": 1, "危机": 1, "悬念": 1, "情感悬停": 1}})
        self.assertEqual(list(self.out["钩子"]["类型分布"]), ["平收", "危机", "反转", "悬念", "情感悬停"])

    def test_新角色(self):
        self.assertEqual(self.out["新角色"], {"计数": 4, "每10章": 6.67})

    def test_主角高光(self):
        self.assertEqual(self.out["主角高光"], {
            "覆盖率": 0.8333, "间隔中位": 1, "间隔最大": 2,
            "分列": {
                "男主": {"章数": 3, "覆盖率": 0.5, "间隔中位": 1, "间隔最大": 3},
                "女主": {"章数": 2, "覆盖率": 0.3333, "间隔中位": 2, "间隔最大": 2},
                "主角": {"章数": 1, "覆盖率": 0.1667, "间隔中位": None, "间隔最大": None},
            }})


SOLO = [ann(1, ["笑点"], "悬念", True, ["女主:甲"], ["男主"])]
EMPTY = [ann(1), ann(2), ann(3)]  # 三章全空：默认 平收 / 无情绪点 / 无大高潮 / 无高光


class 边界(unittest.TestCase):
    def test_单章_一切间隔为null(self):
        out = run_uniform(SOLO, 1000)
        self.assertEqual(out["情绪点"], {
            "总数": 1, "密度每万字": 10.0, "每章均": 1.0, "间隔字数": 1000.0,
            "最长空窗章数": 0, "类型占比": {"笑点": 1.0}})
        self.assertEqual(out["大高潮"], {
            "计数": 1, "章号": [1], "首个章号": 1, "间隔中位": None, "间隔最大": None})
        self.assertEqual(out["主角高光"], {
            "覆盖率": 1.0, "间隔中位": None, "间隔最大": None,
            "分列": {"男主": {"章数": 1, "覆盖率": 1.0, "间隔中位": None, "间隔最大": None},
                     "女主": {"章数": 0, "覆盖率": 0.0, "间隔中位": None, "间隔最大": None},
                     "主角": {"章数": 0, "覆盖率": 0.0, "间隔中位": None, "间隔最大": None}}})

    def test_全空_密度与覆盖率为0_间隔为null_最长空窗等于章数(self):
        out = run_uniform(EMPTY, 1000)
        self.assertEqual(out["范围"], {"起": None, "止": None, "章数": 3, "字数": 3000})
        self.assertEqual(out["情绪点"], {
            "总数": 0, "密度每万字": 0.0, "每章均": 0.0, "间隔字数": None,
            "最长空窗章数": 3, "类型占比": {}})
        self.assertEqual(out["大高潮"], {
            "计数": 0, "章号": [], "首个章号": None, "间隔中位": None, "间隔最大": None})
        self.assertEqual(out["钩子"], {"覆盖率": 0.0, "类型分布": {"平收": 3}})
        self.assertEqual(out["新角色"], {"计数": 0, "每10章": 0.0})
        self.assertEqual(out["主角高光"]["覆盖率"], 0.0)
        self.assertEqual(out["主角高光"]["分列"]["男主"],
                         {"章数": 0, "覆盖率": 0.0, "间隔中位": None, "间隔最大": None})


class 范围切片(unittest.TestCase):
    def test_range_只算指定章_字数按指定章从指标求和(self):
        # 指标里每章字数 = 序号 * 1000；--range 3-5 只算 ch3,4,5，字数 3000+4000+5000=12000
        metrics = {"全书": {"章数": 6, "字数": 21000},
                   "章节": [{"序号": c["序号"], "字数": c["序号"] * 1000} for c in FIXTURE]}
        out = run_on(FIXTURE, metrics, "--range", "3-5")
        self.assertEqual(out["范围"], {"起": 3, "止": 5, "章数": 3, "字数": 12000})
        self.assertEqual(out["情绪点"]["总数"], 3)
        self.assertEqual(out["情绪点"]["最长空窗章数"], 2)
        self.assertEqual(out["情绪点"]["类型占比"], {"笑点": 0.6667, "虐": 0.3333})
        self.assertEqual(out["大高潮"], {
            "计数": 1, "章号": [5], "首个章号": 5, "间隔中位": None, "间隔最大": None})
        self.assertEqual(out["新角色"], {"计数": 1, "每10章": 3.33})
        self.assertEqual(out["主角高光"]["分列"]["男主"],
                         {"章数": 2, "覆盖率": 0.6667, "间隔中位": 1, "间隔最大": 1})


class 确定性与输出(unittest.TestCase):
    def test_同一输入两次输出逐字节相同(self):
        self.assertEqual(run_uniform(FIXTURE, 1000, raw=True), run_uniform(FIXTURE, 1000, raw=True))

    def test_o参数写出的文件与标准输出逐字节相同(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = Path(tmp, "语义标注.json")
            a.write_bytes(json.dumps(FIXTURE, ensure_ascii=False).encode("utf-8"))
            m = Path(tmp, "指标.json")
            m.write_bytes(json.dumps(metrics_for(FIXTURE, 1000), ensure_ascii=False).encode("utf-8"))
            dest = Path(tmp, "语义指标.json")
            self.assertEqual(run_raw(a, m, "-o", str(dest)), b"")
            self.assertEqual(dest.read_bytes(), run_raw(a, m))


@unittest.skipUnless(NANHONG_ANN.exists() and NANHONG_METRICS.exists(),
                     "缺少夹具 对标库/难哄/{语义标注,指标}.json")
class 难哄语义(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.raw = run_raw(NANHONG_ANN, NANHONG_METRICS)
        cls.out = json.loads(cls.raw.decode("utf-8"))

    def test_覆盖全书89章(self):
        self.assertEqual(self.out["范围"]["章数"], 89)

    def test_大高潮首个在第10章_计数与章号自洽(self):
        climax = self.out["大高潮"]
        self.assertEqual(climax["首个章号"], 10)
        self.assertEqual(climax["计数"], len(climax["章号"]))
        self.assertEqual(climax["章号"], sorted(climax["章号"]))
        self.assertTrue(all(1 <= x <= 89 for x in climax["章号"]))

    def test_占比都在0到1之间_情绪点类型占比合计约1(self):
        self.assertAlmostEqual(sum(self.out["情绪点"]["类型占比"].values()), 1.0, delta=0.01)
        self.assertTrue(0 <= self.out["钩子"]["覆盖率"] <= 1)
        self.assertTrue(0 <= self.out["主角高光"]["覆盖率"] <= 1)

    def test_同一输入两次输出逐字节相同(self):
        self.assertEqual(run_raw(NANHONG_ANN, NANHONG_METRICS), self.raw)


if __name__ == "__main__":
    unittest.main()


