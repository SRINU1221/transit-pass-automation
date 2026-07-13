"""
app.py — Entry point.
Only the Multi-Plant page is shown in the sidebar.
Single-plant and Plant Config pages are hidden from navigation.
"""
import streamlit as st

pg = st.navigation([
    st.Page("pages/multi_plant.py", title="Multi-Plant Automation", icon="🏭"),
])
pg.run()
