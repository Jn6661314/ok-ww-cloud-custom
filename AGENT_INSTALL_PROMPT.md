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

执行要求：
1. 先检查是否已安装官方原版 ok-ww（pyappify 安装版，运行目录通常是
   %LOCALAPPDATA%/ok-ww/data/apps/ok-ww/working），并确认 Python 可用。
   如果没装官方原版，请告诉我并给出上游安装方式，不要自行替我安装。
2. 关闭正在运行的 ok-ww 进程，避免文件被占用。
3. 克隆或下载本仓库到本地临时目录，进入仓库目录。
4. 运行安装脚本：
   python tools/install_to_local_app.py
   如果提示找不到 working 目录，请让我提供实际路径，然后带参数重跑：
   python tools/install_to_local_app.py "你的working目录路径"
5. 脚本自动完成：复制新增/修改的源码、给 config.py 注册云任务与「角色代码」页、
   打浏览器后台运行与云游戏进入检测补丁、放入工坊离线缓存，并把被改文件备份为
   .pre-cloud 后缀。请勿手动改动 Cookie、MultiAccountConfig.json、自定义队伍文件。
6. 启动 ok-ww，选择设备「云游戏」，确认能看到「云每日」「云多账号」「保存 Cookie」
   「切换账号」任务，以及「角色代码」页（含工坊）。
7. 如果之后官方更新把补丁覆盖了：关闭 ok-ww 后运行 python restore.py 或双击
   一键恢复.bat；大版本结构变化则重跑第 4 步的安装脚本。详见 docs/backup-and-restore.md。

请逐步执行并汇报结果。遇到报错先自行排查修复（比如路径、Python 版本、文件占用），
不要停下来问我，除非确实需要我提供安装路径或登录凭据。完成后告诉我可以开始使用。
```

---

安装脚本用法、卸载/恢复细节见 [`README.md`](README.md#安装) 和 [`docs/backup-and-restore.md`](docs/backup-and-restore.md)。
