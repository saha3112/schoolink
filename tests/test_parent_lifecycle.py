import unittest
from unittest.mock import patch
from app.services import parent_lifecycle as L

class ParentLifecycleTests(unittest.TestCase):
    def test_teacher_and_invalid_selections_are_rejected(self):
        with self.assertRaises(PermissionError):L.apply({'id':1,'is_admin':False},'trash',['1'])
        for action,ids in [('bad',['1']),('trash',[]),('trash',['invalid']),('trash',['-1'])]:
            with self.assertRaises(L.ParentActionError):L.apply({'id':1,'is_admin':True},action,ids)

    def test_mixed_state_batch_is_rolled_back(self):
        rows=[dict(id=1,user_id='10',deleted_at='2026-01-01')]
        with patch.object(L,'ensure'),patch.object(L.UA,'ensure'),patch.object(L.db,'query',return_value=rows),patch.object(L.db,'execute') as write,patch.object(L.db,'rollback') as rollback,patch.object(L.db,'commit') as commit:
            with self.assertRaises(L.ParentActionError):L.apply({'id':2,'is_admin':True},'trash',['1'])
            write.assert_not_called();commit.assert_not_called();rollback.assert_called_once()

    def test_non_parent_login_cannot_be_removed(self):
        rows=[dict(id=1,user_id='10',deleted_at=None)]
        with patch.object(L,'ensure'),patch.object(L.UA,'ensure'),patch.object(L.db,'query',return_value=rows),patch.object(L.db,'one',return_value={'id':10,'user_type':'1'}),patch.object(L.db,'execute') as write,patch.object(L.db,'rollback'):
            with self.assertRaises(L.ParentActionError):L.apply({'id':2,'is_admin':True},'trash',['1'])
            write.assert_not_called()

if __name__=='__main__':unittest.main()
