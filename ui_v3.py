# ui_v3.py - Advanced Menu Carbon Calculator v3.0
# Features: Database, AI Optimization, Partner Dashboard, PDF Menu Reader
# Run: streamlit run ui_v3.py

import json
import os
import hashlib
from datetime import datetime
from io import BytesIO
from typing import Optional, Dict, List

import pandas as pd
import streamlit as st
from PIL import Image

# Load environment variables from .env file
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, use system env vars

# Get API key from environment variable only (secure method)
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Local imports
try:
    from database import (
        create_user, authenticate_user, save_recipe, get_recipes_by_user,
        save_calculation, log_analytics_event, get_partner_analytics
    )
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False

try:
    from ai_optimizer import get_optimizer, get_improvement_tips
    AI_AVAILABLE = True
except ImportError:
    AI_AVAILABLE = False

try:
    from dashboard import render_dashboard
    DASHBOARD_AVAILABLE = True
except ImportError:
    DASHBOARD_AVAILABLE = False

try:
    from pdf_reader import PDFMenuReader, render_pdf_upload_section
    PDF_READER_AVAILABLE = True
except ImportError:
    PDF_READER_AVAILABLE = False

try:
    import qrcode
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

try:
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# =============================================================================
# CONFIGURATION
# =============================================================================
APP_VERSION = "3.0.0"

ENERGY_FACTORS = {
    "electricity": {"tr": 420.0, "eu": 250.0},
    "natural_gas": {"tr": 200.0, "eu": 200.0},
    "lpg": {"tr": 230.0, "eu": 230.0},
}
TRANSPORT_FACTORS = {"road": 62.0, "rail": 22.0, "sea": 16.0, "air": 602.0}
KLIMATO_THRESHOLDS = {"A": (0, 400), "B": (400, 900), "C": (900, 1800), "D": (1800, 2600), "E": (2600, 99999)}
WRI_THRESHOLDS = {"breakfast": 3590, "lunch": 5380, "dinner": 5380}
WWF_TARGET = 500

CATEGORY_COLORS = {
    "meat": "#ef4444", "seafood": "#3b82f6", "dairy": "#f59e0b", "grain": "#d97706",
    "legume": "#22c55e", "vegetable": "#22c55e", "fruit": "#a855f7", "oil": "#eab308",
}

# =============================================================================
# DATA LOADING
# =============================================================================
@st.cache_data
def load_factors():
    df = pd.read_csv("data/factors.csv")
    df.columns = [c.strip() for c in df.columns]
    
    ef_map, name_map, cat_map, season_map = {}, {}, {}, {}
    for _, row in df.iterrows():
        ing_id = str(row["ingredient_id"]).strip().lower()
        ef_map[ing_id] = float(row["ef_gco2e_per_g"])
        name_map[ing_id] = str(row.get("ingredient_name_tr", row["ingredient_name"]))
        if "category" in df.columns and pd.notna(row.get("category")):
            cat_map[ing_id] = str(row["category"]).lower()
        if "seasonality_winter_factor" in df.columns and pd.notna(row.get("seasonality_winter_factor")):
            season_map[ing_id] = float(row["seasonality_winter_factor"])
    return ef_map, name_map, cat_map, season_map

# =============================================================================
# CALCULATION
# =============================================================================
def classify_klimato(val):
    for g, (lo, hi) in KLIMATO_THRESHOLDS.items():
        if lo <= val < hi:
            return g
    return "E"

def get_klimato_color(g):
    return {"A": "#22c55e", "B": "#84cc16", "C": "#eab308", "D": "#f97316", "E": "#ef4444"}.get(g, "#888")

def calculate(payload, ef_map, season_map, region="tr"):
    season = "winter" if datetime.now().month in [12, 1, 2] else "summer"
    
    ing_em, total_w, details = 0.0, 0.0, []
    for it in payload.get("ingredients", []):
        ing_id = str(it.get("id", "")).lower()
        w = float(it.get("raw_weight_g", 0))
        ef = ef_map.get(ing_id, 0)
        sf = season_map.get(ing_id, 1.0) if season == "winter" else 1.0
        em = w * ef * sf
        ing_em += em
        total_w += w
        details.append({"id": ing_id, "name": it.get("name", ing_id), "weight_g": w, "emission": round(em, 2)})
    
    cook = payload.get("cooking", {})
    kwh = float(cook.get("average_power_kw", 0)) * float(cook.get("duration_min", 0)) / 60
    cook_em = kwh * ENERGY_FACTORS.get(cook.get("energy_type", "electricity"), {}).get(region, 420)
    
    trans_em = 0.0
    trans = payload.get("transport", {})
    if trans.get("enabled"):
        tf = TRANSPORT_FACTORS.get(trans.get("mode", "road"), 62)
        trans_em = (total_w / 1e6) * float(trans.get("distance_km", 0)) * tf
    
    total = ing_em + cook_em + trans_em
    portions = max(1, int(payload.get("portions", 1)))
    per_p = total / portions
    grade = classify_klimato(per_p)
    wri_th = WRI_THRESHOLDS.get(payload.get("meal_type", "lunch"), 5380)
    
    return {
        "ingredient_emissions": round(ing_em, 2),
        "cooking_emissions": round(cook_em, 2),
        "transport_emissions": round(trans_em, 2),
        "total": round(total, 2),
        "per_portion": round(per_p, 2),
        "klimato": grade,
        "klimato_color": get_klimato_color(grade),
        "wri_ok": per_p <= wri_th,
        "wri_th": wri_th,
        "details": details,
        "insights": {
            "car_km": round(per_p/120, 1),  # ~120g CO2/km average car
            "tree_years": round(per_p / 21000 * 365, 1),  # 1 ağaç yılda ~21kg CO2 emer, kaç gün = emission / (21000/365)
            "trees_1year": round(per_p / 21000, 2),  # Kaç ağacın 1 yıllık absorpsiyonu
            "wwf_pct": round(per_p/WWF_TARGET*100, 0)
        }
    }

def compute_id(payload):
    s = json.dumps({"n": payload.get("name", ""), "i": sorted([i["id"] for i in payload.get("ingredients", [])])}, sort_keys=True)
    return hashlib.sha256(s.encode()).hexdigest()[:16]

def make_qr(text, size=200):
    if not QR_AVAILABLE:
        return None
    try:
        qr = qrcode.QRCode(box_size=8, border=2)
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image().convert("RGB").resize((size, size))
        buf = BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()
    except:
        return None

# =============================================================================
# MAIN APP
# =============================================================================
def main():
    st.set_page_config(page_title="Menu Carbon v3", page_icon="🌱", layout="wide")
    
    # Session state
    if "user" not in st.session_state:
        st.session_state.user = None
    if "ingredients" not in st.session_state:
        st.session_state.ingredients = [
            {"id": "beef", "raw_weight_g": 200},
            {"id": "rice", "raw_weight_g": 60},
            {"id": "onion", "raw_weight_g": 20},
        ]
    if "page" not in st.session_state:
        st.session_state.page = "calc"
    
    # Load data
    try:
        EF_MAP, NAME_MAP, CAT_MAP, SEASON_MAP = load_factors()
        ING_OPTIONS = sorted(list(EF_MAP.keys()))
    except Exception as e:
        st.error(f"Data error: {e}")
        st.stop()
    
    # Sidebar
    with st.sidebar:
        st.title("🌱 Menu Carbon v3")
        
        # Auth
        if DB_AVAILABLE:
            if st.session_state.user:
                st.success(f"👤 {st.session_state.user.get('name', st.session_state.user['email'])}")
                if st.button("🚪 Çıkış"):
                    st.session_state.user = None
                    st.rerun()
            else:
                tab = st.radio("", ["Giriş", "Kayıt"], horizontal=True)
                email = st.text_input("Email")
                pw = st.text_input("Şifre", type="password")
                if tab == "Kayıt":
                    name = st.text_input("İsim")
                    if st.button("Kayıt Ol"):
                        uid = create_user(email, pw, name)
                        if uid:
                            st.session_state.user = authenticate_user(email, pw)
                            st.rerun()
                        else:
                            st.error("Email zaten var")
                else:
                    if st.button("Giriş Yap"):
                        u = authenticate_user(email, pw)
                        if u:
                            st.session_state.user = u
                            st.rerun()
                        else:
                            st.error("Hatalı bilgi")
        
        st.divider()
        
        # Nav
        if st.button("🧮 Hesaplayıcı", use_container_width=True):
            st.session_state.page = "calc"
            st.rerun()
        if DB_AVAILABLE and st.session_state.user:
            if st.button("📋 Tariflerim", use_container_width=True):
                st.session_state.page = "recipes"
                st.rerun()
        if DASHBOARD_AVAILABLE:
            if st.button("📊 Dashboard", use_container_width=True):
                st.session_state.page = "dash"
                st.rerun()
        if AI_AVAILABLE:
            if st.button("🤖 AI Optimizer", use_container_width=True):
                st.session_state.page = "ai"
                st.rerun()
        if PDF_READER_AVAILABLE:
            if st.button("📄 PDF'den Oku", use_container_width=True):
                st.session_state.page = "pdf"
                st.rerun()
        
        st.divider()
        
        # Metodoloji
        st.subheader("📖 Metodoloji")
        st.caption("Commited Menu Carbon Methodology v2.0")
        
        methodology_path = "assets/methodology.pdf"
        if os.path.exists(methodology_path):
            with open(methodology_path, "rb") as f:
                st.download_button(
                    "📄 Metodoloji İndir (PDF)",
                    data=f,
                    file_name="methodology.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
        
        with st.expander("ℹ️ Hakkında"):
            st.markdown("""
            **Veri Kaynakları:**
            - Poore & Nemecek (2018)
            - Agribalyse 3.1
            - Ecoinvent
            
            **Sınıflandırma:**
            - A: < 400g CO₂e (Çok Düşük)
            - B: 400-900g (Düşük)
            - C: 900-1800g (Orta)
            - D: 1800-2600g (Yüksek)
            - E: > 2600g (Çok Yüksek)
            
            **Hedefler:**
            - WWF: 500g/öğün
            - WRI Cool Food: 5380g/öğün
            """)
        
        st.divider()
        st.caption(f"v{APP_VERSION}")
    
    # Pages
    if st.session_state.page == "dash" and DASHBOARD_AVAILABLE:
        render_dashboard()
        return
    
    if st.session_state.page == "recipes" and DB_AVAILABLE and st.session_state.user:
        st.title("📋 Tariflerim")
        recipes = get_recipes_by_user(st.session_state.user["id"])
        if recipes:
            for r in recipes:
                with st.expander(f"{r['name']} - {r.get('klimato_grade', '?')} ({r.get('gco2e_per_portion', 0):.0f}g)"):
                    st.write(f"Oluşturulma: {r.get('created_at', '')[:10]}")
                    st.json(r.get("ingredients", []))
        else:
            st.info("Henüz tarif yok")
        return
    
    if st.session_state.page == "ai" and AI_AVAILABLE:
        st.title("🤖 AI Tarif Optimizer")
        
        # API key from environment variable (not from UI for security)
        if ANTHROPIC_API_KEY:
            opt = get_optimizer(ANTHROPIC_API_KEY)
            if opt.is_available():
                st.success("✅ AI hazır (API key .env'den yüklendi)")
                
                st.subheader("Mevcut Tarif")
                cur_em = 0
                for ing in st.session_state.ingredients:
                    em = ing.get("raw_weight_g", 0) * EF_MAP.get(ing.get("id", ""), 0)
                    cur_em += em
                    st.write(f"- {NAME_MAP.get(ing['id'], ing['id'])}: {ing['raw_weight_g']}g ({em:.0f}g CO₂e)")
                
                st.metric("Toplam", f"{cur_em:.0f}g CO₂e")
                
                if st.button("🚀 Optimize Et", type="primary"):
                    with st.spinner("AI analiz ediyor..."):
                        ings = [{"id": i["id"], "name": NAME_MAP.get(i["id"], i["id"]), 
                                "raw_weight_g": i["raw_weight_g"], "emission_factor_g_per_g": EF_MAP.get(i["id"], 0)} 
                               for i in st.session_state.ingredients]
                        res = opt.optimize_recipe("Tarif", ings, cur_em, EF_MAP, NAME_MAP)
                        
                        if res.success:
                            st.success(f"✅ %{res.reduction_percent:.0f} azalma!")
                            c1, c2 = st.columns(2)
                            c1.metric("Önceki", f"{res.original_emission:.0f}g")
                            c2.metric("Sonraki", f"{res.optimized_emission:.0f}g", delta=f"-{res.reduction_percent:.0f}%")
                            
                            st.subheader("Öneriler")
                            for s in res.suggestions:
                                st.info(f"**{s.get('type', '')}**: {s.get('original_ingredient', '')} → {s.get('new_ingredient', '')} - {s.get('explanation', '')}")
                            
                            if st.button("✅ Uygula"):
                                st.session_state.ingredients = [{"id": i["id"], "raw_weight_g": i["raw_weight_g"]} for i in res.optimized_ingredients]
                                st.session_state.page = "calc"
                                st.rerun()
                        else:
                            st.error(res.explanation)
            else:
                st.error("API key geçersiz. .env dosyasını kontrol edin.")
        else:
            st.warning("⚠️ API key bulunamadı")
            st.markdown("""
            **API key ayarlamak için:**
            
            1. `.env.example` dosyasını `.env` olarak kopyalayın:
            ```bash
            cp .env.example .env
            ```
            
            2. `.env` dosyasını açıp API key'inizi girin:
            ```
            ANTHROPIC_API_KEY=sk-ant-xxxxx
            ```
            
            3. Uygulamayı yeniden başlatın
            
            💡 Bu yöntem API key'inizi güvende tutar ve GitHub'a yüklenmesini önler.
            """)
            
            st.divider()
            st.subheader("⚡ Hızlı Öneriler (AI gerektirmez)")
            
            ings = [{"id": i["id"], "name": NAME_MAP.get(i["id"], i["id"]), 
                    "raw_weight_g": i["raw_weight_g"], "emission_factor_g_per_g": EF_MAP.get(i["id"], 0)} 
                   for i in st.session_state.ingredients]
            tips = get_optimizer().get_quick_suggestions(ings, EF_MAP, NAME_MAP)
            for t in tips:
                st.success(f"💡 {t['original_ingredient']} → {t['new_ingredient']}: {t['description']} (-{t['emission_saved_g']:.0f}g)")
        return
    
    # PDF Reader page
    if st.session_state.page == "pdf" and PDF_READER_AVAILABLE:
        st.title("📄 PDF / Görsel'den Tarif Oku")
        st.caption("PDF, fotoğraf veya ekran görüntüsü yükleyerek tarifleri otomatik çıkarın")
        
        reader = PDFMenuReader()
        
        # File upload - support all formats
        uploaded_file = st.file_uploader(
            "📎 Dosya Yükle", 
            type=["pdf", "png", "jpg", "jpeg", "webp", "heic"],
            help="PDF, fotoğraf veya ekran görüntüsü yükleyin"
        )
        
        # Vision option (uses API key from .env)
        use_vision = False
        if ANTHROPIC_API_KEY:
            use_vision = st.checkbox("🤖 Claude Vision kullan (daha doğru)", value=True, 
                                    help="API key .env dosyasından yüklendi")
        else:
            st.info("💡 Daha doğru sonuç için `.env` dosyasına API key ekleyin")
        
        if uploaded_file:
            file_type = uploaded_file.type
            file_bytes = uploaded_file.read()
            
            with st.spinner("🔍 Dosya okunuyor..."):
                try:
                    text_content = ""
                    recipes = []
                    
                    # PDF file
                    if "pdf" in file_type:
                        text_content = reader.extract_text_from_pdf(file_bytes)
                        if text_content:
                            recipes = reader.parse_recipes_from_text(text_content)
                        else:
                            st.warning("PDF'den metin çıkarılamadı. Görsel tabanlı PDF olabilir.")
                    
                    # Image file
                    elif "image" in file_type or file_type in ["image/png", "image/jpeg", "image/webp"]:
                        # Show uploaded image
                        st.image(file_bytes, caption="Yüklenen Görsel", width=400)
                        
                        if use_vision and ANTHROPIC_API_KEY:
                            # Use Claude Vision
                            reader_with_api = PDFMenuReader(ANTHROPIC_API_KEY)
                            result = reader_with_api.extract_text_from_image_vision(file_bytes)
                            
                            if "error" in result and result["error"]:
                                st.error(f"Vision hatası: {result['error']}")
                            else:
                                text_content = result.get("text", "")
                                recipes = result.get("recipes", [])
                        else:
                            # Try OCR (free, no API)
                            try:
                                text_content = reader.extract_text_from_image_ocr(file_bytes)
                                if text_content:
                                    recipes = reader.parse_recipes_from_text(text_content)
                            except Exception as ocr_error:
                                st.warning(f"OCR kullanılamıyor: {ocr_error}")
                                st.info("💡 Daha iyi sonuç için `.env` dosyasına API key ekleyin veya `pip install pytesseract` ile Tesseract kurun")
                    
                    # Show extracted text
                    if text_content:
                        with st.expander("📝 Çıkarılan Metin", expanded=False):
                            st.text(text_content[:2000] + "..." if len(text_content) > 2000 else text_content)
                    
                    # Process recipes
                    if recipes:
                        st.success(f"✅ {len(recipes)} tarif bulundu!")
                        
                        # Match to database
                        matched = reader.match_ingredients_to_database(recipes, EF_MAP, NAME_MAP)
                        
                        # Recipe selector
                        recipe_names = [f"{r['name']} ({len(r['ingredients'])} malzeme)" for r in matched]
                        sel_idx = st.selectbox("Tarif seçin", range(len(recipe_names)), 
                                              format_func=lambda i: recipe_names[i])
                        
                        selected = matched[sel_idx]
                        
                        st.subheader(f"📋 {selected['name']}")
                        
                        # Show matched ingredients
                        if selected["ingredients"]:
                            st.write("**✅ Eşleşen Malzemeler:**")
                            for ing in selected["ingredients"]:
                                ef = ing.get("emission_factor", 0)
                                st.write(f"- {ing['name']}: {ing['raw_weight_g']}g (EF: {ef:.2f})")
                        else:
                            st.warning("Veritabanıyla eşleşen malzeme bulunamadı")
                        
                        # Show unmatched
                        if selected.get("unmatched_ingredients"):
                            with st.expander(f"⚠️ Eşleşmeyen ({len(selected['unmatched_ingredients'])})"):
                                for ing in selected["unmatched_ingredients"]:
                                    st.write(f"- {ing['name']}: {ing['amount_g']}g")
                        
                        # Use recipe button
                        if selected["ingredients"] and st.button("✅ Bu Tarifi Kullan", type="primary", use_container_width=True):
                            st.session_state.ingredients = [
                                {"id": ing["id"], "raw_weight_g": ing["raw_weight_g"], "name": ing["name"]}
                                for ing in selected["ingredients"]
                            ]
                            st.session_state.recipe_name = selected["name"]
                            st.session_state.page = "calc"
                            st.rerun()
                    
                    elif text_content:
                        st.warning("Tarif formatı algılanamadı. Metin çıkarıldı ama yapılandırılmış tarif bulunamadı.")
                        st.info("💡 İpucu: Claude Vision API ile daha iyi sonuç alabilirsiniz")
                    
                    else:
                        st.error("Dosyadan içerik çıkarılamadı.")
                        
                except Exception as e:
                    st.error(f"Hata: {str(e)}")
                    import traceback
                    with st.expander("Hata Detayı"):
                        st.code(traceback.format_exc())
        
        # Help section
        with st.expander("❓ Nasıl Kullanılır"):
            st.markdown("""
            **Desteklenen Formatlar:**
            - 📄 PDF dosyaları
            - 📷 Fotoğraflar (JPG, PNG, WebP)
            - 📱 Telefon fotoğrafları
            - 🖥️ Ekran görüntüleri
            
            **En İyi Sonuç İçin:**
            - Metin net ve okunabilir olmalı
            - Malzeme miktarları (gr, kg, adet vb.) belirtilmiş olmalı
            - Claude Vision API ile daha doğru sonuç alırsınız
            
            **OCR Kurulumu (Opsiyonel):**
            ```bash
            # macOS
            brew install tesseract tesseract-lang
            pip install pytesseract
            
            # Ubuntu
            sudo apt install tesseract-ocr tesseract-ocr-tur
            pip install pytesseract
            ```
            """)
        
        return
    
    # Calculator (default)
    st.title("🌱 Menü Karbon Hesaplayıcı v3")
    
    c1, c2, c3 = st.columns([2, 1, 1])
    default_name = st.session_state.get("recipe_name", "Izgara Köfte + Pilav")
    recipe_name = c1.text_input("Tarif", default_name)
    portions = c2.number_input("Porsiyon", 1, 100, 1)
    meal_type = c3.selectbox("Öğün", ["breakfast", "lunch", "dinner"], 1, format_func=lambda x: {"breakfast": "☀️ Kahvaltı", "lunch": "🌤️ Öğle", "dinner": "🌙 Akşam"}[x])
    
    st.divider()
    st.subheader("🥗 Malzemeler")
    
    for i, ing in enumerate(st.session_state.ingredients):
        c1, c2, c3 = st.columns([2, 1, 1])
        cur_id = ing.get("id", ING_OPTIONS[0])
        if cur_id not in ING_OPTIONS:
            cur_id = ING_OPTIONS[0]
        
        sel = c1.selectbox(f"#{i+1}", ING_OPTIONS, ING_OPTIONS.index(cur_id), key=f"i{i}",
                          format_func=lambda x: f"{NAME_MAP.get(x, x)} ({EF_MAP.get(x, 0):.1f})")
        ing["id"] = sel
        ing["raw_weight_g"] = c2.number_input("g", 0.0, 5000.0, float(ing.get("raw_weight_g", 0)), 10.0, key=f"w{i}")
        ing["name"] = NAME_MAP.get(sel, sel)
        
        cat = CAT_MAP.get(sel, "other")
        col = CATEGORY_COLORS.get(cat, "#888")
        c3.markdown(f'<span style="background:{col};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{cat}</span>', unsafe_allow_html=True)
    
    c1, c2 = st.columns(2)
    if c1.button("➕ Ekle"):
        st.session_state.ingredients.append({"id": ING_OPTIONS[0], "raw_weight_g": 0})
        st.rerun()
    if c2.button("🗑️ Sil") and len(st.session_state.ingredients) > 1:
        st.session_state.ingredients.pop()
        st.rerun()
    
    st.divider()
    st.subheader("🍳 Pişirme")
    c1, c2, c3 = st.columns(3)
    energy = c1.selectbox("Enerji", list(ENERGY_FACTORS.keys()), format_func=lambda x: {"electricity": "⚡ Elektrik", "natural_gas": "🔥 Doğalgaz", "lpg": "🔵 LPG"}[x])
    power = c2.number_input("kW", 0.0, 20.0, 3.0, 0.5)
    dur = c3.number_input("dk", 0.0, 240.0, 12.0, 1.0)
    
    st.subheader("🚛 Taşıma")
    trans_on = st.checkbox("Dahil et", True)
    if trans_on:
        c1, c2 = st.columns(2)
        trans_mode = c1.selectbox("Mod", list(TRANSPORT_FACTORS.keys()), format_func=lambda x: {"road": "🚛 Kara", "rail": "🚂 Tren", "sea": "🚢 Deniz", "air": "✈️ Hava"}[x])
        trans_km = c2.number_input("km", 0.0, 20000.0, 300.0, 50.0)
    else:
        trans_mode, trans_km = "road", 0
    
    st.divider()
    
    payload = {
        "name": recipe_name, "portions": portions, "meal_type": meal_type,
        "ingredients": st.session_state.ingredients,
        "cooking": {"energy_type": energy, "average_power_kw": power, "duration_min": dur},
        "transport": {"enabled": trans_on, "mode": trans_mode, "distance_km": trans_km}
    }
    
    if st.button("🧮 HESAPLA", type="primary", use_container_width=True):
        res = calculate(payload, EF_MAP, SEASON_MAP)
        mid = compute_id(payload)
        
        if DB_AVAILABLE:
            uid = st.session_state.user["id"] if st.session_state.user else None
            save_calculation(payload, res, user_id=uid)
        
        st.success("✅ Hesaplandı!")
        
        # Results
        st.subheader("📊 Sonuçlar")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Malzeme", f"{res['ingredient_emissions']:.0f}g")
        c2.metric("Pişirme", f"{res['cooking_emissions']:.0f}g")
        c3.metric("Taşıma", f"{res['transport_emissions']:.0f}g")
        c4.metric("TOPLAM", f"{res['per_portion']:.0f}g/porsiyon")
        
        # Klimato badge
        g, col = res["klimato"], res["klimato_color"]
        st.markdown(f"""
        <div style="text-align:center;padding:20px;background:linear-gradient(135deg,{col}22,{col}44);border-radius:16px;border:3px solid {col};margin:20px 0">
            <div style="font-size:64px;font-weight:bold;color:{col}">{g}</div>
            <div style="font-size:16px;color:#374151">Carbon Grade</div>
        </div>
        """, unsafe_allow_html=True)
        
        if res["wri_ok"]:
            st.success("✅ WRI Cool Food Certified")
        else:
            st.warning(f"❌ WRI sınırı aşıldı ({res['per_portion']:.0f}g > {res['wri_th']}g)")
        
        # Insights
        st.subheader("🌍 Karşılaştırma")
        c1, c2, c3 = st.columns(3)
        c1.metric("🚗 Araba", f"{res['insights']['car_km']:.1f} km")
        c2.metric("🌳 1 Ağaç", f"{res['insights']['tree_years']:.0f} gün", help="1 ağacın bu emisyonu temizlemesi için gereken süre")
        c3.metric("🎯 WWF", f"%{res['insights']['wwf_pct']:.0f}")
        
        # Tips
        if AI_AVAILABLE:
            tips = get_improvement_tips(g, "tr")
            if tips:
                st.subheader("💡 İpuçları")
                for t in tips:
                    st.info(t)
        
        # Charts
        if PLOTLY_AVAILABLE:
            c1, c2 = st.columns(2)
            with c1:
                fig = go.Figure(data=[go.Pie(labels=["Malzeme", "Pişirme", "Taşıma"], values=[res["ingredient_emissions"], res["cooking_emissions"], res["transport_emissions"]], hole=0.4, marker_colors=["#22c55e", "#3b82f6", "#f59e0b"])])
                fig.update_layout(height=300, margin=dict(t=20, b=20))
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                d = res["details"]
                fig = go.Figure(data=[go.Bar(y=[x["name"] for x in d], x=[x["emission"] for x in d], orientation='h', marker_color=[CATEGORY_COLORS.get(CAT_MAP.get(x["id"], ""), "#888") for x in d])])
                fig.update_layout(height=300, margin=dict(t=20, b=20, l=100), yaxis=dict(autorange="reversed"))
                st.plotly_chart(fig, use_container_width=True)
        
        # Save
        if DB_AVAILABLE and st.session_state.user:
            if st.button("💾 Kaydet"):
                rid = save_recipe(mid, recipe_name, st.session_state.ingredients, payload["cooking"], payload["transport"], {"klimato_grade": g, "gco2e_per_portion": res["per_portion"], "wri_compliant": res["wri_ok"]}, user_id=st.session_state.user["id"])
                st.success(f"✅ Kaydedildi! (ID: {mid})")
        
        # Export
        st.divider()
        c1, c2 = st.columns(2)
        c1.download_button("⬇️ JSON", json.dumps({"id": mid, "payload": payload, "result": res}, indent=2, default=str), "recipe.json")
        if QR_AVAILABLE:
            qr = make_qr(f"https://carbonkey.app/{mid}")
            if qr:
                c2.download_button("📱 QR", qr, "qr.png", "image/png")

if __name__ == "__main__":
    main()
