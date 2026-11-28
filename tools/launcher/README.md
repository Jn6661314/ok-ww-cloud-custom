# 绿色版启动器

包根目录的 `ok-ww.exe` 就是这里编译出来的（约 131 KB，**不是** pyappify 的启动器）。

它只做一件事：定位到自己所在目录，然后

```
CreateProcess(<dir>\data\apps\ok-ww\python\pythonw.exe, <dir>\data\apps\ok-ww\working\main.py)
```

工作目录设为 `working`，同时清掉 `PYTHONHOME` / `PYTHONPATH` / `VIRTUAL_ENV` 等
会干扰内置 Python 的环境变量。

**不碰 git、不读 app.json、不做版本校验、不联网**。所以不会像 pyappify 启动器那样
在启动时把 `working/` `git checkout -f` 回官方版本——这正是定制补丁能被保留的原因。

manifest 是 `requireAdministrator`（和原版一致，读游戏窗口需要管理员权限），
双击会弹一次 UAC。

## 重新编译

需要 Visual Studio 2022 的「使用 C++ 的桌面开发」工作负载：

```
tools\launcher\build.bat
```

产物 `tools\launcher\ok-ww.exe`，复制到打包暂存目录根部即可。
