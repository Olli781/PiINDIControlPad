import tkinter as tk
import pytz
from datetime import datetime
import socket
import PyIndi
import time
import numpy as np
from astropy import wcs
from astropy.wcs import WCS
from astropy.table import Table
from astropy.io import fits
from astropy.coordinates import EarthLocation,SkyCoord
from astropy.time import Time
from astropy import units as u
from astropy.coordinates import AltAz
import photutils
import sys
import threading
import os
import subprocess as subp
import math
import mysql.connector
from mysql.connector import Error
from mysql.connector import errorcode
from datetime import datetime
from tzlocal import get_localzone

#######################################################################################
#### V A R I A B L E S ################################################################
#######################################################################################     
debug=1
exposure=5.0
telescope="Telescope Simulator"
device_telescope=None
telescope_connect=None
ccd="CCD Simulator"
solveOk=0
maxDeviation = 30                    	# In ArcSecs
utc = pytz.utc
currLat = 49.8951
currLong= -97.1384
currAlt=300
minAlt=15                            	# Minimum altitude to slew to
currTour=0				# Current tour we're working on
objectDisplay = ""
   
#######################################################################################
#### F U N C T I O N S ################################################################
#######################################################################################
# Mkhrs takes a time float number in and returns a formatted string as HH:MM:SS
def mkhrs(time):
  hours = int(time)
  minutes = (time*60) % 60
  seconds = (time*3600) % 60
  outstring = "%d:%02d:%02d" % (hours, minutes, seconds)
  return outstring

# Object Display functions ###########################################################
objectDisplay="Unknown"

# prevObject reads a line from a tour.txt file and slews the telescope to that object
def prevObject():
    # to come
    return
    
# nextObject reads a line from a tour.txt file and slews the telescope to that object
def nextObject():
    # to come
    return

def messierObject():
    global objectDisplay
    objectDisplay="Messier "
    return 

def ngcObject():
    global objectDisplay
    objectDisplay="NGC "
    return

def caldwellObject():
    global objectDisplay
    objectDisplay="Caldwell "
    return 

def clearObject():
    global objectDisplay
    objectDisplay=""
    return 
    
def oneEntry():
    global objectDisplay
    objectDisplay=objectDisplay+"1"
    return     

def twoEntry():
    global objectDisplay
    objectDisplay=objectDisplay+"2"
    return 

def threeEntry():
    global objectDisplay
    objectDisplay=objectDisplay+"3"
    return 
    
def fourEntry():
    global objectDisplay
    objectDisplay=objectDisplay+"4"
    return 
    
def fiveEntry():
    global objectDisplay
    objectDisplay=objectDisplay+"5"
    return 
    
def sixEntry():
    global objectDisplay
    objectDisplay=objectDisplay+"6"
    return 
    
def sevenEntry():
    global objectDisplay
    objectDisplay=objectDisplay+"7"
    return 
def eightEntry():
    global objectDisplay
    objectDisplay=objectDisplay+"8"
    return 
def nineEntry():
    global objectDisplay
    objectDisplay=objectDisplay+"9"
    return 
def zeroEntry():
    global objectDisplay
    objectDisplay=objectDisplay+"0"
    return 

def solveEntry():
    os.system("touch solve.requested")
    return 
    
def gotoEntry():
	global objectDisplay
	global currTour
	
	if objectDisplay[0:5]=="TOUR ":
		# Load the first entry in the indicated tour
		sql_select_Query = "select * from tours where name='"+objectDisplay+"'"
		if debug:
			print(sql_select_Query)
		cursor = connection.cursor(buffered=True)
		cursor.execute(sql_select_Query)
		if (cursor.rowcount == 0):
			print("No result in SQL :",sql_select_Query)
			currStatusText.configure(text="TOUR NOT FOUND")
			root.update()
			time.sleep(2)
			return
		row = cursor.fetchone()
		objectDisplay=row[1]
		# Carry on loading and slewing to object
	try:
		sql_select_Query = "select * from objects where name='"+objectDisplay+"'"
		if debug:
			print(sql_select_Query)
			
		cursor = connection.cursor(buffered=True)
		cursor.execute(sql_select_Query)
		if (cursor.rowcount == 0):
			print("No result in SQL :",sql_select_Query)
			currStatusText.configure(text="OBJECT NOT FOUND")
			root.update()
			time.sleep(2)
			return
		row = cursor.fetchone()
	except Error as e:
		print("Error reading data from MySQL table", e)
    
	if debug:
		print("Retrieved ",row[0]," with RA",row[1],"and Dec",row[2])
		
	if (checkAlt(row[1],row[2])): 
		# Slew the telescope
		telescope_radec=device_telescope.getNumber("EQUATORIAL_EOD_COORD")
		while not(telescope_radec):
			time.sleep(0.5)
		telescope_radec=device_telescope.getNumber("EQUATORIAL_EOD_COORD")
		telescope_radec[0].value=row[1]
		telescope_radec[1].value=row[2]
		indiclient.sendNewNumber(telescope_radec)
	else:
		print("Object too low to slew to!")
	
	return

def checkAlt(ra,dec):
	# Determine if the object's altitude is within limits
	observing_location = EarthLocation(lat=currLat*u.deg, lon=currLong*u.deg, height=currAlt*u.m) 
	tz = get_localzone() # local timezone 
	observing_time = datetime.now(tz) 
	
	if debug:
		print("Location is ",observing_location)
		print("Time is ",observing_time)
	alt_az_frame = AltAz(location=observing_location, obstime=observing_time)
	target = SkyCoord(ra*u.hour,dec*u.deg,frame="icrs")
	target_alt_az = target.transform_to(alt_az_frame)
	
	if debug:
      		print("AltAz is ",target_alt_az.alt, target_alt_az.az)

	if (target_alt_az.alt.degree > minAlt):
		return(True)
	else:
		# Update the status
		currStatusText.configure(text="OBJECT TOO LOW")
		root.update()
		time.sleep(2)
		return(False)

    	           
def tourEntry():
    global objectDisplay
    objectDisplay="TOUR "
    return 

def stop():
    global objectDisplay
    objectDisplay="STOP"
    return 


def updateObjectDisplay():
    currObjText.configure(text=objectDisplay)
    root.update()

def oneEntry():
    global objectDisplay
    objectDisplay += "1"
    updateObjectDisplay()



#######################################################################################
#### M Y S Q L ########################################################################
####################################################################################### 
try:
    connection = mysql.connector.connect(host='localhost',
                                         database='ntt',
                                         user='ntt',
                                         password='Jvm123ed!')

except Error as e:
    print("Unable to connect to MYSQL", e)



#######################################################################################
#### I N D I ##########################################################################
#######################################################################################  
# Connect to INDI and set up devices
class IndiClient(PyIndi.BaseClient):
    def __init__(self):
        super(IndiClient, self).__init__()
    def updateProperty(self, prop):
        global blobEvent
        if prop.getType() == PyIndi.INDI_BLOB:
            print("new BLOB ", prop.getName())
            blobEvent.set()
    def newDevice(self, d):
        pass
    def newProperty(self, p):
        pass
    def removeProperty(self, p):
        pass
    def newBLOB(self, bp):
        global blobEvent
        blobEvent.set()
        pass
    def newSwitch(self, svp):
        pass
    def newNumber(self, nvp):
        pass
    def newText(self, tvp):
        pass
    def newLight(self, lvp):
        pass
    def newMessage(self, d, m):
        pass
    def serverConnected(self):
        pass
    def serverDisconnected(self, code):
        pass

indiclient=IndiClient()
indiclient.setServer("localhost",7624)

if not indiclient.connectServer():
    print(
        "No indiserver running on "
        + indiclient.getHost()
        + ":"
        + str(indiclient.getPort())
        + " - Try to run"
    )
    print("  indiserver indi_simulator_telescope indi_simulator_ccd")
    sys.exit(1)

# connect the scope
telescope = "Telescope Simulator"
device_telescope = None
telescope_connect = None

# get the telescope device
device_telescope = indiclient.getDevice(telescope)
while not device_telescope:
    time.sleep(0.5)
    device_telescope = indiclient.getDevice(telescope)

# wait CONNECTION property be defined for telescope
telescope_connect = device_telescope.getSwitch("CONNECTION")
while not telescope_connect:
    time.sleep(0.5)
    telescope_connect = device_telescope.getSwitch("CONNECTION")

# if the telescope device is not connected, we do connect it
if not device_telescope.isConnected():
    # Property vectors are mapped to iterable Python objects
    # Hence we can access each element of the vector using Python indexing
    # each element of the "CONNECTION" vector is a ISwitch
    telescope_connect.reset()
    telescope_connect[0].setState(PyIndi.ISS_ON)  # the "CONNECT" switch
    indiclient.sendNewProperty(telescope_connect)  # send this new value to the device

# We want to set the ON_COORD_SET switch to engage tracking after goto
# device.getSwitch is a helper to retrieve a property vector
telescope_on_coord_set=device_telescope.getSwitch("ON_COORD_SET")
while not(telescope_on_coord_set):
    time.sleep(0.5)
    telescope_on_coord_set=device_telescope.getSwitch("ON_COORD_SET")

# the order below is defined in the property vector
telescope_on_coord_set[0].setState(PyIndi.ISS_ON)  # TRACK
telescope_on_coord_set[1].setState(PyIndi.ISS_OFF) # SLEW
telescope_on_coord_set[2].setState(PyIndi.ISS_OFF) # SYNC
indiclient.sendNewSwitch(telescope_on_coord_set)

# Set up CCD camera 
device_ccd=indiclient.getDevice(ccd)
while not(device_ccd):
    time.sleep(0.5)
    device_ccd=indiclient.getDevice(ccd)   
 
ccd_connect=device_ccd.getSwitch("CONNECTION")
while not(ccd_connect):
    time.sleep(0.5)
    ccd_connect=device_ccd.getSwitch("CONNECTION")
if not(device_ccd.isConnected()):
    ccd_connect[0].setState(PyIndi.ISS_ON)  # the "CONNECT" switch
    ccd_connect[1].setState(PyIndi.ISS_OFF) # the "DISCONNECT" switch
    indiclient.sendNewSwitch(ccd_connect)
 
ccd_exposure=device_ccd.getNumber("CCD_EXPOSURE")
while not(ccd_exposure):
    time.sleep(0.5)
    ccd_exposure=device_ccd.getNumber("CCD_EXPOSURE")
 
# Ensure the CCD driver snoops the telescope driver
ccd_active_devices=device_ccd.getText("ACTIVE_DEVICES")
while not(ccd_active_devices):
    time.sleep(0.5)
    ccd_active_devices=device_ccd.getText("ACTIVE_DEVICES")
ccd_active_devices[0].text=telescope
indiclient.sendNewText(ccd_active_devices)
 
# we should inform the indi server that we want to receive the
# "CCD1" blob from this device
indiclient.setBLOBMode(PyIndi.B_ALSO, ccd, "CCD1")
ccd_ccd1=device_ccd.getBLOB("CCD1")
while not(ccd_ccd1):
    time.sleep(0.5)
    ccd_ccd1=device_ccd.getBLOB("CCD1")

##### Determine our IP address ##########################################################
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
try:
  # doesn't even have to be reachable
  s.connect(('10.255.255.255', 1))
  IP = s.getsockname()[0]
except:
  IP = '127.0.0.1'
finally:
  s.close()

#######################################################################################
#### T K I N T E R ####################################################################
#######################################################################################  
root=tk.Tk()
root.configure(background='black')
# Uncomment this line to get fullscreen (a pain when debugging on a PC!)
#root.wm_attributes('-fullscreen','true')
root.geometry("1024x600")
for x in range(5):
    tk.Grid.columnconfigure(root, x, weight=1)
for y in range(11):
    tk.Grid.rowconfigure(root, y, weight=1)

# Anzeige
currObjText = tk.Label(root, text=objectDisplay, font='verdana 20', bg='black', fg='white')
currObjText.grid(row=0, column=0, columnspan=5, sticky="nsew")

# Buttons
buttons = [
    ('1', oneEntry), ('2', twoEntry), ('3', threeEntry),
    ('4', fourEntry), ('5', fiveEntry), ('6', sixEntry),
    ('7', sevenEntry), ('8', eightEntry), ('9', nineEntry),
    ('Solve', solveEntry), ('0', zeroEntry), ('Goto', gotoEntry),
    ('Clear', clearObject)
]

row = 1
col = 0

for (text, cmd) in buttons:
    b = tk.Button(root, text=text, command=cmd,
                  fg='red', bg='black', padx=2,
                  highlightbackground='red', highlightthickness=2,
                  highlightcolor="black", font='verdana 24')
    b.grid(row=row, column=col, sticky="nsew")
    col += 1
    if col > 2:
        col = 0
        row += 1

# Prev und Next Buttons
prevButton = tk.Button(root, text="Prev", command=prevEntry,
                       fg='red', bg='black', padx=2,
                       highlightbackground='red', highlightthickness=2,
                       highlightcolor="black", font='verdana 24')
prevButton.grid(row=5, column=0, columnspan=2, sticky="nsew")

nextButton = tk.Button(root, text="Next", command=nextEntry,
                       fg='red', bg='black', padx=2,
                       highlightbackground='red', highlightthickness=2,
                       highlightcolor="black", font='verdana 24')
nextButton.grid(row=5, column=2, columnspan=2, sticky="nsew")

# Spalten-/Zeilenkonfiguration für gleichmäßige Verteilung
for i in range(5):
    root.columnconfigure(i, weight=1)
for i in range(6):
    root.rowconfigure(i, weight=1)


#######################################################################################
#### M A I N L I N E ##################################################################
#######################################################################################  
solveOk = True

while (1):        # Loop forever
    # Update coordinates 
    telescope_radec=device_telescope.getNumber("EQUATORIAL_EOD_COORD")
    while not(telescope_radec):
        time.sleep(0.5)
        telescope_radec=device_telescope.getNumber("EQUATORIAL_EOD_COORD")   
        
    # Update Display
    dateTimeObj = datetime.now()
    currDateText.configure(text=dateTimeObj.strftime("%d-%b-%Y\n%H:%M:%S"))
    dateTimeObj = datetime.now(tz=utc)
    currUTDateText.configure(text=dateTimeObj.strftime("%d-%b-%Y\n%H:%M:%S UT"))
    currObjText.configure(text=objectDisplay)
    root.update_idletasks()
    root.update()
    
    # See if we are slewing or do we need a solve?
    if (telescope_radec.getState()==PyIndi.IPS_BUSY):
        currStatusText.configure(text="SLEWING")
        root.update()
        solveOk=False  # We'll need to do a solve after the motion stops
    else:
        # Update the status
        currStatusText.configure(text="TRACKING")
        root.update()
        
        # See if User wants a solve by creating a solve.requested file
        if os.path.exists('solve.requested'):
            os.remove('solve.requested')
            solveOk = False

        # Otherwise if we're good, don't continue on to solve
        if solveOk:
            continue
 
        # Run the solve program 
        # Update display
        currStatusText.configure(text="SOLVING")
        root.update()
            
        # Initiate an image on the camera
        blobEvent=threading.Event()
        blobEvent.clear()
        ccd_exposure[0].value=exposure
        indiclient.sendNewNumber(ccd_exposure)
        blobEvent.wait()
        blobEvent.clear()
        if debug:
            print("name: ", ccd_ccd1[0].name," size: ", ccd_ccd1[0].size," format: ", ccd_ccd1[0].format)
        ccdimage=ccd_ccd1[0].getblobdata()

        # Write the image to disk - disabled because astap won't solve ccd simulator images
#        filehandle = open('solve.fits', 'wb')
#        filehandle.write(ccdimage)
#        filehandle.close()

        # Remove plate solve results
        if os.path.exists('solve.ini'):
           os.remove('solve.ini')
        if os.path.exists('solve.wcs'):
           os.remove('solve.wcs')

        # Do a plate solve on the fits data
        cmd="/usr/local/bin/astap -r 50 -f solve.fits >solve.err 2>&1"
        if (debug): 
            print("Solving...")
            print(cmd)
        # Create a process to call the solver and wait for completion 
        timeout=0 
        os.system(cmd)
        while not os.path.exists('solve.wcs'):
            if debug:
                print ("Sleeping...")
            time.sleep(0.5)
            timeout=timeout+0.5
            if (timeout==10):
                print ("Error, solve not completed in 10s!")
                continue;
                

        # Load the wcs FITS hdulist using astropy.io.fits
        #with fits.open('solve.wcs', mode='readonly', ignore_missing_end=True) as fitsfile:
        #    w = WCS(fitsfile[0].header) 
        #    solveRa=w.wcs.crval[0]
        #    solveDec=w.wcs.crval[1]
        # Kludge because wcs file keeps bombing with corrupt file error, doh!
        os.system("cat solve.wcs | grep CRVAL1 | cut -b12-30 > solve.kludge")
        os.system("cat solve.wcs | grep CRVAL2 | cut -b12-30 >> solve.kludge")
        kludgefile=open("solve.kludge","r")
        rastr=kludgefile.read(19)
        decstr=kludgefile.read(1) # ignore the CR 
        decstr=kludgefile.read(19)
        if debug:
            print("Kludge coords: ",rastr," ",decstr)
        kludgefile.close()
        solveRa=float(rastr)
        solveDec=float(decstr)
        
        if (debug): 
            print("Solved RA= ",solveRa," Dec=",solveDec)

        # Load the ccd image FITS hdulist using astropy.io.fits
        with fits.open('solve.fits', mode='readonly', ignore_missing_end=True) as fitsfile:
            w = WCS(fitsfile[0].header) 
            ccdRa=w.wcs.crval[0]
            ccdDec=w.wcs.crval[1]
        if (debug): 
           print("CCD RA= ",solveRa," Dec=",solveDec)
            
        # Compare the plate solve to the current RA/DEC, convert to arcsecs
        deltaRa = (solveRa - ccdRa)*60*60 
        deltaDec = (solveDec - ccdDec)*60*60
        if (debug): 
           print("Delta RA= ",deltaRa," Delta Dec=",deltaDec)
        
        # If within the threshold arcsecs move the scope set solveOk and continue
        if ((deltaRa < 5) or (deltaDec < 5)):
            if debug:
                print("Deviation < 25 arcsecs, ignoring")
            solveOk=True
            continue;
        if debug:
            print("Deviation ",math.sqrt(deltaRa**2+deltaDec**2),"arcsecs compared to max ",maxDeviation," arcsecs")
        if math.sqrt(deltaRa**2+deltaDec**2) > maxDeviation:
           if debug:
               print("Moving scope to computed coordinates ",ccdRa+deltaRa," ",ccdDec+deltaDec)
           # Otherwise set the desired coordinate and slew
           telescope_radec=device_telescope.getNumber("EQUATORIAL_EOD_COORD")
           while not(telescope_radec):
               time.sleep(0.5)
           telescope_radec=device_telescope.getNumber("EQUATORIAL_EOD_COORD")
           telescope_radec[0].value=ccdRa+deltaRa
           telescope_radec[1].value=ccdDec+deltaDec
           indiclient.sendNewNumber(telescope_radec)
        else:
           solveOk=True



# ************************ ENDS *****************************


