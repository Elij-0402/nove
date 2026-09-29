"""SETUP: 把 skill 自带的 assets/规范/ 铺开到项目根，建空目录。
可反复运行（幂等）。已存在的文件不覆盖；写入前检查资产和目标类型。
用法: python setup.py [项目根路径]
"""
import argparse
import sys
from pathlib import Path


REQUIRED_ASSETS = (
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


def setup(project_root: str | None = None):
    assets_guidelines = Path(__file__).resolve().parents[1] / "assets" / "规范"
    root = Path(project_root).resolve() if project_root is not None else Path.cwd().resolve()
    project_guidelines = root / "规范"

    # 先读完源资产，所有已知的源错误都必须在创建项目目录之前报出。
    if not assets_guidelines.is_dir():
        raise ValueError(f"未找到规范资产目录: {assets_guidelines}")
    for name in REQUIRED_ASSETS:
        if not (assets_guidelines / name).is_file():
            raise ValueError(f"必需资产缺失或不是文件: {assets_guidelines / name}")
    contents = {
        src.relative_to(assets_guidelines): src.read_bytes()
        for src in sorted(assets_guidelines.rglob("*")) if src.is_file()
    }
    for name in REQUIRED_ASSETS:
        if not contents[Path(name)].strip():
            raise ValueError(f"必需资产为空: {assets_guidelines / name}")

    # 连父目录也预检，避免先铺了一半才遇到“目录位置已是文件”。
    directories = {root, project_guidelines, root / "作品", root / "对标库"}
    directories.update((project_guidelines / rel).parent for rel in contents)
    for directory in sorted(directories):
        for path in (directory, *directory.parents):
            if (path.exists() or path.is_symlink()) and not path.is_dir():
                raise ValueError(f"目标应为目录，但已存在其他类型: {path}")
    for rel in contents:
        dst = project_guidelines / rel
        if (dst.exists() or dst.is_symlink()) and not dst.is_file():
            raise ValueError(f"目标应为文件，但已存在其他类型: {dst}")

    laid = 0
    skipped_files = []
    for rel, body in contents.items():
        dst = project_guidelines / rel
        if dst.exists():
            skipped_files.append(rel)
            continue
        dst.parent.mkdir(parents=True, exist_ok=True)
        # 独占创建，即使预检后出现同名用户文件，也绝不覆盖。
        with dst.open("xb") as stream:
            stream.write(body)
        laid += 1
        print(f"  新增 {dst.relative_to(root)}")
    print(f"规范/ 铺了 {laid} 个文件，跳过了 {len(skipped_files)} 个（已存在未覆盖）")
    if skipped_files:
        print("  跳过:", [str(Path("规范") / rel) for rel in skipped_files])

    for name in ("作品", "对标库"):
        directory = root / name
        existed = directory.exists()
        directory.mkdir(parents=True, exist_ok=True)
        print(f"{name}/ {'已存在' if existed else '已创建'}")
    print("\nSETUP 完成。下一步: 把对标源本放进 对标库/<书名>/原文.txt，然后调 /novel-chaishu")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="初始化网文项目，补齐规范文件且不覆盖已有文件。")
    parser.add_argument("project_root", nargs="?", metavar="项目根路径", help="目标目录，省略时使用当前工作目录")
    args = parser.parse_args(argv)
    try:
        setup(args.project_root)
    except (OSError, ValueError) as exc:
        print(f"SETUP 失败: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
