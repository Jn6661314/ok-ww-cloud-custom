# 更新日志

本文件按**日**汇总。每一版的完整改动明细（中英双语）见
[Releases](https://github.com/Jn6661314/ok-ww-cloud-custom/releases)。

所有条目均已在运行目录实际验证。

---

## 2026-11-25

| 版本 | 一句话摘要 |
| --- | --- |
| [v1.5.8](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.8) | 修复 MuMu 打着打着停：队伍识别改为按编队 OCR 读 1/2/3 徽章（不再写死 2 人队/1 号位），切人键按键位映射的"切换角色N"自动适配；新增 AutoCombatTask 安卓覆盖层，当前角色为空时重载重试并捕获普通异常，避免触发任务被 TaskExecutor 关闭；安卓血条闪烁加宽限，PC/云游戏行为不变 |
| [v1.5.7](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.7) | 修复 MuMu 手游端“手动锁敌也不打、角色一动不动”：实际交互层因 `capture=ipc` 回退到 ADBInteraction，`input keyevent` 不触发手游键位映射、无坐标点击又落在屏幕中心空地；安卓战斗中点击改为右下角攻击按钮，模拟器上先把 MuMu 切前台再用 Pynput 发真实键盘触发键位映射（Y 锁敌 / e-q-r 技能 / WASD 走位），PC/云游戏/真机行为不变 |
| [v1.5.6](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.6) | 修复 MuMu 自动战斗启动即报错停止：战斗跑起来后漂泊者重击连招调用 `mouse_down()`，但上游 ADBInteraction 没有该方法抛 AttributeError；在 BaseWWTask 覆盖 `mouse_down/mouse_up`，安卓端用 nemu 触摸长按（无通道降级为点击），PC/云游戏行为不变 |
| [v1.5.5](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.5) | 修复 MuMu 掉线弹窗导致卡住不动：游戏弹出"连接已断开"遮暗画面后，触发任务/战斗循环不经过 `is_main()`，掉线检测从不触发，脚本一直在暗屏上找血条→retarget 失败→卡死且不重登；改为战斗判定入口也检查掉线弹窗，点确认并复位登录态，由 AutoLoginTask 自动重登（含 15s 防重复点击节流），PC/云游戏行为不变 |
| [v1.5.4](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.4) | 修复 MuMu 打着打着就停：切人/intro 动画期间 HUD 圆形头像短暂消失，`in_team()` 返回 -1 导致切人卡 5 秒后中断战斗；安卓端切人改用脚本维护的逻辑下标，不再依赖画面判定，PC/云游戏行为不变 |
| [v1.5.3](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.3) | 修复 MuMu 手动锁定后仍不战斗：手游 UI 无 PC 锁定图标、`has_target()` 恒失败一直 retarget；改为安卓端用头顶红色血条判定目标（阈值 0.95→0.8），锁敌键改用 Y 键（原中键对模拟器无效），PC/云游戏行为不变 |
| [v1.5.2](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.2) | 修复 MuMu/安卓端无法自动战斗：安卓队伍栏无数字徽章导致当前角色下标恒为 -1，`get_current_char()` 返回 None 使 `.perform()` 抛 AttributeError；改为脚本维护逻辑下标 + 兜底选角 + 切人同步，PC/云游戏行为不变 |
| [v1.5.1](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.1) | 修复全新安装装不全导致的启动失败：首装脚本与恢复脚本共用同一份 32 文件清单（此前首装只装 15 个，漏掉 `DeviceManager.py`、`BaseWWTask.py` 等 17 个关键文件）；安装提示词补充目录结构说明与"报没 adb / 找不到 .py"排查清单 |

## 2026-11-24

| 版本 | 一句话摘要 |
| --- | --- |
| [v1.5.0](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.0) | 梦魇聚落传送按钮改用 OCR 识别；登录后黑屏 30 秒冗余等待；安卓设备启动时用 adb 拉起鸣潮；安卓索拉指南开书判定改为模板法 |
| [v1.4.0](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.4.0) | 新增安卓独立每日任务；修复安卓每日任务"卡在大世界不动"（新增 `android_world.py` 判定）；MuMu 抓屏黑帧拦截；新增安卓端"连接已断开"弹窗处理；安卓端 F1/F2 改为直接点右上角图标（新增 `android_book.py` 类别定位） |
| [v1.3.0](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.3.0) | 完整更新到官方 v3.8.14（ok-script 3.0.13 WebRTC）；新增安卓触屏专用操作模式层 `touch_mode.py`；MCP 端口冲突自适应；MuMu 模拟器窗口化操作（PC 式输入） |

## 2026-11-23

| 版本 | 一句话摘要 |
| --- | --- |
| [v1.2.0](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.2.0) | 云鸣潮战斗工坊参数失效与乱切人修复；无怪物时自动退出战斗；Win10 云鸣潮兼容；MuMu 触屏模式 esc 返回键；ADB 触屏键位表补全（A-Z / 0-9 / 反引号） |
| [v1.1.0](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.1.0) | 拉海洛方块·逆转支持"故障方块"机制；云鸣潮 UID 遮罩；通关后退回活动主页卡住修复；玩法说明弹窗自动关闭；新增本地安卓模拟器（ADB）设备入口；4 个上游 PR 提交 |
| [v1.0.1](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.0.1) | 新增 Agent 一键安装提示词（`AGENT_INSTALL_PROMPT.md`） |
| [v1.0.0](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.0.0) | 首次发布：云鸣潮基础支持、云每日与云多账号任务、任务错误恢复、进入游戏与领取修复、多账号配置持久化、编队自定义轴与队伍工坊、工坊离线回退、备份与一键恢复 |

---

## 长期保留的能力

以下能力自 v1.0.0 起一直存在，后续版本未做破坏性改动：

- **云鸣潮**：设备入口与启动逻辑、per-account Cookie profile 隔离、浏览器后台运行伪装、进入游戏完成检测。
- **云多账号**：`CloudDailyTask` / `CloudMultiAccountTask`、每账号独立配置、保存 Cookie / 切换账号两个一次性任务。
- **任务错误恢复**：优先重启浏览器并重跑，失败回退刷新页面，同一错误 3 次后停止。
- **角色代码 / 队伍工坊**：从上游历史恢复并适配新版 GUI，含工坊服务器下线后的离线快照回退。
- **备份与一键恢复**：`restore.py` / `一键恢复.bat` 同时恢复到 `working` 与 `repo`，Cookie 与账号配置始终排除在外。
