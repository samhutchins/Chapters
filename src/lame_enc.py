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

import wave

from libchapters import Lame

if __name__ == "__main__":
    encoder = Lame()
    wav = wave.open("test.wav", "r")
    mp3 = open("test2.mp3", "wb")
    mp3.write(encoder.encode(wav).getvalue())
    wav.close()
    mp3.close()
