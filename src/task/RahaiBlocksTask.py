import re

from ok import BaseTask
from ok.device.interaction_methods.browser import BrowserInteraction
from ok.device.interaction_methods.pynput import PynputInteraction

from src.task.rahai_blocks import (
    HEIGHT, WIDTH, canonical_frame, choose_move, clear_lines,
    preview_center, preview_matches, read_board,
)
from src.task.task_icons import task_icon


STAGE_PROGRESS = re.compile(r"进行中.*?(\d+)\s*[/／]\s*(\d+)")
STAGE_STATUS = re.compile(r"进行中|已(?:通关|完成)|(?:\d+\s*(?:天|小时|分钟))")

# 无尽模式：没有简单/困难难度页签，只有目标分数与一直进行的对局。
# 详情页读不到难度页签，也不该因为"无法识别难度"就退出页面。
ENDLESS_RE = re.compile(r"无尽模式|無盡模式")
ENDLESS_POPUP_RE = re.compile(r"玩家可以一直游玩|直到失败")
ENDLESS_INGAME_RE = re.compile(r"历史最高|歷史最高|达到\d+分结算|達到\d+分結算")
ENDLESS_GOAL_RE = re.compile(r"达到(\d+)分结算|達到(\d+)分結算")


class ChallengeFailed(RuntimeError):
    pass


class RahaiBlocksTask(BaseTask):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "3.8 拉海洛方块·逆转"
        self.description = (
            "从活动关卡列表、任一关卡详情页或无尽模式页面开始，挑战所有已解锁且未通关的关卡。"
            "支持无尽模式：从无尽页面直接开始或加入进行中的对局，达到目标分数后自动退出结算。"
            "支持简体中文 PC 客户端、云鸣潮与 MuMu/安卓模拟器。"
        )
        self.group_name = "Daily Activities"
        self.group_icon = task_icon("category-daily")
        self.supported_languages = ["zh_CN"]
        self._multi_touch = None
        # MuMu 方块旋转：手游不认 input keyevent，交给 MuMu 键位映射的真实键盘。
        # 默认 f1（不与游戏热键 q/r/e/t/space/lshift/tab/f2/b 冲突）。
        self.default_config.update({
            'Rotate Key (MuMu Keymap)': 'f1',
        })
        self.config_description['Rotate Key (MuMu Keymap)'] = (
            'MuMu/安卓模拟器拉海洛方块旋转键。需在 MuMu 键位映射里把此键绑到游戏内'
            '「旋转」按钮，并选一个不与现有键位冲突的键（默认 f1）。留空则回退为点屏幕旋转按钮。'
        )

    def on_destroy(self):
        # 双指触控: 任务被中断/停止时释放仍按下的触点, 避免"手指卡住"影响下次操作。
        if self._multi_touch is not None:
            try:
                self._multi_touch.close()
            except Exception as error:
                self.log_warning(f"释放 MuMu 双指触控失败: {error}")
            self._multi_touch = None
        super().on_destroy()

    # --- 输入层：云鸣潮用浏览器虚拟输入，PC 客户端用真实鼠标 -------------------

    def _make_interaction(self):
        """按设备选输入通道。

        - 云鸣潮: BrowserInteraction(CDP 虚拟输入), 不依赖窗口焦点
        - MuMu/安卓模拟器: 手游版旋转靠屏幕左侧的「旋转」按钮, 需要真正的双指
          （一指按住方块拖动 + 另一指点旋转按钮）。MuMu IPC/u2 都是单指 API,
          所以用 ADB sendevent 多点触控: MuMuMultiTouchInteraction。
        - PC 客户端: PynputInteraction(真实键盘 R 旋转 + 鼠标拖拽)
        """
        capture = self.executor.device_manager.capture_method
        if self.is_browser():
            return BrowserInteraction(capture)
        if self.is_adb():
            from src.task.multi_touch import (
                NemuIpcTouchDevice, AdbMotionEventDevice,
                MuMuMultiTouchInteraction, send_real_key,
            )
            # MuMu IPC 触控的坐标与截图 framebuffer 一致（横屏画面像素），
            # 这正是 interaction 传进来的坐标系 —— 落点和使用者看到的画面 1:1 对应。
            # v1.8.14 的 AdbMotionEventDevice 走 input motionevent，那是 Android
            # wm size 竖屏逻辑坐标（如 900x1600），与横屏截图不同一套，x/y 双向偏移。
            # MuMu IPC 未建立连接时（非 IPC 抓屏/低版本），回退到 ADB 方案。
            capture_method = self.executor.device_manager.capture_method
            nemu = getattr(capture_method, 'nemu_impl', None)
            if nemu is not None:
                self._multi_touch = NemuIpcTouchDevice(capture_method)
            else:
                adb_device = self.executor.device_manager.device
                if adb_device is None:
                    raise RuntimeError("MuMu 触控输入需要已连接的 adb 设备或 IPC 抓屏。")
                self._multi_touch = AdbMotionEventDevice(adb_device)
            rotate_key = (self.config.get('Rotate Key (MuMu Keymap)') or '').strip()
            hwnd_window = self.executor.device_manager.hwnd_window
            return MuMuMultiTouchInteraction(
                self._multi_touch, rotate_key=rotate_key,
                key_sender=(lambda k, dt: send_real_key(k, hwnd_window, dt)) if rotate_key else None,
            )
        return PynputInteraction(capture, self.hwnd)

    def _clickable(self, interaction):
        # Browser 走 CDP 输入、MuMu 走 sendevent 直写触控设备，都不需要窗口前台。
        # 只有 PC 客户端的 Pynput 要求窗口有系统焦点。
        return True if (self.is_browser() or self.is_adb()) else interaction.clickable()

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
            # 无尽模式页面没有难度页签，开始按钮位置也不固定，宽域兜底。
            boxes = self.ocr(.60, .84, 1.0, 1.0, match=re.compile(r"^开始(?:挑战)?$"))
            if boxes:
                return boxes[0]
        return None

    def _stage_details(self):
        return self._event_title() and self.ocr(.68, .43, .82, .48, match="关卡目标")

    # --- 无尽模式识别 ----------------------------------------------------------

    def _endless_page(self):
        """当前是否处于无尽模式（详情页 / 玩法说明弹窗 / 对局内）。"""
        return (self._event_title()
                and (self.ocr(.0, .10, .7, .75, match=ENDLESS_RE)
                     or self.ocr(.0, .10, .7, .75, match=ENDLESS_POPUP_RE)
                     or self.ocr(.0, .10, .35, .25, match=ENDLESS_INGAME_RE)))

    def _endless_ingame(self):
        """已在无尽模式对局内（玩法弹窗未关 / 局内计分 UI 可见）。

        不能用「棋盘可见」兜底: 普通关卡进对局后同样有活动标题 + 棋盘,
        那样任何普通关卡都会被当成无尽模式, 失败时被记成"已通关"。
        """
        if not self._event_title():
            return False
        return bool(self.ocr(.0, .10, .7, .75, match=ENDLESS_POPUP_RE)
                    or self.ocr(.0, .10, .35, .25, match=ENDLESS_INGAME_RE))

    def _endless_goal(self):
        """无尽模式目标分数（局内文案「达到9999分结算可得首通奖励」）。"""
        for goal_box in self.ocr(.0, .10, .35, .25):
            match = ENDLESS_GOAL_RE.search(goal_box.name)
            if match:
                return int(match.group(1) or match.group(2))
        return None

    def _endless_score(self):
        """无尽模式当前分数（左上计分条上的独立数字）。"""
        for score_box in self.ocr(.03, .04, .28, .13):
            if re.fullmatch(r"\d+", score_box.name.strip()):
                return int(score_box.name.strip())
        return None

    def _tutorial_confirm(self):
        """开局玩法说明弹窗（如「无尽模式」介绍，居中「确认」按钮）。"""
        if not (self.ocr(.0, .2, .5, .6, match=ENDLESS_RE)
                or self.ocr(.0, .2, .5, .6, match=ENDLESS_POPUP_RE)):
            return False
        confirm = self.ocr(.38, .85, .62, .97, match=re.compile(r"^确认$|^確認$"))
        if not confirm:
            return False
        self.log_info("关闭玩法说明弹窗（无尽模式）。")
        self.click(confirm[0], after_sleep=.6)
        return True

    # --- 关卡列表导航 ----------------------------------------------------------

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
        # 通关后游戏可能退回活动主页，只有「立即前往」能回到关卡列表。
        return self.ocr(.25, .45, 1.0, .98, match="立即前往")

    def _return_to_list(self):
        """回到关卡列表; 详情页/无尽页/结算页可能要多点几次返回。"""
        for attempt in range(3):
            if self._stage_details() or self._endless_page() or attempt:
                self.click(.942, .06, after_sleep=.45)
            go_now = self.wait_until(self._go_now_button, time_out=3)
            if go_now:
                self.log_info("退回了活动主页，点击「立即前往」返回关卡列表。")
                self.click(go_now[0], after_sleep=.8)
            stages = self.wait_until(self._stage_list, time_out=5)
            if stages:
                return stages
            if self.is_adb():
                # 手游端右上角 X 的坐标与 PC 不同, 可能关不掉详情页;
                # 用返回键(模拟器键位映射里 esc -> 返回/菜单)兜底。
                self.log_info("手游端返回关卡列表失败，尝试安卓返回键。")
                self.send_key('esc', after_sleep=.8)
                go_now = self.wait_until(self._go_now_button, time_out=2)
                if go_now:
                    self.click(go_now[0], after_sleep=.8)
                stages = self.wait_until(self._stage_list, time_out=5)
                if stages:
                    return stages
        raise RuntimeError("挑战结束后无法返回关卡列表。")

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

    # --- 开始挑战 --------------------------------------------------------------

    def _challenge(self, interaction, title, status, completed):
        self.click(status, after_sleep=.45)
        if not self.wait_until(self._stage_details, time_out=5):
            raise RuntimeError(f"无法打开关卡「{title.name}」。")

        difficulty = ("简单", "困难")[completed]

        def selected():
            return self.ocr(.68, .125, .96, .181, match=re.compile(difficulty + r"$"))

        if not selected():
            self.click(.085, (.189, .276)[completed], after_sleep=.35)
            if not self.wait_until(selected, time_out=4):
                raise ChallengeFailed(f"无法选择{difficulty}难度。")
        self._start_and_play(interaction, f"{title.name} · {difficulty}")
        self.log_info(f"已通关：{title.name} · {difficulty}")

    def _start_and_play(self, interaction, label, check_objective=True):
        """在关卡详情页上开始当前页面并打完这一局。

        check_objective=False 用于无尽模式详情页：那里没有「积分/奖章」目标，
        也没有难度页签，硬查目标只会误报失败并退回列表。
        """
        if check_objective and not self.ocr(.68, .48, .88, .55, match=re.compile(r"积分|奖章")):
            raise ChallengeFailed("无法识别关卡目标。")
        start = self._challenge_button(wide=not check_objective)
        if not start:
            raise ChallengeFailed("无法识别开始挑战按钮。")

        self.log_info(f"开始挑战：{label}")
        for _ in range(2):
            self.click(start, down_time=.09, after_sleep=1.3)
            self.next_frame()
            start = self._challenge_button(wide=not check_objective)
            if not start:
                break
        else:
            raise ChallengeFailed("开始挑战按钮未响应。")
        try:
            self.next_frame()
            if self._endless_page() or self._endless_ingame():
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
        """已在关卡详情页启动任务：直接开始当前页面，不再要求先停在列表页。

        无尽模式详情页没有难度页签，直接走无尽流程；普通关卡按详情页当前选中的
        难度开打（不切换难度，避免误改玩家选择）。
        """
        for difficulty in ("困难", "简单"):
            if self.ocr(.68, .125, .96, .181, match=re.compile(difficulty + r"$")):
                self._start_and_play(interaction, f"关卡页面直接开始 · {difficulty}")
                return
        if self._endless_page():
            self._challenge_endless(interaction)
            return
        # 无尽详情页可能连特征文字都读不到（实测），只要页面上有开始按钮就直接开始，
        # 进入后再按实际界面分流（_start_and_play 会识别无尽模式）。
        if self._challenge_button(wide=True):
            self.log_warning("未能识别难度页签，按页面当前内容直接开始。")
            self._start_and_play(interaction, "关卡页面直接开始 · 当前选中难度", check_objective=False)
            return
        raise ChallengeFailed("无法识别关卡页面当前选中的难度。")

    def _click_start(self, wide=True):
        """点击开始按钮直到它消失（说明已进入下一界面）。"""
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

    def _challenge_endless(self, interaction):
        """无尽模式：从无尽页面开始，或加入已在进行中的对局。"""
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

    def _play_endless_round(self, interaction):
        """打完一局无尽模式；达标主动退出结算，无合法落点则等游戏自动结算。"""
        if not self.wait_until(self._ready_board, time_out=15):
            raise ChallengeFailed("无法识别无尽模式棋盘。")
        reason = self._play_board(interaction, endless=True, max_moves=600)
        self.log_info(f"无尽模式本局结束（{reason}）。")
        if reason in ("goal", "cap"):
            self._endless_exit_and_settle()
        elif self.wait_until(self._reward, time_out=3):
            self.click(.5, .88, after_sleep=.8)

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

    # --- 主流程 ----------------------------------------------------------------

    def run(self):
        self.next_frame()
        if canonical_frame(self.frame) is None:
            raise RuntimeError("拉海洛方块需要 16:9 的游戏画面（PC 客户端或云鸣潮 1920x1080）。")
        # 云鸣潮没有 PC 客户端的窗口句柄，只在本地客户端/模拟器上检查。
        # MuMu 等模拟器本身就是 Windows 窗口，句柄存在即可(前台要求由 _clickable 保证)。
        if not (self.is_browser() or self.is_adb()) and (not self.hwnd or not self.hwnd.exists):
            raise RuntimeError("拉海洛方块需要处于前台的 Windows PC 客户端。")

        stages = self.wait_until(self._stage_list, time_out=5)
        interaction = self._make_interaction()
        if not self._clickable(interaction):
            self.hwnd.bring_to_front()
            if not self.wait_until(lambda: self._clickable(interaction), time_out=3):
                raise RuntimeError("请将鸣潮窗口切到前台后再次启动任务。")

        if not stages:
            # 允许直接在关卡详情页 / 无尽模式页面启动：先把当前这一局打完，
            # 再回列表继续扫描其余关卡；失败只警告，不中断后续扫描。
            if self.wait_until(self._stage_details, time_out=3):
                self.log_info("当前已在关卡页面，直接开始（无尽模式则走无尽流程）。")
                try:
                    self._challenge_current_details(interaction)
                except ChallengeFailed as error:
                    self.log_warning(f"关卡页面直接开始失败：{error}")
                stages = self._return_to_list()
            elif self._endless_ingame():
                self.log_info("检测到无尽模式对局，直接加入继续游玩。")
                try:
                    self._challenge_endless(interaction)
                except ChallengeFailed as error:
                    self.log_warning(f"无尽模式挑战失败：{error}")
                stages = self._return_to_list()
            elif self._endless_page():
                # 无尽模式的详情页没有「关卡目标」也没有难度页签, 只认
                # _stage_details() 会落到下面的报错分支。
                self.log_info("当前已在无尽模式页面，直接开始。")
                try:
                    self._challenge_endless(interaction)
                except ChallengeFailed as error:
                    self.log_warning(f"无尽模式挑战失败：{error}")
                stages = self._return_to_list()
            else:
                raise RuntimeError(
                    "请先打开简体中文的「拉海洛方块·逆转」活动关卡列表、"
                    "任一关卡详情页或无尽模式页面。")

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

    def _dismiss_help(self):
        """Close a mechanic manual; it can slide in after the board is already visible."""
        help_page = self.ocr(.05, .28, .32, .35, match=re.compile(r"模式|方块"))
        if not help_page:
            return False
        # OCR sometimes drops 确 on the highlighted button.
        confirm = self.ocr(.41, .88, .59, .95, match=re.compile(r"确?认$"))
        if confirm:
            self.click(confirm[0], after_sleep=.5)
        elif self.ocr(.38, .90, .62, .96, match=re.compile(r"切换至最后一页")):
            self.click(.75, .805, after_sleep=.5)
        return True

    def _ready_board(self):
        # 无尽模式首局会先弹一个「玩家可以一直游玩」的说明弹窗，居中「确认」。
        if self._tutorial_confirm():
            return False
        # The first score challenge includes a manual and three guided clicks.
        if self._dismiss_help():
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

    def _visual_servo(self, interaction, board, move, point, target, max_steps=10):
        """用落点预览闭环把方块挪到目标格（MuMu/安卓触控坐标不可靠时）。

        不猜触控坐标系（竖屏/横屏/缩放/镜像都可能），而是用游戏自己显示的
        落点预览做反馈：读预览中心 -> 与目标格比较 -> 实测「手指像素增量 ->
        预览逻辑位移」的比例 -> 反推手指该挪多少 -> 重复到命中。

        point(xy) 把逻辑坐标换算成 interaction 的像素坐标；move 接受像素坐标。
        返回 True 表示预览命中目标（可以松手落子）。
        """
        P = 40  # 标定时手指试探移动的像素量
        fx, fy = point(target)
        # 手指标点 -> 预览逻辑位移 的 2x2 雅可比：
        #   (预览dx, 预览dy) = [[a, c], [b, d]] · (手指dx, 手指dy)
        # 实测得到，故不依赖任何坐标系假设（缩放/镜像/轴交换都能覆盖）。
        jac = None
        for _ in range(max_steps):
            interaction.move(fx, fy)
            self.sleep(.12)
            frame = canonical_frame(self.next_frame())
            if not self._clickable(interaction):
                raise RuntimeError("Game lost foreground focus during a drag")
            if preview_matches(frame, board, move):
                return True
            center = preview_center(frame, board)
            if center is None:
                # 刚离开托盘时预览还没出现，稍等再读一次。
                self.sleep(.15)
                frame = canonical_frame(self.next_frame())
                if preview_matches(frame, board, move):
                    return True
                center = preview_center(frame, board)
                if center is None:
                    return False

            if jac is None:
                # 还没标定：用两条正交探针实测雅可比（像素偏移，不经过 point）。
                interaction.move(fx + P, fy)
                self.sleep(.12)
                cx = preview_center(canonical_frame(self.next_frame()), board)
                interaction.move(fx, fy + P)
                self.sleep(.12)
                cy = preview_center(canonical_frame(self.next_frame()), board)
                if cx is not None and cy is not None:
                    jac = ((cx[0] - center[0]) / P, (cx[1] - center[1]) / P,
                           (cy[0] - center[0]) / P, (cy[1] - center[1]) / P)
                continue  # 探针把手指挪走了，下一轮 move(fx,fy) 回原位再修正

            a, b, c, d = jac
            ex = target[0] - center[0]
            ey = target[1] - center[1]
            det = a * d - b * c
            if abs(det) < 1e-6:
                # 标定退化（预览没跟手），退回单轴比例，仍读不到就放弃。
                dfx = ex / a if abs(a) > 1e-6 else 0
                dfy = ey / d if abs(d) > 1e-6 else 0
            else:
                dfx = (d * ex - c * ey) / det
                dfy = (-b * ex + a * ey) / det
            # 单步限幅，避免坐标系异常时一次挪太远丢失预览。
            step = max(abs(dfx), abs(dfy))
            if step > 300:
                dfx, dfy = dfx * 300 / step, dfy * 300 / step
            if abs(dfx) < 1 and abs(dfy) < 1:
                # 偏差小于一个像素还判不中：形状/旋转的问题，挪动无用。
                return False
            fx += round(dfx)
            fy += round(dfy)
        return False

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
            if self.is_adb():
                # MuMu/安卓触控坐标系不可靠（横竖屏/缩放/镜像都可能），
                # 用游戏落点预览做视觉闭环，实测偏差并修正手指，不再猜坐标。
                if self._visual_servo(interaction, board, move, point, (dx, dy)):
                    release_at_target = True
                    return True
                # 伺服失败可能是漏旋转（形状不对，挪位置永远不命中）：
                # 补一整圈旋转 90° 再伺服一次，覆盖键位映射偶发丢键。
                if move.turns:
                    for _ in range(4):
                        rotate()
                        if self._visual_servo(interaction, board, move, point, (dx, dy)):
                            release_at_target = True
                            return True
            else:
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
            if self._clickable(interaction):
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
        """落块直到本局结束。

        普通关卡：通关或失败抛 ChallengeFailed（由调用方退出挑战）。
        无尽模式：一直落块并返回结束原因 —— ``goal`` 达到目标分数、``cap`` 到达
        落块上限、``dead`` 无合法落点、``ended`` 棋盘消失（游戏自行结算）。
        """
        misses = 0
        rejected = set()
        mismatches = 0
        stagnant = 0  # moves without a board change
        last_mask = None
        goal = self._endless_goal() if endless else None
        if goal:
            self.log_info(f"无尽模式目标分数：{goal}")
        moves = 0
        for _ in range(max_moves):
            self.next_frame()
            board = self._playable_board() or self.wait_until(self._playable_board, time_out=2)
            if not board:
                if self.wait_until(self._reward, time_out=3):
                    return "reward"
                if self._tutorial_confirm():
                    self.sleep(.5)
                    continue
                if not self._dismiss_help():
                    if endless:
                        # 无尽模式棋盘消失视为进入结算/退出界面。
                        return "ended"
                    self.screenshot("rahai_board_lost")
                    raise ChallengeFailed("棋盘消失，未确认通关。")
                # A manual covered the board; earlier preview misses were caused by it.
                self.wait_until(lambda: not self._dismiss_help(), time_out=10)
                misses = 0
                rejected.clear()
                continue
            if not self._clickable(interaction):
                raise RuntimeError("Game lost foreground focus; no further moves were sent.")
            move = choose_move(board, excluded=rejected)
            if move is None:
                if endless:
                    self.log_info("无尽模式无合法落点，本局结束。")
                    return "dead"
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
            moves += 1
            if endless and goal and moves % 10 == 0:
                score = self._endless_score()
                if score is not None and score >= goal:
                    self.log_info(f"无尽模式已达到分数要求 {score}/{goal}，退出结算。")
                    return "goal"
            expected, lines = clear_lines(board.mask | move.mask, board.fixed)
            self.log_info(f"Rahai Blocks: slot={move.slot + 1}, rotation={move.turns * 90}, "
                          f"cell=({move.row + 1},{move.col + 1}), lines={lines}")
            self.sleep(.95 if lines else .38)
            actual = None
            matched = False
            for _ in range(4):
                self.next_frame()
                actual = self._read_board()
                if actual and actual.mask == expected and actual.fixed == board.fixed:
                    matched = True
                    break
                self.sleep(.23)

            if not matched and lines and self.wait_until(self._reward, time_out=3):
                return "reward"

            # clear_lines() keeps fixed tiles after a clear, but some stages clear
            # them too; the preview matched, so trust the observed board and continue.
            if not matched:
                mismatches += 1
                self.log_warning(
                    f"Rahai Blocks: prediction missed ({mismatches}x), continuing "
                    f"from actual board; "
                    f"expected={expected:#018x}, "
                    f"actual={hex(actual.mask) if actual else 'unrecognized'}")

            # Only a truly unchanged board means the placement failed.
            if actual is not None:
                if last_mask is not None and actual.mask == last_mask and actual.fixed == board.fixed:
                    stagnant += 1
                    if stagnant >= 4:
                        if endless:
                            self.log_warning("棋盘连续 4 次落块无变化，本局结束。")
                            return "dead"
                        raise ChallengeFailed("Board unchanged after 4 consecutive moves; "
                                              "placement appears to have no effect.")
                else:
                    stagnant = 0
                last_mask = actual.mask
        if endless:
            return "cap"
        raise ChallengeFailed("达到落块次数上限，未确认通关。")
