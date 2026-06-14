# 游戏流模块专属图标

## 功能概述

为游戏流（GameFlow）模块新增专属 SVG 图标，替换原来共用的 `Icon.GAME`。

## 设计方案

- 圆环（循环/自动化）+ 中心播放三角（流程推进）
- Fluent 线条风格，24x24 双版本（black/white）

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `app/resource/icons/GameFlow_black.svg` | 新增 | 暗色主题图标 |
| `app/resource/icons/GameFlow_white.svg` | 新增 | 亮色主题图标 |
| `app/common/icons.py` | 修改 | 注册 `GAMEFLOW` 枚举 |
| `app/view/main_window.py` | 修改 | 导航栏改用 `Icon.GAMEFLOW` |
