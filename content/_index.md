---
# 首页的 frontmatter 只用来给社交分享提供图。
#
# 为什么需要这个文件：Hugo 内建的 `_internal/opengraph.html` 和主题的
# twitter-cards.html 都通过 `_funcs/get-page-images` 取图，而它只认**页面自己**的
# images / cover，不认 [params.seo] 的 cover（那个只喂 JSON-LD 的 schema.org image）。
# 之前首页没有任何 frontmatter，分享出去就是 twitter:card=summary 且完全无图。
#
# title 不写：head 里 .IsHome 时标题一律取 .Site.Title，写了也没用。
images:
  - "/og-home.png"
---
