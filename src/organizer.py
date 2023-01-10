from ast import ExtSlice
import hashlib
from datetime import datetime
from os import times
from pathlib import Path
from PIL import Image, ExifTags
import re
from typing import List, Union, Optional
from shutil import move as move_file, copy2 as copy_file
import shlex
import subprocess

def load_dict(backup_dir: Path) -> dict:
    result = {}
    with (backup_dir / "checksums").open("r") as fr:
        for line in fr:
            k, v = line.split(maxsplit=1)
            result[k] = v.rstrip()
    return result

def save_dict(backup_dir: Path, backup_dict: dict, suffix: Optional[str] = ""):
    checksum_file = (backup_dir / f"checksums{suffix}")
    try:
        copy_file(checksum_file, Path(str(checksum_file) + '.bkp'))
    except:
        pass
    with checksum_file.open("w") as fw:
        for k, v in backup_dict.items():
            fw.write(f'{k} {v}\n')
    
def refresh_checksums(backup_dir: Path, dry_run: bool):
    target_dirs = [backup_dir / "photos", backup_dir / "videos"]
    new_backup_dict = {}
    for t in target_dirs:
        for file in sorted(t.glob("**/*")):
            if not file.is_file():
                print(f"Skipping directory ${file}")
                continue
            
            print(f"Processing file {file}")
            checksum = get_checksum(file)
            new_backup_dict[checksum] = str(file)
    
    print(f"New checksum_dict has {len(new_backup_dict)} entries")
    suffix = "_new" if dry_run else ""
    save_dict(backup_dir, new_backup_dict, suffix)
    

def process_directory(backup_dir: Path, dry_run: bool):
    backup_dict = load_dict(backup_dir)
    print(f"Loaded {len(backup_dict)} checksums")

    dropbox_dir = backup_dir / "media_dropbox"
    print(f"\nProcessing directory: {dropbox_dir}")
    counts = {'moved': 0, 'removed': 0}
    for file in dropbox_dir.glob("**/*"):
        if '@eaDir' in str(file):
            continue
        process_file(file, backup_dict, backup_dir, counts, dry_run)
    if not dry_run and counts['moved'] or counts['removed']:
        save_dict(backup_dir, backup_dict)
    print(f'Counts:\n{counts}')


def get_checksum(file: Path):
    # print(f"\tCalculating MD5 checksum")
    m = hashlib.md5()
    count = 0
    with file.open("rb" ) as f:
        while True:
            # We calculate only for the first 100 MB or so
            if count > 3:
                break
            count += 1
            buf = f.read(2**25)  # 33MB chunks
            if not buf:
                break
            m.update( buf )
    return m.hexdigest()


def process_file(file: Path, backup_dict: dict, backup_dir: Path, counts: dict, dry_run: bool):
    """Processes the given file"""
    print(f"\nProcessing file: {file}")

    processors = {
        ".JPG": process_image,
        ".JPEG": process_image,
        ".PNG": process_image,
        ".AVI": process_video,
        ".MOV": process_video,
        ".MP4": process_video,
        ".MPG": process_video,
        ".MTS": process_video,
        ".M2TS": process_video,
    }
    extension = file.suffix.upper()
    if extension not in processors:
        print(f"\tUnsupported extension: {extension} skipping")
        return

    if not file.is_file():
        print(f"Not a file. Skipping")
        return
    checksum = get_checksum(file)

    existing_target_file = backup_dict.get(checksum, None)
    if existing_target_file is not None:
        if Path(existing_target_file).is_file:
            print(
                f"\n\tChecksum found in backup_dict: {existing_target_file}. Removing file."
            )
            counts['removed'] += 1
        try:
            if not dry_run:
                file.unlink()
            else:
                print(f"\tDry run: file not removed")
        except Exception:
            print(f"\tCould not remove the file: {file}")
            pass
        return
    else:
        try:
            target_file = processors[extension](file, backup_dir)
            print(f'\tMoving to file {target_file}')
            if dry_run:
                print(f"\tDry run: file not moved")
            else:
                move_file(file, target_file)
                backup_dict[checksum] = target_file
                counts['moved'] += 1
        except Exception as e:
            print(f'Got exception: {e}')
            pass

def process_image(file: Path, base_target_dir: Path) -> Path:
    tag_info = get_tag_info(file)
    fields = ["DateTimeOriginal", "DateTimeDigitized"]
    img_prefix = 'IMG'
    target_extension = ".JPG"
    base_target_dir = base_target_dir / 'photos'
    ts = None
    for key in fields:
        if key not in tag_info:
            continue
        print(f"\tUsing timestamp from {key}")
        ts = tag_info[key]

    # If no timestamp found in the EXIF data try to guess it from the file name
    if ts is None:
        print(f"\tFailed to get creation time from metadata. Trying file name.")
        ts = get_creation_date_from_file_name(file, r'\d{8}-\d{6}')
    
    if ts is None:
        raise RuntimeError(f'Could not find any of the fields {fields} in the tag info: {tag_info}')
    
    timestamp = _parse_time(ts)
    timestamp_str = datetime.strftime(timestamp, "%Y%m%d-%H%M%S")
    return get_target_file_name(base_target_dir, timestamp, f"{img_prefix}_{timestamp_str}", target_extension)
    

def process_video(file: Path, base_target_dir: Path) -> Path:
    """For videos we only get the creation time from the file name"""
    creation_time = get_creation_date_from_file_name(file, '\d{4}-\d{2}-\d{2}')
    print(f"New checksum_dict has {len(new_backup_dict)} entries")
    suffix = "_new" if dry_run else ""
    if creation_time is None:
        raise RuntimeError(f'Could not find the creation timestamp.')
    
    return get_target_file_name(base_target_dir / 'videos', _parse_time(creation_time), file.stem, file.suffix.upper())


def _parse_time(time_string: str) -> datetime:
    ts = None
    for dt_format in [r'%Y:%m:%d %H:%M:%S',
                      r'%Y%m%d-%H%M%S',
                      r'%Y-%m-%dT%H:%M:%S',
                      r'%Y-%m-%d',]:
        try:
            ts = datetime.strptime(time_string, dt_format)
            break
        except:
            pass
    
    if ts is None:
        raise RuntimeError(f'Could not parse date time: {time_string}')
    return ts


def get_tag_info(file: Path) -> dict:
    try:
        exif = Image.open(file)._getexif()
    except:
        print(f"{file} is not an image. Skipping it.")
        return {}

    if exif is None:
        print(f"\tImage {file} has no EXIF information. Skipping it")
        return {}

    ts_tags = (36867, 36868, 306, 50971)
    return {ExifTags.TAGS[t]: exif[t] for t in ts_tags if t in exif}


def get_target_file_name(base_target_dir: Path, timestamp: datetime, file_stem: str, extension: str):
        suffix = ""
        counter = 1
        target_dir = base_target_dir / str(timestamp.year) / f'{timestamp.month:02d}'
        target_dir.mkdir(parents=True, exist_ok=True)
        if not extension.startswith('.'):
            extension = f'.{extension}'

        got_it = False
        for _ in range(1000):
            target_file_name = target_dir / f"{file_stem}{suffix}{extension}"
            if target_file_name.is_file():
                suffix = f"_{counter:02d}"
                counter += 1
                continue
            got_it = True
            break

        if not got_it:
            raise RuntimeError(f'Could not find a target file name after 50 tries: last tried was {target_file_name}')
        return target_file_name


def get_creation_date_from_file_name(file: Path, match_pattern: str) -> dict:
    print(f"\tTrying to guess timestamp from the file name")
    match_object = re.search(match_pattern, file.name)
    print(f"\t\tGuessed timestamp: {match_object.group(0)}.")
    return match_object.group(0) if match_object else None
    


def _run_command(
    command: Union[str, List[str]],
    command_purpose: str = None,
    exit_on_error: bool = True,
    **kwargs,
):
    """Runs the command, checks for success and returns the result, with the stdout and stderr converted to str"""

    if command_purpose is None:
        command_purpose = command

    if isinstance(command, list):
        command_list = command
        command = " ".join(command_list)
    else:
        command_list = [
            x for x in shlex.split(command) if len(x) != 0
        ]  # handling multiple spaces

    result = subprocess.run(
        command_list, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs
    )
    if result.returncode != 0 and exit_on_error:
        raise RuntimeError(
            f'Failed to run command: "{command_purpose}".\n'
            f"\tCommand {command}\n"
            f"\tStdout: {result.stdout}\n"
            f"\tStderr: {result.stderr}"
        )

    def _decode(bytes_: bytes) -> str:
        result_ = bytes_.decode("utf-8")
        if result_.startswith("'"):
            result_ = result_[1:]
        if result_.endswith("'"):
            result_ = result_[:-1]
        if result_.endswith("\n"):
            result_ = result_[:-1]
        return result_

    result.stdout = _decode(result.stdout)
    result.stderr = _decode(result.stderr)
    return result
    
