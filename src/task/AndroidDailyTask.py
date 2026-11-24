"""MuMu/安卓模拟器单账号每日任务.

配置界面与 ``DailyTask`` 完全一致(继承其全部复选框开关与任务流程), 区别仅在于
运行在 MuMu 等安卓模拟器上: 输入走独立模式层 ``touch_mode``(返回/菜单 = 键位表的
` 键, 指南书 = F2, 由模拟器键位映射转成游戏操作), PC/云游戏行为不受影响.

Select the MuMu/安卓 device before running this task.
"""

from src.task.DailyTask import DailyTask
from src.task.task_icons import task_icon


class AndroidDailyTask(DailyTask):
    """DailyTask running on a MuMu/ADB emulator, with identical switches."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = '📱 每日任务（MuMu/安卓）'
        self.group_name = 'Daily Activities'
        self.group_icon = task_icon('category-daily')
        self.description = (
            '安卓模拟器专用：配置开关与每日任务完全一致，当前设备为 MuMu/安卓时使用。'
            '返回/菜单走键位表映射（` 键），指南书用 F2。请先选择 MuMu/安卓设备。'
        )

    def run(self):
        if not self.is_adb():
            raise Exception(self.tr('请先选择「MuMu/安卓」设备后运行此任务。'
                                    '云游戏请用「每日任务（云鸣潮）」，PC 请用「每日任务」。'))
        super().run()


from ok import run_task  # noqa: E402
from config import config  # noqa: E402

if __name__ == '__main__':
    run_task(config, task=AndroidDailyTask, debug=True)
