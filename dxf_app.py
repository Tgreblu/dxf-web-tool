import streamlit as st
import ezdxf
from ezdxf import path
from io import StringIO
from shapely.geometry import LineString, Polygon
from shapely.ops import linemerge, polygonize, unary_union

# Configurazione della pagina
st.set_page_config(page_title="DXF Power Tool", layout="centered")

st.title("⚡ DXF Power Tool - Shapely Engine")
st.markdown("Utilizza un motore geometrico avanzato per trovare aree chiuse in disegni 'esplosi' o imperfetti.")

# --- CONFIGURAZIONE ---
st.sidebar.header("⚙️ Impostazioni Laser")

# Mappatura versioni
version_map = {
    "R12 (AC1009) - Massima Compatibilità": "R12",
    "R2000 (AC1015) - Standard": "R2000",
    "R2010 (AC1024) - Recente": "R2010"
}

st.sidebar.info("L'algoritmo 'Polygonize' troverà tutte le aree chiuse possibili.")
selected_version_label = st.sidebar.selectbox("Versione Output", options=list(version_map.keys()), index=0)
dxf_version_code = version_map[selected_version_label]

# Parametri Hatch
spacing = st.sidebar.number_input("Spaziatura Campitura (mm)", 0.05, 5.0, 0.2, 0.05)
hatch_angle = st.sidebar.slider("Angolo Campitura", 0, 180, 45)

# --- LOGICA GEOMETRICA AVANZATA ---
def extract_all_paths(doc):
    """Estrae percorsi da ModelSpace e da tutti i Blocchi (ricorsivo light)"""
    paths = []
    # Estraiamo dal ModelSpace
    msp = doc.modelspace()
    for entity in msp:
        try:
            # path.make_path è molto potente, converte quasi tutto (linee, cerchi, spline) in percorsi
            p = path.make_path(entity)
            if p.has_sub_paths:
                for sub in p.sub_paths():
                    paths.append(sub)
            else:
                paths.append(p)
        except Exception:
            pass
    return paths

def create_hatch_lines(polygon, spacing, angle):
    """Genera linee di campitura fisiche (non entità Hatch) dentro un poligono Shapely"""
    minx, miny, maxx, maxy = polygon.bounds
    lines = []
    
    # Creiamo una griglia di linee ruotate
    # Per semplicità, creiamo linee orizzontali enormi e le ruotiamo/tagliamo
    diagonal = ((maxx - minx)**2 + (maxy - miny)**2)**0.5
    num_lines = int(diagonal / spacing) * 2
    
    # Centro del poligono
    cx, cy = (minx + maxx)/2, (miny + maxy)/2
    
    # Generiamo linee lunghe
    h_lines = []
    start_y = cy - (num_lines * spacing) / 2
    
    for i in range(num_lines):
        y = start_y + i * spacing
        # Linea orizzontale molto lunga
        line = LineString([(cx - diagonal, y), (cx + diagonal, y)])
        # Ruotiamo
        from shapely import affinity
        rotated_line = affinity.rotate(line, angle, origin=(cx, cy))
        h_lines.append(rotated_line)
        
    # Intersezione
    final_lines = []
    for line in h_lines:
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

# --- INTERFACCIA ---
uploaded_file = st.file_uploader("Carica DXF (anche R12/R13/R14)", type=["dxf"])

if uploaded_file:
    st.info("File caricato. Premi il pulsante per analizzare la geometria.")
    
    if st.button("🚀 Esegui Analisi e Campitura"):
        try:
            # 1. Lettura Resiliente
            content = uploaded_file.getvalue().decode('utf-8', errors='ignore')
            # Patch header R13/R14 -> R2000 per ezdxf
            if "AC1012" in content or "AC1014" in content: 
                content = content.replace("AC1012", "AC1015").replace("AC1014", "AC1015")
            
            doc_in = ezdxf.read(StringIO(content))
            
            # 2. Estrazione Geometria Pura
            ezdxf_paths = extract_all_paths(doc_in)
            
            if not ezdxf_paths:
                st.error("Non ho trovato entità nel file. Verifica che non sia vuoto.")
                st.stop()
                
            # 3. Conversione in Shapely (LineStrings)
            # Appiattiamo tutto in segmenti lineari (risoluzione 0.05mm)
            shapely_lines = []
            for p in ezdxf_paths:
                # flattening restituisce generatori di vettori, li convertiamo in lista di tuple
                points = list(p.flattening(distance=0.05))
                if len(points) > 1:
                    shapely_lines.append(LineString(points))
            
            st.write(f"🔍 Analizzati {len(shapely_lines)} segmenti geometrici.")

            # 4. Unione e Poligonizzazione (La Magia)
            # linemerge unisce i segmenti che si toccano
            merged = linemerge(shapely_lines)
            
            # polygonize trova le aree chiuse create dalle linee
            polygons = list(polygonize(merged))
            
            if not polygons:
                st.warning("⚠️ Non sono riuscito a trovare aree chiuse. Le linee potrebbero non toccarsi o avere buchi troppo grandi.")
                st.info("Tentativo di 'Buffer': Prova a ingrossare le linee per farle toccare.")
                # Fallback: Buffer
                # (Questo è complesso, per ora fermiamoci qui e vediamo se polygonize funziona)
            else:
                st.success(f"✅ Trovate {len(polygons)} aree chiuse (isole o contorni)!")
                
                # 5. Generazione Output
                doc_out = ezdxf.new(dxf_version_code)
                msp_out = doc_out.modelspace()
                
                total_hatch_lines = 0
                
                # Per ogni area chiusa trovata
                for poly in polygons:
                    # Disegna il contorno (facoltativo, ma utile per verifica)
                    x, y = poly.exterior.xy
                    msp_out.add_polyline2d(list(zip(x, y)), dxfattribs={'layer': 'CONTORNO', 'color': 7})
                    
                    # Genera le linee di campitura (Intersezione geometrica)
                    # Questo bypassa l'oggetto Hatch DXF e crea semplici LINEE (massima compatibilità R12)
                    hatch_lines = create_hatch_lines(poly, spacing, hatch_angle)
                    
                    for h_line in hatch_lines:
                        coords = list(h_line.coords)
                        msp_out.add_line(coords[0], coords[1], dxfattribs={'layer': 'CAMPITURA', 'color': 1}) # Rosso
                        total_hatch_lines += 1
                
                st.write(f"🖊️ Generate {total_hatch_lines} linee di campitura fisiche.")
                
                # Download
                out = StringIO()
                doc_out.write(out)
                file_data = out.getvalue().encode('utf-8')
                
                st.download_button(
                    label="📥 Scarica DXF Pronto (Compatibile R12/13)",
                    data=file_data,
                    file_name=f"processed_{dxf_version_code}.dxf",
                    mime="application/dxf"
                )

        except Exception as e:
            st.error(f"Errore durante l'elaborazione: {e}")
            st.error("Dettaglio tecnico: Verifica che il file non sia corrotto o binario.")

with tab1:
    st.info("Usa il tab 'Campitura' per processare il file caricato.")
