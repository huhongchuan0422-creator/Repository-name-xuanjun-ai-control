"""Client-origin trust boundary: only the pinned Nginx Unix peer can assert IP.
No forwarded chain is parsed; Nginx overwrites the one private header from its
verified effective remote_addr. Tests inject a separate fixture boundary.
"""
import ipaddress
import socket
import struct
from scripts.pr122_customer_core import Denied

HEADER='X-Xuanjun-Client-IP'
class TrustedNginxSource:
    def __init__(self,uid):
        if type(uid) is not int or uid<=0:raise ValueError('PINNED_NGINX_UID_REQUIRED')
        self.uid=uid
    def __call__(self,connection,headers):
        if connection.family!=socket.AF_UNIX:raise Denied('TRUSTED_UNIX_PROXY_REQUIRED')
        _,uid,_=struct.unpack('3i',connection.getsockopt(socket.SOL_SOCKET,socket.SO_PEERCRED,12))
        if uid!=self.uid:raise Denied('NGINX_PEER_REQUIRED')
        values=headers.get_all(HEADER,[])
        if len(values)!=1:raise Denied('SINGLE_PROXY_ORIGIN_REQUIRED')
        return normalize(values[0])

def normalize(value):
    if type(value) is not str or value!=value.strip() or '%' in value or ',' in value:raise Denied('INVALID_PROXY_ORIGIN')
    try:ip=ipaddress.ip_address(value)
    except ValueError:raise Denied('INVALID_PROXY_ORIGIN') from None
    if getattr(ip,'ipv4_mapped',None):ip=ip.ipv4_mapped
    # IPv6 privacy-address rotation within a subscriber prefix cannot reset quota.
    return str(ipaddress.ip_network(str(ip)+'/64',strict=False)) if ip.version==6 else str(ip)

def reject_untrusted(connection,headers):raise Denied('TRUSTED_PROXY_NOT_CONFIGURED')
