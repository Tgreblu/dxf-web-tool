import streamlit as st
import ezdxf
from ezdxf import units
from io import BytesIO, StringIO
import math

# Configurazione della pagina Streamlit
st.set_page_config(page_title="DXF Generator & Hatcher", layout="centered")

st.title("🛠️ DXF Laser Tool")
st.markdown("""
Questa app ti permette di:
1. Creare due cerchi concentrici.
2. Applicare una campitura (Hatch) a file esistenti.
""")

# Funzione CORRETTA per convertire il DXF in bytes per il download
# ezdxf scrive testo, quindi usiamo StringIO poi convertiamo in bytes
def get_dxf_bytes(doc):
    text_buffer = StringIO()
    doc.write(text_buffer)
    # Convertiamo la stringa DXF in bytes (utf-8 è sicuro per il web, cp1252 per compatibilità vecchia)
    # Usiamo cp1252 per massima compatibilità con macchine laser/CNC
    return text_buffer.getvalue().encode('cp1252', errors='ignore')

# --- TAB 1: CREATORE DI CERCHI ---
tab1, tab2 = st.tabs(["🔵 Crea Cerchi", "📐 Applica Campitura"])

with tab1:
    st.header("Generatore Cerchi Concentrici")
    
    col1, col2 = st.columns(2)
    with col1:
        r_outer = st.number_input("Raggio Esterno (mm)", min_value=1.0, value=50.0, step=1.0)
    with col2:
        r_inner = st.number_input("Raggio Interno (mm)", min_value=0.0, value=30.0, step=1.0, help="Metti 0 se vuoi solo un cerchio")

    if r_inner >= r_outer:
        st.error("Il raggio interno deve essere minore di quello esterno!")
    
    if st.button("Genera DXF Cerchi"):
        # Creiamo un nuovo documento DXF compatibile (R12 è il più semplice e compatibile per geometrie base)
        doc = ezdxf.new('R12')
        msp = doc.modelspace()
        
        # Aggiungo i cerchi
        msp.add_circle((0, 0), radius=r_outer)
        if r_inner > 0:
            msp.add_circle((0, 0), radius=r_inner)
            
        # Preparo il file
        out_buffer = get_dxf_bytes(doc)
        
        st.success("File generato con successo!")
        st.download_button(
            label="Scarica Cerchi.dxf",
            data=out_buffer,
            file_name="cerchi_concentrici.dxf",
            mime="application/dxf"
        )

# --- TAB 2: APPLICA CAMPITURA (HATCHING) ---
with tab2:
    st.header("Applica Campitura (Hatch)")
    st.info("Carica un file DXF contenente geometrie chiuse (Cerchi o Polilinee). L'algoritmo riempirà le aree vuote.")

    uploaded_file = st.file_uploader("Carica il tuo file DXF", type=["dxf"])
    
    # Parametri campitura
    hatch_dist = st.slider("Distanza Linee (mm)", 0.1, 5.0, 0.2, step=0.1)
    hatch_scale = hatch_dist 
    
    if uploaded_file is not None:
        try:
            # CORREZIONE LETTURA:
            # 1. Otteniamo i bytes dal file caricato
            bytes_content = uploaded_file.getvalue()
            
            # 2. Decodifichiamo i bytes in stringa (DXF è un formato testo)
            # Proviamo prima cp1252 (standard Windows/CNC), poi utf-8 come fallback
            try:
                str_content = bytes_content.decode('cp1252')
            except UnicodeDecodeError:
                str_content = bytes_content.decode('utf-8', errors='ignore')
            
            # 3. Passiamo lo stream di TESTO a ezdxf
            doc = ezdxf.read(StringIO(str_content))
            
            msp = doc.modelspace()
            
            # Creiamo un nuovo documento per l'output (R2000 necessario per HATCH)
            new_doc = ezdxf.new('R2000') 
            new_msp = new_doc.modelspace()
            
            # --- LOGICA DI CAMPITURA ---
            hatch = new_msp.add_hatch(color=1) 
            hatch.set_pattern_fill('ANSI31', scale=hatch_scale)
            
            found_entities = 0
            
            for entity in msp:
                if entity.dxftype() == 'CIRCLE':
                    hatch.paths.add_polyline_path(
                        ezdxf.path.make_path(entity).flattening(distance=0.01)
                    )
                    # Copia geometria originale
                    new_msp.add_circle(entity.dxf.center, entity.dxf.radius)
                    found_entities += 1
                    
                elif entity.dxftype() == 'LWPOLYLINE':
                    path = ezdxf.path.make_path(entity)
                    hatch.paths.add_polyline_path(path.flattening(distance=0.01))
                    # Copia polilinea originale
                    new_msp.add_lwpolyline(entity.get_points(), close=entity.closed)
                    found_entities += 1

            if found_entities > 0:
                st.write(f"Trovate {found_entities} geometrie. Generazione campitura...")
                
                # Usiamo la funzione corretta get_dxf_bytes
                out_hatch_buffer = get_dxf_bytes(new_doc)
                
                st.success("Campitura applicata! Scarica il file qui sotto.")
                st.download_button(
                    label="Scarica File Campito.dxf",
                    data=out_hatch_buffer,
                    file_name=f"hatch_{uploaded_file.name}",
                    mime="application/dxf"
                )
            else:
                st.warning("Non ho trovato entità valide (Cerchi o Polilinee Chiuse) nel file caricato.")
                
        except Exception as e:
            st.error(f"Si è verificato un errore durante l'elaborazione: {e}")

st.markdown("---")
st.caption("Creato per te - Compatibile R2000")
