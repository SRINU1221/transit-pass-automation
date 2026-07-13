"""Plant Config — Admin page to manage plant credentials in PostgreSQL"""
import streamlit as st
import db

st.set_page_config(page_title="Plant Config", page_icon="⚙️",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif;}
.stApp{background:linear-gradient(135deg,#0f172a,#1e293b,#0f172a);min-height:100vh;}
.card{background:rgba(30,41,59,.85);border:1px solid rgba(255,255,255,.08);
      border-radius:14px;padding:20px;margin-bottom:16px;}
.card-t{font-size:.8rem;font-weight:700;color:#94a3b8;text-transform:uppercase;
        letter-spacing:1px;margin-bottom:14px;}
.stButton>button{border-radius:10px!important;font-weight:600!important;}
section[data-testid="stSidebar"]{background:rgba(15,23,42,.97)!important;}
</style>""", unsafe_allow_html=True)

# ── Init DB on load ──────────────────────────────────────────────────────────
_ok, _msg = db.init_db()

# ── Header ───────────────────────────────────────────────────────────────────
st.markdown("""
<div style="background:linear-gradient(90deg,#1e3a5f,#1565c0);border-radius:16px;
padding:20px 28px;margin-bottom:24px;box-shadow:0 8px 32px rgba(21,101,192,.4)">
  <div style="font-size:1.8rem;font-weight:700;color:#fff;">⚙️ Plant Configuration</div>
  <div style="color:rgba(255,255,255,.7);font-size:.85rem;margin-top:4px;">
    Manage plant credentials stored in PostgreSQL. Changes take effect immediately.
  </div>
</div>""", unsafe_allow_html=True)

# ── DB Status ────────────────────────────────────────────────────────────────
_ok_conn, _conn_msg = db.test_connection()
if _ok_conn:
    st.success(f"🟢 Database connected — `automationDB` | `rayalty` table ready")
else:
    st.error(f"🔴 Database not connected — {_conn_msg}")
    st.info("👉 Edit the `.env` file in the project folder with your PostgreSQL credentials, then restart the app.")
    st.code("DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@localhost:5432/automationDB")
    st.stop()

st.markdown("---")

# ── Left: Add / Edit form  |  Right: Plants table ────────────────────────────
col_form, col_table = st.columns([1, 2], gap="large")

with col_form:
    # ── Add / Edit plant ─────────────────────────────────────────────────────
    st.markdown('<div class="card"><div class="card-t">➕ Add / Update Plant</div>',
                unsafe_allow_html=True)

    if "edit_plant" not in st.session_state:
        st.session_state.edit_plant = {}

    ep = st.session_state.edit_plant
    _pname  = st.text_input("🏭 Plant Name",    value=ep.get("plant_name",""),
                             placeholder="e.g. Mamidipally", key="frm_pname")
    _uname  = st.text_input("👤 Username",       value=ep.get("username",""),
                             placeholder="EPermit login ID", key="frm_uname")
    _pwd    = st.text_input("🔑 Password",       value=ep.get("password",""),
                             type="password",   key="frm_pwd")
    _pdf    = st.text_input("📁 PDF Save Folder",value=ep.get("pdf_save_folder",""),
                             placeholder=r"e.g. D:\PDFs\Mamidipally", key="frm_pdf")

    _b1, _b2 = st.columns(2)
    with _b1:
        if st.button("💾 Save Plant", use_container_width=True,
                     type="primary", key="frm_save"):
            if not (_pname and _uname and _pwd and _pdf):
                st.error("All fields are required.")
            else:
                ok, msg = db.upsert_plant(_pname.strip(), _uname.strip(),
                                          _pwd.strip(), _pdf.strip())
                if ok:
                    st.success(msg)
                    st.session_state.edit_plant = {}
                    st.rerun()
                else:
                    st.error(msg)
    with _b2:
        if st.button("🔄 Clear Form", use_container_width=True, key="frm_clear"):
            st.session_state.edit_plant = {}
            st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)

    # ── DB info ───────────────────────────────────────────────────────────────
    st.markdown('<div class="card"><div class="card-t">ℹ️ Database Info</div>',
                unsafe_allow_html=True)
    st.markdown("""
<div style="font-size:.82rem;color:#94a3b8;line-height:2;">
  <b style="color:#e2e8f0;">Database:</b> automationDB<br>
  <b style="color:#e2e8f0;">Table:</b> rayalty<br>
  <b style="color:#e2e8f0;">Columns:</b> plant_name, username, password, pdf_save_folder<br>
  <b style="color:#e2e8f0;">Config file:</b> .env in project root
</div>""", unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

with col_table:
    st.markdown('<div class="card"><div class="card-t">🏭 Registered Plants</div>',
                unsafe_allow_html=True)

    plants = db.get_all_plants()
    if not plants:
        st.info("No plants registered yet. Use the form on the left to add your first plant.")
    else:
        # Header row
        _h1,_h2,_h3,_h4,_h5 = st.columns([2,2,2,1,1])
        for _h,_t in zip((_h1,_h2,_h3,_h4,_h5),
                          ("Plant Name","Username","PDF Folder","","",)):
            _h.markdown(f"<div style='font-size:.72rem;font-weight:700;color:#64748b;"
                        f"text-transform:uppercase;letter-spacing:.8px;'>{_t}</div>",
                        unsafe_allow_html=True)
        st.markdown("<hr style='border-color:rgba(255,255,255,.08);margin:6px 0 10px;'>",
                    unsafe_allow_html=True)

        for _p in plants:
            _c1,_c2,_c3,_c4,_c5 = st.columns([2,2,2,1,1])
            with _c1:
                st.markdown(f"<div style='color:#e2e8f0;font-weight:600;font-size:.88rem;"
                            f"padding:4px 0;'>{_p['plant_name']}</div>",
                            unsafe_allow_html=True)
            with _c2:
                st.markdown(f"<div style='color:#94a3b8;font-size:.85rem;padding:4px 0;'>"
                            f"{_p['username']}</div>", unsafe_allow_html=True)
            with _c3:
                _short = str(_p['pdf_save_folder'])
                if len(_short) > 28: _short = "…" + _short[-27:]
                st.markdown(f"<div style='color:#94a3b8;font-size:.82rem;padding:4px 0;'>"
                            f"{_short}</div>", unsafe_allow_html=True)
            with _c4:
                if st.button("✏️", key=f"edit_{_p['plant_name']}",
                             help=f"Edit {_p['plant_name']}",
                             use_container_width=True):
                    st.session_state.edit_plant = {
                        "plant_name":      _p["plant_name"],
                        "username":        _p["username"],
                        "password":        _p["password"],
                        "pdf_save_folder": _p["pdf_save_folder"],
                    }
                    st.rerun()
            with _c5:
                if st.button("🗑️", key=f"del_{_p['plant_name']}",
                             help=f"Delete {_p['plant_name']}",
                             use_container_width=True):
                    ok, msg = db.delete_plant(_p["plant_name"])
                    if ok:
                        st.toast(msg, icon="🗑️")
                    else:
                        st.error(msg)
                    st.rerun()

    st.markdown('</div>', unsafe_allow_html=True)
