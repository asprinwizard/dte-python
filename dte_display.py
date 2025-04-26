#!/usr/bin/env python3


from display.lcd1602_IC2.lcd_display import LCD_Display_Rec_01 as DisplayDevice
import time

#display = template.lcd()

class Display:

    def __init__(self):
        self.device = DisplayDevice()

    def test(self):
        #display = Display()
        self.updateDevice('Sony HVR-A1E')
        self.updateFormat('HDV')
        self.updateStatus('Standby')
        self.updateCounter('00:00:00')

        time.sleep(3)
        self.updateStatus('Record')
        time.sleep(1)
        self.updateCounter('00:00:01')
        time.sleep(1)
        self.updateCounter('00:00:02')
        time.sleep(1)
        self.updateCounter('00:00:03')
        time.sleep(1)
        self.updateCounter('00:00:04')
        self.updateStatus('Standby')

    def updateDevice(self, device):
        self.device.updateDevice(device)

    def updateStatus(self, status):
        self.device.updateStatus(status)

    def updateFormat(self, format):
        self.device.updateFormat(format)

    def updateCounter(self, counter):
        self.device.updateCounter(counter)

