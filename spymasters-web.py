import streamlit as st
import requests
import re
import os
import sys
import pandas as pd
from urllib.parse import urlparse
import google.generativeai as genai
import time
from io import BytesIO
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

logo_path = resource_path(os.path.join("media", "spymasters.png"))
favicon_path = resource_path(os.path.join("media", "favicon.png"))
css_path = resource_path("style.css")

GOOGLE_API_KEY = st.secrets["GOOGLE_API_KEY"]
GOOGLE_CX = st.secrets["GOOGLE_CX"]
GEMINI_API_KEY = st.secrets["GEMINI_API_KEY"]

genai.configure(api_key=GEMINI_API_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

st.set_page_config(
    page_title="Spymasters Cloud",
    page_icon=favicon_path if os.path.exists(favicon_path) else "🕵️‍♂️",
    layout="centered"
)

def detect_ecommerce(html):
    if not html: return []
    html_lower = html.lower()
    
    signatures = {
        "Shopify": [r'cdn\.shopify\.com', r'shopify\.theme', r'shopify-checkout', r'myshopify\.com'],
        "Salesforce Commerce Cloud": [r'dwvar_', r'dw\.ac', r'\.demandware\.net', r'demandware\.store', r'edge\.quantity'],
        "Magento": [r'text/x-magento-init', r'mage/captcha', r'checkout/cart', r'magento_version', r'static/frontend'],
        "WooCommerce": [r'wc-cart-fragments', r'woocommerce-no-js', r'wp-content/plugins/woocommerce'],
        "PrestaShop": [r'var prestashop =', r'content=["\']prestashop["\']', r'prestashop-icon'],
        "VTEX": [r'vtexassets\.com', r'vtex-io', r'vtex\.cmc'],
        "BigCommerce": [r'cdn11\.bigcommerce\.com', r'stencil-config'],
        "Wix": [r'wix-ecommerce', r'wix-store-fixed'],
        "Squarespace": [r'squarespace-cart', r'sqs-shopping-cart', r'static\.squarespace\.com'],
        "Odoo": [r'website_sale\.cart', r'website\.assets_frontend']
    }
    
    found = []
    for platform, patterns in signatures.items():
        if any(re.search(p, html_lower) for p in patterns):
            if platform == "WooCommerce" and not any(x in html_lower for x in ['cart', 'carrito', 'basket', 'shop', 'tienda']):
                continue
            found.append(platform)
    return found

def ai_validate_results(query, search_items):
    context = "\n".join([f"{i+1}. Título: {item['title']} | Link: {item['link']} | Snippet: {item['snippet']}" for i, item in enumerate(search_items)])
    prompt = f"Analiza estos resultados para '{query}'. Busca la WEB OFICIAL DE VENTA. Responde SOLO la URL.\n{context}"
    try:
        response = model.generate_content(prompt)
        url = response.text.strip().replace("`", "").split()[0]
        return url if url.startswith('http') else search_items[0]['link']
    except: return search_items[0]['link']

def google_search(query):
    url = "https://www.googleapis.com/customsearch/v1"
    params = {'q': f"{query} tienda oficial", 'key': GOOGLE_API_KEY, 'cx': GOOGLE_CX, 'num': 5}
    try:
        response = requests.get(url, params=params)
        if response.status_code != 200: return None
        result = response.json()
        if "items" in result: return ai_validate_results(query, result['items'])
    except: return None

def get_html(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
    }
    try:
        if not url.startswith('http'): url = f"https://{url}"
        # verify=False para entrar en webs con certificados raros (Mustang)
        res = requests.get(url, headers=headers, timeout=15, verify=False)
        if res.status_code == 200:
            return res.text, res.url
        return None, url
    except Exception as e: 
        return None, url

def local_css(file_name):
    try:
        with open(file_name) as f:
            st.markdown(f'<style>{f.read()}</style>', unsafe_allow_html=True)
    except: pass

# --- 4. INTERFAZ ---
local_css(css_path)

col1, col2 = st.columns([0.25, 0.75])
with col1:
    if os.path.exists(logo_path): st.image(logo_path, width=150)
    else: st.write("🕵️‍♂️")
with col2:
    st.title("Spymasters")

tab1, tab2 = st.tabs(["🔍 Búsqueda Individual", "📁 Procesamiento Excel"])

with tab1:
    user_input = st.text_input("Nombre o URL:", placeholder="Ej: Tienda o tienda.com", key="single")
    if st.button("Investigar", key="btn_single"):
        if user_input:
            with st.spinner('Analizando...'):
                target_url = user_input if ("." in user_input and "/" in user_input) else google_search(user_input)
                
                if target_url:
                    html, final_url = get_html(target_url)
                    if html:
                        found = detect_ecommerce(html)
                        domain = urlparse(final_url).netloc
                        st.subheader(f"📊 Análisis de: {domain}")
                        if found: st.success(f"🚀 Plataforma: {found[0]}")
                        else: st.info("Plataforma no detectada.")
                    else:
                        st.warning(f"No se pudo acceder a la web: {target_url}")
                else: 
                    st.error("URL no encontrada.")

with tab2:
    st.markdown("### Subir archivo Excel")
    st.caption("El archivo debe tener las columnas: **Marca**, **URL**, **Plataforma**")
    
    uploaded_file = st.file_uploader("Elige un archivo Excel", type=["xlsx"])
    
    if uploaded_file:
        df = pd.read_excel(uploaded_file)
        df.columns = df.columns.str.strip()
        
        clean_name = os.path.splitext(uploaded_file.name)[0]
        
        for col in ['Marca', 'URL', 'Plataforma']:
            if col not in df.columns: df[col] = ""
            df[col] = df[col].astype(object)

        if st.button("Iniciar Procesamiento"):
            total_rows = len(df)
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            for i in range(total_rows):
                marca = str(df.at[i, 'Marca']) if pd.notna(df.at[i, 'Marca']) else ""
                url_val = str(df.at[i, 'URL']) if pd.notna(df.at[i, 'URL']) else ""
                plat_val = str(df.at[i, 'Plataforma']) if pd.notna(df.at[i, 'Plataforma']) else ""

                if not plat_val or plat_val == "nan":
                    label = marca if marca else (url_val if url_val else "Fila vacía")
                    status_text.markdown(f"🔎 **({i+1}/{total_rows})**: Procesando `{label}`")
                    
                    if not url_val and marca:
                        res_search = google_search(marca)
                        if res_search:
                            url_val = res_search
                            df.at[i, 'URL'] = url_val
                    
                    if url_val:
                        html, _ = get_html(url_val)
                        if html:
                            found = detect_ecommerce(html)
                            if found:
                                df.at[i, 'Plataforma'] = found[0]

                    if not marca and url_val:
                        try: df.at[i, 'Marca'] = urlparse(url_val).netloc.replace("www.","")
                        except: pass

                progress_bar.progress((i + 1) / total_rows)
            
            status_text.success(f"✅ Completado.")
            st.dataframe(df.head(10))

            output = BytesIO()
            with pd.ExcelWriter(output, engine='openpyxl') as writer:
                df.to_excel(writer, index=False)
            
            st.download_button(
                label="📥 Descargar Excel",
                data=output.getvalue(),
                file_name=f"spymasters_{clean_name}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )