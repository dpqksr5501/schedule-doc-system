# -*- coding: utf-8 -*-
import zipfile, xml.etree.ElementTree as ET

with zipfile.ZipFile(r'C:\Users\I\.gemini\antigravity\scratch\schedule_manager\assets\template.hwpx', 'r') as z:
    xml_text = z.read('Contents/section0.xml')
    root = ET.fromstring(xml_text)
    tbl = root.find('.//{http://www.hancom.co.kr/hwpml/2011/paragraph}tbl')
    rows = tbl.findall('{http://www.hancom.co.kr/hwpml/2011/paragraph}tr')
    for i in range(min(10, len(rows))):
        tc = rows[i].find('{http://www.hancom.co.kr/hwpml/2011/paragraph}tc')
        csz = tc.find('{http://www.hancom.co.kr/hwpml/2011/paragraph}cellSz')
        h = csz.attrib.get('height') if csz is not None else 'None'
        print(f"Row {i} height: {h}")
