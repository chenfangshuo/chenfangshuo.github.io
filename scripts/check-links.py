#!/usr/bin/env python3
r"""
站内死链检查 —— forsure.live

在**构建产物** `public/` 上查死链，不联网。改 URL / 挪 slug / 动主题配置之后跑一次。

用法（只需要 Python 3 标准库）：
    python  scripts/check-links.py                       # 查 public/
    python  scripts/check-links.py --public public       # 同上，显式
    python  scripts/check-links.py --no-anchors          # 跳过 #片段 检查
    python  scripts/check-links.py --quiet-ok            # 干净时只打一行

退出码：0 = 通过   1 = 有死链   2 = 环境/用法问题

── ⚠️ 纯正则会做成一个「永远报 0」的空转检查 ──

站点是 `hugo --gc --minify` 构建的，**压缩器会把属性引号去掉**：

    <a href=/about/>   <script src=/js/main.min.<sha>.js>

实测 `public/` 里带引号的引用 17 个、**裸属性值 785 个**。只用引号正则的话，
你只看到 2% 的链接，然后它会打印「0 个死链」—— 比没有检查更糟，因为它给你
一个假的安心。所以这里用 `html.parser` 解析，不用正则。

同理三条**顺序**上的坑，弄反就是上百条误报：

  1. `href="/"` 是每页都有的站标题链接，必须解析成 public/index.html，
     **不能**当成「当前页」。
  2. `?query` 要先切掉再解析，否则 `/favicon.svg?v=1` 会误报。
  3. `#片段` 是**百分号编码**的（`#%e5%ae%8c…`），而目标里的 id 是裸 UTF-8
     （`id=完整脚本`），必须先 `unquote()` 才能对上。

── 与 check-content.py 的分工 ──

本脚本只认 `public/` 产物。草稿里的相对引用由 check-content.py 管（草稿还没有
产物可查）；已发布文章则由本脚本在真正的产物上查。两者不重复报同一处。

── 已知局限（本地 vs CI）──

Hugo **不删** public/ 里的旧文件：现在 `public/css/` 就躺着 5 个不同 hash 的
custom.min.*.css，只有最新的那个被引用。这对本脚本无害（本脚本只解析 HTML 里
出现的引用，不枚举文件），但它意味着**本地的 public/ 若没重建，可能让一条死链
「通过」**（旧的 <old-slug>/index.html 还在）。CI 是全新检出 + 全新构建，
没有这个问题。所以：本地跑之前先 `.\scripts\hugo-build.ps1`。
"""

import re
import sys
from collections import defaultdict
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlparse

SITE_HOST = "forsure.live"
SKIP_SCHEMES = ("mailto", "tel", "data", "javascript", "about", "blob", "ftp", "file", "ws", "wss")
CSS_URL = re.compile(r"""url\(\s*['"]?([^'")]+)['"]?\s*\)""", re.I)
# `(?<![\w-])` 很关键：否则 `data-id=` / `aria-name=` 也会被当成锚点目标，
# 于是检查变宽松、真断的锚点反而漏掉
ID_ATTR = re.compile(r"""(?<![\w-])(?:id|name)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'`=<>]+))""", re.I)


class RefCollector(HTMLParser):
    """收集 href / src / srcset。用解析器而不是正则 —— 见文件头。"""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.refs = []          # [(attr, 原始值)]

    def handle_starttag(self, tag, attrs):
        for name, value in attrs:
            if value is None:
                continue
            if name in ("href", "src"):
                self.refs.append((name, value))
            elif name == "srcset":
                # "a.png 1x, b.png 2x" —— 取每个候选的第一个 token
                for part in value.split(","):
                    cand = part.strip().split()[0] if part.strip() else ""
                    if cand:
                        self.refs.append((name, cand))

    # 不关心标签内容，避免把正文里的 < 当标签


def collect_html_refs(path: Path):
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    p = RefCollector()
    try:
        p.feed(text)
    except Exception:
        pass
    return p.refs


class Resolver:
    def __init__(self, public: Path):
        self.public = public
        self.files = {p.relative_to(public).as_posix()
                      for p in public.rglob("*") if p.is_file()}
        self._ids = {}

    def exists(self, rel: str) -> bool:
        if rel in self.files:
            return True
        if rel == "":
            return "index.html" in self.files
        base = rel.rstrip("/")
        return f"{base}/index.html" in self.files or f"{base}.html" in self.files

    def normalize(self, rel: str) -> str:
        """把 /about/ 或 /about 归一成实际存在的那个文件路径（用于锚点检查）。"""
        if rel in self.files:
            return rel
        base = rel.rstrip("/")
        if f"{base}/index.html" in self.files:
            return f"{base}/index.html"
        if f"{base}.html" in self.files:
            return f"{base}.html"
        if rel in ("", "/") and "index.html" in self.files:
            return "index.html"
        return ""

    def anchors(self, rel: str) -> set:
        if rel not in self._ids:
            fp = self.public / rel
            ids = set()
            if fp.exists():
                txt = fp.read_text(encoding="utf-8", errors="replace")
                for m in ID_ATTR.finditer(txt):
                    ids.add(next(g for g in m.groups() if g is not None))
            self._ids[rel] = ids
        return self._ids[rel]


def classify(raw: str, page_rel: str):
    """返回 ('internal', 目标相对 public 的路径, 片段) / ('skip', None, None)"""
    v = raw.strip()
    if not v or v.startswith("#"):
        return "fragment", page_rel, v[1:] if v else ""
    u = urlparse(v)
    if u.scheme and u.scheme.lower() not in ("http", "https"):
        if u.scheme.lower() in SKIP_SCHEMES:
            return "skip", None, None
        return "skip", None, None
    if v.startswith("//"):
        return "skip", None, None                      # 协议相对，交给外链
    if u.scheme in ("http", "https"):
        if u.netloc and u.netloc.lower() not in (SITE_HOST, "www." + SITE_HOST):
            return "skip", None, None                  # 真外链，本脚本不查
        path, frag = u.path, u.fragment
    else:
        path, frag = u.path, u.fragment

    # 切掉 ?query **在解析之前**（见文件头第 2 条）
    path = path.split("?")[0]

    if path == "":
        return ("fragment" if frag else "skip"), page_rel if frag else None, frag
    if path.startswith("/"):
        return "internal", path.lstrip("/"), frag
    # 相对：相对当前页所在目录
    base = Path(page_rel).parent
    parts = []
    for seg in (base / path).as_posix().split("/"):
        if seg == "..":
            if parts:
                parts.pop()
        elif seg not in (".", ""):
            parts.append(seg)
    return "internal", "/".join(parts), frag


def scan(public: Path, check_anchors: bool, with_css: bool):
    r = Resolver(public)
    broken = defaultdict(set)      # (kind, target, frag) -> {pages}
    counts = defaultdict(int)

    for html in sorted(public.rglob("*.html")):
        page = html.relative_to(public).as_posix()
        for _attr, raw in collect_html_refs(html):
            kind, target, frag = classify(raw, page)
            if kind == "skip":
                counts["跳过（外链/非 http）"] += 1
                continue
            counts["站内"] += 1
            if not r.exists(target):
                broken[("文件", target, "")].add(page)
                continue
            if check_anchors and frag:
                counts["带片段的引用"] += 1
                rel = r.normalize(target)
                if rel and unquote(frag) not in r.anchors(rel):
                    broken[("锚点", target, unquote(frag))].add(page)

    # CSS 里的 url()：只扫**被某些 HTML 引用到的** CSS，避开 public/ 里的陈旧残留
    if with_css:
        reachable = set()
        for html in public.rglob("*.html"):
            page = html.relative_to(public).as_posix()
            for _attr, raw in collect_html_refs(html):
                kind, target, _frag = classify(raw, page)
                if kind == "internal" and target.endswith(".css") and r.exists(target):
                    reachable.add(r.normalize(target))
        for rel in sorted(reachable):
            fp = public / rel
            txt = fp.read_text(encoding="utf-8", errors="replace")
            for m in CSS_URL.finditer(txt):
                v = m.group(1).strip()
                if not v or v.startswith(("data:", "#")):
                    continue
                counts["CSS url()"] += 1
                tgt = v.split("?")[0].split("#")[0]
                if tgt.startswith("/"):
                    tgt = tgt.lstrip("/")
                else:
                    tgt = (Path(rel).parent / tgt).as_posix()
                    parts = []
                    for seg in tgt.split("/"):
                        if seg == "..":
                            if parts:
                                parts.pop()
                        elif seg != ".":
                            parts.append(seg)
                    tgt = "/".join(parts)
                if not r.exists(tgt):
                    broken[("CSS", tgt, "")].add(rel)
        counts["可达 CSS"] = len(reachable)

    return broken, counts


def main() -> int:
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    argv = sys.argv[1:]
    if "--public" in argv:
        public = Path(argv[argv.index("--public") + 1]).resolve()
    else:
        public = Path(__file__).resolve().parent.parent / "public"
    check_anchors = "--no-anchors" not in argv
    with_css = "--no-css" not in argv
    quiet_ok = "--quiet-ok" in argv

    if not public.is_dir():
        print(f"FAIL  {public} 不存在。先构建：.\\scripts\\hugo-build.ps1")
        return 2

    broken, counts = scan(public, check_anchors, with_css)
    pages = len(list(public.rglob("*.html")))

    if quiet_ok and not broken:
        print(f"OK  {counts.get('站内', 0)} 个站内引用无死链（{pages} 页）")
        return 0

    print(f"[1] 扫过 {pages} 个 html，{counts.get('站内', 0)} 个站内引用"
          f"（另跳过 {counts.get('跳过（外链/非 http）', 0)} 个外链/非 http）")
    if with_css:
        print(f"[2] CSS: 扫了 {counts.get('可达 CSS', 0)} 个可达文件、"
              f"{counts.get('CSS url()', 0)} 个 url()")
    if check_anchors:
        print(f"[3] 其中带 #片段 的: {counts.get('带片段的引用', 0)}")

    print()
    if not broken:
        print(f"结论: OK 通过 —— {counts.get('站内', 0)} 个站内引用全部有对应产物")
        return 0

    print(f"结论: FAIL —— {len(broken)} 处死链")
    for (kind, target, frag) in sorted(broken):
        where = sorted(broken[(kind, target, frag)])
        label = f"{target}#{frag}" if frag else target
        print(f"  [{kind}] {label}")
        for w in where[:4]:
            print(f"        <- {w}")
        if len(where) > 4:
            print(f"        <- … 另 {len(where) - 4} 个页面")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
