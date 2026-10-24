import asyncio
import math
import os

from PyQt5.QtCore import Qt, QTimer, QElapsedTimer, QRectF, QRect, QPointF, pyqtSignal
from PyQt5.QtGui import (QColor, QPainter, QPainterPath, QPen, QPixmap, QFont,
                         QFontMetrics, QIcon, QShowEvent)
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
                             QLabel, QFrame, QSizePolicy)

from app.common.config import qconfig, cfg
from app.common.logger import logger
from app.common.style_sheet import StyleSheet
from app.common.util import getLolClientWindowPos
from app.common.qfluentwidgets import (SwitchButton, IndicatorPosition,
                                       isDarkTheme, themeColor)
from app.lol.connector import connector
from app.components.champion_icon_widget import RoundedLabel
from app.view.opgg_window import OpggWindowBase

TAG = 'AramBenchWindow'

# 尺寸与 design-demos/aram-bench 的方案 A 保持一致
WIN_WIDTH = 384
WIN_HEIGHT_TWO_ROWS = 448

CARD_WIDTH = 65
CARD_HEIGHT = 84
CARD_GAP = 6
BENCH_COLUMNS = 5


def _font(size: int, weight=QFont.Normal) -> QFont:
    font = QFont('Microsoft YaHei')
    font.setPixelSize(size)
    font.setWeight(weight)
    return font


def _text_primary() -> QColor:
    return QColor(255, 255, 255) if isDarkTheme() else QColor(0, 0, 0)


def _text_secondary() -> QColor:
    return QColor(200, 200, 200) if isDarkTheme() else QColor(100, 100, 100)


def _text_tertiary() -> QColor:
    return QColor(176, 176, 177) if isDarkTheme() else QColor(131, 131, 131)


def _soft_border() -> QColor:
    return QColor(255, 255, 255, 28) if isDarkTheme() else QColor(0, 0, 0, 28)


def _preselect_color() -> QColor:
    """预选方框/状态用绿色，和主题色区分开。"""
    return QColor(76, 194, 43)


def _preselect_text_color() -> QColor:
    return QColor(160, 245, 160)


def _warn_color() -> QColor:
    return QColor(255, 194, 75) if isDarkTheme() else QColor(138, 90, 0)


def _status_color(kind: str) -> QColor:
    if kind == 'success':
        return QColor(76, 194, 43) if isDarkTheme() else QColor(28, 111, 11)
    if kind == 'error':
        return QColor(255, 141, 141) if isDarkTheme() else QColor(182, 0, 0)
    if kind == 'warn':
        return _warn_color()
    if kind == 'selected':
        return QColor(76, 194, 43) if isDarkTheme() else QColor(28, 111, 11)
    if kind == 'info':
        return _text_secondary()
    return _text_tertiary()


class RingTimer(QWidget):
    """环形倒计时。progress 为剩余比例，绘制在 68×68 的画布上。"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._progress = 0.0
        self._seconds = 0
        self._idle = True
        self._urgent = False

        self.setFixedSize(68, 68)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

    def setState(self, progress: float, seconds: int, idle: bool, urgent: bool):
        self._progress = max(0.0, min(1.0, progress))
        self._seconds = seconds
        self._idle = idle
        self._urgent = urgent
        self.update()

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(2, 2, self.width() - 4, self.height() - 4)
        track = QColor(255, 255, 255, 46) if isDarkTheme() else QColor(0, 0, 0, 30)

        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(track, 4))
        painter.drawEllipse(rect)

        if not self._idle and self._progress > 0:
            color = _warn_color() if self._urgent else themeColor()
            pen = QPen(color, 4, Qt.SolidLine, Qt.RoundCap)
            painter.setPen(pen)
            if self._progress >= 0.999:
                painter.drawEllipse(rect)
            else:
                painter.drawArc(rect, 90 * 16, int(round(-360 * self._progress * 16)))

        # 中心数字
        number = '—' if self._idle else str(self._seconds)
        numberFont = QFont('Segoe UI')
        numberFont.setPixelSize(19)
        numberFont.setWeight(QFont.DemiBold)
        painter.setFont(numberFont)
        painter.setPen(_warn_color() if self._urgent else _text_primary())
        painter.drawText(QRectF(0, 14, self.width(), 26), Qt.AlignCenter, number)

        if not self._idle:
            unitFont = QFont('Microsoft YaHei')
            unitFont.setPixelSize(9)
            painter.setFont(unitFont)
            painter.setPen(_text_tertiary())
            painter.drawText(QRectF(0, 41, self.width(), 12), Qt.AlignCenter, self.tr('秒'))


class StatusLine(QWidget):
    """底部状态行：成功 / 失败 / 告警 / 进行中 / 中性。"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self._text = ''
        self._kind = 'muted'
        self._spin = 0

        self.setFixedHeight(20)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        self._spinTimer = QTimer(self)
        self._spinTimer.setInterval(40)
        self._spinTimer.timeout.connect(self.__onSpin)

    @property
    def kind(self) -> str:
        return self._kind

    def setStatus(self, text: str, kind: str = 'muted'):
        self._text = text
        self._kind = kind

        if kind == 'info':
            self._spinTimer.start()
        else:
            self._spinTimer.stop()

        self.update()

    def __onSpin(self):
        self._spin = (self._spin + 9) % 360
        self.update()

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        color = _status_color(self._kind)
        iconRect = QRectF(0, 3, 14, 14)

        if self._kind in ('muted', 'selected'):
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(5, 8, 4, 4))
        elif self._kind == 'info':
            pen = QPen(color, 1.8)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.setBrush(Qt.NoBrush)
            painter.drawArc(QRectF(1, 4, 12, 12), self._spin * 16, 270 * 16)
        else:
            ring = QColor(color)
            ring.setAlpha(140)
            painter.setPen(QPen(ring, 1.2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(QRectF(0.7, 3.7, 12.6, 12.6))

            pen = QPen(color, 1.4, Qt.SolidLine, Qt.RoundCap, Qt.RoundJoin)
            painter.setPen(pen)

            if self._kind == 'success':
                path = QPainterPath(QPointF(4.2, 10.0))
                path.lineTo(6.1, 11.9)
                path.lineTo(9.9, 8.0)
                painter.drawPath(path)
            elif self._kind == 'error':
                painter.drawLine(QPointF(7, 6.6), QPointF(7, 10.2))
                painter.setPen(Qt.NoPen)
                painter.setBrush(color)
                painter.drawEllipse(QPointF(7, 12.2), 0.7, 0.7)
            elif self._kind == 'warn':
                painter.drawLine(QPointF(7, 6.5), QPointF(7, 10.0))
                painter.drawLine(QPointF(7, 10.0), QPointF(9.2, 11.2))

        font = _font(12)
        painter.setFont(font)
        painter.setPen(color)

        metrics = QFontMetrics(font)
        available = max(0, self.width() - 21)
        text = metrics.elidedText(self._text, Qt.ElideRight, available)
        painter.drawText(QRectF(21, 0, available, self.height()),
                         Qt.AlignVCenter | Qt.AlignLeft, text)


class ChampionCard(QWidget):
    """备选池英雄卡片：左键预选，右键取消预选。"""

    clicked = pyqtSignal(int)
    rightClicked = pyqtSignal(int)

    def __init__(self, championId: int, name: str, iconPath: str, target: bool, parent=None):
        super().__init__(parent)

        self.championId = championId
        self.name = name
        self.iconPath = iconPath
        self._pixmap = QPixmap(iconPath) if iconPath else QPixmap()

        self._target = target
        self._preselected = False
        self._busy = False
        self._hover = False
        self._pressed = False
        self._spin = 0

        self.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setToolTip(
            self.tr('{}\n左键预选，右键取消预选').format(name))

        self._spinTimer = QTimer(self)
        self._spinTimer.setInterval(40)
        self._spinTimer.timeout.connect(self.__onSpin)

    def setTarget(self, target: bool):
        if self._target == target:
            return

        self._target = target
        self.update()

    def setPreselected(self, preselected: bool):
        if self._preselected == preselected:
            return

        self._preselected = preselected
        self.update()

    def setIconPath(self, iconPath: str):
        changed = iconPath != self.iconPath
        self.iconPath = iconPath

        # 后台下载完成后，同一路径也要把空 pixmap 重新加载一次
        if changed or (self._pixmap.isNull() and iconPath and os.path.exists(iconPath)):
            self._pixmap = QPixmap(iconPath) if iconPath else QPixmap()
            self.update()

    def setBusy(self, busy: bool):
        if self._busy == busy:
            return

        self._busy = busy
        if busy:
            self._spinTimer.start()
        else:
            self._spinTimer.stop()
        self.update()

    def __onSpin(self):
        self._spin = (self._spin + 20) % 360
        self.update()

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        iconRect = QRectF(0, 0, CARD_WIDTH, 65)
        path = QPainterPath()
        path.addRoundedRect(iconRect, 6, 6)

        painter.save()
        painter.setClipPath(path)
        painter.fillRect(iconRect, QColor(13, 15, 18))

        if not self._pixmap.isNull():
            dpr = self.devicePixelRatioF()
            size = max(1, int(round(65 * dpr)))
            pixmap = self._pixmap.scaled(
                size, size, Qt.KeepAspectRatioByExpanding, Qt.SmoothTransformation)
            painter.drawPixmap(
                QRectF(0, 0, CARD_WIDTH, 65), pixmap, QRectF(pixmap.rect()))
        else:
            painter.fillRect(iconRect, QColor(30, 35, 43))
            painter.setPen(QColor(216, 201, 163))
            painter.setFont(_font(16, QFont.DemiBold))
            painter.drawText(iconRect, Qt.AlignCenter, self.name[:1])

        if self._busy:
            painter.fillRect(iconRect, QColor(0, 0, 0, 140))

        painter.restore()

        if self._preselected:
            border = _preselect_color()
            width = 3
        elif self._target:
            border = themeColor()
            width = 2
        elif self._hover or self.hasFocus() or self._pressed:
            border = themeColor()
            width = 1
        else:
            border = _soft_border()
            width = 1

        painter.setPen(QPen(border, width))
        painter.setBrush(Qt.NoBrush)
        inset = width / 2.0
        painter.drawRoundedRect(
            iconRect.adjusted(inset, inset, -inset, -inset), 6, 6)

        if self._target:
            badgeRect = QRectF(CARD_WIDTH - 27, 3, 24, 13)
            painter.setPen(QPen(QColor(0, 159, 170, 140), 1))
            painter.setBrush(QColor(0, 0, 0, 160))
            painter.drawRoundedRect(badgeRect, 3, 3)
            painter.setPen(QColor(143, 224, 232))
            painter.setFont(_font(9))
            painter.drawText(badgeRect, Qt.AlignCenter, self.tr('目标'))

        if self._preselected:
            badgeRect = QRectF(3, 3, 24, 13)
            painter.setPen(QPen(QColor(76, 194, 43, 190), 1))
            painter.setBrush(QColor(0, 0, 0, 165))
            painter.drawRoundedRect(badgeRect, 3, 3)
            painter.setPen(_preselect_text_color())
            painter.setFont(_font(9))
            painter.drawText(badgeRect, Qt.AlignCenter, self.tr('预选'))

        nameFont = _font(12)
        painter.setFont(nameFont)
        painter.setPen(_text_primary() if (self._hover and not self._busy) else _text_tertiary())
        name = QFontMetrics(nameFont).elidedText(self.name, Qt.ElideRight, CARD_WIDTH - 3)
        painter.drawText(QRectF(0, 66, CARD_WIDTH, 18),
                         Qt.AlignHCenter | Qt.AlignTop, name)

        if self._busy:
            spinnerRect = QRectF(CARD_WIDTH / 2.0 - 9, 65 / 2.0 - 9, 18, 18)
            painter.setPen(QPen(QColor(255, 255, 255, 45), 2))
            painter.setBrush(Qt.NoBrush)
            painter.drawEllipse(spinnerRect)

            pen = QPen(QColor(255, 255, 255, 235), 2)
            pen.setCapStyle(Qt.RoundCap)
            painter.setPen(pen)
            painter.drawArc(spinnerRect, self._spin * 16, 270 * 16)

            painter.setPen(_text_secondary())
            painter.setFont(nameFont)
            painter.drawText(QRectF(0, 66, CARD_WIDTH, 18),
                             Qt.AlignHCenter | Qt.AlignTop, name)

    def enterEvent(self, e):
        self._hover = True
        self.update()
        return super().enterEvent(e)

    def leaveEvent(self, e):
        self._hover = False
        self._pressed = False
        self.update()
        return super().leaveEvent(e)

    def mousePressEvent(self, e):
        if e.button() == Qt.RightButton:
            if not self._busy:
                self.rightClicked.emit(self.championId)
            return

        if e.button() == Qt.LeftButton and not self._busy:
            self._pressed = True
            self.update()
            return
        return super().mousePressEvent(e)

    def mouseReleaseEvent(self, e):
        if self._pressed and e.button() == Qt.LeftButton:
            self._pressed = False
            self.update()
            if (self.rect().contains(e.pos())
                    and not self._busy):
                self.clicked.emit(self.championId)
            return
        return super().mouseReleaseEvent(e)

    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Return, Qt.Key_Enter, Qt.Key_Space) \
                and not self._busy:
            self.clicked.emit(self.championId)
            return
        return super().keyPressEvent(e)


class TargetChip(QFrame):
    """优先目标 chip：只显示 28px 头像，名字放 tooltip。"""

    def __init__(self, championId: int, name: str, iconPath: str,
                 inPool: bool, parent=None):
        super().__init__(parent)

        self.championId = championId
        self.iconPath = iconPath
        self._fallbackName = name[:1]

        self.setObjectName('targetChip')
        self.setProperty('inPool', inPool)
        self.setFixedSize(28, 28)
        self.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.hBoxLayout = QHBoxLayout(self)
        self.hBoxLayout.setContentsMargins(2, 2, 2, 2)
        self.hBoxLayout.setSpacing(0)

        if iconPath and os.path.exists(iconPath):
            self.icon = RoundedLabel(iconPath, 3.0, 0)
            self.icon.setFixedSize(22, 22)
            self.hBoxLayout.addWidget(self.icon)
        else:
            self.icon = QLabel(self._fallbackName)
            self.icon.setObjectName('targetChipFallback')
            self.icon.setFont(_font(10))
            self.icon.setAlignment(Qt.AlignCenter)
            self.icon.setFixedSize(22, 22)
            self.hBoxLayout.addWidget(self.icon)

        self.setToolTip(self.tr('优先目标：') + name)

    def setIconPath(self, iconPath: str):
        self.iconPath = iconPath
        if not iconPath or not os.path.exists(iconPath):
            return

        # 已经是真实图标，无需重载
        if isinstance(self.icon, RoundedLabel):
            return

        # 用下载好的图标替换首字占位
        self.hBoxLayout.removeWidget(self.icon)
        self.icon.deleteLater()
        self.icon = RoundedLabel(iconPath, 3.0, 0)
        self.icon.setFixedSize(22, 22)
        self.hBoxLayout.addWidget(self.icon)
        self.update()

    def setInPool(self, inPool: bool):
        if self.property('inPool') == inPool:
            return

        self.setProperty('inPool', inPool)
        self.style().unpolish(self)
        self.style().polish(self)
        self.update()


class PulseDot(QWidget):
    """空状态里的呼吸点。"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setFixedSize(16, 16)
        self._phase = 0.0

        self._timer = QTimer(self)
        self._timer.setInterval(40)
        self._timer.timeout.connect(self.__onTick)

    def showEvent(self, e):
        self._timer.start()
        return super().showEvent(e)

    def hideEvent(self, e):
        self._timer.stop()
        return super().hideEvent(e)

    def __onTick(self):
        self._phase = (self._phase + 0.02) % 1.0
        self.update()

    def paintEvent(self, e):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        color = themeColor()
        ring = QColor(color)
        ring.setAlpha(int(110 * (1 - self._phase)))

        radius = 3 + self._phase * 5
        painter.setPen(QPen(ring, 1))
        painter.setBrush(Qt.NoBrush)
        painter.drawEllipse(QRectF(8 - radius, 8 - radius, radius * 2, radius * 2))

        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QRectF(5, 5, 6, 6))


class EmptyBench(QFrame):
    """备选池为空时的占位块。"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setObjectName('emptyState')
        self.setFixedHeight(174)

        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(16, 16, 16, 16)
        self.vBoxLayout.setSpacing(6)
        self.vBoxLayout.setAlignment(Qt.AlignCenter)

        self.dot = PulseDot()

        self.titleLabel = QLabel(self.tr('备选池暂时为空'))
        self.titleLabel.setObjectName('emptyTitle')
        self.titleLabel.setFont(_font(12))
        self.titleLabel.setAlignment(Qt.AlignCenter)

        self.hintLabel = QLabel(self.tr('有新英雄上架时会自动出现在这里'))
        self.hintLabel.setObjectName('emptyHint')
        self.hintLabel.setFont(_font(11))
        self.hintLabel.setAlignment(Qt.AlignCenter)

        self.vBoxLayout.addWidget(self.dot, alignment=Qt.AlignHCenter)
        self.vBoxLayout.addWidget(self.titleLabel)
        self.vBoxLayout.addWidget(self.hintLabel)


class AramBenchWindow(OpggWindowBase):
    """大乱斗英雄备选池窗口（方案 A · 指挥台）"""

    def __init__(self, parent=None):
        super().__init__()

        self.benchChampions = []
        self.desiredChampions = []
        self.preSelectedChampionId = None
        self._targetChips = {}
        self._cards = []

        self._swapping = False
        self._swapToken = 0
        self._busyChampionId = None
        self._remaining = 0.0
        self._maxTime = 0.0
        self._phase = ''
        self._urgentNotified = False
        self._timeUpNotified = False

        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self.__onTimerTick)
        self._elapsed = QElapsedTimer()

        self._statusTimer = QTimer(self)
        self._statusTimer.setSingleShot(True)
        self._statusTimer.timeout.connect(self.__onStatusTimeout)

        self.__initWindow()
        self.__initWidgets()
        self.__initLayout()
        self.__connectSignals()

        self.__resetTimer()
        self.clearBench()
        self.__loadDesiredChampions()

    # ------------------------------------------------------------------ 窗口
    def __initWindow(self):
        self.setFixedSize(WIN_WIDTH, WIN_HEIGHT_TWO_ROWS)
        self.setWindowIcon(QIcon('app/resource/images/game.png'))
        self.setWindowTitle(self.tr('大乱斗英雄备选池'))

        # FluentTitleBar 默认 48px，这里压到 36px；窗口内容边距已由基类设为 36
        self.titleBar.setFixedHeight(36)
        self.titleBar.titleLabel.setFont(_font(12))

        StyleSheet.ARAM_BENCH_WINDOW.apply(self)

    def __initWidgets(self):
        # 顶部指挥台
        self.heroCard = QFrame()
        self.heroCard.setObjectName('heroCard')
        self.heroCard.setFixedHeight(88)

        self.ringTimer = RingTimer()

        self.heroKicker = QLabel(self.tr('等待上架'))
        self.heroKicker.setObjectName('heroKicker')
        self.heroKicker.setFont(_font(11))

        self.heroPhase = QLabel(self.tr('选人阶段'))
        self.heroPhase.setObjectName('heroPhase')
        self.heroPhase.setFont(_font(14, QFont.DemiBold))

        self.heroHint = QLabel(self.tr('阶段结束前均可更换'))
        self.heroHint.setObjectName('heroHint')
        self.heroHint.setFont(_font(11))

        self.autoLabel = QLabel(self.tr('自动抢选'))
        self.autoLabel.setObjectName('autoLabel')
        self.autoLabel.setFont(_font(11))

        self.switchButton = SwitchButton(indicatorPos=IndicatorPosition.RIGHT)
        self.switchButton.setOnText('')
        self.switchButton.setOffText('')
        self.switchButton.setChecked(cfg.get(cfg.enableAramAutoSwap))

        # 优先目标
        self.targetsWidget = QWidget()
        self.targetsWidget.setFixedHeight(28)

        self.targetsLabel = QLabel(self.tr('优先目标'))
        self.targetsLabel.setObjectName('targetsLabel')
        self.targetsLabel.setFont(_font(11))

        self.chipsWidget = QWidget()
        self.chipsLayout = QHBoxLayout(self.chipsWidget)
        self.chipsLayout.setContentsMargins(0, 0, 0, 0)
        self.chipsLayout.setSpacing(5)

        # 备选池
        self.benchWidget = QWidget()

        self.benchHeader = QWidget()
        self.benchHeader.setFixedHeight(18)
        self.benchTitle = QLabel(self.tr('备选池'))
        self.benchTitle.setObjectName('benchTitle')
        self.benchTitle.setFont(_font(12, QFont.DemiBold))
        self.benchCount = QLabel('0 位')
        self.benchCount.setObjectName('benchCount')
        self.benchCount.setFont(_font(11))

        self.benchGridWidget = QWidget()
        self.benchGrid = QGridLayout(self.benchGridWidget)
        self.benchGrid.setContentsMargins(0, 0, 0, 0)
        self.benchGrid.setSpacing(CARD_GAP)
        self.benchGrid.setAlignment(Qt.AlignLeft | Qt.AlignTop)

        self.emptyBench = EmptyBench()

        # 底部状态
        self.statusLine = StatusLine()

    def __initLayout(self):
        # 顶部指挥台
        heroLayout = QHBoxLayout(self.heroCard)
        heroLayout.setContentsMargins(12, 9, 12, 9)
        heroLayout.setSpacing(12)

        metaLayout = QVBoxLayout()
        metaLayout.setContentsMargins(0, 0, 0, 0)
        metaLayout.setSpacing(0)
        metaLayout.addWidget(self.heroKicker)
        metaLayout.addWidget(self.heroPhase)
        metaLayout.addWidget(self.heroHint)

        autoLayout = QHBoxLayout()
        autoLayout.setContentsMargins(0, 0, 0, 0)
        autoLayout.setSpacing(6)
        autoLayout.addWidget(self.autoLabel)
        autoLayout.addWidget(self.switchButton)

        heroLayout.addWidget(self.ringTimer)
        heroLayout.addLayout(metaLayout, 1)
        heroLayout.addLayout(autoLayout)

        # 优先目标
        targetsLayout = QHBoxLayout(self.targetsWidget)
        targetsLayout.setContentsMargins(0, 0, 0, 0)
        targetsLayout.setSpacing(8)
        targetsLayout.addWidget(self.targetsLabel)
        targetsLayout.addWidget(self.chipsWidget)
        targetsLayout.addStretch(1)

        # 备选池
        benchHeaderLayout = QHBoxLayout(self.benchHeader)
        benchHeaderLayout.setContentsMargins(0, 0, 0, 0)
        benchHeaderLayout.setSpacing(8)
        benchHeaderLayout.addWidget(self.benchTitle)
        benchHeaderLayout.addWidget(self.benchCount)
        benchHeaderLayout.addStretch(1)

        benchLayout = QVBoxLayout(self.benchWidget)
        benchLayout.setContentsMargins(0, 0, 0, 0)
        benchLayout.setSpacing(6)
        benchLayout.addWidget(self.benchHeader)
        benchLayout.addWidget(self.benchGridWidget)
        benchLayout.addWidget(self.emptyBench)

        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(16, 14, 16, 14)
        self.vBoxLayout.setSpacing(12)
        self.vBoxLayout.addWidget(self.heroCard)
        self.vBoxLayout.addWidget(self.targetsWidget)
        self.vBoxLayout.addWidget(self.benchWidget)
        self.vBoxLayout.addStretch(1)
        self.vBoxLayout.addWidget(self.statusLine)

    def __connectSignals(self):
        self.switchButton.checkedChanged.connect(self.__onSwitchChanged)
        qconfig.themeChangedFinished.connect(self.__onThemeChanged)

    # ------------------------------------------------------------------ 主题
    def __onThemeChanged(self):
        for widget in self.findChildren(QWidget):
            widget.update()
        self.update()

    # ------------------------------------------------------------------ 计时
    def __resetTimer(self):
        self._timer.stop()
        self._remaining = 0.0
        self._maxTime = 0.0
        self._phase = ''
        self._urgentNotified = False
        self._timeUpNotified = False

        self.ringTimer.setState(0.0, 0, True, False)
        self.heroKicker.setText(self.tr('等待上架'))
        self.heroPhase.setText(self.tr('选人阶段'))
        self.heroHint.setText(self.tr('阶段结束前均可更换'))

    def __updatePhaseText(self, phase: str):
        names = {
            'PLANNING': self.tr('预选阶段'),
            'BAN_PICK': self.tr('选人阶段'),
            'FINALIZATION': self.tr('确认阶段'),
            'GAME_STARTING': self.tr('即将开始'),
        }
        name = names.get(phase, self.tr('选人阶段'))
        if self.heroPhase.text() != name:
            self.heroPhase.setText(name)

        if phase in ('FINALIZATION', 'GAME_STARTING'):
            hint = self.tr('等待进入游戏')
        else:
            hint = self.tr('阶段结束前均可更换')
        if self.heroHint.text() != hint:
            self.heroHint.setText(hint)

    def updateTimer(self, timer: dict):
        """由主窗口在 champSelect 变化时调用。

        时间数据可能来自任意有计时的阶段（PLANNING / BAN_PICK / FINALIZATION），
        不再只认前两个阶段，否则进入确认阶段后倒计时会冻住。

        比例优先用 LCU 的 totalTimeInPhase；没有这个字段时才退回
        「本阶段首次观测到的剩余时间」。本地 16ms 计时只在偏差超过 1 秒
        或阶段切换时重对表，避免 LCU 每秒一次的数据把环拉得一顿一顿。
        """
        if timer.get('isInfinite', False):
            self._timer.stop()
            return

        phase = timer.get('phase', '') or self._phase
        if phase:
            self.__updatePhaseText(phase)

        try:
            remaining = max(0.0, float(timer.get('adjustedTimeLeftInPhase', 0)) / 1000.0)
            total = max(0.0, float(timer.get('totalTimeInPhase', 0)) / 1000.0)
        except (TypeError, ValueError):
            return

        phaseChanged = phase != self._phase

        # 每个阶段单独对一次最大时间；有 totalTimeInPhase 时用它，
        # 这样即使窗口在阶段中途才打开，环的比例也是对的
        if phaseChanged:
            self._phase = phase
            if total > 0:
                self._maxTime = total
            elif remaining > 0:
                self._maxTime = remaining
            else:
                self._maxTime = 0.0
            self._urgentNotified = False
            self._timeUpNotified = False

            if phase in ('FINALIZATION', 'GAME_STARTING'):
                # 进入确认阶段：先抢预选，然后关闭预选功能
                if self.preSelectedChampionId is not None:
                    self.__tryPreGrab()
                self.__setPreSelected(None)
                if self.statusLine.kind == 'selected':
                    self.updateStatus(self.__idleHint(), 'muted')

            self.__updateCardTooltips()
            if self.statusLine.kind == 'muted':
                self.updateStatus(self.__idleHint(), 'muted')
        elif total > 0:
            self._maxTime = total
        elif self._maxTime <= 0 or remaining > self._maxTime:
            self._maxTime = remaining

        if remaining <= 0:
            if phaseChanged:
                # 新阶段没有可显示的倒计时：停掉上一阶段的本地计时
                self._timer.stop()
                self._remaining = 0.0
                self.ringTimer.setState(0.0, 0, False, True)
            elif self._timer.isActive() or self._remaining > 0:
                # 同一阶段内 LCU 明确归零：把环画到 0 并结束，避免本地计时器
                # 继续跑、或一直停在上一秒
                self._remaining = 0.0
                self._timer.stop()
                self.__paintTimer()
                self.__handleTimeUp()
            return

        if phaseChanged or (not self._timer.isActive()) \
                or abs(remaining - self._remaining) > 1.0:
            self._remaining = remaining
            self._elapsed.restart()

        if self.heroKicker.text() != self.tr('剩余时间'):
            self.heroKicker.setText(self.tr('剩余时间'))

        if not self._timer.isActive():
            self._timer.start(16)

        self.__paintTimer()

    def __onTimerTick(self):
        dt = self._elapsed.restart() / 1000.0
        if dt <= 0:
            return

        self._remaining = max(0.0, self._remaining - dt)
        self.__paintTimer()

        if self._remaining <= 0:
            self._timer.stop()
            self.__handleTimeUp()

    def __handleTimeUp(self):
        if self._timeUpNotified:
            return

        self._timeUpNotified = True

        # 选人阶段倒计时结束但还没进入确认阶段：预选继续等，别提示“时间到”
        if self.preSelectedChampionId is not None \
                and self._phase not in ('FINALIZATION', 'GAME_STARTING'):
            return

        self.updateStatus(self.tr('选人时间已结束'), 'warn')

    def __paintTimer(self):
        progress = self._remaining / self._maxTime if self._maxTime > 0 else 0.0
        seconds = int(math.ceil(self._remaining))
        urgent = self._remaining <= 10.0

        self.ringTimer.setState(progress, seconds, False, urgent)

        if urgent and self._remaining > 0 and not self._urgentNotified:
            if self.statusLine.kind not in ('success', 'error', 'info', 'selected'):
                self._urgentNotified = True
                self.updateStatus(self.tr('剩余时间不足，尽快选择'), 'warn')
        elif self._remaining > 10.0:
            self._urgentNotified = False

    # ------------------------------------------------------------------ 状态
    def updateStatus(self, text: str, kind: str = 'muted'):
        if kind == 'muted':
            if '失败' in text:
                kind = 'error'
            elif '成功' in text or '抢到' in text:
                kind = 'success'

        self.statusLine.setStatus(text, kind)
        self._statusTimer.stop()

        # 成功提示 4 秒后回落到中性提示；失败/告警保留
        if kind == 'success':
            self._statusTimer.start(4000)

    def __onStatusTimeout(self):
        # 成功提示回落后，如果仍有预选，把预选状态重新挂出来
        if self.preSelectedChampionId is not None:
            card = self.__findCard(self.preSelectedChampionId)
            if card is not None:
                self.updateStatus(
                    self.tr('已预选 {} · 进入确认阶段自动抢下').format(card.name),
                    'selected')
                return

        self.updateStatus(self.__idleHint(), 'muted')

    # ------------------------------------------------------------ 优先目标
    def __loadDesiredChampions(self):
        """重建优先目标 chips（设置变更后由 showEvent 再调一次）"""
        try:
            desired = [int(i) for i in (cfg.get(cfg.aramAutoSwapChampions) or [])]
        except (TypeError, ValueError):
            desired = []

        self.desiredChampions = desired
        self._targetChips = {}

        # 设置可能在窗口隐藏期间被改过，把已有卡片的角标同步过来
        for card in self._cards:
            card.setTarget(card.championId in self.desiredChampions)

        while self.chipsLayout.count():
            item = self.chipsLayout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.deleteLater()

        if not desired:
            self.targetsWidget.setVisible(False)
            return

        self.targetsWidget.setVisible(True)
        pool = {c.get('championId', 0) for c in self.benchChampions}

        # 只显示头像，名字放 tooltip；最多 8 个，避免超出 352px
        for championId in desired[:8]:
            chip = TargetChip(
                championId,
                self.__championName(championId),
                f'app/resource/game/champion icons/{championId}.png',
                championId in pool)
            self._targetChips[championId] = chip
            self.chipsLayout.addWidget(chip)

    def __updateTargetsInPool(self):
        pool = {c.get('championId', 0) for c in self.benchChampions}
        for championId, chip in self._targetChips.items():
            chip.setInPool(championId in pool)
            chip.setIconPath(f'app/resource/game/champion icons/{championId}.png')

    def __championName(self, championId: int) -> str:
        try:
            name = connector.manager.getChampionNameById(championId)
        except Exception:
            name = None

        return name or str(championId)

    # ------------------------------------------------------------ 备选池
    def __rebuildBench(self):
        # 先算出本轮要显示哪些英雄
        entries = []
        seen = set()
        for champ in self.benchChampions:
            try:
                championId = int(champ.get('championId', 0))
            except (TypeError, ValueError):
                continue
            if championId <= 0 or championId in seen:
                continue
            seen.add(championId)
            entries.append((championId, champ.get('icon')))
            if len(entries) >= 10:
                break

        self.benchCount.setText(f'{len(entries)} 位')

        if not entries:
            for card in self._cards:
                self.benchGrid.removeWidget(card)
                card.hide()
                card.deleteLater()
            self._cards = []
            self.benchGridWidget.setVisible(False)
            self.emptyBench.setVisible(True)
            return

        # 按 championId 复用已有卡片：同一张卡的 QPixmap 已经缓存，
        # 换英雄引起的备选池刷新不会再让所有头像重新加载、闪一次
        oldById = {card.championId: card for card in self._cards}
        newCards = []

        for championId, iconPath in entries:
            card = oldById.get(championId)
            if card is None:
                card = ChampionCard(
                    championId,
                    self.__championName(championId),
                    iconPath,
                    championId in self.desiredChampions)
                card.clicked.connect(self.__onCardClicked)
                card.rightClicked.connect(self.__onCardRightClicked)
            else:
                card.setIconPath(iconPath)
                card.setTarget(championId in self.desiredChampions)

            card.setPreselected(championId == self.preSelectedChampionId)

            # 只让正在更换的那张卡进入 busy；其余卡片保持原样，
            # 避免点一次换英雄就整排头像重绘、闪一下
            card.setBusy(self._swapping and championId == self._busyChampionId)

            newCards.append(card)

        self.__applyCardLayout(newCards)
        self._cards = newCards
        self.__updateCardTooltips()
        self.benchGridWidget.setVisible(True)
        self.emptyBench.setVisible(False)

        rows = math.ceil(len(newCards) / BENCH_COLUMNS)
        self.benchGridWidget.setFixedHeight(
            rows * CARD_HEIGHT + (rows - 1) * CARD_GAP)

    def __applyCardLayout(self, cards: list):
        """把卡片放到目标格，只动位置真正变化的那几张。

        旧实现每次先把整个布局清空再按顺序重建，哪怕只换了一个英雄，
        所有卡片也会被重新 addWidget 一遍；在透明窗口下这会表现为整排
        头像一起刷新。这里改为逐格对位，未变化的卡片完全不碰。
        """
        targetCell = {
            card.championId: divmod(index, BENCH_COLUMNS)
            for index, card in enumerate(cards)
        }
        keepIds = set(targetCell)

        # 先摘掉不再显示的卡片，以及位置发生变化的卡片
        for card in self._cards:
            if card.championId not in keepIds:
                self.benchGrid.removeWidget(card)
                card.hide()
                card.deleteLater()
                continue

            row, col = targetCell[card.championId]
            item = self.benchGrid.itemAtPosition(row, col)
            if item is None or item.widget() is not card:
                self.benchGrid.removeWidget(card)

        # 再把新增 / 移动的卡片放回目标格
        for card in cards:
            row, col = targetCell[card.championId]
            item = self.benchGrid.itemAtPosition(row, col)
            if item is not None and item.widget() is card:
                continue

            # 顺序调整时，目标格可能还被另一张待移动的卡占着
            if item is not None and item.widget() is not None:
                self.benchGrid.removeWidget(item.widget())

            self.benchGrid.addWidget(
                card, row, col, Qt.AlignLeft | Qt.AlignTop)

    def __updateWindowHeight(self):
        # 固定为两排头像的高度：1-5 个和 6-10 个英雄都保持同一高度，
        # 避免 5→6（或空池→有英雄）时窗口突然长高、位置重算导致抖动
        if self.height() != WIN_HEIGHT_TWO_ROWS:
            self.setFixedHeight(WIN_HEIGHT_TWO_ROWS)

    def updateBenchChampions(self, benchChampions: list):
        benchChampions = benchChampions or []

        normalized = []
        for champ in benchChampions:
            if not isinstance(champ, dict):
                continue
            try:
                championId = int(champ.get('championId', 0))
            except (TypeError, ValueError):
                continue
            if championId <= 0:
                continue
            normalized.append({
                'championId': championId,
                'icon': champ.get('icon')
            })

        self.benchChampions = normalized

        # 预选英雄被别人抢走 / 已不在池里
        if self.preSelectedChampionId is not None:
            if not any(c['championId'] == self.preSelectedChampionId
                       for c in self.benchChampions):
                self.__setPreSelected(None)
                if self.statusLine.kind == 'selected':
                    self.updateStatus(self.tr('预选英雄已不在备选池'), 'warn')

        self.__rebuildBench()
        self.__updateWindowHeight()
        self.__updateTargetsInPool()

        if self.statusLine.kind == 'muted':
            self.updateStatus(self.__idleHint(), 'muted')

    def __cardHint(self) -> str:
        if self._phase in ('FINALIZATION', 'GAME_STARTING'):
            return self.tr('左键直接更换英雄')
        return self.tr('左键预选，右键取消预选')

    def __updateCardTooltips(self):
        hint = self.__cardHint()
        for card in self._cards:
            text = f'{card.name}\n{hint}'
            if card.toolTip() != text:
                card.setToolTip(text)

    def __idleHint(self) -> str:
        if not self._cards:
            return self.tr('等待英雄上架…')
        if self._phase in ('FINALIZATION', 'GAME_STARTING'):
            return self.tr('左键点击英雄直接更换')
        return self.tr('左键预选 · 右键取消 · 确认阶段自动抢下')

    def clearBench(self):
        self.benchChampions = []
        self._swapping = False
        self._swapToken += 1     # 让清空时仍在飞的换英雄请求失效
        self.preSelectedChampionId = None
        self._busyChampionId = None

        self.__rebuildBench()
        self.__updateWindowHeight()
        self.__updateTargetsInPool()
        self.__resetTimer()
        self.updateStatus(self.tr('等待英雄上架…'), 'muted')

    # ------------------------------------------------------------ 预选 / 更换
    def __onSwitchChanged(self, checked: bool):
        qconfig.set(cfg.enableAramAutoSwap, checked)

    def __findCard(self, championId: int):
        for card in self._cards:
            if card.championId == championId:
                return card
        return None

    def __setPreSelected(self, championId):
        self.preSelectedChampionId = championId
        for card in self._cards:
            card.setPreselected(card.championId == championId)

    def __onCardClicked(self, championId: int):
        """选人阶段左键预选；确认阶段左键直接更换。"""
        if self._swapping:
            return

        card = self.__findCard(championId)
        if card is None:
            return

        # 确认阶段：预选功能不生效，左键直接换英雄
        if self._phase in ('FINALIZATION', 'GAME_STARTING'):
            self.__setPreSelected(None)
            self.__startBenchSwap(championId, card.name, auto=False)
            return

        # 选人阶段：左键预选，右键取消
        if championId == self.preSelectedChampionId:
            return

        self.__setPreSelected(championId)
        self.updateStatus(
            self.tr('已预选 {} · 进入确认阶段自动抢下').format(card.name), 'selected')

    def __onCardRightClicked(self, championId: int):
        """右键点击任意卡片 = 取消当前预选。"""
        if self._swapping or self.preSelectedChampionId is None:
            return

        self.__setPreSelected(None)
        self.updateStatus(self.__idleHint(), 'muted')

    def __tryPreGrab(self) -> bool:
        """倒计时结束：有预选就抢，返回是否已经处理过。"""
        championId = self.preSelectedChampionId
        if championId is None or self._swapping:
            return False

        card = self.__findCard(championId)
        if card is None:
            self.__setPreSelected(None)
            self.updateStatus(self.tr('预选英雄已不在备选池'), 'warn')
            return True

        name = card.name
        self.__setPreSelected(None)     # 只抢一次
        self.__startBenchSwap(championId, name, auto=True)
        return True

    def __startBenchSwap(self, championId: int, name: str, auto: bool = False):
        if self._swapping:
            return

        card = self.__findCard(championId)
        if card is None:
            return

        self._swapToken += 1
        token = self._swapToken

        self._swapping = True
        self._busyChampionId = championId

        # 只给被点击的卡片转圈：其它卡片保持原样，点一次换英雄不会整排闪一下
        card.setBusy(True)

        text = self.tr('正在抢下 {}…') if auto else self.tr('正在更换为 {}…')
        self.updateStatus(text.format(name), 'info')
        asyncio.ensure_future(self.__benchSwap(championId, name, token))

    async def __benchSwap(self, championId: int, name: str, token: int):
        try:
            result = await connector.benchSwap(championId)

            if token != self._swapToken:
                return

            if isinstance(result, dict) and result.get('errorCode'):
                self.updateStatus(
                    self.tr('更换失败 · {}').format(result.get('message', '')), 'error')
            else:
                self.updateStatus(self.tr('已抢到 {}').format(name), 'success')
        except Exception as e:
            logger.error(f'更换英雄失败: {e}', TAG)
            if token == self._swapToken:
                self.updateStatus(self.tr('更换失败 · {}').format(str(e)), 'error')
        finally:
            if token != self._swapToken:
                return

            self._swapping = False
            self._busyChampionId = None
            for item in self._cards:
                try:
                    item.setBusy(False)
                except RuntimeError:
                    # 备选池刷新时卡片可能已被 deleteLater
                    pass

    # ------------------------------------------------------------------ 位置
    def adjustPosition(self):
        """调整窗口位置到客户端右下角"""
        size = self.size()
        pos = getLolClientWindowPos()

        if not pos:
            return

        dpi = self.devicePixelRatioF()
        x = pos.right() * dpi
        y = pos.bottom() - size.height() * dpi

        rect = QRect(int(x / dpi), int(y / dpi), size.width(), size.height())
        self.setGeometry(rect)

    def showEvent(self, a0: QShowEvent):
        self.adjustPosition()
        self.switchButton.setChecked(cfg.get(cfg.enableAramAutoSwap))
        self.__loadDesiredChampions()
        self.__updateTargetsInPool()
        return super().showEvent(a0)
