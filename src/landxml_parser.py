"""
LandXML parser — horizontal (CoordGeom) and vertical (ProfAlign) alignment.
Outputs discretized point lists for interpolation.
"""

import xml.etree.ElementTree as ET
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

STEP = 0.5  # discretization interval in metres


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class HPoint:
    ch: float   # chainage
    E: float    # Easting
    N: float    # Northing
    az: float   # forward azimuth in degrees (0=N, 90=E)


@dataclass
class VPoint:
    ch: float
    elev: float
    grade: float  # rise/run (e.g. 0.01 = 1 %)


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------

def _strip(tag: str) -> str:
    return tag.split('}')[-1] if '}' in tag else tag


def _children(elem, tag: str):
    return [e for e in elem if _strip(e.tag) == tag]


def _find_all(elem, tag: str):
    return [e for e in elem.iter() if _strip(e.tag) == tag]


def _parse_pt(text: str) -> Tuple[float, float]:
    """Parse 'N E' or 'N E Z' → (N, E)."""
    parts = text.strip().split()
    return float(parts[0]), float(parts[1])


def _azimuth(dN: float, dE: float) -> float:
    return math.degrees(math.atan2(dE, dN)) % 360


# ---------------------------------------------------------------------------
# Horizontal alignment
# ---------------------------------------------------------------------------

def _parse_horizontal(coord_geom, sta_start: float) -> List[HPoint]:
    raw: List[Tuple[float, float, float]] = []   # (ch, E, N)
    ch = sta_start

    for elem in coord_geom:
        tag = _strip(elem.tag)
        if tag not in ('Line', 'Curve', 'Spiral'):
            continue

        starts = _children(elem, 'Start')
        ends   = _children(elem, 'End')
        if not starts or not ends:
            continue

        N1, E1 = _parse_pt(starts[0].text)
        N2, E2 = _parse_pt(ends[0].text)

        if tag == 'Line':
            length = math.hypot(E2 - E1, N2 - N1)
            if length < 1e-9:
                continue
            n = max(int(math.ceil(length / STEP)), 1)
            for j in range(n + 1):
                t = j / n
                raw.append((ch + t * length,
                             E1 + t * (E2 - E1),
                             N1 + t * (N2 - N1)))
            ch += length

        elif tag == 'Curve':
            len_attr = elem.get('len') or elem.get('length')
            rot = (elem.get('rot') or 'ccw').lower()
            centers = _children(elem, 'Center')

            if centers and centers[0].text:
                Nc, Ec = _parse_pt(centers[0].text)
                r = math.hypot(E1 - Ec, N1 - Nc)

                # Standard math angle: atan2(y, x) = atan2(N-Nc, E-Ec)
                # CCW in plan view → theta increases  ✓
                # CW  in plan view → theta decreases  ✓
                # Point on circle: E = Ec + r*cos(θ), N = Nc + r*sin(θ)
                th1 = math.atan2(N1 - Nc, E1 - Ec)

                if len_attr:
                    arc = float(len_attr)
                    d_th = arc / r
                    th2 = th1 + (d_th if rot == 'ccw' else -d_th)
                else:
                    th2 = math.atan2(N2 - Nc, E2 - Ec)
                    d_th = th2 - th1
                    if rot == 'ccw':          # angle must increase
                        if d_th < 0:
                            d_th += 2 * math.pi
                    else:                     # CW: angle must decrease
                        if d_th > 0:
                            d_th -= 2 * math.pi
                    arc = r * abs(d_th)
                    th2 = th1 + d_th

                n = max(int(math.ceil(arc / STEP)), 1)
                for j in range(n + 1):
                    t = j / n
                    th = th1 + t * (th2 - th1)
                    raw.append((ch + t * arc,
                                Ec + r * math.cos(th),
                                Nc + r * math.sin(th)))
                ch += arc

            else:
                # No center — approximate as chord
                len_val = float(elem.get('len') or elem.get('length') or
                                math.hypot(E2 - E1, N2 - N1))
                n = max(int(math.ceil(len_val / STEP)), 1)
                for j in range(n + 1):
                    t = j / n
                    raw.append((ch + t * len_val,
                                E1 + t * (E2 - E1),
                                N1 + t * (N2 - N1)))
                ch += len_val

        elif tag == 'Spiral':
            len_attr = elem.get('len') or elem.get('length')
            length = float(len_attr) if len_attr else math.hypot(E2 - E1, N2 - N1)
            n = max(int(math.ceil(length / STEP)), 1)
            for j in range(n + 1):
                t = j / n
                raw.append((ch + t * length,
                             E1 + t * (E2 - E1),
                             N1 + t * (N2 - N1)))
            ch += length

    # Deduplicate (keep unique chainages)
    unique: List[Tuple[float, float, float]] = []
    for pt in raw:
        if not unique or abs(pt[0] - unique[-1][0]) > 1e-6:
            unique.append(pt)

    # Compute azimuths numerically from adjacent points
    result: List[HPoint] = []
    n = len(unique)
    for i, (c, E, N) in enumerate(unique):
        if n == 1:
            az = 0.0
        elif i == 0:
            dE = unique[1][1] - unique[0][1]
            dN = unique[1][2] - unique[0][2]
        elif i == n - 1:
            dE = unique[-1][1] - unique[-2][1]
            dN = unique[-1][2] - unique[-2][2]
        else:
            dE = unique[i + 1][1] - unique[i - 1][1]
            dN = unique[i + 1][2] - unique[i - 1][2]

        if n > 1:
            az = _azimuth(dN, dE)
        result.append(HPoint(ch=c, E=E, N=N, az=az))

    return result


# ---------------------------------------------------------------------------
# Vertical alignment
# ---------------------------------------------------------------------------

def _parse_vertical(prof_align) -> Optional[List[VPoint]]:
    pvi_elems = _find_all(prof_align, 'PVI')
    if len(pvi_elems) < 2:
        return None

    pvis = []
    for elem in pvi_elems:
        text = (elem.text or '').strip().split()
        if len(text) < 2:
            continue
        ch, el = float(text[0]), float(text[1])
        pc = _children(elem, 'ParaCurve')
        pvc_len = float(pc[0].get('len', 0)) if pc else 0.0
        pvis.append({'ch': ch, 'elev': el, 'pvc_len': pvc_len})

    if len(pvis) < 2:
        return None

    raw: List[VPoint] = []
    for i in range(len(pvis) - 1):
        p1, p2 = pvis[i], pvis[i + 1]
        dch = p2['ch'] - p1['ch']
        if dch <= 0:
            continue
        g = (p2['elev'] - p1['elev']) / dch
        n = max(int(math.ceil(dch / STEP)), 1)
        for j in range(n):
            t = j / n
            raw.append(VPoint(ch=p1['ch'] + t * dch,
                               elev=p1['elev'] + t * (p2['elev'] - p1['elev']),
                               grade=g))

    # Add final PVI
    last = pvis[-1]
    raw.append(VPoint(ch=last['ch'], elev=last['elev'],
                       grade=raw[-1].grade if raw else 0.0))

    return raw


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def parse_landxml(xml_bytes: bytes) -> dict:
    """
    Parse a LandXML file.

    Returns:
        {
          'horizontal': List[HPoint],
          'vertical':   List[VPoint] | None,
          'sta_start':  float
        }
    """
    root = ET.fromstring(xml_bytes)

    alignments = _find_all(root, 'Alignment')
    if not alignments:
        raise ValueError("LandXML dosyasında 'Alignment' bulunamadı.")

    align = alignments[0]
    sta_start = float(align.get('staStart', 0))

    coord_geoms = _find_all(align, 'CoordGeom')
    if not coord_geoms:
        raise ValueError("Alignment içinde 'CoordGeom' bulunamadı.")

    h_points = _parse_horizontal(coord_geoms[0], sta_start)
    if not h_points:
        raise ValueError("Yatay hizalama noktaları hesaplanamadı.")

    prof_aligns = _find_all(align, 'ProfAlign')
    v_points = _parse_vertical(prof_aligns[0]) if prof_aligns else None

    return {
        'horizontal': h_points,
        'vertical': v_points,
        'sta_start': sta_start,
    }
