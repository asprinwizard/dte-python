#!/usr/bin/env python3

import time
import sys
import signal
import RPi.GPIO as GPIO
from gpiozero import PWMOutputDevice
from display.lcd1602.lcd_display import LCD_Display_Rec_01 as LCD

# GPIO pin definitions (matching start.py)
LCD_BRIGHTNESS_PIN = 12
LCD_CONTRAST_PIN = 13
ROTARY_PIN_A = 26
ROTARY_PIN_B = 20
ROTARY_BUTTON_PIN = 5

class DTEHardwareTest:
    def __init__(self):
        print("DTE Hardware Test - Starting...")
        
        # Initialize display
        try:
            self.display = LCD()
            print("✓ LCD Display initialized successfully")
        except Exception as e:
            print(f"✗ LCD Display initialization failed: {e}")
            sys.exit(1)
        
        # Initialize PWM for brightness and contrast
        try:
            self.brightness_pwm = PWMOutputDevice(LCD_BRIGHTNESS_PIN)
            self.contrast_pwm = PWMOutputDevice(LCD_CONTRAST_PIN)
            print("✓ PWM for brightness/contrast initialized")
        except Exception as e:
            print(f"✗ PWM initialization failed: {e}")
            sys.exit(1)
        
        # Initialize GPIO for rotary encoder
        try:
            self.setup_gpio()
            print("✓ Rotary encoder GPIO initialized")
        except Exception as e:
            print(f"✗ GPIO initialization failed: {e}")
            sys.exit(1)
        
        # Test variables
        self.test_counter = 0
        self.button_press_time = 0
        self.last_rotation = "None"
        
        # Register cleanup handler
        signal.signal(signal.SIGINT, self.cleanup)
        signal.signal(signal.SIGTERM, self.cleanup)

    def setup_gpio(self):
        # Set up GPIO for rotary encoder
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(ROTARY_PIN_A, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(ROTARY_PIN_B, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(ROTARY_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        # Add event detection for rotary encoder
        GPIO.add_event_detect(ROTARY_PIN_A, GPIO.FALLING, callback=self.rotary_callback, bouncetime=50)
        GPIO.add_event_detect(ROTARY_BUTTON_PIN, GPIO.FALLING, callback=self.button_callback, bouncetime=300)

    def rotary_callback(self, channel):
        if GPIO.input(ROTARY_PIN_B) == 0:
            self.last_rotation = "Clockwise"
            self.test_counter += 1
        else:
            self.last_rotation = "Counter-CW"
            self.test_counter -= 1
        
        print(f"Rotary: {self.last_rotation}, Counter: {self.test_counter}")
        self.update_test_display()

    def button_callback(self, channel):
        # Record button press time
        self.button_press_time = time.time()
        
        # Wait for button release
        while GPIO.input(ROTARY_BUTTON_PIN) == 0:
            time.sleep(0.01)
        
        # Calculate press duration
        press_duration = time.time() - self.button_press_time
        
        if press_duration >= 2:
            print(f"Button: LONG PRESS ({press_duration:.1f}s)")
            self.display.updateStatus("LONG PRESS")
        else:
            print(f"Button: Short press ({press_duration:.1f}s)")
            self.display.updateStatus("SHORT PRESS")

    def update_test_display(self):
        # Update display with current test info
        self.display.updateCounter(f"{self.test_counter:08d}")
        self.display.updateDevice(f"Rot: {self.last_rotation}")

    def test_lcd_display(self):
        print("\n--- Testing LCD Display ---")
        
        # Test 1: Basic text display
        print("Test 1: Basic text display")
        self.display.updateFormat("DTE")
        self.display.updateDevice("Test Mode")
        self.display.updateStatus("STBY")
        self.display.updateCounter("00:00:00")
        time.sleep(2)
        
        # Test 2: Different formats
        print("Test 2: Format display")
        formats = ["DV", "HDV", "TEST"]
        for fmt in formats:
            self.display.updateFormat(fmt)
            time.sleep(1)
        
        # Test 3: Device names (test truncation)
        print("Test 3: Device name display")
        devices = ["Sony HVR-A1E", "Canon XM2", "Very Long Device Name"]
        for device in devices:
            self.display.updateDevice(device)
            time.sleep(1)
        
        # Test 4: Status display
        print("Test 4: Status display")
        statuses = ["STBY", "REC", "PLAY", "PAUSE"]
        for status in statuses:
            self.display.updateStatus(status)
            time.sleep(1)
        
        # Test 5: Counter display
        print("Test 5: Counter display")
        counters = ["00:00:00", "01:23:45", "99:59:59"]
        for counter in counters:
            self.display.updateCounter(counter)
            time.sleep(1)
        
        print("✓ LCD Display tests completed")

    def test_brightness_contrast(self):
        print("\n--- Testing Brightness and Contrast ---")
        
        self.display.updateFormat("PWM")
        self.display.updateDevice("Brightness")
        
        # Test brightness
        print("Testing brightness (0-100%)")
        for brightness in [0, 25, 50, 75, 100]:
            self.brightness_pwm.value = brightness / 100
            self.display.updateStatus(f"Bright: {brightness}%")
            self.display.updateCounter(f"Val: {brightness/100:.2f}")
            print(f"  Brightness: {brightness}%")
            time.sleep(2)
        
        # Reset to 50%
        self.brightness_pwm.value = 0.5
        
        # Test contrast
        self.display.updateDevice("Contrast")
        print("Testing contrast (0-100%)")
        for contrast in [0, 25, 50, 75, 100]:
            self.contrast_pwm.value = contrast / 100
            self.display.updateStatus(f"Contrast: {contrast}%")
            self.display.updateCounter(f"Val: {contrast/100:.2f}")
            print(f"  Contrast: {contrast}%")
            time.sleep(2)
        
        # Reset to 50%
        self.contrast_pwm.value = 0.5
        
        print("✓ Brightness and contrast tests completed")

    def test_block_display(self):
        print("\n--- Testing Block Display (for settings) ---")
        
        self.display.updateFormat("BLCK")
        self.display.updateDevice("Block Test")
        
        # Test block characters for settings display
        for i in range(17):  # 0 to 16
            # Create block display (filled blocks for value, empty for remaining)
            block_display = '█' * i + '░' * (16 - i)
            self.display.updateStatus(block_display)
            self.display.updateCounter(f"Value: {i:02d}")
            print(f"  Blocks: {i}/16")
            time.sleep(0.5)
        
        print("✓ Block display test completed")

    def interactive_test(self):
        print("\n--- Interactive Test Mode ---")
        print("Turn the rotary encoder and press the button to test input")
        print("Press Ctrl+C to exit")
        
        self.display.updateFormat("INT")
        self.display.updateDevice("Interactive")
        self.display.updateStatus("Turn/Press")
        self.display.updateCounter("00000000")
        
        try:
            while True:
                time.sleep(0.1)  # Keep the program running
        except KeyboardInterrupt:
            pass

    def gpio_status_check(self):
        print("\n--- GPIO Status Check ---")
        
        # Check current GPIO states
        print(f"Rotary Pin A (GPIO {ROTARY_PIN_A}): {GPIO.input(ROTARY_PIN_A)}")
        print(f"Rotary Pin B (GPIO {ROTARY_PIN_B}): {GPIO.input(ROTARY_PIN_B)}")
        print(f"Button Pin (GPIO {ROTARY_BUTTON_PIN}): {GPIO.input(ROTARY_BUTTON_PIN)}")
        
        # Display on LCD
        self.display.updateFormat("GPIO")
        self.display.updateDevice("Pin Status")
        self.display.updateStatus(f"A:{GPIO.input(ROTARY_PIN_A)} B:{GPIO.input(ROTARY_PIN_B)} BTN:{GPIO.input(ROTARY_BUTTON_PIN)}")

    def cleanup(self, signum=None, frame=None):
        print("\nCleaning up...")
        
        try:
            # Clear display
            self.display.updateFormat("EXIT")
            self.display.updateDevice("Test Complete")
            self.display.updateStatus("Goodbye!")
            self.display.updateCounter("--------")
        except:
            pass
        
        # Clean up GPIO
        GPIO.cleanup()
        
        # Clean up PWM
        if hasattr(self, 'brightness_pwm'):
            self.brightness_pwm.close()
        if hasattr(self, 'contrast_pwm'):
            self.contrast_pwm.close()
        
        print("✓ Cleanup complete")
        sys.exit(0)

    def run_all_tests(self):
        print("Starting comprehensive hardware test...")
        
        try:
            # Run all automated tests
            self.test_lcd_display()
            time.sleep(1)
            
            self.test_brightness_contrast()
            time.sleep(1)
            
            self.test_block_display()
            time.sleep(1)
            
            self.gpio_status_check()
            time.sleep(2)
            
            # Run interactive test
            self.interactive_test()
            
        except Exception as e:
            print(f"Test failed with error: {e}")
            self.cleanup()

def show_menu():
    print("\n" + "="*50)
    print("DTE Hardware Test Menu")
    print("="*50)
    print("1. Run all tests (recommended)")
    print("2. Test LCD display only")
    print("3. Test brightness/contrast only")
    print("4. Test block display (settings)")
    print("5. Interactive test (rotary + button)")
    print("6. GPIO status check")
    print("7. Exit")
    print("="*50)

def main():
    print("DTE Hardware Test Utility")
    print("=" * 40)
    
    # Initialize hardware test
    try:
        test = DTEHardwareTest()
    except Exception as e:
        print(f"Failed to initialize hardware test: {e}")
        return
    
    while True:
        show_menu()
        try:
            choice = input("Select test (1-7): ").strip()
            
            if choice == '1':
                test.run_all_tests()
            elif choice == '2':
                test.test_lcd_display()
            elif choice == '3':
                test.test_brightness_contrast()
            elif choice == '4':
                test.test_block_display()
            elif choice == '5':
                test.interactive_test()
            elif choice == '6':
                test.gpio_status_check()
            elif choice == '7':
                test.cleanup()
                break
            else:
                print("Invalid choice. Please select 1-7.")
                
        except KeyboardInterrupt:
            test.cleanup()
            break
        except Exception as e:
            print(f"Test error: {e}")
            continue

if __name__ == "__main__":
    main() 