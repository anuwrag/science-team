# Author: Anurag Kanase
# Date: December 06, 2021

from tkinter import *
import serial
import serial.tools.list_ports as lp

allport = []
ports = serial.tools.list_ports.comports()
for p in ports:
    allport.append(p.device)

master = Tk()
label = Label(master, text="Choose the port: (e.g. /dev/cu.usbserial***)")  # ,width=20,font=("bold", 10))


def advance():
    rpms = txt1.get("1.0", 'end-1c')
    print(rpms)
    times = txt2.get("1.0", 'end-1c')
    print(times)
    usePort = variable.get()
    # usePort = usePort.encode()
    ser = serial.Serial(port=usePort, baudrate=9600)
    # rpm = "1000"
    # time = "5"
    # rx = b"ssts"+rpms+"\r"
    # rx = rx.encode()
    # tx = b"shakeOnWithRuntime"+times+"\r"
    # tx = tx.encode()
    times = times.encode()
    rpms = rpms.encode()
    ser.write(b'ssts' + rpms + b'\r')
    ser.write(b'shakeOnWithRuntime' + times + b'\r')
    print(ser.read(ser.in_waiting))
    print("Run the shaker on port:" + usePort + "rpm: " + rpms + "time: " + times)


def target_temp():
    temp = txt3.get("1.0", 'end-1c')
    temp = float(temp) * 10
    temp = int(temp)
    temp = str(temp)
    print(temp)
    usePort = variable.get()
    # usePort = usePort.encode()
    ser = serial.Serial(port=usePort, baudrate=9600)
    temp = temp.encode()
    ser.write(b'setTempTarget' + temp + b'\r')
    ser.write(b'tempOn' + b'\r')


def heatoff():
    usePort = variable.get()
    ser = serial.Serial(port=usePort, baudrate=9600)
    ser.write(b'tempOff' + b'\r')


master.geometry('310x280')
master.title("Move the Shaker")
variable = StringVar(master)
variable.set(allport[0])  # default value

w = OptionMenu(master, variable, *allport, advance)
label.place(x=20, y=5)
w.place(x=20, y=35)
txt1 = Text("", height=1, width=15)
txt1.place(x=75, y=77)
txt2 = Text("", height=1, width=5)
txt2.place(x=135, y=107)
txt3 = Text("", height=1, width=5)
txt3.place(x=90, y=190)

print()
# text_box.pack()
# w.pack()
label2 = Label(master, text="RPM")
label2.place(x=20, y=75)
label3 = Label(master, text="Time (seconds)")
label3.place(x=20, y=105)
label4 = Label(master, text="Temperature Control")
label4.place(x=20, y=165)
label5 = Label(master, text="Set temp:")
label5.place(x=20, y=187)
Button(master, text='Run', command=advance, width=10).place(x=20, y=130)

Button(master, text='Set Target Temperature', command=target_temp, width=20).place(x=20, y=210)

Button(master, text='Turn off Heating', command=heatoff, width=20).place(x=20, y=235)

mainloop()