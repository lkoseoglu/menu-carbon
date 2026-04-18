# admin.py - Menu Carbon Admin Paneli
# Calistirmak icin: streamlit run admin.py
# ONEMLI: Bu dosyaya sadece admin erisebilmeli!

import streamlit as st
import sqlite3
import json
import pandas as pd
from datetime import datetime, timedelta
from pathlib import Path
import hashlib
import os

# ============================================================
# YAPILANDIRMA
# ============================================================
DB_PATH = Path("data/menu_carbon.db")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")  # .env ile degistirin!


def get_conn():
    if not DB_PATH.exists():
        st.error("Veritabani bulunamadi. Once ui_v3.py'yi calistirin.")
        st.stop()
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# ADMIN LOGIN
# ============================================================
def check_admin_login():
    if "admin_logged_in" not in st.session_state:
        st.session_state.admin_logged_in = False

    if st.session_state.admin_logged_in:
        return True

    st.set_page_config(page_title="Admin Girisi", page_icon="🔐", layout="centered")
    st.markdown("""
    <div style="text-align:center;padding:40px 0 20px 0;">
        <div style="font-size:48px;">🔐</div>
        <h1 style="font-size:28px;font-weight:700;margin:8px 0;">Menu Carbon Admin</h1>
        <p style="color:#6b7280;">Yonetim paneline erisim icin giris yapin</p>
    </div>
    """, unsafe_allow_html=True)

    with st.form("admin_login"):
        username = st.text_input("Kullanici Adi", placeholder="admin")
        password = st.text_input("Sifre", type="password", placeholder="••••••••")
        submitted = st.form_submit_button("Giris Yap", use_container_width=True, type="primary")

    if submitted:
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
            st.session_state.admin_logged_in = True
            st.rerun()
        else:
            st.error("Hatali kullanici adi veya sifre!")
    return False


# ============================================================
# VERITABANI SORGU YARDIMCILARI
# ============================================================
def get_all_users():
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT
            id,
            email,
            name,
            company,
            role,
            created_at,
            last_login,
            is_active
        FROM users
        ORDER BY created_at DESC
    """, conn)
    conn.close()
    return df


def get_all_recipes():
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT
            r.id,
            r.name            AS tarif_adi,
            u.email           AS kullanici,
            u.name            AS kullanici_adi,
            r.gco2e_per_portion,
            r.klimato_grade,
            r.wri_compliant,
            r.portions,
            r.meal_type,
            r.created_at,
            r.is_public
        FROM recipes r
        LEFT JOIN users u ON r.user_id = u.id
        ORDER BY r.created_at DESC
    """, conn)
    conn.close()
    return df


def get_user_recipes(user_id: int):
    conn = get_conn()
    df = pd.read_sql_query("""
        SELECT
            id,
            name,
            gco2e_per_portion,
            klimato_grade,
            wri_compliant,
            portions,
            meal_type,
            created_at,
            ingredients_json
        FROM recipes
        WHERE user_id = ?
        ORDER BY created_at DESC
    """, conn, params=(user_id,))
    conn.close()
    return df


def get_summary_stats():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM users WHERE is_active = 1")
    total_users = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM recipes")
    total_recipes = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM calculations")
    total_calcs = cur.fetchone()[0]

    cur.execute("SELECT AVG(gco2e_per_portion) FROM recipes")
    avg_emission = cur.fetchone()[0] or 0

    cur.execute("""
        SELECT COUNT(*) FROM users
        WHERE created_at >= datetime('now', '-7 days')
    """)
    new_users_week = cur.fetchone()[0]

    cur.execute("""
        SELECT COUNT(*) FROM recipes
        WHERE created_at >= datetime('now', '-7 days')
    """)
    new_recipes_week = cur.fetchone()[0]

    cur.execute("""
        SELECT klimato_grade, COUNT(*) as adet
        FROM recipes
        WHERE klimato_grade IS NOT NULL
        GROUP BY klimato_grade
        ORDER BY klimato_grade
    """)
    grade_dist = {row[0]: row[1] for row in cur.fetchall()}

    cur.execute("""
        SELECT u.email, u.name, COUNT(r.id) as tarif_sayisi
        FROM users u
        LEFT JOIN recipes r ON u.id = r.user_id
        GROUP BY u.id
        ORDER BY tarif_sayisi DESC
        LIMIT 10
    """)
    top_users = cur.fetchall()

    cur.execute("""
        SELECT DATE(created_at) as gun, COUNT(*) as adet
        FROM recipes
        WHERE created_at >= datetime('now', '-30 days')
        GROUP BY DATE(created_at)
        ORDER BY gun
    """)
    daily_recipes = cur.fetchall()

    conn.close()
    return {
        "total_users": total_users,
        "total_recipes": total_recipes,
        "total_calcs": total_calcs,
        "avg_emission": round(avg_emission, 1),
        "new_users_week": new_users_week,
        "new_recipes_week": new_recipes_week,
        "grade_dist": grade_dist,
        "top_users": top_users,
        "daily_recipes": daily_recipes,
    }


def toggle_user_active(user_id: int, current_status: int):
    conn = get_conn()
    new_status = 0 if current_status else 1
    conn.execute("UPDATE users SET is_active = ? WHERE id = ?", (new_status, user_id))
    conn.commit()
    conn.close()


def delete_recipe(recipe_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM recipes WHERE id = ?", (recipe_id,))
    conn.commit()
    conn.close()


def reset_user_password(user_id: int, new_password: str):
    salt = os.environ.get("PASSWORD_SALT", "menu_carbon_salt_2024")
    new_hash = hashlib.sha256(f"{new_password}{salt}".encode()).hexdigest()
    conn = get_conn()
    conn.execute("UPDATE users SET password_hash = ? WHERE id = ?", (new_hash, user_id))
    conn.commit()
    conn.close()


# ============================================================
# ANA UYGULAMA
# ============================================================
def main():
    if not check_admin_login():
        return

    st.set_page_config(
        page_title="Menu Carbon Admin",
        page_icon="🛠️",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    # Sidebar
    with st.sidebar:
        st.markdown("""
        <div style="padding:12px 0 8px 0;">
            <div style="font-size:24px;font-weight:800;color:#1d4ed8;">🛠️ Admin Panel</div>
            <div style="font-size:11px;color:#6b7280;margin-top:2px;">Menu Carbon Yonetimi</div>
        </div>
        """, unsafe_allow_html=True)
        st.divider()

        page = st.radio(
            "Navigasyon",
            ["📊 Genel Bakis", "👥 Kullanicilar", "📋 Tarifler", "🔍 Kullanici Detay"],
            label_visibility="collapsed",
        )

        st.divider()
        if st.button("🚪 Cikis Yap", use_container_width=True):
            st.session_state.admin_logged_in = False
            st.rerun()

        st.caption(f"Giris: {ADMIN_USERNAME}")

    # ── GENEL BAKIS ──────────────────────────────────────────────────────────
    if page == "📊 Genel Bakis":
        st.title("📊 Genel Bakis")
        stats = get_summary_stats()

        # KPI kartlar
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Toplam Kullanici", stats["total_users"],
                  delta=f"+{stats['new_users_week']} bu hafta")
        c2.metric("Toplam Tarif", stats["total_recipes"],
                  delta=f"+{stats['new_recipes_week']} bu hafta")
        c3.metric("Toplam Hesaplama", stats["total_calcs"])
        c4.metric("Ort. Emisyon (g)", stats["avg_emission"])

        st.divider()
        col1, col2 = st.columns(2)

        with col1:
            st.subheader("Klimato Not Dagilimi")
            if stats["grade_dist"]:
                grade_df = pd.DataFrame(
                    list(stats["grade_dist"].items()),
                    columns=["Not", "Adet"]
                )
                grade_colors = {
                    "A": "#22c55e", "B": "#84cc16",
                    "C": "#eab308", "D": "#f97316", "E": "#ef4444"
                }
                for _, row in grade_df.iterrows():
                    color = grade_colors.get(row["Not"], "#888")
                    pct = int(row["Adet"] / sum(stats["grade_dist"].values()) * 100)
                    st.markdown(
                        f'<div style="display:flex;align-items:center;gap:10px;margin:6px 0;">'
                        f'<span style="background:{color};color:#fff;font-weight:700;'
                        f'padding:2px 10px;border-radius:6px;font-size:14px;min-width:28px;text-align:center;">'
                        f'{row["Not"]}</span>'
                        f'<div style="flex:1;background:#e5e7eb;border-radius:4px;height:18px;">'
                        f'<div style="background:{color};width:{pct}%;height:100%;border-radius:4px;"></div></div>'
                        f'<span style="font-size:13px;color:#374151;min-width:60px;">'
                        f'{row["Adet"]} tarif ({pct}%)</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.info("Henuz tarif yok.")

        with col2:
            st.subheader("En Aktif Kullanicilar")
            if stats["top_users"]:
                for i, u in enumerate(stats["top_users"], 1):
                    email, name, count = u[0], u[1] or "-", u[2]
                    st.markdown(
                        f'<div style="display:flex;align-items:center;gap:10px;'
                        f'padding:8px 12px;background:#f9fafb;border-radius:8px;margin:4px 0;">'
                        f'<span style="font-weight:700;color:#6b7280;min-width:20px;">#{i}</span>'
                        f'<div style="flex:1;">'
                        f'<div style="font-weight:600;font-size:13px;">{name}</div>'
                        f'<div style="font-size:11px;color:#9ca3af;">{email}</div>'
                        f'</div>'
                        f'<span style="background:#dbeafe;color:#1d4ed8;padding:2px 8px;'
                        f'border-radius:12px;font-size:12px;font-weight:600;">{count} tarif</span>'
                        f'</div>',
                        unsafe_allow_html=True,
                    )
            else:
                st.info("Henuz kullanici yok.")

        # Son 30 gun tarif trendi
        if stats["daily_recipes"]:
            st.subheader("Son 30 Gun Tarif Trendi")
            trend_df = pd.DataFrame(stats["daily_recipes"], columns=["Tarih", "Adet"])
            st.bar_chart(trend_df.set_index("Tarih"))

    # ── KULLANICILAR ─────────────────────────────────────────────────────────
    elif page == "👥 Kullanicilar":
        st.title("👥 Kullanicilar")

        users_df = get_all_users()

        if users_df.empty:
            st.info("Henuz kayitli kullanici yok.")
            return

        # Arama
        search = st.text_input("Email veya isim ara...", placeholder="ornek@email.com")
        if search:
            mask = (
                users_df["email"].str.contains(search, case=False, na=False) |
                users_df["name"].fillna("").str.contains(search, case=False, na=False)
            )
            users_df = users_df[mask]

        st.caption(f"{len(users_df)} kullanici")

        # Tablo
        display_df = users_df[["id", "email", "name", "role", "created_at", "last_login", "is_active"]].copy()
        display_df["is_active"] = display_df["is_active"].map({1: "Aktif", 0: "Pasif"})
        display_df.columns = ["ID", "Email", "Ad", "Rol", "Kayit", "Son Giris", "Durum"]
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        # Export
        csv = display_df.to_csv(index=False).encode("utf-8")
        st.download_button("CSV Indir", csv, "kullanicilar.csv", "text/csv")

        st.divider()

        # Kullanici islemleri
        st.subheader("Kullanici Islemleri")
        col1, col2 = st.columns(2)

        with col1:
            st.markdown("**Kullanici Aktif/Pasif**")
            user_emails = users_df["email"].tolist()
            sel_email = st.selectbox("Kullanici sec", user_emails, key="toggle_user")
            sel_row = users_df[users_df["email"] == sel_email].iloc[0]
            current = int(sel_row["is_active"])
            action_label = "Pasif Yap" if current else "Aktif Yap"
            action_color = "Pasif yapildi" if current else "Aktif yapildi"
            if st.button(action_label, key="toggle_btn"):
                toggle_user_active(int(sel_row["id"]), current)
                st.success(f"{sel_email} {action_color}!")
                st.rerun()

        with col2:
            st.markdown("**Sifre Sifirla**")
            sel_email2 = st.selectbox("Kullanici sec", user_emails, key="reset_user")
            new_pw = st.text_input("Yeni sifre", type="password", key="new_pw")
            new_pw2 = st.text_input("Sifre tekrar", type="password", key="new_pw2")
            if st.button("Sifre Sifirla", key="reset_btn"):
                if not new_pw:
                    st.error("Sifre bos olamaz!")
                elif new_pw != new_pw2:
                    st.error("Sifreler eslesmiyor!")
                elif len(new_pw) < 6:
                    st.error("Sifre en az 6 karakter olmali!")
                else:
                    sel_row2 = users_df[users_df["email"] == sel_email2].iloc[0]
                    reset_user_password(int(sel_row2["id"]), new_pw)
                    st.success(f"{sel_email2} sifresi guncellendi!")

    # ── TARIFLER ─────────────────────────────────────────────────────────────
    elif page == "📋 Tarifler":
        st.title("📋 Tum Tarifler")

        recipes_df = get_all_recipes()

        if recipes_df.empty:
            st.info("Henuz kayitli tarif yok.")
            return

        # Filtreler
        col1, col2, col3 = st.columns(3)
        with col1:
            search_r = st.text_input("Tarif veya kullanici ara...", placeholder="kofte...")
        with col2:
            grade_filter = st.multiselect("Klimato Notu", ["A", "B", "C", "D", "E"])
        with col3:
            meal_filter = st.multiselect("Ogun", ["breakfast", "lunch", "dinner"])

        filtered = recipes_df.copy()
        if search_r:
            mask = (
                filtered["tarif_adi"].str.contains(search_r, case=False, na=False) |
                filtered["kullanici"].fillna("").str.contains(search_r, case=False, na=False)
            )
            filtered = filtered[mask]
        if grade_filter:
            filtered = filtered[filtered["klimato_grade"].isin(grade_filter)]
        if meal_filter:
            filtered = filtered[filtered["meal_type"].isin(meal_filter)]

        st.caption(f"{len(filtered)} tarif")

        # Renk kodlu tablo
        grade_colors = {"A": "#dcfce7", "B": "#fef9c3", "C": "#fed7aa", "D": "#fecaca", "E": "#fca5a5"}

        display_cols = ["id", "tarif_adi", "kullanici", "kullanici_adi",
                        "gco2e_per_portion", "klimato_grade", "wri_compliant",
                        "portions", "meal_type", "created_at"]
        disp = filtered[display_cols].copy()
        disp["wri_compliant"] = disp["wri_compliant"].map({1: "Evet", 0: "Hayir", True: "Evet", False: "Hayir"})
        disp.columns = ["ID", "Tarif", "Email", "Ad", "g CO2e/porsiyon",
                        "Klimato", "WRI", "Porsiyon", "Ogun", "Tarih"]

        def color_klimato(val):
            return f"background-color: {grade_colors.get(val, 'white')}"

        styled = disp.style.applymap(color_klimato, subset=["Klimato"])
        st.dataframe(styled, use_container_width=True, hide_index=True)

        # Export
        csv_r = disp.to_csv(index=False).encode("utf-8")
        st.download_button("CSV Indir", csv_r, "tarifler.csv", "text/csv")

        st.divider()
        st.subheader("Tarif Sil")
        del_id = st.number_input("Silinecek Tarif ID", min_value=1, step=1, value=1)
        if st.button("Tarifi Sil", type="secondary"):
            if del_id in recipes_df["id"].values:
                tarif_adi = recipes_df[recipes_df["id"] == del_id]["tarif_adi"].values[0]
                delete_recipe(int(del_id))
                st.success(f"'{tarif_adi}' (ID:{del_id}) silindi!")
                st.rerun()
            else:
                st.error(f"ID {del_id} bulunamadi!")

    # ── KULLANICI DETAY ───────────────────────────────────────────────────────
    elif page == "🔍 Kullanici Detay":
        st.title("🔍 Kullanici Detay")

        users_df = get_all_users()
        if users_df.empty:
            st.info("Henuz kullanici yok.")
            return

        options = {f"{row['name'] or row['email']} ({row['email']})": row["id"]
                   for _, row in users_df.iterrows()}
        sel = st.selectbox("Kullanici sec", list(options.keys()))
        uid = options[sel]
        user_row = users_df[users_df["id"] == uid].iloc[0]

        # Kullanici bilgi karti
        status_color = "#22c55e" if user_row["is_active"] else "#ef4444"
        status_text = "Aktif" if user_row["is_active"] else "Pasif"
        st.markdown(
            f'<div style="background:#f8fafc;border:1px solid #e2e8f0;border-radius:12px;'
            f'padding:20px 24px;margin-bottom:20px;">'
            f'<div style="display:flex;align-items:center;gap:16px;">'
            f'<div style="width:52px;height:52px;background:#dbeafe;border-radius:50%;'
            f'display:flex;align-items:center;justify-content:center;font-size:22px;">👤</div>'
            f'<div>'
            f'<div style="font-size:18px;font-weight:700;">{user_row["name"] or "(Isimsiz)"}</div>'
            f'<div style="color:#6b7280;font-size:13px;">{user_row["email"]}</div>'
            f'<div style="margin-top:4px;">'
            f'<span style="background:{status_color};color:#fff;padding:2px 8px;'
            f'border-radius:10px;font-size:11px;font-weight:600;">{status_text}</span>'
            f'&nbsp;<span style="background:#e5e7eb;color:#374151;padding:2px 8px;'
            f'border-radius:10px;font-size:11px;">{user_row["role"]}</span>'
            f'</div>'
            f'</div>'
            f'</div>'
            f'<div style="margin-top:12px;display:flex;gap:24px;">'
            f'<div><span style="color:#9ca3af;font-size:11px;">KAYIT</span>'
            f'<div style="font-size:13px;">{str(user_row["created_at"])[:10]}</div></div>'
            f'<div><span style="color:#9ca3af;font-size:11px;">SON GIRIS</span>'
            f'<div style="font-size:13px;">{str(user_row["last_login"] or "-")[:10]}</div></div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Bu kullanicinin tarifleri
        user_recipes = get_user_recipes(int(uid))
        st.subheader(f"Tarifler ({len(user_recipes)})")

        if user_recipes.empty:
            st.info("Bu kullanicinin kayitli tarifi yok.")
        else:
            grade_colors = {"A": "#dcfce7", "B": "#fef9c3", "C": "#fed7aa", "D": "#fecaca", "E": "#fca5a5"}
            for _, r in user_recipes.iterrows():
                color = grade_colors.get(r.get("klimato_grade"), "#f9fafb")
                with st.expander(
                    f"**{r['name']}**  —  {r.get('klimato_grade','?')}  |  "
                    f"{r.get('gco2e_per_portion',0):.0f} g CO2e/porsiyon  |  "
                    f"{str(r.get('created_at',''))[:10]}"
                ):
                    c1, c2, c3 = st.columns(3)
                    c1.metric("Emisyon", f"{r.get('gco2e_per_portion',0):.0f} g CO2e")
                    c2.metric("Klimato", r.get("klimato_grade", "?"))
                    c3.metric("WRI", "Evet" if r.get("wri_compliant") else "Hayir")
                    try:
                        ings = json.loads(r.get("ingredients_json", "[]"))
                        if ings:
                            st.write("**Malzemeler:**")
                            ing_data = [{"Malzeme": i.get("id",""), "Gram": i.get("raw_weight_g",0)} for i in ings]
                            st.dataframe(pd.DataFrame(ing_data), hide_index=True, use_container_width=True)
                    except Exception:
                        pass


if __name__ == "__main__":
    main()
