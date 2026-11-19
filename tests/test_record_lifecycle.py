import unittest
from unittest.mock import patch
from app.services import user_lifecycle as U,student_lifecycle as S,user_access as A

class RecordLifecycleTests(unittest.TestCase):
    def test_self_and_super_admin_accounts_are_protected(self):
        root={'id':1,'user_type':'0','is_admin':True}
        self.assertFalse(U.can_manage(root,root))
        self.assertFalse(U.can_manage(root,{'id':2,'user_type':'9','is_admin':True}))
        self.assertTrue(U.can_manage(root,{'id':3,'user_type':'2','is_admin':False}))

    def test_reset_delegation_does_not_grant_user_deletion(self):
        with self.assertRaises(PermissionError):U.apply({'id':1,'is_admin':False},'trash',['2'])
        with self.assertRaises(PermissionError):S.apply({'id':1,'is_admin':False},'trash',['2'])

    def test_academic_references_block_purge_and_ignore_configuration(self):
        columns=[{'TABLE_NAME':'exam_marks','COLUMN_NAME':'studentId'},{'TABLE_NAME':'student_subject_exclusion','COLUMN_NAME':'studentId'}]
        with patch.object(S.db,'query',return_value=columns),patch.object(S.db,'scalar',return_value=1) as query:
            self.assertEqual(S.academic_references(10),['exam_marks']);query.assert_called_once()

if __name__=='__main__':unittest.main()
