"""Fill the photographed bottle with cold brew, then print the label on it."""
import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

import bottle_geom as G
import mockup as M

SUP = 4  # polygon raster supersampling

# outer half-width of the shoulder (measured on the photo), body uses the model
SH_V = np.array([560, 600, 640, 680, 720, 750, 800], float)
SH_W = np.array([154, 175, 191, 205, 214, 217.5, G.a(800)], float)


def outer_hw(v):
    v = np.asarray(v, float)
    return np.where(v < 800, np.interp(v, SH_V, SH_W), G.a(v))


def arc(v_level, radius, n=160, front=True):
    """Front arc of a horizontal circle (silhouette row v_level, image radius `radius`)."""
    r = radius / np.sqrt(G.F ** 2 + radius ** 2)
    pm = np.arccos(r)
    phi = np.linspace(-pm, pm, n)
    x = G.cx(v_level) + radius * np.sqrt(1 - r * r) * np.sin(phi) / (1 - r * np.cos(phi))
    if front:
        y = G.YH + (v_level - G.YH) * (1 - r * r) / (1 - r * np.cos(phi))
    else:  # back arc
        y = G.YH + (v_level - G.YH) * (1 - r * r) / (1 + r * np.cos(phi))
    return np.c_[x, y]


def poly_mask(pts, shape, blur=0.0):
    h, w = shape
    im = Image.new("L", (w * SUP, h * SUP), 0)
    ImageDraw.Draw(im).polygon([(float(x) * SUP, float(y) * SUP) for x, y in pts], fill=255)
    m = np.asarray(im.resize((w, h), Image.BOX)).astype(np.float32) / 255.0
    if blur:
        m = ndi.gaussian_filter(m, blur)
    return m


V_SURF = 612.0      # liquid level (silhouette row)
V_BOT = 1778.0      # inner bottom disc (silhouette row)
RIM = 3.0           # glass rim left visible at the sides
BASE_PTS = [(121, 1785), (125, 1800), (150, 1830), (200, 1867), (250, 1880), (300, 1885), (350, 1882),
            (400, 1873), (450, 1865), (500, 1850), (550, 1825), (575, 1795), (581, 1785)]


def liquid_polygon():
    top = arc(V_SURF, outer_hw(V_SURF) - RIM)
    vs = np.linspace(V_SURF, V_BOT, 120)
    right = np.c_[G.cx(vs) + outer_hw(vs) - RIM, vs]
    bot = arc(V_BOT, 212.0)[::-1]
    left = np.c_[G.cx(vs) - (outer_hw(vs) - RIM), vs][::-1]
    return np.vstack([top, right, bot, left])


def bottle_polygon():
    """Outer silhouette from the shoulder down to the base outline."""
    vs = np.linspace(560, 1785, 200)
    right = np.c_[G.cx(vs) + outer_hw(vs), vs]
    left = np.c_[G.cx(vs) - outer_hw(vs), vs][::-1]
    base = np.array(BASE_PTS, float)[::-1]
    return np.vstack([right, base, left])


def highlight_layer(photo):
    L = photo.mean(axis=2)
    y, x = np.ogrid[-12:13, -12:13]
    fp = (x * x + y * y) <= 144
    op = ndi.grey_opening(L, footprint=fp)
    th = L - op
    m = np.clip((th - 12) / 40.0, 0, 1) * np.clip((L - 115) / 80.0, 0, 1)
    m = ndi.gaussian_filter(m, 0.6)
    return m, L


def render(label_svg="label_flat.svg", out_file="mockup_coldbrew.png", seed=3):
    photo = np.asarray(Image.open("photo.png").convert("RGB")).astype(np.float32)
    H, W = photo.shape[:2]
    liq = poly_mask(liquid_polygon(), (H, W), blur=0.6)
    bottle = poly_mask(bottle_polygon(), (H, W), blur=0.5)
    base_reg = np.clip(bottle - poly_mask(np.vstack([liquid_polygon()]), (H, W)), 0, 1)
    base_reg[:1700] = 0
    base_reg = ndi.gaussian_filter(base_reg, 0.8)

    # angle from the front for every pixel (outer-surface model)
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    hw = outer_hw(yy)
    sphi = np.clip((xx - G.cx(yy)) / hw, -1, 1)
    edge = np.abs(sphi)

    # --- liquid colour field ---
    core = np.array([13, 7, 5], np.float32)
    rimL = np.array([62, 26, 15], np.float32)
    rimR = np.array([88, 38, 21], np.float32)
    w_rim = np.clip((edge - 0.80) / 0.19, 0, 1) ** 1.8
    rim = np.where(sphi[..., None] < 0, rimL, rimR)
    col = core * (1 - w_rim[..., None]) + rim * w_rim[..., None]
    vert = 1.0 + 0.35 * np.clip((820 - yy) / 220.0, 0, 1) - 0.10 * np.clip((yy - 1350) / 450.0, 0, 1)
    col = col * vert[..., None]
    # broad soft sheen of the window light on the right half of the glass
    sheen = np.exp(-((sphi - 0.62) ** 2) / (2 * 0.16 ** 2)) * np.clip((yy - 640) / 120.0, 0, 1)
    col = col + sheen[..., None] * np.array([16, 13, 12], np.float32)
    # very fine glass texture from the photo
    Lp = photo.mean(axis=2)
    detail = Lp - ndi.gaussian_filter(Lp, 3)
    col = col * (1 + np.clip(detail, -30, 30)[..., None] / 260.0)

    # reflections: vertical streaks (window) + sparkles in the base
    bgm = ndi.median_filter(Lp, size=(1, 41))
    d = np.clip(Lp - bgm, 0, None)
    m_streak = np.clip((d - 10) / 38.0, 0, 1) * np.clip((Lp - 135) / 65.0, 0, 1)
    # keep only vertically coherent streaks (window reflections), drop short marks
    coh = ndi.gaussian_filter(m_streak, (9, 0.8))
    m_streak = m_streak * np.clip((coh - 0.10) / 0.18, 0, 1)
    m_streak = ndi.gaussian_filter(m_streak, 0.6)
    hl_m, _ = highlight_layer(photo)
    hl_rgb = photo * m_streak[..., None] * 1.15

    # the thin glass rim outside the liquid also looks dark when filled
    rim_band = np.clip(bottle - liq, 0, 1) * (yy > V_SURF + 30)
    out = photo.copy()
    out = out * (1 - rim_band[..., None] * 0.40) + rim_band[..., None] * np.array([20, 10, 7], np.float32) * 0.40
    out = out * (1 - liq[..., None]) + col * liq[..., None]
    # thick glass base: sees the coffee above it -> dark, warm, keeps sparkles
    tinted = photo * np.array([0.26, 0.17, 0.14], np.float32) + np.array([8, 3, 2], np.float32)
    out = out * (1 - base_reg[..., None]) + tinted * base_reg[..., None]
    refl_w = np.clip(liq + base_reg + rim_band, 0, 1)[..., None]
    out = out + hl_rgb * refl_w
    out = out + photo * (hl_m * base_reg)[..., None] * 0.5

    # soft glossy window reflections (continuous, gently modulated) for volume
    rng2 = np.random.default_rng(11)
    mod = ndi.gaussian_filter1d(rng2.normal(0, 1, H), 40)
    mod = 0.75 + 0.25 * mod / (np.abs(mod).max() + 1e-6)
    for c0, wdt, amp in ((0.50, 0.050, 20.0), (-0.47, 0.035, 9.0)):
        band_g = np.exp(-((sphi - c0) ** 2) / (2 * wdt ** 2)) * mod[:, None]
        band_g *= np.clip((yy - V_SURF - 30) / 90.0, 0, 1) * np.clip((1770 - yy) / 90.0, 0, 1)
        out = out + (band_g * liq)[..., None] * np.array([1.0, 0.97, 0.93], np.float32) * amp

    # thin bright glass edges along the silhouette
    vs = np.linspace(V_SURF + 40, 1780, 300)
    for side, strength in ((-1, 34.0), (1, 52.0)):
        xs = G.cx(vs) + side * (outer_hw(vs) - 2.2)
        im = Image.new("L", (W * SUP, H * SUP), 0)
        ImageDraw.Draw(im).line([(float(x) * SUP, float(y) * SUP) for x, y in zip(xs, vs)], fill=255,
                                width=int(1.4 * SUP))
        e = ndi.gaussian_filter(np.asarray(im.resize((W, H), Image.BOX)).astype(np.float32) / 255.0, 0.7)
        fade = np.clip((yy - V_SURF - 40) / 120.0, 0, 1) * np.clip((1780 - yy) / 80.0, 0, 1)
        out = out + (e * fade)[..., None] * np.array([1.0, 0.96, 0.9], np.float32) * strength

    # meniscus: thin warm line + faint lighter underside band
    top = arc(V_SURF, outer_hw(V_SURF) - RIM)
    back = arc(V_SURF, outer_hw(V_SURF) - RIM, front=False)
    band = poly_mask(np.vstack([top, back[::-1]]), (H, W), blur=1.0) * liq
    out = out + band[..., None] * np.array([26, 18, 15], np.float32)
    line = np.zeros((H, W), np.float32)
    im = Image.new("L", (W * SUP, H * SUP), 0)
    ImageDraw.Draw(im).line([(float(x) * SUP, float(y) * SUP) for x, y in top], fill=255, width=int(1.6 * SUP))
    line = np.asarray(im.resize((W, H), Image.BOX)).astype(np.float32) / 255.0
    line = ndi.gaussian_filter(line, 0.6)
    out = out * (1 - line[..., None] * 0.55) + line[..., None] * np.array([150, 112, 88], np.float32) * 0.55

    # subtle grain over the synthetic liquid so it matches the photo
    rng = np.random.default_rng(seed)
    grain = ndi.gaussian_filter(rng.normal(0, 3.0, (H, W)), 0.5)[..., None]
    out = out + grain * np.clip(liq + base_reg, 0, 1)[..., None]
    out = np.clip(out, 0, 255)

    # --- print the label ---
    lab = M.load_label(label_svg)
    lab_pm, phi = M.project(lab)
    reg = out[M.RY0:M.RY1, M.RX0:M.RX1].copy()
    reg_photo = photo[M.RY0:M.RY1, M.RX0:M.RX1]
    res = M.composite(reg, lab_pm, phi, reg_photo, ink_opacity=0.96, hl_over_ink=0.5, seed=seed)
    out[M.RY0:M.RY1, M.RX0:M.RX1] = res
    Image.fromarray(np.clip(out, 0, 255).round().astype(np.uint8)).save(out_file)
    return out


if __name__ == "__main__":
    render()
    print("ok")
