#!/usr/bin/env python3
"""CalNav — MailGuard: stima locale dell'affidabilità di una mail (anti-phishing).

Flusso (run): EXTRACT_JS gira nella pagina webmail aperta (nessun canale/bridge,
solo runJavaScript con callback) e restituisce mittente, link, allegati e
testo della mail aperta. Su Gmail, GMAIL_HEADERS_JS scarica anche l'originale
del messaggio ("Mostra originale", con la sessione già loggata) da cui si
leggono SPF/DKIM/DMARC. analyze() applica regole euristiche *locali* (nessun
dato lascia il computer) e produce indice 0-100 + elenco dei motivi.

È un indicatore, non una garanzia. Gli header di autenticazione sono
disponibili solo su Gmail; sugli altri provider non vengono verificati.
"""

import json
import re
from typing import Dict, List, Optional
from urllib.parse import urlparse, parse_qs, unquote

# ── Estrazione dal DOM (Gmail, Outlook, Yahoo, Roundcube/Libero/generico) ────
EXTRACT_JS = r"""
(function () {
  var EMAIL = /[\w.+'-]+@[\w-]+(\.[\w-]+)+/;
  function txt(el) { return el ? (el.innerText || el.textContent || '').trim() : ''; }
  function vis(el) { return !!(el && (el.offsetWidth || el.offsetHeight || (el.getClientRects && el.getClientRects().length))); }
  var host = location.hostname, doc = document, body = null, m;
  var out = {
    provider: '', subject: '', from_name: '', from_email: '', reply_to: '',
    body: '', links: [], attachments: [], page_host: host, approx: false, gmail_msg_id: '',
    diag: { matched: [], iframes: 0, skeleton: [] }
  };
  function first(sels, root) {
    root = root || doc;
    for (var i = 0; i < sels.length; i++) {
      var el = null;
      try { el = root.querySelector(sels[i]); } catch (e) {}
      if (el && vis(el)) { out.diag.matched.push(sels[i]); return el; }
    }
    return null;
  }
  function setSender(t) {
    if (!t || !(m = t.match(EMAIL))) return false;
    out.from_email = m[0];
    return true;
  }
  function sameOriginFrames() {
    var res = [], fr = document.querySelectorAll('iframe');
    out.diag.iframes = fr.length;
    Array.prototype.forEach.call(fr, function (f) {
      try { if (f.contentDocument && f.contentDocument.body) res.push(f.contentDocument); } catch (e) {}
    });
    return res;
  }

  if (/mail\.google\.com$/.test(host)) {
    out.provider = 'Gmail';
    var msgs = Array.prototype.filter.call(document.querySelectorAll('div.adn'), vis);
    var msg = msgs.length ? msgs[msgs.length - 1] : null;
    if (msg) {
      var mid = msg.getAttribute('data-message-id') || '';
      out.gmail_msg_id = mid.replace(/^#/, '');
      var s = msg.querySelector('span.gD[email]');
      if (s) { out.from_email = s.getAttribute('email') || ''; out.from_name = s.getAttribute('name') || txt(s); }
      var bodies = msg.querySelectorAll('div.a3s');
      body = bodies.length ? bodies[bodies.length - 1] : null;
      if (body) out.diag.matched.push('gmail:div.a3s');
      Array.prototype.forEach.call(msg.querySelectorAll('.aQH span.aV3, .aZo span.aV3, [download_url]'), function (a) {
        var n = a.getAttribute('download_url') ? a.getAttribute('download_url').split(':')[1] : txt(a);
        if (n) out.attachments.push(n);
      });
    }
    out.subject = txt(document.querySelector('h2.hP'));
  } else if (/(outlook\.(live|office|office365)\.com|outlook\.com)$/.test(host)) {
    out.provider = 'Outlook';
    body = first(['#UniqueMessageBody', 'div[aria-label="Corpo del messaggio"]', 'div[aria-label="Message body"]',
                  'div[role="document"][aria-label]', 'div[role="document"]']);
    var pane = document.querySelector('[role="main"]') || document.body;
    var cand = pane.querySelectorAll('[title*="@"], [aria-label*="@"], [data-testid*="Persona"]');
    for (var i = 0; i < cand.length; i++) {
      var t = (cand[i].getAttribute('title') || cand[i].getAttribute('aria-label') || txt(cand[i]));
      if (setSender(t)) { out.from_name = txt(cand[i]).replace(out.from_email, '').replace(/[<>()]/g, '').trim(); break; }
    }
    var h = first(['[data-app-section="ConversationContainer"] [role="heading"]', '[role="main"] [role="heading"]']);
    out.subject = txt(h);
  } else if (/mail\.yahoo\.com$/.test(host)) {
    out.provider = 'Yahoo Mail';
    body = first(['[data-test-id="message-view-body-content"]', '[data-test-id="message-view-body"]']);
    var yf = first(['[data-test-id="message-from"]', '[data-test-id="message-group-from"]']);
    if (yf) { setSender(yf.getAttribute('title') || txt(yf)); out.from_name = txt(yf).replace(out.from_email, '').replace(/[<>()]/g, '').trim(); }
    out.subject = txt(first(['[data-test-id="message-group-subject-text"]', 'h1']));
  } else {
    out.provider = 'Webmail generica';
  }

  // — Webmail generica / fallback: selettori comuni, poi iframe stesso-origine —
  if (!body) {
    var BODY_SELS = ['#messagebody', '.message-htmlpart', '#message-content', '.messageBody', '.mail-body',
                     '.email-body', '.msg-body', '[class*="message-body"]', '[class*="MessageBody"]',
                     '[class*="mail-body"]', '[id*="messagebody"]', '[id*="message_body"]', '[data-testid*="message-body"]'];
    body = first(BODY_SELS);
    if (!body) {
      var best = null, bestLen = 0;
      sameOriginFrames().forEach(function (d) {
        var inner = first(BODY_SELS, d) || d.body;
        var len = txt(inner).length;
        if (len > bestLen) { best = { d: d, el: inner }; bestLen = len; }
      });
      if (best && bestLen > 30) { doc = best.d; body = best.el; out.approx = true; out.diag.matched.push('iframe'); }
    }
    if (!body) {   // ultimo tentativo A: ruoli semantici
      var cs = document.querySelectorAll('[role="document"], [role="article"], article');
      var bl = 0;
      Array.prototype.forEach.call(cs, function (c) {
        var len = txt(c).length;
        if (vis(c) && len > 120 && len < 60000 && len > bl) { body = c; bl = len; }
      });
      if (body) { out.approx = true; out.diag.matched.push('semantic'); }
    }
    if (!body) {   // ultimo tentativo B: dal contenuto principale scende al contenitore che ha ≥60% del testo
      var el = document.querySelector('[role="main"]') || document.body, tl = txt(el).length;
      for (var depth = 0; depth < 25 && el; depth++) {
        var nxt = null;
        for (var k = 0; k < el.children.length; k++) {
          var ch = el.children[k];
          if (vis(ch) && txt(ch).length >= 0.6 * tl) { nxt = ch; break; }
        }
        if (!nxt) break;
        el = nxt;
      }
      if (el && el !== document.body && tl > 120 && tl < 60000) { body = el; out.approx = true; out.diag.matched.push('dominant'); }
    }
  }

  // — Mittente / oggetto generici (se il provider non li ha già valorizzati) —
  if (!out.from_email) {
    var FROM_SELS = ['.header .from a', '.header-from a', '.from a', '[class*="sender"]', '[class*="from"] a',
                     '[class*="From"]', '[data-testid*="from"]'];
    [doc, document].some(function (d) {
      var fr = first(FROM_SELS, d);
      if (fr && setSender((fr.getAttribute('title') || '') + ' ' + (fr.getAttribute('href') || '').replace(/^mailto:/, '') + ' ' + txt(fr))) {
        out.from_name = txt(fr).replace(out.from_email, '').replace(/[<>()]/g, '').trim();
        return true;
      }
      return false;
    });
  }
  if (!out.from_email) {
    [doc, document].some(function (d) {
      var head = txt(d.body).slice(0, 6000);
      var mm = head.match(/(?:^|\n)\s*(?:Da|From|Mittente|De|Von)\s*:?\s*([^\n<]*?)\s*<?([\w.+'-]+@[\w-]+(?:\.[\w-]+)+)>?/i);
      if (mm) { out.from_email = mm[2]; out.from_name = (mm[1] || '').trim(); out.approx = true; return true; }
      return false;
    });
  }
  if (!out.subject) out.subject = txt(first(['.header-subject', '.subject', '[class*="subject"]', 'h1', 'h2']));
  if (!out.attachments.length) {
    Array.prototype.forEach.call(doc.querySelectorAll('[class*="attachment"] a, .attachmentslist a, [data-test-id*="attachment"], [data-testid*="attachment"]'), function (a) {
      var n = (a.getAttribute('download') || txt(a)).trim();
      if (/\.\w{2,5}$/.test(n) && out.attachments.length < 30) out.attachments.push(n);
    });
  }

  // — Diagnostica anonima: solo struttura (tag/id/class/ruolo), mai testo della mail —
  function desc(el) {
    var d = el.tagName.toLowerCase();
    if (el.id) d += '#' + String(el.id).slice(0, 30);
    if (el.className && typeof el.className === 'string') d += '.' + el.className.trim().split(/\s+/).slice(0, 3).join('.').slice(0, 60);
    var r = el.getAttribute('role'); if (r) d += '[role=' + r + ']';
    var a = el.getAttribute('aria-label'); if (a) d += '[aria=' + a.replace(EMAIL, '<email>').slice(0, 30) + ']';
    var ti = el.getAttribute('data-testid') || el.getAttribute('data-test-id'); if (ti) d += '[testid=' + ti.slice(0, 40) + ']';
    return d;
  }
  try {
    if (body) {
      for (var el = body, n = 0; el && el.tagName && n < 12; el = el.parentElement, n++) out.diag.skeleton.push(desc(el));
    } else {
      var mainEl = document.querySelector('[role="main"]') || document.body;
      Array.prototype.forEach.call(mainEl.querySelectorAll('*'), function (e) {
        if (out.diag.skeleton.length < 40 && vis(e) && (e.id || e.getAttribute('role') || e.getAttribute('data-testid'))) out.diag.skeleton.push(desc(e));
      });
    }
  } catch (e) {}

  if (!body) return JSON.stringify(out);
  out.body = txt(body).slice(0, 20000);
  Array.prototype.forEach.call(body.querySelectorAll('a[href]'), function (a) {
    if (out.links.length < 200) out.links.push({ text: txt(a).slice(0, 300), href: a.href });
  });
  return JSON.stringify(out);
})()
"""

# Gmail: scarica l'"originale" del messaggio aperto (stessa sessione, solo verso
# mail.google.com) e tiene gli header in window.__calnavMG. Il fetch è asincrono:
# Python fa polling di quella variabile (runJavaScript non attende le Promise).
GMAIL_HEADERS_JS = r"""
(function () {
  window.__calnavMG = { state: 'pending' };
  try {
    var ik = (window.GLOBALS && window.GLOBALS[9]) || '';
    if (!ik) {
      var a = document.querySelector('a[href*="ik="]');
      var mm = a && a.href.match(/[?&]ik=([0-9a-f]+)/);
      if (mm) ik = mm[1];
    }
    var msgs = Array.prototype.filter.call(document.querySelectorAll('div.adn'), function (e) { return e.offsetWidth || e.offsetHeight; });
    var msg = msgs.length ? msgs[msgs.length - 1] : null;
    var id = msg ? (msg.getAttribute('data-message-id') || '').replace(/^#/, '') : '';
    var um = location.pathname.match(/\/mail\/u\/(\d+)/);
    if (!ik || !id) { window.__calnavMG = { state: 'error', why: !ik ? 'ik' : 'id' }; return 'started'; }
    var url = '/mail/u/' + (um ? um[1] : '0') + '/?ik=' + encodeURIComponent(ik) + '&view=om&permmsgid=' + encodeURIComponent(id);
    fetch(url, { credentials: 'include' }).then(function (r) { return r.text(); }).then(function (t) {
      var cut = t.search(/\r?\n\r?\n/);
      window.__calnavMG = { state: 'done', headers: (cut > 0 ? t.slice(0, cut) : t).slice(0, 40000) };
    }).catch(function (e) { window.__calnavMG = { state: 'error', why: 'fetch' }; });
  } catch (e) { window.__calnavMG = { state: 'error', why: 'exc' }; }
  return 'started';
})()
"""


# ── Parsing header di autenticazione ─────────────────────────────────────────
def parse_headers(raw: str) -> Optional[dict]:
    """Da header grezzi → {spf, dkim, dmarc, reply_to, from_header, dkim_domains}.
    Ritorna None se non c'è alcun esito di autenticazione leggibile."""
    if not raw or not raw.strip():
        return None
    unfolded = re.sub(r"\r?\n[ \t]+", " ", raw)
    hdrs = []
    for line in re.split(r"\r?\n", unfolded):
        if ":" in line:
            k, _, v = line.partition(":")
            hdrs.append((k.strip().lower(), v.strip()))

    def get(name):
        return [v for k, v in hdrs if k == name]

    res = {"spf": None, "dkim": None, "dmarc": None, "dkim_domains": [],
           "reply_to": (get("reply-to") or [""])[0], "from_header": (get("from") or [""])[0]}
    ar = get("authentication-results")
    if ar:
        top = ar[0]   # il più in alto = aggiunto dal server ricevente
        for key in ("spf", "dmarc"):
            mm = re.search(r"\b%s=(\w+)" % key, top, re.I)
            if mm:
                res[key] = mm.group(1).lower()
        dk = [x.lower() for x in re.findall(r"\bdkim=(\w+)", top, re.I)]
        if dk:
            res["dkim"] = "pass" if "pass" in dk else dk[0]
        res["dkim_domains"] = re.findall(r"header\.(?:d|i)=@?([\w.-]+)", top, re.I)
    if res["spf"] is None:
        rs = get("received-spf")
        if rs:
            mm = re.match(r"(\w+)", rs[0])
            if mm:
                res["spf"] = mm.group(1).lower()
    if not any(res[k] for k in ("spf", "dkim", "dmarc")):
        return None
    return res


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
    auth = data.get("auth")
    reply_to = ((data.get("reply_to") or (auth or {}).get("reply_to")) or "").strip().lower()
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

    # — Autenticazione (solo se gli header sono stati letti: Gmail) —
    if auth:
        spf, dkim, dmarc = auth.get("spf"), auth.get("dkim"), auth.get("dmarc")
        if dmarc == "fail":
            f.append(Finding(30, "DMARC fallito",
                             "Il dominio del mittente non autorizza questo invio: forte indizio di falsificazione."))
        if spf == "fail":
            f.append(Finding(20, "SPF fallito", "Il server che ha inviato non è autorizzato dal dominio mittente."))
        elif spf == "softfail":
            f.append(Finding(10, "SPF in softfail", "Il server mittente non è tra quelli previsti dal dominio."))
        if dkim in ("fail", "neutral", "permerror", "temperror"):
            f.append(Finding(15, f"Firma DKIM non valida ({dkim})", "Il messaggio potrebbe essere stato alterato o falsificato."))
        doms = [registered_domain(d) for d in auth.get("dkim_domains") or []]
        if dkim == "pass" and doms and sender_dom and sender_dom not in doms:
            f.append(Finding(5, "Firma DKIM valida ma di un dominio diverso dal mittente",
                             "Firmata da " + ", ".join(sorted(set(doms))) + ", non da " + sender_dom + "."))
        if all(x in (None, "none") for x in (spf, dkim, dmarc)):
            f.append(Finding(10, "Nessuna autenticazione SPF/DKIM/DMARC presente"))
        elif spf == "pass" and dkim == "pass" and dmarc in ("pass", None):
            f.append(Finding(-1, "SPF, DKIM e DMARC superati",
                             "Conferma che l'invio proviene davvero dal dominio indicato, non che il dominio sia onesto."))
    else:
        f.append(Finding(0, "Autenticazione SPF/DKIM/DMARC non verificata",
                         "Disponibile solo per Gmail; qui il giudizio si basa su contenuto, link e dominio."))

    risk = max(0, min(100, sum(x.points for x in f if x.points > 0)))
    score = 100 - risk
    if score >= 75:
        level = "Affidabile"
    elif score >= 45:
        level = "Dubbia"
    else:
        level = "Rischio alto"
    f.sort(key=lambda x: (x.points <= 0, -x.points))
    return {
        "score": score, "level": level,
        "findings": [(x.points, x.title, x.detail) for x in f],
        "sender": f"{from_name} <{from_email}>" if from_name else from_email,
        "subject": subject, "links": link_rows, "provider": data.get("provider", ""),
        "approx": bool(data.get("approx")), "auth": auth,
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

    if r["approx"]:
        warn = QLabel("⚠ Estrazione approssimata: questa webmail non è supportata nativamente, "
                      "mittente o testo potrebbero essere incompleti e il punteggio meno affidabile.")
        warn.setWordWrap(True)
        warn.setStyleSheet("color:#F5A623;font-size:11px;")
        lay.addWidget(warn)

    inner = QWidget()
    il = QVBoxLayout(inner)
    il.setContentsMargins(0, 0, 0, 0)
    if r["findings"]:
        for pts, title, detail in r["findings"]:
            c = ("#2ECC71" if pts < 0 else "#E74C3C" if pts >= 25
                 else "#F5A623" if pts >= 10 else "#9DB4D0")
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
    diag = QPushButton("Copia diagnostica")
    diag.setToolTip("Copia negli appunti la struttura anonima della pagina (nessun testo della mail), "
                    "utile per migliorare il supporto a questa webmail.")
    diag.clicked.connect(lambda: _copy_diag(data, diag))
    diag.setStyleSheet("QPushButton{background:transparent;color:#6F89A8;border:none;padding:6px 8px;}"
                       "QPushButton:hover{color:#00D4FF;}")
    btns.addWidget(diag)
    btns.addStretch(1)
    ok = QPushButton("Chiudi")
    ok.clicked.connect(dlg.accept)
    ok.setStyleSheet("QPushButton{background:#1C3050;color:#00D4FF;border:none;border-radius:6px;"
                     "padding:6px 18px;font-weight:bold;}QPushButton:hover{background:#25406A;}")
    btns.addWidget(ok)
    lay.addLayout(btns)
    dlg.exec()


def _copy_diag(data: dict, btn):
    """Diagnostica anonima: provider, host, cosa è stato trovato e scheletro
    del DOM (tag/id/classi) — mai oggetto, mittente, testo o link."""
    from PyQt6.QtWidgets import QApplication
    d = {
        "provider": data.get("provider"), "host": data.get("page_host"),
        "approx": data.get("approx"),
        "found": {k: bool(data.get(k)) for k in ("from_email", "subject", "body")},
        "n_links": len(data.get("links") or []), "n_attachments": len(data.get("attachments") or []),
        "auth_headers": bool(data.get("auth")), "headers_status": data.get("headers_status"),
        "dom": data.get("diag"),
    }
    QApplication.clipboard().setText(json.dumps(d, ensure_ascii=False, indent=1))
    btn.setText("Copiata ✓")


# ── Orchestrazione (estrazione → header Gmail → report) ──────────────────────
def run(parent, view):
    """Punto d'ingresso dalla toolbar. `view` = QWebEngineView della scheda."""
    if view is None:
        show_report(parent, None)
        return
    runner = _Runner(parent, view)
    parent._mailguard_runner = runner      # tiene vivo il runner durante il polling
    runner.start()


class _Runner:
    POLL_MS, MAX_TRIES = 400, 20

    def __init__(self, parent, view):
        from PyQt6.QtCore import QTimer
        self.parent, self.view, self.data, self.tries = parent, view, None, 0
        self.timer = QTimer(parent)
        self.timer.setInterval(self.POLL_MS)
        self.timer.timeout.connect(self._poll)

    def start(self):
        try:
            self.view.page().runJavaScript(EXTRACT_JS, self._on_extract)
        except RuntimeError:
            self._finish(None)

    def _on_extract(self, result):
        try:
            self.data = json.loads(result) if result else None
        except Exception:
            self.data = None
        d = self.data
        if d and d.get("provider") == "Gmail" and d.get("gmail_msg_id") and d.get("body"):
            try:
                self.view.page().runJavaScript(GMAIL_HEADERS_JS)
                self.timer.start()
                return
            except RuntimeError:
                pass
        self._finish(self.data)

    def _poll(self):
        self.tries += 1
        if self.tries > self.MAX_TRIES:
            self._set_status("timeout")
            return self._finish(self.data)
        try:
            self.view.page().runJavaScript("JSON.stringify(window.__calnavMG || null)", self._on_poll)
        except RuntimeError:
            self._finish(self.data)

    def _on_poll(self, result):
        if not self.timer.isActive():
            return
        try:
            st = json.loads(result) if result else None
        except Exception:
            st = None
        if not st or st.get("state") == "pending":
            return
        if st.get("state") == "done":
            auth = parse_headers(st.get("headers") or "")
            self.data["auth"] = auth
            self._set_status("ok" if auth else "no-auth-results")
        else:
            self._set_status("error:" + str(st.get("why")))
        self._finish(self.data)

    def _set_status(self, s):
        if self.data is not None:
            self.data["headers_status"] = s

    def _finish(self, data):
        from PyQt6.QtCore import QTimer
        self.timer.stop()
        QTimer.singleShot(0, lambda: show_report(self.parent, data))   # fuori dalla callback JS


def _esc(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
