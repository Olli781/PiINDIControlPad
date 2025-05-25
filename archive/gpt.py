import tkinter as tk
import pytz
from datetime import datetime
import socket
import PyIndi
import time
import numpy as np
from astropy.wcs import WCS
from astropy.io import fits
import sys
import threading
import os
import math
import logging
from pathlib import Path
import sqlite3
from astroquery.simbad import Simbad

# Logging einrichten
logging.basicConfig(
    filename='astrocontroller.log', 
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)

# Globale Konfigurationsvariablen
DEBUG = True
EXPOSURE_TIME = 5.0
TELESCOPE_NAME = "Telescope Simulator"
CCD_NAME = "CCD Simulator"
MAX_DEVIATION_ARCSEC = 30
LATITUDE = 49.8951
LONGITUDE = -97.1384
ALTITUDE = 300
UTC = pytz.utc
DB_PATH = Path("astro_data.db")

class IndiClient(PyIndi.BaseClient):
    def __init__(self):
        super(IndiClient, self).__init__()
        self.blob_event = threading.Event()

    def newBLOB(self, bp):
        self.blob_event.set()

    def newNumber(self, nd):
        # Hier kann man Statusupdates abfangen, z.B. Positionen
        # print(f"Number updated: {nd.name}")
        pass

    def newSwitch(self, sp):
        # Statusupdates für Schalter
        pass

    def newText(self, tp):
        pass

    def newMessage(self, device, message):
        logging.info(f"INDI Message from {device}: {message}")

class AstroController:
    def __init__(self):
        self.indiclient = IndiClient()
        self.telescope = None
        self.ccd = None
        self.solve_requested = False
        self.solve_ok = True
        self.currTour = 0
        self.objectDisplay = ""
        self.setup_indi()
        self.ip_address = self.get_ip_address()
        self.init_database()

    def setup_indi(self):
        self.indiclient.setServer("localhost", 7624)
        if not self.indiclient.connectServer():
            logging.error("INDI Server nicht erreichbar")
            sys.exit(1)

        self.telescope = self.connect_device(TELESCOPE_NAME, "CONNECTION")
        self.set_switch(self.telescope, "ON_COORD_SET", [1, 0, 0])

        self.ccd = self.connect_device(CCD_NAME, "CONNECTION")
        self.set_text(self.ccd, "ACTIVE_DEVICES", [TELESCOPE_NAME])
        self.indiclient.setBLOBMode(PyIndi.B_ALSO, CCD_NAME, "CCD1")

    def connect_device(self, name, connect_property):
        device = self.indiclient.getDevice(name)
        while not device:
            time.sleep(0.5)
            device = self.indiclient.getDevice(name)

        connection = device.getSwitch(connect_property)
        while not connection:
            time.sleep(0.5)
            connection = device.getSwitch(connect_property)

        if not device.isConnected():
            connection[0].s = PyIndi.ISS_ON
            connection[1].s = PyIndi.ISS_OFF
            self.indiclient.sendNewSwitch(connection)

        return device

    def set_switch(self, device, prop_name, values):
        prop = device.getSwitch(prop_name)
        while not prop:
            time.sleep(0.5)
            prop = device.getSwitch(prop_name)
        for i, val in enumerate(values):
            prop[i].s = PyIndi.ISS_ON if val else PyIndi.ISS_OFF
        self.indiclient.sendNewSwitch(prop)

    def set_text(self, device, prop_name, texts):
        prop = device.getText(prop_name)
        while not prop:
            time.sleep(0.5)
            prop = device.getText(prop_name)
        for i, text in enumerate(texts):
            prop[i].text = text
        self.indiclient.sendNewText(prop)

    def get_ip_address(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP

    def init_database(self):
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute('''CREATE TABLE IF NOT EXISTS observations (
                id INTEGER PRIMARY KEY,
                timestamp TEXT,
                ra REAL,
                dec REAL,
                solved INTEGER
            )''')
            conn.commit()

    def save_observation(self, ra, dec, solved):
        with sqlite3.connect(DB_PATH) as conn:
            c = conn.cursor()
            c.execute("INSERT INTO observations (timestamp, ra, dec, solved) VALUES (?, ?, ?, ?)",
                      (datetime.utcnow().isoformat(), ra, dec, int(solved)))
            conn.commit()

    def capture_and_solve(self):
        exposure = self.ccd.getNumber("CCD_EXPOSURE")
        if exposure is None:
            logging.error("CCD_EXPOSURE nicht verfügbar")
            return None

        exposure[0].value = EXPOSURE_TIME
        self.indiclient.sendNewNumber(exposure)

        self.indiclient.blob_event.clear()
        self.indiclient.blob_event.wait()
        blob_vector = self.ccd.getBLOB("CCD1")
        if not blob_vector or not blob_vector[0].getblobdata():
            logging.error("Kein BLOB-Datenempfang")
            return None

        image_blob = blob_vector[0].getblobdata()

        with open("solve.fits", "wb") as f:
            f.write(image_blob)

        os.system("rm -f solve.ini solve.wcs")
        os.system("/usr/local/bin/astap -r 50 -f solve.fits > solve.err 2>&1")

        timeout = 0
        while not os.path.exists("solve.wcs") and timeout < 10:
            time.sleep(1)
            timeout += 1

        if not os.path.exists("solve.wcs"):
            logging.warning("Plate Solve fehlgeschlagen")
            self.save_observation(None, None, False)
            return None

        try:
            with fits.open("solve.wcs") as hdul:
                w = WCS(hdul[0].header)
                ra, dec = w.wcs.crval
                self.save_observation(ra, dec, True)
                return ra, dec
        except Exception as e:
            logging.error(f"WCS Fehler: {e}")
            return None

    def update_position(self, ra, dec):
        coords = self.telescope.getNumber("EQUATORIAL_EOD_COORD")
        coords[0].value = ra
        coords[1].value = dec
        self.indiclient.sendNewNumber(coords)

    def goto_object(self, object_name):
        try:
            object_name = object_name.strip().upper().replace("  ", " ")
            if object_name.startswith("M ") == False and object_name.startswith("M"):
                object_name = object_name.replace("M", "M ", 1)
            elif object_name.startswith("NGC ") == False and object_name.startswith("NGC"):
                object_name = object_name.replace("NGC", "NGC ", 1)
            elif object_name.startswith("IC ") == False and object_name.startswith("IC"):
                object_name = object_name.replace("IC", "IC ", 1)

            result = Simbad.query_object(object_name)
            if result is None:
                logging.warning(f"Objekt '{object_name}' nicht gefunden")
                self.objectDisplay = f"Nicht gefunden: {object_name}"
                return
            ra_str = result['RA'][0]
            dec_str = result['DEC'][0]
            ra = self.hms_to_degrees(ra_str)
            dec = self.dms_to_degrees(dec_str)
            self.update_position(ra, dec)
            self.objectDisplay = f"Goto {object_name}"
            logging.info(f"Goto {object_name}: RA={ra}, DEC={dec}")
        except Exception as e:
            logging.error(f"Fehler bei Goto {object_name}: {e}")
            self.objectDisplay = f"Fehler: {object_name}"

    def hms_to_degrees(self, hms):
        h, m, s = [float(part) for part in hms.split()]
        return 15 * (h + m/60 + s/3600)

    def dms_to_degrees(self, dms):
        parts = dms.split()
        sign = -1 if parts[0].startswith('-') else 1
        d = abs(float(parts[0]))
        m = float(parts[1])
        s = float(parts[2])
        return sign * (d + m/60 + s/3600)

    def synchronize_position(self):
        coords = self.telescope.getNumber("EQUATORIAL_EOD_COORD")
        if coords:
            ra = coords[0].value
            dec = coords[1].value
            self.objectDisplay = f"Synchronized RA: {ra:.5f} DEC: {dec:.5f}"
        else:
            self.objectDisplay = "Synchronisierung fehlgeschlagen"
        logging.info(f"Position synchronisiert: RA={ra}, DEC={dec}")

# GUI mit Steuerbuttons
if __name__ == "__main__":
    controller = AstroController()

    root = tk.Tk()
    root.title("AstroController GUI")
    root.geometry("600x400")

    def update_display():
        label_display.config(text=controller.objectDisplay)
        root.update()

    def add_digit(d):
        controller.objectDisplay += d
        update_display()

    def clear():
        controller.objectDisplay = ""
        update_display()

    def solve():
        controller.objectDisplay = f"Solved: {controller.objectDisplay}"
        update_display()

    def goto():
        object_name = controller.objectDisplay.strip()
        controller.goto_object(object_name)
        update_display()

    def prev():
        controller.currTour = max(0, controller.currTour - 1)
        controller.objectDisplay = f"TOUR {controller.currTour}"
        update_display()

    def next_():
        controller.currTour += 1
        controller.objectDisplay = f"TOUR {controller.currTour}"
        update_display()

    def synchronize():
        controller.synchronize_position()
        update_display()

    label_display = tk.Label(root, text="", font='verdana 20', bg='black', fg='white')
    label_display.grid(row=0, column=0, columnspan=5, sticky="nsew")

    buttons = [
        ('1', lambda: add_digit('1')), ('2', lambda: add_digit('2')), ('3', lambda: add_digit('3')),
        ('4', lambda: add_digit('4')), ('5', lambda: add_digit('5')), ('6', lambda: add_digit('6')),
        ('7', lambda: add_digit('7')), ('8', lambda: add_digit('8')), ('9', lambda: add_digit('9')),
        ('Messier', lambda: add_digit('M ')), ('0', lambda: add_digit('0')), ('NGC', lambda: add_digit('NGC')),
        ('IC', lambda: add_digit('IC')), ('Solve', solve), ('Goto', goto), ('Clear', clear)
    ]

    row = 1
    col = 0
    for (text, cmd) in buttons:
        b = tk.Button(root, text=text, command=cmd, fg='red', bg='black', padx=2,
                     highlightbackground='red', highlightthickness=2,
                     highlightcolor="black", font='verdana 18')
        b.grid(row=row, column=col, sticky="nsew")
        col += 1
        if col > 2:
            col = 0
            row += 1

    tk.Button(root, text="Prev", command=prev, font='verdana 18', bg='gray20', fg='white').grid(row=row, column=0, sticky="nsew")
    tk.Button(root, text="Next", command=next_, font='verdana 18', bg='gray20', fg='white').grid(row=row, column=1, sticky="nsew")
    tk.Button(root, text="Synchronisieren", command=synchronize, font='verdana 18', bg='green', fg='white').grid(row=row, column=2, sticky="nsew")

    for i in range(5):
        root.columnconfigure(i, weight=1)
    for i in range(row+1):
        root.rowconfigure(i, weight=1)

    root.mainloop()
