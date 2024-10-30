#!/usr/bin/env python3

import subprocess
import time
from pathlib import Path



class Capture:
    
    #def __init__(self, display):
    #    self.dvgrab_process = None
    #    self.running = False
    #    self.device_disconnected = False
    #    self.display = display

        
    def __init__(self):
        self.app_path = str(Path().absolute()) + '/dvgrab'
        self.data_path = str(Path.joinpath(Path.home(), ".dte"))
        self.log_file_path = self.data_path + '/output'
        self.capture_path = str(Path.joinpath(Path.home(), "Videos"))
        self.dvgrab_params = "--buffers 10 --recordonly --autosplit --interactive"

        self.dvgrab_process = None
        self.running = False
        self.device_disconnected = False

    def detect_device(self):
        print("Detecting firewire device...")
        time.sleep(1)
        return True  # Assume device is detected for demonstration

    def start_dvgrab(self):
        #self.display.show_message("Device connected - Starting dvgrab")
        #log_file_path = "/path_to_logs/output.log"  # Path to the log file

        # Open the log file and start dvgrab, redirecting stderr to the log file
        with open(self.log_file_path, "a") as log_file:
            self.dvgrab_process = subprocess.Popen(
                ['dvgrab', '--buffers', '10', '--recordonly', '--autosplit', '--interactive',
                 '/path_to_capture_dir/filename.dv'],
                stdout=subprocess.PIPE,
                stderr=log_file
            )
        self.running = True
        self.device_disconnected = False

    def stop_dvgrab(self):
        if self.dvgrab_process:
            #self.display.show_message("Device disconnected - Stopping dvgrab")
            self.dvgrab_process.terminate()
            self.dvgrab_process.wait()
            self.dvgrab_process = None
        self.running = False
        self.device_disconnected = True

    def monitor_device(self):
        while True:
            if self.detect_device():
                if not self.running:
                    self.start_dvgrab()
            else:
                if self.running:
                    self.stop_dvgrab()
                    break  # Exit loop on device disconnection
            time.sleep(1)

