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

class AstroController:
    def __init__(self):
        self.indiclient = IndiClient()
        self.telescope = None
        self.ccd = None
        self.solve_requested = False
        self.solve_ok = True
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
        exposure[0].value = EXPOSURE_TIME
        self.indiclient.sendNewNumber(exposure)

        self.indiclient.blob_event.clear()
        self.indiclient.blob_event.wait()
        image_blob = self.ccd.getBLOB("CCD1")[0].getblobdata()

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

class AstroGUI:
    def __init__(self, controller):
        self.controller = controller
        self.root = tk.Tk()
        self.root.title("AstroControl")
        self.root.configure(bg='black')
        self.root.geometry("400x600")
        self.build_ui()
        self.update_ui()
        self.root.mainloop()

    def build_ui(self):
        for x in range(3):
            tk.Grid.columnconfigure(self.root, x, weight=1)
        for y in range(6):
            tk.Grid.rowconfigure(self.root, y, weight=1)

        self.label_localtime = tk.Label(self.root, font='verdana 14', fg='red', bg='black')
        self.label_localtime.grid(row=0, column=0, sticky="w", columnspan=2)

        self.label_status = tk.Label(self.root, text=self.controller.ip_address, font='verdana 14', fg='red', bg='black')
        self.label_status.grid(row=0, column=2, sticky="e")

        tk.Button(self.root, text="Solve On", command=self.solve_on, font='verdana 24',
                  fg='red', bg='black', highlightbackground='red', highlightthickness=2).grid(row=1, column=1, sticky="nsew")
        tk.Button(self.root, text="Solve Off", command=self.solve_off, font='verdana 24',
                  fg='red', bg='black', highlightbackground='red', highlightthickness=2).grid(row=2, column=1, sticky="nsew")
        tk.Button(self.root, text="Sync", command=self.sync, font='verdana 24',
                  fg='red', bg='black', highlightbackground='red', highlightthickness=2).grid(row=3, column=1, sticky="nsew")

        self.label_utctime = tk.Label(self.root, font='verdana 14', fg='red', bg='black')
        self.label_utctime.grid(row=4, column=0, columnspan=2, sticky="nsew")
        self.label_ip = tk.Label(self.root, text=self.controller.ip_address, font='verdana 14', fg='red', bg='black')
        self.label_ip.grid(row=4, column=2, sticky="nsew")

        tk.Button(self.root, text="Show Log", command=self.show_log, font='verdana 14',
                  fg='red', bg='black', highlightbackground='red').grid(row=5, column=1, sticky="nsew")

    def update_ui(self):
        now = datetime.now()
        self.label_localtime.config(text=now.strftime("%d-%b-%Y\n%H:%M:%S"))
        utc_now = datetime.now(tz=UTC)
        self.label_utctime.config(text=utc_now.strftime("%d-%b-%Y\n%H:%M:%S UT"))
        self.root.after(1000, self.update_ui)

    def solve_on(self):
        self.controller.solve_requested = True
        self.label_status.config(text="Solving...")
        coords = self.controller.capture_and_solve()
        if coords:
            ra, dec = coords
            self.controller.update_position(ra, dec)
            self.label_status.config(text="Tracking")
        else:
            self.label_status.config(text="Solve Failed")

    def solve_off(self):
        self.controller.solve_requested = False
        self.label_status.config(text="Solve Disabled")

    def sync(self):
        # Beispiel Sync Funktion
        self.label_status.config(text="Syncing...")
        coords = self.controller.capture_and_solve()
        if coords:
            ra, dec = coords
            self.controller.update_position(ra, dec)
            self.label_status.config(text="Synced")
        else:
            self.label_status.config(text="Sync Failed")

    def show_log(self):
        os.system("xdg-open astrocontroller.log")

if __name__ == "__main__":
    controller = AstroController()
    AstroGUI(controller)
