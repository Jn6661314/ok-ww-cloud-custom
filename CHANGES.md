# 更新内容明细

按功能分组列出相对于上游 `ok-oldking/ok-wuthering-waves` 的全部定制改动。
日期为 2026 年 11 月。所有条目均已在运行目录实际验证。

## 一、云鸣潮基础支持

- 从上游 Git 历史恢复"云鸣潮"设备入口与启动逻辑（`config.py`）。
- 为云游戏浏览器增加 per-account Cookie profile：`data/cloud_profiles/<账号>/storage_state.json`，各账号登录态隔离，不串号。
- 修复浏览器不会自动启动的问题。
- 修复云游戏必须鼠标点击浏览器窗口才能在后台运行的问题（浏览器捕获模块伪装 + 后台交互）。
- 修复拉海洛方块任务在云游戏浏览器模式下不工作的问题：浏览器模式跳过 hwnd 前台检查，改用 `BrowserInteraction`。
- 新增等待与识别"进入云游戏完成"的检测，避免还没进游戏就开始跑任务。

## 二、云每日与云多账号任务

- 新增 `CloudDailyTask`：单纯的单账号云每日任务，继承 `DailyTask` 的全部复选框开关。
- 新增 `CloudMultiAccountTask`：继承 `MultiAccountDailyTask`，有"配置账号"按钮，支持**每个账号独立配置**，按账号顺序切换 Cookie 登录态执行。
- 修复多账号每日任务嵌套 `super()` 导致的反复报错（先绑定 `daily_run = super().run` 再调用）。
- 修复账号切换串号：不再往运行中的页面注入 Cookie，而是关闭旧浏览器、用目标账号 profile 启动全新实例。
- 新增"💾 保存云鸣潮账号 Cookie"与"🔄 切换云鸣潮账号（重启浏览器）"两个一次性任务，可手动维护登录态。

## 三、任务错误恢复

- 新增 `run_with_cloud_recovery()`：任务出错不再直接停止，先尝试恢复再重跑。
- 恢复策略：优先调用 `restart_browser()` **真正重启浏览器**并用当前账号 Cookie profile 打开；失败再回退 `restart_page()` / `reload_page()`；仍失败才停止。
- 错误恢复传 `save_previous=False`，避免重启过程中卡在保存 Cookie。
- 同一错误连续出现达到上限（3 次）时提前停止，避免无限刷新。
- 用户主动停止（`TaskDisabledException`）不触发重试。
- 可通过配置 `Cloud Restart Browser On Error: False` 退回只刷新页面的旧行为。

## 四、进入游戏与领取修复

- "开始游戏"有时要点两次才能进入：固定 60 秒冷却改为分级冷却 `0 / 8 / 30 / 60` 秒，并按点击次数重置。
- 修复先约电台无法唤起导致领不到奖励的问题：浏览器模式不用 Alt，改为直接点击候选坐标，终端 OCR 作兜底；PC 模式保留 Alt。
- 修复每日活跃度检查：多区域多次 OCR；识别不到时返回 `None` 并跳过体力判断，不再误判为 0。
- 修复邮箱奖励被误判为月卡奖励导致卡死：已登录且不在月卡窗口时跳过月卡检测，并确保 `back()` 关闭邮箱界面。

## 五、多账号配置持久化

- 修复"保存好配置、重启软件后消失"的问题：
  - 原逻辑把"任务已启用/排队"误判成"正在运行"，保存时静默跳过；改为只在 `task.running` 为真时锁定编辑。
  - 配置文件相对路径改为解析到应用实际工作目录，不受快捷方式/计划任务启动目录影响。
  - 每次保存同步写 `MultiAccountConfig.backup.json`，主文件损坏时自动回退。
  - store 或编辑器未就绪时改为按需初始化/加载，失败明确提示而不是无声失败。
- 保留 `Farm Nightmare Nest for Daily Echo` 等复选框的自主控制权：早期版本曾强制关闭（只做每日/周常），现已去掉清洗逻辑，勾选即生效，默认开启；安装脚本不再改写用户已保存的开关。

## 六、历史功能回归：编队自定义轴与队伍工坊

- 从上游删除提交 `d0a59291` 的父版本恢复以下文件并适配新版 GUI：
  - `src/gui/CharacterCodeTab.py`：角色代码页面，按队伍给 3 个角色分别编辑代码（自定义轴），内置/导入切换，保存热加载，导出/导入队伍 zip。
  - `src/char/CustomCharLoader.py`：自定义队伍代码存储于 `configs/custom_teams`，zip 校验导入，动态类热加载。
  - `src/char/CharFactory.py` + `src/task/BaseCombatTask.py`：认出完整三人队后应用自定义角色类，让代码真正生效。
- `config.py` 重新注册 `custom_tabs`，主界面出现"角色代码"页；页面内含"工坊/队伍"按钮，可浏览全部队伍、搜索筛选、查看详情、一键导入。
- 为新版 ok-script 3.0.7 增加 `tr()` 覆盖与中文 fallback 字典，补回上游删掉的中文文案。
- 未恢复旧的 `CharacterCodeTask.py` / web 资源：新版框架已无 `WebCustomTab`，Qt 页面本身已含工坊功能。

## 七、工坊服务器下线后的离线回退

- 上游工坊域名 `cfokwwchar.ok-script.com`（DNS 失效）与 `okwwcharcode.ok-script.com`（仅剩 GitHub Pages 404）均已下线，点工坊会报"工坊错误"。
- `CharacterCodeTab.py` 改为在线失败自动回退本地快照：
  - `fetch_all_workshop_teams()` 读 `configs/workshop_cache/teams.json`；
  - `fetch_workshop_codes()` 读 `configs/workshop_cache/teams/<slug>.json`；
  - 下载代码包失败时从 `configs/workshop_cache/codes/<filename>` 读取 zip 导入。
  - HTTP 404 仍按空列表处理，保留原有语义。
- 离线快照来自社区公开镜像 `yamadafz/ok-ww-char-code`：50 个队伍 / 72 个配置。
- 仓库随附文本索引，代码包可用 `tools/download_workshop_cache.py` 拉取；安装/恢复脚本会自动把快照放进 `configs/workshop_cache`，不触碰 Cookie 与自定义队伍。

## 八、备份与一键恢复

- 建立独立的定制备份（不在 ok-ww 安装目录内，不会被自动更新覆盖）。
- `restore.py` / `一键恢复.bat`：把所有定制文件同时恢复到 `working` 与 `repo` 两处，恢复前自动备份当前文件到带时间戳的目录。
- `install_to_local_app.py`：大版本升级后用源码级副本重新打补丁，全部操作幂等。
- 账号 Cookie（`cloud_profiles`）与任务配置（`configs`）始终排除在备份/恢复之外。

## 九、2026-11-23 新增：故障方块与 UID 遮罩

- **拉海洛方块·逆转 支持"故障方块"新机制**（1 级 / 2 级故障）：
  - 视觉识别：按教程图校准的故障特效特征（亮粉色噪点，BGR ≈ 242/105/207，覆盖约 90% 方块面），普通紫/蓝/橙/白图标方块不会误判（`rahai_blocks._fault_mask`）。
  - 消除模拟：故障方块与数据损坏方块一致——参与凑满行列消除但自身留在棋盘上，故障解除后重新读盘自动转为普通方块参与后续消除（`clear_lines(mask, fixed, fault)`）。
  - 落块验证放宽：故障解除残留、爆炸方块引爆导致的棋盘偏差不再中断挑战，改为告警并以重新读取的实际棋盘继续。
  - 教程翻页识别新增"故障方块""爆炸方块"标题，开局说明页可自动跳过。
  - 合成图像单测 `tests/TestRahaiFaults.py` 全部通过（视觉识别、消除模拟、规划器集成）。
- **云鸣潮 UID 遮罩**：
  - 云游戏浏览器启动时注入持久遮罩层（`add_init_script`），盖住右下角 UID 区域（与 PC 端 `paint_uid_cover` 相同比例：宽 13% × 高 2.5%）。
  - `pointer-events:none` 不影响鼠标点击；页面跳转后自动重新生效；CDP 截图中同样被遮住。
  - 设备配置 `cover_uid` 可关闭（默认开启）。

## 十、2026-11-23 修复：通关后活动主页卡住与玩法说明弹窗

- **通关后退回活动主页需要手动点「立即前往」**：
  - 通关结算后游戏可能直接退回活动主页而不是关卡详情，任务此前会报"领取奖励后无法识别关卡详情"并停止。
  - 新增 `_go_now_button()` OCR 识别「立即前往」，在 `_challenge` 领奖后与 `_return_to_list` 中自动点击返回关卡列表；若直接回到关卡列表也能正常继续。
- **玩法说明弹窗（如"1 级故障方块"）不会关闭**：
  - 抽出 `_close_help_popup()`：检测到说明弹窗后先点右上角 X（归一化坐标 0.960/0.210），无效再依次用「确认」按钮、"切换至最后一页"跳转兜底。
  - 挑战过程中弹出的说明弹窗（如故障方块首次出现时）此前会导致"棋盘消失"误报，现在下棋循环中检测到弹窗会自动关闭并继续。

## 十一、2026-11-23 上游 PR 提交情况

本仓库的定制改动已按主题拆分为 4 个互相独立、可单独合并的上游 PR（均通过 CI，SonarCloud Quality Gate OK）：

- **[ok-wuthering-waves #1873](https://github.com/ok-oldking/ok-wuthering-waves/pull/1873)**：云鸣潮支持与多账号 Cookie 隔离（对应本仓库第一~八章内容：`CloudDailyTask`、`CloudMultiAccountTask`、云账号切换/恢复等 13 个文件）。
- **[ok-wuthering-waves #1874](https://github.com/ok-oldking/ok-wuthering-waves/pull/1874)**：拉海洛方块·逆转的故障方块支持（`rahai_blocks.py` 视觉识别与消除语义、`RahaiBlocksTask.py` 接入、`tests/TestRahaiFaults.py` 单测，对应第九章第一部分）。
- **[ok-script #130](https://github.com/ok-oldking/ok-script/pull/130)**：云鸣潮 UID 遮罩（`ok/device/capture_methods/browser.py` 的 `cover_uid` 配置与遮罩层注入，对应第九章第二部分）。UID 遮罩所属的 `browser.py` 是 ok-script 包文件（ok-ww 仓库本身不含 `ok/` 目录），故提到 ok-script。
- **[ok-script #131](https://github.com/ok-oldking/ok-script/pull/131)**：浏览器捕获的每账号独立 profile、登录态持久化与后台输入伪装（`user_data_dir` 配置支持路径/可调用对象 + `OK_WW_CLOUD_PROFILE` 环境变量兜底；关闭前保存 `storage_state.json`、启动时恢复 cookies 与 localStorage；`background_input` 后台输入伪装，默认开启）。这是第一~二章云多账号 Cookie 隔离在 ok-script 侧的配套改动。

说明：

- 四个 PR 互不依赖；#130 与 #131 都改 `browser.py`，先合并者另一方需 rebase（改动区域不同，冲突易解）。
- 在 PR 被合并前，上述能力仍以本仓库快照形式提供（`ok/device/capture_methods/browser.py` 即含 UID 遮罩、账号 profile、后台输入三块补丁的完整定制版，`restore.py` / `一键恢复.bat` 会把它恢复到 ok-script 安装位置）。

## 十二、2026-11-23 新增：本地安卓模拟器（ADB）设备入口

- `config.py` 新增 `adb` 配置节，设备选择列表里会出现已安装的安卓模拟器（如 MuMuPlayer 12）与 USB / 无线 ADB 设备：
  - `packages` 同时包含国服 `com.kurogame.mingchao` 与国际服 `com.kurogame.wutheringwaves`，框架按实际安装的游戏自动选择并拉到前台。
  - `capture_method` 默认 `'adb'`（通用截图，后台可用但约 300ms/帧）；**MuMuPlayer 12 用户可在设备连接弹窗的"捕获方式"里切换到 `Ipc`**，走模拟器原生截图通道，速度快得多。
  - 点击方式为框架自带的 `ADBInteraction`（`adb input` / 可选 uiautomator2），无需改动任务代码。
- 运行环境需要 `adbutils`（安装版 Python 自带环境如缺失，执行 `python -m pip install adbutils`）；adb.exe 由 adbutils 自带，无需单独安装 Android SDK。
- 实测：本机已装的 MuMuPlayer-15.0-0（`127.0.0.1:16384`）能被设备管理器正确识别，模拟器开机后即可连接。
- 注：这是"多一个设备入口"，任务里的浏览器/PC 专用判断逻辑未改动；ADB 设备上的完整任务流程（尤其实时战斗循环）请自行实测。

## 十三、2026-11-24 修复：云鸣潮战斗不使用工坊参数 / 乱切人

两个问题同源：云鸣潮抓的是 WebRTC 视频流（H.264 + 4:2:0 色度抽稀），角色头像/文字模板与协奏环颜色识别都会抖动。而工坊队伍代码的接入逻辑对识别结果有"全有或全无"的强依赖，某一帧认错就把整队工坊代码丢掉，角色类型退回默认 `MAIN_DPS`、切人优先级走内置默认，于是表现为"工坊参数没生效 + 乱切人"。

- **工坊队伍代码每轮被退回内置类（核心 bug）**：工坊队伍代码是内置角色类的"兄弟"类（同名、都直接继承 `BaseChar`，不是内置类的子类），`CharFactory.get_char_by_pos` 里的 `isinstance(old_char, cls)` 对工坊实例恒为 False，导致每轮识别都把工坊实例用内置类重建，工坊自定义战斗逻辑/切人优先级全部丢失。改为按类名判断（`old_char.name != cls.__name__` 才重建），自定义类同名即保留，真正换角色才重建。
- **单槽位识别失败导致整队工坊失效**：`apply_team_char_classes` 原来是"全有或全无"——只要有一个角色认不出（`char_name='unknown'` / 人数≠3）就整体跳过，另外两个认出的角色也拿不到工坊代码。现在在 task 上缓存每个槽位上一轮的身份 `{index: (canonical_name, builtin_cls)}`，某帧认不出时用缓存身份补全，工坊代码仍应用到全队；缓存是 per-task 的，云多账号各实例互不干扰。
- **协奏环颜色在云流下失准**：`con_colors` 每个通道区间仅约 30 宽，4:2:0 压缩后颜色偏移导致协奏值算错 → intro 预判错 → 乱切人。云浏览器模式下对每个通道区间向外放宽 `CLOUD_CON_COLOR_TOLERANCE`（默认 10，可在 `BaseCombatTask.py` 顶部调整）用于环颜色统计与属性索引推断；本地客户端不走此分支，识别行为零变化。
- 验证：`tests/TestCloudCombatFixes.py` 4 项单测（工坊类保活、缓存补全、颜色容差仅云模式生效）全部通过；原有 `TestCustomCharLoader.py` 26 项无回归。
- 说明：颜色容差默认值是按经验设的保守值。若云游戏上仍有协奏环误判，请提供对战中"协奏环非满 / 技能冷却中 / 大招可用"的截图，据此微调 `CLOUD_CON_COLOR_TOLERANCE` 或各属性区间。本次修复未提上游 PR，仅更新本仓库与本地运行版。

## 十四、2026-11-24 修复：无怪物仍自动战斗 + Win10 云鸣潮兼容

- **无怪物时自动退出战斗**（`src/combat/CombatCheck.py`）：新增无怪物看门狗，连续 2 秒既没有锁定目标、也看不到血条即判定怪物已死亡/消失并退出战斗。血条因云游戏压缩闪烁时不会无限续命；深渊挑战强制战斗窗口与大招动画期间不触发，避免误伤。
- **大招标志残留**（`src/task/BaseCombatTask.py`）：`send_key_and_wait_animation` 超时时 `_in_liberation` 可能仍为 True，导致 `in_combat()` 永远返回 True、战斗退不出去。超时处补上清理。
- **Win10 云鸣潮**（`ok/util/window.py`、`ok/device/capture_methods/windows_graphics.py`、`config.py`）：WGC 可用性门禁原用 Win11 的「无边框」版本 20348，实际 WGC 从 Win10 2004（19041）起就可用；改为按 19041 判断并保留 COM 组件运行时探测。抓屏去黄色边框的设置也放宽到 Win10 尝试执行并加好退处理。设备标签更新为「需要Win10 2004+或Win11」。
- 验证：模拟 19041 / 19045 / 22621 三个版本号，云模式均可用；语法检查通过；看门狗定向测试通过。本机为 Win11，Win10 实机效果待用户确认。

## 十五、2026-11-24 补充修复：MuMu 触屏模式的 esc 返回键

- **问题**：ADB/MuMu 触屏操作模式下，业务代码里大量 `send_key('esc')`（返回/关闭界面）被映射成 `KEYCODE_ESCAPE`，鸣潮手游不响应该键，导致日常任务卡在菜单、无法返回。
- **修复**（`ok/device/interaction_methods/keys.py`）：`ADB_KEY_MAP['esc']` 由 `KEYCODE_ESCAPE` 改为 `KEYCODE_BACK`（安卓返回键）。该映射表仅 ADB 交互使用，PC（PostMessage/Pynput）与云游戏浏览器模式均不受影响。
- **验证**：语法检查通过；映射断言 `ADB esc == KEYCODE_BACK` 且 `PC vk ESC == 27`（未改动）通过；两个备份恢复清单完整性检查通过。
- 说明：这是触屏适配的第一步（低风险的「返回/关闭」类）。「打开菜单/战斗技能点按屏幕」需要标定触屏坐标，尚未实现。

## 十六、2026-11-24 补充：ADB 触屏键位表补全（A-Z / 0-9 / 反引号）

- **背景**：用户提供了鸣潮安卓版操作键位表（WASD 移动、Q/E/R 技能、F 交互、M 地图、C 角色、1~2 切人、`` ` `` 菜单/跳过等），据此核对代码实际发送的按键。
- **根因**：`ADB_KEY_MAP` 只定义了 esc/enter/space/方向键/修饰键等，`src/` 里用到的 8 个字母键（f/m/z/w/r/d/c/a）没有映射，在 ADB 交互下被原样透传成 `input keyevent f` 这类非法命令，安卓不认识小写键名，游戏收不到任何事件——这才是日常任务在 MuMu 触屏模式下大面积失效的主因，比 esc 问题更严重。
- **修复**（`ok/device/interaction_methods/keys.py`）：补全 a-z → `KEYCODE_A`..`KEYCODE_Z`、0-9 → `KEYCODE_0`..`KEYCODE_9`；反引号 `` ` ``/grave/backtick → `KEYCODE_GRAVE`（用户明确指出菜单/跳过是反引号而非 esc）。此表仅 ADB 交互使用，PC 与云游戏浏览器模式不受影响。
- **验证**：代码用到的 13 个键现全部映射为合法 keyevent；`ADB['f']==KEYCODE_F` / `ADB['esc']==KEYCODE_BACK` / `ADB['\`']==KEYCODE_GRAVE` 断言通过；PC 端 `vk_key_dict['ESC']==27` 未改动；语法检查与两处恢复清单完整性通过。
- 仍待触屏实测：MuMu 的 ADB 调试端口本机连不上（16384/7555 拒绝），无法实测按键是否真正驱动游戏；若补全后仍无反应，需要开 ADB 调试或游戏截图进一步定位（可能要走坐标点击而非 keyevent）。

## 十七、2026-11-24 完整更新到官方 v3.8.14（ok-script 3.0.13 WebRTC）

- **官方新特性**：云游戏抓屏从「截浏览器窗口（WGC）」改为「直接读游戏视频流（WebRTC）」，浏览器最小化也可截图；浏览器启动失败后重启无需重启 ok-ww；任务出错保存截图到 `screenshots/error/`；拉海洛方块落点预览不匹配不再每次截图。官方改动 13 个文件（含新增 `ok/device/capture_methods/browser_webrtc.py`）。
- **冲突分析**：13 个改动文件中 3 个与定制重叠——`config.py`、`ok/device/capture_methods/browser.py`、`src/task/RahaiBlocksTask.py`。`browser.py` 官方改 182 行并新增 WebRTC 模块，定制改 87 行（Cookie/账号 profile、后台输入伪装、UID 遮挡），自动三方合并失败，改为以官方新版为底逐块手工移植。
- **合并结果**：
  - `browser.py`：官方 WebRTC 代码 100% 保留，移植 5 处定制（两个 JS 常量、per-account user_data_dir、storage_state 恢复 + 后台/UID init script、复用页面 evaluate、storage_state 保存）。与官方新版差异仅 5 处新增块，无官方代码删除。
  - `config.py`：以 v3.8.14 官方版为底，保留官方 `'capture': 'webrtc'`，加回 custom_tabs、adb 段、user_data_dir、nick、云多账号任务列表。
  - `RahaiBlocksTask.py`：以定制版（含 `_go_now_button`、云恢复、浏览器交互）为底，同步删除官方那行 `screenshot("rahai_preview_mismatch")`。
- **更新动作**：repo 快进到官方 `e2cc611`（v3.8.14），官方非冲突文件（CHANGELOG/README/TaskExecutor/layout/browser_webrtc）保持纯官方内容；24 个定制文件写回 working/repo 并同步两套备份；`app.json` 版本 v3.8.13→v3.8.14，复位 update_state。
- **备份**：两个 restore.py 清单新增 `browser_webrtc.py`（合并版 browser.py 依赖它，避免恢复到旧环境时导入失败）。custom-backup 现 24 项，cloud-custom 现 23 项。
- **验证**：关键文件语法编译通过；browser.py 与 browser_webrtc.py 可正常 import；config 加载确认 version=v3.8.14 / capture=webrtc / 云任务齐全；24 个定制文件 working/repo/备份三处 md5 一致；两个恢复清单完整且语法正确；官方非冲突文件哈希与 e2cc611 一致（未被定制污染）。
- **注意**：WebRTC 抓屏与旧 WGC 的视觉表现不同（只抓视频流、页面元素周围为黑），且本机未登录云游戏、无 MuMu ADB 连接，无法实测云鸣潮在 WebRTC 下的抓屏/切号/后台表现。如遇异常，可把 `config.py` 里 `'capture': 'webrtc'` 改回 `'wgc'` 并重启（定制的后台伪装仍生效）。
