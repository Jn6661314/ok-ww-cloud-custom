# 更新被官方覆盖后如何恢复

ok-ww 的自动更新会还原安装目录下 `working` 与 `repo` 两处的源码，本补丁文件也会被覆盖。
下面两种方式都不会改动账号 Cookie（`data/cloud_profiles/`）和任务配置（`configs/`）。

## 方式一：直接覆盖（同版本）

1. **先关闭 ok-ww**，否则文件被占用会复制失败。
2. 在本仓库根目录双击 `一键恢复.bat`，或执行：

   ```bash
   python restore.py
   ```

3. 看到"恢复完成"后重新打开 ok-ww。

脚本会把 32 个定制文件同时恢复到 `working` 和 `repo`，并在恢复前把当前文件备份到
`custom-backup-before-restore-<时间戳>` 目录，出问题可以回退。

可选参数：

```bash
python restore.py "D:/some/working"   # 自定义 working 路径
python restore.py --working-only      # 只恢复 working
python restore.py --no-backup         # 跳过恢复前备份（不推荐）
```

## 方式二：重新打补丁（大版本升级后）

如果 ok-ww 升级导致文件结构变化、直接覆盖后报错，从源码级副本重新应用：

```bash
python tools/install_to_local_app.py
python tools/install_to_local_app.py "D:/path/to/working"   # 自定义路径
```

脚本会把新增模块复制进去，并以幂等方式重新应用 `config.py`、多账号注册表、
ok-script 浏览器捕获模块、进入游戏冷却与月卡守卫等 patch。每个被改动的文件
首次会被备份成 `*.pre-cloud`。

工坊离线索引在 `workshop_cache/`，脚本会自动复制到 `configs/workshop_cache`；
代码包 `codes/*.zip` 可用下面的命令补全：

```bash
python tools/download_workshop_cache.py
```

## 提示

- 若不需要再跟随官方更新，可以干脆在 ok-ww 里关闭自动更新。
- 自定义队伍代码保存在 `configs/custom_teams`，不在恢复范围内，可放心保留。
