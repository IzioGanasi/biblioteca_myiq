import sys
import os

# Force usage of local myiq package
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from myiq import get_req_id, get_sub_id, get_client_id

def test_utils_raw():
    print("--- RAW GENERATED IDENTIFIERS ---")
    print(f"Request ID:      {get_req_id()}")
    print(f"Subscription ID: {get_sub_id()}")
    print(f"Client ID:       {get_client_id()}")

if __name__ == "__main__":
    test_utils_raw()
