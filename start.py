#!/usr/bin/env python3

import os
import subprocess as sp
from pathlib import Path
import time
import capture

data_path = str(Path.joinpath(Path.home(), ".dte"))
device = data_path + '/device'
vendor_name = ''
model_name = ''

#print (model_name)

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
    model_name = ''
    vendor_name = ''
    f = open(device, 'w')
    f.write('')
    f.close()

while True:
    device_detect()
    if model_name:
        print('Something is connected')
        vendor_name = sp.getoutput('grep . /sys/bus/firewire/devices/fw1/vendor_name')
        filename = vendor_name + ' ' + model_name + '-'
        #os.system("capture.py " + filename)
        #capture.run(filename)
    else:
        print('Nothing connected')
        capture.run()
    time.sleep(2)