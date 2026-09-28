"""网文语义指标脚本：把一份逐章语义标注 + 机械指标 JSON 变成确定性的语义指标 JSON。

用法：python semantics.py <语义标注.json> --metrics <指标.json> [--range A-B] [-o 输出.json]

只用标准库。同一输入永远得到逐字节相同的输出。判断（逐章标注）由 Claude 产出，
本脚本只做算术：情绪点、大高潮、钩子、新角色、主角高光的密度/间隔/覆盖率/占比。
字数取自 指标.json 的 章节[].字数，按 --range 或标注里的序号切齐。
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

from metrics import nearest_rank, ratio

HIGHLIGHT_ROLES = ("男主", "女主", "主角")


def decode(data):
    return data.decode("utf-8-sig")


def per_myriad(count, chars):
    return round(count * 10000 / chars, 2) if chars else 0.0


def mean(total, n):
    return round(total / n, 2) if n else 0.0


def interval(nums):
    """相邻序号差的（中位数, 最大值）；不足两个样本时都是 None。中位用最近秩法（与 metrics.py 共用）。"""
    marks = sorted(nums)
    diffs = sorted(b - a for a, b in zip(marks, marks[1:]))
    if not diffs:
        return None, None
    return nearest_rank(diffs, 0.5), max(diffs)


def longest_empty_run(annot):
    """连续没有情绪点的最多章数。"""
    best = current = 0
    for c in annot:
        current = current + 1 if not c["情绪点"] else 0
        best = max(best, current)
    return best


def by_frequency(counter):
    """按次数降序、同次数按名字升序，排成一个有序 dict。"""
    return {k: v for k, v in sorted(counter.items(), key=lambda kv: (-kv[1], kv[0]))}


def build(annot, charmap, rng):
    n = len(annot)
    chars = sum(charmap[c["序号"]] for c in annot)

    emotions = [e for c in annot for e in c["情绪点"]]
    total_emo = len(emotions)
    emo_counts = Counter(emotions)

    climax = [c["序号"] for c in annot if c["大高潮"]]
    cm_med, cm_max = interval(climax)

    hooks = Counter(c["钩子"] for c in annot)
    non_flat = sum(v for k, v in hooks.items() if k != "平收")

    new_roles = sum(len(c["新角色"]) for c in annot)

    lit = [c["序号"] for c in annot if c["高光"]]
    hl_med, hl_max = interval(lit)
    split = {}
    for role in HIGHLIGHT_ROLES:
        chapters = [c["序号"] for c in annot if role in c["高光"]]
        r_med, r_max = interval(chapters)
        split[role] = {"章数": len(chapters), "覆盖率": ratio(len(chapters), n),
                       "间隔中位": r_med, "间隔最大": r_max}

    return {
        "范围": {"起": rng[0] if rng else None, "止": rng[1] if rng else None,
                 "章数": n, "字数": chars},
        "情绪点": {
            "总数": total_emo,
            "密度每万字": per_myriad(total_emo, chars),
            "每章均": mean(total_emo, n),
            "间隔字数": round(chars / total_emo, 2) if total_emo else None,
            "最长空窗章数": longest_empty_run(annot),
            "类型占比": {k: ratio(v, total_emo) for k, v in by_frequency(emo_counts).items()},
        },
        "大高潮": {"计数": len(climax), "章号": climax,
                   "首个章号": climax[0] if climax else None,
                   "间隔中位": cm_med, "间隔最大": cm_max},
        "钩子": {"覆盖率": ratio(non_flat, n), "类型分布": by_frequency(hooks)},
        "新角色": {"计数": new_roles, "每10章": round(new_roles * 10 / n, 2) if n else 0.0},
        "主角高光": {"覆盖率": ratio(len(lit), n), "间隔中位": hl_med, "间隔最大": hl_max,
                     "分列": split},
    }


def parse_range(text):
    lo, _, hi = text.partition("-")
    lo, hi = int(lo), int(hi)
    if lo > hi:
        raise ValueError
    return lo, hi


def main(argv=None):
    parser = argparse.ArgumentParser(description="网文语义指标脚本")
    parser.add_argument("annotations", type=Path, help="语义标注 JSON：逐章 {序号,情绪点,钩子,大高潮,新角色,高光}")
    parser.add_argument("--metrics", type=Path, required=True, help="指标 JSON（metrics.py 的输出），取每章字数")
    parser.add_argument("--range", dest="span", help="只算这段章号，写成 起-止（含两端）")
    parser.add_argument("-o", "--output", type=Path, help="写到这个文件（UTF-8），不给就写到标准输出")
    args = parser.parse_args(argv)
    for path in (args.annotations, args.metrics):
        if not path.exists():
            parser.error(f"找不到输入：{path}")
    rng = None
    if args.span:
        try:
            rng = parse_range(args.span)
        except ValueError:
            parser.error(f"--range 要写成 起-止 且起不大于止：{args.span}")

    annot = sorted(json.loads(decode(args.annotations.read_bytes())), key=lambda c: c["序号"])
    metrics = json.loads(decode(args.metrics.read_bytes()))
    charmap = {c["序号"]: c["字数"] for c in metrics["章节"]}
    if rng:
        annot = [c for c in annot if rng[0] <= c["序号"] <= rng[1]]
    missing = [c["序号"] for c in annot if c["序号"] not in charmap]
    if missing:
        parser.error(f"指标 JSON 缺这些章的字数：{missing}")

    data = json.dumps(build(annot, charmap, rng), ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    if args.output:
        args.output.write_bytes(data)
    else:
        sys.stdout.buffer.write(data)


if __name__ == "__main__":
    main()
