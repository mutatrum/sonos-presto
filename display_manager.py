from presto import Presto
from picographics import PicoGraphics, PEN_RGB565
import jpegdec
import time
import gc
import micropython

@micropython.viper
def scale_blit_viper(src_obj, dst_obj, w_src: int, h_src: int, w_dst: int, h_dst: int):
    # Cast buffers to 16-bit pointers (RGB565)
    src = ptr16(src_obj)
    dst = ptr16(dst_obj)
    
    # Calculate fixed-point ratios (16.16 format)
    x_ratio = int((w_src << 16) // w_dst)
    y_ratio = int((h_src << 16) // h_dst)
    
    y_acc = 0
    for y in range(h_dst):
        sy = y_acc >> 16
        
        # Calculate row offsets (in 16-bit words)
        row_src_idx = sy * w_src
        row_dst_idx = y * w_dst
        
        x_acc = 0
        for x in range(w_dst):
            sx = x_acc >> 16
            # Copy pixel
            dst[row_dst_idx + x] = src[row_src_idx + sx]
            x_acc += x_ratio
            
        y_acc += y_ratio

class DisplayManager:
    def __init__(self):
        # Presto handles display initialization internally
        self.presto = Presto(full_res=True, direct_to_fb=True)
        
        # Start with backlight off to avoid noise
        self.presto.set_backlight(0.0)
        self.presto.auto_ambient_leds(True)
        
        # Use the display object created by Presto
        self.display = self.presto.display
        self.width, self.height = self.display.get_bounds()
        self.output_buffer = None 
        
        self.jpeg = jpegdec.JPEG(self.display)
        
        # Colors
        self.black = self.display.create_pen(0, 0, 0)
        self.white = self.display.create_pen(255, 255, 255)
        self.accent = self.display.create_pen(255, 0, 128) # Pink-ish

        # Clear screen on startup to remove noise
        self.clear()
        
        # Turn backlight on
        self.presto.set_backlight(1.0)

    def clear(self):
        # Single layer in full_res mode
        self.display.set_pen(self.black)
        self.display.clear()
        self.presto.update()

    def set_backlight(self, value):
        """Sets backlight brightness (0.0 to 1.0)."""
        # Ensure value is clamped
        value = max(0.0, min(1.0, value))
        self.brightness = value
        self.presto.set_backlight(value)

    def adjust_brightness(self, delta):
        """Adjusts brightness by delta."""
        new_val = self.brightness + delta
        # Clamp to 0.1-1.0 range (don't go fully black via adjustment)
        new_val = max(0.1, min(1.0, new_val))
        self.set_backlight(new_val)

    def turn_off(self):
        """Turns off display."""
        # Don't update self.brightness here so we can restore it
        self.presto.set_backlight(0.0)
        self.presto.auto_ambient_leds(False)
        # Clear LEDs manually as clear_leds() doesn't exist
        for i in range(7):
            self.presto.set_led_rgb(i, 0, 0, 0)
        # Clear display buffer so old image doesn't flash on wake
        self.clear()
        
    def turn_on(self, value=None):
        """Turns on display. Restores previous brightness if value is None."""
        if value is not None:
            self.set_backlight(value)
        else:
            self.set_backlight(self.brightness)
        self.presto.auto_ambient_leds(True)

    def show_text(self, text, scale=1.0, y_offset=0):
        self.display.set_pen(self.black)
        self.display.clear()
        
        self.display.set_pen(self.white)
        self.display.set_font("bitmap8") 
        
        # Center text roughly
        text_width = self.display.measure_text(text, scale)
        x = (self.width - text_width) // 2
        y = (self.height // 2) + y_offset
        
        self.display.text(text, x, y, scale=scale)
        self.presto.update()

    def is_progressive_jpeg(self, data):
        """Checks if JPEG data uses progressive encoding (SOF2 = 0xFFC2)."""
        i = 0
        if len(data) < 2 or data[0] != 0xFF or data[1] != 0xD8:
            return False # Not a JPEG
        i += 2
        while i < len(data) - 1:
            # Find next marker (0xFF followed by non-0xFF)
            while i < len(data) and data[i] != 0xFF: i += 1
            while i < len(data) and data[i] == 0xFF: i += 1
            
            if i >= len(data): break
            marker = data[i]
            i += 1
            
            # SOF2 = Progressive (0xC2)
            if marker == 0xC2: return True
            # SOF0 = Baseline (0xC0), SOS = Start of Scan (0xDA) -> Stop
            if marker == 0xC0 or marker == 0xDA: return False
            
            # Skip segment payload
            if i + 2 > len(data): break
            length = (data[i] << 8) | data[i+1]
            i += length
        return False

    def show_album_art(self, jpg_data):
        if not jpg_data:
            self.display.set_pen(self.black)
            self.display.clear()
            print("Error: No JPG data to display")
            self.show_text("No Data")
            self.presto.update()
            return

        if self.is_progressive_jpeg(jpg_data):
            print("Skipping update: Progressive JPEG detected (unsupported). Keeping previous image.")
            return

        print(f"Displaying JPG, size: {len(jpg_data)} bytes")

        try:
            self.jpeg.open_RAM(jpg_data)
            w = self.jpeg.get_width()
            h = self.jpeg.get_height()
            
            print(f"Screen: {self.width}x{self.height}, Image: {w}x{h}")
            
            gc.collect()

            # Allocate buffer for the full source image
            buf = bytearray(w * h * 2)
            src_gfx = PicoGraphics(width=w, height=h, pen_type=PEN_RGB565, buffer=buf)
            
            # Create a new jpegdec instance attached to the source graphics buffer
            j_src = jpegdec.JPEG(src_gfx)
            j_src.open_RAM(jpg_data)
            j_src.decode(0, 0) # Decode the full image into the buffer
            
            # self.presto.buffer is exposed because we used direct_to_fb=True
            scale_blit_viper(buf, self.presto.buffer, w, h, self.width, self.height)
                
            self.presto.update() # Final update
            
            return
            
        except Exception as e:
            print(f"Error displaying image: {e}")
            self.show_text("Art Error")
            
        self.presto.update()
