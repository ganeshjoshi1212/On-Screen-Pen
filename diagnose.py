"""Diagnostic script for OnScreen Pen - checks what's going wrong."""
import sys
import ctypes
import ctypes.wintypes
from PyQt6.QtWidgets import QApplication, QWidget, QPushButton, QLabel, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer, QRect
from PyQt6.QtGui import QFont, QScreen

def main():
    app = QApplication(sys.argv)
    print("[OK] QApplication created", flush=True)
    
    # Check screens
    screens = QApplication.screens()
    print(f"[INFO] Number of screens: {len(screens)}", flush=True)
    for i, s in enumerate(screens):
        g = s.geometry()
        dpr = s.devicePixelRatio()
        print(f"  Screen {i}: {g.width()}x{g.height()} at ({g.x()},{g.y()}), DPR={dpr}", flush=True)
    
    # Compute united rect (what overlay uses)
    rect = QRect()
    for s in screens:
        rect = rect.united(s.geometry())
    print(f"[INFO] United rect: {rect.x()},{rect.y()} {rect.width()}x{rect.height()}", flush=True)
    
    # Check primary screen
    primary = QApplication.primaryScreen()
    if primary:
        pg = primary.geometry()
        print(f"[INFO] Primary screen: {pg.width()}x{pg.height()}", flush=True)
        toolbar_x = pg.width() - 90
        toolbar_y = pg.height() // 2 - 30
        print(f"[INFO] Toolbar would be at: ({toolbar_x}, {toolbar_y})", flush=True)
    
    # Test creating a simple always-on-top window
    print("[TEST] Creating simple test window...", flush=True)
    test_win = QWidget()
    test_win.setWindowFlags(
        Qt.WindowType.FramelessWindowHint |
        Qt.WindowType.WindowStaysOnTopHint |
        Qt.WindowType.Tool
    )
    test_win.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    
    btn = QPushButton("TEST ORB")
    btn.setFixedSize(80, 80)
    btn.setStyleSheet("""
        QPushButton{background:#ff4444;color:white;border-radius:40px;
                    font-size:14px;font-weight:bold;}
    """)
    layout = QVBoxLayout(test_win)
    layout.setContentsMargins(0,0,0,0)
    layout.addWidget(btn)
    test_win.setFixedSize(80, 80)
    
    # Position it at center of primary screen for easy visibility
    if primary:
        cx = pg.width() // 2 - 40
        cy = pg.height() // 2 - 40
        test_win.move(cx, cy)
        print(f"[INFO] Test window at ({cx}, {cy})", flush=True)
    
    test_win.show()
    test_win.raise_()
    test_win.activateWindow()
    print(f"[INFO] Test window visible: {test_win.isVisible()}", flush=True)
    print(f"[INFO] Test window geometry: {test_win.geometry()}", flush=True)
    print(f"[INFO] Test window winId: {int(test_win.winId())}", flush=True)
    
    # Also test the overlay-style window
    overlay = QWidget()
    overlay.setWindowFlags(
        Qt.WindowType.FramelessWindowHint |
        Qt.WindowType.WindowStaysOnTopHint |
        Qt.WindowType.Tool
    )
    overlay.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
    overlay.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating)
    overlay.setGeometry(rect)
    overlay.show()
    print(f"[INFO] Overlay visible: {overlay.isVisible()}", flush=True)
    print(f"[INFO] Overlay geometry: {overlay.geometry()}", flush=True)
    print(f"[INFO] Overlay winId: {int(overlay.winId())}", flush=True)
    
    # Test WinAPI click-through
    try:
        hwnd = int(overlay.winId())
        GWL_EXSTYLE = -20
        WS_EX_TRANSPARENT = 0x00000020
        
        user32 = ctypes.windll.user32
        if sys.maxsize > 2**32:
            get_wl = user32.GetWindowLongPtrW
            get_wl.restype = ctypes.c_void_p
            get_wl.argtypes = [ctypes.c_void_p, ctypes.c_int]
        else:
            get_wl = user32.GetWindowLongW
            get_wl.restype = ctypes.c_long
            get_wl.argtypes = [ctypes.c_void_p, ctypes.c_int]
        
        ex_style = get_wl(ctypes.c_void_p(hwnd), GWL_EXSTYLE)
        print(f"[INFO] Overlay extended style: {ex_style} (type: {type(ex_style)})", flush=True)
        if ex_style is None:
            print("[ERROR] GetWindowLong returned None! This is the bug.", flush=True)
        else:
            print(f"[INFO] Extended style hex: {hex(ex_style)}", flush=True)
            has_transparent = bool(ex_style & WS_EX_TRANSPARENT)
            print(f"[INFO] Currently click-through: {has_transparent}", flush=True)
    except Exception as e:
        print(f"[ERROR] WinAPI test failed: {e}", flush=True)
    
    # Auto-close after 15 seconds
    def close_all():
        print("[INFO] Auto-closing after 15s timeout", flush=True)
        app.quit()
    
    QTimer.singleShot(15000, close_all)
    
    btn.clicked.connect(lambda: print("[OK] Button clicked! UI is interactive.", flush=True))
    
    print("\n[RESULT] If you can see a RED circle on screen, the basic window system works.", flush=True)
    print("[RESULT] App will auto-close in 15 seconds.", flush=True)
    
    sys.exit(app.exec())

if __name__ == "__main__":
    main()
