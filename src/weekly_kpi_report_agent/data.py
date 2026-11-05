from pathlib import Path

import pandas as pd

COLUMNS = [
    "Invoice",
    "StockCode",
    "Description",
    "Quantity",
    "InvoiceDate",
    "Price",
    "Customer ID",
    "Country",
]
PRODUCT_CODE = r"^\d{5}[A-Za-z]*$"


def read(path: Path) -> pd.DataFrame:
    """All sheets of the workbook concatenated, as given."""
    return pd.concat(
        pd.read_excel(
            path, sheet_name=None, dtype={"Invoice": str, "StockCode": str}
        ).values(),
        ignore_index=True,
    )


def missing_columns(raw: pd.DataFrame) -> list[str]:
    return [c for c in COLUMNS if c not in raw.columns]


def clean(raw: pd.DataFrame) -> pd.DataFrame:
    """One row per source line with `bucket` (DEC-03) and `revenue` columns."""
    df = raw[COLUMNS].copy()
    df["Invoice"] = df["Invoice"].astype(str)
    df["StockCode"] = df["StockCode"].astype(str)
    df["Description"] = df["Description"].fillna("").astype(str).str.strip()
    df["Country"] = df["Country"].fillna("").astype(str).str.strip()
    df["InvoiceDate"] = pd.to_datetime(df["InvoiceDate"])
    df["bucket"] = "product"
    rules = [
        ("duplicate", df.duplicated(subset=COLUMNS)),
        ("cancellation", df["Invoice"].str.startswith("C")),
        ("adjustment", df["Invoice"].str.startswith("A")),
        ("non_product", ~df["StockCode"].str.match(PRODUCT_CODE)),
        ("non_positive", (df["Price"] <= 0) | (df["Quantity"] <= 0)),
    ]
    for name, mask in reversed(rules):
        df.loc[mask, "bucket"] = name
    df["revenue"] = df["Quantity"] * df["Price"]
    return df
