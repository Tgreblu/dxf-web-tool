import streamlit as st
import ezdxf
from ezdxf import units
from io import StringIO

# Configurazione della pagina
st.set_page_config(page_title="DXF Utility Tool", layout="centered")

st.title("🛠️ DXF Utility Web App")
st.markdown("Genera cerchi concentrici o aggiungi hatching ai tuoi file DXF.")

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
            # Creazione del documento DXF
            doc = ezdxf.new('R2010')
            doc.units = units.MM
            msp = doc.modelspace()

            # Aggiunta dei cerchi
            msp.add_circle((0, 0), radius=r_int, dxfattribs={'layer': 'CERCHI'})
            msp.add_circle((0, 0), radius=r_ext, dxfattribs={'layer': 'CERCHI'})

            # CORREZIONE: Usiamo StringIO perché DXF è testo
            output_stream = StringIO()
            doc.write(output_stream)
            
            # Convertiamo la stringa in bytes per il download (UTF-8 è standard sicuro)
            dxf_string = output_stream.getvalue()
            dxf_bytes = dxf_string.encode('utf-8')
            
            st.success("File generato con successo!")
            
            # Bottone di download
            st.download_button(
                label="📥 Scarica Cerchi.dxf",
                data=dxf_bytes,
                file_name="cerchi_concentrici.dxf",
                mime="application/dxf"
            )
        except Exception as e:
            st.error(f"Errore durante la generazione: {e}")

# --- FUNZIONE 2: HATCHING (CAMPITURA) ---
with tab2:
    st.header("Aggiungi Campitura a 45°")
    st.info("Carica un file DXF contenente forme chiuse (Cerchi, Polilinee chiuse).")

    uploaded_file = st.file_uploader("Carica il tuo file DXF", type=["dxf"])
    
    # Parametro spaziatura
    spacing = st.number_input("Distanza righe (mm) - (Scala Hatch)", min_value=0.05, value=0.2, step=0.05, format="%.2f")

    if uploaded_file is not None:
        if st.button("Applica Campitura"):
            try:
                # 1. Leggiamo il file caricato (Streamlit dà bytes)
                bytes_data = uploaded_file.getvalue()
                
                # 2. Decodifichiamo i bytes in stringa per ezdxf
                # Usiamo 'ignore' per saltare eventuali caratteri corrotti, ma utf-8 è standard
                string_data = bytes_data.decode('utf-8', errors='ignore')
                
                # 3. Leggiamo il DXF dalla stringa usando StringIO
                doc = ezdxf.read(StringIO(string_data))
                msp = doc.modelspace()
                
                # Definizione della scala (approssimazione per pattern ANSI31)
                hatch_scale = spacing 
                
                count = 0
                
                # Cerchiamo entità chiuse da campire
                for entity in msp:
                    if entity.dxftype() == 'CIRCLE':
                        # Creiamo l'hatch
                        hatch = msp.add_hatch(color=1) # Colore 1 = Rosso
                        
                        # Aggiungiamo il contorno (boundary) basato sul cerchio esistente
                        hatch.paths.add_edge_path().add_arc(
                            center=entity.dxf.center,
                            radius=entity.dxf.radius,
                            start_angle=0,
                            end_angle=360
                        )
                        # Impostiamo il pattern ANSI31 (linee a 45 gradi)
                        hatch.set_pattern_fill('ANSI31', scale=hatch_scale)
                        count += 1
                        
                    elif entity.dxftype() == 'LWPOLYLINE':
                        if entity.is_closed:
                            hatch = msp.add_hatch(color=1)
                            path = hatch.paths.add_polyline_path(entity.get_points(format='xy'))
                            hatch.set_pattern_fill('ANSI31', scale=hatch_scale)
                            count += 1

                if count > 0:
                    st.success(f"Campitura applicata a {count} elementi!")
                    
                    # 4. Salviamo il risultato in memoria usando StringIO
                    output_stream = StringIO()
                    doc.write(output_stream)
                    
                    # 5. Codifichiamo in bytes per il download
                    dxf_out_string = output_stream.getvalue()
                    dxf_out_bytes = dxf_out_string.encode('utf-8')
                    
                    st.download_button(
                        label="📥 Scarica DXF Modificato",
                        data=dxf_out_bytes,
                        file_name=f"hatch_{uploaded_file.name}",
                        mime="application/dxf"
                    )
                else:
                    st.warning("Nessuna forma chiusa (Cerchi o Polilinee chiuse) trovata da campire.")
                    
            except Exception as e:
                st.error(f"Si è verificato un errore durante l'elaborazione del file: {e}")
