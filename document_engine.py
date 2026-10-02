"""Paginated daily, weekly and calendar HWPX output; preserve the package contract."""
from pathlib import Path
from datetime import date, timedelta
import copy
import os
import tempfile
import zipfile
import xml.etree.ElementTree as ET
from app_paths import resource_dir
from schedule_domain import text, today, timestamp, valid_date
from document_layout import build_plan, wrap

NS_HP = 'http://www.hancom.co.kr/hwpml/2011/paragraph'
NS_HC = 'http://www.hancom.co.kr/hwpml/2011/core'
NS_HH = 'http://www.hancom.co.kr/hwpml/2011/head'
HP, HH = '{' + NS_HP + '}', '{' + NS_HH + '}'
WIDTHS, ADDRS, SPANS = [4149, 3866, 30244, 9491, 7793], [0, 1, 3, 4, 5], [1, 2, 1, 1, 2]
DAY_NAMES = ['월', '화', '수', '목', '금', '토', '일']


def get_template_path():
    path = resource_dir() / 'assets' / 'template.hwpx'
    if not path.is_file():
        raise FileNotFoundError('한글 문서 양식이 없습니다. 프로그램을 다시 내려받아 주세요.')
    return str(path)


def set_text(paragraph, value, ref='0'):
    value = text(value, '문서 내용', 32000)
    for run in paragraph.findall(HP + 'run'):
        paragraph.remove(run)
    run = ET.SubElement(paragraph, HP + 'run', charPrIDRef=str(ref))
    lines = value.split('\n')
    node = ET.SubElement(run, HP + 't')
    node.text = lines[0]
    # OWPML CT owns lineBreak; it is not a sibling of t inside CRunType.
    # Reference: hancom-io/hwpx-owpml-model OWPML/Class/Para/t.cpp.
    for line in lines[1:]:
        ET.SubElement(node, HP + 'lineBreak').tail = line
    for lineseg in paragraph.findall(HP + 'linesegarray'):
        paragraph.remove(lineseg)


def document_model(snapshot, request):
    if not isinstance(request, dict) or request.get('view') not in ('daily', 'weekly', 'monthly'):
        raise ValueError('일일·주간·월간 중 출력 양식을 선택해 주세요.')
    selected = date.fromisoformat(valid_date(request.get('date')))
    notes, only = request.get('includeNotes', False), request.get('gunsuOnly', False)
    annotations, weekend = request.get('includeAnnotation', False), request.get('weekendPair', True)
    if any(type(v) is not bool for v in (notes, only, annotations, weekend)):
        raise ValueError('출력 선택 정보가 올바르지 않습니다.')
    view = request['view']
    if view == 'daily':
        start = end = selected
        if weekend and selected.weekday() >= 5:
            start = selected - timedelta(days=selected.weekday() - 5)
            end = start + timedelta(days=1)
        title = snapshot['settings']['leaderTitle'] + ' 일정표' if only else '일일 일정표'
    elif view == 'weekly':
        start = selected - timedelta(days=selected.weekday())
        end, title = start + timedelta(days=6), '주간 주요행사계획'
    else:
        start = selected.replace(day=1)
        end = (start.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)
        title = f'{selected.year}년 {selected.month}월 일정표'
    events = sorted((e for e in snapshot['events'] if start.isoformat() <= e['date'] <= end.isoformat()
                     and e['status'] != 'cancelled' and (view != 'daily' or not only or e['attendee'] == 'gunsu')),
                    key=lambda e: (e['date'], e['time'], e['id']))
    days, current = [], start
    while current <= end:
        days.append({'date': current.isoformat(), 'dayLabel': f'{current.month}.{current.day}({DAY_NAMES[current.weekday()]})',
                     'events': [e for e in events if e['date'] == current.isoformat()]})
        current += timedelta(days=1)
    return {'view': view, 'title': title, 'start': start.isoformat(), 'end': end.isoformat(),
            'period_str': start.strftime('%Y. %m. %d.') + (' ~ ' + end.strftime('%Y. %m. %d.') if end != start else ''),
            'created_date_str': today().replace('-', '. ') + ' 작성 · ' + snapshot['settings']['orgName'],
            'includeNotes': notes, 'includeAnnotation': annotations, 'dailyTitle': title, 'days': days}


def _cell(proto, value, row, column, span, width, height, ref='0', last=False):
    cell = copy.deepcopy(proto)
    cell.find(HP + 'cellAddr').attrib.update(colAddr=str(column), rowAddr=str(row))
    cell.find(HP + 'cellSpan').attrib.update(colSpan=str(span), rowSpan='1')
    cell.find(HP + 'cellSz').attrib.update(width=str(width), height=str(height))
    if last:
        cell.set('borderFillIDRef', '10')
    paragraphs = cell.find(HP + 'subList')
    first = paragraphs.find(HP + 'p')
    for extra in list(paragraphs):
        if extra is not first:
            paragraphs.remove(extra)
    set_text(first, value, ref)
    return cell


def validate_grid(table):
    rows = table.findall(HP + 'tr')
    count, columns = int(table.get('rowCnt')), int(table.get('colCnt'))
    if count != len(rows):
        raise ValueError('문서의 표 행 수가 일치하지 않습니다.')
    occupied = set()
    for row in rows:
        for cell in row.findall(HP + 'tc'):
            addr, span = cell.find(HP + 'cellAddr'), cell.find(HP + 'cellSpan')
            for r in range(int(addr.get('rowAddr')), int(addr.get('rowAddr')) + int(span.get('rowSpan'))):
                for c in range(int(addr.get('colAddr')), int(addr.get('colAddr')) + int(span.get('colSpan'))):
                    if r >= count or c >= columns or (r, c) in occupied:
                        raise ValueError('문서 표의 셀 주소가 겹치거나 범위를 벗어났습니다.')
                    occupied.add((r, c))
    if len(occupied) != count * columns:
        raise ValueError('문서 표에 빠진 셀이 있습니다.')


class _Styles:
    def __init__(self, header):
        self.chars = header.find('.//' + HH + 'charProperties')
        self.paras = header.find('.//' + HH + 'paraProperties')
        self.borders = header.find('.//' + HH + 'borderFills')
        self.cache = {}

    def char(self, spec):
        key = ('char', spec['font'], spec['color'], spec['bold'])
        if key not in self.cache:
            source = next(c for c in self.chars if c.get('id') == '36')
            value = copy.deepcopy(source)
            identifier = str(max(int(c.get('id')) for c in self.chars) + 1)
            value.attrib.update(id=identifier, height=str(spec['font']), textColor=spec['color'])
            for bold in value.findall(HH + 'bold'):
                value.remove(bold)
            if spec['bold']:
                position = next((i for i, c in enumerate(value) if c.tag == HH + 'underline'), len(value))
                value.insert(position, ET.Element(HH + 'bold'))
            self.chars.append(value)
            self.chars.set('itemCnt', str(len(self.chars)))
            self.cache[key] = identifier
        return self.cache[key]

    def para(self, align):
        key = ('para', align)
        if key not in self.cache:
            value = copy.deepcopy(next(p for p in self.paras if p.get('id') == '0'))
            identifier = str(max(int(c.get('id')) for c in self.paras) + 1)
            value.set('id', identifier)
            value.find(HH + 'align').set('horizontal', align)
            for margin in value.iter(HH + 'margin'):
                for child in margin:
                    child.set('value', '0')
            for spacing in value.iter(HH + 'lineSpacing'):
                spacing.attrib.update(type='PERCENT', value='100')
            self.paras.append(value)
            self.paras.set('itemCnt', str(len(self.paras)))
            self.cache[key] = identifier
        return self.cache[key]

    def border(self, sides, fill=None):
        key = ('border', ''.join(sorted(set(sides))), fill)
        if key not in self.cache:
            value = copy.deepcopy(next(p for p in self.borders if p.get('id') == '1'))
            identifier = str(max(int(c.get('id')) for c in self.borders) + 1)
            value.set('id', identifier)
            for name, code in [('leftBorder','L'), ('rightBorder','R'), ('topBorder','T'), ('bottomBorder','B')]:
                value.find(HH + name).attrib.update(type='SOLID' if code in sides else 'NONE', width='0.1 mm', color='#000000')
            if fill:
                brush = ET.SubElement(value, '{' + NS_HC + '}fillBrush')
                ET.SubElement(brush, '{' + NS_HC + '}winBrush', faceColor=fill, hatchColor='#000000', alpha='0')
            self.borders.append(value)
            self.borders.set('itemCnt', str(len(self.borders)))
            self.cache[key] = identifier
        return self.cache[key]


def _fit_picture(source, width, height, identifier):
    picture = copy.deepcopy(source)
    picture.attrib.update(id=str(identifier), instid=str(identifier), zOrder='0')
    picture.find(HP + 'offset').attrib.update(x='0', y='0')
    picture.find(HP + 'curSz').attrib.update(width=str(width), height=str(height))
    picture.find(HP + 'sz').attrib.update(width=str(width), height=str(height))
    picture.find(HP + 'pos').attrib.update(treatAsChar='1', affectLSpacing='1', vertRelTo='PARA',
        horzRelTo='PARA', vertOffset='0', horzOffset='0', vertAlign='TOP', horzAlign='LEFT')
    picture.find(HP + 'rotationInfo').attrib.update(centerX=str(width // 2), centerY=str(height // 2))
    org = picture.find(HP + 'orgSz')
    for matrix in picture.find(HP + 'renderingInfo'):
        matrix.attrib.update(e1='1', e2='0', e3='0', e4='0', e5='1', e6='0')
        if matrix.tag.endswith('scaMatrix'):
            matrix.attrib.update(e1=str(width / int(org.get('width'))), e5=str(height / int(org.get('height'))))
    return picture


def generate_document(model, output_path):
    with zipfile.ZipFile(get_template_path()) as source:
        parts = {item.filename: source.read(item) for item in source.infolist()}
    section, header = ET.fromstring(parts['Contents/section0.xml']), ET.fromstring(parts['Contents/header.xml'])
    original = section.find('.//' + HP + 'tbl')
    if original is None or original.get('colCnt') != '7':
        raise ValueError('한글 양식의 표 구조가 예상과 다릅니다.')
    prototypes = original.findall(HP + 'tr')[3].findall(HP + 'tc')
    if [int(c.find(HP + 'cellSz').get('width')) for c in prototypes] != WIDTHS:
        raise ValueError('한글 양식의 열 너비가 변경되었습니다.')
    pictures = {}
    for pic in original.iter(HP + 'pic'):
        ref = pic.find('{' + NS_HC + '}img').get('binaryItemIDRef')
        pictures.setdefault('symbol' if ref == 'image1' else 'slogan', pic)
    plan = build_plan(model)
    pages = plan['pages']
    styles = _Styles(header)
    parent = next(p for p in list(section) if p.find('.//' + HP + 'tbl') is not None)
    first_run = copy.deepcopy(parent.findall(HP + 'run')[0])
    first_run.find('.//' + HP + 'pagePr').set('landscape', 'NARROWLY' if model['view'] == 'monthly' else 'WIDELY')
    for child in list(section):
        section.remove(child)
    preview = [model['title'], model['period_str'], model['created_date_str']]
    for data in pages:
        for data_row in data['rows']:
            preview.extend(c['text'] for c in data_row['cells'] if c['text'])
    serial = 100
    for page_index, data in enumerate(pages):
        table = copy.deepcopy(original)
        table.attrib.update(id=str(1801150963 + page_index), pageBreak='NONE', noAdjust='0', repeatHeader='0',
                            rowCnt=str(len(data['rows'])), colCnt=str(data['columns']), borderFillIDRef=styles.border(''))
        for existing in table.findall(HP + 'tr'):
            table.remove(existing)
        table.find(HP + 'sz').attrib.update(width=str(data['width']), height=str(data['height']))
        for margin in (HP + 'inMargin', HP + 'outMargin'):
            table.find(margin).attrib.update(left='0', right='0', top='0', bottom='0')
        for row_index, data_row in enumerate(data['rows']):
            target_row = ET.SubElement(table, HP + 'tr')
            for spec in data_row['cells']:
                value = _cell(prototypes[2], spec['text'], row_index, spec['column'], spec['span'], spec['width'],
                              spec.get('mergedHeight', data_row['height']), styles.char(spec))
                value.set('borderFillIDRef', styles.border(spec['borders'], spec['fill']))
                value.set('hasMargin', '1')
                value.find(HP + 'cellSpan').set('rowSpan', str(spec['rowSpan']))
                value.find(HP + 'cellMargin').attrib.update(left='180', right='180', top='180', bottom='180')
                sublist = value.find(HP + 'subList')
                sublist.set('vertAlign', 'CENTER' if data_row['kind'].endswith('header') or spec['rowSpan'] > 1 else 'TOP')
                paragraph = sublist.find(HP + 'p')
                paragraph.attrib.update(id=str(serial), paraPrIDRef=styles.para(spec['align']))
                serial += 1
                if spec.get('segments'):
                    sublist.remove(paragraph)
                    for segment in spec['segments']:
                        item = ET.SubElement(sublist, HP + 'p', id=str(serial), paraPrIDRef=styles.para(spec['align']),
                                             styleIDRef='0', pageBreak='0', columnBreak='0', merged='0')
                        set_text(item, segment['text'], styles.char({**spec, **segment}))
                        serial += 1
                if spec['picture']:
                    # Reuse the template's original binary image without redrawing its logo.
                    symbol = spec['picture'] == 'symbol'
                    width = min(spec['width'] - 700, 5600 if symbol else 14500)
                    height = min(data_row['height'] - 600, round(width * (749 / 777 if symbol else 1157 / 3392)))
                    run = paragraph.find(HP + 'run')
                    run.insert(0, _fit_picture(pictures[spec['picture']], width, height, 2000000000 + serial))
                    serial += 1
                target_row.append(value)
        validate_grid(table)
        paragraph = ET.SubElement(section, HP + 'p', id=str(serial), paraPrIDRef=styles.para('LEFT'), styleIDRef='0',
                                  pageBreak='1' if page_index else '0', columnBreak='0', merged='0')
        serial += 1
        if page_index == 0:
            paragraph.append(copy.deepcopy(first_run))
        run = ET.SubElement(paragraph, HP + 'run', charPrIDRef='0')
        run.append(table)
        ET.SubElement(run, HP + 't')
    for prefix, namespace in [('hp', NS_HP), ('hc', NS_HC), ('hh', NS_HH)]:
        ET.register_namespace(prefix, namespace)
    parts['Contents/section0.xml'] = ET.tostring(section, encoding='utf-8', xml_declaration=True)
    parts['Contents/header.xml'] = ET.tostring(header, encoding='utf-8', xml_declaration=True)
    parts['Preview/PrvText.txt'] = '\r\n'.join(preview).encode('utf-8')
    parts.pop('Preview/PrvImage.png', None)
    settings = ET.fromstring(parts['settings.xml'])
    for caret in settings.iter('{http://www.hancom.co.kr/hwpml/2011/app}CaretPosition'):
        caret.attrib.update(listIDRef='0', paraIDRef='0', pos='0')
    parts['settings.xml'] = ET.tostring(settings, encoding='utf-8', xml_declaration=True)
    for name in ('Contents/content.hpf', 'META-INF/manifest.xml', 'META-INF/container.xml'):
        root = ET.fromstring(parts[name])
        if name == 'Contents/content.hpf':
            opf = '{http://www.idpf.org/2007/opf/}'
            metadata = root.find(opf + 'metadata')
            for item in metadata:
                if item.tag == opf + 'title':
                    item.text = model['title']
                elif item.tag == opf + 'meta':
                    item.text = timestamp() if item.get('name') in ('CreatedDate', 'ModifiedDate', 'date') else ''
        for element in root.iter():
            for child in list(element):
                if any('PrvImage' in value for value in child.attrib.values()):
                    element.remove(child)
        parts[name] = ET.tostring(root, encoding='utf-8', xml_declaration=True)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    fd, staged = tempfile.mkstemp(prefix='.' + output.name, suffix='.tmp', dir=output.parent)
    os.close(fd)
    try:
        with zipfile.ZipFile(staged, 'w', zipfile.ZIP_DEFLATED) as package:
            package.writestr('mimetype', parts.pop('mimetype'), compress_type=zipfile.ZIP_STORED)
            for name, content in parts.items():
                if name.endswith(('.xml', '.hpf', '.rdf')):
                    ET.fromstring(content)
                package.writestr(name, content)
        with zipfile.ZipFile(staged) as package:
            if package.testzip() is not None:
                raise ValueError('한글 파일의 압축 검증이 실패했습니다.')
        with open(staged, 'r+b') as stream:
            os.fsync(stream.fileno())
        os.replace(staged, output)
    finally:
        if os.path.exists(staged):
            os.unlink(staged)
    return {'path': str(output), 'pages': len(pages)}
