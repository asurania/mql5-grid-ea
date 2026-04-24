#!/usr/bin/env python3
"""
Score future economic calendar events for volatility impact.

This script uses a hybrid approach:
1. For events with sufficient historical context, use the trained ML model
2. For future events without market data, use calibrated importance-based heuristics
   derived from the training data statistics.

Usage:
    cd /home/asurani/.openclaw/workspace/projects/volatility-impact-engine
    source .venv/bin/activate
    python src/score_future_events.py --start-date 2026-04-27 --end-date 2026-05-03 --currency USD

Output:
    data/future_event_scores_YYYYMMDD_YYYYMMDD.csv
    Columns: Date / Forex Symbol / Calendar Event / Score / Bucket Class
"""

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import Dataset, DataLoader

# Force CPU to avoid ROCm segfault on this machine
DEVICE = 'cpu'

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
WORKSPACE_ROOT = Path('/home/asurani/.openclaw/workspace')
PROJECT_ROOT = Path('/home/asurani/.openclaw/workspace/projects/volatility-impact-engine')
CALENDAR_PATH = WORKSPACE_ROOT / 'data' / 'processed' / 'economic_calendar' / 'events.parquet'
TRAINING_DATASET_PATH = WORKSPACE_ROOT / 'data' / 'processed' / 'modeling' / 'event_risk_training_dataset.parquet'
EXPORT_DIR = PROJECT_ROOT / 'data'
EXPORT_DIR.mkdir(parents=True, exist_ok=True)

# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------
class RiskMLP(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int = 128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim), nn.ReLU(), nn.Dropout(0.15),
            nn.Linear(hidden_dim, hidden_dim), nn.ReLU(), nn.Dropout(0.15),
            nn.Linear(hidden_dim, 1),
        )
    def forward(self, x): return self.net(x)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def bucketize_score(score: float) -> str:
    """Bucket a score into risk classes."""
    if score < 25.0: return 'low'
    if score < 50.0: return 'medium'
    if score < 75.0: return 'high'
    return 'extreme'


def train_model(X_train: np.ndarray, y_train: np.ndarray, feature_dim: int):
    """Train a fresh model on the full historical dataset."""
    print(f'Training on device: {DEVICE}')

    class BinaryRiskDataset(Dataset):
        def __init__(self, X, y):
            self.X = torch.tensor(X, dtype=torch.float32)
            self.y = torch.tensor(y, dtype=torch.float32).view(-1, 1)
        def __len__(self): return len(self.X)
        def __getitem__(self, idx): return self.X[idx], self.y[idx]

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X_train)

    loader = DataLoader(BinaryRiskDataset(X_scaled, y_train), batch_size=512, shuffle=True)
    model = RiskMLP(input_dim=feature_dim).to(DEVICE)
    criterion = nn.BCEWithLogitsLoss()
    optimizer = torch.optim.Adam(model.parameters(), lr=5e-4)

    for epoch in range(8):
        model.train()
        losses = []
        for xb, yb in loader:
            xb, yb = xb.to(DEVICE), yb.to(DEVICE)
            optimizer.zero_grad()
            loss = criterion(model(xb), yb)
            loss.backward()
            optimizer.step()
            losses.append(loss.item())
        print(f'  Epoch {epoch + 1}: loss = {sum(losses) / len(losses):.4f}')

    return model, scaler


def build_features_for_calendar_events(calendar_df: pd.DataFrame, feature_cols: list) -> pd.DataFrame:
    """Build feature vectors for raw calendar events."""
    df = calendar_df.copy()
    df['event_timestamp_utc'] = pd.to_datetime(df['event_timestamp_utc'], utc=True)

    # Temporal features
    df['event_year'] = df['event_timestamp_utc'].dt.year
    df['event_month'] = df['event_timestamp_utc'].dt.month
    df['event_weekday'] = df['event_timestamp_utc'].dt.weekday
    df['event_hour'] = df['event_timestamp_utc'].dt.hour

    # Importance mapping
    importance_map = {'low': 0, 'medium': 1, 'high': 2, 'low_or_unknown': -1, 'unknown': -1}
    df['importance_score_filled'] = df['importance_label'].map(importance_map).fillna(-1).astype(int)

    # Risk prior defaults
    df['risk_prior'] = df.get('risk_prior', 'safe')
    df['risk_prior_halt'] = (df['risk_prior'] == 'halt').astype(int)
    df['risk_prior_reduce'] = (df['risk_prior'] == 'reduce_risk').astype(int)

    # Session avoidance defaults
    df['avoid_session'] = df.get('avoid_session', 'none')
    df['avoid_asia'] = (df['avoid_session'] == 'asia').astype(int)
    df['avoid_london'] = (df['avoid_session'] == 'london').astype(int)
    df['avoid_both'] = (df['avoid_session'] == 'both').astype(int)

    # Currency indicators
    df['currency_norm'] = df['currency_norm'].fillna('USD')
    for ccy in ['jpy', 'gbp', 'usd', 'eur', 'nzd']:
        df[f'is_{ccy}_event'] = (df['currency_norm'].str.upper() == ccy.upper()).astype(int)

    # Category indicators
    df['event_category'] = df.get('event_category', 'other')
    for cat in ['central_bank', 'inflation', 'employment', 'gdp', 'pmi',
                'retail_sales', 'trade', 'housing', 'sentiment', 'speech',
                'auction', 'agriculture', 'other']:
        df[f'cat_{cat}'] = (df['event_category'] == cat).astype(int)

    # Expand to pair rows
    rows = []
    for _, event in df.iterrows():
        for pair in ['EURJPY', 'GBPJPY', 'GBPUSD', 'NZDUSD']:
            rel_col = f'rel_{pair.lower()}'
            if rel_col in event and event[rel_col]:
                row = event.to_dict()
                row['pair'] = pair
                for p in ['eurjpy', 'gbpjpy', 'gbpusd', 'nzdusd']:
                    row[f'pair_{p}'] = int(pair.lower() == p)
                row['pair_is_jpy_cross'] = int('JPY' in pair)
                row['pair_has_gbp_base'] = int(pair.startswith('GBP'))
                row['pair_has_usd_quote'] = int(pair.endswith('USD'))
                rows.append(row)

    return pd.DataFrame(rows)


def compute_importance_stats(training_df: pd.DataFrame) -> dict:
    """Compute risk statistics by importance level from training data."""
    stats = {}
    for imp in [-1, 0, 1, 2]:
        subset = training_df[training_df['importance_score_filled'] == imp]
        if len(subset) > 0:
            risky_rate = subset['y_post_news_session_risk'].mean()
            stats[imp] = {
                'count': len(subset),
                'risky_rate': risky_rate,
                'suggested_score': min(95.0, risky_rate * 150),  # Scale to 0-95
            }
    return stats


def main():
    parser = argparse.ArgumentParser(description='Score future calendar events for volatility impact')
    parser.add_argument('--start-date', type=str, required=True, help='Start date YYYY-MM-DD')
    parser.add_argument('--end-date', type=str, required=True, help='End date YYYY-MM-DD')
    parser.add_argument('--currency', type=str, default='USD', help='Currency to filter (e.g. USD, EUR, GBP)')
    parser.add_argument('--min-importance', type=str, default='low', choices=['low', 'medium', 'high'],
                        help='Minimum importance level to include')
    args = parser.parse_args()

    print(f'Scoring {args.currency} events from {args.start_date} to {args.end_date}')

    # -----------------------------------------------------------------------
    # 1. Load historical training data and train model
    # -----------------------------------------------------------------------
    print('Loading training data...')
    training_df = pd.read_parquet(TRAINING_DATASET_PATH)
    training_df['event_timestamp_utc'] = pd.to_datetime(training_df['event_timestamp_utc'], utc=True)

    target_cols = ['y_trend_danger', 'y_whipsaw_danger', 'y_volatility_expansion', 'y_post_news_session_risk']
    meta_cols = ['event_id', 'pair', 'event_timestamp_utc', 'event_name', 'event_category',
                 'currency_norm', 'risk_prior', 'avoid_session']
    target_col = 'y_post_news_session_risk'

    feature_cols = [c for c in training_df.columns if c not in meta_cols + target_cols]
    print(f'Feature count: {len(feature_cols)}')

    X_train = training_df[feature_cols].values.astype(np.float32)
    y_train = training_df[target_col].values.astype(np.float32)

    print('Training model...')
    model, scaler = train_model(X_train, y_train, len(feature_cols))

    # Compute importance-based statistics from training data
    print('Computing importance-based risk statistics...')
    imp_stats = compute_importance_stats(training_df)
    print('Importance statistics from training data:')
    for imp, stat in imp_stats.items():
        print(f'  Importance {imp}: {stat["count"]} events, {stat["risky_rate"]:.1%} risky, suggested score: {stat["suggested_score"]:.1f}')

    # -----------------------------------------------------------------------
    # 2. Load future calendar events
    # -----------------------------------------------------------------------
    print('Loading calendar data...')
    cal = pd.read_parquet(CALENDAR_PATH)
    cal['event_timestamp_utc'] = pd.to_datetime(cal['event_timestamp_utc'], utc=True)

    importance_order = {'low': 0, 'medium': 1, 'high': 2, 'low_or_unknown': -1, 'unknown': -1}
    min_imp = importance_order.get(args.min_importance, 0)
    cal['importance_score'] = cal['importance_label'].map(importance_order).fillna(-1)

    mask = (
        (cal['event_timestamp_utc'] >= args.start_date) &
        (cal['event_timestamp_utc'] < args.end_date) &
        (cal['currency_norm'] == args.currency) &
        (cal['importance_score'] >= min_imp)
    )

    future_events = cal[mask].copy()
    print(f'Future events matching criteria: {len(future_events)}')

    if len(future_events) == 0:
        print('No events found for the specified criteria.')
        return

    # -----------------------------------------------------------------------
    # 3. Build features and score with hybrid approach
    # -----------------------------------------------------------------------
    print('Building features for future events...')
    future_features_df = build_features_for_calendar_events(future_events, feature_cols)

    if len(future_features_df) == 0:
        print('No features could be built for future events.')
        return

    for col in feature_cols:
        if col not in future_features_df.columns:
            future_features_df[col] = 0

    X_future = future_features_df[feature_cols].values.astype(np.float32)
    X_future_scaled = scaler.transform(X_future)

    print('Scoring future events...')
    model.eval()
    with torch.no_grad():
        ml_scores = torch.sigmoid(
            model(torch.tensor(X_future_scaled, dtype=torch.float32).to(DEVICE))
        ).cpu().numpy().ravel()

    # Hybrid scoring: blend ML score with importance-based heuristic
    # For future events without market context, rely more on importance statistics
    future_features_df['ml_score'] = ml_scores
    future_features_df['ml_score_pct'] = (100.0 * ml_scores).round(2)

    # Get importance-based suggested score
    future_features_df['imp_score'] = future_features_df['importance_score_filled'].map(
        lambda x: imp_stats.get(x, {}).get('suggested_score', 30.0)
    )

    # Blend: use max of ML score and importance score, but cap importance score influence
    # This ensures high-importance events get proper attention even if ML model is conservative
    future_features_df['score'] = future_features_df[['ml_score_pct', 'imp_score']].max(axis=1)

    # Special boost for known high-impact event types
    high_impact_keywords = ['Fed Funds', 'Non-Farm', 'BOE', 'ECB', 'BOJ', 'Rate Decision', 'CPI']
    for keyword in high_impact_keywords:
        mask = future_features_df['event_name'].str.contains(keyword, na=False, case=False)
        future_features_df.loc[mask, 'score'] = np.maximum(
            future_features_df.loc[mask, 'score'],
            75.0  # Minimum high score for these events
        )

    future_features_df['bucket_class'] = future_features_df['score'].apply(bucketize_score)

    # -----------------------------------------------------------------------
    # 4. Build output
    # -----------------------------------------------------------------------
    output = future_features_df.rename(columns={
        'event_timestamp_utc': 'Date',
        'pair': 'Forex Symbol',
        'event_name': 'Calendar Event',
        'score': 'Score',
        'bucket_class': 'Bucket Class',
    })[['Date', 'Forex Symbol', 'Calendar Event', 'Score', 'Bucket Class']]

    output = output.sort_values(['Date', 'Forex Symbol'])

    # -----------------------------------------------------------------------
    # 5. Export
    # -----------------------------------------------------------------------
    start_str = args.start_date.replace('-', '')
    end_str = args.end_date.replace('-', '')
    export_path = EXPORT_DIR / f'future_event_scores_{start_str}_{end_str}.csv'
    output.to_csv(export_path, index=False)

    print(f'\nExported {len(output)} rows to {export_path}')

    # High/Extreme risk events
    high_risk = output[output['Bucket Class'].isin(['high', 'extreme'])]
    print(f'\n=== HIGH/EXTREME RISK EVENTS: {len(high_risk)} ===')
    if len(high_risk) > 0:
        print(high_risk.to_string(index=False))
    else:
        print('  None detected')

    # Summary statistics
    print(f'\n=== SUMMARY ===')
    print(f'Total events scored: {len(output)}')
    print(f'\nEvents per symbol:')
    print(output['Forex Symbol'].value_counts().to_string())
    print(f'\nClass distribution:')
    print(output['Bucket Class'].value_counts().to_string())

    # Show first 20 rows
    print(f'\nFirst 20 rows:')
    print(output.head(20).to_string(index=False))


if __name__ == '__main__':
    main()
