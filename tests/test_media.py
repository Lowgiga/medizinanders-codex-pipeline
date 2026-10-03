import hashlib
import json
import shutil
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from medizinanders import media


def _by_id(checks):
    return {check["id"]: check for check in checks}


def _video_stream():
    return {"index": 0, "codec_type": "video", "width": 1080, "height": 1920,
            "sample_aspect_ratio": "1:1", "pix_fmt": "yuv420p", "codec_name": "h264",
            "profile": "High", "level": 41, "time_base": "1/15360", "duration_ts": 890880,
            "color_primaries": "bt709", "color_transfer": "bt709", "color_space": "bt709",
            "has_b_frames": 2, "field_order": "progressive"}


def _probe():
    return {"streams": [_video_stream(), {"index": 1, "codec_type": "audio", "codec_name": "aac",
             "profile": "LC", "sample_rate": "48000", "channels": 2, "channel_layout": "stereo"}],
            "format": {"duration": "58.000000"}}


def _frames(count=1740):
    return [{"pts": index * 512, "key_frame": int(index % 60 == 0), "interlaced_frame": 0,
             "pict_type": "I" if index % 60 == 0 else "P" if index % 3 == 0 else "B",
             "width": 1080, "height": 1920, "sample_aspect_ratio": "1:1", "pix_fmt": "yuv420p"}
            for index in range(count)]


def _box(kind, payload=b"", *, extended=False):
    if extended:
        return struct.pack(">I4sQ", 1, kind, 16 + len(payload)) + payload
    return struct.pack(">I4s", 8 + len(payload), kind) + payload


def _dummy_mp4(path, faststart=True):
    ftyp = _box(b"ftyp", b"isom\x00\x00\x02\x00isommp42")
    moov, mdat = _box(b"moov", extended=True), _box(b"mdat", b"DEMO")
    path.write_bytes(ftyp + (moov + mdat if faststart else mdat + moov))


class MediaMeasurementTests(unittest.TestCase):
    def test_profile_metadata_measures_real_required_fields(self):
        checks = _by_id(media._metadata_checks(_probe()))
        self.assertTrue(all(check["status"] == "bestanden" for check in checks.values()))

    def test_duration_is_exact_and_not_rounded(self):
        probe = _probe()
        probe["format"]["duration"] = "58.001000"
        self.assertEqual(_by_id(media._metadata_checks(probe))["duration"]["status"], "fehlgeschlagen")

    def test_rotated_resolution_does_not_pass(self):
        probe = _probe()
        probe["streams"][0]["side_data_list"] = [{"rotation": 90}]
        self.assertEqual(_by_id(media._metadata_checks(probe))["video_resolution"]["status"], "fehlgeschlagen")

    def test_hdr_or_missing_color_tags_never_pass(self):
        probe = _probe()
        probe["streams"][0]["color_transfer"] = "smpte2084"
        self.assertEqual(_by_id(media._metadata_checks(probe))["video_color"]["status"], "fehlgeschlagen")
        probe["streams"][0]["color_transfer"] = "unknown"
        self.assertEqual(_by_id(media._metadata_checks(probe))["video_color"]["status"], "nicht_geprueft")

    def test_actual_1740_frame_cfr_and_gop(self):
        checks = _by_id(media._frame_checks(_frames(), _video_stream()))
        for check_id in ("video_frame_count", "video_cfr", "video_gop", "video_progressive", "video_b_frames",
                         "video_resolution", "video_sar", "video_pixel_format"):
            self.assertEqual(checks[check_id]["status"], "bestanden", check_id)

    def test_midstream_frame_property_changes_cannot_hide_behind_metadata(self):
        frames = _frames()
        frames[700].update({"width": 720, "height": 1280, "sample_aspect_ratio": "4:3", "pix_fmt": "yuv420p10le"})
        checks = _by_id(media._frame_checks(frames, _video_stream()))
        for check_id in ("video_resolution", "video_sar", "video_pixel_format"):
            self.assertEqual(checks[check_id]["status"], "fehlgeschlagen")
            self.assertEqual(checks[check_id]["ist"]["first_mismatch_indices"], [700])

    def test_declared_30fps_does_not_mask_vfr_pts(self):
        frames = _frames()
        frames[900]["pts"] += 128
        video = {**_video_stream(), "r_frame_rate": "30/1", "avg_frame_rate": "30/1"}
        self.assertEqual(_by_id(media._frame_checks(frames, video))["video_cfr"]["status"], "fehlgeschlagen")

    def test_duplicate_pts_or_nonzero_start_fails(self):
        duplicated, shifted = _frames(3), _frames(3)
        duplicated[1]["pts"] = duplicated[0]["pts"]
        for frame in shifted:
            frame["pts"] += 512
        for frames in (duplicated, shifted):
            self.assertEqual(_by_id(media._frame_checks(frames, _video_stream()))["video_cfr"]["status"], "fehlgeschlagen")

    def test_missing_actual_pts_is_unmeasured(self):
        frames = _frames(4)
        for frame in frames:
            frame["best_effort_timestamp"] = frame.pop("pts")
        self.assertEqual(_by_id(media._frame_checks(frames, _video_stream()))["video_cfr"]["status"], "nicht_geprueft")

    def test_actual_interlacing_or_long_gop_fails(self):
        frames = _frames()
        frames[100]["interlaced_frame"] = 1
        frames[60]["key_frame"] = 0
        checks = _by_id(media._frame_checks(frames, _video_stream()))
        self.assertEqual(checks["video_progressive"]["status"], "fehlgeschlagen")
        self.assertEqual(checks["video_gop"]["status"], "fehlgeschlagen")

    def test_decoder_reorder_depth_is_not_b_frame_proof(self):
        frames = _frames(12)
        for frame in frames:
            frame["pict_type"] = "P"
        self.assertEqual(_by_id(media._frame_checks(frames, _video_stream()))["video_b_frames"]["status"], "fehlgeschlagen")

    def test_closed_gop_requires_matching_idr_headers(self):
        frames = _frames(3)
        trace = "\n".join(
            f"[trace_headers @ 0x1] Packet: 100 bytes, {'key frame, ' if i == 0 else ''}pts {i * 512}, dts {i * 512}, duration 512.\n"
            f"[trace_headers @ 0x1] 3 nal_unit_type 00101 = {5 if i == 0 else 1}"
            for i in range(3))
        self.assertEqual(media._closed_gop_check(trace, frames, _video_stream())["status"], "bestanden")
        open_gop = trace.replace("00101 = 5", "00001 = 1")
        self.assertEqual(media._closed_gop_check(open_gop, frames, _video_stream())["status"], "fehlgeschlagen")
        self.assertEqual(media._closed_gop_check("", frames, _video_stream())["status"], "nicht_geprueft")

    def test_changed_in_band_sps_cannot_hide_codec_or_bit_depth_changes(self):
        valid = "[trace_headers] 8 profile_idc 01100100 = 100\n[trace_headers] 24 level_idc 00101001 = 41\n"
        self.assertEqual(media._avc_parameter_checks(valid), [])
        changed = valid + "[trace_headers] 8 profile_idc 01001101 = 77\n[trace_headers] 24 level_idc 00101010 = 42\n[trace_headers] 36 bit_depth_luma_minus8 011 = 2\n"
        checks = _by_id(media._avc_parameter_checks(changed))
        self.assertEqual(checks["video_codec"]["status"], "fehlgeschlagen")
        self.assertEqual(checks["video_pixel_format"]["status"], "fehlgeschlagen")

    def test_one_second_packet_peak_uses_sliding_not_fixed_bins(self):
        packets = [{"stream_index": 0, "size": 1_100_000, "dts_time": time,
                    "duration_time": "0.033333"} for time in ("0.9", "1.1")]
        rates = media._packet_rates(packets, {"index": 0})
        self.assertEqual(rates["max_rolling_1s_bits_per_second"], 17_600_000)

    def test_one_second_window_is_end_exclusive(self):
        packets = [{"stream_index": 0, "size": 100, "dts_time": time,
                    "duration_time": "0.033333"} for time in ("0.0", "1.0")]
        self.assertEqual(media._packet_rates(packets, {"index": 0})["max_rolling_1s_bits_per_second"], 800)

    def test_missing_packet_duration_not_fabricated(self):
        self.assertIsNone(media._packet_rates([{"stream_index": 0, "size": 100, "pts_time": "0"}], {"index": 0}))

    def test_loudness_and_true_peak_are_real_report_values(self):
        raw = "lavfi.r128.I=-14.123\nIntegrated loudness:\n I: -14.1 LUFS\nTrue peak:\n Peak: -1.8 dBFS\n"
        checks = _by_id(media._loudness_checks(raw))
        self.assertEqual(checks["audio_loudness"]["ist"]["integrated_lufs"], -14.123)
        self.assertEqual(checks["audio_loudness"]["status"], "bestanden")
        self.assertEqual(checks["audio_true_peak"]["status"], "bestanden")
        self.assertEqual(_by_id(media._loudness_checks(raw.replace("-1.8", "-1.4")))["audio_true_peak"]["status"], "fehlgeschlagen")

    def test_rounded_true_peak_on_limit_remains_unverified(self):
        check = _by_id(media._loudness_checks("I: -14.0 LUFS\nPeak: -1.5 dBFS"))["audio_true_peak"]
        self.assertEqual(check["status"], "nicht_geprueft")

    def test_silence_requires_all_four_seconds_and_digital_zero(self):
        raw = "[astats] Overall\n[astats] Peak level dB: -inf\n[astats] Number of samples: 192000"
        self.assertEqual(media._silence_check(raw)["status"], "bestanden")
        self.assertEqual(media._silence_check(raw.replace("192000", "48000"))["status"], "nicht_geprueft")
        self.assertEqual(media._silence_check(raw.replace("-inf", "-65.0"))["status"], "fehlgeschlagen")


class MediaReportTests(unittest.TestCase):
    def test_mp4_faststart_uses_actual_atom_order(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "misleading-extension.bin"
            _dummy_mp4(source)
            with patch.object(media.shutil, "which", return_value=None):
                result = media.inspect_video(source, Path(directory) / "reports")
            checks = _by_id(result["checks"])
            self.assertEqual(checks["container_faststart"]["status"], "bestanden")
            self.assertEqual(checks["decode"]["status"], "nicht_geprueft")
            self.assertEqual(result["ergebnis"], "pruefung_unvollstaendig")
            self.assertTrue(any("ffmpeg" in step for step in result["manual_steps"]))
            _dummy_mp4(source, faststart=False)
            with patch.object(media.shutil, "which", return_value=None):
                other = media.inspect_video(source, Path(directory) / "reports")
            self.assertEqual(_by_id(other["checks"])["container_faststart"]["status"], "fehlgeschlagen")
            self.assertNotEqual(result["report_dir"], other["report_dir"])

    def test_malformed_atoms_fail_without_out_of_bounds_reads(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "broken.mp4"
            source.write_bytes(struct.pack(">I4s", 999999999, b"moov"))
            with self.assertRaises(ValueError):
                media._read_mp4_atoms(source)

    def test_missing_source_is_a_failed_explicit_report(self):
        with tempfile.TemporaryDirectory() as directory:
            result = media.inspect_video(Path(directory) / "missing.mp4", Path(directory) / "reports")
            self.assertIsNone(result["sha256"])
            self.assertEqual(result["ergebnis"], "nacharbeit_erforderlich")
            self.assertEqual(_by_id(result["checks"])["source_readable"]["status"], "fehlgeschlagen")
            self.assertTrue(Path(result["report_path"]).exists())

    def test_source_mutation_invalidates_measurement_binding(self):
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "DEMO.mp4"
            _dummy_mp4(source)
            calls = 0
            real_hash = media._sha256

            def changing_hash(path):
                nonlocal calls
                if path == source:
                    calls += 1
                    return "before" if calls == 1 else "after"
                return real_hash(path)

            with patch.object(media.shutil, "which", return_value=None), patch.object(media, "_sha256", side_effect=changing_hash):
                result = media.inspect_video(source, Path(directory) / "reports")
            checks = _by_id(result["checks"])
            self.assertEqual(checks["source_stability"]["status"], "fehlgeschlagen")
            self.assertEqual(checks["container_faststart"]["status"], "nicht_geprueft")
            self.assertFalse(result["raw_reports"][0]["source_unchanged"])

    def test_timeout_retains_raw_output_without_claiming_success(self):
        with tempfile.TemporaryDirectory() as directory:
            reports = []
            error = subprocess.TimeoutExpired(["ffprobe"], 180, output=b"partial", stderr=b"timed out")
            with patch.object(media.subprocess, "run", side_effect=error) as run:
                result = media._run_report(["ffprobe", "/tmp/$(touch should-not-execute).mp4"], Path(directory), "timeout", reports)
            self.assertFalse(result["ok"])
            self.assertTrue(result["timed_out"])
            self.assertEqual(Path(reports[0]["path"]).read_text(), "partial")
            self.assertEqual(run.call_args.kwargs["timeout"], media.COMMAND_TIMEOUT_SECONDS)
            self.assertNotIn("shell", run.call_args.kwargs)
            self.assertIsInstance(run.call_args.args[0], list)


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "ffmpeg/ffprobe not installed")
class DemoMediaIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.directory = tempfile.TemporaryDirectory()
        cls.source = Path(cls.directory.name) / "DEMO-wrong-resolution.mp4"
        process = subprocess.run([shutil.which("ffmpeg"), "-hide_banner", "-nostdin", "-v", "error",
            "-f", "lavfi", "-i", "color=c=black:s=32x64:r=30", "-f", "lavfi", "-i", "anullsrc=r=48000:cl=stereo",
            "-t", "0.4", "-c:v", "libx264", "-profile:v", "high", "-level", "4.1", "-pix_fmt", "yuv420p",
            "-g", "6", "-keyint_min", "6", "-bf", "2", "-x264-params", "open-gop=0",
            "-c:a", "aac", "-b:a", "384k", "-movflags", "+faststart", "-metadata", "title=DEMO",
            str(cls.source)], capture_output=True, text=True, timeout=30, check=False)
        if process.returncode:
            cls.directory.cleanup()
            raise unittest.SkipTest("DEMO fixture needs FFmpeg libx264/AAC: " + process.stderr[-500:])
        cls.before = cls.source.read_bytes()
        cls.result = media.inspect_video(cls.source, Path(cls.directory.name) / "reports")

    @classmethod
    def tearDownClass(cls):
        cls.directory.cleanup()

    def test_wrong_resolution_demo_cannot_pass_production_profile(self):
        checks = _by_id(self.result["checks"])
        self.assertEqual(self.result["ergebnis"], "nacharbeit_erforderlich")
        for check_id in ("video_resolution", "duration", "video_frame_count", "audio_loudness"):
            self.assertEqual(checks[check_id]["status"], "fehlgeschlagen")
        for check_id in ("container_faststart", "video_cfr", "video_closed_gop", "decode"):
            self.assertEqual(checks[check_id]["status"], "bestanden")
        self.assertEqual(checks["ending_visual_disclaimer"]["status"], "nicht_geprueft")

    def test_reports_contain_genuine_outputs_and_hashes(self):
        self.assertEqual(self.before, self.source.read_bytes())
        digest = hashlib.sha256(self.before).hexdigest()
        self.assertEqual(self.result["sha256"], digest)
        self.assertGreaterEqual(len(self.result["raw_reports"]), 15)
        for report in self.result["raw_reports"]:
            self.assertEqual(report["sha256"], hashlib.sha256(Path(report["path"]).read_bytes()).hexdigest())
            self.assertEqual(report["source_sha256"], digest)
        streams_report = next(report for report in self.result["raw_reports"] if report["id"] == "ffprobe-streams.stdout")
        probe = json.loads(Path(streams_report["path"]).read_text())
        self.assertEqual(probe["format"]["tags"]["title"], "DEMO")
        self.assertEqual(probe["streams"][0]["width"], 32)
        persisted = json.loads(Path(self.result["report_path"]).read_text())
        self.assertEqual(persisted, self.result)


if __name__ == "__main__":
    unittest.main()
