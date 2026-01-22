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
def extract_sor_table(pdf_file):
    """
    Extract the SOR table from PDF that comes after:
    "M&E SCHEDULE 2023\nINDEX" and under "PAGE PART II RATE SCHEDULE"
    Returns a clean list of rows suitable for DataFrame creation
    """
    sor_rows = []

    with pdfplumber.open(pdf_file) as pdf:
        for page in pdf.pages:
            text = page.extract_text()
            # Only process pages with the target heading
            if text and "PAGE PART II RATE SCHEDULE" in text and "M&E SCHEDULE 2023" in text:
                tables = page.extract_tables()
                for table in tables:
                    # Simple filter: only tables with at least 4 columns
                    if table and len(table[0]) >= 4:
                        # Keep first 4 columns only
                        cleaned_table = [row[:4] for row in table if any(cell for cell in row)]
                        sor_rows.extend(cleaned_table)
                if sor_rows:  # stop after first matching page
                    break

    return sor_rows

def parse_sor_row(row_text):
    """
    Parse a single SOR row text into 4 columns.
    """
    # S.N.
    sn_match = re.match(r"(R[0-9A-Za-z\-]+)", row_text)
    if not sn_match:
        return None
    sn = sn_match.group(1)

    # UNIT + Final rate (number at end)
    final_match = re.search(r"(Nos|Set|m|kg)\s*(\d+)$", row_text)
    if final_match:
        unit = final_match.group(1)
        rate = float(final_match.group(2))
        desc = row_text[len(sn):row_text.rfind(unit)].strip()
    else:
        unit = ""
        rate = None
        desc = row_text[len(sn):].strip()

    desc = re.sub(r"\s+", " ", desc)  # collapse spaces
    return [sn, desc, unit, rate]
# ---------------------------------------------------------------------
# SECTION 1: Upload & Store SOR (PDF → DB)
# ---------------------------------------------------------------------
st.header("Step 1: Upload SOR (PDF)")

sor_pdf = st.file_uploader("Upload SOR PDF", type=["pdf"], key="sor")

if sor_pdf:
    # Open PDF to get number of pages
    with pdfplumber.open(sor_pdf) as pdf:
        num_pages = len(pdf.pages)
        st.info(f"PDF has {num_pages} pages")

        # User inputs start and end page
        start_page = st.number_input("Start page", min_value=1, max_value=num_pages, value=1, step=1)
        end_page = st.number_input("End page", min_value=1, max_value=num_pages, value=num_pages, step=1)

        if st.button("Extract SOR Table"):
            if start_page > end_page:
                st.error("Start page cannot be greater than end page")
                st.stop()

            st.info(f"Extracting tables from pages {start_page} to {end_page}...")

            sor_rows = []

            with pdfplumber.open(sor_pdf) as pdf:
                for p in range(start_page, end_page + 1):
                    page = pdf.pages[p - 1]  # convert to 0-index
                    text = page.extract_text()
                    if not text:
                        continue

                    buffer = ""
                    for line in text.splitlines():
                        line = line.strip()
                        if not line:
                            continue

                        # Detect start of a new row by S.N. pattern (starts with R)
                        if re.match(r"R[0-9A-Za-z\-]+", line):
                            # Process previous buffered row
                            if buffer:
                                row = parse_sor_row(buffer)
                                if row:
                                    sor_rows.append(row)
                            buffer = line
                        else:
                            # Continuation of DESCRIPTION
                            buffer += " " + line

                    # Process last buffered row
                    if buffer:
                        row = parse_sor_row(buffer)
                        if row:
                            sor_rows.append(row)

            if not sor_rows:
                st.error("No table detected in the selected page range.")
                st.stop()

            # Create DataFrame
            sor_df = pd.DataFrame(
                sor_rows,
                columns=["S.N.", "DESCRIPTION OF ITEMS", "UNIT", "Final rate (Excluding GST)"]
            )

            # Cleaning
            sor_df = sor_df[sor_df["S.N."].str.strip() != "S.N."]
            sor_df["S.N."] = sor_df["S.N."].astype(str).str.strip()
            sor_df["UNIT"] = sor_df["UNIT"].astype(str).str.strip()
            sor_df["Final rate (Excluding GST)"] = pd.to_numeric(
                sor_df["Final rate (Excluding GST)"].astype(str).str.replace(",", "", regex=True),
                errors="coerce"
            )

            st.success("SOR extracted successfully")
            st.dataframe(sor_df)

            if st.button("Save SOR to Database"):
                engine = get_engine()
                sor_df.to_sql("sor", engine, if_exists="replace", index=False)
                st.success("SOR saved to database")

# ---------------------------------------------------------------------
# SECTION 2: Upload BOQ (PDF → Match)
# ---------------------------------------------------------------------
st.header("Step 2: Upload BOQ (Excel)")

# Upload BOQ file
boq_file = st.file_uploader("Upload BOQ Excel file", type=["xlsx", "xls"], key="boq_excel")
if boq_file is not None:
    boq_df = pd.read_excel(boq_file)
    st.write("**Uploaded BOQ Data:**")
    st.dataframe(boq_df.head())

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
        if not all(col in boq_df.columns for col in required_cols):
            st.error(f"BOQ file must contain columns: {required_cols}")
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
            st.warning(f"Performing fuzzy matching for {len(unmatched_indices)} unmatched items...")
            sor_descriptions = sor_db["DESCRIPTION OF ITEMS"].tolist()

            for idx in unmatched_indices:
                desc = merged.at[idx, "Description of work"]
                match, score = process.extractOne(desc, sor_descriptions)
                if score >= 80:  # confidence threshold
                    match_row = sor_db[sor_db["DESCRIPTION OF ITEMS"] == match].iloc[0]
                    merged.at[idx, "DESCRIPTION OF ITEMS"] = match_row["DESCRIPTION OF ITEMS"]
                    merged.at[idx, "UNIT"] = match_row["UNIT"]
                    merged.at[idx, "Final rate (Excluding GST)"] = match_row["Final rate (Excluding GST)"]

        # --- 4. Compute totals ---
        merged["Final rate (Excluding GST)"] = pd.to_numeric(
            merged["Final rate (Excluding GST)"], errors="coerce"
        )
        merged["Total Amount (Rs)"] = merged["Qty"] * merged["Final rate (Excluding GST)"]

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
        st.dataframe(result.head(20))

        # --- 6. Download as Excel ---
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