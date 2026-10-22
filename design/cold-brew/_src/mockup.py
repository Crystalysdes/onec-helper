"""Render the label onto the bottle photo (clear bottle and cold-brew variants)."""
import sys

import cairosvg
import numpy as np
from PIL import Image
from scipy import ndimage as ndi

import bottle_geom as G

LS = 4                       # label raster scale (px per label unit)
UX, SY = 400.0, 600.0        # label SVG origin offsets (see label.py)
RX0, RY0, RX1, RY1 = 90, 820, 620, 1880   # working region in the photo
SS = 2                       # supersampling


def load_label(svg_path="label_flat.svg"):
    cairosvg.svg2png(url=svg_path, write_to="_label_raster.png", output_width=int(800 * LS))
    lab = np.asarray(Image.open("_label_raster.png").convert("RGBA")).astype(np.float32) / 255.0
    rgb = lab[..., :3] * lab[..., 3:4]           # premultiply
    return np.dstack([rgb, lab[..., 3]])


def project(lab):
    """Project the label into photo space for the working region. Returns premult RGBA, phi."""
    w, h = (RX1 - RX0) * SS, (RY1 - RY0) * SS
    xs = RX0 + (np.arange(w) + 0.5) / SS
    ys = RY0 + (np.arange(h) + 0.5) / SS
    X, Y = np.meshgrid(xs, ys)
    u, s, vis, phi, v = G.inverse(X, Y)
    col = (u + UX) * LS - 0.5
    row = (s - SY) * LS - 0.5
    out = np.zeros((h, w, 4), np.float32)
    for c in range(4):
        out[..., c] = ndi.map_coordinates(lab[..., c], [row, col], order=1, mode="constant", cval=0.0)
    out *= vis[..., None]
    # downsample
    out = out.reshape(h // SS, SS, w // SS, SS, 4).mean(axis=(1, 3))
    phi1 = phi.reshape(h // SS, SS, w // SS, SS).mean(axis=(1, 3))
    return out, phi1


def lighting(phi, y):
    """RGB multiplier for a white print as a function of angle from the front (from the cap)."""
    deg = np.degrees(phi)
    kx = np.array([-90, -60, -30, 0, 30, 55, 70, 90], float)
    R = np.array([0.55, 0.70, 0.80, 0.875, 0.895, 0.94, 0.955, 0.80])
    Gc = np.array([0.50, 0.64, 0.75, 0.83, 0.85, 0.91, 0.93, 0.77])
    B = np.array([0.47, 0.59, 0.69, 0.76, 0.78, 0.84, 0.855, 0.72])
    L = np.dstack([np.interp(deg, kx, R), np.interp(deg, kx, Gc), np.interp(deg, kx, B)])
    vert = 1.0 - 0.07 * np.clip((y - 900) / 850.0, 0, 1)
    return L * vert[..., None]


def highlights(photo):
    """Specular streaks on the glass: bright, thin, mostly vertical."""
    L = photo.mean(axis=2)
    bg = ndi.median_filter(L, size=(1, 41))
    bg = ndi.gaussian_filter(bg, 2)
    d = np.clip(L - bg, 0, None)
    m = np.clip((d - 12) / 40, 0, 1) * np.clip((L - 140) / 60, 0, 1)
    m = ndi.gaussian_filter(m, 0.7)
    bg_rgb = np.dstack([ndi.gaussian_filter(ndi.median_filter(photo[..., c], size=(1, 41)), 2) for c in range(3)])
    hl = np.clip(photo - bg_rgb, 0, None) * m[..., None]
    return hl, m


def composite(base, lab_pm, phi, photo_reg, ink_opacity=0.95, hl_over_ink=0.55, seed=1):
    h, w = lab_pm.shape[:2]
    ys = RY0 + np.arange(h)[:, None] + 0.5 + np.zeros((1, w))
    L = lighting(phi, ys)
    a = lab_pm[..., 3:4] * ink_opacity
    rgb = lab_pm[..., :3] / np.maximum(lab_pm[..., 3:4], 1e-6)
    ink = rgb * L * 255.0
    # match photo softness
    ink_blur = np.dstack([ndi.gaussian_filter(ink[..., c] * a[..., 0], 0.55) for c in range(3)])
    a_blur = ndi.gaussian_filter(a[..., 0], 0.55)[..., None]
    out = base * (1 - a_blur) + ink_blur
    hl, m = highlights(photo_reg)
    out = out + hl * (1 - a_blur) * 0.0 + hl * a_blur * hl_over_ink
    rng = np.random.default_rng(seed)
    grain = rng.normal(0, 2.2, out.shape[:2])[..., None]
    out = out + grain * a_blur
    return np.clip(out, 0, 255)


def render_clear(label_svg="label_flat.svg", out="mockup_clear.png"):
    photo = np.asarray(Image.open("photo.png").convert("RGB")).astype(np.float32)
    lab = load_label(label_svg)
    lab_pm, phi = project(lab)
    reg = photo[RY0:RY1, RX0:RX1].copy()
    res = composite(reg, lab_pm, phi, reg)
    full = photo.copy()
    full[RY0:RY1, RX0:RX1] = res
    Image.fromarray(full.round().astype(np.uint8)).save(out)
    return full


if __name__ == "__main__":
    render_clear()
    print("ok")
