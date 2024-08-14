#!/usr/bin/env python3

import subprocess as sp
model_name = sp.getoutput('grep . /sys/bus/firewire/devices/fw1/model_name')
#print (model_name)

if not model_name:
    print("Nothing connected")

if model_name == 'grep: /sys/bus/firewire/devices/fw1/model_name: No such file or directory':
    print("No driver connected")