# Changelog

## 1.0.0

- Initial experimental release.
- Detects ArcGIS REST FeatureServer layers.
- Reads selected features.
- Queries attachments by OBJECTID.
- Opens an HTML gallery.
- Supports one or multiple selected features.

## 1.0.1

- Restricted REST requests to validated HTTP(S) ArcGIS FeatureServer layer URLs.
- Added URL validation before opening attachment endpoints.
- Addressed Bandit security scan warning for URL opening.
