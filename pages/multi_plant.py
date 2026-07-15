"""Multi-Plant Parallel Automation — credentials loaded from PostgreSQL"""
from __future__ import annotations
import asyncio, json, queue, threading, time
from pathlib import Path
import streamlit as st
import config
import db
from excel_processor import load_records

st.set_page_config(page_title="Multi-Plant Automation", page_icon="🏭",
                   layout="wide", initial_sidebar_state="expanded")

st.markdown("""<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
html,body,[class*="css"]{font-family:'Inter',sans-serif;}
.stApp{background:linear-gradient(135deg,#0f172a,#1e293b,#0f172a);min-height:100vh;}
.card{background:rgba(30,41,59,.85);border:1px solid rgba(255,255,255,.08);
      border-radius:14px;padding:20px;margin-bottom:16px;}
.card-t{font-size:.8rem;font-weight:700;color:#94a3b8;text-transform:uppercase;
        letter-spacing:1px;margin-bottom:14px;}
.log-box{background:rgba(10,15,30,.97);border:1px solid rgba(255,255,255,.06);
         border-radius:8px;padding:14px;height:300px;overflow-y:auto;
         font-family:'Courier New',monospace;font-size:.78rem;line-height:1.6;color:#94a3b8;}
.ok{color:#34d399}.err{color:#f87171}.warn{color:#fbbf24}.info{color:#60a5fa}
.sg{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;margin-bottom:14px;}
.sb{background:rgba(15,23,42,.8);border:1px solid rgba(255,255,255,.07);
    border-radius:10px;padding:14px;text-align:center;}
.sn{font-size:1.8rem;font-weight:700;line-height:1}
.sl{font-size:.7rem;color:#64748b;margin-top:4px;}
.c-blue{color:#60a5fa}.c-green{color:#34d399}.c-red{color:#f87171}.c-yellow{color:#fbbf24}
.otp-box{background:rgba(251,191,36,.1);border:2px solid #fbbf24;border-radius:10px;
         padding:14px;margin:10px 0;animation:otpP 2s infinite;}
@keyframes otpP{0%,100%{box-shadow:0 0 0 rgba(251,191,36,0)}
               50%{box-shadow:0 0 16px rgba(251,191,36,.4)}}
[data-testid="stWidgetLabel"],[data-testid="stWidgetLabel"] p
{color:#fbbf24!important;font-weight:500!important;}
.stButton>button{border-radius:10px!important;font-weight:600!important;}
section[data-testid="stSidebar"]{background:rgba(15,23,42,.97)!important;}
</style>""", unsafe_allow_html=True)

# ── Init DB ───────────────────────────────────────────────────────────────────
db.init_db()

# ── Load plants from DB ───────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def _load_plants():
    return db.get_all_plants()

def _refresh_plants():
    st.cache_data.clear()

_db_plants = _load_plants()
_db_ok     = db.test_connection()[0]

# ── Runtime state helpers ─────────────────────────────────────────────────────
def _make_rt():
    return {
        "log_q": queue.Queue(), "otp_resp_q": queue.Queue(),
        "stop_event": threading.Event(),
        "otp_requested": False, "otp_submitted": False,
        "running": False, "done": False,
        "log_lines": [], "pdf_files": [],
        "live_success": 0, "live_failed": 0, "live_skipped": 0,
        "progress_done": 0, "progress_total": 0,
        "error_msg": "",
    }

# Session state keyed by plant_name
if "mp_rt"  not in st.session_state: st.session_state.mp_rt  = {}
if "mp_cfg" not in st.session_state: st.session_state.mp_cfg = {}
if "mp_sel" not in st.session_state: st.session_state.mp_sel = None
# Per-plant TP credential overrides (username/password entered by user for TP mode)
if "mp_tp_creds" not in st.session_state: st.session_state.mp_tp_creds = {}

# Initialise state for any new plants
for _p in _db_plants:
    _pn = _p["plant_name"]
    if _pn not in st.session_state.mp_rt:
        st.session_state.mp_rt[_pn]  = _make_rt()
    if _pn not in st.session_state.mp_cfg:
        st.session_state.mp_cfg[_pn] = {"records": [], "_fid": "",
                                         "mode": "MDL", "headless": False}

# Default selection
if st.session_state.mp_sel not in [p["plant_name"] for p in _db_plants]:
    st.session_state.mp_sel = _db_plants[0]["plant_name"] if _db_plants else None

# ── Drain ALL plant log queues on every rerun ─────────────────────────────────
_any_running = False
for _pn, _rt in st.session_state.mp_rt.items():
    if not (_rt["running"] or _rt["done"]): continue
    if _rt["running"]: _any_running = True
    while True:
        try: _m = _rt["log_q"].get_nowait()
        except queue.Empty: break
        if _m == "__OTP_REQUESTED__":
            _rt["otp_requested"] = True; _rt["otp_submitted"] = False
        elif _m.startswith("__ERROR__"):
            _rt["error_msg"] = _m[len("__ERROR__"):]
            _rt["running"] = False; _rt["done"] = True
        elif _m.startswith("__PROGRESS__"):
            _,_,d,t = _m.split("__")
            _rt["progress_done"] = int(d); _rt["progress_total"] = int(t)
        elif _m.startswith("__RECORD_DONE__"):
            r = _m[len("__RECORD_DONE__"):].strip()
            if r == "success":  _rt["live_success"] += 1
            elif r == "failed": _rt["live_failed"]  += 1
            elif r == "skipped":_rt["live_skipped"] += 1
        elif _m.startswith("__DONE__"):
            _rt["running"] = False; _rt["done"] = True
        elif _m.startswith("__PDF__"):
            p = _m[len("__PDF__"):]
            if p and p not in _rt["pdf_files"]: _rt["pdf_files"].append(p)
        else:
            _rt["log_lines"].append(_m)

# ── Sidebar — plant navigator ─────────────────────────────────────────────────
with st.sidebar:
    st.markdown("""
    <div style="padding:16px 8px 10px;border-bottom:1px solid rgba(255,255,255,.08);margin-bottom:10px;">
      <div style="font-size:1.1rem;font-weight:700;color:#fff;">🏭 Multi-Plant</div>
      <div style="font-size:.75rem;color:#475569;margin-top:2px;">Click a plant to manage it</div>
    </div>""", unsafe_allow_html=True)

    if not _db_ok:
        st.error("🔴 DB not connected")
        st.info("Go to ⚙️ Plant Config to fix connection")
    elif not _db_plants:
        st.warning("No plants in DB yet.")
        st.info("Go to ⚙️ Plant Config to add plants.")
    else:
        for _p in _db_plants:
            _pn  = _p["plant_name"]
            _rt2 = st.session_state.mp_rt.get(_pn, {})
            if _rt2.get("running"):           _ico = "🟡"
            elif _rt2.get("done") and _rt2.get("live_failed", 0) == 0: _ico = "✅"
            elif _rt2.get("done"):            _ico = "⚠️"
            else:                             _ico = "🔵"
            _is_sel = st.session_state.mp_sel == _pn
            _rec    = len(st.session_state.mp_cfg.get(_pn, {}).get("records", []))
            st.markdown(
                f'<div style="background:{"rgba(29,78,216,.25)" if _is_sel else "transparent"};'
                f'border:1.5px solid {"#1d4ed8" if _is_sel else "transparent"};'
                f'border-radius:10px;padding:10px 12px;margin-bottom:6px;">',
                unsafe_allow_html=True)
            if st.button(f"{_ico}  {_pn}", key=f"nav_{_pn}",
                         use_container_width=True,
                         type="primary" if _is_sel else "secondary"):
                st.session_state.mp_sel = _pn; st.rerun()
            if _rec:
                st.markdown(f'<div style="font-size:.7rem;color:#64748b;margin-top:-8px;'
                            f'padding-left:4px;">{_rec} records loaded</div>',
                            unsafe_allow_html=True)
            st.markdown('</div>', unsafe_allow_html=True)

    st.markdown('<hr style="border-color:rgba(255,255,255,.08);margin:8px 0;">', unsafe_allow_html=True)
    _running_count = sum(1 for r in st.session_state.mp_rt.values() if r.get("running"))
    st.markdown(
        f'<div style="font-size:.78rem;color:#94a3b8;text-align:center;">'
        f'{"🟡 "+str(_running_count)+" plant(s) running" if _running_count else "No plants running"}'
        f'</div>', unsafe_allow_html=True)
    if st.button("🔄 Refresh Plants", key="mp_refresh", use_container_width=True):
        _refresh_plants(); st.rerun()

# ── No plants guard ───────────────────────────────────────────────────────────
if not _db_plants or st.session_state.mp_sel is None:
    st.markdown("""
    <div style="background:rgba(30,41,59,.85);border:1px solid rgba(255,255,255,.08);
    border-radius:14px;padding:40px;text-align:center;margin-top:40px;">
      <div style="font-size:2rem;margin-bottom:12px;">🏭</div>
      <div style="font-size:1.2rem;font-weight:700;color:#e2e8f0;margin-bottom:8px;">
        No Plants Configured
      </div>
      <div style="color:#94a3b8;font-size:.9rem;">
        Go to <b>⚙️ Plant Config</b> in the sidebar to add your plants with credentials.
      </div>
    </div>""", unsafe_allow_html=True)
    st.stop()

# ── Main area — selected plant ────────────────────────────────────────────────
_sel  = st.session_state.mp_sel
_cfg  = st.session_state.mp_cfg.get(_sel, {"records":[], "_fid":"", "mode":"MDL", "headless":False})
_rt   = st.session_state.mp_rt.get(_sel, _make_rt())
_pdata = db.get_plant(_sel)   # credentials from DB (hidden from UI)

# Status badge
if _rt["running"]:    _status,_bclr = "🟡 Running…","#fbbf24"
elif _rt["done"] and _rt["live_failed"] == 0: _status,_bclr = "✅ Complete","#34d399"
elif _rt["done"]:     _status,_bclr = f"⚠️ Done ({_rt['live_failed']} failed)","#f87171"
else:                 _status,_bclr = "🔵 Ready to start","#60a5fa"

st.markdown(f"""
<div style="background:linear-gradient(90deg,#0f4c81,#1565c0);border-radius:16px;
padding:20px 28px;margin-bottom:20px;display:flex;align-items:center;
justify-content:space-between;box-shadow:0 8px 32px rgba(21,101,192,.4)">
  <div>
    <div style="font-size:1.8rem;font-weight:700;color:#fff;">🏭 {_sel}</div>
    <div style="color:rgba(255,255,255,.7);font-size:.85rem;margin-top:4px;">
      Credentials loaded from database · Mode &amp; Excel selected below
    </div>
  </div>
  <div style="background:rgba(255,255,255,.15);border:1.5px solid {_bclr};
  border-radius:50px;padding:8px 20px;color:#fff;font-size:.9rem;font-weight:600;">
    {_status}
  </div>
</div>""", unsafe_allow_html=True)

if _pdata is None:
    st.error(f"❌ Plant '{_sel}' not found in database. Please re-add it via ⚙️ Plant Config.")
    st.stop()

# ── Two columns ───────────────────────────────────────────────────────────────
_col_l, _col_r = st.columns([1, 1], gap="large")

with _col_l:
    # ── Mode selector (needed early to decide credential display) ──────────────
    st.markdown('<div class="card"><div class="card-t">⚙️ Run Configuration</div>',
                unsafe_allow_html=True)
    _cfg["mode"] = st.selectbox("Mode", ["MDL", "TP", "Govt. Royalty"],
                                 index=["MDL","TP","Govt. Royalty"].index(_cfg.get("mode","MDL")),
                                 key=f"mode_{_sel}", disabled=_rt["running"])
    _cfg["headless"] = st.toggle("🕶️ Headless (hide browser)", value=_cfg.get("headless", False),
                                  key=f"hl_{_sel}", disabled=_rt["running"])
    _cfg["delay"] = st.number_input("⏱️ Delay between records (sec)",
                                     min_value=1.0, max_value=30.0,
                                     value=float(_cfg.get("delay", 3.0)),
                                     step=0.5, key=f"delay_{_sel}",
                                     disabled=_rt["running"])
    st.markdown('</div>', unsafe_allow_html=True)

    # ── Credentials card — behaviour depends on selected mode ─────────────────
    _is_tp_mode = (_cfg["mode"] == "TP")

    # Initialise TP credential store for this plant if missing
    if _sel not in st.session_state.mp_tp_creds:
        st.session_state.mp_tp_creds[_sel] = {"username": "", "password": ""}
    _tp_creds = st.session_state.mp_tp_creds[_sel]

    if _is_tp_mode:
        # ── TP mode: user supplies username + password manually ────────────────
        st.markdown("""
<div class="card">
  <div class="card-t">🔐 TP Login Credentials</div>
  <div style="background:rgba(251,191,36,.08);border:1px solid rgba(251,191,36,.35);
  border-radius:10px;padding:10px 14px;margin-bottom:12px;font-size:.8rem;color:#fbbf24;">
    ✏️ <b>TP mode</b> — enter your Telangana Mines portal username &amp; password below.
    These are used only for this run and are never stored.
  </div>""", unsafe_allow_html=True)

        _tp_creds["username"] = st.text_input(
            "👤 Username",
            value=_tp_creds.get("username", ""),
            key=f"tp_user_{_sel}",
            disabled=_rt["running"],
            placeholder="Enter portal username…"
        )
        _tp_creds["password"] = st.text_input(
            "🔑 Password",
            value=_tp_creds.get("password", ""),
            key=f"tp_pass_{_sel}",
            type="password",
            disabled=_rt["running"],
            placeholder="Enter portal password…"
        )
        st.markdown('</div>', unsafe_allow_html=True)
    else:
        # ── MDL / Govt. Royalty: credentials come silently from database ───────
        st.markdown('<div class="card"><div class="card-t">🔒 Credentials (from Database)</div>',
                    unsafe_allow_html=True)
        st.markdown(f"""
<div style="display:grid;gap:8px;">
  <div style="background:rgba(15,23,42,.6);border-radius:8px;padding:10px 14px;
  display:flex;justify-content:space-between;align-items:center;">
    <span style="color:#64748b;font-size:.82rem;">👤 Username</span>
    <span style="color:#e2e8f0;font-size:.85rem;font-weight:600;">{_pdata['username']}</span>
  </div>
  <div style="background:rgba(15,23,42,.6);border-radius:8px;padding:10px 14px;
  display:flex;justify-content:space-between;align-items:center;">
    <span style="color:#64748b;font-size:.82rem;">🔑 Password</span>
    <span style="color:#e2e8f0;font-size:.85rem;font-weight:600;">{'•' * 8}</span>
  </div>
</div>
<div style="margin-top:6px;font-size:.75rem;color:#475569;">
  🔒 Username &amp; password auto-loaded from DB · To update go to <b>⚙️ Plant Config</b>
</div>""", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

    # ── PDF Save Folder — always visible for ALL modes ─────────────────────────
    st.markdown('<div class="card"><div class="card-t">📁 PDF Save Folder</div>',
                unsafe_allow_html=True)
    _cfg["pdf_folder"] = st.text_input(
        "📁 PDF Save Folder",
        value=_cfg.get("pdf_folder", _pdata["pdf_save_folder"]),
        key=f"pdf_folder_{_sel}",
        disabled=_rt["running"],
        placeholder=r"e.g. C:\Users\YourName\Desktop\PDFs",
        label_visibility="collapsed",
        help="Path where PDFs will be saved. Pre-filled from database — edit to override."
    )
    st.markdown(
        '<div style="font-size:.75rem;color:#475569;margin-top:4px;">'
        '✏️ You can change this path before starting. '
        'Pre-filled from the database — your changes are not saved back to DB.'
        '</div>',
        unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)


    # Excel upload
    st.markdown('<div class="card"><div class="card-t">📂 Excel Data File</div>',
                unsafe_allow_html=True)
    _up = st.file_uploader("Upload Excel", type=["xlsx","xls"],
                            key=f"up_{_sel}", disabled=_rt["running"],
                            label_visibility="collapsed")
    if _up:
        _fid = f"{_up.name}_{_up.size}"
        if _cfg.get("_fid") != _fid:
            _sp = Path(f"mp_upload_{_sel.replace(' ','_')}.xlsx")
            _sp.write_bytes(_up.read())
            _recs, _ = load_records(str(_sp))
            _cfg["records"] = _recs; _cfg["_fid"] = _fid
        st.success(f"✅ {len(_cfg['records'])} records loaded from {_up.name}")
    elif _cfg.get("records"):
        st.success(f"✅ {len(_cfg['records'])} records ready")
    else:
        st.info("📂 Upload the Excel file for this plant")
    st.markdown('</div>', unsafe_allow_html=True)

    # Start / Stop
    # For TP mode — validate that the user has entered credentials
    _tp_creds_ok = (not _is_tp_mode) or (
        bool(_tp_creds.get("username", "").strip()) and
        bool(_tp_creds.get("password", "").strip())
    )
    _ready = bool(_cfg.get("records")) and _tp_creds_ok
    if _is_tp_mode and not _tp_creds_ok and _cfg.get("records"):
        st.warning("⚠️ Enter your TP portal username and password above before starting.")

    _b1, _b2 = st.columns(2)
    with _b1:
        if st.button(f"🚀 Start {_sel}", disabled=_rt["running"] or not _ready,
                     use_container_width=True, type="primary", key=f"start_{_sel}"):
            import importlib, config as _lc, automation as _la, platform
            importlib.reload(_lc); importlib.reload(_la)
            from automation import run_batch as _rb
            config.DELAY_BETWEEN_RECORDS = 3.0

            _lrt = st.session_state.mp_rt[_sel]

            # TP mode → use manually entered credentials
            # MDL / Govt. Royalty → use credentials from database
            if _cfg["mode"] == "TP":
                _run_username = st.session_state.mp_tp_creds[_sel]["username"].strip()
                _run_password = st.session_state.mp_tp_creds[_sel]["password"].strip()
            else:
                _run_username = _pdata["username"]
                _run_password = _pdata["password"]

            _lps = {
                "plant_name": _sel,
                "username":   _run_username,
                "password":   _run_password,
                # Use user-entered PDF folder (falls back to DB value if untouched)
                "pdf_folder": _cfg.get("pdf_folder", _pdata["pdf_save_folder"]).strip() or _pdata["pdf_save_folder"],
                "mode":       _cfg["mode"],
                "headless":   _cfg["headless"],
                "delay":      float(_cfg.get("delay", 3.0)),
                "records":    list(_cfg["records"]),
            }
            for _q in (_lrt["log_q"], _lrt["otp_resp_q"]):
                while not _q.empty():
                    try: _q.get_nowait()
                    except: break
            _lrt["stop_event"].clear()
            _lrt.update({"otp_requested":False,"otp_submitted":False,
                          "running":True,"done":False,"log_lines":[],"pdf_files":[],
                          "error_msg":"","live_success":0,"live_failed":0,
                          "live_skipped":0,"progress_done":0,
                          "progress_total":len(_lps["records"])})

            _lh = True if platform.system() == "Linux" else _lps["headless"]
            _prof = f"chrome_profile_{_sel.lower().replace(' ','_')}"

            def _run(_ps=_lps, _r=_lrt, _h=_lh, _rb2=_rb, _prof=_prof):
                _lq = _r["log_q"]; _oq = _r["otp_resp_q"]
                _lq.put(f"🚀 [{_ps['plant_name']}] Starting — {len(_ps['records'])} records")
                loop = asyncio.new_event_loop(); asyncio.set_event_loop(loop)
                try:
                    config.DELAY_BETWEEN_RECORDS = _ps["delay"]
                    res = loop.run_until_complete(_rb2(
                        records=_ps["records"], username=_ps["username"],
                        password=_ps["password"],
                        log_fn=lambda m,q=_lq: q.put(m),
                        otp_fn=lambda q=_oq: q.get(timeout=config.OTP_WAIT_TIMEOUT),
                        progress_fn=lambda d,t,q=_lq: q.put(f"__PROGRESS__{d}__{t}"),
                        headless=_h, pdf_folder=_ps["pdf_folder"],
                        mode=_ps["mode"], chrome_profile_dir=_prof,
                        stop_event=_r["stop_event"],
                    ))
                    try: _lq.put("__RESULTS__"+json.dumps(res, default=str))
                    except: pass
                except Exception as ex:
                    import traceback
                    _lq.put(f"💥 Fatal: {ex}\n{traceback.format_exc()}")
                finally:
                    loop.close(); _lq.put("__DONE__0")

            threading.Thread(target=_run, daemon=True,
                             name=f"plant_{_sel}").start()
            st.rerun()

    with _b2:
        if st.button(f"⏹️ Stop {_sel}", disabled=not _rt["running"],
                     use_container_width=True, key=f"stop_{_sel}"):
            _rt["stop_event"].set()
            _rt["log_q"].put("⏹️ Stop requested — browser closing…")
            st.toast(f"Stop sent to {_sel} — closing browser!", icon="⏹️")

    if _rt["done"]:
        if st.button("🗑️ Reset This Plant", use_container_width=True, key=f"reset_{_sel}"):
            _rt["stop_event"].clear()
            _rt.update({"done":False,"log_lines":[],"pdf_files":[],"error_msg":"",
                        "live_success":0,"live_failed":0,"live_skipped":0,
                        "progress_done":0,"progress_total":0,
                        "otp_requested":False,"otp_submitted":False})
            st.rerun()

with _col_r:
    # Error popup
    _err = _rt.get("error_msg","")
    if _err:
        _parts   = _err.split("|")
        _etitle  = _parts[0] if len(_parts)>0 else "Error"
        _edetail = _parts[1] if len(_parts)>1 else ""
        _eaction = _parts[2] if len(_parts)>2 else "Close Chrome and try again."
        st.markdown(f"""
<div style="background:rgba(239,68,68,.12);border:2px solid #ef4444;
border-radius:14px;padding:22px;margin-bottom:18px;
box-shadow:0 4px 24px rgba(239,68,68,.25);">
  <div style="font-size:1.15rem;font-weight:700;color:#f87171;margin-bottom:8px;">
    🚨 {_etitle}</div>
  <div style="color:#fca5a5;font-size:.9rem;margin-bottom:12px;">{_edetail}</div>
  <div style="background:rgba(255,255,255,.06);border-radius:8px;
  padding:12px;border-left:3px solid #fbbf24;">
    <span style="color:#fbbf24;font-weight:600;">👉 Action Required: </span>
    <span style="color:#e2e8f0;font-size:.88rem;">{_eaction}</span>
  </div>
</div>""", unsafe_allow_html=True)
        if st.button("✖ Dismiss & Reset Plant", use_container_width=True,
                     key=f"err_dismiss_{_sel}", type="secondary"):
            _rt["stop_event"].set()
            _rt.update({"error_msg":"","done":False,"running":False,
                        "log_lines":[],"pdf_files":[],"otp_requested":False,
                        "otp_submitted":False,"live_success":0,"live_failed":0,
                        "live_skipped":0,"progress_done":0,"progress_total":0})
            _rt["stop_event"].clear()
            st.toast("Plant reset.", icon="🔄"); st.rerun()

    # OTP section (hidden on error)
    if not _err:
        _otp_needed = _rt["running"] and _rt["otp_requested"] and not _rt["otp_submitted"]
        if _otp_needed:
            st.markdown(
                f'<div class="otp-box">'
                f'<div style="font-size:1rem;font-weight:700;color:#fbbf24;">📲 OTP Required!</div>'
                f'<div style="font-size:.85rem;color:#94a3b8;margin-top:4px;">'
                f'OTP sent to mobile linked to <b>{_pdata["username"]}</b>.<br>'
                f'Enter it below and click Submit.</div></div>',
                unsafe_allow_html=True)
        _oc1,_oc2 = st.columns([3,1])
        with _oc1:
            _otp_val = st.text_input("OTP", max_chars=8, key=f"otp_{_sel}",
                placeholder="Enter OTP here" if _otp_needed else "Waiting for automation…",
                disabled=not _otp_needed, label_visibility="collapsed")
        with _oc2:
            if st.button("✅ Submit OTP", key=f"otp_btn_{_sel}",
                         disabled=not _otp_needed, use_container_width=True,
                         type="primary" if _otp_needed else "secondary"):
                if _otp_val and _otp_val.strip():
                    _rt["otp_resp_q"].put(_otp_val.strip())
                    _rt["otp_submitted"] = True
                    st.toast(f"✅ OTP submitted for {_sel}!", icon="✅")
                    st.rerun()
                else:
                    st.error("Enter OTP before submitting.")
    else:
        st.info("⚠️ Fix the error above first — OTP field is hidden until error is dismissed.")

    # Stats
    if _rt["running"] or _rt["done"]:
        _tot = max(_rt["progress_total"] or len(_cfg.get("records",[])), 1)
        _suc = _rt["live_success"]; _fal = _rt["live_failed"]; _skp = _rt["live_skipped"]
        _pend = max(0, _tot - _suc - _fal - _skp)
        st.markdown(f"""<div class="sg">
<div class="sb"><div class="sn c-blue">{_tot}</div><div class="sl">Total</div></div>
<div class="sb"><div class="sn c-green">{_suc}</div><div class="sl">✅ Success</div></div>
<div class="sb"><div class="sn c-red">{_fal}</div><div class="sl">❌ Failed</div></div>
<div class="sb"><div class="sn c-yellow">{_pend}</div><div class="sl">⏳ Pending</div></div>
</div>""", unsafe_allow_html=True)
        if _rt["running"] and _rt["progress_total"] > 0:
            st.progress(_rt["progress_done"] / _rt["progress_total"],
                        text=f"Record {_rt['progress_done']}/{_rt['progress_total']}")

    # Log
    st.markdown('<div class="card"><div class="card-t">📋 Live Log</div>',
                unsafe_allow_html=True)
    def _cls(l):
        lo = l.lower()
        if "✅" in l or "success" in lo or "saved" in lo: return "ok"
        if "❌" in l or "error" in lo or "fail" in lo:    return "err"
        if "⚠" in l or "warn" in lo:                      return "warn"
        return "info"
    _lh = "\n".join(f'<div class="{_cls(l)}">{l}</div>' for l in _rt["log_lines"][-200:]) \
          or '<div style="color:#475569">No logs yet — start automation above.</div>'
    st.markdown(f'<div class="log-box">{_lh}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # PDFs
    if _rt["pdf_files"]:
        st.markdown(f'<div class="card"><div class="card-t">📄 PDFs — {len(_rt["pdf_files"])} file(s)</div>',
                    unsafe_allow_html=True)
        for _pp_str in _rt["pdf_files"]:
            _pp = Path(_pp_str)
            if _pp.exists():
                with open(str(_pp),"rb") as _f:
                    st.download_button(f"⬇️ {_pp.name}", _f.read(),
                                       file_name=_pp.name, mime="application/pdf",
                                       key=f"dl_{_sel}_{_pp.stem}",
                                       use_container_width=True)
        st.markdown('</div>', unsafe_allow_html=True)

# ── Auto-refresh ──────────────────────────────────────────────────────────────
if _any_running:
    time.sleep(1.2)
    st.rerun()
