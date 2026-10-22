"""Text -> SVG path (outlined) with HarfBuzz shaping and fontTools outlines."""
import math
import os

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.pens.boundsPen import BoundsPen
from fontTools.ttLib import TTFont

FONT_DIR = os.environ.get("FONT_DIR", os.path.join(os.path.dirname(__file__), "fonts")) + "/"
_cache = {}


def _load(name):
    if name not in _cache:
        path = FONT_DIR + name + ".ttf"
        blob = hb.Blob.from_file_path(path)
        face = hb.Face(blob)
        font = hb.Font(face)
        tt = TTFont(path)
        _cache[name] = (font, face.upem, tt, tt.getGlyphSet(), tt.getGlyphOrder())
    return _cache[name]


def shape(name, text, size, tracking=0.0):
    font, upem, tt, gs, order = _load(name)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(font, buf, {"kern": True, "liga": True})
    s = size / upem
    glyphs = []
    x = 0.0
    n = len(buf.glyph_infos)
    for i, (info, pos) in enumerate(zip(buf.glyph_infos, buf.glyph_positions)):
        glyphs.append((order[info.codepoint], x + pos.x_offset * s, pos.y_offset * s))
        x += pos.x_advance * s
        if i < n - 1:
            x += tracking * size
    return glyphs, x


def metrics(name):
    font, upem, tt, gs, order = _load(name)
    os2 = tt["OS/2"]
    cap = getattr(os2, "sCapHeight", 0) or 0.7 * upem
    xh = getattr(os2, "sxHeight", 0) or 0.5 * upem
    return cap / upem, xh / upem


def text_path(name, text, size, x=0.0, y=0.0, anchor="middle", tracking=0.0, skew_deg=0.0):
    """Return (d, bbox) for text with baseline at y. anchor: start|middle|end."""
    font, upem, tt, gs, order = _load(name)
    glyphs, width = shape(name, text, size, tracking)
    if anchor == "middle":
        x0 = x - width / 2
    elif anchor == "end":
        x0 = x - width
    else:
        x0 = x
    s = size / upem
    sk = math.tan(math.radians(skew_deg))
    out = []
    bp_all = None
    for gname, gx, gy in glyphs:
        pen = SVGPathPen(gs)
        t = (s, 0, sk * s, -s, x0 + gx, y - gy)
        gs[gname].draw(TransformPen(pen, t))
        out.append(pen.getCommands())
        bp = BoundsPen(gs)
        gs[gname].draw(TransformPen(bp, t))
        if bp.bounds:
            b = bp.bounds
            bp_all = b if bp_all is None else (min(bp_all[0], b[0]), min(bp_all[1], b[1]),
                                                max(bp_all[2], b[2]), max(bp_all[3], b[3]))
    return " ".join(c for c in out if c), bp_all, width
