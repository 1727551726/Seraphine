# 迁移英雄选择功能到游戏流界面

## 功能概述

将辅助功能界面中英雄选择相关的自动化功能迁移至游戏流界面，合并同类功能，删除重复的自动接受对局卡片。

## 实现步骤

1. 将 `AutoAcceptSwapingCard`、`AutoSelectChampionCard`、`AutoBanChampionCard`、`ChampionsCard` 从 `auxiliary_interface.py` 迁移至 `gameflow_interface.py`
2. 在 `gameflow_interface.py` 新增 `bpGroup`（Ban / Pick）分组，包含迁移的卡片
3. 删除 `auxiliary_interface.py` 中的 BP 分组及重复的 `AutoAcceptMatchingCard`
4. 更新 `main_window.py` 添加 `gameflowInterface.initChampionList()` 调用
5. 清理 `auxiliary_interface.py` 中不再使用的导入

## 文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `app/view/gameflow_interface.py` | 修改 | 添加 BP 组及迁移的卡片类 |
| `app/view/auxiliary_interface.py` | 修改 | 删除 BP 组、重复卡片、迁移的类 |
| `app/view/main_window.py` | 修改 | 添加 gameflowInterface.initChampionList() |
