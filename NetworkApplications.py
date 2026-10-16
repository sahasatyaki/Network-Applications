#!/usr/bin/env python3
# -*- coding: UTF-8 -*-

import argparse
import socket
import os
import sys
import struct
import time
import random
import traceback # useful for exception handling
import threading
# NOTE: Do not import any other modules - the ones above should be sufficient
def setupArgumentParser() -> argparse.Namespace:
        parser = argparse.ArgumentParser(
            description='A collection of Network Applications.')
        parser.set_defaults(func=ICMPPing, hostname='example.com')
        subparsers = parser.add_subparsers(help='sub-command help')
        
        parser_p = subparsers.add_parser('ping', aliases=['p'], help='run ping')
        parser_p.set_defaults(timeout=2, count=10)
        parser_p.add_argument('hostname', type=str, help='host to ping towards')
        parser_p.add_argument('--count', '-c', nargs='?', type=int,
                              help='number of times to ping the host before stopping')
        parser_p.add_argument('--timeout', '-t', nargs='?',
                              type=int,
                              help='maximum timeout before considering request lost')
        parser_p.set_defaults(func=ICMPPing)

        parser_t = subparsers.add_parser('traceroute', aliases=['t'],
                                         help='run traceroute')
        parser_t.set_defaults(timeout=2, protocol='icmp')
        parser_t.add_argument('hostname', type=str, help='host to traceroute towards')
        parser_t.add_argument('--timeout', '-t', nargs='?', type=int,
                              help='maximum timeout before considering request lost')
        parser_t.add_argument('--protocol', '-p', nargs='?', type=str,
                              help='protocol to send request with (UDP/ICMP)')
        parser_t.set_defaults(func=Traceroute)
        
        parser_w = subparsers.add_parser('web', aliases=['w'], help='run web server')
        parser_w.set_defaults(port=8080)
        parser_w.add_argument('--port', '-p', type=int, nargs='?',
                              help='port number to start web server listening on')
        parser_w.set_defaults(func=WebServer)

        parser_x = subparsers.add_parser('proxy', aliases=['x'], help='run proxy')
        parser_x.set_defaults(port=8000)
        parser_x.add_argument('--port', '-p', type=int, nargs='?',
                              help='port number to start web server listening on')
        parser_x.set_defaults(func=Proxy)

        args = parser.parse_args()
        return args


class NetworkApplication:

    def checksum(self, dataToChecksum: bytes) -> int:
        csum = 0
        countTo = (len(dataToChecksum) // 2) * 2
        count = 0

        while count < countTo:
            thisVal = dataToChecksum[count+1] * 256 + dataToChecksum[count]
            csum = csum + thisVal
            csum = csum & 0xffffffff
            count = count + 2

        if countTo < len(dataToChecksum):
            csum = csum + dataToChecksum[len(dataToChecksum) - 1]
            csum = csum & 0xffffffff

        csum = (csum >> 16) + (csum & 0xffff)
        csum = csum + (csum >> 16)
        answer = ~csum
        answer = answer & 0xffff
        answer = answer >> 8 | (answer << 8 & 0xff00)

        answer = socket.htons(answer)

        return answer

    def printOneResult(self, destinationAddress: str, packetLength: int, time: float, seq: int, ttl: int, destinationHostname=''):
        if destinationHostname:
            print("%d bytes from %s (%s): icmp_seq=%d ttl=%d time=%.3f ms" % (packetLength, destinationHostname, destinationAddress, seq, ttl, time))
        else:
            print("%d bytes from %s: icmp_seq=%d ttl=%d time=%.3f ms" % (packetLength, destinationAddress, seq, ttl, time))

    def printAdditionalDetails(self, packetLoss=0.0, minimumDelay=0.0, averageDelay=0.0, maximumDelay=0.0):
        print("%.2f%% packet loss" % (packetLoss))
        if minimumDelay > 0 and averageDelay > 0 and maximumDelay > 0:
            print("rtt min/avg/max = %.2f/%.2f/%.2f ms" % (minimumDelay, averageDelay, maximumDelay))

    def printOneTraceRouteIteration(self, ttl: int, destinationAddress: str, measurements: list, destinationHostname=''):
        latencies = ''
        noResponse = True
        for rtt in measurements:
            if rtt is not None:
                latencies += str(round(rtt, 3))
                latencies += ' ms  '
                noResponse = False
            else:
                latencies += '* ' 

        if noResponse is False:
            print("%d %s (%s) %s" % (ttl, destinationHostname, destinationAddress, latencies))
        else:
            print("%d %s" % (ttl, latencies))

class ICMPPing(NetworkApplication):
    #self: THis entire class # NetworkApplication: Parent class
    def receiveOnePing(self, icmpSocket, destinationAddress, ID, timeout):
        icmpSocket.settimeout(timeout)

        try:
            # print("Before receiving")
            # 1. Wait for the socket to receive a reply

            bytes, address = icmpSocket.recvfrom(65565)
            # print("The bytes and adress are: " , bytes, address)
            # 2. If reply received, record time of receipt, otherwise, handle timeout
            recvd_time = time.time()

            # 3. Unpack the imcp and ip headers for useful information, including Identifier, TTL, sequence number
            recvd_icmp_header = bytes[20:28]
            recvd_icmp_type, recvd_icmp_code, recvd_icmp_checksum, recvd_icmp_id, recvd_icmp_seqno = struct.unpack('BBHHH', recvd_icmp_header)
            # print(recvd_icmp_type, recvd_icmp_code, recvd_icmp_checksum, recvd_icmp_id, recvd_icmp_seqno)
            # print ("\n", ID)

            # 5. Check that the Identifier (ID) matches between the request and reply
            if(recvd_icmp_id == ID):
                ttl = bytes[8]
                # print(ttl)
                packetSize = len(bytes)
                seq_no = recvd_icmp_seqno
                return (recvd_time, ttl, packetSize, seq_no)

        except socket.timeout:
            print ("Timeout error")
            # recvd_time = 0
            # ttl = None
            # packetSize = None
            # seq_no = None

        # 6. Return time of receipt, TTL, packetSize, sequence number
        return (0, 0, 0, 0)
        # pass

    def sendOnePing(self, icmpSocket, destinationAddress, ID, seq_num):
        # 1. Build ICMP header
        icmp_type = 8 # ICMP echo REQUEST 
        icmp_code = 0
        icmp_checkSum = 0  
        icmp_id = ID
        icmp_seqno = seq_num
        icmp_header = struct.pack('BBHHH', icmp_type, icmp_code, icmp_checkSum, icmp_id, icmp_seqno)
        # 2. Checksum ICMP packet using given function
        checksum_calculation  = self.checksum(icmp_header + b'a' * 36)
        # 3. Insert checksum into packet
        icmp_header = struct.pack('BBHHH', icmp_type, icmp_code, checksum_calculation, icmp_id, icmp_seqno)
        # 4. Send packet using socket
        # icmpSocket.setsockopt(socket.IPPROTO_IP)
        sending = icmpSocket.sendto(icmp_header+ b'a'*36, (destinationAddress, 0))
        # print("printed")

        # address
        # portNo = 0
        # (address, portNo)

        # 5. Return time of sending
        time_sent = time.time() #start time
        return time_sent
        pass

    def doOnePing(self, destinationAddress, packetID, seq_num, timeout, hostName):
        # 1. Create ICMP socket
        icmpSocket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        # 2. Call sendOnePing function
        call_sendOnePing = self.sendOnePing(icmpSocket, destinationAddress, packetID, seq_num)
        # 3. Call receiveOnePing function
        (recvd_time, ttl, packetSize, seq_num) = self.receiveOnePing(icmpSocket, destinationAddress, packetID, timeout)
        # 4. Close ICMP socket
        close_mypacket = icmpSocket.close()
        # 5. Print out the delay (and other relevant details) using the printOneResult method, below is just an example.
        # HAVE TO ALTER THIS
        if(recvd_time == 0):
            print("Packets not received")
        else:
            self.printOneResult(destinationAddress, packetSize, (recvd_time-call_sendOnePing)*1000, seq_num, ttl, hostName) # Example use of printOneResult - complete as appropriate
        pass

    def __init__(self, args):
        print('Ping to: %s...' % (args.hostname))
        # 1. Look up hostname, resolving it to an IP address    
        ip = socket.gethostbyname(args.hostname)
        # 2. Repeat below args.count times
        for i in range(1, args.count+1):
            # 3. Call doOnePing function, approximately every second, below is just an example
            self.doOnePing(ip, 1, i, 2, args.hostname) # I HAVE REPLACED THE destinationAddress = 0, WITH 'i' TO CREATE A DISTINCT ADDRESS
            time.sleep(1)

class Traceroute(NetworkApplication):

    def receiveOneTraceroute(self, icmpSocket, destinationAddress, ID, timeout, protocol, store):
        icmpSocket.settimeout(timeout)

        try:
            # print("Before receiving")
            # 1. Wait for the socket to receive a reply
            bytes, address = icmpSocket.recvfrom(65565)
            recvd_time = time.time()

            # 3. Unpack the imcp and ip headers for useful information, including Identifier, TTL, sequence number
            recvd_icmp_header = bytes[20:28] # Time exceeded header for ICMP or UDP
            recvd_icmp_type, recvd_icmp_code, recvd_icmp_checksum, recvd_icmp_id, recvd_icmp_seqno= struct.unpack(
                'BBHHH', recvd_icmp_header)
            
            source_address = bytes[12:16]  
            a, b, c, d = struct.unpack(
                'BBBB', source_address)
            

            if (recvd_icmp_type == 11): # HERE, I SHOULD CHECK IF THE RECVD ICMP CODE IS 11
                recvd_icmp_type, recvd_icmp_code, recvd_icmp_checksum, recvd_icmp_id, recvd_icmp_seqno= struct.unpack(
                'BBHHH', recvd_icmp_header)

                # if protocol is icmp
                if(protocol == "icmp"):
                    # If I send out an ICMP packet, it is an ICMP header.  
                    new_icmp_header = bytes[48:56]
                    recvd_icmp_type, recvd_icmp_code, recvd_icmp_checksum, recvd_icmp_id, recvd_icmp_seqno = struct.unpack(
                        'BBHHH', new_icmp_header)
                    
                    if(recvd_icmp_id == ID):
                        ttl = bytes[8]
                        # print(ttl)
                        packetSize = len(bytes)
                        seq_no = recvd_icmp_seqno
                        # print("here9")
                
                    return (recvd_time, ttl, packetSize, seq_no, f"{a}.{b}.{c}.{d}")

                # if udp
                elif (protocol == "udp"):
                    # If I send an UDP packet, I get the UDP Header in the time exceeded packet.  
                    new_udp_header = bytes[48:56]
                    recvd_udp_sourceport,recvd_udp_destport, recvd_udp_length, recvd_udp_checksum = struct.unpack(
                        'HHHH', new_udp_header)
                    if(store[1] == recvd_udp_sourceport): # CHECKING IF SOURCE PORT SENT = SOURCE PORT RECIEVED.  
                        ttl = bytes[8]
                        packetSize = len(bytes)


            ttl = bytes[8]
            # print(ttl)
            packetSize = len(bytes)
            seq_no = recvd_icmp_seqno
            # print("here")

            return (recvd_time, ttl, packetSize, seq_no, f"{a}.{b}.{c}.{d}")

        except Exception as e:

            return (0, 0, 0, 0, 0)


    def sendOneTraceroute(self, icmpSocket, destinationAddress, ID, seq_num, time_to_live):
        # 1. Build ICMP header | Use icmpSocket.setsockopt(socket.IPPROTO_IP) set TTL. |
        icmp_type = 8  # ICMP echo REQUEST
        icmp_code = 0
        icmp_checkSum = 0
        icmp_id = ID
        icmp_seqno = seq_num
        icmp_header = struct.pack('BBHHH', icmp_type, icmp_code, icmp_checkSum, icmp_id, icmp_seqno)
        # 2. Checksum ICMP packet using given function
        checksum_calculation = self.checksum(icmp_header)
        # 3. Insert checksum into packet
        icmp_header = struct.pack('BBHHH', icmp_type, icmp_code, checksum_calculation, icmp_id, icmp_seqno)
        # 4. I should Set the TTL for my socket and send my packet using socket
        setting_my_ttl = icmpSocket.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, time_to_live)
        # print("Before printed")
        sending = icmpSocket.sendto(icmp_header, (destinationAddress, 0))
        # print(sending) # PRINTING 8
        # print("After printed")
        # 6. Return time of sending
        time_sent = time.time() #start time
        return time_sent
        # pass

    def sendOneTracerouteUDP(self, icmpSocket, destinationAddress, ID, seq_num, time_to_live):
        # 1. I am creating an UDP socket.
        socketUDP = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        socketName = socketUDP.getsockname()
        # 2. I should Set the TTL for my socket and send my packet using socket
        setting_my_ttl = socketUDP.setsockopt(socket.IPPROTO_IP, socket.IP_TTL, time_to_live)
        # print("Before printed")
        data = bytes(10)
        sending_udp = socketUDP.sendto(data, (destinationAddress, 33437))
        # print(sending) # PRINTING 8
        # print("After printed")
        # 6. Return time of sending
        time_sent = time.time() #start time
        return time_sent, socketName
        # pass

    def doOneTraceroute(self, destinationAddress, packetID, ttl, timeout, protocol):
        # 1. Create ICMP socket


        storage = []
        icmpSocket = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
        # 2. Repeat with increasing TTL until reaching my destination
            #2.a I have to set up an maximum number for hops to stop an infinite loop.
        number_of_hops = 30
            #2.b Make a loop for time to live that goes from 1 to the maximum number of hops
        for i in range (3):
            # 3. I should Call sendOneTraceroute function
            if (protocol == "icmp"):
                store = None
                sendingTraceroute = self.sendOneTraceroute(icmpSocket, destinationAddress, packetID, timeout, ttl) # time to live should be i
            elif (protocol == "udp"):
                sendingTraceroute, store = self.sendOneTracerouteUDP(icmpSocket, destinationAddress, packetID, timeout, ttl)
            # 4. Now, I Call receiveOneTraceroute function
            # print("here:",self.receiveOneTraceroute(icmpSocket, destinationAddress, packetID, timeout))
            recvd_time, recvd_ttl, packetSize, seq_num, address = self.receiveOneTraceroute(icmpSocket, destinationAddress, packetID, timeout,args.protocol, store)
            if(recvd_time == 0):
                storage += [None]
                pass
            else:
                storage += [(recvd_time-sendingTraceroute) * 1000]
            # 5. I Print out the delay (and other relevant details) using the printOneTraceRouteIteration method, below is just an example.

        try:
            a, b, c = socket.gethostbyaddr(address)
        except:
            a = address

        self.printOneTraceRouteIteration(ttl,address, storage, a)
            # 6. If I receive the reply, I have to stop the traceroute

        # 7. Finally, I should close the icmpSocket.
        icmpSocket.close()

        return address
        pass
    def __init__(self, args):
        print('Traceroute to: %s...' % (args.hostname))
        # # 1. Look up hostname, resolving it to an IP address
        ip = socket.gethostbyname(args.hostname)
        # # 2. Repeat below args.count times
        # Call the doOneTraceroute 30 times each with different ttl


        print(args.protocol)


        for ttl in range(1, 30):
        #     # 3. Call doOnePing function, approximately every second, below is just an example
            address_call = self.doOneTraceroute(ip, 1, ttl, 2, args.protocol)  # I HAVE REPLACED THE destinationAddress = 0, WITH 'i' TO CREATE A DISTINCT ADDRESS

            if(address_call == ip):
                # print("dest reached")
                break

class WebServer(NetworkApplication): #2.1

    def handleRequest(self, tcpSocket):
        # 1. Receive request message from the client on connection socket
        recv_rqst_msg = tcpSocket.recv(1024)
        print(recv_rqst_msg.decode())
        # 2. Extract the path of the requested object from the message (second part of the HTTP header)
        path_extract = recv_rqst_msg.split()[1]
        print("Extract: ", path_extract)
        decode_path = path_extract.decode("utf-8")
        # 3. Read the corresponding file from disk
        try:
            opening_file = open(decode_path[1:])
        # 4. Store in temporary buffer
            reading_file = opening_file.read()
            print(reading_file)
            response = 'HTTP/1.1 200 OK\r\n\r\n'
            # 6. Send the content of the file to the socket
            tcpSocket.send(response.encode())
            tcpSocket.sendall(reading_file.encode())
        # 5. Send the correct HTTP response error
        except:
            response = "HTTP/1.1 404 NOT FOUND\r\n\r\n"
            # 6. Send the content of the file to the socket
            tcpSocket.sendall(response.encode())

        # 7. Close the connection socket
        tcpSocket.close()
        pass

    def __init__(self, args):
        print('Web Server starting on port: %i...' % (args.port))
        ADDRESS = "127.0.0.1"
        PORT = args.port
        # 1. Create server socket
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # 2. Bind the server socket to server address and server port
        server_bind = server.bind((ADDRESS, PORT))
        # 3. Continuously listen for connections to server socket
        while(True):
            # 4. When a connection is accepted, call handleRequest function, passing new connection socket (see https://docs.python.org/3/library/socket.html#socket.socket.accept)
            server.listen(1)
            conn, address = server.accept()
            self.handleRequest(conn)

        # 5. Close server socket
        server_close = server.close()


class Proxy(NetworkApplication): # 2.2
    def handleRequest(self, tcpSocket):
        cache = "Cache Folder"

        if not os.path.exists(cache):
            make_dir = os.mkdir(cache)


        # 2. I should make an Infinite loop
        recv_rqst_msg = tcpSocket.recv(1024)
        print(recv_rqst_msg.decode())

        # 2c. Extract the path of the requested object from the message (second part of the HTTP header)
        hostname = recv_rqst_msg.split()[4]
        url = recv_rqst_msg.split()[1].decode('utf-8')

        path = url.split('/', 3)[3] # IT DOES NOT SPLIT THE PATH
        print(path)

        print("Extract: ", path)
        # decode_path = path.decode("utf-8")

        extract = recv_rqst_msg.split()[5]
        print("hostname", hostname)

        decode_hostname = hostname.decode('utf-8')
        # ADD THESE 2 LINES AFTER GENERATING PATH.
        filepath = "Cache Folder/"+os.path.join(decode_hostname, path, ".html").replace("/", " ")

        if(os.path.isfile(filepath)):
            reading = open(filepath, "rb")
            store = reading.read()
            print(store)
            # file = open(filepath, "x")
            tcpSocket.sendall(store)
            print("From cache")
            reading.close()
            tcpSocket.close()
            return
            
        # Creating client and server sockets
        server1 = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

        my_port = 80
        try:
            host = socket.gethostbyname(hostname)
            print(host)
            print ("Before")
            server1.connect((host, my_port))
            print("Connected")

            # 6. Send the content of the file to the socket
            server1.sendall(recv_rqst_msg)
            # 3. Read the corresponding file from disk
            open_file = open(filepath, "wb")
            while True:
                recv_data = server1.recv(1024)
                tcpSocket.sendall(recv_data)
                open_file.write(recv_data)
                if(len(recv_data) <= 0):
                    break
            print("From server")
            server1.close()

        except:
            response = "HTTP/1.1 404 NOT FOUND\r\n\r\n"
            # 6. Send the content of the file to the socket
            tcpSocket.sendall(response.encode())

        tcpSocket.close()
    
    def __init__(self, args):
        print('Web Proxy starting on port: %i...' % (args.port))
        ADDRESS = "127.0.0.1"
        PORT = args.port
        # 1. I should first create a server socket
        client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        client.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        # 2. Bind the server socket to server address and server port
        server_bind = client.bind((ADDRESS, PORT))
        # 3. Continuously listen for connections to server socket
        while(True):
            # 4. When a connection is accepted, call handleRequest function, passing new connection socket (see https://docs.python.org/3/library/socket.html#socket.socket.accept)
            client.listen(1)
            conn, address = client.accept()
            self.handleRequest(conn)

# Do not delete or modify the code below
if __name__ == "__main__":
    args = setupArgumentParser()
    args.func(args)