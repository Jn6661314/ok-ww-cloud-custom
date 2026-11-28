# 交给 Agent 的一键安装提示词

把下面整段复制给 Agent（WorkBuddy / Claude / Cursor 等）。脚本会先备份被改文件，**不会**覆盖你的 Cookie、多账号配置和自定义队伍。

> **先选对提示词**：云鸣潮 / 多账号日常 / MuMu / 远控窗口 / 云游戏 → 用本文件；双机 / 采集卡 / KMBox / 游戏机+控制机 → 用 [`AGENT_INSTALL_DUALPC.md`](AGENT_INSTALL_DUALPC.md)。两者独立安装、不同目录，不能混装。

---

## 复制以下内容发给 Agent

```text
请帮我在本机安装 ok-wuthering-waves 的「云鸣潮定制补丁」，仓库：
https://github.com/Jn6661314/ok-ww-cloud-custom

这是非官方第三方补丁，依赖官方原版 ok-ww（上游：
https://github.com/ok-oldking/ok-wuthering-waves）。请尽量自动完成，不要让我手动操作。

【目录结构】ok-ww 是 pyappify 安装版，源码不在安装根目录：
  安装根目录：%LOCALAPPDATA%/ok-ww/                          ← 只有 ok-ww.exe，没有 .py
  运行目录：  %LOCALAPPDATA%/ok-ww/data/apps/ok-ww/working/  ← 实际运行的源码
  源码副本：  %LOCALAPPDATA%/ok-ww/data/apps/ok-ww/repo/     ← 官方更新会从这里覆盖 working
  自带 Python：%LOCALAPPDATA%/ok-ww/data/apps/ok-ww/python/python.exe
在安装根目录找 .py 找不到是正常的，不要当成安装失败。

【Python】优先用自带 python.exe；系统 Python 往往缺 adbutils，会报
ModuleNotFoundError: adbutils（看着像"没有 adb"）。必须用系统 Python 时先
pip install adbutils onnxruntime opencv-python numpy。

执行要求：
1. 确认已装官方原版（working 目录存在），Python 可用。若没装，告诉我并给出上游安装方式，
   不要自行替我安装。
2. 关闭正在运行的 ok-ww，避免文件被占用。
3. 克隆/下载完整仓库到临时目录并进入（清单在 restore.py，只下载单个文件会装不全）。
4. 运行安装脚本：
   python tools/install_to_local_app.py
   若 ok-ww 装在非系统盘（D:/E:/F: 等），不要靠默认路径（脚本默认只找 %LOCALAPPDATA%，
   会报 "Not installed"）：直接问我要实际路径，带参数重跑（含空格加引号）：
   python tools/install_to_local_app.py "E:/ok-ww/data/apps/ok-ww/working"
   路径末尾就是 working，不要写到 ok-ww.exe 那层。不要让我用记事本改任何 .py。
5. 脚本自动把全部定制文件复制到 working 与 repo、放好工坊离线缓存、把被改文件备份为
   .pre-cloud。请勿手动改 Cookie、MultiAccountConfig.json、自定义队伍。结束会打印
   "Done: N file copies across 2 directories."（N = 定制文件数 × 2，当前 46 个文件时是 92），
   确认这一行出现；数字随仓库清单变化属正常，以脚本实际输出为准。
6. 启动 ok-ww 做以下确认：
   a. 设备选「云游戏」，任务列表仍只有一个日常任务 + 一个多账号任务（官方按所选设备
      自动区分操作，不会重复注册）；多账号设置页多出「保存登录状态」「切换账号」两个按钮
      （PC/安卓下不显示）。
   b. 设置里有「Enable Blur」，勾选后云游戏右下角 UID 被遮挡（Blur / Inpaint）。
   c. 「角色代码」页（含工坊）存在。
   d. MuMu/安卓：先在 MuMu 里启动鸣潮，设备下拉才会出现模拟器；左侧导航「游戏」分组里有
      「MuMu 安卓 Config」，抓屏默认 MuMu IPC；拉海洛方块任务能启动。
7. 之后官方更新覆盖了补丁：关闭 ok-ww → 运行 python restore.py 或双击 一键恢复.bat；
   大版本结构变化则重跑第 4 步的安装脚本。详见 docs/backup-and-restore.md。

【常见报错，按顺序自查】
- 云游戏浏览器一打开就闪退（Win10）：本补丁默认已是 1600×900（config.py 里 browser 的
  resolution），不用记事本改。仍闪退就确认装的 config.py 里 resolution 是 (1600, 900)，
  重跑 restore 并重启；Win11 想用 1080p 可自行改回。
- 装完还是官方版 / 定制被刷回：官方启动器（pyappify）会 `git checkout -f` 到 app.json
  里的版本 tag，丢弃未提交改动。restore.py 已把版本 tag 钉到定制提交
  （pin_version_tag_to_head），务必用它部署，不要手动只拷 .py。重跑 restore 再启动。
  排查：`git -C <repo> reflog -5` 看 checkout；`git -C <repo> rev-parse v3.8.18^{commit}`
  应等于 `git -C <repo> rev-parse HEAD`。启动崩溃时启动器会绕开 git 整份重装，所以先看
  working/logs/ok-script.log 里的 `ok:__init__ error` / `RuntimeError: Can not find global
  config X`（配置改名漏改引用），修好再 restore。
- 不想依赖官方启动器：可直接用内置 pythonw 启动（把 <目录> 换成实际路径，如 E:\ok-ww）：
    cmd /c start "" /D "<目录>\data\apps\ok-ww\working" "<目录>\data\apps\ok-ww\python\pythonw.exe" main.py
  等价于成品包里的 ok-ww.exe：cwd 设为 working、不碰 git 和 app.json，官方启动器不会介入。
- 设备选了 PC/安卓时看不到「保存登录状态 / 切换账号」是设计行为；UID 遮罩需勾选
  Enable Blur（WebRTC 捕获同样生效）。
- 模拟器不在设备列表 / 没画面 / 不打架：先在 MuMu 里启动鸣潮；抓屏选 MuMu IPC，窗口最小化
  或开「后台保活」会持续黑屏；乱切人就手填「MuMu 安卓 Config → MuMu 编队」；按键无反应
  说明手游键位映射被关掉，必须保留模拟器的键位映射，不要改成纯 ADB 输入。
- 远控/串流窗口（UU远程、ToDesk、向日葵、Parsec、Moonlight）：入口在**左侧导航「游戏」
  分组最下面**的「远控串流窗口(试验性)」独立页，**不在设置页**；勾 Enable、填窗口标题
  关键字（如 UU远程|ToDesk|Parsec）、重启 ok-ww。前提：被控电脑游戏全屏 16:9
  （1920x1080/2560x1440/1600x900/1280x720）、远控画质选原画、本机窗口客户区 16:9 无黑边
  且保持前台、ok-ww 管理员运行、远控端鼠标绝对定位。日志出现「比例不是 16:9」就是窗口
  没拉对。设备下拉只剩远控窗口一个条目是设计行为。
- 其他：查 working/logs/ok-script.log 的 ERROR / playwright / cloud。

请逐步执行并汇报结果。遇到报错先自行排查修复（路径、Python 版本、文件占用），
不要停下来问我，除非确实需要我提供安装路径或登录凭据。完成后告诉我可以开始使用。
```

---

安装脚本用法、卸载/恢复细节见 [`README.md`](README.md#安装) 和 [`docs/backup-and-restore.md`](docs/backup-and-restore.md)。
