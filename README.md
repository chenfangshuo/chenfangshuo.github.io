# forsure.live

个人博客。由 **Hugo** 构建，主题 **FixIt**，部署到 GitHub Pages（自定义域名 `forsure.live`，前面有 Cloudflare 代理）。

> 2026-10 从 Hexo 7 + Fluid 1.9.6 迁移而来。旧源码保留在 `D:\Software\Hexo\blog`，
> 备份在 `D:\Software\Hexo\backups`。

---

## 版本锁定（重要）

这个站点的目标是「配好一次，长期不动」，所以**故意把版本钉死**：

| 组件 | 版本 | 锁定方式 |
|---|---|---|
| Hugo | `0.167.0`（**extended**） | 本机 winget 指定版本；CI 里写死在 `HUGO_VERSION` |
| Dart Sass | `1.105.1` | 本机解压版；CI 里写死在 `DART_SASS_VERSION` |
| FixIt 主题 | `v1.0.0-beta.1` | git submodule 的 gitlink SHA（`33433e37`） |

### ⚠️ 不要做的事

- **不要**运行 `git submodule update --remote` —— 会把主题升到最新，可能引入破坏性变更
- **不要**在 `.gitmodules` 里加 `branch = main` —— 锁点会失效
- **不要**引入官方 starter 模板的自动升级 workflow（`hugo-fixit-starter` 自带每日、
  `starter1` 自带每周自动升级主题）—— 与锁版本直接冲突
- **不要**把 Hugo 设成 `latest`

升级是**主动行为**：确认新版没问题后，显式 `git checkout <新 tag>` 并同步更新 CI 里的版本号。

查看当前锁定状态：

```bash
git submodule status          # 应显示 ... themes/FixIt (v1.0.0-beta.1)
hugo version                  # 应含 extended 与 v0.167.0
sass --version                # 1.105.1
```

---

## 本地写作与预览

```bash
hugo new content posts/my-post/index.md    # 新建文章（默认 draft: true，附带图片用包）
hugo server -D                             # 预览（-D 含草稿），http://localhost:1313/
hugo server                                # 预览，不含草稿

hugo --gc --minify                         # 生产构建，产物在 public/
```

### ⚠️ 为什么 `hugo server` 里看不到评论区

**这是主题有意为之，不是配置错了。** 主题的
`layouts/_partials/init/detection-env.html` 把整段评论配置包在
`{{- if hugo.IsProduction -}}` 里，所以开发环境下页面**完全不渲染评论容器**——
目的是避免本地测试时把测试评论写进你线上的 MongoDB。

想本地看到评论（含已有的历史评论），用生产环境跑：

```bash
hugo server -e production                  # 评论正常加载（只是别真的提交测试评论）
```

或者跑 `hugo --gc --minify` 后用任意静态服务器打开 `public/`。

发布流程：把想发的那篇 `draft` 改成 `false` → `git add` / `commit` / `push`。
CI 构建**不带** `--buildDrafts`，所以草稿永远不会被发到线上。

### 文章 front matter

```yaml
---
title: 标题
date: 2026-10-09T12:00:00+08:00
slug: my-post-name          # 决定 URL：/<slug>/  ← 保持与旧站一致的形状
draft: true
featured_image: featured-image.jpg   # 同目录下的封面图（也可留空）
tags: []
categories: []
---
```

- 文章放在 `content/posts/<名字>/index.md`，图片直接放同一目录，正文里用**相对文件名**引用：
  `![说明](screenshot.png)`
- 封面图推荐命名为 `featured-image.jpg`（主题按这个资源名自动识别）
- `slug` 决定最终 URL。因为 `[permalinks.page] posts = "/:slug/"`，文章都在根路径 `/<slug>/`

---

## 目录结构

```
hugo.toml                    站点配置（含从主题复制的结构性配置，见文件内说明）
assets/scss/custom.scss      自定义样式（滚动条、Twikoo 评论框、页脚心形 hover）
assets/js/custom.js          自定义脚本（首页 hitokoto 一言 + 注入雪花特效）
static/js/snow.js            雪花特效（DHTML Snowstorm，经典脚本）
static/images/               头像、友链图
static/favicon* apple-touch-icon.png
content/posts/…              文章
content/about|links|search/  关于 / 友链 / 搜索页
data/friends.yml             友链数据
themes/FixIt/                主题（submodule，锁在 v1.0.0-beta.1）
```

### 两处「刻意为之」，改动前请先读

1. **友链页在 `/links/` 而不是 FixIt 惯例的 `/friends/`。**
   旧站该路径下已有 2 条 Twikoo 评论；Twikoo 以页面路径为 key，换路径评论就失联。

2. **文章 slug 必须保持稳定，尤其是那篇老文章。**
   `/customize-some-effects-for-hexofluid/` 这个 URL 下挂着 11 条历史评论，
   改 URL = 丢评论。

---

## 外部服务

| 服务 | 用途 | 位置 |
|---|---|---|
| Twikoo | 评论 | `https://twikoo.forsure.live`（Vercel + MongoDB 自建） |
| hitokoto | 首页随机一言 | `assets/js/custom.js` |
| Cloudflare | DNS 代理 + TLS | 域名解析面板 |

### Twikoo 前端版本（已升级到 2.0.13）

主题 FixIt v1.0.0-beta.1 自带的是 **twikoo 2.0.12**。本站把它覆盖成了 **2.0.13**：

- 覆盖方式：在 `assets/lib/twikoo/twikoo.all.min.js` 放一份 2.0.13。
  **站点自己的 `assets/` 会遮蔽主题同路径的资源**，所以不需要改主题（submodule 保持干净），
  也不需要引入 CDN（你在中国大陆，jsDelivr 不稳，这是刻意的）。
- 升级原因：2.0.13 修了 **#1211 —— 评论里的图片/表情被宿主题的 `img{display:block}` 挤成块级**。
  FixIt 正好这么设（`main.min.css` 里有多条 `img{display:block}`），所以这个 bug 在我们站是真实存在的。
- 想退回主题自带版本：删掉 `assets/lib/twikoo/twikoo.all.min.js` 即可。
- **升级前请先核对类名**：自定义 CSS（`assets/scss/custom.scss`）依赖
  `.tk-input` / `.tk-textarea__inner` / `.tk-input__count` / `.tk-footer`。
  换版本前先 `grep -o 'tk-textarea__inner' <新文件> | wc -l` 确认还在，否则评论框样式会再次失效
  （1.6.x 的 Element UI 类名 `.el-textarea__inner` 就是这么没的）。
- 部署后记得 **purge Cloudflare 缓存**：该文件名不带 hash，CDN 可能继续返回旧的 2.0.12。

### ⚠️ 后端版本与前端不一致

云函数（`https://twikoo.forsure.live`，Vercel 部署）当前是 **1.6.26**，而前端是 2.0.13。
目前实际运行正常（评论能加载、能提交），Twikoo 前端会通过 `GET_FUNC_VERSION` 探测后端版本。
但 2.0.13 的另一个修复 #1220（评论列表查询不再读取整页文档）属于**服务端查询逻辑**，
只换前端不会生效。

官方文档明确要求**前后端版本保持一致**（"部署时请注意保持二者版本一致"），
所以这个 1.6.26 是整套里唯一掉队的部分（`1.6.26` 发布于 2023-11-27，将近三年）。

### 后端升级到 2.0.13（待办，需要你在 Vercel 操作）

好消息：**不需要迁移 MongoDB 数据**。1.6 → 2.0 的集合/字段模型没变，
官方也没有针对 Vercel + MongoDB 这条路径给出任何数据迁移步骤。
另外后台的配置项**没有删除或改名**（只有新增，如验证码/LLM/S3 等），
所以你现在 Twikoo 后台的既有设置都会保留。

步骤：

1. Vercel 控制台 → twikoo 项目 → **Deployments**
2. 最新那次部署右侧 `⋯` → **Redeploy**
3. 弹窗里**务必取消勾选 "Use existing Build Cache"** —— 否则 `twikoo-vercel@latest`
   不会被重新解析，等于白部署
4. 确认 Redeploy，然后访问 `https://twikoo.forsure.live`，应看到
   "Twikoo 云函数运行正常"
5. 2.0 要求运行时 **Node 20+**（不再支持 Node 16）

### 两条注意

- **i18n 副作用**：2.x 只把 `zh-CN` 和 `en` 打进主包，其它语言（`zh-HK`/`ja-JP` 等）
  会**按需从 `dist/locales/<lang>.js` 懒加载**。我们只 vendored 了主包 `twikoo.all.min.js`，
  所以如果哪天加了别的语言站点，那些语言会静默退回英文。本站只有 `zh-CN`（内置），不受影响。
- **2.0.x 迭代很急**（约三周发了 13 个补丁，期间出现过 pushoo、非 ASCII 表情名、
  Vercel/Netlify 提交阻塞等真实回归），2.0.13 又是当天发布的，几乎没有沉淀时间。
  反正上线还没做，建议放几天观察再一起部署。

- **旧站的 LeanCloud 浏览量已移除**（LeanCloud 公共服务于 2027-01-12 关停），
  页面不再显示阅读数。
- **GoatCounter 访问统计**待接入（还没注册）。
- **百度收录提交**待接入（验证文件是 `e90e165bb1c4fd5b1c1aa687053621ad`，
  主动推送的 token 必须走 GitHub Secret，不要写进仓库）。
- 主题默认的 Cookie 同意横幅已在 `hugo.toml` 里关闭。

---

## 部署（GitHub Actions）

源码在 `chenfangshuo.github.io` 仓库的 `main` 分支，由 GitHub Actions 构建并用
`actions/deploy-pages` 发布；Pages 的来源要设成 **GitHub Actions**（不是分支）。

CI 只需 **Hugo extended + Dart Sass** 两步 —— 不需要 Node、不需要 Go。
（`fixit-cli` 和内容加密组件才需要 Node，本站都不用；Hugo Modules 才需要 Go，本站用 submodule。）

### Cloudflare 注意

`forsure.live` 走 Cloudflare 代理，源站是 GitHub Pages。切换上线后：

- **purge 一次缓存**，否则 `Cache-Control: max-age=600` 可能让旧页面继续返回约 10 分钟
- **SSL/TLS 模式设为 Full (strict)**
- DNS 记录**不需要改**（仍然指向同一个 GitHub Pages 源站）

---

## 迁移遗留说明

- 旧站的 3 个自定义 CSS（`indeximg-hover` / `macpanel` / `lazyload-ani`）**有意未移植**，
  原因写在 `assets/scss/custom.scss` 末尾。其中 mac 风格代码块改用主题内置的
  `[params.codeblock] mode = "mac"`。
- 老文章里有个**旧站就有的笔误**：`[<sup>3</sup>]` 指向 `#refer-anchor-2` 而不是 `-3`。
  迁移时原样保留（保持内容一致），需要的话在
  `content/posts/customize-some-effects-for-hexofluid/index.md` 里改。
- 站内 `/authors/` `/collections/` 是主题 v1 自动生成的（源自 author 分类法），
  旧站没有这两个页面，属于新增。
