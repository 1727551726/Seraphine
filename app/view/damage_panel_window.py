import asyncio
import time

import win32con
import win32gui
from PyQt5.QtCore import Qt, QTimer
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

# 结算数据不是游戏一结束就立刻可取：客户端要把这一局写进匹配历史，
# 期间详情接口只会返回没有 participants 的空壳，所以要留足够长的重试窗口
# （实测索引延迟可达几十秒）。20 次 × 3 秒 ≈ 60 秒。
FETCH_RETRY = 20
FETCH_INTERVAL = 3.0

# 回退到匹配历史时的时效宽限，必须比 session 候选严格得多：
# 本局还没进匹配历史索引时，列表里最近一局就是**上一局**，
# 用宽泛的 15 分钟判定会把上一局的数据当成刚打完这局弹出来
# （大乱斗、重开、早期投降这些短局恰好会命中）。
HISTORY_TOLERANCE = 3 * 60

# session 候选的时效上限。它是权威依据，理论上不需要校验，但同一接口有
# 「数据陈旧」的先例（connector 里有 FIXME 记录该接口会返回上一局的队员信息），
# 万一 gameData 残留一个已结算的旧局，不设上限就会把更早的一局当成本局弹出。
# 刚结束的局必在几分钟内，所以 1 小时的上限绝不会误拒。
SESSION_MAX_AGE = 60 * 60

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
                        'getGameDetailByGameId', 'getGameflowSession',
                        'getChampionIcon'))

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
        self.__shuttingDown = False
        self.__topMost = False
        self.__shownGameId = None
        # 诊断用：记录最近一次取数走到哪一步、最后一次异常。
        # 本仓库默认日志级别是 40(ERROR)，warning 级根本不会落盘，
        # 所以最终失败必须以 error 级输出并把这两项带上，否则无从查起。
        self.__lastProbe = '尚未取数'
        self.__lastError = None

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
        # 主窗口可能已经最小化到托盘，此时用户关掉面板就是「关掉最后一个窗口」，
        # 默认会连带退出整个应用 —— 关面板应该是正常操作，不该退出应用
        self.setAttribute(Qt.WA_QuitOnClose, False)

        # 弹出后自动关闭（设置项，默认开启 15 秒）
        self.__autoCloseTimer = QTimer(self)
        self.__autoCloseTimer.setSingleShot(True)
        self.__autoCloseTimer.timeout.connect(self.close)

        # 面板还挂在屏幕上时改设置，立刻按新值重排定时器（否则要等下一局）
        cfg.damagePanelAutoCloseDelay.valueChanged.connect(
            self.__onAutoCloseSettingChanged)
        cfg.enableDamagePanelAutoClose.valueChanged.connect(
            self.__onAutoCloseSettingChanged)

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

    async def __fetchGameDetail(self, attempt=0):
        """拿「刚刚结束的那一局」的对局详情，拿不到返回 None

        这里有三个坑（都是拿真实对局踩出来的）：

        1. 对局刚结束时，gameflow session 里已经有 gameData.gameId 了，
           但详情接口 /lol-match-history/v1/games/{id} 对「还没结算完」的局
           会返回一个**没有 participants 的空壳**。直接当失败处理、
           又拿同一个 id 反复重试的话，永远拿不到数据。
        2. 匹配历史**列表**接口的条目前只含自己那 1 个 participant，
           不能拿来当 10 人数据用；而且列表索引到这一局也有延迟。
        3. 本局还没进列表索引时，列表里最近一局就是**上一局**，
           拿它当结果会弹出上一局的数据（比不弹更严重）。

        所以：session 的 gameId 优先（它是权威的，不需要时间校验，只校验
        gameId 对得上 + 人数 > 1 + 时长已结算）；只有 session 拿不到时才回退
        匹配历史，且回退候选必须「刚刚结束」（HISTORY_TOLERANCE）。
        每条失败路径都写进 self.__lastProbe，最终失败时随 error 日志输出。
        """
        summoner = await connector.getCurrentSummoner()
        puuid = summoner.get('puuid')

        if not puuid:
            self.__lastProbe = '拿不到当前召唤师 puuid'
            return None

        reasons = []
        expectedGameId = None

        try:
            session = await connector.getGameflowSession()
            expectedGameId = ((session or {}).get('gameData') or {}).get('gameId')
        except (asyncio.CancelledError, SystemExit, KeyboardInterrupt):
            raise
        except BaseException as e:
            # 注意：本仓库自定义异常全部继承 BaseException 而不是 Exception，
            # 写成 except Exception 会兜不住，异常漏出去会把整个协程干掉
            self.__lastError = f'getGameflowSession: {type(e).__name__}: {e}'
            reasons.append(f'session 取数失败: {type(e).__name__}')

        # ── 候选 1：session 里的 gameId（权威）──
        if expectedGameId:
            detail = await connector.getGameDetailByGameId(expectedGameId)

            if not isinstance(detail, dict) or not self.__sameId(
                    detail.get('gameId'), expectedGameId):
                reasons.append(
                    f'session gameId={expectedGameId} 详情是空壳'
                    f'（该局还没结算完）[{self.__detailBrief(detail)}]')
            elif len(detail.get('participants') or []) < 2:
                reasons.append(
                    f'session gameId={expectedGameId} 只有 '
                    f'{len(detail.get("participants") or [])} 个 participant')
            elif not self.__isJustFinished(detail, SESSION_MAX_AGE, strict=True):
                # 陈旧数据兜底：只在超过 1 小时时才拒（刚打完的局不可能超）
                reasons.append(
                    f'session gameId={expectedGameId} 超过时效上限'
                    f'（{self.__endTimeBrief(detail)}）')
            elif not (detail.get('gameDuration') or 0) and attempt < FETCH_RETRY // 2:
                # 已入索引但时长还没结算完：前半段先等，绝不回退匹配历史 ——
                # 那一刻列表里最近一局还是上一局
                self.__lastProbe = (
                    f'session gameId={expectedGameId} 已入索引但时长未结算，等下一轮')
                return None
            else:
                # 后半段即使时长仍为 0 也放行：代价只是副标题显示 0:00，
                # 伤害数据是对的；否则极短的重开局可能永远等不到
                self.__lastProbe = (
                    f'session gameId={expectedGameId} OK'
                    f'（{len(detail.get("participants") or [])} 人）')
                return detail, puuid

        # ── 候选 2：匹配历史最近一局（只在 session 拿不到时用）──
        try:
            games = (await connector.getSummonerGamesByPuuid(puuid, 0, 2))['games']
        except (asyncio.CancelledError, SystemExit, KeyboardInterrupt):
            raise
        except BaseException as e:
            # 同样不能漏出去；失败就不回退，继续等 session 候选可用
            self.__lastError = f'getSummonerGamesByPuuid: {type(e).__name__}: {e}'
            reasons.append(f'匹配历史请求失败: {type(e).__name__}')
            games = []

        for game in games[:2]:
            gameId = game.get('gameId')

            if not gameId or self.__sameId(gameId, expectedGameId):
                continue

            # 回退候选必须「刚刚结束」：本局还没进索引时，列表里最近一局
            # 就是上一局，用宽泛的 15 分钟判定会把上一局的数据弹出来。
            # strict=True：时间字段缺失即判为不是刚结束的（fail-closed），
            # 因为残缺条目恰恰会缺字段
            if not self.__isJustFinished(game, HISTORY_TOLERANCE, strict=True):
                reasons.append(
                    f'历史 gameId={gameId} 不是刚结束的（{self.__endTimeBrief(game)}）')
                continue

            detail = await connector.getGameDetailByGameId(gameId)

            if not isinstance(detail, dict) or not self.__sameId(
                    detail.get('gameId'), gameId):
                reasons.append(
                    f'历史 gameId={gameId} 详情不可用[{self.__detailBrief(detail)}]')
                continue

            count = len(detail.get('participants') or [])

            if count < 2:
                reasons.append(f'历史 gameId={gameId} 只有 {count} 个 participant')
                continue

            self.__lastProbe = f'历史 gameId={gameId} OK（{count} 人）'
            return detail, puuid

        if not reasons:
            reasons.append('没有可用的候选对局')

        # 把每个候选失败的原因都留下，日志里能看到完整判断过程
        self.__lastProbe = '候选对局都不可用: ' + '; '.join(reasons)

        return None

    @staticmethod
    def __sameId(a, b):
        """gameId 可能是 int 也可能是 str，直接 != 会把「已就绪」误判成「空壳」"""
        return a is not None and b is not None and str(a) == str(b)

    @staticmethod
    def __detailBrief(detail):
        """空壳到底是 404、errorCode 还是别的，记下来才知道怎么对症"""
        if not isinstance(detail, dict):
            return f'响应类型 {type(detail).__name__}'

        keys = ','.join(sorted(detail.keys())[:6])
        err = (detail.get('errorCode') or detail.get('httpStatus')
               or detail.get('message'))

        return f'keys={keys}' + (f' err={err}' if err else '')

    @staticmethod
    def __endTimeBrief(game):
        creation = game.get('gameCreation') or 0
        duration = game.get('gameDuration') or 0
        end = (creation + duration * 1000) / 1000

        return (f'结束于 {time.strftime("%m-%d %H:%M", time.localtime(end))}，'
                f'距今 {(time.time() - end) / 60:.0f} 分钟')

    def __isJustFinished(self, game, tolerance, strict=False):
        """这局是不是刚刚结束的？

        用 gameCreation + gameDuration 得到结束时间，和当前时间比。
        刚打完的局误差只有几秒；如果是上一局，通常会差几十分钟。

        时钟可能和服务器有偏差，所以留一点宽限；宽限大小由调用方给 ——
        「防弹上一局」的判据必须用很小的值（见 HISTORY_TOLERANCE）。

        strict=True 时，时间字段缺失或无效一律判为「不是刚结束的」：
        LCU 的残缺/空壳条目恰恰会缺这些字段，fail-open 会放进错误对局。
        """
        try:
            creation = float(game.get('gameCreation') or 0)
            duration = float(game.get('gameDuration') or 0)
        except (TypeError, ValueError):
            return not strict

        if creation <= 0:
            return not strict

        endTime = (creation + duration * 1000) / 1000
        now = time.time()

        return -60 <= (now - endTime) <= tolerance

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
                detail = await self.__fetchGameDetail(attempt)

                if detail:
                    data = await self.__buildData(*detail)

                    if data:
                        gameId = data.get('gameId')

                        # gameId 拿不到时不能和初始的 None 相等就当作「已弹过」，
                        # 那会让面板永远不出现
                        if gameId is not None and gameId == self.__shownGameId:
                            return True

                        if self.__shuttingDown:
                            # 应用正在退出，别再 show 出幽灵窗口
                            return True

                        self.__showPanel(data)

                        # 必须放在「确认真的显示出来了」之后：
                        # 之前记在 show() 之前，一旦中间抛异常，重试时会因为
                        # gameId 相同而直接判定「已弹过」并静默放弃，
                        # 留下一个「有数据、已定位、已置顶、但不可见」的窗口。
                        self.__shownGameId = gameId

                        return True
                    else:
                        # __buildData 解析不出队伍时不抛异常，不加这句的话
                        # __lastProbe 会停在「…OK（10 人）」，最终日志自相矛盾
                        self.__lastProbe += ' | __buildData 解析不出面板数据'
            except (asyncio.CancelledError, SystemExit, KeyboardInterrupt):
                # 取消不是取数失败，必须原样放出去
                raise
            except BaseException as e:
                # 必须用 BaseException：本仓库自定义异常（SummonerGamesNotFound、
                # RetryMaximumAttempts 等）全部继承 BaseException 而不是 Exception，
                # 写成 except Exception 会让它们直接干掉整个协程，
                # 连下面那条汇总 error 日志都留不下来 —— 那正是最难查的静默失败
                self.__lastError = f'{type(e).__name__}: {e}'
                logger.warning(f'伤害面板第 {attempt + 1} 次取数失败: {e}', TAG)

            await asyncio.sleep(FETCH_INTERVAL)

        # 用 error 级：本仓库默认日志级别是 40，warning 不会落盘，
        # 那样「面板没弹」就成了完全无从查起的静默失败
        logger.error(
            f'对局伤害面板: 重试 {FETCH_RETRY} 次仍未弹出。'
            f'取数过程: {self.__lastProbe}'
            + (f' | 最后一次异常: {self.__lastError}' if self.__lastError else ''),
            TAG)

        return False

    def blockShowing(self):
        """应用正在退出时调用，阻止面板再被显示出来（避免退出瞬间闪出幽灵窗口）。

        注意：不要用 closeEvent 来判断 —— 用户手动关掉面板是正常操作，
        不该因此让这个面板在本次运行里再也不出现。
        """
        self.__shuttingDown = True

    def __showPanel(self, data):
        """填数据、定位、置顶、显示，并确认窗口真的可见了

        自检必须查到 Win32 层：实测出现过「Qt 的 isVisible() 为真、
        但原生窗口 IsWindowVisible 为假」的状态 —— 只信 Qt 的话，
        自检会通过、__shownGameId 被置位、自愈也就失效了。
        """
        self.setData(data)
        # 先摆好位置再置顶：setStayOnTop() 内部会调用 show()，
        # 顺序反了会先在默认位置闪一下
        self.adjustPosition()
        self.__ensureStayOnTop()
        self.show()
        self.raise_()

        # 先武装自动关闭定时器：下面显示自检在「一切正常」时会提前 return，
        # 放在末尾的话正常路径反而永远不启动定时器
        self.__restartAutoCloseTimer()

        hwnd = int(self.winId())

        # 自检绝不能反过来影响显示本身，所以整段都兜住
        try:
            qtVisible = self.isVisible()
            nativeVisible = win32gui.IsWindowVisible(hwnd)
        except BaseException as e:
            logger.error(f'对局伤害面板: 显示自检失败: {type(e).__name__}: {e}', TAG)
            return

        if qtVisible and nativeVisible:
            return

        # 两层都查：实测出现过「Qt 认为可见、原生窗口被隐藏」，
        # 反向不一致（Qt 隐藏、原生可见）也要一起补
        logger.error(
            f'对局伤害面板: 窗口未真正显示'
            f'(Qt isVisible={qtVisible} isHidden={self.isHidden()} '
            f'Win32 visible={nativeVisible} '
            f'flags={int(self.windowFlags()):#x} '
            f'geometry={self.geometry().x()},{self.geometry().y()} '
            f'{self.geometry().width()}x{self.geometry().height()})，正在兜底显示', TAG)

        try:
            if not qtVisible:
                self.show()
                self.raise_()

            if not win32gui.IsWindowVisible(hwnd):
                win32gui.ShowWindow(hwnd, win32con.SW_SHOW)
        except BaseException as e:
            logger.error(
                f'对局伤害面板: 兜底显示失败: {type(e).__name__}: {e}', TAG)
            return

        try:
            if not (self.isVisible() and win32gui.IsWindowVisible(hwnd)):
                logger.error(
                    f'对局伤害面板: 兜底显示后窗口仍不可见 (hwnd={hwnd})', TAG)
        except BaseException:
            pass

    def __onAutoCloseSettingChanged(self, *_):
        """设置页改了自动关闭相关项：面板正显示着就立刻生效"""
        if self.isVisible():
            self.__restartAutoCloseTimer()

    def __restartAutoCloseTimer(self):
        """按设置定时自动关闭面板

        每次弹出都重新读一遍配置，这样改完设置下一局就生效，
        不需要重启应用。设置项本身在设置页的二级菜单里（默认开启 15 秒）。
        """
        self.__autoCloseTimer.stop()

        if not cfg.get(cfg.enableDamagePanelAutoClose):
            return

        try:
            delay = int(cfg.get(cfg.damagePanelAutoCloseDelay) or 0)
        except (TypeError, ValueError):
            delay = 0

        if delay > 0:
            self.__autoCloseTimer.start(delay * 1000)

    def closeEvent(self, e):
        # 窗口关了就别留着定时器（用户手动关闭时同样停掉）
        self.__autoCloseTimer.stop()

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
