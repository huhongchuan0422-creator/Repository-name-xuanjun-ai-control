"""Owner Telegram transport candidate; no production webhook modification."""
import json
import hmac
import hashlib
import time
import urllib.request

class OwnerTelegramTransport:
    def __init__(self, token, owner_chat_id, owner_user_id, signature_key, uk_callback, uk_auth):
        if not all((token, owner_chat_id, owner_user_id, signature_key, uk_auth)):
            raise ValueError("missing configuration")
        if not uk_callback.startswith("https://"):
            raise ValueError("HTTPS callback required")
        self.token = token
        self.chat_id = str(owner_chat_id)
        self.user_id = str(owner_user_id)
        self.key = signature_key.encode("utf-8")
        self.callback = uk_callback
        self.auth = uk_auth

    def send(self, request_id):
        body = json.dumps({"chat_id":self.chat_id, "text":"Owner task awaiting review: "+request_id+"\n/approve "+request_id+" or /reject "+request_id}).encode()
        request = urllib.request.Request("https://api.telegram.org/bot"+self.token+"/sendMessage",
                                         data=body,headers={"Content-Type":"application/json"},method="POST")
        with urllib.request.urlopen(request,timeout=10) as response:
            result=json.loads(response.read(100000).decode())
        if not result.get("ok") or not result.get("result",{}).get("message_id"):
            raise RuntimeError("telegram delivery not acknowledged")
        return result["result"]["message_id"]

    def accept_update(self, update, lookup):
        """Existing authenticated production webhook may call this; no second poller."""
        message=update.get("message") or {}
        if str((message.get("chat") or {}).get("id")) != self.chat_id:
            return "IGNORED"
        if (message.get("chat") or {}).get("type") != "private":
            return "IGNORED"
        if str((message.get("from") or {}).get("id")) != self.user_id:
            return "IGNORED"
        args=str(message.get("text") or "").split()
        if len(args)!=2 or args[0] not in ("/approve","/reject"):
            return "IGNORED"
        ref=lookup(args[1])
        if not ref or ref["state"]!="WAITING_HUMAN" or ref["expires_at"] <= time.time():
            return "IGNORED"
        payload=json.dumps({"request_id":args[1],"task_id":ref["task_id"],"fence":ref["fence"],
                            "owner_user_id":self.user_id,"owner_chat_id":self.chat_id,
                            "update_id":update["update_id"],
                            "decision":"APPROVE" if args[0]=="/approve" else "REJECT"},
                            sort_keys=True,separators=(",",":")).encode()
        signature=hmac.new(self.key,payload,hashlib.sha256).hexdigest()
        request=urllib.request.Request(self.callback,data=payload,method="POST",
                   headers={"Content-Type":"application/json","X-Xuanjun-Signature":signature,
                            "Authorization":"Bearer "+self.auth})
        with urllib.request.urlopen(request,timeout=10) as response:
            answer=json.loads(response.read(100000).decode())
        return "ACCEPTED" if answer.get("accepted") is True else "REJECTED"
