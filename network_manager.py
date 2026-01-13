import network
import time
import config

def connect_wifi():
    """Connects to the Wi-Fi network using credentials from config.py."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    if not wlan.isconnected():
        print(f"Connecting to network '{config.SSID}'...")
        wlan.connect(config.SSID, config.PASSWORD)
        
        # Wait for connection
        max_wait = 10
        while max_wait > 0:
            if wlan.status() < 0 or wlan.status() >= 3:
                break
            max_wait -= 1
            print("Waiting for connection...")
            time.sleep(1)
            
    if wlan.status() != 3:
        raise RuntimeError("Network connection failed")
    else:
        status = wlan.ifconfig()
        print(f"Connected! IP: {status[0]}")
        return status[0]
