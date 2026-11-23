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
