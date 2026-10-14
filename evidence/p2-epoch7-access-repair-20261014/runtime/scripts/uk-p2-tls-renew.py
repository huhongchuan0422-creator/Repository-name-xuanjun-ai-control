#!/usr/bin/env python3
import os,sys
sys.path.insert(0,os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'stage1'))
from p2_tls_lifecycle import renew
if __name__=='__main__':renew()
