"""
Islamic Stock Screener — Core Engine
AAOIFI Standard No. 21 Shariah Screening + Damodaran DCF Valuation
FMP Stable API (post August 2025)
"""

import json, time, requests
import anthropic

FMP_BASE = "https://financialmodelingprep.com/stable"

SECTOR_TICKERS = {
    "Technology": [
        "AAPL","MSFT","NVDA","GOOGL","META","ORCL","CSCO","IBM","QCOM","TXN",
        "AMAT","KLAC","LRCX","AVGO","AMD","HPQ","DELL","NOW","ADBE","INTU",
        "PANW","FTNT","SNPS","CDNS","ANSS",
    ],
    "Healthcare": [
        "JNJ","ABT","MDT","TMO","DHR","BSX","SYK","EW","BDX","ISRG",
        "IDXX","IQV","ZBH","HOLX","GMED","DXCM","RMD","PODD","ALGN","TFX",
    ],
    "Energy": [
        "XOM","CVX","COP","EOG","PSX","MPC","VLO","SLB","BKR","HAL",
        "OXY","DVN","FANG","APA","MRO","HES","CTRA","SM","MTDR","CHRD",
    ],
    "Industrials": [
        "GE","HON","CAT","DE","RTX","LMT","GD","NOC","ITW","EMR",
        "ETN","PH","ROK","AME","XYL","IR","OTIS","CARR","FTV","GNRC",
    ],
    "Consumer Discretionary": [
        "AMZN","HD","LOW","NKE","SBUX","MCD","CMG","ORLY","AZO","ULTA",
        "TJX","ROST","BBY","DPZ","YUM","F","GM","TSLA","BKNG","MAR",
    ],
    "Consumer Staples": [
        "PG","KO","PEP","COST","WMT","CL","KMB","GIS","K","SJM",
        "MKC","CHD","CLX","EL","COTY","NWL","CENT","JJSF","LANC","THS",
    ],
    "Materials": [
        "LIN","APD","ECL","SHW","PPG","NEM","FCX","NUE","STLD","CLF",
        "AA","ALB","CE","EMN","FMC","RPM","OLN","HUN","TROX","IOSP",
    ],
    "Real Estate": [
        "PLD","AMT","EQIX","CCI","PSA","WELL","DLR","SPG","O","EQR",
        "AVB","MAA","UDR","CPT","ESS","ARE","BXP","VTR","PEAK","HST",
    ],
    "Utilities": [
        "NEE","DUK","SO","D","AEP","EXC","SRE","PEG","ED","XEL",
        "WEC","ES","DTE","ETR","FE","PPL","AEE","CMS","LNT","EVRG",
    ],
    "Communication Services": [
        "NFLX","DIS","CMCSA","T","VZ","TMUS","CHTR","SIRI","IPG","OMC",
        "NYT","NWSA","MTCH","SNAP","PINS","SPOT","TTD","ZG","IAC","FOXA",
    ],
}

ALWAYS_EXCLUDED_INDUSTRIES = {
    "Banks","Diversified Banks","Regional Banks","Investment Banking & Brokerage",
    "Insurance","Life & Health Insurance","Property & Casualty Insurance",
    "Thrifts & Mortgage Finance","Consumer Finance","Capital Markets",
    "Mortgage REITs","Asset Management & Custody Banks",
}

ALWAYS_EXCLUDED_SECTORS = {"Financials"}

HARAM_KEYWORDS = [
    "alcohol","beer","wine","spirits","distill","brew","casino","gambling",
    "lottery","tobacco","cigarette","pork","swine","adult entertainment",
    "pornograph","weapons manufacturer","ammunition manufacturer",
]

VALUATION_SYSTEM = """You are an expert equity analyst applying Aswath Damodaran's valuation methodology.
Given raw financial data and sector benchmarks, produce a rigorous DCF + relative valuation.
Respond ONLY with a valid JSON object — no markdown, no code fences, no preamble.

Required JSON structure:
{
  "intrinsic_value_per_share": <number>,
  "dcf_wacc_pct": <number>,
  "dcf_terminal_growth_pct": <number>,
  "dcf_growth_yr1_5_pct": <number>,
  "dcf_roic_pct": <number>,
  "bear_case_iv": <number>,
  "bull_case_iv": <number>,
  "margin_of_safety_pct": <number>,
  "pe_company": <number or null>,
  "pe_sector_avg": <number>,
  "ev_ebitda_company": <number or null>,
  "ev_ebitda_sector_avg": <number>,
  "relative_assessment": "Cheap" | "Fair" | "Expensive",
  "final_verdict": "BUY" | "HOLD" | "AVOID",
  "verdict_rationale": "<one concise sentence>",
  "purification_pct": <number>
}

Damodaran rules:
- Terminal growth rate never exceeds 4.5%
- WACC must reflect sector beta and current risk-free rate (~4.5%)
- Margin of safety = (intrinsic_value - current_price) / intrinsic_value * 100
- BUY: margin_of_safety >= 20% AND relative_assessment in [Cheap, Fair]
- HOLD: margin_of_safety between -10% and 20%
- AVOID: margin_of_safety < -10% OR fundamentals deteriorating
- Purification = impure_income_ratio_pct (pass through, round to 2dp)"""


# ── FMP API helpers ────────────────────────────────────────────────────────────

def fmp_get(endpoint, api_key, params=None, retries=3):
    p = {"apikey": api_key}
    if params:
        p.update(params)
    for attempt in range(retries):
        try:
            r = requests.get(f"{FMP_BASE}/{endpoint}", params=p, timeout=15)
            if r.status_code == 429:
                time.sleep(15)
                continue
            if r.status_code != 200:
                return None
            data = r.json()
            return data if data else None
        except Exception:
            if attempt < retries - 1:
                time.sleep(3)
    return None


def get_profile(ticker, api_key):
    """Returns company profile with mktCap, sector, industry, description, price"""
    data = fmp_get("profile", api_key, {"symbol": ticker})
    return data[0] if data else None


def get_income(ticker, api_key):
    """Returns income statement — revenue, netIncome, ebitda, interestExpense"""
    data = fmp_get("income-statement", api_key, {"symbol": ticker, "limit": 1})
    return data[0] if data else None


def get_balance(ticker, api_key):
    """Returns balance sheet — totalDebt, shortTermDebt, longTermDebt,
       cashAndCashEquivalents, shortTermInvestments, totalAssets"""
    data = fmp_get("balance-sheet-statement", api_key, {"symbol": ticker, "limit": 1})
    return data[0] if data else None


def get_cashflow(ticker, api_key):
    """Returns cash flow — freeCashFlow, capitalExpenditure"""
    data = fmp_get("cash-flow-statement", api_key, {"symbol": ticker, "limit": 1})
    return data[0] if data else None


def get_metrics(ticker, api_key):
    """Returns key metrics — peRatio, evToEbitda, roic, revenuePerShare"""
    data = fmp_get("key-metrics", api_key, {"symbol": ticker, "limit": 1})
    return data[0] if data else None


def get_ratios(ticker, api_key):
    """Returns ratios — priceEarningsRatio, grossProfitMargin, freeCashFlowPerShare"""
    data = fmp_get("ratios", api_key, {"symbol": ticker, "limit": 1})
    return data[0] if data else None


def get_quote(ticker, api_key):
    """Returns current price, 52-week high and low"""
    data = fmp_get("quote", api_key, {"symbol": ticker})
    if data:
        q = data[0]
        return q.get("price"), q.get("yearHigh"), q.get("yearLow")
    return None, None, None


# ── AAOIFI Layer 1 — Sector screen ────────────────────────────────────────────

def sector_screen(profile):
    if not profile:
        return False, "No profile data available"

    industry = (profile.get("industry") or "").strip()
    sector   = (profile.get("sector") or "").strip()
    desc     = (profile.get("description") or "").lower()
    name     = (profile.get("companyName") or "").lower()

    if industry in ALWAYS_EXCLUDED_INDUSTRIES:
        return False, f"Excluded industry: {industry}"
    if sector in ALWAYS_EXCLUDED_SECTORS:
        return False, f"Excluded sector: {sector}"
    for kw in HARAM_KEYWORDS:
        if kw in desc or kw in name:
            return False, f"Haram activity detected: {kw}"
    return True, "Passed sector screen"


# ── AAOIFI Layer 2 — Financial ratio screen ───────────────────────────────────

def ratio_screen(profile, income, balance):
    """
    AAOIFI Standard No. 21 three-ratio screen.
    Sources:
      - mktCap: from profile endpoint
      - totalDebt: shortTermDebt + longTermDebt from balance sheet
        (FMP stable uses 'shortTermDebt' and 'longTermDebt')
      - cash: cashAndCashEquivalents + shortTermInvestments from balance sheet
      - interestIncome: from income statement (interest earned on cash/investments)
      - revenue: from income statement
    """
    results = {
        "passed": True,
        "reasons": [],
        "debt_ratio": None,
        "cash_ratio": None,
        "impure_income_ratio": None,
        "fail_reason": "",
    }

    # Market cap from profile
    mkt_cap = (profile or {}).get("mktCap") or 0

    if mkt_cap <= 0:
        results["passed"] = False
        results["reasons"].append("Market cap unavailable")
        results["fail_reason"] = "Market cap unavailable"
        return results

    # ── Ratio 1: Interest-bearing debt / Market Cap < 30% ──
    b = balance or {}
    # FMP stable API field names for debt
    short_debt = b.get("shortTermDebt") or b.get("shortTermDebtAndCurrentPortionOfLongTermDebt") or 0
    long_debt  = b.get("longTermDebt") or b.get("longTermDebtNoncurrent") or 0
    total_debt = short_debt + long_debt

    # Fallback: try totalDebt field directly
    if total_debt == 0:
        total_debt = b.get("totalDebt") or 0

    r1 = total_debt / mkt_cap
    results["debt_ratio"] = r1
    if r1 >= 0.30:
        results["passed"] = False
        results["reasons"].append(f"Debt/MktCap {r1:.1%} ≥ 30%")

    # ── Ratio 2: Cash & interest-bearing securities / Market Cap < 30% ──
    cash = (b.get("cashAndCashEquivalents") or 0) + \
           (b.get("shortTermInvestments") or b.get("otherShortTermInvestments") or 0)
    r2 = cash / mkt_cap
    results["cash_ratio"] = r2
    if r2 >= 0.30:
        results["passed"] = False
        results["reasons"].append(f"Cash/MktCap {r2:.1%} ≥ 30%")

    # ── Ratio 3: Non-permissible income / Total Revenue < 5% ──
    inc = income or {}
    revenue = inc.get("revenue") or 0
    # interestIncome = interest earned (not interest expense)
    # FMP may call it interestIncome or nonInterestIncome depending on company type
    interest_inc = abs(inc.get("interestIncome") or 0)

    if revenue > 0:
        r3 = interest_inc / revenue
        results["impure_income_ratio"] = r3
        if r3 >= 0.05:
            results["passed"] = False
            results["reasons"].append(f"Impure income {r3:.1%} ≥ 5%")
    else:
        results["impure_income_ratio"] = 0.0

    results["fail_reason"] = "; ".join(results["reasons"])
    return results


def get_shariah_status(sector_pass, ratio_results, musaffa_override=None):
    if musaffa_override:
        return musaffa_override, "Musaffa verified"
    if not sector_pass:
        return "HARAM", "sector screen"
    if not ratio_results.get("passed"):
        return "HARAM", "ratio screen"
    impure = ratio_results.get("impure_income_ratio") or 0
    if impure > 0:
        return "PURIFY", "minor impure income"
    return "HALAL", "all checks passed"


# ── Layer 3 — Claude Damodaran valuation ──────────────────────────────────────

def run_claude_valuation(anthropic_key, ticker, profile, income, balance,
                         cashflow, metrics, ratios, current_price,
                         impure_ratio, sector_benchmarks=None,
                         damodaran_context=None):
    def safe(v, d=2):
        try:
            return round(float(v), d) if v is not None else None
        except Exception:
            return None

    def mm(v):
        try:
            return round(float(v) / 1_000_000, 1) if v else None
        except Exception:
            return None

    b = balance or {}
    inc = income or {}
    cf  = cashflow or {}
    m   = metrics or {}
    ra  = ratios or {}
    p   = profile or {}

    short_debt = b.get("shortTermDebt") or 0
    long_debt  = b.get("longTermDebt") or 0
    total_debt = short_debt + long_debt or b.get("totalDebt") or 0

    payload = {
        "ticker": ticker,
        "company": p.get("companyName"),
        "sector": p.get("sector"),
        "industry": p.get("industry"),
        "current_price_usd": safe(current_price),
        "market_cap_mm": mm(p.get("mktCap")),
        "revenue_mm": mm(inc.get("revenue")),
        "ebitda_mm": mm(inc.get("ebitda")),
        "net_income_mm": mm(inc.get("netIncome")),
        "free_cash_flow_mm": mm(cf.get("freeCashFlow")),
        "total_debt_mm": mm(total_debt),
        "cash_mm": mm(b.get("cashAndCashEquivalents")),
        "shares_outstanding_mm": mm(p.get("sharesOutstanding")),
        "pe_ratio": safe(m.get("peRatio") or ra.get("priceEarningsRatio"), 1),
        "ev_ebitda": safe(m.get("evToEbitda") or m.get("enterpriseValueOverEBITDA"), 1),
        "roic": safe(m.get("roic"), 4),
        "gross_margin": safe(ra.get("grossProfitMargin"), 4),
        "impure_income_ratio_pct": round((impure_ratio or 0) * 100, 2),
    }

    if sector_benchmarks:
        payload["sector_benchmarks"] = sector_benchmarks
    if damodaran_context:
        payload["damodaran_methodology_notes"] = damodaran_context[:800]

    client = anthropic.Anthropic(api_key=anthropic_key)
    try:
        resp = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=800,
            system=VALUATION_SYSTEM,
            messages=[{
                "role": "user",
                "content": f"Value this stock:\n{json.dumps(payload, indent=2)}"
            }]
        )
        raw = resp.content[0].text.strip().replace("```json","").replace("```","").strip()
        return json.loads(raw)
    except Exception:
        return None


# ── Main per-ticker pipeline ───────────────────────────────────────────────────

def screen_ticker(ticker, fmp_key, anthropic_key, run_mode="both",
                  musaffa_data=None, sector_benchmarks=None,
                  damodaran_context=None):

    result = {
        "ticker": ticker, "company": ticker,
        "sector": "", "industry": "",
        "shariah_status": "—", "shariah_source": "—",
        "debt_ratio": None, "cash_ratio": None,
        "impure_income_ratio": None, "fail_reason": "",
        "current_price": None, "week52_high": None, "week52_low": None,
        "intrinsic_value": None, "margin_of_safety": None,
        "wacc": None, "terminal_growth": None,
        "pe_company": None, "pe_sector": None,
        "ev_ebitda_company": None, "ev_ebitda_sector": None,
        "relative_assessment": "—", "verdict": "—",
        "rationale": "", "purification_pct": None, "error": None,
    }

    profile = get_profile(ticker, fmp_key)
    if not profile:
        result["error"] = "No FMP data"
        return result

    result["company"]  = profile.get("companyName", ticker)
    result["sector"]   = profile.get("sector", "")
    result["industry"] = profile.get("industry", "")

    price, high, low = get_quote(ticker, fmp_key)
    result["current_price"]  = price
    result["week52_high"]    = high
    result["week52_low"]     = low

    musaffa_override = (musaffa_data or {}).get(ticker)

    income  = get_income(ticker, fmp_key)
    balance = get_balance(ticker, fmp_key)

    if run_mode in ("compliance", "both"):
        sector_pass, sector_reason = sector_screen(profile)

        if sector_pass:
            ratio_res = ratio_screen(profile, income, balance)
        else:
            ratio_res = {
                "passed": False, "debt_ratio": None, "cash_ratio": None,
                "impure_income_ratio": None, "fail_reason": sector_reason,
                "reasons": [sector_reason],
            }

        status, source = get_shariah_status(sector_pass, ratio_res, musaffa_override)
        result["shariah_status"]      = status
        result["shariah_source"]      = source
        result["debt_ratio"]          = ratio_res.get("debt_ratio")
        result["cash_ratio"]          = ratio_res.get("cash_ratio")
        result["impure_income_ratio"] = ratio_res.get("impure_income_ratio")
        result["fail_reason"]         = ratio_res.get("fail_reason", "")
    else:
        ratio_res = ratio_screen(profile, income, balance)

    if run_mode in ("valuation", "both") and anthropic_key:
        cashflow = get_cashflow(ticker, fmp_key)
        metrics  = get_metrics(ticker, fmp_key)
        ratios   = get_ratios(ticker, fmp_key)
        impure   = result.get("impure_income_ratio") or \
                   ratio_res.get("impure_income_ratio") or 0

        val = run_claude_valuation(
            anthropic_key, ticker, profile, income, balance,
            cashflow, metrics, ratios, price, impure,
            sector_benchmarks, damodaran_context,
        )
        if val:
            result["intrinsic_value"]     = val.get("intrinsic_value_per_share")
            result["margin_of_safety"]    = val.get("margin_of_safety_pct")
            result["wacc"]                = val.get("dcf_wacc_pct")
            result["terminal_growth"]     = val.get("dcf_terminal_growth_pct")
            result["pe_company"]          = val.get("pe_company")
            result["pe_sector"]           = val.get("pe_sector_avg")
            result["ev_ebitda_company"]   = val.get("ev_ebitda_company")
            result["ev_ebitda_sector"]    = val.get("ev_ebitda_sector_avg")
            result["relative_assessment"] = val.get("relative_assessment", "—")
            result["verdict"]             = val.get("final_verdict", "—")
            result["rationale"]           = val.get("verdict_rationale", "")
            result["purification_pct"]    = val.get("purification_pct")

    time.sleep(0.35)
    return result
