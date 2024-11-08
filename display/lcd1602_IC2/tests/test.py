import sys
import os

# getting the name of the directory
# where the this file is present.
current = os.path.dirname(os.path.realpath(__file__))

# Getting the parent directory name
# where the current directory is present.
parent = os.path.dirname(current)

# adding the parent directory to 
# the sys.path.
sys.path.append(parent)

import I2C_LCD_driver
from time import *

lcd = I2C_LCD_driver.lcd()

lcd.lcd_display_string("Device Name", 1);
lcd.lcd_display_string("Record Status & Counter", 2)
