# Libro della Casa: stato al 09/11/2026

## Il PDF in questa cartella ha ancora i TESTI VECCHI

Il PDF composto il 09/11 (tolto da qui perché ha i testi vecchi) aveva l'impaginazione
giusta: copertina 230 × 305 e dorso 40 × 305 su A3, crocini, scheda di lavorazione, controlli superati.
**I testi però sono quelli di prima delle correzioni di giovedì 05/11, verso le 17.** Per esempio a pagina 6:
«un rogito o un APE rovinati sono una seccatura da rifare».

Le correzioni del 05/11 sono state fatte nella **chat dell'app Claude** e non sono mai state salvate su disco.
Non sono nel PDF «Per la Tecnica - 13 pagine», né nel vecchio «file unico per la copisteria»: hanno gli stessi testi.

**Prima di stampare:** copiare qui i testi corretti dalla chat dell'app, in `testi corretti.md`, e rifare il PDF.

## Come rifare il PDF

Dalla cartella `strumenti/`:

    pip install pymupdf reportlab zxing-cpp numpy
    python3 build.py "sorgente/Per la Tecnica - 13 pagine, senza scheda.pdf" "../Il Libro della Casa - stampa definitiva.pdf"
    python3 check.py "../Il Libro della Casa - stampa definitiva.pdf" "sorgente/Per la Tecnica - 13 pagine, senza scheda.pdf"

- `build.py` compone il file: scheda (pag. 1), copertina su A3 (pag. 2), inserto A4 (pag. 3), dorso su A3 (pag. 4),
  pagine interne A4 (5–14).
- `check.py` controlla i formati, i crocini in mm, la lettura del QR, l'assenza di fili bianchi sui tagli e che
  inserto e pagine interne siano identici alla sorgente.
- `sorgente/testi delle pagine interne (versione vecchia).txt` contiene i testi da confrontare con quelli corretti.
- I testi corretti vanno sostituiti nella sorgente (pagine interne), poi si rilancia `build.py`; `check.py` darà
  «DIVERSA» sulle pagine cambiate, ed è giusto così.
