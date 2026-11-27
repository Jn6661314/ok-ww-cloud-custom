# 更新日志

本文件按**日**汇总。每一版的完整改动明细（中英双语）见
[Releases](https://github.com/Jn6661314/ok-ww-cloud-custom/releases)。

所有条目均已在运行目录实际验证。

---

## 2026-11-27

| 版本 | 一句话摘要 |
| --- | --- |
| [v1.8.23](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.23) | **修好「手机投屏启动不了」（内核起来就自己退）**：单独跑内核复现，stderr 里的实话是 `device is offline`——而且是在节点启动后**仅 23ms** 就去请求投屏。根因是 `mirror_start` 要求会话已建立，而节点刚起来时后台还在拨号重连，握手根本没完成 → 必然失败（上游 NectarLink CLI 在同一件事上会先 `wait_until_online` 等设备上线，我们漏了这一步）。另发现**同时有 3 个 `nectarlink-sidecar.exe` 在跑**，用**同一个设备身份**、占 3 个 UDP 端口、mDNS 广播同一个 NodeId，手机拿到对不上的地址就判「离线」——所以即使加了等待，上一轮内核没退干净照样连不上。修复：内核新增 `wait_until_online()`（判据 `LinkState::Online`，每 300ms 查一次，默认最多等 120 秒，等待期间每 10 秒报一次进度，不让界面看着像卡死）+ 投屏请求失败自动重试（Offline/Network/Timeout 最多 5 次，手机刚同意时连接常要重建一次）+ `sidecar.json` 状态文件记录 pid；ok-ww 侧捕获内核 stderr 并过滤掉 tracing 的日常 INFO，把**真实原因**（如「设备离线」）显示出来，不再只有一句没头没尾的「还没就绪」；启动前清掉残留内核（读状态文件 + 按命令行扫同数据目录的进程）；`pid_alive()` 走 Windows API 而不是 `os.kill(pid, 0)`（**Windows 上后者会直接 TerminateProcess**，「试探进程还在不在」本身就会杀掉进程）；配对模式与普通模式自动切换（以前跑着普通内核时点「配对手机」一直等不到二维码）；配对码拿到前两个确认按钮禁用；内核日志关掉颜色码（颜色码把 ` INFO ` 拆成两半，导致噪声过滤失效）。Rust 8 项测试通过，Python 新增 16 项，全量 455 项通过。**需重跑 `restore.py` 并重启 ok-ww**（换了内核二进制） |
| [v1.8.22](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.22) | **修好配对二维码（之前根本出不来，手机也扫不动）**：v1.8.20 的内置投屏内核第一次真机使用就卡在配对——窗口能开、状态栏写着「等待手机扫码…」，二维码那块却是空白（日志显示内核正常，配对链接已拿到，问题在 ok-ww 画码这一段）。三个 bug 叠加：① 转 Qt 图像时 `bytesPerLine` 传了 `width` 而非 `width * 3`（BGR 每像素 3 字节），Qt 认为数据不足直接给**空图** → 界面白板；② 二维码被**反相**——OpenCV 编码器输出本就是标准白底黑码，反相后成黑底白码，手机扫码器不认（之前那条测试断言的恰是反相后的样子，把错误当成了标准）；③ 缺静区（标准要求四周 4 个模块宽）。现在不反相 + 补静区 + 缩放改 6 倍（真实链接 178 字符 → 61×61 模块 → 366 像素正好不裁切）+ bytesPerLine 修正，并加转换失败告警（不再默默显示白板）。另修内核往 stdout 写配对提示语（`print!` 无换行）会把后续 JSON 粘成一行、整条消息被吞（`paired` 致命：配对成功了 ok-ww 却不知道）→ 改写 stderr，stdout 保持纯 JSON；ok-ww 解析器也加容错（按大括号配平逐个抠 JSON）。端到端验证：拿内核真实发出的 178 字符链接走完「编码→加静区→缩放→转 Qt 位图→从位图读回→扫码」，扫出来与原文逐字符相同。新增 11 项测试，全量 437 项通过。**需重跑 `restore.py` 并重启 ok-ww**（换了内核二进制） |
| [v1.8.21](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.21) | **两个手机投屏菜单合成一个**：v1.8.19 的「手机投屏(NectarLink)」和 v1.8.20 的「手机投屏(内置引擎)」并排挂着且功能重叠（旧菜单只有一个下载入口，新菜单已包住），现在合成一个「手机投屏」，用「模式」下拉切换内置引擎／桌面端；选桌面端时不用再去「远控串流窗口」菜单选 NectarLink 预设，本菜单直接切到投屏窗口并打 `phone_mirror` 标记（编队识别/切人按安卓端处理），「远控串流窗口」菜单本身不受影响。**配置自动迁移**：ConfigOption 的名字就是配置文件名，改名会让用户设置"消失"（改了配置却不生效），新增 `src/phone_mirror_config.py` 在启动最早期把旧两份配置合成 `手机投屏.json`，Enable/画面宽度/帧率/码率全部保留、模式按旧配置推断，且只在真正启动时执行（测试不动用户真实配置）。设备下拉条目改为「手机投屏」。新增 15 项测试，全量 426 项通过。**升级后不用改配置**，需重跑 `restore.py` 并重启 ok-ww |
| [v1.8.20](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.20) | **内置投屏引擎，把 NectarLink 桌面端装进 ok-ww**：新增内置投屏内核 `bin/nectarlink-sidecar.exe`（Rust，基于 nectarlink-core 的 MPL-2.0 无界面内核：自己跟手机配对、拉流，用 Windows 自带 Media Foundation 解 H.264，经本机 socket 把 NV12 画面推给 ok-ww），**不用再装 NectarLink 桌面端**；ok-ww 侧新增 socket 抓屏（裁黑边 + 归一化到模板原生 1080）与触点输入（点击/滑动/按键直接变成手机触点，不再走真实鼠标，窗口不用在前台）；新增全局配置「手机投屏(内置引擎)」与扫码配对窗口（二维码用 OpenCV 自带编码器，无额外依赖）；投屏模式 16:9 分辨率契约彻底放宽，不再报 resolution error、不再弹错误框；内核端口写 link.json 可跨次运行复用，少重启就少在手机上点「允许」。新增 5 项测试，全量 407 项通过 |

## 2026-11-26

| 版本 | 一句话摘要 |
| --- | --- |
| [v1.8.9](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.9) | **修掉云鸣潮「敌人没打完就莫名其妙停了」**：官方云游戏用锁定图标优先 + 血条辅助双判定，血条消失还有 3 秒宽限；我们定制为防无限续命加的 `no_enemy_for()` 却对所有端统一用 2 秒，**比官方宽限还短**，串流延迟/技能特效让图标和血条闪断 2~3 秒就被判脱战，退出战斗去走奖励，30 秒后官方才发现战斗还在又重打。现在云游戏端单独用 6 秒无敌人窗口（PC 2 / 安卓 4 不变，聚落任务仍用自己的锁敌超时），重锁时血条闪断忍耐从 1.2 秒放宽到 3 秒；判定仍以官方双信号为准。新增 10 项测试（旧代码 4 失败 + 1 错误），全量 287 项通过 |
| [v1.8.8](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.8) | **云鸣潮战斗奖励副本出错后现场续打，不再重进**：旧流程重启浏览器后 `ensure_main()` 看到 `in_realm()` 会按 Esc 退出副本，DailyTask 又从 F2 重进，白丢当前这场。新增 `src/reward_dungeon_recovery.py`：出错瞬间快照是否在副本，重启后先等云端画面回来、续打未结束的战斗、探测战斗是否结束、有「领取」F/宝箱就按 F 领奖，再从副本菜单正常退出；续打成功时跳过 `ensure_main` 与二次等待，剩余任务照常跑。不在副本/探测失败/会话已回首页都安全回退；可用任务配置 `Cloud Resume Reward Dungeon: false` 关闭。新增 13 项测试（旧代码 3 项挂），全量 277 项通过，定制文件 32→33 |
| [v1.8.7](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.7) | **残象聚落锁敌兜底 + Moonlight 远控预设**：双极等敌人飞出聚落时不再一路追出边界——5 秒锁不到就在原地重锁 2 次（CombatCheck 新增可配置 `target_enemy_retry_count/retry_timeout`，默认 0 不影响其他任务），仍失败则跳过当前聚落去下一个；真打死有 F 掉落时照常拾取。任务配置可调 `Lock Retry Timeout (s)` / `Lock Retries`。远控窗口配置新增 `Preset` 下拉，Moonlight 预设匹配串流窗口「`<主机名> - Moonlight`」（上游 `session.cpp` 的标题），避免误抓主界面，UU远程/ToDesk/向日葵/Parsec 也有预设且可与手填正则叠加。新增 15 项测试，全量 264 项通过；定制文件 31→32 |
| [v1.8.6](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.6) | **修复重启任务偶尔丢账号登录态**：错误恢复调用 `restart_browser()` 时没带账号，函数把 `None` 猜成 `default`，于是把当前账号 profile 存好后却装入磁盘上遗留的 `default` profile（`active_account` 也被改写成 default）。新增 `resolve_account()`（live profile marker 优先，其次 `cloud_browser.json`），错误恢复显式传账号；`_replace_dir()` 改带退避重试 + 失败回滚，不再在 Chromium 锁文件时静默删除 Cookie。新增 6 项回归测试（旧代码全部失败），全量 249 项通过，已部署并核对 working/repo 与 git 一致 |
| [v1.8.5](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.5) | **两套 Agent 安装提示词**：新增 `AGENT_INSTALL_DUALPC.md`（真双机版：采集卡 + KMBox Net / SendInput，独立项目 okww-dualpc，独立目录，不碰现有 ok-ww），主提示词与 README 加分流表（云鸣潮/MuMu/远控 → 原提示词；双机/采集卡/KMBox → 新提示词）。评估后**不把双机合并进本分支**：它是 6600 行 Python 适配层 + Rust 内核 + Qt 界面的独立实现，基线为 ok-ww-enhanced/老 ok-script，设备层把 device_dict 覆写成唯一双机设备、关闭 browser/adb/windows，与我们的云/MuMu/远控天然互斥。顺手修正 README 与提示词里过时的 `Done: 15/29 file copies`（现为 31×2=62，且以脚本实际输出为准）。仅文档变更，243 项测试仍通过 |

## 2026-11-25

| 版本 | 一句话摘要 |
| --- | --- |
| [v1.8.4](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.4) | **修复启动即崩**：v1.8.1 把全局配置 `MuMu/安卓 Config` 改名为 `MuMu 安卓 Config`（去斜杠）时只改了 `config.py` 的注册处，漏改 `BaseWWTask.py:123` 的读取处，于是每次任务初始化都抛 `RuntimeError: Can not find global config MuMu/安卓 Config`，整个 ok-ww 起不来（连试三次后退出）。改掉这 1 行并统一注释，新增 `tests/TestGlobalConfigRefs.py` 4 项 AST 静态检查（注册名可解析、注册名不含斜杠、`get_global_config` 字面量必须已注册、`*_CONFIG_NAME` 常量必须已注册），全量 243 项通过；实测启动日志 `Loaded 11 tasks` 且无 `ok:__init__ error`。**同时更正 v1.8.3 的表述**：启动器在"判定安装损坏"时会绕开 git 从官方文件整份重装（reflog 23:56:31 的 checkout 目标正是我们的定制提交，事后 HEAD 却仍是官方 `567f025`），所以让代码能正常启动才是第一道防线，钉 tag 只在正常启动路径上有效 |
| [v1.8.3](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.3) | **堵死"启动一次就丢定制"的第二条路径**：v1.8.2 把定制提交进 git 后，用户又意外打开一次官方启动器，22 个已跟踪文件仍被整体刷回官方（`config.py` 17430→13380 字节）。reflog 揭穿真相——启动器不是比对工作区，而是拿 `app.json` 的 `current_version`（`v3.8.15`）找**同名 git tag**，再 `git checkout -f`：tag 指向官方提交，`-f` 就强制覆盖工作区，定制提交只是"当时的 HEAD"、一秒钟被甩掉。所以 `restore.py` 新增 `pin_version_tag_to_head()`：把版本 tag 本身（`v3.8.15`）指到定制提交，原官方指向只备份一次为 `official-v3.8.15`；此后启动器的 checkout 切出来的就是定制树。已实测 `git checkout -f v3.8.15` 后 `repo/config.py` 仍是定制版、`working` 与 git 一致、重复运行幂等；`tests/TestRestoreGitSync.py` 8→13 项，全量 239 项通过。诚实边界：官方发新版后在更新卡片点"安装"仍会覆盖，重跑 `restore.py` 即可重新钉住 |
| [v1.8.2](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.2) | **修掉启动器显示「本地版本 3.8.14」**：代码基线一直是 v3.8.15（`config.py::version` / 启动日志 / 应用内关于页都对），但启动器（ok-ww.exe）读的是 `data/apps/ok-ww/app.json` 的 `current_version`，那是装 3.8.14 时留下的旧值。危害不止显示：启动器因此以为"还能更新到 3.8.15"，**点一下更新就会用官方代码覆盖 `working`/`repo`，定制全丢**。`restore.py` 现在每次部署都同步该字段（改前备份 `app.json.<时间戳>.bak`），9 项单测覆盖 |
| [v1.8.1](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.1) | **修正远控/串流窗口的入口位置说明**：它是左侧导航栏「游戏」分组里的独立页（图标=显示器），`show_at_tab` 配置项会被设置页主动跳过，所以**不在「设置」页里**；同时修掉配置名含 `/` 被当成目录分隔符、配置写进 `configs/远控/串流窗口.json` 子目录的问题（改名为 `远控串流窗口(试验性)`），`MuMu/安卓 Config` → `MuMu 安卓 Config`，并加单测禁止全局配置名再含斜杠 |
| [v1.8.0](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.0) | **试验性支持远控 / 串流软件窗口作为设备**（UU远程、ToDesk、向日葵、Parsec、Moonlight）：这类软件把被控电脑的画面显示成本机的一个窗口，所以「抓这个窗口 + 往里发真实键鼠事件」就等于操作被控电脑上的游戏，不需要远程专用逻辑。设置新增「远控/串流窗口(试验性)」（Enable / Window Title 正则 / Force Pynput），`Globals` 启动时把 `DeviceManager` 切成按窗口标题匹配：清掉 `Client-Win64-Shipping.exe` 与 `UnrealWindow` 类名限制、强制 `PynputInteraction`、重新指向 `HwndWindow`，并按实例禁用 `try_resize_to`（远控窗口不能被程序 resize，否则画面变形/加黑边）。`do_start` 在远控模式下把 16:9 参考尺寸传给 `find_hwnd`，让它先在窗口内部找 16:9 的画面区、再由 `HwndWindow` 裁掉多余高度；启动后检查客户区比例，非 16:9 会给出实际尺寸与修正建议（不阻断）。远控窗口没打开时不建「未连接」占位设备，避免启动流程误报「游戏路径不存在」。文档给出硬性要求：被控电脑游戏**全屏 16:9**、远控画质选原画、本机窗口客户区 16:9 无黑边、窗口必须前台、管理员运行、鼠标绝对定位。新增 22 项测试，全量 215 项通过 |
| [v1.7.0](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.7.0) | **把 MuMu / 安卓模拟器支持合并回官方 v3.8.15 基线**（三方合并，官方 3.8.15 的新特性——云战斗宽限、协奏环新算法、Cultivation 刷取、切换链限制——全部保留，只叠 MuMu 增量）：设备下拉重新出现模拟器，抓屏默认 MuMu IPC（全黑帧自动重建连接，加载期 30 秒冗余窗口），模拟器开机后自动用 adb 拉起游戏（20 秒冷却，且不再受抓屏方式限制），MuMu 网桥时从 ARP 表发现虚拟机 IP；输入在 ADB 之上**叠加真实键盘事件**由模拟器键位映射转发，`esc` 统一改写为键位表的 ` 键（返回/菜单），补全 F1-F12 / A-Z / 0-9 / 反引号；指南书与活动面板改为点右上角图标，书是否打开用笔画 IoU 判定；大世界判定改用雷达箭头/血条（PC 的 1/2/3 徽章在手游上永远匹配不到，曾导致卡 600 秒无日志）；编队支持「手填编队 > 缩放识别投票锁定」，战斗期零识别、切人键只在 1/2 里推导；「连接已断开」弹窗自动确认重登 + 掉线频率提示；月卡误报防护与宝箱超时恢复；**拉海洛方块支持 MuMu**（模拟器窗口 Pynput 输入、免 PC 窗口检查、返回键兜底），无尽模式与关卡页直接启动在 PC/云/MuMu 三端都可用；新增 28 项测试，全量 193 项通过 |
| [v1.6.0](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.6.0) | **以官方 v3.8.15 为基线重建**：官方已原生支持云鸣潮，且 `DailyTask` 只注册一次、按所选设备自动区分 PC / 云鸣潮 / 安卓操作，因此整体换回官方代码，删除我们自建的 `CloudDailyTask` / `CloudMultiAccountTask` / `SaveCloudAccountCookieTask` / `SwitchCloudAccountTask`（历史配置里的旧任务名仍可被读取，不会丢账号数据），任务列表恢复成"选设备 → 跑同一个日常/多账号"。**UID 遮罩改走框架通用 `blur_area`**：`Box(width*0.870, height*0.975, width*0.130, height*0.025)`，在设置「Enable Blur」里可选 Blur / Inpaint，截图与实时窗口都走框架同一套逻辑；框架侧不再有游戏专用的 DOM 注入，与 WebRTC 视频流捕获兼容。**该能力官方 ok-ww 早已自带**（`09b072a 设置中添加隐藏uid功能.`，2026-05-26，`config.blur_area` + `create_basic_options(enable_blur=True)`），我们只是把遮挡区域调得略大（官方为 `0.879 / 0.976`），因此不存在需要向上游提交的新功能。**多账号任务内新增「保存登录状态」「切换账号」两个按钮**，仅云设备下显示（PC 下不出现，也不注册成独立任务）；账号隔离改为纯 ok-ww 侧把 `cache/playwright` 目录整体换入换出，不改底层框架。**拉海洛方块 = 官方新版 + 无尽模式重新实现**：官方版要求 PC 窗口句柄且用 Pynput 发真实鼠标，云鸣潮下直接报"需要 Windows PC 客户端"，且无尽关卡没有难度页签会走到"无法选择难度"退页；现在按设备分流（云鸣潮走 BrowserInteraction、免窗口句柄），并补齐无尽页直启/加入进行中对局/达标退出结算、详情页直接开始、玩法说明弹窗关闭、通关退回主页点「立即前往」；另保留 4 块托盘搜索预算修复（任意托盘束裁剪 + 3 秒墙钟兜底），无尽模式不再卡死。MuMu / 安卓定制整支保留在 `legacy-mumu-v1.5.21` 分支，本版不合并 |
| [v1.5.21](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.21) | 云游戏 UID 遮罩兼容 WebRTC 捕获：主分支合入 WebRTC 视频流捕获（00cb86c）后，该模式直接读取视频流解码帧、不经过页面合成，原先注入的 DOM 覆盖层（`OK_UID_COVER_JS`）不会出现在帧里，导致截图/日志泄露右下角 UID（遮罩失效）。现在在取帧路径上按与 PC 端相同的比例（右下 13%×2.5%）直接涂黑帧像素，WebRTC 与 Playwright 截图两种捕获源输出一致；DOM 覆盖层保留，浏览器窗口内同样看不到 UID，二者共用 `cover_uid` 开关 |
| [v1.5.20](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.20) | 拉海洛方块"越跑越卡最后冻死"根因修复：无尽模式托盘是 4 块布局，而走棋搜索 `choose_move` 的束宽保护只认 3 块托盘，4 块时中间状态不裁剪导致组合爆炸——单次搜索要评估上千万次盘面，纯 CPU 卡死数分钟并把整机拖卡（关机线程转储定格在 board_value 计算中，零日志实锤）。改为任意托盘大小都做束搜索裁剪（全局状态上限 96）+ 3 秒墙钟兜底，超时直接用已找到的最优解，4 块托盘搜索从卡死数分钟降到 0.9 秒内；另发现算法模块 `rahai_blocks.py` 此前不在部署清单、修复从未同步到运行目录，已补入并重新部署 |
| [v1.5.19](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.19) | 拉海洛方块两个实测问题修复：① 无尽详情页直接退出——OCR 读不到"无尽模式"等特征文字导致报"无法识别难度"后误点 X 退页（18:28 实测日志），现在难度识别全失败时只要有"开始挑战"按钮就直接开始（跳过积分/奖章目标检查），点开始后若实际进入无尽模式自动转无尽流程；② 云游戏任务卡死——CDP 交互调用 `future.result()` 无超时，浏览器卡顿/假死时拖拽鼠标事件永久阻塞（18:29 实测 71 秒无日志），现在 `run_in_loop` 加 15 秒超时，超时取消调用并告警放行，任务自动继续 |
| [v1.5.18](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.18) | 拉海洛方块直接支持无尽模式：此前无尽页面（无难度选项）会报"无法识别难度"、局内则直接 FatalTaskError；现在从无尽模式详情页可直接开始，或加入已在进行中的对局（识别局内"历史最高/达到N分结算"UI、玩法弹窗与棋盘），一直落块消行，达到目标分数（如"达到9999分结算可得首通奖励"）后主动退出结算领奖励，无合法落点则等游戏自动结算；开始按钮增加宽域"开始/开始挑战"兜底 |
| [v1.5.17](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.17) | MuMu 三项修复: ① 每日任务活跃行迹——手游指南书布局与 PC 不同导致 PC 专属 OCR 区域全部落空（实测日志"total daily points 未识别"→保守跳过体力），新增安卓分支：OCR 定位"活跃行迹"子页签 + 宽域识别 x/180 用量与 x/100 活跃度（分母限定过滤任务进度，优先取"活跃度"文字附近读数）；② 拉海洛方块 MuMu 支持——开局"无尽模式"玩法说明弹窗自动点确认、无尽模式详情页（无难度选项）明确提示暂不支持并继续其余关卡、手游难度页签识别不到时宽域 OCR 兜底（按当前选中难度继续）、手游返回列表失败用安卓返回键兜底；③ 掉线恢复加固——掉线弹窗按钮识别补充"重新登录/重新连接"变体，短时多次掉线（10 分钟 ≥3 次）提示 MuMu 后台省电/网络排查建议。另：自动战斗不触发的根因是 ok-ww 进程早于代码恢复启动、内存仍是 v1.5.13 旧字节码（load_chars 每 100ms 抛 AttributeError，当日 7384 次），**恢复脚本已部署修复版，重启 ok-ww 即生效** |
| [v1.5.16](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.16) | 拉海洛方块支持在关卡详情页直接开始：此前必须停在活动关卡列表页否则报错；现在检测到玩家已打开某关卡页面（OCR 到"关卡目标"）时直接开始当前选中的难度（OCR 识别简单/困难，不误切难度），打完回列表继续扫描其余关卡，直启失败仅告警不中断 |
| [v1.5.15](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.15) | 修复爱弥斯上场 0.3~0.9 秒即被切走、全场零输出（与副C/奶妈形成 2.7 秒切人死循环）：上游设计要求"变奏入场+两个队友都满协奏退场且 buff 未超时"才出招，但 buff 打点只在满协奏退场时生效，副C 经常协奏未满就被切走导致条件恒 False；定制 Aemeath 改为变奏入场就正常输出（强化E/大招/二段大仍由模板判定兜底），未入场且有副C时保持待机 | 
| [v1.5.14](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.14) | 修复 v1.5.13 引入的战斗检查错误风暴：编队识别阈值误写成 `self.ANDROID_DETECT_THRESHOLD`（实为模块级常量），运行时 AttributeError 每 100ms 炸一次 `do_check_in_combat` 致战斗检查瘫痪；改为引用模块常量，并把编队识别整段包上 try/except——识别环节任何异常只记一条日志即走上游 PC 框兜底，load_chars 不再被识别异常炸掉（自恢复）；PC/云游戏行为不变 |
| [v1.5.13](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.13) | 修复 MuMu 延奏识别失效与切人乱（一个人 A 到死、不切奶妈）：手游队伍栏是圆形头像（比 PC 大 1.7 倍且构图不同），PC 头像模板固定尺度匹配导致同一队 2 秒读出 4 种组合、角色类型每帧漂移；新增安卓编队锁定（手填编队 > 队伍栏缩放 0.58 识别 + 连续 3 次一致投票锁定，锁定后零识别，战斗期绝不复检，失败回退上游路径）；协奏环检测框在手游上完全够不到弧（PC 环带 22~27px vs 手游弧 37~42px）导致 current_con 恒 0，新增安卓专用大框覆盖弧且排除图标本体；PC/云游戏行为不变 |
| [v1.5.12](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.12) | 修复 MuMu 声骸副本炸每日任务：走向奖励时残象其实还没清完（切波次间隙被误判战斗结束），宝箱未刷新导致找图标 30 秒超时抛 WaitFailedException 且手游端 in_realm 恢复路径失效；改为找宝箱超时先回战斗清残象再重走一次，仍无宝箱交回上层 rechallenge 循环恢复。队伍识别改为以配置的编队为准，移除战斗期间的队伍栏徽章 OCR（战斗特效会干扰识别），切人键按编队规则推导（键 1→靠后队友），PC/云游戏行为不变 |
| [v1.5.11](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.11) | 修复 MuMu 切人：模拟器键位映射只有 1/2 两颗切换键，旧兜底映射会发不存在的 3 键导致切 3 号位永远失败；改为键->角色映射随出战角色动态推导（OCR 键位提示 > 队友已确认键 > 实测规律兜底），发切人键后用编队徽章核实实际出战角色，按错键自动换另一颗键重试，PC/云游戏行为不变 |
| [v1.5.10](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.10) | 修复 MuMu"打着打着莫名其妙不打了"：boss 潜地/无敌帧/切波次期间血条消失，安卓端因 has_target 与血条同判定走不到 PC 的 30 秒耐心路径，3 秒重锁定失败即退出战斗；安卓无血条重锁定耐心 3→8 秒、失败先重试一轮再退出、等待锁敌期间继续普攻、连续无敌人退出窗口 2→4 秒、整帧黑保护，PC/云游戏行为不变 |
| [v1.5.9](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.5.9) | 修复 MuMu 无法谐振破坏：PC 的 f_break 模板是 F 键帽，手游端是触摸图标永远匹配不上；安卓端改为 f_break_full 谐振条模板（阈值放宽 0.85）+ OCR 识别"破坏/谐振"提示文字，识别到后直接点击提示位置触发，不再按 F 键，PC/云游戏行为不变 |
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

- **云鸣潮**：浏览器设备入口与启动逻辑、按账号的 Playwright profile 目录换入换出、后台输入伪装、进入游戏完成检测。
- **云多账号**：直接沿用官方的单个日常任务（`DailyTask`）+ `MultiAccountDailyTask`，按所选设备自动区分 PC / 云鸣潮操作；云端专属的「保存登录状态」「切换账号」是多账号任务内的两个按钮（仅云设备显示），不再单独注册任务。
- **任务错误恢复**：优先重启浏览器并重跑，失败回退刷新页面，同一错误 3 次后停止。
- **角色代码 / 队伍工坊**：从上游历史恢复并适配新版 GUI，含工坊服务器下线后的离线快照回退。
- **备份与一键恢复**：`restore.py` / `一键恢复.bat` 同时恢复到 `working` 与 `repo`，Cookie 与账号配置始终排除在外。
