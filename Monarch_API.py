from fastapi import FastAPI
import uvicorn
from typing import Dict
import os
import threading
from pathlib import Path
import yfinance as yf
import time
from zoneinfo import ZoneInfo
from datetime import datetime, timezone, time as clock_time

app = FastAPI()


@app.get("/")
def root():
    return {"status": "ok"}

users = {}
VERSION = "V3"
allOpenPositions = {}
passwordToUser = {}


UNE = {"status": "user does not exist"}

def getClose(sym):
    for attempt in range(2):
        try:
            stock = yf.Ticker(sym)
            price = stock.fast_info.last_price
            return price
        except Exception as e:
            print(f"Error retrieving close: {e}")
            if attempt == 2:
                return None

def getLast5Closes(sym):
    stock = yf.Ticker(sym)
    data = stock.history(period="1d", interval="1m")
    closes = data["Close"].tail(5).tolist()
    return closes


def inOperationHours() -> bool:
    central_now = datetime.now(ZoneInfo("America/Chicago"))
    central_time = central_now.time()

    start_time = clock_time(6, 0)    # 6:00 AM
    end_time = clock_time(20, 30)    # 8:30 PM

    return central_now.weekday() < 5 and start_time <= central_time <= end_time


### ---------- Threads -------- ###

def getDate():
    current_date = datetime.now()

    current_day = current_date.day
    current_month = current_date.month
    current_year = current_date.year

    return current_day, current_month, current_year
current_day, current_month, current_year = getDate()




def tradeDataAggregator():
    global users
    nextCheckTime = time.time()
    while True:
        if inOperationHours():
            if time.time() >= nextCheckTime:
                for sym in allOpenPositions:
                    # Get last 5 closes
                    if not allOpenPositions[sym]:
                        allOpenPositions[sym].extend(getLast5Closes(sym))
                    else:
                        close = getClose(sym)
                        if close:
                            # add current 5M candle
                            allOpenPositions[sym].append(close)
                nextCheckTime = time.time()+ (60*5) # +5 min
        else:
            time.sleep(120)




def daily_1202_checker():
    global users, current_day, current_month, current_year
    hour = 5
    minute = 2
    timeZone = "America/Chicago"
    last_run_date = None

    while True:
        # Use the selected timezone
        now = datetime.now(ZoneInfo(timeZone))

        # Run once per day at the specified hour/minute in that timezone
        if now.hour == hour and now.minute == minute:
            if last_run_date != now.date():
                # Organize chart
                d,m,y = getDate()
                if d != current_day:
                    for user in users:
                        lastProfit = users[user]["CMP"][0]
                        todaysProfit = users[user]["TodaysProfit"]
                        users[user]["CMP"].append(lastProfit+todaysProfit)

                if m != current_month:
                    for user in users:  # CYP
                        lastProfit = users[user]["CYP"][0]
                        currentMProfit = users[user]["CMP"][0]
                        users[user]["CYP"].append(lastProfit+currentMProfit)
                    for user in users:  # AP
                        lastProfit = users[user]["AP"][0]
                        currentAProfit = users[user]["CMP"][0]
                        users[user]["AP"].append(lastProfit+currentAProfit)

                    # Also clear trades at end of month
                    for user in users:
                        users[user]["trades"] = []

                # Clear running day info
                for user in users:
                    users[user]["TodaysProfit"] = 0.0
                    users[user]["logs"] = []

                print("organized chart", flush=True)
                last_run_date = now.date()


        time.sleep(1)



dataAggregatorThread = threading.Thread(target=tradeDataAggregator, daemon=True)
dataAggregatorThread.start()
print("Started data aggregator")



def userExists(user):
    global users
    return user in users



@app.get("/add-user")
def addUser(newUser: str, name: str):
    global users, passwordToUser

    users[newUser] = {
        "Account_Balance": 0.0,
        "Connection_status": "Offline",
        "Version": "V3",
        "Connected_Account": "None",
        "TodaysProfit": 0.0,
        "CMP": [0],
        "CYP": [0],
        "AP": [0],
        "logs": [],
        "positions": {},
        "progress": [],
        "schedule": [],
        "trades": [],
        "settings": {},
        "settings_applied": True,
        "lastPingTime": 0
    }
    passwordToUser[newUser] = name

    return {"status": "added"}









# ---------- Monarch Endpoints ---------- #
@app.get("/update-logs")
def updateLogs(log: str, user: str):
    global users
    if userExists(user):
        users[user]["logs"].append(log)
        return {"status": "updated"}
    else:
        return UNE
    
@app.get("/update-current-progress") #
def updateCurrentStatus(progress: str, user: str):
    global users
    if progress:
        users[user]["progress"].append(progress)
    else:
        users[user]["progress"].clear()
    return {"status": "updated"}

@app.get("/update-schedule") #
def updateSchedule(time: str, description: str, user: str):
    global users
    users[user]["schedule"].append({time: description})
    return {"status": "updated"}


@app.post("/update-positions") #
def updatePositions(positions: dict, user: str):
    global users
    users[user]["positions"] = positions
    return {"status": "updated"}

@app.get("/open-position") #
def openPosition(sym: str):
    global allOpenPositions
    allOpenPositions[sym] = []
    return {"status": "updated"}

@app.get("/close-position") #
def closePosition(sym: str, profit: float, side: str, user: str):
    global users
    if not userExists(user):
        return UNE
    plotPoints = allOpenPositions.get(sym, [])
    if sym in allOpenPositions:
        del allOpenPositions[sym]        
        
    users[user]["trades"].append(
        {sym: {
            "profit": profit,
            "side": side,
            "plot_points": plotPoints
        }})
    return {"status": "updated"}

@app.get("/ping") #
def Ping(user: str, version: str, connectedAccount: str, accountBalance: str):
    global users
    users[user]["Account_Balance"] = accountBalance
    users[user]["Version"] = version
    users[user]["Connected_Account"] = connectedAccount
    users[user]["Connection_status"] = "Online"
    users[user]["settings_applied"] = True
    newSettings = users[user]["settings"]
    users[user]["lastPingTime"] = time.time()
    return {
        "status": "received",
        "new_settings": newSettings
        }


# -------- App Endpoints -------- #

@app.get("/get-logs")
def getLogs(user: str):
    global users
    if userExists(user):
        return users[user]["logs"]
    return UNE


@app.get("/get-trade-page")
def getTradePage(user: str):
    global users
    if not userExists(user):
        return UNE
    return {"trade-page": {
        "positions": users[user]["positions"],
        "progress": users[user]["progress"],
        "schedule": users[user]["schedule"],
    }}


@app.post("/update-settings")
def updatesSettings(user:str, newSettings: dict):
    if not userExists(user):
        return UNE
    users[user]["settings"] = newSettings
    users[user]["settings_applied"] = False
    return {"status": "updating"}

@app.get("/check-updated-settings-status")
def checkUpdatedSettingsStatus(user: str):
    if not userExists(user):
        return UNE
    if users[user]["settings_applied"]:
        return {"status": "updated"}
    else:
        return {"status": "updating"}
    



@app.get("/get-home-page")
def getHomePage(user: str, timeFrame: str): # MONTH/YEAR/ALL-TIME
    if not userExists(user):
        return UNE

    if timeFrame:
        if timeFrame == "MONTH":
            profit = users[user]["CMP"]
        elif timeFrame == "YEAR":
            profit = users[user]["CYP"]
        elif timeFrame == "ALL-TIME":
            profit = users[user]["AP"]
        todaysProfit = users[user]["TodaysProfit"]
        trades = users[user]["trades"]
        if users[user]["lastPingTime"]+30 < time.time():
            connectionStatus = "Offline"
        else:
            connectionStatus = "Online"
        settings = users[user]["settings"]

        return {
            "profit": profit,
            "todays_profit": todaysProfit,
            "trades": trades,
            "connectionStatus": connectionStatus,
            "settings": settings
        }
    else:
        return {"status": "timeFrame not specified"}



@app.get("/login")
def login(user: str):
    if userExists(user):
        return {"status": f"Hey, {passwordToUser[user]}"}
    else:
        return UNE

endpoints = []
for route in app.routes:
    hi = ["/openapi.json", "/docs", "/docs/oauth2-redirect", "/redoc"]
    if route.path not in hi:
        print("http://127.0.0.1:8000"+route.path)
        endpoints.append(route.path)

@app.get("/endpoints")
def getendpoints():
    global endpoints
    return {"endpoints": endpoints}

# Deploy code:
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)


"""
# Testing code:
if __name__ == "__main__":
    uvicorn.run("Sleepy_API_v1:app", host="127.0.0.1", port=8000, reload=True)
"""

# Querei: http://127.0.0.1:8000/update-profit?value=1036.39871243?Aname=hiiii
# Get: http://127.0.0.1:8000/total-profit
