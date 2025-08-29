# Changelog

All notable changes to this project will be documented in this file.

## [1.0.0] - 2025-07-02

### 🎉 Initial Release

- Added support for creating polygons by entering azimuth and distance.
- Extracts azimuth and distance from selected polygons:
  - 🧭 Azimuth Degrees & Minutes
  - 📏 Segment Distance
- Interactive UI with modern emoji-based layout:
  - ➕ Add Row
  - ➖ Delete Row
  - 👁 Preview
  - ✅ Commit
  - 🔄 New
- Rubber band visualization of the polygon geometry.
- Zooms to the previewed polygon automatically.
- Auto-populates coordinate and segment table when selecting an existing polygon.
- Supports both single and multipolygon geometries.
- Clears visualization when deselecting features or resetting the form.

---

### 📌 Notes

- All generated geometries are stored in the target layer you select.
- Designed for QGIS 3.16 and above.

## [1.1.0] - 2025-08-12

### ✨ Enhancements
- Rubber band preview now shows only the outline (transparent fill).
- Plugin reuses a single panel (no duplicate docks).
- Added ⬆ and ⬇ buttons to reorder azimuth/distance table rows.

---

## [1.2.0] - 2025-08-29

### 🚀 New Features & Fixes
- Added CRS dropdown (31N / 32N) with checkbox:
  - ✔ If checked: entered coordinates are transformed to EPSG:26332.
  - ❌ If unchecked: coordinates are used as-is.
- Reverse-engineering enhanced:
  - Selected polygon’s first vertex is displayed in CRS chosen from dropdown.
  - Coordinates update automatically when changing CRS dropdown.
  - Azimuth/distance segments extracted as before.
- Added UTM bounds validation:
  - Easting: 166,021–833,978  
  - Northing: 0–9,339,005
- Dock now fully closes and resets when closed.
- Improved coordinate handling to avoid errors when switching between CRSs.

---

### 📌 Notes
- Commit always adds the new polygon to the selected target polygon layer.
- CRS handling ensures consistent use of Minna / UTM 31N & 32N zones.
