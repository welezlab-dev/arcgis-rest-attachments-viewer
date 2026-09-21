# Changelog

## 1.0.4

* Added compatibility with QGIS 4 and Qt 6.
* Retained compatibility with QGIS 3.22 and later versions.
* Updated Qt enum usage, `QAction` imports, event loop execution, and network error handling.
* Replaced silent exception handling flagged by the automated Bandit security scan.
* Updated the plugin icon with an opaque white attachment clip.

## 1.0.3

* Marked the plugin as stable by setting the experimental metadata flag to `False`.

## 1.0.2

* Replaced direct URL opening with the QGIS network access manager.
* Removed `urllib.request.urlopen` to comply with QGIS plugin security requirements.
* Retained REST URL validation for HTTP(S) ArcGIS FeatureServer endpoints.

## 1.0.1

* Restricted REST requests to validated HTTP(S) ArcGIS FeatureServer layer URLs.
* Added URL validation before opening attachment endpoints.
* Addressed the Bandit security warning related to URL opening.

## 1.0.0

* Initial experimental release.
* Added detection of ArcGIS REST FeatureServer layers.
* Added support for reading selected features.
* Added attachment queries using feature `OBJECTID` values.
* Added an HTML attachment gallery.
* Added support for one or multiple selected features.
