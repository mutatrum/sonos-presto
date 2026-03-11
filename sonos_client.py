import usocket as socket
import ustruct as struct
import time
import ure as re
import io
import ssl

class Response:
    def __init__(self, status_code, content):
        self.status_code = status_code
        self.content = content
        self._text = None
        
    @property
    def text(self):
        if self._text is None:
            try:
                self._text = self.content.decode("utf-8")
            except:
                self._text = ""
        return self._text
        
    def close(self):
        pass

def http_request(method, url, data=None, headers=None):
    try:
        if "/" in url.replace("http://", "").replace("https://", ""):
             # handle http://host/path and https://host/path
             if url.startswith("http://"):
                 proto, dummy, host, path = url.split("/", 3)
             elif url.startswith("https://"):
                 proto, dummy, host, path = url.split("/", 3)
             else:
                 # Should not happen if filtered below, but for safety
                 if url.startswith("http"):
                     # maybe no path?
                     proto, dummy, host = url.split("/", 2)
                     path = ""
                 else:
                     raise ValueError("Unsupported protocol")
        else:
             if url.startswith("http://"):
                 proto, dummy, host = url.split("/", 2)
             elif url.startswith("https://"):
                 proto, dummy, host = url.split("/", 2)
             else:
                 raise ValueError("Unsupported protocol")
             path = ""
    except ValueError:
        # Fallback simplistic parsing
        if url.startswith("https://"):
             proto = "https:"
        else:
             proto = "http:"
        host = url
        path = ""
        
    if proto not in ("http:", "https:"):
        raise ValueError("Unsupported protocol: " + proto)

    if ":" in host:
        host, port_str = host.split(":", 1)
        port = int(port_str)
    else:
        if proto == "https:":
            port = 443
        else:
            port = 80

    s = socket.socket()
    s.settimeout(10.0) # Prevent infinite hangs
    try:
        ai = socket.getaddrinfo(host, port)
        addr = ai[0][-1]
        s.connect(addr)
        if proto == "https:":
            s = ssl.wrap_socket(s, server_hostname=host)
    except Exception as e:
        s.close()
        print(f"HTTP Connect Error ({host}:{port}): {e}")
        raise e
    
    s.write(b"%s /%s HTTP/1.1\r\n" % (method.encode(), path.encode()))
    s.write(b"Host: %s\r\n" % host.encode())
    
    if headers:
        for k, v in headers.items():
            s.write(b"%s: %s\r\n" % (k.encode(), v.encode()))
            
    if data:
        if isinstance(data, str):
            data = data.encode()
        s.write(b"Content-Length: %d\r\n" % len(data))
    
    s.write(b"\r\n")
    if data:
        s.write(data)

    line = s.readline()
    if not line:
        s.close()
        raise ValueError("No response")
        
    l = line.split(None, 2)
    # Handle older HTTP versions or weird responses? Basic split should work: HTTP/1.1 200 OK
    if len(l) < 2:
         s.close()
         raise ValueError("Invalid response: " + line.decode())
    status = int(l[1])
    
    headers_resp = {}
    chunked = False
    content_length = -1
    
    while True:
        line = s.readline()
        if not line or line == b"\r\n":
            break
        parts = line.decode().split(":", 1)
        if len(parts) == 2:
            key, val = parts
            headers_resp[key.lower()] = val.strip()
        
    if headers_resp.get("transfer-encoding", "").lower() == "chunked":
        chunked = True
    
    if "content-length" in headers_resp:
        content_length = int(headers_resp["content-length"])
        
    content = b""
    try:
        if chunked:
            while True:
                line = s.readline()
                if not line: 
                    break 
                # Chunk size is hex
                line_str = line.strip()
                if not line_str:
                     continue # empty line before chunk size?
                chunk_size = int(line_str, 16)
                if chunk_size == 0:
                    s.readline() # Consume last CRLF and ending
                    break
                # Read chunk data
                data_read = 0
                while data_read < chunk_size:
                    chunk = s.read(chunk_size - data_read)
                    if not chunk:
                        break
                    content += chunk
                    data_read += len(chunk)
                
                s.readline() # Consume trailing CRLF
        else:
            if content_length >= 0:
                data_read = 0
                while data_read < content_length:
                    chunk = s.read(content_length - data_read)
                    if not chunk:
                        break
                    content += chunk
                    data_read += len(chunk)
            else:
                # No content info, read until close
                while True:
                    chunk = s.read(1024)
                    if not chunk:
                        break
                    content += chunk
    except Exception as e:
        print(f"Error reading content: {e}")
    finally:
        s.close()

    if content is None:
        content = b""
        
    return Response(status, content)


class SonosDevice:
    def __init__(self, ip, port=1400):
        self.ip = ip
        self.port = port
        self.room_name = None
        self.udn = None

    def get_device_info(self):
        """Fetches device description to find room name and UDN (Rincon ID)."""
        url = f"http://{self.ip}:{self.port}/xml/device_description.xml"
        try:
            response = http_request("GET", url)
            if response.status_code == 200:
                xml = response.text
                # Simple regex for room name
                room_match = re.search(r"<roomName>(.*?)</roomName>", xml)
                if room_match:
                    self.room_name = room_match.group(1)
                
                # Simple regex for UDN (uuid:RINCON_...)
                udn_match = re.search(r"<UDN>(uuid:.*?)</UDN>", xml)
                if udn_match:
                    self.udn = udn_match.group(1)
                    
            response.close()
        except Exception as e:
            print(f"Error getting device info for {self.ip}: {e}")
        return self.room_name, self.udn

    def get_room_name(self):
        """Legacy helper, now uses get_device_info."""
        if self.room_name is None:
            self.get_device_info()
        return self.room_name

    def get_position_info(self):
        """Fetches current track info using AVTransport service."""
        endpoint = f"http://{self.ip}:{self.port}/MediaRenderer/AVTransport/Control"
        soap_action = '"urn:schemas-upnp-org:service:AVTransport:1#GetPositionInfo"'
        body = """<?xml version="1.0" encoding="utf-8"?>
        <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
          <s:Body>
            <u:GetPositionInfo xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
              <InstanceID>0</InstanceID>
            </u:GetPositionInfo>
          </s:Body>
        </s:Envelope>"""
        
        headers = {
            'Content-Type': 'text/xml; charset="utf-8"',
            'SOAPAction': soap_action
        }

        try:
            response = http_request("POST", endpoint, data=body, headers=headers)
            if response.status_code == 200:
                xml = response.text
                response.close()
                return self._parse_position_info(xml)
            response.close()
        except Exception as e:
            # print(f"Error getting position info: {e}")
            pass
        return None

    def _parse_position_info(self, xml):
        """Extracts TrackURI and TrackMetaData from response."""
        info = {}
        # Parse TrackMetaData (DIDL-Lite inside XML)
        # Note: XML in XML, standard UPnP mess
        meta_match = re.search(r"&lt;upnp:albumArtURI&gt;(.*?)&lt;/upnp:albumArtURI&gt;", xml)
        
        # Sometimes it might be directly in the response if not escaped, but usually it is escaped
        # Let's try basic regex for the escaped content
        if meta_match:
            uri = meta_match.group(1)
            # Unescape generic XML entities
            # We do it multiple times or specific replace because of the "XML within XML" (double escaping)
            # &amp;amp; -> &amp; -> &
            for _ in range(2):
                uri = uri.replace("&lt;", "<").replace("&gt;", ">").replace("&quot;", '"').replace("&apos;", "'").replace("&amp;", "&")
            
            info['album_art_uri'] = uri
            
        return info

    def get_transport_info(self):
        """Fetches current transport status (PLAYING, STOPPED, PAUSED_PLAYBACK, etc)."""
        endpoint = f"http://{self.ip}:{self.port}/MediaRenderer/AVTransport/Control"
        soap_action = '"urn:schemas-upnp-org:service:AVTransport:1#GetTransportInfo"'
        body = """<?xml version="1.0" encoding="utf-8"?>
        <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
          <s:Body>
            <u:GetTransportInfo xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
              <InstanceID>0</InstanceID>
            </u:GetTransportInfo>
          </s:Body>
        </s:Envelope>"""
        
        headers = {
            'Content-Type': 'text/xml; charset="utf-8"',
            'SOAPAction': soap_action
        }

        try:
            response = http_request("POST", endpoint, data=body, headers=headers)
            if response.status_code == 200:
                xml = response.text
                response.close()
                # Simple regex for CurrentTransportState
                match = re.search(r"<CurrentTransportState>(.*?)</CurrentTransportState>", xml)
                if match:
                    return match.group(1)
            response.close()
        except Exception as e:
            # print(f"Error getting transport info: {e}")
            pass
        return None

    def _send_av_cmd(self, action, params=None):
        """Helper to send basic AVTransport commands."""
        endpoint = f"http://{self.ip}:{self.port}/MediaRenderer/AVTransport/Control"
        soap_action = f'"urn:schemas-upnp-org:service:AVTransport:1#{action}"'
        
        args = f"<InstanceID>0</InstanceID>"
        if action == "Play":
             args += "<Speed>1</Speed>"
        if params:
             args += params
            
        body = f"""<?xml version="1.0" encoding="utf-8"?>
        <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
          <s:Body>
            <u:{action} xmlns:u="urn:schemas-upnp-org:service:AVTransport:1">
              {args}
            </u:{action}>
          </s:Body>
        </s:Envelope>"""
        
        headers = {
            'Content-Type': 'text/xml; charset="utf-8"',
            'SOAPAction': soap_action
        }
        try:
            response = http_request("POST", endpoint, data=body, headers=headers)
            response.close()
        except Exception as e:
            print(f"AV Cmd {action} error: {e}")

    def play(self):
        self._send_av_cmd("Play")

    def pause(self):
        self._send_av_cmd("Pause")

    def next(self):
        self._send_av_cmd("Next")

    def previous(self):
        self._send_av_cmd("Previous")

    def get_volume(self):
        endpoint = f"http://{self.ip}:{self.port}/MediaRenderer/RenderingControl/Control"
        soap_action = '"urn:schemas-upnp-org:service:RenderingControl:1#GetVolume"'
        body = """<?xml version="1.0" encoding="utf-8"?>
        <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
          <s:Body>
            <u:GetVolume xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1">
              <InstanceID>0</InstanceID>
              <Channel>Master</Channel>
            </u:GetVolume>
          </s:Body>
        </s:Envelope>"""
        
        headers = { 'Content-Type': 'text/xml; charset="utf-8"', 'SOAPAction': soap_action }
        try:
            response = http_request("POST", endpoint, data=body, headers=headers)
            if response.status_code == 200:
                xml = response.text
                response.close()
                match = re.search(r"<CurrentVolume>(.*?)</CurrentVolume>", xml)
                if match:
                    return int(match.group(1))
            response.close()
        except Exception as e:
            print(f"GetVolume error: {e}")
        return None

    def set_volume(self, volume):
        endpoint = f"http://{self.ip}:{self.port}/MediaRenderer/RenderingControl/Control"
        soap_action = '"urn:schemas-upnp-org:service:RenderingControl:1#SetVolume"'
        body = f"""<?xml version="1.0" encoding="utf-8"?>
        <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" s:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/">
          <s:Body>
            <u:SetVolume xmlns:u="urn:schemas-upnp-org:service:RenderingControl:1">
              <InstanceID>0</InstanceID>
              <Channel>Master</Channel>
              <DesiredVolume>{volume}</DesiredVolume>
            </u:SetVolume>
          </s:Body>
        </s:Envelope>"""
        
        headers = { 'Content-Type': 'text/xml; charset="utf-8"', 'SOAPAction': soap_action }
        try:
            http_request("POST", endpoint, data=body, headers=headers).close()
        except Exception as e:
            print(f"SetVolume error: {e}")

    def set_relative_volume(self, adjustment):
        vol = self.get_volume()
        if vol is not None:
            new_vol = max(0, min(100, vol + adjustment))
            print(f"Vol: {vol} -> {new_vol}")
            self.set_volume(new_vol)

    def get_album_art_jpeg(self, uri):
        """Downloads album art as bytes."""
        # URI is usually relative, e.g., /getaa?s=1&u=x-sonos-http%3a...
        if not uri.startswith("http"):
            url = f"http://{self.ip}:{self.port}{uri}"
        else:
            url = uri
            
        print(f"Fetching Art: {url}")
        try:
            # We use stream to save memory if possible, but jpegdec might need full buffer
            # On RP2350 (Presto) we have 8MB PSRAM, so buffering is fine.
            response = http_request("GET", url)
            if response.status_code == 200:
                data = response.content
                response.close()
                return data
            response.close()
        except Exception as e:
            print(f"Error fetching album art: {e}")
        return None


def discover_devices(timeout=2):
    """Sends SSDP discovery packet and returns list of SonosDevice IPs."""
    SSDP_ADDR = "239.255.255.250"
    SSDP_PORT = 1900
    SSDP_MX = 1
    SSDP_ST = "urn:schemas-upnp-org:device:ZonePlayer:1"

    msg = \
        'M-SEARCH * HTTP/1.1\r\n' \
        f'HOST: {SSDP_ADDR}:{SSDP_PORT}\r\n' \
        'MAN: "ssdp:discover"\r\n' \
        f'MX: {SSDP_MX}\r\n' \
        f'ST: {SSDP_ST}\r\n' \
        '\r\n'

    devices = set()
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.settimeout(timeout)
    
    try:
        # Send multiple discovery packets for reliability
        for _ in range(3):
            s.sendto(msg.encode(), (SSDP_ADDR, SSDP_PORT))
            time.sleep(0.1)
            
        start = time.time()
        while time.time() - start < timeout:
            try:
                data, addr = s.recvfrom(1024)
                # print(f"SSDP Response from {addr[0]}") # Debug
                devices.add(addr[0])
            except OSError:
                break # Timeout
    except Exception as e:
        print(f"Discovery Error: {e}")
    finally:
        s.close()
        
    return [SonosDevice(ip) for ip in devices]
