"""
Islamic Stock Screener — Streamlit Web App
AAOIFI Standard No. 21 + Damodaran DCF Valuation
"""

import streamlit as st
import json, datetime, io, time
import pandas as pd

from screener      import screen_ticker, SECTOR_TICKERS
from excel_export  import build_excel
from drive         import (get_drive_service, ensure_folder_structure,
                           get_damodaran_files_status, get_musaffa_pdfs,
                           get_valuation_templates, get_watchlist_files,
                           download_file_bytes, save_output, upload_to_folder,
                           list_files_in_folder)
from pdf_reader    import (parse_musaffa_pdf, extract_damodaran_context,
                           load_damodaran_sector_benchmarks)

st.set_page_config(
    page_title="Islamic Stock Screener",
    page_icon="🌙",
    layout="wide",
    initial_sidebar_state="expanded",
)

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=DM+Sans:wght@300;400;500;600&display=swap');

html, body, [class*="css"] { font-family: 'DM Sans', sans-serif; }

.main-header {
    background: linear-gradient(135deg, #1B3A5C 0%, #2D5A8E 100%);
    color: white; padding: 1.5rem 2rem; border-radius: 12px;
    margin-bottom: 1.5rem; display: flex; align-items: center; gap: 1rem;
}
.main-header h1 { margin: 0; font-size: 22px; font-weight: 600; color: white; }
.main-header p  { margin: 0; font-size: 13px; opacity: 0.8; color: white; }

.stat-card {
    background: white; border: 0.5px solid #E5E7EB;
    border-radius: 10px; padding: 1rem 1.25rem; text-align: center;
}
.stat-card .num { font-size: 28px; font-weight: 600; color: #1B3A5C; }
.stat-card .lbl { font-size: 12px; color: #6B7280; margin-top: 2px; }
.stat-card .num.green { color: #1E6B3C; }
.stat-card .num.amber { color: #7A5200; }
.stat-card .num.red   { color: #9B1C1C; }

.badge-halal  { background:#E6F4EA; color:#1E6B3C; padding:3px 10px;
                border-radius:20px; font-size:12px; font-weight:500; }
.badge-purify { background:#FFF8E1; color:#7A5200; padding:3px 10px;
                border-radius:20px; font-size:12px; font-weight:500; }
.badge-haram  { background:#FDECEA; color:#9B1C1C; padding:3px 10px;
                border-radius:20px; font-size:12px; font-weight:500; }
.badge-buy    { background:#E6F4EA; color:#1E6B3C; padding:3px 10px;
                border-radius:20px; font-size:12px; font-weight:500; }
.badge-hold   { background:#FFF8E1; color:#7A5200; padding:3px 10px;
                border-radius:20px; font-size:12px; font-weight:500; }
.badge-avoid  { background:#FDECEA; color:#9B1C1C; padding:3px 10px;
                border-radius:20px; font-size:12px; font-weight:500; }

.file-status-ok   { color: #1E6B3C; font-size: 13px; }
.file-status-miss { color: #9B1C1C; font-size: 13px; }

.log-entry { font-family: monospace; font-size: 12px; padding: 4px 0;
             border-bottom: 0.5px solid #F3F4F6; }

[data-testid="stSidebar"] { background: #F8FAFC; }
.stButton > button {
    border-radius: 8px; font-family: 'DM Sans', sans-serif;
    font-weight: 500;
}
div[data-testid="stMetricValue"] { font-size: 28px; }
</style>
""", unsafe_allow_html=True)


# ── Session state initialisation ──────────────────────────────────────────────
def init_state():
    defaults = {
        "results": [],
        "run_config": {},
        "drive_service": None,
        "folder_ids": None,
        "musaffa_data": {},
        "damodaran_context": None,
        "sector_benchmarks": {},
        "credentials_loaded": False,
        "last_run_stats": {},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_state()


# ── Credential helpers ────────────────────────────────────────────────────────
def get_fmp_key():
    try:
        return st.secrets["FMP_API_KEY"]
    except Exception:
        return st.session_state.get("fmp_key_input", "")

def get_anthropic_key():
    try:
        return st.secrets["ANTHROPIC_API_KEY"]
    except Exception:
        return st.session_state.get("anthropic_key_input", "")

def get_credentials_json():
    try:
        raw = st.secrets["GOOGLE_CREDENTIALS"]
        return json.loads(raw) if isinstance(raw, str) else dict(raw)
    except Exception:
        return None

def connect_drive():
    creds = get_credentials_json()
    if not creds:
        return False
    try:
        svc = get_drive_service(creds)
        root_folder_id = st.secrets.get("GOOGLE_DRIVE_ROOT_FOLDER_ID", None)
        fids = ensure_folder_structure(svc, root_folder_id)
        st.session_state["drive_service"] = svc
        st.session_state["folder_ids"]    = fids
        st.session_state["credentials_loaded"] = True
        return True
    except Exception as e:
        st.error(f"Google Drive connection failed: {e}")
        return False

# ── Load training data from Drive ─────────────────────────────────────────────
def load_drive_training_data():
    svc  = st.session_state.get("drive_service")
    fids = st.session_state.get("folder_ids")
    if not svc or not fids:
        return

    # Load Musaffa PDFs
    musaffa_combined = {}
    pdfs = get_musaffa_pdfs(svc, fids)
    for pdf_file in pdfs:
        try:
            pdf_bytes = download_file_bytes(svc, pdf_file["id"])
            extracted = parse_musaffa_pdf(pdf_bytes, get_anthropic_key())
            musaffa_combined.update(extracted)
        except Exception:
            pass
    st.session_state["musaffa_data"] = musaffa_combined

    # Load Damodaran valuation template context
    templates = get_valuation_templates(svc, fids)
    if templates:
        try:
            xl_bytes = download_file_bytes(svc, templates[0]["id"])
            st.session_state["damodaran_context"] = extract_damodaran_context(xl_bytes)
        except Exception:
            pass

    # Load Damodaran sector benchmarks
    damodaran_status = get_damodaran_files_status(svc, fids)
    excel_bytes_map  = {}
    for fname, info in damodaran_status.items():
        if info["uploaded"]:
            try:
                excel_bytes_map[fname] = download_file_bytes(svc, info["id"])
            except Exception:
                pass
    if excel_bytes_map:
        st.session_state["sector_benchmarks"] = load_damodaran_sector_benchmarks(excel_bytes_map)


# ── Sidebar ───────────────────────────────────────────────────────────────────
def render_sidebar():
    with st.sidebar:
        st.markdown("### 🌙 Islamic Screener")
        st.markdown("---")

        page = st.radio(
            "Navigate",
            ["Dashboard", "Ticker Search", "Data Files", "New Run"],
            label_visibility="collapsed",
        )

        st.markdown("---")
        st.markdown("**API Status**")

        fmp = get_fmp_key()
        ant = get_anthropic_key()
        drv = st.session_state.get("credentials_loaded")

        st.markdown(f"{'✅' if fmp else '❌'} FMP API")
        st.markdown(f"{'✅' if ant else '❌'} Anthropic API")
        st.markdown(f"{'✅' if drv else '❌'} Google Drive")

        if not drv:
            if st.button("Connect Google Drive", use_container_width=True):
                with st.spinner("Connecting…"):
                    if connect_drive():
                        load_drive_training_data()
                        st.success("Connected!")
                        st.rerun()

        st.markdown("---")
        if st.session_state.get("last_run_stats"):
            s = st.session_state["last_run_stats"]
            st.markdown("**Last run**")
            st.markdown(f"📅 {s.get('date','—')}")
            st.markdown(f"🔍 {s.get('total',0)} screened")
            st.markdown(f"✅ {s.get('halal',0)} HALAL · 🔶 {s.get('purify',0)} PURIFY")
            st.markdown(f"📈 {s.get('buy',0)} BUY signals")

        st.markdown("---")
        if not st.secrets.get("FMP_API_KEY"):
            with st.expander("🔑 Enter API keys manually"):
                st.text_input("FMP API Key",       type="password", key="fmp_key_input")
                st.text_input("Anthropic API Key", type="password", key="anthropic_key_input")

    return page


# ══════════════════════════════════════════════════════════════════════════════
# PAGES
# ══════════════════════════════════════════════════════════════════════════════

def page_dashboard():
    st.markdown("""
    <div class="main-header">
      <div style="font-size:36px">🌙</div>
      <div>
        <h1>Islamic Stock Screener</h1>
        <p>AAOIFI Standard No. 21 · Damodaran DCF Valuation · US Equities</p>
      </div>
    </div>
    """, unsafe_allow_html=True)

    results = st.session_state.get("results", [])

    if not results:
        st.info("No run completed yet. Go to **New Run** to screen stocks.")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.markdown("""<div class="stat-card">
                <div class="num">—</div><div class="lbl">Stocks screened</div>
            </div>""", unsafe_allow_html=True)
        with c2:
            st.markdown("""<div class="stat-card">
                <div class="num">—</div><div class="lbl">HALAL / PURIFY</div>
            </div>""", unsafe_allow_html=True)
        with c3:
            st.markdown("""<div class="stat-card">
                <div class="num">—</div><div class="lbl">BUY signals</div>
            </div>""", unsafe_allow_html=True)
        return

    halal_n  = sum(1 for r in results if r.get("shariah_status") == "HALAL")
    purify_n = sum(1 for r in results if r.get("shariah_status") == "PURIFY")
    haram_n  = sum(1 for r in results if r.get("shariah_status") == "HARAM")
    buy_n    = sum(1 for r in results if r.get("verdict") == "BUY")
    hold_n   = sum(1 for r in results if r.get("verdict") == "HOLD")

    mos_vals = [r.get("margin_of_safety") for r in results
                if r.get("margin_of_safety") is not None
                and r.get("shariah_status") in ("HALAL","PURIFY")]
    avg_mos  = (sum(mos_vals) / len(mos_vals)) if mos_vals else None

    c1, c2, c3, c4, c5 = st.columns(5)
    with c1:
        st.markdown(f"""<div class="stat-card">
            <div class="num">{len(results)}</div><div class="lbl">Screened</div>
        </div>""", unsafe_allow_html=True)
    with c2:
        st.markdown(f"""<div class="stat-card">
            <div class="num green">{halal_n}</div><div class="lbl">HALAL</div>
        </div>""", unsafe_allow_html=True)
    with c3:
        st.markdown(f"""<div class="stat-card">
            <div class="num amber">{purify_n}</div><div class="lbl">PURIFY</div>
        </div>""", unsafe_allow_html=True)
    with c4:
        st.markdown(f"""<div class="stat-card">
            <div class="num green">{buy_n}</div><div class="lbl">BUY signals</div>
        </div>""", unsafe_allow_html=True)
    with c5:
        mos_display = f"{avg_mos:+.1f}%" if avg_mos is not None else "—"
        st.markdown(f"""<div class="stat-card">
            <div class="num">{mos_display}</div><div class="lbl">Avg MoS (halal)</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("### Results")
    _render_results_table(results)


def _render_results_table(results, key_suffix="main"):
    if not results:
        return

    fc1, fc2, fc3, fc4 = st.columns([2, 1, 1, 1])
    with fc1:
        search = st.text_input("🔍 Search ticker or company", key=f"search_{key_suffix}", placeholder="e.g. AAPL, Apple")
    with fc2:
        sh_filter = st.selectbox("Shariah", ["All","HALAL","PURIFY","HARAM"], key=f"sh_{key_suffix}")
    with fc3:
        vd_filter = st.selectbox("Verdict",  ["All","BUY","HOLD","AVOID"], key=f"vd_{key_suffix}")
    with fc4:
        sc_filter = st.selectbox("Sector", ["All"] + sorted(set(r.get("sector","") for r in results if r.get("sector"))), key=f"sc_{key_suffix}")

    filtered = results
    if search:
        s = search.upper()
        filtered = [r for r in filtered if s in r.get("ticker","").upper() or s in r.get("company","").upper()]
    if sh_filter != "All":
        filtered = [r for r in filtered if r.get("shariah_status") == sh_filter]
    if vd_filter != "All":
        filtered = [r for r in filtered if r.get("verdict") == vd_filter]
    if sc_filter != "All":
        filtered = [r for r in filtered if r.get("sector") == sc_filter]

    st.caption(f"Showing {len(filtered)} of {len(results)} stocks")

    def badge(status, kind="shariah"):
        if kind == "shariah":
            m = {"HALAL":"halal","PURIFY":"purify","HARAM":"haram"}
        else:
            m = {"BUY":"buy","HOLD":"hold","AVOID":"avoid"}
        cls = m.get(status, "")
        icons = {"HALAL":"✅","PURIFY":"🔶","HARAM":"❌","BUY":"📈","HOLD":"⏸","AVOID":"🚫"}
        return f"{icons.get(status,'')} {status}"

    def fmt_pct(v):
        try:
            return f"{float(v):+.1f}%" if v is not None else "—"
        except Exception:
            return "—"

    def fmt_price(v):
        try:
            return f"${float(v):.2f}" if v is not None else "—"
        except Exception:
            return "—"

    table_data = []
    for r in filtered:
        table_data.append({
            "Ticker":          r.get("ticker",""),
            "Company":         r.get("company",""),
            "Sector":          r.get("sector",""),
            "Shariah":         badge(r.get("shariah_status",""), "shariah"),
            "Price":           fmt_price(r.get("current_price")),
            "52W High":        fmt_price(r.get("week52_high")),
            "52W Low":         fmt_price(r.get("week52_low")),
            "Intrinsic Value": fmt_price(r.get("intrinsic_value")),
            "MoS":             fmt_pct(r.get("margin_of_safety")),
            "Rel.Val.":        r.get("relative_assessment","—"),
            "Verdict":         badge(r.get("verdict",""), "verdict"),
            "Purify %":        f"{r.get('purification_pct'):.2f}%" if r.get("purification_pct") else "—",
        })

    if table_data:
        df = pd.DataFrame(table_data)
        st.dataframe(df, use_container_width=True, hide_index=True, height=420)

    run_mode     = st.session_state.get("run_config", {}).get("run_mode", "both")
    output_filter= st.session_state.get("run_config", {}).get("output_filter", "all")
    cfg          = st.session_state.get("run_config", {})

    col_dl, col_drive, _ = st.columns([1, 1, 3])
    with col_dl:
        if st.button("📥 Export to Excel", key=f"dl_{key_suffix}", use_container_width=True):
            excel_bytes = build_excel(filtered, cfg, output_filter, run_mode)
            fname = f"islamic_screener_{datetime.date.today()}.xlsx"
            st.download_button(
                "⬇️ Download Excel",
                data=excel_bytes,
                file_name=fname,
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key=f"dl_btn_{key_suffix}",
            )
    with col_drive:
        svc  = st.session_state.get("drive_service")
        fids = st.session_state.get("folder_ids")
        if svc and fids:
            if st.button("☁️ Save to Drive", key=f"drive_{key_suffix}", use_container_width=True):
                with st.spinner("Saving to Google Drive…"):
                    excel_bytes = build_excel(filtered, cfg, output_filter, run_mode)
                    fname = f"islamic_screener_{datetime.date.today()}.xlsx"
                    save_output(svc, fids, fname, excel_bytes)
                st.success(f"Saved to Drive → 5_Outputs/{fname}")


def page_ticker_search():
    st.markdown("## 🔍 Ticker Search")
    st.caption("Instant full analysis for any US stock ticker")

    col1, col2, col3 = st.columns([2, 1, 1])
    with col1:
        ticker_input = st.text_input("Enter ticker", placeholder="e.g. NVDA", label_visibility="collapsed").upper().strip()
    with col2:
        mode = st.selectbox("Mode", ["Both", "Compliance Only", "Valuation Only"], label_visibility="collapsed")
    with col3:
        run_search = st.button("▶ Analyze", use_container_width=True, type="primary")

    mode_map = {"Both": "both", "Compliance Only": "compliance", "Valuation Only": "valuation"}

    if run_search and ticker_input:
        fmp_key = get_fmp_key()
        ant_key = get_anthropic_key()

        if not fmp_key:
            st.error("FMP API key not configured. Add it in the sidebar or Streamlit secrets.")
            return

        with st.spinner(f"Analyzing {ticker_input}…"):
            result = screen_ticker(
                ticker_input, fmp_key, ant_key,
                run_mode=mode_map[mode],
                musaffa_data=st.session_state.get("musaffa_data", {}),
                sector_benchmarks=st.session_state.get("sector_benchmarks", {}),
                damodaran_context=st.session_state.get("damodaran_context"),
            )

        _render_single_result(result, mode_map[mode])

    elif run_search and not ticker_input:
        st.warning("Please enter a ticker symbol.")


def _render_single_result(r, run_mode):
    if r.get("error"):
        st.error(f"Could not fetch data for {r.get('ticker')}: {r.get('error')}")
        return

    status  = r.get("shariah_status","—")
    verdict = r.get("verdict","—")

    status_icons  = {"HALAL":"✅","PURIFY":"🔶","HARAM":"❌"}
    verdict_icons = {"BUY":"📈","HOLD":"⏸","AVOID":"🚫"}

    st.markdown(f"""
    ### {r.get('ticker')} — {r.get('company','')}
    **{r.get('sector','')}** · {r.get('industry','')}
    """)

    col1, col2 = st.columns(2)
    with col1:
        st.markdown(f"**Shariah Status:** {status_icons.get(status,'')} {status}")
        if r.get("shariah_source"):
            st.caption(f"Source: {r.get('shariah_source')}")
    with col2:
        st.markdown(f"**Verdict:** {verdict_icons.get(verdict,'')} {verdict}")
        if r.get("rationale"):
            st.caption(r.get("rationale"))

    m1, m2, m3, m4 = st.columns(4)
    with m1:
        v = r.get("current_price")
        st.metric("Current Price", f"${v:.2f}" if v else "—")
    with m2:
        v = r.get("intrinsic_value")
        st.metric("Intrinsic Value", f"${v:.2f}" if v else "—")
    with m3:
        v = r.get("margin_of_safety")
        st.metric("Margin of Safety", f"{v:+.1f}%" if v is not None else "—")
    with m4:
        h = r.get("week52_high"); l = r.get("week52_low")
        st.metric("52W Range", f"${l:.0f}–${h:.0f}" if h and l else "—")

    if run_mode in ("compliance","both"):
        st.markdown("#### Shariah Screening — AAOIFI Standard No. 21")
        c1, c2, c3 = st.columns(3)
        checks = [
            ("Debt / MktCap", r.get("debt_ratio"), 0.30),
            ("Cash / MktCap", r.get("cash_ratio"),  0.30),
            ("Impure Income", r.get("impure_income_ratio"), 0.05),
        ]
        for col, (label, val, threshold) in zip([c1,c2,c3], checks):
            with col:
                if val is not None:
                    icon = "✅" if val < threshold else "❌"
                    st.metric(label, f"{val:.1%}", delta=f"Limit: {threshold:.0%}")
                else:
                    st.metric(label, "—")

        if r.get("fail_reason"):
            st.error(f"Failed: {r.get('fail_reason')}")

        if status == "PURIFY" and r.get("purification_pct"):
            st.warning(f"🔶 Purification required: donate **{r.get('purification_pct'):.2f}%** of any dividend received to charity.")

    if run_mode in ("valuation","both"):
        st.markdown("#### Damodaran Valuation")
        vc1, vc2, vc3, vc4 = st.columns(4)
        with vc1:
            v = r.get("wacc")
            st.metric("WACC", f"{v:.1f}%" if v else "—")
        with vc2:
            v = r.get("terminal_growth")
            st.metric("Terminal Growth", f"{v:.1f}%" if v else "—")
        with vc3:
            pe  = r.get("pe_company"); pes = r.get("pe_sector")
            st.metric("P/E", f"{pe:.1f}x" if pe else "—",
                      delta=f"Sector: {pes:.1f}x" if pes else None)
        with vc4:
            ev  = r.get("ev_ebitda_company"); evs = r.get("ev_ebitda_sector")
            st.metric("EV/EBITDA", f"{ev:.1f}x" if ev else "—",
                      delta=f"Sector: {evs:.1f}x" if evs else None)

    with st.expander("Add to watchlist"):
        if st.button(f"Save {r.get('ticker')} to watchlist"):
            svc  = st.session_state.get("drive_service")
            fids = st.session_state.get("folder_ids")
            if svc and fids:
                csv_content = f"{r.get('ticker')}\n".encode()
                upload_to_folder(svc, fids, "watchlists",
                                 "my_watchlist.csv", csv_content, "text/csv")
                st.success("Added to watchlist in Google Drive.")
            else:
                st.info("Connect Google Drive to save watchlists.")


def page_data_files():
    st.markdown("## 📁 Data Files")

    svc  = st.session_state.get("drive_service")
    fids = st.session_state.get("folder_ids")

    if not svc or not fids:
        st.warning("Connect Google Drive first (use the sidebar button).")
        return

    tab1, tab2, tab3, tab4 = st.tabs([
        "📊 Damodaran Training",
        "📋 Valuation Templates",
        "🗂 Watchlists",
        "📄 Musaffa Reports",
    ])

    with tab1:
        st.markdown("Upload Damodaran's annual sector dataset files from `pages.stern.nyu.edu/~adamodar/`")
        st.caption("Refresh once a year (January). These improve WACC, P/E, and growth rate accuracy.")

        from drive import get_damodaran_files_status, DAMODARAN_FILES
        status = get_damodaran_files_status(svc, fids)

        for fname in DAMODARAN_FILES:
            col1, col2, col3 = st.columns([3, 2, 2])
            with col1:
                info = status[fname]
                if info["uploaded"]:
                    st.markdown(f"<span class='file-status-ok'>✅ {fname}</span>", unsafe_allow_html=True)
                    st.caption(f"Updated: {info['modified'][:10] if info['modified'] else 'unknown'}")
                else:
                    st.markdown(f"<span class='file-status-miss'>⚠️ {fname} — not uploaded</span>", unsafe_allow_html=True)
            with col2:
                up = st.file_uploader(f"Upload {fname}", key=f"up_{fname}", label_visibility="collapsed")
                if up:
                    upload_to_folder(svc, fids, "training", fname, up.read())
                    st.success(f"{fname} uploaded to Drive.")
                    st.rerun()

        if any(s["uploaded"] for s in status.values()):
            if st.button("🔄 Reload benchmarks from Drive"):
                from pdf_reader import load_damodaran_sector_benchmarks
                from drive import download_file_bytes
                excel_bytes_map = {}
                for fname, info in status.items():
                    if info["uploaded"]:
                        excel_bytes_map[fname] = download_file_bytes(svc, info["id"])
                st.session_state["sector_benchmarks"] = load_damodaran_sector_benchmarks(excel_bytes_map)
                st.success(f"Loaded benchmarks for {len(st.session_state['sector_benchmarks'])} sectors.")

    with tab2:
        st.markdown("Upload a complete Damodaran valuation Excel (e.g. his Apple or Tesla valuation).")
        st.caption("The agent reads this to understand his exact methodology and applies it to all valuations.")

        templates = get_valuation_templates(svc, fids)
        if templates:
            for t in templates:
                st.markdown(f"✅ **{t['name']}** — {t.get('modifiedTime','')[:10]}")
        else:
            st.info("No valuation template uploaded yet.")

        up_template = st.file_uploader("Upload Damodaran valuation Excel", type=["xlsx","xls"], key="up_template")
        if up_template:
            upload_to_folder(svc, fids, "templates", up_template.name, up_template.read())
            from pdf_reader import extract_damodaran_context
            up_template.seek(0)
            st.session_state["damodaran_context"] = extract_damodaran_context(up_template.read())
            st.success("Valuation template uploaded and loaded.")
            st.rerun()

    with tab3:
        st.markdown("Upload a CSV of tickers (one per line) or paste them below.")

        watchlists = get_watchlist_files(svc, fids)
        if watchlists:
            for w in watchlists:
                col1, col2 = st.columns([3, 1])
                with col1:
                    st.markdown(f"📋 **{w['name']}**")
                with col2:
                    if st.button("View", key=f"view_{w['id']}"):
                        content = download_file_bytes(svc, w["id"]).decode("utf-8", errors="ignore")
                        tickers = [t.strip().upper() for t in content.splitlines() if t.strip()]
                        st.write(f"{len(tickers)} tickers: {', '.join(tickers[:20])}{'...' if len(tickers)>20 else ''}")

        col1, col2 = st.columns(2)
        with col1:
            up_wl = st.file_uploader("Upload watchlist CSV", type=["csv"], key="up_watchlist")
            if up_wl:
                upload_to_folder(svc, fids, "watchlists", up_wl.name, up_wl.read(), "text/csv")
                st.success("Watchlist uploaded to Drive.")
                st.rerun()
        with col2:
            paste = st.text_area("Or paste tickers (one per line or comma-separated)", key="paste_tickers", height=120)
            if st.button("Save pasted watchlist"):
                if paste:
                    tickers = [t.strip().upper() for t in paste.replace(",","\n").splitlines() if t.strip()]
                    content = "\n".join(tickers).encode()
                    upload_to_folder(svc, fids, "watchlists", "my_watchlist.csv", content, "text/csv")
                    st.success(f"Saved {len(tickers)} tickers to Drive.")

    with tab4:
        st.markdown("Drop Musaffa compliance PDF reports here. The agent reads them and gives their verdicts priority over our AAOIFI calculations.")

        pdfs = get_musaffa_pdfs(svc, fids)
        if pdfs:
            st.success(f"{len(pdfs)} Musaffa PDF(s) loaded · {len(st.session_state.get('musaffa_data',{}))} tickers extracted")
            for p in pdfs:
                st.markdown(f"📄 {p['name']} — {p.get('modifiedTime','')[:10]}")
        else:
            st.info("No Musaffa PDFs uploaded yet.")

        up_pdf = st.file_uploader("Upload Musaffa PDF report", type=["pdf"], key="up_musaffa")
        if up_pdf:
            pdf_bytes = up_pdf.read()
            upload_to_folder(svc, fids, "musaffa", up_pdf.name, pdf_bytes, "application/pdf")
            ant_key = get_anthropic_key()
            if ant_key:
                with st.spinner("Extracting compliance data from PDF…"):
                    from pdf_reader import parse_musaffa_pdf
                    extracted = parse_musaffa_pdf(pdf_bytes, ant_key)
                    st.session_state["musaffa_data"].update(extracted)
                st.success(f"Uploaded and extracted {len(extracted)} tickers from PDF.")
            else:
                st.warning("Anthropic API key needed to extract PDF data. PDF saved to Drive.")
            st.rerun()

        if st.session_state.get("musaffa_data"):
            with st.expander("View extracted Musaffa verdicts"):
                md = st.session_state["musaffa_data"]
                df = pd.DataFrame(list(md.items()), columns=["Ticker","Musaffa Status"])
                st.dataframe(df, use_container_width=True, hide_index=True)


def page_new_run():
    st.markdown("## ▶ New Screening Run")

    fmp_key = get_fmp_key()
    ant_key = get_anthropic_key()

    if not fmp_key:
        st.error("FMP API key required. Add it in the sidebar.")
        return

    col_left, col_right = st.columns([2, 1])

    with col_left:
        st.markdown("#### Input source")
        input_source = st.radio("Source", ["Screen by sector", "Use custom watchlist"],
                                horizontal=True, label_visibility="collapsed")

        selected_tickers = []

        if input_source == "Screen by sector":
            st.markdown("**Select sectors:**")
            sector_cols = st.columns(2)
            selected_sectors = []
            for i, (sector, tickers) in enumerate(SECTOR_TICKERS.items()):
                with sector_cols[i % 2]:
                    if st.checkbox(f"{sector} ({len(tickers)} stocks)", key=f"sec_{sector}"):
                        selected_sectors.append(sector)
                        selected_tickers.extend(tickers)

            selected_tickers = list(dict.fromkeys(selected_tickers))

            if selected_tickers:
                fmp_calls = len(selected_tickers) * 6
                over_limit = fmp_calls > 240
                color = "red" if over_limit else "green"
                st.markdown(f"**{len(selected_tickers)} stocks selected · ~{fmp_calls} FMP calls**")
                if over_limit:
                    st.warning(f"⚠️ {fmp_calls} FMP calls exceeds free tier limit (~240/day). Upgrade to FMP Starter ($14/mo) for unlimited calls, or select fewer sectors.")

        else:
            svc  = st.session_state.get("drive_service")
            fids = st.session_state.get("folder_ids")
            watchlist_tickers = []

            if svc and fids:
                wls = get_watchlist_files(svc, fids)
                if wls:
                    selected_wl = st.selectbox("Select watchlist", [w["name"] for w in wls])
                    wl_file = next((w for w in wls if w["name"] == selected_wl), None)
                    if wl_file:
                        content = download_file_bytes(svc, wl_file["id"]).decode("utf-8", errors="ignore")
                        watchlist_tickers = [t.strip().upper() for t in content.replace(",","\n").splitlines() if t.strip()]
                        st.caption(f"{len(watchlist_tickers)} tickers loaded: {', '.join(watchlist_tickers[:10])}{'...' if len(watchlist_tickers)>10 else ''}")
                else:
                    st.info("No watchlists found. Upload one in Data Files → Watchlists.")
            else:
                st.info("Connect Google Drive to load saved watchlists.")

            paste = st.text_area("Or paste tickers here (comma or newline separated)", height=80, key="run_paste")
            if paste:
                extra = [t.strip().upper() for t in paste.replace(",","\n").splitlines() if t.strip()]
                watchlist_tickers = list(dict.fromkeys(watchlist_tickers + extra))

            selected_tickers = watchlist_tickers

    with col_right:
        st.markdown("#### Run mode")
        run_mode = st.radio("Mode", ["Both (recommended)", "Compliance Only", "Valuation Only"],
                            label_visibility="collapsed")
        mode_map = {"Both (recommended)": "both", "Compliance Only": "compliance", "Valuation Only": "valuation"}
        run_mode_val = mode_map[run_mode]

        st.markdown("#### Output filter")
        out_filter = st.radio("Filter", ["All stocks", "HALAL + PURIFY only", "BUY signals only", "BUY + HOLD"],
                              label_visibility="collapsed")
        filter_map = {
            "All stocks": "all",
            "HALAL + PURIFY only": "halal_only",
            "BUY signals only": "buy_only",
            "BUY + HOLD": "buy_hold",
        }
        out_filter_val = filter_map[out_filter]

        if run_mode_val in ("valuation","both") and not ant_key:
            st.warning("⚠️ Anthropic API key needed for valuation. Compliance screening will still run.")

        st.markdown("#### Estimated cost")
        if selected_tickers:
            n = len(selected_tickers)
            claude_cost = n * 0.004 if run_mode_val in ("valuation","both") else 0
            st.markdown(f"**{n} stocks**")
            st.markdown(f"FMP calls: ~{n*6 if run_mode_val != 'compliance' else n*3}")
            if claude_cost > 0:
                st.markdown(f"Claude API: ~${claude_cost:.2f}")
        else:
            st.markdown("Select stocks to see estimate")

    st.markdown("---")
    run_col, _ = st.columns([1, 3])
    with run_col:
        start = st.button("▶ Start Screening", type="primary",
                          disabled=len(selected_tickers) == 0,
                          use_container_width=True)

    if start and selected_tickers:
        _run_batch(selected_tickers, run_mode_val, out_filter_val)


def _run_batch(tickers, run_mode, output_filter):
    fmp_key = get_fmp_key()
    ant_key = get_anthropic_key()

    st.markdown("---")
    st.markdown(f"### Running — {len(tickers)} stocks")

    progress_bar  = st.progress(0)
    status_text   = st.empty()
    stats_display = st.empty()
    log_container = st.container()

    log_lines = []
    results   = []
    counts    = {"halal": 0, "purify": 0, "haram": 0, "buy": 0, "hold": 0, "avoid": 0}

    musaffa_data      = st.session_state.get("musaffa_data", {})
    sector_benchmarks = st.session_state.get("sector_benchmarks", {})
    damodaran_context = st.session_state.get("damodaran_context")

    for i, ticker in enumerate(tickers):
        pct = (i + 1) / len(tickers)
        progress_bar.progress(pct)
        status_text.markdown(f"**Processing {ticker}** ({i+1}/{len(tickers)})")

        result = screen_ticker(
            ticker, fmp_key, ant_key,
            run_mode=run_mode,
            musaffa_data=musaffa_data,
            sector_benchmarks=sector_benchmarks,
            damodaran_context=damodaran_context,
        )
        results.append(result)

        status  = result.get("shariah_status","—")
        verdict = result.get("verdict","—")
        mos     = result.get("margin_of_safety")
        mos_str = f"{mos:+.1f}%" if mos is not None else "—"

        if status == "HALAL":   counts["halal"]  += 1
        elif status == "PURIFY":counts["purify"] += 1
        elif status == "HARAM": counts["haram"]  += 1
        if verdict == "BUY":    counts["buy"]    += 1
        elif verdict == "HOLD": counts["hold"]   += 1
        elif verdict == "AVOID":counts["avoid"]  += 1

        s_icon = {"HALAL":"✅","PURIFY":"🔶","HARAM":"❌"}.get(status,"•")
        v_icon = {"BUY":"📈","HOLD":"⏸","AVOID":"🚫"}.get(verdict,"")
        log_line = f"{s_icon} **{ticker}** {result.get('company','')} — {status} → {v_icon} {verdict} · MoS: {mos_str}"
        log_lines.insert(0, log_line)

        stats_display.markdown(
            f"✅ HALAL: **{counts['halal']}** · "
            f"🔶 PURIFY: **{counts['purify']}** · "
            f"❌ HARAM: **{counts['haram']}** · "
            f"📈 BUY: **{counts['buy']}** · "
            f"⏸ HOLD: **{counts['hold']}**"
        )

        with log_container:
            st.markdown("\n\n".join(log_lines[:15]))

    progress_bar.progress(1.0)
    status_text.success(f"✅ Complete — {len(results)} stocks processed")

    run_config = {
        "run_date":      str(datetime.date.today()),
        "run_mode":      run_mode,
        "sectors":       "custom watchlist" if len(tickers) < 20 else "multiple sectors",
        "output_filter": output_filter,
        "total":         len(results),
        **counts,
    }

    st.session_state["results"]         = results
    st.session_state["run_config"]      = run_config
    st.session_state["last_run_stats"]  = {
        "date":   str(datetime.date.today()),
        "total":  len(results),
        "halal":  counts["halal"],
        "purify": counts["purify"],
        "buy":    counts["buy"],
    }

    st.markdown("---")
    st.markdown("### Results")
    _render_results_table(results, key_suffix="run")

    excel_bytes = build_excel(results, run_config, output_filter, run_mode)
    fname = f"islamic_screener_{datetime.date.today()}.xlsx"
    st.download_button(
        "⬇️ Download Excel Report",
        data=excel_bytes,
        file_name=fname,
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key="final_download",
    )

    svc  = st.session_state.get("drive_service")
    fids = st.session_state.get("folder_ids")
    if svc and fids:
        if st.button("☁️ Auto-save to Google Drive", key="auto_save"):
            save_output(svc, fids, fname, excel_bytes)
            st.success(f"Saved to Drive → 5_Outputs/{fname}")


# ── Main router ───────────────────────────────────────────────────────────────
def main():
    if not st.session_state.get("credentials_loaded"):
        connect_drive()
        if st.session_state.get("credentials_loaded"):
            load_drive_training_data()

    page = render_sidebar()

    if page == "Dashboard":
        page_dashboard()
    elif page == "Ticker Search":
        page_ticker_search()
    elif page == "Data Files":
        page_data_files()
    elif page == "New Run":
        page_new_run()


if __name__ == "__main__":
    main()
