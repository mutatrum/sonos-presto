import time

# Action Constants
class Action:
    NONE = 0
    PLAY_PAUSE = 1
    NEXT = 2
    PREV = 3
    VOLUME_UP = 4
    VOLUME_DOWN = 5
    BRIGHT_UP = 6
    BRIGHT_DOWN = 7

class TouchManager:
    def __init__(self, presto_inst, width=480, height=480):
        self.presto = presto_inst
        self.width = width
        self.height = height
        
        # State tracking
        self.start_x = 0
        self.start_y = 0
        self.last_x = 0 
        self.last_y = 0
        self.start_time = 0
        self.touch_active = False
        
        # Debouncing/Rate limiting
        self.last_action_time = 0
        
        # Configuration
        self.TAP_TIME_MS = 400
        self.SWIPE_DIST = 60 # Lower threshold slightly for easier triggering
        self.TAP_MOVE_DIST = 20 # Max movement for a tap (prevent sloppy swipes triggering tap)
        self.DRAG_THRESHOLD = 30
        self.DRAG_REPEAT_MS = 100 # How fast to repeat volume/brightness events while dragging

    def poll(self):
        """Polls the touch input and returns an Action based on gestures."""
        # Ensure latest touch data is read from hardware
        self.presto.touch_poll()
        
        t = self.presto.touch_a
        
        now = time.ticks_ms()
        
        if t.touched:
            self.last_x = t.x 
            self.last_y = t.y
            
            if not self.touch_active:
                # Touch Start
                self.touch_active = True
                self.start_x = t.x
                self.start_y = t.y
                self.start_time = now
            else:
                # Dragging Logic (Continuous)
                dy = t.y - self.start_y
                dx = t.x - self.start_x
                
                # Check for Vertical Drag (Volume/Brightness)
                # Must be more vertical than horizontal, and exceed threshold
                if abs(dy) > self.DRAG_THRESHOLD and abs(dy) > abs(dx):
                    if time.ticks_diff(now, self.last_action_time) > self.DRAG_REPEAT_MS:
                        self.last_action_time = now
                        
                        # Determine Side
                        is_right = self.start_x > (self.width // 2)
                        
                        # Reset start_y to allow continuous scrolling
                        # We stepped, so new baseline is current y
                        self.start_y = t.y 
                        
                        if is_right:
                            return Action.VOLUME_DOWN if dy > 0 else Action.VOLUME_UP
                        else:
                            # Inverted Y for brightness usually feels natural (Up = Brighter)
                            # Screen Y grows Down. so dy < 0 is UP.
                            return Action.BRIGHT_DOWN if dy > 0 else Action.BRIGHT_UP

        elif self.touch_active:
            # Touch Release
            self.touch_active = False
            duration = time.ticks_diff(now, self.start_time)
            dx = self.last_x - self.start_x
            dy = self.last_y - self.start_y
            
            if duration < self.TAP_TIME_MS:
                # Swipe must be significantly horizontal
                if abs(dx) > self.SWIPE_DIST and abs(dx) > abs(dy):
                    return Action.NEXT if dx > 0 else Action.PREV # Swipe Right (dx > 0) -> Next
                elif abs(dx) < self.TAP_MOVE_DIST and abs(dy) < self.TAP_MOVE_DIST:
                    return Action.PLAY_PAUSE
                    
        return Action.NONE
