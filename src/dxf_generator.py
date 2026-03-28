"""
DXF generator — plan view + profile view.

Mirrors the two VBA subroutines:
  PTSPlanByPolyline2D    → plan view (E, N coordinates)
  PTSProfileByPolyline2D → profile view (Chainage, Elevation)
"""

import io
import math
from typing import List, Dict, Any, Optional

import ezdxf
from ezdxf.enums import TextEntityAlignment


# ---------------------------------------------------------------------------
# Geometry helpers (identical logic to VBA's PvCoorYXtoNE)
# ---------------------------------------------------------------------------

def _offset_perpendicular(E: float, N: float, az_deg: float, offset: float):
    """
    Return point offset perpendicularly (right = +) to the direction az_deg.

    Formula: same as VBA PvCoorYXtoNE(ECL, NCL, AZ, Y=0, X=offset, "E"/"N")
      E_out = E + offset * sin(az + 90) = E + offset * cos(az)
      N_out = N + offset * cos(az + 90) = N - offset * sin(az)
    """
    az = math.radians(az_deg)
    return (E + offset * math.cos(az),
            N - offset * math.sin(az))


# ---------------------------------------------------------------------------
# Layer definitions
# ---------------------------------------------------------------------------

LAYERS = {
    'CENTER':  {'color': 7, 'linetype': 'CONTINUOUS'},   # white
    'WALL':    {'color': 5, 'linetype': 'CONTINUOUS'},   # blue
    'SEGMENT': {'color': 3, 'linetype': 'CONTINUOUS'},   # green
    'TEXT':    {'color': 2, 'linetype': 'CONTINUOUS'},   # yellow
}

LAYER_CENTER  = 'TUN-CENTER'
LAYER_WALL    = 'TUN-WALL'
LAYER_SEGMENT = 'TUN-SEGMENT'
LAYER_TEXT    = 'TUN-TEXT'


# ---------------------------------------------------------------------------
# Text helper
# ---------------------------------------------------------------------------

def _add_text(msp, text: str, x: float, y: float,
              height: float, rotation: float, layer: str):
    t = msp.add_text(text, dxfattribs={
        'layer':    layer,
        'height':   height,
        'rotation': rotation,
    })
    t.set_placement((x, y), align=TextEntityAlignment.MIDDLE_CENTER)


# ---------------------------------------------------------------------------
# Plan view
# ---------------------------------------------------------------------------

def _draw_plan(msp, segs: List[Dict], radius: float):
    if len(segs) < 2:
        return

    # Compute left / right wall points for each face
    for s in segs:
        s['_EL'], s['_NL'] = _offset_perpendicular(s['E'], s['N'], s['az'], -radius)
        s['_ER'], s['_NR'] = _offset_perpendicular(s['E'], s['N'], s['az'],  radius)

    # Centreline polyline
    msp.add_lwpolyline(
        [(s['E'], s['N']) for s in segs],
        dxfattribs={'layer': LAYER_CENTER})

    # Left-wall polyline
    msp.add_lwpolyline(
        [(s['_EL'], s['_NL']) for s in segs],
        dxfattribs={'layer': LAYER_WALL})

    # Right-wall polyline
    msp.add_lwpolyline(
        [(s['_ER'], s['_NR']) for s in segs],
        dxfattribs={'layer': LAYER_WALL})

    # Segment cross-section lines (face lines)
    for s in segs:
        msp.add_line(
            (s['_EL'], s['_NL'], 0),
            (s['_ER'], s['_NR'], 0),
            dxfattribs={'layer': LAYER_SEGMENT})

    # Ring-name labels at midpoint between consecutive faces
    text_h = max(radius * 0.25, 0.1)
    for i in range(1, len(segs)):
        s0, s1 = segs[i - 1], segs[i]
        mid_E = (s0['E'] + s1['E']) / 2
        mid_N = (s0['N'] + s1['N']) / 2
        rot   = 90 - s1['az']           # AutoCAD angle from East-axis
        _add_text(msp, s1['name'], mid_E, mid_N, text_h, rot, LAYER_TEXT)


# ---------------------------------------------------------------------------
# Profile view
# ---------------------------------------------------------------------------

def _profile_offset_pt(ch_rel: float, elev: float,
                        za_deg: float, offset: float, base_N: float):
    """
    Offset perpendicular to the profile direction.
    Uses the same PvCoorYXtoNE formula with CH→E, EL→N, ZA→AZ.
    Returns (CH_out, EL_out) in profile-space, then shifts EL by base_N.
    """
    za = math.radians(za_deg)
    ch_out = ch_rel + offset * math.cos(za)
    el_out = elev   - offset * math.sin(za) + base_N
    return ch_out, el_out


def _draw_profile(msp, segs: List[Dict], radius: float, base_N: float):
    """
    Draw the profile (longitudinal section).
    X-axis = relative chainage (ch - ch_ref), Y-axis = elevation + base_N.
    base_N pushes the profile below the plan view in model space.
    """
    if len(segs) < 2 or segs[0]['elev'] is None:
        return

    ch_ref = segs[0]['ch']

    for s in segs:
        ch_r = s['ch'] - ch_ref
        za   = s['za'] if s['za'] is not None else 90.0
        s['_CH_top'], s['_EL_top'] = _profile_offset_pt(ch_r, s['elev'], za, -radius, base_N)
        s['_CH_bot'], s['_EL_bot'] = _profile_offset_pt(ch_r, s['elev'], za,  radius, base_N)

    # Centreline polyline
    msp.add_lwpolyline(
        [(s['ch'] - ch_ref, s['elev'] + base_N) for s in segs],
        dxfattribs={'layer': LAYER_CENTER})

    # Top-wall polyline
    msp.add_lwpolyline(
        [(s['_CH_top'], s['_EL_top']) for s in segs],
        dxfattribs={'layer': LAYER_WALL})

    # Bottom-wall polyline
    msp.add_lwpolyline(
        [(s['_CH_bot'], s['_EL_bot']) for s in segs],
        dxfattribs={'layer': LAYER_WALL})

    # Segment face lines
    for s in segs:
        msp.add_line(
            (s['_CH_top'], s['_EL_top'], 0),
            (s['_CH_bot'], s['_EL_bot'], 0),
            dxfattribs={'layer': LAYER_SEGMENT})

    # Ring-name labels
    text_h = max(radius * 0.25, 0.1)
    for i in range(1, len(segs)):
        s0, s1 = segs[i - 1], segs[i]
        ch_mid = (s0['ch'] + s1['ch']) / 2 - ch_ref
        el_mid = (s0['elev'] + s1['elev']) / 2 + base_N
        za = s1['za'] if s1['za'] is not None else 90.0
        rot = 90 - za
        _add_text(msp, s1['name'], ch_mid, el_mid, text_h, rot, LAYER_TEXT)


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def generate_dxf(segs: List[Dict], tunnel_diameter: float) -> io.BytesIO:
    """
    Generate a DXF file containing:
      - Plan view  (E / N coordinates, model-space)
      - Profile view below the plan view (Chainage / Elevation)

    Returns a BytesIO buffer ready to send to the client.
    """
    doc = ezdxf.new('R2010')
    msp = doc.modelspace()

    # Create layers
    for name, attrs in {
        LAYER_CENTER:  {'color': 7},
        LAYER_WALL:    {'color': 5},
        LAYER_SEGMENT: {'color': 3},
        LAYER_TEXT:    {'color': 2},
    }.items():
        doc.layers.new(name, dxfattribs=attrs)

    radius = tunnel_diameter / 2.0

    # Plan view
    _draw_plan(msp, segs, radius)

    # Profile view — place below plan with gap = 3 × diameter
    has_profile = segs and segs[0].get('elev') is not None
    if has_profile:
        min_N   = min(s['N'] for s in segs)
        max_elev = max(s['elev'] for s in segs)
        gap     = tunnel_diameter * 3 + 20
        base_N  = min_N - gap - max_elev - radius
        _draw_profile(msp, segs, radius, base_N)

    text_buf = io.StringIO()
    doc.write(text_buf)
    buf = io.BytesIO(text_buf.getvalue().encode('utf-8'))
    buf.seek(0)
    return buf
