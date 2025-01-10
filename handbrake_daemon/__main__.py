from itertools import chain
from pathlib import Path
import subprocess
import time
from typing import Iterator, Tuple

from pathlib_extensions import prepare_input_dir, prepare_input_file, prepare_output_file
from pymediainfo import MediaInfo

PROJECT_ROOT = Path(__file__).parents[1]
HANDBRAKE_CONFIG = PROJECT_ROOT / "H264 NVENC CQ27.json"


def wait_until_file_stable(file_path: Path, check_interval_seconds: float = 1, stability_duration_seconds: float = 5, timeout_seconds: float = 60) -> bool:
    """
    Block until a file is no longer being changed by monitoring size and modification time.

    Args:
        file_path (Path): Path to the file to be checked.
        check_interval_seconds (float, optional): Time between checks in seconds (default 1 second).
        stability_duration_seconds (float, optional): How long the file must be unchanged before considering it stable (default 5 seconds).
        timeout_seconds (float, optional): Maximum time to wait for the file to stabilize (default 60 seconds).

    Returns:
        bool: True if the file has stabilized, False if the file is inaccessible.
    """
    if not file_path.is_file():
        return False
    try:
        stable_since = None
        last_size = None
        last_mtime = None
        start_time = time.time()
        while True:
            if time.time() - start_time >= timeout_seconds:
                print(f"Timeout waiting for file to stabilize: {file_path}")
                return False
            current_stat = file_path.stat()
            current_size = current_stat.st_size
            current_mtime = current_stat.st_mtime
            if last_size == current_size and last_mtime == current_mtime:
                if stable_since is None:
                    stable_since = time.time()
                elif time.time() - stable_since >= stability_duration_seconds:
                    print(f"File has stabilized: {file_path}")
                    return True
            else:
                stable_since = None
            last_size = current_size
            last_mtime = current_mtime
            time.sleep(check_interval_seconds)
    except (OSError, FileNotFoundError) as e:
        print(f"Ignoring file {file_path} due to error: {e}")
        return False


def is_h264_encoded(file_path: Path) -> bool:
    """
    Check if a video file is encoded in H264/AVC format.

    Args:
        file_path (Path): Path to the video file.

    Returns:
        bool: True if the video is H264/AVC encoded, False otherwise.

    Raises:
        ValueError: If no video track is found in the file.
    """
    for track in MediaInfo.parse(prepare_input_file(file_path)).tracks:
        if track.track_type == "Video":
            return track.format == "AVC"
    raise ValueError(f"No video track found in {file_path}")


def get_output_file_path_for_mp4(input_file_path: Path, max_retries: int = 5) -> Path | None:
    """
    Generate HandBrake output file path for MP4 files.

    Args:
        input_file_path (Path): Path to the input MP4 file.
        max_retries (int, optional): Maximum number of retries to find a unique filename. Defaults to 5.

    Returns:
        Path | None: Path for the output file, or None if no transcoding is needed.
    """
    if not input_file_path.exists():
        print("Skipping missing input file", input_file_path)
        return None
    if is_h264_encoded(input_file_path):
        print("MP4 file is already encoded in H264:", input_file_path)
        return None
    counter = 1
    while counter <= max_retries:
        new_path = input_file_path.with_suffix(f".{counter}.mp4")
        if not new_path.exists():
            return new_path
        # if new_path exists but is not a file, move on to the next candidate filename
        elif new_path.is_file() and is_h264_encoded(new_path):
            print(f"A subsequent file encoded in H264 already exists: {input_file_path} -> {new_path}")
            return None
        counter += 1
    return None


def get_output_file_path_for_mkv(input_file_path: Path) -> Path | None:
    """
    Generate HandBrake output file path for MKV files.

    Args:
        input_file_path (Path): Path to the input MKV file.

    Returns:
        Path | None: Path for the output MP4 file, or None if no transcoding is needed.
    """
    if not input_file_path.exists():
        print("Skipping missing input file", input_file_path)
        return None
    mp4_file_path = input_file_path.with_suffix(".mp4")
    if not mp4_file_path.exists():
        return mp4_file_path
    return get_output_file_path_for_mp4(mp4_file_path)


def get_output_file_path(input_file_path: Path) -> Path | None:
    """
    Generate HandBrake output file path for MKV and MP4 files.

    Args:
        input_file_path (Path): Path to the input video file.

    Returns:
        Path | None: Path for the output file, or None if no transcoding is needed.

    Raises:
        ValueError: If the input file type is not supported (.mp4 or .mkv).
    """
    match input_file_path.suffix.lower():
        case ".mp4":
            return get_output_file_path_for_mp4(input_file_path)
        case ".mkv":
            return get_output_file_path_for_mkv(input_file_path)
        case _:
            raise ValueError(f"Unsupported file type: {input_file_path}")


def yield_transcode_tasks(dir_path: Path) -> Iterator[Tuple[Path, Path]]:
    """
    Yield all video file paths in a directory that need transcoding.

    Args:
        dir_path (Path): Directory to search for video files.

    Yields:
        Tuple[Path, Path]: Pairs of (input_path, output_path) for files needing transcoding.
    """
    prepare_input_dir(dir_path)
    for suffix in (".mkv", ".mp4"):
        for input_file_path in dir_path.glob(f"**/*{suffix}"):
            if wait_until_file_stable(input_file_path) and (output_file_path := get_output_file_path(input_file_path)):
                yield input_file_path, output_file_path


def transcode_video_file(input_file_path: Path, output_file_path: Path, config_file_path: Path = HANDBRAKE_CONFIG) -> None:
    """
    Transcode a video file using HandBrake CLI.

    Args:
        input_file_path (Path): Path to the input video file.
        output_file_path (Path): Path to the output video file.
        config_file_path (Path, optional): Path to HandBrake config file. Defaults to `HANDBRAKE_CONFIG`.
    """
    if not input_file_path.exists():
        print("Skipping missing input file", input_file_path)
        return
    print(f"Transcoding: {input_file_path} -> {output_file_path}")
    command = [
        "HandBrakeCLI",
        "--preset-import-file", str(config_file_path),
        "-i", str(prepare_input_file(input_file_path)),
        "-o", str(prepare_output_file(output_file_path)),
    ]
    subprocess.run(command, check=True)


def get_video_duration(file_path: Path) -> int:
    """
    Get the duration of a video file in milliseconds.

    Args:
        file_path (Path): Path to the video file.

    Returns:
        int: Duration of the video in milliseconds.

    Raises:
        ValueError: If no video track is found in the file.
    """
    for track in MediaInfo.parse(file_path).tracks:
        if track.track_type == "Video":
            return int(float(track.duration))  # duration might look like '3614866.000000'
    raise ValueError(f"No video track found in {file_path}")


def monitor_and_transcode(*dir_paths: Path, check_interval_seconds: float = 60) -> None:
    """
    Monitor directories and transcode new video files as they appear. After transcoding, it verifies that input and output video durations match.

    Args:
        *dir_paths (Path): One or more directory paths to monitor.
        check_interval_seconds (float, optional): Time between directory scans in seconds. Defaults to 60.
    """
    while True:
        for input_file_path, output_file_path in chain.from_iterable(map(yield_transcode_tasks, dir_paths)):
            transcode_video_file(input_file_path, output_file_path)
            input_duration = get_video_duration(input_file_path)
            output_duration = get_video_duration(output_file_path)
            assert abs(input_duration - output_duration) <= 50, (input_duration, output_duration)  # at 30 fps, 50ms is 1.5 frames
        print(f"Sleeping for {check_interval_seconds} seconds...")
        time.sleep(check_interval_seconds)


if __name__ == "__main__":
    monitor_and_transcode(PROJECT_ROOT / "assets")
