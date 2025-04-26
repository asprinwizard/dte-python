#!/usr/bin/env python3

import multiprocessing
import time
import threading
from display import Display
from capture import Capture
from controller.rotary import MenuNavigator  # Assuming MenuNavigator is in its own file for better organization

class StartProcess:
    def __init__(self):
        self.mode = 1
        self.display = Display()
        self.menu_items = ["Option 1", "Option 2", "Option 3", "Exit"]
        self.navigator = MenuNavigator(rotary_clk_pin=17, rotary_dt_pin=18, button_pin=27,
                                       display=self.display, menu_items=self.menu_items)
        self.navigator_thread = threading.Thread(target=self.navigator.run, daemon=True)
        self.navigator_thread.start()  # Start menu navigation in the background

    def start_mode_1(self):
        print("Starting Mode 1")
        self.capture_instance = Capture()  # Pass Display to Capture
        self.mode1_process = multiprocessing.Process(target=run_capture, args=(capture_instance,))
        self.mode1_process.start()
        # Code specific to Mode 1 goes here

    def start_mode_2(self):
        print("Starting Mode 2")
        # Code specific to Mode 2 goes here

        if self.mode1_process:
            print("Terminating Mode 1 processes")
            self.mode1_process.terminate()
            self.mode1_process.join()

    def stop(self):
        # Clean up or exit actions
        print("Stopping program")
        GPIO.cleanup()  # Ensure GPIO is cleaned up
        self.display.clear()  # Clear display before exit
        if self.mode1_process:
            print("Terminating Mode 1 processes")
            self.mode1_process.terminate()
            self.mode1_process.join()

    def reset()

    def run_capture(capture):
        capture.monitor_device()

if __name__ == "__main__":
    mode = 1
    process = StartProcess()
    try:
        process.start_mode_1()  # Call Mode 1 or Mode 2 as needed, or switch as required
        # You can also switch between start_mode_1 and start_mode_2 as needed

        while True:
            if mode == 1 and process.capture_instance.device_disconnected:
                print("Device disconnected, restarting Mode 1...")
                process.reset()
            time.sleep(0.1)
    except KeyboardInterrupt:
        process.stop()
