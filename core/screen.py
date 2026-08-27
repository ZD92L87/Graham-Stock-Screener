import pandas as pd
import os

def filter(df):
    # Do not drop a stock just because a fundamental field is missing from the
    # active data source: only enforce a criterion when its value is available.
    pe = df["PE"]
    pb = df["PB"]
    return df[
        (pe.isna() | (pe < 15))
        & (pb.isna() | (pb < 1.5))
        & ((pe * pb).isna() | ((pe * pb) < 22.5))
        & (df["DebtToEquity"].isna() | (df["DebtToEquity"] < 0.5))
        & (df["CurrentRatio"].isna() | (df["CurrentRatio"] > 1.5))
        & (df["DividendYield"].isna() | (df["DividendYield"] > 0.02))
        & (df["EPS"].isna() | (df["EPS"] > 0))
        & (df["MarketCap"].isna() | (df["MarketCap"] > 500_000_000))
    ]

def apply_filter(file_path, market):
    df = pd.read_csv(file_path, encoding='utf-8')
    filtered_df = filter(df)
    os.makedirs('results', exist_ok=True)
    filtered_df.to_csv(f"results/filtered_{market}.csv", index=False, encoding='utf-8')
    print(f"Filtered stocks saved to 'results/filtered_{market}.csv'")
    return filtered_df 
