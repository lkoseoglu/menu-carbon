# ai_optimizer.py - AI-powered recipe optimization using Claude API
# Requires: pip install anthropic

import os
import json
from typing import Dict, List, Optional, Any
from dataclasses import dataclass

# Try to import Anthropic
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False
    print("⚠️ Anthropic not installed. Run: pip install anthropic")


@dataclass
class OptimizationResult:
    """Result of AI optimization"""
    success: bool
    original_emission: float
    optimized_emission: float
    reduction_percent: float
    suggestions: List[Dict]
    optimized_ingredients: List[Dict]
    explanation: str
    ai_model: str
    raw_response: Dict


class RecipeOptimizer:
    """AI-powered recipe optimizer using Claude"""
    
    def __init__(self, api_key: str = None):
        """Initialize optimizer with API key"""
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.model = "claude-sonnet-4-20250514"
        self.client = None
        
        if ANTHROPIC_AVAILABLE and self.api_key:
            self.client = anthropic.Anthropic(api_key=self.api_key)
    
    def is_available(self) -> bool:
        """Check if AI optimization is available"""
        return self.client is not None
    
    def optimize_recipe(
        self,
        recipe_name: str,
        ingredients: List[Dict],
        current_emission: float,
        ef_map: Dict[str, float],
        name_map: Dict[str, str],
        target_reduction: float = 30.0,
        preserve_taste: bool = True,
        dietary_restrictions: List[str] = None,
    ) -> OptimizationResult:
        """
        Optimize a recipe to reduce carbon footprint.
        
        Args:
            recipe_name: Name of the recipe
            ingredients: List of ingredients with id, name, raw_weight_g, emission_factor_g_per_g
            current_emission: Current total emission in g CO2e
            ef_map: Map of ingredient_id -> emission factor
            name_map: Map of ingredient_id -> display name
            target_reduction: Target reduction percentage (default 30%)
            preserve_taste: Try to preserve original taste profile
            dietary_restrictions: List of dietary restrictions to consider
        
        Returns:
            OptimizationResult with suggestions and optimized recipe
        """
        if not self.is_available():
            return OptimizationResult(
                success=False,
                original_emission=current_emission,
                optimized_emission=current_emission,
                reduction_percent=0,
                suggestions=[{"error": "AI optimization not available. Set ANTHROPIC_API_KEY."}],
                optimized_ingredients=ingredients,
                explanation="AI optimization not available",
                ai_model="none",
                raw_response={}
            )
        
        # Build available ingredients list
        available_ingredients = []
        for ing_id, ef in sorted(ef_map.items(), key=lambda x: x[1]):
            available_ingredients.append({
                "id": ing_id,
                "name": name_map.get(ing_id, ing_id),
                "emission_factor": ef,
            })
        
        # Create prompt
        prompt = self._build_optimization_prompt(
            recipe_name=recipe_name,
            ingredients=ingredients,
            current_emission=current_emission,
            available_ingredients=available_ingredients,
            target_reduction=target_reduction,
            preserve_taste=preserve_taste,
            dietary_restrictions=dietary_restrictions,
        )
        
        try:
            # Call Claude API
            response = self.client.messages.create(
                model=self.model,
                max_tokens=2000,
                messages=[{"role": "user", "content": prompt}]
            )
            
            # Parse response
            response_text = response.content[0].text
            result = self._parse_optimization_response(response_text, ingredients, current_emission)
            result.ai_model = self.model
            result.raw_response = {"text": response_text}
            
            return result
            
        except Exception as e:
            return OptimizationResult(
                success=False,
                original_emission=current_emission,
                optimized_emission=current_emission,
                reduction_percent=0,
                suggestions=[{"error": str(e)}],
                optimized_ingredients=ingredients,
                explanation=f"AI optimization failed: {str(e)}",
                ai_model=self.model,
                raw_response={"error": str(e)}
            )
    
    def _build_optimization_prompt(
        self,
        recipe_name: str,
        ingredients: List[Dict],
        current_emission: float,
        available_ingredients: List[Dict],
        target_reduction: float,
        preserve_taste: bool,
        dietary_restrictions: List[str],
    ) -> str:
        """Build the optimization prompt for Claude"""
        
        # Format current ingredients
        current_ing_str = "\n".join([
            f"  - {ing.get('name', ing['id'])}: {ing['raw_weight_g']}g (EF: {ing['emission_factor_g_per_g']:.2f} g CO₂e/g, Emission: {ing['raw_weight_g'] * ing['emission_factor_g_per_g']:.0f}g CO₂e)"
            for ing in ingredients
        ])
        
        # Format available alternatives (low emission options)
        low_emission_alternatives = [ing for ing in available_ingredients if ing["emission_factor"] < 3.0][:30]
        alternatives_str = "\n".join([
            f"  - {ing['name']} ({ing['id']}): EF = {ing['emission_factor']:.2f} g CO₂e/g"
            for ing in low_emission_alternatives
        ])
        
        restrictions_str = ", ".join(dietary_restrictions) if dietary_restrictions else "None"
        
        prompt = f"""You are a culinary AI assistant specialized in sustainable cooking. Your task is to optimize a recipe to reduce its carbon footprint while maintaining taste and nutritional value.

## Current Recipe: {recipe_name}

### Current Ingredients:
{current_ing_str}

### Current Total Emission: {current_emission:.0f} g CO₂e
### Target Reduction: {target_reduction}% (Target: {current_emission * (1 - target_reduction/100):.0f} g CO₂e)

### Constraints:
- Preserve taste: {"Yes - maintain similar flavor profile" if preserve_taste else "No - can change significantly"}
- Dietary restrictions: {restrictions_str}

### Available Low-Emission Alternatives:
{alternatives_str}

## Your Task:
Analyze the recipe and suggest modifications to reduce carbon footprint. For each suggestion:
1. Identify high-emission ingredients that can be replaced or reduced
2. Suggest specific alternatives from the available list
3. Adjust quantities to maintain recipe balance
4. Explain the taste/nutrition impact

## Response Format:
Please respond in the following JSON format:

```json
{{
  "analysis": "Brief analysis of the current recipe's carbon hotspots",
  "suggestions": [
    {{
      "type": "replace|reduce|remove",
      "original_ingredient": "ingredient name",
      "new_ingredient": "replacement name or null",
      "original_weight_g": 200,
      "new_weight_g": 150,
      "emission_saved_g": 500,
      "taste_impact": "minimal|moderate|significant",
      "explanation": "Why this change works"
    }}
  ],
  "optimized_ingredients": [
    {{
      "id": "ingredient_id",
      "name": "Ingredient Name",
      "raw_weight_g": 150,
      "emission_factor_g_per_g": 1.5
    }}
  ],
  "estimated_new_emission": 800,
  "reduction_achieved_percent": 35,
  "overall_explanation": "Summary of changes and expected outcome"
}}
```

Important: 
- Only suggest ingredients from the available list
- Be realistic about portion sizes and recipe balance
- Consider protein, texture, and flavor when substituting
- Prioritize changes with highest emission reduction and lowest taste impact"""

        return prompt
    
    def _parse_optimization_response(
        self,
        response_text: str,
        original_ingredients: List[Dict],
        original_emission: float
    ) -> OptimizationResult:
        """Parse Claude's response into structured result"""
        
        try:
            # Extract JSON from response
            json_start = response_text.find("{")
            json_end = response_text.rfind("}") + 1
            
            if json_start == -1 or json_end == 0:
                raise ValueError("No JSON found in response")
            
            json_str = response_text[json_start:json_end]
            data = json.loads(json_str)
            
            suggestions = data.get("suggestions", [])
            optimized_ingredients = data.get("optimized_ingredients", original_ingredients)
            new_emission = data.get("estimated_new_emission", original_emission)
            reduction = data.get("reduction_achieved_percent", 0)
            explanation = data.get("overall_explanation", "")
            
            # Validate and calculate actual emission
            calculated_emission = sum(
                ing.get("raw_weight_g", 0) * ing.get("emission_factor_g_per_g", 0)
                for ing in optimized_ingredients
            )
            
            if calculated_emission > 0:
                new_emission = calculated_emission
                reduction = ((original_emission - new_emission) / original_emission) * 100
            
            return OptimizationResult(
                success=True,
                original_emission=original_emission,
                optimized_emission=round(new_emission, 2),
                reduction_percent=round(reduction, 1),
                suggestions=suggestions,
                optimized_ingredients=optimized_ingredients,
                explanation=explanation,
                ai_model="",
                raw_response={}
            )
            
        except json.JSONDecodeError as e:
            # Try to extract useful info even if JSON parsing fails
            return OptimizationResult(
                success=False,
                original_emission=original_emission,
                optimized_emission=original_emission,
                reduction_percent=0,
                suggestions=[{"error": f"Failed to parse AI response: {str(e)}"}],
                optimized_ingredients=original_ingredients,
                explanation=response_text[:500],
                ai_model="",
                raw_response={"raw_text": response_text}
            )
    
    def get_quick_suggestions(
        self,
        ingredients: List[Dict],
        ef_map: Dict[str, float],
        name_map: Dict[str, str],
    ) -> List[Dict]:
        """
        Get quick suggestions without AI (rule-based).
        Useful when API is not available or for instant feedback.
        """
        suggestions = []
        
        # Define substitution rules
        substitutions = {
            "beef": [
                ("chicken", "Tavuk ile değiştirin", 74),
                ("tofu", "Tofu ile değiştirin (vejetaryen)", 93),
                ("lentil", "Mercimek ile değiştirin", 97),
            ],
            "lamb": [
                ("chicken", "Tavuk ile değiştirin", 82),
                ("fish_wild", "Balık ile değiştirin", 91),
            ],
            "cheese": [
                ("yogurt", "Yoğurt ile değiştirin", 85),
                ("cheese_feta", "Beyaz peynir ile değiştirin", 37),
            ],
            "butter": [
                ("oil_olive", "Zeytinyağı ile değiştirin", 58),
                ("oil_sunflower", "Ayçiçek yağı ile değiştirin", 75),
            ],
            "shrimp": [
                ("mussel", "Midye ile değiştirin", 97),
                ("fish_wild", "Balık ile değiştirin", 81),
            ],
            "rice": [
                ("bulgur", "Bulgur ile değiştirin", 70),
                ("pasta", "Makarna ile değiştirin", 60),
            ],
            "cream": [
                ("yogurt", "Yoğurt ile değiştirin", 62),
                ("milk", "Süt ile değiştirin", 63),
            ],
        }
        
        for ing in ingredients:
            ing_id = ing.get("id", "").lower()
            ing_ef = ing.get("emission_factor_g_per_g", 0)
            ing_weight = ing.get("raw_weight_g", 0)
            
            if ing_id in substitutions:
                for alt_id, description, reduction in substitutions[ing_id]:
                    if alt_id in ef_map:
                        alt_ef = ef_map[alt_id]
                        alt_name = name_map.get(alt_id, alt_id)
                        current_emission = ing_weight * ing_ef
                        new_emission = ing_weight * alt_ef
                        saved = current_emission - new_emission
                        
                        suggestions.append({
                            "type": "replace",
                            "original_ingredient": ing.get("name", ing_id),
                            "original_id": ing_id,
                            "new_ingredient": alt_name,
                            "new_id": alt_id,
                            "emission_saved_g": round(saved, 0),
                            "reduction_percent": reduction,
                            "description": description,
                        })
        
        # Sort by emission saved
        suggestions.sort(key=lambda x: x["emission_saved_g"], reverse=True)
        
        return suggestions[:5]  # Top 5 suggestions
    
    def analyze_recipe_hotspots(
        self,
        ingredients: List[Dict],
    ) -> Dict:
        """Analyze which ingredients contribute most to emissions"""
        
        total_emission = sum(
            ing.get("raw_weight_g", 0) * ing.get("emission_factor_g_per_g", 0)
            for ing in ingredients
        )
        
        hotspots = []
        for ing in ingredients:
            emission = ing.get("raw_weight_g", 0) * ing.get("emission_factor_g_per_g", 0)
            percentage = (emission / total_emission * 100) if total_emission > 0 else 0
            
            hotspots.append({
                "ingredient": ing.get("name", ing.get("id", "unknown")),
                "id": ing.get("id", ""),
                "weight_g": ing.get("raw_weight_g", 0),
                "emission_g": round(emission, 2),
                "percentage": round(percentage, 1),
                "emission_factor": ing.get("emission_factor_g_per_g", 0),
                "is_hotspot": percentage > 20,  # More than 20% of total
            })
        
        # Sort by emission
        hotspots.sort(key=lambda x: x["emission_g"], reverse=True)
        
        # Identify main hotspots
        main_hotspots = [h for h in hotspots if h["is_hotspot"]]
        
        return {
            "total_emission": round(total_emission, 2),
            "hotspots": hotspots,
            "main_hotspots": main_hotspots,
            "hotspot_count": len(main_hotspots),
            "top_contributor": hotspots[0] if hotspots else None,
        }


# =============================================================================
# RECIPE IMPROVEMENT SUGGESTIONS
# =============================================================================

def get_improvement_tips(klimato_grade: str, language: str = "tr") -> List[str]:
    """Get improvement tips based on Klimato grade"""
    
    tips = {
        "tr": {
            "E": [
                "🔴 Kırmızı et miktarını azaltmayı veya tavuk/balık ile değiştirmeyi deneyin",
                "🔴 Tereyağı yerine zeytinyağı kullanın",
                "🔴 Peynir miktarını azaltın veya beyaz peynir tercih edin",
                "🔴 Porsiyon boyutunu gözden geçirin",
                "🔴 Mevsiminde ve yerel sebzeler ekleyin",
            ],
            "D": [
                "🟠 Et porsiyonunu %25 azaltmayı deneyin",
                "🟠 Baklagiller ekleyerek protein dengesini koruyun",
                "🟠 Pirinç yerine bulgur veya makarna kullanın",
                "🟠 Süt ürünlerini bitkisel alternatiflerle değiştirin",
            ],
            "C": [
                "🟡 İyi gidiyorsunuz! Küçük değişikliklerle B seviyesine ulaşabilirsiniz",
                "🟡 Sebze oranını artırın",
                "🟡 Yerel ve mevsimlik malzemeler tercih edin",
            ],
            "B": [
                "🟢 Harika! A seviyesi için son adımlar:",
                "🟢 Tamamen bitkisel alternatifler düşünün",
                "🟢 Organik ve yerel ürünler tercih edin",
            ],
            "A": [
                "⭐ Mükemmel! Bu tarif çok düşük karbon ayak izine sahip",
                "⭐ Bu tarifi örnek olarak paylaşabilirsiniz",
            ],
        },
        "en": {
            "E": [
                "🔴 Try reducing red meat or substituting with chicken/fish",
                "🔴 Use olive oil instead of butter",
                "🔴 Reduce cheese amount or choose feta",
                "🔴 Review portion sizes",
                "🔴 Add seasonal and local vegetables",
            ],
            "D": [
                "🟠 Try reducing meat portion by 25%",
                "🟠 Add legumes to maintain protein balance",
                "🟠 Use bulgur or pasta instead of rice",
                "🟠 Replace dairy with plant-based alternatives",
            ],
            "C": [
                "🟡 Good progress! Small changes can reach B level",
                "🟡 Increase vegetable ratio",
                "🟡 Prefer local and seasonal ingredients",
            ],
            "B": [
                "🟢 Great! Final steps for A level:",
                "🟢 Consider fully plant-based alternatives",
                "🟢 Prefer organic and local products",
            ],
            "A": [
                "⭐ Excellent! This recipe has very low carbon footprint",
                "⭐ You can share this recipe as an example",
            ],
        }
    }
    
    lang_tips = tips.get(language, tips["en"])
    return lang_tips.get(klimato_grade, [])


# =============================================================================
# SINGLETON INSTANCE
# =============================================================================

_optimizer_instance = None

def get_optimizer(api_key: str = None) -> RecipeOptimizer:
    """Get or create optimizer instance"""
    global _optimizer_instance
    
    if _optimizer_instance is None or api_key:
        _optimizer_instance = RecipeOptimizer(api_key)
    
    return _optimizer_instance
