# nectarlink-sidecar · 内置投屏内核的源码

这里是 ok-ww 内置投屏内核 `nectarlink-sidecar` 的 Rust 源码。

成品 `bin/nectarlink-sidecar.exe` 已经随本仓库分发，正常使用**不需要**编译。
这份源码放在这里，是为了：

* 让你能看懂它到底做了什么（协议内核 + Windows 自带的 H.264 解码 + 本机 socket）；
* 让你能按自己的需要改（比如加 H.265、调整码率策略），自己重新编译。

## 它是哪来的

nectarlink 是开源项目（<https://github.com/thtbee/nectarlink>），本目录的代码来自
它的 `core/nectarlink-sidecar` crate。上游仓库用了 workspace 布局，
所以这里的 `Cargo.toml` 做了改造：

* 依赖项写死版本，不再用 `.workspace = true`；
* `nectarlink-core` / `nectarlink-protocol` 改成 git 依赖，直接指向上游仓库；
* 自带一份 `third_party/iroh-mdns-address-lookup`——上游用 `[patch.crates-io]`
  换掉了 iroh 的 mDNS 实现，但那个机制只在上游 workspace 根目录生效，
  对 git 依赖不适用。补丁做了什么见 `third_party/iroh-mdns-address-lookup/NECTARLINK.md`。

因此编译需要能访问 GitHub（拉取 nectarlink-core）。

## 编译

```bash
cd nectarlink-sidecar-src
cargo build --release
```

产物在 `target/release/nectarlink-sidecar.exe`，把它复制到 ok-ww 的
`bin/` 目录覆盖旧文件，然后重跑 `python restore.py` 并重启 ok-ww。

> 首次编译要拉几百 MB 的依赖，第一次会比较慢。`Cargo.lock` 已经提交，
> 用的是和本仓库 `bin/` 里那个二进制一致的依赖版本。

## 协议

内核与 ok-ww 之间走 `127.0.0.1` 上的一条 TCP 连接，每条消息是
**1 字节类型 + 4 字节长度（小端）+ 负载**：

| 类型 | 方向 | 负载 |
| --- | --- | --- |
| 1 状态 | 内核 → ok-ww | JSON 文本 |
| 2 画面 | 内核 → ok-ww | u32 宽 + u32 高 + u32 字节数 + NV12 像素 |
| 3 触控 | ok-ww → 内核 | u8 动作(0按下/1移动/2抬起) + f32 x + f32 y |
| 4 按键 | ok-ww → 内核 | u8 键码 |

触控的 x/y 是**屏幕比例 0..1**，与手机当前的画面尺寸、横竖屏、缩放无关。

## 许可证

MPL-2.0，与 nectarlink 项目的其余部分一致。
