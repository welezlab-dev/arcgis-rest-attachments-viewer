# -*- coding: utf-8 -*-
"""
Visor Adjuntos ArcGIS REST
Versión simple para QGIS.

Uso:
1. Cargar una capa ArcGIS FeatureServer en QGIS.
2. Seleccionar una o varias entidades.
3. Ejecutar el botón del complemento.
4. El complemento abre una galería HTML con los adjuntos agrupados por OBJECTID.

Limitación:
- Funciona mejor con capas públicas o URLs REST que incluyan token.
- Para capas privadas con autenticación administrada por QGIS, el acceso directo por urllib puede requerir token.
"""

import html
import json
import os
import re
import tempfile
import traceback
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from qgis.PyQt.QtCore import QUrl
from qgis.PyQt.QtGui import QDesktopServices, QIcon
from qgis.PyQt.QtWidgets import QAction

from qgis.core import Qgis, QgsMessageLog, QgsVectorLayer


class ArcGisAttachmentsViewer:
    def __init__(self, iface):
        self.iface = iface
        self.plugin_dir = os.path.dirname(__file__)
        self.action = None

    def initGui(self):
        icon_path = os.path.join(self.plugin_dir, "icon.svg")
        icon = QIcon(icon_path)

        self.action = QAction(icon, "Ver adjuntos ArcGIS", self.iface.mainWindow())
        self.action.setObjectName("ArcGisAttachmentsViewerAction")
        self.action.setToolTip("Ver fotos/adjuntos de la capa ArcGIS REST seleccionada")
        self.action.triggered.connect(self.run)

        self.iface.addToolBarIcon(self.action)
        self.iface.addPluginToMenu("Adjuntos ArcGIS REST", self.action)

    def unload(self):
        if self.action:
            self.iface.removeToolBarIcon(self.action)
            self.iface.removePluginMenu("Adjuntos ArcGIS REST", self.action)
            self.action = None

    # -------------------------
    # Mensajes
    # -------------------------
    def info(self, message, duration=6):
        self.iface.messageBar().pushMessage(
            "Adjuntos ArcGIS REST",
            message,
            level=Qgis.Info,
            duration=duration,
        )

    def warning(self, message, duration=8):
        self.iface.messageBar().pushMessage(
            "Adjuntos ArcGIS REST",
            message,
            level=Qgis.Warning,
            duration=duration,
        )

    def critical(self, message, duration=10):
        self.iface.messageBar().pushMessage(
            "Adjuntos ArcGIS REST",
            message,
            level=Qgis.Critical,
            duration=duration,
        )

    def log_error(self, message):
        QgsMessageLog.logMessage(message, "Adjuntos ArcGIS REST", Qgis.Critical)

    # -------------------------
    # Acción principal
    # -------------------------
    def run(self):
        try:
            layer = self.iface.activeLayer()

            if layer is None:
                self.warning("No hay una capa activa.")
                return

            if not isinstance(layer, QgsVectorLayer):
                self.warning("La capa activa no es una capa vectorial.")
                return

            selected = layer.selectedFeatures()

            if not selected:
                self.warning("Selecciona una o varias entidades antes de ejecutar la herramienta.")
                return

            base_url, token = self.extract_arcgis_rest_url(layer.source())

            if not base_url:
                self.warning(
                    "No pude detectar una URL tipo FeatureServer/0, FeatureServer/1, etc. "
                    "Verifica que la capa activa venga de ArcGIS REST."
                )
                return

            objectid_field = self.find_objectid_field(layer)

            if not objectid_field:
                self.warning(
                    "No encontré un campo OBJECTID/objectid/OID/FID. "
                    "La consulta de adjuntos de ArcGIS REST necesita el OBJECTID."
                )
                return

            if len(selected) == 1:
                self.info("Consultando adjuntos de 1 entidad...")
            else:
                self.info(f"Consultando adjuntos de {len(selected)} entidades seleccionadas...")

            sections = []
            total_attachments = 0
            total_images = 0

            for index, feature in enumerate(selected, start=1):
                objectid = feature[objectid_field]

                if objectid is None or str(objectid).strip() == "":
                    sections.append(self.section_error(index, "SIN_OBJECTID", "La entidad no tiene OBJECTID."))
                    continue

                objectid_text = str(objectid).strip()

                try:
                    attachments = self.fetch_attachments(base_url, objectid_text, token)
                    total_attachments += len(attachments)

                    section_html, image_count = self.build_feature_section(
                        base_url=base_url,
                        objectid=objectid_text,
                        attachments=attachments,
                        token=token,
                        feature_index=index,
                    )
                    total_images += image_count
                    sections.append(section_html)

                except Exception as ex:
                    sections.append(self.section_error(index, objectid_text, str(ex)))

            output_html = self.build_gallery_html(
                layer_name=layer.name(),
                base_url=base_url,
                objectid_field=objectid_field,
                selected_count=len(selected),
                total_attachments=total_attachments,
                total_images=total_images,
                sections="\n".join(sections),
            )

            html_path = self.write_temp_html(output_html)
            QDesktopServices.openUrl(QUrl.fromLocalFile(html_path))

            self.info(
                f"Galería generada: {len(selected)} entidades, "
                f"{total_attachments} adjuntos, {total_images} imágenes."
            )

        except Exception:
            details = traceback.format_exc()
            self.log_error(details)
            self.critical("Ocurrió un error. Revisa el panel Registro de mensajes de QGIS.")

    # -------------------------
    # Detección URL REST
    # -------------------------
    def extract_arcgis_rest_url(self, source):
        """
        Intenta extraer:
        - URL base de capa: https://.../FeatureServer/1
        - token, si está explícito en la fuente

        Ejemplos de source posibles:
        - url='https://.../FeatureServer/1' ...
        - https://.../FeatureServer/1
        - url=https%3A%2F%2F... no siempre; se intenta buscar URL normal primero.
        """
        if not source:
            return None, None

        source_text = str(source)

        # 1) URL normal sin codificar.
        match = re.search(
            r"(https?://[^\s'\"<>]+?/arcgis/rest/services/[^\s'\"<>]+?/FeatureServer/\d+)",
            source_text,
            flags=re.IGNORECASE,
        )

        # 2) Variante menos estricta: cualquier FeatureServer/N.
        if not match:
            match = re.search(
                r"(https?://[^\s'\"<>]+?/FeatureServer/\d+)",
                source_text,
                flags=re.IGNORECASE,
            )

        if not match:
            return None, None

        base_url = match.group(1)

        # Limpieza por si la URL viene con parámetros pegados.
        base_url = re.sub(r"[?&].*$", "", base_url)
        base_url = base_url.rstrip("/")

        token = None
        token_match = re.search(r"(?:\?|&|token=)token=([^&\s'\"]+)", source_text, flags=re.IGNORECASE)
        if not token_match:
            token_match = re.search(r"(?:\?|&)token=([^&\s'\"]+)", source_text, flags=re.IGNORECASE)

        if token_match:
            token = token_match.group(1)

        return base_url, token

    # -------------------------
    # Campo OBJECTID
    # -------------------------
    def find_objectid_field(self, layer):
        field_names = [field.name() for field in layer.fields()]
        lower_to_real = {name.lower(): name for name in field_names}

        preferred = [
            "objectid",
            "objectid_1",
            "oid",
            "fid",
        ]

        for key in preferred:
            if key in lower_to_real:
                return lower_to_real[key]

        # Si QGIS conoce la PK, úsala como último recurso.
        try:
            pk_indexes = layer.dataProvider().pkAttributeIndexes()
            if pk_indexes:
                idx = pk_indexes[0]
                if 0 <= idx < len(field_names):
                    return field_names[idx]
        except Exception:
            pass

        return None

    # -------------------------
    # Consulta REST
    # -------------------------
    def build_url(self, base_url, path, params=None):
        url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
        if params:
            url += "?" + urlencode(params)
        return url

    def fetch_json(self, url):
        request = Request(
            url,
            headers={
                "User-Agent": "QGIS ArcGIS Attachments Viewer",
                "Accept": "application/json,text/plain,*/*",
            },
        )

        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8", errors="replace")

        try:
            data = json.loads(raw)
        except Exception:
            raise Exception("La respuesta REST no llegó en formato JSON. Puede ser un problema de permisos o token.")

        if isinstance(data, dict) and "error" in data:
            error = data.get("error", {})
            message = error.get("message", "Error desconocido")
            details = error.get("details", [])
            if details:
                message += " - " + " | ".join(str(d) for d in details)
            raise Exception(message)

        return data

    def fetch_attachments(self, base_url, objectid, token=None):
        params = {"f": "json"}
        if token:
            params["token"] = token

        url = self.build_url(base_url, f"{quote(str(objectid))}/attachments", params)
        data = self.fetch_json(url)

        attachments = data.get("attachmentInfos", [])
        if attachments is None:
            attachments = []

        return attachments

    def attachment_direct_url(self, base_url, objectid, attachment_id, token=None):
        url = self.build_url(
            base_url,
            f"{quote(str(objectid))}/attachments/{quote(str(attachment_id))}",
            None,
        )
        if token:
            url += "?" + urlencode({"token": token})
        return url

    # -------------------------
    # HTML
    # -------------------------
    def safe(self, value):
        return html.escape(str(value), quote=True)

    def section_error(self, index, objectid, error_message):
        return f"""
        <section class="feature-card error-card">
            <h2>Entidad {self.safe(index)} · OBJECTID {self.safe(objectid)}</h2>
            <p class="error">No se pudieron consultar los adjuntos: {self.safe(error_message)}</p>
        </section>
        """

    def build_feature_section(self, base_url, objectid, attachments, token, feature_index):
        if not attachments:
            return f"""
            <section class="feature-card empty-card">
                <h2>Entidad {self.safe(feature_index)} · OBJECTID {self.safe(objectid)}</h2>
                <p class="muted">Esta entidad no tiene adjuntos.</p>
            </section>
            """, 0

        cards = []
        image_count = 0

        for att in attachments:
            att_id = att.get("id")
            name = att.get("name", f"Adjunto {att_id}")
            content_type = att.get("contentType", "")
            size = att.get("size", "")

            direct_url = self.attachment_direct_url(base_url, objectid, att_id, token)
            is_image = str(content_type).lower().startswith("image/")

            if is_image:
                image_count += 1
                preview = f"""
                <a href="{self.safe(direct_url)}" target="_blank" rel="noopener">
                    <img src="{self.safe(direct_url)}" alt="{self.safe(name)}" loading="lazy">
                </a>
                """
            else:
                preview = f"""
                <div class="file-box">
                    <span class="file-icon">📎</span>
                    <a href="{self.safe(direct_url)}" target="_blank" rel="noopener">Abrir adjunto</a>
                </div>
                """

            size_text = ""
            try:
                if size not in (None, ""):
                    size_kb = round(float(size) / 1024, 1)
                    size_text = f"{size_kb} KB"
            except Exception:
                size_text = str(size)

            cards.append(f"""
            <article class="attachment-card">
                {preview}
                <div class="attachment-info">
                    <strong>{self.safe(name)}</strong>
                    <span>{self.safe(content_type or "sin tipo")}</span>
                    <span>{self.safe(size_text)}</span>
                    <a href="{self.safe(direct_url)}" target="_blank" rel="noopener">Abrir en navegador</a>
                </div>
            </article>
            """)

        return f"""
        <section class="feature-card">
            <h2>Entidad {self.safe(feature_index)} · OBJECTID {self.safe(objectid)}</h2>
            <p class="muted">{len(attachments)} adjunto(s), {image_count} imagen(es).</p>
            <div class="grid">
                {''.join(cards)}
            </div>
        </section>
        """, image_count

    def build_gallery_html(
        self,
        layer_name,
        base_url,
        objectid_field,
        selected_count,
        total_attachments,
        total_images,
        sections,
    ):
        return f"""<!doctype html>
<html lang="es">
<head>
<meta charset="utf-8">
<title>Adjuntos ArcGIS REST</title>
<style>
    body {{
        font-family: Arial, Helvetica, sans-serif;
        margin: 0;
        background: #f3f4f6;
        color: #111827;
    }}
    header {{
        background: #111827;
        color: white;
        padding: 18px 24px;
    }}
    header h1 {{
        margin: 0 0 8px 0;
        font-size: 22px;
    }}
    header p {{
        margin: 4px 0;
        color: #d1d5db;
        font-size: 14px;
    }}
    main {{
        padding: 20px 24px 40px 24px;
    }}
    .summary {{
        background: white;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 18px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    }}
    .feature-card {{
        background: white;
        border-radius: 10px;
        padding: 16px;
        margin-bottom: 20px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
    }}
    .feature-card h2 {{
        margin: 0 0 8px 0;
        font-size: 18px;
    }}
    .muted {{
        color: #6b7280;
        margin-top: 0;
    }}
    .grid {{
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
        gap: 16px;
    }}
    .attachment-card {{
        border: 1px solid #e5e7eb;
        border-radius: 10px;
        overflow: hidden;
        background: #fafafa;
    }}
    .attachment-card img {{
        width: 100%;
        height: 230px;
        object-fit: contain;
        background: #e5e7eb;
        display: block;
    }}
    .attachment-info {{
        padding: 10px 12px 12px 12px;
        display: flex;
        flex-direction: column;
        gap: 5px;
        font-size: 13px;
    }}
    .attachment-info strong {{
        font-size: 14px;
        overflow-wrap: anywhere;
    }}
    .attachment-info a {{
        color: #2563eb;
        text-decoration: none;
    }}
    .attachment-info a:hover {{
        text-decoration: underline;
    }}
    .file-box {{
        height: 230px;
        display: flex;
        align-items: center;
        justify-content: center;
        flex-direction: column;
        gap: 12px;
        background: #e5e7eb;
    }}
    .file-icon {{
        font-size: 40px;
    }}
    .error-card {{
        border-left: 5px solid #dc2626;
    }}
    .empty-card {{
        border-left: 5px solid #9ca3af;
    }}
    .error {{
        color: #b91c1c;
    }}
    code {{
        background: #e5e7eb;
        padding: 2px 4px;
        border-radius: 4px;
    }}
</style>
</head>
<body>
<header>
    <h1>Adjuntos ArcGIS REST</h1>
    <p>Capa: {self.safe(layer_name)}</p>
    <p>URL REST: {self.safe(base_url)}</p>
</header>
<main>
    <div class="summary">
        <p><strong>Entidades seleccionadas:</strong> {self.safe(selected_count)}</p>
        <p><strong>Campo usado:</strong> <code>{self.safe(objectid_field)}</code></p>
        <p><strong>Total adjuntos:</strong> {self.safe(total_attachments)}</p>
        <p><strong>Total imágenes:</strong> {self.safe(total_images)}</p>
    </div>

    {sections}
</main>
</body>
</html>
"""

    def write_temp_html(self, content):
        fd, path = tempfile.mkstemp(prefix="qgis_arcgis_adjuntos_", suffix=".html")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(content)
        return path
