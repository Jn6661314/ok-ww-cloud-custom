## 更新日志

按**日**汇总，完整改动明细见 [Releases](https://github.com/Jn6661314/ok-ww-cloud-custom/releases)（中英双语）。

### 2026-11-25

- **[v1.6.0](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.6.0)** — **以官方 v3.8.15 为基线重建**：官方已原生支持云鸣潮，`DailyTask` 只注册一次并按所选设备自动区分操作，因此删除我们自建的「云每日 / 云多账号 / 保存 Cookie / 切换账号」四个任务（旧配置里的任务名仍可被读取）。UID 遮罩改走框架通用 `blur_area`（与 WebRTC 视频流捕获兼容，设置里可选 Blur / Inpaint），框架侧不再有任何游戏专用注入；多账号任务内新增「保存登录状态」「切换账号」两个按钮，**仅云设备下显示**；拉海洛方块按官方新版部署并保留 4 块托盘搜索预算修复。MuMu / 安卓定制整支保留在 `legacy-mumu-v1.5.21` 分支，本版不包含。
- **[v1.5.21](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.21)** — 云游戏 UID 遮罩兼容 WebRTC 捕获（视频流帧不经过页面合成，DOM 覆盖层会失效，改为在取帧路径涂黑）。
- **[v1.5.1](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.1)** — 修复全新安装装不全导致的启动失败：首装脚本与恢复脚本改为共用同一份文件清单。

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

一句话概览：**官方 v3.8.15 之上的云游戏多账号定制 + 历史功能回归**。

> 本仓库从 v1.6.0 起**以官方 v3.8.15 为基线**：官方已原生支持云鸣潮，并且日常任务只注册一次、
> 按所选设备自动区分 PC / 云鸣潮操作。因此这里只保留官方尚未具备的那部分定制。

- 云鸣潮启动支持；每个账号独立浏览器 Cookie profile，互不串号（目录整体换入换出，不改底层框架）
- **多账号任务内的「保存登录状态」「切换账号」按钮**：只在设备选「云游戏」时出现，PC / 安卓下不显示也不注册
- 云游戏后台运行，无需鼠标点击浏览器窗口（后台输入伪装）
- 任务出错自动恢复：优先重启浏览器并重跑，失败再回退刷新页面
- 进入游戏分级冷却，解决"要点两次开始游戏"；进入完成检测；邮箱奖励误判月卡的死循环修复
- 拉海洛方块云游戏浏览器模式适配；先约电台唤起修复；每日活跃度多区域重试识别
- **云鸣潮 UID 遮罩走框架通用 `blur_area`**：右下角 13%×2.5% 区域模糊/图案覆盖，截图与实时窗口一致，
  设置里「Enable Blur」可选 Blur / Inpaint；框架侧零游戏专用注入，与 WebRTC 视频流捕获兼容
- **拉海洛方块搜索预算兜底**：任意托盘大小都做束裁剪 + 3 秒墙钟上限，4 块托盘的无尽模式不再卡死
- 多账号配置持久化修复（排队/重启后保存不丢失、配置文件损坏自动回退备份）
- 从上游历史恢复 **角色代码（编队自定义轴）** 页面与 **队伍创意工坊**（含离线快照）
- "刷梦魇巢穴 / 4C"由配置复选框自行决定（默认开启），不再强制关闭
- 相关**上游 PR**：[ok-wuthering-waves #1873](https://github.com/ok-oldking/ok-wuthering-waves/pull/1873)（云鸣潮多账号，已被官方 v3.8.15 的原生实现取代）、[ok-script #130](https://github.com/ok-oldking/ok-script/pull/130)（UID 遮罩，已按维护者建议改为走框架 `blur_area`，见 v1.6.0）、[ok-script #131](https://github.com/ok-oldking/ok-script/pull/131)（账号 profile / 登录态 / 后台输入）

详细的逐项更新说明见 [`CHANGES.md`](CHANGES.md)。

## 与官方 v3.8.15 的差异

| 能力 | 官方 v3.8.15 | 本仓库 v1.6.0 |
| --- | --- | --- |
| 云鸣潮设备入口 / 启动 / 掉线重连 | ✅ 原生 | 沿用官方 |
| 日常任务注册次数 | ✅ 单个 `DailyTask`，按所选设备自动区分操作 | 沿用官方（已删除我们自建的「云每日」） |
| 多账号任务 | ✅ `MultiAccountDailyTask`（每账号独立配置） | 官方基础上加「保存登录状态」「切换账号」两个按钮，**仅云设备显示** |
| UID 遮罩 | ✅ `config.blur_area` + 设置里的 Enable Blur | 补上遮挡区域 `Box(w*0.870, h*0.975, w*0.130, h*0.025)`，走框架同一机制 |
| 账号登录态隔离 | ❌ Playwright 固定用 `cache/playwright`，多账号会互相顶号 | ✅ 按账号把 profile 目录整体换入换出（纯 ok-ww 侧，不改框架） |
| 云游戏后台输入 | ❌ 需要框架支持 | ✅ 框架侧补丁 `browser.py`（= ok-script PR #131） |
| 每日活跃度识别 | 单一区域读取，失败按 0 处理 | 多区域重试，读不到时不再误判"已完成"或"该刷体力" |
| 拉海洛方块 | 常规关卡（按难度逐个通关） | 官方版本 + 走棋搜索预算兜底（4 块托盘不再卡死） |
| 角色代码（编队自定义轴）/ 队伍工坊 | ❌ 上游已删除 | ✅ 从上游历史恢复，含工坊离线快照 |
| 多账号配置持久化 | 基础实现 | 排队/重启不丢、配置文件损坏自动回退备份 |

**旧版有、本版没有的能力**（官方 v3.8.15 的拉海洛方块不含这些，我们按"以官方为准"没有合并回来；
需要的话可以从 `legacy-mumu-v1.5.21` 分支取，或让我在官方代码上重新实现）：

- 无尽模式（无难度选项页面直接开始 / 加入进行中的对局 / 达到目标分数自动结算）
- 开局玩法说明弹窗自动关闭、通关后退回活动主页自动点「立即前往」
- 「故障方块 / 爆炸方块」机制识别

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

   脚本会把**全部 15 个**定制文件复制到 `working` 与 `repo` 两处，结束时打印
   `Done: 15 file copies across 2 directories.` —— 确认这一行出现，说明装齐了。

5. 打开 ok-ww，做三项确认：
   - 设备下拉选「云游戏」后，任务列表里**仍然只有一个日常任务 + 一个多账号任务**
     （官方 v3.8.15 起按所选设备自动区分操作，不会出现「云每日」「云多账号」这类重复任务）；
     多账号任务的设置页在云设备下会多出「保存登录状态」「切换账号」两个按钮。
   - 设置里能看到「Enable Blur」，勾选后云游戏右下角 UID 被模糊/图案覆盖（可选 Blur / Inpaint）。
   - 「角色代码」页（含工坊）存在。

> **基线版本**：本补丁以官方 **v3.8.15**（ok-script 3.0.14）为基线。如果你的官方 ok-ww
> 还是 v3.8.14 或更早，请先把官方更新到 v3.8.15 再打补丁，否则会出现文件对不上。

## 关于 MuMu / 安卓模拟器

**本分支（v1.6.0 起）不包含 MuMu / 安卓模拟器定制**，只做云鸣潮（浏览器）适配——这样
ok-ww 侧的改动才能干净地向上游提 PR。此前完整的 MuMu 定制（ADB 设备入口、MuMu IPC 抓屏、
触屏操作层、手游战斗/切人修复等）完整保留在仓库的 **`legacy-mumu-v1.5.21`** 分支：

```bash
git clone https://github.com/Jn6661314/ok-ww-cloud-custom
cd ok-ww-cloud-custom
git checkout legacy-mumu-v1.5.21
python tools/install_to_local_app.py
```

需要安卓模拟器的用户请用上面这支分支；两支分支的账号 Cookie 与多账号配置格式互相兼容。

## 更新被官方覆盖后怎么恢复

ok-ww 自带更新会还原 `working` 和 `repo` 中的文件。两种恢复方式：

- **直接覆盖**（同版本文件被还原）：关闭 ok-ww 后双击 `一键恢复.bat`，或命令行 `python restore.py`。恢复前会自动备份当前文件。
- **重新打补丁**（大版本升级后结构变化）：按上面"安装"步骤运行 `install_to_local_app.py`。

两种都不会动账号 Cookie 和任务配置。详见 [`docs/backup-and-restore.md`](docs/backup-and-restore.md)。

## 目录结构

```text
config.py                   patched 后的上游 config（任务/标签页注册、blur_area 遮罩区域）
src/                        新增与修改的 ok-ww 源码
  task/MultiAccountDailyTask.py  官方多账号任务 + 云端「保存登录状态/切换账号」按钮（仅云设备显示）
  task/DailyTask.py              每日任务云端适配（活跃度多区域重试、约电台不按 Alt）
  task/RahaiBlocksTask.py        拉海洛方块（官方 v3.8.15 版本）
  task/rahai_blocks.py           走棋算法（官方版本 + 束裁剪与 3 秒墙钟预算）
  cloud_browser.py               按账号切换 Playwright profile 目录（纯 ok-ww 侧，不改框架）
  cloud_recovery.py              云端错误自恢复（重启浏览器 → 刷新页面 → 放弃）
  task/account/                  多账号配置存储（持久化、损坏回退备份）
  task/NightmareNestTask.py      梦魇/残象聚落传送（"快速旅行"按钮 OCR 识别 + 确认按钮兜底）
  char/、gui/                    角色代码（编队自定义轴）与队伍工坊
ok/device/capture_methods/
  browser.py               框架侧补丁：后台输入伪装 + CDP 调用 15 秒超时（对应 ok-script PR #131）
                           —— 官方合入后即可删除，ok-ww 侧的 PR 不需要它
tools/                      安装、patch、工坊缓存下载与 Release 发布脚本
  publish_release.py         把 releases/*.md 发布成 GitHub Release（自动打 tag）
releases/                   各版本的完整改动明细（中英双语，发布脚本的正文来源）
tests/                      新增/修改的单元测试（143 项）
docs/                       多账号配置说明、备份恢复说明
workshop_cache/             工坊离线索引（teams.json + teams/*.json）
restore.py / 一键恢复.bat   官方更新覆盖后的一键恢复
LICENSE.txt                 AGPL-3.0 许可证原文
```

---

## 免责声明

本仓库为个人定制补丁，按"现状"提供，不保证与上游后续版本兼容。使用自动化脚本可能违反游戏服务条款，风险自负。
