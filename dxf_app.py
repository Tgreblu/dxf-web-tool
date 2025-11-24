import streamlit as st
import ezdxf
from ezdxf import units
from ezdxf.addons import Importer
from io import BytesIO, StringIO
import math

# Configurazione della pagina Streamlit
st.set_page_config(page_title="DXF Generator & Hatcher", layout="centered")

st.title("🛠️ DXF Laser Tool")
st.markdown("""
Questa app ti permette di:
1. Creare due cerchi concentrici.
2. Applicare una campitura (Hatch) a file esistenti (Supporta Cerchi, Polilinee, Spline, Ellissi).
""")

# Funzione CORRETTA per convertire il DXF in bytes per il download
def get_dxf_bytes(doc):
    text_buffer = StringIO()
    doc.write(text_buffer)
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
        # R12 per massima compatibilità geometria semplice
        doc = ezdxf.new('R12')
        msp = doc.modelspace()
        
        msp.add_circle((0, 0), radius=r_outer)
        if r_inner > 0:
            msp.add_circle((0, 0), radius=r_inner)
            
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
    st.info("Carica un file DXF. Supporta: Cerchi, Polilinee, Spline, Ellissi.")

    uploaded_file = st.file_uploader("Carica il tuo file DXF", type=["dxf"])
    
    # Parametri campitura
    hatch_dist = st.slider("Distanza Linee (mm)", 0.1, 5.0, 0.2, step=0.1)
    hatch_scale = hatch_dist 
    
    if uploaded_file is not None:
        try:
            # 1. Lettura File
            bytes_content = uploaded_file.getvalue()
            try:
                str_content = bytes_content.decode('cp1252')
            except UnicodeDecodeError:
                str_content = bytes_content.decode('utf-8', errors='ignore')
            
            # Carichiamo il documento originale
            source_doc = ezdxf.read(StringIO(str_content))
            source_msp = source_doc.modelspace()
            
            # 2. Creazione Nuovo Documento (R2000 necessario per Hatch e Spline)
            new_doc = ezdxf.new('R2000') 
            new_msp = new_doc.modelspace()
            
            # 3. Importazione Geometrie
            # Usiamo l'Importer per copiare le entità dal file originale a quello nuovo
            importer = Importer(source_doc, new_doc)
            
            entities_to_hatch = []
            valid_types = ['CIRCLE', 'LWPOLYLINE', 'POLYLINE', 'SPLINE', 'ELLIPSE']
            
            # Cerchiamo tutte le entità valide nello spazio modello
            for entity in source_msp:
                if entity.dxftype() in valid_types:
                    entities_to_hatch.append(entity)
            
            if len(entities_to_hatch) > 0:
                st.write(f"Trovate {len(entities_to_hatch)} geometrie valide (incluse Spline/Polilinee).")
                
                # Importiamo le geometrie nel nuovo file (così rimangono identiche per il taglio)
                importer.add(entities_to_hatch)
                importer.finalize()
                
                # 4. Creazione Campitura
                hatch = new_msp.add_hatch(color=1) 
                hatch.set_pattern_fill('ANSI31', scale=hatch_scale)
                
                # Aggiungiamo i percorsi al tratteggio usando le entità originali
                # ezdxf calcola automaticamente il perimetro
                for entity in entities_to_hatch:
                    # make_path converte qualsiasi geometria (anche Spline) in un percorso calcolabile
                    path = ezdxf.path.make_path(entity)
                    # flattening converte curve in segmentini per il tratteggio
                    hatch.paths.add_polyline_path(path.flattening(distance=0.01))

                # 5. Export
                out_hatch_buffer = get_dxf_bytes(new_doc)
                
                st.success("Campitura applicata con successo!")
                st.download_button(
                    label="Scarica File Campito.dxf",
                    data=out_hatch_buffer,
                    file_name=f"hatch_{uploaded_file.name}",
                    mime="application/dxf"
                )
            else:
                st.warning("Non ho trovato entità valide (Cerchi, Polilinee, Spline) nel file caricato.")
                
        except Exception as e:
            st.error(f"Si è verificato un errore durante l'elaborazione: {e}")

st.markdown("---")
st.caption("Creato per te - Supporto Spline e Geometrie Complesse")
