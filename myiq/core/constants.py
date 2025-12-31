
IQ_HTTP_URL = "https://auth.iqoption.com/api/v2/login"
IQ_WS_URL = "wss://iqoption.com/echo/websocket"

# Operations
OP_AUTHENTICATE = "authenticate"
OP_GET_BALANCES = "internal-billing.get-balances"
OP_OPEN_OPTION = "binary-options.open-option"
OP_SUBSCRIBE_POSITIONS = "subscribe-positions"
OP_GET_CANDLES = "get-candles"
OP_SET_SETTINGS = "set-user-settings" # Gatilho para candles

# Events
EV_AUTHENTICATED = "authenticated"
EV_TIME_SYNC = "timeSync"
EV_POSITION_CHANGED = "position-changed"
EV_CANDLE_GENERATED = "candle-generated"

# Blitz
OPTION_TYPE_BLITZ = 12
INSTRUMENT_TYPE_BLITZ = "blitz-option"
