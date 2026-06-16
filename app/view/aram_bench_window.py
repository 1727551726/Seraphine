from qasync import asyncSlot
from PyQt5.QtGui import QColor, QPainter, QIcon
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
                             QGridLayout, QSpacerItem, QSizePolicy)

from app.common.config import qconfig, cfg
from app.common.logger import logger
from app.common.style_sheet import StyleSheet
from app.common.qfluentwidgets import (FramelessWindow, isDarkTheme, BackgroundAnimationWidget,
                                       FluentTitleBar, BodyLabel, SwitchButton, IndicatorPosition,
                                       PushButton)
from app.components.champion_icon_widget import RoundIcon
from app.view.opgg_window import OpggWindowBase

TAG = 'AramBenchWindow'


class AramBenchWindow(OpggWindowBase):
    """大乱斗备选池窗口"""

    def __init__(self, parent=None):
        super().__init__()

        self.vBoxLayout = QVBoxLayout(self)

        # 标题
        self.titleLabel = BodyLabel(self.tr("大乱斗备选池"))
        self.titleLabel.setObjectName("titleLabel")

        # 备选池英雄展示区域
        self.benchWidget = QWidget()
        self.benchLayout = QGridLayout(self.benchWidget)
        self.benchLayout.setSpacing(8)

        # 自动抢选开关
        self.switchWidget = QWidget()
        self.switchLayout = QHBoxLayout(self.switchWidget)
        self.enableLabel = QLabel(self.tr("自动抢选:"))
        self.switchButton = SwitchButton(indicatorPos=IndicatorPosition.RIGHT)
        self.switchButton.setChecked(cfg.get(cfg.enableAramAutoSwap))

        # 当前状态显示
        self.statusLabel = QLabel(self.tr("等待英雄上架..."))

        self.__initWindow()
        self.__initLayout()
        self.__connectSignalToSlot()

    def __initWindow(self):
        self.setFixedSize(320, 400)
        self.setWindowIcon(QIcon("app/resource/images/game.png"))
        self.setWindowTitle(self.tr("ARAM 备选池"))

        self.statusLabel.setStyleSheet("color: gray; font-size: 12px;")

    def __initLayout(self):
        self.vBoxLayout.setContentsMargins(20, 40, 20, 20)
        self.vBoxLayout.setSpacing(15)

        # 标题
        self.vBoxLayout.addWidget(self.titleLabel)

        # 备选池英雄
        self.vBoxLayout.addWidget(self.benchWidget)

        # 状态显示
        self.vBoxLayout.addWidget(self.statusLabel)

        # 开关
        self.switchLayout.setContentsMargins(0, 0, 0, 0)
        self.switchLayout.addWidget(self.enableLabel)
        self.switchLayout.addWidget(self.switchButton)
        self.switchLayout.addStretch()
        self.vBoxLayout.addWidget(self.switchWidget)

        # 添加弹性空间
        self.vBoxLayout.addStretch()

    def __connectSignalToSlot(self):
        self.switchButton.checkedChanged.connect(self.__onSwitchChanged)

    def __onSwitchChanged(self, checked):
        qconfig.set(cfg.enableAramAutoSwap, checked)

    def updateBenchChampions(self, benchChampions: list):
        """更新备选池英雄显示"""
        # 清除现有的英雄图标
        while self.benchLayout.count():
            item = self.benchLayout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        # 重新添加英雄图标（5列网格）
        for i, champ in enumerate(benchChampions):
            row = i // 5
            col = i % 5
            iconPath = champ.get('icon')
            if iconPath:
                icon = RoundIcon(iconPath, 48, 2, 2)
                self.benchLayout.addWidget(icon, row, col, Qt.AlignCenter)

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
