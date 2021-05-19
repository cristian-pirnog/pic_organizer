import hashlib
from datetime import datetime
from dateutil.parser import parse
from pathlib import Path
from PIL import Image, ExifTags
from typing import Union
from shutil import copyfile, move as move_file, copy2 as copy_file

def load_dict(backup_dir: Path) -> dict:
    result = {}
    with (backup_dir / "checksums").open("r") as fr:
        for line in fr:
            k, v = line.split()
            result[k] = v
    return result

def save_dict(backup_dir: Path, backup_dict: dict):
    checksum_file = (backup_dir / "checksums")
    copy_file(checksum_file, Path(str(checksum_file) + '.bkp'))
    with checksum_file.open("w") as fw:
        for k, v in backup_dict.items():
            fw.write(f'{k} {v}\n')
    


def process_directory(backup_dir: Path):
    backup_dict = load_dict(backup_dir)
    print(f"Loaded {len(backup_dict)} checksums")

    dropbox_dir = backup_dir / "media_dropbox"
    print(f"Processing directory: {dropbox_dir}")
    for file in dropbox_dir.glob("**/*"):
        if '@eaDir' in str(file):
            continue
        process_file(file, backup_dict, backup_dir)
    save_dict(backup_dir, backup_dict)


def process_file(file: Path, backup_dict: dict, backup_dir: Path) -> bool:
    """Processes the given file"""
    print(f"Processing file: {file}...    ", end="")

    processors = {
        ".JPG": process_image,
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
    checksum = hashlib.md5(file.open("rb").read()).hexdigest()

    existing_target_file = backup_dict.get(checksum, None)
    if existing_target_file is not None:
        if Path(existing_target_file).is_file:
            print(
                f"\n\tChecksum found in backup_dict: {existing_target_file}. Removing file."
            )
        try:
            file.unlink()
        except Exception:
            print(f"\tCould not remove the file: {file}")
            pass
        return
    else:
        try:
            target_file = processors[extension](file, backup_dir)
            move_file(file, target_file)
            backup_dict[checksum] = target_file
        except Exception as e:
            print(f'Got exception: {e}')
            pass
    print('Done')

def process_image(file: Path, base_target_dir: Path) -> Path:
    tag_info = get_tag_info(file)
    fields = ["DateTime", "DateTimeOriginal", "DateTimeDigitized"]
    for key in fields:
        if key not in tag_info:
            continue
        timestamp = datetime.strftime(parse(tag_info[key]), "%Y%m%d-%H%M%S")
        suffix = ""
        counter = 1
        target_dir = base_target_dir / 'photos' / timestamp[:4]
        target_dir.mkdir(parents=True, exist_ok=True)

        got_it = False
        for _ in range(50):
            target_file_name = target_dir / (f"IMG_{timestamp}{suffix}.JPG")
            if target_file_name.is_file():
                suffix = f"_{counter:02d}"
                counter += 1
                continue
            got_it = True
            break

        if not got_it:
            raise RuntimeError(f'Could not find a target file name after 50 tries: last tried was {target_file_name}')
        return target_file_name

    raise RuntimeError(f'Could not find any of the fields {fields} in the tag info: {tag_info}')


def process_video(file: Path, base_target_dir: Path) -> Path:
    raise RuntimeError(f'Function process_video not implemented')


def get_tag_info(file: Path) -> dict:
    try:
        exif = Image.open(file)._getexif()
    except:
        print(f"{file} is not an image. Skipping it.")
        return {}

    if exif is None:
        print(f"Image {file} has no EXIF information. Skipping it")
        return {}

    ts_tags = (36867, 36868, 306, 50971)
    return {ExifTags.TAGS[t]: exif[t] for t in ts_tags if t in exif}

