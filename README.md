# Sonos Presto Controller

A high-performance, touch-enabled Sonos album art display and controller for the **Pimoroni Presto** (powered by the Raspberry Pi RP2350).

## Features

- **Dynamic Album Art**: Automatically fetches and displays high-quality album art for the currently playing track on your Sonos system.
- **Viper-Optimized Scaling**: Uses MicroPython's `@micropython.viper` for high-speed, nearest-neighbor image scaling, ensuring 640x640 images fit perfectly on the 480x480 display in ~0.7s.
- **Touch Gesture Controls**:
  - **Tap**: Toggle Play/Pause.
  - **Swipe Right**: Next Track.
  - **Swipe Left**: Previous Track.
  - **Drag (Right Side)**: Adjust Volume Up/Down.
  - **Drag (Left Side)**: Adjust Display Brightness Up/Down.
- **Touch-to-Wake**: The display automatically sleeps when music stops. A simple tap wakes the device and resumes playback.
- **Progressive JPEG Support**: Gracefully handles unsupported progressive JPEG formats by preserving the previous artwork.
- **Custom Sonos Client**: A lightweight, dependency-free UPnP/SOAP client designed specifically for MicroPython's constrained environment.

## Hardware Requirements

- [Pimoroni Presto](https://shop.pimoroni.com/products/presto) (480x480 IPS Display, RP2350)
- Sonos Speaker(s) on the same local network.

## Installation & Setup

1.  **Flash Firmware**: Ensure your Presto is running the latest Pimoroni MicroPython firmware for the RP2350.
2.  **Configure**: Rename `config.py.example` to `config.py` (if applicable) or edit `config.py` directly with your details:
    ```python
    SSID = "Your_WiFi_Name"
    PASSWORD = "Your_WiFi_Password"
    ROOM_NAME = "Living Room" # The exact name of your Sonos room
    ```
3.  **Upload Files**: Use Thonny or `mpremote` to upload all `.py` files to the root of your Presto.
4.  **Run**: Execution starts automatically from `main.py`.

## Technical Notes

### Seamless Transitions
The controller minimizes visual noise by drawing new artwork directly over the old buffer without a full screen clear. This creates a smooth "wipe" transition between tracks.

### Non-Blocking Architecture
The `main.py` loop is designed to be highly responsive. It polls the touchscreen at ~50Hz while handling network updates and display scaling in a way that never leaves the touch interface unresponsive.

### Memory Management
The project carefully manages memory to handle large JPEG buffers on the RP2350, utilizing RAM-based decoding for maximum speed.
