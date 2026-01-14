import network_manager
import sonos_client
import display_manager
import config
import time
import machine

def main():
    # 1. Init Display
    display = display_manager.DisplayManager()
    display.show_text("Booting...")
    
    # 2. Connect WiFi
    display.show_text(f"Joining {config.SSID}...")
    try:
        ip = network_manager.connect_wifi()
        display.show_text("WiFi connected!")
        time.sleep(1)
    except Exception as e:
        display.show_text("WiFi Fail")
        print(e)
        return

    # 3. Discover Sonos
    target_sonos = None
    while target_sonos is None:
        display.show_text("Searching Sonos...")
        devices = sonos_client.discover_devices()
        print(f"Found {len(devices)} devices")
        
        for device in devices:
            name = device.get_room_name()
            print(f"Check: {device.ip} -> {name}")
            display.show_text(f"Room: {name}")
            if name == config.ROOM_NAME:
                target_sonos = device
                break
        
        if target_sonos is None:
            display.show_text("Retrying...")
            time.sleep(2)

    # 4. Main Loop
    from touch_manager import TouchManager, Action
    tm = TouchManager(display.presto)
    
    last_art_uri = None
    
    # Initialize state based on current playback
    initial_state = target_sonos.get_transport_info()
    display_is_on = (initial_state in ["PLAYING", "TRANSITIONING"])
    if not display_is_on:
        print(f"Startup: Music status is {initial_state}. Sleeping display.")
        display.turn_off()
    
    # Timers for non-blocking loop
    last_sonos_poll = time.ticks_ms() # Start timer now
    sonos_poll_interval = 2000 # 2 seconds normally
    wake_grace_until = 0 # Time until which we keep screen on regardless of state
    
    # Brightness state
    current_brightness = 1.0

    print("Entering Main Loop...")
    
    while True:
        try:
            now = time.ticks_ms()
            
            # --- 1. Touch Handling (Fast Poll) ---
            action = tm.poll()
            
            if action != Action.NONE:
                print(f"Touch Action: {action}")
                
                # Update grace period on any interaction
                wake_grace_until = now + 5000
                
                # If display is off, any touch wakes it (and potentially acts)
                if not display_is_on:
                    print("Touch Wake Up")
                    display.turn_on(current_brightness)
                    display_is_on = True
                    last_art_uri = None # Force refresh of art on wake
                    # Reset timers to force immediate update
                    last_sonos_poll = 0 
                
                # Handle gestures
                if action == Action.PLAY_PAUSE:
                    try:
                        state = target_sonos.get_transport_info()
                        if state == "PLAYING":
                            target_sonos.pause()
                            wake_grace_until = 0 # Cancel grace if we intentionally paused
                        else:
                            target_sonos.play()
                    except:
                        target_sonos.play() # Default to play
                        
                elif action == Action.NEXT:
                    target_sonos.next()
                elif action == Action.PREV:
                    target_sonos.previous()
                elif action == Action.VOLUME_UP:
                    target_sonos.set_relative_volume(2) # +2%
                elif action == Action.VOLUME_DOWN:
                    target_sonos.set_relative_volume(-2) # -2%
                elif action == Action.BRIGHT_UP:
                    current_brightness = min(1.0, current_brightness + 0.1)
                    display.set_backlight(current_brightness)
                elif action == Action.BRIGHT_DOWN:
                    current_brightness = max(0.1, current_brightness - 0.1) # Min 10%
                    display.set_backlight(current_brightness)

            # --- 2. Sonos Polling (Slow Interval) ---
            if time.ticks_diff(now, last_sonos_poll) > sonos_poll_interval:
                last_sonos_poll = now
                
                # Check transport state
                transport_state = target_sonos.get_transport_info()
                
                # Determine if we should be active
                should_be_active = (transport_state in ["PLAYING", "TRANSITIONING"]) or (now < wake_grace_until)
                
                if not should_be_active:
                    if display_is_on:
                        print(f"Music status: {transport_state}. Sleeping display.")
                        display.turn_off()
                        display_is_on = False
                        
                    # Slow down polling when inactive
                    sonos_poll_interval = 5000 
                else:
                    # Music is playing or In Grace Period
                    sonos_poll_interval = 2000
                    if not display_is_on:
                        print(f"Music status: {transport_state}. Waking display.")
                        display.turn_on(current_brightness)
                        display_is_on = True
                        last_art_uri = None # Force refresh
                
                # Update Art if display is on
                if display_is_on:
                    info = target_sonos.get_position_info()
                    if info and 'album_art_uri' in info:
                        current_uri = info['album_art_uri']
                        if current_uri != last_art_uri:
                            print("New Art Detected")
                            jpeg_data = target_sonos.get_album_art_jpeg(current_uri)
                            if jpeg_data:
                                display.show_album_art(jpeg_data)
                                last_art_uri = current_uri
                            else:
                                display.show_text("Art Fetch Fail")

        except Exception as e:
            print(f"Loop Error: {e}")
            
        time.sleep(0.02) # 20ms Throttle for main loop (approx 50Hz)

if __name__ == "__main__":
    main()
