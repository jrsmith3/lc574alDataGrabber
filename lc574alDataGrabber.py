# -*- coding: utf-8 -*-
#!/usr/bin/env python

import serial
import numpy
import pickle
import datetime

"""
Write data from the LeCroy LC574AL oscilloscope over GPIB-USB to a file.

This program uses the Prologix GPIB-USB controller (prologix.biz) to communicate with the LeCroy LC574AL oscilloscope, collect the trace data from all of the input channels, and write it to a file that can be used from a python script. This program was written because of the unacceptably slow speed of data transfer via RS232. The scope of this program is very narrow: it is a drop-in replacement for manually collecting trace data from the scope over RS232 during the typical workflow of creating marks on a sample with the pulse generator. This program would typically be run at the end of a spectroscopy scan, after the STM image data has been saved and after the STOP button has been pressed on the scope.

Data is collected from all input channels, regardless of what (if anything) is plugged into them. The data is restructured and saved as a python pickle so that it is trivial to access it from a python program later on. Data from the oscilloscope is structured in a nested series of dictionaries and lists as follows: The root object is a python dictionary with two fields, "metadata" and "data". The "metadata" field contains a string that identifies the oscillosocpe. The "data" field contains a python list with entries corresponding to each segment the oscilloscope has recorded. Each entry in the "data" list is a dictionary with four fields: "C1", ..., "C4", and "time". All items in the dictionary are numpy arrays; the "time" array is the ordinate and the "C1", etc arrays are the abscissae. Times are recorded relative to the initial trigger event.

For example, I sometimes do a spectroscopy scan using a regular 4x4 array of spectroscopy points. Therefore there are 16 total spectroscopy locations, the coordinates of which are recorded in the SM4 file that XPMPro records. Each of these 16 pulses are recorded by the oscilloscope, and this program will put the data for each of them into the 16 elements of the "data" list. If I had done a regular 8x8 array spectroscopy scan, this program would create a "data" list 64 elements long, and so on. Assuming there is zero temporal offset on the scope, the first element of the "time" array in the first item of the "data" list would be 0.0000... Assuming there was a 0.25s gap betweeen the first pulse and the second, the first element of the "time" array in the second item of the "data" list would be 0.25000000..., and so on.

This program automatically saves the data to a file using the standard format: YYYYMMDD-HHMM_lc574al_<sample name>_<experimenter name>.dat
"""

# Some parameters that define the GPIB network topology.
scopeGPIBAddr = 5
sampleName = "jrs0076"
experimenterInitials = "jrs"

# Initialize the Prologix controller. For some reason I don't understand the timeout must be set to 0 for things to work.
prologix = serial.Serial("/dev/ttyUSB0", timeout=0)

# Configure the prologix box to be a CONTROLLER, set it to talk to the scope, and make sure the scope automatically responds after it has been addressed.
prologix.write("++mode 1\n")
prologix.write("++addr" + scopeGPIBAddr + "\n")
prologix.write("++auto 1\n")

# Grab identifying information about the scope.

# Get data from the various channels on the scope.

# Rearrange the data into an object.

# Write the data to a file.
now = datetime.datetime.now()
filename = "_".join([now.strftime("%Y%m%d-%H%M"), "ls574al", sampleName, experimenterName]) + ".dat"