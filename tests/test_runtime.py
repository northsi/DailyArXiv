import contextlib
import io
import os
import runpy
import tempfile
import unittest
import urllib.error
import urllib.parse
from pathlib import Path
from unittest.mock import MagicMock, patch

import llm_utils
import main
import utils


class RuntimeTests(unittest.TestCase):
    def test_import_does_not_run_pipeline_or_create_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = os.getcwd()
            try:
                os.chdir(tmp)
                with (
                    patch("utils.back_up_files") as backup,
                    patch("utils.get_daily_papers_by_keyword_with_retries") as fetch,
                ):
                    runpy.run_path(str(Path(main.__file__)), run_name="import_only")
                backup.assert_not_called()
                fetch.assert_not_called()
                self.assertEqual(list(Path(tmp).iterdir()), [])
            finally:
                os.chdir(original)

    def test_failed_run_restores_reports_and_preserves_exit_status(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = os.getcwd()
            try:
                os.chdir(tmp)
                Path(".github").mkdir()
                for path in utils.REPORT_FILES:
                    Path(path).parent.mkdir(parents=True, exist_ok=True)
                    Path(path).write_text("original " + path)

                def fail():
                    for path in utils.REPORT_FILES:
                        Path(path).write_text("partial output")
                    raise RuntimeError("failed update")

                with (
                    patch("main.run_pipeline", side_effect=fail),
                    contextlib.redirect_stdout(io.StringIO()),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    with self.assertRaises(SystemExit) as error:
                        main.main()
                self.assertEqual(error.exception.code, 1)
                for path in utils.REPORT_FILES:
                    self.assertEqual(Path(path).read_text(), "original " + path)
                    self.assertFalse(Path(path + ".bk").exists())
            finally:
                os.chdir(original)

    def test_llm_retry_policy_and_client_cleanup(self):
        for failures in [0, 1, 3]:
            with self.subTest(failures=failures):
                client = MagicMock()
                response = MagicMock()
                response.choices[0].message.content = " result "
                client.chat.completions.create.side_effect = [
                    RuntimeError("temporary")
                ] * failures + [response]
                with (
                    patch("llm_utils._get_client", return_value=client),
                    patch("time.sleep") as sleep,
                    contextlib.redirect_stdout(io.StringIO()),
                ):
                    result = llm_utils._call_llm("prompt")
                self.assertEqual(result, "" if failures == 3 else "result")
                self.assertEqual(
                    client.chat.completions.create.call_count, min(failures + 1, 3)
                )
                self.assertEqual(sleep.call_count, min(failures, 2))
                client.close.assert_called_once()

    def test_arxiv_retry_after_and_response_cleanup(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = (
            b'<feed xmlns="http://www.w3.org/2005/Atom"/>'
        )
        error = urllib.error.HTTPError(
            "http://example.org", 429, "rate limited", {"Retry-After": "7"}, None
        )
        with (
            patch(
                "utils.urllib.request.urlopen", side_effect=[error, response]
            ) as request,
            patch("time.sleep") as sleep,
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(utils.request_paper_with_arXiv_api("test", 1), [])
        self.assertEqual(request.call_count, 2)
        self.assertIn(unittest.mock.call(7), sleep.call_args_list)
        response.__exit__.assert_called_once()

    def test_boolean_keywords_and_field_matching(self):
        self.assertEqual(
            utils.build_arxiv_query("superconductivity OR superconducting"),
            '(ti:"superconductivity" OR abs:"superconductivity") OR '
            '(ti:"superconducting" OR abs:"superconducting")',
        )
        self.assertEqual(
            utils.build_arxiv_query("NbSe2", "AND"), 'ti:"NbSe2" AND abs:"NbSe2"'
        )
        self.assertEqual(
            utils.build_arxiv_query("high temperature"),
            'ti:"high temperature" OR abs:"high temperature"',
        )
        self.assertEqual(
            utils.build_arxiv_query("order parameter"),
            'ti:"order parameter" OR abs:"order parameter"',
        )
        self.assertEqual(
            utils.build_arxiv_query("superconductivity or superconducting"),
            utils.build_arxiv_query("superconductivity OR superconducting"),
        )
        for keyword in ["", "superconductivity OR", "OR superconducting", "a OR OR b"]:
            with self.subTest(keyword=keyword), self.assertRaises(ValueError):
                utils.build_arxiv_query(keyword)

    def test_arxiv_request_encodes_boolean_expression(self):
        response = MagicMock()
        response.__enter__.return_value.read.return_value = (
            b'<feed xmlns="http://www.w3.org/2005/Atom"/>'
        )
        with (
            patch("utils.urllib.request.urlopen", return_value=response) as request,
            patch("time.sleep"),
        ):
            utils.request_paper_with_arXiv_api(
                "superconductivity OR superconducting", 10
            )
        params = urllib.parse.parse_qs(
            urllib.parse.urlsplit(request.call_args.args[0]).query
        )
        self.assertEqual(
            params["search_query"],
            [utils.build_arxiv_query("superconductivity OR superconducting")],
        )
        self.assertEqual(params["max_results"], ["10"])
        self.assertEqual(params["sortBy"], ["lastUpdatedDate"])

    def test_empty_digest_has_valid_website_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = os.getcwd()
            try:
                os.chdir(tmp)
                main.write_site_data({"Physics": []}, {"Physics": []}, "2026-10-08")
                import json

                digest = json.loads(Path("_data/papers.json").read_text())
                self.assertEqual(digest["paper_count"], 0)
                self.assertEqual(digest["new_count"], 0)
                self.assertEqual(digest["topics"][0]["papers"], [])
            finally:
                os.chdir(original)

    def test_tag_filter_preserves_order_and_avoids_duplicates(self):
        papers = [
            {"Tags": ["cond-mat.supr-con", "physics.optics"]},
            {"Tags": ["cs.AI"]},
            {"Tags": ["quant-ph"]},
        ]
        self.assertEqual(utils.filter_tags(papers), [papers[0], papers[2]])
