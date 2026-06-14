# AGENTS.md

## 项目概述

Seraphine 是一个**仅限 Windows** 的 PyQt5 桌面应用，用于英雄联盟（LOL）战绩查询。通过 LCU（League Client Update）API 获取数据并提供辅助功能。GUI 基于 [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets)。

## 快速启动

```powershell
conda create -n seraphine python=3.8
conda activate seraphine
pip install -r requirements.txt
python main.py
```

## 构建与打包

```powershell
pip install pyinstaller==5.13
.\make.ps1          # 在当前目录生成 Seraphine.7z
.\make.ps1 -dest .  # 指定输出目录
.\make.ps1 -dbg     # 保留 dist/ 目录用于调试，不生成 7z
```

`make.ps1` 执行 PyInstaller 后，将 `app/` 复制到 dist，然后**删除** `app/common`、`app/components`、`app/lol`、`app/view` 及游戏资源目录（已编译进 exe）。同时生成 `filelist.txt` 供更新器使用。

## 无测试、Lint 和类型检查

本仓库**没有测试套件、没有 linter 配置、没有类型检查器、没有格式化器**。不存在 `pytest`、`mypy`、`ruff`、`black` 等配置。验证方式为手动运行应用检查行为。

## 架构

```
main.py                  # 入口：QApplication + qasync 事件循环
app/
  common/
    config.py            # 单例 Config（QConfig 子类），VERSION、BETA、cfg
    signals.py           # 全局 SignalBus（pyqtSignal 中心，跨组件通信）
    logger.py            # 单例 Logger -> log/ 目录
    util.py              # 辅助工具：GitHub API、LOL 客户端 PID 检测、注册表读取
    qfluentwidgets.py    # 重导出垫片：通过置空 stdout 抑制 qfluentwidgets 广告
    update.py            # 自更新：生成并运行 PowerShell 更新脚本
    icons.py, style_sheet.py
  lol/
    connector.py         # 单例 `connector`（LolClientConnector）— 所有 LCU API 调用
    listener.py          # QThread 轮询 LOL 客户端进程（基于 PID）
    tools.py             # 游戏逻辑辅助：选人/禁用/交换/交易、服务器映射、数据解析
    opgg.py              # OPGG API 客户端（异步，alru_cache）
    aram.py              # 大乱斗 Buff 数据（来自 jddld.com）
    champions.py         # 英雄别名解析
    exceptions.py        # 自定义异常（SummonerNotFound 等）
  components/            # 可复用 PyQt 控件（非视图）
  view/                  # 顶层界面（导航页）
    main_window.py       # FluentWindow，含导航、系统托盘、监听器连接
    career_interface.py, search_interface.py, game_info_interface.py, ...
  resource/
    i18n/                # Qt .ts/.qm 翻译文件 + gamemodes.json
    images/, icons/, qss/, bin/
```

## 关键模式

- **单例**：`connector`（app/lol/connector.py:1383）、`signalBus`（app/common/signals.py:40）、`cfg`（app/common/config.py:175）、`logger`（app/common/logger.py:110）、`opgg`（app/lol/opgg.py）。直接导入使用，不要实例化。
- **Qt 中的异步**：使用 `qasync`（`QEventLoop`）在 Qt 事件循环中运行 asyncio。异步槽函数使用 `@asyncSlot` 装饰器。connector 使用 `aiohttp` 进行 LCU API 调用。
- **SignalBus**：跨组件事件的中央发布/订阅中心（如 `lolClientStarted`、`gameStatusChanged`、`champSelectChanged`）。在视图构造函数中连接。
- **Retry 装饰器**：`@retry(count=5, retry_sep=0)` 包装 connector 方法，自动重试并记录日志。
- **`@needLcu()` 装饰器**：守护需要活跃 LCU 连接的 connector 方法。
- **配置系统**：基于 `qfluentwidgets.QConfig`。所有设置在 `cfg` 中。用户配置存储在 `%AppData%/Seraphine/config.json`。
- **版本号**：定义在 `app/common/config.py` 的 `VERSION = "1.1.1"`。CI 在 HEAD 提交中检测此值是否变更，变更时自动创建 GitHub Release。

## CI / 发布

- `.github/workflows/build_seraphine.yaml`：在 Windows 上用 Python 3.8 构建，产出 `Seraphine.7z`。
- 自动发布：CI 检查 `config.py` 中的 `VERSION` 是否在 HEAD 提交中被修改；如果是，创建 GitHub Release 并通过 `sync.py` 同步到 Gitee。
- `sync.py` 需要环境变量：`GITEE_OWNER`、`GITEE_REPO`、`GITEE_USERNAME`、`GITEE_PASSWORD`、`GITEE_CLIENT_ID`、`GITEE_CLIENT_SECRET`。

## Windows 专属依赖

应用导入 `win32api`、`win32gui`、`winreg`、`psutil`，并使用 `subprocess` 运行 `tasklist`。从 Windows 注册表读取 LOL 安装路径。无法在 Linux/macOS 上运行。

## 国际化（i18n）

- 翻译源文件：`app/resource/i18n/Seraphine.zh_CN.ts`（Qt Linguist 格式）
- 编译后：`Seraphine.zh_CN.qm`
- `Seraphine.pro` 列出所有可翻译源文件，供 `lupdate` 使用
- 运行时语言选择通过 `cfg.language`（简体中文、英文、自动）

## 配置陷阱

`qfluentwidgets.py` 在导入时将 `sys.stdout = None` 以抑制库的广告输出，之后恢复。这是有意为之——不要"修复"它。

## 更新器流程

`app/common/update.py` 生成 PowerShell 脚本（`updater.ps1`），等待 Seraphine.exe 退出，通过 `filelist.txt` 删除旧文件，从 `%AppData%/Seraphine/temp` 移动新文件，然后重新启动 exe。

## 界面设计约束

**所有 UI 修改必须遵守 `design.md` 中的设计规范。** 核心约束：

- **Fluent Design**: 基于 PyQt-Fluent-Widgets，不引入其他 UI 框架或自造轮子
- **双主题必须**: 每个页面/组件必须同时提供 `dark/` 和 `light/` 两套 QSS，禁止硬编码颜色值
- **圆角统一**: 卡片/面板 6px，按钮 5-6px，不得随意使用其他圆角值
- **字体规范**: 西文 `Segoe UI` + 中文 `Microsoft YaHei`，基础字号 14px
- **页面内边距**: 统一 `30, 32, 30, 20` 或 `30, 32, 30, 30`
- **主题色变量**: 使用 `--ThemeColor` CSS 变量，不硬编码主题色
- **状态色可定制**: 胜/负/重做颜色必须从 `cfg` 读取，支持用户自定义
- **组件复用**: 使用 `app/components/` 中已有的自定义组件（`CardWidget`、`TransparentButton`、`SummonerName` 等），不重复造轮子
- **加载状态**: 使用 `QStackedWidget` 模式（索引 0=加载页，索引 1=内容页）
- **图标双版本**: 新增图标必须同时提供 `_black.svg` 和 `_white.svg`，通过 `Icon` 枚举注册
- **样式表加载**: 通过 `StyleSheet.XXX.apply(self)` 加载，不直接 `setStyleSheet()`

## 工作流约束

- **禁止擅自提交**: 未经用户明确指令，不得执行 `git commit` 或 `git push`。所有代码修改完成后，等待用户确认再提交。
- **修改后必须 Code Review + 启动验证**: 每次代码修改完成后，必须：
  1. 启动 subagent 对变更文件进行 code review（检查语法、导入完整性、逻辑正确性）
  2. Code review 通过后，运行 `python main.py` 启动应用，确认无报错正常运行
  3. 若发现问题，修复后重复上述流程

## 开发日志规范

**当用户要求提交修改时，必须先生成开发日志：**

1. 在 `developLog/` 目录下创建日志文件，命名格式：`YYYY-MM-DD_功能名称.md`
2. 日志内容包含：
   - 功能概述
   - 实现步骤
   - 遇到的问题及解决方案
   - 经验总结
   - 文件变更清单
   - 后续优化建议（如有）
3. 将日志文件与代码一起提交
