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

from typing import NamedTuple


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
