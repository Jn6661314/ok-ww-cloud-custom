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

## 十八、2026-11-24 补充：MCP 端口冲突自适应

- **修复 MCP 服务器开启报 `[Errno 13]`**（`ok/core/mcp_server.py`）：本机百度输入法（`BaiduPinyin.exe`）常驻监听 `0.0.0.0:8765`，OKWW 绑 `127.0.0.1:8765` 时 Windows 返回 `EACCES(13 / winerror 10013)`，而非通常的 `EADDRINUSE(10048)`；原 `bind_mcp_socket` 只认后者，直接把 EACCES 抛出，GUI 弹"MCP 服务器错误"。现把 `EACCES/10013` 一并视作端口冲突，自动递增到可用端口（实测 8765 冲突→8766 绑定成功）。实际端口经 `getsockname()` 写回 connection 文件，客户端动态发现，无需改配置、也无需关闭输入法。
- **恢复清单**：cloud-custom 的 `restore.py` 新增 `ok/core/mcp_server.py`（现 24 项），避免后续更新/恢复把该修复覆盖；清单完整性检查通过。
- **关于"MuMu 打开菜单"的实测结论（未改动代码）**：通过 MCP 在 MuMu/ADB 下实测——反引号 `` ` ``（KEYCODE_GRAVE）会触发剧情/过场（即键位表里的"跳过"语义），返回键 KEYCODE_BACK 在主界面会弹"是否确定退出游戏？"对话框。二者都不是"打开系统菜单"，因此撤销了先前把 `is_main` adb 分支改成发反引号的改动，恢复原 `back()`。触屏版"打开菜单"的正确操作仍需确认（可能是点屏幕上的终端/菜单按钮），确认后再做。

## 十九、2026-11-24 补充：安卓触屏专用操作模式层

- **新增 `src/task/touch_mode.py`（安卓键位模式层）**：把散落在各 task 的 `is_adb()/is_browser()` 判断与触屏键位集中到一处。核心原则（按用户确认）：安卓端「返回」和「打开菜单」**是同一个按钮**，就是键位表里的"菜单/跳过"键 `` ` ``（→ `KEYCODE_GRAVE`），不是 `KEYCODE_BACK`（实测主界面发 `KEYCODE_BACK` 弹"是否确定退出游戏"）。`TouchMode` 提供 `is_touch/is_cloud`、`back()/open_menu()`（触屏发 `` ` ``，PC/云维持原 `back()`=esc）、`book_key()`（触屏 F2）。`BaseWWTask` 持有 `self.touch`，PC/云行为零变化。
- **接入点**（`src/task/BaseWWTask.py`）：`is_main(esc=True)` 的返回分支、`open_esc_menu()`（触屏不再做 PC 式 Alt+点击）、`openF2Book()` 的指南书键，均改走 `self.touch`。`setup` 时在 `__init__` 创建助手。
- **补全触屏功能键**（`ok/device/interaction_methods/keys.py`）：`ADB_KEY_MAP` 新增 `F1-F12 → KEYCODE_F1..F12`，使触屏指南书 `F2` 合法；此前已补 `A-Z/0-9/` `` ` ``。
- **恢复清单**：`restore.py` 新增 `src/task/touch_mode.py`（现 25 项），避免后续更新覆盖；三处目录（working/repo/补丁仓库）一致，语法检查通过。
- **说明**：本模式层已把"返回/菜单"语义键位集中，`wait main` 在 MuMu 下将发 `` ` ``；此前误判 `` ` `` 触发剧情的那次实为登录超时重连载入画面（用户澄清）。未再实机验证（游戏处于超时重载，避免继续操作导致会话中断），需下次在线时确认。

## 二十、2026-11-24 补充：MuMu 模拟器窗口化操作（PC 式输入）

- **问题本质（用户指正）**：MuMu 模拟器就是一个 Windows 窗口，用户已在模拟器里把游戏键位映射配好。而 OKWW 对 adb 设备固定用 `ADBInteraction`（`input keyevent`/`input tap`）——这是直接给安卓系统发按键，**完全绕过模拟器的键位映射**：`KEYCODE_BACK` 在主界面弹"是否确定退出游戏"、键位表里的 `` ` ``（菜单/跳过）从未生效。正确做法是与 PC 客户端/云游戏一致：向模拟器窗口发真实键盘/鼠标消息，由模拟器键位映射转成游戏操作。
- **框架改动**（`ok/device/DeviceManager.py`）：`do_start` 的 adb 分支原本无条件强制 `ADBInteraction`，现尊重显式配置的 interaction（`config['interaction']` + `win_interaction_class`，且需 `hwnd_window` 存在），未配置时保持原行为，对其他用户零影响。
- **配置改动**（`config.py` adb 段）：`capture_method: 'windows'`（MuMu 窗口截图，走 WGC）+ `interaction: 'PostMessage'`。键盘按键（esc、`` ` ``、f2、WASD 等）经 `vk_key_dict`/`VkKeyScan` 转 VK 码 PostMessage 给 MuMu 窗口；鼠标点击由 MuMu 转成触屏 tap。
- **连带修复**：`MouseResetTask` 在 adb 下每 10 秒刷的 `'ADBCaptureMethod' object has no attribute 'get_abs_cords'` 随截图通道切到 PC 侧而消失（`BaseCaptureMethod` 本有该方法）。
- **TouchMode 兼容**：`src/task/touch_mode.py` 发的 `` ` ``/`f2` 在 PostMessage 下同样合法（VkKeyScan 转 VK 码），语义键位无需修改；`ADB_KEY_MAP` 保留给仍选 ADBInteraction 的场景。
- **恢复清单**：`restore.py` 新增 `ok/device/DeviceManager.py`（现 26 项）。三处目录一致，语法检查通过。生效需重启 OKWW。

## 二十一、2026-11-24 补充：安卓每日任务"卡在大世界不动"的根因修复

### 21.1 根因复盘

用户反馈："mumu链接有问题，日常专属任务进入大世界以后一直卡在那不动，也不跳过也没其他操作也没额外日志输出"。

日志证据链（`working/logs/ok-script.log`）：

```
18:03:50  AndroidDailyTask: current task wait main esc=True
18:13:24  wait_until timeout <bound method BaseWWTask.in_team_and_world> 10 seconds
18:13:51  wait_until timeout <function BaseWWTask.ensure_main.<lambda>> 600 seconds
18:13:51  错误 请在大世界并在队伍中开始!
```

`wait main` 到超时恰好 **601 秒**，与 `ensure_main` 在未登录态把 `time_out` 提到 600 秒完全吻合。

真正的断点在 `in_team()`：PC 端用右上角队伍栏的 `1/2/3` 数字徽章（`char_1_text`/`char_2_text`/`char_3_text`）判定"在队伍中"，但**安卓客户端的队伍栏是圆形角色头像，没有数字徽章**。复刻 `FeatureSet.find_one_feature` 的区域约束匹配后实测：

| 模板 | 安卓大世界实测置信度 | 阈值 |
| --- | --- | --- |
| `char_1_text` | 0.150 | 0.8 |
| `char_2_text` | 0.115 | 0.8 |
| `char_3_text` | 0.129 | 0.8 |

三个模板全部落空 → `in_team()` 恒 False → `in_team_and_world()` 恒 False → `is_main()` 恒 False → `ensure_main()` 必然 600 秒超时。

同时确认**没有任何现成模板可复用**：对 301 个模板做区域约束扫描与全图扫描，安卓大世界最佳匹配仅 0.615（且是角色专属模板），无法通用。因此判定必须走代码判据。

### 21.2 新增 `src/task/android_world.py`（安卓专用大世界判定）

用与角色/场景无关的 HUD 元素判定，阈值全部来自真实帧标定：

| 判据 | 大世界实测 | 加载界面 | 活动页 | 登录页 | 全黑帧 | 阈值 |
| --- | --- | --- | --- | --- | --- | --- |
| `radar_yellow`（左上雷达黄色玩家箭头） | 339 / 347 | 0 | 29 | 0 | 0 | ≥120 |
| `ult_orange`（底部偏左协奏金球） | 534 / 717 | 0 | 0 | 0 | 0 | ≥300 |
| `party_white`（右上队伍栏白条） | 815 / 1057 | 215 | 619 | 208 | 0 | ≥600 |
| `hp_bar_white`（底部共鸣者血条） | 3023 / 2877 | 2240 | 0 | 1073 | 0 | ≥2200 |
| `loading_bar`（底部最长连续白像素） | 93 / 94 | **1313** | 381 | 74 | 0 | ≥800 判为加载中 |

判定规则：

1. 全黑帧 → 直接判否并单独告警（区别于"不在大世界"）。
2. `loading_bar ≥ 800` → 判否（加载界面）。
3. `radar_yellow ≥ 120` 或 `ult_orange ≥ 300` → 判真。
4. 兜底：`party_white ≥ 600` **且** `hp_bar_white ≥ 2200` 同时成立才判真。

> **踩过的坑**：最初只按"白像素总数"判血条，结果**加载界面被误判成大世界**（加载进度条 2240 ≥ 2200）。逐行分析后发现加载进度条是 **y=1021~1027 单行、贯穿全屏（连续 1299 px）** 的细条，而大世界血条是 **两段 85 px 的短条**（中间有刻度分隔）。改用"单行最长连续白像素长度"后两者彻底分开（1313 vs 93），阈值 800 落在活动页 381 与加载页 1313 之间，两侧都有 2 倍以上余量。

### 21.3 `src/task/BaseWWTask.py` 改动

- `in_team()` 开头加 `if self.is_adb(): return self.in_team_android()`，PC 分支逻辑一行未改。
- 新增 `in_team_android()`：调用 `android_world.in_android_world()`，返回同构三元组 `(是否在队伍, 当前角色下标, 队伍人数)`。安卓端无法可靠区分出战角色下标（头像与 PC 徽章布局不同），队伍人数按"至少 1 名"处理，战斗切人逻辑退化为不切人。
- **补日志**：PC 分支三个模板全落空时原先**完全静默**，现在打印各模板实际置信度；安卓端打印 `in_team(android): in world (radar_yellow=347)` / `not in world (...)`，黑帧单独 warning。

### 21.4 `ok/device/capture_methods/nemu_ipc.py`（MuMu 抓屏黑帧拦截）

- 背景：MuMu IPC 通道偶尔"返回成功但画面全黑"（实测 `mean=0`，`max=0`，非零像素占比 0；18:13:51 的错误截图与 18:57 两张截图都是纯黑，等于没有任何现场信息）。上层拿到黑帧会认为画面正常，于是模板全不命中，表现和"不在大世界"一模一样。
- 处理：全黑帧先**重建 IPC 连接重试 3 次**（每次间隔 0.5 秒），仍失败抛带明确中文原因的 `CaptureException`；底层 `@retry` 耗尽后抛的是不带 message 的裸 `Exception`，这里补上"请确认模拟器正在运行、窗口可见、未开启后台保活"等可读原因。
- 判定阈值：整帧 `max ≤ 8` 视为空画面（正常画面即使只有一个非黑像素也不会误判）。

### 21.5 新增安卓端"连接已断开"弹窗处理

- 场景：MuMu 挂机过久或网络抖动，游戏弹【连接已断开】对话框（"已与服务器断开连接，请尝试重新登录"）。此时**画面背后仍然是大世界**，`in_team` 判定依然为 True，任务以为一切正常，但所有点击都被弹窗挡住——与用户反馈的"卡住不动"完全一致。
- 处理（`BaseWWTask.handle_android_disconnect()`，在 `is_main()` 里**先于**大世界判定执行）：
  1. 廉价亮度预筛：中央区域亮像素（灰度 > 200）占比 ≥ 0.5 才继续（实测弹窗 0.777，其余画面 ≤ 0.101），避免每次 `is_main` 都跑 OCR；
  2. OCR 确认文案命中 `连接已断开|断开连接|重新登录`（实测置信度 1.0）；
  3. 点掉弹窗底部的「确认」，复位 `logged_in = False`，交给既有 `wait_login` 重新登录。
- PC / 云游戏完全不受影响（`is_adb()` 为假直接返回）。

### 21.6 恢复清单与验证

- `restore.py` 的 `RELATIVE_FILES` 新增 `src/task/android_world.py` 与 `ok/device/capture_methods/nemu_ipc.py`（现 30 项），避免官方更新/恢复覆盖。
- 顺带修正：此前 `restore.py` 只在 17:47 同步过一次，仓库里 18:10 之后的 `BaseWWTask.py`（`back()`/`send_key()` 触屏语义统一）、`touch_mode.py`（`is_touch` 只在 `ADBInteraction` 下为真）、`AndroidDailyTask.py` 三处改动**并未生效到运行目录**，本次一并补齐。
- 实测验证：
  - MuMu 15.0 实机走通「连接页 → 点击连接 → 加载 → 大世界」；
  - 大世界判定对 **大世界×2 / 加载界面×1 / 活动页×1 / 登录页×3 / 全黑帧×3** 共 10 张带标注真实帧全部判对；
  - 断线弹窗处理 5/5 通过（真实调用应用配置的 `onnxocr` 走完整决策链，非 ADB 场景不误触发）；
  - 黑帧拦截 13/13 通过（黑帧判定边界、正常帧不误伤、先黑后好能自恢复、持续黑帧抛明确异常、裸 Exception 补可读原因）。
- 遗留：安卓端"当前出战角色下标"仍无法识别，战斗切人逻辑在安卓端退化为不切人，属已知限制。

## 二十二、2026-11-24 安卓端 F1/F2 改为直接点右上角图标

### 22.1 需求

用户反馈"F2 打开任务环节也有问题，任务在右上角图标里面"，并指出**该图标左边那个是活动**，
要求把 F2、F1 都改成在安卓版脚本里直接点击，不走按键。

### 22.2 触屏端没有 F1/F2

- PC 端 `F2` 打开「索拉指南」、`F1` 打开「活动」；安卓客户端触屏上没有这两个键，
  实测发 `KEYCODE_F2` 游戏无任何反应。
- 原 `openF2Book` 的分支是 `if self.in_team_and_world() and self.touch.open_book(): ... else: send_key('f2')`
  —— 安卓端一旦因为任何原因没走进点图标分支，就会掉进发键分支，然后白等
  `wait_book` 超时，最后抛"can't find gray_book_boss, make sure f2 is the hotkey for book"。

### 22.3 改动

**`src/task/touch_mode.py`**

| 常量 | 含义 | 归一化坐标 |
| --- | --- | --- |
| `TOUCH_BOOK_CLICK` | F2 索拉指南 → 右上角**方框书本**图标（第 2 个） | (0.7293, 0.0612) |
| `TOUCH_ACTIVITY_CLICK` | F1 活动 → 右上角**活动**图标（第 1 个） | (0.6813, 0.0602) |

新增 `open_activity()`；`open_book()` 保持不变。两者在非触屏下返回 `False`，
由调用方走按键 —— PC/云游戏行为不变。

**`src/task/BaseWWTask.py`**

- `openF2Book()`：安卓端**只走点击**，彻底去掉 `send_key('f2')` 回落分支；
  PC 端分支原样保留。
- 新增 `open_touch_book()`：点图标后用 `is_book_opened()` 确认书是否真的打开
  （书本来就开着时再点图标会把它关掉），没打开就补点一次，最多 12 秒。
- 新增 `touch_book_opened()`：用左列类别图标数量 + 竖向跨度判断书是否已打开。
- 新增 `find_android_book_tab()` / `get_feature_template()`：安卓端类别图标定位。
- 新增 `open_activity()`：F1 的安卓替代。
- `wait_book()`：安卓端改走 `find_android_book_tab`，PC 端保持 `find_one` + `box_gray_book`。

**`src/task/android_book.py`（新增）**

安卓索拉指南是移动端布局（左侧一列竖排类别图标 + 右侧列表），类别图标与 PC 模板
尺寸/位置都不同。**直接拿 PC 模板做 NCC 会命中背景空白** —— 实测在安卓书界面上：

| 模板 | NCC 最高分 | 命中位置 | 实际图标位置 |
| --- | --- | --- | --- |
| `gray_book_quest` | 0.712 | (48,156) | y≈191 |
| `gray_book_boss` | 0.741 | (44,283) | y≈322 |
| `gray_book_weekly` | 0.767 | (42,426) | y≈461 |
| `gray_book_all_monsters` | 0.822 | (39,695) | y≈727 |

最高分全部落在**模板自身锚点处的空背景**上而不是图标上 —— 定位失败，点下去也是错位置。

改用「**白色笔画二值掩码 + 多尺度 IoU 滑窗**」：

1. 屏幕左侧图标列窄条（x 为屏宽 1.5%~7.5%、y 为屏高 12%~73%）二值化成笔画掩码；
2. PC 模板同样二值化（灰度/笔画两种口径各一份），裁到笔画外接框；
3. 在 0.40~1.10 共 8 个缩放比例下，用积分图算**逐位置精确 IoU**，取全局最高分。

关键坑位：

- **纵向下界必须卡到屏高 73%**。屏幕下方有背景渐变，会变亮成一片白；二值化后整块全 1，
  任何模板都能在上面拿到 **IoU=1.0** 的假匹配（实测 `gray_book_all_monsters` 命中 y=844/1038）。
- **纵向上界要卡掉标题栏**（屏高 12% 以上），否则标题的"素材获取"图标会被当成类别图标。
- 模板与屏幕要用**不同口径**的掩码：屏幕侧用笔画掩码（`S<110 且 V>150`），
  模板侧同时试灰度掩码与笔画掩码，取分高者。

实测结果（真实安卓书界面）：

| PC 模板 | 类别 | 安卓左列命中 | IoU |
| --- | --- | --- | --- |
| `gray_book_quest` | 任务（菱形星标） | (76,191) | 0.78 |
| `gray_book_boss` | 首领（交叉双剑） | (77,322) | 0.86 |
| `gray_book_weekly` | 周常（循环徽章） | (76,461) | 0.88 |
| `gray_book_all_monsters` | 全部怪物（骷髅面具） | (80,727) | 0.90 |

### 22.4 验证

- 单元回归：`probe/test_android_book.py`（4 个类别全部对号入座 + 大世界画面不误报）、
  `probe/test_touch_book.py`（安卓端不发 F2 / 点图标 / 点到类别；PC 端仍发 F2/F1）—— 全绿。
- 回归既有套件：`test_android_world` 10/10、`test_black_frame` 13/13、`test_disconnect` 5/5 —— 全绿。
- **实机端到端**（MuMu 15.0，真实截图 + 真实模板 + 真实点击，无桩件）：
  「大世界 → 点右上角方框书本图标 → 索拉指南打开 → 自动定位并点击「任务」类别 →
  出现『活跃行迹 / 完成1次日常任务 0/1 / 活跃度 120』页面」全程走通。
- 附带确认：`DailyTask.open_daily()` 里紧接的 `click(0.17, 0.12)` 在安卓端正好落在
  「活跃度」标签页上，无需改动。

## 二十三、2026-11-24 补充：梦魇聚落打不开 / 登录黑屏冗余等待 / 安卓启动拉起鸣潮

### 23.1 梦魇聚落（残象聚落）点不开

- **根因是"传送按钮认不出来"，不是点击坐标错**。聚落条目点开后是「详情页 + 右下角黑底白字的**快速旅行**按钮」，
  而脚本只会找 `fast_travel_custom` / `gray_teleport` / `remove_custom` 三个 PC 模板。
  实测 1920×1080 云游戏与安卓截图上，这三个模板最高匹配度只有 **0.02 ~ 0.28**，远低于 0.7 阈值，
  `wait_feature` 直接抛异常 → 日志 `NightmareNestTask Failed`。
- **修复**（`src/task/BaseWWTask.py` 新增 `find_travel_button()` / `find_travel_button_by_ocr()` /
  `find_confirm_button()` / `find_confirm_button_by_ocr()`）：
  - 模板找不到时用 **OCR 认「快速旅行」**，实测 `onnxocr` 在右下角 `(0.7,0.89)-(1,1)` 区域置信度 **0.99998**。
  - 点完传送若弹确认框（`确认` / `確定` / `确定`）一并点掉。
  - 「按钮是否还在」的判定只对同名模板成立，OCR 按钮改为直接等回到大世界。
- **新增覆盖层文件** `src/task/NightmareNestTask.py`（基于上游 v3.8.13 的 `NightmareNestTask.py`），
  `combat_nest` 改用新的 `wait_travel_or_team()`，`_travel_to_nest_or_skip` 重写。
- 已加入 `restore.py` 的 `RELATIVE_FILES`（定制文件 31 → 32）。

### 23.2 登录后黑屏被误判为抓屏失败

- 模拟器点完登录后正常黑屏十几秒（游戏载入资源），MuMu IPC 此时返回纯黑帧；
  旧逻辑重试 3 次（约 1.5 秒）就抛 `CaptureException`，**每日任务被直接断掉**
  （21:09 / 21:13 的 `error_DailyTask_CaptureException` 截图佐证）。
- **修复**（`ok/device/capture_methods/nemu_ipc.py`）：新增 `BLACK_FRAME_GRACE_PERIOD = 30` 秒**冗余等待窗口**。
  窗口内全黑一律当作"登录/加载中"继续等（第一帧黑时重建一次 IPC 连接，同一段黑屏不再反复重连），
  超过 30 秒仍是全黑才抛带秒数的明确异常。

### 23.3 安卓设备启动时用 adb 拉起鸣潮

- 模拟器/真机开机后游戏不会自动运行；原先只有 `start_controller.check_device_error()` 里
  调过一次 `adb_ensure_in_front()`，而且它在**成功抓到一帧之后**才执行，
  模拟器桌面分辨率不匹配时会一直重试、游戏始终没被拉起。
- **修复**（`ok/device/DeviceManager.py`）：安卓设备启动分支（`do_start` 的 adb 分支）主动调
  `adb_start_game()` —— **等 adb 就绪 → 确认游戏不在前台 → `monkey -p <包名> -c android.intent.category.LAUNCHER 1` 拉起**。
  - 已在前台则不做任何事；两次拉起之间 20 秒冷却，避免"等待设备就绪"循环反复拉起。
  - adb 还没连上时立刻返回不空等，交给下一轮重试；设备已连接但命令失败时最多等 60 秒。

### 23.4 验证

- 新增 `probe/test_adb_start_game.py`（19 项：前台/未前台/未安装/冷却/设备未就绪/未连上/强制拉起）—— 全绿。
- 更新 `probe/test_black_frame.py`（19 项，含冗余窗口内不抛异常、窗口耗尽才抛异常、窗口时长上限）—— 全绿。
- 更新 `probe/test_touch_book.py`（14 项，含"书已打开则不再点右上角图标"、"书未打开才点"）—— 全绿。
- 回归：`test_book_opened` 3/3、`test_android_book` 5/5、`test_android_world` 10/10、`test_disconnect` 5/5 —— 全绿。
