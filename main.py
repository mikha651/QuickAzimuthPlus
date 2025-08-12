from qgis.PyQt.QtWidgets import (
    QDockWidget, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit,
    QTableWidget, QTableWidgetItem, QPushButton, QComboBox,
    QHeaderView, QAbstractItemView
)
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtGui import QBrush
from qgis.core import (
    QgsProject, QgsPointXY, QgsGeometry, QgsVectorLayer,
    QgsFeature, QgsWkbTypes, QgsFeatureRequest
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
        self.rubber_band.setFillColor(Qt.transparent)  # ✅ Outline only
        self.points = []
        self.selected_layer = None

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

        self.layer_combo = QComboBox()
        self.layer_combo.addItems([
            layer.name() for layer in QgsProject.instance().mapLayers().values()
            if isinstance(layer, QgsVectorLayer) and layer.geometryType() == QgsWkbTypes.PolygonGeometry
        ])
        self.layer_combo.currentIndexChanged.connect(self.connect_selection_signal)
        layout.addWidget(QLabel("Target Layer:"))
        layout.addWidget(self.layer_combo)

        self.table = QTableWidget(3, 3)
        self.table.setHorizontalHeaderLabels(["Azimuth °", "Azimuth '", "Distance"])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        layout.addWidget(self.table)

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

    def connect_selection_signal(self):
        name = self.layer_combo.currentText()
        self.selected_layer = next((l for l in QgsProject.instance().mapLayers().values() if l.name() == name), None)
        if self.selected_layer:
            try:
                self.selected_layer.selectionChanged.disconnect(self.on_selection_changed)
            except:
                pass
            self.selected_layer.selectionChanged.connect(self.on_selection_changed)

    def on_selection_changed(self, selected, deselected, clearAndSelect):
        if not self.selected_layer or not selected:
            self.rubber_band.reset(QgsWkbTypes.PolygonGeometry)
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

        first = ring[0]
        self.x_input.setText(str(first.x()))
        self.y_input.setText(str(first.y()))

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

    def preview(self):
        try:
            x = float(self.x_input.text())
            y = float(self.y_input.text())
        except ValueError:
            return

        points = [QgsPointXY(x, y)]
        current = QgsPointXY(x, y)
        for i in range(self.table.rowCount()):
            try:
                deg = float(self.table.item(i, 0).text())
                mins = float(self.table.item(i, 1).text())
                dist = float(self.table.item(i, 2).text())
                angle = math.radians(deg + mins / 60)
                dx = dist * math.sin(angle)
                dy = dist * math.cos(angle)
                current = QgsPointXY(current.x() + dx, current.y() + dy)
                points.append(current)
            except:
                continue

        points.append(points[0])
        self.points = points
        self.rubber_band.setToGeometry(QgsGeometry.fromPolygonXY([points]), None)

        # Zoom to the preview polygon
        extent = QgsGeometry.fromPolygonXY([points]).boundingBox()
        self.canvas.setExtent(extent)
        self.canvas.refresh()

    def commit(self):
        if not self.points:
            return
        name = self.layer_combo.currentText()
        layer = next((l for l in QgsProject.instance().mapLayers().values() if l.name() == name), None)
        if not layer:
            return
        if not layer.isEditable():
            layer.startEditing()
        f = QgsFeature(layer.fields())
        geom = QgsGeometry.fromPolygonXY([self.points])
        f.setGeometry(geom)
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

    def on_dock_closed(self, event):
        event.ignore()  # ❌ Don't destroy it, just hide
        self.dock.hide()

