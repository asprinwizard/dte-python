import time
import RPi.GPIO as GPIO
from display import Display  # assuming you have a Display class for the LCD

class MenuNavigator:
    def __init__(self, rotary_clk_pin, rotary_dt_pin, button_pin, display, menu_items, long_press_duration=2):
        self.rotary_clk_pin = rotary_clk_pin
        self.rotary_dt_pin = rotary_dt_pin
        self.button_pin = button_pin
        self.display = display
        self.menu_items = menu_items
        self.long_press_duration = long_press_duration
        
        self.current_index = 0
        self.in_menu = False
        self.button_press_time = None

        # GPIO setup
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(self.rotary_clk_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.rotary_dt_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(self.button_pin, GPIO.IN, pull_up_down=GPIO.PUD_UP)

        # Set up event detection
        GPIO.add_event_detect(self.button_pin, GPIO.BOTH, callback=self.button_callback, bouncetime=300)
        GPIO.add_event_detect(self.rotary_clk_pin, GPIO.BOTH, callback=self.rotary_callback, bouncetime=50)

        # Initialize display
        self.display.clear()
        self.display.display_text("Press to start menu")

    def enter_menu(self):
        self.in_menu = True
        self.current_index = 0
        self.display.clear()
        self.display.display_text(self.menu_items[self.current_index])

    def exit_menu(self):
        self.in_menu = False
        self.display.clear()
        self.display.display_text("Press to start menu")

    def navigate_menu(self, direction):
        if direction == "left":
            self.current_index = (self.current_index - 1) % len(self.menu_items)
        elif direction == "right":
            self.current_index = (self.current_index + 1) % len(self.menu_items)
        self.display.clear()
        self.display.display_text(self.menu_items[self.current_index])

    def select_item(self):
        selected_item = self.menu_items[self.current_index]
        self.display.clear()
        self.display.display_text(f"Selected: {selected_item}")
        time.sleep(1)  # brief delay for feedback
        if selected_item == "Exit":
            self.exit_menu()

    def button_callback(self, channel):
        if GPIO.input(self.button_pin) == GPIO.LOW:  # button pressed
            self.button_press_time = time.time()
        else:  # button released
            press_duration = time.time() - self.button_press_time
            if press_duration >= self.long_press_duration:
                self.exit_menu()
            elif not self.in_menu:
                self.enter_menu()
            else:
                self.select_item()

    def rotary_callback(self, channel):
        if self.in_menu:
            clk_state = GPIO.input(self.rotary_clk_pin)
            dt_state = GPIO.input(self.rotary_dt_pin)
            if clk_state == dt_state:
                self.navigate_menu("right")
            else:
                self.navigate_menu("left")

    def run(self):
        try:
            while True:
                time.sleep(0.1)  # Keep the program running

        except KeyboardInterrupt:
            print("Exiting program")

        finally:
            GPIO.cleanup()
            self.display.clear()
