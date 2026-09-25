"""网文指标脚本：把一个 txt 或章节 md 目录变成一份确定性的 JSON 指标。

用法：python metrics.py <txt文件或章节目录> [-o 输出.json] [--phrases 词表.txt]
只用标准库。同一输入永远得到逐字节相同的输出。
"""
import argparse
import json
import math
import re
import sys
import unicodedata
from collections import Counter
from pathlib import Path

CN_NUM = "0-9０-９零〇一二三四五六七八九十百千万两"
# 标题里编号或关键字之后允许紧跟的字符
TITLE_SEP = r"\s:：、.·—\-】"
# 章标题：第N章/回/节（阿拉伯或中文数字）、番外、楔子等开头，后面可跟章名。
# 允许下载站常见的前缀：“正文 ”、同一行的卷号“第二卷 ”、方括号“【”。
# 回/节和关键字后面必须是分隔符、编号或行尾，免得把“第三回合”“尾声渐渐”当成标题。
CHAPTER_RE = re.compile(
    rf"^(?:正文\s*)?(?:(?P<卷>第[{CN_NUM}]+[卷部集])\s*)?【?"
    rf"(?:第[{CN_NUM}]+(?:章|[回节](?=[{TITLE_SEP}]|$))"
    rf"|(?:番外|楔子|序章|序言|引子|尾声|终章|后记)(?=[{TITLE_SEP}{CN_NUM}]|$))"
)
# 卷标题：第N卷/部/集，后面要么是分隔符要么行尾，免得把“第一部手机”当成卷
VOLUME_RE = re.compile(rf"^第[{CN_NUM}]+[卷部集](?:[{TITLE_SEP}]|$)")
# 标题行都短，且不以句读收尾；正文里以“第一章”开头的句子靠这条排除
MAX_TITLE_LEN = 30
# 晋江等站点章末的作者留言：从这一行到下一个标题都不算正文
AUTHOR_NOTE_PREFIX = "作者有话要说"
# 分隔线：整行只有横线、等号、星号之类的符号（含章内的场景分隔“-”）
SEPARATOR_RE = re.compile(r"^[-=_*~#+·•―—─━－＝＊～＿※☆★◇◆○●□■△▲]+$")
# 章末标记
CHAPTER_END_RE = re.compile(r"^[（(]?本章完[）)]?$")
# 下载站杂质：网址、域名，以及只在声明里出现的固定说法。
# “最新章节”“免费阅读”这类词正文里也会写到，不收；带它们的广告行通常也带网址。
SITE_NOISE_RE = re.compile(
    r"https?://|www\.|[A-Za-z0-9-]+\.(?:com|net|org|cc|cn|la|info|me|io|co|xyz|top)\b"
    r"|用户上传之内容|仅供预览|交流学习使用|版权归原作者|请支持正版|与本站无任何关系"
    r"|整理制作|[Tt][Xx][Tt]下载|电子书下载"
)
# 正文里夹的水印会把域名拆散：字母间插空格、下划线，混用全角字母。
# 挤掉空白和下划线、做 NFKC 归一后再按上面的规则查一遍。
SQUEEZE_RE = re.compile(r"[\s_]+")
OPEN_QUOTES = "“「『"
CLOSE_QUOTES = "”」』"
# 句子：一段非句末字符 + 句末标点 + 紧跟的收引号
SENTENCE_RE = re.compile(r"[^。！？!?…]+[。！？!?…]*[”’」』\"]*")
SENTENCE_BUCKETS = [(1, 5), (6, 10), (11, 20), (21, 30), (31, 50), (51, None)]
PARAGRAPH_BUCKETS = [(1, 10), (11, 30), (31, 60), (61, 100), (101, 200), (201, None)]
# 高频词：没有分词器，统计汉字 2–4 元组；下面这些是没有文风信息量的虚词
HAN_RUN_RE = re.compile(r"[㐀-䶿一-鿿]+")
STOP_WORDS = (
    "一个 没有 什么 自己 他们 她们 我们 你们 这个 那个 这样 那样 不是 就是 还是 已经 可以"
    " 因为 所以 但是 然后 如果 虽然 这么 那么 怎么 时候 这些 那些 一下 一样"
).split()
BAD_START = set("的了着吗呢吧啊呀嘛也")
BAD_END = set("的地和与在把被给他她我你它这那不也没")
TOP_WORDS = 100


def decode(data):
    for enc in ("utf-8-sig", "gb18030"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            pass
    raise SystemExit("无法识别编码：只支持 UTF-8、UTF-8 BOM、GBK/GB18030")


def is_site_noise(line):
    squeezed = unicodedata.normalize("NFKC", SQUEEZE_RE.sub("", line))
    return bool(SITE_NOISE_RE.search(line) or SITE_NOISE_RE.search(squeezed))


def clean_lines(text):
    """去掉空行、分隔线和下载站杂质，返回剩下的行（已去首尾空白）。"""
    for line in text.splitlines():
        line = line.strip()
        if (
            line
            and not SEPARATOR_RE.match(line)
            and not CHAPTER_END_RE.match(line)
            and not is_site_noise(line)
        ):
            yield line


def parse_heading(line):
    """章标题返回 ("章", 同一行里的卷号或 None)，卷标题返回 ("卷", 整行)，正文返回 None。"""
    if len(line) > MAX_TITLE_LEN or "。" in line or line[-1] in "，、；":
        return None
    m = CHAPTER_RE.match(line)
    if m:
        return "章", m.group("卷")
    if VOLUME_RE.match(line):
        return "卷", line
    return None


def split_chapters(text):
    """按标题切章。第一个章标题之前的文字（书名、简介等）丢弃；一个标题都没有时整篇算一章。"""
    lines = list(clean_lines(text))
    chapters = []
    volume = None
    in_author_note = False
    for line in lines:
        heading = parse_heading(line)
        if heading:
            kind, heading_volume = heading
            volume = heading_volume or volume
            in_author_note = False
            if kind == "章":
                chapters.append({"标题": line, "卷": volume, "段落": []})
        elif line.startswith(AUTHOR_NOTE_PREFIX):
            in_author_note = True
        elif chapters and not in_author_note:
            chapters[-1]["段落"].append(line)
    return chapters or [{"标题": "全文", "卷": None, "段落": lines}]


def read_md_chapter(path):
    """一个 md 文件算一章。章名取首行 # 标题，没有就取文件名去掉编号。"""
    lines = list(clean_lines(decode(path.read_bytes())))
    if lines and lines[0].startswith("#"):
        title = lines.pop(0).lstrip("#").strip()
    else:
        title = re.sub(r"^\d+[-_\s]*", "", path.stem)
    return {"标题": title, "卷": None, "段落": lines}


def read_source(source):
    """章节目录按文件名排序逐个读 md；单个 md 文件算一章；其余当 txt 按标题切章。"""
    if source.is_dir():
        return [read_md_chapter(path) for path in sorted(source.glob("*.md"))]
    if source.suffix.lower() == ".md":
        return [read_md_chapter(source)]
    return split_chapters(decode(source.read_bytes()))


def char_count(s):
    return len(re.sub(r"\s", "", s))


def dialogue_count(paragraph):
    """引号内的非空白字数，不含引号本身。直引号 " 成对开合。跨段未闭合的引号在段末截止。"""
    depth = 0
    in_straight = False
    count = 0
    for ch in paragraph:
        if ch in OPEN_QUOTES:
            depth += 1
        elif ch in CLOSE_QUOTES:
            depth = max(depth - 1, 0)
        elif ch == '"':
            in_straight = not in_straight
        elif (depth or in_straight) and not ch.isspace():
            count += 1
    return count


def ratio(part, whole):
    return round(part / whole, 4) if whole else 0.0


def sentences(paragraph):
    """按句末标点切句，句末标点后紧跟的收引号归前句；只有标点的碎片不算句子。"""
    for m in SENTENCE_RE.finditer(paragraph):
        if any(ch.isalnum() for ch in m.group()):
            yield m.group()


def length_stats(lengths, buckets=None):
    """数量、平均、分位数（最近秩法，结果都是原始长度值）和可选的分桶占比。"""
    values = sorted(lengths)
    n = len(values)

    def rank(p):
        return values[max(math.ceil(p * n) - 1, 0)] if n else 0

    stats = {
        "数量": n,
        "平均": round(sum(values) / n, 2) if n else 0.0,
        "最小": values[0] if n else 0,
        "P25": rank(0.25),
        "中位数": rank(0.5),
        "P75": rank(0.75),
        "P90": rank(0.9),
        "最大": values[-1] if n else 0,
    }
    if buckets:
        dist = {}
        for low, high in buckets:
            label = f"{low}+" if high is None else f"{low}-{high}"
            hits = sum(1 for v in values if v >= low and (high is None or v <= high))
            dist[label] = ratio(hits, n)
        stats["分布"] = dist
    return stats


def top_words(paragraphs, chars):
    """汉字 2–4 元组的高频表。一个片段若几乎总是出现在某个更长的片段里（≥80%），
    就被那个长片段吸收，比如“以凡”被“温以凡”吸收。"""
    counts = Counter()
    for p in paragraphs:
        for run in HAN_RUN_RE.findall(p):
            for n in (2, 3, 4):
                counts.update(run[i:i + n] for i in range(len(run) - n + 1))
    best_extension = Counter()
    for gram, count in counts.items():
        if len(gram) > 2:
            for sub in (gram[:-1], gram[1:]):
                best_extension[sub] = max(best_extension[sub], count)
    kept = [
        (gram, count)
        for gram, count in counts.items()
        if count >= 2
        and best_extension[gram] < 0.8 * count
        and gram[0] not in BAD_START
        and gram[-1] not in BAD_END
        and not any(stop in gram for stop in STOP_WORDS)
    ]
    kept.sort(key=lambda item: (-item[1], item[0]))
    return [
        {"词": gram, "次数": count, "每万字": round(count * 10000 / chars, 2)}
        for gram, count in kept[:TOP_WORDS]
    ]


def read_phrases(path):
    """词表每行一个词；空行和 # 开头的注释行跳过。"""
    lines = (line.strip() for line in decode(path.read_bytes()).splitlines())
    return [line for line in lines if line and not line.startswith("#")]


def phrase_counts(paragraphs, phrases, chars):
    """词表里每个词在正文里的出现次数（段内不重叠计数），保持词表顺序。"""
    return [
        {"词": phrase, "次数": n, "每万字": round(n * 10000 / chars, 2) if chars else 0.0}
        for phrase in phrases
        for n in [sum(p.count(phrase) for p in paragraphs)]
    ]


def measure(chapter):
    """一章的原始量：字数、引号内字数、每句长度、每段长度。"""
    paragraphs = chapter["段落"]
    return {
        "字数": sum(char_count(p) for p in paragraphs),
        "对白": sum(dialogue_count(p) for p in paragraphs),
        "句长": [char_count(s) for p in paragraphs for s in sentences(p)],
        "段长": [char_count(p) for p in paragraphs],
    }


def build(chapters, phrases=None):
    measured = [measure(c) for c in chapters]
    chars = sum(m["字数"] for m in measured)
    paragraphs = [p for c in chapters for p in c["段落"]]
    result = {
        "全书": {
            "章数": len(chapters),
            "字数": chars,
            "章字数统计": length_stats([m["字数"] for m in measured]),
            "对白占比": ratio(sum(m["对白"] for m in measured), chars),
            "句长统计": length_stats([n for m in measured for n in m["句长"]], SENTENCE_BUCKETS),
            "段长统计": length_stats([n for m in measured for n in m["段长"]], PARAGRAPH_BUCKETS),
            "高频词": top_words(paragraphs, chars),
        },
        "章节": [
            {
                "序号": i,
                "标题": c["标题"],
                "卷": c["卷"],
                "字数": m["字数"],
                "对白占比": ratio(m["对白"], m["字数"]),
                "句长统计": length_stats(m["句长"], SENTENCE_BUCKETS),
                "段长统计": length_stats(m["段长"], PARAGRAPH_BUCKETS),
            }
            for i, (c, m) in enumerate(zip(chapters, measured), 1)
        ],
    }
    if phrases is not None:
        result["全书"]["词表计数"] = phrase_counts(paragraphs, phrases, chars)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description="网文指标脚本")
    parser.add_argument("source", type=Path, help="txt 文件或章节 md 目录")
    parser.add_argument("-o", "--output", type=Path, help="写到这个文件（UTF-8），不给就写到标准输出")
    parser.add_argument("--phrases", type=Path, help="词表文件，每行一个词；输出里加一项全书的词表计数")
    args = parser.parse_args(argv)
    for path in (args.source, args.phrases):
        if path and not path.exists():
            parser.error(f"找不到输入：{path}")
    phrases = read_phrases(args.phrases) if args.phrases else None
    result = build(read_source(args.source), phrases)
    data = json.dumps(result, ensure_ascii=False, indent=2).encode("utf-8") + b"\n"
    if args.output:
        args.output.write_bytes(data)
    else:
        sys.stdout.buffer.write(data)


if __name__ == "__main__":
    main()
