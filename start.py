#!/usr/bin/env python3

import multiprocessing
import time
from gpiozero import Button
from capture import Capture
from display import Display  # Import the Display class

def run_capture(capture):
    capture.monitor_device()

def switch_to_mode(mode):
    global current_mode, mode1_process, capture_instance
    print(f"Switching to mode {mode}")
    current_mode = mode
    if mode == 2 and mode1_process:
        print("Terminating Mode 1 processes")
        mode1_process.terminate()
        mode1_process.join()

def restart_mode1():
    global mode1_process, capture_instance, display
    if mode1_process.is_alive():
        mode1_process.terminate()
        mode1_process.join()
    capture_instance = Capture(display)  # Pass the display instance
    mode1_process = multiprocessing.Process(target=run_capture, args=(capture_instance,))
    mode1_process.start()

def on_encoder_click():
    if current_mode == 1:
        switch_to_mode(2)
    elif current_mode == 2:
        switch_to_mode(1)

# Setup encoder button on GPIO pin
encoder_button = Button(17)  # Adjust GPIO pin as needed
encoder_button.when_pressed = on_encoder_click

if __name__ == "__main__":
    current_mode = 1
    #display = Display()  # Instantiate the Display class
    #capture_instance = Capture(display)  # Pass Display to Capture
    capture_instance = Capture()  # Pass Display to Capture
    mode1_process = multiprocessing.Process(target=run_capture, args=(capture_instance,))
    mode1_process.start()

    try:
        while True:
            if current_mode == 1 and capture_instance.device_disconnected:
                print("Device disconnected, restarting Mode 1...")
                restart_mode1()
            time.sleep(0.1)
    except KeyboardInterrupt:
        print("Exiting...")
    finally:
        if mode1_process.is_alive():
            mode1_process.terminate()
            mode1_process.join()
