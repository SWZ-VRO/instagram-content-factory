from backend.services import ffmpeg_runner, qc


def test_unsupported_extension_fails_fast(tmp_path):
    f = tmp_path / "clip.txt"
    f.write_text("not a video")
    result = qc.check_master_integrity(f)
    assert not result.passed
    assert any("extension" in r for r in result.reasons)


def test_empty_file_fails_fast(tmp_path):
    f = tmp_path / "clip.mp4"
    f.touch()
    result = qc.check_master_integrity(f)
    assert not result.passed
    assert any("empty" in r for r in result.reasons)


def test_duration_below_minimum_fails(tmp_path, monkeypatch):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"x")
    monkeypatch.setattr(
        ffmpeg_runner,
        "probe",
        lambda path: ffmpeg_runner.ProbeResult(
            duration_seconds=0.1, width=100, height=100, has_video_stream=True, has_audio_stream=False
        ),
    )
    result = qc.check_master_integrity(f)
    assert not result.passed
    assert any("below minimum" in r for r in result.reasons)


def test_no_video_stream_fails(tmp_path, monkeypatch):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"x")
    monkeypatch.setattr(
        ffmpeg_runner,
        "probe",
        lambda path: ffmpeg_runner.ProbeResult(
            duration_seconds=10, width=0, height=0, has_video_stream=False, has_audio_stream=True
        ),
    )
    result = qc.check_master_integrity(f)
    assert not result.passed
    assert any("no video stream" in r for r in result.reasons)


def test_valid_file_passes(tmp_path, monkeypatch):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"x")
    monkeypatch.setattr(
        ffmpeg_runner,
        "probe",
        lambda path: ffmpeg_runner.ProbeResult(
            duration_seconds=10, width=1920, height=1080, has_video_stream=True, has_audio_stream=True
        ),
    )
    result = qc.check_master_integrity(f)
    assert result.passed
    assert result.probe.width == 1920


def test_unreadable_media_fails_via_ffmpeg_error(tmp_path, monkeypatch):
    f = tmp_path / "clip.mp4"
    f.write_bytes(b"x")

    def boom(path):
        raise ffmpeg_runner.FFmpegError("corrupt")

    monkeypatch.setattr(ffmpeg_runner, "probe", boom)
    result = qc.check_master_integrity(f)
    assert not result.passed
    assert any("unreadable" in r for r in result.reasons)


def test_variant_output_check_rejects_empty_file(tmp_path):
    f = tmp_path / "variant.mp4"
    result = qc.check_variant_output(f)
    assert not result.passed
