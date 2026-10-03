"""Read-only, evidence-bound checks for the MA-SHORT-58 delivery profile.

The inspector does not render or repair a video. FFmpeg outputs go to its null
muxer; only probe/measurement reports are written. A missing measurement is
``nicht_geprueft`` and can never silently become a successful check.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import shutil
import struct
import subprocess
import uuid
from datetime import datetime, timezone
from fractions import Fraction
from pathlib import Path
from typing import Any


COMMAND_TIMEOUT_SECONDS = 180
PROFILE = "MA-SHORT-58-v1.0"
VIDEO_FRAMES = 1740
VIDEO_SECONDS = 58
FRAME_RATE = Fraction(30)
MAX_VIDEO_BITS_PER_SECOND = 16_000_000

_REQUIREMENTS = {
    "source_readable": "Eine lesbare, unveränderte lokale Videodatei.",
    "source_stability": "Gleicher SHA-256 vor und nach allen Messungen.",
    "container_mp4": "MP4 mit gültigen ftyp-, moov- und mdat-Atomen.",
    "container_faststart": "moov vollständig vor dem ersten mdat (MP4 faststart).",
    "stream_count": "Genau eine Videospur und eine Audiospur.",
    "video_resolution": "1080 × 1920 Pixel, ohne Rotationsmetadaten.",
    "video_sar": "Sample Aspect Ratio 1:1.",
    "duration": "Videospur und Container exakt 58 Sekunden.",
    "video_frame_count": "Genau 1740 tatsächlich gelesene Videoframes.",
    "video_cfr": "Tatsächliche Präsentationszeitstempel: CFR 30 fps ab Sekunde 0.",
    "video_progressive": "Alle Frames progressiv, keine Interlaced-Frames.",
    "video_pixel_format": "8-Bit yuv420p.",
    "video_color": "BT.709-Primärfarben, BT.709-Transfer, BT.709-Matrix; SDR.",
    "video_codec": "AVC/H.264 High, Level 4.1.",
    "video_bitrate_target": "Beleg des Encoder-Ziels 10.000.000 bit/s.",
    "video_peak_bitrate": "Höchstens 16.000.000 bit/s in jedem gleitenden 1-s-Paketfenster.",
    "video_vbv_maxrate": "Beleg des Encoder-/VBV-Limits höchstens 16.000.000 bit/s.",
    "video_gop": "GOP-Länge höchstens 60 Frames, erstes Frame ein Keyframe.",
    "video_closed_gop": "Jede tatsächliche GOP beginnt mit einer AVC-IDR-Picture (geschlossene GOP).",
    "video_b_frames": "Höchstens zwei aufeinanderfolgende B-Frames; mindestens ein Zweierlauf.",
    "decode": "Vollständiges Decodieren von Bild und Ton ohne Fehler.",
    "audio_codec": "AAC-LC.",
    "audio_sample_rate": "48.000 Hz.",
    "audio_channels": "Stereo, genau zwei Kanäle.",
    "audio_bitrate": "Beleg des AAC-Encoder-Ziels 384.000 bit/s.",
    "audio_loudness": "Integrierte Lautheit zwischen −15 und −13 LUFS einschließlich.",
    "audio_true_peak": "True Peak höchstens −1,5 dBTP.",
    "ending_silence": "Durchgehend digitale Stille von 54,000 bis 58,000 s (192.000 Samples/Kanal).",
    "ending_visual_disclaimer": "54–58 s: schwarzer Hintergrund und vollständig lesbarer korrekter Disclaimer.",
    "audio_video_sync": "Echte Bild-/Ton-Synchronität durch vollständiges Ansehen und Anhören.",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _check(check_id: str, status: str, actual: Any = None, reason: str = "") -> dict[str, Any]:
    return {"id": check_id, "status": status, "ist": actual,
            "soll": _REQUIREMENTS[check_id], "grund": reason}


def _result(checks: list[dict[str, Any]]) -> str:
    if any(item["status"] == "fehlgeschlagen" for item in checks):
        return "nacharbeit_erforderlich"
    if any(item["status"] == "nicht_geprueft" for item in checks):
        return "pruefung_unvollstaendig"
    return "freigabefaehig"


def _fraction(value: Any) -> Fraction | None:
    try:
        if value is None or isinstance(value, bool):
            return None
        return Fraction(str(value))
    except (ValueError, ZeroDivisionError, TypeError, OverflowError):
        return None


def _integer(value: Any) -> int | None:
    number = _fraction(value)
    return int(number) if number is not None and number.denominator == 1 else None


def _frame_time(frame: dict[str, Any], time_base: Fraction | None) -> Fraction | None:
    # Only original presentation timestamps prove actual CFR. A decoder's
    # best-effort reconstruction and declared fps are retained in the raw
    # report, but never accepted as evidence for missing PTS.
    ticks = _integer(frame.get("pts"))
    if ticks is not None and time_base is not None:
        return ticks * time_base
    return _fraction(frame.get("pts_time"))


def _read_mp4_atoms(path: Path) -> dict[str, Any]:
    """Read bounded top-level boxes; no extension-based MP4/faststart guess."""
    size = path.stat().st_size
    atoms: list[dict[str, Any]] = []
    brands: list[str] = []
    with path.open("rb") as handle:
        position = 0
        while position < size:
            if len(atoms) >= 10000:
                raise ValueError("Zu viele MP4-Atome; sichere Analyse abgebrochen.")
            handle.seek(position)
            header = handle.read(8)
            if len(header) != 8:
                raise ValueError("Unvollständiger MP4-Atomheader.")
            box_size, raw_type = struct.unpack(">I4s", header)
            header_size = 8
            if box_size == 1:
                extended = handle.read(8)
                if len(extended) != 8:
                    raise ValueError("Unvollständige erweiterte MP4-Atomgröße.")
                box_size = struct.unpack(">Q", extended)[0]
                header_size = 16
            elif box_size == 0:
                box_size = size - position
            if box_size < header_size or position + box_size > size:
                raise ValueError("MP4-Atomgröße liegt außerhalb der Datei.")
            atom_type = raw_type.decode("ascii", errors="replace")
            atoms.append({"typ": atom_type, "offset": position, "size": box_size})
            if atom_type == "ftyp":
                payload_size = box_size - header_size
                if payload_size < 8 or payload_size > 4096 or payload_size % 4:
                    raise ValueError("Ungültiger ftyp-Inhalt.")
                payload = handle.read(payload_size)
                brands = [payload[:4].decode("ascii", errors="replace")]
                brands.extend(payload[i:i + 4].decode("ascii", errors="replace")
                              for i in range(8, len(payload), 4))
            position += box_size
    return {"atoms": atoms, "brands": brands, "size": size}


def _run_report(command: list[str], report_root: Path, report_id: str,
                reports: list[dict[str, Any]], *, json_output: bool = False) -> dict[str, Any]:
    stdout_path = report_root / f"{report_id}.stdout.{'json' if json_output else 'txt'}"
    stderr_path = report_root / f"{report_id}.stderr.txt"
    status = {"returncode": None, "timed_out": False, "error": None}
    stdout = ""
    stderr = ""
    try:
        process = subprocess.run(command, stdin=subprocess.DEVNULL, capture_output=True,
                                 text=True, encoding="utf-8", errors="replace",
                                 timeout=COMMAND_TIMEOUT_SECONDS, check=False)
        stdout, stderr = process.stdout, process.stderr
        status["returncode"] = process.returncode
    except subprocess.TimeoutExpired as error:
        status["timed_out"] = True
        status["error"] = f"Zeitlimit von {COMMAND_TIMEOUT_SECONDS} Sekunden überschritten."
        stdout = error.stdout or ""
        stderr = error.stderr or ""
        if isinstance(stdout, bytes):
            stdout = stdout.decode("utf-8", errors="replace")
        if isinstance(stderr, bytes):
            stderr = stderr.decode("utf-8", errors="replace")
    except OSError as error:
        status["error"] = str(error)
    stdout_path.write_text(stdout, encoding="utf-8")
    stderr_path.write_text(stderr, encoding="utf-8")
    data = None
    if json_output and status["returncode"] == 0 and not status["timed_out"]:
        try:
            data = json.loads(stdout)
            if not isinstance(data, dict):
                raise ValueError("Kein JSON-Objekt im Rohreport.")
        except (ValueError, json.JSONDecodeError) as error:
            status["error"] = f"Ungültiger ffprobe-JSON-Report: {error}"
    for stream_name, output_path in (("stdout", stdout_path), ("stderr", stderr_path)):
        reports.append({"id": f"{report_id}.{stream_name}", "path": str(output_path),
                        "sha256": _sha256(output_path), "command": command,
                        "timeout_seconds": COMMAND_TIMEOUT_SECONDS, **status})
    return {**status, "stdout": stdout, "stderr": stderr, "data": data,
            "ok": status["returncode"] == 0 and not status["timed_out"] and not status["error"]}


def _metadata_checks(probe: dict[str, Any]) -> list[dict[str, Any]]:
    checks = []
    streams = probe.get("streams", [])
    videos = [s for s in streams if s.get("codec_type") == "video"]
    audios = [s for s in streams if s.get("codec_type") == "audio"]
    checks.append(_check("stream_count", "bestanden" if len(videos) == len(audios) == 1
                         else "fehlgeschlagen", {"video": len(videos), "audio": len(audios)}))
    video = videos[0] if videos else {}
    audio = audios[0] if audios else {}

    def compare(check_id: str, actual: Any, expected: Any) -> None:
        status = "nicht_geprueft" if actual is None else (
            "bestanden" if actual == expected else "fehlgeschlagen")
        checks.append(_check(check_id, status, actual,
                             "Angabe fehlt im ffprobe-Rohreport." if actual is None else ""))

    width, height = _integer(video.get("width")), _integer(video.get("height"))
    rotations = [s.get("rotation") for s in video.get("side_data_list", [])
                 if "rotation" in s]
    if "rotate" in video.get("tags", {}):
        rotations.append(video["tags"]["rotate"])
    rotation_ok = all(_fraction(r) is not None and _fraction(r) % 360 == 0 for r in rotations)
    checks.append(_check("video_resolution", "nicht_geprueft" if width is None or height is None
                         else "bestanden" if (width, height) == (1080, 1920) and rotation_ok
                         else "fehlgeschlagen", {"width": width, "height": height,
                                                "rotation": rotations}))
    sar = video.get("sample_aspect_ratio")
    compare("video_sar", sar if sar not in (None, "N/A", "0:1") else None, "1:1")
    compare("video_pixel_format", video.get("pix_fmt"), "yuv420p")
    codec = {"codec": video.get("codec_name"), "profile": video.get("profile"),
             "level": _integer(video.get("level"))}
    checks.append(_check("video_codec", "nicht_geprueft" if None in codec.values()
                         else "bestanden" if codec == {"codec": "h264", "profile": "High", "level": 41}
                         else "fehlgeschlagen", codec))

    colors = {key: video.get(key) for key in ("color_primaries", "color_transfer", "color_space")}
    hdr = [s.get("side_data_type", "") for s in video.get("side_data_list", [])
           if any(name in s.get("side_data_type", "").lower()
                  for name in ("mastering display", "content light", "hdr", "dovi", "dolby"))]
    if hdr or any(value not in (None, "unknown", "unspecified", "bt709") for value in colors.values()):
        color_status = "fehlgeschlagen"
    elif any(value in (None, "unknown", "unspecified") for value in colors.values()):
        color_status = "nicht_geprueft"
    else:
        color_status = "bestanden"
    checks.append(_check("video_color", color_status, {**colors, "hdr_side_data": hdr},
                         "Fehlende Farbangaben sind kein SDR-Nachweis." if color_status == "nicht_geprueft" else ""))
    duration_ticks = _fraction(video.get("duration_ts"))
    time_base = _fraction(video.get("time_base"))
    video_duration = (duration_ticks * time_base if duration_ticks is not None and time_base is not None
                      else _fraction(video.get("duration")))
    container_duration = _fraction(probe.get("format", {}).get("duration"))
    checks.append(_check("duration", "nicht_geprueft" if video_duration is None or container_duration is None
                         else "bestanden" if video_duration == container_duration == VIDEO_SECONDS
                         else "fehlgeschlagen", {"video_s": str(video_duration) if video_duration is not None else None,
                                                 "container_s": str(container_duration) if container_duration is not None else None}))
    audio_codec = {"codec": audio.get("codec_name"), "profile": audio.get("profile")}
    checks.append(_check("audio_codec", "nicht_geprueft" if None in audio_codec.values()
                         else "bestanden" if audio_codec == {"codec": "aac", "profile": "LC"}
                         else "fehlgeschlagen", audio_codec))
    compare("audio_sample_rate", _integer(audio.get("sample_rate")), 48000)
    channels = _integer(audio.get("channels"))
    layout = audio.get("channel_layout")
    checks.append(_check("audio_channels", "nicht_geprueft" if channels is None or layout in (None, "unknown")
                         else "bestanden" if channels == 2 and layout == "stereo" else "fehlgeschlagen",
                         {"channels": channels, "layout": layout}))
    return checks


def _frame_checks(frames: list[dict[str, Any]], video: dict[str, Any]) -> list[dict[str, Any]]:
    checks = [_check("video_frame_count", "bestanden" if len(frames) == VIDEO_FRAMES
                     else "fehlgeschlagen", len(frames))]
    # AVC permits parameter changes within a stream. The first stream header
    # alone cannot prove that every decoded frame has the required dimensions,
    # sample aspect ratio, and pixel format.
    for check_id, fields, expected in (
        ("video_resolution", ("width", "height"), (1080, 1920)),
        ("video_sar", ("sample_aspect_ratio",), ("1:1",)),
        ("video_pixel_format", ("pix_fmt",), ("yuv420p",)),
    ):
        measurements = [tuple(frame.get(field) for field in fields) for frame in frames]
        unknown = sum(any(value is None or value in ("N/A", "unknown", "0:1") for value in values)
                      for values in measurements)
        mismatches = [index for index, values in enumerate(measurements)
                      if not any(value is None or value in ("N/A", "unknown", "0:1") for value in values)
                      and values != expected]
        status = "fehlgeschlagen" if mismatches else "nicht_geprueft" if not frames or unknown else "bestanden"
        checks.append(_check(check_id, status,
                             {"decoded_frames": len(frames), "unknown_frames": unknown,
                              "mismatched_frames": len(mismatches), "first_mismatch_indices": mismatches[:20],
                              "observed_values": [list(values) for values in dict.fromkeys(measurements)]},
                             "Eigenschaften jedes tatsächlich decodierten Frames geprüft."))
    time_base = _fraction(video.get("time_base"))
    timestamps = [_frame_time(frame, time_base) for frame in frames]
    tolerance = (time_base / 2 if time_base is not None and time_base > 0 else Fraction(0)) + Fraction(1, 1_000_000)
    if not timestamps or any(value is None for value in timestamps):
        checks.append(_check("video_cfr", "nicht_geprueft", None,
                             "Mindestens ein tatsächlicher Frame-PTS fehlt; Metadaten-fps genügen nicht."))
    else:
        deviations = [abs(timestamp - Fraction(index, 30)) for index, timestamp in enumerate(timestamps)]
        monotonic = all(a < b for a, b in zip(timestamps, timestamps[1:]))
        checks.append(_check("video_cfr", "bestanden" if monotonic and max(deviations) <= tolerance
                             else "fehlgeschlagen", {"frames": len(frames), "first_pts_s": float(timestamps[0]),
                                                      "last_pts_s": float(timestamps[-1]), "strictly_increasing": monotonic,
                                                      "max_deviation_s": float(max(deviations)),
                                                      "quantization_tolerance_s": float(tolerance)},
                             "Vergleich jedes PTS mit Frameindex/30; Toleranz: halber Timebase-Tick + 1 µs."))
    interlaced = [_integer(frame.get("interlaced_frame")) for frame in frames]
    checks.append(_check("video_progressive", "fehlgeschlagen" if any(value == 1 for value in interlaced)
                         or video.get("field_order") in ("tt", "bb", "tb", "bt")
                         else "nicht_geprueft" if not interlaced or any(value is None for value in interlaced)
                         else "bestanden", {"interlaced_frames": sum(value == 1 for value in interlaced),
                                            "unknown_frames": sum(value is None for value in interlaced),
                                            "declared_field_order": video.get("field_order")}))
    key_indices = [index for index, frame in enumerate(frames) if _integer(frame.get("key_frame")) == 1]
    known_keys = all(_integer(frame.get("key_frame")) in (0, 1) for frame in frames)
    if not frames or not known_keys:
        checks.append(_check("video_gop", "nicht_geprueft", None, "Keyframe-Informationen fehlen."))
    else:
        lengths = [b - a for a, b in zip(key_indices, key_indices[1:])]
        if key_indices:
            lengths.append(len(frames) - key_indices[-1])
        maximum = max(lengths) if lengths else len(frames)
        checks.append(_check("video_gop", "bestanden" if key_indices and key_indices[0] == 0 and maximum <= 60
                             else "fehlgeschlagen", {"keyframes": len(key_indices), "max_gop_frames": maximum,
                                                      "first_frame_keyframe": bool(key_indices and key_indices[0] == 0)}))
    run = maximum = 0
    known_types = bool(frames) and all(frame.get("pict_type") in ("I", "P", "B") for frame in frames)
    for frame in frames:
        run = run + 1 if frame.get("pict_type") == "B" else 0
        maximum = max(maximum, run)
    checks.append(_check("video_b_frames", "nicht_geprueft" if not known_types
                         else "bestanden" if maximum == 2 else "fehlgeschlagen",
                         {"max_consecutive_b_frames": maximum,
                          "declared_decoder_reorder_depth": video.get("has_b_frames")},
                         "has_b_frames allein belegt keine B-Frame-Konfiguration; tatsächliche Bildfolge geprüft."))
    hdr_frames = [index for index, frame in enumerate(frames)
                  if any(any(name in side.get("side_data_type", "").lower()
                             for name in ("mastering display", "content light", "hdr", "dovi", "dolby"))
                         for side in frame.get("side_data_list", []))]
    if hdr_frames:
        # The caller replaces the stream color check with this stronger failure.
        checks.append(_check("video_color", "fehlgeschlagen", {"hdr_frames": hdr_frames[:20]},
                             "HDR-Side-Data in tatsächlich gelesenen Videoframes."))
    return checks


def _closed_gop_check(raw_headers: str, frames: list[dict[str, Any]],
                      video: dict[str, Any]) -> dict[str, Any]:
    if video.get("codec_name") != "h264":
        return _check("video_closed_gop", "fehlgeschlagen", video.get("codec_name"), "Kein AVC-Bitstream.")
    packets = []
    current = None
    for line in raw_headers.splitlines():
        if "[trace_headers" not in line:
            continue
        if "Packet:" in line:
            if current is not None:
                packets.append(current)
            pts = re.search(r"\bpts (-?\d+)(?:,|\.)", line)
            current = {"pts": int(pts.group(1)) if pts else None, "nal_types": [],
                       "key": "key frame" in line}
        elif current is not None:
            match = re.search(r"\bnal_unit_type\s+[01]+\s*=\s*(\d+)\s*$", line)
            if match:
                current["nal_types"].append(int(match.group(1)))
    if current is not None:
        packets.append(current)
    actual = {"packets": len(packets), "key_packets": sum(packet["key"] for packet in packets),
              "idr_packets": sum(5 in packet["nal_types"] for packet in packets)}
    frame_pts = [_integer(frame.get("pts")) for frame in frames]
    if (not frames or len(packets) != len(frames) or any(value is None for value in frame_pts)
            or any(_integer(frame.get("key_frame")) not in (0, 1) for frame in frames)
            or any(packet["pts"] is None or not ({1, 5} & set(packet["nal_types"])) for packet in packets)
            or sorted(frame_pts) != sorted(packet["pts"] for packet in packets)):
        return _check("video_closed_gop", "nicht_geprueft", actual,
                      "AVC-Header lassen sich nicht lückenlos den tatsächlichen Frames zuordnen; Exportbeleg/Bitstreamprüfung nötig.")
    key_pts = {pts for pts, frame in zip(frame_pts, frames) if _integer(frame.get("key_frame")) == 1}
    idr_pts = {packet["pts"] for packet in packets if 5 in packet["nal_types"]}
    passed = bool(key_pts) and key_pts == idr_pts and frame_pts[0] in idr_pts
    return _check("video_closed_gop", "bestanden" if passed else "fehlgeschlagen", actual,
                  "Jede Frame-Keyframe-Position mit NAL-Typ 5 (IDR) abgeglichen; keine Annahme aus GOP-Länge.")


def _avc_parameter_checks(raw_headers: str) -> list[dict[str, Any]]:
    """Reject contradictory in-band SPS, beyond the first stream descriptor."""
    values = {}
    for name in ("profile_idc", "level_idc", "bit_depth_luma_minus8", "bit_depth_chroma_minus8"):
        values[name] = [int(match) for match in re.findall(
            rf"\b{re.escape(name)}\s+[01]+\s*=\s*(\d+)\s*$", raw_headers, re.MULTILINE)]
    checks = []
    if (values["profile_idc"] and any(value != 100 for value in values["profile_idc"])) or (
            values["level_idc"] and any(value != 41 for value in values["level_idc"])):
        checks.append(_check("video_codec", "fehlgeschlagen", values,
                             "Mindestens ein tatsächliches AVC-SPS widerspricht High Level 4.1."))
    if any(value != 0 for name in ("bit_depth_luma_minus8", "bit_depth_chroma_minus8") for value in values[name]):
        checks.append(_check("video_pixel_format", "fehlgeschlagen", values,
                             "Mindestens ein tatsächliches AVC-SPS signalisiert mehr als 8 Bit."))
    return checks


def _packet_rates(packets: list[dict[str, Any]], stream: dict[str, Any]) -> dict[str, Any] | None:
    stream_index = _integer(stream.get("index"))
    if stream_index is None:
        return None
    selected = [packet for packet in packets if _integer(packet.get("stream_index")) == stream_index]
    samples = []
    for packet in selected:
        timestamp = _fraction(packet.get("dts_time"))
        if timestamp is None:
            timestamp = _fraction(packet.get("pts_time"))
        packet_size = _integer(packet.get("size"))
        duration = _fraction(packet.get("duration_time"))
        if timestamp is None or packet_size is None or packet_size < 0 or duration is None or duration <= 0:
            return None
        samples.append((timestamp, packet_size * 8, duration))
    if not samples:
        return None
    samples.sort()
    start = samples[0][0]
    end = max(t + duration for t, _, duration in samples)
    span = end - start
    if span <= 0:
        return None
    # Maximum over *all* packet-boundary sliding windows, rather than disjoint
    # integer-second bins. The end of the window is exclusive.
    left = 0
    bits = maximum = 0
    for right, (timestamp, packet_bits, _) in enumerate(samples):
        bits += packet_bits
        while timestamp - samples[left][0] >= 1:
            bits -= samples[left][1]
            left += 1
        maximum = max(maximum, bits)
    return {"packets": len(samples), "span_s": float(span),
            "mean_bits_per_second": float(Fraction(sum(s[1] for s in samples)) / span),
            "max_rolling_1s_bits_per_second": maximum, "window_seconds": 1,
            "window_time_source": "packet DTS, otherwise packet PTS",
            "includes_container_overhead": False}


def _loudness_checks(raw: str) -> list[dict[str, Any]]:
    measurements = re.findall(r"lavfi\.r128\.I=(-?(?:\d+(?:\.\d+)?|inf))", raw)
    loudness = float(measurements[-1]) if measurements else None
    if loudness is None:
        summary = re.findall(r"\bI:\s+(-?(?:\d+(?:\.\d+)?|inf))\s+LUFS", raw)
        loudness = float(summary[-1]) if summary else None
    actual_i = loudness if loudness is not None and math.isfinite(loudness) else (
        "-inf" if loudness == -math.inf else None)
    checks = [_check("audio_loudness", "nicht_geprueft" if loudness is None
                     else "bestanden" if -15 <= loudness <= -13 else "fehlgeschlagen",
                     {"integrated_lufs": actual_i, "standard": "FFmpeg ebur128 / ITU-R BS.1770"})]
    peaks = re.findall(r"\bPeak:\s+(-?(?:\d+(?:\.\d+)?|inf))\s+dBFS", raw)
    peak = float(peaks[-1]) if peaks else None
    if peak is None:
        status = "nicht_geprueft"
    elif peak == -1.5:
        status = "nicht_geprueft"
    else:
        status = "bestanden" if peak < -1.5 else "fehlgeschlagen"
    checks.append(_check("audio_true_peak", status,
                         {"true_peak_dbtp": peak if peak is not None and math.isfinite(peak) else (
                             "-inf" if peak == -math.inf else None), "summary_precision_db": 0.1},
                         "Grenzwert −1,5 gerundet auf 0,1 dB: genaueres True-Peak-Meter nötig."
                         if peak == -1.5 else "Oversampled True-Peak-Messung mit ebur128=peak=true."))
    return checks


def _silence_check(raw: str) -> dict[str, Any]:
    overall = raw.rsplit("Overall", 1)[-1] if "Overall" in raw else ""
    sample_match = re.search(r"Number of samples:\s*(\d+(?:\.\d+)?)", overall)
    peak_match = re.search(r"Peak level dB:\s*(-?(?:\d+(?:\.\d+)?|inf))", overall)
    samples = _integer(sample_match.group(1)) if sample_match else None
    peak = float(peak_match.group(1)) if peak_match else None
    actual = {"range_s": [54, 58], "samples_per_channel": samples,
              "peak_dbfs": peak if peak is not None and math.isfinite(peak) else (
                  "-inf" if peak == -math.inf else None)}
    if samples != 192000 or peak is None:
        return _check("ending_silence", "nicht_geprueft", actual,
                      "Kein vollständiger Messnachweis für alle vier Schlusssekunden bei 48 kHz.")
    return _check("ending_silence", "bestanden" if peak == -math.inf else "fehlgeschlagen", actual,
                  "Null Samples sind digitale Stille; leiser Restton wird nicht als Stille umgedeutet.")


def inspect_video(path: str | Path, report_dir: str | Path) -> dict[str, Any]:
    """Inspect a local file, persist original tool outputs, and return a QA report.

    ``sha256`` binds every measurement to the bytes inspected. Report filenames
    are isolated per invocation. Missing tools, unsupported header tracing,
    timeouts, and human checks remain explicit incomplete mandatory checks.
    Encoder target settings cannot be recovered from an average bitrate.
    """
    source = Path(path).expanduser().resolve()
    reports_root = Path(report_dir).expanduser().resolve()
    reports_root.mkdir(parents=True, exist_ok=True)
    report_root = reports_root / f"inspection-{uuid.uuid4().hex}"
    report_root.mkdir()
    checks: dict[str, dict[str, Any]] = {
        check_id: _check(check_id, "nicht_geprueft", None, "Messung noch nicht verfügbar.")
        for check_id in _REQUIREMENTS}
    reports: list[dict[str, Any]] = []
    manual_steps = []
    digest = None
    digest_after = None

    def use(items: list[dict[str, Any]]) -> None:
        for item in items:
            if checks[item["id"]]["status"] == "fehlgeschlagen" and item["status"] != "fehlgeschlagen":
                continue
            checks[item["id"]] = item

    try:
        if not source.is_file():
            raise OSError("Pfad ist keine reguläre lesbare Datei.")
        digest = _sha256(source)
        checks["source_readable"] = _check("source_readable", "bestanden",
                                           {"path": str(source), "size_bytes": source.stat().st_size,
                                            "sha256": digest})
    except OSError as error:
        checks["source_readable"] = _check("source_readable", "fehlgeschlagen", str(source), str(error))

    if digest:
        try:
            atoms = _read_mp4_atoms(source)
            atom_path = report_root / "mp4-atoms.json"
            atom_path.write_text(json.dumps(atoms, ensure_ascii=False, indent=2), encoding="utf-8")
            reports.append({"id": "mp4_atoms", "path": str(atom_path), "sha256": _sha256(atom_path),
                            "command": None, "parser": "bounded_top_level_mp4_boxes"})
            atom_types = [atom["typ"] for atom in atoms["atoms"]]
            mp4_brands = {"isom", "iso2", "iso3", "iso4", "iso5", "iso6", "mp41", "mp42", "avc1", "M4V "}
            is_mp4 = (atom_types.count("ftyp") == atom_types.count("moov") == 1
                      and "mdat" in atom_types and bool(mp4_brands & set(atoms["brands"])))
            checks["container_mp4"] = _check("container_mp4", "bestanden" if is_mp4 else "fehlgeschlagen",
                                             {"atom_types": atom_types, "brands": atoms["brands"]})
            faststart = is_mp4 and atom_types.index("moov") < atom_types.index("mdat")
            checks["container_faststart"] = _check("container_faststart", "bestanden" if faststart else "fehlgeschlagen",
                                                   {"moov_before_mdat": faststart})
        except (OSError, ValueError, struct.error) as error:
            use([_check("container_mp4", "fehlgeschlagen", None, str(error)),
                 _check("container_faststart", "nicht_geprueft", None, "MP4-Struktur nicht lesbar.")])

        ffprobe = shutil.which("ffprobe")
        ffmpeg = shutil.which("ffmpeg")
        if not ffprobe:
            manual_steps.append("ffprobe installieren; dieselbe Datei (SHA-256 unverändert) erneut mit ma technisch prüfen.")
        if not ffmpeg:
            manual_steps.append("ffmpeg mit AVC trace_headers und ebur128-True-Peak-Unterstützung installieren; erneut prüfen.")
        video: dict[str, Any] = {}
        audio: dict[str, Any] = {}
        frames: list[dict[str, Any]] = []
        metadata_ok = False
        if ffprobe:
            metadata = _run_report([ffprobe, "-v", "error", "-show_streams", "-show_format", "-of", "json", str(source)],
                                   report_root, "ffprobe-streams", reports, json_output=True)
            if metadata["ok"]:
                probe = metadata["data"]
                use(_metadata_checks(probe))
                video = next((s for s in probe.get("streams", []) if s.get("codec_type") == "video"), {})
                audio = next((s for s in probe.get("streams", []) if s.get("codec_type") == "audio"), {})
                metadata_ok = True
            else:
                manual_steps.append("ffprobe-Rohreport lesen und Ursache beheben: " + (metadata["error"] or "ffprobe hat die Datei abgewiesen."))
            if video:
                frame_report = _run_report([ffprobe, "-v", "error", "-select_streams", "v:0", "-show_frames",
                    "-show_entries", "frame=pts,pts_time,best_effort_timestamp,best_effort_timestamp_time,key_frame,pict_type,interlaced_frame,width,height,sample_aspect_ratio,pix_fmt,side_data_list",
                    "-of", "json", str(source)], report_root, "ffprobe-frames", reports, json_output=True)
                if frame_report["ok"] and isinstance(frame_report["data"].get("frames"), list):
                    frames = frame_report["data"]["frames"]
                    use(_frame_checks(frames, video))
                else:
                    manual_steps.append("Frame-PTS und Bildstruktur konnten nicht vollständig gelesen werden; ffprobe-frames-Rohreport prüfen.")
            if video or audio:
                packet_report = _run_report([ffprobe, "-v", "error", "-show_packets", "-show_entries",
                    "packet=stream_index,size,pts_time,dts_time,duration_time", "-of", "json", str(source)],
                    report_root, "ffprobe-packets", reports, json_output=True)
                if packet_report["ok"] and isinstance(packet_report["data"].get("packets"), list):
                    packets = packet_report["data"]["packets"]
                    video_rate = _packet_rates(packets, video)
                    audio_rate = _packet_rates(packets, audio)
                    checks["video_bitrate_target"] = _check("video_bitrate_target", "nicht_geprueft", video_rate,
                        "Reale Paketmittelrate berichtet; Encoder-Zielrate ist daraus nicht beweisbar. Exportprofil mit Datei-SHA-256 belegen.")
                    checks["audio_bitrate"] = _check("audio_bitrate", "nicht_geprueft", audio_rate,
                        "Reale AAC-Paketmittelrate berichtet; Encoder-Ziel 384 kbit/s braucht einen Exportprofil-Nachweis.")
                    if video_rate:
                        peak_status = ("bestanden" if video_rate["max_rolling_1s_bits_per_second"] <= MAX_VIDEO_BITS_PER_SECOND
                                       else "fehlgeschlagen")
                        checks["video_peak_bitrate"] = _check("video_peak_bitrate", peak_status, video_rate,
                            "Maximaler Inhalt aller gleitenden 1-s-DTS-Paketfenster; kein Nachweis der Encoder-VBV-Konfiguration.")
        if ffmpeg and metadata_ok:
            if video or audio:
                decode = _run_report([ffmpeg, "-nostdin", "-hide_banner", "-v", "error", "-xerror", "-i", str(source),
                    "-map", "0:v:0?", "-map", "0:a:0?", "-f", "null", "-"], report_root, "ffmpeg-decode", reports)
                checks["decode"] = _check("decode", "bestanden" if decode["ok"] else (
                    "nicht_geprueft" if decode["timed_out"] or decode["error"] else "fehlgeschlagen"),
                    {"returncode": decode["returncode"], "timed_out": decode["timed_out"]},
                    decode["error"] or ("Siehe vollständigen ffmpeg-decode-Rohreport." if not decode["ok"] else ""))
            if video:
                headers = _run_report([ffmpeg, "-nostdin", "-hide_banner", "-v", "info", "-i", str(source),
                    "-map", "0:v:0", "-c:v", "copy", "-bsf:v", "trace_headers", "-f", "null", "-"],
                    report_root, "ffmpeg-avc-headers", reports)
                if headers["ok"]:
                    checks["video_closed_gop"] = _closed_gop_check(headers["stderr"], frames, video)
                    use(_avc_parameter_checks(headers["stderr"]))
                else:
                    checks["video_closed_gop"] = _check("video_closed_gop", "nicht_geprueft", None,
                        "trace_headers nicht verfügbar oder nicht vollständig ausgeführt; Bitstream-/Exportnachweis erforderlich.")
            if audio:
                loudness = _run_report([ffmpeg, "-nostdin", "-hide_banner", "-v", "info", "-i", str(source),
                    "-map", "0:a:0", "-vn", "-af",
                    "ebur128=metadata=1:peak=true,ametadata=mode=print:key=lavfi.r128.I", "-f", "null", "-"],
                    report_root, "ffmpeg-loudness", reports)
                if loudness["ok"]:
                    use(_loudness_checks(loudness["stderr"]))
                else:
                    manual_steps.append("Lautheit und True Peak mit einem EBU-R128-/BS.1770-Meter an derselben finalen Datei messen; Rohreport und Datei-SHA-256 aufbewahren.")
                silence = _run_report([ffmpeg, "-nostdin", "-hide_banner", "-v", "info", "-i", str(source),
                    "-map", "0:a:0", "-vn", "-af", "atrim=start=54:end=58,asetpts=PTS-STARTPTS,astats=metadata=0:reset=0",
                    "-f", "null", "-"], report_root, "ffmpeg-ending-silence", reports)
                if silence["ok"]:
                    checks["ending_silence"] = _silence_check(silence["stderr"])
        try:
            digest_after = _sha256(source)
            checks["source_stability"] = _check("source_stability", "bestanden" if digest_after == digest else "fehlgeschlagen",
                                                 {"sha256_before": digest, "sha256_after": digest_after})
        except OSError as error:
            checks["source_stability"] = _check("source_stability", "fehlgeschlagen", None, str(error))
        if digest_after != digest:
            for check_id in checks:
                if check_id not in ("source_readable", "source_stability"):
                    checks[check_id] = _check(check_id, "nicht_geprueft", None,
                                             "Datei während der Prüfung verändert; sämtliche Messungen ungültig. Erneut prüfen.")

    checks["video_vbv_maxrate"]["grund"] = "Gemessene 1-s-Spitzenrate beweist kein VBV-Limit. Exportprofil/Encoderprotokoll mit Datei-SHA-256 vorlegen."
    checks["ending_visual_disclaimer"] = _check("ending_visual_disclaimer", "nicht_geprueft", None,
        "Mensch muss 54–58 s in Originalauflösung ansehen: schwarzer Hintergrund, richtiger Text, Lesbarkeit und volle vier Sekunden.")
    checks["audio_video_sync"] = _check("audio_video_sync", "nicht_geprueft", None,
        "Vollständige finale Datei mit Ton ansehen; Synchronität wird nicht aus fps oder Dauer abgeleitet.")
    manual_steps.extend([
        "Exportprotokoll für Video-Zielrate 10 Mbit/s, Maxrate 16 Mbit/s und AAC-Zielrate 384 kbit/s mit exakt dieser Datei-SHA-256 dokumentieren.",
        "Die finale Datei vollständig mit Ton ansehen; Bild-/Ton-Synchronität und 54–58 s schwarzen, lesbaren Disclaimer konkret bestätigen.",
    ])
    for report in reports:
        report["source_sha256"] = digest
        report["source_unchanged"] = digest is not None and digest == digest_after
    ordered = list(checks.values())
    result = {"ergebnis": _result(ordered), "checks": ordered, "sha256": digest,
              "sha256_after": digest_after, "path": str(source), "profil": PROFILE,
              "inspected_at": datetime.now(timezone.utc).isoformat(), "raw_reports": reports,
              "manual_steps": manual_steps, "report_dir": str(report_root),
              "report_path": str(report_root / "inspection.json"), "rendered_or_modified": False}
    Path(result["report_path"]).write_text(json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    return result
