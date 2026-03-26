# utils.py
import os
import time
import pytz
import shutil
import datetime
from typing import List, Dict
import urllib.request
import urllib.parse

import feedparser
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
    response = urllib.request.urlopen(url).read().decode("utf-8")
    feed = feedparser.parse(response)

    papers = []
    for entry in feed.entries:
        entry = EasyDict(entry)
        paper = EasyDict()
        paper.Title    = remove_duplicated_spaces(entry.title.replace("\n", " "))
        paper.Abstract = remove_duplicated_spaces(entry.summary.replace("\n", " "))
        paper.Authors  = [
            remove_duplicated_spaces(_["name"].replace("\n", " "))
            for _ in getattr(entry, "authors", [])
        ]
        paper.Link    = remove_duplicated_spaces(entry.link.replace("\n", " "))
        paper.Tags    = [
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
    results = []
    for paper in papers:
        tags = paper.get("Tags", [])
        for tag in tags:
            if tag.split(".")[0] in target_fields:
                results.append(paper)
                break
    return results


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
        print(f"Empty list for '{keyword}', retrying ({attempt + 1}/{retries})…")
        time.sleep(60)
    return None


def generate_table(papers: List[Dict], ignore_keys: List[str] = None) -> str:
    """
    Render a Markdown table from a list of paper dicts.

    Key behaviours
    ──────────────
    • 'Link'        – embedded into the Title hyperlink; never its own column.
    • 'Abstract_CN' – embedded inside the 'Abstract' cell as a second
                      collapsible block; never its own column.
    • 'Abstract'    – rendered as two collapsible <details> blocks (EN / 中文).
    • 'Authors'     – shortened to "First Author et al."
    • 'Tags'        – collapsed when lengthy.
    • ignore_keys   – any column names to exclude entirely.
    """
    if not papers:
        return "*No papers matched today.*"

    ignore_keys  = set(ignore_keys or [])
    INTERNAL_KEYS = {"Link", "Abstract_CN"}   # consumed internally, not columns

    columns_in_use = [
        k for k in papers[0].keys()
        if k not in ignore_keys and k not in INTERNAL_KEYS
    ]

    formatted_papers = []
    for paper in papers:
        fp = {}
        for key in columns_in_use:
            val = paper.get(key, "")

            if key == "Title":
                link = paper.get("Link", "")
                fp["Title"] = f"**[{val}]({link})**"

            elif key == "Date":
                fp["Date"] = val.split("T")[0] if "T" in val else val

            elif key == "Abstract":
                cn = paper.get("Abstract_CN", "")
                cell = f"<details><summary>EN</summary><p>{val}</p></details>"
                if cn:
                    cell += f"<details><summary>中文</summary><p>{cn}</p></details>"
                fp["Abstract"] = cell

            elif key == "Authors":
                fp["Authors"] = (
                    f"{val[0]} et al." if isinstance(val, list) and val else ""
                )

            elif key == "Tags":
                tags_str = ", ".join(val) if isinstance(val, list) else str(val)
                fp["Tags"] = (
                    f"<details><summary>{tags_str[:5]}…</summary>"
                    f"<p>{tags_str}</p></details>"
                    if len(tags_str) > 10 else tags_str
                )

            else:
                fp[key] = str(val)

        formatted_papers.append(fp)

    # Build Markdown table
    final_cols = list(formatted_papers[0].keys())
    header  = "| " + " | ".join(f"**{c}**" for c in final_cols) + " |\n"
    header += "| " + " | ".join(["---"] * len(final_cols)) + " |"

    body = ""
    for fp in formatted_papers:
        row  = [str(fp.get(c, "")) for c in final_cols]
        body += "\n| " + " | ".join(row) + " |"

    return header + body


def back_up_files():
    os.makedirs(".github", exist_ok=True)
    if os.path.exists("README.md"):
        shutil.copy("README.md", "README.md.bk")
    if os.path.exists(".github/ISSUE_TEMPLATE.md"):
        shutil.copy(".github/ISSUE_TEMPLATE.md", ".github/ISSUE_TEMPLATE.md.bk")


def restore_files():
    if os.path.exists("README.md.bk"):
        shutil.move("README.md.bk", "README.md")
    if os.path.exists(".github/ISSUE_TEMPLATE.md.bk"):
        shutil.move(".github/ISSUE_TEMPLATE.md.bk", ".github/ISSUE_TEMPLATE.md")


def remove_backups():
    if os.path.exists("README.md.bk"):
        os.remove("README.md.bk")
    if os.path.exists(".github/ISSUE_TEMPLATE.md.bk"):
        os.remove(".github/ISSUE_TEMPLATE.md.bk")


def get_daily_date() -> str:
    beijing_timezone = pytz.timezone("Asia/Shanghai")
    today = datetime.datetime.now(beijing_timezone)
    return today.strftime("%B %d, %Y")        paper = EasyDict()
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
    results = []
    for paper in papers:
        tags = paper.get("Tags", [])
        for tag in tags:
            if tag.split(".")[0] in target_fields:
                results.append(paper)
                break
    return results


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
        print(f"Unexpected empty list for '{keyword}', retrying ({attempt + 1}/{retries})...")
        time.sleep(60)
    return None


def generate_table(papers: List[Dict], ignore_keys: List[str] = None) -> str:
    if not papers:
        return "*No papers matched today.*"

    ignore_keys = ignore_keys or []
    formatted_papers = []
    keys = list(papers[0].keys())

    for paper in papers:
        formatted_paper = {}

        # Fixed columns: Title (with hyperlink) and Date
        title = paper.get("Title", "")
        link = paper.get("Link", "")
        formatted_paper["Title"] = f"**[{title}]({link})**"

        date_str = paper.get("Date", "")
        formatted_paper["Date"] = (
            date_str.split("T")[0] if "T" in date_str else date_str
        )

        # Variable columns
        for key in keys:
            if key in ["Title", "Link", "Date"] or key in ignore_keys:
                continue

            val = paper.get(key, "")

            if key == "Abstract":
                formatted_paper[key] = (
                    f"<details><summary>Show EN</summary><p>{val}</p></details>"
                )
            elif key == "Abstract_ZH":
                # Map the internal key to a display-friendly column name
                formatted_paper["Abstract (中文)"] = (
                    f"<details><summary>显示中文</summary><p>{val}</p></details>"
                    if val
                    else ""
                )
            elif key == "Authors":
                formatted_paper[key] = (
                    f"{val[0]} et al." if isinstance(val, list) and val else ""
                )
            elif key == "Tags":
                tags_str = ", ".join(val) if isinstance(val, list) else str(val)
                formatted_paper[key] = (
                    f"<details><summary>{tags_str[:5]}...</summary>"
                    f"<p>{tags_str}</p></details>"
                    if len(tags_str) > 10
                    else tags_str
                )
            elif key == "Comment":
                if not val:
                    formatted_paper[key] = ""
                elif len(val) > 20:
                    formatted_paper[key] = (
                        f"<details><summary>{val[:5]}...</summary>"
                        f"<p>{val}</p></details>"
                    )
                else:
                    formatted_paper[key] = val
            else:
                formatted_paper[key] = str(val)

        formatted_papers.append(formatted_paper)

    # Build the Markdown table
    columns = list(formatted_papers[0].keys())
    header = (
        "| " + " | ".join(f"**{col}**" for col in columns) + " |\n"
        + "| " + " | ".join(["---"] * len(columns)) + " |"
    )
    body = ""
    for paper in formatted_papers:
        row_vals = [str(paper.get(col, "")) for col in columns]
        body += "\n| " + " | ".join(row_vals) + " |"

    return header + body


def back_up_files():
    os.makedirs(".github", exist_ok=True)
    if os.path.exists("README.md"):
        shutil.copy("README.md", "README.md.bk")
    if os.path.exists(".github/ISSUE_TEMPLATE.md"):
        shutil.copy(".github/ISSUE_TEMPLATE.md", ".github/ISSUE_TEMPLATE.md.bk")


def restore_files():
    if os.path.exists("README.md.bk"):
        shutil.move("README.md.bk", "README.md")
    if os.path.exists(".github/ISSUE_TEMPLATE.md.bk"):
        shutil.move(".github/ISSUE_TEMPLATE.md.bk", ".github/ISSUE_TEMPLATE.md")


def remove_backups():
    if os.path.exists("README.md.bk"):
        os.remove("README.md.bk")
    if os.path.exists(".github/ISSUE_TEMPLATE.md.bk"):
        os.remove(".github/ISSUE_TEMPLATE.md.bk")


def get_daily_date() -> str:
    beijing_timezone = pytz.timezone("Asia/Shanghai")
    today = datetime.datetime.now(beijing_timezone)
    return today.strftime("%B %d, %Y")        
    
    paper.Date = entry.updated
    papers.append(paper)
    return papers

def filter_tags(papers: List[Dict], target_fields: List[str] = ["physics", "cond-mat", "quant-ph", "nlin"]) -> List[Dict]:
    # 修复了原版的 target_fileds 拼写错误
    results = []
    for paper in papers:
        tags = paper.get("Tags", [])
        for tag in tags:
            if tag.split(".")[0] in target_fields:
                results.append(paper)
                break
    return results

def get_daily_papers_by_keyword(keyword: str, column_names: List[str], max_result: int, link: str = "OR") -> List[Dict]:
    papers = request_paper_with_arXiv_api(keyword, max_result, link)
    papers = filter_tags(papers)
    # 仅保留所需列
    return [{col: paper.get(col, "") for col in column_names} for paper in papers]

def get_daily_papers_by_keyword_with_retries(keyword: str, column_names: List[str], max_result: int, link: str = "OR", retries: int = 6) -> List[Dict]:
    for attempt in range(retries):
        papers = get_daily_papers_by_keyword(keyword, column_names, max_result, link)
        if papers: # 当返回不是空列表时
            return papers
        
        print(f"Unexpected empty list for '{keyword}', retrying ({attempt + 1}/{retries})...")
        time.sleep(60) # 注意：在CI中休眠30分钟会导致严重超时，这里改为了60秒
        
    return None

def generate_table(papers: List[Dict], ignore_keys: List[str] = None) -> str:
    if not papers:
        return "*No papers matched today.*"
        
    ignore_keys = ignore_keys or []
    formatted_papers = []
    keys = papers[0].keys()
    
    for paper in papers:
        formatted_paper = {}
        
        # 处理固定列
        title = paper.get("Title", "")
        link = paper.get("Link", "")
        formatted_paper["Title"] = f"**[{title}]({link})**"
        
        date_str = paper.get("Date", "")
        formatted_paper["Date"] = date_str.split("T")[0] if "T" in date_str else date_str
        
        # 处理其他列
        for key in keys:
            if key in ["Title", "Link", "Date"] or key in ignore_keys:
                continue
            
            val = paper.get(key, "")
            if key == "Abstract":
                formatted_paper[key] = f"<details><summary>Show</summary><p>{val}</p></details>"
            elif key == "Authors":
                formatted_paper[key] = f"{val[0]} et al." if isinstance(val, list) and val else ""
            elif key == "Tags":
                tags_str = ", ".join(val) if isinstance(val, list) else str(val)
                if len(tags_str) > 10:
                    formatted_paper[key] = f"<details><summary>{tags_str[:5]}...</summary><p>{tags_str}</p></details>"
                else:
                    formatted_paper[key] = tags_str
            elif key == "Comment":
                if not val:
                    formatted_paper[key] = ""
                elif len(val) > 20:
                    formatted_paper[key] = f"<details><summary>{val[:5]}...</summary><p>{val}</p></details>"
                else:
                    formatted_paper[key] = val
            else:
                formatted_paper[key] = str(val)
                
        formatted_papers.append(formatted_paper)

    # 生成表头
    columns = list(formatted_papers[0].keys())
    header_cols = [f"**{col}**" for col in columns]
    header = "| " + " | ".join(header_cols) + " |\n"
    header += "| " + " | ".join(["---"] * len(columns)) + " |"
    
    # 生成主体
    body = ""
    for paper in formatted_papers:
        row_vals = [str(paper.get(col, "")) for col in columns]
        body += "\n| " + " | ".join(row_vals) + " |"
        
    return header + body

def back_up_files():
    os.makedirs(".github", exist_ok=True) # 确保目录存在
    if os.path.exists("README.md"):
        shutil.copy("README.md", "README.md.bk") # 使用 copy 而非 move 保证文件流操作安全
    if os.path.exists(".github/ISSUE_TEMPLATE.md"):
        shutil.copy(".github/ISSUE_TEMPLATE.md", ".github/ISSUE_TEMPLATE.md.bk")

def restore_files():
    if os.path.exists("README.md.bk"):
        shutil.move("README.md.bk", "README.md")
    if os.path.exists(".github/ISSUE_TEMPLATE.md.bk"):
        shutil.move(".github/ISSUE_TEMPLATE.md.bk", ".github/ISSUE_TEMPLATE.md")

def remove_backups():
    if os.path.exists("README.md.bk"):
        os.remove("README.md.bk")
    if os.path.exists(".github/ISSUE_TEMPLATE.md.bk"):
        os.remove(".github/ISSUE_TEMPLATE.md.bk")

def get_daily_date() -> str:
    beijing_timezone = pytz.timezone('Asia/Shanghai')
    today = datetime.datetime.now(beijing_timezone)
    return today.strftime("%B %d, %Y")
