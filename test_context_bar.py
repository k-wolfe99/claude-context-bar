#!/usr/bin/env python3
"""
Tests for claude-context-bar.py.

Runs the script as a subprocess with synthetic payloads on stdin, controlling
the cache clock via the mtime of a temporary transcript file.

    python3 test_context_bar.py
"""
import json, os, re, subprocess, sys, tempfile, time, unittest
from datetime import date

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "claude-context-bar.py")

ANSI = re.compile(r"\033\[[0-9;]*m")
TTL = 300


def run(payload):
    """Return (plain_text, raw_output) for a payload."""
    proc = subprocess.run(
        [sys.executable, SCRIPT],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        check=True,
    )
    return ANSI.sub("", proc.stdout), proc.stdout


def payload(model_id="claude-opus-5", display_name="Opus 5", tokens=44_800,
            total=1_000_000, transcript_path=None, used_percentage=4.5):
    body = {
        "model": {"id": model_id, "display_name": display_name},
        "context_window": {
            "context_window_size": total,
            "used_percentage": used_percentage,
            "current_usage": {"input_tokens": tokens},
        },
    }
    if transcript_path is not None:
        body["transcript_path"] = transcript_path
    return body


class Transcript:
    """A transcript file whose mtime is pinned to a chosen instant.

    Pass `age` for "N seconds ago", or `at` for an absolute epoch.
    """

    def __init__(self, age=None, at=None):
        self.stamp = at if at is not None else time.time() - (age or 0)

    def __enter__(self):
        fd, self.path = tempfile.mkstemp(suffix=".jsonl")
        os.close(fd)
        os.utime(self.path, (self.stamp, self.stamp))
        return self.path

    def __exit__(self, *exc):
        os.unlink(self.path)


def local_epoch(y, mo, d, h, mi):
    """Epoch seconds for a local wall-clock time, so tests are timezone-proof."""
    return time.mktime((y, mo, d, h, mi, 0, 0, 0, -1))


class TestExpiryTime(unittest.TestCase):
    def test_expiry_is_last_request_plus_ttl(self):
        # A request at 1:20pm keeps the cache alive until 1:25pm.
        with Transcript(at=local_epoch(2026, 8, 1, 13, 20)) as path:
            text, _ = run(payload(transcript_path=path))
        self.assertIn("⏱ til 1:25pm", text)

    def test_expiry_advances_with_a_newer_request(self):
        """A later request pushes the expiry out — this is the 'updates on tool
        calls' behaviour, since every tool call appends to the transcript."""
        with Transcript(at=local_epoch(2026, 8, 1, 13, 20)) as path:
            earlier, _ = run(payload(transcript_path=path))
        with Transcript(at=local_epoch(2026, 8, 1, 13, 47)) as path:
            later, _ = run(payload(transcript_path=path))
        self.assertIn("⏱ til 1:25pm", earlier)
        self.assertIn("⏱ til 1:52pm", later)

    def test_expiry_in_the_past_is_still_reported(self):
        """An elapsed cache reports the time it lapsed rather than hiding it —
        the user compares against their own clock."""
        with Transcript(at=local_epoch(2026, 8, 1, 9, 3)) as path:
            text, _ = run(payload(transcript_path=path))
        self.assertIn("⏱ til 9:08am", text)

    def test_no_leading_zero_on_the_hour(self):
        with Transcript(at=local_epoch(2026, 8, 1, 15, 0)) as path:
            text, _ = run(payload(transcript_path=path))
        self.assertIn("til 3:05pm", text)
        self.assertNotIn("03:05", text)

    def test_midnight_is_twelve_am(self):
        with Transcript(at=local_epoch(2026, 8, 1, 0, 0)) as path:
            text, _ = run(payload(transcript_path=path))
        self.assertIn("til 12:05am", text)

    def test_noon_is_twelve_pm(self):
        with Transcript(at=local_epoch(2026, 8, 1, 11, 58)) as path:
            text, _ = run(payload(transcript_path=path))
        self.assertIn("til 12:03pm", text)

    def test_a_fresh_transcript_expires_five_minutes_out(self):
        now = time.time()
        with Transcript(age=0) as path:
            text, _ = run(payload(transcript_path=path))
        t = time.localtime(now + TTL)
        expected = f"{t.tm_hour % 12 or 12}:{t.tm_min:02d}"
        self.assertIn(f"til {expected}", text)


class TestPricing(unittest.TestCase):
    """Both prices show at once: at paint time it is genuinely unknowable which
    side of the expiry the next request will land on."""

    def _prices(self, **kwargs):
        with Transcript(age=0) as path:
            text, _ = run(payload(transcript_path=path, **kwargs))
        return re.findall(r"\$[\d.]+", text)

    def test_shows_read_then_write(self):
        # 44,800 tokens at $5/MTok: read 0.1x = $0.022, write 1.25x = $0.280
        self.assertEqual(self._prices(), ["$0.022", "$0.280"])

    def test_arrow_separates_them(self):
        with Transcript(age=0) as path:
            text, _ = run(payload(transcript_path=path))
        self.assertIn("$0.022→$0.280", text)

    def test_fable_5(self):
        self.assertEqual(
            self._prices(model_id="claude-fable-5", display_name="Fable 5"),
            ["$0.045", "$0.560"],
        )

    def test_haiku_4_5(self):
        self.assertEqual(
            self._prices(model_id="claude-haiku-4-5", display_name="Haiku 4.5"),
            ["$0.004", "$0.056"],
        )

    def test_sonnet_4_6_uses_standard_rate(self):
        self.assertEqual(
            self._prices(model_id="claude-sonnet-4-6", display_name="Sonnet 4.6"),
            ["$0.013", "$0.168"],
        )

    def test_sonnet_5_intro_pricing(self):
        intro = date.today() <= date(2026, 8, 31)
        self.assertEqual(
            self._prices(model_id="claude-sonnet-5", display_name="Sonnet 5"),
            ["$0.009", "$0.112"] if intro else ["$0.013", "$0.168"],
        )

    def test_write_is_12_5x_the_read(self):
        # 800k tokens on Opus 5 divides cleanly: $0.400 read, $5.000 write.
        read, write = self._prices(tokens=800_000)
        self.assertEqual((read, write), ("$0.400", "$5.000"))
        self.assertAlmostEqual(float(write[1:]) / float(read[1:]), 12.5, places=6)

    def test_full_context_stays_within_seven_characters(self):
        read, write = self._prices(model_id="claude-fable-5", display_name="Fable 5",
                                   tokens=1_000_000)
        self.assertEqual(write, "$12.500")
        self.assertLessEqual(len(write), 7)


class TestColor(unittest.TestCase):
    """The read price is green and the write price red, so the penalty reads at
    a glance. Nothing is coloured by time remaining — that value is frozen at
    paint time and would be permanently green, which would be a lie."""

    def _raw(self):
        with Transcript(age=0) as path:
            _, raw = run(payload(transcript_path=path))
        return raw

    def test_read_price_is_green(self):
        self.assertRegex(self._raw(), r"\033\[38;5;82m\$0\.022")

    def test_write_price_is_red(self):
        self.assertRegex(self._raw(), r"\033\[38;5;196m\$0\.280")

    def test_expiry_time_is_dim(self):
        self.assertRegex(self._raw(), r"\033\[38;5;245m⏱ til ")


class TestDegradation(unittest.TestCase):
    """The cache readout must never take the existing bar down with it."""

    def _baseline(self):
        text, _ = run(payload())  # no transcript_path at all
        return text

    def test_missing_transcript_path_omits_the_segment(self):
        self.assertNotIn("⏱", self._baseline())

    def test_missing_transcript_path_keeps_the_bar_intact(self):
        self.assertIn("Opus 5", self._baseline())
        self.assertIn("44.8k / 1M (4.5%)", self._baseline())

    def test_unreadable_transcript_omits_the_segment(self):
        text, _ = run(payload(transcript_path="/nonexistent/transcript.jsonl"))
        self.assertNotIn("⏱", text)
        self.assertIn("44.8k / 1M (4.5%)", text)

    def test_unknown_model_keeps_expiry_but_drops_price(self):
        with Transcript(at=local_epoch(2026, 8, 1, 13, 20)) as path:
            text, _ = run(payload(model_id="claude-something-new",
                                  display_name="Something New",
                                  transcript_path=path))
        self.assertIn("⏱ til 1:25pm", text)
        self.assertNotIn("$", text)

    def test_no_token_data_falls_back(self):
        with Transcript(age=0) as path:
            text, _ = run({"model": {"display_name": "Opus 5"},
                           "transcript_path": path})
        self.assertEqual(text, "Opus 5 | Context: no data yet")
        self.assertNotIn("⏱", text)


class TestBar(unittest.TestCase):
    def test_bar_is_24_cells_wide(self):
        with Transcript(age=0) as path:
            text, _ = run(payload(transcript_path=path))
        self.assertEqual(len(re.search(r"\[([█░]+)\]", text).group(1)), 24)

    def test_bar_still_reflects_context_usage(self):
        with Transcript(age=0) as path:
            text, _ = run(payload(transcript_path=path, used_percentage=50.0))
        bar = re.search(r"\[([█░]+)\]", text).group(1)
        self.assertEqual(bar.count("█"), 12)  # 50% of 24


if __name__ == "__main__":
    unittest.main(verbosity=2)
