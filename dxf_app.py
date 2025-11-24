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

# Dizionario per mappare le etichette leggibili ai codici interni di ezdxf
# La chiave è quello che vedi nel menu, il valore è il codice DXF.
version_map = {
    "R12 (AC1009) - Molto Vecchio": "R12",
    "R13 (AC1012) - Release 13": "R13",
    "R14 (AC1014) - Release 14": "R14",
    "R2000 (AC1015) - Standard": "R2000",
    "R2004 (AC1018)": "R2004",
    "R2007 (AC1021)": "R2007",
    "R2010 (AC1024) - Recente": "R2010"
}

# Creiamo il menu a tendina. 
# index=1 imposta "R13" come default (perché è il secondo elemento della lista, partendo da 0)
selected_version_label = st.sidebar.selectbox(
    "Versione DXF Output",
    options=list(version_map.keys()),
    index=1, 
    help="Seleziona la versione compatibile con la tua macchina laser. R13 è impostato come default."
)

# Recuperiamo il codice effettivo (es. "R13") da passare alla libreria
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
            # Creazione del documento DXF con la versione selezionata
            doc = ezdxf.new(dxf_version_code)
            doc.units = units.MM
            msp = doc.modelspace()

            # Aggiunta dei cerchi
            msp.add_circle((0, 0), radius=r_int, dxfattribs={'layer': 'CERCHI'})
            msp.add_circle((0, 0), radius=r_ext, dxfattribs={'layer': 'CERCHI'})

            # Usiamo StringIO perché DXF è testo
            output_stream = StringIO()
            doc.write(output_stream)
            
            # Convertiamo la stringa in bytes per il download
            dxf_string = output_stream.getvalue()
            dxf_bytes = dxf_string.encode('utf-8')
            
            st.success(f"File generato in versione {dxf_version_code}!")
            
            # Bottone di download
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
    
    # Parametro spaziatura
    spacing = st.number_input("Distanza righe (mm) - (Scala Hatch)", min_value=0.05, value=0.2, step=0.05, format="%.2f")

    if uploaded_file is not None:
        if st.button("Applica Campitura"):
            try:
                # Se l'utente ha scelto R12, avvisiamo che l'Hatch è problematico
                if dxf_version_code == "R12":
                    st.warning("⚠️ Attenzione: La versione R12 non supporta le entità Hatch moderne. Potrebbe non funzionare correttamente su software vecchi.")

                # 1. Lettura del file
                bytes_data = uploaded_file.getvalue()
                string_data = bytes_data.decode('utf-8', errors='ignore')
                
                # Carichiamo il DXF originale
                doc_original = ezdxf.read(StringIO(string_data))
                
                # Creiamo un NUOVO documento con la versione desiderata (es. R13)
                doc_export = ezdxf.new(dxf_version_code)
                doc_export.units = units.MM
                msp = doc_export.modelspace()
                
                # Leggiamo il modelspace originale per copiare le geometrie
                msp_original = doc_original.modelspace()

                hatch_scale = spacing 
                
                # Creiamo l'entità Hatch vuota nel NUOVO documento
                hatch = msp.add_hatch(color=1)
                hatch.set_pattern_fill('ANSI31', scale=hatch_scale)
                hatch.dxf.hatch_style = 0 
                
                count = 0
                
                # Copiamo le entità e creiamo i contorni
                # Nota: In un caso reale complesso dovremmo copiare le entità originali nel nuovo file.
                # Qui ricreiamo geometricamente i contorni sull'hatch basandoci sull'input.
                
                for entity in msp_original:
                    if entity.dxftype() == 'CIRCLE':
                        # Ricreiamo il cerchio nel nuovo file per visualizzazione
                        msp.add_circle(entity.dxf.center, entity.dxf.radius, dxfattribs={'layer': 'GEOMETRIA'})
                        
                        # Aggiungiamo al path dell'hatch
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
                            # Ricreiamo la polilinea nel nuovo file
                            msp.add_lwpolyline(points, close=True, dxfattribs={'layer': 'GEOMETRIA'})
                            
                            # Aggiungiamo al path dell'hatch
                            hatch.paths.add_polyline_path(points)
                            count += 1

                if count > 0:
                    st.success(f"Campitura creata! Versione export: {dxf_version_code}")
                    
                    # Salvataggio
                    output_stream = StringIO()
                    doc_export.write(output_stream)
                    dxf_out_string = output_stream.getvalue()
                    dxf_out_bytes = dxf_out_string.encode('utf-8')
                    
                    st.download_button(
                        label="📥 Scarica DXF Modificato",
                        data=dxf_out_bytes,
                        file_name=f"hatch_{dxf_version_code}_{uploaded_file.name}",
                        mime="application/dxf"
                    )
                else:
                    st.warning("Nessuna forma chiusa valida trovata.")
                    
            except Exception as e:
                st.error(f"Si è verificato un errore: {e}")
