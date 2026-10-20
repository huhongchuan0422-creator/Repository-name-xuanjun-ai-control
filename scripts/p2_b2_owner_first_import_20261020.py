"""Owner-confirmed B2 orchestration, no UK execution performed by preparation."""
import os,sys,stat,json,hashlib,runpy,fcntl,time,subprocess,re,base64
from pathlib import Path
BASE=Path('/var/lib/xuanjun-p2-isolated-test')
ROOT=BASE/'b2-evidence'
INPUT=BASE/'b2-input-20261020'
LOGS=BASE/'logs/b2-first-import-20261020'
HOST='iZd7oeikknn1z21sq6ji6zZ'
IMAGE='sha256:5341f193a5741b64f2acc63a99dc95910289fcc39ff17dacff373a50e233724d'
TAR_SHA='c3cadb38a0ab4587ea4f5f4dc882af9d75f184cb2b881d4c76efc218659b399a'
SPEC_RAW=base64.b64decode('eyJhdHRlbXB0X2lkIjoiYjItcHJlc2VydmUtYTEiLCJiYXRjaF9pZCI6ImIyLXByZXNlcnZlIiwiaW5wdXRzIjp7fSwiaW5zdGFsbGF0aW9uX2lkIjoicDItdWstaXNvbGF0ZWQtMjAyNjEwMjAiLCJvcmlnaW5fc2NvcGUiOiJJU09MQVRFRF9CMV9FVklERU5DRSIsInJvb3QiOiIvdmFyL2xpYi94dWFuanVuLXAyLWlzb2xhdGVkLXRlc3QvYjItZXZpZGVuY2UiLCJzY2hlbWEiOjEsInNjb3BlIjoiSVNPTEFURURfVEVTVF9PTkxZIiwic291cmNlX3Jvb3QiOiIvc291cmNlIiwic291cmNlcyI6eyJiMS1yZWNlaXB0Lmpzb24iOnsib3JpZ2luX3JlZiI6Ii92YXIvbGliL3h1YW5qdW4tcDItaXNvbGF0ZWQtdGVzdC9hcnRpZmFjdHMvLnAyX2FydGlmYWN0cy9yZWNlaXB0cy9wMi11ay1pc29sYXRlZC0yMDI2MTAyMC0tYjEtcmVsZWFzZS5qc29uIiwic2hhMjU2IjoiMmFhMDYxNmY4ZDljYzU3ZTRkYzM2NzE5OGZjYjQwYjFkOWNmZTg4ZmZhNDYyMjEyNzNjNjJjZjRhZDZlMDY5YSJ9LCJiMS1zdW1tYXJ5Lmpzb24iOnsib3JpZ2luX3JlZiI6Ii92YXIvbGliL3h1YW5qdW4tcDItaXNvbGF0ZWQtdGVzdC9sb2dzL2IxLWZpcnN0LWluc3RhbGwtMjAyNjEwMjAvc3VtbWFyeS5qc29uIiwic2hhMjU2IjoiYmRhY2NhMzBkNThhMzBjN2U2MDNjM2M0NWE0OWQ5ZWIwYmZmN2UxNTNjNjYzNWZmOTU4NTRiZGE3NWMxNGQ5YyJ9fX0=')
ADAPTER=base64.b64decode('IiIiQjIgaXNvbGF0ZWQgZXZpZGVuY2UgcGFja2FnaW5nIGFkYXB0ZXI7IGV4YWN0IGVhMzEgcGVyZm9ybXMgaW5zdGFsbGF0aW9uL3JlY292ZXJ5LiIiIgppbXBvcnQgYXJncGFyc2UKaW1wb3J0IGhhc2hsaWIKaW1wb3J0IGlvCmltcG9ydCBqc29uCmltcG9ydCBvcwpmcm9tIHBhdGhsaWIgaW1wb3J0IFBhdGgKaW1wb3J0IHN0YXQKaW1wb3J0IHRhcmZpbGUKaW1wb3J0IHV1aWQKZnJvbSBwcm9kdWN0aW9uLnAyX2FydGlmYWN0cyBpbXBvcnQgaW5zdGFsbGVyIGFzIGFydGlmYWN0cwoKTkFNRVMgPSAoJ2IxLXJlY2VpcHQuanNvbicsICdiMS1zdW1tYXJ5Lmpzb24nKQpMSU1JVCA9IDQgKiAxMDI0ICogMTAyNApPUklHSU5fUkVGUyA9IHsKICAgICdiMS1yZWNlaXB0Lmpzb24nOiAnL3Zhci9saWIveHVhbmp1bi1wMi1pc29sYXRlZC10ZXN0L2FydGlmYWN0cy8ucDJfYXJ0aWZhY3RzL3JlY2VpcHRzL3AyLXVrLWlzb2xhdGVkLTIwMjYxMDIwLS1iMS1yZWxlYXNlLmpzb24nLAogICAgJ2IxLXN1bW1hcnkuanNvbic6ICcvdmFyL2xpYi94dWFuanVuLXAyLWlzb2xhdGVkLXRlc3QvbG9ncy9iMS1maXJzdC1pbnN0YWxsLTIwMjYxMDIwL3N1bW1hcnkuanNvbid9CkIxX1JFQ0VJUFRfU0hBID0gJzJhYTA2MTZmOGQ5Y2M1N2U0ZGMzNjcxOThmY2I0MGIxZDljZmU4OGZmYTQ2MjIxMjczYzYyY2Y0YWQ2ZTA2OWEnCgoKZGVmIHJlYWRfcmVndWxhcihwYXRoKToKICAgIHBhdGggPSBQYXRoKHBhdGgpCiAgICBpZiBub3QgcGF0aC5pc19hYnNvbHV0ZSgpIG9yICcuLicgaW4gcGF0aC5wYXJ0czoKICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCdTT1VSQ0VfUEFUSCcpCiAgICBmZCA9IG9zLm9wZW4oJy8nLCBvcy5PX1JET05MWSB8IG9zLk9fRElSRUNUT1JZKQogICAgdHJ5OgogICAgICAgIGZvciBwYXJ0IGluIHBhdGgucGFydHNbMTotMV06CiAgICAgICAgICAgIGNoaWxkID0gb3Mub3BlbihwYXJ0LCBvcy5PX1JET05MWSB8IG9zLk9fRElSRUNUT1JZIHwgb3MuT19OT0ZPTExPVywgZGlyX2ZkPWZkKQogICAgICAgICAgICBvcy5jbG9zZShmZCkKICAgICAgICAgICAgZmQgPSBjaGlsZAogICAgICAgIHNvdXJjZSA9IG9zLm9wZW4ocGF0aC5uYW1lLCBvcy5PX1JET05MWSB8IG9zLk9fTk9GT0xMT1cgfCBvcy5PX05PTkJMT0NLLCBkaXJfZmQ9ZmQpCiAgICAgICAgd2l0aCBvcy5mZG9wZW4oc291cmNlLCAncmInKSBhcyBzdHJlYW06CiAgICAgICAgICAgIGJlZm9yZSA9IG9zLmZzdGF0KHN0cmVhbS5maWxlbm8oKSkKICAgICAgICAgICAgaWYgbm90IHN0YXQuU19JU1JFRyhiZWZvcmUuc3RfbW9kZSkgb3IgYmVmb3JlLnN0X3NpemUgPiBMSU1JVDoKICAgICAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ1NPVVJDRV9UWVBFX09SX1NJWkUnKQogICAgICAgICAgICByYXcgPSBzdHJlYW0ucmVhZChMSU1JVCArIDEpCiAgICAgICAgICAgIGFmdGVyID0gb3MuZnN0YXQoc3RyZWFtLmZpbGVubygpKQogICAgICAgICAgICBmaWVsZHMgPSBsYW1iZGEgczogKHMuc3RfZGV2LCBzLnN0X2lubywgcy5zdF9zaXplLCBzLnN0X210aW1lX25zLCBzLnN0X2N0aW1lX25zKQogICAgICAgICAgICBpZiBmaWVsZHMoYmVmb3JlKSAhPSBmaWVsZHMoYWZ0ZXIpIG9yIGxlbihyYXcpICE9IGJlZm9yZS5zdF9zaXplOgogICAgICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignU09VUkNFX0NIQU5HRUQnKQogICAgICAgICAgICByZXR1cm4gcmF3CiAgICBmaW5hbGx5OgogICAgICAgIG9zLmNsb3NlKGZkKQoKCmRlZiBzaGEocmF3KToKICAgIHJldHVybiBoYXNobGliLnNoYTI1NihyYXcpLmhleGRpZ2VzdCgpCgoKZGVmIGluZGV4X2J5dGVzKHNwZWMpOgogICAgaWYgbm90IGlzaW5zdGFuY2Uoc3BlYywgZGljdCk6CiAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignVU5LTk9XTl9TT1VSQ0VfU1BFQycpCiAgICBpZiBzcGVjLmdldCgnc2NvcGUnKSAhPSAnSVNPTEFURURfVEVTVF9PTkxZJyBvciBzcGVjLmdldCgnb3JpZ2luX3Njb3BlJykgbm90IGluICgKICAgICAgICAgICAgJ0lTT0xBVEVEX0IxX0VWSURFTkNFJywgJ1NZTlRIRVRJQ19URVNUX09OTFknKToKICAgICAgICByYWlzZSBWYWx1ZUVycm9yKCdVTktOT1dOX1NPVVJDRV9TQ09QRScpCiAgICBpZiBub3QgaXNpbnN0YW5jZShzcGVjLmdldCgnc291cmNlcycpLCBkaWN0KSBvciBzZXQoc3BlY1snc291cmNlcyddKSAhPSBzZXQoTkFNRVMpOgogICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ1VOS05PV05fU09VUkNFX1NFVCcpCiAgICBmb3IgdmFsdWUgaW4gc3BlY1snc291cmNlcyddLnZhbHVlcygpOgogICAgICAgIGlmIG5vdCBpc2luc3RhbmNlKHZhbHVlLCBkaWN0KSBvciBub3QgYXJ0aWZhY3RzLkhFWC5mdWxsbWF0Y2godmFsdWUuZ2V0KCdzaGEyNTYnLCAnJykpIG9yIG5vdCB2YWx1ZS5nZXQoJ29yaWdpbl9yZWYnKToKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignVU5LTk9XTl9TT1VSQ0VfQklORElORycpCiAgICBpZiBzcGVjWydvcmlnaW5fc2NvcGUnXSA9PSAnSVNPTEFURURfQjFfRVZJREVOQ0UnOgogICAgICAgIGlmIGFueShzcGVjWydzb3VyY2VzJ11bbl1bJ29yaWdpbl9yZWYnXSAhPSBPUklHSU5fUkVGU1tuXSBmb3IgbiBpbiBOQU1FUyk6CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ1VOS05PV05fQjFfT1JJR0lOJykKICAgICAgICBpZiBzcGVjWydzb3VyY2VzJ11bJ2IxLXJlY2VpcHQuanNvbiddWydzaGEyNTYnXSAhPSBCMV9SRUNFSVBUX1NIQToKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignVU5LTk9XTl9CMV9SRUNFSVBUJykKICAgICAgICBpZiAoc3BlYy5nZXQoJ3Jvb3QnKSwgc3BlYy5nZXQoJ3NvdXJjZV9yb290JyksIHNwZWMuZ2V0KCdpbnN0YWxsYXRpb25faWQnKSwgc3BlYy5nZXQoJ2JhdGNoX2lkJyksIHNwZWMuZ2V0KCdhdHRlbXB0X2lkJykpICE9ICgKICAgICAgICAgICAgICAgICcvdmFyL2xpYi94dWFuanVuLXAyLWlzb2xhdGVkLXRlc3QvYjItZXZpZGVuY2UnLCAnL3NvdXJjZScsCiAgICAgICAgICAgICAgICAncDItdWstaXNvbGF0ZWQtMjAyNjEwMjAnLCAnYjItcHJlc2VydmUnLCAnYjItcHJlc2VydmUtYTEnKToKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignQjJfRklYRURfU0NPUEVfTUlTTUFUQ0gnKQogICAgcmV0dXJuIGFydGlmYWN0cy5lbmNvZGUoeydzY2hlbWEnOiAxLCAnc2NvcGUnOiBzcGVjWydzY29wZSddLCAnb3JpZ2luX3Njb3BlJzogc3BlY1snb3JpZ2luX3Njb3BlJ10sCiAgICAgICAgJ3Byb2R1Y3Rpb25faGlzdG9yeSc6IEZhbHNlLCAnc291cmNlcyc6IHNwZWNbJ3NvdXJjZXMnXX0pCgoKZGVmIHB1Ymxpc2gocGF0aCwgcmF3KToKICAgIGlmIG9zLnBhdGgubGV4aXN0cyhzdHIocGF0aCkpOgogICAgICAgIGlmIHJlYWRfcmVndWxhcihwYXRoKSAhPSByYXc6CiAgICAgICAgICAgIHJhaXNlIFZhbHVlRXJyb3IoJ1BSRVBBUkVEX0VWSURFTkNFX0NPTkZMSUNUJykKICAgICAgICByZXR1cm4KICAgICMgS2VlcCBpbnRlcnJ1cHRlZCBhbmQgbGlua2VkIHN0YWdpbmcgZmlsZXMgYXMgZXZpZGVuY2U7IG5ldmVyIG92ZXJ3cml0ZS91bmxpbmsuCiAgICBwZW5kaW5nID0gcGF0aC5wYXJlbnQgLyAoJy4nICsgcGF0aC5uYW1lICsgJy5wZW5kaW5nLScgKyB1dWlkLnV1aWQ0KCkuaGV4KQogICAgZmQgPSBvcy5vcGVuKHN0cihwZW5kaW5nKSwgb3MuT19XUk9OTFkgfCBvcy5PX0NSRUFUIHwgb3MuT19FWENMIHwgb3MuT19OT0ZPTExPVywgMG80MDApCiAgICB3aXRoIG9zLmZkb3BlbihmZCwgJ3diJykgYXMgb3V0OgogICAgICAgIG91dC53cml0ZShyYXcpCiAgICAgICAgb3V0LmZsdXNoKCkKICAgICAgICBvcy5mc3luYyhvdXQuZmlsZW5vKCkpCiAgICB0cnk6CiAgICAgICAgb3MubGluayhzdHIocGVuZGluZyksIHN0cihwYXRoKSkKICAgIGV4Y2VwdCBGaWxlRXhpc3RzRXJyb3I6CiAgICAgICAgaWYgcmVhZF9yZWd1bGFyKHBhdGgpICE9IHJhdzoKICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignUFJFUEFSRURfRVZJREVOQ0VfQ09ORkxJQ1QnKQogICAgYXJ0aWZhY3RzLmZzeW5jX2RpcihwYXRoLnBhcmVudCkKCgpkZWYgY29tcG9uZW50X3JlcXVlc3Qoc3BlYywgcm9vdCwgYXJjaGl2ZV9zaGEpOgogICAgaW5kZXggPSBpbmRleF9ieXRlcyhzcGVjKQogICAgcmV0dXJuIHtrOiBzcGVjW2tdIGZvciBrIGluICgnc2NoZW1hJywgJ3Njb3BlJywgJ2luc3RhbGxhdGlvbl9pZCcsICdiYXRjaF9pZCcsICdhdHRlbXB0X2lkJyl9IHwgewogICAgICAgICdyb290Jzogc3RyKHJvb3QpLCAnaW5wdXRzJzogeydvcGVyYXRpb24nOiAnaW5zdGFsbCcsICdhcmNoaXZlJzogc3RyKHJvb3QgLyAnYjItaW5wdXQudGFyJyksCiAgICAgICAgJ2FyY2hpdmVfc2hhMjU2JzogYXJjaGl2ZV9zaGEsICdmaWxlcyc6IGRpY3QoCiAgICAgICAgICAgIHtuOiBzcGVjWydzb3VyY2VzJ11bbl1bJ3NoYTI1NiddIGZvciBuIGluIE5BTUVTfSwgKip7J0lOREVYLmpzb24nOiBzaGEoaW5kZXgpfSksCiAgICAgICAgJ21vZGVzJzoge246IDBvNjAwIGZvciBuIGluIE5BTUVTICsgKCdJTkRFWC5qc29uJywpfX19CgoKZGVmIGRpc3BhdGNoKHNwZWMsIGFjdGlvbik6CiAgICB0cnk6CiAgICAgICAgaW5kZXggPSBpbmRleF9ieXRlcyhzcGVjKSAgIyBVTktOT1dOIG5ldmVyIGNyZWF0ZXMgY29tcG9uZW50IHN0YXRlLgogICAgICAgIHJvb3QgPSBhcnRpZmFjdHMucmVxdWVzdF9jaGVjayhzcGVjKQogICAgICAgIGxvY2sgPSBvcy5vcGVuKHN0cihyb290IC8gJy5iMi5sb2NrJyksIG9zLk9fUkRXUiB8IG9zLk9fQ1JFQVQgfCBvcy5PX05PRk9MTE9XLCAwbzYwMCkKICAgICAgICB0cnk6CiAgICAgICAgICAgIGluZm8gPSBvcy5mc3RhdChsb2NrKQogICAgICAgICAgICBpZiBub3Qgc3RhdC5TX0lTUkVHKGluZm8uc3RfbW9kZSkgb3IgaW5mby5zdF91aWQgIT0gb3MuZ2V0ZXVpZCgpIG9yIHN0YXQuU19JTU9ERShpbmZvLnN0X21vZGUpICE9IDBvNjAwOgogICAgICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignTE9DS19JREVOVElUWScpCiAgICAgICAgICAgIGltcG9ydCBmY250bAogICAgICAgICAgICBmY250bC5mbG9jayhsb2NrLCBmY250bC5MT0NLX0VYIHwgZmNudGwuTE9DS19OQikKICAgICAgICAgICAgaW50ZW50X3BhdGggPSByb290IC8gJ2IyLWludGVudC5qc29uJwogICAgICAgICAgICBzcGVjX3NoYSA9IHNoYShhcnRpZmFjdHMuZW5jb2RlKHNwZWMpKQogICAgICAgICAgICBpZiBvcy5wYXRoLmxleGlzdHMoc3RyKGludGVudF9wYXRoKSk6CiAgICAgICAgICAgICAgICBpbnRlbnQgPSBqc29uLmxvYWRzKHJlYWRfcmVndWxhcihpbnRlbnRfcGF0aCkpCiAgICAgICAgICAgICAgICBpZiBpbnRlbnRbJ3NwZWNfc2hhMjU2J10gIT0gc3BlY19zaGE6CiAgICAgICAgICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignUkVRVUVTVF9DT05GTElDVCcpCiAgICAgICAgICAgICAgICByZXF1ZXN0ID0gY29tcG9uZW50X3JlcXVlc3Qoc3BlYywgcm9vdCwgaW50ZW50WydhcmNoaXZlX3NoYTI1NiddKQogICAgICAgICAgICAgICAgaWYgaW50ZW50Wydjb21wb25lbnRfcmVxdWVzdCddICE9IHJlcXVlc3Q6CiAgICAgICAgICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignSU5URU5UX0NPTkZMSUNUJykKICAgICAgICAgICAgZWxzZToKICAgICAgICAgICAgICAgIGlmIGFjdGlvbiA9PSAnaW5zcGVjdCc6CiAgICAgICAgICAgICAgICAgICAgcmV0dXJuIHsnc2NvcGUnOiBzcGVjWydzY29wZSddLCAnc3RhdHVzJzogJ05PX0VGRkVDVCcsICdyZWNlaXB0JzogTm9uZX0KICAgICAgICAgICAgICAgIGNvbnRlbnRzID0ge246IHJlYWRfcmVndWxhcihQYXRoKHNwZWNbJ3NvdXJjZV9yb290J10pIC8gbikgZm9yIG4gaW4gTkFNRVN9CiAgICAgICAgICAgICAgICBmb3IgbmFtZSwgcmF3IGluIGNvbnRlbnRzLml0ZW1zKCk6CiAgICAgICAgICAgICAgICAgICAgaWYgc2hhKHJhdykgIT0gc3BlY1snc291cmNlcyddW25hbWVdWydzaGEyNTYnXToKICAgICAgICAgICAgICAgICAgICAgICAgcmFpc2UgVmFsdWVFcnJvcignU09VUkNFX0RJR0VTVF9NSVNNQVRDSCcpCiAgICAgICAgICAgICAgICBjb250ZW50c1snSU5ERVguanNvbiddID0gaW5kZXgKICAgICAgICAgICAgICAgIG91dHB1dCA9IGlvLkJ5dGVzSU8oKQogICAgICAgICAgICAgICAgd2l0aCB0YXJmaWxlLm9wZW4oZmlsZW9iaj1vdXRwdXQsIG1vZGU9J3cnLCBmb3JtYXQ9dGFyZmlsZS5VU1RBUl9GT1JNQVQpIGFzIGFyY2hpdmU6CiAgICAgICAgICAgICAgICAgICAgZm9yIG5hbWUsIHJhdyBpbiBzb3J0ZWQoY29udGVudHMuaXRlbXMoKSk6CiAgICAgICAgICAgICAgICAgICAgICAgIG1lbWJlciA9IHRhcmZpbGUuVGFySW5mbyhuYW1lKQogICAgICAgICAgICAgICAgICAgICAgICBtZW1iZXIuc2l6ZSwgbWVtYmVyLm1vZGUsIG1lbWJlci5tdGltZSA9IGxlbihyYXcpLCAwbzYwMCwgMAogICAgICAgICAgICAgICAgICAgICAgICBhcmNoaXZlLmFkZGZpbGUobWVtYmVyLCBpby5CeXRlc0lPKHJhdykpCiAgICAgICAgICAgICAgICByYXcgPSBvdXRwdXQuZ2V0dmFsdWUoKQogICAgICAgICAgICAgICAgcHVibGlzaChyb290IC8gJ2IyLWlucHV0LnRhcicsIHJhdykKICAgICAgICAgICAgICAgIHJlcXVlc3QgPSBjb21wb25lbnRfcmVxdWVzdChzcGVjLCByb290LCBzaGEocmF3KSkKICAgICAgICAgICAgICAgIHB1Ymxpc2goaW50ZW50X3BhdGgsIGFydGlmYWN0cy5lbmNvZGUoeydzcGVjX3NoYTI1Nic6IHNwZWNfc2hhLAogICAgICAgICAgICAgICAgICAgICdhcmNoaXZlX3NoYTI1Nic6IHNoYShyYXcpLCAnY29tcG9uZW50X3JlcXVlc3QnOiByZXF1ZXN0fSkpCiAgICAgICAgICAgIHJldHVybiBnZXRhdHRyKGFydGlmYWN0cywgYWN0aW9uKShyZXF1ZXN0KQogICAgICAgIGZpbmFsbHk6CiAgICAgICAgICAgIG9zLmNsb3NlKGxvY2spCiAgICBleGNlcHQgKFZhbHVlRXJyb3IsIE9TRXJyb3IsIEtleUVycm9yLCBUeXBlRXJyb3IsIGFydGlmYWN0cy5TdG9wKSBhcyBleGM6CiAgICAgICAgcmV0dXJuIHsnc2NvcGUnOiAnSVNPTEFURURfVEVTVF9PTkxZJywgJ3N0YXR1cyc6ICdVTktOT1dOJywKICAgICAgICAgICAgICAgICdyZWNlaXB0JzogTm9uZSwgJ2Vycm9yJzogeydjb2RlJzogZ2V0YXR0cihleGMsICdjb2RlJywgc3RyKGV4YykpfX0KCgpkZWYgbWFpbigpOgogICAgcGFyc2VyID0gYXJncGFyc2UuQXJndW1lbnRQYXJzZXIoKQogICAgcGFyc2VyLmFkZF9hcmd1bWVudCgnYWN0aW9uJywgY2hvaWNlcz0oJ2V4ZWN1dGUnLCAnaW5zcGVjdCcsICdyZWNvdmVyJykpCiAgICBhcmdzID0gcGFyc2VyLnBhcnNlX2FyZ3MoKQogICAgcmVzdWx0ID0gZGlzcGF0Y2goanNvbi5sb2FkKF9faW1wb3J0X18oJ3N5cycpLnN0ZGluKSwgYXJncy5hY3Rpb24pCiAgICBwcmludChqc29uLmR1bXBzKHJlc3VsdCwgc29ydF9rZXlzPVRydWUpKQogICAgcmV0dXJuIDAgaWYgcmVzdWx0WydzdGF0dXMnXSBpbiAoJ0NPTU1JVFRFRCcsICdOT19FRkZFQ1QnKSBlbHNlIDIKCgppZiBfX25hbWVfXyA9PSAnX19tYWluX18nOgogICAgcmFpc2UgU3lzdGVtRXhpdChtYWluKCkpCg==')
SPEC=json.loads(SPEC_RAW)
ADAPTER_SHA='d2de84ed3c0b50d24664c9f1cf0f2fc02785e1a6a96eb6ef8855c1fc7d70a57b'
def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def require(condition, reason):
    if not condition:
        raise RuntimeError(reason)


def directory(path, uid, gid, mode):
    path.mkdir(mode=0o700)
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fchown(fd, uid, gid)
        os.fchmod(fd, mode)
        os.fsync(fd)
    finally:
        os.close(fd)
    sync(path.parent)


def sync(path):
    fd = os.open(str(path), os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def write(path, raw, uid=0, gid=0, mode=0o600):
    fd = os.open(str(path), os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    with os.fdopen(fd, 'wb') as out:
        out.write(raw)
        os.fchown(out.fileno(), uid, gid)
        os.fchmod(out.fileno(), mode)
        out.flush()
        os.fsync(out.fileno())
    sync(path.parent)


def read_file(path):
    fd = os.open(str(path), os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK)
    with os.fdopen(fd, 'rb') as source:
        info = os.fstat(source.fileno())
        require(stat.S_ISREG(info.st_mode), 'NON_REGULAR_EVIDENCE')
        raw = source.read()
    return raw, info


def installed(request):
    key = request['installation_id'] + '--' + request['batch_id']
    dest = ROOT / 'versions' / key
    expected = request['inputs']['files']
    found = set()
    for parent, dirs, names in os.walk(str(dest), followlinks=False):
        for name in dirs:
            require(stat.S_ISDIR(os.lstat(os.path.join(parent, name)).st_mode), 'INSTALLED_UNSAFE_DIRECTORY')
        for name in names:
            found.add(str(Path(parent, name).relative_to(dest)))
    require(found == set(expected), 'INSTALLED_FILE_SET')
    rows = {}
    for name, expected_sha in sorted(expected.items()):
        path = dest / name
        raw, info = read_file(path)
        mode = stat.S_IMODE(info.st_mode)
        require(sha(raw) == expected_sha and mode == request['inputs']['modes'][name]
                and (info.st_uid, info.st_gid) == (1002, 1002), 'INSTALLED_SHA_MODE_OWNER:' + name)
        rows[name] = {'sha256': sha(raw), 'mode': mode, 'uid': info.st_uid, 'gid': info.st_gid,
                      'size': info.st_size, 'inode': info.st_ino, 'mtime_ns': info.st_mtime_ns}
    receipt_path = ROOT / '.p2_artifacts/receipts' / (key + '.json')
    raw, info = read_file(receipt_path)
    return {'files': rows, 'receipt': {'path': str(receipt_path), 'sha256': sha(raw),
                                     'inode': info.st_ino, 'mtime_ns': info.st_mtime_ns}}, raw


def container_state(name):
    fields = '{"state":{{json .State}},"image":{{json .Image}},"user":{{json .Config.User}},"mounts":{{json .Mounts}},"network":{{json .HostConfig.NetworkMode}},"readonly":{{json .HostConfig.ReadonlyRootfs}},"cap_drop":{{json .HostConfig.CapDrop}},"security_opt":{{json .HostConfig.SecurityOpt}},"memory":{{json .HostConfig.Memory}},"memory_swap":{{json .HostConfig.MemorySwap}},"pids":{{json .HostConfig.PidsLimit}},"cpu_quota":{{json .HostConfig.CpuQuota}},"nano_cpus":{{json .HostConfig.NanoCpus}}}'
    p = subprocess.run(['/bin/docker', 'inspect', '--format', fields, name], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
    require(p.returncode == 0, 'CONTAINER_INSPECT_FAILED:' + name)
    return json.loads(p.stdout.decode())


def safe_source(path):
    fd=os.open('/',os.O_RDONLY|os.O_DIRECTORY)
    try:
        for part in path.parts[1:-1]:
            child=os.open(part,os.O_RDONLY|os.O_DIRECTORY|os.O_NOFOLLOW,dir_fd=fd)
            os.close(fd);fd=child
        src=os.open(path.name,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK,dir_fd=fd)
        with os.fdopen(src,'rb') as stream:
            before=os.fstat(stream.fileno())
            require(stat.S_ISREG(before.st_mode) and before.st_size<=4194304,'SOURCE_TYPE_SIZE')
            raw=stream.read(4194305);after=os.fstat(stream.fileno())
            meta=lambda s:(s.st_dev,s.st_ino,s.st_uid,s.st_gid,stat.S_IMODE(s.st_mode),s.st_size,s.st_mtime_ns,s.st_ctime_ns)
            require(meta(before)==meta(after) and len(raw)==before.st_size,'SOURCE_CHANGED_DURING_READ')
            return raw,meta(after)
    finally:os.close(fd)

def read_originals():
    rows={}
    for name,binding in sorted(SPEC['sources'].items()):
        raw,meta=safe_source(Path(binding['origin_ref']))
        require(sha(raw)==binding['sha256'],'ORIGINAL_SHA:'+name)
        if name=='b1-summary.json':
            require(len(raw)==19159 and meta[2:5]==(0,0,0o600),'SUMMARY_IDENTITY')
        rows[name]=(raw,meta)
    return rows

def command(action):
    return ['/bin/docker','run','--interactive','--pull=never','--name=p2-uk-b2-'+action+'-20261020',
      '--cidfile='+str(LOGS/(action+'.cid')),'--hostname='+HOST,'--user=1002:1002',
      '--network=none','--cap-drop=ALL','--security-opt=no-new-privileges','--read-only',
      '--pids-limit=96','--memory=512m','--memory-swap=1g','--log-driver=none',
      '--mount=type=bind,src='+str(INPUT)+',dst=/input,readonly',
      '--mount=type=bind,src='+str(INPUT/'sources')+',dst=/source,readonly',
      '--mount=type=bind,src='+str(ROOT)+',dst='+str(ROOT),
      '--workdir=/input/tools','--env=PYTHONPATH=/input/tools','--env=PYTHONNOUSERSITE=1',
      '--entrypoint=/usr/bin/python3.11',IMAGE,'-B','-S','-m',
      'production.p2_install.evidence_import',action]

def main():
    os.umask(0o077)
    require(os.geteuid()==0 and os.uname().nodename.split('.')[0]==HOST,'HOST_OR_IDENTITY')
    for path in (Path('/var'),Path('/var/lib'),BASE,BASE/'state',BASE/'logs'):
        s=os.lstat(str(path));require(stat.S_ISDIR(s.st_mode),'PARENT_NOT_DIRECTORY')
    parent_before=os.lstat(str(BASE))
    require((parent_before.st_uid,parent_before.st_gid,stat.S_IMODE(parent_before.st_mode))==(0,0,0o700),'BASE_IDENTITY')
    require(not any(os.path.lexists(str(p)) for p in (ROOT,INPUT,LOGS)),'EXISTING_B2_RETAIN_RECONCILE')
    originals=read_originals()
    require(sha(ADAPTER)==ADAPTER_SHA,'ADAPTER_SHA')
    # Verify only the three unchanged tools needed by this B2, not B1 installation again.
    pins={'__init__.py':'81e68a6ce38e3c08a2aceb07a76a57527a2dea75c42d2e4090c18fac75d96905',
      '__main__.py':'c7340363b8826cbe0eba701c0093e03d674170c9ad718a3e5ba4302f2b31eae2',
      'installer.py':'548ee7b8ae17d56fb1a57a7b4d59a4f03f87cca16852dd3c74ab0cd721208108'}
    tools={}
    for name,pin in pins.items():
        raw,meta=safe_source(BASE/'b1-input-20261020/tools/production/p2_artifacts'/name)
        require(sha(raw)==pin,'EXISTING_TOOL_SHA');tools[name]=raw
    index=json.dumps({'schema':1,'scope':SPEC['scope'],'origin_scope':SPEC['origin_scope'],
      'production_history':False,'sources':SPEC['sources']},sort_keys=True,separators=(',',':')).encode()
    request={k:SPEC[k] for k in ('schema','scope','installation_id','batch_id','attempt_id')}
    request.update({'root':str(ROOT),'inputs':{'operation':'install','archive':str(ROOT/'b2-input.tar'),
      'archive_sha256':TAR_SHA,'files':dict({n:v['sha256'] for n,v in SPEC['sources'].items()},**{'INDEX.json':sha(index)}),
      'modes':{n:0o600 for n in ('b1-receipt.json','b1-summary.json','INDEX.json')}}})
    lock=os.open(str(BASE/'state/.formal-cli.lock'),os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW,0o600)
    try:
        li=os.fstat(lock);require(stat.S_ISREG(li.st_mode) and li.st_uid==0 and stat.S_IMODE(li.st_mode)==0o600,'LOCK_IDENTITY')
        fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
        require(read_originals()==originals,'SOURCE_CHANGED_BEFORE_STAGE')
        directory(LOGS,0,0,0o700)
        summary={'scope':'ISOLATED_TEST_ONLY','status':'NOT_EXECUTED','calls':[],'production_activated':False,
          'spec_sha256':sha(SPEC_RAW),'tar_sha256':TAR_SHA,'request':request,'source_metadata':{n:list(v[1]) for n,v in originals.items()},
          'tool_commit':'ea31dbbec2a8710b964efb38fa2975684bbd9739','adapter_commit':'f98ab027ff460371a494a6231badbc880182543c',
          'adapter_sha256':ADAPTER_SHA,'retained_paths':[str(ROOT),str(INPUT),str(LOGS)]}
        try:
            write(LOGS/'owner-script.py',Path(__file__).read_bytes())
            write(LOGS/'spec.json',SPEC_RAW)
            directory(INPUT,0,1002,0o550)
            directory(INPUT/'sources',0,1002,0o550)
            for name,(raw,meta) in originals.items():write(INPUT/'sources'/name,raw,0,1002,0o440)
            write(INPUT/'spec.json',SPEC_RAW,0,1002,0o440)
            for part in ('tools','tools/production','tools/production/p2_artifacts','tools/production/p2_install'):
                directory(INPUT/part,0,1002,0o550)
            for name,raw in tools.items():write(INPUT/'tools/production/p2_artifacts'/name,raw,0,1002,0o440)
            write(INPUT/'tools/production/p2_install/evidence_import.py',ADAPTER,0,1002,0o440)
            directory(ROOT,1002,1002,0o700)
            baseline = None
            for action in ('execute', 'inspect', 'recover'):
                name = 'p2-uk-b2-' + action + '-20261020'
                args = command(action)
                call = {'action': action, 'argv': args, 'started_utc': int(time.time()), 'exit_code': None}
                summary['calls'].append(call)
                with (LOGS / (action + '-stdout.json')).open('xb') as out, (LOGS / (action + '-stderr.log')).open('xb') as err:
                    try:
                        p = subprocess.run(args, input=SPEC_RAW, stdout=out, stderr=err, timeout=120)
                        call['exit_code'] = p.returncode
                    except subprocess.TimeoutExpired:
                        call['timeout'] = True
                        if (LOGS / (action + '.cid')).is_file():
                            cid = (LOGS / (action + '.cid')).read_text().strip()
                            require(re.fullmatch('[0-9a-f]{64}', cid), 'INVALID_OWN_CONTAINER_ID')
                            stopped = subprocess.run(['/bin/docker', 'stop', '--time=3', cid], stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=15)
                            call['stop_exit'] = stopped.returncode
                        else:
                            call['stop_result'] = 'NO_CREATED_CID_NO_UNKNOWN_CONTAINER_STOP'
                    finally:
                        out.flush(); os.fsync(out.fileno())
                        err.flush(); os.fsync(err.fileno())
                call['ended_utc'] = int(time.time())
                cid = (LOGS / (action + '.cid')).read_text().strip()
                require(re.fullmatch('[0-9a-f]{64}', cid), 'INVALID_OWN_CONTAINER_ID')
                call['container_id'] = cid
                state = container_state(cid)
                call['container'] = state
                write(LOGS / (action + '-container.json'), json.dumps(state, sort_keys=True, indent=2).encode())
                require(state['state']['Running'] is False, 'CONTAINER_STILL_RUNNING_RETAIN_STATE')
                require(state['image'] == IMAGE and state['user'] == '1002:1002'
                        and state['network'] == 'none' and state['readonly'] is True
                        and 'ALL' in state['cap_drop']
                        and any(x.startswith('no-new-privileges') for x in state['security_opt'])
                        and state['memory'] == 536870912 and state['memory_swap'] == 1073741824
                        and state['pids'] == 96 and state['cpu_quota'] == 0 and state['nano_cpus'] == 0,
                        'ACTUAL_CONTAINER_BOUNDARY_MISMATCH')
                mounts = {(x['Source'], x['Destination'], x['RW'], x['Type']) for x in state['mounts']}
                require(mounts == {(str(INPUT), '/input', False, 'bind'), (str(INPUT / 'sources'), '/source', False, 'bind'),
                                   (str(ROOT), str(ROOT), True, 'bind')}, 'ACTUAL_MOUNT_MISMATCH')
                raw, unused = read_file(LOGS / (action + '-stdout.json'))
                stderr, unused = read_file(LOGS / (action + '-stderr.log'))
                call['stdout'] = raw.decode('utf-8', 'replace')
                call['stderr'] = stderr.decode('utf-8', 'replace')
                call['stdout_sha256'] = sha(raw)
                call['stderr_sha256'] = sha(stderr)
                require(call['exit_code'] == 0, 'CLI_FAILED_RETAIN_STATE:' + action)
                response = json.loads(raw.decode())
                call['response'] = response
                require(response['status'] == 'COMMITTED', 'NOT_COMMITTED:' + action)
                for key in ('schema','scope','installation_id','batch_id','attempt_id'):
                    require(response[key] == request[key], 'RESPONSE_IDENTITY:' + key)
                require(read_originals() == originals, 'B1_ORIGINAL_CHANGED')
                require(sha(read_file(ROOT / 'b2-input.tar')[0]) == TAR_SHA, 'B2_TAR_MISMATCH')
                observed, receipt_raw = installed(request)
                require(response['receipt'] == {k: observed['receipt'][k] for k in ('path','sha256')}, 'RECEIPT_REFERENCE')
                call['observed'] = observed
                if baseline is None:
                    baseline = observed
                    write(LOGS / 'original-commit-receipt.json', receipt_raw)
                else:
                    require(observed == baseline, 'COMMITTED_BYTES_OR_METADATA_CHANGED:' + action)
                write(LOGS / (action + '-result.json'), json.dumps(call, sort_keys=True, indent=2).encode())
            after=os.lstat(str(BASE))
            require((after.st_uid,after.st_gid,stat.S_IMODE(after.st_mode),after.st_ino)==(0,0,0o700,parent_before.st_ino),'BASE_CHANGED')
            require(read_originals()==originals,'ORIGINAL_CHANGED')
            summary['status']='B2_UK_ISOLATED_EVIDENCE_IMPORT_PASS'
        except Exception as exc:
            summary['status']='FAILED_RETAINED';summary['error']={'type':type(exc).__name__,'detail':str(exc)}
        finally:
            summary['ended_utc']=int(time.time())
            write(LOGS/'summary.json',json.dumps(summary,sort_keys=True,indent=2).encode())
            print(json.dumps(summary,sort_keys=True,indent=2));print('RETAINED_SUMMARY='+str(LOGS/'summary.json'))
        return 0 if summary['status']=='B2_UK_ISOLATED_EVIDENCE_IMPORT_PASS' else 2
    finally:os.close(lock)

if __name__=='__main__':
    try:sys.exit(main())
    except Exception as exc:
        print(json.dumps({'scope':'ISOLATED_TEST_ONLY','status':'HOLD_RETAIN_STATE','error':str(exc),'production_activated':False},sort_keys=True));sys.exit(2)
