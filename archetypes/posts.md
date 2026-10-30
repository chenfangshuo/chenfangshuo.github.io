---
title: "{{ replace .File.ContentBaseName "-" " " | title }}"
subtitle: ""
date: {{ .Date }}
slug: "{{ substr .File.UniqueID 0 7 }}"           # ← 必须改成有意义的小写英文：这串哈希就是 URL，改晚了 Twikoo 评论会失联
draft: true                                       # ← 发布前改 false。CI 不带 --buildDrafts，忘了就是静默不发
lightgallery: "force"                             # 正文图片灯箱；"force" 才能覆盖无 title 的图。没配图可删掉这行
description: ""
keywords: []
featured_image: ""                                # 1600x900，用 cover.py 生成
featured_image_preview: ""                        # 800x450。漏了这张，首页卡片会退回下发上面那张大图
tags: []
categories: []
---

<!--more-->
