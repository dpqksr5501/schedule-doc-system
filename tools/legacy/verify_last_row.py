# -*- coding: utf-8 -*-
import zipfile, xml.etree.ElementTree as ET

p = r"C:\Users\I\Desktop\군수실_일정_출력문서\주간주요행사계획(26.09.21.~09.27.)_테스트출력.hwpx"
with zipfile.ZipFile(p, 'r') as z:
    xml_text = z.read('Contents/section0.xml')
    root = ET.fromstring(xml_text)
    tbl = root.find('.//{http://www.hancom.co.kr/hwpml/2011/paragraph}tbl')
    sz = tbl.find('{http://www.hancom.co.kr/hwpml/2011/paragraph}sz')
    print("Tbl sz height:", sz.attrib.get('height') if sz is not None else 'None')
    rows = tbl.findall('{http://www.hancom.co.kr/hwpml/2011/paragraph}tr')
    last_r = rows[-1]
    tcs = last_r.findall('{http://www.hancom.co.kr/hwpml/2011/paragraph}tc')
    print(f"Last row cells count: {len(tcs)}")
    for i, tc in enumerate(tcs):
        bf = tc.attrib.get('borderFillIDRef')
        csz = tc.find('{http://www.hancom.co.kr/hwpml/2011/paragraph}cellSz')
        h = csz.attrib.get('height') if csz is not None else 'None'
        print(f"  tc {i}: borderFill={bf}, height={h}")
