"""
Placement of Tunnel Segment — Web Application
Flask backend: accepts LandXML + parameters, returns DXF.
"""

import traceback
from flask import Flask, request, send_file, render_template, jsonify

from src.landxml_parser    import parse_landxml
from src.segment_calculator import calculate_segments
from src.dxf_generator     import generate_dxf

app = Flask(__name__)
app.config['MAX_CONTENT_LENGTH'] = 32 * 1024 * 1024   # 32 MB


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/')
def index():
    return render_template('index.html')


@app.route('/preview', methods=['POST'])
def preview():
    """Return first 20 segments as JSON (for the on-page table preview)."""
    try:
        xml_bytes, params = _parse_request()
        alignment = parse_landxml(xml_bytes)
        segs = calculate_segments(alignment, **params)

        rows = [
            {
                'no':       s['no'],
                'name':     s['name'],
                'ch':       round(s['ch'],   3),
                'E':        round(s['E'],    3),
                'N':        round(s['N'],    3),
                'elev':     round(s['elev'], 3) if s['elev'] is not None else '—',
                'az':       round(s['az'],   4),
                'za':       round(s['za'],   4) if s['za']  is not None else '—',
            }
            for s in segs[:20]
        ]
        return jsonify({'total': len(segs), 'rows': rows})

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'Beklenmeyen hata: {e}'}), 500


@app.route('/generate', methods=['POST'])
def generate():
    """Generate and return the DXF file."""
    try:
        xml_bytes, params = _parse_request()
        alignment = parse_landxml(xml_bytes)
        segs      = calculate_segments(alignment, **params)
        dxf_buf   = generate_dxf(segs, float(request.form['tunnel_diameter']))

        filename = f"tunnel_segments_{params['ring_prefix']}.dxf"
        return send_file(
            dxf_buf,
            mimetype='application/octet-stream',
            as_attachment=True,
            download_name=filename,
        )

    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    except Exception as e:
        traceback.print_exc()
        return jsonify({'error': f'Beklenmeyen hata: {e}'}), 500


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _parse_request():
    """Extract and validate file + form parameters."""
    f = request.files.get('landxml')
    if not f or f.filename == '':
        raise ValueError('LandXML dosyası seçilmedi.')

    xml_bytes = f.read()

    start_ch         = float(request.form['start_ch'])
    seg_width        = float(request.form['seg_width'])
    tunnel_diameter  = float(request.form['tunnel_diameter'])
    ring_prefix      = request.form.get('ring_prefix', 'R').strip() or 'R'

    num_rings_str = request.form.get('num_rings', '').strip()
    end_ch_str    = request.form.get('end_ch',    '').strip()

    if num_rings_str:
        num_rings = int(num_rings_str)
    elif end_ch_str:
        end_ch    = float(end_ch_str)
        num_rings = int(round((end_ch - start_ch) / seg_width))
    else:
        raise ValueError('Ring sayısı veya bitiş chainagei girilmedi.')

    if seg_width <= 0:
        raise ValueError('Segment genişliği 0\'dan büyük olmalı.')
    if num_rings <= 0:
        raise ValueError('Ring sayısı 0\'dan büyük olmalı.')
    if tunnel_diameter <= 0:
        raise ValueError('Tünel çapı 0\'dan büyük olmalı.')

    params = dict(
        start_ch    = start_ch,
        seg_width   = seg_width,
        num_rings   = num_rings,
        ring_prefix = ring_prefix,
    )
    return xml_bytes, params


if __name__ == '__main__':
    app.run(debug=True, port=5000)
