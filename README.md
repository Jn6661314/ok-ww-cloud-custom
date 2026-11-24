## 更新日志

**2026-11-24（MuMu 模拟器窗口化操作：像 PC 客户端一样输入）**

- **模拟器输入改为 PC 键盘/鼠标消息**：以前 adb 设备固定用 `input keyevent`/`input tap`——这是直接给安卓系统发按键，**绕过了 MuMu 的键位映射**，导致 esc 变成安卓返回键、主界面弹出"退出游戏"、键位表完全没被用上。现在（`config.py` + `ok/device/DeviceManager.py`）：模拟器的截图与输入都走 Windows 窗口通道（`capture_method: windows` + `interaction: PostMessage`），与 PC 客户端/云游戏完全一致——发真实键盘/鼠标消息给 MuMu 窗口，由模拟器自己的键位映射转成游戏操作。顺带修复了 `MouseResetTask` 在 adb 下刷 `get_abs_cords` 报错的问题（PC 截图类本有该方法）。

**2026-11-24（安卓触屏专用操作模式）**

- **安卓键位/操作抽成独立模式层**（`src/task/touch_mode.py`）：以前"打开菜单"和"返回/关闭"两种语义都压在 `esc` 上，触屏下又被全局映射成 `KEYCODE_BACK`，导致 MuMu 里 `wait main` 一直触发返回、打不开菜单（实测主界面发 `KEYCODE_BACK` 弹的是"是否确定退出游戏"）。现把触屏操作集中到一个模式层：安卓端「返回=打开菜单」是同一个按钮，按你给的键位表用 `` ` ``（菜单/跳过 → `KEYCODE_GRAVE`）；指南书用 `F2`。PC/云游戏行为完全不变（仍走各自的 `esc`）。`is_main`、`open_esc_menu`、`openF2Book` 已改走该入口。
- **补全触屏功能键**：`ADB_KEY_MAP` 增加 `F1-F12` → `KEYCODE_F1..F12`，指南书 `F2` 在触屏下才是合法按键。

**2026-11-24（MCP 端口自适应）**

- **修复 MCP 服务器开启报 Errno 13**：常见输入法（如百度输入法）会常驻占用 `0.0.0.0:8765`，OKWW 绑 `127.0.0.1:8765` 时 Windows 返回 `EACCES(13)` 而非 `EADDRINUSE`，原逻辑只认后者就直接报错。现在 EACCES/10013 也视为端口冲突，自动递增到 8766 等可用端口；实际端口写回 connection 文件，客户端动态发现，无需手动改配置。（`ok/core/mcp_server.py`）

**2026-11-24（完整更新到官方 v3.8.14）**

- **同步官方 v3.8.14（ok-script 3.0.13）**：云游戏抓屏改为直接读取游戏视频流（WebRTC），浏览器最小化时也能截图；浏览器启动失败后再次启动无需重启；任务出错即使发生在等待后也会保存截图到 `screenshots/error/`；拉海洛方块落点预览不匹配不再每次截图。已同步官方全部改动（含新增 `browser_webrtc.py`），并把定制逐项合并回新版、验证兼容。
- **定制与新版共存**：合并版 `browser.py` 在官方 WebRTC 抓屏基底上保留了 Cookie/账号 profile 隔离、后台输入伪装、UID 遮挡；`config.py` 在 v3.8.14 上新加 `capture: webrtc`，同时保留 adb 段、自定义工坊页、云多账号任务列表；`RahaiBlocksTask.py` 保留云鸣潮支持并吸收官方「不再狂存截图」改动。24 个定制文件三处（working/repo/备份）一致。

**2026-11-24（此前的定制修复）**

- **怪物消失后不再对着空气自动战斗**：连续 2 秒没有锁定目标且看不到血条即判定战斗结束；大招动画等待超时时清除残留的「大招中」标志，避免战斗状态永远退不出去。
- **Win10 也能玩云鸣潮**：WGC 抓屏可用性门槛从 Win11（build 20348）放宽到实际最低要求（Win10 2004 / build 19041），并去掉抓屏黄色边框；云游戏设备标签同步更新。
- **MuMu 模拟器触屏键位补全**：ADB 交互下，`esc` 从游戏不认的 `KEYCODE_ESCAPE` 改为安卓返回键 `KEYCODE_BACK`；补全 A-Z / 0-9 字母数字键映射（`send_key('f')` 等原本原样透传成非法 `input keyevent f`，游戏根本收不到）；反引号映射为 `KEYCODE_GRAVE`。这是日常任务在触屏模式下大面积失效的主因（不影响 PC 与云游戏模式）。

---

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

1. 关闭 ok-ww。
2. 克隆或下载本仓库。
3. 按需补全工坊代码包（可选，索引已随仓库提供）：

   ```bash
   python tools/download_workshop_cache.py
   ```

4. 应用补丁：

   ```bash
   python tools/install_to_local_app.py
   ```

   也可传自定义 working 路径：`python tools/install_to_local_app.py "D:/path/to/working"`。

5. 打开 ok-ww，选择设备"云游戏"，即可看到云每日/云多账号/保存 Cookie/切换账号任务，以及"角色代码"页（含工坊）。

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

## 更新被官方覆盖后怎么恢复

ok-ww 自带更新会还原 `working` 和 `repo` 中的文件。两种恢复方式：

- **直接覆盖**（同版本文件被还原）：关闭 ok-ww 后双击 `一键恢复.bat`，或命令行 `python restore.py`。恢复前会自动备份当前文件。
- **重新打补丁**（大版本升级后结构变化）：按上面"安装"步骤运行 `install_to_local_app.py`。

两种都不会动账号 Cookie 和任务配置。详见 [`docs/backup-and-restore.md`](docs/backup-and-restore.md)。

## 目录结构

```text
config.py                   patched 后的上游 config（任务/标签页注册）
src/                        新增与修改的 ok-ww 源码
ok/device/capture_methods/  patched 后的 ok-script 浏览器捕获模块
tools/                      安装、patch 与工坊缓存下载脚本
tests/                      新增/修改的单元测试
docs/                       多账号配置说明、备份恢复说明
workshop_cache/             工坊离线索引（teams.json + teams/*.json）
restore.py / 一键恢复.bat   官方更新覆盖后的一键恢复
LICENSE.txt                 AGPL-3.0 许可证原文
```

## 免责声明

本仓库为个人定制补丁，按"现状"提供，不保证与上游后续版本兼容。使用自动化脚本可能违反游戏服务条款，风险自负。
