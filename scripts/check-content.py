#!/usr/bin/env python3
r"""
发文安全网 —— fars.cc

把「静默失败」变成「会响的失败」。本站有两个坑，出错时本地完全看不出异常：

  1. `slug` 忘了改。archetypes/posts.md 生成的是 `{{ substr .File.UniqueID 0 7 }}`，
     也就是一串随机哈希（如 `ec86391`）。而 `[permalinks.page] posts = "/:slug/"`
     —— **slug 就是 URL**。Twikoo 以页面路径为 key，URL 一变评论全部失联。
  2. `draft: true` 忘了关。CI 跑的是 `hugo --gc --minify`，**不带 --buildDrafts**，
     忘了就是静默不发。

用法（只需要 Python 3 标准库，不需要 pip install）：
    python  scripts/check-content.py                 # CI 与本地都用这一条
    python3 scripts/check-content.py                 # CI 里是 python3（见下）
    python  scripts/check-content.py --strict        # 警告也当失败
    python  scripts/check-content.py --repo <路径>   # 指定站点根目录

退出码：0 = 通过（可能有警告）  1 = 有 ERROR  2 = 环境/用法问题

── 为什么让 Hugo 自己解析 front matter ──

slug 与 draft **不从文件里正则抠**，而是读 `hugo list all` 的 CSV。那是 Hugo 自己
的解析结果，所以这个检查和构建**不可能各说各话**。

slug 与 draft 决定了下面 `published` 的用法：`hugo list all` 含草稿，
`hugo list published` 只含会真正发布的。两者的差集就是「会被静默吞掉的文章」。

── 两条容易做错、会直接毁掉这个脚本的地方 ──

* **不要用 `subprocess.run(..., text=True)`。** 本机控制台是 GBK(cp936)，hugo 输出
  是 UTF-8，会在**读取线程**里抛 UnicodeDecodeError —— 注意它不会让 run() 失败，
  只是**静默丢输出**。CI 是 UTF-8 所以永远看不到这个 bug，只有本机会中招。
  必须显式 `.decode("utf-8")`。
* **不要 `out.split(",")`。** 用 `csv` 模块。标题里带逗号时手切会把所有列错位。

另外 `hugo list` 会去抢构建锁，所以一律带 `--noBuildLock` —— 否则你开着
`hugo server` 的时候跑这个脚本会假报错。

详见 MAINTENANCE.local.md「发文流程」。
"""

import csv
import io
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

# archetypes/posts.md 里 `{{ substr .File.UniqueID 0 7 }}` 生成的东西
HASH_SLUG = re.compile(r"^[0-9a-f]{7}$")
# 有意义的小写英文短横线
GOOD_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")

# 人工维护：只有明确确认过“历史上真的以这个哈希 URL 上线”的条目才登记在这里。
# 键是 (源文件路径, slug)，避免以后别的文章复用同一个 slug 时被一起豁免。
# 当前 6 篇文章都没有哈希 slug，所以保持为空。
LIVE_HASH_SLUGS = {
    # ("content/posts/foo/index.md", "ec86391"),
}

# 本站已启用的、没有内容源文件的 HTML 输出（home 的附加 output 与 Hugo 404）。
# 普通页面用 url: 覆盖到这些路径时，hugo list 里看不到冲突对象，需要单独登记。
RESERVED_HTML_TARGETS = {
    "/": "首页",
    "/archives/": "首页 archives 输出",
    "/offline/": "首页 offline 输出",
    "/link/": "首页 link 输出",
    "/posts/": "posts section 列表页",
    "/404.html": "Hugo 404",
}

IMG_MD = re.compile(r"!\[[^\]]*\]\(\s*([^)\s]+)")
LINK_MD = re.compile(r"(?<!!)\[[^\]]*\]\(\s*([^)\s]+)")
INLINE_CODE = re.compile(r"`[^`\n]*`")
FENCE = re.compile(r"^\s*(```|~~~)")

# 这些前缀的引用不是「包内文件」，跳过
SKIP_REF = ("http://", "https://", "//", "mailto:", "tel:", "data:", "about:", "#")


def run_hugo(repo: Path, sub: str) -> list:
    """跑 `hugo list <sub>` 并返回 CSV 行。见文件头：必须显式 utf-8 解码。"""
    try:
        proc = subprocess.run(
            ["hugo", "list", sub, "--noBuildLock"],
            cwd=str(repo), capture_output=True,
        )
    except FileNotFoundError:
        print("FAIL  PATH 上找不到 hugo。CI 里 Hugo 由前面的步骤装好；本机看 MAINTENANCE.local.md。")
        raise SystemExit(2)
    if proc.returncode != 0:
        print(f"FAIL  `hugo list {sub}` 退出码 {proc.returncode}:")
        print("      " + proc.stderr.decode("utf-8", "replace").strip().replace("\n", "\n      "))
        raise SystemExit(2)
    text = proc.stdout.decode("utf-8")          # ← 不要改成 text=True
    return list(csv.DictReader(io.StringIO(text)))


def split_front_matter(text: str):
    """返回 (front_matter 文本, 正文, 正文起始行号)。本站用 YAML 的 `---` 围栏。"""
    if not text.startswith("---"):
        return "", text, 1
    lines = text.splitlines(keepends=True)
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == "---":
            return "".join(lines[1:i]), "".join(lines[i + 1:]), i + 2
    return "", text, 1


def scalar(fm: str, key: str) -> str:
    r"""
    从 front matter 里取一个标量值。**必须处理行尾注释** —— 本站的封面字段就长这样：

        featured_image: featured-image.webp          # 文章封面 1600x900（…）

    天真的 `^key:\s*(.+)$` 会把注释一起当成文件名，于是报「文件不存在」的假错。
    YAML 里 `#` 只有**前面有空白**时才是注释，所以用 `\s+#` 切 —— 这样引号里的
    `#` 和 URL 的 `#frag` 都能保住。
    """
    m = re.search(rf"^{re.escape(key)}:\s*(.*)$", fm, re.M)
    if not m:
        return ""
    v = m.group(1).strip()
    if v[:1] in ('"', "'"):
        q = v[0]
        end = v.find(q, 1)
        return v[1:end] if end > 0 else v[1:]
    return re.split(r"\s+#", v, maxsplit=1)[0].strip()


def body_refs(body: str):
    """正文里指向「包内文件」的相对引用。跳过围栏代码块、行内代码与外部链接。"""
    out = []
    in_fence = False
    for n, line in enumerate(body.splitlines(), 1):
        if FENCE.match(line):
            in_fence = not in_fence
            continue
        if in_fence:
            continue
        line = INLINE_CODE.sub("``", line)
        for tgt in IMG_MD.findall(line) + LINK_MD.findall(line):
            if tgt.startswith(SKIP_REF):
                continue
            if tgt.split("#")[0].split("?")[0].lower().endswith((".md", ".markdown")):
                continue          # leaf bundle 的 .md 不会被复制到 public/
            out.append((n, tgt))
    return out


def main() -> int:
    # GBK 控制台下打印中文以外的字符（框线、emoji）会抛 UnicodeEncodeError 打断输出
    try:
        sys.stdout.reconfigure(errors="replace")
    except Exception:
        pass

    argv = sys.argv[1:]
    strict = "--strict" in argv
    if "--repo" in argv:
        repo = Path(argv[argv.index("--repo") + 1]).resolve()
    else:
        repo = Path(__file__).resolve().parent.parent

    if not (repo / "hugo.toml").exists():
        print(f"FAIL  {repo} 看起来不是站点根目录（没有 hugo.toml）")
        return 2

    allrows = run_hugo(repo, "all")
    pubrows = run_hugo(repo, "published")
    # 只要博客文章：kind=page、section=posts。这样自动排除 about/links/search/
    # content/_index.md（它的 permalink 是 /search.json）以及主题的 term 页。
    posts = [r for r in allrows
             if r.get("kind") == "page" and r.get("section") == "posts"]
    published = {r["path"] for r in pubrows}

    print(f"[1] hugo list all / published : {len(allrows)} / {len(pubrows)} 行"
          f"，其中文章 {len(posts)} 篇")

    errors, warns = [], []

    def flag(level, rule, path, msg):
        (errors if level == "ERROR" else warns).append((rule, path, msg))

    counts = {}

    # --- 规则 ------------------------------------------------ 每条的检查数记进 counts
    # URL 碰撞：用 Hugo 解析后的 HTML permalink 分组，覆盖 posts、about/links 等普通页。
    # 不自己拼 slug；/x/ 与 /x/index.html 视为同一输出；home 的 search.json 不是 HTML，排除。
    def html_target(permalink: str) -> str:
        p = urlparse(permalink).path
        if p.endswith("/index.html"):
            p = p[: -len("index.html")]
        if p.endswith("/") or p.endswith(".html"):
            return p
        return ""

    n = 0
    targets = {}
    for r in allrows:
        if r.get("kind") not in ("page", "taxonomy", "term", "section"):
            continue
        if r["path"] not in published:
            continue  # 草稿/未来页面不参与本次发布，不应被算碰撞
        key = html_target(r.get("permalink", ""))
        if not key:
            continue
        targets.setdefault(key, []).append(r["path"])

    def is_tag_term_owner(path: str) -> bool:
        parts = Path(path).parts
        return (
            len(parts) == 4
            and parts[0] == "content"
            and parts[1] == "tags"
            and parts[3] == "_index.md"
        )

    for key, paths in sorted(targets.items()):
        unique = sorted(set(paths))
        # 多个不同源文件输出到同一路径，永远是碰撞；归属豁免不能跳过这条。
        if len(unique) > 1:
            n += 1
            flag("ERROR", "permalink-collision", " + ".join(unique),
                 f"多个页面输出到同一路径 {key}")
            continue
        owner = unique[0]
        if key.startswith("/tags/"):
            # 合法 taxonomy 索引（content/tags/_index.md）和 term 自身
            # （content/tags/<slug>/_index.md）允许；其他页占用 /tags/ 命名空间
            # 一律报错，不再靠手写 YAML 解析猜标签。
            if key == "/tags/" and owner == "content/tags/_index.md":
                continue
            if is_tag_term_owner(owner):
                continue
            n += 1
            flag("ERROR", "permalink-collision", owner,
                 f"页面输出到 /tags/ 命名空间（{key}），可能与自动标签 term 冲突")
        elif key == "/posts/" and owner == "content/posts/_index.md":
            continue  # posts section 自己的元数据页
        elif key in RESERVED_HTML_TARGETS:
            n += 1
            flag("ERROR", "permalink-collision", owner,
                 f"页面输出路径 {key} 与{RESERVED_HTML_TARGETS[key]}冲突")
    counts["permalink-collision"] = n

    n = 0
    for r in posts:
        slug, path = r.get("slug", ""), r["path"]
        if not HASH_SLUG.match(slug):
            continue
        n += 1
        if (path, slug) in LIVE_HASH_SLUGS:
            # 只有人工确认过的历史 URL 才降级；改名会孤儿化历史评论
            flag("WARN", "slug-hash-live", path,
                 f'slug 是随机哈希 "{slug}"（已登记为历史 URL，改名会让现有评论失联，'
                 f'故只警告不拦）')
        else:
            # 新文章不管 draft 是什么都必须改：hugo list published 只知道“本次会发布”，
            # 不知道这个 URL 历史上有没有上线。
            flag("ERROR", "slug-hash-blocked", path,
                 f'slug 还是模板生成的随机哈希 "{slug}"；URL 会变成 /{slug}/，'
                 f'且以后改名会让 Twikoo 评论失联。首次发文必须改；'
                 f'如确属历史已上线 URL，人工登记到 LIVE_HASH_SLUGS')
    counts["slug-hash"] = n

    n = 0
    for r in posts:
        slug = r.get("slug", "")
        if not slug or HASH_SLUG.match(slug):
            continue
        n += 1
        if not GOOD_SLUG.match(slug):
            flag("WARN", "slug-format", r["path"],
                 f'slug "{slug}" 不是小写英文短横线；URL 会带大写/下划线等字符，'
                 f'不影响访问但不便于分享与排错')
    counts["slug-format"] = n

    n = 0
    for r in posts:
        if r["path"] not in published:
            n += 1
            flag("ERROR", "draft-true", r["path"],
                 "未发布（draft: true / 未来日期 / 已过期）。CI 不带 --buildDrafts "
                 "→ 这篇会被静默吞掉。若是有意的 WIP，在 commit message 里"
                 "**独占一行**写 [skip-content-check]")
    counts["draft-true"] = n

    n = 0
    for r in posts:
        path = r["path"]
        src = repo / path
        if not src.exists():
            continue
        fm, body, _ = split_front_matter(src.read_text(encoding="utf-8"))
        bundle = src.parent
        for key, level, rule in (
            ("featured_image", "ERROR", "featured-image-missing"),
            ("featured_image_preview", "WARN", "featured-preview-missing"),
        ):
            val = scalar(fm, key)
            if not val or val.startswith(("http://", "https://", "data:", "//", "/")):
                continue          # 远程/内联/全局资源交给 Hugo 自己解析
            n += 1
            if not (bundle / val).exists():
                flag(level, rule, path, f"{key} 指向的 {val} 不在文章目录里")
    counts["featured-image"] = n

    # 正文引用只查**未发布**的文章：已发布的那部分交给 check-links.py 在真正的
    # public/ 产物上查，避免同一处断链被两个门各报一次。
    n = 0
    for r in posts:
        if r["path"] in published:
            continue
        src = repo / r["path"]
        if not src.exists():
            continue
        _, body, off = split_front_matter(src.read_text(encoding="utf-8"))
        bundle = src.parent
        for line, tgt in body_refs(body):
            n += 1
            # 先切 query/fragment，再对 URL 的 path 只解码一次
            rel = unquote(tgt.split("#")[0].split("?")[0])
            if rel and not (bundle / rel).exists():
                flag("ERROR", "body-ref-missing", r["path"],
                     f"{off + line - 1} 行的引用 {tgt} 在文章目录里找不到")
    counts["body-ref"] = n

    n = 0
    for r in posts:
        src = repo / r["path"]
        if not src.exists():
            continue
        _, body, _ = split_front_matter(src.read_text(encoding="utf-8"))
        n += 1
        if "<!--more-->" not in body:
            flag("WARN", "more-marker-missing", r["path"],
                 "正文里没有 <!--more-->；摘要会退化成 Hugo 的自动截断")
    counts["more-marker"] = n

    n = 0
    for r in posts:
        slug, permalink = r.get("slug", ""), r.get("permalink", "")
        if not slug or not permalink:
            continue
        n += 1
        if not permalink.endswith(f"/{slug}/"):
            flag("WARN", "permalink-drift", r["path"],
                 f"permalink {permalink} 与 slug 对不上 —— front matter 里是不是有 "
                 f"url: 覆盖？（那会绕过 slug，且让评论失联）")
    counts["permalink"] = n

    # --- 报告 ------------------------------------------------
    # 一个小节可以对应多条规则（第 2 节就有「未发布」与「已发布」两种严重度）
    def report(sec, ids, label, key, unit="项"):
        got = [x for x in errors + warns if x[0] in ids]
        bad = [x for x in errors if x[0] in ids]
        state = "FAIL" if bad else ("WARN" if got else "OK")
        print(f"[{sec}] {label:26s}: {counts[key]:>3} {unit}  {state}")
        for _, path, msg in got:
            print(f"      {path}")
            print(f"        {msg}")

    report(2, ("slug-hash-blocked", "slug-hash-live"), "slug 是随机哈希", "slug-hash", "篇")
    report("2b", ("slug-format",), "slug 格式", "slug-format", "篇")
    report(3, ("draft-true",), "draft-true / 未发布", "draft-true", "篇")
    report(4, ("featured-image-missing", "featured-preview-missing"),
           "featured-image 存在", "featured-image", "个声明")
    report(5, ("body-ref-missing",), "正文相对引用存在", "body-ref", "处引用（仅未发布）")
    report(6, ("more-marker-missing",), "有 <!--more-->", "more-marker", "篇")
    report(7, ("permalink-drift",), "permalink 与 slug 一致", "permalink", "篇")
    report("7b", ("permalink-collision",), "输出路径唯一", "permalink-collision", "项")

    print()
    if errors:
        print(f"结论: FAIL —— {len(errors)} 个错误、{len(warns)} 个警告，不要发布")
        return 1
    if warns and strict:
        print(f"结论: FAIL（--strict）—— {len(warns)} 个警告被当成错误")
        return 1
    tail = f"（{len(warns)} 条警告；--strict 可升级为失败）" if warns else ""
    print(f"结论: OK 通过{tail}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
