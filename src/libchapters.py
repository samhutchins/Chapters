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

import collections
import os
import re
import struct
import wave
from io import BytesIO
from subprocess import Popen, PIPE
from typing import List, Dict, IO, NamedTuple, Optional
from wave import Wave_read

from mutagen import id3

from lame_enc import Lame


class Chapter(NamedTuple):
    start: int
    end: int
    name: str


class MetaData(NamedTuple):
    podcast_title: Optional[str] = None
    episode_title: Optional[str] = None
    episode_number: Optional[int] = None
    chapters: Optional[List[Chapter]] = None


class LibChapters:
    def encode_podcast(self, path_to_wav_file: str, meta_data: MetaData) -> BytesIO:
        wav_file = wave.open(path_to_wav_file)
        audio_data: BytesIO = self.__encode(wav_file)
        wav_file.close()

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

        tags.save(audio_data)

        return audio_data

    def read_chapters(self, path_to_wav_file: str) -> List[Chapter]:
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

        ret: List[Chapter] = list()
        num_chapters: int = len(sorted_markers)
        for idx, chap in enumerate(sorted_markers):
            if idx + 1 < num_chapters:
                next_timestamp = int(sorted_markers[idx + 1]["timestamp"])
            else:
                next_timestamp = self.__samples_to_millis(wav_file, wav_file.getnframes())

            ret.append(Chapter(int(chap["timestamp"]), next_timestamp, chap["label"]))

        wav_file.close()
        return ret

    @staticmethod
    def guess_podcast_info(path_to_wav: str) -> MetaData:
        basename = os.path.splitext(os.path.basename(path_to_wav))[0]
        match_info = re.search("([0-9]{1,3}) *- *(.*)", basename)

        return MetaData(
            episode_number=int(match_info.group(1)),
            episode_title=match_info.group(2))

    @staticmethod
    def __encode(wav_file: Wave_read) -> BytesIO:
        lame = Lame()
        return lame.encode(wav_file)

        # TODO threading
        # num_cpu = os.cpu_count() if not None else 4
        # bit_depth = wav_file.getsampwidth() * 8
        # sample_rate = wav_file.getframerate()
        # num_samples = wav_file.getnframes()
        # samples_per_chunk = int(LibChapters.__round_up(num_samples, num_cpu) / num_cpu)
        # output_chunks: List[BytesIO] = list()
        # threads: List[Thread] = list()
        #
        # for i in range(num_cpu):
        #     wav_file.setpos(samples_per_chunk * i)
        #     chunk = wav_file.readframes(samples_per_chunk)
        #     output_chunk = BytesIO()
        #     output_chunks.append(output_chunk)
        #     threads.append(Thread(
        #         target=self.__encode_chunk,
        #         args=(chunk, output_chunk, bit_depth, sample_rate)
        #     ))
        #
        # for thread in threads:
        #     thread.start()
        #
        # for thread in threads:
        #     thread.join()
        #
        # output_bytes = BytesIO()
        # for chunk in output_chunks:
        #     output_bytes.write(chunk.getvalue())
        #     chunk.close()
        #
        # return output_bytes

    @staticmethod
    def __encode_chunk(chunk: bytes, output: BytesIO, bit_depth: int, sample_rate: int) -> None:
        command: List[str] = ['lame',
                              '-r',
                              '-m', 'm',
                              '--bitwidth', str(bit_depth),
                              '-s', str(sample_rate),
                              '-']
        process: Popen = Popen(command, stdin=PIPE, stdout=PIPE, stderr=PIPE)
        mp3_data: bytes = process.communicate(chunk)[0]
        output.write(mp3_data)

    @staticmethod
    def __round_up(num: int, target_mutliple: int) -> int:
        while num % target_mutliple != 0:
            num += 1

        return num

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
