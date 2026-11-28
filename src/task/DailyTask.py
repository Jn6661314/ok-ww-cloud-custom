import re
import time


from ok import Logger, TaskDisabledException
from src.task.CultivationTask import CultivationTask
from src.task.FarmEchoTask import FarmEchoTask
from src.task.ForgeryTask import ForgeryTask
from src.task.GardenTask import GardenTask
from src.task.MergeEchoTask import MergeEchoTask
from src.task.NightmareNestTask import NightmareNestTask
from src.task.TacetTask import TacetTask
from src.task.SimulationTask import SimulationTask
from src.task.WWOneTimeTask import WWOneTimeTask
from src.task.BaseCombatTask import BaseCombatTask
from src.task.EchoBoxMixin import EchoBoxMixin
from src.task.task_icons import task_icon

logger = Logger.get_logger(__name__)

CHECK_WEEKLY_GARDEN = 'Check Weekly Garden'
AUTO_FARM_NIGHTMARE_NEST = 'Auto Farm all Nightmare Nest'
MERGE_ECHO_IF_DISCARDED_OVER_1000 = 'Merge Echo If discarded > 1000'
TELEPORT_AND_FARM_4C_ECHO = 'Teleport and Farm 4C Echo'
ADDITIONAL_TASKS = 'Additional Tasks to Run After Daily Task'
USE_ECHO_BOX_FOR_DAILY = 'Use Echo Box for Daily Echo'

# 手游端(MuMu/安卓)活跃行迹页: 布局与 PC 不同, PC 专属坐标/OCR 区域全部落空
# (实测安卓端连续 "total daily points 未识别" -> 保守跳过体力),
# 改为宽域 OCR: 先定位"活跃行迹"子页签, 再全页搜 x/180 与 x/100 形式的读数。
ANDROID_ACTIVITY_TRACE_RE = re.compile(r'活跃行迹|活躍行跡|每日活跃|每日活躍')
ANDROID_DAILY_PROGRESS_RE = re.compile(r'(\d{1,3})\s*[/／]\s*180')
ANDROID_DAILY_POINTS_RE = re.compile(r'(\d{1,3})\s*[/／]\s*(100|200)')
ANDROID_ACTIVITY_PAGE_RE = re.compile(r'活跃度|活躍度')
# 实测手游「活跃行迹」页的当前活跃度是单独一个数字(如 120)，下面才是「活跃度」
# 标签和 20/40/60/80/100 里程碑 —— 没有 PC 的 "120/100" 形式。单靠分母 regex
# 必然读不到，因此额外接受纯数字，并用它与「活跃度」标签的距离排除里程碑。
ANDROID_DAILY_POINTS_FREE_RE = re.compile(r'^\s*(\d{1,3})\s*$')
CULTIVATION_TARGET = 'Cultivation Target'


class DailyTask(EchoBoxMixin, WWOneTimeTask, BaseCombatTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "📅 Daily Task"
        self.icon = task_icon('daily')
        self.group_name = 'Daily Activities'
        self.group_icon = task_icon('category-daily')
        self.support_schedule_task = True
        self.support_tasks = ["Tacet Suppression", "Forgery Challenge", "Simulation Challenge", CULTIVATION_TARGET]
        self.default_config = {
            'Which to Farm': self.support_tasks[0],
            'Which Tacet Suppression to Farm': 1,  # starts with 1
            'Which Forgery Challenge to Farm': 1,  # starts with 1
            'Material Selection': 'Shell Credit',
            'Farm Nightmare Nest for Daily Echo': True,
            USE_ECHO_BOX_FOR_DAILY: False,
            ADDITIONAL_TASKS: [CHECK_WEEKLY_GARDEN],
        }
        self.config_description = {
            'Which Tacet Suppression to Farm': 'The Tacet Suppression number in the F2 list.',
            'Which Forgery Challenge to Farm': 'The Forgery Challenge number in the F2 list.',
            'Which to Farm': 'Cultivation Target follows the Guidebook cultivation target and the '
                             'Cultivation Resource Farm task settings (Simplified Chinese, 16:9).',
            'Material Selection': 'Resonator EXP / Weapon EXP / Shell Credit',
            'Farm Nightmare Nest for Daily Echo': 'Farm 1 Echo from Nightmare Nest to complete Daily Task when needed.',
            USE_ECHO_BOX_FOR_DAILY: 'When needed, use an Echo box from the Bag to obtain an Echo and complete daily activities.',
            ADDITIONAL_TASKS: 'Nightmare Nest runs after stamina farming. If Tacet Suppression yielded rewards, '
                              'daily rewards are claimed before Nightmare Nest.',
        }
        material_option_list = ['Resonator EXP', 'Weapon EXP', 'Shell Credit']
        self.config_type = {
            'Which to Farm': {
                'type': "drop_down",
                'options': self.support_tasks,
                'sub_configs': {
                    'Tacet Suppression': ['Which Tacet Suppression to Farm'],
                    'Forgery Challenge': ['Which Forgery Challenge to Farm'],
                    'Simulation Challenge': [
                        'Material Selection'],
                    CULTIVATION_TARGET: [],
                }
            },
            'Material Selection': {
                'type': 'drop_down',
                'options': material_option_list
            },
            ADDITIONAL_TASKS: {
                'type': 'multi_selection',
                'options': [
                    CHECK_WEEKLY_GARDEN,
                    AUTO_FARM_NIGHTMARE_NEST,
                    MERGE_ECHO_IF_DISCARDED_OVER_1000,
                    TELEPORT_AND_FARM_4C_ECHO,
                ],
            },
        }
        self.add_exit_after_config()
        self.description = "Login, claim monthly card, farm echo, and claim daily reward"

    def run(self):
        self.validate_additional_tasks()

        WWOneTimeTask.run(self)
        self.logged_in = False
        self.ensure_main(time_out=180)

        used_stamina, daily_reward_ready = self.open_daily()
        points_unknown = getattr(self, '_daily_points_unknown', False)
        # 云游戏 OCR 偶尔读不到活跃度: 读不到时不要当作 0, 否则活跃度已满也会白刷体力.
        need_stamina = not daily_reward_ready and not points_unknown and used_stamina < 180
        target = self.config.get('Which to Farm', self.support_tasks[0])
        additional_tasks = self.config.get(ADDITIONAL_TASKS) or []
        farm_all_nests = AUTO_FARM_NIGHTMARE_NEST in additional_tasks
        cultivation_task = self.get_task_by_class(CultivationTask) if target == CULTIVATION_TARGET else None
        farm_daily_echo = (
            self.config.get('Farm Nightmare Nest for Daily Echo')
            and not daily_reward_ready
            and not points_unknown
            and target != self.support_tasks[0]
            # The cultivation target already clears its echo set Nightmare Nest when it runs.
            and not (cultivation_task and need_stamina and cultivation_task.nightmare_enabled())
        )

        tacet_farmed = False
        if need_stamina:
            if target == self.support_tasks[0]:
                spent = self.get_task_by_class(TacetTask).farm_tacet(
                    daily=True, used_stamina=used_stamina, config=self.config)
                tacet_farmed = spent > 0
            elif target == CULTIVATION_TARGET:
                try:
                    spent = cultivation_task.farm_cultivation(daily=True, used_stamina=used_stamina)
                    tacet_farmed = spent > 0
                except TaskDisabledException:
                    raise
                except Exception as e:
                    self.log_error(self.tr('CultivationTask Failed'), e)
                    self.ensure_main(time_out=180)
            elif target == self.support_tasks[1]:
                self.get_task_by_class(ForgeryTask).farm_forgery(daily=True, used_stamina=used_stamina,
                                                                 config=self.config)
            else:
                self.get_task_by_class(SimulationTask).farm_simulation(daily=True, used_stamina=used_stamina,
                                                                       config=self.config)
            self.sleep(4)

        if tacet_farmed:
            self.claim_daily()

        if farm_all_nests or farm_daily_echo:
            nightmare_task = self.get_task_by_class(NightmareNestTask)
            try:
                if not tacet_farmed:
                    # Keep the guidebook open for the daily reward claim.
                    nightmare_task.ensure_main = lambda *args, **kwargs: None
                if farm_all_nests:
                    self.log_debug('Auto Farm all Nightmare Nest')
                    self.run_task_by_class(NightmareNestTask)
                else:
                    self.log_debug('Farm Nightmare Nest for Daily Echo')
                    nightmare_task.run_capture_mode()
            except TaskDisabledException:
                raise
            except Exception as e:
                self.log_error(self.tr('NightmareNestTask Failed'), e)
                self.screenshot('NightmareNestTask')
                self.ensure_main(time_out=180)
            finally:
                if not tacet_farmed:
                    nightmare_task.__dict__.pop('ensure_main', None)

        if not tacet_farmed:
            self.claim_daily()

        self.claim_mail()
        self.sleep(1)
        self.claim_battle_pass()
        self.run_additional_tasks()
        if self.config.get(USE_ECHO_BOX_FOR_DAILY, False):
            self.complete_daily_with_echo_box()
        self.log_info(self.tr('Daily Task Completed'), notify=True)

    def complete_daily_with_echo_box(self):
        """原日常领取完成后检查积分，必要时使用一个箱子，成功后复用原领取方法。

        不改变梦魇或体力流程；积分读不清、无箱子或开箱失败时继续后续日常。
        """
        completed = False
        try:
            self._echo_box_step(self.tr('Checking daily activity after claiming rewards'))
            self.open_daily()
            points = self._wait_for_daily_points()
            if points is None:
                self.log_info(self.tr('Could not read daily activity. No Echo box was used.'))
            elif points < 100:
                self.ensure_main()
                if self.use_one_echo_box():
                    self.ensure_main()
                    self.log_info(self.tr('Claiming daily rewards after using one Echo box'))
                    self.claim_daily()
                    completed = True
        except TaskDisabledException:
            raise
        except Exception as error:
            self.log_error(self.tr('Echo box daily completion failed; continuing daily tasks: {error}').format(
                error=error))
            self.screenshot('DailyEcho_box_failed')

        # 满分、读不清和无箱子时也可能停留在清单或背包，结束时恢复主界面。
        # 不使用 finally 恢复页面，确保手动停止后不再操作游戏。
        try:
            self.ensure_main()
        except TaskDisabledException:
            raise
        except Exception as error:
            self.log_error(self.tr('Could not return to the open world after the Echo box step: {error}').format(
                error=error))
            self.screenshot('DailyEcho_return_failed')
        return completed

    def validate_additional_tasks(self):
        additional_tasks = self.config.get(ADDITIONAL_TASKS) or []
        if TELEPORT_AND_FARM_4C_ECHO in additional_tasks:
            farm_echo_task = self.get_task_by_class(FarmEchoTask)
            if farm_echo_task.config.get('Teleport to Boss', 'No') == 'No':
                raise Exception(
                    self.tr(
                        'Teleport and Farm 4C Echo requires "Teleport to Boss" to be enabled in Farm Echo Task.'
                    )
                )
        if AUTO_FARM_NIGHTMARE_NEST in additional_tasks:
            nightmare_task = self.get_task_by_class(NightmareNestTask)
            if not nightmare_task.config.get('Which to Farm'):
                raise Exception(
                    self.tr(
                        'Auto Farm all Nightmare Nest requires at least one "Which to Farm" option.'
                    )
                )
        return True

    def run_additional_tasks(self):
        additional_tasks = self.config.get(ADDITIONAL_TASKS) or []
        if CHECK_WEEKLY_GARDEN in additional_tasks:
            self.check_weekly_garden()
        if MERGE_ECHO_IF_DISCARDED_OVER_1000 in additional_tasks:
            self.check_discarded_echo()
        if TELEPORT_AND_FARM_4C_ECHO in additional_tasks:
            self.log_info(self.tr('Daily task completed, start teleport to farm 4C echo'), notify=True)
            self.run_task_by_class(FarmEchoTask)

    def check_weekly_garden(self):
        self.info_set('current task', 'check weekly garden')
        self.log_info(self.tr('check weekly garden'))
        try:
            garden_task = self.get_task_by_class(GardenTask)
            garden_task.open_garden_weekly_page()
            if garden_task.is_weekly_garden_completed():
                self.log_info(self.tr('weekly garden already completed'))
                return
            self.log_info(self.tr('weekly garden not completed, run GardenTask'))
            self.run_task_by_class(GardenTask)
        except TaskDisabledException:
            raise
        except Exception as e:
            self.log_error(self.tr('GardenTask Failed'), e)
            self.screenshot('GardenTask')
            self.ensure_main(time_out=180)

    def check_discarded_echo(self):
        self.info_set('current task', 'check discarded echo')
        self.log_info(self.tr('check discarded echo'))
        merge_echo_task = self.get_task_by_class(MergeEchoTask)
        old_notify_if_not_enough = merge_echo_task.notify_if_not_enough
        try:
            merge_echo_task.notify_if_not_enough = False
            self.run_task_by_class(MergeEchoTask)
        except TaskDisabledException:
            raise
        except Exception as e:
            self.log_error(self.tr('MergeEchoTask Failed'), e)
            self.screenshot('MergeEchoTask')
            self.ensure_main(time_out=180)
        finally:
            merge_echo_task.notify_if_not_enough = old_notify_if_not_enough

    def _battle_pass_opened(self) -> bool:
        return bool(self.wait_ocr(0.2, 0.13, 0.32, 0.22, match=re.compile(r'\d+'),
                                  settle_time=1, time_out=2, raise_if_not_found=False))

    def _open_battle_pass(self) -> bool:
        """唤起先约电台界面.

        原版靠 Alt + 点击右上角图标, 但云游戏浏览器会吞掉 Alt (Windows 菜单),
        导致界面始终打不开. 浏览器模式下直接点击入口, 并准备多个候选坐标;
        最后再走一次主终端的文字入口作为兜底.
        """
        browser = self.is_browser()
        positions = [(0.86, 0.05)] if not browser else [(0.86, 0.05), (0.90, 0.05), (0.95, 0.05)]
        for x, y in positions:
            if not browser:
                self.send_key_down('alt')
                self.sleep(0.05)
            self.click_relative(x, y, after_sleep=1)
            if not browser:
                self.send_key_up('alt')
            if self._battle_pass_opened():
                return True

        try:
            self.back(after_sleep=1.5)
            boxes = self.ocr(0, 0, 1, 1, match=re.compile('先约电台'))
            if boxes:
                self.click(boxes[0], after_sleep=2)
                if self._battle_pass_opened():
                    return True
        except Exception as error:
            self.log_debug(f'terminal battle pass fallback failed: {error}')
        return False

    def claim_battle_pass(self):
        self.log_info(self.tr('battle pass'))
        self.ensure_main()
        if not self._open_battle_pass():
            self.log_error(self.tr('can not battle pass, maybe ended'))
            self.ensure_main()
            return
        self.click_relative(0.04, 0.3, after_sleep=1)
        self.click_relative(0.68, 0.91, hcenter=True, after_sleep=3)
        self.click_relative(0.04, 0.17, after_sleep=2)
        self.click_relative(0.68, 0.91, hcenter=True, after_sleep=2)
        self.wait_ocr(0.2, 0.13, 0.32, 0.22, match=re.compile(r'\d+'),
                      post_action=lambda: self.click(0.68, 0.91, after_sleep=1), settle_time=1,
                      raise_if_not_found=False)
        self.ensure_main()

    def open_daily(self):
        self.log_info(self.tr('open_daily'))
        self.openF2Book("gray_book_quest")
        touch = getattr(self, 'touch', None)
        is_touch = bool(touch is not None and touch.is_touch)
        if not is_touch:
            # PC/云游戏的征程页要用这个坐标切到活跃行迹；手游页左侧图标栏里
            # 这个点落在内容区，反而会把已打开的活跃行迹页切走。
            self.click(0.17, 0.12, after_sleep=1)
        current = None
        if self.is_adb():
            # 手游端: 先确认"活跃行迹"子页打开。手游页没有 x/180 读数，
            # current 改由活跃度点数推导(见下面)，别再拿 /180 的 regex 硬读。
            self._android_open_activity_trace()
        else:
            progress = self.ocr(0.1, 0.1, 0.5, 0.75, match=re.compile(r'^(\d+)/180$'))
            if not progress:
                self.click(0.974, 0.6, after_sleep=1)
                progress = self.ocr(0.1, 0.1, 0.5, 0.75, match=re.compile(r'^(\d+)/180$'))
            if progress:
                current = int(progress[0].name.split('/')[0])
            else:
                current = 0
        self._daily_points_unknown = False
        points = self.get_total_daily_points()
        # 识别失败绝不能当成 0, 否则活跃度已满还会白刷一遍体力.
        daily_reward_ready = points is not None and points >= 100
        if current is None:
            # 手游「活跃行迹」页不显示 x/180; 活跃度满了就当体力进度已满，
            # 没满但读数可信时留给后续的体力任务补足。
            current = 180 if daily_reward_ready else 0
        self.info_set('current daily progress', current)
        if is_touch and touch is not None and getattr(touch, 'is_phone_mirror', False):
            touch.close_panel()
        return current, daily_reward_ready
        # 请注意：如果任务【累计消耗180点结晶波片】已完成，current 也可能为 0，因为翻页后也有可能识别不到已用体力。

    def _android_open_activity_trace(self, time_out=6):
        """手游端: 确保"活跃行迹"子页已打开。

        手游征程页的子页签位置与 PC 不同, PC 坐标 (0.17,0.12) 未必选中活跃行迹。
        先检查页面上是否已出现活跃度读数; 没有就用 OCR 定位"活跃行迹"文字点击。
        点击落空也只是点到内容区, 不会产生副作用。
        """
        deadline = time.time() + time_out
        # 手游指南书左侧是纯图标栏(没有文字可 OCR)。实测第一个图标
        # (画面 2376x1080 下的 (148,180)) 就是「活跃行迹」。
        left_tab = (0.062, 0.17)
        while True:
            if self.ocr(0.0, 0.0, 1.0, 1.0, match=ANDROID_ACTIVITY_PAGE_RE,
                        name='android_activity_page'):
                return True
            tab = self.ocr(0.0, 0.0, 1.0, 0.4, match=ANDROID_ACTIVITY_TRACE_RE,
                           name='android_activity_tab')
            if tab:
                self.log_info(self.tr('click 活跃行迹 tab (android)'))
                self.click(tab[0], after_sleep=1)
            else:
                self.log_info(self.tr('click left guidebook tab 1 (android)'))
                self.click_relative(*left_tab, after_sleep=1)
            if self.ocr(0.0, 0.0, 1.0, 1.0, match=ANDROID_ACTIVITY_PAGE_RE,
                        name='android_activity_page'):
                return True
            if time.time() >= deadline:
                self.log_warning(self.tr('安卓端未找到「活跃行迹」页签, 活跃度可能识别失败'))
                return False
            self.sleep(0.5)
        # 请注意：如果任务【累计消耗180点结晶波片】已完成，current 也可能为 0，因为翻页后也有可能识别不到已用体力。

    def get_total_daily_points(self):
        """读取当前每日活跃度; 识别不到返回 None 而不是 0.

        云游戏下 OCR 偶尔读不到活跃度数字 (日志里出现过 120 被读成 0), 单次
        失败直接当成 0 会误判成"活跃度未满"并重复消耗体力. 这里换两个区域、
        重试几次, 仍读不到就明确标记未知, 让调用方保守跳过体力任务.
        """
        if self.is_adb():
            return self._android_total_daily_points()
        # 先用上游 3.8.18 的严格读取接口（有效区分有效的 0 与识别失败），
        # 读不到再走下面的宽区域重试；两者都失败才标记未知。
        points = self._read_daily_points()
        if points is not None:
            self.info_set('total daily points', points)
            return points
        regions = [(0.19, 0.8, 0.30, 0.93), (0.15, 0.75, 0.35, 0.95)]
        for _ in range(3):
            for x, y, to_x, to_y in regions:
                points_boxes = self.ocr(x, y, to_x, to_y, match=number_re)
                if not points_boxes:
                    continue
                try:
                    points = int(re.sub(r'\D', '', points_boxes[0].name))
                except (TypeError, ValueError):
                    continue
                if 0 <= points <= 200:
                    self.info_set('total daily points', points)
                    return points
            self.sleep(0.5)

        self._daily_points_unknown = True
        self.info_set('total daily points', self.tr('未识别'))
        self.log_warning(self.tr('无法确认当前活跃度，为避免浪费体力将跳过体力刷取。'))
        return None

    def _android_total_daily_points(self):
        """手游端活跃行迹页: 读当前活跃度点数。

        手游页实测把点数显示成单独一个数字(如 120)，下面是「活跃度」标签和
        20/40/60/80/100 里程碑；只有里程碑格子里才有 x/100 文字。所以先按
        老布局找 x/100，再退回"纯数字 + 离底部'活跃度'标签最近"，用距离
        排除里程碑数字(它们离标签水平方向远得多)。
        """
        regions = [(0.0, 0.05, 1.0, 1.0), (0.0, 0.3, 0.7, 1.0)]
        for _ in range(3):
            for region in regions:
                anchors = self.ocr(*region, match=ANDROID_ACTIVITY_PAGE_RE,
                                   name='android_activity_anchor')
                # 「活跃度」在页面顶部页签和底部标签各出现一次；底部那个才是
                # 点数的标签，顶部页签离里程碑很远，参与选择会选错。
                bottom_anchors = [a for a in anchors if a.y > 0.7 * self.height] or anchors
                boxes = self.ocr(*region, match=ANDROID_DAILY_POINTS_RE,
                                 name='android_daily_points')
                candidates = []
                for box in boxes:
                    m = ANDROID_DAILY_POINTS_RE.search(box.name)
                    if not m:
                        continue
                    points, total = int(m.group(1)), int(m.group(2))
                    if 0 <= points <= total:
                        candidates.append((points, box))
                if not candidates:
                    free = self.ocr(*region, match=ANDROID_DAILY_POINTS_FREE_RE,
                                    name='android_daily_points_free')
                    for box in free:
                        m = ANDROID_DAILY_POINTS_FREE_RE.match(box.name)
                        if not m:
                            continue
                        points = int(m.group(1))
                        if 0 <= points <= 200:
                            candidates.append((points, box))
                if not candidates:
                    continue
                if bottom_anchors:
                    chosen = min(candidates, key=lambda pc: min(
                        (pc[1].x - a.x) ** 2 + (pc[1].y - a.y) ** 2
                        for a in bottom_anchors))
                else:
                    chosen = candidates[0]
                points = chosen[0]
                self.info_set('total daily points', points)
                return points
            self.sleep(0.5)

        self._daily_points_unknown = True
        self.info_set('total daily points', self.tr('未识别'))
        self.log_warning(self.tr('无法确认当前活跃度，为避免浪费体力将跳过体力刷取。'))
        return None

    def _read_daily_points(self):
        """只读取活跃度数字，不包含下方标题与里程碑；识别失败返回 None。"""
        boxes = self.ocr(0.175, 0.82, 0.285, 0.885,
                         match=re.compile(r'^\s*[0-9]{1,3}\s*$'), threshold=0.8)
        if len(boxes) == 1 and re.fullmatch(r'\s*[0-9]{1,3}\s*', boxes[0].name):
            points = int(boxes[0].name.strip())
            if 0 <= points <= 100:
                return points
        return None

    def _wait_for_daily_points(self):
        """等待连续两帧一致，用元组保留有效的 0 点。"""
        previous = None

        def read_stable():
            nonlocal previous
            points = self._read_daily_points()
            result = (points,) if points is not None and points == previous else None
            previous = points
            return result

        result = self.wait_until(read_stable, time_out=5, settle_time=0)
        if result is not None:
            self.info_set('total daily points', result[0])
            return result[0]
        return None

    def claim_daily(self):
        self.info_set('current task', 'claim daily')
        self.openF2Book('gray_book_quest')
        if not self.find_one('boss_proceed', box=self.box_of_screen(0.803, 0.189, 0.960, 0.312)):
            self.log_info(self.tr('no_boss_proceed, click claim'))
            # Click [Guidebook] in [Terminal] interface
            self.click(0.885, 0.250, after_sleep=2)
        self.log_info(self.tr('claim daily reward via  coordinate'))
        self.click(0.930, 0.882, after_sleep=1)
        touch = getattr(self, 'touch', None)
        if touch is not None and getattr(touch, 'is_phone_mirror', False):
            # 领完奖励还停在指南书里；用户校准的返回键可能落在指南书图标上，
            # 直接点面板右上角的 X 才关得掉。
            touch.close_panel(after_sleep=1)
        self.ensure_main(time_out=10)

    def claim_mail(self):
        self.info_set('current task', 'claim mail')
        self.back(after_sleep=1.5)
        self.click(0.64, 0.95, after_sleep=1)
        self.click(0.14, 0.9, after_sleep=1)
        self.ensure_main(time_out=10)


from ok import run_task
from config import config

if __name__ == "__main__":
    run_task(config, task=DailyTask, debug=True)
