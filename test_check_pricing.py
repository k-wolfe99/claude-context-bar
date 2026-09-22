#!/usr/bin/env python3
"""
Tests for check_pricing.py.

Everything runs against inline fixtures in the pricing page's Markdown format,
so the suite never touches the network.

    python3 test_check_pricing.py
"""
import io, os, tempfile, unittest
from contextlib import redirect_stdout, redirect_stderr

import check_pricing

HEADER = """\
# Pricing

The following table shows pricing for all Claude models:

| Model | Base input tokens | 5m cache writes | 1h cache writes | Cache hits and refreshes | Output tokens |
| :---- | :---------------- | :-------------- | :-------------- | :----------------------- | :------------ |
"""

# Rows matching the rates in claude-context-bar.py, in the page's own format:
# footnote markers, a limited-availability link, and a retired model.
ROWS = {
    "fable51":  "| Claude Fable 5.1 | $10 / MTok | $12.50 / MTok | $20 / MTok | $0.25 / MTok<sup>1</sup> | $50 / MTok |",
    "mythos51": "| Claude Mythos 5.1 ([limited availability](https://anthropic.com/glasswing)) | $10 / MTok | $12.50 / MTok | $20 / MTok | $0.25 / MTok<sup>1</sup> | $50 / MTok |",
    "fable5":   "| Claude Fable 5 | $10 / MTok | $12.50 / MTok | $20 / MTok | $1 / MTok | $50 / MTok |",
    "opus55":   "| Claude Opus 5.5 | $4 / MTok | $5 / MTok | $8 / MTok | $0.20 / MTok<sup>2</sup> | $20 / MTok |",
    "opus5":    "| Claude Opus 5 | $5 / MTok | $6.25 / MTok | $10 / MTok | $0.50 / MTok | $25 / MTok |",
    "opus41":   "| Claude Opus 4.1 ([retired, except on Bedrock and Google Cloud](https://example.com)) | $15 / MTok | $18.75 / MTok | $30 / MTok | $1.50 / MTok | $75 / MTok |",
    "sonnet5":  "| Claude Sonnet 5 | $2 / MTok | $2.50 / MTok | $4 / MTok | $0.20 / MTok | $10 / MTok |",
    "sonnet46": "| Claude Sonnet 4.6 | $3 / MTok | $3.75 / MTok | $6 / MTok | $0.30 / MTok | $15 / MTok |",
    "haiku45":  "| Claude Haiku 4.5 | $1 / MTok | $1.25 / MTok | $2 / MTok | $0.10 / MTok | $5 / MTok |",
}

FOOTER = """
*<sup>1 Cache hits on Claude Fable 5.1 are priced at 0.025x the base input price.</sup>*

## Batch processing

| Model | Batch input | Batch output |
| :---- | :---------- | :----------- |
| Claude Opus 5 | $2.50 / MTok | $12.50 / MTok |
"""


def page(**overrides):
    """The fixture page, with any row replaced by keyword (None drops it)."""
    rows = {**ROWS, **overrides}
    return HEADER + "\n".join(r for r in rows.values() if r is not None) + "\n" + FOOTER


def script():
    return check_pricing.load_script(check_pricing.SCRIPT)


def diff(md):
    return check_pricing.compare(check_pricing.parse_page(md), *script())


class TestParsePage(unittest.TestCase):
    def test_reads_every_current_model(self):
        names = [r["name"] for r in check_pricing.parse_page(page())]
        self.assertIn("Claude Fable 5.1", names)
        self.assertIn("Claude Mythos 5.1", names)
        self.assertIn("Claude Haiku 4.5", names)

    def test_strips_links_and_footnotes(self):
        rows = {r["name"]: r for r in check_pricing.parse_page(page())}
        self.assertEqual(rows["Claude Mythos 5.1"]["read"], 0.25)
        self.assertEqual(rows["Claude Opus 5.5"]["read"], 0.20)

    def test_skips_retired_models(self):
        names = [r["name"] for r in check_pricing.parse_page(page())]
        self.assertFalse(any("4.1" in n for n in names))

    def test_only_reads_the_main_table(self):
        """The batch table below also lists Opus 5; it must not be read as a
        second, cheaper Opus 5."""
        rows = [r for r in check_pricing.parse_page(page()) if r["name"] == "Claude Opus 5"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["input"], 5.0)

    def test_missing_table_is_an_error(self):
        with self.assertRaises(ValueError):
            check_pricing.parse_page("# Pricing\n\nNothing here.\n")

    def test_unparseable_price_is_an_error(self):
        """A layout change must fail loudly, not read as a zero price."""
        with self.assertRaises(ValueError):
            check_pricing.parse_page(page(opus5="| Claude Opus 5 | Contact sales | - | - | - | - |"))


class TestLoadScript(unittest.TestCase):
    def test_reads_prices_without_running_the_script(self):
        prices, _, _ = script()
        self.assertIn(((("opus-5-5", "opus 5.5")), 4.00, 0.05), prices)

    def test_reads_both_write_multipliers(self):
        _, write_5m, write_1h = script()
        self.assertEqual((write_5m, write_1h), (1.25, 2.0))


class TestCompare(unittest.TestCase):
    def test_current_page_matches(self):
        self.assertEqual(diff(page()), [])

    def test_input_rate_change_is_reported(self):
        found = diff(page(sonnet5="| Claude Sonnet 5 | $3 / MTok | $3.75 / MTok | $6 / MTok | $0.30 / MTok | $15 / MTok |"))
        self.assertTrue(any("Claude Sonnet 5" in d and "input" in d for d in found), found)

    def test_cache_read_change_is_reported(self):
        found = diff(page(fable5="| Claude Fable 5 | $10 / MTok | $12.50 / MTok | $20 / MTok | $0.50 / MTok | $50 / MTok |"))
        self.assertTrue(any("Claude Fable 5" in d and "cache read" in d for d in found), found)

    def test_write_multiplier_change_is_reported(self):
        found = diff(page(haiku45="| Claude Haiku 4.5 | $1 / MTok | $1.50 / MTok | $2 / MTok | $0.10 / MTok | $5 / MTok |"))
        self.assertTrue(any("Claude Haiku 4.5" in d and "5m cache write" in d for d in found), found)

    def test_unknown_model_is_reported(self):
        new = "| Claude Tern 1 | $6 / MTok | $7.50 / MTok | $12 / MTok | $0.60 / MTok | $30 / MTok |"
        found = diff(page(tern=new))
        self.assertTrue(any("Claude Tern 1" in d and "no entry" in d for d in found), found)

    def test_point_release_priced_differently_is_reported(self):
        """The Opus 5.5 failure mode: a new model that falls through to an
        older row and silently takes that row's price."""
        new = "| Claude Sonnet 5.5 | $2.50 / MTok | $3.125 / MTok | $5 / MTok | $0.25 / MTok | $12.50 / MTok |"
        found = diff(page(sonnet55=new))
        self.assertTrue(any("Claude Sonnet 5.5" in d for d in found), found)


class TestMain(unittest.TestCase):
    def _run(self, md):
        fd, path = tempfile.mkstemp(suffix=".md")
        with os.fdopen(fd, "w") as f:
            f.write(md)
        out, err = io.StringIO(), io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = check_pricing.main(["--file", path])
        finally:
            os.unlink(path)
        return code, out.getvalue(), err.getvalue()

    def test_in_sync_exits_zero(self):
        code, out, _ = self._run(page())
        self.assertEqual(code, 0)
        self.assertIn("in sync", out)

    def test_drift_exits_one_and_lists_it(self):
        code, out, _ = self._run(page(opus5="| Claude Opus 5 | $6 / MTok | $7.50 / MTok | $12 / MTok | $0.60 / MTok | $30 / MTok |"))
        self.assertEqual(code, 1)
        self.assertIn("Claude Opus 5", out)

    def test_unreadable_page_exits_two(self):
        code, _, err = self._run("# Pricing\n")
        self.assertEqual(code, 2)
        self.assertIn("pricing table", err)


if __name__ == "__main__":
    unittest.main(verbosity=2)
