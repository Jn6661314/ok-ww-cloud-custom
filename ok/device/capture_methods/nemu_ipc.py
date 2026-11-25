import json
import os
import re
import time

import numpy as np

from ok.util.collection import deep_get
from ok.util.logger import Logger

from ok.device.capture_methods.base import BaseCaptureMethod
from ok.task.exceptions import CaptureException

logger = Logger.get_logger(__name__)

# MuMu IPC 抓屏偶尔会"返回成功"但实际给出一张全黑画面(缓冲区没有真正写入像素)。
# 上层拿到这种帧会认为画面正常, 任务就会一直停在原地: 既不报错, 也不跳过,
# 日志里也看不到任何异常(只有一堆无意义的模板匹配分数)。
# 这里统一在截图后端拦截: 全黑帧先重建 IPC 连接再重试, 连续失败才抛带明确原因的异常。
BLACK_FRAME_MAX_VALUE = 8
BLACK_FRAME_MAX_RETRY = 3
BLACK_FRAME_RETRY_INTERVAL = 0.5
# 登录/加载阶段模拟器会正常黑屏十几秒(游戏正在载入资源, 窗口还没渲染出画面),
# 这段时间全黑属于正常现象, 不能当成"抓屏失败"把整个每日任务打断。
# 所以给一个冗余等待窗口: 窗口内一直是黑屏就继续等, 超过窗口才判定为真的抓不到画面。
BLACK_FRAME_GRACE_PERIOD = 30


def is_black_frame(frame):
    """帧是否为空画面(全黑)。None 也按空画面处理。"""
    if frame is None:
        return True
    try:
        return int(np.asarray(frame).max()) <= BLACK_FRAME_MAX_VALUE
    except (ValueError, TypeError):
        return False


class NemuIpcCaptureMethod(BaseCaptureMethod):
    name = "Nemu Ipc Capture"
    description = "MuMu Player native capture"

    def __init__(self, device_manager, exit_event, width=0, height=0):
        super().__init__()
        self.device_manager = device_manager
        self.exit_event = exit_event
        self._connected = (width != 0 and height != 0)
        self.nemu_impl = None
        self.emulator = None

    def update_emulator(self, emulator):
        self.emulator = emulator
        logger.info(f'update_path_and_id {emulator}')
        if self.nemu_impl:
            self.nemu_impl.disconnect()
            self.nemu_impl = None

    def init_nemu(self):
        if not self.nemu_impl:
            self.check_mumu_app_keep_alive_400()
            from ok.capture.adb.nemu_ipc import NemuIpc
            self.nemu_impl = NemuIpc(
                nemu_folder=self.base_folder(),
                instance_id=self.emulator.player_id,
                display_id=0,
                runtime_version=self.runtime_version()
            )

    def reset_nemu(self):
        """重建 IPC 连接。抓屏通道失效(空画面/连接断开)时用来自恢复。"""
        if self.nemu_impl:
            try:
                self.nemu_impl.disconnect()
            except Exception as e:
                logger.warning(f'disconnect nemu ipc failed: {e}')
            self.nemu_impl = None

    def base_folder(self):
        return os.path.dirname(os.path.dirname(self.emulator.path))

    def runtime_version(self):
        match = re.search(r'-(\d+(?:\.\d+)+)-\d+$', getattr(self.emulator, 'name', ''))
        return match.group(1) if match else '12.0'

    def check_mumu_app_keep_alive_400(self):
        instance_name = getattr(self.emulator, 'name', None) or f'MuMuPlayer-12.0-{self.emulator.player_id}'
        file = os.path.abspath(os.path.join(
            self.base_folder(),
            'vms', instance_name, 'configs/customer_config.json'))

        try:
            with open(file, mode='r', encoding='utf-8') as f:
                s = f.read()
                data = json.loads(s)
        except FileNotFoundError:
            logger.warning(f'Failed to check check_mumu_app_keep_alive, file {file} not exists')
            return False
        value = deep_get(data, keys='customer.app_keptlive', default=None)
        if str(value).lower() == 'true':
            logger.error('Please turn off enable background keep alive in MuMuPlayer settings')
            raise Exception('Please turn off enable background keep alive in MuMuPlayer settings')
        return True

    def close(self):
        super().close()
        if self.nemu_impl:
            self.nemu_impl.disconnect()
            self.nemu_impl = None

    def do_get_frame(self):
        if self.exit_event.is_set():
            return None
        # 冗余等待窗口的起点: 在窗口内, 全黑帧一律当作"登录/加载中"继续等。
        deadline = time.monotonic() + BLACK_FRAME_GRACE_PERIOD
        attempt = 0
        ipc_reset = False
        while True:
            self.init_nemu()
            if not self.nemu_impl:
                return None
            try:
                frame = self.nemu_impl.screenshot(timeout=0.5)
            except Exception as e:
                # 底层 @retry 重试耗尽后抛的是不带 message 的裸 Exception,
                # 这里补上可读原因, 否则界面上只会显示一个空错误。
                reason = str(e).strip() or '连接模拟器超时'
                raise CaptureException(
                    f'MuMu IPC 抓屏失败({reason}), '
                    f'请确认 MuMu 模拟器正在运行、窗口可见, 并关闭「后台保活」后重试'
                ) from e
            if not is_black_frame(frame):
                return frame
            attempt += 1
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise CaptureException(
                    f'MuMu 模拟器抓屏持续 {BLACK_FRAME_GRACE_PERIOD} 秒返回空画面(全黑), '
                    f'请确认模拟器窗口可见(未被最小化/遮挡)且未开启「后台保活」, 然后重试'
                )
            logger.warning(
                f'MuMu 抓屏返回空画面(全黑), 第 {attempt} 次, '
                f'登录/加载期的黑屏属正常现象, 冗余等待窗口还剩 {remaining:.1f}s')
            if not ipc_reset or attempt % BLACK_FRAME_MAX_RETRY == 0:
                # 重建 IPC 连接(缓冲区可能真的失效了)。
                # 第一帧黑就重建一次; 之后若仍连续黑, 每 BLACK_FRAME_MAX_RETRY 次再重建一次,
                # 避免加载期无休止地重连。
                ipc_reset = True
                self.reset_nemu()
            time.sleep(min(BLACK_FRAME_RETRY_INTERVAL, remaining))

    def connected(self):
        return True
