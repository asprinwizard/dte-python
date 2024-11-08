#!/usr/bin/env python3

import os, sys
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

import I2C_LCD_driver

class lcd:

    def __init__(self):
        self.device = I2C_LCD_driver.lcd()

    def updateDevice(self, device):
        self.device.lcd_display_string(device, 1, 4)

    def updateFormat(self, format):
        self.device.lcd_display_string(format, 1)

    def updateStatus(self, status):
        self.device.lcd_display_string(status, 2)

    def updateCounter(self, counter):
        self.device.lcd_display_string(counter, 2, 8)
