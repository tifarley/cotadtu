## Cota Desktop Transmitter Utility (DTU)
Cota DTU is a Python application for controlling Ossia Inc's Cota Wireless Power Transmitters.

Cota DTU uses the Tkinter GUI library that is included in most Python distributions and requires Python 3.7+. The repository contains a requirements.txt that lists all other dependencies that must be installed. It is recommended to create a Python virtual environment to install the dependencies and run the DTU. An example is shown below.

### Installing dependencies
*Create a virtual environment in the myvenv/ directory:*

`python3 -m venv myvenv`

*Activate the virtual environment:*

*Linux:*

`source myvenv/bin/activate`

*Windows:*

`myvenv/bin/activate.bat`

*Install the required packages:*

`(myvenv) pip install -r requirements.txt`

*Start Cota DTU:*

`(myvenv) python CotaDTU.py`

### GUI Design
A separate application called PAGE is used to configure and place all of the GUI elements through a drag and drop interface. PAGE can be installed from [http://page.sourceforge.net/](http://page.sourceforge.net/) and the documentation can be found [here](http://page.sourceforge.net/html/index.html)

## Code layout