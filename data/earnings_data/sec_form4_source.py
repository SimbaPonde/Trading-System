from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, List

import pandas as pd
import requests
import xml.etree.ElementTree as ET


def _norm_ticker(t: str) -> str:
    return str(t).upper().strip()


def _pad_cik(cik: str | int) -> str:
    s = str(cik).strip()
    s = re.sub(r"\D", "", s)
    return s.zfill(10)


def _safe_float(x) -> Optional[float]:
    try:
        if x is None:
            return None
        s = str(x).strip()
        if s == "":
            return None
        return float(s)
    except Exception:
        return None


def _safe_int(x) -> Optional[int]:
    try:
        if x is None:
            return None
        s = str(x).strip()
        if s == "":
            return None
        return int(float(s))
    except Exception:
        return None


def _extract_xml_payload(text: str) -> str:
    """
    SEC filings sometimes include HTML wrappers. We try to extract the main XML payload.
    """
    if not text:
        return ""

    # If already looks like XML doc
    if "<ownershipDocument" in text:
        m = re.search(r"(<ownershipDocument[\s\S]*?</ownershipDocument>)", text)
        if m:
            return m.group(1)

    # Some have <XML> ... </XML> wrappers
    m = re.search(r"(<\?xml[\s\S]*?>[\s\S]*</ownershipDocument>)", text)
    if m:
        return m.group(0)

    # fallback: best-effort: take everything from first "<" to last ">"
    i = text.find("<")
    j = text.rfind(">")
    if i >= 0 and j > i:
        return text[i : j + 1]
    return text


@dataclass
class SECForm4Source:
    user_agent: str
    cache_dir: str | Path = "cache"
    sleep_s: float = 0.2  # be polite to SEC

    def __post_init__(self):
        self.cache_dir = Path(self.cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": self.user_agent,
            "Accept-Encoding": "gzip, deflate",
            "Host": "data.sec.gov",
        })

        self._ticker_map: Optional[Dict[str, str]] = None  # ticker -> cik10

    # ---------- HTTP helpers ----------

    def _get(self, url: str) -> requests.Response:
        time.sleep(self.sleep_s)
        r = self.session.get(url, timeout=30)
        r.raise_for_status()
        return r

    # ---------- Ticker -> CIK ----------

    def _load_ticker_map(self) -> Dict[str, str]:
        if self._ticker_map is not None:
            return self._ticker_map

        cache_path = self.cache_dir / "sec_company_tickers.json"
        if cache_path.exists():
            try:
                data = json.loads(cache_path.read_text(encoding="utf-8"))
                m = {}
                for _, row in data.items():
                    t = _norm_ticker(row.get("ticker"))
                    cik = _pad_cik(row.get("cik_str"))
                    if t and cik:
                        m[t] = cik
                self._ticker_map = m
                return m
            except Exception:
                pass

        # SEC official mapping
        url = "https://www.sec.gov/files/company_tickers.json"
        r = requests.get(url, headers={"User-Agent": self.user_agent}, timeout=30)
        r.raise_for_status()
        data = r.json()
        try:
            cache_path.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass

        m = {}
        for _, row in data.items():
            t = _norm_ticker(row.get("ticker"))
            cik = _pad_cik(row.get("cik_str"))
            if t and cik:
                m[t] = cik
        self._ticker_map = m
        return m

    def _ticker_to_cik10(self, ticker: str) -> Optional[str]:
        t = _norm_ticker(ticker)
        m = self._load_ticker_map()
        return m.get(t)

    # ---------- Submissions JSON ----------

    def _submissions_cache_path(self, cik10: str) -> Path:
        return self.cache_dir / f"sec_submissions_{cik10}.json"

    def _get_submissions_json(self, cik10: str) -> dict:
        cik10 = _pad_cik(cik10)
        p = self._submissions_cache_path(cik10)

        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                pass

        url = f"https://data.sec.gov/submissions/CIK{cik10}.json"
        data = self._get(url).json()

        try:
            p.write_text(json.dumps(data), encoding="utf-8")
        except Exception:
            pass

        return data

    # ---------- Filing fetch ----------

    def _filing_cache_path(self, accession: str) -> Path:
        acc = accession.replace("-", "")
        return self.cache_dir / f"sec_form4_{acc}.txt"

    def _fetch_filing_text(self, cik10: str, accession: str, primary_doc: str) -> str:
        cik10 = _pad_cik(cik10)
        acc_nodash = accession.replace("-", "")

        p = self._filing_cache_path(accession)
        if p.exists():
            try:
                return p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                pass

        # data.sec.gov/Archives/edgar/data/{cik}/{acc_nodash}/{primary_doc}
        url = f"https://data.sec.gov/Archives/edgar/data/{int(cik10)}/{acc_nodash}/{primary_doc}"
        txt = self._get(url).text

        try:
            p.write_text(txt, encoding="utf-8")
        except Exception:
            pass

        return txt

    # ---------- XML parsing ----------

    def _parse_form4_xml(self, xml_text: str, ticker: str, fallback_date: pd.Timestamp) -> pd.DataFrame:
        xml_text = _extract_xml_payload(xml_text)
        if not xml_text:
            return pd.DataFrame()

        # Some filings have bad xml entities; be forgiving
        xml_text = xml_text.replace("&nbsp;", " ").replace("\x00", "")

        try:
            root = ET.fromstring(xml_text)
        except Exception:
            return pd.DataFrame()

        ns = ""  # SEC form 4 usually no namespaces
        def findall(path: str):
            return root.findall(path)

        # Identify reporting owner
        insider_name = None
        try:
            owner = root.find("./reportingOwner/reportingOwnerId/rptOwnerName")
            if owner is not None and owner.text:
                insider_name = owner.text.strip()
        except Exception:
            insider_name = None

        rows = []

        # Non-derivative transactions
        for tx in findall(".//nonDerivativeTable/nonDerivativeTransaction"):
            code = tx.findtext("./transactionCoding/transactionCode")
            code = (code or "").strip().upper()

            shares = _safe_float(tx.findtext("./transactionAmounts/transactionShares/value"))
            price = _safe_float(tx.findtext("./transactionAmounts/transactionPricePerShare/value"))
            tdate = tx.findtext("./transactionDate/value")
            trade_date = pd.to_datetime(tdate, errors="coerce").normalize() if tdate else pd.NaT

            is10b5 = tx.findtext("./transactionCoding/transactionFormType")
            # Better: treat as routine only if 10b5-1 flag exists and true
            tenb5 = tx.findtext(".//tenb5One/tenb5OneFlag")
            is_routine = False
            if tenb5 is not None and str(tenb5).strip().lower() in ("1", "true", "yes", "y"):
                is_routine = True

            if pd.isna(trade_date):
                trade_date = fallback_date

            value_usd = None
            if shares is not None and price is not None:
                value_usd = float(shares) * float(price)

            rows.append({
                "symbol": _norm_ticker(ticker),
                "trade_date": trade_date,
                "transaction_type": code,   # P/S/M/etc
                "shares": shares,
                "price": price,
                "value_usd": value_usd if value_usd is not None else 0.0,
                "is_routine": bool(is_routine),
                "insider_name": insider_name,
            })

        # Derivative transactions (optional, but helpful)
        for tx in findall(".//derivativeTable/derivativeTransaction"):
            code = tx.findtext("./transactionCoding/transactionCode")
            code = (code or "").strip().upper()

            shares = _safe_float(tx.findtext("./transactionAmounts/transactionShares/value"))
            price = _safe_float(tx.findtext("./transactionAmounts/transactionPricePerShare/value"))
            tdate = tx.findtext("./transactionDate/value")
            trade_date = pd.to_datetime(tdate, errors="coerce").normalize() if tdate else pd.NaT
            if pd.isna(trade_date):
                trade_date = fallback_date

            # Derivatives often not a good “value” proxy; keep what we can
            value_usd = None
            if shares is not None and price is not None:
                value_usd = float(shares) * float(price)

            rows.append({
                "symbol": _norm_ticker(ticker),
                "trade_date": trade_date,
                "transaction_type": code,
                "shares": shares,
                "price": price,
                "value_usd": value_usd if value_usd is not None else 0.0,
                "is_routine": False,
                "insider_name": insider_name,
            })

        if not rows:
            return pd.DataFrame()

        df = pd.DataFrame(rows)
        df["trade_date"] = pd.to_datetime(df["trade_date"], errors="coerce").dt.normalize()
        df["transaction_type"] = df["transaction_type"].astype(str).str.upper().str.strip()

        # Keep only meaningful codes: P (buy), S (sell), M (option exercise) etc.
        df = df[df["transaction_type"] != ""].copy()
        return df

    # ---------- Public API ----------

    def get_insider_trades(self, ticker: str, start_date, end_date) -> pd.DataFrame:
        """
        Returns Form 4-derived insider trades for the ticker.
        IMPORTANT: we filter filings by filingDate (reliable), not by transactionDate (often missing).
        """
        t = _norm_ticker(ticker)
        start_ts = pd.to_datetime(start_date).normalize()
        end_ts = pd.to_datetime(end_date).normalize()
        
        # Ensure timezone-naive for comparison (SEC dates are always naive)
        if start_ts.tzinfo is not None:
            start_ts = start_ts.tz_localize(None)
        if end_ts.tzinfo is not None:
            end_ts = end_ts.tz_localize(None)

        cik10 = self._ticker_to_cik10(t)
        if not cik10:
            return pd.DataFrame()

        subs = self._get_submissions_json(cik10)

        recent = subs.get("filings", {}).get("recent", {})
        forms = recent.get("form", [])
        accession = recent.get("accessionNumber", [])
        filing_dates = recent.get("filingDate", [])
        primary_docs = recent.get("primaryDocument", [])

        if not forms:
            return pd.DataFrame()

        rows = []
        for form, acc, fdate, pdoc in zip(forms, accession, filing_dates, primary_docs):
            if str(form).strip() != "4":
                continue

            fd = pd.to_datetime(fdate, errors="coerce").normalize()
            if pd.isna(fd):
                continue

            if fd < start_ts or fd > end_ts:
                continue

            if not acc or not pdoc:
                continue

            try:
                txt = self._fetch_filing_text(cik10, acc, pdoc)
                df = self._parse_form4_xml(txt, t, fallback_date=fd)
                if df is not None and not df.empty:
                    rows.append(df)
            except Exception:
                continue

        if not rows:
            return pd.DataFrame()

        out = pd.concat(rows, ignore_index=True)

        # Final cleanup
        out["symbol"] = out["symbol"].astype(str).str.upper().str.strip()
        out["trade_date"] = pd.to_datetime(out["trade_date"], errors="coerce").dt.normalize()
        out["value_usd"] = pd.to_numeric(out["value_usd"], errors="coerce").fillna(0.0)

        # keep within range by trade_date (now trade_date always exists due to fallback)
        out = out[(out["trade_date"] >= start_ts) & (out["trade_date"] <= end_ts)].copy()
        return out
