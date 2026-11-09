import sys, io, os
import pymupdf as fitz
from reportlab.pdfgen import canvas
from reportlab.lib.units import mm as RMM
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.lib.colors import HexColor

S = os.path.dirname(os.path.abspath(__file__))
SRC = sys.argv[1]
OUT = sys.argv[2]
F = S + "/fonts"
MM = 72 / 25.4
A3W, A3H = 297, 420
BLEED = 3.0
DARK = (0.1254899948835373, 0.09019599854946136, 0.1647060066461563)  # fondo della grafica originale
MARK_OFF, MARK_LEN, MARK_W = 5.0, 10.0, 0.6  # crocini: da 5 a 15 mm fuori dal taglio, 0,6 pt

src = fitz.open(SRC)
assert src.page_count == 13


def R(x0, y0, x1, y1):
    return fitz.Rect(x0 * MM, y0 * MM, x1 * MM, y1 * MM)


def strip_image(page, bbox_mm_y, x_range):
    """Restituisce l'immagine inline del gradiente nel punto indicato."""
    for b in page.get_text("dict")["blocks"]:
        if b["type"] == 1:
            x0, y0, x1, y1 = [v / MM for v in b["bbox"]]
            if abs(y0 - bbox_mm_y) < 0.3 and x_range[0] - 1 < x0 < x_range[0] + 1:
                pix = fitz.Pixmap(b["image"])
                if pix.alpha or pix.n != 3:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                import numpy as np
                a = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)
                print("  righe del gradiente identiche:", all((a[i] == a[0]).all() for i in range(pix.h)), pix.w, "x", pix.h)
                return pix.tobytes("png"), (x0, y0, x1, y1)
    raise RuntimeError("gradiente non trovato")


def cleaned(src, pno, clip_mm):
    """Copia della pagina sorgente senza quello che sta fuori dal ritaglio
    (crocini vecchi, didascalie con le misure vecchie, le altre strisce del dorso)."""
    cx0, cy0, cx1, cy1 = clip_mm
    tmp = fitz.open()
    tmp.insert_pdf(src, from_page=pno, to_page=pno)
    pg = tmp[0]
    W, H = pg.rect.width / MM, pg.rect.height / MM
    for r in ((0, 0, W, cy0), (0, cy1, W, H), (0, 0, cx0, H), (cx1, 0, W, H)):
        pg.add_redact_annot(R(*r), fill=False)
    pg.apply_redactions(images=fitz.PDF_REDACT_IMAGE_REMOVE,
                        graphics=fitz.PDF_REDACT_LINE_ART_REMOVE_IF_TOUCHED,
                        text=fitz.PDF_REDACT_TEXT_REMOVE)
    return tmp


def crop_marks(page, tx0, ty0, tx1, ty1):
    sh = page.new_shape()
    for x in (tx0, tx1):
        sh.draw_line(fitz.Point(x * MM, (ty0 - MARK_OFF - MARK_LEN) * MM), fitz.Point(x * MM, (ty0 - MARK_OFF) * MM))
        sh.draw_line(fitz.Point(x * MM, (ty1 + MARK_OFF) * MM), fitz.Point(x * MM, (ty1 + MARK_OFF + MARK_LEN) * MM))
    for y in (ty0, ty1):
        sh.draw_line(fitz.Point((tx0 - MARK_OFF - MARK_LEN) * MM, y * MM), fitz.Point((tx0 - MARK_OFF) * MM, y * MM))
        sh.draw_line(fitz.Point((tx1 + MARK_OFF) * MM, y * MM), fitz.Point((tx1 + MARK_OFF + MARK_LEN) * MM, y * MM))
    sh.finish(color=(0, 0, 0), width=MARK_W, lineCap=0, closePath=False)
    sh.commit()


def label(page, text, y_mm):
    page.insert_font(fontname="MonM", fontfile=F + "/Montserrat-Medium.ttf")
    fs = 8
    w = fitz.get_text_length(text, fontname="helv", fontsize=fs)  # solo per stima
    font = fitz.Font(fontfile=F + "/Montserrat-Medium.ttf")
    w = font.text_length(text, fontsize=fs)
    page.insert_text(fitz.Point((A3W * MM - w) / 2, y_mm * MM), text, fontname="MonM", fontsize=fs, color=(0.35, 0.35, 0.38))


def a3_piece(out, src_pno, clip_mm, fin_w, fin_h, scale_by, line_y_src, label_text):
    cx0, cy0, cx1, cy1 = clip_mm
    cw, ch = cx1 - cx0, cy1 - cy0
    s = fin_h / ch if scale_by == "h" else fin_w / cw
    gw, gh = cw * s, ch * s
    tx0, ty0 = (A3W - fin_w) / 2, (A3H - fin_h) / 2
    tx1, ty1 = tx0 + fin_w, ty0 + fin_h
    gx0, gy0 = tx0 + (fin_w - gw) / 2, ty0 + (fin_h - gh) / 2
    p = out.new_page(width=A3W * MM, height=A3H * MM)
    # fondo scuro su tutto il pezzo + 3 mm di margine per lato
    p.draw_rect(R(tx0 - BLEED, ty0 - BLEED, tx1 + BLEED, ty1 + BLEED), color=None, fill=DARK, overlay=True)
    # grafica originale, ingrandita in proporzione
    p.show_pdf_page(R(gx0, gy0, gx0 + gw, gy0 + gh), cleaned(src, src_pno, clip_mm), 0, clip=R(cx0, cy0, cx1, cy1), keep_proportion=True)
    # cornice di fondo scuro sopra il bordo del ritaglio (0,5 mm dentro la grafica, dove c'è solo fondo):
    # toglie il filo chiaro che l'antialiasing lascia sul bordo della pagina originale
    I = 0.5
    bx0, by0, bx1, by1 = tx0 - BLEED, ty0 - BLEED, tx1 + BLEED, ty1 + BLEED
    for r in ((bx0, by0, bx1, gy0 + I), (bx0, gy0 + gh - I, bx1, by1),
              (bx0, by0, gx0 + I, by1), (gx0 + gw - I, by0, bx1, by1)):
        p.draw_rect(R(*r), color=None, fill=DARK, overlay=True)
    # gradiente da bordo a bordo, margine compreso
    png, (lx0, ly0, lx1, ly1) = strip_image(src[src_pno], line_y_src, (cx0, cx1))
    ny0 = gy0 + (ly0 - cy0) * s
    ny1 = gy0 + (ly1 - cy0) * s
    p.insert_image(R(tx0 - BLEED, ny0, tx1 + BLEED, ny1), stream=png, keep_proportion=False, overlay=True)
    crop_marks(p, tx0, ty0, tx1, ty1)
    label(p, label_text, ty0 - MARK_OFF - MARK_LEN - 6)
    return dict(scale=s, graphic=(gx0, gy0, gx0 + gw, gy0 + gh), trim=(tx0, ty0, tx1, ty1), line=(ny0, ny1))


# ---------- scheda di lavorazione (reportlab, Montserrat) ----------
def scheda_pdf():
    for w in ("Regular", "Medium", "SemiBold", "Bold"):
        pdfmetrics.registerFont(TTFont("Mont-" + w, f"{F}/Montserrat-{w}.ttf"))
    NAVY = HexColor("#1B2A4A")
    NAVY2 = HexColor("#2E3F63")
    GOLD = HexColor("#C9A24A")
    GOLDL = HexColor("#F6EFDD")
    INK = HexColor("#1F2433")
    GREY = HexColor("#5A6070")
    W, H = 210 * RMM, 297 * RMM
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=(W, H))
    c.setTitle("Il Libro della Casa - stampa definitiva")
    L = 16 * RMM
    RR = W - 16 * RMM

    # testata
    c.setFillColor(NAVY); c.rect(0, H - 30 * RMM, W, 30 * RMM, stroke=0, fill=1)
    c.setFillColor(GOLD); c.rect(0, H - 31.2 * RMM, W, 1.2 * RMM, stroke=0, fill=1)
    c.setFillColor(HexColor("#FFFFFF")); c.setFont("Mont-Bold", 17)
    c.drawString(L, H - 17 * RMM, "SCHEDA DI LAVORAZIONE")
    c.setFillColor(GOLD); c.setFont("Mont-SemiBold", 9)
    c.drawRightString(RR, H - 17 * RMM, "Questa pagina non si stampa")
    c.setFillColor(HexColor("#C9CFDC")); c.setFont("Mont-Regular", 8.5)
    c.drawString(L, H - 24 * RMM, "Il Libro della Casa · Rev(enue)Up · file di 14 pagine")

    y = H - 44 * RMM
    c.setFillColor(NAVY); c.setFont("Mont-Bold", 14)
    c.drawString(L, y, "Il Libro della Casa: stampa definitiva")
    y -= 6.5 * RMM
    c.setFillColor(INK); c.setFont("Mont-Regular", 9.5)
    c.drawString(L, y, "Stampare le pagine da 2 a 14 di questo PDF. La pagina 1 (questa) non si stampa.")

    # riquadri chiave
    y -= 7 * RMM
    boxes = [("COPIE", "1"), ("STAMPA", "A colori, solo fronte"), ("SCALA", "100%, senza adattare"), ("PAGINE", "Da 2 a 14")]
    gap = 3 * RMM
    bw = (RR - L - 3 * gap) / 4
    bh = 17 * RMM
    for i, (k, v) in enumerate(boxes):
        x = L + i * (bw + gap)
        c.setFillColor(GOLDL); c.rect(x, y - bh, bw, bh, stroke=0, fill=1)
        c.setFillColor(GOLD); c.rect(x, y - bh, 1.2 * RMM, bh, stroke=0, fill=1)
        c.setFillColor(GREY); c.setFont("Mont-SemiBold", 7)
        c.drawString(x + 4 * RMM, y - 5.5 * RMM, k)
        c.setFillColor(NAVY); c.setFont("Mont-Bold", 10)
        c.drawString(x + 4 * RMM, y - 12 * RMM, v)
    y -= bh + 8 * RMM

    # tabella pagine
    cols = [("PAG.", 12), ("CONTENUTO", 40), ("FOGLIO", 16), ("SUPPORTO", 32), ("LAVORAZIONE", 38), ("MISURA FINITA", 40)]
    tw = sum(w for _, w in cols)
    sc = (RR - L) / (tw * RMM)
    xs = [L]
    for _, w in cols:
        xs.append(xs[-1] + w * RMM * sc)
    hh = 8 * RMM
    c.setFillColor(NAVY); c.rect(L, y - hh, RR - L, hh, stroke=0, fill=1)
    c.setFillColor(GOLD); c.setFont("Mont-SemiBold", 7.5)
    for i, (k, _) in enumerate(cols):
        c.drawString(xs[i] + 2.5 * RMM, y - 5.2 * RMM, k)
    y -= hh
    rows = [
        ("2", ["Copertina"], ["A3"], ["Cartoncino opaco", "200 g"], ["Taglio sui crocini"], ["230 × 305 mm"]),
        ("3", ["Inserto interno,", "2 copie sul foglio"], ["A4"], ["Cartoncino opaco", "200 g"], ["Taglio sui crocini"], ["2 pezzi da", "195 × 135 mm"]),
        ("4", ["Dorso"], ["A3"], ["Cartoncino opaco", "200 g"], ["Taglio sui crocini"], ["40 × 305 mm"]),
        ("5–14", ["Pagine interne,", "10 fogli"], ["A4"], ["Carta opaca", "120 g"], ["Nessun taglio,", "4 fori a sinistra"], ["A4, 210 × 297 mm"]),
    ]
    rh = 13 * RMM
    for ri, row in enumerate(rows):
        if ri % 2 == 1:
            c.setFillColor(HexColor("#F3F4F8")); c.rect(L, y - rh, RR - L, rh, stroke=0, fill=1)
        c.setFillColor(NAVY); c.setFont("Mont-Bold", 11)
        c.drawString(xs[0] + 2.5 * RMM, y - 7.6 * RMM, row[0])
        for ci, cell in enumerate(row[1:], start=1):
            bold = ci in (2, 5)
            c.setFont("Mont-SemiBold" if bold else "Mont-Regular", 8.6)
            c.setFillColor(NAVY if bold else INK)
            n = len(cell)
            y0 = y - rh / 2 + (n - 1) * 1.9 * RMM - 1.1 * RMM
            for li, t in enumerate(cell):
                c.drawString(xs[ci] + 2.5 * RMM, y0 - li * 3.8 * RMM, t)
        y -= rh
        c.setStrokeColor(HexColor("#D9DCE5")); c.setLineWidth(0.5); c.line(L, y, RR, y)
    y -= 9 * RMM

    def section(title, items, y):
        c.setFillColor(NAVY); c.setFont("Mont-Bold", 10.5)
        c.drawString(L, y, title)
        c.setFillColor(GOLD); c.rect(L, y - 2.4 * RMM, 14 * RMM, 0.8 * RMM, stroke=0, fill=1)
        y -= 7.5 * RMM
        for it in items:
            c.setFillColor(GOLD); c.circle(L + 1.2 * RMM, y + 1.1 * RMM, 0.9 * RMM, stroke=0, fill=1)
            for li, (t, font) in enumerate(it):
                c.setFillColor(INK); c.setFont(font, 9)
                c.drawString(L + 5 * RMM, y - li * 4.4 * RMM, t)
            y -= (len(it) * 4.4 + 2.2) * RMM
        return y - 4 * RMM

    R_, B_ = "Mont-Regular", "Mont-SemiBold"
    y = section("Copertina e dorso (pagine 2 e 4): fogli A3", [
        [("Stampare su A3 verticale (297 × 420 mm), al 100%, su cartoncino opaco 200 g.", R_)],
        [("Tagliare sui crocini: copertina finita 230 × 305 mm, dorso finito 40 × 305 mm.", B_)],
        [("Il fondo scuro continua 3 mm oltre il taglio su ogni lato.", R_)],
    ], y)
    y = section("Inserto interno (pagina 3): foglio A4", [
        [("Sul foglio ci sono 2 copie: tagliare sui crocini, 2 pezzi da 195 × 135 mm.", R_)],
    ], y)
    y = section("Pagine interne (5–14): foratura", [
        [("4 fori sul lato sinistro, diametro 6 mm, 80 mm fra i centri.", B_)],
        [("Centri a 12 mm dal bordo sinistro e a 28,5 · 108,5 · 188,5 · 268,5 mm", R_),
         ("dal bordo alto. Nessun taglio.", R_)],
        [("Provare un foglio sugli anelli prima di forare gli altri.", B_)],
    ], y)

    # attenzione
    ah = 16 * RMM
    c.setFillColor(GOLDL); c.rect(L, y - ah, RR - L, ah, stroke=0, fill=1)
    c.setFillColor(GOLD); c.rect(L, y - ah, 1.5 * RMM, ah, stroke=0, fill=1)
    c.setFillColor(NAVY); c.setFont("Mont-Bold", 10)
    c.drawString(L + 6 * RMM, y - 6.3 * RMM, "Attenzione")
    c.setFillColor(INK); c.setFont("Mont-Regular", 9)
    c.drawString(L + 6 * RMM, y - 11.6 * RMM, "La copertina ha un fondo scuro pieno: se esce a chiazze, avvisare prima di tagliare.")

    # piede
    c.setFillColor(NAVY); c.rect(0, 0, W, 18 * RMM, stroke=0, fill=1)
    c.setFillColor(GOLD); c.rect(0, 18 * RMM, W, 1 * RMM, stroke=0, fill=1)
    c.setFillColor(HexColor("#FFFFFF")); c.setFont("Mont-Regular", 9.5)
    c.drawString(L, 7.5 * RMM, "Per dubbi:")
    c.setFont("Mont-Bold", 9.5)
    c.drawString(L + c.stringWidth("Per dubbi: ", "Mont-Regular", 9.5), 7.5 * RMM, "Massimiliano Zambotto")
    c.setFillColor(GOLD); c.setFont("Mont-Bold", 11)
    c.drawRightString(RR, 7.3 * RMM, "+39 347 244 0128")
    c.showPage(); c.save()
    return buf.getvalue()


out = fitz.open()
out.insert_pdf(fitz.open("pdf", scheda_pdf()))
info_c = a3_piece(out, 0, (11, 11, 199, 286), 230, 305, "h", 121.0,
                  "PAGINA 2 · COPERTINA · foglio A3 al 100% · cartoncino opaco 200 g · taglio sui crocini: 230 × 305 mm")
out.insert_pdf(src, from_page=1, to_page=1)
info_d = a3_piece(out, 2, (25.5, 7, 63.5, 289), 40, 305, "w", 244.294,
                  "PAGINA 4 · DORSO · foglio A3 al 100% · cartoncino opaco 200 g · taglio sui crocini: 40 × 305 mm")
out.insert_pdf(src, from_page=3, to_page=12)
out.set_metadata({"title": "Il Libro della Casa - stampa definitiva", "author": "Rev(enue)Up"})
out.save(OUT, garbage=3, deflate=True)
print("copertina", info_c)
print("dorso", info_d)
