import socket
import struct
from time import sleep

MulticastServerPort = 10000

def sendMulticastMessage():
    leader_server_found = False
    message = 'This is a multicast msg'
    multicast_group = ('224.3.29.71', MulticastServerPort)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)     # Create the datagram socket
    sock.settimeout(2)
    # Set the time-to-live for messages to 1 so they do not go past the local network segment.
    ttl = struct.pack('b', 1)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, ttl)

    while (not leader_server_found):
        try:
            print('Sending multicast msg to discover leader server')
            sent = sock.sendto(message.encode(), multicast_group)              # Send data to the multicast group
            while True:
                print('Server multicast: Waiting for respond from the leader')
                try:             # Look for responses from all recipients
                    data, server_addr = sock.recvfrom(128)  # bytes
                    if data.decode() == "True":
                        print('respond "%s" from %s' % (data.decode(), server_addr))
                        leader_server_found = True  # Leader Server discovered stop multicasting
                        break
                except socket.timeout:
                    #print('Timed out, no more responses')
                    break
        except KeyboardInterrupt:  # on CTRL-C
            break

        except:
            print("Failed to send multicast message")

        if leader_server_found is False:  # send another multicast after 2 seconds only when leader is not found
            sleep(2)