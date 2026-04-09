import sys
import os
import ctypes
import ctypes.wintypes
from datetime import datetime
from PyQt6.QtWidgets import (QApplication, QWidget, QVBoxLayout, QPushButton,
                             QColorDialog, QSlider, QLabel, QHBoxLayout, QFrame,
                             QFileDialog, QMessageBox, QGraphicsDropShadowEffect,
                             QComboBox, QDialog, QScrollArea, QGridLayout, QSizePolicy)
from PyQt6.QtCore import Qt, QPoint, QRect, QTimer, QMarginsF, QSizeF, QPointF, QRectF, QSettings, QEvent
from PyQt6.QtGui import (QPainter, QPen, QColor, QPixmap, QPainterPath,
                          QImage, QPdfWriter, QPageLayout, QPageSize, QFont)
from PyQt6.QtWidgets import QColorDialog, QDialogButtonBox, QFormLayout
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
        self.setAttribute(Qt.WidgetAttribute.WA_AcceptTouchEvents, True)

        self.settings = QSettings("GaneshJoshi", "OnScreenPen")

        # Cover all monitors
        rect = QRect()
        for s in QApplication.screens():
            rect = rect.united(s.geometry())
        self.setGeometry(rect)

        # Buffer for fast rendering
        self.buffer = QPixmap(rect.size())
        self.buffer.fill(Qt.GlobalColor.transparent)

        # Load configurations
        pen_color = self.settings.value("pen_color", "#ff0000")
        bg_color = self.settings.value("bg_color", "#ffffff")
        self.app_mode = self.settings.value("app_mode", "Overlay")
        self.ui_theme = self.settings.value("ui_theme", "Text")

        # Drawing state
        self.paths = []              # list of (points, color, thickness, is_eraser)
        self.current_path = []
        self.current_path_painter_path = QPainterPath()
        self.current_color = QColor(pen_color)
        self.current_thickness = 5
        self.bg_color = QColor(bg_color)
        self.is_erasing = False
        self.active_tool_eraser = False

        # Grid state
        self.grid_mode = "Blank/Plain"  # "Blank/Plain", "Lined/Ruled", "Dot Grid", "Square/Grid"

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

    def _create_smooth_path(self, points):
        path = QPainterPath()
        if not points:
            return path
        path.moveTo(points[0])
        if len(points) == 1:
            path.lineTo(points[0] + QPointF(0.1, 0.1))
            return path
        if len(points) == 2:
            path.lineTo(points[1])
            return path
        for i in range(1, len(points) - 1):
            mid = QPointF((points[i].x() + points[i+1].x()) / 2.0, (points[i].y() + points[i+1].y()) / 2.0)
            path.quadTo(points[i], mid)
        path.lineTo(points[-1])
        return path

    # ── Paint ─────────────────────────────────────────────────────────────
    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        if self.app_mode == "Whiteboard" and self.drawing_active:
            painter.fillRect(event.rect(), self.bg_color)
        elif self.drawing_active:
            painter.fillRect(event.rect(), QColor(255, 255, 255, 1))
            
        if self.drawing_active:
            # Draw grid if active within repainted region only to maximize FPS
            if self.grid_mode != "Blank/Plain":
                step = 40
                r = event.rect()
                
                if self.grid_mode == "Lined/Ruled":
                    margin_left = 120
                    header_top = 100
                    h_pen = QPen(QColor(0, 0, 0, 35), 1)
                    painter.setPen(h_pen)
                    start_y = max(header_top, int(r.top() / step) * step)
                    for y in range(start_y, r.bottom() + step, step):
                        painter.drawLine(r.left(), y, r.right(), y)
                        
                    if r.left() <= margin_left <= r.right():
                        v_pen = QPen(QColor(255, 69, 58, 80), 2)
                        painter.setPen(v_pen)
                        painter.drawLine(margin_left, r.top(), margin_left, r.bottom())
                    
                elif self.grid_mode == "Dot Grid":
                    d_pen = QPen(QColor(0, 0, 0, 50), 3)
                    d_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                    painter.setPen(d_pen)
                    start_x = max(step, int(r.left() / step) * step)
                    start_y = max(step, int(r.top() / step) * step)
                    for x in range(start_x, r.right() + step, step):
                        for y in range(start_y, r.bottom() + step, step):
                            painter.drawPoint(x, y)
                            
                elif self.grid_mode == "Square/Grid":
                    grid_pen = QPen(QColor(0, 0, 0, 20), 1)
                    painter.setPen(grid_pen)
                    start_x = max(0, int(r.left() / step) * step)
                    for x in range(start_x, r.right() + step, step):
                        painter.drawLine(x, r.top(), x, r.bottom())
                    start_y = max(0, int(r.top() / step) * step)
                    for y in range(start_y, r.bottom() + step, step):
                        painter.drawLine(r.left(), y, r.right(), y)

        # Draw cached strokes buffer perfectly instantly
        painter.drawPixmap(event.rect(), self.buffer, event.rect())

        if not self.current_path_painter_path.isEmpty():
            pen = QPen(self.current_color, self.current_thickness,
                       Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                       Qt.PenJoinStyle.RoundJoin)
            # If erasing, it's drawn normally here but maybe red or translucent to show eraser path? 
            # Actually just drawing it with compositionmode clear is better if we draw it directly.
            # But the 'current_path_painter_path' draws on top of everything. If it's the eraser, let's draw it as a translucent red stroke.
            if self.is_erasing:
                pen.setColor(QColor(255, 0, 0, 100))
            painter.setPen(pen)
            painter.drawPath(self.current_path_painter_path)

    # ── Touch handling ────────────────────────────────────────────────────
    def event(self, event):
        if event.type() in (QEvent.Type.TouchBegin, QEvent.Type.TouchUpdate, QEvent.Type.TouchEnd):
            self.handle_touch(event)
            return True
        return super().event(event)

    def handle_touch(self, event):
        if not self.drawing_active:
            return
            
        points = event.points()
        if not points:
            return

        # Centralize touch points
        center_x = sum(p.position().x() for p in points) / len(points)
        center_y = sum(p.position().y() for p in points) / len(points)
        pos = QPointF(center_x, center_y)

        if event.type() == QEvent.Type.TouchBegin:
            self.current_path = [pos]
            self.current_path_painter_path = self._create_smooth_path(self.current_path)
            # If 3 or more fingers, use eraser mode!
            self.is_erasing = len(points) >= 3
            if self.is_erasing:
                self.current_thickness = 40  # Big eraser
            self.update()

        elif event.type() == QEvent.Type.TouchUpdate:
            if not self.current_path:
                self.current_path = [pos]
            self.current_path.append(pos)
            
            if len(points) >= 3:
                self.is_erasing = True
                self.current_thickness = 40

            if len(self.current_path) >= 2:
                p1 = self.current_path[-2]
                rect = QRectF(p1, pos).normalized()
                margin = self.current_thickness * 2
                rect.adjust(-margin, -margin, margin, margin)
                self.current_path_painter_path = self._create_smooth_path(self.current_path)
                self.update(rect.toRect())

        elif event.type() == QEvent.Type.TouchEnd:
            self._commit_current_path()

    # ── Mouse handling ────────────────────────────────────────────────────
    def mousePressEvent(self, event):
        if hasattr(self, 'toolbar'):
            # Always ensure toolbar stays on top whenever canvas is clicked
            self.toolbar.raise_()
            # If the user somehow clicked inside the toolbar area, ignore it
            if self.toolbar.geometry().contains(event.globalPosition().toPoint()):
                return

        if event.button() == Qt.MouseButton.LeftButton and self.drawing_active:
            self.current_path = [event.position()]
            self.current_path_painter_path = self._create_smooth_path(self.current_path)
            self.is_erasing = self.active_tool_eraser
            pen_color = self.settings.value("pen_color", "#ff0000")
            self.current_color = QColor(pen_color)
            self.update()

    def mouseMoveEvent(self, event):
        if hasattr(self, 'toolbar'):
            if self.toolbar.geometry().contains(event.globalPosition().toPoint()):
                return
                
        if event.buttons() & Qt.MouseButton.LeftButton and self.drawing_active:
            pos = event.position()
            self.current_path.append(pos)
            
            if self.active_tool_eraser:
                self.is_erasing = True
                
            if len(self.current_path) >= 2:
                p1 = self.current_path[-2]
                rect = QRectF(p1, pos).normalized()
                margin = self.current_thickness * 2
                rect.adjust(-margin, -margin, margin, margin)
                
                self.current_path_painter_path = self._create_smooth_path(self.current_path)
                self.update(rect.toRect())
            else:
                self.current_path_painter_path = self._create_smooth_path(self.current_path)
                self.update()

    def mouseReleaseEvent(self, event):
        if hasattr(self, 'toolbar'):
            if self.toolbar.geometry().contains(event.globalPosition().toPoint()):
                return

        if event.button() == Qt.MouseButton.LeftButton and self.drawing_active:
            self._commit_current_path()
            
    def _commit_current_path(self):
        if self.current_path:
            path_obj = self._create_smooth_path(self.current_path)
            
            # Bake into buffer immediately
            painter = QPainter(self.buffer)
            painter.setRenderHint(QPainter.RenderHint.Antialiasing)
            pen = QPen(self.current_color, self.current_thickness,
                       Qt.PenStyle.SolidLine, Qt.PenCapStyle.RoundCap,
                       Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            
            if self.is_erasing:
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
                
            painter.drawPath(path_obj)
            painter.end()

            self.paths.append((list(self.current_path),
                               QColor(self.current_color),
                               self.current_thickness,
                               self.is_erasing))
            self.current_path = []
            self.current_path_painter_path = QPainterPath()
            self.is_erasing = False
            
        self.update()

    # ── Public API ────────────────────────────────────────────────────────
    def set_draw_mode(self, active: bool):
        self.drawing_active = active
        hwnd = int(self.winId())
        _set_click_through(hwnd, not active)
        self.update()

    def redraw_buffer(self):
        self.buffer.fill(Qt.GlobalColor.transparent)
        painter = QPainter(self.buffer)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        for points, color, thickness, is_eraser in self.paths:
            path_obj = self._create_smooth_path(points)
            pen = QPen(color, thickness, Qt.PenStyle.SolidLine,
                       Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            
            if is_eraser:
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_Clear)
            else:
                painter.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)
                
            painter.drawPath(path_obj)
        painter.end()
        self.update()

    def clear_canvas(self):
        self.paths.clear()
        self.current_path.clear()
        self.current_path_painter_path = QPainterPath()
        self.redraw_buffer()

    def undo(self):
        if self.paths:
            self.paths.pop()
            self.redraw_buffer()

    def set_color(self, color):
        self.current_color = color

    def set_thickness(self, thickness):
        self.current_thickness = thickness

    def set_bg_color(self, color):
        self.bg_color = color

    def set_grid_mode(self, mode_str):
        self.grid_mode = mode_str
        self.update()

    # ── Slide management ──────────────────────────────────────────────────
    def _render_current_to_image(self):
        img = QImage(self.size(), QImage.Format.Format_ARGB32)
        img.fill(self.bg_color)
        painter = QPainter(img)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # Draw grid if active
        if self.grid_mode != "Blank/Plain":
            step = 40
            
            if self.grid_mode == "Lined/Ruled":
                # Ruled paper style margins
                margin_left = 120
                header_top = 100
                
                # Horizontal rules
                h_pen = QPen(QColor(0, 0, 0, 35), 1)
                painter.setPen(h_pen)
                for y in range(header_top, self.height(), step):
                    painter.drawLine(0, y, self.width(), y)
                    
                # Left red margin line
                v_pen = QPen(QColor(255, 69, 58, 80), 2)
                painter.setPen(v_pen)
                painter.drawLine(margin_left, 0, margin_left, self.height())
                
            elif self.grid_mode == "Dot Grid":
                # Bullet journal style dot grid
                d_pen = QPen(QColor(0, 0, 0, 50), 3)
                d_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
                painter.setPen(d_pen)
                for x in range(step, self.width(), step):
                    for y in range(step, self.height(), step):
                        painter.drawPoint(x, y)
                        
            elif self.grid_mode == "Square/Grid":
                # Technical graph paper
                grid_pen = QPen(QColor(0, 0, 0, 20), 1)
                painter.setPen(grid_pen)
                for x in range(0, self.width(), step):
                    painter.drawLine(x, 0, x, self.height())
                for y in range(0, self.height(), step):
                    painter.drawLine(0, y, self.width(), y)

        for points, color, thickness, is_eraser in self.paths:
            path_obj = self._create_smooth_path(points)
            if is_eraser:
                pen = QPen(self.bg_color, thickness, Qt.PenStyle.SolidLine,
                           Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            else:
                pen = QPen(color, thickness, Qt.PenStyle.SolidLine,
                           Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin)
            painter.setPen(pen)
            painter.drawPath(path_obj)
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
            # Get the exact area that the PDF writer provides
            target_size = QSizeF(writer.width(), writer.height())
            # Compute a scaled size that absolutely guards the aspect ratio
            img_size = QSizeF(slide_img.size())
            img_size.scale(target_size, Qt.AspectRatioMode.KeepAspectRatio)
            
            # Center the image perfectly in the PDF page
            x = int((writer.width() - img_size.width()) / 2)
            y = int((writer.height() - img_size.height()) / 2)
            dest_rect = QRect(x, y, int(img_size.width()), int(img_size.height()))
            
            painter.drawImage(dest_rect, slide_img)
        painter.end()
        return True, filepath


# ─── Custom Widgets ────────────────────────────────────────────────────────
from PyQt6.QtCore import pyqtSignal

class CircleButton(QPushButton):
    """Custom button that distinguishes between single and double clicks
       so we can delay single-click actions and not hide immediately."""
    doubleClicked = pyqtSignal()
    singleClicked = pyqtSignal()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        # Use typical system double-click speed as delay
        interval = QApplication.doubleClickInterval()
        # Cap it to 300ms max so single-clicks don't feel too sluggish
        self._timer.setInterval(min(interval, 300))
        self._timer.timeout.connect(self._emit_single)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(event.position().toPoint()):
            if not self._timer.isActive():
                self._timer.start()

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            if self._timer.isActive():
                self._timer.stop()
            self.doubleClicked.emit()
            event.accept()
        else:
            super().mouseDoubleClickEvent(event)

    def _emit_single(self):
        self.singleClicked.emit()

    def hitButton(self, pos):
        # Prevent default clicked signal from doing anything by overriding hitButton
        # Actually it's cleaner to just not connect to the default 'clicked' signal
        return super().hitButton(pos)


class SlideGalleryDialog(QDialog):
    """A dialog to preview and manage slides before exporting."""
    def __init__(self, slides_list, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Slide Gallery")
        self.setMinimumSize(900, 600)
        self.slides = slides_list
        self.setStyleSheet("background-color: #1e1e1e; color: #ffffff;")
        
        self.main_layout = QVBoxLayout(self)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("border: none; background-color: #1e1e1e;")
        
        self.container = QWidget()
        self.grid_layout = QGridLayout(self.container)
        self.grid_layout.setSpacing(20)
        self.scroll_area.setWidget(self.container)
        
        self.main_layout.addWidget(self.scroll_area)
        
        self.populate_gallery()

    def populate_gallery(self):
        # Clear existing layout
        for i in reversed(range(self.grid_layout.count())): 
            widget_to_remove = self.grid_layout.itemAt(i).widget()
            self.grid_layout.removeWidget(widget_to_remove)
            widget_to_remove.setParent(None)

        if not self.slides:
            lbl = QLabel("No slides saved yet. Add some slides to view them here!")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setStyleSheet("font-size: 14pt; color: #aaaaaa;")
            self.grid_layout.addWidget(lbl, 0, 0)
            return

        col_count = 3
        for index, slide_img in enumerate(self.slides):
            row = index // col_count
            col = index % col_count
            
            # Slide container
            slide_widget = QFrame()
            slide_widget.setStyleSheet("background-color: #2c2c2c; border-radius: 8px; border: 1px solid #444;")
            v_lyt = QVBoxLayout(slide_widget)
            
            # Thumbnail
            thumb_lbl = QLabel()
            pixmap = QPixmap.fromImage(slide_img)
            # Scale thumbnail to a reasonable size keeping aspect ratio
            thumb_lbl.setPixmap(pixmap.scaled(250, 200, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
            thumb_lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            v_lyt.addWidget(thumb_lbl)
            
            # Info & Delete row
            h_lyt = QHBoxLayout()
            info_lbl = QLabel(f"Slide {index + 1}\nAspect Ratio matches Screen")
            info_lbl.setStyleSheet("font-size: 10pt; color: #cccccc; border: none;")
            del_btn = QPushButton("🗑️ Delete")
            del_btn.setStyleSheet("background-color: #ff453a; color: white; padding: 5px; border-radius: 4px; border: none; font-weight: bold;")
            del_btn.clicked.connect(lambda checked, idx=index: self.delete_slide(idx))
            
            h_lyt.addWidget(info_lbl)
            h_lyt.addWidget(del_btn)
            v_lyt.addLayout(h_lyt)
            
            self.grid_layout.addWidget(slide_widget, row, col)

    def delete_slide(self, index):
        if 0 <= index < len(self.slides):
            self.slides.pop(index)
            self.populate_gallery()


class SettingsDialog(QDialog):
    def __init__(self, overlay, parent=None):
        super().__init__(parent)
        self.overlay = overlay
        self.setWindowTitle("Settings")
        self.setMinimumSize(300, 200)
        self.setStyleSheet("background-color: #1e1e1e; color: #ffffff;")
        
        layout = QVBoxLayout(self)
        
        form = QFormLayout()
        
        self.theme_combo = QComboBox()
        self.theme_combo.addItems(["Text", "Icons"])
        self.theme_combo.setCurrentText(self.overlay.ui_theme)
        self.theme_combo.setStyleSheet("color: white; background: #2c2c2c; padding: 5px;")
        
        self.mode_combo = QComboBox()
        self.mode_combo.addItems(["Overlay", "Whiteboard"])
        self.mode_combo.setCurrentText(self.overlay.app_mode)
        self.pen_color = QColor(self.overlay.settings.value("pen_color", "#ff0000"))
        self.btn_pen = QPushButton()
        self.btn_pen.setFixedSize(40, 20)
        self.btn_pen.setStyleSheet(f"background-color: {self.pen_color.name()}; border: 1px solid white;")
        self.btn_pen.clicked.connect(self.pick_default_pen)

        self.bg_color = QColor(self.overlay.settings.value("bg_color", "#ffffff"))
        self.btn_bg_col = QPushButton()
        self.btn_bg_col.setFixedSize(40, 20)
        self.btn_bg_col.setStyleSheet(f"background-color: {self.bg_color.name()}; border: 1px solid white;")
        self.btn_bg_col.clicked.connect(self.pick_default_bg)
        
        lbl_theme = QLabel("UI Theme:")
        lbl_mode = QLabel("App Mode:")
        form.addRow(lbl_theme, self.theme_combo)
        form.addRow(lbl_mode, self.mode_combo)
        form.addRow("Default Pen Color:", self.btn_pen)
        form.addRow("Default Background:", self.btn_bg_col)
        
        layout.addLayout(form)
        
        btn_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        btn_box.accepted.connect(self.accept)
        btn_box.rejected.connect(self.reject)
        # Style buttons roughly
        btn_box.setStyleSheet("QPushButton { background-color: rgba(255, 255, 255, 20); color: white; padding: 5px; border-radius: 4px; } QPushButton:hover { background-color: rgba(255, 255, 255, 40); }")
        layout.addWidget(btn_box)

    def pick_default_pen(self):
        c = QColorDialog.getColor(self.pen_color, self, "Pick Default Pen Color")
        if c.isValid():
            self.pen_color = c
            self.btn_pen.setStyleSheet(f"background-color: {c.name()}; border: 1px solid white;")
            
    def pick_default_bg(self):
        c = QColorDialog.getColor(self.bg_color, self, "Pick Default BG Color")
        if c.isValid():
            self.bg_color = c
            self.btn_bg_col.setStyleSheet(f"background-color: {c.name()}; border: 1px solid white;")

    def get_settings(self):
        return {
            "ui_theme": self.theme_combo.currentText(),
            "app_mode": self.mode_combo.currentText(),
            "pen_color": self.pen_color.name(),
            "bg_color": self.bg_color.name()
        }


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

        # Fixed Position at top right of primary screen
        self.right_margin = 20
        self.top_margin = 20
        scr = QApplication.primaryScreen()
        if scr:
            self.screen_width = scr.geometry().width()
        else:
            self.screen_width = 1920

        self._build_ui()
        self.update_theme_display()

    # ── UI construction ───────────────────────────────────────────────────
    def _build_ui(self):
        self.main_layout = QVBoxLayout(self)
        self.main_layout.setContentsMargins(15, 15, 15, 15)  # margin for shadow

        # ── Collapsed circle ──────────────────────────────────────────────
        self.collapsed_widget = QWidget()
        clayout = QVBoxLayout(self.collapsed_widget)
        clayout.setContentsMargins(0, 0, 0, 0)

        self.btn_circle = CircleButton("🖱️")
        self.btn_circle.setFixedSize(65, 65)
        # Drop shadow for the orb
        shadow_orb = QGraphicsDropShadowEffect()
        shadow_orb.setBlurRadius(18)
        shadow_orb.setColor(QColor(0, 0, 0, 100))
        shadow_orb.setOffset(0, 4)
        self.btn_circle.setGraphicsEffect(shadow_orb)
        
        self._style_circle_mouse()
        self.btn_circle.singleClicked.connect(self.expand_menu)
        self.btn_circle.doubleClicked.connect(self.toggle_mode)
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
        self.lbl_title = QLabel("≡  OnScreen Pen")
        self.lbl_title.setStyleSheet("color: #ffffff; font-size: 11pt; font-weight: 600; letter-spacing: 0.5px;")
        
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
        header.addWidget(self.lbl_title)
        header.addStretch()
        header.addWidget(btn_collapse)
        elayout.addLayout(header)

        # Mode toggle (starts as "Mouse Mode" = passthrough)
        self.btn_mode = QPushButton("🖱️  Mouse Mode")
        self.btn_mode.setStyleSheet("background-color: #30d158; color: #000000; font-weight: bold; border: none;")
        self.btn_mode.clicked.connect(self.toggle_mode)
        elayout.addWidget(self.btn_mode)

        # Separator 1
        elayout.addWidget(self._create_separator())

        # Tool selection row
        tool_row = QHBoxLayout()
        tool_row.setSpacing(10)
        self.btn_color = QPushButton("🎨 Pick Pen Color")
        self.btn_color.clicked.connect(self.pick_color)
        
        self.btn_eraser = QPushButton("🧽 Eraser")
        self.btn_eraser.setCheckable(True)
        self.btn_eraser.clicked.connect(self.toggle_eraser)
        
        tool_row.addWidget(self.btn_color)
        tool_row.addWidget(self.btn_eraser)
        elayout.addLayout(tool_row)

        # Thickness slider
        slayout = QHBoxLayout()
        self.lbl_thickness = QLabel("Thickness")
        self.lbl_thickness.setStyleSheet("font-size: 9pt;")
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

        slayout.addWidget(self.lbl_thickness)
        slayout.addWidget(self.slider)
        slayout.addWidget(self.size_val)
        elayout.addLayout(slayout)

        # Undo & Clear Actions (Row)
        action_row = QHBoxLayout()
        action_row.setSpacing(10)
        self.btn_undo = QPushButton("↩️ Undo Stroke")
        self.btn_undo.clicked.connect(self.overlay.undo)
        self.btn_clear = QPushButton("🗑️ Clear All")
        self.btn_clear.clicked.connect(self.overlay.clear_canvas)
        action_row.addWidget(self.btn_undo)
        action_row.addWidget(self.btn_clear)
        elayout.addLayout(action_row)
        
        # Separator 2
        elayout.addWidget(self._create_separator())
        
        # Settings
        self.btn_settings = QPushButton("⚙️ Settings")
        self.btn_settings.clicked.connect(self.open_settings)
        elayout.addWidget(self.btn_settings)

        # Grid / Lined overlay Option
        grid_row = QHBoxLayout()
        self.grid_lbl = QLabel("Pattern:")
        self.grid_lbl.setStyleSheet("font-size: 9pt;")
        self.grid_combo = QComboBox()
        self.grid_combo.addItems(["Blank/Plain", "Lined/Ruled", "Dot Grid", "Square/Grid"])
        self.grid_combo.setStyleSheet("""
            QComboBox { background-color: rgba(255, 255, 255, 12); color: white; border: 1px solid rgba(255, 255, 255, 20); border-radius: 5px; padding: 5px; }
            QComboBox::drop-down { border: none; }
            QComboBox QAbstractItemView { background-color: #2c2c2c; color: white; selection-background-color: #0a84ff; }
        """)
        self.grid_combo.currentTextChanged.connect(self.overlay.set_grid_mode)
        grid_row.addWidget(self.grid_lbl)
        grid_row.addWidget(self.grid_combo)
        elayout.addLayout(grid_row)

        # BG Color for Slides
        self.btn_bg = QPushButton("🖼️ Slide BG (White)")
        self.btn_bg.clicked.connect(self.pick_bg_color)
        elayout.addWidget(self.btn_bg)

        # Add Slide
        self.btn_add = QPushButton("📄 Add Slide to PDF")
        self.btn_add.setStyleSheet("background-color: #0a84ff; color: #ffffff; font-weight: bold; border: none;")
        self.btn_add.clicked.connect(self.add_slide)
        elayout.addWidget(self.btn_add)
        
        # View Slides button
        self.btn_view_slides = QPushButton("🗂️ View / Manage Slides")
        self.btn_view_slides.setStyleSheet("background-color: rgba(255,255,255,15); color: #ffffff; font-weight: bold; border: 1px solid rgba(255,255,255,30);")
        self.btn_view_slides.clicked.connect(self.open_slide_gallery)
        elayout.addWidget(self.btn_view_slides)
        
        # Slide counter
        self.lbl_slides = QLabel("0 slides in memory")
        self.lbl_slides.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_slides.setStyleSheet("font-size: 8.5pt; color: #888888; margin-bottom: 2px;")
        elayout.addWidget(self.lbl_slides)

        # Export PDF
        self.btn_pdf = QPushButton("📕 Save & Export PDF")
        self.btn_pdf.setStyleSheet("background-color: #ff453a; color: #ffffff; font-weight: bold; border: none;")
        self.btn_pdf.clicked.connect(self.export_pdf)
        elayout.addWidget(self.btn_pdf)

        # Clear Canvas
        elayout.addSpacing(6)
        self.btn_exit = QPushButton("Exit App")
        self.btn_exit.setStyleSheet("""
            QPushButton {
                background: transparent; color: #ff453a; font-weight: normal; border: 1px solid rgba(255, 69, 58, 80);
            }
            QPushButton:hover { background: rgba(255, 69, 58, 20); }
        """)
        self.btn_exit.clicked.connect(QApplication.instance().quit)
        elayout.addWidget(self.btn_exit)

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
        icons = (self.overlay.ui_theme == "Icons")
        w = 120 if icons else 290
        h = 540 if icons else 540
        self.resize(w, h)
        self.move(self.screen_width - w - self.right_margin, self.top_margin)

    def collapse_menu(self):
        self.is_expanded = False
        self.expanded_widget.hide()
        self.collapsed_widget.show()
        w, h = 95, 95  # 65 + 30px shadow padding
        self.resize(w, h)
        self.move(self.screen_width - w - self.right_margin, self.top_margin)

    # ── Mode toggle ───────────────────────────────────────────────────────
    def toggle_mode(self):
        if self.overlay.drawing_active:
            # Currently drawing → switch to mouse mode
            self.overlay.set_draw_mode(False)
            self.btn_mode.setText("🖱️  Mouse Mode")
            self.btn_mode.setStyleSheet("background-color: #30d158; color: #000000; font-weight: bold; border: none;")
            self.btn_circle.setText("🖱️")
            self._style_circle_mouse()
        else:
            # Currently mouse → switch to draw mode
            self.overlay.set_draw_mode(True)
            self.btn_mode.setText("✍" if self.overlay.ui_theme == "Icons" else "✍  Draw Mode")
            self.btn_mode.setStyleSheet("background-color: #0a84ff; color: #ffffff; font-weight: bold; border: none;")
            self.btn_circle.setText("✍")
            self._style_circle_draw()
        
        # Guarantee we don't get buried
        self.raise_()
        self.activateWindow()

    def update_theme_display(self):
        icons = (self.overlay.ui_theme == "Icons")
        rad = "22px" if icons else "8px"
        
        # 1. Base generic stylesheet
        self.expanded_widget.setStyleSheet(f"""
            QFrame#ExpandedPanel {{ background-color: rgba(22, 22, 24, 240); border: 1px solid rgba(255, 255, 255, 25); border-radius: 16px; }}
            QPushButton {{ background-color: rgba(255, 255, 255, 12); color: #ffffff; border: 1px solid rgba(255, 255, 255, 12); padding: 5px; border-radius: {rad}; font-size: 13pt; font-family: 'Segoe UI Emoji'; }}
            QPushButton:hover {{ background-color: rgba(255, 255, 255, 25); border: 1px solid rgba(255, 255, 255, 30); }}
            QPushButton:pressed {{ background-color: rgba(255, 255, 255, 8); }}
            QLabel {{ color: #d1d1d1; font-family: 'Segoe UI', system-ui, sans-serif; font-weight: 500; }}
            QSlider::groove:horizontal {{ height: 6px; background: rgba(255, 255, 255, 20); border-radius: 3px; }}
            QSlider::handle:horizontal {{ background: #0a84ff; width: 14px; height: 14px; margin: -4px 0; border-radius: 7px; }}
            QSlider::handle:horizontal:hover {{ background: #409cff; }}
        """)

        buttons = [self.btn_mode, self.btn_color, self.btn_eraser, self.btn_undo, self.btn_clear, self.btn_settings, self.btn_bg, self.btn_add, self.btn_view_slides, self.btn_pdf, self.btn_exit]
        for btn in buttons:
            if icons:
                btn.setFixedSize(44, 44)
            else:
                btn.setMinimumSize(0, 0)
                btn.setMaximumSize(16777215, 16777215)
                
        if self.overlay.drawing_active:
            self.btn_mode.setText("✍" if icons else "✍  Draw Mode")
            self.btn_mode.setStyleSheet(f"background-color: #0a84ff; color: #ffffff; font-weight: bold; border: none; border-radius: {rad};")
        else:
            self.btn_mode.setText("🖱️" if icons else "🖱️  Mouse Mode")
            self.btn_mode.setStyleSheet(f"background-color: #30d158; color: #000000; font-weight: bold; border: none; border-radius: {rad};")

        self.btn_color.setText("🎨" if icons else "🎨 Pick Pen Color")
        self.btn_eraser.setText("🧽" if icons else "🧽 Eraser")
        
        if self.overlay.active_tool_eraser:
            self.btn_eraser.setStyleSheet(f"background-color: #ff453a; color: #ffffff; font-weight: bold; border: none; border-radius: {rad};")
        else:
            self.btn_eraser.setStyleSheet("")
            
        self.btn_undo.setText("↩️" if icons else "↩️ Undo Stroke")
        self.btn_clear.setText("🗑️" if icons else "🗑️ Clear All")
        self.btn_settings.setText("⚙️" if icons else "⚙️ Settings")
        
        self.grid_lbl.setVisible(not icons)
        self.grid_combo.setVisible(not icons)
        self.slider.setVisible(not icons)
        self.size_val.setVisible(not icons)
        self.lbl_thickness.setVisible(not icons)
        self.lbl_slides.setVisible(not icons)
        self.lbl_title.setVisible(not icons)
        
        self.btn_bg.setText("🖼️" if icons else f"🖼️ Slide BG")
        self.btn_add.setText("📄" if icons else "📄 Add Slide")
        self.btn_view_slides.setText("🗂️" if icons else "🗂️ View Slides")
        self.btn_pdf.setText("📕" if icons else "📕 Export PDF")
        self.btn_exit.setText("❌" if icons else "Exit App")
        
        self.btn_pdf.setStyleSheet(f"background-color: #ff453a; color: #ffffff; font-weight: bold; border: none; border-radius: {rad};")
        self.btn_exit.setStyleSheet(f"background: transparent; color: #ff453a; font-weight: normal; border: 1px solid rgba(255, 69, 58, 80); border-radius: {rad};")
        
        if self.is_expanded:
            w = 126 if icons else 290
            h = 540 if icons else 540
            self.resize(w, h)
            self.move(self.screen_width - w - self.right_margin, self.top_margin)

    # ── Actions ───────────────────────────────────────────────────────────
    def toggle_eraser(self):
        self.overlay.active_tool_eraser = not self.overlay.active_tool_eraser
        self.update_theme_display()

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
            self._update_slide_count_label()
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

    def open_slide_gallery(self):
        # We temporarily collapse the toolbar to keep it out of the way, or we can just open the dialog
        dialog = SlideGalleryDialog(self.overlay.slides, self)
        dialog.exec()
        # After gallery closes, update the label showing slide count
        self._update_slide_count_label()

    def _update_slide_count_label(self):
        count = len(self.overlay.slides)
        self.lbl_slides.setText(f"{count} slide{'s' if count != 1 else ''} in memory")
        if count > 0:
            self.lbl_slides.setStyleSheet("font-size: 8.5pt; color: #30d158; font-weight: bold;")
        else:
            self.lbl_slides.setStyleSheet("font-size: 8.5pt; color: #888888; font-weight: normal;")

    def open_settings(self):
        dlg = SettingsDialog(self.overlay, self)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            st = dlg.get_settings()
            self.overlay.ui_theme = st["ui_theme"]
            self.overlay.app_mode = st["app_mode"]
            self.overlay.current_color = QColor(st["pen_color"])
            self.overlay.bg_color = QColor(st["bg_color"])
            
            self.overlay.settings.setValue("ui_theme", st["ui_theme"])
            self.overlay.settings.setValue("app_mode", st["app_mode"])
            self.overlay.settings.setValue("pen_color", st["pen_color"])
            self.overlay.settings.setValue("bg_color", st["bg_color"])
            
            self.update_theme_display()
            self.overlay.update()

    # ── Helpers ───────────────────────────────────────────────────────────
    def _style_circle_mouse(self):
        self.btn_circle.setStyleSheet("""
            QPushButton {
                background-color: #30d158; color: #000000;
                border-radius: 32px; font-size: 30px;
                font-family: 'Segoe UI', system-ui, sans-serif;
            }
            QPushButton:hover { background-color: #2ed158; }
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




# ─── Entry Point ──────────────────────────────────────────────────────────────
def main():
    app = QApplication(sys.argv)
    
    # Establish a clean base font
    app.setFont(QFont("Segoe UI", 9))

    overlay = OverlayWindow()
    toolbar = ToolbarWindow(overlay)
    overlay.toolbar = toolbar

    overlay.show()
    toolbar.show()

    # Ensure toolbar is above the overlay in the z-order
    toolbar.raise_()
    toolbar.activateWindow()

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
