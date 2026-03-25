import os
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
    get_daily_date,
)
from llm_utils import (
    configure_gemini,
    get_gemini_model,
    summarize_papers_for_topic,
    translate_abstract_to_chinese,
    generate_knowledge_section,
)
from email_utils import send_email, build_email_html

# ─── Configuration ────────────────────────────────────────────────────────────

beijing_timezone = pytz.timezone("Asia/Shanghai")
current_date = datetime.now(beijing_timezone).strftime("%Y-%m-%d")

keywords = ["Superconductivity", "spin glass"]  # TODO: add more keywords

max_results_per_keyword = {
    "Superconductivity": 20,
    "spin glass": 10,
}

issues_result = 30      # max papers shown in the GitHub issue
column_names = ["Title", "Link", "Abstract", "Date", "Comment"]

# ─── Read last update date from existing README ───────────────────────────────

last_update_date = ""
try:
    with open("README.md", "r", encoding="utf-8") as f:
        for line in f:
            if "Last update:" in line:
                last_update_date = line.split(": ", 1)[1].strip()
                break
except FileNotFoundError:
    pass

# Uncomment to prevent re-running on the same day:
# if last_update_date == current_date:
#     sys.exit("Already updated today!")

# ─── LLM Setup ────────────────────────────────────────────────────────────────

gemini_api_key = os.environ.get("GEMINI_API_KEY", "")
if gemini_api_key:
    configure_gemini(gemini_api_key)
    model = get_gemini_model("gemini-1.5-flash")
    llm_enabled = True
    print("✅ Gemini LLM enabled.")
else:
    model = None
    llm_enabled = False
    print("⚠️  GEMINI_API_KEY not set — LLM features disabled.")

# ─── Email Setup ──────────────────────────────────────────────────────────────

email_sender    = os.environ.get("EMAIL_SENDER", "")
email_password  = os.environ.get("EMAIL_PASSWORD", "")
email_recipient = os.environ.get("EMAIL_RECIPIENT", "")
repo_url        = os.environ.get("REPO_URL", "")
email_enabled   = all([email_sender, email_password, email_recipient])

if not email_enabled:
    print("⚠️  Email secrets incomplete — email notification disabled.")

# ─── Main Logic ───────────────────────────────────────────────────────────────

back_up_files()

topic_summaries: dict = {}
all_papers_flat: list = []
knowledge_section = ""

try:
    with open("README.md", "w", encoding="utf-8") as f_rm, \
         open(".github/ISSUE_TEMPLATE.md", "w", encoding="utf-8") as f_is:

        # ── README header ──────────────────────────────────────────────────────
        f_rm.write("# Daily Papers\n")
        f_rm.write(
            "The project automatically fetches the latest papers from arXiv "
            "based on keywords.\n\n"
        )
        f_rm.write("The subheadings represent the search keywords.\n\n")
        f_rm.write(
            "Only the most recent articles for each keyword are retained, "
            "up to a maximum of 100 papers.\n\n"
        )
        f_rm.write("You can click the 'Watch' button to receive daily email notifications.\n\n")
        f_rm.write(f"Last update: {current_date}\n\n")

        # ── ISSUE header ───────────────────────────────────────────────────────
        f_is.write("---\n")
        f_is.write(f"title: Latest {issues_result} Papers - {get_daily_date()}\n")
        f_is.write("labels: documentation\n")
        f_is.write("---\n")
        f_is.write(
            "**Please check the [Github](https://github.com/zezhishao/MTS_Daily_ArXiv) "
            "page for a better reading experience and more papers.**\n\n"
        )

        # ── Per-keyword processing ─────────────────────────────────────────────
        for keyword in keywords:
            print(f"\n{'='*50}")
            print(f"Processing keyword: {keyword}")

            f_rm.write(f"## {keyword}\n\n")
            f_is.write(f"## {keyword}\n\n")

            link_mode = "AND" if len(keyword.split()) == 1 else "OR"
            max_result = max_results_per_keyword.get(keyword, 10)

            papers = get_daily_papers_by_keyword_with_retries(
                keyword, column_names, max_result, link_mode
            )

            if papers is None:
                raise RuntimeError(f"Failed to fetch papers for keyword: '{keyword}'")

            all_papers_flat.extend(papers)

            # ── Translate abstracts and generate topic summary via LLM ────────
            if llm_enabled:
                print(f"  Translating {len(papers)} abstracts to Chinese...")
                for paper in papers:
                    paper["Abstract_ZH"] = translate_abstract_to_chinese(
                        paper.get("Abstract", ""), model
                    )
                    time.sleep(1.5)  # respect Gemini rate limits

                print(f"  Generating topic overview...")
                summary = summarize_papers_for_topic(papers, keyword, model)
            else:
                for paper in papers:
                    paper["Abstract_ZH"] = ""
                summary = "*Overview unavailable — GEMINI_API_KEY not configured.*"

            topic_summaries[keyword] = summary

            # ── Part 1: Today's Overview ───────────────────────────────────────
            f_rm.write("### 📋 Today's Overview\n\n")
            f_rm.write(f"{summary}\n\n")
            f_is.write("### 📋 Today's Overview\n\n")
            f_is.write(f"{summary}\n\n")

            # ── Part 2: Paper Details ──────────────────────────────────────────
            f_rm.write("### 📄 Paper Details\n\n")
            # README: includes both English and Chinese abstracts
            rm_table = generate_table(papers)
            f_rm.write(rm_table + "\n\n")

            f_is.write("### 📄 Paper Details\n\n")
            # Issue: compact view, abstracts omitted to keep it readable
            is_table = generate_table(
                papers[:issues_result],
                ignore_keys=["Abstract", "Abstract_ZH"],
            )
            f_is.write(is_table + "\n\n")

            time.sleep(5)  # avoid arXiv API rate limiting

        # ── Global knowledge / keywords section ───────────────────────────────
        print("\nGenerating cross-topic knowledge section...")
        if llm_enabled:
            knowledge_section = generate_knowledge_section(
                all_papers_flat, keywords, model
            )
        else:
            knowledge_section = (
                "*Knowledge section unavailable — GEMINI_API_KEY not configured.*"
            )

        separator = "---\n\n"
        knowledge_header = "## 💡 Concepts & Keywords to Learn Today\n\n"

        f_rm.write(separator + knowledge_header + knowledge_section + "\n\n")
        f_is.write(separator + knowledge_header + knowledge_section + "\n\n")

except Exception as e:
    print(f"\n❌ Error occurred: {e}")
    restore_files()
    sys.exit(1)

remove_backups()
print("\n✅ Files updated successfully.")

# ─── Email Notification ───────────────────────────────────────────────────────

if email_enabled:
    try:
        print("Sending email notification...")
        email_html = build_email_html(
            topic_summaries, knowledge_section, current_date, repo_url
        )
        subject = f"📄 Daily arXiv Papers — {current_date}"
        send_email(
            email_sender, email_password, email_recipient, subject, email_html
        )
    except Exception as e:
        print(f"⚠️  Email sending failed (non-fatal): {e}")
else:
    print("Email skipped — not configured.")max_results_per_keyword = {
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
