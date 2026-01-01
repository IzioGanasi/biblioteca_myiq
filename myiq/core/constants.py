
IQ_HTTP_URL = "https://auth.iqoption.com/api/v2/login"
IQ_WS_URL = "wss://iqoption.com/echo/websocket"

# Operations
OP_AUTHENTICATE = "authenticate"
OP_GET_BALANCES = "internal-billing.get-balances"
OP_OPEN_OPTION = "binary-options.open-option"
OP_SUBSCRIBE_POSITIONS = "subscribe-positions"
OP_GET_CANDLES = "get-candles"
OP_SET_SETTINGS = "set-user-settings" # Gatilho para candles
OP_GET_FINANCIAL_INFO = "get-financial-information"

# Events
EV_AUTHENTICATED = "authenticated"
EV_FINANCIAL_INFO = "financial-information"
EV_TIME_SYNC = "timeSync"
EV_POSITION_CHANGED = "position-changed"
EV_CANDLE_GENERATED = "candle-generated"

# Blitz
OPTION_TYPE_BLITZ = 12
INSTRUMENT_TYPE_BLITZ = "blitz-option"

EV_UNDERLYING_LIST_CHANGED = "underlying-list-changed"
EV_PROFILE = "profile"
EV_FEATURES = "features"
EV_USER_SETTINGS = "user-settings" # Note: in logs it appears as "user-settings" or "set-user-settings" depending on context, but incoming is "user-settings" or via "sendMessage" wrapper.
EV_INIT_DATA = "initialization-data"
