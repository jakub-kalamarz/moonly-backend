from datetime import datetime
from services.data_store import sat_data as get_data, last_updated as get_last_updated

def sat_data():
    """
    Wrapper function to maintain compatibility with existing code.
    Simply calls the implementation in data_store.py
    """
    return get_data()

def last_updated():
    """
    Wrapper function to maintain compatibility with existing code.
    Simply calls the implementation in data_store.py
    """
    return get_last_updated()