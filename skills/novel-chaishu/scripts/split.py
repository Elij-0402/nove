"""切章脚本：把源本 txt 切成逐章的 md 文件，并给出拆书的精拆范围和子代理分块。

用法：python split.py <原文.txt> <章节目录> [-o 分块.json]
切章、去杂质的规则与 metrics.py 完全相同；对切出的目录跑 metrics.py，结果与原 txt 一致（卷字段除外）。
只用标准库。同一输入永远得到逐字节相同的输出。
"""
import argparse
import json
import re
import sys
from pathlib import Path

from metrics import char_count, decode, split_chapters

GOLDEN = 3  # 黄金三章，由主代理亲自逐章拆
FINE_MAX_CHARS = 150000  # 精拆范围：前 15 万字或前 50 章，取较少的一方
FINE_MAX_CHAPTERS = 50
FINE_CHUNK = 50000  # 每个子代理一块的字数上限
COARSE_CHUNK = 100000
BAD_FILENAME_RE = re.compile(r'[\s\\/:*?"<>|]+')


def filename(no, title):
    safe = BAD_FILENAME_RE.sub("-", title).strip("-.")[:40]
    return f"{no:04d}-{safe}.md"


def write_chapters(chapters, dest):
    """每章一个 md：首行 # 标题，之后每段一行。先清掉目录里旧的 md，免得重切后留下多余的章。"""
    dest.mkdir(parents=True, exist_ok=True)
    for old in dest.glob("*.md"):
        old.unlink()
    names = []
    for no, c in enumerate(chapters, 1):
        name = filename(no, c["标题"])
        body = "".join(f"{line}\n" for line in [f"# {c['标题']}", *c["段落"]])
        (dest / name).write_bytes(body.encode("utf-8"))
        names.append(name)
    return names


def fine_end(sizes):
    """精拆到累计不超过 15 万字、且不超过 50 章的最后一章；黄金三章无论多长都在内。"""
    end, total = 0, 0
    for no, size in enumerate(sizes[:FINE_MAX_CHAPTERS], 1):
        total += size
        if total > FINE_MAX_CHARS:
            break
        end = no
    return max(end, min(GOLDEN, len(sizes)))


def pack(units, limit):
    """按顺序把单元装箱，每箱不超过 limit；本身超过 limit 的单元独占一箱。单元是章序号列表加字数。"""
    boxes = []
    for nos, size in units:
        if boxes and boxes[-1][1] + size <= limit:
            boxes[-1] = (boxes[-1][0] + nos, boxes[-1][1] + size)
        else:
            boxes.append((nos, size))
    return boxes


def coarse_boxes(nos, chapters, sizes):
    """粗拆按卷装箱：连续属于同一卷的章节算一个单元，几个小卷可以装进同一箱；
    超过上限的卷单独按章装箱，不和别的卷混在一起。"""
    runs = []
    for no in nos:
        if runs and chapters[runs[-1][-1] - 1]["卷"] == chapters[no - 1]["卷"]:
            runs[-1].append(no)
        else:
            runs.append([no])
    boxes, whole_volumes = [], []
    for run in runs:
        size = sum(sizes[no - 1] for no in run)
        if size <= COARSE_CHUNK:
            whole_volumes.append((run, size))
        else:
            boxes += pack(whole_volumes, COARSE_CHUNK) + pack([([no], sizes[no - 1]) for no in run], COARSE_CHUNK)
            whole_volumes = []
    return boxes + pack(whole_volumes, COARSE_CHUNK)


def plan(chapters, names):
    sizes = [char_count("".join(c["段落"])) for c in chapters]
    end = fine_end(sizes)
    golden = min(GOLDEN, len(chapters))
    fine = [([no], sizes[no - 1]) for no in range(golden + 1, end + 1)]
    coarse = coarse_boxes(range(end + 1, len(chapters) + 1), chapters, sizes)
    boxes = [("精拆", box) for box in pack(fine, FINE_CHUNK)]
    boxes += [("粗拆", box) for box in coarse]
    blocks = []
    for i, (kind, (nos, size)) in enumerate(boxes, 1):
        volumes = []
        for no in nos:
            volume = chapters[no - 1]["卷"]
            if volume and volume not in volumes:
                volumes.append(volume)
        blocks.append({
            "块": i,
            "类型": kind,
            "起": nos[0],
            "止": nos[-1],
            "字数": size,
            "卷": volumes,
            "文件": [names[no - 1] for no in nos],
        })
    return {
        "章数": len(chapters),
        "字数": sum(sizes),
        "黄金三章": list(range(1, golden + 1)),
        "精拆": {"起": 1, "止": end, "字数": sum(sizes[:end])},
        "分块": blocks,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="切章脚本")
    parser.add_argument("source", type=Path, help="源本 txt")
    parser.add_argument("dest", type=Path, help="章节目录，里面原有的 md 会被清掉")
    parser.add_argument("-o", "--output", type=Path, help="分块 JSON 写到这个文件（UTF-8），不给就写到标准输出")
    args = parser.parse_args(argv)
    if not args.source.is_file():
        parser.error(f"找不到源本：{args.source}")
    chapters = split_chapters(decode(args.source.read_bytes()))
    result = plan(chapters, write_chapters(chapters, args.dest))
    data = json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    if args.output:
        args.output.write_bytes(data)
    else:
        sys.stdout.buffer.write(data)


if __name__ == "__main__":
    main()
