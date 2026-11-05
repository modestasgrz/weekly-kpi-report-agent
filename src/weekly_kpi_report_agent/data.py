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


def read(path: Path) -> list[pd.DataFrame]:
    """Every sheet of the workbook, as given."""
    return list(
        pd.read_excel(
            path, sheet_name=None, dtype={"Invoice": str, "StockCode": str}
        ).values()
    )


def missing_columns(sheets: list[pd.DataFrame]) -> list[str]:
    """Required columns absent from at least one sheet, in DEC-03 order."""
    return [c for c in COLUMNS if any(c not in sheet.columns for sheet in sheets)]


def clean(sheets: list[pd.DataFrame]) -> pd.DataFrame:
    """One row per source line with `bucket` (DEC-03) and `revenue` columns."""
    df = pd.concat([sheet[COLUMNS] for sheet in sheets], ignore_index=True)
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
