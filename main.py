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
    retry_count = 0
    ip = None
    while ip is None:
        display.show_text(f"Joining {config.SSID}...")
        try:
            ip, rssi = network_manager.connect_wifi()
            display.show_text(f"Connected!\n{ip}\nRSSI: {rssi}dBm")
            time.sleep(2)
        except Exception as e:
            retry_count += 1
            display.show_text(f"WiFi Fail ({retry_count})\nRetrying...")
            print(f"WiFi Connection Error (Attempt {retry_count}): {e}")
            time.sleep(5)
            if retry_count > 10:
                display.show_text("Fatal: WiFi Fail\nCheck Config/Signal")
                return

    while True: # Outer loop for persistent discovery/re-discovery
        # 3. Discover Sonos
        target_sonos = None
        discovery_attempts = 0
        udn_map = {} # Map uuid:RINCON_... -> SonosDevice
        
        while target_sonos is None:
            discovery_attempts += 1
            display.show_text(f"Searching Sonos...\n(Attempt {discovery_attempts})")
            devices = sonos_client.discover_devices()
            print(f"Found {len(devices)} devices")
            
            for device in devices:
                try:
                    name, udn = device.get_device_info()
                    print(f"Check: {device.ip} -> {name} ({udn})")
                    if udn:
                        udn_map[udn] = device
                        
                    if name:
                        display.show_text(f"Found: {name}")
                    if name == config.ROOM_NAME:
                        target_sonos = device
                        # Don't break yet, we want to find all UDNs in the network
                except Exception as e:
                    print(f"Error checking device {device.ip}: {e}")
            
            if target_sonos is None:
                display.show_text("Sonos NotFound\nRetrying...")
                time.sleep(2)

        # 4. Main Loop
        from touch_manager import TouchManager, Action
        tm = TouchManager(display.presto)
        
        last_art_uri = None
        sonos_fail_count = 0
        
        # Initialize state based on current playback
        try:
            initial_state = target_sonos.get_transport_info()
        except Exception as e:
            print(f"Initial State Error: {e}")
            initial_state = "STOPPED"
            
        print(f"Startup Music Status: {initial_state}")
        display_is_on = (initial_state in ["PLAYING", "TRANSITIONING"])
        if not display_is_on:
            print("Music is not active. Sleeping display.")
            display.turn_off()
        else:
            print("Music is active. Keeping display on.")
            display.turn_on(1.0) 
        
        # Timers for non-blocking loop
        last_sonos_poll = time.ticks_ms()
        sonos_poll_interval = 2000
        wake_grace_until = 0
        
        # Brightness state
        current_brightness = 1.0

        print(f"Entering Main Loop for {config.ROOM_NAME}...")
        loop_count = 0
    
        while True:
            try:
                now = time.ticks_ms()
                loop_count += 1
                if loop_count % 100 == 0:
                    print(".", end="") # Heartbeat
                
                # --- 1. Touch Handling (Fast Poll) ---
                action = tm.poll()
                
                if action != Action.NONE:
                    print(f"\nTouch Action: {action}")
                    
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
                    print(f"\nPolling Sonos... (Interval: {sonos_poll_interval}ms)")
                    
                    try:
                        # Check transport state
                        transport_state = target_sonos.get_transport_info()
                        print(f"Transport State: {transport_state}")
                        
                        if transport_state is None:
                            # Communication failed
                            sonos_fail_count += 1
                            print(f"Sonos Polling Failed ({sonos_fail_count})")
                            
                            if sonos_fail_count > 5:
                                print("Persistent Sonos failure. Triggering re-discovery...")
                                display.show_text("Sonos Lost\nRe-discovering...")
                                target_sonos = None
                                break 
                        else:
                            sonos_fail_count = 0 # Reset on success
                        
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
                            # Use tracking for Group Coordinator
                            current_sonos = target_sonos
                            
                            info = target_sonos.get_position_info()
                            
                            # Check if it's a group Rincon URI
                            if info and 'track_uri' in info and "x-rincon:" in info['track_uri']:
                                current_uri = info['track_uri']
                                rincon_id = "uuid:" + current_uri.split(":")[1]
                                if rincon_id in udn_map:
                                    print(f"Following Group Coordinator: {udn_map[rincon_id].ip}")
                                    current_sonos = udn_map[rincon_id]
                                    info = current_sonos.get_position_info()
                            
                            if info:
                                image_uri = info.get('album_art_uri')
                                
                                if image_uri and "x-rincon:" not in image_uri:
                                    if image_uri != last_art_uri:
                                        print(f"New Art Detected: {image_uri}")
                                        jpeg_data = current_sonos.get_album_art_jpeg(image_uri)
                                        if jpeg_data:
                                            display.show_album_art(jpeg_data)
                                            last_art_uri = image_uri
                                        else:
                                            display.show_text("Art Fetch Fail")
                                else:
                                    # Fallback to Text MetaData when no Album Art is present
                                    stream_text = info.get('stream_content')
                                    title_text = info.get('title')
                                    artist_text = info.get('artist')
                                    
                                    display_text = ""
                                    if stream_text:
                                        display_text = stream_text
                                    elif title_text:
                                        display_text = title_text
                                        if artist_text:
                                            display_text += f"\n{artist_text}"
                                    else:
                                        display_text = "Radio Playing"
                                    
                                    text_state_id = "txt:" + display_text
                                    
                                    if last_art_uri != text_state_id:
                                        print(f"Displaying Text Fallback: {display_text}")
                                        display.show_text(display_text, scale=2)
                                        last_art_uri = text_state_id
                            else:
                                print("No Metadata Info")
                    except Exception as e:
                        print(f"\nSonos Update Error: {e}")
                        sonos_fail_count += 1

            except Exception as e:
                print(f"Loop Error: {e}")
                # Potential WiFi loss handling
                try:
                    import network
                    wlan = network.WLAN(network.STA_IF)
                    if not wlan.isconnected():
                        print("WiFi Disconnected mid-loop! Attempting recovery...")
                        display.show_text("WiFi Lost\nReconnecting...")
                        try:
                            network_manager.connect_wifi()
                            last_art_uri = None 
                            display.show_text("WiFi Recovered")
                            time.sleep(1)
                        except:
                            print("WiFi Recovery Failed")
                except:
                    pass
                
            time.sleep(0.02) # 20ms Throttle for main loop (approx 50Hz)

if __name__ == "__main__":
    main()
