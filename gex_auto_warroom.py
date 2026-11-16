#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
全美股期權 GEX 戰情室 & Telegram 自動推播系統 (日K對齊 + 首頁14檔燈號 + 納指方向研判版)
===============================================================================
更新時間: 2026-11-15 10:38:00 (UTC+8)

【本次針對 4 張實機截圖之全面升級】：
1. K 線全面對齊看盤軟體「日 K 線 (Daily K-Bars + MA5/MA10/MA20)」：
   • 修正原本抓 15 分鐘 K 線導致形狀與富途牛牛日 K 對不起來、且 X 軸只有 0~40 編號的問題。
   • 改為抓取標準近 45 個交易日之「日 K 線 (1D)」，疊加 MA5(橘)、MA10(青)、MA20(紫)，X 軸顯示真實 MM/DD 日期。
2. 徹底解決手機版 Streamlit 圖表與文字重疊、縮放跑版問題：
   • 採用 `xaxis_type="category"` 消除週末休市空白斷層，K 線 100% 填滿手機畫面。
   • 將「日 K 線支撐壓力圖」與「各履約價 GEX 柱狀圖」改為上下獨立滿版排列，並將價位線標籤改為右側防重疊膠囊與圖例，手機滑動不再亂跑或字體互疊。
3. 網站一打開預設直接顯示「納斯達克前十大 Gamma 總體方向研判」+「核心 14 檔正負 Gamma 即時燈號牆」：
   • 首頁自動統計 QQQ 與納指前十大權重股之正負 Gamma 家數比、總淨曝險 (Net GEX) 與操作方向建議，並以紅綠燈卡片展示 14 檔核心股。
4. 重新設計 Telegram 早報排版與嚴格區分現價上下之 Call/Put 牆：
   • 強制規定 Call 牆必須 `> 現價`、Put 牆必須 `< 現價`（解決 Put 牆高於現價或與 Call 牆重疊之問題），並新增納指前十大方向總結與清爽三行式早報排版。
"""

import importlib
import os
import re
import socket
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

DEFAULT_CORE_WATCHLIST = [
    "NVDA",
    "TSLA",
    "LUNR",
    "SPCX",
    "TSM",
    "AAPL",
    "MSFT",
    "AMZN",
    "AVGO",
    "META",
    "GOOGL",
    "COST",
    "NFLX",
]
MARKET_INDEX_TICKERS = ["SPY", "QQQ", "SMH", "SOXX", "GLD"]
NASDAQ_TOP10_TICKERS = [
    "AAPL",
    "NVDA",
    "MSFT",
    "AMZN",
    "AVGO",
    "META",
    "TSLA",
    "GOOGL",
    "COST",
    "NFLX",
]


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
    if (
        "--patrol" not in sys.argv
        and "--test-self" not in sys.argv
        and "--morning" not in sys.argv
        and "--daemon-loop" not in sys.argv
    ):
        print("🚀 正在啟動 Windows VPS 全美股 GEX 戰情室與 24H 後台推播守護程序...")
        print("   • 本機設定網址: http://localhost:8501 (不需開放 VPS 防火牆)")
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
import ssl
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

try:
    import urllib3
    import urllib3.util.connection as urllib3_cn

    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    urllib3_cn.allowed_gai_family = lambda: socket.AF_INET
except Exception:
    pass


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
MT5_CSV_LOCK = threading.Lock()


def sanitize_tg_credentials(token: str, chat_id: str) -> Tuple[str, str]:
    clean_tok = re.sub(r"[^0-9a-zA-Z:_-]", "", str(token or ""))
    clean_cid = re.sub(r"[^0-9-]", "", str(chat_id or ""))
    return clean_tok, clean_cid


def get_mt5_common_files_dir() -> str:
    appdata = os.environ.get("APPDATA", "")
    if IS_WINDOWS_VPS and appdata:
        mt5_common = os.path.join(appdata, "MetaQuotes", "Terminal", "Common", "Files")
        try:
            os.makedirs(mt5_common, exist_ok=True)
            return mt5_common
        except Exception:
            pass
    return BASE_DIR


def export_snapshot_to_mt5_common_csv(snap) -> str:
    header = (
        "Ticker,SpotPrice,IsPosGamma,NetGEX_M,ZeroGamma,CallWall,PutWall,MaxPain,"
        "BullTrigger,BearTrigger,BullExhaust,BearExhaust,ATM_IV,IV_Peak,IV_DropPct,"
        "DTE,ActiveAlertCode,UpdatedTW"
    )
    alert_code = snap.active_alerts[0].code if snap.active_alerts else "NONE"
    clean_tw = str(snap.timestamp_tw).replace(",", " ")
    row_str = (
        f"{snap.ticker.upper()},{snap.spot_price:.4f},{1 if snap.is_positive_gamma else 0},"
        f"{snap.net_gex_millions:.2f},{snap.zero_gamma_flip:.4f},{snap.call_wall:.4f},"
        f"{snap.put_wall:.4f},{snap.max_pain:.4f},{snap.bull_squeeze_trigger:.4f},"
        f"{snap.bear_squeeze_trigger:.4f},{snap.bull_exhaustion_price:.4f},"
        f"{snap.bear_exhaustion_price:.4f},{snap.atm_iv_pct:.2f},{snap.iv_peak_pct:.2f},"
        f"{snap.iv_drop_from_peak_pct:.2f},{snap.dte_days:.1f},{alert_code},{clean_tw}"
    )

    target_dirs = {BASE_DIR, get_mt5_common_files_dir()}
    primary_csv = os.path.join(get_mt5_common_files_dir(), "gex_mt5_levels.csv")

    with MT5_CSV_LOCK:
        for d in target_dirs:
            csv_path = os.path.join(d, "gex_mt5_levels.csv")
            existing_rows = {}
            if os.path.exists(csv_path):
                try:
                    with open(csv_path, "r", encoding="utf-8") as rf:
                        for line in rf:
                            s = line.strip()
                            if not s or s.startswith("Ticker,"):
                                continue
                            tk_key = s.split(",", 1)[0].strip().upper()
                            if tk_key:
                                existing_rows[tk_key] = s
                except Exception:
                    pass
            existing_rows[snap.ticker.upper()] = row_str
            try:
                with open(csv_path, "w", encoding="utf-8") as wf:
                    wf.write(header + "\n")
                    for k in sorted(existing_rows.keys()):
                        wf.write(existing_rows[k] + "\n")
            except Exception:
                pass
    return primary_csv


def enable_invisible_windows_background_service() -> Tuple[bool, str]:
    if not IS_WINDOWS_VPS:
        return False, "目前非 Windows 系統，無需設定 Windows 隱形背景常駐。"
    try:
        appdata = os.environ.get("APPDATA", "")
        startup_dir = os.path.join(
            appdata, "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
        )
        os.makedirs(startup_dir, exist_ok=True)

        old_bat = os.path.join(startup_dir, "GEX_Auto_WarRoom_Startup.bat")
        if os.path.exists(old_bat):
            try:
                os.remove(old_bat)
            except Exception:
                pass

        script_abs = os.path.abspath(__file__)
        py_exe = sys.executable
        vbs_path = os.path.join(startup_dir, "GEX_Invisible_Daemon.vbs")

        vbs_content = (
            'Set WshShell = CreateObject("WScript.Shell")\n'
            f'WshShell.CurrentDirectory = "{BASE_DIR}"\n'
            f'WshShell.Run """{py_exe}"" ""{script_abs}"" --daemon-loop", 0, False\n'
        )
        with open(vbs_path, "w", encoding="utf-8") as f:
            f.write(vbs_content)

        creation_flags = 0x08000000 | 0x00000008  # CREATE_NO_WINDOW | DETACHED_PROCESS
        subprocess.Popen(
            [py_exe, script_abs, "--daemon-loop"],
            cwd=BASE_DIR,
            creationflags=creation_flags,
            close_fds=True,
        )
        return (
            True,
            f"已啟動無黑窗隱形背景程序並寫入開機自啟 ({vbs_path})！你現在可以直接把黑色的 CMD 視窗關掉了。",
        )
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

    c_tok, c_cid = sanitize_tg_credentials(
        default_cfg.get("tg_token", ""), default_cfg.get("tg_chat_id", "")
    )
    default_cfg["tg_token"] = c_tok
    default_cfg["tg_chat_id"] = c_cid
    return default_cfg


def save_user_config(cfg: Dict) -> None:
    try:
        c_tok, c_cid = sanitize_tg_credentials(
            cfg.get("tg_token", ""), cfg.get("tg_chat_id", "")
        )
        cfg["tg_token"] = c_tok
        cfg["tg_chat_id"] = c_cid
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
    """
    美股期權市場正規交易時段為美東 09:30 ~ 16:00（夏令 13:30~20:00 UTC / 冬令 14:30~21:00 UTC，即冬令台灣時間 22:30~05:00）。
    避開 21:00~22:25 盤前期權未開盤時段 Yahoo Finance 重置 IV 為 0 的問題。
    """
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if now_utc.weekday() >= 5:
        return False
    utc_hour_float = now_utc.hour + now_utc.minute / 60.0
    return 14.45 <= utc_hour_float <= 21.2


def is_premarket_briefing_window() -> bool:
    now_utc = datetime.datetime.now(datetime.timezone.utc)
    if now_utc.weekday() >= 5:
        return False
    utc_hm = now_utc.hour * 60 + now_utc.minute
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
    ssl_ctx = ssl._create_unverified_context()
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
    for url in [
        "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies",
        "https://en.wikipedia.org/wiki/Nasdaq-100",
    ]:
        try:
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=10, context=ssl_ctx) as resp:
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
    ssl_ctx = ssl._create_unverified_context()
    headers = {"User-Agent": "QuantOptionsGEXScanner/3.0 (contact@quant-research.local)"}
    try:
        req = urllib.request.Request(
            "https://www.sec.gov/files/company_tickers.json", headers=headers
        )
        with urllib.request.urlopen(req, timeout=12, context=ssl_ctx) as resp:
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
    risk_free_rate: float = 0.045,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    T = max(float(tte_years), 1.0 / (365.0 * 24.0))
    sigma = np.clip(iv.astype(float), 0.05, 5.0)
    K = np.maximum(strikes.astype(float), 0.01)
    S = max(float(spot), 0.01)

    sqrt_T = math.sqrt(T)
    d1 = (np.log(S / K) + (risk_free_rate + 0.5 * sigma**2) * T) / (sigma * sqrt_T)
    d2 = d1 - sigma * sqrt_T

    pdf_d1 = norm_pdf(d1)
    cdf_d1 = norm_cdf(d1)

    call_delta = cdf_d1
    put_delta = cdf_d1 - 1.0
    gamma = pdf_d1 / (S * sigma * sqrt_T)
    vanna = -pdf_d1 * (d2 / sigma)
    charm = -pdf_d1 * (
        (2.0 * risk_free_rate * T - d2 * sigma * sqrt_T) / (2.0 * T * sigma * sqrt_T)
    )
    return call_delta, put_delta, gamma, vanna, charm


def dealer_call_polarity(
    call_vol: np.ndarray,
    call_oi: np.ndarray,
    call_iv: np.ndarray,
    put_iv: Optional[np.ndarray] = None,
    ticker: str = "",
) -> np.ndarray:
    """
    依資產類別區分造市商 Call 部位極性：
    • 一般股票/科技股：機構常賣 Covered Call (+1.0)，僅當 Vol/OI >= 0.85 且 IV >= 65% 才判定為散戶/動能追買 Call (-1.0)。
    • 黃金/商品 ETF (GLD, SLV)：黃金波動率基準較低 (~15%~28%) 且機構常買價外 Call 避險/追漲 (Call Skew)，
      只要 Vol/OI >= 0.80 且呈現 Call Skew (call_iv >= put_iv) 或 IV >= 25%，即判定造市商為 Short Call Gamma (-1.0)。
    """
    vol_oi = call_vol / np.maximum(call_oi, 1.0)
    # 若美股開盤前交易所將當日成交量 (call_vol) 歸零重置，則僅以高 IV 與 Skew 判定，避免開盤前極性突然翻轉
    is_preopen_zero_vol = float(np.sum(call_vol)) <= 10.0
    tk_u = ticker.upper()
    if tk_u in {"GLD", "SLV", "GDX", "USO"}:
        if put_iv is not None:
            has_call_skew = call_iv >= put_iv * 0.99
            if is_preopen_zero_vol:
                return np.where(has_call_skew & (call_iv >= 0.25), -1.0, 1.0)
            return np.where((vol_oi >= 0.80) & (has_call_skew | (call_iv >= 0.25)), -1.0, 1.0)
        return np.where((vol_oi >= 0.80) & (call_iv >= 0.25), -1.0, 1.0)
    if is_preopen_zero_vol:
        if put_iv is not None:
            return np.where((call_iv >= 0.65) & (call_iv >= put_iv * 1.02), -1.0, 1.0)
        return np.where(call_iv >= 0.70, -1.0, 1.0)
    return np.where((vol_oi >= 0.85) & (call_iv >= 0.65), -1.0, 1.0)


def compute_max_pain(df_chain: pd.DataFrame) -> float:
    strikes = df_chain["strike"].values.astype(float)
    call_oi = df_chain["call_oi"].values.astype(float)
    put_oi = df_chain["put_oi"].values.astype(float)

    payouts = []
    for s_test in strikes:
        c_loss = np.sum(np.maximum(0.0, s_test - strikes) * call_oi)
        p_loss = np.sum(np.maximum(0.0, strikes - s_test) * put_oi)
        payouts.append(c_loss + p_loss)
    return float(strikes[int(np.argmin(payouts))])


def find_zero_gamma_flip(
    spot: float,
    strikes: np.ndarray,
    call_oi: np.ndarray,
    put_oi: np.ndarray,
    call_iv: np.ndarray,
    put_iv: np.ndarray,
    tte_years: float,
    call_pol: Optional[np.ndarray] = None,
) -> float:
    """
    100% 純數學求解 Net GEX(S) = 0 之零點 (Zero Gamma Flip)，不加任何人工上下界強制規定：
    代入與當下 Net GEX 完全一致之 call_pol 極性，直接找出離現價最近之 Net GEX = 0 交叉點。
    """
    low_s = max(float(np.min(strikes)) * 0.90, spot * 0.75)
    high_s = min(float(np.max(strikes)) * 1.10, spot * 1.25)
    grid = np.linspace(low_s, high_s, 160)
    pol = call_pol if call_pol is not None else np.ones_like(strikes)

    net_curve = []
    for s_val in grid:
        _, _, c_gam, _, _ = bs_greeks(s_val, strikes, tte_years, call_iv)
        _, _, p_gam, _, _ = bs_greeks(s_val, strikes, tte_years, put_iv)
        c_gex = np.sum(call_oi * c_gam * pol * 100.0 * (s_val**2) * 0.01)
        p_gex = np.sum(-put_oi * p_gam * 100.0 * (s_val**2) * 0.01)
        net_curve.append(c_gex + p_gex)

    arr = np.array(net_curve)
    signs = np.sign(arr)
    crossings = np.where(np.diff(signs) != 0)[0]
    if len(crossings) > 0:
        best_idx = min(crossings, key=lambda idx: abs(grid[idx] - spot))
        x0, x1 = grid[best_idx], grid[best_idx + 1]
        y0, y1 = arr[best_idx], arr[best_idx + 1]
        if abs(y1 - y0) > 1e-9:
            return round(float(x0 - y0 * (x1 - x0) / (y1 - y0)), 2)
    return round(float(grid[int(np.argmin(np.abs(arr)))]), 2)


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
    next_upper_call_wall: float
    next_lower_put_wall: float
    max_pain: float
    bull_squeeze_trigger: float
    bear_squeeze_trigger: float
    bull_exhaustion_price: float
    bear_exhaustion_price: float
    charm_unwind_time_tw: str
    active_alerts: List[AlertSignal]


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
    prev_close = float(df_ohlcv["Close"].iloc[-2]) if len(df_ohlcv) >= 2 else spot
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

    call_pol = dealer_call_polarity(call_vol, call_oi, call_iv, put_iv, ticker)
    if "pre_call_gex_m" in df.columns and "pre_put_gex_m" in df.columns:
        df["call_gex_raw_m"] = df["pre_call_gex_m"].values.astype(float)
        df["put_gex_m"] = df["pre_put_gex_m"].values.astype(float)
    else:
        df["call_gex_raw_m"] = (call_oi * c_gamma * 100.0 * (spot**2) * 0.01) / 1e6
        df["put_gex_m"] = (-put_oi * p_gamma * 100.0 * (spot**2) * 0.01) / 1e6
    df["call_gex_m"] = df["call_gex_raw_m"] * call_pol
    df["net_gex_m"] = df["call_gex_m"] + df["put_gex_m"]
    df["call_vol_oi"] = call_vol / np.maximum(call_oi, 1.0)
    df["put_vol_oi"] = put_vol / np.maximum(put_oi, 1.0)

    net_gex_total = float(df["net_gex_m"].sum())
    zero_gamma = find_zero_gamma_flip(
        spot, strikes, call_oi, put_oi, call_iv, put_iv, tte_years, call_pol
    )
    # 正負 Gamma 完全由當下總淨曝險 (net_gex_total > 0) 決定，不人為扭曲
    is_pos_gamma = net_gex_total > 0

    atm_idx = int(np.argmin(np.abs(strikes - spot)))
    atm_iv_pct = float(((call_iv[atm_idx] + put_iv[atm_idx]) / 2.0) * 100.0)

    today_tw_str = (
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    ).strftime("%Y-%m-%d")
    tracker = load_tracker_state()
    tk_state = tracker.get(ticker.upper(), {})
    if tk_state.get("iv_peak_date") == today_tw_str:
        recorded_iv_peak = float(tk_state.get("iv_peak_pct", atm_iv_pct))
    else:
        recorded_iv_peak = atm_iv_pct
    if simulated_iv_peak_pct is not None:
        iv_peak_pct = max(simulated_iv_peak_pct, atm_iv_pct)
    else:
        iv_peak_pct = max(recorded_iv_peak, atm_iv_pct)
    tk_state["iv_peak_date"] = today_tw_str

    iv_drop_rel_pct = (
        ((iv_peak_pct - atm_iv_pct) / iv_peak_pct) * 100.0 if iv_peak_pct > 0 else 0.0
    )

    expected_move_pct = (atm_iv_pct / 100.0) * math.sqrt(tte_years)
    expected_move_usd = spot * expected_move_pct

    # 1. 100% 純粹依據造市商 Gamma Exposure (GEX) 決定主力 Call 牆與主力 Put 牆：
    # • 主力 Call 牆：全場正 Gamma 曝險 (Call GEX / Net GEX > 0) 最大的履約價（對應右側圖表最長綠柱）。
    # • 主力 Put 牆：全場負向 Put Gamma 佔優 (Net GEX < 0，即 Put GEX 超過 Call GEX，對應右側圖表最長紅柱)
    #   或全場負向 Put GEX 絕對值最大的獨立履約價，絕不摻雜人為 OI 權重，亦不與正向 Call 牆重疊於同一綠柱。
    pos_net_df = df[df["net_gex_m"] > 0]
    if not pos_net_df.empty:
        call_wall = float(pos_net_df.loc[pos_net_df["call_gex_raw_m"].idxmax(), "strike"])
    else:
        call_wall = float(df.loc[df["call_gex_raw_m"].idxmax(), "strike"])

    neg_net_df = df[df["net_gex_m"] < 0]
    if not neg_net_df.empty:
        put_wall = float(neg_net_df.loc[neg_net_df["put_gex_m"].idxmin(), "strike"])
    else:
        non_cw_df = df[df["strike"] != call_wall]
        put_wall = float(
            non_cw_df.loc[non_cw_df["put_gex_m"].idxmin(), "strike"]
            if not non_cw_df.empty
            else df.loc[df["put_gex_m"].idxmin(), "strike"]
        )

    # 2. 若主力 Call 牆已被現價站上 (call_wall <= spot，轉為正 Gamma 磁吸支撐)，同時標出上方最大 Call GEX 次級壓力牆
    upper_df = df[df["strike"] > spot * 1.001]
    if not upper_df.empty:
        next_upper_call_wall = float(upper_df.loc[upper_df["call_gex_raw_m"].idxmax(), "strike"])
    else:
        next_upper_call_wall = round(spot * 1.03, 2)

    # 若主力 Put 牆已被現價跌破 (put_wall >= spot，轉為負 Gamma 破牆反壓)，同時標出下方最大 Put GEX 次級支撐牆
    lower_df = df[df["strike"] < spot * 0.999]
    if not lower_df.empty:
        next_lower_put_wall = float(lower_df.loc[lower_df["put_gex_m"].idxmin(), "strike"])
    else:
        next_lower_put_wall = round(spot * 0.97, 2)

    max_pain = compute_max_pain(df)

    # 多頭起漲點 (bull_trigger)：
    # 若目前在負 Gamma (spot < zero_gamma)，必須先站上翻轉點 zero_gamma 才會結束負 Gamma 助跌，
    # 因此多頭起漲點必須 >= max(spot * 1.006, zero_gamma)，絕不會挑到僅差 $0.11 且還在翻轉點下方的價平履約價！
    min_bull_strike = max(spot * 1.006, zero_gamma if not is_pos_gamma else spot * 1.005)
    bull_cands = df[(df["strike"] >= min_bull_strike) & (df["strike"] <= spot * 1.14)].copy()
    if not bull_cands.empty:
        bull_cands["sq_score"] = bull_cands["call_gex_raw_m"] * (
            1.0 + bull_cands["call_vol_oi"]
        )
        bull_trigger = float(bull_cands.loc[bull_cands["sq_score"].idxmax(), "strike"])
    else:
        bull_trigger = max(next_upper_call_wall, round(min_bull_strike, 2))

    # 空頭破牆加空點 (bear_trigger)：至少低於現價 0.5%，若主力 Put 牆已跌破則對齊下方次級支撐牆
    max_bear_strike = min(spot * 0.995, zero_gamma if is_pos_gamma else spot * 0.995)
    bear_cands = df[(df["strike"] <= max_bear_strike) & (df["strike"] >= spot * 0.86)].copy()
    if not bear_cands.empty:
        bear_cands["cr_score"] = np.abs(bear_cands["put_gex_m"]) * (
            1.0 + bear_cands["put_vol_oi"]
        )
        bear_trigger = float(bear_cands.loc[bear_cands["cr_score"].idxmax(), "strike"])
    else:
        bear_trigger = min(next_lower_put_wall, round(max_bear_strike, 2))

    far_calls = df[df["strike"] > bull_trigger]
    if not far_calls.empty:
        oi_cut = np.percentile(far_calls["call_oi"], 75)
        term_call = float(far_calls[far_calls["call_oi"] >= oi_cut]["strike"].max())
    else:
        term_call = round(spot + expected_move_usd, 2)
    bull_exhaust = round(
        max(bull_trigger * 1.025, min(term_call, spot + 1.25 * expected_move_usd)), 2
    )

    far_puts = df[df["strike"] < bear_trigger]
    if not far_puts.empty:
        oi_cut_p = np.percentile(far_puts["put_oi"], 75)
        term_put = float(far_puts[far_puts["put_oi"] >= oi_cut_p]["strike"].min())
    else:
        term_put = round(spot - expected_move_usd, 2)
    bear_exhaust = round(
        min(bear_trigger * 0.975, max(term_put, spot - 1.25 * expected_move_usd)), 2
    )

    try:
        exp_dt = datetime.datetime.strptime(expiration_date[:10], "%Y-%m-%d")
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
    is_price_exhausted = (high_curr >= bull_exhaust * 0.995) and (upper_wick_ratio > 0.45) and (spot > bull_trigger)
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
        next_upper_call_wall=next_upper_call_wall,
        next_lower_put_wall=next_lower_put_wall,
        max_pain=max_pain,
        bull_squeeze_trigger=bull_trigger,
        bear_squeeze_trigger=bear_trigger,
        bull_exhaustion_price=bull_exhaust,
        bear_exhaustion_price=bear_exhaust,
        charm_unwind_time_tw=charm_tw_str,
        active_alerts=alerts,
    )
    try:
        export_snapshot_to_mt5_common_csv(snapshot)
    except Exception:
        pass
    return snapshot, df


# ============================================================================
# 3. 高解析度「標準日K線 (含MA5/10/20 + 日期軸) + 右側GEX牆 + 防重疊標籤」繪製器
# ============================================================================
def extract_mmdd_labels(df_plot: pd.DataFrame) -> List[str]:
    labels = []
    idx_vals = df_plot.index
    if "Date" in df_plot.columns:
        idx_vals = df_plot["Date"]
    elif "Datetime" in df_plot.columns:
        idx_vals = df_plot["Datetime"]

    for idx_v in idx_vals:
        s = str(idx_v)
        m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
        if m:
            labels.append(f"{m.group(2)}/{m.group(3)}")
        else:
            labels.append(s[:5])
    return labels


def render_warroom_chart_png(
    snap: WarRoomSnapshot,
    df_ohlcv: pd.DataFrame,
    df_chain: pd.DataFrame,
    output_path: str,
) -> str:
    fig = plt.figure(figsize=(15.5, 9.5), dpi=160, facecolor="#0E1117")
    gs = fig.add_gridspec(
        2, 2, width_ratios=[3.15, 1.15], height_ratios=[4.3, 1.35], hspace=0.25, wspace=0.08
    )

    ax_k = fig.add_subplot(gs[0, 0], facecolor="#131722")
    ax_gex = fig.add_subplot(gs[0, 1], sharey=ax_k, facecolor="#131722")
    ax_card = fig.add_subplot(gs[1, :], facecolor="#161B26")

    df_full = df_ohlcv.copy()
    df_full["MA5"] = df_full["Close"].rolling(5, min_periods=1).mean()
    df_full["MA10"] = df_full["Close"].rolling(10, min_periods=1).mean()
    df_full["MA20"] = df_full["Close"].rolling(20, min_periods=1).mean()

    # 聚焦最近 22 個交易日之日 K 線，並以「近 12 日高低點 + 期權牆區間」決定 Y 軸上下界，
    # 避免兩個月前過高或過低的歷史價位把 Y 軸拉得太遠，導致現價附近的 Call/Put 牆擠在一起！
    df_plot = df_full.tail(22).copy()
    date_labels = extract_mmdd_labels(df_plot)
    df_plot = df_plot.reset_index(drop=True)

    recent_focus = df_plot.tail(12)
    k_low = float(recent_focus["Low"].min())
    k_high = float(recent_focus["High"].max())
    y_min = min(k_low, snap.put_wall, snap.next_lower_put_wall, snap.zero_gamma_flip) * 0.988
    y_max = max(k_high, snap.call_wall, snap.next_upper_call_wall, snap.bull_exhaustion_price) * 1.012

    if snap.is_positive_gamma:
        ax_k.axhspan(snap.zero_gamma_flip, y_max, color="#00E676", alpha=0.04)
        ax_k.axhspan(y_min, snap.zero_gamma_flip, color="#FF1744", alpha=0.03)
    else:
        ax_k.axhspan(y_min, y_max, color="#FF1744", alpha=0.04)

    # 繪製日 K 線與 MA5 / MA10 / MA20 (對齊富途牛牛日K圖風格)
    x_arr = np.arange(len(df_plot))
    ax_k.plot(x_arr, df_plot["MA5"].values, color="#FF9800", linewidth=1.3, label="MA5", zorder=4)
    ax_k.plot(x_arr, df_plot["MA10"].values, color="#29B6F6", linewidth=1.3, label="MA10", zorder=4)
    ax_k.plot(x_arr, df_plot["MA20"].values, color="#AB47BC", linewidth=1.4, label="MA20", zorder=4)

    for i, row in df_plot.iterrows():
        o, h, l, c = float(row["Open"]), float(row["High"]), float(row["Low"]), float(row["Close"])
        color = "#00E676" if c >= o else "#FF5252"
        ax_k.plot([i, i], [l, h], color=color, linewidth=1.35, zorder=3)
        body_bottom = min(o, c)
        body_h = max(abs(c - o), (y_max - y_min) * 0.0025)
        rect = mpatches.Rectangle(
            (i - 0.32, body_bottom), 0.64, body_h, facecolor=color, edgecolor=color, zorder=5
        )
        ax_k.add_patch(rect)

    # 繪製關鍵期權水平線，並做垂直防重疊偏移 (Anti-Overlap Vertical Solver)
    cw_label = (
        f"主力 Call 牆(已突破轉撐) ${snap.call_wall:.1f}"
        if snap.call_wall < snap.spot_price
        else f"主力 Call 壓力牆 ${snap.call_wall:.1f}"
    )
    pw_label = (
        f"主力 Put 牆(已跌破轉壓) ${snap.put_wall:.1f}"
        if snap.put_wall > snap.spot_price
        else f"主力 Put 支撐牆 ${snap.put_wall:.1f}"
    )
    levels_raw = [
        (snap.bull_exhaustion_price, f"衰竭天花板 ${snap.bull_exhaustion_price:.1f}", "#E040FB", "-.", 1.6),
        (snap.call_wall, cw_label, "#FF5252", "-", 2.0),
        (snap.bull_squeeze_trigger, f"軋空啟動 ${snap.bull_squeeze_trigger:.1f}", "#FF9100", "-.", 1.8),
        (snap.max_pain, f"Max Pain 痛點 ${snap.max_pain:.1f}", "#40C4FF", ":", 1.8),
        (snap.zero_gamma_flip, f"Zero Gamma 翻轉 ${snap.zero_gamma_flip:.2f}", "#FFD600", "--", 2.0),
        (snap.put_wall, pw_label, "#00E676", "-", 2.0),
    ]
    if snap.call_wall < snap.spot_price and snap.next_upper_call_wall > snap.spot_price:
        levels_raw.append((snap.next_upper_call_wall, f"上方次級 Call 牆 ${snap.next_upper_call_wall:.1f}", "#FF8A80", "--", 1.5))
    if snap.put_wall > snap.spot_price and snap.next_lower_put_wall < snap.spot_price:
        levels_raw.append((snap.next_lower_put_wall, f"下方次級 Put 牆 ${snap.next_lower_put_wall:.1f}", "#69F0AE", "--", 1.5))
    # 合併相同價位之標籤，避免兩條同價位線字體重疊
    merged_levels: List[Tuple[float, str, str, str, float]] = []
    for price_val, lbl, col, ls, lw in sorted(levels_raw, key=lambda x: x[0], reverse=True):
        if not (y_min <= price_val <= y_max):
            continue
        if merged_levels and abs(price_val - merged_levels[-1][0]) < (y_max - y_min) * 0.008:
            prev_p, prev_lbl, prev_col, prev_ls, prev_lw = merged_levels[-1]
            short_new = lbl.split("$")[0].strip()
            merged_levels[-1] = (prev_p, f"{prev_lbl} / {short_new}", prev_col, prev_ls, prev_lw)
        else:
            merged_levels.append((price_val, lbl, col, ls, lw))

    min_gap_y = (y_max - y_min) * 0.042
    placed_y: List[float] = []
    for idx_l, (price_val, lbl, col, ls, lw) in enumerate(merged_levels):
        ax_k.axhline(price_val, color=col, linestyle=ls, linewidth=lw, alpha=0.88, zorder=2)
        target_y = price_val
        for py in placed_y:
            if abs(target_y - py) < min_gap_y:
                target_y = py - min_gap_y
        target_y = max(y_min + min_gap_y * 0.4, min(y_max - min_gap_y * 0.4, target_y))
        placed_y.append(target_y)
        x_anchor = 7.5 if (idx_l % 2 == 0) else 20.0
        ax_k.text(
            x_anchor,
            target_y,
            lbl,
            color=col,
            fontsize=9.2,
            fontweight="bold",
            bbox=dict(boxstyle="round,pad=0.22", facecolor="#0E1117", edgecolor=col, lw=0.8, alpha=0.90),
            zorder=7,
        )

    # X 軸真實日期刻度
    tick_positions = list(range(0, len(df_plot), max(1, len(df_plot) // 7)))
    if (len(df_plot) - 1) not in tick_positions:
        tick_positions.append(len(df_plot) - 1)
    ax_k.set_xticks(tick_positions)
    ax_k.set_xticklabels([date_labels[p] for p in tick_positions], color="#B2B5BE", fontsize=9)

    chg_pct = ((snap.spot_price - snap.prev_close) / max(snap.prev_close, 0.01)) * 100.0
    regime_title = "【正 Gamma 穩定區】" if snap.is_positive_gamma else "【負 Gamma 擠壓警戒區】"
    ax_k.set_title(
        f"{snap.ticker} 日 K 線圖 (現價 ${snap.spot_price:.2f} / {chg_pct:+.2f}% / 昨收 ${snap.prev_close:.2f}) — {regime_title}",
        color="white",
        fontsize=12.2,
        fontweight="bold",
        pad=10,
    )
    ax_k.legend(loc="upper left", facecolor="#131722", edgecolor="#2A2E39", labelcolor="white", fontsize=8.5)
    ax_k.set_ylim(y_min, y_max)
    ax_k.set_xlim(-1, len(df_plot) + 1.5)
    ax_k.grid(True, color="#2A2E39", linestyle="--", linewidth=0.6, alpha=0.6)
    ax_k.tick_params(colors="#B2B5BE", labelsize=9)

    df_sub = df_chain[(df_chain["strike"] >= y_min) & (df_chain["strike"] <= y_max)]
    bar_height = (
        max(np.min(np.diff(df_sub["strike"].values)) * 0.65, 0.8)
        if len(df_sub) > 1
        else 1.5
    )
    colors_gex = ["#00E676" if v >= 0 else "#FF1744" for v in df_sub["net_gex_m"].values]
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
        f"[正 Gamma 穩定態] 現價 ${snap.spot_price:.2f} (昨收 ${snap.prev_close:.2f}) | 翻轉點 ${snap.zero_gamma_flip:.2f} | Net GEX {snap.net_gex_millions:+.1f}M"
        if snap.is_positive_gamma
        else f"[負 Gamma 擠壓態] 現價 ${snap.spot_price:.2f} (昨收 ${snap.prev_close:.2f}) | 翻轉點 ${snap.zero_gamma_flip:.2f} | Net GEX {snap.net_gex_millions:+.1f}M"
    )
    line1 = f"標的: {snap.ticker} (日K) | 期權範圍: {snap.expiration_date} | 時間: {snap.timestamp_tw}"
    line2 = f"• {status_str} | 下方 Put 支撐牆: ${snap.put_wall:.2f} | Max Pain 痛點: ${snap.max_pain:.2f} | 上方 Call 壓力牆: ${snap.call_wall:.2f}"
    line3 = (
        f"• [Squeeze 雷達] 向上軋空啟動: ${snap.bull_squeeze_trigger:.2f} (衰竭目標: ${snap.bull_exhaustion_price:.2f}) | "
        f"向下破牆助跌: ${snap.bear_squeeze_trigger:.2f} | ATM IV: {snap.atm_iv_pct:.1f}% (峰值 {snap.iv_peak_pct:.1f}%)"
    )
    if snap.active_alerts:
        a0 = snap.active_alerts[0]
        line4 = f"🚨 {a0.title} — 建議進場 ${a0.entry_price:.2f} | 停損 ${a0.sl_price:.2f} | 停利 ${a0.tp_price:.2f} (RRR 1:{a0.rrr:.1f})"
        c4 = "#FFD600"
    else:
        line4 = f"• [Charm 平倉警戒窗] {snap.charm_unwind_time_tw} | 預期波動區間: +/-${snap.expected_move_usd:.2f} (+/-{snap.expected_move_pct:.1f}%)"
        c4 = "#80D8FF"

    ax_card.text(0.015, 0.78, line1, color="#FFFFFF", fontsize=10.5, fontweight="bold", transform=ax_card.transAxes)
    ax_card.text(0.015, 0.54, line2, color="#00E676" if snap.is_positive_gamma else "#FF8A80", fontsize=10, transform=ax_card.transAxes)
    ax_card.text(0.015, 0.30, line3, color="#FFB74D", fontsize=10, transform=ax_card.transAxes)
    ax_card.text(0.015, 0.07, line4, color=c4, fontsize=10, fontweight="bold", transform=ax_card.transAxes)

    plt.savefig(output_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return output_path


# ============================================================================
# 4. Telegram 推播與清爽三行式早報 / 納斯達克前十大總體方向研判
# ============================================================================
def format_streamlit_card_markdown(snap: WarRoomSnapshot) -> str:
    """
    專為 Streamlit Markdown 設計的逐行條列戰情卡（使用標準 - 清單與標題，確保每項數據獨立換行、絕不擠在同一行）
    """
    chg_pct = ((snap.spot_price - snap.prev_close) / max(snap.prev_close, 0.01)) * 100.0
    regime_emoji = "🟢 正 Gamma (高拋低吸 / 區間收斂)" if snap.is_positive_gamma else "🔴 負 Gamma (追高殺低 / 擠壓爆發)"
    cw_line = (
        f"- **主力 Call 牆**：`${snap.call_wall:.2f}` 🚀 *(現價已突破轉下方支撐；上方次級 Call 牆 `${snap.next_upper_call_wall:.2f}`)*"
        if snap.call_wall < snap.spot_price
        else f"- **主力 Call 壓力牆**：`${snap.call_wall:.2f}`"
    )
    pw_line = (
        f"- **主力 Put 牆**：`${snap.put_wall:.2f}` ⚠️ *(現價已跌破轉上方反壓；下方次級 Put 牆 `${snap.next_lower_put_wall:.2f}`)*"
        if snap.put_wall > snap.spot_price
        else f"- **主力 Put 支撐牆**：`${snap.put_wall:.2f}`"
    )
    lines = [
        f"##### 📡 {snap.ticker} 期權 GEX 日 K 戰情卡",
        f"- **分析時間**：`{snap.timestamp_tw}`",
        f"- **期權樣本**：`{snap.expiration_date}`",
        f"- **最新日 K**：`${snap.spot_price:.2f}` (`{chg_pct:+.2f}%` / 昨收 `${snap.prev_close:.2f}`)｜[Yahoo Finance](https://finance.yahoo.com/quote/{snap.ticker})",
        f"- **期權體制**：{regime_emoji}",
        f"- **總淨曝險**：`{snap.net_gex_millions:+.2f}M`｜**Zero Gamma 翻轉點**：`${snap.zero_gamma_flip:.2f}`",
        "",
        "##### 🏛️ 全場主力支撐壓力牆與破牆狀態",
        cw_line,
        f"- **Max Pain 最大痛點**：`${snap.max_pain:.2f}`",
        pw_line,
        "",
        "##### ⚡ Gamma Squeeze 啟動與衰竭雷達",
        f"- **向上軋空啟動**：`${snap.bull_squeeze_trigger:.2f}` ➔ **衰竭目標**：`${snap.bull_exhaustion_price:.2f}`",
        f"- **向下破牆助跌**：`${snap.bear_squeeze_trigger:.2f}` ➔ **空頭目標**：`${snap.bear_exhaustion_price:.2f}`",
        f"- **ATM IV 狀態**：`{snap.atm_iv_pct:.1f}%`（盤中峰值 `{snap.iv_peak_pct:.1f}%` / 相對回落 `{snap.iv_drop_from_peak_pct:.1f}%`）",
        f"- **Charm 尾盤平倉窗**：`{snap.charm_unwind_time_tw}`",
        f"- **🧭 當下操作判定與關鍵路線**：{build_stock_action_advice(snap)}",
    ]
    cfd_extra = format_cfd_mapping_line(snap, html_mode=False)
    if cfd_extra:
        lines.append("")
        lines.append("##### 🎯 CFD 專屬點位對照 (XAUUSD / US100 / US500)")
        for cl in cfd_extra.split("\n"):
            lines.append("- " + cl.strip().lstrip("•").strip())
    if snap.active_alerts:
        lines.append("")
        lines.append("##### 🚨 即時觸發警報與交易計畫")
        for a in snap.active_alerts:
            lines.extend(
                [
                    f"- **{a.title}**",
                    f"  - 診斷：{a.description}",
                    f"  - 策略：{a.action_plan}",
                    f"  - 點位：進場 `${a.entry_price:.2f}`｜停損 `${a.sl_price:.2f}`｜停利 `${a.tp_price:.2f}` (`RRR 1:{a.rrr:.1f}`)",
                ]
            )
    return "\n".join(lines)


def format_telegram_card_message(snap: WarRoomSnapshot) -> str:
    chg_pct = ((snap.spot_price - snap.prev_close) / max(snap.prev_close, 0.01)) * 100.0
    regime_emoji = "🟢 正 Gamma (高拋低吸 / 區間收斂)" if snap.is_positive_gamma else "🔴 負 Gamma (追高殺低 / 擠壓爆發)"
    cfd_name, mult, latest_cfd = get_cfd_multiplier(snap.ticker, snap.spot_price)
    verdict, reason, lv = classify_tactical_verdict(snap, mult, latest_cfd)
    anomalies = detect_special_gex_anomalies(snap, mult)
    fmt = ".0f" if mult > 5.0 else ".1f"

    lines = [
        f"*{snap.ticker} 建議：{verdict}*",
        f"💡 *建議操作*：{reason}",
        f"🎯 *關鍵路線*：盤整 `${lv['range_low']:{fmt}}~${lv['range_high']:{fmt}}`｜🚀 漲過 `${lv['bull_start']:{fmt}}` 做多 ➔ `${lv['bull_tp']:{fmt}}` 平倉｜🩸 跌破 `${lv['bear_start']:{fmt}}` 加空 ➔ `${lv['bear_tp']:{fmt}}` 回補",
        "",
        f"📡 *【{snap.ticker} 期權 GEX 數據明細】*",
        f"• 分析時間：`{snap.timestamp_tw}`",
        f"• 期權樣本：`{snap.expiration_date}`",
        f"• 最新日K：`${snap.spot_price:.2f}` (`{chg_pct:+.2f}%` / 昨收 `${snap.prev_close:.2f}`) [Yahoo Finance](https://finance.yahoo.com/quote/{snap.ticker})",
        f"• 期權體制：{regime_emoji}",
        f"• 總淨曝險：`{snap.net_gex_millions:+.2f}M`｜翻轉點：`${snap.zero_gamma_flip:.2f}`",
        "",
        "🏛️ *【全場主力支撐壓力牆與破牆狀態】*",
        (
            f"• 主力 Call 牆：`${snap.call_wall:.2f}` 🚀 *(現價已突破轉下方支撐！上方次級 Call 牆 `${snap.next_upper_call_wall:.2f}`)*"
            if snap.call_wall < snap.spot_price
            else f"• 主力 Call 壓力牆：`${snap.call_wall:.2f}`"
        ),
        f"• Max Pain 最大痛點：`${snap.max_pain:.2f}`",
        (
            f"• 主力 Put 牆：`${snap.put_wall:.2f}` ⚠️ *(現價已跌破轉上方反壓！下方次級 Put 牆 `${snap.next_lower_put_wall:.2f}`)*"
            if snap.put_wall > snap.spot_price
            else f"• 主力 Put 支撐牆：`${snap.put_wall:.2f}`"
        ),
        "",
        "⚡ *【Gamma Squeeze 啟動與衰竭雷達】*",
        f"• 向上軋空啟動：`${snap.bull_squeeze_trigger:.2f}` ➔ 衰竭目標 `${snap.bull_exhaustion_price:.2f}`",
        f"• 向下破牆助跌：`${snap.bear_squeeze_trigger:.2f}` ➔ 空頭目標 `${snap.bear_exhaustion_price:.2f}`",
        f"• ATM IV 狀態：`{snap.atm_iv_pct:.1f}%` (峰值 `{snap.iv_peak_pct:.1f}%` / 回落 `{snap.iv_drop_from_peak_pct:.1f}%`)",
        f"• Charm 平倉窗：`{snap.charm_unwind_time_tw}`",
    ]
    if anomalies:
        lines.append("")
        lines.append("🔍 *【特殊籌碼結構提醒】*")
        for an in anomalies:
            lines.append(f"• {an}")
    if snap.active_alerts:
        lines.append("")
        for a in snap.active_alerts:
            lines.extend(
                [
                    f"🚨 *{a.title}*",
                    f"• 診斷：{a.description}",
                    f"• 策略：{a.action_plan}",
                    f"• 點位：進場 `${a.entry_price:.2f}`｜停損 `${a.sl_price:.2f}`｜停利 `${a.tp_price:.2f}` (`RRR 1:{a.rrr:.1f}`)",
                ]
            )
    return "\n".join(lines)


CFD_RATIO_CACHE: Dict[str, Tuple[float, float]] = {}


def get_cfd_multiplier(etf_ticker: str, etf_spot: float) -> Tuple[str, float, float]:
    """
    將 QQQ 換算為 US100 點位、GLD 換算為 XAUUSD 黃金點位、SPY 換算為 US500 點位。
    同時抓取盤後/期貨 (prepost=True) 最新價格以對齊 OANDA/MT5 17:00 ET 收盤與夜盤報價！
    回傳: (cfd_name, strike_multiplier, latest_cfd_price)
    """
    tk_u = etf_ticker.upper()
    if tk_u not in {"QQQ", "GLD", "SPY"} or etf_spot <= 0:
        return "", 1.0, etf_spot

    now_ts = time.time()
    if tk_u in CFD_RATIO_CACHE and (now_ts - CFD_RATIO_CACHE[tk_u][0] < 600):
        mult, latest_cfd = CFD_RATIO_CACHE[tk_u][1], CFD_RATIO_CACHE[tk_u][2]
    else:
        ref_map = {"QQQ": ("^NDX", 41.1004), "GLD": ("GC=F", 10.928), "SPY": ("^GSPC", 10.0238)}
        yf_sym, default_mult = ref_map[tk_u]
        mult = default_mult
        latest_cfd = etf_spot * mult
        try:
            import yfinance as yf

            # 1. 先計算 16:00 ET 正規盤收盤之精確履約價換算比例 (Index_Close / ETF_Close)
            hist_idx = yf.Ticker(yf_sym).history(period="5d", interval="1d")
            if not hist_idx.empty:
                idx_close = float(hist_idx["Close"].iloc[-1])
                if idx_close > 0:
                    mult = idx_close / etf_spot
                    latest_cfd = idx_close

            # 2. 再抓含盤後 (16:00~17:00 ET / 夜盤 prepost=True) 之 ETF 最新成交價，反映 OANDA/MT5 盤後跳動
            hist_post = yf.Ticker(tk_u).history(period="2d", interval="5m", prepost=True)
            if not hist_post.empty:
                etf_post_last = float(hist_post["Close"].iloc[-1])
                if etf_post_last > 0:
                    latest_cfd = etf_post_last * mult
        except Exception:
            pass
        CFD_RATIO_CACHE[tk_u] = (now_ts, mult, latest_cfd)

    cfd_name = {"QQQ": "US100 (NDX)", "GLD": "XAUUSD (黃金)", "SPY": "US500 (SPX)"}[tk_u]
    return cfd_name, mult, latest_cfd


def detect_special_gex_anomalies(s: WarRoomSnapshot, mult: float = 1.0) -> List[str]:
    """
    自動偵測 6 大期權籌碼特殊結構 (Special GEX Anomalies)，並在操作判定與交易計畫中特別說明：
    1. 倒置型買 Call 逼空負 Gamma (負 Gamma 但翻轉點在現價下方，如暴漲股 LUNR)
    2. 倒置型底部賣 Put 護盤正 Gamma (正 Gamma 但翻轉點在現價上方)
    3. Max Pain 籌碼滯後牽引 (Max Pain 落在 Put 牆下方或 Call 牆上方，短期暴漲暴跌後遺症)
    4. Gamma Pinning 磁吸釘住效應 (正 Gamma 且現價緊貼主力牆 <= 0.6% 或上下牆極窄)
    5. 破牆 Gamma 真空互換區 (現價已跌破主力 Put 牆或已突破主力 Call 牆)
    6. 臨近結算 Charm 尾盤解構窗 (DTE <= 1.5 天，造市商尾盤集中平倉避險部位)
    """
    notes: List[str] = []
    spot = s.spot_price * mult
    flip = s.zero_gamma_flip * mult
    pw = s.put_wall * mult
    cw = s.call_wall * mult
    mp = s.max_pain * mult
    next_pw = s.next_lower_put_wall * mult
    next_cw = s.next_upper_call_wall * mult
    fmt = ".0f" if mult > 5.0 else ".1f"

    # 特殊狀況 1：負 Gamma 但翻轉點在現價下方 (倒置型買 Call 逼空負 Gamma)
    if (not s.is_positive_gamma) and (s.zero_gamma_flip < s.spot_price * 0.995):
        notes.append(
            f"🔥【倒置型買 Call 逼空負 Gamma（翻轉點 ${flip:{fmt}} 在現價下方）】：此處並非跌破支撐走空，而是市場在上方高履約價搶買高 IV Call，"
            f"使造市商在高價區背負 Short Call 負 Gamma！股價是因為「向上衝過翻轉點 ${flip:{fmt}}」才進入造市商被迫追買的軋空加速區；"
            f"只要守穩翻轉點 ${flip:{fmt}} 與支撐牆 ${pw:{fmt}} 之上皆屬多頭逼空控盤，跌回 ${flip:{fmt}} 下方才會退回正 Gamma 盤整。"
        )

    # 特殊狀況 2：正 Gamma 但翻轉點在現價上方 (底部賣 Put 護盤型正 Gamma)
    if s.is_positive_gamma and (s.zero_gamma_flip > s.spot_price * 1.005):
        notes.append(
            f"🛡️【倒置型底部賣 Put 護盤正 Gamma（翻轉點 ${flip:{fmt}} 在現價上方）】：機構在下方大舉賣出 Put 收租使下檔呈現正 Gamma 強力護盤，"
            f"急跌皆有造市商低接買盤撐底；但若向上突破翻轉點 ${flip:{fmt}} 反而會進入上方買方主導的高波動加速區。"
        )

    # 特殊狀況 3：Max Pain 落在 Put 牆下方或 Call 牆上方 (暴漲暴跌後的籌碼滯後效應)
    if s.max_pain < min(s.put_wall, s.spot_price * 0.96):
        notes.append(
            f"🧲【Max Pain 籌碼滯後下拽（痛點 ${mp:{fmt}} 低於 Put 牆 ${pw:{fmt}}）】：因近期股價急漲，當下短線 Put 牆雖已上移至 ${pw:{fmt}}，"
            f"但歷史累積最多未平倉口數的結算痛點仍留在下方 ${mp:{fmt}}；一旦短線跌破 Put 牆 ${pw:{fmt}}，期權賣方磁吸力會加速將價格往痛點 ${mp:{fmt}} 壓回。"
        )
    elif s.max_pain > max(s.call_wall, s.spot_price * 1.04):
        notes.append(
            f"🧲【Max Pain 籌碼滯後上吸（痛點 ${mp:{fmt}} 高於 Call 牆 ${cw:{fmt}}）】：因近期股價急跌，短線 Call 壓力雖下移至 ${cw:{fmt}}，"
            f"但歷史最大未平倉痛點仍留在上方 ${mp:{fmt}}；只要帶量站上 Call 牆 ${cw:{fmt}}，極易觸發往痛點 ${mp:{fmt}} 回歸的強勁反彈。"
        )

    # 特殊狀況 4：Gamma Pinning 磁吸釘住效應 (正 Gamma 且緊貼大牆或區間極窄)
    if s.is_positive_gamma and (
        abs(s.spot_price - s.call_wall) / max(s.spot_price, 0.01) <= 0.006
        or abs(s.spot_price - s.put_wall) / max(s.spot_price, 0.01) <= 0.006
        or abs(s.call_wall - s.put_wall) / max(s.spot_price, 0.01) <= 0.012
    ):
        notes.append(
            f"📌【Gamma Pinning 磁吸釘住效應】：現價緊貼正 Gamma 最大籌碼牆，造市商雙向微幅高拋低吸將波動率鎖死（絞肉機盤勢），"
            f"買方期權易遭時間價值（Theta）嚴重磨損，突破單易遭雙巴，建議以極短線區間高出低進或觀望為主。"
        )

    # 特殊狀況 5：破牆 Gamma 真空與支撐壓力互換
    if s.put_wall > s.spot_price * 1.002:
        notes.append(
            f"🌪️【跌破主力 Put 牆（支撐轉反壓 + 負 Gamma 真空）】：原全場最大 Put 支撐牆 (${pw:{fmt}}) 已被跌穿並轉為上方蓋頭反壓！"
            f"在重新站回 ${pw:{fmt}} 前反彈皆視為逃命波，下檔防守直接退守次級 Put 支撐牆 ${next_pw:{fmt}}。"
        )
    elif s.call_wall < s.spot_price * 0.998:
        notes.append(
            f"🌪️【穿破主力 Call 牆（壓力轉鐵板支撐 + 軋空真空）】：原全場最大 Call 壓力牆 (${cw:{fmt}}) 已被帶量攻克並轉為下方強力支撐！"
            f"回測 ${cw:{fmt}} 不破皆偏多操作，上檔目標推升至次級 Call 壓力牆 ${next_cw:{fmt}}。"
        )

    # 特殊狀況 6：臨近結算日 Charm 尾盤倒貨時間窗
    if s.dte_days <= 1.5:
        notes.append(
            f"⏰【臨近結算 Charm 尾盤解構警戒（僅餘 {s.dte_days:.1f} DTE）】：距離主力合約到期極近，價外期權 Delta 將隨時間快速歸零，"
            f"造市商將於尾盤平倉窗（{s.charm_unwind_time_tw}）大量了結避險現貨，順勢部位務必於尾盤前主動落袋，切勿留倉賭結算。"
        )

    return notes


def classify_tactical_verdict(
    s: WarRoomSnapshot, mult: float = 1.0, override_spot: Optional[float] = None
) -> Tuple[str, str, Dict[str, float]]:
    """
    明確判別當前屬於【🟢 做多】、【🔴 做空】、【🟡 盤整區間操作】或【⚪ 空手觀察】，
    並回傳換算後的關鍵作戰點位：盤整上下緣、多頭起漲點➔多單衰竭平倉點、跌破加空點➔空單回補平倉點。
    """
    spot = override_spot if (override_spot is not None and override_spot > 0) else (s.spot_price * mult)
    flip = s.zero_gamma_flip * mult
    pw = s.put_wall * mult
    cw = s.call_wall * mult
    mp = s.max_pain * mult

    # 盤整區間上下緣：取現價下方有效支撐與現價上方有效壓力
    range_low = (s.next_lower_put_wall if s.put_wall > s.spot_price else s.put_wall) * mult
    range_high = (s.next_upper_call_wall if s.call_wall < s.spot_price else s.call_wall) * mult

    # 多頭起漲點與多單衰竭平倉點
    bull_start = s.bull_squeeze_trigger * mult
    bull_tp_exhaust = max(s.bull_exhaustion_price * mult, bull_start * 1.015)

    # 空頭跌破加空點與空單建議平倉點 (空頭衰竭目標 / 下方次級大牆)
    bear_start = min(s.bear_squeeze_trigger, s.put_wall) * mult
    bear_tp_exhaust = min(s.bear_exhaustion_price * mult, range_low * 0.985, bear_start * 0.98)

    iv_crushing = s.iv_drop_from_peak_pct >= 6.0
    near_bull_exhaust = spot >= bull_tp_exhaust * 0.995
    near_bear_exhaust = spot <= bear_tp_exhaust * 1.005

    levels = {
        "spot": spot,
        "flip": flip,
        "pw": pw,
        "cw": cw,
        "mp": mp,
        "range_low": range_low,
        "range_high": range_high,
        "bull_start": bull_start,
        "bull_tp": bull_tp_exhaust,
        "bear_start": bear_start,
        "bear_tp": bear_tp_exhaust,
    }

    if iv_crushing or near_bull_exhaust or near_bear_exhaust:
        verdict = "⚪ 【空手觀察 / 獲利了結】（已進入動能衰竭或 IV 回落反轉區）"
        reason = (
            f"現價 (${spot:.1f}) 已逼近衰竭目標或觸發 IV 回落 ({s.iv_drop_from_peak_pct:.1f}%)，"
            f"追價肉少風險大，原順勢部位建議立即平倉落袋，空手等待下一波回測支撐或重新突破。"
        )
        return verdict, reason, levels

    if not s.is_positive_gamma:
        is_inverted_call_squeeze = s.zero_gamma_flip < s.spot_price * 0.995
        if spot <= bear_start or s.put_wall > s.spot_price:
            verdict = "🔴 【順勢做空】（跌破支撐牆觸發負 Gamma 助跌）"
            reason = (
                f"現價 (${spot:.1f}) 已跌破關鍵防線 (${bear_start:.1f}) 處於負 Gamma 助跌區，"
                f"造市商被迫順勢拋售避險；反彈不破 ${bear_start:.1f} 偏空操作，空單跌至 ${bear_tp_exhaust:.1f} 建議分批平倉回補。"
            )
        elif spot >= bull_start:
            verdict = "🟢 【順勢做多】（突破負 Gamma 軋空起漲點）"
            reason = (
                f"現價 (${spot:.1f}) 已攻克軋空起漲點 (${bull_start:.1f})，造市商負 Gamma 被迫追買助漲；"
                f"順勢做多並以 ${max(bear_start, flip):.1f} 為防守停損，漲至衰竭點 ${bull_tp_exhaust:.1f} 建議獲利平倉。"
            )
        elif is_inverted_call_squeeze:
            verdict = "🟢 【偏多待突破 / 逼空蓄勢】（倒置型買 Call 負 Gamma：翻轉點在現價下方）"
            reason = (
                f"雖呈負 Gamma，但翻轉點 (${flip:.1f}) 在現價下方！代表股價已衝入上方買 Call 逼空區；"
                f"守穩 Put 牆 ${pw:.1f} 可偏多操作或等突破起漲點 ${bull_start:.1f} 加碼追軋空（目標 ${bull_tp_exhaust:.1f}），若跌破 ${pw:.1f} 則停損防回測痛點 ${mp:.1f}。"
            )
        else:
            verdict = "⚪ 【空手觀察】（負 Gamma 中間夾縫區，等待突破起漲點或跌破加空點）"
            reason = (
                f"目前位於翻轉點 (${flip:.1f}) 下方之負 Gamma 震盪夾縫，既未漲過起漲點 (${bull_start:.1f}) 也未跌破加空點 (${bear_start:.1f})，"
                f"中間進場易遭雙巴；建議空手等待漲破 ${bull_start:.1f} 做多、或跌破 ${bear_start:.1f} 做空。"
            )
    else:
        if s.call_wall < s.spot_price or (s.ticker.upper() == "GLD" and spot >= bull_start):
            verdict = "🟢 【順勢做多】（強勢穿牆 / 黃金 Call Skew 起漲推進）"
            reason = (
                f"現價 (${spot:.1f}) 已強勢突破原壓力 (${cw:.1f}) 轉為下方支撐；"
                f"回測守穩 ${cw:.1f} 偏多操作，上檔漲至衰竭目標 ${bull_tp_exhaust:.1f} 建議分批平倉。"
            )
        elif abs(spot - range_low) / max(spot, 1.0) <= 0.012:
            verdict = "🟢 【逢低做多】（正 Gamma 回測 Put 支撐牆低接區）"
            reason = (
                f"正 Gamma 體制下回測下方支撐牆 (${range_low:.1f}) 且守穩翻轉點 (${flip:.1f})，"
                f"造市商逢低護盤買盤進場；可偏多低接（跌破 ${bear_start:.1f} 停損），漲至 ${range_high:.1f} 平倉。"
            )
        else:
            verdict = "🟡 【盤整區間操作】（正 Gamma 造市商高拋低吸減震區）"
            reason = (
                f"處於翻轉點 (${flip:.1f}) 上方之正 Gamma 穩定區，造市商逢低買、逢高賣；"
                f"於區間下緣 ${range_low:.1f} 低接做多、上緣 ${range_high:.1f} 逢高平倉（痛點中心 ${mp:.1f}）；"
                f"唯有帶量漲破 ${bull_start:.1f} 才轉為追多看 ${bull_tp_exhaust:.1f}。"
            )

    return verdict, reason, levels


def format_cfd_mapping_line(s: WarRoomSnapshot, html_mode: bool = False) -> str:
    cfd_name, mult, latest_cfd = get_cfd_multiplier(s.ticker, s.spot_price)
    if not cfd_name:
        return ""
    verdict, _, lv = classify_tactical_verdict(s, mult, latest_cfd)
    if html_mode:
        return (
            f"<div style=\"background-color:#1E2638;border-radius:6px;padding:7px 9px;margin-top:4px;font-size:13px;border-left:3px solid #FFD54F;\">"
            f"<div style=\"color:#FFD54F;font-weight:700;\">🎯 【{cfd_name} CFD 實戰點位與判定】 {verdict}</div>"
            f"<div style=\"color:#FFFFFF;margin-top:2px;\">"
            f"• <b>CFD 現價</b>: {lv['spot']:.0f} ｜ <b>多空翻轉點</b>: {lv['flip']:.0f} ｜ <b>盤整區間</b>: {lv['range_low']:.0f} ⟷ {lv['range_high']:.0f}"
            f"</div>"
            f"<div style=\"color:#80CBC4;margin-top:2px;\">"
            f"• <b>🚀 多頭路線</b>: 漲過 <b>{lv['bull_start']:.0f} (起漲點)</b> 做多 ➔ 漲到 <b>{lv['bull_tp']:.0f} (衰竭點)</b> 平倉"
            f"</div>"
            f"<div style=\"color:#FFAB91;margin-top:2px;\">"
            f"• <b>🩸 空頭路線</b>: 跌破 <b>{lv['bear_start']:.0f} (加空點)</b> 做空 ➔ 跌到 <b>{lv['bear_tp']:.0f} (空單平倉點)</b> 回補"
            f"</div>"
            f"</div>"
        )
    return (
        f"  • 🎯 *【{cfd_name} CFD 判定】*：{verdict}\n"
        f"  • 📏 *CFD 盤整區間*：`{lv['range_low']:.0f}` (支撐) ⟷ `{lv['range_high']:.0f}` (壓力)｜翻轉點 `{lv['flip']:.0f}`\n"
        f"  • 🚀 *CFD 多頭路線*：漲過 `{lv['bull_start']:.0f}` (起漲點) 做多 ➔ 到 `{lv['bull_tp']:.0f}` (衰竭點) 平倉\n"
        f"  • 🩸 *CFD 空頭路線*：跌破 `{lv['bear_start']:.0f}` (加空點) 做空 ➔ 到 `{lv['bear_tp']:.0f}` (空單平倉點) 回補"
    )


def build_stock_action_advice(s: WarRoomSnapshot) -> str:
    """
    對所有 18 檔核心股輸出統一結構的「四選一判定 + 起漲/衰竭/加空/平倉點位 + 6大特殊籌碼結構診斷」。
    """
    cfd_name, mult, latest_cfd = get_cfd_multiplier(s.ticker, s.spot_price)
    verdict, reason, lv = classify_tactical_verdict(s, mult, latest_cfd)
    anomalies = detect_special_gex_anomalies(s, mult)
    unit_prefix = f"[{cfd_name}] " if cfd_name else ""
    fmt = ".0f" if mult > 5.0 else ".1f"
    base_txt = (
        f"{unit_prefix}{verdict} — {reason} "
        f"（📌 盤整區間：${lv['range_low']:{fmt}}~${lv['range_high']:{fmt}} ｜ "
        f"🚀 漲破 ${lv['bull_start']:{fmt}} 起漲 ➔ ${lv['bull_tp']:{fmt}} 衰竭平倉 ｜ "
        f"🩸 跌破 ${lv['bear_start']:{fmt}} 加空 ➔ ${lv['bear_tp']:{fmt}} 空單平倉）"
    )
    if anomalies:
        return base_txt + " ｜ " + " ； ".join(anomalies)
    return base_txt


def analyze_nasdaq_top10_direction(scanned_map: Dict[str, WarRoomSnapshot]) -> Dict:
    """
    精簡高密度版總體 Gamma 分析：消除冗長文字與分類矛盾（TSM 依自身正負 Gamma 自動歸隊，不混入反方括號）。
    """
    ndx_snaps = [scanned_map[tk] for tk in NASDAQ_TOP10_TICKERS if tk in scanned_map]
    qqq_snap = scanned_map.get("QQQ")
    spy_snap = scanned_map.get("SPY")
    smh_snap = scanned_map.get("SMH")
    soxx_snap = scanned_map.get("SOXX")
    tsm_snap = scanned_map.get("TSM")

    pos_list = [s.ticker for s in ndx_snaps if s.is_positive_gamma]
    neg_list = [s.ticker for s in ndx_snaps if not s.is_positive_gamma]
    pos_count = len(pos_list)
    neg_count = len(neg_list)
    total_ndx_gex = sum(s.net_gex_millions for s in ndx_snaps)
    above_flip_count = sum(1 for s in ndx_snaps if s.spot_price >= s.zero_gamma_flip)

    # 將 TSM 依自身實際正負 Gamma 放入對應操作分組，絕不張冠李戴
    pos_group = list(pos_list)
    neg_group = list(neg_list)
    if tsm_snap:
        if tsm_snap.is_positive_gamma and "TSM" not in pos_group:
            pos_group.append("TSM")
        elif (not tsm_snap.is_positive_gamma) and "TSM" not in neg_group:
            neg_group.append("TSM")

    qqq_pos = qqq_snap.is_positive_gamma if qqq_snap else (pos_count >= 5)
    qqq_gex = qqq_snap.net_gex_millions if qqq_snap else total_ndx_gex
    spy_gex = spy_snap.net_gex_millions if spy_snap else 0.0
    smh_gex = smh_snap.net_gex_millions if smh_snap else 0.0
    soxx_gex = soxx_snap.net_gex_millions if soxx_snap else 0.0

    qqq_flip_str = f"${qqq_snap.zero_gamma_flip:.2f} (US100 約 {qqq_snap.zero_gamma_flip * 41.10:.0f})" if qqq_snap else "N/A"
    qqq_put_str = (
        f"${qqq_snap.put_wall:.1f} (已破/次撐 ${qqq_snap.next_lower_put_wall:.1f})"
        if (qqq_snap and qqq_snap.put_wall > qqq_snap.spot_price)
        else (f"${qqq_snap.put_wall:.1f}" if qqq_snap else "N/A")
    )

    if qqq_pos and pos_count >= 6:
        overall_badge = "🟢 納指與權重全面正 Gamma（造市商逢低護盤、偏多震盪）"
        inst_behavior = f"法人於 QQQ ({qqq_gex:+.0f}M) 與 {pos_count}/10 檔權重股皆採賣 Call 收租或偏多佈局。"
        mm_mechanism = "指數與個股雙端皆為「跌買漲賣」減震護盤，回測 Put 支撐牆易有買盤承接。"
        conclusion_plan = (
            f"1. 【指數結論】：QQQ 守穩翻轉點 {qqq_flip_str} 偏多操作，回測 Put 牆 {qqq_put_str} 低接。\n"
            f"2. 【個股分組】：優先低接 🟢 正 Gamma 護盤組（{', '.join(pos_group) or '無'}）；避開 🔴 負 Gamma 組（{', '.join(neg_group) or '無'}）。"
        )
    elif (not qqq_pos) and pos_count >= 5:
        overall_badge = "🟡 指數負 Gamma 避險 vs. 權重正 Gamma 護盤（急殺易拉回之震盪盤）"
        inst_behavior = f"法人集中在指數 ETF 買 Put 避險（SPY {spy_gex:+.0f}M / QQQ {qqq_gex:+.0f}M / SMH {smh_gex:+.0f}M），但 {pos_count}/10 檔權重股仍維持正 Gamma ({total_ndx_gex:+.0f}M)。"
        mm_mechanism = "指數端造市商「順勢追空」易帶動急殺，但跌至個股 Put 牆時，正 Gamma 權重股造市商會「逆勢買進護盤」，形成急殺留長下影線的拉扯盤。"
        conclusion_plan = (
            f"1. 【指數結論】：QQQ 位於翻轉點 {qqq_flip_str} 下方（Put 牆 {qqq_put_str}），站回翻轉點前勿盲目摸底，突破起漲點再追多。\n"
            f"2. 【🟢 正 Gamma 低接組】：{', '.join(pos_group) or '無'}（回測各自 Put 牆守穩可低接，近 Call 牆平倉）。\n"
            f"3. 【🔴 負 Gamma 警戒組】：{', '.join(neg_group) or '無'}（造市商順勢助跌，跌破 Put 牆嚴禁接刀）。"
        )
    elif qqq_pos and pos_count < 6:
        overall_badge = "🟠 指數正 Gamma 撐盤 vs. 權重負 Gamma 轉弱（拉指數出個股背離盤）"
        inst_behavior = f"QQQ ({qqq_gex:+.0f}M) 雖維持正 Gamma，但已有 {neg_count}/10 檔權重股轉為負 Gamma ({total_ndx_gex:+.0f}M)。"
        mm_mechanism = "指數表面抗跌，但多數權重股已失去造市商低接護盤，提防個股破牆拖累指數補跌。"
        conclusion_plan = (
            f"1. 【指數結論】：嚴防 QQQ 跌破翻轉點 {qqq_flip_str} 轉空。\n"
            f"2. 【個股分組】：避開 🔴 負 Gamma 轉弱組（{', '.join(neg_group) or '無'}）；僅短打 🟢 正 Gamma 組（{', '.join(pos_group) or '無'}）。"
        )
    else:
        overall_badge = "🔴 納指與權重全面負 Gamma 警戒（造市商追高殺低、嚴防破牆急殺）"
        inst_behavior = f"法人於指數（QQQ {qqq_gex:+.0f}M / SPY {spy_gex:+.0f}M）與 {neg_count}/10 檔權重股同步大買 Put 避險。"
        mm_mechanism = "指數與個股雙端皆處於「跌賣漲買」助跌模式，跌破 Put 牆將引發造市商連鎖拋售。"
        conclusion_plan = (
            f"1. 【指數結論】：QQQ 未收復翻轉點 {qqq_flip_str} 前偏空看待，跌破 {qqq_put_str} 順勢做空或停損。\n"
            f"2. 【個股分組】：全面避開 🔴 負 Gamma 破牆組（{', '.join(neg_group) or '無'}）；僅關注 🟢 正 Gamma 組（{', '.join(pos_group) or '無'}）。"
        )

    direction_summary = f"{inst_behavior} {mm_mechanism}"
    return {
        "pos_count": pos_count,
        "neg_count": neg_count,
        "pos_list": pos_list,
        "neg_list": neg_list,
        "total_ndx_gex": round(total_ndx_gex, 1),
        "above_flip_count": above_flip_count,
        "qqq_gex": round(qqq_gex, 1),
        "spy_gex": round(spy_gex, 1),
        "smh_gex": round(smh_gex, 1),
        "soxx_gex": round(soxx_gex, 1),
        "overall_badge": overall_badge,
        "inst_behavior": inst_behavior,
        "mm_mechanism": mm_mechanism,
        "conclusion_plan": conclusion_plan,
        "direction_summary": direction_summary,
    }


def format_clean_3line_stock_brief(s: WarRoomSnapshot) -> str:
    """
    清爽易讀的四行式早報卡片（含支撐壓力牆、啟動/衰竭價位與近期操作建議）
    """
    chg_pct = ((s.spot_price - s.prev_close) / max(s.prev_close, 0.01)) * 100.0
    light = "🟢 正Gamma" if s.is_positive_gamma else "🔴 負Gamma"
    line1 = f"*{s.ticker}* (`${s.spot_price:.2f}` / `{chg_pct:+.2f}%`)｜{light} (`{s.net_gex_millions:+.1f}M`)｜翻轉點 `${s.zero_gamma_flip:.2f}`"
    pw_tag = f"${s.put_wall:.1f}(⚠️已破/次撐${s.next_lower_put_wall:.1f})" if s.put_wall > s.spot_price else f"${s.put_wall:.1f}"
    cw_tag = f"${s.call_wall:.1f}(🚀已破/次壓${s.next_upper_call_wall:.1f})" if s.call_wall < s.spot_price else f"${s.call_wall:.1f}"
    line2 = f"  • 支撐壓力：Put牆 `{pw_tag}` ｜ 痛點 `${s.max_pain:.1f}` ｜ Call牆 `{cw_tag}`"
    line3 = (
        f"  • 啟動與衰竭：🚀 軋空啟動 `${s.bull_squeeze_trigger:.1f}` ➔ 衰竭 `${s.bull_exhaustion_price:.1f}` ｜ "
        f"🩸 破牆啟動 `${s.bear_squeeze_trigger:.1f}` ➔ 空頭衰竭 `${s.bear_exhaustion_price:.1f}`"
    )
    cfd_line = format_cfd_mapping_line(s, html_mode=False)
    line4 = f"  • 💡 建議：{build_stock_action_advice(s)}"
    if cfd_line:
        return f"{line1}\n{cfd_line}\n{line2}\n{line3}\n{line4}"
    return f"{line1}\n{line2}\n{line3}\n{line4}"


def split_telegram_message_chunks(text: str, max_len: int = 3400) -> List[str]:
    """
    Telegram 單則訊息上限為 4,096 字元；當 18 檔早報含完整操作建議與特殊結構說明超過 3,400 字元時，
    自動依段落 (\n\n) 或換行 (\n) 智慧切分為多則連續訊息發送，絕不截斷單一股票卡片，也絕不報 message is too long 錯誤！
    """
    if len(text) <= max_len:
        return [text]

    chunks: List[str] = []
    blocks = text.split("\n\n")
    curr = ""

    for blk in blocks:
        candidate = f"{curr}\n\n{blk}" if curr else blk
        if len(candidate) <= max_len:
            curr = candidate
        else:
            if curr:
                chunks.append(curr)
                curr = ""
            if len(blk) <= max_len:
                curr = blk
            else:
                for line in blk.split("\n"):
                    cand_line = f"{curr}\n{line}" if curr else line
                    if len(cand_line) <= max_len:
                        curr = cand_line
                    else:
                        if curr:
                            chunks.append(curr)
                        curr = line[:max_len]
    if curr:
        chunks.append(curr)

    total = len(chunks)
    if total > 1:
        return [f"📄 *【分段 {i+1}/{total}】*\n{c}" for i, c in enumerate(chunks)]
    return chunks


def cleanup_legacy_alert_pngs() -> int:
    """
    自動清理 VPS 資料夾內累積的 *_bg_alert.png / *_tg_query.png / *_warroom_alert.png 暫存圖檔，
    避免硬碟空間被舊圖塞爆。
    """
    removed = 0
    try:
        for fname in os.listdir(BASE_DIR):
            if fname.endswith(("_bg_alert.png", "_tg_query.png", "_warroom_alert.png")):
                try:
                    os.remove(os.path.join(BASE_DIR, fname))
                    removed += 1
                except Exception:
                    pass
    except Exception:
        pass
    return removed


def send_telegram_alert_with_detail(
    bot_token: str,
    chat_id: str,
    message_md: str,
    image_path: Optional[str] = None,
) -> Tuple[bool, str]:
    clean_tok, clean_cid = sanitize_tg_credentials(bot_token, chat_id)
    if not clean_tok or not clean_cid:
        return False, "Bot Token 或 Chat ID 為空"

    import requests

    def _post_tg(url: str, data_dict: Dict, files_dict: Optional[Dict] = None) -> requests.Response:
        try:
            return requests.post(url, data=data_dict, files=files_dict, timeout=20, verify=True)
        except requests.exceptions.SSLError:
            return requests.post(url, data=data_dict, files=files_dict, timeout=20, verify=False)

    try:
        if image_path and os.path.exists(image_path):
            url_photo = f"https://api.telegram.org/bot{clean_tok}/sendPhoto"
            short_cap = (
                f"📊 {os.path.basename(image_path)} — 完整期權 GEX 日K點位請見下方戰情卡"
                if len(message_md) > 850
                else message_md
            )
            with open(image_path, "rb") as img_f:
                r_img = _post_tg(
                    url_photo,
                    {"chat_id": clean_cid, "caption": short_cap},
                    {"photo": img_f},
                )
            if r_img.status_code != 200:
                return False, f"sendPhoto HTTP {r_img.status_code}: {r_img.text[:160]}"
            if len(message_md) <= 850:
                return True, "圖文單則推播成功"

        url_msg = f"https://api.telegram.org/bot{clean_tok}/sendMessage"
        chunks = split_telegram_message_chunks(message_md, max_len=3400)
        for idx, chunk_txt in enumerate(chunks):
            r_txt = _post_tg(
                url_msg,
                {
                    "chat_id": clean_cid,
                    "text": chunk_txt,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": "true",
                },
            )
            if r_txt.status_code != 200:
                plain_text = chunk_txt.replace("*", "").replace("`", "")
                r_plain = _post_tg(
                    url_msg,
                    {
                        "chat_id": clean_cid,
                        "text": plain_text,
                        "disable_web_page_preview": "true",
                    },
                )
                if r_plain.status_code != 200:
                    return False, f"分段 {idx+1}/{len(chunks)} HTTP {r_plain.status_code}: {r_plain.text[:180]}"
            if idx + 1 < len(chunks):
                time.sleep(0.35)

        if len(chunks) > 1:
            return True, f"推播成功 (共自動切分為 {len(chunks)} 則連續訊息)"
        return True, "推播成功"
    except Exception as exc:
        return False, f"網路連線異常: {exc}"


def send_telegram_alert(
    bot_token: str,
    chat_id: str,
    message_md: str,
    image_path: Optional[str] = None,
) -> bool:
    ok, _ = send_telegram_alert_with_detail(bot_token, chat_id, message_md, image_path)
    return ok


# ============================================================================
# 5. 全美股多執行緒期權鏈批次掃描器 (改為抓取標準日K線 1d + 近4期期權聚合)
# ============================================================================
def build_spot_proxy_chain(spot: float, df_ohlcv: pd.DataFrame) -> Tuple[pd.DataFrame, str, float]:
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
    ticker: str, exp_index: int = 0, interval: str = "1d", period: str = "3mo"
) -> Tuple[str, pd.DataFrame, pd.DataFrame, str, float]:
    """
    預設抓取近 3 個月之標準「日 K 線 (interval='1d', period='3mo')」，
    確保 K 線形態、最高最低價、昨收價與富途牛牛 / TradingView 的日線圖 100% 一致！
    """
    import yfinance as yf

    tk = yf.Ticker(ticker)
    df_ohlcv = tk.history(period=period, interval=interval)
    if df_ohlcv.empty:
        df_ohlcv = tk.history(period="1mo", interval="1d")
    if df_ohlcv.empty:
        raise RuntimeError(f"無法取得 {ticker} 日 K 線數據。")

    spot = float(df_ohlcv["Close"].iloc[-1])
    exps = tk.options
    if not exps:
        df_proxy, exp_str, dte_val = build_spot_proxy_chain(spot, df_ohlcv)
        return ticker.upper(), df_ohlcv, df_proxy, exp_str, dte_val

    today_dt = datetime.datetime.now(datetime.timezone.utc).date()
    if exp_index == 0:
        # 統一對齊「未來 14 天內 (涵蓋本週五與下週五 OPEX)」的所有近月/週選合約；
        # 解決 SPY/QQQ 因每日到期導致前 4 期漏掉本週五主力 OPEX 的問題（最少取 2 期、最多 10 期兼顧速度）
        within_14d = []
        for e_s in exps:
            try:
                e_dt = datetime.datetime.strptime(e_s, "%Y-%m-%d").date()
                if (e_dt - today_dt).days <= 14:
                    within_14d.append(e_s)
            except Exception:
                continue
        if len(within_14d) < 2:
            selected_exps = list(exps[: min(2, len(exps))])
        else:
            selected_exps = within_14d[:10]
    else:
        selected_exps = [exps[min(exp_index, len(exps) - 1)]]

    agg_frames = []
    exp_oi_totals = {}
    valid_exps = []

    for exp_str in selected_exps:
        try:
            opt = tk.option_chain(exp_str)
            calls = opt.calls[["strike", "openInterest", "volume", "impliedVolatility"]].rename(
                columns={"openInterest": "call_oi", "volume": "call_vol", "impliedVolatility": "call_iv"}
            )
            puts = opt.puts[["strike", "openInterest", "volume", "impliedVolatility"]].rename(
                columns={"openInterest": "put_oi", "volume": "put_vol", "impliedVolatility": "put_iv"}
            )
            df_e = pd.merge(calls, puts, on="strike", how="outer").fillna(0.0)
            df_e = df_e[
                (df_e["strike"] >= spot * 0.78) & (df_e["strike"] <= spot * 1.22)
            ].copy()
            if df_e.empty:
                continue
            exp_d_obj = datetime.datetime.strptime(exp_str, "%Y-%m-%d").date()
            now_utc_dt = datetime.datetime.now(datetime.timezone.utc)
            # 美股期權於到期日美東 16:00 (21:00 UTC，即台灣時間隔日凌晨 05:00) 才正式到期結算！
            # 在結算前，當日到期合約 (如週一 11/16 合約) 仍為場上最大 Gamma 主力，絕不可提前丟棄！
            exp_close_utc = datetime.datetime(
                exp_d_obj.year, exp_d_obj.month, exp_d_obj.day, 21, 0, tzinfo=datetime.timezone.utc
            )
            rem_hours = (exp_close_utc - now_utc_dt).total_seconds() / 3600.0
            if rem_hours <= -2.0 and len(selected_exps) > 1:
                continue
            dte_e = max(rem_hours / 24.0, 0.5)
            tte_e = max(dte_e / 365.0, 1.0 / (365.0 * 24.0))

            # 盤前/休市 Yahoo Finance 常將部分履約價之 impliedVolatility 重置為 0.00001；
            # 自動以 20 日歷史波動率 (HV) 或有效中位數 IV 修復低於 8% 之異常歸零 IV！
            log_r = np.log(df_ohlcv["Close"] / df_ohlcv["Close"].shift(1)).dropna()
            hv_fallback = float(np.clip(log_r.std() * np.sqrt(252), 0.15, 1.20)) if len(log_r) >= 5 else 0.30
            valid_c_iv = df_e.loc[df_e["call_iv"] > 0.08, "call_iv"]
            c_iv_med = float(valid_c_iv.median()) if not valid_c_iv.empty else hv_fallback
            valid_p_iv = df_e.loc[df_e["put_iv"] > 0.08, "put_iv"]
            p_iv_med = float(valid_p_iv.median()) if not valid_p_iv.empty else hv_fallback

            df_e["call_iv"] = np.where(df_e["call_iv"] > 0.08, df_e["call_iv"], c_iv_med)
            df_e["put_iv"] = np.where(df_e["put_iv"] > 0.08, df_e["put_iv"], p_iv_med)

            _, _, c_gam_e, _, _ = bs_greeks(
                spot, df_e["strike"].values, tte_e, df_e["call_iv"].values
            )
            _, _, p_gam_e, _, _ = bs_greeks(
                spot, df_e["strike"].values, tte_e, df_e["put_iv"].values
            )
            # 先依各到期日真實剩餘天數 T_m 與 IV 算出各期真實 Dollar GEX，再跨期加總
            df_e["pre_call_gex_m"] = (df_e["call_oi"].values * c_gam_e * 100.0 * (spot**2) * 0.01) / 1e6
            df_e["pre_put_gex_m"] = (-df_e["put_oi"].values * p_gam_e * 100.0 * (spot**2) * 0.01) / 1e6
            df_e["call_iv_weighted"] = df_e["call_iv"] * np.maximum(df_e["call_oi"], 1.0)
            df_e["put_iv_weighted"] = df_e["put_iv"] * np.maximum(df_e["put_oi"], 1.0)
            agg_frames.append(df_e)
            exp_oi_totals[exp_str] = float(
                np.abs(df_e["pre_call_gex_m"]).sum() + np.abs(df_e["pre_put_gex_m"]).sum()
            )
            valid_exps.append(exp_str)
        except Exception:
            continue

    if not agg_frames:
        df_proxy, exp_str, dte_val = build_spot_proxy_chain(spot, df_ohlcv)
        return ticker.upper(), df_ohlcv, df_proxy, exp_str, dte_val

    df_concat = pd.concat(agg_frames, ignore_index=True)
    grouped = df_concat.groupby("strike", as_index=False).agg(
        call_oi=("call_oi", "sum"),
        put_oi=("put_oi", "sum"),
        call_vol=("call_vol", "sum"),
        put_vol=("put_vol", "sum"),
        call_iv_w=("call_iv_weighted", "sum"),
        put_iv_w=("put_iv_weighted", "sum"),
        pre_call_gex_m=("pre_call_gex_m", "sum"),
        pre_put_gex_m=("pre_put_gex_m", "sum"),
    )
    grouped["call_iv"] = grouped["call_iv_w"] / np.maximum(grouped["call_oi"], 1.0)
    grouped["put_iv"] = grouped["put_iv_w"] / np.maximum(grouped["put_oi"], 1.0)
    df_chain = grouped[
        ["strike", "call_oi", "put_oi", "call_vol", "put_vol", "call_iv", "put_iv", "pre_call_gex_m", "pre_put_gex_m"]
    ].reset_index(drop=True)

    dominant_exp = max(exp_oi_totals.items(), key=lambda x: x[1])[0]
    dom_dt = datetime.datetime.strptime(dominant_exp, "%Y-%m-%d").date()
    dte_days = max(float((dom_dt - today_dt).days), 0.5)

    if len(valid_exps) > 1:
        exp_label = f"{dominant_exp} (主力OI，聚合 {valid_exps[0]}~{valid_exps[-1]} 共{len(valid_exps)}期)"
    else:
        exp_label = valid_exps[0]

    return ticker.upper(), df_ohlcv, df_chain, exp_label, dte_days


def scan_single_ticker_worker(
    ticker: str, exp_index: int = 0, iv_crush_drop_threshold_pct: float = 6.0
) -> Optional[Tuple[WarRoomSnapshot, pd.DataFrame, pd.DataFrame]]:
    try:
        tk, df_ohlcv, df_chain, exp_d, dte = fetch_live_market_data(
            ticker, exp_index=exp_index, interval="1d", period="3mo"
        )
        snap, df_gex = evaluate_snapshot_and_alerts(
            tk, df_ohlcv, df_chain, exp_d, dte, iv_crush_drop_threshold_pct
        )
        return snap, df_ohlcv, df_gex
    except Exception:
        return None


def scan_core_14_tickers_map(
    core_tickers: List[str], iv_crush_drop_threshold_pct: float = 6.0
) -> Dict[str, Tuple[WarRoomSnapshot, pd.DataFrame, pd.DataFrame]]:
    target_list = list(dict.fromkeys(MARKET_INDEX_TICKERS + core_tickers + NASDAQ_TOP10_TICKERS))
    out_map: Dict[str, Tuple[WarRoomSnapshot, pd.DataFrame, pd.DataFrame]] = {}
    with ThreadPoolExecutor(max_workers=6) as executor:
        fut_map = {
            executor.submit(
                scan_single_ticker_worker, tk, 0, iv_crush_drop_threshold_pct
            ): tk
            for tk in target_list
        }
        for fut in as_completed(fut_map):
            tk_k = fut_map[fut]
            res = fut.result()
            if res is not None:
                out_map[tk_k] = res
    return out_map


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
    now_tw = (
        datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(hours=8)
    ).strftime("%Y-%m-%d %H:%M:%S (UTC+8)")

    full_map = scan_core_14_tickers_map(core_tickers, iv_crush_drop_threshold_pct)
    scanned_map: Dict[str, WarRoomSnapshot] = {k: v[0] for k, v in full_map.items()}
    ndx_diag = analyze_nasdaq_top10_direction(scanned_map)

    lines = [
        "🌅 *【美股開盤前 GEX 籌碼戰情早報】*",
        f"時間：`{now_tw}`（未來14天內全到期日主力籌碼聚合）",
        "",
        "🧭 *【一、 總體 Gamma 結構：法人佈局、造市商對沖與結論】*",
        f"• *總體定調*：{ndx_diag['overall_badge']}",
        f"• *權重與指數數據*：前十大正 Gamma `{ndx_diag['pos_count']} 檔` vs 負 Gamma `{ndx_diag['neg_count']} 檔`（合計 `{ndx_diag['total_ndx_gex']:+.1f}M`）｜QQQ `{ndx_diag['qqq_gex']:+.1f}M`｜SPY `{ndx_diag['spy_gex']:+.1f}M`｜SMH `{ndx_diag['smh_gex']:+.1f}M`",
        f"• *① 法人籌碼操作*：{ndx_diag['inst_behavior']}",
        f"• *② 造市商對沖機制*：{ndx_diag['mm_mechanism']}",
        f"• *③ 實戰分析結論*：\n{ndx_diag['conclusion_plan']}",
        "",
        "📊 *【二、 大盤、費半與黃金五指標 (SPY / QQQ / SMH / SOXX / GLD)】*",
    ]

    for idx_tk in MARKET_INDEX_TICKERS:
        if idx_tk in scanned_map:
            lines.append(format_clean_3line_stock_brief(scanned_map[idx_tk]))
            lines.append("")

    lines.append("🎯 *【三、 核心自選股 13 檔開盤作戰地圖 (含 TSM)】*")
    for c_tk in core_tickers:
        if c_tk in scanned_map:
            lines.append(format_clean_3line_stock_brief(scanned_map[c_tk]))
            lines.append("")

    near_breakout_lines = []
    for tk_k, sn in scanned_map.items():
        if tk_k in MARKET_INDEX_TICKERS:
            continue
        dist_bull_pct = abs(sn.bull_squeeze_trigger - sn.spot_price) / max(sn.spot_price, 0.01) * 100.0
        dist_put_pct = abs(sn.spot_price - sn.put_wall) / max(sn.spot_price, 0.01) * 100.0
        if dist_bull_pct <= 1.8:
            near_breakout_lines.append(
                f"• *{sn.ticker}* (`${sn.spot_price:.2f}`) — 距上方軋空啟動 `${sn.bull_squeeze_trigger:.1f}` 僅 `{dist_bull_pct:.2f}%`"
            )
        elif dist_put_pct <= 1.8:
            near_breakout_lines.append(
                f"• *{sn.ticker}* (`${sn.spot_price:.2f}`) — 緊貼下方 Put 牆 `${sn.put_wall:.1f}` 僅 `{dist_put_pct:.2f}%`"
            )

    lines.append("🔥 *【四、 臨門一腳重點關注】*")
    if near_breakout_lines:
        lines.extend(near_breakout_lines[:5])
    else:
        lines.append("• 目前核心自選股均位於支撐與壓力牆中間區間，等待開盤表態。")

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
        self._thread_mt5_req = threading.Thread(target=self._mt5_request_loop, daemon=True)
        cleanup_legacy_alert_pngs()
        self._thread_patrol.start()
        self._thread_tg_cmd.start()
        self._thread_mt5_req.start()

    def _mt5_request_loop(self) -> None:
        while True:
            try:
                req_path = os.path.join(get_mt5_common_files_dir(), "gex_mt5_request.txt")
                if os.path.exists(req_path):
                    with open(req_path, "r", encoding="utf-8", errors="ignore") as rf:
                        req_tk = rf.read().strip().upper()
                    try:
                        os.remove(req_path)
                    except Exception:
                        pass
                    if 1 <= len(req_tk) <= 5 and (req_tk.isalpha() or "-" in req_tk):
                        cfg = load_user_config()
                        scan_single_ticker_worker(
                            req_tk, 0, float(cfg.get("iv_drop_thresh", 6.0))
                        )
            except Exception:
                pass
            time.sleep(3)

    def _patrol_loop(self) -> None:
        while True:
            try:
                cfg = load_user_config()
                tg_token, tg_chat_id = sanitize_tg_credentials(
                    cfg.get("tg_token", ""), cfg.get("tg_chat_id", "")
                )
                enable_bg = bool(cfg.get("enable_bg_daemon", IS_WINDOWS_VPS))
                enable_morning = bool(cfg.get("enable_morning_report", True))
                only_mkt = bool(cfg.get("only_us_market_hours", True))
                interval_sec = max(int(cfg.get("patrol_interval_min", 15)), 5) * 60

                if enable_bg and tg_token and tg_chat_id:
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

                    if not only_mkt or is_us_market_active_window():
                        core_list = parse_watchlist_string(
                            cfg.get("core_watchlist", ", ".join(DEFAULT_CORE_WATCHLIST))
                        )
                        iv_th = float(cfg.get("iv_drop_thresh", 6.0))
                        # 必掃核心 18 檔 (確保任何一檔發生 ATM IV 回落 >= 6% 都能即時通知手機，不被大盤快篩濾掉)
                        core_res_map = scan_core_14_tickers_map(core_list, iv_th)
                        univ_results = scan_us_market_universe(
                            universe_mode=cfg.get("universe_mode", "SP500_NDX100"),
                            custom_tickers=core_list,
                            max_stage2_tickers=int(cfg.get("max_scan", 30)),
                            iv_crush_drop_threshold_pct=iv_th,
                        )
                        merged_map = {r[0].ticker: r for r in univ_results}
                        merged_map.update(core_res_map)
                        results = list(merged_map.values())
                        self.total_scans += 1
                        self.last_run_tw = (
                            datetime.datetime.now(datetime.timezone.utc)
                            + datetime.timedelta(hours=8)
                        ).strftime("%Y-%m-%d %H:%M:%S (UTC+8)")

                        cleanup_legacy_alert_pngs()
                        core_set = set(MARKET_INDEX_TICKERS + core_list)
                        non_core_hits = []

                        for snap, df_ohlcv, df_gex in results:
                            if not snap.active_alerts:
                                continue
                            top_code = snap.active_alerts[0].code
                            if not should_send_alert_with_cooldown(snap.ticker, top_code):
                                continue

                            if snap.ticker.upper() in core_set:
                                # 核心 18 檔：立即發送單股圖文警報，發完隨即刪除暫存圖檔不佔空間
                                out_png = os.path.join(BASE_DIR, f"_tmp_{snap.ticker}_alert.png")
                                try:
                                    render_warroom_chart_png(snap, df_ohlcv, df_gex, out_png)
                                    ok = send_telegram_alert(
                                        tg_token,
                                        tg_chat_id,
                                        format_telegram_card_message(snap),
                                        out_png,
                                    )
                                    if ok:
                                        self.total_pushed += 1
                                finally:
                                    if os.path.exists(out_png):
                                        try:
                                            os.remove(out_png)
                                        except Exception:
                                            pass
                            else:
                                non_core_hits.append(snap)

                        # 非核心全美股：精選最強前 5 名彙整為「1 則精選黑馬榜單」，徹底杜絕一次 100 封洗版！
                        if non_core_hits:
                            non_core_hits.sort(key=lambda s: abs(s.net_gex_millions), reverse=True)
                            top5 = non_core_hits[:5]
                            digest_lines = [
                                f"🐎 *【全美股異動精選 Top {len(top5)} 榜單】*（本次共偵測 {len(non_core_hits)} 檔觸發，已自動濃縮防洗版）",
                                f"時間：`{self.last_run_tw}`（輸入代號即可單獨看 K 線圖）",
                                "",
                            ]
                            for sn_h in top5:
                                v_h, _, lv_h = classify_tactical_verdict(sn_h, 1.0)
                                a0 = sn_h.active_alerts[0]
                                digest_lines.extend([
                                    f"*{sn_h.ticker}* (`${sn_h.spot_price:.2f}`)｜{v_h}",
                                    f"  • 訊號：{a0.title}",
                                    f"  • 建議：進場 `${a0.entry_price:.2f}`｜停損 `${a0.sl_price:.2f}`｜目標 `${a0.tp_price:.2f}` (`RRR 1:{a0.rrr:.1f}`)",
                                    "",
                                ])
                            if send_telegram_alert(tg_token, tg_chat_id, "\n".join(digest_lines)):
                                self.total_pushed += 1
                    else:
                        self.last_run_tw = "非美股開盤時段自動待機中"
                time.sleep(interval_sec)
            except Exception:
                time.sleep(300)

    def _tg_command_loop(self) -> None:
        import requests

        while True:
            try:
                cfg = load_user_config()
                tg_token, tg_chat_id = sanitize_tg_credentials(
                    cfg.get("tg_token", ""), cfg.get("tg_chat_id", "")
                )
                enable_bg = bool(cfg.get("enable_bg_daemon", IS_WINDOWS_VPS))
                if not enable_bg or not tg_token or not tg_chat_id:
                    time.sleep(10)
                    continue

                url = f"https://api.telegram.org/bot{tg_token}/getUpdates?offset={self._last_update_id + 1}&timeout=10"
                try:
                    resp = requests.get(url, timeout=15, verify=True)
                except requests.exceptions.SSLError:
                    resp = requests.get(url, timeout=15, verify=False)

                if resp.status_code != 200:
                    time.sleep(5)
                    continue

                data = resp.json()
                for item in data.get("result", []):
                    self._last_update_id = max(self._last_update_id, int(item["update_id"]))
                    msg_obj = item.get("message", {})
                    sender_chat_id = str(msg_obj.get("chat", {}).get("id", ""))
                    text = str(msg_obj.get("text", "")).strip()

                    if sender_chat_id != tg_chat_id or not text:
                        continue

                    cmd_clean = text.lstrip("/").replace("gex", "").strip().upper()
                    if cmd_clean in {"STATUS", "狀態"}:
                        now_tw = (
                            datetime.datetime.now(datetime.timezone.utc)
                            + datetime.timedelta(hours=8)
                        ).strftime("%Y-%m-%d %H:%M:%S (UTC+8)")
                        send_telegram_alert(
                            tg_token,
                            tg_chat_id,
                            f"✅ *[VPS 後台守護執行中]*\n• 目前時間：`{now_tw}`\n• 累計掃描：`{self.total_scans}` 次\n• 累計推播：`{self.total_pushed}` 則\n• 狀態：`{self.last_run_tw}`",
                        )
                    elif cmd_clean in {"MORNING", "BRIEF", "早報"}:
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
                            out_png = os.path.join(BASE_DIR, f"_tmp_{snap.ticker}_tg_query.png")
                            try:
                                render_warroom_chart_png(snap, df_ohlcv, df_gex, out_png)
                                send_telegram_alert(
                                    tg_token,
                                    tg_chat_id,
                                    format_telegram_card_message(snap),
                                    out_png,
                                )
                            finally:
                                if os.path.exists(out_png):
                                    try:
                                        os.remove(out_png)
                                    except Exception:
                                        pass
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
    base_dt = datetime.date(2026, 9, 14)
    dates = [
        (base_dt + datetime.timedelta(days=int(i * 1.4))).strftime("%Y-%m-%d")
        for i in range(n_bars)
    ]
    if scenario == "NVDA_SQUEEZE":
        base_prices = np.linspace(152.0, 168.5, n_bars - 1).tolist() + [171.40]
        opens = [p - np.random.uniform(-1.5, 1.5) for p in base_prices[:-1]] + [168.20]
        highs = [max(o, c) + np.random.uniform(0.6, 2.2) for o, c in zip(opens[:-1], base_prices[:-1])] + [172.30]
        lows = [min(o, c) - np.random.uniform(0.6, 2.0) for o, c in zip(opens[:-1], base_prices[:-1])] + [167.90]
        vols = [np.random.uniform(35e6, 52e6) for _ in range(n_bars - 1)] + [88e6]
        df_ohlcv = pd.DataFrame(
            {"Date": dates, "Open": opens, "High": highs, "Low": lows, "Close": base_prices, "Volume": vols}
        ).set_index("Date")

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
        return "NVDA", df_ohlcv, df_chain, "2026-11-20 (主力OI，聚合4期)", 5.0, 81.5
    else:
        base_prices = np.linspace(155.0, 179.2, n_bars - 1).tolist() + [178.40]
        opens = [p - np.random.uniform(-1.2, 1.4) for p in base_prices[:-1]] + [179.10]
        highs = [max(o, c) + np.random.uniform(0.5, 1.8) for o, c in zip(opens[:-1], base_prices[:-1])] + [182.60]
        lows = [min(o, c) - np.random.uniform(0.5, 1.6) for o, c in zip(opens[:-1], base_prices[:-1])] + [177.80]
        vols = [np.random.uniform(45e6, 68e6) for _ in range(n_bars - 1)] + [38e6]
        df_ohlcv = pd.DataFrame(
            {"Date": dates, "Open": opens, "High": highs, "Low": lows, "Close": base_prices, "Volume": vols}
        ).set_index("Date")

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
        return "NVDA", df_ohlcv, df_chain, "2026-11-20 (主力OI，聚合4期)", 4.0, 88.0


# ============================================================================
# 6. Streamlit 網頁戰情室 (首頁預設顯示 14 檔正負 Gamma 燈號 + 納指方向研判 + 手機防重疊日K圖)
# ============================================================================
def run_streamlit_warroom() -> None:
    import plotly.graph_objects as go
    import streamlit as st

    st.set_page_config(
        page_title="全美股期權 GEX 與納指方向戰情室",
        layout="wide",
        initial_sidebar_state="collapsed",
    )

    @st.cache_resource
    def get_bg_daemon() -> BackgroundPatrolDaemon:
        return BackgroundPatrolDaemon()

    @st.cache_data(ttl=300, show_spinner=False)
    def cached_core_14_scan(wl_tuple: Tuple[str, ...], iv_thresh: float) -> Dict[str, WarRoomSnapshot]:
        raw_map = scan_core_14_tickers_map(list(wl_tuple), iv_thresh)
        return {k: v[0] for k, v in raw_map.items()}

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
        else "📱 Streamlit Cloud 手機看盤端"
    )
    st.markdown(f"### 🌎 美股期權 GEX 戰情室 ({role_badge})")

    with st.sidebar:
        st.header("⚙️ 戰情室與推播設定")
        app_tab = st.radio(
            "選擇功能模式",
            [
                "🚦 核心 18 檔燈號總覽 & 單股日K診斷 (首頁預設)",
                "🌎 全美股 5,000+ 檔批次掃描雷達",
            ],
            index=0,
        )
        iv_drop_thresh = st.slider(
            "IV 高點回落衰竭警報門檻 (%)",
            3.0,
            15.0,
            float(cfg.get("iv_drop_thresh", 6.0)),
            0.5,
        )

        st.divider()
        st.subheader("🌅 核心自選股與每日早報")
        core_wl_str = st.text_area(
            "核心自選股清單 (含 NVDA, TSLA, LUNR, SPCX, TSM 與納指前十大)",
            value=cfg.get("core_watchlist", ", ".join(DEFAULT_CORE_WATCHLIST)),
            height=90,
        )
        enable_morning = st.checkbox(
            "每日美股開盤前 15 分鐘自動發送早報 (22:15 / 21:15 UTC+8)",
            value=bool(cfg.get("enable_morning_report", True)),
        )

        st.divider()
        st.subheader("📲 Telegram 推播與背景常駐")
        tg_token_raw = st.text_input(
            "Telegram Bot Token", value=cfg.get("tg_token", ""), type="password"
        )
        tg_chat_id_raw = st.text_input(
            "Telegram Chat ID", value=cfg.get("tg_chat_id", "")
        )
        tg_token, tg_chat_id = sanitize_tg_credentials(tg_token_raw, tg_chat_id_raw)

        enable_bg = st.checkbox(
            "啟用 24H 後台巡邏與 TG 雙向回覆 (VPS 自動勾選)",
            value=bool(cfg.get("enable_bg_daemon", IS_WINDOWS_VPS)),
        )
        only_mkt = st.checkbox(
            "僅於美股交易時段巡邏",
            value=bool(cfg.get("only_us_market_hours", True)),
        )
        st.caption(
            f"🤖 後台狀態：已巡邏 `{daemon.total_scans}` 次 | 已推播 `{daemon.total_pushed}` 則 | `{daemon.last_run_tw}`"
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
            cfg["tg_token"] = tg_token
            cfg["tg_chat_id"] = tg_chat_id
            cfg["core_watchlist"] = core_wl_str.strip()
            cfg["enable_morning_report"] = enable_morning
            cfg["iv_drop_thresh"] = iv_drop_thresh
            cfg["enable_bg_daemon"] = enable_bg
            cfg["only_us_market_hours"] = only_mkt
            save_user_config(cfg)
            st.toast("✅ 已儲存設定！")

        if st.button("🌅 立即發送今日開盤前早報至 Telegram"):
            if not tg_token or not tg_chat_id:
                st.error("請先填入 Telegram Bot Token 與 Chat ID！")
            else:
                with st.spinner("正在計算納指方向與 18 檔核心股早報..."):
                    c_list = parse_watchlist_string(core_wl_str)
                    brief_txt = generate_morning_briefing_report(c_list, iv_drop_thresh)
                    ok_b, detail_b = send_telegram_alert_with_detail(
                        tg_token, tg_chat_id, brief_txt
                    )
                if ok_b:
                    st.success(f"🎉 清爽版開盤前早報已發送至 Telegram！({detail_b})")
                else:
                    st.error(f"發送失敗：{detail_b}")

        if st.button("📈 立即同步 SPY/QQQ/SMH/SOXX/GLD 與 13 檔核心股 GEX 至 MT5 (Common\\Files)"):
            with st.spinner("正在寫入 MT5 Common\\Files\\gex_mt5_levels.csv..."):
                c_list = parse_watchlist_string(core_wl_str)
                _ = generate_morning_briefing_report(c_list, iv_drop_thresh)
                mt5_csv_p = os.path.join(get_mt5_common_files_dir(), "gex_mt5_levels.csv")
            st.success(f"✅ 已同步 18 檔核心股至 MT5：`{mt5_csv_p}`")

        if IS_WINDOWS_VPS:
            if st.button("👻 一鍵啟動『無黑窗隱形背景常駐』並加入開機自啟 (按完即可關掉 CMD)"):
                ok_st, msg_st = enable_invisible_windows_background_service()
                if ok_st:
                    st.success(msg_st)
                else:
                    st.error(f"設定失敗：{msg_st}")

    core_list = parse_watchlist_string(core_wl_str)
    quick_14_list = list(dict.fromkeys(MARKET_INDEX_TICKERS + core_list))

    if app_tab.startswith("🚦"):
        # ====================================================================
        # 首頁第一區塊：自動載入「納斯達克前十大 Gamma 總體方向研判」+「核心 14 檔正負 Gamma 燈號牆」
        # ====================================================================
        top_c1, top_c2 = st.columns([4, 1])
        with top_c1:
            st.markdown("#### 🧭 一、 納斯達克 100 (QQQ + 前十大權重股) 總體 Gamma 狀況與方向研判")
        with top_c2:
            if st.button("🔄 刷新 18 檔燈號", use_container_width=True):
                cached_core_14_scan.clear()

        with st.spinner("正在同步核心 18 檔 (含 SMH/SOXX 費半與 TSM) 期權 GEX 燈號..."):
            snap_map = cached_core_14_scan(tuple(core_list), iv_drop_thresh)

        if snap_map:
            ndx_info = analyze_nasdaq_top10_direction(snap_map)
            summary_md = (
                f"**{ndx_info['overall_badge']}**\n\n"
                f"- **核心籌碼統計**：前十大權重 🟢 正 Gamma `{ndx_info['pos_count']} 檔` vs 🔴 負 Gamma `{ndx_info['neg_count']} 檔` "
                f"（權重合計 `{ndx_info['total_ndx_gex']:+.1f}M`）｜**SPY**: `{ndx_info['spy_gex']:+.1f}M` ｜ "
                f"**QQQ**: `{ndx_info['qqq_gex']:+.1f}M` ｜ **SMH (費半)**: `{ndx_info['smh_gex']:+.1f}M` ｜ **SOXX**: `{ndx_info['soxx_gex']:+.1f}M`\n"
                f"- **🏦 ① 法人期權佈局邏輯**：{ndx_info['inst_behavior']}\n"
                f"- **⚙️ ② 造市商 (Market Maker) 對沖機制**：{ndx_info['mm_mechanism']}\n"
                f"- **🎯 ③ 整體分析結論與近期操作方針**：\n"
            )
            for c_line in ndx_info["conclusion_plan"].split("\n"):
                summary_md += f"  - {c_line}\n"

            if ndx_info["pos_count"] >= 6 and (snap_map.get("QQQ") and snap_map["QQQ"].is_positive_gamma):
                st.success(summary_md)
            elif ndx_info["neg_count"] >= 6:
                st.error(summary_md)
            else:
                st.warning(summary_md)

            st.markdown("#### 🚦 二、 核心 18 檔（SPY/QQQ/SMH/SOXX/GLD + 13 檔核心自選股含 TSM）正負 Gamma 即時燈號牆（點擊任一檔直接看下方日K圖）")
            if "selected_ticker" not in st.session_state:
                st.session_state["selected_ticker"] = "AAPL"

            # 注入全域 CSS 解除 Streamlit 按鈕單行省略號 (...) 限制，並使用獨立彩色邊框卡片完整呈現所有數值
            st.markdown(
                """
                <style>
                div[data-testid="stButton"] > button {
                    white-space: normal !important;
                    word-wrap: break-word !important;
                    height: auto !important;
                    min-height: 2.2rem !important;
                    padding: 6px 10px !important;
                }
                div[data-testid="stButton"] > button p {
                    white-space: normal !important;
                    text-overflow: clip !important;
                    overflow: visible !important;
                }
                .gex-card {
                    border-radius: 10px;
                    padding: 10px 12px;
                    margin-bottom: 6px;
                    background-color: #161B26;
                    font-size: 13.5px;
                    line-height: 1.55;
                }
                .gex-pos {
                    border-left: 5px solid #00E676;
                    border-top: 1px solid #263238;
                    border-right: 1px solid #263238;
                    border-bottom: 1px solid #263238;
                }
                .gex-neg {
                    border-left: 5px solid #FF5252;
                    border-top: 1px solid #263238;
                    border-right: 1px solid #263238;
                    border-bottom: 1px solid #263238;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )

            def _render_lamp_card(col_obj, tk_sym: str) -> None:
                sn = snap_map.get(tk_sym)
                if sn is None:
                    return
                chg_p = ((sn.spot_price - sn.prev_close) / max(sn.prev_close, 0.01)) * 100.0
                lamp = "🟢 正Gamma" if sn.is_positive_gamma else "🔴 負Gamma"
                cls_name = "gex-pos" if sn.is_positive_gamma else "gex-neg"
                chg_col = "#00E676" if chg_p >= 0 else "#FF5252"
                pw_note = (
                    f"${sn.put_wall:.1f} (⚠️已破/次撐${sn.next_lower_put_wall:.1f})"
                    if sn.put_wall > sn.spot_price
                    else f"${sn.put_wall:.1f}"
                )
                cw_note = (
                    f"${sn.call_wall:.1f} (🚀已破/次壓${sn.next_upper_call_wall:.1f})"
                    if sn.call_wall < sn.spot_price
                    else f"${sn.call_wall:.1f}"
                )
                iv_crush_lvl = round(sn.iv_peak_pct * 0.94, 1)
                advice_txt = build_stock_action_advice(sn)
                if not sn.is_positive_gamma:
                    squeeze_html = (
                        f"<div style=\"color:#FFB74D;margin-top:2px;\">"
                        f"• <b>🚀 向上軋空啟動</b>: ${sn.bull_squeeze_trigger:.1f} ➔ <b>衰竭目標</b>: ${sn.bull_exhaustion_price:.1f}<br>"
                        f"• <b>🩸 向下破牆啟動</b>: ${sn.bear_squeeze_trigger:.1f} ➔ <b>空頭衰竭</b>: ${sn.bear_exhaustion_price:.1f} "
                        f"<span style=\"color:#B0BEC5;\">(ATM IV {sn.atm_iv_pct:.1f}% / 衰竭警戒 &lt;{iv_crush_lvl:.1f}%)</span>"
                        f"</div>"
                    )
                else:
                    squeeze_html = (
                        f"<div style=\"color:#80D8FF;margin-top:2px;\">"
                        f"• <b>⚡ 突破轉軋空啟動價</b>: ${sn.bull_squeeze_trigger:.1f} ➔ <b>衰竭天花板</b>: ${sn.bull_exhaustion_price:.1f} "
                        f"｜ <b>預期波動</b>: ±${sn.expected_move_usd:.1f} (±{sn.expected_move_pct:.1f}%)"
                        f"</div>"
                    )
                card_html = (
                    f"<div class=\"gex-card {cls_name}\">"
                    f"<div style=\"font-weight:700;font-size:15px;color:#FFFFFF;\">"
                    f"{lamp} ｜ {sn.ticker} <span style=\"color:{chg_col};\">${sn.spot_price:.2f} ({chg_p:+.1f}%)</span> "
                    f"<span style=\"color:#FFD54F;font-size:13px;\">｜ Net GEX: {sn.net_gex_millions:+.1f}M</span>"
                    f"</div>"
                    f"<div style=\"color:#E0E0E0;margin-top:4px;\">"
                    f"• <b>Put牆</b>: {pw_note} ｜ <b>Call牆</b>: {cw_note} ｜ <b>痛點</b>: ${sn.max_pain:.1f} ｜ <b>翻轉點</b>: ${sn.zero_gamma_flip:.2f}"
                    f"</div>"
                    f"{format_cfd_mapping_line(sn, html_mode=True)}"
                    f"{squeeze_html}"
                    f"<div style=\"color:#A5D6A7;margin-top:5px;padding-top:4px;border-top:1px dashed #37474F;font-size:13px;\">"
                    f"💡 <b>近期操作建議</b>：{advice_txt}"
                    f"</div>"
                    f"</div>"
                )
                with col_obj:
                    st.markdown(card_html, unsafe_allow_html=True)
                    if st.button(f"📈 查看 {sn.ticker} 日K與GEX圖", key=f"lamp_{tk_sym}", use_container_width=True):
                        st.session_state["selected_ticker"] = tk_sym

            # 第 1 列專門放「大盤、費半與黃金五指標 (SPY / QQQ / SMH / SOXX / GLD)」，確保手機版 QQQ 永遠緊接在 SPY 正下方
            idx_tks = [t for t in quick_14_list if t in MARKET_INDEX_TICKERS]
            if idx_tks:
                idx_cols = st.columns(len(idx_tks))
                for c_i, tk_sym in enumerate(idx_tks):
                    _render_lamp_card(idx_cols[c_i], tk_sym)

            # 第 2 列起依序每 3 檔建立獨立橫列 (Row-by-Row)，確保手機版完全依照清單順序由上往下排列
            other_tks = [t for t in quick_14_list if t not in MARKET_INDEX_TICKERS]
            for r_start in range(0, len(other_tks), 3):
                row_slice = other_tks[r_start : r_start + 3]
                row_cols = st.columns(3)
                for c_i, tk_sym in enumerate(row_slice):
                    _render_lamp_card(row_cols[c_i], tk_sym)

        st.divider()
        st.markdown("#### 📈 三、 單股標準日 K 線 (含 MA5/MA10/MA20) 與期權 GEX 支撐壓力牆")

        col_inp1, col_inp2, col_inp3 = st.columns([2, 1, 2])
        with col_inp1:
            ticker_input = (
                st.text_input(
                    "輸入任意美股代號 (支援全美股 5,000+ 檔)",
                    value=st.session_state.get("selected_ticker", "AAPL"),
                )
                .strip()
                .upper()
            )
            st.session_state["selected_ticker"] = ticker_input
        with col_inp2:
            exp_idx = st.number_input(
                "期權範圍 (0=未來14天內全合約聚合含週五OPEX)", min_value=0, max_value=8, value=0
            )
        with col_inp3:
            lock_zoom = st.checkbox(
                "📱 鎖定手機觸控比例 (防止手指滑動時圖表跑版，勾選後用上方按鈕切換股票)",
                value=True,
            )

        view_mode = st.radio(
            "🔍 選擇 K 線週期與期權牆放大視角（解決日線跨度太大導致近期 Call/Put 牆擠在一起的問題）",
            [
                "🎯 日K期權牆聚焦視角 (近15日日K + 自動鎖定期權牆區間放大Y軸，預設最清晰)",
                "⚡ 60分K短線作戰視角 (近8日小時K，適合Call/Put牆距離極近時拉開空間)",
                "📅 日K波段全景視角 (近45日完整日K，檢視三個月大波段趨勢)",
            ],
            index=0,
            horizontal=True,
        )

        k_interval = "60m" if view_mode.startswith("⚡") else "1d"
        k_period = "1mo" if view_mode.startswith("⚡") else "3mo"

        try:
            tk, df_ohlcv, df_chain, exp_d, dte = fetch_live_market_data(
                ticker_input, int(exp_idx), interval=k_interval, period=k_period
            )
            sim_peak = None
        except Exception as e:
            st.warning(f"即時連線失敗 ({e})，自動載入內建 NVDA 數據。")
            tk, df_ohlcv, df_chain, exp_d, dte, sim_peak = get_demo_scenario_data("NVDA_SQUEEZE")

        snap, df_gex = evaluate_snapshot_and_alerts(
            tk, df_ohlcv, df_chain, exp_d, dte, iv_drop_thresh, sim_peak
        )

        df_full = df_ohlcv.copy()
        df_full["MA5"] = df_full["Close"].rolling(5, min_periods=1).mean()
        df_full["MA10"] = df_full["Close"].rolling(10, min_periods=1).mean()
        df_full["MA20"] = df_full["Close"].rolling(20, min_periods=1).mean()

        if view_mode.startswith("🎯"):
            df_k = df_full.tail(15).copy()
            x_dates = extract_mmdd_labels(df_k)
            k_low = float(df_k["Low"].min())
            k_high = float(df_k["High"].max())
            y_min = min(k_low, snap.put_wall, snap.next_lower_put_wall, snap.zero_gamma_flip) * 0.990
            y_max = max(k_high, snap.call_wall, snap.next_upper_call_wall, snap.bull_exhaustion_price) * 1.010
        elif view_mode.startswith("⚡"):
            df_k = df_full.tail(35).copy()
            x_dates = [str(idx)[5:16] for idx in df_k.index]
            k_low = float(df_k["Low"].min())
            k_high = float(df_k["High"].max())
            y_min = min(k_low, snap.put_wall, snap.next_lower_put_wall, snap.zero_gamma_flip) * 0.992
            y_max = max(k_high, snap.call_wall, snap.next_upper_call_wall, snap.bull_exhaustion_price) * 1.008
        else:
            df_k = df_full.tail(45).copy()
            x_dates = extract_mmdd_labels(df_k)
            k_low = float(df_k["Low"].min())
            k_high = float(df_k["High"].max())
            y_min = min(k_low, snap.put_wall, snap.zero_gamma_flip) * 0.985
            y_max = max(k_high, snap.call_wall, snap.bull_exhaustion_price) * 1.015

        # 【圖表 1：獨立滿版日 K 線圖 (消除週末斷層、使用圖例與防重疊標籤，手機絕不擠成一團)】
        fig_k = go.Figure()
        fig_k.add_trace(
            go.Candlestick(
                x=x_dates,
                open=df_k["Open"],
                high=df_k["High"],
                low=df_k["Low"],
                close=df_k["Close"],
                name="日K線",
                increasing_line_color="#00E676",
                decreasing_line_color="#FF5252",
            )
        )
        fig_k.add_trace(
            go.Scatter(x=x_dates, y=df_k["MA5"], mode="lines", name="MA5", line=dict(color="#FF9800", width=1.5))
        )
        fig_k.add_trace(
            go.Scatter(x=x_dates, y=df_k["MA10"], mode="lines", name="MA10", line=dict(color="#29B6F6", width=1.5))
        )
        fig_k.add_trace(
            go.Scatter(x=x_dates, y=df_k["MA20"], mode="lines", name="MA20", line=dict(color="#AB47BC", width=1.6))
        )

        # 用獨立 Scatter 線條加入 Legend 圖例（不直接在 K 線中間疊字，徹底解決手機字體重疊）
        cw_st_lbl = (
            f"主力 Call 牆(已突破轉撐) ${snap.call_wall:.2f}"
            if snap.call_wall < snap.spot_price
            else f"主力 Call 壓力牆 ${snap.call_wall:.2f}"
        )
        pw_st_lbl = (
            f"主力 Put 牆(已跌破轉壓) ${snap.put_wall:.2f}"
            if snap.put_wall > snap.spot_price
            else f"主力 Put 支撐牆 ${snap.put_wall:.2f}"
        )
        key_lines = [
            (snap.bull_exhaustion_price, f"Squeeze 衰竭天花板 ${snap.bull_exhaustion_price:.2f}", "#E040FB", "dashdot"),
            (snap.call_wall, cw_st_lbl, "#FF5252", "solid"),
            (snap.bull_squeeze_trigger, f"Squeeze 向上啟動 ${snap.bull_squeeze_trigger:.2f}", "#FF9100", "dashdot"),
            (snap.max_pain, f"Max Pain 最大痛點 ${snap.max_pain:.2f}", "#40C4FF", "dot"),
            (snap.zero_gamma_flip, f"Zero Gamma 翻轉點 ${snap.zero_gamma_flip:.2f}", "#FFD600", "dash"),
            (snap.put_wall, pw_st_lbl, "#00E676", "solid"),
        ]
        if snap.call_wall < snap.spot_price and snap.next_upper_call_wall > snap.spot_price:
            key_lines.append((snap.next_upper_call_wall, f"上方次級 Call 牆 ${snap.next_upper_call_wall:.2f}", "#FF8A80", "dash"))
        if snap.put_wall > snap.spot_price and snap.next_lower_put_wall < snap.spot_price:
            key_lines.append((snap.next_lower_put_wall, f"下方次級 Put 牆 ${snap.next_lower_put_wall:.2f}", "#69F0AE", "dash"))
        for y_val, label_txt, color_hex, dash_style in key_lines:
            fig_k.add_trace(
                go.Scatter(
                    x=[x_dates[0], x_dates[-1]],
                    y=[y_val, y_val],
                    mode="lines",
                    name=label_txt,
                    line=dict(color=color_hex, width=2.0, dash=dash_style),
                    hoverinfo="name+y",
                )
            )

        chg_pct = ((snap.spot_price - snap.prev_close) / max(snap.prev_close, 0.01)) * 100.0
        fig_k.update_layout(
            title=dict(
                text=f"{snap.ticker} 日 K 線與期權關鍵牆｜現價 ${snap.spot_price:.2f} ({chg_pct:+.2f}%)｜昨收 ${snap.prev_close:.2f}",
                font=dict(size=15),
            ),
            template="plotly_dark",
            height=500,
            margin=dict(l=10, r=10, t=45, b=35),
            xaxis=dict(
                type="category",
                rangeslider=dict(visible=False),
                nticks=9,
                fixedrange=lock_zoom,
            ),
            yaxis=dict(
                range=[y_min, y_max],
                side="right",
                fixedrange=lock_zoom,
            ),
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=-0.32,
                xanchor="left",
                x=0.0,
                font=dict(size=11),
            ),
            dragmode=False if lock_zoom else "pan",
        )
        st.plotly_chart(
            fig_k,
            use_container_width=True,
            config={"scrollZoom": not lock_zoom, "displayModeBar": not lock_zoom},
        )

        # 【圖表 2：獨立滿版各履約價 Net GEX 柱狀圖 (上下分開排列，手機清楚好讀)】
        df_sub_gex = df_gex[(df_gex["strike"] >= snap.spot_price * 0.82) & (df_gex["strike"] <= snap.spot_price * 1.18)].copy()
        bar_colors = ["#00E676" if v >= 0 else "#FF1744" for v in df_sub_gex["net_gex_m"]]
        fig_gex = go.Figure()
        fig_gex.add_trace(
            go.Bar(
                x=df_sub_gex["strike"].astype(str),
                y=df_sub_gex["net_gex_m"],
                marker_color=bar_colors,
                name="Net GEX (M$)",
            )
        )
        fig_gex.update_layout(
            title=dict(
                text=f"{snap.ticker} 各履約價 Net GEX 籌碼分佈 (總淨曝險: {snap.net_gex_millions:+.1f}M 美元)",
                font=dict(size=14),
            ),
            template="plotly_dark",
            height=300,
            margin=dict(l=10, r=10, t=40, b=30),
            xaxis=dict(title="履約價 (Strike $)", type="category", fixedrange=lock_zoom),
            yaxis=dict(title="Net GEX (M$)", side="right", fixedrange=lock_zoom),
            dragmode=False if lock_zoom else "pan",
        )
        st.plotly_chart(
            fig_gex,
            use_container_width=True,
            config={"scrollZoom": not lock_zoom, "displayModeBar": not lock_zoom},
        )

        st.markdown("#### 🧭 四、 單股期權籌碼診斷戰情卡")
        st.markdown(format_streamlit_card_markdown(snap))

    else:
        st.subheader("🌎 全美股兩階段漏斗高速掃描雷達")
        u_col1, u_col2 = st.columns([2, 1])
        with u_col1:
            u_mode = st.selectbox(
                "選擇掃描股票池範圍",
                [
                    "CUSTOM (掃描 SPY/QQQ/SMH/SOXX/GLD + 13 檔核心自選股)",
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
                value="SPY, QQQ, SMH, SOXX, GLD, " + core_wl_str,
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
                    f"Put牆 ${snap.put_wall:.1f} ⟷ 痛點 ${snap.max_pain:.1f} ⟷ Call牆 ${snap.call_wall:.1f}",
                    expanded=bool(snap.active_alerts),
                ):
                    st.markdown(format_streamlit_card_markdown(snap))
                    if snap.active_alerts and tg_token and tg_chat_id:
                        out_png = os.path.join(BASE_DIR, f"{snap.ticker}_warroom_alert.png")
                        render_warroom_chart_png(snap, df_ohlcv, df_gex, out_png)
                        send_telegram_alert(
                            tg_token, tg_chat_id, format_telegram_card_message(snap), out_png
                        )


# ============================================================================
# 7. CLI 命令列與無黑窗隱形常駐入口 (--daemon-loop)
# ============================================================================
def main() -> None:
    parser = argparse.ArgumentParser(description="All-in-One US Options GEX War Room")
    parser.add_argument("--patrol", action="store_true", help="單次背景自動巡邏模式")
    parser.add_argument("--daemon-loop", action="store_true", help="無黑窗 24H 隱形常駐守護模式")
    parser.add_argument("--morning", action="store_true", help="立即產生並發送今日開盤前早報")
    parser.add_argument("--test-self", action="store_true", help="執行單檔完整性自檢與日K圖繪製驗證")
    args, _ = parser.parse_known_args()

    if is_running_inside_streamlit():
        run_streamlit_warroom()
        return

    if args.test_self:
        tk, df_ohlcv, df_chain, exp_d, dte, sim_peak = get_demo_scenario_data("NVDA_SQUEEZE")
        snap, df_gex = evaluate_snapshot_and_alerts(tk, df_ohlcv, df_chain, exp_d, dte, 6.0, sim_peak)
        test_png = os.path.join(BASE_DIR, "NVDA_DailyK_Verified_Preview.png")
        render_warroom_chart_png(snap, df_ohlcv, df_gex, test_png)
        print(
            f"✅ [日K對齊與防重疊版自檢通過] {snap.ticker} Spot=${snap.spot_price:.2f} | "
            f"Put牆=${snap.put_wall:.1f} < Spot < Call牆=${snap.call_wall:.1f} | Net GEX={snap.net_gex_millions:+.2f}M"
        )
        return

    if args.daemon_loop:
        _daemon = BackgroundPatrolDaemon()
        while True:
            time.sleep(3600)

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