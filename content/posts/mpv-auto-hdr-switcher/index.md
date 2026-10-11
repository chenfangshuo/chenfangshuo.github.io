---
title: 让 MPV 自动切换 Windows HDR
subtitle: ""
date: 2026-10-11T14:45:00+08:00
slug: "mpv-auto-hdr-switcher"
draft: false
description: "一个 mpv 脚本：播 HDR 片时自动打开 Windows 的 HDR，播 SDR 内容时切回来，不用再手按 Win+Alt+B。附判定逻辑、安装调参，以及几处有意为之的取舍。"
keywords: []
featured_image: featured-image.webp                 # 文章封面 1600x900（代码卡片风，与站内代码块同一套视觉）
featured_image_preview: featured-image-preview.webp # 首页卡片用 800x450
tags: []
categories: []
---

Windows 的 HDR 是个**全局开关**：开着的时候桌面、浏览器、SDR 视频全都在 HDR 模式下跑，SDR 内容会发灰；关着的时候再 HDR 的片源也只能拿到一条 SDR 信号，HDR 就白瞎了。所以每次看片前后都得按一下 `Win+Alt+B` —— 看之前忘了按画面发暗，看完忘了按回来 SDR 又发灰。

上一篇[我的 MPV 配置](/my-mpv-config/)里那个 `target-colorspace-hint=yes`，管的是「把 HDR 元数据标到输出上」这一段；而系统总开关握在 Windows 手里，不会自己动。所以我写了个 mpv 脚本补上这一步：**认出是 HDR 片就替你打开系统 HDR，是 SDR 内容就切回去**。

<!--more-->

### 它做什么

| 场景 | HDR 状态 | 备注 |
| :--- | :--- | :--- |
| 打开 HDR 电影 | 开 | 从片头开始播，不漏首帧 |
| 连播 / 手动切集 | 保持开 | 不会有二次黑屏闪烁 |
| 拖动进度条 / 暂停 / 继续 | 不变 | 不会重复触发检测 |
| 切到 SDR 视频 | 关 | 黑屏一次，之后从片头续播 |
| 播完停在最后一帧 | 保持开 | 不急着切回 SDR，方便拖进度条回看 |
| 手动停止 / 关掉当前文件 | 延迟关 | 等 2.5 秒确认没有新任务 |
| 直接点 ✕ 退出 | 立即关 | 随播放器退出恢复 SDR |
| 系统本来就开着 HDR | 保持开 | 看完不会替你关掉 |
| 显示器不支持 HDR | 不动 | 不暂停、不调用、不等待 |
| 播放中自己改了 HDR | 按真实状态 | 之后的行为不会和你抢 |

目标就是让你**不需要知道它是怎么切的**——正常用下来，除了切 HDR 时那一次黑屏，你不应该感觉到它的存在。

### 怎么判断

判断分两道，先快后准：

1. **文件名预判**。文件名里带 `hdr` / `dovi` / `dolby vision` / `.dv.` / `smpte2084` / `hlg` 的，直接按 HDR 处理，不等元数据。好处是判定零延迟，从片头就开始播。
2. **元数据检测**。其余文件读 mpv 的 `video-params/gamma`，`pq` / `hlg` 即 HDR，其余按 SDR。元数据要等首帧解出来，所以这里以 0.1 秒的间隔轮询、最多等 1.5 秒，超时再回到文件名兜底。

拿到判定结果之后还不算完——**每次决定切换前都会重新问一次系统当前的真实状态**（执行 `HDRCmd.exe status` 读退出码），而不是启动时读一次存着。这样你播放中手动按了 `Win+Alt+B`，脚本下一次判断的依据依然是真实状态，不会和你抢。

真正需要切换时，脚本会先把画面按住不放，等显示器握手结束再放开；如果开播后不到两秒就触发了切换，还会把这一小段退回片头重播，免得在黑屏期间白播掉。系统本来就处于目标状态时，不做任何停顿。

### 安装

**1. 准备 `HDRCmd.exe`**

到 [HDRTray Releases](https://github.com/res2k/HDRTray/releases) 下载压缩包，解压出 `HDRCmd.exe`，放到 `C:\Program Files\mpv\`。换别的位置也行，但要同步改脚本里的 `hdr_cmd_path`。

**2. 放入脚本**

把 `auto-hdr.lua` 放进 mpv 的脚本目录：

| 装法 | 脚本目录 |
|---|---|
| 便携版 | `mpv\portable_config\scripts\` |
| 安装版 | `%APPDATA%\mpv\scripts\` |

装完播一部 HDR 片即可验证，正常情况下不需要再做任何事。

### 调参

只需要改 `auto-hdr.lua` 顶部的 `options`：

| 参数 | 默认 | 什么时候改 |
| :--- | :--- | :--- |
| `hdr_cmd_path` | `C:\\Program Files\\mpv\\HDRCmd.exe` | HDRCmd.exe 不在这个位置时。**Lua 里反斜杠必须写两个** |
| `handshake_delay_on` | `3.8` 秒 | **开** HDR 时等显示器黑屏结束的时间。画面亮了才开始播 → 调大；黑屏早结束了还在等 → 调小 |
| `handshake_delay_off` | `3.8` 秒 | **关** HDR 时的同一等待。开 HDR 的黑屏通常比关更长，所以两个值分开配 |
| `turn_off_delay` | `2.5` 秒 | 播放结束后延迟关闭的防抖窗口。为切集、选片留出缓冲，避免关了又开 |

`handshake_delay_*` 是最需要按自己显示器微调的两个值：显示器切 HDR/SDR 时会黑屏一段时间，脚本在这段时间里按住画面不放，等黑屏结束才开始播。**3.8 秒是给手头这台显示器的数**，你的屏幕可能更快或更慢——片头总是先黑一下再开始、或者反过来白等了一会儿，就是它该调了。

其余参数（判定细节、状态缓存、调试日志等）见 [DEVELOPER.md](https://github.com/chenfangshuo/auto-hdr/blob/main/DEVELOPER.md)。

### 几处有意的取舍

有几条行为看着像 bug，其实是特意这么写的：

* **播完不自动切回 SDR**。配了 `keep-open` 时，播到结尾只是停在最后一帧、文件仍被加载，脚本收不到「文件卸载」事件——而这正是想要的：播完往往还要拖进度条回去回看，不该在这时候被切回 SDR。想恢复 SDR 就退出 mpv、手动 stop，或者播下一部 SDR 内容。
* **只关自己开的**。系统 HDR 如果是你手动开的，脚本看完不会替你关掉，不越权。
* **文件名预判优先于元数据**。命中 HDR 标签的文件不再核对元数据（换来的是零延迟），代价是**文件名错标的 SDR 会被点亮 HDR**。
* **不支持 HDR 的机器整体旁路**。查不到支持 HDR 的显示器时，脚本不暂停、不调用、不等待，只给一条 OSD 提示——否则每部 HDR 片都要白等一次握手时长。
* **多显示器不区分主副屏**。`HDRCmd.exe` 会连带切换所有支持 HDR 的屏幕。

### 排错

先在 PowerShell 里自检依赖（第二条返回 `exit=1` 表示当前 HDR 是关的，开着则是 `exit=0`）：

```powershell
& 'C:\Program Files\mpv\HDRCmd.exe' status
& 'C:\Program Files\mpv\HDRCmd.exe' status -m x; "exit=$LASTEXITCODE"
```

两条都正常再把脚本里的 `debug` 改成 `true`，看 mpv 日志（前缀 `[auto_hdr]`）：终端版 `mpv.com` 直接可见，`mpv.exe` 按 `~` 打开控制台。日志会给出决策链的每一步。

最常见的一类「没生效」其实不是故障：**HDR 片画面对了但系统 HDR 没切**，通常是因为系统 HDR 本来就被你手动开着，脚本检测到已处于目标状态就什么都不做了。反过来「该切 SDR 却没切」也是同理——那不是它开的，它就不关。

### 完整脚本

{{% include auto-hdr.lua lua %}}

也可以在 GitHub 上取：[chenfangshuo/auto-hdr](https://github.com/chenfangshuo/auto-hdr)。脚本是 **MIT 许可**的，想怎么改、想塞进自己的配置里都行，不用来问。

仓库里的 `DEVELOPER.md` 写了实现细节、mpv 事件语义的实测结论和完整排错表，`test/` 下有一套用假 HDRCmd 跑的自测（不碰真实显示器）。

### 最后

写它的起因很简单：受够了手动按快捷键，以及忘记按回来之后那种灰蒙蒙的画面。脚本本身没什么黑魔法，用到的都是 HDRCmd 的退出码和 mpv 的几个事件，麻烦的地方全在边界情况上——切集、暂停、seek、退出，每一条都要确认不会误触发或者漏触发。

已经用了一段时间，现在属于「装上就忘了它存在」的状态，所以拿出来分享一下。有遇到判定不准或者黑屏时长对不上的，照着上面调 `handshake_delay_*` 和自己的屏幕对齐就行。
