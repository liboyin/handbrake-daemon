from unittest.mock import Mock

import pytest

import handbrake_daemon.__main__ as testee


@pytest.mark.parametrize("format,expected", [("AVC", True), ("HEVC", False)])
def test_is_h264_encoded(mocker, tmp_path, format, expected):
    mocker.patch.object(testee, "prepare_input_file", lambda x: x)
    mocker.patch.object(testee.MediaInfo, "parse", return_value=Mock(tracks=[Mock(track_type="Video", format=format)]))
    assert testee.is_h264_encoded(tmp_path / "test.mp4", file_stable_flag=True) is expected


def test_is_h264_encoded_no_video_track(mocker, tmp_path):
    mocker.patch.object(testee, "prepare_input_file", lambda x: x)
    mocker.patch.object(testee.MediaInfo, "parse", return_value=Mock(tracks=[]))
    assert testee.is_h264_encoded(tmp_path / "test.mp4", file_stable_flag=True) is None


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


def test_yield_transcode_tasks(mocker, tmp_path):
    mkv_file = tmp_path / "test.mkv"
    mp4_file = tmp_path / "test.mp4"
    mkv_file.touch()
    mp4_file.touch()
    mocker.patch.object(testee, "get_output_file_path", lambda x: x.with_suffix(".output.mp4"))
    tasks = list(testee.yield_transcode_tasks(tmp_path))
    assert len(tasks) == 2
    assert all(isinstance(task, tuple) and len(task) == 2 for task in tasks)
    assert all(task[1].suffix == ".mp4" for task in tasks)


def test_get_video_duration(mocker, tmp_path):
    mocker.patch.object(testee, "prepare_input_file", lambda x: x)
    mocker.patch.object(testee.MediaInfo, "parse", return_value=Mock(tracks=[Mock(track_type="Video", duration=5000)]))
    assert testee.get_video_duration_milliseconds(tmp_path / "test.mp4") == 5000


def test_get_video_duration_no_video_track(mocker, tmp_path):
    mocker.patch.object(testee, "prepare_input_file", lambda x: x)
    mocker.patch.object(testee.MediaInfo, "parse", return_value=Mock(tracks=[]))
    assert testee.get_video_duration_milliseconds(tmp_path / "test.mp4") is None
