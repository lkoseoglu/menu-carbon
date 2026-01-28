# 🌱 Menu Carbon Calculator v2.0

A comprehensive carbon footprint calculator for food recipes, designed for restaurants, hotels, and food service providers.

![Version](https://img.shields.io/badge/version-2.0.0-green)
![Python](https://img.shields.io/badge/python-3.10+-blue)
![License](https://img.shields.io/badge/license-MIT-blue)

## ✨ Features

### Core Functionality
- **Recipe-based LCA calculation** - Calculate carbon footprint based on ingredients, cooking, and transport
- **80+ ingredients** - Comprehensive database with emission factors from Agribalyse, Poore & Nemecek, and other sources
- **Multiple classification systems** - Simple (LOW/MEDIUM/HIGH), Klimato (A-E), WRI Cool Food compliance

### Advanced Features
- **🌍 Multi-language support** - Turkish and English interfaces
- **📅 Seasonality adjustments** - Winter greenhouse factors for vegetables
- **🌐 Regional energy factors** - Turkey, EU, US, and global electricity emission factors
- **💡 Alternative suggestions** - AI-powered low-carbon ingredient alternatives
- **📊 Interactive charts** - Plotly-powered visualizations
- **📱 QR code generation** - Certificate verification
- **📦 Batch processing** - Process multiple recipes via CSV upload
- **🔌 REST API** - FastAPI-based endpoints for integration

### Export Options
- PNG/PDF labels for menu display
- CSV/Excel reports
- JSON API envelope for system integration

## 🚀 Quick Start

### Installation

```bash
# Clone or download the project
cd menu_carbon

# Create virtual environment (recommended)
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt
```

### Run Streamlit UI

```bash
streamlit run ui_v2.py
```

Open http://localhost:8501 in your browser.

### Run REST API

```bash
uvicorn api:app --reload --port 8000
```

API docs available at http://localhost:8000/docs

## 📁 Project Structure

```
menu_carbon/
├── ui_v2.py              # Streamlit web application
├── api.py                # FastAPI REST API
├── requirements.txt      # Python dependencies
├── README.md             # This file
├── data/
│   ├── factors.csv       # Ingredient emission factors (80+ items)
│   └── sample_batch.csv  # Example batch upload file
└── assets/
    └── methodology.pdf   # Methodology documentation
```

## 📊 Data Sources

The emission factors are sourced from:

| Source | Type | Geography |
|--------|------|-----------|
| Poore & Nemecek (2018) | Academic meta-analysis | Global |
| Agribalyse 3.1 | LCA database | EU/France |
| Ecoinvent | LCA database | Various |

## 🏷️ Classification Systems

### Simple Labels (per portion)
| Label | Range | Color |
|-------|-------|-------|
| LOW | < 500g CO₂e | 🟢 Green |
| MEDIUM | 500-1500g CO₂e | 🟡 Yellow |
| HIGH | > 1500g CO₂e | 🔴 Red |

### Klimato A-E System (normalized to 400g portion)
| Grade | Range | Description |
|-------|-------|-------------|
| A | < 400g CO₂e | Very Low Carbon |
| B | 400-900g CO₂e | Low Carbon |
| C | 900-1800g CO₂e | Medium Carbon |
| D | 1800-2600g CO₂e | High Carbon |
| E | ≥ 2600g CO₂e | Very High Carbon |

### WRI Cool Food Meals
- Breakfast: ≤ 3,590g CO₂e
- Lunch/Dinner: ≤ 5,380g CO₂e

### WWF One Planet Plate
- Target: ≤ 500g CO₂e per meal

## 🔌 API Usage

### Calculate Carbon Footprint

```bash
curl -X POST "http://localhost:8000/calculate" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Grilled Beef Köfte",
    "portions": 1,
    "ingredients": [
      {"id": "beef", "raw_weight_g": 200},
      {"id": "rice", "raw_weight_g": 60}
    ],
    "cooking": {
      "energy_type": "electricity",
      "average_power_kw": 3.0,
      "duration_min": 12.0
    }
  }'
```

### List Ingredients

```bash
curl "http://localhost:8000/ingredients?category=meat"
```

### Get Thresholds

```bash
curl "http://localhost:8000/thresholds"
```

## 📋 Batch Processing

Upload a CSV file with the following columns:

| Column | Required | Description |
|--------|----------|-------------|
| recipe_name | ✅ | Name of the recipe |
| ingredient_id | ✅ | Ingredient ID from factors.csv |
| weight_g | ✅ | Weight in grams |
| portions | ❌ | Number of portions (default: 1) |
| meal_type | ❌ | breakfast/lunch/dinner (default: lunch) |

Example CSV:
```csv
recipe_name,ingredient_id,weight_g,portions,meal_type
Izgara Köfte,beef,200,1,lunch
Izgara Köfte,onion,30,1,lunch
Pilav,rice,80,1,lunch
```

## 🔧 Configuration

### Energy Factors (g CO₂e/kWh)

| Type | Turkey | EU | US | Global |
|------|--------|----|----|--------|
| Electricity | 420 | 250 | 380 | 475 |
| Natural Gas | 200 | 200 | 200 | 200 |
| LPG | 230 | 230 | 230 | 230 |
| Wood | 30 | 30 | 30 | 30 |

### Transport Factors (g CO₂e/ton-km)

| Mode | Factor |
|------|--------|
| Road | 62 |
| Rail | 22 |
| Sea | 16 |
| Air | 602 |

## 🌐 Adding New Ingredients

Edit `data/factors.csv`:

```csv
ingredient_id,ingredient_name,ingredient_name_tr,ef_gco2e_per_g,source,geography,year,synonyms,default_portion_g,category,seasonality_winter_factor,notes
new_item,New Item,Yeni Malzeme,1.5,Your Source,Global,2024,"alias1,alias2",100,vegetable,1.0,"Your notes"
```

## 📈 Roadmap

- [ ] Carbon offset integration
- [ ] Recipe optimization AI
- [ ] Supply chain tracking
- [ ] Multi-tenant SaaS
- [ ] Mobile app

## 📄 License

MIT License - See LICENSE file for details.

## 🤝 Contributing

Contributions are welcome! Please read our contributing guidelines before submitting a PR.

## 📞 Support

- Documentation: [docs.commited.app](https://docs.commited.app)
- Email: support@commited.app
- Issues: GitHub Issues

---

**Powered by Commited** 🌱
