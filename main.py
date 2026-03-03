import sys
import time
import pytz
from datetime import datetime

from utils import get_daily_papers_by_keyword_with_retries, generate_table, back_up_files,\
    restore_files, remove_backups, get_daily_date


beijing_timezone = pytz.timezone('Asia/Shanghai')

# NOTE: arXiv API seems to sometimes return an unexpected empty list.

# get current beijing time date in the format of "2021-08-01"
current_date = datetime.now(beijing_timezone).strftime("%Y-%m-%d")
# get last update date from README.md
with open("README.md", "r") as f:
    while True:
        line = f.readline()
        if "Last update:" in line: break
    last_update_date = line.split(": ")[1].strip()
    # if last_update_date == current_date:
        # sys.exit("Already updated today!")

keywords = ["Superconductivity", "spin glass"] # TODO add more keywords

max_results_per_keyword = {
    "Superconductivity": 15,
    "spin glass": 5
}
issues_result = 30 # maximum papers to be included in the issue

# all columns: Title, Authors, Abstract, Link, Tags, Comment, Date
# fixed_columns = ["Title", "Link", "Date"]

column_names = ["Title", "Link", "Abstract", "Date", "Comment"]

back_up_files() # back up README.md and ISSUE_TEMPLATE.md

# write to README.md - 修改为更美观的格式
f_rm = open("README.md", "w") # file for README.md

# 添加Jekyll Front Matter
f_rm.write("---\n")
f_rm.write("layout: default\n")
f_rm.write("title: Daily ArXiv Papers\n")
f_rm.write("---\n\n")

# 美化标题和介绍
f_rm.write("# 📄 Daily ArXiv Papers\n\n")
f_rm.write("> 每日自动更新的arXiv论文精选 | Automatically fetched papers from arXiv\n\n")
f_rm.write("## ✨ 项目介绍\n\n")
f_rm.write("该项目基于关键词自动从arXiv抓取最新论文。README中的副标题代表搜索关键词。\n\n")
f_rm.write("每个关键词只保留最新的论文，最多100篇。\n\n")
f_rm.write("点击右上角的 **'Watch'** 按钮可以每天接收邮件通知。\n\n")
f_rm.write("## 📅 更新信息\n\n")
f_rm.write("| 项目 | 信息 |\n")
f_rm.write("|------|------|\n")
f_rm.write("| 最后更新 | {0} |\n".format(current_date))
f_rm.write("| 更新时间 | 每天北京时间 00:00 |\n")
f_rm.write("| 论文总数 | 根据关键词动态更新 |\n\n")

# write to ISSUE_TEMPLATE.md
f_is = open(".github/ISSUE_TEMPLATE.md", "w") # file for ISSUE_TEMPLATE.md
f_is.write("---\n")
f_is.write("title: Latest {0} Papers - {1}\n".format(issues_result, get_daily_date()))
f_is.write("labels: documentation\n")
f_is.write("---\n")
f_is.write("**Please check the [Github](https://github.com/zezhishao/MTS_Daily_ArXiv) page for a better reading experience and more papers.**\n\n")

total_papers = 0
for keyword in keywords:
    f_rm.write("## 🔬 {0}\n".format(keyword))
    f_is.write("## {0}\n".format(keyword))
    if len(keyword.split()) == 1: link = "AND" # for keyword with only one word, We search for papers containing this keyword in both the title and abstract.
    else: link = "OR"
    max_result = max_results_per_keyword[keyword]
    papers = get_daily_papers_by_keyword_with_retries(keyword, column_names, max_result, link)
    if papers is None: # failed to get papers
        print("Failed to get papers!")
        f_rm.close()
        f_is.close()
        restore_files()
        sys.exit("Failed to get papers!")
    
    total_papers += len(papers)
    rm_table = generate_table(papers)
    is_table = generate_table(papers[:issues_result], ignore_keys=["Abstract"])
    
    # 添加论文计数
    f_rm.write("> 本次更新找到 **{0}** 篇相关论文\n\n".format(len(papers)))
    f_rm.write(rm_table)
    f_rm.write("\n\n")
    f_is.write(is_table)
    f_is.write("\n\n")
    time.sleep(5) # avoid being blocked by arXiv API

# 添加页脚
f_rm.write("---\n\n")
f_rm.write("## 📊 统计信息\n\n")
f_rm.write("- 本次更新论文总数：**{0}** 篇\n".format(total_papers))
f_rm.write("- 关键词数量：**{0}** 个\n".format(len(keywords)))
f_rm.write("- 数据来源：[arXiv.org](https://arxiv.org/)\n\n")
f_rm.write("## 📬 订阅方式\n\n")
f_rm.write("1. 点击仓库右上角的 **Watch** 按钮\n")
f_rm.write("2. 选择 **Custom** → **Releases**\n")
f_rm.write("3. 即可每天收到更新通知\n\n")
f_rm.write("---\n\n")
f_rm.write("*项目开源在 [GitHub](https://github.com/northsi/DailyArXiv)，欢迎Star和PR* ⭐\n")

f_rm.close()
f_is.close()
remove_backups()
