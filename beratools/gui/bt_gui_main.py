"""
Copyright (C) 2025 Applied Geospatial Research Group.

This script is licensed under the GNU General Public License v3.0.
See <https://gnu.org/licenses/gpl-3.0> for full license details.

Author: Richard Zeng

Description:
    This script is part of the BERA Tools.
    Webpage: https://github.com/appliedgrg/beratools

    The purpose of this script is to provide main GUI functions.
"""

import json
import os
import shlex
import sys
import webbrowser
from pathlib import Path

from PyQt5 import QtCore, QtGui, QtWidgets

import beratools.core.constants as bt_const
from beratools.gui import bt_data
from beratools.gui.tool_widgets import ToolWidgets

bt = bt_data.BTData()

def extract_string_from_printout(str_print, str_extract):
    str_array = shlex.split(str_print)  # keep string in double quotes
    str_array_enum = enumerate(str_array)
    index = 0
    for item in str_array_enum:
        if str_extract in item[1]:
            index = item[0]
            break
    str_out = str_array[index]
    return str_out.strip()

class _SearchProxyModel(QtCore.QSortFilterProxyModel):
    def setFilterRegExp(self, pattern):
        if isinstance(pattern, str):
            pattern = QtCore.QRegExp(pattern, QtCore.Qt.CaseInsensitive, QtCore.QRegExp.FixedString)
        super(_SearchProxyModel, self).setFilterRegExp(pattern)

    def _accept_index(self, idx):
        if idx.isValid():
            text = idx.data(QtCore.Qt.DisplayRole)
            if self.filterRegExp().indexIn(text) >= 0:
                return True
            for row in range(idx.model().rowCount(idx)):
                if self._accept_index(idx.model().index(row, 0, idx)):
                    return True
        return False

    def filterAcceptsRow(self, sourceRow, sourceParent):
        idx = self.sourceModel().index(sourceRow, 0, sourceParent)
        return self._accept_index(idx)


class BTTreeView(QtWidgets.QWidget):
    """Tree view for BERA Tools GUI."""

    tool_changed = QtCore.pyqtSignal(str)  # tool selection changed

    def __init__(self, parent=None):
        super(BTTreeView, self).__init__(parent)

        # controls
        self.tool_search = QtWidgets.QLineEdit()
        self.tool_search.setPlaceholderText("Search...")

        self.tags_model = _SearchProxyModel()
        self.tree_model = QtGui.QStandardItemModel()
        self.tags_model.setSourceModel(self.tree_model)
        # self.tags_model.setDynamicSortFilter(True)
        self.tags_model.setFilterCaseSensitivity(QtCore.Qt.CaseInsensitive)

        self.tree_view = QtWidgets.QTreeView()
        self.tree_view.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tree_view.setHeaderHidden(True)
        self.tree_view.setRootIsDecorated(True)
        self.tree_view.setUniformRowHeights(True)
        self.tree_view.setModel(self.tags_model)

        # layout
        main_layout = QtWidgets.QVBoxLayout()
        main_layout.addWidget(self.tool_search)
        main_layout.addWidget(self.tree_view)
        self.setLayout(main_layout)

        # signals
        self.tool_search.textChanged.connect(self.search_text_changed)

        # init
        first_child = self.create_model()

        self.tree_view.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectRows)
        self.tree_view.setSelectionMode(QtWidgets.QAbstractItemView.SingleSelection)
        self.tree_view.setEditTriggers(QtWidgets.QAbstractItemView.NoEditTriggers)
        self.tree_view.setFirstColumnSpanned(0, self.tree_view.rootIndex(), True)
        self.tree_view.setUniformRowHeights(True)

        self.tree_model.setHorizontalHeaderLabels(["Tools"])
        self.tree_sel_model = self.tree_view.selectionModel()
        self.tree_sel_model.selectionChanged.connect(self.tree_view_selection_changed)

        index = None
        # select recent tool
        if bt.recent_tool:
            index = self.get_tool_index(bt.recent_tool)
        else:
            # index_set = self.tree_model.index(0, 0)
            index = self.tree_model.indexFromItem(first_child)

        self.select_tool_by_index(index)
        self.tree_view.collapsed.connect(self.tree_item_collapsed)
        self.tree_view.expanded.connect(self.tree_item_expanded)

    def create_model(self):
        first_child = self.add_tool_list_to_tree(bt.toolbox_list, bt.sorted_tools)

        return first_child

    def search_text_changed(self, text=None):
        self.tags_model.setFilterRegExp(self.tool_search.text())

        if len(self.tool_search.text()) >= 1 and self.tags_model.rowCount() > 0:
            self.tree_view.expandAll()
        else:
            self.tree_view.collapseAll()

    def add_tool_list_to_tree(self, toolbox_list, sorted_tools):
        first_child = None
        for i, toolbox in enumerate(toolbox_list):
            parent = QtGui.QStandardItem(
                QtGui.QIcon(os.path.join(bt_const.ASSETS_PATH, "close.gif")), toolbox
            )
            for j, tool in enumerate(sorted_tools[i]):
                child = QtGui.QStandardItem(QtGui.QIcon(os.path.join(bt_const.ASSETS_PATH, "tool.gif")), tool)
                if i == 0 and j == 0:
                    first_child = child

                parent.appendRow([child])
            self.tree_model.appendRow(parent)

        return first_child

    def tree_view_selection_changed(self, new, old):
        if len(new.indexes()) == 0:
            return

        selected = new.indexes()[0]
        source_index = self.tags_model.mapToSource(selected)
        item = self.tree_model.itemFromIndex(source_index)
        parent = item.parent()
        if not parent:
            return

        tool = item.text()
        self.tool_changed.emit(tool)

    def tree_item_expanded(self, index):
        source_index = self.tags_model.mapToSource(index)
        item = self.tree_model.itemFromIndex(source_index)
        if not item:
            return

        if item.hasChildren():
            item.setIcon(QtGui.QIcon(os.path.join(bt_const.ASSETS_PATH, "open.gif")))

    def tree_item_collapsed(self, index):
        source_index = self.tags_model.mapToSource(index)
        item = self.tree_model.itemFromIndex(source_index)
        if not item:
            return

        if item.hasChildren():
            item.setIcon(QtGui.QIcon(os.path.join(bt_const.ASSETS_PATH, "close.gif")))

    def get_tool_index(self, tool_name):
        item = self.tree_model.findItems(tool_name, QtCore.Qt.MatchExactly | QtCore.Qt.MatchRecursive)
        if len(item) > 0:
            item = item[0]

        index = self.tree_model.indexFromItem(item)
        return index

    def select_tool_by_index(self, index):
        proxy_index = self.tags_model.mapFromSource(index)
        self.tree_sel_model.select(proxy_index, QtCore.QItemSelectionModel.ClearAndSelect)
        self.tree_view.expand(proxy_index.parent())
        self.tree_sel_model.setCurrentIndex(proxy_index, QtCore.QItemSelectionModel.Current)

    def select_tool_by_name(self, name):
        index = self.get_tool_index(name)
        self.select_tool_by_index(index)


class ClickSlider(QtWidgets.QSlider):
    """Custom slider for BERA Tools GUI."""

    def mousePressEvent(self, event):
        super(ClickSlider, self).mousePressEvent(event)
        if event.button() == QtCore.Qt.LeftButton:
            val = self.pixel_pos_to_range_value(event.pos())
            self.setValue(val)
            self.sliderMoved.emit(val)

    def pixel_pos_to_range_value(self, pos):
        opt = QtWidgets.QStyleOptionSlider()
        self.initStyleOption(opt)
        gr = self.style().subControlRect(
            QtWidgets.QStyle.CC_Slider, opt, QtWidgets.QStyle.SC_SliderGroove, self
        )
        sr = self.style().subControlRect(
            QtWidgets.QStyle.CC_Slider, opt, QtWidgets.QStyle.SC_SliderHandle, self
        )

        if self.orientation() == QtCore.Qt.Horizontal:
            slider_length = sr.width()
            slider_min = gr.x()
            slider_max = gr.right() - slider_length + 1
        else:
            slider_length = sr.height()
            slider_min = gr.y()
            slider_max = gr.bottom() - slider_length + 1
        pr = pos - sr.center() + sr.topLeft()
        p = pr.x() if self.orientation() == QtCore.Qt.Horizontal else pr.y()
        return QtWidgets.QStyle.sliderValueFromPosition(
            self.minimum(),
            self.maximum(),
            p - slider_min,
            slider_max - slider_min,
            opt.upsideDown,
        )


class BTSlider(QtWidgets.QWidget):
    """Slider for BERA Tools GUI."""

    def __init__(self, current, maximum, parent=None):
        super(BTSlider, self).__init__(parent)

        self.value = current
        self.slider = ClickSlider(QtCore.Qt.Horizontal)
        self.slider.setFixedWidth(120)
        self.slider.setTickInterval(2)
        self.slider.setTickPosition(QtWidgets.QSlider.TicksAbove)
        self.slider.setRange(1, maximum)
        self.slider.setValue(current)
        self.label = QtWidgets.QLabel(self.generate_label_text(current))

        layout = QtWidgets.QHBoxLayout()
        layout.addWidget(self.label)
        layout.addWidget(self.slider)
        self.setLayout(layout)

        self.slider.sliderMoved.connect(self.slider_moved)

    def slider_moved(self, value):
        bt.set_max_procs(value)
        QtWidgets.QToolTip.showText(QtGui.QCursor.pos(), f"{value}")
        self.label.setText(self.generate_label_text())

    def generate_label_text(self, value=None):
        if not value:
            value = self.slider.value()

        return f"Use CPU Cores: {value:3d}"


class BTListView(QtWidgets.QWidget):
    """List view for BERA Tools GUI."""

    tool_changed = QtCore.pyqtSignal(str)

    def __init__(self, data_list=None, parent=None):
        super(BTListView, self).__init__(parent)

        delete_icon = QtWidgets.QStyle.SP_DialogCloseButton
        delete_icon = self.style().standardIcon(delete_icon)
        clear_icon = QtWidgets.QStyle.SP_DialogResetButton
        clear_icon = self.style().standardIcon(clear_icon)
        btn_delete = QtWidgets.QPushButton()
        btn_clear = QtWidgets.QPushButton()
        btn_delete.setIcon(delete_icon)
        btn_clear.setIcon(clear_icon)
        btn_delete.setToolTip("Delete selected tool history")
        btn_clear.setToolTip("clear all tool history")
        btn_delete.setFixedWidth(40)
        btn_clear.setFixedWidth(40)

        layout_h = QtWidgets.QHBoxLayout()
        layout_h.addWidget(btn_delete)
        layout_h.addWidget(btn_clear)
        layout_h.addStretch(1)

        self.list_view = QtWidgets.QListView()
        self.list_view.setFlow(QtWidgets.QListView.TopToBottom)
        self.list_view.setBatchSize(5)

        self.list_model = QtCore.QStringListModel()  # model
        if data_list:
            self.list_model.setStringList(data_list)

        self.list_view.setModel(self.list_model)  # set model
        self.sel_model = self.list_view.selectionModel()

        self.list_view.setLayoutMode(QtWidgets.QListView.SinglePass)
        btn_delete.clicked.connect(self.delete_selected_item)
        btn_clear.clicked.connect(self.clear_all_items)
        self.sel_model.selectionChanged.connect(self.selection_changed)

        layout = QtWidgets.QVBoxLayout()
        layout.addLayout(layout_h)
        layout.addWidget(self.list_view)
        self.setLayout(layout)

    def selection_changed(self, new, old):
        indexes = new.indexes()
        if len(indexes) == 0:
            return

        selection = new.indexes()[0]
        tool = self.list_model.itemData(selection)[0]
        self.tool_changed.emit(tool)

    def set_data_list(self, data_list):
        self.list_model.setStringList(data_list)

    def delete_selected_item(self):
        selection = self.sel_model.currentIndex()
        self.list_model.removeRow(selection.row())
        bt.remove_tool_history_item(selection.row())

    def clear_all_items(self):
        self.list_model.setStringList([])
        bt.remove_tool_history_all()


class MainWindow(QtWidgets.QMainWindow):
    """Main window for BERA Tools GUI."""

    def __init__(self):
        super().__init__()

        self.script_dir = os.path.dirname(os.path.realpath(__file__))
        self.title = "BERA Tools"
        self.setWindowTitle(self.title)
        self.working_dir = bt.work_dir
        self.tool_api = None
        self.tool_name = "Centerline"
        self.recent_tool = bt.recent_tool
        if self.recent_tool:
            self.tool_name = self.recent_tool
            self.tool_api = bt.get_bera_tool_api(self.tool_name)

        self.update_procs(bt.get_max_cpu_cores())

        # QProcess run tools
        self.process = None
        self.cancel_op = False

        # BERA tool list
        self.bera_tools = bt.bera_tools
        self.tools_list = bt.tools_list
        self.sorted_tools = bt.sorted_tools
        self.toolbox_list = bt.toolbox_list
        self.upper_toolboxes = bt.upper_toolboxes
        self.lower_toolboxes = bt.lower_toolboxes

        self.current_file_path = Path(__file__).resolve().parent
        bt.set_bera_dir(self.current_file_path)

        # Tree view
        self.tree_view = BTTreeView()
        self.tree_view.tool_changed.connect(self.set_tool)

        # group box for tree view
        tree_box = QtWidgets.QGroupBox()
        tree_box.setTitle("Tools available")
        tree_layout = QtWidgets.QVBoxLayout()
        tree_layout.addWidget(self.tree_view)
        tree_box.setLayout(tree_layout)

        # QListWidget
        self.tool_history = BTListView()
        self.tool_history.set_data_list(bt.tool_history)
        self.tool_history.tool_changed.connect(self.set_tool)

        # group box
        tool_history_box = QtWidgets.QGroupBox()
        tool_history_layout = QtWidgets.QVBoxLayout()
        tool_history_layout.addWidget(self.tool_history)
        tool_history_box.setTitle("Tool history")
        tool_history_box.setLayout(tool_history_layout)

        # left layout
        page_layout = QtWidgets.QHBoxLayout()
        self.left_layout = QtWidgets.QVBoxLayout()
        self.right_layout = QtWidgets.QVBoxLayout()

        self.left_layout.addWidget(tree_box)
        self.left_layout.addWidget(tool_history_box)

        # top buttons
        label = QtWidgets.QLabel(f"{self.tool_name}")
        label.setFont(QtGui.QFont("Consolas", 14))
        self.btn_advanced = QtWidgets.QPushButton("Show Advanced Options")
        self.btn_advanced.setFixedWidth(180)
        btn_help = QtWidgets.QPushButton("help")
        btn_code = QtWidgets.QPushButton("Code")
        btn_help.setFixedWidth(250)
        btn_code.setFixedWidth(100)

        self.btn_layout_top = QtWidgets.QHBoxLayout()
        self.btn_layout_top.setAlignment(QtCore.Qt.AlignRight)
        self.btn_layout_top.addWidget(label)
        self.btn_layout_top.addStretch(1)
        self.btn_layout_top.addWidget(self.btn_advanced)
        self.btn_layout_top.addWidget(btn_code)

        # ToolWidgets
        tool_args = bt.get_bera_tool_args(self.tool_name)
        self.tool_widget = ToolWidgets(self.recent_tool, tool_args, bt.show_advanced)

        # bottom buttons
        slider = BTSlider(bt.max_procs, bt.max_cpu_cores)
        btn_default_args = QtWidgets.QPushButton("Load Default Arguments")
        self.btn_run = QtWidgets.QPushButton("Run")
        btn_cancel = QtWidgets.QPushButton("Cancel")
        btn_default_args.setFixedWidth(150)
        slider.setFixedWidth(250)
        self.btn_run.setFixedWidth(120)
        btn_cancel.setFixedWidth(120)

        btn_layout_bottom = QtWidgets.QHBoxLayout()
        btn_layout_bottom.setAlignment(QtCore.Qt.AlignRight)
        btn_layout_bottom.addStretch(1)
        btn_layout_bottom.addWidget(btn_default_args)
        btn_layout_bottom.addWidget(slider)
        btn_layout_bottom.addWidget(self.btn_run)
        btn_layout_bottom.addWidget(btn_cancel)

        self.top_right_layout = QtWidgets.QVBoxLayout()
        self.top_right_layout.addLayout(self.btn_layout_top)
        self.top_right_layout.addWidget(self.tool_widget)
        self.top_right_layout.addLayout(btn_layout_bottom)
        tool_widget_grp = QtWidgets.QGroupBox("Tool")
        tool_widget_grp.setLayout(self.top_right_layout)

        # Text widget
        self.text_edit = QtWidgets.QPlainTextEdit()
        self.text_edit.setFont(QtGui.QFont("Consolas", 9))
        self.text_edit.setReadOnly(True)
        self.print_about()

        # progress bar
        self.progress_label = QtWidgets.QLabel()
        self.progress_bar = QtWidgets.QProgressBar(self)
        self.progress_var = 0

        # progress layout
        progress_layout = QtWidgets.QHBoxLayout()
        progress_layout.addWidget(self.progress_label)
        progress_layout.addWidget(self.progress_bar)

        self.right_layout.addWidget(tool_widget_grp)
        self.right_layout.addWidget(self.text_edit)
        self.right_layout.addLayout(progress_layout)

        # main layouts
        page_layout.addLayout(self.left_layout, 3)
        page_layout.addLayout(self.right_layout, 7)

        # signals and slots
        self.btn_advanced.clicked.connect(self.show_advanced)
        btn_help.clicked.connect(self.show_help)
        btn_code.clicked.connect(self.view_code)
        btn_default_args.clicked.connect(self.load_default_args)
        self.btn_run.clicked.connect(self.start_process)
        btn_cancel.clicked.connect(self.stop_process)

        widget = QtWidgets.QWidget(self)
        widget.setLayout(page_layout)
        self.setCentralWidget(widget)

    def set_tool(self, tool=None):
        if tool:
            self.tool_name = tool

        # let tree view select the tool
        self.tree_view.select_tool_by_name(self.tool_name)
        self.tool_api = bt.get_bera_tool_api(self.tool_name)
        tool_args = bt.get_bera_tool_args(self.tool_name)

        # update tool label
        self.btn_layout_top.itemAt(0).widget().setText(self.tool_name)

        # update tool widget
        self.tool_widget = ToolWidgets(self.tool_name, tool_args, bt.show_advanced)
        widget = self.top_right_layout.itemAt(1).widget()
        self.top_right_layout.removeWidget(widget)
        self.top_right_layout.insertWidget(1, self.tool_widget)
        self.top_right_layout.update()

    def save_tool_parameter(self):
        # Retrieve tool parameters from GUI
        args = self.tool_widget.get_widgets_arguments()
        # bt.load_saved_tool_info()
        bt.add_tool_history(self.tool_api, args)
        bt.save_tool_info()

        # update tool history list
        bt.get_tool_history()
        self.tool_history.set_data_list(bt.tool_history)

    def get_current_tool_parameters(self):
        self.tool_api = bt.get_bera_tool_api(self.tool_name)
        return bt.get_bera_tool_params(self.tool_name)

    def show_help(self):
        # open the user manual section for the current tool
        webbrowser.open_new_tab(self.get_current_tool_parameters()["tech_link"])

    def print_about(self):
        self.text_edit.clear()
        self.print_to_output(bt.about())

    def print_license(self):
        self.text_edit.clear()
        self.print_to_output(bt.license())

    def update_procs(self, value):
        max_procs = int(value)
        bt.set_max_procs(max_procs)

    def print_to_output(self, text):
        self.text_edit.moveCursor(QtGui.QTextCursor.End)
        self.text_edit.insertPlainText(text)
        self.text_edit.moveCursor(QtGui.QTextCursor.End)

    def print_line_to_output(self, text, tag=None):
        self.text_edit.moveCursor(QtGui.QTextCursor.End)
        self.text_edit.insertPlainText(text + "\n")
        self.text_edit.moveCursor(QtGui.QTextCursor.End)

    def show_advanced(self):
        if bt.show_advanced:
            bt.show_advanced = False
            self.btn_advanced.setText("Show Advanced Options")
        else:
            bt.show_advanced = True
            self.btn_advanced.setText("Hide Advanced Options")

        self.set_tool()

    def view_code(self):
        webbrowser.open_new_tab(self.get_current_tool_parameters()["tech_link"])

    def custom_callback(self, value):
        """Define custom callback that deals with tool output."""
        value = str(value)
        value.strip()
        if value != "":
            # remove esc string which origin is unknown
            rm_str = "\x1b[0m"
            if rm_str in value:
                value = value.replace(rm_str, "")

        if "%" in value:
            try:
                str_progress = extract_string_from_printout(value, "%")

                # remove progress string
                value = value.replace(str_progress, "").strip()
                progress = float(str_progress.replace("%", "").strip())
                self.progress_bar.setValue(int(progress))
            except ValueError as e:
                print("custom_callback: Problem parsing data into number: ", e)
            except Exception as e:
                print(e)
        elif "PROGRESS_LABEL" in value:
            str_label = extract_string_from_printout(value, "PROGRESS_LABEL")
            value = value.replace(str_label, "").strip()  # remove progress string
            value = value.replace('"', "")
            str_label = str_label.replace("PROGRESS_LABEL", "").strip()
            self.progress_label.setText(str_label)

        if value:
            self.print_line_to_output(value)

    def message(self, s):
        self.text_edit.appendPlainText(s)

    def load_default_args(self):
        self.tool_widget.load_default_args()

    def start_process(self):
        args = self.tool_widget.get_widgets_arguments()
        if not args:
            print("Please check the parameters.")
            return

        self.print_line_to_output("")
        self.print_line_to_output(f"Starting tool {self.tool_name} ... \n")
        self.print_line_to_output("-----------------------------")
        self.print_line_to_output("Tool arguments:")
        self.print_line_to_output(json.dumps(args, indent=4))
        self.print_line_to_output("")

        bt.recent_tool = self.tool_name
        self.save_tool_parameter()

        # Run the tool and check the return value for an error
        for key in args.keys():
            if type(args[key]) is not str:
                args[key] = str(args[key])

        tool_type, tool_args = bt.run_tool(self.tool_api, args, self.custom_callback)

        if self.process is None:  # No process running.
            self.print_line_to_output(f"Tool {self.tool_name} started")
            self.print_line_to_output("-----------------------")
            self.process = QtCore.QProcess()  # Keep a reference to the QProcess
            self.process.readyReadStandardOutput.connect(self.handle_stdout)
            self.process.readyReadStandardError.connect(self.handle_stderr)
            self.process.stateChanged.connect(self.handle_state)

            # Clean up once complete.
            self.process.finished.connect(self.process_finished)
            self.process.start(tool_type, tool_args)

        while self.process is not None:
            sys.stdout.flush()
            if self.cancel_op:
                self.cancel_op = False
                self.process.terminate()
            else:
                break

    def stop_process(self):
        self.cancel_op = True
        if self.process:
            self.print_line_to_output(f"Tool {self.tool_name} terminating ...")
            self.process.kill()

    def handle_stderr(self):
        data = self.process.readAllStandardError()
        stderr = bytes(data).decode("utf8")

        self.message(stderr)

    def handle_stdout(self):
        line = self.process.readLine()
        line = bytes(line).decode("utf8")

        # process line output
        self.custom_callback(line)
        sys.stdout.flush()

    def handle_state(self, state):
        states = {
            QtCore.QProcess.NotRunning: "Not running",
            QtCore.QProcess.Starting: "Starting",
            QtCore.QProcess.Running: "Running",
        }
        state_name = states[state]
        if state_name == "Not running":
            self.btn_run.setEnabled(True)
            if self.cancel_op:
                self.message("Tool operation canceled")
        elif state_name == "Starting":
            self.btn_run.setEnabled(False)

    def process_finished(self):
        self.message("Process finished.")
        self.process = None
        self.progress_bar.setValue(0)
        self.progress_label.setText("")


def runner():
    app = QtWidgets.QApplication(sys.argv)
    app.setWindowIcon(QtGui.QIcon("beratools/gui/assets/BERALogo.ico"))
    window = MainWindow()
    window.setMinimumSize(1024, 768)
    window.show()
    app.exec()
