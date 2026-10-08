import copy
import json
import os
import runpy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import llm_utils
import utils


class PaperOutputTests(unittest.TestCase):
    def test_last_author_is_displayed(self):
        atom = """<feed xmlns="http://www.w3.org/2005/Atom" xmlns:arxiv="http://arxiv.org/schemas/atom"><entry>
        <id>https://arxiv.org/abs/1234.5678</id><title>Discovery</title><summary>A finding.</summary>
        <updated>2026-10-08T00:00:00Z</updated><link href="https://arxiv.org/abs/1234.5678"/>
        <author><name>First</name><arxiv:affiliation>Wrong University</arxiv:affiliation></author>
        <author><name>Last</name><arxiv:affiliation>University A</arxiv:affiliation><arxiv:affiliation>Institute B</arxiv:affiliation></author>
        </entry></feed>"""
        with patch("utils.urllib.request.urlopen") as request, patch("time.sleep"):
            request.return_value.__enter__.return_value.read.return_value = (
                atom.encode()
            )
            paper = utils.request_paper_with_arXiv_api("test", 1)[0]
        paper["Finding_Summary"] = "A new phenomenon was found."
        table = utils.generate_table([paper])
        self.assertIn("**Last Author**", table)
        self.assertIn("| Last |", table)
        self.assertNotIn("University A", table)
        self.assertNotIn("Affiliation", table)
        self.assertNotIn("Wrong University", table)
        self.assertIn("A new phenomenon was found.", table)
        paper["Authors"] = []
        self.assertIn("Author not provided", utils.generate_table([paper]))

    def test_findings_prompt_and_incomplete_response(self):
        with (
            patch(
                "llm_utils._call_llm", return_value="[1] Finding A.\n[2] Finding B."
            ) as call,
            patch("time.sleep"),
        ):
            self.assertEqual(
                llm_utils.batch_summarize_findings(["abstract A", "abstract B"]),
                ["Finding A.", "Finding B."],
            )
            self.assertIn("Do not read the full paper", call.call_args.args[0])
            self.assertIn("abstract B", call.call_args.args[0])
        with (
            patch("llm_utils._call_llm", return_value="[1] Finding A."),
            patch("time.sleep"),
        ):
            with self.assertRaises(RuntimeError):
                llm_utils.batch_summarize_findings(["A", "B"])

    def test_filter_caches_decisions_and_rescreens_changed_abstract(self):
        papers = [
            {"Title": "Keep", "Abstract": "Concrete result", "Link": "keep"},
            {"Title": "Reject", "Abstract": "Empty claims", "Link": "reject"},
        ]
        cache = {}
        with (
            patch(
                "llm_utils._call_llm",
                return_value='[{"id":2,"reject":true},{"id":1,"reject":false}]',
            ) as call,
            patch("time.sleep"),
        ):
            self.assertEqual(
                llm_utils.filter_low_quality_papers(papers, cache), [papers[0]]
            )
            self.assertEqual(
                llm_utils.filter_low_quality_papers(papers, cache), [papers[0]]
            )
            self.assertEqual(call.call_count, 1)
        papers[1]["Abstract"] = "Updated concrete evidence"
        with (
            patch(
                "llm_utils._call_llm", return_value='[{"id":1,"reject":false}]'
            ) as call,
            patch("time.sleep"),
        ):
            self.assertEqual(llm_utils.filter_low_quality_papers(papers, cache), papers)
            self.assertEqual(call.call_count, 1)

    def test_filter_policy_version_invalidates_previous_decisions(self):
        papers = [
            {"Title": "Model", "Abstract": "Routine calculation", "Link": "model"}
        ]
        cache = {}
        with (
            patch("llm_utils.QUALITY_FILTER_VERSION", 1),
            patch("llm_utils._call_llm", return_value='[{"id":1,"reject":false}]'),
            patch("time.sleep"),
        ):
            self.assertEqual(llm_utils.filter_low_quality_papers(papers, cache), papers)
        with (
            patch(
                "llm_utils._call_llm", return_value='[{"id":1,"reject":true}]'
            ) as call,
            patch("time.sleep"),
        ):
            self.assertEqual(llm_utils.filter_low_quality_papers(papers, cache), [])
            self.assertEqual(call.call_count, 1)

    def test_filter_rejects_invalid_decisions(self):
        for response in [
            "",
            "[]",
            '[{"id":1,"reject":"false"}]',
            '[{"id":2,"reject":false}]',
        ]:
            with (
                self.subTest(response=response),
                patch("llm_utils._call_llm", return_value=response),
            ):
                with self.assertRaises(RuntimeError):
                    llm_utils.filter_low_quality_papers([{"Link": "paper"}], {})

    def test_rejected_papers_never_reach_summaries_or_output(self):
        main_path = Path(__file__).resolve().parents[1] / "main.py"
        papers = [
            {
                "Title": title,
                "Link": title,
                "Abstract": title + " abstract",
                "Date": "2099-01-01",
                "Authors": ["Last"],
            }
            for title in ["Keep", "Reject"]
        ]
        old_cwd = os.getcwd()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.chdir(tmp)
                events = []

                def screen(*args, **kwargs):
                    events.append("filter")
                    return '[{"id":1,"reject":false},{"id":2,"reject":true}]'

                def summarize(texts, **kwargs):
                    events.append("summary")
                    self.assertEqual(texts, ["Keep abstract"])
                    return ["The accepted finding."]

                for index in range(2):
                    with (
                        patch(
                            "utils.get_daily_papers_by_keyword_with_retries",
                            return_value=copy.deepcopy(papers),
                        ),
                        patch("llm_utils._call_llm", side_effect=screen) as llm,
                        patch(
                            "llm_utils.batch_summarize_findings", side_effect=summarize
                        ) as summary,
                        patch("time.sleep"),
                    ):
                        runpy.run_path(str(main_path), run_name="__main__")
                    self.assertEqual(llm.call_count, 1 if index == 0 else 0)
                    self.assertEqual(summary.call_count, 1 if index == 0 else 0)
                    for output in ["README.md"]:
                        self.assertNotIn("Reject", Path(output).read_text())
                    self.assertNotIn("email", Path("README.md").read_text())
                    digest = json.loads(Path("_data/papers.json").read_text())
                    self.assertEqual(digest["paper_count"], 1)
                    self.assertEqual(digest["new_count"], 1 if index == 0 else 0)
                    website_paper = digest["topics"][0]["papers"][0]
                    self.assertEqual(website_paper["title"], "Keep")
                    self.assertEqual(website_paper["finding"], "The accepted finding.")
                    self.assertEqual(website_paper["last_author"], "Last")
                    self.assertNotIn("Reject", json.dumps(digest))
                    self.assertFalse(Path(".github/ISSUE_TEMPLATE.md").exists())
                    cache = json.loads(Path("paper_cache.json").read_text())
                    self.assertTrue(cache["Reject"]["Quality_Filter"]["reject"])
                    self.assertNotIn("Finding_Summary", cache["Reject"])
                self.assertEqual(events, ["filter", "summary"])
        finally:
            os.chdir(old_cwd)

    def test_legacy_cache_migrates_and_rerun_reuses_finding(self):
        main_path = Path(__file__).resolve().parents[1] / "main.py"
        paper = {
            "Title": "Discovery",
            "Link": "https://arxiv.org/abs/1234.5678",
            "Abstract": "An abstract.",
            "Date": "2099-01-01",
            "Authors": ["First", "Last"],
        }
        old_cwd = os.getcwd()
        try:
            with tempfile.TemporaryDirectory() as tmp:
                os.chdir(tmp)
                Path("paper_cache.json").write_text(
                    json.dumps(
                        {
                            paper["Link"]: {
                                "Abstract_CN": "Legacy translation",
                                "Date": "2099-01-01",
                            }
                        }
                    )
                )
                for index in range(2):
                    with (
                        patch(
                            "utils.get_daily_papers_by_keyword_with_retries",
                            return_value=[copy.deepcopy(paper)],
                        ),
                        patch(
                            "llm_utils.batch_summarize_findings",
                            return_value=["A new phenomenon was found."],
                        ) as summarize,
                        patch(
                            "llm_utils._call_llm",
                            return_value='[{"id":1,"reject":false}]',
                        ),
                        patch("time.sleep"),
                    ):
                        runpy.run_path(str(main_path), run_name="__main__")
                    self.assertEqual(summarize.call_count, 1 if index == 0 else 0)
                    output = Path("README.md").read_text()
                    self.assertIn("A new phenomenon was found.", output)
                    self.assertIn("| Last |", output)
                    self.assertNotIn("Affiliation", output)
                    self.assertNotIn("Legacy translation", output)
                    self.assertIn("0 new today", output)
                    cache = json.loads(Path("paper_cache.json").read_text())
                    self.assertNotIn("Abstract_CN", cache[paper["Link"]])
                    self.assertEqual(cache[paper["Link"]]["Finding_Language"], "en")
        finally:
            os.chdir(old_cwd)


if __name__ == "__main__":
    unittest.main()
