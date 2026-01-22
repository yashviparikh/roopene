import streamlit as st
import pandas as pd
import pdfplumber
from io import BytesIO
from db_config import get_engine
from fuzzywuzzy import process
import re
# if "authentication_status" not in st.session_state or not st.session_state["authentication_status"]:
#     st.error("Unauthorized access")
#     st.stop()

st.set_page_config(page_title="SOR–BOQ Matching", layout="wide")
st.title("SOR–BOQ Matching System")


# ---------------------------------------------------------------------
# Utility: Extract table from PDF
# ---------------------------------------------------------------------
def normalize_sor_excel(df):
    rows = []

    for _, row in df.iterrows():

        sheet_name = row.get("__sheet__", "").strip()

        # Expected fixed columns:
        # 0 = S.N.
        # 1 = Description
        # 2 = Unit
        # 3 = Rate

        sn = str(row[0]).strip() if pd.notna(row[0]) else ""
        description = str(row[1]).strip() if pd.notna(row[1]) else ""
        unit = str(row[2]).strip() if pd.notna(row[2]) else ""
        rate_raw = row[3]

        # Skip rows without valid SOR code
        if not re.match(r"R[0-9A-Za-z\-]+", sn):
            continue

        # Clean description: remove embedded "Table xx"
        description = re.sub(r"\bTable\s*\d+\b", "", description, flags=re.I)
        description = re.sub(r"\s+", " ", description).strip()

        # Normalize rate
        rate = None
        if pd.notna(rate_raw):
            try:
                rate = float(str(rate_raw).replace(",", "").strip())
            except ValueError:
                rate = None

        rows.append([
            sn,
            description,
            unit,
            rate,
            sheet_name   # Table number from sheet name
        ])

    return pd.DataFrame(
        rows,
        columns=[
            "S.N.",
            "DESCRIPTION OF ITEMS",
            "UNIT",
            "Final rate (Excluding GST)",
            "TABLE_NO"
        ]
    )
# ---------------------------------------------------------------------
# SECTION 1: Upload & Store SOR (PDF → DB)
# ---------------------------------------------------------------------
st.header("Step 1: Upload SOR (Excel)")

sor_excel = st.file_uploader("Upload SOR Excel file", type=["xlsx", "xls"])

if sor_excel:
    xls = pd.ExcelFile(sor_excel)

    total_sheets = len(xls.sheet_names)
    st.info(f"Workbook contains {total_sheets} sheets")

    start_sheet = st.number_input(
        "Start sheet number (1-based)",
        min_value=1,
        max_value=total_sheets,
        value=5
    )

    end_sheet = st.number_input(
        "End sheet number (inclusive)",
        min_value=start_sheet,
        max_value=total_sheets,
        value=min(103, total_sheets)
    )
    
    raw_frames = []

    for i in range(start_sheet - 1, end_sheet):
        sheet_name = xls.sheet_names[i]
        df = pd.read_excel(
            sor_excel,
            sheet_name=sheet_name,
            header=None
        )
        df["__sheet__"] = sheet_name  # optional traceability
        raw_frames.append(df)

    combined_raw_df = pd.concat(raw_frames, ignore_index=True)
    
    sor_df = normalize_sor_excel(combined_raw_df)

    st.success(
        f"SOR extracted from sheets {start_sheet} to {end_sheet}"
    )
    st.dataframe(sor_df)
    if st.button("Save SOR to Database"):
        engine = get_engine()
        sor_df.to_sql("sor", engine, if_exists="replace", index=False)
        st.success("SOR saved to database successfully")

# ---------------------------------------------------------------------
# SECTION 2: Upload BOQ (PDF → Match)
# ---------------------------------------------------------------------
st.header("Step 2: Upload BOQ (Excel)")

# Upload BOQ file
# Upload BOQ file
boq_file = st.file_uploader(
    "Upload BOQ Excel file",
    type=["xlsx", "xls"],
    key="boq_excel"
)

if boq_file is not None:
    boq_df = pd.read_excel(boq_file)

    # -------------------------------
    # Normalize BOQ headers
    # -------------------------------
    boq_df.columns = (
        boq_df.columns
        .astype(str)
        .str.strip()
        .str.lower()
        .str.replace(".", "", regex=False)
        .str.replace("/", "", regex=False)
        .str.replace(r"\s+", " ", regex=True)
    )

    rename_map = {
        "usor code": "usor_code",
        "usorcode": "usor_code",
        "description of work": "Description of work",
        "qty": "Qty",
        "quantity": "Qty"
    }

    boq_df = boq_df.rename(columns=rename_map)

    # Drop serial number columns safely
    boq_df = boq_df.loc[
        :,
        ~boq_df.columns.str.contains(r"^sr|^sl|^sno", regex=True)
    ]

    st.write("**Uploaded BOQ Data (Normalized):**")
    st.dataframe(boq_df)

    if st.button("Perform SOR - BOQ Matching"):
        # --- 0. Load SOR from DB ---
        try:
            engine = get_engine()
            sor_db = pd.read_sql("SELECT * FROM sor", engine)
        except Exception as e:
            st.error(f"Error reading SOR data from DB: {e}")
            st.stop()

        # --- 1. Validate BOQ columns ---
        required_cols = ["usor_code", "Description of work", "Qty"]
        missing = [c for c in required_cols if c not in boq_df.columns]

        if missing:
            st.error(
                f"BOQ file must contain columns: {required_cols}\n"
                f"Missing: {missing}"
            )
            st.stop()

        # --- 2. Merge directly on USOR code ---
        merged = boq_df.merge(
            sor_db,
            left_on="usor_code",
            right_on="S.N.",
            how="left",
            suffixes=("", "_sor")
        )

        # --- 3. Fuzzy match unmatched items ---
        unmatched_mask = merged["Final rate (Excluding GST)"].isna()
        unmatched_indices = merged.index[unmatched_mask]

        if not unmatched_indices.empty:
            st.warning(
                f"Performing fuzzy matching for {len(unmatched_indices)} unmatched items..."
            )
            sor_descriptions = sor_db["DESCRIPTION OF ITEMS"].tolist()

            for idx in unmatched_indices:
                desc = merged.at[idx, "Description of work"]
                match, score = process.extractOne(desc, sor_descriptions)
                if score >= 80:
                    match_row = sor_db[
                        sor_db["DESCRIPTION OF ITEMS"] == match
                    ].iloc[0]

                    merged.at[idx, "DESCRIPTION OF ITEMS"] = match_row[
                        "DESCRIPTION OF ITEMS"
                    ]
                    merged.at[idx, "UNIT"] = match_row["UNIT"]
                    merged.at[idx, "Final rate (Excluding GST)"] = match_row[
                        "Final rate (Excluding GST)"
                    ]

        # --- 4. Compute totals ---
        merged["Final rate (Excluding GST)"] = pd.to_numeric(
            merged["Final rate (Excluding GST)"], errors="coerce"
        )

        merged["Total Amount (Rs)"] = (
            merged["Qty"] * merged["Final rate (Excluding GST)"]
        )

        # --- 5. Prepare final output ---
        output_cols = [
            "usor_code",
            "Description of work",
            "Qty",
            "UNIT",
            "Final rate (Excluding GST)",
            "Total Amount (Rs)",
        ]

        result = merged[output_cols]

        st.success("SOR–BOQ Matching completed successfully.")
        st.dataframe(result)

        # --- 6. Download as Excel ---
        output_buffer = BytesIO()
        with pd.ExcelWriter(output_buffer, engine="xlsxwriter") as writer:
            result.to_excel(
                writer,
                index=False,
                sheet_name="SOR_BOQ_Match"
            )

        output_buffer.seek(0)

        st.download_button(
            label="Download Matched Excel File",
            data=output_buffer,
            file_name="SOR_BOQ_Matched.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
