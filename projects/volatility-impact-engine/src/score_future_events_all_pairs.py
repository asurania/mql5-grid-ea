#!/usr/bin/env python3
"""
Score future economic calendar events for ALL major/minor forex pairs.

Usage:
    cd /home/asurani/.openclaw/workspace/projects/volatility-impact-engine
    source .venv/bin/activate
    python src/score_future_events_all_pairs.py --start-date 2026-04-27 --end-date 2026-05-03 --currency USD

Output:
    data/future_event_scores_YYYYMMDD_YYYYMMDD_all_pairs.csv
    Columns: Date / Forex Symbol / Calendar Event / Score / Bucket Class
"""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import torch
from sklearn.preprocessing import StandardScaler
from torch import nn
from torch.utils.data import Dataset, DataLoader

DEVICE = 'cpu'

# All 28 major/minor forex pairs
ALL_PAIRS = [
    'AUDCAD', 'AUDCHF', 'AUDJPY', 'AUDNZD', 'AUDUSD',
    'CADCHF', 'CADJPY', 'CHFJPY',
    'EURAUD', 'EURCAD', 'EURCHF', 'EURGBP', 'EURJPY', 'EURNZD', 'EURUSD',
    'GBPAUD', 'GBPCAD', 'GBPCHF', 'GBPJPY', 'GBPNZD', 'GBPUSD',
    'NZDCAD', 'NZDCHF', 'NZDJPY', 'NZDUSD',
    'USDCAD', 'USDCHF', 'USDJPY'
]

# Currency to affected pairs mapping
CURRENCY_TO_PAIRS = {
    'USD': ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD', 'USDCAD', 'USDCHF', 'USDJPY'],
    'EUR': ['EURUSD', 'EURJPY', 'EURGBP', 'EURAUD', 'EURCAD', 'EURCHF', 'EURNZD'],
    'GBP': ['GBPUSD', 'EURGBP', 'GBPJPY', 'GBPAUD', 'GBPCAD', 'GBPCHF', 'GBPNZD'],
    'JPY': ['USDJPY', 'EURJPY', 'GBPJPY', 'AUDJPY', 'CADJPY', 'CHFJPY', 'NZDJPY'],
    'AUD': ['AUDUSD', 'EURAUD', 'GBPAUD', 'AUDCAD', 'AUDCHF', 'AUDJPY', 'AUDNZD'],
    'NZD': ['NZDUSD', 'EURNZD', 'GBPNZD', 'AUDNZD', 'NZDCAD', 'NZDCHF', 'NZDJPY'],
    'CAD': ['USDCAD', 'EURCAD', 'GBPCAD', 'AUDCAD', 'NZDCAD', 'CADCHF', 'CADJPY'],
    'CHF': ['USDCHF', 'EURCHF', 'GBPCHF', 'AUDCHF', 'NZDCHF', 'CADCHF', 'CHFJPY'],
}

# Paths
WORKSPACE_ROOT = Path('/home/asurani/.openclaw/workspace')
PROJECT_ROOT = Path('/home/asurani/.openclaw/workspace/projects/volatility-impact-engine')
CALENDAR_PATH = WORKSPACE_ROOT / 'data' / 'processed' / 'economic_calendar' / 'events.parquet'
TRAINING_DATASET_PATH = WORKSPACE_ROOT / 'data' / 'processed' / 'modeling' / 'event_risk_training_dataset.parquet'
EXPORT_DIR = PROJECT_ROOT / 'data'
EXPORT_DIR.mkdir(parents=True, exist_ok=True)


class RiskMLP(nn.Module):
    def __init__(self, input_dim: int, hidden_dim: int = 128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, hidden_dim), nn.ReLU(), nn.Dropout(0.15),
            nn.Linear(hidden_dim, hidden_dim), nn.ReLU(), nn.Dropout(0.15),
            nn.Linear(hidden_dim, 1),
        )
    def forward(self, x): return self.net(x)


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


def compute_importance_stats(training_df: pd.DataFrame, cal: pd.DataFrame) -> dict:
    """Compute risk statistics by importance level from training data."""
    # Build importance mapping from calendar
    importance_map = {'low': 0, 'medium': 1, 'high': 2, 'low_or_unknown': -1, 'unknown': -1}
    cal_imp = cal.groupby('event_name')['importance_label'].first().to_dict()

    imp_stats = {}
    for imp_label, imp_score in importance_map.items():
        event_names = [k for k, v in cal_imp.items() if v == imp_label]
        if event_names:
            subset = training_df[training_df['event_name'].isin(event_names)]
            if len(subset) > 0:
                risky_rate = subset['y_post_news_session_risk'].mean()
                imp_stats[imp_score] = {
                    'count': len(subset),
                    'risky_rate': risky_rate,
                    'suggested_score': min(95.0, risky_rate * 150),
                }

    return imp_stats


def bucketize_score(score: float) -> str:
    if score < 25.0: return 'low'
    if score < 50.0: return 'medium'
    if score < 75.0: return 'high'
    return 'extreme'


def main():
    parser = argparse.ArgumentParser(description='Score future calendar events for all forex pairs')
    parser.add_argument('--start-date', type=str, required=True, help='Start date YYYY-MM-DD')
    parser.add_argument('--end-date', type=str, required=True, help='End date YYYY-MM-DD')
    parser.add_argument('--currency', type=str, default='USD', help='Currency to filter (e.g. USD, EUR, GBP, ALL)')
    parser.add_argument('--min-importance', type=str, default='low', choices=['low', 'medium', 'high'])
    args = parser.parse_args()

    print(f'Scoring {args.currency} events from {args.start_date} to {args.end_date}')
    print(f'All {len(ALL_PAIRS)} major/minor pairs will be included')

    # -----------------------------------------------------------------------
    # 1. Load training data and train model
    # -----------------------------------------------------------------------
    print('Loading training data...')
    training_df = pd.read_parquet(TRAINING_DATASET_PATH)
    training_df['event_timestamp_utc'] = pd.to_datetime(training_df['event_timestamp_utc'], utc=True)

    target_cols = ['y_trend_danger', 'y_whipsaw_danger', 'y_volatility_expansion', 'y_post_news_session_risk']
    meta_cols = ['event_id', 'pair', 'event_timestamp_utc', 'event_name', 'event_category',
                 'currency_norm', 'risk_prior', 'avoid_session']
    feature_cols = [c for c in training_df.columns if c not in meta_cols + target_cols]

    X_train = training_df[feature_cols].values.astype(np.float32)
    y_train = training_df['y_post_news_session_risk'].values.astype(np.float32)

    print('Training model...')
    model, scaler = train_model(X_train, y_train, len(feature_cols))

    # -----------------------------------------------------------------------
    # 2. Load calendar and compute importance stats
    # -----------------------------------------------------------------------
    print('Loading calendar data...')
    cal = pd.read_parquet(CALENDAR_PATH)
    cal['event_timestamp_utc'] = pd.to_datetime(cal['event_timestamp_utc'], utc=True)

    print('Computing importance statistics...')
    imp_stats = compute_importance_stats(training_df, cal)
    print('Importance statistics:')
    for imp, stat in imp_stats.items():
        print(f'  Importance {imp}: {stat["count"]} events, {stat["risky_rate"]:.1%} risky, suggested score: {stat["suggested_score"]:.1f}')

    # -----------------------------------------------------------------------
    # 3. Filter future events
    # -----------------------------------------------------------------------
    importance_map = {'low': 0, 'medium': 1, 'high': 2, 'low_or_unknown': -1, 'unknown': -1}
    min_imp = importance_map.get(args.min_importance, 0)
    cal['importance_score'] = cal['importance_label'].map(importance_map).fillna(-1)

    mask = (
        (cal['event_timestamp_utc'] >= args.start_date) &
        (cal['event_timestamp_utc'] < args.end_date) &
        (cal['importance_score'] >= min_imp)
    )

    # Filter by currency if specified
    if args.currency != 'ALL':
        mask = mask & (cal['currency_norm'] == args.currency)

    future_events = cal[mask].copy()
    print(f'Future events matching criteria: {len(future_events)}')

    if len(future_events) == 0:
        print('No events found for the specified criteria.')
        return

    # -----------------------------------------------------------------------
    # 4. Build output for ALL pairs
    # -----------------------------------------------------------------------
    print('Building output for all pairs...')
    rows = []
    high_impact_keywords = ['Fed Funds', 'Non-Farm', 'BOE', 'ECB', 'BOJ', 'Rate Decision', 'CPI', 'NFP', 'FOMC']

    for _, event in future_events.iterrows():
        currency = event['currency_norm']
        if currency not in CURRENCY_TO_PAIRS:
            continue

        for pair in CURRENCY_TO_PAIRS[currency]:
            imp_label = event.get('importance_label', 'low')
            imp_score = importance_map.get(imp_label, 0)
            base_score = imp_stats.get(imp_score, {}).get('suggested_score', 15.0)

            # Boost for known high-impact keywords
            event_name = event['event_name']
            for keyword in high_impact_keywords:
                if keyword in event_name:
                    base_score = max(base_score, 75.0)
                    break

            rows.append({
                'Date': event['event_timestamp_utc'],
                'Forex Symbol': pair,
                'Calendar Event': event_name,
                'Currency': currency,
                'Score': round(base_score, 2),
                'Bucket Class': bucketize_score(base_score),
                'Importance': imp_label,
            })

    output = pd.DataFrame(rows).sort_values(['Date', 'Forex Symbol'])

    # -----------------------------------------------------------------------
    # 5. Export
    # -----------------------------------------------------------------------
    start_str = args.start_date.replace('-', '')
    end_str = args.end_date.replace('-', '')
    curr_str = args.currency
    export_path = EXPORT_DIR / f'future_event_scores_{start_str}_{end_str}_{curr_str}_all_pairs.csv'
    output[['Date', 'Forex Symbol', 'Calendar Event', 'Score', 'Bucket Class']].to_csv(export_path, index=False)

    print(f'\nExported {len(output)} rows to {export_path}')

    # Summary
    high_risk = output[output['Bucket Class'].isin(['high', 'extreme'])]
    print(f'\n=== HIGH/EXTREME RISK EVENTS: {len(high_risk)} ===')
    if len(high_risk) > 0:
        print(high_risk.to_string(index=False))

    print(f'\n=== SUMMARY ===')
    print(f'Total events scored: {len(output)}')
    print(f'Unique pairs covered: {output["Forex Symbol"].nunique()}')
    print(f'Unique events: {output["Calendar Event"].nunique()}')

    print(f'\nEvents per symbol (top 10):')
    print(output['Forex Symbol'].value_counts().head(10).to_string())

    print(f'\nClass distribution:')
    print(output['Bucket Class'].value_counts().to_string())

    print(f'\nFirst 20 rows:')
    print(output.head(20).to_string(index=False))


if __name__ == '__main__':
    main()
