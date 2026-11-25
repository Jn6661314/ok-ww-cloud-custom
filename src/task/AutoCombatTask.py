import time

from ok import TriggerTask, Logger, TaskDisabledException
from src.char.CharFactory import char_names
from src.scene.WWScene import WWScene
from src.task.BaseCombatTask import BaseCombatTask, NotInCombatException, CharDeadException
from src.task.task_icons import task_icon

logger = Logger.get_logger(__name__)


class AutoCombatTask(BaseCombatTask, TriggerTask):
    owns_switch_healer_config = True
    _reset_combat_on_run = False

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.default_config = {'_enabled': True}
        self.trigger_interval = 0.1
        self.name = "⚔️ Auto Combat"
        self.icon = task_icon('combat')
        self.description = "Enable auto combat in Abyss, Game World etc"
        self.last_is_click = False
        self.default_config.update({
            'Auto Target': True,
            'Use Liberation': True,
            'Check Levitator': True,
            'Switch to Healer before and after Combat': True,
        })
        self.config_description = {
            'Auto Target': 'Turn off to enable auto combat only when manually target enemy using middle click',
            'Use Liberation': 'Do not use Liberation in Open World to Save Time',
            'Check Levitator': 'Toggle the levitator and verify if the character is floating',
            'Switch to Healer before and after Combat': 'Better Chance to Keep Character Alive',
        }
        self.op_index = 0
        self.char_features_warmed_up = False

    def disable(self):
        # The UI thread only invalidates state; the executor performs the reset.
        self._reset_combat_on_run = True
        super().disable()

    def reset_auto_combat(self, reason):
        self._reset_combat_on_run = False
        self.reset_to_false(reason)
        self.chars = [None, None, None]
        self.freeze_durations = []

    def warm_up_char_features(self):
        if self.char_features_warmed_up:
            return
        try:
            for char_name in char_names:
                self.get_feature_by_name(char_name)
        except Exception as e:
            logger.warning(f'warm_up_char_features failed: {e}')
            return
        self.char_features_warmed_up = True
        logger.info(f'warm_up_char_features loaded {len(char_names)} character templates')

    def run(self):
        if self._reset_combat_on_run:
            self.reset_auto_combat('auto combat restarted')
        try:
            return self.run_auto_combat()
        except TaskDisabledException:
            self.reset_auto_combat('auto combat disabled')
            raise

    def _current_char_for_perform(self):
        """取当前出战角色; MuMu 队伍识别抖动时重载一次再取。

        上游 AutoCombatTask 直接 `self.get_current_char().perform()`。在 MuMu 上
        切人动画/HUD 变化会让角色对象短暂全部为空, 这里会抛 AttributeError,
        TaskExecutor 把普通异常当作任务故障并 disable 触发任务 —— 表现就是
        "能打一会儿, 然后莫名其妙自动战斗自己关了"。BaseCombatTask.combat_once
        早就有同样的 None 守卫, 触发任务这里必须同步。
        """
        current = self.get_current_char(raise_exception=False)
        if current is not None:
            return current
        if not self.is_adb():
            return None
        self.load_chars()
        current = self.get_current_char(raise_exception=False)
        if current is None:
            self.log_debug('auto combat: current char still unavailable, retry next tick')
        return current

    def run_auto_combat(self):
        self.warm_up_char_features()
        ret = False
        if not self.scene.in_team(self.in_team_and_world):
            self.reset_auto_combat('not in team and world')
            return ret
        self.use_liberation = self.config.get('Use Liberation')
        if not self.use_liberation and not self.in_world():  # 仅大世界生效
            self.use_liberation = True
        combat_start = time.time()
        switched_to_healer = False
        try:
            while self.in_combat():
                ret = True
                try:
                    if not switched_to_healer:
                        self.switch_healer()
                        switched_to_healer = True
                    current_char = self._current_char_for_perform()
                    if current_char is None:
                        # 不要调用 None.perform(), 也不要让异常冒泡到 TaskExecutor
                        # 把触发任务 disable 掉; 等下一帧再试即可。
                        self.sleep(0.1)
                        continue
                    current_char.perform()
                except CharDeadException:
                    self.log_error(self.tr('Characters dead'), notify=True)
                    break
                except NotInCombatException as e:
                    logger.info(f'auto_combat_task_out_of_combat {int(time.time() - combat_start)} {e}')
                    break
                except Exception as e:  # noqa: BLE001 - 触发任务不能因单帧异常被关闭
                    logger.exception(f'auto_combat_task_perform_failed: {e}')
                    self.reset_auto_combat('auto combat perform failed')
                    return False
        except NotInCombatException as e:
            logger.info(f'auto_combat_task_out_of_combat {int(time.time() - combat_start)} {e}')
        except Exception as e:  # noqa: BLE001
            logger.exception(f'auto_combat_task_failed: {e}')
            self.reset_auto_combat('auto combat failed')
            return False
        if ret:
            self.combat_end()
            self.switch_healer()
        return ret

    def realm_perform(self):
        if not self.last_is_click:
            if self.op_index % 10 == 0:
                self.send_key_and_wait_animation('4', self.in_illusive_realm, enter_animation_wait=0.2)
            else:
                self.click()
        else:
            if self.available('liberation'):
                self.send_key_and_wait_animation(self.get_liberation_key(), self.in_illusive_realm)
            elif self.available('echo'):
                self.send_key(self.get_echo_key())
            elif self.available('resonance'):
                self.send_key(self.get_resonance_key())
            elif self.is_con_full() and self.in_team()[0]:
                self.send_key_and_wait_animation('2', self.in_illusive_realm)
        self.last_is_click = not self.last_is_click
        self.op_index += 1
        self.sleep(0.02)


from ok import run_task
from config import config

if __name__ == "__main__":
    run_task(config, task=AutoCombatTask, debug=True)
