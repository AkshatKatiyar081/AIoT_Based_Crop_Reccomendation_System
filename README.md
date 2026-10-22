# Kisan Mitra: AIoT Crop, Fertilizer and Irrigation Advisory for Pune District

Kisan Mitra tells a Pune district farmer which crops suit their soil, what each crop is likely to earn at today's mandi prices, how to split the farm across crops, how much fertilizer to apply at each crop stage and when to irrigate. It uses models trained on real Soil Health Card data from Pune, live Agmarknet prices, and an ESP32 field node connected over MQTT.

Design Experience (DE) project. The problem statement comes from our DE1 literature review of 25 smart agriculture papers.

## What it does

- **Crop recommendation** from the farmer's Soil Health Card (11 values: pH, OC, N, P, K, S, Zn, B, Fe, Mn, Cu). The app splits crops into "sow now" and "later this year" using season and rainfall rules.
- **Confidence check** that warns when a soil card is unlike the Pune training data.
- **Fertilizer plan**:
  - the predicted Soil Health Card fertilizer combinations
  - doses as DAP-based and SSP-based products, in kg, bags and rupees (official bag prices)
  - a **stage-wise schedule** with a date for every split (basal, tillering, flowering...) counted from the sowing date, and a rain warning when urea is due before heavy rain
  - micronutrient corrections and organic manure advice
- **Market prices and profit.** Today's mandi price for each crop (Pune district markets, else the Maharashtra median, from data.gov.in). Profit is estimated from the price in the crop's harvest month over the last 5 years, the district yield and the cost of cultivation, as a bad-year / typical / good-year range.
- **Farm planner.** The farmer enters total land, number of plots and irrigated land. A mixed-integer program chooses the crops and the area for each plot for the highest expected profit: each crop takes 10–50% of the farm, irrigated crops fit the irrigated land, and the farmer can fix one crop. Each plot gets its own fertilizer schedule, and the plan is compared with growing the single best crop.
- **Upcoming tasks.** Saved crops show their next fertilizer steps on the dashboard.
- **Smart irrigation.** The ESP32 reports soil moisture, temperature and humidity. The backend switches the pump using the crop's moisture band and the 24-hour rain forecast. Modes: auto, manual, and a safety cut-off.
- **Live weather** for 13 Pune talukas (Open-Meteo) and a **Pune district soil profile**.
- **User accounts and crop history.**

## Architecture

| Layer | Components |
| --- | --- |
| 1. Perception | ESP32 field node (Wokwi): DHT22, soil moisture probe, relay driving the pump |
| 2. Network | MQTT broker (`<prefix>/sensor` up, `<prefix>/pump` down, retained), Open-Meteo API, data.gov.in API (Agmarknet mandi prices) |
| 3. Intelligence | Flask backend: crop model, fertilizer models, confidence check, agronomy rules, fertilizer scheduler, price and profit engine, farm planner (MILP), irrigation controller, field simulator fallback |
| 4. Application | Web dashboard, SQLite database |

## Models

All three are Random Forests (scikit-learn, 300 trees). They were evaluated with 5 rounds of 5-fold cross-validation. Folds are grouped by soil profile, so the same soil is never used for both training and testing.

| Model | Training data | Result on unseen soil | Simple baseline |
| --- | --- | --- | --- |
| Crop suitability (17 crops, multi-label) | 130 unique Pune soil samples | First suggestion suitable 94.9% | 58.5% (always suggest the most popular crops) |
| Fertilizer combination 1 (4 classes) | 562 soil + crop pairs | 96.2% accuracy | 82.2% (most common combination for the crop) |
| Fertilizer combination 2 (13 classes) | 562 soil + crop pairs | 87.1% accuracy | 64.1% (most common combination for the crop) |

## Project structure

```
backend/
  app.py              Flask app and entry point
  routes.py           REST API
  auth.py, database.py
  recommender.py      crop model + season, water and confidence logic
  fertilizer.py       fertilizer combinations, doses, costs, stage-wise schedule
  market.py           live mandi prices, harvest-month prices, yields, profit
  planner.py          farm planner (mixed-integer program, scipy)
  irrigation.py       pump controller
  mqtt_service.py     MQTT link + simulator fallback
  weather.py          Open-Meteo client
  district.py         Pune district soil profile
  soil_ratings.py     soil test rating bands and feature encoding
  field_sim.py        simulated field node
  knowledge/          crop facts, fertilizer codes, taluka locations (with sources)
frontend/             login and dashboard (HTML, CSS, JavaScript)
ml/                   model training and price / yield download scripts
models/               trained models and their metrics
data/                 Pune Soil Health Card datasets, GIPE district data, mandi price history, yields
tests/                automated tests (unittest)
wokwi/                ESP32 firmware (PlatformIO) and Wokwi circuit
sensor_simulator.py   Python stand-in for the ESP32 over MQTT
```

## Setup (Windows, PowerShell)

1. Create the environment and install the dependencies:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r backend\requirements.txt
```

2. Copy `backend\.env.example` to `backend\.env`:
   - Set a random `SECRET_KEY`.
   - Set a unique `MQTT_TOPIC_PREFIX`, e.g. `kisanmitra/your-team-name`.
   - Put the same prefix in `TOPIC_PREFIX` in `wokwi\src\sketch.ino`.

   - For live mandi prices, get a free API key at [data.gov.in](https://data.gov.in) (sign up, then My Account → API key) and set `DATA_GOV_IN_API_KEY`. Without it the app still works, using the stored price history, but shows no live price.

   The default broker is the free public `broker.hivemq.com`, which needs no account.

## Run

```powershell
python backend\app.py
```

Open http://localhost:5000 and register an account. On the dashboard, click **Load a real Pune soil card**, then **Get Recommendation**.

The irrigation panel shows simulated readings until a field node publishes. To add one, use either option below.

**Python simulator** (in a second terminal):

```powershell
python sensor_simulator.py Haveli
```

**ESP32 in Wokwi:**

1. Install the Wokwi extension and activate a free licence.
2. Build the firmware (one-time setup: `pip install platformio`):

```powershell
cd wokwi
..\.venv\Scripts\pio.exe run
```

3. Open `diagram.json` and run **Wokwi: Start Simulator**.

Turn the soil moisture knob to watch the pump LED switch.

## Tests

```powershell
python -m unittest discover -s tests -v
```

40 tests run offline (weather and live prices are stubbed, and a temporary database is used). They cover the fertilizer schedule (splits add up, DAP nitrogen carry-over, rain warnings), prices and profit arithmetic, the farm planner (rules always hold, and the optimiser matches a brute-force search on small farms), the irrigation controller (hysteresis, rain skip, safety cut-off) and the HTTP API.

## Retrain the models and refresh the data

```powershell
python ml\train_crop_model.py
python ml\train_fertilizer_model.py
python ml\fetch_market_history.py
python ml\fetch_pune_yields.py
```

The training scripts write a model and a metrics file to `models\`. The fetch scripts need `DATA_GOV_IN_API_KEY`. They download Pune-district mandi prices and crop yields to `data\processed\`. Refresh the price history every few months.

## Data sources

- Vispute, S. & Sankhla, K. (2026). [Soil Nutrient Dataset for Crop Advice, Pune](https://data.mendeley.com/datasets/6n3jjhncbp). Mendeley Data. CC BY 4.0.
- Vispute, S. et al. (2026). [Soil Macro Nutrient Dataset for Fertilizer Combinations Advice, Pune](https://data.mendeley.com/datasets/tfvgnm8rxt/1). Mendeley Data. CC BY 4.0.
- Vispute, S. (2026). [Soil Macro Nutrient Dataset for Organic Fertilizer Advice, Pune](https://data.mendeley.com/datasets/hr7vg2vs5x/1). Mendeley Data. CC BY 4.0.
- Vhankade, P. (2026). [Maharashtra district soil nutrient stress data](https://doi.org/10.7910/DVN/QPAW2H). Harvard Dataverse. CC BY 4.0.
- Fertilizer doses and sowing windows: MPKV Rahuri, Dr. PDKV Akola, Dr. BSKKV Dapoli and ICAR publications. Each crop's sources and verification status are in `backend/knowledge/crops.json`.
- Fertilizer schedules (split timing): MPKV, PDKV, AICRP and ICAR package-of-practices. Each crop's schedule is marked verified, partial or general practice in `crops.json`.
- Mandi prices: Agmarknet via data.gov.in, [current daily prices](https://data.gov.in/resource/current-daily-price-various-commodities-various-markets-mandi) (live) and variety-wise daily prices for Pune district since 2021 (history).
- Yields: data.gov.in district-wise crop production statistics (Pune, 2010–14), and NHB *Horticultural Statistics at a Glance 2018* for vegetables.
- Fertilizer prices: official maximum retail prices of urea and DAP; MOP and SSP from 2023-24 average retail prices. Sugarcane price: the 2025-26 Fair and Remunerative Price (₹355 per quintal).
- Weather: [Open-Meteo](https://open-meteo.com).

## Limitations

- The training data covers 8 villages in 5 of Pune's 13 talukas.
- Cucumber and spinach doses, and most cost-per-hectare figures, are estimates.
- District yields are averages that include rain-fed fields and older years, so profit for a well-managed irrigated field is likely understated. Wheat, jowar and bajra can show a loss for this reason.
- Spinach and methi have no published yield, so they get no profit estimate and are left out of the farm plan.
- Profit uses past harvest-month prices; it is an expectation with a range, not a forecast.
- The field node runs in simulation and has not been calibrated in a real field.

## Security

- Keep `backend/.env` private. It is excluded by `.gitignore`.
- Never put broker passwords or API tokens (including the data.gov.in key) in the firmware or any committed file.
