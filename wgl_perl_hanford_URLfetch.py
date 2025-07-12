#!/usr/bin/env python3

# wgl_perl_hanford_URLfetch.py
# Jim Miller, 9:31 PM Tue March 21, 2023

import requests
from requests.exceptions import Timeout
import codecs
import urllib3

# Disable the InsecureRequestWarning
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

try:
    # This is used by geturl.pl to fetch the HMS page.
    response = requests.get("https://www.hanford.gov/c.cfm/hms/realtime.cfm", timeout=20, verify=False)
    
    with codecs.open('C:\\Users\\Jim\\Documents\\webcontent\\waconia\\wgl_perl_hanford_URLdump.txt', 'w', encoding=response.encoding) as file:
        file.write(response.text)
        
    print('Request to Hanford page has succeeded.')
    
except Timeout:
    print('Request to Hanford page has timed out.')
    
except Exception as e:
    print('Request to Hanford page has failed.')
    print(f'Error: {e}')