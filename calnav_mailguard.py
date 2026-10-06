#!/usr/bin/env python3
"""CalNav — MailGuard: stima locale dell'affidabilità di una mail (anti-phishing).

Flusso: EXTRACT_JS gira nella pagina webmail aperta (nessun canale/bridge,
solo runJavaScript con callback) e restituisce mittente, link, allegati e
testo della mail aperta; analyze() applica regole euristiche *locali* (nessun
dato lascia il computer) e produce indice 0-100 + elenco dei motivi.

È un indicatore, non una garanzia: SPF/DKIM/DMARC non sono nel DOM della
mail e non vengono verificati.
"""

import re
from typing import Dict, List, Optional
from urllib.parse import urlparse, parse_qs, unquote

# ── Estrazione dal DOM (Gmail, Outlook web, Roundcube/Libero/generico) ───────
EXTRACT_JS = r"""
(function () {
  function txt(el) { return el ? (el.innerText || el.textContent || '').trim() : ''; }
  function vis(el) { return !!(el && (el.offsetWidth || el.offsetHeight)); }
  var host = location.hostname, out = {
    provider: '', subject: '', from_name: '', from_email: '', reply_to: '',
    body: '', links: [], attachments: [], page_host: host
  };
  var body = null, m;

  if (/mail\.google\.com$/.test(host)) {
    out.provider = 'Gmail';
    var msgs = Array.prototype.filter.call(document.querySelectorAll('div.adn'), vis);
    var msg = msgs.length ? msgs[msgs.length - 1] : null;
    if (msg) {
      var s = msg.querySelector('span.gD[email]');
      if (s) { out.from_email = s.getAttribute('email') || ''; out.from_name = s.getAttribute('name') || txt(s); }
      var bodies = msg.querySelectorAll('div.a3s');
      body = bodies.length ? bodies[bodies.length - 1] : null;
      Array.prototype.forEach.call(msg.querySelectorAll('.aQH span.aV3, .aZo span.aV3, [download_url]'), function (a) {
        var n = a.getAttribute('download_url') ? a.getAttribute('download_url').split(':')[1] : txt(a);
        if (n) out.attachments.push(n);
      });
    }
    out.subject = txt(document.querySelector('h2.hP'));
  } else if (/(outlook\.(live|office|office365)\.com|outlook\.com)$/.test(host)) {
    out.provider = 'Outlook';
    body = document.querySelector('#UniqueMessageBody, div[aria-label="Corpo del messaggio"], div[aria-label="Message body"]');
    var pane = document.querySelector('[role="main"]') || document.body;
    var cand = pane.querySelectorAll('[title*="@"], [aria-label*="@"]');
    for (var i = 0; i < cand.length; i++) {
      var t = cand[i].getAttribute('title') || cand[i].getAttribute('aria-label') || '';
      if ((m = t.match(/[\w.+'-]+@[\w-]+(\.[\w-]+)+/))) {
        out.from_email = m[0]; out.from_name = txt(cand[i]).replace(m[0], '').replace(/[<>()]/g, '').trim(); break;
      }
    }
    var h = document.querySelector('[role="main"] [role="heading"], [data-app-section="ConversationContainer"] [role="heading"]');
    out.subject = txt(h);
  } else {
    out.provider = 'Webmail generica';
    body = document.querySelector('#messagebody, .message-htmlpart, #message-content, .messageBody, .mail-body, .email-body, [class*="message-body"]');
    out.subject = txt(document.querySelector('.header-subject, .subject, h1, h2'));
    var fr = document.querySelector('.header .from a, .header-from a, .from a, [class*="sender"]');
    if (fr) {
      var ft = (fr.getAttribute('title') || fr.getAttribute('href') || txt(fr)).replace(/^mailto:/, '');
      if ((m = ft.match(/[\w.+'-]+@[\w-]+(\.[\w-]+)+/))) out.from_email = m[0];
      out.from_name = txt(fr).replace(out.from_email, '').replace(/[<>()]/g, '').trim();
    }
  }
  if (!body) return JSON.stringify(out);
  out.body = txt(body).slice(0, 20000);
  Array.prototype.forEach.call(body.querySelectorAll('a[href]'), function (a) {
    if (out.links.length < 200) out.links.push({ text: txt(a).slice(0, 300), href: a.href });
  });
  return JSON.stringify(out);
})()
"""

# ── Dati di riferimento ──────────────────────────────────────────────────────
# marchio -> domini legittimi (dominio registrabile)
BRANDS: Dict[str, List[str]] = {
    "paypal": ["paypal.com", "paypal.it"],
    "amazon": ["amazon.com", "amazon.it", "amazon.de", "amazon.co.uk", "amazon.fr", "amazon.es", "amazonses.com"],
    "poste": ["poste.it", "postepay.it", "posteitaliane.it"],
    "postepay": ["poste.it", "postepay.it", "posteitaliane.it"],
    "intesa": ["intesasanpaolo.com", "intesa.it"],
    "unicredit": ["unicredit.it", "unicreditgroup.eu"],
    "google": ["google.com", "gmail.com", "youtube.com", "accounts.google.com"],
    "microsoft": ["microsoft.com", "outlook.com", "live.com", "office.com", "microsoftonline.com"],
    "apple": ["apple.com", "icloud.com", "me.com"],
    "netflix": ["netflix.com"],
    "dhl": ["dhl.com", "dhl.it", "dhl.de"],
    "ups": ["ups.com"],
    "fedex": ["fedex.com"],
    "inps": ["inps.it"],
    "agenziaentrate": ["agenziaentrate.gov.it", "agenziaentrate.it"],
    "aruba": ["aruba.it", "arubapec.it"],
    "libero": ["libero.it", "iol.it"],
    "facebook": ["facebook.com", "facebookmail.com", "meta.com"],
    "instagram": ["instagram.com"],
    "whatsapp": ["whatsapp.com"],
    "spid": ["spid.gov.it", "agid.gov.it"],
    "tim": ["tim.it", "telecomitalia.it"],
    "vodafone": ["vodafone.it", "vodafone.com"],
    "wind": ["windtre.it"],
    "ebay": ["ebay.com", "ebay.it"],
    "binance": ["binance.com"],
    "coinbase": ["coinbase.com"],
}
# marchi ≤3 lettere: troppo ambigui per il match "contiene" (es. "tim" in "optimum")
_SHORT_BRANDS = {b for b in BRANDS if len(b) <= 3}

FREE_MAIL = {"gmail.com", "outlook.com", "hotmail.com", "hotmail.it", "yahoo.com", "yahoo.it",
             "libero.it", "virgilio.it", "icloud.com", "live.com", "tiscali.it", "alice.it", "tin.it"}
SHORTENERS = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "ow.ly", "is.gd", "buff.ly", "cutt.ly",
              "rebrand.ly", "shorturl.at", "tiny.cc", "rb.gy", "t.ly", "lnkd.in"}
RISKY_TLDS = {"zip", "mov", "top", "xyz", "click", "work", "country", "gq", "tk", "ml", "cf", "ga",
              "icu", "cam", "rest", "monster", "support", "loan", "men", "date", "bid", "buzz"}
_SLD = {"co", "com", "org", "net", "gov", "edu", "ac"}
DANGEROUS_EXT = {"exe", "scr", "js", "jse", "vbs", "vbe", "bat", "cmd", "lnk", "iso", "img", "hta",
                 "jar", "msi", "ps1", "com", "pif", "html", "htm", "svg", "docm", "xlsm", "pptm", "one"}
ARCHIVE_EXT = {"zip", "rar", "7z", "gz", "tar", "cab", "ace"}

URGENCY = [
    r"urgent[ei]?", r"immediat[ao]", r"entro (\d+|24|48) ore", r"ultimo avviso", r"azione richiesta",
    r"sospes[oa]", r"bloccat[oa]", r"limitat[oa]", r"scadenza", r"disattivat[oa]", r"verifica (il tuo|immediatamente)",
    r"your account (has been|will be)", r"suspended", r"within 24 hours", r"final notice",
    r"act now", r"immediately", r"unusual (activity|sign-in)", r"verify your",
]
CREDENTIALS = [
    r"password", r"credenziali", r"\biban\b", r"carta di credito", r"\bpin\b", r"\botp\b",
    r"codice di sicurezza", r"\bcvv\b", r"accedi (ora|qui|subito)", r"conferma (i tuoi )?dati",
    r"aggiorna (i tuoi )?dati", r"sign in", r"log ?in", r"verify your (identity|account)", r"payment details",
]
GENERIC_GREETING = [r"gentile cliente", r"caro cliente", r"egregio utente", r"dear (customer|user|client)",
                    r"gentile utente"]

_LEET = str.maketrans({"0": "o", "1": "l", "3": "e", "4": "a", "5": "s", "7": "t", "8": "b", "@": "a", "$": "s"})
_EMAIL_RE = re.compile(r"[\w.+'-]+@([\w-]+(?:\.[\w-]+)+)")
_URLISH_RE = re.compile(r"^(?:https?://)?((?:[a-z0-9-]+\.)+[a-z]{2,})(?:[/:?#]|$)", re.I)


# ── Utilità ──────────────────────────────────────────────────────────────────
def registered_domain(host: str) -> str:
    host = (host or "").lower().strip(".")
    parts = host.split(".")
    if len(parts) <= 2:
        return host
    if len(parts[-1]) == 2 and parts[-2] in _SLD:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def _levenshtein(a: str, b: str, cap: int = 3) -> int:
    if abs(len(a) - len(b)) > cap:
        return cap + 1
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _unwrap(href: str) -> str:
    """Gmail/Outlook avvolgono i link in redirect (google.com/url?q=…,
    safelinks.protection.outlook.com): confrontiamo la destinazione vera."""
    try:
        u = urlparse(href)
        qs = parse_qs(u.query)
        host = (u.hostname or "").lower()
        if host.endswith("google.com") and u.path == "/url":
            for k in ("q", "url"):
                if k in qs:
                    return unquote(qs[k][0])
        if "safelinks.protection.outlook.com" in host and "url" in qs:
            return unquote(qs["url"][0])
    except Exception:
        pass
    return href


def _brand_hit(domain: str) -> Optional[str]:
    """Se `domain` imita un marchio noto (senza esserlo) ritorna il marchio."""
    reg = registered_domain(domain)
    for brand, legit in BRANDS.items():
        if reg in legit or any(reg == registered_domain(d) for d in legit):
            return None
    label = reg.split(".")[0]
    norm = label.translate(_LEET)
    tokens = [t for t in norm.split("-") if t]
    for brand in BRANDS:
        if brand in tokens or norm == brand:
            return brand
        if len(brand) >= 6 and brand in norm.replace("-", ""):
            return brand                      # paypal-secure, amazonlogin…
        if len(brand) >= 4 and any(t.startswith(brand) for t in tokens) and len(brand) >= 5:
            return brand
        if len(brand) >= 5 and 0 < _levenshtein(norm, brand) <= 1:
            return brand
    return None


# ── Motore di regole ─────────────────────────────────────────────────────────
class Finding:
    __slots__ = ("points", "title", "detail")

    def __init__(self, points: int, title: str, detail: str = ""):
        self.points, self.title, self.detail = points, title, detail


def analyze(data: dict) -> dict:
    """data = output di EXTRACT_JS. Ritorna {score, level, findings, ...}."""
    f: List[Finding] = []
    from_email = (data.get("from_email") or "").strip().lower()
    from_name = (data.get("from_name") or "").strip()
    reply_to = (data.get("reply_to") or "").strip().lower()
    body = data.get("body") or ""
    subject = data.get("subject") or ""
    text = f"{subject}\n{body}".lower()
    m = _EMAIL_RE.search(from_email)
    sender_dom = registered_domain(m.group(1)) if m else ""
    full_host = m.group(1).lower() if m else ""

    # — Mittente —
    if not sender_dom:
        f.append(Finding(10, "Mittente non rilevato",
                         "Impossibile leggere l'indirizzo del mittente dalla pagina."))
    else:
        name_l = from_name.lower().replace(" ", "").replace("-", "")
        for brand, legit in BRANDS.items():
            if brand in name_l and sender_dom not in [registered_domain(d) for d in legit]:
                f.append(Finding(35, f"Il nome del mittente cita «{brand}» ma il dominio è {sender_dom}",
                                 "Nome visualizzato e indirizzo reale non corrispondono: tecnica tipica di spoofing."))
                break
        hit = _brand_hit(full_host)
        if hit:
            f.append(Finding(40, f"Dominio del mittente simile a «{hit}»: {sender_dom}",
                             "Possibile typosquatting o dominio che imita un marchio noto."))
        if "xn--" in full_host or any(ord(c) > 127 for c in full_host):
            f.append(Finding(25, "Dominio del mittente con caratteri speciali (punycode)",
                             "Può nascondere caratteri che somigliano a lettere latine."))
        if sender_dom.split(".")[-1] in RISKY_TLDS:
            f.append(Finding(10, f"Estensione di dominio a rischio (.{sender_dom.split('.')[-1]})"))
        if re.search(r"\d{4,}", sender_dom.split(".")[0]):
            f.append(Finding(5, "Dominio del mittente con lunga sequenza di numeri"))
        rm = _EMAIL_RE.search(reply_to)
        if rm and registered_domain(rm.group(1)) != sender_dom:
            f.append(Finding(15, f"Reply-To diverso dal mittente ({registered_domain(rm.group(1))})",
                             "Le risposte andrebbero a un indirizzo diverso da quello che ha scritto."))

    # — Link —
    seen = set()
    mismatch = ip = short = punyl = risky = deep = at = http = lookalike = 0
    link_rows = []
    for ln in data.get("links") or []:
        href = _unwrap(ln.get("href") or "")
        if not href.lower().startswith(("http://", "https://")):
            continue
        try:
            u = urlparse(href)
            host = (u.hostname or "").lower()
        except Exception:
            continue
        if not host:
            continue
        reg = registered_domain(host)
        shown = (ln.get("text") or "").strip()
        link_rows.append((shown, host))
        key = (shown, href)
        if key in seen:
            continue
        seen.add(key)
        sm = _URLISH_RE.match(shown)
        if sm and registered_domain(sm.group(1).lower()) != reg:
            mismatch += 1
        if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", host):
            ip += 1
        if host in SHORTENERS:
            short += 1
        if "xn--" in host:
            punyl += 1
        if reg.split(".")[-1] in RISKY_TLDS:
            risky += 1
        if host.count(".") >= 4:
            deep += 1
        if "@" in u.netloc:
            at += 1
        if u.scheme == "http":
            http += 1
        if _brand_hit(host):
            lookalike += 1
    if mismatch:
        f.append(Finding(30, f"{mismatch} link con testo diverso dalla destinazione reale",
                         "Il testo mostra un sito, ma il click porta altrove."))
    if lookalike:
        f.append(Finding(30, f"{lookalike} link verso domini che imitano un marchio noto"))
    if ip:
        f.append(Finding(20, f"{ip} link verso indirizzo IP numerico"))
    if at:
        f.append(Finding(15, f"{at} link con '@' nell'indirizzo (nasconde la vera destinazione)"))
    if punyl:
        f.append(Finding(15, f"{punyl} link con dominio punycode"))
    if short:
        f.append(Finding(10, f"{short} link accorciati (destinazione non verificabile)"))
    if risky:
        f.append(Finding(10, f"{risky} link verso estensioni di dominio a rischio"))
    if deep:
        f.append(Finding(8, f"{deep} link con troppi sottodomini"))
    if http:
        f.append(Finding(5, f"{http} link non cifrati (http)"))

    # — Allegati —
    for name in data.get("attachments") or []:
        parts = name.lower().split(".")
        ext = parts[-1] if len(parts) > 1 else ""
        if len(parts) > 2 and parts[-2] in {"pdf", "doc", "docx", "xls", "xlsx", "jpg", "png", "txt"} \
                and ext in DANGEROUS_EXT | ARCHIVE_EXT:
            f.append(Finding(30, f"Allegato con doppia estensione: {name}",
                             "Es. fattura.pdf.exe — si finge un documento."))
        elif ext in DANGEROUS_EXT:
            f.append(Finding(30, f"Allegato potenzialmente eseguibile: {name}"))
        elif ext in ARCHIVE_EXT:
            f.append(Finding(10, f"Allegato compresso: {name}", "Gli archivi possono nascondere malware."))

    # — Testo —
    urg = [p for p in URGENCY if re.search(p, text)]
    if urg:
        f.append(Finding(min(15, 5 * len(urg)), "Linguaggio di urgenza o minaccia",
                         "Il phishing spinge ad agire in fretta senza riflettere."))
    cred = [p for p in CREDENTIALS if re.search(p, text)]
    if cred:
        f.append(Finding(min(15, 7 * len(cred)), "Richiesta di credenziali, dati personali o pagamento",
                         "Gli enti seri non chiedono questi dati via mail."))
    if any(re.search(p, text) for p in GENERIC_GREETING):
        f.append(Finding(5, "Saluto generico (nessun nome personale)"))
    if sender_dom in FREE_MAIL and (urg or cred) and not any(x.points >= 35 for x in f):
        f.append(Finding(8, "Richiesta sensibile da un indirizzo di posta gratuita"))

    risk = min(100, sum(x.points for x in f))
    score = 100 - risk
    if score >= 75:
        level = "Affidabile"
    elif score >= 45:
        level = "Dubbia"
    else:
        level = "Rischio alto"
    f.sort(key=lambda x: -x.points)
    return {
        "score": score, "level": level,
        "findings": [(x.points, x.title, x.detail) for x in f],
        "sender": f"{from_name} <{from_email}>" if from_name else from_email,
        "subject": subject, "links": link_rows, "provider": data.get("provider", ""),
    }


# ── Finestra del risultato ───────────────────────────────────────────────────
def show_report(parent, data: dict):
    """Mostra il risultato. `data` None/vuoto → messaggio 'nessuna mail aperta'."""
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QLabel, QProgressBar, QScrollArea, QWidget, QPushButton, QHBoxLayout,
    )
    from PyQt6.QtGui import QFont

    dlg = QDialog(parent)
    dlg.setWindowTitle("Affidabilità mail — CalNav")
    dlg.setMinimumSize(520, 460)
    dlg.setStyleSheet("QDialog{background:#0F1E33;} QLabel{color:#E6F1FF;}")
    lay = QVBoxLayout(dlg)
    lay.setContentsMargins(20, 18, 20, 16)

    if not data or not (data.get("body") or data.get("from_email")):
        lbl = QLabel("Nessuna mail aperta rilevata in questa pagina.\n\n"
                     "Apri un messaggio in Gmail, Outlook o nella tua webmail e riprova.")
        lbl.setWordWrap(True)
        lay.addWidget(lbl)
        dlg.exec()
        return

    r = analyze(data)
    color = "#2ECC71" if r["score"] >= 75 else "#F5A623" if r["score"] >= 45 else "#E74C3C"
    head = QLabel(f"{r['score']}/100 — {r['level']}")
    head.setFont(QFont("Segoe UI", 20, QFont.Weight.Bold))
    head.setStyleSheet(f"color:{color};")
    lay.addWidget(head)
    bar = QProgressBar()
    bar.setRange(0, 100)
    bar.setValue(r["score"])
    bar.setTextVisible(False)
    bar.setFixedHeight(10)
    bar.setStyleSheet(f"QProgressBar{{background:#1C3050;border:none;border-radius:5px;}}"
                      f"QProgressBar::chunk{{background:{color};border-radius:5px;}}")
    lay.addWidget(bar)

    info = QLabel(f"<b>Da:</b> {_esc(r['sender'] or '—')}<br><b>Oggetto:</b> {_esc(r['subject'] or '—')}"
                  f"<br><b>Link nel messaggio:</b> {len(r['links'])}")
    info.setWordWrap(True)
    info.setTextFormat(Qt.TextFormat.RichText)
    lay.addWidget(info)

    inner = QWidget()
    il = QVBoxLayout(inner)
    il.setContentsMargins(0, 0, 0, 0)
    if r["findings"]:
        for pts, title, detail in r["findings"]:
            c = "#E74C3C" if pts >= 25 else "#F5A623" if pts >= 10 else "#9DB4D0"
            row = QLabel(f"<span style='color:{c}'>●</span> <b>{_esc(title)}</b>"
                         + (f"<br><span style='color:#9DB4D0'>{_esc(detail)}</span>" if detail else ""))
            row.setWordWrap(True)
            row.setTextFormat(Qt.TextFormat.RichText)
            il.addWidget(row)
    else:
        il.addWidget(QLabel("Nessun segnale sospetto rilevato dalle regole locali."))
    il.addStretch(1)
    scroll = QScrollArea()
    scroll.setWidgetResizable(True)
    scroll.setStyleSheet("QScrollArea{border:none;background:transparent;}"
                         "QScrollArea>QWidget>QWidget{background:transparent;}")
    scroll.setWidget(inner)
    lay.addWidget(scroll, 1)

    note = QLabel("Stima euristica eseguita sul tuo computer: nulla viene inviato online. "
                  "Non verifica SPF/DKIM/DMARC né la reputazione dei link, e non è una garanzia. "
                  "Nel dubbio non cliccare: apri il sito digitando tu l'indirizzo.")
    note.setWordWrap(True)
    note.setStyleSheet("color:#6F89A8;font-size:11px;")
    lay.addWidget(note)
    btns = QHBoxLayout()
    btns.addStretch(1)
    ok = QPushButton("Chiudi")
    ok.clicked.connect(dlg.accept)
    ok.setStyleSheet("QPushButton{background:#1C3050;color:#00D4FF;border:none;border-radius:6px;"
                     "padding:6px 18px;font-weight:bold;}QPushButton:hover{background:#25406A;}")
    btns.addWidget(ok)
    lay.addLayout(btns)
    dlg.exec()


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
