#!/usr/bin/env python3

from . import I2C_LCD_driver

from display.custom.chars.chars5x8 import Custom_Characters

class LCD_Display_Rec_01:

    def __init__(self):
        self.device = I2C_LCD_driver.lcd()

        chars = Custom_Characters()

        self.customChars = [
            chars.record,
            chars.pause
        ]

        #self.customChars = [
        #    # char(0) - Record
        #    [
        #        0b00000,
        #        0b00000,
        #        0b01110,
        #        0b11111,
        #        0b11111,
        #        0b11111,
        #        0b01110,
        #        0b00000            
        #    ],
        #    # Char(1) - Pause
        #    [
        #        0b00000,
        #        0b00000,
        #        0b01010,
        #        0b01010,
        #        0b01010,
        #        0b01010,
        #        0b01010,
        #        0b00000
        #    ],
        #]
#        self.device.lcd_load_custom_chars(customChars)

    def updateDevice(self, device):
        self.device.lcd_display_string(device, 1, 4)

    def updateFormat(self, format):
        self.device.lcd_display_string(format, 1)

    def updateStatus(self, status):
        if status == 'Record':
            #self.device.lcd_display_string(self.device.lcd_write_char(0))
            self.device.lcd_load_custom_chars(self.customChars)
            self.device.lcd_write(0xc0)
            self.device.lcd_write_char(0)
            self.device.lcd_display_string('REC   ', 2, 1)
        elif (status == 'Standby'):
            self.device.lcd_load_custom_chars(self.customChars)
            self.device.lcd_write(0xc0)
            self.device.lcd_write_char(1)
            self.device.lcd_display_string('Paused', 2, 1)
        else:
            self.device.lcd_display_string(status, 2)

    def updateCounter(self, counter):
        self.device.lcd_display_string(counter, 2, 8)
