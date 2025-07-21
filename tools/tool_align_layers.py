# -*- coding: utf-8 -*-
import os
from qgis.core import QgsApplication

# Step 1: get the “prefix” that QGIS is using
_qgis_prefix = QgsApplication.prefixPath()  
# On macOS this might be …/QGIS.app/Contents/MacOS or …/QGIS.app/Contents/
# On Windows or Linux it might be …/Program Files/QGIS 3.xx or /usr

# Step 2: construct the two most likely locations of proj.db
candidate1 = os.path.join(_qgis_prefix, 'share', 'proj')
candidate2 = os.path.join(_qgis_prefix, 'proj')
candidate3 = os.path.join(os.path.dirname(_qgis_prefix), 'Resources', 'share', 'proj')

# Step 3: pick whichever one actually exists
if os.path.isdir(candidate1):
    os.environ['PROJ_LIB'] = candidate1
elif os.path.isdir(candidate2):
    os.environ['PROJ_LIB'] = candidate2
elif os.path.isdir(candidate3):
    os.environ['PROJ_LIB'] = candidate3
else:
    # (fallback) leave PROJ_LIB unset, so QGIS’s defaults apply
    # or log a warning
    print("Warning: cannot find a ‘share/proj’ under", _qgis_prefix)

# Now import the rest of PyQGIS / processing safely
import re
from qgis.PyQt import uic
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog,
    QFileDialog,
    QListWidgetItem,
    QTableWidgetItem,
    QComboBox,
    QMessageBox,
    QProgressDialog
)
from qgis.core import (
    QgsProject,
    QgsRasterLayer
)

from qgis import processing  # ensure we have access to processing.run()

FORM_CLASS, _ = uic.loadUiType(os.path.join(os.path.dirname(__file__), "tool_align_layers.ui"))

class AlignLayersTool(QDialog, FORM_CLASS):
    def __init__(self, iface):
        # use the QGIS main window as the dialog’s parent
        super().__init__(iface.mainWindow())
        self.iface = iface
        self.setupUi(self)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        # Store reference layer info
        self.ref_layer = None
        self.ref_cellsize = None
        self.ref_cols = None
        self.ref_rows = None
        self.ref_crs = None

        # Connect signals
        self.toolButton_browse_output.clicked.connect(self.select_output_folder)
        self.comboBox_reference_layer.currentIndexChanged.connect(self.on_reference_layer_changed)
        self.pushButton_add.clicked.connect(self.add_selected_layers)
        self.pushButton_remove.clicked.connect(self.remove_selected_layers)
        self.pushButton_run.clicked.connect(self.run_alignment)
        self.pushButton_cancel.clicked.connect(self.reject)  # close dialog

        # Initialize UI
        self.populate_reference_layers()
        self.populate_available_layers()
        self.prepare_table_headers()

    def select_output_folder(self):
        """Open a folder dialog to select output folder."""
        folder = QFileDialog.getExistingDirectory(self, "Select Output Folder", "")
        if folder:
            self.lineEdit_output_folder.setText(folder)

    def populate_reference_layers(self):
        """Populate the combo box with all raster layers in the project."""
        self.comboBox_reference_layer.clear()
        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsRasterLayer):
                self.comboBox_reference_layer.addItem(layer.name(), layer.id())

        if self.comboBox_reference_layer.count() == 0:
            self.comboBox_reference_layer.addItem("<No raster layers found>", None)
            self.comboBox_reference_layer.setEnabled(False)

    def on_reference_layer_changed(self, idx):
        """
        When the user selects a new reference layer, extract its characteristics:
        - Cell size (X, Y) → rounded to 1 decimal (or 0.0 if dimensions are zero)
        - Number of columns
        - Number of rows
        - CRS
        Then display them in the read-only text area, and refresh “Available Layers.”
        """
        layer_id = self.comboBox_reference_layer.itemData(idx)
        if not layer_id:
            self.ref_layer = None
            self.plainTextEdit_ref_info.clear()
            self.populate_available_layers()
            return

        layer = QgsProject.instance().mapLayer(layer_id)
        if not isinstance(layer, QgsRasterLayer):
            return

        self.ref_layer = layer

        # Extract dimensions & CRS
        extent = layer.extent()
        width = layer.width()
        height = layer.height()
        crs = layer.crs()
        self.ref_crs = crs
        self.ref_cols = width
        self.ref_rows = height

        # Compute cell size (guard against division by zero)
        if width == 0 or height == 0:
            cell_x = 0.0
            cell_y = 0.0
        else:
            cell_x = abs(extent.width() / float(width))
            cell_y = abs(extent.height() / float(height))
        # Round to one decimal place
        self.ref_cellsize = (round(cell_x, 1), round(cell_y, 1))

        # Display in read-only text area
        info_text = (
            f"<b>Cell size (X, Y):</b> {self.ref_cellsize[0]:.1f}, {self.ref_cellsize[1]:.1f}; "
            f"<b>Columns:</b> {self.ref_cols}; "
            f"<b>Rows:</b> {self.ref_rows}; "
            f"<b>CRS:</b> {crs.authid()}"
        )
        self.plainTextEdit_ref_info.setPlainText(info_text)
        # make intro background transparent to match form
        #self.plainTextEdit_ref_info.setStyleSheet("background-color: transparent;")
        self.plainTextEdit_ref_info.setStyleSheet("""
            background-color: transparent;
            border: none;
        """)
        # TO TEST IF THE ABOVE FAILS: 
        #self.plainTextEdit_ref_info.viewport().setStyleSheet("background-color: transparent;")

        # Refresh “Available Layers” to exclude the reference
        self.populate_available_layers()

    def populate_available_layers(self):
        """
        List all raster layers except the chosen reference.
        Each item shows: "<LayerName> (Cell size: X.X, Y.Y)" with one-decimal rounding.
        The layer ID is stored in Qt.UserRole.
        """
        self.listWidget_available.clear()
        ref_id = None
        idx = self.comboBox_reference_layer.currentIndex()
        if idx >= 0:
            ref_id = self.comboBox_reference_layer.itemData(idx)

        for layer in QgsProject.instance().mapLayers().values():
            if isinstance(layer, QgsRasterLayer) and layer.id() != ref_id:
                # Compute cell size (guard against zero dims)
                ext = layer.extent()
                w = layer.width()
                h = layer.height()
                if w == 0 or h == 0:
                    pix_x, pix_y = 0.0, 0.0
                else:
                    pix_x = abs(ext.width() / float(w))
                    pix_y = abs(ext.height() / float(h))
                cell_str = f"{pix_x:.1f}, {pix_y:.1f}"
                display_text = f"{layer.name()} (Cell size: {cell_str})"

                item = QListWidgetItem(display_text)
                item.setData(Qt.UserRole, layer.id())
                self.listWidget_available.addItem(item)

    def prepare_table_headers(self):
        """Ensure the table has 7 columns and zero rows initially."""
        self.tableWidget_selected.setRowCount(0)
        # Column headers (from .ui):
        # ["Original Name","Cell size","Data Type","CRS","New Layer Name","Interp. Method","Output Type"]

    def add_selected_layers(self):
        """
        Move items from “Available” into the “Selected” table.
        For each:
         1. Original Name (non-editable)
         2. Cell size (non-editable; one-decimal, or "0.0, 0.0" if dims are zero)
         3. Data Type (non-editable; from provider)
         4. CRS (non-editable; authid)
         5. New Layer Name (editable, max length 20, left-aligned)
         6. Interpolation Method (QComboBox: default based on resolution vs reference)
         7. Output Type (non-editable, “Float32”)
        """
        selected_items = self.listWidget_available.selectedItems()
        for item in selected_items:
            layer_id = item.data(Qt.UserRole)
            layer = QgsProject.instance().mapLayer(layer_id)
            if not isinstance(layer, QgsRasterLayer):
                continue

            row = self.tableWidget_selected.rowCount()
            self.tableWidget_selected.insertRow(row)

            # 1. Original Name (non-editable)
            name_item = QTableWidgetItem(layer.name())
            name_item.setFlags(name_item.flags() ^ Qt.ItemIsEditable)
            self.tableWidget_selected.setItem(row, 0, name_item)

            # 2. Cell size – compute from extent and dimensions (guard against zero dims)
            ext = layer.extent()
            w = layer.width()
            h = layer.height()
            if w == 0 or h == 0:
                pix_x, pix_y = 0.0, 0.0
            else:
                pix_x = abs(ext.width() / float(w))
                pix_y = abs(ext.height() / float(h))
            cell_str = f"{pix_x:.1f}, {pix_y:.1f}"
            cell_item = QTableWidgetItem(cell_str)
            cell_item.setFlags(cell_item.flags() ^ Qt.ItemIsEditable)
            self.tableWidget_selected.setItem(row, 1, cell_item)

            # 3. Data Type – try provider.dataType(1), fallback to dataTypeName(1)
            dtype = layer.dataProvider().dataType(1)
            if not dtype:
                try:
                    dtype = layer.dataProvider().dataTypeName(1)
                except Exception:
                    dtype = "Unknown"
            dtype_item = QTableWidgetItem(dtype)
            dtype_item.setFlags(dtype_item.flags() ^ Qt.ItemIsEditable)
            self.tableWidget_selected.setItem(row, 2, dtype_item)

            # 4. CRS – layer.crs().authid()
            crs_item = QTableWidgetItem(layer.crs().authid())
            crs_item.setFlags(crs_item.flags() ^ Qt.ItemIsEditable)
            self.tableWidget_selected.setItem(row, 3, crs_item)

            # 5. New Layer Name – editable, max length 20, left-aligned
            new_layer_item = QTableWidgetItem("")
            new_layer_item.setFlags(new_layer_item.flags() | Qt.ItemIsEditable)
            new_layer_item.setData(Qt.UserRole, layer.id())  # store original layer ID
            new_layer_item.setToolTip("Enter a name (1–20 characters; no \\ / : * ? \" < > | )")
            new_layer_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            self.tableWidget_selected.setItem(row, 4, new_layer_item)

            # 6. Interpolation Method – QComboBox
            interp_combo = QComboBox()
            interp_combo.addItem("Nearest Neighbor")
            interp_combo.addItem("Cubic B-spline")
            # Pre-select based on resolution vs reference if available
            if self.ref_cellsize:
                src_pix_size = max(pix_x, pix_y)
                ref_pix_size = max(self.ref_cellsize[0], self.ref_cellsize[1])
                default_method = "Nearest Neighbor" if src_pix_size <= ref_pix_size else "Cubic B-spline"
            else:
                default_method = "Nearest Neighbor"
            interp_combo.setCurrentText(default_method)
            self.tableWidget_selected.setCellWidget(row, 5, interp_combo)

            # 7. Output Type – non-editable, “Float32”
            out_type_item = QTableWidgetItem("Float64")
            out_type_item.setFlags(out_type_item.flags() ^ Qt.ItemIsEditable)
            out_type_item.setTextAlignment(Qt.AlignCenter)
            self.tableWidget_selected.setItem(row, 6, out_type_item)

            # Finally, remove this item from “Available”
            row_index = self.listWidget_available.row(item)
            self.listWidget_available.takeItem(row_index)

    def remove_selected_layers(self):
        """
        Remove selected rows from the “Selected Layers” table and put them back into “Available Layers.”
        """
        selected_ranges = self.tableWidget_selected.selectionModel().selectedRows()
        rows_to_remove = sorted([r.row() for r in selected_ranges], reverse=True)
        for row in rows_to_remove:
            orig_name_item = self.tableWidget_selected.item(row, 0)
            layer_name = orig_name_item.text()
            orig_layer_id = self.tableWidget_selected.item(row, 4).data(Qt.UserRole)

            # Re-add to available (recompute cell size if needed)
            layer = QgsProject.instance().mapLayer(orig_layer_id)
            if isinstance(layer, QgsRasterLayer):
                ext = layer.extent()
                w = layer.width()
                h = layer.height()
                if w == 0 or h == 0:
                    pix_x, pix_y = 0.0, 0.0
                else:
                    pix_x = abs(ext.width() / float(w))
                    pix_y = abs(ext.height() / float(h))
                cell_str = f"{pix_x:.1f}, {pix_y:.1f}"
                display_text = f"{layer.name()} (Cell size: {cell_str})"
                new_item = QListWidgetItem(display_text)
                new_item.setData(Qt.UserRole, orig_layer_id)
                self.listWidget_available.addItem(new_item)

            # Remove the row
            self.tableWidget_selected.removeRow(row)

    def run_alignment(self):
        self.show()
        """
        Collect all parameters, validate them, and run two‐step processing for each selected layer:
         1. Warp/reproject/clip to reference (gdal:warpreproject, Float64)
         2. Multiply by the reference mask (gdal:rastercalculator, Float64)
        If “Add output layers to project” is checked, each output is added under “01. Aligned layers.”
        Show a QProgressDialog (“hover window”) with row‐by‐row progress and Cancel button.
        """
        # 1. Validate output folder
        output_folder = self.lineEdit_output_folder.text().strip()
        if not output_folder or not os.path.isdir(output_folder):
            QMessageBox.critical(self, "Error", "Please select a valid output folder.")
            return

        # 2. Validate reference layer
        if not self.ref_layer:
            QMessageBox.critical(self, "Error", "Please select a reference layer.")
            return

        # 3. Validate that at least one layer is selected
        total_rows = self.tableWidget_selected.rowCount()
        if total_rows == 0:
            QMessageBox.information(self, "No Layers", "No layers selected to align.")
            return

        # 4. Validate each “New Layer Name” (1–20 chars, no invalid characters)
        invalid_pattern = re.compile(r'[\/:\\\*\?"<>\|]')
        summary_lines = []
        for row in range(total_rows):
            new_name_item = self.tableWidget_selected.item(row, 4)
            new_name = new_name_item.text().strip()
            if not new_name:
                QMessageBox.critical(
                    self,
                    "Invalid Name",
                    f"Row {row+1}: New layer name cannot be empty."
                )
                return
            if len(new_name) > 20:
                QMessageBox.critical(
                    self,
                    "Invalid Name Length",
                    f"Row {row+1}: Name '{new_name}' exceeds 20 characters."
                )
                return
            if invalid_pattern.search(new_name):
                QMessageBox.critical(
                    self,
                    "Invalid Characters",
                    f"Row {row+1}: Name '{new_name}' contains invalid character(s). "
                    r"Disallowed: \ / : * ? \" < > |"
                )
                return

            interp_widget = self.tableWidget_selected.cellWidget(row, 5)
            interp_method = interp_widget.currentText()
            summary_lines.append(f"{new_name} ({interp_method})")

        # Build confirmation text
        summary_text = "Layers to process:\n" + "\n".join(summary_lines)
        summary_text += f"\n\nOutput folder:\n{output_folder}"

        # 5. Confirm with the user
        confirm = QMessageBox.question(
            self,
            "Confirm Alignment",
            summary_text,
            QMessageBox.Ok | QMessageBox.Cancel,
            QMessageBox.Ok
        )
        if confirm != QMessageBox.Ok:
            return

        # 6. Check if user wants to add outputs to project
        add_to_project = self.checkBox_addToProject.isChecked()
        if add_to_project:
            # Ensure “01. Aligned layers” group exists (or create it)
            root = QgsProject.instance().layerTreeRoot()
            group = root.findGroup("01. Aligned layers")
            if not group:
                group = root.addGroup("01. Aligned layers")

        # 7. Proceed with processing, using a QProgressDialog (the “hover window”)
        progress_dialog = QProgressDialog("Aligning rasters...", "Cancel", 0, total_rows, self)
        progress_dialog.setWindowTitle("Processing")
        progress_dialog.setWindowModality(Qt.WindowModal)
        progress_dialog.show()

        for row in range(total_rows):
            if progress_dialog.wasCanceled():
                break

            orig_layer_id = self.tableWidget_selected.item(row, 4).data(Qt.UserRole)
            orig_layer = QgsProject.instance().mapLayer(orig_layer_id)
            new_basename = self.tableWidget_selected.item(row, 4).text().strip()
            interp_method = self.tableWidget_selected.cellWidget(row, 5).currentText()

            # Translate interp_method → integer code
            if interp_method == "Nearest Neighbor":
                resample_code = 0
            else:  # "Cubic B-spline"
                resample_code = 3

            # 7a) Warp/reproject/clip to reference (Float64)
            ref_ext = self.ref_layer.extent()
            tgt_x_res = self.ref_cellsize[0]
            tgt_y_res = self.ref_cellsize[1]

            warp_params = {
                'INPUT': orig_layer.source(),
                'TARGET_CRS': self.ref_crs.toWkt(),
                'RESAMPLING': resample_code,
                'NODATA': None,
                'TARGET_RESOLUTION': max(tgt_x_res, tgt_y_res),
                'OPTIONS': '',
                'DATA_TYPE': 6,  # Float64 (double)
                'TARGET_EXTENT': f"{ref_ext.xMinimum()},{ref_ext.xMaximum()},{ref_ext.yMinimum()},{ref_ext.yMaximum()}",
                'TARGET_EXTENT_CRS': self.ref_crs.toWkt(),
                'MULTITHREADING': False,
                'OUTPUT': 'TEMPORARY_OUTPUT'
            }

            try:
                warp_result = processing.run("gdal:warpreproject", warp_params)
                temp_warped = warp_result['OUTPUT']
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Warp Error",
                    f"Error warping layer '{orig_layer.name()}':\n{str(e)}"
                )
                progress_dialog.setValue(row + 1)
                continue

            # 7b) Apply mask via raster calculator (Float64)
            final_filepath = os.path.join(output_folder, f"{new_basename}.tif")
            calc_params = {
                'INPUT_A': temp_warped,
                'BAND_A': 1,
                'INPUT_B': self.ref_layer.source(),
                'BAND_B': 1,
                'FORMULA': 'A*B',
                'RTYPE': 6,  # Float64
                'NODATA': None,
                'OPTIONS': '',
                'OUTPUT': final_filepath
            }
            try:
                processing.run("gdal:rastercalculator", calc_params)
            except Exception as e:
                QMessageBox.warning(
                    self,
                    "Mask Error",
                    f"Error applying mask to '{new_basename}':\n{str(e)}"
                )
                progress_dialog.setValue(row + 1)
                continue

            # 7c) If user opted in, add the new raster to the project under “01. Aligned layers”
            if add_to_project:
                # Create a QgsRasterLayer from the output and add to project
                rlayer = QgsRasterLayer(final_filepath, new_basename)
                if rlayer.isValid():
                    QgsProject.instance().addMapLayer(rlayer, False)
                    group.addLayer(rlayer)
                else:
                    QMessageBox.warning(self, "Add to Project", f"Could not load {new_basename}.tif as a layer.")

            progress_dialog.setValue(row + 1)

        progress_dialog.close()
        QMessageBox.information(self, "Done", "All selected rasters have been aligned and masked.")

    def run(self):
        # Show the Align Layers dialog.
        return self.exec_()

