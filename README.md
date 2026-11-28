## 让 Agent 帮你安装：先选对版本

有两套安装提示词，按你的**设备形态**选，不要混装：

| 你的场景 | 提示词 | 安装内容 |
| --- | --- | --- |
| 云鸣潮 / 多账号日常 / MuMu 模拟器 / **手机投屏(NectarLink) 真机** / 远控窗口（UU远程、ToDesk、向日葵、Parsec）/ 单机 PC | [`AGENT_INSTALL_PROMPT.md`](AGENT_INSTALL_PROMPT.md) | 本仓库的 Python 定制补丁（装进现有 ok-ww 的 `working`/`repo`） |
| 双机：游戏机 + 控制机，采集卡取画面，KMBox Net 键鼠盒或 SendInput 输入，DXGI 远程 | [`AGENT_INSTALL_DUALPC.md`](AGENT_INSTALL_DUALPC.md) | 独立项目 [okww-dualpc](https://github.com/xueyuannnn/okww-dualpc) 的官方包（独立目录，Rust 内核 + Qt 界面） |

把对应文件里 `text` 代码块中的整段内容复制给 Agent（WorkBuddy / Claude / Cursor 等），它会自动完成安装与验证；
提示词里已写明"不覆盖 Cookie / 账号配置 / 自定义队伍"以及"两套安装互不干扰"的约束。

**为什么不把双机做成同款补丁**：okww-dualpc 是另一套完整实现（41 个 Python 适配文件约 6600 行 +
Rust 业务内核 + Qt 界面，基线为 ok-ww-enhanced 与老版 ok-script），设备层还会把
`device_dict` 覆写成唯一双机设备、关闭 browser/adb/windows —— 与本仓库的云鸣潮/MuMu/远控窗口
天然互斥。做两套独立安装、各自独立目录，比强行合并更稳，也便于分别升级。

## 更新日志

完整逐版明细见 [`CHANGES.md`](CHANGES.md)，发布正文见 [Releases](https://github.com/Jn6661314/ok-ww-cloud-custom/releases)（中英双语）。

| 版本 | 摘要 |
| --- | --- |
| [v1.8.28](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.28) | 配对不再误复用残留内核、补回 `child_session` 方法、云游戏默认分辨率改 1600×900（Win10 闪退）；精简本文档与安装提示词 |
| [v1.8.27](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.27) | 基线升到官方 v3.8.18 + 修掉上游评审的 7 个问题 + 首个「解压即用」绿色成品包 |
| [v1.8.26](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.26) | 手机投屏按键变可校准触点 + 电脑上实时显示手机画面 |
| [v1.8.25](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.25) | 修投屏「连上但启动不了」（抓屏通道连接晚几十毫秒） |
| [v1.8.24](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.24) | 修投屏连不上（手机端关掉了这台电脑的自动重连） |
| 更早版本 | 见 [`CHANGES.md`](CHANGES.md) |

# ok-wuthering-waves 云鸣潮定制补丁

> 非官方第三方定制补丁集，仅包含相对于上游项目新增/修改的文件，**不是**完整程序。
> 使用前请先安装官方原版 ok-wuthering-waves。
>
> **不想折腾？** 从 [Releases](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/latest)
> 下载 `ok-ww-custom-vX.Y.Z-full.7z`（绿色包，含 Python 环境与官方 v3.8.18 全部文件），
> 解压到任意文件夹后双击 `ok-ww.exe` 即可：不用装 Python、不用跑 `restore.py`、不用 AI、
> 也不用安装或写注册表。包里是**自建的轻量启动器**（不碰 git），不会像官方启动器那样
> 一启动就把定制补丁还原掉。
> 成品包不含任何人的配置、账号、Cookie、云存档与日志。

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

一句话概览：**官方 v3.8.18 之上的云游戏多账号 + MuMu/安卓模拟器定制 + 历史功能回归**。

> 本仓库从 v1.6.0 起**以官方 v3.8.15 为基线**（v1.8.27 起升到 **v3.8.18**）：官方已原生支持云鸣潮，并且日常任务只注册一次、
> 按所选设备自动区分 PC / 云鸣潮操作。因此这里只保留官方尚未具备的那部分定制。

- 云鸣潮启动支持；每个账号独立浏览器 Cookie profile，互不串号（目录整体换入换出，不改底层框架）
- **MuMu / 安卓模拟器支持**：设备下拉自动出现模拟器；抓屏默认 MuMu IPC（全黑帧检测 + 自动重连），
  输入走「ADB + 真实键盘事件叠加」由模拟器键位映射转发；返回/菜单统一为键位表的 ` 键，
  指南书/活动面板改为点右上角图标（取代 F1/F2）；掉线弹窗自动确认并重登
- **MuMu 编队锁定**：全局配置可手填「MuMu 编队」（编队为准，零画面识别）；不填则按缩放模板识别 +
  连续一致投票锁定，战斗期间不做任何队伍 OCR，切人键只在 1/2 两颗键里动态推导
- **多账号任务内的「保存登录状态」「切换账号」按钮**：只在设备选「云游戏」时出现，PC / 安卓下不显示也不注册
- 云游戏后台运行，无需鼠标点击浏览器窗口（后台输入伪装）
- 任务出错自动恢复：优先重启浏览器并重跑，失败再回退刷新页面
- 进入游戏分级冷却，解决"要点两次开始游戏"；进入完成检测；邮箱奖励误判月卡的死循环修复
- **拉海洛方块**：官方 v3.8.18 版本之上重新实现无尽模式（无尽页直启 / 加入进行中的对局 /
  达到目标分数自动退出结算）、关卡详情页直接开始、玩法说明弹窗自动关闭、
  通关退回活动主页自动点「立即前往」；云鸣潮（浏览器虚拟输入，无需窗口在前台）与
  MuMu/安卓模拟器（模拟器窗口键鼠 + 返回键兜底）都可用
- 先约电台唤起修复；每日活跃度多区域重试识别
- **云鸣潮 UID 遮罩 = 官方功能，不是本仓库新增**：官方 `config.blur_area` + 设置里「Enable Blur」
  （Blur / Inpaint）早已覆盖右下角 UID，保存的截图与实时窗口走同一套逻辑，与 WebRTC 视频流捕获兼容。
  本仓库只把遮挡区域调大了一点（见下表），**没有**游戏专用注入，也没有需要上游合并的补丁
- **拉海洛方块搜索预算兜底**：任意托盘大小都做束裁剪 + 3 秒墙钟上限，4 块托盘的无尽模式不再卡死
- **远控 / 串流软件窗口当设备（试验性）**：UU远程、ToDesk、向日葵、Parsec、Moonlight 这类软件
  把被控电脑的画面显示成本机的一个窗口，所以抓这个窗口 + 往里发真实键鼠事件就等于在操作被控电脑上的游戏。
  打开左侧导航栏「游戏」分组最下面的「远控串流窗口(试验性)」页，填窗口标题关键字即可，
  启动时会校验 16:9、并禁用自动 resize
  （详见[下文](#远控--串流软件试验性)的硬性要求）
- 多账号配置持久化修复（排队/重启后保存不丢失、配置文件损坏自动回退备份）
- 从上游历史恢复 **角色代码（编队自定义轴）** 页面与 **队伍创意工坊**（含离线快照）
- "刷梦魇巢穴 / 4C"由配置复选框自行决定（默认开启），不再强制关闭
- 相关**上游 PR**：[ok-wuthering-waves #1873](https://github.com/ok-oldking/ok-wuthering-waves/pull/1873)（云鸣潮多账号，已被官方 v3.8.15 的原生实现取代）、[ok-script #130](https://github.com/ok-oldking/ok-script/pull/130)（UID 遮罩：维护者建议改走框架 `blur_area`，而该能力官方 ok-ww 一早就有，故关闭后不再另提）、[ok-script #131](https://github.com/ok-oldking/ok-script/pull/131)（账号 profile / 登录态 / 后台输入）

详细的逐项更新说明见 [`CHANGES.md`](CHANGES.md)。

## 与官方 v3.8.18 的差异

| 能力 | 官方 v3.8.18 | 本仓库 v1.8.28 |
| --- | --- | --- |
| 云鸣潮设备入口 / 启动 / 掉线重连 | ✅ 原生 | 沿用官方 |
| 日常任务注册次数 | ✅ 单个 `DailyTask`，按所选设备自动区分操作 | 沿用官方（已删除我们自建的「云每日」） |
| 多账号任务 | ✅ `MultiAccountDailyTask`（每账号独立配置） | 官方基础上加「保存登录状态」「切换账号」两个按钮，**仅云设备显示** |
| UID 遮罩（防截图泄露账号） | ✅ 官方早已实现：`config.blur_area` + 设置里的 Enable Blur，保存截图与实时窗口都覆盖 | 机制完全沿用官方，**仅遮挡区域略大**：`Box(w*0.870, h*0.975, w*0.130, h*0.025)`（官方为 `0.879 / 0.976`），非本仓库新增能力 |
| 账号登录态隔离 | ❌ Playwright 固定用 `cache/playwright`，多账号会互相顶号 | ✅ 按账号把 profile 目录整体换入换出（纯 ok-ww 侧，不改框架） |
| 云游戏后台输入 | ❌ 需要框架支持 | ✅ 框架侧补丁 `browser.py`（= ok-script PR #131） |
| 每日活跃度识别 | 单一区域读取，失败按 0 处理 | 多区域重试，读不到时不再误判"已完成"或"该刷体力" |
| 拉海洛方块 | 常规关卡（按难度逐个通关）；**要求 PC 窗口在前台，云鸣潮下不可用** | 官方版本 + 无尽模式（直启/加入对局/达标结算）+ 详情页直接开始 + 玩法弹窗关闭 + 通关退回主页自动「立即前往」+ 云鸣潮（浏览器输入）支持 + 走棋搜索预算兜底 |
| 角色代码（编队自定义轴）/ 队伍工坊 | ❌ 上游已删除 | ✅ 从上游历史恢复，含工坊离线快照 |
| MuMu / 安卓模拟器 | ❌ 只能自己配 adb，无键位/编队/掉线处理 | ✅ 设备自动出现、IPC 抓屏、键位映射转发、编队锁定、掉线重登 |
| 拉海洛方块（安卓） | ❌ 要 PC 窗口在前台，安卓下无法运行 | ✅ 模拟器窗口输入 + 返回键兜底 |
| 远控 / 串流软件窗口（UU远程、ToDesk、向日葵、Parsec） | ❌ 只认 `Client-Win64-Shipping.exe` + `UnrealWindow`，远控窗口不会出现在设备列表 | ✅ **试验性**：设置里填窗口标题关键字即可把远控窗口当 PC 设备（windows 抓屏 + Pynput 真实键鼠），启动时校验 16:9 并禁用自动 resize |
| 多账号配置持久化 | 基础实现 | 排队/重启不丢、配置文件损坏自动回退备份 |

**仍然没有合并回来的能力**（唯一一项）：

- 「故障方块 / 爆炸方块」机制识别（需要连 `rahai_blocks.py` 的 fault 位运算一起改）。

MuMu / 安卓定制、无尽模式、详情页直接开始、玩法说明弹窗、通关退回主页的「立即前往」
**都已合并在本版中**，不再是丢失项。

## 隐私说明

- 本仓库**不包含任何账号、密码、手机号、Cookie、浏览器登录态或 `cloud_profiles` 数据**，源码中出现的账号/邮箱均为虚构占位示例。
- 本仓库**不包含** `configs/MultiAccountConfig.json`、`MultiAccountResults.json`、`devices.json` 等运行时配置。
- 安装/恢复脚本只覆盖定制源码文件，**不会**改动你的 Cookie 或任务配置。
- 工坊快照只包含社区公开分享的队伍代码，不含任何个人登录信息。

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

   脚本会把 `restore.py::RELATIVE_FILES` 里的**全部定制文件**（当前 46 个）复制到 `working` 与
   `repo` 两处，结束时打印 `Done: N file copies across 2 directories.`（N = 文件数 × 2，当前应为 92）
   —— 确认这一行出现，说明装齐了；数字随清单变化属正常，以脚本实际输出为准。

5. 打开 ok-ww，做三项确认：
   - 设备下拉选「云游戏」后，任务列表里**仍然只有一个日常任务 + 一个多账号任务**
     （官方 v3.8.15 起按所选设备自动区分操作，不会出现「云每日」「云多账号」这类重复任务）；
     多账号任务的设置页在云设备下会多出「保存登录状态」「切换账号」两个按钮。
   - 设置里能看到「Enable Blur」（官方自带，默认开启），勾选后云游戏右下角 UID 被模糊/图案覆盖（可选 Blur / Inpaint）。
   - 「角色代码」页（含工坊）存在。

> **基线版本**：本补丁以官方 **v3.8.18** 为基线。如果你的官方 ok-ww 还是 v3.8.17 或更早，
> 请先把官方更新到 v3.8.18 再打补丁（或直接用 Release 里的成品包，它已经把版本对齐好了），
> 否则会出现文件对不上。

## MuMu / 安卓模拟器

从 **v1.7.0** 起 MuMu / 安卓模拟器支持重新合并回主线（与云鸣潮、PC 并存，用同一个任务）。

### 1. 让模拟器出现在设备列表

先在 MuMu 里启动鸣潮，然后打开 ok-ww 的设备下拉——ADB 设备会被自动扫描出来。
模拟器**不用**手动填 adb 端口（`config.py` 里已声明包名与默认抓屏方式）：

```python
'adb': {
    'packages': ['com.kurogame.mingchao', 'com.kurogame.wutheringwaves'],
    'capture_method': 'ipc',   # MuMu IPC 抓屏; 非 MuMu 模拟器自动回退到 adb 抓屏
},
```

### 2. 抓屏

| 抓屏方式 | 说明 |
| --- | --- |
| **Nemu IPC**（默认） | 最快，支持长按重击。返回全黑帧时会自动重建 IPC 连接，不会把加载黑屏当成故障；连续 30 秒全黑才报错并提示检查「后台保活」/窗口是否被最小化 |
| ADB 抓屏 | 非 MuMu 模拟器（雷电等）或想强制走 adb 时使用，速度慢一些 |
| 窗口抓屏（WGC） | 想按 PC 方式驱动模拟器窗口时可选；Win10 2004+ 也可用（去掉了黄色边框） |

### 3. 输入与键位

- 模拟器是 Windows 窗口，但**手游不认 `input keyevent`**：技能/切人键发出去没有任何反应。
  所以 `send_key` 会在 ADB 键位之外**叠加一次真实键盘事件**，由 MuMu 自己的键位映射转成触屏操作。
- 返回 / 打开菜单统一映射为键位表里的 **` 键**（`esc` 会变成安卓返回键，甚至弹出"退出游戏"）。
- 键位表补全了 `F1-F12`、`A-Z`、`0-9`、反引号，避免出现非法的 `input keyevent f`。
- 索拉指南（PC 的 F2）与活动面板（PC 的 F1）改为**直接点右上角对应图标**；书是否已打开用
  笔画掩码 + 多尺度 IoU 判定，不会来回点开关。

### 4. 编队（重要）

手游队伍栏是**圆形头像**（约 1.7 倍大），PC 头像模板直接匹配会抖动，导致"该切奶妈却切主C"。

- 推荐：在左侧导航栏「游戏」分组 → **MuMu 安卓 Config** → `MuMu 编队` 里按槽位顺序手填角色名，
  如 `绯雪,漂泊者·衍射,渊武` 或 `Hiyuki,Rover: Spectro,Yuanwu`。填了就以编队为准，**完全不做画面识别**。
- 不填：把队伍栏缩放到 PC 尺度后识别，连续 3 次一致才锁定；战斗期间不再识别，
  非战斗时每 15 秒复检一次，换队后自动重锁。
- 切人键只会在 `1` / `2` 两颗键里推导（MuMu 只绑了两颗），绝不会发 `3`。

### 5. 掉线与异常

- 「连接已断开」弹窗：先用亮度预筛定位中央弹窗，再 OCR 确认文案，点「确认」后重新登录。
- 短时间内反复掉线会提示一次排查建议（关闭 MuMu 后台省电/限帧、别最小化到托盘、
  管理员运行 `networkReset.bat`、换 DNS）。
- 模拟器刚开机时游戏不会自动运行：设备就绪后会自动用 adb 拉起鸣潮（20 秒冷却，不会反复拉）。

### 6. 只想要 MuMu（不要云游戏）？

用 `legacy-mumu-v1.5.21` 分支仍是官方 v3.8.14 + 纯 MuMu 定制；本分支（main）则同时包含
云鸣潮与 MuMu，两者配置与 Cookie 格式互相兼容，可以直接切。

## 远控 / 串流软件（试验性）

UU远程、ToDesk、向日葵、Parsec、Moonlight 这类软件，本质是把**被控电脑的画面显示成本机的一个窗口**，
再把本机的键鼠事件转发过去。所以「抓这个窗口 + 往里发真实键鼠事件」就等于在操作被控电脑上的游戏，
不需要任何"远程"专用逻辑 —— 走的就是 PC 客户端同一条 windows 抓屏 + Pynput 链路。

### 怎么开

> **它在哪**：左侧导航栏 **「游戏」分组最下面**（图标是显示器），**不在「设置」页里**。
> 这类 `show_at_tab` 配置项会被设置页主动跳过，只作为独立页出现；侧边栏需要往下滚一点。

1. 左侧导航栏「游戏」分组 → **远控串流窗口(试验性)** → 勾选 `Enable`；
2. `Preset` 直接选软件即可，不用手填正则：
   - **Moonlight**：匹配串流窗口「`<主机名> - Moonlight`」（上游源码 `session.cpp` 生成的标题），**不会误抓 Moonlight 主界面**；
   - UU远程 / ToDesk / 向日葵 / Parsec：对应各自窗口标题/类名；
   - 需要多个或特殊窗口时，`Preset` 选 `Manual`，在 `Window Title` 填标题关键字（正则，忽略大小写），例如 `UU远程`、`ToDesk`、`SunloginClient`、`Parsec` 或 `UU远程|ToDesk|Parsec`；
   - `Preset` 与 `Window Title` 同时填时两者都会匹配。
3. 保存并**重启 ok-ww**（配置在启动时读取一次）；
4. 设备下拉里会只剩一个条目，名字就是远控窗口的标题，选中它照常跑「每日任务」。

> 开启后**鸣潮 PC 客户端不再出现在设备列表**里（同一时间只驱动一个窗口）。想换回本地客户端就把
> `Enable` 取消勾选再重启。`Force Pynput` 保持勾选 —— 远控软件基本不处理窗口消息（PostMessage
> 打到它窗口上不会转发），只有真实键鼠事件才会被转发。

### 硬性要求（不满足就会坐标偏移 / 识图失败）

| 项目 | 要求 |
| --- | --- |
| 被控电脑 · 游戏 | **必须全屏运行**（独占全屏或窗口化全屏都行），不要留在窗口模式 |
| 被控电脑 · 分辨率 | **16:9**，且是 ok-ww 支持的档位之一：`1920x1080` / `2560x1440` / `1600x900` / `1280x720` |
| 远控软件 · 画质 | 选「原画 / 原始分辨率」，**不要**用「自适应」「缩放填充」「智能降分辨率」 |
| 本机 · 窗口尺寸 | 远控窗口的**客户区**必须是 16:9，且画面铺满；出现黑边就会被裁切或整体偏移 |
| 本机 · 前台 | 远控窗口必须**在前台**、不能被遮挡、不能最小化（Pynput 会检查前台，否则点击直接跳过） |
| 权限 | ok-ww 必须**以管理员身份运行**（Pynput 注入系统键鼠事件需要） |
| 鼠标模式 | 远控端鼠标选**绝对定位 / 直接控制**；如果用了「锁定鼠标 / 相对移动」，点击会整体偏移 |

补充说明：

- 程序**不会**去调整远控窗口大小（`try_resize_to` 已按实例禁用），所以窗口比例要你自己拉对，
  否则只会弹告警而不会自动 "修好"；
- 启动时会检查一次客户区比例，非 16:9 会在日志和通知里给出实际尺寸和修正建议，但**不会阻断**运行
  （试验性，允许你先跑起来看看）；
- 远控软件有压缩和延迟，识图阈值比本地 PC 更脆；如果频繁认不出界面，优先提高画质而不是调阈值；
- 同一台被控电脑上，游戏内分辨率改了之后，本机窗口也要重新拉成对应比例。

### 已知限制

- 远控窗口开晚了（先点开始、后开窗口）不会立刻生效：设备列表里没有条目，等窗口出现后刷新即可；
- 只支持一个远控窗口；多窗口/多开请用多账号任务而不是多个设备；
- 手柄映射、云游戏浏览器（`browser` 设备）与远控窗口不能同时启用。

## 更新被官方覆盖后怎么恢复

ok-ww 自带更新会还原 `working` 和 `repo` 中的文件。两种恢复方式：

- **直接覆盖**（同版本文件被还原）：关闭 ok-ww 后双击 `一键恢复.bat`，或命令行 `python restore.py`。恢复前会自动备份当前文件。
- **重新打补丁**（大版本升级后结构变化）：按上面"安装"步骤运行 `install_to_local_app.py`。

两种都不会动账号 Cookie 和任务配置。详见 [`docs/backup-and-restore.md`](docs/backup-and-restore.md)。

### 启动器什么时候会刷掉定制（v1.8.3 / v1.8.4 实测边界）

启动器（pyappify）正常启动/自检时：读 `app.json` 的 `current_version`（如 `v3.8.18`）→
在 `repo` 里找**同名 git tag** → `git checkout -f <tag>`。`-f` 会丢弃工作区里所有未提交改动，
所以：

- 只把定制写成文件（不提交）→ 一次启动就没了；
- 只把定制**提交**成 HEAD（v1.8.2 的做法）→ tag 还指向官方提交，`checkout -f` 照样切回官方；
- 把**版本 tag 本身**指到定制提交（v1.8.3 的做法）→ 正常路径下 checkout 切出来的就是定制树。

`restore.py` 每次部署会依次做：写文件 → 提交进 git（`local-custom-baseline`）→ 把 `v<版本号>` tag
钉到该提交（原官方指向备份成 `official-v<版本号>`）→ 自检。

**但 v1.8.4 补上了另一半真相**：如果 ok-ww 启动过程抛异常（启动崩溃），启动器会判定"安装损坏"，
**绕开 git 直接从官方文件整份重装** `working`/`repo`。2026-11-25 23:56 就是这样：reflog 里那条
`checkout: moving from 9d33201 to 9d33201` 的目标明明是我们的定制提交，事后 `HEAD` 却是官方
`567f025`、`config.py` 回到 13380 字节。tag 钉得再准也拦不住这条路径。

所以两道防线，优先级从高到低：

1. **代码必须能正常启动** —— 这是最强的保护（v1.8.4 修的就是启动崩溃）；
2. 正常启动时靠「提交 + 钉 tag」防止被校验还原。

想临时回官方基线：`git -C "$env:LOCALAPPDATA/ok-ww/data/apps/ok-ww/repo" checkout official-v3.8.18`。

> 仍会覆盖的情况：官方发新版本后在更新卡片点「安装」；或启动崩溃触发自动修复。
> 真发生了就重跑 `python restore.py`，它会重新提交并重新钉 tag，账号与任务配置不动。

## 目录结构

```text
config.py                   patched 后的上游 config（任务/标签页注册、blur_area 遮罩区域）
src/                        新增与修改的 ok-ww 源码
  task/MultiAccountDailyTask.py  官方多账号任务 + 云端「保存登录状态/切换账号」按钮（仅云设备显示）
  task/DailyTask.py              每日任务云端适配（活跃度多区域重试、约电台不按 Alt）
  task/RahaiBlocksTask.py        拉海洛方块（官方 v3.8.18 + 无尽模式/详情页直启 + 云/MuMu 输入分流）
  task/rahai_blocks.py           走棋算法（官方版本 + 束裁剪与 3 秒墙钟预算）
  task/multi_touch.py            MuMu 双指触控（ADB sendevent ABS_MT_SLOT：一指点旋转按钮 + 一指拖方块）
  cloud_browser.py               按账号切换 Playwright profile 目录（纯 ok-ww 侧，不改框架）
  cloud_recovery.py              云端错误自恢复（重启浏览器 → 刷新页面 → 放弃）
  stream_window.py               远控串流窗口(试验性)：读取配置并把窗口切成当前设备
  globals.py                     官方 Globals + 启动时挂载远控/串流窗口（改完需重启生效）
  task/account/                  多账号配置存储（持久化、损坏回退备份）
  task/NightmareNestTask.py      梦魇/残象聚落传送（"快速旅行"按钮 OCR 识别 + 确认按钮兜底）
  task/BaseWWTask.py             触屏语义层（返回/菜单=`) + 安卓大世界判定 + 断线弹窗 + 真实键叠加
  task/BaseCombatTask.py         编队锁定、1/2 切人键推导、安卓协奏环框、角色空值兜底
  combat/CombatCheck.py          安卓锁敌(Y)、谐振破坏 OCR、无血条耐心重锁定
  task/AutoCombatTask.py         触发任务不被单帧异常关闭
  task/MouseResetTask.py         无 get_abs_cords 的抓屏(安卓)跳过鼠标复位
  task/touch_mode.py             触屏语义操作（返回/指南书/活动）
  task/android_world.py          安卓大世界判定（雷达箭头/血条/加载条/断线弹窗）
  task/android_book.py           安卓索拉指南左列类别图标定位（笔画 IoU）
  task/AndroidDailyTask.py       可选：显式校验安卓设备的每日任务入口（默认不注册）
  char/、gui/                    角色代码（编队自定义轴）与队伍工坊
ok/device/
  DeviceManager.py         框架侧：adb 拉起游戏、MuMu 网桥回退、模拟器窗口交互覆盖、远控/串流窗口模式
  capture_methods/nemu_ipc.py       MuMu IPC 全黑帧检测 + 连接自恢复
  capture_methods/windows_graphics.py  WGC 在 Win10 2004+ 可用、去黄色边框
  capture_methods/browser.py        后台输入伪装 + CDP 调用 15 秒超时（对应 ok-script PR #131）
  interaction_methods/keys.py       ADB 键位映射（esc→返回、F1-F12、A-Z、0-9、`）
ok/util/window.py          WGC 可用性判定不再被 Win11 门禁误伤
tools/                      安装、patch、工坊缓存下载与 Release 发布脚本
  publish_release.py         把 releases/*.md 发布成 GitHub Release（自动打 tag）
releases/                   各版本的完整改动明细（中英双语，发布脚本的正文来源）
tests/                      新增/修改的单元测试（236 项）
docs/                       多账号配置说明、备份恢复说明
workshop_cache/             工坊离线索引（teams.json + teams/*.json）
restore.py / 一键恢复.bat   官方更新覆盖后的一键恢复
LICENSE.txt                 AGPL-3.0 许可证原文
```

---

## 免责声明

本仓库为个人定制补丁，按"现状"提供，不保证与上游后续版本兼容。使用自动化脚本可能违反游戏服务条款，风险自负。
