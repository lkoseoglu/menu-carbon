# dashboard.py - Analytics Dashboard for Partners
# Standalone Streamlit page for partner analytics

import streamlit as st
import pandas as pd
import json
from datetime import datetime, timedelta
from typing import Dict, List, Optional

# Try imports
try:
    import plotly.express as px
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

# Import database functions
try:
    from database import (
        get_partner_analytics,
        get_recipes_by_partner,
        get_calculation_history,
        get_partner_by_slug,
        get_ai_optimizations,
    )
    DB_AVAILABLE = True
except ImportError:
    DB_AVAILABLE = False


# =============================================================================
# DASHBOARD CHARTS
# =============================================================================

def create_grade_distribution_chart(grade_dist: Dict, language: str = "tr") -> go.Figure:
    """Create Klimato grade distribution pie chart"""
    
    grades = ["A", "B", "C", "D", "E"]
    colors = ["#22c55e", "#84cc16", "#eab308", "#f97316", "#ef4444"]
    
    values = [grade_dist.get(g, 0) for g in grades]
    
    labels = {
        "tr": ["A - Çok Düşük", "B - Düşük", "C - Orta", "D - Yüksek", "E - Çok Yüksek"],
        "en": ["A - Very Low", "B - Low", "C - Medium", "D - High", "E - Very High"]
    }
    
    fig = go.Figure(data=[go.Pie(
        labels=labels.get(language, labels["en"]),
        values=values,
        marker_colors=colors,
        hole=0.4,
        textinfo='label+percent',
        textposition='outside',
    )])
    
    title = "Klimato Not Dağılımı" if language == "tr" else "Klimato Grade Distribution"
    fig.update_layout(
        title=dict(text=title, x=0.5),
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.2),
        height=400,
    )
    
    return fig


def create_emission_trend_chart(daily_trend: List[Dict], language: str = "tr") -> go.Figure:
    """Create daily calculation trend line chart"""
    
    if not daily_trend:
        return None
    
    df = pd.DataFrame(daily_trend)
    df["date"] = pd.to_datetime(df["date"])
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=df["date"],
        y=df["count"],
        mode='lines+markers',
        name='Hesaplamalar' if language == "tr" else 'Calculations',
        line=dict(color='#3b82f6', width=3),
        marker=dict(size=8),
        fill='tozeroy',
        fillcolor='rgba(59, 130, 246, 0.1)',
    ))
    
    title = "Günlük Hesaplama Trendi" if language == "tr" else "Daily Calculation Trend"
    fig.update_layout(
        title=dict(text=title, x=0.5),
        xaxis_title="Tarih" if language == "tr" else "Date",
        yaxis_title="Hesaplama Sayısı" if language == "tr" else "Calculation Count",
        height=350,
        hovermode='x unified',
    )
    
    return fig


def create_top_recipes_chart(recipes: List[Dict], chart_type: str = "highest", language: str = "tr") -> go.Figure:
    """Create horizontal bar chart for top recipes"""
    
    if not recipes:
        return None
    
    names = [r["name"][:25] + "..." if len(r["name"]) > 25 else r["name"] for r in recipes]
    values = [r["gco2e_per_portion"] for r in recipes]
    grades = [r["klimato_grade"] for r in recipes]
    
    colors = {
        "A": "#22c55e", "B": "#84cc16", "C": "#eab308", 
        "D": "#f97316", "E": "#ef4444"
    }
    bar_colors = [colors.get(g, "#6b7280") for g in grades]
    
    fig = go.Figure(data=[go.Bar(
        y=names,
        x=values,
        orientation='h',
        marker_color=bar_colors,
        text=[f"{v:.0f}g" for v in values],
        textposition='outside',
    )])
    
    if chart_type == "highest":
        title = "En Yüksek Emisyonlu Tarifler" if language == "tr" else "Highest Emission Recipes"
    else:
        title = "En Düşük Emisyonlu Tarifler" if language == "tr" else "Lowest Emission Recipes"
    
    fig.update_layout(
        title=dict(text=title, x=0.5),
        xaxis_title="g CO₂e / porsiyon",
        yaxis=dict(autorange="reversed"),
        height=300,
        margin=dict(l=150),
    )
    
    return fig


def create_category_breakdown_chart(recipes: List[Dict], language: str = "tr") -> go.Figure:
    """Create category breakdown chart"""
    
    # Aggregate by category
    category_emissions = {}
    category_counts = {}
    
    for recipe in recipes:
        cat = recipe.get("category", "Diğer" if language == "tr" else "Other")
        if not cat:
            cat = "Diğer" if language == "tr" else "Other"
        
        emission = recipe.get("gco2e_per_portion", 0)
        
        if cat not in category_emissions:
            category_emissions[cat] = 0
            category_counts[cat] = 0
        
        category_emissions[cat] += emission
        category_counts[cat] += 1
    
    # Calculate averages
    categories = list(category_emissions.keys())
    avg_emissions = [
        category_emissions[cat] / category_counts[cat] if category_counts[cat] > 0 else 0
        for cat in categories
    ]
    counts = [category_counts[cat] for cat in categories]
    
    fig = make_subplots(
        rows=1, cols=2,
        specs=[[{"type": "bar"}, {"type": "pie"}]],
        subplot_titles=(
            "Kategori Bazlı Ort. Emisyon" if language == "tr" else "Avg Emission by Category",
            "Tarif Dağılımı" if language == "tr" else "Recipe Distribution"
        )
    )
    
    # Bar chart
    fig.add_trace(
        go.Bar(x=categories, y=avg_emissions, marker_color='#3b82f6', name="Ort. Emisyon"),
        row=1, col=1
    )
    
    # Pie chart
    fig.add_trace(
        go.Pie(labels=categories, values=counts, hole=0.3, name="Tarifler"),
        row=1, col=2
    )
    
    fig.update_layout(height=350, showlegend=False)
    
    return fig


def create_wri_compliance_gauge(compliance_rate: float, language: str = "tr") -> go.Figure:
    """Create WRI compliance gauge chart"""
    
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=compliance_rate,
        number={'suffix': "%"},
        delta={'reference': 50, 'position': "bottom"},
        title={'text': "WRI Cool Food Uyum Oranı" if language == "tr" else "WRI Cool Food Compliance"},
        gauge={
            'axis': {'range': [0, 100]},
            'bar': {'color': "#22c55e" if compliance_rate >= 50 else "#f97316"},
            'steps': [
                {'range': [0, 30], 'color': "#fecaca"},
                {'range': [30, 50], 'color': "#fed7aa"},
                {'range': [50, 70], 'color': "#fef9c3"},
                {'range': [70, 100], 'color': "#dcfce7"},
            ],
            'threshold': {
                'line': {'color': "black", 'width': 4},
                'thickness': 0.75,
                'value': compliance_rate
            }
        }
    ))
    
    fig.update_layout(height=280)
    
    return fig


def create_emission_histogram(recipes: List[Dict], language: str = "tr") -> go.Figure:
    """Create emission distribution histogram"""
    
    emissions = [r.get("gco2e_per_portion", 0) for r in recipes if r.get("gco2e_per_portion")]
    
    if not emissions:
        return None
    
    fig = go.Figure(data=[go.Histogram(
        x=emissions,
        nbinsx=20,
        marker_color='#3b82f6',
        opacity=0.75,
    )])
    
    # Add threshold lines
    fig.add_vline(x=500, line_dash="dash", line_color="#22c55e", 
                  annotation_text="WWF Hedef (500g)" if language == "tr" else "WWF Target (500g)")
    fig.add_vline(x=1500, line_dash="dash", line_color="#ef4444",
                  annotation_text="Yüksek (1500g)" if language == "tr" else "High (1500g)")
    
    title = "Emisyon Dağılımı" if language == "tr" else "Emission Distribution"
    fig.update_layout(
        title=dict(text=title, x=0.5),
        xaxis_title="g CO₂e / porsiyon",
        yaxis_title="Tarif Sayısı" if language == "tr" else "Recipe Count",
        height=350,
        bargap=0.1,
    )
    
    return fig


# =============================================================================
# DASHBOARD PAGE
# =============================================================================

def render_dashboard(partner_slug: str = None, language: str = "tr"):
    """Render the analytics dashboard"""
    
    t = {
        "tr": {
            "title": "📊 Partner Dashboard",
            "subtitle": "Menü karbon analitikleri ve içgörüler",
            "overview": "Genel Bakış",
            "total_recipes": "Toplam Tarif",
            "avg_emission": "Ort. Emisyon",
            "calculations": "Hesaplamalar",
            "wri_rate": "WRI Uyum",
            "grade_dist": "Klimato Not Dağılımı",
            "trend": "Hesaplama Trendi",
            "highest": "En Yüksek Emisyonlu",
            "lowest": "En Düşük Emisyonlu",
            "all_recipes": "Tüm Tarifler",
            "export": "Rapor İndir",
            "no_data": "Henüz veri bulunmuyor",
            "last_30_days": "Son 30 Gün",
        },
        "en": {
            "title": "📊 Partner Dashboard",
            "subtitle": "Menu carbon analytics and insights",
            "overview": "Overview",
            "total_recipes": "Total Recipes",
            "avg_emission": "Avg. Emission",
            "calculations": "Calculations",
            "wri_rate": "WRI Compliance",
            "grade_dist": "Klimato Grade Distribution",
            "trend": "Calculation Trend",
            "highest": "Highest Emission",
            "lowest": "Lowest Emission",
            "all_recipes": "All Recipes",
            "export": "Export Report",
            "no_data": "No data available yet",
            "last_30_days": "Last 30 Days",
        }
    }[language]
    
    st.title(t["title"])
    st.caption(t["subtitle"])
    
    # Partner selector
    if not partner_slug:
        partner_slug = st.text_input("Partner Slug", value="demo_partner")
    
    if not DB_AVAILABLE:
        st.error("Database module not available. Please check database.py")
        return
    
    # Get analytics data
    partner = get_partner_by_slug(partner_slug)
    
    if not partner:
        st.warning(f"Partner '{partner_slug}' not found. Showing demo data.")
        # Demo data
        analytics = {
            "total_recipes": 0,
            "grade_distribution": {},
            "avg_emission_per_portion": 0,
            "calculations_last_n_days": 0,
            "wri_compliance_rate": 0,
            "highest_emission_recipes": [],
            "lowest_emission_recipes": [],
            "daily_calculation_trend": [],
        }
        recipes = []
    else:
        analytics = get_partner_analytics(partner["id"], days=30)
        recipes = get_recipes_by_partner(partner["id"], limit=500)
    
    # Overview metrics
    st.subheader(f"📈 {t['overview']}")
    
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric(
            t["total_recipes"],
            analytics["total_recipes"],
            help="Kayıtlı tarif sayısı"
        )
    
    with col2:
        st.metric(
            t["avg_emission"],
            f"{analytics['avg_emission_per_portion']:.0f}g",
            delta=f"{analytics['avg_emission_per_portion'] - 500:.0f}g vs WWF" if analytics['avg_emission_per_portion'] else None,
            delta_color="inverse"
        )
    
    with col3:
        st.metric(
            f"{t['calculations']} ({t['last_30_days']})",
            analytics["calculations_last_n_days"]
        )
    
    with col4:
        st.metric(
            t["wri_rate"],
            f"{analytics['wri_compliance_rate']:.0f}%",
            delta=f"{analytics['wri_compliance_rate'] - 50:.0f}%" if analytics['wri_compliance_rate'] else None
        )
    
    st.divider()
    
    # Charts row 1
    if PLOTLY_AVAILABLE and analytics["total_recipes"] > 0:
        col_ch1, col_ch2 = st.columns(2)
        
        with col_ch1:
            grade_chart = create_grade_distribution_chart(analytics["grade_distribution"], language)
            st.plotly_chart(grade_chart, use_container_width=True)
        
        with col_ch2:
            wri_gauge = create_wri_compliance_gauge(analytics["wri_compliance_rate"], language)
            st.plotly_chart(wri_gauge, use_container_width=True)
        
        # Trend chart
        if analytics["daily_calculation_trend"]:
            trend_chart = create_emission_trend_chart(analytics["daily_calculation_trend"], language)
            if trend_chart:
                st.plotly_chart(trend_chart, use_container_width=True)
        
        st.divider()
        
        # Top recipes
        col_top1, col_top2 = st.columns(2)
        
        with col_top1:
            st.subheader(f"🔴 {t['highest']}")
            if analytics["highest_emission_recipes"]:
                high_chart = create_top_recipes_chart(analytics["highest_emission_recipes"], "highest", language)
                if high_chart:
                    st.plotly_chart(high_chart, use_container_width=True)
            else:
                st.info(t["no_data"])
        
        with col_top2:
            st.subheader(f"🟢 {t['lowest']}")
            if analytics["lowest_emission_recipes"]:
                low_chart = create_top_recipes_chart(analytics["lowest_emission_recipes"], "lowest", language)
                if low_chart:
                    st.plotly_chart(low_chart, use_container_width=True)
            else:
                st.info(t["no_data"])
        
        st.divider()
        
        # Emission histogram
        if recipes:
            hist_chart = create_emission_histogram(recipes, language)
            if hist_chart:
                st.plotly_chart(hist_chart, use_container_width=True)
    
    else:
        st.info(t["no_data"])
    
    # All recipes table
    st.subheader(f"📋 {t['all_recipes']}")
    
    if recipes:
        df = pd.DataFrame([{
            "Tarif" if language == "tr" else "Recipe": r["name"],
            "Emisyon (g)" if language == "tr" else "Emission (g)": r.get("gco2e_per_portion", 0),
            "Klimato": r.get("klimato_grade", "-"),
            "WRI": "✅" if r.get("wri_compliant") else "❌",
            "Porsiyon": r.get("portions", 1),
            "Tarih" if language == "tr" else "Date": r.get("created_at", "")[:10] if r.get("created_at") else "",
        } for r in recipes])
        
        # Color code by Klimato
        def color_grade(val):
            colors = {"A": "#dcfce7", "B": "#fef9c3", "C": "#fed7aa", "D": "#fecaca", "E": "#fca5a5"}
            return f'background-color: {colors.get(val, "white")}'
        
        styled_df = df.style.applymap(color_grade, subset=["Klimato"])
        st.dataframe(styled_df, use_container_width=True, height=400)
        
        # Export button
        csv = df.to_csv(index=False).encode('utf-8')
        st.download_button(
            f"⬇️ {t['export']} (CSV)",
            csv,
            f"menu_carbon_report_{partner_slug}.csv",
            "text/csv",
        )
    else:
        st.info(t["no_data"])


# =============================================================================
# STANDALONE RUN
# =============================================================================

def main():
    """Run dashboard as standalone app"""
    st.set_page_config(
        page_title="Menu Carbon Dashboard",
        page_icon="📊",
        layout="wide",
    )
    
    # Language selector in sidebar
    with st.sidebar:
        st.title("⚙️ Settings")
        language = st.selectbox("Language", ["tr", "en"], format_func=lambda x: "🇹🇷 Türkçe" if x == "tr" else "🇬🇧 English")
        
        st.divider()
        
        partner_slug = st.text_input("Partner Slug", value="demo_partner")
        
        st.divider()
        st.caption("Menu Carbon Dashboard v2.0")
    
    render_dashboard(partner_slug, language)


if __name__ == "__main__":
    main()
