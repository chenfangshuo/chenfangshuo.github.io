#!/usr/bin/env python3
r"""
搜索引擎通知 —— forsure.live

用法（CI 里用 python3，纯标准库）：
    python3 scripts/seo-submit.py --mode changed --before <sha> --after <sha>
    python3 scripts/seo-submit.py --mode full
    python3 scripts/seo-submit.py --mode changed --before HEAD^ --after HEAD --dry-run

行为：
- changed：用 git diff 找出本次推送改过的 content/posts/*/index.md，读 front matter
  的 slug（缺失时用目录名），映射为 https://forsure.live/<slug>/；draft: true 跳过。
- full：抓线上 sitemap.xml 的 <loc>；百度只挑已发布文章 URL，IndexNow 推全部。
- 百度：只推文章 URL，默认最多 10 条（--max-baidu 可调）。
- IndexNow：changed 模式推变更文章 + 首页；full 模式推 sitemap 全部 URL。
- 网络/接口错误只打 warning，不阻断发布（脚本始终 exit 0）。

环境变量：
    BAIDU_TOKEN     百度主动推送 token（GitHub Secret）
    INDEXNOW_KEY    IndexNow key（公开值，同时是 static/<key>.txt 的文件名）
"""

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

# Windows 控制台默认 GBK，中文日志会乱码；CI 是 UTF-8，重设无副作用。
for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
CONTENT = ROOT / "content" / "posts"
SITE = "https://forsure.live"
HOST = "forsure.live"
BAIDU_ENDPOINT = "http://data.zz.baidu.com/urls"
INDEXNOW_ENDPOINT = "https://api.indexnow.org/indexnow"
ZERO_SHA = "0" * 40

FM_RE = re.compile(r"^---\s*\n(.*?)\n---\s*\n", re.S)
SLUG_RE = re.compile(r"""^slug:\s*["']?([^"'\s#]+)""", re.M)
DRAFT_RE = re.compile(r"^draft:\s*true\s*(?:#.*)?$", re.M | re.I)


def summary(line: str) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as f:
            f.write(line + "\n")


def notice(msg: str) -> None:
    print(f"::notice::{msg}")
    summary(f"- {msg}")


def warn(msg: str) -> None:
    print(f"::warning::{msg}")
    summary(f"- ⚠️ {msg}")


def dedupe(items: list[str]) -> list[str]:
    seen = set()
    out = []
    for item in items:
        if item not in seen:
            seen.add(item)
            out.append(item)
    return out


def parse_post(path: Path) -> str | None:
    """返回 slug；draft: true 或没有 front matter 时返回 None。"""
    text = path.read_text(encoding="utf-8", errors="replace")
    m = FM_RE.match(text)
    if not m:
        return None
    front = m.group(1)
    if DRAFT_RE.search(front):
        return None
    slug = SLUG_RE.search(front)
    return slug.group(1) if slug else path.parent.name


def all_published() -> dict[Path, str]:
    out = {}
    for path in sorted(CONTENT.glob("*/index.md")):
        slug = parse_post(path)
        if slug:
            out[path] = f"{SITE}/{slug}/"
    return out


def changed_urls(before: str, after: str) -> list[str]:
    if not before or before == ZERO_SHA or set(before) == {"0"}:
        return []
    try:
        result = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACMR", before, after, "--", "content/posts"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        )
    except subprocess.CalledProcessError as exc:
        warn(f"git diff 失败（before={before} after={after}）：{exc.stderr.strip()}")
        return []

    urls = []
    for line in result.stdout.splitlines():
        path = (ROOT / line.strip()).resolve()
        try:
            rel = path.relative_to(CONTENT)
        except ValueError:
            continue
        # 文章是 page bundle：封面、正文图片、内嵌脚本变了也算文章内容变更，
        # 统一映射到 content/posts/<slug>/index.md 的 slug。
        if len(rel.parts) < 2:
            continue
        index = CONTENT / rel.parts[0] / "index.md"
        if not index.is_file():
            continue
        slug = parse_post(index)
        if slug:
            urls.append(f"{SITE}/{slug}/")
    return dedupe(urls)


def fetch_sitemap() -> list[str]:
    try:
        # 带浏览器 UA：Cloudflare 会拦 Python 默认的 Python-urllib UA（实测 403）。
        req = urllib.request.Request(
            f"{SITE}/sitemap.xml",
            headers={
                "User-Agent": "Mozilla/5.0 (compatible; forsure.live-seo-submit/1.0)",
                "Accept": "application/xml,text/xml,*/*",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            xml = resp.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001 - 通知失败不应阻断发布
        warn(f"sitemap 获取失败：{exc}")
        return []
    return dedupe(re.findall(r"<loc>([^<]+)</loc>", xml))


def http_post(url: str, data: bytes, headers: dict[str, str], timeout: int = 30) -> tuple[int | None, str]:
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)


def submit_baidu(urls: list[str], max_urls: int, dry_run: bool) -> None:
    token = os.environ.get("BAIDU_TOKEN", "").strip()
    urls = dedupe(urls)[:max_urls]
    if not urls:
        notice("百度：没有文章 URL 需要提交")
        return
    if not token:
        notice("百度：BAIDU_TOKEN 未配置，跳过")
        return
    if dry_run:
        notice(f"百度 dry-run（{len(urls)} 条）：" + ", ".join(urls))
        return

    query = urllib.parse.urlencode({"site": HOST, "token": token})
    status, body = http_post(
        f"{BAIDU_ENDPOINT}?{query}",
        "\n".join(urls).encode("utf-8"),
        {"Content-Type": "text/plain"},
    )
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        data = None

    if isinstance(data, dict) and data.get("success"):
        notice(f"百度：成功 {data.get('success')} 条，剩余配额 {data.get('remain')}")
    elif isinstance(data, dict) and data.get("error"):
        warn(f"百度：error={data.get('error')} message={data.get('message', '')}")
    else:
        warn(f"百度：HTTP {status} 响应 {body[:300]}")

    if isinstance(data, dict):
        extra = {k: data[k] for k in ("not_same_site", "not_valid") if data.get(k)}
        if extra:
            notice(f"百度：未提交的 URL {json.dumps(extra, ensure_ascii=False)}")


def submit_indexnow(urls: list[str], dry_run: bool) -> None:
    key = os.environ.get("INDEXNOW_KEY", "").strip()
    urls = dedupe(urls)[:10000]
    if not urls:
        notice("IndexNow：没有 URL 需要提交")
        return
    if not key:
        notice("IndexNow：INDEXNOW_KEY 未配置，跳过")
        return
    if not re.fullmatch(r"[A-Za-z0-9-]{8,128}", key):
        warn("IndexNow：INDEXNOW_KEY 格式不合法（8-128 位字母/数字/短横线）")
        return

    payload = {
        "host": HOST,
        "key": key,
        "keyLocation": f"{SITE}/{key}.txt",
        "urlList": urls,
    }
    if dry_run:
        notice(f"IndexNow dry-run（{len(urls)} 条）：" + json.dumps(payload, ensure_ascii=False))
        return

    status, body = http_post(
        INDEXNOW_ENDPOINT,
        json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        {"Content-Type": "application/json; charset=utf-8"},
    )
    if status in (200, 202):
        notice(f"IndexNow：HTTP {status}，已接收 {len(urls)} 条")
    else:
        warn(f"IndexNow：HTTP {status} 响应 {body[:300]}")


def main() -> int:
    parser = argparse.ArgumentParser(description="提交变更 URL 到百度和 IndexNow")
    parser.add_argument("--mode", choices=("changed", "full"), default="changed")
    parser.add_argument("--before", default="")
    parser.add_argument("--after", default="HEAD")
    parser.add_argument("--max-baidu", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    if args.mode == "changed":
        article_urls = changed_urls(args.before, args.after)
        indexnow_urls = article_urls + ([f"{SITE}/"] if article_urls else [])
        if not article_urls:
            notice("没有文章变更，跳过百度和 IndexNow")
            return 0
    else:
        sitemap_urls = fetch_sitemap()
        published = set(all_published().values())
        article_urls = [url for url in sitemap_urls if url in published]
        indexnow_urls = sitemap_urls
        if not sitemap_urls:
            notice("sitemap 为空或获取失败，跳过")
            return 0

    notice(f"模式={args.mode}，文章 URL {len(article_urls)} 条，IndexNow URL {len(indexnow_urls)} 条")
    submit_indexnow(indexnow_urls, args.dry_run)
    submit_baidu(article_urls, args.max_baidu, args.dry_run)
    return 0


if __name__ == "__main__":
    sys.exit(main())
