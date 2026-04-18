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
    pass

ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

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
    "meat": "#ef4444", "seafood": "#3b82f6", "dairy": "#f59e0b",
    "grain": "#d97706", "legume": "#22c55e", "vegetable": "#22c55e",
    "fruit": "#a855f7", "oil": "#eab308",
}


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
            "car_km": round(per_p / 120, 1),
            "tree_years": round(per_p / 21000 * 365, 1),
            "trees_1year": round(per_p / 21000, 2),
            "wwf_pct": round(per_p / WWF_TARGET * 100, 0),
        },
    }


def compute_id(payload):
    s = json.dumps(
        {"n": payload.get("name", ""), "i": sorted([i["id"] for i in payload.get("ingredients", [])])},
        sort_keys=True,
    )
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
    except Exception:
        return None


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
    if "last_result" not in st.session_state:
        st.session_state.last_result = None
    if "last_mid" not in st.session_state:
        st.session_state.last_mid = None
    if "last_payload" not in st.session_state:
        st.session_state.last_payload = None
    if "recipe_saved" not in st.session_state:
        st.session_state.recipe_saved = False

    # Data
    try:
        EF_MAP, NAME_MAP, CAT_MAP, SEASON_MAP = load_factors()
        ING_OPTIONS = sorted(list(EF_MAP.keys()))
    except Exception as e:
        st.error(f"Data error: {e}")
        st.stop()

    # Sidebar
    with st.sidebar:
        st.title("🌱 Menu Carbon v3")

        if DB_AVAILABLE:
            if st.session_state.user:
                st.success(f"👤 {st.session_state.user.get('name', st.session_state.user['email'])}")
                if st.button("🚪 Cikis"):
                    st.session_state.user = None
                    st.rerun()
            else:
                tab = st.radio("", ["Giris", "Kayit"], horizontal=True)
                email = st.text_input("Email")
                pw = st.text_input("Sifre", type="password")
                if tab == "Kayit":
                    name = st.text_input("Isim")
                    if st.button("Kayit Ol"):
                        uid = create_user(email, pw, name)
                        if uid:
                            st.session_state.user = authenticate_user(email, pw)
                            st.rerun()
                        else:
                            st.error("Email zaten var")
                else:
                    if st.button("Giris Yap"):
                        u = authenticate_user(email, pw)
                        if u:
                            st.session_state.user = u
                            st.rerun()
                        else:
                            st.error("Hatali bilgi")

        st.divider()

        if st.button("🧮 Hesaplayici", use_container_width=True):
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
        st.subheader("📖 Metodoloji")
        st.caption("Commited Menu Carbon Methodology v2.0")
        methodology_path = "assets/methodology.pdf"
        if os.path.exists(methodology_path):
            with open(methodology_path, "rb") as f:
                st.download_button("📄 Metodoloji Indir", data=f, file_name="methodology.pdf",
                                   mime="application/pdf", use_container_width=True)
        with st.expander("ℹ️ Hakkinda"):
            st.markdown("""
**Veri Kaynaklari:** Poore & Nemecek (2018), Agribalyse 3.1, Ecoinvent

**Siniflandirma:**
- A: < 400g CO2e (Cok Dusuk)
- B: 400-900g (Dusuk)
- C: 900-1800g (Orta)
- D: 1800-2600g (Yuksek)
- E: > 2600g (Cok Yuksek)

**Hedefler:** WWF 500g/ogun | WRI Cool Food 5380g/ogun
""")
        st.divider()
        st.caption(f"v{APP_VERSION}")

    # Page routing
    if st.session_state.page == "dash" and DASHBOARD_AVAILABLE:
        render_dashboard()
        return

    if st.session_state.page == "recipes" and DB_AVAILABLE and st.session_state.user:
        st.title("📋 Tariflerim")
        recipes = get_recipes_by_user(st.session_state.user["id"])
        if recipes:
            for r in recipes:
                with st.expander(
                    f"{r['name']} - {r.get('klimato_grade', '?')} ({r.get('gco2e_per_portion', 0):.0f}g)"
                ):
                    st.write(f"Olusturulma: {r.get('created_at', '')[:10]}")
                    st.json(r.get("ingredients", []))
        else:
            st.info("Henuz tarif yok. Hesaplayicidan bir tarif hesaplayip 'Tarifi Kaydet' butonuna basin.")
        return

    if st.session_state.page == "ai" and AI_AVAILABLE:
        st.title("🤖 AI Tarif Optimizer")
        if ANTHROPIC_API_KEY:
            opt = get_optimizer(ANTHROPIC_API_KEY)
            if opt.is_available():
                st.success("AI hazir")
                cur_em = sum(
                    ing.get("raw_weight_g", 0) * EF_MAP.get(ing.get("id", ""), 0)
                    for ing in st.session_state.ingredients
                )
                for ing in st.session_state.ingredients:
                    em = ing.get("raw_weight_g", 0) * EF_MAP.get(ing.get("id", ""), 0)
                    st.write(f"- {NAME_MAP.get(ing['id'], ing['id'])}: {ing['raw_weight_g']}g ({em:.0f}g CO2e)")
                st.metric("Toplam", f"{cur_em:.0f}g CO2e")
                if st.button("Optimize Et", type="primary"):
                    with st.spinner("AI analiz ediyor..."):
                        ings = [
                            {"id": i["id"], "name": NAME_MAP.get(i["id"], i["id"]),
                             "raw_weight_g": i["raw_weight_g"], "emission_factor_g_per_g": EF_MAP.get(i["id"], 0)}
                            for i in st.session_state.ingredients
                        ]
                        res = opt.optimize_recipe("Tarif", ings, cur_em, EF_MAP, NAME_MAP)
                        if res.success:
                            st.success(f"%{res.reduction_percent:.0f} azalma!")
                            c1, c2 = st.columns(2)
                            c1.metric("Onceki", f"{res.original_emission:.0f}g")
                            c2.metric("Sonraki", f"{res.optimized_emission:.0f}g", delta=f"-{res.reduction_percent:.0f}%")
                            for s in res.suggestions:
                                st.info(f"**{s.get('type','')}**: {s.get('original_ingredient','')} -> {s.get('new_ingredient','')} - {s.get('explanation','')}")
                            if st.button("Uygula"):
                                st.session_state.ingredients = [
                                    {"id": i["id"], "raw_weight_g": i["raw_weight_g"]}
                                    for i in res.optimized_ingredients
                                ]
                                st.session_state.page = "calc"
                                st.rerun()
                        else:
                            st.error(res.explanation)
            else:
                st.error("API key gecersiz.")
        else:
            st.warning("API key bulunamadi. .env dosyasina ANTHROPIC_API_KEY ekleyin.")
        st.divider()
        if AI_AVAILABLE:
            st.subheader("Hizli Oneriler (AI gerektirmez)")
            ings2 = [
                {"id": i["id"], "name": NAME_MAP.get(i["id"], i["id"]),
                 "raw_weight_g": i["raw_weight_g"], "emission_factor_g_per_g": EF_MAP.get(i["id"], 0)}
                for i in st.session_state.ingredients
            ]
            tips = get_optimizer().get_quick_suggestions(ings2, EF_MAP, NAME_MAP)
            for tip in tips:
                st.success(f"💡 {tip['original_ingredient']} -> {tip['new_ingredient']}: {tip['description']} (-{tip['emission_saved_g']:.0f}g)")
        return

    if st.session_state.page == "pdf" and PDF_READER_AVAILABLE:
        st.title("📄 PDF / Gorsel'den Tarif Oku")
        reader = PDFMenuReader()
        uploaded_file = st.file_uploader("Dosya Yukle", type=["pdf", "png", "jpg", "jpeg", "webp"])
        use_vision = bool(ANTHROPIC_API_KEY) and st.checkbox("Claude Vision kullan", value=True)
        if uploaded_file:
            file_bytes = uploaded_file.read()
            file_type = uploaded_file.type
            with st.spinner("Okunuyor..."):
                try:
                    text_content, recipes = "", []
                    if "pdf" in file_type:
                        text_content = reader.extract_text_from_pdf(file_bytes)
                        if text_content:
                            recipes = reader.parse_recipes_from_text(text_content)
                    else:
                        st.image(file_bytes, width=400)
                        if use_vision and ANTHROPIC_API_KEY:
                            r2 = PDFMenuReader(ANTHROPIC_API_KEY)
                            result = r2.extract_text_from_image_vision(file_bytes)
                            text_content = result.get("text", "")
                            recipes = result.get("recipes", [])
                        else:
                            try:
                                text_content = reader.extract_text_from_image_ocr(file_bytes)
                                if text_content:
                                    recipes = reader.parse_recipes_from_text(text_content)
                            except Exception as ocr_err:
                                st.warning(f"OCR kullanilamiyor: {ocr_err}")
                    if recipes:
                        st.success(f"{len(recipes)} tarif bulundu!")
                        matched = reader.match_ingredients_to_database(recipes, EF_MAP, NAME_MAP)
                        names = [f"{r['name']} ({len(r['ingredients'])} malzeme)" for r in matched]
                        idx = st.selectbox("Tarif", range(len(names)), format_func=lambda i: names[i])
                        sel = matched[idx]
                        if sel["ingredients"] and st.button("Bu Tarifi Kullan", type="primary"):
                            st.session_state.ingredients = [
                                {"id": i["id"], "raw_weight_g": i["raw_weight_g"], "name": i["name"]}
                                for i in sel["ingredients"]
                            ]
                            st.session_state.page = "calc"
                            st.rerun()
                    else:
                        st.warning("Tarif bulunamadi.")
                except Exception as e:
                    st.error(f"Hata: {e}")
        return

    # ==========================================================================
    # CALCULATOR PAGE (default)
    # ==========================================================================
    st.title("🌱 Menu Karbon Hesaplayici v3")

    c1, c2, c3 = st.columns([2, 1, 1])
    recipe_name = c1.text_input("Tarif", st.session_state.get("recipe_name", "Izgara Koefte + Pilav"))
    portions = c2.number_input("Porsiyon", 1, 100, 1)
    meal_type = c3.selectbox(
        "Ogun", ["breakfast", "lunch", "dinner"], 1,
        format_func=lambda x: {"breakfast": "Kahvalti", "lunch": "Ogle", "dinner": "Aksam"}[x],
    )

    st.divider()
    st.subheader("Malzemeler")
    for i, ing in enumerate(st.session_state.ingredients):
        c1, c2, c3 = st.columns([2, 1, 1])
        cur_id = ing.get("id", ING_OPTIONS[0])
        if cur_id not in ING_OPTIONS:
            cur_id = ING_OPTIONS[0]
        sel = c1.selectbox(
            f"#{i + 1}", ING_OPTIONS, ING_OPTIONS.index(cur_id), key=f"i{i}",
            format_func=lambda x: f"{NAME_MAP.get(x, x)} ({EF_MAP.get(x, 0):.1f})",
        )
        ing["id"] = sel
        ing["raw_weight_g"] = c2.number_input("g", 0.0, 5000.0, float(ing.get("raw_weight_g", 0)), 10.0, key=f"w{i}")
        ing["name"] = NAME_MAP.get(sel, sel)
        cat = CAT_MAP.get(sel, "other")
        col = CATEGORY_COLORS.get(cat, "#888")
        c3.markdown(
            f'<span style="background:{col};color:#fff;padding:2px 8px;border-radius:4px;font-size:11px">{cat}</span>',
            unsafe_allow_html=True,
        )

    c1, c2 = st.columns(2)
    if c1.button("Ekle"):
        st.session_state.ingredients.append({"id": ING_OPTIONS[0], "raw_weight_g": 0})
        st.rerun()
    if c2.button("Sil") and len(st.session_state.ingredients) > 1:
        st.session_state.ingredients.pop()
        st.rerun()

    st.divider()
    st.subheader("Pisirme")
    c1, c2, c3 = st.columns(3)
    energy = c1.selectbox(
        "Enerji", list(ENERGY_FACTORS.keys()),
        format_func=lambda x: {"electricity": "Elektrik", "natural_gas": "Dogalgaz", "lpg": "LPG"}[x],
    )
    power = c2.number_input("kW", 0.0, 20.0, 3.0, 0.5)
    dur = c3.number_input("dk", 0.0, 240.0, 12.0, 1.0)

    st.subheader("Tasima")
    trans_on = st.checkbox("Dahil et", True)
    if trans_on:
        c1, c2 = st.columns(2)
        trans_mode = c1.selectbox(
            "Mod", list(TRANSPORT_FACTORS.keys()),
            format_func=lambda x: {"road": "Kara", "rail": "Tren", "sea": "Deniz", "air": "Hava"}[x],
        )
        trans_km = c2.number_input("km", 0.0, 20000.0, 300.0, 50.0)
    else:
        trans_mode, trans_km = "road", 0

    st.divider()

    payload = {
        "name": recipe_name,
        "portions": portions,
        "meal_type": meal_type,
        "ingredients": st.session_state.ingredients,
        "cooking": {"energy_type": energy, "average_power_kw": power, "duration_min": dur},
        "transport": {"enabled": trans_on, "mode": trans_mode, "distance_km": trans_km},
    }

    # HESAPLA
    if st.button("HESAPLA", type="primary", use_container_width=True):
        res = calculate(payload, EF_MAP, SEASON_MAP)
        mid = compute_id(payload)
        st.session_state.last_result = res
        st.session_state.last_mid = mid
        st.session_state.last_payload = payload
        st.session_state.recipe_saved = False  # reset save state on new calculation
        if DB_AVAILABLE:
            uid = st.session_state.user["id"] if st.session_state.user else None
            save_calculation(payload, res, user_id=uid)
        st.success("Hesaplandi!")

    # RESULTS
    if st.session_state.last_result is not None:
        res = st.session_state.last_result
        mid = st.session_state.last_mid

        st.subheader("Sonuclar")
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Malzeme", f"{res['ingredient_emissions']:.0f}g")
        c2.metric("Pisirme", f"{res['cooking_emissions']:.0f}g")
        c3.metric("Tasima", f"{res['transport_emissions']:.0f}g")
        c4.metric("TOPLAM", f"{res['per_portion']:.0f}g/porsiyon")

        g, col = res["klimato"], res["klimato_color"]
        st.markdown(
            f'<div style="text-align:center;padding:20px;background:linear-gradient(135deg,{col}22,{col}44);'
            f'border-radius:16px;border:3px solid {col};margin:20px 0">'
            f'<div style="font-size:64px;font-weight:bold;color:{col}">{g}</div>'
            f'<div style="font-size:16px;color:#374151">Carbon Grade</div></div>',
            unsafe_allow_html=True,
        )

        if res["wri_ok"]:
            st.success("WRI Cool Food Certified")
        else:
            st.warning(f"WRI siniri asildi ({res['per_portion']:.0f}g > {res['wri_th']}g)")

        st.subheader("Karsilastirma")
        c1, c2, c3 = st.columns(3)
        c1.metric("Araba", f"{res['insights']['car_km']:.1f} km")
        c2.metric("1 Agac", f"{res['insights']['tree_years']:.0f} gun",
                  help="1 agacin bu emisyonu temizlemesi icin gereken sure")
        c3.metric("WWF", f"%{res['insights']['wwf_pct']:.0f}")

        if AI_AVAILABLE:
            tips = get_improvement_tips(g, "tr")
            if tips:
                st.subheader("Ipuclari")
                for tip in tips:
                    st.info(tip)

        if PLOTLY_AVAILABLE:
            c1, c2 = st.columns(2)
            with c1:
                fig = go.Figure(data=[go.Pie(
                    labels=["Malzeme", "Pisirme", "Tasima"],
                    values=[res["ingredient_emissions"], res["cooking_emissions"], res["transport_emissions"]],
                    hole=0.4, marker_colors=["#22c55e", "#3b82f6", "#f59e0b"],
                )])
                fig.update_layout(height=300, margin=dict(t=20, b=20))
                st.plotly_chart(fig, use_container_width=True)
            with c2:
                d = res["details"]
                fig = go.Figure(data=[go.Bar(
                    y=[x["name"] for x in d], x=[x["emission"] for x in d], orientation="h",
                    marker_color=[CATEGORY_COLORS.get(CAT_MAP.get(x["id"], ""), "#888") for x in d],
                )])
                fig.update_layout(height=300, margin=dict(t=20, b=20, l=100), yaxis=dict(autorange="reversed"))
                st.plotly_chart(fig, use_container_width=True)

        # ══════════════════════════════════════════════════════════════════════
        # KAYDET BOLUMU — goze carpan tasarim
        # ══════════════════════════════════════════════════════════════════════
        st.markdown("<br>", unsafe_allow_html=True)

        if DB_AVAILABLE and st.session_state.user:
            sp = st.session_state.last_payload
            sr = st.session_state.last_result
            sm = st.session_state.last_mid

            if st.session_state.recipe_saved:
                # Kaydedildikten sonra gosterilen onay banner
                st.markdown(
                    f"""
                    <div style="
                        background: linear-gradient(135deg, #065f46, #047857);
                        border-radius: 16px;
                        padding: 24px 32px;
                        display: flex;
                        align-items: center;
                        gap: 16px;
                        margin: 8px 0 24px 0;
                        box-shadow: 0 4px 20px rgba(4,120,87,0.35);
                    ">
                        <span style="font-size:40px;">✅</span>
                        <div>
                            <div style="color:#d1fae5;font-size:13px;font-weight:600;letter-spacing:1px;text-transform:uppercase;">Kaydedildi</div>
                            <div style="color:#ffffff;font-size:20px;font-weight:700;margin-top:2px;">"{sp['name']}" Tariflerim'e eklendi</div>
                            <div style="color:#a7f3d0;font-size:12px;margin-top:4px;">ID: {sm}</div>
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )
            else:
                # Kaydet butonu — buyuk, cekici tasarim
                st.markdown(
                    """
                    <div style="
                        background: linear-gradient(135deg, #1e3a5f, #1d4ed8);
                        border-radius: 16px;
                        padding: 24px 32px;
                        margin: 8px 0 16px 0;
                        box-shadow: 0 4px 20px rgba(29,78,216,0.35);
                        border: 1px solid rgba(255,255,255,0.1);
                    ">
                        <div style="display:flex;align-items:center;gap:14px;margin-bottom:14px;">
                            <span style="font-size:36px;">💾</span>
                            <div>
                                <div style="color:#bfdbfe;font-size:12px;font-weight:600;letter-spacing:1px;text-transform:uppercase;">Tarifi kaydet</div>
                                <div style="color:#ffffff;font-size:18px;font-weight:700;margin-top:1px;">Hesaplanan sonucu Tariflerim'e ekle</div>
                            </div>
                        </div>
                        <div style="color:#93c5fd;font-size:13px;margin-bottom:4px;">
                            Tarifi kaydederek daha sonra <b style="color:#fff;">Tariflerim</b> sayfasinda inceleyebilirsiniz.
                        </div>
                    </div>
                    """,
                    unsafe_allow_html=True,
                )

                # CSS ile butonun kendisini de buyutelim
                st.markdown(
                    """
                    <style>
                    div[data-testid="stButton"]:has(button[kind="primary"]#save_btn) button {
                        font-size: 18px !important;
                        padding: 14px 0 !important;
                        font-weight: 700 !important;
                    }
                    </style>
                    """,
                    unsafe_allow_html=True,
                )

                if st.button(
                    "💾  TARIFI KAYDET  →  Tariflerim",
                    type="primary",
                    use_container_width=True,
                    key="save_btn",
                ):
                    rid = save_recipe(
                        sm,
                        sp["name"],
                        sp["ingredients"],
                        sp["cooking"],
                        sp["transport"],
                        {
                            "total_gco2e": sr["total"],
                            "gco2e_per_portion": sr["per_portion"],
                            "klimato_grade": sr["klimato"],
                            "wri_compliant": sr["wri_ok"],
                            "portions": sp.get("portions", 1),
                        },
                        user_id=st.session_state.user["id"],
                    )
                    st.session_state.recipe_saved = True
                    st.rerun()

        elif DB_AVAILABLE and not st.session_state.user:
            # Giris yapilmamis — uyari banner
            st.markdown(
                """
                <div style="
                    background: linear-gradient(135deg, #78350f, #b45309);
                    border-radius: 14px;
                    padding: 20px 28px;
                    display: flex;
                    align-items: center;
                    gap: 14px;
                    margin: 8px 0 24px 0;
                    box-shadow: 0 4px 16px rgba(180,83,9,0.3);
                ">
                    <span style="font-size:32px;">🔒</span>
                    <div>
                        <div style="color:#fef3c7;font-size:13px;font-weight:600;">Tarifi kaydetmek icin giris yapin</div>
                        <div style="color:#fcd34d;font-size:12px;margin-top:4px;">Sol paneldeki giris formunu kullanin</div>
                    </div>
                </div>
                """,
                unsafe_allow_html=True,
            )

        # EXPORT
        st.divider()
        sp2 = st.session_state.last_payload or payload
        c1, c2 = st.columns(2)
        c1.download_button(
            "JSON Indir",
            json.dumps({"id": mid, "payload": sp2, "result": res}, indent=2, default=str),
            "recipe.json",
        )
        if QR_AVAILABLE:
            qr = make_qr(f"https://carbonkey.app/{mid}")
            if qr:
                c2.download_button("QR Indir", qr, "qr.png", "image/png")


if __name__ == "__main__":
    main()
