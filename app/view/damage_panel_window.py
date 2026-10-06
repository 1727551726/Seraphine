import asyncio
import time

from PyQt5.QtGui import QIcon, QShowEvent
from PyQt5.QtWidgets import (QApplication, QHBoxLayout, QLabel, QVBoxLayout,
                             QWidget)

from app.common.config import cfg
from app.common.logger import logger
from app.common.qfluentwidgets import Pivot
from app.common.style_sheet import StyleSheet
from app.lol.connector import connector
from app.components.damage_panel import DamageGroupWidget, DamageLegendWidget
from app.view.opgg_window import OpggWindowBase

TAG = 'DamagePanelWindow'
# 对局结束后这几个阶段才拿得到结算数据（和 gameflow_interface 的判断保持一致）
POST_GAME_STATUS = ('PreEndOfGame', 'WaitingForStats', 'EndOfGame')

# 结算数据不是游戏一结束就立刻可取，失败要重试
FETCH_RETRY = 8
FETCH_INTERVAL = 3.0

# 距离屏幕右上角的留白
SCREEN_MARGIN = 16

VIEW_DEALT = 'dealt'
VIEW_TAKEN = 'taken'

# 结算数据里各字段的候选名。match-history 与 eog-stats 两套命名不同，
# 这里按候选顺序取第一个有效值，取不到就退化，不用 0 冒充。
STAT_KEYS = {
    VIEW_DEALT: {
        'physical': ('physicalDamageDealtToChampions',
                     'PHYSICAL_DAMAGE_DEALT_TO_CHAMPIONS'),
        'magic': ('magicDamageDealtToChampions',
                  'magicalDamageDealtToChampions',
                  'MAGIC_DAMAGE_DEALT_TO_CHAMPIONS'),
        'real': ('trueDamageDealtToChampions',
                 'TRUE_DAMAGE_DEALT_TO_CHAMPIONS'),
        'total': ('totalDamageDealtToChampions',
                  'TOTAL_DAMAGE_DEALT_TO_CHAMPIONS'),
    },
    VIEW_TAKEN: {
        'physical': ('physicalDamageTaken', 'PHYSICAL_DAMAGE_TAKEN'),
        # 实测（真实 LCU 数据）字段名是 magicalDamageTaken，不是 magicDamageTaken。
        # 写成后者会让魔法承伤全是 0，而且缺口会被算进物理伤害。
        'magic': ('magicalDamageTaken', 'magicDamageTaken',
                  'MAGIC_DAMAGE_TAKEN'),
        'real': ('trueDamageTaken', 'TRUE_DAMAGE_TAKEN'),
        'total': ('totalDamageTaken', 'TOTAL_DAMAGE_TAKEN'),
    },
}

# 本模块会调用的 connector 方法名。retry 装饰器耗尽重试时会把函数名
# 通过 signalBus.lcuApiExceptionRaised 发出去，main_window 据此让路。
PANEL_APIS = frozenset(('getCurrentSummoner', 'getSummonerGamesByPuuid',
                        'getGameDetailByGameId', 'getGameflowSession'))

# 伤害面板是否正在静默重试取数
_quietFetch = False


def setFetchingQuietly(active):
    global _quietFetch
    _quietFetch = active


def isFetchingQuietly():
    """取数失败是「结算数据还没准备好」这种预期情况，不该弹 LCU 错误提示"""
    return _quietFetch


def isWin(value):
    """判断队伍是否获胜。

    实测 LCU 这个字段是字符串 'Win'/'Fail' 而不是布尔 —— 直接 bool('Fail')
    会得到 True，于是两个队伍都会被标成「胜利」，输的那局也显示我方胜利。
    这里同时兼容布尔，免得接口哪天又变。
    """
    if isinstance(value, bool):
        return value

    return str(value).strip().lower() in ('win', 'true', '1')


def largestRemainder(values, total, digits=1):
    """最大余数法：让整列百分比的显示值之和，等于精确值之和的四舍五入结果。

    调用方保证 `total == sum(values)` 时，结果就精确合计 100.0%。
    每行各自四舍五入会得到 99.9% / 100.1% 这种合计偏差，在数据面板里是硬伤。
    """
    scale = 10 ** digits

    if not values or not total:
        return [0.0] * len(values)

    exact = [v / total * 100 * scale for v in values]
    out = [int(v) for v in exact]

    # 目标值取精确值之和，而不是硬写 100*scale ——
    # 否则 total 与 sum(values) 不一致时结果会离谱
    rest = round(sum(exact)) - sum(out)

    order = sorted(range(len(exact)), key=lambda i: exact[i] - int(exact[i]),
                   reverse=True)

    for i in order:
        if rest <= 0:
            break
        out[i] += 1
        rest -= 1

    return [v / scale for v in out]


def statValue(stats, keys):
    """按候选字段名取第一个数值，都没有就返回 None"""
    for key in keys:
        value = stats.get(key)

        if isinstance(value, (int, float)):
            return int(value)

    return None


def buildDamage(stats, view):
    """把一个玩家的结算 stats 整理成某个视图下的三段 + 总量"""
    keys = STAT_KEYS[view]
    physical = statValue(stats, keys['physical']) or 0
    magic = statValue(stats, keys['magic']) or 0
    real = statValue(stats, keys['real']) or 0
    total = statValue(stats, keys['total'])

    if total is None:
        total = physical + magic + real

    resolved = physical + magic + real

    return {
        'physical': physical,
        'magic': magic,
        'real': real,
        'total': total,
        # 三段之和明显对不上总量时也要退化：说明有字段没取到。
        # 否则缺失的那部分会被画成物理伤害（unsplit=False），等于给出错误结论。
        # 完全取不到（resolved==0）但总量有值同理。
        'unsplit': total > 0 and resolved < total * 0.98,
    }


def secondsToStr(seconds):
    """秒 -> mm:ss（非数值一律当 0，不让脏数据把面板搞崩）"""
    try:
        seconds = max(int(seconds), 0)
    except (TypeError, ValueError):
        seconds = 0

    return f'{seconds // 60}:{seconds % 60:02d}'


class DamagePanelWindow(OpggWindowBase):
    """对局结束后自动弹出的伤害面板（贴屏幕右上角）"""

    def __init__(self, parent=None):
        super().__init__(parent)

        self.view = VIEW_DEALT
        self.teams = None
        self.__busy = False
        self.__pending = False
        self.__closed = False
        self.__topMost = False
        self.__shownGameId = None

        self.viewTexts = {
            VIEW_DEALT: {
                'legend': (self.tr('物理伤害'), self.tr('魔法伤害'),
                           self.tr('真实伤害')),
                'total': self.tr('团队总伤害'),
            },
            VIEW_TAKEN: {
                'legend': (self.tr('物理承伤'), self.tr('魔法承伤'),
                           self.tr('真实承伤')),
                'total': self.tr('团队总承伤'),
            },
        }

        self.__initWindow()
        self.__initLayout()

        StyleSheet.DAMAGE_PANEL_WINDOW.apply(self)

    def __initWindow(self):
        self.setWindowTitle(self.tr('伤害统计'))
        self.setWindowIcon(QIcon('app/resource/images/game.png'))
        self.setFixedWidth(640)

    def __initLayout(self):
        self.subtitleLabel = QLabel(self)
        self.subtitleLabel.setObjectName('subtitleLabel')

        self.pivot = Pivot(self)
        # 注意：PyQt-Fluent-Widgets 1.5.7 的 Pivot 没有 currentItemChanged 信号，
        # 切换只能靠 addItem 的 onClick（它接的是 PivotItem.itemClicked(bool)）
        self.pivot.addItem(
            VIEW_DEALT, self.tr('造成伤害'),
            onClick=lambda _: self.__onViewChanged(VIEW_DEALT))
        self.pivot.addItem(
            VIEW_TAKEN, self.tr('承受伤害'),
            onClick=lambda _: self.__onViewChanged(VIEW_TAKEN))
        self.pivot.setItemFontSize(14)

        self.legend = DamageLegendWidget(self)

        self.tabsRow = QWidget(self)
        self.tabsRow.setObjectName('tabsRow')
        self.tabsLayout = QHBoxLayout(self.tabsRow)
        self.tabsLayout.setContentsMargins(0, 0, 0, 0)
        self.tabsLayout.setSpacing(12)
        self.tabsLayout.addWidget(self.pivot)
        self.tabsLayout.addStretch(1)
        self.tabsLayout.addWidget(self.legend)

        self.allyGroup = DamageGroupWidget(self)
        self.enemyGroup = DamageGroupWidget(self)

        self.vBoxLayout = QVBoxLayout(self)
        self.vBoxLayout.setContentsMargins(24, 24, 24, 24)
        self.vBoxLayout.setSpacing(12)
        self.vBoxLayout.addWidget(self.subtitleLabel)
        self.vBoxLayout.addWidget(self.tabsRow)
        self.vBoxLayout.addWidget(self.allyGroup)
        self.vBoxLayout.addWidget(self.enemyGroup)
        self.vBoxLayout.addStretch(1)

        self.pivot.setCurrentItem(VIEW_DEALT)

    # ------------------------------------------------------------------ 取数

    async def __fetchGameDetail(self):
        """拿「刚刚结束的那一局」的对局详情，拿不到返回 None"""
        summoner = await connector.getCurrentSummoner()
        puuid = summoner.get('puuid')

        if not puuid:
            return None

        # 匹配历史有延迟时 games[0] 会还是上一局。直接弹就会显示错的对局，
        # 而且 __shownGameId 会把正确那一局永久挡掉。所以优先用 gameflow
        # session 里的 gameId —— 那才是「刚打完这局」的权威依据。
        expectedGameId = None

        try:
            session = await connector.getGameflowSession()
            expectedGameId = ((session or {}).get('gameData') or {}).get('gameId')
        except Exception:
            expectedGameId = None

        if expectedGameId:
            game = await connector.getGameDetailByGameId(expectedGameId)
        else:
            games = (await connector.getSummonerGamesByPuuid(puuid, 0, 1))['games']

            if not games:
                return None

            game = await connector.getGameDetailByGameId(games[0]['gameId'])

        if not game.get('participants'):
            return None

        if not self.__isJustFinished(game):
            # 拿到的不是刚打完的那局（session 过期 / 匹配历史滞后），
            # 宁可这一轮不弹，等下一次重试
            return None

        return game, puuid

    def __isJustFinished(self, game):
        """这局是不是刚刚结束的？

        用 gameCreation + gameDuration 得到结束时间，和当前时间比。
        刚打完的局误差只有几秒；如果是上一局，通常会差几十分钟。
        时钟可能和服务器有偏差，所以给 15 分钟宽限。
        """
        try:
            creation = float(game.get('gameCreation') or 0)
            duration = float(game.get('gameDuration') or 0)
        except (TypeError, ValueError):
            return True

        if creation <= 0:
            return True

        endTime = (creation + duration * 1000) / 1000
        now = time.time()

        return -60 <= (now - endTime) <= 15 * 60

    async def __buildData(self, game, myPuuid):
        """把对局详情整理成面板数据"""
        identities = {}

        for item in game.get('participantIdentities', []):
            identities[item.get('participantId')] = item.get('player') or {}

        teams = {}

        for participant in game.get('participants', []):
            stats = participant.get('stats') or {}
            player = identities.get(participant.get('participantId')) or {}
            puuid = player.get('puuid') or ''
            championId = participant.get('championId', 0)

            name = player.get('gameName') or player.get('summonerName') or ''
            tagLine = player.get('tagLine') or ''

            if tagLine:
                name = f'{name}#{tagLine}'

            teamId = participant.get('teamId', 100)

            if teamId == 0:
                # 和下面 wins 的处理保持一致：teamId 0 即 200。
                # 不统一的话 wins.get(0) 取不到值，会被误判成失败
                teamId = 200

            teams.setdefault(teamId, []).append({
                'name': name or self.tr('未知玩家'),
                'champion': connector.manager.getChampionNameById(championId),
                'icon': await connector.getChampionIcon(championId),
                'isMe': bool(puuid) and puuid == myPuuid,
                'dealt': buildDamage(stats, VIEW_DEALT),
                'taken': buildDamage(stats, VIEW_TAKEN),
            })

        if not teams:
            return None

        wins = {}

        for team in game.get('teams', []):
            teamId = team.get('teamId', 100)
            # 注意：这个字段实测是字符串 'Win'/'Fail'，不是布尔
            wins[200 if teamId == 0 else teamId] = isWin(team.get('win'))

        myTeamId = None

        for teamId, players in teams.items():
            if any(p['isMe'] for p in players):
                myTeamId = teamId
                break

        if myTeamId is None:
            # 认不出本人（比如观战/回放），就把 100 当己方
            myTeamId = 100 if 100 in teams else sorted(teams)[0]

        enemyTeamId = next((tid for tid in teams if tid != myTeamId), None)

        # 竞技场（斗魂竞技场）这类多小队模式没有「队伍胜负」这个概念：
        # 玩家实际名次看 subteamPlacement，teamId 100/200 上的 win 没有意义。
        # 这种模式下不要在标签上声称胜负，只显示阵营，免得给出错误结论。
        isSubteamMode = game.get('mapId') == 30 or game.get('queueId') == 1700

        def teamLabel(sideText, win):
            if isSubteamMode:
                return sideText

            return sideText + ' · ' + (self.tr('胜利') if win else self.tr('失败'))

        return {
            'gameId': game.get('gameId'),
            'subtitle': self.__buildSubtitle(game),
            'teams': [
                {
                    'label': teamLabel(self.tr('我方'), wins.get(myTeamId)),
                    'win': wins.get(myTeamId, False),
                    'neutral': isSubteamMode,
                    'players': teams[myTeamId],
                },
                {
                    'label': teamLabel(self.tr('敌方'), wins.get(enemyTeamId)),
                    'win': wins.get(enemyTeamId, False),
                    'neutral': isSubteamMode,
                    'players': teams.get(enemyTeamId, []),
                },
            ],
        }

    def __buildSubtitle(self, game):
        """召唤师峡谷 · 单双排位 · 32:14"""
        parts = []

        try:
            nameMap = connector.manager.getNameMapByQueueId(
                game.get('queueId', 0)) or {}
            parts.append(nameMap.get('map') or '')
            parts.append(nameMap.get('name') or '')
        except Exception:
            parts.append(game.get('gameMode') or '')

        parts.append(secondsToStr(game.get('gameDuration')))

        return ' · '.join([p for p in parts if p])

    # ------------------------------------------------------------------ 展示

    async def fetchAndShow(self):
        """拉结算数据并弹出面板。

        游戏刚结束时结算数据往往还没准备好，所以这里带重试；
        整个过程失败只记日志，不弹任何错误提示打扰用户
        （取数期间会给 main_window 的 LCU 报错提示让路，见 PANEL_APIS）。

        对局结束会连着来好几个阶段（PreEndOfGame / WaitingForStats / EndOfGame），
        本方法会被调用多次：正在跑的那一轮不会被后来的调用打断，但会记一个
        pending，等这一轮跑完再补跑一轮 —— 否则第一轮没抢到数据时，
        后面明明有数据的阶段会被直接丢掉，面板永远不出来。
        """
        if not cfg.get(cfg.enableDamagePanel):
            return

        if self.__busy:
            self.__pending = True
            return

        self.__busy = True
        setFetchingQuietly(True)

        try:
            while True:
                self.__pending = False

                if await self.__fetchOnce():
                    return

                if not self.__pending:
                    return
        finally:
            setFetchingQuietly(False)
            self.__busy = False

    async def __fetchOnce(self):
        """重试若干次去取数；成功弹出返回 True"""
        for attempt in range(FETCH_RETRY):
            try:
                detail = await self.__fetchGameDetail()

                if detail:
                    data = await self.__buildData(*detail)

                    if data:
                        gameId = data.get('gameId')

                        # gameId 拿不到时不能和初始的 None 相等就当作「已弹过」，
                        # 那会让面板永远不出现
                        if gameId is not None and gameId == self.__shownGameId:
                            return True

                        self.__shownGameId = gameId

                        if self.__closed:
                            # 面板已经被关掉了（比如用户关了应用），别再 show 出幽灵窗口
                            return True

                        self.setData(data)
                        # 先摆好位置再置顶：setStayOnTop() 内部会调用 show()，
                        # 顺序反了会先在默认位置闪一下
                        self.adjustPosition()
                        self.__ensureStayOnTop()
                        self.show()
                        self.raise_()
                        return True
            except Exception as e:
                logger.warning(f'伤害面板第 {attempt + 1} 次取数失败: {e}', TAG)

            await asyncio.sleep(FETCH_INTERVAL)

        logger.warning('伤害面板: 重试耗尽，仍未拿到结算数据', TAG)

        return False

    def closeEvent(self, e):
        self.__closed = True

        return super().closeEvent(e)

    def __ensureStayOnTop(self):
        """让小窗自动置顶。

        只在第一次显示前设一次标志：改动窗口 flag 会让已经显示的窗口隐藏，
        重复调用会闪一下；而且 setStayOnTop() 内部自己会 show()，
        所以绝不能在建窗时调 —— 那样应用一启动就会冒出这个窗口。
        """
        if self.__topMost:
            return

        self.__topMost = True
        self.setStayOnTop(True)

    def setData(self, data):
        self.subtitleLabel.setText(data.get('subtitle', ''))
        self.teams = data.get('teams') or []

        self.__refresh()
        self.adjustSize()

    def __onViewChanged(self, routeKey):
        if routeKey not in self.viewTexts or routeKey == self.view:
            return

        self.view = routeKey
        self.__refresh()

    def __refresh(self):
        if not self.teams:
            return

        self.legend.setLabels(self.viewTexts[self.view]['legend'])

        for groupWidget, team in zip((self.allyGroup, self.enemyGroup),
                                     self.teams):
            self.__fillGroup(groupWidget, team)

    def __fillGroup(self, groupWidget, team):
        """按当前视图给一个阵营排序、算占比，再交给控件去画"""
        view = self.view
        players = sorted(team.get('players', []),
                         key=lambda p: p[view]['total'], reverse=True)

        totals = [p[view]['total'] for p in players]
        teamTotal = sum(totals)
        groupMax = totals[0] if totals else 0
        shares = largestRemainder(totals, teamTotal)

        rows = []

        for player, share in zip(players, shares):
            damage = player[view]

            rows.append(({
                'name': player['name'],
                'champion': player['champion'],
                'icon': player['icon'],
                'isMe': player['isMe'],
                'share': share,
                'unsplit': damage['unsplit'],
                'total': damage['total'],
                'physical': damage['physical'],
                'magic': damage['magic'],
                'real': damage['real'],
            }, (damage['total'] / groupMax) if groupMax else 0.0))

        # 多小队模式下 chip 用中性灰（remake 那套颜色），不要给出绿/红的胜负暗示
        if team.get('neutral'):
            resultType = 'remake'
        else:
            resultType = 'win' if team.get('win') else 'lose'

        groupWidget.setTeam(
            text=team.get('label', ''),
            resultType=resultType,
            caption=self.viewTexts[view]['total'],
            totalText=f'{teamTotal:,}',
            rows=rows)

    # ------------------------------------------------------------------ 定位

    def adjustPosition(self):
        """贴到主屏右上角。

        availableGeometry() 已经是逻辑像素、且已经排除任务栏，
        所以不要再乘 devicePixelRatioF()（那是 getLolClientWindowPos 那套才需要的）。
        """
        screen = QApplication.primaryScreen()

        if screen is None:
            return

        rect = screen.availableGeometry()
        self.move(rect.right() - self.width() + 1 - SCREEN_MARGIN,
                  rect.top() + SCREEN_MARGIN)

    def showEvent(self, a0: QShowEvent) -> None:
        self.adjustPosition()

        return super().showEvent(a0)
