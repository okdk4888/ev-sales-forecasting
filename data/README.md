# Data Documentation

This project uses publicly available data from the IEA and World Bank. Raw data files are **not included in the repository** due to size and licensing — download them manually using the links below.

## Download Instructions

### 1. IEA Global EV Data Explorer

- **URL**: https://www.iea.org/data-and-statistics/data-tools/global-ev-data-explorer
- **File**: `iea_ev_data_explorer_2025.xlsx`
- **How**: Click "Download all data" on the page, save the Excel file
- **Place in**: `data/raw/`

### 2. World Bank — GDP per Capita

- **URL**: https://data.worldbank.org/indicator/NY.GDP.PCAP.CD
- **How**: Click "Download" → CSV
- **Files needed**:
  - `API_NY.GDP.PCAP.CD_DS2_en_csv_v2_245.csv` (main data)
  - `Metadata_Country_API_NY.GDP.PCAP.CD_DS2_en_csv_v2_245.csv` (country metadata, used for name matching)
- **Place in**: `data/raw/world_bank/gdp_per_capita/`

### 3. World Bank — Inflation (CPI)

- **URL**: https://data.worldbank.org/indicator/FP.CPI.TOTL.ZG
- **Files needed**: `API_FP.CPI.TOTL.ZG_DS2_en_csv_v2_287.csv`
- **Place in**: `data/raw/world_bank/inflation_cpi/`

### 4. World Bank — Unemployment

- **URL**: https://data.worldbank.org/indicator/SL.UEM.TOTL.ZS
- **Files needed**: `API_SL.UEM.TOTL.ZS_DS2_en_csv_v2_36.csv`
- **Place in**: `data/raw/world_bank/unemployment/`

## Expected Directory Structure

```
data/
├── raw/
│   ├── iea_ev_data_explorer_2025.xlsx
│   └── world_bank/
│       ├── gdp_per_capita/
│       │   ├── API_NY.GDP.PCAP.CD_DS2_en_csv_v2_245.csv
│       │   └── Metadata_Country_API_NY.GDP.PCAP.CD_DS2_en_csv_v2_245.csv
│       ├── inflation_cpi/
│       │   └── API_FP.CPI.TOTL.ZG_DS2_en_csv_v2_287.csv
│       └── unemployment/
│           └── API_SL.UEM.TOTL.ZS_DS2_en_csv_v2_36.csv
└── README.md    ← this file
```

## Data Dictionary

### IEA Panel (after processing)

| Column | Type | Description |
|--------|------|-------------|
| `region_country` | str | Country or region name (IEA naming) |
| `year` | int | Calendar year (2010–2024) |
| `ev_sales` | float | Annual EV sales (BEV + PHEV, passenger cars) |
| `ev_sales_share` | float | EV share of total car sales (0–1) |
| `ev_stock` | float | Cumulative EV fleet size |
| `ev_stock_share` | float | EV share of total car stock (0–1) |
| `iso3` | str | ISO 3166-1 alpha-3 country code (from World Bank matching) |
| `country_matched` | bool | Whether IEA country matched to a World Bank country |

### World Bank Indicators

| Indicator | Code | Unit | Source |
|-----------|------|------|--------|
| GDP per capita | NY.GDP.PCAP.CD | Current USD | World Bank WDI |
| Inflation (CPI) | FP.CPI.TOTL.ZG | Annual % | World Bank WDI |
| Unemployment | SL.UEM.TOTL.ZS | % of total labor force (ILO estimate) | World Bank WDI |

### Engineered Features

| Feature | Description |
|---------|-------------|
| `lag1_log_ev_sales` | log(1 + last year's EV sales) |
| `lag2_log_ev_sales` | log(1 + EV sales 2 years ago) |
| `lag1_log_ev_stock` | log(1 + last year's EV stock) |
| `year_index` | Year minus base year (2010), captures time trend |
| `lag1_log_gdp` | log(1 + last year's GDP per capita) |
| `lag1_inflation_cpi` | Last year's CPI inflation rate |
| `lag1_unemployment` | Last year's unemployment rate |
| `sales_growth_rate` | (lag1_sales - lag2_sales) / lag2_sales, clipped to [-5, 10] |
| `share_change` | Change in EV market share over 2 years |
| `stock_sales_ratio` | lag1_stock / lag1_sales, clipped to [0, 50] |
| `target_growth` | log(1 + sales_t) - log(1 + sales_{t-1}), the prediction target |

## Notes

- IEA data is typically updated in July each year
- World Bank indicators may have 1–2 year reporting lags for some countries
- The `v2_245` / `v2_287` / `v2_36` suffixes in filenames are World Bank version numbers and may change with future downloads — update the filenames in `ev_sales_forecasting.py` accordingly
- 55 countries/regions in IEA data; 52 successfully matched to World Bank
