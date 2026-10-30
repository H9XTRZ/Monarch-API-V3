from fastapi import FastAPI
import uvicorn
import os
import threading
from persistence import StateStore, database_path
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

store = StateStore(database_path(), users=users, passwordToUser=passwordToUser,
                   allOpenPositions=allOpenPositions)
print(f"Persistent storage: {store.path}", flush=True)
adminKey = "ab93d7f953a0dc076a16b6a0"


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
    current_date = datetime.now(ZoneInfo("America/Chicago"))

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
                with store.transaction():
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
        time.sleep(1 if inOperationHours() else 120)

def dataOrgasm():
    global users, current_day, current_month, current_year
    with store.transaction():
        # Organize chart
        d,m,y = getDate()
        if d != current_day:
            for user in users:
                lastProfit = users[user]["CMP"][-1]
                todaysProfit = 208.61
                if todaysProfit != 0:
                    users[user]["CMP"].append(lastProfit+todaysProfit)
                    lastAProfit = users[user]["AP"][-1]
                    users[user]["AP"].append(lastAProfit+todaysProfit)

        if m != current_month:
            for user in users:  # CYP
                lastProfit = users[user]["CYP"][-1]
                currentMProfit = users[user]["CMP"][-1]
                users[user]["CYP"].append(lastProfit+currentMProfit)
                # Also clear trades at end of month
                users[user]["trades"] = []
                users[user]["CMP"].clear()

        if y != current_year:
            for user in users:
                users[user]["CYP"].clear()

        # Clear running day info
        if d != current_day or m != current_month or y != current_year:
            for user in users:
                users[user]["TodaysProfit"] = 0.0
                users[user]["logs"] = []
                users[user]["schedule"] = []
            current_day, current_month, current_year = getDate()

dataOrgasm()

def dataOrganizer():
    global users, current_day, current_month, current_year
    with store.transaction():
        # Organize chart
        d,m,y = getDate()
        if d != current_day:
            for user in users:
                lastProfit = users[user]["CMP"][-1]
                todaysProfit = users[user]["TodaysProfit"]
                if todaysProfit != 0:
                    users[user]["CMP"].append(lastProfit+todaysProfit)
                    lastAProfit = users[user]["AP"][-1]
                    users[user]["AP"].append(lastAProfit+todaysProfit)

        if m != current_month:
            for user in users:  # CYP
                lastProfit = users[user]["CYP"][-1]
                currentMProfit = users[user]["CMP"][-1]
                users[user]["CYP"].append(lastProfit+currentMProfit)
                # Also clear trades at end of month
                users[user]["trades"] = []
                users[user]["CMP"].clear()

        if y != current_year:
            for user in users:
                users[user]["CYP"].clear()

        # Clear running day info
        if d != current_day or m != current_month or y != current_year:
            for user in users:
                users[user]["TodaysProfit"] = 0.0
                users[user]["logs"] = []
                users[user]["schedule"] = []
            current_day, current_month, current_year = getDate()


def daily_1202_checker():
    global users, current_day, current_month, current_year
    hour = 0
    minute = 2
    timeZone = "America/Chicago"
    last_run_date = None

    while True:
        # Use the selected timezone
        now = datetime.now(ZoneInfo(timeZone))

        # Run once per day at the specified hour/minute in that timezone
        if now.hour == hour and now.minute == minute:
            if last_run_date != now.date():
                dataOrganizer()

                print("organized chart", flush=True)
                last_run_date = now.date()


        time.sleep(1)



dataAggregatorThread = threading.Thread(target=tradeDataAggregator, daemon=True)
dataAggregatorThread.start()
daily1202CheckerThread = threading.Thread(target=daily_1202_checker, daemon=True)
daily1202CheckerThread.start()
print("Started background threads")



def userExists(user):
    global users
    return user in users

# ---------- Admin Endpoints ---------- #

@app.get("/add-user")
@store.endpoint
def addUser(password: str, name: str):
    global users, passwordToUser

    if password in users:
        return {"status": "user already exists"}

    users[password] = {
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
    passwordToUser[password] = name

    return {"status": "added"}



@app.get("/remove-user")
@store.endpoint
def removeUser(user: str, key: str):
    global users
    if key != adminKey:
        return {"status": "incorrect creds"}
    if user not in users:
        return {"status": "User not found"}
    del users[user]
    passwordToUser.pop(user, None)
    return {"status": f"User {user} deleted"}



@app.get("/clear-user-trades")
@store.endpoint
def clearUserTrades(user:str):
    global users
    if not userExists(user):
        return UNE
    users[user]["trades"] = []
    users[user]["TodaysProfit"] = 0.0
    users[user]["positions"] = {}
    return {"status": "cleared"}

@app.get("/get-plot-point-stuff")
@store.endpoint
def getPlotPointStuff():
    global allOpenPositions
    return {"positions": allOpenPositions}

@app.get("/clear-schedule") #
@store.endpoint
def updateSchedule(user: str):
    global users
    if not userExists(user):
        return UNE
    users[user]["schedule"] = []
    return {"status": "cleared"}


@app.post("/update-position-results")
@store.endpoint
def updatePositionResults(positionToUpdate: dict, newPositionInfo: dict, user: str):
    # DO NOT USE TO UPDATE TRADES ON A PREVIOUS DAY
    global users
    if not userExists(user):
        return UNE
    if not positionToUpdate in users[user]["trades"]:
        return {"status": "trade not found"}
    oldPositionProfit = positionToUpdate[list(positionToUpdate)[0]]["profit"]
    if oldPositionProfit < 0:
        users[user]["TodaysProfit"] += abs(oldPositionProfit)
    else:
        users[user]["TodaysProfit"] -= oldPositionProfit
    replaceIDX = users[user]["trades"].index(positionToUpdate)
    users[user]["trades"][replaceIDX] = newPositionInfo
    newProfit = newPositionInfo[list(newPositionInfo)[0]]["profit"]
    users[user]["TodaysProfit"] += newProfit
    return {"status": "updated"}


@app.get("/reset-AT")
@store.endpoint
def reset_AT(user: str):
    """ Resets AP to what ever the last CMP item is """
    global users
    if not userExists(user):
        return UNE
    users[user]["AP"].append(users[user]["CMP"][-1])
    return {"status": "reset"}



# ---------- Monarch Endpoints ---------- #
@app.get("/update-logs") #
@store.endpoint
def updateLogs(log: str, user: str):
    global users
    if userExists(user):
        users[user]["logs"].append(log)
        return {"status": "updated"}
    else:
        return UNE
    
@app.get("/update-current-progress") #
@store.endpoint
def updateCurrentStatus(progress: str, user: str):
    global users
    if progress != "COMPLETE":
        users[user]["progress"].append(progress)
    else:
        users[user]["progress"].clear()
    return {"status": "updated"}

@app.post("/update-schedule") #
@store.endpoint
def updateSchedule(time: str, info: dict, user: str):
    global users
    users[user]["schedule"].append({time: info})
    return {"status": "updated"}
"""
New schedule format:

[
# For investigations
    TIME:{
        "Event": "INVESTIGATION",
        "description": 
    }

# For orders
    TIME:{
        "Event": "ORDER",
        "Symbol": symbol
        "Purchase_Price": fillPrice,
        "Shares": shares,
        "Side": side,
    }
]

"""


@app.post("/open-position") #
@store.endpoint
def openPosition(sym: str, positions: dict, user: str):
    """ Updated both data collecting and user positions """
    global allOpenPositions, users
    allOpenPositions[sym] = []
    users[user]["positions"] = positions
    return {"status": "updated"}


@app.get("/close-position") #
@store.endpoint
def closePosition(sym: str, profit: float, side: str, user: str):
    global users
    if not userExists(user):
        return UNE
    plotPoints = allOpenPositions.get(sym, [])
    if sym in allOpenPositions:
        del allOpenPositions[sym]     
    if sym in users[user]["positions"]:
        del users[user]["positions"][sym]
        
    users[user]["trades"].append(
        {sym: {
            "profit": profit,
            "side": side,
            "plot_points": plotPoints
        }})
    users[user]["TodaysProfit"] += profit
    return {"status": "updated"}


    

@app.get("/ping") #
@store.endpoint
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
@store.endpoint
def getLogs(user: str):
    global users
    if userExists(user):
        return users[user]["logs"]
    return UNE


@app.get("/get-trade-page")
@store.endpoint
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
@store.endpoint
def updatesSettings(user:str, newSettings: dict):
    if not userExists(user):
        return UNE
    users[user]["settings"] = newSettings
    users[user]["settings_applied"] = False
    return {"status": "updating"}

@app.get("/check-updated-settings-status")
@store.endpoint
def checkUpdatedSettingsStatus(user: str):
    if not userExists(user):
        return UNE
    if users[user]["settings_applied"]:
        return {"status": "updated"}
    else:
        return {"status": "updating"}
    



@app.get("/get-home-page")
@store.endpoint
def getHomePage(user: str, timeFrame: str): # MONTH/YEAR/ALL-TIME
    if not userExists(user):
        return UNE

    if timeFrame:
        if timeFrame == "MONTH":
            profit = users[user]["CMP"]
        elif timeFrame == "YEAR":
            month_profit = users[user]["CMP"]
            profit = users[user]["CYP"]
            profit += month_profit
        elif timeFrame == "ALL-TIME":
            profit = users[user]["AP"]
        todaysProfit = users[user]["TodaysProfit"]
        trades = users[user]["trades"]
        if users[user]["lastPingTime"]+120 < time.time():
            connectionStatus = "Offline"
            users[user]["progress"].clear() # Just in case if it goes offline and the progress isn't cleared
        else:
            connectionStatus = "Online"
        settings = users[user]["settings"]
        connectedAccount = users[user]["Connected_Account"]
        Account_Balance = users[user]["Account_Balance"]
        return {
            "profit": profit,
            "todays_profit": todaysProfit,
            "trades": trades,
            "connectionStatus": connectionStatus,
            "connectedAccount": connectedAccount,
            "Account_Balance": Account_Balance,
            "settings": settings,
        }
    else:
        return {"status": "timeFrame not specified"}



@app.get("/login")
@store.endpoint
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

