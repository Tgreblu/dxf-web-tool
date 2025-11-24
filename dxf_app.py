import streamlit as st
import ezdxf
from ezdxf import units
from io import BytesIO

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

            # Salvataggio in buffer di memoria (non su disco fisico)
            buffer = BytesIO()
            doc.write(buffer)
            
            st.success("File generato con successo!")
            
            # Bottone di download
            st.download_button(
                label="📥 Scarica Cerchi.dxf",
                data=buffer.getvalue(),
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
    
    # Parametro spaziatura (richiesta utente: default 0.2mm)
    spacing = st.number_input("Distanza righe (mm)", min_value=0.05, value=0.2, step=0.05, format="%.2f")

    if uploaded_file is not None:
        if st.button("Applica Campitura"):
            try:
                # Lettura del file caricato (Streamlit gestisce i file come bytes)
                # Dobbiamo leggere lo stream come testo per ezdxf
                file_bytes = uploaded_file.getvalue()
                # ezdxf richiede una stringa o un file system, usiamo un buffer testo
                try:
                    doc = ezdxf.read(BytesIO(file_bytes))
                except Exception as e:
                    st.error(f"Impossibile leggere il DXF. Assicurati che sia valido. Err: {e}")
                    st.stop()

                msp = doc.modelspace()
                
                # Definizione del pattern
                # ANSI31 è lo standard per le linee a 45 gradi
                # La scala deve essere calcolata. In ANSI31 standard, scale=1 significa circa 3mm di spaziatura.
                # Questa è una approssimazione: Scale = SpaziaturaDesiderata / SpaziaturaBase
                # Per precisione millimetrica, ezdxf ha strumenti più complessi, ma usiamo la scala visuale qui.
                hatch_scale = spacing  # In DXF metrico puro, spesso scala 1 = 1 unità. 
                                       # Nota: L'hatching DXF è complesso, dipende dalle unità del file origine.
                
                count = 0
                
                # Cerchiamo entità chiuse da campire (Cerchi e Polilinee Chiuse)
                for entity in msp:
                    if entity.dxftype() == 'CIRCLE':
                        hatch = msp.add_hatch(color=1) # Colore 1 = Rosso
                        hatch.paths.add_edge_path().add_arc(
                            center=entity.dxf.center,
                            radius=entity.dxf.radius,
                            start_angle=0,
                            end_angle=360
                        )
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
                    
                    # Preparazione download
                    out_buffer = BytesIO()
                    doc.write(out_buffer)
                    
                    st.download_button(
                        label="📥 Scarica DXF Modificato",
                        data=out_buffer.getvalue(),
                        file_name=f"hatch_{uploaded_file.name}",
                        mime="application/dxf"
                    )
                else:
                    st.warning("Nessuna forma chiusa (Cerchi o Polilinee chiuse) trovata nel ModelSpace da campire.")
                    
            except Exception as e:
                st.error(f"Si è verificato un errore durante l'elaborazione: {e}")