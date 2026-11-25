# 更新日志

本文件按**日**汇总。每一版的完整改动明细（中英双语）见
[Releases](https://github.com/Jn6661314/ok-ww-cloud-custom/releases)。

所有条目均已在运行目录实际验证。

---

## 2026-11-25

| 版本 | 一句话摘要 |
| --- | --- |
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
