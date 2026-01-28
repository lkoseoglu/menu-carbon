# database.py - Database models and operations
# Uses SQLite for simplicity, can be migrated to PostgreSQL

import sqlite3
import json
from datetime import datetime
from typing import Optional, List, Dict, Any
from dataclasses import dataclass, asdict
from pathlib import Path
import hashlib
import os

# Database path
DB_PATH = Path("data/menu_carbon.db")


def get_connection() -> sqlite3.Connection:
    """Get database connection with row factory"""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_database():
    """Initialize database tables"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Users table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            name TEXT,
            company TEXT,
            role TEXT DEFAULT 'user',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_login TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    """)
    
    # Partners table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS partners (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            logo_url TEXT,
            website TEXT,
            contact_email TEXT,
            subscription_tier TEXT DEFAULT 'free',
            api_key TEXT UNIQUE,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_active BOOLEAN DEFAULT 1
        )
    """)
    
    # Recipes table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS recipes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            menu_carbon_id TEXT UNIQUE NOT NULL,
            partner_id INTEGER,
            user_id INTEGER,
            name TEXT NOT NULL,
            description TEXT,
            category TEXT,
            cuisine TEXT,
            portions INTEGER DEFAULT 1,
            meal_type TEXT DEFAULT 'lunch',
            ingredients_json TEXT NOT NULL,
            cooking_json TEXT,
            transport_json TEXT,
            total_gco2e REAL,
            gco2e_per_portion REAL,
            klimato_grade TEXT,
            wri_compliant BOOLEAN,
            is_optimized BOOLEAN DEFAULT 0,
            original_recipe_id INTEGER,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            is_public BOOLEAN DEFAULT 0,
            view_count INTEGER DEFAULT 0,
            FOREIGN KEY (partner_id) REFERENCES partners(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (original_recipe_id) REFERENCES recipes(id)
        )
    """)
    
    # Calculations history table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS calculations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER,
            user_id INTEGER,
            partner_id INTEGER,
            payload_json TEXT NOT NULL,
            result_json TEXT NOT NULL,
            region TEXT DEFAULT 'tr',
            season TEXT,
            apply_seasonality BOOLEAN DEFAULT 1,
            calculated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (recipe_id) REFERENCES recipes(id),
            FOREIGN KEY (user_id) REFERENCES users(id),
            FOREIGN KEY (partner_id) REFERENCES partners(id)
        )
    """)
    
    # AI Optimization suggestions table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS ai_optimizations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            recipe_id INTEGER NOT NULL,
            original_gco2e REAL,
            optimized_gco2e REAL,
            reduction_percent REAL,
            suggestions_json TEXT,
            optimized_recipe_json TEXT,
            ai_model TEXT,
            ai_response_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            accepted BOOLEAN DEFAULT 0,
            FOREIGN KEY (recipe_id) REFERENCES recipes(id)
        )
    """)
    
    # Analytics events table
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS analytics_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            partner_id INTEGER,
            user_id INTEGER,
            event_type TEXT NOT NULL,
            event_data_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (partner_id) REFERENCES partners(id),
            FOREIGN KEY (user_id) REFERENCES users(id)
        )
    """)
    
    # Create indexes
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recipes_partner ON recipes(partner_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recipes_klimato ON recipes(klimato_grade)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_recipes_created ON recipes(created_at)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_calculations_partner ON calculations(partner_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_analytics_partner ON analytics_events(partner_id)")
    cursor.execute("CREATE INDEX IF NOT EXISTS idx_analytics_type ON analytics_events(event_type)")
    
    conn.commit()
    conn.close()
    
    print("✅ Database initialized successfully")


# =============================================================================
# USER OPERATIONS
# =============================================================================

def hash_password(password: str) -> str:
    """Hash password with salt"""
    salt = os.environ.get("PASSWORD_SALT", "menu_carbon_salt_2024")
    return hashlib.sha256(f"{password}{salt}".encode()).hexdigest()


def create_user(email: str, password: str, name: str = None, company: str = None, role: str = "user") -> Optional[int]:
    """Create a new user"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO users (email, password_hash, name, company, role)
            VALUES (?, ?, ?, ?, ?)
        """, (email.lower(), hash_password(password), name, company, role))
        conn.commit()
        user_id = cursor.lastrowid
        return user_id
    except sqlite3.IntegrityError:
        return None  # Email already exists
    finally:
        conn.close()


def authenticate_user(email: str, password: str) -> Optional[Dict]:
    """Authenticate user and return user data"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT * FROM users 
        WHERE email = ? AND password_hash = ? AND is_active = 1
    """, (email.lower(), hash_password(password)))
    
    row = cursor.fetchone()
    
    if row:
        # Update last login
        cursor.execute("UPDATE users SET last_login = ? WHERE id = ?", 
                      (datetime.now(), row["id"]))
        conn.commit()
        user = dict(row)
        conn.close()
        return user
    
    conn.close()
    return None


def get_user_by_id(user_id: int) -> Optional[Dict]:
    """Get user by ID"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# =============================================================================
# PARTNER OPERATIONS
# =============================================================================

def create_partner(slug: str, name: str, **kwargs) -> Optional[int]:
    """Create a new partner"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Generate API key
    api_key = hashlib.sha256(f"{slug}{datetime.now().isoformat()}".encode()).hexdigest()[:32]
    
    try:
        cursor.execute("""
            INSERT INTO partners (slug, name, logo_url, website, contact_email, subscription_tier, api_key)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (
            slug.lower(),
            name,
            kwargs.get("logo_url"),
            kwargs.get("website"),
            kwargs.get("contact_email"),
            kwargs.get("subscription_tier", "free"),
            api_key
        ))
        conn.commit()
        partner_id = cursor.lastrowid
        return partner_id
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_partner_by_slug(slug: str) -> Optional[Dict]:
    """Get partner by slug"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM partners WHERE slug = ? AND is_active = 1", (slug.lower(),))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


def get_partner_by_api_key(api_key: str) -> Optional[Dict]:
    """Get partner by API key"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM partners WHERE api_key = ? AND is_active = 1", (api_key,))
    row = cursor.fetchone()
    conn.close()
    return dict(row) if row else None


# =============================================================================
# RECIPE OPERATIONS
# =============================================================================

def save_recipe(
    menu_carbon_id: str,
    name: str,
    ingredients: List[Dict],
    cooking: Dict,
    transport: Dict,
    result: Dict,
    partner_id: int = None,
    user_id: int = None,
    **kwargs
) -> Optional[int]:
    """Save a recipe to database"""
    conn = get_connection()
    cursor = conn.cursor()
    
    try:
        cursor.execute("""
            INSERT INTO recipes (
                menu_carbon_id, partner_id, user_id, name, description, category, cuisine,
                portions, meal_type, ingredients_json, cooking_json, transport_json,
                total_gco2e, gco2e_per_portion, klimato_grade, wri_compliant, is_public
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            menu_carbon_id,
            partner_id,
            user_id,
            name,
            kwargs.get("description"),
            kwargs.get("category"),
            kwargs.get("cuisine"),
            result.get("portions", 1),
            kwargs.get("meal_type", "lunch"),
            json.dumps(ingredients, ensure_ascii=False),
            json.dumps(cooking, ensure_ascii=False),
            json.dumps(transport, ensure_ascii=False),
            result.get("total_gco2e"),
            result.get("gco2e_per_portion"),
            result.get("klimato_grade"),
            result.get("wri_compliant"),
            kwargs.get("is_public", False)
        ))
        conn.commit()
        recipe_id = cursor.lastrowid
        return recipe_id
    except sqlite3.IntegrityError:
        # Recipe already exists, update it
        cursor.execute("""
            UPDATE recipes SET
                name = ?, ingredients_json = ?, cooking_json = ?, transport_json = ?,
                total_gco2e = ?, gco2e_per_portion = ?, klimato_grade = ?, wri_compliant = ?,
                updated_at = ?
            WHERE menu_carbon_id = ?
        """, (
            name,
            json.dumps(ingredients, ensure_ascii=False),
            json.dumps(cooking, ensure_ascii=False),
            json.dumps(transport, ensure_ascii=False),
            result.get("total_gco2e"),
            result.get("gco2e_per_portion"),
            result.get("klimato_grade"),
            result.get("wri_compliant"),
            datetime.now(),
            menu_carbon_id
        ))
        conn.commit()
        cursor.execute("SELECT id FROM recipes WHERE menu_carbon_id = ?", (menu_carbon_id,))
        row = cursor.fetchone()
        return row["id"] if row else None
    finally:
        conn.close()


def get_recipe_by_id(recipe_id: int) -> Optional[Dict]:
    """Get recipe by ID"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM recipes WHERE id = ?", (recipe_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        recipe = dict(row)
        recipe["ingredients"] = json.loads(recipe["ingredients_json"])
        recipe["cooking"] = json.loads(recipe["cooking_json"]) if recipe["cooking_json"] else {}
        recipe["transport"] = json.loads(recipe["transport_json"]) if recipe["transport_json"] else {}
        return recipe
    return None


def get_recipes_by_partner(partner_id: int, limit: int = 100, offset: int = 0) -> List[Dict]:
    """Get all recipes for a partner"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM recipes 
        WHERE partner_id = ? 
        ORDER BY created_at DESC 
        LIMIT ? OFFSET ?
    """, (partner_id, limit, offset))
    rows = cursor.fetchall()
    conn.close()
    
    recipes = []
    for row in rows:
        recipe = dict(row)
        recipe["ingredients"] = json.loads(recipe["ingredients_json"])
        recipes.append(recipe)
    return recipes


def get_recipes_by_user(user_id: int, limit: int = 100) -> List[Dict]:
    """Get all recipes for a user"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM recipes 
        WHERE user_id = ? 
        ORDER BY created_at DESC 
        LIMIT ?
    """, (user_id, limit))
    rows = cursor.fetchall()
    conn.close()
    
    recipes = []
    for row in rows:
        recipe = dict(row)
        recipe["ingredients"] = json.loads(recipe["ingredients_json"])
        recipes.append(recipe)
    return recipes


def search_recipes(query: str, limit: int = 50) -> List[Dict]:
    """Search recipes by name"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM recipes 
        WHERE name LIKE ? AND is_public = 1
        ORDER BY view_count DESC 
        LIMIT ?
    """, (f"%{query}%", limit))
    rows = cursor.fetchall()
    conn.close()
    return [dict(row) for row in rows]


# =============================================================================
# CALCULATION HISTORY
# =============================================================================

def save_calculation(
    payload: Dict,
    result: Dict,
    recipe_id: int = None,
    user_id: int = None,
    partner_id: int = None,
    region: str = "tr",
    season: str = None,
    apply_seasonality: bool = True
) -> int:
    """Save calculation to history"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO calculations (
            recipe_id, user_id, partner_id, payload_json, result_json,
            region, season, apply_seasonality
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        recipe_id,
        user_id,
        partner_id,
        json.dumps(payload, ensure_ascii=False),
        json.dumps(result, ensure_ascii=False, default=str),
        region,
        season,
        apply_seasonality
    ))
    conn.commit()
    calc_id = cursor.lastrowid
    conn.close()
    return calc_id


def get_calculation_history(partner_id: int = None, user_id: int = None, limit: int = 100) -> List[Dict]:
    """Get calculation history"""
    conn = get_connection()
    cursor = conn.cursor()
    
    if partner_id:
        cursor.execute("""
            SELECT c.*, r.name as recipe_name 
            FROM calculations c
            LEFT JOIN recipes r ON c.recipe_id = r.id
            WHERE c.partner_id = ?
            ORDER BY c.calculated_at DESC
            LIMIT ?
        """, (partner_id, limit))
    elif user_id:
        cursor.execute("""
            SELECT c.*, r.name as recipe_name 
            FROM calculations c
            LEFT JOIN recipes r ON c.recipe_id = r.id
            WHERE c.user_id = ?
            ORDER BY c.calculated_at DESC
            LIMIT ?
        """, (user_id, limit))
    else:
        cursor.execute("""
            SELECT c.*, r.name as recipe_name 
            FROM calculations c
            LEFT JOIN recipes r ON c.recipe_id = r.id
            ORDER BY c.calculated_at DESC
            LIMIT ?
        """, (limit,))
    
    rows = cursor.fetchall()
    conn.close()
    
    history = []
    for row in rows:
        calc = dict(row)
        calc["payload"] = json.loads(calc["payload_json"])
        calc["result"] = json.loads(calc["result_json"])
        history.append(calc)
    return history


# =============================================================================
# AI OPTIMIZATION
# =============================================================================

def save_ai_optimization(
    recipe_id: int,
    original_gco2e: float,
    optimized_gco2e: float,
    suggestions: List[Dict],
    optimized_recipe: Dict,
    ai_model: str,
    ai_response: Dict
) -> int:
    """Save AI optimization result"""
    conn = get_connection()
    cursor = conn.cursor()
    
    reduction = ((original_gco2e - optimized_gco2e) / original_gco2e) * 100 if original_gco2e > 0 else 0
    
    cursor.execute("""
        INSERT INTO ai_optimizations (
            recipe_id, original_gco2e, optimized_gco2e, reduction_percent,
            suggestions_json, optimized_recipe_json, ai_model, ai_response_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        recipe_id,
        original_gco2e,
        optimized_gco2e,
        reduction,
        json.dumps(suggestions, ensure_ascii=False),
        json.dumps(optimized_recipe, ensure_ascii=False),
        ai_model,
        json.dumps(ai_response, ensure_ascii=False)
    ))
    conn.commit()
    opt_id = cursor.lastrowid
    conn.close()
    return opt_id


def get_ai_optimizations(recipe_id: int) -> List[Dict]:
    """Get AI optimizations for a recipe"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        SELECT * FROM ai_optimizations 
        WHERE recipe_id = ?
        ORDER BY created_at DESC
    """, (recipe_id,))
    rows = cursor.fetchall()
    conn.close()
    
    optimizations = []
    for row in rows:
        opt = dict(row)
        opt["suggestions"] = json.loads(opt["suggestions_json"])
        opt["optimized_recipe"] = json.loads(opt["optimized_recipe_json"])
        optimizations.append(opt)
    return optimizations


# =============================================================================
# ANALYTICS
# =============================================================================

def log_analytics_event(event_type: str, event_data: Dict = None, partner_id: int = None, user_id: int = None):
    """Log an analytics event"""
    conn = get_connection()
    cursor = conn.cursor()
    
    cursor.execute("""
        INSERT INTO analytics_events (partner_id, user_id, event_type, event_data_json)
        VALUES (?, ?, ?, ?)
    """, (
        partner_id,
        user_id,
        event_type,
        json.dumps(event_data, ensure_ascii=False) if event_data else None
    ))
    conn.commit()
    conn.close()


def get_partner_analytics(partner_id: int, days: int = 30) -> Dict:
    """Get analytics summary for a partner"""
    conn = get_connection()
    cursor = conn.cursor()
    
    # Total recipes
    cursor.execute("SELECT COUNT(*) as count FROM recipes WHERE partner_id = ?", (partner_id,))
    total_recipes = cursor.fetchone()["count"]
    
    # Recipes by Klimato grade
    cursor.execute("""
        SELECT klimato_grade, COUNT(*) as count 
        FROM recipes WHERE partner_id = ?
        GROUP BY klimato_grade
    """, (partner_id,))
    grade_distribution = {row["klimato_grade"]: row["count"] for row in cursor.fetchall()}
    
    # Average emission per portion
    cursor.execute("""
        SELECT AVG(gco2e_per_portion) as avg_emission 
        FROM recipes WHERE partner_id = ?
    """, (partner_id,))
    avg_emission = cursor.fetchone()["avg_emission"] or 0
    
    # Total calculations
    cursor.execute("""
        SELECT COUNT(*) as count FROM calculations 
        WHERE partner_id = ? AND calculated_at >= datetime('now', ?)
    """, (partner_id, f'-{days} days'))
    calculations_count = cursor.fetchone()["count"]
    
    # WRI compliance rate
    cursor.execute("""
        SELECT 
            SUM(CASE WHEN wri_compliant = 1 THEN 1 ELSE 0 END) as compliant,
            COUNT(*) as total
        FROM recipes WHERE partner_id = ?
    """, (partner_id,))
    wri_row = cursor.fetchone()
    wri_rate = (wri_row["compliant"] / wri_row["total"] * 100) if wri_row["total"] > 0 else 0
    
    # Top 5 highest emission recipes
    cursor.execute("""
        SELECT name, gco2e_per_portion, klimato_grade
        FROM recipes WHERE partner_id = ?
        ORDER BY gco2e_per_portion DESC LIMIT 5
    """, (partner_id,))
    highest_emission = [dict(row) for row in cursor.fetchall()]
    
    # Top 5 lowest emission recipes
    cursor.execute("""
        SELECT name, gco2e_per_portion, klimato_grade
        FROM recipes WHERE partner_id = ?
        ORDER BY gco2e_per_portion ASC LIMIT 5
    """, (partner_id,))
    lowest_emission = [dict(row) for row in cursor.fetchall()]
    
    # Daily calculation trend
    cursor.execute("""
        SELECT DATE(calculated_at) as date, COUNT(*) as count
        FROM calculations
        WHERE partner_id = ? AND calculated_at >= datetime('now', ?)
        GROUP BY DATE(calculated_at)
        ORDER BY date
    """, (partner_id, f'-{days} days'))
    daily_trend = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    return {
        "total_recipes": total_recipes,
        "grade_distribution": grade_distribution,
        "avg_emission_per_portion": round(avg_emission, 2),
        "calculations_last_n_days": calculations_count,
        "wri_compliance_rate": round(wri_rate, 1),
        "highest_emission_recipes": highest_emission,
        "lowest_emission_recipes": lowest_emission,
        "daily_calculation_trend": daily_trend,
    }


# Initialize database on import
init_database()
