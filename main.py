#!/usr/bin/env python3

# Stele Steuerung Version 3
from tkinter import *
from tkinter import font as font
import socket
# from socket import *
from pythonosc import udp_client
from pythonosc import osc_bundle_builder, osc_message_builder
from pythonosc import dispatcher, osc_server

from get_wlan0IP import get_wlan0ip as get_ip

from omxplayer.player import OMXPlayer

import pyglet

import threading

import platform

import pickle
from time import sleep as sleep

from typing import List, Any

from PIL import Image
from PIL import ImageTk

import os
import sys
import stat
import subprocess
from pynput.keyboard import Key, Controller
from pynput.mouse import Controller as Mouse

# TODO Variable first_time_video_played entfernen, wird nicht genutzt

# GPIO Setups Part 1
print("Running on {}".format(platform.system()), flush=True)
if platform.system() != "Windows":
    import RPi.GPIO as GPIO

    pin_people_going = 26  # Person OUT
    pin_people_comming = 23  # Person IN

    pin_buzzer = 31  # Buzzer pin

    GPIO.setmode(GPIO.BOARD)

# Konfigs

small_window = False  # Zeige die Gui in einem nicht bildfüllendem Format, zum Debuggen hilfreich

# Einrichtung Font
font_file = "/home/pi/PeopleCounter_V3/otherfont.otf"  # Font zum anzeigen der sChrift
pyglet.font.add_file(font_file)
myfont = pyglet.font.load('adineue PRO Bold')

# First Variables definition

max_people_allowed = 0  # Maximale Anzahl drinnen befiindlicher Personen
people_inside = 0  # Momentane Anzahl der drinnen befindlichen Personen

index_video = 0  # Index des Angeteigten Videos
file_list = []  # Gefundene Video dateien
server = []  # Platzhalter für OSC Server

checked_in_ips = []  # Sammelstelle der IPs/Devices ,welche Nachrichten an den Master schicken
first_time_video_played = True  # Wird zum ersten Mal ein Video abgespielt ?

video_player = []  # Platzhalter für OMXPlayer

keyboard = Controller()  # ??
mouse = Mouse()  # Maus-Kontorller um Maus vom Bildschirm zu schieben
mouse.position = (10000, 10000)  # Masu aus den Bildschirm schieben
root = Tk()  # TK root
local_ip = None  # Platzhalter für eigene IP des Gerätes
is_master_modus = False  # Default für Master

# Ermitterlung der eigenen IP im Wifi Netzwerk, , an der IP wird Master/Slave Stauts ermittelt. 192.168.4.1
# -> Master, alle weiteren IP -> Slave
while local_ip is None:
    try:
        local_ip = get_ip()
        if local_ip == '192.168.4.1':
            is_master_modus = True

    except:
        print("Waiting for Network to be online")
        pass


if not small_window:
    root.attributes('-fullscreen', True)
    # root.geometry("1090x1930")

# Bilder werden geladen im Hintergrund
if platform.system() != "Windows":
    background_go = PhotoImage(file="/home/pi/PeopleCounter_V3/Go.png") # Hintergrund, wenn Leute rein düfen -> Branding möglich
    background_stop = PhotoImage(file="/home/pi/PeopleCounter_V3/Stop.png") # Stop Anzeige, nach möglichkeit gleich

    # Master Slave Symbol auf Größe bringen
    width = 100
    height = 100
    img = Image.open("/home/pi/PeopleCounter_V3/Slave.png")
    img = img.resize((width, height), Image.ANTIALIAS)
    slave_img = ImageTk.PhotoImage(img)
    img = Image.open("/home/pi/PeopleCounter_V3/Master.png")
    img = img.resize((width, height), Image.ANTIALIAS)
    master_img = ImageTk.PhotoImage(img)

# Logo unter dem Video
    width = int((1920 - 1312) * .9)
    height = width
    img = Image.open("/home/pi/PeopleCounter_V3/Logo.png")
    img = img.resize((width, height), Image.ANTIALIAS)
    logo = ImageTk.PhotoImage(img)
    # logo = PhotoImage(img)
else:
    background_go = PhotoImage(file="Go.png")
    background_stop = PhotoImage(file="Stop.png")


# Anfang Funktionen Definition
def load_last_file():  # Laed den letzten Stand der Perseonen Counter
    try:
        with open("/home/pi/PeopleCounter_V3/reset/save.pkl", "rb") as f:
            maximum, inside = pickle.load(f)
            if maximum is None:
                maximum = 20
            if inside is None:
                inside = 0
    except:  # Falls kein save vorhanden setzte auf Defaultwerte
        maximum = 20
        inside = 0
    return maximum, inside


def save_last_file(maximum, inside):  # Speicher Anzahl in reset/save.pkl
    print("Starte Speichern")
    with open("/home/pi/PeopleCounter_V3/reset/save.pkl", "wb+") as f:
        pickle.dump([maximum, inside], f)
    print("Ende Speichern")


def inside_plus():  # Erhoehe Inside Counter um Eins und speichere Anzahl
    global people_inside
    if people_inside < 1100:
        people_inside = people_inside + 1
    save_last_file(max_people_allowed, people_inside)
    root.after(1, update_the_screen)
    if not is_master_modus:  # Falls Stele im Slave-Modus, sende an Master
        t = threading.Thread(target=send_inside_plus_to_master)
        t.start()


def inside_minus():     # Erniedrige Inside Counter um Eins und speichere neue Anzahl
    global people_inside
    print("Inside ein absziehen")
    if people_inside > 0:   # Es kann keine negative Anzahl an Personen im Laden sein
        people_inside = people_inside - 1
    save_last_file(max_people_allowed, people_inside)
    root.after(1, update_the_screen)
    if not is_master_modus:  # Falls Stele im Slave-Modus, sende an Master
        t = threading.Thread(target=send_inside_minus_to_master)
        t.start()


def set_inside(i):  # Setze Inside Counter auf Anzahl und speichere
    global people_inside
    people_inside = i
    save_last_file(max_people_allowed, people_inside)
    root.after(1, update_the_screen)


def maximum_plus():  # Erhoehe Maximal Counter um Eins und speichere Anzahl
    global max_people_allowed
    # TODO: maximal 1000 noetig ??
    if max_people_allowed < 1000:  # Maximal 1000 Leute
        max_people_allowed = max_people_allowed + 1
    save_last_file(max_people_allowed, people_inside)
    root.after(1, update_the_screen)
    if not is_master_modus:  # Falls Stele im Slave-Modus, sende an Master
        t = threading.Thread(target=send_max_plus_to_master)
        t.start()


def maximum_minus():  # Erniedrige Maximal Counter um Eins und speichere neue Anzahl
    global max_people_allowed
    if max_people_allowed > 0:  # Maximale Anzahl Personen kann nicht negativ sein
        max_people_allowed = max_people_allowed - 1
    save_last_file(max_people_allowed, people_inside)
    root.after(1, update_the_screen)
    if not is_master_modus:     # Falls Stele im Slave-Modus, sende an Master
        t = threading.Thread(target=send_max_minus_to_master)
        t.start()


def set_maximum(i):     # Setze Maximal Counter auf Anzahl und speichere
    global max_people_allowed
    max_people_allowed = i
    save_last_file(max_people_allowed, people_inside)
    root.after(1, update_the_screen)


def set_maximum_and_inside(m, i):   # Setzte Inside und Maximal Counter gleichzeitig, benoetigt von Stele im Slave-Modus
    #   um die Antwort des Masters zu verarbeiten. Insbesondere weil sont der "Counter zitter"
    global max_people_allowed, people_inside
    max_people_allowed = m
    people_inside = i
    save_last_file(max_people_allowed, people_inside)
    root.after(100, update_the_screen)


def max_people_reached():   # Abfrage, ob maximale Anzahl Personen erreicht ist bzw darueber liegt. Flag,
    # steuert spaeter Stop anzeige
    global max_people_allowed, people_inside
    if max_people_allowed > people_inside:
        return False
    return True


# PIN EVENT HANDLER
def pin_inside_plus_resc(channel):  # Wird gecallt wenn der Plus Pin Signal erhaelt. callt  inside_plus und laesst
    # den Buzzer peepen
    # Funktion wird durch GPIO Bibliothek als Interrupt gecallt, deswegen u a flush=true bei print noetig
    inside_plus()
    print(channel, flush=True)
    print("Pin Inside Plus Empfangen", flush=True)
    t = threading.Thread(target=beep_buzzer)    # Callt Buzzer als Thread um Programm nicht zu unterbrechen, anzuhalten
    t.start()


def pin_inside_minus_resc(channel):  # Wird gecallt wenn der Plus Pin Signal erhaelt. callt  inside_minus und laesst
    # den Buzzer peepen
    # Funktion wird durch GPIO Bibliothek als Interrupt gecallt, deswegen u a flush=true bei print noetig
    inside_minus()
    print(channel, flush=True)
    print("Pin Inside Minus Empfangen", flush=True)
    t = threading.Thread(target=beep_buzzer)     # Callt Buzzer als Thread um Programm nicht zu unterbrechen, anzuhalten
    t.start()


# IP Address Handler
# Schaut ob die IP-Adresse teil der Liste ist. Falls nicht wird IP-Adresse der Liste hinzugefuegt.
# Liste wird heran genommen um vom Master an alle bekannten Slave-Stelen und Tablets die aktuellen Counter zu schicken
def handle_ips(ip_addr):
    global checked_in_ips
    if ip_addr not in checked_in_ips:
        checked_in_ips.append(ip_addr)


# OSC Handler
# got_ Funktionen werden vom OSC - Server gecallt und laufen als seperate Threads ab
def got_set_inside(address: str, *args: List[Any]) -> None:     # Kommt idR vom Tablet
    # sendet anschließend neue Counter an alle bekannten IPs
    if len(args) > 0:
        print(args, flush=True)
        inside = args[1]
        set_inside(inside)
        handle_ips(address[0])
        t = threading.Thread(target=send_counter_info_to_all)
        t.start()


def got_set_maximum(address: str, *args: List[Any]) -> None:     # Kommt idR vom Tablet
    # sendet anschließend neue Counter an alle bekannten IPs
    if len(args) > 0:
        print(args, flush=True)
        maximum = args[1]
        set_maximum(maximum)
        handle_ips(address[0])
        t = threading.Thread(target=send_counter_info_to_all)
        t.start()


def got_maximum_plus(address: str, *args: List[Any]) -> None:   # Kann vom Tablet oder Slave kommen
    # sendet anschließend neue Counter an alle bekannten IPs
    maximum_plus()
    handle_ips(address[0])
    t = threading.Thread(target=send_counter_info_to_all)
    t.start()


def got_maximum_minus(address: str, *args: List[Any]) -> None:  # Kann vom Tablet oder Slave kommen
    # sendet anschließend neue Counter an alle bekannten IPs
    maximum_minus()
    handle_ips(address[0])
    t = threading.Thread(target=send_counter_info_to_all)
    t.start()


def got_inside_plus(address: str, *args: List[Any]) -> None:    # Kann vom Tablet oder Slave kommen
    # sendet anschließend neue Counter an alle bekannten IPs
    inside_plus()
    handle_ips(address[0])
    t = threading.Thread(target=send_counter_info_to_all)
    t.start()


def got_inside_minus(address: str, *args: List[Any]) -> None:   # Kann vom Tablet oder Slave kommen
    # sendet anschließend neue Counter an alle bekannten IPs
    inside_minus()
    handle_ips(address[0])
    t = threading.Thread(target=send_counter_info_to_all)
    t.start()


def got_counter_info(address: str, *args: List[Any]) -> None:   # kommt in regelmaeßigen Abstaenden
    # vom Tablet oder Slave
    # Counter werden nur an die IP zurueck gesendet von der die Anfrage kam
    # Anwort wird vom Tablet u. a. dafuer verwendet die Konnektivitaet zu pruefen
    handle_ips(address[0])
    t = threading.Thread(target=send_counter_info, args=(address[0],))
    t.start()


# Sende Counter zurück an Sender
def send_counter_info(adress_send_to):
    global max_people_allowed, people_inside
    print(adress_send_to)
    client = udp_client.SimpleUDPClient(adress_send_to, 9001)
    msg = osc_message_builder.OscMessageBuilder(address="/counter_info")
    bundle = osc_bundle_builder.OscBundleBuilder(osc_bundle_builder.IMMEDIATELY)
    msg.add_arg(max_people_allowed)
    msg.add_arg(people_inside)
    bundle.add_content(msg.build())
    bundle = bundle.build()
    print("counter_info an {} gesendet mit max {} und inside {}".format(adress_send_to, max_people_allowed,
                                                                        people_inside), flush=True)
    client.send(bundle)


# Sende Counter an alle IPs in Liste checked_in_ips[]
def send_counter_info_to_all():
    global max_people_allowed, people_inside
    print(checked_in_ips)
    for i in range(len(checked_in_ips)):
        client = udp_client.SimpleUDPClient(checked_in_ips[i], 9001)
        msg = osc_message_builder.OscMessageBuilder(address="/counter_info")
        bundle = osc_bundle_builder.OscBundleBuilder(osc_bundle_builder.IMMEDIATELY)
        msg.add_arg(max_people_allowed)
        msg.add_arg(people_inside)
        bundle.add_content(msg.build())
        bundle = bundle.build()
        print("counter_info an {} gesendet mit max {} und inside {}".format(checked_in_ips[i], max_people_allowed,
                                                                            people_inside), flush=True)
        client.send(bundle)


# Im Slave Modus frage nach den Akutellen Countern
def send_counter_anfrage():
    client = udp_client.SimpleUDPClient("192.168.4.1", 9001)
    msg = osc_message_builder.OscMessageBuilder(address="/counter/counter_info")
    bundle = osc_bundle_builder.OscBundleBuilder(osc_bundle_builder.IMMEDIATELY)
    msg.add_arg(0)
    bundle.add_content(msg.build())
    bundle = bundle.build()
    client.send(bundle)
    print("Counter Anfrage gesendet")
    root.after(5000, send_counter_anfrage)


# Im Slave-Modus, falls neue Counter vom Master kommen, setze diese als neue Counter, update Anzeige und speichere
# neue Werte
def got_slave_info(address: str, *args: List[Any]) -> None:
    if len(args) > 0:
        print(args, flush=True)
        maximum = args[1]
        inside = args[2]
        # set_maximum(maximum)
        # set_inside(inside)
        set_maximum_and_inside(maximum, inside)


# Im Slave-Modus, wenn die Stele einen Durchgang erkennt, werden die entprechenden Counter Veraenderungen an den
# Master weiter gegeben
# Master hat immer die 192.168.4.1
def send_inside_plus_to_master():
    client = udp_client.SimpleUDPClient("192.168.4.1", 9001)
    msg = osc_message_builder.OscMessageBuilder(address="/counter/inside_plus")
    bundle = osc_bundle_builder.OscBundleBuilder(osc_bundle_builder.IMMEDIATELY)
    msg.add_arg(0)
    bundle.add_content(msg.build())
    bundle = bundle.build()
    client.send(bundle)


def send_inside_minus_to_master():
    client = udp_client.SimpleUDPClient("192.168.4.1", 9001)
    msg = osc_message_builder.OscMessageBuilder(address="/counter/inside_minus")
    bundle = osc_bundle_builder.OscBundleBuilder(osc_bundle_builder.IMMEDIATELY)
    msg.add_arg(0)
    bundle.add_content(msg.build())
    bundle = bundle.build()
    client.send(bundle)


def send_max_plus_to_master():
    client = udp_client.SimpleUDPClient("192.168.4.1", 9001)
    msg = osc_message_builder.OscMessageBuilder(address="/counter/max_plus")
    bundle = osc_bundle_builder.OscBundleBuilder(osc_bundle_builder.IMMEDIATELY)
    msg.add_arg(0)
    bundle.add_content(msg.build())
    bundle = bundle.build()
    client.send(bundle)


def send_max_minus_to_master():
    client = udp_client.SimpleUDPClient("192.168.4.1", 9001)
    msg = osc_message_builder.OscMessageBuilder(address="/counter/max_minus")
    bundle = osc_bundle_builder.OscBundleBuilder(osc_bundle_builder.IMMEDIATELY)
    msg.add_arg(0)
    bundle.add_content(msg.build())
    bundle = bundle.build()
    client.send(bundle)


# Update Screen Display Zeichne die Zahlen und Stop Bildschirm
def update_the_screen():
    global max_people_allowed, people_inside
    global mainCanvas, video_player

    print("Starte Screen zeichnen")
    if not max_people_reached():    # Wenn maxiale Anzahl nicht erreicht
        mainCanvas.itemconfigure(backgroud_stele, image=background_go)       # GO Hintergrund
        mainCanvas.itemconfigure(logo_bottom, state='normal')  # Logo hinter Video
        my_text = 'PERSONEN'    # Text Personen
        mainCanvas.itemconfigure(personen_text, text=my_text, state='normal')
        my_text = str(max_people_allowed)            # Text Anzeige Maximale Anzahl
        mainCanvas.itemconfigure(numbers_right, text=my_text, state='normal')
        my_text = str(people_inside) + "/"          # Text Anzeige Personenanzahl
        mainCanvas.itemconfigure(numbers_left, text=my_text, state='normal')

        try:

            video_player.show_video()  # Zeige Video
            print("Show Video done")
        except:
            pass

    else:       # Wenn maximale Anzahl Erreicht  - - STOP
        try:
            video_player.hide_video()  # Blende Video aus
        except:
            pass
        mainCanvas.itemconfigure(backgroud_stele, image=background_stop)    # Zeige Stop Anzeige
        mainCanvas.itemconfigure(logo_bottom, state='hidden')               # Blende Logo aus
        mainCanvas.itemconfigure(personen_text, state='hidden')             # Blende Personen Text aus
        mainCanvas.itemconfigure(numbers_right, state='hidden')             # Blende Counter aus
        mainCanvas.itemconfigure(numbers_left, state='hidden')


# Starte OSC Server
def start_osc_server():
    global server
    print("*** STARTE OSC SERVER ***", flush=True)
    dispat = dispatcher.Dispatcher()

    # Empfangbare Messeges mit Functioncalls
    dispat.map("/counter/reset_inside", got_set_inside, needs_reply_address=True)
    dispat.map("/counter/reset_max", got_set_maximum, needs_reply_address=True)
    dispat.map("/counter/inside_plus", got_inside_plus, needs_reply_address=True)
    dispat.map("/counter/inside_minus", got_inside_minus, needs_reply_address=True)
    dispat.map("/counter/max_plus", got_maximum_plus, needs_reply_address=True)
    dispat.map("/counter/max_minus", got_maximum_minus, needs_reply_address=True)
    dispat.map("/counter/counter_info", got_counter_info, needs_reply_address=True)
    dispat.map("/counter_info", got_slave_info, needs_reply_address=True)
    print(local_ip, flush=True)
    server = osc_server.ThreadingOSCUDPServer((local_ip, 9001), dispat)

    server.serve_forever()


# Methoden zum Suchen und finden der Videos
def walktree(top, callback):
    """recursively descend the directory tree rooted at top, calling the
    callback function for each regular file. Taken from the module-stat
    example at: http://docs.python.org/lib/module-stat.html
    """
    for f in os.listdir(top):
        pathname = os.path.join(top, f)
        mode = os.stat(pathname)[stat.ST_MODE]
        if stat.S_ISDIR(mode):
            # It's a directory, recurse into it
            walktree(pathname, callback)
        elif stat.S_ISREG(mode):
            # It's a file, call the callback function
            callback(pathname)
        else:
            pass
            # Unknown file type, print a message
            # print('Skipping %s' % pathname)


def addtolist(file, extensions=['.mp4']):
    """Add a file to a global list of image files."""
    global file_list  # ugh
    filename, ext = os.path.splitext(file)
    e = ext.lower()
    # Only add common image types to the list.
    if e in extensions:
        print('Adding to list: ', file, flush=True)
        file_list.append(file)


def check_usb_stick_exists():
    # TODO: sind die globalen Variablen hier von Noeten ? Auf den ersten Blick nein
    global index_video, first_time_video_played, videoplayerthread
    print("Checking for USB", flush=True)

    direc = "/media/pi/"
    for f in os.listdir(direc):
        if len(os.listdir(direc + f)) > 0:
            return True
    return False


def start_video_player():   # Starte OMX Videoplayer der am unteren Bildschirmrand angezeigt wird
    # TODO global variablen checken, file_list muss ziemlich sicher nicht global sein,
    #  video_player wahrscheinlich auch nicht, first_time_video_played wird gar nicht benutzt
    global file_list, video_player, index_video, first_time_video_played
    print("Laenge von Filelist: {}".format(len(file_list)))
    t = threading.currentThread()
    index_video = 0
    while getattr(t, "running", True):
        if len(file_list) > 0:
            print("File exists: {}".format(os.path.exists(file_list[index_video])))
            if os.path.exists(file_list[index_video]):
                filey = file_list[index_video]
                print("VIDEO Playing {}".format(filey), flush=True)
                t = threading.Event()
                index_video = index_video + 1
                if index_video > len(file_list) - 1:
                    index_video = 0
                try:
                    video_player_playing = video_player.is_playing()
                except:
                    video_player_playing = False

                if not video_player_playing:
                    video_player = OMXPlayer(filey,
                                             args=['--orientation', '270', '--win', '1312,0,1920,1080', '--no-osd',
                                                   '--vol',
                                                   '-10000000'], dbus_name='org.mpris.MeidlaPlayer2.omxplayer1')

                else:
                    video_player.load(filey)

                try:
                    duration_of_video = video_player.duration() + 3
                except:
                    duration_of_video = 3
                    print("duration of video failed", flush=True)

                print(duration_of_video, flush=True)
                video_player.mute()
                if max_people_reached():
                    video_player.hide_video()
                video_player.play_sync()
                sleep(3)
                # sleep(duration_of_video)
            else:
                break
        else:
            break


def starte_server_thread():     # Thread in dem der OSC Server gestartet wird
    run_osc_server = threading.Thread(target=start_osc_server)
    run_osc_server.start()


def checkifvideoplayerisallive():
    global videoplayerthread
    print(videoplayerthread.is_alive())
    print("poop")
    while True:
        if not videoplayerthread.is_alive():
            root.after(1000, check_usb_stick_exists)
        sleep(10)


def usb_video_handler():
    global videoplayerthread, video_player, file_list

    while True:
        print("usb_vide_handler Go")
        try:
            if check_usb_stick_exists():
                # tt = threading.Thread(target=start_video_player)
                # tt.start()
                if not videoplayerthread.is_alive():
                    file_list = []
                    walktree("/media/pi", addtolist)
                    print("Checking for mp4")
                    print("Videoplayer Dead, restarting")
                    first_time_video_played = True
                    index_video = 0
                    videoplayerthread = threading.Thread(target=start_video_player)
                    videoplayerthread.start()
            else:
                if videoplayerthread.is_alive():
                    print("Trying to Stop Video")
                    video_player.quit()
                    videoplayerthread.running = False
        except:
            print("Something went wrong with the usb or videplayer, going to retry now")
        sleep(1)


def beep_buzzer():
    global pin_buzzer
    print("BEEP")
    GPIO.output(pin_buzzer, 1)
    sleep(0.1)
    GPIO.output(pin_buzzer, 0)


# GPIO Setup Part2
if platform.system() != "Windows":
    GPIO.setup(pin_people_going, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)
    GPIO.setup(pin_people_comming, GPIO.IN, pull_up_down=GPIO.PUD_DOWN)

    GPIO.setup(pin_buzzer, GPIO.OUT)
    GPIO.output(pin_buzzer, 0)

    GPIO.add_event_detect(pin_people_going, GPIO.RISING, callback=pin_inside_minus_resc)
    GPIO.add_event_detect(pin_people_comming, GPIO.RISING, callback=pin_inside_plus_resc)

# Lade Save File und letzte bekannte Besucher
max_people_allowed, people_inside = load_last_file()
videoplayerthread = threading.Thread(target=start_video_player)
checkifvideoplayerisalliveTread = threading.Thread(target=usb_video_handler)
checkifvideoplayerisalliveTread.start()

# Erstellen der GUI
mainCanvas = Canvas(root)
mainCanvas.pack(fill="both", expand=True)
# root.after(3000, check_usb_stick_exists)
root.after(2, starte_server_thread)
backgroud_stele = mainCanvas.create_image(0, 0, image=background_go, anchor="nw")
logo_bottom = mainCanvas.create_image((1080 / 2), (1312 + (1920 - 1312) / 2), image=logo, anchor=CENTER)
my_text1 = 'PERSONEN'
personen_text = mainCanvas.create_text(540, 1070, anchor=CENTER, text=my_text1, fill='white',
                                       font=('adineue PRO Bold', 80, 'bold'),
                                       state='normal')
my_text3 = str(max_people_allowed)
numbers_right = mainCanvas.create_text(540, 900, anchor=NW, text=my_text3, fill='white',
                                       font=('adineue PRO Bold', 80, 'bold'),
                                       state='normal')
my_text3 = str(people_inside) + "/"
numbers_left = mainCanvas.create_text(540, 900, anchor=NE, text=my_text3, fill='white',
                                      font=('adineue PRO Bold', 80, 'bold'),
                                      state='normal')
if is_master_modus:
    slave_master = mainCanvas.create_image(1080, 0, image=master_img, anchor=NE)
else:
    slave_master = mainCanvas.create_image(1080, 0, image=slave_img, anchor=NE)
    root.after(5, send_counter_anfrage)

root.after(1, update_the_screen)

root.mainloop()
