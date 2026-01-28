# pdf_reader.py - PDF Menu/Recipe Reader with OCR and Claude Vision
# Extracts ingredients and quantities from PDF menus and images

import os
import base64
import json
import re
from typing import Dict, List, Optional, Tuple
from pathlib import Path

# Try imports
try:
    import anthropic
    ANTHROPIC_AVAILABLE = True
except ImportError:
    ANTHROPIC_AVAILABLE = False

try:
    import fitz  # PyMuPDF
    PYMUPDF_AVAILABLE = True
except ImportError:
    PYMUPDF_AVAILABLE = False

try:
    import pytesseract
    from PIL import Image
    TESSERACT_AVAILABLE = True
except ImportError:
    TESSERACT_AVAILABLE = False
    from PIL import Image

from io import BytesIO


class PDFMenuReader:
    """Read and extract recipe ingredients from PDF menus and images"""
    
    def __init__(self, api_key: str = None):
        self.api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        self.client = None
        self.model = "claude-sonnet-4-20250514"
        
        if ANTHROPIC_AVAILABLE and self.api_key:
            self.client = anthropic.Anthropic(api_key=self.api_key)
    
    def is_available(self) -> bool:
        """Check if Claude API is available (for smart image analysis)"""
        return self.client is not None
    
    def has_ocr(self) -> bool:
        """Check if Tesseract OCR is available"""
        return TESSERACT_AVAILABLE
    
    # =========================================================================
    # TEXT EXTRACTION (No API needed)
    # =========================================================================
    
    def extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        """Extract text content from PDF without API"""
        if not PYMUPDF_AVAILABLE:
            raise RuntimeError("PyMuPDF gerekli: pip install PyMuPDF")
        
        text_parts = []
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        
        for page in doc:
            text = page.get_text()
            if text.strip():
                text_parts.append(text)
        
        doc.close()
        return "\n\n".join(text_parts)
    
    def extract_text_from_image_ocr(self, image_bytes: bytes, lang: str = "tur+eng") -> str:
        """Extract text from image using Tesseract OCR (no API needed)"""
        if not TESSERACT_AVAILABLE:
            raise RuntimeError("Tesseract OCR gerekli: pip install pytesseract ve Tesseract kurulumu")
        
        # Open image
        img = Image.open(BytesIO(image_bytes))
        
        # Convert to RGB if necessary
        if img.mode != 'RGB':
            img = img.convert('RGB')
        
        # Run OCR
        text = pytesseract.image_to_string(img, lang=lang)
        return text
    
    def extract_text_from_image_vision(self, image_bytes: bytes, language: str = "tr") -> Dict:
        """Extract recipes from image using Claude Vision (API needed)"""
        if not self.is_available():
            return {"error": "Claude API not available", "recipes": [], "text": ""}
        
        # Convert to base64
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        
        # Detect media type
        if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            media_type = "image/png"
        elif image_bytes[:2] == b'\xff\xd8':
            media_type = "image/jpeg"
        elif image_bytes[:4] == b'RIFF':
            media_type = "image/webp"
        else:
            media_type = "image/jpeg"
        
        # Build prompt
        if language == "tr":
            prompt = """Bu menü veya tarif görselini analiz et. 

Görseldeki TÜM yazıları ve tarifleri çıkar. Her malzeme için miktarı gram cinsinden tahmin et.

Yanıtını şu JSON formatında ver:

```json
{
  "text": "Görseldeki tüm metin",
  "recipes": [
    {
      "name": "Tarif Adı",
      "portions": 1,
      "ingredients": [
        {"name": "malzeme adı", "amount_g": 200, "original_text": "orijinal metin"}
      ]
    }
  ]
}
```

Dönüşüm kuralları:
- 1 su bardağı = 200g (sıvı), 150g (katı)
- 1 yemek kaşığı = 15g
- 1 çay kaşığı = 5g
- 1 adet yumurta = 60g
- 1 adet soğan = 150g
- 1 adet domates = 150g"""
        else:
            prompt = """Analyze this menu or recipe image.

Extract ALL text and recipes. Estimate amounts in grams.

Respond in JSON format:

```json
{
  "text": "All text from image",
  "recipes": [
    {
      "name": "Recipe Name",
      "portions": 1,
      "ingredients": [
        {"name": "ingredient name", "amount_g": 200, "original_text": "original text"}
      ]
    }
  ]
}
```"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_b64,
                                }
                            },
                            {"type": "text", "text": prompt}
                        ]
                    }
                ]
            )
            
            response_text = response.content[0].text
            return self._parse_vision_response(response_text)
            
        except Exception as e:
            return {"error": str(e), "recipes": [], "text": ""}
    
    def _parse_vision_response(self, response_text: str) -> Dict:
        """Parse Claude Vision response"""
        try:
            # Extract JSON
            json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            if json_match:
                json_str = json_match.group(1)
            else:
                json_start = response_text.find("{")
                json_end = response_text.rfind("}") + 1
                if json_start != -1 and json_end > json_start:
                    json_str = response_text[json_start:json_end]
                else:
                    return {"error": "JSON bulunamadı", "recipes": [], "text": response_text}
            
            return json.loads(json_str)
        except json.JSONDecodeError as e:
            return {"error": f"JSON hatası: {e}", "recipes": [], "text": response_text}
    
    def parse_recipes_from_text(self, text: str) -> List[Dict]:
        """Parse recipes from extracted text using pattern matching"""
        recipes = []
        
        # Common Turkish recipe patterns
        # Pattern 1: "TARIF ADI" followed by ingredients
        # Pattern 2: Lines with "gr", "g", "kg", "adet", "su bardağı" etc.
        
        lines = text.split('\n')
        current_recipe = None
        current_ingredients = []
        
        # Weight patterns
        weight_patterns = [
            r'(\d+)\s*(?:gr|g|gram)\b',  # 200gr, 200g, 200 gram
            r'(\d+)\s*(?:kg|kilo)\b',     # 1kg, 1 kilo (multiply by 1000)
            r'(\d+)\s*(?:adet)\b',         # 2 adet
            r'(\d+)\s*(?:su bardağı|bardak)\b',  # 1 su bardağı (~200g)
            r'(\d+)\s*(?:yemek kaşığı|yk)\b',    # 2 yemek kaşığı (~30g)
            r'(\d+)\s*(?:çay kaşığı|ck)\b',      # 1 çay kaşığı (~5g)
            r'(\d+)\s*(?:ml|litre|lt)\b',        # 200ml
        ]
        
        # Ingredient keywords that indicate a line is an ingredient
        ingredient_indicators = [
            'gr', 'g', 'kg', 'adet', 'bardak', 'kaşık', 'ml', 'litre',
            'dana', 'tavuk', 'balık', 'et', 'pirinç', 'bulgur', 'makarna',
            'soğan', 'sarımsak', 'domates', 'biber', 'patates', 'havuç',
            'yağ', 'tuz', 'şeker', 'un', 'süt', 'yumurta', 'peynir'
        ]
        
        for i, line in enumerate(lines):
            line = line.strip()
            if not line:
                continue
            
            # Check if this looks like a recipe title (ALL CAPS or ends with colon)
            is_title = (
                (line.isupper() and len(line) > 3 and len(line) < 50) or
                (line.endswith(':') and len(line) < 50) or
                (line.startswith('#') or line.startswith('*'))
            )
            
            # Check if line contains ingredient indicators
            line_lower = line.lower()
            has_ingredient = any(ind in line_lower for ind in ingredient_indicators)
            has_number = any(c.isdigit() for c in line)
            
            if is_title and not has_ingredient:
                # Save previous recipe
                if current_recipe and current_ingredients:
                    recipes.append({
                        "name": current_recipe,
                        "portions": 1,
                        "ingredients": current_ingredients
                    })
                
                # Start new recipe
                current_recipe = line.strip(':').strip('#').strip('*').strip()
                current_ingredients = []
            
            elif has_ingredient and has_number:
                # Parse ingredient
                ingredient = self._parse_ingredient_line(line)
                if ingredient:
                    current_ingredients.append(ingredient)
        
        # Save last recipe
        if current_recipe and current_ingredients:
            recipes.append({
                "name": current_recipe,
                "portions": 1,
                "ingredients": current_ingredients
            })
        
        # If no structured recipes found, try to find all ingredients in text
        if not recipes:
            all_ingredients = []
            for line in lines:
                ingredient = self._parse_ingredient_line(line)
                if ingredient:
                    all_ingredients.append(ingredient)
            
            if all_ingredients:
                recipes.append({
                    "name": "PDF'den Çıkarılan Tarif",
                    "portions": 1,
                    "ingredients": all_ingredients
                })
        
        return recipes
    
    def _parse_ingredient_line(self, line: str) -> Optional[Dict]:
        """Parse a single line to extract ingredient and amount"""
        line = line.strip()
        if not line:
            return None
        
        # Try to extract amount
        amount_g = 0
        
        # Check for gram
        match = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:gr|g|gram)\b', line, re.IGNORECASE)
        if match:
            amount_g = float(match.group(1).replace(',', '.'))
        
        # Check for kg
        if not amount_g:
            match = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:kg|kilo)\b', line, re.IGNORECASE)
            if match:
                amount_g = float(match.group(1).replace(',', '.')) * 1000
        
        # Check for su bardağı (~200g for liquids, ~150g for solids)
        if not amount_g:
            match = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:su bardağı|bardak)\b', line, re.IGNORECASE)
            if match:
                amount_g = float(match.group(1).replace(',', '.')) * 150
        
        # Check for yemek kaşığı (~15g)
        if not amount_g:
            match = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:yemek kaşığı|yk)\b', line, re.IGNORECASE)
            if match:
                amount_g = float(match.group(1).replace(',', '.')) * 15
        
        # Check for çay kaşığı (~5g)
        if not amount_g:
            match = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:çay kaşığı|ck|tatlı kaşığı)\b', line, re.IGNORECASE)
            if match:
                amount_g = float(match.group(1).replace(',', '.')) * 5
        
        # Check for adet (estimate based on common items)
        if not amount_g:
            match = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:adet)\b', line, re.IGNORECASE)
            if match:
                count = float(match.group(1).replace(',', '.'))
                # Estimate weight based on ingredient
                line_lower = line.lower()
                if 'yumurta' in line_lower:
                    amount_g = count * 60
                elif 'soğan' in line_lower:
                    amount_g = count * 150
                elif 'domates' in line_lower:
                    amount_g = count * 150
                elif 'biber' in line_lower:
                    amount_g = count * 30
                elif 'sarımsak' in line_lower:
                    amount_g = count * 5
                elif 'patates' in line_lower:
                    amount_g = count * 200
                elif 'havuç' in line_lower:
                    amount_g = count * 100
                else:
                    amount_g = count * 100  # Default estimate
        
        # Check for ml/litre
        if not amount_g:
            match = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:ml)\b', line, re.IGNORECASE)
            if match:
                amount_g = float(match.group(1).replace(',', '.'))  # 1ml ≈ 1g for most liquids
        
        if not amount_g:
            match = re.search(r'(\d+(?:[.,]\d+)?)\s*(?:litre|lt|l)\b', line, re.IGNORECASE)
            if match:
                amount_g = float(match.group(1).replace(',', '.')) * 1000
        
        # If no amount found but line looks like ingredient, skip it
        if amount_g == 0:
            return None
        
        # Clean ingredient name (remove numbers and units)
        name = re.sub(r'\d+(?:[.,]\d+)?\s*(?:gr|g|gram|kg|kilo|adet|su bardağı|bardak|yemek kaşığı|yk|çay kaşığı|ck|tatlı kaşığı|ml|litre|lt|l)\b', '', line, flags=re.IGNORECASE)
        name = re.sub(r'[•\-–—:]', '', name)
        name = name.strip()
        
        if not name or len(name) < 2:
            return None
        
        return {
            "name": name.lower(),
            "amount_g": round(amount_g),
            "original_text": line
        }
    
    def pdf_to_images(self, pdf_path: str = None, pdf_bytes: bytes = None, max_pages: int = 5) -> List[bytes]:
        """Convert PDF pages to images"""
        images = []
        
        if PYMUPDF_AVAILABLE:
            # Use PyMuPDF
            if pdf_path:
                doc = fitz.open(pdf_path)
            else:
                doc = fitz.open(stream=pdf_bytes, filetype="pdf")
            
            for page_num in range(min(len(doc), max_pages)):
                page = doc[page_num]
                # Render at 2x resolution for better OCR
                mat = fitz.Matrix(2, 2)
                pix = page.get_pixmap(matrix=mat)
                img_bytes = pix.tobytes("png")
                images.append(img_bytes)
            
            doc.close()
        
        elif PDF2IMAGE_AVAILABLE:
            # Use pdf2image (requires poppler)
            if pdf_path:
                pil_images = convert_from_path(pdf_path, last_page=max_pages, dpi=200)
            else:
                pil_images = convert_from_bytes(pdf_bytes, last_page=max_pages, dpi=200)
            
            for img in pil_images:
                buf = BytesIO()
                img.save(buf, format="PNG")
                images.append(buf.getvalue())
        
        else:
            raise RuntimeError("PDF okumak için PyMuPDF veya pdf2image gerekli. pip install PyMuPDF")
        
        return images
    
    def extract_recipes_from_image(self, image_bytes: bytes, language: str = "tr") -> Dict:
        """Extract recipes from a single image using Claude Vision"""
        
        if not self.is_available():
            return {"error": "Claude API not available", "recipes": []}
        
        # Convert to base64
        image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")
        
        # Determine media type
        if image_bytes[:8] == b'\x89PNG\r\n\x1a\n':
            media_type = "image/png"
        elif image_bytes[:2] == b'\xff\xd8':
            media_type = "image/jpeg"
        else:
            media_type = "image/png"
        
        # Build prompt
        if language == "tr":
            prompt = """Bu menü/tarif görselini analiz et ve içindeki tüm tarifleri/yemekleri çıkar.

Her tarif için şunları belirle:
1. Tarif adı
2. Malzemeler ve miktarları (gram cinsinden tahmin et)
3. Porsiyon sayısı (belirtilmemişse 1 varsay)

Yanıtını SADECE şu JSON formatında ver, başka bir şey yazma:

```json
{
  "recipes": [
    {
      "name": "Tarif Adı",
      "portions": 1,
      "ingredients": [
        {"name": "malzeme adı", "amount_g": 200, "original_text": "orijinal metin"},
        {"name": "başka malzeme", "amount_g": 100, "original_text": "orijinal metin"}
      ]
    }
  ],
  "notes": "Varsa ek notlar"
}
```

Önemli kurallar:
- Miktarlar gram cinsinden olmalı (1 su bardağı = ~200g, 1 yemek kaşığı = ~15g, 1 çay kaşığı = ~5g)
- Malzeme adları Türkçe ve küçük harf olmalı
- Eğer miktar belirtilmemişse makul bir tahmin yap
- "beef", "chicken", "rice" gibi İngilizce karşılıkları da ingredients içine "id" olarak ekle"""
        else:
            prompt = """Analyze this menu/recipe image and extract all recipes/dishes.

For each recipe, identify:
1. Recipe name
2. Ingredients with quantities (estimate in grams)
3. Number of portions (assume 1 if not specified)

Respond ONLY in this JSON format:

```json
{
  "recipes": [
    {
      "name": "Recipe Name",
      "portions": 1,
      "ingredients": [
        {"name": "ingredient name", "amount_g": 200, "original_text": "original text"},
        {"name": "another ingredient", "amount_g": 100, "original_text": "original text"}
      ]
    }
  ],
  "notes": "Any additional notes"
}
```

Important rules:
- Amounts must be in grams (1 cup = ~200g, 1 tablespoon = ~15g, 1 teaspoon = ~5g)
- Ingredient names should be lowercase
- If amount not specified, make a reasonable estimate"""

        try:
            response = self.client.messages.create(
                model=self.model,
                max_tokens=4000,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image",
                                "source": {
                                    "type": "base64",
                                    "media_type": media_type,
                                    "data": image_b64,
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ]
            )
            
            # Parse response
            response_text = response.content[0].text
            return self._parse_recipe_response(response_text)
            
        except Exception as e:
            return {"error": str(e), "recipes": []}
    
    def extract_recipes_from_pdf(
        self, 
        pdf_path: str = None, 
        pdf_bytes: bytes = None,
        language: str = "tr",
        max_pages: int = 5
    ) -> Dict:
        """Extract all recipes from a PDF document"""
        
        try:
            # Convert PDF to images
            images = self.pdf_to_images(pdf_path, pdf_bytes, max_pages)
            
            all_recipes = []
            all_notes = []
            
            for i, img_bytes in enumerate(images):
                result = self.extract_recipes_from_image(img_bytes, language)
                
                if "error" in result and result["error"]:
                    all_notes.append(f"Sayfa {i+1}: {result['error']}")
                else:
                    for recipe in result.get("recipes", []):
                        recipe["source_page"] = i + 1
                        all_recipes.append(recipe)
                    
                    if result.get("notes"):
                        all_notes.append(f"Sayfa {i+1}: {result['notes']}")
            
            return {
                "recipes": all_recipes,
                "total_pages": len(images),
                "notes": "\n".join(all_notes) if all_notes else None
            }
            
        except Exception as e:
            return {"error": str(e), "recipes": []}
    
    def _parse_recipe_response(self, response_text: str) -> Dict:
        """Parse Claude's response into structured data"""
        
        try:
            # Extract JSON from response
            json_match = re.search(r'```json\s*(.*?)\s*```', response_text, re.DOTALL)
            
            if json_match:
                json_str = json_match.group(1)
            else:
                # Try to find raw JSON
                json_start = response_text.find("{")
                json_end = response_text.rfind("}") + 1
                if json_start != -1 and json_end > json_start:
                    json_str = response_text[json_start:json_end]
                else:
                    return {"error": "JSON bulunamadı", "recipes": [], "raw": response_text}
            
            data = json.loads(json_str)
            return data
            
        except json.JSONDecodeError as e:
            return {"error": f"JSON parse hatası: {e}", "recipes": [], "raw": response_text}
    
    def match_ingredients_to_database(
        self, 
        recipes: List[Dict], 
        ef_map: Dict[str, float],
        name_map: Dict[str, str],
        syn_map: Dict[str, str] = None
    ) -> List[Dict]:
        """Match extracted ingredients to database ingredients"""
        
        syn_map = syn_map or {}
        
        # Common Turkish to English mappings
        tr_to_en = {
            "dana eti": "beef", "sığır eti": "beef", "kıyma": "beef",
            "kuzu eti": "lamb", "kuzu": "lamb",
            "tavuk": "chicken", "tavuk göğsü": "chicken", "tavuk but": "chicken",
            "balık": "fish_wild", "somon": "salmon", "levrek": "fish_wild",
            "karides": "shrimp", "midye": "mussel",
            "pirinç": "rice", "bulgur": "bulgur", "makarna": "pasta",
            "patates": "potato", "soğan": "onion", "sarımsak": "garlic",
            "domates": "tomato", "biber": "pepper", "salatalık": "cucumber",
            "havuç": "carrot", "patlıcan": "eggplant", "kabak": "zucchini",
            "fasulye": "beans", "nohut": "chickpea", "mercimek": "lentil",
            "süt": "milk", "yoğurt": "yogurt", "peynir": "cheese",
            "beyaz peynir": "cheese_feta", "kaşar": "cheese",
            "tereyağı": "butter", "zeytinyağı": "oil_olive",
            "ayçiçek yağı": "oil_sunflower", "yumurta": "egg",
            "un": "flour", "şeker": "sugar", "tuz": "salt",
            "maydanoz": "parsley", "dereotu": "dill", "nane": "mint",
        }
        
        matched_recipes = []
        
        for recipe in recipes:
            matched_ingredients = []
            unmatched = []
            
            for ing in recipe.get("ingredients", []):
                ing_name = ing.get("name", "").lower().strip()
                amount = ing.get("amount_g", 0)
                
                # Try to find match
                matched_id = None
                
                # 1. Direct match in ef_map
                if ing_name in ef_map:
                    matched_id = ing_name
                
                # 2. Check synonym map
                elif ing_name in syn_map:
                    matched_id = syn_map[ing_name]
                
                # 3. Check Turkish to English mapping
                elif ing_name in tr_to_en:
                    en_name = tr_to_en[ing_name]
                    if en_name in ef_map:
                        matched_id = en_name
                
                # 4. Fuzzy match - check if any key contains the ingredient name
                else:
                    for key in ef_map.keys():
                        if ing_name in key or key in ing_name:
                            matched_id = key
                            break
                    
                    # Also check reverse
                    if not matched_id:
                        for tr_name, en_name in tr_to_en.items():
                            if tr_name in ing_name or ing_name in tr_name:
                                if en_name in ef_map:
                                    matched_id = en_name
                                    break
                
                if matched_id:
                    matched_ingredients.append({
                        "id": matched_id,
                        "name": name_map.get(matched_id, matched_id),
                        "raw_weight_g": amount,
                        "original_name": ing_name,
                        "emission_factor": ef_map.get(matched_id, 0)
                    })
                else:
                    unmatched.append({
                        "name": ing_name,
                        "amount_g": amount,
                        "original_text": ing.get("original_text", "")
                    })
            
            matched_recipes.append({
                "name": recipe.get("name", ""),
                "portions": recipe.get("portions", 1),
                "ingredients": matched_ingredients,
                "unmatched_ingredients": unmatched,
                "source_page": recipe.get("source_page", 1)
            })
        
        return matched_recipes


# =============================================================================
# STREAMLIT COMPONENT
# =============================================================================

def render_pdf_upload_section(
    ef_map: Dict[str, float],
    name_map: Dict[str, str],
    api_key: str = None,
    language: str = "tr"
):
    """Render PDF upload section in Streamlit"""
    import streamlit as st
    
    t = {
        "tr": {
            "title": "📄 PDF'den Menü Oku",
            "upload": "PDF dosyası yükleyin",
            "or_image": "veya görsel yükleyin",
            "analyzing": "Analiz ediliyor...",
            "found": "tarif bulundu",
            "no_recipes": "Tarif bulunamadı",
            "select": "Hesaplamak için tarif seçin",
            "use_recipe": "Bu Tarifi Kullan",
            "unmatched": "Eşleşmeyen malzemeler",
            "api_required": "PDF okuma için Anthropic API key gerekli",
        },
        "en": {
            "title": "📄 Read Menu from PDF",
            "upload": "Upload PDF file",
            "or_image": "or upload image",
            "analyzing": "Analyzing...",
            "found": "recipes found",
            "no_recipes": "No recipes found",
            "select": "Select recipe to calculate",
            "use_recipe": "Use This Recipe",
            "unmatched": "Unmatched ingredients",
            "api_required": "Anthropic API key required for PDF reading",
        }
    }[language]
    
    st.subheader(t["title"])
    
    if not api_key:
        st.warning(t["api_required"])
        return None
    
    reader = PDFMenuReader(api_key)
    
    if not reader.is_available():
        st.error("Claude API bağlantısı kurulamadı")
        return None
    
    col1, col2 = st.columns(2)
    
    with col1:
        pdf_file = st.file_uploader(t["upload"], type=["pdf"], key="pdf_upload")
    
    with col2:
        image_file = st.file_uploader(t["or_image"], type=["png", "jpg", "jpeg"], key="img_upload")
    
    if pdf_file or image_file:
        with st.spinner(t["analyzing"]):
            try:
                if pdf_file:
                    result = reader.extract_recipes_from_pdf(
                        pdf_bytes=pdf_file.read(),
                        language=language
                    )
                else:
                    result = reader.extract_recipes_from_image(
                        image_bytes=image_file.read(),
                        language=language
                    )
                
                if "error" in result and result["error"]:
                    st.error(result["error"])
                    return None
                
                recipes = result.get("recipes", [])
                
                if not recipes:
                    st.warning(t["no_recipes"])
                    return None
                
                st.success(f"✅ {len(recipes)} {t['found']}")
                
                # Match to database
                matched = reader.match_ingredients_to_database(recipes, ef_map, name_map)
                
                # Let user select recipe
                recipe_names = [f"{r['name']} ({len(r['ingredients'])} malzeme)" for r in matched]
                selected_idx = st.selectbox(t["select"], range(len(recipe_names)), format_func=lambda i: recipe_names[i])
                
                selected_recipe = matched[selected_idx]
                
                # Show ingredients
                st.write("**Malzemeler:**")
                for ing in selected_recipe["ingredients"]:
                    st.write(f"- {ing['name']}: {ing['raw_weight_g']}g (EF: {ing['emission_factor']:.2f})")
                
                # Show unmatched
                if selected_recipe["unmatched_ingredients"]:
                    with st.expander(f"⚠️ {t['unmatched']} ({len(selected_recipe['unmatched_ingredients'])})"):
                        for ing in selected_recipe["unmatched_ingredients"]:
                            st.write(f"- {ing['name']}: {ing['amount_g']}g")
                
                # Return button
                if st.button(f"✅ {t['use_recipe']}", type="primary"):
                    return {
                        "name": selected_recipe["name"],
                        "portions": selected_recipe["portions"],
                        "ingredients": [
                            {"id": ing["id"], "raw_weight_g": ing["raw_weight_g"], "name": ing["name"]}
                            for ing in selected_recipe["ingredients"]
                        ]
                    }
                
            except Exception as e:
                st.error(f"Hata: {str(e)}")
                return None
    
    return None


# =============================================================================
# SINGLETON
# =============================================================================

_reader_instance = None

def get_pdf_reader(api_key: str = None) -> PDFMenuReader:
    """Get or create PDF reader instance"""
    global _reader_instance
    
    if _reader_instance is None or api_key:
        _reader_instance = PDFMenuReader(api_key)
    
    return _reader_instance
