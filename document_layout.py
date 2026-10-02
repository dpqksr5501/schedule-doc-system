"""One geometry plan for the desktop preview and HWPX/HWP document engine.

Dimensions are HWPUNIT (1/7200 inch). Rows are split before a table is emitted;
notes never enlarge a printed page beyond its budget.
"""
from datetime import date, timedelta
import unicodedata

PORTRAIT_WIDTH, LANDSCAPE_WIDTH = 55543, 79384
PAGE_BUDGET, CALENDAR_BUDGET = 78000, 54000
WEEKLY_WIDTHS = [4149, 3866, 30244, 9491, 7793]
WEEKLY_COLUMNS, WEEKLY_SPANS = [0, 1, 3, 4, 5], [1, 2, 1, 1, 2]
WEEKLY_GRID = [4149, 2830, 1036, 30244, 9491, 1415, 6378]
DAILY_GRID = [6200, 9300, 14700, 13000, 12343]
DAYS = ['월', '화', '수', '목', '금', '토', '일']
COLORS = {'general': '#000000', 'gunsu': '#008000', 'v_gunsu': '#0000FF'}


def wrap(value, width, font_size=1100):
    capacity = max(2, (width - 750) / font_size)
    lines = []
    for paragraph in value.replace('\r\n', '\n').replace('\r', '\n').expandtabs(4).split('\n'):
        current, used = '', 0.0
        for character in paragraph:
            size = 1 if unicodedata.east_asian_width(character) in ('W', 'F') else 0.9 if character in 'MW@%&#' else 0.58
            if current and used + size > capacity:
                lines.append(current)
                current, used = '', 0.0
            current += character
            used += size
        lines.append(current)
    return lines or ['']


def label(value):
    day = date.fromisoformat(value)
    return f'{day.month}/{day.day}({DAYS[day.weekday()]})'


def event_title(event, annotations=False):
    title = ('[중요] ' if event['priority'] == 'important' else '')
    title += ('[미확정] ' if event['status'] == 'tentative' else '') + event['title']
    if annotations and event.get('annotation'):
        title += '\n※ ' + event['annotation']
    return title


def cell(text, column, width, span=1, font=1100, color='#000000', bold=False,
         align='LEFT', borders='', fill=None, picture=None, event=None):
    return dict(text=text, column=column, width=width, span=span, rowSpan=1,
                font=font, color=color, bold=bold, align=align, borders=borders,
                fill=fill, picture=picture, eventId=event['id'] if event else None)


def row(cells, height, kind='body', **extra):
    return dict(cells=cells, height=height, kind=kind, **extra)


def annotation_style(target, lines, offset, event, enabled):
    if enabled and event.get('annotation'):
        start = len(wrap(event_title(event), target['width'], target['font']))
        target['segments'] = [dict(text=line, font=950, color='#555555', bold=False)
                              if offset + i >= start else dict(text=line, font=target['font'])
                              for i, line in enumerate(lines)]


def paginate(items, budget):
    pages, current, used = [], [], 0
    for item in items:
        if item['height'] > budget:
            raise ValueError('한 항목이 출력 페이지보다 큽니다. 내용을 나누어 주세요.')
        if current and used + item['height'] > budget:
            pages.append(current)
            current, used = [], 0
        current.append(item)
        used += item['height']
    return pages + ([current] if current else [])


def page(kind, rows, columns, width=PORTRAIT_WIDTH, landscape=False, grid=None):
    grid = grid or (DAILY_GRID if columns == 5 else WEEKLY_GRID if columns == 7 else [width])
    return dict(kind=kind, rows=rows, columns=columns, width=width,
                height=sum(r['height'] for r in rows), landscape=landscape, grid=grid)


def _daily_header(model, day, continuation=False):
    value = date.fromisoformat(day['date'])
    title = model['dailyTitle'] + (' (계속)' if continuation else '')
    color = '#0000FF' if value.weekday() == 5 else '#FF0000' if value.weekday() == 6 else '#000000'
    return row([
        cell('', 0, sum(DAILY_GRID[:2]), 2, borders='LTB', picture='slogan'),
        cell(title, 2, sum(DAILY_GRID[2:4]), 2, font=3000 if not continuation else 2400,
             align='CENTER', borders='TB'),
        cell(f'[{value.month:02}월{value.day:02}일({DAYS[value.weekday()]})]', 4, DAILY_GRID[4],
             font=1350, color=color, align='RIGHT', borders='TRB')], 5600, 'daily-header')


def _daily_rows(model, day):
    result = []
    widths = [DAILY_GRID[0], sum(DAILY_GRID[1:4]), DAILY_GRID[4]]
    for event in day['events']:
        values = ['▶ ' + event['time'], event_title(event, model['includeAnnotation']),
                  '< ' + event['place'] + ' >' if event['place'] else '']
        lines = [wrap(v, w, f) for v, w, f in zip(values, widths, [1100, 1250, 1100])]
        for offset in range(0, max(map(len, lines)), 16):
            content = ['\n'.join(v[offset:offset + 16]) for v in lines]
            height = max(2800, max(len(v[offset:offset + 16]) for v in lines) * 1600 + 800)
            item = row([
                cell(content[0], 0, widths[0], font=1100, borders='L'),
                cell(content[1], 1, widths[1], 3, font=1250, event=event),
                cell(content[2], 4, widths[2], font=1100, align='RIGHT', borders='R')],
                height, date=day['date'], time=event['time'])
            annotation_style(item['cells'][1], lines[1][offset:offset + 16], offset, event, model['includeAnnotation'])
            result.append(item)
    return result


def _daily_block(model, day, rows, body_budget, continuation=False):
    header = _daily_header(model, day, continuation)
    spacer = row([cell('', 0, PORTRAIT_WIDTH, 5, borders='LR')], 2000, 'spacer')
    body = [dict(r, cells=[dict(c) for c in r['cells']]) for r in rows]
    remaining = body_budget - spacer['height'] - sum(r['height'] for r in body)
    if remaining < 0:
        raise ValueError('일일 일정의 페이지 높이를 초과했습니다.')
    if not body:
        body = [row([cell('', 0, PORTRAIT_WIDTH, 5, borders='LR')], remaining, 'spacer')]
    else:
        # Place sparse agendas on a working-day timeline, retaining blank hours.
        minutes = [int(r['time'][:2]) * 60 + int(r['time'][3:]) for r in body]
        beginning = min(8 * 60, minutes[0] - 60)
        ending = max(18 * 60, minutes[-1] + 60)
        weights = [minutes[0] - beginning] + [max(1, b - a) for a, b in zip(minutes, minutes[1:])] + [ending - minutes[-1]]
        total = sum(weights)
        allocated = 0
        for index, item in enumerate([spacer, *body]):
            extra = remaining - allocated if index == len(body) else remaining * weights[index] // total
            item['height'] += extra
            allocated += extra
    return [header, spacer, *body]


def _daily_pages(model):
    daily = [(day, _daily_rows(model, day)) for day in model['days']]
    # Two weekend days share one sheet only when both fit at readable sizes.
    half_body = PAGE_BUDGET // 2 - 5600
    if len(daily) == 2 and all(sum(r['height'] for r in rows) + 4000 <= half_body for _, rows in daily):
        combined = []
        for day, rows in daily:
            block = _daily_block(model, day, rows, half_body)
            block[0]['cells'][0]['borders'] = 'L' + ('T' if not combined else '')
            block[0]['cells'][1]['borders'] = 'T' if not combined else ''
            block[0]['cells'][2]['borders'] = 'R' + ('T' if not combined else '')
            combined += block
        for c in combined[-1]['cells']:
            c['borders'] += 'B'
        return [page('daily-weekend', combined, 5)]
    pages = []
    for day, rows in daily:
        chunks = paginate(rows, PAGE_BUDGET - 9600) or [[]]
        for index, chunk in enumerate(chunks):
            block = _daily_block(model, day, chunk, PAGE_BUDGET - 5600, bool(index))
            for c in block[-1]['cells']:
                c['borders'] += 'B'
            pages.append(page('daily', block, 5))
    return pages


def _weekly_header(model):
    headings = [row([
        cell('', 0, 6979, 2, picture='symbol'),
        cell('주 간 주 요 행 사 계 획\n(' + model['period_str'] + ')', 2, 42186, 4,
             font=1800, bold=True, align='CENTER'),
        cell('', 6, 6378, picture='slogan')], 6800, 'weekly-header'),
        row([cell(model['created_date_str'], 0, PORTRAIT_WIDTH, 7, font=900, align='RIGHT')], 1400, 'created'),
        row([cell(t, c, w, s, font=1100, bold=True, align='CENTER', borders='LTRB')
             for t, c, w, s in zip(['일자', '시간', '행 사 명', '장 소', '주관/관련부서'],
                                  WEEKLY_COLUMNS, WEEKLY_WIDTHS, WEEKLY_SPANS)], 2200, 'column-header')]
    headings[0]['cells'][1]['segments'] = [dict(text='주 간 주 요 행 사 계 획', font=2300),
                                           dict(text='(' + model['period_str'] + ')', font=1400)]
    return headings


def _weekly_pages(model):
    rows = []
    for day in model['days']:
        for event in day['events'] or [None]:
            daily_label = str(date.fromisoformat(day['date']).day) + '(' + DAYS[date.fromisoformat(day['date']).weekday()] + ')'
            values = [daily_label, event['time'] if event else '',
                      event_title(event, model['includeAnnotation']) if event else '',
                      event['place'] if event else '', event['dept'] if event else '']
            lines = [wrap(v, w, 1000 if i < 2 else 1100) for i, (v, w) in enumerate(zip(values, WEEKLY_WIDTHS))]
            for offset in range(0, max(map(len, lines)), 20):
                contents = ['\n'.join(v[offset:offset + 20]) for v in lines]
                contents[0] = daily_label
                if offset:
                    contents[1] = ''
                color = COLORS[event['attendee']] if event else '#000000'
                cells = [cell(t, c, w, s, font=1000 if index < 2 else 1100, color=color if index else '#000000',
                              bold=bool(index and event and (event['attendee'] != 'general' or event['priority'] == 'important')),
                              align='CENTER' if index == 0 else 'LEFT', borders='LR',
                              event=event if index == 2 else None)
                         for index, (t, c, w, s) in enumerate(zip(contents, WEEKLY_COLUMNS, WEEKLY_WIDTHS, WEEKLY_SPANS))]
                height = max(1900, max(len(v[offset:offset + 20]) for v in lines[1:]) * 1400 + 500)
                if event:
                    annotation_style(cells[2], lines[2][offset:offset + 20], offset, event, model['includeAnnotation'])
                rows.append(row(cells, height, date=day['date']))
    pages = []
    for chunk in paginate(rows, PAGE_BUDGET - 10400):
        # Merge each date within this page; a continuation page starts a new cell.
        for start in range(len(chunk)):
            if start and chunk[start - 1]['date'] == chunk[start]['date']:
                continue
            end = start + 1
            while end < len(chunk) and chunk[end]['date'] == chunk[start]['date']:
                end += 1
            chunk[start]['cells'][0].update(rowSpan=end - start, mergedHeight=sum(r['height'] for r in chunk[start:end]))
            chunk[start]['cells'][0]['borders'] = 'LTRB'
            for item in chunk[start + 1:end]:
                item['cells'] = item['cells'][1:]
            for c in chunk[start]['cells'][1:]:
                c['borders'] += 'T'
            for c in chunk[end - 1]['cells']:
                c['borders'] += 'B'
        pages.append(page('weekly', _weekly_header(model) + chunk, 7))
    return pages


def _monthly_pages(model):
    first, last = date.fromisoformat(model['start']), date.fromisoformat(model['end'])
    cursor = first - timedelta(days=first.weekday())
    finish = last + timedelta(days=6 - last.weekday())
    days = {d['date']: d for d in model['days']}
    widths = [LANDSCAPE_WIDTH * weight // 100 for weight in [16, 16, 16, 16, 16, 10, 10]]
    widths[-1] += LANDSCAPE_WIDTH - sum(widths)
    groups = []
    while cursor <= finish:
        dates = [cursor + timedelta(days=i) for i in range(7)]
        contents = []
        for day, width in zip(dates, widths):
            value = '\n'.join(e['time'] + ' ' + event_title(e, model['includeAnnotation']) +
                              ('\n(' + e['place'] + ')' if e['place'] else '')
                              for e in days.get(day.isoformat(), {}).get('events', []))
            contents.append(wrap(value, width, 950))
        for offset in range(0, max(map(len, contents)), 24):
            headings = [cell(label(d.isoformat()) + (' 계속' if offset else ''), i, w,
                             font=1100, bold=True, align='CENTER', color='#FF0000' if i >= 5 else '#000000',
                             borders='LTRB', fill='#FFFFE8') for i, (d, w) in enumerate(zip(dates, widths))]
            body = [cell('\n'.join(v[offset:offset + 24]), i, w, font=950, borders='LTRB',
                         fill='#F7F7F7' if not first <= d <= last else None)
                    for i, (d, w, v) in enumerate(zip(dates, widths, contents))]
            height = max(5500, max(len(v[offset:offset + 24]) for v in contents) * 1250 + 600)
            head_height = 3000 if offset else 1900
            groups.append(dict(rows=[row(headings, head_height, 'calendar-date'), row(body, height, 'calendar-body')], height=head_height + height))
        cursor += timedelta(days=7)
    chunks = paginate(groups, CALENDAR_BUDGET - 4200)
    pages = []
    for chunk in chunks:
        spare = CALENDAR_BUDGET - 4200 - sum(g['height'] for g in chunk)
        for i, group in enumerate(chunk):
            extra = spare // len(chunk) + (spare % len(chunk) if i == len(chunk) - 1 else 0)
            group['rows'][1]['height'] += extra
        heading = row([cell('월간 일정표   ' + model['period_str'], 0, LANDSCAPE_WIDTH, 7,
                            font=1800, color='#FF0000', bold=True, align='CENTER')], 4200, 'monthly-header')
        pages.append(page('monthly', [heading] + [r for g in chunk for r in g['rows']], 7, LANDSCAPE_WIDTH, True, widths))
    return pages


def _appendix_pages(model):
    if not model['includeNotes']:
        return []
    landscape = model['view'] == 'monthly'
    width, budget = (LANDSCAPE_WIDTH, CALENDAR_BUDGET) if landscape else (PORTRAIT_WIDTH, PAGE_BUDGET)
    rows = []
    for day in model['days']:
        for event in day['events']:
            values = []
            for caption, key in [('출력 주석', 'annotation'), ('참석 예정자', 'participants'), ('담당 / 연락', 'contact'),
                                 ('진행 / 준비', 'preparation'), ('업무 메모', 'notes')]:
                if event.get(key):
                    values.append(caption + ': ' + event[key])
            if event['checklist']:
                values.append('준비 확인 목록:\n' + '\n'.join(('[완료] ' if c['done'] else '[미완료] ') + c['text'] for c in event['checklist']))
            if not values:
                continue
            content = wrap(label(day['date']) + ' ' + event['time'] + ' ' + event['title'] + '\n' + '\n'.join(values), width)
            for offset in range(0, len(content), 22):
                value = '\n'.join(content[offset:offset + 22])
                if offset:
                    value = event['time'] + ' ' + event['title'][:35] + ' (계속)\n' + value
                rows.append(row([cell(value, 0, width, borders='LTRB', event=event)],
                                len(value.split('\n')) * 1450 + 1000, 'reference'))
    pages = []
    for chunk in paginate(rows, budget - 5000):
        heading = row([cell('업무 참고자료 · 내부 공유용\n' + model['period_str'], 0, width,
                            font=1600, bold=True, align='CENTER')], 5000, 'reference-header')
        pages.append(page('reference', [heading] + chunk, 1, width, landscape))
    return pages


def build_plan(model):
    pages = {'daily': _daily_pages, 'weekly': _weekly_pages, 'monthly': _monthly_pages}[model['view']](model)
    pages += _appendix_pages(model)
    return dict(title=model['title'], period=model['period_str'], pages=pages,
                eventCount=sum(len(d['events']) for d in model['days']),
                includeAnnotation=model['includeAnnotation'], includeNotes=model['includeNotes'])
