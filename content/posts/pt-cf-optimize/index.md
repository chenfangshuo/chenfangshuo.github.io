---
title: 从 30 秒到 3 秒：把 Cloudflare 优选 IP 写进 hosts
subtitle: ""
date: 2026-10-29T22:20:00+08:00
slug: "pt-cf-optimize"
draft: false
description: "一个 Windows PowerShell 工具：扫描 Cloudflare 边缘 IP、逐域名验证后写进 hosts，让套了 Cloudflare 的站点更快。我这边有站从 30 秒掉到 3 秒内。不代理、不登录、不改出口 IP，带严格校验、备份和一键回滚。"
keywords: ["Cloudflare", "优选 IP", "hosts", "网站加速", "PowerShell", "PT"]
featured_image: featured-image.webp
featured_image_preview: featured-image-preview.webp
tags: ["cloudflare", "hosts", "powershell", "pt", "network"]
categories: []
---

很多站点都套在 Cloudflare 后面：PT 站、论坛、图床、个人博客。CF 会把域名解析到它认为合适的边缘节点，但「合适」是按它自己的调度算的，不一定适合你这条线路。

我这边就有几个这样的站：没做优选时，整页加载要 30 秒左右，运气不好直接打不开；把优选 IP 写进 hosts 之后，同样的页面 3 秒内就出来了。差别不是玄学——同一个站落到不同的边缘 IP，有时只是首字节 1 秒变 0.6 秒，有时就是「打不开」和「3 秒」的区别。所以「Cloudflare 优选」一直有人折腾。

但常见做法各有各的代价：给代理客户端换节点，改变的是出口 IP，站方看到的是另一条线路；在线优选网站要把域名交给第三方；手工把 IP 抄进 hosts，又没有验证和备份，站点一换 IP 就打不开了。我想要的其实很小——**只把「哪些 CF 边缘 IP 对这条宽带更快」算清楚，再安全地写进本机 hosts**。

[`pt-cf-optimize`](https://github.com/chenfangshuo/pt-cf-optimize) 就是为这个写的：Windows PowerShell 脚本，不代理、不登录、不改出口 IP；扫描、测速、逐站验证都在本地完成，最后只维护 hosts 里一个带标记的区块，出问题一条命令回滚。名字里的 `pt` 只是因为最早是给自己挂 PT 用的——它并不绑定 PT，任何套了 Cloudflare 的域名都可以填进 `domains.txt`。

<!--more-->

## 它做什么，不做什么

| 做 | 不做 |
| :--- | :--- |
| 扫描 Cloudflare 边缘 IPv4，按延迟和丢包预筛 | 不代理任何流量，不改变出口 IP |
| 独立测吞吐，按落地机房分层抽样 | 不登录、不带 Cookie、不读 passkey |
| 每个域名以当前 hosts/DNS 为基线做 HEAD 验证 | 不访问 announce URL |
| 只维护 hosts 里一对 `BEGIN/END` 标记之间的内容 | 不碰 BitTorrent 的 P2P 数据连接 |
| 备份、原子写入、读回校验、一键回滚 | 不代替 VPN / 机场 / 在线优选网站 |

它解决的是「网页和 API 打开慢」这一段；对 PT 来说，tracker 的连接也会顺一点。**下载速度不会因此变快**，因为 PT 的实际传输是 BitTorrent 直连，和 hosts 无关。这一点在 FAQ 里被问得最多，先写在前面。

## 跑起来

需要 Windows 10/11、PowerShell 7+，以及系统自带的 `curl.exe`。CFST 是可选的。

**1）准备域名**

复制 `domains.example.txt` 为 `domains.txt`，每行一个域名，只填**确认由 Cloudflare 代理**的站点。可以先探一下响应头：

```powershell
curl.exe -sI https://example.com | findstr /i "server:"
```

返回 `server: cloudflare` 是线索，不是绝对保证；不是 CF 的站点会在逐站验证阶段被跳过，所以不确定的也可以先放进去，用 `-DryRun` 看结果。

域名不想手填，可以从 PT-Depiler 备份、Windows 代理旁路列表、文本或剪贴板导入：

```powershell
.\Import-Domains.ps1 -Source Depiler -Path '.\PTD_backup.zip'
.\Import-Domains.ps1 -Source ProxyBypass
```

导入器只读 PT-Depiler 备份里的 `metadata.json`，**不会碰** `cookies.json`、`userInfo.json`、`downloadHistory.json`；而且默认只写 `domains.imported.txt`，不覆盖 `domains.txt`。先打开检查，确认后再用 `-Merge` 合并——代理旁路列表里常常混着 test-ipv6、Steam 这类非 PT 域名。

**2）可选：放好 CFST**

从 [CloudflareSpeedTest releases](https://github.com/XIU2/CloudflareSpeedTest/releases) 下载后，把 `cfst.exe` 和 `ip.txt` 放到脚本旁的 `cfst\` 目录。不放也能用，脚本会自动回退到内置扫描。

**3）先看结果，不写 hosts**

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\pt-cf-optimize.ps1 -DryRun
```

**4）确认后，用管理员 PowerShell 正式写入**

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\pt-cf-optimize.ps1
```

**5）出问题一键回滚**

```powershell
pwsh -NoProfile -ExecutionPolicy Bypass -File .\pt-cf-optimize.ps1 -Rollback
```

第一次运行大约 **8–15 分钟**。其中「探测候选落地区域（256 个）」本身就要几分钟；脚本每 32 个打印一次 `已探测 x/256`，不会看起来像卡死。第二次以后有机房缓存，通常会快不少。

## 它是怎么选的

整个流程可以拆成五步：

1. **延迟/丢包预筛**。有 CFST 就用 CFST 的 TCPing 结果；没有就用内置扫描，从 CF 官方网段随机抽样，用 `cdn-cgi/trace` 测。只保留丢包 ≤5%、有响应的 IP，按延迟排序。
2. **按机房分层抽样**。取延迟最低的 256 个候选读 `colo=`，按机房分组，组内按 TTFB 排序，再轮流抽 32 个。目的不是选「最快」，而是避免候选全落在同一个机房。
3. **吞吐初测 + 决赛**。32 个候选各下 1MB 做初测，前 6 名进入决赛：3 次 × 2MB，串行下载，取中位数。**最终排名只认决赛成绩**，初测分数不保留。
4. **逐域名验证**。每个域名以**当前的 hosts/DNS 路径**为基线发 HEAD，候选则带 `--resolve` 直接打到指定 IP。准备切换时，基线和选中的候选再各复核一次。
5. **决定写不写**。只有比基线快 ≥15%（`-MinImprovementPct`）**且**绝对改善 ≥30ms（`-MinImprovementMs`），或者基线本来就不可用/类别更差，才切换；否则保留原样。

### CFST 和内置扫描怎么选

CFST 只是可选的加速器，两条路径的区别在候选池和延迟测量方式：

| | CFST（`cfst\cfst.exe`） | 内置扫描（`-NoCfst` / 未找到） |
| :--- | :--- | :--- |
| 候选覆盖 | `ip.txt` 当前 25 个网段，更广 | 随机抽 `-MaxCandidates` 个（默认 192） |
| 延迟测量 | TCPing（TCP RTT） | HTTPS `cdn-cgi/trace`（含 TLS） |
| 依赖 | 第三方 GPL-3.0 二进制 | 仅 PowerShell 7 + 系统 `curl.exe` |
| 速度 | 快 | 几十秒到一两分钟 |

两者共用后面的机房分层、吞吐决赛和逐域名选择；CFST 只负责延迟/丢包，不参与下载测速。

### 为什么不直接信 CFST 的测速

项目里有一条挺典型的观测：CFST 官方默认的测速地址 `https://cf.xiu2.xyz/url` 某次返回了 **403**，而 CFST 把 403 的响应体当成了「下载完成」，于是算出一个 15 MB/s 的假速度；拿一个 3MB 文件单独复测，真实吞吐只有 0.48 MB/s。

这是特定时间和网络下的个例，不保证每个人复现。但它说明了一个通用问题：**单一测速端点的结果不能当成真实吞吐**。所以这个工具只拿 CFST 做延迟/丢包筛选，吞吐量自己测，并且校验下载字节数、HTTP 状态码和实际远端 IP。

### 为什么按机房分层

同一线路到不同 CF 机房的表现差得很远：

- **HKG**：TCP 握手可能只有 130 ms，看起来很美，但大流量丢包严重，TLS 偶尔卡几秒，3MB 下载可能直接超时。
- **LAX / SJC**：握手 170–340 ms，但吞吐通常更稳。
- **FRA / LHR**：有时吞吐反而最高，但网页 TTFB 不一定最好。

只按延迟排序会系统性地高估 HKG。分层抽样保证每个主要机房都有候选，再由吞吐和逐站 TTFB 决定谁留下。

### 为什么每个域名单独选

同一个 CF 边缘 IP 可以服务任何 CF 站点，但不同站点到不同机房的 TTFB 不一样，个别站点还可能对你的 HEAD 请求返回 1034（Edge IP Validation）——意思是这个 zone 只服务它自己的 IP，优选不出来。全局吞吐排名只用来挑出前 3 个候选，最终每个域名独立比较。

这里还有两个容易被忽略的细节：

- **时间统一扣掉 DNS 解析**。候选走 `--resolve`，解析时间接近 0；基线走系统解析。如果不扣，基线会白背一次 DNS 时间，15% 的门槛就被解析时间吃掉了。
- **1034 回退到 DNS 时不写 hosts**。如果所有候选都不可用，脚本会看这个域名自己的 DNS A 记录；如果 DNS 的 IP 胜出，动作是**交还 DNS**（删掉托管条目），而不是把那个临时 IP 写进去——否则站点下次换 IP，hosts 就成了故障源。

## hosts 是怎么改的

这是整个工具里最不性感、但最要紧的部分。原则是：**能明确判断才改，判断不了就中止**。

- 只接受「没有标记」或「恰好一对 `BEGIN/END`」；缺失、重复、嵌套、孤立 END 直接中止，并报告行号。
- 编码只支持 ASCII / UTF-8；UTF-16、GBK 之类的直接拒绝改写，避免越改越烂。
- 托管区块外如果有多别名行、受管域名的 IPv6 映射，或者别的工具的托管区块，也中止。
- 写入流程是：全局互斥锁 → 提交前重新读一遍 hosts 校验哈希 → 备份 → 临时文件 → 原子替换 → 读回校验 → 刷新 DNS。
- 备份落在 `%ProgramData%\pt-cf-optimize\backup`，保留最近 10 份和一份首次接管快照；`-Rollback` 不依赖 `domains.txt`，域名清单丢了也能恢复。

增量语义也很保守：验证成功才更新；验证失败默认保留上一次的映射；只有明确的 1034/1003 才自动丢弃；不在本次列表里的域名默认保留，想删要显式加 `-Prune`。换句话说，**它不会因为一次验证失败，就把你原来能用的映射删掉**。

## 一次运行长什么样

下面是脱敏后的决策表（域名和数字换成了示例）：

```text
==== 逐域名决策 ====

Domain            BaselineIP      BaseState BaseTTFB ChosenIP        ChosenTTFB ImprovePct Reason           Action
------            ----------      --------- -------- --------        ---------- ---------- ------           ------
pt.example.com    104.17.143.151  ok            1.01 162.159.160.5        0.62      39.30 confirmed        update
forum.example.org 104.17.131.149  ok            0.57 104.17.131.149       0.57       7.30 below-threshold  keep
```

我最近一次实际运行是 17 个域名：**只切换了 4 个；其余 12 个没达到 15% + 30ms 的门槛而保留，1 个没有可用候选**。这个比例看着「不划算」，但这正是设计目标——多数时候 DNS 给的 IP 已经够用，脚本只处理那几处明显慢的，不制造无意义的变更。

耗时分布大概是：

| 阶段 | 典型耗时 | 说明 |
| :--- | :--- | :--- |
| CFST 延迟/丢包扫描 | 1–3 分钟 | `-NoCfst` 内置扫描通常更快但覆盖小 |
| 探测候选落地区域（256 个） | 2–6 分钟 | 有 14 天内的机房缓存时约 1 分钟 |
| 吞吐初测 + 决赛 | 1–3 分钟 | 约 70MB 下载，取决于带宽 |
| 逐域名验证与复核 | 1–3 分钟 | 每站约 6–10 次 HEAD |

想缩短时间可以调小候选数：

```powershell
.\pt-cf-optimize.ps1 -ThroughputCandidates 16 -MaxDomainProbes 4
.\pt-cf-optimize.ps1 -NoCfst -MaxCandidates 128
```

需要给面板或定时任务消费结果时，用 `-Plan -PlanPath .\plan.json` 输出 JSON（不写 hosts、不需要管理员）。定时运行的三种方案，包括自动写入的风险，在仓库的 `docs/scheduling.md` 里。

## 安全边界：它对目标站做了什么

这部分比速度更值得强调，挂 PT 的话尤其要看：

- **不改变出口 IP**。工具只决定「连到哪个 CF 边缘节点」，流量仍然从家宽直接出去；登录 IP、tracker 上报 IP 都不变。前提是这些域名在代理旁路里。
- **不登录、不带 Cookie、不访问 announce URL、不读 passkey**。对目标站只发少量 HEAD：每域名典型 6–10 次，最坏 11 次；准备切换时同一 IP 最多 2 次。
- **Clash 开着也没关系**。所有 curl 都带 `--noproxy '*'`，CFST 启动前会清空代理环境变量，探测和测速强制直连。
- **TUN / 虚拟网卡模式要避免**。检测到 TUN 时，非 DryRun 会中止；确认风险后可以加 `-Force`。
- 脚本会检查 WinINET 旁路和 TUN，但**无法完整识别** PAC/WPAD、WinHTTP、应用级代理和 WFP 透明转发。它只能做到「尽力而为」，具体规则仍以各站为准。

另外，默认只写 **1 个 IP**（`-TopN 1`）。hosts 不是带优先级的故障转移配置，写多行既不能保证顺序，也不能保证首个失败就切换；多写反而可能让某些客户端先连一个不可用的地址。

## 它解决不了什么

- **对 PT 来说，下载不会变快**。hosts 只影响这些域名的网页和 tracker 通告；P2P 传输取决于做种人数、IPv6 和运营商互联。
- **IPv6 没有优选**。脚本只扫 IPv4。写入 A 记录后，Windows 通常不再使用 DNS 返回的 AAAA，所以浏览器会走 hosts 里的 IPv4；但应用自带解析器、DoH 可能有不同行为，`-CheckResolved` 可以看到系统实际返回的地址。BitTorrent 的 IPv6 对等连接不受影响。
- **结果有时效**。CF 路由、运营商互联和 zone 白名单都会变。选中的 IP 如果一直健康，不会因为「过了两周」自动变慢；但它一旦变慢或失效，hosts 不会自己更新，这时可能比走 DNS 还慢。建议每 1–2 周重跑，或者在站点打不开时先 `-Rollback`。
- **只支持 Windows**。依赖注册表里的 WinINET 代理设置、`Get-NetAdapter` 和 `ipconfig`。

## 最后

写这个工具的出发点不是「做出一个比在线优选更准的测速器」，而是把「测出来」到「写进去」之间那段最容易出事的环节补上：严格校验、增量更新、备份和回滚。速度是目标，但**可逆**才是它敢碰 hosts 的前提。

仓库在 [chenfangshuo/pt-cf-optimize](https://github.com/chenfangshuo/pt-cf-optimize)，MIT 协议，不附带 CloudflareSpeedTest 的代码或二进制。README 和 `docs/` 里有完整的参数表、导入说明和 FAQ；如果你也有几个 Windows 上访问慢得离谱的 CF 站点——PT、论坛、个人博客都算——又不想为了它们去动代理，可以直接从 `-DryRun` 开始。
