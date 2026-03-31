import sys
import traceback

def main():
    try:
        from PyQt6.QtWidgets import QApplication, QLabel
        app = QApplication(sys.argv)
        print("Application initialized successfully", flush=True)
    except Exception as e:
        print("Error initializing:")
        traceback.print_exc()

if __name__ == "__main__":
    main()
