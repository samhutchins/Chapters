# Chapters
# Copyright (C) 2019  Sam Hutchins
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <https://www.gnu.org/licenses/>.

from __future__ import annotations

import collections
import os
import pickle
import re
import struct
import subprocess
import wave
from abc import ABC, abstractmethod
from io import BytesIO
from pathlib import Path
from subprocess import Popen, PIPE, STARTUPINFO
from threading import Thread
from typing import List, Dict, IO, NamedTuple, Optional, Callable, Tuple, Union
from urllib.error import HTTPError
from urllib.request import urlopen
from wave import Wave_read

from mutagen import id3

__all__ = ["APPLICATION_NAME", "APPLICATION_VERSION", "HOMEPAGE", "DOCUMENTATION", "GITHUB", "ISSUES",
           "Chapter", "MetaData",
           "LibChapters", "AbstractLibChaptersListener",
           "UpdateChecker", "AbstractUpdateCheckerListener",
           "Prefs"]


class LibChapters:
    def __init__(self, listener: AbstractLibChaptersListener) -> None:
        self.listener = listener
        self.mp3_data: Optional[BytesIO] = None

    def encode_wav_file(self, path_to_wav_file: str) -> None:
        run_async(lambda: self.__encode_file(path_to_wav_file))

    def read_metadata_from_wav_file(self, path_to_wav_file: str) -> None:
        run_async(lambda: self.__read_metadata_from_wav_file(path_to_wav_file))

    def read_metadata_from_mp3_file(self, path_to_mp3_file: str) -> None:
        run_async(lambda: self.__read_metadata_from_mp3_file(path_to_mp3_file))

    def write_metadata_to_file(self, meta_data: MetaData, path_to_mp3_file: str,) -> None:
        run_async(lambda: self.__write_metadata_to_file(meta_data, path_to_mp3_file))

    def write_mp3_data_with_metadata(self, metadata: MetaData, path_to_output: str) -> None:
        run_async(lambda: self.__write_mp3_data_with_metadata(metadata, path_to_output))

    def copy_mp3_with_metadata(self, path_to_input_mp3: str, path_to_output_mp3: str, metadata: MetaData) -> None:
        run_async(lambda: self.__copy_mp3_with_metadata(path_to_input_mp3, path_to_output_mp3, metadata))

    def __encode_file(self, path_to_wav_file: str) -> None:
        self.listener.encode_started()
        lame = Lame(self.listener)
        self.mp3_data = lame.encode(path_to_wav_file)
        self.listener.encode_complete()

    def __read_metadata_from_wav_file(self, path_to_wav_file) -> None:
        self.listener.read_metadata_started()
        episode_number, episode_title = self.__guess_podcast_info_from_filename(path_to_wav_file)
        chapters = self.__read_chapters_from_wav_file(path_to_wav_file)
        self.listener.read_metadata_complete(MetaData(episode_number=episode_number,
                                                      episode_title=episode_title,
                                                      chapters=chapters))

    def __read_metadata_from_mp3_file(self, path_to_mp3_file: str) -> None:
        self.listener.read_metadata_started()
        with open(path_to_mp3_file, "rb") as mp3_file:
            try:
                tags = id3.ID3(mp3_file)
            except id3.ID3NoHeaderError:
                tags = id3.ID3()

        podcast_title = self.__get_podcast_name_from_id3_tags(tags)
        episode_title = self.__get_episode_title_from_id3_tags(tags)
        episode_number = self.__get_episode_number_from_id3_tags(tags)
        chapters = self.__get_chapters_from_id3_tags(tags)

        self.listener.read_metadata_complete(MetaData(podcast_title=podcast_title,
                                                      episode_title=episode_title,
                                                      episode_number=episode_number,
                                                      chapters=chapters))

    def __read_chapters_from_wav_file(self, path_to_wav_file: str) -> List[Chapter]:
        wav_file = wave.open(path_to_wav_file)
        with open(path_to_wav_file, "rb") as fid:
            fsize: int = self.__read_riff_chunk(fid)
            markersdict: Dict[int, Dict[str, str]] = collections.defaultdict(
                lambda: {"timestamp": "", "label": ""})

            while fid.tell() < fsize:
                chunk_id: bytes = fid.read(4)
                if chunk_id == b"cue ":
                    str1: bytes = fid.read(8)
                    numcue: int = struct.unpack('<ii', str1)[1]
                    for _ in range(numcue):
                        str1 = fid.read(24)
                        cue_id, position = struct.unpack("<iiiiii", str1)[0:2]
                        markersdict[cue_id]["timestamp"] = str(
                            self.__samples_to_millis(wav_file, position))
                elif chunk_id == b"LIST":
                    fid.read(8)
                elif chunk_id == b"labl":
                    str1 = fid.read(8)
                    size, cue_id = struct.unpack("<ii", str1)
                    size = size + (size % 2)
                    label: bytes = fid.read(size - 4).rstrip(b"\x00")
                    markersdict[cue_id]["label"] = label.decode("utf-8")
                else:
                    self.__skip_unknown_chunk(fid)

        sorted_markers: List[Dict[str, str]] = sorted(
            [markersdict[l] for l in markersdict],
            key=lambda k: int(k["timestamp"]))

        chapters: List[Chapter] = list()
        num_chapters: int = len(sorted_markers)
        for idx, chap in enumerate(sorted_markers):
            if idx + 1 < num_chapters:
                next_timestamp = int(sorted_markers[idx + 1]["timestamp"])
            else:
                next_timestamp = self.__samples_to_millis(wav_file, wav_file.getnframes())

            chapters.append(Chapter(int(chap["timestamp"]), next_timestamp, chap["label"]))

        wav_file.close()
        return chapters

    def __write_metadata_to_file(self, metadata: MetaData, path_to_mp3_file: str) -> None:
        self.listener.write_mp3_file_started()
        if os.path.exists(path_to_mp3_file):
            tags = self.__get_tags(metadata)
            with open(path_to_mp3_file, "r+b") as mp3_file:
                tags.save(mp3_file)

        self.listener.write_mp3_file_complete(path_to_mp3_file)

    def __write_mp3_data_with_metadata(self, metadata: MetaData, path_to_output: str) -> None:
        self.listener.write_mp3_file_started()
        tags = self.__get_tags(metadata)
        tags.save(self.mp3_data)
        self.mp3_data.seek(0)
        total = len(self.mp3_data.getvalue())
        with open(path_to_output, "wb") as mp3_file:
            data = self.mp3_data.read(4096)
            while data:
                mp3_file.write(data)
                self.listener.write_mp3_file_progress(int(self.mp3_data.tell() * 100 / total))
                data = self.mp3_data.read(4096)

        self.listener.write_mp3_file_complete(path_to_output)

    def __copy_mp3_with_metadata(self, path_to_input_mp3: str, path_to_output_mp3: str, metadata: MetaData) -> None:
        self.listener.write_mp3_file_started()
        tags = self.__get_tags(metadata)
        if os.path.exists(path_to_input_mp3):
            total = os.path.getsize(path_to_input_mp3)
            with open(path_to_input_mp3, "rb") as input_mp3:
                with open(path_to_output_mp3, "w+b") as output_mp3:
                    data = input_mp3.read(4096)
                    while data:
                        output_mp3.write(data)
                        self.listener.write_mp3_file_progress(int(input_mp3.tell() * 100 / total))
                        data = input_mp3.read(4096)

                    tags.save(output_mp3)

        self.listener.write_mp3_file_complete(path_to_output_mp3)

    @staticmethod
    def __get_tags(metadata: MetaData) -> id3.ID3:
        tags = id3.ID3()

        if metadata.podcast_title:
            tags.add(id3.TPE1(encoding=id3.Encoding.LATIN1, text=metadata.podcast_title))

        if metadata.episode_title:
            tags.add(id3.TIT2(encoding=id3.Encoding.LATIN1, text=metadata.episode_title))

        if metadata.episode_number:
            tags.add(id3.TRCK(encoding=id3.Encoding.LATIN1, text=str(metadata.episode_number)))

        if metadata.chapters:
            toc: List[str] = [f"chp{index}" for index in range(len(metadata.chapters))]
            tags.add(id3.CTOC(encoding=id3.Encoding.LATIN1, element_id="toc",
                              flags=id3.CTOCFlags.TOP_LEVEL | id3.CTOCFlags.ORDERED,
                              child_element_ids=toc, sub_frames=[]))

            for idx, chapter in enumerate(metadata.chapters):
                tags.add(id3.CHAP(encoding=id3.Encoding.LATIN1, element_id=f"chp{idx}",
                                  start_time=chapter.start, end_time=chapter.end,
                                  sub_frames=[id3.TIT2(encoding=id3.Encoding.LATIN1, text=chapter.name)]))

        return tags

    @staticmethod
    def __get_podcast_name_from_id3_tags(tags: id3.ID3) -> Optional[str]:
        tpe1_tag: id3.TPE1 = tags.get("TPE1")
        if tpe1_tag and tpe1_tag.text:
            return tpe1_tag.text[0]
        else:
            return None

    @staticmethod
    def __get_episode_title_from_id3_tags(tags: id3.ID3) -> Optional[str]:
        tit2_tag: id3.TIT2 = tags.get("TIT2")
        if tit2_tag and tit2_tag.text:
            return tit2_tag.text[0]
        else:
            return None

    @staticmethod
    def __get_episode_number_from_id3_tags(tags: id3.ID3) -> Optional[int]:
        trck_tag: id3.TRCK = tags.get("TRCK")
        if trck_tag and trck_tag.text:
            return int(trck_tag.text[0])
        else:
            return None

    @staticmethod
    def __get_chapters_from_id3_tags(tags: id3.ID3) -> List[Chapter]:
        all_chap_tags: Dict[str, id3.CHAP] = dict()
        for tag in tags.getall("CHAP"):
            all_chap_tags[tag.element_id] = tag

        chapters: List[Chapter] = list()
        ctoc_tags: List[id3.CTOC] = tags.getall("CTOC")
        if ctoc_tags:
            chapter_ids: List[str] = ctoc_tags[0].child_element_ids
            for chapter_id in chapter_ids:
                chap_tag = all_chap_tags[chapter_id]
                chapter_tit2_tag = chap_tag.sub_frames.get("TIT2")
                if chapter_tit2_tag:
                    name = chapter_tit2_tag.text
                else:
                    name = ""

                chapters.append(Chapter(name=name,
                                        start=chap_tag.start_time,
                                        end=chap_tag.end_time))

        return chapters

    @staticmethod
    def __guess_podcast_info_from_filename(path_to_file: str) -> Union[Tuple, Tuple[int, str]]:
        basename = os.path.splitext(os.path.basename(path_to_file))[0]
        match_info = re.search("([0-9]{1,3}) *- *(.*)", basename)

        if match_info:
            return int(match_info.group(1)), match_info.group(2)
        else:
            return None, None  # empty tuple

    @staticmethod
    def __samples_to_millis(wav_file: Wave_read, samples: int) -> int:
        return int((samples / wav_file.getframerate()) * 1000)

    @staticmethod
    def __skip_unknown_chunk(fid: IO[bytes]) -> None:
        data = fid.read(4)
        size = struct.unpack('<i', data)[0]
        if bool(size & 1):
            size += 1

        fid.seek(size, 1)

    @staticmethod
    def __read_riff_chunk(fid: IO[bytes]) -> int:
        str1: bytes = fid.read(4)
        if str1 != b'RIFF':
            raise ValueError("Not a WAV file.")

        fsize: int = struct.unpack('<I', fid.read(4))[0] + 8
        str1 = fid.read(4)
        if str1 != b'WAVE':
            raise ValueError("Not a WAV file.")

        return fsize


class Chapter:
    def __init__(self, start: int = 0, end: int = 0, name: str = "") -> None:
        self.start: int = start
        self.end: int = end
        self.name: str = name


class MetaData(NamedTuple):
    podcast_title: Optional[str] = None
    episode_title: Optional[str] = None
    episode_number: Optional[int] = None
    chapters: Optional[List[Chapter]] = None


class AbstractLibChaptersListener(ABC):
    @abstractmethod
    def encode_started(self) -> None:
        ...

    @abstractmethod
    def encode_update(self, progress: int) -> None:
        ...

    @abstractmethod
    def encode_complete(self) -> None:
        ...

    @abstractmethod
    def read_metadata_started(self) -> None:
        ...

    @abstractmethod
    def read_metadata_complete(self, metadata: MetaData) -> None:
        ...

    @abstractmethod
    def write_mp3_file_started(self) -> None:
        ...

    @abstractmethod
    def write_mp3_file_progress(self, progress: int) -> None:
        ...

    @abstractmethod
    def write_mp3_file_complete(self, path_to_mp3: str) -> None:
        ...


class ApplicationVersion:
    def __init__(self, year: int, update: int) -> None:
        self.year = year
        self.update = update

    def is_older_than(self, other: ApplicationVersion) -> bool:
        if self.year < other.year:
            return True
        elif self.year == other.year and self.update < other.update:
            return True
        else:
            return False

    @staticmethod
    def parse(version: str) -> ApplicationVersion:
        year, update = version.split(".")
        return ApplicationVersion(int(year), int(update))

    # override
    def __str__(self) -> str:
        return f"{self.year}.{self.update}"


class UpdateChecker:
    def __init__(self, listener: AbstractUpdateCheckerListener) -> None:
        self.listener = listener

    def check_for_updates(self, current_version: ApplicationVersion) -> None:
        run_async(lambda: self.__check_for_updates(current_version))

    def __check_for_updates(self, current_version: ApplicationVersion) -> None:
        try:
            with urlopen("https://www.samhutchins.co.uk/software/chapters/latest") as update_file:
                latest_version = ApplicationVersion.parse(update_file.read())
        except HTTPError:
            latest_version = APPLICATION_VERSION

        if current_version.is_older_than(latest_version):
            self.listener.update_available()
        else:
            self.listener.no_update_available()


class AbstractUpdateCheckerListener(ABC):
    @abstractmethod
    def update_available(self) -> None:
        ...

    @abstractmethod
    def no_update_available(self) -> None:
        ...


class Prefs:
    def __init__(self) -> None:
        prefs_folder = Path(os.getenv("LOCALAPPDATA")) / "Chapters"
        if not prefs_folder.exists():
            prefs_folder.mkdir()

        self.prefs_pickle = prefs_folder / "prefs.pickle"

        self.prefs_dict: Dict[str, str] = dict()
        if self.prefs_pickle.exists():
            with open(self.prefs_pickle, "rb") as f:
                self.prefs_dict = pickle.load(f)

    def get_pref_open_dir(self) -> str:
        try:
            return self.prefs_dict["open_dir"]
        except KeyError:
            return str(Path.home())

    def set_pref_open_dir(self, path: str) -> None:
        self.prefs_dict["open_dir"] = path
        self.save_prefs()

    def get_pref_save_dir(self) -> str:
        try:
            return self.prefs_dict["save_dir"]
        except KeyError:
            return str(Path.home())

    def set_pref_save_dir(self, path: str) -> None:
        self.prefs_dict["save_dir"] = path
        self.save_prefs()

    def save_prefs(self):
        with open(self.prefs_pickle, "wb") as f:
            pickle.dump(self.prefs_dict, f)


def run_async(fn: Callable) -> None:
    thread = Thread(target=fn)
    thread.daemon = True
    thread.start()


#############
# Constants #
#############

APPLICATION_NAME = "Chapters"
APPLICATION_VERSION = ApplicationVersion(2019, 1)

HOMEPAGE = "https://www.samhutchins.co.uk/software/chapters/"
DOCUMENTATION = HOMEPAGE + "documentation/"
GITHUB = "https://github.com/samhutchins/Chapters/"
ISSUES = GITHUB + "issues"

################
# LAME wrapper #
################


class Lame:
    def __init__(self, listener: AbstractLibChaptersListener) -> None:
        self.listener = AggregateListener(listener)
        path_to_lame = Path(__file__).parent / "lib" / "lame.exe"

        self.command = [str(path_to_lame),
                        "-r",
                        "-m", "m",  # mono
                        "--bitwidth", "24",  # bit depth
                        "-s", "44100",  # sample rate
                        "-b", "64",  # bitrate
                        "-"]

    def encode(self, path_to_wav: str) -> BytesIO:
        num_cpu = os.cpu_count()
        with wave.open(path_to_wav, "rb") as wav_file:
            num_samples = self.make_multiple(wav_file.getnframes(), num_cpu)

        samples_per_thread = int(num_samples / num_cpu)
        output_chunks: List[BytesIO] = list()
        threads: List[Thread] = list()

        for i in range(num_cpu):
            wav_file = wave.open(path_to_wav, "rb")
            wav_file.setpos(samples_per_thread * i)
            output = BytesIO()
            output_chunks.append(output)
            thread_id = f"encoder-{i+1}"
            self.listener.add_id(thread_id)
            threads.append(Thread(target=self.encode_chunk,
                                  args=[thread_id, wav_file, samples_per_thread, output]))

        for thread in threads:
            thread.start()

        for thread in threads:
            thread.join()

        mp3_output = BytesIO()
        for chunk in output_chunks:
            mp3_output.write(chunk.getvalue())

        return mp3_output

    def encode_chunk(self, thread_id: str, file: Wave_read, total_samples_to_read: int, output: BytesIO) -> None:
        options = STARTUPINFO()
        options.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        options.wShowWindow = subprocess.SW_HIDE
        process = Popen(self.command, stdin=PIPE, stdout=PIPE, stderr=PIPE, startupinfo=options)

        read_data_thread = Thread(target=lambda: output.write(process.stdout.read()))
        read_data_thread.daemon = True
        read_data_thread.start()

        samples_to_read, samples_left = self.update_samples_to_read(total_samples_to_read, 1024)
        last_progress = 0
        while samples_left > 0:
            process.stdin.write(file.readframes(samples_to_read))

            progress = int((total_samples_to_read - samples_left) * 100 / total_samples_to_read)
            if progress != last_progress:
                self.listener.encode_update(thread_id, progress)
                last_progress = progress

            samples_to_read, samples_left = self.update_samples_to_read(samples_left, 1024)

        self.listener.encode_update(thread_id, 100)
        process.stdin.close()
        read_data_thread.join()
        process.stdout.close()
        process.stderr.close()
        file.close()

    @staticmethod
    def update_samples_to_read(samples_left: int, chunk_size: int) -> Tuple[int, int]:
        if samples_left > chunk_size:
            samples_to_read = chunk_size
            samples_left -= chunk_size
        else:
            samples_to_read = samples_left
            samples_left = 0

        return samples_to_read, samples_left

    @staticmethod
    def make_multiple(number: int, divisor: int) -> int:
        """
        Takes a number, and keeps adding 1 until it evenly divides into the divisor
        :param number: The number you want to evenly divide by the divisor
        :param divisor: The divisor
        :return: A number that's greater or equal to the input, and will evenly divide into the divisor
        """
        while number % divisor != 0:
            number += 1

        return number


class AggregateListener:
    def __init__(self, wrapped_listener: AbstractLibChaptersListener) -> None:
        self.wrapped_listener = wrapped_listener
        self.progress_dict: Dict[str, int] = dict()

    def add_id(self, thread_id: str) -> None:
        self.progress_dict[thread_id] = 0

    def encode_update(self, thread_id: str, progress: int) -> None:
        # CPython dicts happen to be thread safe for atomic operations
        self.progress_dict[thread_id] = progress
        values = self.progress_dict.values()
        avg_progress = int(sum(values) / len(values))
        self.wrapped_listener.encode_update(avg_progress)
