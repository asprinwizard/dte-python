#!/usr/bin/env python3

import os
import sys
import time
import json
import signal
import multiprocessing
import subprocess
from pathlib import Path
import RPi.GPIO as GPIO
from gpiozero import Button, PWMOutputDevice

# Import project modules
from display.lcd1602.lcd_display import LCD_Display_Rec_01 as LCD
from config.loader import load_config, reset

# GPIO pin definitions
LCD_BRIGHTNESS_PIN = 12
LCD_CONTRAST_PIN = 13
ROTARY_PIN_A = 26
ROTARY_PIN_B = 20
ROTARY_BUTTON_PIN = 5

# Mode definitions
MODE_CAPTURE = 'capture'
MODE_PLAYBACK = 'playback'
MODE_SETTINGS = 'settings'

# Storage location priorities
STORAGE_PRIORITIES = ['sd', 'usb', 'internal']

class DTERecorder:
    def __init__(self):
        # Initialize paths
        self.base_path = Path().absolute()
        self.dvgrab_path = str(Path.home() / 'dvgrab-dte' / 'dvgrab_status_ready.py')
        self.user_home = Path.home()
        self.config_dir = self.user_home / '.dte'
        self.config_file = self.config_dir / 'config'
        self.dvgrab_status_file = self.config_dir / 'dvgrab_status.json'
        
        # Create config directory if it doesn't exist
        if not self.config_dir.exists():
            self.config_dir.mkdir(parents=True)
        
        # Initialize config
        self.load_config()
        
        # Initialize display
        self.display = LCD()
        self.setup_display()
        
        # Initialize storage
        self.storage_location = None
        self.set_storage_location()
        
        # Initialize device tracking
        self.connected_device = None
        self.recording = False
        self.dvgrab_process = None
        
        # Initialize mode
        self.current_mode = MODE_CAPTURE
        self.idle_timer = None
        
        # Initialize GPIO
        self.setup_gpio()
        
        # Process trackers
        self.capture_process = None
        self.playback_process = None

        # Menu configuration
        self.settings_menu = [
            {
                'label': 'LCD Brightness',
                'key': 'lcd_brightness',
                'template': 'range'
            },
            {
                'label': 'LCD Contrast',
                'key': 'lcd_contrast',
                'template': 'range'
            },
            {
                'label': 'Factory Reset',
                'template': 'confirm'
            }
        ]
        self.selected_menu_item = 0
        self.confirm_value = 'No'
        
        # Playback variables
        self.video_files = []
        self.selected_file_index = 0
        self.playback_status = 'PAUSE'
        
        # Register signal handlers
        signal.signal(signal.SIGTERM, self.cleanup)
        signal.signal(signal.SIGINT, self.cleanup)

    def load_config(self):
        # Create config file from default if it doesn't exist
        if not self.config_file.exists():
            default_config = self.base_path / 'config.txt'
            if not self.config_dir.exists():
                self.config_dir.mkdir(parents=True)
            with open(default_config, 'r') as src, open(self.config_file, 'w') as dst:
                dst.write(src.read())
        
        # Load config
        self.config = {}
        with open(self.config_file, 'r') as f:
            for line in f:
                if line.strip() and not line.strip().startswith('#'):
                    key, value = line.strip().split('=', 1)
                    self.config[key.strip()] = value.strip()

    def update_config(self, key, value):
        self.config[key] = value
        with open(self.config_file, 'w') as f:
            for k, v in self.config.items():
                f.write(f"{k}={v}\n")

    def setup_display(self):
        # Set display brightness and contrast based on config
        brightness = int(self.config.get('lcd_brightness', 8))
        contrast = int(self.config.get('lcd_contrast', 8))
        
        # Initialize PWM for brightness and contrast
        self.brightness_pwm = PWMOutputDevice(LCD_BRIGHTNESS_PIN)
        self.contrast_pwm = PWMOutputDevice(LCD_CONTRAST_PIN)
        
        # Set brightness and contrast (convert from 0-16 to 0-1 scale)
        self.brightness_pwm.value = brightness / 16
        self.contrast_pwm.value = contrast / 16
        
        # Display welcome message
        self.display.updateFormat("DTE")
        self.display.updateDevice("Starting...")
        self.display.updateStatus("STBY")
        self.display.updateCounter("00:00:00")

    def setup_gpio(self):
        # Set up GPIO for rotary encoder
        GPIO.setmode(GPIO.BCM)
        GPIO.setup(ROTARY_PIN_A, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(ROTARY_PIN_B, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        GPIO.setup(ROTARY_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
        
        # Add event detection for rotary encoder
        GPIO.add_event_detect(ROTARY_PIN_A, GPIO.FALLING, callback=self.rotary_callback, bouncetime=50)
        GPIO.add_event_detect(ROTARY_BUTTON_PIN, GPIO.FALLING, callback=self.button_callback, bouncetime=300)
        
        # Variables for tracking button state
        self.button_press_time = 0

    def rotary_callback(self, channel):
        if GPIO.input(ROTARY_PIN_B) == 0:
            self.rotary_clockwise()
        else:
            self.rotary_counterclockwise()
        
        # Reset idle timer
        self.reset_idle_timer()

    def rotary_clockwise(self):
        if self.current_mode == MODE_PLAYBACK:
            if self.playback_status == 'PAUSE':
                # Navigate file list
                self.selected_file_index = (self.selected_file_index + 1) % len(self.video_files)
                self.display_selected_file()
            
        elif self.current_mode == MODE_SETTINGS:
            if 'template' in self.settings_menu[self.selected_menu_item]:
                template = self.settings_menu[self.selected_menu_item]['template']
                
                if template == 'range':
                    # Increase value for range template
                    key = self.settings_menu[self.selected_menu_item]['key']
                    current_value = int(self.config.get(key, 8))
                    new_value = min(16, current_value + 1)
                    self.update_config(key, str(new_value))
                    
                    # Update display
                    if key == 'lcd_brightness':
                        self.brightness_pwm.value = new_value / 16
                    elif key == 'lcd_contrast':
                        self.contrast_pwm.value = new_value / 16
                    
                    # Update display
                    self.display_setting_value(key, new_value)
                
                elif template == 'confirm':
                    # Toggle between Yes and No
                    self.confirm_value = 'Yes' if self.confirm_value == 'No' else 'No'
                    self.display_confirm_template()

    def rotary_counterclockwise(self):
        if self.current_mode == MODE_PLAYBACK:
            if self.playback_status == 'PAUSE':
                # Navigate file list
                self.selected_file_index = (self.selected_file_index - 1) % len(self.video_files)
                self.display_selected_file()
            
        elif self.current_mode == MODE_SETTINGS:
            if 'template' in self.settings_menu[self.selected_menu_item]:
                template = self.settings_menu[self.selected_menu_item]['template']
                
                if template == 'range':
                    # Decrease value for range template
                    key = self.settings_menu[self.selected_menu_item]['key']
                    current_value = int(self.config.get(key, 8))
                    new_value = max(0, current_value - 1)
                    self.update_config(key, str(new_value))
                    
                    # Update display
                    if key == 'lcd_brightness':
                        self.brightness_pwm.value = new_value / 16
                    elif key == 'lcd_contrast':
                        self.contrast_pwm.value = new_value / 16
                    
                    # Update display
                    self.display_setting_value(key, new_value)
                
                elif template == 'confirm':
                    # Toggle between Yes and No
                    self.confirm_value = 'Yes' if self.confirm_value == 'No' else 'No'
                    self.display_confirm_template()

    def button_callback(self, channel):
        # Record button press time
        self.button_press_time = time.time()
        
        # Wait for button release
        while GPIO.input(ROTARY_BUTTON_PIN) == 0:
            time.sleep(0.01)
        
        # Calculate press duration
        press_duration = time.time() - self.button_press_time
        
        # Check if long press (2 seconds)
        if press_duration >= 2:
            self.handle_long_press()
        else:
            self.handle_short_press()
        
        # Reset idle timer
        self.reset_idle_timer()

    def handle_short_press(self):
        if self.current_mode == MODE_CAPTURE:
            # Only allow mode change when not recording
            if not self.recording:
                self.switch_mode(MODE_PLAYBACK)
        
        elif self.current_mode == MODE_PLAYBACK:
            if self.playback_status == 'PAUSE':
                # Start playback of selected file
                self.playback_status = 'PLAY'
                self.display_playback_status()
            else:
                # Pause playback
                self.playback_status = 'PAUSE'
                self.display_playback_status()
        
        elif self.current_mode == MODE_SETTINGS:
            menu_item = self.settings_menu[self.selected_menu_item]
            
            if menu_item['template'] == 'range':
                # Return to settings menu
                self.display_settings_menu()
            
            elif menu_item['template'] == 'confirm':
                # Check confirm value
                if self.confirm_value == 'Yes':
                    # Perform factory reset
                    self.factory_reset()
                else:
                    # Return to settings menu
                    self.display_settings_menu()

    def handle_long_press(self):
        if self.current_mode == MODE_CAPTURE:
            # Only allow mode change when not recording
            if not self.recording:
                self.switch_mode(MODE_SETTINGS)
        
        elif self.current_mode == MODE_PLAYBACK:
            # Return to file list if playing, or exit to capture mode
            if self.playback_status == 'PLAY':
                self.playback_status = 'PAUSE'
                self.display_file_list()
            else:
                self.switch_mode(MODE_CAPTURE)
        
        elif self.current_mode == MODE_SETTINGS:
            # Exit settings mode
            self.switch_mode(MODE_CAPTURE)

    def switch_mode(self, new_mode):
        # Stop any running processes for current mode
        if self.current_mode == MODE_CAPTURE and self.capture_process and self.capture_process.is_alive():
            self.stop_capture_process()
        
        # Set new mode
        self.current_mode = new_mode
        
        # Initialize new mode
        if new_mode == MODE_CAPTURE:
            self.start_capture_mode()
        elif new_mode == MODE_PLAYBACK:
            self.start_playback_mode()
        elif new_mode == MODE_SETTINGS:
            self.start_settings_mode()
        
        # Reset idle timer
        self.reset_idle_timer()

    def reset_idle_timer(self):
        # Only set timer for non-capture modes
        if self.current_mode != MODE_CAPTURE:
            if self.idle_timer:
                self.idle_timer.cancel()
            self.idle_timer = threading.Timer(15, self.handle_idle_timeout)
            self.idle_timer.daemon = True
            self.idle_timer.start()

    def handle_idle_timeout(self):
        # Return to capture mode after timeout
        if self.current_mode != MODE_CAPTURE:
            self.switch_mode(MODE_CAPTURE)

    def set_storage_location(self):
        # Check for storage devices in priority order
        for storage_type in STORAGE_PRIORITIES:
            if storage_type == 'sd':
                # Skip SD for now as mentioned in spec
                continue
            elif storage_type == 'usb':
                # Check for USB drive
                if self.check_usb_mounted():
                    self.storage_location = 'usb'
                    self.videos_path = Path('/media/usb/Videos')
                    break
            elif storage_type == 'internal':
                # Use internal storage as fallback
                self.storage_location = 'internal'
                self.videos_path = self.user_home / 'Videos'
                break
        
        # Create Videos directory if it doesn't exist
        if not self.videos_path.exists():
            self.videos_path.mkdir(parents=True)

    def check_usb_mounted(self):
        # Check if USB is mounted at /media/usb
        return Path('/media/usb').exists()

    def monitor_storage(self):
        # Check for storage changes and update accordingly
        current_storage = self.storage_location
        self.set_storage_location()
        
        # If storage changed, stop capture and update
        if current_storage != self.storage_location:
            if self.dvgrab_process:
                self.stop_dvgrab()
            
            # Display message
            self.display.updateDevice("Please Wait")
            time.sleep(1)
            
            # Restart capture process if in capture mode
            if self.current_mode == MODE_CAPTURE:
                self.detect_device()

    def detect_device(self):
        # Run dvgrab wrapper with --help to see if any devices are found
        try:
            result = subprocess.run(['python3', self.dvgrab_path, '--help'], 
                                    stdout=subprocess.PIPE, 
                                    stderr=subprocess.PIPE, 
                                    timeout=2)
            
            # Check if output indicates device found
            output = result.stderr.decode('utf-8')
            if "No camera exists" not in output:
                # Extract device information (in real implementation, parse vendor/model)
                device_info = self.extract_device_info(output)
                if device_info:
                    self.connected_device = device_info
                    return True
            
            # No device found
            self.connected_device = None
            self.display.updateDevice("No Device")
            return False
            
        except subprocess.TimeoutExpired:
            # Timeout, assume no device
            self.connected_device = None
            return False
    
    def extract_device_info(self, output):
        # In real implementation, parse actual device vendor/model
        # For now, return dummy value
        return "Sony HVR-A1E"

    def start_dvgrab(self):
        # Create filename with device prefix or fallback
        if self.connected_device:
            filename_prefix = self.connected_device.replace(' ', '-')
        else:
            filename_prefix = "dte-capture"
        
        # Prepare dvgrab wrapper command
        cmd = [
            'python3',
            self.dvgrab_path,
            '--buffers', '10',
            '--recordonly',
            '--autosplit',
            '--interactive',
            f"{self.videos_path}/{filename_prefix}-"
        ]
        
        # Start dvgrab wrapper process
        self.dvgrab_process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
            bufsize=1
        )
        
        # Update display
        self.display.updateFormat("DV")  # Default format, will be updated
        if self.connected_device:
            self.display.updateDevice(self.connected_device[:10])  # Truncate if needed
        else:
            self.display.updateDevice("Unknown")
        self.display.updateStatus("STBY")
        self.display.updateCounter("00:00:00")
        
        return True

    def stop_dvgrab(self):
        if self.dvgrab_process:
            # Terminate dvgrab process
            self.dvgrab_process.terminate()
            try:
                self.dvgrab_process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.dvgrab_process.kill()
            
            self.dvgrab_process = None
            self.recording = False

    def parse_dvgrab_status(self):
        # Read and parse dvgrab status from JSON file
        try:
            if self.dvgrab_status_file.exists():
                with open(self.dvgrab_status_file, 'r') as f:
                    data = json.load(f)
                    
                if 'status' in data:
                    self.display.updateStatus('REC' if data['status'] == 'REC' else 'STBY')
                    self.recording = data['status'] == 'REC'
                if 'timecode' in data:
                    self.display.updateCounter(data['timecode'])
                if 'format' in data:
                    self.display.updateFormat(data['format'])
        except (json.JSONDecodeError, FileNotFoundError):
            # Handle JSON errors or missing file
            pass

    def capture_loop(self):
        # Main capture process loop
        while True:
            # Check for device
            if not self.connected_device or not self.detect_device():
                # No device connected, poll every second
                self.display.updateDevice("No Device")
                time.sleep(1)
                continue
            
            # Device connected, start dvgrab if not running
            if not self.dvgrab_process:
                self.start_dvgrab()
            
            # Process dvgrab status
            if self.dvgrab_process:
                # Read status from JSON file
                self.parse_dvgrab_status()
                
                # Check if process is still running
                if self.dvgrab_process.poll() is not None:
                    # Process ended, reset
                    self.dvgrab_process = None
                    self.connected_device = None
            
            # Check for storage changes
            self.monitor_storage()
            
            # Sleep briefly
            time.sleep(0.1)

    def start_capture_mode(self):
        # Display waiting message
        self.display.updateDevice("Starting...")
        
        # Start capture process
        if not self.capture_process or not self.capture_process.is_alive():
            self.capture_process = multiprocessing.Process(target=self.capture_loop)
            self.capture_process.daemon = True
            self.capture_process.start()

    def stop_capture_process(self):
        if self.capture_process and self.capture_process.is_alive():
            # Stop dvgrab
            self.stop_dvgrab()
            
            # Terminate process
            self.capture_process.terminate()
            self.capture_process.join(timeout=3)
            
            # Force kill if still alive
            if self.capture_process.is_alive():
                self.capture_process.kill()
                self.capture_process.join()

    def start_playback_mode(self):
        # Load video files
        self.load_video_files()
        
        # Display file list
        self.display_file_list()

    def load_video_files(self):
        # Get list of video files
        self.video_files = list(self.videos_path.glob('*.dv'))
        self.video_files.extend(self.videos_path.glob('*.m2t'))  # HDV files
        
        # Sort by modification time (newest first)
        self.video_files.sort(key=lambda x: x.stat().st_mtime, reverse=True)
        
        # Reset selected index
        self.selected_file_index = 0

    def display_file_list(self):
        # Show file selection screen
        self.display.updateDevice("Select File:")
        
        if self.video_files:
            filename = self.video_files[self.selected_file_index].name
            self.display.updateStatus(filename[:16])  # Truncate if needed
        else:
            self.display.updateStatus("No files found")

    def display_selected_file(self):
        if self.video_files:
            filename = self.video_files[self.selected_file_index].name
            self.display.updateStatus(filename[:16])  # Truncate if needed

    def display_playback_status(self):
        if self.video_files:
            filename = self.video_files[self.selected_file_index].name
            self.display.updateDevice(filename[:13])
            self.display.updateStatus("PLAY" if self.playback_status == 'PLAY' else "PAUSE")
            self.display.updateCounter("00:00:00")  # Would be updated during actual playback

    def start_settings_mode(self):
        # Display settings menu
        self.selected_menu_item = 0
        self.display_settings_menu()

    def display_settings_menu(self):
        # Show currently selected menu item
        self.display.updateDevice(self.settings_menu[self.selected_menu_item]['label'])
        self.display.updateStatus("")
        
        # If enter item with click, show appropriate template
        menu_item = self.settings_menu[self.selected_menu_item]
        if menu_item['template'] == 'range':
            key = menu_item['key']
            value = int(self.config.get(key, 8))
            self.display_setting_value(key, value)
        elif menu_item['template'] == 'confirm':
            self.confirm_value = 'No'  # Default to No
            self.display_confirm_template()

    def display_setting_value(self, key, value):
        # Display the value as blocks (filled for the value, empty for remaining)
        block_display = '█' * value + '░' * (16 - value)
        self.display.updateStatus(block_display)

    def display_confirm_template(self):
        self.display.updateDevice("Are you sure?")
        self.display.updateStatus(self.confirm_value)

    def factory_reset(self):
        # Display message
        self.display.updateDevice("Resetting...")
        self.display.updateStatus("Please wait")
        
        # Delete config file
        if self.config_file.exists():
            self.config_file.unlink()
        
        # Reboot system
        subprocess.run(['sudo', 'reboot'])

    def cleanup(self, signum=None, frame=None):
        # Stop processes
        self.stop_dvgrab()
        self.stop_capture_process()
        
        # Clean up GPIO
        GPIO.cleanup()
        
        # Exit
        sys.exit(0)

    def run(self):
        # Start in capture mode
        self.switch_mode(MODE_CAPTURE)
        
        # Main loop
        try:
            while True:
                # Check for storage changes
                self.monitor_storage()
                
                # Sleep briefly
                time.sleep(0.1)
        except KeyboardInterrupt:
            self.cleanup()


if __name__ == "__main__":
    # Import threading here to avoid circular import
    import threading
    
    # Create and run recorder
    recorder = DTERecorder()
    recorder.run()
