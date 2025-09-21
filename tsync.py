#!/usr/bin/env -S mamba run -n PyHome python

"""
tsync.py — recursive copy & metadata synchronizer
=========================================================
Recursively copies media files from *source* to *destination*, mirrors a chosen
Exif/QuickTime timestamp across related tags and keeps the file-name consistent
(YYYYMMDD_HHMMSS.ext lower-case).

Updated 2025-05-05.
"""

from __future__ import annotations
import argparse
import random
import re
import shutil
import sys
import logging
from datetime import datetime
from PIL import Image
from pillow_heif import register_heif_opener
from pathlib import Path
from typing import Dict, Optional, List

from exiftool import ExifToolHelper
from exiftool.exceptions import ExifToolExecuteError

# ------------------------------------------------------------------------
# configuration & constants
# ------------------------------------------------------------------------
DEFAULT_SRC = "/home/ntheme/Data2/Temp/Sorting"
DEFAULT_DST = "adjusted"

_VERBOSE = False
_NO_WRITE_META = False

FNAME_RE = re.compile(r"^\d{8}_\d{6}$")

STREAMS: Dict[str, Dict[str, str]] = {
    "image": {
        "fname": "File:FileName",
        "fmodify": "File:FileModifyDate",
        "faccess": "File:FileAccessDate",
        "fnode": "File:FileInodeChangeDate",
        "emodify": "EXIF:ModifyDate",
        "eorigin": "EXIF:DateTimeOriginal",
        "ecreate": "EXIF:CreateDate",
    },
    "video": {
        "fname": "File:FileName",
        "fmodify": "File:FileModifyDate",
        "faccess": "File:FileAccessDate",
        "fnode": "File:FileInodeChangeDate",
        "qcreate": "QuickTime:CreateDate",
        "qmodify": "QuickTime:ModifyDate",
        "qmcreate": "QuickTime:MediaCreateDate",
        "qmmodify": "QuickTime:MediaModifyDate",
        "qtcreate": "QuickTime:TrackCreateDate",
        "qtmodify": "QuickTime:TrackModifyDate",
    },
    "audio": {
        "fname": "File:FileName",
        "fmodify": "File:FileModifyDate",
        "faccess": "File:FileAccessDate",
        "fnode": "File:FileInodeChangeDate",
    },
}

register_heif_opener()


# ------------------------------------------------------------------------
# logging setup
# ------------------------------------------------------------------------
def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        format="[%(levelname)s] %(message)s", level=level
    )


def cprint(msg: str, level: str = "info") -> None:
    """Simple wrapper to log messages."""
    if level == "debug":
        logging.debug(msg)
    elif level == "warn":
        logging.warning(msg)
    elif level == "error":
        logging.error(msg)
    else:
        logging.info(msg)


# ------------------------------------------------------------------------
# util functions
# ------------------------------------------------------------------------
def get_mime(meta: dict) -> List[str]:
    """Return a top-level MIME type from metadata."""
    return meta.get("File:MIMEType", "").split("/", 1)


def fname_from_ts(ts: str) -> str:
    """Normalize timestamp string to 'YYYYMMDD_HHMMSS' format."""
    return ts.replace(":", "").replace(" ", "_")[:15]


def ts_from_fname(stem: str) -> str:
    """Parse timestamp from filename stem 'YYYYMMDD_HHMMSS'."""
    if not FNAME_RE.match(stem):
        raise RuntimeError("Filename stem must be 'YYYYMMDD_HHMMSS'")
    dt = datetime.strptime(stem, "%Y%m%d_%H%M%S")
    return dt.strftime("%Y:%m:%d %H:%M:%S")


def ensure_unique(path: Path) -> Path:
    """Generate a unique Path by appending incrementing suffix if needed."""
    if not path.exists():
        return path
    i = 1
    while True:
        candidate = path.with_name(f"{path.stem}_{i}{path.suffix}")
        if not candidate.exists():
            return candidate
        i += 1


def convert_photo_to_jpg(src_path: Path):
    jpg_path = src_path.with_suffix('.jpg')
    unique_jpg = ensure_unique(jpg_path)

    img = Image.open(src_path)

    if img.mode != 'RGB':
        img = img.convert('RGB')

    img.save(unique_jpg, format="JPEG", quality=100, subsampling=0, optimize=False)
    src_path.unlink()
    return unique_jpg


def convert_video_to_mp4(src_path: Path) -> Path:
    """Convert video to MP4 using ffmpeg and remove the original."""
    mp4_path = src_path.with_suffix(".mp4")
    unique_mp4 = ensure_unique(mp4_path)

    import subprocess

    result = subprocess.run([
        "ffmpeg", "-y", "-i", str(src_path),
        "-c:v", "libx264", "-preset", "fast", "-crf", "22",
        "-c:a", "aac", "-b:a", "128k",
        str(unique_mp4)
    ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    if result.returncode != 0 or not unique_mp4.exists():
        raise RuntimeError(f"Failed to convert video: {src_path.name}")

    src_path.unlink()
    return unique_mp4


# ------------------------------------------------------------------------
# CLI parsing
# ------------------------------------------------------------------------
def parse_cli(argv: Optional[list[str]] = None):
    p = argparse.ArgumentParser(
        prog="sync_tags.py",
        description="Copy files and synchronise Exif/QuickTime timestamps."
    )
    p.add_argument("-t", "--type", dest="type_key", metavar="TAG_KEY",
                   help="choose specific metadata tag to mirror")
    p.add_argument("-e", "--example", dest="example", nargs="?", const="",
                   metavar="FILE", help="show example metadata")
    p.add_argument("-s", "--source", dest="src_folder", default=DEFAULT_SRC)
    p.add_argument("-d", "--destination", dest="dst_folder", default=DEFAULT_DST)
    p.add_argument("-a", "--all", action="store_true",
                   help="print full metadata in example mode")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="enable debug output")
    p.add_argument("-m", "--manual", dest="manual_ts_raw", metavar="YYYYMMDD_HHMMSS",
                   help="force-set timestamp to this value for every file")
    p.add_argument("-f", "--force", action="store_true",
                   help="skip prompts and force operations")
    p.add_argument("--no-write-meta", action="store_true",
                   help="skip writing metadata tags")
    p.add_argument("-r", "--remove-source", action="store_true",
                   help="delete source files after syncing")

    args = p.parse_args(argv)
    args.remove_source = args.remove_source
    global _VERBOSE, _NO_WRITE_META
    _VERBOSE = args.verbose
    _NO_WRITE_META = args.no_write_meta

    setup_logging(_VERBOSE)

    if args.manual_ts_raw:
        if args.example is not None or args.type_key:
            p.error("-m/--manual cannot be combined with -e/--example or -t/--type")
        if not FNAME_RE.match(args.manual_ts_raw):
            p.error("-m must match YYYYMMDD_HHMMSS")
        args.manual_ts = datetime.strptime(
            args.manual_ts_raw, "%Y%m%d_%H%M%S"
        ).strftime("%Y:%m:%d %H:%M:%S")
    else:
        args.manual_ts = None

    if args.type_key is None and args.example is None and args.manual_ts_raw is None:
        p.error("either -t/--type, -e/--example, or -m/--manual is required")
    if args.example is not None and args.type_key is not None and args.all:
        p.error("-a cannot be used with -t when -e is given")

    spath = Path(args.src_folder).expanduser()
    spath = spath if spath.is_absolute() else Path(DEFAULT_SRC) / spath
    if not spath.exists():
        p.error(f"Source not found: {spath}")
    args.src_path = spath.resolve() if spath.is_dir() else spath.parent.resolve()
    args.src_file = None if spath.is_dir() else spath.resolve()

    dst_arg = Path(args.dst_folder).expanduser()
    args.dst_path = dst_arg.resolve() if dst_arg.is_absolute() else (args.src_path / dst_arg)
    if args.dst_path.resolve() == args.src_path:
        p.error("Destination must differ from source")

    if args.src_file is None:
        try:
            args.skip_top_dir = args.dst_path.relative_to(args.src_path).parts[0]
        except ValueError:
            args.skip_top_dir = None
    else:
        args.skip_top_dir = None

    return args


# ------------------------------------------------------------------------
# core synchronisation
# ------------------------------------------------------------------------
def synchronise_file(
        src_file: Path,
        src_root: Path,
        dst_root: Path,
        stream_key: str,
        et: ExifToolHelper,
        stats: Dict[str, int],
        manual_ts: Optional[str] = None,
):
    """Copy one file atomically and sync all related metadata tags."""
    meta = et.get_metadata(str(src_file))[0]
    mime = get_mime(meta)
    tag_map = STREAMS.get(mime[0])
    if not tag_map:
        raise RuntimeError(f"Unknown MIME '{mime[0]} with type '{mime[1]}'")

    if stream_key == 'manual':
        main_tag = "File:Manual"
        main_val = manual_ts
    elif stream_key == "fname":
        main_tag = tag_map[stream_key]
        main_val = ts_from_fname(src_file.stem)
    else:
        main_tag = tag_map[stream_key]
        main_val = meta.get(main_tag)
        if not main_val:
            raise RuntimeError(f"File has no tag {main_tag}")

    old_vals = {tag: meta.get(tag) for tag in tag_map.values()}

    rel = src_file.relative_to(src_root)
    dst_dir = dst_root / rel.parent
    dst_dir.mkdir(parents=True, exist_ok=True)

    if stream_key == "fname":
        base_name = src_file.stem + src_file.suffix.lower()
    else:
        base_name = fname_from_ts(main_val) + src_file.suffix.lower()
    new_path = ensure_unique(dst_dir / base_name)

    shutil.copy2(src_file, new_path)

    if mime[0] == 'image' and mime[1] != 'jpeg':
        try:
            new_path = convert_photo_to_jpg(new_path)
            stats["converted_jpg"] += 1
        except Exception:
            raise
    # elif mime[0] == 'video' and new_path.suffix.lower() != '.mp4':
    #     try:
    #         new_path = convert_video_to_mp4(new_path)
    #         stats["converted_mp4"] += 1
    #     except Exception:
    #         raise

    if not _NO_WRITE_META:
        params = ["-overwrite_original", "-api", "QuickTimeUTC"]
        other_tags = {tag: main_val for tag in tag_map.values()}
        other_tags["File:FileName"] = new_path.name

        try:
            et.set_tags([str(new_path)], tags=other_tags, params=params)
        except ExifToolExecuteError:
            cprint("Reconverting JPG", "warn")
            shutil.copy2(new_path, new_path.with_suffix(".JPG"))
            new_path.unlink()
            convert_photo_to_jpg(new_path.with_suffix(".JPG"))
            stats["converted_jpg"] += 1
            try:
                et.set_tags([str(new_path)], tags=other_tags, params=params)
            except ExifToolExecuteError:
                new_path.unlink()
                raise

    return new_path, main_tag, main_val, old_vals


# ------------------------------------------------------------------------
# example mode
# ------------------------------------------------------------------------
def show_example_info(args):
    """Example mode: show metadata for one random or specified file."""
    if args.example == "":
        files = [f for f in args.src_path.rglob("*")
                 if f.is_file() and not (args.skip_top_dir and
                                         f.relative_to(args.src_path).parts[0] == args.skip_top_dir)]
        if not files:
            sys.exit("No files for example")
        file_path = random.choice(files)
        cprint(f"Random file selected: {file_path.relative_to(args.src_path)}", "info")
    else:
        file_path = Path(args.example)
        if not file_path.is_absolute():
            file_path = args.src_path / file_path
        if not file_path.exists():
            sys.exit(f"File not found: {file_path}")

    with ExifToolHelper() as et:
        meta = et.get_metadata(str(file_path))[0]

    mime = get_mime(meta)[0]
    tag_map = STREAMS.get(mime, {})

    if args.type_key:
        full_tag = tag_map.get(args.type_key)

        if full_tag:
            cprint(f"{full_tag}: {meta.get(full_tag)}", "info")
        else:
            cprint("Requested tag not applicable to this file", "warn")
        return

    import json
    if args.all:
        print(json.dumps(meta, indent=2, ensure_ascii=False))
    else:
        print(f"== {file_path.name} ==")
        for _, tag in tag_map.items():
            print(f"{tag}: {meta.get(tag)}")


# ------------------------------------------------------------------------
# batch mode
# ------------------------------------------------------------------------
def run_batch_sync(args):
    """Batch mode: sync all files under source to destination."""
    stats = {
        "processed": 0,
        "converted_jpg": 0,
        "converted_mp4": 0,
        "failed": 0,
        "skipped": 0,
        "removed": 0,
        "removed_dirs": 0,
    }

    if args.dst_path.exists() and any(args.dst_path.iterdir()):
        if args.force:
            cprint("Force wipe: removing existing destination content", "warn")
            for item in args.dst_path.iterdir():
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()
        else:
            resp = input(
                f"Destination '{args.dst_path}' is not empty.\n"
                "  [y] – merge with existing content\n"
                "  [c] – COMPLETELY WIPE the folder and continue\n"
                "  anything else – abort\n"
                "Your choice: "
            ).strip().lower()
            if resp not in {"y", "c"}:
                sys.exit("Aborted by user")
            if resp == "c":
                cprint("Wiping destination folder…", "warn")
                for item in args.dst_path.iterdir():
                    if item.is_dir():
                        shutil.rmtree(item)
                    else:
                        item.unlink()
    else:
        args.dst_path.mkdir(parents=True, exist_ok=True)

    with ExifToolHelper() as et:
        stream_key = "manual" if args.manual_ts else args.type_key

        cprint(f"Using tag: {stream_key}", "info")

        file_iter = [args.src_file] if args.src_file else args.src_path.rglob("*")
        for f in file_iter:
            rel = f.relative_to(args.src_path)
            if not f.is_file() or (args.skip_top_dir and rel.parts[0] == args.skip_top_dir):
                continue
            try:
                stats["processed"] += 1
                new_file, tag_full, val, old_vals = synchronise_file(
                    f, args.src_path, args.dst_path, stream_key, et, stats, args.manual_ts)
            except Exception as exc:
                cprint(f"Skip {rel} → {exc}", "warn")
                stats["failed"] += 1
                continue

            cprint(f"OK {rel} → {new_file.relative_to(args.dst_path)} ({tag_full} = {val})", "info")

            if args.remove_source:
                try:
                    f.unlink()
                    stats["removed"] += 1
                    cprint(f"REMOVED {rel}", "info")
                    parent = f.parent

                    while parent != args.src_path and not any(parent.iterdir()):
                        parent_rel = parent.relative_to(args.src_path)
                        parent.rmdir()
                        stats["removed_dirs"] += 1
                        cprint(f"REMOVED DIR {parent_rel}", "info")
                        parent = parent.parent
                except Exception as e:
                    cprint(f"Failed to clean up {rel} or its dirs: {e}", "warn")

    cprint("==== Summary ====", "info")
    for k, v in stats.items():
        cprint(f"{k.replace('_', ' ').capitalize()}: {v}", "info")


# ------------------------------------------------------------------------
# entry point
# ------------------------------------------------------------------------
def main():
    args = parse_cli()
    if args.example is not None:
        show_example_info(args)
    else:
        run_batch_sync(args)


if __name__ == "__main__":
    main()
