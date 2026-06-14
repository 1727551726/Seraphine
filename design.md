# Seraphine UI 设计规范

## 设计语言

基于 **Microsoft Fluent Design**，使用 [PyQt-Fluent-Widgets](https://github.com/zhiyiYo/PyQt-Fluent-Widgets) 构建。主窗口继承 `FluentWindow`，完整支持暗色/亮色双主题。

## 色彩体系

### 主题色

使用 `--ThemeColor` CSS 变量体系，用户可通过设置页 `ThemeColorSettingCard` 自定义：

| 变量 | 用途 |
|------|------|
| `--ThemeColorPrimary` | 选中状态、标题、强调元素 |
| `--ThemeColorLight1/2/3` | 悬停、边框、按下（亮色主题） |
| `--ThemeColorDark1/2/3` | 悬停、高亮、按下（暗色主题） |

### 背景色

| 元素 | 暗色 | 亮色 |
|------|------|------|
| 卡片背景 | `rgba(255,255,255,0.051)` | `rgba(245,245,245,0.667)` |
| 卡片边框 | `rgb(35,35,35)` ~ `rgb(82,82,82)` | `rgba(0,0,0,0.095)` |
| 悬停背景 | `rgba(255,255,255,0.084)` | `rgba(233,233,233,0.5)` |

### 状态色（可自定义）

| 状态 | 默认颜色 |
|------|----------|
| 胜利 | `#2839b01b` 绿色半透明 |
| 失败 | `#28d3190c` 红色半透明 |
| 重做 | `#28a2a2a2` 灰色半透明 |

### 文字层次

| 层次 | 暗色 | 亮色 |
|------|------|------|
| 主标题 | `white` | `black` |
| 副标题 | `rgb(200,200,200)` | `rgb(100,100,100)` |
| 辅助文字 | `rgb(176,176,177)` | `rgb(131,131,131)` |
| 禁用文字 | `rgba(255,255,255,0.43)` | `rgba(0,0,0,0.43)` |

## 字体

- **西文**: `Segoe UI`
- **中文**: `Microsoft YaHei`
- **抗锯齿**: `PreferAntialias` + `PreferFullHinting`

### 字号层次

| 用途 | 字号 | 字重 |
|------|------|------|
| 页面标题 | 33px | normal |
| 召唤师名称 | 32px | bold |
| 结果标签 | 28px | bold |
| 副标题 | 17-22px | bold |
| 正文 | 14px | normal |
| 按钮文字 | 13px | normal |
| 辅助小字 | 12px | normal |

## 圆角

| 元素 | 圆角 |
|------|------|
| 卡片/面板/表格 | 6px |
| 按钮 | 5-6px |
| 英雄图标 | 3-4px |
| 技能图标 | 5px |
| 弹框/选择区 | 8-10px |

## 间距

- **页面内边距**: `30, 32, 30, 20` (左、上、右、下)
- **卡片内边距**: `6-8px`
- **元素间距**: `5-20px`
- **紧凑间距**: `1-4px`

## 组件规范

### 按钮

- **TransparentButton**: 透明背景，5px 圆角，悬停半透明背景，选中态文字变主题色加粗
- **PrimaryButton**: 主题色实心，6px 圆角，暗色主题黑字/亮色主题白字
- **ToolButton**: 图标按钮，16x16 或 26x26

### 卡片

所有卡片统一 `6px` 圆角 + `1px` 边框 + 半透明背景。胜负状态卡片通过 `ColorAnimationFrame` 自动应用状态色。

### 加载状态

使用 `QStackedWidget`：索引 0 = 加载页（`IndeterminateProgressRing`），索引 1 = 内容页。

## 布局

- 左侧导航栏宽度: 250px
- 所有页面继承 `SeraphineInterface`（`SmoothScrollArea`），纵向 `QVBoxLayout`
- 搜索页左侧 Tab 栏: 160px 固定宽度
- 对局信息页左右比例: 2:7

## 图标

- 61 个 SVG 图标存放在 `app/resource/icons/`
- 每个图标 `_black.svg` / `_white.svg` 双版本
- 扁平化线条风格，无填充
- 通过 `Icon` 枚举类管理，自动根据主题切换颜色

## 样式表

- 存放路径: `app/resource/qss/{dark|light}/{组件名}.qss`
- 通过 `StyleSheet.XXX.apply(self)` 加载
- 每个页面/组件必须同时提供暗色和亮色两套 QSS

## 主题切换

- `ColorChangeable` 基类 + `ColorManager` 单例，监听 `qconfig.themeChanged` 信号
- Win11 默认开启 Mica 毛玻璃效果（`cfg.micaEnabled`）
- 支持 DPI 缩放: 1, 1.25, 1.5, 1.75, 2, Auto
