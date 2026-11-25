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
   脚本结束会打印 "copied 32 files -> ..."，请确认这两行都出现。
6. 启动 ok-ww，选择设备「云游戏」，确认能看到「云每日」「云多账号」「保存 Cookie」
   「切换账号」任务，以及「角色代码」页（含工坊）。
7. 如果之后官方更新把补丁覆盖了：关闭 ok-ww 后运行 python restore.py 或双击
   一键恢复.bat；大版本结构变化则重跑第 4 步的安装脚本。详见 docs/backup-and-restore.md。

【如果用户报"启动不了/报没 adb/找不到 .py"，按这个顺序排查】
   a. 确认装齐：%LOCALAPPDATA%/ok-ww/data/apps/ok-ww/working/ok/device/DeviceManager.py
      与 working/src/task/BaseWWTask.py 是否存在且内容较新。缺失说明是旧版安装器
      （只装 15 个文件），请改跑 restore.py 补齐 32 个文件。
   b. 确认用的是「云游戏」设备类型。选「安卓/本地模拟器」才会走 adb 通道，
      报 "Emulator is not connected, start the emulator first!" 属于选错设备类型。
   c. 确认模拟器已启动、adb 端口可连（MuMu 默认 127.0.0.1:16384）。
   d. 查日志：%LOCALAPPDATA%/ok-ww/data/apps/ok-ww/working/logs/ok-script.log，
      搜 ERROR / adb_start_game / get_preferred_device returned None。
   e. 若日志显示 "set ADBUTILS_ADB_PATH failed"，说明找不到 adb.exe，
      通常是 adbutils 没装全，改用 ok-ww 自带的 python 重装。

请逐步执行并汇报结果。遇到报错先自行排查修复（比如路径、Python 版本、文件占用），
不要停下来问我，除非确实需要我提供安装路径或登录凭据。完成后告诉我可以开始使用。
```

---

安装脚本用法、卸载/恢复细节见 [`README.md`](README.md#安装) 和 [`docs/backup-and-restore.md`](docs/backup-and-restore.md)。
