# -*- coding: utf-8 -*-
import zipfile, xml.etree.ElementTree as ET

with zipfile.ZipFile(r'C:\Users\I\.gemini\antigravity\scratch\schedule_manager\assets\template.hwpx', 'r') as z:
    xml_text = z.read('Contents/header.xml')
    root = ET.fromstring(xml_text)
    border_fills = root.findall('.//{http://www.hancom.co.kr/hwpml/2011/head}borderFill')
    for bf in border_fills:
        bf_id = bf.attrib.get('id')
        if bf_id in ['5', '7', '8', '10', '12', '18', '20', '21']:
            bb = bf.find('{http://www.hancom.co.kr/hwpml/2011/head}bottomBorder')
            lb = bf.find('{http://www.hancom.co.kr/hwpml/2011/head}leftBorder')
            rb = bf.find('{http://www.hancom.co.kr/hwpml/2011/head}rightBorder')
            tb = bf.find('{http://www.hancom.co.kr/hwpml/2011/head}topBorder')
            print(f"borderFill id={bf_id}:")
            if bb is not None: print(f"  bottom: type={bb.attrib.get('type')}, width={bb.attrib.get('width')}")
            if lb is not None: print(f"  left: type={lb.attrib.get('type')}, width={lb.attrib.get('width')}")
            if rb is not None: print(f"  right: type={rb.attrib.get('type')}, width={rb.attrib.get('width')}")
            if tb is not None: print(f"  top: type={tb.attrib.get('type')}, width={tb.attrib.get('width')}")
