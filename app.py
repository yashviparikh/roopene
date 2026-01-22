import streamlit as st

st.set_page_config(page_title="SOR-BOQ App", layout="wide")
# if "authentication_status" not in st.session_state:
#     st.session_state["authentication_status"] = False
# st.success(f"Welcome, {user}!")

st.title("Landing Page")
st.subheader("Choose an action:")

cols = st.columns(2)
with cols[0]:
    if st.button("SOR–BOQ Matching"):
        st.switch_page("pages/sor-boq.py")
    if st.button("Inventory Manager"):
        st.switch_page("pages/inventory.py")

with cols[1]:
    if st.button("3. Page Three"):
        st.switch_page("pages/3_Page_Three.py")
    if st.button("4. Page Four"):
        st.switch_page("pages/4_Page_Four.py")
