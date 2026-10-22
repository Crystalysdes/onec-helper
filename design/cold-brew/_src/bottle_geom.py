"""Camera/cylinder model of the bottle in photo.png (1170x2080).

Measured: silhouette centre cx(v) and half-width a(v) per image row v;
ellipse ratios at the cap (-0.36) and base (+0.38) give focal length f and
the horizon row y_h.  Points on the cylinder are (phi, v): phi = angle from
the front, v = image row of that circle's silhouette.
Label coordinates (u, s) are "front pixels": u = R_LABEL * phi, s = row of
the circle's front-most point.
"""
import numpy as np

F = 1984.0
YH = 1044.0
R_LABEL = 252.0


def cx(v):
    return 333.5 + 0.0237 * (v - 1000.0)


def a(v):
    return 219.5 + 0.0137 * (v - 1000.0)


def rho(v):
    av = a(v)
    return av / np.sqrt(F * F + av * av)


def forward(u, s):
    """label (u, s) -> image (x, y)"""
    phi = u / R_LABEL
    v = YH + (s - YH) / (1.0 + rho(s))
    for _ in range(3):
        v = YH + (s - YH) / (1.0 + rho(v))
    r = rho(v)
    x = cx(v) + a(v) * np.sqrt(1 - r * r) * np.sin(phi) / (1 - r * np.cos(phi))
    y = YH + (v - YH) * (1 - r * r) / (1 - r * np.cos(phi))
    return x, y


def inverse(x, y, iters=6):
    """image (x, y) -> label (u, s), visibility mask, phi, v"""
    x = np.asarray(x, float)
    y = np.asarray(y, float)
    v = y.copy()
    phi = np.zeros_like(x)
    for _ in range(iters):
        r = rho(v)
        A = a(v) * np.sqrt(1 - r * r)
        t = (x - cx(v)) / A
        q = t / np.sqrt(1 + (t * r) ** 2)
        q = np.clip(q, -1, 1)
        phi = np.arcsin(q) - np.arctan2(t * r, 1.0)
        v = YH + (y - YH) * (1 - r * np.cos(phi)) / (1 - r * r)
    r = rho(v)
    s = YH + (v - YH) * (1 + r)
    u = R_LABEL * phi
    vis = np.cos(phi) > r + 0.02
    return u, s, vis, phi, v
