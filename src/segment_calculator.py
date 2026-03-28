"""
Segment (ring) placement along a parsed LandXML alignment.

Each ring is represented by the position of its face (the joint between rings),
following the same data model as the original VBA program:
  No, Name, Chainage, Easting, Northing, Elevation, Azimuth, ZenithAngle
"""

import math
from typing import List, Dict, Any, Optional
from src.landxml_parser import HPoint, VPoint


# ---------------------------------------------------------------------------
# Interpolation helpers
# ---------------------------------------------------------------------------

def _interp_h(pts: List[HPoint], ch: float):
    """Return (E, N, az) at chainage ch."""
    if ch <= pts[0].ch:
        p = pts[0]
        return p.E, p.N, p.az
    if ch >= pts[-1].ch:
        p = pts[-1]
        return p.E, p.N, p.az

    lo, hi = 0, len(pts) - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if pts[mid].ch <= ch:
            lo = mid
        else:
            hi = mid

    p1, p2 = pts[lo], pts[hi]
    t = (ch - p1.ch) / (p2.ch - p1.ch)

    E  = p1.E  + t * (p2.E  - p1.E)
    N  = p1.N  + t * (p2.N  - p1.N)

    # Angular interpolation (handles 359→1 wrap)
    d = p2.az - p1.az
    if d >  180: d -= 360
    if d < -180: d += 360
    az = (p1.az + t * d) % 360

    return E, N, az


def _interp_v(pts: Optional[List[VPoint]], ch: float):
    """Return (elev, grade) at chainage ch, or (None, None) if no profile."""
    if not pts:
        return None, None
    if ch <= pts[0].ch:
        p = pts[0]; return p.elev, p.grade
    if ch >= pts[-1].ch:
        p = pts[-1]; return p.elev, p.grade

    lo, hi = 0, len(pts) - 1
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if pts[mid].ch <= ch:
            lo = mid
        else:
            hi = mid

    p1, p2 = pts[lo], pts[hi]
    t = (ch - p1.ch) / (p2.ch - p1.ch)
    elev  = p1.elev  + t * (p2.elev  - p1.elev)
    grade = p1.grade + t * (p2.grade - p1.grade)
    return elev, grade


# ---------------------------------------------------------------------------
# Zenith-angle helper  (mirrors VBA DirecDistAz used on CH/EL pairs)
# ---------------------------------------------------------------------------

def _profile_azimuth(dCH: float, dEL: float) -> float:
    """
    Azimuth in the profile plane treating chainage as 'Easting' and
    elevation as 'Northing' — exactly as the VBA does.
    Result ≈ 90° for a flat tunnel.
    """
    if dCH == 0 and dEL == 0:
        return 90.0
    if dEL != 0:
        Q = math.degrees(math.atan(dCH / dEL))
    if dEL == 0:
        return 90.0 if dCH > 0 else 270.0
    elif dEL > 0:
        return Q if dCH >= 0 else 360.0 + Q
    else:
        return 180.0 + Q


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def calculate_segments(alignment: dict,
                        start_ch: float,
                        seg_width: float,
                        num_rings: int,
                        ring_prefix: str) -> List[Dict[str, Any]]:
    """
    Returns a list of dicts, one per ring-face position (num_rings+1 entries).

    Keys: no, name, ch, E, N, elev, az, za
    """
    h_pts = alignment['horizontal']
    v_pts = alignment.get('vertical')

    ch_min = h_pts[0].ch
    ch_max = h_pts[-1].ch
    end_ch = start_ch + num_rings * seg_width

    if start_ch < ch_min or end_ch > ch_max + 1e-3:
        raise ValueError(
            f"İstenen chainage aralığı ({start_ch:.3f} – {end_ch:.3f}) "
            f"hizalamanın dışında ({ch_min:.3f} – {ch_max:.3f})."
        )

    segs: List[Dict] = []

    for i in range(num_rings + 1):
        ch = start_ch + i * seg_width
        E, N, az = _interp_h(h_pts, ch)
        elev, _  = _interp_v(v_pts, ch)

        # Ring name: prefix + zero-padded index (face 0 = start face)
        name = f"{ring_prefix}{i:03d}"

        segs.append({
            'no':   i,
            'name': name,
            'ch':   ch,
            'E':    E,
            'N':    N,
            'elev': elev,
            'az':   az,
            'za':   None,   # computed below
        })

    # Compute zenith angles from adjacent faces
    for i, s in enumerate(segs):
        if s['elev'] is None:
            continue
        prev = segs[i - 1] if i > 0 else segs[0]
        nxt  = segs[i + 1] if i < len(segs) - 1 else segs[-1]
        dCH = nxt['ch']   - prev['ch']
        dEL = nxt['elev'] - prev['elev']
        s['za'] = _profile_azimuth(dCH, dEL)

    return segs
