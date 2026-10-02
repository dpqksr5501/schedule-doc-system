from datetime import date
from pathlib import Path
import tempfile
import unittest
import zipfile
import xml.etree.ElementTree as ET
from document_engine import HP, document_model, generate_document, validate_grid
from document_layout import build_plan, PAGE_BUDGET, CALENDAR_BUDGET
from schedule_domain import empty_snapshot, event_record, validate_snapshot
from main import DesktopApi
from app_paths import AppPaths


def sample(identifier='one', **values):
    raw = dict(id=identifier, date='2026-10-02', time='09:00', title='주민 간담회',
               place='군청 소회의실', dept='행정운영과', attendee='gunsu',
               annotation='주민 대표 참석 · 인사말 3분', notes='내부 전용 전달사항')
    raw.update(values)
    return event_record(raw)


def plan(snapshot, view='daily', selected='2026-10-02', **options):
    return build_plan(document_model(snapshot, dict(view=view, date=selected, **options)))


def content(pages):
    return '\n'.join(c['text'] for p in pages for r in p['rows'] for c in r['cells'])


class DocumentLayoutTests(unittest.TestCase):
    def setUp(self):
        self.snapshot = empty_snapshot()
        self.snapshot['events'] = [sample()]

    def test_v2_migration_preserves_details_and_adds_annotation(self):
        old = empty_snapshot()
        old['schemaVersion'] = 2
        old['events'] = [sample()]
        del old['events'][0]['annotation']
        migrated = validate_snapshot(old)
        self.assertEqual(migrated['schemaVersion'], 3)
        self.assertEqual(migrated['events'][0]['annotation'], '')
        self.assertEqual(migrated['events'][0]['notes'], '내부 전용 전달사항')
        self.assertEqual(old['schemaVersion'], 2)

    def test_daily_frame_and_timeline(self):
        self.snapshot['events'].append(sample('two', time='16:00'))
        page = plan(self.snapshot)['pages'][0]
        self.assertEqual(page['columns'], 5)
        self.assertEqual(page['height'], PAGE_BUDGET)
        self.assertEqual(page['rows'][0]['kind'], 'daily-header')
        self.assertEqual(page['rows'][0]['cells'][0]['picture'], 'slogan')
        body = [r for r in page['rows'] if r['kind'] == 'body']
        self.assertNotIn('B', body[0]['cells'][1]['borders'])
        self.assertIn('B', body[-1]['cells'][1]['borders'])
        self.assertIn('▶ 09:00', content([page]))
        self.assertIn('< 군청 소회의실 >', content([page]))

    def test_weekend_pair_and_explicit_single_day(self):
        self.snapshot['events'] = [sample('sat', date='2026-10-03'), sample('sun', date='2026-10-04')]
        result = plan(self.snapshot, selected='2026-10-04')
        self.assertEqual(result['eventCount'], 2)
        self.assertEqual(len(result['pages']), 1)
        headings = [r for r in result['pages'][0]['rows'] if r['kind'] == 'daily-header']
        self.assertEqual([r['cells'][-1]['color'] for r in headings], ['#0000FF', '#FF0000'])
        self.assertEqual(plan(self.snapshot, selected='2026-10-04', weekendPair=False)['eventCount'], 1)

    def test_busy_weekend_does_not_shrink_text_to_fit(self):
        self.snapshot['events'] = [sample(str(i), date='2026-10-03', title=('긴 행사명 ' * 55)) for i in range(20)]
        pages = plan(self.snapshot, selected='2026-10-03')['pages']
        self.assertGreater(len(pages), 2)
        self.assertTrue(all(p['height'] <= PAGE_BUDGET for p in pages))
        self.assertTrue(all(c['font'] >= 1100 for p in pages for r in p['rows'] if r['kind'] == 'body' for c in r['cells']))

    def test_weekly_merges_dates_and_keeps_attendance_colors(self):
        self.snapshot['events'].append(sample('two', time='10:00', attendee='v_gunsu', priority='important'))
        result = plan(self.snapshot, 'weekly')
        cells = [c for p in result['pages'] for r in p['rows'] for c in r['cells']]
        dates = [c for c in cells if c['column'] == 0 and c['text'] == '2(금)']
        self.assertEqual(len(dates), 1)
        self.assertEqual(dates[0]['rowSpan'], 2)
        self.assertEqual(next(c['color'] for c in cells if c['eventId'] == 'two'), '#0000FF')

    def test_monthly_dates_cover_month_and_keep_narrow_weekends(self):
        for selected in ('2026-08-03', '2026-02-01', '2028-02-29', '2026-03-31'):
            result = plan(self.snapshot, 'monthly', selected)
            page = result['pages'][0]
            self.assertEqual(len(result['pages']), 1)
            self.assertEqual(page['height'], CALENDAR_BUDGET)
            self.assertLess(page['grid'][-1], page['grid'][0])
            labels = [c['text'] for r in page['rows'] if r['kind'] == 'calendar-date' for c in r['cells']]
            model = document_model(self.snapshot, dict(view='monthly', date=selected))
            for day in model['days']:
                d = date.fromisoformat(day['date'])
                expected = f'{d.month}/{d.day}(' + ['월','화','수','목','금','토','일'][d.weekday()] + ')'
                self.assertIn(expected, labels)
            self.assertEqual(len(set(labels)), len(labels))

    def test_notes_have_three_separate_output_scopes(self):
        default = plan(self.snapshot)
        summary = plan(self.snapshot, includeAnnotation=True)
        detail = plan(self.snapshot, includeNotes=True)
        self.assertNotIn('인사말', content(default['pages']))
        self.assertIn('인사말', content(summary['pages']))
        self.assertNotIn('내부 전용', content(summary['pages']))
        official = [p for p in detail['pages'] if p['kind'] != 'reference']
        reference = [p for p in detail['pages'] if p['kind'] == 'reference']
        self.assertNotIn('내부 전용', content(official))
        self.assertIn('내부 전용', content(reference))

    def test_long_annotation_and_notes_keep_content_and_valid_grid(self):
        self.snapshot['events'][0]['annotation'] = '출력 주석입니다. ' * 50
        self.snapshot['events'][0]['notes'] = '\n'.join(f'업무 사항 {i:03}' for i in range(200))
        self.snapshot = validate_snapshot(self.snapshot)
        with tempfile.TemporaryDirectory() as directory:
            for view in ('daily', 'weekly', 'monthly'):
                model = document_model(self.snapshot, dict(view=view, date='2026-10-02', includeNotes=True, includeAnnotation=True))
                planned = build_plan(model)
                target = Path(directory) / (view + '.hwpx')
                saved = generate_document(model, target)
                self.assertEqual(saved['pages'], len(planned['pages']))
                self.assertIn('업무 사항 199', content(planned['pages']))
                with zipfile.ZipFile(target) as package:
                    root = ET.fromstring(package.read('Contents/section0.xml'))
                    tables = list(root.iter(HP + 'tbl'))
                    self.assertEqual(len(tables), len(planned['pages']))
                    for table, page in zip(tables, planned['pages']):
                        validate_grid(table)
                        self.assertEqual(int(table.get('colCnt')), page['columns'])
                        for row, expected in zip(table.findall(HP + 'tr'), page['rows']):
                            self.assertEqual([int(c.find(HP + 'cellSz').get('width')) for c in row], [c['width'] for c in expected['cells']])

    def test_preview_uses_committed_data_and_validates_choices(self):
        with tempfile.TemporaryDirectory() as directory:
            api = DesktopApi(AppPaths.isolated(directory))
            result = api.preview_document(dict(view='daily', date='2026-10-02'))
            self.assertTrue(result['success'])
            self.assertEqual(result['plan']['eventCount'], 0)
            api._store.save(self.snapshot, 0)
            result = api.preview_document(dict(view='daily', date='2026-10-02', includeAnnotation=True))
            self.assertEqual(result['plan']['eventCount'], 1)
            self.assertEqual(result['revision'], 1)
        for key in ('includeAnnotation', 'includeNotes', 'weekendPair'):
            with self.assertRaises(ValueError):
                document_model(self.snapshot, dict(view='daily', date='2026-10-02', **{key: 1}))
        self.snapshot['events'][0]['annotation'] = '가' * 601
        with self.assertRaises(ValueError):
            validate_snapshot(self.snapshot)
