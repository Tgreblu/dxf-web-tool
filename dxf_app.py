import streamlit as st
import ezdxf
from ezdxf import units
from io import StringIO

# Configurazione della pagina
st.set_page_config(page_title="DXF Utility Tool", layout="centered")

st.title("🛠️ DXF Utility Web App")
st.markdown("Genera cerchi concentrici o aggiungi hatching con rilevamento isole.")

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

            # Usiamo StringIO perché DXF è testo
            output_stream = StringIO()
            doc.write(output_stream)
            
            # Convertiamo la stringa in bytes per il download
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

# --- FUNZIONE 2: HATCHING (CAMPITURA INTELLIGENTE) ---
with tab2:
    st.header("Aggiungi Campitura a 45°")
    st.info("Carica un file DXF. Le forme concentriche verranno campite come 'isole' (es. ciambella).")

    uploaded_file = st.file_uploader("Carica il tuo file DXF", type=["dxf"])
    
    # Parametro spaziatura
    spacing = st.number_input("Distanza righe (mm) - (Scala Hatch)", min_value=0.05, value=0.2, step=0.05, format="%.2f")

    if uploaded_file is not None:
        if st.button("Applica Campitura"):
            try:
                # 1. Lettura del file
                bytes_data = uploaded_file.getvalue()
                string_data = bytes_data.decode('utf-8', errors='ignore')
                doc = ezdxf.read(StringIO(string_data))
                msp = doc.modelspace()
                
                # Definizione della scala
                hatch_scale = spacing 
                
                # --- MODIFICA FONDAMENTALE PER LA LOGICA "ISOLE" ---
                # Invece di creare un hatch per ogni oggetto, creiamo UN SOLO oggetto Hatch
                # e gli passiamo tutti i contorni che troviamo.
                # In questo modo il DXF calcola automaticamente "pieno, vuoto, pieno" (regola Odd/Even).
                
                # Creiamo l'entità Hatch vuota
                hatch = msp.add_hatch(color=1) # Colore 1 = Rosso
                hatch.set_pattern_fill('ANSI31', scale=hatch_scale)
                # Impostiamo lo stile "Normal" (0) che gestisce le isole (pieno-vuoto-pieno)
                hatch.dxf.hatch_style = 0 
                
                count = 0
                
                # Cerchiamo tutte le entità chiuse e le aggiungiamo allo STESSO hatch
                for entity in msp:
                    if entity.dxftype() == 'CIRCLE':
                        # Aggiungiamo il cerchio come contorno (path) all'hatch unico
                        hatch.paths.add_edge_path().add_arc(
                            center=entity.dxf.center,
                            radius=entity.dxf.radius,
                            start_angle=0,
                            end_angle=360
                        )
                        count += 1
                        
                    elif entity.dxftype() == 'LWPOLYLINE':
                        if entity.is_closed:
                            # Aggiungiamo la polilinea come contorno all'hatch unico
                            hatch.paths.add_polyline_path(entity.get_points(format='xy'))
                            count += 1

                if count > 0:
                    st.success(f"Campitura applicata rilevando {count} contorni!")
                    
                    # Salvataggio
                    output_stream = StringIO()
                    doc.write(output_stream)
                    dxf_out_string = output_stream.getvalue()
                    dxf_out_bytes = dxf_out_string.encode('utf-8')
                    
                    st.download_button(
                        label="📥 Scarica DXF Modificato",
                        data=dxf_out_bytes,
                        file_name=f"hatch_smart_{uploaded_file.name}",
                        mime="application/dxf"
                    )
                else:
                    # Se non abbiamo trovato nulla, rimuoviamo l'hatch vuoto per pulizia
                    msp.delete_entity(hatch)
                    st.warning("Nessuna forma chiusa (Cerchi o Polilinee chiuse) trovata da campire.")
                    
            except Exception as e:
                st.error(f"Si è verificato un errore durante l'elaborazione del file: {e}")
