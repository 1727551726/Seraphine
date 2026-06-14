# coding:utf-8
import random
import asyncio

from PyQt5.QtCore import Qt, QTimer, QSize, QEvent, pyqtSignal
from PyQt5.QtWidgets import (QWidget, QLabel, QHBoxLayout, QGridLayout,
                              QFrame, QSpacerItem, QSizePolicy)
from qasync import asyncSlot

from app.common.config import cfg, qconfig
from app.common.icons import Icon
from app.common.qfluentwidgets import (SettingCardGroup, ExpandLayout,
                                       ComboBox, SpinBox, ExpandGroupSettingCard,
                                       SwitchButton, IndicatorPosition, ConfigItem,
                                       SwitchSettingCard, setCustomStyleSheet,
                                       TransparentToolButton, FluentIcon,
                                       ToolTipFilter, ToolTipPosition,
                                       PushButton)
from app.common.style_sheet import StyleSheet
from app.components.champion_icon_widget import RoundIcon
from app.components.message_box import MultiChampionSelectMsgBox
from app.components.seraphine_interface import SeraphineInterface
from app.lol.connector import connector
from app.common.logger import logger
from app.common.signals import signalBus


class AutoAcceptCard(ExpandGroupSettingCard):

    def __init__(self, title, content, parent):
        super().__init__(Icon.CONNECTION, title, content, parent)

        self.statusLabel = QLabel(self)

        self.inputWidget = QWidget(self.view)
        self.inputLayout = QHBoxLayout(self.inputWidget)

        self.delayLabel = QLabel(self.tr("接受延迟（秒）:"), self)
        self.delaySpinBox = SpinBox(self)

        self.switchButtonWidget = QWidget(self.view)
        self.switchButtonLayout = QHBoxLayout(self.switchButtonWidget)

        self.switchButton = SwitchButton(
            indicatorPos=IndicatorPosition.RIGHT)

        self.__initLayout()
        self.__initWidget()

    def __initLayout(self):
        self.addWidget(self.statusLabel)

        self.inputLayout.setSpacing(19)
        self.inputLayout.setAlignment(Qt.AlignTop)
        self.inputLayout.setContentsMargins(48, 18, 44, 18)

        self.inputLayout.addWidget(
            self.delayLabel, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(
            self.delaySpinBox, alignment=Qt.AlignRight)
        self.inputLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.switchButtonLayout.setContentsMargins(48, 18, 44, 18)
        self.switchButtonLayout.addWidget(
            self.switchButton, 0, Qt.AlignRight)
        self.switchButtonLayout.setSizeConstraint(
            QHBoxLayout.SetMinimumSize)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.inputWidget)
        self.addGroupWidget(self.switchButtonWidget)

    def __initWidget(self):
        self.delaySpinBox.setRange(0, 11)
        self.delaySpinBox.setValue(cfg.get(cfg.autoAcceptMatchingDelay))
        self.delaySpinBox.setSingleStep(1)
        self.delaySpinBox.setMinimumWidth(250)

        self.switchButton.setChecked(cfg.get(cfg.enableAutoAcceptMatching))
        self.switchButton.setOnText(self.tr("开"))
        self.switchButton.setOffText(self.tr("关"))

        self.delaySpinBox.valueChanged.connect(self.__onValueChanged)
        self.switchButton.checkedChanged.connect(
            self.__onSwitchButtonCheckedChanged)

        value, isChecked = self.delaySpinBox.value(), self.switchButton.isChecked()
        self.__setStatusLabelText(value, isChecked)

    def __onSwitchButtonCheckedChanged(self, isChecked: bool):
        qconfig.set(cfg.enableAutoAcceptMatching, isChecked)
        self.__setStatusLabelText(self.delaySpinBox.value(), isChecked)

    def __onValueChanged(self, value):
        qconfig.set(cfg.autoAcceptMatchingDelay, value)
        self.__setStatusLabelText(value, self.switchButton.isChecked())

    def __setStatusLabelText(self, delay, isChecked):
        if isChecked:
            self.statusLabel.setText(
                self.tr("已开启，延迟: ") + str(delay) + self.tr(" 秒"))
        else:
            self.statusLabel.setText(self.tr("已关闭"))


class AutoHonorCard(ExpandGroupSettingCard):

    def __init__(self, title, content, parent):
        super().__init__(Icon.STAROFF, title, content, parent)

        self.statusLabel = QLabel(self)

        self.inputWidget = QWidget(self.view)
        self.inputLayout = QHBoxLayout(self.inputWidget)

        self.strategyLabel = QLabel(self.tr("点赞策略:"), self)
        self.strategyComboBox = ComboBox(self)

        self.switchButtonWidget = QWidget(self.view)
        self.switchButtonLayout = QHBoxLayout(self.switchButtonWidget)

        self.switchButton = SwitchButton(
            indicatorPos=IndicatorPosition.RIGHT)

        self.__initLayout()
        self.__initWidget()

    def __initLayout(self):
        self.addWidget(self.statusLabel)

        self.inputLayout.setSpacing(19)
        self.inputLayout.setAlignment(Qt.AlignTop)
        self.inputLayout.setContentsMargins(48, 18, 44, 18)

        self.inputLayout.addWidget(
            self.strategyLabel, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(
            self.strategyComboBox, alignment=Qt.AlignRight)
        self.inputLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.switchButtonLayout.setContentsMargins(48, 18, 44, 18)
        self.switchButtonLayout.addWidget(
            self.switchButton, 0, Qt.AlignRight)
        self.switchButtonLayout.setSizeConstraint(
            QHBoxLayout.SetMinimumSize)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.inputWidget)
        self.addGroupWidget(self.switchButtonWidget)

    def __initWidget(self):
        self.strategyComboBox.addItems([
            self.tr("优先预组队成员"),
            self.tr("仅预组队成员"),
            self.tr("所有队友"),
            self.tr("所有玩家（含对手）"),
            self.tr("跳过点赞")
        ])

        strategyMap = {
            "prefer-lobby-member": 0,
            "only-lobby-member": 1,
            "all-member": 2,
            "all-member-including-opponent": 3,
            "opt-out": 4
        }
        currentStrategy = cfg.get(cfg.autoHonorStrategy)
        self.strategyComboBox.setCurrentIndex(
            strategyMap.get(currentStrategy, 0))

        self.strategyComboBox.setMinimumWidth(250)

        self.switchButton.setChecked(cfg.get(cfg.enableAutoHonor))
        self.switchButton.setOnText(self.tr("开"))
        self.switchButton.setOffText(self.tr("关"))

        self.strategyComboBox.currentIndexChanged.connect(
            self.__onStrategyChanged)
        self.switchButton.checkedChanged.connect(
            self.__onSwitchButtonCheckedChanged)

        self.__setStatusLabelText(self.switchButton.isChecked())

    def __onSwitchButtonCheckedChanged(self, isChecked: bool):
        qconfig.set(cfg.enableAutoHonor, isChecked)
        self.__setStatusLabelText(isChecked)

    def __onStrategyChanged(self, index):
        strategyMap = {
            0: "prefer-lobby-member",
            1: "only-lobby-member",
            2: "all-member",
            3: "all-member-including-opponent",
            4: "opt-out"
        }
        cfg.set(cfg.autoHonorStrategy,
                strategyMap.get(index, "prefer-lobby-member"))

    def __setStatusLabelText(self, isChecked):
        if isChecked:
            self.statusLabel.setText(self.tr("已开启"))
        else:
            self.statusLabel.setText(self.tr("已关闭"))


class AutoPlayAgainCard(SwitchSettingCard):

    def __init__(self, title, content, parent):
        super().__init__(
            Icon.ARROWCIRCLE,
            title,
            content,
            cfg.enableAutoPlayAgain,
            parent
        )
        self.switchButton.setOnText(self.tr("开"))
        self.switchButton.setOffText(self.tr("关"))
        self.setValue(False)

    def setValue(self, isChecked: bool):
        if self.configItem:
            qconfig.set(self.configItem, isChecked)

        self.switchButton.setChecked(isChecked)
        self.switchButton.setText(
            self.tr('开') if isChecked else self.tr('关'))


class AutoSearchMatchCard(ExpandGroupSettingCard):

    def __init__(self, title, content, parent):
        super().__init__(Icon.SEARCH, title, content, parent)

        self.statusLabel = QLabel(self)

        self.inputWidget = QWidget(self.view)
        self.inputLayout = QGridLayout(self.inputWidget)

        self.delayLabel = QLabel(self.tr("匹配前等待（秒）:"), self)
        self.delaySpinBox = SpinBox(self)

        self.minMembersLabel = QLabel(self.tr("最低人数:"), self)
        self.minMembersSpinBox = SpinBox(self)

        self.waitForInviteesLabel = QLabel(self.tr("等待邀请中的玩家:"), self)
        self.waitForInviteesSwitch = SwitchButton(
            indicatorPos=IndicatorPosition.RIGHT)

        self.rematchStrategyLabel = QLabel(self.tr("停止匹配策略:"), self)
        self.rematchStrategyComboBox = ComboBox(self)

        self.rematchDurationLabel = QLabel(self.tr("固定时间（秒）:"), self)
        self.rematchDurationSpinBox = SpinBox(self)

        self.switchButtonWidget = QWidget(self.view)
        self.switchButtonLayout = QHBoxLayout(self.switchButtonWidget)

        self.switchButton = SwitchButton(
            indicatorPos=IndicatorPosition.RIGHT)

        self.__initLayout()
        self.__initWidget()

    def __initLayout(self):
        self.addWidget(self.statusLabel)

        self.inputLayout.setVerticalSpacing(19)
        self.inputLayout.setAlignment(Qt.AlignTop)
        self.inputLayout.setContentsMargins(48, 18, 44, 18)

        self.inputLayout.addWidget(
            self.delayLabel, 0, 0, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(
            self.delaySpinBox, 0, 1, alignment=Qt.AlignRight)
        self.inputLayout.addWidget(
            self.minMembersLabel, 1, 0, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(
            self.minMembersSpinBox, 1, 1, alignment=Qt.AlignRight)
        self.inputLayout.addWidget(
            self.waitForInviteesLabel, 2, 0, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(
            self.waitForInviteesSwitch, 2, 1, alignment=Qt.AlignRight)
        self.inputLayout.addWidget(
            self.rematchStrategyLabel, 3, 0, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(
            self.rematchStrategyComboBox, 3, 1, alignment=Qt.AlignRight)
        self.inputLayout.addWidget(
            self.rematchDurationLabel, 4, 0, alignment=Qt.AlignLeft)
        self.inputLayout.addWidget(
            self.rematchDurationSpinBox, 4, 1, alignment=Qt.AlignRight)

        self.inputLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.switchButtonLayout.setContentsMargins(48, 18, 44, 18)
        self.switchButtonLayout.addWidget(
            self.switchButton, 0, Qt.AlignRight)
        self.switchButtonLayout.setSizeConstraint(
            QHBoxLayout.SetMinimumSize)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.inputWidget)
        self.addGroupWidget(self.switchButtonWidget)

    def __initWidget(self):
        self.delaySpinBox.setRange(0, 30)
        self.delaySpinBox.setValue(cfg.get(cfg.autoSearchMatchDelay))
        self.delaySpinBox.setSingleStep(1)
        self.delaySpinBox.setMinimumWidth(150)

        self.minMembersSpinBox.setRange(1, 5)
        self.minMembersSpinBox.setValue(
            cfg.get(cfg.autoSearchMinimumMembers))
        self.minMembersSpinBox.setSingleStep(1)
        self.minMembersSpinBox.setMinimumWidth(150)

        self.rematchStrategyComboBox.addItems([
            self.tr("永不"),
            self.tr("固定时间"),
            self.tr("超过队列预估时间")
        ])

        strategyMap = {
            "never": 0,
            "fixed-duration": 1,
            "estimated-duration": 2
        }
        currentStrategy = cfg.get(cfg.autoSearchRematchStrategy)
        self.rematchStrategyComboBox.setCurrentIndex(
            strategyMap.get(currentStrategy, 0))
        self.rematchStrategyComboBox.setMinimumWidth(150)

        self.rematchDurationSpinBox.setRange(1, 10)
        self.rematchDurationSpinBox.setValue(
            cfg.get(cfg.autoSearchRematchFixedDuration))
        self.rematchDurationSpinBox.setSingleStep(1)
        self.rematchDurationSpinBox.setMinimumWidth(150)

        self.switchButton.setChecked(cfg.get(cfg.enableAutoSearchMatch))
        self.switchButton.setOnText(self.tr("开"))
        self.switchButton.setOffText(self.tr("关"))
        self.waitForInviteesSwitch.setChecked(
            cfg.get(cfg.autoSearchWaitForInvitees))
        self.waitForInviteesSwitch.setOnText(self.tr("开"))
        self.waitForInviteesSwitch.setOffText(self.tr("关"))

        self.delaySpinBox.valueChanged.connect(
            lambda v: cfg.set(cfg.autoSearchMatchDelay, v))
        self.minMembersSpinBox.valueChanged.connect(
            lambda v: cfg.set(cfg.autoSearchMinimumMembers, v))
        self.rematchStrategyComboBox.currentIndexChanged.connect(
            self.__onRematchStrategyChanged)
        self.rematchDurationSpinBox.valueChanged.connect(
            lambda v: cfg.set(cfg.autoSearchRematchFixedDuration, v))
        self.waitForInviteesSwitch.checkedChanged.connect(
            lambda v: cfg.set(cfg.autoSearchWaitForInvitees, v))
        self.switchButton.checkedChanged.connect(
            self.__onSwitchButtonCheckedChanged)

        self.rematchDurationLabel.setVisible(
            cfg.get(cfg.autoSearchRematchStrategy) == "fixed-duration")
        self.rematchDurationSpinBox.setVisible(
            cfg.get(cfg.autoSearchRematchStrategy) == "fixed-duration")

        self.__setStatusLabelText(self.switchButton.isChecked())

    def __onSwitchButtonCheckedChanged(self, isChecked: bool):
        qconfig.set(cfg.enableAutoSearchMatch, isChecked)
        self.__setStatusLabelText(isChecked)

    def __onRematchStrategyChanged(self, index):
        strategyMap = {
            0: "never",
            1: "fixed-duration",
            2: "estimated-duration"
        }
        cfg.set(cfg.autoSearchRematchStrategy,
                strategyMap.get(index, "never"))
        self.rematchDurationLabel.setVisible(index == 1)
        self.rematchDurationSpinBox.setVisible(index == 1)

    def __setStatusLabelText(self, isChecked):
        if isChecked:
            self.statusLabel.setText(self.tr("已开启"))
        else:
            self.statusLabel.setText(self.tr("已关闭"))


class AutoAcceptSwapingCard(ExpandGroupSettingCard):
    def __init__(self, title, content, enableCeilSwapItem: ConfigItem = None,
                 enableChampSwapItem: ConfigItem = None, parent=None):
        super().__init__(Icon.TEXTCHECK, title, content, parent)

        self.statusLabel = QLabel(self)

        self.switchButtonWidget = QWidget(self.view)
        self.switchButtonLayout = QGridLayout(self.switchButtonWidget)

        self.label1 = QLabel(self.tr("自动接受楼层交换请求:"))
        self.label2 = QLabel(self.tr("自动接受英雄交易请求:"))

        self.switchButton1 = SwitchButton(indicatorPos=IndicatorPosition.RIGHT)
        self.switchButton2 = SwitchButton(indicatorPos=IndicatorPosition.RIGHT)

        self.enableCeilSwapItem = enableCeilSwapItem
        self.enableChampSwapItem = enableChampSwapItem

        self.__initLayout()
        self.__initWidget()

    def __initLayout(self):
        self.addWidget(self.statusLabel)

        self.switchButtonLayout.setVerticalSpacing(19)
        self.switchButtonLayout.addWidget(self.label1, 0, 0, Qt.AlignLeft)
        self.switchButtonLayout.addWidget(
            self.switchButton1, 0, 1, Qt.AlignRight)
        self.switchButtonLayout.addWidget(
            self.label2, 1, 0, Qt.AlignLeft)
        self.switchButtonLayout.addWidget(
            self.switchButton2, 1, 1, Qt.AlignRight)

        self.switchButtonLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)
        self.switchButtonLayout.setContentsMargins(48, 24, 44, 28)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)
        self.addGroupWidget(self.switchButtonWidget)

    def __initWidget(self):
        ceilSwap = cfg.get(cfg.autoAcceptCeilSwap)
        champTrade = cfg.get(cfg.autoAcceptChampTrade)

        self.switchButton1.setChecked(ceilSwap)
        self.switchButton2.setChecked(champTrade)

        self.__setStatusLableText()

        self.switchButton1.checkedChanged.connect(
            self.__onSwichButton1CheckedChanged)
        self.switchButton2.checkedChanged.connect(
            self.__onSwichButton2CheckedChanged)

    def __onSwichButton1CheckedChanged(self, isChecked: bool):
        cfg.set(cfg.autoAcceptCeilSwap, isChecked)
        self.__setStatusLableText()

    def __onSwichButton2CheckedChanged(self, isChecked: bool):
        cfg.set(cfg.autoAcceptChampTrade, isChecked)
        self.__setStatusLableText()

    def __setStatusLableText(self):
        ceilSwap = self.switchButton1.isChecked()
        champTrade = self.switchButton2.isChecked()

        if any([ceilSwap, champTrade]):
            self.statusLabel.setText(self.tr("已开启"))
        else:
            self.statusLabel.setText(self.tr("已关闭"))


class AutoSelectChampionCard(ExpandGroupSettingCard):
    def __init__(self, title, content=None,
                 enableConfigItem: ConfigItem = None,
                 championsConfigItem: ConfigItem = None,
                 topChampionsConfigItem: ConfigItem = None,
                 jugChampionsConfigItem: ConfigItem = None,
                 midChampionsConfigItem: ConfigItem = None,
                 botChampionsConfigItem: ConfigItem = None,
                 supChampionsConfigItem: ConfigItem = None,
                 enableTimeoutCompleteCfgItem: ConfigItem = None,
                 parent=None):
        super().__init__(Icon.CHECK, title, content, parent)

        self.champions = {}

        self.enableConfigItem = enableConfigItem
        self.defaultChampionsConfigItem = championsConfigItem
        self.topChampionsConfigItem = topChampionsConfigItem
        self.jugChampionsConfigItem = jugChampionsConfigItem
        self.midChampionsConfigItem = midChampionsConfigItem
        self.botChampionsConfigItem = botChampionsConfigItem
        self.supChampionsConfigItem = supChampionsConfigItem
        self.enableTimeoutCompleteCfgItem = enableTimeoutCompleteCfgItem

        self.statusLabel = QLabel()

        self.defaultCfgWidget = QWidget(self.view)
        self.defaultCfgLayout = QGridLayout(self.defaultCfgWidget)
        self.defaultHintLabel = QLabel(self.tr("默认配置"))
        self.helpLayout = QHBoxLayout()
        self.helpButotn = TransparentToolButton(Icon.QUESTION_CIRCLE)

        self.defaultLabel = QLabel(self.tr("默认英雄: "))
        self.defaultChampions = ChampionsCard()
        self.defaultSelectButton = PushButton(self.tr("选择"))

        self.rankCfgWidget = QWidget(self.view)
        self.rankCfgLayout = QGridLayout(self.rankCfgWidget)
        self.rankLabel = QLabel(self.tr("分路配置"))

        self.topLabel = QLabel(self.tr("上单: "))
        self.jugLabel = QLabel(self.tr("打野: "))
        self.midLabel = QLabel(self.tr("中单: "))
        self.botLabel = QLabel(self.tr("下路: "))
        self.supLabel = QLabel(self.tr("辅助: "))
        self.topChampions = ChampionsCard()
        self.jugChampions = ChampionsCard()
        self.midChampions = ChampionsCard()
        self.botChampions = ChampionsCard()
        self.supChampions = ChampionsCard()
        self.topSelectButton = PushButton(self.tr("选择"))
        self.jugSelectButton = PushButton(self.tr("选择"))
        self.midSelectButton = PushButton(self.tr("选择"))
        self.botSelectButton = PushButton(self.tr("选择"))
        self.supSelectButton = PushButton(self.tr("选择"))

        self.buttonsWidget = QWidget(self.view)
        self.buttonsLayout = QGridLayout(self.buttonsWidget)
        self.enableLabel = QLabel(self.tr("启用:"))
        self.enableSwitchButton = SwitchButton(
            indicatorPos=IndicatorPosition.RIGHT)
        self.enableTimeoutCompleteLabel = QLabel(
            self.tr("超时前自动锁定:"))
        self.enableTimeoutSwtichButton = SwitchButton(
            indicatorPos=IndicatorPosition.RIGHT)
        self.resetButton = PushButton(self.tr("重置"))

        self.__initWidget()
        self.__initLayout()

    def __initWidget(self):
        self.defaultHintLabel.setStyleSheet("font: bold")
        self.rankLabel.setStyleSheet("font: bold")

        self.helpButotn.setFixedSize(QSize(26, 26))
        self.helpButotn.setIconSize(QSize(16, 16))

        self.helpButotn.setToolTip(self.tr(
            "必须先设置默认英雄。\n\n如果分路英雄不可用，将使用默认配置。"))
        self.helpButotn.installEventFilter(ToolTipFilter(
            self.helpButotn, 0, ToolTipPosition.RIGHT))

        selected = qconfig.get(self.defaultChampionsConfigItem) != []
        checked = qconfig.get(self.enableConfigItem)
        timeoutChecked = qconfig.get(self.enableTimeoutCompleteCfgItem)

        for ty in ['default', 'top', 'jug', 'mid', 'bot', 'sup']:
            button: PushButton = getattr(self, f"{ty}SelectButton")
            button.setMinimumWidth(100)
            button.clicked.connect(lambda _, t=ty: self.__onButtonClicked(t))

            if ty != 'default':
                button.setEnabled(selected)

        self.enableSwitchButton.checkedChanged.connect(
            self.__onEnableSelectChanged)
        self.enableSwitchButton.setEnabled(selected)
        self.enableSwitchButton.setChecked(checked)

        self.enableTimeoutSwtichButton.checkedChanged.connect(
            self.__onEnableTimeoutCompleteChanged)
        self.enableTimeoutSwtichButton.setEnabled(checked)
        self.enableTimeoutSwtichButton.setChecked(timeoutChecked)

        self.resetButton.clicked.connect(self.__onResetButtonClicked)
        self.resetButton.setMinimumWidth(100)

        self.__updateStatusLabel()

    def __initLayout(self):
        self.addWidget(self.statusLabel)

        self.defaultCfgLayout.setVerticalSpacing(19)
        self.defaultCfgLayout.setContentsMargins(48, 18, 44, 18)
        self.defaultCfgLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.helpLayout.setContentsMargins(0, 0, 0, 0)
        self.helpLayout.setSpacing(10)
        self.helpLayout.addWidget(self.defaultHintLabel)
        self.helpLayout.addWidget(self.helpButotn)

        self.defaultCfgLayout.addLayout(
            self.helpLayout, 0, 0, Qt.AlignLeft)

        self.defaultCfgLayout.addWidget(
            self.defaultLabel, 1, 0, Qt.AlignLeft)
        self.defaultCfgLayout.addWidget(
            self.defaultChampions, 1, 1, Qt.AlignHCenter)
        self.defaultCfgLayout.addWidget(
            self.defaultSelectButton, 1, 2, Qt.AlignRight)

        self.rankCfgLayout.setVerticalSpacing(19)
        self.rankCfgLayout.setContentsMargins(48, 18, 44, 18)
        self.rankCfgLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.rankCfgLayout.addWidget(self.rankLabel, 0, 0, Qt.AlignLeft)

        for i, ty in enumerate(['top', 'jug', 'mid', 'bot', 'sup']):
            label = getattr(self, f"{ty}Label")
            champions = getattr(self, f"{ty}Champions")
            button = getattr(self, f"{ty}SelectButton")

            self.rankCfgLayout.addWidget(label, i + 1, 0, Qt.AlignLeft)
            self.rankCfgLayout.addWidget(champions, i + 1, 1, Qt.AlignHCenter)
            self.rankCfgLayout.addWidget(button, i + 1, 2, Qt.AlignRight)

        self.buttonsLayout.setVerticalSpacing(19)
        self.buttonsLayout.setContentsMargins(48, 18, 44, 18)
        self.buttonsLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.buttonsLayout.addWidget(
            self.enableLabel, 0, 0, Qt.AlignLeft)
        self.buttonsLayout.addWidget(
            self.enableSwitchButton, 0, 1, Qt.AlignRight)
        self.buttonsLayout.addWidget(
            self.enableTimeoutCompleteLabel, 1, 0, Qt.AlignLeft)
        self.buttonsLayout.addWidget(
            self.enableTimeoutSwtichButton, 1, 1, Qt.AlignRight)
        self.buttonsLayout.addWidget(
            self.resetButton, 2, 1, Qt.AlignRight)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)

        self.addGroupWidget(self.defaultCfgWidget)
        self.addGroupWidget(self.rankCfgWidget)
        self.addGroupWidget(self.buttonsWidget)

    async def initChampionList(self, champions: dict = None):
        if champions:
            self.champions = champions
        else:
            self.champions = {
                i: [name, await connector.getChampionIcon(i)]
                for i, name in connector.manager.getChampions().items()
                if i != -1
            }

        for ty in ['default', 'top', 'jug', 'mid', 'bot', 'sup']:
            configItem = getattr(self, f"{ty}ChampionsConfigItem")
            champions: ChampionsCard = getattr(self, f"{ty}Champions")
            selected = qconfig.get(configItem)

            champions.clearRequested.connect(
                lambda t=ty: self.__onChampionsChanged([], t))

            if not (type(selected) is list and all(type(s) is int for s in selected)):
                selected = []
                qconfig.set(configItem, selected)

            if len(selected) == 0:
                continue

            champions.updateChampions(
                [self.champions[id][1] for id in selected])

        return self.champions

    def __onButtonClicked(self, type: str):
        configItem: ConfigItem = getattr(self, f"{type}ChampionsConfigItem")
        selected = qconfig.get(configItem)

        box = MultiChampionSelectMsgBox(
            self.champions, selected, self.window())
        box.completed.connect(
            lambda champions, t=type: self.__onChampionsChanged(champions, t))
        box.exec()

    def __onChampionsChanged(self, champions: list, type: str):
        configItem = getattr(self, f"{type}ChampionsConfigItem")
        qconfig.set(configItem, champions)

        card: ChampionsCard = getattr(self, f"{type}Champions")
        card.updateChampions(
            [self.champions[id][1] for id in champions])

        if type != 'default':
            return

        if len(champions) == 0:
            self.enableSwitchButton.setChecked(False)
            self.enableSwitchButton.setEnabled(False)
            self.enableTimeoutSwtichButton.setChecked(False)
            self.enableTimeoutSwtichButton.setEnabled(False)
            buttonEnable = False
        else:
            self.enableSwitchButton.setEnabled(True)
            buttonEnable = True

        for ty in ['top', 'jug', 'mid', 'bot', 'sup']:
            button: PushButton = getattr(self, f"{ty}SelectButton")
            button.setEnabled(buttonEnable)

    def __onEnableSelectChanged(self, checked):
        qconfig.set(self.enableConfigItem, checked)

        for ty in ['default', 'top', 'jug', 'mid', 'bot', 'sup']:
            button: PushButton = getattr(self, f"{ty}SelectButton")
            button.setEnabled(not checked)

        self.enableTimeoutSwtichButton.setEnabled(checked)

        if not checked:
            self.enableTimeoutSwtichButton.setChecked(False)

        self.__updateStatusLabel()

    def __onEnableTimeoutCompleteChanged(self, checked):
        qconfig.set(self.enableTimeoutCompleteCfgItem, checked)

    def __updateStatusLabel(self):
        checked = self.enableSwitchButton.isChecked()

        text = self.tr("已开启") if checked else self.tr("已关闭")
        self.statusLabel.setText(text)

    def __onResetButtonClicked(self):
        for ty in ['default', 'top', 'jug', 'mid', 'bot', 'sup']:
            self.__onChampionsChanged([], ty)


class AutoBanChampionCard(ExpandGroupSettingCard):
    def __init__(self, title, content=None,
                 enableConfigItem: ConfigItem = None,
                 championsConfigItem: ConfigItem = None,
                 topChampionsConfigItem: ConfigItem = None,
                 jugChampionsConfigItem: ConfigItem = None,
                 midChampionsConfigItem: ConfigItem = None,
                 botChampionsConfigItem: ConfigItem = None,
                 supChampionsConfigItem: ConfigItem = None,
                 friendlyConfigItem: ConfigItem = None,
                 delayTimeConfigItem: ConfigItem = None, parent=None):
        super().__init__(Icon.SQUARECROSS, title, content, parent)

        self.champions = {}

        self.enableConfigItem = enableConfigItem
        self.defaultChampionsConfigItem = championsConfigItem
        self.topChampionsConfigItem = topChampionsConfigItem
        self.jugChampionsConfigItem = jugChampionsConfigItem
        self.midChampionsConfigItem = midChampionsConfigItem
        self.botChampionsConfigItem = botChampionsConfigItem
        self.supChampionsConfigItem = supChampionsConfigItem

        self.friendlyConfigItem = friendlyConfigItem
        self.delayTimeConfigItem = delayTimeConfigItem

        self.statusLabel = QLabel()

        self.defaultCfgWidget = QWidget(self.view)
        self.defaultCfgLayout = QGridLayout(self.defaultCfgWidget)
        self.defaultHintLabel = QLabel(self.tr("默认配置"))
        self.helpLayout = QHBoxLayout()
        self.helpButotn = TransparentToolButton(Icon.QUESTION_CIRCLE)

        self.defaultLabel = QLabel(self.tr("默认英雄: "))
        self.defaultChampions = ChampionsCard()
        self.defaultSelectButton = PushButton(self.tr("选择"))

        self.rankCfgWidget = QWidget(self.view)
        self.rankCfgLayout = QGridLayout(self.rankCfgWidget)
        self.rankLabel = QLabel(self.tr("分路配置"))

        self.topLabel = QLabel(self.tr("上单: "))
        self.jugLabel = QLabel(self.tr("打野: "))
        self.midLabel = QLabel(self.tr("中单: "))
        self.botLabel = QLabel(self.tr("下路: "))
        self.supLabel = QLabel(self.tr("辅助: "))
        self.topChampions = ChampionsCard()
        self.jugChampions = ChampionsCard()
        self.midChampions = ChampionsCard()
        self.botChampions = ChampionsCard()
        self.supChampions = ChampionsCard()
        self.topSelectButton = PushButton(self.tr("选择"))
        self.jugSelectButton = PushButton(self.tr("选择"))
        self.midSelectButton = PushButton(self.tr("选择"))
        self.botSelectButton = PushButton(self.tr("选择"))
        self.supSelectButton = PushButton(self.tr("选择"))

        self.buttonsCfgWidget = QWidget(self.view)
        self.buttonsCfgLayout = QGridLayout(self.buttonsCfgWidget)
        self.delayLabel = QLabel(self.tr("禁用延迟（秒）:"))
        self.delaySpinBox = SpinBox()
        self.enableLabel = QLabel(self.tr("启用:"))
        self.enableSwitchButton = SwitchButton(
            indicatorPos=IndicatorPosition.RIGHT)
        self.friendlyLabel = QLabel(
            self.tr("防止禁用队友预选的英雄:"))
        self.friendlySwitchButton = SwitchButton(
            indicatorPos=IndicatorPosition.RIGHT)

        self.resetButton = PushButton(self.tr("重置"))

        self.__initWidget()
        self.__initLayout()

    def __initWidget(self):
        self.defaultHintLabel.setStyleSheet("font: bold")
        self.rankLabel.setStyleSheet("font: bold")

        haveDefault = qconfig.get(self.defaultChampionsConfigItem) != []
        enabled = qconfig.get(self.enableConfigItem)
        delayTime = qconfig.get(self.delayTimeConfigItem)
        friendlyEnabled = qconfig.get(self.friendlyConfigItem)

        self.helpButotn.setFixedSize(QSize(26, 26))
        self.helpButotn.setIconSize(QSize(16, 16))

        self.helpButotn.setToolTip(self.tr(
            "必须先设置默认英雄。\n\n如果分路英雄不可用，将使用默认配置。"))
        self.helpButotn.installEventFilter(ToolTipFilter(
            self.helpButotn, 0, ToolTipPosition.RIGHT))

        for ty in ['default', 'top', 'jug', 'mid', 'bot', 'sup']:
            button: PushButton = getattr(self, f"{ty}SelectButton")
            button.setMinimumWidth(100)
            button.clicked.connect(lambda _, t=ty: self.__onButtonClicked(t))

            if ty != 'default':
                button.setEnabled(haveDefault)

        self.enableSwitchButton.checkedChanged.connect(
            self.__onEnableSwitchButtonClicked)
        self.delaySpinBox.valueChanged.connect(
            self.__onDelaySpinBoxValueChanged)
        self.friendlySwitchButton.checkedChanged.connect(
            self.__onFriendlySwitchButtonClicked)
        self.resetButton.clicked.connect(self.__onResetButtonClicked)

        self.delaySpinBox.setMinimumWidth(250)
        self.delaySpinBox.setSingleStep(1)
        self.delaySpinBox.setRange(0, 25)
        self.delaySpinBox.setEnabled(haveDefault and not enabled)
        self.delaySpinBox.setValue(delayTime)
        self.enableSwitchButton.setEnabled(haveDefault)
        self.enableSwitchButton.setChecked(enabled)
        self.friendlySwitchButton.setEnabled(enabled)
        self.friendlySwitchButton.setChecked(friendlyEnabled)
        self.resetButton.setMinimumWidth(100)

        self.__updateStatusLabel()
        self.__fixStyleSheetOfSpinBox()

    def __initLayout(self):
        self.addWidget(self.statusLabel)

        self.defaultCfgLayout.setVerticalSpacing(19)
        self.defaultCfgLayout.setContentsMargins(48, 18, 44, 18)
        self.defaultCfgLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.helpLayout.setContentsMargins(0, 0, 0, 0)
        self.helpLayout.setSpacing(10)
        self.helpLayout.addWidget(self.defaultHintLabel)
        self.helpLayout.addWidget(self.helpButotn)

        self.defaultCfgLayout.addLayout(
            self.helpLayout, 0, 0, Qt.AlignLeft)

        self.defaultCfgLayout.addWidget(
            self.defaultLabel, 1, 0, Qt.AlignLeft)
        self.defaultCfgLayout.addWidget(
            self.defaultChampions, 1, 1, Qt.AlignHCenter)
        self.defaultCfgLayout.addWidget(
            self.defaultSelectButton, 1, 2, Qt.AlignRight)

        self.rankCfgLayout.setVerticalSpacing(19)
        self.rankCfgLayout.setContentsMargins(48, 18, 44, 18)
        self.rankCfgLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.rankCfgLayout.addWidget(self.rankLabel, 0, 0, Qt.AlignLeft)

        for i, ty in enumerate(['top', 'jug', 'mid', 'bot', 'sup']):
            label = getattr(self, f"{ty}Label")
            champions = getattr(self, f"{ty}Champions")
            button = getattr(self, f"{ty}SelectButton")

            self.rankCfgLayout.addWidget(label, i + 1, 0, Qt.AlignLeft)
            self.rankCfgLayout.addWidget(champions, i + 1, 1, Qt.AlignHCenter)
            self.rankCfgLayout.addWidget(button, i + 1, 2, Qt.AlignRight)

        self.buttonsCfgLayout.setVerticalSpacing(19)
        self.buttonsCfgLayout.setContentsMargins(48, 18, 44, 18)
        self.buttonsCfgLayout.setSizeConstraint(QHBoxLayout.SetMinimumSize)

        self.buttonsCfgLayout.addWidget(
            self.delayLabel, 0, 0, Qt.AlignLeft)
        self.buttonsCfgLayout.addWidget(
            self.delaySpinBox, 0, 1, Qt.AlignRight)
        self.buttonsCfgLayout.addWidget(
            self.enableLabel, 1, 0, Qt.AlignLeft)
        self.buttonsCfgLayout.addWidget(
            self.enableSwitchButton, 1, 1, Qt.AlignRight)
        self.buttonsCfgLayout.addWidget(
            self.friendlyLabel, 2, 0, Qt.AlignLeft)
        self.buttonsCfgLayout.addWidget(
            self.friendlySwitchButton, 2, 1, Qt.AlignRight)
        self.buttonsCfgLayout.addWidget(
            self.resetButton, 3, 1, Qt.AlignRight)

        self.viewLayout.setSpacing(0)
        self.viewLayout.setContentsMargins(0, 0, 0, 0)

        self.addGroupWidget(self.defaultCfgWidget)
        self.addGroupWidget(self.rankCfgWidget)
        self.addGroupWidget(self.buttonsCfgWidget)

    async def initChampionList(self, champions: dict = None):
        if champions:
            self.champions = champions
        else:
            self.champions = {
                i: [name, await connector.getChampionIcon(i)]
                for i, name in connector.manager.getChampions().items()
                if i != -1
            }

        for ty in ['default', 'top', 'jug', 'mid', 'bot', 'sup']:
            configItem = getattr(self, f"{ty}ChampionsConfigItem")
            champions: ChampionsCard = getattr(self, f"{ty}Champions")
            selected = qconfig.get(configItem)

            champions.clearRequested.connect(
                lambda t=ty: self.__onChampionsChanged([], t))

            if not (type(selected) is list and all(type(s) is int for s in selected)):
                selected = []
                qconfig.set(configItem, selected)

            if len(selected) == 0:
                continue

            champions.updateChampions(
                [self.champions[id][1] for id in selected])

        return self.champions

    def __onButtonClicked(self, type: str):
        configItem: ConfigItem = getattr(self, f"{type}ChampionsConfigItem")
        selected = qconfig.get(configItem)

        box = MultiChampionSelectMsgBox(
            self.champions, selected, self.window())
        box.completed.connect(
            lambda champions, t=type: self.__onChampionsChanged(champions, t))
        box.exec()

    def __onChampionsChanged(self, champions: list, type: str):
        configItem = getattr(self, f"{type}ChampionsConfigItem")
        qconfig.set(configItem, champions)

        card: ChampionsCard = getattr(self, f"{type}Champions")
        card.updateChampions(
            [self.champions[id][1] for id in champions])

        if type != 'default':
            return

        if len(champions) == 0:
            self.enableSwitchButton.setChecked(False)
            self.enableSwitchButton.setEnabled(False)
            self.friendlySwitchButton.setChecked(False)
            self.friendlySwitchButton.setEnabled(False)
            self.delaySpinBox.setEnabled(False)
            buttonEnable = False
        else:
            self.enableSwitchButton.setEnabled(True)
            self.delaySpinBox.setEnabled(True)
            buttonEnable = True

        for ty in ['top', 'jug', 'mid', 'bot', 'sup']:
            button: PushButton = getattr(self, f"{ty}SelectButton")
            button.setEnabled(buttonEnable)

    def __onEnableSwitchButtonClicked(self, checked):
        qconfig.set(self.enableConfigItem, checked)

        for ty in ['default', 'top', 'jug', 'mid', 'bot', 'sup']:
            button: PushButton = getattr(self, f"{ty}SelectButton")
            button.setEnabled(not checked)

        self.friendlySwitchButton.setEnabled(checked)
        self.delaySpinBox.setEnabled(not checked)

        if not checked:
            self.friendlySwitchButton.setChecked(False)

        self.__updateStatusLabel()

    def __onDelaySpinBoxValueChanged(self, value):
        qconfig.set(self.delayTimeConfigItem, value)

    def __onFriendlySwitchButtonClicked(self, checked):
        qconfig.set(self.friendlyConfigItem, checked)

    def __onResetButtonClicked(self):
        for ty in ['default', 'top', 'jug', 'mid', 'bot', 'sup']:
            self.__onChampionsChanged([], ty)

        self.delaySpinBox.setValue(0)

    def __updateStatusLabel(self):
        checked = self.enableSwitchButton.isChecked()

        text = self.tr("已开启") if checked else self.tr("已关闭")
        self.statusLabel.setText(text)

    def __fixStyleSheetOfSpinBox(self):
        light = """
            SpinBox:disabled {
                color: rgba(0, 0, 0, 150);
                background-color: rgba(249, 249, 249, 0.3);
                border: 1px solid rgba(0, 0, 0, 13);
                border-bottom: 1px solid rgba(0, 0, 0, 13);
            }
        """

        dark = """
            SpinBox:disabled {
                color: rgba(255, 255, 255, 150);
                background-color: rgba(255, 255, 255, 0.0419);
                border: 1px solid rgba(255, 255, 255, 0.0698);
            }
        """

        setCustomStyleSheet(self.delaySpinBox, light, dark)


class ChampionsCard(QFrame):
    clearRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.hBoxLayout = QHBoxLayout(self)
        self.hBoxLayout.setContentsMargins(2, 0, 4, 0)
        self.hBoxLayout.setAlignment(Qt.AlignCenter)

        self.iconLayout = QHBoxLayout()
        self.iconLayout.setContentsMargins(6, 6, 0, 6)
        self.clearButton = TransparentToolButton(FluentIcon.CLOSE)
        self.clearButton.setFixedSize(28, 28)
        self.clearButton.setIconSize(QSize(15, 15))
        self.clearButton.setVisible(False)
        self.clearButton.clicked.connect(self.clearRequested)

        self.hBoxLayout.addLayout(self.iconLayout)
        self.hBoxLayout.addItem(QSpacerItem(
            0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed))
        self.hBoxLayout.addWidget(self.clearButton, alignment=Qt.AlignVCenter)

        self.setFixedWidth(250)
        self.setFixedHeight(42)

    def updateChampions(self, champions):
        self.clear()

        for icon in champions:
            icon = RoundIcon(icon, 28, 2, 2)
            self.iconLayout.addWidget(icon, alignment=Qt.AlignVCenter)

    def clear(self):
        for i in reversed(range(self.iconLayout.count())):
            item = self.iconLayout.itemAt(i)
            self.iconLayout.removeItem(item)

            if item.widget():
                item.widget().deleteLater()

    def enterEvent(self, a0: QEvent) -> None:
        self.clearButton.setVisible(True)
        return super().enterEvent(a0)

    def leaveEvent(self, a0: QEvent) -> None:
        self.clearButton.setVisible(False)
        return super().leaveEvent(a0)


class GameflowInterface(SeraphineInterface):

    def __init__(self, parent=None):
        super().__init__(parent)

        self.scrollWidget = QWidget()
        self.expandLayout = ExpandLayout(self.scrollWidget)

        self.titleLabel = QLabel(self.tr("游戏流"), self)

        self.gameflowGroup = SettingCardGroup(
            self.tr("自动化"), self.scrollWidget)

        self.autoAcceptCard = AutoAcceptCard(
            self.tr("自动接受对局"),
            self.tr("匹配到对局后自动点击接受"),
            self.gameflowGroup
        )

        self.autoHonorCard = AutoHonorCard(
            self.tr("自动点赞"),
            self.tr("游戏结束后自动为队友点赞"),
            self.gameflowGroup
        )

        self.autoPlayAgainCard = AutoPlayAgainCard(
            self.tr("自动回到房间"),
            self.tr("对局结束后自动返回房间"),
            self.gameflowGroup
        )

        self.autoSearchMatchCard = AutoSearchMatchCard(
            self.tr("自动匹配对局"),
            self.tr("满足条件时自动开始匹配"),
            self.gameflowGroup
        )

        self.bpGroup = SettingCardGroup(
            self.tr("Ban / Pick"), self.scrollWidget)

        self.autoAcceptSwapingCard = AutoAcceptSwapingCard(
            self.tr("自动接受交换"),
            self.tr("自动接受楼层交换或英雄交易请求"),
            cfg.autoAcceptCeilSwap, cfg.autoAcceptChampTrade,
            self.bpGroup)
        self.autoSelectChampionCard = AutoSelectChampionCard(
            self.tr("自动选用英雄"),
            self.tr("选用阶段自动选择预设英雄"),
            cfg.enableAutoSelectChampion,
            cfg.autoSelectChampion,
            cfg.autoSelectChampionTop,
            cfg.autoSelectChampionJug,
            cfg.autoSelectChampionMid,
            cfg.autoSelectChampionBot,
            cfg.autoSelectChampionSup,
            cfg.enableAutoSelectTimeoutCompleted,
            self.bpGroup)
        self.autoBanChampionsCard = AutoBanChampionCard(
            self.tr("自动禁用英雄"),
            self.tr("禁用阶段自动禁用预设英雄"),
            cfg.enableAutoBanChampion,
            cfg.autoBanChampion,
            cfg.autoBanChampionTop,
            cfg.autoBanChampionJug,
            cfg.autoBanChampionMid,
            cfg.autoBanChampionBot,
            cfg.autoBanChampionSup,
            cfg.pretentBan,
            cfg.autoBanDelay,
            self.bpGroup)

        self.playAgainTimer = QTimer(self)
        self.playAgainTimer.setSingleShot(True)
        self.playAgainTimer.timeout.connect(self.__onPlayAgainTimeout)

        self.searchMatchTimer = QTimer(self)
        self.searchMatchTimer.setSingleShot(True)
        self.searchMatchTimer.timeout.connect(self.__onSearchMatchTimeout)

        self.acceptTimer = QTimer(self)
        self.acceptTimer.setSingleShot(True)
        self.acceptTimer.timeout.connect(self.__onAcceptTimeout)

        self.__initWidget()
        self.__initLayout()
        self.__connectSignalToSlot()

    def __initWidget(self):
        self.titleLabel.setObjectName("titleLabel")
        self.scrollWidget.setObjectName('scrollWidget')

        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setViewportMargins(0, 90, 0, 20)
        self.setWidget(self.scrollWidget)
        self.setWidgetResizable(True)

        StyleSheet.AUXILIARY_INTERFACE.apply(self)

    def __initLayout(self):
        self.titleLabel.move(36, 30)

        self.gameflowGroup.addSettingCard(self.autoAcceptCard)
        self.gameflowGroup.addSettingCard(self.autoHonorCard)
        self.gameflowGroup.addSettingCard(self.autoPlayAgainCard)
        self.gameflowGroup.addSettingCard(self.autoSearchMatchCard)

        self.bpGroup.addSettingCard(self.autoAcceptSwapingCard)
        self.bpGroup.addSettingCard(self.autoSelectChampionCard)
        self.bpGroup.addSettingCard(self.autoBanChampionsCard)

        self.expandLayout.setSpacing(30)
        self.expandLayout.setContentsMargins(36, 0, 36, 0)
        self.expandLayout.addWidget(self.gameflowGroup)
        self.expandLayout.addWidget(self.bpGroup)

    async def initChampionList(self):
        champions = await self.autoSelectChampionCard.initChampionList()
        await self.autoBanChampionsCard.initChampionList(champions)
        return champions

    def __connectSignalToSlot(self):
        signalBus.gameStatusChanged.connect(self.__onGameStatusChanged)
        signalBus.honorBallotChanged.connect(self.__onHonorBallotChanged)
        signalBus.readyCheckChanged.connect(self.__onReadyCheckChanged)
        signalBus.lobbyChanged.connect(self.__onLobbyChanged)

    def __onGameStatusChanged(self, status):
        if status in ["WaitingForStats", "PreEndOfGame", "EndOfGame"]:
            if cfg.get(cfg.enableAutoPlayAgain):
                self.playAgainTimer.start(10000)

    def __onHonorBallotChanged(self, ballot):
        if not cfg.get(cfg.enableAutoHonor):
            return

        if ballot is None:
            return

        self.playAgainTimer.stop()
        asyncio.ensure_future(self.__doAutoHonor(ballot))

    async def __doAutoHonor(self, ballot):
        try:
            strategy = cfg.get(cfg.autoHonorStrategy)

            if strategy == "opt-out":
                await connector.honorPlayer(ballot['gameId'], "OPT_OUT", 0)
                return

            eligibleAllies = ballot.get('eligibleAllies', [])
            eligibleOpponents = ballot.get('eligibleOpponents', [])

            if not eligibleAllies and not eligibleOpponents:
                return

            target = None

            if strategy == "prefer-lobby-member":
                target = await self.__findLobbyMember(eligibleAllies)
                if target is None and eligibleAllies:
                    target = random.choice(eligibleAllies)

            elif strategy == "only-lobby-member":
                target = await self.__findLobbyMember(eligibleAllies)

            elif strategy == "all-member":
                if eligibleAllies:
                    target = random.choice(eligibleAllies)

            elif strategy == "all-member-including-opponent":
                allPlayers = eligibleAllies + eligibleOpponents
                if allPlayers:
                    target = random.choice(allPlayers)

            if target:
                categories = ["COOL", "SHOTCALLER", "HEART"]
                category = random.choice(categories)
                await connector.honorPlayer(
                    ballot['gameId'], category, target['summonerId'])

        except Exception as e:
            logger.error(f"自动点赞失败: {e}", "GameflowInterface")

        if cfg.get(cfg.enableAutoPlayAgain):
            self.playAgainTimer.start(1575)

    async def __findLobbyMember(self, eligiblePlayers):
        try:
            eogStatus = await connector.getEogStatus()
            lobbyMembersPuuid = eogStatus.get('eogPlayers', [])

            if not lobbyMembersPuuid:
                return None

            for player in eligiblePlayers:
                summoner = await connector.getSummonerByPuuid(
                    player.get('puuid', ''))
                if summoner and summoner.get('puuid', '') in lobbyMembersPuuid:
                    return player

            return None

        except Exception:
            return None

    def __onReadyCheckChanged(self, readyCheck):
        if not cfg.get(cfg.enableAutoAcceptMatching):
            return

        if readyCheck is None:
            return

        state = readyCheck.get('state', '')
        if state == 'InProgress':
            playerResponse = readyCheck.get('playerResponse', '')
            if playerResponse == 'None':
                delay = cfg.get(cfg.autoAcceptMatchingDelay) * 1000
                self.acceptTimer.start(delay)
            else:
                self.acceptTimer.stop()
        else:
            self.acceptTimer.stop()

    def __onAcceptTimeout(self):
        asyncio.ensure_future(connector.acceptMatchMaking())

    def __onPlayAgainTimeout(self):
        asyncio.ensure_future(connector.playAgain())

    def __onLobbyChanged(self, lobby):
        if not cfg.get(cfg.enableAutoSearchMatch):
            return

        if lobby is None:
            return

        asyncio.ensure_future(self.__checkAutoSearchMatch(lobby))

    async def __checkAutoSearchMatch(self, lobby):
        try:
            canStart = lobby.get('canStartActivity', False)
            if not canStart:
                self.searchMatchTimer.stop()
                return

            localMember = lobby.get('localMember', {})
            isLeader = localMember.get('isLeader', False)
            if not isLeader:
                self.searchMatchTimer.stop()
                return

            members = lobby.get('members', [])
            minMembers = cfg.get(cfg.autoSearchMinimumMembers)
            if len(members) < minMembers:
                self.searchMatchTimer.stop()
                return

            if cfg.get(cfg.autoSearchWaitForInvitees):
                invitations = lobby.get('invitations', [])
                hasPending = any(
                    inv.get('state') == 'Pending' for inv in invitations)
                if hasPending:
                    self.searchMatchTimer.stop()
                    return

            searchState = await connector.getMatchmakingSearch()
            if searchState:
                if searchState.get('isCurrentlyInQueue', False):
                    return

                lowPriorityData = searchState.get('lowPriorityData', {})
                penaltyTime = lowPriorityData.get('penaltyTimeRemaining', 0)
                if penaltyTime > 0:
                    self.searchMatchTimer.stop()
                    return

            delay = cfg.get(cfg.autoSearchMatchDelay)
            await self.__sendCountdownMessage(delay)
            self.searchMatchTimer.start(delay * 1000)

        except Exception as e:
            logger.error(f"自动匹配检查失败: {e}", "GameflowInterface")

    def __onSearchMatchTimeout(self):
        asyncio.ensure_future(self.__startMatchWithRematchStrategy())

    async def __startMatchWithRematchStrategy(self):
        try:
            await connector.startMatchmaking()

            strategy = cfg.get(cfg.autoSearchRematchStrategy)
            if strategy == "never":
                return

            if strategy == "fixed-duration":
                duration = cfg.get(cfg.autoSearchRematchFixedDuration)
                await asyncio.sleep(duration)
                await connector.stopMatchmaking()

            elif strategy == "estimated-duration":
                searchState = await connector.getMatchmakingSearch()
                if searchState:
                    estimatedTime = searchState.get(
                        'estimatedQueueTime', 0)
                    await asyncio.sleep(estimatedTime)
                    await connector.stopMatchmaking()

        except Exception as e:
            logger.error(f"自动匹配失败: {e}", "GameflowInterface")

    async def __sendCountdownMessage(self, seconds):
        try:
            lobby = await connector.getLobby()
            if lobby:
                partyId = lobby.get('partyId', '')
                if partyId:
                    message = f"[Seraphine] 将在 {seconds} 秒后自动匹配"
                    await connector.sendChatMessage(partyId, message)
        except Exception as e:
            logger.error(f"发送倒计时消息失败: {e}", "GameflowInterface")
