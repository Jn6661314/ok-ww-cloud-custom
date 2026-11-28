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

按**日**汇总，完整改动明细见 [Releases](https://github.com/Jn6661314/ok-ww-cloud-custom/releases)（中英双语）。

### 2026-11-28

- **[v1.8.27](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.27)** — **基线升到官方 v3.8.18 + 修掉上游评审的 7 个问题 + 第一次给「解压即用」的绿色成品包**：定制层从 v3.8.15 rebase 到 v3.8.18，上游新增的 `child_session` 与本地 `adb` 入口并存；7 条评审问题（锁敌重试要血条正向证据、跳过聚落仍找残象、无尽判定只认正则、云多账号配置隔离、`_replace_dir` 跨盘回滚、`_is_cloud_device` 回落 `config['preferred']`、`_run_cloud_account` 分开两种 None）全部修掉，Python 全量 **481 项通过**。绿色包 `ok-ww-custom-v1.8.27-full.7z` 用自建 134KB 轻量启动器直接跑内置 Python，**不碰 git**，解决官方 pyappify 启动器「一打开就把定制补丁还原」的问题；不含任何账号/Cookie/配置/日志。**同日追加**：手机投屏不再自动弹预览窗口（点按钮才开，窗口仍是实时画面）；截图一律不再落盘到 screenshots/。需重跑 `restore.py` 并重启 ok-ww；或直接下载绿色包解压双击 `ok-ww.exe`。

### 2026-11-27

- **[v1.8.26](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.26)** — **手机投屏：按键变触点（可校准的键位映射）+ 电脑上能看到手机画面**：投屏下 MuMu 那套按键失效，根因不是没做映射，而是**这层映射本来就不存在于真机**——MuMu 上是模拟器自带键位映射把真实键盘事件翻成触点；NectarLink 手机端收到按键只会当 **Android 按键事件**注入（`PhonePlatform.kt:295` → `Elevated.kt:1139` 的 `K <keycode>`），而鸣潮手游只认触点，协议层也没有任何消息能改对端键位（`phone.toggles` / `phone.toggle.set` 只管免打扰、铃声、手电筒这些）。于是把 MuMu 那份映射搬到 ok-ww 自己身上：新增 `src/phone_mirror_keymap.py`（`键 -> 屏幕比例坐标`，存 `configs/phone_mirror_keymap.json`，比例坐标与横竖屏/缩放/黑边无关），`PhoneMirrorInteraction.send_key()` 命中映射就发 `TOUCH_DOWN/UP` 触点、没命中才回退手机系统键；**返回/菜单的老问题**一并修掉——手游里返回和打开菜单是同一个按钮，发 `esc` 过去手机会当成 `KEYCODE_BACK` 弹「是否确定退出游戏」，现在 `TouchMode.is_touch` 把投屏也算触屏，`back()` / `open_menu()` 走键位表的 `` ` `` 翻成左上角一次点击（默认只给这一个键，因为位置固定；技能/切人的位置随手机分辨率和游戏内自定义布局而变，硬编码一套标准布局会点偏，而点偏比不点更糟）。新增**校准窗口**（配置 → 手机投屏 → 校准键位(点屏幕)）：左边列出菜单/返回、切人 1/2/3、技能 E、共鸣解放 R、交互 F、跳跃、锁敌 Y，选中后在右边投屏画面上点一下即绑定，自动跳到下一个键，点「保存」写盘。另新增**预览窗口** `src/phone_mirror_preview.py`：独立连一条到投屏内核的连接，实时显示手机画面（内核 `serve` 是循环 `accept`、每个连接单独推流，**不会抢任务那条连接**），可缩放、默认窗口置顶、底部显示真实分辨率；入口有两个——配置按钮「预览手机画面」（内核没跑会自动拉起），以及配置项「运行时显示画面」（默认开，任务启动时自动弹出）。新增 12 项测试，Python 全量 **477 项通过**；校准窗口与预览窗口都用真实内核开过并截图确认。**需重跑 `restore.py` 并重启 ok-ww**，然后**手机横屏进游戏**再校准（竖屏画面点出来的坐标对横屏无效）。
- **[v1.8.25](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.25)** — **手机投屏「能连上但启动不了」：连是按毫秒算的，框架问得太早**：v1.8.24 之后内核连上了、画面端口也拿到了，点开始却起不来，而日志同一屏里自相矛盾——既有「已连接投屏内核, 画面端口 64353」，又有 `start_device: {... 'connected': False ...}`，说明**不是没连上，是问得太早**。根因是一个几十毫秒的时序窗口：`PhoneMirrorSocketCaptureMethod.start()` 只把接收线程拉起来就 `return`，而 `connected()` 判的是 `_running and _socket is not None`，`do_start` 紧接着读它，于是必然读到 `False`（本机回环实际只需 **31ms**）；这个瞬时值又被 `do_start` 结尾的 `preferred['connected'] = capture_method.connected()` 写回 `device_dict`，覆盖掉 `update_pc_device()` 里内置引擎伪设备的 `True`。而框架 `start_controller.start_device()` 对「未连接的 windows 设备」只有两条路——**要求以管理员身份重启**，或者**去启动游戏 exe**；内置引擎是个没有窗口、没有 exe 的伪设备，于是走到「游戏路径不存在，请手动打开游戏」，任务根本起不来。修复：`start()` **等到真的连上才返回**（最多 3 秒），连不上就老实返回 `False` 不谎报；`connected()` 增加 **8 秒重连宽限**（内核换模式/手机短暂掉线时 socket 会断，后台线程一秒内重连，间隙里不能判成未连接）；`_use_phone_mirror_engine_capture()` **同端口已连接就复用**，不再每次启动流程都把 socket 重建一遍（每次重建都会造出一个新的空窗）；`do_start` 里内置引擎的 `connected` **恒为 `True`**——伪设备没有"外部设备"可断线，能不能用由 capture 层回答（`check_device_error` 会检查并实际取一帧），内核真没起来时仍会打出真实原因（如「手机端关掉了自动重连」）。Python 全量 465 项通过（新增 3 项：`start()` 返回即已连接、端口没人监听时不谎报、刚断开的瞬间仍算连接）。另用**真实运行中的内核**实测：`start()` 31ms 返回 `True`、`connected()` 立刻为真、0.5 秒收到 `1080×491` 画面。**需重跑 `restore.py` 并重启 ok-ww**（只改 Python 侧，内核二进制未动）。
- **[v1.8.24](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.24)** — **手机投屏连不上：不是网络问题，是手机端把「这台设备的自动重连」关掉了**：v1.8.23 之后内核不再秒退，但真机仍连不上，而且有一条决定性对照——**同一个手机、同一个局域网，NectarLink 桌面端能连、ok-ww 内置内核连不上**。用 ok-ww 自己的身份连：QUIC 握手**成功**，随后对端发来 `ApplicationClosed{error_code:0, reason:b"reconnect off"}`；仅把 `identity.key` 换成桌面端那份（数据目录一行不动），**1 秒内**就连上并出画面。根因：`reconnect off` 只在 `!reconnects(&peer)` 时产生，而 `reconnects()` 读的是**本机** `peer_toggles` 表的 `reconnect` 行（缺省 true），ok-ww 数据目录里那张表**是空的** → **不是我们拒的，是手机拒的**；协议层也确认 `phone.toggles` / `phone.toggle.set` 只管手机快捷开关（免打扰、铃声、手电筒、音量、亮度、Wi-Fi、蓝牙），**没有任何一条消息能改对端的 `reconnect` 开关**，它只存在手机本地。手机端唯一写入点 `Core.setReconnect`、唯一 UI 入口在 `HomeScreen.kt`：**同一个按钮设备在线时显示「断开」、离线时显示「停止重连」，两者都调 `setReconnect(false)`**，而恢复用的「重连」按钮只在「离线且自动重连已关」时才出现 —— 所以「点一次断开」= 永久关掉这台设备的自动重连，而它看起来只是断开一次。顺带**纠正 v1.8.23 的一条错误论据**：「本端日志没有 `refusing session` 所以不是我们拒的」无效——那行是 `tracing::debug!`，内核跑的是 `info` 级，压根不输出。修复：内核把「先等上线再请求投屏」合并成「一边等一边试」（**只有真的发起请求，错误里才带着手机拒绝的理由**），认出 `reconnect off` 立刻发 `notice(reconnect_off)` 并按中文原因退出（以前会等满 120 秒再错报「手机没上线」）；ok-ww 侧新增 `_looks_like_reconnect_off()`，**识别必须放在「过滤日常 INFO 日志」之前**（那行正是 `tracing::info!`，按原规则会被当成噪声扔掉），`failure_reason` 换成一句能照做的中文，`wait_ready()` 认出拒绝立即返回。Rust 9 项 + Python 全量 462 项通过。**需在手机 NectarLink 的设备列表里给 ok-ww 点一次「重连」**（该按钮只在设备离线且自动重连已关时出现），再重跑 `restore.py` 并重启 ok-ww。
- **[v1.8.23](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.23)** — **修好「手机投屏启动不了」（内核起来就自己退）**：单独跑内核复现，stderr 里的实话是 `device is offline`——而且是在节点启动后**仅 23ms** 就去请求投屏。根因是 `mirror_start` 要求会话已建立，而节点刚起来时后台还在拨号重连，握手根本没完成 → 必然失败（上游 NectarLink CLI 在同一件事上会先 `wait_until_online` 等设备上线，我们漏了这一步）。另发现**同时有 3 个 `nectarlink-sidecar.exe` 在跑**，用**同一个设备身份**、占 3 个 UDP 端口、mDNS 广播同一个 NodeId，手机拿到对不上的地址就判「离线」——即使加了等待，上一轮内核没退干净照样连不上。修复：内核新增 `wait_until_online()`（判据 `LinkState::Online`，每 300ms 查一次，默认最多等 120 秒，等待期间每 10 秒报一次进度，不让界面看着像卡死）+ 投屏请求失败自动重试（Offline/Network/Timeout 最多 5 次，手机刚同意时连接常要重建一次）+ `sidecar.json` 状态文件记录 pid；ok-ww 侧捕获内核 stderr 并过滤掉 tracing 的日常 INFO，把**真实原因**（如「设备离线」）显示出来，不再只有一句没头没尾的「还没就绪」；启动前清掉残留内核（读状态文件 + 按命令行扫同数据目录的进程）；`pid_alive()` 走 Windows API 而不是 `os.kill(pid, 0)`（**Windows 上后者会直接 TerminateProcess**，「试探进程还在不在」本身就会杀掉进程）；配对模式与普通模式自动切换（以前跑着普通内核时点「配对手机」一直等不到二维码）；配对码拿到前两个确认按钮禁用；内核日志关掉颜色码（颜色码把 ` INFO ` 拆成两半，导致噪声过滤失效）。Rust 8 项测试通过，Python 新增 16 项，全量 455 项通过。**需重跑 `restore.py` 并重启 ok-ww**（换了内核二进制）。
- **[v1.8.22](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.22)** — **修好配对二维码（之前根本出不来，手机也扫不动）**：v1.8.20 的内置投屏内核第一次真机使用就卡在配对——窗口能开、状态栏写着「等待手机扫码…」，**二维码那块却是空白**。日志显示内核其实正常（配对链接已拿到），问题在 ok-ww 画码这一段，三个 bug 叠在一起：① 转 Qt 图像时 `bytesPerLine` 传了 `width` 而不是 `width * 3`（BGR 每像素 3 字节），Qt 认为数据不足直接给**空图** → 界面白板；② 二维码被**反相**了——OpenCV 编码器输出的本来就是标准白底黑码，反相后变成黑底白码，手机扫码器不认（之前那条测试断言的恰恰是反相后的样子，等于把错误当成了标准）；③ **缺静区**（标准要求四周留 4 个模块宽）。现在：不反相 + 补静区 + 缩放改 6 倍（真实链接 178 字符 → 61×61 模块 → 366 像素正好不裁切）+ `bytesPerLine` 修正，并加了转换失败时的告警（不再默默显示白板）。另外内核往 stdout 写配对提示语（`print!` 无换行）会把后面的 JSON 粘成一行、**整条消息被吞掉**（`paired` 尤其致命，配对成功了 ok-ww 却不知道）——改成写 stderr，stdout 保持纯 JSON；ok-ww 侧的解析器也加了容错（按大括号配平逐个抠 JSON）。端到端验证：拿内核真实发出的 178 字符链接走完「编码→加静区→缩放→转 Qt 位图→从位图读回→扫码」，扫出来与原文逐字符相同。新增 11 项测试，全量 437 项通过。**需重跑 `restore.py` 并重启 ok-ww**（这版换了内核二进制）。
- **[v1.8.21](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.21)** — **两个手机投屏菜单合成一个**：v1.8.19 的「手机投屏(NectarLink)」和 v1.8.20 的「手机投屏(内置引擎)」并排挂着，功能其实重叠（旧菜单只有一个下载入口，新菜单已经包住了）。现在合成一个「**手机投屏**」，里面用「**模式**」下拉切换：**内置引擎**（默认，ok-ww 自带内核，不用装桌面端）／**桌面端**（抓 NectarLink 桌面端的投屏窗口，需自己装桌面端）。选桌面端时**不用再去「远控串流窗口」菜单里选一次 NectarLink 预设**，本菜单直接切到投屏窗口并打上 `phone_mirror` 标记（编队识别/切人按安卓端处理）；「远控串流窗口」菜单本身不受影响，UU远程/ToDesk/Moonlight 照旧。**配置自动迁移**：框架里 `ConfigOption` 的名字就是配置文件名，改名会让用户设置"消失"（改了配置却不生效），所以新增 `src/phone_mirror_config.py` 在启动最早期把旧的两份配置合成 `手机投屏.json`，`Enable`/画面宽度/帧率/码率全部保留，模式按旧配置推断；迁移只在真正启动时执行，测试不会动用户真实配置。设备下拉条目从「手机投屏(内置引擎)」改成「手机投屏」。新增 15 项测试，全量 426 项通过；**升级后不用改配置**，需重跑 `restore.py` 并重启 ok-ww。
- **[v1.8.20](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.20)** — **内置投屏引擎：把 NectarLink 桌面端装进 ok-ww**：新增内置投屏内核 `bin/nectarlink-sidecar.exe`（Rust，基于 nectarlink-core 的 MPL-2.0 无界面内核，用 Windows 自带 Media Foundation 解 H.264，画面经本机 socket 推给 ok-ww），**不用再装 NectarLink 桌面端**；ok-ww 侧新增 socket 抓屏（裁黑边 + 归一化到模板原生 1080）与触点输入（点击/滑动/按键直接变成手机触点，**不再走真实鼠标**，窗口不用在前台）；新增全局配置「手机投屏(内置引擎)」（Enable / 手机 / 画面宽度 / 帧率 / 码率 / 配对手机 / 启动投屏内核），配对二维码用 OpenCV 自带编码器生成（不需要额外依赖）；投屏模式的 16:9 分辨率契约彻底放宽，不再报 `resolution error`、不再弹错误框、也不再去 resize 窗口；内核端口写在 link.json 里可跨次运行复用，少重启就少在手机上点「允许」。新增 5 项测试（假内核端到端：收帧/裁边/归一化/坐标/触点/二维码），全量 407 项通过。**需重跑 `restore.py` 并重启 ok-ww**；配对与出画面效果由用户实机确认。
- **[v1.8.19](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.19)** — **手机投屏(NectarLink)驱动真机玩鸣潮，取代 MuMu 模拟器**：NectarLink 把手机画面投成 PC 窗口，并按**屏幕比例**把鼠标点击转回手机（协议 §4「Positions are fractions of the screen」），坐标换算由投屏软件全权负责 —— 缩放/黑边/横竖屏都不再影响落点，正好绕开 MuMu 上折腾五版都没解决的触控坐标错配。本版把投屏窗口接进 ok-ww：「远控串流窗口(试验性)」Preset 新增「NectarLink 手机投屏」预设（自动匹配标题 `<设备名> · NectarLink`），设备打 `phone_mirror` 标记并在 `BaseWWTask.is_adb()` 认它，于是 v1.8.18 的编队识别首次即锁定、编队角色下拉、切人键 1/2 全部直接生效；手机投屏不做 16:9 裁剪、不弹 16:9 告警、不尝试启动本机游戏。新增「手机投屏(NectarLink)」全局配置，带**「下载手机端(网盘)」按钮**（网盘地址 `https://pan.baidu.com/s/13Y-rkKtfp7EQHd4SJwdzDA?pwd=Jn66`）。新增 22 项测试，全量 380 项通过。**需重跑 `restore.py` 并重启 ok-ww**；切人需在手机端 NectarLink 里把 1/2 绑成切人键。
- **[v1.8.18](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.18)** — **修复 MuMu 战斗切人永远只切 1 号位**：手填编队为空→走画面识别，投票锁定要求连续 3 次一致，但战斗特效让每次识别都不同（日志每 0.1~0.2s 在渊武/折枝/漂泊者/奥古斯塔间乱串、213 次、锁定 0 次），导致 `load_chars` 每帧重建角色、当前下标恒被重置为 0、切人键映射全乱。改为：战斗中首次识别即锁定、整场战斗不再换锁；「MuMu 安卓 Config」新增三个「编队角色」下拉（58 个官方名点选，防写错、槽位固定），优先于旧字符串编队，坏槽位跳过不作废。新增 8 项测试，全量 357 项通过。**需重跑 `restore.py` 并重启 ok-ww**，建议填三个编队角色下拉最稳。
- **[v1.8.17](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.17)** — **修复「开了远控窗口模式，设备下拉还是 PC 客户端」**：`Enable=true` 但 `Preset=Manual`、`Window Title=""` 时，旧逻辑发现标题为空就打一句「没填窗口标题，继续使用默认 PC 设备」直接返回，`set_stream_window()` 从未执行 —— 开关被静默忽略、GUI 无任何提示。本版改为：未填标题也启用远控模式，`set_stream_window(None)` 清空 `exe`/`title`/`hwnd_class`/`top_hwnd_class` 全部过滤，`update_pc_device()` 枚举所有可见窗口，下拉里就能选中远控窗口（仍强制 Pynput）；填了标题/Preset 时仍是精确匹配；日志改为明确提示。新增/更新测试覆盖空标题分支与全窗口枚举，远控相关 31 项、全量 349 项通过。**需重跑 `restore.py` 并重启 ok-ww**。
- **[v1.8.16](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.16)** — **MuMu 方块改用落点预览视觉闭环，彻底不再猜触控坐标**：v1.8.12~v1.8.15 连续四版修拖拽落点（sendevent 手算 / input motionevent / IPC 触控）都没解决，因为 MuMu 的「触控坐标→屏幕落点」关系因版本/设置而异、无法靠读代码猜。换思路：拖拽时游戏会把方块吸附到目标格并显示**高亮落点预览**，直接读预览中心（`preview_center`) 与目标格比较，用两条正交探针**实测**「手指像素→预览位移」的 2x2 映射（覆盖缩放/镜像/轴交换），求逆反推手指该挪多少，迭代到命中；伺服失败且需旋转时补转一圈再试。PC/云鸣潮仍走原坐标路径。新增 7 项测试（含各向异性缩放、双轴镜像收敛），全量 347 项通过。**需重跑 `restore.py` 并重启 ok-ww**，落点由用户实机确认，反正还是用不了（悲）。
- **[v1.8.15](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.15)** — **MuMu 方块拖拽改用 IPC 触控，修复 x/y 落点大幅偏移**：v1.8.14 的 `input motionevent` 走 Android `wm size` **竖屏逻辑坐标**（MuMu 报 900x1600），而任务算的是**横屏截图坐标**（1600x900），两套坐标系错配，实机 x、y 都偏得极远。新增 `NemuIpcTouchDevice` 用 MuMu IPC 的 `nemu_input_event_touch_down/up` 注入触点 —— 它的坐标与截图 framebuffer 完全一致（官方框架 `swipe_nemu` 直接传截图像素坐标、`convert_xy` 是注释掉的），无需任何旋转换算；MuMu IPC 可用时优先用，非 IPC 抓屏回退旧方案，旋转仍走键位映射 F1。新增 7 项测试，全量 340 项通过。**需抓屏方式为 IPC（`devices.json` 的 `capture` = `ipc`）、重跑 `restore.py` 并重启 ok-ww 才生效**，落点由用户实机确认。
- **[v1.8.14](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.14)** — **MuMu 方块拖拽改用 input motionevent，修复落点错位**：v1.8.12~v1.8.13 拖拽走 `sendevent` 手算物理坐标，但游戏横屏 1920x1080 → 物理触屏 1080x1920 需要做 90° 旋转（翻一个轴），代码却只做转置 `(gy,gx)` = 沿对角线镜像，导致「方块移动不到预期位置、高度差很远」、`Placement preview did not match` 连续三次失败。本机 Android 15 支持 `input motionevent DOWN|MOVE|UP x y`，它用**逻辑显示坐标**（与截图画面一致 1920x1080），由系统自动旋转到物理触屏，无需手算映射。新增 `AdbMotionEventDevice` 并让方块任务在 MuMu 下改用它；旋转仍走 v1.8.13 的键位映射键（键盘），与拖拽互不干扰。新增 6 项测试，全量 236 项通过。**需重跑 `restore.py` 并重启 ok-ww 才生效**。
- **[v1.8.13](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.13)** — **MuMu 方块旋转改走可配置键位映射键**：v1.8.12 用固定屏幕坐标点「旋转」按钮，但 MuMu 物理触控 1080x1920 + 逻辑显示 1920x1080 之间有旋转层，窗口缩放时坐标失效，导致 `Placement preview did not match`、连续三次落子失败。新增配置项 `Rotate Key (MuMu Keymap)`（默认 `f1`，不与游戏热键冲突）：在 MuMu 键位映射里把该键绑到游戏内旋转按钮，方块旋转时发真实键盘事件由键位映射完成，坐标不再靠猜；拖拽仍走 sendevent（slot 0），旋转键发送失败自动回退点屏幕按钮。**需先在你自己的 MuMu 键位映射里把 F1 绑到旋转按钮**，再重跑 `restore.py` 并重启 ok-ww。新增 8 项测试，全量 230 项通过。
- **[v1.8.12](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.12)** — **MuMu 拉海洛方块真双指触控 + 不再要求窗口前台**：手游版旋转靠屏幕左侧圆形「旋转」按钮，操作是「一指点旋转 + 一指长按拖方块」，MuMu IPC/u2 都是单指 API 做不到。新增 `src/task/multi_touch.py`，用 ADB `sendevent` 写 `ABS_MT_SLOT` 多点触控：slot 0 拖方块、send_key('r') 走 slot 1 点旋转按钮，坐标映射实测 `物理(x,y)=(游戏y,游戏x)`，触控节点自动探测，任务中断自动释放触点。另外**修复"必须在前台"**：IPC 抓屏（从模拟器内部取帧）+ sendevent 输入都不依赖窗口前台，MuMu 可后台跑方块；方块输入改用 sendevent 后不再需要 windows 抓屏的 `get_abs_cords`，配置回退到 IPC 抓屏（保留 v1.8.11 修的启动器 exe 解析防「连不上」）。新增 17 项测试，全量 225 项通过。**需重跑 `restore.py` 并重启 ok-ww 才生效**。
- **[v1.8.11](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.11)** — **修复鸣潮已启动但 MuMu 报"未连接"**：从远控窗口/PC 切到 MuMu 时 `devices.json` 的 `capture` 残留 `windows`，`do_start()` 照它走 windows 抓屏、拿 `MuMuNxMain.exe` 启动器去 find hwnd → hwnd=0 报"设备未连接"，而 adb 其实早连上了、鸣潮也在前台。现在 `do_start()` 改用 `get_preferred_capture()` 纠偏（残留值按设备类型回退到 app config 声明的 `ipc`），windows 分支也用 `resolve_emulator_window_exe()` 解析出真正的窗口 exe。新增 10 项测试，全量 305 项通过。**需重跑 `restore.py` 并重启 ok-ww 才生效**；现有配置无需手改，启动自动纠偏。
- **[v1.8.10](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.10)** — **修复首次进配置页不显示账号按钮 + MuMu 设备列表加载慢**：云鸣潮下刚启动 ok-ww 就进多账号设置页时，「保存登录状态」「切换账号」两个按钮不出现（设备列表还没异步刷新完，`_is_cloud_device()` 判定落空）；现在设备未就绪时回退检查云游戏配置是否存在，按钮照常显示，PC/安卓下仍不显示。另外打补丁后设备下拉卡好几秒才出列表——MuMu 网桥回退对整个 ARP 表逐 IP 探测且不缓存；现在加 120 秒 TTL 缓存、探测超时 0.4→0.25 秒，刷新从十几秒降到毫秒级。新增 6 项测试，全量 295 项通过。**需重跑 `restore.py` 并重启 ok-ww 才生效**。
- **[v1.8.9](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.9)** — **修掉云鸣潮「打着打着敌人没打完就停了」**：官方云游戏是锁定图标优先 + 血条辅助的双判定，血条消失还有 3 秒宽限；我们定制的 `no_enemy_for()` 却统一用 2 秒，比宽限还短，串流延迟/技能特效让图标和血条闪断 2~3 秒就被判脱战、退出战斗去走奖励，30 秒后官方才发现战斗还在又重打。现在云游戏端单独用 6 秒窗口（PC 2 秒 / 安卓 4 秒不变），重锁时血条闪断忍耐放宽到 3 秒；不会无限续命，聚落任务的锁敌超时也不受影响。新增 10 项测试，全量 287 项通过。
- **[v1.8.8](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.8)** — **战斗奖励副本出错后现场续打，不再重进**：无音区等副本中途报错时，旧流程重启浏览器后会被 `ensure_main()` 按 Esc 踢出副本、再从 F2 图鉴重进，白丢这一场。现在出错瞬间先记录是否在副本，重启后优先续打未结束的战斗、探测战斗是否结束、发现「领取」F/宝箱就按 F 领奖，再正常退出副本；续打成功跳过二次 `ensure_main`，剩余任务照常执行。不在副本/探测失败/云端会话已回首页时安全回退；可用任务配置 `Cloud Resume Reward Dungeon: false` 关闭。新增 13 项测试，全量 277 项通过。
- **[v1.8.7](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.7)** — **残象聚落锁敌兜底 + Moonlight 预设**：双极这类敌人飞出聚落范围时，5 秒内锁不到就在**原地**重锁 2 次（不追出边界）；仍失败则跳过当前聚落、直接去图鉴找下一个，真打死有 F 掉落时照常拾取。两个参数（`Lock Retry Timeout (s)` / `Lock Retries`）在任务配置里可调。远控窗口新增 `Preset` 下拉，**Moonlight 一键匹配串流窗口**「`<主机名> - Moonlight`」（不会误抓主界面）；UU远程/ToDesk/向日葵/Parsec 也有预设，可与手填正则叠加。新增 15 项测试，全量 264 项通过。
- **[v1.8.6](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.6)** — **修复重启任务偶尔丢失云鸣潮账号登录态**：任务出错自动恢复时 `restart_browser()` 没收到账号，内部把 `None` 当成 `default`，结果把当前账号的 profile 存好后却装回磁盘上遗留的 `default` profile，`active_account` 也被改写，表现为「重启后账号掉了」。现在以 live profile 的归属标记为准（`resolve_account()`），错误恢复显式传账号；profile 目录被 Chromium 短暂锁住时改为重试 + 失败回滚，不再静默删 Cookie 文件。新增 6 项回归测试（旧代码全挂），全量 249 项通过。**需重跑 `restore.py` 并重启 ok-ww 才生效**，已有 profile 不受影响。
- **[v1.8.5](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.5)** — **两套 Agent 安装提示词**：新增 [`AGENT_INSTALL_DUALPC.md`](AGENT_INSTALL_DUALPC.md) 对应真双机版（采集卡 + KMBox Net / SendInput，来自独立项目 okww-dualpc，独立目录安装，不碰现有 ok-ww），原提示词与 README 加分流表。评估后不把双机合并进本分支：它是 6600 行 Python 适配层 + Rust 内核 + Qt 界面的独立实现、基线不同、设备层与其他设备互斥。顺手修正两处过时的 `Done: 15/29 file copies` 文案。仅文档变更，243 项测试通过。

### 2026-11-25

- **[v1.8.4](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.4)** — **修复启动即崩**：v1.8.1 把全局配置 `MuMu/安卓 Config` 改名为 `MuMu 安卓 Config`（去斜杠）时只改了 `config.py` 的注册处，漏改 `BaseWWTask.py:123` 的读取处，导致每次任务初始化都抛 `RuntimeError: Can not find global config MuMu/安卓 Config`，ok-ww 连试三次后直接退出。改掉这 1 行 + 新增 `tests/TestGlobalConfigRefs.py` 4 项 AST 静态检查（`get_global_config` 的字面量必须都在 `config.py` 注册过），全量 243 项通过，实测启动 `Loaded 11 tasks` 无报错。
- **[v1.8.3](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.3)** — **堵死「启动一次就丢定制」的第二条路径**：v1.8.2 把定制提交进 git 后，又打开一次官方启动器，22 个已跟踪文件仍被整体刷回官方（`config.py` 17430→13380 字节）。reflog 揭穿真相：启动器不是比对工作区，而是拿 `app.json` 的 `current_version`（`v3.8.15`）找**同名 git tag** 再 `git checkout -f` —— tag 指向官方提交时，`-f` 直接覆盖工作区，定制提交只是"当时的 HEAD"、一秒钟被甩掉。`restore.py` 现在把版本 tag 本身（`v3.8.15`）指到定制提交（原官方指向备份为 `official-v3.8.15`），此后启动器的 checkout 切出来的就是定制树；已实测 checkout 后仍是定制版、重复运行幂等，`tests/TestRestoreGitSync.py` 8→13 项，全量 239 项通过。
- **[v1.8.2](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.2)** — **修掉「本地版本显示 3.8.14」**：代码基线早就是 v3.8.15（`config.py::version`、启动日志、应用内「关于」页都是 3.8.15），但**启动器**（ok-ww.exe）读的是 `data/apps/ok-ww/app.json` 里的 `current_version`，那里还留着装 3.8.14 时的值。除了显示不对，它还让启动器以为"可以更新到 3.8.15" —— **一旦点更新，官方代码会覆盖 `working`/`repo`，整套定制全丢**。现在 `restore.py` 每次部署都会把 `app.json.current_version` 对齐到 `config.py::version`（改前自动备份 `app.json.<时间戳>.bak`），9 项单测覆盖（版本不同改写、相同不动、无文件/坏 JSON 安全跳过）。
- **[v1.8.1](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.1)** — **修正远控/串流窗口的入口位置说明**：它是左侧导航栏「游戏」分组里的独立页（图标=显示器），**不在「设置」页里**（`show_at_tab` 配置项会被设置页主动跳过），此前文档写的「设置 → …」让人找不到；同时修掉配置名含 `/` 导致配置被写成 `configs/远控/串流窗口.json` 子目录的问题（改为 `远控串流窗口(试验性)`，文件落回 `configs/` 根下），`MuMu/安卓 Config` 一并改为 `MuMu 安卓 Config`，并加单测禁止全局配置名再出现斜杠。
- **[v1.8.0](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.8.0)** — **试验性支持把远控 / 串流软件窗口当 PC 设备**（UU远程、ToDesk、向日葵、Parsec、Moonlight）：设置里「远控/串流窗口(试验性)」填窗口标题关键字，设备下拉即出现该窗口，走 windows 抓屏 + Pynput 真实键鼠，与 PC 客户端同一条链路；启动时校验客户区 16:9 并禁用自动 resize，比例不对会给出实际尺寸与修正建议。附带完整的硬性要求（被控电脑游戏全屏 16:9、远控画质原画、窗口前台、管理员运行、鼠标绝对定位）。
- **[v1.7.0](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.7.0)** — **把 MuMu / 安卓模拟器支持加回来**（官方 v3.8.15 基线不变）：设备下拉重新出现模拟器，抓屏默认 MuMu IPC（全黑帧自动重连），键位由模拟器映射转发（esc→返回/菜单、F1-F12、A-Z、0-9、反引号），断线弹窗自动确认重登，编队识别改为「手填编队 > 缩放识别投票锁定」并在战斗期零识别；**拉海洛方块支持 MuMu**（模拟器窗口 Pynput 输入 + 返回键兜底），无尽模式与关卡页直接启动一并可用。
- **[v1.6.0](https://github.com/Jn6661314/ok-ww-cloud-custom/releases/tag/v1.6.0)** — **以官方 v3.8.15 为基线重建**：官方已原生支持云鸣潮，`DailyTask` 只注册一次并按所选设备自动区分操作，因此删除我们自建的「云每日 / 云多账号 / 保存 Cookie / 切换账号」四个任务（旧配置里的任务名仍可被读取）。UID 遮罩改走框架通用 `blur_area`（该能力官方 ok-ww 早已自带，我们只是把遮挡区域调得略大；与 WebRTC 视频流捕获兼容，设置里可选 Blur / Inpaint），框架侧不再有任何游戏专用注入；多账号任务内新增「保存登录状态」「切换账号」两个按钮，**仅云设备下显示**；拉海洛方块按官方新版部署并保留 4 块托盘搜索预算修复。MuMu / 安卓定制整支保留在 `legacy-mumu-v1.5.21` 分支，本版不包含。
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

| 能力 | 官方 v3.8.18 | 本仓库 v1.8.27 |
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
