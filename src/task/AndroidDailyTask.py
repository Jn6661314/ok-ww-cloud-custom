"""MuMu/安卓模拟器单账号每日任务.

配置界面与 ``DailyTask`` 完全一致(继承其全部复选框开关与任务流程), 区别仅在于
运行在 MuMu 等安卓模拟器上: 输入走独立模式层 ``touch_mode``(返回/菜单 = 键位表的
` 键; PC 的 F1「活动」与 F2「索拉指南」在触屏上没有按键, 改为直接点右上角图标栏里
对应的图标), PC/云游戏行为不受影响.

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
            '返回/打开菜单统一走键位表的 ` 键（触屏下返回=菜单=同一按钮，不会误触'
            '退出游戏弹窗），指南书/活动面板直接点击右上角对应图标（取代 PC 的 F2/F1）。'
            '请先选择 MuMu/安卓设备。'
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
