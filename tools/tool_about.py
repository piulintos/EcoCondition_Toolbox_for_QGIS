import os
from qgis.PyQt import uic
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtWidgets import QDialog

class aboutWindow:
    def __init__(self, iface):
        self.iface = iface
        # path to the UI file
        self.ui_path = os.path.join(os.path.dirname(__file__), 'tool_about.ui')

    def run(self):
        # verify UI path exists
        if not os.path.exists(self.ui_path):
            raise FileNotFoundError(f"Cannot find UI file at {self.ui_path}")

        # load the UI into a QDialog parented to the QGIS main window
        self.dlg = uic.loadUi(self.ui_path, QDialog(self.iface.mainWindow()))
        self.dlg.setFixedSize(1000, 600) # 1424, 650

        # compute path to the HTML file in the resources folder
        plugin_root = os.path.dirname(os.path.dirname(__file__))
        info_path   = os.path.join(plugin_root, 'resources', 'info.html')

        # load HTML content into the QTextBrowser with base URL for relative links
        with open(info_path, 'r', encoding='utf-8') as f:
            html = f.read()
        base = QUrl.fromLocalFile(os.path.dirname(info_path) + os.sep)
        # set the document's base URL so <img> paths resolve correctly
        self.dlg.htmlInfoTab.document().setBaseUrl(base)
        self.dlg.htmlInfoTab.setHtml(html)
        self.dlg.htmlInfoTab.setStyleSheet("background-color: transparent;")

        # connect Close button
        self.dlg.buttonBox.rejected.connect(self.dlg.reject)

        # show the dialog modally
        self.dlg.exec_()
