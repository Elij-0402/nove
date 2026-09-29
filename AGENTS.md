# 网文工坊维护约定

本仓库发布中文小说写作 skills，不存放作者作品或对标原文。源码位于 `skills/`，克隆仓库不等于向宿主注册技能；安装和使用见 [README.md](README.md)。

## 修改入口

- **修改阶段流转、进度字段或关卡行为前**，读取 [PROJECT.md](skills/novel/PROJECT.md)。它是唯一状态机定义；模板字段与技能读取规则需同步，不能只改字段名。
- **修改安装、脚本路径或默认规范前**，读取 [SETUP.md](skills/novel/SETUP.md)。技能安装位置与写作工作区是两个根；运行依赖必须包含在七技能内，不能依赖本文件随安装分发。
- **修改度量口径前**，读取 [METRICS.md](skills/novel-chaishu/METRICS.md) 与 [SEMANTICS.md](skills/novel-chaishu/SEMANTICS.md)，保留确定性并补对应回归测试。

## 发布边界

- `skills/novel/assets/规范/` 是默认规范的唯一分发源；工作区 `规范/` 是作者副本，初始化只补缺失文件。
- 保持七技能同级、整套安装。共享参考用文件链接，业务规则不在 README 或其他入口复制。
- Python 最低版本为 3.10，只用标准库；代码和说明使用中文，保持现有命名风格。
- 作品、对标原文、个人配置、工程 skills、嵌套备份和缓存留在本地。测试使用原创合成夹具与临时目录，不向安装目录或作者作品目录写测试产物。

## 验证

在仓库根运行：

```text
python scripts/check_package.py
python -m unittest discover -s skills/novel-chaishu/scripts -p "test_*.py" -v
python -m unittest discover -s tests -p "test_*.py" -v
git diff --check
```

发布前在干净检出中复验；自动测试只能验证文件、脚本和安装路径，不能替代实际宿主中的关卡行为验收。
