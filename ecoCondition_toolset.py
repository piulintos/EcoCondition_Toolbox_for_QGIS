# eco_cond_toolset.py
import os
from functools import partial
from qgis.core import QgsProject, QgsRasterLayer, QgsLayerTreeLayer, QgsLayerTreeGroup, QgsApplication

from qgis.PyQt.QtCore import QCoreApplication
from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui     import QIcon
from qgis.PyQt.QtWidgets import QAction

# my_plugin/eco_cond_toolset.py
from .tools.tool_align_layers           import AlignLayersTool
from .tools.tool_solve_nodata           import SolveNoDataTool
from .tools.tool_test_multicollinearity import CheckMulticollinearityDialog
from .tools.tool_normalise_invert       import NormalizeTool
from .tools.tool_calc_condition         import EcoCondTool
from .tools.tool_about                  import aboutWindow


class EcoConditionToolset:
    def __init__(self, iface):
        self.iface     = iface
        self.menu_name = "&Ecosystem Condition Toolset"
        self.actions   = []

    def initGui(self):
        res = os.path.join(os.path.dirname(__file__), 'resources')
        tools = [
            ("icon_AlignRasters_mini.png",     "1. Align layers (with clip and resample)",       AlignLayersTool),
            ("icon_noDataCorr_mini.png",       "2. Solve no-data issues",                        SolveNoDataTool),
            ("icon_Multicollinearity_mini.png","3. Multicollinearity assessment",                CheckMulticollinearityDialog),
            ("icon_Normalization_mini.png",    "4. Normalise and invert (with no-data options)", NormalizeTool),
            ("icon_EcoCond_mini.png",          "5. Ecosystem Condition assessment",              EcoCondTool),
            ("icon_about.png",                 "About",                                          aboutWindow),
        ]
        for icon_file, label, ToolClass in tools:
            icon   = QIcon(os.path.join(res, icon_file))
            action = QAction(icon, label, self.iface.mainWindow())
            # instantiate the tool with the real iface, then call its run()
            action.triggered.connect(partial(self.launch_tool, ToolClass))
            self.iface.addPluginToMenu(self.menu_name, action)
            self.iface.addToolBarIcon(action)
            self.actions.append(action)

    def unload(self):
        for action in self.actions:
            self.iface.removePluginMenu(self.menu_name, action)
            self.iface.removeToolBarIcon(action)
        self.actions.clear()

    def launch_tool(self, ToolClass, checked=False):
        tool = ToolClass(self.iface)
        tool.run()
