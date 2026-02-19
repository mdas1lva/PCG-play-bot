import sys
import os
import asyncio
import qasync
from os import path
from dotenv import load_dotenv

load_dotenv()

from PyQt6.QtWebEngineCore import QWebEngineUrlScheme
from PyQt6.QtWidgets import QApplication

from src.MainApplication.index import MainApplication

# Fix for Wayland/GPU issues
os.environ["QT_QPA_PLATFORM"] = "xcb"
os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = "--disable-gpu"


def except_hook(cls, exception, traceback):
    """Used to force PyQt to print exceptions"""

    sys.__excepthook__(cls, exception, traceback)


def get_program_path(main_file):
    """Gets this program folder path"""

    if getattr(sys, "frozen", False):
        application_path = path.dirname(sys.executable)

    else:
        application_path = path.abspath(path.dirname(main_file))

    return application_path


async def main():
    program_path = get_program_path(__file__)
    core_app = MainApplication(program_path)
    
    # We await the core_app so the event loop stays alive
    # We will need to implement a run/shutdown method in MainApplication
    await core_app.run()


if __name__ == "__main__":

    sys.excepthook = except_hook

    scheme = QWebEngineUrlScheme(b"qt")
    QWebEngineUrlScheme.registerScheme(scheme)

    app = QApplication(sys.argv)
    
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    try:
        loop.run_until_complete(main())
    except KeyboardInterrupt:
        pass
    finally:
        loop.close()
