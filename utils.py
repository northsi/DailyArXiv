# utils.py
import datetime
import os
import random
import re
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


def build_arxiv_query(keyword: str, link: str = "OR") -> str:
    """Combine OR-separated terms; link controls title versus abstract matching."""
    if link not in {"OR", "AND"}:
        raise ValueError("link must be 'OR' or 'AND'")
    terms = [term.strip() for term in re.split(r"\bOR\b", keyword, flags=re.IGNORECASE)]
    if any(not term for term in terms):
        raise ValueError("Search terms must not be empty")
    clauses = [f'ti:"{term}" {link} abs:"{term}"' for term in terms]
    if len(clauses) == 1:
        return clauses[0]
    return " OR ".join(f"({clause})" for clause in clauses)


def request_paper_with_arXiv_api(
    keyword: str, max_results: int, link: str = "OR"
) -> List[Dict]:
    query = build_arxiv_query(keyword, link)
    params = urllib.parse.urlencode(
        {
            "search_query": query,
            "max_results": max_results,
            "sortBy": "lastUpdatedDate",
        }
    )
    url = f"http://export.arxiv.org/api/query?{params}"

    max_retries = 5
    for attempt in range(max_retries):
        # Wait a random 1-3 seconds before each request.
        time.sleep(random.uniform(1, 3))

        try:
            with urllib.request.urlopen(url, timeout=30) as response:
                data = response.read().decode("utf-8")
            return parse_arxiv_feed(data)

        except urllib.error.HTTPError as e:
            if e.code == 429:
                # Read the Retry-After header.
                retry_after = e.headers.get("Retry-After")
                if retry_after is not None:
                    wait = int(retry_after)
                else:
                    wait = 30 * (2**attempt)  # Exponential backoff: 30, 60, 120...
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

    # Return an empty list when retries are exhausted.
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
        wait = min(60 * (attempt + 1), 300)  # Wait at most 5 minutes.
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
    for idx, paper in enumerate(papers, start=1):  # Number rows starting at 1.
        fp = {"#": str(idx)}  # Add the row-number column.
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
                fp["Main Finding"] = escape(str(val)).replace("|", "&#124;")

            elif key == "Authors":
                author = (
                    val[-1] if isinstance(val, list) and val else "Author not provided"
                )
                fp["Last Author"] = escape(str(author)).replace("|", "&#124;")

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
    ]  # Put row numbers first.
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
