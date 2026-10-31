#!/usr/bin/env python3
"""Validate a built Jekyll site before it is deployed to GitHub Pages.

The deploy job only runs if this script exits 0. Checks:
  1. README markers  - README.md has the activity markers, in order, with entries.
  2. Homepage        - _site/index.html exists and rendered the README include.
  3. HTML structure  - every page has the basic skeleton, balanced tags, unique ids.
  4. Internal links  - every href/src inside the site points to a file that exists
                       (and #fragments point to an existing id).
  5. External links  - every http(s) link answers with 2xx/3xx.
                       429/403 rate limits are reported as warnings, not failures.

Usage:
  python3 scripts/validate_site.py --site _site --readme README.md --base-path /devops-pages-lab
Only the Python standard library is used.
"""
import argparse
import os
import sys
import time
import urllib.error
import urllib.request
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlsplit

START = "<!--START_SECTION:activity-->"
END = "<!--END_SECTION:activity-->"

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "param", "source", "track", "wbr"}
# end tags that HTML allows to be omitted
OPTIONAL_END = {"p", "li", "dt", "dd", "option", "optgroup", "tr", "td", "th",
                "thead", "tbody", "tfoot", "colgroup", "rt", "rp", "head", "body", "html"}

errors, warnings = [], []


def fail(check, msg):
    errors.append(f"[{check}] {msg}")


def warn(check, msg):
    warnings.append(f"[{check}] {msg}")


class Page(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.problems = [], []
        self.ids, self.dup_ids = set(), set()
        self.links = []  # (tag, attr, value, line)
        self.seen = set()
        self.doctype = False
        self.text = []
        self.li_count = 0

    def handle_decl(self, decl):
        if decl.lower().startswith("doctype"):
            self.doctype = True

    def handle_starttag(self, tag, attrs):
        self.seen.add(tag)
        a = dict(attrs)
        if "id" in a and a["id"]:
            if a["id"] in self.ids:
                self.dup_ids.add(a["id"])
            self.ids.add(a["id"])
        if tag == "a" and a.get("name"):
            self.ids.add(a["name"])
        for attr in ("href", "src"):
            if a.get(attr) is not None and tag in ("a", "link", "script", "img", "iframe", "source"):
                self.links.append((tag, attr, a[attr], self.getpos()[0]))
        if tag == "li":
            self.li_count += 1
        if tag not in VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID and self.stack and self.stack[-1][0] == tag:
            self.stack.pop()

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not any(t == tag for t, _ in self.stack):
            self.problems.append(f"line {self.getpos()[0]}: stray </{tag}>")
            return
        while self.stack:
            t, line = self.stack.pop()
            if t == tag:
                break
            if t not in OPTIONAL_END:
                self.problems.append(f"line {line}: <{t}> is never closed (closed by </{tag}>)")

    def handle_data(self, data):
        self.text.append(data)

    def close(self):
        super().close()
        for t, line in self.stack:
            if t not in OPTIONAL_END:
                self.problems.append(f"line {line}: <{t}> is never closed")


def check_readme(path):
    try:
        text = open(path, encoding="utf-8").read()
    except OSError as e:
        fail("readme", f"cannot read {path}: {e}")
        return
    if text.count(START) != 1 or text.count(END) != 1:
        fail("readme", f"expected exactly one {START} and one {END} "
                       f"(found {text.count(START)} and {text.count(END)})")
        return
    s, e = text.index(START), text.index(END)
    if e < s:
        fail("readme", "END marker comes before START marker")
        return
    body = [l for l in text[s + len(START):e].splitlines() if l.strip()]
    if not body:
        warn("readme", "activity section is empty (the activity-log workflow has not filled it yet)")
    print(f"  readme: markers OK, {len(body)} activity line(s)")


def parse_pages(site):
    pages = {}
    for root, _, files in os.walk(site):
        for f in files:
            if f.endswith(".html"):
                p = os.path.join(root, f)
                pg = Page()
                pg.feed(open(p, encoding="utf-8", errors="replace").read())
                pg.close()
                pages[os.path.relpath(p, site)] = pg
    return pages


def check_homepage(site, pages):
    pg = pages.get("index.html")
    if pg is None:
        fail("homepage", f"{site}/index.html was not built")
        return
    text = "".join(pg.text)
    if "{%" in text or "include_relative" in text:
        fail("homepage", "Liquid tag was not rendered - is Jekyll running?")
    if "Recent activity" not in text:
        fail("homepage", "README content (\"Recent activity\") is missing from the homepage")
    print(f"  homepage: rendered, {pg.li_count} list item(s)")


def check_structure(pages):
    for rel, pg in pages.items():
        if not pg.doctype:
            fail("html", f"{rel}: missing <!DOCTYPE html>")
        for tag in ("html", "head", "title", "body"):
            if tag not in pg.seen:
                fail("html", f"{rel}: missing <{tag}>")
        for p in pg.problems:
            fail("html", f"{rel}: {p}")
        for i in sorted(pg.dup_ids):
            fail("html", f"{rel}: duplicate id=\"{i}\"")
    print(f"  html: {len(pages)} page(s) checked")


def resolve_internal(site, base_path, page_rel, url):
    """Map an internal URL to a file path inside the built site."""
    parts = urlsplit(url)
    path = unquote(parts.path)
    if path.startswith("/"):
        bp = base_path.rstrip("/")
        if bp and (path == bp or path.startswith(bp + "/")):
            path = path[len(bp):]
        target = path.lstrip("/")
    else:
        page_dir = os.path.dirname(page_rel)
        target = os.path.normpath(os.path.join(page_dir, path)) if path else page_rel
    full = os.path.join(site, target)
    if os.path.isdir(full) or target.endswith("/") or target in ("", "."):
        full = os.path.join(full, "index.html")
    if not os.path.splitext(full)[1] and not os.path.exists(full) and os.path.exists(full + ".html"):
        full = full + ".html"  # Jekyll pretty URLs
    return full, parts.fragment


def check_links(site, base_path, pages, check_external):
    external = {}
    n_int = 0
    for rel, pg in pages.items():
        for tag, attr, url, line in pg.links:
            u = url.strip()
            if not u or u.startswith(("mailto:", "tel:", "javascript:", "data:")):
                continue
            if u.startswith("//"):
                u = "https:" + u
            if u.startswith(("http://", "https://")):
                external.setdefault(u.split("#")[0], []).append(f"{rel}:{line}")
                continue
            n_int += 1
            full, frag = resolve_internal(site, base_path, rel, u)
            if not os.path.exists(full):
                fail("links", f"{rel}:{line} <{tag} {attr}=\"{url}\"> -> {os.path.relpath(full, site)} does not exist")
                continue
            if frag and full.endswith(".html"):
                target = pages.get(os.path.relpath(full, site))
                if target is not None and frag not in target.ids:
                    fail("links", f"{rel}:{line} <{tag} {attr}=\"{url}\"> -> #{frag} not found")
    print(f"  links: {n_int} internal link(s) checked")
    if not check_external:
        print("  links: external check skipped")
        return
    for url, where in sorted(external.items()):
        status = fetch(url)
        if isinstance(status, int) and 200 <= status < 400:
            continue
        if status in (403, 429):
            warn("links", f"{url} -> HTTP {status} (rate limited, not counted as broken)")
        else:
            fail("links", f"{url} -> {status} (used in {', '.join(where[:3])})")
    print(f"  links: {len(external)} external link(s) checked")


def fetch(url, tries=3):
    last = None
    for i in range(tries):
        for method in ("HEAD", "GET"):
            req = urllib.request.Request(url, method=method, headers={"User-Agent": "pages-gate/1.0"})
            try:
                with urllib.request.urlopen(req, timeout=15) as r:
                    return r.status
            except urllib.error.HTTPError as e:
                last = e.code
                if e.code in (405, 501) and method == "HEAD":
                    continue  # retry with GET
                if e.code == 404 or e.code == 410:
                    return e.code
                break
            except Exception as e:  # DNS, timeout, TLS
                last = type(e).__name__
                break
        time.sleep(2 * (i + 1))
    return last


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--site", default="_site")
    ap.add_argument("--readme", default="README.md")
    ap.add_argument("--base-path", default="")
    ap.add_argument("--no-external", action="store_true")
    a = ap.parse_args()

    print("Validating built site before deploy:")
    check_readme(a.readme)
    pages = parse_pages(a.site)
    check_homepage(a.site, pages)
    check_structure(pages)
    check_links(a.site, a.base_path, pages, not a.no_external)

    for w in warnings:
        print("WARN  " + w)
    for e in errors:
        print("FAIL  " + e)
    if errors:
        print(f"\nGATE CLOSED: {len(errors)} problem(s). Deploy is blocked.")
        return 1
    print("\nGATE OPEN: all checks passed. Deploy may proceed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
