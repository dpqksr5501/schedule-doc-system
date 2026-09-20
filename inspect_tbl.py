# -*- coding: utf-8 -*-
import zipfile, xml.etree.ElementTree as ET

with zipfile.ZipFile(r'C:\Users\I\.gemini\antigravity\scratch\schedule_manager\assets\template.hwpx', 'r') as z:
    xml_text = z.read('Contents/section0.xml')
    root = ET.fromstring(xml_text)
    tbl = root.find('.//{http://www.hancom.co.kr/hwpml/2011/paragraph}tbl')
    rows = tbl.findall('{http://www.hancom.co.kr/hwpml/2011/paragraph}tr')
    
    print(f"Total rows: {len(rows)}")
    for r_idx in [2, 3, 4, 5]:
        r = rows[r_idx]
        tcs = r.findall('{http://www.hancom.co.kr/hwpml/2011/paragraph}tc')
        print(f"\nRow {r_idx}: num_tcs={len(tcs)}")
        for i, tc in enumerate(tcs):
            addr = tc.find('{http://www.hancom.co.kr/hwpml/2011/paragraph}cellAddr')
            span = tc.find('{http://www.hancom.co.kr/hwpml/2011/paragraph}cellSpan')
            sz = tc.find('{http://www.hancom.co.kr/hwpml/2011/paragraph}cellSz')
            txt = ''.join([t.text for t in tc.findall('.//{http://www.hancom.co.kr/hwpml/2011/paragraph}t') if t.text])
            ca = addr.get('colAddr') if addr is not None else 'None'
            ra = addr.get('rowAddr') if addr is not None else 'None'
            cs = span.get('colSpan') if span is not None else 'None'
            rs = span.get('rowSpan') if span is not None else 'None'
            w = sz.get('width') if sz is not None else 'None'
            print(f"  tc {i}: colAddr={ca}, rowAddr={ra}, colSpan={cs}, rowSpan={rs}, width={w}, txt={txt[:15]}")
