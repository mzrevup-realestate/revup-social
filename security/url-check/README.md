# Verifica link sospetti

Quando arriva un link che non conosciamo (e-mail, WhatsApp, commenti sui social,
messaggi di presunti clienti, QR code…) **non lo apriamo**. Lo mandiamo a 10
servizi di analisi che lo controllano nei loro archivi o lo aprono nelle loro
sandbox, e leggiamo il responso.

Le verifiche girano su **GitHub Actions**, cioè sui server di GitHub: né i
nostri computer né i nostri dati entrano in contatto con il link.

## I 10 servizi

| # | Servizio | Cosa fa | Apre la pagina? | Chiave (gratuita) |
|---|---|---|---|---|
| 1 | Google Safe Browsing | Liste di phishing e malware usate da Chrome | No, solo confronto | `GOOGLE_SAFE_BROWSING_KEY` |
| 2 | VirusTotal | Oltre 70 antivirus e motori di reputazione | Solo se il link è nuovo | `VIRUSTOTAL_API_KEY` |
| 3 | urlscan.io | Apre la pagina in sandbox, screenshot, verdetto | Sì, in modalità non elencata | `URLSCAN_API_KEY` |
| 4 | URLhaus (abuse.ch) | Link che distribuiscono malware | No | `ABUSECH_AUTH_KEY` |
| 5 | ThreatFox (abuse.ch) | Domini/IP usati da malware e botnet | No | `ABUSECH_AUTH_KEY` (la stessa) |
| 6 | AlienVault OTX | Segnalazioni di minacce dalla comunità | No | `OTX_API_KEY` |
| 7 | AbuseIPDB | Reputazione del server che ospita il sito | No | `ABUSEIPDB_API_KEY` |
| 8 | Cloudflare Radar URL Scanner | Seconda sandbox con verdetto e screenshot | Sì, in modalità non elencata | `CLOUDFLARE_ACCOUNT_ID` + `CLOUDFLARE_API_TOKEN` |
| 9 | MetaDefender (OPSWAT) | Reputazione del link su più fonti | No | `METADEFENDER_API_KEY` |
| 10 | Sucuri SiteCheck | Malware e blacklist sul sito | Sì | nessuna |

Verdetto finale: basta **un** servizio che dice *malevolo* per avere
🔴 MALEVOLO; un dubbio dà 🟠 SOSPETTO; servono almeno tre risposte pulite per
🟢 PULITO, altrimenti ⚪ SCONOSCIUTO.

## Come si usa

**A. Dal telefono o dal browser (il più comodo)** — apri una *issue* nel
repository con titolo che inizia per `[verifica]` e incolla nel testo il
messaggio sospetto così com'è. Dopo 1–3 minuti arriva un commento con l'esito.
Funziona solo per issue aperte da chi gestisce il repository.

**B. Manuale** — scheda *Actions* → *Verifica link sospetti* → *Run workflow* →
incolla il link.

**C. Coda** — aggiungi il link a `da-verificare.txt` e fai commit: l'esito è nel
riepilogo dell'esecuzione in *Actions*.

**D. In automatico, ogni lunedì** — i domini scritti in `siti-nostri.txt`
vengono controllati; se uno risulta in blacklist o con malware si apre da sola
una issue d'allarme.

**E. Da riga di comando** (su un computer con le chiavi nelle variabili d'ambiente):

```bash
python3 security/url-check/verifica_link.py 'hxxps://sito-strano[.]com/login'
```

I link si possono incollare anche "disinnescati" (`hxxp`, `[.]`). Nei rapporti
vengono sempre mostrati disinnescati, così nessuno li apre per sbaglio.

## Protezione dei nostri dati

- Se il link contiene un indirizzo e-mail o un codice lungo (tipico dei link di
  phishing "personalizzati"), quella parte viene **tolta prima dell'invio**:
  altrimenti la sandbox, aprendolo, direbbe al truffatore che il messaggio è
  stato letto. Per inviarla comunque: `--url-completo`.
- urlscan.io e Cloudflare usano la visibilità *non elencata*.
- Il nome del server viene risolto tramite il DNS di Google, non dal nostro.
- **Mai** usare questo strumento per documenti interni o link condivisi privati
  (Drive, Dropbox, WeTransfer nostri): VirusTotal e gli altri conservano i link
  che ricevono.
- Se il repository è pubblico, anche le issue lo sono: in quel caso usare il
  metodo B o C, oppure rendere privato il repository.

## Configurazione (una volta sola, ~30 minuti)

Registrati gratuitamente su ciascun servizio, copia la chiave e salvala in
GitHub: *Settings → Secrets and variables → Actions → New repository secret*,
con esattamente il nome della tabella.

| Segreto | Dove si ottiene |
|---|---|
| `GOOGLE_SAFE_BROWSING_KEY` | console.cloud.google.com → nuovo progetto → abilita "Safe Browsing API" → Credenziali → Chiave API |
| `VIRUSTOTAL_API_KEY` | virustotal.com → registrati → menu utente → *API key* |
| `URLSCAN_API_KEY` | urlscan.io → registrati → *Settings & API* → *New API key* |
| `ABUSECH_AUTH_KEY` | auth.abuse.ch → accedi → *Optional* → *Generate Key* (vale per URLhaus e ThreatFox) |
| `OTX_API_KEY` | otx.alienvault.com → registrati → *Settings* → *OTX Key* |
| `ABUSEIPDB_API_KEY` | abuseipdb.com → registrati → *Account* → *API* → *Create Key* |
| `CLOUDFLARE_ACCOUNT_ID` / `CLOUDFLARE_API_TOKEN` | dash.cloudflare.com → ID account nella pagina principale; *My Profile → API Tokens → Create Token* con permesso *Account · URL Scanner · Edit* |
| `METADEFENDER_API_KEY` | metadefender.opswat.com → registrati → *Account* → *API key* |

Si può partire anche con poche chiavi: i servizi senza chiave vengono saltati
e il rapporto lo dice. Le versioni gratuite hanno limiti giornalieri
(VirusTotal: 4 richieste al minuto, 500 al giorno) più che sufficienti per un
uso aziendale.

## Cosa fare con l'esito

- 🔴 **MALEVOLO**: non aprire, cancellare il messaggio, avvisare i colleghi che
  potrebbero averlo ricevuto. Se qualcuno ha già cliccato o inserito dati:
  cambiare subito le password interessate e attivare la verifica in due passaggi.
- 🟠 **SOSPETTO**: trattarlo come malevolo finché il mittente non conferma per
  un altro canale (telefono, non rispondendo al messaggio).
- 🟢 **PULITO**: nessuna segnalazione. Un link creato da poche ore può non
  essere ancora in nessuna lista: se il messaggio era comunque strano, meglio
  chiedere conferma al mittente.
