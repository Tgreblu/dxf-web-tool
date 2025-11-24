import io
import math
from typing import List, Tuple

import streamlit as st
import ezdxf
from ezdxf import recover

from shapely.geometry import Polygon, MultiPolygon, LineString, Point
from shapely.ops import unary_union
from shapely import affinity


# ==========================
#   FUNZIONI GEOMETRICHE
# ==========================

def float_range(start: float, stop: float, step: float):
    """Range per float, inclusivo sullo stop con una piccola tolleranza."""
    x = start
    while x <= stop + 1e-9:
        yield x
        x += step


def build_annulus_region(outer_radius: float, inner_radius: float) -> Polygon:
    """Regione 'anello' tra due cerchi concentrici usando Shapely."""
    if outer_radius <= 0 or inner_radius <= 0:
        raise ValueError("I raggi devono essere > 0.")
    if inner_radius >= outer_radius:
        raise ValueError("Il raggio interno deve essere < del raggio esterno.")

    # Approssimo il cerchio con un buffer di un punto
    outer = Point(0, 0).buffer(outer_radius, resolution=128)
    inner = Point(0, 0).buffer(inner_radius, resolution=128)
    region = outer.difference(inner)
    if region.is_empty:
        raise RuntimeError("La regione ad anello risulta vuota.")
    return region


def extract_loop_region_from_dxf(doc: ezdxf.document.Drawing):
    """
    Legge dal modelspace tutte le entità che possono essere loop chiusi
    (CIRCLE, LWPOLYLINE chiuse, POLYLINE chiuse) e costruisce una regione
    geometrica totale (MultiPolygon/Polygon) con Shapely.

    Stile 'loop nidificati': se hai un perimetro esterno e uno interno,
    quello interno diventa un buco.
    """
    msp = doc.modelspace()
    polys = []

    for e in msp:
        dxftype = e.dxftype()
        if dxftype == "CIRCLE":
            cx, cy, _ = e.dxf.center
            r = e.dxf.radius
            if r <= 0:
                continue
            poly = Point(cx, cy).buffer(r, resolution=128)
            polys.append(poly)

        elif dxftype == "LWPOLYLINE":
            if not e.closed:
                continue
            points = [(p[0], p[1]) for p in e.get_points()]  # (x, y, [start_width, end_width, bulge])
            if len(points) < 3:
                continue
            poly = Polygon(points)
            if not poly.is_valid or poly.is_empty:
                continue
            polys.append(poly)

        elif dxftype == "POLYLINE":
            # POLYLINE 2D chiusa
            try:
                is_closed = bool(e.dxf.flags & 1)  # bit 1 = closed
            except AttributeError:
                is_closed = False
            if not is_closed:
                continue
            points = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            if len(points) < 3:
                continue
            poly = Polygon(points)
            if not poly.is_valid or poly.is_empty:
                continue
            polys.append(poly)

    if not polys:
        raise RuntimeError(
            "Nel DXF non ho trovato loop chiusi (CIRCLE o (LW)POLYLINE chiuse)."
        )

    region = unary_union(polys)
    if region.is_empty:
        raise RuntimeError("La regione risultante dai loop è vuota.")

    return region


def make_hatch_lines(
    region,
    spacing: float,
    angle_deg: float = 45.0,
) -> List[Tuple[float, float, float, float]]:
    """
    Genera segmenti di linee (x1, y1, x2, y2) che riempiono la regione
    con linee parallele inclinate di angle_deg, distanziate di 'spacing'.

    region: Polygon o MultiPolygon (Shapely)
    """
    if spacing <= 0:
        raise ValueError("La distanza tra le linee deve essere > 0.")

    # ruoto la regione in modo da usare linee orizzontali più facili da gestire
    rot_region = affinity.rotate(region, -angle_deg, origin=(0, 0), use_radians=False)

    minx, miny, maxx, maxy = rot_region.bounds

    # Creo linee orizzontali da minx - margine a maxx + margine
    margin = spacing * 2
    x_start = minx - margin
    x_end = maxx + margin

    segments = []

    for y in float_range(miny - margin, maxy + margin, spacing):
        base_line = LineString([(x_start, y), (x_end, y)])
        inter = rot_region.intersection(base_line)

        if inter.is_empty:
            continue

        if isinstance(inter, LineString):
            xs, ys, xe, ye = *inter.coords[0], *inter.coords[-1]
            # ruoto indietro
            seg = LineString([(xs, ys), (xe, ye)])
            seg_rot = affinity.rotate(seg, angle_deg, origin=(0, 0), use_radians=False)
            (x1, y1), (x2, y2) = seg_rot.coords[0], seg_rot.coords[-1]
            segments.append((x1, y1, x2, y2))

        elif inter.geom_type == "MultiLineString":
            for part in inter:
                xs, ys, xe, ye = *part.coords[0], *part.coords[-1]
                seg = LineString([(xs, ys), (xe, ye)])
                seg_rot = affinity.rotate(
                    seg, angle_deg, origin=(0, 0), use_radians=False
                )
                (x1, y1), (x2, y2) = seg_rot.coords[0], seg_rot.coords[-1]
                segments.append((x1, y1, x2, y2))

        # Se arriva GeometryCollection, ignoro le parti non lineari

    return segments


# ==========================
#   FUNZIONI DXF
# ==========================

def load_dxf_from_bytes(data: bytes) -> ezdxf.document.Drawing:
    """Carica un DXF da bytes in modo robusto."""
    stream = io.BytesIO(data)
    doc, auditor = recover.read(stream)
    if auditor.has_errors:
        st.warning(
            "Il DXF conteneva alcuni errori, ezdxf ha provato a correggerli."
        )
    return doc


def create_dxf_r12_with_lines(
    region,
    segments: List[Tuple[float, float, float, float]],
    boundary_geometries=None,
) -> io.BytesIO:
    """
    Crea un DXF R12 con:
    - (opzionale) le geometrie di contorno (boundary_geometries)
    - tutte le linee della campitura.

    boundary_geometries: lista di dict semplici, es:
        {"type": "circle", "center": (cx, cy), "radius": r}
        {"type": "polyline", "points": [(x,y), ...]}
    """
    doc = ezdxf.new("R12")
    msp = doc.modelspace()

    # Disegno perimetri, se forniti
    if boundary_geometries:
        for g in boundary_geometries:
            if g["type"] == "circle":
                msp.add_circle(g["center"], g["radius"])
            elif g["type"] == "polyline":
                msp.add_lwpolyline(g["points"], format="xy", close=True)

    # Aggiungo linee di hatch
    for (x1, y1, x2, y2) in segments:
        msp.add_line((x1, y1), (x2, y2))

    buf = io.BytesIO()
    doc.write(buf)  # R12 ASCII DXF
    buf.seek(0)
    return buf


def extract_boundary_geometries_from_dxf(doc: ezdxf.document.Drawing):
    """
    Estrae le geometrie di contorno (CIRCLE, LWPOLYLINE chiuse, POLYLINE chiuse)
    per ridisegnarle nel nuovo DXF.
    """
    msp = doc.modelspace()
    geometries = []

    for e in msp:
        dxftype = e.dxftype()
        if dxftype == "CIRCLE":
            cx, cy, _ = e.dxf.center
            r = e.dxf.radius
            if r <= 0:
                continue
            geometries.append(
                {
                    "type": "circle",
                    "center": (cx, cy),
                    "radius": r,
                }
            )
        elif dxftype == "LWPOLYLINE":
            if not e.closed:
                continue
            points = [(p[0], p[1]) for p in e.get_points()]
            if len(points) < 3:
                continue
            geometries.append(
                {
                    "type": "polyline",
                    "points": points,
                }
            )
        elif dxftype == "POLYLINE":
            try:
                is_closed = bool(e.dxf.flags & 1)
            except AttributeError:
                is_closed = False
            if not is_closed:
                continue
            points = [(v.dxf.location.x, v.dxf.location.y) for v in e.vertices]
            if len(points) < 3:
                continue
            geometries.append(
                {
                    "type": "polyline",
                    "points": points,
                }
            )

    return geometries


# ==========================
#   INTERFACCIA STREAMLIT
# ==========================

def main():
    st.set_page_config(
        page_title="DXF Hatch Lines (R12)",
        page_icon="🌀",
        layout="centered",
    )

    st.title("🌀 Generatore DXF con campitura a linee (compatibile R12)")

    st.markdown(
        """
Questa web app:

1. **Genera un annulus** (due cerchi concentrici) con campitura a linee inclinate.
2. **Carica un DXF con loop chiusi** (cerchi / polilinee chiuse) e crea un nuovo **DXF R12**
   con la campitura a linee nei loop nidificati.

🛈 *Nota tecnica:*  
- Uso **ezdxf** che può scrivere fino al formato **R12** e formati successivi (R2000+),  
  ma **non** può scrivere R13 nativo.  
- La campitura è fatta con **LINE** già tagliate sui perimetri, non con entità HATCH.
"""
    )

    mode = st.sidebar.radio(
        "Modalità",
        (
            "1) Genera annulus (due cerchi concentrici)",
            "2) Aggiungi campitura a DXF con loop chiusi",
        ),
    )

    if mode.startswith("1)"):
        st.header("1) Genera annulus con campitura")

        col1, col2 = st.columns(2)
        with col1:
            outer_radius = st.number_input(
                "Raggio esterno (unità DXF, es. mm)",
                min_value=0.01,
                value=10.0,
                step=0.1,
            )
        with col2:
            inner_radius = st.number_input(
                "Raggio interno (unità DXF, es. mm)",
                min_value=0.01,
                value=5.0,
                step=0.1,
            )

        spacing = st.number_input(
            "Distanza tra le linee (es. 0.2)",
            min_value=0.01,
            value=0.2,
            step=0.05,
            help="Valore tipico 0.2 per 0,2 mm.",
        )

        angle = st.number_input(
            "Angolo delle linee (gradi)",
            min_value=0.0,
            max_value=180.0,
            value=45.0,
            step=5.0,
        )

        if st.button("Crea DXF annulus"):
            try:
                region = build_annulus_region(outer_radius, inner_radius)
                segments = make_hatch_lines(region, spacing=spacing, angle_deg=angle)

                # Perimetri come cerchi
                boundaries = [
                    {"type": "circle", "center": (0.0, 0.0), "radius": outer_radius},
                    {"type": "circle", "center": (0.0, 0.0), "radius": inner_radius},
                ]

                buf = create_dxf_r12_with_lines(
                    region=region,
                    segments=segments,
                    boundary_geometries=boundaries,
                )

                filename = f"annulus_lines_{outer_radius:.2f}_{inner_radius:.2f}.dxf"
                st.success("DXF generato (formato R12) con annulus + campitura a linee.")
                st.download_button(
                    label="⬇️ Scarica DXF annulus",
                    data=buf,
                    file_name=filename,
                    mime="image/vnd.dxf",
                )

            except Exception as e:
                st.error(f"Errore nella generazione dell'annulus: {e}")

    else:
        st.header("2) Campitura su DXF con loop chiusi")

        st.markdown(
            """
Carica un DXF che contenga **CIRCLE** e/o **(LW)POLYLINE chiuse** come perimetri.
L'app creerà un **nuovo DXF R12** con:

- gli stessi perimetri (cerchi e polilinee chiuse),
- la campitura a linee nei loop (con buchi se ci sono loop nidificati).
"""
        )

        uploaded = st.file_uploader(
            "Carica il DXF sorgente",
            type=["dxf"],
        )

        spacing = st.number_input(
            "Distanza tra le linee (es. 0.2)",
            min_value=0.01,
            value=0.2,
            step=0.05,
        )

        angle = st.number_input(
            "Angolo delle linee (gradi)",
            min_value=0.0,
            max_value=180.0,
            value=45.0,
            step=5.0,
        )

        if uploaded is not None and st.button("Elabora DXF"):
            try:
                dxf_bytes = uploaded.read()
                src_doc = load_dxf_from_bytes(dxf_bytes)

                region = extract_loop_region_from_dxf(src_doc)
                segments = make_hatch_lines(region, spacing=spacing, angle_deg=angle)
                boundaries = extract_boundary_geometries_from_dxf(src_doc)

                buf = create_dxf_r12_with_lines(
                    region=region,
                    segments=segments,
                    boundary_geometries=boundaries,
                )

                st.success(
                    "DXF elaborato. Creato nuovo DXF R12 con perimetri + campitura a linee."
                )
                st.download_button(
                    label="⬇️ Scarica DXF con campitura",
                    data=buf,
                    file_name="dxf_campitura_linee_R12.dxf",
                    mime="image/vnd.dxf",
                )

            except Exception as e:
                st.error(f"Errore durante l'elaborazione del DXF: {e}")

    st.markdown("---")
    st.caption(
        "Output in formato DXF R12 (AC1009) con campitura realizzata tramite entità LINE."
    )


if __name__ == "__main__":
    main()
