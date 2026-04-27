# EV Sales Forecasting — Time Series Analysis

Forecasting annual electric vehicle sales across 40+ countries using IEA and World Bank data.

## Overview

This project predicts country-level EV sales by modeling **log growth rates** with GradientBoosting, blended with a lag-1 baseline. It demonstrates a complete data science workflow: data integration, feature engineering, modeling, and evaluation.

## Results

| Split | Model | MAE | RMSE | MAPE | R² |
|-------|-------|-----|------|------|----|
| Validation | Lag-1 baseline | 71,696 | 343,459 | 37.0% | 0.88 |
| Validation | Growth GBR (blend=0.6) | **29,456** | **127,047** | **23.3%** | **0.98** |
| Test | Lag-1 baseline | 80,350 | 445,102 | 31.7% | 0.92 |
| Test | Growth GBR (blend=0.6) | **23,964** | **47,135** | **36.5%** | **0.999** |

Compared to the initial Ridge regression model (test MAPE 42.4%), the improved approach reduced MAE by 70% and RMSE by 86%.

## Key Improvements

| Change | Why it helped |
|--------|--------------|
| Predict log growth rate instead of absolute sales | Makes the model scale-invariant — China (11M) and small markets (5K) contribute equally |
| GradientBoosting instead of Ridge | Captures non-linear feature interactions without manual engineering |
| Added macro features (GDP, inflation, unemployment) | Provides economic context beyond just historical sales |
| Added growth rate & market maturity features | Captures momentum and saturation effects |
| Tuned blend weight on validation set | Optimal weight (0.6) found via grid search, replacing hardcoded 0.5 |
| Extended training data (≤2023) | More recent patterns improve generalization to 2024 |

## Data Sources

| Source | Description | Format |
|--------|-------------|--------|
| [IEA Global EV Data Explorer](https://www.iea.org/data-and-statistics/data-tools/global-ev-data-explorer) | EV sales, stock, market share by country (2010–2024) | Excel |
| [World Bank WDI](https://databank.worldbank.org/) | GDP per capita, CPI inflation, unemployment rate | CSV |

See [`data/README.md`](data/README.md) for detailed data documentation.

## Project Structure

```
├── data/
│   ├── raw/                    # Original datasets (see data/README.md)
│   └── README.md               # Data dictionary & download instructions
├── figures/                    # Generated charts (created by notebook)
├── notebooks/
│   ├── 01_ev_sales_forecasting_portfolio.ipynb   # Main analysis
│   └── ev_sales_forecasting_colab.ipynb          # Self-contained Colab version
├── src/
│   └── ev_sales_forecasting.py # Core pipeline
├── requirements.txt
├── .gitignore
├── LICENSE
└── README.md
```

## Quick Start

**Option A — Run locally:**
```bash
git clone https://github.com/<your-username>/ev-sales-forecasting.git
cd ev-sales-forecasting
pip install -r requirements.txt

# Download data (see data/README.md) and place in data/raw/
jupyter notebook notebooks/01_ev_sales_forecasting_portfolio.ipynb
```

**Option B — Run on Google Colab:**

Upload `notebooks/ev_sales_forecasting_colab.ipynb` to [Google Colab](https://colab.research.google.com/), then follow the in-notebook prompts to upload the 5 data files. No local setup needed.

## Methodology

1. **Data integration** — Merge IEA EV panel with World Bank macro indicators via fuzzy country-name matching
2. **Feature engineering** — Lag-1/2 sales, lag-1 stock (log-transformed), year trend, country fixed effects, GDP, inflation, unemployment, sales growth rate, share change, stock-sales ratio
3. **Modeling** — GradientBoosting on log growth rates, blended with lag-1 baseline (weight tuned on validation set)
4. **Evaluation** — Train ≤2021 → validate 2022–2023 (tune blend weight) → retrain ≤2023 → test 2024

## Limitations & Future Work

- Test MAPE (36.5%) still above naive baseline (31.7%) — small markets with rapid structural shifts drive percentage errors
- Could explore LightGBM / XGBoost with Bayesian hyperparameter tuning
- Policy variables (subsidies, emission standards) would help capture regulatory shocks
- Per-region or per-market-tier models may improve heterogeneous markets

## Tech Stack

Python · pandas · scikit-learn · matplotlib · seaborn

## License

MIT
