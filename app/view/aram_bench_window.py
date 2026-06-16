import os
import asyncio
from qasync import asyncSlot
from PyQt5.QtGui import QColor, QPainter, QIcon, QPixmap, QCursor, QFont
from PyQt5.QtCore import Qt, pyqtSignal, QTimer, QSize, QRectF
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QGridLayout, QSpacerItem, QSizePolicy, QFrame,
                             QProgressBar, QApplication)

from app.common.config import qconfig, cfg
from app.common.logger import logger
from app.common.style_sheet import StyleSheet
from app.common.qfluentwidgets import (FramelessWindow, isDarkTheme, BackgroundAnimationWidget,
                                       FluentTitleBar, BodyLabel, SwitchButton, IndicatorPosition,
                                       PushButton)
from app.lol.connector import connector
from app.components.champion_icon_widget import RoundIcon
from app.view.opgg_window import OpggWindowBase

TAG = 'AramBenchWindow'


class ClickableChampionIcon(QFrame):
    """可点击的英雄图标，正方形显示"""
    clicked = pyqtSignal(int)  # 发出 championId

    def __init__(self, championId: int, iconPath: str, size: int = 56, parent=None):
        super().__init__(parent)
        self.championId = championId
        self.iconPath = iconPath
        self.size = size
        self.hovered = False

        self.setFixedSize(size, size)
        self.setCursor(QCursor(Qt.PointingHandCursor))

        # 加载图片
        self.pixmap = QPixmap(iconPath)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 绘制背景
        if self.hovered:
            painter.setBrush(QColor(255, 255, 255, 30))
        else:
            painter.setBrush(QColor(0, 0, 0, 60))
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(self.rect(), 6, 6)

        # 绘制图片
        if not self.pixmap.isNull():
            margin = 4
            targetRect = QRectF(margin, margin, self.size - 2 * margin, self.size - 2 * margin)
            sourceRect = QRectF(0, 0, self.pixmap.width(), self.pixmap.height())
            painter.drawPixmap(targetRect, self.pixmap, sourceRect)

        # 绘制边框
        if self.hovered:
            painter.setPen(QColor(255, 255, 255, 150))
        else:
            painter.setPen(QColor(255, 255, 255, 50))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(self.rect().adjusted(1, 1, -1, -1), 6, 6)

    def enterEvent(self, event):
        self.hovered = True
        self.update()

    def leaveEvent(self, event):
        self.hovered = False
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit(self.championId)


class AramBenchWindow(OpggWindowBase):
    """大乱斗备选池窗口"""

    def __init__(self, parent=None):
        super().__init__()

        self.vBoxLayout = QVBoxLayout(self)

        # 期望英雄显示区域
        self.desiredWidget = QWidget()
        self.desiredLayout = QHBoxLayout(self.desiredWidget)
        self.desiredLabel = QLabel(self.tr("期望英雄:"))
        self.desiredIconsLayout = QHBoxLayout()
        self.desiredIconsLayout.setSpacing(4)

        # 备选池英雄展示区域
        self.benchWidget = QWidget()
        self.benchLayout = QGridLayout(self.benchWidget)
        self.benchLayout.setSpacing(8)
        self.benchLayout.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        # 倒计时进度条
        self.timerWidget = QWidget()
        self.timerLayout = QVBoxLayout(self.timerWidget)
        self.timerLabel = QLabel(self.tr("剩余时间: --"))
        self.progressBar = QProgressBar()
        self.progressBar.setFixedHeight(8)
        self.progressBar.setTextVisible(False)

        # 自动抢选开关
        self.switchWidget = QWidget()
        self.switchLayout = QHBoxLayout(self.switchWidget)
        self.enableLabel = QLabel(self.tr("自动抢选:"))
        self.switchButton = SwitchButton(indicatorPos=IndicatorPosition.RIGHT)
        self.switchButton.setChecked(cfg.get(cfg.enableAramAutoSwap))

        # 当前状态显示
        self.statusLabel = QLabel(self.tr("等待英雄上架..."))

        # 倒计时相关
        self.timeLeft = 0
        self.maxTime = 0
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.__onTimerTick)

        self.__initWindow()
        self.__initLayout()
        self.__connectSignalToSlot()
        self.__loadDesiredChampions()

    def __initWindow(self):
        self.setFixedSize(360, 480)
        self.setWindowIcon(QIcon("app/resource/images/game.png"))
        self.setWindowTitle(self.tr("大乱斗英雄备选池"))

        # 设置字体
        font = QFont("Microsoft YaHei", 11)
        self.enableLabel.setFont(font)
        self.desiredLabel.setFont(font)

        self.statusLabel.setStyleSheet("color: gray; font-size: 11px;")
        self.timerLabel.setStyleSheet("color: gray; font-size: 11px;")

        # 设置进度条样式
        self.progressBar.setStyleSheet("""
            QProgressBar {
                background-color: rgba(255, 255, 255, 30);
                border-radius: 4px;
                border: none;
            }
            QProgressBar::chunk {
                background-color: #009688;
                border-radius: 4px;
            }
        """)

    def __initLayout(self):
        self.vBoxLayout.setContentsMargins(20, 40, 20, 20)
        self.vBoxLayout.setSpacing(15)

        # 备选池英雄
        self.vBoxLayout.addWidget(self.benchWidget)

        # 倒计时
        self.timerLayout.setContentsMargins(0, 0, 0, 0)
        self.timerLayout.setSpacing(5)
        self.timerLayout.addWidget(self.timerLabel)
        self.timerLayout.addWidget(self.progressBar)
        self.vBoxLayout.addWidget(self.timerWidget)

        # 状态显示
        self.vBoxLayout.addWidget(self.statusLabel)

        # 开关
        self.switchLayout.setContentsMargins(0, 0, 0, 0)
        self.switchLayout.addWidget(self.enableLabel)
        self.switchLayout.addWidget(self.switchButton)
        self.switchLayout.addStretch()
        self.vBoxLayout.addWidget(self.switchWidget)

        # 期望英雄（开关下方）
        self.desiredLayout.setContentsMargins(0, 0, 0, 0)
        self.desiredLayout.setSpacing(8)
        self.desiredLayout.addWidget(self.desiredLabel)
        self.desiredLayout.addLayout(self.desiredIconsLayout)
        self.desiredLayout.addStretch()
        self.vBoxLayout.addWidget(self.desiredWidget)

        # 添加弹性空间
        self.vBoxLayout.addStretch()

    def __connectSignalToSlot(self):
        self.switchButton.checkedChanged.connect(self.__onSwitchChanged)

    def __loadDesiredChampions(self):
        """加载期望英雄头像（同步，直接读取本地缓存）"""
        # 清除现有图标
        while self.desiredIconsLayout.count():
            item = self.desiredIconsLayout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # 获取期望英雄列表
        desiredChampions = cfg.get(cfg.aramAutoSwapChampions)
        if not desiredChampions:
            self.desiredWidget.setVisible(False)
            return

        self.desiredWidget.setVisible(True)

        # 同步加载英雄图标（从本地缓存读取）
        for championId in desiredChampions:
            iconPath = f"app/resource/game/champion icons/{championId}.png"
            if os.path.exists(iconPath):
                icon = RoundIcon(iconPath, 28, 2, 2)
                self.desiredIconsLayout.addWidget(icon)

    def __onSwitchChanged(self, checked):
        qconfig.set(cfg.enableAramAutoSwap, checked)
        self.__loadDesiredChampions()

    def __onTimerTick(self):
        """定时器每秒触发，更新倒计时"""
        if self.timeLeft > 0:
            self.timeLeft -= 1
            self.progressBar.setValue(self.timeLeft)
            self.timerLabel.setText(self.tr("剩余时间: {}秒").format(self.timeLeft))
        else:
            self.timer.stop()
            self.timerLabel.setText(self.tr("剩余时间: 0秒"))

    def updateBenchChampions(self, benchChampions: list):
        """更新备选池英雄显示"""
        # 清除现有的英雄图标
        while self.benchLayout.count():
            item = self.benchLayout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # 重新添加英雄图标（5列网格，左对齐）
        for i, champ in enumerate(benchChampions):
            row = i // 5
            col = i % 5
            championId = champ.get('championId', 0)
            iconPath = champ.get('icon')
            if iconPath and championId > 0:
                icon = ClickableChampionIcon(championId, iconPath, 56)
                icon.clicked.connect(self.__onChampionClicked)
                self.benchLayout.addWidget(icon, row, col, Qt.AlignLeft | Qt.AlignTop)

    def __onChampionClicked(self, championId):
        """点击英雄图标，执行替换"""
        logger.info(f"尝试替换英雄: {championId}", TAG)
        asyncio.ensure_future(self.__benchSwap(championId))

    async def __benchSwap(self, championId):
        """执行备选席英雄替换"""
        try:
            result = await connector.benchSwap(championId)
            if result:
                self.updateStatus(self.tr("已替换英雄!"))
            else:
                self.updateStatus(self.tr("替换失败"))
        except Exception as e:
            logger.error(f"替换英雄失败: {e}", TAG)
            self.updateStatus(self.tr("替换失败: {}").format(str(e)))

    def updateTimer(self, timer: dict):
        """更新倒计时显示"""
        phase = timer.get('phase', '')
        if phase not in ['BAN_PICK', 'PLANNING']:
            self.timerWidget.setVisible(False)
            return

        self.timerWidget.setVisible(True)

        # 获取剩余时间（毫秒转秒）
        adjustedTime = timer.get('adjustedTimeLeftInPhase', 0)
        self.timeLeft = int(adjustedTime / 1000)

        # 设置进度条最大值（首次设置时）
        if self.maxTime == 0 or self.timeLeft > self.maxTime:
            self.maxTime = self.timeLeft
            self.progressBar.setMaximum(self.maxTime)

        self.progressBar.setValue(self.timeLeft)
        self.timerLabel.setText(self.tr("剩余时间: {}秒").format(self.timeLeft))

        # 启动定时器
        if not self.timer.isActive():
            self.timer.start(1000)

    def updateStatus(self, text):
        """更新状态显示"""
        self.statusLabel.setText(text)

    def clearBench(self):
        """清空备选池显示"""
        while self.benchLayout.count():
            item = self.benchLayout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        self.statusLabel.setText(self.tr("等待英雄上架..."))
        self.timer.stop()
        self.timerLabel.setText(self.tr("剩余时间: --"))
        self.progressBar.setValue(0)
        self.maxTime = 0
