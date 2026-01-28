# ui.py - Advanced Menu Carbon Calculator
# Version: 2.0.0
# Features: Klimato A-E labeling, WRI Cool Food compliance, multi-language,
#           seasonality, insights, alternatives, charts, batch processing, API
#
# Run: streamlit run ui.py
# Requirements: pip install streamlit pandas pillow reportlab plotly pydantic qrcode[pil]

import json
import os
import hashlib
from dataclasses import dataclass, field
from datetime import datetime
from io import BytesIO
from typing import Optional, List, Dict, Any, Tuple
import re

import pandas as pd
import streamlit as st
from PIL import Image, ImageDraw, ImageFont

from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A6, A4
from reportlab.lib.units import mm
from reportlab.lib import colors as rl_colors

# Optional imports
try:
    import qrcode
    QR_AVAILABLE = True
except ImportError:
    QR_AVAILABLE = False

try:
    import plotly.express as px
    import plotly.graph_objects as go
    PLOTLY_AVAILABLE = True
except ImportError:
    PLOTLY_AVAILABLE = False

try:
    from pydantic import BaseModel, Field, validator
    PYDANTIC_AVAILABLE = True
except ImportError:
    PYDANTIC_AVAILABLE = False


# =============================================================================
# CONFIGURATION & CONSTANTS
# =============================================================================

APP_VERSION = "2.0.0"
METHODOLOGY_VERSION = "v2.0"
METHODOLOGY_DATE = "2026-01-26"
METHODOLOGY_FILE = "assets/methodology.pdf"
METHODOLOGY_TITLE = f"Commited Menu Carbon Methodology {METHODOLOGY_VERSION} ({METHODOLOGY_DATE})"

# Energy emission factors (g CO2e per kWh)
ENERGY_FACTORS = {
    "electricity": {"tr": 420.0, "eu": 250.0, "us": 380.0, "global": 475.0},
    "natural_gas": {"tr": 200.0, "eu": 200.0, "us": 200.0, "global": 200.0},
    "lpg": {"tr": 230.0, "eu": 230.0, "us": 230.0, "global": 230.0},
    "wood": {"tr": 30.0, "eu": 30.0, "us": 30.0, "global": 30.0},
}

# Transport emission factors (g CO2e per ton-km)
TRANSPORT_FACTORS = {
    "road": 62.0,
    "rail": 22.0,
    "sea": 16.0,
    "air": 602.0,
}

# Klimato A-E thresholds (g CO2e per 400g portion)
KLIMATO_THRESHOLDS = {
    "A": (0, 400),       # Very Low
    "B": (400, 900),     # Low
    "C": (900, 1800),    # Medium
    "D": (1800, 2600),   # High
    "E": (2600, float('inf')),  # Very High
}

# WRI Cool Food Meal thresholds (g CO2e)
WRI_COOL_FOOD = {
    "breakfast": 3590,
    "lunch": 5380,
    "dinner": 5380,
}

# WWF One Planet Plate target
WWF_TARGET_PER_MEAL = 500  # g CO2e

# Simple 3-tier thresholds
SIMPLE_THRESHOLDS = {
    "low": 500,
    "medium": 1500,
}

# Category colors
CATEGORY_COLORS = {
    "meat": "#ef4444",
    "seafood": "#3b82f6",
    "dairy": "#f59e0b",
    "dairy_alt": "#84cc16",
    "grain": "#d97706",
    "legume": "#22c55e",
    "protein_alt": "#10b981",
    "vegetable": "#22c55e",
    "fruit": "#a855f7",
    "oil": "#eab308",
    "sweetener": "#ec4899",
    "nuts": "#f97316",
    "beverage": "#6366f1",
    "spice": "#8b5cf6",
    "herb": "#14b8a6",
}

# Alternative suggestions for high-impact ingredients
ALTERNATIVES = {
    "beef": [
        ("chicken", -74),
        ("tofu", -93),
        ("lentil", -97),
        ("mushroom", -96),
    ],
    "lamb": [
        ("chicken", -82),
        ("fish_wild", -91),
        ("tempeh", -97),
    ],
    "cheese": [
        ("yogurt", -85),
        ("cheese_feta", -37),
        ("tofu", -85),
    ],
    "butter": [
        ("oil_olive", -58),
        ("oil_sunflower", -75),
    ],
    "shrimp": [
        ("mussel", -97),
        ("fish_wild", -81),
        ("tofu", -89),
    ],
    "rice": [
        ("bulgur", -70),
        ("pasta", -60),
        ("potato", -88),
    ],
}


# =============================================================================
# TRANSLATIONS (Multi-language support)
# =============================================================================

TRANSLATIONS = {
    "tr": {
        # App
        "app_title": "Menü Karbon Ayak İzi Hesaplayıcı",
        "app_subtitle": "Birim: g CO₂e/porsiyon (Malzemeler + Pişirme + Taşıma)",
        
        # Labels
        "low": "DÜŞÜK",
        "medium": "ORTA",
        "high": "YÜKSEK",
        "very_low": "ÇOK DÜŞÜK",
        "very_high": "ÇOK YÜKSEK",
        
        # Sections
        "partner_settings": "Partner & Sertifika Ayarları",
        "recipe_basics": "Tarif Bilgileri",
        "ingredients": "Malzemeler",
        "cooking": "Pişirme",
        "transport": "Taşıma (opsiyonel)",
        "batch_mode": "Toplu İşlem Modu",
        "results": "Sonuçlar",
        "insights": "Çevresel Karşılaştırma",
        "alternatives": "Düşük Karbonlu Alternatifler",
        "breakdown": "Emisyon Dağılımı",
        "certificate": "Sertifika / ID",
        "api_test": "API Test (JSON)",
        
        # Fields
        "partner_slug": "Partner kodu",
        "certificate_url": "Sertifika URL (opsiyonel)",
        "recipe_name": "Tarif adı",
        "portions": "Porsiyon sayısı",
        "energy_type": "Enerji tipi",
        "power_kw": "Ortalama güç (kW)",
        "duration_min": "Süre (dakika)",
        "transport_mode": "Taşıma modu",
        "distance_km": "Mesafe (km)",
        "weight_g": "Ağırlık (g)",
        "meal_type": "Öğün tipi",
        
        # Buttons
        "calculate": "Hesapla",
        "add_ingredient": "➕ Malzeme Ekle",
        "remove_last": "🗑️ Son Malzemeyi Sil",
        "download_csv": "⬇️ CSV İndir",
        "download_xlsx": "⬇️ Excel İndir",
        "download_png": "🖼️ Etiket İndir (PNG)",
        "download_pdf": "📄 Etiket İndir (PDF)",
        "download_json": "⬇️ JSON İndir",
        
        # Results
        "ingredients_emission": "Malzeme Emisyonu",
        "cooking_emission": "Pişirme Emisyonu",
        "transport_emission": "Taşıma Emisyonu",
        "total_emission": "TOPLAM",
        "per_portion": "Porsiyon başına",
        
        # Insights
        "car_km": "🚗 Araba Yolculuğu",
        "tree_absorption": "🌳 Ağaç Absorpsiyonu",
        "smartphone_days": "📱 Telefon Şarjı",
        "lightbulb_hours": "💡 Ampul Kullanımı",
        "wwf_target": "🎯 WWF Hedefine Göre",
        "uk_average": "🇬🇧 UK Ortalamasına Göre",
        
        # Klimato
        "klimato_grade": "Klimato Notu",
        "klimato_a": "A - Çok Düşük Karbon",
        "klimato_b": "B - Düşük Karbon",
        "klimato_c": "C - Orta Karbon",
        "klimato_d": "D - Yüksek Karbon",
        "klimato_e": "E - Çok Yüksek Karbon",
        
        # WRI
        "wri_compliant": "✅ WRI Cool Food Sertifikalı",
        "wri_not_compliant": "❌ WRI Cool Food Sınırını Aşıyor",
        
        # Seasonality
        "season_winter": "Kış",
        "season_summer": "Yaz",
        "season_transition": "Geçiş Dönemi",
        "seasonality_applied": "Mevsimsel faktör uygulandı",
        
        # Misc
        "methodology": "Metodoloji",
        "data_loaded": "Veri yüklendi",
        "qr_disabled": "QR kapalı (pip install qrcode[pil])",
        "powered_by": "Powered by Commited",
        "per_portion_label": "porsiyon başına",
        "scan_for_details": "Detaylar için tarayın",
    },
    "en": {
        # App
        "app_title": "Menu Carbon Footprint Calculator",
        "app_subtitle": "Unit: g CO₂e/portion (Ingredients + Cooking + Transport)",
        
        # Labels
        "low": "LOW",
        "medium": "MEDIUM",
        "high": "HIGH",
        "very_low": "VERY LOW",
        "very_high": "VERY HIGH",
        
        # Sections
        "partner_settings": "Partner & Certificate Settings",
        "recipe_basics": "Recipe Basics",
        "ingredients": "Ingredients",
        "cooking": "Cooking",
        "transport": "Transport (optional)",
        "batch_mode": "Batch Mode",
        "results": "Results",
        "insights": "Environmental Comparison",
        "alternatives": "Low-Carbon Alternatives",
        "breakdown": "Emission Breakdown",
        "certificate": "Certificate / ID",
        "api_test": "API Test (JSON)",
        
        # Fields
        "partner_slug": "Partner slug",
        "certificate_url": "Certificate URL (optional)",
        "recipe_name": "Recipe name",
        "portions": "Number of portions",
        "energy_type": "Energy type",
        "power_kw": "Average power (kW)",
        "duration_min": "Duration (minutes)",
        "transport_mode": "Transport mode",
        "distance_km": "Distance (km)",
        "weight_g": "Weight (g)",
        "meal_type": "Meal type",
        
        # Buttons
        "calculate": "Calculate",
        "add_ingredient": "➕ Add Ingredient",
        "remove_last": "🗑️ Remove Last",
        "download_csv": "⬇️ Download CSV",
        "download_xlsx": "⬇️ Download Excel",
        "download_png": "🖼️ Download Label (PNG)",
        "download_pdf": "📄 Download Label (PDF)",
        "download_json": "⬇️ Download JSON",
        
        # Results
        "ingredients_emission": "Ingredient Emissions",
        "cooking_emission": "Cooking Emissions",
        "transport_emission": "Transport Emissions",
        "total_emission": "TOTAL",
        "per_portion": "Per portion",
        
        # Insights
        "car_km": "🚗 Car Journey",
        "tree_absorption": "🌳 Tree Absorption",
        "smartphone_days": "📱 Phone Charging",
        "lightbulb_hours": "💡 Lightbulb Usage",
        "wwf_target": "🎯 vs WWF Target",
        "uk_average": "🇬🇧 vs UK Average",
        
        # Klimato
        "klimato_grade": "Klimato Grade",
        "klimato_a": "A - Very Low Carbon",
        "klimato_b": "B - Low Carbon",
        "klimato_c": "C - Medium Carbon",
        "klimato_d": "D - High Carbon",
        "klimato_e": "E - Very High Carbon",
        
        # WRI
        "wri_compliant": "✅ WRI Cool Food Certified",
        "wri_not_compliant": "❌ Exceeds WRI Cool Food Threshold",
        
        # Seasonality
        "season_winter": "Winter",
        "season_summer": "Summer",
        "season_transition": "Transition",
        "seasonality_applied": "Seasonal factor applied",
        
        # Misc
        "methodology": "Methodology",
        "data_loaded": "Data loaded",
        "qr_disabled": "QR disabled (pip install qrcode[pil])",
        "powered_by": "Powered by Commited",
        "per_portion_label": "per portion",
        "scan_for_details": "Scan for details",
    }
}


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_current_season() -> str:
    """Determine current season based on month"""
    month = datetime.now().month
    if month in [12, 1, 2]:
        return "winter"
    elif month in [6, 7, 8]:
        return "summer"
    return "transition"


def get_season_factor(ingredient_id: str, season: str, seasonality_map: dict) -> float:
    """Get seasonality multiplier for ingredient"""
    if season == "summer":
        return 1.0
    factor = seasonality_map.get(ingredient_id, 1.0)
    if season == "winter":
        return factor
    # Transition: halfway between summer and winter
    return 1.0 + (factor - 1.0) * 0.5


def classify_simple(total_g: float) -> str:
    """Simple 3-tier classification (LOW/MEDIUM/HIGH)"""
    if total_g < SIMPLE_THRESHOLDS["low"]:
        return "LOW"
    if total_g <= SIMPLE_THRESHOLDS["medium"]:
        return "MEDIUM"
    return "HIGH"


def classify_klimato(total_g: float, portion_weight_g: float = 400) -> str:
    """Klimato A-E classification (normalized to 400g portion)"""
    # Normalize to 400g standard portion
    if portion_weight_g > 0:
        normalized = (total_g / portion_weight_g) * 400
    else:
        normalized = total_g
    
    for grade, (low, high) in KLIMATO_THRESHOLDS.items():
        if low <= normalized < high:
            return grade
    return "E"


def get_klimato_color(grade: str) -> str:
    """Get color for Klimato grade"""
    colors = {
        "A": "#22c55e",  # Green
        "B": "#84cc16",  # Light green
        "C": "#eab308",  # Yellow
        "D": "#f97316",  # Orange
        "E": "#ef4444",  # Red
    }
    return colors.get(grade, "#6b7280")


def get_simple_label_color(label: str) -> str:
    """Get color for simple label"""
    if "LOW" in label:
        return "#22c55e"
    if "MEDIUM" in label:
        return "#eab308"
    return "#ef4444"


def check_wri_compliance(total_gco2e: float, meal_type: str = "lunch") -> dict:
    """Check WRI Cool Food Meals compliance"""
    threshold = WRI_COOL_FOOD.get(meal_type, 5380)
    compliant = total_gco2e <= threshold
    return {
        "compliant": compliant,
        "threshold": threshold,
        "meal_type": meal_type,
        "percentage": round((total_gco2e / threshold) * 100, 1),
    }


def generate_insights(total_gco2e: float) -> dict:
    """Generate comparative insights for the emission value"""
    return {
        "car_km": round(total_gco2e / 120, 1),  # ~120g CO2/km average car
        "lightbulb_hours": round(total_gco2e / 42, 1),  # 100W bulb ~42g/hour
        "smartphone_days": round(total_gco2e / 8, 1),  # ~8g CO2/day charging
        "tree_minutes": round(total_gco2e / 0.02, 0),  # Tree absorbs ~0.02g/min
        "uk_average_percent": round((total_gco2e / 1600) * 100, 0),  # UK avg 1600g
        "wwf_target_percent": round((total_gco2e / WWF_TARGET_PER_MEAL) * 100, 0),
    }


def suggest_alternatives(ingredients: list, ef_map: dict, name_map: dict) -> list:
    """Suggest lower-carbon alternatives for high-impact ingredients"""
    suggestions = []
    
    for ing in ingredients:
        ing_id = ing.get("id", "").lower()
        ef = ing.get("emission_factor_g_per_g", 0)
        
        if ing_id in ALTERNATIVES and ef > 5:  # Only for high-impact
            for alt_id, reduction in ALTERNATIVES[ing_id]:
                if alt_id in ef_map:
                    alt_ef = ef_map[alt_id]
                    actual_reduction = round((1 - alt_ef / ef) * 100)
                    suggestions.append({
                        "original_id": ing_id,
                        "original_name": ing.get("name", ing_id),
                        "alternative_id": alt_id,
                        "alternative_name": name_map.get(alt_id, alt_id),
                        "reduction_percent": actual_reduction,
                        "original_ef": ef,
                        "alternative_ef": alt_ef,
                    })
    
    # Sort by reduction percentage
    suggestions.sort(key=lambda x: x["reduction_percent"], reverse=True)
    return suggestions[:5]  # Top 5 suggestions


def compute_menu_carbon_id(payload: dict) -> str:
    """Generate deterministic hash ID for the recipe"""
    # Canonical form for consistent hashing
    ingr = []
    for it in payload.get("ingredients", []):
        ingr.append({
            "id": str(it.get("id", "")).strip().lower(),
            "raw_weight_g": round(float(it.get("raw_weight_g", 0.0)), 3),
            "ef": round(float(it.get("emission_factor_g_per_g", 0.0)), 6),
        })
    ingr_sorted = sorted(ingr, key=lambda x: (x["id"], x["raw_weight_g"], x["ef"]))
    
    cooking = payload.get("cooking", {})
    transport = payload.get("transport", {})
    
    canonical = {
        "name": str(payload.get("name", "")).strip(),
        "ingredients": ingr_sorted,
        "cooking": {
            "energy_type": str(cooking.get("energy_type", "")).strip(),
            "average_power_kw": round(float(cooking.get("average_power_kw", 0.0)), 6),
            "duration_min": round(float(cooking.get("duration_min", 0.0)), 3),
        },
        "transport": {
            "enabled": bool(transport.get("enabled", False)),
            "mode": str(transport.get("mode", "")).strip(),
            "distance_km": round(float(transport.get("distance_km", 0.0)), 3),
        },
    }
    
    s = json.dumps(canonical, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(s.encode("utf-8")).hexdigest()[:16]


def make_qr_png_bytes(text: str, size_px: int = 380) -> Optional[bytes]:
    """Generate QR code PNG bytes"""
    if not QR_AVAILABLE:
        return None
    try:
        qr = qrcode.QRCode(
            version=None,
            error_correction=qrcode.constants.ERROR_CORRECT_M,
            box_size=10,
            border=2,
        )
        qr.add_data(text)
        qr.make(fit=True)
        img = qr.make_image(fill_color="black", back_color="white").convert("RGB")
        img = img.resize((size_px, size_px))
        out = BytesIO()
        img.save(out, format="PNG", optimize=True)
        return out.getvalue()
    except Exception:
        return None


# =============================================================================
# DATA LOADING & FACTOR MAPS
# =============================================================================

@st.cache_data
def load_factors_csv(path: str = "data/factors.csv") -> pd.DataFrame:
    """Load and cache the factors CSV"""
    df = pd.read_csv(path)
    df.columns = [c.strip() for c in df.columns]
    return df


def build_factor_maps(df: pd.DataFrame, language: str = "tr") -> Tuple[dict, dict, dict, dict, dict]:
    """
    Build lookup maps from the factors DataFrame.
    
    Returns:
        - ef_map: ingredient_id -> emission factor (g CO2e/g)
        - name_map: ingredient_id -> display name
        - syn_map: synonym -> canonical ingredient_id
        - category_map: ingredient_id -> category
        - seasonality_map: ingredient_id -> winter factor
    """
    required = {"ingredient_id", "ingredient_name", "ef_gco2e_per_g"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"factors.csv missing columns: {missing}")
    
    ef_map = {}
    name_map = {}
    syn_map = {}
    category_map = {}
    seasonality_map = {}
    
    # Check for localized name column
    name_col = f"ingredient_name_{language}" if f"ingredient_name_{language}" in df.columns else "ingredient_name"
    
    for _, row in df.iterrows():
        ing_id = str(row["ingredient_id"]).strip().lower()
        if not ing_id:
            continue
        
        ef_map[ing_id] = float(row["ef_gco2e_per_g"])
        name_map[ing_id] = str(row.get(name_col, row["ingredient_name"])).strip()
        syn_map[ing_id] = ing_id  # Self-reference
        
        # Category
        if "category" in df.columns and pd.notna(row.get("category")):
            category_map[ing_id] = str(row["category"]).strip().lower()
        
        # Seasonality
        if "seasonality_winter_factor" in df.columns and pd.notna(row.get("seasonality_winter_factor")):
            seasonality_map[ing_id] = float(row["seasonality_winter_factor"])
        
        # Synonyms
        if "synonyms" in df.columns and pd.notna(row.get("synonyms")):
            syns = str(row["synonyms"]).strip()
            for token in syns.split(","):
                t = token.strip().lower()
                if t:
                    syn_map[t] = ing_id
    
    return ef_map, name_map, syn_map, category_map, seasonality_map


def resolve_ingredient_id(user_input: str, syn_map: dict) -> str:
    """Resolve user input to canonical ingredient ID"""
    t = str(user_input or "").strip().lower()
    if not t:
        return ""
    if t in syn_map:
        return syn_map[t]
    # Try with underscores instead of spaces
    t2 = "_".join(t.split())
    return syn_map.get(t2, t)


def pick_first_available(used: set, options: list) -> str:
    """Pick first available option not in used set"""
    for opt in options:
        if opt not in used:
            return opt
    return options[0] if options else ""


# =============================================================================
# CORE CALCULATION ENGINE
# =============================================================================

def calculate(
    payload: dict,
    region: str = "tr",
    apply_seasonality: bool = True,
    season: str = None,
    seasonality_map: dict = None,
) -> dict:
    """
    Core carbon footprint calculation.
    
    Args:
        payload: Recipe payload with ingredients, cooking, transport
        region: Geographic region for energy factors
        apply_seasonality: Whether to apply seasonal adjustments
        season: Override season (winter/summer/transition)
        seasonality_map: Map of ingredient_id -> winter factor
    
    Returns:
        Dictionary with emission breakdown and labels
    """
    if season is None:
        season = get_current_season()
    
    if seasonality_map is None:
        seasonality_map = {}
    
    # Ingredient emissions
    ingredient_emissions = 0.0
    total_weight_g = 0.0
    ingredient_details = []
    
    for it in payload.get("ingredients", []):
        ing_id = str(it.get("id", "")).lower()
        w = float(it.get("raw_weight_g", 0))
        ef = float(it.get("emission_factor_g_per_g", 0))
        
        # Apply seasonality
        if apply_seasonality and ing_id in seasonality_map:
            season_factor = get_season_factor(ing_id, season, seasonality_map)
            ef_adjusted = ef * season_factor
        else:
            season_factor = 1.0
            ef_adjusted = ef
        
        emission = w * ef_adjusted
        ingredient_emissions += emission
        total_weight_g += w
        
        ingredient_details.append({
            "id": ing_id,
            "name": it.get("name", ing_id),
            "weight_g": w,
            "ef_original": ef,
            "ef_adjusted": ef_adjusted,
            "season_factor": season_factor,
            "emission_gco2e": round(emission, 2),
        })
    
    # Cooking emissions
    cooking = payload.get("cooking", {})
    duration_hours = float(cooking.get("duration_min", 0)) / 60.0
    kwh = float(cooking.get("average_power_kw", 0)) * duration_hours
    energy_type = cooking.get("energy_type", "electricity")
    
    # Get region-specific energy factor
    energy_factor = ENERGY_FACTORS.get(energy_type, {}).get(region, 420.0)
    cooking_emissions = kwh * energy_factor
    
    # Transport emissions
    transport_emissions = 0.0
    transport = payload.get("transport", {})
    if transport.get("enabled"):
        total_weight_kg = total_weight_g / 1000.0
        total_weight_ton = total_weight_kg / 1000.0
        mode = transport.get("mode", "road")
        dist = float(transport.get("distance_km", 0))
        tf = TRANSPORT_FACTORS.get(mode, 62.0)
        transport_emissions = total_weight_ton * dist * tf
    
    # Totals
    total = ingredient_emissions + cooking_emissions + transport_emissions
    portions = max(1, int(payload.get("portions", 1)))
    per_portion = total / portions
    
    # Classifications
    simple_label = classify_simple(per_portion)
    klimato_grade = classify_klimato(per_portion, total_weight_g / portions if portions > 0 else 400)
    
    # WRI compliance (default to lunch)
    meal_type = payload.get("meal_type", "lunch")
    wri_check = check_wri_compliance(per_portion, meal_type)
    
    return {
        "ingredient_emissions_gco2e": round(ingredient_emissions, 2),
        "cooking_emissions_gco2e": round(cooking_emissions, 2),
        "transport_emissions_gco2e": round(transport_emissions, 2),
        "total_gco2e": round(total, 2),
        "portions": portions,
        "gco2e_per_portion": round(per_portion, 2),
        "total_weight_g": round(total_weight_g, 2),
        
        # Labels
        "label_simple": simple_label,
        "klimato_grade": klimato_grade,
        "klimato_color": get_klimato_color(klimato_grade),
        
        # WRI
        "wri_compliant": wri_check["compliant"],
        "wri_threshold": wri_check["threshold"],
        "wri_percentage": wri_check["percentage"],
        
        # Details
        "ingredient_details": ingredient_details,
        "season_applied": season if apply_seasonality else None,
        "region": region,
        
        # Insights
        "insights": generate_insights(per_portion),
    }


# =============================================================================
# VALIDATION (Pydantic models if available)
# =============================================================================

if PYDANTIC_AVAILABLE:
    class IngredientInput(BaseModel):
        id: str
        raw_weight_g: float = Field(ge=0, le=10000)
        emission_factor_g_per_g: Optional[float] = None
        name: Optional[str] = None
        
        @validator('raw_weight_g')
        def weight_reasonable(cls, v):
            if v > 5000:
                raise ValueError('Single ingredient weight should not exceed 5kg')
            return v
    
    class CookingInput(BaseModel):
        energy_type: str = "electricity"
        average_power_kw: float = Field(ge=0, le=50, default=0)
        duration_min: float = Field(ge=0, le=480, default=0)
        
        @validator('energy_type')
        def valid_energy_type(cls, v):
            allowed = list(ENERGY_FACTORS.keys())
            if v not in allowed:
                raise ValueError(f'Energy type must be one of: {allowed}')
            return v
    
    class TransportInput(BaseModel):
        enabled: bool = False
        mode: str = "road"
        distance_km: float = Field(ge=0, le=50000, default=0)
        
        @validator('mode')
        def valid_mode(cls, v):
            allowed = list(TRANSPORT_FACTORS.keys())
            if v not in allowed:
                raise ValueError(f'Transport mode must be one of: {allowed}')
            return v
    
    class RecipePayload(BaseModel):
        name: str
        portions: int = Field(ge=1, le=1000, default=1)
        ingredients: List[IngredientInput]
        cooking: CookingInput = CookingInput()
        transport: TransportInput = TransportInput()
        partner_slug: Optional[str] = None
        meal_type: str = "lunch"
        
        @validator('ingredients')
        def at_least_one_ingredient(cls, v):
            if len(v) < 1:
                raise ValueError('At least one ingredient is required')
            return v


# =============================================================================
# CHART GENERATION (Plotly)
# =============================================================================

def create_emission_breakdown_pie(ingredient_details: list, cooking_emission: float, 
                                   transport_emission: float, language: str = "tr") -> Any:
    """Create pie chart showing emission breakdown by source"""
    if not PLOTLY_AVAILABLE:
        return None
    
    # Aggregate ingredient emissions
    ing_total = sum(i["emission_gco2e"] for i in ingredient_details)
    
    labels = []
    values = []
    colors = []
    
    if ing_total > 0:
        labels.append("Malzemeler" if language == "tr" else "Ingredients")
        values.append(round(ing_total, 2))
        colors.append("#22c55e")
    
    if cooking_emission > 0:
        labels.append("Pişirme" if language == "tr" else "Cooking")
        values.append(round(cooking_emission, 2))
        colors.append("#3b82f6")
    
    if transport_emission > 0:
        labels.append("Taşıma" if language == "tr" else "Transport")
        values.append(round(transport_emission, 2))
        colors.append("#f59e0b")
    
    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        marker_colors=colors,
        hole=0.4,
        textinfo='label+percent',
        textposition='outside',
    )])
    
    fig.update_layout(
        title=dict(
            text="Emisyon Kaynakları" if language == "tr" else "Emission Sources",
            x=0.5,
            font=dict(size=16)
        ),
        showlegend=False,
        height=350,
        margin=dict(t=60, b=20, l=20, r=20),
    )
    
    return fig


def create_ingredient_breakdown_bar(ingredient_details: list, category_map: dict,
                                     language: str = "tr") -> Any:
    """Create horizontal bar chart showing emission by ingredient"""
    if not PLOTLY_AVAILABLE:
        return None
    
    # Sort by emission
    sorted_details = sorted(ingredient_details, key=lambda x: x["emission_gco2e"], reverse=True)
    
    names = [i["name"] for i in sorted_details]
    values = [i["emission_gco2e"] for i in sorted_details]
    colors = []
    
    for i in sorted_details:
        cat = category_map.get(i["id"], "other")
        colors.append(CATEGORY_COLORS.get(cat, "#6b7280"))
    
    fig = go.Figure(data=[go.Bar(
        y=names,
        x=values,
        orientation='h',
        marker_color=colors,
        text=[f"{v:.0f}g" for v in values],
        textposition='outside',
    )])
    
    fig.update_layout(
        title=dict(
            text="Malzeme Bazında Emisyon" if language == "tr" else "Emission by Ingredient",
            x=0.5,
            font=dict(size=16)
        ),
        xaxis_title="g CO₂e",
        yaxis=dict(autorange="reversed"),
        height=max(300, len(names) * 35),
        margin=dict(t=60, b=40, l=120, r=60),
        showlegend=False,
    )
    
    return fig


def create_klimato_gauge(grade: str, per_portion: float, language: str = "tr") -> Any:
    """Create gauge chart showing Klimato grade"""
    if not PLOTLY_AVAILABLE:
        return None
    
    grade_values = {"A": 200, "B": 650, "C": 1350, "D": 2200, "E": 3000}
    grade_colors = {
        "A": "#22c55e", "B": "#84cc16", "C": "#eab308", 
        "D": "#f97316", "E": "#ef4444"
    }
    
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=per_portion,
        number={'suffix': " g CO₂e", 'font': {'size': 24}},
        title={'text': f"Klimato: {grade}", 'font': {'size': 20, 'color': grade_colors[grade]}},
        gauge={
            'axis': {'range': [0, 3000], 'tickwidth': 1},
            'bar': {'color': grade_colors[grade]},
            'steps': [
                {'range': [0, 400], 'color': '#dcfce7'},
                {'range': [400, 900], 'color': '#fef9c3'},
                {'range': [900, 1800], 'color': '#fed7aa'},
                {'range': [1800, 2600], 'color': '#fecaca'},
                {'range': [2600, 3000], 'color': '#fca5a5'},
            ],
            'threshold': {
                'line': {'color': "black", 'width': 4},
                'thickness': 0.75,
                'value': per_portion
            }
        }
    ))
    
    fig.update_layout(
        height=280,
        margin=dict(t=60, b=20, l=30, r=30),
    )
    
    return fig


def create_comparison_chart(per_portion: float, language: str = "tr") -> Any:
    """Create comparison bar chart vs targets/averages"""
    if not PLOTLY_AVAILABLE:
        return None
    
    labels = [
        "Bu Yemek" if language == "tr" else "This Meal",
        "WWF Hedefi" if language == "tr" else "WWF Target",
        "UK Ortalaması" if language == "tr" else "UK Average",
        "Vejetaryen Ort." if language == "tr" else "Vegetarian Avg",
    ]
    values = [per_portion, 500, 1600, 400]
    colors = ["#3b82f6", "#22c55e", "#ef4444", "#84cc16"]
    
    fig = go.Figure(data=[go.Bar(
        x=labels,
        y=values,
        marker_color=colors,
        text=[f"{v:.0f}g" for v in values],
        textposition='outside',
    )])
    
    fig.update_layout(
        title=dict(
            text="Karşılaştırma" if language == "tr" else "Comparison",
            x=0.5,
            font=dict(size=16)
        ),
        yaxis_title="g CO₂e / porsiyon",
        height=350,
        margin=dict(t=60, b=40, l=60, r=40),
        showlegend=False,
    )
    
    return fig


# =============================================================================
# LABEL EXPORT (PNG)
# =============================================================================

def build_label_png_bytes(
    recipe_name: str,
    total_gco2e: float,
    klimato_grade: str,
    methodology_title: str,
    qr_text: str = None,
    language: str = "tr",
) -> bytes:
    """Generate high-resolution PNG label"""
    W, H = 1240, 1748  # A6-ish hi-res
    img = Image.new("RGB", (W, H), "white")
    draw = ImageDraw.Draw(img)
    
    t = TRANSLATIONS.get(language, TRANSLATIONS["en"])
    
    def load_font(size: int, bold: bool = False):
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold else "/System/Library/Fonts/Supplemental/Arial.ttf",
        ]
        for p in candidates:
            try:
                return ImageFont.truetype(p, size=size)
            except Exception:
                continue
        return ImageFont.load_default()
    
    font_title = load_font(56, bold=True)
    font_h = load_font(40, bold=True)
    font_body = load_font(34, bold=False)
    font_big = load_font(86, bold=True)
    font_small = load_font(26, bold=False)
    font_tiny = load_font(22, bold=False)
    
    pad = 80
    y = pad
    
    # Header
    draw.text((pad, y), "Menu Carbon Label", fill="black", font=font_title)
    y += 130
    
    # Dish name
    draw.text((pad, y), "Dish" if language == "en" else "Yemek", fill="black", font=font_h)
    y += 60
    rn = (recipe_name or "").strip()[:42]
    if len(recipe_name or "") > 42:
        rn += "…"
    draw.text((pad, y), rn, fill="black", font=font_body)
    y += 140
    
    # Total
    draw.text((pad, y), "Total footprint" if language == "en" else "Toplam Ayak İzi", fill="black", font=font_h)
    y += 70
    draw.text((pad, y), f"{total_gco2e:.0f} g CO₂e", fill="black", font=font_big)
    y += 110
    draw.text((pad, y), t["per_portion_label"], fill=(60, 60, 60), font=font_small)
    y += 120
    
    # QR (optional)
    if qr_text and QR_AVAILABLE:
        qr_bytes = make_qr_png_bytes(qr_text, size_px=360)
        if qr_bytes:
            qr_img = Image.open(BytesIO(qr_bytes))
            img.paste(qr_img, (W - pad - 360, y - 10))
        draw.text((pad, y + 20), t["scan_for_details"], fill=(40, 40, 40), font=font_small)
        y += 260
    else:
        y += 40
    
    # Klimato Badge
    color = get_klimato_color(klimato_grade)
    r = int(color[1:3], 16)
    g = int(color[3:5], 16)
    b = int(color[5:7], 16)
    
    badge_w, badge_h = 700, 120
    badge_x, badge_y = pad, y
    radius = 60
    draw.rounded_rectangle([badge_x, badge_y, badge_x + badge_w, badge_y + badge_h], 
                           radius=radius, fill=(r, g, b))
    
    # Dot
    dot_r = 18
    dot_cx = badge_x + 55
    dot_cy = badge_y + badge_h // 2
    draw.ellipse([dot_cx - dot_r, dot_cy - dot_r, dot_cx + dot_r, dot_cy + dot_r], fill="white")
    
    # Grade text
    grade_text = t.get(f"klimato_{klimato_grade.lower()}", f"Grade {klimato_grade}")
    draw.text((badge_x + 95, badge_y + 32), grade_text, fill="white", font=load_font(40, bold=True))
    y = badge_y + badge_h + 90
    
    # Methodology
    draw.text((pad, y), t["methodology"] + ":", fill="black", font=font_small)
    y += 50
    mt = (methodology_title or "").strip()[:64]
    draw.text((pad, y), mt, fill=(40, 40, 40), font=font_tiny)
    
    # Footer
    footer = t["powered_by"]
    bbox = draw.textbbox((0, 0), footer, font=font_tiny)
    tw = bbox[2] - bbox[0]
    draw.text((W - pad - tw, H - pad), footer, fill=(80, 80, 80), font=font_tiny)
    
    out = BytesIO()
    img.save(out, format="PNG", optimize=True)
    return out.getvalue()


# =============================================================================
# LABEL EXPORT (PDF - A6)
# =============================================================================

def build_label_pdf_bytes(
    recipe_name: str,
    total_gco2e: float,
    klimato_grade: str,
    methodology_title: str,
    qr_text: str = None,
    language: str = "tr",
) -> bytes:
    """Generate A6 PDF label"""
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A6)
    width, height = A6
    
    t = TRANSLATIONS.get(language, TRANSLATIONS["en"])
    
    # Background
    c.setFillColor(rl_colors.white)
    c.rect(0, 0, width, height, stroke=0, fill=1)
    
    # Header
    c.setFillColor(rl_colors.black)
    c.setFont("Helvetica-Bold", 14)
    c.drawString(12 * mm, height - 16 * mm, "Menu Carbon Label")
    
    # Dish
    c.setFont("Helvetica-Bold", 12)
    c.drawString(12 * mm, height - 28 * mm, "Dish" if language == "en" else "Yemek")
    c.setFont("Helvetica", 11)
    c.drawString(12 * mm, height - 35 * mm, (recipe_name or "")[:40])
    
    # Total
    c.setFont("Helvetica-Bold", 12)
    c.drawString(12 * mm, height - 48 * mm, "Total footprint" if language == "en" else "Toplam Ayak İzi")
    c.setFont("Helvetica-Bold", 20)
    c.drawString(12 * mm, height - 62 * mm, f"{total_gco2e:.0f} g CO2e")
    c.setFont("Helvetica", 9)
    c.drawString(12 * mm, height - 68 * mm, t["per_portion_label"])
    
    # QR
    if qr_text and QR_AVAILABLE:
        qr_bytes = make_qr_png_bytes(qr_text, size_px=220)
        if qr_bytes:
            c.drawInlineImage(Image.open(BytesIO(qr_bytes)), 
                            width - 12 * mm - 26 * mm, height - 74 * mm, 26 * mm, 26 * mm)
    
    # Klimato Badge
    color = get_klimato_color(klimato_grade)
    r_val = int(color[1:3], 16) / 255
    g_val = int(color[3:5], 16) / 255
    b_val = int(color[5:7], 16) / 255
    badge_color = rl_colors.Color(r_val, g_val, b_val)
    
    c.setFillColor(badge_color)
    c.roundRect(12 * mm, height - 88 * mm, 60 * mm, 12 * mm, 6 * mm, stroke=0, fill=1)
    c.setFillColor(rl_colors.white)
    c.setFont("Helvetica-Bold", 10)
    grade_text = t.get(f"klimato_{klimato_grade.lower()}", f"Grade {klimato_grade}")
    c.drawString(16 * mm, height - 85 * mm, grade_text[:30])
    
    # Methodology
    c.setFillColor(rl_colors.black)
    c.setFont("Helvetica", 7.5)
    c.drawString(12 * mm, 18 * mm, t["methodology"] + ":")
    c.setFont("Helvetica", 7)
    c.drawString(12 * mm, 14 * mm, (methodology_title or "")[:70])
    
    # Footer
    c.setFont("Helvetica-Oblique", 7)
    c.drawRightString(width - 10 * mm, 10 * mm, t["powered_by"])
    
    c.showPage()
    c.save()
    
    pdf_bytes = buf.getvalue()
    buf.close()
    return pdf_bytes


# =============================================================================
# BATCH PROCESSING
# =============================================================================

def batch_compute(
    df: pd.DataFrame,
    ef_map: dict,
    name_map: dict,
    syn_map: dict,
    seasonality_map: dict,
    default_cooking: dict,
    default_transport: dict,
    partner_slug: str,
    certificate_base_url: str,
    region: str = "tr",
    apply_seasonality: bool = True,
) -> pd.DataFrame:
    """Process batch recipes from CSV"""
    cols = [c.strip() for c in df.columns]
    df.columns = cols
    
    required = {"recipe_name", "ingredient_id", "weight_g"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"Batch CSV missing columns: {missing}")
    
    # Normalize
    df["recipe_name"] = df["recipe_name"].astype(str).str.strip()
    df["ingredient_id"] = df["ingredient_id"].astype(str).str.strip().str.lower()
    df["weight_g"] = df["weight_g"].astype(float)
    
    if "portions" not in df.columns:
        df["portions"] = 1
    df["portions"] = df["portions"].fillna(1).astype(int)
    
    if "meal_type" not in df.columns:
        df["meal_type"] = "lunch"
    
    rows = []
    
    for recipe, g in df.groupby("recipe_name"):
        ingr = []
        for _, r in g.iterrows():
            rid = resolve_ingredient_id(r["ingredient_id"], syn_map)
            ingr.append({
                "id": rid,
                "name": name_map.get(rid, rid),
                "raw_weight_g": float(r["weight_g"]),
                "emission_factor_g_per_g": float(ef_map.get(rid, 0.0)),
            })
        
        payload = {
            "partner_slug": partner_slug,
            "name": recipe,
            "portions": int(g["portions"].iloc[0]),
            "meal_type": g["meal_type"].iloc[0] if "meal_type" in g.columns else "lunch",
            "ingredients": ingr,
            "cooking": default_cooking,
            "transport": default_transport,
        }
        
        result = calculate(
            payload,
            region=region,
            apply_seasonality=apply_seasonality,
            seasonality_map=seasonality_map,
        )
        
        menu_id = compute_menu_carbon_id(payload)
        cert_url = (certificate_base_url.rstrip("/") + "/" + menu_id) if certificate_base_url.strip() else ""
        
        rows.append({
            "partner_slug": partner_slug,
            "recipe_name": recipe,
            "menu_carbon_id": menu_id,
            "certificate_url": cert_url,
            "total_gco2e": result["total_gco2e"],
            "portions": result["portions"],
            "gco2e_per_portion": result["gco2e_per_portion"],
            "label_simple": result["label_simple"],
            "klimato_grade": result["klimato_grade"],
            "wri_compliant": result["wri_compliant"],
            "ingredients_gco2e": result["ingredient_emissions_gco2e"],
            "cooking_gco2e": result["cooking_emissions_gco2e"],
            "transport_gco2e": result["transport_emissions_gco2e"],
        })
    
    return pd.DataFrame(rows).sort_values(["klimato_grade", "gco2e_per_portion"], ascending=[True, True])


# =============================================================================
# STREAMLIT UI
# =============================================================================

def main():
    """Main Streamlit application"""
    
    # Page config
    st.set_page_config(
        page_title="Menu Carbon Calculator",
        page_icon="🌱",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    
    # Initialize session state
    if "language" not in st.session_state:
        st.session_state.language = "tr"
    if "ingredients" not in st.session_state:
        st.session_state.ingredients = [
            {"id": "beef", "raw_weight_g": 200.0},
            {"id": "rice", "raw_weight_g": 60.0},
            {"id": "onion", "raw_weight_g": 20.0},
            {"id": "oil_sunflower", "raw_weight_g": 10.0},
        ]
    
    # Load data
    try:
        factors_df = load_factors_csv("data/factors.csv")
        EF_MAP, NAME_MAP, SYN_MAP, CATEGORY_MAP, SEASONALITY_MAP = build_factor_maps(
            factors_df, st.session_state.language
        )
        INGREDIENT_OPTIONS = sorted(list(EF_MAP.keys()))
    except Exception as e:
        st.error(f"❌ Failed to load data/factors.csv: {e}")
        st.stop()
    
    t = TRANSLATIONS.get(st.session_state.language, TRANSLATIONS["en"])
    
    # ==========================================================================
    # SIDEBAR
    # ==========================================================================
    with st.sidebar:
        st.image("https://via.placeholder.com/200x60?text=Commited", width=200)
        
        # Language selector
        st.subheader("🌐 Language / Dil")
        lang_options = {"tr": "🇹🇷 Türkçe", "en": "🇬🇧 English"}
        selected_lang = st.selectbox(
            "Select language",
            options=list(lang_options.keys()),
            format_func=lambda x: lang_options[x],
            index=0 if st.session_state.language == "tr" else 1,
            key="lang_select",
        )
        if selected_lang != st.session_state.language:
            st.session_state.language = selected_lang
            st.rerun()
        
        st.divider()
        
        # Data info
        st.subheader("📊 " + t["data_loaded"])
        st.success(f"✅ factors.csv ({len(factors_df)} " + ("malzeme" if st.session_state.language == "tr" else "ingredients") + ")")
        
        with st.expander("Malzeme Listesi" if st.session_state.language == "tr" else "Ingredient List"):
            st.dataframe(
                factors_df[["ingredient_id", "ingredient_name_tr" if "ingredient_name_tr" in factors_df.columns else "ingredient_name", "ef_gco2e_per_g", "category"]].head(20),
                use_container_width=True,
                height=300,
            )
        
        st.divider()
        
        # Methodology
        st.subheader("📖 " + t["methodology"])
        st.caption(METHODOLOGY_TITLE)
        
        if os.path.exists(METHODOLOGY_FILE):
            with open(METHODOLOGY_FILE, "rb") as f:
                st.download_button(
                    label="📄 Download Methodology (PDF)",
                    data=f,
                    file_name="Commited_Menu_Carbon_Methodology.pdf",
                    mime="application/pdf",
                )
        
        st.divider()
        
        # Settings
        st.subheader("⚙️ " + ("Ayarlar" if st.session_state.language == "tr" else "Settings"))
        
        region = st.selectbox(
            "Bölge / Region",
            options=["tr", "eu", "us", "global"],
            format_func=lambda x: {"tr": "🇹🇷 Türkiye", "eu": "🇪🇺 EU", "us": "🇺🇸 USA", "global": "🌍 Global"}[x],
            index=0,
        )
        
        apply_seasonality = st.checkbox(
            "Mevsimsel faktör uygula" if st.session_state.language == "tr" else "Apply seasonality",
            value=True,
        )
        
        current_season = get_current_season()
        season_labels = {
            "winter": t["season_winter"],
            "summer": t["season_summer"],
            "transition": t["season_transition"],
        }
        st.caption(f"📅 {season_labels.get(current_season, current_season)}")
        
        st.divider()
        
        # Status
        st.caption(f"App Version: {APP_VERSION}")
        if not QR_AVAILABLE:
            st.warning(t["qr_disabled"])
        if not PLOTLY_AVAILABLE:
            st.warning("📊 Plotly not available")
    
    # ==========================================================================
    # MAIN CONTENT
    # ==========================================================================
    
    st.title("🌱 " + t["app_title"])
    st.caption(t["app_subtitle"])
    
    # Partner Settings
    st.subheader("0️⃣ " + t["partner_settings"])
    col_p1, col_p2 = st.columns([1, 2])
    with col_p1:
        partner_slug = st.text_input(t["partner_slug"], value="demo_partner")
    with col_p2:
        certificate_base_url = st.text_input(
            t["certificate_url"],
            value="https://carbonkey.commited.app/cert/",
        )
    
    st.divider()
    
    # Recipe Basics
    st.subheader("1️⃣ " + t["recipe_basics"])
    col_r1, col_r2, col_r3 = st.columns([2, 1, 1])
    with col_r1:
        recipe_name = st.text_input(t["recipe_name"], value="Izgara Köfte + Pilav")
    with col_r2:
        portions = st.number_input(t["portions"], min_value=1, max_value=100, value=1)
    with col_r3:
        meal_type = st.selectbox(
            t["meal_type"],
            options=["breakfast", "lunch", "dinner"],
            format_func=lambda x: {"breakfast": "☀️ Kahvaltı/Breakfast", "lunch": "🌤️ Öğle/Lunch", "dinner": "🌙 Akşam/Dinner"}[x],
            index=1,
        )
    
    st.divider()
    
    # Ingredients
    st.subheader("2️⃣ " + t["ingredients"])
    
    for idx, ing in enumerate(st.session_state.ingredients):
        col1, col2, col3, col4 = st.columns([2, 2, 1, 1])
        
        current_id = str(ing.get("id", "")).strip().lower()
        if not current_id or current_id not in INGREDIENT_OPTIONS:
            current_id = INGREDIENT_OPTIONS[0]
            ing["id"] = current_id
        
        # Get used IDs by other rows
        used_by_others = set()
        for j, other in enumerate(st.session_state.ingredients):
            if j != idx:
                oid = str(other.get("id", "")).strip().lower()
                if oid:
                    used_by_others.add(oid)
        
        options_for_row = [x for x in INGREDIENT_OPTIONS if x not in used_by_others]
        if not options_for_row:
            options_for_row = [current_id]
        
        if current_id not in options_for_row:
            current_id = pick_first_available(used_by_others, INGREDIENT_OPTIONS)
            ing["id"] = current_id
        
        with col1:
            selected = st.selectbox(
                f"Malzeme #{idx + 1}" if st.session_state.language == "tr" else f"Ingredient #{idx + 1}",
                options=options_for_row,
                index=options_for_row.index(current_id) if current_id in options_for_row else 0,
                key=f"ing_id_{idx}",
                format_func=lambda x: f"{NAME_MAP.get(x, x)} ({x})",
            )
            ing["id"] = selected
        
        resolved_id = resolve_ingredient_id(ing["id"], SYN_MAP)
        auto_name = NAME_MAP.get(resolved_id, resolved_id)
        auto_ef = float(EF_MAP.get(resolved_id, 0.0))
        category = CATEGORY_MAP.get(resolved_id, "other")
        
        with col2:
            st.caption(f"Kategori / Category")
            cat_color = CATEGORY_COLORS.get(category, "#6b7280")
            st.markdown(f'<span style="background-color: {cat_color}; color: white; padding: 2px 8px; border-radius: 4px; font-size: 12px;">{category.upper()}</span>', unsafe_allow_html=True)
        
        with col3:
            weight = st.number_input(
                t["weight_g"],
                min_value=0.0,
                max_value=5000.0,
                value=float(ing.get("raw_weight_g", 0)),
                step=10.0,
                key=f"ing_weight_{idx}",
            )
            ing["raw_weight_g"] = weight
        
        with col4:
            st.caption("EF (g CO₂e/g)")
            st.write(f"**{auto_ef:.2f}**")
        
        ing["name"] = auto_name
        ing["emission_factor_g_per_g"] = auto_ef
    
    # Add/Remove buttons
    col_add, col_del = st.columns(2)
    with col_add:
        used = set(str(x.get("id", "")).strip().lower() for x in st.session_state.ingredients)
        all_used = len(used) >= len(INGREDIENT_OPTIONS)
        if st.button(t["add_ingredient"], disabled=all_used, use_container_width=True):
            new_id = pick_first_available(used, INGREDIENT_OPTIONS)
            st.session_state.ingredients.append({"id": new_id, "raw_weight_g": 0.0})
            st.rerun()
    with col_del:
        if st.button(t["remove_last"], disabled=len(st.session_state.ingredients) <= 1, use_container_width=True):
            st.session_state.ingredients.pop()
            st.rerun()
    
    st.divider()
    
    # Cooking
    st.subheader("3️⃣ " + t["cooking"])
    col_c1, col_c2, col_c3 = st.columns(3)
    with col_c1:
        energy_type = st.selectbox(
            t["energy_type"],
            options=list(ENERGY_FACTORS.keys()),
            format_func=lambda x: {"electricity": "⚡ Elektrik", "natural_gas": "🔥 Doğalgaz", "lpg": "🔵 LPG", "wood": "🪵 Odun"}[x],
            index=0,
        )
    with col_c2:
        power_kw = st.number_input(t["power_kw"], min_value=0.0, max_value=50.0, value=3.0, step=0.5)
    with col_c3:
        duration_min = st.number_input(t["duration_min"], min_value=0.0, max_value=480.0, value=12.0, step=1.0)
    
    st.divider()
    
    # Transport
    st.subheader("4️⃣ " + t["transport"])
    transport_enabled = st.checkbox(
        "Taşıma emisyonlarını dahil et" if st.session_state.language == "tr" else "Include transport emissions",
        value=True,
    )
    
    if transport_enabled:
        col_t1, col_t2 = st.columns(2)
        with col_t1:
            transport_mode = st.selectbox(
                t["transport_mode"],
                options=list(TRANSPORT_FACTORS.keys()),
                format_func=lambda x: {"road": "🚛 Karayolu", "rail": "🚂 Demiryolu", "sea": "🚢 Deniz", "air": "✈️ Hava"}[x],
                index=0,
            )
        with col_t2:
            transport_distance = st.number_input(t["distance_km"], min_value=0.0, max_value=50000.0, value=300.0, step=50.0)
    else:
        transport_mode = "road"
        transport_distance = 0.0
    
    st.divider()
    
    # Build payload
    payload = {
        "partner_slug": partner_slug,
        "name": recipe_name,
        "portions": int(portions),
        "meal_type": meal_type,
        "ingredients": st.session_state.ingredients,
        "cooking": {
            "energy_type": energy_type,
            "average_power_kw": float(power_kw),
            "duration_min": float(duration_min),
        },
        "transport": {
            "enabled": transport_enabled,
            "mode": transport_mode,
            "distance_km": float(transport_distance),
        },
        "methodology": {
            "title": METHODOLOGY_TITLE,
            "version": METHODOLOGY_VERSION,
            "date": METHODOLOGY_DATE,
        },
    }
    
    # ==========================================================================
    # BATCH MODE
    # ==========================================================================
    st.subheader("5️⃣ " + t["batch_mode"])
    
    with st.expander("📁 Toplu CSV Yükle" if st.session_state.language == "tr" else "📁 Upload Batch CSV"):
        st.caption("CSV sütunları: recipe_name, ingredient_id, weight_g (opsiyonel: portions, meal_type)")
        batch_file = st.file_uploader("Upload CSV", type=["csv"], key="batch_upload")
        
        if batch_file is not None:
            try:
                dfb = pd.read_csv(batch_file)
                
                with st.spinner("İşleniyor..." if st.session_state.language == "tr" else "Processing..."):
                    batch_result = batch_compute(
                        df=dfb,
                        ef_map=EF_MAP,
                        name_map=NAME_MAP,
                        syn_map=SYN_MAP,
                        seasonality_map=SEASONALITY_MAP,
                        default_cooking=payload["cooking"],
                        default_transport=payload["transport"],
                        partner_slug=partner_slug,
                        certificate_base_url=certificate_base_url,
                        region=region,
                        apply_seasonality=apply_seasonality,
                    )
                
                st.success(f"✅ {len(batch_result)} tarif işlendi!")
                
                # Color code by Klimato grade
                def color_grade(val):
                    colors = {"A": "#dcfce7", "B": "#fef9c3", "C": "#fed7aa", "D": "#fecaca", "E": "#fca5a5"}
                    return f'background-color: {colors.get(val, "white")}'
                
                styled_df = batch_result.style.applymap(color_grade, subset=["klimato_grade"])
                st.dataframe(styled_df, use_container_width=True)
                
                # Download buttons
                col_b1, col_b2 = st.columns(2)
                with col_b1:
                    csv_bytes = batch_result.to_csv(index=False).encode("utf-8")
                    st.download_button(
                        t["download_csv"],
                        data=csv_bytes,
                        file_name="menu_carbon_batch_results.csv",
                        mime="text/csv",
                        use_container_width=True,
                    )
                with col_b2:
                    xlsx_buf = BytesIO()
                    with pd.ExcelWriter(xlsx_buf, engine="openpyxl") as writer:
                        batch_result.to_excel(writer, index=False, sheet_name="results")
                        dfb.to_excel(writer, index=False, sheet_name="raw_input")
                    st.download_button(
                        t["download_xlsx"],
                        data=xlsx_buf.getvalue(),
                        file_name="menu_carbon_batch_results.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
                
            except Exception as e:
                st.error(f"Batch error: {e}")
    
    st.divider()
    
    # ==========================================================================
    # CALCULATE BUTTON
    # ==========================================================================
    if st.button("🧮 " + t["calculate"], type="primary", use_container_width=True):
        
        with st.spinner("Hesaplanıyor..." if st.session_state.language == "tr" else "Calculating..."):
            result = calculate(
                payload,
                region=region,
                apply_seasonality=apply_seasonality,
                seasonality_map=SEASONALITY_MAP,
            )
        
        menu_carbon_id = compute_menu_carbon_id(payload)
        certificate_url = (certificate_base_url.rstrip("/") + "/" + menu_carbon_id) if certificate_base_url.strip() else ""
        qr_text = certificate_url if certificate_url else f"{partner_slug}:{menu_carbon_id}"
        
        # Store results in session state for persistence
        st.session_state.last_result = result
        st.session_state.last_menu_id = menu_carbon_id
        st.session_state.last_cert_url = certificate_url
        st.session_state.last_qr_text = qr_text
        st.session_state.last_payload = payload
        
        st.success("✅ " + ("Hesaplama tamamlandı!" if st.session_state.language == "tr" else "Calculation complete!"))
        
        # ==========================================================================
        # RESULTS SECTION
        # ==========================================================================
        st.subheader("📊 " + t["results"])
        
        # Main metrics
        col_m1, col_m2, col_m3, col_m4, col_m5 = st.columns(5)
        with col_m1:
            st.metric(t["ingredients_emission"], f"{result['ingredient_emissions_gco2e']:.0f} g")
        with col_m2:
            st.metric(t["cooking_emission"], f"{result['cooking_emissions_gco2e']:.0f} g")
        with col_m3:
            st.metric(t["transport_emission"], f"{result['transport_emissions_gco2e']:.0f} g")
        with col_m4:
            st.metric(t["total_emission"], f"{result['total_gco2e']:.0f} g", delta=None)
        with col_m5:
            st.metric(t["per_portion"], f"{result['gco2e_per_portion']:.0f} g")
        
        # Klimato gauge and grade
        st.subheader(t["klimato_grade"])
        col_k1, col_k2 = st.columns([2, 1])
        
        with col_k1:
            if PLOTLY_AVAILABLE:
                gauge_fig = create_klimato_gauge(
                    result["klimato_grade"],
                    result["gco2e_per_portion"],
                    st.session_state.language,
                )
                if gauge_fig:
                    st.plotly_chart(gauge_fig, use_container_width=True)
        
        with col_k2:
            grade = result["klimato_grade"]
            color = result["klimato_color"]
            grade_text = t.get(f"klimato_{grade.lower()}", f"Grade {grade}")
            
            st.markdown(f"""
            <div style="
                text-align: center;
                padding: 30px;
                background: linear-gradient(135deg, {color}22, {color}44);
                border-radius: 16px;
                border: 3px solid {color};
            ">
                <div style="font-size: 72px; font-weight: bold; color: {color};">{grade}</div>
                <div style="font-size: 18px; color: #374151; margin-top: 10px;">{grade_text}</div>
            </div>
            """, unsafe_allow_html=True)
            
            # WRI compliance badge
            st.markdown("<br>", unsafe_allow_html=True)
            if result["wri_compliant"]:
                st.success(t["wri_compliant"])
            else:
                st.warning(f"{t['wri_not_compliant']} ({result['wri_percentage']:.0f}%)")
        
        # ==========================================================================
        # INSIGHTS SECTION
        # ==========================================================================
        st.subheader("🌍 " + t["insights"])
        
        insights = result["insights"]
        col_i1, col_i2, col_i3 = st.columns(3)
        
        with col_i1:
            st.metric(t["car_km"], f"{insights['car_km']:.1f} km")
            st.caption("≈ araba yolculuğu" if st.session_state.language == "tr" else "≈ car journey")
        
        with col_i2:
            st.metric(t["tree_absorption"], f"{insights['tree_minutes']:.0f} dk")
            st.caption("≈ ağaç absorpsiyonu" if st.session_state.language == "tr" else "≈ tree absorption")
        
        with col_i3:
            st.metric(t["wwf_target"], f"%{insights['wwf_target_percent']:.0f}")
            st.caption("WWF 500g hedefine göre" if st.session_state.language == "tr" else "vs WWF 500g target")
        
        col_i4, col_i5, col_i6 = st.columns(3)
        
        with col_i4:
            st.metric(t["smartphone_days"], f"{insights['smartphone_days']:.0f} gün")
            st.caption("≈ telefon şarjı" if st.session_state.language == "tr" else "≈ phone charging")
        
        with col_i5:
            st.metric(t["lightbulb_hours"], f"{insights['lightbulb_hours']:.0f} saat")
            st.caption("≈ 100W ampul" if st.session_state.language == "tr" else "≈ 100W lightbulb")
        
        with col_i6:
            st.metric(t["uk_average"], f"%{insights['uk_average_percent']:.0f}")
            st.caption("UK ortalamasına göre" if st.session_state.language == "tr" else "vs UK average")
        
        # ==========================================================================
        # BREAKDOWN CHARTS
        # ==========================================================================
        st.subheader("📈 " + t["breakdown"])
        
        if PLOTLY_AVAILABLE:
            col_ch1, col_ch2 = st.columns(2)
            
            with col_ch1:
                pie_fig = create_emission_breakdown_pie(
                    result["ingredient_details"],
                    result["cooking_emissions_gco2e"],
                    result["transport_emissions_gco2e"],
                    st.session_state.language,
                )
                if pie_fig:
                    st.plotly_chart(pie_fig, use_container_width=True)
            
            with col_ch2:
                bar_fig = create_ingredient_breakdown_bar(
                    result["ingredient_details"],
                    CATEGORY_MAP,
                    st.session_state.language,
                )
                if bar_fig:
                    st.plotly_chart(bar_fig, use_container_width=True)
            
            # Comparison chart
            comp_fig = create_comparison_chart(
                result["gco2e_per_portion"],
                st.session_state.language,
            )
            if comp_fig:
                st.plotly_chart(comp_fig, use_container_width=True)
        else:
            st.info("📊 Install Plotly for charts: pip install plotly")
        
        # ==========================================================================
        # ALTERNATIVES SECTION
        # ==========================================================================
        st.subheader("💡 " + t["alternatives"])
        
        alternatives = suggest_alternatives(
            st.session_state.ingredients,
            EF_MAP,
            NAME_MAP,
        )
        
        if alternatives:
            for alt in alternatives:
                col_a1, col_a2, col_a3 = st.columns([2, 2, 1])
                with col_a1:
                    st.write(f"**{alt['original_name']}** ({alt['original_ef']:.1f} g CO₂e/g)")
                with col_a2:
                    st.write(f"→ **{alt['alternative_name']}** ({alt['alternative_ef']:.1f} g CO₂e/g)")
                with col_a3:
                    st.success(f"🌱 -{alt['reduction_percent']}%")
        else:
            st.info("✅ " + ("Mevcut malzemeler zaten düşük karbonlu!" if st.session_state.language == "tr" else "Current ingredients are already low-carbon!"))
        
        # ==========================================================================
        # CERTIFICATE SECTION
        # ==========================================================================
        st.subheader("📜 " + t["certificate"])
        
        col_cert1, col_cert2 = st.columns([2, 1])
        
        with col_cert1:
            st.write(f"**Partner:** {partner_slug}")
            st.write(f"**Menu Carbon ID:** `{menu_carbon_id}`")
            if certificate_url:
                st.write(f"**Certificate URL:** [{certificate_url}]({certificate_url})")
            
            st.markdown(f"**{t['methodology']}:** {METHODOLOGY_TITLE}")
            
            if apply_seasonality and result.get("season_applied"):
                st.info(f"📅 {t['seasonality_applied']}: {season_labels.get(result['season_applied'], result['season_applied'])}")
        
        with col_cert2:
            if QR_AVAILABLE and qr_text:
                qr_bytes = make_qr_png_bytes(qr_text, size_px=200)
                if qr_bytes:
                    st.image(qr_bytes, caption=t["scan_for_details"], width=200)
        
        # ==========================================================================
        # EXPORT SECTION
        # ==========================================================================
        st.subheader("📥 Export")
        
        col_ex1, col_ex2, col_ex3, col_ex4 = st.columns(4)
        
        # Summary CSV
        summary_row = {
            "partner_slug": partner_slug,
            "recipe_name": recipe_name,
            "menu_carbon_id": menu_carbon_id,
            "certificate_url": certificate_url,
            "total_gco2e": result["total_gco2e"],
            "gco2e_per_portion": result["gco2e_per_portion"],
            "klimato_grade": result["klimato_grade"],
            "label_simple": result["label_simple"],
            "wri_compliant": result["wri_compliant"],
            "ingredients_gco2e": result["ingredient_emissions_gco2e"],
            "cooking_gco2e": result["cooking_emissions_gco2e"],
            "transport_gco2e": result["transport_emissions_gco2e"],
            "region": region,
            "season": result.get("season_applied", ""),
            "methodology_version": METHODOLOGY_VERSION,
        }
        
        with col_ex1:
            csv_bytes = pd.DataFrame([summary_row]).to_csv(index=False).encode("utf-8")
            st.download_button(
                t["download_csv"],
                data=csv_bytes,
                file_name="menu_carbon_summary.csv",
                mime="text/csv",
                use_container_width=True,
            )
        
        with col_ex2:
            png_bytes = build_label_png_bytes(
                recipe_name=recipe_name,
                total_gco2e=result["gco2e_per_portion"],
                klimato_grade=result["klimato_grade"],
                methodology_title=METHODOLOGY_TITLE,
                qr_text=qr_text,
                language=st.session_state.language,
            )
            st.download_button(
                t["download_png"],
                data=png_bytes,
                file_name="menu_carbon_label.png",
                mime="image/png",
                use_container_width=True,
            )
        
        with col_ex3:
            pdf_bytes = build_label_pdf_bytes(
                recipe_name=recipe_name,
                total_gco2e=result["gco2e_per_portion"],
                klimato_grade=result["klimato_grade"],
                methodology_title=METHODOLOGY_TITLE,
                qr_text=qr_text,
                language=st.session_state.language,
            )
            st.download_button(
                t["download_pdf"],
                data=pdf_bytes,
                file_name="menu_carbon_label.pdf",
                mime="application/pdf",
                use_container_width=True,
            )
        
        with col_ex4:
            api_envelope = {
                "menu_carbon_id": menu_carbon_id,
                "certificate_url": certificate_url,
                "payload": payload,
                "result": result,
                "app_version": APP_VERSION,
                "methodology_version": METHODOLOGY_VERSION,
            }
            json_str = json.dumps(api_envelope, indent=2, ensure_ascii=False, default=str)
            st.download_button(
                t["download_json"],
                data=json_str,
                file_name="menu_carbon_export.json",
                mime="application/json",
                use_container_width=True,
            )
        
        # Technical JSON preview
        with st.expander("🔧 Technical JSON Export"):
            st.json(api_envelope)
    
    st.divider()
    
    # ==========================================================================
    # API TEST SECTION
    # ==========================================================================
    st.subheader("6️⃣ " + t["api_test"])
    
    with st.expander("🔌 API Payload Test"):
        sample_payload = {
            "partner_slug": "demo_partner",
            "name": "Sample Recipe",
            "portions": 1,
            "meal_type": "lunch",
            "ingredients": [
                {"id": "beef", "raw_weight_g": 200},
                {"id": "rice", "raw_weight_g": 60},
            ],
            "cooking": {"energy_type": "electricity", "average_power_kw": 3.0, "duration_min": 12.0},
            "transport": {"enabled": True, "mode": "road", "distance_km": 300.0},
        }
        
        raw_json = st.text_area(
            "Payload JSON",
            value=json.dumps(sample_payload, ensure_ascii=False, indent=2),
            height=250,
        )
        
        if st.button("🧪 Compute from JSON"):
            try:
                pld = json.loads(raw_json)
                
                # Resolve ingredients
                ingr2 = []
                for it in pld.get("ingredients", []):
                    rid = resolve_ingredient_id(it.get("id", ""), SYN_MAP)
                    w = float(it.get("raw_weight_g", 0.0))
                    ef = it.get("emission_factor_g_per_g")
                    if ef is None:
                        ef = float(EF_MAP.get(rid, 0.0))
                    ingr2.append({
                        "id": rid,
                        "name": NAME_MAP.get(rid, rid),
                        "raw_weight_g": w,
                        "emission_factor_g_per_g": float(ef),
                    })
                pld["ingredients"] = ingr2
                
                res = calculate(pld, region=region, apply_seasonality=apply_seasonality, seasonality_map=SEASONALITY_MAP)
                mid = compute_menu_carbon_id(pld)
                
                st.success(f"✅ OK. menu_carbon_id = {mid}")
                st.json({"menu_carbon_id": mid, "result": res})
                
            except Exception as e:
                st.error(f"❌ JSON compute error: {e}")
    
    # Footer
    st.divider()
    st.caption(f"🌱 {t['powered_by']} | Version {APP_VERSION} | Methodology {METHODOLOGY_VERSION}")


# =============================================================================
# ENTRY POINT
# =============================================================================

if __name__ == "__main__":
    main()
