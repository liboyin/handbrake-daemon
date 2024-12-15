from itertools import chain
from pathlib import Path
import subprocess
import time
from typing import Iterator, Tuple

from pathlib_extensions import prepare_input_dir, prepare_input_file, prepare_output_file
from pymediainfo import MediaInfo

PROJECT_ROOT = Path(__file__).parents[1]
HANDBRAKE_CONFIG = PROJECT_ROOT / "H264 NVENC CQ27.json"


def is_h264_encoded(file_path: Path) -> bool:
    for track in MediaInfo.parse(prepare_input_file(file_path)).tracks:
        if track.track_type == "Video":
            return track.format == "AVC"
    raise ValueError(f"No video track found in {file_path}")


def get_output_file_path_for_mp4(input_file_path: Path) -> Path | None:
    if not input_file_path.exists():
        print("Skipping missing input file", input_file_path)
        return None
    if is_h264_encoded(input_file_path):
        print("MP4 file is already encoded in H264:", input_file_path)
        return None
    counter = 1
    while True:
        new_path = input_file_path.with_suffix(f".{counter}.mp4")
        if not new_path.exists():
            return new_path
        # if new_path exists but is not a file, move on to the next candidate filename
        elif new_path.is_file() and is_h264_encoded(new_path):
            print(f"A subsequent file encoded in H264 already exists: {input_file_path} -> {new_path}")
            return None
        counter += 1


def get_output_file_path_for_mkv(input_file_path: Path) -> Path | None:
    if not input_file_path.exists():
        print("Skipping missing input file", input_file_path)
        return None
    mp4_file_path = input_file_path.with_suffix(".mp4")
    if not mp4_file_path.exists():
        return mp4_file_path
    return get_output_file_path_for_mp4(mp4_file_path)


def get_output_file_path(input_file_path: Path) -> Path | None:
    match input_file_path.suffix.lower():
        case ".mp4":
            return get_output_file_path_for_mp4(input_file_path)
        case ".mkv":
            return get_output_file_path_for_mkv(input_file_path)
        case _:
            raise ValueError(f"Unsupported file type: {input_file_path}")


def yield_transcode_tasks(dir_path: Path) -> Iterator[Tuple[Path, Path]]:
    prepare_input_dir(dir_path)
    for suffix in (".mkv", ".mp4"):
        for input_file_path in dir_path.glob(f"**/*{suffix}"):
            if output_file_path := get_output_file_path(input_file_path):
                yield input_file_path, output_file_path


def transcode_video_file(input_file_path: Path, output_file_path: Path, config_file_path: Path = HANDBRAKE_CONFIG) -> None:
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


def monitor_and_transcode(*dir_paths: Path, check_interval_seconds: float = 60) -> None:
    while True:
        for input_file_path, output_file_path in chain.from_iterable(map(yield_transcode_tasks, dir_paths)):
            transcode_video_file(input_file_path, output_file_path)
        print(f"Sleeping for {check_interval_seconds} seconds...")
        time.sleep(check_interval_seconds)


if __name__ == "__main__":
    monitor_and_transcode(PROJECT_ROOT / "assets")
