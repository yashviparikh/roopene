import streamlit as st
import pandas as pd
from sqlalchemy import text
from db_config import get_engine
from sqlalchemy.exc import OperationalError

st.set_page_config(page_title="Inventory Tracking", layout="wide")
st.title("Inventory Management")

engine = get_engine()

if "inventory_items" not in st.session_state or not st.session_state.inventory_items:
    st.session_state.inventory_items = [{"item_name": "", "qty": 0, "rate": 0.0, "unit": "kg"}]

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
                background-color: #ffffff;
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

create_inventory_table()

module = st.radio(
    "Select Operation",
    ["Add Inventory", "View Inventory", "Generate Challan"],
    horizontal=True
)

# ------------------- ADD INVENTORY -------------------
if module == "Add Inventory":
    st.header("Add Inventory (Batch-wise)")

    # Initialize session state once
    if "inventory_items" not in st.session_state:
        st.session_state.inventory_items = [
            {"item_name": "", "qty": 0, "rate": 0.0, "unit": "kg"}
        ]

    # -------- ADD ITEM (OUTSIDE FORM — REQUIRED) --------
    if st.button("➕ Add Item"):
        st.session_state.inventory_items.append(
            {"item_name": "", "qty": 0, "rate": 0.0, "unit": "kg"}
        )
        st.rerun()

    # ---------------- FORM START ----------------
    with st.form("batch_inventory_form", clear_on_submit=True):

        # ---------- BATCH INFO ----------
        col1, col2, col3 = st.columns(3)
        supplier = col1.text_input("Supplier Name / ID")
        batch_no = col2.text_input("Batch No")
        invoice_no = col3.text_input("Invoice No")
        purchase_date = st.date_input("Purchase Date")

        st.subheader("Add Items to Batch")

        updated_items = []

        # ---------- ITEM ROWS ----------
        for idx, item in enumerate(st.session_state.inventory_items):
            cols = st.columns([3, 2, 2, 2])

            item_name = cols[0].text_input(
                "Item Name",
                key=f"item_name_{idx}",
                value=item["item_name"],
                label_visibility="collapsed"
            )

            qty = cols[1].number_input(
                "Quantity",
                min_value=0,
                step=1,
                key=f"qty_{idx}",
                value=item["qty"],
                label_visibility="collapsed"
            )

            rate = cols[2].number_input(
                "Rate",
                min_value=0.0,
                step=0.01,
                format="%.2f",
                key=f"rate_{idx}",
                value=item["rate"],
                label_visibility="collapsed"
            )

            unit = cols[3].selectbox(
                "Unit",
                ["kg", "nos", "m", "ltr"],
                index=["kg", "nos", "m", "ltr"].index(item["unit"]),
                key=f"unit_{idx}",
                label_visibility="collapsed"
            )

            updated_items.append({
                "item_name": item_name,
                "qty": qty,
                "rate": rate,
                "unit": unit
            })

        # ---------- SUBMIT ----------
        submitted = st.form_submit_button("Save Batch Inventory")

    # ---------------- FORM END ----------------

    # Update state AFTER form render
    st.session_state.inventory_items = updated_items

    # ---------- SAVE LOGIC ----------
    if submitted:
        if not supplier.strip() or not batch_no.strip():
            st.error("Supplier and Batch No are required.")
            st.stop()

        valid_items = [
            i for i in st.session_state.inventory_items
            if i["item_name"] and i["qty"] > 0 and i["rate"] > 0
        ]

        if not valid_items:
            st.error("At least one valid item is required.")
            st.stop()

        with engine.begin() as conn:
            for item in valid_items:
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
                        "item": item["item_name"],
                        "supplier": supplier,
                        "batch": batch_no,
                        "pdate": purchase_date,
                        "invoice": invoice_no,
                        "qty": item["qty"],
                        "rate": item["rate"],
                        "unit": item["unit"]
                    }
                )

        st.success(f"Batch {batch_no} saved successfully!")

        # Reset to one default row
        st.session_state.inventory_items = [
            {"item_name": "", "qty": 0, "rate": 0.0, "unit": "kg"}
        ]

# ------------------- VIEW INVENTORY -------------------
elif module == "View Inventory":
    st.header("Current Inventory")

    # ---------- SEARCH FILTERS ----------
    col1, col2 = st.columns(2)
    supplier_filter = col1.text_input("Search by Supplier Name / ID")
    batch_filter = col2.text_input("Search by Batch No")

    query = "SELECT * FROM inventory_master WHERE 1=1"
    params = {}

    if supplier_filter.strip():
        query += " AND LOWER(supplier_name) LIKE LOWER(:supplier)"
        params["supplier"] = f"%{supplier_filter.strip()}%"

    if batch_filter.strip():
        query += " AND LOWER(batch_no) LIKE LOWER(:batch)"
        params["batch"] = f"%{batch_filter.strip()}%"

    query += " ORDER BY id DESC"

    # ---------- FETCH DATA ----------
    try:
        with engine.connect() as conn:
            inv_df = pd.read_sql(text(query), conn, params=params)

        if inv_df.empty:
            st.info("No inventory found for the given filters.")
        else:
            st.dataframe(inv_df, width='stretch')

    except OperationalError:
        st.error("Inventory table not found.")


# ------------------- GENERATE CHALLAN -------------------
elif module == "Generate Challan":

    # ---------------- INIT STATE ----------------
    if "challan_view_mode" not in st.session_state:
        st.session_state["challan_view_mode"] = "generate"

    if "search_inventory" not in st.session_state:
        st.session_state["search_inventory"] = False

    # ---------------- HEADER + ACTION BUTTONS ----------------
    header_col, action_col = st.columns([8, 2])
    with header_col:
        st.header("Generate Challan")

    # ---------------- BUTTONS ----------------
    with action_col:
        if st.session_state["challan_view_mode"] == "generate":
            view_col, reset_col = st.columns(2)

            # ---- VIEW / PRINT ----
            with view_col:
                if st.button("View / Print"):
                    st.session_state["challan_view_mode"] = "view"
                    st.rerun()

            # ---- RESET ----
            with reset_col:
                if st.button("Reset"):
                    st.session_state["search_inventory"] = False
                    st.session_state.pop("inv_df", None)

                    # remove all qty inputs
                    for key in list(st.session_state.keys()):
                        if key.startswith("qty_"):
                            del st.session_state[key]

                    st.rerun()

        elif st.session_state["challan_view_mode"] == "view":
            # Show only Back button in view mode
            if st.button("← Back to Generate", key="back_to_generate"):
                st.session_state["challan_view_mode"] = "generate"
                st.rerun()

    # =========================================================
    # ================= GENERATE MODE =========================
    # =========================================================
    if st.session_state["challan_view_mode"] == "generate":
        supplier = st.text_input("Supplier ID / Name")
        batch_no = st.text_input("Batch No")

        if st.button("Search Inventory"):
            st.session_state["search_inventory"] = True

        # -------- FETCH INVENTORY --------
        if st.session_state["search_inventory"]:
            try:
                with engine.connect() as conn:
                    inv_df = pd.read_sql(
                        text("""
                            SELECT 
                                id,
                                item_name,
                                supplier_name,
                                batch_no,
                                qty_available,
                                unit
                            FROM inventory_master
                            WHERE qty_available > 0
                              AND LOWER(supplier_name) LIKE LOWER(:supplier)
                              AND LOWER(batch_no) LIKE LOWER(:batch)
                            ORDER BY supplier_name, batch_no, item_name
                        """),
                        conn,
                        params={
                            "supplier": f"%{supplier}%",
                            "batch": f"%{batch_no}%"
                        }
                    )
                st.session_state["inv_df"] = inv_df
            except Exception:
                st.error("Unable to fetch inventory.")
                st.session_state["inv_df"] = pd.DataFrame()

        inv_df = st.session_state.get("inv_df", pd.DataFrame())

        if st.session_state["search_inventory"] and inv_df.empty:
            st.warning("No inventory found for given supplier / batch.")
            st.stop()

        issue_data = []

        if st.session_state["search_inventory"] and not inv_df.empty:
            st.success(f"{len(inv_df)} item(s) found")
            st.dataframe(inv_df, width='stretch')

            selected_ids = st.multiselect(
                "Select Inventory Items",
                inv_df["id"].tolist()
            )

            for inv_id in selected_ids:
                row = inv_df.loc[inv_df["id"] == inv_id].iloc[0]
                max_qty = float(row["qty_available"])
                key = f"qty_{inv_id}"

                if key not in st.session_state:
                    st.session_state[key] = 0.0

                qty = st.number_input(
                    f"Issue Qty – {row['item_name']} (Max {max_qty})",
                    min_value=0,
                    max_value=max_qty,
                    value=st.session_state[key],
                    step=1,
                    key=key
                )

                issue_data.append((inv_id, qty))

        project_location = st.text_input("Project Location")

        # -------- VALIDATION --------
        def is_challan_valid(data):
            return bool(data) and any(qty > 0 for _, qty in data)

        # -------- GENERATE CHALLAN --------
        if st.button("Generate Challan"):

            if not project_location.strip():
                st.error("Project Location is required.")
                st.stop()

            if not is_challan_valid(issue_data):
                st.error("All selected items have zero quantity.")
                st.stop()

            valid_items = [(iid, qty) for iid, qty in issue_data if qty > 0]

            with engine.begin() as conn:
                challan_id = conn.execute(
                    text("""
                        INSERT INTO challan_header
                        (supplier_id, project_location, challan_date)
                        VALUES (:supplier, :location, CURRENT_TIMESTAMP)
                    """),
                    {"supplier": supplier, "location": project_location}
                ).lastrowid

                for inv_id, qty in valid_items:
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

            st.session_state["challan_view_mode"] = "view"
            st.rerun()

        # ================= VIEW / PRINT MODE =====================
    if "opened_challan_id" not in st.session_state:
        st.session_state["opened_challan_id"] = None

    if st.session_state.get("challan_view_mode") == "view":

        title_col, _ = st.columns([8, 2])
        with title_col:
            st.subheader("View / Print Challans")

        # Fetch all challans
        with engine.connect() as conn:
            challan_df = pd.read_sql("""
                SELECT challan_id, supplier_id, project_location, challan_date
                FROM challan_header
                ORDER BY challan_date DESC
            """, conn)

        if challan_df.empty:
            st.info("No challans available.")
            st.stop()

        challan_df["challan_date"] = pd.to_datetime(challan_df["challan_date"])

        # ---------- TABLE HEADERS ----------
        h1, h2, h3, h4, h5 = st.columns([1.2, 2, 2, 1.5, 2])
        h1.markdown("**Challan No**")
        h2.markdown("**Supplier**")
        h3.markdown("**Project Location**")
        h4.markdown("**Date**")
        h5.markdown("**Actions**")
        st.divider()

        # ---------- TABLE ROWS ----------
        for _, row in challan_df.iterrows():
            challan_id = row["challan_id"]

            c1, c2, c3, c4, c5 = st.columns([1.2, 2, 2, 1.5, 2])
            c1.write(f"CHLN-{challan_id}")
            c2.write(row["supplier_id"])
            c3.write(row["project_location"])
            c4.write(row["challan_date"].strftime("%d-%m-%Y"))

            # Buttons
            b1, b2 = c5.columns(2)
            if b1.button("Open", key=f"open_{challan_id}"):
                st.session_state["opened_challan_id"] = challan_id
                st.rerun()

            if b2.button("Print", key=f"print_{challan_id}"):
                print_challan(challan_id)

        # ---------- OPENED CHALLAN PREVIEW (ONLY ONCE) ----------
        if st.session_state.get("opened_challan_id") is not None:
            open_id = st.session_state["opened_challan_id"]
            st.divider()
            title_col, close_col = st.columns([8, 2])
            with title_col:
                st.subheader(f"Challan Preview – CHLN-{open_id}")
            with close_col:
                if st.button("X", key=f"close_{open_id}"):
                    st.session_state["opened_challan_id"] = None
                    st.rerun()

            # Fetch header & items for preview
            with engine.connect() as conn:
                header = pd.read_sql(
                    text("SELECT * FROM challan_header WHERE challan_id = :cid"),
                    conn,
                    params={"cid": open_id}
                ).iloc[0]

                items_df = pd.read_sql(
                    text("""
                        SELECT im.item_name, im.unit, ci.qty_issued
                        FROM challan_items ci
                        JOIN inventory_master im ON ci.inventory_id = im.id
                        WHERE ci.challan_id = :cid
                    """),
                    conn,
                    params={"cid": open_id}
                )

            items = [
                {"name": r["item_name"], "qty": r["qty_issued"], "unit": r["unit"]}
                for _, r in items_df.iterrows()
            ]

            html = generate_challan_html(
                challan_no=f"CHLN-{open_id}",
                date=header["challan_date"],
                po_no="",
                project_location=header["project_location"],
                items=items
            )

            st.components.v1.html(html, height=900, scrolling=True)

# ---------- PRINT FUNCTION ----------
def print_challan(challan_id):
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
        date=header["challan_date"],
        po_no="",
        project_location=header["project_location"],
        items=items
    )

    html += """
    <script>
        window.onload = function() {
            window.print();
        }
    </script>
    """
    st.components.v1.html(html, height=900, scrolling=True)
