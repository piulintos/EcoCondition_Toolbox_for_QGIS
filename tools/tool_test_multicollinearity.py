# -*- coding: utf-8 -*-
import os
import numpy as np
import pandas as pd
from osgeo import gdal
from qgis.PyQt import uic
from qgis.core import QgsProject, QgsRasterLayer, QgsLayerTreeGroup, QgsLayerTreeLayer
from qgis.PyQt.QtGui import QColor
from qgis.PyQt.QtWidgets import QDialog, QApplication, QMessageBox, QProgressDialog, QTreeWidgetItem, QFileDialog
from qgis.PyQt.QtCore import QObject, QThread, pyqtSignal
from scipy.stats import spearmanr

gdal.UseExceptions()  # enable GDAL Python exceptions and suppress FutureWarning

import csv
import time

# Monkey-patch missing attrs so old statsmodels will import
if not hasattr(np, 'long'):
    np.long = int
if not hasattr(np, 'longlong'):
    np.longlong = int

if not hasattr(np, 'MachAr'):
    class MachAr:
        """
        Minimal stand-in for numpy.MachAr used by old statsmodels.
        """
        def __init__(self):
            fi = np.finfo(float)
            self.eps             = fi.eps
            self.tiny            = fi.tiny
            self.smallest_normal = fi.tiny
            self.huge            = fi.max

        def __repr__(self):
            return f"<patched MachAr eps={self.eps}>"

    np.MachAr = MachAr

# Now pull in statsmodels safely
try:
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    HAVE_STATSMODELS = True
except ImportError:
    HAVE_STATSMODELS = False
    # define a dummy so code doesn’t break at import time
    def variance_inflation_factor(*args, **kwargs):
        raise ImportError("statsmodels not available")

FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), 'tool_test_multicollinearity.ui'))

class CorrelationWorker(QObject):
    # Signals to communicate
    finished = pyqtSignal(dict)     # will emit a dict of results
    error    = pyqtSignal(str)      # emit error message

    def __init__(self, layer_ids, mask_id, enable_vif=True):
        super().__init__()
        self.layer_ids = layer_ids
        self.mask_id = mask_id
        self.enable_vif = enable_vif

    def run(self):
        try:
            # ** 1. Resolve layer IDs into actual file paths and load **
            arrays, names = [], []
            
            for lid in self.layer_ids:
                # lid is a QGIS layer ID, so fetch that layer
                lyr = QgsProject.instance().mapLayer(lid)
                path = lyr.source() if hasattr(lyr, 'source') else lid
                ds   = gdal.Open(path)
                band = ds.GetRasterBand(1)
                arr  = band.ReadAsArray().astype(float)
                nod  = band.GetNoDataValue()
                if nod is not None: arr[arr == nod] = np.nan
                arrays.append(arr.flatten())
                names.append(os.path.splitext(os.path.basename(path))[0])

            stacked = np.stack(arrays, axis=1)
            # ** 2. Mask **
            if self.mask_id:
                # mask_id may also be a layer ID
                mask_lyr = QgsProject.instance().mapLayer(self.mask_id)
                mpath     = mask_lyr.source() if hasattr(mask_lyr, 'source') else self.mask_id
                dsm       = gdal.Open(mpath)
                m = dsm.GetRasterBand(1).ReadAsArray().astype(float)
                nod = dsm.GetRasterBand(1).GetNoDataValue()
                if nod is not None: m[m == nod] = np.nan
                mask_flat = m.flatten()
                valid = (~np.isnan(stacked).any(1)) & (~np.isnan(mask_flat))
            else:
                valid = ~np.isnan(stacked).any(1)
            filtered = stacked[valid]

            if filtered.shape[0] < 2:
                raise ValueError("Too few valid pixels to compute correlation.")

            # ** 3. Spearman **
            # compute the full correlation matrix across columns
            corr, _ = spearmanr(filtered, axis=0)

            # ** 4. VIF (optional) **
            df = pd.DataFrame(filtered, columns=names)
            if self.enable_vif:
                # compute VIF only if statsmodels is available
                vifs = []
                for i in range(df.shape[1]):
                    try:
                        vifs.append(variance_inflation_factor(df.values, i))
                    except Exception:
                        vifs.append(None)
            else:
                vifs = [None] * df.shape[1]

            # ** 5. Emit results **
            nan_summary = {
                name: int(np.isnan(arr).sum()) for name, arr in zip(names, arrays)
            }
            self.finished.emit({
                "corr":        corr,
                "names":       names,
                "vif":         vifs,
                "total_pix":   stacked.shape[0],
                "valid_pix":   filtered.shape[0],
                "nan_summary": nan_summary
            })
        except Exception as e:
            self.error.emit(str(e))

class CheckMulticollinearityDialog(QDialog, FORM_CLASS): # BEFORE: TestMulticollinearityTool
    def __init__(self, iface):
        # parent the dialog to the QGIS main window
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.setupUi(self)

        # 1) CIF checkbox setup
        if HAVE_STATSMODELS:
            self.chkEnableVIF.setChecked(True)
        else:
            self.chkEnableVIF.setChecked(False)
            self.chkEnableVIF.setEnabled(False)
            self.chkEnableVIF.setToolTip("statsmodels not installed: VIF disabled")

        self.setWindowTitle("Multicollinearity assessment")
        self.setFixedSize(1424, 650)

        # 2) Wire each button exactly once
        self.btnAdd.clicked.connect(self.addLayers)
        self.btnRemove.clicked.connect(self.removeLayers)

        self.btnVerifyAlignment.clicked.connect(self.verifyAlignment)
        self.btnRun.clicked.connect(self.runCorrelation)
        self.btnCancel.clicked.connect(self.reject)

        # export buttons
        self.btnExportCSV.clicked.connect(self.exportCSV)
        self.btnExportHTML.clicked.connect(self.exportHTML)
        self.btnCopyClipboard.clicked.connect(self.copyMatrixToClipboard)
        self.btnExportVifCSV.clicked.connect(self.exportVIFCSV)
        self.btnExportVifHTML.clicked.connect(self.exportVIFHTML)

        # ** define highlight color and cache default **
        self.highlight_style           = "background-color: orange;" # #FF8A24;"
        self.default_btn_add_style     = self.btnAdd.styleSheet()
        self.default_btn_verify_style  = self.btnVerifyAlignment.styleSheet()
        self.default_btn_run_style     = self.btnRun.styleSheet()

        # ** initial state: only Add is highlighted **
        self.btnAdd.setStyleSheet(self.highlight_style)
        self.btnVerifyAlignment.setEnabled(False)
        self.btnRun.setEnabled(False)

        self.btnRun.setEnabled(False)
        self.loadAvailableLayers()

        # ** Initial highlight **
        self._reset_step_one()

    def _reset_step_one(self):
        # Step 1: only Add is highlighted; others disabled/default. 
        self.btnAdd .setStyleSheet(self.highlight_style)
        self.btnVerifyAlignment.setEnabled(False)
        self.btnVerifyAlignment.setStyleSheet(self.default_btn_verify_style)
        self.btnRun .setEnabled(False)
        self.btnRun .setStyleSheet(self.default_btn_run_style)

    # *********************************************************************
    # Show all available layers, by layer groups
    def loadAvailableLayers(self):
        # ** TEST for list of layers area **
        print(self.treeAvailableLayers)
        
        self.treeAvailableLayers.clear()
        root = QgsProject.instance().layerTreeRoot()
        mask_id = self.cboMaskLayer.currentData()

        def addGroupItems(group, parentItem):
            for child in group.children():
                if isinstance(child, QgsLayerTreeGroup):
                    groupItem = QTreeWidgetItem([child.name()])
                    font = groupItem.font(0)
                    font.setUnderline(True)
                    groupItem.setFont(0, font)
                    parentItem.addChild(groupItem)
                    addGroupItems(child, groupItem)
                elif isinstance(child, QgsLayerTreeLayer):
                    layer = QgsProject.instance().mapLayer(child.layerId())
                    if isinstance(layer, QgsRasterLayer) and layer.id() != mask_id:
                        item = QTreeWidgetItem([layer.name()])
                        item.setData(0, 1, layer.id())
                        parentItem.addChild(item)

        for top in root.children():
            if isinstance(top, QgsLayerTreeGroup):
                topItem = QTreeWidgetItem([top.name()])
                font = topItem.font(0)
                font.setUnderline(True)
                topItem.setFont(0, font)
                self.treeAvailableLayers.addTopLevelItem(topItem)
                addGroupItems(top, topItem)

        self.cboMaskLayer.clear()
        self.cboMaskLayer.addItem("None")  # default option

        for lyr in QgsProject.instance().mapLayers().values():
            if isinstance(lyr, QgsRasterLayer):
                self.cboMaskLayer.addItem(lyr.name(), lyr.id())
        self.btnRun.setEnabled(False)

    # ** Add selected layers (check if repeated) **
    def addLayers(self): 
        existing_ids = {
            self.treeSelectedLayers.topLevelItem(i).data(0, 1)
            for i in range(self.treeSelectedLayers.topLevelItemCount())
        }

        for item in self.treeAvailableLayers.selectedItems():
            layer_id = item.data(0, 1)
            if layer_id and layer_id not in existing_ids:
                layer = QgsProject.instance().mapLayer(layer_id)
                if layer and isinstance(layer, QgsRasterLayer):
                    newItem = QTreeWidgetItem([layer.name()])
                    newItem.setData(0, 1, layer.id())
                    self.treeSelectedLayers.addTopLevelItem(newItem)
        self.btnRun.setEnabled(False)

        # ** if user has now added at least one **
        count = self.treeSelectedLayers.topLevelItemCount()
        # ** highlight next step if layers exist **
        if count > 0:
            self.btnAdd.setStyleSheet(self.default_btn_add_style)
            self.btnVerifyAlignment.setEnabled(True)
            self.btnVerifyAlignment.setStyleSheet(self.highlight_style)
        else:
            # no layers → go back to step one
            self._reset_step_one()
        # always disable Run until verifyAlignment
        self.btnRun.setEnabled(False)

    def removeLayers(self):
        # 1) Remove all selected items
        for item in self.treeSelectedLayers.selectedItems():
            idx = self.treeSelectedLayers.indexOfTopLevelItem(item)
            self.treeSelectedLayers.takeTopLevelItem(idx)
    
        # 2) Update UI state based on how many are left
        count = self.treeSelectedLayers.topLevelItemCount()
    
        if count == 0:
            # No layers left → go back to Step 1 (only Add highlighted)
            self._reset_step_one()
        else:
            # Some still left → re-enable & highlight Verify Alignment
            self.btnRun.setEnabled(False)
            self.btnRun.setStyleSheet(self.default_btn_run_style)
    
            self.btnVerifyAlignment.setEnabled(True)
            self.btnVerifyAlignment.setStyleSheet(self.highlight_style)
    
            # And restore Add to its default look
            self.btnAdd.setStyleSheet(self.default_btn_add_style)

    ## *********************************************************************
    ## Verify selected layers for alignment
    def verifyAlignment(self):
        layers = self.getSelectedLayers()
        mask_id = self.cboMaskLayer.currentData()
        if mask_id and mask_id != "None":
            mask_layer = QgsProject.instance().mapLayer(mask_id)
            if isinstance(mask_layer, QgsRasterLayer):
                layers.append(mask_layer)
    
        # Must have at least 2 layers
        if len(layers) < 2:
            QMessageBox.warning(
                self,
                "Not enough layers",
                "Select at least 2 layers to verify alignment."
            )
            # keep Verify highlighted, Run disabled
            self.btnVerifyAlignment.setStyleSheet(self.highlight_style)
            self.btnRun.setEnabled(False)
            return
    
        # Check alignment against first layer
        ref_layer = layers[0]
        for lyr in layers[1:]:
            if not self.layersAligned(ref_layer, lyr):
                QMessageBox.warning(
                    self,
                    "Alignment Error",
                    f"Layer '{lyr.name()}' is not aligned with '{ref_layer.name()}'.\n\n"
                    "Use the 'Align Layers' tool."
                )
                # on failure, re-highlight Verify
                self.btnVerifyAlignment.setStyleSheet(self.highlight_style)
                self.btnRun.setEnabled(False)
                return
    
        # All aligned!
        QMessageBox.information(
            self,
            "Alignment OK",
            "All selected layers are aligned."
        )
        # reset Verify‐alignment button to its default look
        self.btnVerifyAlignment.setStyleSheet(self.default_btn_verify_style)
        # enable & highlight the Run button
        self.btnRun.setEnabled(True)
        self.btnRun.setStyleSheet(self.highlight_style)

    def layersAligned(self, l1, l2):
        return (
            l1.width() == l2.width() and
            l1.height() == l2.height() and
            l1.rasterUnitsPerPixelX() == l2.rasterUnitsPerPixelX() and
            l1.rasterUnitsPerPixelY() == l2.rasterUnitsPerPixelY() and
            l1.extent() == l2.extent() and
            l1.crs() == l2.crs()
        )

    def getSelectedLayers(self):
        layers = []
        for i in range(self.treeSelectedLayers.topLevelItemCount()):
            item = self.treeSelectedLayers.topLevelItem(i)
            layer_id = item.data(0, 1)
            layer = QgsProject.instance().mapLayer(layer_id)
            if isinstance(layer, QgsRasterLayer):
                layers.append(layer)
        return layers

    ## *********************************************************************
    ## Correlation analysis
    def runCorrelation(self):
        layers = self.getSelectedLayers()
        if len(layers) < 2:
            QMessageBox.warning(self, "Not enough layers", "Select at least 2 aligned raster layers.")
            return

        # Show busy indicator
        self.progressBar.setVisible(True)
        self.progressBar.setMaximum(0)

        # Prepare worker
        layer_uris = [lyr.dataProvider().dataSourceUri() for lyr in layers]
        mask_id    = self.cboMaskLayer.currentData() or None
        self.thread = QThread()
        # pass a flag to tell the worker whether to compute VIF
        enable_vif = self.chkEnableVIF.isChecked() and HAVE_STATSMODELS
        self.worker = CorrelationWorker(layer_uris, mask_id, enable_vif)
        self.worker.moveToThread(self.thread)

        # 3) Connect thread/worker signals
        self.thread.started.connect(self.worker.run)
        self.worker.finished.connect(self.onResultsReady)
        self.worker.error.connect(self.onResultsError)
        self.worker.finished.connect(self.thread.quit)
        self.worker.error.connect(self.thread.quit)
        self.worker.finished.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.thread.deleteLater)

        # Start
        self.thread.start()

    ## *********************************************************************
    ## After the Correlation analysis is done, prepare the outputs... 
    def onResultsReady(self, data):

        # hide spinner + reset run button
        self.progressBar.setVisible(False)
        self.btnRun.setStyleSheet(self.default_btn_run_style)
        self.btnRun.setEnabled(False)

        # 1) Unpack everything from the worker
        corr      = data["corr"]        # numpy matrix
        raw_names = data["names"]       # list of filenames, e.g. ['landuse1989.tif', ...]
        vifs      = data["vif"]         # list of floats
        total_pix = data["total_pix"]
        valid_pix = data["valid_pix"]

        # 2) Strip off extensions ('.tif', '.img', etc.)
        names = [os.path.splitext(n)[0] for n in raw_names]

        # 3) Store for exports
        self._layer_names = names
        self._corr_matrix = corr
        self.vif_data = pd.DataFrame({"layer": names, "VIF": vifs})

        # Retrieve NaN‐summary from the worker
        nan_summary = data.get("nan_summary", {})

        # ————————————————————————————————
        # 1. BUILD SUMMARY HTML
        # ————————————————————————————————
        summary_html = (
            f"<p><i>Based on {valid_pix:,} valid pixels "
            f"out of {total_pix:,} total pixels.</i></p>"
        )

        # Strong correlations (|ρ| ≥ 0.8)
        strong = [
            f"{names[i]} ↔ {names[j]}: ρ = {corr[i,j]:.3f}"
            for i in range(len(names)) for j in range(i+1, len(names))
            if abs(corr[i,j]) >= 0.8
        ]
        summary_html += "<h3>Strong Spearman ρ (|ρ| ≥ 0.8)</h3>"
        if strong:
            summary_html += "<ul>" + "".join(f"<li>{s}</li>" for s in strong) + "</ul>"
        else:
            summary_html += "<p>No strong pairwise correlations detected.</p>"

        # VIF summary
        summary_html += "<h3>Variance Inflation Factor (VIF)</h3><ul>"
        for name, vif in zip(names, vifs):
          if vif is None:
            display, warn = "N/A", ""
          elif np.isinf(vif):
            display, warn = "Perfect collinearity", ""
          else:
            display = f"{vif:.2f}"
            warn    = " <b style='color:red'>(risk)</b>" if vif >= 10 else ""
          summary_html += f"<li>{name}: VIF = {display}{warn}</li>"
        summary_html += "</ul>"

        summary_html += "<h3>Missing data per layer</h3><ul>"
        for layer, count in nan_summary.items():
            summary_html += f"<li>{layer}: {count} missing pixels</li>"
        summary_html += "</ul>"

        # set the text of your “resume” tab
        self.htmlSummary.setHtml(summary_html)

        # ————————————————————————————————
        # 2. BUILD CORRELATION MATRIX
        # ————————————————————————————————
        # …inside onResultsReady…

        # 1) START building the matrix HTML
        matrix_html = "<h3>Correlation Matrix</h3>"
        matrix_html += (
            "<table style='"
            "border-collapse:collapse; width:100%; font-family:sans-serif;"
            "'>"
        )
        # 2) Column headers
        matrix_html += "<tr>"
        #   first blank top-left cell
        matrix_html += (
            "<th style='"
            "border-top:1px solid black; border-bottom:1px solid black;"
            " padding:6px;'"
            "></th>"
        )
        #   now one <th> per cleaned name
        for col_name in names:
            matrix_html += (
                f"<th style="
                "'border-top:1px solid black; "
                "border-bottom:1px solid black; "
                "padding:6px; text-align:center;'"
                f">{col_name}</th>"
            )
        matrix_html += "</tr>"

        # data rows
        for i, row_name in enumerate(names):
            matrix_html += "<tr>"
            # row header: use row_name, not name
            matrix_html += (
                f"<th style='border-top:1px dotted #555; "
                f"border-bottom:1px dotted #555; padding:6px; "
                f"text-align:left; font-weight:bold;'>{row_name}</th>"
            )
            for j, _ in enumerate(names):
                val = corr[i,j]
                style = (
                    "text-align:center; padding:6px;"
                    " border-top:1px dotted #555; border-bottom:1px dotted #555;"
                )
                # diagonal
                if i == j:
                    style += " background-color:#CCC;"
                # strong
                elif abs(val) >= 0.8:
                    style += " background-color:#FF9197; font-weight:bold;"
                matrix_html += f"<td style='{style}'>{val:.3f}</td>"
            matrix_html += "</tr>"

        matrix_html += "</table>"
        self.htmlMatrix.setHtml(matrix_html)

        # ————————————————————————————————
        # 3. BUILD VIF RESULTS TABLE
        # ————————————————————————————————
        vif_html = (
            "<h3>VIF Results</h3>"
            "<table style='border-collapse:collapse; width:100%; font-family:sans-serif;'>"
            "<tr>"
            "<th style='border-top:1px solid black; border-bottom:1px solid black;"
            " padding:6px;'>Layer</th>"
            "<th style='border-top:1px solid black; border-bottom:1px solid black;"
            " padding:6px;'>VIF</th>"
            "</tr>"
        )
        for name, vif in zip(names, vifs):
            if np.isinf(vif):
                display = "Perfect collinearity"
            else:
                display = f"{vif:.2f}"
            cell_style = "padding:6px; border-top:1px dotted #555; border-bottom:1px dotted #555;"
            if not np.isinf(vif) and vif >= 10:
                cell_style += " background-color:#FFDDDD; font-weight:bold;"
            vif_html += (
                f"<tr>"
                f"<td style='{cell_style} text-align:left;'>{name}</td>"
                f"<td style='{cell_style} text-align:center;'>{display}</td>"
                "</tr>"
            )
        vif_html += "</table>"

        # 4) Correlation matrix HTML 
        self.htmlMatrix.setHtml(matrix_html)

        # 5) VIF full‐table HTML (optional)
        self.htmlVIF.setHtml(vif_html)

    def showEvent(self, event):
        # ** Called whenever the dialog is shown 
        # ** We use it to clear out any prior selections or results.
        super().showEvent(event)

        # 1) Clear the selected‐layers list
        self.treeSelectedLayers.clear()

        # 2) Clear any previously computed HTML
        self.htmlSummary.clear()
        self.htmlMatrix.clear()
        # if you have a VIF tab:
        try:
            self.htmlVIF.clear()
        except AttributeError:
            pass

        # 3) Reset the step‐by‐step button highlighting
        self._reset_step_one()

    def onResultsError(self, message):
        self.progressBar.setVisible(False)
        self.thread.quit()
        QMessageBox.critical(self, "Calculation error", message)

    ## *********************************************************************
    ## Export buttons... 
    
    def exportCSV(self):
        if self._corr_matrix is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export CSV", "", "CSV files (*.csv)")
        if path:
            with open(path, 'w', newline='') as f:
                writer = csv.writer(f)
                writer.writerow([""] + self._layer_names)
                for name, row in zip(self._layer_names, self._corr_matrix):
                    writer.writerow([name] + [f"{val:.4f}" for val in row])

    def exportHTML(self):
        if self._corr_matrix is None:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export HTML", "", "HTML files (*.html)")
        if path:
            with open(path, 'w') as f:
                f.write(self.htmlMatrix.toHtml())

    def copyMatrixToClipboard(self):
        if self._corr_matrix is None:
            return

    def exportVIFCSV(self):
        if not hasattr(self, "vif_data") or self.vif_data is None:
            return
    
        path, _ = QFileDialog.getSaveFileName(self, "Export VIF CSV", "", "CSV files (*.csv)")
        if path:
            # Prepare formatted display version
            display_vif = self.vif_data.copy()
            display_vif["VIF"] = display_vif["VIF"].apply(
                lambda x: "Perfect collinearity" if np.isinf(x) or pd.isna(x) else f"{x:.2f}"
            )
            display_vif.to_csv(path, index=False)

    def exportVIFHTML(self):
        if not hasattr(self, "htmlVIF") or not self.htmlVIF.toHtml():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export VIF HTML", "", "HTML files (*.html)")
        if path:
            with open(path, 'w') as f:
                f.write(self.htmlVIF.toHtml())

        output = []
        output.append(",".join([""] + self._layer_names))
        for name, row in zip(self._layer_names, self._corr_matrix):
            output.append(",".join([name] + [f"{val:.4f}" for val in row]))

        clipboard = QApplication.clipboard()
        clipboard.setText("\n".join(output))

    def run(self):
        """Show the dialog modally."""
        return self.exec_()

