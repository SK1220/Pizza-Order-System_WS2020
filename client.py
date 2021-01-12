""" Tkinter GUI  Pizza Ordering client. """
import tkinter
import tkinter as tk
from tkinter import *
import socket
from socket import AF_INET, SOCK_STREAM,  SOCK_DGRAM
from threading import Thread
import threading
import time
import re
import struct
import pickle
import os

port = 8080  # Server connection Port

class App(threading.Thread):
    def __init__(self,):
        Thread.__init__(self)
        self.leader_server_found = False  # stops multicasting when leader server is found
        self.client_orderlist = []        # stores placed orders in list
        self.client_socket = ''
        self.invalidorder = True          # Checks if orders are placed correctly
        self.connectedToLeader = False    # Checks if leader server is still online
        self.order_port = 0               # Connection Order Port to the leader.
        self.leader_order_request_port = 9200  # New Leader uses this port to

        self.thread = threading.Thread(target=self.listenforLeaderOrderRequest)
        self.thread.start()

        self.thread2 = threading.Thread(target=self.discoverLeaderServer)
        self.thread2.start()

        self.start()
        self.role = ""
        self.printrole = ""
        self.order_msg = ""

        self.firstpass = False
        self.name = 0

    def AppPrint(self, msg):  # Print in GUI
        self.msg_list.insert(tkinter.END, msg)

    def callback(self):  # Close the GUI
        self.top.quit()

    def run(self):  # Defines the GUI
        self.top = tk.Tk()
        self.top.title("Pizza Ordering System v1.0")
        messages_frame = tkinter.Frame(self.top)
        self.my_msg = tkinter.StringVar()  # Messages to be sent.
        self.my_msg.set("")  # clear field

        scrollbar = tkinter.Scrollbar(messages_frame)  # To navigate through past messages.
        self.msg_list = tkinter.Listbox(messages_frame, height=15, width=55, yscrollcommand=scrollbar.set)
        scrollbar.pack(side=tkinter.RIGHT, fill=tkinter.Y)
        self.msg_list.pack(side=tkinter.LEFT, fill=tkinter.BOTH)
        self.msg_list.pack()

        messages_frame.pack()

        frame1 = Frame(master=self.top)
        frame1.pack()
        self.button = tkinter.Button(master=frame1, text="Staff", command=self.staff_button_tieup)
        self.button.pack(padx=5, pady=5, side=LEFT)
        self.button2 = tkinter.Button(master=frame1, text="Customer", command=self.customer_button_tieup)
        self.button2.pack(padx=5, pady=5, side=LEFT)

        self.button_label = tkinter.Label(self.top, text="Text field:")
        self.button_label.pack()

        self.entry_field = tkinter.Entry(self.top, textvariable=self.my_msg, foreground="Black")
        self.entry_field.bind("<Return>", self.send)
        self.entry_field.bind('<FocusIn>', self.on_entry_click)
        self.entry_field.pack()

        self.send_button = tkinter.Button(self.top, text="Send messages", command=self.send)
        self.send_button.pack()

        self.update_button = tkinter.Button(self.top, text="Update", command=self.send_update)
        self.update_button.pack()

        self.frame2 = Frame(master=self.top)
        self.frame2.pack()
        self.pizza_button = tkinter.Button(master=self.frame2, text="Pizza", command=self.pizza_button_tieup)
        self.pizza_button.pack()

        self.total_list_button = tkinter.Button(master=self.frame2, text="Show total Order list", command=self.send_Get_OrderList)
        self.total_list_button['state'] = tkinter.DISABLED

        quit_button = tkinter.Button(self.top, text="Quit", command=self.on_closing)
        quit_button.pack()
        self.top.protocol("WM_DELETE_WINDOW", self.callback)

        self.top.mainloop()

    def on_entry_click(self, event):
        """function that gets called whenever entry1 is clicked"""
        self.entry_field.delete(0, "end")  # delete all the text in the entry
        self.entry_field.config(fg='BLUE')


    def on_closing(self, event=None):  # Quit Button
        """ This function is to be called when the window is closed. """
        try:
            self.disconnectToLeaderServer()
            self.top.quit()
            os.exit()
        except:
            self.top.quit()

    def disconnectToLeaderServer(self):
        msg = 'disconnect'
        msg = msg.encode()
        self.client_socket.send(msg)
        self.client_socket.close()

    def staff_button_tieup(self, event=None):
        """ Function for staff button action """
        self.role = "Customer"  #
        self.switchButtonState()
        print("Set SClient")
        self.order_msg = "SClient"
        self.printrole = "SClient"
        self.client_socket.send(self.order_msg.encode())
        self.pizza_button.configure(text="Show Delivery list", command=self.send_Get_DeliverList)
        self.total_list_button['state'] = tkinter.NORMAL
        self.total_list_button.pack()
        self.update_button['text'] = "Update Orders"
        self.button_label['text'] = "Enter finished Order ID/Message:"

    def customer_button_tieup(self, event=None):
        """ Function for smiley button action """
        self.role = "Client"
        print("Set Customer")
        self.order_msg = "Client "
        self.printrole = "Client"
        self.client_socket.send(self.order_msg.encode())
        self.pizza_button['text'] = 'Order Pizza'
        self.update_button['text'] = "Show deliveries"
        self.switchButtonState()

    def switchButtonState(self):
        try:
            if (self.pizza_button['text'] == 'Order Pizza'):
                self.button_label['state'] = tkinter.NORMAL
                self.entry_field['state'] = tkinter.NORMAL
                self.send_button['state'] = tkinter.NORMAL
        except:
            pass

    def pizza_button_tieup(self, event=None):
        """ Function for pizza button action """
        msg = "Pizza"
        self.client_socket.send(msg.encode())

    def send_update(self):
        msg = ""
        if self.printrole == "Client":
            msg = "check Order"
        elif self.printrole == "SClient":
            msg = "update"
        try:
            self.client_socket.send(msg.encode())  # send order
        except:
            print("except_send")
            pass

    def send_Get_DeliverList(self):
        msg = "getReadyList"

        try:
            self.client_socket.send(msg.encode())  # send order
        except:
            print("except_send")
            pass

    def send_Get_OrderList(self):
        msg = "getOrderList"

        try:
            self.client_socket.send(msg.encode())  # get orderlist for Staff
        except:
            print("except_send")
            pass

    def send(self, event=None):
        msg = self.my_msg.get()
        self.my_msg.set("")  # Clears input field.
        if ("Your Name?" == str(self.msg_list.get("end"))):
            self.name = msg           # Set Client name for automatic reconnecting
            self.firstpass = 2
        try:
            self.client_socket.send(msg.encode())  # send order
        except:
            print("except_send")
            pass

    def listenforLeaderOrderRequest(self):
        try:
            server_address = ('', self.leader_order_request_port)
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # Create a TCP/IP socket
            sock.bind(server_address)  # Bind to the server address
            sock.listen()

            while True:
                missed_order_list = []      # create everytime empty list

                connection, server_address = sock.accept()  # Wait for a connection
                received_ordernumber = connection.recv(1024)

                received_ordernumber = pickle.loads(received_ordernumber)   # unpickle ordernumebr from leader

                if len(self.client_orderlist)==0: # no orders send no to leader server
                    response = 'no'
                    connection.send(response.encode())
                else:                   # look in orderlist if there is a order id higher than leader order id
                    for x in range(len(self.client_orderlist)):
                        id, myconnection, order = self.client_orderlist[x]
                        if id > received_ordernumber:
                            missed_order_list.append(self.client_orderlist[x])  # id is higher put in to list
                        else:
                            pass    # do nothing
                    if len(missed_order_list)>0 :       # send missed orders to server
                        response = pickle.dumps(missed_order_list)
                        connection.send(response)
                    else:               # client has no missed orders to send
                        response = 'no'
                        connection.send(response.encode())
        except:
            pass

    def discoverLeaderServer(self):
        message = ('Client Multicast Message')
        multicast_group = ('224.3.29.71', 8200)

        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)       # Create the datagram socket
        sock.settimeout(2)    # Set a timeout so the socket does not block indefinitely when trying # to receive data. (in sec flaot)
        ttl = struct.pack('b', 1)  # Set the time-to-live for messages to 1 so they do not go past the local network segment.
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)

        print("Dynamic Discovery of Leader")
        while(not self.leader_server_found):
            try:
                # Send data to the multicast group and wait for receive
                sent = sock.sendto(message.encode(), multicast_group)
                print('Dynamic Discovery: Waiting to receive')
                while True:
                    try:
                        data, server_addr = sock.recvfrom(128)  # bytes

                        if data.decode() == "True":
                            leader_server, port = server_addr  # split up server_adress into ip adress and port
                            self.leader_server_found = True    # Leader Server discovered stop multicasting

                    except socket.timeout:
                        break

            except KeyboardInterrupt:   # on CTRL-C
                break
            except:
                print("Failed to send multicast message")

        sock.close()

        self.connectToLeaderServer(leader_server)

    def connectToLeaderServer(self,leader_server):
        self.client_socket = socket.socket(AF_INET, SOCK_STREAM)
        self.client_socket.bind(('',self.order_port))      # Connection port for the client

        self.client_socket.connect((leader_server, port))
        print("Client connected to Leader Server: ", leader_server)
        self.connectedToLeader = True

        if self.firstpass > 0:
            try:
                if self.printrole == "Client":
                    self.customer_button_tieup()
                else:
                   self.staff_button_tieup()
            except:
                pass

        else:
            self.AppPrint("Welcome to the Pizza Order System!")
            self.AppPrint("Please choose your Role.")
            self.firstpass = 1

        while self.connectedToLeader:

            time.sleep(0.5)
            try:
                # Wait for response
                response = self.client_socket.recv(1024)  # wait for order confirmation
            except:
                print('Order could not be sent')
                self.invalidorder = True
                self.role == ""
                self.connectedToLeader = False  # leader crashed
                break
            if len(response) == 0:  # 0 bytes means leader crashed
                time.sleep(3)
                print("Leader Server not online, starting leader discovery again")
                self.connectedToLeader = False
            else:
                response = pickle.loads(response)
                print("response: " + str(response))
                self.client_orderlist.append(response)
                #print(self.printrole)
                if (not(re.search('Pizza', str(response)) == None) and (self.printrole == "Client")) :
                    self.AppPrint("Pizza order received (ID " + str(response[1]) + ") ")

                else:
                    if (self.firstpass >= 1 and (response == "Your Name?" or response == "Hello Staff. Wait for Orders" or response == "Your Order?")):
                        if  self.printrole == "Client" and self.firstpass >= 2 and response == "Your Name?":
                            msg = self.name
                            print("self.name: " + self.name)
                            self.client_socket.send(msg.encode())
                            self.firstpass == 4
                        elif response == "Your Order?" and self.firstpass == 3:
                            pass
                        elif response == "Hello Staff. Wait for Orders" and self.firstpass == 1:
                            self.AppPrint(response)
                            self.firstpass = 2
                        elif response == "Hello Staff. Wait for Orders" and self.firstpass == 2:
                            pass
                        else:
                            if response == "Your Order?":
                                self.firstpass = 3
                            self.AppPrint(response)
                            pass

                    else:
                        self.AppPrint(response)
                        print('Received order confirmation', response)


            if (self.printrole == "SClient"):
                pass

        self.client_socket.close()       # close the client socket and start discovery again for leader server

        self.leader_server_found=False  # since we have no leader set value back to inital
        self.discoverLeaderServer()

if __name__ == '__main__':
    try:
        c = App()

    except KeyboardInterrupt:
        print(' Disconnecting client')
        c.diseconnectToLeaderServer()