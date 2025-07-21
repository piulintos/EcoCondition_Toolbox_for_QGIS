# -*- coding: utf-8 -*-
"""
Tool “Replace NoData” for EcoCondition Toolbox
"""

import os
from osgeo import gdal
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog, 
    QFileDialog, 
    QTreeWidget, QTreeWidgetItem,
    QTableWidget, QTableWidgetItem,
    QHeaderView, 
    QPushButton,
    QLineEdit, 
    QCheckBox,
    QDialogButtonBox,
    QAbstractItemView, 
    QDoubleSpinBox, 
    QMessageBox
)
from qgis.core import (
    QgsProject, 
    QgsProcessingContext, 
    QgsRasterLayer, 
    QgsLayerTreeModel,
    QgsLayerTreeLayer,
    QgsLayerTreeGroup, 
    QgsProcessingFeedback
)
import processing

class SolveNoDataTool:
    def __init__(self, iface, plugin_dir=None):
        import os
        # store the QGIS interface
        self.iface = iface
        # locate the plugin root if not explicitly passed
        if plugin_dir:
            self.plugin_dir = plugin_dir
        else:
            # this file lives under <plugin>/tools/
            self.plugin_dir = os.path.dirname(os.path.dirname(__file__))
        # will be our dialog once we load it
        self.dialog = None

    def run(self):
        self.selected_layers = []
        if not self.dialog:
            # 1) load the UI
            ui_path = os.path.join(self.plugin_dir, "tools", "tool_solve_nodata.ui")
            self.dialog = uic.loadUi(ui_path, QDialog())

            # 2) Grab all your widgets by their objectName
            self.treeAvail   = self.dialog.findChild(QTreeWidget,    "treeAvailable")
            self.tableSel    = self.dialog.findChild(QTableWidget,   "tblSelected")
            self.btnAdd      = self.dialog.findChild(QPushButton,    "btnAdd")
            self.btnRemove   = self.dialog.findChild(QPushButton,    "btnRemove")

            self.spinNoData   = self.dialog.findChild(QDoubleSpinBox, "spinNoData")
            self.txtFolder    = self.dialog.findChild(QLineEdit,       "txtFolder")
            self.txtPrefix    = self.dialog.findChild(QLineEdit,       "txtPrefix")
            self.txtSuffix    = self.dialog.findChild(QLineEdit,       "txtSuffix")
            self.chkAdd       = self.dialog.findChild(QCheckBox,       "chkAdd")
            self.chkOverwrite = self.dialog.findChild(QCheckBox,       "chkOverwrite")
            self.btnBrowse    = self.dialog.findChild(QPushButton,     "btnBrowse")
            self.buttonBox    = self.dialog.findChild(QDialogButtonBox,"buttonBox")

            # 3) Wire signals
            self.btnAdd.clicked.connect(self.addLayers)
            self.btnRemove.clicked.connect(self.removeLayers)
            self.btnBrowse.clicked.connect(self.chooseFolder)
            self.buttonBox.accepted.connect(self.apply)
            self.buttonBox.rejected.connect(self.dialog.reject)

            # 4) Populate tree & prep table
            self.populateLayers()

        # finally show
        self.dialog.show()
        self.dialog.exec_()

    def populateLayers(self):
        # Fill the left-hand QTreeWidget and reset the right-hand QTableWidget.
        ## the tree of available rasters
        self.treeAvail.clear()
        ## the selected-rasters table
        self.tableSel.clearContents()
        self.tableSel.setRowCount(0)

        # 2) Recursive function to add groups & layers
        def recurse(group_item, parent_widget_item):
            for child in group_item.children():
                if isinstance(child, QgsLayerTreeGroup):
                    w = QTreeWidgetItem([child.name()])
                    font = w.font(0)
                    font.setUnderline(True)
                    w.setFont(0, font)
                    parent_widget_item.addChild(w)
                    recurse(child, w)
                elif isinstance(child, QgsLayerTreeLayer):
                    lyr = QgsProject.instance().mapLayer(child.layerId())
                    if isinstance(lyr, QgsRasterLayer):
                        w = QTreeWidgetItem([lyr.name()])
                        w.setData(0, Qt.UserRole, lyr.id())
                        parent_widget_item.addChild(w)

        # 3) Walk the root of the layer tree
        root = QgsProject.instance().layerTreeRoot()
        for top in root.children():
            if isinstance(top, QgsLayerTreeGroup):
                topItem = QTreeWidgetItem([top.name()])
                font = topItem.font(0); font.setUnderline(True)
                topItem.setFont(0, font)
                self.treeAvail.addTopLevelItem(topItem)
                recurse(top, topItem)
            elif isinstance(top, QgsLayerTreeLayer):
                lyr = QgsProject.instance().mapLayer(top.layerId())
                if isinstance(lyr, QgsRasterLayer):
                    itm = QTreeWidgetItem([lyr.name()])
                    itm.setData(0, Qt.UserRole, lyr.id())
                    self.treeAvail.addTopLevelItem(itm)


        # 4) Allow multi-select
        self.treeAvail.setSelectionMode(QAbstractItemView.ExtendedSelection)

        # 5) Expand all so user sees the full hierarchy
        self.treeAvail.expandAll()

        # 6) prepare the QTableWidget for added rows
        self.tableSel.setColumnCount(2)
        self.tableSel.setHorizontalHeaderLabels(['Layer', 'Short Name (15 charac. max.)'])
        self.tableSel.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    def addLayers(self):
        # Move selected in the tree into the right‐hand table.
        """Move any selected items from the tree into the table."""
        for item in self.treeAvail.selectedItems():
            layer_id = item.data(0, Qt.UserRole)
            if not layer_id:
                continue
            # avoid duplicates
            for r in range(self.tableSel.rowCount()):
                if self.tableSel.item(r,0).data(Qt.UserRole) == layer_id:
                    break
            else:
                row = self.tableSel.rowCount()
                self.tableSel.insertRow(row)
                # name column
                i0 = QTableWidgetItem(item.text(0))
                i0.setData(Qt.UserRole, layer_id)
                i0.setFlags(i0.flags() & ~Qt.ItemIsEditable)
                self.tableSel.setItem(row, 0, i0)
                # short-name column (editable)
                i1 = QTableWidgetItem(item.text(0))
                self.tableSel.setItem(row, 1, i1)

    def removeLayers(self):
        """Delete highlighted rows from the table."""
        for sel in reversed(self.tableSel.selectionModel().selectedRows()):
            self.tableSel.removeRow(sel.row())

    def chooseFolder(self):
        fld = QFileDialog.getExistingDirectory(self.dialog, "Select output folder")
        if fld:
            self.txtFolder.setText(fld)

    def apply(self):
        """
        Gathers parameters from the UI, then for each selected raster
        applies the same robust nodata‐fix logic you had in algorithm.py.
        """
        # 1) Collect inputs from the right‐hand table
        layers = []
        for row in range(self.tableSel.rowCount()):
            lid = self.tableSel.item(row, 0).data(Qt.UserRole)
            lyr = QgsProject.instance().mapLayer(lid)
            if isinstance(lyr, QgsRasterLayer):
                layers.append(lyr)

        if not layers:
            QMessageBox.warning(
                self.dialog,
                "Replace NoData",
                "No raster layers selected.\nPlease select at least one raster."
            )
            return

        # 2) Read the other parameters
        nodata_val    = self.spinNoData.value()
        output_folder = self.txtFolder.text().strip()
        prefix        = self.txtPrefix.text() or ""
        suffix        = self.txtSuffix.text() or ""
        add_to_proj   = self.chkAdd.isChecked()
        overwrite     = self.chkOverwrite.isChecked()

        if not output_folder or not os.path.isdir(output_folder):
            QMessageBox.warning(
                self.dialog,
                "Replace NoData",
                "Please select a valid output folder."
            )
            return

        # 3) Set up processing context & feedback (DE-INDENTED)
        context  = QgsProcessingContext()
        feedback = QgsProcessingFeedback()

        # 4) Loop through each layer (all of this MUST be inside the loop)
        for lyr in layers:
            if feedback.isCanceled():
                break

            base_name = lyr.name()
            feedback.pushInfo(f"Processing {base_name}")
            inp_path  = lyr.source()

            # build output path
            out_name = f"{prefix}{base_name}{suffix}.tif"
            out_name = out_name.strip(".").replace("..", ".").lstrip("_")
            out_path = os.path.join(output_folder, out_name)

            if os.path.exists(out_path) and not overwrite:
                feedback.pushWarning(f"Skipping existing: {out_name}")
                continue

            # 5) Inspect the raster
            ds = gdal.Open(inp_path)
            band = ds.GetRasterBand(1)
            dtype        = gdal.GetDataTypeName(band.DataType)
            input_nodata = band.GetNoDataValue()
            ds = None

            # 6) Byte/UInt16 no-data fallback
            calc_input = inp_path
            if dtype in ("Byte", "UInt16") and input_nodata is None:
                feedback.pushInfo(f"  NoData undefined—translating {base_name}")
                tmp = processing.run(
                    "gdal:translate",
                    {
                        "INPUT":             inp_path,
                        "TARGET_CRS":        None,
                        "NODATA":            0,
                        "COPY_SUBDATASETS":  False,
                        "OPTIONS":           "",
                        "DATA_TYPE":         5,  # Float32
                        "OUTPUT":            "TEMPORARY_OUTPUT",
                    },
                    context=context,
                    feedback=feedback,
                )
                calc_input   = tmp["OUTPUT"]
                input_nodata = 0

            # 7) Build the raster‐calculator expression
            if input_nodata is not None:
                expr = (
                    f"({nodata_val}) * (A == {input_nodata}) "
                    f"+ A * (A != {input_nodata})"
                )
            else:
                expr = (
                    f"({nodata_val}) * ((A<=-3.4e+38)+(A!=A)) "
                    f"+ ((A>-3.4e+38)*(A==A)*A)"
                )

            # 8) Run raster‐calculator
            processing.run(
                "gdal:rastercalculator",
                {
                    "INPUT_A":  calc_input,
                    "BAND_A":   1,
                    "INPUT_B":  None, "BAND_B": -1,
                    "INPUT_C":  None, "BAND_C": -1,
                    "INPUT_D":  None, "BAND_D": -1,
                    "INPUT_E":  None, "BAND_E": -1,
                    "INPUT_F":  None, "BAND_F": -1,
                    "FORMULA":  expr,
                    "NO_DATA":  nodata_val,
                    "RTYPE":    5,  # Float32
                    "EXTRA":    "",
                    "OPTIONS":  "",
                    "OUTPUT":   out_path,
                },
                context=context,
                feedback=feedback,
            )

            # 9) Clean up temporary if needed
            if calc_input != inp_path:
                try:
                    processing.run(
                        "gdal:remove",
                        {"INPUT": calc_input},
                        context=context,
                        feedback=feedback,
                    )
                except Exception:
                    pass

            # 10) Optionally add to project
            if add_to_proj:
                new_lyr = QgsRasterLayer(out_path, base_name)
                if new_lyr.isValid():
                    QgsProject.instance().addMapLayer(new_lyr)

        # 11) Close the dialog when done
        self.dialog.accept()
