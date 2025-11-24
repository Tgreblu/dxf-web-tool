import streamlit as st
import ezdxf
from ezdxf import path, units
from io import StringIO
from shapely.geometry import LineString, Polygon
from shapely.ops import linemerge, polygonize
from shapely import affinity

# Configurazione della pagina
st.set_page_config(page_title="DXF Power Tool", layout="centered")

st.title("⚡ DXF Power Tool - Shapely Engine")
st.markdown("Generatore di Cerchi e sistema avanzato di Campitura per disegni CAD.")

# --- CONFIGURAZIONE LATERALE ---
st.sidebar.header("⚙️ Impostazioni Laser")

version_map = {
    "R12 (AC1009) - Massima Compatibilità": "R12",
    "R2000 (AC1015) - Standard": "R2000",
    "R2010 (AC1024) - Recente": "R2010"
}

st.sidebar.info("Seleziona R12 per macchine laser datate. La campitura sarà esplosa in linee singole.")
selected_version_label = st.sidebar.selectbox("Versione Output", options=list(version_map.keys()), index=0)
dxf_version_code = version_map[selected_version_label]

# Creazione Tab (Questa riga mancava prima!)
tab1, tab2 = st.tabs(["🔵 Genera Cerchi", "✏️ Campitura Avanzata (Shapely)"])

# --- FUNZIONI DI SUPPORTO (MOTORE GEOMETRICO) ---
def extract_all_paths(doc):
    """Estrae percorsi da ModelSpace e da tutti i Blocchi in modo sicuro."""
    paths = []
    msp = doc.modelspace()
    for entity in msp:
        try:
            # Converte qualsiasi entità (Linee, Archi, Spline, Cerchi) in percorsi
            p = path.make_path(entity)
            if p.has_sub_paths:
                for sub in p.sub_paths():
                    paths.append(sub)
            else:
                paths.append(p)
        except Exception:
            pass # Ignora entità non geometriche (testi, quote)
    return paths

def create_hatch_lines(polygon, spacing, angle):
    """Genera linee di campitura fisiche tagliando linee lunghe con il poligono."""
    minx, miny, maxx, maxy = polygon.bounds
    
    # Calcolo diagonale per coprire l'intera area
    diagonal = ((maxx - minx)**2 + (maxy - miny)**2)**0.5
    # Aumentiamo l'area di copertura per sicurezza
    coverage = diagonal * 1.5
    
    # Centro del poligono
    cx, cy = (minx + maxx)/2, (miny + maxy)/2
    
    # Numero linee stimate
    num_lines = int(coverage / spacing)
    start_y = cy - (num_lines * spacing) / 2
    
    # Generazione linee orizzontali lunghe
    raw_lines = []
    for i in range(num_lines):
        y = start_y + i * spacing
        line = LineString([(cx - coverage, y), (cx + coverage, y)])
        # Rotazione
        rotated_line = affinity.rotate(line, angle, origin=(cx, cy))
        raw_lines.append(rotated_line)
        
    # Intersezione (Taglio)
    final_lines = []
    for line in raw_lines:
        if polygon.intersects(line):
            intersection = polygon.intersection(line)
            if intersection.is_empty:
                continue
            
            if intersection.geom_type == 'LineString':
                final_lines.append(intersection)
            elif intersection.geom_type == 'MultiLineString':
                for seg in intersection.geoms:
                    final_lines.append(seg)
                    
    return final_lines

# --- TAB 1: CERCHI CONCENTRICI ---
with tab1:
    st.header("Crea Cerchi Concentrici")
    c1, c2 = st.columns(2)
    with c1: 
        r_int = st.number_input("Raggio Interno (mm)", 1.0, value=10.0, step=0.5)
    with c2: 
        r_ext = st.number_input("Raggio Esterno (mm)", r_int+0.1, value=20.0, step=0.5)

    if st.button("Genera DXF Cerchi"):
        doc = ezdxf.new(dxf_version_code)
        doc.units = units.MM
        msp = doc.modelspace()
        
        msp.add_circle((0, 0), radius=r_int, dxfattribs={'layer': 'CERCHI'})
        msp.add_circle((0, 0), radius=r_ext, dxfattribs={'layer': 'CERCHI'})
        
        out = StringIO()
        doc.write(out)
        st.success(f"File generato (Versione {dxf_version_code})")
        st.download_button(
            label="📥 Scarica Cerchi.dxf",
            data=out.getvalue().encode('utf-8'),
            file_name=f"cerchi_{dxf_version_code}.dxf",
            mime="application/dxf"
        )

# --- TAB 2: CAMPITURA AVANZATA (SHAPELY) ---
with tab2:
    st.header("Campitura 'Ricostruttiva'")
    st.info("Questo strumento ricostruisce le forme da linee esplose e applica la campitura.")
    
    col_opt1, col_opt2 = st.columns(2)
    with col_opt1:
        spacing = st.number_input("Spaziatura (mm)", 0.05, 10.0, 0.2, 0.05)
    with col_opt2:
        hatch_angle = st.slider("Angolo (°)", 0, 180, 45)

    uploaded_file = st.file_uploader("Carica il tuo file DXF", type=["dxf"])

    if uploaded_file and st.button("🚀 Analizza e Campisci"):
        try:
            # 1. Lettura del file
            content = uploaded_file.getvalue().decode('utf-8', errors='ignore')
            if "AC1012" in content or "AC1014" in content: 
                content = content.replace("AC1012", "AC1015").replace("AC1014", "AC1015")
            
            doc_in = ezdxf.read(StringIO(content))
            
            # 2. Estrazione Percorsi
            ezdxf_paths = extract_all_paths(doc_in)
            
            if not ezdxf_paths:
                st.error("Il file sembra vuoto o non contiene linee valide.")
                st.stop()
            
            # 3. Conversione in Geometria Shapely
            shapely_lines = []
            for p in ezdxf_paths:
                # Appiattimento curve in segmenti lineari (risoluzione alta 0.01mm)
                points = list(p.flattening(distance=0.01))
                if len(points) > 1:
                    shapely_lines.append(LineString(points))
            
            # 4. Unione Linee (Merge) e Poligonizzazione
            # Unisce segmenti che si toccano
            merged = linemerge(shapely_lines)
            
            # Trova aree chiuse
            polygons = list(polygonize(merged))
            
            if not polygons:
                st.warning("⚠️ Non sono state trovate aree completamente chiuse.")
                st.info("Suggerimento: Il disegno potrebbe avere micro-interruzioni. Prova a ripassare i contorni nel CAD originale.")
            else:
                st.success(f"✅ Trovate {len(polygons)} aree chiuse!")
                
                # 5. Generazione Output
                doc_out = ezdxf.new(dxf_version_code)
                doc_out.units = units.MM
                msp_out = doc_out.modelspace()
                
                total_hatch_lines = 0
                
                for poly in polygons:
                    # (Opzionale) Disegna il contorno ricostruito
                    if poly.exterior:
                        x, y = poly.exterior.xy
                        msp_out.add_polyline2d(list(zip(x, y)), dxfattribs={'layer': 'CONTORNO_RICOSTRUITO', 'color': 7})
                    
                    # Calcola e disegna la campitura
                    lines = create_hatch_lines(poly, spacing, hatch_angle)
                    for l in lines:
                        coords = list(l.coords)
                        # Aggiungiamo LINEE SEMPLICI (compatibilità R12 100%)
                        msp_out.add_line(coords[0], coords[1], dxfattribs={'layer': 'CAMPITURA', 'color': 1})
                        total_hatch_lines += 1
                
                st.write(f"🖊️ Generate {total_hatch_lines} linee di campitura.")
                
                out_buffer = StringIO()
                doc_out.write(out_buffer)
                
                st.download_button(
                    label="📥 Scarica DXF Processato",
                    data=out_buffer.getvalue().encode('utf-8'),
                    file_name=f"hatch_fixed_{dxf_version_code}.dxf",
                    mime="application/dxf"
                )

        except Exception as e:
            st.error(f"Si è verificato un errore: {e}")
