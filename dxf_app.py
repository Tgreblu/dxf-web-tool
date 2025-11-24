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

# NOTA: R13 e R14 non sono supportate in scrittura da ezdxf.
# Abbiamo mappato le opzioni alle versioni sicuramente funzionanti.
# Per macchine R13, la R12 è solitamente la scelta sicura.
version_map = {
    "R12 (AC1009) - Universale/Sicuro": "R12",
    "R2000 (AC1015) - Standard": "R2000",
    "R2004 (AC1018)": "R2004",
    "R2007 (AC1021)": "R2007",
    "R2010 (AC1024) - Recente": "R2010"
}

st.sidebar.warning("Nota: Le versioni R13/R14 non sono supportate nativamente in scrittura dalle librerie moderne. Usa **R12** per massima compatibilità con macchine datate.")

selected_version_label = st.sidebar.selectbox(
    "Versione DXF Output",
    options=list(version_map.keys()),
    index=0, # Default su R12 per sicurezza
    help="Seleziona R12 se hai una macchina vecchia (es. anni '90/2000). Seleziona R2000 se è più recente."
)

dxf_version_code = version_map[selected_version_label]

st.sidebar.info(f"I file verranno salvati in formato **{dxf_version_code}**.")

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
            
            dxf_string = output_stream.getvalue()
            dxf_bytes = dxf_string.encode('utf-8')
            
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
    
    spacing = st.number_input("Distanza righe (mm) - (Scala Hatch)", min_value=0.05, value=0.2, step=0.05, format="%.2f")

    if uploaded_file is not None:
        if st.button("Applica Campitura"):
            try:
                # 1. Lettura e PATCHING automatico per R13/R14
                bytes_data = uploaded_file.getvalue()
                string_data = bytes_data.decode('utf-8', errors='ignore')
                
                # --- HACK DI COMPATIBILITÀ ---
                # Se il file dice di essere versione 13 (AC1012) o 14 (AC1014),
                # mentiamo alla libreria dicendo che è una 2000 (AC1015) per forzarne la lettura.
                # La struttura geometrica è spesso simile abbastanza da funzionare.
                is_patched = False
                if "AC1012" in string_data:
                    string_data = string_data.replace("AC1012", "AC1015")
                    st.warning("⚠️ Rilevato file R13 (AC1012). Tentativo di conversione forzata in lettura...")
                    is_patched = True
                elif "AC1014" in string_data:
                    string_data = string_data.replace("AC1014", "AC1015")
                    st.warning("⚠️ Rilevato file R14 (AC1014). Tentativo di conversione forzata in lettura...")
                    is_patched = True

                try:
                    doc_original = ezdxf.read(StringIO(string_data))
                except ezdxf.DXFError as e:
                    # Se il trucco non funziona, ci arrendiamo
                    st.error(f"Impossibile leggere il file anche dopo il patching. Il formato R13 è troppo complesso. Errore: {e}")
                    st.stop()
                
                # Creiamo un NUOVO documento per l'export
                doc_export = ezdxf.new(dxf_version_code)
                doc_export.units = units.MM
                msp_export = doc_export.modelspace()
                msp_original = doc_original.modelspace()

                hatch_scale = spacing 
                
                # Creazione Hatch
                # Nota: R12 NON supporta le entità HATCH complesse.
                # Se l'utente seleziona R12, ezdxf cercherà di degradare l'Hatch a blocchi o linee se possibile,
                # oppure potrebbe non visualizzarlo. 
                # Tuttavia, per le macchine laser, spesso l'Hatch deve essere esploso in linee.
                # Qui usiamo l'entità Hatch standard.
                
                hatch = msp_export.add_hatch(color=1)
                hatch.set_pattern_fill('ANSI31', scale=hatch_scale)
                hatch.dxf.hatch_style = 0 
                
                count = 0
                
                for entity in msp_original:
                    if entity.dxftype() == 'CIRCLE':
                        # Copia nel nuovo file
                        msp_export.add_circle(entity.dxf.center, entity.dxf.radius, dxfattribs={'layer': 'GEOMETRIA'})
                        
                        # Aggiungi a Hatch
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
                    
                    # Supporto basilare per vecchie POLYLINE (comuni in R12/R13)
                    elif entity.dxftype() == 'POLYLINE':
                         if entity.is_closed:
                            # Estraiamo i punti (la logica è complessa per polyline 3d, assumiamo 2d semplice)
                            points = [v.dxf.location[:2] for v in entity.vertices]
                            if points:
                                msp_export.add_polyline2d(points, close=True, dxfattribs={'layer': 'GEOMETRIA'})
                                hatch.paths.add_polyline_path(points)
                                count += 1

                if count > 0:
                    st.success(f"Campitura creata! Export verso: {dxf_version_code}")
                    if is_patched:
                        st.info("Il file originale R13 è stato letto con successo grazie alla modalità compatibilità.")

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
                    st.warning("Nessuna forma chiusa valida trovata (Cerchi o Polilinee chiuse).")
                    
            except Exception as e:
                st.error(f"Si è verificato un errore critico: {e}")
