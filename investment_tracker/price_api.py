"""
轻量级股票行情 API
给 investment-tracker.html 提供无 CORS 限制的数据接口

启动：uvicorn price_api:app --host 127.0.0.1 --port 8001
"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
import yfinance as yf

app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)

ETF_SKIP = {"VOO","VTI","QQQ","SCHD","VYM","DGRO","GLD","BND","IEF","TLT","VXUS","MGK","SPY","IVV"}


@app.get("/api/quote")
async def get_quote(symbols: str):
    """批量获取股票现价和日涨跌幅"""
    ticker_list = [s.strip().upper() for s in symbols.split(",") if s.strip()]
    if not ticker_list:
        raise HTTPException(400, "symbols 参数不能为空")

    result = []
    try:
        if len(ticker_list) == 1:
            t = yf.Ticker(ticker_list[0])
            hist = t.history(period="2d")
            if len(hist) >= 2:
                price = float(hist["Close"].iloc[-1])
                prev  = float(hist["Close"].iloc[-2])
                chg   = (price - prev) / prev * 100
            elif len(hist) == 1:
                price = float(hist["Close"].iloc[-1]); chg = 0.0
            else:
                price = 0.0; chg = 0.0
            result.append({"symbol": ticker_list[0],
                            "regularMarketPrice": round(price, 2),
                            "regularMarketChangePercent": round(chg, 4)})
        else:
            data = yf.download(ticker_list, period="2d",
                               auto_adjust=True, progress=False, threads=True)
            closes = data["Close"]
            for t in ticker_list:
                try:
                    col = closes[t]
                    prices = col.dropna()
                    if len(prices) >= 2:
                        price = float(prices.iloc[-1])
                        prev  = float(prices.iloc[-2])
                        chg   = (price - prev) / prev * 100
                    elif len(prices) == 1:
                        price = float(prices.iloc[-1]); chg = 0.0
                    else:
                        price = 0.0; chg = 0.0
                    result.append({"symbol": t,
                                   "regularMarketPrice": round(price, 2),
                                   "regularMarketChangePercent": round(chg, 4)})
                except Exception:
                    result.append({"symbol": t,
                                   "regularMarketPrice": 0,
                                   "regularMarketChangePercent": 0})
    except Exception as e:
        raise HTTPException(500, f"数据获取失败：{e}")

    return {"quoteResponse": {"result": result}}


@app.get("/api/calendar/{symbol}")
async def get_calendar(symbol: str):
    """获取个股财报日期（ETF 自动跳过）"""
    sym = symbol.upper()
    if sym in ETF_SKIP:
        return {"earningsDate": []}
    try:
        cal = yf.Ticker(sym).calendar
        if cal is None:
            return {"earningsDate": []}

        dates = []

        # 新格式：dict，如 {'Earnings Date': [datetime.date(2026, 4, 29)], ...}
        if isinstance(cal, dict) and "Earnings Date" in cal:
            raw_dates = cal["Earnings Date"]
            if not isinstance(raw_dates, list):
                raw_dates = [raw_dates]
            for d in raw_dates:
                try:
                    if hasattr(d, "strftime"):
                        dates.append({"raw": 0, "fmt": str(d)})
                except Exception:
                    pass
            return {"earningsDate": dates}

        # 旧格式：DataFrame
        if hasattr(cal, "columns") and "Earnings Date" in cal.columns:
            for d in cal["Earnings Date"]:
                try:
                    if hasattr(d, "timestamp"):
                        dates.append({"raw": int(d.timestamp()), "fmt": str(d.date())})
                except Exception:
                    pass
            return {"earningsDate": dates}

    except Exception:
        pass
    return {"earningsDate": []}


@app.get("/api/health")
async def health():
    return {"status": "ok"}
