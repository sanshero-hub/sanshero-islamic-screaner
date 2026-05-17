"""
PDF & Excel reader — extracts Musaffa compliance data and Damodaran methodology context
"""

import io, re
import anthropic


def extract_text_from_pdf_bytes(pdf_bytes: bytes) -> str:
    try:
        import PyPDF2
        reader = PyPDF2.PdfReader(io.BytesIO(pdf_bytes))
        text = ""
        for page in reader.pages:
            text += (page.extract_text() or "") + "\n"
        return text.strip()
    except Exception as e:
        return ""


def parse_musaffa_pdf(pdf_bytes: bytes, anthropic_key: str) -> dict:
    raw_text = extract_text_from_pdf_bytes(pdf_bytes)
    if not raw_text:
        return {}

    client = anthropic.Anthropic(api_key=anthropic_key)
    system = """You are extracting Islamic stock compliance data from a Musaffa report PDF.
Extract every stock mentioned and its compliance status.
Respond ONLY with a JSON object mapping ticker symbols to compliance status strings.
Map all halal/compliant variants to "HALAL".
Map all questionable/needs purification variants to "PURIFY".
Map all not halal/haram/non-compliant variants to "HARAM".
Example: {"AAPL": "PURIFY", "MSFT": "HALAL", "JPM": "HARAM"}
If no tickers found, return {}"""

    try:
        resp = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=500,
            system=system,
            messages=[{
                "role": "user",
                "content": f"Extract compliance data from this Musaffa report:\n\n{raw_text[:3000]}"
            }]
        )
        raw = resp.content[0].text.strip().replace("```json", "").replace("```", "").strip()
        return json_safe_parse(raw)
    except Exception:
        return {}


def extract_damodaran_context(excel_bytes: bytes) -> str:
    try:
        import pandas as pd
        xl = pd.ExcelFile(io.BytesIO(excel_bytes))
        context_parts = []
        for sheet in xl.sheet_names[:4]:
            try:
                df = xl.parse(sheet, header=None)
                text = df.to_string(index=False, header=False, na_rep="")
                context_parts.append(f"[Sheet: {sheet}]\n{text[:1500]}")
            except Exception:
                continue
        return "\n\n".join(context_parts)[:4000]
    except Exception:
        return ""


def load_damodaran_sector_benchmarks(excel_bytes_map: dict) -> dict:
    benchmarks = {}
    try:
        import pandas as pd

        if "pe.xls" in excel_bytes_map:
            df = pd.read_excel(io.BytesIO(excel_bytes_map["pe.xls"]), header=0)
            df.columns = [str(c).strip().lower() for c in df.columns]
            name_col  = next((c for c in df.columns if "industry" in c or "sector" in c), None)
            pe_col    = next((c for c in df.columns if "p/e" in c or "pe" in c), None)
            if name_col and pe_col:
                for _, row in df.iterrows():
                    sector = str(row.get(name_col, "")).strip()
                    val    = row.get(pe_col)
                    if sector and val and str(val).replace(".","").isdigit():
                        benchmarks.setdefault(sector, {})["pe"] = float(val)

        if "EVmultiples.xls" in excel_bytes_map:
            df = pd.read_excel(io.BytesIO(excel_bytes_map["EVmultiples.xls"]), header=0)
            df.columns = [str(c).strip().lower() for c in df.columns]
            name_col = next((c for c in df.columns if "industry" in c or "sector" in c), None)
            ev_col   = next((c for c in df.columns if "ev/ebitda" in c or "evebitda" in c), None)
            if name_col and ev_col:
                for _, row in df.iterrows():
                    sector = str(row.get(name_col, "")).strip()
                    val    = row.get(ev_col)
                    if sector and val and str(val).replace(".","").isdigit():
                        benchmarks.setdefault(sector, {})["ev_ebitda"] = float(val)

        if "wacc.xls" in excel_bytes_map:
            df = pd.read_excel(io.BytesIO(excel_bytes_map["wacc.xls"]), header=0)
            df.columns = [str(c).strip().lower() for c in df.columns]
            name_col  = next((c for c in df.columns if "industry" in c or "sector" in c), None)
            wacc_col  = next((c for c in df.columns if "wacc" in c), None)
            if name_col and wacc_col:
                for _, row in df.iterrows():
                    sector = str(row.get(name_col, "")).strip()
                    val    = row.get(wacc_col)
                    if sector and val:
                        try:
                            benchmarks.setdefault(sector, {})["wacc"] = float(val)
                        except Exception:
                            pass

    except Exception:
        pass

    return benchmarks


def json_safe_parse(text: str) -> dict:
    try:
        return __import__("json").loads(text)
    except Exception:
        return {}
