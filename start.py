#!/usr/bin/env python3

import os
import subprocess as sp
from pathlib import Path
import time
import capture
import atexit

data_path = str(Path.joinpath(Path.home(), ".dte"))
log_path = str(Path().absolute()) + '/log.py'
device = data_path + '/device'
vendor_name = ''
model_name = ''
log_process = False

def setup():
    # Run cleanup
    cleanup()

    # Start logging
    start_logging()

    # Pause briefly to allow files to be created
    time.sleep(0.2)

    # Reset the device
    reset_device()

def loop():
    global filename
    global model_name
    global vendor_name
    while True:
        device_detect()
        if model_name:
            print('Something is connected')
            vendor_name = sp.getoutput('grep . /sys/bus/firewire/devices/fw1/vendor_name')
            filename = vendor_name + ' ' + model_name + '-'
        else:
            print('Nothing connected')
            #capture.run()
        time.sleep(2)

def cleanup():
    global log_process
    if log_process:
        status = sp.Popen.poll(log_process)
        if not status:
            sp.Popen.terminate(log_process)
            status = sp.Popen.poll(log_process)
    log_process = False
    

def exit_handler():
    cleanup()

def start_logging():
    global log_process
    log_process = sp.Popen(['python3', log_path])

def device_detect():
    model_name = sp.getoutput('grep . /sys/bus/firewire/devices/fw1/model_name')
    if not model_name:
        print("Waiting for camera")
    elif model_name == 'grep: /sys/bus/firewire/devices/fw1/model_name: No such file or directory':
        print("No firewire driver connected")
    else:
        f = open(device, 'w')
        f.write(model_name)
        f.close()

def reset_device():
    global model_name
    global vendor_name
    model_name = ''
    vendor_name = ''
    f = open(device, 'w')
    f.write('')
    f.close()

# Register handlers
atexit.register(exit_handler)

# Finally run the methods
setup()
loop()