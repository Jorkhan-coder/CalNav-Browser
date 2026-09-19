"""
calnav_source_viewer.py — "Visualizza sorgente", but actually useful.

QtWebEngine's built-in WebAction.ViewSource is a no-op unless the app wires
up window creation for view-source: URLs, which CalNav doesn't — so the
native menu entry did nothing. This replaces it with a self-contained
viewer that goes further than a raw text dump:

  • Syntax-highlighted HTML / CSS / JS, with line numbers.
  • Two source modes: the live DOM (post-JavaScript, via QWebEnginePage.
    toHtml — what's actually on screen right now) and the as-sent-by-the-
    server HTML (a fresh HTTP fetch of the same URL) — genuinely different
    for most modern sites, and browsers don't make this easy to compare.
  • Inline <style>/<script> blocks and external stylesheet/script URLs
    extracted into their own tabs.
  • A quick "Analisi" panel: size, tag/resource counts, inline event-handler
    count, and a mixed-content (http:// resource on an https:// page) check.
  • Search, copy, save-to-file.
"""
from __future__ import annotations

import re
from typing import List, Optional, Tuple

from PyQt6.QtCore import Qt, QRect, QSize, QUrl
from PyQt6.QtGui import (
    QColor, QFont, QPainter, QSyntaxHighlighter, QTextCharFormat, QTextCursor,
    QTextDocument,
)
from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QWidget, QPlainTextEdit, QLabel,
    QPushButton, QLineEdit, QTabWidget, QComboBox, QFileDialog, QMessageBox,
    QApplication, QGridLayout,
)
from PyQt6.QtNetwork import QNetworkAccessManager, QNetworkRequest, QNetworkReply
from PyQt6.QtWebEngineWidgets import QWebEngineView

# ── Palette (self-contained — no import from calnav.py, to avoid a cycle) ──
_BG        = "#0A1628"
_GUTTER_BG = "#0D1B2E"
_FG        = "#E8F1FF"
_DIM       = "#7C93AD"
_TAG       = "#5CD6FF"
_ATTR      = "#FFD166"
_STRING    = "#8CE99A"
_COMMENT   = "#5A7A99"
_KEYWORD   = "#FF6B9D"
_NUMBER    = "#B794F6"
_SELECTOR  = "#5CD6FF"
_PROPERTY  = "#FFD166"


def _fmt(color: str, *, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    f = QTextCharFormat()
    f.setForeground(QColor(color))
    if bold:
        f.setFontWeight(QFont.Weight.Bold)
    if italic:
        f.setFontItalic(True)
    return f


# ── Syntax highlighters ─────────────────────────────────────────────────────

class HtmlHighlighter(QSyntaxHighlighter):
    _TAG_RE = re.compile(r"</?[a-zA-Z][\w:-]*")
    _ATTR_RE = re.compile(r'([a-zA-Z_:][\w:-]*)(\s*=\s*)("[^"]*"|\'[^\']*\'|[^\s>]+)')
    _COMMENT_START = re.compile(r"<!--")
    _COMMENT_END = re.compile(r"-->")
    _DOCTYPE_RE = re.compile(r"<!DOCTYPE[^>]*>", re.IGNORECASE)

    def highlightBlock(self, text: str):
        in_comment = self.previousBlockState() == 1

        if in_comment:
            end = self._COMMENT_END.search(text)
            if end:
                self.setFormat(0, end.end(), _fmt(_COMMENT, italic=True))
                in_comment = False
                rest_start = end.end()
            else:
                self.setFormat(0, len(text), _fmt(_COMMENT, italic=True))
                self.setCurrentBlockState(1)
                return
        else:
            rest_start = 0

        for m in self._DOCTYPE_RE.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), _fmt(_DIM, italic=True))

        for m in self._TAG_RE.finditer(text, rest_start):
            self.setFormat(m.start(), m.end() - m.start(), _fmt(_TAG, bold=True))

        for m in self._ATTR_RE.finditer(text, rest_start):
            self.setFormat(m.start(1), len(m.group(1)), _fmt(_ATTR))
            self.setFormat(m.start(3), len(m.group(3)), _fmt(_STRING))

        start = self._COMMENT_START.search(text, rest_start)
        if start:
            end = self._COMMENT_END.search(text, start.end())
            if end:
                self.setFormat(start.start(), end.end() - start.start(), _fmt(_COMMENT, italic=True))
            else:
                self.setFormat(start.start(), len(text) - start.start(), _fmt(_COMMENT, italic=True))
                self.setCurrentBlockState(1)
                return

        self.setCurrentBlockState(0)


class CssHighlighter(QSyntaxHighlighter):
    _COMMENT_START = re.compile(r"/\*")
    _COMMENT_END = re.compile(r"\*/")
    _SELECTOR_RE = re.compile(r"^[^{}/]+(?=\{)", re.MULTILINE)
    _PROPERTY_RE = re.compile(r"([\w-]+)(\s*:)")
    _STRING_RE = re.compile(r'"[^"]*"|\'[^\']*\'')
    _NUMBER_RE = re.compile(r"\b\d+(\.\d+)?(px|em|rem|%|vh|vw|s|ms)?\b")

    def highlightBlock(self, text: str):
        in_comment = self.previousBlockState() == 1
        rest_start = 0
        if in_comment:
            end = self._COMMENT_END.search(text)
            if end:
                self.setFormat(0, end.end(), _fmt(_COMMENT, italic=True))
                rest_start = end.end()
            else:
                self.setFormat(0, len(text), _fmt(_COMMENT, italic=True))
                self.setCurrentBlockState(1)
                return

        for m in self._SELECTOR_RE.finditer(text):
            self.setFormat(m.start(), m.end() - m.start(), _fmt(_SELECTOR, bold=True))
        for m in self._PROPERTY_RE.finditer(text, rest_start):
            self.setFormat(m.start(1), len(m.group(1)), _fmt(_PROPERTY))
        for m in self._STRING_RE.finditer(text, rest_start):
            self.setFormat(m.start(), m.end() - m.start(), _fmt(_STRING))
        for m in self._NUMBER_RE.finditer(text, rest_start):
            self.setFormat(m.start(), m.end() - m.start(), _fmt(_NUMBER))

        start = self._COMMENT_START.search(text, rest_start)
        if start:
            end = self._COMMENT_END.search(text, start.end())
            if end:
                self.setFormat(start.start(), end.end() - start.start(), _fmt(_COMMENT, italic=True))
                self.setCurrentBlockState(0)
            else:
                self.setFormat(start.start(), len(text) - start.start(), _fmt(_COMMENT, italic=True))
                self.setCurrentBlockState(1)
        else:
            self.setCurrentBlockState(0)


class JsHighlighter(QSyntaxHighlighter):
    _KEYWORDS = (
        r"\b(function|var|let|const|if|else|for|while|do|return|break|continue|"
        r"class|extends|new|this|typeof|instanceof|in|of|try|catch|finally|throw|"
        r"switch|case|default|delete|void|yield|async|await|import|export|from|"
        r"null|undefined|true|false|super|static|get|set)\b"
    )
    _KEYWORD_RE = re.compile(_KEYWORDS)
    _STRING_RE = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'|`(?:[^`\\]|\\.)*`')
    _COMMENT_RE = re.compile(r"//[^\n]*")
    _COMMENT_START = re.compile(r"/\*")
    _COMMENT_END = re.compile(r"\*/")
    _NUMBER_RE = re.compile(r"\b\d+(\.\d+)?\b")

    def highlightBlock(self, text: str):
        in_comment = self.previousBlockState() == 1
        rest_start = 0
        if in_comment:
            end = self._COMMENT_END.search(text)
            if end:
                self.setFormat(0, end.end(), _fmt(_COMMENT, italic=True))
                rest_start = end.end()
            else:
                self.setFormat(0, len(text), _fmt(_COMMENT, italic=True))
                self.setCurrentBlockState(1)
                return

        for m in self._KEYWORD_RE.finditer(text, rest_start):
            self.setFormat(m.start(), m.end() - m.start(), _fmt(_KEYWORD, bold=True))
        for m in self._NUMBER_RE.finditer(text, rest_start):
            self.setFormat(m.start(), m.end() - m.start(), _fmt(_NUMBER))
        for m in self._STRING_RE.finditer(text, rest_start):
            self.setFormat(m.start(), m.end() - m.start(), _fmt(_STRING))

        block_start = self._COMMENT_START.search(text, rest_start)
        line_comment = self._COMMENT_RE.search(text, rest_start)
        if block_start and (not line_comment or block_start.start() < line_comment.start()):
            end = self._COMMENT_END.search(text, block_start.end())
            if end:
                self.setFormat(block_start.start(), end.end() - block_start.start(), _fmt(_COMMENT, italic=True))
                self.setCurrentBlockState(0)
            else:
                self.setFormat(block_start.start(), len(text) - block_start.start(), _fmt(_COMMENT, italic=True))
                self.setCurrentBlockState(1)
                return
        else:
            self.setCurrentBlockState(0)

        if line_comment:
            self.setFormat(line_comment.start(), len(text) - line_comment.start(), _fmt(_COMMENT, italic=True))


# ── Line-numbered read-only code view ──────────────────────────────────────

class _LineNumberArea(QWidget):
    def __init__(self, editor: "CodeView"):
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_area_width(), 0)

    def paintEvent(self, event):
        self._editor.paint_line_numbers(event)


class CodeView(QPlainTextEdit):
    """Read-only monospace source view with a line-number gutter."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setReadOnly(True)
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        f = QFont("Consolas", 10)
        f.setStyleHint(QFont.StyleHint.Monospace)
        f.setFixedPitch(True)
        self.setFont(f)
        self.setStyleSheet(f"QPlainTextEdit {{ background: {_BG}; color: {_FG}; border: none; }}")
        self._area = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_area_width)
        self.updateRequest.connect(self._update_area)
        self._update_area_width(0)

    def line_number_area_width(self) -> int:
        digits = max(3, len(str(max(1, self.blockCount()))))
        return 14 + self.fontMetrics().horizontalAdvance("9") * digits

    def resizeEvent(self, event):
        super().resizeEvent(event)
        r = self.contentsRect()
        self._area.setGeometry(QRect(r.left(), r.top(), self.line_number_area_width(), r.height()))

    def _update_area_width(self, _):
        self.setViewportMargins(self.line_number_area_width(), 0, 0, 0)

    def _update_area(self, rect, dy):
        if dy:
            self._area.scroll(0, dy)
        else:
            self._area.update(0, rect.y(), self._area.width(), rect.height())
        if rect.contains(self.viewport().rect()):
            self._update_area_width(0)

    def paint_line_numbers(self, event):
        painter = QPainter(self._area)
        painter.fillRect(event.rect(), QColor(_GUTTER_BG))
        block = self.firstVisibleBlock()
        block_number = block.blockNumber()
        top = int(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        bottom = top + int(self.blockBoundingRect(block).height())
        painter.setPen(QColor(_DIM))
        while block.isValid() and top <= event.rect().bottom():
            if block.isVisible() and bottom >= event.rect().top():
                painter.drawText(
                    0, top, self._area.width() - 8, self.fontMetrics().height(),
                    Qt.AlignmentFlag.AlignRight, str(block_number + 1),
                )
            block = block.next()
            top = bottom
            bottom = top + int(self.blockBoundingRect(block).height())
            block_number += 1

    def find_text(self, query: str, backward: bool = False) -> bool:
        if not query:
            return False
        flags = QTextDocument.FindFlag(0)
        if backward:
            flags |= QTextDocument.FindFlag.FindBackward
        found = self.find(query, flags)
        if not found:
            cursor = self.textCursor()
            cursor.movePosition(
                QTextCursor.MoveOperation.End if backward else QTextCursor.MoveOperation.Start
            )
            self.setTextCursor(cursor)
            found = self.find(query, flags)
        return found


# ── Extraction / analysis helpers ──────────────────────────────────────────

_STYLE_RE = re.compile(r"<style[^>]*>(.*?)</style>", re.DOTALL | re.IGNORECASE)
_LINK_CSS_RE = re.compile(
    r'<link\b[^>]*\brel=["\']?stylesheet["\']?[^>]*>|<link\b[^>]*\bhref=[^>]*\brel=["\']?stylesheet["\']?[^>]*>',
    re.IGNORECASE,
)
_HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
_SCRIPT_INLINE_RE = re.compile(r"<script(?![^>]*\bsrc=)[^>]*>(.*?)</script>", re.DOTALL | re.IGNORECASE)
_SCRIPT_SRC_RE = re.compile(r'<script\b[^>]*\bsrc=["\']([^"\']+)["\']', re.IGNORECASE)
_INLINE_HANDLER_RE = re.compile(r'\bon[a-z]+\s*=\s*["\']', re.IGNORECASE)
_TAG_COUNT_RE = re.compile(r"<(\w+)", re.IGNORECASE)


def extract_css(html: str) -> Tuple[List[str], List[str]]:
    inline = [m.strip() for m in _STYLE_RE.findall(html) if m.strip()]
    links = [_HREF_RE.search(tag).group(1) for tag in _LINK_CSS_RE.findall(html) if _HREF_RE.search(tag)]
    return inline, links


def extract_js(html: str) -> Tuple[List[str], List[str]]:
    inline = [m.strip() for m in _SCRIPT_INLINE_RE.findall(html) if m.strip()]
    srcs = _SCRIPT_SRC_RE.findall(html)
    return inline, srcs


def analyze(html: str, page_url: QUrl) -> "dict[str, str]":
    size_b = len(html.encode("utf-8", errors="ignore"))
    tags = _TAG_COUNT_RE.findall(html)
    tag_lower = [t.lower() for t in tags]
    css_inline, css_links = extract_css(html)
    js_inline, js_srcs = extract_js(html)
    inline_handlers = len(_INLINE_HANDLER_RE.findall(html))

    is_https = page_url.scheme() == "https"
    mixed = 0
    if is_https:
        for url in css_links + js_srcs + re.findall(r'src=["\']([^"\']+)["\']', html, re.IGNORECASE):
            if url.startswith("http://"):
                mixed += 1

    return {
        "Dimensione": f"{size_b:,} byte  ·  {len(html):,} caratteri".replace(",", "."),
        "Tag totali": f"{len(tags):,}".replace(",", "."),
        "Script (inline + esterni)": f"{len(js_inline)} inline, {len(js_srcs)} esterni",
        "Fogli di stile (inline + esterni)": f"{len(css_inline)} inline, {len(css_links)} esterni",
        "Immagini <img>": str(tag_lower.count("img")),
        "Link <a>": str(tag_lower.count("a")),
        "Form <form>": str(tag_lower.count("form")),
        "Iframe": str(tag_lower.count("iframe")),
        "Gestori eventi inline (onclick=…)": str(inline_handlers),
        "⚠ Contenuto misto (http:// su pagina https)": str(mixed) if is_https else "n/d (pagina non https)",
    }


# ── Main dialog ─────────────────────────────────────────────────────────────

class SourceViewerDialog(QDialog):
    """Self-contained "view source" window for one QWebEngineView."""

    def __init__(self, view: QWebEngineView, parent=None):
        super().__init__(parent)
        self._view = view
        self._dom_html = ""
        self._raw_html = ""
        self._raw_fetched = False
        self._raw_nam: Optional[QNetworkAccessManager] = None

        self.setWindowTitle(f"👁  Sorgente — {view.title() or view.url().toString()}")
        self.resize(1040, 740)
        self._build()
        self._load_dom()      # needed for the extraction/analysis panels either way
        self._fetch_raw()     # default view is "HTML originale"

    # ── UI ───────────────────────────────────────────────────────────────

    def _build(self):
        self.setStyleSheet(f"background: #0F2138; color: {_FG};")
        vbox = QVBoxLayout(self)
        vbox.setContentsMargins(14, 12, 14, 12)
        vbox.setSpacing(8)

        top = QHBoxLayout()
        top.addWidget(QLabel("Vista:"))
        self._mode_combo = QComboBox()
        self._mode_combo.addItems([
            "📄 HTML originale (dal server)",
            "🧬 DOM live (dopo JavaScript)",
        ])
        self._mode_combo.currentIndexChanged.connect(self._on_mode_changed)
        top.addWidget(self._mode_combo)
        top.addSpacing(16)

        top.addWidget(QLabel("Cerca:"))
        self._search = QLineEdit()
        self._search.setFixedWidth(220)
        self._search.returnPressed.connect(lambda: self._find(False))
        top.addWidget(self._search)
        btn_prev = QPushButton("◀")
        btn_prev.setFixedWidth(28)
        btn_prev.clicked.connect(lambda: self._find(True))
        top.addWidget(btn_prev)
        btn_next = QPushButton("▶")
        btn_next.setFixedWidth(28)
        btn_next.clicked.connect(lambda: self._find(False))
        top.addWidget(btn_next)

        top.addStretch()
        btn_copy = QPushButton("⧉  Copia")
        btn_copy.clicked.connect(self._copy_current)
        top.addWidget(btn_copy)
        btn_save = QPushButton("💾  Salva…")
        btn_save.clicked.connect(self._save_current)
        top.addWidget(btn_save)
        vbox.addLayout(top)

        self._status = QLabel("⏳  Caricamento…")
        self._status.setStyleSheet(f"color: {_DIM}; font-size: 11px;")
        vbox.addWidget(self._status)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(f"""
            QTabWidget::pane {{ border: 1px solid #1C3050; }}
            QTabBar::tab {{ background: #14294A; color: {_FG}; padding: 6px 14px; }}
            QTabBar::tab:selected {{ background: #1C3050; }}
        """)

        self._html_view = CodeView()
        self._html_hl = HtmlHighlighter(self._html_view.document())
        self._tabs.addTab(self._html_view, "HTML")

        self._css_view = CodeView()
        self._css_hl = CssHighlighter(self._css_view.document())
        self._tabs.addTab(self._css_view, "CSS estratto")

        self._js_view = CodeView()
        self._js_hl = JsHighlighter(self._js_view.document())
        self._tabs.addTab(self._js_view, "JavaScript estratto")

        self._analysis_view = QPlainTextEdit()
        self._analysis_view.setReadOnly(True)
        self._analysis_view.setStyleSheet(f"background: {_BG}; color: {_FG}; border: none;")
        self._analysis_view.setFont(self._html_view.font())
        self._tabs.addTab(self._analysis_view, "🔎 Analisi")

        vbox.addWidget(self._tabs, stretch=1)

        bot = QHBoxLayout()
        bot.addStretch()
        btn_close = QPushButton("Chiudi")
        btn_close.clicked.connect(self.accept)
        bot.addWidget(btn_close)
        vbox.addLayout(bot)

    # ── Loading ──────────────────────────────────────────────────────────

    def _load_dom(self):
        self._view.page().toHtml(self._on_dom_html)

    def _on_dom_html(self, html: str):
        self._dom_html = html or ""
        if self._mode_combo.currentIndex() == 1:
            self._show_html(self._dom_html)
            self._status.setText("🧬  DOM live (dopo l'esecuzione di JavaScript).")
        self._populate_extracted(self._dom_html)

    def _fetch_raw(self):
        if self._raw_fetched:
            self._show_html(self._raw_html)
            return
        self._status.setText("⏳  Scaricamento HTML originale dal server…")
        self._raw_nam = QNetworkAccessManager(self)
        req = QNetworkRequest(self._view.url())
        req.setRawHeader(b"User-Agent", self._view.page().profile().httpUserAgent().encode())
        reply = self._raw_nam.get(req)
        reply.finished.connect(lambda: self._on_raw_fetched(reply))

    def _on_raw_fetched(self, reply: QNetworkReply):
        if reply.error() == QNetworkReply.NetworkError.NoError:
            data = bytes(reply.readAll())
            try:
                text = data.decode("utf-8")
            except UnicodeDecodeError:
                text = data.decode("latin-1", errors="replace")
            self._raw_html = text
            self._raw_fetched = True
            self._status.setText("📄  HTML originale (come inviato dal server, prima di ogni JavaScript).")
            if self._mode_combo.currentIndex() == 0:
                self._show_html(text)
        else:
            self._status.setText(f"❌  Download HTML originale fallito: {reply.errorString()}")
        reply.deleteLater()

    def _on_mode_changed(self, index: int):
        if index == 1:
            self._show_html(self._dom_html)
            self._status.setText("🧬  DOM live (dopo l'esecuzione di JavaScript).")
        else:
            if self._raw_fetched:
                self._show_html(self._raw_html)
                self._status.setText("📄  HTML originale (come inviato dal server).")
            else:
                self._fetch_raw()

    def _show_html(self, html: str):
        self._html_view.setPlainText(html)

    def _populate_extracted(self, html: str):
        css_inline, css_links = extract_css(html)
        js_inline, js_srcs = extract_js(html)

        css_text = ""
        if css_links:
            css_text += "/* Fogli di stile esterni */\n" + "\n".join(f"/* {u} */" for u in css_links) + "\n\n"
        for i, block in enumerate(css_inline, 1):
            css_text += f"/* <style> inline #{i} */\n{block}\n\n"
        self._css_view.setPlainText(css_text.strip() or "/* Nessun CSS inline o collegato trovato */")

        js_text = ""
        if js_srcs:
            js_text += "// Script esterni\n" + "\n".join(f"// {u}" for u in js_srcs) + "\n\n"
        for i, block in enumerate(js_inline, 1):
            js_text += f"// <script> inline #{i}\n{block}\n\n"
        self._js_view.setPlainText(js_text.strip() or "// Nessuno script inline o collegato trovato")

        stats = analyze(html, self._view.url())
        lines = [f"{k:<45} {v}" for k, v in stats.items()]
        self._analysis_view.setPlainText("\n".join(lines))

    # ── Actions ──────────────────────────────────────────────────────────

    def _current_view(self) -> CodeView:
        w = self._tabs.currentWidget()
        return w if isinstance(w, CodeView) else self._html_view

    def _current_text(self) -> str:
        w = self._tabs.currentWidget()
        return w.toPlainText() if hasattr(w, "toPlainText") else ""

    def _find(self, backward: bool):
        self._current_view().find_text(self._search.text(), backward)

    def _copy_current(self):
        QApplication.clipboard().setText(self._current_text())
        self._status.setText("⧉  Copiato negli appunti.")

    def _save_current(self):
        ext = {0: "html", 1: "css", 2: "js", 3: "txt"}.get(self._tabs.currentIndex(), "txt")
        suggested = f"sorgente.{ext}"
        path, _filt = QFileDialog.getSaveFileName(self, "Salva sorgente", suggested)
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(self._current_text())
        except OSError as e:
            QMessageBox.critical(self, "Salvataggio fallito", str(e))
            return
        self._status.setText(f"💾  Salvato: {path}")
