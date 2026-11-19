import unittest
from jinja2 import Environment, FileSystemLoader

class ParentChildDefaultsTests(unittest.TestCase):
    def render(self, selected):
        children=[dict(studentId=i,student_name='Child '+str(i),student_code='S'+str(i),ADMNO='A'+str(i),class_name='Class 1',section_name='A') for i in range(1,6)]
        env=Environment(loader=FileSystemLoader('app/templates'))
        return env.get_template('_parent_children.html').render(student_options=children,selected_children=selected)

    def test_existing_children_are_selected_in_matching_slots(self):
        html=self.render([2,4])
        self.assertIn('value="2" selected',html)
        self.assertIn('value="4" selected',html)
        self.assertEqual(html.count(' selected'),2)
        self.assertEqual(html.count('name="child_ids"'),3)

    def test_new_parent_has_three_empty_slots(self):
        html=self.render([])
        self.assertNotIn(' selected',html)
        self.assertEqual(html.count('name="child_ids"'),3)

    def test_submitted_string_ids_and_more_than_three_children(self):
        html=self.render(['1','2','3','4'])
        self.assertEqual(html.count(' selected'),4)
        self.assertEqual(html.count('name="child_ids"'),4)

if __name__=='__main__':unittest.main()
