from itertools import chain
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Iterator, Tuple

from pathlib_extensions import prepare_input_dir, prepare_input_file, prepare_output_file
from pymediainfo import MediaInfo

PROJECT_ROOT = Path(__file__).parents[1]
HANDBRAKE_CONFIG = PROJECT_ROOT / "H264 NVENC CQ27.json"


def is_gpu_healthy() -> bool:
    """
    Checks if the GPU is healthy and available by running nvidia-smi.
    
    Returns:
        bool: True if nvidia-smi finished with exit code 0, False otherwise.
    """
    try:
        result = subprocess.run(["nvidia-smi"], check=False)
        return result.returncode == 0
    except Exception:
        return False


def wait_until_file_stable(file_path: Path, check_interval_seconds: float = 2, stability_duration_seconds: float = 5, timeout_seconds: float = 60) -> bool:
    """
    Block until a file is no longer being changed by monitoring size and modification time.

    Args:
        file_path (Path): Path to the file to be checked.
        check_interval_seconds (float, optional): Time between checks in seconds (default 2 seconds).
        stability_duration_seconds (float, optional): How long the file must be unchanged before considering it stable (default 5 seconds).
        timeout_seconds (float, optional): Maximum time to wait for the file to stabilize (default 60 seconds).

    Returns:
        bool: True if the file has stabilized, False if the file is inaccessible or empty.
    """
    if not file_path.is_file():
        return False
    try:
        print(f"Monitoring file: {file_path}")
        start_time = last_change_time = time.time()
        last_stat = file_path.stat()
        # skip empty files
        if last_stat.st_size == 0:
            print(f"File is empty: {file_path}")
            return False
        while True:
            time.sleep(check_interval_seconds)
            current_time = time.time()
            current_stat = file_path.stat()
            # case 1: file is empty
            if current_stat.st_size == 0:
                print(f"File is empty: {file_path}")
                return False
            # case 2: file has changed
            if current_stat.st_size != last_stat.st_size or current_stat.st_mtime != last_stat.st_mtime:
                print(f"File has changed: {file_path}")
                last_change_time = current_time
                last_stat = current_stat
                continue
            # case 3: file has stabilized
            if current_time - last_change_time >= stability_duration_seconds:
                print(f"File has stabilized: {file_path}")
                return True
            # case 4: timeout
            if current_time - start_time >= timeout_seconds:
                print(f"Timeout waiting for file to stabilize: {file_path}")
                return False
            # case 5: file did not change, but we're waiting for the stability duration to finish
            print(f"Waiting for the stability duration to finish: {file_path}")
    except (OSError, FileNotFoundError) as e:
        print(f"Could not wait for file {file_path} to stabilize due to {type(e).__name__}: {e}")
        return False


def is_h264_encoded(file_path: Path, file_stable_flag: bool = False) -> bool | None:
    """
    Check if a video file is encoded in H264/AVC format.

    Args:
        file_path (Path): Path to the video file.
        file_stable_flag (bool, optional): Whether the file is known to have stabilized. Defaults to False.

    Returns:
        bool | None: True if the video is H264/AVC encoded, False otherwise, or None if no video track is found.
    """
    try:
        for track in MediaInfo.parse(prepare_input_file(file_path)).tracks:
            if track.track_type == "Video":
                return track.format == "AVC"
    except Exception as e:
        print(f"Could not check encoding of {file_path} due to {type(e).__name__}: {e}")
        return None
    if file_stable_flag:
        print(f"Skipping encoding check because no video track was found in {file_path}")
        return None
    if not wait_until_file_stable(file_path):
        return None
    return is_h264_encoded(file_path, file_stable_flag=True)


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
        print(f"Skipping missing input path: {input_file_path}")
        return None
    if is_h264_encoded(input_file_path):
        print(f"MP4 file is already encoded in H264: {input_file_path}")
        return None
    for counter in range(1, max_retries + 1):
        new_path = input_file_path.with_suffix(f".{counter}.mp4")
        # case 1: candidate path does not exist
        if not new_path.exists():
            return new_path
        # case 2: candidate path is an H264-encoded video file
        elif new_path.is_file() and is_h264_encoded(new_path):
            print(f"A subsequent file encoded in H264 already exists: {input_file_path} -> {new_path}")
            return None
        # case 3: candidate path exists but is not a file
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
        print(f"Skipping missing input path: {input_file_path}")
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
            if output_file_path := get_output_file_path(input_file_path):
                yield input_file_path, output_file_path


def transcode_video_file(input_file_path: Path, output_file_path: Path, config_file_path: Path = HANDBRAKE_CONFIG) -> None:
    """
    Transcode a video file using HandBrake CLI.

    During transcoding, it writes to a temporary output file. This file is renamed to the final output filename if HandBrake exit with 0.

    Args:
        input_file_path (Path): Path to the input video file.
        output_file_path (Path): Path to the output video file.
        config_file_path (Path, optional): Path to HandBrake config file. Defaults to `HANDBRAKE_CONFIG`.
    """
    if not wait_until_file_stable(input_file_path):
        print(f"Skipping transcoding because the input file does not exist or has not stabilized: {input_file_path}")
        return False
    temp_output_file_path = output_file_path.parent / (output_file_path.name + ".tmp")
    if temp_output_file_path.exists():
        print(f"Skipping transcoding because the temp output path already exists: {temp_output_file_path}")
        return False
    command = [
        "HandBrakeCLI",
        "--preset-import-file", str(config_file_path),
        "-i", str(prepare_input_file(input_file_path)),
        "-o", str(prepare_output_file(temp_output_file_path)),
    ]
    print(f"Starting subprocess: {command}")
    # HandBrake may fail due to CUDA issues, in which case the container needs to be restarted
    subprocess.run(command, check=True)
    if not output_file_path.exists():
        temp_output_file_path.rename(output_file_path)
    print(f"HandBrake finished successfully: {input_file_path} -> {output_file_path}")


def get_video_duration(file_path: Path) -> int | None:
    """
    Get the duration of a video file in milliseconds.

    Args:
        file_path (Path): Path to the video file.

    Returns:
        int | None: Duration of the video in milliseconds, or None if no video track is found.
    """
    try:
        for track in MediaInfo.parse(file_path).tracks:
            if track.track_type == "Video":
                return int(float(track.duration))  # duration might look like '3614866.000000'
    except Exception as e:
        print(f"Could not get duration of {file_path} due to {type(e).__name__}: {e}")
        return None
    print(f"Skipping duration check because no video track was found in {file_path}")
    return None


def monitor_and_transcode(*dir_paths: Path, check_interval_seconds: float = 60) -> None:
    """
    Monitor directories and transcode new video files as they appear. After transcoding, it verifies that input and output video durations match.

    Args:
        *dir_paths (Path): One or more directory paths to monitor.
        check_interval_seconds (float, optional): Time between directory scans in seconds. Defaults to 60.
    """
    while True:
        if not is_gpu_healthy():
            print("GPU health check failed. Restarting...")
            sys.exit(2)  # ENOENT
        for input_file_path, output_file_path in chain.from_iterable(map(yield_transcode_tasks, dir_paths)):
            transcode_video_file(input_file_path, output_file_path)
            input_duration = get_video_duration(input_file_path)
            if input_duration is None:
                print(f"Skipping duration check because no video track was found in {input_file_path}")
                continue
            output_duration = get_video_duration(output_file_path)
            if output_duration is None:
                print(f"Skipping duration check because no video track was found in {output_file_path}")
                continue
            if abs(input_duration - output_duration) > 500:  # at 30 fps, 500ms is 15 frames
                print(f"Duration mismatch: {input_file_path} ({input_duration}ms) -> {output_file_path} ({output_duration}ms)")
                output_file_path.unlink(missing_ok=True)
        print(f"Sleeping for {check_interval_seconds} seconds...")
        time.sleep(check_interval_seconds)


if __name__ == "__main__":
    monitor_and_transcode(Path(os.environ.get("MONITOR_DIR", PROJECT_ROOT / "assets")))
