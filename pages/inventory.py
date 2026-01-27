import streamlit as st
import pandas as pd
from sqlalchemy import text
from db_config import get_engine
from sqlalchemy.exc import OperationalError

st.set_page_config(page_title="Inventory Tracking", layout="wide")
st.title("Inventory Management")

engine = get_engine()

# Create table if not exists
def create_inventory_table():
    with engine.connect() as conn:
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS inventory_master (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                item_name TEXT,
                supplier_name TEXT,
                batch_no TEXT,
                purchase_date DATE,
                invoice_no TEXT,
                qty_available REAL,
                rate REAL,
                unit TEXT
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS challan_header (
                challan_id INTEGER PRIMARY KEY AUTOINCREMENT,
                supplier_id TEXT,
                project_location TEXT,
                challan_date DATETIME
            )
        """))

        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS challan_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                challan_id INTEGER,
                inventory_id INTEGER,
                qty_issued REAL
            )
        """))

create_inventory_table()

module = st.radio(
    "Select Operation",
    ["Add Inventory", "View Inventory", "Generate Challan", "View / Print Challans"],
    horizontal=True
)

# ------------------- ADD INVENTORY -------------------
if module == "Add Inventory":
    st.header("Add Inventory")
    col1, col2, col3 = st.columns(3)
    supplier = col1.text_input("Supplier Name / ID")
    batch_no = col2.text_input("Batch No")
    invoice_no = col3.text_input("Invoice No")
    purchase_date = st.date_input("Purchase Date")

    with st.form("add_inventory_form"):
        item_name = st.text_input("Item Name")
        qty = st.number_input("Quantity", min_value=0.0)
        rate = st.number_input("Rate", min_value=0.0)
        unit = st.selectbox("Unit", ["kg", "nos", "m", "ltr"])
        submit = st.form_submit_button("Add to Inventory")

    # Validation: cannot be zero
    if submit:
        if not item_name.strip() or qty <= 0 or rate <= 0 or not supplier.strip() or not batch_no.strip():
            st.error("Please fill all fields. Quantity and Rate must be greater than zero.")
        else:
            with engine.connect() as conn:
                conn.execute(
                    text("""
                        INSERT INTO inventory_master
                        (item_name, supplier_name, batch_no, purchase_date,
                        invoice_no, qty_available, rate, unit)
                        VALUES
                        (:item, :supplier, :batch, :pdate,
                        :invoice, :qty, :rate, :unit)
                    """),
                    {
                        "item": item_name,
                        "supplier": supplier,
                        "batch": batch_no,
                        "pdate": purchase_date,
                        "invoice": invoice_no,
                        "qty": qty,
                        "rate": rate,
                        "unit": unit
                    }
                )
            st.success(f"Inventory for '{item_name}' added successfully!")

# ------------------- VIEW INVENTORY -------------------
elif module == "View Inventory":
    st.header("Current Inventory")
    try:
        with engine.connect() as conn:
            inv_df = pd.read_sql("SELECT * FROM inventory_master ORDER BY id DESC", conn)
        if inv_df.empty:
            st.info("No inventory found.")
        else:
            st.dataframe(inv_df, use_container_width=True)
    except OperationalError:
        st.error("Inventory table not found.")

# ------------------- GENERATE CHALLAN -------------------
elif module == "Generate Challan":
    st.header("Generate Challan")

    supplier = st.text_input("Supplier ID / Name")
    batch_no = st.text_input("Batch No")
    project_location = st.text_input("Project Location")

    if "search_inventory" not in st.session_state:
        st.session_state["search_inventory"] = False

    if st.button("Search Inventory"):
        st.session_state["search_inventory"] = True

    if st.session_state["search_inventory"]:
        try:
            with engine.connect() as conn:
                inv_df = pd.read_sql(
                    text("""
                        SELECT id, item_name, qty_available, unit
                        FROM inventory_master
                        WHERE qty_available > 0
                        AND LOWER(supplier_name) LIKE LOWER(:supplier)
                        AND LOWER(batch_no) LIKE LOWER(:batch)
                    """),
                    conn,
                    params={"supplier": f"%{supplier}%", "batch": f"%{batch_no}%"}
                )
            st.session_state["inv_df"] = inv_df
        except Exception:
            st.error("Unable to fetch inventory.")
            st.session_state["inv_df"] = pd.DataFrame()


    inv_df = st.session_state.get("inv_df", pd.DataFrame())
    if inv_df.empty:
        st.info("No inventory available. Please search.")
        st.stop()

    st.success(f"{len(inv_df)} item(s) found")
    st.dataframe(inv_df, use_container_width=True)

    selected_ids = st.multiselect("Select Inventory Items", inv_df["id"].tolist())
    if not selected_ids:
        st.info("Select at least one item to generate challan.")
        st.stop()

    issue_data = []
    for inv_id in selected_ids:
        max_qty = float(inv_df.loc[inv_df["id"] == inv_id, "qty_available"].iloc[0])
        qty = st.number_input(
            f"Issue Qty for Item ID {inv_id}",
            min_value=0.0,
            max_value=max_qty,
            key=f"qty_{inv_id}"
        )
        issue_data.append((inv_id, qty))

    if st.button("Generate Challan"):
        if not project_location.strip():
            st.error("Project Location is required.")
            st.stop()
        with engine.begin() as conn:
            challan_id = conn.execute(
                text("""
                    INSERT INTO challan_header
                    (supplier_id, project_location, challan_date)
                    VALUES (:supplier, :location, CURRENT_TIMESTAMP)
                """),
                {"supplier": supplier, "location": project_location}
            ).lastrowid

            for inv_id, qty in issue_data:
                if qty > 0:
                    conn.execute(
                        text("""
                            INSERT INTO challan_items
                            (challan_id, inventory_id, qty_issued)
                            VALUES (:cid, :iid, :qty)
                        """),
                        {"cid": challan_id, "iid": inv_id, "qty": qty}
                    )
                    conn.execute(
                        text("""
                            UPDATE inventory_master
                            SET qty_available = qty_available - :qty
                            WHERE id = :iid
                        """),
                        {"qty": qty, "iid": inv_id}
                    )
        st.success(f"Challan CHLN-{challan_id} generated successfully")
        st.session_state.pop("inv_df", None)


def generate_challan_html(
    challan_no, date, po_no, project_location, items
):
    rows = ""
    for i, item in enumerate(items, 1):
        rows += f"""
        <tr>
            <td>{i}</td>
            <td>{item['name']}</td>
            <td>{item['qty']}</td>
            <td>{item['unit']}</td>
        </tr>
        """

    html = f"""
    <html>
    <head>
        <style>
            body {{
                font-family: Arial;
                margin: 30px;
            }}
            h2, h3 {{
                text-align: center;
                margin: 5px;
            }}
            table {{
                width: 100%;
                border-collapse: collapse;
                margin-top: 15px;
            }}
            th, td {{
                border: 1px solid black;
                padding: 8px;
                text-align: left;
            }}
            .meta td {{
                border: none;
                padding: 4px;
            }}
        </style>
    </head>

    <body>
        <h2>CHALLAN / TAX INVOICE</h2>
        <h3>ROOPEN ELECTRICALS</h3>

        <p>
            <b>Address:</b> Shop Address, City, State, Pincode<br>
            <b>Mobile:</b> 9XXXXXXXXX
        </p>

        <table class="meta">
            <tr><td><b>Challan No:</b> {challan_no}</td><td><b>Date:</b> {date}</td></tr>
            <tr><td><b>P.O. No:</b> {po_no}</td><td><b>Project Location:</b> {project_location}</td></tr>
        </table>

        <p>Please receive the following goods in good order and condition:</p>

        <table>
            <tr>
                <th>Sr No</th>
                <th>Item Description</th>
                <th>Quantity</th>
                <th>Unit</th>
            </tr>
            {rows}
        </table>

        <br><br>

        <table class="meta">
            <tr>
                <td>Receiver Signature: _____________</td>
                <td style="text-align:right;">
                    For <b>ROOPEN ELECTRICALS</b><br><br>
                    Authorized Signatory
                </td>
            </tr>
        </table>

    </body>
    </html>
    """
    return html

if module == "View / Print Challans":
    st.header("Generated Challans")

    try:
        with engine.connect() as conn:
            challan_df = pd.read_sql("""
                SELECT challan_id, supplier_id, project_location, challan_date
                FROM challan_header
                ORDER BY challan_date DESC
            """, conn)
    except OperationalError:
        st.info("No challans found yet.")
        st.stop()

    if challan_df.empty:
        st.info("No challans generated yet.")
        st.stop()

    for _, row in challan_df.iterrows():
        col1, col2, col3, col4, col5 = st.columns([2, 2, 3, 3, 2])

        col1.write(f"**CHLN-{row['challan_id']}**")
        col2.write(row["challan_date"].strftime("%d-%m-%Y"))
        col3.write(row["supplier_id"])
        col4.write(row["project_location"])

        if col5.button("🖨 Print", key=f"print_{row['challan_id']}"):
            st.session_state["print_challan_id"] = row["challan_id"]
if "print_challan_id" in st.session_state:
    challan_id = st.session_state["print_challan_id"]

    with engine.connect() as conn:
        header = pd.read_sql(
            text("SELECT * FROM challan_header WHERE challan_id = :cid"),
            conn,
            params={"cid": challan_id}
        ).iloc[0]

        items_df = pd.read_sql(
            text("""
                SELECT im.item_name, im.unit, ci.qty_issued
                FROM challan_items ci
                JOIN inventory_master im ON ci.inventory_id = im.id
                WHERE ci.challan_id = :cid
            """),
            conn,
            params={"cid": challan_id}
        )

    items = [
        {"name": r["item_name"], "qty": r["qty_issued"], "unit": r["unit"]}
        for _, r in items_df.iterrows()
    ]

    html = generate_challan_html(
        challan_no=f"CHLN-{challan_id}",
        date=header["challan_date"].strftime("%d-%m-%Y"),
        po_no="",
        project_location=header["project_location"],
        items=items
    )

    st.markdown("---")
    st.subheader(f"Printable Challan CHLN-{challan_id}")
    st.components.v1.html(html, height=900, scrolling=True)
