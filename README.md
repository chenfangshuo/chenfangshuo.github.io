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
