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

import os
import re
import sys
from typing import Any, List, Callable, NamedTuple, Optional

from PySide2.QtCore import Signal, QCoreApplication, QAbstractTableModel, QModelIndex, Qt, QObject
from PySide2.QtGui import QKeySequence
from PySide2.QtWidgets import QMainWindow, QLineEdit, QSpinBox, QTableView, QWidget, QVBoxLayout, \
    QFileDialog, QDialog, QApplication, QFormLayout, QProgressBar, QPushButton, QHBoxLayout, QTextBrowser

from libchapters import Chapter, MetaData, LibChapters, ApplicationVersion, Listener

APPLICATION_NAME = "Chapters"
APPLICATION_VERSION = ApplicationVersion(1, 0)


class MainWindow(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.lib_chapters = self.__create_libchapters()
        self.current_file: Optional[str] = None
        self.current_file_type: Optional[str] = None


        # UI components
        self.setWindowTitle(APPLICATION_NAME)
        self.setMinimumSize(480, 320)
        self.resize(900, 500)
        self.__create_menu()

        self.podcast_title = QLineEdit()
        self.episode_title = QLineEdit()
        self.episode_number = QSpinBox()
        self.episode_number.setMaximumWidth(55)

        self.chapters_table_view = QTableView()
        self.chapters_table_model = ChaptersTableModel(self.chapters_table_view)
        self.chapters_table_view.setModel(self.chapters_table_model)
        self.chapters_table_view.horizontalHeader().setStretchLastSection(True)

        self.add_chapter_button = QPushButton("Add")
        self.add_chapter_button.clicked.connect(self.chapters_table_model.add_chapter)

        self.delete_chapter_button = QPushButton("Delete")
        self.delete_chapter_button.clicked.connect(self.chapters_table_model.remove_selected_chapters)

        self.progress_bar = QProgressBar()

        self.setCentralWidget(self.__create_center_widget())

        self.__create_status_bar()

    def __create_libchapters(self) -> LibChapters:
        listener = LibChaptersListener()
        listener.signals.encode_started.connect(self.__encode_started)
        listener.signals.encode_progress.connect(self.__encode_progress)
        listener.signals.encode_complete.connect(self.__encode_complete)
        listener.signals.read_metadata_started.connect(self.__read_metadata_started)
        listener.signals.read_metadata_complete.connect(self.__read_metadata_complete)
        listener.signals.write_mp3_file_started.connect(self.__write_mp3_started)
        listener.signals.write_mp3_file_progress.connect(self.__write_mp3_progress)
        listener.signals.write_mp3_file_complete.connect(self.__write_mp3_complete)
        return LibChapters(listener)

    def __create_center_widget(self) -> QWidget:
        episode_info_layout = QFormLayout()
        episode_info_layout.addRow("Podcast Title:", self.podcast_title)
        episode_info_layout.addRow("Episode Title:", self.episode_title)
        episode_info_layout.addRow("Episode Number:", self.episode_number)

        add_remove_chapters_layout = QHBoxLayout()
        add_remove_chapters_layout.addWidget(self.add_chapter_button)
        add_remove_chapters_layout.addWidget(self.delete_chapter_button)
        add_remove_chapters_layout.setAlignment(Qt.AlignLeft)

        center_widget_layout = QVBoxLayout()
        center_widget_layout.addLayout(episode_info_layout)
        center_widget_layout.addWidget(self.chapters_table_view)
        center_widget_layout.addLayout(add_remove_chapters_layout)

        center_widget = QWidget()
        center_widget.setLayout(center_widget_layout)

        return center_widget

    def __create_menu(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")

        import_action = file_menu.addAction("Import Audio...")
        import_action.setShortcut(QKeySequence("Ctrl+I"))
        import_action.triggered.connect(self.__import_audio)

        open_file_action = file_menu.addAction("Open...")
        open_file_action.setShortcut(QKeySequence("Ctrl+O"))
        open_file_action.triggered.connect(self.__open_file)

        file_menu.addSeparator()

        save_action = file_menu.addAction("Save")
        save_action.setShortcut(QKeySequence("Ctrl+S"))
        save_action.triggered.connect(self.__save_current_file)

        save_as_action = file_menu.addAction("Save As...")
        save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_action.triggered.connect(self.__save_current_file_as)

        file_menu.addSeparator()

        exit_action = file_menu.addAction("Exit")
        exit_action.setShortcut(QKeySequence("Alt+f4"))
        exit_action.triggered.connect(QCoreApplication.quit)

        help_menu = menu_bar.addMenu("Help")
        help_action = help_menu.addAction("About")
        help_action.triggered.connect(self.__show_about_dialog)

    def __create_status_bar(self):
        status_bar = self.statusBar()
        status_bar.addPermanentWidget(self.progress_bar)

    def __import_audio(self):
        file, _ = QFileDialog.getOpenFileName(self, filter="*.wav")
        if file:
            self.__set_current_file(file, "wav")
            self.lib_chapters.read_metadata_from_wav_file(file)
            self.lib_chapters.encode_wav_file(file)

    def __open_file(self):
        file, _ = QFileDialog.getOpenFileName(self, filter="*.mp3")
        if file:
            self.__set_current_file(file, "mp3")
            self.lib_chapters.read_metadata_from_mp3_file(file)

    def __encode_started(self):
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("Importing file...")

    def __encode_progress(self, progress: int):
        self.progress_bar.setValue(progress)

    def __encode_complete(self):
        self.centralWidget().setDisabled(False)
        self.menuBar().setDisabled(False)
        self.statusBar().showMessage("Import complete")

    def __read_metadata_started(self):
        self.chapters_table_view.setDisabled(True)

    def __read_metadata_complete(self, metadata: MetaData):
        self.chapters_table_view.setDisabled(False)
        if metadata.podcast_title:
            self.podcast_title.setText(metadata.podcast_title)
        else:
            self.podcast_title.clear()

        if metadata.episode_title:
            self.episode_title.setText(metadata.episode_title)
        else:
            self.episode_title.clear()

        if metadata.episode_number:
            self.episode_number.setValue(metadata.episode_number)
        else:
            self.episode_number.clear()

        if metadata.chapters:
            self.chapters_table_model.set_chapters(metadata.chapters)
        else:
            self.chapters_table_model.clear_chapters()

    def __save_current_file(self):
        if self.current_file:
            meta_data = MetaData(
                podcast_title=self.podcast_title.text(),
                episode_title=self.episode_title.text(),
                episode_number=self.episode_number.value(),
                chapters=self.chapters_table_model.get_chapters())

            if self.current_file_type == "wav":
                output_file, _ = QFileDialog.getSaveFileName(self, filter="*.mp3")
                if output_file:
                    self.lib_chapters.write_mp3_data_with_metadata(meta_data, output_file)
            elif self.current_file_type == "mp3":
                self.lib_chapters.write_metadata_to_file(meta_data, self.current_file)

    def __save_current_file_as(self):
        if self.current_file:
            output_file, _ = QFileDialog.getSaveFileName(self, filter="*.mp3")
            if output_file:
                meta_data = MetaData(
                    podcast_title=self.podcast_title.text(),
                    episode_title=self.episode_title.text(),
                    episode_number=self.episode_number.value(),
                    chapters=self.chapters_table_model.get_chapters())

                if self.current_file_type == "wav":
                    self.lib_chapters.write_mp3_data_with_metadata(meta_data, output_file)
                elif self.current_file_type == "mp3":
                    self.lib_chapters.copy_mp3_with_metadata(self.current_file, output_file, meta_data)

    def __write_mp3_started(self):
        self.menuBar().setDisabled(True)
        self.centralWidget().setDisabled(True)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("Saving MP3...")

    def __write_mp3_progress(self, progress: int):
        self.progress_bar.setValue(progress)

    def __write_mp3_complete(self, path_to_mp3: str):
        self.menuBar().setDisabled(False)
        self.centralWidget().setDisabled(False)
        self.__set_current_file(path_to_mp3, "mp3")
        self.statusBar().showMessage("Save complete")

    def __show_about_dialog(self):
        about_dialog = AboutDialog(self)
        about_dialog.show()

    def __set_current_file(self, current_file: str, current_file_type: str):
        self.current_file = current_file
        self.current_file_type = current_file_type
        self.setWindowTitle(f"{APPLICATION_NAME} - {os.path.basename(current_file)}")


class ChaptersTableModel(QAbstractTableModel):
    def __init__(self, table_view: QTableView):
        QAbstractTableModel.__init__(self)
        self.table_view = table_view
        self.__chapters: List[Chapter] = list()
        self.__columns: List[TableColumn] = [
            TableColumn("Start Time", self.__get_start(False), self.__get_start(True), self.__set_start),
            TableColumn("End Time", self.__get_end(False), self.__get_end(True), self.__set_end),
            TableColumn("Name", self.__get_name, self.__get_name, self.__set_name)
        ]

    def set_chapters(self, chapters: List[Chapter]):
        self.clear_chapters()
        self.beginInsertRows(QModelIndex(), 0, len(chapters) - 1)
        self.__chapters = list(chapters)
        self.endInsertRows()

    def add_chapter(self):
        self.beginInsertRows(QModelIndex(), len(self.__chapters) - 1, len(self.__chapters) - 1)
        self.__chapters.append(Chapter())
        self.endInsertRows()

    def remove_selected_chapters(self):
        selected_indexes: List[QModelIndex] = self.table_view.selectedIndexes()
        rows: List[int] = [index.row() for index in selected_indexes]
        rows.sort(reverse=True)
        for row in rows:
            if row < len(self.__chapters):
                self.beginRemoveRows(QModelIndex(), row, row)
                del self.__chapters[row]
                self.endRemoveRows()

    def clear_chapters(self):
        self.beginRemoveRows(QModelIndex(), 0, len(self.__chapters) - 1)
        self.__chapters = list()
        self.endRemoveRows()

    def get_chapters(self) -> List[Chapter]:
        return list(self.__chapters)

    # override
    def rowCount(self, parent: QModelIndex = ...) -> int:
        return len(self.__chapters)

    # override
    def columnCount(self, parent: QModelIndex = ...) -> int:
        return len(self.__columns)

    # override
    def headerData(self, section: int, orientation: Qt.Orientation, role: int = ...) -> Any:
        if role == Qt.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                column = self.__columns[section]
                return column.title
            else:
                return section + 1
        elif role == Qt.TextAlignmentRole:
            return Qt.AlignCenter
        else:
            return None

    # override
    def flags(self, index: QModelIndex) -> Qt.ItemFlags:
        return Qt.ItemIsEnabled | Qt.ItemIsSelectable | Qt.ItemIsEditable

    # override
    def data(self, index: QModelIndex, role: int = ...) -> Any:
        column = self.__columns[index.column()]
        if role == Qt.DisplayRole:
            return column.get_data(self.__chapters[index.row()])
        elif role == Qt.EditRole:
            return column.get_edit_data(self.__chapters[index.row()])
        elif role == Qt.TextAlignmentRole:
            return Qt.AlignVCenter
        else:
            return None

    def setData(self, index: QModelIndex, value: str, role: int = ...) -> bool:
        if role == Qt.EditRole:
            chapter = self.__chapters[index.row()]
            self.__columns[index.column()].set_data(chapter, value)
            self.dataChanged.emit(index.row(), index.column())
            return True
        else:
            return False

    def __get_start(self, for_edit: bool) -> Callable[[Chapter], str]:
        return lambda chapter: self.__format_timestamp(chapter.start, for_edit)

    def __set_start(self, chapter: Chapter, new_start: str):
        parsed = self.__parse_timestamp(new_start)
        if parsed:
            chapter.start = parsed

    def __get_end(self, for_edit: bool) -> Callable[[Chapter], str]:
        return lambda chapter: self.__format_timestamp(chapter.end, for_edit)

    def __set_end(self, chapter: Chapter, new_end: str):
        parsed = self.__parse_timestamp(new_end)
        if parsed:
            chapter.end = parsed

    @staticmethod
    def __get_name(chapter: Chapter) -> str:
        return chapter.name

    @staticmethod
    def __set_name(chapter: Chapter, new_name: str):
        chapter.name = new_name

    milliseconds_in_hour = 3600000
    milliseconds_in_minute = 60000
    milliseconds_in_second = 1000

    def __format_timestamp(self, timestamp_millis: int, include_millis: bool) -> str:
        hours, remainder = divmod(timestamp_millis, self.milliseconds_in_hour)
        minutes, remainder = divmod(remainder, self.milliseconds_in_minute)
        seconds, milliseconds = divmod(remainder, self.milliseconds_in_second)

        if include_millis:
            return "{:02}:{:02}:{:02}.{:03}".format(hours, minutes, seconds, milliseconds)
        else:
            return "{:02}:{:02}:{:02}".format(hours, minutes, seconds)

    def __parse_timestamp(self, timestamp: str) -> Optional[int]:
        match_info = re.search("([0-9]{1,2}):([0-5]?[0-9]):([0-5]?[0-9])(\\.[0-9]{1,3})?", timestamp)
        if match_info:
            hours = int(match_info.group(1))
            minutes = int(match_info.group(2))
            seconds = int(match_info.group(3))
            millis_str = match_info.group(4)
            if millis_str:
                milliseconds = int(millis_str[1:])
            else:
                milliseconds = 0

            return (hours * self.milliseconds_in_hour) + \
                   (minutes * self.milliseconds_in_minute) + \
                   (seconds * self.milliseconds_in_second) + milliseconds
        else:
            return None


class AboutDialog(QDialog):
    def __init__(self, parent: MainWindow):
        QDialog.__init__(self, parent, Qt.WindowCloseButtonHint)
        self.setWindowTitle("About")
        self.resize(400, 200)

        text_browser = QTextBrowser()
        text_browser.setHtml(f"""<h1>{APPLICATION_NAME}</h1>
            <p>
            <a href="https://www.samhutchins.co.uk/software/chapters/">{APPLICATION_NAME}</a> version {APPLICATION_VERSION}, released under GPLv3. Source code can be found on <a href="https://github.com/samhutchins/Chapters">GitHub</a>.
            </p>
            <p>
            Found a bug? <a href="https://twitter.com/_samhutchins">Tweet at me</a>!
            </p>""")

        text_browser.setOpenExternalLinks(True)

        ok_button = QPushButton("OK")
        ok_button.clicked.connect(self.close)
        button_layout = QHBoxLayout()
        button_layout.setAlignment(Qt.AlignRight)
        button_layout.addWidget(ok_button)

        layout = QVBoxLayout()
        layout.addWidget(text_browser)
        layout.addLayout(button_layout)
        self.setLayout(layout)

    # override
    def show(self):
        super().show()
        self.raise_()
        self.activateWindow()


class TableColumn(NamedTuple):
    title: str
    get_data: Callable[[Chapter], str]
    get_edit_data: Callable[[Chapter], str]
    set_data: Callable[[Chapter, str], None]


class EncoderListenerSignals(QObject):
    encode_started = Signal()
    encode_progress = Signal(int)
    encode_complete = Signal()
    read_metadata_started = Signal()
    read_metadata_complete = Signal(object)  # MetaData
    write_mp3_file_started = Signal()
    write_mp3_file_progress = Signal(int)
    write_mp3_file_complete = Signal(str)


class LibChaptersListener(Listener):
    signals = EncoderListenerSignals()

    def encode_started(self):
        self.signals.encode_started.emit()

    def encode_update(self, progress: int):
        self.signals.encode_progress.emit(progress)

    def encode_complete(self):
        self.signals.encode_complete.emit()

    def read_metadata_started(self):
        self.signals.read_metadata_started.emit()

    def read_metadata_complete(self, metadata: MetaData):
        self.signals.read_metadata_complete.emit(metadata)

    def write_mp3_file_started(self):
        self.signals.write_mp3_file_started.emit()

    def write_mp3_file_progress(self, progress: int):
        self.signals.write_mp3_file_progress.emit(progress)

    def write_mp3_file_complete(self, path_to_mp3: str):
        self.signals.write_mp3_file_complete.emit(path_to_mp3)


if __name__ == "__main__":
    app = QApplication(sys.argv)

    main_window = MainWindow()
    main_window.show()

    sys.exit(app.exec_())
