from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QPushButton, QComboBox, QCheckBox,
    QHeaderView, QAbstractItemView, QMessageBox
)
from qgis.PyQt.QtCore import Qt
from qgis.core import (
    QgsProject, QgsPointXY, QgsGeometry, QgsVectorLayer,
    QgsFeature, QgsWkbTypes, QgsFeatureRequest,
    QgsCoordinateReferenceSystem, QgsCoordinateTransform
)
from qgis.gui import QgsRubberBand
import math


class QuickAzimuthPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.canvas = iface.mapCanvas()
        self.dock = None
        self.rubber_band = QgsRubberBand(self.canvas, QgsWkbTypes.PolygonGeometry)
        self.rubber_band.setColor(Qt.red)
        self.rubber_band.setWidth(2)
        self.rubber_band.setFillColor(Qt.transparent)  # Outline only
        self.points = []
        self.selected_layer = None

        # Remember the last selected feature's first vertex in the LAYER CRS,
        # so we can re-display it when the CRS dropdown changes.
        self._last_first_vertex_layer_crs = None
        self._last_layer_crs = None

    # ---------------- Plugin hooks ----------------
    def initGui(self):
        self.action_button = QPushButton("🧭 QuickAzimuth+")
        self.action_button.clicked.connect(self.open_dock)
        self.iface.addToolBarWidget(self.action_button)

    def unload(self):
        if self.dock:
            self.iface.removeDockWidget(self.dock)
            self.dock = None
        if self.action_button:
            self.action_button.deleteLater()
            self.action_button = None
        if self.selected_layer:
            try:
                self.selected_layer.selectionChanged.disconnect(self.on_selection_changed)
            except:
                pass

    # ---------------- UI ----------------
    def open_dock(self):
        if self.dock and self.dock.isVisible():
            self.dock.raise_()
            return
        elif self.dock:
            self.dock.show()
            return

        self.dock = QDockWidget("QuickAzimuth+", self.iface.mainWindow())
        self.widget = QWidget()
        layout = QVBoxLayout()

        # Coordinate input
        coord_layout = QHBoxLayout()
        self.x_input = QLineEdit()
        self.x_input.setPlaceholderText("X")
        self.y_input = QLineEdit()
        self.y_input.setPlaceholderText("Y")
        coord_layout.addWidget(QLabel("Start X:"))
        coord_layout.addWidget(self.x_input)
        coord_layout.addWidget(QLabel("Y:"))
        coord_layout.addWidget(self.y_input)
        layout.addLayout(coord_layout)

        # CRS controls (for both reverse-engineering display + preview transform)
        crs_layout = QHBoxLayout()
        self.crs_combo = QComboBox()
        self.crs_combo.addItems(["", "31N", "32N"])  # blank allowed
        self.crs_check = QCheckBox("CRS")
        self.crs_check.setChecked(True)
        self.crs_check.stateChanged.connect(self.handle_crs_checkbox)
        self.crs_combo.currentIndexChanged.connect(self.update_xy_for_dropdown)  # <- update X/Y when CRS selection changes
        crs_layout.addWidget(QLabel("CRS:"))
        crs_layout.addWidget(self.crs_combo)
        crs_layout.addWidget(self.crs_check)
        layout.addLayout(crs_layout)

        # Layer selector
        self.layer_combo = QComboBox()
        self.layer_combo.addItems([
            layer.name() for layer in QgsProject.instance().mapLayers().values()
            if isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.PolygonGeometry
        ])
        self.layer_combo.currentIndexChanged.connect(self.connect_selection_signal)
        layout.addWidget(QLabel("Target Layer:"))
        layout.addWidget(self.layer_combo)

        # Table for azimuth/distance
        self.table = QTableWidget(3, 3)
        self.table.setHorizontalHeaderLabels(["Azimuth °", "Azimuth '", "Distance"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

        # Row buttons
        row_button_layout = QHBoxLayout()
        add_row_btn = QPushButton("➕ Add Row")
        del_row_btn = QPushButton("➖ Delete Row")
        move_up_btn = QPushButton("⬆ Move Up")
        move_down_btn = QPushButton("⬇ Move Down")
        add_row_btn.clicked.connect(self.add_row)
        del_row_btn.clicked.connect(self.delete_row)
        move_up_btn.clicked.connect(self.move_row_up)
        move_down_btn.clicked.connect(self.move_row_down)
        row_button_layout.addWidget(add_row_btn)
        row_button_layout.addWidget(del_row_btn)
        row_button_layout.addWidget(move_up_btn)
        row_button_layout.addWidget(move_down_btn)
        layout.addLayout(row_button_layout)

        # Action buttons
        button_layout = QHBoxLayout()
        preview_btn = QPushButton("👁 Preview")
        commit_btn = QPushButton("✅ Commit")
        reset_btn = QPushButton("🔄 New")
        preview_btn.clicked.connect(self.preview)
        commit_btn.clicked.connect(self.commit)
        reset_btn.clicked.connect(self.reset)
        button_layout.addWidget(preview_btn)
        button_layout.addWidget(commit_btn)
        button_layout.addWidget(reset_btn)
        layout.addLayout(button_layout)

        self.widget.setLayout(layout)
        self.dock.setWidget(self.widget)
        self.iface.addDockWidget(Qt.LeftDockWidgetArea, self.dock)
        self.dock.closeEvent = self.on_dock_closed
        self.dock.show()

        self.connect_selection_signal()

    def handle_crs_checkbox(self, state):
        if state == Qt.Unchecked:
            reply = QMessageBox.question(
                self.widget,
                "Disable CRS Transformation?",
                "Unchecking will skip CRS transformation during Preview/Commit.\n"
                "Coordinates will be treated as EPSG:26332 (used as-is).\n\nContinue?",
                QMessageBox.Yes | QMessageBox.No
            )
            if reply == QMessageBox.No:
                self.crs_check.setChecked(True)
        # If user toggles checkbox, we do not need to change X/Y display here.

    # ---------------- Selection wiring ----------------
    def connect_selection_signal(self):
        name = self.layer_combo.currentText()
        self.selected_layer = next(
            (l for l in QgsProject.instance().mapLayers().values() if l.name() == name),
            None
        )
        if self.selected_layer:
            try:
                self.selected_layer.selectionChanged.disconnect(self.on_selection_changed)
            except:
                pass
            self.selected_layer.selectionChanged.connect(self.on_selection_changed)

    # ---------------- Reverse engineering (selection -> inputs) ----------------
    def on_selection_changed(self, selected, deselected, clearAndSelect):
        if not self.selected_layer or not selected:
            self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
            self._last_first_vertex_layer_crs = None
            self._last_layer_crs = None
            return

        feat = next(self.selected_layer.getFeatures(QgsFeatureRequest().setFilterFid(selected[0])), None)
        if not feat:
            return

        geom = feat.geometry()
        if not geom or geom.isEmpty():
            return

        if geom.isMultipart():
            multi = geom.asMultiPolygon()
            if not multi or not multi[0]:
                return
            ring = multi[0][0]
        else:
            polygon = geom.asPolygon()
            if not polygon or not polygon[0]:
                return
            ring = polygon[0]

        # Remember first vertex + layer CRS so we can re-display in chosen CRS
        first = ring[0]
        self._last_first_vertex_layer_crs = QgsPointXY(first)
        self._last_layer_crs = self.selected_layer.crs()

        # Display X/Y in CRS chosen in dropdown
        self.update_xy_for_dropdown()

        # Fill table (unchanged; uses geometry segments as-is)
        self.table.setRowCount(len(ring) - 1)
        for i in range(len(ring) - 1):
            pt1 = ring[i]
            pt2 = ring[i + 1]
            dx = pt2.x() - pt1.x()
            dy = pt2.y() - pt1.y()
            dist = math.hypot(dx, dy)
            angle_rad = math.atan2(dx, dy)
            angle_deg = math.degrees(angle_rad)
            if angle_deg < 0:
                angle_deg += 360
            deg = int(angle_deg)
            mins = round((angle_deg - deg) * 60, 2)
            self.table.setItem(i, 0, QTableWidgetItem(str(deg)))
            self.table.setItem(i, 1, QTableWidgetItem(str(mins)))
            self.table.setItem(i, 2, QTableWidgetItem(str(round(dist, 3))))

        self.preview()

    def update_xy_for_dropdown(self):
        """Show the remembered first vertex in the CRS chosen in the dropdown."""
        if self._last_first_vertex_layer_crs is None or self._last_layer_crs is None:
            return  # nothing selected yet

        target_text = self.crs_combo.currentText()
        pt = QgsPointXY(self._last_first_vertex_layer_crs)

        if target_text in ("31N", "32N"):
            target_crs = QgsCoordinateReferenceSystem("EPSG:26331" if target_text == "31N" else "EPSG:26332")
            if self._last_layer_crs != target_crs:
                try:
                    xform = QgsCoordinateTransform(self._last_layer_crs, target_crs, QgsProject.instance())
                    pt = xform.transform(pt)
                except Exception as e:
                    QMessageBox.warning(self.widget, "CRS Transform Error", str(e))
                    return
        # else: dropdown blank => show as layer CRS (no transform)

        self.x_input.setText(str(pt.x()))
        self.y_input.setText(str(pt.y()))

    # ---------------- Row helpers ----------------
    def add_row(self):
        self.table.insertRow(self.table.rowCount())

    def delete_row(self):
        selected = self.table.currentRow()
        if selected >= 0:
            self.table.removeRow(selected)

    def move_row_up(self):
        current = self.table.currentRow()
        if current > 0:
            self.swap_rows(current, current - 1)
            self.table.selectRow(current - 1)

    def move_row_down(self):
        current = self.table.currentRow()
        if current < self.table.rowCount() - 1:
            self.swap_rows(current, current + 1)
            self.table.selectRow(current + 1)

    def swap_rows(self, row1, row2):
        for col in range(self.table.columnCount()):
            item1 = self.table.item(row1, col)
            item2 = self.table.item(row2, col)
            text1 = item1.text() if item1 else ""
            text2 = item2.text() if item2 else ""
            self.table.setItem(row1, col, QTableWidgetItem(text2))
            self.table.setItem(row2, col, QTableWidgetItem(text1))

    # ---------------- Preview & commit ----------------
    @staticmethod
    def _utm31_32_bounds_ok(x, y):
        # UTM zone bounds (valid for both 31N and 32N):
        # Easting ∈ [166,021 ; 833,978], Northing ∈ [0 ; 9,339,005]
        return (166021 <= x <= 833978) and (0 <= y <= 9339005)

    def preview(self):
        # Parse coords
        try:
            x = float(self.x_input.text())
            y = float(self.y_input.text())
        except ValueError:
            return

        # Bounds check on the entered CRS (whichever user has in X/Y)
        if not self._utm31_32_bounds_ok(x, y):
            QMessageBox.warning(self.widget, "Invalid Coordinates",
                                "Coordinates are out of UTM 31N/32N bounds.\n"
                                "Easting must be 166,021–833,978; Northing 0–9,339,005.")
            return

        # Start point: either transform to 26332 (if CRS checked), or use as-is
        pt = QgsPointXY(x, y)
        if self.crs_check.isChecked():
            crs_text = self.crs_combo.currentText()
            if crs_text not in ("31N", "32N"):
                QMessageBox.warning(self.widget, "CRS Missing", "Select 31N or 32N (or uncheck CRS to skip).")
                return
            src_crs = QgsCoordinateReferenceSystem("EPSG:26331" if crs_text == "31N" else "EPSG:26332")
            tgt_crs = QgsCoordinateReferenceSystem("EPSG:26332")
            try:
                xform = QgsCoordinateTransform(src_crs, tgt_crs, QgsProject.instance())
                pt = xform.transform(pt)
            except Exception as e:
                QMessageBox.warning(self.widget, "CRS Transform Error", str(e))
                return
        # else unchecked: pt already assumed in 26332

        # Build polygon by azimuth/distance
        points = [pt]
        current = QgsPointXY(pt)
        for i in range(self.table.rowCount()):
            try:
                deg = float(self.table.item(i, 0).text())
                mins = float(self.table.item(i, 1).text())
                dist = float(self.table.item(i, 2).text())
            except Exception:
                continue
            angle = math.radians(deg + mins / 60.0)
            dx = dist * math.sin(angle)
            dy = dist * math.cos(angle)
            current = QgsPointXY(current.x() + dx, current.y() + dy)
            points.append(current)

        if len(points) < 2:
            return

        points.append(points[0])
        self.points = points
        geom = QgsGeometry.fromPolygonXY([points])
        self.rubber_band.setToGeometry(geom, None)

        # Zoom to preview polygon
        self.canvas.setExtent(geom.boundingBox())
        self.canvas.refresh()

    def commit(self):
        if not self.points:
            return
        name = self.layer_combo.currentText()
        layer = next((l for l in QgsProject.instance().mapLayers().values() if l.name() == name), None)
        if not layer:
            QMessageBox.warning(self.widget, "No Target Layer", "Please select a valid polygon layer.")
            return
        if not layer.isEditable():
            layer.startEditing()
        f = QgsFeature(layer.fields())
        f.setGeometry(QgsGeometry.fromPolygonXY([self.points]))
        layer.addFeature(f)
        self.iface.openFeatureForm(layer, f)
        layer.triggerRepaint()

    def reset(self):
        self.x_input.clear()
        self.y_input.clear()
        self.table.clearContents()
        self.table.setRowCount(3)
        self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
        self.points = []
        # keep dropdown/checkbox as user last set
        self._last_first_vertex_layer_crs = None
        self._last_layer_crs = None

    def on_dock_closed(self, event):
        # Fully close & destroy
        self.reset()
        self.iface.removeDockWidget(self.dock)
        self.dock = None
        event.accept()
