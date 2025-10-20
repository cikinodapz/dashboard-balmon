import streamlit as st
import pandas as pd
import folium
from folium.plugins import MarkerCluster, MiniMap, MeasureControl, Fullscreen
from streamlit_folium import st_folium
from geopy.distance import great_circle
import openpyxl  # Untuk load Excel
from typing import Dict

# Util DB opsional
try:
    from db_utils import get_engine_from_params, write_dataframe
except Exception:
    get_engine_from_params = None  # type: ignore
    write_dataframe = None  # type: ignore

# Konfigurasi halaman: gunakan lebar penuh
st.set_page_config(page_title="Dashboard Link Stasiun Radio", page_icon="🗺️", layout="wide")

# CSS ringan untuk merentangkan konten hingga mendekati tepi layar
st.markdown(
    """
    <style>
    .main .block-container { max-width: 100%; padding-left: 1rem; padding-right: 1rem; }
    /* Rapikan jarak heading */
    h1, h2, h3 { margin-top: 0.2rem; }
    /* Sidebar sedikit lebih lebar agar kontrol nyaman */
    section[data-testid="stSidebar"] > div { width: 320px; }
    </style>
    """,
    unsafe_allow_html=True,
)

# Helper untuk render peta Folium di Streamlit
def render_map(df_to_plot):
    if df_to_plot is None or df_to_plot.empty:
        st.warning("Tidak ada data untuk dipetakan.")
        return

    # Peta dengan beberapa basemap ala "Google-like"
    m = folium.Map(location=[-0.3, 100.4], zoom_start=12, tiles=None)
    # Basemaps (dengan atribusi eksplisit untuk menghindari error)
    folium.TileLayer('CartoDB Voyager', name='Street (Voyager)', control=True).add_to(m)
    folium.TileLayer('OpenStreetMap', name='OSM Standard', control=True).add_to(m)
    # Esri Street
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
        attr='Tiles © Esri — Source: Esri, HERE, Garmin, USGS, NGA, NASA, EPA, NPS, USDA',
        name='Street (Esri)', control=True
    ).add_to(m)
    # Esri Satellite Imagery
    folium.TileLayer(
        tiles='https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        attr='Tiles © Esri — Source: Esri, Maxar, Earthstar Geographics, and the GIS User Community',
        name='Satellite (Esri)', control=True
    ).add_to(m)

    # Controls for better UX
    Fullscreen(position='topleft').add_to(m)
    MiniMap(toggle_display=True, position='bottomright').add_to(m)
    MeasureControl(position='topleft', primary_length_unit='kilometers').add_to(m)
    marker_cluster = MarkerCluster().add_to(m)

    # Iterasi baris untuk marker dan link
    for _, row in df_to_plot.iterrows():
        popup_main = f"{row['STN_NAME']}<br>Frekuensi: {row.get('FREQ', '')}<br>Jarak: {row.get('CIRCUIT_LEN', '')} km"
        folium.Marker(
            [row['LAT_DEC'], row['LONG_DEC']],
            popup=popup_main,
            tooltip=row['STN_NAME'],
            icon=folium.Icon(color='blue', icon='info-sign')
        ).add_to(marker_cluster)

        popup_to = f"{row['STASIUN_LAWAN']}<br>Frekuensi Pair: {row.get('FREQ_PAIR', '')}"
        folium.Marker(
            [row['TO_LAT_DEC'], row['TO_LONG_DEC']],
            popup=popup_to,
            tooltip=row['STASIUN_LAWAN'],
            icon=folium.Icon(color='green', icon='ok-sign')
        ).add_to(marker_cluster)

        # Warna link berdasarkan masa berlaku (aman terhadap format tanggal)
        masa = pd.to_datetime(row.get('MASA_LAKU'), errors='coerce')
        today = pd.Timestamp.today().normalize()
        color = 'red' if pd.notna(masa) and masa < today else 'blue'

        folium.PolyLine(
            [[row['LAT_DEC'], row['LONG_DEC']], [row['TO_LAT_DEC'], row['TO_LONG_DEC']]],
            color=color, weight=2.5, opacity=1,
            popup=f"Jarak: {row.get('CIRCUIT_LEN', '')} km"
        ).add_to(m)

    # Sesuaikan view ke semua koordinat jika memungkinkan
    try:
        coords = list(zip(df_to_plot['LAT_DEC'], df_to_plot['LONG_DEC'])) + \
                 list(zip(df_to_plot['TO_LAT_DEC'], df_to_plot['TO_LONG_DEC']))
        if len(coords) > 0:
            m.fit_bounds(coords)
    except Exception:
        pass

    # Layer switcher
    folium.LayerControl(collapsed=False).add_to(m)
    # Sembunyikan attribution bawaan Leaflet (akan diganti caption di bawah)
    try:
        css_hide_attr = "<style>.leaflet-control-attribution{display:none !important;}</style>"
        m.get_root().html.add_child(folium.Element(css_hide_attr))
    except Exception:
        pass

    st_folium(m, height=600, use_container_width=True)
    # Caption kredit penyedia data/tile agar tetap patuh lisensi
    st.caption("Map data © OpenStreetMap contributors • Tiles © Esri, CartoDB, OSM • Imagery © Esri/Maxar")

# Fungsi untuk konversi DMS ke decimal (jika data masih DMS)
def dms_to_decimal(deg, min_, sec, dir_ind):
    decimal = deg + (min_ / 60) + (sec / 3600)
    if dir_ind in ['S', 'W']:
        decimal = -decimal
    return decimal

# Load data dari Excel
@st.cache_data
def load_data(file_path):
    df = pd.read_excel(file_path, sheet_name='Sheet2', header=0)
    # Konversi koordinat utama ke decimal jika belum
    df['LAT_DEC'] = df.apply(lambda row: dms_to_decimal(row['LAT_DEG'], row['LAT_MIN'], row['LAT_SEC'], row['LAT_DIR_IND']), axis=1)
    df['LONG_DEC'] = df.apply(lambda row: dms_to_decimal(row['LONG_DEG'], row['LONG_MIN'], row['LONG_SEC'], row['LONG_DIR_IND']), axis=1)
    # Sama untuk stasiun lawan
    df['TO_LAT_DEC'] = df.apply(lambda row: dms_to_decimal(row['TO_LAT_DEG'], row['TO_LAT_MIN'], row['TO_LAT_SEC'], row['TO_LAT_DIR_IND']), axis=1)
    df['TO_LONG_DEC'] = df.apply(lambda row: dms_to_decimal(row['TO_LONG_DEG'], row['TO_LONG_MIN'], row['TO_LONG_SEC'], row['TO_LONG_DIR_IND']), axis=1)
    # Hitung jarak awal jika CIRCUIT_LEN kosong
    df['CIRCUIT_LEN'] = df.apply(lambda row: round(great_circle((row['LAT_DEC'], row['LONG_DEC']), (row['TO_LAT_DEC'], row['TO_LONG_DEC'])).km, 3), axis=1)
    return df

# Path file Excel
file_path = "Data Site2.xlsx"
df = load_data(file_path)

# Sidebar untuk filter/edit
st.sidebar.title("Filter & Edit")
st.sidebar.caption("Pilih beberapa filter yang relevan.")

# Nonce untuk memastikan reset benar-benar membuat widget baru
if 'filter_nonce' not in st.session_state:
    st.session_state['filter_nonce'] = 0

# Tombol reset filter
FILTER_KEYS = [
    'f_appl', 'f_station_names', 'f_to_names',
    'f_freq', 'f_dist', 'f_date', 'f_expired'
]
if st.sidebar.button("Reset Filter", use_container_width=True):
    for k in FILTER_KEYS:
        if k in st.session_state:
            st.session_state.pop(k)
    # Ganti nonce supaya semua key widget berubah dan state lama tidak dipakai
    st.session_state['filter_nonce'] = st.session_state.get('filter_nonce', 0) + 1
    try:
        st.experimental_rerun()
    except Exception:
        pass

# Helper filter function
def apply_filters(source_df: pd.DataFrame) -> pd.DataFrame:
    out = source_df.copy()

    # APPL_ID
    nonce = st.session_state.get('filter_nonce', 0)

    if 'APPL_ID' in out:
        selected_appl = st.sidebar.multiselect(
            "APPL_ID",
            sorted(out['APPL_ID'].dropna().unique().tolist()),
            key=f'f_appl_{nonce}'
        )
        if selected_appl:
            out = out[out['APPL_ID'].isin(selected_appl)]

    # Nama stasiun
    if 'STN_NAME' in out:
        st.sidebar.divider()
        st.sidebar.subheader("Nama Stasiun")
        selected_names = st.sidebar.multiselect("Pilih STN_NAME", sorted(out['STN_NAME'].dropna().unique().tolist()), key=f'f_station_names_{nonce}')
        if selected_names:
            out = out[out['STN_NAME'].isin(selected_names)]

    # Stasiun lawan
    if 'STASIUN_LAWAN' in out:
        selected_to = st.sidebar.multiselect("Stasiun Lawan", sorted(out['STASIUN_LAWAN'].dropna().unique().tolist()), key=f'f_to_names_{nonce}')
        if selected_to:
            out = out[out['STASIUN_LAWAN'].isin(selected_to)]

    # Frekuensi range
    if 'FREQ' in out:
        st.sidebar.divider()
        st.sidebar.subheader("Frekuensi")
        # Coerce to numeric quietly
        freq_numeric = pd.to_numeric(out['FREQ'], errors='coerce')
        fmin = float(freq_numeric.min()) if pd.notna(freq_numeric.min()) else 0.0
        fmax = float(freq_numeric.max()) if pd.notna(freq_numeric.max()) else 0.0
        sel_min, sel_max = st.sidebar.slider(
            "Rentang FREQ",
            min_value=float(fmin),
            max_value=float(fmax) if fmax>fmin else float(fmin if fmin>0 else 1.0),
            value=(float(fmin), float(fmax) if fmax>fmin else float(fmin)),
            key=f'f_freq_{nonce}'
        )
        out = out[(pd.to_numeric(out['FREQ'], errors='coerce') >= sel_min) & (pd.to_numeric(out['FREQ'], errors='coerce') <= sel_max)]

    # Jarak (km)
    if 'CIRCUIT_LEN' in out:
        st.sidebar.subheader("Jarak (km)")
        dmin = float(out['CIRCUIT_LEN'].min()) if len(out) else 0.0
        dmax = float(out['CIRCUIT_LEN'].max()) if len(out) else 0.0
        dsel = st.sidebar.slider(
            "Rentang Jarak",
            min_value=float(0.0 if dmin> dmax else dmin),
            max_value=float(dmax if dmax> dmin else dmin if dmin>0 else 1.0),
            value=(float(dmin if dmax>=dmin else 0.0), float(dmax if dmax>=dmin else dmin)),
            key=f'f_dist_{nonce}'
        )
        out = out[(out['CIRCUIT_LEN'] >= dsel[0]) & (out['CIRCUIT_LEN'] <= dsel[1])]

    # Masa berlaku
    if 'MASA_LAKU' in out:
        st.sidebar.subheader("Masa Laku")
        show_only_expired = st.sidebar.checkbox("Hanya yang kadaluarsa", value=False, key=f'f_expired_{nonce}')
        date_series = pd.to_datetime(out['MASA_LAKU'], errors='coerce')
        # Range date picker (handle NaT)
        min_date = pd.Timestamp(date_series.min()) if pd.notna(date_series.min()) else pd.Timestamp('2000-01-01')
        max_date = pd.Timestamp(date_series.max()) if pd.notna(date_series.max()) else pd.Timestamp.today()
        dr = st.sidebar.date_input("Rentang Tanggal", value=(min_date.date(), max_date.date()), key=f'f_date_{nonce}')
        if isinstance(dr, tuple) and len(dr) == 2:
            start, end = pd.to_datetime(dr[0]), pd.to_datetime(dr[1]) + pd.Timedelta(days=1) - pd.Timedelta(seconds=1)
            mask_range = (date_series >= start) & (date_series <= end)
            out = out[mask_range.fillna(False)]
        if show_only_expired:
            out = out[pd.to_datetime(out['MASA_LAKU'], errors='coerce') < pd.Timestamp.today().normalize()]

    return out

# Apply filters
df_filtered = apply_filters(df)

# Header & deskripsi
st.title("Dashboard Link Stasiun Radio")
st.markdown("Kelola data stasiun, cek jarak & masa laku, dan lihat peta interaktif.")

# Metrik ringkas
total_links = len(df_filtered)
unique_sites = df_filtered['STN_NAME'].nunique() if 'STN_NAME' in df_filtered else total_links
avg_distance = float(df_filtered['CIRCUIT_LEN'].mean()) if 'CIRCUIT_LEN' in df_filtered else 0.0
expired_count = 0
if 'MASA_LAKU' in df_filtered:
    masa_series = pd.to_datetime(df_filtered['MASA_LAKU'], errors='coerce')
    expired_count = int((masa_series < pd.Timestamp.today().normalize()).sum())

col1, col2, col3, col4 = st.columns(4)
col1.metric("Total Link", f"{total_links}")
col2.metric("Unique Stasiun", f"{unique_sites}")
col3.metric("Rata-rata Jarak", f"{avg_distance:.1f} km")
col4.metric("Kadaluarsa", f"{expired_count}")

st.divider()

# Tabs: Peta, Tabel, Statistik
tab_map, tab_table, tab_stats = st.tabs(["Peta", "Tabel", "Statistik"])

with tab_map:
    st.subheader("Peta Link Stasiun")
    df_to_show = st.session_state.get('edited_df', df_filtered)
    render_map(df_to_show)

with tab_table:
    st.subheader("Tabel Data (Editable)")
    st.caption("Klik sel untuk ubah. Tambah baris baru jika perlu.")
    edited_df = st.data_editor(df_filtered, num_rows="dynamic", use_container_width=True)
    if st.button("Hitung Ulang & Simpan Perubahan"):
        # Update koordinat decimal dari edited data (jika user edit DMS)
        edited_df['LAT_DEC'] = edited_df.apply(lambda row: dms_to_decimal(row['LAT_DEG'], row['LAT_MIN'], row['LAT_SEC'], row['LAT_DIR_IND']), axis=1)
        edited_df['LONG_DEC'] = edited_df.apply(lambda row: dms_to_decimal(row['LONG_DEG'], row['LONG_MIN'], row['LONG_SEC'], row['LONG_DIR_IND']), axis=1)
        edited_df['TO_LAT_DEC'] = edited_df.apply(lambda row: dms_to_decimal(row['TO_LAT_DEG'], row['TO_LAT_MIN'], row['TO_LAT_SEC'], row['TO_LAT_DIR_IND']), axis=1)
        edited_df['TO_LONG_DEC'] = edited_df.apply(lambda row: dms_to_decimal(row['TO_LONG_DEG'], row['TO_LONG_MIN'], row['TO_LONG_SEC'], row['TO_LONG_DIR_IND']), axis=1)

        # Hitung ulang jarak
        edited_df['CIRCUIT_LEN'] = edited_df.apply(lambda row: round(great_circle((row['LAT_DEC'], row['LONG_DEC']), (row['TO_LAT_DEC'], row['TO_LONG_DEC'])).km, 3), axis=1)

        # Simpan edited data ke Excel baru (opsional)
        edited_df.to_excel("Data_Edited.xlsx", index=False)
        st.success("Data diupdate & disimpan ke Data_Edited.xlsx")

        # Simpan ke session_state agar peta ikut update
        st.session_state['edited_df'] = edited_df

with tab_stats:
    st.subheader("Statistik Ringkas")
    st.markdown("- Distribusi jarak (km) — ringkasan deskriptif")
    if 'CIRCUIT_LEN' in df_filtered:
        st.dataframe(df_filtered['CIRCUIT_LEN'].describe().to_frame().T, use_container_width=True)
    else:
        st.info("Kolom CIRCUIT_LEN belum tersedia.")

st.caption("Tip: Gunakan layer control di peta untuk ganti basemap (Street/Satellite).")

# Sidebar section: Import Excel -> PostgreSQL
with st.sidebar.expander("Database • Import Excel → PostgreSQL", expanded=False):
    st.caption("Simpan data saat ini ke PostgreSQL. Isi koneksi lalu klik Import.")
    db_host = st.text_input("Host", value="localhost")
    db_port = st.number_input("Port", value=5432, step=1)
    db_name = st.text_input("Database", value="postgres")
    db_user = st.text_input("User", value="postgres")
    db_pass = st.text_input("Password", value="", type="password")
    table_name = st.text_input("Nama Tabel", value="balmon_links")
    if st.button("Import Sekarang", use_container_width=True):
        df_to_save = st.session_state.get('edited_df', df)
        if df_to_save is None or df_to_save.empty:
            st.error("Tidak ada data untuk disimpan.")
        else:
            try:
                if get_engine_from_params is None or write_dataframe is None:
                    raise RuntimeError("Perlu paket: pip install sqlalchemy psycopg2-binary")
                params: Dict[str, object] = {
                    "host": db_host,
                    "port": db_port,
                    "database": db_name,
                    "user": db_user,
                    "password": db_pass,
                }
                engine = get_engine_from_params(params)
                write_dataframe(df_to_save, table_name=table_name, engine=engine, if_exists="replace")
                st.success(f"Berhasil impor {len(df_to_save)} baris ke tabel '{table_name}'.")
            except Exception as e:
                st.error(f"Gagal impor ke PostgreSQL: {e}")
