"""
app.py — Transit Pass Automation Dashboard (Streamlit)
Run:  streamlit run app.py
"""
from __future__ import annotations

import asyncio
import json
import os
import queue
import threading
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

import config
from excel_processor import load_records, records_to_dataframe, add_status_column

# ─────────────────────────────────────────────────────────────────────────────
#  Page config + CSS
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Transit Pass Automation — Telangana Mines",
    page_icon="🚛",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap');
html,body,[class*="css"]{ font-family:'Inter',sans-serif; }

.stApp{
  background:linear-gradient(135deg,#0f172a 0%,#1e293b 50%,#0f172a 100%);
  min-height:100vh;
}
.hdr{
  background:linear-gradient(90deg,#0f4c81 0%,#1565c0 50%,#1976d2 100%);
  border-radius:16px;padding:24px 32px;margin-bottom:24px;
  display:flex;align-items:center;justify-content:space-between;
  box-shadow:0 8px 32px rgba(21,101,192,.4);
}
.hdr-title{font-size:1.9rem;font-weight:700;color:#fff;margin:0}
.hdr-sub{color:rgba(255,255,255,.75);font-size:.88rem;margin-top:4px}
.hdr-badge{
  background:rgba(255,255,255,.15);border:1px solid rgba(255,255,255,.25);
  border-radius:50px;padding:6px 18px;color:#fff;font-size:.8rem;font-weight:500;
}
.card{
  background:rgba(30,41,59,.85);border:1px solid rgba(255,255,255,.08);
  border-radius:14px;padding:22px;margin-bottom:18px;
  backdrop-filter:blur(20px);box-shadow:0 4px 24px rgba(0,0,0,.3);
}
.card-title{
  font-size:.85rem;font-weight:700;color:#94a3b8;
  text-transform:uppercase;letter-spacing:1px;margin-bottom:14px;
}
.sg{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin-bottom:20px}
.sb{
  background:rgba(30,41,59,.9);border:1px solid rgba(255,255,255,.07);
  border-radius:12px;padding:16px;text-align:center;
}
.sn{font-size:2rem;font-weight:700;line-height:1}
.sl{font-size:.75rem;color:#64748b;margin-top:4px;text-transform:uppercase;letter-spacing:.5px}
.c-blue{color:#60a5fa} .c-green{color:#34d399} .c-red{color:#f87171} .c-yellow{color:#fbbf24}

.log-box{
  background:rgba(10,15,30,.97);border:1px solid rgba(255,255,255,.06);
  border-radius:10px;padding:14px;height:340px;overflow-y:auto;
  font-family:'Courier New',monospace;font-size:.8rem;line-height:1.65;color:#94a3b8;
}
.ok{color:#34d399} .err{color:#f87171} .warn{color:#fbbf24} .info{color:#60a5fa}

/* OTP section — fixed below Step 3 buttons */
.otp-section{
  border-radius:12px;padding:18px 20px;margin-top:16px;
  transition:all .4s ease;
}
.otp-idle{
  background:rgba(30,41,59,.6);border:1.5px solid rgba(255,255,255,.08);
  opacity:.55;
}
.otp-active{
  background:linear-gradient(135deg,rgba(251,191,36,.15),rgba(245,158,11,.05));
  border:2px solid #fbbf24;
  animation:otpPulse 2s infinite;
  opacity:1;
}
@keyframes otpPulse{
  0%,100%{border-color:#fbbf24;box-shadow:0 0 0 rgba(251,191,36,0)}
  50%{border-color:#f59e0b;box-shadow:0 0 18px rgba(251,191,36,.35)}
}
.otp-label-idle{color:#475569;font-size:.82rem;font-weight:600;letter-spacing:.5px;text-transform:uppercase;margin-bottom:10px}
.otp-label-active{color:#fbbf24;font-size:.95rem;font-weight:700;margin-bottom:6px}
.otp-hint{color:#94a3b8;font-size:.82rem;margin-bottom:12px}

.pdf-card{
  background:rgba(16,185,129,.08);border:1px solid rgba(16,185,129,.25);
  border-radius:10px;padding:12px 16px;margin-bottom:8px;
  display:flex;align-items:center;justify-content:space-between;
}

.steps{display:flex;gap:8px;margin-bottom:22px}
.step{flex:1;padding:10px;border-radius:10px;text-align:center;font-size:.8rem;
      font-weight:600;border:1.5px solid rgba(255,255,255,.1);color:#475569}
.step.act{background:rgba(29,78,216,.2);border-color:#1d4ed8;color:#60a5fa}
.step.done{background:rgba(52,211,153,.1);border-color:#34d399;color:#34d399}

.stButton>button{font-family:'Inter',sans-serif!important;font-weight:600!important;
  border-radius:10px!important;transition:all .2s ease!important}
.stButton>button:hover{transform:translateY(-1px)!important;
  box-shadow:0 6px 20px rgba(0,0,0,.3)!important}

/* ── Yellow labels for all input widgets ───────────────────────────── */
.stTextInput     > label,
.stTextInput     > div > label,
.stSelectbox     > label,
.stSelectbox     > div > label,
.stNumberInput   > label,
.stNumberInput   > div > label,
.stCheckbox      > label,
.stCheckbox      > div > label,
.stRadio         > label,
.stRadio         > div > label,
.stFileUploader  > label,
.stFileUploader  > div > label,
.stSlider        > label,
.stSlider        > div > label,
.stTextArea      > label,
.stTextArea      > div > label,
[data-testid="stWidgetLabel"],
[data-testid="stWidgetLabel"] p,
div[data-testid*="Label"],
div[data-testid*="Label"] p {
  color: #fbbf24 !important;
  font-weight: 500 !important;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
#  Session State
# ─────────────────────────────────────────────────────────────────────────────

def _init():
    defs: dict = {
        "records":          [],
        "uploaded_path":    None,
        "log_lines":        [],
        "running":          False,
        "done":             False,
        "otp_requested":    False,
        "otp_submitted":    False,
        "progress_done":    0,
        "progress_total":   0,
        "result_records":   [],
        "pdf_files":        [],      # list of generated PDF paths
        "log_q":            queue.Queue(),
        "otp_resp_q":       queue.Queue(),
        "pdf_folder":       config.PDF_SAVE_FOLDER,
        # ── Live per-record counters (updated after every record via __RECORD_DONE__)
        "live_success":     0,
        "live_failed":      0,
        "live_skipped":     0,
        "live_current":     "",      # label of the record currently being processed
    }
    for k, v in defs.items():
        if k not in st.session_state:
            st.session_state[k] = v

_init()

# ─────────────────────────────────────────────────────────────────────────────
#  Drain log queue
# ─────────────────────────────────────────────────────────────────────────────

if st.session_state.running:
    _q = st.session_state.log_q
    while True:
        try:
            msg = _q.get_nowait()
        except queue.Empty:
            break

        if msg == "__OTP_REQUESTED__":
            st.session_state.otp_requested = True
            st.session_state.otp_submitted = False

        elif msg.startswith("__PROGRESS__"):
            _, _, done, total = msg.split("__")
            st.session_state.progress_done  = int(done)
            st.session_state.progress_total = int(total)

        elif msg.startswith("__RECORD_DONE__"):
            # ── Live stat update ──────────────────────────────────────────
            # Emitted by automation.py after every record finishes.
            _rec_result = msg[len("__RECORD_DONE__"):].strip()
            if _rec_result == "success":
                st.session_state.live_success += 1
            elif _rec_result == "failed":
                st.session_state.live_failed  += 1
            elif _rec_result == "skipped":
                st.session_state.live_skipped += 1

        elif msg.startswith("__DONE__"):
            st.session_state.running = False
            st.session_state.done    = True

        elif msg.startswith("__RESULTS__"):
            try:
                st.session_state.result_records = json.loads(msg[len("__RESULTS__"):])
            except Exception:
                pass

        elif msg.startswith("__PDF__"):
            pdf_path = msg[len("__PDF__"):]
            if pdf_path and pdf_path not in st.session_state.pdf_files:
                st.session_state.pdf_files.append(pdf_path)

        else:
            st.session_state.log_lines.append(msg)

# ─────────────────────────────────────────────────────────────────────────────
#  Header
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="hdr">
  <div>
    <div class="hdr-title">🚛 Transit Pass Automation</div>
    <div class="hdr-sub">Telangana Dept. of Mines &amp; Geology — EPermit Transit Pass Auto-Generation</div>
  </div>
  <div class="hdr-badge">🤖 Powered by Playwright</div>
</div>
""", unsafe_allow_html=True)

# Steps indicator
r = st.session_state
_s = lambda active, done: "done" if done else ("act" if active else "step")
st.markdown(f"""
<div class="steps">
  <div class="{_s(True, bool(r.records))} step">① Upload Excel</div>
  <div class="{_s(bool(r.records), r.running or r.done)} step">② Credentials</div>
  <div class="{_s(r.running, False)} step">③ Running</div>
  <div class="{_s(False, r.done)} step">④ Done</div>
</div>
""", unsafe_allow_html=True)

# (OTP input is now a fixed section inside Step 3 — see below)

# ─────────────────────────────────────────────────────────────────────────────
#  Main layout
# ─────────────────────────────────────────────────────────────────────────────

col_l, col_r = st.columns([1, 1], gap="large")

# ═══════════════════════════════════════
#  LEFT — Controls
# ═══════════════════════════════════════

with col_l:

    # ── Step 1: Upload ──────────────────────────────────────
    st.markdown('<div class="card"><div class="card-title">📂 Step 1 — Upload Excel File</div>', unsafe_allow_html=True)

    uploaded = st.file_uploader(
        "Excel file", type=["xlsx", "xls"],
        key="uploader", label_visibility="collapsed"
    )
    if uploaded:
        save_path = Path("uploaded_royalty.xlsx")
        save_path.write_bytes(uploaded.read())
        st.session_state.uploaded_path = str(save_path)
        records, warnings = load_records(str(save_path))
        st.session_state.records = records
        if records:
            st.success(f"✅ Loaded **{len(records)} records** from '{uploaded.name}'")
        for w in warnings:
            if w.startswith("ℹ"):
                st.info(w)
            else:
                st.warning(w)

    st.markdown('</div>', unsafe_allow_html=True)

    # ── Step 2: Credentials ─────────────────────────────────
    st.markdown('<div class="card"><div class="card-title">🔑 Step 2 — Login Credentials</div>', unsafe_allow_html=True)

    username = st.text_input("Username", placeholder="EPermit username", key="username")
    password = st.text_input("Password", placeholder="EPermit password",
                             type="password", key="password")
    mode = st.selectbox("Automation Type", ["MDL", "TP"], index=0, key="mode")

    c1, c2 = st.columns(2)
    with c1:
        headless = st.toggle("🕶️ Headless", value=False,
                             help="ON = browser invisible  OFF = see browser")
    with c2:
        delay = st.number_input("⏱️ Delay (sec)", 1, 30, 3,
                                help="Wait between records")

    # PDF save folder (editable, defaults to Desktop/TransitPass_PDFs)
    pdf_folder_input = st.text_input(
        "📁 PDF Save Folder",
        value=st.session_state.pdf_folder,
        help="Folder where royalty PDFs are saved. Created automatically if it does not exist.",
        key="pdf_folder_input",
    )
    if pdf_folder_input.strip():
        st.session_state.pdf_folder = pdf_folder_input.strip()
    st.caption(f"PDFs will be saved to: `{st.session_state.pdf_folder}`")

    st.markdown('</div>', unsafe_allow_html=True)

    # ── Preview ────────────────────────────────────────────────
    if st.session_state.records:
        recs = st.session_state.records
        st.markdown(
            f'<div class="card"><div class="card-title">👁️ Preview — {len(recs)} Records</div>',
            unsafe_allow_html=True
        )
        st.dataframe(records_to_dataframe(recs), use_container_width=True, height=220)
        r0 = recs[0]
        st.info(
            f"✏️ CONSIGNEE INFO per row — "
            f"Dispatch Qty: {r0.get('dispatch_qty','?')} | "
            f"Sale Value: {r0.get('sales_value','?')} | "
            f"Stationery No: {r0.get('stationary_no','?')} (each row gets its own)"
        )
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Step 3: Controls ────────────────────────────────────
    st.markdown('<div class="card"><div class="card-title">▶️ Step 3 — Run Automation</div>', unsafe_allow_html=True)

    btn1, btn2 = st.columns(2)
    can_start = (bool(st.session_state.records)
                 and bool(username) and bool(password)
                 and not st.session_state.running)

    with btn1:
        if st.button("🚀 Start Automation", disabled=not can_start,
                     use_container_width=True, type="primary", key="btn_start"):

            st.session_state.running        = True
            st.session_state.done           = False
            st.session_state.log_lines      = []
            st.session_state.progress_done  = 0
            st.session_state.progress_total = len(st.session_state.records)
            st.session_state.otp_requested  = False
            st.session_state.otp_submitted  = False
            st.session_state.result_records = []
            st.session_state.pdf_files      = []
            # ── Reset live counters for a fresh run
            st.session_state.live_success   = 0
            st.session_state.live_failed    = 0
            st.session_state.live_skipped   = 0
            st.session_state.live_current   = ""

            while not st.session_state.log_q.empty():
                try: st.session_state.log_q.get_nowait()
                except: break
            while not st.session_state.otp_resp_q.empty():
                try: st.session_state.otp_resp_q.get_nowait()
                except: break

            config.DELAY_BETWEEN_RECORDS = float(delay)

            _log_q      = st.session_state.log_q
            _otp_resp_q = st.session_state.otp_resp_q
            _records    = [dict(r) for r in st.session_state.records]
            _username   = str(username)
            _password   = str(password)
            _headless   = bool(headless)
            _pdf_folder = str(st.session_state.pdf_folder)
            _mode       = str(mode)

            def _run():
                _log_q.put("🚀 Automation thread started…")
                _log_q.put(f"👤 Username: {_username}")
                _log_q.put(f"📋 Records to process: {len(_records)}")

                try:
                    _log_q.put("📦 Loading automation engine…")
                    import importlib
                    import config
                    import automation
                    importlib.reload(config)
                    importlib.reload(automation)
                    from automation import run_batch
                    _log_q.put("✅ Engine loaded. Launching browser…")
                except Exception as imp_err:
                    _log_q.put(f"❌ Import failed: {imp_err}")
                    _log_q.put("__DONE__0")
                    return

                def log_fn(msg: str):
                    _log_q.put(msg)

                def otp_fn() -> str:
                    try:
                        return _otp_resp_q.get(timeout=config.OTP_WAIT_TIMEOUT)
                    except queue.Empty:
                        return ""

                def progress_fn(done: int, total: int):
                    _log_q.put(f"__PROGRESS__{done}__{total}")

                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                try:
                    results = loop.run_until_complete(
                        run_batch(
                            records     = _records,
                            username    = _username,
                            password    = _password,
                            log_fn      = log_fn,
                            otp_fn      = otp_fn,
                            progress_fn = progress_fn,
                            headless    = _headless,
                            pdf_folder  = _pdf_folder,
                            mode        = _mode,
                        )
                    )
                    try:
                        _log_q.put("__RESULTS__" + json.dumps(results, default=str))
                    except Exception:
                        pass
                except Exception as ex:
                    import traceback
                    _log_q.put(f"💥 Fatal error: {ex}")
                    _log_q.put(traceback.format_exc())
                finally:
                    loop.close()
                    _log_q.put("__DONE__0")

            t = threading.Thread(target=_run, daemon=True, name="automation")
            t.start()
            st.rerun()

    with btn2:
        if st.button("⏹️ Stop", disabled=not st.session_state.running,
                     use_container_width=True, key="btn_stop"):
            st.session_state.running = False
            st.session_state.log_lines.append("⏹️  Stop requested by user.")

    # ── Fixed OTP Entry (always visible below Start/Stop) ────────────────────
    _otp_needed = (st.session_state.running
                   and st.session_state.otp_requested
                   and not st.session_state.otp_submitted)

    _otp_css = "otp-active" if _otp_needed else "otp-idle"

    if _otp_needed:
        st.markdown(
            '<div class="otp-section otp-active">'
            '<div class="otp-label-active">📲 OTP Required — Enter Here!</div>'
            '<div class="otp-hint">An OTP has been sent to your mobile. '
            'Enter it below and click <strong>Submit OTP</strong> to continue.</div>'
            '</div>',
            unsafe_allow_html=True,
        )
    else:
        _status_txt = (
            "✅ OTP submitted — automation continuing…" if st.session_state.otp_submitted
            else "Waiting for automation to reach OTP step…"
        )
        st.markdown(
            f'<div class="otp-section otp-idle">'
            f'<div class="otp-label-idle">🔢 Step 3b — Enter OTP Here</div>'
            f'<div style="color:#475569;font-size:.8rem">{_status_txt}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

    otp_col1, otp_col2 = st.columns([2, 1])
    with otp_col1:
        otp_val = st.text_input(
            "OTP",
            max_chars=8,
            placeholder="Enter OTP here" if _otp_needed else "OTP field (ready)",
            key="otp_field",
            label_visibility="collapsed",
            disabled=not _otp_needed,
        )
    with otp_col2:
        if st.button(
            "✅ Submit OTP",
            use_container_width=True,
            type="primary" if _otp_needed else "secondary",
            key="otp_btn",
            disabled=not _otp_needed,
        ):
            if otp_val and otp_val.strip():
                st.session_state.otp_resp_q.put(otp_val.strip())
                st.session_state.otp_submitted = True
                st.toast("✅ OTP submitted! Automation resuming…", icon="✅")
                st.rerun()
            else:
                st.error("Please enter the OTP before submitting.")

    st.markdown('</div>', unsafe_allow_html=True)

    # ── PDF Downloads (per Transit Pass) ────────────────────
    if st.session_state.pdf_files:
        st.markdown(
            f'<div class="card"><div class="card-title">📄 Generated Transit Pass PDFs — {len(st.session_state.pdf_files)} file(s)</div>',
            unsafe_allow_html=True
        )
        for pdf_path_str in st.session_state.pdf_files:
            pdf_p = Path(pdf_path_str)
            if pdf_p.exists():
                with open(str(pdf_p), "rb") as f:
                    pdf_bytes = f.read()
                st.download_button(
                    label=f"⬇️  {pdf_p.name}",
                    data=pdf_bytes,
                    file_name=pdf_p.name,
                    mime="application/pdf",
                    use_container_width=True,
                    key=f"pdf_dl_{pdf_p.stem}",
                )
            else:
                st.warning(f"PDF not found: {pdf_path_str}")
        st.markdown('</div>', unsafe_allow_html=True)

    # ── Download Result Excel ────────────────────────────────
    if st.session_state.done and st.session_state.result_records:
        st.markdown('<div class="card"><div class="card-title">📥 Download Results</div>', unsafe_allow_html=True)
        out = "royalty_result.xlsx"
        if st.session_state.uploaded_path:
            try:
                add_status_column(st.session_state.result_records,
                                  st.session_state.uploaded_path, out)
                with open(out, "rb") as f:
                    st.download_button(
                        "⬇️ Download Result Excel", f.read(),
                        file_name=f"transit_result_{datetime.now():%Y%m%d_%H%M%S}.xlsx",
                        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        use_container_width=True,
                    )
            except Exception as e:
                st.error(f"Could not generate result file: {e}")
        st.markdown('</div>', unsafe_allow_html=True)


# ═══════════════════════════════════════
#  RIGHT — Stats + Log
# ═══════════════════════════════════════

with col_r:

    # ── Stat boxes — live during run, final counts when done ───────────────────
    total = len(st.session_state.records)

    if st.session_state.running:
        # Use live counters updated per-record in real-time
        success = st.session_state.live_success
        failed  = st.session_state.live_failed
        skipped = st.session_state.live_skipped
        processed = success + failed + skipped
        pending = total - processed
    else:
        # Use final result_records when done (or 0 before run starts)
        success = sum(1 for r in st.session_state.result_records if "✅" in r.get("_status", ""))
        failed  = sum(1 for r in st.session_state.result_records if "❌" in r.get("_status", ""))
        skipped = sum(1 for r in st.session_state.result_records if "⏭️" in r.get("_status", ""))
        pending = max(0, total - success - failed - skipped)

    # Current record label (shown inside Pending box while running)
    _cur = st.session_state.progress_done
    _cur_label = (
        f"<div style='font-size:.68rem;color:#94a3b8;margin-top:4px'>Record {_cur+1}/{total}</div>"
        if st.session_state.running and total > 0 else ""
    )

    st.markdown(f"""
    <div class="sg">
      <div class="sb"><div class="sn c-blue">{total}</div><div class="sl">Total</div></div>
      <div class="sb"><div class="sn c-green">{success}</div><div class="sl">✅ Success</div></div>
      <div class="sb"><div class="sn c-red">{failed}</div><div class="sl">❌ Failed</div></div>
      <div class="sb"><div class="sn c-yellow">{pending}</div><div class="sl">⏳ Pending</div>{_cur_label}</div>
    </div>
    """, unsafe_allow_html=True)

    if st.session_state.running or st.session_state.done:
        prog = st.session_state.progress_done / max(st.session_state.progress_total, 1)
        st.progress(prog,
            text=f"{'Running…' if st.session_state.running else 'Complete!'} "
                 f"{st.session_state.progress_done}/{st.session_state.progress_total} records")

    # Live log
    st.markdown('<div class="card"><div class="card-title">📋 Live Automation Log</div>', unsafe_allow_html=True)

    def _cls(line: str) -> str:
        l = line.lower()
        if "✅" in line or "success" in l or "saved" in l: return "ok"
        if "❌" in line or "error" in l or "fail" in l:    return "err"
        if "⚠️" in line or "warn" in l:                    return "warn"
        return "info"

    log_html = "\n".join(
        f'<div class="{_cls(l)}">{l}</div>'
        for l in st.session_state.log_lines[-250:]
    ) or '<div style="color:#475569">Waiting for automation to start…</div>'

    st.markdown(f'<div class="log-box">{log_html}</div>', unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)

    # Results table
    if st.session_state.result_records:
        st.markdown('<div class="card"><div class="card-title">📊 Results Summary</div>', unsafe_allow_html=True)
        df_res = records_to_dataframe(st.session_state.result_records)
        df_res["Status"] = [r.get("_status", "") for r in st.session_state.result_records]
        st.dataframe(df_res, use_container_width=True, height=260)
        st.markdown('</div>', unsafe_allow_html=True)

    # Error screenshots gallery
    ss_dir = Path("screenshots")
    if ss_dir.exists():
        shots = sorted(ss_dir.glob("*.png"), key=os.path.getmtime, reverse=True)[:6]
        if shots:
            st.markdown('<div class="card"><div class="card-title">📸 Debug Screenshots</div>', unsafe_allow_html=True)
            ic = st.columns(2)
            for i, p in enumerate(shots):
                with ic[i % 2]:
                    st.image(str(p), caption=p.stem, use_container_width=True)
            st.markdown('</div>', unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
#  Auto-refresh
# ─────────────────────────────────────────────────────────────────────────────

if st.session_state.running:
    if st.session_state.otp_requested and not st.session_state.otp_submitted:
        time.sleep(0.5)
    else:
        time.sleep(1.2)
    st.rerun()
