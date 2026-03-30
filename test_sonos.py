import sys
import socket
import struct
import re

# Shim for CPython to emulate MicroPython's usocket features (read/write on sockets)
class SocketWrapper:
    def __init__(self, s):
        self._s = s
        self._f = s.makefile('rwb')
    def connect(self, addr): self._s.connect(addr)
    def close(self): self._s.close()
    def write(self, data): self._s.sendall(data)
    def read(self, n=None): return self._f.read(n) if n else self._f.read()
    def readline(self): return self._f.readline()
    def settimeout(self, t): self._s.settimeout(t)

class socket_module:
    AF_INET = socket.AF_INET
    SOCK_DGRAM = socket.SOCK_DGRAM
    @staticmethod
    def socket(*args): 
        s = socket.socket(*args)
        if not args or len(args) < 2 or args[1] == socket.SOCK_STREAM:
            return SocketWrapper(s)
        return s
    @staticmethod
    def getaddrinfo(*args): 
        return socket.getaddrinfo(*args)

if sys.implementation.name != 'micropython':
    sys.modules['usocket'] = socket_module
    sys.modules['ustruct'] = struct
    sys.modules['ure'] = re

import sonos_client
import config

def main():
    print("Discovering Sonos devices...")
    devices = sonos_client.discover_devices()
    print(f"Discovered {len(devices)} devices")

    target = None
    for d in devices:
        try:
            name, udn = d.get_device_info()
            if name == getattr(config, 'ROOM_NAME', None) or name:
                if name == getattr(config, 'ROOM_NAME', None):
                    target = d
                    print(f"Room {name} found at {d.ip}")
                    break
        except Exception as e:
            print(f"Error connecting to {d.ip}: {e}")

    if not target:
        if devices:
            print(f"Target room '{getattr(config, 'ROOM_NAME', 'Unknown')}' not found, using first available device...")
            target = devices[0]
        else:
            print("No devices found!")
            sys.exit(1)

    state = target.get_transport_info()
    print(f"\nTransport State: {state}")

    info = target.get_position_info()
    print(f"Parsed Position Info: {info}")

    print("\nFetching raw XML for Position Info...")
    endpoint = f"http://{target.ip}:{target.port}/MediaRenderer/AVTransport/Control"
    soap_action = '"urn:schemas-upnp-org:service:AVTransport:1#GetPositionInfo"'
    body = """<?xml version="1.0" encoding="utf-8"?>
    <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
      <s:Body>
        <u:GetPositionInfo xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
          <InstanceID>0</InstanceID>
        </u:GetPositionInfo>
      </s:Body>
    </s:Envelope>"""
    headers = {'Content-Type': 'text/xml; charset="utf-8"', 'SOAPAction': soap_action}
    try:
        resp = sonos_client.http_request("POST", endpoint, data=body, headers=headers)
        print("\nRAW XML RESPONSE:")
        print(resp.text)
    except Exception as e:
        print(f"Error fetching raw XML: {e}")

    print("\nFetching raw XML for Media Info (for streams)...")
    endpoint = f"http://{target.ip}:{target.port}/MediaRenderer/AVTransport/Control"
    soap_action = '"urn:schemas-upnp-org:service:AVTransport:1#GetMediaInfo"'
    body = """<?xml version="1.0" encoding="utf-8"?>
    <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
      <s:Body>
        <u:GetMediaInfo xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
          <InstanceID>0</InstanceID>
        </u:GetMediaInfo>
      </s:Body>
    </s:Envelope>"""
    headers = {'Content-Type': 'text/xml; charset="utf-8"', 'SOAPAction': soap_action}
    try:
        resp = sonos_client.http_request("POST", endpoint, data=body, headers=headers)
        print("\nRAW XML MEDIA INFO RESPONSE:")
        print(resp.text)
    except Exception as e:
        print(f"Error fetching Media Info: {e}")

if __name__ == "__main__":
    main()
