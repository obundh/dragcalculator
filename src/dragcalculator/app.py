from __future__ import annotations

import sys
import re
from dataclasses import dataclass

from PIL import Image
from PyQt6.QtCore import QPoint, QRect, QSize, QTimer, Qt
from PyQt6.QtGui import (
    QColor,
    QCursor,
    QFont,
    QGuiApplication,
    QImage,
    QPainter,
    QPen,
    QPixmap,
)
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QSpacerItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from .calculator import (
    Calculation,
    CalculationError,
    calculate_expression,
    calculate_from_text,
    calculate_with_operator,
    clean_number_text,
)
from .ocr import OcrNumber, OcrResult, RapidOcrReader
from .screen import CaptureRect, capture_region


@dataclass
class EditableNumber:
    index: int
    value: str
    rect: QRect
    confidence: float
    line_text: str


class SelectionOverlay(QWidget):
    def __init__(self, on_selected, on_cancel) -> None:
        super().__init__()
        self._on_selected = on_selected
        self._on_cancel = on_cancel
        self._origin: QPoint | None = None
        self._current: QPoint | None = None
        self._selection = QRect()

        self.setWindowTitle("DragCalculator Capture")
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setMouseTracking(True)
        self.setCursor(QCursor(Qt.CursorShape.CrossCursor))

    def start(self) -> None:
        screen = QGuiApplication.primaryScreen()
        geometry = screen.virtualGeometry() if screen else QRect(0, 0, 1200, 800)
        self._origin = None
        self._current = None
        self._selection = QRect()
        self.setGeometry(geometry)
        self.show()
        self.raise_()
        self.activateWindow()

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(14, 16, 19, 78))

        hint_rect = QRect(28, 24, 380, 40)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(248, 250, 252, 238))
        painter.drawRoundedRect(hint_rect, 8, 8)
        painter.setPen(QColor(33, 38, 45))
        painter.setFont(QFont("Segoe UI", 10, QFont.Weight.Medium))
        painter.drawText(
            hint_rect.adjusted(16, 0, -16, 0),
            Qt.AlignmentFlag.AlignVCenter,
            "Drag an area to calculate. Esc cancels.",
        )

        if self._selection.isNull():
            return

        local_rect = QRect(self._selection)
        local_rect.translate(-self.geometry().topLeft())
        painter.fillRect(local_rect, QColor(34, 197, 166, 36))
        painter.setPen(QPen(QColor(22, 163, 142), 2))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRoundedRect(local_rect.adjusted(0, 0, -1, -1), 4, 4)

        size_label = f"{self._selection.width()} x {self._selection.height()}"
        label_rect = QRect(
            local_rect.left(),
            max(0, local_rect.top() - 30),
            96,
            24,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(33, 38, 45, 226))
        painter.drawRoundedRect(label_rect, 6, 6)
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Segoe UI", 9, QFont.Weight.Medium))
        painter.drawText(label_rect, Qt.AlignmentFlag.AlignCenter, size_label)

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        self._origin = event.globalPosition().toPoint()
        self._current = self._origin
        self._selection = QRect(self._origin, self._current).normalized()
        self.update()

    def mouseMoveEvent(self, event) -> None:
        if self._origin is None:
            return
        self._current = event.globalPosition().toPoint()
        self._selection = QRect(self._origin, self._current).normalized()
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton or self._origin is None:
            return

        self._current = event.globalPosition().toPoint()
        self._selection = QRect(self._origin, self._current).normalized()
        selection = QRect(self._selection)
        self._origin = None
        self._current = None

        if selection.width() < 8 or selection.height() < 8:
            self._selection = QRect()
            self.update()
            return

        self.hide()
        self._on_selected(selection)

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.hide()
            self._on_cancel()


class CapturePreview(QWidget):
    def __init__(self, on_number_clicked) -> None:
        super().__init__()
        self._on_number_clicked = on_number_clicked
        self._pixmap: QPixmap | None = None
        self._numbers: list[EditableNumber] = []
        self._notice = "No capture yet"
        self._zoom = 1.0
        self.setMinimumSize(520, 360)
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

    def sizeHint(self) -> QSize:
        if self._pixmap is None or self._pixmap.isNull():
            return QSize(620, 420)
        return QSize(
            max(1, int(self._pixmap.width() * self._zoom)),
            max(1, int(self._pixmap.height() * self._zoom)),
        )

    def set_capture(self, image: Image.Image, numbers: list[EditableNumber]) -> None:
        self._pixmap = _pil_to_pixmap(image)
        self._numbers = numbers
        self._notice = ""
        self._sync_canvas_size()
        self.update()

    def set_notice(self, notice: str) -> None:
        self._pixmap = None
        self._numbers = []
        self._notice = notice
        self.setMinimumSize(520, 360)
        self.setMaximumSize(16777215, 16777215)
        self.resize(620, 420)
        self.update()

    def set_zoom(self, zoom: float) -> None:
        self._zoom = max(0.15, min(2.5, zoom))
        self._sync_canvas_size()
        self.update()

    def image_width(self) -> int:
        if self._pixmap is None:
            return 0
        return self._pixmap.width()

    def zoom(self) -> float:
        return self._zoom

    def paintEvent(self, _event) -> None:
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.fillRect(self.rect(), QColor(246, 248, 250))

        if self._pixmap is None or self._pixmap.isNull():
            painter.setPen(QColor(101, 113, 126))
            painter.setFont(QFont("Segoe UI", 12, QFont.Weight.Medium))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, self._notice)
            return

        image_rect = self._image_rect()
        painter.drawPixmap(image_rect, self._pixmap)

        for number in self._numbers:
            box = self._map_image_rect(number.rect)
            painter.fillRect(box, QColor(220, 38, 38, 28))
            painter.setPen(QPen(QColor(220, 38, 38), 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(box.adjusted(0, 0, -1, -1), 4, 4)
            self._draw_number_tag(painter, box, number.value)

    def mouseMoveEvent(self, event) -> None:
        cursor = (
            Qt.CursorShape.PointingHandCursor
            if self._number_at(event.position().toPoint())
            else Qt.CursorShape.ArrowCursor
        )
        self.setCursor(QCursor(cursor))

    def mousePressEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        number = self._number_at(event.position().toPoint())
        if number is not None:
            self._on_number_clicked(number.index)

    def _draw_number_tag(self, painter: QPainter, box: QRect, text: str) -> None:
        metrics = painter.fontMetrics()
        tag_width = max(32, metrics.horizontalAdvance(text) + 14)
        tag = QRect(
            box.left(),
            max(self._image_rect().top(), box.top() - 22),
            tag_width,
            19,
        )
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(220, 38, 38))
        painter.drawRoundedRect(tag, 5, 5)
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
        painter.drawText(tag, Qt.AlignmentFlag.AlignCenter, text)

    def _number_at(self, point: QPoint) -> EditableNumber | None:
        for number in reversed(self._numbers):
            if self._map_image_rect(number.rect).contains(point):
                return number
        return None

    def _image_rect(self) -> QRect:
        if self._pixmap is None or self._pixmap.isNull():
            return QRect()

        return QRect(
            0,
            0,
            max(1, int(self._pixmap.width() * self._zoom)),
            max(1, int(self._pixmap.height() * self._zoom)),
        )

    def _map_image_rect(self, rect: QRect) -> QRect:
        if self._pixmap is None or self._pixmap.isNull():
            return QRect()

        return QRect(
            int(rect.left() * self._zoom),
            int(rect.top() * self._zoom),
            max(6, int(rect.width() * self._zoom)),
            max(6, int(rect.height() * self._zoom)),
        )

    def _sync_canvas_size(self) -> None:
        if self._pixmap is None or self._pixmap.isNull():
            return

        size = self.sizeHint()
        self.setMinimumSize(size)
        self.setMaximumSize(size)
        self.resize(size)


class MainWindow(QWidget):
    def __init__(self, controller: "AppController") -> None:
        super().__init__()
        self._controller = controller
        self._last_calculation: Calculation | None = None
        self._base_calculation: Calculation | None = None
        self._numbers: list[EditableNumber] = []
        self._ocr_raw_text = ""
        self._preview_fit_width = True
        self._operation_mode = "+"
        self._refreshing_numbers = False

        self.setWindowTitle("DragCalculator")
        self.setMinimumSize(1040, 920)
        self.resize(1200, 960)
        self.setObjectName("AppWindow")

        self._build_ui()
        self._apply_style()

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if self._preview_fit_width:
            QTimer.singleShot(0, self.fit_preview_to_width)

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(22, 22, 22, 22)
        root.setSpacing(14)

        header = QHBoxLayout()
        title_stack = QVBoxLayout()
        title_stack.setSpacing(3)

        app_name = QLabel("DragCalculator")
        app_name.setObjectName("AppName")
        subtitle = QLabel("Screen math from a dragged region")
        subtitle.setObjectName("Subtitle")
        title_stack.addWidget(app_name)
        title_stack.addWidget(subtitle)

        self.status_label = QLabel("Ready")
        self.status_label.setObjectName("StatusBadge")
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        header.addLayout(title_stack)
        header.addStretch(1)
        header.addWidget(self.status_label)
        root.addLayout(header)

        result_panel = QFrame()
        result_panel.setObjectName("DisplayPanel")
        result_layout = QVBoxLayout(result_panel)
        result_layout.setContentsMargins(22, 18, 22, 20)
        result_layout.setSpacing(12)

        result_header = QHBoxLayout()
        result_title = QLabel("Calculator")
        result_title.setObjectName("DisplayTitle")
        self.mode_label = QLabel("Auto")
        self.mode_label.setObjectName("ModePill")
        result_header.addWidget(result_title)
        result_header.addStretch(1)
        result_header.addWidget(self.mode_label)
        result_layout.addLayout(result_header)

        self.result_value = QLabel("0")
        self.result_value.setObjectName("ResultValue")
        self.result_value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self.result_value.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        result_layout.addWidget(self.result_value)

        self.expression_label = QLabel("No capture yet")
        self.expression_label.setObjectName("Expression")
        self.expression_label.setWordWrap(True)
        self.expression_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        result_layout.addWidget(self.expression_label)

        button_row = QHBoxLayout()
        self.capture_button = QPushButton("Capture")
        self.capture_button.setObjectName("PrimaryButton")
        self.copy_button = QPushButton("Copy")
        self.copy_button.setEnabled(False)
        button_row.addWidget(self.capture_button)
        button_row.addWidget(self.copy_button)
        button_row.addItem(QSpacerItem(20, 1, QSizePolicy.Policy.Expanding))
        result_layout.addLayout(button_row)

        root.addWidget(result_panel)

        workspace = QGridLayout()
        workspace.setSpacing(16)
        workspace.setColumnStretch(0, 4)
        workspace.setColumnStretch(1, 2)
        workspace.setRowStretch(0, 5)
        workspace.setRowStretch(1, 1)
        root.addLayout(workspace, 1)

        preview_panel = QFrame()
        preview_panel.setObjectName("Panel")
        preview_layout = QVBoxLayout(preview_panel)
        preview_layout.setContentsMargins(18, 18, 18, 18)
        preview_layout.setSpacing(10)

        preview_header = QHBoxLayout()
        preview_title = QLabel("Captured Area")
        preview_title.setObjectName("PanelTitle")
        self.fit_button = QPushButton("Fit")
        self.actual_button = QPushButton("100%")
        self.zoom_out_button = QPushButton("-")
        self.zoom_in_button = QPushButton("+")
        for button in (
            self.fit_button,
            self.actual_button,
            self.zoom_out_button,
            self.zoom_in_button,
        ):
            button.setObjectName("SmallButton")
        preview_header.addWidget(preview_title)
        preview_header.addStretch(1)
        preview_header.addWidget(self.fit_button)
        preview_header.addWidget(self.actual_button)
        preview_header.addWidget(self.zoom_out_button)
        preview_header.addWidget(self.zoom_in_button)
        preview_layout.addLayout(preview_header)

        self.preview = CapturePreview(self.edit_number)
        self.preview.setObjectName("Preview")
        self.preview_scroll = QScrollArea()
        self.preview_scroll.setObjectName("PreviewScroll")
        self.preview_scroll.setWidget(self.preview)
        self.preview_scroll.setWidgetResizable(False)
        self.preview_scroll.setAlignment(Qt.AlignmentFlag.AlignCenter)
        preview_layout.addWidget(self.preview_scroll, 1)
        workspace.addWidget(preview_panel, 0, 0, 2, 1)

        numbers_panel = QFrame()
        numbers_panel.setObjectName("Panel")
        numbers_panel.setMinimumHeight(390)
        numbers_layout = QVBoxLayout(numbers_panel)
        numbers_layout.setContentsMargins(18, 18, 18, 18)
        numbers_layout.setSpacing(8)

        numbers_title = QLabel("Numbers")
        numbers_title.setObjectName("PanelTitle")
        self.numbers_list = QListWidget()
        self.numbers_list.setObjectName("NumbersList")
        self.numbers_list.setMinimumHeight(118)
        self.numbers_list.setMaximumHeight(124)
        self.numbers_list.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.numbers_list.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.numbers_list.setEditTriggers(
            QAbstractItemView.EditTrigger.DoubleClicked
            | QAbstractItemView.EditTrigger.EditKeyPressed
            | QAbstractItemView.EditTrigger.SelectedClicked
        )
        numbers_layout.addWidget(numbers_title)
        numbers_layout.addWidget(self.numbers_list, 1)

        op_grid = QGridLayout()
        op_grid.setSpacing(8)
        self.add_button = QPushButton("+")
        self.subtract_button = QPushButton("-")
        self.multiply_button = QPushButton("x")
        self.divide_button = QPushButton("/")
        for button in (
            self.add_button,
            self.subtract_button,
            self.multiply_button,
            self.divide_button,
        ):
            button.setObjectName("CalcButton")
        op_grid.addWidget(self.add_button, 0, 0)
        op_grid.addWidget(self.subtract_button, 0, 1)
        op_grid.addWidget(self.multiply_button, 0, 2)
        op_grid.addWidget(self.divide_button, 0, 3)
        numbers_layout.addLayout(op_grid)

        formula_row = QHBoxLayout()
        self.formula_input = QLineEdit()
        self.formula_input.setObjectName("FormulaInput")
        self.formula_input.setPlaceholderText("3+(4+5), sqrt(n1), n1*(n2+n3)")
        self.apply_formula_button = QPushButton("=")
        self.apply_formula_button.setObjectName("CalcButton")
        formula_row.addWidget(self.formula_input, 1)
        formula_row.addWidget(self.apply_formula_button)
        numbers_layout.addLayout(formula_row)

        sci_grid = QGridLayout()
        sci_grid.setSpacing(8)
        self.insert_number_button = QPushButton("n#")
        sci_buttons = [
            (self.insert_number_button, None),
            (QPushButton("("), "("),
            (QPushButton(")"), ")"),
            (QPushButton("^"), "^"),
            (QPushButton("x^2"), "^2"),
            (QPushButton("sqrt"), "sqrt("),
            (QPushButton("sin"), "sin("),
            (QPushButton("cos"), "cos("),
            (QPushButton("tan"), "tan("),
            (QPushButton("log"), "log("),
            (QPushButton("ln"), "ln("),
            (QPushButton("pi"), "pi"),
        ]
        self._formula_insert_buttons: list[tuple[QPushButton, str | None]] = sci_buttons
        for position, (button, _text) in enumerate(sci_buttons):
            button.setObjectName("SmallButton")
            sci_grid.addWidget(button, position // 6, position % 6)
        numbers_layout.addLayout(sci_grid)
        workspace.addWidget(numbers_panel, 0, 1)

        history_panel = QFrame()
        history_panel.setObjectName("Panel")
        history_layout = QVBoxLayout(history_panel)
        history_layout.setContentsMargins(18, 18, 18, 18)
        history_layout.setSpacing(10)

        history_title = QLabel("Tape")
        history_title.setObjectName("PanelTitle")
        self.history_list = QListWidget()
        self.history_list.setObjectName("HistoryList")
        self.history_list.setAlternatingRowColors(False)
        history_layout.addWidget(history_title)
        history_layout.addWidget(self.history_list, 1)

        ocr_panel = QFrame()
        ocr_panel.setObjectName("Panel")
        ocr_layout = QVBoxLayout(ocr_panel)
        ocr_layout.setContentsMargins(18, 18, 18, 18)
        ocr_layout.setSpacing(10)

        ocr_title = QLabel("OCR Text")
        ocr_title.setObjectName("PanelTitle")
        self.ocr_text = QTextEdit()
        self.ocr_text.setObjectName("OcrText")
        self.ocr_text.setReadOnly(True)
        self.ocr_text.setPlaceholderText("Captured text appears here.")
        ocr_layout.addWidget(ocr_title)
        ocr_layout.addWidget(self.ocr_text)

        side_bottom = QGridLayout()
        side_bottom.setSpacing(16)
        side_bottom.addWidget(history_panel, 0, 0)
        side_bottom.addWidget(ocr_panel, 0, 1)
        side_bottom.setColumnStretch(0, 1)
        side_bottom.setColumnStretch(1, 1)
        workspace.addLayout(side_bottom, 1, 1)

        self.capture_button.clicked.connect(self._controller.begin_capture)
        self.copy_button.clicked.connect(self.copy_result)
        self.fit_button.clicked.connect(self.fit_preview_to_width)
        self.actual_button.clicked.connect(self.show_preview_actual_size)
        self.zoom_out_button.clicked.connect(lambda: self.zoom_preview(0.8))
        self.zoom_in_button.clicked.connect(lambda: self.zoom_preview(1.25))
        self.numbers_list.itemChanged.connect(self._number_item_changed)
        self.numbers_list.model().rowsMoved.connect(self._numbers_reordered)
        self.add_button.clicked.connect(lambda: self.set_uniform_operation("+"))
        self.subtract_button.clicked.connect(lambda: self.set_uniform_operation("-"))
        self.multiply_button.clicked.connect(lambda: self.set_uniform_operation("*"))
        self.divide_button.clicked.connect(lambda: self.set_uniform_operation("/"))
        self.apply_formula_button.clicked.connect(self.apply_custom_expression)
        self.formula_input.returnPressed.connect(self.apply_custom_expression)
        for button, text in self._formula_insert_buttons:
            if text is None:
                button.clicked.connect(self.insert_selected_number_placeholder)
            else:
                button.clicked.connect(lambda _checked=False, value=text: self.insert_formula_text(value))

    def fit_preview_to_width(self) -> None:
        image_width = self.preview.image_width()
        if image_width <= 0:
            return

        self._preview_fit_width = True
        available_width = max(1, self.preview_scroll.viewport().width() - 24)
        zoom = available_width / image_width
        self.preview.set_zoom(max(0.15, min(1.5, zoom)))

    def show_preview_actual_size(self) -> None:
        self._preview_fit_width = False
        self.preview.set_zoom(1.0)

    def zoom_preview(self, factor: float) -> None:
        self._preview_fit_width = False
        self.preview.set_zoom(self.preview.zoom() * factor)

    def _edit_number_item(self, item: QListWidgetItem) -> None:
        index = item.data(Qt.ItemDataRole.UserRole)
        if index is not None:
            self.edit_number(int(index))

    def set_uniform_operation(self, operator: str) -> None:
        self._operation_mode = operator
        self._calculate_current_numbers()

    def apply_custom_expression(self) -> None:
        expression = self._expression_with_placeholders()
        try:
            calculation = calculate_expression(
                expression,
                raw_text=self.formula_input.text(),
                mode="custom",
            )
            self._operation_mode = "custom"
            self._show_calculation(calculation, record_history=False)
        except CalculationError as exc:
            self.status_label.setText("Invalid")
            self.expression_label.setText(str(exc))

    def insert_formula_text(self, text: str) -> None:
        self.formula_input.insert(text)
        self.formula_input.setFocus()

    def insert_selected_number_placeholder(self) -> None:
        row = self.numbers_list.currentRow()
        if row < 0:
            row = 0
        self.insert_formula_text(f"n{row + 1}")

    def _number_item_changed(self, item: QListWidgetItem) -> None:
        if self._refreshing_numbers:
            return

        index = item.data(Qt.ItemDataRole.UserRole)
        if index is None:
            return

        number = next((entry for entry in self._numbers if entry.index == int(index)), None)
        if number is None:
            return

        try:
            number.value = clean_number_text(item.text())
            if item.text() != number.value:
                self._refresh_numbers_list()
            self._calculate_current_numbers()
            self.preview.update()
        except CalculationError as exc:
            self.status_label.setText("Invalid")
            self.expression_label.setText(str(exc))
            self._refresh_numbers_list()

    def _numbers_reordered(self, *_args) -> None:
        QTimer.singleShot(0, self._sync_number_order_from_list)

    def _sync_number_order_from_list(self) -> None:
        if self._refreshing_numbers:
            return

        by_index = {number.index: number for number in self._numbers}
        ordered: list[EditableNumber] = []
        for row in range(self.numbers_list.count()):
            index = self.numbers_list.item(row).data(Qt.ItemDataRole.UserRole)
            if index in by_index:
                ordered.append(by_index[int(index)])

        if len(ordered) == len(self._numbers):
            self._numbers = ordered
            self._calculate_current_numbers()
            self.preview.update()

    def _calculate_current_numbers(self) -> None:
        if not self._numbers:
            return

        try:
            if self._operation_mode in {"+", "-", "*", "/"}:
                calculation = calculate_with_operator(
                    [number.value for number in self._numbers],
                    self._operation_mode,
                )
                self._set_formula_text(calculation.expression)
                self._show_calculation(calculation, record_history=False)
            else:
                self.apply_custom_expression()
        except CalculationError as exc:
            self.status_label.setText("Invalid")
            self.expression_label.setText(str(exc))

    def _expression_with_placeholders(self) -> str:
        values = [number.value for number in self._numbers]

        def replace(match) -> str:
            number_index = int(match.group(1)) - 1
            if number_index < 0 or number_index >= len(values):
                raise CalculationError(f"Unknown number reference: n{number_index + 1}")
            return values[number_index]

        try:
            return re.sub(
                r"\bn(\d+)\b",
                replace,
                self.formula_input.text(),
                flags=re.IGNORECASE,
            )
        except CalculationError:
            raise

    def _set_formula_text(self, expression: str) -> None:
        self.formula_input.blockSignals(True)
        self.formula_input.setText(expression)
        self.formula_input.blockSignals(False)

    def _apply_style(self) -> None:
        self.setStyleSheet(
            """
            QWidget#AppWindow {
                background: #eef1f4;
                color: #1d232a;
                font-family: "Segoe UI";
                font-size: 14px;
            }

            QLabel#AppName {
                color: #151a20;
                font-size: 25px;
                font-weight: 700;
            }

            QLabel#Subtitle {
                color: #65717d;
                font-size: 13px;
            }

            QLabel#StatusBadge {
                background: #e4f4ef;
                border: 1px solid #b9dbcf;
                border-radius: 7px;
                color: #106451;
                font-size: 12px;
                font-weight: 600;
                padding: 6px 12px;
            }

            QFrame#DisplayPanel {
                background: #101820;
                border: 1px solid #0b1117;
                border-radius: 8px;
            }

            QLabel#DisplayTitle {
                color: #91a0ae;
                font-size: 12px;
                font-weight: 700;
                letter-spacing: 0px;
            }

            QLabel#ModePill {
                background: #1b2a35;
                border: 1px solid #2f4352;
                border-radius: 7px;
                color: #bbf7d0;
                font-size: 12px;
                font-weight: 650;
                padding: 6px 12px;
            }

            QFrame#Panel {
                background: #ffffff;
                border: 1px solid #d6dde4;
                border-radius: 8px;
            }

            QLabel#PanelTitle {
                color: #323a43;
                font-size: 13px;
                font-weight: 700;
            }

            QLabel#ResultValue {
                color: #f8fafc;
                font-size: 64px;
                font-weight: 760;
                padding: 2px 0 0 0;
            }

            QLabel#Expression {
                color: #dce6ee;
                background: #17212b;
                border: 1px solid #2c3d4b;
                border-radius: 6px;
                padding: 11px 13px;
            }

            QPushButton {
                border: 1px solid #bfc9d4;
                border-radius: 7px;
                background: #ffffff;
                color: #242a31;
                font-weight: 650;
                padding: 10px 16px;
                min-width: 88px;
            }

            QPushButton:hover {
                background: #f5f8fa;
                border-color: #8d9cab;
            }

            QPushButton:pressed {
                background: #e7edf2;
            }

            QPushButton:disabled {
                background: #e7ebef;
                border-color: #d4dce3;
                color: #8f9aa5;
            }

            QPushButton#PrimaryButton {
                background: #0f766e;
                border-color: #0f766e;
                color: #ffffff;
            }

            QPushButton#PrimaryButton:hover {
                background: #0d665f;
                border-color: #0d665f;
            }

            QPushButton#SmallButton {
                min-width: 36px;
                min-height: 24px;
                max-height: 30px;
                padding: 5px 7px;
            }

            QPushButton#CalcButton {
                min-width: 38px;
                min-height: 26px;
                max-height: 34px;
                padding: 7px 9px;
                font-size: 15px;
            }

            QLineEdit#FormulaInput {
                background: #0f1720;
                border: 1px solid #2c3d4b;
                border-radius: 7px;
                color: #f8fafc;
                font-family: "Consolas";
                font-size: 14px;
                min-height: 30px;
                max-height: 34px;
                padding: 7px 10px;
            }

            QWidget#Preview {
                background: #f6f8fa;
            }

            QScrollArea#PreviewScroll,
            QListWidget#NumbersList,
            QListWidget#HistoryList,
            QTextEdit#OcrText {
                background: #f6f8fa;
                border: 1px solid #dce3ea;
                border-radius: 7px;
                color: #2b333b;
                selection-background-color: #cce9df;
                selection-color: #17211f;
            }

            QTextEdit#OcrText {
                padding: 8px;
            }

            QListWidget#NumbersList,
            QListWidget#HistoryList {
                padding: 8px;
            }

            QListWidget#NumbersList {
                font-size: 12px;
            }

            QListWidget#NumbersList::item {
                border-bottom: 1px solid #e4eaf0;
                min-height: 20px;
                padding: 4px 6px;
            }

            QListWidget#HistoryList::item {
                border-bottom: 1px solid #e4eaf0;
                padding: 7px 6px;
            }

            QListWidget#NumbersList::item:selected,
            QListWidget#HistoryList::item:selected {
                background: #d8efe8;
                border-radius: 4px;
            }
            """
        )

    def set_processing(self) -> None:
        self.status_label.setText("Reading")
        self.capture_button.setEnabled(False)
        self.copy_button.setEnabled(False)
        self.expression_label.setText("Processing selection...")
        self.preview.set_notice("Reading selection...")
        self.numbers_list.clear()

    def set_ready(self) -> None:
        self.status_label.setText("Ready")
        self.capture_button.setEnabled(True)
        self.copy_button.setEnabled(self._last_calculation is not None)

    def set_capture_error(
        self,
        message: str,
        image: Image.Image | None = None,
        ocr_result: OcrResult | None = None,
    ) -> None:
        self._last_calculation = None
        self._base_calculation = None
        self.status_label.setText("Check")
        self.result_value.setText("--")
        self.mode_label.setText("Error")
        self.expression_label.setText(message)
        self.ocr_text.setPlainText(ocr_result.text if ocr_result else "")
        self.capture_button.setEnabled(True)
        self.copy_button.setEnabled(False)

        if image is not None and ocr_result is not None:
            self._numbers = _editable_numbers(ocr_result.numbers)
            self.preview.set_capture(image, self._numbers)
            self._refresh_numbers_list()
            QTimer.singleShot(0, self.fit_preview_to_width)
        elif image is not None:
            self._numbers = []
            self.preview.set_capture(image, [])
            self._refresh_numbers_list()
            QTimer.singleShot(0, self.fit_preview_to_width)
        else:
            self._numbers = []
            self.preview.set_notice("No capture available")
            self._refresh_numbers_list()

    def set_capture_result(
        self,
        image: Image.Image,
        ocr_result: OcrResult,
        calculation: Calculation,
    ) -> None:
        self._base_calculation = calculation
        self._numbers = _editable_numbers(ocr_result.numbers)
        self._ocr_raw_text = ocr_result.text
        self.preview.set_capture(image, self._numbers)
        self._refresh_numbers_list()
        self.ocr_text.setPlainText(ocr_result.text)
        self._operation_mode = "+"
        if self._numbers:
            calculation = calculate_with_operator(
                [number.value for number in self._numbers],
                "+",
            )
            self._set_formula_text(calculation.expression)
        else:
            self._set_formula_text(calculation.expression)
        self._show_calculation(calculation, record_history=True)
        QTimer.singleShot(0, self.fit_preview_to_width)

    def edit_number(self, index: int) -> None:
        number = next((item for item in self._numbers if item.index == index), None)
        if number is None:
            return

        new_value, accepted = QInputDialog.getText(
            self,
            "Edit Number",
            "Number",
            text=number.value,
        )
        if not accepted:
            return

        try:
            number.value = clean_number_text(new_value)
            self._calculate_current_numbers()
            self._refresh_numbers_list()
            self.preview.update()
        except CalculationError as exc:
            self.status_label.setText("Invalid")
            self.expression_label.setText(str(exc))

    def copy_result(self) -> None:
        if self._last_calculation is None:
            return
        QGuiApplication.clipboard().setText(self._last_calculation.display)
        self.status_label.setText("Copied")

    def _show_calculation(self, calculation: Calculation, record_history: bool) -> None:
        self._last_calculation = calculation
        self.status_label.setText("Copied")
        self.mode_label.setText(calculation.mode.title())
        self.result_value.setText(calculation.display)
        self.expression_label.setText(
            f"{calculation.mode.title()}: {calculation.expression} = {calculation.display}"
        )
        self.capture_button.setEnabled(True)
        self.copy_button.setEnabled(True)
        QGuiApplication.clipboard().setText(calculation.display)

        if record_history:
            self._prepend_history(calculation)

    def _prepend_history(self, calculation: Calculation) -> None:
        item = QListWidgetItem(
            f"{calculation.display}    {calculation.mode}: {calculation.expression}"
        )
        item.setToolTip(self._ocr_raw_text or calculation.raw_text)
        self.history_list.insertItem(0, item)
        while self.history_list.count() > 8:
            self.history_list.takeItem(self.history_list.count() - 1)

    def _refresh_numbers_list(self) -> None:
        self._refreshing_numbers = True
        self.numbers_list.clear()
        if not self._numbers:
            item = QListWidgetItem("No numbers detected")
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEnabled)
            self.numbers_list.addItem(item)
            self._refreshing_numbers = False
            return

        for order, number in enumerate(self._numbers, start=1):
            item = QListWidgetItem(number.value)
            item.setData(Qt.ItemDataRole.UserRole, number.index)
            item.setToolTip(f"n{order} from OCR line: {number.line_text}")
            item.setFlags(
                item.flags()
                | Qt.ItemFlag.ItemIsEditable
                | Qt.ItemFlag.ItemIsDragEnabled
                | Qt.ItemFlag.ItemIsDropEnabled
            )
            self.numbers_list.addItem(item)
        self._refreshing_numbers = False


class AppController:
    def __init__(self) -> None:
        self.reader: RapidOcrReader | None = None
        self.window = MainWindow(self)
        self.overlay = SelectionOverlay(self._handle_selection, self._handle_cancel)

    def start(self) -> None:
        self.window.show()
        self.window.raise_()
        self.window.activateWindow()

    def begin_capture(self) -> None:
        self.window.hide()
        QTimer.singleShot(160, self.overlay.start)

    def _handle_cancel(self) -> None:
        self.window.set_ready()
        self.start()

    def _handle_selection(self, selection: QRect) -> None:
        self.start()
        self.window.set_processing()
        QTimer.singleShot(100, lambda: self._process_selection(selection))

    def _process_selection(self, selection: QRect) -> None:
        image: Image.Image | None = None
        ocr_result: OcrResult | None = None
        try:
            rect = CaptureRect(
                left=selection.left(),
                top=selection.top(),
                width=selection.width(),
                height=selection.height(),
            )
            image = capture_region(rect)

            if self.reader is None:
                self.reader = RapidOcrReader()

            ocr_result = self.reader.read_result(image)
            calculation = calculate_from_text(ocr_result.text)
            self.window.set_capture_result(image, ocr_result, calculation)
        except Exception as exc:
            self.window.set_capture_error(str(exc), image, ocr_result)


def _editable_numbers(numbers: list[OcrNumber]) -> list[EditableNumber]:
    editable: list[EditableNumber] = []
    for number in numbers:
        x, y, width, height = number.rect
        editable.append(
            EditableNumber(
                index=number.index,
                value=_safe_clean_number(number.text),
                rect=QRect(x, y, width, height),
                confidence=number.confidence,
                line_text=number.line_text,
            )
        )
    return editable


def _safe_clean_number(text: str) -> str:
    try:
        return clean_number_text(text)
    except CalculationError:
        return text


def _pil_to_pixmap(image: Image.Image) -> QPixmap:
    rgba = image.convert("RGBA")
    data = rgba.tobytes("raw", "RGBA")
    qimage = QImage(
        data,
        rgba.width,
        rgba.height,
        rgba.width * 4,
        QImage.Format.Format_RGBA8888,
    )
    return QPixmap.fromImage(qimage.copy())


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("DragCalculator")
    app.setStyle("Fusion")
    controller = AppController()
    controller.start()
    return app.exec()
