import logging
import os
import subprocess
import sys
import time
from collections.abc import Iterator
from itertools import chain
from pathlib import Path

from pathlib_extensions import (
    prepare_input_dir,
    prepare_input_file,
    prepare_output_file,
)
from pymediainfo import MediaInfo

log_level = os.environ.get("LOG_LEVEL", "INFO").upper()
logging.basicConfig(
    level=getattr(logging, log_level, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%Y-%m-%dT%H:%M:%S",
)
logger = logging.getLogger(__name__)

PROJECT_ROOT = Path(__file__).parents[1]
HANDBRAKE_CONFIG = PROJECT_ROOT / "H264 NVENC CQ27.json"


def is_gpu_healthy() -> bool:
    """
    Checks if the GPU is healthy and available by running nvidia-smi.
    
    Returns:
        bool: True if nvidia-smi finished with exit code 0, False otherwise.
    """
    try:
        result = subprocess.run(["nvidia-smi"], check=False, capture_output=True)
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
        logger.debug("Monitoring file: %s", file_path)
        start_time = last_change_time = time.time()
        last_stat = file_path.stat()
        # case 0: the file is already stable
        if start_time - last_stat.st_mtime >= stability_duration_seconds:
            logger.debug("File is already stable: %s", file_path)
            return True
        while True:
            time.sleep(check_interval_seconds)
            current_time = time.time()
            current_stat = file_path.stat()
            # case 1: file is empty
            if current_stat.st_size == 0:
                logger.info("File is empty: %s", file_path)
                return False
            # case 2: timeout
            if current_time - start_time >= timeout_seconds:
                logger.info("Timeout waiting for file to stabilize: %s", file_path)
                return False
            # case 3: file has changed
            # must check timeout first, otherwise this function will stuck on a constantly-changing file
            if current_stat.st_size != last_stat.st_size or current_stat.st_mtime != last_stat.st_mtime:
                logger.info("File size or modification time has changed: %s", file_path)
                last_change_time = current_time
                last_stat = current_stat
                continue
            # case 4: file has stabilized
            if current_time - last_change_time >= stability_duration_seconds:
                logger.debug("File has stabilized: %s", file_path)
                return True
            # case 5: file did not change, but we're waiting for the stability duration to finish
            logger.debug("Waiting for the stability duration to finish: %s", file_path)
    except (OSError, FileNotFoundError) as e:
        logger.error("Could not wait for file %s to stabilize due to %s: %s", file_path, type(e).__name__, e)
        return False


def is_h264_encoded(file_path: Path) -> bool | None:
    """
    Check if a video file is encoded in H264/AVC format.

    Args:
        file_path (Path): Path to the video file.

    Returns:
        bool | None: True if the video is H264/AVC encoded, False otherwise, or None if no video track is found.
    """
    try:
        for track in MediaInfo.parse(prepare_input_file(file_path)).tracks:
            if track.track_type == "Video":
                return track.format == "AVC"
    except Exception as e:
        logger.error("Could not check encoding of %s due to %s: %s", file_path, type(e).__name__, e)
    return None


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
        logger.warning("Skipping missing input path: %s", input_file_path)
        return None
    match is_h264_encoded(input_file_path):
        case True:
            logger.debug("MP4 file is already encoded in H264: %s", input_file_path)
            return None
        case False:
            for counter in range(1, max_retries + 1):
                new_path = input_file_path.with_suffix(f".{counter}.mp4")
                # case 1: candidate path does not exist
                if not new_path.exists():
                    return new_path
                # case 2: candidate path is an H264-encoded video file
                elif new_path.is_file() and is_h264_encoded(new_path):
                    logger.debug("A subsequent file encoded in H264 already exists: %s -> %s", input_file_path, new_path)
                    return None
                # case 3: candidate path exists but is not a file
                continue
            return None
        case _:  # None: could not check encoding
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
        logger.warning("Skipping missing input path: %s", input_file_path)
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


def yield_transcode_tasks(dir_path: Path) -> Iterator[tuple[Path, Path]]:
    """
    Yield all video file paths in a directory that need transcoding.

    Args:
        dir_path (Path): Directory to search for video files.

    Yields:
        Tuple[Path, Path]: Pairs of (input_path, output_path) for files needing transcoding.
    """
    prepare_input_dir(dir_path)
    for suffix in (".mkv", ".mp4"):
        for input_file_path in dir_path.rglob(f"*{suffix}", case_sensitive=False):
            if not input_file_path.is_file():
                continue
            file_name = input_file_path.name
            if '.tmp' in file_name or '.temp' in file_name:  # skip temp files
                continue
            if wait_until_file_stable(input_file_path) and (output_file_path := get_output_file_path(input_file_path)):
                yield input_file_path, output_file_path


def get_video_duration_milliseconds(file_path: Path) -> int | None:
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
                return int(float(track.duration))  # track.duration might look like '3614866.000000'
    except Exception as e:
        logger.error("Could not get duration of %s due to %s: %s", file_path, type(e).__name__, e)
        return None
    logger.warning("Skipping duration check because no video track was found in %s", file_path)
    return None


def transcode_video_file(input_file_path: Path, output_file_path: Path, config_file_path: Path = HANDBRAKE_CONFIG) -> None:
    """
    Transcode a video file using HandBrake CLI.

    During transcoding, it writes to a temporary output file. This file is renamed to the final output filename if HandBrake exit with 0.

    Args:
        input_file_path (Path): Path to the input video file.
        output_file_path (Path): Path to the output video file.
        config_file_path (Path, optional): Path to HandBrake config file. Defaults to `HANDBRAKE_CONFIG`.
    """
    temp_output_file_path = output_file_path.parent / (output_file_path.name + ".tmp")
    if temp_output_file_path.exists():
        logger.warning("Skipping transcoding because the temp output path already exists: %s", temp_output_file_path)
        return
    command = [
        "HandBrakeCLI",
        "--preset-import-file", str(config_file_path),
        "-i", str(prepare_input_file(input_file_path)),
        "-o", str(prepare_output_file(temp_output_file_path)),
    ]
    logger.info("Starting subprocess: %s", command)
    # HandBrake may fail due to CUDA issues, in which case the container needs to be restarted
    try:
        duration_ms = get_video_duration_milliseconds(input_file_path)
        timeout_seconds = (duration_ms * 1.5 if duration_ms else 7_200_000) / 1000  # default to 2 hours timeout
        subprocess.run(command, check=True, timeout=timeout_seconds)
        if not output_file_path.exists():
            temp_output_file_path.rename(output_file_path)
        logger.info("HandBrake finished successfully: %s -> %s", input_file_path, output_file_path)
    except subprocess.TimeoutExpired:
        logger.error("HandBrake timed out after %s seconds processing %s", timeout_seconds, input_file_path)
        temp_output_file_path.unlink(missing_ok=True)
        raise


def monitor_and_transcode(*dir_paths: Path, check_interval_seconds: float = 60) -> None:
    """
    Monitor directories and transcode new video files as they appear. After transcoding, it verifies that input and output video durations match.

    Args:
        *dir_paths (Path): One or more directory paths to monitor.
        check_interval_seconds (float, optional): Time between directory scans in seconds. Defaults to 60.
    """
    while True:
        if not is_gpu_healthy():
            logger.critical("GPU health check failed. Restarting...")
            sys.exit(2)  # ENOENT
        for input_file_path, output_file_path in chain.from_iterable(map(yield_transcode_tasks, dir_paths)):
            transcode_video_file(input_file_path, output_file_path)
            input_duration_ms = get_video_duration_milliseconds(input_file_path)
            if input_duration_ms is None:
                logger.warning("Skipping duration check because no video track was found in %s", input_file_path)
                continue
            output_duration_ms = get_video_duration_milliseconds(output_file_path)
            if output_duration_ms is None:
                logger.warning("Skipping duration check because no video track was found in %s", output_file_path)
                continue
            if abs(input_duration_ms - output_duration_ms) > 500:  # at 30 fps, 500ms is 15 frames
                logger.error("Duration mismatch: %s (%sms) -> %s (%sms)", input_file_path, input_duration_ms, output_file_path, output_duration_ms)
                output_file_path.unlink(missing_ok=True)
        logger.debug("Sleeping for %s seconds...", check_interval_seconds)
        time.sleep(check_interval_seconds)


if __name__ == "__main__":
    monitor_and_transcode(Path(os.environ.get("MONITOR_DIR", PROJECT_ROOT / "assets")))
