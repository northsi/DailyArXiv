import sys
import time
import pytz
from datetime import datetime

from utils import (
    get_daily_papers_by_keyword_with_retries, 
    generate_table, 
    back_up_files,
    restore_files, 
    remove_backups, 
    get_daily_date
)

beijing_timezone = pytz.timezone('Asia/Shanghai')

# 获取当前北京时间
current_date = datetime.now(beijing_timezone).strftime("%Y-%m-%d")

# 安全地读取 README.md 中的最后更新日期
last_update_date = ""
try:
    with open("README.md", "r", encoding="utf-8") as f:
        for line in f:
            if "Last update:" in line:
                last_update_date = line.split(": ")[1].strip()
                break
except FileNotFoundError:
    pass  # 如果文件不存在则跳过

# 取消注释以启用更新检查
# if last_update_date == current_date:
#     sys.exit("Already updated today!")

keywords = ["Superconductivity", "spin glass"] # TODO add more keywords

max_results_per_keyword = {
    "Superconductivity": 20,
    "spin glass": 10
}
issues_result = 30 # maximum papers to be included in the issue
column_names = ["Title", "Link", "Abstract", "Date", "Comment"]

# 备份原文件
back_up_files()

try:
    # 使用 with 语句自动管理文件关闭，避免异常时文件流未释放
    with open("README.md", "w", encoding="utf-8") as f_rm, \
         open(".github/ISSUE_TEMPLATE.md", "w", encoding="utf-8") as f_is:

        # 写入 README.md 头部
        f_rm.write("# Daily Papers\n")
        f_rm.write("The project automatically fetches the latest papers from arXiv based on keywords.\n\n")
        f_rm.write("The subheadings in the README file represent the search keywords.\n\n")
        f_rm.write("Only the most recent articles for each keyword are retained, up to a maximum of 100 papers.\n\n")
        f_rm.write("You can click the 'Watch' button to receive daily email notifications.\n\n")
        f_rm.write(f"Last update: {current_date}\n\n")

        # 写入 ISSUE_TEMPLATE.md 头部
        f_is.write("---\n")
        f_is.write(f"title: Latest {issues_result} Papers - {get_daily_date()}\n")
        f_is.write("labels: documentation\n")
        f_is.write("---\n")
        f_is.write("**Please check the [Github](https://github.com/zezhishao/MTS_Daily_ArXiv) page for a better reading experience and more papers.**\n\n")

        for keyword in keywords:
            f_rm.write(f"## {keyword}\n")
            f_is.write(f"## {keyword}\n")
            
            # 单个单词使用 AND，多个单词使用 OR
            link = "AND" if len(keyword.split()) == 1 else "OR"
            max_result = max_results_per_keyword.get(keyword, 10)
            
            papers = get_daily_papers_by_keyword_with_retries(keyword, column_names, max_result, link)
            
            if papers is None: # 获取失败触发异常进行还原
                raise RuntimeError(f"Failed to get papers for keyword: {keyword}!")
            
            rm_table = generate_table(papers)
            is_table = generate_table(papers[:issues_result], ignore_keys=["Abstract"])
            
            f_rm.write(rm_table + "\n\n")
            f_is.write(is_table + "\n\n")
            
            time.sleep(5) # 避免被 arXiv API 封禁请求

except Exception as e:
    print(f"Error occurred: {e}")
    restore_files()
    sys.exit(1)

# 执行成功，移除备份
remove_backups()
