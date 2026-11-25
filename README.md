## 更新日志

按**日**汇总，完整改动明细见 [Releases](https://github.com/Jn6661314/ok-ww-cloud-custom/releases)（中英双语）。

### 2026-11-25

- **[v1.5.1](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.1)** — 修复全新安装装不全导致的启动失败：首装脚本与恢复脚本改为共用同一份 32 文件清单（此前首装只装 15 个，漏掉 `DeviceManager.py`、`BaseWWTask.py` 等 17 个关键文件）；安装提示词补充 ok-ww 目录结构说明与「报没 adb / 找不到 .py」排查清单。

### 2026-11-24

- **[v1.5.0](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.0)** — 梦魇聚落（残象聚落）传送按钮改用 OCR 识别（实测置信度 0.99998）；登录后黑屏 30 秒冗余等待窗口，不再打断每日任务；安卓设备启动时用 adb 拉起鸣潮。
- **[v1.4.0](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.4.0)** — 新增安卓独立每日任务；修复安卓每日任务「卡在大世界不动」（新增 `android_world.py`）；MuMu 抓屏黑帧拦截与「连接已断开」弹窗处理；安卓端 F1/F2 改为直接点右上角图标（新增 `android_book.py` 类别定位）。
- **[v1.3.0](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.3.0)** — 完整更新到官方 v3.8.14（ok-script 3.0.13 WebRTC）；新增安卓触屏操作模式层 `touch_mode.py`；MCP 端口冲突自适应；MuMu 模拟器窗口化操作（PC 式输入）。

### 2026-11-23

- **[v1.2.0](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.2.0)** — 云鸣潮战斗工坊参数失效与乱切人修复；无怪物时自动退出战斗；Win10 云鸣潮兼容；MuMu 触屏模式 esc 返回键；ADB 触屏键位表补全（A-Z / 0-9 / 反引号）。
- **[v1.1.0](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.1.0)** — 拉海洛方块·逆转支持「故障方块」机制；云鸣潮 UID 遮罩；通关后退回活动主页卡住修复；玩法说明弹窗自动关闭；新增本地安卓模拟器（ADB）设备入口；4 个上游 PR 提交。
- **[v1.0.1](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.0.1)** — 新增 Agent 一键安装提示词（`AGENT_INSTALL_PROMPT.md`）。
- **[v1.0.0](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.0.0)** — 首次发布：云鸣潮基础支持、云每日与云多账号任务、任务错误恢复、进入游戏与领取修复、多账号配置持久化、编队自定义轴与队伍工坊、工坊离线回退、备份与一键恢复。


# ok-wuthering-waves 云鸣潮定制补丁

> 非官方第三方定制补丁集，仅包含相对于上游项目新增/修改的文件，**不是**完整程序。
> 使用前请先安装官方原版 ok-wuthering-waves。

## 上游与授权（重要）

| 项目 | 地址 | 说明 |
| --- | --- | --- |
| **ok-wuthering-waves（鸣潮官方自动化项目）** | <https://github.com/ok-oldking/ok-wuthering-waves> | 本仓库的所有游戏逻辑、图像识别与任务框架均来自该项目，版权归原作者所有 |
| **ok-script** | <https://github.com/ok-oldking/ok-script> | 上游使用的自动化框架，`ok/device/capture_methods/browser.py` 的定制基于它 |
| **队伍代码工坊离线快照** | <https://github.com/yamadafz/ok-ww-char-code> | 社区公开镜像，仅用于工坊数据离线回退 |

- 本仓库遵循与上游一致的 **GNU Affero General Public License v3.0**，完整许可证见 [`LICENSE.txt`](LICENSE.txt)。
- 本项目与 `ok-oldking` 官方无任何隶属关系，"角色代码/编队自定义轴/工坊"功能是从**上游自身历史版本**（删除提交 `d0a59291` 的父提交）恢复并适配新版 GUI，并非本仓库原创。
- 如果这些功能对你有用，请优先给上游项目点 Star。

## 功能更新内容

一句话概览：**云游戏多账号日常自动化 + 历史功能回归**。

- 云鸣潮启动支持；每个账号独立浏览器 Cookie profile，互不串号
- **本地安卓模拟器（ADB）设备入口**：MuMu 12 / 通用 ADB 设备自动出现在设备列表，MuMu 可切 IPC 高速截图通道（详见下方"ADB 模拟器"一节）
- 云游戏后台运行，无需鼠标点击浏览器窗口
- 云每日任务（与本地每日相同的复选框）、云多账号每日任务（每账号独立配置）
- 手动保存 Cookie / 手动切换账号（重启浏览器方式）
- 任务出错自动恢复：优先重启浏览器并重跑，失败再回退刷新页面
- 进入游戏分级冷却，解决"要点两次开始游戏"；进入完成检测；邮箱奖励误判月卡的死循环修复
- 拉海洛方块云游戏浏览器模式适配；先约电台唤起修复；每日活跃度多次识别
- **拉海洛方块·逆转支持"故障方块"新机制**（1/2 级故障自动识别，参与凑行消除但留在棋盘上）
- **云鸣潮 UID 遮罩**：自动盖住右下角 UID 区域（CDP 截图同样遮挡，`cover_uid` 可关闭）
- 拉海洛通关后退回活动主页自动点「立即前往」返回关卡列表；玩法说明弹窗（如"1 级故障方块"）自动点右上角 X 关闭，不再误报中断
- 多账号配置持久化修复（排队/重启后保存不丢失、配置文件损坏自动回退备份）
- 从上游历史恢复 **角色代码（编队自定义轴）** 页面与 **队伍创意工坊**（含离线快照）
- **云鸣潮战斗修复**：工坊队伍代码不再被每轮识别退回内置类（"工坊参数不生效"）；单帧识别失败时用缓存身份补全、整队工坊代码保活；协奏环颜色识别在云视频流下自动加容差，减少误判导致的"乱切人"（本地客户端行为不变）
- "刷梦魇巢穴 / 4C"由配置复选框自行决定（默认开启），不再强制关闭
- 部分改动已按主题拆分提交**上游 PR**：[ok-wuthering-waves #1873](https://github.com/ok-oldking/ok-wuthering-waves/pull/1873)（云鸣潮多账号）、[#1874](https://github.com/ok-oldking/ok-wuthering-waves/pull/1874)（故障方块）、[ok-script #130](https://github.com/ok-oldking/ok-script/pull/130)（UID 遮罩）、[#131](https://github.com/ok-oldking/ok-script/pull/131)（账号 profile/登录态/后台输入），均通过 CI 与 SonarCloud Quality Gate；合并前本仓库仍是完整可用的快照

详细的逐项更新说明见 [`CHANGES.md`](CHANGES.md)。

## 隐私说明

- 本仓库**不包含任何账号、密码、手机号、Cookie、浏览器登录态或 `cloud_profiles` 数据**，源码中出现的账号/邮箱均为虚构占位示例。
- 本仓库**不包含** `configs/MultiAccountConfig.json`、`MultiAccountResults.json`、`devices.json` 等运行时配置。
- 安装/恢复脚本只覆盖定制源码文件，**不会**改动你的 Cookie 或任务配置。
- 工坊快照只包含社区公开分享的队伍代码，不含任何个人登录信息。

## 让 Agent 帮你快速安装

不想手动操作？把 [`AGENT_INSTALL_PROMPT.md`](AGENT_INSTALL_PROMPT.md) 里的整段提示词复制给你常用的 Agent（WorkBuddy / Claude / Cursor 等），它会自动检查环境、关闭软件、运行安装脚本并验证任务是否出现。提示词已包含"不覆盖 Cookie / 账号配置 / 自定义队伍"的约束。

## 安装

适用于 pyappify 安装版，默认路径 `%LOCALAPPDATA%/ok-ww/data/apps/ok-ww/working`。

> **先看清目录结构**（这是最常见的误解）：
>
> ```text
> %LOCALAPPDATA%/ok-ww/                              ← 安装根目录，只有 ok-ww.exe，没有任何 .py
> %LOCALAPPDATA%/ok-ww/data/apps/ok-ww/working/     ← 实际运行的源码
> %LOCALAPPDATA%/ok-ww/data/apps/ok-ww/repo/        ← 源码副本（官方更新会从这里覆盖 working）
> %LOCALAPPDATA%/ok-ww/data/apps/ok-ww/python/      ← ok-ww 自带的 Python（含 adbutils 等依赖）
> ```
>
> 在安装根目录里找 `.py` 文件**一定找不到**，这是正常的，不是安装失败。
> 跑脚本请用 ok-ww 自带的 Python：`%LOCALAPPDATA%/ok-ww/data/apps/ok-ww/python/python.exe`；
> 系统 Python 通常没装 `adbutils`，会报 `ModuleNotFoundError: adbutils`（看起来像"没有 adb"）。

1. 关闭 ok-ww。
2. 克隆或下载本仓库（**要完整仓库**，安装清单在 `restore.py` 里，只下载单个文件会装不全）。
3. 按需补全工坊代码包（可选，索引已随仓库提供）：

   ```bash
   python tools/download_workshop_cache.py
   ```

4. 应用补丁：

   ```bash
   python tools/install_to_local_app.py
   ```

   也可传自定义 working 路径：`python tools/install_to_local_app.py "D:/path/to/working"`。

   脚本会把**全部 32 个**定制文件复制到 `working` 与 `repo` 两处，结束时打印
   `copied 32 files -> ...` 两行 —— 确认这两行都出现，说明装齐了。

5. 打开 ok-ww，选择设备"云游戏"，即可看到云每日/云多账号/保存 Cookie/切换账号任务，以及"角色代码"页（含工坊）。

> **如果你的 ok-ww 是用旧版本安装器装的**：可能只装了 15 个文件，漏掉 `DeviceManager.py`、
> `BaseWWTask.py` 等 17 个关键文件，表现为启动报错、任务列表不全、报"没 adb"。
> 关闭 ok-ww 后补跑 `python restore.py` 即可补齐全部 32 个文件。

## 本地安卓模拟器（ADB）

除了 Windows 客户端和云浏览器，ok-ww 现在也支持本地安卓模拟器 / 真机，通过 ADB 连接。设备选择列表会自动列出已安装的模拟器与已连接的 ADB 设备。

**游戏包名**：国服 `com.kurogame.mingchao`、国际服 `com.kurogame.wutheringwaves`，脚本按实际安装情况自动识别并拉到前台，两者都装了也没问题。

**准备工作**：

1. 若首次使用报缺少 `adbutils`，在 ok-ww 安装目录执行 `python -m pip install adbutils`（`adb.exe` 由该包自带，无需单独安装 Android SDK）。
2. 真机需在「开发者选项」里打开 USB 调试；无线设备先用 `adb connect <IP>:<端口>` 连上（MuMu 等模拟器一般会自动连接，无需手动操作）。

**在 ok-ww 里连接**：

1. 启动模拟器 / 真机并装好鸣潮。
2. 打开 ok-ww，在设备选择里找到对应设备（如 `MuMuPlayer-15.0-0`、`127.0.0.1:16384`），点开连接设置：
   - **MuMu 12**：捕获方式选 `Ipc`（`Nemu Ipc Capture`，模拟器原生截图通道，速度快，推荐）——脚本会自动识别已安装的 MuMu 12 实例并给出该选项；
   - 其他模拟器 / 真机：保持 `ADB`（通用 `adb screencap`，后台可用但约 3fps / 300ms 每帧）。
3. 多开模拟器时每个实例是独立设备，按序列号分别选择即可，互不干扰。
4. 之后按普通设备运行任务。

**注意**：ADB 设备是独立设备入口，不套用云浏览器（云鸣潮）的专用逻辑；通用 ADB 通道约 3fps，适合日常 / 回合类内容，实时战斗循环（如精细变轴）建议用 MuMu IPC 通道，并自行实测效果。

### 安卓端常见问题

**「每日任务进入大世界以后一直卡在那不动，也不跳过也没其他操作也没额外日志」**

这是 2026-11-24 之前的老问题，根因与修法见上面更新日志的「安卓每日任务"卡在大世界不动"的根因修复」。升级后日志里会出现这几条，可以直接对照判断卡在哪一步：

| 日志关键字 | 含义 |
| --- | --- |
| `in_team(android): in world (radar_yellow=...)` | 已在大世界，判定通过 |
| `in_team(android): not in world (...)` | 不在大世界，后面会列出四个判据的实测数值 |
| `安卓端截图全黑(MuMu 抓屏失败)` | MuMu 抓到了空帧，不是"不在大世界" |
| `Game disconnected, closing the notice and logging in again` | 命中了【连接已断开】弹窗，正在重新登录 |
| `MuMu 模拟器抓屏持续返回空画面(全黑)` | 抓屏通道真的坏了，需检查模拟器窗口是否可见、是否开启「后台保活」 |

**MuMu 抓屏偶尔返回全黑画面**：模拟器窗口被最小化/遮挡、或 MuMu 设置里开了「后台保活」时，IPC 通道会返回一张纯黑图。现在脚本会先自动重建连接重试，仍失败会明确报错，不会再"卡住不动"。

**停在【连接已断开】对话框**：挂机过久或网络抖动导致。脚本会自动点"确认"并重新登录；也可以手动把游戏切回大世界再启动任务。

**报"没有 adb" / 找不到 adb.exe**：按顺序排查这 4 条，前两条最常见。

| # | 现象 | 原因与解法 |
| --- | --- | --- |
| 1 | 装完补丁后启动就报错、任务列表不全 | 旧安装器只装了 15 个文件，漏掉 `DeviceManager.py`、`BaseWWTask.py` 等 17 个关键文件 → 关闭 ok-ww 补跑 `python restore.py` |
| 2 | 用系统 Python 跑脚本报 `ModuleNotFoundError: adbutils` | 系统 Python 没装 adbutils → 改用 ok-ww 自带的 `%LOCALAPPDATA%/ok-ww/data/apps/ok-ww/python/python.exe`（它自带 adbutils 和 `adb.exe`） |
| 3 | 选了设备但报 `Emulator is not connected, start the emulator first!` | 模拟器没启动，或 adb 端口不通（MuMu 默认 `127.0.0.1:16384`）→ 先启动模拟器 |
| 4 | 日志出现 `set ADBUTILS_ADB_PATH failed` | adbutils 没装全或 `adb.exe` 缺失 → 用自带 Python 重装，或 `python -m pip install adbutils` |

**云游戏用户完全不需要 adb**：只有「安卓/本地模拟器」设备类型才走 adb 通道，
选「云游戏」时这段逻辑完全不执行。

## 更新被官方覆盖后怎么恢复

ok-ww 自带更新会还原 `working` 和 `repo` 中的文件。两种恢复方式：

- **直接覆盖**（同版本文件被还原）：关闭 ok-ww 后双击 `一键恢复.bat`，或命令行 `python restore.py`。恢复前会自动备份当前文件。
- **重新打补丁**（大版本升级后结构变化）：按上面"安装"步骤运行 `install_to_local_app.py`。

两种都不会动账号 Cookie 和任务配置。详见 [`docs/backup-and-restore.md`](docs/backup-and-restore.md)。

## 目录结构

```text
config.py                   patched 后的上游 config（任务/标签页注册）
src/                        新增与修改的 ok-ww 源码
  task/android_world.py     安卓端"在大世界且在队伍中"判定（雷达黄点/协奏金球等 HUD 判据）
  task/android_book.py      安卓端索拉指南（PC 的 F2）类别图标定位（笔画掩码 + 多尺度 IoU）
  task/touch_mode.py        安卓触屏操作模式层（返回=菜单=` 键，F1/F2 改为点右上角图标）
  task/NightmareNestTask.py 梦魇/残象聚落传送（"快速旅行"按钮 OCR 识别 + 确认按钮兜底）
ok/device/capture_methods/  patched 后的 ok-script 捕获模块
  nemu_ipc.py               MuMu IPC 抓屏（全黑帧拦截 + 重连重试 + 30 秒冗余等待窗口）
ok/device/DeviceManager.py  patched 后的设备管理（安卓设备启动时用 adb 拉起鸣潮）
tools/                      安装、patch、工坊缓存下载与 Release 发布脚本
  publish_release.py         把 releases/*.md 发布成 GitHub Release（自动打 tag）
releases/                   各版本的完整改动明细（中英双语，发布脚本的正文来源）
tests/                      新增/修改的单元测试
docs/                       多账号配置说明、备份恢复说明
workshop_cache/             工坊离线索引（teams.json + teams/*.json）
restore.py / 一键恢复.bat   官方更新覆盖后的一键恢复
LICENSE.txt                 AGPL-3.0 许可证原文
```

## 免责声明

本仓库为个人定制补丁，按"现状"提供，不保证与上游后续版本兼容。使用自动化脚本可能违反游戏服务条款，风险自负。
