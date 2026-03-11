import network
import time
import config

def connect_wifi():
    """Connects to the Wi-Fi network using credentials from config.py."""
    wlan = network.WLAN(network.STA_IF)
    wlan.active(True)
    
    if not wlan.isconnected():
        print(f"Connecting to '{config.SSID}'...")
        wlan.connect(config.SSID, config.PASSWORD)
        
        # Wait for connection
        max_wait = 30 # Increased from 10
        while max_wait > 0:
            status = wlan.status()
            if status < 0 or status >= 3:
                break
            max_wait -= 1
            print(f"Waiting... ({max_wait}s)")
            time.sleep(1)
            
    status = wlan.status()
    if status != 3:
        raise RuntimeError(f"WiFi failed (status={status})")
    else:
        config_info = wlan.ifconfig()
        rssi = wlan.status('rssi')
        print(f"Connected! IP: {config_info[0]}, RSSI: {rssi}dBm")
        return config_info[0], rssi
