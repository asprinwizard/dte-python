#!/usr/bin/env python3

from display.lcd1602_IC2 import template01 as template

#display = template.lcd()

def test():
    display = template.lcd()
    display.updateDevice('Sony HVR-A1E')
    display.updateFormat('HDV')
    display.updateStatus('Standby')
    display.updateCounter('00:00:00')
