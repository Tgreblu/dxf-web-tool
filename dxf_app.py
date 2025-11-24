import streamlit as st
import ezdxf
from ezdxf import units
from io import StringIO

# Configurazione della pagina
st.set_page_config(page_title="DXF Utility Tool", layout="centered")

st.title("🛠️ DXF Utility Web App")
st.markdown("Genera cerchi concentrici o aggiungi hatching con rilevamento isole.")

# --- BARRA LATERALE PER IMPOSTAZIONI ---
st.sidebar.header("⚙️ Impostazioni Macchina")

version_map = {
    "R12 (AC1009) - Universale/Laser": "R12",
    "R2000 (AC1015) - Standard": "R2000",
    "R2004 (AC1018)": "R2004",
    "R2007 (AC1021)": "R2007",
    "R2010 (AC1024) - Recente": "R2010"
}

st.sidebar.warning("Nota: Se selezioni R12, la campitura verrà automaticamente 'esplosa' in singole linee per garantire la compatibilità.")

selected_version_label = st.sidebar.selectbox(
    "Versione DXF Output",
    options=list(version_map.keys()),
    index=0, # Default su R12
    help="R12 trasforma tutto in linee semplici. Ideale per laser vecchi."
)

dxf_version_code = version_map[selected_version_label]
st.sidebar.info(f"Output impostato su: **{dxf_version_code}**")

# Creiamo due tab per le due funzioni
tab1, tab2 = st.tabs(["🔵 Genera Cerchi", "✏️ Aggiungi Campitura (Hatch)"])

# --- FUNZIONE 1: CREAZIONE CERCHI ---
with tab1:
    st.header("Crea Cerchi Concentrici")
    
    col1, col2 = st.columns(2)
    with col1:
        r_int = st.number_input("Raggio Interno (mm)", min_value=1.0, value=10.0, step=0.5)
    with col2:
        r_ext = st.number_input("Raggio Esterno (mm)", min_value=r_int+0.1, value=20.0, step=0.5)

    if st.button("Genera DXF Cerchi"):
        try:
            doc = ezdxf.new(dxf_version_code)
            doc.units = units.MM
            msp = doc.modelspace()

            msp.add_circle((0, 0), radius=r_int, dxfattribs={'layer': 'CERCHI'})
            msp.add_circle((0, 0), radius=r_ext, dxfattribs={'layer': 'CERCHI'})

            output_stream = StringIO()
            doc.write(output_stream)
            dxf_bytes = output_stream.getvalue().encode('utf-8')
            
            st.success(f"File generato in versione {dxf_version_code}!")
            st.download_button(
                label="📥 Scarica Cerchi.dxf",
                data=dxf_bytes,
                file_name=f"cerchi_{dxf_version_code}.dxf",
                mime="application/dxf"
            )
        except Exception as e:
            st.error(f"Errore durante la generazione: {e}")

# --- FUNZIONE 2: HATCHING (CAMPITURA INTELLIGENTE) ---
with tab2:
    st.header("Aggiungi Campitura a 45°")
    st.info("Carica un file DXF. Le forme concentriche verranno campite come 'isole'.")

    uploaded_file = st.file_uploader("Carica il tuo file DXF", type=["dxf"])
    spacing = st.number_input("Distanza righe (mm)", min_value=0.05, value=0.2, step=0.05, format="%.2f")

    if uploaded_file is not None:
        if st.button("Applica Campitura"):
            try:
                # 1. Lettura e PATCHING (R13/R14 -> R2000 per lettura)
                bytes_data = uploaded_file.getvalue()
                string_data = bytes_data.decode('utf-8', errors='ignore')
                
                if "AC1012" in string_data:
                    string_data = string_data.replace("AC1012", "AC1015")
                elif "AC1014" in string_data:
                    string_data = string_data.replace("AC1014", "AC1015")

                doc_original = ezdxf.read(StringIO(string_data))
                msp_original = doc_original.modelspace()
                
                # 2. Preparazione Documento Finale (es. R12)
                doc_export = ezdxf.new(dxf_version_code)
                doc_export.units = units.MM
                msp_export = doc_export.modelspace()

                # 3. Gestione Hatch per R12 (Esplosione)
                # Se l'output è R12, non possiamo usare l'entità Hatch.
                # Dobbiamo calcolarla in un documento temporaneo moderno (R2000), esploderla in linee,
                # e copiare le linee nel documento R12.
                explode_hatch = (dxf_version_code == "R12")
                
                if explode_hatch:
                    doc_temp = ezdxf.new('R2000') # Serve solo per calcolare la geometria
                    msp_hatch_target = doc_temp.modelspace()
                else:
                    msp_hatch_target = msp_export # Scriviamo direttamente nel file finale

                # Creazione Hatch nel target appropriato
                hatch = msp_hatch_target.add_hatch(color=1)
                hatch.set_pattern_fill('ANSI31', scale=spacing)
                hatch.dxf.hatch_style = 0 # Normal (Islands detection)
                
                count = 0
                
                # 4. Ricostruzione Geometrie e Contorni Hatch
                for entity in msp_original:
                    if entity.dxftype() == 'CIRCLE':
                        # Disegna geometria nel file finale
                        msp_export.add_circle(entity.dxf.center, entity.dxf.radius, dxfattribs={'layer': 'GEOMETRIA'})
                        
                        # Aggiungi contorno all'hatch (per il calcolo)
                        hatch.paths.add_edge_path().add_arc(
                            center=entity.dxf.center,
                            radius=entity.dxf.radius,
                            start_angle=0,
                            end_angle=360
                        )
                        count += 1
                        
                    elif entity.dxftype() == 'LWPOLYLINE':
                        if entity.is_closed:
                            points = entity.get_points(format='xy')
                            msp_export.add_lwpolyline(points, close=True, dxfattribs={'layer': 'GEOMETRIA'})
                            hatch.paths.add_polyline_path(points)
                            count += 1

                    elif entity.dxftype() == 'POLYLINE':
                         if entity.is_closed:
                            points = [v.dxf.location[:2] for v in entity.vertices]
                            if points:
                                msp_export.add_polyline2d(points, close=True, dxfattribs={'layer': 'GEOMETRIA'})
                                hatch.paths.add_polyline_path(points)
                                count += 1

                if count > 0:
                    # 5. Fase Finale: Esplosione (Se R12)
                    if explode_hatch:
                        # Trasforma il blocco Hatch in tante linee semplici
                        hatch.explode()
                        
                        # Copia le linee risultanti nel file finale R12
                        lines_count = 0
                        for entity in msp_hatch_target:
                            if entity.dxftype() == 'LINE':
                                msp_export.add_line(
                                    start=entity.dxf.start, 
                                    end=entity.dxf.end, 
                                    dxfattribs={'layer': 'CAMPITURA'}
                                )
                                lines_count += 1
                        st.success(f"Campitura generata ed esplosa in {lines_count} linee per compatibilità R12!")
                    else:
                        st.success(f"Campitura generata come entità HATCH (R2000+).")

                    # Salvataggio
                    output_stream = StringIO()
                    doc_export.write(output_stream)
                    dxf_out_bytes = output_stream.getvalue().encode('utf-8')
                    
                    st.download_button(
                        label="📥 Scarica DXF Modificato",
                        data=dxf_out_bytes,
                        file_name=f"hatch_{dxf_version_code}_{uploaded_file.name}",
                        mime="application/dxf"
                    )
                else:
                    st.warning("Nessuna forma chiusa valida trovata.")
                    
            except Exception as e:
                st.error(f"Errore: {e}")
