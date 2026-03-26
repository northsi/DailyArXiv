# main.py
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
from llm_utils import batch_translate_to_chinese, summarize_topic
from email_utils import send_daily_email

# ── Configuration ─────────────────────────────────────────────────────────────

beijing_timezone = pytz.timezone("Asia/Shanghai")
current_date = datetime.now(beijing_timezone).strftime("%Y-%m-%d")

keywords = ["Superconductivity", "spin glass"]

max_results_per_keyword = {
    "Superconductivity": 20,
    "spin glass": 10,
}

issues_result = 30
column_names = ["Title", "Link", "Abstract", "Date", "Authors"]

# ── Duplicate-run guard ───────────────────────────────────────────────────────

last_update_date = ""
try:
    with open("README.md", "r", encoding="utf-8") as f:
        for line in f:
            if "Last update:" in line:
                last_update_date = line.split(": ", 1)[1].strip()
                break
except FileNotFoundError:
    pass

# ── Main ──────────────────────────────────────────────────────────────────────

back_up_files()

try:
    # ── Step 1: Fetch papers from arXiv ──────────────────────────────────────
    print("[debug] Step 1: Fetching papers …")
    keyword_papers: dict = {}

    for keyword in keywords:
        link = "AND" if len(keyword.split()) == 1 else "OR"
        max_result = max_results_per_keyword.get(keyword, 10)
        print(f"[debug]   Fetching '{keyword}' (max={max_result}, link={link}) …")

        papers = get_daily_papers_by_keyword_with_retries(
            keyword, column_names, max_result, link
        )
        if papers is None:
            raise RuntimeError(f"Failed to fetch papers for keyword: '{keyword}'")

        print(f"[debug]   Got {len(papers)} papers for '{keyword}'")

        # Inspect every paper for suspicious field values
        for i, paper in enumerate(papers):
            for key, val in paper.items():
                if val == "" or val is None:
                    print(f"[debug]   WARNING: paper[{i}]['{key}'] is empty/None  —  title: {paper.get('Title', 'N/A')[:60]}")

        keyword_papers[keyword] = papers
        time.sleep(5)

    all_papers = [p for papers in keyword_papers.values() for p in papers]
    print(f"[debug] Total papers across all keywords: {len(all_papers)}")

    # ── Step 2: Translate abstracts ───────────────────────────────────────────
    print("[main] Translating abstracts …")
    for keyword, papers in keyword_papers.items():
        print(f"[debug] Step 2: Translating {len(papers)} abstracts for '{keyword}' …")
        abstracts = [p.get("Abstract", "") for p in papers]
        print(f"[debug]   Sample abstracts[:2]: {[a[:80] for a in abstracts[:2]]}")

        translations = batch_translate_to_chinese(abstracts, batch_size=5)
        print(f"[debug]   Got {len(translations)} translations back")

        for paper, cn in zip(papers, translations):
            paper["Abstract_CN"] = cn

    print("[debug] Step 2 complete ✓")

    # ── Step 3: Generate topic summaries ──────────────────────────────────────
    print("[main] Generating topic summaries …")
    topic_summaries: dict = {}
    for keyword, papers in keyword_papers.items():
        print(f"[debug] Step 3: Summarising topic '{keyword}' with {len(papers)} papers …")
        print(f"[debug]   Paper keys available: {list(papers[0].keys()) if papers else 'NO PAPERS'}")
        summary = summarize_topic(keyword, papers)
        print(f"[debug]   Summary length: {len(summary)} chars")
        topic_summaries[keyword] = summary
        time.sleep(2)

    print("[debug] Step 3 complete ✓")

    # ── Step 4: Compose email body ─────────────────────────────────────────────
    print("[debug] Step 4: Composing email body …")
    email_body = f"# Daily arXiv Papers – {get_daily_date()}\n\n"
    for keyword in keywords:
        email_body += f"## {keyword}\n\n{topic_summaries[keyword]}\n\n"
    print("[debug] Step 4 complete ✓")

    # ── Step 5: Write README.md and ISSUE_TEMPLATE.md ─────────────────────────
    print("[debug] Step 5: Writing README.md and ISSUE_TEMPLATE.md …")
    with open("README.md", "w", encoding="utf-8") as f_rm, \
         open(".github/ISSUE_TEMPLATE.md", "w", encoding="utf-8") as f_is:

        f_rm.write("# Daily Papers\n\n")
        f_rm.write(
            "The project automatically fetches the latest papers from arXiv based on keywords.\n\n"
            "The subheadings represent search keywords. "
            "Only the most recent articles per keyword are kept (up to 100).\n\n"
            "Click the **Watch** button to receive daily email notifications.\n\n"
        )
        f_rm.write(f"Last update: {current_date}\n\n---\n\n")

        f_is.write("---\n")
        f_is.write(f"title: Latest {issues_result} Papers – {get_daily_date()}\n")
        f_is.write("labels: documentation\n---\n")
        f_is.write(
            "**Check the [GitHub page](https://github.com/zezhishao/MTS_Daily_ArXiv) "
            "for a better reading experience and more papers.**\n\n"
        )

        overview_header = f"## 📋 Today's Overview\n*{get_daily_date()}*\n\n"
        f_rm.write(overview_header)
        f_is.write(overview_header)

        for keyword in keywords:
            block = f"### {keyword}\n\n{topic_summaries[keyword]}\n\n"
            f_rm.write(block)
            f_is.write(block)

        f_rm.write("---\n\n## 📄 Paper Details\n\n")
        f_is.write("---\n\n## 📄 Paper Details\n\n")

        for keyword in keywords:
            papers = keyword_papers[keyword]
            print(f"[debug]   Generating table for '{keyword}' ({len(papers)} papers) …")

            f_rm.write(f"### {keyword}\n\n")
            f_is.write(f"### {keyword}\n\n")

            rm_table = generate_table(papers)
            print(f"[debug]   README table generated ({len(rm_table)} chars)")

            is_table = generate_table(papers[:issues_result])
            print(f"[debug]   Issue table generated ({len(is_table)} chars)")

            f_rm.write(rm_table + "\n\n")
            f_is.write(is_table + "\n\n")

    print("[debug] Step 5 complete ✓")

    # ── Step 6: Send email ────────────────────────────────────────────────────
    print("[debug] Step 6: Sending email …")
    send_daily_email(
        subject=f"📄 Daily arXiv Papers – {get_daily_date()}",
        body_markdown=email_body,
    )
    print("[debug] Step 6 complete ✓")

except Exception as exc:
    import traceback
    print(f"[Error] {exc}")
    print("[debug] Full traceback:")
    traceback.print_exc()
    restore_files()
    sys.exit(1)

remove_backups()
print("[main] Done ✓")
