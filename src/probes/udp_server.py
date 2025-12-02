#!/usr/bin/env python3
"""
UDP Reflector Server
Lightweight echo server that reflects UDP packets back to sender
Runs on worker-2 for network probing and jitter measurement
"""

import socket

def main():
    """Run UDP reflector server on port 5201"""
    host = '0.0.0.0'
    port = 5201
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((host, port))
    
    print(f"UDP Reflector started on {host}:{port}")
    
    while True:
        data, addr = sock.recvfrom(1024)
        sock.sendto(data, addr)


if __name__ == "__main__":
    main()
