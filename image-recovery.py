#!/usr/bin/env python3
import argparse
import imghdr
import logging
import os
import re
import shutil
from datetime import datetime
from os import path

from PIL import ExifTags, Image, UnidentifiedImageError
from PIL.Image import DecompressionBombError

is_exit = False


def setup_logging():
    global logger
    logger = logging.getLogger(__name__)
    logger.setLevel(logging.DEBUG)
    ch = logging.StreamHandler()
    ch.setLevel(logging.DEBUG)
    formatter = logging.Formatter("%(asctime)s %(levelname)s %(message)s")
    ch.setFormatter(formatter)
    logger.addHandler(ch)


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_dir")
    parser.add_argument("output_dir")
    parser.add_argument("skip_dir_prefix")
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args()


def mkdir_if_not_exists(target_dir):
    logger.debug("target_dir: %s", target_dir)
    if not path.isdir(target_dir):
        logger.info("Creating dir: %s", target_dir)
        os.makedirs(target_dir)


def exif2dict(img_exif):
    exif = {}
    for key, val in dict(img_exif).items():
        if key in ExifTags.TAGS:
            exif[ExifTags.TAGS[key]] = val
    return exif


def escape(text):
    return text.strip().replace("\x00", "").replace(" ", "_")


def get_nonconflicting_name(dst_path):
    dst_dir, file_name = path.split(dst_path)
    dst_name, dst_ext = path.splitext(file_name)
    counter = 1
    while path.isfile(
        dst_path := path.join(dst_dir, dst_name + "-" + str(counter).zfill(3) + dst_ext)
    ):
        counter += 1
    return dst_path


def move_without_conflict(file_path, dst_dir, file_name=None):
    is_log = True
    if file_name is None:
        # Get original filename
        _, file_name = path.split(file_path)
        is_log = False
    mkdir_if_not_exists(dst_dir)
    dst_path = path.join(dst_dir, file_name)
    if path.isfile(dst_path):
        dst_path = get_nonconflicting_name(dst_path)
    if is_log:
        logger.info("Moving to %s", dst_path)
    os.rename(file_path, dst_path)


def process_file(file_path):
    try:
        img: Image = Image.open(file_path)
    except (UnidentifiedImageError, DecompressionBombError, RuntimeError) as e:
        return False

    img_exif = img.getexif()

    if img_exif is None or len(dict(img_exif)) == 0:
        return False

    exif = exif2dict(img_exif)
    if "Model" not in exif:
        logger.debug("exif: %s", exif)
        return False

    logger.info("Processing: %s img_type: %s", file_path, img_type)

    model = escape(exif["Model"])

    if "DateTimeOriginal" in exif or "DateTime" in exif:
        date_key = "DateTimeOriginal"
        if "DateTimeOriginal" not in exif and "DateTime" in exif:
            date_key = "DateTime"
        try:
            created = datetime.strptime(escape(exif[date_key]), "%Y:%m:%d_%H:%M:%S")
        except (KeyError, ValueError) as e:
            logger.exception("Exception while parsing. Exiting immediately.")
            logger.error("exif: %s", exif)
            exit(3)
    else:
        # Get created time from stat
        stat = os.stat(file_path)
        created = datetime.fromtimestamp(stat.st_ctime)

    logger.info("model: %s created: %s", model, created)

    # Create dst dir
    dst_dir = path.join(
        output_dir, model, created.strftime("%Y"), created.strftime("%m")
    )
    dst_name = created.strftime("%Y-%m-%d_%H-%M-%S")
    _, dst_ext = path.splitext(file_path)
    file_name = dst_name + dst_ext
    move_without_conflict(file_path, dst_dir, file_name)

    global is_exit, image_counter
    image_counter += 1
    if image_counter >= 10:
        is_exit = True

    return True


if __name__ == "__main__":
    setup_logging()

    args = parse_args()
    logger.debug("args: %s", args)

    if not args.verbose:
        logger.setLevel(logging.INFO)

    input_dir = path.abspath(args.input_dir)
    logger.debug("input_dir: %s", input_dir)
    if not path.isdir(input_dir):
        logger.error(input_dir, "does not exist! Exiting.")
        exit(1)

    output_dir = path.abspath(args.output_dir)
    mkdir_if_not_exists(output_dir)

    skip_images_dir = path.abspath(args.skip_dir_prefix + "Images")
    mkdir_if_not_exists(skip_images_dir)

    skip_files_dir = path.abspath(args.skip_dir_prefix + "Files")
    mkdir_if_not_exists(skip_files_dir)

    # Process input dir
    image_counter = 0
    for root, dirs, files in os.walk(input_dir):
        for name in files:
            file_path = path.join(root, name)
            # logger.debug("file_path: %s", file_path)
            img_type = imghdr.what(file_path)
            if img_type:
                if not process_file(file_path):
                    move_without_conflict(file_path, skip_images_dir)
                    # is_exit = True
            else:
                move_without_conflict(file_path, skip_files_dir)
                # is_exit = True

            if is_exit:
                break

        if len(files) == 0 and len(dirs) == 0:
            logger.info("Deleting empty dir: %s", root)
            os.rmdir(root)

        if is_exit:
            break
