"""
将渲染好的报纸网页写入站点目录（默认 docs/，供 GitHub Pages 'main /docs' 使用），
维护：dated 文件 + index.html(最新) + archive.html(往期索引)，并可选 git 提交推送。
"""

from __future__ import annotations

import logging
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.models import Digest

from .paper import render_archive, render_paper

logger = logging.getLogger(__name__)

_DATE_FILE_RE = re.compile(r"^(\d{4}-\d{2}-\d{2})\.html$")


@dataclass
class PublishResult:
    page_path: Path
    index_path: Path
    archive_path: Path
    git_pushed: bool = False
    git_message: str | None = None


def _digest_date(digest: Digest) -> str:
    ga = digest.generated_at
    if ga:
        try:
            return datetime.fromisoformat(ga.replace("Z", "+00:00")).date().isoformat()
        except ValueError:
            pass
    return datetime.now().date().isoformat()


def _collect_archive(papers_dir: Path) -> list[tuple[str, str]]:
    """扫描 papers/ 下的 dated 文件，返回 [(date, 'papers/xxx.html')]，新到旧。"""
    entries: list[tuple[str, str]] = []
    if papers_dir.is_dir():
        for p in papers_dir.iterdir():
            m = _DATE_FILE_RE.match(p.name)
            if m:
                entries.append((m.group(1), f"papers/{p.name}"))
    entries.sort(key=lambda e: e[0], reverse=True)
    return entries


def _run_git(args: list[str], cwd: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, timeout=120
    )


def _git_publish(output_dir: Path, date_str: str, branch: str | None) -> tuple[bool, str]:
    """git add 站点目录 → commit → push 当前(或指定)分支。返回 (是否推送, 说明)。"""
    repo = output_dir
    # 找到 git 仓库根
    top = _run_git(["rev-parse", "--show-toplevel"], repo if repo.is_dir() else Path.cwd())
    if top.returncode != 0:
        return False, f"not a git repo: {top.stderr.strip()}"
    root = Path(top.stdout.strip())

    add = _run_git(["add", str(output_dir)], root)
    if add.returncode != 0:
        return False, f"git add failed: {add.stderr.strip()}"

    # 没有变化则跳过
    status = _run_git(["status", "--porcelain", str(output_dir)], root)
    if not status.stdout.strip():
        return False, "no changes to publish"

    commit = _run_git(["commit", "-m", f"paper: {date_str} 早报"], root)
    if commit.returncode != 0:
        return False, f"git commit failed: {commit.stderr.strip() or commit.stdout.strip()}"

    push_args = ["push", "origin"]
    if branch:
        push_args.append(f"HEAD:{branch}")
    push = _run_git(push_args, root)
    if push.returncode != 0:
        return False, f"git push failed: {push.stderr.strip()}"
    return True, f"pushed {date_str}"


def publish_paper(
    digest: Digest,
    *,
    output_dir: str = "docs",
    git_publish: bool = False,
    git_branch: str | None = None,
    masthead_en: str = "THE DAILY DISPATCH",
) -> PublishResult:
    """渲染并写入站点目录，更新 index/archive，按需 git 推送。"""
    out = Path(output_dir)
    papers = out / "papers"
    papers.mkdir(parents=True, exist_ok=True)

    date_str = _digest_date(digest)

    # dated 页面（archive 链接指向 ../archive.html，因为它在 papers/ 子目录下）
    page_html = render_paper(digest, masthead_en=masthead_en, archive_href="../archive.html")
    page_path = papers / f"{date_str}.html"
    page_path.write_text(page_html, encoding="utf-8")

    # index.html = 最新一期（archive 链接为同级 archive.html）
    index_html = render_paper(digest, masthead_en=masthead_en, archive_href="archive.html")
    index_path = out / "index.html"
    index_path.write_text(index_html, encoding="utf-8")

    # archive.html
    entries = _collect_archive(papers)
    archive_path = out / "archive.html"
    archive_path.write_text(render_archive(entries), encoding="utf-8")

    result = PublishResult(
        page_path=page_path, index_path=index_path, archive_path=archive_path
    )

    if git_publish:
        pushed, msg = _git_publish(out, date_str, git_branch)
        result.git_pushed = pushed
        result.git_message = msg
        logger.info("[webpaper] git publish: pushed=%s msg=%s", pushed, msg)
    else:
        logger.info("[webpaper] git_publish=false, wrote files only to %s", out)

    return result


__all__ = ["publish_paper", "PublishResult"]
