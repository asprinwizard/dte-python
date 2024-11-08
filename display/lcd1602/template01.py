#!/usr/bin/env python3

import os, sys
sys.path.append(os.path.dirname(os.path.realpath(__file__)))

#import I2C_LCD_driver
import Adafruit_CharLCD

class lcd:

    def __init__(self):
        # Constants
        self.DEVICE_LENGTH = 10
        self.FORMAT_LENGTH = 4
        self.STATUS_LENGTH = 8
        #self.device = I2C_LCD_driver.lcd()
        
        # Raspberry Pi pin setup
        lcd_rs = 26  # Register select pin
        lcd_en = 19  # Enable pin
        lcd_d4 = 13  # Data pins
        lcd_d5 = 6
        lcd_d6 = 5
        lcd_d7 = 11
        lcd_rs        = 25 
        lcd_en        = 24
        lcd_d4        = 23
        lcd_d5        = 17
        lcd_d6        = 18
        lcd_d7        = 22

        # This will be set by gpio
        lcd_backlight = 4

        # Define LCD column and row size for 16x2 LCD.
        lcd_columns = 16
        lcd_rows = 2

        self.device = Adafruit_CharLCD.Adafruit_CharLCD(lcd_rs, lcd_en, lcd_d4, lcd_d5, lcd_d6, lcd_d7, lcd_columns, lcd_rows, lcd_backlight)
        #self.device.clear()

    def updateDevice(self, device):
        #self.device.lcd_display_string(device, 1, 4)
        self.device.set_cursor(4, 0)
        self.device.lcd.message(device)

    def updateFormat(self, format):
        #self.device.lcd_display_string(format, 1)
        self.device.set_cursor(0, 0)
        self.device.lcd.message(format)

    def updateStatus(self, status):
        #self.device.lcd_display_string(status, 2)
        self.device.set_cursor(0, 1)
        self.device.lcd.message(status)

    def updateCounter(self, counter):
        #self.device.lcd_display_string(counter, 2, 8)
        self.device.set_cursor(8, 1)
        self.device.lcd.message(counter)
