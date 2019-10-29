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

import datetime
import os
import sys
from io import BytesIO
from typing import Any, List, Callable, NamedTuple, Optional, BinaryIO

from PySide2.QtCore import Signal, QCoreApplication, QAbstractTableModel, QModelIndex, Qt, QObject
from PySide2.QtGui import QKeySequence
from PySide2.QtWidgets import QMainWindow, QLineEdit, QSpinBox, QTableView, QWidget, QLabel, QVBoxLayout, \
    QFileDialog, QDialog, QApplication, QFormLayout, QProgressBar

from libchapters import Chapter, MetaData, LibChapters, ApplicationVersion, Listener

APPLICATION_NAME = "Chapters"
APPLICATION_VERSION = ApplicationVersion(1, 0)


class MainWindow(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.lib_chapters = self.__create_libchapters()
        self.current_file: Optional[BinaryIO] = None

        self.chapters_table_model = ChaptersTableModel()

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
        self.chapters_table_view.setModel(self.chapters_table_model)
        self.chapters_table_view.horizontalHeader().setStretchLastSection(True)

        self.progress_bar = QProgressBar()

        self.setCentralWidget(self.__create_center_widget())

        self.__create_status_bar()

    def __create_libchapters(self) -> LibChapters:
        listener = LibChaptersListener()
        listener.signals.encode_started.connect(self.__encode_started)
        listener.signals.encode_progress.connect(self.__encode_progress)
        listener.signals.encode_complete.connect(self.__encode_complete)
        listener.signals.read_chapters_started.connect(self.__read_chapters_started)
        listener.signals.read_chapters_complete.connect(self.__read_chapters_complete)
        listener.signals.add_metadata_started.connect(self.__add_metadata_started)
        listener.signals.add_metadata_complete.connect(self.__add_metadata_complete)
        listener.signals.write_mp3_file_started.connect(self.__write_mp3_started)
        listener.signals.write_mp3_file_progress.connect(self.__write_mp3_progress)
        listener.signals.write_mp3_file_complete.connect(self.__write_mp3_complete)
        return LibChapters(listener)

    def __create_center_widget(self) -> QWidget:
        episode_info_pane = QFormLayout()
        episode_info_pane.addRow("Podcast Title:", self.podcast_title)
        episode_info_pane.addRow("Episode Title:", self.episode_title)
        episode_info_pane.addRow("Episode Number:", self.episode_number)

        center_widget_layout = QVBoxLayout()
        center_widget_layout.addLayout(episode_info_pane)
        center_widget_layout.addWidget(self.chapters_table_view)
        center_widget = QWidget()
        center_widget.setLayout(center_widget_layout)

        return center_widget

    def __create_menu(self):
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        import_action = file_menu.addAction("Import Audio...")
        import_action.setShortcut(QKeySequence("Ctrl+I"))
        import_action.triggered.connect(self.__import_audio)

        save_as_action = file_menu.addAction("Save As...")
        save_as_action.setShortcut(QKeySequence("Ctrl+Shift+S"))
        save_as_action.triggered.connect(self.__save_current_file)

        file_menu.addSeparator()

        exit_action = file_menu.addAction("Exit")
        exit_action.setShortcut(QKeySequence("Alt+f4"))
        exit_action.triggered.connect(QCoreApplication.quit)

        help_menu = menu_bar.addMenu("Help")
        help_action = help_menu.addAction("About")
        help_action.setShortcut(QKeySequence("F1"))
        help_action.triggered.connect(self.__show_about_dialog)

    def __create_status_bar(self):
        status_bar = self.statusBar()
        status_bar.addPermanentWidget(self.progress_bar)

    def __import_audio(self):
        file, _ = QFileDialog.getOpenFileName(self, filter="*.wav")
        if file:
            self.setWindowTitle(f"{APPLICATION_NAME} [{os.path.basename(file)}]")
            guessed_metadata = self.lib_chapters.guess_podcast_info(file)
            if guessed_metadata.podcast_title:
                self.podcast_title.setText(guessed_metadata.podcast_title)

            if guessed_metadata.episode_title:
                self.episode_title.setText(guessed_metadata.episode_title)

            if guessed_metadata.episode_number:
                self.episode_number.setValue(guessed_metadata.episode_number)

            self.lib_chapters.read_chapters(file)
            self.lib_chapters.encode_file(file)

    def __encode_started(self):
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("Importing file...")

    def __encode_progress(self, progress: int):
        self.progress_bar.setValue(progress)

    def __encode_complete(self, mp3_data: BytesIO):
        self.centralWidget().setDisabled(False)
        self.menuBar().setDisabled(False)
        self.statusBar().showMessage("Import complete")
        self.current_file = mp3_data

    def __read_chapters_started(self):
        self.chapters_table_view.setDisabled(True)

    def __read_chapters_complete(self, chapters: List[Chapter]):
        self.chapters_table_view.setDisabled(False)
        self.chapters_table_model.set_chapters(chapters)

    def __save_current_file(self):
        if self.current_file:
            meta_data = MetaData(
                podcast_title=self.podcast_title.text(),
                episode_title=self.episode_title.text(),
                episode_number=self.episode_number.value(),
                chapters=self.chapters_table_model.get_chapters())

            self.lib_chapters.add_metadata(self.current_file, meta_data)

    def __add_metadata_started(self):
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("Adding metadata...")

    def __add_metadata_complete(self):
        if isinstance(self.current_file, BytesIO):
            file, _ = QFileDialog.getSaveFileName(self, filter="*.mp3")
            if file:
                self.lib_chapters.write_mp3_data(self.current_file, file)
        else:
            self.progress_bar.setValue(100)
            print("Save complete")

    def __write_mp3_started(self):
        self.menuBar().setDisabled(True)
        self.centralWidget().setDisabled(True)
        self.progress_bar.setValue(0)
        self.statusBar().showMessage("Saving MP3...")

    def __write_mp3_progress(self, progress: int):
        self.progress_bar.setValue(progress)

    def __write_mp3_complete(self):
        self.menuBar().setDisabled(False)
        self.centralWidget().setDisabled(False)
        self.statusBar().showMessage("Save complete")

    def __show_about_dialog(self):
        about_dialog = AboutDialog(self)
        about_dialog.show()


class ChaptersTableModel(QAbstractTableModel):
    def __init__(self):
        QAbstractTableModel.__init__(self)
        self.__chapters: List[Chapter] = list()
        self.__columns: List[TableColumn] = [
            TableColumn("Start Time", lambda chapter: str(datetime.timedelta(seconds=int(chapter.start / 1000)))),
            TableColumn("End Time", lambda chapter: str(datetime.timedelta(seconds=int(chapter.end / 1000)))),
            TableColumn("Name", lambda chapter: chapter.name)
        ]

    def set_chapters(self, chapters: List[Chapter]):
        self.clear_chapters()
        self.beginInsertRows(QModelIndex(), 0, len(chapters) - 1)
        self.__chapters = list(chapters)
        self.endInsertRows()

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
    def data(self, index: QModelIndex, role: int = ...) -> Any:
        column = self.__columns[index.column()]
        if role == Qt.DisplayRole:
            return column.get_data(self.__chapters[index.row()])
        elif role == Qt.TextAlignmentRole:
            return column.alignment
        else:
            return None

    # override
    def headerData(self, section: int, orientation: Qt.Orientation, role: int = ...) -> Any:
        if role == Qt.DisplayRole:
            if orientation == Qt.Orientation.Horizontal:
                column = self.__columns[section]
                return column.title
            else:
                return section
        elif role == Qt.TextAlignmentRole:
            return Qt.AlignCenter
        else:
            return None


class AboutDialog(QDialog):
    def __init__(self, parent: MainWindow):
        QDialog.__init__(self, parent, Qt.WindowCloseButtonHint)
        self.setWindowTitle("About")
        self.resize(400, 200)

        layout = QVBoxLayout()
        layout.addWidget(QLabel(f"{APPLICATION_NAME} version {APPLICATION_VERSION}"))
        layout.addWidget(QLabel("Licenced GPLv3"))
        layout.addStretch()
        self.setLayout(layout)

    # override
    def show(self):
        super().show()
        self.raise_()
        self.activateWindow()


class TableColumn(NamedTuple):
    title: str
    get_data: Callable[[Chapter], str]
    alignment: int = Qt.AlignVCenter


class EncoderListenerSignals(QObject):
    encode_started = Signal()
    encode_progress = Signal(int)
    encode_complete = Signal(object)  # BytesIO
    read_chapters_started = Signal()
    read_chapters_complete = Signal(object)  # List[Chapter]
    add_metadata_started = Signal()
    add_metadata_complete = Signal()
    write_mp3_file_started = Signal()
    write_mp3_file_progress = Signal(int)
    write_mp3_file_complete = Signal()


class LibChaptersListener(Listener):
    signals = EncoderListenerSignals()

    def encode_started(self):
        self.signals.encode_started.emit()

    def encode_update(self, progress: int):
        self.signals.encode_progress.emit(progress)

    def encode_complete(self, result: BytesIO):
        self.signals.encode_complete.emit(result)

    def read_chapters_started(self):
        self.signals.read_chapters_started.emit()

    def read_chapters_complete(self, chapters: List[Chapter]):
        self.signals.read_chapters_complete.emit(chapters)

    def add_metadata_started(self):
        self.signals.add_metadata_started.emit()

    def add_metadata_complete(self):
        self.signals.add_metadata_complete.emit()

    def write_mp3_file_started(self):
        self.signals.write_mp3_file_started.emit()

    def write_mp3_file_progress(self, progress: int):
        self.signals.write_mp3_file_progress.emit(progress)

    def write_mp3_file_complete(self):
        self.signals.write_mp3_file_complete.emit()


if __name__ == "__main__":
    app = QApplication(sys.argv)

    main_window = MainWindow()
    main_window.show()

    sys.exit(app.exec_())
