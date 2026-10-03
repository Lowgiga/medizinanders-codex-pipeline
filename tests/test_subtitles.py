import hashlib
import tempfile
import unittest
from pathlib import Path

from medizinanders import subtitles


def _cue(text, start="00:00:00,000", end="00:00:02,000", index=1):
    return f"{index}\n{start} --> {end}\n{text}\n"


def _by_id(result):
    return {check["id"]: check for check in result["checks"]}


class SubtitleValidationTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name) / "captions.srt"

    def tearDown(self):
        self.directory.cleanup()

    def validate(self, content, font_path=None):
        self.path.write_bytes(content if isinstance(content, bytes) else content.encode("utf-8"))
        return subtitles.validate_srt(self.path, font_path=font_path)

    def test_valid_text_is_not_claimed_as_measured_sync_or_pixel_width(self):
        result = self.validate(_cue("Das ist ein Satz."))
        checks = _by_id(result)
        self.assertEqual(result["ergebnis"], "pruefung_unvollstaendig")
        for check_id in ("srt_utf8", "srt_syntax", "srt_line_length", "srt_cps", "srt_cue_duration", "srt_timeline"):
            self.assertEqual(checks[check_id]["status"], "bestanden")
        for check_id in ("srt_pixel_width", "srt_audio_sync", "srt_burn_in"):
            self.assertEqual(checks[check_id]["status"], "nicht_geprueft")
        self.assertEqual(result["sha256"], hashlib.sha256(self.path.read_bytes()).hexdigest())
        self.assertIn("100 ms", checks["srt_audio_sync"]["soll"])

    def test_utf8_bom_and_crlf_are_valid(self):
        content = b"\xef\xbb\xbf" + _cue("Ärztliche Rückfrage.").replace("\n", "\r\n").encode("utf-8")
        checks = _by_id(self.validate(content))
        self.assertEqual(checks["srt_utf8"]["status"], "bestanden")
        self.assertEqual(checks["srt_syntax"]["status"], "bestanden")

    def test_latin1_and_utf16_cannot_pass_utf8(self):
        for encoding in ("latin-1", "utf-16"):
            checks = _by_id(self.validate(_cue("Ärzte").encode(encoding)))
            self.assertEqual(checks["srt_utf8"]["status"], "fehlgeschlagen")

    def test_syntax_error_does_not_hide_partial_file(self):
        content = _cue("Okay.") + "\n2\n00:00:xx,000 --> 00:00:04,000\nFehler.\n"
        checks = _by_id(self.validate(content))
        self.assertEqual(checks["srt_syntax"]["status"], "fehlgeschlagen")
        self.assertEqual(checks["srt_cps"]["status"], "nicht_geprueft")

    def test_invalid_seconds_and_empty_file_fail(self):
        for content in ("", _cue("Text.", start="00:00:61,000")):
            self.assertEqual(_by_id(self.validate(content))["srt_syntax"]["status"], "fehlgeschlagen")

    def test_missing_file_returns_clear_failure(self):
        result = subtitles.validate_srt(self.path)
        self.assertEqual(result["ergebnis"], "nacharbeit_erforderlich")
        self.assertIsNone(result["sha256"])

    def test_three_lines_fail(self):
        checks = _by_id(self.validate(_cue("Eine\nzweite\ndritte")))
        self.assertEqual(checks["srt_line_count"]["status"], "fehlgeschlagen")

    def test_28_characters_inclusive_29_fail(self):
        for length, expected in ((28, "bestanden"), (29, "fehlgeschlagen")):
            checks = _by_id(self.validate(_cue("a" * length)))
            self.assertEqual(checks["srt_line_length"]["status"], expected)

    def test_duration_bounds_are_inclusive(self):
        for end, expected in (("00:00:00,799", "fehlgeschlagen"), ("00:00:00,800", "bestanden"),
                              ("00:00:04,000", "bestanden"), ("00:00:04,001", "fehlgeschlagen")):
            checks = _by_id(self.validate(_cue("Text", end=end)))
            self.assertEqual(checks["srt_cue_duration"]["status"], expected)

    def test_cps_counts_spaces_and_not_line_breaks(self):
        for content, expected in (("123456789\n123456789", "bestanden"), ("123456789 123456789", "fehlgeschlagen")):
            checks = _by_id(self.validate(_cue(content, end="00:00:01,000")))
            self.assertEqual(checks["srt_cps"]["status"], expected)

    def test_54_second_boundary_inclusive(self):
        for end, expected in (("00:00:54,000", "bestanden"), ("00:00:54,001", "fehlgeschlagen")):
            checks = _by_id(self.validate(_cue("Text", start="00:00:52,000", end=end)))
            self.assertEqual(checks["srt_timeline"]["status"], expected)

    def test_overlap_and_backward_timing_fail(self):
        content = _cue("Erster.", end="00:00:03,000") + "\n" + _cue("Zweiter.", start="00:00:02,000", end="00:00:04,000", index=2)
        self.assertEqual(_by_id(self.validate(content))["srt_timeline"]["status"], "fehlgeschlagen")
        self.assertEqual(_by_id(self.validate(_cue("Text", start="00:00:02,000", end="00:00:01,000")))["srt_timeline"]["status"], "fehlgeschlagen")

    def test_nonsequential_numbers_fail(self):
        self.assertEqual(_by_id(self.validate(_cue("Text", index=7)))["srt_index_sequence"]["status"], "fehlgeschlagen")

    def test_known_negation_number_unit_splits_are_rejected(self):
        for content in ("Das hilft nicht\nallen.", "Eine Dosis von 5\nmg wirkt.", "Etwa 3 bis\n5 mg.", "Der Wert ist −\n5 mg."):
            self.assertEqual(_by_id(self.validate(_cue(content, end="00:00:04,000")))["srt_semantic_wrap"]["status"], "fehlgeschlagen", content)

    def test_sensitive_split_across_cues_is_also_rejected(self):
        content = _cue("Eine Dosis von 5") + "\n" + _cue("mg täglich.", start="00:00:02,000", end="00:00:04,000", index=2)
        self.assertEqual(_by_id(self.validate(content))["srt_semantic_wrap"]["status"], "fehlgeschlagen")

    def test_markup_and_invisible_control_characters_fail(self):
        for content in ("<b>Text</b>", "{\\an8}Text", "Text\x00", "Text\tText"):
            self.assertEqual(_by_id(self.validate(_cue(content)))["srt_plain_text"]["status"], "fehlgeschlagen")

    def test_missing_or_bogus_font_is_unmeasured(self):
        for font in (self.path.parent / "missing.ttf", self.path.parent / "bogus.ttf"):
            if font.name == "bogus.ttf":
                font.write_bytes(b"not a real font")
            check = _by_id(self.validate(_cue("Text"), font))["srt_pixel_width"]
            self.assertEqual(check["status"], "nicht_geprueft")

    def test_real_replacement_font_does_not_count_as_montserrat(self):
        candidates = (Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
                      Path("/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"))
        font = next((path for path in candidates if path.exists()), None)
        if not font:
            self.skipTest("No installed replacement font for negative font test")
        check = _by_id(self.validate(_cue("Text"), font))["srt_pixel_width"]
        self.assertEqual(check["status"], "nicht_geprueft")


class SubtitleGenerationTests(unittest.TestCase):
    def _validate(self, srt):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "estimated.srt"
            path.write_text(srt, encoding="utf-8")
            return subtitles.validate_srt(path)

    def test_generation_preserves_text_and_satisfies_measurable_limits(self):
        text = "Das Mittel hilft nicht allen. Eine Dosis von 5 mg ist kein Beweis. Frage bitte deine Ärztin."
        srt = subtitles.generate_srt({"sprechertext": text}, {})
        result = self._validate(srt)
        reconstructed = " ".join(" ".join(cue["lines"]) for cue in result["cues"])
        self.assertEqual(reconstructed, text)
        self.assertTrue(all(check["status"] == "bestanden" for check in result["checks"]
                            if check["id"] not in {"srt_pixel_width", "srt_audio_sync", "srt_burn_in"}))
        self.assertIn("GESCHÄTZTE", subtitles.GENERATED_TIMING_BASIS)
        self.assertEqual(_by_id(result)["srt_audio_sync"]["status"], "nicht_geprueft")

    def test_short_text_is_not_spread_over_54_seconds_without_scene_plan(self):
        result = self._validate(subtitles.generate_srt({"sprechertext": "Ein kurzer Satz."}, {}))
        self.assertLess(result["cues"][-1]["ende_ms"], 4000)

    def test_scene_bounds_supply_estimates_and_silent_disclaimer_has_no_cues(self):
        first, second = "Das ist ein Beispiel.", "Es gilt nicht immer."
        a05 = {"sprechertext": first + " " + second}
        a06 = {"szenen": [{"sprechertext": first, "start_ms": 500, "ende_ms": 4500},
                         {"sprechertext": second, "start_ms": 49000, "ende_ms": 53000},
                         {"sprechertext": "", "start_ms": 54000, "ende_ms": 58000}]}
        result = self._validate(subtitles.generate_srt(a05, a06))
        self.assertEqual(result["cues"][0]["start_ms"], 500)
        self.assertLessEqual(result["cues"][-1]["ende_ms"], 54000)
        self.assertFalse(any(cue["start_ms"] >= 54000 for cue in result["cues"]))

    def test_caption_basis_is_authoritative(self):
        srt = subtitles.generate_srt({"sprechertext": "Andere Worte.", "untertitel_basis": "Die Basis."}, {})
        self.assertIn("Die Basis.", srt)
        self.assertNotIn("Andere Worte.", srt)

    def test_mismatched_scene_text_is_not_invented(self):
        with self.assertRaisesRegex(ValueError, "stimmt nicht"):
            subtitles.generate_srt({"sprechertext": "Eine Aussage."},
                                   {"szenen": [{"sprechertext": "Andere Aussage.", "start_ms": 0, "ende_ms": 4000}]})

    def test_negations_numbers_ranges_and_units_stay_atomic(self):
        text = "Das ist nicht wirksam. Es geht um 3 bis 5 mg und 1 von 100 Menschen. Der Wert ist − 5 mg."
        atoms = subtitles._atomic_phrases(text)
        self.assertIn("nicht wirksam.", atoms)
        self.assertIn("3 bis 5 mg", atoms)
        self.assertIn("1 von 100 Menschen.", atoms)
        self.assertIn("− 5 mg.", atoms)
        checks = _by_id(self._validate(subtitles.generate_srt({"sprechertext": text}, {})))
        self.assertEqual(checks["srt_semantic_wrap"]["status"], "bestanden")

    def test_unbreakable_long_word_is_not_truncated(self):
        with self.assertRaisesRegex(ValueError, "länger als 28"):
            subtitles.generate_srt({"sprechertext": "x" * 29}, {})

    def test_too_short_window_raises_instead_of_fabricating_sync(self):
        text = "Ein langer Satz mit vielen Zeichen und wichtigen Informationen."
        with self.assertRaisesRegex(ValueError, "zu kurz"):
            subtitles.generate_srt({"sprechertext": text},
                                   {"szenen": [{"sprechertext": text, "start_ms": 0, "ende_ms": 800}]})

    def test_too_long_narration_raises_instead_of_hiding_words(self):
        text = " ".join(["Ein Satz enthält Text."] * 90)
        with self.assertRaisesRegex(ValueError, "zu kurz"):
            subtitles.generate_srt({"sprechertext": text}, {})

    def test_invalid_scene_timeline_or_missing_text_raises(self):
        for a05, a06 in (({}, {}), ({"sprechertext": "Text."}, {"szenen": [
                {"sprechertext": "Text.", "start_ms": 54000, "ende_ms": 58000}]})):
            with self.assertRaises(ValueError):
                subtitles.generate_srt(a05, a06)


if __name__ == "__main__":
    unittest.main()
