import re

from ok import BaseTask
from ok.device.interaction_methods.browser import BrowserInteraction
from ok.device.interaction_methods.pynput import PynputInteraction

from src.cloud_recovery import FatalTaskError, run_with_cloud_recovery
from src.task.rahai_blocks import HEIGHT, WIDTH, canonical_frame, choose_move, clear_lines, preview_matches, read_board
from src.task.task_icons import task_icon


STAGE_PROGRESS = re.compile(r"进行中.*?(\d+)\s*[/／]\s*(\d+)")
STAGE_STATUS = re.compile(r"进行中|已(?:通关|完成)|(?:\d+\s*(?:天|小时|分钟))")

# 手游(MuMu/安卓)端适配:
# - 无尽模式没有简单/困难难度选项, v1.5.18 起直接支持: 从无尽模式页面开始,
#   或加入已在进行中的无尽对局; 达到目标分数("达到9999分结算可得首通奖励")
#   后主动退出结算。
# - 开局会弹"无尽模式"玩法说明弹窗(居中"确认"按钮), 不点掉会挡住棋盘识别。
# - 手游详情页布局与 PC 有差异, 难度/开始按钮识别提供宽域 OCR 兜底。
ENDLESS_RE = re.compile(r"无尽模式|無盡模式")
ENDLESS_POPUP_RE = re.compile(r"玩家可以一直游玩|直到失败")
ENDLESS_INGAME_RE = re.compile(r"历史最高|歷史最高|达到\d+分结算|達到\d+分結算")
ENDLESS_GOAL_RE = re.compile(r"达到(\d+)分结算|達到(\d+)分結算")
ANDROID_DIFFICULTY_BOX = (.5, .05, 1.0, .7)


class ChallengeFailed(RuntimeError):
    pass


class RahaiBlocksTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "3.8 拉海洛方块·逆转"
        self.description = (
            "从活动关卡列表或关卡详情页开始，挑战所有已解锁且未通关的关卡；"
            "支持无尽模式（从无尽页面开始或直接加入进行中的对局，达到目标分数后自动结算）。"
            "支持简体中文 PC 客户端、云鸣潮与 MuMu/安卓模拟器"
            "（模拟器需保持 MuMu 窗口在前台）。"
        )
        self.group_name = "Daily Activities"
        self.group_icon = task_icon("category-daily")
        self.supported_languages = ["zh_CN"]

    def _make_interaction(self):
        """Browser mode uses Playwright's virtual input; PC mode uses real mouse."""
        capture = self.executor.device_manager.capture_method
        if self.is_browser():
            return BrowserInteraction(capture)
        return PynputInteraction(capture, self.hwnd)

    def _clickable(self, interaction):
        # BrowserInteraction has no clickable(): CDP input works without OS focus.
        return True if self.is_browser() else interaction.clickable()

    def _event_title(self):
        return self.ocr(.045, .04, .2, .09, match=re.compile(r"拉海洛方块"))

    def _stage_list(self):
        if not self._event_title():
            return []
        boxes = self.ocr(.045, .18, .965, .79)
        stages = []
        for status in boxes:
            y = status.center()[1] / self.height
            if not (.39 < y < .44 or .74 < y < .79) or not STAGE_STATUS.search(status.name):
                continue
            titles = [box for box in boxes if .18 < (status.y - box.y) / self.height < .23
                      and abs(status.x - box.x) < .025 * self.width]
            if titles:
                title = min(titles, key=lambda box: abs(status.x - box.x))
                stages.append((title, status))
        return sorted(stages, key=lambda stage: stage[1].x)

    def _challenge_button(self, wide=False):
        boxes = self.ocr(.69, .89, .96, .95, match="开始挑战")
        if boxes:
            return boxes[0]
        if wide:
            # 手游/无尽模式开始按钮位置可能偏移: 宽域兜底("开始"或"开始挑战")
            boxes = self.ocr(.60, .84, 1.0, 1.0, match=re.compile(r"^开始(?:挑战)?$"))
            if boxes:
                return boxes[0]
        return None

    def _stage_details(self):
        return self._event_title() and self.ocr(.68, .43, .82, .48, match="关卡目标")

    def _endless_page(self):
        """当前是否处于无尽模式(详情页/玩法弹窗/对局内)。无尽模式没有难度选项。"""
        return (self._event_title()
                and (self.ocr(.0, .10, .7, .75, match=ENDLESS_RE)
                     or self.ocr(.0, .10, .7, .75, match=ENDLESS_POPUP_RE)
                     or self.ocr(.0, .10, .35, .25, match=ENDLESS_INGAME_RE)))

    def _endless_ingame(self):
        """已在无尽模式对局内(玩法弹窗未关/局内计分 UI 可见/棋盘可见)。"""
        if not self._event_title():
            return False
        if (self.ocr(.0, .10, .7, .75, match=ENDLESS_POPUP_RE)
                or self.ocr(.0, .10, .35, .25, match=ENDLESS_INGAME_RE)):
            return True
        return bool(self._playable_board())

    def _selected_difficulty(self, difficulty, wide=False):
        """详情页当前选中的难度是否为 difficulty。

        narrow: PC 布局右上方标题区域 (.68,.125,.96,.181), 只有选中难度会出现在这里。
        wide:   手游布局兜底, 扫整个右栏; 若同时读到"简单/困难"页签, 取最靠上的
                (标题区)那个作为当前选中难度。
        """
        if not wide:
            return bool(self.ocr(.68, .125, .96, .181, match=re.compile(difficulty + r"$")))
        boxes = self.ocr(*ANDROID_DIFFICULTY_BOX, match=re.compile(r"困难|简单"))
        if not boxes:
            return False
        top = min(boxes, key=lambda box: box.y)
        return bool(top and re.fullmatch(difficulty, top.name.strip()))

    def _widest_selected_difficulty(self):
        """宽域识别当前选中的难度(手游端), 返回 '简单'/'困难' 或 None。"""
        for name in ("困难", "简单"):
            if self._selected_difficulty(name, wide=True):
                return name
        return None

    def _tutorial_confirm(self):
        """开局玩法说明弹窗(如"无尽模式"介绍, 居中"确认"按钮): 点掉并返回是否处理过。"""
        if not (self.ocr(.0, .2, .5, .6, match=ENDLESS_RE)
                or self.ocr(.0, .2, .5, .6, match=ENDLESS_POPUP_RE)):
            return False
        confirm = self.ocr(.38, .85, .62, .97, match=re.compile(r"^确认$|^確認$"))
        if not confirm:
            return False
        self.log_info("关闭玩法说明弹窗(无尽模式)。")
        self.click(confirm[0], after_sleep=.6)
        return True

    def _scroll_stages(self, interaction, direction, stages):
        if not self._clickable(interaction):
            raise RuntimeError("请将鸣潮窗口保持在前台。")
        left = round(self.width * .34)
        right = round(self.width * .81)
        y = round(self.height * .49)
        start, end = (right, left) if direction > 0 else (left, right)
        interaction.swipe(start, y, end, y, 650)
        self.sleep(.55)
        stages_after = self.wait_until(self._stage_list, time_out=5)
        if not stages_after:
            raise RuntimeError("滑动后无法识别拉海洛方块关卡列表。")
        moved = len(stages_after) != len(stages) or any(
            abs(before.x - after.x) > .005 * self.width
            for (_, before), (_, after) in zip(stages, stages_after)
        )
        return stages_after, moved

    def _first_page(self, interaction, stages):
        for _ in range(12):
            stages, moved = self._scroll_stages(interaction, -1, stages)
            if not moved:
                return stages
        raise RuntimeError("无法定位到拉海洛方块关卡列表起点。")

    def _go_now_button(self):
        # 通关后游戏可能退回活动主页, 只有「立即前往」能回到关卡列表。
        return self.ocr(.25, .45, 1.0, .98, match="立即前往")

    def _return_to_list(self):
        if self._stage_details():
            self.click(.942, .06, after_sleep=.45)
        go_now = self.wait_until(self._go_now_button, time_out=3)
        if go_now:
            self.log_info("退回了活动主页，点击「立即前往」返回关卡列表。")
            self.click(go_now[0], after_sleep=.8)
        stages = self.wait_until(self._stage_list, time_out=5)
        if not stages and self.is_adb():
            # 手游端 X 按钮坐标可能不准: 用返回键(esc 已映射为安卓返回)兜底关掉详情页
            self.log_info("手游端返回关卡列表失败，尝试安卓返回键。")
            self.send_key('esc', after_sleep=.8)
            go_now = self.wait_until(self._go_now_button, time_out=2)
            if go_now:
                self.click(go_now[0], after_sleep=.8)
            stages = self.wait_until(self._stage_list, time_out=5)
        if not stages:
            raise RuntimeError("挑战结束后无法返回关卡列表。")
        return stages

    def _leave_button(self):
        if self.ocr(.33, .45, .67, .52, match=re.compile(r"退出挑战|关卡进度")):
            return self.ocr(.60, .59, .71, .67, match="离开")
        return []

    def _leave_challenge(self):
        if self._stage_details():
            return
        leave = self._leave_button()
        if not leave and self._event_title() and (self._read_board() or self._score()):
            self.click(.942, .06, after_sleep=.45)
            leave = self.wait_until(self._leave_button, time_out=5)
        if not leave:
            raise RuntimeError("无法确认退出挑战界面。")
        self.click(leave[0], after_sleep=.45)
        if not self.wait_until(self._stage_details, time_out=5):
            raise RuntimeError("退出挑战后无法返回关卡详情。")

    def _challenge(self, interaction, title, status, completed):
        self.click(status, after_sleep=.45)
        if not self.wait_until(self._stage_details, time_out=5):
            raise RuntimeError(f"无法打开关卡「{title.name}」。")

        difficulty = ("简单", "困难")[completed]

        if not self._selected_difficulty(difficulty):
            self.click(.085, (.189, .276)[completed], after_sleep=.35)
            if not self.wait_until(lambda: self._selected_difficulty(difficulty), time_out=4):
                # 手游端难度页签坐标可能不同: 无法按 PC 区域确认目标难度时,
                # 宽域 OCR 识别当前选中难度; 只要页面上还有难度字样就继续
                # (实际以详情页当前选中的难度开打)。
                selected = self._widest_selected_difficulty()
                if selected:
                    self.log_warning(f"未能确认{difficulty}难度已选中，"
                                     f"按当前选中难度({selected or '未知'})继续。")
                else:
                    raise ChallengeFailed(f"无法选择{difficulty}难度。")
        self._start_and_play(interaction, difficulty, f"{title.name} · {difficulty}")
        self.log_info(f"已通关：{title.name} · {difficulty}")

    def _start_and_play(self, interaction, difficulty, label, check_objective=True):
        """在关卡详情页上开始当前选中难度并下完这一局(原 _challenge 尾部公共流程)。

        v1.5.19: check_objective=False 供难度识别全失败时的兜底直启(无尽详情页
        OCR 读不到特征文字, 也没有积分/奖章目标可查); 点开始后若实际进入的是
        无尽模式(弹窗/局内特征), 自动转无尽对局流程。
        """
        if check_objective and not self.ocr(.68, .48, .88, .55, match=re.compile(r"积分|奖章")):
            raise ChallengeFailed("无法识别关卡目标。")
        start = self._challenge_button(wide=(difficulty == "未知"))
        if not start:
            raise ChallengeFailed("无法识别开始挑战按钮。")

        self.log_info(f"开始挑战：{label}")
        for _ in range(2):
            self.click(start, down_time=.09, after_sleep=1.3)
            self.next_frame()
            start = self._challenge_button(wide=(difficulty == "未知"))
            if not start:
                break
        else:
            raise ChallengeFailed("开始挑战按钮未响应。")
        try:
            self.next_frame()
            if self._endless_page() or self._endless_ingame():
                # 兜底直启进入了无尽模式 -> 转无尽对局流程(含弹窗/结算处理)
                self.log_info("进入的是无尽模式，转无尽对局流程。")
                self._play_endless_round(interaction)
                return
            if not self.wait_until(self._ready_board, time_out=15):
                raise ChallengeFailed("无法识别棋盘。")
            self._play_board(interaction)
        except ChallengeFailed:
            self._leave_challenge()
            raise
        self.click(.5, .88, after_sleep=.6)
        if not self.wait_until(self._stage_details, time_out=3):
            # 通关结算后游戏可能直接退回活动主页而不是关卡详情。
            go_now = self.wait_until(self._go_now_button, time_out=4)
            if go_now:
                self.log_info("通关后退回了活动主页，点击「立即前往」返回关卡列表。")
                self.click(go_now[0], after_sleep=.8)
            elif not self.wait_until(self._stage_list, time_out=3):
                raise RuntimeError("领取奖励后无法识别关卡详情。")

    def _challenge_current_details(self, interaction):
        """已在关卡详情页启动任务: 直接开始当前选中的难度, 无需回列表选关。

        v1.5.16: 玩家手动打开某个关卡页面后直接跑任务, 不再要求必须停在列表页。
        难度以详情页当前选中的为准(OCR 识别"简单/困难"), 避免误切难度。
        v1.5.17: 手游端布局差异导致 PC 区域读不到难度时, 用宽域 OCR 兜底。
        v1.5.18: 无尽模式没有难度选项, 直接开始无尽挑战(详见 _challenge_endless)。
        """
        difficulty = None
        for name in ("困难", "简单"):
            if self._selected_difficulty(name):
                difficulty = name
                break
        if difficulty is None:
            # 手游端布局差异: PC 标题区域读不到时用宽域 OCR 兜底
            difficulty = self._widest_selected_difficulty()
        if difficulty is None:
            if self._endless_page():
                self._challenge_endless(interaction)
                return
            # v1.5.19: 无尽详情页可能 OCR 读不到任何特征文字(实测 18:28 直启
            # 失败后误点 X 退出页面)。此时只要页面上有开始按钮就直接开始:
            # 无尽没有难度选项; 普通关卡按当前选中难度开打(与宽域兜底"按当前
            # 选中难度继续"策略一致), 进入后再按实际界面分流(见 _start_and_play)。
            if self._challenge_button(wide=True):
                self.log_warning("未能识别难度页签，按页面当前选中难度直接开始。")
                self._start_and_play(interaction, "未知",
                                     "关卡页面直接开始 · 当前选中难度",
                                     check_objective=False)
                return
            raise ChallengeFailed("无法识别关卡页面当前选中的难度。")
        self._start_and_play(interaction, difficulty, f"关卡页面直接开始 · {difficulty}")

    def _endless_goal(self):
        """无尽模式目标分数(局内文案"达到9999分结算可得首通奖励")。"""
        for goal_box in self.ocr(.0, .10, .35, .25):
            m = ENDLESS_GOAL_RE.search(goal_box.name)
            if m:
                return int(m.group(1) or m.group(2))
        return None

    def _endless_score(self):
        """无尽模式当前分数(左上计分条上的独立数字)。"""
        for score_box in self.ocr(.03, .04, .28, .13):
            m = re.fullmatch(r"\d+", score_box.name.strip())
            if m:
                return int(m.group(0))
        return None

    def _click_start(self, wide=True):
        """点击开始按钮直到按钮消失(进入下一界面)。返回是否成功。"""
        start = self._challenge_button(wide=wide)
        if not start:
            return False
        for _ in range(2):
            self.click(start, down_time=.09, after_sleep=1.3)
            self.next_frame()
            start = self._challenge_button(wide=wide)
            if not start:
                return True
        return False

    def _play_endless_round(self, interaction):
        """无尽对局: 处理玩法弹窗后打完本局; 达标退出结算/无落点自动结算。"""
        if not self.wait_until(self._ready_board, time_out=15):
            raise ChallengeFailed("无法识别无尽模式棋盘。")
        reason = self._play_board(interaction, endless=True, max_moves=600)
        self.log_info(f"无尽模式本局结束（{reason}）。")
        if reason in ('goal', 'cap'):
            self._endless_exit_and_settle()
        elif self.wait_until(self._reward, time_out=3):
            # 失败/无落点后游戏自动结算: 点掉奖励弹窗
            self.click(.5, .88, after_sleep=.8)

    def _challenge_endless(self, interaction):
        """无尽模式: 从无尽页面开始, 或加入已在进行中的对局。

        无尽模式没有简单/困难难度: 点击开始(首局先点掉玩法说明弹窗)后一直
        落块消行, 达到目标分数(如 9999 分)主动退出结算; 无合法落点则等游戏
        自动结算。结束后由调用方负责返回关卡列表。
        """
        if self._tutorial_confirm():
            self.sleep(.5)
            self.next_frame()
        if self._playable_board():
            self.log_info("检测到无尽模式对局，直接加入继续游玩。")
        else:
            if not self._click_start():
                raise ChallengeFailed("无法识别无尽模式的开始按钮。")
            self.log_info("开始挑战：无尽模式")
        self._play_endless_round(interaction)

    def _endless_exit_and_settle(self):
        """达到分数目标后主动退出无尽模式并结算领取奖励。"""
        self.click(.942, .06, after_sleep=.8)

        def leave_or_confirm():
            leave = self.ocr(.55, .55, .78, .72, match=re.compile(r"^离开$|^離開$"))
            if leave:
                return leave[0]
            confirm = self.ocr(.38, .78, .62, .98,
                               match=re.compile(r"^确认$|^確認$|^确定$|^確定$"))
            return confirm[0] if confirm else None

        button = self.wait_until(leave_or_confirm, time_out=4)
        if button:
            self.click(button, after_sleep=1.0)
        if self.wait_until(self._reward, time_out=6):
            self.click(.5, .88, after_sleep=.8)

    def run(self):
        # 云游戏出错时原地重跑整个关卡扫描流程。这里不刷新页面:
        # 刷新会把玩家打开的活动关卡 UI 退回云游戏首页, 反而无法继续。
        # 本地客户端保持原行为(错误直接抛出)。
        run_with_cloud_recovery(
            self, self._run_task, name=self.name,
            refresh_page=False, wait_ready=False)

    def _run_task(self):
        self.next_frame()
        if canonical_frame(self.frame) is None:
            raise FatalTaskError("拉海洛方块需要 16:9 的游戏画面（PC 客户端或 1920x1080 云鸣潮）。")
        # 云游戏(浏览器)没有 PC 客户端的 HwndWindow, 只在 PC 模式下检查窗口句柄。
        if not self.is_browser() and (not self.hwnd or not self.hwnd.exists):
            raise FatalTaskError("拉海洛方块需要处于前台的 Windows PC 客户端。")
        stages = self.wait_until(self._stage_list, time_out=5)
        interaction = self._make_interaction()
        if not self._clickable(interaction):
            self.hwnd.bring_to_front()
            if not self.wait_until(lambda: self._clickable(interaction), time_out=3):
                raise FatalTaskError("请将鸣潮窗口切到前台后再次启动任务。")

        if not stages:
            # v1.5.16: 支持直接在关卡详情页启动 —— 先把当前选中的难度打完,
            # 然后回列表继续扫描其余关卡; 失败只警告, 不中断后续扫描。
            if self.wait_until(self._stage_details, time_out=3):
                self.log_info("当前已在关卡页面，直接开始当前选中的难度（无尽模式则直接开始无尽挑战）。")
                try:
                    self._challenge_current_details(interaction)
                except ChallengeFailed as exc:
                    self.log_warning(f"关卡页面直接开始失败：{exc}")
                stages = self._return_to_list()
            elif self._endless_ingame():
                # v1.5.18: 已在无尽模式对局内(玩法弹窗或棋盘可见) -> 直接加入
                self.log_info("检测到无尽模式对局，直接加入继续游玩。")
                try:
                    self._challenge_endless(interaction)
                except ChallengeFailed as exc:
                    self.log_warning(f"无尽模式挑战失败：{exc}")
                stages = self._return_to_list()
            else:
                raise FatalTaskError(
                    "请先打开简体中文的「拉海洛方块·逆转」活动关卡列表、任一关卡详情页"
                    "或无尽模式页面（MuMu/安卓端同样支持）。")

        stages = self._first_page(interaction, stages)
        attempted = set()
        failures = []
        cleared = 0
        for _ in range(32):
            for title, status in stages:
                progress = STAGE_PROGRESS.search(status.name)
                if not progress:
                    continue
                completed, total = map(int, progress.groups())
                attempt = (title.name, completed)
                if total != 2 or completed >= total or attempt in attempted:
                    continue
                attempted.add(attempt)
                try:
                    self._challenge(interaction, title, status, completed)
                    cleared += 1
                except ChallengeFailed as exc:
                    failures.append(title.name)
                    self.log_warning(f"{title.name}：{exc}")
                stages = self._return_to_list()
                break
            else:
                stages, moved = self._scroll_stages(interaction, 1, stages)
                if not moved:
                    self._first_page(interaction, stages)
                    if failures:
                        raise RuntimeError(f"已通关 {cleared} 个难度，未完成：{'、'.join(failures)}")
                    self.log_info(f"已通关 {cleared} 个难度，所有已解锁关卡已检查。", notify=True)
                    return
        raise RuntimeError("扫描关卡列表达到上限。")

    def _read_board(self):
        return read_board(canonical_frame(self.frame))

    def _playable_board(self):
        board = self._read_board()
        return board if board and board.pieces else None

    def _score(self):
        texts = self.ocr(x=.09, y=.125, to_x=.235, to_y=.181)
        for box in texts:
            if match := re.search(r"(\d+)\s*[/／]\s*(\d+)", box.name):
                score, goal = map(int, match.groups())
                if goal > 0:
                    return score, goal
        return None

    def _reward(self):
        return self.ocr(.36, .216, .64, .29, match=re.compile(r"^获\s*得$"))

    def _help_popup(self):
        # The first score challenge includes a manual and three guided clicks.
        # 数据损坏/故障/爆炸方块 are the 3.8 逆转 tutorial pager pages.
        return self.ocr(.05, .28, .32, .35,
                        match=re.compile(r"积分模式|奖章模式|数据损坏方块|故障方块|爆炸方块"))

    def _close_help_popup(self):
        """关闭玩法说明弹窗: 先点右上角 X, 无效再用「确认」/跳转最后一页兜底。返回是否处理过弹窗。"""
        if not self._help_popup():
            return False
        self.click(.960, .210, after_sleep=.6)
        if not self._help_popup():
            return True
        confirm = self.ocr(.41, .88, .59, .95, match="确认")
        if confirm:
            self.click(confirm[0], after_sleep=.6)
        elif self.ocr(.38, .90, .62, .96, match=re.compile(r"切换至最后一页")):
            self.click(.75, .805, after_sleep=.5)
        return True

    def _ready_board(self):
        if self._tutorial_confirm():
            return False
        if self._close_help_popup():
            return False

        for region, hint, target in (
            ((.54, .39, .81, .47), "选择右侧方块", (.863, .444)),
            ((.28, .28, .72, .37), "方块旋转后填入空格", (.50, .48)),
            ((.035, .23, .37, .30), "方块消除后将获得积分", (.16, .16)),
        ):
            if self.ocr(*region, match=re.compile(hint)):
                self.click(*target, after_sleep=.5)
                return False

        return self._playable_board()

    def _place(self, interaction, board, move):
        piece = next(p for p in board.pieces if p.slot == move.slot)
        height, width = self.frame.shape[:2]

        def point(xy):
            return round(xy[0] * width / WIDTH), round(xy[1] * height / HEIGHT)

        def move_cursor(xy):
            if not self._clickable(interaction):
                raise RuntimeError("Game lost foreground focus during a drag")
            interaction.move(*point(xy))

        source = piece.pickup
        dx, dy = move.drop
        move_cursor(source)
        self.sleep(.12)
        interaction.mouse_down(*point(source))
        release_at_target = False
        try:
            # Trigger the drag in the tray, but rotate over the board where
            # the game reliably accepts R even for pieces near the tray edge.
            self.sleep(.10)
            move_cursor((source[0] - 16, source[1]))
            self.sleep(.12)
            for i in range(1, 9):
                move_cursor((source[0] + (dx - source[0]) * i / 8, source[1] + (dy - source[1]) * i / 8))
                self.sleep(.025)
            self.sleep(.15)

            def rotate():
                if not self._clickable(interaction):
                    raise RuntimeError("Game lost foreground focus during a drag")
                interaction.send_key('r', down_time=.08)
                move_cursor((dx + 5, dy))
                self.sleep(.13)

            for _ in range(move.turns):
                rotate()
            # Retry a full rotation cycle if a key press was missed.
            for attempt in range(4):
                if attempt:
                    rotate()
                for ox, oy in ((0, 0), (0, -12), (-12, 0), (12, 0), (0, 12)):
                    move_cursor((dx + ox, dy + oy))
                    self.sleep(.16)
                    if self._clickable(interaction) and preview_matches(canonical_frame(self.next_frame()), board, move):
                        release_at_target = True
                        return True
            if not release_at_target:
                self.log_warning(f"Placement preview did not match: slot={move.slot}, turns={move.turns}, "
                                 f"row={move.row}, col={move.col}")
            return release_at_target
        finally:
            if self.is_browser():
                # CDP mouse events are virtual: always release, focus is irrelevant.
                if not release_at_target:
                    interaction.move(*point(source))
                interaction.mouse_up()
            elif interaction.clickable():
                if not release_at_target:
                    # No task sleep here: cancellation must still release the button.
                    interaction.move(*point(source))
                interaction.mouse_up()
            else:
                # PynputInteraction.mouse_up deliberately skips when not focused.
                # Release our already-held button even if the focus changed.
                from pynput import mouse
                mouse.Controller().release(mouse.Button.left)

    def _play_board(self, interaction, endless=False, max_moves=160):
        """下完一局棋盘。返回结束原因: 'reward'(结算奖励) / 'dead'(无合法落点) /
        'goal'(无尽模式达到目标分数) / 'cap'(落块次数上限); 普通模式结束原因
        依旧为 None(仅结算奖励时返回), 异常照常抛出。"""
        misses = 0
        rejected = set()
        goal = self._endless_goal() if endless else None
        if endless and goal:
            self.log_info(f"无尽模式目标分数：{goal}，达到后自动退出结算。")
        for move_no in range(max_moves):
            self.next_frame()
            board = self._playable_board() or self.wait_until(self._playable_board, time_out=2)
            if not board:
                if self.wait_until(self._reward, time_out=3):
                    return 'reward'
                # 挑战中游戏可能弹出玩法说明(如无尽模式介绍/故障方块介绍),
                # 点掉"确认"/关闭后棋盘恢复。
                if self.wait_until(self._tutorial_confirm, time_out=2):
                    self.sleep(.5)
                    continue
                if self.wait_until(self._close_help_popup, time_out=2):
                    self.sleep(.5)
                    continue
                if endless:
                    # 无尽模式棋盘消失视为进入结算/退出界面
                    return 'ended'
                raise ChallengeFailed("棋盘消失，未确认通关。")
            if not self._clickable(interaction):
                raise RuntimeError("Game lost foreground focus; no further moves were sent.")
            move = choose_move(board, excluded=rejected)
            if move is None:
                if endless:
                    self.log_info("无尽模式无合法落点，本局结束。")
                    return 'dead'
                raise ChallengeFailed("剩余方块无合法落点。")
            if not self._place(interaction, board, move):
                misses += 1
                rejected.add((move.slot, move.mask))
                if misses >= 3:
                    raise ChallengeFailed("连续三次未能匹配落点预览。")
                self.sleep(.35)
                continue
            misses = 0
            rejected.clear()
            if endless and goal and move_no % 10 == 9:
                score = self._endless_score()
                if score is not None and score >= goal:
                    self.log_info(f"无尽模式已达到分数要求 {score}/{goal}，退出结算。")
                    return 'goal'
            expected, lines = clear_lines(board.mask | move.mask, board.fixed, board.fault)
            self.log_info(f"Rahai Blocks: slot={move.slot + 1}, rotation={move.turns * 90}, "
                          f"cell=({move.row + 1},{move.col + 1}), lines={lines}, "
                          f"fault={board.fault.bit_count()}")
            self.sleep(.95 if lines else .38)
            for _ in range(4):
                self.next_frame()
                actual = self._read_board()
                if actual and actual.mask == expected and actual.fixed == board.fixed:
                    break
                self.sleep(.23)
            else:
                if lines and self.wait_until(self._reward, time_out=3):
                    return
                if not actual:
                    raise ChallengeFailed("落块后棋盘无法识别。")
                # 故障解除后方块残留、爆炸方块引爆都会让实际棋盘偏离预测;
                # 以重新读到的棋盘为准继续, 不中断挑战。
                self.log_warning(f"Rahai Blocks: expected={expected:#018x}, "
                                 f"actual={actual.mask:#018x}; continuing from the observed board")
        if endless:
            return 'cap'
        raise ChallengeFailed("达到落块次数上限，未确认通关。")
