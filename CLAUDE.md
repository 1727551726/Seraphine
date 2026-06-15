# CLAUDE.md

## 项目概述

Seraphine 是一个**仅限 Windows** 的 PyQt5 桌面应用，用于英雄联盟（LOL）战绩查询。通过 LCU API 获取数据并提供辅助功能。GUI 基于 PyQt-Fluent-Widgets。

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
.\make.ps1          # 生成 Seraphine.7z
.\make.ps1 -dest .  # 指定输出目录
.\make.ps1 -dbg     # 保留 dist/ 目录用于调试
```

## 验证方式

本项目**无测试套件、无 linter、无类型检查**。验证方式为手动运行 `python main.py` 检查行为。

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

- **单例**：`connector`、`signalBus`、`cfg`、`logger`、`opgg`。直接导入使用，不要实例化。
- **Qt 中的异步**：使用 `qasync`（`QEventLoop`）在 Qt 事件循环中运行 asyncio。异步槽函数使用 `@asyncSlot` 装饰器。
- **SignalBus**：跨组件事件的中央发布/订阅中心（如 `lolClientStarted`、`gameStatusChanged`、`champSelectChanged`）。
- **Retry 装饰器**：`@retry(count=5, retry_sep=0)` 包装 connector 方法，自动重试并记录日志。
- **配置系统**：基于 `qfluentwidgets.QConfig`。所有设置在 `cfg` 中。用户配置存储在 `%AppData%/Seraphine/config.json`。
- **版本号**：定义在 `app/common/config.py` 的 `VERSION`。CI 在 HEAD 提交中检测此值是否变更，变更时自动创建 GitHub Release。

## 工作流约束

### 提交规范
- **禁止擅自提交**: 未经用户明确指令，不得执行 `git commit` 或 `git push`。
- **开发日志**: 用户要求提交时，先在 `developLog/` 目录创建日志（格式：`YYYY-MM-DD_功能名称.md`）。

### 修改后必须 Code Review + 启动验证
1. 对变更文件进行 code review（语法、导入完整性、逻辑正确性）
2. Code review 通过后，运行 `python main.py` 启动应用，确认无报错正常运行
3. 若发现问题，修复后重复上述流程

## 界面设计约束

- **Fluent Design**: 基于 PyQt-Fluent-Widgets，不引入其他 UI 框架
- **双主题必须**: 每个页面/组件必须同时提供 `dark/` 和 `light/` 两套 QSS，禁止硬编码颜色值
- **圆角统一**: 卡片/面板 6px，按钮 5-6px
- **字体规范**: 西文 `Segoe UI` + 中文 `Microsoft YaHei`，基础字号 14px
- **页面内边距**: 统一 `30, 32, 30, 20` 或 `30, 32, 30, 30`
- **主题色变量**: 使用 `--ThemeColor` CSS 变量，不硬编码主题色
- **状态色可定制**: 胜/负/重做颜色必须从 `cfg` 读取，支持用户自定义
- **组件复用**: 使用 `app/components/` 中已有的自定义组件
- **加载状态**: 使用 `QStackedWidget` 模式（索引 0=加载页，索引 1=内容页）
- **图标双版本**: 新增图标必须同时提供 `_black.svg` 和 `_white.svg`
- **样式表加载**: 通过 `StyleSheet.XXX.apply(self)` 加载，不直接 `setStyleSheet()`
- **导航栏顺序**: 开始 → 生涯 → 搜索 → 对局信息 → 游戏流 → 其他功能

## Windows 专属依赖

应用导入 `win32api`、`win32gui`、`winreg`、`psutil`，并使用 `subprocess` 运行 `tasklist`。从 Windows 注册表读取 LOL 安装路径。无法在 Linux/macOS 上运行。

## 配置陷阱

`qfluentwidgets.py` 在导入时将 `sys.stdout = None` 以抑制库的广告输出，之后恢复。这是有意为之——不要"修复"它。
