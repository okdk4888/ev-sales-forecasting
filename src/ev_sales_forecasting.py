"""
EV Sales Forecasting — Core Module

Model strategy:
  1. Predict log growth rates: log(sales_t) - log(sales_{t-1})
  2. Use GradientBoosting to capture non-linear patterns
  3. Blend model predictions with lag-1 baseline at optimized weight
"""

import math
import re
import unicodedata

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.impute import SimpleImputer
from sklearn.linear_model import Ridge
from sklearn.metrics import mean_absolute_error, mean_squared_error, r2_score
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from pathlib import Path


# ──────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────

WB_INDICATORS = {
    'gdp_per_capita': 'API_NY.GDP.PCAP.CD_DS2_en_csv_v2_245.csv',
    'inflation_cpi':  'API_FP.CPI.TOTL.ZG_DS2_en_csv_v2_287.csv',
    'unemployment':   'API_SL.UEM.TOTL.ZS_DS2_en_csv_v2_36.csv',
}

COUNTRY_NAME_OVERRIDES = {
    'Czech Republic': 'Czechia',
    'Korea':          'Korea, Rep.',
    'Russia':         'Russian Federation',
    'Slovakia':       'Slovak Republic',
    'Turkiye':        'Türkiye',
    'USA':            'United States',
    'Viet Nam':       'Vietnam',
}

TARGET_COLUMN        = 'ev_sales'
CATEGORICAL_FEATURES = ['region_country']

NUMERIC_FEATURES = [
    'lag1_log_ev_sales', 'lag2_log_ev_sales', 'lag1_log_ev_stock', 'year_index',
    'lag1_log_gdp', 'lag1_inflation_cpi', 'lag1_unemployment',
    'sales_growth_rate', 'share_change', 'stock_sales_ratio', 'lag1_ev_sales_share',
]

NUMERIC_FEATURES_ORIG = [
    'lag1_log_ev_sales', 'lag2_log_ev_sales', 'lag1_log_ev_stock', 'year_index',
]

DEFAULT_BLEND_WEIGHT = 0.6


# ──────────────────────────────────────────────
# Path Management
# ──────────────────────────────────────────────

class ProjectPaths:
    def __init__(self, root):
        self.root = Path(root)

    @property
    def data_raw(self):
        return self.root / 'data' / 'raw'

    @property
    def iea_file(self):
        return self.data_raw / 'iea_ev_data_explorer_2025.xlsx'

    @property
    def wb_metadata_file(self):
        return (
            self.data_raw / 'world_bank' / 'gdp_per_capita'
            / 'Metadata_Country_API_NY.GDP.PCAP.CD_DS2_en_csv_v2_245.csv'
        )

    @property
    def wb_indicator_dir(self):
        return self.data_raw / 'world_bank'

    @property
    def figures_dir(self):
        d = self.root / 'figures'
        d.mkdir(parents=True, exist_ok=True)
        return d


# ──────────────────────────────────────────────
# Utilities
# ──────────────────────────────────────────────

def _normalize_name(value):
    """Normalize country name: strip accents, lowercase, keep alphanumeric only."""
    value = unicodedata.normalize('NFKD', value)
    value = ''.join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = re.sub(r'[^a-z0-9]+', '', value)
    return value


def _load_wb_country_lookup(metadata_file):
    """Load World Bank metadata for country code + normalized name mapping."""
    metadata = pd.read_csv(metadata_file)
    metadata = metadata.rename(
        columns={'Country Code': 'iso3', 'TableName': 'wb_country_name_lookup'}
    )
    metadata['normalized_name'] = metadata['wb_country_name_lookup'].map(_normalize_name)
    return metadata[['iso3', 'wb_country_name_lookup', 'normalized_name']].drop_duplicates()


# ──────────────────────────────────────────────
# Data Loading
# ──────────────────────────────────────────────

def load_iea_panel(iea_file, wb_metadata_file):
    """Load IEA Excel into a country-year long table, aligned with World Bank codes."""
    raw = pd.read_excel(iea_file, sheet_name='GEVO_EV_2025')
    raw = raw.loc[
        (raw['category'] == 'Historical')
        & (raw['mode'] == 'Cars')
        & (raw['Aggregate group'] == 'Other')
    ].copy()

    metrics = {
        'EV sales':       'ev_sales',
        'EV sales share': 'ev_sales_share',
        'EV stock':       'ev_stock',
        'EV stock share': 'ev_stock_share',
    }

    frames = []
    for parameter, metric_name in metrics.items():
        subset = raw.loc[raw['parameter'] == parameter, ['region_country', 'year', 'value']]
        aggregation = 'sum' if parameter in {'EV sales', 'EV stock'} else 'mean'
        subset = (
            subset.groupby(['region_country', 'year'], as_index=False)['value']
            .agg(aggregation)
            .rename(columns={'value': metric_name})
        )
        frames.append(subset)

    panel = frames[0]
    for frame in frames[1:]:
        panel = panel.merge(frame, on=['region_country', 'year'], how='outer')

    panel['year'] = panel['year'].astype(int)
    panel = panel.sort_values(['region_country', 'year']).reset_index(drop=True)

    country_lookup = _load_wb_country_lookup(wb_metadata_file)
    panel['wb_country_name'] = panel['region_country'].replace(COUNTRY_NAME_OVERRIDES)
    panel['normalized_name'] = panel['wb_country_name'].map(_normalize_name)
    panel = panel.merge(country_lookup, on='normalized_name', how='left')
    panel['wb_country_name'] = panel['wb_country_name_lookup'].fillna(panel['wb_country_name'])
    panel = panel.drop(columns=['normalized_name', 'wb_country_name_lookup'])
    panel['country_matched'] = panel['iso3'].notna()
    return panel


def load_world_bank_indicator(indicator_file, value_name):
    """Reshape World Bank wide CSV (years as columns) into long format."""
    wide = pd.read_csv(indicator_file, skiprows=4)
    year_columns = [col for col in wide.columns if re.fullmatch(r'\d{4}', str(col))]
    long = wide.melt(
        id_vars=['Country Name', 'Country Code', 'Indicator Name', 'Indicator Code'],
        value_vars=year_columns,
        var_name='year',
        value_name=value_name,
    )
    long = long.rename(columns={'Country Name': 'wb_country_name', 'Country Code': 'iso3'})
    long['year'] = long['year'].astype(int)
    return long[['wb_country_name', 'iso3', 'year', value_name]]


def load_macro_panel(paths):
    """Merge GDP, inflation, and unemployment into one macro panel."""
    frames = []
    for value_name, file_name in WB_INDICATORS.items():
        indicator_dir = paths.wb_indicator_dir / value_name
        frames.append(load_world_bank_indicator(indicator_dir / file_name, value_name))

    macro = frames[0]
    for frame in frames[1:]:
        macro = macro.merge(frame, on=['wb_country_name', 'iso3', 'year'], how='outer')
    return macro.sort_values(['iso3', 'year']).reset_index(drop=True)


# ──────────────────────────────────────────────
# Feature Engineering
# ──────────────────────────────────────────────

def build_modeling_dataset(paths):
    """Merge IEA and macro data, then build all features."""
    iea_panel = load_iea_panel(paths.iea_file, paths.wb_metadata_file)
    macro = load_macro_panel(paths)

    panel = iea_panel.merge(
        macro, on=['wb_country_name', 'iso3', 'year'],
        how='left', validate='many_to_one',
    )
    panel = panel.sort_values(['region_country', 'year']).reset_index(drop=True)

    lag_columns = [
        TARGET_COLUMN, 'ev_sales_share', 'ev_stock', 'ev_stock_share',
        'gdp_per_capita', 'inflation_cpi', 'unemployment',
    ]
    for column in lag_columns:
        panel[f'lag1_{column}'] = panel.groupby('region_country')[column].shift(1)
    panel['lag2_ev_sales'] = panel.groupby('region_country')[TARGET_COLUMN].shift(2)

    base_year = int(panel['year'].min())
    panel['year_index']        = panel['year'] - base_year
    panel['log_ev_sales']      = np.log1p(panel[TARGET_COLUMN])
    panel['lag1_log_ev_sales'] = np.log1p(panel['lag1_ev_sales'].clip(lower=0))
    panel['lag2_log_ev_sales'] = np.log1p(panel['lag2_ev_sales'].fillna(0).clip(lower=0))
    panel['lag1_log_ev_stock'] = np.log1p(panel['lag1_ev_stock'].fillna(0).clip(lower=0))

    panel['sales_growth_rate'] = (
        (panel['lag1_ev_sales'] - panel['lag2_ev_sales'])
        / panel['lag2_ev_sales'].replace(0, np.nan)
    ).clip(-5, 10)

    panel['share_change'] = (
        panel['lag1_ev_sales_share']
        - panel.groupby('region_country')['ev_sales_share'].shift(2)
    )

    panel['lag1_log_gdp'] = np.log1p(panel['lag1_gdp_per_capita'].fillna(0).clip(lower=0))
    panel['stock_sales_ratio'] = (
        panel['lag1_ev_stock'] / panel['lag1_ev_sales'].replace(0, np.nan)
    ).clip(0, 50)

    panel['target_growth'] = (
        np.log1p(panel[TARGET_COLUMN])
        - np.log1p(panel['lag1_ev_sales'].clip(lower=0))
    )
    return panel


def make_train_valid_test_split(panel):
    """Split dataset by year."""
    modeling = panel.loc[
        panel['country_matched']
        & panel[TARGET_COLUMN].notna()
        & panel['lag1_ev_sales'].notna()
    ].copy()

    return {
        'train':      modeling.loc[modeling['year'] <= 2021].copy(),
        'validation': modeling.loc[modeling['year'].between(2022, 2023)].copy(),
        'test':       modeling.loc[modeling['year'] == 2024].copy(),
        'train_full': modeling.loc[modeling['year'] <= 2023].copy(),
    }


# ──────────────────────────────────────────────
# Modeling
# ──────────────────────────────────────────────

def build_growth_gbr_model(random_state=42):
    """Improved: GradientBoosting on log growth rates."""
    preprocessor = ColumnTransformer(transformers=[
        ('numeric', Pipeline([('imputer', SimpleImputer(strategy='median'))]), NUMERIC_FEATURES),
        ('categorical', OneHotEncoder(handle_unknown='ignore', sparse_output=False), CATEGORICAL_FEATURES),
    ])
    return Pipeline([
        ('preprocessor', preprocessor),
        ('model', GradientBoostingRegressor(
            n_estimators=500, max_depth=3, learning_rate=0.03,
            subsample=0.8, min_samples_leaf=8, random_state=random_state,
        )),
    ])


def build_ridge_model(numeric_features=None, alpha=2.0, random_state=42):
    """Original: Ridge regression on log sales (for comparison)."""
    if numeric_features is None:
        numeric_features = NUMERIC_FEATURES_ORIG
    preprocessor = ColumnTransformer(transformers=[
        ('numeric', Pipeline([
            ('imputer', SimpleImputer(strategy='median')),
            ('scaler', StandardScaler()),
        ]), numeric_features),
        ('categorical', OneHotEncoder(handle_unknown='ignore'), CATEGORICAL_FEATURES),
    ])
    return Pipeline([('preprocessor', preprocessor), ('model', Ridge(alpha=alpha, random_state=random_state))])


def fit_growth_model(train_df):
    """Train the growth-rate GBR model."""
    model = build_growth_gbr_model()
    model.fit(train_df[NUMERIC_FEATURES + CATEGORICAL_FEATURES], train_df['target_growth'])
    return model


def fit_ridge_model(train_df, numeric_features=None):
    """Train Ridge model (for comparison)."""
    if numeric_features is None:
        numeric_features = NUMERIC_FEATURES_ORIG
    model = build_ridge_model(numeric_features)
    model.fit(train_df[numeric_features + CATEGORICAL_FEATURES], train_df['log_ev_sales'])
    return model


# ──────────────────────────────────────────────
# Prediction & Evaluation
# ──────────────────────────────────────────────

def predict_growth(model, frame, blend_weight=DEFAULT_BLEND_WEIGHT):
    """Predict growth rate -> convert to absolute sales -> blend with baseline."""
    pred_growth = model.predict(frame[NUMERIC_FEATURES + CATEGORICAL_FEATURES])
    lag1_log = np.log1p(frame['lag1_ev_sales'].clip(lower=0).to_numpy())
    pred_abs = np.expm1(lag1_log + pred_growth)
    baseline = frame['lag1_ev_sales'].to_numpy()
    return np.maximum(0.0, blend_weight * pred_abs + (1 - blend_weight) * baseline)


def predict_ridge(model, frame, blend_weight=0.5, numeric_features=None):
    """Ridge prediction (original method, for comparison)."""
    if numeric_features is None:
        numeric_features = NUMERIC_FEATURES_ORIG
    ar_pred = np.expm1(model.predict(frame[numeric_features + CATEGORICAL_FEATURES]))
    baseline = frame['lag1_ev_sales'].to_numpy()
    return np.maximum(0.0, blend_weight * ar_pred + (1 - blend_weight) * baseline)


def baseline_predict(frame):
    """Baseline: use last year's sales as the prediction."""
    return frame['lag1_ev_sales'].to_numpy()


def evaluate_predictions(actual, predicted):
    """Compute MAE, RMSE, MAPE, R-squared."""
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    positive_actual = np.where(actual <= 0, np.nan, actual)
    return {
        'mae':  float(mean_absolute_error(actual, predicted)),
        'rmse': float(math.sqrt(mean_squared_error(actual, predicted))),
        'mape': float(np.nanmean(np.abs((actual - predicted) / positive_actual)) * 100),
        'r2':   float(r2_score(actual, predicted)),
    }


def find_best_blend_weight(model, val_df, predict_fn, grid=None):
    """Grid-search for optimal blend weight on the validation set."""
    if grid is None:
        grid = np.arange(0, 1.01, 0.05)
    best_w, best_mape = 0.5, 1e9
    for w in grid:
        mape = evaluate_predictions(val_df[TARGET_COLUMN], predict_fn(model, val_df, w))['mape']
        if mape < best_mape:
            best_w, best_mape = round(w, 2), mape
    return best_w, best_mape


def collect_metrics(splits, model_growth, blend_weight, model_ridge=None, ridge_blend=0.5):
    """Collect metrics for all models on validation and test sets."""
    rows = []
    for split_name in ('validation', 'test'):
        frame = splits[split_name]
        actual = frame[TARGET_COLUMN]
        bp = baseline_predict(frame)
        rows.append({'split': split_name, 'model': 'Lag-1 baseline', **evaluate_predictions(actual, bp)})
        if model_ridge is not None:
            rp = predict_ridge(model_ridge, frame, ridge_blend)
            rows.append({'split': split_name, 'model': f'Original Ridge (blend={ridge_blend})', **evaluate_predictions(actual, rp)})
        gp = predict_growth(model_growth, frame, blend_weight)
        rows.append({'split': split_name, 'model': f'Growth GBR (blend={blend_weight})', **evaluate_predictions(actual, gp)})
    return pd.DataFrame(rows)


def top_country_summary(frame, predictions, top_n=15):
    """Per-country prediction details."""
    result = frame.loc[:, ['region_country', 'year', TARGET_COLUMN]].copy()
    result['predicted_ev_sales'] = predictions
    result['error'] = result[TARGET_COLUMN] - result['predicted_ev_sales']
    result['pct_error'] = result['error'] / result[TARGET_COLUMN].replace(0, np.nan) * 100
    return result.sort_values(TARGET_COLUMN, ascending=False).head(top_n).reset_index(drop=True)
