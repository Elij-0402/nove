# 网文工坊 · Novel Workshop

一套中文网文写作 skills workflow：从对标分析、立项、设定到大纲、写章和审稿，把可复用的方法与作者的关键决策分开。

**入口是 `/novel`，不是一键生成整本书。** 非关卡阶段自动接续，立项、总纲、卷纲和章节关卡由作者拍板。对标只借鉴抽象技法，不搬用原作情节，也不承诺商业成绩。

## 前置条件

- **Python 3.10+**：初始化和度量脚本只用标准库，无须安装 pip 依赖。Windows 可用 `py -3` 替代 `python`，需确保所选版本符合要求。
- **支持 skills 的代理工具**：以 Claude Code 为主要使用入口。完整流程需要文件读写、执行 Python、子代理、独立审稿上下文及设定阶段的联网检索能力；缺少能力时应报告限制，不伪装成已完成独立审稿。
- **Node.js/npm**：仅通过 `npx skills` 安装时需要；手动复制技能不需要 Node.js。

其他工具可使用包内的技能文档和 `agents/openai.yaml` 元数据，但这不表示已经完成所有客户端的端到端兼容验证。

## 安装

七个技能共享状态机、模板和度量脚本，**必须整套安装，保持原名并放在同一父目录**。可以单独调用某个阶段，但不能只安装那个阶段。

### 安装到写作项目

先进入你自己的写作项目目录，再运行：

```bash
npx skills add Elij-0402/nove --agent claude-code --skill '*' --copy
```

这会向当前项目安装完整套件，不是安装到系统全局。使用复制模式可避免 Windows 符号链接权限差异。安装到其他宿主前，请核实其技能目录和所需能力。

该命令安装仓库默认分支的版本；尚未合并的开发分支请使用下面的本地源码安装方式，不要把分支已推送视为默认版本已更新。

### 从本地源码安装

取得此仓库的目标版本后，在写作项目目录运行（替换为真实路径）：

```bash
npx skills add "/path/to/nove/skills" --agent claude-code --skill '*' --copy
```

不使用安装器时，把仓库 `skills/` 下的七个完整目录复制到写作项目的 `.claude/skills/` 下。保留每个目录的参考文档、`scripts/`、`assets/` 和 `agents/`，不要只复制 `SKILL.md`；已有同名技能时先备份、比较，不覆盖未知修改。

**仅克隆仓库不会自动注册技能。** 安装完成后按宿主要求重新加载技能或开启新会话。

## 第一次写作

在写作项目中调用：

```text
/novel
```

总控会按照 [SETUP 约定](skills/novel/SETUP.md)准备工作区、检查当前进度，再给出下一步。单独调用阶段技能也会先检查初始化。

项目级 Claude Code 复制安装后，也可以在写作项目根手动初始化：

```bash
python ".claude/skills/novel/scripts/setup.py" "."
```

从源码直接运行时，脚本路径应指向**源码仓库**，参数则是独立的**写作项目**：

```bash
python "/path/to/nove/skills/novel/scripts/setup.py" "/path/to/my-novel"
```

初始化会逐文件补齐默认 `规范/`，创建 `作品/`、`对标库/`。已有文件保持原样，缺少必要安装资产则报错停止。不要只因 `规范/` 目录已存在就认为初始化完整。

接着把你有权使用的对标文本放入 `对标库/<书名>/原文.txt`，调用 `/novel-chaishu` 拆书，或让 `/novel` 引导下一步。仓库不附带小说原文或作者的创作项目。

## 写作流程

```text
拆书 → 立项★ → 设定 → 总纲★ → 卷纲★ → 写章 → 审稿 → 章节★
                                             ↑              ↓
                                             └── 下一章 ────┘
卷末章节通过 → 卷末结算 → 下一卷卷纲★ → …… → 完结
```

★ 是作者关卡。章节默认每章停顿，调整停顿频率后的规则见 [PROJECT.md](skills/novel/PROJECT.md)；卷末总是停顿点。

| Skill | 职责 |
|---|---|
| `/novel` | 查看进度、核对产物、接续到下一个人工关卡 |
| `/novel-chaishu` | 拆书，生成报告、机械与语义基线、风格档案 |
| `/novel-lixiang` | 提出差异化方案，作者拍板后创建项目 |
| `/novel-sheding` | 角色、世界、势力、体系与时间线设定 |
| `/novel-dagang` | 总纲、卷纲、章纲、伏笔表和原创性自检 |
| `/novel-xiezhang` | 代写、收稿、局部代笔、卷末结算 |
| `/novel-shengao` | 一致性、AI 腔、字数轻审；基线对比与读者盲评全审 |

每部作品的 `作品/<书名>/项目.md` 是唯一进度记录。状态机、精确字段和关卡规则只在 [PROJECT.md](skills/novel/PROJECT.md) 定义，不从目录名猜进度。

## 源码与写作数据

```text
nove/
├── README.md、LICENSE、AGENTS.md、CLAUDE.md
├── skills/
│   ├── novel/                  总控、状态机、初始化
│   │   ├── assets/规范/        默认模板、读者画像、词表
│   │   └── scripts/setup.py
│   ├── novel-chaishu/          拆书、度量脚本及回归测试
│   ├── novel-lixiang/
│   ├── novel-sheding/
│   ├── novel-dagang/
│   ├── novel-xiezhang/
│   └── novel-shengao/
├── scripts/check_package.py   发布包检查
├── tests/                    初始化与安装测试
└── .github/workflows/        跨平台验证
```

作者的写作项目另外保存：

- `作品/`：设定、大纲、正文、审稿和摘要。
- `对标库/`：用户提供的原文及拆书产物；源文、标注与指标按阶段要求保存。
- `规范/`：作者可修改的本地副本。

`skills/novel/assets/规范/` 是唯一分发的默认规范。更新技能不会替你合并已修改的用户规范；重跑初始化只补缺项。需要新版模板时，先备份并比较，再手动合并。模板字段被技能读取，改字段名要同步相关规则。

切章脚本的输出目录必须是专门存放可再生成章节的目录：重跑会清理其中旧的 `.md`，不要指向作者正文或其他手写文件目录。

## 更新与迁移

从 GitHub 来源通过安装器安装的套件，可以在写作项目中更新：

```bash
npx skills update novel novel-chaishu novel-lixiang novel-sheding novel-dagang novel-xiezhang novel-shengao --project
```

本地源码安装请更新源码后重新执行本地安装命令；手动复制安装则从同一版本更新全部七个目录。更新前都应备份自行修改过的技能文件；用户规范按前述方式比较、合并，不强制覆盖。

**从旧工作区仓库迁移时，先备份作品、对标库、规范和个人配置。** 新版 Git 树不再跟踪这些资料；整理操作在原工作区保留了文件，但其他克隆拉取包含删除的提交时，Git 仍可能删除那些旧的受跟踪副本。未跟踪资料不再由此仓库备份，应自行安排数据备份。

本次整理保留既有 Git 历史，历史提交仍可能包含旧作品、对标材料和工程工具。**干净的当前发布树不等于历史已清除。**

## 开发与验证

在仓库根运行：

```bash
python scripts/check_package.py
python -m unittest discover -s skills/novel-chaishu/scripts -p "test_*.py" -v
python -m unittest discover -s tests -p "test_*.py" -v
```

所有自动测试使用原创合成输入和临时目录，不要求本地小说原文。CI 在 Windows/Linux 上验证 Python 3.10 与 3.14。发布前还应在干净检出中重跑，避免本地忽略文件掩盖依赖缺失。

安装器命令的参数已按 `skills 1.7.0` 核对。自动测试验证包完整性、初始化和脚本链路，不等同于模型写作质量或实际客户端的关卡行为已通过；后者需在目标宿主中另行验收。

维护约定见 [AGENTS.md](AGENTS.md)。

## 许可证与素材

本项目有权授权的技能文档、脚本、模板及原创测试以 [MIT](LICENSE) 许可发布，版权归 2026 Elij-0402。

MIT 不对用户作品、对标原文或历史中的第三方材料重新授权。请自行确认输入材料的使用权，生成的新作保持原创。写作数据由你保存和管理；调用模型与外部工具时，遵循相应服务的数据政策。
