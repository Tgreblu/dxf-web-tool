import streamlit as st
import ezdxf
from ezdxf import path
from ezdxf import units
from io import StringIO

# Configurazione della pagina
st.set_page_config(page_title="DXF Utility Tool", layout="centered")

st.title("🛠️ DXF Utility Web App")
st.markdown("Genera cerchi o applica campiture (Hatching) con funzione **Unisci Linee** per disegni esplosi o aperti.")

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

# Tolleranza per unione automatica
merge_tolerance = st.sidebar.slider(
    "Tolleranza Unione (mm)", 
    0.0, 5.0, 0.1, 0.05, 
    help="Distanza massima tra due linee per considerarle collegate. Aumenta se il disegno ha 'buchi' visibili o è spezzettato."
)

tab1, tab2 = st.tabs(["🔵 Genera Cerchi", "✏️ Aggiungi Campitura (Hatch)"])

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
    st.header("Campitura & Unione Linee")
    st.info("Il sistema cercherà di unire linee spezzate (spaghetti CAD) in forme chiuse valide.")
    
    uploaded_file = st.file_uploader("File DXF", type=["dxf"])
    spacing = st.number_input("Spaziatura Hatch (mm)", 0.05, value=0.2, step=0.05)

    if uploaded_file and st.button("Analizza e Campisci"):
        try:
            # 1. Lettura Resiliente
            content = uploaded_file.getvalue().decode('utf-8', errors='ignore')
            # Patch per header corrotti o versioni strane
            if "AC1012" in content or "AC1014" in content: 
                content = content.replace("AC1012", "AC1015").replace("AC1014", "AC1015")
            
            doc_in = ezdxf.read(StringIO(content))
            msp_in = doc_in.modelspace()
            
            # 2. Preparazione Export
            doc_out = ezdxf.new(dxf_version_code)
            msp_out = doc_out.modelspace()
            
            # Configurazione Hatch
            explode = (dxf_version_code == "R12")
            target_doc = ezdxf.new('R2000') if explode else doc_out
            target_msp = target_doc.modelspace()
            
            hatch = target_msp.add_hatch(color=1)
            hatch.set_pattern_fill('ANSI31', scale=spacing)
            
            # 3. RACCOLTA E UNIONE GEOMETRIE (Il Cuore della Logica)
            input_paths = []
            raw_entity_count = 0
            
            # Convertiamo tutto (Linee, Archi, Polilinee) in percorsi astratti
            for entity in msp_in:
                if entity.dxftype() in ['LINE', 'ARC', 'CIRCLE', 'LWPOLYLINE', 'POLYLINE', 'SPLINE', 'ELLIPSE']:
                    try:
                        # make_path normalizza qualsiasi geometria in un percorso gestibile
                        p = path.make_path(entity)
                        if p.has_sub_paths:
                            for sub in p.sub_paths():
                                input_paths.append(sub)
                        else:
                            input_paths.append(p)
                        raw_entity_count += 1
                    except Exception:
                        pass

            if raw_entity_count == 0:
                st.error("Il file sembra vuoto o non contiene geometrie supportate (Linee, Archi, Polilinee).")
                st.stop()

            # UNIONE: Incolla i percorsi che si toccano
            # merge_paths restituisce percorsi uniti. 
            # ignore_double_floating_point_precision è false per usare la nostra tolleranza manuale se serve, 
            # ma qui ci affidiamo alla topologia.
            merged_paths = path.merge_paths(input_paths, distance=merge_tolerance)
            
            valid_closed_shapes = 0
            open_shapes_after_merge = 0
            
            # 4. GENERAZIONE HATCH SU FORME CHIUSE
            for p in merged_paths:
                # Se il percorso è chiuso (o quasi chiuso entro tolleranza)
                if p.is_closed or (p.start.isclose(p.end, abs_tol=merge_tolerance)):
                    
                    # Trasformiamo il path in punti per il DXF
                    # flatten trasforma curve in segmenti lineari (necessario per R12/Laser)
                    points = list(p.flattening(distance=0.05))
                    
                    if len(points) > 2:
                        # Disegna il contorno pulito nel file finale
                        msp_out.add_polyline2d(points, dxfattribs={'layer': 'GEOMETRIA', 'color': 7})
                        
                        # Aggiungi all'hatch
                        hatch.paths.add_polyline_path(points)
                        valid_closed_shapes += 1
                else:
                    # Se rimane aperto anche dopo l'unione, lo copiamo come linea semplice senza hatch
                    points = list(p.flattening(distance=0.05))
                    if len(points) > 1:
                        msp_out.add_polyline2d(points, dxfattribs={'layer': 'APK_APERTE', 'color': 1}) # Rosso per debug
                        open_shapes_after_merge += 1

            # 5. SALVATAGGIO
            if valid_closed_shapes > 0:
                if explode:
                    hatch.explode()
                    lines_count = 0
                    for e in target_msp:
                        if e.dxftype() == 'LINE':
                            msp_out.add_line(e.dxf.start, e.dxf.end, dxfattribs={'layer': 'HATCH', 'color': 2}) # Giallo
                            lines_count += 1
                    st.success(f"✅ Successo! {valid_closed_shapes} forme chiuse ricostruite da {raw_entity_count} segmenti.")
                    st.info(f"Campitura generata ed esplosa in {lines_count} linee (compatibile R12).")
                else:
                    st.success(f"✅ Successo! {valid_closed_shapes} forme chiuse ricostruite e campite.")
                
                out = StringIO()
                doc_out.write(out)
                st.download_button("📥 Scarica DXF Processato", out.getvalue().encode('utf-8'), f"hatch_{dxf_version_code}_fixed.dxf", "application/dxf")
            else:
                st.error("❌ Non sono riuscito a chiudere nessuna forma.")
                st.warning(f"Ho trovato {raw_entity_count} segmenti, ma dopo aver provato a unirli sono risultati {open_shapes_after_merge} percorsi aperti.")
                st.markdown("👉 **Suggerimento:** Prova ad aumentare la **'Tolleranza Unione'** nella barra laterale a sinistra (es. a 0.5 o 1.0 mm) e riprova.")

        except Exception as e:
            st.error(f"Errore tecnico durante l'elaborazione: {e}")
