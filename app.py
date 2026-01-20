import streamlit as st
from utils.auth import keycloak_login

st.set_page_config(page_title="SOR-BOQ App", layout="wide")

user = keycloak_login()

if not user:
    st.warning("Please log in to access the application.")
    st.stop()

st.success(f"Welcome, {user}!")

st.title("Landing Page")
st.subheader("Choose an action:")

cols = st.columns(2)
with cols[0]:
    if st.button("1. SOR–BOQ Matching"):
        st.switch_page("pages/1_SOR_BOQ_Matching.py")
    if st.button("2. Page Two"):
        st.switch_page("pages/2_Page_Two.py")

with cols[1]:
    if st.button("3. Page Three"):
        st.switch_page("pages/3_Page_Three.py")
    if st.button("4. Page Four"):
        st.switch_page("pages/4_Page_Four.py")
