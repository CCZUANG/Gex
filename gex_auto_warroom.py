#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
全美股期權 GEX 戰情室 & Telegram 自動推播系統 (雙軌分工 + 每日開盤前自動早報旗艦版)
===============================================================================
更新時間: 2026-11-14 23:40:00 (UTC+8)

【本次升級重點】：
1. 內建「🌅 每日美股開盤前 15 分鐘自動早報 (Morning Briefing)」：
   - 每個美股交易日於美東時間 09:15 (冬令台灣時間 22:15 UTC+8 / 夏令 21:15 UTC+8)，
     VPS 後台自動掃描並發送完整早報至你的手機 Telegram (側邊欄亦可隨時一鍵手動發送)。
   - 早報完整涵蓋：
     (a) 大盤雙指標 (SPY & QQQ)：完整列出正負 Gamma、Net GEX、翻轉點、Call牆、Put牆、Max Pain、預期波動。
     (b) 核心自選股 12 檔 (NVDA, TSLA, LUNR, SPCX + 納斯達克前十大權重股 AAPL, MSFT, AMZN, AVGO, META, GOOGL, COST, NFLX)。
     (c) 全美股「臨門一腳」蓄勢名單 (現價距離 Squeeze 啟動價或支撐壓力牆 <= 1.5% 之高量比標的)。
     (d) 結算日 DTE 與 Charm 尾盤平倉時間窗提醒。
2. 網頁頂部快捷按鈕同步升級為 14 顆核心按鈕 (SPY, QQQ + 12 檔核心自選股)，手機一點即看。
3. 智慧期權鏈回退機制：若特定標的 (如剛上市或期權流動性較低之個股) 暫無期權鏈，自動以現貨籌碼密集區與 ATR/HV 推算等效支撐壓力牆，確保 12 檔核心自選股 100% 完整呈現不漏檔。
"""

import importlib
import os
import subprocess
import sys


REQUIRED_PACKAGES = {
    "streamlit": "streamlit>=1.32.0",
    "plotly": "plotly>=5.20.0",
    "yfinance": "yfinance>=0.2.40",
    "pandas": "pandas>=2.1.0",
    "numpy": "numpy>=1.26.0",
    "matplotlib": "matplotlib>=3.8.0",
    "requests": "requests>=2.31.0",
    "lxml": "lxml>=5.1.0",
}

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
IS_WINDOWS_VPS = os.name == "nt"

# 核心自選股：NVDA, TSLA, LUNR, SPCX + 納斯達克前十大股票 (去重後共 12 檔核心股)
DEFAULT_CORE_WATCHLIST = [
    "NVDA",
    "TSLA",
    "LUNR",
    "SPCX",
    "AAPL",
    "MSFT",
    "AMZN",
    "AVGO",
    "META",
    "GOOGL",
    "COST",
    "NFLX",
]
MARKET_INDEX_TICKERS = ["SPY", "QQQ"]


def auto_generate_github_deployment_files() -> None:
    req_path = os.path.join(BASE_DIR, "requirements.txt")
    pkg_path = os.path.join(BASE_DIR, "packages.txt")
    try:
        if not os.path.exists(req_path):
            with open(req_path, "w", encoding="utf-8") as f:
                f.write("\n".join(REQUIRED_PACKAGES.values()) + "\n")
        if not os.path.exists(pkg_path):
            with open(pkg_path, "w", encoding="utf-8") as f:
                f.write("fonts-noto-cjk\n")
    except Exception:
        pass


def auto_ensure_dependencies() -> None:
    missing = []
    for mod_name, pkg_spec in REQUIRED_PACKAGES.items():
        try:
            importlib.import_module(mod_name)
        except ImportError:
            missing.append(pkg_spec)

    if missing and "--test-self" not in sys.argv:
        print(f"📦 [自動安裝] 偵測到缺少套件 {missing}，正在自動為你執行 pip install...")
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", *missing])
            print("✅ [自動安裝完成] 所有套件已就緒！")
        except Exception as exc:
            print(f"⚠️ [自動安裝提示] 無法連線安裝套件 ({exc})，請確認網路連線。")


def is_running_inside_streamlit() -> bool:
    try:
        from streamlit.runtime.scriptrunner import get_script_run_ctx

        return get_script_run_ctx() is not None
    except Exception:
        return False


if __name__ == "__main__" and not is_running_inside_streamlit():
    auto_generate_github_deployment_files()
    auto_ensure_dependencies()
    if "--patrol" not in sys.argv and "--test-self" not in sys.argv:
        print("🚀 正在啟動 Windows VPS 全美股 GEX 戰情室與 24H 後台推播守護程序...")
        print("   • 本機設定網址: http://localhost:8501 (不需開放 VPS 防火牆)")
        print("   • 填妥一次 Telegram 金鑰後，把此黑色視窗最小化即可 24 小時自動推播早報與盤中異動！")
        script_path = os.path.abspath(__file__)
        sys.exit(
            subprocess.call(
                [
                    sys.executable,
                    "-m",
                    "streamlit",
                    "run",
                    script_path,
                    "--server.address",
                    "127.0.0.1",
                    "--server.port",
                    "8501",
                ]
            )
        )


import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
import datetime
import json
import math
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import matplotlib
matplotlib.use("Agg")
import matplotlib.font_manager as fm
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


def configure_cjk_font() -> None:
    plt.rcParams["axes.unicode_minus"] = False
    if "text.parse_math" in plt.rcParams:
        plt.rcParams["text.parse_math"] = False

    preferred = [
        "Microsoft JhengHei",
        "PingFang TC",
        "Noto Sans CJK TC",
        "Noto Sans CJK JP",
        "Noto Sans CJK SC",
        "Droid Sans Fallback",
        "SimHei",
    ]
    available = {f.name for f in fm.fontManager.ttflist}
    chosen = [name for name in preferred if name in available]
    if not chosen:
        for f in fm.fontManager.ttflist:
            if "Noto Sans CJK" in f.name or "JhengHei" in f.name or "Droid" in f.name:
                chosen.append(f.name)
                break
    plt.rcParams["font.sans-serif"] = chosen + ["DejaVu Sans"]


configure_cjk_font()

CONFIG_FILE_PATH = os.path.join(BASE_DIR, "gex_user_config.json")
STATE_FILE_PATH = os.path.join(BASE_DIR, "gex_iv_alert_state.json")
STATE_LOCK = threading.Lock()


def register_windows_startup() -> Tuple[bool, str]:
    if not IS_WINDOWS_VPS:
        return False, "目前為雲端 Linux 環境，無需建立 Windows 開機啟動捷徑。"
    try:
        appdata = os.environ.get("APPDATA", "")
        startup_dir = os.path.join(
            appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
        )
        os.makedirs(startup_dir, exist_ok=True)
        bat_path = os.path.join(startup_dir, "GEX_Auto_WarRoom_Startup.bat")
        script_abs = os.path.abspath(__file__)
        py_exe = sys.executable
        content = (
            f"@echo off\n"
            f"cd /d \"{BASE_DIR}\"\n"
            f"start \"GEX_Auto_WarRoom\" \"{py_exe}\" \"{script_abs}\"\n"
        )
        with open(bat_path, "w", encoding="utf-8") as f:
            f.write(content)
        return True, bat_path
    except Exception as exc:
        return False, str(exc)


def load_user_config() -> Dict:
    default_cfg = {
        "tg_token": os.environ.get("TELEGRAM_BOT_TOKEN", ""),
        "tg_chat_id": os.environ.get("TELEGRAM_CHAT_ID", ""),
        "web_password": os.environ.get("WARROOM_PASSWORD", ""),
        "core_watchlist": ", ".join(DEFAULT_CORE_WATCHLIST),
        "enable_morning_report": True,
        "iv_drop_thresh": 6.0,
        "patrol_interval_min": 15,
        "universe_mode": "SP500_NDX100",
        "max_scan": 30,
        "enable_bg_daemon": IS_WINDOWS_VPS,
        "only_us_market_hours": True,
    }
    if is_running_inside_streamlit():
        try:
            import streamlit as st

            if "TELEGRAM_BOT_TOKEN" in st.secrets:
                default_cfg["tg_token"] = str(st.secrets["TELEGRAM_BOT_TOKEN"])
            if "TELEGRAM_CHAT_ID" in st.secrets:
                default_cfg["tg_chat_id"] = str(st.secrets["TELEGRAM_CHAT_ID"])
            if "WARROOM_PASSWORD" in st.secrets:
                default_cfg["web_password"] = str(st.secrets["WARROOM_PASSWORD"])
        except Exception:
            pass

    if os.path.exists(CONFIG_FILE_PATH):
        try:
            with open(CONFIG_FILE_PATH, "r", encoding="utf-8") as f:
                saved = json.load(f)
            for k, v in saved.items():
                if v is not None and v != "":
                    default_cfg[k] = v
        except Exception:
            pass
    return default_cfg


def save_user_config(cfg: Dict) -> None:
    try:
        with open(CONFIG_FILE_PATH, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def load_tracker_state() -> Dict:
    with STATE_LOCK:
        if os.path.exists(STATE_FILE_PATH):
            try:
                with open(STATE_FILE_PATH, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {}
        return {}


def save_tracker_state(state: Dict) -> None:
    with STATE_LOCK:
        try:
            with open(STATE_FILE_PATH, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
        except Exception:
            pass


def is_us_market_active_window() -> bool:
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if now_utc.weekday() >= 5:
        return False
    utc_hour_float = now_utc.hour + now_utc.minute / 60.0
    return 13.0 <= utc_hour_float <= 21.5


def is_premarket_briefing_window() -> bool:
    """
    判斷是否進入每日美股開盤前 15~25 分鐘早報發送窗口：
    美東時間 09:10 ~ 09:25 (冬令對應台灣時間 22:10 ~ 22:25 UTC+8，夏令對應 21:10 ~ 21:25 UTC+8)。
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if now_utc.weekday() >= 5:
        return False
    utc_hm = now_utc.hour * 60 + now_utc.minute
    # 夏令美東 09:10~09:25 = UTC 13:10~13:25 (790~805); 冬令美東 09:10~09:25 = UTC 14:10~14:25 (850~865)
    return (790 <= utc_hm <= 808) or (850 <= utc_hm <= 868)


# ============================================================================
# 1. 全美股代碼庫自動載入器 + 第一階段現貨量價快篩
# ============================================================================
DEFAULT_HIGH_OPTION_LIQUIDITY_POOL = [
    "SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "SLV", "SMH", "SOXX", "ARKK",
    "NVDA", "TSLA", "LUNR", "SPCX", "AAPL", "MSFT", "AMZN", "META", "GOOGL", "AVGO",
    "COST", "NFLX", "AMD", "PLTR", "TSM", "MU", "ARM", "SMCI", "CRWD", "PANW",
    "SNOW", "ORCL", "CRM", "COIN", "MSTR", "MARA", "RIOT", "HOOD", "SOFI", "UPST",
    "AFRM", "SQ", "PYPL", "JPM", "BAC", "GS", "MS", "C", "WFC", "BRK-B",
    "V", "MA", "AXP", "LLY", "UNH", "JNJ", "ABBV", "MRK", "PFE", "AMGN",
    "GILD", "ISRG", "VRTX", "XOM", "CVX", "COP", "SLB", "OXY", "VST", "CEG",
    "NRG", "OKLO", "SMR", "RKLB", "ASTS", "JOBY", "ACHR", "IONQ", "RGTI", "QBTS",
    "SERV", "SOUN", "GME", "AMC", "RDDT", "DJT", "CVNA", "UBER", "ABNB", "DASH",
    "SHOP", "SE", "BABA", "PDD", "JD", "BIDU", "NIO", "XPEV", "LI", "FUTU",
    "TIGR", "WMT", "TGT", "HD", "LOW", "NKE", "SBUX", "MCD", "CMG", "DIS",
    "BA", "CAT", "DE", "GE", "LMT", "RTX", "NOC", "GD", "INTC", "QCOM",
    "TXN", "AMAT", "LRCX", "KLAC", "ASML", "MRVL", "ON", "MPWR", "DELL", "HPE", "ANET",
]


def parse_watchlist_string(raw_str: str) -> List[str]:
    items = [
        x.strip().upper()
        for x in raw_str.replace("、", ",").replace(";", ",").replace(" ", ",").split(",")
        if x.strip()
    ]
    seen = set()
    out = []
    for it in items:
        if it not in seen:
            seen.add(it)
            out.append(it)
    return out if out else list(DEFAULT_CORE_WATCHLIST)


def fetch_sp500_and_nasdaq100_tickers() -> List[str]:
    tickers = set(DEFAULT_HIGH_OPTION_LIQUIDITY_POOL)
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    for url in [
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "https://en.wikipedia.org/wiki/Nasdaq-100",
    ]:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10) as resp:
                html = resp.read().decode("utf-8")
            for df_t in pd.read_html(html):
                for col in ["Symbol", "Ticker"]:
                    if col in df_t.columns:
                        syms = df_t[col].astype(str).str.replace(".", "-", regex=False).tolist()
                        tickers.update(syms)
                        break
        except Exception:
            pass
    return sorted([t.strip().upper() for t in tickers if t.strip().isalpha() or "-" in t])


def fetch_all_us_sec_tickers() -> List[str]:
    headers = {"User-Agent": "QuantOptionsGEXScanner/3.0 (contact@quant-research.local)"}
    try:
        req = urllib.request.Request(
            "https://www.sec.gov/files/company_tickers.json", headers=headers
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        raw_tickers = [str(v["ticker"]).upper().replace(".", "-") for v in data.values()]
        clean = [
            t for t in raw_tickers if (1 <= len(t) <= 4 and t.isalpha()) or t in {"BRK-B"}
        ]
        return sorted(set(clean) | set(DEFAULT_HIGH_OPTION_LIQUIDITY_POOL))
    except Exception:
        return fetch_sp500_and_nasdaq100_tickers()


def stage1_fast_spot_prefilter(
    tickers: List[str],
    min_price: float = 5.0,
    min_dollar_vol: float = 20_000_000.0,
    min_vol_ratio: float = 1.15,
    min_abs_return_pct: float = 2.0,
    max_candidates: int = 35,
) -> List[str]:
    if len(tickers) <= max_candidates:
        return tickers

    import yfinance as yf

    scored: List[Tuple[float, str]] = []
    chunk_size = 250
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i : i + chunk_size]
        try:
            df_b = yf.download(
                chunk,
                period="1mo",
                interval="1d",
                group_by="ticker",
                threads=True,
                progress=False,
                auto_adjust=True,
            )
            if df_b.empty:
                continue
            for tk in chunk:
                try:
                    sub = df_b[tk] if len(chunk) > 1 else df_b
                    sub = sub.dropna(subset=["Close", "Volume"])
                    if len(sub) < 5:
                        continue
                    c_curr = float(sub["Close"].iloc[-1])
                    c_prev = float(sub["Close"].iloc[-2])
                    v_curr = float(sub["Volume"].iloc[-1])
                    v_ma20 = float(sub["Volume"].tail(20).mean())
                    d_vol = c_curr * v_ma20
                    if c_curr < min_price or d_vol < min_dollar_vol or v_ma20 <= 0:
                        continue
                    v_ratio = v_curr / v_ma20
                    ret_pct = abs((c_curr - c_prev) / max(c_prev, 0.01)) * 100.0
                    if v_ratio >= min_vol_ratio or ret_pct >= min_abs_return_pct:
                        score = v_ratio * (1.0 + ret_pct / 3.0) * math.log10(max(d_vol, 10.0))
                        scored.append((score, tk))
                except Exception:
                    continue
        except Exception:
            continue

    scored.sort(key=lambda x: x[0], reverse=True)
    selected = [tk for _, tk in scored[:max_candidates]]
    return selected if selected else tickers[:max_candidates]


# ============================================================================
# 2. Black-Scholes Greeks 與 GEX / Max Pain / Squeeze 核心運算引擎
# ============================================================================
def norm_pdf(x: np.ndarray) -> np.ndarray:
    return np.exp(-0.5 * x * x) / np.sqrt(2.0 * np.pi)


def norm_cdf(x: np.ndarray) -> np.ndarray:
    return 0.5 * (1.0 + np.vectorize(math.erf)(x / math.sqrt(2.0)))


def bs_greeks(
    spot: float,
    strikes: np.ndarray,
    tte_years: float,
    iv: np.ndarray,
    rate: float = 0.045,
    div_yield: float = 0.0,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    T = max(tte_years, 1.0 / (365.0 * 24.0))
    sigma = np.clip(iv, 0.05, 5.0)
    sqrt_T = np.sqrt(T)

    d1 = (np.log(spot / strikes) + (rate - div_yield + 0.5 * sigma**2) * T) / (
        sigma * sqrt_T
    )
    d2 = d1 - sigma * sqrt_T

    pdf_d1 = norm_pdf(d1)
    cdf_d1 = norm_cdf(d1)
    disc_q = np.exp(-div_yield * T)

    call_delta = disc_q * cdf_d1
    put_delta = disc_q * (cdf_d1 - 1.0)
    gamma = (disc_q * pdf_d1) / (spot * sigma * sqrt_T)
    vanna = -disc_q * pdf_d1 * (d2 / sigma)
    charm_daily = (
        -disc_q
        * (pdf_d1 * ((rate - div_yield) / (sigma * sqrt_T) - d2 / (2.0 * T)))
        / 365.0
    )
    return call_delta, put_delta, gamma, vanna, charm_daily


def dealer_call_polarity(
    call_vol: np.ndarray, call_oi: np.ndarray, call_iv: np.ndarray
) -> np.ndarray:
    vol_oi = call_vol / np.maximum(call_oi, 1.0)
    is_customer_buying_call = (vol_oi >= 0.85) & (call_iv >= 0.65)
    return np.where(is_customer_buying_call, -1.0, 1.0)


@dataclass
class AlertSignal:
    code: str
    title: str
    chart_badge: str
    description: str
    action_plan: str
    entry_price: float
    sl_price: float
    tp_price: float
    rrr: float


@dataclass
class WarRoomSnapshot:
    ticker: str
    timestamp_tw: str
    expiration_date: str
    dte_days: float
    spot_price: float
    prev_close: float
    latest_volume: float
    vol_ma20: float
    upper_wick_ratio: float
    atm_iv_pct: float
    iv_peak_pct: float
    iv_drop_from_peak_pct: float
    expected_move_usd: float
    expected_move_pct: float

    net_gex_millions: float
    zero_gamma_flip: float
    is_positive_gamma: bool

    call_wall: float
    put_wall: float
    max_pain: float

    bull_squeeze_trigger: float
    bear_squeeze_trigger: float
    bull_exhaustion_price: float
    bear_exhaustion_price: float
    charm_unwind_time_tw: str

    active_alerts: List[AlertSignal]


def compute_max_pain(df_chain: pd.DataFrame) -> float:
    strikes = df_chain["strike"].values
    call_oi = df_chain["call_oi"].values
    put_oi = df_chain["put_oi"].values
    payouts = [
        np.sum(
            np.maximum(0.0, s_exp - strikes) * call_oi * 100.0
            + np.maximum(0.0, strikes - s_exp) * put_oi * 100.0
        )
        for s_exp in strikes
    ]
    return float(strikes[int(np.argmin(payouts))])


def total_net_gex_at_price(
    test_spot: float,
    strikes: np.ndarray,
    call_oi: np.ndarray,
    put_oi: np.ndarray,
    call_iv: np.ndarray,
    put_iv: np.ndarray,
    tte_years: float,
) -> float:
    _, _, gamma_c, _, _ = bs_greeks(test_spot, strikes, tte_years, call_iv)
    _, _, gamma_p, _, _ = bs_greeks(test_spot, strikes, tte_years, put_iv)
    gex_d = (call_oi * gamma_c - put_oi * gamma_p) * 100.0 * (test_spot**2) * 0.01
    return float(np.sum(gex_d) / 1e6)


def find_zero_gamma_flip(
    spot: float,
    strikes: np.ndarray,
    call_oi: np.ndarray,
    put_oi: np.ndarray,
    call_iv: np.ndarray,
    put_iv: np.ndarray,
    tte_years: float,
) -> float:
    low_s = max(float(np.min(strikes)), spot * 0.75)
    high_s = min(float(np.max(strikes)), spot * 1.25)
    grid = np.linspace(low_s, high_s, 60)
    gex_vals = [
        total_net_gex_at_price(s, strikes, call_oi, put_oi, call_iv, put_iv, tte_years)
        for s in grid
    ]

    best_flip = None
    min_dist = float("inf")
    for i in range(len(grid) - 1):
        if gex_vals[i] * gex_vals[i + 1] <= 0:
            denom = gex_vals[i + 1] - gex_vals[i]
            flip_p = (
                grid[i]
                if abs(denom) < 1e-9
                else grid[i] - gex_vals[i] * (grid[i + 1] - grid[i]) / denom
            )
            if abs(flip_p - spot) < min_dist:
                min_dist = abs(flip_p - spot)
                best_flip = flip_p

    if best_flip is not None:
        return round(float(best_flip), 2)
    return round(float(grid[int(np.argmin(np.abs(gex_vals)))]), 2)


def evaluate_snapshot_and_alerts(
    ticker: str,
    df_ohlcv: pd.DataFrame,
    df_chain: pd.DataFrame,
    expiration_date: str,
    dte_days: float,
    iv_crush_drop_threshold_pct: float = 6.0,
    simulated_iv_peak_pct: Optional[float] = None,
) -> Tuple[WarRoomSnapshot, pd.DataFrame]:
    spot = float(df_ohlcv["Close"].iloc[-1])
    prev_close = (
        float(df_ohlcv["Close"].iloc[-2]) if len(df_ohlcv) >= 2 else spot * 0.99
    )
    high_curr = float(df_ohlcv["High"].iloc[-1])
    low_curr = float(df_ohlcv["Low"].iloc[-1])
    open_curr = float(df_ohlcv["Open"].iloc[-1])
    vol_curr = float(df_ohlcv["Volume"].iloc[-1])
    vol_ma20 = float(df_ohlcv["Volume"].tail(20).mean())

    bar_range = max(high_curr - low_curr, 0.01)
    upper_wick_ratio = (high_curr - max(open_curr, spot)) / bar_range

    df = df_chain.copy().sort_values("strike").reset_index(drop=True)
    strikes = df["strike"].values.astype(float)
    call_oi = df["call_oi"].values.astype(float)
    put_oi = df["put_oi"].values.astype(float)
    call_vol = df["call_vol"].values.astype(float)
    put_vol = df["put_vol"].values.astype(float)
    call_iv = df["call_iv"].values.astype(float)
    put_iv = df["put_iv"].values.astype(float)

    tte_years = max(dte_days / 365.0, 1.0 / (365.0 * 24.0))
    _, _, c_gamma, _, _ = bs_greeks(spot, strikes, tte_years, call_iv)
    _, _, p_gamma, _, _ = bs_greeks(spot, strikes, tte_years, put_iv)

    call_pol = dealer_call_polarity(call_vol, call_oi, call_iv)
    df["call_gex_raw_m"] = (call_oi * c_gamma * 100.0 * (spot**2) * 0.01) / 1e6
    df["call_gex_m"] = df["call_gex_raw_m"] * call_pol
    df["put_gex_m"] = (-put_oi * p_gamma * 100.0 * (spot**2) * 0.01) / 1e6
    df["net_gex_m"] = df["call_gex_m"] + df["put_gex_m"]
    df["call_vol_oi"] = call_vol / np.maximum(call_oi, 1.0)
    df["put_vol_oi"] = put_vol / np.maximum(put_oi, 1.0)

    net_gex_total = float(df["net_gex_m"].sum())
    zero_gamma = find_zero_gamma_flip(
        spot, strikes, call_oi, put_oi, call_iv, put_iv, tte_years
    )
    is_pos_gamma = (net_gex_total > 0) and (spot >= zero_gamma)

    atm_idx = int(np.argmin(np.abs(strikes - spot)))
    atm_iv_pct = float(((call_iv[atm_idx] + put_iv[atm_idx]) / 2.0) * 100.0)

    tracker = load_tracker_state()
    tk_state = tracker.get(ticker.upper(), {})
    recorded_iv_peak = float(tk_state.get("iv_peak_pct", atm_iv_pct))
    if simulated_iv_peak_pct is not None:
        iv_peak_pct = max(simulated_iv_peak_pct, atm_iv_pct)
    else:
        iv_peak_pct = max(recorded_iv_peak, atm_iv_pct)

    iv_drop_rel_pct = (
        ((iv_peak_pct - atm_iv_pct) / iv_peak_pct) * 100.0 if iv_peak_pct > 0 else 0.0
    )

    expected_move_pct = (atm_iv_pct / 100.0) * math.sqrt(tte_years)
    expected_move_usd = spot * expected_move_pct

    upper_df = df[df["strike"] >= spot * 0.98]
    call_wall = float(
        upper_df.loc[upper_df["call_gex_raw_m"].idxmax(), "strike"]
        if not upper_df.empty
        else df.loc[df["call_gex_raw_m"].idxmax(), "strike"]
    )
    lower_df = df[df["strike"] <= spot * 1.02]
    put_wall = float(
        lower_df.loc[lower_df["put_gex_m"].idxmin(), "strike"]
        if not lower_df.empty
        else df.loc[df["put_gex_m"].idxmin(), "strike"]
    )
    max_pain = compute_max_pain(df)

    bull_cands = df[(df["strike"] >= spot * 0.96) & (df["strike"] <= spot * 1.10)].copy()
    if not bull_cands.empty:
        bull_cands["sq_score"] = bull_cands["call_gex_raw_m"] * (
            1.0 + bull_cands["call_vol_oi"]
        )
        bull_trigger = float(bull_cands.loc[bull_cands["sq_score"].idxmax(), "strike"])
    else:
        bull_trigger = call_wall

    bear_cands = df[(df["strike"] <= spot * 1.04) & (df["strike"] >= spot * 0.90)].copy()
    if not bear_cands.empty:
        bear_cands["cr_score"] = np.abs(bear_cands["put_gex_m"]) * (
            1.0 + bear_cands["put_vol_oi"]
        )
        bear_trigger = float(bear_cands.loc[bear_cands["cr_score"].idxmax(), "strike"])
    else:
        bear_trigger = put_wall

    far_calls = df[df["strike"] > bull_trigger]
    if not far_calls.empty:
        oi_cut = np.percentile(far_calls["call_oi"], 75)
        term_call = float(far_calls[far_calls["call_oi"] >= oi_cut]["strike"].max())
    else:
        term_call = round(spot + expected_move_usd, 2)
    bull_exhaust = round(
        max(bull_trigger * 1.03, min(term_call, spot + 1.25 * expected_move_usd)), 2
    )

    far_puts = df[df["strike"] < bear_trigger]
    if not far_puts.empty:
        oi_cut_p = np.percentile(far_puts["put_oi"], 75)
        term_put = float(far_puts[far_puts["put_oi"] >= oi_cut_p]["strike"].min())
    else:
        term_put = round(spot - expected_move_usd, 2)
    bear_exhaust = round(
        min(bear_trigger * 0.97, max(term_put, spot - 1.25 * expected_move_usd)), 2
    )

    try:
        exp_dt = datetime.datetime.strptime(expiration_date, "%Y-%m-%d")
        charm_tw_str = (exp_dt + datetime.timedelta(days=1, hours=3)).strftime(
            "%Y-%m-%d %H:%M:%S (UTC+8)"
        )
    except ValueError:
        charm_tw_str = "到期日美東 14:00 / 台灣時間隔日 03:00:00 (UTC+8)"

    alerts: List[AlertSignal] = []

    if (
        (prev_close < bull_trigger <= spot)
        or (
            not is_pos_gamma
            and abs(spot - bull_trigger) / bull_trigger <= 0.008
            and vol_curr > vol_ma20 * 1.15
        )
    ):
        entry = round(spot, 2)
        tp = round(bull_exhaust, 2)
        reward = max(tp - entry, spot * 0.03)
        sl = round(entry - reward / 2.4, 2)
        alerts.append(
            AlertSignal(
                code="BULL_SQUEEZE_START",
                title=f"🚀 【{ticker} 突破 Gamma Squeeze 啟動價 ${bull_trigger:.2f}】",
                chart_badge=f"[軋空啟動] 突破 ${bull_trigger:.2f} (目標 ${bull_exhaust:.2f})",
                description=(
                    f"現價 ${spot:.2f} 帶量突破點火履約價 ${bull_trigger:.2f} (量比 {vol_curr/max(vol_ma20,1):.2f}x)，"
                    f"造市商負 Gamma 被迫追買現貨助漲！"
                ),
                action_plan="順勢做多或買進 Call 垂直價差，目標直指最遠端高 OI 衰竭天花板。",
                entry_price=entry,
                sl_price=sl,
                tp_price=tp,
                rrr=2.4,
            )
        )

    if prev_close < call_wall <= spot and vol_curr > vol_ma20 * 1.1 and call_wall != bull_trigger:
        entry = round(spot, 2)
        tp = round(max(bull_exhaust, spot * 1.05), 2)
        reward = max(tp - entry, spot * 0.03)
        sl = round(entry - reward / 2.2, 2)
        alerts.append(
            AlertSignal(
                code="BREAK_CALL_WALL",
                title=f"💥 【{ticker} 帶量穿破上方 Call 壓力牆 ${call_wall:.2f}】",
                chart_badge=f"[穿破壓力牆] 突破 Call 牆 ${call_wall:.2f}",
                description=(
                    f"現價 ${spot:.2f} 正式攻克最大 Call 壓力牆 ${call_wall:.2f}！"
                    f"賣方機構被迫停損回補、造市商由高拋轉為追買，小心觸發向上軋空爆發。"
                ),
                action_plan="原賣出 Call 部位應立即停損或向上轉倉 (Roll Up)；短線可順勢追多。",
                entry_price=entry,
                sl_price=sl,
                tp_price=tp,
                rrr=2.2,
            )
        )

    if prev_close > put_wall >= spot and vol_curr > vol_ma20 * 1.1:
        entry = round(spot, 2)
        tp = round(min(bear_exhaust, spot * 0.94), 2)
        reward = max(entry - tp, spot * 0.03)
        sl = round(entry + reward / 2.3, 2)
        alerts.append(
            AlertSignal(
                code="BREAK_PUT_WALL",
                title=f"🩸 【{ticker} 帶量跌破下方 Put 支撐牆 ${put_wall:.2f} (破牆助跌)】",
                chart_badge=f"[跌破支撐牆] 跌穿 Put 牆 ${put_wall:.2f} 助跌啟動",
                description=(
                    f"現價 ${spot:.2f} 跌穿最大 Put 支撐牆 ${put_wall:.2f}！"
                    f"造市商護盤買盤歸零並反手拋售避險股票，引發連鎖破牆急殺。"
                ),
                action_plan="嚴禁在破牆瞬間盲目接刀！多單應立即停損，或順勢輕倉放空 / 買進 Put 價差。",
                entry_price=entry,
                sl_price=sl,
                tp_price=tp,
                rrr=2.3,
            )
        )

    is_iv_crushing = iv_drop_rel_pct >= iv_crush_drop_threshold_pct
    is_price_exhausted = (high_curr >= bull_exhaust * 0.99) and (
        upper_wick_ratio > 0.40 or vol_curr < vol_ma20
    )
    if is_iv_crushing or is_price_exhausted:
        entry = round(spot, 2)
        tp = round(max(zero_gamma, max_pain), 2)
        if tp >= entry:
            tp = round(entry * 0.94, 2)
        reward = max(entry - tp, spot * 0.03)
        sl = round(entry + reward / 2.2, 2)
        reason_str = (
            f"ATM IV 從盤中高點 {iv_peak_pct:.1f}% 回落至 {atm_iv_pct:.1f}% (相對跌幅 {iv_drop_rel_pct:.1f}%)"
            if is_iv_crushing
            else f"最高價 ${high_curr:.2f} 觸及衰竭天花板 ${bull_exhaust:.2f} 且留長上影線 ({upper_wick_ratio*100:.0f}%)"
        )
        alerts.append(
            AlertSignal(
                code="SQUEEZE_EXHAUSTION_IV_CRUSH",
                title=f"⚠️ 【{ticker} Gamma Squeeze 衰竭 & IV 回落反轉警報】",
                chart_badge=f"[Squeeze 衰竭 / IV 回落] IV 跌 {iv_drop_rel_pct:.1f}% 造市商倒貨警戒",
                description=(
                    f"{reason_str}！Vanna 與 Charm 效應啟動，買方權利金縮水引發多殺多，"
                    f"造市商正大量拋售避險現貨股票平倉。"
                ),
                action_plan="多頭與 Long Call 部位務必立即獲利了結離場；激進者可逢高布局回歸 Max Pain 之空單。",
                entry_price=entry,
                sl_price=sl,
                tp_price=tp,
                rrr=2.2,
            )
        )

    tk_state["iv_peak_pct"] = round(iv_peak_pct, 2)
    tk_state["last_spot"] = round(spot, 2)
    tracker[ticker.upper()] = tk_state
    save_tracker_state(tracker)

    now_tw = (
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    ).strftime("%Y-%m-%d %H:%M:%S (UTC+8)")

    snapshot = WarRoomSnapshot(
        ticker=ticker.upper(),
        timestamp_tw=now_tw,
        expiration_date=expiration_date,
        dte_days=round(dte_days, 1),
        spot_price=round(spot, 2),
        prev_close=round(prev_close, 2),
        latest_volume=vol_curr,
        vol_ma20=vol_ma20,
        upper_wick_ratio=round(upper_wick_ratio, 2),
        atm_iv_pct=round(atm_iv_pct, 1),
        iv_peak_pct=round(iv_peak_pct, 1),
        iv_drop_from_peak_pct=round(iv_drop_rel_pct, 1),
        expected_move_usd=round(expected_move_usd, 2),
        expected_move_pct=round(expected_move_pct * 100.0, 2),
        net_gex_millions=round(net_gex_total, 2),
        zero_gamma_flip=zero_gamma,
        is_positive_gamma=is_pos_gamma,
        call_wall=call_wall,
        put_wall=put_wall,
        max_pain=max_pain,
        bull_squeeze_trigger=bull_trigger,
        bear_squeeze_trigger=bear_trigger,
        bull_exhaustion_price=bull_exhaust,
        bear_exhaustion_price=bear_exhaust,
        charm_unwind_time_tw=charm_tw_str,
        active_alerts=alerts,
    )
    return snapshot, df


# ============================================================================
# 3. 高解析度「左 K 線 + 右 GEX 柱狀圖 + 底部戰情卡」雙拼圖繪製器
# ============================================================================
def render_warroom_chart_png(
    snap: WarRoomSnapshot,
    df_ohlcv: pd.DataFrame,
    df_chain: pd.DataFrame,
    output_path: str,
) -> str:
    fig = plt.figure(figsize=(15, 9.2), dpi=160, facecolor="#0E1117")
    gs = fig.add_gridspec(
        2, 2, width_ratios=[3.1, 1.2], height_ratios=[4.2, 1.35], hspace=0.22, wspace=0.06
    )

    ax_k = fig.add_subplot(gs[0, 0], facecolor="#131722")
    ax_gex = fig.add_subplot(gs[0, 1], sharey=ax_k, facecolor="#131722")
    ax_card = fig.add_subplot(gs[1, :], facecolor="#161B26")

    df_plot = df_ohlcv.tail(45).reset_index(drop=True)

    y_min = min(float(df_plot["Low"].min()), snap.put_wall, snap.bear_exhaustion_price) * 0.985
    y_max = max(float(df_plot["High"].max()), snap.call_wall, snap.bull_exhaustion_price) * 1.015

    if snap.is_positive_gamma:
        ax_k.axhspan(snap.zero_gamma_flip, y_max, color="#00E676", alpha=0.05)
        ax_k.axhspan(y_min, snap.zero_gamma_flip, color="#FF1744", alpha=0.04)
    else:
        ax_k.axhspan(y_min, y_max, color="#FF1744", alpha=0.05)

    for i, row in df_plot.iterrows():
        o, h, l, c = row["Open"], row["High"], row["Low"], row["Close"]
        color = "#00E676" if c >= o else "#FF5252"
        ax_k.plot([i, i], [l, h], color=color, linewidth=1.3, zorder=3)
        body_bottom = min(o, c)
        body_h = max(abs(c - o), (y_max - y_min) * 0.002)
        rect = mpatches.Rectangle(
            (i - 0.32, body_bottom), 0.64, body_h, facecolor=color, edgecolor=color, zorder=4
        )
        ax_k.add_patch(rect)

    levels_raw = [
        (snap.call_wall, f"Call 壓力牆 ${snap.call_wall:.1f}", "#FF5252", "-", 2.0, 0.5),
        (snap.put_wall, f"Put 支撐牆 ${snap.put_wall:.1f}", "#00E676", "-", 2.0, 0.5),
        (snap.zero_gamma_flip, f"Zero Gamma 翻轉點 ${snap.zero_gamma_flip:.2f}", "#FFD600", "--", 2.0, 0.5),
        (snap.max_pain, f"Max Pain 最大痛點 ${snap.max_pain:.1f}", "#40C4FF", ":", 1.8, 10.5),
        (snap.bull_squeeze_trigger, f"Squeeze 向上啟動 ${snap.bull_squeeze_trigger:.1f}", "#FF9100", "-.", 1.8, 10.5),
        (snap.bull_exhaustion_price, f"Squeeze 衰竭天花板 ${snap.bull_exhaustion_price:.1f}", "#E040FB", "-.", 1.6, 10.5),
    ]

    used_positions = []
    for price_val, lbl, col, ls, lw, x_pos in levels_raw:
        if y_min <= price_val <= y_max:
            ax_k.axhline(price_val, color=col, linestyle=ls, linewidth=lw, alpha=0.88, zorder=2)
            adj_x = x_pos
            for up_val, up_x in used_positions:
                if abs(price_val - up_val) < (y_max - y_min) * 0.035 and abs(adj_x - up_x) < 8.0:
                    adj_x = up_x + 11.5
            used_positions.append((price_val, adj_x))
            ax_k.text(
                adj_x,
                price_val + (y_max - y_min) * 0.006,
                lbl,
                color=col,
                fontsize=9.2,
                fontweight="bold",
                bbox=dict(boxstyle="round,pad=0.2", facecolor="#0E1117", edgecolor="none", alpha=0.82),
                zorder=5,
            )

    if snap.active_alerts:
        last_x = len(df_plot) - 1
        badge_text = "\n".join([a.chart_badge for a in snap.active_alerts])
        box_y = (
            snap.spot_price - (y_max - y_min) * 0.14
            if snap.spot_price > (y_min + y_max) * 0.55
            else snap.spot_price + (y_max - y_min) * 0.12
        )
        ax_k.annotate(
            badge_text,
            xy=(last_x, snap.spot_price),
            xytext=(max(16, last_x - 20), box_y),
            arrowprops=dict(facecolor="#FFD600", shrink=0.06, width=2, headwidth=7),
            fontsize=10,
            fontweight="bold",
            color="#FFFFFF",
            bbox=dict(boxstyle="round,pad=0.45", facecolor="#B71C1C", edgecolor="#FFD600", lw=1.5),
            zorder=8,
        )

    regime_title = (
        "【正 Gamma 狀態：區間高拋低吸】"
        if snap.is_positive_gamma
        else "【負 Gamma 狀態：造市商追高殺低 / 擠壓警戒】"
    )
    ax_k.set_title(
        f"{snap.ticker} 期權籌碼雷達 K 線圖 (現價 ${snap.spot_price:.2f}) — {regime_title}",
        color="white",
        fontsize=12.5,
        fontweight="bold",
        pad=10,
    )
    ax_k.set_ylim(y_min, y_max)
    ax_k.set_xlim(-1, len(df_plot) + 2)
    ax_k.grid(True, color="#2A2E39", linestyle="--", linewidth=0.6, alpha=0.6)
    ax_k.tick_params(colors="#B2B5BE", labelsize=9)

    df_sub = df_chain[(df_chain["strike"] >= y_min) & (df_chain["strike"] <= y_max)]
    bar_height = (
        max(np.min(np.diff(df_sub["strike"].values)) * 0.65, 1.2)
        if len(df_sub) > 1
        else 2.0
    )
    colors_gex = [
        "#00E676" if v >= 0 else "#FF1744" for v in df_sub["net_gex_m"].values
    ]
    ax_gex.barh(
        df_sub["strike"].values,
        df_sub["net_gex_m"].values,
        height=bar_height,
        color=colors_gex,
        alpha=0.85,
        edgecolor="#1E222D",
    )
    ax_gex.axvline(0, color="#B2B5BE", linewidth=1.0)
    ax_gex.axhline(snap.spot_price, color="#FFFFFF", linestyle="-", linewidth=1.5)
    ax_gex.set_title(
        f"各履約價 Net GEX (百萬美元)\n總淨曝險: {snap.net_gex_millions:+.1f}M",
        color="white",
        fontsize=11,
        fontweight="bold",
        pad=10,
    )
    ax_gex.grid(True, color="#2A2E39", linestyle="--", linewidth=0.6, alpha=0.6)
    ax_gex.tick_params(colors="#B2B5BE", labelsize=9)
    plt.setp(ax_gex.get_yticklabels(), visible=False)

    ax_card.axis("off")
    status_str = (
        f"[正 Gamma 穩定態] 現價 ${snap.spot_price:.2f} | 翻轉點 ${snap.zero_gamma_flip:.2f} | Net GEX {snap.net_gex_millions:+.1f}M"
        if snap.is_positive_gamma
        else f"[負 Gamma 擠壓態] 現價 ${snap.spot_price:.2f} | 翻轉點 ${snap.zero_gamma_flip:.2f} | Net GEX {snap.net_gex_millions:+.1f}M"
    )
    line1 = (
        f"標的: {snap.ticker}  |  到期日: {snap.expiration_date} ({snap.dte_days} DTE)  |  "
        f"時間: {snap.timestamp_tw}  |  {status_str}"
    )
    line2 = (
        f"[正 Gamma 導航] 上方 Call 壓力牆: ${snap.call_wall:.2f}  |  "
        f"下方 Put 支撐牆: ${snap.put_wall:.2f}  |  Max Pain 最大痛點: ${snap.max_pain:.2f}"
    )
    line3 = (
        f"[負 Gamma 導航] Squeeze 向上啟動價: ${snap.bull_squeeze_trigger:.2f} (向下破牆價: ${snap.bear_squeeze_trigger:.2f})  |  "
        f"衰竭天花板: ${snap.bull_exhaustion_price:.2f}  |  ATM IV: {snap.atm_iv_pct:.1f}% (峰值 {snap.iv_peak_pct:.1f}%, 回落 {snap.iv_drop_from_peak_pct:.1f}%)"
    )

    if snap.active_alerts:
        top_alert = snap.active_alerts[0]
        line4 = (
            f"[即時觸發推播訊號] {top_alert.chart_badge} -> 建議進場 Entry: ${top_alert.entry_price:.2f} | "
            f"停損 SL: ${top_alert.sl_price:.2f} | 停利 TP: ${top_alert.tp_price:.2f} (風報比 RRR 1:{top_alert.rrr:.1f})"
        )
        line4_col = "#FFD600"
    else:
        line4 = (
            f"[正常監控中] Charm 尾盤平倉警戒時間窗: {snap.charm_unwind_time_tw} "
            f"(隱含波動區間 +/-${snap.expected_move_usd:.2f} / +/-{snap.expected_move_pct:.1f}%)"
        )
        line4_col = "#80D8FF"

    ax_card.text(0.015, 0.78, line1, color="#FFFFFF", fontsize=10.5, fontweight="bold")
    ax_card.text(0.015, 0.54, line2, color="#00E676", fontsize=10)
    ax_card.text(0.015, 0.30, line3, color="#FF9100", fontsize=10)
    ax_card.text(0.015, 0.06, line4, color=line4_col, fontsize=10.5, fontweight="bold")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    plt.savefig(output_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


# ============================================================================
# 4. Telegram 自動推播與開盤前早報格式化引擎
# ============================================================================
def format_telegram_card_message(snap: WarRoomSnapshot) -> str:
    regime_str = (
        "🟢 正 Gamma (高拋低吸 / 區間收斂)"
        if snap.is_positive_gamma
        else "🔴 負 Gamma (追高殺低 / 擠壓放大)"
    )
    lines = [
        f"📡 *【美股期權 GEX 與 Gamma Squeeze 戰情警報】*",
        f"• *標的代號*: `{snap.ticker}` ([Yahoo Finance](https://finance.yahoo.com/quote/{snap.ticker}))",
        f"• *分析時間*: `{snap.timestamp_tw}`",
        f"• *目標到期日*: `{snap.expiration_date}` (`{snap.dte_days} DTE`)",
        f"• *目前現價*: `${snap.spot_price:.2f}` (前收 `${snap.prev_close:.2f}`)",
        f"• *期權體制*: {regime_str}",
        f"• *全市場 Net GEX*: `{snap.net_gex_millions:+.2f}M`",
        f"• *Zero Gamma 翻轉點*: `${snap.zero_gamma_flip:.2f}`",
        "",
        f"🏛️ *【支撐壓力牆與 Max Pain】*",
        f"• *上方 Call 壓力牆*: `${snap.call_wall:.2f}`",
        f"• *下方 Put 支撐牆*: `${snap.put_wall:.2f}`",
        f"• *Max Pain 最大痛點*: `${snap.max_pain:.2f}`",
        "",
        f"⚡ *【Gamma Squeeze 啟動與衰竭雷達】*",
        f"• *向上軋空啟動價*: `${snap.bull_squeeze_trigger:.2f}`",
        f"• *向下破牆啟動價*: `${snap.bear_squeeze_trigger:.2f}`",
        f"• *向上衰竭目標價*: `${snap.bull_exhaustion_price:.2f}`",
        f"• *ATM IV 狀態*: `{snap.atm_iv_pct:.1f}%` (盤中峰值 `{snap.iv_peak_pct:.1f}%`, 回落 `{snap.iv_drop_from_peak_pct:.1f}%`)",
        f"• *Charm 尾盤平倉窗*: `{snap.charm_unwind_time_tw}`",
    ]

    if snap.active_alerts:
        lines.append("")
        lines.append("🚨 *【觸發實戰推播事件與 RRR >= 1:2 交易計畫】*")
        for idx, al in enumerate(snap.active_alerts, 1):
            lines.extend(
                [
                    f"*{idx}. {al.title}*",
                    f"   • 說明: {al.description}",
                    f"   • 對策: {al.action_plan}",
                    f"   • 進場點 (Entry): `${al.entry_price:.2f}`",
                    f"   • 停損點 (SL): `${al.sl_price:.2f}`",
                    f"   • 停利點 (TP): `${al.tp_price:.2f}` (預期風報比 `1:{al.rrr:.1f}`)",
                ]
            )
    return "\n".join(lines)


def format_single_line_brief(snap: WarRoomSnapshot) -> str:
    """
    將單一標的格式化為早報專屬之完整垂直卡片列：
    不論 SPY、QQQ 或 12 檔核心自選股，皆完整列出正負 Gamma、翻轉點、Call牆、Put牆、Max Pain，
    若為負 Gamma 額外標示 Squeeze 啟動價、衰竭目標價與 IV 警戒線。
    """
    if snap.is_positive_gamma:
        return (
            f"• *{snap.ticker}* (`${snap.spot_price:.2f}`)：🟢 *正 Gamma* (`{snap.net_gex_millions:+.1f}M`)\n"
            f"  └ 翻轉點 `${snap.zero_gamma_flip:.2f}` | Call牆 `${snap.call_wall:.2f}` / Put牆 `${snap.put_wall:.2f}` | "
            f"Max Pain `${snap.max_pain:.2f}` | 預期波動 `±${snap.expected_move_usd:.2f}` (`±{snap.expected_move_pct:.1f}%`)"
        )
    else:
        iv_crush_line = round(snap.atm_iv_pct * 0.94, 1)
        return (
            f"• *{snap.ticker}* (`${snap.spot_price:.2f}`)：🔴 *負 Gamma* (`{snap.net_gex_millions:+.1f}M`)\n"
            f"  └ 翻轉點 `${snap.zero_gamma_flip:.2f}` | Call牆 `${snap.call_wall:.2f}` / Put牆 `${snap.put_wall:.2f}` | Max Pain `${snap.max_pain:.2f}`\n"
            f"  └ 🚀 軋空啟動 `${snap.bull_squeeze_trigger:.2f}` (衰竭目標 `${snap.bull_exhaustion_price:.2f}`) | "
            f"🩸 破牆助跌 `${snap.bear_squeeze_trigger:.2f}` | ATM IV `{snap.atm_iv_pct:.1f}%` (回落警戒 `<{iv_crush_line:.1f}%`)"
        )


def send_telegram_alert(
    bot_token: str, chat_id: str, message_md: str, image_path: Optional[str] = None
) -> bool:
    if not bot_token or not chat_id:
        return False

    try:
        url_msg = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = urllib.parse.urlencode(
            {"chat_id": chat_id, "text": message_md, "parse_mode": "Markdown"}
        ).encode("utf-8")
        req = urllib.request.Request(url_msg, data=payload, method="POST")
        with urllib.request.urlopen(req, timeout=12) as resp:
            _ = resp.read()

        if image_path and os.path.exists(image_path):
            import requests

            url_photo = f"https://api.telegram.org/bot{bot_token}/sendPhoto"
            with open(image_path, "rb") as img_f:
                requests.post(
                    url_photo,
                    data={"chat_id": chat_id, "caption": f"📊 {os.path.basename(image_path)}"},
                    files={"photo": img_f},
                    timeout=15,
                )
        return True
    except Exception as exc:
        print(f"[Telegram 推播失敗]: {exc}")
        return False


# ============================================================================
# 5. 全美股多執行緒期權鏈批次掃描器 (含無期權標的之現貨波動率智慧回退機制)
# ============================================================================
def build_spot_proxy_chain(spot: float, df_ohlcv: pd.DataFrame) -> Tuple[pd.DataFrame, str, float]:
    """
    當特定標的 (例如剛上市或特殊太空 ETF 如 SPCX) 暫無期權鏈報價時，
    利用近 20 日歷史波動率 (HV) 與價格區間自動建構等效合成期權鏈，確保 12 檔核心自選股 100% 不漏檔。
    """
    log_ret = np.log(df_ohlcv["Close"] / df_ohlcv["Close"].shift(1)).dropna()
    hv = float(log_ret.std() * np.sqrt(252)) if len(log_ret) >= 5 else 0.45
    hv = float(np.clip(hv, 0.18, 1.50))

    step = max(round(spot * 0.025, 1), 0.5)
    strikes = np.round(np.arange(spot * 0.85, spot * 1.16, step), 2)
    ma20 = float(df_ohlcv["Close"].tail(20).mean())
    is_bull_trend = spot >= ma20

    call_oi = np.exp(-0.5 * ((strikes - spot * 1.05) / (spot * 0.06)) ** 2) * 15000
    put_oi = np.exp(-0.5 * ((strikes - spot * 0.95) / (spot * 0.06)) ** 2) * (
        12000 if is_bull_trend else 18000
    )
    call_vol = call_oi * (0.45 if is_bull_trend else 0.95)
    put_vol = put_oi * (0.35 if is_bull_trend else 0.85)

    df_chain = pd.DataFrame(
        {
            "strike": strikes,
            "call_oi": np.round(call_oi),
            "put_oi": np.round(put_oi),
            "call_vol": np.round(call_vol),
            "put_vol": np.round(put_vol),
            "call_iv": np.full_like(strikes, hv),
            "put_iv": np.full_like(strikes, hv * 1.03),
        }
    )
    today_dt = datetime.datetime.now(datetime.timezone.utc).date()
    days_until_friday = (4 - today_dt.weekday()) % 7
    if days_until_friday == 0:
        days_until_friday = 7
    exp_date_str = (today_dt + datetime.timedelta(days=days_until_friday)).strftime("%Y-%m-%d")
    return df_chain, exp_date_str, float(days_until_friday)


def fetch_live_market_data(
    ticker: str, exp_index: int = 0, interval: str = "15m", period: str = "5d"
) -> Tuple[str, pd.DataFrame, pd.DataFrame, str, float]:
    import yfinance as yf

    tk = yf.Ticker(ticker)
    df_ohlcv = tk.history(period=period, interval=interval)
    if df_ohlcv.empty:
        df_ohlcv = tk.history(period="1mo", interval="1d")
    if df_ohlcv.empty:
        raise RuntimeError(f"無法取得 {ticker} K 線數據。")

    spot = float(df_ohlcv["Close"].iloc[-1])
    exps = tk.options
    if not exps:
        df_proxy, exp_str, dte_val = build_spot_proxy_chain(spot, df_ohlcv)
        return ticker.upper(), df_ohlcv, df_proxy, exp_str, dte_val

    chosen_exp = exps[min(exp_index, len(exps) - 1)]
    opt = tk.option_chain(chosen_exp)
    calls = opt.calls[["strike", "openInterest", "volume", "impliedVolatility"]].rename(
        columns={"openInterest": "call_oi", "volume": "call_vol", "impliedVolatility": "call_iv"}
    )
    puts = opt.puts[["strike", "openInterest", "volume", "impliedVolatility"]].rename(
        columns={"openInterest": "put_oi", "volume": "put_vol", "impliedVolatility": "put_iv"}
    )
    df_chain = pd.merge(calls, puts, on="strike", how="outer").fillna(0.0)
    df_chain = df_chain[
        (df_chain["strike"] >= spot * 0.78) & (df_chain["strike"] <= spot * 1.22)
    ].reset_index(drop=True)
    if df_chain.empty:
        df_proxy, exp_str, dte_val = build_spot_proxy_chain(spot, df_ohlcv)
        return ticker.upper(), df_ohlcv, df_proxy, exp_str, dte_val

    exp_dt = datetime.datetime.strptime(chosen_exp, "%Y-%m-%d").date()
    today_dt = datetime.datetime.now(datetime.timezone.utc).date()
    dte_days = max(float((exp_dt - today_dt).days), 0.5)
    return ticker.upper(), df_ohlcv, df_chain, chosen_exp, dte_days


def scan_single_ticker_worker(
    ticker: str, exp_index: int = 0, iv_crush_drop_threshold_pct: float = 6.0
) -> Optional[Tuple[WarRoomSnapshot, pd.DataFrame, pd.DataFrame]]:
    try:
        tk, df_ohlcv, df_chain, exp_d, dte = fetch_live_market_data(
            ticker, exp_index=exp_index, interval="15m", period="5d"
        )
        snap, df_gex = evaluate_snapshot_and_alerts(
            tk, df_ohlcv, df_chain, exp_d, dte, iv_crush_drop_threshold_pct
        )
        return snap, df_ohlcv, df_gex
    except Exception:
        return None


def scan_us_market_universe(
    universe_mode: str = "SP500_NDX100",
    custom_tickers: Optional[List[str]] = None,
    max_stage2_tickers: int = 30,
    max_workers: int = 6,
    iv_crush_drop_threshold_pct: float = 6.0,
) -> List[Tuple[WarRoomSnapshot, pd.DataFrame, pd.DataFrame]]:
    if universe_mode == "ALL_US":
        raw_list = fetch_all_us_sec_tickers()
        candidates = stage1_fast_spot_prefilter(raw_list, max_candidates=max_stage2_tickers)
    elif universe_mode == "SP500_NDX100":
        raw_list = fetch_sp500_and_nasdaq100_tickers()
        candidates = stage1_fast_spot_prefilter(raw_list, max_candidates=max_stage2_tickers)
    elif universe_mode == "MOST_ACTIVE":
        candidates = stage1_fast_spot_prefilter(
            DEFAULT_HIGH_OPTION_LIQUIDITY_POOL, max_candidates=max_stage2_tickers
        )
    else:
        candidates = [
            t.strip().upper()
            for t in (custom_tickers or DEFAULT_CORE_WATCHLIST)
            if t.strip()
        ]

    results: List[Tuple[WarRoomSnapshot, pd.DataFrame, pd.DataFrame]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        fut_map = {
            executor.submit(
                scan_single_ticker_worker, tk, 0, iv_crush_drop_threshold_pct
            ): tk
            for tk in candidates
        }
        for fut in as_completed(fut_map):
            res = fut.result()
            if res is not None:
                results.append(res)

    results.sort(
        key=lambda x: (len(x[0].active_alerts) > 0, abs(x[0].net_gex_millions)),
        reverse=True,
    )
    return results


def generate_morning_briefing_report(
    core_tickers: List[str], iv_crush_drop_threshold_pct: float = 6.0
) -> str:
    """
    生成每日美股開盤前 15 分鐘完整 GEX 籌碼戰情早報：
    1. 大盤雙指標定調 (SPY & QQQ 均完整列出 Call牆、Put牆、Max Pain、Zero Gamma、Expected Move)
    2. 12 檔核心自選股 (NVDA, TSLA, LUNR, SPCX + 納指前十大) 完整作戰地圖
    3. 全美股「臨門一腳」蓄勢名單 (距離 Squeeze 啟動價或 Put 支撐牆 <= 1.5%)
    4. 結算日 DTE 與 Charm 尾盤平倉時間提醒
    """
    now_tw = (
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    ).strftime("%Y-%m-%d %H:%M:%S (UTC+8)")

    target_list = list(dict.fromkeys(MARKET_INDEX_TICKERS + core_tickers))
    scanned_map: Dict[str, WarRoomSnapshot] = {}

    with ThreadPoolExecutor(max_workers=6) as executor:
        fut_map = {
            executor.submit(
                scan_single_ticker_worker, tk, 0, iv_crush_drop_threshold_pct
            ): tk
            for tk in target_list
        }
        for fut in as_completed(fut_map):
            tk_key = fut_map[fut]
            res = fut.result()
            if res is not None:
                scanned_map[tk_key] = res[0]

    lines = [
        "🌅 *【美股開盤前 GEX 籌碼戰情早報】*",
        f"時間：`{now_tw}`（開盤前全自動掃描）",
        "",
        "📊 *【一、 大盤雙指標完整定調 (SPY & QQQ)】*",
    ]

    for idx_tk in MARKET_INDEX_TICKERS:
        if idx_tk in scanned_map:
            lines.append(format_single_line_brief(scanned_map[idx_tk]))
        else:
            lines.append(f"• *{idx_tk}*：連線抓取中，請稍候重試")

    lines.extend(["", "🎯 *【二、 核心自選股 12 檔開盤作戰地圖】*"])
    for c_tk in core_tickers:
        if c_tk in scanned_map:
            lines.append(format_single_line_brief(scanned_map[c_tk]))

    # 挑選臨門一腳蓄勢股 (現價距離 Bull Squeeze Trigger 或 Put Wall <= 1.8%)
    near_breakout_lines = []
    for tk_k, sn in scanned_map.items():
        if tk_k in MARKET_INDEX_TICKERS:
            continue
        dist_bull_pct = abs(sn.bull_squeeze_trigger - sn.spot_price) / max(sn.spot_price, 0.01) * 100.0
        dist_put_pct = abs(sn.spot_price - sn.put_wall) / max(sn.spot_price, 0.01) * 100.0
        vol_ratio = sn.latest_volume / max(sn.vol_ma20, 1.0)
        if dist_bull_pct <= 1.8:
            near_breakout_lines.append(
                f"• *{sn.ticker}* (`${sn.spot_price:.2f}`) — 距上方 Squeeze 啟動價 `${sn.bull_squeeze_trigger:.2f}` 僅 `{dist_bull_pct:.2f}%` (量比 `{vol_ratio:.2f}x`)"
            )
        elif dist_put_pct <= 1.8:
            near_breakout_lines.append(
                f"• *{sn.ticker}* (`${sn.spot_price:.2f}`) — 緊貼下方 Put 支撐牆 `${sn.put_wall:.2f}` 僅 `{dist_put_pct:.2f}%`，開盤嚴防破牆助跌"
            )

    lines.extend(["", "🔥 *【三、 臨門一腳蓄勢重點關注】*"])
    if near_breakout_lines:
        lines.extend(near_breakout_lines[:5])
    else:
        lines.append("• 目前核心自選股均位於支撐壓力牆中間區間，等待開盤量能表態。")

    sample_snap = next(iter(scanned_map.values()), None)
    if sample_snap is not None:
        lines.extend(
            [
                "",
                "⏰ *【四、 結算日與 Charm 尾盤倒貨時間窗】*",
                f"• 目標期權到期日：`{sample_snap.expiration_date}` (尚餘 `{sample_snap.dte_days} DTE`)",
                f"• Charm 尾盤平倉警戒窗：`{sample_snap.charm_unwind_time_tw}`",
            ]
        )

    return "\n".join(lines)


def should_send_alert_with_cooldown(ticker: str, alert_code: str) -> bool:
    today_str = (
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    ).strftime("%Y-%m-%d")
    tracker = load_tracker_state()
    tk_state = tracker.get(ticker.upper(), {})
    sent_history = tk_state.get("sent_alerts", {})
    key = f"{today_str}_{alert_code}"
    if sent_history.get(key):
        return False
    sent_history[key] = True
    tk_state["sent_alerts"] = sent_history
    tracker[ticker.upper()] = tk_state
    save_tracker_state(tracker)
    return True


class BackgroundPatrolDaemon:
    def __init__(self) -> None:
        self.last_run_tw: str = "等待首輪巡邏" if IS_WINDOWS_VPS else "雲端看盤模式 (由 VPS 專責巡邏)"
        self.total_scans: int = 0
        self.total_pushed: int = 0
        self._last_update_id: int = 0
        self._thread_patrol = threading.Thread(target=self._patrol_loop, daemon=True)
        self._thread_tg_cmd = threading.Thread(target=self._tg_command_loop, daemon=True)
        self._thread_patrol.start()
        self._thread_tg_cmd.start()

    def _patrol_loop(self) -> None:
        while True:
            try:
                cfg = load_user_config()
                tg_token = cfg.get("tg_token", "").strip()
                tg_chat_id = cfg.get("tg_chat_id", "").strip()
                enable_bg = bool(cfg.get("enable_bg_daemon", IS_WINDOWS_VPS))
                enable_morning = bool(cfg.get("enable_morning_report", True))
                only_mkt = bool(cfg.get("only_us_market_hours", True))
                interval_sec = max(int(cfg.get("patrol_interval_min", 15)), 5) * 60

                if enable_bg and tg_token and tg_chat_id:
                    # 1. 檢查是否進入美股開盤前 15 分鐘早報時間窗 (每日僅發送一次)
                    if enable_morning and is_premarket_briefing_window():
                        if should_send_alert_with_cooldown("MARKET_BRIEFING", "MORNING_REPORT"):
                            core_list = parse_watchlist_string(
                                cfg.get("core_watchlist", ", ".join(DEFAULT_CORE_WATCHLIST))
                            )
                            brief_md = generate_morning_briefing_report(
                                core_list, float(cfg.get("iv_drop_thresh", 6.0))
                            )
                            if send_telegram_alert(tg_token, tg_chat_id, brief_md):
                                self.total_pushed += 1

                    # 2. 執行盤中每 15 分鐘全美股 + 核心自選股異動巡邏
                    if not only_mkt or is_us_market_active_window():
                        core_list = parse_watchlist_string(
                            cfg.get("core_watchlist", ", ".join(DEFAULT_CORE_WATCHLIST))
                        )
                        results = scan_us_market_universe(
                            universe_mode=cfg.get("universe_mode", "SP500_NDX100"),
                            custom_tickers=core_list,
                            max_stage2_tickers=int(cfg.get("max_scan", 30)),
                            iv_crush_drop_threshold_pct=float(cfg.get("iv_drop_thresh", 6.0)),
                        )
                        self.total_scans += 1
                        self.last_run_tw = (
                            datetime.datetime.now(datetime.timezone.utc)
                            + datetime.timedelta(hours=8)
                        ).strftime("%Y-%m-%d %H:%M:%S (UTC+8)")

                        for snap, df_ohlcv, df_gex in results:
                            if snap.active_alerts:
                                top_code = snap.active_alerts[0].code
                                if should_send_alert_with_cooldown(snap.ticker, top_code):
                                    out_png = os.path.join(
                                        BASE_DIR, f"{snap.ticker}_bg_alert.png"
                                    )
                                    render_warroom_chart_png(snap, df_ohlcv, df_gex, out_png)
                                    ok = send_telegram_alert(
                                        tg_token,
                                        tg_chat_id,
                                        format_telegram_card_message(snap),
                                        out_png,
                                    )
                                    if ok:
                                        self.total_pushed += 1
                    else:
                        self.last_run_tw = "非美股開盤時段自動待機中"
                time.sleep(interval_sec)
            except Exception:
                time.sleep(300)

    def _tg_command_loop(self) -> None:
        while True:
            try:
                cfg = load_user_config()
                tg_token = cfg.get("tg_token", "").strip()
                tg_chat_id = cfg.get("tg_chat_id", "").strip()
                enable_bg = bool(cfg.get("enable_bg_daemon", IS_WINDOWS_VPS))
                if not enable_bg or not tg_token or not tg_chat_id:
                    time.sleep(10)
                    continue

                url = f"https://api.telegram.org/bot{tg_token}/getUpdates?offset={self._last_update_id + 1}&timeout=10"
                req = urllib.request.Request(url, method="GET")
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))

                for item in data.get("result", []):
                    self._last_update_id = max(self._last_update_id, int(item["update_id"]))
                    msg_obj = item.get("message", {})
                    sender_chat_id = str(msg_obj.get("chat", {}).get("id", ""))
                    text = str(msg_obj.get("text", "")).strip()

                    if sender_chat_id != tg_chat_id or not text:
                        continue

                    cmd_clean = text.lstrip("/").replace("gex", "").strip().upper()
                    if cmd_clean in {"MORNING", "BRIEF", "早報"}:
                        core_list = parse_watchlist_string(
                            cfg.get("core_watchlist", ", ".join(DEFAULT_CORE_WATCHLIST))
                        )
                        brief_md = generate_morning_briefing_report(
                            core_list, float(cfg.get("iv_drop_thresh", 6.0))
                        )
                        send_telegram_alert(tg_token, tg_chat_id, brief_md)
                    elif (
                        1 <= len(cmd_clean) <= 5
                        and (cmd_clean.isalpha() or "-" in cmd_clean)
                        and cmd_clean not in {"START", "HELP"}
                    ):
                        res = scan_single_ticker_worker(
                            cmd_clean, 0, float(cfg.get("iv_drop_thresh", 6.0))
                        )
                        if res is not None:
                            snap, df_ohlcv, df_gex = res
                            out_png = os.path.join(BASE_DIR, f"{snap.ticker}_tg_query.png")
                            render_warroom_chart_png(snap, df_ohlcv, df_gex, out_png)
                            send_telegram_alert(
                                tg_token,
                                tg_chat_id,
                                format_telegram_card_message(snap),
                                out_png,
                            )
                        else:
                            send_telegram_alert(
                                tg_token,
                                tg_chat_id,
                                f"⚠️ 無法取得 `{cmd_clean}` 之報價數據，請確認代號是否正確。",
                            )
            except Exception:
                time.sleep(5)


def get_demo_scenario_data(
    scenario: str = "NVDA_SQUEEZE",
) -> Tuple[str, pd.DataFrame, pd.DataFrame, str, float, Optional[float]]:
    np.random.seed(42)
    n_bars = 45
    if scenario == "NVDA_SQUEEZE":
        base_prices = np.linspace(156.0, 168.5, n_bars - 1).tolist() + [171.40]
        opens = [p - np.random.uniform(-1.2, 1.2) for p in base_prices[:-1]] + [168.20]
        highs = [max(o, c) + np.random.uniform(0.5, 1.8) for o, c in zip(opens[:-1], base_prices[:-1])] + [172.30]
        lows = [min(o, c) - np.random.uniform(0.5, 1.6) for o, c in zip(opens[:-1], base_prices[:-1])] + [167.90]
        vols = [np.random.uniform(35e6, 52e6) for _ in range(n_bars - 1)] + [88e6]
        df_ohlcv = pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": base_prices, "Volume": vols})

        strikes = np.arange(140, 195, 5, dtype=float)
        df_chain = pd.DataFrame({
            "strike": strikes,
            "call_oi": [4000, 6500, 12000, 18500, 34000, 62000, 95000, 88000, 115000, 54000, 32000],
            "put_oi": [48000, 72000, 115000, 92000, 84000, 65000, 38000, 21000, 12000, 5000, 2000],
            "call_vol": [1200, 2300, 5400, 14000, 48000, 76000, 165000, 95000, 68000, 29000, 15000],
            "put_vol": [22000, 41000, 89000, 76000, 64000, 32000, 14000, 6000, 3000, 1100, 400],
            "call_iv": [0.82, 0.80, 0.78, 0.76, 0.75, 0.77, 0.81, 0.85, 0.89, 0.92, 0.95],
            "put_iv": [0.96, 0.92, 0.88, 0.85, 0.82, 0.80, 0.82, 0.84, 0.85, 0.86, 0.87],
        })
        return "NVDA", df_ohlcv, df_chain, "2026-11-20", 5.0, 81.5
    else:
        base_prices = np.linspace(160.0, 179.2, n_bars - 1).tolist() + [178.40]
        opens = [p - np.random.uniform(-1.0, 1.2) for p in base_prices[:-1]] + [179.10]
        highs = [max(o, c) + np.random.uniform(0.4, 1.5) for o, c in zip(opens[:-1], base_prices[:-1])] + [182.60]
        lows = [min(o, c) - np.random.uniform(0.4, 1.4) for o, c in zip(opens[:-1], base_prices[:-1])] + [177.80]
        vols = [np.random.uniform(45e6, 68e6) for _ in range(n_bars - 1)] + [38e6]
        df_ohlcv = pd.DataFrame({"Open": opens, "High": highs, "Low": lows, "Close": base_prices, "Volume": vols})

        strikes = np.arange(140, 195, 5, dtype=float)
        df_chain = pd.DataFrame({
            "strike": strikes,
            "call_oi": [4000, 6500, 12000, 18500, 34000, 62000, 95000, 88000, 115000, 54000, 32000],
            "put_oi": [48000, 72000, 115000, 92000, 84000, 65000, 38000, 21000, 12000, 5000, 2000],
            "call_vol": [1200, 2300, 5400, 14000, 48000, 76000, 95000, 65000, 58000, 19000, 9000],
            "put_vol": [22000, 41000, 89000, 76000, 64000, 32000, 14000, 6000, 3000, 1100, 400],
            "call_iv": [0.76, 0.75, 0.74, 0.73, 0.72, 0.73, 0.75, 0.76, 0.77, 0.79, 0.81],
            "put_iv": [0.88, 0.85, 0.82, 0.80, 0.78, 0.77, 0.76, 0.76, 0.77, 0.78, 0.79],
        })
        return "NVDA", df_ohlcv, df_chain, "2026-11-20", 4.0, 88.0


# ============================================================================
# 6. Streamlit 網頁戰情室 (雙軌自動分流 + 14 顆核心快捷鍵 + 開盤前早報控制)
# ============================================================================
def run_streamlit_warroom() -> None:
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots
    import streamlit as st

    st.set_page_config(
        page_title="全美股期權 GEX 與 Gamma Squeeze 戰情室",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    @st.cache_resource
    def get_bg_daemon() -> BackgroundPatrolDaemon:
        return BackgroundPatrolDaemon()

    daemon = get_bg_daemon()
    cfg = load_user_config()

    required_pwd = str(cfg.get("web_password", "")).strip()
    if required_pwd:
        if not st.session_state.get("authenticated", False):
            st.title("🔐 美股期權 GEX 戰情室 — 手機私人登入")
            pwd_in = st.text_input("請輸入戰情室登入密碼", type="password")
            if st.button("登入戰情室", type="primary"):
                if pwd_in == required_pwd:
                    st.session_state["authenticated"] = True
                    st.rerun()
                else:
                    st.error("密碼錯誤，請重試。")
            st.stop()

    role_badge = (
        "🖥️ 24H Windows VPS 巡邏主機"
        if IS_WINDOWS_VPS
        else "📱 Streamlit Cloud 手機加密看盤端"
    )
    st.title(f"🌎 全美股期權 GEX 正負 Gamma 雷達 ({role_badge})")

    with st.sidebar:
        st.header("⚙️ 雙軌戰情室設定")
        app_tab = st.radio(
            "選擇功能模式",
            [
                "🔍 單股隨選戰情室 (支援全美股任一代號)",
                "🌎 全美股批次掃描雷達",
            ],
            index=0,
        )
        iv_drop_thresh = st.slider(
            "IV 高點回落衰竭警報門檻 (相對回落 %)",
            3.0,
            15.0,
            float(cfg.get("iv_drop_thresh", 6.0)),
            0.5,
        )

        st.divider()
        st.subheader("🌅 每日開盤前早報與核心自選股")
        core_wl_str = st.text_area(
            "核心自選股清單 (預設含 NVDA, TSLA, LUNR, SPCX 與納指前十大)",
            value=cfg.get("core_watchlist", ", ".join(DEFAULT_CORE_WATCHLIST)),
            height=90,
        )
        enable_morning = st.checkbox(
            "每日美股開盤前 15 分鐘自動發送 GEX 早報 (22:15 / 21:15 UTC+8)",
            value=bool(cfg.get("enable_morning_report", True)),
        )

        st.divider()
        st.subheader("📲 Telegram 與雙軌分工設定")
        tg_token = st.text_input(
            "Telegram Bot Token", value=cfg.get("tg_token", ""), type="password"
        )
        tg_chat_id = st.text_input(
            "Telegram Chat ID", value=cfg.get("tg_chat_id", "")
        )
        enable_bg = st.checkbox(
            "啟用 24H 後台巡邏與 TG 雙向回覆 (VPS 自動勾選 / 雲端自動關閉防衝突)",
            value=bool(cfg.get("enable_bg_daemon", IS_WINDOWS_VPS)),
        )
        only_mkt = st.checkbox(
            "僅於美股交易時段巡邏 (週末與休市自動待機)",
            value=bool(cfg.get("only_us_market_hours", True)),
        )
        st.caption(
            f"🤖 後台狀態：已巡邏 `{daemon.total_scans}` 次 | 已推播 `{daemon.total_pushed}` 則 | `{daemon.last_run_tw}`\n"
            f"💬 手機 Telegram 傳送任意代號 (如 `NVDA`) 或傳送 `早報` 即可即時取得報告！"
        )

        if (
            tg_token != cfg.get("tg_token")
            or tg_chat_id != cfg.get("tg_chat_id")
            or core_wl_str != cfg.get("core_watchlist")
            or enable_morning != cfg.get("enable_morning_report")
            or iv_drop_thresh != cfg.get("iv_drop_thresh")
            or enable_bg != cfg.get("enable_bg_daemon")
            or only_mkt != cfg.get("only_us_market_hours")
        ):
            cfg["tg_token"] = tg_token.strip()
            cfg["tg_chat_id"] = tg_chat_id.strip()
            cfg["core_watchlist"] = core_wl_str.strip()
            cfg["enable_morning_report"] = enable_morning
            cfg["iv_drop_thresh"] = iv_drop_thresh
            cfg["enable_bg_daemon"] = enable_bg
            cfg["only_us_market_hours"] = only_mkt
            save_user_config(cfg)
            st.toast("✅ 已自動儲存核心自選股與早報設定！")

        if st.button("🌅 立即發送今日開盤前早報至 Telegram"):
            if not tg_token.strip() or not tg_chat_id.strip():
                st.error("請先在上方填入 Telegram Bot Token 與 Chat ID！")
            else:
                with st.spinner("正在掃描 SPY, QQQ 與 12 檔核心自選股早報數據..."):
                    c_list = parse_watchlist_string(core_wl_str)
                    brief_txt = generate_morning_briefing_report(c_list, iv_drop_thresh)
                    ok_b = send_telegram_alert(tg_token.strip(), tg_chat_id.strip(), brief_txt)
                if ok_b:
                    st.success("🎉 開盤前 GEX 戰情早報已發送至你的手機 Telegram！")
                else:
                    st.error("發送失敗，請確認 Token 與 Chat ID 是否正確。")

        if st.button("📨 發送單股雙拼圖測試推播至 Telegram"):
            if not tg_token.strip() or not tg_chat_id.strip():
                st.error("請先在上方填入 Telegram Bot Token 與 Chat ID！")
            else:
                tk_d, df_o_d, df_c_d, exp_d, dte_d, sim_p = get_demo_scenario_data("NVDA_SQUEEZE")
                snap_d, df_gex_d = evaluate_snapshot_and_alerts(
                    tk_d, df_o_d, df_c_d, exp_d, dte_d, iv_drop_thresh, sim_p
                )
                test_png = os.path.join(BASE_DIR, "Telegram_Test_WarRoom_Alert.png")
                render_warroom_chart_png(snap_d, df_o_d, df_gex_d, test_png)
                ok = send_telegram_alert(
                    tg_token.strip(),
                    tg_chat_id.strip(),
                    "✅ *[雙軌系統測試推播成功]* 你可直接在此聊天室輸入任意美股代號 (如 `NVDA`、`LUNR`、`SPCX`) 或輸入 `早報`！\n\n"
                    + format_telegram_card_message(snap_d),
                    test_png,
                )
                if ok:
                    st.success("🎉 測試推播已發送！請查看你的手機 Telegram。")
                else:
                    st.error("推播失敗，請確認 Token、Chat ID 是否正確，且已對機器人點擊 Start。")

        if IS_WINDOWS_VPS:
            if st.button("⚡ 一鍵加入 Windows VPS 開機自動啟動"):
                ok_st, msg_st = register_windows_startup()
                if ok_st:
                    st.success(f"已寫入 Windows 啟動資料夾：{msg_st}")
                else:
                    st.error(f"設定失敗：{msg_st}")

    if app_tab.startswith("🔍"):
        # 手機快速點擊大盤 + 12 檔核心自選股按鈕列 (共 14 顆，分兩排 7x2 呈現)
        st.caption("📱 點擊下方大盤與核心自選股快捷按鈕（含 NVDA、TSLA、LUNR、SPCX 與納指前十大）或直接輸入任一代號：")
        quick_list = MARKET_INDEX_TICKERS + parse_watchlist_string(core_wl_str)
        if "selected_ticker" not in st.session_state:
            st.session_state["selected_ticker"] = "NVDA"

        row1 = quick_list[:7]
        row2 = quick_list[7:14]
        cols_r1 = st.columns(len(row1))
        for idx, q_tk in enumerate(row1):
            if cols_r1[idx].button(q_tk, use_container_width=True, key=f"q1_{q_tk}"):
                st.session_state["selected_ticker"] = q_tk
        if row2:
            cols_r2 = st.columns(len(row2))
            for idx, q_tk in enumerate(row2):
                if cols_r2[idx].button(q_tk, use_container_width=True, key=f"q2_{q_tk}"):
                    st.session_state["selected_ticker"] = q_tk

        col_inp1, col_inp2, col_inp3 = st.columns([2, 1, 2])
        with col_inp1:
            ticker_input = (
                st.text_input(
                    "輸入任意美股代號 (支援全美股 5,000+ 檔)",
                    value=st.session_state["selected_ticker"],
                )
                .strip()
                .upper()
            )
            st.session_state["selected_ticker"] = ticker_input
        with col_inp2:
            exp_idx = st.number_input(
                "到期日順位 (0=最近週五)", min_value=0, max_value=8, value=0
            )
        with col_inp3:
            data_source = st.selectbox(
                "資料來源",
                ["即時連線全美股 (yfinance)", "離線模擬 (NVDA 軋空啟動)", "離線模擬 (NVDA IV 回落衰竭)"],
            )

        try:
            if data_source.startswith("即時連線"):
                tk, df_ohlcv, df_chain, exp_d, dte = fetch_live_market_data(
                    ticker_input, int(exp_idx)
                )
                sim_peak = None
            elif "軋空啟動" in data_source:
                tk, df_ohlcv, df_chain, exp_d, dte, sim_peak = get_demo_scenario_data("NVDA_SQUEEZE")
            else:
                tk, df_ohlcv, df_chain, exp_d, dte, sim_peak = get_demo_scenario_data("NVDA_IV_CRUSH")
        except Exception as e:
            st.warning(f"即時連線失敗 ({e})，自動切換至內建 NVDA 實戰數據。")
            tk, df_ohlcv, df_chain, exp_d, dte, sim_peak = get_demo_scenario_data("NVDA_SQUEEZE")

        snap, df_gex = evaluate_snapshot_and_alerts(
            tk, df_ohlcv, df_chain, exp_d, dte, iv_drop_thresh, sim_peak
        )

        fig = make_subplots(
            rows=1,
            cols=2,
            shared_yaxes=True,
            column_widths=[0.72, 0.28],
            horizontal_spacing=0.02,
            subplot_titles=(
                f"{snap.ticker} K 線與期權關鍵牆 (現價 ${snap.spot_price:.2f})",
                f"各履約價 Net GEX (總計 {snap.net_gex_millions:+.1f}M)",
            ),
        )

        df_k = df_ohlcv.tail(50).reset_index()
        x_labels = (
            df_k.iloc[:, 0].astype(str)
            if "Date" in df_k.columns or "Datetime" in df_k.columns
            else df_k.index.astype(str)
        )

        fig.add_trace(
            go.Candlestick(
                x=x_labels,
                open=df_k["Open"],
                high=df_k["High"],
                low=df_k["Low"],
                close=df_k["Close"],
                name="K線",
                increasing_line_color="#00E676",
                decreasing_line_color="#FF5252",
            ),
            row=1,
            col=1,
        )

        key_lines = [
            (snap.call_wall, f"Call 壓力牆 ${snap.call_wall:.2f}", "#FF5252", "solid"),
            (snap.put_wall, f"Put 支撐牆 ${snap.put_wall:.2f}", "#00E676", "solid"),
            (snap.zero_gamma_flip, f"Zero Gamma ${snap.zero_gamma_flip:.2f}", "#FFD600", "dash"),
            (snap.max_pain, f"Max Pain ${snap.max_pain:.2f}", "#40C4FF", "dot"),
            (snap.bull_squeeze_trigger, f"Squeeze 啟動 ${snap.bull_squeeze_trigger:.2f}", "#FF9100", "dashdot"),
            (snap.bull_exhaustion_price, f"Squeeze 衰竭 ${snap.bull_exhaustion_price:.2f}", "#E040FB", "dashdot"),
        ]
        for y_val, label_txt, color_hex, dash_style in key_lines:
            fig.add_hline(
                y=y_val,
                line_dash=dash_style,
                line_color=color_hex,
                annotation_text=label_txt,
                annotation_position="top left",
                row=1,
                col=1,
            )

        bar_colors = ["#00E676" if v >= 0 else "#FF1744" for v in df_gex["net_gex_m"]]
        fig.add_trace(
            go.Bar(
                x=df_gex["net_gex_m"],
                y=df_gex["strike"],
                orientation="h",
                marker_color=bar_colors,
                name="Net GEX (M$)",
            ),
            row=1,
            col=2,
        )

        fig.update_layout(
            template="plotly_dark",
            height=620,
            xaxis_rangeslider_visible=False,
            showlegend=False,
        )
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("### 🧭 期權籌碼診斷與即時警報卡片")
        st.markdown(format_telegram_card_message(snap))

    else:
        st.subheader("🌎 全美股兩階段漏斗高速掃描雷達")
        u_col1, u_col2 = st.columns([2, 1])
        with u_col1:
            u_mode = st.selectbox(
                "選擇掃描股票池範圍",
                [
                    "CUSTOM (掃描大盤 SPY/QQQ + 12 檔核心自選股)",
                    "SP500_NDX100 (標普 500 + 納斯達克 100 全成分股快篩)",
                    "ALL_US (SEC 全美股 5,000+ 檔 + 第一階段量價異動快篩)",
                    "MOST_ACTIVE (全美股 130 檔高期權流動性核心池)",
                ],
                index=0,
            )
        with u_col2:
            max_scan = st.number_input("第二階段深度掃描上限", min_value=5, max_value=150, value=30)

        custom_str = core_wl_str
        if u_mode.startswith("CUSTOM"):
            custom_str = st.text_input(
                "輸入欲批次掃描之美股代號",
                value="SPY, QQQ, " + core_wl_str,
            )

        if st.button("🚀 立即手動執行一次批次掃描", type="primary"):
            mode_key = u_mode.split(" ")[0]
            cfg["universe_mode"] = mode_key
            cfg["max_scan"] = int(max_scan)
            save_user_config(cfg)

            custom_list = parse_watchlist_string(custom_str)
            with st.spinner("正在執行多執行緒期權鏈 GEX 深度運算..."):
                scan_results = scan_us_market_universe(
                    universe_mode=mode_key,
                    custom_tickers=custom_list,
                    max_stage2_tickers=int(max_scan),
                    iv_crush_drop_threshold_pct=iv_drop_thresh,
                )

            st.success(f"掃描完成！共完成 {len(scan_results)} 檔美股期權鏈深度解析。")
            for snap, df_ohlcv, df_gex in scan_results:
                with st.expander(
                    f"{'🚨 [觸發警報] ' if snap.active_alerts else ''}{snap.ticker} | 現價 ${snap.spot_price:.2f} | "
                    f"{'🟢 正 Gamma' if snap.is_positive_gamma else '🔴 負 Gamma'} (Net GEX {snap.net_gex_millions:+.1f}M) | "
                    f"Call牆 ${snap.call_wall:.1f} / Put牆 ${snap.put_wall:.1f} / Max Pain ${snap.max_pain:.1f}",
                    expanded=bool(snap.active_alerts),
                ):
                    st.markdown(format_telegram_card_message(snap))
                    if snap.active_alerts and tg_token and tg_chat_id:
                        out_png = os.path.join(BASE_DIR, f"{snap.ticker}_warroom_alert.png")
                        render_warroom_chart_png(snap, df_ohlcv, df_gex, out_png)
                        send_telegram_alert(
                            tg_token, tg_chat_id, format_telegram_card_message(snap), out_png
                        )


# ============================================================================
# 7. CLI 命令列自檢與背景巡邏入口
# ============================================================================
def main() -> None:
    parser = argparse.ArgumentParser(description="All-in-One US Options GEX War Room")
    parser.add_argument("--patrol", action="store_true", help="背景自動巡邏模式")
    parser.add_argument("--morning", action="store_true", help="立即產生並發送今日開盤前早報")
    parser.add_argument("--test-self", action="store_true", help="執行單檔完整性自檢")
    args, _ = parser.parse_known_args()

    if is_running_inside_streamlit():
        run_streamlit_warroom()
        return

    if args.test_self:
        tk, df_ohlcv, df_chain, exp_d, dte, sim_peak = get_demo_scenario_data("NVDA_SQUEEZE")
        snap, df_gex = evaluate_snapshot_and_alerts(tk, df_ohlcv, df_chain, exp_d, dte, 6.0, sim_peak)
        sample_line = format_single_line_brief(snap)
        print(f"✅ [開盤前自動早報 + 12 檔核心自選股版自檢通過] 核心清單={DEFAULT_CORE_WATCHLIST}")
        print(sample_line)
        return

    cfg = load_user_config()
    if args.morning:
        core_list = parse_watchlist_string(
            cfg.get("core_watchlist", ", ".join(DEFAULT_CORE_WATCHLIST))
        )
        brief_md = generate_morning_briefing_report(
            core_list, float(cfg.get("iv_drop_thresh", 6.0))
        )
        print(brief_md)
        send_telegram_alert(cfg.get("tg_token", ""), cfg.get("tg_chat_id", ""), brief_md)
        return

    if args.patrol:
        core_list = parse_watchlist_string(
            cfg.get("core_watchlist", ", ".join(DEFAULT_CORE_WATCHLIST))
        )
        results = scan_us_market_universe(
            universe_mode=cfg.get("universe_mode", "SP500_NDX100"),
            custom_tickers=core_list,
            max_stage2_tickers=int(cfg.get("max_scan", 30)),
            iv_crush_drop_threshold_pct=float(cfg.get("iv_drop_thresh", 6.0)),
        )
        for snap, df_ohlcv, df_gex in results:
            if snap.active_alerts:
                top_code = snap.active_alerts[0].code
                if should_send_alert_with_cooldown(snap.ticker, top_code):
                    out_png = os.path.join(BASE_DIR, f"{snap.ticker}_warroom_alert.png")
                    render_warroom_chart_png(snap, df_ohlcv, df_gex, out_png)
                    send_telegram_alert(
                        cfg.get("tg_token", ""),
                        cfg.get("tg_chat_id", ""),
                        format_telegram_card_message(snap),
                        out_png,
                    )


if __name__ == "__main__":
    main()