# api.py - FastAPI REST API for Menu Carbon Calculator
# Run: uvicorn api:app --reload --port 8000
# Docs: http://localhost:8000/docs

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, validator
from typing import List, Optional, Dict, Any
import pandas as pd
import hashlib
import json
from datetime import datetime

# =============================================================================
# APP CONFIGURATION
# =============================================================================

app = FastAPI(
    title="Menu Carbon API",
    description="Calculate carbon footprint of food recipes based on LCA data",
    version="2.0.0",
    contact={
        "name": "Commited",
        "url": "https://commited.app",
    },
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# =============================================================================
# CONSTANTS
# =============================================================================

ENERGY_FACTORS = {
    "electricity": {"tr": 420.0, "eu": 250.0, "us": 380.0, "global": 475.0},
    "natural_gas": {"tr": 200.0, "eu": 200.0, "us": 200.0, "global": 200.0},
    "lpg": {"tr": 230.0, "eu": 230.0, "us": 230.0, "global": 230.0},
    "wood": {"tr": 30.0, "eu": 30.0, "us": 30.0, "global": 30.0},
}

TRANSPORT_FACTORS = {
    "road": 62.0,
    "rail": 22.0,
    "sea": 16.0,
    "air": 602.0,
}

KLIMATO_THRESHOLDS = {
    "A": (0, 400),
    "B": (400, 900),
    "C": (900, 1800),
    "D": (1800, 2600),
    "E": (2600, float('inf')),
}

WRI_COOL_FOOD = {
    "breakfast": 3590,
    "lunch": 5380,
    "dinner": 5380,
}

WWF_TARGET = 500

# =============================================================================
# LOAD DATA
# =============================================================================

def load_factors():
    """Load emission factors from CSV"""
    try:
        df = pd.read_csv("data/factors.csv")
        df.columns = [c.strip() for c in df.columns]
        
        ef_map = {}
        name_map = {}
        syn_map = {}
        category_map = {}
        seasonality_map = {}
        
        for _, row in df.iterrows():
            ing_id = str(row["ingredient_id"]).strip().lower()
            if not ing_id:
                continue
            
            ef_map[ing_id] = float(row["ef_gco2e_per_g"])
            name_map[ing_id] = str(row.get("ingredient_name_tr", row["ingredient_name"])).strip()
            syn_map[ing_id] = ing_id
            
            if "category" in df.columns and pd.notna(row.get("category")):
                category_map[ing_id] = str(row["category"]).strip().lower()
            
            if "seasonality_winter_factor" in df.columns and pd.notna(row.get("seasonality_winter_factor")):
                seasonality_map[ing_id] = float(row["seasonality_winter_factor"])
            
            if "synonyms" in df.columns and pd.notna(row.get("synonyms")):
                for token in str(row["synonyms"]).split(","):
                    t = token.strip().lower()
                    if t:
                        syn_map[t] = ing_id
        
        return ef_map, name_map, syn_map, category_map, seasonality_map
    
    except Exception as e:
        print(f"Warning: Could not load factors.csv: {e}")
        return {}, {}, {}, {}, {}

EF_MAP, NAME_MAP, SYN_MAP, CATEGORY_MAP, SEASONALITY_MAP = load_factors()

# =============================================================================
# PYDANTIC MODELS
# =============================================================================

class IngredientInput(BaseModel):
    id: str
    raw_weight_g: float = Field(ge=0, le=10000)
    emission_factor_g_per_g: Optional[float] = None
    name: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "beef",
                "raw_weight_g": 200,
            }
        }


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
    
    class Config:
        json_schema_extra = {
            "example": {
                "name": "Grilled Beef Köfte + Rice",
                "portions": 1,
                "meal_type": "lunch",
                "ingredients": [
                    {"id": "beef", "raw_weight_g": 200},
                    {"id": "rice", "raw_weight_g": 60},
                    {"id": "onion", "raw_weight_g": 20},
                ],
                "cooking": {
                    "energy_type": "electricity",
                    "average_power_kw": 3.0,
                    "duration_min": 12.0,
                },
                "transport": {
                    "enabled": True,
                    "mode": "road",
                    "distance_km": 300,
                },
            }
        }


class CalculationResult(BaseModel):
    menu_carbon_id: str
    ingredient_emissions_gco2e: float
    cooking_emissions_gco2e: float
    transport_emissions_gco2e: float
    total_gco2e: float
    gco2e_per_portion: float
    portions: int
    klimato_grade: str
    klimato_color: str
    label_simple: str
    wri_compliant: bool
    wri_threshold: float
    wri_percentage: float
    insights: Dict[str, Any]


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def get_current_season() -> str:
    month = datetime.now().month
    if month in [12, 1, 2]:
        return "winter"
    elif month in [6, 7, 8]:
        return "summer"
    return "transition"


def get_season_factor(ingredient_id: str, season: str) -> float:
    if season == "summer":
        return 1.0
    factor = SEASONALITY_MAP.get(ingredient_id, 1.0)
    if season == "winter":
        return factor
    return 1.0 + (factor - 1.0) * 0.5


def classify_simple(total_g: float) -> str:
    if total_g < 500:
        return "LOW"
    if total_g <= 1500:
        return "MEDIUM"
    return "HIGH"


def classify_klimato(total_g: float) -> str:
    for grade, (low, high) in KLIMATO_THRESHOLDS.items():
        if low <= total_g < high:
            return grade
    return "E"


def get_klimato_color(grade: str) -> str:
    colors = {"A": "#22c55e", "B": "#84cc16", "C": "#eab308", "D": "#f97316", "E": "#ef4444"}
    return colors.get(grade, "#6b7280")


def resolve_ingredient(user_id: str) -> str:
    t = str(user_id or "").strip().lower()
    if not t:
        return ""
    if t in SYN_MAP:
        return SYN_MAP[t]
    t2 = "_".join(t.split())
    return SYN_MAP.get(t2, t)


def compute_menu_carbon_id(payload: dict) -> str:
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


def generate_insights(total_gco2e: float) -> dict:
    return {
        "car_km": round(total_gco2e / 120, 1),
        "lightbulb_hours": round(total_gco2e / 42, 1),
        "smartphone_days": round(total_gco2e / 8, 1),
        "tree_minutes": round(total_gco2e / 0.02, 0),
        "uk_average_percent": round((total_gco2e / 1600) * 100, 0),
        "wwf_target_percent": round((total_gco2e / WWF_TARGET) * 100, 0),
    }


# =============================================================================
# API ENDPOINTS
# =============================================================================

@app.get("/")
async def root():
    """API health check"""
    return {
        "status": "healthy",
        "api": "Menu Carbon API",
        "version": "2.0.0",
        "ingredients_loaded": len(EF_MAP),
    }


@app.get("/ingredients")
async def list_ingredients(
    category: Optional[str] = Query(None, description="Filter by category"),
    limit: int = Query(100, ge=1, le=500),
):
    """List all available ingredients with their emission factors"""
    result = []
    for ing_id, ef in EF_MAP.items():
        cat = CATEGORY_MAP.get(ing_id, "other")
        if category and cat != category.lower():
            continue
        result.append({
            "id": ing_id,
            "name": NAME_MAP.get(ing_id, ing_id),
            "emission_factor_g_per_g": ef,
            "category": cat,
            "seasonality_winter_factor": SEASONALITY_MAP.get(ing_id, 1.0),
        })
    
    return {"ingredients": result[:limit], "total": len(result)}


@app.get("/ingredients/{ingredient_id}")
async def get_ingredient(ingredient_id: str):
    """Get details for a specific ingredient"""
    resolved = resolve_ingredient(ingredient_id)
    if resolved not in EF_MAP:
        raise HTTPException(status_code=404, detail=f"Ingredient '{ingredient_id}' not found")
    
    return {
        "id": resolved,
        "name": NAME_MAP.get(resolved, resolved),
        "emission_factor_g_per_g": EF_MAP[resolved],
        "category": CATEGORY_MAP.get(resolved, "other"),
        "seasonality_winter_factor": SEASONALITY_MAP.get(resolved, 1.0),
    }


@app.get("/categories")
async def list_categories():
    """List all ingredient categories"""
    categories = set(CATEGORY_MAP.values())
    result = []
    for cat in sorted(categories):
        count = sum(1 for c in CATEGORY_MAP.values() if c == cat)
        result.append({"category": cat, "count": count})
    return {"categories": result}


@app.post("/calculate", response_model=CalculationResult)
async def calculate(
    payload: RecipePayload,
    region: str = Query("tr", description="Region for energy factors"),
    apply_seasonality: bool = Query(True, description="Apply seasonal adjustments"),
):
    """Calculate carbon footprint for a recipe"""
    
    season = get_current_season()
    
    # Process ingredients
    ingredient_emissions = 0.0
    total_weight_g = 0.0
    processed_ingredients = []
    
    for ing in payload.ingredients:
        resolved_id = resolve_ingredient(ing.id)
        
        # Get emission factor
        if ing.emission_factor_g_per_g is not None:
            ef = ing.emission_factor_g_per_g
        elif resolved_id in EF_MAP:
            ef = EF_MAP[resolved_id]
        else:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown ingredient '{ing.id}' and no emission_factor provided"
            )
        
        # Apply seasonality
        if apply_seasonality:
            season_factor = get_season_factor(resolved_id, season)
            ef_adjusted = ef * season_factor
        else:
            ef_adjusted = ef
        
        emission = ing.raw_weight_g * ef_adjusted
        ingredient_emissions += emission
        total_weight_g += ing.raw_weight_g
        
        processed_ingredients.append({
            "id": resolved_id,
            "name": NAME_MAP.get(resolved_id, resolved_id),
            "weight_g": ing.raw_weight_g,
            "ef": ef_adjusted,
            "emission": round(emission, 2),
        })
    
    # Cooking emissions
    duration_hours = payload.cooking.duration_min / 60.0
    kwh = payload.cooking.average_power_kw * duration_hours
    energy_factor = ENERGY_FACTORS.get(payload.cooking.energy_type, {}).get(region, 420.0)
    cooking_emissions = kwh * energy_factor
    
    # Transport emissions
    transport_emissions = 0.0
    if payload.transport.enabled:
        total_weight_ton = total_weight_g / 1_000_000
        tf = TRANSPORT_FACTORS.get(payload.transport.mode, 62.0)
        transport_emissions = total_weight_ton * payload.transport.distance_km * tf
    
    # Totals
    total = ingredient_emissions + cooking_emissions + transport_emissions
    per_portion = total / payload.portions
    
    # Classifications
    simple_label = classify_simple(per_portion)
    klimato_grade = classify_klimato(per_portion)
    
    # WRI check
    wri_threshold = WRI_COOL_FOOD.get(payload.meal_type, 5380)
    wri_compliant = per_portion <= wri_threshold
    
    # Menu ID
    payload_dict = payload.dict()
    for i, ing in enumerate(payload_dict["ingredients"]):
        ing["emission_factor_g_per_g"] = processed_ingredients[i]["ef"]
    menu_id = compute_menu_carbon_id(payload_dict)
    
    return CalculationResult(
        menu_carbon_id=menu_id,
        ingredient_emissions_gco2e=round(ingredient_emissions, 2),
        cooking_emissions_gco2e=round(cooking_emissions, 2),
        transport_emissions_gco2e=round(transport_emissions, 2),
        total_gco2e=round(total, 2),
        gco2e_per_portion=round(per_portion, 2),
        portions=payload.portions,
        klimato_grade=klimato_grade,
        klimato_color=get_klimato_color(klimato_grade),
        label_simple=simple_label,
        wri_compliant=wri_compliant,
        wri_threshold=wri_threshold,
        wri_percentage=round((per_portion / wri_threshold) * 100, 1),
        insights=generate_insights(per_portion),
    )


@app.get("/thresholds")
async def get_thresholds():
    """Get all threshold values used for classification"""
    return {
        "simple": {
            "low": {"max": 500, "label": "LOW", "color": "#22c55e"},
            "medium": {"min": 500, "max": 1500, "label": "MEDIUM", "color": "#eab308"},
            "high": {"min": 1500, "label": "HIGH", "color": "#ef4444"},
        },
        "klimato": {
            grade: {
                "min": low,
                "max": high if high != float('inf') else None,
                "color": get_klimato_color(grade),
            }
            for grade, (low, high) in KLIMATO_THRESHOLDS.items()
        },
        "wri_cool_food": WRI_COOL_FOOD,
        "wwf_target": WWF_TARGET,
    }


@app.get("/energy-factors")
async def get_energy_factors():
    """Get energy emission factors by type and region"""
    return ENERGY_FACTORS


@app.get("/transport-factors")
async def get_transport_factors():
    """Get transport emission factors by mode"""
    return TRANSPORT_FACTORS


# =============================================================================
# RUN
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
