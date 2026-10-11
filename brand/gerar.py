from PIL import Image, ImageDraw, ImageFont, ImageOps
import sys
F = "/root/.claude/skills/synced/3c149fb8-94e7-490b-a0b5-c22f6bc1e4cb_074bbf9e-d82a-4282-ab2a-222d47a26740/canvas-design/canvas-fonts/"
OUT = sys.argv[1]
PAPER, INK, RED, GREY = (242, 236, 223), (20, 20, 20), (229, 64, 47), (138, 132, 120)

def font(name, size): return ImageFont.truetype(F + name, size)

def irony_mark(height):
    """Ponto de ironia: o «?» da Gloock espelhado; devolve (gancho, ponto) como máscaras do mesmo tamanho."""
    f = font("Gloock-Regular.ttf", int(height * 1.45))
    probe = Image.new("L", (int(height * 2), int(height * 2.2)), 0)
    ImageDraw.Draw(probe).text((height * 0.3, 0), "?", font=f, fill=255)
    m = ImageOps.mirror(probe.crop(probe.getbbox()))
    m = m.resize((round(m.width * height / m.height), height), Image.LANCZOS)
    rows = [sum(1 for x in range(m.width) if m.getpixel((x, y)) > 40) for y in range(m.height)]
    gap = next(y for y in range(m.height - 1, 0, -1) if rows[y] == 0)   # linha vazia entre o gancho e o ponto
    hook, dot = m.copy(), m.copy()
    ImageDraw.Draw(hook).rectangle([0, gap, m.width, m.height], fill=0)
    ImageDraw.Draw(dot).rectangle([0, 0, m.width, gap], fill=0)
    return hook, dot

def paste_mark(img, cx, cy, height, hook_color, dot_color):
    hook, dot = irony_mark(height)
    db = dot.getbbox(); dot_cx = (db[0] + db[2]) / 2
    axis = (hook.width / 2 + dot_cx) / 2          # centro ótico: entre a caixa e o eixo do ponto
    x, y = round(cx - axis), round(cy - height / 2)
    img.paste(Image.new("RGB", hook.size, hook_color), (x, y), hook)
    img.paste(Image.new("RGB", dot.size, dot_color), (x, y), dot)

def text_center(d, cx, y, s, f, fill):
    w = d.textlength(s, font=f); d.text((cx - w / 2, y), s, font=f, fill=fill)

# 1) Avatar (Instagram/TikTok recortam em círculo): marca centrada com margem de segurança.
def avatar(bg, fg, path, size=1080):
    img = Image.new("RGB", (size, size), bg)
    paste_mark(img, size / 2, size / 2, int(size * 0.56), fg, RED)
    img.save(path)
avatar(INK, PAPER, OUT + "/ironia-diaria-avatar.png")
avatar(PAPER, INK, OUT + "/ironia-diaria-avatar-claro.png")

# 2) Logótipo horizontal (fundo transparente): marca + palavra.
def lockup(word, path, ink=INK):
    h, fw = 300, font("Gloock-Regular.ttf", 230)
    tmp = ImageDraw.Draw(Image.new("RGB", (10, 10)))
    tw = tmp.textlength(word, font=fw)
    W, H = int(h * 0.62 + 70 + tw + 80), 420
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    base = Image.new("RGB", (W, H), PAPER)
    hook, dot = irony_mark(h)
    x, y = 40, (H - h) // 2
    img.paste(ink + (255,), (x, y), hook); img.paste(RED + (255,), (x, y), dot)
    d = ImageDraw.Draw(img)
    asc, desc = fw.getmetrics()
    d.text((x + hook.width + 70, (H - asc) // 2 - 10), word, font=fw, fill=ink + (255,))
    img = img.crop(img.getbbox())
    pad = Image.new("RGBA", (img.width + 80, img.height + 80), (0, 0, 0, 0)); pad.paste(img, (40, 40))
    pad.save(path)
lockup("Ironia Diária", OUT + "/ironia-diaria-logotipo.png")
lockup("Ironía Diaria", OUT + "/ironia-diaria-logotipo-es.png")

# 3) Prancha da marca.
W, H, M = 2400, 3000, 160
img = Image.new("RGB", (W, H), PAPER); d = ImageDraw.Draw(img)
mono, mono_s = font("GeistMono-Regular.ttf", 30), font("GeistMono-Regular.ttf", 24)
d.text((M, M - 40), "IRONIA DIÁRIA", font=mono, fill=INK)
s = "IDENTIDADE  ·  FIG. 1"; d.text((W - M - d.textlength(s, font=mono), M - 40), s, font=mono, fill=GREY)
d.line([(M, M + 20), (W - M, M + 20)], fill=INK, width=2)

cx, cy, r = W / 2, 1060, 620
d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=GREY, width=2)
for i in range(120):                          # régua circular: marcas de medição
    import math
    a = math.radians(i * 3); L = 34 if i % 10 == 0 else 14
    x1, y1 = cx + r * math.cos(a), cy + r * math.sin(a)
    x2, y2 = cx + (r - L) * math.cos(a), cy + (r - L) * math.sin(a)
    d.line([(x1, y1), (x2, y2)], fill=GREY, width=2 if i % 10 == 0 else 1)
paste_mark(img, cx, cy, 760, INK, RED)
d.text((cx + r + 30, cy - 14), "A", font=mono_s, fill=GREY)
d.text((cx - r - 52, cy - 14), "B", font=mono_s, fill=GREY)
cap = "ponto de ironia  —  Alcanter de Brahm, 1899"
cw = d.textlength(cap, font=mono_s); x0 = cx - (cw + 40) / 2
paste_mark(img, x0 + 8, cy + r + 60, 30, GREY, RED)
d.text((x0 + 40, cy + r + 46), cap, font=mono_s, fill=GREY)

fw = font("Gloock-Regular.ttf", 190)
text_center(d, cx, 1880, "Ironia Diária", fw, INK)
text_center(d, cx, 2110, "Ironía Diaria", font("InstrumentSerif-Italic.ttf", 104), GREY)
text_center(d, cx, 2255, "PT · ES", mono_s, GREY)

d.line([(M, 2380), (W - M, 2380)], fill=INK, width=2)
sw = [(PAPER, "PAPEL", "#F2ECDF"), (INK, "TINTA", "#141414"), (RED, "ÚLTIMA HORA", "#E5402F")]
for i, (c, n, hx) in enumerate(sw):
    x = M + i * 420
    d.ellipse([x, 2450, x + 150, 2600], fill=c, outline=INK, width=2)
    d.text((x + 180, 2480), n, font=mono_s, fill=INK); d.text((x + 180, 2522), hx, font=mono_s, fill=GREY)
for j, (bg, fg) in enumerate([(INK, PAPER), (PAPER, INK)]):   # avatares em uso (círculo)
    a = Image.new("RGB", (300, 300), bg); paste_mark(a, 150, 150, 168, fg, RED)
    mask = Image.new("L", (300, 300), 0); ImageDraw.Draw(mask).ellipse([0, 0, 299, 299], fill=255)
    x = W - M - 300 - j * 340
    img.paste(a, (x, 2360 + 80), mask); d.ellipse([x, 2440, x + 299, 2739], outline=INK, width=2)
d.text((M, H - M + 30), "Gloock · Instrument Serif · Geist Mono", font=mono_s, fill=GREY)
s = "avatar  ·  fundo escuro / claro"; d.text((W - M - d.textlength(s, font=mono_s), H - M + 30), s, font=mono_s, fill=GREY)
img.save(OUT + "/ironia-diaria-marca.png")
print("ok")
