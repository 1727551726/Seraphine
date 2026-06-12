# 自动游戏流功能开发日志

**日期**: 2026-06-13
**开发者**: MiMoCode
**功能**: 自动游戏流模块 (Auto Gameflow)

---

## 一、功能概述

参考 LeagueAkari 项目的设计文档，为 Seraphine 项目新增自动游戏流功能模块，包含以下四个核心功能：

1. **自动接受对局** - 匹配到对局后自动点击接受
2. **自动点赞** - 游戏结束后自动为队友点赞
3. **自动回到房间** - 对局结束后自动返回房间
4. **自动匹配对局** - 满足条件时自动开始匹配

---

## 二、实现步骤

### 2.1 添加配置项 (config.py)

```python
# 自动游戏流配置
enableAutoHonor = ConfigItem("AutoGameflow", "EnableAutoHonor", False, BoolValidator())
autoHonorStrategy = OptionsConfigItem(...)
enableAutoPlayAgain = ConfigItem("AutoGameflow", "EnableAutoPlayAgain", False, BoolValidator())
enableAutoSearchMatch = ConfigItem("AutoGameflow", "EnableAutoSearchMatch", False, BoolValidator())
autoSearchMatchDelay = RangeConfigItem(...)
autoSearchMinimumMembers = RangeConfigItem(...)
autoSearchWaitForInvitees = ConfigItem(...)
autoSearchRematchStrategy = OptionsConfigItem(...)
autoSearchRematchFixedDuration = RangeConfigItem(...)
```

### 2.2 添加 LCU API (connector.py)

新增的 API 方法：
- `getHonorBallot()` - 获取点赞投票信息
- `honorPlayer()` - 执行点赞操作
- `getEogStatus()` - 获取游戏结束状态
- `getLobby()` - 获取房间信息
- `startMatchmaking()` - 开始匹配
- `stopMatchmaking()` - 停止匹配
- `getMatchmakingSearch()` - 获取匹配搜索状态
- `declineMatchMaking()` - 拒绝对局
- `sendChatMessage()` - 发送聊天消息
- `getGameflowPhase()` - 获取游戏流阶段

### 2.3 添加信号 (signals.py)

```python
honorBallotChanged = pyqtSignal(dict)
readyCheckChanged = pyqtSignal(dict)
lobbyChanged = pyqtSignal(dict)
```

### 2.4 添加 WebSocket 事件监听 (connector.py)

```python
@self.listener.subscribe(event='OnJsonApiEvent_lol-honor-v2_v1_ballot', ...)
async def onHonorBallotChanged(event):
    signalBus.honorBallotChanged.emit(event['data'])

@self.listener.subscribe(event='OnJsonApiEvent_lol-matchmaking_v1_ready-check', ...)
async def onReadyCheckChanged(event):
    signalBus.readyCheckChanged.emit(event['data'])

@self.listener.subscribe(event='OnJsonApiEvent_lol-lobby_v2_lobby', ...)
async def onLobbyChanged(event):
    signalBus.lobbyChanged.emit(event['data'])
```

### 2.5 创建界面 (gameflow_interface.py)

创建了以下界面组件：
- `AutoAcceptCard` - 自动接受对局卡片
- `AutoHonorCard` - 自动点赞卡片
- `AutoPlayAgainCard` - 自动回到房间卡片
- `AutoSearchMatchCard` - 自动匹配对局卡片
- `GameflowInterface` - 游戏流主界面

### 2.6 集成到主窗口 (main_window.py)

```python
from app.view.gameflow_interface import GameflowInterface

# 创建界面
self.gameflowInterface = GameflowInterface(self)

# 添加到导航
self.addSubInterface(self.gameflowInterface, Icon.GAME, self.tr("游戏流"), pos)
```

---

## 三、遇到的问题及解决方案

### 3.1 API 方法添加位置错误

**问题**: 将 API 方法添加到了 `JsonManager` 类中，而不是 `LolClientConnector` 类中。

**原因**: `LolClientConnector` 类在 `connector.py` 文件的第 1207 行结束，`JsonManager` 类从第 1208 行开始。

**解决**: 将 API 方法移动到 `LolClientConnector` 类的正确位置。

### 3.2 Icon 属性不存在

**问题**: 使用了 `Icon.HEART`，但 `Icon` 类中没有这个属性。

**解决**: 查看 `Icon` 类定义，使用存在的属性 `Icon.STAROFF` 替代。

### 3.3 界面布局错乱

**问题**: 使用 `ExpandGroupSettingCard` 时，内部元素布局混乱。

**解决**: 参考 `auxiliary_interface.py` 的实现方式，使用标准的布局结构。

### 3.4 开关文本显示问题

**问题**: 默认显示中文，但点击后变回英文。

**原因**: `SwitchSettingCard.setValue()` 方法会重置文本。

**解决**: 重写 `setValue()` 方法，使用中文文本。

### 3.5 Python 中 `&&` 语法不支持

**问题**: PowerShell 不支持 `&&` 运算符。

**解决**: 使用 `;` 分隔命令或使用 PowerShell 条件语法。

---

## 四、经验总结

### 4.1 代码组织

1. **类定义位置**: 在修改大型文件时，需要先了解类的定义位置，避免将方法添加到错误的类中。
2. **模块化设计**: 将界面、配置、API 分离，便于维护和扩展。

### 4.2 PyQt5 开发

1. **信号槽机制**: 使用 `pyqtSignal` 进行组件间通信，避免直接调用。
2. **异步处理**: 使用 `qasync` 和 `asyncio.ensure_future()` 处理异步操作。
3. **国际化**: 使用 `self.tr()` 包装所有用户可见的文本。

### 4.3 界面开发

1. **样式统一**: 参考项目现有的界面风格，保持一致性。
2. **开关组件**: 使用 `SwitchButton` 并设置 `setOnText()` 和 `setOffText()` 实现中文显示。
3. **布局管理**: 使用 `QGridLayout` 和 `QHBoxLayout` 进行精确布局控制。

### 4.4 LCU API 开发

1. **装饰器使用**: 使用 `@retry()` 和 `@needLcu()` 装饰器处理异常和连接检查。
2. **WebSocket 事件**: 通过订阅 WebSocket 事件监听游戏状态变化。
3. **错误处理**: 使用 `try-except` 捕获异常并记录日志。

### 4.5 测试验证

1. **语法检查**: 使用 `python -m py_compile` 检查语法错误。
2. **导入测试**: 验证模块是否可以正确导入。
3. **运行测试**: 启动应用程序验证功能是否正常。

---

## 五、文件变更清单

| 文件 | 变更类型 | 说明 |
|------|----------|------|
| `app/common/config.py` | 修改 | 添加自动游戏流配置项 |
| `app/common/signals.py` | 修改 | 添加新信号 |
| `app/lol/connector.py` | 修改 | 添加 LCU API 和 WebSocket 事件监听 |
| `app/view/gameflow_interface.py` | 新增 | 游戏流界面实现 |
| `app/view/main_window.py` | 修改 | 集成游戏流界面 |

---

## 六、后续优化建议

1. **聊天通知**: 实现匹配倒计时消息发送功能
2. **重匹配策略**: 完善"超过队列预估时间"策略的实现
3. **状态显示**: 添加更详细的当前状态显示
4. **日志记录**: 增强关键操作的日志记录
5. **单元测试**: 添加自动化测试用例

---

*开发完成时间: 2026-06-13*
