"""检查七技能发布包；只读，不依赖 Git、宿主配置或作者资料。"""
import argparse
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit


REQUIRED = {
    "novel": ("PROJECT.md", "SETUP.md", "scripts/setup.py"),
    "novel-chaishu": (
        "METRICS.md", "SEMANTICS.md", "CHUNK-BRIEF.md", "OUTPUTS.md",
        "scripts/metrics.py", "scripts/split.py", "scripts/semantics.py",
    ),
    "novel-lixiang": ("OUTPUTS.md",),
    "novel-sheding": ("CHECK.md", "OUTPUTS.md"),
    "novel-dagang": ("CHECK.md", "OUTPUTS.md"),
    "novel-xiezhang": ("PARTIAL.md", "VOLUME-END.md", "OUTPUTS.md"),
    "novel-shengao": (
        "CONSISTENCY.md", "AI-TONE.md", "WORDCOUNT.md", "BASELINE.md",
        "READERBLIND.md", "OUTPUTS.md",
    ),
}
ASSETS = (
    "AI腔清单.md", "套话候选.txt",
    "模板/设定/世界观.md", "模板/设定/力量体系.md", "模板/设定/角色.md",
    "模板/设定/关系体系.md", "模板/设定/势力.md", "模板/设定/时间线.md",
    "模板/大纲/伏笔表.md", "模板/大纲/卷纲.md", "模板/大纲/总纲.md",
    "读者画像/晋江.md", "读者画像/番茄.md", "读者画像/起点.md",
)
LINK = re.compile(r"\[[^\]\n]*\]\(([^)\n]+)\)")
SCRIPT = re.compile(r"<技能目录>/([\w/-]+\.py)")
FORBIDDEN_DIRS = {".git", ".claude", ".agents", "作品", "对标库", "资料"}


def need_file(path, errors):
    if not path.is_file():
        errors.append(f"缺少文件：{path}")
    elif path.stat().st_size == 0:
        errors.append(f"空文件：{path}")


def check_links(path, text, errors):
    for match in LINK.finditer(text):
        target = match.group(1).strip()
        # 只检查实际文件链接；产物占位符和外部网址不是安装依赖。
        if any(char in target for char in "<>{}"):
            continue
        target = target.split(' "', 1)[0]
        parsed = urlsplit(target)
        if parsed.scheme or target.startswith("//") or not parsed.path:
            continue
        destination = path.parent / unquote(parsed.path)
        if not destination.exists():
            line = text.count("\n", 0, match.start()) + 1
            errors.append(f"断链：{path}:{line} -> {target}")


def check_package(skills_root, repository=None):
    skills_root = Path(skills_root).resolve()
    errors = []
    if not skills_root.is_dir():
        return [f"缺少技能目录：{skills_root}"]
    actual = {p.name for p in skills_root.iterdir() if p.is_dir() and p.name != "__pycache__"}
    if actual != set(REQUIRED):
        errors.append(f"技能集合不符：缺少 {sorted(set(REQUIRED) - actual)}；多出 {sorted(actual - set(REQUIRED))}")

    for name, files in REQUIRED.items():
        base = skills_root / name
        entry = base / "SKILL.md"
        for relative in ("SKILL.md", "agents/openai.yaml", *files):
            need_file(base / relative, errors)
        if not entry.is_file():
            continue
        text = entry.read_text(encoding="utf-8-sig")
        lines = text.splitlines()
        if not lines or lines[0] != "---" or "---" not in lines[1:]:
            errors.append(f"frontmatter 缺失：{entry}")
            continue
        end = lines.index("---", 1)
        fields = {}
        for line in lines[1:end]:
            if ":" in line:
                key, value = line.split(":", 1)
                if key.strip() in fields:
                    errors.append(f"frontmatter 字段重复：{entry} -> {key.strip()}")
                fields[key.strip()] = value.strip().strip("\"'")
        if fields.get("name") != name or not fields.get("description"):
            errors.append(f"name/description 无效：{entry}")
        if fields.get("disable-model-invocation", "false").lower() == "true":
            errors.append(f"总控无法调用的技能：{entry}")
        if "SETUP.md" not in text:
            errors.append(f"入口缺少初始化指针：{entry}")

    for relative in ASSETS:
        need_file(skills_root / "novel" / "assets" / "规范" / relative, errors)

    paths = (path for name in REQUIRED for path in (skills_root / name).rglob("*"))
    for path in paths:
        relative = path.relative_to(skills_root)
        if path.is_dir() and path.name in FORBIDDEN_DIRS:
            errors.append(f"发布包含本地目录：{relative}")
        # 本地跑测试会产生字节码；Git 发布树另行检查，不把缓存当技能内容。
        if "__pycache__" in relative.parts or not path.is_file():
            continue
        if path.name == ".env" or path.name.startswith(".env."):
            errors.append(f"发布包含环境文件：{relative}")
        if path.suffix != ".md":
            continue
        text = path.read_text(encoding="utf-8-sig")
        check_links(path, text, errors)
        for match in SCRIPT.finditer(text):
            need_file(skills_root / match.group(1), errors)
        if re.search(r"\bpython\s+\.\./", text):
            errors.append(f"脚本路径仍相对错误的工作目录：{relative}")
        if re.search(r"[A-Za-z]:[\\/]Users[\\/]", text):
            errors.append(f"文档含本机用户路径：{relative}")

    if repository is not None:
        for name in ("README.md", "AGENTS.md", "CLAUDE.md", "LICENSE", ".gitignore"):
            path = Path(repository) / name
            need_file(path, errors)
            if path.is_file() and path.suffix == ".md":
                check_links(path, path.read_text(encoding="utf-8-sig"), errors)
    return errors


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skills-root", type=Path, help="检查另一处完整安装，不检查仓库根文档")
    args = parser.parse_args()
    repository = Path(__file__).resolve().parents[1]
    try:
        errors = check_package(args.skills_root or repository / "skills",
                               None if args.skills_root else repository)
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"检查失败：{exc}", file=sys.stderr)
        return 1
    if errors:
        for error in errors:
            print(error, file=sys.stderr)
        return 1
    print("发布检查通过：7 个技能、14 份默认规范及其静态依赖完整。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
