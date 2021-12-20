# vim: ft=python fileencoding=utf-8 sw=4 et sts=4

# This file is part of vimiv.
# Copyright 2017-2021 Christian Karl (karlch) <karlch at protonmail dot com>
# License: GNU GPL v3, see the "LICENSE" and "AUTHORS" files for details.

"""Functions dealing with files and paths."""

import imghdr
import functools
import os
from stat import S_ISDIR, S_ISREG
from typing import List, Tuple, Optional, BinaryIO, Iterable, Callable

from PyQt5.QtGui import QImageReader

from vimiv.utils import imagereader


ImghdrTestFuncT = Callable[[bytes, Optional[BinaryIO]], bool]


def listdir(directory: str, show_hidden: bool = False) -> List[str]:
    """Wrapper around os.listdir.

    Args:
        directory: Directory to check for files in via os.listdir(directory).
        show_hidden: Include hidden files in output.
    Returns:
        Sorted list of files in the directory with their absolute path.
    """
    directory = os.path.abspath(os.path.expanduser(directory))
    return sorted(
        os.path.join(directory, path)
        for path in os.listdir(directory)
        if show_hidden or not path.startswith(".")
    )


SupportedMeta = Tuple[List[Tuple[str, os.stat_result]], List[Tuple[str, os.stat_result]]]


def supported_with_meta(paths: Iterable[str]) -> SupportedMeta:
    directories = []
    images = []
    for path in paths:
        stat_result = os.stat(path)
        if S_ISDIR(stat_result.st_mode):
            directories.append((path, stat_result))
        elif is_image(path, stat_result):
            images.append((path, stat_result))
    return images, directories


def strip_meta(files: SupportedMeta) -> Tuple[List[str], List[str]]:
    def first(it):
        return list(map(lambda a: a[0], it))
    images, directories = files
    return first(images), first(directories)


def supported(paths: Iterable[str]) -> Tuple[List[str], List[str]]:
    """Get a list of supported images and a list of directories from paths.

    Args:
        paths: List containing paths to parse.
    Returns:
        images: List of images inside the directory.
        directories: List of directories inside the directory.
    """
    return strip_meta(supported_with_meta(paths))


def get_size(path: str, stat_result: Optional[os.stat_result] = None) -> str:
    """Get the size of a path in human readable format.

    If the path is an image, the filesize is returned in the form of 2.3M. If
    the path is a directory, the amount of supported files in the directory is
    returned.

    Returns:
        Size of path as string.
    """
    try:
        if stat_result is not None:
            isfile = S_ISREG(stat_result.st_mode)
        else:
            isfile = os.path.isfile(path)
    except OSError:
        return "N/A"
    if isfile:
        return get_size_file(path, stat_result)
    return get_size_directory(path)


def get_size_file(path: str, stat_result: Optional[os.stat_result] = None) -> str:
    """Retrieve the size of a file as formatted byte number in human-readable format.

    Args:
        path: Path to the file
        stat_result: Result of os.stat() to determine node type of filename without disk access.
    """
    try:
        if stat_result is not None:
            size = stat_result.st_size
        else:
            size = os.path.getsize(path)
        return sizeof_fmt(size)
    except OSError:
        return "N/A"


def sizeof_fmt(num: float) -> str:
    """Retrieve size of a byte number in human-readable format.

    Args:
        num: Filesize in bytes.

    Returns:
        Filesize in human-readable format.
    """
    for unit in ("B", "K", "M", "G", "T", "P", "E", "Z"):
        if num < 1024.0:
            if num < 100:
                return f"{num:3.1f}{unit}"
            return f"{num:3.0f}{unit}"
        num /= 1024.0
    return f"{num:.1f}Y"


def get_size_directory(path: str) -> str:
    """Get size of directory by checking amount of supported paths.

    Args:
        path: Path to directory to check.
    Returns:
        Size as formatted string.
    """
    try:
        return str(len(os.listdir(path)))
    except OSError:
        return "N/A"


def is_image(filename: str, stat_result: Optional[os.stat_result] = None) -> bool:
    """Check whether a file is an image.

    Args:
        filename: Name of file to check.
        stat_result: Result of os.stat() to determine node type of filename without disk access.
    """
    try:
        if stat_result is not None:
            is_file = S_ISREG(stat_result.st_mode)
        else:
            is_file = os.path.isfile(filename)
        return is_file and imghdr.what(filename) is not None
    except OSError:
        return False


def listfiles(directory: str, abspath: bool = False) -> List[str]:
    """Return list of all files in directory traversing the directory recursively.

    Args:
        directory: The directory to traverse.
        abspath: Return the absolute path to the files, not relative to directory.
    """
    return [
        os.path.join(root, fname)
        if abspath
        else os.path.join(root.replace(directory, "").lstrip("/"), fname)
        for root, _, files in os.walk(directory)
        for fname in files
    ]


def add_image_format(name: str, check: ImghdrTestFuncT) -> None:
    """Add a new image format to the checks performed in is_image.

    Args:
        name: Name of the image format, e.g. "svg".
        check: Function used to determine if the file is of this format.
    """

    @functools.wraps(check)
    def test(h: bytes, f: Optional[BinaryIO]) -> Optional[str]:
        if check(h, f):
            if hasattr(test, "checked"):
                return name
            if (
                name in QImageReader.supportedImageFormats()
                or name in imagereader.external_handler
            ):
                setattr(test, "checked", True)
                return name
            imghdr.tests.remove(test)
        return None

    imghdr.tests.insert(add_image_format.index, test)  # type: ignore
    add_image_format.index += 1  # type: ignore


add_image_format.index = 3  # type: ignore  # Start inserting after jpg, png and gif


def test_svg(h: bytes, _f: Optional[BinaryIO]) -> bool:
    return h.startswith((b"<?xml", b"<svg"))


add_image_format("svg", test_svg)


# We now directly override the jpg part of imghdr as it has some known limitations
# See e.g. https://bugs.python.org/issue16512
def test_jpg(h: bytes, _f: Optional[BinaryIO]) -> Optional[str]:
    """Custom jpg test function.

    The one from the imghdr module fails with some jpgs that include ICC_PROFILE data.
    """
    if h[6:10] in (b"JFIF", b"Exif"):
        return "jpg"
    if h[:2] == b"\xff\xd8" and (b"JFIF" in h or b"8BIM" in h):
        return "jpg"
    return None


def test_jpg_fallback(h: bytes, _f: Optional[BinaryIO]) -> Optional[str]:
    """Fallback test for jpg files with no headers, only the two starting bits."""
    return "jpg" if h[:2] == b"\xff\xd8" else None


imghdr.tests[0] = test_jpg
imghdr.tests.append(test_jpg_fallback)
