from PyQt5.QtCore import Qt, QRectF
from PyQt5.QtGui import QColor, QPainter, QPainterPath
from PyQt5.QtWidgets import (QWidget, QHBoxLayout, QVBoxLayout, QLabel,
                             QSizePolicy)

from app.common.qfluentwidgets import isDarkTheme, qconfig
from app.components.champion_icon_widget import RoundIcon
from app.components.animation_frame import NoBorderColorAnimationFrame

# 伤害类型配色（规格：物理红棕 / 魔法蓝 / 真实白）
# 真实伤害必须分亮暗两套：深色主题上就是纯白，但纯白压在浅色主题的浅底上
# 会直接消失，所以浅色主题换成中性灰 —— 这是唯一一处无法照字面执行的地方。
DAMAGE_COLORS = {
    True: {                     # 深色主题
        'physical': '#b8512c',
        'magic': '#3b82f6',
        'real': '#ffffff',
    },
    False: {                    # 浅色主题
        'physical': '#b8512c',
        'magic': '#3b82f6',
        'real': '#8a8a8a',
    },
}

# 条的底槽，以及「结算数据没给三段拆分」时的兜底色
TRACK_COLOR = {True: QColor(255, 255, 255, 26), False: QColor(0, 0, 0, 20)}
UNSPLIT_COLOR = {True: QColor(255, 255, 255, 90), False: QColor(0, 0, 0, 90)}

SEGMENT_KEYS = ('physical', 'magic', 'real')


def damageColors():
    """当前主题下的三段配色"""
    return DAMAGE_COLORS[isDarkTheme()]


class DamageBarWidget(QWidget):
    """物理 / 魔法 / 真实 三段堆叠的伤害条（自绘）。

    `ratio` 是「本行数值 / 组内最高值」，决定填充长度；
    三段之间再按各自数值占本行总量的比例分配宽度。
    """

    def __init__(self, parent=None):
        super().__init__(parent)

        self.physical = 0
        self.magic = 0
        self.real = 0
        self.ratio = 0.0
        self.unsplit = False

        self.setFixedHeight(10)
        self.setMinimumWidth(60)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

        # 自绘控件不吃 qss，主题切换得自己触发重绘
        qconfig.themeChangedFinished.connect(self.update)

    def setData(self, physical, magic, real, ratio, unsplit=False):
        self.physical = max(int(physical or 0), 0)
        self.magic = max(int(magic or 0), 0)
        self.real = max(int(real or 0), 0)
        self.ratio = min(max(float(ratio or 0.0), 0.0), 1.0)
        self.unsplit = unsplit

        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w = self.width()
        h = self.height()
        radius = h / 2
        colors = damageColors()

        # 底槽：全圆角，和 SmoothProgressBar 的 r = height / 2 保持一致
        painter.setPen(Qt.NoPen)
        painter.setBrush(TRACK_COLOR[isDarkTheme()])
        painter.drawRoundedRect(QRectF(0, 0, w, h), radius, radius)

        fillWidth = w * self.ratio

        if fillWidth <= 0:
            return

        # 填充裁成圆角，两端自然收圆
        path = QPainterPath()
        path.addRoundedRect(QRectF(0, 0, fillWidth, h), radius, radius)
        painter.setClipPath(path)

        total = self.physical + self.magic + self.real

        if self.unsplit or total <= 0:
            # 结算数据没给三段拆分时退化成一根中性色条。
            # 既不能用 0 冒充缺失值，也不能把总量全算成物理伤害。
            painter.setBrush(UNSPLIT_COLOR[isDarkTheme()])
            painter.drawRect(QRectF(0, 0, fillWidth, h))
            return

        x = 0.0

        for key in SEGMENT_KEYS:
            value = getattr(self, key)

            if value <= 0:
                continue

            nextX = x + fillWidth * value / total
            painter.setBrush(QColor(colors[key]))
            painter.drawRect(QRectF(x, 0, nextX - x, h))
            x = nextX


class DamageDot(QWidget):
    """图例里的小色块（和伤害条共用同一份配色常量）"""

    def __init__(self, key, parent=None):
        super().__init__(parent)

        self.key = key
        self.setFixedSize(8, 8)

        qconfig.themeChangedFinished.connect(self.update)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(damageColors()[self.key]))
        painter.drawRoundedRect(
            QRectF(0, 0, self.width(), self.height()), 2, 2)


class DamageLegendWidget(QWidget):
    """三色图例。切视图时名称会变（物理伤害 / 物理承伤）"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.labels = []

        self.hBoxLayout = QHBoxLayout(self)
        self.hBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.hBoxLayout.setSpacing(14)

        for key in SEGMENT_KEYS:
            text = QLabel(self)
            text.setObjectName('legendText')
            self.labels.append(text)

            itemLayout = QHBoxLayout()
            itemLayout.setContentsMargins(0, 0, 0, 0)
            itemLayout.setSpacing(6)
            itemLayout.addWidget(DamageDot(key, self))
            itemLayout.addWidget(text)

            self.hBoxLayout.addLayout(itemLayout)

    def setLabels(self, texts):
        for label, text in zip(self.labels, texts):
            label.setText(text)


class DamageRowWidget(QWidget):
    """面板的一行：英雄头像 + 召唤师 ID + 伤害条 + 数值 + 占比"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # 普通 QWidget 默认不绘制 qss 背景：不设这个属性的话，
        # DamageRowWidget[current=true] 的底色和圆角根本不会出现，
        # 「我」那一行的高亮就是隐形的（实测像素级验证过）
        self.setAttribute(Qt.WA_StyledBackground, True)

        self.avatar = RoundIcon(None, 32, 2, 2, parent=self)

        self.nameLabel = QLabel(self)
        self.nameLabel.setObjectName('summonerNameLabel')
        self.nameLabel.setFixedWidth(132)

        self.championLabel = QLabel(self)
        self.championLabel.setObjectName('championNameLabel')
        self.championLabel.setFixedWidth(132)

        self.textLayout = QVBoxLayout()
        self.textLayout.setContentsMargins(0, 0, 0, 0)
        self.textLayout.setSpacing(0)
        self.textLayout.addWidget(self.nameLabel)
        self.textLayout.addWidget(self.championLabel)

        self.bar = DamageBarWidget(self)

        self.valueLabel = QLabel(self)
        self.valueLabel.setObjectName('damageValueLabel')
        self.valueLabel.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.valueLabel.setMinimumWidth(62)

        self.pctLabel = QLabel(self)
        self.pctLabel.setObjectName('damagePctLabel')
        self.pctLabel.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
        self.pctLabel.setFixedWidth(44)

        self.hBoxLayout = QHBoxLayout(self)
        self.hBoxLayout.setContentsMargins(8, 5, 8, 5)
        self.hBoxLayout.setSpacing(12)
        self.hBoxLayout.addWidget(self.avatar)
        self.hBoxLayout.addLayout(self.textLayout)
        self.hBoxLayout.addWidget(self.bar, 1)
        self.hBoxLayout.addWidget(self.valueLabel)
        self.hBoxLayout.addWidget(self.pctLabel)

    def setInfo(self, info, ratio):
        """`info` 见 DamageGroupWidget.setTeam 的说明；`ratio` 是条长基准比例"""
        isMe = bool(info.get('isMe'))

        # 动态属性变了必须重新 polish，否则 qss 里的属性选择器不会重新求值。
        # 子控件的后代选择器（> QLabel#summonerNameLabel）也要一并重新 polish，
        # 只 polish 自己不生效。
        self.setProperty('current', isMe)

        for widget in (self, self.nameLabel):
            widget.style().unpolish(widget)
            widget.style().polish(widget)

        self.avatar.setIcon(info.get('icon'))

        self.nameLabel.setText(info.get('name', ''))
        self.championLabel.setText(info.get('champion', ''))
        self.valueLabel.setText(f"{info.get('total', 0):,}")
        self.pctLabel.setText(f"{info.get('share', 0.0):.1f}%")

        self.bar.setData(info.get('physical', 0), info.get('magic', 0),
                         info.get('real', 0), ratio, info.get('unsplit', False))


class DamageGroupWidget(QWidget):
    """一个阵营：阵营标签 + 团队合计 + 若干行"""

    def __init__(self, parent=None):
        super().__init__(parent)

        # chip 必须定死尺寸：QFrame 放进 QHBoxLayout 会被纵向拉伸成一大块
        self.sideChip = NoBorderColorAnimationFrame(type='win', parent=self)
        self.sideChip.setBorderRadius(4)
        self.sideChip.setFixedHeight(22)
        self.sideChip.setSizePolicy(QSizePolicy.Fixed, QSizePolicy.Fixed)

        self.sideLabel = QLabel(self)
        self.sideLabel.setObjectName('sideLabel')
        self.sideLabel.setContentsMargins(8, 0, 8, 0)

        chipLayout = QHBoxLayout(self.sideChip)
        chipLayout.setContentsMargins(0, 0, 0, 0)
        chipLayout.addWidget(self.sideLabel)

        self.totalCaption = QLabel(self)
        self.totalCaption.setObjectName('teamTotalCaption')

        self.totalValue = QLabel(self)
        self.totalValue.setObjectName('teamTotalValue')

        self.headLayout = QHBoxLayout()
        self.headLayout.setContentsMargins(8, 0, 8, 0)
        self.headLayout.setSpacing(6)
        self.headLayout.addWidget(self.sideChip)
        self.headLayout.addStretch(1)
        self.headLayout.addWidget(self.totalCaption)
        self.headLayout.addWidget(self.totalValue)

        self.rowsWidget = QWidget(self)
        self.rowsLayout = QVBoxLayout(self.rowsWidget)
        self.rowsLayout.setContentsMargins(0, 0, 0, 0)
        self.rowsLayout.setSpacing(0)

        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(0, 0, 0, 0)
        self.vBoxLayout.setSpacing(4)
        self.vBoxLayout.addLayout(self.headLayout)
        self.vBoxLayout.addWidget(self.rowsWidget)

        self.rows = []

    def setTeam(self, text, resultType, caption, totalText, rows):
        """
        text:       阵营标签文本，如「我方 · 胜利」
        resultType: 'win' / 'lose'（决定 chip 底色，走 cfg 里的自定义胜负色）
        caption:    合计说明，如「团队总伤害」
        totalText:  合计数值（已格式化）
        rows:       [(info, ratio), ...]，顺序由调用方按降序排好
        """
        self.sideLabel.setText(text)
        self.totalCaption.setText(caption)
        self.totalValue.setText(totalText)

        # chip 的颜色类型只能建一次，切换时重新注册颜色
        if self.sideChip.type != resultType:
            self.sideChip.setType(resultType)

        self.__rebuildRows(rows)

    def __rebuildRows(self, rows):
        # 行数按数据重建：默认 5v5，但不写死，免得遇到非常规模式时错位
        while self.rowsLayout.count():
            item = self.rowsLayout.takeAt(0)
            widget = item.widget()

            if widget is not None:
                widget.setParent(None)
                widget.deleteLater()

        self.rows = []

        for info, ratio in rows:
            row = DamageRowWidget(self.rowsWidget)
            row.setInfo(info, ratio)
            self.rowsLayout.addWidget(row)
            self.rows.append(row)
