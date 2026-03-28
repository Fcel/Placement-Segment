"""
Placement of Tunnel Segment — Streamlit App
"""

import io
import streamlit as st
from src.landxml_parser     import parse_landxml
from src.segment_calculator import calculate_segments
from src.dxf_generator      import generate_dxf

st.set_page_config(
    page_title="Tunnel Segment Placement",
    page_icon="🚇",
    layout="centered",
)

st.title("🚇 Tunnel Segment Placement")
st.caption("LandXML hizalamasından otomatik segment yerleşimi — DXF çıktısı")

# ── 1. LandXML upload ──────────────────────────────────────────────────────
st.subheader("1 · LandXML Dosyası")
uploaded = st.file_uploader("XML / LandXML dosyası seçin", type=["xml", "landxml"])

# ── 2. Parameters ──────────────────────────────────────────────────────────
st.subheader("2 · Segment Parametreleri")

col1, col2 = st.columns(2)
with col1:
    start_ch    = st.number_input("Başlangıç Chainagei (m)", value=0.0, step=0.001, format="%.3f")
    seg_width   = st.number_input("Segment Genişliği (m)",   value=1.500, step=0.001, format="%.3f", min_value=0.001)
    tunnel_dia  = st.number_input("Tünel Çapı (m)",          value=6.300, step=0.001, format="%.3f", min_value=0.001)

with col2:
    ring_mode = st.radio("Ring sınırı", ["Ring Sayısı", "Bitiş Chainagei"], horizontal=True)
    if ring_mode == "Ring Sayısı":
        num_rings = st.number_input("Ring Sayısı", value=100, min_value=1, step=1)
        end_ch    = None
    else:
        end_ch    = st.number_input("Bitiş Chainagei (m)", value=0.0, step=0.001, format="%.3f")
        num_rings = None

    ring_prefix = st.text_input("Ring Ön Eki", value="R", max_chars=10)

# ── Resolve num_rings ───────────────────────────────────────────────────────
def resolve_num_rings():
    if num_rings is not None:
        return int(num_rings)
    delta = end_ch - start_ch
    if delta <= 0:
        st.error("Bitiş chainagei başlangıçtan büyük olmalı.")
        return None
    return max(1, int(round(delta / seg_width)))

# ── 3. Actions ─────────────────────────────────────────────────────────────
st.subheader("3 · İşlem")

col_prev, col_gen = st.columns(2)

# Preview
with col_prev:
    if st.button("📋 Önizle", use_container_width=True):
        if not uploaded:
            st.error("LandXML dosyası yüklenmedi.")
        else:
            n = resolve_num_rings()
            if n:
                with st.spinner("Hesaplanıyor…"):
                    try:
                        aln  = parse_landxml(uploaded.read())
                        segs = calculate_segments(
                            aln, start_ch=start_ch, seg_width=seg_width,
                            num_rings=n, ring_prefix=ring_prefix or "R"
                        )
                        st.session_state["segs"] = segs
                        st.success(f"Toplam {len(segs)} yüzey hesaplandı.")
                    except Exception as e:
                        st.error(str(e))

# Generate DXF
with col_gen:
    if st.button("⬇️ DXF Oluştur", use_container_width=True, type="primary"):
        if not uploaded:
            st.error("LandXML dosyası yüklenmedi.")
        else:
            n = resolve_num_rings()
            if n:
                with st.spinner("DXF üretiliyor…"):
                    try:
                        uploaded.seek(0)
                        aln  = parse_landxml(uploaded.read())
                        segs = calculate_segments(
                            aln, start_ch=start_ch, seg_width=seg_width,
                            num_rings=n, ring_prefix=ring_prefix or "R"
                        )
                        buf = generate_dxf(segs, tunnel_diameter=tunnel_dia)
                        st.session_state["dxf_buf"]  = buf.read()
                        st.session_state["dxf_name"] = f"tunnel_segments_{ring_prefix or 'R'}.dxf"
                    except Exception as e:
                        st.error(str(e))

# Download button (persists after rerun)
if "dxf_buf" in st.session_state:
    st.download_button(
        label="💾 DXF İndir",
        data=st.session_state["dxf_buf"],
        file_name=st.session_state["dxf_name"],
        mime="application/octet-stream",
        use_container_width=True,
    )

# ── 4. Preview table ────────────────────────────────────────────────────────
if "segs" in st.session_state:
    segs = st.session_state["segs"]
    st.subheader("4 · Önizleme (ilk 20 yüzey)")

    import pandas as pd
    rows = [
        {
            "No":          s["no"],
            "İsim":        s["name"],
            "Chainage (m)": round(s["ch"],   3),
            "Easting (m)":  round(s["E"],    3),
            "Northing (m)": round(s["N"],    3),
            "Elev (m)":     round(s["elev"], 3) if s["elev"] is not None else "—",
            "Azimuth (°)":  round(s["az"],   4),
            "Zenith (°)":   round(s["za"],   4) if s["za"]  is not None else "—",
        }
        for s in segs[:20]
    ]
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)
