import unittest
from unittest.mock import patch
from flask import Flask
from werkzeug.exceptions import Forbidden
from app.services import features as F,access as A
from app.blueprints import marks as M

class TeacherEligibilityTests(unittest.TestCase):
    def setUp(self):
        self.app=Flask(__name__)
        self.teacher={'id':123,'is_admin':False,'is_teacher':True}

    def test_only_teacher_subject_contexts_become_visible_pairs(self):
        rows=[dict(classId=4,sectionId=5,examId=1,subjectId=8),dict(classId=4,sectionId=5,examId=2,subjectId=8)]
        with patch.object(F,'mark_contexts',return_value=rows):
            self.assertEqual(F.pairs('entry',self.teacher),[{'classId':4,'sectionId':5}])
        with patch.object(F,'mark_contexts',return_value=[]):self.assertEqual(F.pairs('special',self.teacher),[])

    def test_subject_context_query_checks_assignment_exam_and_enrollment(self):
        with self.app.test_request_context('/'),patch.object(F.enrollment if hasattr(F,'enrollment') else __import__('app.services.enrollment',fromlist=['ensure']),'ensure'),patch.object(F.db,'query',return_value=[]) as query:
            F.mark_contexts(self.teacher,'entry')
            sql,args=query.call_args.args
            for required in ('assign_teacher','t.t_id=%s','assign_subject','exam_subtype','student_subject_exclusion','students st'):
                self.assertIn(required,sql)
            self.assertEqual(args,['0',123])

    def test_special_exams_do_not_leak_normal_subject_exams(self):
        rows=[dict(classId=4,sectionId=5,examId=2,subjectId=8),dict(classId=6,sectionId=7,examId=1,subjectId=9)]
        with patch.object(F,'mark_contexts',return_value=rows),patch.object(F.db,'query',return_value=[{'examId':2,'exam_name':'Second'}]) as query:
            self.assertEqual(F.mark_exams(self.teacher,'special',4,5)[0]['examId'],2)
            self.assertEqual(query.call_args.args[1],[2])

    def test_invalid_post_class_section_and_exam_are_denied(self):
        pairs=[{'classId':4,'sectionId':5}];classes=[{'classId':4}]
        for query in ('class_id=99&section_id=5&exam_id=1','class_id=4&section_id=99&exam_id=1','class_id=4&section_id=5&exam_id=99'):
            with self.app.test_request_context('/marks/entry?'+query,method='POST'),patch.object(F,'pairs',return_value=pairs),patch.object(F,'nav_allowed',return_value=True),patch.object(A,'classes_for',return_value=classes),patch.object(A,'sections_for',return_value=[{'sectionId':5}]),patch.object(F,'mark_exams',return_value=[{'examId':1}]):
                with self.assertRaises(Forbidden):M._ctx(self.teacher)

    def test_editing_disabled_hides_write_pages_but_not_marks_list(self):
        with patch.object(A,'editing_enabled',return_value=False):
            self.assertFalse(F.nav_allowed(self.teacher,'marks.entry'))
            self.assertFalse(F.nav_allowed(self.teacher,'marks.special'))
            self.assertFalse(F.nav_allowed(self.teacher,'classteacher.comments'))
            self.assertTrue(F.nav_allowed(self.teacher,'marks.marks_list'))

if __name__=='__main__':unittest.main()
