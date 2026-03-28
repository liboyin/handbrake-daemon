from pathlib import Path
from unittest.mock import Mock, patch

import pytest

import handbrake_daemon.__main__ as testee


def test_is_gpu_healthy_true(mocker):
    mocker.patch("subprocess.run", return_value=Mock(returncode=0))
    assert testee.is_gpu_healthy() is True


@pytest.mark.parametrize("return_value,side_effect", [
    (Mock(returncode=1), None),
    (None, Exception("nvidia-smi not found")),
])
def test_is_gpu_healthy_false(mocker, return_value, side_effect):
    mocker.patch("subprocess.run", return_value=return_value, side_effect=side_effect)
    assert testee.is_gpu_healthy() is False


def test_wait_until_file_stable_not_exists(tmp_path):
    assert testee.wait_until_file_stable(tmp_path / "missing.mp4") is False


def test_wait_until_file_stable_already_stable(mocker, tmp_path):
    f = mocker.MagicMock(spec=testee.Path)
    f.is_file.return_value = True
    f.stat.return_value = Mock(st_mtime=90, st_size=100)
    mocker.patch("time.time", return_value=100)
    assert testee.wait_until_file_stable(f) is True


def test_wait_until_file_stable_empty(mocker, tmp_path):
    f = mocker.MagicMock(spec=testee.Path)
    f.is_file.return_value = True
    f.stat.return_value = Mock(st_mtime=100, st_size=0)
    mocker.patch("time.time", return_value=100)
    mocker.patch("time.sleep")
    assert testee.wait_until_file_stable(f) is False


def test_wait_until_file_stable_timeout_while_changing(mocker, tmp_path):
    f = mocker.MagicMock(spec=testee.Path)
    f.is_file.return_value = True
    f.stat.side_effect = [Mock(st_mtime=i*10, st_size=(i+1)*100) for i in range(100)]
    # file changes constantly, time passes well beyond timeout
    mocker.patch("time.time", side_effect=[0, 10, 20])
    mocker.patch("time.sleep")
    assert testee.wait_until_file_stable(f, timeout_seconds=10) is False


def test_wait_until_file_stable_stabilizes(mocker, tmp_path):
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


@pytest.mark.parametrize("format,expected", [("AVC", True), ("HEVC", False)])
def test_is_h264_encoded(mocker, tmp_path, format, expected):
    mocker.patch.object(testee, "prepare_input_file", lambda x: x)
    mocker.patch.object(testee.MediaInfo, "parse", return_value=Mock(tracks=[Mock(track_type="Video", format=format)]))
    assert testee.is_h264_encoded(tmp_path / "test.mp4") is expected


def test_is_h264_encoded_no_video_track(mocker, tmp_path):
    mocker.patch.object(testee, "prepare_input_file", lambda x: x)
    mocker.patch.object(testee.MediaInfo, "parse", return_value=Mock(tracks=[]))
    assert testee.is_h264_encoded(tmp_path / "test.mp4") is None


def test_get_output_file_path_for_mp4_file_not_exists(tmp_path):
    input_path = tmp_path / "test.mp4"
    assert testee.get_output_file_path_for_mp4(input_path) is None


def test_get_output_file_path_for_mp4_already_h264(mocker, tmp_path):
    mocker.patch("pathlib.Path.exists", return_value=True)
    mocker.patch.object(testee, "is_h264_encoded", return_value=True)
    assert testee.get_output_file_path_for_mp4(tmp_path / "test.mp4") is None


def test_get_output_file_path_for_mp4_needs_encoding(mocker, tmp_path):
    mocker.patch("pathlib.Path.exists", side_effect=[True, False])
    mocker.patch.object(testee, "is_h264_encoded", return_value=False)
    assert testee.get_output_file_path_for_mp4(tmp_path / "test.mp4") == tmp_path / "test.1.mp4"


def test_get_output_file_path_for_mkv_file_not_exists(tmp_path):
    assert testee.get_output_file_path_for_mkv(tmp_path / "test.mkv") is None


def test_get_output_file_path_for_mkv_mp4_not_exists(mocker, tmp_path):
    mocker.patch("pathlib.Path.exists", side_effect=[True, False])
    assert testee.get_output_file_path_for_mkv(tmp_path / "test.mkv") == tmp_path / "test.mp4"


def test_get_output_file_path_unsupported_format(tmp_path):
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
    mocker.patch.object(testee, "prepare_input_file", lambda x: x)
    mocker.patch.object(testee.MediaInfo, "parse", return_value=Mock(tracks=[Mock(track_type="Video", duration=5000)]))
    assert testee.get_video_duration_milliseconds(tmp_path / "test.mp4") == 5000


def test_get_video_duration_milliseconds_no_video_track(mocker, tmp_path):
    mocker.patch.object(testee, "prepare_input_file", lambda x: x)
    mocker.patch.object(testee.MediaInfo, "parse", return_value=Mock(tracks=[]))
    assert testee.get_video_duration_milliseconds(tmp_path / "test.mp4") is None


def test_transcode_video_file_timeout_multiplier(mocker, tmp_path):
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
    output_file = tmp_path / "out.mp4"
    temp_file = output_file.parent / (output_file.name + ".tmp")
    temp_file.touch()
    mocker.patch("subprocess.run")
    testee.transcode_video_file(tmp_path / "in.mp4", output_file)
    testee.subprocess.run.assert_not_called()


def test_transcode_video_file_timeout_unlinks_temp(mocker, tmp_path):
    input_file = tmp_path / "in.mp4"
    input_file.touch()
    output_file = tmp_path / "out.mp4"
    mocker.patch("subprocess.run", side_effect=testee.subprocess.TimeoutExpired(["HandBrakeCLI"], 10))
    mocker.patch.object(testee, "get_video_duration_milliseconds", return_value=10000)
    with pytest.raises(testee.subprocess.TimeoutExpired):
        testee.transcode_video_file(input_file, output_file)


def test_monitor_and_transcode_gpu_fail(mocker, tmp_path):
    mocker.patch.object(testee, "is_gpu_healthy", return_value=False)
    with pytest.raises(SystemExit) as exc:
        testee.monitor_and_transcode(tmp_path)
    assert exc.value.code == 2


def test_monitor_and_transcode_success_loop(mocker, tmp_path):
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
