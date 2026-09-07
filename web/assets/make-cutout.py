"""
Zemin duz degil, radyal bir vinyet. Kenar serisinden 2. derece bir yuzey
uydurup her pikselde beklenen zemin rengini kestiriyoruz; figur o yuzeyden
uzaklastigi icin ayrisiyor. Sonra kenarlardan bagli bilesen aliniyor ki
figurun uzerindeki bej tonlar (karton kutu) silinmesin.
"""
import os
import sys
from collections import deque

import numpy as np
from PIL import Image, ImageFilter

src_path, out_path, tol = sys.argv[1], sys.argv[2], float(sys.argv[3])
src = Image.open(src_path).convert("RGBA")
a = np.array(src)
h, w = a.shape[:2]
rgb = a[:, :, :3].astype(np.float64)

yy, xx = np.mgrid[0:h, 0:w].astype(np.float64)
Y, X = yy / h, xx / w
basis = np.stack([np.ones_like(X), X, Y, X * X, Y * Y, X * Y], axis=-1)   # (h,w,6)

ring = np.zeros((h, w), bool)
b = 14
ring[:b, :] = ring[-b:, :] = ring[:, :b] = ring[:, -b:] = True

A = basis[ring]                      # (n,6)
pred = np.empty_like(rgb)
for c in range(3):
    coef, *_ = np.linalg.lstsq(A, rgb[ring][:, c], rcond=None)
    pred[:, :, c] = basis @ coef

dist = np.linalg.norm(rgb - pred, axis=2)
mask = dist < tol

visited = np.zeros((h, w), bool)
dq = deque()
for x in range(w):
    for y in (0, h - 1):
        if mask[y, x] and not visited[y, x]:
            visited[y, x] = True
            dq.append((y, x))
for y in range(h):
    for x in (0, w - 1):
        if mask[y, x] and not visited[y, x]:
            visited[y, x] = True
            dq.append((y, x))
while dq:
    y, x = dq.popleft()
    for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ny, nx = y + dy, x + dx
        if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not visited[ny, nx]:
            visited[ny, nx] = True
            dq.append((ny, nx))

alpha = np.where(visited, 0, 255).astype(np.uint8)
out = Image.fromarray(np.dstack([a[:, :, :3], alpha]))
out.putalpha(out.split()[3].filter(ImageFilter.GaussianBlur(1.0)))
out.save(out_path, optimize=True)
ys, xs = np.where(alpha > 12)
print(f"seffaf {100 * visited.mean():.1f}% · figur {xs.max()-xs.min()}x{ys.max()-ys.min()}"
      f" · {os.path.getsize(out_path) // 1024} KB")
