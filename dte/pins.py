"""Every GPIO used by the recorder, as BCM numbers.

Header pin numbers (standard 40-pin layout) are in the comments.
"""

# LCD brightness / contrast (hardware PWM0 channels 0 and 1)
PWM_BRIGHTNESS = 12     # pin 32
PWM_CONTRAST = 13       # pin 33
PWM_BRIGHTNESS_CHANNEL = 0
PWM_CONTRAST_CHANNEL = 1

# LCD1602, 4-bit parallel mode (RW tied to GND)
LCD_RS = 4              # pin 7  -> LCD pin 4
LCD_EN = 17             # pin 11 -> LCD pin 6
LCD_D4 = 22             # pin 15 -> LCD pin 11
LCD_D5 = 23             # pin 16 -> LCD pin 12
LCD_D6 = 24             # pin 18 -> LCD pin 13
LCD_D7 = 25             # pin 22 -> LCD pin 14

# Rotary encoder
ENCODER_A = 26          # pin 37
ENCODER_B = 20          # pin 38
ENCODER_SWITCH = 5      # pin 29

# Record control
RECORD_BUTTON = 6       # pin 31, active low with internal pull-up
LANC_INPUT = 16         # pin 36, HIGH = record (from the Arduino, via a level shifter)
RECORD_LED = 27         # pin 13, optional tally light
