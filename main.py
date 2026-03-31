import sys
import os
import ctypes
import ctypes.wintypes
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton,
                             QColorDialog, QSlider, QLabel, QHBoxLayout, QFrame,
                             QFileDialog, QMessageBox, QGraphicsDropShadowEffect)
from PyQt6.QtCore import Qt, QPoint, QRect, QTimer, QMarginsF, QSizeF
from PyQt6.QtGui import (QPainter, QPen, QColor, QKeySequence, QShortcut,
                          QImage, QPdfWriter, QPageLayout, QPageSize, QFont)

# ─── Windows API Constants ───────────────────────────────────────────────────
WS_EX_LAYERED       = 0x00080000
WS_EX_TRANSPARENT   = 0x00000020
WS_EX_NOACTIVATE    = 0x08000000
GWL_EXSTYLE         = -20
SWP_NOMOVE          = 0x0002
SWP_NOSIZE          = 0x0001
SWP_NOZORDER        = 0x0004
SWP_FRAMECHANGED    = 0x0020
HWND_TOPMOST        = -1

user32 = ctypes.windll.user32

if sys.maxsize > 2**32:
    GetWindowLongPtr = user32.GetWindowLongPtrW
    GetWindowLongPtr.restype = ctypes.c_void_p
    GetWindowLongPtr.argtypes = [ctypes.c_void_p, ctypes.c_int]
    SetWindowLongPtr = user32.SetWindowLongPtrW
    SetWindowLongPtr.restype = ctypes.c_void_p
    SetWindowLongPtr.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
else:
    GetWindowLongPtr = user32.GetWindowLongW
    GetWindowLongPtr.restype = ctypes.c_long
    GetWindowLongPtr.argtypes = [ctypes.c_void_p, ctypes.c_int]
    SetWindowLongPtr = user32.SetWindowLongW
    SetWindowLongPtr.restype = ctypes.c_long
    SetWindowLongPtr.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_long]

SetWindowPos = user32.SetWindowPos
SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int,
                         ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_uint]


def _set_click_through(hwnd, enabled: bool):
    """Enable or disable WS_EX_TRANSPARENT on a window handle."""
    ex = GetWindowLongPtr(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
    if enabled:
        ex |= WS_EX_TRANSPARENT
    else:
        ex &= ~WS_EX_TRANSPARENT
    SetWindowLongPtr(ctypes.c_void_p(hwnd), GWL_EXSTYLE, ctypes.c_void_p(ex))
    flags = SWP_NOMOVE | SWP_NOSIZE | SWP_NOZORDER | SWP_FRAMECHANGED
    SetWindowPos(ctypes.c_void_p(hwnd), ctypes.c_void_p(0), 0, 0, 0, 0, flags)


# ─── Overlay (Canvas) ────────────────────────────────────────────────────────
class OverlayWindow(QWidget):
    """Full-screen transparent canvas for drawing. Starts click-through."""

    def __init__(self):
        super().__init__()
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)

        # Cover all monitors
        rect = QRect()
        for s in QApplication.screens():
            rect = rect.united(s.geometry())
        self.setGeometry(rect)

        # Drawing state
        self.paths = []              # list of (points, color, thickness)
        self.current_path = []
        self.current_color = QColor(255, 0, 0)
        self.current_thickness = 5
        self.bg_color = QColor(0, 0, 0)  # default slide background: black

        # Slides stored in memory
        self.slides = []

        # Start in MOUSE mode (click-through)
        self.drawing_active = False

    def showEvent(self, event):
        super().showEvent(event)
        QTimer.singleShot(100, self._make_click_through)

    def _make_click_through(self):
        hwnd = int(self.winId())
        _set_click_through(hwnd, True)

    # ── Paint ─────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.drawing_active:
            painter.fillRect(self.rect(), QColor(255, 255, 255, 1))

        for path, color, thickness in self.paths:
            pen = QPen(color, thickness, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            for i in range(len(path) - 1):
                painter.drawLine(path[i], path[i + 1])

        if self.current_path:
            pen = QPen(self.current_color, self.current_thickness,
                       Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                       Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            for i in range(len(self.current_path) - 1):
                painter.drawLine(self.current_path[i], self.current_path[i + 1])

    # ── Mouse handling ────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drawing_active:
            self.current_path.append(event.position().toPoint())
            self.update()

    def mouseMoveEvent(self, event):
        if event.buttons() & Qt.MouseButton.LeftButton and self.drawing_active:
            self.current_path.append(event.position().toPoint())
            self.update()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and self.drawing_active:
            if self.current_path:
                self.paths.append((list(self.current_path),
                                   QColor(self.current_color),
                                   self.current_thickness))
                self.current_path = []
            self.update()

    # ── Public API ────────────────────────────────────────────────────────
    def set_draw_mode(self, active: bool):
        self.drawing_active = active
        hwnd = int(self.winId())
        _set_click_through(hwnd, not active)
        self.update()

    def clear_canvas(self):
        self.paths.clear()
        self.current_path.clear()
        self.update()

    def undo(self):
        if self.paths:
            self.paths.pop()
            self.update()

    def set_color(self, color):
        self.current_color = color

    def set_thickness(self, thickness):
        self.current_thickness = thickness

    def set_bg_color(self, color):
        self.bg_color = color

    # ── Slide management ──────────────────────────────────────────────────
    def _render_current_to_image(self):
        img = QImage(self.size(), QImage.Format.Format_ARGB32)
        img.fill(self.bg_color)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for path, color, thickness in self.paths:
            pen = QPen(color, thickness, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            for i in range(len(path) - 1):
                painter.drawLine(path[i], path[i + 1])
        painter.end()
        return img

    def add_slide(self):
        if not self.paths:
            return False, "Canvas is empty — write something first!"
        img = self._render_current_to_image()
        self.slides.append(img)
        self.clear_canvas()
        return True, ""

    def discard_last_slide(self):
        if self.slides:
            self.slides.pop()
            return True
        return False

    def export_pdf(self):
        if not self.slides:
            return False, "No slides to export. Add slides first!"
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_name = os.path.join(os.path.expanduser("~/Desktop"), f"my_notes_{ts}.pdf")
        filepath, _ = QFileDialog.getSaveFileName(None, "Save Notes as PDF", default_name, "PDF Files (*.pdf)")
        if not filepath:
            return False, "Export cancelled."

        first = self.slides[0]
        w_mm = first.width() * 0.2646
        h_mm = first.height() * 0.2646

        writer = QPdfWriter(filepath)
        page_size = QPageSize(QSizeF(w_mm, h_mm), QPageSize.Unit.Millimeter, "Screen")
        layout = QPageLayout(page_size, QPageLayout.Orientation.Landscape, QMarginsF(0, 0, 0, 0))
        writer.setPageLayout(layout)
        writer.setResolution(96)

        painter = QPainter(writer)
        for i, slide_img in enumerate(self.slides):
            if i > 0:
                writer.newPage()
            target = QRect(0, 0, writer.width(), writer.height())
            painter.drawImage(target, slide_img)
        painter.end()
        return True, filepath


# ─── Toolbar  ─────────────────────────────────────────────────────────────────
class ToolbarWindow(QWidget):
    """Floating toolbar. Highly aesthetic frontend."""

    def __init__(self, overlay: OverlayWindow):
        super().__init__()
        self.overlay = overlay
        
        # Enable dropping shadows behind frameless window
        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint |
            Qt.WindowType.WindowStaysOnTopHint |
            Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)

        self.is_expanded = False
        self.drag_pos = QPoint()

        self._build_ui()

        # Position at bottom right of primary screen
        scr = QApplication.primaryScreen()
        if scr:
            g = scr.geometry()
            self.move(g.width() - 280, g.height() // 2 - 150)

        # ── Global hotkey (F9 ONLY) ─────────────────────────
        shortcut = QShortcut(QKeySequence(Qt.Key.Key_F9), self)
        shortcut.setContext(Qt.ShortcutContext.ApplicationShortcut)
        shortcut.activated.connect(self.toggle_mode)

    # ── UI construction ───────────────────────────────────────────────────
    def _build_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(15, 15, 15, 15)  # margin for shadow

        # ── Collapsed circle ──────────────────────────────────────────────
        self.collapsed_widget = QWidget()
        clayout = QVBoxLayout(self.collapsed_widget)
        clayout.setContentsMargins(0, 0, 0, 0)

        self.btn_circle = QPushButton("🖱️")
        self.btn_circle.setFixedSize(65, 65)
        # Drop shadow for the orb
        shadow_orb = QGraphicsDropShadowEffect()
        shadow_orb.setBlurRadius(18)
        shadow_orb.setColor(QColor(0, 0, 0, 100))
        shadow_orb.setOffset(0, 4)
        self.btn_circle.setGraphicsEffect(shadow_orb)
        
        self._style_circle_mouse()
        self.btn_circle.clicked.connect(self.expand_menu)
        clayout.addWidget(self.btn_circle)

        # ── Expanded panel ────────────────────────────────────────────────
        self.expanded_widget = QFrame()
        self.expanded_widget.setObjectName("ExpandedPanel")
        
        # Professional Glassmorphism & Modern CSS
        self.expanded_widget.setStyleSheet("""
            QFrame#ExpandedPanel {
                background-color: rgba(22, 22, 24, 240);
                border: 1px solid rgba(255, 255, 255, 25);
                border-radius: 16px;
            }
            QPushButton {
                background-color: rgba(255, 255, 255, 12);
                color: #ffffff;
                border: 1px solid rgba(255, 255, 255, 12);
                padding: 10px;
                border-radius: 8px;
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-size: 10pt;
                font-weight: 500;
                text-align: center;
            }
            QPushButton:hover {
                background-color: rgba(255, 255, 255, 25);
                border: 1px solid rgba(255, 255, 255, 30);
            }
            QPushButton:pressed {
                background-color: rgba(255, 255, 255, 8);
            }
            QLabel {
                color: #d1d1d1;
                font-family: 'Segoe UI', system-ui, sans-serif;
                font-weight: 500;
            }
            QSlider::groove:horizontal {
                height: 6px;
                background: rgba(255, 255, 255, 20);
                border-radius: 3px;
            }
            QSlider::handle:horizontal {
                background: #0a84ff;
                width: 14px;
                height: 14px;
                margin: -4px 0;
                border-radius: 7px;
            }
            QSlider::handle:horizontal:hover {
                background: #409cff;
            }
        """)

        # Drop shadow for the main panel
        shadow_panel = QGraphicsDropShadowEffect()
        shadow_panel.setBlurRadius(25)
        shadow_panel.setColor(QColor(0, 0, 0, 150))
        shadow_panel.setOffset(0, 6)
        self.expanded_widget.setGraphicsEffect(shadow_panel)

        elayout = QVBoxLayout(self.expanded_widget)
        elayout.setContentsMargins(18, 18, 18, 18)
        elayout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title = QLabel("≡  OnScreen Pen")
        title.setStyleSheet("color: #ffffff; font-size: 11pt; font-weight: 600; letter-spacing: 0.5px;")
        
        btn_collapse = QPushButton("✕")
        btn_collapse.setFixedSize(28, 28)
        btn_collapse.setStyleSheet("""
            QPushButton {
                background: transparent; border: none; font-size: 13px; color: #999;
                border-radius: 14px; padding: 0px;
            }
            QPushButton:hover { background: rgba(255, 255, 255, 20); color: #fff; }
        """)
        btn_collapse.clicked.connect(self.collapse_menu)
        header.addWidget(title)
        header.addStretch()
        header.addWidget(btn_collapse)
        elayout.addLayout(header)

        # Mode toggle (starts as "Mouse Mode" = passthrough)
        self.btn_mode = QPushButton("🖱️  Mouse Mode (F9)")
        self.btn_mode.setStyleSheet("background-color: #30d158; color: #000000; font-weight: bold; border: none;")
        self.btn_mode.clicked.connect(self.toggle_mode)
        elayout.addWidget(self.btn_mode)

        # Separator 1
        elayout.addWidget(self._create_separator())

        # Colour picker
        self.btn_color = QPushButton("🎨 Pick Pen Color")
        self.btn_color.clicked.connect(self.pick_color)
        elayout.addWidget(self.btn_color)

        # Thickness slider
        slayout = QHBoxLayout()
        slabel = QLabel("Thickness")
        slabel.setStyleSheet("font-size: 9pt;")
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setMinimum(1)
        self.slider.setMaximum(50)
        self.slider.setValue(self.overlay.current_thickness)
        self.slider.valueChanged.connect(self.overlay.set_thickness)
        
        self.size_val = QLabel(f"{self.overlay.current_thickness}")
        self.size_val.setFixedWidth(24)
        self.size_val.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.size_val.setStyleSheet("font-weight: bold; color: #0a84ff; font-size: 9pt;")
        self.slider.valueChanged.connect(lambda v: self.size_val.setText(str(v)))

        slayout.addWidget(slabel)
        slayout.addWidget(self.slider)
        slayout.addWidget(self.size_val)
        elayout.addLayout(slayout)

        # Undo & Clear Actions (Row)
        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        btn_undo = QPushButton("↩️ Undo Stroke")
        btn_undo.clicked.connect(self.overlay.undo)
        btn_clear = QPushButton("🗑️ Clear All")
        btn_clear.clicked.connect(self.overlay.clear_canvas)
        action_row.addWidget(btn_undo)
        action_row.addWidget(btn_clear)
        elayout.addLayout(action_row)
        
        # Separator 2
        elayout.addWidget(self._create_separator())

        # BG Color for Slides
        self.btn_bg = QPushButton("🖼️ Slide BG (Black)")
        self.btn_bg.clicked.connect(self.pick_bg_color)
        elayout.addWidget(self.btn_bg)

        # Add Slide
        self.btn_add = QPushButton("📄 Add Slide to PDF")
        self.btn_add.setStyleSheet("background-color: #0a84ff; color: #ffffff; font-weight: bold; border: none;")
        self.btn_add.clicked.connect(self.add_slide)
        elayout.addWidget(self.btn_add)
        
        # Slide counter
        self.lbl_slides = QLabel("0 slides in memory")
        self.lbl_slides.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_slides.setStyleSheet("font-size: 8.5pt; color: #888888; margin-bottom: 2px;")
        elayout.addWidget(self.lbl_slides)

        # Export PDF
        btn_pdf = QPushButton("📕 Save & Export PDF")
        btn_pdf.setStyleSheet("background-color: #ff453a; color: #ffffff; font-weight: bold; border: none;")
        btn_pdf.clicked.connect(self.export_pdf)
        elayout.addWidget(btn_pdf)

        # Clear Canvas
        elayout.addSpacing(6)
        btn_exit = QPushButton("Exit App")
        btn_exit.setStyleSheet("""
            QPushButton {
                background: transparent; color: #ff453a; font-weight: normal; border: 1px solid rgba(255, 69, 58, 80);
            }
            QPushButton:hover { background: rgba(255, 69, 58, 20); }
        """)
        btn_exit.clicked.connect(QApplication.instance().quit)
        elayout.addWidget(btn_exit)

        self.main_layout.addWidget(self.collapsed_widget)
        self.main_layout.addWidget(self.expanded_widget)

        # Start collapsed
        self.collapse_menu()

    def _create_separator(self):
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet("border-top: 1px solid rgba(255, 255, 255, 20); margin: 4px 0px;")
        return line

    # ── Expand / Collapse ─────────────────────────────────────────────────
    def expand_menu(self):
        self.is_expanded = True
        self.collapsed_widget.hide()
        self.expanded_widget.show()
        # Accommodate drop shadow padding (15px each side)
        self.resize(270, 520)

    def collapse_menu(self):
        self.is_expanded = False
        self.expanded_widget.hide()
        self.collapsed_widget.show()
        self.resize(95, 95)  # 65 + 30px shadow padding

    # ── Mode toggle ───────────────────────────────────────────────────────
    def toggle_mode(self):
        if self.overlay.drawing_active:
            # Currently drawing → switch to mouse mode
            self.overlay.set_draw_mode(False)
            self.btn_mode.setText("🖱️  Mouse Mode (F9)")
            self.btn_mode.setStyleSheet("background-color: #30d158; color: #000000; font-weight: bold; border: none;")
            self.btn_circle.setText("🖱️")
            self._style_circle_mouse()
        else:
            # Currently mouse → switch to draw mode
            self.overlay.set_draw_mode(True)
            self.btn_mode.setText("✍  Draw Mode (F9)")
            self.btn_mode.setStyleSheet("background-color: #0a84ff; color: #ffffff; font-weight: bold; border: none;")
            self.btn_circle.setText("✍")
            self._style_circle_draw()

    # ── Actions ───────────────────────────────────────────────────────────
    def pick_color(self):
        color = QColorDialog.getColor(self.overlay.current_color, self, "Select Pen Color")
        if color.isValid():
            self.overlay.set_color(color)
            
    def pick_bg_color(self):
        color = QColorDialog.getColor(self.overlay.bg_color, self, "Select Slide Background Color")
        if color.isValid():
            self.overlay.set_bg_color(color)
            self.btn_bg.setText(f"🖼️ Slide BG ({color.name()})")

    def add_slide(self):
        ok, msg = self.overlay.add_slide()
        if ok:
            count = len(self.overlay.slides)
            self.lbl_slides.setText(f"{count} slide{'s' if count != 1 else ''} in memory")
            self.lbl_slides.setStyleSheet("font-size: 8.5pt; color: #30d158; font-weight: bold;")
            self.btn_add.setText("✓ Added to PDF")
            self.btn_add.setStyleSheet("background-color: #30d158; color: #000000; font-weight: bold; border: none;")
            
            QTimer.singleShot(1500, self._reset_add_button)
        else:
            QMessageBox.warning(self, "Add Slide", msg)

    def _reset_add_button(self):
        self.lbl_slides.setStyleSheet("font-size: 8.5pt; color: #888888; font-weight: normal;")
        self.btn_add.setText("📄 Add Slide to PDF")
        self.btn_add.setStyleSheet("background-color: #0a84ff; color: #ffffff; font-weight: bold; border: none;")

    def export_pdf(self):
        ok, msg = self.overlay.export_pdf()
        if ok:
            QMessageBox.information(self, "PDF Export", f"Successfully exported PDF to:\n{msg}")
        else:
            QMessageBox.warning(self, "PDF Export", msg)

    # ── Helpers ───────────────────────────────────────────────────────────
    def _style_circle_mouse(self):
        self.btn_circle.setStyleSheet("""
            QPushButton {
                background-color: #30d158; color: #000000;
                border-radius: 32px; font-size: 30px;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }
            QPushButton:hover { background-color: #2ed158; transform: scale(1.05); }
        """)

    def _style_circle_draw(self):
        self.btn_circle.setStyleSheet("""
            QPushButton {
                background-color: #0a84ff; color: #ffffff;
                border-radius: 32px; font-size: 30px;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }
            QPushButton:hover { background-color: #409cff; }
        """)

    # ── Dragging (applied to whole window) ────────────────────────────────
    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.drag_pos = event.globalPosition().toPoint() - self.frameGeometry().topLeft()
            event.accept()

    def mouseMoveEvent(self, event):
        if event.buttons() == Qt.MouseButton.LeftButton:
            self.move(event.globalPosition().toPoint() - self.drag_pos)
            event.accept()


# ─── Entry Point ──────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    
    # Establish a clean base font
    app.setFont(QFont("Segoe UI", 9))

    overlay = OverlayWindow()
    toolbar = ToolbarWindow(overlay)

    overlay.show()
    toolbar.show()

    # Ensure toolbar is above the overlay in the z-order
    toolbar.raise_()
    toolbar.activateWindow()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
