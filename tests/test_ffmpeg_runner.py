"""
backend/services/ffmpeg_runner.py is the one place that shells out to
ffmpeg/ffprobe. These tests mock subprocess.run/shutil.which so the error
handling and JSON parsing are verified without the real binaries installed
(this repo was developed and tested on a machine without FFmpeg -- see
README "Tests"; the Docker image does install it for real use).
"""
import json

import pytest

from backend.services import ffmpeg_runner


def test_probe_raises_not_available_when_binary_missing(monkeypatch, tmp_path):
    monkeypatch.setattr(ffmpeg_runner.shutil, "which", lambda name: None)
    with pytest.raises(ffmpeg_runner.FFmpegNotAvailable):
        ffmpeg_runner.probe(tmp_path / "x.mp4")


def test_run_ffmpeg_raises_on_nonzero_exit(monkeypatch, tmp_path):
    monkeypatch.setattr(ffmpeg_runner.shutil, "which", lambda name: "/usr/bin/ffmpeg")

    class FakeProc:
        returncode = 1
        stderr = "boom"
        stdout = ""

    monkeypatch.setattr(ffmpeg_runner.subprocess, "run", lambda *a, **k: FakeProc())
    with pytest.raises(ffmpeg_runner.FFmpegError):
        ffmpeg_runner.run_ffmpeg(["-i", "in.mp4"], output_path=tmp_path / "out.mp4")


def test_run_ffmpeg_raises_if_output_missing_despite_zero_exit(monkeypatch, tmp_path):
    monkeypatch.setattr(ffmpeg_runner.shutil, "which", lambda name: "/usr/bin/ffmpeg")

    class FakeProc:
        returncode = 0
        stderr = ""
        stdout = ""

    monkeypatch.setattr(ffmpeg_runner.subprocess, "run", lambda *a, **k: FakeProc())
    with pytest.raises(ffmpeg_runner.FFmpegError):
        ffmpeg_runner.run_ffmpeg(["-i", "in.mp4"], output_path=tmp_path / "out.mp4")


def test_run_ffmpeg_succeeds_when_output_written(monkeypatch, tmp_path):
    monkeypatch.setattr(ffmpeg_runner.shutil, "which", lambda name: "/usr/bin/ffmpeg")
    out = tmp_path / "out.mp4"

    class FakeProc:
        returncode = 0
        stderr = ""
        stdout = ""

    def fake_run(cmd, **kwargs):
        out.write_bytes(b"fake video bytes")
        return FakeProc()

    monkeypatch.setattr(ffmpeg_runner.subprocess, "run", fake_run)
    ffmpeg_runner.run_ffmpeg(["-i", "in.mp4"], output_path=out)
    assert out.exists() and out.stat().st_size > 0


def test_probe_parses_streams_and_format(monkeypatch, tmp_path):
    monkeypatch.setattr(ffmpeg_runner.shutil, "which", lambda name: "/usr/bin/ffprobe")
    payload = json.dumps(
        {
            "format": {"duration": "12.5"},
            "streams": [
                {"codec_type": "video", "width": 1280, "height": 720},
                {"codec_type": "audio"},
            ],
        }
    )

    class FakeProc:
        returncode = 0
        stdout = payload
        stderr = ""

    monkeypatch.setattr(ffmpeg_runner.subprocess, "run", lambda *a, **k: FakeProc())
    result = ffmpeg_runner.probe(tmp_path / "in.mp4")
    assert result.duration_seconds == 12.5
    assert (result.width, result.height) == (1280, 720)
    assert result.has_video_stream is True
    assert result.has_audio_stream is True


def test_probe_raises_ffmpeg_error_on_nonzero_exit(monkeypatch, tmp_path):
    monkeypatch.setattr(ffmpeg_runner.shutil, "which", lambda name: "/usr/bin/ffprobe")

    class FakeProc:
        returncode = 1
        stdout = ""
        stderr = "not a media file"

    monkeypatch.setattr(ffmpeg_runner.subprocess, "run", lambda *a, **k: FakeProc())
    with pytest.raises(ffmpeg_runner.FFmpegError):
        ffmpeg_runner.probe(tmp_path / "in.mp4")
