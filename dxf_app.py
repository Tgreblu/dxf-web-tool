import streamlit as st
import ezdxf
import math
from ezdxf import units
from io import StringIO

# Configurazione della pagina
st.set_page_config(page_title="DXF Utility Tool", layout="centered")

st.title("🛠️ DXF Utility Web App")
st.markdown("Genera cerchi o applica campiture (Hatching) anche su file datati o imperfetti.")

# --- BARRA LATERALE ---
st.sidebar.header("⚙️ Configurazione")

version_map = {
    "R12 (AC1009) - Universale/Laser": "R12",
    "R2000 (AC1015) - Standard": "R2000",
    "R2010 (AC1024) - Recente": "R2010"
}

st.sidebar.info("Seleziona R12 per macchine laser datate (la campitura verrà esplosa in linee).")
selected_version_label = st.sidebar.selectbox(
    "Versione DXF Output",
    options=list(version_map.keys()),
    index=0
)
dxf_version_code = version_map[selected_version_label]

# Tolleranza per chiusura automatica
close_tolerance = st.sidebar.slider("Tolleranza Chiusura (mm)", 0.0, 2.0, 0.5, 0.1, help="Se l'inizio e la fine di una linea distano meno di questo valore, il programma la chiude automaticamente.")

tab1, tab2 = st.tabs(["🔵 Genera Cerchi", "✏️ Aggiungi Campitura (Hatch)"])

# --- FUNZIONI DI SUPPORTO ---
def dist(p1, p2):
    """Calcola distanza euclidea tra due punti (x,y)"""
    return math.hypot(p1[0] - p2[0], p1[1] - p2[1])

def get_clean_points(entity):
    """Estrae i punti da diverse entità e cerca di chiuderle se necessario."""
    points = []
    is_closed = False
    
    try:
        # 1. Estrazione Punti
        if entity.dxftype() == 'LWPOLYLINE':
            # get_points restituisce (x, y, start_width, end_width, bulge)
            raw_points = entity.get_points(format='xy')
            points = raw_points # Sono già tuple (x,y)
            is_closed = entity.closed
            
        elif entity.dxftype() == 'POLYLINE':
            # Vecchie polilinee 2D/3D
            points = [v.dxf.location[:2] for v in entity.vertices]
            is_closed = entity.is_closed
            
        elif entity.dxftype() == 'SPLINE':
            # Convertiamo spline in polilinea densa
            try:
                points = list(entity.flattening(distance=0.05))
                is_closed = entity.closed
            except:
                return [], False

        # 2. Controllo e Correzione Chiusura
        if len(points) > 2:
            start = points[0]
            end = points[-1]
            gap = dist(start, end)

            # Se è flaggata chiusa o geometricamente chiusa (gap quasi 0)
            if is_closed or gap < 0.001:
                return points, True
            
            # Se è aperta ma il gap è piccolo (tolleranza utente), la chiudiamo forzatamente
            if gap <= close_tolerance:
                points.append(start) # Aggiunge il punto iniziale alla fine per chiudere
                return points, True # La consideriamo chiusa
                
        return points, False # Rimane aperta
        
    except Exception:
        return [], False

# --- TAB 1: CERCHI ---
with tab1:
    st.header("Crea Cerchi Concentrici")
    c1, c2 = st.columns(2)
    with c1: r_int = st.number_input("Raggio Interno (mm)", 1.0, value=10.0)
    with c2: r_ext = st.number_input("Raggio Esterno (mm)", r_int+0.1, value=20.0)

    if st.button("Genera DXF Cerchi"):
        doc = ezdxf.new(dxf_version_code)
        msp = doc.modelspace()
        msp.add_circle((0, 0), r_int, dxfattribs={'layer': 'CERCHI'})
        msp.add_circle((0, 0), r_ext, dxfattribs={'layer': 'CERCHI'})
        
        out = StringIO()
        doc.write(out)
        st.download_button("📥 Scarica Cerchi.dxf", out.getvalue().encode('utf-8'), f"cerchi_{dxf_version_code}.dxf", "application/dxf")

# --- TAB 2: HATCHING ---
with tab2:
    st.header("Campitura (Hatching) Intelligente")
    st.info("Carica il file. Il sistema tenterà di chiudere automaticamente le linee aperte.")
    
    uploaded_file = st.file_uploader("File DXF", type=["dxf"])
    spacing = st.number_input("Spaziatura Hatch (mm)", 0.05, value=0.2, step=0.05)

    if uploaded_file and st.button("Applica Campitura"):
        try:
            # Lettura resiliente
            content = uploaded_file.getvalue().decode('utf-8', errors='ignore')
            # Patch per vecchi header problematici
            if "AC1012" in content or "AC1014" in content: content = content.replace("AC1012", "AC1015").replace("AC1014", "AC1015")
            
            doc_in = ezdxf.read(StringIO(content))
            msp_in = doc_in.modelspace()
            
            # Preparazione Export
            doc_out = ezdxf.new(dxf_version_code)
            msp_out = doc_out.modelspace()
            
            # Setup Hatch
            explode = (dxf_version_code == "R12")
            # Se R12 usiamo un doc temporaneo per calcolare l'hatch
            target_doc = ezdxf.new('R2000') if explode else doc_out
            target_msp = target_doc.modelspace()
            
            hatch = target_msp.add_hatch(color=1)
            hatch.set_pattern_fill('ANSI31', scale=spacing)
            
            # Analisi Entità
            valid_shapes = 0
            open_shapes = 0
            ignored_entities = 0
            
            debug_log = []

            for entity in msp_in:
                etype = entity.dxftype()
                
                if etype == 'CIRCLE':
                    # I cerchi sono facili e sempre chiusi
                    msp_out.add_circle(entity.dxf.center, entity.dxf.radius, dxfattribs={'layer': 'GEOMETRIA'})
                    hatch.paths.add_edge_path().add_arc(entity.dxf.center, entity.dxf.radius, 0, 360)
                    valid_shapes += 1
                    
                elif etype in ['LWPOLYLINE', 'POLYLINE', 'SPLINE']:
                    # Logica avanzata di pulizia punti
                    points, is_closed = get_clean_points(entity)
                    
                    if len(points) > 1:
                        # Ricostruiamo la geometria nel file di output (così ripariamo eventuali errori)
                        # Usiamo POLYLINE2D (compatibile R12)
                        msp_out.add_polyline2d(points, dxfattribs={'layer': 'GEOMETRIA', 'color': 7})
                        
                        if is_closed:
                            hatch.paths.add_polyline_path(points)
                            valid_shapes += 1
                        else:
                            open_shapes += 1
                            debug_log.append(f"Forma aperta (Gap > {close_tolerance}mm) di tipo {etype} ignorata.")
                    else:
                        ignored_entities += 1

            # Esito
            if valid_shapes > 0:
                if explode:
                    hatch.explode()
                    lines_count = 0
                    for e in target_msp:
                        if e.dxftype() == 'LINE':
                            msp_out.add_line(e.dxf.start, e.dxf.end, dxfattribs={'layer': 'HATCH', 'color': 1})
                            lines_count += 1
                    st.success(f"✅ Fatto! Campite {valid_shapes} forme. Hatch esploso in {lines_count} linee (R12).")
                else:
                    st.success(f"✅ Fatto! Campite {valid_shapes} forme (Hatch Entità).")
                
                out = StringIO()
                doc_out.write(out)
                st.download_button("📥 Scarica Risultato", out.getvalue().encode('utf-8'), f"hatch_{dxf_version_code}_{uploaded_file.name}", "application/dxf")
            else:
                st.error("❌ Nessuna forma chiusa valida trovata per la campitura.")
            
            # Report Diagnostico
            with st.expander("🔍 Dettagli Analisi File (Clicca per aprire)"):
                st.write(f"**Forme valide (chiuse):** {valid_shapes}")
                st.write(f"**Forme aperte (ignorate):** {open_shapes}")
                st.write(f"**Entità non geometriche ignorate:** {ignored_entities}")
                if open_shapes > 0:
                    st.warning(f"Ci sono {open_shapes} linee che sembrano forme ma non sono chiuse. Prova ad aumentare la 'Tolleranza Chiusura' nella barra laterale.")
                    st.caption("Log dettagliato:")
                    for msg in debug_log:
                        st.text("- " + msg)

        except Exception as e:
            st.error(f"Errore critico: {e}")
