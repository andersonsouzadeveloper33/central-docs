"""
Converte logo.png para icon.ico com fundo transparente e múltiplos tamanhos.
Requer: pip install pillow
"""
from PIL import Image
import os

INPUT  = os.path.join(os.path.dirname(__file__), "logo.png")
OUTPUT = os.path.join(os.path.dirname(__file__), "icon.ico")

img = Image.open(INPUT).convert("RGBA")

# Remove fundo branco tornando-o transparente
r, g, b, a = img.split()
pixels = img.load()
w, h = img.size
for y in range(h):
    for x in range(w):
        pr, pg, pb, pa = pixels[x, y]
        # Se o pixel for próximo do branco, torna transparente
        if pr > 240 and pg > 240 and pb > 240:
            pixels[x, y] = (pr, pg, pb, 0)

# Adiciona fundo escuro (#1E2A3A) — fica bem na barra de tarefas
bg = Image.new("RGBA", img.size, (30, 42, 58, 255))
bg.paste(img, mask=img.split()[3])

sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
icons = []
for size in sizes:
    resized = bg.resize(size, Image.LANCZOS)
    icons.append(resized)

icons[0].save(OUTPUT, format="ICO", sizes=sizes, append_images=icons[1:])
print(f"Ícone gerado: {OUTPUT}")
