"""Step 1-2: profile the raw DataCo files, clean them, and write Hadoop-ready TSVs.

Outputs
  data/processed/order_items.tsv      tab-separated, no header (HDFS input, one line per order item)
  data/processed/order_items.csv      same rows with a header (ML + MongoDB loader)
  data/processed/access_logs.tsv      cleaned clickstream (HDFS input)
  docs/results/profile.json           raw-data profile (shape, missing values, duplicates, label check)
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
RES = ROOT / "docs" / "results"
OUT.mkdir(parents=True, exist_ok=True)
RES.mkdir(parents=True, exist_ok=True)

# Order Country / Customer Country are stored in Spanish in the source; standardise the
# common ones to English so regional reports read naturally.
COUNTRY_EN = {
    "Estados Unidos": "United States", "EE. UU.": "United States", "Francia": "France",
    "México": "Mexico", "Alemania": "Germany", "Australia": "Australia", "Brasil": "Brazil",
    "Reino Unido": "United Kingdom", "China": "China", "Italia": "Italy", "India": "India",
    "Indonesia": "Indonesia", "España": "Spain", "El Salvador": "El Salvador",
    "República Dominicana": "Dominican Republic", "Honduras": "Honduras", "Cuba": "Cuba",
    "Turquía": "Turkey", "Nicaragua": "Nicaragua", "Nigeria": "Nigeria", "Guatemala": "Guatemala",
    "Filipinas": "Philippines", "Países Bajos": "Netherlands", "Colombia": "Colombia",
    "Argentina": "Argentina", "Japón": "Japan", "Corea del Sur": "South Korea", "Irán": "Iran",
    "Pakistán": "Pakistan", "Tailandia": "Thailand", "Egipto": "Egypt", "Marruecos": "Morocco",
    "Sudáfrica": "South Africa", "Canada": "Canada", "Canadá": "Canada", "Perú": "Peru",
    "Venezuela": "Venezuela", "Chile": "Chile", "Ecuador": "Ecuador", "Bélgica": "Belgium",
    "Suecia": "Sweden", "Austria": "Austria", "Polonia": "Poland", "Rusia": "Russia",
    "Ucrania": "Ukraine", "Bangladés": "Bangladesh", "Malasia": "Malaysia", "Vietnam": "Vietnam",
    "Arabia Saudí": "Saudi Arabia", "Irak": "Iraq", "Nueva Zelanda": "New Zealand",
    "Singapur": "Singapore", "Suiza": "Switzerland", "Dinamarca": "Denmark", "Noruega": "Norway",
    "Irlanda": "Ireland", "Portugal": "Portugal", "Grecia": "Greece", "Hungría": "Hungary",
    "Rumania": "Romania", "Rumanía": "Romania", "Panamá": "Panama", "Costa Rica": "Costa Rica",
    "Bolivia": "Bolivia", "Paraguay": "Paraguay", "Uruguay": "Uruguay", "Haití": "Haiti",
    "Jamaica": "Jamaica", "Puerto Rico": "Puerto Rico", "Argelia": "Algeria", "Túnez": "Tunisia",
    "Kenia": "Kenya", "Etiopía": "Ethiopia", "Ghana": "Ghana", "Afganistán": "Afghanistan",
    "Sri Lanka": "Sri Lanka", "Nepal": "Nepal", "Birmania": "Myanmar", "Camboya": "Cambodia",
    "Hong Kong": "Hong Kong", "Taiwán": "Taiwan", "Israel": "Israel", "Siria": "Syria",
    "Jordania": "Jordan", "Emiratos Árabes Unidos": "United Arab Emirates", "Kazajistán": "Kazakhstan",
    "Uzbekistán": "Uzbekistan", "República Checa": "Czech Republic", "Croacia": "Croatia",
    "Serbia": "Serbia", "Finlandia": "Finland", "Belarús": "Belarus", "Bielorrusia": "Belarus",
    "Camerún": "Cameroon", "Costa de Marfil": "Ivory Coast", "Senegal": "Senegal",
    "República Democrática del Congo": "DR Congo", "Angola": "Angola", "Tanzania": "Tanzania",
    "Uganda": "Uganda", "Zimbabue": "Zimbabwe", "Mozambique": "Mozambique", "Madagascar": "Madagascar",
}

# Order State is also partly in Spanish (US / Canadian states and some others)
STATE_EN = {
    "Nueva York": "New York", "Nueva Jersey": "New Jersey", "Carolina del Norte": "North Carolina",
    "Carolina del Sur": "South Carolina", "Nuevo México": "New Mexico", "Luisiana": "Louisiana",
    "Pensilvania": "Pennsylvania", "Misisipi": "Mississippi", "Misuri": "Missouri", "Hawái": "Hawaii",
    "Virginia Occidental": "West Virginia", "Dakota del Norte": "North Dakota", "Dakota del Sur": "South Dakota",
    "Columbia Británica": "British Columbia", "Columbia británica": "British Columbia", "Oregón": "Oregon",
    "Nuevo Hampshire": "New Hampshire", "Terranova": "Newfoundland and Labrador", "Nueva Escocia": "Nova Scotia", "Terranova y Labrador":
    "Newfoundland and Labrador", "Isla del Príncipe Eduardo": "Prince Edward Island", "Nuevo Brunswick": "New Brunswick",
    "Distrito de Columbia": "District of Columbia",
    # Australia, France, Mexico, Spain (largest remaining Spanish state names)
    "Nueva Gales del Sur": "New South Wales", "Australia Occidental": "Western Australia",
    "Australia del Sur": "South Australia", "Territorio de la Capital Australiana": "Australian Capital Territory",
    "Territorio del Norte": "Northern Territory", "Isla de Francia": "Île-de-France",
    "Distrito Federal": "Mexico City (Distrito Federal)", "Islas Baleares": "Balearic Islands",
}

KEEP = {
    "Order Id": "order_id", "Order Item Id": "order_item_id", "Order Customer Id": "customer_id",
    "order date (DateOrders)": "order_date", "shipping date (DateOrders)": "shipping_date",
    "Type": "payment_type", "Days for shipping (real)": "days_real",
    "Days for shipment (scheduled)": "days_scheduled", "Delivery Status": "delivery_status",
    "Late_delivery_risk": "late_delivery_risk", "Shipping Mode": "shipping_mode",
    "Market": "market", "Order Region": "order_region", "Order Country": "order_country",
    "Order State": "order_state", "Order City": "order_city", "Customer Segment": "customer_segment",
    "Customer Country": "customer_country", "Customer State": "customer_state",
    "Category Name": "category", "Department Name": "department", "Product Name": "product_name",
    "Product Card Id": "product_id", "Order Item Quantity": "quantity",
    "Order Item Product Price": "unit_price", "Order Item Discount": "discount",
    "Order Item Discount Rate": "discount_rate", "Sales": "sales", "Order Item Total": "item_total",
    "Order Profit Per Order": "profit", "Order Item Profit Ratio": "profit_ratio",
    "Order Status": "order_status", "Latitude": "store_lat", "Longitude": "store_lon",
}

TSV_COLS = [
    "order_id", "order_item_id", "customer_id", "order_ts", "order_ym", "order_dow", "order_hour",
    "payment_type", "shipping_mode", "days_real", "days_scheduled", "delay_days",
    "delivery_status", "is_late", "is_canceled", "market", "order_region", "order_country",
    "order_state", "customer_segment", "category", "department", "product_name", "quantity",
    "unit_price", "discount_rate", "sales", "item_total", "profit", "order_status",
]


def profile(df: pd.DataFrame) -> dict:
    miss = df.isna().sum()
    return {
        "rows": int(len(df)),
        "columns": int(df.shape[1]),
        "unique_orders": int(df["Order Id"].nunique()),
        "unique_customers": int(df["Order Customer Id"].nunique()),
        "unique_products": int(df["Product Card Id"].nunique()),
        "date_min": str(pd.to_datetime(df["order date (DateOrders)"], format="%m/%d/%Y %H:%M").min()),
        "date_max": str(pd.to_datetime(df["order date (DateOrders)"], format="%m/%d/%Y %H:%M").max()),
        "exact_duplicate_rows": int(df.duplicated().sum()),
        "duplicate_order_item_ids": int(df["Order Item Id"].duplicated().sum()),
        "missing_values": {c: int(v) for c, v in miss[miss > 0].items()},
        "missing_pct": {c: round(100 * v / len(df), 2) for c, v in miss[miss > 0].items()},
        "dtypes": {c: str(t) for c, t in df.dtypes.items()},
    }


def main() -> None:
    t0 = time.time()
    raw = pd.read_csv(RAW / "DataCoSupplyChainDataset.csv", encoding="latin-1")
    raw.columns = [c.strip() for c in raw.columns]
    prof = profile(raw)

    df = raw[list(KEEP)].rename(columns=KEEP).copy()
    steps = []

    # 1. duplicates
    before = len(df)
    df = df.drop_duplicates()
    df = df.drop_duplicates(subset="order_item_id")
    steps.append(f"Removed {before - len(df)} duplicate rows (exact + duplicate Order Item Id)")

    # 2. text normalisation
    for c in df.select_dtypes(include=["object", "string"]).columns:
        df[c] = df[c].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    df["order_country_raw"] = df["order_country"]
    df["order_country"] = df["order_country"].map(COUNTRY_EN).fillna(df["order_country"])
    df["customer_country"] = df["customer_country"].map(COUNTRY_EN).fillna(df["customer_country"])
    df["order_state"] = df["order_state"].map(STATE_EN).fillna(df["order_state"])
    mapped = (df["order_country"] != df["order_country_raw"]).mean()
    steps.append(f"Trimmed text fields; translated Spanish country names to English ({mapped:.1%} of rows changed)")

    # 3. dates
    df["order_ts"] = pd.to_datetime(df["order_date"], format="%m/%d/%Y %H:%M", errors="coerce")
    df["ship_ts"] = pd.to_datetime(df["shipping_date"], format="%m/%d/%Y %H:%M", errors="coerce")
    bad_dates = int(df["order_ts"].isna().sum() + df["ship_ts"].isna().sum())
    df = df.dropna(subset=["order_ts", "ship_ts"])
    steps.append(f"Parsed order/shipping timestamps to ISO-8601 ({bad_dates} unparseable values dropped)")

    # 4. missing values in the kept columns
    miss = df[list(KEEP.values())].isna().sum()
    miss = miss[miss > 0]
    for c in miss.index:
        if df[c].dtype == object:
            df[c] = df[c].fillna("Unknown")
        else:
            df[c] = df[c].fillna(df[c].median())
    steps.append("Missing values in kept columns: " + (", ".join(f"{c}={v}" for c, v in miss.items()) or "none")
                 + "; dropped columns with >85% missing (Product Description, Order Zipcode) and PII "
                   "(customer name, e-mail, password, street)")

    # 5. features and labels
    df["delay_days"] = df["days_real"] - df["days_scheduled"]
    df["is_canceled"] = (df["delivery_status"] == "Shipping canceled").astype(int)
    df["is_late"] = (df["delivery_status"] == "Late delivery").astype(int)
    label_agree = float((df["is_late"] == df["late_delivery_risk"]).mean())
    recomputed = ((df["days_real"] > df["days_scheduled"]).astype(int) == df["late_delivery_risk"]).mean()
    steps.append(f"Derived delay_days = real - scheduled; is_late from Delivery Status agrees with "
                 f"Late_delivery_risk on {label_agree:.2%} of rows; (real > scheduled) agrees on {recomputed:.2%}")
    df["order_ym"] = df["order_ts"].dt.strftime("%Y-%m")
    df["order_dow"] = df["order_ts"].dt.dayofweek
    df["order_hour"] = df["order_ts"].dt.hour
    df["ship_lag_days"] = (df["ship_ts"] - df["order_ts"]).dt.total_seconds() / 86400
    lag_match = float((df["ship_lag_days"].round() == df["days_real"]).mean())
    steps.append(f"Checked label consistency: shipping_date - order_date equals Days for shipping (real) on "
                 f"{lag_match:.2%} of rows")

    df = df.sort_values(["order_ts", "order_id", "order_item_id"]).reset_index(drop=True)
    df["order_ts"] = df["order_ts"].dt.strftime("%Y-%m-%dT%H:%M")
    df["ship_ts"] = df["ship_ts"].dt.strftime("%Y-%m-%dT%H:%M")
    for c in ["sales", "item_total", "profit", "unit_price", "discount_rate", "discount", "profit_ratio"]:
        df[c] = df[c].round(4)

    df[TSV_COLS].to_csv(OUT / "order_items.tsv", sep="\t", header=False, index=False)
    (OUT / "order_items.schema").write_text("\t".join(TSV_COLS) + "\n")
    df.drop(columns=["order_date", "shipping_date"]).to_csv(OUT / "order_items.csv", index=False)

    # order-level consistency: is delivery info constant within an order?
    g = df.groupby("order_id")
    consistent = {
        c: float((g[c].nunique() == 1).mean())
        for c in ["shipping_mode", "delivery_status", "days_real", "days_scheduled", "order_region"]
    }

    # clickstream
    logs = pd.read_csv(RAW / "tokenized_access_logs.csv", encoding="latin-1")
    logs_before = len(logs)
    logs = logs.drop_duplicates()
    for c in logs.select_dtypes(include=["object", "string"]).columns:
        logs[c] = logs[c].astype(str).str.replace(r"\s+", " ", regex=True).str.strip()
    logs["ts"] = pd.to_datetime(logs["Date"], format="%m/%d/%Y %H:%M", errors="coerce")
    logs = logs.dropna(subset=["ts"])
    logs["ym"] = logs["ts"].dt.strftime("%Y-%m")
    logs["dow"] = logs["ts"].dt.dayofweek
    logs[["ts", "ym", "Hour", "dow", "Department", "Category", "Product", "ip"]].assign(
        ts=logs["ts"].dt.strftime("%Y-%m-%dT%H:%M")
    ).to_csv(OUT / "access_logs.tsv", sep="\t", header=False, index=False)

    report = {
        "raw_profile": prof,
        "cleaning_steps": steps,
        "clean_rows": int(len(df)),
        "clean_orders": int(df["order_id"].nunique()),
        "order_level_consistency": consistent,
        "tsv_columns": TSV_COLS,
        "access_logs": {
            "raw_rows": int(logs_before), "clean_rows": int(len(logs)),
            "duplicates_removed": int(logs_before - len(logs)),
            "date_min": str(logs["ts"].min()), "date_max": str(logs["ts"].max()),
            "unique_ips": int(logs["ip"].nunique()), "unique_products": int(logs["Product"].nunique()),
        },
        "value_counts": {
            c: df[c].value_counts().head(30).to_dict()
            for c in ["delivery_status", "shipping_mode", "market", "order_region", "customer_segment",
                      "payment_type", "order_status", "department"]
        },
        "seconds": round(time.time() - t0, 2),
    }
    (RES / "profile.json").write_text(json.dumps(report, indent=2, default=str))
    print(json.dumps({k: v for k, v in report.items() if k not in ("raw_profile", "value_counts")}, indent=2, default=str))


if __name__ == "__main__":
    main()
