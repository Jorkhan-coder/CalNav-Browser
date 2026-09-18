"""
calnav_print.py — Print / Save-as-PDF for the current page.

Features beyond a bare "print" button:
  • In-app preview (thumbnails + full page) via QtPdf, no OS print dialog
    detour just to see what you're printing.
  • "Modalita lettura": strips nav/ads/sidebars before capturing, like a
    print-focused reader mode.
  • Optional footer stamp (source URL + capture timestamp) — useful when the
    printout needs to prove where/when it came from.
  • Save as plain PDF or as a genuine PDF/A-1b (via pikepdf): XMP
    pdfaid:part/conformance tags + an embedded sRGB ICC OutputIntent, which
    is what PDF/A actually requires beyond "being a PDF".
  • Merge several open tabs into one combined PDF.
  • Print to a real printer (renders the generated PDF page-by-page).
"""
from __future__ import annotations

import io
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, List, Optional, Tuple

from PyQt6.QtCore import Qt, QMarginsF, QSize, QTimer
from PyQt6.QtGui import QPageLayout, QPageSize
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QPushButton, QCheckBox, QComboBox, QSplitter, QFileDialog,
    QMessageBox, QDialogButtonBox,
)
from PyQt6.QtPrintSupport import QPrinter, QPrintDialog
from PyQt6.QtPdf import QPdfDocument
from PyQt6.QtPdfWidgets import QPdfView
from PyQt6.QtWebEngineWidgets import QWebEngineView

try:
    import pikepdf
    PIKEPDF_AVAILABLE = True
except ImportError:
    PIKEPDF_AVAILABLE = False

# Read live off the OS — every Windows 10/11 install ships this — rather
# than bundling our own copy of a Microsoft/HP-authored profile.
_ICC_SRGB_PATH = Path(
    r"C:\Windows\System32\spool\drivers\color\sRGB Color Space Profile.icm"
)

_READER_STYLE_ID = "__cn_print_reader_style"
_STAMP_ID = "__cn_print_stamp"
_STAMP_STYLE_ID = "__cn_print_stamp_style"

_READER_MODE_JS = f"""
(function() {{
    if (document.getElementById('{_READER_STYLE_ID}')) return;
    var style = document.createElement('style');
    style.id = '{_READER_STYLE_ID}';
    style.textContent = `
        nav, header, footer, aside,
        [role="navigation"], [role="banner"], [role="complementary"],
        .ad, .ads, .advertisement, .cookie-banner, .cookie-consent,
        [class*="sidebar" i], [id*="sidebar" i],
        [class*="popup" i], [class*="modal" i], [class*="overlay" i],
        [class*="promo" i]
        {{ display: none !important; }}
        body {{ max-width: 780px !important; margin: 0 auto !important; }}
    `;
    document.head.appendChild(style);
}})();
"""

_CLEANUP_JS = f"""
(function() {{
    ['{_READER_STYLE_ID}', '{_STAMP_ID}', '{_STAMP_STYLE_ID}'].forEach(function(id) {{
        var el = document.getElementById(id);
        if (el) el.remove();
    }});
}})();
"""


def _stamp_js(text: str) -> str:
    safe_text = json.dumps(text)
    return f"""
(function() {{
    if (document.getElementById('{_STAMP_ID}')) return;
    var style = document.createElement('style');
    style.id = '{_STAMP_STYLE_ID}';
    style.textContent =
        '@media print {{ #{_STAMP_ID} {{ display: block !important; }} }} ' +
        '#{_STAMP_ID} {{ display: none; }}';
    document.head.appendChild(style);
    var div = document.createElement('div');
    div.id = '{_STAMP_ID}';
    div.style.cssText =
        'position: fixed; left: 0; right: 0; bottom: 0; padding: 6px 14px;' +
        'font: 10px sans-serif; color: #555; border-top: 1px solid #ccc;' +
        'background: white; z-index: 2147483647;';
    div.textContent = {safe_text};
    document.body.appendChild(div);
}})();
"""


# ── Capture ─────────────────────────────────────────────────────────────────

def _page_layout() -> QPageLayout:
    return QPageLayout(
        QPageSize(QPageSize.PageSizeId.A4),
        QPageLayout.Orientation.Portrait,
        QMarginsF(12, 12, 12, 12),
    )


def capture_page_pdf(
    view: QWebEngineView, *,
    reader_mode: bool, stamp: bool,
    on_done: Callable[[Optional[bytes], str], None],
):
    """Render *view*'s current page to PDF bytes (async — Chromium's own
    print pipeline). on_done(pdf_bytes_or_None, error_message)."""
    page = view.page()

    def do_capture():
        def on_pdf(data):
            pdf_bytes = bytes(data)
            if reader_mode or stamp:
                page.runJavaScript(_CLEANUP_JS)
            if not pdf_bytes:
                on_done(None, "Generazione PDF fallita per questa pagina.")
            else:
                on_done(pdf_bytes, "")
        page.printToPdf(on_pdf, _page_layout())

    scripts = []
    if reader_mode:
        scripts.append(_READER_MODE_JS)
    if stamp:
        when = datetime.now().strftime("%d/%m/%Y %H:%M")
        scripts.append(_stamp_js(f"{view.url().toString()}  —  catturato il {when}"))

    if scripts:
        page.runJavaScript("\n".join(scripts), lambda _result: do_capture())
    else:
        do_capture()


# ── PDF/A-1b conversion ───────────────────────────────────────────────────

def make_pdfa1b(pdf_bytes: bytes, *, title: str = "") -> bytes:
    """Convert a plain PDF to a (good-faith) PDF/A-1b: XMP identification +
    an embedded sRGB OutputIntent. Requires pikepdf."""
    if not PIKEPDF_AVAILABLE:
        raise RuntimeError("La libreria pikepdf non è installata.")

    pdf = pikepdf.open(io.BytesIO(pdf_bytes))

    with pdf.open_metadata(set_pikepdf_as_editor=False) as meta:
        if title:
            meta["dc:title"] = title
        meta["dc:format"] = "application/pdf"
        meta["pdf:Producer"] = "CalNav Browser"
        meta["xmp:CreatorTool"] = "CalNav Browser"
        meta["xmp:CreateDate"] = datetime.now(timezone.utc).strftime(
            "%Y-%m-%dT%H:%M:%SZ")
        meta["pdfaid:part"] = "1"
        meta["pdfaid:conformance"] = "B"

    if _ICC_SRGB_PATH.exists() and "/OutputIntents" not in pdf.Root:
        icc_bytes = _ICC_SRGB_PATH.read_bytes()
        stream = pikepdf.Stream(pdf, icc_bytes)
        stream[pikepdf.Name.N] = 3
        stream[pikepdf.Name.Alternate] = pikepdf.Name.DeviceRGB
        intent = pikepdf.Dictionary(
            Type=pikepdf.Name.OutputIntent,
            S=pikepdf.Name.GTS_PDFA1,
            OutputConditionIdentifier=pikepdf.String("sRGB IEC61966-2.1"),
            Info=pikepdf.String("sRGB IEC61966-2.1"),
            DestOutputProfile=stream,
        )
        pdf.Root.OutputIntents = pikepdf.Array([intent])

    if "/Encrypt" in pdf.trailer:
        del pdf.trailer["/Encrypt"]

    out = io.BytesIO()
    pdf.save(out, min_version="1.4")
    return out.getvalue()


def merge_pdfs(pdf_byte_chunks: List[bytes]) -> bytes:
    if not pdf_byte_chunks:
        return b""
    if not PIKEPDF_AVAILABLE:
        raise RuntimeError("La libreria pikepdf non è installata.")
    base = pikepdf.open(io.BytesIO(pdf_byte_chunks[0]))
    for chunk in pdf_byte_chunks[1:]:
        other = pikepdf.open(io.BytesIO(chunk))
        base.pages.extend(other.pages)
    out = io.BytesIO()
    base.save(out)
    return out.getvalue()


# ── Merge-tabs picker dialog ──────────────────────────────────────────────

class _MergeTabsDialog(QDialog):
    def __init__(self, tabs: List[Tuple[str, object]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Unisci altre schede nel PDF")
        self.setMinimumWidth(420)
        self._tabs = tabs
        vbox = QVBoxLayout(self)
        vbox.addWidget(QLabel("Seleziona le schede da aggiungere, in ordine, dopo quella corrente:"))
        self._list = QListWidget()
        for label, _view in tabs:
            item = QListWidgetItem(label)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Unchecked)
            self._list.addItem(item)
        vbox.addWidget(self._list)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        vbox.addWidget(buttons)

    def selected_views(self) -> List[object]:
        out = []
        for i in range(self._list.count()):
            if self._list.item(i).checkState() == Qt.CheckState.Checked:
                out.append(self._tabs[i][1])
        return out


# ── Print preview dialog ──────────────────────────────────────────────────

class PrintPreviewDialog(QDialog):
    """Self-contained print/export dialog for one QWebEngineView."""

    def __init__(
        self, view: QWebEngineView,
        other_tabs_provider: Callable[[], List[Tuple[str, object]]],
        parent=None,
    ):
        super().__init__(parent)
        self._view = view
        self._other_tabs_provider = other_tabs_provider
        self._pdf_bytes: Optional[bytes] = None
        self._extra_pdf_bytes: List[bytes] = []   # from merged tabs
        self._tmp_path = None

        self.setWindowTitle(f"Stampa — {view.title() or view.url().toString()}")
        self.resize(920, 720)
        self._build()
        self._regenerate()

    # ── UI ────────────────────────────────────────────────────────────────

    def _build(self):
        vbox = QVBoxLayout(self)

        split = QSplitter(Qt.Orientation.Horizontal)
        self._thumbs = QListWidget()
        self._thumbs.setFixedWidth(160)
        self._thumbs.setIconSize(QSize(120, 160))
        self._thumbs.currentRowChanged.connect(self._on_thumb_selected)
        split.addWidget(self._thumbs)

        self._doc = QPdfDocument(self)
        self._pdf_view = QPdfView(self)
        self._pdf_view.setDocument(self._doc)
        self._pdf_view.setPageMode(QPdfView.PageMode.MultiPage)
        self._pdf_view.setZoomMode(QPdfView.ZoomMode.FitToWidth)
        split.addWidget(self._pdf_view)
        split.setStretchFactor(1, 1)
        vbox.addWidget(split, stretch=1)

        opts = QHBoxLayout()
        self._chk_reader = QCheckBox("Modalità lettura (rimuovi menu/pubblicità)")
        self._chk_reader.stateChanged.connect(lambda _: self._regenerate())
        opts.addWidget(self._chk_reader)

        self._chk_stamp = QCheckBox("Timbro URL + data/ora")
        self._chk_stamp.stateChanged.connect(lambda _: self._regenerate())
        opts.addWidget(self._chk_stamp)

        opts.addStretch(1)
        opts.addWidget(QLabel("Formato:"))
        self._format = QComboBox()
        self._format.addItems(["PDF", "PDF/A-1b (archivio)"])
        if not PIKEPDF_AVAILABLE:
            self._format.model().item(1).setEnabled(False)
        opts.addWidget(self._format)
        vbox.addLayout(opts)

        self._status = QLabel("")
        self._status.setStyleSheet("color: #888; font-size: 11px;")
        vbox.addWidget(self._status)

        btns = QHBoxLayout()
        btn_merge = QPushButton("Unisci altre schede…")
        btn_merge.clicked.connect(self._on_merge_tabs)
        btns.addWidget(btn_merge)
        btns.addStretch(1)

        btn_print = QPushButton("Stampa su carta…")
        btn_print.clicked.connect(self._on_print_physical)
        btns.addWidget(btn_print)

        btn_save = QPushButton("Salva come…")
        btn_save.setDefault(True)
        btn_save.clicked.connect(self._on_save)
        btns.addWidget(btn_save)

        btn_close = QPushButton("Chiudi")
        btn_close.clicked.connect(self.reject)
        btns.addWidget(btn_close)
        vbox.addLayout(btns)

    # ── Generation ────────────────────────────────────────────────────────

    def _regenerate(self):
        self._status.setText("⏳  Generazione anteprima…")
        capture_page_pdf(
            self._view,
            reader_mode=self._chk_reader.isChecked(),
            stamp=self._chk_stamp.isChecked(),
            on_done=self._on_captured,
        )

    def _on_captured(self, pdf_bytes: Optional[bytes], error: str):
        if pdf_bytes is None:
            self._status.setText(f"❌  {error}")
            return
        chunks = [pdf_bytes] + self._extra_pdf_bytes
        try:
            merged = merge_pdfs(chunks) if len(chunks) > 1 else pdf_bytes
        except Exception as e:
            merged = pdf_bytes
            self._status.setText(f"⚠  Merge fallito, mostro solo la pagina corrente: {e}")
        self._pdf_bytes = merged
        self._load_preview(merged)

    def _load_preview(self, pdf_bytes: bytes):
        import tempfile, os as _os
        if self._tmp_path and _os.path.exists(self._tmp_path):
            try:
                _os.remove(self._tmp_path)
            except OSError:
                pass
        fd, path = tempfile.mkstemp(suffix=".pdf", prefix="calnav_print_")
        with _os.fdopen(fd, "wb") as f:
            f.write(pdf_bytes)
        self._tmp_path = path
        self._doc.load(path)
        if self._doc.status() == QPdfDocument.Status.Ready:
            self._populate_thumbs()
        else:
            self._doc.statusChanged.connect(self._on_doc_status_changed)

    def _on_doc_status_changed(self, status):
        if status == QPdfDocument.Status.Ready:
            self._doc.statusChanged.disconnect(self._on_doc_status_changed)
            self._populate_thumbs()

    def _populate_thumbs(self):
        self._thumbs.clear()
        n = self._doc.pageCount()
        for i in range(n):
            img = self._doc.render(i, QSize(120, 160))
            item = QListWidgetItem(f"Pag. {i + 1}")
            if not img.isNull():
                from PyQt6.QtGui import QIcon, QPixmap
                item.setIcon(QIcon(QPixmap.fromImage(img)))
            self._thumbs.addItem(item)
        if n:
            self._thumbs.setCurrentRow(0)
        self._status.setText(f"{n} pagina/e pronte." if n else "⚠  Nessuna pagina generata.")

    def _on_thumb_selected(self, row: int):
        if row < 0:
            return
        nav = self._pdf_view.pageNavigator()
        if nav:
            nav.jump(row, nav.currentLocation())

    # ── Actions ───────────────────────────────────────────────────────────

    def _on_merge_tabs(self):
        tabs = self._other_tabs_provider()
        if not tabs:
            QMessageBox.information(self, "Unisci schede", "Non ci sono altre schede aperte.")
            return
        dlg = _MergeTabsDialog(tabs, parent=self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        views = dlg.selected_views()
        if not views:
            return
        self._status.setText("⏳  Cattura delle altre schede…")
        self._extra_pdf_bytes = []
        self._merge_queue = list(views)
        self._merge_next()

    def _merge_next(self):
        if not self._merge_queue:
            self._regenerate()
            return
        view = self._merge_queue.pop(0)
        capture_page_pdf(
            view,
            reader_mode=self._chk_reader.isChecked(),
            stamp=self._chk_stamp.isChecked(),
            on_done=self._on_merge_captured,
        )

    def _on_merge_captured(self, pdf_bytes: Optional[bytes], error: str):
        if pdf_bytes:
            self._extra_pdf_bytes.append(pdf_bytes)
        self._merge_next()

    def _wanted_bytes(self) -> Optional[bytes]:
        if not self._pdf_bytes:
            return None
        if self._format.currentIndex() == 1:
            try:
                return make_pdfa1b(self._pdf_bytes, title=self._view.title())
            except Exception as e:
                QMessageBox.warning(self, "PDF/A-1b", f"Conversione fallita, salvo come PDF normale.\n\n{e}")
        return self._pdf_bytes

    def _on_save(self):
        data = self._wanted_bytes()
        if not data:
            return
        suggested = (self._view.title() or "pagina").strip() or "pagina"
        for ch in '<>:"/\\|?*':
            suggested = suggested.replace(ch, "_")
        path, _filt = QFileDialog.getSaveFileName(
            self, "Salva PDF", f"{suggested}.pdf", "PDF (*.pdf)")
        if not path:
            return
        try:
            Path(path).write_bytes(data)
        except OSError as e:
            QMessageBox.critical(self, "Salvataggio fallito", str(e))
            return
        self._status.setText(f"✅  Salvato: {path}")

    def _on_print_physical(self):
        if not self._pdf_bytes or self._doc.pageCount() == 0:
            return
        printer = QPrinter(QPrinter.PrinterMode.HighResolution)
        dlg = QPrintDialog(printer, self)
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return
        from PyQt6.QtGui import QPainter as _QPainter
        painter = _QPainter(printer)
        try:
            n = self._doc.pageCount()
            for i in range(n):
                if i > 0:
                    printer.newPage()
                page_pt = self._doc.pagePointSize(i)
                dpi = printer.resolution()
                target = QSize(
                    int(page_pt.width() / 72.0 * dpi),
                    int(page_pt.height() / 72.0 * dpi),
                )
                img = self._doc.render(i, target)
                painter.drawImage(painter.viewport(), img)
        finally:
            painter.end()
        self._status.setText("✅  Inviato alla stampante.")

    def closeEvent(self, event):
        import os as _os
        if self._tmp_path and _os.path.exists(self._tmp_path):
            try:
                _os.remove(self._tmp_path)
            except OSError:
                pass
        super().closeEvent(event)
