import streamlit as st
import pandas as pd
import plotly.express as px
from config.db_config import get_engine
from sqlalchemy import text
from io import BytesIO
import time

st.set_page_config(page_title="Inventory Tracking", layout="wide")
st.title("Inventory Tracking and Dashboard")

engine = get_engine()

# ------------------------------------------------------------
# Utility Functions
# ------------------------------------------------------------
def get_existing_sites():
    with engine.connect() as conn:
        tables = pd.read_sql(
            "SELECT table_name FROM information_schema.tables WHERE table_schema='public'", conn
        )
    return [t for t in tables["table_name"].tolist() if t.startswith("inventory_")]

def ensure_log_table():
    with engine.connect() as conn:
        conn.execute(
            text("""
                CREATE TABLE IF NOT EXISTS material_log (
                    id SERIAL PRIMARY KEY,
                    site VARCHAR(255),
                    material VARCHAR(255),
                    qty FLOAT,
                    source VARCHAR(255),
                    dest VARCHAR(255),
                    rate FLOAT,
                    bill_invoice_no VARCHAR(255),
                    entry_date TIMESTAMP DEFAULT NOW()
                );
            """)
        )

def download_excel(df, filename):
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False)
    output.seek(0)
    st.download_button(
        label=f"📥 Download {filename}",
        data=output,
        file_name=filename,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    )

def download_csv(df, filename):
    csv = df.to_csv(index=False).encode("utf-8")
    st.download_button(
        label=f"📥 Download {filename}",
        data=csv,
        file_name=filename,
        mime="text/csv",
    )

# ------------------------------------------------------------
# SECTION 1: Create & Manage Sites
# ------------------------------------------------------------
st.header("Step 1: Create and Manage Sites")

existing_sites = get_existing_sites()
new_site = st.text_input("Enter new site name (no spaces, lowercase preferred):")

if st.button("Create New Site Table"):
    if not new_site:
        st.error("Please enter a valid site name.")
    else:
        table_name = f"inventory_{new_site.lower()}"
        with engine.connect() as conn:
            conn.execute(
                text(
                    f"""
                    CREATE TABLE IF NOT EXISTS {table_name} (
                        id SERIAL PRIMARY KEY,
                        material VARCHAR(255),
                        total_no FLOAT,
                        rate_per_unit FLOAT,
                        unit VARCHAR(50)
                    );
                    """
                )
            )
        st.success(f"New site '{table_name}' created successfully.")
        existing_sites = get_existing_sites()

# ------------------------------------------------------------
# SECTION 2: Daily Material Input
# ------------------------------------------------------------
st.header("Step 2: Add Daily Material Movement")

ensure_log_table()
if existing_sites:
    selected_site = st.selectbox("Select Site", existing_sites)
    tab1, tab2 = st.tabs(["Manual Entry", "Excel Upload"])

    # --- Manual Entry ---
    with tab1:
        with st.form("manual_entry"):
            material = st.text_input("Material Name")
            qty = st.number_input("Quantity", min_value=0.0, step=0.01)
            source = st.text_input("Source")
            dest = st.text_input("Destination")
            rate = st.number_input("Rate per Unit (Rs)", min_value=0.0, step=0.01)
            bill = st.text_input("Bill / Invoice No")
            submit = st.form_submit_button("Submit Entry")

            if submit:
                with engine.connect() as conn:
                    conn.execute(
                        text(
                            f"""
                            INSERT INTO {selected_site} (material, total_no, rate_per_unit, unit)
                            VALUES (:material, :qty, :rate, 'units');
                            """
                        ),
                        {"material": material, "qty": qty, "rate": rate},
                    )
                    conn.execute(
                        text(
                            """
                            INSERT INTO material_log
                            (site, material, qty, source, dest, rate, bill_invoice_no)
                            VALUES (:site, :material, :qty, :source, :dest, :rate, :bill);
                            """
                        ),
                        {
                            "site": selected_site,
                            "material": material,
                            "qty": qty,
                            "source": source,
                            "dest": dest,
                            "rate": rate,
                            "bill": bill,
                        },
                    )
                st.success("Entry successfully recorded.")
                time.sleep(1)
                st.experimental_rerun()

    # --- Excel Upload ---
    with tab2:
        uploaded_file = st.file_uploader("Upload Excel File", type=["xlsx", "xls"])
        if uploaded_file:
            df = pd.read_excel(uploaded_file)
            st.write("**Uploaded Data Preview:**")
            st.dataframe(df.head())
            required_cols = ["material", "qty", "source", "dest", "rate", "bill_invoice_no"]
            if not all(col in df.columns for col in required_cols):
                st.error(f"Excel must contain columns: {required_cols}")
            else:
                if st.button("Add Excel Data to Database"):
                    with engine.connect() as conn:
                        for _, row in df.iterrows():
                            conn.execute(
                                text(
                                    f"""
                                    INSERT INTO {selected_site} (material, total_no, rate_per_unit, unit)
                                    VALUES (:material, :qty, :rate, 'units');
                                    """
                                ),
                                {"material": row["material"], "qty": row["qty"], "rate": row["rate"]},
                            )
                            conn.execute(
                                text(
                                    """
                                    INSERT INTO material_log
                                    (site, material, qty, source, dest, rate, bill_invoice_no)
                                    VALUES (:site, :material, :qty, :source, :dest, :rate, :bill);
                                    """
                                ),
                                {
                                    "site": selected_site,
                                    "material": row["material"],
                                    "qty": row["qty"],
                                    "source": row["source"],
                                    "dest": row["dest"],
                                    "rate": row["rate"],
                                    "bill": row["bill_invoice_no"],
                                },
                            )
                    st.success("Excel data successfully added.")
                    time.sleep(1)
                    st.experimental_rerun()
else:
    st.warning("Create a site table first to begin tracking materials.")

# ------------------------------------------------------------
# SECTION 3: Dashboard
# ------------------------------------------------------------
st.header("Step 3: Real-Time Inventory Dashboard")

try:
    with engine.connect() as conn:
        log_df = pd.read_sql("SELECT * FROM material_log ORDER BY entry_date DESC", conn)
except Exception:
    st.info("No material data found yet.")
    st.stop()

if not log_df.empty:
    # Sidebar Filters
    st.sidebar.subheader("Filter Dashboard Data")
    site_filter = st.sidebar.multiselect("Site", log_df["site"].unique())
    material_filter = st.sidebar.multiselect("Material", log_df["material"].unique())
    source_filter = st.sidebar.multiselect("Source", log_df["source"].unique())
    dest_filter = st.sidebar.multiselect("Destination", log_df["dest"].unique())

    filtered_df = log_df.copy()
    if site_filter:
        filtered_df = filtered_df[filtered_df["site"].isin(site_filter)]
    if material_filter:
        filtered_df = filtered_df[filtered_df["material"].isin(material_filter)]
    if source_filter:
        filtered_df = filtered_df[filtered_df["source"].isin(source_filter)]
    if dest_filter:
        filtered_df = filtered_df[filtered_df["dest"].isin(dest_filter)]

    st.write("### Filtered Data")
    st.dataframe(filtered_df)

    # Summary metrics
    total_qty = filtered_df["qty"].sum()
    total_value = (filtered_df["qty"] * filtered_df["rate"]).sum()
    unique_materials = filtered_df["material"].nunique()

    col1, col2, col3 = st.columns(3)
    col1.metric("Total Quantity Moved", f"{total_qty:.2f}")
    col2.metric("Total Value (Rs)", f"{total_value:,.2f}")
    col3.metric("Unique Materials", unique_materials)

    # Charts
    st.write("### Quantity Distribution by Site")
    fig1 = px.bar(
        filtered_df,
        x="site",
        y="qty",
        color="material",
        barmode="group",
        title="Material Quantity per Site"
    )
    st.plotly_chart(fig1, use_container_width=True)

    st.write("### Material Flow: Source → Destination → Material")
    fig2 = px.sunburst(
        filtered_df,
        path=["source", "dest", "material"],
        values="qty",
        title="Material Flow Hierarchy"
    )
    st.plotly_chart(fig2, use_container_width=True)

    st.write("### Cost Distribution by Material")
    filtered_df["Total Value"] = filtered_df["qty"] * filtered_df["rate"]
    fig3 = px.pie(
        filtered_df,
        names="material",
        values="Total Value",
        title="Material Cost Distribution"
    )
    st.plotly_chart(fig3, use_container_width=True)

    # Download Options
    st.subheader("Download Filtered Data")
    col_a, col_b = st.columns(2)
    with col_a:
        download_excel(filtered_df, "Filtered_Inventory_Data.xlsx")
    with col_b:
        download_csv(filtered_df, "Filtered_Inventory_Data.csv")

else:
    st.warning("No entries found in material_log yet.")
