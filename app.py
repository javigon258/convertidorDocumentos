# Módulos estándar
import os
import sys
import base64
import tempfile
import subprocess

# Paquetes de terceros
import streamlit as st
from PIL import Image
from fpdf import FPDF
from ebooklib import epub, ITEM_DOCUMENT, ITEM_STYLE, ITEM_IMAGE
from bs4 import BeautifulSoup
import pdfkit


# --- CONFIGURACIÓN ---
st.set_page_config(page_title="Convertidor de Archivos", page_icon="🧰")
st.title("🧰 Convertidor de Formatos")

# --- MENÚ LATERAL ---
st.sidebar.title("Selecciona una acción")
accion = st.sidebar.radio("¿Qué deseas hacer?", ["📸 Imágenes a PDF", "📖 EPUB a PDF"])

# --- OPCIÓN: TAMAÑO DE PÁGINA ---
page_size = st.sidebar.selectbox("Tamaño de página para el PDF", ["A4", "Carta", "Usar tamaño original de la imagen"])

# --- FUNCIONES ---

def convert_images_to_pdf(images, page_size):
    sizes = {
        "A4": (210, 297),
        "Carta": (215.9, 279.4)
    }

    if page_size == "Usar tamaño original de la imagen":
        pdf = FPDF(unit="mm")
    else:
        pdf = FPDF(unit="mm", format=sizes[page_size])

    for img_file in images:
        img = Image.open(img_file).convert("RGB")
        img_width_px, img_height_px = img.size
        img_path = os.path.join(tempfile.gettempdir(), img_file.name)
        img.save(img_path)

        if page_size == "Usar tamaño original de la imagen":
            width_mm = img_width_px * 0.264583
            height_mm = img_height_px * 0.264583
            pdf.add_page(format=(width_mm, height_mm))
            pdf.image(img_path, x=0, y=0, w=width_mm, h=height_mm)
        else:
            page_w, page_h = sizes[page_size]
            pdf.add_page()
            max_w, max_h = page_w - 20, page_h - 20  # márgenes
            ratio = min(max_w / img_width_px, max_h / img_height_px)
            new_w = img_width_px * ratio
            new_h = img_height_px * ratio
            x = (page_w - new_w) / 2
            y = (page_h - new_h) / 2
            pdf.image(img_path, x=x, y=y, w=new_w, h=new_h)

    output_path = os.path.join(tempfile.gettempdir(), "imagenes_convertidas.pdf")
    pdf.output(output_path)
    return output_path

def convert_epub_to_pdf(uploaded_file, debug=False, st_write=None):
    def dprint(msg):
        if debug:
            (st_write if st_write else print)(msg)

    def get_wkhtmltopdf_path():
        base_path = os.path.dirname(os.path.abspath(__file__))
        exe_name = 'wkhtmltopdf.exe' if sys.platform.startswith('win') else 'wkhtmltopdf'
        return os.path.join(base_path, 'wkhtmltopdf', 'bin', exe_name)

    ruta_wkhtmltopdf = get_wkhtmltopdf_path()
    dprint(f"Usando wkhtmltopdf en: {ruta_wkhtmltopdf}")

    if not os.path.exists(ruta_wkhtmltopdf):
        dprint(f"Error: No se encontró wkhtmltopdf en {ruta_wkhtmltopdf}")
        raise FileNotFoundError(f"No se encontró wkhtmltopdf en {ruta_wkhtmltopdf}")

    if not os.access(ruta_wkhtmltopdf, os.X_OK):
        dprint(f"Error: wkhtmltopdf no tiene permisos de ejecución.")
        raise PermissionError("wkhtmltopdf no tiene permisos de ejecución.")

    config = pdfkit.configuration(wkhtmltopdf=ruta_wkhtmltopdf)


    # Guardar archivo EPUB temporalmente
    with tempfile.NamedTemporaryFile(delete=False, suffix=".epub") as tmp_file:
        tmp_file.write(uploaded_file.read())
        tmp_path = tmp_file.name
    dprint(f"Archivo EPUB guardado temporalmente en: {tmp_path}")

    book = epub.read_epub(tmp_path)
    dprint("EPUB leído correctamente")

    # Extraer metadatos básicos
    title = book.get_metadata('DC', 'title')
    author = book.get_metadata('DC', 'creator')
    title_text = title[0][0] if title else "Sin título"
    author_text = author[0][0] if author else "Desconocido"
    dprint(f"Título extraído: {title_text}")
    dprint(f"Autor extraído: {author_text}")

    # Extraer CSS
    css_content = ""
    for item in book.get_items_of_type(ITEM_STYLE):
        css_content += item.get_content().decode('utf-8') + "\n"
    dprint(f"CSS extraído, longitud total: {len(css_content)} caracteres")

    # Extraer imágenes y codificar en base64
    images_map = {}
    for item in book.get_items_of_type(ITEM_IMAGE):
        images_map[item.file_name] = base64.b64encode(item.get_content()).decode('utf-8')
    dprint(f"Imágenes extraídas: {len(images_map)}")

    # Construcción del índice en HTML (para principio y final)
    def generate_toc_html(book, with_title=True):
        toc_html = ''
        if with_title:
            toc_html += '<h1>Índice</h1>\n'
        toc_html += '<ul>\n'
        def append_toc_items(items):
            for item in items:
                if isinstance(item, epub.Link):
                    yield f'<li><a href="#{item.href}">{item.title}</a></li>'
                elif isinstance(item, tuple) and len(item) == 2:
                    link = item[0]
                    subitems = item[1]
                    yield f'<li><a href="#{link.href}">{link.title}</a><ul>'
                    yield from append_toc_items(subitems)
                    yield '</ul></li>'
        toc_html += "".join(append_toc_items(book.toc))
        toc_html += "\n</ul>\n"
        return toc_html

    # Portada HTML (salto de página después)
    portada_html = f"""
    <div style="page-break-after: always; text-align:center; margin-top: 200px;">
        <h1 style="font-size: 48px; margin-bottom: 20px;">{title_text}</h1>
        <h3 style="font-size: 24px; color: #666;">{author_text}</h3>
    </div>
    """

    # Índice inicial (salto página después)
    toc_inicio_html = f'<div style="page-break-after: always;">{generate_toc_html(book)}</div>'

    # Extraer contenido HTML con anclajes para capítulos y reemplazar imágenes
    html_parts = [portada_html, toc_inicio_html]
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        raw_html = item.get_content().decode('utf-8', errors='ignore')
        soup = BeautifulSoup(raw_html, 'html.parser')

        # Añadir id en body para referencia desde índice
        body_tag = soup.find('body')
        if body_tag and not body_tag.has_attr('id'):
            body_tag['id'] = item.file_name.rsplit('.', 1)[0]

        # Reemplazar imágenes en el HTML con base64 inline
        imgs = soup.find_all('img')
        for img in imgs:
            src = img.get('src')
            if src and src in images_map:
                ext = os.path.splitext(src)[1].lower()
                mime = 'application/octet-stream'
                if ext in ['.jpg', '.jpeg']:
                    mime = 'image/jpeg'
                elif ext == '.png':
                    mime = 'image/png'
                elif ext == '.gif':
                    mime = 'image/gif'
                img['src'] = f"data:{mime};base64,{images_map[src]}"

        html_parts.append(str(soup))

    # Índice final (salto página antes)
    toc_final_html = f'<div style="page-break-before: always;">{generate_toc_html(book)}</div>'
    html_parts.append(toc_final_html)

    # Construir CSS y estilos generales
    default_css = f"""
    <style>
    {css_content}
    body {{ font-family: DejaVu Sans, sans-serif; line-height: 1.6; padding: 20px; }}
    h1, h2, h3 {{ color: #333; margin-top: 24px; margin-bottom: 12px; }}
    img {{ max-width: 100%; height: auto; display: block; margin: 10px auto; }}
    ul {{ margin-left: 20px; }}
    a {{ color: #0645ad; text-decoration: none; }}
    a:hover {{ text-decoration: underline; }}
    div[style*="page-break-before: always;"], div[style*="page-break-after: always;"] {{
        page-break-before: always;
        page-break-after: always;
    }}
    </style>
    """

    # HTML final con portada, índice al inicio y final, y contenido
    html_final = f"""<!DOCTYPE html>
    <html>
    <head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    {default_css}
    <title>{title_text}</title>
    </head>
    <body>
    {''.join(html_parts)}
    </body>
    </html>"""

    # Guardar HTML temporal para debug
    html_temp_path = os.path.join(tempfile.gettempdir(), uploaded_file.name.rsplit('.', 1)[0] + "_full.html")
    with open(html_temp_path, "w", encoding="utf-8") as f:
        f.write(html_final)
    dprint(f"HTML completo guardado en: {html_temp_path}")

    # Opciones PDF con pie de página avanzado (título, autor, páginas)
    options = {
        'enable-local-file-access': None,
        'quiet': '',
        'page-size': 'A4',
        'encoding': 'UTF-8',
        'margin-top': '20mm',
        'margin-bottom': '25mm',
        'margin-left': '20mm',
        'margin-right': '20mm',
        'footer-left': title_text,
        'footer-center': author_text,
        'footer-right': '[page]/[toPage]',
        'footer-font-size': '9',
        'footer-spacing': '5',
    }

    output_pdf_path = os.path.join(tempfile.gettempdir(), uploaded_file.name.rsplit('.', 1)[0] + ".pdf")

    dprint("Iniciando conversión a PDF con wkhtmltopdf...")
    pdfkit.from_string(html_final, output_pdf_path, options=options, configuration=config)
    dprint(f"PDF generado en: {output_pdf_path}")

    return output_pdf_path

# --- INTERFAZ ---

if accion == "📸 Imágenes a PDF":
    st.header("📸 Convertir Imágenes a PDF")
    uploaded_files = st.file_uploader(
        "Sube una o varias imágenes (JPG o PNG)", 
        type=["jpg", "jpeg", "png"], 
        accept_multiple_files=True, 
        key="img_uploader"
    )
    if uploaded_files:
        if st.button("📥 Convertir a PDF"):
            with st.spinner("Generando PDF..."):
                pdf_path = convert_images_to_pdf(uploaded_files, page_size)
            with open(pdf_path, "rb") as f:
                st.success("✅ PDF creado exitosamente.")
                st.download_button("📄 Descargar PDF", f, file_name="imagenes_convertidas.pdf", mime="application/pdf")

elif accion == "📖 EPUB a PDF":
    st.header("📖 Convertir EPUB a PDF")
    epub_file = st.file_uploader(
        "Sube un archivo EPUB", 
        type=["epub"], 
        key="epub_uploader"
    )
    if epub_file:
        if st.button("📥 Convertir a PDF"):
            with st.spinner("Procesando EPUB..."):
                try:
                    pdf_path = convert_epub_to_pdf(epub_file)
                    with open(pdf_path, "rb") as f:
                        st.success("✅ PDF generado correctamente.")
                        st.download_button("📄 Descargar PDF", f, file_name=os.path.basename(pdf_path), mime="application/pdf")
                except Exception as e:
                    st.error(f"❌ Error al convertir: {e}")
