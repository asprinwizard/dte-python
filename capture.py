#!/usr/bin/env python3

import sys
from pathlib import Path
import subprocess as sp

app_path = str(Path().absolute()) + '/dvgrab'
data_path = str(Path.joinpath(Path.home(), ".dte"))
output = data_path + '/output'
capture_path = str(Path.joinpath(Path.home(), "Videos"))
dvgrab_params = "--buffers 10 --recordonly --autosplit --interactive"

def run(filename = 'dvgrab-'):
    command = app_path + ' ' + dvgrab_params + ' ' + capture_path + '/' + filename + ' - 2> ' + output
    print(filename)
    print(command)
    #sp.run(command)

