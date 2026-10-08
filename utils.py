# utils.py
import datetime
import os
import random
import shutil
import time
import urllib.parse
import urllib.request
from html import escape
from typing import Dict, List

import feedparser
import pytz
from easydict import EasyDict


def remove_duplicated_spaces(text: str) -> str:
    return " ".join(text.split())


def request_paper_with_arXiv_api(
    keyword: str, max_results: int, link: str = "OR"
) -> List[Dict]:
    assert link in ["OR", "AND"], "link should be 'OR' or 'AND'"
    quoted_keyword = f'"{keyword}"'
    url = (
        f"http://export.arxiv.org/api/query?"
        f"search_query=ti:{quoted_keyword}+{link}+abs:{quoted_keyword}"
        f"&max_results={max_results}&sortBy=lastUpdatedDate"
    )
    url = urllib.parse.quote(url, safe="%/:=&?~#+!$,;'@()*[]")

    max_retries = 5
    for attempt in range(max_retries):
        # 1. 每次请求前随机休眠 1~3 秒，降低节奏感
        time.sleep(random.uniform(1, 3))

        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = response.read().decode("utf-8")
            return parse_arxiv_feed(data)

        except urllib.error.HTTPError as e:
            if e.code == 429:
                # 读取 Retry-After 头
                retry_after = e.headers.get("Retry-After")
                if retry_after is not None:
                    wait = int(retry_after)
                else:
                    wait = 30 * (2**attempt)  # 指数退避：30, 60, 120...
                print(
                    f"[arXiv] 429 Too Many Requests. Waiting {wait}s (attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(wait)
                continue
            elif e.code == 503:
                wait = 10 * (2**attempt)
                print(
                    f"[arXiv] 503 Service Unavailable. Waiting {wait}s (attempt {attempt + 1}/{max_retries})"
                )
                time.sleep(wait)
                continue
            else:
                raise
        except Exception as e:
            print(f"[arXiv] Unexpected error: {e}")
            if attempt == max_retries - 1:
                raise
            time.sleep(10 * (2**attempt))

    # 重试用尽，返回空列表（与主程序逻辑适配）
    print(f"[arXiv] Failed to fetch data for '{keyword}' after {max_retries} attempts.")
    return []


def parse_arxiv_feed(data: str) -> List[Dict]:
    """Parse an Atom response without performing network operations."""
    feed = feedparser.parse(data)
    papers = []
    for entry in feed.entries:
        entry = EasyDict(entry)
        paper = EasyDict()
        paper.Title = remove_duplicated_spaces(entry.title.replace("\n", " "))
        paper.Abstract = remove_duplicated_spaces(entry.summary.replace("\n", " "))
        paper.Authors = [
            remove_duplicated_spaces(_["name"].replace("\n", " "))
            for _ in getattr(entry, "authors", [])
        ]
        paper.Link = remove_duplicated_spaces(entry.link.replace("\n", " "))
        paper.Tags = [
            remove_duplicated_spaces(_["term"].replace("\n", " "))
            for _ in getattr(entry, "tags", [])
        ]
        paper.Comment = remove_duplicated_spaces(
            entry.get("arxiv_comment", "").replace("\n", " ")
        )
        paper.Date = entry.updated
        papers.append(paper)
    return papers


def filter_tags(
    papers: List[Dict],
    target_fields: List[str] = ["physics", "cond-mat", "quant-ph", "nlin"],
) -> List[Dict]:
    allowed_fields = set(target_fields)
    return [
        paper
        for paper in papers
        if any(tag.split(".")[0] in allowed_fields for tag in paper.get("Tags", []))
    ]


def get_daily_papers_by_keyword(
    keyword: str, column_names: List[str], max_result: int, link: str = "OR"
) -> List[Dict]:
    papers = request_paper_with_arXiv_api(keyword, max_result, link)
    papers = filter_tags(papers)
    return [{col: paper.get(col, "") for col in column_names} for paper in papers]


def get_daily_papers_by_keyword_with_retries(
    keyword: str,
    column_names: List[str],
    max_result: int,
    link: str = "OR",
    retries: int = 6,
) -> List[Dict]:
    for attempt in range(retries):
        papers = get_daily_papers_by_keyword(keyword, column_names, max_result, link)
        if papers:
            return papers
        wait = min(60 * (attempt + 1), 300)  # 最多等 5 分钟
        print(
            f"Empty list for '{keyword}', retrying in {wait}s ({attempt + 1}/{retries})…"
        )
        time.sleep(wait)
    return None


def generate_table(papers: List[Dict], ignore_keys: List[str] = None) -> str:
    """
    Render a Markdown table from a list of paper dicts.

    Keep the English abstract, display a one-sentence finding, and show the
    last listed author.
    """
    if not papers:
        return "*No papers matched today.*"

    ignore_keys = set(ignore_keys or [])
    INTERNAL_KEYS = {"Link", "Abstract_CN"}  # consumed internally, not columns

    columns_in_use = [
        k for k in papers[0].keys() if k not in ignore_keys and k not in INTERNAL_KEYS
    ]

    formatted_papers = []
    for idx, paper in enumerate(papers, start=1):  # 从1开始编号
        fp = {"#": str(idx)}  # 添加编号列
        for key in columns_in_use:
            val = paper.get(key, "")

            if key == "Title":
                link = paper.get("Link", "")
                fp["Title"] = f"**[{val}]({link})**"

            elif key == "Date":
                fp["Date"] = val.split("T")[0] if "T" in val else val

            elif key == "Abstract":
                fp["Abstract"] = (
                    f"<details><summary>EN</summary><p>{escape(str(val))}</p></details>"
                )

            elif key == "Finding_Summary":
                fp["主要发现"] = escape(str(val)).replace("|", "&#124;")

            elif key == "Authors":
                author = val[-1] if isinstance(val, list) and val else "作者未提供"
                fp["最后作者"] = escape(str(author)).replace("|", "&#124;")

            elif key == "Tags":
                tags_str = ", ".join(val) if isinstance(val, list) else str(val)
                fp["Tags"] = (
                    f"<details><summary>{tags_str[:5]}…</summary>"
                    f"<p>{tags_str}</p></details>"
                    if len(tags_str) > 10
                    else tags_str
                )

            else:
                fp[key] = str(val)

        formatted_papers.append(fp)

    # Build Markdown table
    final_cols = ["#"] + [
        col for col in list(formatted_papers[0].keys()) if col != "#"
    ]  # 编号列放在最前面
    header = "| " + " | ".join(f"**{c}**" for c in final_cols) + " |\n"
    header += "| " + " | ".join(["---"] * len(final_cols)) + " |"

    rows = [header]
    for fp in formatted_papers:
        row = [str(fp.get(c, "")) for c in final_cols]
        rows.append("| " + " | ".join(row) + " |")
    return "\n".join(rows)


REPORT_FILES = ("README.md",)
BEIJING_TIMEZONE = pytz.timezone("Asia/Shanghai")


def back_up_files():
    for path in REPORT_FILES:
        if os.path.exists(path):
            shutil.copy(path, f"{path}.bk")


def restore_files():
    for path in REPORT_FILES:
        backup = f"{path}.bk"
        if os.path.exists(backup):
            shutil.move(backup, path)


def remove_backups():
    for path in REPORT_FILES:
        backup = f"{path}.bk"
        if os.path.exists(backup):
            os.remove(backup)


def get_daily_date() -> str:
    today = datetime.datetime.now(BEIJING_TIMEZONE)
    return today.strftime("%B %d, %Y")
