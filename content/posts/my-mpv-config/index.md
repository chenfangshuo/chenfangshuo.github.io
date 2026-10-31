---
title: 我的 MPV 配置
subtitle: ""
date: 2026-10-11T13:28:45+08:00
slug: "my-mpv-config"
draft: false
description: "一份自用的 Windows mpv 配置：gpu-next + D3D11 硬解，HDR 直通与补帧都开了，配 uosc 界面。附放置位置、逐项取舍说明和几个可选方案。"
keywords: ["mpv", "mpv.conf", "HDR", "Windows", "uosc"]
featured_image: featured-image.webp                 # 文章封面 1600x900 / 21KB（代码卡片风，与站内代码块同一套视觉）
featured_image_preview: featured-image-preview.webp # 首页卡片用 800x450 / 8KB，见 MAINTENANCE.local.md「国内访问优化」
images:
  - featured-image.webp
seo:
  images:
    - featured-image.webp
featured_image_alt: ""
tags: ["mpv", "windows", "config", "hdr"]
categories: []
---

玩 mpv 的人大概都有一份越改越长的 `mpv.conf`。这里把我自用的那份贴出来，一是给同样在折腾播放器的朋友一个能直接用的起点，二是顺带在网上留个备份。

配置只针对 **Windows**，写法以 **mpv v0.41**（`mpv --list-options`）校对过。整理的原则是**与默认值相同的一律不写**，所以文件很短，剩下的每一项都是真的改过行为的。

<!--more-->

### 放在哪

`mpv.conf` 要和 mpv 主程序配套放，两种装法的位置不一样：

| 装法 | 配置目录 |
|---|---|
| 安装版 | `%APPDATA%\mpv\` |
| 便携版 | 主程序旁边的 `portable_config\` |

`input.conf`（快捷键）、`scripts\`（脚本）、`script-opts\`（脚本配置）都放在同一个目录下。

### 配置文件

{{% include mpv.conf ini %}}

上面这份就是仓库里的同名文件——正文这里不是手抄的，是把那份文件直接渲染出来的，所以两边永远不会写歪。想整份拿走可以用：[mpv.conf](mpv.conf)。

### 几个数值说明一下

配置里都写了短注释，只有下面几项容易照抄踩坑，单独说一下。

#### 色彩与 HDR

`target-colorspace-hint=yes` 会把色彩空间元数据交给系统，是 HDR 直通的关键。注意它的默认值是 `auto`——只在显示器报告 HDR 能力时才启用；显式写 `yes` 是强制开启。**显示器不支持 HDR 的话，用默认的 `auto` 更稳妥。**

`dither-depth` 要和显示器位深一致。10bit 面板写 `10` 是对的，但 8bit 屏也照抄 `10` 就会按错误位深抖动，那种情况建议改回 `auto` 让 mpv 自己探测。

#### 补帧（interpolation）

`interpolation=yes` 配 `video-sync=display-resample`，是把画面补到显示器刷新率：24fps 的片源在 60Hz 屏上本来会有 3:2 pulldown 的规律性抖动，开这个能抹平。

**但补帧最适合「刷新率是片源帧率的整数倍」**——24fps 配 120Hz 是完美的 5 倍，配 60Hz 就只能靠 `display-resample` 尽量匀一匀。如果你的屏幕刷新率跟片源对不上，这项带来的可能不是流畅而是另一种抖动，可以先关掉对比一下。

配置文件里我把 `video-sync=audio` 留成了注释行，就是给这种情况准备的：改回它之后音频做主时钟、画面丢帧对齐，最稳当（它本来就是默认值），代价是少了补帧那点顺滑。哪边更好因片源和设备而异，建议自己 A/B 一下。

#### 快捷键与界面

`input-default-bindings=no` 关掉了 mpv 所有内建快捷键，`osd-bar=no` 关掉了内建进度条——这两个都是配合 uosc 这类第三方界面的写法，进度条由 uosc 自己画，不然会重影。

⚠️ **代价是：屏蔽内建快捷键之后，必须自己提供 `input.conf`，否则键盘鼠标会完全没反应**——连 `q` 退出、空格暂停都不剩。

我那份 `mpv.conf` 是配套自己的 `input.conf` 用的（方向键快进、滚轮调音量、`,` 和 `.` 调音频延迟、`Ctrl+s` 截图到桌面）。这次只放了 `mpv.conf`，所以你要是也照抄了 `input-default-bindings=no`，至少先把这个最小配置存成 `input.conf` 放到同一目录：

```ini
SPACE  cycle pause
LEFT   seek -5
RIGHT  seek 5
UP     add volume 5
DOWN   add volume -5
f      cycle fullscreen
q      quit
```

### 被我省略的项

对照别人的配置会发现少了不少眼熟的条目，它们都是当前 mpv 的默认值，写不写一个样：

```ini
dither=fruit
tscale=oversample
d3d11-flip=yes
d3d11-exclusive-fs=no
vulkan-async-compute=yes
```

剩下的删的是真没用的：`log-file`（调试用）、`profile=gpu-hq`（那套预设会和这里显式写的缩放算法打架）、`osc=no`（那是给 modern.lua 的，我用 uosc 不需要），以及 `no-osd-bar`、`no-border` 这种命令行写法——在配置文件里得写成 `osd-bar=no`、`border=no`。

还有一段原来记下来的 `[Idle]` 待机配色示例也删了，因为里面有一处典型的坑：`background=1` 并不是合法值，`background` 只能取 `none` / `color` / `tiles`，写错 mpv 会直接起不来。顺带一提，这个文件里所有**颜色值都必须加引号**（`background-color="#000000"`），否则 `#` 会被当成行内注释，参数就空了。

### 几个可选方案

配置文件末尾留了两段注释掉的方案，按需取消注释：

- **Vulkan 后端**：部分显卡上 HDR 和性能会更好，但驱动兼容性不如 D3D11，遇到花屏/闪退可以两边对比。
- **蓝光原盘回退**：BDMV 进不去菜单时，用 `profile-cond` 匹配到 `MovieObject` 就切回 D3D11 上下文。注意当前主流程已经跑在 D3D11 上，这段只在上面改用 Vulkan 之后才有意义。

### 最后

这份配置的作用是「打开就能看，字幕音轨自动认，HDR 直接通」，没有做压暗部、锐化之类的画面调色——那些因人而异，而且很容易越调越糟。

配置本身没什么原创，都是官方手册和各个 mpv 交流群里的常用做法攒起来的。如果你的屏幕是 8bit，或者显示器刷新率不是片源帧率的整数倍，记得照着上面「几个数值说明一下」改两行再抄。
