# coding:utf-8
import random
import asyncio

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import QWidget, QLabel, QHBoxLayout, QGridLayout
from qasync import asyncSlot

from app.common.config import cfg, qconfig
from app.common.icons import Icon
from app.common.qfluentwidgets import (SettingCardGroup, ExpandLayout,
                                       ComboBox, SpinBox, ExpandGroupSettingCard,
                                       SwitchButton, IndicatorPosition, ConfigItem,
                                       SwitchSettingCard)
from app.common.style_sheet import StyleSheet
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

        self.expandLayout.setSpacing(30)
        self.expandLayout.setContentsMargins(36, 0, 36, 0)
        self.expandLayout.addWidget(self.gameflowGroup)

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
