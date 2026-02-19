from json import loads

from PyQt6.QtCore import QUrl, pyqtSlot, QRect, QObject
from PyQt6.QtGui import QIcon, QGuiApplication
from PyQt6.QtWebChannel import QWebChannel
from PyQt6.QtWebEngineWidgets import QWebEngineView

from src.helpers.WebPageDebugger import WebPageDebugger
from src.helpers.SchemeHandler import QtSchemeHandler


class ConfigPageBridge(QObject):
    """
    Bridge class to handle communication between Python and JavaScript.
    Separated from QWidget to avoid exposing widget properties to QWebChannel.
    """
    def __init__(self, save_config_callback):
        super().__init__()
        self._save_config_callback = save_config_callback

    @pyqtSlot(str)
    def save_config(self, new_config):
        """Receives GUI action to save new configurations via qt channel"""
        self._save_config_callback(loads(new_config))


class ConfigPage(QWebEngineView):
    """

    This is the program's configuration GUI.
    It is used to set not configurations as which balls throw and when to buy.
    """

    def __init__(self,
                 program_path,
                 on_load_callback,
                 on_save_config_callback
                 ):
        super().__init__()

        self._program_path = program_path
        self._load_callback = on_load_callback
        
        # Bridge object for JS communication
        self._bridge = ConfigPageBridge(on_save_config_callback)

        self._channel = QWebChannel()
        self._channel.registerObject("backend_channel", self._bridge)

        self._page = WebPageDebugger(debug_active=True)
        self._page.setWebChannel(self._channel)
        self._page.loadFinished.connect(self._load_callback)
        
        # Install Scheme Handler ONCE during initialization
        self.scheme_handler = QtSchemeHandler(self._program_path)
        self._page.profile().installUrlSchemeHandler(
             b"qt", self.scheme_handler
        )

        self.setPage(self._page)

        self.setWindowTitle("Config")
        self.setWindowIcon(QIcon(f"{self._program_path}/assets/icons/gear.png"))

        self.setGeometry(QRect(0, 0, 960, 640)) 
        center_point = QGuiApplication.primaryScreen().availableGeometry().center()
        qt_rectangle = self.frameGeometry()
        qt_rectangle.moveCenter(center_point)
        self.move(qt_rectangle.topLeft())

    def open(self):
        """Opens the GUI page"""

        url = QUrl("qt://main")
        url.setPath("/config.html")
        self.load(url)

        self.show()

    def update_config_data(self, new_value):
        """Updates GUI config in page js store via qt channel"""

        self._page.runJavaScript(f"runSetConfig('{new_value}')")

