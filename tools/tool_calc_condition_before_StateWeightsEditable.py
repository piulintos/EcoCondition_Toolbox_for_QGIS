# Calculate ecosystem condition tool stub
import os
import processing
from collections import defaultdict
import numpy as np
from osgeo import gdal
gdal.UseExceptions()  # enable GDAL Python exceptions and suppress FutureWarning


from qgis.PyQt           import uic
from qgis.PyQt.QtCore    import Qt, QUrl
from qgis.PyQt.QtGui     import QFont, QBrush, QColor, QIcon, QPixmap, QPainter, QLinearGradient
from qgis.PyQt.QtWidgets import (
    QAbstractItemView,
    QCheckBox, 
    QDoubleSpinBox,
    QDialog,
    QFileDialog, 
    QGraphicsColorizeEffect,
    QGridLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QSizePolicy,
    QTableWidget,
    QTableWidgetItem, 
    QTreeWidget, 
    QTreeWidgetItem,
    QWidget,
    QVBoxLayout,
    QHBoxLayout
)
from qgis.gui            import QgsMapCanvas
from qgis.core           import (
    QgsProject,
    QgsCoordinateReferenceSystem,
    QgsVectorLayer,
    QgsRasterLayer,
    QgsRasterShader, 
    QgsRasterBandStats,
    QgsRasterPipe,
    QgsLayerTreeGroup,
    QgsLayerTreeLayer,
    QgsSingleBandPseudoColorRenderer,
    QgsSingleBandGrayRenderer,
    QgsGradientColorRamp,
    QgsColorRampShader,
    QgsContrastEnhancement, 
    QgsMessageLog, 
    Qgis
)

# ordered list of the six EC‐state names, matching tabs 3→8
EC_STATES = [
    'Physical',
    'Chemical',
    'Compositional',
    'Structural',
    'Functional',
    'Landscape'
]
# Tab index (2→7) to EC_STATES mapping
TAB_STATE = {
    2: EC_STATES[0],  # 'Physical'
    3: EC_STATES[1],  # 'Chemical'
    4: EC_STATES[2],  # 'Compositional'
    5: EC_STATES[3],  # 'Structural'
    6: EC_STATES[4],  # 'Functional'
    7: EC_STATES[5],  # 'Landscape'
}

class EcoCondTool:
    def __init__(self, iface):
        self.iface = iface
        # path to the UI file
        self.ui_path = os.path.join(os.path.dirname(__file__), 'tool_calc_condition.ui')

        ## HTML text blocks for TABs 2 to 11:
        htmlTab1 = f"""
        <div style="text-align:left">
          <h3>Base data for the analysis</h3>
          Please set a destination folder for the resulting raster files.
        </div>
        """
        htmlTab2 = f"""
        <div style="text-align:left">
          <h3>Layers to consider for the assessment of the Ecosystem physical state</h3>
          From the left window below, select the raster layers you want to use for the assessment of the physical state of the study area. You must select at least one layer. Click on the 'Add' button to add them to the right panel. On this panel, provide a short name for the variable, and indicate if the layers need to be inverted for the process. Once this is done, click on the 'Check alignment for selected layers' button'. If all selected layers are aligned, you can proceed by click on the 'Next EC State' button. 
        </div>
        """
        htmlTab3 = f"""
        <div style="text-align:left">
          <h3>Layers to consider for the assessment of the Ecosystem chemical state</h3>
          From the left window below, select the raster layers you want to use for the assessment of the chemical state of the study area. You must select at least one layer. Click on the 'Add' button to add them to the right panel. On this panel, provide a short name for the variable, and indicate if the layers need to be inverted for the process. Once this is done, click on the 'Check alignment for selected layers' button'. If all selected layers are aligned, you can proceed by click on the 'Next EC State' button.
        </div>
        """
        htmlTab4 = f"""
        <div style="text-align:left">
          <h3>Layers to consider for the assessment of the Ecosystem compositional state</h3>
          From the left window below, select the raster layers you want to use for the assessment of the compositional state of the study area. You must select at least one layer. Click on the 'Add' button to add them to the right panel. On this panel, provide a short name for the variable, and indicate if the layers need to be inverted for the process. Once this is done, click on the 'Check alignment for selected layers' button'. If all selected layers are aligned, you can proceed by click on the 'Next EC State' button. 
        </div>
        """
        htmlTab5 = f"""
        <div style="text-align:left">
          <h3>Layers to consider for the assessment of the Ecosystem structural state</h3>
          From the left window below, select the raster layers you want to use for the assessment of the structural state of the study area. You must select at least one layer. Click on the 'Add' button to add them to the right panel. On this panel, provide a short name for the variable, and indicate if the layers need to be inverted for the process. Once this is done, click on the 'Check alignment for selected layers' button'. If all selected layers are aligned, you can proceed by click on the 'Next EC State' button.
        </div>
        """
        htmlTab6 = f"""
        <div style="text-align:left">
          <h3>Layers to consider for the assessment of the Ecosystem functional state</h3>
          From the left window below, select the raster layers you want to use for the assessment of the functional state of the study area. You must select at least one layer. Click on the 'Add' button to add them to the right panel. On this panel, provide a short name for the variable, and indicate if the layers need to be inverted for the process. Once this is done, click on the 'Check alignment for selected layers' button'. If all selected layers are aligned, you can proceed by click on the 'Next EC State' button.
        </div>
        """
        htmlTab7 = f"""
        <div style="text-align:left">
          <h3>Layers to consider for the assessment of the Ecosystem landscape state</h3>
          From the left window below, select the raster layers you want to use for the assessment of the landscape state of the study area. You must select at least one layer. Click on the 'Add' button to add them to the right panel. On this panel, provide a short name for the variable, and indicate if the layers need to be inverted for the process. Once this is done, click on the 'Check alignment for selected layers' button'. If all selected layers are aligned, you can proceed by click on the 'Next EC State' button.
        </div>
        """
        htmlTab8 = f"""
        <div style="text-align:left">
          <h3>Weight attribution</h3>
          In the table below set weights for each variable (0.1 to 0.9), per landscape state (the sum of weights per ecosystem state must be 1). Set also the weight for each landscape state, to calculate the overal and final Ecosystem condition.
        </div>
        """
        htmlTab9 = f"""
        <div style="text-align:left">
          <h3>Results</h3><br>
          The map below shows the results for the global Ecosystem condition.
        </div>
        """
        ## store HTML text blocks for TABs 2 to 11 on variable 'htmlTabTexts': 
        self.htmlTabTexts = {
            1: htmlTab1,
            2: htmlTab2,
            3: htmlTab3,
            4: htmlTab4,
            5: htmlTab5,
            6: htmlTab6,
            7: htmlTab7,
            8: htmlTab8,
            9: htmlTab9
        }

        # keep a running list of all accepted layers
        # each entry is just:
        # { 'layer': QgsRasterLayer, 'ec_state': str, 'short': str }
        self.selected_layers = []
        # coloured buttons (to implement):
        self.default_btn_style   = ""  
        self.highlight_style     = "background-color: orange;" #FF8A24; # blue: #B0E0E6

    def run(self):
        # — reset any per‐run state —
        self.selected_layers      = []
        self._user_overrides      = {}
        self._result_state_layers = {}
        self._result_final        = None

        # load the UI into a QDialog parented to the QGIS main window
        self.dlg = uic.loadUi(self.ui_path, QDialog(self.iface.mainWindow()))
        self.dlg.setFixedSize(1424, 650)

        # FIRST set up all your static content (incl. htmlTabTexts)
        self.setup_main_tab()

        # THEN wire tab‐change → ec_tabs, and kick it off once
        self.dlg.tabWidget.currentChanged.connect(self.setup_ec_tabs)
        self.setup_ec_tabs()

        tabw = self.dlg.tabWidget
        #tabw.currentChanged.connect(self.on_tab_changed)
        # only keep tab 0 (Intro) and tab 1 (Main Options) enabled
        for i in range(tabw.count()):
            tabw.setTabEnabled(i, i <= 1)
        self.dlg.btnNext1.clicked.connect(self.validate_main_options)
        
        # Set all ec-tabs() buttons here:
        # *** Wire up your buttons
        for idx in range(2,8):
            getattr(self.dlg, f'btnMulticollinearWarning{idx}').clicked.connect(self.check_alignment)
            getattr(self.dlg, f'btnNext{idx}').         clicked.connect(self.next_ec_tab)
            getattr(self.dlg, f'btnAdd{idx}').          clicked.connect(
                lambda _, i=idx: self.ec_add_layer(
                    getattr(self.dlg, f'treeAvailable{i}'),
                    getattr(self.dlg, f'treeSelected{i}'),
                    i
                )
            )
            getattr(self.dlg, f'btnRemove{idx}').clicked.connect(
                lambda _, i=idx: self.ec_remove_layer(
                    getattr(self.dlg, f'treeSelected{i}'),
                    i
                )
            )
        # Now that all the “static” tabs are ready, show the dialog:
        self.dlg.exec_()

    # *********************************************************************
    # --------------------------
    # **** TAB 1
    # --------------------------
    def setup_main_tab(self):
        # ----------------------
        # Tab 1: Base settings
        # ----------------------
        # use HTML in QTextBrowser
        self.dlg.labelIntroTab1.setHtml(self.htmlTabTexts[1])
        # QTextBrowser handles rich text automatically, no setTextFormat needed
        # make intro background transparent to match form
        self.dlg.labelIntroTab1.setStyleSheet("background-color: transparent;")

        # Tab 1 'Next' button
        # Browse folder
        self.dlg.btnBrowseFolder.clicked.connect(self.browse_output_folder)

    def validate_main_options(self):
        # ensure output folder is set
        if not self.dlg.lineFolder.text():
            QMessageBox.warning(
                self.iface.mainWindow(),
                'Missing data',
                'Please select an output folder before proceeding.'
            )
            return
        # enable and jump to Tab 2
        self.dlg.tabWidget.setTabEnabled(1, True)
        self.dlg.tabWidget.setCurrentIndex(1)
        
    def browse_output_folder(self):
        folder = QFileDialog.getExistingDirectory(self.dlg, 'Select Output Folder')
        if folder:
            self.dlg.lineFolder.setText(folder)
            # hand focus immediately to the Next button:
            self.dlg.btnNext1.setFocus()

    # --------------------------
    # **** TABs 2 to 7
    # --------------------------
    def setup_ec_tabs(self):
        # 0) compute the set of already‐selected layer IDs
        used_ids = {
            entry['layer'].id()
            for entry in getattr(self, 'selected_layers', [])
        }

        for idx in range(2, 8):
            treeAvail = getattr(self.dlg, f'treeAvailable{idx}')
            tableSel  = getattr(self.dlg, f'treeSelected{idx}')
            btnAdd    = getattr(self.dlg, f'btnAdd{idx}')
            btnRem    = getattr(self.dlg, f'btnRemove{idx}')
            btnCheck  = getattr(self.dlg, f'btnMulticollinearWarning{idx}')
            btnNext   = getattr(self.dlg, f'btnNext{idx}')

            btnNext.setEnabled(False)
            # … grab the other widgets, wire up buttons etc …

            # 1) fill the intro QTextBrowser for this tab —
            intro = getattr(self.dlg, f'labelIntroTab{idx}')
            intro.setHtml(self.htmlTabTexts[idx])
            intro.setStyleSheet("background-color: transparent;")

            # 2) Clear out any old items
            treeAvail.clear()
            tableSel.clearContents()
            tableSel.setRowCount(0)

            # 3) Recursive function to add groups & layers
            def addGroupItems(group, parentItem):
                for child in group.children():
                    if isinstance(child, QgsLayerTreeGroup):
                        grpItem = QTreeWidgetItem([child.name()])
                        font = grpItem.font(0);  font.setUnderline(True)
                        grpItem.setFont(0, font)
                        parentItem.addChild(grpItem)
                        addGroupItems(child, grpItem)
                    elif isinstance(child, QgsLayerTreeLayer):
                        lyr = QgsProject.instance().mapLayer(child.layerId())
                        if isinstance(lyr, QgsRasterLayer):
                            item = QTreeWidgetItem([lyr.name()])
                            item.setData(0, Qt.UserRole, lyr.id())
                            parentItem.addChild(item)

            # 4) Walk the root of the layer tree
            root = QgsProject.instance().layerTreeRoot()
            for top in root.children():
                if isinstance(top, QgsLayerTreeGroup):
                    topItem = QTreeWidgetItem([top.name()])
                    font = topItem.font(0);  font.setUnderline(True)
                    topItem.setFont(0, font)
                    treeAvail.addTopLevelItem(topItem)
                    addGroupItems(top, topItem)
                elif isinstance(top, QgsLayerTreeLayer):
                    lyr = QgsProject.instance().mapLayer(top.layerId())
                    if isinstance(lyr, QgsRasterLayer):
                        itm = QTreeWidgetItem([lyr.name()])
                        itm.setData(0, Qt.UserRole, lyr.id())
                        treeAvail.addTopLevelItem(itm)

            # 5) Allow multi-select
            treeAvail.setSelectionMode(QAbstractItemView.ExtendedSelection)

            # 6) Expand all so user sees the full hierarchy
            treeAvail.expandAll()

            # 7) prepare the QTableWidget for added rows
            tableSel.setColumnCount(2)
            tableSel.setHorizontalHeaderLabels(['Layer', 'Short Name (15 charac. max.)'])
            tableSel.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)

    # Helper: add selected items into table
    def ec_add_layer(self, treeAvail, tableSel, idx):
        # Only add real layer‐items (those with a userRole ID), not group headers.
        for item in treeAvail.selectedItems():
            layer_id = item.data(0, Qt.UserRole)
            if not layer_id:
                continue

            layer = QgsProject.instance().mapLayer(layer_id)
            # skip if not a raster
            if not isinstance(layer, QgsRasterLayer):
                continue

            # skip if already in this state’s table
            existing = [ tableSel.item(r, 0).text()
                         for r in range(tableSel.rowCount()) ]
            if layer.name() in existing:
                continue

            # add to the QTableWidget
            row = tableSel.rowCount()
            tableSel.insertRow(row)

            # strip extension and truncate for the short name
            base, _ext = os.path.splitext(layer.name())
            short = base[:15]

            tableSel.setItem(row, 0, QTableWidgetItem(layer.name()))
            tableSel.setItem(row, 1, QTableWidgetItem(short))

            # **also** record it in your central list for later tabs:
            self.selected_layers.append({
                'layer': layer,
                'ec_state': TAB_STATE[idx],
                'short': short
            })
        # enable and highlight the “Check layers alignment” button
        check_btn = getattr(self.dlg, f'btnMulticollinearWarning{idx}')
        check_btn.setEnabled(True)                # in case it was disabled
        check_btn.setFocus()                      # give it keyboard focus
        check_btn.setStyleSheet(self.highlight_style)  # turn it orange

    def ec_remove_layer(self, tableSel, idx):
        # Remove all selected rows from the per‐tab table AND remove
        # their entries from self.selected_layers.
        # 1) Gather the names to remove
        removed = set()
        for idx in range(tableSel.rowCount()):
            # if row idx is selected anywhere, mark it
            if any(model_index.row() == idx for model_index in tableSel.selectedIndexes()):
                name = tableSel.item(idx, 0).text()
                removed.add(name)
    
        # 2) Actually delete rows (in reverse)
        for r in sorted(removed, reverse=True):
            # Find the row number
            for row in range(tableSel.rowCount()):
                if tableSel.item(row, 0).text() in removed:
                    tableSel.removeRow(row)
    
        # 3) Prune from self.selected_layers
        self.selected_layers = [
            e for e in self.selected_layers
            if e['layer'].name() not in removed
        ]

    def loadAvailableLayers(self, treeAvailableLayers, cboMaskLayer):
        treeAvailableLayers.clear()
        root = QgsProject.instance().layerTreeRoot()
        mask_id = cboMaskLayer.currentData()
        # … build the tree exactly as in your Group/Layer code …
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

    def addLayers(self, treeAvailableLayers, treeSelectedLayers):
        existing = {
          treeSelectedLayers.topLevelItem(i).data(0,1)
          for i in range(treeSelectedLayers.topLevelItemCount())
        }
        for item in treeAvailableLayers.selectedItems():
            lid = item.data(0,1)
            if lid and lid not in existing:
                layer = QgsProject.instance().mapLayer(lid)
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
    
    def removeLayers(self, treeSelectedLayers):
        # 1) Remove all selected items
        for item in treeSelectedLayers.selectedItems():
            idx = treeSelectedLayers.indexOfTopLevelItem(item)
            treeSelectedLayers.takeTopLevelItem(idx)
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

    ## Verify selected layers for alignment
    def check_alignment(self):
        tabw = self.dlg.tabWidget
        current = tabw.currentIndex()
        # nothing to check on the first two tabs
        if current < 1:
            return
    
        # suffix is how your buttons are named: btnNext2 lives on tab index 1, etc.
        suffix = current + 1
        btnNext = getattr(self.dlg, f'btnNext{suffix}')
    
        # decide which EC‐states are “so far”:
        # EC_STATES[0] is for tab index 1,
        # EC_STATES[1] is for tab index 2, etc.
        allowed_states = EC_STATES[: current ] # current-1 ]
    
        # pull in your running list
        layers = [ e['layer'] for e in self.selected_layers
                   if e['ec_state'] in allowed_states ]
    
        # 1) need two to compare
        if len(layers) < 2:
            QMessageBox.warning(
                self.iface.mainWindow(),
                "Not enough layers",
                "Please add at least two layers to verify alignment."
            )
            btnNext.setEnabled(False)
            return
    
        # 2) test against the first
        bad = []
        ref = layers[0]
        for lyr in layers[1:]:
            if not self.layersAligned(ref, lyr):
                bad.append(lyr.name())
    
        if bad:
            QMessageBox.critical(
                self.iface.mainWindow(),
                "Alignment Error",
                "The following are misaligned:\n\n" + "\n".join(bad)
            )
            btnNext.setEnabled(False)
            return
    
        # 3) success → enable the very next tab & the Next button
        QMessageBox.information(
            self.iface.mainWindow(),
            "Alignment OK",
            f"All {len(layers)} layers up through “{allowed_states[-1]}” are aligned."
        )

        # remove highlight from the 'check' button... ("suffix" is the corresponding number)
        check_btn = getattr(self.dlg, f'btnMulticollinearWarning{suffix}')
        check_btn.setStyleSheet("")

        # ... and add highlight and pass focus to the 'next' button. 
        nxt_tab = current + 1
        if nxt_tab < tabw.count():
            tabw.setTabEnabled(nxt_tab, True)
        btnNext.setEnabled(True)
        btnNext.setStyleSheet(self.highlight_style)
        # hand focus immediately to the Next button:
        btnNext.setFocus()
        
        

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

    def next_ec_tab(self):
        tabw    = self.dlg.tabWidget
        current = tabw.currentIndex()

        # map tab index → the corresponding table widget suffix
        suffix = current + 1
        table_widget = getattr(self.dlg, f'treeSelected{suffix}', None)

        if not table_widget or table_widget.rowCount() == 0:
            QMessageBox.warning(
                self.iface.mainWindow(),
                'No layers',
                'Please add at least one layer before proceeding.'
            )
            return

        # enable & jump to the next QTab
        nxt = current + 1
        if nxt < tabw.count():
            tabw.setTabEnabled(nxt, True)
            tabw.setCurrentIndex(nxt)

        if nxt == 7:  # just unlocked “Weights section” next
            self.setup_weights_tab()

    # --------------------------
    # **** TAB 8: Weights
    # --------------------------
    def setup_weights_tab(self):
        tree = self.dlg.treeWeights

        # 1) Clear out any old content
        tree.clear()

        # 2) DEFINITELY tell the tree it has 2 columns *before* adding items
        tree.setColumnCount(2)
        tree.setHeaderLabels(['Variable', 'Weight'])
        tree.header().setSectionResizeMode(0, QHeaderView.Stretch)
        tree.header().setSectionResizeMode(1, QHeaderView.ResizeToContents)

        # 3) Intro HTML
        html = """
        <div style="text-align:left">
          <h3>Weight attribution</h3>
          In the table below set weights for each variable (0.05 to 0.95), per 
          landscape state (the sum of weights per ecosystem state must be 1). 
          Set also the weight for each landscape state, to calculate the overall 
          and final Ecosystem condition.
        </div>
        """
        self.dlg.labelIntroTab8.setHtml(html)
        self.dlg.labelIntroTab8.setStyleSheet("background-color: transparent;")

        # 4) Build the hierarchical items
        groups = defaultdict(list)
        for e in self.selected_layers:
            groups[e['ec_state']].append(e)

        default_state_w = 1.0 / (len(groups) or 1)

        for state, entries in groups.items():
            parent = QTreeWidgetItem([state, f"{default_state_w:.3f}"])
            font = parent.font(0)
            font.setBold(True)
            parent.setFont(0, font)
            parent.setFirstColumnSpanned(True)
            tree.addTopLevelItem(parent)

            default_layer_w = 1.0 / len(entries)
            for ent in entries:
                child = QTreeWidgetItem([ent['short'], ""])
                parent.addChild(child)

                sb = QDoubleSpinBox()
                sb.setRange(0.05, 0.95)
                sb.setSingleStep(0.01)
                sb.setValue(default_layer_w)
                sb.valueChanged.connect(
                    lambda val, sb=sb, item=child, parent=parent:
                        self._on_layer_weight_changed(val, sb, item, parent)
                )
                tree.setItemWidget(child, 1, sb)

        # 5) Expand and style
        tree.expandAll()
        for i in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(i)
            for col in range(tree.columnCount()):
                item.setBackground(col, QBrush(QColor(0, 0, 0)))
                item.setForeground(col, QBrush(QColor(255, 255, 255)))

        # 6) Enable the “Calculate” button
        self.dlg.btnCalculate.setEnabled(True)
        self.dlg.btnCalculate.clicked.connect(self.calculate_weighted_sums)

    # The weights rebalance logic
    def _on_layer_weight_changed(self, val, sb, item, parent_item):
        # val         = new value from the spinbox
        # sb          = the QDoubleSpinBox that emitted the change
        # item        = the QTreeWidgetItem for this layer
        # parent_item = the QTreeWidgetItem for the EC‐state header
        
        tree = self.dlg.treeWeights

        # 1) mark this spinbox as explicitly overridden
        self._user_overrides[id(sb)] = val

        # 2) walk all children under this parent to
        #    compute total of overridden vs. list of non-overridden
        total_override = 0.0
        unovr = []
        for i in range(parent_item.childCount()):
            child = parent_item.child(i)
            spin = tree.itemWidget(child, 1)
            if not isinstance(spin, QDoubleSpinBox):
                continue
            v = spin.value()
            if id(spin) in self._user_overrides:
                total_override += v
            else:
                unovr.append(spin)

        # 3) if user total > 1.0, clamp *this* spinbox down so sum == 1
        if total_override > 1.0:
            # sum of *other* overrides (excluding this sb)
            prev_sum = sum(
                w for k,w in self._user_overrides.items()
                if k != id(sb)
            )
            # allow this sb to be at most (1 - previous)
            clamped = max(0.0, 1.0 - prev_sum)
            sb.blockSignals(True)
            sb.setValue(clamped)
            sb.blockSignals(False)
            self._user_overrides[id(sb)] = clamped
            total_override = prev_sum + clamped

        # 4) distribute the remaining weight (1 - total_override)
        #    equally among non-overridden spinboxes
        remainder = max(0.0, 1.0 - total_override)
        if unovr:
            share = remainder / len(unovr)
            for spin in unovr:
                spin.blockSignals(True)
                spin.setValue(share)
                spin.blockSignals(False)

    # Calculate the weighted sums
    def calculate_weighted_sums(self):
        out_folder = self.dlg.lineFolder.text()
        final_path = os.path.join(out_folder, 'EcoCondition.tif')

        # 1) group by state
        from collections import defaultdict
        groups = defaultdict(list)
        weights = {}
        tree = self.dlg.treeWeights
        for state in EC_STATES:
            # find the header item for this state
            items = tree.findItems(state, Qt.MatchExactly)
            if not items:
                continue
            parent = items[0]
            state_w = float(parent.text(1))
            weights[state] = state_w
            # collect its child layers
            for i in range(parent.childCount()):
                child = parent.child(i)
                short = child.text(0).strip()
                sb    = tree.itemWidget(child, 1)
                w     = sb.value()
                # find the matching layer object
                e = next(e for e in self.selected_layers if e['short'] == short)
                groups[state].append((e['layer'], w))

        # Helper: the six possible letters
        letters = ['A','B','C','D','E','F']

        # Set a layer group destination for the output files
        project = QgsProject.instance()
        root = project.layerTreeRoot()
        
        # find or create your output group
        project = QgsProject.instance()
        root    = project.layerTreeRoot()
        group_name = "EcoCond Outputs"
        grp = root.findGroup(group_name)
        if not grp:
            grp = root.addGroup(group_name)

        # 2) each state → its own weighted sum
        state_paths = {}
        for idx, state in enumerate(EC_STATES, start=1):
            layers = groups.get(state, [])
            if not layers:
                continue

            # build the formula like "0.3*A + 0.7*B"
            expr = " + ".join(f"{w}*{letters[j]}"
                              for j, (_lyr, w) in enumerate(layers))

            params = {
                "FORMULA": expr,
                "NO_DATA": -9999,
                "RTYPE": 5,
                "OUTPUT": os.path.join(out_folder, f"{idx:02d}_{state}.tif")
            }
            # now fill the INPUT_A.. slots properly
            for j, (lyr, _) in enumerate(layers):
                letter = letters[j]
                params[f"INPUT_{letter}"] = lyr.source()
                params[f"BAND_{letter}"]  = 1

            res = processing.run("gdal:rastercalculator", params)
            state_paths[state] = res["OUTPUT"] # record the path for later steps 
            
            # Add to the defined layer group
            state_lyr = QgsRasterLayer(res["OUTPUT"], f"{idx:02d}_{state}")
            
            QgsProject.instance().addMapLayer(state_lyr, addToLegend=False)
            grp.addLayer(state_lyr)

        # 3) final Ecosystem Condition = weighted sum of those six rasters
        ordered = [s for s in EC_STATES if s in state_paths]
        expr2 = " + ".join(f"{weights[s]}*{letters[i]}"
                           for i, s in enumerate(ordered))

        params2 = {
            "FORMULA": expr2,
            "NO_DATA": -9999,
            "RTYPE": 5,
            "OUTPUT": final_path
        }
        for i, s in enumerate(ordered):
            letter = letters[i]
            params2[f"INPUT_{letter}"] = state_paths[s]
            params2[f"BAND_{letter}"]  = 1

        # single, correct call
        processing.run("gdal:rastercalculator", params2)

        # 4) add to QGIS as a styled layer
        final_lyr = QgsRasterLayer(final_path, "EcoCondition")
        final_path = final_lyr.source()
        QgsProject.instance().addMapLayer(final_lyr, addToLegend=False)
        grp.addLayer(final_lyr)

        # 5) set up gray renderer
        provider = final_lyr.dataProvider()
        
        # instantiate the gray renderer (provider + band only)
        renderer = QgsSingleBandGrayRenderer(provider, 1)
        
        # 6) compute real min/max
        # read stats on band #1, All flags, over the full extent at our chosen resolution
        stats = provider.bandStatistics(
            1,
            QgsRasterBandStats.All
        )

        min_val = stats.minimumValue
        max_val = stats.maximumValue

        # 7) build a contrast enhancer with those ends
        ce = QgsContrastEnhancement(provider.dataType(1))
        ce.setMinimumValue(min_val)
        ce.setMaximumValue(max_val)
        ce.setContrastEnhancementAlgorithm(
            QgsContrastEnhancement.StretchToMinimumMaximum
        )
        
        # 8) attach the CE to the renderer
        renderer.setContrastEnhancement(ce)
        
        # 9) assign the fully‐configured renderer back to the layer
        final_lyr.setRenderer(renderer)
        
        # 10) force a repaint
        final_lyr.triggerRepaint()

        # 5) Build a color-ramp shader with five classes
        #crs = QgsColorRampShader()
        #crs.setColorRampType(QgsColorRampShader.Interpolated)
        #crs.setColorRampItemList([
        #    QgsColorRampShader.ColorRampItem(0.0,       QColor('red'),        '0–0.2'),
        #    QgsColorRampShader.ColorRampItem(0.2,       QColor('orange'),     '0.2–0.4'),
        #    QgsColorRampShader.ColorRampItem(0.4,       QColor('yellow'),     '0.4–0.6'),
        #    QgsColorRampShader.ColorRampItem(0.6,       QColor('lightgreen'), '0.6–0.8'),
        #    QgsColorRampShader.ColorRampItem(0.8,       QColor('green'),      '0.8–1.0'),
        #])
        #crs.classifyColorRamp(5)  # ← build exactly 5 discrete steps

        # 6) Wrap it in a QgsRasterShader
        #rshader = QgsRasterShader()
        #rshader.setRasterShaderFunction(crs)

        # 7) Create renderer
        #renderer = QgsSingleBandPseudoColorRenderer(final_lyr.dataProvider(), 1, rshader)
        #if not final_lyr.isValid():
        #    self.iface.messageBar().pushCritical(
        #        "EcoCond", "❌ Couldn’t load final raster, cannot style it."
        #    )
        #    return
        
        #final_lyr.setRenderer(renderer)
        
        # 8) now call the stretch‐to‐min/max on the layer itself:
        #from qgis.core import QgsContrastEnhancement
        #final_lyr.setContrastEnhancement(
        #    QgsContrastEnhancement.StretchToMinimumMaximum
        #)

        #final_lyr.setRenderer(renderer)

        # save for the results tab 11
        self._result_state_layers  = state_paths
        self._result_final         = final_path

        # move to the results tab 11
        tabw = self.dlg.tabWidget
        tabw.setTabEnabled(8, True)
        tabw.setCurrentIndex(8)

        self.setup_result_tab()

        # enable & switch to the Results tab
        tabw = self.dlg.tabWidget
        last_idx = tabw.count() - 1
        tabw.setTabEnabled(last_idx, True)
        tabw.setCurrentIndex(last_idx)

    # --------------------------
    # **** TAB 9
    # --------------------------
    # Set function to clear layout properly
    def clear_layout(self, layout):
        """Recursively remove and delete all items from a QLayout."""
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                w = item.widget()
                w.setParent(None)
                w.deleteLater()
            elif item.layout():
                self.clear_layout(item.layout())
                layout.removeItem(item)

    # Set up the results tab
    def setup_result_tab(self):
        # — 1) Intro HTML —
        html = """
        <div style="text-align:left">
          <h3>Results</h3>
        </div>
        """
        self.dlg.labelIntroTab9.setHtml(html)
        self.dlg.labelIntroTab9.setStyleSheet("background-color: transparent;")

        # — 2) Grab container & its layout, then clear it —
        container = self.dlg.mapPreview
        layout = container.layout()
        self.clear_layout(layout)

        # - 3) get the styled “EcoCondition” layer you pushed into the project
        final_lyr = QgsProject.instance().mapLayersByName('EcoCondition')[0]
        # For file-based rasters, use source() to get the file path
        final_path = final_lyr.source()

        # — 4) Legend and legend placeholder —
        # *** - Build the gradient + labels as a VBoxLayout
        width, height = 300, 20
        pix = QPixmap(width, height)
        painter = QPainter(pix)
        grad = QLinearGradient(0, 0, width, 0)
        grad.setColorAt(0.0, Qt.white)
        grad.setColorAt(1.0, Qt.black)
        painter.fillRect(0, 0, width, height, grad)
        painter.end()

        # *** — put it in a label —
        grad_label = QLabel()
        grad_label.setPixmap(pix)

        # *** — create the min/max labels —
        min_label = QLabel("0")
        max_label = QLabel("1")
        min_label.setAlignment(Qt.AlignLeft)
        max_label.setAlignment(Qt.AlignRight)

        # *** — pack them all into a little vertical widget (parented to legend_widget) —
        legend_widget = QWidget(container)
        legend_widget.setFixedHeight(50)
        legend_widget.setStyleSheet("background-color: transparent;")
        top_layout = QVBoxLayout(legend_widget)
        top_layout.setContentsMargins(0, 0, 0, 0)
        top_layout.addWidget(grad_label)

        lm = QHBoxLayout()
        lm.addWidget(min_label)
        lm.addStretch()
        lm.addWidget(max_label)

        # *** - wrap the label-row in a fixed-width widget
        lm_widget = QWidget()
        lm_widget.setLayout(lm)
        lm_widget.setFixedWidth(width)      # exactly the gradient’s width

        # - 5) Build area‐by‐class table -
        # *** - 1. read the raster into a numpy array via GDAL
        ds  = gdal.Open(final_path)
        arr = ds.GetRasterBand(1).ReadAsArray()
    
        # *** - 2. compute pixel area in km²
        pix_w = abs(final_lyr.rasterUnitsPerPixelX())
        pix_h = abs(final_lyr.rasterUnitsPerPixelY())
        km2_per_pixel = (pix_w * pix_h) / 1e6

        # *** - 3. define the five 0.2-wide bins and tally areas
        bins    = [i*0.2 for i in range(6)]  # [0.0, 0.2, …, 1.0]
        classes = [(bins[i], bins[i+1]) for i in range(5)]
        areas   = []
        for lo, hi in classes:
            mask  = (arr >= lo) & (arr < hi)
            count = np.count_nonzero(mask)
            areas.append(count * km2_per_pixel)

        # *** - 4. build the table widget
        tbl = QTableWidget(len(classes), 2, legend_widget)
        tbl.setHorizontalHeaderLabels(["Range", "Area (km²)"])
        tbl.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        tbl.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        tbl.setSizePolicy(tbl.sizePolicy().horizontalPolicy(),
                          tbl.sizePolicy().verticalPolicy())

        for i, (lo, hi) in enumerate(classes):
            rng = f"{lo:.1f}–{hi:.1f}"
            tbl.setItem(i, 0, QTableWidgetItem(rng))
            tbl.setItem(i, 1, QTableWidgetItem(f"{areas[i]:.2f}"))

        # *** - 5. remove everything you added so far from legend_widget…
        old_items = []
        while top_layout.count():
            old_items.append(top_layout.takeAt(0))

        # *** - 6. now rebuild: gradient + space + table
        h = QHBoxLayout()
        h.addWidget(grad_label)               # your gradient pixmap
        h.addStretch(1)
        h.addWidget(tbl)                      # the new areas table
        # put HBox back into the legend widget
        top_layout.addLayout(h)
        # then re-add the min/max row you built earlier:
        top_layout.addWidget(lm_widget)

        # *** — 7. finally insert this single legend_widget into the container’s layout
        layout.insertWidget(0, legend_widget)

        # — 6) Build the H-split: left big map, right grid of thumbs —
        hsplit = QHBoxLayout()

        # *** — Left side: wrap the canvas + its title in a QWidget/VBoxLayout —
        left_widget = QWidget(container)
        left_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 10, 0, 0) # left, top, right, bottom 
        left_layout.setSpacing(0) # original: 5

        # *** - Title above the big map:
        title = QLabel("Final Ecosystem Condition")
        title.setAlignment(Qt.AlignCenter)
        left_layout.addWidget(title)
        
        # *** - The canvas itself:
        eco_canvas = QgsMapCanvas(container)
        eco_canvas.setCanvasColor(Qt.white)
        eco_canvas.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        # - set layers, extent, and refresh…
        
        # --- add base OSM-based map as an in-memory XYZ layer (no project insertion) ---

        # *** ALTERNATIVE 1 - OSM data in colours: 
        
        # *** - 1. Set url and layer name
        url = "http://tile.openstreetmap.org/{z}/{x}/{y}.png"
        layer_name = "OSM base map"
        # *** - 2. Instantiate it as a raster layer of type "xyz"
        url_with_params = f"type=xyz&url={url}&zmin=0&zmax=20"
        

        # *** ALTERNATIVE 2 - Use Stamen Toner-Lite (grayscale) instead of OSM
        """
        # *** - 1. Set url and layer name
        url = "https://tile.stamen.com/toner-lite/{z}/{x}/{y}.png"
        layer_name = "Stamen Toner-Lite (grayscale)"
        # *** - 2. Instantiate it as a raster layer of type "xyz"
        url_with_params = f"type=xyz&url={url}&zmin=0&zmax=20"
        """

        # *** ALTERNATIVE 3 - Use Wikimedia's B&W OSM map (no labels)
        """
        url = "https://maps.wikimedia.org/osm/{z}/{x}/{y}.png"
        layer_name = "Wikimedia's B&W OSM map"
        # *** - 2. Instantiate it as a raster layer of type "xyz"
        url_with_params = f"type=xyz&url={url}&zmin=0&zmax=20"
        """

        # *** ALTERNATIVE 4 - Use Wikimedia's B&W OSM map (with labels)
        """
        # *** - 1. Set url and layer name
        url = "https://maps.wikimedia.org/osm-intl/{z}/{x}/{y}.png?lang=en"
        layer_name = "Wikimedia's B&W OSM map (with names)"
        # *** - 2. Instantiate it as a raster layer of type "xyz"
        url_with_params = f"type=xyz&url={url}&zmin=0&zmax=20"
        """

        # *** - Add the selected OSM-based map
        osm_layer = QgsRasterLayer(
            url_with_params,
            layer_name,
            "xyz"
        )
        if not osm_layer.isValid():
            QgsMessageLog.logMessage("Failed to load XYZ layer", "EcoCondPlugin", level=Qgis.Warning)
            layers = [final_lyr]
        else:
            # never add to the main legend:
            # QgsProject.instance().addMapLayer(osm_layer, addToLegend=False)
        
            # set the transparency
            osm_layer.setOpacity(0.5)
        
            # send it straight into your RESULTS map canvas
            layers = [osm_layer, final_lyr]

        # push into the canvas only
        eco_canvas.setLayers(layers)
        # zoom to the eco layer’s true extent
        eco_canvas.setExtent(final_lyr.extent())
        # force draw
        eco_canvas.refresh()

        # Pseudo‐grayscale with a color filter
        effect = QGraphicsColorizeEffect()
        effect.setColor(Qt.lightGray)
        effect.setStrength(0.75)             # how strong the gray tint is - 0. no effect, 1. full gray
        eco_canvas.viewport().setGraphicsEffect(effect)

        # now add the canvas *into* the left‐widget layout
        left_layout.addWidget(eco_canvas)

        # finally add the left‐widget (with title+canvas) to the H-split
        hsplit.addWidget(left_widget, 2)


        # — Right side: wrap grid in its own QWidget —
        grid_widget = QWidget(container)
        grid_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        
        grid = QGridLayout(grid_widget)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(5) # 10
        grid.setVerticalSpacing(5) # 10
        
        for i, (state, path) in enumerate(self._result_state_layers.items()):
            row = (i // 3) * 2
            col = i % 3

            # Label above each mini‐map
            lbl = QLabel(state)
            grid.addWidget(lbl, row, col, alignment=Qt.AlignCenter)

            # The mini‐canvas
            mini = QgsMapCanvas(container)
            mini.setCanvasColor(Qt.white)
            mini.setLayers([QgsProject.instance().mapLayersByName(f"{i+1:02d}_{state}")[0]])
            mini.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            mini.zoomToFullExtent()
            mini.refresh()
            grid.addWidget(mini, row+1, col)

        # add to the split, stretch factor = 3
        hsplit.addWidget(grid_widget, 3)

        # 5) Tie it all together
        layout.addLayout(hsplit)

        # 6) hook up the finish button
        self.dlg.btnFinish.clicked.connect(self.dlg.close)
