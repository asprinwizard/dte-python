#!/usr/bin/env python3
import os
import subprocess as sp
from pathlib import Path
import time

data_path = str(Path.joinpath(Path.home(), ".dte"))
output = data_path + '/output'
display = data_path + '/display'

print(data_path)
print(output)
print(display)

if not os.path.exists(data_path): 
    print(data_path + ' needs creating')
    os.makedirs(data_path)
else:
    print(data_path + ' exists')

# Clear out the output file
f = open(output, 'w')
f.write('')
f.close()

# Add starting up to text display
f = open(display, 'w')
f.write('Starting up...')
f.close()

# wait one second
time.sleep(1)

while True:
    print("check logs")
    line = sp.check_output(['tail', '-1', output])
    if not line:
        print("output is empty")
    time.sleep(0.2)