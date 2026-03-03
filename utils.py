import os
import time
import pytz
import shutil
import datetime
from typing import List, Dict
import urllib, urllib.request

import feedparser
from easydict import EasyDict


def remove_duplicated_spaces(text: str) -> str:
    return " ".join(text.split())

def request_paper_with_arXiv_api(keyword: str, max_results: int, link: str = "OR") -> List[Dict[str, str]]:
    # keyword = keyword.replace(" ", "+")
    assert link in ["OR", "AND"], "link should be 'OR' or 'AND'"
    keyword = "\"" + keyword + "\""
    url = "http://export.arxiv.org/api/query?search_query=ti:{0}+{2}+abs:{0}&max_results={1}&sortBy=lastUpdatedDate".format(keyword, max_results, link)
    url = urllib.parse.quote(url, safe="%/:=&?~#+!$,;'@()*[]")
    response = urllib.request.urlopen(url).read().decode('utf-8')
    feed = feedparser.parse(response)

    # NOTE default columns: Title, Authors, Abstract, Link, Tags, Comment, Date
    papers = []
    for entry in feed.entries:
        entry = EasyDict(entry)
        paper = EasyDict()

        # title
        paper.Title = remove_duplicated_spaces(entry.title.replace("\n", " "))
        # abstract
        paper.Abstract = remove_duplicated_spaces(entry.summary.replace("\n", " "))
        # authors
        paper.Authors = [remove_duplicated_spaces(_["name"].replace("\n", " ")) for _ in entry.authors]
        # link
        paper.Link = remove_duplicated_spaces(entry.link.replace("\n", " "))
        # tags
        paper.Tags = [remove_duplicated_spaces(_["term"].replace("\n", " ")) for _ in entry.tags]
        # comment
        paper.Comment = remove_duplicated_spaces(entry.get("arxiv_comment", "").replace("\n", " "))
        # date
        paper.Date = entry.updated

        papers.append(paper)
    return papers

def filter_tags(papers: List[Dict[str, str]], target_fileds: List[str]=["physics", "cond-mat"]) -> List[Dict[str, str]]:
    # filtering tags: only keep the papers in target_fileds
    results = []
    for paper in papers:
        tags = paper.Tags
        for tag in tags:
            if tag.split(".")[0] in target_fileds:
                results.append(paper)
                break
    return results

def get_daily_papers_by_keyword_with_retries(keyword: str, column_names: List[str], max_result: int, link: str = "OR", retries: int = 6) -> List[Dict[str, str]]:
    for _ in range(retries):
        papers = get_daily_papers_by_keyword(keyword, column_names, max_result, link)
        if len(papers) > 0: return papers
        else:
            print("Unexpected empty list, retrying...")
            time.sleep(60 * 30) # wait for 30 minutes
    # failed
    return None

def get_daily_papers_by_keyword(keyword: str, column_names: List[str], max_result: int, link: str = "OR") -> List[Dict[str, str]]:
    # get papers
    papers = request_paper_with_arXiv_api(keyword, max_result, link) # NOTE default columns: Title, Authors, Abstract, Link, Tags, Comment, Date
    # NOTE filtering tags: only keep the papers in cs field
    # TODO filtering more
    papers = filter_tags(papers)
    # select columns for display
    papers = [{column_name: paper[column_name] for column_name in column_names} for paper in papers]
    return papers

def generate_table(papers: List[Dict[str, str]], ignore_keys: List[str] = []) -> str:
    if not papers:
        return "No papers found for this keyword.\n"
    
    formatted_papers = []
    keys = papers[0].keys()
    for paper in papers:
        # process fixed columns
        formatted_paper = EasyDict()
        ## Title and Link - 添加标签样式
        formatted_paper.Title = "**" + "[{0}]({1})".format(paper["Title"], paper["Link"]) + "**"
        ## Process Date (format: 2021-08-01T00:00:00Z -> 2021-08-01)
        formatted_paper.Date = paper["Date"].split("T")[0]
        
        # process other columns
        for key in keys:
            if key in ["Title", "Link", "Date"] or key in ignore_keys:
                continue
            elif key == "Abstract":
                # 美化abstract折叠框
                formatted_paper[key] = "<details><summary>📖 查看摘要</summary><p>{0}</p></details>".format(paper[key])
            elif key == "Authors":
                # 只显示第一作者
                formatted_paper[key] = paper[key][0] + " et al."
            elif key == "Tags":
                tags = paper[key]
                # 美化标签显示
                tag_spans = []
                for tag in tags[:5]:  # 最多显示5个标签
                    tag_spans.append('<span class="tag">{0}</span>'.format(tag))
                if len(tags) > 5:
                    tag_spans.append('<span class="tag">+{0}</span>'.format(len(tags)-5))
                formatted_paper[key] = " ".join(tag_spans) if tag_spans else ""
            elif key == "Comment":
                if paper[key] == "":
                    formatted_paper[key] = ""
                else:
                    # 美化评论显示
                    formatted_paper[key] = '<span class="comment">{0}</span>'.format(paper[key][:100] + "..." if len(paper[key]) > 100 else paper[key])
        formatted_papers.append(formatted_paper)

    # generate header - 美化表头
    column_names_map = {
        "Title": "📄 论文标题",
        "Date": "📅 日期",
        "Abstract": "📝 摘要",
        "Comment": "💬 评论",
        "Authors": "👥 作者",
        "Tags": "🏷️ 标签"
    }
    
    columns = list(formatted_papers[0].keys())
    # 映射列名
    header_columns = [column_names_map.get(col, col) for col in columns]
    
    # 添加emoji表头
    header = "| " + " | ".join(header_columns) + " |"
    header = header + "\n" + "| " + " | ".join([":---"] * len(columns)) + " |"
    
    # generate the body
    body = ""
    for paper in formatted_papers:
        row = []
        for key in columns:
            value = paper[key]
            if key == "Title":
                value = value.replace("**", "")  # 移除加粗标记，因为markdown会自动处理
            row.append(value)
        body += "\n| " + " | ".join(row) + " |"
    return header + body

def back_up_files():
    # back up README.md and ISSUE_TEMPLATE.md
    shutil.move("README.md", "README.md.bk")
    shutil.move(".github/ISSUE_TEMPLATE.md", ".github/ISSUE_TEMPLATE.md.bk")

def restore_files():
    # restore README.md and ISSUE_TEMPLATE.md
    shutil.move("README.md.bk", "README.md")
    shutil.move(".github/ISSUE_TEMPLATE.md.bk", ".github/ISSUE_TEMPLATE.md")

def remove_backups():
    # remove README.md and ISSUE_TEMPLATE.md
    os.remove("README.md.bk")
    os.remove(".github/ISSUE_TEMPLATE.md.bk")

def get_daily_date():
    # get beijing time in the format of "March 1, 2021"
    beijing_timezone = pytz.timezone('Asia/Shanghai')
    today = datetime.datetime.now(beijing_timezone)
    return today.strftime("%B %d, %Y")        ## Title and Link
        formatted_paper.Title = "**" + "[{0}]({1})".format(paper["Title"], paper["Link"]) + "**"
        ## Process Date (format: 2021-08-01T00:00:00Z -> 2021-08-01)
        formatted_paper.Date = paper["Date"].split("T")[0]
        
        # process other columns
        for key in keys:
            if key in ["Title", "Link", "Date"] or key in ignore_keys:
                continue
            elif key == "Abstract":
                # add show/hide button for abstract
                formatted_paper[key] = "<details><summary>Show</summary><p>{0}</p></details>".format(paper[key])
            elif key == "Authors":
                # NOTE only use the first author
                formatted_paper[key] = paper[key][0] + " et al."
            elif key == "Tags":
                tags = ", ".join(paper[key])
                if len(tags) > 10:
                    formatted_paper[key] = "<details><summary>{0}...</summary><p>{1}</p></details>".format(tags[:5], tags)
                else:
                    formatted_paper[key] = tags
            elif key == "Comment":
                if paper[key] == "":
                    formatted_paper[key] = ""
                elif len(paper[key]) > 20:
                    formatted_paper[key] = "<details><summary>{0}...</summary><p>{1}</p></details>".format(paper[key][:5], paper[key])
                else:
                    formatted_paper[key] = paper[key]
        formatted_papers.append(formatted_paper)

    # generate header
    columns = formatted_papers[0].keys()
    # highlight headers
    columns = ["**" + column + "**" for column in columns]
    header = "| " + " | ".join(columns) + " |"
    header = header + "\n" + "| " + " | ".join(["---"] * len(formatted_papers[0].keys())) + " |"
    # generate the body
    body = ""
    for paper in formatted_papers:
        body += "\n| " + " | ".join(paper.values()) + " |"
    return header + body

def back_up_files():
    # back up README.md and ISSUE_TEMPLATE.md
    shutil.move("README.md", "README.md.bk")
    shutil.move(".github/ISSUE_TEMPLATE.md", ".github/ISSUE_TEMPLATE.md.bk")

def restore_files():
    # restore README.md and ISSUE_TEMPLATE.md
    shutil.move("README.md.bk", "README.md")
    shutil.move(".github/ISSUE_TEMPLATE.md.bk", ".github/ISSUE_TEMPLATE.md")

def remove_backups():
    # remove README.md and ISSUE_TEMPLATE.md
    os.remove("README.md.bk")
    os.remove(".github/ISSUE_TEMPLATE.md.bk")

def get_daily_date():
    # get beijing time in the format of "March 1, 2021"
    beijing_timezone = pytz.timezone('Asia/Shanghai')
    today = datetime.datetime.now(beijing_timezone)
    return today.strftime("%B %d, %Y")
