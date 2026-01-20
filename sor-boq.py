import streamlit as st
import pandas as pd
import pdfplumber
from io import BytesIO
from config.db_config import get_engine
from fuzzywuzzy import process

st.set_page_config(page_title="SOR–BOQ Matching", layout="wide")
st.title("SOR–BOQ Matching System")

# ---------------------------------------------------------------------
# SECTION 1: Upload and Save SOR (PDF)
# ---------------------------------------------------------------------
st.header("Step 1: Upload SOR (PDF)")

sor_pdf = st.file_uploader("Upload SOR PDF file", type=["pdf"])

if sor_pdf is not None:
    st.info("Extracting table data from SOR PDF. Please wait...")

    data_rows = []
    try:
        with pdfplumber.open(sor_pdf) as pdf:
            for page in pdf.pages:
                table = page.extract_table()
                if table:
                    for row in table:
                        if len(row) >= 4 and row[0] != "S.N.":
                            data_rows.append(row[:4])
    except Exception as e:
        st.error(f"Error while reading PDF: {e}")
        st.stop()

    if not data_rows:
        st.error("No valid SOR data found in the uploaded PDF.")
    else:
        sor_df = pd.DataFrame(
            data_rows,
            columns=["S.N.", "DESCRIPTION OF ITEMS", "UNIT", "Final rate (Excluding GST)"]
        )
        sor_df = sor_df.dropna(subset=["DESCRIPTION OF ITEMS"])
        sor_df["S.N."] = sor_df["S.N."].astype(str).str.strip()
        sor_df["UNIT"] = sor_df["UNIT"].astype(str).str.strip()
        sor_df["Final rate (Excluding GST)"] = (
            sor_df["Final rate (Excluding GST)"]
            .astype(str)
            .str.replace(",", "", regex=True)
            .astype(float, errors="ignore")
        )

        st.success("SOR PDF successfully parsed.")
        st.dataframe(sor_df.head(20))

        if st.button("Save SOR to Database"):
            try:
                engine = get_engine()
                sor_df.to_sql("sor", con=engine, if_exists="replace", index=False)
                st.success("SOR table updated successfully in the database.")
            except Exception as e:
                st.error(f"Database update failed: {e}")

# ---------------------------------------------------------------------
# SECTION 2: Upload BOQ (Excel) and Match
# ---------------------------------------------------------------------
st.header("Step 2: Upload BOQ (Excel)")

boq_file = st.file_uploader("Upload BOQ Excel file", type=["xlsx", "xls"], key="boq_excel")

if boq_file is not None:
    boq_df = pd.read_excel(boq_file)
    st.write("**Uploaded BOQ Data:**")
    st.dataframe(boq_df.head())

    if st.button("Perform SOR–BOQ Matching"):
        try:
            engine = get_engine()
            sor_db = pd.read_sql("SELECT * FROM sor", engine)
        except Exception as e:
            st.error(f"Error reading SOR data from DB: {e}")
            st.stop()

        # Validate BOQ columns
        required_cols = ["usor_code", "Description of work", "Qty"]
        if not all(col in boq_df.columns for col in required_cols):
            st.error(f"BOQ file must contain columns: {required_cols}")
            st.stop()

        # --- 1. Merge directly on code ---
        merged = boq_df.merge(
            sor_db,
            left_on="usor_code",
            right_on="S.N.",
            how="left",
            suffixes=("", "_sor")
        )

        # --- 2. Fuzzy match where code not found ---
        unmatched_mask = merged["Final rate (Excluding GST)"].isna()
        unmatched_items = merged.loc[unmatched_mask, "Description of work"]

        if not unmatched_items.empty:
            st.warning(f"Performing fuzzy matching for {len(unmatched_items)} unmatched items...")

            sor_descriptions = sor_db["DESCRIPTION OF ITEMS"].tolist()
            for i, desc in unmatched_items.items():
                match, score = process.extractOne(desc, sor_descriptions)
                if score >= 80:  # Match confidence threshold
                    match_row = sor_db[sor_db["DESCRIPTION OF ITEMS"] == match].iloc[0]
                    merged.at[i, "DESCRIPTION OF ITEMS"] = match_row["DESCRIPTION OF ITEMS"]
                    merged.at[i, "UNIT"] = match_row["UNIT"]
                    merged.at[i, "Final rate (Excluding GST)"] = match_row["Final rate (Excluding GST)"]

        # --- 3. Compute totals ---
        merged["Final rate (Excluding GST)"] = pd.to_numeric(
            merged["Final rate (Excluding GST)"], errors="coerce"
        )
        merged["Total Amount (Rs)"] = merged["Qty"] * merged["Final rate (Excluding GST)"]

        # --- 4. Prepare final output ---
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
        st.dataframe(result.head(20))

        # --- 5. Download as Excel ---
        output_buffer = BytesIO()
        with pd.ExcelWriter(output_buffer, engine="xlsxwriter") as writer:
            result.to_excel(writer, index=False, sheet_name="SOR_BOQ_Match")
        output_buffer.seek(0)

        st.download_button(
            label="Download Matched Excel File",
            data=output_buffer,
            file_name="SOR_BOQ_Matched.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
