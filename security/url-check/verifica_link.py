#!/usr/bin/env python3
"""Verifica di link sospetti tramite 10 servizi di analisi esterni.

Il link NON viene mai aperto da qui: lo script lo invia ai servizi, che lo
controllano nei loro database o lo aprono nelle loro sandbox, e raccoglie i
responsi in un unico rapporto.

Uso:
    python3 verifica_link.py URL [URL ...]
    python3 verifica_link.py --file elenco.txt
    python3 verifica_link.py --json URL

Solo libreria standard di Python 3.9+. Le chiavi API si leggono dalle
variabili d'ambiente (vedi README.md); i servizi senza chiave vengono saltati.

Codice di uscita: 0 nessun problema, 1 sospetto, 2 malevolo.
"""

from __future__ import annotations

import argparse
import base64
import ipaddress
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field

UA = "verifica-link/1.0"
TIMEOUT = 25

MALEVOLO, SOSPETTO, PULITO, SCONOSCIUTO, SALTATO, ERRORE = (
    "MALEVOLO", "SOSPETTO", "PULITO", "SCONOSCIUTO", "SALTATO", "ERRORE",
)
ICONE = {MALEVOLO: "🔴", SOSPETTO: "🟠", PULITO: "🟢", SCONOSCIUTO: "⚪", SALTATO: "⏭️", ERRORE: "⚠️"}


@dataclass
class Esito:
    servizio: str
    verdetto: str
    dettaglio: str = ""
    link_rapporto: str = ""


@dataclass
class Rapporto:
    url_originale: str  # solo uso locale, non finisce nel rapporto Markdown
    url_inviato: str
    dominio: str
    ip: list = field(default_factory=list)
    note: list = field(default_factory=list)
    esiti: list = field(default_factory=list)
    verdetto: str = SCONOSCIUTO


# --------------------------------------------------------------------------- HTTP

def http(method, url, headers=None, json_body=None, form=None, timeout=TIMEOUT):
    """Ritorna (status, corpo decodificato da JSON se possibile)."""
    headers = {"User-Agent": UA, "Accept": "application/json", **(headers or {})}
    data = None
    if json_body is not None:
        data = json.dumps(json_body).encode()
        headers["Content-Type"] = "application/json"
    elif form is not None:
        data = urllib.parse.urlencode(form).encode()
        headers["Content-Type"] = "application/x-www-form-urlencoded"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            status, raw = r.status, r.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    try:
        return status, json.loads(raw.decode("utf-8", "replace"))
    except ValueError:
        return status, raw.decode("utf-8", "replace")[:500]


def env(nome):
    v = os.environ.get(nome, "").strip()
    return v or None


# ------------------------------------------------------------- preparazione link

def rifanga(testo: str) -> str:
    """Rende un link non cliccabile per i rapporti (hxxps://esempio[.]it)."""
    testo = re.sub(r"^http", "hxxp", testo, flags=re.I)
    return testo.replace(".", "[.]").replace("://", "[://]")


def normalizza(grezzo: str) -> str:
    """Accetta anche link già 'disinnescati' (hxxp, [.], (.) ...)."""
    u = grezzo.strip().strip("<>\"'")
    u = re.sub(r"^hxxp", "http", u, flags=re.I)
    u = u.replace("[.]", ".").replace("(.)", ".").replace("[:]", ":").replace("[://]", "://")
    if not re.match(r"^[a-z][a-z0-9+.-]*://", u, re.I):
        u = "http://" + u
    return u


TOKEN_RE = re.compile(r"[A-Za-z0-9_\-]{20,}")
EMAIL_RE = re.compile(r"[^@\s/=&]+(@|%40)[^@\s/=&]+\.[a-z]{2,}", re.I)


def proteggi(url: str, completo: bool):
    """Toglie query e frammento quando sembrano identificare il destinatario.

    I link di phishing spesso contengono la mail o un codice personale: inviarli
    interi a un servizio che li apre direbbe al mittente che il messaggio è
    stato letto, e renderebbe pubblici i nostri dati.
    """
    p = urllib.parse.urlsplit(url)
    if completo or not (p.query or p.fragment):
        return url, None
    coda = urllib.parse.unquote(p.query + "#" + p.fragment)
    if EMAIL_RE.search(coda) or TOKEN_RE.search(coda):
        pulito = urllib.parse.urlunsplit((p.scheme, p.netloc, p.path, "", ""))
        return pulito, ("Parametri rimossi prima dell'invio: contenevano un indirizzo e-mail o un "
                        "codice che potrebbe identificarci. Usa --url-completo per inviarli.")
    return url, None


def risolvi_ip(dominio: str):
    """Risoluzione DNS tramite DNS-over-HTTPS di Google: la domanda al server
    dell'attaccante parte da Google, non da noi."""
    try:
        ipaddress.ip_address(dominio)
        return [dominio]
    except ValueError:
        pass
    try:
        st, js = http("GET", "https://dns.google/resolve?" + urllib.parse.urlencode({"name": dominio, "type": "A"}))
    except OSError:
        return []
    if st != 200 or not isinstance(js, dict):
        return []
    return [a["data"] for a in js.get("Answer", []) if a.get("type") == 1][:3]


def attendi(fn, secondi=90, passo=6):
    """Ripete fn() finché non restituisce qualcosa di diverso da None."""
    fine = time.time() + secondi
    while time.time() < fine:
        r = fn()
        if r is not None:
            return r
        time.sleep(passo)
    return None


# ------------------------------------------------------------------- 10 servizi

def google_safe_browsing(r: Rapporto) -> Esito:
    nome = "Google Safe Browsing"
    key = env("GOOGLE_SAFE_BROWSING_KEY")
    if not key:
        return Esito(nome, SALTATO, "manca GOOGLE_SAFE_BROWSING_KEY")
    body = {
        "client": {"clientId": "verifica-link", "clientVersion": "1.0"},
        "threatInfo": {
            "threatTypes": ["MALWARE", "SOCIAL_ENGINEERING", "UNWANTED_SOFTWARE",
                            "POTENTIALLY_HARMFUL_APPLICATION"],
            "platformTypes": ["ANY_PLATFORM"],
            "threatEntryTypes": ["URL"],
            "threatEntries": [{"url": r.url_inviato}],
        },
    }
    st, js = http("POST", "https://safebrowsing.googleapis.com/v4/threatMatches:find?key=" + key, json_body=body)
    if st != 200:
        return Esito(nome, ERRORE, f"HTTP {st}")
    matches = js.get("matches", []) if isinstance(js, dict) else []
    if matches:
        tipi = sorted({m.get("threatType", "?") for m in matches})
        return Esito(nome, MALEVOLO, "segnalato come " + ", ".join(tipi))
    return Esito(nome, PULITO, "non presente nelle liste di Google")


def virustotal(r: Rapporto) -> Esito:
    nome = "VirusTotal"
    key = env("VIRUSTOTAL_API_KEY")
    if not key:
        return Esito(nome, SALTATO, "manca VIRUSTOTAL_API_KEY")
    h = {"x-apikey": key}
    uid = base64.urlsafe_b64encode(r.url_inviato.encode()).decode().rstrip("=")
    link = f"https://www.virustotal.com/gui/url/{uid}"
    st, js = http("GET", f"https://www.virustotal.com/api/v3/urls/{uid}", h)
    stats = None
    if st == 200:
        stats = js["data"]["attributes"].get("last_analysis_stats")
    elif st == 404:  # mai visto: lo inviamo per l'analisi
        st, js = http("POST", "https://www.virustotal.com/api/v3/urls", h, form={"url": r.url_inviato})
        if st != 200:
            return Esito(nome, ERRORE, f"invio fallito, HTTP {st}", link)
        aid = js["data"]["id"]

        def pronto():
            s, j = http("GET", f"https://www.virustotal.com/api/v3/analyses/{aid}", h)
            if s == 200 and j["data"]["attributes"].get("status") == "completed":
                return j["data"]["attributes"]["stats"]
            return None

        stats = attendi(pronto, 120, 10)
        if stats is None:
            return Esito(nome, SCONOSCIUTO, "analisi ancora in corso, riprova tra qualche minuto", link)
    else:
        return Esito(nome, ERRORE, f"HTTP {st}", link)
    mal, sus = stats.get("malicious", 0), stats.get("suspicious", 0)
    tot = sum(v for v in stats.values() if isinstance(v, int))
    det = f"{mal} motori su {tot} lo danno malevolo, {sus} sospetto"
    if mal >= 2:
        return Esito(nome, MALEVOLO, det, link)
    if mal == 1 or sus >= 1:
        return Esito(nome, SOSPETTO, det, link)
    return Esito(nome, PULITO, det, link)


def urlscan(r: Rapporto) -> Esito:
    nome = "urlscan.io"
    key = env("URLSCAN_API_KEY")
    if not key:
        return Esito(nome, SALTATO, "manca URLSCAN_API_KEY")
    h = {"API-Key": key}
    st, js = http("POST", "https://urlscan.io/api/v1/scan/", h,
                  json_body={"url": r.url_inviato, "visibility": "unlisted", "tags": ["verifica-link"]})
    if st != 200:
        msg = js.get("message", "") if isinstance(js, dict) else ""
        return Esito(nome, ERRORE, f"HTTP {st} {msg}".strip())
    uuid = js["uuid"]
    link = f"https://urlscan.io/result/{uuid}/"

    def pronto():
        s, j = http("GET", f"https://urlscan.io/api/v1/result/{uuid}/", h)
        return j if s == 200 else None

    res = attendi(pronto, 90, 8)
    if res is None:
        return Esito(nome, SCONOSCIUTO, "scansione non terminata in tempo", link)
    ov = res.get("verdicts", {}).get("overall", {})
    cat = ", ".join(ov.get("categories", []) or ov.get("brands", []) or [])
    if ov.get("malicious"):
        return Esito(nome, MALEVOLO, f"punteggio {ov.get('score')} {cat}".strip(), link)
    if (ov.get("score") or 0) > 0:
        return Esito(nome, SOSPETTO, f"punteggio {ov.get('score')} {cat}".strip(), link)
    return Esito(nome, PULITO, "pagina aperta in sandbox, nessun verdetto negativo (screenshot nel rapporto)", link)


def urlhaus(r: Rapporto) -> Esito:
    nome = "URLhaus (abuse.ch)"
    key = env("ABUSECH_AUTH_KEY")
    if not key:
        return Esito(nome, SALTATO, "manca ABUSECH_AUTH_KEY")
    h = {"Auth-Key": key}
    st, js = http("POST", "https://urlhaus-api.abuse.ch/v1/url/", h, form={"url": r.url_inviato})
    if st != 200 or not isinstance(js, dict):
        return Esito(nome, ERRORE, f"HTTP {st}")
    if js.get("query_status") == "ok":
        return Esito(nome, MALEVOLO, f"link di distribuzione malware ({js.get('threat')}, stato {js.get('url_status')})",
                     js.get("urlhaus_reference", ""))
    st, js = http("POST", "https://urlhaus-api.abuse.ch/v1/host/", h, form={"host": r.dominio})
    if st == 200 and isinstance(js, dict) and js.get("query_status") == "ok":
        return Esito(nome, SOSPETTO, f"il dominio ha ospitato {js.get('url_count')} link malevoli",
                     js.get("urlhaus_reference", ""))
    return Esito(nome, PULITO, "né il link né il dominio sono in elenco")


def threatfox(r: Rapporto) -> Esito:
    nome = "ThreatFox (abuse.ch)"
    key = env("ABUSECH_AUTH_KEY")
    if not key:
        return Esito(nome, SALTATO, "manca ABUSECH_AUTH_KEY")
    trovati = []
    for termine in [r.dominio, *r.ip]:
        st, js = http("POST", "https://threatfox-api.abuse.ch/api/v1/", {"Auth-Key": key},
                      json_body={"query": "search_ioc", "search_term": termine})
        if st != 200 or not isinstance(js, dict):
            return Esito(nome, ERRORE, f"HTTP {st}")
        if js.get("query_status") == "ok" and isinstance(js.get("data"), list):
            trovati += js["data"]
    if trovati:
        fam = sorted({d.get("malware_printable", "?") for d in trovati})
        return Esito(nome, MALEVOLO, "indicatore di compromissione noto: " + ", ".join(fam),
                     "https://threatfox.abuse.ch/ioc/%s/" % trovati[0].get("id"))
    return Esito(nome, PULITO, "nessun indicatore noto per dominio/IP")


def alienvault_otx(r: Rapporto) -> Esito:
    nome = "AlienVault OTX"
    key = env("OTX_API_KEY")
    if not key:
        return Esito(nome, SALTATO, "manca OTX_API_KEY")
    try:
        ipaddress.ip_address(r.dominio)
        tipo = "IPv4"
    except ValueError:
        tipo = "domain"
    st, js = http("GET", f"https://otx.alienvault.com/api/v1/indicators/{tipo}/{r.dominio}/general",
                  {"X-OTX-API-KEY": key})
    link = f"https://otx.alienvault.com/indicator/{tipo.lower()}/{r.dominio}"
    if st != 200 or not isinstance(js, dict):
        return Esito(nome, ERRORE, f"HTTP {st}", link)
    n = js.get("pulse_info", {}).get("count", 0)
    if js.get("validation"):  # domini noti e affidabili (es. in whitelist)
        return Esito(nome, PULITO, f"dominio in whitelist ({n} segnalazioni ignorate)", link)
    if n >= 3:
        return Esito(nome, MALEVOLO, f"citato in {n} segnalazioni di minacce", link)
    if n:
        return Esito(nome, SOSPETTO, f"citato in {n} segnalazioni di minacce", link)
    return Esito(nome, PULITO, "nessuna segnalazione", link)


def abuseipdb(r: Rapporto) -> Esito:
    nome = "AbuseIPDB"
    key = env("ABUSEIPDB_API_KEY")
    if not key:
        return Esito(nome, SALTATO, "manca ABUSEIPDB_API_KEY")
    if not r.ip:
        return Esito(nome, SCONOSCIUTO, "il dominio non risolve a nessun IP")
    peggiore, det = 0, []
    for ip in r.ip:
        st, js = http("GET", "https://api.abuseipdb.com/api/v2/check?" +
                      urllib.parse.urlencode({"ipAddress": ip, "maxAgeInDays": 90}), {"Key": key})
        if st != 200 or not isinstance(js, dict):
            return Esito(nome, ERRORE, f"HTTP {st}")
        d = js["data"]
        peggiore = max(peggiore, d.get("abuseConfidenceScore", 0))
        det.append(f"{ip}: {d.get('abuseConfidenceScore')}% ({d.get('totalReports')} segnalazioni, {d.get('countryCode')})")
    link = f"https://www.abuseipdb.com/check/{r.ip[0]}"
    v = MALEVOLO if peggiore >= 50 else SOSPETTO if peggiore >= 15 else PULITO
    return Esito(nome, v, "; ".join(det), link)


def cloudflare_radar(r: Rapporto) -> Esito:
    nome = "Cloudflare Radar"
    acc, tok = env("CLOUDFLARE_ACCOUNT_ID"), env("CLOUDFLARE_API_TOKEN")
    if not (acc and tok):
        return Esito(nome, SALTATO, "mancano CLOUDFLARE_ACCOUNT_ID / CLOUDFLARE_API_TOKEN")
    h = {"Authorization": "Bearer " + tok}
    base = f"https://api.cloudflare.com/client/v4/accounts/{acc}/urlscanner/v2"
    st, js = http("POST", base + "/scan", h, json_body={"url": r.url_inviato, "visibility": "Unlisted"})
    if st not in (200, 201) or not isinstance(js, dict) or "uuid" not in js:
        return Esito(nome, ERRORE, f"HTTP {st}")
    uuid = js["uuid"]
    link = f"https://radar.cloudflare.com/scan/{uuid}"

    def pronto():
        s, j = http("GET", f"{base}/result/{uuid}", h)
        return j if s == 200 else None

    res = attendi(pronto, 90, 8)
    if res is None:
        return Esito(nome, SCONOSCIUTO, "scansione non terminata in tempo", link)
    ov = res.get("verdicts", {}).get("overall", {})
    cat = ", ".join(c.get("name", "") if isinstance(c, dict) else str(c) for c in ov.get("categories", []))
    if ov.get("malicious"):
        return Esito(nome, MALEVOLO, cat or "pagina giudicata malevola", link)
    return Esito(nome, PULITO, "pagina aperta in sandbox, nessun verdetto negativo", link)


def metadefender(r: Rapporto) -> Esito:
    nome = "MetaDefender (OPSWAT)"
    key = env("METADEFENDER_API_KEY")
    if not key:
        return Esito(nome, SALTATO, "manca METADEFENDER_API_KEY")
    st, js = http("GET", "https://api.metadefender.com/v4/url/" + urllib.parse.quote(r.url_inviato, safe=""),
                  {"apikey": key})
    if st != 200 or not isinstance(js, dict):
        return Esito(nome, ERRORE, f"HTTP {st}")
    lr = js.get("lookup_results", {})
    n = lr.get("detected_by", 0)
    fonti = [s.get("provider", "?") for s in lr.get("sources", []) if s.get("assessment")]
    if n >= 2:
        return Esito(nome, MALEVOLO, f"rilevato da {n} fonti: " + ", ".join(fonti))
    if n == 1:
        return Esito(nome, SOSPETTO, "rilevato da 1 fonte: " + ", ".join(fonti))
    return Esito(nome, PULITO, f"nessuna delle {len(lr.get('sources', []))} fonti lo segnala")


def sucuri_sitecheck(r: Rapporto) -> Esito:
    nome = "Sucuri SiteCheck"
    if env("SUCURI_DISABILITATO"):
        return Esito(nome, SALTATO, "disabilitato")
    link = f"https://sitecheck.sucuri.net/results/{r.dominio}"
    st, js = http("GET", "https://sitecheck.sucuri.net/api/v3/?" + urllib.parse.urlencode({"scan": r.dominio}),
                  timeout=60)
    if st != 200 or not isinstance(js, dict):
        return Esito(nome, ERRORE, f"HTTP {st} (servizio senza chiave, a volte limitato)", link)
    warn = js.get("warnings", {}) or {}
    malware = (warn.get("security", {}) or {}).get("malware") if isinstance(warn, dict) else None
    liste = [b for b in js.get("blacklists", []) or [] if isinstance(b, dict)]
    if malware:
        return Esito(nome, MALEVOLO, f"malware trovato sul sito ({len(malware)} elementi)", link)
    if liste:
        return Esito(nome, MALEVOLO, "in blacklist: " + ", ".join(b.get("vendor", "?") for b in liste), link)
    if warn:
        return Esito(nome, SOSPETTO, "avvisi di sicurezza: " + ", ".join(warn.keys()), link)
    return Esito(nome, PULITO, "nessun malware né blacklist", link)


SERVIZI = [google_safe_browsing, virustotal, urlscan, urlhaus, threatfox,
           alienvault_otx, abuseipdb, cloudflare_radar, metadefender, sucuri_sitecheck]


# ---------------------------------------------------------------------- analisi

def analizza(grezzo: str, completo: bool = False) -> Rapporto:
    url = normalizza(grezzo)
    inviato, nota = proteggi(url, completo)
    dominio = (urllib.parse.urlsplit(inviato).hostname or "").lower()
    r = Rapporto(grezzo, inviato, dominio)
    if nota:
        r.note.append(nota)
    if not dominio:
        r.note.append("Link non valido.")
        return r
    r.ip = risolvi_ip(dominio)

    def sicuro(fn):
        try:
            return fn(r)
        except Exception as e:  # un servizio rotto non deve fermare gli altri
            return Esito(fn.__name__.replace("_", " ").title(), ERRORE, f"{type(e).__name__}: {e}"[:200])

    with ThreadPoolExecutor(len(SERVIZI)) as ex:
        r.esiti = list(ex.map(sicuro, SERVIZI))
    v = [e.verdetto for e in r.esiti]
    if MALEVOLO in v:
        r.verdetto = MALEVOLO
    elif SOSPETTO in v:
        r.verdetto = SOSPETTO
    elif v.count(PULITO) >= 3:
        r.verdetto = PULITO
    return r


GIUDIZIO = {
    MALEVOLO: "**NON aprire il link.** Cancella il messaggio e, se lo hai già aperto o hai inserito dati, cambia subito le password coinvolte.",
    SOSPETTO: "**Non aprire il link** finché non è chiarito: almeno un servizio ha dei dubbi.",
    PULITO: "Nessun servizio segnala problemi. Resta prudente: un link nuovissimo può non essere ancora in nessuna lista.",
    SCONOSCIUTO: "Troppi pochi servizi hanno risposto per dare un giudizio: configura altre chiavi o riprova.",
}


def markdown(r: Rapporto) -> str:
    # Si mostra il link come inviato ai servizi: senza eventuali dati personali
    out = [f"### {ICONE[r.verdetto]} {r.verdetto} — `{rifanga(r.url_inviato)}`", "",
           GIUDIZIO[r.verdetto], ""]
    out.append(f"- Dominio: `{rifanga(r.dominio)}` · IP: {', '.join(r.ip) or 'nessuno'}")
    out += [f"- ℹ️ {n}" for n in r.note]
    out += ["", "| Servizio | Esito | Dettaglio | Rapporto |", "|---|---|---|---|"]
    for e in r.esiti:
        det = e.dettaglio.replace("|", "/")
        rap = f"[apri]({e.link_rapporto})" if e.link_rapporto else ""
        out.append(f"| {e.servizio} | {ICONE[e.verdetto]} {e.verdetto} | {det} | {rap} |")
    return "\n".join(out) + "\n"


def leggi_elenco(percorso):
    with open(percorso, encoding="utf-8") as f:
        return [l.strip() for l in f if l.strip() and not l.lstrip().startswith("#")]


URL_RE = re.compile(r"(?:h[tx]{2}ps?(?:\[?://\]?|://)|www\.)[^\s<>\"'`)\]|]+", re.I)


def estrai_link(testo: str):
    testo = (testo or "").replace("[.]", ".").replace("(.)", ".").replace("[://]", "://").replace("[:]", ":")
    visti = []
    for m in URL_RE.findall(testo):
        m = m.rstrip(".,;:")
        if m not in visti:
            visti.append(m)
    return visti


def main():
    ap = argparse.ArgumentParser(description="Verifica link sospetti senza aprirli.")
    ap.add_argument("url", nargs="*", help="link da verificare (anche in forma hxxp / [.])")
    ap.add_argument("--file", help="file con un link per riga (# per i commenti)")
    ap.add_argument("--testo-da-env", metavar="VAR",
                    help="estrae i link dal testo contenuto nella variabile d'ambiente VAR")
    ap.add_argument("--url-completo", action="store_true",
                    help="invia anche parametri che sembrano personali (sconsigliato)")
    ap.add_argument("--json", action="store_true", help="output JSON invece che Markdown")
    ap.add_argument("--max", type=int, default=10, help="numero massimo di link per esecuzione")
    a = ap.parse_args()

    links = list(a.url)
    if a.file:
        links += leggi_elenco(a.file)
    if a.testo_da_env:
        links += estrai_link(os.environ.get(a.testo_da_env, ""))
    links = links[: a.max]
    if not links:
        print("Nessun link da verificare.")
        return 0

    rapporti = [analizza(l, a.url_completo) for l in links]
    if a.json:
        print(json.dumps([asdict(r) for r in rapporti], ensure_ascii=False, indent=2))
    else:
        print("\n".join(markdown(r) for r in rapporti))
    v = {r.verdetto for r in rapporti}
    return 2 if MALEVOLO in v else 1 if SOSPETTO in v else 0


if __name__ == "__main__":
    sys.exit(main())
