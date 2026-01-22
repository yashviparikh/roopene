import streamlit as st
import pandas as pd
import pdfplumber
from io import BytesIO
from db_config import get_engine
from fuzzywuzzy import process

# if "authentication_status" not in st.session_state or not st.session_state["authentication_status"]:
#     st.error("Unauthorized access")
#     st.stop()

st.set_page_config(page_title="SOR–BOQ Matching", layout="wide")
st.title("SOR–BOQ Matching System")

# ---------------------------------------------------------------------
# Utility: Extract table from PDF
# ---------------------------------------------------------------------
def extract_pdf_table(pdf_file, min_cols=3):
    rows = []
    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            table = page.extract_table()
            if table:
                for row in table:
                    if row and len(row) >= min_cols:
                        rows.append(row)
    return rows


# ---------------------------------------------------------------------
# SECTION 1: Upload & Store SOR (PDF → DB)
# ---------------------------------------------------------------------
st.header("Step 1: Upload SOR (PDF)")

sor_pdf = st.file_uploader("Upload SOR PDF", type=["pdf"], key="sor")

if sor_pdf:
    st.info("Reading SOR PDF...")

    sor_rows = extract_pdf_table(sor_pdf, min_cols=4)
    st.info("rows extracted")
    if not sor_rows:
        st.error("No table detected in SOR PDF.")
        st.stop()

    sor_df = pd.DataFrame(
        sor_rows,
        columns=["S.N.", "DESCRIPTION OF ITEMS", "UNIT", "Final rate (Excluding GST)"]
    )
    st.info("df made")
    # Cleaning
    sor_df = sor_df[sor_df["S.N."] != "S.N."]
    sor_df["S.N."] = sor_df["S.N."].astype(str).str.strip()
    sor_df["UNIT"] = sor_df["UNIT"].astype(str).str.strip()
    sor_df["Final rate (Excluding GST)"] = (
        sor_df["Final rate (Excluding GST)"]
        .astype(str)
        .str.replace(",", "", regex=True)
        .astype(float, errors="coerce")
    )

    st.success("SOR extracted successfully")
    st.dataframe(sor_df.head(15))

    if st.button("Save SOR to Database"):
        engine = get_engine()
        sor_df.to_sql("sor", engine, if_exists="replace", index=False)
        st.success("SOR saved to database")


# ---------------------------------------------------------------------
# SECTION 2: Upload BOQ (PDF → Match)
# ---------------------------------------------------------------------
st.header("Step 2: Upload BOQ (PDF)")

boq_pdf = st.file_uploader("Upload BOQ PDF", type=["pdf"], key="boq")

if boq_pdf:
    st.info("Reading BOQ PDF...")

    boq_rows = extract_pdf_table(boq_pdf, min_cols=3)

    if not boq_rows:
        st.error("No table detected in BOQ PDF.")
        st.stop()

    # Expected BOQ columns:
    # USOR Code | Description of Work | Qty
    boq_df = pd.DataFrame(
        boq_rows,
        columns=["usor_code", "Description of work", "Qty"]
    )

    boq_df = boq_df[boq_df["usor_code"] != "usor_code"]
    boq_df["usor_code"] = boq_df["usor_code"].astype(str).str.strip()
    boq_df["Qty"] = pd.to_numeric(boq_df["Qty"], errors="coerce")

    st.success("BOQ extracted successfully")
    st.dataframe(boq_df.head(15))

    if st.button("Perform SOR–BOQ Matching"):
        engine = get_engine()
        sor_db = pd.read_sql("SELECT * FROM sor", engine)

        # -----------------------------------------------------------------
        # 1. Direct match on USOR code
        # -----------------------------------------------------------------
        merged = boq_df.merge(
            sor_db,
            left_on="usor_code",
            right_on="S.N.",
            how="left"
        )

        # -----------------------------------------------------------------
        # 2. Fuzzy match fallback (description-based)
        # -----------------------------------------------------------------
        unmatched = merged["Final rate (Excluding GST)"].isna()

        if unmatched.any():
            sor_descs = sor_db["DESCRIPTION OF ITEMS"].tolist()

            for idx in merged[unmatched].index:
                boq_desc = merged.at[idx, "Description of work"]
                match, score = process.extractOne(boq_desc, sor_descs)

                if score >= 80:
                    sor_row = sor_db[sor_db["DESCRIPTION OF ITEMS"] == match].iloc[0]
                    merged.at[idx, "UNIT"] = sor_row["UNIT"]
                    merged.at[idx, "Final rate (Excluding GST)"] = sor_row["Final rate (Excluding GST)"]

        # -----------------------------------------------------------------
        # 3. Compute totals
        # -----------------------------------------------------------------
        merged["Final rate (Excluding GST)"] = pd.to_numeric(
            merged["Final rate (Excluding GST)"], errors="coerce"
        )
        merged["Total Amount (Rs)"] = merged["Qty"] * merged["Final rate (Excluding GST)"]

        # -----------------------------------------------------------------
        # 4. Final Output
        # -----------------------------------------------------------------
        result = merged[
            [
                "usor_code",
                "Description of work",
                "Qty",
                "UNIT",
                "Final rate (Excluding GST)",
                "Total Amount (Rs)",
            ]
        ]

        st.success("SOR–BOQ Matching completed")
        st.dataframe(result.head(20))

        # -----------------------------------------------------------------
        # 5. Download Excel
        # -----------------------------------------------------------------
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            result.to_excel(writer, index=False, sheet_name="SOR_BOQ")

        st.download_button(
            "Download Output Excel",
            buffer.getvalue(),
            file_name="SOR_BOQ_Matched.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
