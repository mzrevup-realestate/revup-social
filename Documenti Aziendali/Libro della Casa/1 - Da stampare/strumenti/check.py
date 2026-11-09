import sys
import numpy as np
import pymupdf as fitz
import zxingcpp

F, SRC = sys.argv[1], sys.argv[2]
MM = 72 / 25.4
d = fitz.open(F)
src = fitz.open(SRC)
ok = True


def fail(msg):
    global ok
    ok = False
    print("  ** NON PASSA:", msg)


print("1) FORMATI")
names = {(595, 842): "A4 verticale", (842, 1191): "A3 verticale"}
exp = ["A4 verticale", "A3 verticale", "A4 verticale", "A3 verticale"] + ["A4 verticale"] * 10
if d.page_count != 14:
    fail(f"pagine {d.page_count}")
for i, p in enumerate(d):
    k = (round(p.rect.width), round(p.rect.height))
    n = names.get(k, str(k))
    print(f"  pag {i+1:2d}: {p.rect.width/MM:.1f} × {p.rect.height/MM:.1f} mm  {n}")
    if n != exp[i]:
        fail(f"pag {i+1} è {n}, attesa {exp[i]}")
    if p.rotation:
        fail(f"pag {i+1} ruotata")

print("2) CROCINI")
pieces = {2: ("copertina", (33.5, 57.5, 263.5, 362.5)), 4: ("dorso", (128.5, 57.5, 168.5, 362.5))}
for pno, (name, (tx0, ty0, tx1, ty1)) in pieces.items():
    p = d[pno - 1]
    lines = []
    for dr in p.get_drawings():
        if dr.get("color") == (0.0, 0.0, 0.0):
            for it in dr["items"]:
                if it[0] == "l":
                    a, b = it[1], it[2]
                    lines.append(((a.x / MM, a.y / MM), (b.x / MM, b.y / MM), dr["width"]))
    print(f"  pag {pno} {name}: {len(lines)} crocini, spessore {lines[0][2]:.2f} pt; taglio atteso x {tx0}/{tx1}, y {ty0}/{ty1} mm")
    if len(lines) != 8:
        fail("numero crocini")
    bleed = (tx0 - 3, ty0 - 3, tx1 + 3, ty1 + 3)
    for (ax, ay), (bx, by), w in lines:
        if abs(ax - bx) < 1e-6:  # verticale
            on = min(abs(ax - tx0), abs(ax - tx1)) < 0.005
            outside = max(ay, by) <= bleed[1] + 1e-6 or min(ay, by) >= bleed[3] - 1e-6
            desc = f"verticale  x={ax:7.2f}  y {min(ay,by):6.2f}–{max(ay,by):6.2f}"
        else:
            on = min(abs(ay - ty0), abs(ay - ty1)) < 0.005
            outside = max(ax, bx) <= bleed[0] + 1e-6 or min(ax, bx) >= bleed[2] - 1e-6
            desc = f"orizzontale y={ay:7.2f}  x {min(ax,bx):6.2f}–{max(ax,bx):6.2f}"
        print(f"    {desc}  sulla linea di taglio: {'sì' if on else 'NO'}  fuori dal margine: {'sì' if outside else 'NO'}")
        if not (on and outside):
            fail(desc)

print("3) QR DELLA COPERTINA")
want = "https://wa.me/message/TRID3JO5EGZ4M1?src=qr"
for dpi in (150, 300, 600):
    pix = d[1].get_pixmap(dpi=dpi)
    img = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3].copy()
    res = zxingcpp.read_barcodes(img)
    txt = [r.text for r in res if r.format == zxingcpp.BarcodeFormat.QRCode]
    print(f"  {dpi} dpi, pagina intera: {txt}")
    if txt != [want]:
        fail(f"QR a {dpi} dpi")
qr = [dr for dr in d[1].get_drawings() if dr.get("fill") == (1.0, 1.0, 1.0) and len(dr["items"]) > 100]
if qr:
    r = qr[0]["rect"]
    print(f"  QR: {r.x0/MM:.2f}–{r.x1/MM:.2f} × {r.y0/MM:.2f}–{r.y1/MM:.2f} mm, lato {r.width/MM:.2f} mm")
# confronto posizione rispetto alla grafica originale
s = 305 / 275
gx0 = 33.5 + (230 - 188 * s) / 2
print(f"  QR atteso (originale 155,00–181,04 ingrandito): x {gx0+(155-11)*s:.2f}–{gx0+(181.04-11)*s:.2f}, y {57.5+(237.04-11)*s:.2f}–{57.5+(263.08-11)*s:.2f}")

print("4) BORDI DI TAGLIO: niente fili bianchi")
DARK = np.array([32, 23, 42])
DPI = 600
for pno, (name, (tx0, ty0, tx1, ty1)), grect, liney in (
    (2, pieces[2], (33.5 + (230 - 188 * s) / 2, 57.5, 33.5 + (230 + 188 * s) / 2, 362.5), (179.50, 180.674)),
    (4, pieces[4], (128.5, 57.5 + (305 - 282 * 40 / 38) / 2, 168.5, 362.5 - (305 - 282 * 40 / 38) / 2), (311.36, 312.11)),
):
    p = d[pno - 1]
    bx0, by0, bx1, by1 = tx0 - 3, ty0 - 3, tx1 + 3, ty1 + 3
    pix = p.get_pixmap(dpi=DPI, clip=fitz.Rect(bx0 * MM, by0 * MM, bx1 * MM, by1 * MM))
    a = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, pix.n)[:, :, :3].astype(int)
    xs = bx0 + (np.arange(pix.w) + 0.5) / DPI * 25.4
    ys = by0 + (np.arange(pix.h) + 0.5) / DPI * 25.4
    diff = np.abs(a - DARK).sum(2)
    lum = a.mean(2)
    # (a) nessun pixel chiaro in tutta l'area margine+pezzo
    print(f"  pag {pno} {name}: area resa {xs[0]-0.02:.1f}–{xs[-1]+0.02:.1f} × {ys[0]-0.02:.1f}–{ys[-1]+0.02:.1f} mm a {DPI} dpi")
    # fascia: dal bordo del margine fino a 1 mm oltre il bordo della grafica ingrandita (o 2 mm dentro il taglio)
    gx0_, gy0_, gx1_, gy1_ = grect
    ix0, iy0 = max(gx0_ + 1, tx0 + 2), max(gy0_ + 1, ty0 + 2)
    ix1, iy1 = min(gx1_ - 1, tx1 - 2), min(gy1_ - 1, ty1 - 2)
    band = ~(((xs > ix0) & (xs < ix1))[None, :] & ((ys > iy0) & (ys < iy1))[:, None])
    onl = ((ys >= liney[0] - 0.15) & (ys <= liney[1] + 0.15))[:, None] & np.ones(len(xs), bool)[None, :]
    # escludo solo l'anello di 0,15 mm sul bordo esterno del margine (antialiasing contro la carta, viene rifilato via)
    ring = ~(((xs > bx0 + 0.15) & (xs < bx1 - 0.15))[None, :] & ((ys > by0 + 0.15) & (ys < by1 - 0.15))[:, None])
    bg = band & ~onl & ~ring
    print(f"    fascia sul bordo (fondo): max scarto dal fondo scuro {diff[bg].max()}, luminosità max {lum[bg].max():.0f}/255, pixel chiari {(lum[bg] > 60).sum()}")
    if diff[bg].max() > 12:
        fail(f"{name}: pixel non scuri nella fascia sul bordo")
    # righe e colonne esattamente sui tagli
    inx = (xs > bx0 + 0.15) & (xs < bx1 - 0.15)
    iny = (ys > by0 + 0.15) & (ys < by1 - 0.15) & ~((ys >= liney[0] - 0.15) & (ys <= liney[1] + 0.15))
    for lab, sl in (("taglio sinistro", a[iny, np.argmin(abs(xs - tx0))]), ("taglio destro", a[iny, np.argmin(abs(xs - tx1))]),
                    ("taglio alto", a[np.argmin(abs(ys - ty0)), inx]), ("taglio basso", a[np.argmin(abs(ys - ty1)), inx])):
        l = sl.mean(1)
        print(f"    {lab} (fuori dalla riga del gradiente): luminosità max {l.max():.0f}/255")
        if l.max() > 60:
            fail(f"{name}: {lab} chiaro")
    # (b) gradiente: da bordo a bordo del margine
    rows = np.where((ys > liney[0] + 0.1) & (ys < liney[1] - 0.1))[0]
    lr = a[rows].mean(0)
    colored = np.abs(lr - DARK).sum(1) > 60
    cx = xs[colored]
    print(f"    gradiente: colorato da x={cx.min()-0.02:.2f} a x={cx.max()+0.02:.2f} mm (margine {bx0:.1f}–{bx1:.1f}); "
          f"colonne non colorate in mezzo: {int((~colored[(xs>=cx.min())&(xs<=cx.max())]).sum())}; "
          f"colore ai capi {lr[0].round().astype(int).tolist()} … {lr[-1].round().astype(int).tolist()}")
    if not (cx.min() <= bx0 + 0.05 and cx.max() >= bx1 - 0.05):
        fail(f"{name}: gradiente non arriva al bordo del margine")
    # (c) fuori dal margine: bianco (nessuna sbavatura del fondo)
    pixf = p.get_pixmap(dpi=150)
    f = np.frombuffer(pixf.samples, np.uint8).reshape(pixf.h, pixf.w, pixf.n)[:, :, :3].astype(int)
    X = (np.arange(pixf.w) + 0.5) / 150 * 25.4
    Y = (np.arange(pixf.h) + 0.5) / 150 * 25.4
    out = ~(((X > bx0 - 0.3) & (X < bx1 + 0.3))[None, :] & ((Y > by0 - 0.3) & (Y < by1 + 0.3))[:, None])
    dk = (f.mean(2) < 100) & out
    print(f"    fuori dal margine, pixel scuri a parte crocini e didascalia: ", end="")
    # escludo crocini e didascalia
    m = dk.copy()
    m[Y < ty0 - 4, :] = False  # sopra: crocini + didascalia
    m[Y > ty1 + 4, :] = False
    m[:, (X < tx0 - 4) | (X > tx1 + 4)] = False
    print(int(m.sum()))
    if m.sum():
        fail(f"{name}: fondo sbordato")

print("5) INSERTO E PAGINE INTERNE IDENTICHE ALL'ORIGINALE")
INT = fitz.open(sys.argv[3]) if len(sys.argv) > 3 else None
pairs = [(3, src, 2)] + ([(i, INT, i - 3) for i in range(5, 15)] if INT else [(i, src, i - 1) for i in range(5, 15)])
for outp, sdoc, srcp in pairs:
    A = d[outp - 1].get_pixmap(dpi=100).samples
    B = sdoc[srcp - 1].get_pixmap(dpi=100).samples
    same = A == B
    print(f"  pag {outp} = originale pag {srcp}: {'identica' if same else 'DIVERSA'}", end="; ")
    if not same:
        fail(f"pag {outp}")
print()
print("ESITO:", "TUTTO OK" if ok else "CI SONO PROBLEMI")
