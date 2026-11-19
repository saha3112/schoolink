import unittest
from unittest.mock import patch
from app.services import csvio as C


class CsvMappingTests(unittest.TestCase):
    def setUp(self):
        rollback = patch.object(C.db, 'rollback')
        rollback.start()
        self.addCleanup(rollback.stop)

    def parent(self):
        return dict(id=1, phone_1='9000000001', fname='Parent', mname='', lname='', phone_2='', secondary_name='', address='')

    def test_parent_sample_round_trip_and_siblings(self):
        parent = self.parent()
        kids = [dict(studentId=3, student_code='S1', student_name='Child One', parent_id=1), dict(studentId=4, student_code='S2', student_name='Child Two', parent_id=1)]
        headers = ['mobile', 'first_name', 'middle_name', 'last_name', 'alternate_phone', 'secondary_name', 'address', 'student_codes', 'children_names']
        rows = [['9000000001', 'Parent', '', '', '', '', '', 'S1; S2', 'Child One; Child Two']]
        headers, rows = C.read_csv(C.to_csv_bytes(headers, rows))
        self.assertEqual(rows[0][-2], 'S1; S2')
        self.assertEqual(rows[0][-1], 'Child One; Child Two')
        with patch.object(C.db, 'query', side_effect=[[parent], [dict(k, parent_id=None) for k in kids]]), patch.object(C.db, 'execute') as write, patch.object(C.db, 'commit'):
            result = C._import_parents(headers, rows)
            self.assertTrue(result['ok'])
            self.assertEqual(write.call_count, 2)
            self.assertIn('Linked 2', result['message'])

    def test_parent_sample_uses_only_examples(self):
        with patch.object(C.db, 'query') as query:
            headers, rows = C.sample(dict(kind='parents'))
            query.assert_not_called()
        headers, rows = C.read_csv(C.to_csv_bytes(headers, rows))
        self.assertEqual(len(rows), 2)
        self.assertIn('children_names', headers)
        self.assertEqual(rows[0][headers.index('student_codes')], 'SAMPLE001; SAMPLE002')
        self.assertEqual(rows[0][headers.index('admission_numbers')], 'ADM001; ADM002')
        self.assertTrue(all(len(row) == len(headers) for row in rows))

    def test_admission_only_and_mismatched_identifiers(self):
        from app.services.parent_links import resolve_children, LinkError
        students = [dict(studentId=1, student_code='S1', ADMNO='A1'), dict(studentId=2, student_code='S2', ADMNO='A2'), dict(studentId=3, student_code='S3', ADMNO='A3')]
        self.assertEqual([s['studentId'] for s in resolve_children(students, '', 'A1; A2; A3')], [1, 2, 3])
        self.assertEqual(len(resolve_children(students, 'S1; S2; S3', 'A1; A2; A3')), 3)
        self.assertEqual(resolve_children(students, '', ''), [])
        with self.assertRaises(LinkError):
            resolve_children(students, 'S1', 'A2')

    def test_csv_new_parent_and_three_children(self):
        students = [dict(studentId=i, student_code=f'S{i}', ADMNO=f'A{i}', parent_id=None) for i in range(1, 4)]
        headers = ['mobile', 'first_name', 'student_codes', 'admission_numbers', 'initial_password']
        with patch.object(C.db, 'query', side_effect=[[], students]), patch.object(C.db, 'one', return_value=None), patch('app.services.parent_links.create_parent', return_value=90) as create, patch.object(C.db, 'execute') as write, patch.object(C.db, 'commit'):
            result = C._import_parents(headers, [['9000000001', 'Parent', 'S1; S2; S3', 'A1; A2; A3', 'test-password']])
            self.assertTrue(result['ok'])
            create.assert_called_once()
            self.assertEqual(write.call_count, 3)
            self.assertEqual([call.args[1] for call in write.call_args_list], [(90, 1), (90, 2), (90, 3)])

    def test_conflicting_parent_links_write_nothing(self):
        second = dict(self.parent(), id=2, phone_1='9000000002')
        student = dict(studentId=3, student_code='S1', ADMNO='A1', parent_id=None)
        with patch.object(C.db, 'query', side_effect=[[self.parent(), second], [student]]), patch.object(C.db, 'execute') as write:
            result = C._import_parents(['mobile', 'student_codes'], [['9000000001', 'S1'], ['9000000002', 'S1']])
            self.assertFalse(result['ok'])
            write.assert_not_called()

    def test_manual_create_links_three_optional_children(self):
        from flask import Flask
        from app.blueprints import parents
        app = Flask(__name__)
        app.secret_key = 'test'
        app.register_blueprint(parents.bp)
        children = [dict(studentId=i) for i in range(1, 4)]
        with app.test_request_context('/parents/create', method='POST', data={'fname':'Parent', 'mobile':'9000000001', 'initial_password':'test-password', 'child_ids':['1','2','3']}), patch.object(parents, '_student_options', return_value=children), patch.object(C.db, 'one', return_value=None), patch('app.services.parent_links.create_parent', return_value=90), patch.object(C.db, 'execute') as write, patch.object(C.db, 'commit'):
            response = parents.create.__wrapped__()
            self.assertEqual(response.status_code, 302)
            self.assertEqual(write.call_count, 3)
        from werkzeug.datastructures import MultiDict
        self.assertEqual(parents._chosen_children(MultiDict(), children), set())

    def test_optional_parent_email_import(self):
        for email in ('', 'parent@example.com', 'invalid-email'):
            with self.subTest(email=email), patch.object(C.db, 'query', return_value=[dict(self.parent(), email='old@example.com')]), patch.object(C.db, 'execute') as write, patch.object(C.db, 'commit'):
                result = C._import_parents(['mobile', 'email'], [['9000000001', email]])
                self.assertEqual(result['ok'], email != 'invalid-email')
                if email == 'parent@example.com':
                    self.assertEqual(write.call_args.args[1], ['parent@example.com', 1])
                else:
                    write.assert_not_called()

    def test_edit_login_phone_sync_and_duplicate_rejection(self):
        from flask import Flask
        from app.blueprints import parents
        app = Flask(__name__)
        app.secret_key = 'test'
        app.register_blueprint(parents.bp)
        parent = dict(self.parent(), user_id='50')
        for conflict in (None, {'id':2}):
            with self.subTest(conflict=conflict), app.test_request_context('/parents/1', method='POST', data={'action':'save', 'fname':'Parent', 'mobile':'9000000009', 'phone_2':'', 'email':'contact@example.com', 'secondary_name':'Second Parent'}), patch.object(parents, '_scope', return_value=None), patch.object(parents, '_children', return_value={}), patch.object(parents, 'current_user', return_value={'is_admin':True}), patch.object(C.db, 'one', side_effect=[parent, conflict, None]), patch.object(C.db, 'execute') as write, patch.object(C.db, 'commit') as commit:
                response = parents.detail.__wrapped__(1)
                self.assertEqual(response.status_code, 302)
                if conflict:
                    write.assert_not_called()
                    commit.assert_not_called()
                else:
                    self.assertEqual(write.call_count, 2)
                    self.assertIn('phone_1=%s', write.call_args_list[0].args[0])
                    self.assertEqual(write.call_args_list[0].args[1][3], '')
                    self.assertEqual(write.call_args_list[1].args[1], ('9000000009', 'Parent', '50'))
                    commit.assert_called_once()

    def test_parent_name_falls_back_to_account(self):
        from app.blueprints.parents import _name, _fill_parent_name
        parent = dict(self.parent(), fname='', account_name='Rina Das')
        self.assertEqual(_name(parent), 'Rina Das')
        self.assertEqual(_fill_parent_name(parent)['fname'], 'Rina Das')
        self.assertEqual(_name(dict(self.parent(), fname='', account_name='Parent')), '')
        self.assertEqual(_name(dict(self.parent(), account_name='Other Name')), 'Parent')

    def test_parent_sample_contains_all_contact_fields(self):
        headers, rows = C.sample(dict(kind='parents'))
        self.assertTrue({'first_name','middle_name','last_name','mobile','alternate_phone','secondary_name','email','occupation','address','student_codes','admission_numbers','initial_password'}.issubset(headers))
        self.assertTrue(all(len(row) == len(headers) for row in rows))

    def test_parent_list_missing_name_uses_code_without_dash(self):
        from jinja2 import Environment, ChoiceLoader, DictLoader, FileSystemLoader
        env = Environment(loader=ChoiceLoader([DictLoader({'layout.html':'{% block content %}{% endblock %}', '_pager.html':'{% macro pager(p) %}{% endmacro %}'}), FileSystemLoader('app/templates')]))
        env.globals['url_for'] = lambda *args, **kw: '/parents/'
        row = dict(self.parent(), name='', code='PAR01181843', children=[], email='', occupation='')
        html = env.get_template('parents_list.html').render(rows=[row], p={'total':1}, me={'is_admin':True}, classes=[], sections=[], q='', cls=None, sec=None)
        self.assertIn('<b>PAR01181843</b>', html)
        self.assertNotIn('<b>—</b>', html)
        self.assertEqual(html.count('PAR01181843'), 1)

    def test_invalid_mapping_writes_nothing(self):
        with patch.object(C.db, 'query', side_effect=[[self.parent()], []]), patch.object(C.db, 'execute') as write, patch.object(C.db, 'commit') as commit:
            result = C._import_parents(['mobile', 'first_name', 'student_codes'], [['9000000001', 'Changed', 'MISSING']])
            self.assertFalse(result['ok'])
            write.assert_not_called()
            commit.assert_not_called()

    def test_student_reordered_headings(self):
        with patch.object(C.db, 'query', side_effect=[[dict(classId=1, class_name='Class 1')], [dict(sectionId=2, class_id=1, section_name='A')], []]), patch.object(C.db, 'execute') as write, patch.object(C.db, 'commit'):
            result = C._import_students({}, ['section_name', 'roll', 'first_name', 'student_code', 'class_name'], [['A', '1', 'Aarav', 'S1', 'Class 1']])
            self.assertTrue(result['ok'])
            self.assertEqual(write.call_args.args[1], ('N/A', 'S1', 'Aarav', 1, 2, 1))

    def test_student_missing_name_rejected(self):
        with patch.object(C.db, 'query', side_effect=[[dict(classId=1, class_name='Class 1')], [dict(sectionId=2, class_id=1, section_name='A')], []]), patch.object(C.db, 'execute') as write:
            result = C._import_students({}, ['student_id', 'student_code', 'first_name', 'last_name', 'roll', 'class_name', 'section_name'], [['', 'S1', '', '', '1', 'Class 1', 'A']])
            self.assertFalse(result['ok'])
            write.assert_not_called()

if __name__ == '__main__':
    unittest.main()
