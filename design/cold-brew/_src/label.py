"""Flat bottle-print artwork in cylinder coordinates.

Units: u = arc length from the front centre line, s = height; both in
"front pixels" of the photo (1 unit ~ 1 px at the front of the bottle).
SVG x = u + UX, SVG y = s - SY.
"""
import json
import math

from textpath import text_path

UX, SY = 400.0, 600.0          # SVG origin offset
W, H = 800.0, 1300.0           # SVG size (u -400..400, s 600..1900)

RUBY = "#b8162f"
RUBY_DARK = "#8a0f22"
INK = "#ffffff"

logo = json.load(open("logo_parts_local.json"))
LW, LH = logo["w"], logo["h"]   # 1058 x 676


def logo_group(cu, cs, width_u, variant="color"):
    """Logo rotated 90deg CCW (reads bottom-to-top), centred at (cu, cs)."""
    sc = width_u / LH
    x, y = cu + UX, cs - SY
    tf = f"translate({x:.2f} {y:.2f}) rotate(-90) scale({sc:.5f}) translate({-LW / 2:.2f} {-LH / 2:.2f})"
    if variant == "color":
        gx0, gx1 = logo["grad_x"]
        a, b = logo["hl_a"], logo["hl_b"]
        defs = (f'<linearGradient id="cb-jog" gradientUnits="userSpaceOnUse" x1="{gx0:.2f}" y1="0" x2="{gx1:.2f}" y2="0">'
                '<stop offset="0" stop-color="#686868"/><stop offset=".126" stop-color="#5f5f5f"/>'
                '<stop offset=".3" stop-color="#5a5a5a"/><stop offset=".425" stop-color="#474747"/>'
                '<stop offset=".644" stop-color="#3c3c3c"/><stop offset=".747" stop-color="#484848"/>'
                '<stop offset=".845" stop-color="#6e6e6e"/><stop offset=".931" stop-color="#8f8f8f"/>'
                '<stop offset="1" stop-color="#a0a0a0"/></linearGradient>'
                f'<linearGradient id="cb-hl" gradientUnits="userSpaceOnUse" x1="{a[0]:.2f}" y1="{a[1]:.2f}" x2="{b[0]:.2f}" y2="{b[1]:.2f}">'
                '<stop offset="0" stop-color="#fff" stop-opacity=".42"/><stop offset="1" stop-color="#fff" stop-opacity="0"/>'
                '</linearGradient>')
        body = (f'<g transform="{tf}"><path fill="url(#cb-jog)" d="{logo["shade"]}"/>'
                f'<path fill="url(#cb-hl)" d="{logo["hl"]}"/>'
                f'<path fill="{INK}" fill-rule="evenodd" d="{logo["letters"]}"/>'
                f'<path fill="{INK}" d="{logo["bolt"]}"/>'
                f'<path fill="#bdbdbd" d="{logo["crease"]}"/></g>')
    else:
        defs = ""
        body = (f'<g transform="{tf}" fill="{INK}"><path d="{logo["shade"]}"/>'
                f'<path fill-rule="evenodd" d="{logo["letters"]}"/><path d="{logo["bolt"]}"/></g>')
    return defs, body


def P(u, s):
    return f"{u + UX:.2f} {s - SY:.2f}"


def build(cfg=None):
    c = dict(
        logo_center_s=1200.0, logo_width=300.0,
        desc_s=1545.0, desc_size=14.0, desc_track=0.12,
        band_top=1562.0, band_h=54.0, band_w=244.0, band_skew=15.0,
        flavor_size=43.0, flavor_track=0.07,
        vol_s=1658.0, vol_size=21.0, rule_len=58.0, rule_gap=12.0, rule_w=1.6,
    )
    if cfg:
        c.update(cfg)
    defs, logo_body = logo_group(0.0, c["logo_center_s"], c["logo_width"])
    parts = []
    # --- descriptor ---
    d, bb, w = text_path("Exo2_600i", "КОФЕЙНЫЙ ТОНИЗИРУЮЩИЙ НАПИТОК", c["desc_size"],
                         x=UX, y=c["desc_s"] - SY, anchor="middle", tracking=c["desc_track"])
    parts.append(f'<path fill="{INK}" fill-opacity=".92" d="{d}"/>')
    desc_w = w
    # --- ruby band (parallelogram, italic like the logo) ---
    t = math.tan(math.radians(c["band_skew"]))
    top, h, bw = c["band_top"], c["band_h"], c["band_w"]
    dx = t * h / 2
    band = [(-bw / 2 + dx, top), (bw / 2 + dx, top), (bw / 2 - dx, top + h), (-bw / 2 - dx, top + h)]
    parts.append('<linearGradient id="ruby" x1="0" y1="0" x2="0" y2="1">'
                 f'<stop offset="0" stop-color="#c91d38"/><stop offset="1" stop-color="{RUBY_DARK}"/></linearGradient>')
    parts.append('<path fill="url(#ruby)" d="M' + "L".join(P(u, s) for u, s in band) + 'Z"/>')
    # flavour text, optically centred on cap height
    cap = 0.7  # Russo One cap height / em (approx; refined below)
    base = top + h / 2 + c["flavor_size"] * cap / 2
    d, bb, w = text_path("RussoOne", "ГРАНАТ", c["flavor_size"], x=UX, y=base - SY,
                         anchor="middle", tracking=c["flavor_track"], skew_deg=c["band_skew"])
    # re-centre using real bbox
    cy = (bb[1] + bb[3]) / 2
    cx = (bb[0] + bb[2]) / 2
    shift_y = (top + h / 2 - SY) - cy
    shift_x = UX - cx
    parts.append(f'<path fill="{INK}" transform="translate({shift_x:.2f} {shift_y:.2f})" d="{d}"/>')
    # --- volume with rules ---
    d, bb, w = text_path("RussoOne", "280 мл", c["vol_size"], x=UX, y=c["vol_s"] - SY,
                         anchor="middle", tracking=0.04, skew_deg=c["band_skew"])
    cx = (bb[0] + bb[2]) / 2
    parts.append(f'<path fill="{INK}" transform="translate({UX - cx:.2f} 0)" d="{d}"/>')
    half = (bb[2] - bb[0]) / 2
    ymid = (bb[1] + bb[3]) / 2
    for sgn in (-1, 1):
        x0 = UX + sgn * (half + c["rule_gap"])
        x1 = UX + sgn * (half + c["rule_gap"] + c["rule_len"])
        parts.append(f'<path stroke="{INK}" stroke-width="{c["rule_w"]}" stroke-linecap="round" '
                     f'd="M{x0:.2f} {ymid:.2f}L{x1:.2f} {ymid:.2f}"/>')
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W:.0f} {H:.0f}" width="{W:.0f}" height="{H:.0f}">'
           f"<defs>{defs}</defs>{logo_body}{''.join(parts)}</svg>")
    return svg, {"desc_w": desc_w}


if __name__ == "__main__":
    import cairosvg
    svg, info = build()
    open("label_flat.svg", "w").write(svg)
    print(info)
    # preview on coffee-coloured background, cropped to the printed area
    bg = svg.replace('<defs>', f'<rect width="{W}" height="{H}" fill="#24130d"/><defs>', 1)
    cairosvg.svg2png(bytestring=bg.encode(), write_to="label_preview.png", output_width=800)
