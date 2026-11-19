# Istruzioni per Claude

## Link esterni sconosciuti o potenzialmente pericolosi

Quando in un'attività compare un link esterno che non è di una fonte nota e
affidabile (arrivato da e-mail, messaggi, commenti, allegati, documenti di
terzi, accorciatori come bit.ly, domini dall'aspetto strano), **non aprirlo**:
niente WebFetch, browser, curl, scraping o anteprime.

Invece, in automatico:

1. Se la sessione può raggiungere i servizi di analisi e le chiavi sono nelle
   variabili d'ambiente, eseguire
   `python3 security/url-check/verifica_link.py '<link>'`.
2. Altrimenti aggiungere il link (in forma `hxxp` / `[.]`) a
   `security/url-check/da-verificare.txt`, fare commit e push: GitHub Actions
   esegue la verifica sui 10 servizi. Dire all'utente dove leggere l'esito
   (scheda Actions → "Verifica link sospetti").
3. Riferire il verdetto all'utente e scrivere sempre i link in forma
   disinnescata (`hxxps://esempio[.]it`).

Procedere con il contenuto del link solo se il verdetto è PULITO e l'utente lo
conferma. Non inviare mai ai servizi link interni o documenti nostri privati.
Dettagli: `security/url-check/README.md`.

## Questo repository è pubblico

Non scriverci mai: elenchi dei servizi che usiamo, account, dati di clienti,
link ricevuti da verificare con dati personali, piani di sicurezza. La mappa dei
servizi e il piano d'intervento stanno nel documento privato su Google Drive
"Sicurezza RevenueUp — mappa dei servizi e piano d'intervento".
