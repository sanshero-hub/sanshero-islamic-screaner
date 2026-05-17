# Islamic Stock Screener
### AAOIFI Standard No. 21 · Damodaran DCF Valuation · US Equities

---

## Files in this project

| File | Purpose |
|------|---------|
| `app.py` | Main Streamlit web application |
| `screener.py` | AAOIFI screening + Damodaran valuation engine |
| `drive.py` | Google Drive integration |
| `pdf_reader.py` | Musaffa PDF + Damodaran Excel reader |
| `excel_export.py` | Formatted Excel output builder |
| `requirements.txt` | Python dependencies |
| `.streamlit/secrets.toml.example` | API keys template |

---

## Deployment — Step by Step

### Step 1 — Create GitHub repository

1. Go to `github.com` → click **+** (top right) → **New repository**
2. Name it: `islamic-screener`
3. Set to **Public**
4. Click **Create repository**
5. Click **uploading an existing file**
6. Drag and drop ALL files from this ZIP (including the `.streamlit` folder)
7. Click **Commit changes**

### Step 2 — Deploy on Streamlit Cloud

1. Go to `share.streamlit.io`
2. Click **New app**
3. Select your GitHub repository: `islamic-screener`
4. Main file path: `app.py`
5. Click **Deploy**
6. Wait ~2 minutes for it to build

### Step 3 — Add your secrets

1. In Streamlit Cloud → your app → **Settings** → **Secrets**
2. Copy the contents of `.streamlit/secrets.toml.example`
3. Replace placeholder values with your real keys:
   - `FMP_API_KEY` — from financialmodelingprep.com dashboard
   - `ANTHROPIC_API_KEY` — from console.anthropic.com
   - `GOOGLE_CREDENTIALS` — open your `google_credentials.json` file,
     copy the entire contents, paste between the triple quotes
4. Click **Save**
5. App will restart automatically

### Step 4 — Connect Google Drive

1. Open your app URL
2. In the sidebar, click **Connect Google Drive**
3. It will automatically create these folders in your Drive:
   ```
   📁 Islamic Screener
   ├── 📁 1_Damodaran_Training
   ├── 📁 2_Valuation_Templates
   ├── 📁 3_Watchlists
   ├── 📁 4_Musaffa_Reports
   └── 📁 5_Outputs
   ```

### Step 5 — Upload your data files

Go to **Data Files** in the app:

**Tab 1 — Damodaran Training** (download from `pages.stern.nyu.edu/~adamodar/New_Home_Page/datafile/`)
- `betaUSA.xls` — betas by sector
- `wacc.xls` — WACC by sector
- `margins.xls` — margins by sector
- `pe.xls` — P/E ratios by sector
- `EVmultiples.xls` — EV/EBITDA by sector
- `growth.xls` — growth rates by sector

**Tab 2 — Valuation Templates**
- Upload any complete Damodaran valuation Excel (e.g. his Apple or Tesla model)

**Tab 3 — Watchlists**
- Upload a CSV of tickers or paste them directly

**Tab 4 — Musaffa Reports**
- Drop your Musaffa compliance PDF reports here

### Step 6 — Run your first screen

1. Click **New Run** in the sidebar
2. Select sectors or use your watchlist
3. Choose run mode: Both / Compliance Only / Valuation Only
4. Choose output filter: All / HALAL+PURIFY / BUY only / BUY+HOLD
5. Click **Start Screening**
6. Watch the live log as stocks are processed
7. Download Excel or save to Google Drive when complete

---

## Shariah Screening — AAOIFI Standard No. 21

### Status labels

| Label | Meaning |
|-------|---------|
| ✅ HALAL | Passes all 4 AAOIFI checks, zero impure income |
| 🔶 PURIFY | Passes all checks but has minor incidental interest income (<5%). Donate purification % of dividends to charity. |
| ❌ HARAM | Failed sector screen or one or more ratio thresholds |

### Layer 1 — Sector screen (hard exclusions)
Conventional banks, insurance, tobacco, alcohol, gambling, weapons, adult entertainment, mortgage REITs

### Layer 2 — AAOIFI financial ratios
- Interest-bearing debt / Market Cap **< 30%**
- Cash & securities / Market Cap **< 30%**
- Non-permissible income / Revenue **< 5%**

### Musaffa override
If a Musaffa PDF is uploaded containing a verdict for a ticker, that verdict takes priority over our calculation. The source column shows "Musaffa verified" when this applies.

---

## Valuation — Damodaran DCF

- **WACC** — sector beta × equity risk premium + risk-free rate
- **Growth years 1–5** — sector growth rate from Damodaran data
- **Terminal growth** — capped at 4.5% (10Y Treasury estimate)
- **Margin of safety** = (Intrinsic Value − Price) / Intrinsic Value × 100

### Verdicts
| Verdict | Condition |
|---------|-----------|
| 📈 BUY | MoS ≥ 20% AND relative valuation is Cheap or Fair |
| ⏸ HOLD | MoS between -10% and 20% |
| 🚫 AVOID | MoS < -10% OR fundamentals deteriorating |

---

## Google Drive folder structure

```
📁 Islamic Screener                 ← root (shared with service account)
├── 📁 1_Damodaran_Training         ← upload sector .xls files annually
├── 📁 2_Valuation_Templates        ← upload Damodaran valuation Excel
├── 📁 3_Watchlists                 ← upload or save ticker CSVs
├── 📁 4_Musaffa_Reports            ← drop Musaffa PDFs here
└── 📁 5_Outputs                    ← all run outputs auto-saved here
```

---

## Cost reference

| Item | Cost |
|------|------|
| Streamlit Cloud hosting | Free |
| GitHub | Free |
| Google Drive | Free |
| FMP free tier (~40 stocks/day) | Free |
| FMP Starter (unlimited) | $14/month |
| Anthropic Claude API (full run) | ~$0.80–$1.00 per 210-stock run |

---

## Disclaimer

This tool is for educational and research purposes only. It does not constitute a fatwa, financial advice, or investment recommendation. Always verify data against official SEC filings before making any investment decision. Shariah compliance determinations may differ across scholars and jurisdictions. The purification amounts shown are estimates — consult a qualified scholar for your specific situation.
