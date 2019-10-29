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
import ctypes
import os
import re
import struct
import wave
from abc import ABC, abstractmethod
from ctypes import c_ulong, c_byte, c_ushort, c_long, WinDLL, c_void_p, byref
from io import BytesIO
from pathlib import Path
from threading import Thread
from typing import List, Dict, IO, NamedTuple, Optional, BinaryIO
from wave import Wave_read

from mutagen import id3

__all__ = ["ApplicationVersion",
           "Chapter",
           "MetaData",
           "LibChapters",
           "Listener"]


class LibChapters:
    def __init__(self, listener: Listener):
        self.listener = listener

    def encode_file(self, path_to_wav_file: str):
        thread = Thread(target=lambda: self.__encode_file(path_to_wav_file),
                        daemon=True)
        thread.start()

    def read_chapters(self, path_to_wav_file: str):
        thread = Thread(target=lambda: self.__read_chapters(path_to_wav_file),
                        daemon=True)
        thread.start()

    def add_metadata(self, mp3_file: BinaryIO, meta_data: MetaData):
        thread = Thread(target=lambda: self.__add_metadata(mp3_file, meta_data),
                        daemon=True)
        thread.start()

    def write_mp3_data(self, mp3_data: BytesIO, path_to_output: str):
        thread = Thread(target=lambda: self.__write_mp3_data(mp3_data, path_to_output),
                        daemon=True)
        thread.start()

    @staticmethod
    def guess_podcast_info(path_to_wav: str) -> MetaData:
        basename = os.path.splitext(os.path.basename(path_to_wav))[0]
        match_info = re.search("([0-9]{1,3}) *- *(.*)", basename)

        if match_info:
            return MetaData(
                episode_number=int(match_info.group(1)),
                episode_title=match_info.group(2))
        else:
            return MetaData()

    def __encode_file(self, path_to_wav_file: str):
        self.listener.encode_started()
        lame = Lame(self.listener)
        with wave.open(path_to_wav_file) as wav_file:
            audio_data: BytesIO = lame.encode(wav_file)
        self.listener.encode_complete(audio_data)

    def __read_chapters(self, path_to_wav_file: str):
        self.listener.read_chapters_started()
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
        self.listener.read_chapters_complete(chapters)

    def __add_metadata(self, mp3_data: BinaryIO, meta_data: MetaData):
        self.listener.add_metadata_started()
        tags = id3.ID3()

        if meta_data.podcast_title:
            tags.add(id3.TPE1(encoding=id3.Encoding.LATIN1, text=meta_data.podcast_title))

        if meta_data.episode_title:
            tags.add(id3.TIT2(encoding=id3.Encoding.LATIN1, text=meta_data.episode_title))

        if meta_data.episode_number:
            tags.add(id3.TRCK(encoding=id3.Encoding.LATIN1, text=str(meta_data.episode_number)))

        if meta_data.chapters:
            toc: List[str] = [f"chp{index}" for index in range(len(meta_data.chapters))]
            tags.add(id3.CTOC(encoding=id3.Encoding.LATIN1, element_id="toc",
                              flags=id3.CTOCFlags.TOP_LEVEL | id3.CTOCFlags.ORDERED,
                              child_element_ids=toc, sub_frames=[]))

            for idx, chapter in enumerate(meta_data.chapters):
                tags.add(id3.CHAP(encoding=id3.Encoding.LATIN1, element_id=f"chp{idx}",
                                  start_time=chapter.start, end_time=chapter.end,
                                  sub_frames=[id3.TIT2(encoding=id3.Encoding.LATIN1, text=chapter.name)]))

        tags.save(mp3_data)
        self.listener.add_metadata_complete()

    def __write_mp3_data(self, mp3_data: BytesIO, path_to_output: str):
        self.listener.write_mp3_file_started()
        mp3_data.seek(0)
        total = len(mp3_data.getvalue())
        with open(path_to_output, "wb") as mp3_file:
            data = mp3_data.read(4096)
            while data:
                mp3_file.write(data)
                self.listener.write_mp3_file_progress(int(mp3_data.tell() * 100 / total))
                data = mp3_data.read(4096)

        self.listener.write_mp3_file_complete()

    @staticmethod
    def __samples_to_millis(wav_file: Wave_read, samples: int) -> int:
        return int((samples / wav_file.getframerate()) * 1000)

    @staticmethod
    def __skip_unknown_chunk(fid: IO[bytes]):
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


class Chapter(NamedTuple):
    start: int
    end: int
    name: str


class MetaData(NamedTuple):
    podcast_title: Optional[str] = None
    episode_title: Optional[str] = None
    episode_number: Optional[int] = None
    chapters: Optional[List[Chapter]] = None


class Listener(ABC):
    @abstractmethod
    def encode_started(self):
        ...

    @abstractmethod
    def encode_update(self, progress: int):
        ...

    @abstractmethod
    def encode_complete(self, result: BytesIO):
        ...

    @abstractmethod
    def read_chapters_started(self):
        ...

    @abstractmethod
    def read_chapters_complete(self, chapters: List[Chapter]):
        ...

    @abstractmethod
    def add_metadata_started(self):
        ...

    @abstractmethod
    def add_metadata_complete(self):
        ...

    @abstractmethod
    def write_mp3_file_started(self):
        ...

    @abstractmethod
    def write_mp3_file_progress(self, progress: int):
        ...

    @abstractmethod
    def write_mp3_file_complete(self):
        ...


class ApplicationVersion(NamedTuple):
    major: int
    minor: int

    def is_older_than(self, other: ApplicationVersion) -> bool:
        if self.major < other.major:
            return True
        elif self.major == other.major and self.minor < other.minor:
            return True
        else:
            return False

    # override
    def __str__(self):
        return f"{self.major}.{self.minor}"


################
# LAME wrapper #
################


BE_CONFIG_MP3 = 0
BE_MP3_MODE_MONO = 3


class BE_CONFIG(ctypes.Structure):
    _fields_ = [
        ("dwConfig", c_ulong),
        ("dwSampleRate", c_ulong),
        ("byMode", c_byte),
        ("wBitrate", c_ushort),
        ("bPrivate", c_long),
        ("bCRC", c_long),
        ("bCopyright", c_long),
        ("bOriginal", c_long)
    ]

    _packed_ = 1


class Lame:
    def __init__(self, listener: Listener):
        dll_path = Path(__file__).parent / ".." / "lib" / "lame_enc.dll"
        self.lame_dll = WinDLL(str(dll_path))
        self.listener = listener

    def encode(self, file: Wave_read) -> BytesIO:
        config = self.__config(file)
        samples_per_chunk = c_ulong()
        mp3_buf_size = c_ulong()
        stream = c_void_p()
        init_error = self.lame_dll.beInitStream(
            byref(config),
            byref(samples_per_chunk),
            byref(mp3_buf_size),
            byref(stream))

        if init_error:
            # TODO Handle failure properly
            print(f"Error during init: {init_error}")

        mp3_bytes = c_ulong()
        mp3_buffer = ctypes.create_string_buffer(mp3_buf_size.value)
        # 24 bit depth input, so 3 bytes per sample
        bytes_per_sample = 3

        mp3_data = BytesIO()
        while True:
            wav_data: bytes = file.readframes(samples_per_chunk.value)
            if not wav_data:
                deinit_error = self.lame_dll.beDeinitStream(stream, byref(mp3_buffer), byref(mp3_bytes))
                if not deinit_error and mp3_bytes != 0:
                    mp3_data.write(mp3_buffer.raw[0:mp3_bytes.value])

                break

            # wav_buffer = (c_short * (samples_per_chunk.value * bytes_per_sample))(*wav_data)
            wav_buffer = ctypes.create_string_buffer(wav_data, samples_per_chunk.value * bytes_per_sample)

            encode_error = self.lame_dll.beEncodeChunk(
                stream,
                int(len(wav_data) / bytes_per_sample),
                byref(wav_buffer),
                byref(mp3_buffer),
                byref(mp3_bytes))

            if encode_error:
                print(f"Encoder error: {encode_error}")
                break

            mp3_data.write(mp3_buffer.raw[0:mp3_bytes.value])
            self.listener.encode_update(int(file.tell() * 100 / file.getnframes()))

        self.lame_dll.beCloseStream(stream)

        return mp3_data

    @staticmethod
    def __config(wav_file: Wave_read) -> BE_CONFIG:
        config = BE_CONFIG()
        config.dwConfig = BE_CONFIG_MP3
        config.dwSampleRate = wav_file.getframerate()
        config.byMode = BE_MP3_MODE_MONO  # TODO Mono for now
        config.bitrate = 64
        config.bPrivate = False
        config.bCRC = True
        config.bCopyright = False
        config.bOriginal = True

        return config
