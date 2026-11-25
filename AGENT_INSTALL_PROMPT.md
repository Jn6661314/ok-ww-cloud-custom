# 交给 Agent 的一键安装提示词

把下面整段复制给你使用的 Agent（WorkBuddy / Claude / Cursor 等），它就能自动在本机完成安装与验证。
安装脚本会先备份被修改的文件，且**不会**覆盖你的 Cookie、多账号配置和自定义队伍。

---

## 复制以下内容发给 Agent

```text
请帮我在本机安装 ok-wuthering-waves 的「云鸣潮定制补丁」，仓库地址：
https://github.com/Jn6661314/ok-ww-cloud-custom

这是一个非官方第三方补丁，依赖官方原版 ok-wuthering-waves（上游：
https://github.com/ok-oldking/ok-wuthering-waves）。请尽量自动完成，不要让我手动操作。

【重要：目录结构】ok-ww 是 pyappify 安装版，源码不在安装根目录：
  安装根目录：%LOCALAPPDATA%/ok-ww/            ← 这里只有 ok-ww.exe，没有任何 .py
  运行目录：  %LOCALAPPDATA%/ok-ww/data/apps/ok-ww/working/   ← 实际运行的源码
  源码副本：  %LOCALAPPDATA%/ok-ww/data/apps/ok-ww/repo/      ← 官方更新会从这里覆盖 working
  自带Python：%LOCALAPPDATA%/ok-ww/data/apps/ok-ww/python/python.exe
在安装根目录找 .py 一定找不到，这是正常的，不要因此认为安装失败。

【Python】请优先用 ok-ww 自带的 python（上面的 python.exe）。系统 Python 往往缺少
adbutils 等依赖，跑脚本时会报 ModuleNotFoundError: adbutils，看起来就像"没有 adb"。
若必须用系统 Python，请先 pip install adbutils onnxruntime opencv-python numpy。

执行要求：
1. 先检查是否已安装官方原版 ok-ww（确认 %LOCALAPPDATA%/ok-ww/data/apps/ok-ww/working
   目录存在），并确认 Python 可用。如果没装官方原版，请告诉我并给出上游安装方式，
   不要自行替我安装。
2. 关闭正在运行的 ok-ww 进程，避免文件被占用。
3. 克隆或下载本仓库到本地临时目录，进入仓库目录（要完整仓库，不要只下载单个文件，
   因为安装清单在 restore.py 里）。
4. 运行安装脚本：
   python tools/install_to_local_app.py
   如果提示找不到 working 目录，请让我提供实际路径，然后带参数重跑：
   python tools/install_to_local_app.py "你的working目录路径"
5. 脚本自动完成：把全部定制文件复制到 working 与 repo 两个目录、放入工坊离线缓存，
   并把被改文件备份为 .pre-cloud 后缀。请勿手动改动 Cookie、MultiAccountConfig.json、
   自定义队伍文件。
   脚本结束会打印 "Done: 29 file copies across 2 directories."，请确认这一行出现。
6. 启动 ok-ww，做三项确认：
   a. 设备下拉里选「云游戏」，任务列表里**仍然只有一个日常任务**和一个多账号任务
      （官方 v3.8.15 起按所选设备自动区分操作，不会出现「云每日」「云多账号」这类
      重复任务）；多账号任务的设置页在云设备下会多出「保存登录状态」「切换账号」
      两个按钮，切到 PC 设备后这两个按钮消失。
   b. 设置里能看到「Enable Blur」，选中后云游戏界面右下角 UID 被模糊/图案覆盖
      （可切换 Blur / Inpaint）。
   c. 「角色代码」页（含工坊）存在。
   d. MuMu/安卓：设备下拉里选模拟器后，**左侧导航栏「游戏」分组里**能看到「MuMu 安卓 Config」页（可手填编队），
      抓屏方式默认为 MuMu IPC；拉海洛方块任务在该设备下也能启动。
7. 如果之后官方更新把补丁覆盖了：关闭 ok-ww 后运行 python restore.py 或双击
   一键恢复.bat；大版本结构变化则重跑第 4 步的安装脚本。详见 docs/backup-and-restore.md。

【版本号的坑：启动器和应用内读的是两个地方】
   - 应用内「关于」页 / 日志的版本来自 working/config.py 的 version（本补丁为 v3.8.15）；
   - 启动器（ok-ww.exe）窗口显示的版本来自 data/apps/ok-ww/app.json 的 current_version。
     若那里还是 v3.8.14，启动器不仅显示错误，还会认为"可以更新到 3.8.15"——
     用户一点更新，官方代码就覆盖 working/repo，**整套定制全部丢失**。
   - restore.py 每次部署都会自动把 current_version 同步成 config.py 的 version（改前备份
     app.json.<时间戳>.bak）。所以务必用 restore.py 部署，不要手动只拷 .py 文件。
   - 用户报"版本还是 3.8.14"时：先看是启动器还是应用内；两者不一致就让其重跑 restore.py。

【如果用户报"启动不了/按钮不见了/UID 还在"，按这个顺序排查】
   a. 确认版本对得上：本补丁以官方 v3.8.15 + ok-script 3.0.14 为基线。若用户装的是
      更老的官方版（如 v3.8.14），先让用户把官方 ok-ww 更新到 v3.8.15 再装补丁。
   b. 确认装齐 31 个文件：working/src/task/MultiAccountDailyTask.py、
      working/src/cloud_browser.py、working/src/stream_window.py、working/src/globals.py、
      working/src/task/BaseWWTask.py、working/ok/device/DeviceManager.py、working/config.py
      等是否存在且内容较新。
   c. 「保存登录状态 / 切换账号」只在设备选「云游戏」时出现——选成 PC 或安卓时不显示，
      这是设计行为，不是 bug。
   d. UID 遮罩由框架的 blur 机制实现，需要在设置里勾选「Enable Blur」（默认 Inpaint）。
      若用 WebRTC 捕获模式，遮罩同样生效（走取帧路径，不依赖页面 DOM）。
   e. 查日志：%LOCALAPPDATA%/ok-ww/data/apps/ok-ww/working/logs/ok-script.log，
      搜 ERROR / playwright / cloud。

   f. 如果用户报"模拟器不在设备列表 / MuMu 没画面 / 不打架"：
      - 先在 MuMu 里把鸣潮启动起来，设备下拉才会扫到 adb 设备；
      - 抓屏方式选 MuMu IPC；若窗口被最小化或开了「后台保活」，IPC 会持续黑屏
        （日志里是"MuMu 抓屏返回空画面"）；
      - 战斗识别乱切人：让用户在「左侧栏『游戏』分组 → MuMu 安卓 Config → MuMu 编队」手填编队；
      - 按键无反应：手游不认 input keyevent，必须保留模拟器的键位映射，不要改成纯 ADB 输入。

   g. 如果用户想用 UU远程 / ToDesk / 向日葵 / Parsec 这类远控或串流窗口跑任务（试验性）：
      - **入口位置先说清楚，否则用户一定找不到**：在**左侧导航栏「游戏」分组最下面**的
        「远控串流窗口(试验性)」独立页（图标是显示器），**不在「设置」页里** ——
        这类 `show_at_tab` 配置项会被设置页主动跳过；侧边栏可能要往下滚一点。
      - 在该页勾 Enable，Window Title 填窗口标题关键字
        （如 `UU远程`、`ToDesk`、`SunloginClient`、`Parsec`，多个用 `|` 分隔），改完**重启 ok-ww**；
      - 前提必须逐条确认：被控电脑上游戏**全屏 16:9**（1920x1080/2560x1440/1600x900/1280x720）；
        远控软件画质选「原画/原始分辨率」，不要自适应缩放；本机窗口客户区也是 16:9 且画面铺满，
        不能有黑边；窗口保持前台不最小化；ok-ww 以管理员身份运行；远控端鼠标用绝对定位；
      - 日志里出现"远控/串流窗口比例是 WxH ... 不是 16:9"就是窗口没拉对，按提示改窗口比例；
      - 设备下拉里只有一个条目（远控窗口标题），鸣潮 PC 客户端不会同时出现，这是设计行为。

请逐步执行并汇报结果。遇到报错先自行排查修复（比如路径、Python 版本、文件占用），
不要停下来问我，除非确实需要我提供安装路径或登录凭据。完成后告诉我可以开始使用。
```

---

安装脚本用法、卸载/恢复细节见 [`README.md`](README.md#安装) 和 [`docs/backup-and-restore.md`](docs/backup-and-restore.md)。
