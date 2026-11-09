# Libro della Casa: stato al 09/11/2026

## Il file da stampare

`Il Libro della Casa - stampa definitiva.pdf`, 14 pagine: è la versione generica (la «matrice»).

| Pagina | Cosa | Foglio |
|---|---|---|
| 1 | Scheda di lavorazione, non si stampa | A4 |
| 2 | Copertina, finita 230 × 305 mm | A3 |
| 3 | Inserto interno, 2 copie, 195 × 135 mm | A4 |
| 4 | Dorso, finito 40 × 305 mm | A3 |
| 5–14 | Pagine interne: i testi rivisti il 05/11 (rev. 02) | A4 |

Le pagine interne vengono dal PDF del 05/11 delle 17:21 (chat «Raccoglitore brandizzato»), senza la sua pagina 1
di servizio. Cambiati il 09/11 solo questi testi, con lo stesso carattere, corpo e posizione:

- frontespizio: FAMIGLIA → PROPRIETARIO/A;
- benvenuto: «10 minuti» → «Dieci minuti»; «nel pc o su cloud» → «sul computer o in un cloud»;
- lavori: «cercare da sola» → «cercare da sé»; ultima frase → «Alla pagina successiva può annotare i contatti della rete.»;
- rete di fiducia: «ci contatti per ricevere il contatto adeguato» → «mi chieda il contatto giusto»;
- documenti consegnati: le righe di «Già nel raccoglitore» sono vuote, da scrivere a mano (versione generica).

Lasciate come sono, per scelta del 09/11: le frasi sul mutuo e «agente e mediatore».

## Da fare

- L'inserto interno (pagina 3) è ancora quello di prima del 05/11: se giovedì è stato rivisto anche lui, va sostituito.
- Più avanti: la versione personalizzata per cliente, con i campi già compilati dai documenti della sua cartella.

## Come rifare il PDF

Dalla cartella `strumenti/`: `build.py <sorgente 13 pagine> <uscita> [pagine interne 11 pagine]`, poi
`check.py <uscita> <sorgente> [pagine interne]` (formati, crocini, QR, fili bianchi, pagine identiche).
