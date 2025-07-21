import os
from qgis.PyQt import uic
from qgis.PyQt.QtWidgets import QFileDialog, QMessageBox, QTreeWidgetItem, QComboBox, QDialog
from qgis.PyQt.QtCore import Qt
from qgis.core import QgsProject, QgsRasterLayer
from osgeo import gdal
import numpy as np

# List of ecosystem states for the combobox
EC_STATES = [
    'Physical', 'Chemical', 'Compositional',
    'Structural', 'Functional', 'Landscape'
]

#ui_path = os.path.join(os.path.dirname(__file__), 'tool_normalise_invert.ui')

class NormalizeTool:
    def __init__(self, iface):
        self.iface = iface
        self.ui_path = os.path.join(os.path.dirname(__file__), 'tool_normalise_invert.ui')

    def run(self):
        # load the UI into a QDialog parented to the QGIS main window
        # self.dlg ...
        self.dialog = uic.loadUi(self.ui_path, QDialog(self.iface.mainWindow()))
        self.dialog.setFixedSize(1424, 650)

        # Grab all raster layers
        self.layers = [
            lyr for lyr in QgsProject.instance().mapLayers().values()
            if isinstance(lyr, QgsRasterLayer)
        ]

        # Populate tree: one row per layer
        tree = self.dialog.treeLayers
        tree.clear()
        for lyr in self.layers:
            # Create a 4‐column item
            item = QTreeWidgetItem(['', lyr.name(), '', ''])
            # Make column 0 (“Use?”) checkable
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(0, Qt.Unchecked)
            # Make column 3 (“Invert?”) checkable
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(3, Qt.Unchecked)
            tree.addTopLevelItem(item)
            # Put EC State combobox into column 2
            combo = QComboBox()
            combo.addItems(EC_STATES)
            tree.setItemWidget(item, 2, combo)

        # set fixed widths (in pixels) per column:
        tree.setColumnWidth(0,  50)   # “Use?” checkbox
        tree.setColumnWidth(1, 310)   # Layer name
        tree.setColumnWidth(2, 120)   # EC State combobox
        tree.setColumnWidth(3,  60)   # “Invert?” checkbox

        # Populate masks comboboxes
        for lyr in self.layers:
            self.dialog.comboMinMask.addItem(lyr.name())
            self.dialog.comboMaxMask.addItem(lyr.name())

        # Connect browse button
        self.dialog.btnBrowse.clicked.connect(self.browseFolder)
        # Connect OK/Cancel
        self.dialog.buttonBox.accepted.connect(self.process)
        self.dialog.buttonBox.rejected.connect(self.dialog.close)
        self.dialog.show()

    def browseFolder(self):
        folder = QFileDialog.getExistingDirectory(self.dialog, 'Select Output Folder')
        if folder:
            self.dialog.lineFolder.setText(folder)

    def process(self):
        tree = self.dialog.treeLayers

        # Build lists with ec_state and invert flag
        tasks = []
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            if item.checkState(0) != Qt.Checked:
                continue  # skip rows not “Used”
            name = item.text(1)
            lyr = next(l for l in self.layers if l.name() == name)
            ec_state = tree.itemWidget(item, 2).currentText()
            invert = (item.checkState(3) == Qt.Checked)
            tasks.append({'layer': lyr, 'ec_state': ec_state, 'invert': invert})

        # Now read masks, output settings, etc.
        min_mask_layer = self.layers[self.dialog.comboMinMask.currentIndex()]
        max_mask_layer = self.layers[self.dialog.comboMaxMask.currentIndex()]
        out_folder = self.dialog.lineFolder.text()
        prefix = self.dialog.linePrefix.text() or ''
        suffix = self.dialog.lineSuffix.text() or ''
        clip = self.dialog.checkClip.isChecked()
        add_proj = self.dialog.checkAdd.isChecked()
        csv_name = self.dialog.lineCSV.text() or 'normalization_summary.csv'
        csv_path = os.path.join(out_folder, csv_name)

        # Load mask arrays
        min_ds = gdal.Open(min_mask_layer.source())
        max_ds = gdal.Open(max_mask_layer.source())
        min_arr = min_ds.GetRasterBand(1).ReadAsArray() == 1
        max_arr = max_ds.GetRasterBand(1).ReadAsArray() == 1
        # Clip the max‐mask by the min‐mask
        max_arr = max_arr & min_arr

        summary = []
        for task in tasks:
            lyr = task['layer']
            invert = task['invert']
            ec_state = task['ec_state']
            name = lyr.name()
            self.iface.messageBar().pushMessage(
                f"Processing {name} ({ec_state}, invert={invert})",
                level=0, duration=5
            )
            ds = gdal.Open(lyr.source())
            arr = ds.GetRasterBand(1).ReadAsArray().astype(float)
            nod = ds.GetRasterBand(1).GetNoDataValue()
            valid = (arr != nod) if nod is not None else ~np.isnan(arr)

            # compute and cap
            mmin = float(np.min(arr[min_arr & valid]))
            mmax = float(np.max(arr[max_arr & valid]))
            arr[arr < mmin] = mmin
            arr[arr > mmax] = mmax

            # normalize / invert
            norm = (arr - mmin) / (mmax - mmin)
            if invert:
                norm = 1 - norm

            # clip
            if clip:
                norm[~min_arr] = nod if nod is not None else -9999

            # save raster
            out_fn = f"{prefix}{name}{suffix}.tif"
            out_path = os.path.join(out_folder, out_fn)
            drv = gdal.GetDriverByName('GTiff')
            out_ds = drv.Create(
                out_path, ds.RasterXSize, ds.RasterYSize, 1, gdal.GDT_Float32
            )
            out_ds.SetGeoTransform(ds.GetGeoTransform())
            out_ds.SetProjection(ds.GetProjection())
            band = out_ds.GetRasterBand(1)
            band.WriteArray(norm.astype(np.float32))
            band.SetNoDataValue(nod if nod is not None else -9999)
            out_ds = None

            if add_proj:
                rl = QgsRasterLayer(out_path, out_fn)
                QgsProject.instance().addMapLayer(rl)

            summary.append(f"{name},{ec_state},{mmin},{mmax},{invert}")

        # write CSV
        with open(csv_path, 'w') as f:
            f.write('layer,ec_state,min,max,inverted\n')
            f.write('\n'.join(summary))

        QMessageBox.information(
            self.iface.mainWindow(),
            'Done',
            f'Normalization complete.\nSummary saved to {csv_path}'
        )
        self.dialog.close()
