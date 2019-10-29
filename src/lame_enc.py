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

import pathlib
import wave
from ctypes import *
from io import BytesIO
from wave import Wave_read

BE_CONFIG_MP3 = 0
BE_MP3_MODE_MONO = 3


class BE_CONFIG(Structure):
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
    def __init__(self):
        dll_path = pathlib.Path(__file__).parent / ".." / "lib" / "lame_enc.dll"
        self.lame_dll = WinDLL(str(dll_path))

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
        mp3_buffer = create_string_buffer(mp3_buf_size.value)
        # 24 bit depth input, so 3 bytes per sample
        bytes_per_sample = 3

        mp3_data = BytesIO()
        while True:
            wav_data: bytes = file.readframes(samples_per_chunk.value)
            if not wav_data:
                deinit_error = self.lame_dll.beDeinitStream(stream, byref(mp3_buffer), byref(mp3_bytes))
                if not deinit_error and mp3_bytes != 0:
                    mp3_data.write(mp3_buffer.raw[0:mp3_bytes.value])  # TODO typing
                    print("Done!")

                break

            # wav_buffer = (c_short * (samples_per_chunk.value * bytes_per_sample))(*wav_data)
            wav_buffer = create_string_buffer(wav_data, samples_per_chunk.value * bytes_per_sample)

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


if __name__ == "__main__":
    encoder = Lame()
    wav = wave.open("test.wav", "r")
    mp3 = open("test2.mp3", "wb")
    mp3.write(encoder.encode(wav).getvalue())
    wav.close()
    mp3.close()
