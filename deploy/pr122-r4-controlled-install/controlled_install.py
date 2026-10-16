#!/usr/bin/python3 -I
"""Fixed R4 root action, preparation candidate only; no privilege registration.

Reuses the exact installed root-owned log-fix transaction engine in memory.
Never reads OAuth state, credentials or a business database.
"""
import ast
import base64
import fcntl
import errno
import hashlib
import http.client
import json
import os
from pathlib import Path
import socket
import ssl
import stat
import subprocess
import sys
import types

HOST = "iZ6wee8q9z4t03hvqumwfhZ"
HELPER = Path("/usr/local/sbin/xuanjun-pr122-portal-logfix-v1")
HELPER_SHA256 = "0e61a4cab72a18e94ed8b97c81e035ee023dfe0969c871c50651cf75792cbcbe"
STATE = Path("/var/lib/xuanjun-pr122-r4-containment")
SUMMARY = Path("/var/lib/xuanjun-pr122-r4-containment-receipt.json")
TARGET = Path("/opt/trading-system/scripts/secure_secrets_portal_server.py")
SOURCE_SHA256 = "d5ab592a6a23dd5ebfa8689c95aaa453e371127aab9a39bc2fe7eba0febbbdf0"
CANDIDATE_SHA256 = "57e38fc9c37d2811010b3170f672c4ba7b4877f2e27575b564131ed12adee1a1"
GUARD_SHA256 = "1afc01c6b19cb8bfc82c16eab257a06dd95b0420118dc6a0dc4726f25a0d6d93"
GUARD_B64 = "IiIiUjQgY29udGFpbm1lbnQgY2FuZGlkYXRlOiBkaXNhYmxlIHRoZSBsZWdhY3kgSFRUUCBkaXNjb25uZWN0IG9wZXJhdGlvbi4KClRoaXMgaXMgTk9UIGFuIGF1dGhlbnRpY2F0ZWQgZGlzY29ubmVjdCBpbXBsZW1lbnRhdGlvbiBvciBhIHByb2R1Y3Rpb24gaW5zdGFsbGVyLgpPbmx5IHRoZSBleGFjdCBkZXBsb3llZCBsZWdhY3kgc291cmNlIGlzIGFjY2VwdGVkOyBhbGwgb3RoZXIgYnl0ZXMgYXJlIHByZXNlcnZlZC4KIiIiCmltcG9ydCBoYXNobGliCgpTT1VSQ0VfU0hBMjU2ID0gImQ1YWI1OTJhNmEyM2RkNWViZmE4Njg5Yzk1YWFhNDUzZTM3MTEyN2FhYjlhMzliYzJmZTdlYmEwZmViYmJkZjAiCk9MRF9CUkFOQ0ggPSAnJycgICAgICAgIGlmIHBhcnNlZC5wYXRoID09IFRJS1RPS19ESVNDT05ORUNUX1BBVEg6CiAgICAgICAgICAgIHBheWxvYWQgPSBUaWtUb2tUb2tlbkxpZmVjeWNsZVN0b3JlKERFRkFVTFRfU1RBVEVfUk9PVCAvICJ0aWt0b2stdG9rZW4tc3RhdGUiKS5kaXNjb25uZWN0KCkKICAgICAgICAgICAgc2VsZi5zZXJ2ZXIucG9ydGFsX3NlcnZpY2Uub3BlcmF0aW9uc19zdG9yZS5yZWNvcmRfYXVkaXQoewogICAgICAgICAgICAgICAgIm9wZXJhdGlvbiI6ICJUSUtUT0tfRElTQ09OTkVDVCIsCiAgICAgICAgICAgICAgICAicHJvdmlkZXIiOiAidGlrdG9rIiwKICAgICAgICAgICAgICAgICJyZXN1bHQiOiAiUEFTUyIsCiAgICAgICAgICAgICAgICAic2VjcmV0X3ZhbHVlX2V4cG9zZWQiOiBGYWxzZSwKICAgICAgICAgICAgfSkKICAgICAgICAgICAgc2VsZi5fc2VuZChIVFRQU3RhdHVzLk9LLCBqc29uLmR1bXBzKHBheWxvYWQsIGVuc3VyZV9hc2NpaT1UcnVlLCBzb3J0X2tleXM9VHJ1ZSkgKyAiXFxuIiwgY29udGVudF90eXBlPSJhcHBsaWNhdGlvbi9qc29uOyBjaGFyc2V0PXV0Zi04IikKICAgICAgICAgICAgcmV0dXJuCicnJwpORVdfQlJBTkNIID0gJycnICAgICAgICBpZiBwYXJzZWQucGF0aCA9PSBUSUtUT0tfRElTQ09OTkVDVF9QQVRIOgogICAgICAgICAgICBzeXMuc3RkZXJyLndyaXRlKCJzZWN1cml0eV9ldmVudD1USUtUT0tfRElTQ09OTkVDVF9IVFRQX0RFTklFRFxcbiIpCiAgICAgICAgICAgIHNlbGYuX3NlbmQoSFRUUFN0YXR1cy5GT1JCSURERU4sIGpzb24uZHVtcHMoewogICAgICAgICAgICAgICAgInN0YXR1cyI6ICJSRUpFQ1RFRCIsCiAgICAgICAgICAgICAgICAic2FuaXRpemVkX2Vycm9yX2NvZGUiOiAiRElTQ09OTkVDVF9ESVNBQkxFRF9BVVRIX05PVF9JTlRFR1JBVEVEIiwKICAgICAgICAgICAgICAgICJvcGVyYXRpb25fcGVyZm9ybWVkIjogRmFsc2UsCiAgICAgICAgICAgIH0sIGVuc3VyZV9hc2NpaT1UcnVlLCBzb3J0X2tleXM9VHJ1ZSkgKyAiXFxuIiwgY29udGVudF90eXBlPSJhcHBsaWNhdGlvbi9qc29uOyBjaGFyc2V0PXV0Zi04IikKICAgICAgICAgICAgcmV0dXJuCicnJwoKCmRlZiBidWlsZF9jYW5kaWRhdGUoc291cmNlKToKICAgIGlmIG5vdCBpc2luc3RhbmNlKHNvdXJjZSwgYnl0ZXMpOgogICAgICAgIHJhaXNlIFR5cGVFcnJvcigiU09VUkNFX0JZVEVTX1JFUVVJUkVEIikKICAgIGlmIGhhc2hsaWIuc2hhMjU2KHNvdXJjZSkuaGV4ZGlnZXN0KCkgIT0gU09VUkNFX1NIQTI1NjoKICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJTT1VSQ0VfU0hBMjU2X01JU01BVENIIikKICAgIG9sZCwgbmV3ID0gT0xEX0JSQU5DSC5lbmNvZGUoKSwgTkVXX0JSQU5DSC5lbmNvZGUoKQogICAgaWYgc291cmNlLmNvdW50KG9sZCkgIT0gMToKICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJVTklRVUVfRElTQ09OTkVDVF9CUkFOQ0hfUkVRVUlSRUQiKQogICAgcmV0dXJuIHNvdXJjZS5yZXBsYWNlKG9sZCwgbmV3LCAxKQo="
UNIT = "secure-secrets-portal.service"
GATE_SHA256 = "d869a2f9770e4a8bf6fb863b94abb13edcf461c3b0b39477a2d721201cdbb435"
GATE_B64 = "IiIiSTEgYWRtaXNzaW9uOiBPd25lci1waW5uZWQgaW5kZXBlbmRlbnQgcmVjZWlwdCArIGNhbm9uaWNhbCBHaXRIdWIgZmFjdHMuCgpHaXRIdWIgZGV2ZWxvcGVyL3Jldmlld2VyIHNoYXJlIGFuIGFjY291bnQvQXBwLiBQcm92ZW5hbmNlIGFsb25lIGNhbm5vdCBwcm92ZQppbmRlcGVuZGVuY2U6IGEgc2VwYXJhdGUgT3duZXItcm9vdCBwaW4gb2YgdGhlIGluZGVwZW5kZW50bHkgcmVjZWl2ZWQgYm9keSBoYXNoCmlzIG1hbmRhdG9yeS4gVGhpcyBtb2R1bGUgbmV2ZXIgY3JlYXRlcyB0aGF0IHRydXN0IGFuY2hvciBvciBhbiBhcHByb3ZhbC4KIiIiCmltcG9ydCBiYXNlNjQKZnJvbSBkYXRldGltZSBpbXBvcnQgZGF0ZXRpbWUKaW1wb3J0IGhhc2hsaWIKaW1wb3J0IGpzb24KaW1wb3J0IG9zCmZyb20gcGF0aGxpYiBpbXBvcnQgUGF0aAppbXBvcnQgcmUKaW1wb3J0IHNzbAppbXBvcnQgc3RhdAppbXBvcnQgdGltZQppbXBvcnQgdXJsbGliLnJlcXVlc3QKClJFUE8gPSAiaHVob25nY2h1YW4wNDIyLWNyZWF0b3IvUmVwb3NpdG9yeS1uYW1lLXh1YW5qdW4tYWktY29udHJvbCIKSE9TVCA9ICJpWjZ3ZWU4cTl6NHQwM2h2cXVtd2ZoWiIKQVVUSE9SX0lEID0gMzMyMzk4OTA4CkFQUF9JRCA9IDExNDQ5OTUKSU5TVEFMTEVSX1BBVEggPSAiZGVwbG95L3ByMTIyLXI0LWNvbnRyb2xsZWQtaW5zdGFsbC9jb250cm9sbGVkX2luc3RhbGwucHkiCkJJTkRJTkdfUEFUSCA9ICJkZXBsb3kvcHIxMjItcjQtY29udHJvbGxlZC1pbnN0YWxsL1JFVklFV19CSU5ESU5HLmpzb24iClNPVVJDRV9TSEEgPSAiZDVhYjU5MmE2YTIzZGQ1ZWJmYTg2ODljOTVhYWE0NTNlMzcxMTI3YWFiOWEzOWJjMmZlN2ViYTBmZWJiYmRmMCIKQ0FORElEQVRFX1NIQSA9ICI1N2UzOGZjOWMzN2QyODExMDEwYjMxNzBmNjcyYzRiYTdiNDg3N2YyZTI3NTc1YjU2NDEzMWVkMTJhZGVlMWExIgpIRUxQRVJfU0hBID0gIjBlNjFhNGNhYjcyYTE4ZTk0ZWQ4Yjk3YzgxZTAzNWVlMDIzZGZlMDk2OWM4NzFjNTA2NTFjZjc1NzkyY2JjYmUiCkJFR0lOID0gIjwhLS0gUFIxMjJfUjRfQUNUSU9OX0FQUFJPVkFMX1YxXG4iCkVORCA9ICJcblBSMTIyX1I0X0FDVElPTl9BUFBST1ZBTF9WMSAtLT4iCkVGRkVDVFMgPSB7CiAgICAiaW5zdGFsbCI6IFsiYmFja3VwX3NpbmdsZV9zb3VyY2UiLCAid3JpdGVfc2luZ2xlX3NvdXJjZSIsICJyZXN0YXJ0X3BvcnRhbF9vbmNlIiwgImVtcHR5X25lZ2F0aXZlX3Bvc3RfNCJdLAogICAgInJvbGxiYWNrLW9mZmxpbmUiOiBbInN0b3BfcG9ydGFsIiwgInJlc3RvcmVfc2luZ2xlX3NvdXJjZV9vZmZsaW5lIiwgImtlZXBfcG9ydGFsX3N0b3BwZWQiXSwKfQpfU0VBTCA9IG9iamVjdCgpCgoKZGVmIHN0cmljdF9qc29uKGRhdGEpOgogICAgZGVmIHBhaXJzKGl0ZW1zKToKICAgICAgICByZXN1bHQgPSB7fQogICAgICAgIGZvciBrZXksIHZhbHVlIGluIGl0ZW1zOgogICAgICAgICAgICBpZiBrZXkgaW4gcmVzdWx0OgogICAgICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcigiRFVQTElDQVRFX0pTT05fS0VZIikKICAgICAgICAgICAgcmVzdWx0W2tleV0gPSB2YWx1ZQogICAgICAgIHJldHVybiByZXN1bHQKICAgIGRlZiBpbnZhbGlkKHZhbHVlKToKICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJOT05GSU5JVEVfSlNPTiIpCiAgICByZXR1cm4ganNvbi5sb2FkcyhkYXRhLCBvYmplY3RfcGFpcnNfaG9vaz1wYWlycywgcGFyc2VfY29uc3RhbnQ9aW52YWxpZCkKCgpkZWYgcm9vdF9maWxlKHBhdGgsIG1vZGUsIGxpbWl0KToKICAgIGZkID0gb3Mub3BlbihwYXRoLCBvcy5PX1JET05MWSB8IG9zLk9fTk9GT0xMT1cpCiAgICB3aXRoIG9zLmZkb3BlbihmZCwgInJiIikgYXMgaGFuZGxlOgogICAgICAgIGluZm8gPSBvcy5mc3RhdChoYW5kbGUuZmlsZW5vKCkpCiAgICAgICAgaWYgKG5vdCBzdGF0LlNfSVNSRUcoaW5mby5zdF9tb2RlKSBvciBpbmZvLnN0X3VpZCAhPSAwIG9yIGluZm8uc3RfbmxpbmsgIT0gMQogICAgICAgICAgICAgICAgb3Igc3RhdC5TX0lNT0RFKGluZm8uc3RfbW9kZSkgIT0gbW9kZSk6CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoIlJPT1RfQURNSVNTSU9OX0ZJTEVfSURFTlRJVFkiKQogICAgICAgIGRhdGEgPSBoYW5kbGUucmVhZChsaW1pdCArIDEpCiAgICAgICAgaWYgbGVuKGRhdGEpID4gbGltaXQ6CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoIkFETUlTU0lPTl9TSVpFX0xJTUlUIikKICAgICAgICByZXR1cm4gZGF0YQoKCmRlZiByb290X3BhcmVudChwYXRoKToKICAgIGluZm8gPSBwYXRoLmxzdGF0KCkKICAgIGlmIG5vdCBzdGF0LlNfSVNESVIoaW5mby5zdF9tb2RlKSBvciBpbmZvLnN0X3VpZCAhPSAwIG9yIHN0YXQuU19JTU9ERShpbmZvLnN0X21vZGUpICE9IDBvNzAwOgogICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoIlJPT1RfQURNSVNTSU9OX1BBUkVOVF9JREVOVElUWSIpCgoKY2xhc3MgTm9SZWRpcmVjdCh1cmxsaWIucmVxdWVzdC5IVFRQUmVkaXJlY3RIYW5kbGVyKToKICAgIGRlZiByZWRpcmVjdF9yZXF1ZXN0KHNlbGYsICphcmdzLCAqKmt3YXJncyk6CiAgICAgICAgcmFpc2UgVmFsdWVFcnJvcigiR0lUSFVCX1JFRElSRUNUX1JFSkVDVEVEIikKCgpkZWYgZ2l0aHViX2pzb24ocGF0aCk6CiAgICBpZiBub3QgcGF0aC5zdGFydHN3aXRoKCIvcmVwb3MvIiArIFJFUE8gKyAiLyIpIG9yICIuLiIgaW4gcGF0aDoKICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJDQU5PTklDQUxfR0lUSFVCX1BBVEhfUkVRVUlSRUQiKQogICAgdXJsID0gImh0dHBzOi8vYXBpLmdpdGh1Yi5jb20iICsgcGF0aAogICAgb3BlbmVyID0gdXJsbGliLnJlcXVlc3QuYnVpbGRfb3BlbmVyKHVybGxpYi5yZXF1ZXN0LlByb3h5SGFuZGxlcih7fSksCiAgICAgICAgdXJsbGliLnJlcXVlc3QuSFRUUFNIYW5kbGVyKGNvbnRleHQ9c3NsLmNyZWF0ZV9kZWZhdWx0X2NvbnRleHQoKSksIE5vUmVkaXJlY3QoKSkKICAgIHJlcXVlc3QgPSB1cmxsaWIucmVxdWVzdC5SZXF1ZXN0KHVybCwgaGVhZGVycz17IlVzZXItQWdlbnQiOiAiUFIxMjItUjQtQWRtaXNzaW9uLVYxIiwgIkFjY2VwdCI6ICJhcHBsaWNhdGlvbi92bmQuZ2l0aHViK2pzb24ifSkKICAgIHdpdGggb3BlbmVyLm9wZW4ocmVxdWVzdCwgdGltZW91dD0xMCkgYXMgcmVzcG9uc2U6CiAgICAgICAgaWYgcmVzcG9uc2UuZ2V0dXJsKCkgIT0gdXJsIG9yIHJlc3BvbnNlLnN0YXR1cyAhPSAyMDA6CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoIkNBTk9OSUNBTF9HSVRIVUJfUkVTUE9OU0VfUkVRVUlSRUQiKQogICAgICAgIGRhdGEgPSByZXNwb25zZS5yZWFkKDI2MjE0NSkKICAgIGlmIGxlbihkYXRhKSA+IDI2MjE0NDoKICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJHSVRIVUJfUkVTUE9OU0VfU0laRV9MSU1JVCIpCiAgICByZXR1cm4gc3RyaWN0X2pzb24oZGF0YSkKCgpkZWYgaW50ZWdlcih2YWx1ZSwgbWluaW11bT0xKToKICAgIHJldHVybiB0eXBlKHZhbHVlKSBpcyBpbnQgYW5kIHZhbHVlID49IG1pbmltdW0KCgpjbGFzcyBHYXRlOgogICAgZGVmIF9faW5pdF9fKHNlbGYsIGFjdGlvbiwgc2VsZl9wYXRoLCAqLCBhbmNob3I9Tm9uZSwgcmVnaXN0cnk9Tm9uZSwKICAgICAgICAgICAgICAgICBmZXRjaD1naXRodWJfanNvbiwgY2xvY2s9dGltZS50aW1lKToKICAgICAgICBpZiBhY3Rpb24gbm90IGluIEVGRkVDVFM6CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoIlVOUkVHSVNURVJFRF9BQ1RJT04iKQogICAgICAgIHNlbGYuYWN0aW9uLCBzZWxmLnNlbGZfcGF0aCA9IGFjdGlvbiwgUGF0aChzZWxmX3BhdGgpCiAgICAgICAgc2VsZi5hbmNob3IgPSBQYXRoKGFuY2hvcikgaWYgYW5jaG9yIGVsc2UgUGF0aCgiL2V0Yy94dWFuanVuLXByMTIyLXJlbGVhc2UvIiArIGFjdGlvbiArICItYWRtaXNzaW9uLmpzb24iKQogICAgICAgIHNlbGYucmVnaXN0cnkgPSBQYXRoKHJlZ2lzdHJ5KSBpZiByZWdpc3RyeSBlbHNlIFBhdGgoIi92YXIvbGliL3h1YW5qdW4tcHIxMjItYXV0aG9yaXphdGlvbnMiKQogICAgICAgIHNlbGYuZmV0Y2gsIHNlbGYuY2xvY2sgPSBmZXRjaCwgY2xvY2sKCiAgICBkZWYgZ2V0KHNlbGYsIHN1ZmZpeCk6CiAgICAgICAgaWYgc2VsZi5jbG9jaygpIC0gc2VsZi5zdGFydGVkID4gNjA6CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoIkFQUFJPVkFMX1ZBTElEQVRJT05fREVBRExJTkUiKQogICAgICAgIHJldHVybiBzZWxmLmZldGNoKCIvcmVwb3MvIiArIFJFUE8gKyBzdWZmaXgpCgogICAgZGVmIHZhbGlkYXRlKHNlbGYpOgogICAgICAgIHNlbGYuc3RhcnRlZCA9IHNlbGYuY2xvY2soKQogICAgICAgIGlmIG9zLmdldGV1aWQoKSAhPSAwIG9yIG9zLnVuYW1lKCkubm9kZW5hbWUgIT0gSE9TVDoKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcigiUk9PVF9PTl9BUFBST1ZFRF9IT1NUX1JFUVVJUkVEIikKICAgICAgICByb290X3BhcmVudChzZWxmLmFuY2hvci5wYXJlbnQpCiAgICAgICAgYW5jaG9yX2RhdGEgPSByb290X2ZpbGUoc2VsZi5hbmNob3IsIDBvNjAwLCAxNjM4NCkKICAgICAgICBwaW4gPSBzdHJpY3RfanNvbihhbmNob3JfZGF0YSkKICAgICAgICBleHBlY3RlZF9waW5fa2V5cyA9IHsic2NoZW1hX3ZlcnNpb24iLCAiYWN0aW9uIiwgImFwcHJvdmFsX2NvbW1lbnRfaWQiLCAiYXBwcm92YWxfYm9keV9zaGEyNTYiLCAib3duZXJfYXR0ZXN0c19pbmRlcGVuZGVudF9yZXZpZXciLCAib3duZXJfY29uZmlybXNfYmFja2VuZF9vdXRhZ2UifQogICAgICAgIGlmIChzZXQocGluKSAhPSBleHBlY3RlZF9waW5fa2V5cyBvciB0eXBlKHBpblsic2NoZW1hX3ZlcnNpb24iXSkgaXMgbm90IGludCBvciBwaW5bInNjaGVtYV92ZXJzaW9uIl0gIT0gMQogICAgICAgICAgICAgICAgb3IgcGluWyJhY3Rpb24iXSAhPSBzZWxmLmFjdGlvbiBvciBwaW5bIm93bmVyX2F0dGVzdHNfaW5kZXBlbmRlbnRfcmV2aWV3Il0gaXMgbm90IFRydWUKICAgICAgICAgICAgICAgIG9yIHBpblsib3duZXJfY29uZmlybXNfYmFja2VuZF9vdXRhZ2UiXSBpcyBub3QgKHNlbGYuYWN0aW9uID09ICJyb2xsYmFjay1vZmZsaW5lIikKICAgICAgICAgICAgICAgIG9yIG5vdCBpbnRlZ2VyKHBpblsiYXBwcm92YWxfY29tbWVudF9pZCJdKQogICAgICAgICAgICAgICAgb3Igbm90IHJlLmZ1bGxtYXRjaChyIlswLTlhLWZdezY0fSIsIHN0cihwaW5bImFwcHJvdmFsX2JvZHlfc2hhMjU2Il0pKSk6CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoIk9XTkVSX1BJTl9SRVFVSVJFRCIpCiAgICAgICAgaWRlbnRpZmllciA9IHBpblsiYXBwcm92YWxfY29tbWVudF9pZCJdCiAgICAgICAgbWFya2VyID0gc2VsZi5yZWdpc3RyeSAvICgiYXBwcm92YWwtIiArIHN0cihpZGVudGlmaWVyKSArICIuY29uc3VtZWQuanNvbiIpCiAgICAgICAgaWYgb3MucGF0aC5sZXhpc3RzKG1hcmtlcik6CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoIkFQUFJPVkFMX0FMUkVBRFlfQ09OU1VNRUQiKQogICAgICAgIGNvbW1lbnQgPSBzZWxmLmdldCgiL2lzc3Vlcy9jb21tZW50cy8iICsgc3RyKGlkZW50aWZpZXIpKQogICAgICAgIGlmIChjb21tZW50LmdldCgiaWQiKSAhPSBpZGVudGlmaWVyCiAgICAgICAgICAgICAgICBvciBjb21tZW50LmdldCgiaXNzdWVfdXJsIikgIT0gImh0dHBzOi8vYXBpLmdpdGh1Yi5jb20vcmVwb3MvIiArIFJFUE8gKyAiL2lzc3Vlcy8xMjIiCiAgICAgICAgICAgICAgICBvciBjb21tZW50LmdldCgidXNlciIsIHt9KS5nZXQoImlkIikgIT0gQVVUSE9SX0lECiAgICAgICAgICAgICAgICBvciAoY29tbWVudC5nZXQoInBlcmZvcm1lZF92aWFfZ2l0aHViX2FwcCIpIG9yIHt9KS5nZXQoImlkIikgIT0gQVBQX0lEKToKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcigiQVBQUk9WQUxfUFJPVkVOQU5DRV9NSVNNQVRDSCIpCiAgICAgICAgYm9keSA9IGNvbW1lbnQuZ2V0KCJib2R5IiwgIiIpCiAgICAgICAgaWYgbm90IGlzaW5zdGFuY2UoYm9keSwgc3RyKSBvciBoYXNobGliLnNoYTI1Nihib2R5LmVuY29kZSgpKS5oZXhkaWdlc3QoKSAhPSBwaW5bImFwcHJvdmFsX2JvZHlfc2hhMjU2Il06CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoIlBJTk5FRF9BUFBST1ZBTF9CT0RZX01JU01BVENIIikKICAgICAgICBpZiBib2R5LmNvdW50KEJFR0lOKSAhPSAxIG9yIGJvZHkuY291bnQoRU5EKSAhPSAxOgogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJFWFBMSUNJVF9BQ1RJT05fQVBQUk9WQUxfUkVRVUlSRUQiKQogICAgICAgIHZhbHVlID0gc3RyaWN0X2pzb24oYm9keS5zcGxpdChCRUdJTilbMV0uc3BsaXQoRU5EKVswXSkKICAgICAgICBrZXlzID0geyJzY2hlbWFfdmVyc2lvbiIsICJraW5kIiwgImRlY2lzaW9uIiwgInJldmlld2VyX3JvbGUiLCAicmVwb3NpdG9yeSIsICJwcl9udW1iZXIiLCAiaG9zdCIsICJhY3Rpb24iLCAibWF4X2F0dGVtcHRzIiwgInNvdXJjZV9jb21taXQiLCAic291cmNlX3RyZWUiLCAiaW5zdGFsbGVyX3NoYTI1NiIsICJiaW5kaW5nX3NoYTI1NiIsICJhcnRpZmFjdF9pZCIsICJhcnRpZmFjdF96aXBfc2hhMjU2IiwgImFydGlmYWN0X3Rhcl9zaGEyNTYiLCAiZXhwZWN0ZWRfc291cmNlX3NoYTI1NiIsICJyZXN1bHRfc291cmNlX3NoYTI1NiIsICJoZWxwZXJfc2hhMjU2IiwgImFsbG93ZWRfZWZmZWN0cyIsICJuZWdhdGl2ZV9wb3N0X3JlcXVlc3RzX21heCIsICJpc3N1ZWRfYXQiLCAiZXhwaXJlc19hdCIsICJhcHByb3ZhbF9ub25jZSJ9CiAgICAgICAgaWYgKHNldCh2YWx1ZSkgIT0ga2V5cyBvciB0eXBlKHZhbHVlWyJzY2hlbWFfdmVyc2lvbiJdKSBpcyBub3QgaW50IG9yIHZhbHVlWyJzY2hlbWFfdmVyc2lvbiJdICE9IDEKICAgICAgICAgICAgICAgIG9yIHZhbHVlWyJraW5kIl0gIT0gIlBSMTIyX1I0X0FDVElPTl9BUFBST1ZBTCIKICAgICAgICAgICAgICAgIG9yIHZhbHVlWyJkZWNpc2lvbiJdICE9ICJBUFBST1ZFRF9FWEFDVF9PTkVfQVRURU1QVCIKICAgICAgICAgICAgICAgIG9yIHZhbHVlWyJyZXZpZXdlcl9yb2xlIl0gIT0gIklOREVQRU5ERU5UX0FVRElUT1IiCiAgICAgICAgICAgICAgICBvciB2YWx1ZVsicmVwb3NpdG9yeSJdICE9IFJFUE8gb3IgdmFsdWVbInByX251bWJlciJdICE9IDEyMgogICAgICAgICAgICAgICAgb3IgdmFsdWVbImhvc3QiXSAhPSBIT1NUIG9yIHZhbHVlWyJhY3Rpb24iXSAhPSBzZWxmLmFjdGlvbgogICAgICAgICAgICAgICAgb3IgdHlwZSh2YWx1ZVsibWF4X2F0dGVtcHRzIl0pIGlzIG5vdCBpbnQgb3IgdmFsdWVbIm1heF9hdHRlbXB0cyJdICE9IDEKICAgICAgICAgICAgICAgIG9yIHZhbHVlWyJhbGxvd2VkX2VmZmVjdHMiXSAhPSBFRkZFQ1RTW3NlbGYuYWN0aW9uXQogICAgICAgICAgICAgICAgb3IgdHlwZSh2YWx1ZVsibmVnYXRpdmVfcG9zdF9yZXF1ZXN0c19tYXgiXSkgaXMgbm90IGludAogICAgICAgICAgICAgICAgb3IgdmFsdWVbIm5lZ2F0aXZlX3Bvc3RfcmVxdWVzdHNfbWF4Il0gIT0gKDQgaWYgc2VsZi5hY3Rpb24gPT0gImluc3RhbGwiIGVsc2UgMCkpOgogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJFWEFDVF9BUFBST1ZBTF9TQ09QRV9SRVFVSVJFRCIpCiAgICAgICAgZm9yIGtleSBpbiAoInNvdXJjZV9jb21taXQiLCAic291cmNlX3RyZWUiKToKICAgICAgICAgICAgaWYgbm90IHJlLmZ1bGxtYXRjaChyIlswLTlhLWZdezQwfSIsIHN0cih2YWx1ZVtrZXldKSk6CiAgICAgICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJBUFBST1ZBTF9DT01NSVRfVFJFRV9GT1JNQVQiKQogICAgICAgIGZvciBrZXkgaW4gKCJpbnN0YWxsZXJfc2hhMjU2IiwgImJpbmRpbmdfc2hhMjU2IiwgImFydGlmYWN0X3ppcF9zaGEyNTYiLCAiYXJ0aWZhY3RfdGFyX3NoYTI1NiIpOgogICAgICAgICAgICBpZiBub3QgcmUuZnVsbG1hdGNoKHIiWzAtOWEtZl17NjR9Iiwgc3RyKHZhbHVlW2tleV0pKToKICAgICAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoIkFQUFJPVkFMX0RJR0VTVF9GT1JNQVQiKQogICAgICAgIG9sZCwgbmV3ID0gKFNPVVJDRV9TSEEsIENBTkRJREFURV9TSEEpIGlmIHNlbGYuYWN0aW9uID09ICJpbnN0YWxsIiBlbHNlIChDQU5ESURBVEVfU0hBLCBTT1VSQ0VfU0hBKQogICAgICAgIGlmICh2YWx1ZVsiZXhwZWN0ZWRfc291cmNlX3NoYTI1NiJdICE9IG9sZCBvciB2YWx1ZVsicmVzdWx0X3NvdXJjZV9zaGEyNTYiXSAhPSBuZXcKICAgICAgICAgICAgICAgIG9yIHZhbHVlWyJoZWxwZXJfc2hhMjU2Il0gIT0gSEVMUEVSX1NIQQogICAgICAgICAgICAgICAgb3Igbm90IHJlLmZ1bGxtYXRjaChyIlswLTlhLWZdezMyfSIsIHN0cih2YWx1ZVsiYXBwcm92YWxfbm9uY2UiXSkpKToKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcigiU09VUkNFX09SX0FDVElPTl9CSU5ESU5HX01JU01BVENIIikKICAgICAgICBub3cgPSBzZWxmLmNsb2NrKCkKICAgICAgICBjcmVhdGVkID0gZGF0ZXRpbWUuZnJvbWlzb2Zvcm1hdChjb21tZW50WyJjcmVhdGVkX2F0Il0ucmVwbGFjZSgiWiIsICIrMDA6MDAiKSkudGltZXN0YW1wKCkKICAgICAgICBpZiAobm90IGludGVnZXIodmFsdWVbImlzc3VlZF9hdCJdLCAwKSBvciBub3QgaW50ZWdlcih2YWx1ZVsiZXhwaXJlc19hdCJdLCAwKQogICAgICAgICAgICAgICAgb3IgYWJzKHZhbHVlWyJpc3N1ZWRfYXQiXSAtIGNyZWF0ZWQpID4gNjAgb3Igbm93IDwgdmFsdWVbImlzc3VlZF9hdCJdCiAgICAgICAgICAgICAgICBvciBub3cgPj0gdmFsdWVbImV4cGlyZXNfYXQiXSBvciBub3QgMCA8IHZhbHVlWyJleHBpcmVzX2F0Il0gLSB2YWx1ZVsiaXNzdWVkX2F0Il0gPD0gODY0MDApOgogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJBUFBST1ZBTF9FWFBJUkVEX09SX05PVF9DVVJSRU5UIikKICAgICAgICBvd24gPSByb290X2ZpbGUoc2VsZi5zZWxmX3BhdGgsIDBvNDAwLCAyMDAwMDApCiAgICAgICAgaWYgaGFzaGxpYi5zaGEyNTYob3duKS5oZXhkaWdlc3QoKSAhPSB2YWx1ZVsiaW5zdGFsbGVyX3NoYTI1NiJdOgogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJJTlNUQUxMRVJfSEFTSF9OT1RfQVBQUk9WRUQiKQogICAgICAgIGNvbW1pdCA9IHNlbGYuZ2V0KCIvZ2l0L2NvbW1pdHMvIiArIHZhbHVlWyJzb3VyY2VfY29tbWl0Il0pCiAgICAgICAgaWYgY29tbWl0LmdldCgic2hhIikgIT0gdmFsdWVbInNvdXJjZV9jb21taXQiXSBvciBjb21taXQuZ2V0KCJ0cmVlIiwge30pLmdldCgic2hhIikgIT0gdmFsdWVbInNvdXJjZV90cmVlIl06CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoIkFQUFJPVkVEX0NPTU1JVF9UUkVFX01JU01BVENIIikKICAgICAgICBkZWYgY29udGVudChwYXRoKToKICAgICAgICAgICAgZW50cnkgPSBzZWxmLmdldCgiL2NvbnRlbnRzLyIgKyBwYXRoICsgIj9yZWY9IiArIHZhbHVlWyJzb3VyY2VfY29tbWl0Il0pCiAgICAgICAgICAgIGlmIGVudHJ5LmdldCgidHlwZSIpICE9ICJmaWxlIiBvciBlbnRyeS5nZXQoInBhdGgiKSAhPSBwYXRoIG9yIGVudHJ5LmdldCgiZW5jb2RpbmciKSAhPSAiYmFzZTY0IjoKICAgICAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoIkFQUFJPVkVEX0ZJTEVfQklORElOR19NSVNNQVRDSCIpCiAgICAgICAgICAgIHJldHVybiBiYXNlNjQuYjY0ZGVjb2RlKCIiLmpvaW4oZW50cnlbImNvbnRlbnQiXS5zcGxpdCgpKSwgdmFsaWRhdGU9VHJ1ZSkKICAgICAgICBpZiBjb250ZW50KElOU1RBTExFUl9QQVRIKSAhPSBvd246CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoIklOU1RBTExFUl9DT01NSVRfQllURVNfTUlTTUFUQ0giKQogICAgICAgIGJpbmRpbmdfZGF0YSA9IGNvbnRlbnQoQklORElOR19QQVRIKQogICAgICAgIGJpbmRpbmcgPSBzdHJpY3RfanNvbihiaW5kaW5nX2RhdGEpCiAgICAgICAgaWYgKGhhc2hsaWIuc2hhMjU2KGJpbmRpbmdfZGF0YSkuaGV4ZGlnZXN0KCkgIT0gdmFsdWVbImJpbmRpbmdfc2hhMjU2Il0KICAgICAgICAgICAgICAgIG9yIGJpbmRpbmcuZ2V0KCJmaWxlcyIsIHt9KS5nZXQoSU5TVEFMTEVSX1BBVEgpICE9IHZhbHVlWyJpbnN0YWxsZXJfc2hhMjU2Il0pOgogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJBUFBST1ZBTF9NQU5JRkVTVF9NSVNNQVRDSCIpCiAgICAgICAgaWYgbm90IGludGVnZXIodmFsdWVbImFydGlmYWN0X2lkIl0pOgogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJBUFBST1ZBTF9BUlRJRkFDVF9JRCIpCiAgICAgICAgYXJ0aWZhY3QgPSBzZWxmLmdldCgiL2FjdGlvbnMvYXJ0aWZhY3RzLyIgKyBzdHIodmFsdWVbImFydGlmYWN0X2lkIl0pKQogICAgICAgIHJ1biA9IGFydGlmYWN0LmdldCgid29ya2Zsb3dfcnVuIiwge30pCiAgICAgICAgaWYgKGFydGlmYWN0LmdldCgiaWQiKSAhPSB2YWx1ZVsiYXJ0aWZhY3RfaWQiXSBvciBhcnRpZmFjdC5nZXQoImV4cGlyZWQiKSBpcyBub3QgRmFsc2UKICAgICAgICAgICAgICAgIG9yIGFydGlmYWN0LmdldCgiZGlnZXN0IikgIT0gInNoYTI1NjoiICsgdmFsdWVbImFydGlmYWN0X3ppcF9zaGEyNTYiXQogICAgICAgICAgICAgICAgb3IgcnVuLmdldCgiaGVhZF9zaGEiKSAhPSB2YWx1ZVsic291cmNlX2NvbW1pdCJdCiAgICAgICAgICAgICAgICBvciBydW4uZ2V0KCJyZXBvc2l0b3J5X2lkIikgIT0gMTQxMzEzMjE1OSBvciBydW4uZ2V0KCJoZWFkX3JlcG9zaXRvcnlfaWQiKSAhPSAxNDEzMTMyMTU5KToKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcigiQVBQUk9WRURfQVJUSUZBQ1RfTUlTTUFUQ0giKQogICAgICAgIGlmIHNlbGYuY2xvY2soKSA+PSB2YWx1ZVsiZXhwaXJlc19hdCJdIG9yIHNlbGYuY2xvY2soKSAtIHNlbGYuc3RhcnRlZCA+IDMwOgogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJBUFBST1ZBTF9WQUxJREFUSU9OX05PVF9DVVJSRU5UIikKICAgICAgICAjIFRBUiBieXRlcyBhcmUgaW5kZXBlbmRlbnRseSByZXZpZXdlZCBhbmQgcGlubmVkIGJ5IHRoZSBleGFjdCBPd25lciBib2R5CiAgICAgICAgIyBoYXNoLiBBbm9ueW1vdXMgR2l0SHViIG1ldGFkYXRhIHZlcmlmaWVzIHRoZSBhY3R1YWwgWklQIGRpZ2VzdC9ydW47IGRvCiAgICAgICAgIyBub3QgY2xhaW0gdGhpcyBydW50aW1lIGRvd25sb2Fkcy9yZWhhc2hlcyBhbiBhdXRoZW50aWNhdGVkIGFydGlmYWN0LgogICAgICAgIHByb29mID0gZGljdCh2YWx1ZSwgYXBwcm92YWxfY29tbWVudF9pZD1pZGVudGlmaWVyLAogICAgICAgICAgICBhcHByb3ZhbF9ib2R5X3NoYTI1Nj1waW5bImFwcHJvdmFsX2JvZHlfc2hhMjU2Il0sCiAgICAgICAgICAgIHRydXN0X2JvdW5kYXJ5PSJPV05FUl9ST09UX1BJTl9TSEFSRURfR0lUSFVCX0lERU5USVRZX05PVF9DUllQVE9HUkFQSElDX1JFVklFV0VSX1NFUEFSQVRJT04iKQogICAgICAgIHJldHVybiBWZXJpZmllZFRpY2tldChfU0VBTCwgc2VsZiwgcHJvb2YsIGhhc2hsaWIuc2hhMjU2KGFuY2hvcl9kYXRhKS5oZXhkaWdlc3QoKSwgbWFya2VyLCBzZWxmLnN0YXJ0ZWQpCgoKY2xhc3MgVmVyaWZpZWRUaWNrZXQ6CiAgICBkZWYgX19pbml0X18oc2VsZiwgc2VhbCwgZ2F0ZSwgcHJvb2YsIGFuY2hvcl9oYXNoLCBtYXJrZXIsIHZhbGlkYXRlZF9hdCk6CiAgICAgICAgaWYgc2VhbCBpcyBub3QgX1NFQUw6CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoIlVOVkVSSUZJRURfQVBQUk9WQUxfVElDS0VUIikKICAgICAgICBzZWxmLl9zZWFsLCBzZWxmLl9nYXRlLCBzZWxmLl9wcm9vZiA9IHNlYWwsIGdhdGUsIGpzb24uZHVtcHMocHJvb2YsIHNvcnRfa2V5cz1UcnVlKQogICAgICAgIHNlbGYuX2FuY2hvcl9oYXNoLCBzZWxmLl9tYXJrZXIsIHNlbGYuX3ZhbGlkYXRlZF9hdCA9IGFuY2hvcl9oYXNoLCBtYXJrZXIsIHZhbGlkYXRlZF9hdAogICAgICAgIHNlbGYuX2NvbnN1bWVkID0gRmFsc2UKCiAgICBkZWYgc25hcHNob3Qoc2VsZik6CiAgICAgICAgcmV0dXJuIHN0cmljdF9qc29uKHNlbGYuX3Byb29mKQoKICAgIGRlZiBjaGVjayhzZWxmLCBhY3Rpb24pOgogICAgICAgIHByb29mID0gc2VsZi5zbmFwc2hvdCgpCiAgICAgICAgbm93ID0gc2VsZi5fZ2F0ZS5jbG9jaygpCiAgICAgICAgaWYgKHNlbGYuX2NvbnN1bWVkIG9yIG9zLnBhdGgubGV4aXN0cyhzZWxmLl9tYXJrZXIpIG9yIHByb29mWyJhY3Rpb24iXSAhPSBhY3Rpb24KICAgICAgICAgICAgICAgIG9yIG5vdyA+PSBwcm9vZlsiZXhwaXJlc19hdCJdIG9yIG5vdCAwIDw9IG5vdyAtIHNlbGYuX3ZhbGlkYXRlZF9hdCA8PSAzMCk6CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoIkFQUFJPVkFMX1RJQ0tFVF9OT1RfQ1VSUkVOVF9PUl9DT05TVU1FRCIpCiAgICAgICAgY3VycmVudCA9IHJvb3RfZmlsZShzZWxmLl9nYXRlLmFuY2hvciwgMG82MDAsIDE2Mzg0KQogICAgICAgIGlmIGhhc2hsaWIuc2hhMjU2KGN1cnJlbnQpLmhleGRpZ2VzdCgpICE9IHNlbGYuX2FuY2hvcl9oYXNoOgogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJPV05FUl9QSU5fQ0hBTkdFRCIpCiAgICAgICAgaWYgaGFzaGxpYi5zaGEyNTYocm9vdF9maWxlKHNlbGYuX2dhdGUuc2VsZl9wYXRoLCAwbzQwMCwgMjAwMDAwKSkuaGV4ZGlnZXN0KCkgIT0gcHJvb2ZbImluc3RhbGxlcl9zaGEyNTYiXToKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcigiSU5TVEFMTEVSX0RSSUZUX0FGVEVSX0FQUFJPVkFMIikKICAgICAgICBjb21tZW50ID0gc2VsZi5fZ2F0ZS5nZXQoIi9pc3N1ZXMvY29tbWVudHMvIiArIHN0cihwcm9vZlsiYXBwcm92YWxfY29tbWVudF9pZCJdKSkKICAgICAgICBib2R5ID0gY29tbWVudC5nZXQoImJvZHkiLCAiIikKICAgICAgICBpZiBub3QgaXNpbnN0YW5jZShib2R5LCBzdHIpIG9yIGhhc2hsaWIuc2hhMjU2KGJvZHkuZW5jb2RlKCkpLmhleGRpZ2VzdCgpICE9IHByb29mWyJhcHByb3ZhbF9ib2R5X3NoYTI1NiJdOgogICAgICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJBUFBST1ZBTF9DSEFOR0VEX0JFRk9SRV9DT05TVU1QVElPTiIpCiAgICAgICAgaWYgc2VsZi5fZ2F0ZS5jbG9jaygpID49IHByb29mWyJleHBpcmVzX2F0Il0gb3Igc2VsZi5fZ2F0ZS5jbG9jaygpIC0gc2VsZi5fdmFsaWRhdGVkX2F0ID4gMzA6CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoIkFQUFJPVkFMX0VYUElSRURfQkVGT1JFX0NPTlNVTVBUSU9OIikKCiAgICBkZWYgY29uc3VtZShzZWxmKToKICAgICAgICBzZWxmLmNoZWNrKHNlbGYuc25hcHNob3QoKVsiYWN0aW9uIl0pCiAgICAgICAgZGlyZWN0b3J5ID0gc2VsZi5fZ2F0ZS5yZWdpc3RyeQogICAgICAgIGlmIG5vdCBvcy5wYXRoLmxleGlzdHMoZGlyZWN0b3J5KToKICAgICAgICAgICAgZGlyZWN0b3J5Lm1rZGlyKG1vZGU9MG83MDApCiAgICAgICAgcm9vdF9wYXJlbnQoZGlyZWN0b3J5KQogICAgICAgIGZkID0gb3Mub3BlbihzZWxmLl9tYXJrZXIsIG9zLk9fV1JPTkxZIHwgb3MuT19DUkVBVCB8IG9zLk9fRVhDTCB8IG9zLk9fTk9GT0xMT1csIDBvNjAwKQogICAgICAgIHNlbGYuX2NvbnN1bWVkID0gVHJ1ZQogICAgICAgIHdpdGggb3MuZmRvcGVuKGZkLCAid2IiKSBhcyBoYW5kbGU6CiAgICAgICAgICAgIGhhbmRsZS53cml0ZSgoc2VsZi5fcHJvb2YgKyAiXG4iKS5lbmNvZGUoKSkKICAgICAgICAgICAgaGFuZGxlLmZsdXNoKCkKICAgICAgICAgICAgb3MuZnN5bmMoaGFuZGxlLmZpbGVubygpKQogICAgICAgIGZvciBwYXRoIGluIChkaXJlY3RvcnksIGRpcmVjdG9yeS5wYXJlbnQpOgogICAgICAgICAgICBmZCA9IG9zLm9wZW4ocGF0aCwgb3MuT19SRE9OTFkgfCBvcy5PX0RJUkVDVE9SWSB8IG9zLk9fTk9GT0xMT1cpCiAgICAgICAgICAgIHRyeToKICAgICAgICAgICAgICAgIG9zLmZzeW5jKGZkKQogICAgICAgICAgICBmaW5hbGx5OgogICAgICAgICAgICAgICAgb3MuY2xvc2UoZmQpCgoKZGVmIHJlcXVpcmVfdGlja2V0KHRpY2tldCwgYWN0aW9uKToKICAgIGlmIHR5cGUodGlja2V0KSBpcyBub3QgVmVyaWZpZWRUaWNrZXQgb3IgdGlja2V0Ll9zZWFsIGlzIG5vdCBfU0VBTDoKICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCJFWEFDVF9JTkRFUEVOREVOVF9BUFBST1ZBTF9SRVFVSVJFRCIpCiAgICB0aWNrZXQuY2hlY2soYWN0aW9uKQogICAgcmV0dXJuIHRpY2tldAo="
_gate_module = None


def approval_module():
    global _gate_module
    if _gate_module is None:
        data = base64.b64decode(GATE_B64, validate=True)
        if hashlib.sha256(data).hexdigest() != GATE_SHA256:
            raise ValueError("APPROVAL_GATE_HASH")
        module = types.ModuleType("r4_exact_approval_gate")
        exec(compile(data, "<r4-approval-gate>", "exec"), module.__dict__)
        _gate_module = module
    return _gate_module


def require_authorization(ticket, action):
    return approval_module().require_ticket(ticket, action)


def root_chain(path):
    for item in reversed((path,) + tuple(path.parents)):
        info = item.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError("ROOT_PATH_IDENTITY")


def load_engine():
    root_chain(HELPER.parent)
    fd = os.open(HELPER, os.O_RDONLY | os.O_NOFOLLOW)
    with os.fdopen(fd, "rb") as handle:
        info = os.fstat(handle.fileno())
        if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1
                or stat.S_IMODE(info.st_mode) != 0o755):
            raise ValueError("REUSED_HELPER_IDENTITY")
        data = handle.read(1000001)
    if hashlib.sha256(data).hexdigest() != HELPER_SHA256:
        raise ValueError("REUSED_HELPER_SHA256")
    engine = types.ModuleType("r4_reused_transaction_engine")
    exec(compile(data, str(HELPER), "exec"), engine.__dict__)
    guard_data = base64.b64decode(GUARD_B64, validate=True)
    if hashlib.sha256(guard_data).hexdigest() != GUARD_SHA256:
        raise ValueError("APPROVED_GUARD_SHA256")
    guard = types.ModuleType("r4_exact_approved_builder")
    exec(compile(guard_data, "<approved-r4-builder>", "exec"), guard.__dict__)
    engine.SOURCE_SHA256 = SOURCE_SHA256
    engine.CANDIDATE_SHA256 = CANDIDATE_SHA256
    engine.build_candidate = guard.build_candidate
    return engine


def service_state():
    result = subprocess.run(["/usr/bin/systemctl", "show", UNIT, "-p", "MainPID",
        "-p", "User", "-p", "ActiveState", "-p", "SubState", "-p", "WorkingDirectory"],
        check=True, capture_output=True, text=True, timeout=10,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"})
    return dict(line.split("=", 1) for line in result.stdout.splitlines() if "=" in line)


def stop_backend():
    subprocess.run(["/usr/bin/systemctl", "stop", UNIT], check=True, timeout=40,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        env={"PATH": "/usr/sbin:/usr/bin:/sbin:/bin", "LANG": "C"})


def backend_closed():
    with socket.socket() as connection:
        connection.settimeout(2)
        try:
            return connection.connect_ex(("127.0.0.1", 18080)) == errno.ECONNREFUSED
        except OSError:
            return False


def running(state):
    return (state.get("ActiveState") == "active" and state.get("SubState") == "running"
        and state.get("User") == "admin" and state.get("WorkingDirectory") == "/opt/trading-system"
        and state.get("MainPID", "0").isdigit() and int(state["MainPID"]) > 0)


class Operation:
    def __init__(self, engine, root=STATE, source=TARGET, summary=SUMMARY,
                 inspect=service_state, restart=None, health=None, negative=None,
                 stop=stop_backend, offline_confirm=backend_closed):
        self.engine, self.root, self.source, self.summary = engine, Path(root), Path(source), Path(summary)
        self.inspect, self.stop = inspect, stop
        self.offline_confirm = offline_confirm
        self.health = health or (lambda: engine.verify_live(501))
        self.negative = negative or self.verify_disabled_http
        self.cap = engine.Capability(root=self.root, source=self.source,
            restart=restart or engine.restart_portal, verify=self.verify_after,
            preflight=self.preflight)

    def current(self, expected):
        data, info = self.cap.source_bytes()
        if hashlib.sha256(data).hexdigest() != expected:
            raise ValueError("LIVE_SOURCE_HASH_CHANGED")
        return data, info

    def preflight(self):
        self.before = self.inspect()
        if not running(self.before):
            raise ValueError("EXPECTED_RUNNING_PORTAL_REQUIRED")

    def verify_after(self, ignored):
        self.current(self.engine.CANDIDATE_SHA256)
        after = self.inspect()
        if not running(after) or after["MainPID"] == self.before["MainPID"]:
            raise ValueError("NEW_RUNNING_PORTAL_PID_REQUIRED")
        checks = self.health()
        self.current(self.engine.CANDIDATE_SHA256)
        checks.extend(self.negative())
        self.cap.record["service_before"] = self.before
        self.cap.record["service_after"] = after
        return checks

    def verify_disabled_http(self):
        """Proposed safe negative POST only after exact new bytes + fresh PID.

        This action still requires installation-plan approval. No real session,
        account ID, Cookie, bearer token or business data is sent.
        """
        checks = []
        domain = "wenwenwenyiyiyi.work"
        for address in ("47.245.53.152", "47.101.152.210"):
            for variant in ("empty", "synthetic_untrusted_headers"):
                self.current(self.engine.CANDIDATE_SHA256)
                raw = socket.create_connection((address, 443), timeout=8)
                tls = ssl.create_default_context().wrap_socket(raw, server_hostname=domain)
                conn = http.client.HTTPConnection(domain, timeout=8)
                conn.sock = tls
                try:
                    headers = {"Host": domain, "Connection": "close", "Content-Length": "0"}
                    if variant != "empty":
                        headers.update({"Origin": "https://invalid.example", "X-Authenticated-User": "SYNTHETIC_OWNER", "X-CSRF-Token": "SYNTHETIC_INVALID"})
                    conn.request("POST", "/integrations/tiktok/disconnect", body=b"", headers=headers)
                    response = conn.getresponse()
                    data = response.read(4096)
                    if response.status != 403 or response.getheader("Set-Cookie"):
                        raise ValueError("LIVE_CONTAINMENT_STATUS")
                    if json.loads(data) != {"status": "REJECTED", "sanitized_error_code": "DISCONNECT_DISABLED_AUTH_NOT_INTEGRATED", "operation_performed": False}:
                        raise ValueError("LIVE_CONTAINMENT_BODY")
                    checks.append({"address": address, "variant": variant, "method": "POST", "status": 403, "tls_verified": True, "synthetic_empty_request": True})
                finally:
                    conn.close()
        return checks

    def publish(self):
        self.cap.load()
        record = self.cap.record
        # Only fixed operational metadata; never copy private source or grant.
        public = {"schema_version": 1, "action": "PR122_R4_CONTAINMENT_V1",
            "host": HOST, "status": record["status"], "source_sha256": self.engine.SOURCE_SHA256,
            "candidate_sha256": self.engine.CANDIDATE_SHA256,
            "apply_started": record.get("apply_started", False),
            "offline_rollback_started": record.get("offline_rollback_started", False),
            "checks": record.get("checks", []), "service_before": record.get("service_before"),
            "service_after": record.get("service_after"), "error": record.get("error"),
            "dns_change": False, "website_files_changed": False,
            "tiktok_http_disconnect": "TEMPORARILY_DISABLED" if record["status"] == "LIVE_R4_CONTAINMENT_PASS" else "NOT_ESTABLISHED",
            "authenticated_disconnect": "NOT_IMPLEMENTED"}
        if os.path.lexists(self.summary):
            data, _ = self.engine.checked_read(self.summary, 0, 0o644)
            if json.loads(data).get("action") != public["action"]:
                raise ValueError("PUBLIC_RECEIPT_IDENTITY")
        self.engine.atomic_write(self.summary, (json.dumps(public, sort_keys=True) + "\n").encode(), mode=0o644)
        return public

    def install(self, authorization=None):
        authorization = require_authorization(authorization, "install")
        proof = authorization.snapshot()
        if (proof["expected_source_sha256"] != self.engine.SOURCE_SHA256
                or proof["result_source_sha256"] != self.engine.CANDIDATE_SHA256):
            raise ValueError("APPROVAL_RUNTIME_SOURCE_BINDING")
        if os.path.lexists(self.root) or os.path.lexists(self.summary):
            raise ValueError("NO_BLIND_INSTALL_RETRY")
        data, _ = self.current(self.engine.SOURCE_SHA256)
        candidate = self.engine.build_candidate(data)
        if hashlib.sha256(candidate).hexdigest() != self.engine.CANDIDATE_SHA256:
            raise ValueError("CANDIDATE_HASH_MISMATCH")
        ast.parse(candidate)
        self.preflight()
        authorization.consume()
        self.root.mkdir(mode=0o700)
        self.root.chmod(0o700)
        self.engine.atomic_write(self.root / "grant.json", json.dumps({
            "scope": "OWNER_LONG_TERM_DOMESTIC_TOKYO_MIGRATION_R4_FIXED_ACTION",
            "source_scope_approval": "PR122#6205371670",
            "install_plan_approval": authorization.snapshot(),
            "full_authenticated_disconnect": "NOT_IMPLEMENTED"}).encode())
        try:
            self.cap.run("apply")
            self.cap.record["status"] = "LIVE_R4_CONTAINMENT_PASS"
            self.cap.save()
            return self.publish()
        except BaseException as error:
            # Inherited engine preserves its bounded failure receipt and backup.
            self.cap.load()
            self.cap.record.update(status="UNKNOWN_PRESERVE_EVIDENCE", error=type(error).__name__)
            self.cap.save()
            self.publish()
            raise

    def rollback_offline(self, authorization=None):
        """Emergency-only proposed rollback: old vulnerable code stays OFFLINE.

        Never automatic. Stops only Portal (not Nginx/VM), verifies MainPID=0,
        restores exact backup, and DOES NOT restart. Requires independent plan
        acceptance and deliberate Owner root invocation; dynamic routes outage.
        """
        authorization = require_authorization(authorization, "rollback-offline")
        proof = authorization.snapshot()
        if (proof["expected_source_sha256"] != self.engine.CANDIDATE_SHA256
                or proof["result_source_sha256"] != self.engine.SOURCE_SHA256):
            raise ValueError("APPROVAL_RUNTIME_SOURCE_BINDING")
        self.cap.load()
        if not self.cap.record.get("apply_started") or self.cap.record.get("offline_rollback_started"):
            raise ValueError("OFFLINE_ROLLBACK_NOT_ALLOWED")
        _, info = self.current(self.engine.CANDIDATE_SHA256)
        backup, _ = self.engine.checked_read(self.root / "source.before.py", 0, 0o400)
        if hashlib.sha256(backup).hexdigest() != self.engine.SOURCE_SHA256:
            raise ValueError("ROLLBACK_BACKUP_HASH")
        authorization.consume()
        self.cap.record["offline_rollback_approval"] = authorization.snapshot()
        self.cap.record.update(offline_rollback_started=True, status="OFFLINE_ROLLBACK_STARTED")
        self.cap.save()
        try:
            self.stop()
            stopped = self.inspect()
            if (stopped.get("MainPID") != "0"
                    or stopped.get("ActiveState") not in ("inactive", "failed")
                    or not self.offline_confirm()):
                raise ValueError("PORTAL_STOP_NOT_CONFIRMED")
            self.current(self.engine.CANDIDATE_SHA256)
            self.engine.atomic_write(self.source, backup, info.st_uid, info.st_gid, 0o755)
            self.cap.record.update(status="ROLLED_BACK_BACKEND_STOPPED", checks=[], service_after=stopped)
            self.cap.save()
            return self.publish()
        except BaseException as error:
            self.cap.record.update(status="UNKNOWN_PRESERVE_EVIDENCE", error=type(error).__name__)
            self.cap.save()
            self.publish()
            raise


def lock_file(path, *, create):
    flags = os.O_RDWR | os.O_NOFOLLOW | (os.O_CREAT if create else 0)
    fd = os.open(path, flags, 0o600)
    info = os.fstat(fd)
    if (not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_nlink != 1
            or stat.S_IMODE(info.st_mode) != 0o600):
        os.close(fd)
        raise ValueError("EXECUTION_LOCK_IDENTITY")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return fd
    except BaseException:
        os.close(fd)
        raise


def main():
    if len(sys.argv) != 2 or sys.argv[1] not in ("--install", "--status", "--rollback-offline"):
        raise SystemExit("ONE_FIXED_ACTION_REQUIRED")
    if os.geteuid() != 0 or os.uname().nodename != HOST:
        raise SystemExit("ROOT_ON_APPROVED_TOKYO_REQUIRED")
    os.umask(0o077)
    # Mandatory admission occurs before any lock creation, state, or service action.
    ticket = None
    if sys.argv[1] != "--status":
        ticket = approval_module().Gate(sys.argv[1][2:], Path(__file__)).validate()
    engine = load_engine()
    root_chain(STATE.parent)
    root_chain(Path("/var/lib/xuanjun-pr122-portal-logfix-capability"))
    # Coordinate with the already installed engine; do not change its state.
    locks = []
    try:
        locks.append(lock_file(Path("/var/lib/xuanjun-pr122-portal-logfix-capability/execution.lock"), create=False))
        locks.append(lock_file(Path("/run/xuanjun-pr122-r4-install.lock"), create=True))
        operation = Operation(engine)
        if sys.argv[1] == "--install":
            result = operation.install(ticket)
        elif sys.argv[1] == "--rollback-offline":
            result = operation.rollback_offline(ticket)
        else:
            result = operation.cap.run("status")
        print(json.dumps(result, sort_keys=True))
    except BaseException as error:
        print(json.dumps({"status": "HOLD_PRESERVE_EVIDENCE", "reason": type(error).__name__, "private_state": str(STATE)}, sort_keys=True))
        raise SystemExit(1)
    finally:
        for fd in reversed(locks):
            os.close(fd)


if __name__ == "__main__":
    main()
