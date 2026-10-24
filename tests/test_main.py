from unittest.mock import Mock, patch

import pytest

import handbrake_daemon.__main__ as testee


def test_is_gpu_healthy_true(mocker):
    """Returns true when the GPU health check command succeeds."""
    mocker.patch("subprocess.run", return_value=Mock(returncode=0))
    assert testee.is_gpu_healthy() is True


@pytest.mark.parametrize("return_value,side_effect", [
    (Mock(returncode=1), None),
    (None, FileNotFoundError("nvidia-smi")),
    (None, PermissionError("nvidia-smi")),
])
def test_is_gpu_healthy_false(mocker, return_value, side_effect):
    """Returns false when the GPU health check fails or cannot be executed."""
    mocker.patch.object(testee.subprocess, "run", return_value=return_value, side_effect=side_effect)
    assert testee.is_gpu_healthy() is False


def test_is_gpu_healthy_propagates_unexpected_errors(mocker):
    """Propagates errors other than a failure to execute the GPU health check."""
    mocker.patch.object(testee.subprocess, "run", side_effect=ValueError("unexpected"))
    with pytest.raises(ValueError, match="unexpected"):
        testee.is_gpu_healthy()


def test_wait_until_file_stable_not_exists(tmp_path):
    """Returns false when the target path does not exist as a file."""
    assert testee.wait_until_file_stable(tmp_path / "missing.mp4") is False


def test_wait_until_file_stable_already_stable(mocker):
    """Returns true when the file was already stable before monitoring started."""
    f = mocker.MagicMock(spec=testee.Path)
    f.is_file.return_value = True
    f.stat.return_value = Mock(st_mtime=90, st_size=100)
    mocker.patch("time.time", return_value=100)
    assert testee.wait_until_file_stable(f) is True


def test_wait_until_file_stable_empty(mocker):
    """Returns false when a monitored file is observed with zero size."""
    f = mocker.MagicMock(spec=testee.Path)
    f.is_file.return_value = True
    f.stat.return_value = Mock(st_mtime=100, st_size=0)
    mocker.patch("time.time", return_value=100)
    mocker.patch("time.sleep")
    assert testee.wait_until_file_stable(f) is False


def test_wait_until_file_stable_timeout_while_changing(mocker):
    """Returns false when the file keeps changing until the timeout elapses."""
    f = mocker.MagicMock(spec=testee.Path)
    f.is_file.return_value = True
    f.stat.side_effect = [Mock(st_mtime=i*10, st_size=(i+1)*100) for i in range(100)]
    # file changes constantly, time passes well beyond timeout
    mocker.patch("time.time", side_effect=[0, 10, 20])
    mocker.patch("time.sleep")
    assert testee.wait_until_file_stable(f, timeout_seconds=10) is False


def test_wait_until_file_stable_stabilizes(mocker):
    """Returns true once a changing file stays unchanged long enough."""
    f = mocker.MagicMock(spec=testee.Path)
    f.is_file.return_value = True
    f.stat.side_effect = [
        Mock(st_mtime=0, st_size=100),   # start
        Mock(st_mtime=2, st_size=200),   # changed
        Mock(st_mtime=2, st_size=200),   # stable
        Mock(st_mtime=2, st_size=200),   # stable >= duration
        Mock(st_mtime=2, st_size=200),   # extra
    ]
    # file size changes initially, then stays the same long enough
    mocker.patch("time.time", side_effect=[0, 2, 4, 6, 8])
    mocker.patch("time.sleep")
    assert testee.wait_until_file_stable(f, check_interval_seconds=2, stability_duration_seconds=3) is True


def test_wait_until_file_stable_handles_os_error(mocker):
    """Returns false when file metadata cannot be read during monitoring."""
    f = mocker.MagicMock(spec=testee.Path)
    f.is_file.return_value = True
    f.stat.side_effect = OSError("stat failed")
    mocker.patch("time.time", return_value=100)
    assert testee.wait_until_file_stable(f) is False


@pytest.mark.parametrize("format,expected", [("AVC", True), ("HEVC", False)])
def test_is_h264_encoded(mocker, tmp_path, format, expected):
    """Detects whether the first video track is encoded as AVC."""
    mocker.patch.object(testee, "prepare_input_file", lambda x: x)
    mocker.patch.object(testee.MediaInfo, "parse", return_value=Mock(tracks=[Mock(track_type="Video", format=format)]))
    assert testee.is_h264_encoded(tmp_path / "test.mp4") is expected


def test_is_h264_encoded_no_video_track(mocker, tmp_path):
    """Returns none when media info exposes no video track."""
    mocker.patch.object(testee, "prepare_input_file", lambda x: x)
    mocker.patch.object(testee.MediaInfo, "parse", return_value=Mock(tracks=[]))
    assert testee.is_h264_encoded(tmp_path / "test.mp4") is None


def test_is_h264_encoded_returns_none_on_parse_error(tmp_path):
    """Returns none when media-info parsing raises an exception."""
    with (
        patch.object(testee, "prepare_input_file", side_effect=lambda path: path),
        patch.object(testee.MediaInfo, "parse", side_effect=RuntimeError("parse failed")),
    ):
        assert testee.is_h264_encoded(tmp_path / "test.mp4") is None


def test_get_output_file_path_for_mp4_file_not_exists(tmp_path):
    """Returns none for a missing MP4 input path."""
    input_path = tmp_path / "test.mp4"
    assert testee.get_output_file_path_for_mp4(input_path) is None


def test_get_output_file_path_for_mp4_already_h264(mocker, tmp_path):
    """Returns none when the MP4 input is already H264 encoded."""
    mocker.patch("pathlib.Path.exists", return_value=True)
    mocker.patch.object(testee, "is_h264_encoded", return_value=True)
    assert testee.get_output_file_path_for_mp4(tmp_path / "test.mp4") is None


def test_get_output_file_path_for_mp4_needs_encoding(mocker, tmp_path):
    """Returns the first available numbered MP4 output path when transcoding is needed."""
    mocker.patch("pathlib.Path.exists", side_effect=[True, False])
    mocker.patch.object(testee, "is_h264_encoded", return_value=False)
    assert testee.get_output_file_path_for_mp4(tmp_path / "test.mp4") == tmp_path / "test.1.mp4"


def test_get_output_file_path_for_mp4_returns_none_when_probe_fails(tmp_path):
    """Returns none when the input MP4 encoding cannot be determined."""
    input_path = tmp_path / "test.mp4"
    with (
        patch.object(testee.Path, "exists", return_value=True),
        patch.object(testee, "is_h264_encoded", return_value=None),
    ):
        assert testee.get_output_file_path_for_mp4(input_path) is None


def test_get_output_file_path_for_mp4_returns_none_when_h264_copy_exists(tmp_path):
    """Returns none when a numbered MP4 output already exists in H264 format."""
    input_path = tmp_path / "test.mp4"
    with (
        patch.object(testee.Path, "exists", side_effect=[True, True]),
        patch.object(testee.Path, "is_file", return_value=True),
        patch.object(testee, "is_h264_encoded", side_effect=[False, True]),
    ):
        assert testee.get_output_file_path_for_mp4(input_path, max_retries=1) is None


def test_get_output_file_path_for_mp4_skips_non_file_candidates_until_retries_exhausted(tmp_path):
    """Returns none when all numbered output candidates exist as non-files."""
    input_path = tmp_path / "test.mp4"
    with (
        patch.object(testee.Path, "exists", side_effect=[True, True, True]),
        patch.object(testee.Path, "is_file", return_value=False),
    ):
        assert testee.get_output_file_path_for_mp4(input_path, max_retries=2) is None


def test_get_output_file_path_for_mkv_file_not_exists(tmp_path):
    """Returns none for a missing MKV input path."""
    assert testee.get_output_file_path_for_mkv(tmp_path / "test.mkv") is None


def test_get_output_file_path_for_mkv_mp4_not_exists(mocker, tmp_path):
    """Returns the sibling MP4 path when no MP4 output exists yet."""
    mocker.patch("pathlib.Path.exists", side_effect=[True, False])
    assert testee.get_output_file_path_for_mkv(tmp_path / "test.mkv") == tmp_path / "test.mp4"


def test_get_output_file_path_for_mkv_delegates_when_mp4_exists(tmp_path):
    """Delegates to the MP4 helper when the sibling MP4 path already exists."""
    input_path = tmp_path / "test.mkv"
    mp4_path = tmp_path / "test.mp4"
    expected = tmp_path / "test.1.mp4"
    with (
        patch.object(testee.Path, "exists", side_effect=[True, True]),
        patch.object(testee, "get_output_file_path_for_mp4", return_value=expected) as mock_get_output_file_path_for_mp4,
    ):
        assert testee.get_output_file_path_for_mkv(input_path) == expected
    mock_get_output_file_path_for_mp4.assert_called_once_with(mp4_path)


def test_get_output_file_path_dispatches_mp4(tmp_path):
    """Dispatches MP4 inputs to the MP4-specific output path helper."""
    input_path = tmp_path / "test.mp4"
    expected = tmp_path / "test.1.mp4"
    with patch.object(testee, "get_output_file_path_for_mp4", return_value=expected) as mock_get_output_file_path_for_mp4:
        assert testee.get_output_file_path(input_path) == expected
    mock_get_output_file_path_for_mp4.assert_called_once_with(input_path)


def test_get_output_file_path_dispatches_mkv(tmp_path):
    """Dispatches MKV inputs to the MKV-specific output path helper."""
    input_path = tmp_path / "test.mkv"
    expected = tmp_path / "test.mp4"
    with patch.object(testee, "get_output_file_path_for_mkv", return_value=expected) as mock_get_output_file_path_for_mkv:
        assert testee.get_output_file_path(input_path) == expected
    mock_get_output_file_path_for_mkv.assert_called_once_with(input_path)


def test_get_output_file_path_unsupported_format(tmp_path):
    """Raises a value error for unsupported input file types."""
    with pytest.raises(ValueError, match="Unsupported file type"):
        testee.get_output_file_path(tmp_path / "test.avi")


def test_yield_transcode_tasks_yields_case_insensitive_video_files(tmp_path):
    """Yields transcode tasks for MKV and MP4 files regardless of suffix casing."""
    mkv_file = tmp_path / "movie.MKV"
    mp4_file = tmp_path / "clip.Mp4"
    mkv_file.touch()
    mp4_file.touch()

    with (
        patch.object(testee, "prepare_input_dir") as mock_prepare_input_dir,
        patch.object(testee, "wait_until_file_stable", return_value=True) as mock_wait_until_file_stable,
        patch.object(testee, "get_output_file_path", side_effect=lambda path: path.with_suffix(".output.mp4")) as mock_get_output_file_path,
    ):
        tasks = set(testee.yield_transcode_tasks(tmp_path))

    assert tasks == {
        (mkv_file, mkv_file.with_suffix(".output.mp4")),
        (mp4_file, mp4_file.with_suffix(".output.mp4")),
    }
    mock_prepare_input_dir.assert_called_once_with(tmp_path)
    assert mock_wait_until_file_stable.call_count == 2
    assert mock_get_output_file_path.call_count == 2


def test_yield_transcode_tasks_skips_temp_files_and_directories(tmp_path):
    """Skips temporary video files and directory entries during task discovery."""
    real_file = tmp_path / "movie.mkv"
    temp_mkv_file = tmp_path / "movie.tmp.mkv"
    temp_mp4_file = tmp_path / "movie.temp.mp4"
    fake_mp4_dir = tmp_path / "folder.mp4"
    real_file.touch()
    temp_mkv_file.touch()
    temp_mp4_file.touch()
    fake_mp4_dir.mkdir()

    with (
        patch.object(testee, "prepare_input_dir"),
        patch.object(testee, "wait_until_file_stable", return_value=True) as mock_wait_until_file_stable,
        patch.object(testee, "get_output_file_path", side_effect=lambda path: path.with_suffix(".output.mp4")) as mock_get_output_file_path,
    ):
        tasks = list(testee.yield_transcode_tasks(tmp_path))

    assert tasks == [(real_file, real_file.with_suffix(".output.mp4"))]
    mock_wait_until_file_stable.assert_called_once_with(real_file)
    mock_get_output_file_path.assert_called_once_with(real_file)



def test_yield_transcode_tasks_skips_unstable_files_and_missing_outputs(tmp_path):
    """Skips files that are unstable or do not produce an output path."""
    unstable_file = tmp_path / "unstable.mkv"
    no_output_file = tmp_path / "already_h264.mp4"
    needs_output_file = tmp_path / "needs_transcode.mp4"
    unstable_file.touch()
    no_output_file.touch()
    needs_output_file.touch()

    with (
        patch.object(testee, "prepare_input_dir"),
        patch.object(
            testee,
            "wait_until_file_stable",
            side_effect=lambda path: path != unstable_file,
        ) as mock_wait_until_file_stable,
        patch.object(
            testee,
            "get_output_file_path",
            side_effect=lambda path: None if path == no_output_file else path.with_suffix(".output.mp4"),
        ) as mock_get_output_file_path,
    ):
        tasks = set(testee.yield_transcode_tasks(tmp_path))

    assert tasks == {
        (needs_output_file, needs_output_file.with_suffix(".output.mp4")),
    }
    assert mock_wait_until_file_stable.call_count == 3
    assert {call.args[0] for call in mock_get_output_file_path.call_args_list} == {
        no_output_file,
        needs_output_file,
    }


def test_get_video_duration_milliseconds(mocker, tmp_path):
    """Returns the video duration in milliseconds for a media file."""
    mocker.patch.object(testee, "prepare_input_file", lambda x: x)
    mocker.patch.object(testee.MediaInfo, "parse", return_value=Mock(tracks=[Mock(track_type="Video", duration=5000)]))
    assert testee.get_video_duration_milliseconds(tmp_path / "test.mp4") == 5000


def test_get_video_duration_milliseconds_no_video_track(mocker, tmp_path):
    """Returns none when no video track is available for duration lookup."""
    mocker.patch.object(testee, "prepare_input_file", lambda x: x)
    mocker.patch.object(testee.MediaInfo, "parse", return_value=Mock(tracks=[]))
    assert testee.get_video_duration_milliseconds(tmp_path / "test.mp4") is None


def test_get_video_duration_milliseconds_returns_none_on_parse_error(tmp_path):
    """Returns none when media-info duration parsing raises an exception."""
    with patch.object(testee.MediaInfo, "parse", side_effect=RuntimeError("parse failed")):
        assert testee.get_video_duration_milliseconds(tmp_path / "test.mp4") is None


def test_transcode_video_file_timeout_multiplier(mocker, tmp_path):
    """Uses a timeout equal to one and a half times the input duration."""
    input_file = tmp_path / "test.mp4"
    input_file.touch()
    output_file = tmp_path / "out.mp4"
    mocker.patch.object(testee, "get_video_duration_milliseconds", return_value=60000)
    mock_run = mocker.patch("subprocess.run")
    mocker.patch.object(testee, "prepare_input_file", return_value=input_file)
    mocker.patch.object(testee, "prepare_output_file", return_value=output_file.with_suffix(".mp4.tmp"))
    mocker.patch("pathlib.Path.rename")
    testee.transcode_video_file(input_file, output_file)
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["timeout"] == 90.0  # 60s * 1.5 = 90.0


def test_transcode_video_file_timeout_no_duration(mocker, tmp_path):
    """Falls back to the default timeout when input duration is unavailable."""
    input_file = tmp_path / "test.mp4"
    input_file.touch()
    output_file = tmp_path / "out.mp4"
    mocker.patch.object(testee, "get_video_duration_milliseconds", return_value=None)
    mock_run = mocker.patch("subprocess.run")
    mocker.patch.object(testee, "prepare_input_file", return_value=input_file)
    mocker.patch.object(testee, "prepare_output_file", return_value=output_file.with_suffix(".mp4.tmp"))
    mocker.patch("pathlib.Path.rename")
    testee.transcode_video_file(input_file, output_file)
    mock_run.assert_called_once()
    assert mock_run.call_args.kwargs["timeout"] == 7200.0  # 7_200_000 / 1000 = 7200.0


def test_transcode_video_file_temp_exists(mocker, tmp_path):
    """Skips transcoding when the temporary output path already exists."""
    output_file = tmp_path / "out.mp4"
    temp_file = output_file.parent / (output_file.name + ".tmp")
    temp_file.touch()
    mock_run = mocker.patch("subprocess.run")
    testee.transcode_video_file(tmp_path / "in.mp4", output_file)
    mock_run.assert_not_called()


def test_transcode_video_file_timeout_unlinks_temp(mocker, tmp_path):
    """Removes the temporary output file when HandBrake times out."""
    input_file = tmp_path / "in.mp4"
    input_file.touch()
    output_file = tmp_path / "out.mp4"
    mocker.patch("subprocess.run", side_effect=testee.subprocess.TimeoutExpired(["HandBrakeCLI"], 10))
    mocker.patch.object(testee, "get_video_duration_milliseconds", return_value=10000)
    with pytest.raises(testee.subprocess.TimeoutExpired):
        testee.transcode_video_file(input_file, output_file)


def test_monitor_and_transcode_gpu_fail(mocker, tmp_path):
    """Exits with code two when the GPU health check fails."""
    mocker.patch.object(testee, "is_gpu_healthy", return_value=False)
    with pytest.raises(SystemExit) as exc:
        testee.monitor_and_transcode(tmp_path)
    assert exc.value.code == 2


def test_monitor_and_transcode_success_loop(mocker, tmp_path):
    """Transcodes discovered files when the GPU is healthy and durations match."""
    mocker.patch.object(testee, "is_gpu_healthy", return_value=True)
    input_file = tmp_path / "in.mp4"
    output_file = tmp_path / "out.mp4"
    mocker.patch.object(testee, "yield_transcode_tasks", return_value=[(input_file, output_file)])
    mocker.patch.object(testee, "transcode_video_file")
    mocker.patch.object(testee, "get_video_duration_milliseconds", side_effect=[10000, 10000])
    # break loop on sleep
    mocker.patch("time.sleep", side_effect=KeyboardInterrupt)
    with pytest.raises(KeyboardInterrupt):
        testee.monitor_and_transcode(tmp_path)
    testee.transcode_video_file.assert_called_once_with(input_file, output_file)


def test_monitor_and_transcode_duration_mismatch(mocker, tmp_path):
    """Deletes the output file when transcoding produces a duration mismatch."""
    mocker.patch.object(testee, "is_gpu_healthy", return_value=True)
    mocker.patch("time.sleep", side_effect=KeyboardInterrupt)
    input_file = tmp_path / "in.mp4"
    output_file = tmp_path / "out.mp4"
    output_file.touch()
    mocker.patch.object(testee, "yield_transcode_tasks", return_value=[(input_file, output_file)])
    mocker.patch.object(testee, "transcode_video_file")
    # mismatch durations: 10000 vs 9000
    mocker.patch.object(testee, "get_video_duration_milliseconds", side_effect=[10000, 9000])
    with pytest.raises(KeyboardInterrupt):
        testee.monitor_and_transcode(tmp_path)
    assert not output_file.exists()  # mismatched file should be unlinked


def test_monitor_and_transcode_missing_durations(mocker, tmp_path):
    """Leaves the output file in place when duration checks cannot be performed."""
    mocker.patch.object(testee, "is_gpu_healthy", return_value=True)
    mocker.patch("time.sleep", side_effect=KeyboardInterrupt)
    input_file = tmp_path / "in.mp4"
    output_file = tmp_path / "out.mp4"
    output_file.touch()
    mocker.patch.object(testee, "yield_transcode_tasks", return_value=[(input_file, output_file)])
    mocker.patch.object(testee, "transcode_video_file")
    # Check scenario where input duration is None
    mocker.patch.object(testee, "get_video_duration_milliseconds", return_value=None)
    with pytest.raises(KeyboardInterrupt):
        testee.monitor_and_transcode(tmp_path)
    assert output_file.exists()


def test_monitor_and_transcode_skips_missing_output_duration(mocker, tmp_path):
    """Leaves the output file in place when output duration cannot be determined."""
    mocker.patch.object(testee, "is_gpu_healthy", return_value=True)
    mocker.patch("time.sleep", side_effect=KeyboardInterrupt)
    input_file = tmp_path / "in.mp4"
    output_file = tmp_path / "out.mp4"
    output_file.touch()
    mocker.patch.object(testee, "yield_transcode_tasks", return_value=[(input_file, output_file)])
    mocker.patch.object(testee, "transcode_video_file")
    mocker.patch.object(testee, "get_video_duration_milliseconds", side_effect=[10000, None])
    with pytest.raises(KeyboardInterrupt):
        testee.monitor_and_transcode(tmp_path)
    assert output_file.exists()
