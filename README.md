# ArcGIS REST Attachments Viewer

A QGIS plugin to view ArcGIS REST FeatureServer attachments from selected features.

## Features

- Detects ArcGIS REST FeatureServer layer URLs.
- Reads one or multiple selected features.
- Queries ArcGIS REST attachments by OBJECTID.
- Opens an HTML gallery with photos and files.
- Supports public ArcGIS REST FeatureServer layers with attachments enabled.

## Usage

1. Load an ArcGIS REST FeatureServer layer in QGIS.
2. Select one or more features.
3. Click the attachment icon.
4. The plugin opens a gallery with the available attachments.

## Limitations

- The layer must expose attachments.
- The plugin currently uses OBJECTID to query attachments.
- Private services may require a valid ArcGIS session or token.
- The plugin does not store usernames, passwords or tokens.

## License

GNU General Public License v2.0 or later.
