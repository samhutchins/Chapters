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
from typing import Any, List, Callable, NamedTuple, Optional

from PySide2.QtCore import Signal, QThreadPool, QCoreApplication, QAbstractTableModel, QModelIndex, Qt, QRunnable, \
    QObject
from PySide2.QtGui import QKeySequence
from PySide2.QtWidgets import QMainWindow, QLineEdit, QSpinBox, QTableView, QWidget, QLabel, QVBoxLayout, \
    QFileDialog, QDialog, QApplication, QFormLayout

from libchapters import Chapter, MetaData, LibChapters
from utils import ApplicationVersion

APPLICATION_NAME = "Chapters"
APPLICATION_VERSION = ApplicationVersion(1, 0)


class MainWindow(QMainWindow):
    def __init__(self):
        QMainWindow.__init__(self)
        self.lib_chapters = LibChapters()
        self.task_executor = QThreadPool.globalInstance()
        self.current_file: Optional[str] = None

        self.chapters_table_model = ChaptersTableModel()

        # UI components
        self.setWindowTitle(APPLICATION_NAME)
        self.setMinimumSize(480, 320)
        self.resize(900, 500)
        self.__create_menu()
        self.__create_status_bar()

        self.podcast_title = QLineEdit()
        self.episode_title = QLineEdit()
        self.episode_number = QSpinBox()
        self.episode_number.setMaximumWidth(55)

        self.chapters_table_view = QTableView()
        self.chapters_table_view.setModel(self.chapters_table_model)
        self.chapters_table_view.horizontalHeader().setStretchLastSection(True)

        self.setCentralWidget(self.__create_center_widget())
        self.centralWidget().setDisabled(True)

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

    def __create_menu(self) -> None:
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("File")
        open_action = file_menu.addAction("Open")
        open_action.setShortcut(QKeySequence("Ctrl+O"))
        open_action.triggered.connect(self.__open_file)

        export_action = file_menu.addAction("Export")
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self.__export_file)

        file_menu.addSeparator()

        exit_action = file_menu.addAction("Exit")
        exit_action.setShortcut(QKeySequence("Alt+f4"))
        exit_action.triggered.connect(QCoreApplication.quit)

        help_menu = menu_bar.addMenu("Help")
        help_action = help_menu.addAction("About")
        help_action.setShortcut(QKeySequence("F1"))
        help_action.triggered.connect(self.__show_about_dialog)

    def __create_status_bar(self):
        self.statusBar()

    def __update_table(self) -> None:
        read_chapters_task = ReadChaptersTask(self.lib_chapters, self.current_file)
        read_chapters_task.signals.finished.connect(self.chapters_table_model.set_chapters)
        self.task_executor.start(read_chapters_task)

    def __open_file(self) -> None:
        file, _ = QFileDialog.getOpenFileName(self, filter="*.wav")
        if file:
            self.current_file = file
            self.setWindowTitle(f"{APPLICATION_NAME} [{os.path.basename(file)}]")
            self.centralWidget().setDisabled(False)
            guessed_metadata = self.lib_chapters.guess_podcast_info(file)
            if guessed_metadata.podcast_title:
                self.podcast_title.setText(guessed_metadata.podcast_title)

            if guessed_metadata.episode_title:
                self.episode_title.setText(guessed_metadata.episode_title)

            if guessed_metadata.episode_number:
                self.episode_number.setValue(guessed_metadata.episode_number)

            self.__update_table()

    def __export_file(self) -> None:
        if self.current_file:
            file, _ = QFileDialog.getSaveFileName(self, filter="*.mp3")
            if file:
                meta_data = MetaData(
                    podcast_title=self.podcast_title.text(),
                    episode_title=self.episode_title.text(),
                    episode_number=self.episode_number.value(),
                    chapters=self.chapters_table_model.get_chapters())

                task = EncoderTask(self.lib_chapters, self.current_file, meta_data, file)
                task.signals.finished.connect(self.__encode_finished)
                self.__encode_started(file)
                self.task_executor.start(task)

    def __show_about_dialog(self) -> None:
        about_dialog = AboutDialog(self)
        about_dialog.show()

    def __encode_started(self, output: str):
        self.centralWidget().setDisabled(True)
        self.menuBar().setDisabled(True)
        self.statusBar().showMessage(f"Encoding {os.path.basename(self.current_file)} to {output}")

    def __encode_finished(self):
        self.centralWidget().setDisabled(False)
        self.menuBar().setDisabled(False)
        self.statusBar().clearMessage()


class ChaptersTableModel(QAbstractTableModel):
    def __init__(self):
        QAbstractTableModel.__init__(self)
        self.__chapters: List[Chapter] = list()
        self.__columns: List[TableColumn] = [
            TableColumn("Start Time", lambda chapter: str(datetime.timedelta(seconds=int(chapter.start / 1000)))),
            TableColumn("End Time", lambda chapter: str(datetime.timedelta(seconds=int(chapter.end / 1000)))),
            TableColumn("Name", lambda chapter: chapter.name)
        ]

    def set_chapters(self, chapters: List[Chapter]) -> None:
        self.clear_chapters()
        self.beginInsertRows(QModelIndex(), 0, len(chapters) - 1)
        self.__chapters = list(chapters)
        self.endInsertRows()

    def clear_chapters(self) -> None:
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
    def show(self) -> None:
        super().show()
        self.raise_()
        self.activateWindow()


class ReadChaptersTaskSignals(QObject):
    finished = Signal(object)  # List[Chapter]


class ReadChaptersTask(QRunnable):
    def __init__(self, lib_chapters: LibChapters, path_to_wav: str):
        QRunnable.__init__(self)
        self.signals = ReadChaptersTaskSignals()
        self.lib_chapters = lib_chapters
        self.path_to_wav = path_to_wav

    # override
    def run(self):
        chapters = self.lib_chapters.read_chapters(self.path_to_wav)
        self.signals.finished.emit(chapters)


class EncoderTaskSignals(QObject):
    finished = Signal()


class EncoderTask(QRunnable):
    def __init__(self, lib_chapters: LibChapters, path_to_wav: str, meta_data: MetaData, path_to_output: str):
        QRunnable.__init__(self)
        self.signals = EncoderTaskSignals()
        self.lib_chapters = lib_chapters
        self.path_to_wav = path_to_wav
        self.meta_data = meta_data
        self.path_to_output = path_to_output

    # override
    def run(self):
        audio_data = self.lib_chapters.encode_podcast(self.path_to_wav, self.meta_data)
        with open(self.path_to_output, "wb") as f:
            f.write(audio_data.getvalue())

        self.signals.finished.emit()


class TableColumn(NamedTuple):
    title: str
    get_data: Callable[[Chapter], str]
    alignment: int = Qt.AlignVCenter


if __name__ == "__main__":
    app = QApplication(sys.argv)

    main_window = MainWindow()
    main_window.show()

    sys.exit(app.exec_())
