
import uuid
import time

def get_req_id() -> str:
    return str(uuid.uuid4().int)[:10]

def get_sub_id() -> str:
    return f"s_{uuid.uuid4().hex[:4]}"

def get_client_id() -> str:
    return str(int(time.time() * 1000))
