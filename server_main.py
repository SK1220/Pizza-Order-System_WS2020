from socket import socket, AF_INET, SOCK_STREAM, INADDR_ANY, SOCK_DGRAM, IPPROTO_IP, IP_ADD_MEMBERSHIP
import socket
import threading
import sys
import pickle
import re
import struct
from time import sleep
from lcr import *
from server_multicast import sendMulticastMessage

# Ports

MulticastServerPort = 10000                # Multicast server Port
UnicastServerPort = 8300                   # TCP Unicast heartbeat Port between server | Thread 4 | StartHeartbeat
MulticastClientPort = 8200                 # Clients Port to discover leader and connect to leader | Thread 9
CommunicationPort = 8080                   # Communication Port between leaderserver and Client
ClientListUpdateServerPort = 8090          # Get updated client list port from leader
ServerlistUpdatePort = 8060                # Get updated server list port from leader
UpdateOrderlistPort = 8070                 # Replicating orderlist port from leader to replica
LCRPort = 8100                             # Port used for new leader election when leader crashes
NewLeaderMessagePort = 8110                # Port to inform all server about new leader after the election executed
SendOrderlistToNewLeaderPort = 8105

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.connect(("8.8.8.8", 80))
host_ip_address = s.getsockname()[0]


class Server:
    def __init__(self):
        self.serverlist = []            # Stores the server addresses
        self.clientlist = []            # Stores the client addresses
        self.customerclientlist = []    # Stores the customer addresses
        self.isLeader = False           # Stores Leader state
        self.PizzaReadylist = []        # Stores Finished Orders with the current Client
        self.heartbeatActive = False    # Stores heartbeat running state
        self.heartbeat_thread = threading.Thread(target=self.startHeartbeat)
        self.heartbeat_counter = 0        # Variable used for the first start of the heartbeat function
        self.servermemberUpdate = False   # State for Server list updates
        self.clientlist_counter = [0, 0]  # Count for Client list update
        self.ordernumber = 0              # Automatically increases by every new Order
        self.orderlist = []               # Stores the Orders
        self.orderlist_update_thread_started = False  # Turns into True if the replication of the orderlist has started
        self.leaderCrashed = False  # If leader crash is detected this value turns into True and starts the election

    def updateServerList(self, newserverlist):
        if len(self.serverlist) == 0:  # Do nothing when serverlist is empty and finish heartbeat if all servers left
            print('Serverlist empty heartbeat not starting')
            self.heartbeatActive = False  # End running heartbeat when no server is left in the list

            self.heartbeat_counter = 0

            if self.isLeader is False:
                self.isLeader = True     # This server is the only one so turn into leader server
                print("Serverlist empty. I'm the new leader")

        elif len(self.serverlist) > 0:
            if self.heartbeat_counter == 0:
                self.heartbeat_counter = self.heartbeat_counter + 1
                self.serverlist = newserverlist         # Overwrite serverlist with updated list

                print("Starting Heartbeat. Serverlist:", self.serverlist)
                self.heartbeatActive = True
                self.heartbeat_thread = threading.Thread(target=self.startHeartbeat)  # Run heartbeat for first time
                self.heartbeat_thread.start()
            else:
                self.serverlist = newserverlist
                print("Serverlist is updated: ", self.serverlist)
                self.servermemberUpdate = True

# Ordered Reliable Multicast

    def sendUpdatedClientList(self):   # Function can only used by leader server
        if self.isLeader == True:
            if len(self.serverlist)>0:  # if server list consists at least one server replicate the updated client list
                for x in range(len(self.serverlist)):   # send new client to all replica servers in list
                    connection_and_leader = self.serverlist[x]  # host ip and port and True/False
                    server_adress, isLeader = connection_and_leader  # split tuple
                    ip, port = server_adress  # split server_adress

                    s = socket.socket(AF_INET, SOCK_STREAM)  # create one heartbeat TCP socket for each server
                    s.settimeout(3)   # wait 3 seconds for respond

                    message1 = pickle.dumps(self.clientlist_counter)
                    message2 = pickle.dumps(self.clientlist) #  pickle to send objects
                    try:
                        s.connect((ip, ClientListUpdateServerPort))  # Connect to Client list update port
                        s.send(message1)
                        try:
                            response = s.recv(1024)
                            response = response.decode()
                            if response=='yes':
                                s.send(message2)
                                print("Client list has been sent to : {},{} ".format(ip, ClientListUpdateServerPort))
                            else:
                                print("Server {} already knows the client. Rejected client")
                        except socket.timeout:
                            print('No response received from sent clientlist_counter from:{}'.format(ip))

                    except Exception as e:
                        print(e)
                        print("Failed to send clientlist to: {},{}".format(ip, ClientListUpdateServerPort))
                    finally:
                        s.close()
            else:
                print("Serverlist is Empty cant replicate clientlist to member servers")

    def listenClientListUpdate(self): # Thread 3: Listening for clientlist updates
        server_address = ('', ClientListUpdateServerPort)
        sock = socket.socket(AF_INET, SOCK_STREAM)  # TCP socket
        sock.bind(server_address)
        sock.listen()

        while True:
            connection, server_address = sock.accept()
            message1 = connection.recv(1024)
            message1 = pickle.loads(message1)
            new_clientlist_counter = message1

            if new_clientlist_counter[0]> self.clientlist_counter[0] or new_clientlist_counter[1]> self.clientlist_counter[1] :

                response = 'yes'
                response = response.encode()
                connection.send(response)

                message2 = connection.recv(1024)
                message2 = pickle.loads(message2)
                self.clientlist = message2
                self.clientlist_counter = new_clientlist_counter
                print('Received update from leader. Clientlist: ', self.clientlist)
            else:
                response = 'no'
                response = response.encode()
                connection.send(response)
                print('Rejected client list update')

    def sendOrderlistUpdate(self):

        while True:
            if len(self.serverlist) == 0 :
                print('No replica servers in the list. Not asking for orderlist updates')

            if len(self.serverlist) >0 :    # update when servers exist
                # print('Asking replica servers for orderlist update')
                for x in range(len(self.serverlist)):   # Iterate through serverlist
                    connection_and_leader = self.serverlist[x]  # serverlist: tuple of a tuple and a boolean. The inside tuple are the connection details host ip and port
                    server_adress, isLeader = connection_and_leader  # split up tuple into sinlge variables
                    ip, port = server_adress  # split up server_adress into ip adress and port

                    s = socket.socket(AF_INET, SOCK_STREAM)  # TCP socket
                    s.settimeout(2)  # seconds
                    try:
                        s.connect((ip, UpdateOrderlistPort))  # Connect to each member servers UpdateOrderlistPort
                        ordernumber = pickle.dumps(self.ordernumber)
                        s.send(ordernumber)                          # send ordernumber and wait for the response

                        response = s.recv(1024)
                        response = pickle.loads(response)
                        if response == 'no':                 # no update
                            # No Update needed for server
                            pass
                        else:
                            for i in range(self.ordernumber-response):  # difference between leader order number and received replica server ordernumber
                                if i == 0:  # only for the first round of the loop
                                    if response == 0:  # Orderlist empty
                                        missing_element = 1
                                    else:  # We need the next element of response.
                                        missing_element = response + 1

                                missing_order = pickle.dumps(self.orderlist[missing_element-1])  # List index begins with zero therefore subtract -1 to get missing element
                                s.send(missing_order)
                                # Updating server: Sending ordernumber
                                ack_missing_order = s.recv(1024)
                                ack_missing_order = ack_missing_order.decode()
                                missing_element += 1  # count up to get the next needed element in orderlist
                    except:
                        print('Could not connect or send msg to:', ip, ',', UpdateOrderlistPort)
                        pass
                    finally:
                        s.close()
            sleep(30)   # Updates will be sent every 30 secs

    def listenforOrderlistUpdate(self):  # Thread 10         # Listening Orderlist with Server
        server_address = ('', UpdateOrderlistPort)
        sock = socket.socket(AF_INET, SOCK_STREAM)  # TCP socket
        sock.bind(server_address)  # Bind to the server address
        sock.listen()
        while True:
            connection, server_address = sock.accept()  # Wait for a connection
            leader_ordernumber = connection.recv(1024)
            leader_ordernumber = pickle.loads(leader_ordernumber)   # unpickle the order number and compare to own

            if leader_ordernumber > self.ordernumber:        # if leader has more orders than ask for the missing orders
                own_ordernumber = pickle.dumps(self.ordernumber)    # send own ordernumber
                connection.send(own_ordernumber)
                for i in range(leader_ordernumber-self.ordernumber):
                    missing_order = connection.recv(1024)           # wait for missing order
                    missing_order = pickle.loads(missing_order)
                    ack_msg_missing_order = 'Received missing order'
                    connection.send(ack_msg_missing_order.encode())
                    self.orderlist.append(missing_order)            # add missing order in own list
                    self.ordernumber += 1                           # count up own ordernumber
                print('Received missing updates from leader server. Current orderlist: ', self.orderlist)
            else:
                msg = 'no'
                msg = pickle.dumps(msg)
                connection.send(msg)
                # print('No updates received. Orderlist already equal to leader orderlist ')

# Dynamic Discovery

    def leaderCheck(self):
        leader_found = False
        message = 'This is a multicast msg'
        multicast_group = ('224.3.29.71', 5009)
        sock = socket.socket(AF_INET, SOCK_DGRAM)
        sock.settimeout(2)
        ttl = struct.pack('b', 1)  # Set the time-to-live for messages to 1 so after, the message is marked for deletion
        sock.setsockopt(IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)  # set options on sockets

        while not leader_found:
            try:
                print('Function LeaderCheck: Send multicast msg to discover leader server')
                sent = sock.sendto(message.encode(), multicast_group)
                while True:
                    print('Function LeaderCheck: Waiting for receive...')
                    try:
                        data, server_addr = sock.recvfrom(128)  # receive 128 bytes at once
                        if data.decode() == "True":
                            print('received "%s" from %s' % (data.decode(), server_addr))
                            leader_found = True  # Leader Server discovered -> Stop multicasting
                            break
                    except socket.timeout:
                        print('Function LeaderCheck: Timed out')
                        break
            except KeyboardInterrupt:  # on CTRL-C
                break
            except:
                print("Failed to send multicast message")

            if leader_found is False:  # send another multicast after 2 seconds only when leader is not found
                for i in range(2):
                    sleep(2)
                if i == 1:
                    s.isLeader = True
                    print("Function LeaderCheck: No Leader was found")
                    break

    def listenMulticast(self):  # Thread 7: Multicast to detect Leader and add to serverlist
        multicast_group = '224.3.29.71'
        server_address = ('', MulticastServerPort)
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(server_address)

        # Tell the operating system to add the socket to the multicast group on all interfaces.
        group = socket.inet_aton(multicast_group)
        mreq = struct.pack('4sL', group, socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        # Receive/respond loop
        while True:
            data, address = sock.recvfrom(128)

            if self.isLeader:  # If Leader than responds with "True"
                response = 'True'
            else:
                response = 'False'

            sock.sendto(response.encode(), address)

            if self.isLeader is True:
                if len(self.serverlist) == 0:  # If there is no server in the list add and send update
                    self.serverlist.append((address, False))  # Add new connection
                    self.updateServerList(self.serverlist)  # Overwrite serverlist with updated one
                    self.sendUpdatedServerList()  # Send updated list to all servers
                else:
                    # check if the connection is already in the list
                    for x in range(len(self.serverlist)):
                        connection_and_leader = self.serverlist[x]
                        replica_server_adress, isLeader = connection_and_leader  # split up tuple into sinlge variables

                        if replica_server_adress == address:  # Check if connection is already in list
                            break
                        else:
                            self.serverlist.append((address, False))  # Add new connection
                            self.updateServerList(self.serverlist)  # Overwrite serverlist with updated one
                            self.sendUpdatedServerList()  # Send updated list to all servers
                            break

            if len(self.clientlist) > 0:  # If Clients exists update new server with client list
                self.sendUpdatedClientList()

    def listenMulticastLeaderCheck(self):  # Thread 9 # Multicast  to detect Leader
        multicast_group = '224.3.29.71'
        server_address = ('', 5009)
        sock = socket.socket(AF_INET, SOCK_DGRAM)
        sock.bind(server_address)
        group = socket.inet_aton(multicast_group)  # add socket to the multicast group
        mreq = struct.pack('4sL', group, socket.INADDR_ANY)
        sock.setsockopt(IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        while True:
            data, address = sock.recvfrom(128)
            if self.isLeader:
                response = 'True'
            else:
                response = 'False'

            sock.sendto(response.encode(), address)

    def startMulticastMessage(self):  # Replica mode: Start discovering leader server
        sendMulticastMessage()


# Client Connection Sockets

    def startServer(self):
        try:
            s = socket.socket(AF_INET, SOCK_STREAM)  # SOCK_STREAM means that it is a TCP socket
            host_ip_address = ''
            print("Server started")
            s.bind((host_ip_address, CommunicationPort))  # Bind to the port

            # Calling listen() puts the socket into server mode
            s.listen()  # Listen/wait for new connections
            print("Server is waiting for incoming client connections...")

            # Create new thread and wait for new connections
            thread = threading.Thread(target=self.listenforConnections, args=(s,))
            thread.start()
        except socket.error as msg:
            print('Leader server already exist ')  # + str(msg[0]) + ' Message ' + msg[1]
            sys.exit()

    def listenClientMulticast(self):  # Thread 9
        # Listen for Client multicast messages and response with isLeaderValue
        # this function is for clients to discover the leader server and connect to leader server
        multicast_group = '224.3.29.71'
        server_address = ('', MulticastClientPort)
        sock = socket.socket(AF_INET, SOCK_DGRAM)  # UDP socket
        sock.bind(server_address)  # Bind to the server address
        group = socket.inet_aton(multicast_group)   # Add to multicast group.
        mreq = struct.pack('4sL', group, socket.INADDR_ANY)
        sock.setsockopt(socket.IPPROTO_IP, socket.IP_ADD_MEMBERSHIP, mreq)

        # Receive/respond loop
        # Listen to Client Multicast Address:
        while True:
            data, address = sock.recvfrom(128)
            if self.isLeader:
                response = 'True'
            else:
                response = 'False'
            sock.sendto(response.encode(), address)

    # Communication Loop with Client
    def listenforOrders(self, conn, addr):
        role = ""
        # print("listenOrders")
        try:
            while True:                  # If clients disconnects end while loop
                sleep(1.75)
                ordermsg = conn.recv(1024)
                ordermsg = ordermsg.decode()
                # Handle Role
                if ordermsg == "Client " or ordermsg == "SClient" or role == "Client " or role == "SClient":
                    if ordermsg == "Client ":
                        role = "Client"
                        current_client_orders = []  # Storege the Orders with the current Cliet
                        name = pickle.dumps("Your Name?")
                        conn.sendall(name)
                        name = conn.recv(1024)
                        name = name.decode()

                        order = pickle.dumps("Your Order?")
                        conn.sendall(order)

                        order = conn.recv(1024)
                        order = order.decode()
                        print(order)
                        ordermsg = order
                        # self.customerclientlist.append([name, addr])
                    if ordermsg == "SClient":
                        print("role = SClient")
                        role = "SClient"


                if ordermsg == 'disconnect' or len(
                        ordermsg) == 0:  # on Keyboard Interupt (CTRL-C) client will send "disconnect" when closind scirpt socket send 0 bytes
                    for i in range(len(self.clientlist)):
                        if addr == self.clientlist[i]:
                            print('Client', addr, "has disconnected")
                            del self.clientlist[i]
                            self.clientlist_counter[1] += 1
                            self.sendUpdatedClientList()
                        break
                else:
                    if ( role == "Client" and (not ordermsg == "check Order")):  # Handle new Orders
                        print('Received order from:', addr, ordermsg)
                        self.ordernumber += 1  # increase ordernumber by one
                        self.orderlist.append(
                            (self.ordernumber, addr, ordermsg, name))  # save tuple of ordernumber,addr, ordermsg in a list

                        if self.ordernumber == 1:  # Start updating thread when the first order is received
                            print('First order received starting updating thread with replica')
                            thread = threading.Thread(target=self.sendOrderlistUpdate)
                            thread.start()

                        print('\nTotal orderlist:', self.orderlist)
                        orderconfirm = ((name, self.ordernumber, addr, ordermsg))
                        orderconfirm = pickle.dumps(orderconfirm)
                        conn.sendall(orderconfirm)
                        current_client_orders.append(self.ordernumber)

                    elif ( role == "Client" and ordermsg == "check Order"): # Client query ready Orders
                        for i in current_client_orders:
                            print("Current Client Orders :" + str(i))
                            print("Pizza Ready list :" + str(self.PizzaReadylist))
                            if i in self.PizzaReadylist:
                                msg = pickle.dumps("Your Order with ID: " + str(i) + " is ready.")
                                conn.sendall(msg)
                                sleep(0.5)
                                print("current_client_orders " + str(current_client_orders))

                    if(bool(re.search("[0-9]+", ordermsg)) and role== "SClient"): # Stuff deliver Order with ID
                        mo = re.search("[0-9]+", ordermsg)
                        for i in range(len(self.orderlist)):
                            for j in range(len(self.orderlist[i])):
                                if mo[0] == str(self.orderlist[i][0]):
                                    print("Pizza Ready for Order: " + mo[0])
                                    self.PizzaReadylist.append(int(mo[0]))
                                    print(self.PizzaReadylist)
                                    break

                    if (( ordermsg == "getReadyList" ) and role == "SClient"):  # Stuff query ready Orders
                        for i in self.PizzaReadylist:
                            ordermsg = "Pizza Ready for Order: "
                            msg = pickle.dumps(ordermsg + str(i))
                            conn.sendall(msg)
                            sleep(0.5)

                    if ((ordermsg == "getOrderList") and role == "SClient"):  # Stuff query total Orders
                        for i in self.orderlist:
                            orderconfirm = str(i)
                            orderconfirm = pickle.dumps(orderconfirm)
                            conn.sendall(orderconfirm)
                            sleep(0.5)

                    if (ordermsg == "update"): # Stuff query for new Orders
                        if len(self.orderlist) > lenorderlist:
                            #print(str(lenorderlist) + " " + str(len(self.orderlist)))
                            for i in range(lenorderlist, len(self.orderlist)):
                                msg = pickle.dumps(self.orderlist[i])
                                conn.sendall(msg)
                                sleep(0.4)
                            lenorderlist = len(self.orderlist)

                    elif (role == "SClient"):  # Part of Staff Communication
                        msg = pickle.dumps("Hello Staff. Wait for Orders")
                        conn.sendall(msg)
                        #print(len(self.orderlist))
                        lenorderlist = len(self.orderlist)

                        if len(self.orderlist) > lenorderlist:
                            msg = pickle.dumps(self.orderlist[len(self.orderlist) - 1])
                            conn.sendall(msg)
                            lenorderlist = len(self.orderlist)
        except:
            for i in range(len(self.clientlist)):
                if addr == self.clientlist[i]:
                    print('Client', addr, "has disconnected")
                    del self.clientlist[i]
                    self.clientlist_counter[1] += 1
                    self.sendUpdatedClientList()

    def listenforConnections(self, s):  # Handels a single client connection. (Thread)
        while True:
            if self.isLeader is True:  # accept client connection when the server is the leader server
                conn, addr = s.accept()

                if self.clientlist:  # check if the connection exists in clientlist
                    for i in range(len(self.clientlist)):
                        if addr == self.clientlist[i]:
                            client_already_in_list = True
                            break
                        else:
                            client_already_in_list = False

                    if client_already_in_list is False:
                        print("Client ", addr, " has connected to the server ...")
                        self.clientlist.append(addr)  # Save incoming connection in List
                        self.clientlist_counter[0] += 1  # everytime a client connects first element increases by 1
                        print("Updated client list: ", self.clientlist)
                        self.sendUpdatedClientList()  # send updated client list to all replica servers

                        # Create new thread for every connected client. Each thread handles order from one client.
                        thread = threading.Thread(target=self.listenforOrders, args=(
                        conn, addr))  # conn is socket from client, s is socket from server
                        thread.start()
                    else:
                        print("Client ", addr, " has reconnected to the server ...")
                        self.sendUpdatedClientList()  # send updated client list to all replica servers
                        thread = threading.Thread(target=self.listenforOrders, args=(
                        conn, addr))  # conn is socket from client, s is socket from server
                        thread.start()

                else:
                    self.clientlist.append(addr)  # Save incoming connection in List
                    self.clientlist_counter[0] += 1  # everytime a client connects first element increases by 1
                    print("Client ", addr, " has connected to the server and is now online ...")
                    print("Updated client list: ", self.clientlist)
                    self.sendUpdatedClientList()    # send updated client list to all replica servers

                    # Create new thread for every connected client. Each thread handles order from one client.
                    thread = threading.Thread(target=self.listenforOrders, args=(conn, addr))   # conn is socket, addr and from Client
                    thread.start()

    def sendUpdatedServerList(self):
        if self.isLeader is True:
            if len(self.serverlist) > 0:  # if server list consists a server replicate the updated client list to the servers
                for x in range(len(self.serverlist)):  # send new clients to all replica servers in list
                    connection_and_leader = self.serverlist[x]  # host ip, port, true/false
                    server_adress, isLeader = connection_and_leader  # split up tuple into sinlge variables
                    ip, port = server_adress  # split up server_adress into ip adress and port

                    s = socket.socket(AF_INET, SOCK_STREAM)  # create one heartbeat TCP socket for each server
                    s.settimeout(3)  # wait 3 seconds for respond

                    try:
                        s.connect((ip, ServerlistUpdatePort))  # Connect to Client list update port

                        updatedserverlist = pickle.dumps(self.serverlist)
                        # send updated serverlist
                        s.send(updatedserverlist)
                        try:
                            response = s.recv(1024)
                            response = response.decode()
                        except socket.timeout:
                            #print('No response received from sent serverlist from: {}'.format(ip))
                            pass
                    except:
                        print("Failed to send serverlist to: {}".format(ip))
                    finally:
                        s.close()
            else:
                print("Serverlist is Empty cant replicate serverlist to member servers")

    def listenServerListUpdate(self):  # Listening for serverlist updates
        server_address = ('', ServerlistUpdatePort)
        sock = socket.socket(AF_INET, SOCK_STREAM)  # TCP socket
        sock.bind(server_address)  # Bind to the server address
        sock.listen()

        while True:
            connection, leader_address = sock.accept()  # Wait for a connection

            leaderserverlist = connection.recv(2048)              # save incoming bytes
            leaderserverlist = pickle.loads(leaderserverlist)       # unpickle the message

            newserverlist = []
            newserverlist = leaderserverlist                  # store leaderserverlist in new list

            serverlist_lenght = len(newserverlist)          # store lenght of newserverlist in variable

            for x in range(serverlist_lenght):
                connection_and_leader = newserverlist[x]  # serverlist format: ((host ip, port, true/false)
                server_adress, isLeader = connection_and_leader  # split up tuple into sinlge variables
                ip, port = server_adress  # split up server_adress into ip adress and port
                if ip == host_ip_address:   # remove own ip from list
                    del newserverlist[x]
                    newserverlist.append((leader_address, True))    # add leader server to list
                    self.serverlist = newserverlist                 # Overwrite own list with new one
                    sleep(0.5)                                    # just to print Receveived Multicast msg from leader before starting heartbeat message
                    self.updateServerList(self.serverlist)          # Overwrite old serverlist with the updated list

# Heartbeat

    def restartHeartbeat(self):
        if self.servermemberUpdate is True:
            self.servermemberUpdate = False  # latest update received

            if self.leaderCrashed is True:  # if leader crashed start election
                self.leaderCrashed = False
                print('Starting Leader Election')
                startElection(self.serverlist, host_ip_address)

            print("Restarting Heartbeat")
            self.heartbeat_thread = threading.Thread(
                target=self.startHeartbeat)  # overwrite dead thread and create new thread and rerun heartbeat
            self.heartbeatActive = True
            self.heartbeat_thread.start()

    def startHeartbeat(self):
        message = ('Heartbeat')
        failed_server = -1  # initial value -1 means there is no failed server

        while self.heartbeatActive:
            sleep(3)  # failure detection every 3 seconds
            for x in range(len(self.serverlist)):
                if self.servermemberUpdate is True:
                    self.heartbeatActive = False
                    break
                connection_and_leader = self.serverlist[x]
                server_adress, isLeader = connection_and_leader  # split up tuple into sinlge variables
                ip, port = server_adress  # split up server_adress into ip adress and port

                s = socket.socket(AF_INET, SOCK_STREAM)  # create one heartbeat TCP socket for each server
                s.settimeout(2)  # set timeout for every socket to 1 seconds
                try:
                    s.connect((ip, UnicastServerPort))  # Connect each socket to ip adress and UNICAST Port
                    s.send(message.encode())
                    # Sending Heartbeat: Heartbeatmsg sent to: {},{} ".format(ip, UnicastServerPort))
                    try:
                        response = s.recv(1024)
                        # print(response)
                    except socket.timeout:
                        #  No response
                        pass
                        # if no response is received remove server from list
                except:
                    # Server can't connect
                    failed_server = x  # Position of failed server in the server list

                    if isLeader is True:  # Crashed server is the leader
                        self.leaderCrashed = True
                        # print ('Leader crashed')

                finally:
                    s.close()

            if failed_server >= 0:  # If a failed server is detected
                newserverlist = self.serverlist
                del newserverlist[failed_server]
                if self.leaderCrashed is True:
                    print('Removed crashed leader server', ip, 'from serverlist')
                else:
                    print('Removed crashed server', ip, 'from serverlist')

                self.updateServerList(newserverlist)
                self.heartbeatActive = False

            # check if heartbeatActive value has changed
            if self.heartbeatActive is False:  # everytime serverlist is updated self.heartbeatActive will set to False to end thread
                break

        #print('Stopped Heartbeat!')
        self.restartHeartbeat()

    def listenHeartbeat(self):  # Thread 4: Handle heartbeat messages
        server_address = ('', UnicastServerPort)

        sock = socket.socket(AF_INET, SOCK_STREAM)  # Create a TCP/IP socket
        sock.bind(server_address)
        sock.listen()
        # Listening to Heartbeat
        while True:
            connection, server_address = sock.accept()  # Wait for a connection
            heartbeat_msg = connection.recv(1024)
            heartbeat_msg = heartbeat_msg.decode()
            # Listening Heartbeat:
            if heartbeat_msg:
                # Sending Heartbeat back
                connection.sendall(heartbeat_msg.encode())


# Leader election
    def sendnewLeaderMessage(self):
        if self.isLeader is True:
            message = host_ip_address      #IP of new leader
            for x in range(len(self.serverlist)):
                connection_and_leader = self.serverlist[x]  # serverlist:
                server_adress, isLeader = connection_and_leader  # split up tuple into sinlge variables
                ip, port = server_adress  # split up server_adress into ip adress and port

                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # create one heartbeat TCP socket
                s.settimeout(2)  # set timeout for every socket to 1 seconds
                try:
                    s.connect((ip, NewLeaderMessagePort))  # Connect to every servers socke to inform about new leader
                    s.send(message.encode())
                    print('Sending newLeaderMessage to ', ip)
                    try:
                        # Received ack from sent newLeaderMessage
                        response = s.recv(1024)
                    except socket.timeout:
                        pass
                finally:
                    s.close()           # Close socket

    def listenforNewLeaderMessage(self):  # Thread 5: Listening to NewLeaderMessage
        server_address = ('', NewLeaderMessagePort)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.bind(server_address)
        sock.listen()
        # Listening to NewLeaderMessage
        while True:
            connection, server_address = sock.accept()
            newleader_ip = connection.recv(1024)
            newleader_ip = newleader_ip.decode()

            for i in range(len(self.serverlist)):   # search for the leader IP in the serverlist
                connection_and_leader = self.serverlist[i]  # serverlist consists a tuple of a tuple and a boolean. The inside tuple are the connection details host ip and port
                server_adress, isLeader = connection_and_leader  # split up tuple into sinlge variables
                ip, port = server_adress  # split up server_adress into ip adress and port
                if ip == newleader_ip:  # When ip in list matches the leader ip change the isLeader value to True
                    self.serverlist[i] = server_adress, True   # Overwrite old value with new value

            response = 'ack msg.Received new leader information'    # send back ack msg
            connection.send(response.encode())

            newleadderID = newleader_ip.split('.')

            print('Received newLeaderMessage: new leader is:', newleadderID[3])
            print('Updated my serverlist: ', self.serverlist)

    def listenforElectionMessage(self):  # Thread 6
        server_address = ('', LCRPort)

        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # TCP socket
        sock.bind(server_address)  # Bind to the server address
        sock.listen()
        # Listening for LCR Election messages on Port: LCRPort
        while True:
            connection, server_address = sock.accept()  # Wait for a connection
            received_ip = connection.recv(1024)
            received_ip = received_ip.decode()         # Otherwise it is a IP and election is still running
            sleep(2)

            if socket.inet_aton(received_ip) == socket.inet_aton(host_ip_address):  # If received own ID. I'm the leader
                print("Leader Election: I'm the new leader")
                self.isLeader = True
                self.sendnewLeaderMessage()             # Inform other servers about the new leader

                print('Checking for orderlist updates on member servers')

                self.getLatestOrderlistfromServer()

                if len(self.clientlist) > 0:
                    print('Checking for orderlist updates on clients')
                    self.getLatestOrderlistfromClient()

                if self.ordernumber > 0:
                    print('Restarting orderlist update thread')
                    thread = threading.Thread(target=self.sendOrderlistUpdate)
                    thread.start()

            elif socket.inet_aton(received_ip) > socket.inet_aton(host_ip_address):  # e.g 192.168.0.100 > 192.168.0.50, if received IP is higher pass on to neighbor
                ipID = received_ip.split('.')
                hostID = host_ip_address.split('.')
                print('Received ID ', ipID[3], ' > ', hostID[3], '. Passing higher IP to neighbour')
                sendElectionmessage(received_ip)
            else:
                ipID = received_ip.split('.')
                hostID = host_ip_address.split('.')
                print('Received ID ', ipID[3], ' <  ', hostID[3], ' Not passing to neighbour')

    def listenforNewLeaderOrderlistRequest(self):  # Thread 2: act as Replica Server
        server_address = ('', SendOrderlistToNewLeaderPort)
        sock = socket.socket(AF_INET, SOCK_STREAM)
        sock.bind(server_address)
        sock.listen()
        while True:         # Checks the Ordelist
            connection, server_address = sock.accept()
            leader_ordernumber = connection.recv(1024)
            leader_ordernumber = pickle.loads(leader_ordernumber)
            print('Received ordernumber from leader:', leader_ordernumber)

            if self.ordernumber == leader_ordernumber or self.ordernumber < leader_ordernumber:
                print('Ordernumber identical with leader server')
                response = 'no'       # no updates
                connection.send(response.encode())
            else:
                print('My ordernumer is higher than leader order number. Sending order updates')
                message = pickle.dumps(self.orderlist)
                connection.send(message)

    def getLatestOrderlistfromServer(self):
        for x in range(len(self.serverlist)):
            connection_and_leader = self.serverlist[x]  # serverlist consists a tuple of a tuple and a boolean. The inside tuple are the connection details host ip and port
            server_adress, isLeader = connection_and_leader  # split up tuple into sinlge variables
            ip, port = server_adress  # split up server_adress into ip adress and port

            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)  # create one heartbeat TCP socket for each server
            s.settimeout(2)  # set timeout for every socket to 1 seconds

            try:
                s.connect((ip, SendOrderlistToNewLeaderPort))  # Connect to each member server
                ordernumber = pickle.dumps(self.ordernumber)
                s.send(ordernumber)  # send ordernumber and wait for the response

                response = s.recv(1024)
                try:
                    response = pickle.loads(response)
                except:
                    response = response.decode()

                if response == 'no':
                    print('New Leader: Orderlist of leader server and server', ip, ' is identical')
                else:
                    self.orderlist = response
                    self.ordernumber = len(self.orderlist)
                    print('Restored latest list form server', ip)
                    print('Current orderlist:', self.orderlist, 'Current ordernumber:',self.ordernumber)
            except:
                print('Could not connect or send msg to:', ip, ',', SendOrderlistToNewLeaderPort)
            finally:
                s.close()

    def getLatestOrderlistfromClient(self):
        for x in range(len(self.clientlist)):
            client_ip, client_port = self.clientlist[x]
            client_order_request_port = client_port + 200    #  port listening for requests for missed orders

            s = socket.socket(AF_INET, SOCK_STREAM)  # create one heartbeat TCP socket for each server
            s.settimeout(2)  # set timeout for every socket to 2 seconds

            leader_ordernumber_msg = pickle.dumps(self.ordernumber)

            try:
                s.connect((client_ip, client_order_request_port))  # Connect to every servers socket to inform about new leader
                s.send(leader_ordernumber_msg)

                response = s.recv(1024)
                try:                                #if the client has no higher orderid response will be 'no' which is string
                    response = response.decode()
                    print('Client',self.clientlist[x], 'has no missed orders')
                except:        # if response can not be decoded it means it's no string. It will be list of missed orders
                    missed_order_list = []
                    missed_order_list = pickle.loads(response)

                    for i in range(len(missed_order_list)):
                        self.orderlist.append(missed_order_list[i])
                        self.ordernumber += 1

                    print('Client', self.clientlist[x], 'has sent', len(missed_order_list), 'missed orders')
                    self.orderlist.sort(key=lambda x: x[0])  # after adding missed orders. Sort orderlist


            except:
                pass    # if connection cant be establish client is offline
        print('Latest orderlist:', self.orderlist)


if __name__ == '__main__':
    s = Server()  # create new server
    s.leaderCheck() # checks if leader exists

    s.startServer()                 #

    if s.isLeader == False:
        thread1 = threading.Thread(
            target=s.listenServerListUpdate)  # listen for serverlist updates
        thread1.start()
        s.startMulticastMessage()  # discover leader server

        thread2 = threading.Thread(target=s.listenforNewLeaderOrderlistRequest)
        thread2.start()

    thread3 = threading.Thread(target=s.listenClientListUpdate)  # Listening for clientlist updates with vector clock
    thread3.start()

    thread4 = threading.Thread(target=s.listenHeartbeat) # Listen for heartbeat messages
    thread4.start()

    thread5 = threading.Thread(target=s.listenforNewLeaderMessage)  # Leader Election: Listening for the NewLeaderMessage
    thread5.start()

    thread6 = threading.Thread(target=s.listenforElectionMessage) # Handling LCR Election messages
    thread6.start()

    thread7 = threading.Thread(target=s.listenMulticast) # Multicast to detect Leader and add to Serverlist
    thread7.start()

    thread8 = threading.Thread(target=s.listenMulticastLeaderCheck) # This function is to detect the leader server for other servers
    thread8.start()

    thread9 = threading.Thread(target=s.listenClientMulticast) # This function is for clients to discover the leader server
    thread9.start()

    thread10 = threading.Thread(target=s.listenforOrderlistUpdate)  # Listening Orderlist with Server
    thread10.start()

