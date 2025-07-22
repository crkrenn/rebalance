#!/usr/bin/env python3
"""
Rebalance script (ported from Mathematica to Python).

This version prints the columns in the following order to match your screenshot:

    target delta | delta shares | Symbol | Description | Current Value | Last Price | current fraction | target fraction

It also treats each “primary–alt” pair as a single logical position:
  • If the primary symbol is in your CSV, it uses that.
  • Otherwise, if the alt symbol is in your CSV, it uses the alt.
  • If neither is present, it still includes the primary with zero current value.
"""

import os
import pandas as pd
import math

# --- USER CONFIGURATION ---
COMPANY = "fidelity"
FILENAME = "Portfolio_Positions_Jun-04-2025.csv"  # ← Update this to your downloaded CSV
CASHOUT = -50000  # Margin + cash + fractional shares (e.g. 15000)

# (Optional) Change working directory if needed:
# PATH = "/Users/crkrenn/backblaze_restore/crkrenn/OneDrive - LLNL/personal/fidelity"
# os.chdir(PATH)

# --- STEP 1: Load positions CSV into a DataFrame ---
df = pd.read_csv(FILENAME)

# Display column names (for debugging)
print("Columns in CSV:", list(df.columns))

# --- STEP 2: Identify & clean the numeric columns ---
SYMBOL_COL = "Symbol"
DESCRIPTION_COL = "Description"
CURRENT_VALUE_COL = "Current Value"
LAST_PRICE_COL = "Last Price"

# Verify that these columns exist
for col in [SYMBOL_COL, DESCRIPTION_COL, CURRENT_VALUE_COL, LAST_PRICE_COL]:
    if col not in df.columns:
        raise ValueError(f"Expected column '{col}' not found in CSV.")

# Strip out dollar signs and commas, then convert to float
df[CURRENT_VALUE_COL] = (
    df[CURRENT_VALUE_COL]
    .astype(str)
    .str.replace(r"[\$,]", "", regex=True)
    .astype(float)
)
df[LAST_PRICE_COL] = (
    df[LAST_PRICE_COL].astype(str).str.replace(r"[\$,]", "", regex=True).astype(float)
)

# --- STEP 3: Build a lookup from Symbol -> Description (in case we need it) ---
symbol_lookup = pd.Series(df[DESCRIPTION_COL].values, index=df[SYMBOL_COL]).to_dict()

# --- STEP 4: Define your target allocation (primary ↔ alt as functional equivalent) ---
targets = [
    {"weight": 0.01, "primary": "AAPL", "alt": "AAPL"},
    {"weight": 0.14, "primary": "FCPEX", "alt": "FESM"},
    {"weight": 0.05, "primary": "FEMKX", "alt": "FEMKX"},
    {"weight": 0.09, "primary": "FIBAX", "alt": "FUAMX"},
    {"weight": 0.09, "primary": "FINPX", "alt": "FIPDX"},
    {"weight": 0.11, "primary": "FRESX", "alt": "FRESX"},
    {"weight": 0.18, "primary": "FSEVX", "alt": "FSMAX"},
    {"weight": 0.14, "primary": "FSIVX", "alt": "FSPSX"},
    {"weight": 0.145, "primary": "FUSVX", "alt": "FXAIX"},
    {"weight": 0.01, "primary": "TSLA", "alt": "TSLA"},
    {"weight": 0.01, "primary": "AMZN", "alt": "AMZN"},
    {"weight": 0.01, "primary": "CRM", "alt": "CRM"},
    {"weight": 0.005, "primary": "GOOG", "alt": "GOOG"},
    {"weight": 0.005, "primary": "GOOGL", "alt": "GOOGL"},
]

# --- STEP 5: Build df_targets so that each target entry yields exactly one row ---

rows = []
for t in targets:
    prim = t["primary"]
    alt = t["alt"]
    wgt = t["weight"]

    # 1) Try to find the primary in the CSV
    row_primary = df[df[SYMBOL_COL] == prim]
    if not row_primary.empty:
        # Use the primary row
        sym = prim
        desc = row_primary.iloc[0][DESCRIPTION_COL]
        curr_val = row_primary.iloc[0][CURRENT_VALUE_COL]
        last_pr = row_primary.iloc[0][LAST_PRICE_COL]
    else:
        # 2) Else, try to find the alt in the CSV
        row_alt = df[df[SYMBOL_COL] == alt]
        if not row_alt.empty:
            sym = alt
            desc = row_alt.iloc[0][DESCRIPTION_COL]
            curr_val = row_alt.iloc[0][CURRENT_VALUE_COL]
            last_pr = row_alt.iloc[0][LAST_PRICE_COL]
        else:
            # 3) Neither present ⇒ include primary with zero value and no price
            sym = prim
            desc = symbol_lookup.get(prim, "")
            curr_val = 0.0
            last_pr = float("nan")

    rows.append(
        {
            SYMBOL_COL: sym,
            DESCRIPTION_COL: desc,
            CURRENT_VALUE_COL: curr_val,
            LAST_PRICE_COL: last_pr,
            "target_fraction": wgt,
        }
    )

# Build the DataFrame
df_targets = pd.DataFrame(rows)

print(f"\nBuilt df_targets with {len(df_targets)} total rows (one per target entry).")
print(df_targets.to_string(index=False))

# --- STEP 6: Compute current total value of target positions ---
current_total_value = float(df_targets[CURRENT_VALUE_COL].sum())
print(f"\nCurrent total value of target positions: ${current_total_value:,.2f}")

# --- STEP 7: Compute target total value (after cashout) ---
target_total_value = current_total_value - CASHOUT
print(f"Target total value (after cashout of ${CASHOUT:,}): ${target_total_value:,.2f}")

# --- STEP 8: Add computed columns ---
df_targets["current_fraction"] = df_targets[CURRENT_VALUE_COL] / current_total_value
df_targets["target_value"] = df_targets["target_fraction"] * target_total_value
df_targets["delta_value"] = df_targets["target_value"] - df_targets[CURRENT_VALUE_COL]


# Function to compute how many shares to buy/sell
def compute_delta_shares(row):
    price = row[LAST_PRICE_COL]
    # If price is NaN or ≤ 0, we cannot compute a share count → return 0
    if pd.isna(price) or price <= 0:
        return 0
    raw = row["delta_value"] / price
    # Floor for a sell/buy calculation (positive ⇒ sell, negative ⇒ buy)
    return math.floor(raw)


df_targets["delta_shares"] = df_targets.apply(compute_delta_shares, axis=1)

# --- STEP 9: Summarize net buys/sells ---
net_delta_shares = int(df_targets["delta_shares"].sum())
print(f"\nNet delta (sum of all delta_shares): {net_delta_shares} shares")

# Split into SELL vs BUY (sell = positive delta_shares; buy = negative)
df_sell = df_targets[df_targets["delta_shares"] > 0].copy()
df_buy = df_targets[df_targets["delta_shares"] < 0].copy()

# Add cumulative totals
df_sell["cumulative_shares"] = df_sell["delta_shares"].cumsum()
df_buy["cumulative_shares"] = df_buy["delta_shares"].cumsum()

# --- STEP 10: Print results in the exact order desired ---
ordered_cols = [
    "delta_value",  # target delta
    "delta_shares",  # delta shares
    SYMBOL_COL,  # Symbol
    DESCRIPTION_COL,  # Description
    CURRENT_VALUE_COL,  # Current Value
    LAST_PRICE_COL,  # Last Price
    "current_fraction",  # current fraction
    "target_fraction",  # target fraction
]
ordered_cols = [c for c in ordered_cols if c in df_targets.columns]

# Sort by delta_value ascending (largest positive ⇒ biggest sell down to biggest negative ⇒ biggest buy)
df_targets = df_targets.sort_values("delta_value", ascending=True).reset_index(
    drop=True
)

print("\n--- REBALANCE SUMMARY ---")
print(df_targets[ordered_cols].to_string(index=False))

# (Optional) Print separate SELL / BUY lists
# print("\n--- SELL (delta_shares > 0) ---")
# if not df_sell.empty:
#     print(df_sell[ordered_cols].to_string(index=False))
# else:
#     print("No sells needed.")
#
# print("\n--- BUY (delta_shares < 0) ---")
# if not df_buy.empty:
#     print(df_buy[ordered_cols].to_string(index=False))
# else:
#     print("No buys needed.")

# --- STEP 11: Summary stats ---
print(f"\nTotal positions considered: {len(df_targets)}")
print(f"Sum of current values: ${current_total_value:,.2f}")
print(f"Sum of target values:  ${df_targets['target_value'].sum():,.2f}")

# (Optional) Export entire table if you’d like:
# df_targets.to_csv("rebalance_output.csv", index=False)
